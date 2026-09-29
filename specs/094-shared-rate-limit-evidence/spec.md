# Feature Specification: One home for rate-limit evidence

**Feature Branch**: `094-shared-rate-limit-evidence`

**Created**: 2026-09-29

**Status**: Draft

**Input**: Lifecycle issue #726, routed from the board loop (originating issue #551): "agent-verdict robustness: NDJSON transcripts kill the step, non-object records hide the result, and rate-limit evidence is parsed in two places". Found by the code review of the #544 fix (branch `fix/544-verdict-rate-limit-status`), plus one comment item on the same review.

## Context

The originating issue named five items against `.github/actions/wing-commander-agent-verdict/action.yml` and `.github/scripts/board_triage.py`. Triaged against current `main` (commit `e4ce6e6`):

1. **An NDJSON or multi-document transcript kills the composite step** (exit 127 at the `eval "$(bash … count-turns.sh)"` line) — **already fixed**. The transcript is normalised once through `.github/actions/_shared/normalise-transcript.sh` (`jq -cs`, one flat array), and the `eval` now only sees lines matching `^(main_turns|sub_turns|reported)=[0-9]*$` (`action.yml:288-293`, both changes credited to #551/#572 in their own comments).

2. **Non-object transcript elements hide the terminal result** (`.type` on a number is a jq error that `|| true` swallows) — **already fixed**. Both the result read and the rate-limit read filter with `objects` before selecting on `.type` (`action.yml:146-147`, `action.yml:210`), and `normalise-transcript.sh` drops non-objects itself.

3. **Rate-limit evidence is parsed in two places** — **still true, and the substance of this feature.** The composite decides evidence with a jq program inside its `run:` block (`action.yml:197-224`); `board_triage.py`'s `check_rate_limit()` decides it again in Python over the same transcript (`board_triage.py:95-151`). As of #543 and the #544 fix the two rules differ **on purpose**, and they differ in a direction nobody chose as a whole:
   - the composite counts a `rate_limit_event` only when its status is `rejected` (case-insensitive, read at `.rate_limit_info.status` then top-level `.status`) or absent entirely; an `allowed` / `allowed_warning` event is informational and does not count;
   - triage counts **any** `rate_limit_event`, then guards the close with its own three extra tests — a failed terminal result, `0 <= num_turns <= 1`, and `total_cost_usd == 0`.

   So an ordinary long run that happens to carry an informational `allowed` event, failed for an unrelated reason on its first turn at zero cost, is `failed` to the composite and a *closable rate limit* to triage. The evidence triage then quotes on the issue reports `rate_limit_status: allowed` as grounds for closing.

   This is also a contract divergence, not only a duplication: `specs/057-autonomous-board-loop/research.md` D4 decided ground 1 by "directly reusing `wing-commander-agent-verdict`'s existing `rate-limited` verdict … rather than re-parsing `rate_limit_event`/`api_error_status` a second way". The shipped `board_triage.py` re-parses. `CLAUDE.md`'s "Shared logic has exactly one home" section is the general rule, and its own worked example is exactly this failure mode: a copy is invisible until the first divergent fix, and the #544 fix was that first divergent fix.

4. **Statusless events count as evidence on the strength of a hand-reduced fixture.** The composite's jq defaults a missing status to `rejected`, so a bare `{"type":"rate_limit_event"}` qualifies. The stated justification is issue #231's refused-run transcript, which exists in this repository only as `REFUSED_RETRY_TRANSCRIPT` in `.github/scripts/verify-truncated-cycle-carry-forward.py:842-849` — a hand-reduced copy of run 32675877971, whose `rate_limit_event` element is `{"type": "rate_limit_event"}` with no status. Whether the *real* artifact (`claude-execution-output-retry` of that run) also carried no status has never been checked. If it did carry one, the statusless-tolerant branch rests on a reduction artifact, and statusless events could fail closed instead.

5. **`reason=` interpolates `subtype` and `RUN_LABEL` without stripping CR/LF** (the review comment item) — **already fixed**. `RUN_LABEL` is `tr`-cleaned at read (`action.yml:107`), `subtype` is `gsub("[\r\n]"; " ")`-cleaned at read (`action.yml:154`), and every written value is cleaned again at the write site (`action.yml:311-318`).

This feature therefore covers items 3 and 4 only. Items 1, 2 and 5 are closed by the triage above, with the evidence quoted, not re-fixed.

## Open Questions

Three decisions are left to the clarify stage; each is marked in place below.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Rate-limit evidence is decided in one place (Priority: P1)

A maintainer changes what counts as rate-limit evidence in an agent transcript — a new status value the runtime starts emitting, a different field name, a decision to stop trusting a statusless event. They change it in one place, and both readers of that judgement — the verdict composite the whole fleet gates on, and the board loop's triage gate that closes issues on it — change with it.

**Why this priority**: the two copies have already diverged once, silently, and the divergence is load-bearing in both directions: the composite decides whether a stage run is retried, and triage decides whether a human-filed issue is closed without a fix. One of the two is wrong about `allowed` events today and no gate says which.

**Independent Test**: change the set of statuses that count as evidence in the single home; confirm without editing the other call site that both the composite's `verdict` output and `board_triage.py`'s close decision follow the change, and that a fixture asserting the old behaviour fails.

**Acceptance Scenarios**:

1. **Given** a transcript whose only `rate_limit_event` carries status `rejected`, **When** the composite classifies it and triage evaluates it, **Then** both agree that rate-limit evidence is present.
2. **Given** a transcript whose only `rate_limit_event` carries status `allowed` (or `allowed_warning`), **When** the composite classifies it and triage evaluates it, **Then** both agree on whether that is evidence — there is no input on which one says "evidence" and the other says "no evidence".
3. **Given** a transcript with a terminal result carrying `terminal_reason == "api_error"` and `api_error_status == "429"` and no `rate_limit_event` at all, **When** either reader evaluates it, **Then** both find evidence present, as both do today.
4. **Given** the evidence rule has a single home, **When** a maintainer greps the fleet for the status comparison, **Then** the composite's `run:` block no longer carries its own copy of the rule and `board_triage.py` no longer carries a second one.
5. **Given** the consolidation has landed, **When** a third site re-implements the evidence rule, **Then** a gate fails.

---

### User Story 2 - Triage still closes only on its own full evidence bar (Priority: P1)

The board loop closes a watchdog `pipeline-defect` issue only when the cited run was genuinely refused — one turn, zero cost, a failed result, and rate-limit evidence. Sharing the evidence predicate must not lower that bar, and must not let the composite's verdict alone close an issue.

**Why this priority**: closing a human-visible issue is the durable action Constitution IX governs; `#402` was already wrongly closed once on a 451-turn, $43 run that carried an informational event. This story is what keeps consolidation from becoming a regression, so it ships with User Story 1 rather than after it.

**Independent Test**: run the existing board-triage fixtures unchanged against the consolidated implementation; every fixture that closes today on grounds other than an `allowed`-only event still closes, and every fixture that refuses to close still refuses.

**Acceptance Scenarios**:

1. **Given** a transcript with rate-limit evidence but 451 turns and non-zero cost, **When** triage evaluates it, **Then** it does not close — the extra one-turn and zero-cost guards still apply after consolidation.
2. **Given** a transcript with rate-limit evidence and a successful terminal result, **When** triage evaluates it, **Then** it does not close.
3. **Given** a transcript whose `num_turns` or `total_cost_usd` is absent, non-numeric, or non-finite, **When** triage evaluates it, **Then** it does not close.
4. **Given** any closing decision, **When** triage records its evidence on the issue, **Then** the evidence still quotes the transcript's own field values verbatim, never a constant or a restatement of the rule.
5. **Given** the shared home, **When** triage runs, **Then** it reaches its verdict without a network call, a second agent invocation, or a dependency that is unavailable in the board-loop job's environment.

---

### User Story 3 - The statusless-event rule rests on real evidence (Priority: P2)

A maintainer asking "why does a `rate_limit_event` with no status count as a refusal?" finds an answer grounded in an actual runtime transcript, not in a hand-reduced test fixture.

**Why this priority**: it changes at most one branch of the rule, and the current behaviour is the safe direction (a real refusal is not demoted to `failed`). But it is the one remaining place where a documented rule cites a reduction of a run as if it were the run, so it is worth settling once — and settling it is a prerequisite for the shared predicate to be documented honestly.

**Independent Test**: the resolution is recorded with its source — either the real artifact's own `rate_limit_event` element, quoted, or an explicit statement that the artifact is no longer retrievable — and the rule in the single home cites that record rather than the fixture.

**Acceptance Scenarios**:

1. **Given** the statusless-tolerant branch, **When** a maintainer reads the single home, **Then** it cites the evidence the rule actually rests on, and no comment describes a hand-reduced fixture as the run it was reduced from.
2. **Given** the resolution keeps statusless events counting, **When** a bare `{"type":"rate_limit_event"}` appears with a failed one-turn zero-cost result, **Then** both readers still treat it as evidence and nothing about today's behaviour changes.
3. **Given** the resolution stops statusless events counting, **When** the #231 refused-run shape is replayed, **Then** the change of verdict for that shape is stated explicitly in the spec artifacts and every fixture asserting the old outcome is updated in the same change.
4. **Given** `verify-truncated-cycle-carry-forward.py`'s `REFUSED_RETRY_TRANSCRIPT` fixture, **When** the rule changes, **Then** that fixture's expectations are reconciled with the new rule rather than left asserting a verdict the rule no longer produces.

---

### Edge Cases

- A transcript carrying several `rate_limit_event` records, some informational and one refused: the last *qualifying* event is authoritative for classification today, while the reset time alone may fall back to the last event of any status. The single home must keep "which event is authoritative" and "which event may supply a display-only field" distinguishable, or the reset time starts gating.
- A `rate_limit_event` whose `status` is a non-string (a number, an object): the composite lower-cases only strings and compares the rest as-is; the shared rule needs one defined answer for a non-string status rather than two.
- A status that differs only in case (`REJECTED`): counts today, case-insensitively, and must keep counting.
- An NDJSON or multi-document transcript: the composite normalises before reading; `board_triage.py` uses `json.load` and returns `None` on it, which triage reads as `evidence_unavailable`. A literal single home changes triage's behaviour on that shape — which is an improvement, but it is a behaviour change and must be stated, not discovered.
- A transcript that is a single JSON object rather than an array: both readers accept it today, by different code paths.
- A transcript with no terminal result record at all: triage returns `None` before looking for evidence; the composite returns `failed` with "no terminal result record". Consolidating only the *evidence* predicate must not accidentally merge these two different answers to a different question.
- A missing, empty, or unparseable transcript file: the composite must still exit 0 with `unclassifiable` (its never-fails-its-own-step contract), and triage must still reach `evidence_unavailable` rather than raising.
- The single home being unavailable at runtime — absent from a partial checkout, or not executable: the composite must degrade without killing its step, exactly as it already does when `_shared/count-turns.sh` is missing, and triage must not close an issue on a silently empty answer.
- A published stage or an adopter repository that pins the composite: whatever the single home is, the composite must still resolve it from its own action directory, never from a path that only exists in this repository's checkout.
- The board-loop jobs that must import helpers from the pre-agent pristine snapshot rather than the working tree: triage runs from the working tree today, but a single home that lands under a directory the snapshot does not copy would strand any future caller in one of those jobs.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: What counts as rate-limit evidence in an agent execution transcript MUST be decided in exactly one place, and both `wing-commander-agent-verdict` and `board_triage.py`'s `check_rate_limit()` MUST reach that decision through it rather than each carrying its own implementation.
- **FR-002**: The single home MUST cover both halves of today's evidence test: a qualifying `rate_limit_event` record, and a terminal result carrying `terminal_reason == "api_error"` with `api_error_status == "429"`.
- **FR-003**: The single home MUST take the transcript it reads as an input and MUST NOT make a network call, invoke an agent, or read any file the caller did not name.
- **FR-004**: The unified evidence rule MUST produce the same answer for every input at both call sites — there MUST be no transcript on which the composite reports evidence and triage does not, or vice versa. [NEEDS CLARIFICATION: which rule the unified predicate adopts — the composite's `rejected`-or-statusless rule (informational `allowed`/`allowed_warning` events stop being grounds for triage to close an issue, narrowing an existing close path), or triage's any-event rule (the composite starts calling a run rate-limited on an informational event, widening a retry path #544 deliberately narrowed)?]
- **FR-005**: Triage's three additional close guards — a failed terminal result, `num_turns` a finite number in [0, 1], and `total_cost_usd` a finite number equal to 0 — MUST remain in force and MUST remain triage's own, outside the shared evidence predicate. Evidence alone MUST NOT close an issue.
- **FR-006**: Triage MUST continue to refuse to close when `num_turns` or `total_cost_usd` is absent, non-numeric, or non-finite.
- **FR-007**: The evidence triage records on an issue MUST continue to quote the cited transcript's own field values, never constants or a restatement of the rule.
- **FR-008**: `wing-commander-agent-verdict` MUST continue to exit 0 from its own step for every input, including one where the single home is missing, unreadable, or returns nothing.
- **FR-009**: The composite MUST continue to resolve everything it needs from its own action directory, so an adopter repository that pins the published action is unaffected. The single home MUST NOT be a path that exists only in this repository's own checkout layout.
- **FR-010**: The verdict ordering the composite ships today MUST be unchanged: `exhausted` before `rate-limited`, `rate-limited` before the generic `is_error`/`subtype` fallthrough, and a recovered 429 followed by a successful terminal result staying `healthy`.
- **FR-011**: The composite's `rate-limit-reset` output behaviour MUST be unchanged: the qualifying event's `resetsAt` verbatim when present, the last event of any status as a reset-only fallback, `unknown` when neither yields a usable value, an implausible epoch value never rendered as a fabricated date, and an empty string for every verdict other than `rate-limited`.
- **FR-012**: The window value (`rateLimitType`) MUST continue to come only from a qualifying event and MUST NOT fall back to an informational one.
- **FR-013**: Neither reader's transcript-shape tolerance MAY regress. A literal shared implementation that gives `board_triage.py` tolerance it lacks today (NDJSON, multi-document, non-object elements) is acceptable and MUST be recorded as an intended behaviour change, with a fixture for the newly accepted shape.
- **FR-014**: Every value the composite writes to its step outputs MUST remain a single line — CR/LF stripped both where each value is read and again at the write site — after the consolidation moves code across the boundary.
- **FR-015**: A structural check MUST exist that fails when the rate-limit evidence rule is re-implemented at a site other than its declared home, anywhere under `.github/workflows/`, `.github/actions/`, or `.github/scripts/`.
- **FR-016**: That check MUST be able to fail its own subject: every failure branch it ships MUST be exercised by a checked-in fixture or a mutation self-test, not by a manual demonstration (Constitution VIII).
- **FR-017**: A conformance check MUST exist that runs both call sites against one shared corpus of transcript fixtures and fails when they disagree about evidence — so FR-004 is held by a gate, not by a convention. The corpus MUST include, at minimum: a `rejected` event, an `allowed` event, an `allowed_warning` event, a statusless event, a non-string status, a mixed-status transcript, a terminal 429 with no event, and a transcript with neither.
- **FR-018**: The new checks MUST be reachable through the gate registry, MUST run the same subject with the same arguments locally as in CI, and MUST be triggered by changes to the files they check.
- **FR-019**: The existing gates covering these two subjects — Gate 22 (`verify-agent-verdict.py`) and Gate 82 (`verify-board-triage.py`) — MUST continue to pass, and each MUST continue to exercise the shipped subject rather than a hand-copied duplicate of it.
- **FR-020**: The statusless-`rate_limit_event` branch MUST be documented against the evidence it actually rests on. The real `claude-execution-output-retry` artifact of run 32675877971 MUST be inspected and its `rate_limit_event` element recorded verbatim; if the artifact is no longer retrievable, that MUST be stated in the spec artifacts as the reason the branch's justification stands on a reduction. [NEEDS CLARIFICATION: if the real artifact is unretrievable or shows the event *did* carry a status, does the statusless branch keep counting (status quo, a real refusal is never demoted to `failed`) or fail closed (statusless stops being evidence, and #231's replayed shape changes verdict)?]
- **FR-021**: Any comment or spec text that presents a hand-reduced fixture as the run it was reduced from MUST be corrected to say which it is.
- **FR-022**: `specs/047-rate-limited-verdict/data-model.md`'s "status tolerated absent" rule and `specs/057-autonomous-board-loop/research.md` D4's "rather than re-parsing … a second way" decision MUST both end this feature agreeing with the shipped code; where they do not, the artifact MUST be amended in this feature rather than left contradicting it.
- **FR-023**: The consolidation MUST NOT change any other observable behaviour of either subject — the same verdicts for the same transcripts, the same close/no-close decisions for the same fixtures, the same outputs in the same order.
- **FR-024**: The full PR-time gate suite MUST pass on the change, including the workflow-comment gates that byte-compare and mutate comment prose.
- **FR-025**: The single home MUST be internal rather than published: its interface MUST NOT become part of the adopter-pinned compatibility surface Constitution VII governs. [NEEDS CLARIFICATION: what shape is the single home — a shared shell/jq script under `.github/actions/_shared/` that the composite runs and `board_triage.py` invokes as a subprocess (matches the existing `_shared/` precedent, adds a jq-and-shell dependency to a Python gate); a Python module the composite runs as a command-line entrypoint and `board_triage.py` imports (one language, but the published composite must resolve it from its own action directory, which `.github/scripts/` is not); or two implementations kept deliberately, bound by the FR-017 conformance corpus alone (no move, weaker rule, cheapest change)?]

### Key Entities

- **Rate-limit evidence**: the judgement "this transcript shows the run was refused for rate-limit reasons", derived from `rate_limit_event` records and the terminal result's `terminal_reason`/`api_error_status`. The subject of this feature.
- **`rate_limit_event` record**: a transcript element of `type: "rate_limit_event"`, optionally carrying `status`, `resetsAt` and `rateLimitType` either top-level or nested under `rate_limit_info`.
- **Qualifying event**: the subset of `rate_limit_event` records that count as evidence. The composite and triage currently define this subset differently — FR-004 is the decision to define it once.
- **Close guard**: triage's additional tests (failed result, one turn, zero cost) applied *after* evidence is found; the reason evidence alone never closes an issue.
- **Declared home**: the single file that owns an idiom's implementation, named in the single-home gate's declared-homes list.
- **Conformance corpus**: one set of transcript fixtures run through both call sites, whose purpose is to fail when the two readers disagree.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The number of independent implementations of the rate-limit evidence rule drops from 2 to 1 (or, if FR-025 resolves to the conformance-only option, stays at 2 with every disagreement provably impossible under SC-002).
- **SC-002**: For every fixture in the conformance corpus — at least the 8 shapes FR-017 names — the composite and triage agree about evidence; a deliberately introduced divergence in either site makes at least one gate fail.
- **SC-003**: A change to what counts as rate-limit evidence lands in 1 file and is picked up by both readers, verifiable without editing the other call site.
- **SC-004**: 0 transcripts exist on which one reader reports evidence and the other does not, demonstrated by the corpus rather than asserted.
- **SC-005**: Every close/no-close decision the existing board-triage fixtures assert is unchanged, except those whose change FR-004's resolution explicitly requires — and each such change is named in the spec artifacts before it lands.
- **SC-006**: Every verdict the existing agent-verdict fixtures assert is unchanged, except those FR-004's resolution explicitly requires, each named the same way.
- **SC-007**: `wing-commander-agent-verdict` exits 0 for 100% of the inputs its gate exercises, including the single-home-absent case.
- **SC-008**: The statusless-event rule cites a named source — the real artifact's own record, quoted, or an explicit statement that it could not be retrieved — and 0 comments in the changed files describe a reduced fixture as the run itself.
- **SC-009**: Introducing a third implementation of the evidence rule at a new site causes at least one gate to fail, demonstrated by a checked-in fixture.
- **SC-010**: Each new check's failure branches are each exercised by a checked-in fixture or mutation self-test — 0 failure branches proven only by a manual demonstration.
- **SC-011**: The full PR-time gate suite passes, including Gate 22 and Gate 82 unchanged in intent.

## Assumptions

- Items 1, 2 and 5 of the originating issue are already fixed on `main` (commit `e4ce6e6`) and are closed by the triage in Context with the evidence quoted; this feature does not re-fix them.
- The runtime's `rate_limit_event` shape — `status` at `.rate_limit_info.status` or top-level, values `rejected` / `allowed` / `allowed_warning` — is as `specs/047-rate-limited-verdict/data-model.md` records it, and this feature does not go looking for further undocumented statuses beyond the artifact inspection FR-020 requires.
- `#402`'s wrong close (a 451-turn, $43 run carrying an informational event) is the historical reason evidence alone never closes, and that reason still holds.
- Triage's own three guards are correct as-is; this feature moves the evidence predicate, not the guards.
- The board-loop triage job runs helpers from the working tree (not the pristine snapshot), so a single home reachable from the checkout is available to it today; a future caller in a snapshot-bound job is an extension concern named in the edge cases, not a requirement here.
- `jq` is available wherever the composite runs, as it already is; whether it may be assumed available to a Python gate is part of FR-025's trade-off rather than a settled fact.
- The existing single-home gate's declared-homes list and waiver mechanism are reused rather than re-invented.
- Both `verify-agent-verdict.py` and `verify-board-triage.py` already execute their shipped subjects rather than copies, so a consolidation can be proven by extending them rather than by new parallel harnesses.
- Whether run 32675877971's artifact is still downloadable is unknown at specification time; FR-020 requires the attempt and the record of its outcome, not a particular finding.

## Out of Scope

- Any change to what the composite's other outputs mean — turn counting, `over-budget`, `subagent-turns`, `normalised-transcript`.
- Triage's second close ground (upstream action bump) and its `evidence_unavailable` ground.
- The "already fixed on `main`" third ground, which remains deliberately unimplemented.
- Which artifact the board loop downloads for a cited run, and how it chooses among several matching artifacts.
- Consolidating any other duplicated transcript read in the fleet beyond the rate-limit evidence rule.
- Changing the watchdog's own decision about what to do with a `rate-limited` verdict.
