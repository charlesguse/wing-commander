# Research: The Board Loop

Input: `spec.md` carries no `[NEEDS CLARIFICATION]` markers — both
clarification rounds are folded into the spec's own Clarifications
section. The decisions below fix concrete shapes (script names, composite
boundaries, state representation, thresholds) the tasks stage needs before
it can write file-level tasks; each records what existing mechanism is
reused and what genuinely has no prior art in this repository.

## D1: One repository-only workflow, `board-loop.yml`

**Decision**: A single new workflow, `.github/workflows/board-loop.yml`,
carries no `workflow_call` trigger, states in its own header comment why
it is not a published stage (mirroring `auto-release.yml`'s own header —
"it releases THIS repository, not an adopter's"), and is triggered by
`schedule`, `workflow_dispatch`, and `pull_request: types: [closed]` (the
resume path, FR-002/FR-041).

**Rationale**: FR-062/FR-063 require exactly this shape, for the same
reason `auto-release.yml` already has it: every convention this feature
encodes (the 429 evidence, the `board:stalled` label, this repository's
own gate-suite entry point) would have to become a typed input to publish,
which would hand adopters a stage unusable without also adopting the
convention.

**Alternatives considered**: A `wing-commander-N-*.yml` wrapper around a
published inner workflow, matching the eight lifecycle stages — rejected;
that shape exists specifically to let a wrapper pass ambient
repository-only values into a portable, adopter-reusable `workflow_call`
body. This feature has no portable body to wrap (FR-062).

## D2: Kill switch and concurrency

**Decision**: Repository variable `WING_COMMANDER_BOARD_LOOP_PAUSED`, read
with the exact `if: vars.WING_COMMANDER_BOARD_LOOP_PAUSED != 'true'`
pattern `auto-release.yml` already uses at every job/step boundary that
can take a durable action, re-checked between rounds of an already-running
item (FR-051). Concurrency group `wing-commander-board-loop`,
`cancel-in-progress: false` — a second run queues behind an in-flight one,
never cancels or races it (FR-048).

**Rationale**: Reuses the exact family and checking idiom Constitution
Principle X names as this feature's required kill switch, and the
`cancel-in-progress: false` choice is what makes "queues rather than
races" (SC-005) true structurally rather than by convention.

## D3: Eligibility and selection is one script, two invocations

**Decision**: `.github/scripts/board_eligibility.py` exposes
`classify_issue(issue, labeled_events) -> Eligibility` (maintainer-authored
/ maintainer-labeled / pipeline-labeled / ineligible) and
`select(open_issues) -> issue | None` (oldest eligible, excluding FR-010's
closed/disposition/`board:stalled`/`stage:*`/`spec:*` state). The same
script runs twice: at runtime, fed real `gh issue list --json ...` and
`gh api .../timeline` data; at PR time, fed the checked-in fixtures
`verify-board-eligibility.py` supplies, asserting each of FR-064's four
eligibility branches (maintainer-authored no label / maintainer-applied
label / same label bot-applied / pipeline-only label) resolves as
expected.

**Rationale**: Matches this repository's existing self-test convention
(`verify-post-agent-credential-refresh.py`'s mutation-fixture pattern; the
D5-style hand-written-validator idiom from spec 056) — one script is both
the runtime decision and its own PR-time proof, rather than a decision
buried in workflow YAML that only a live run can exercise.

**Alternatives considered**: An allowlist checked against the label set
alone — rejected explicitly by the spec (FR-008): it would let a
bot-applied label (the `spec-request` spin-off, for instance) admit an
issue, which is the loop feeding itself work.

## D4: Triage's two close grounds — one reused, one new

**Decision**: Ground 1 (rate-limit 429) is decided by directly reusing
`wing-commander-agent-verdict`'s existing `rate-limited` verdict (spec 047)
against the cited run's transcript — `board_triage.py` calls the same
classification the watchdog already trusts, rather than re-parsing
`rate_limit_event`/`api_error_status` a second way. Ground 2 (upstream
action bump) has no prior art anywhere in this repository (confirmed: no
script compares a run's pinned `uses:` lines against `main`'s) and is new:
`board_triage.py` reads the cited run's own commit SHA, extracts each
`uses: owner/action@ref` line from the workflow file(s) that SHA ran, and
compares each against the same file's current line on `main`, flagging a
bump when they differ and `main`'s pin is the newer one.

**Rationale**: FR-059 requires reusing existing dedup/evidence machinery
rather than a second filing implementation; ground 1 already has an
authoritative, tested classifier. Ground 2 is a new evidence check because
none exists — recorded here so tasks does not go looking for
non-existent prior art.

**Third ground, deferred**: "already fixed on `main`" is explicitly *not*
implemented (FR-012's clarification) — `board_triage.py` has no function
for it. When the agent proposes this, the loop records the proposal and
named commit on the issue, applies `board:stalled`, and ends the run for
that item; this is a hand-over path, not a close path.

## D5: Route backstop reuses `pr-conversation.yml`'s idiom, extracted

**Decision**: `pr-conversation.yml`'s `small-unrelated-change` threshold
check (job `classify-and-announce`, inline `jq` over
`drafted-content.file-changes`, currently hardcoded to `files > 3` or
`lines > 40`) is extracted into a new composite,
`.github/actions/wing-commander-size-path-backstop/`, taking `max-files`
and `max-lines` as inputs (defaulted to 3/40 so `pr-conversation.yml`'s
existing call site is byte-identical in behavior) and returning
`over-threshold`, `measured-files`, `measured-lines`. `board-loop.yml`
calls the same composite with its own, larger, PR-reviewed constants (the
spec's own Assumptions section: "a separate PR-reviewed constant with the
same *shape* and the same narrow-only property" as pr-conversation's,
never pr-conversation's own numbers). `board_route_backstop.py` layers two
board-specific checks the shared composite does not do: contract-widening
detection (D6) and re-application to the final diff after a push
(FR-021).

**Rationale**: CLAUDE.md's single-home rule triggers the moment a second
workflow needs the same shape of check; this feature is exactly that
moment, and FR-018/FR-020/FR-061 all name reuse of this idiom explicitly.

**Alternatives considered**: A second, independent inline `jq` block in
`board-loop.yml` with the board's own numbers — rejected; it is the
literal pasted-copy CLAUDE.md's "Shared logic has exactly one home"
section warns against, this time for a check this feature would be the
one introducing a second copy of on day one.

## D6: Contract-widening detection (FR-019)

**Decision**: No existing gate checks "did this diff change a published
interface" as a route input. `board_route_backstop.py` adds a structural
check: the diff is contract-widening if it touches a `workflow_call:`
`inputs:`/`outputs:` block of any `.github/workflows/*.yml`, or the
`inputs:`/`outputs:` keys of any `wing-commander-*` composite's
`action.yml` — a path-and-YAML-key structural check, not a semantic read
of whether the change is "big." A contract-widening diff routes to
`spec-request` regardless of size (FR-019), independent of the
size-and-path backstop's own verdict.

**Rationale**: Principle VII already treats the published surface as a
deliberate-act boundary; detecting a touch to the exact keys that define
that surface is fully code-decidable and needs no agent judgment, keeping
Principle IX's split intact.

## D7: Fresh-`main` fetch and base-SHA recording (FR-022)

**Decision**: No shared composite exists for "fetch `origin/main` fresh,
then cut a branch from it, recording the base SHA" — `implement.yml`'s own
`steps.base.outputs.base-sha` capture is inline per-call, not a reusable
script. The fix step follows that same inline pattern: `git fetch origin
main`, `git checkout -b fix/<issue>-<slug> origin/<default-branch-sha>`,
and a step output `base-sha` recorded the same way, rather than
introducing a new shared composite for a two-line idiom `implement.yml`
itself does not share out.

**Rationale**: Extracting a composite for an idiom that has exactly one
existing inline instance (not two) is premature per CLAUDE.md's rule,
which triggers on a *second* copy, not a first plus a plan.

## D8: Gate suite invocation is the exact CI command (FR-024/FR-025)

**Decision**: The fix step runs `python3 .github/scripts/run-local-gates.py`
exactly once before any push, in the identical invocation shape
`implement.yml`'s `cycle`/`retry` gate-suite steps already use (capture to
a log, grep the first `FAIL` line on non-zero exit, surface it as a step
output consumed by the issue comment on failure).

**Rationale**: FR-025 requires "one invocation, not a re-typed list of
gates" — this is the one invocation every other stage that runs the gate
suite already uses.

## D9: PR-body citation and cross-linking reuse `wing-commander-outstanding-task-item`

**Decision**: Every artifact the loop creates outside the originating
issue — the fix PR, a `spec-request` issue, an out-of-scope review-finding
issue — is cross-linked onto the issue via the existing
`wing-commander-outstanding-task-item` composite (`gh issue comment
$ISSUE --body "- [ ] $PHRASE — $URL"`), the same mechanism spec 056's
filing step already reuses, rather than a second hand-written link format
(FR-045).

**Rationale**: FR-045 requires exactly this reuse; the composite was
promoted specifically so a second caller would not paste its `gh issue
comment` shape again.

## D10: Review is a second, context-isolated agent invocation

**Decision**: The reviewer runs as an independent job/step with no shared
transcript, memory, or prompt continuation from the fixer's invocation
(FR-028) — a fresh agent step whose prompt supplies only the PR diff and
issue context, never the fixer's session. It posts findings via `gh api
repos/:owner/:repo/pulls/:number/reviews -f event=COMMENT` (never `APPROVE`
or `REQUEST_CHANGES` — GitHub rejects both when the acting identity
authored the PR, and the loop's PR and its review share the
wing-commander-bot App identity, FR-029).

**Rationale**: FR-028/FR-029 are explicit about both constraints; `COMMENT`
is the only review event GitHub permits an author to leave on their own
PR, which is why this has never surfaced before — every prior fix PR in
this repository was human-authored.

## D11: Review findings — new schema, new fenced-block channel

**Decision**: A new schema, `.github/schemas/board-review-finding.schema.json`,
and a new fenced-block marker, ` ```wing-commander-review-findings `,
distinct from spec 056's `wing-commander-findings`/`stage-finding.schema.json`
pair. The reviewer's structured result carries an additional required
field spec 056's shape does not have: `in_scope` (boolean) — the datum
FR-033 requires the readiness report's open-finding count to be computed
from without parsing prose. Validation is a new hand-written script,
`verify-board-review-finding-schema.py`, following D5's precedent (spec
056: no third-party JSON Schema library; a small Python function checked
against the schema's required fields, proven against the schema by a
fixture that feeds every required field and confirms each omission is
caught).

**Rationale**: Overloading `stage-finding.schema.json` with a field the
other six stages never populate would make every existing stage's
extraction logic special-case a property it doesn't use; a distinct
schema for a distinct consumer (the readiness report, not a `found-by:*`
issue) keeps FR-016's single-home rule aimed at genuine duplication, not
at two shapes that happen to look similar.

## D12: Out-of-scope findings are filed through the existing durable-failure-issue composite

**Decision**: Each out-of-scope finding is filed via
`wing-commander-durable-failure-issue` with `operation: report`, `label:
found-by:board-review`, and `marker` set to `sha256("<issue>|<norm(title)>|<norm(file_path)>")`
(the same three-field shape as spec 056's D6 fingerprint, `norm` defined
identically), `comment-body-file` carrying the line `Found by the code
review of #<PR>` plus the quoted finding, blockquoted as untrusted data
(FR-032, FR-059).

**Rationale**: FR-059 requires reusing "the existing durable-failure issue
mechanism and the watchdog's fingerprint discipline... rather than a
second filing implementation" — this is that mechanism's `marker`-based
dedup path (spec 056's D7 extension), already built for exactly this
find-or-create-and-cross-link shape.

## D13: Readiness — checks green on the exact head SHA

**Decision**: No existing script re-derives "checks green on this exact
head SHA, never the PR's cached check summary" as a standalone,
consumable check — the closest precedent
(`_shared/auto-release-e2e-merge-decision.sh`) re-polls a live rollup
inline for one specific job, not as a reusable primitive. `board_readiness.py`
is new: it fetches `gh pr view <n> --json headRefOid,statusCheckRollup`
fresh at evaluation time (never a value captured earlier in the run),
asserts every entry in the rollup belongs to `headRefOid` and none is
missing/pending, and treats an empty rollup as not green (FR-037) — the
same `headRefOid` re-fetch idiom `watchdog.yml` already uses for its own
stale-shape avoidance, generalized to the rollup case FR-036/FR-037 newly
require.

**Decision (gate-suite condition)**: "the gate suite green on that same
SHA" (FR-066) is read as the `lint-workflows` job's own named check within
that same fresh rollup, not a second local re-run of
`run-local-gates.py` against the head — the rollup already contains that
exact result for that exact SHA; re-running it a second time would spend a
redundant checkout and gate pass to re-derive a fact CI already recorded.

**Rationale**: Avoids the ambiguity a future reader would hit wondering
whether "gate suite green" means "re-run it now" or "read what CI already
said" — recorded so tasks does not have to make this call mid-implementation.

## D14: Prove step reuses `auto-release.yml`'s dispatch-and-correlate idiom, extracted

**Decision**: `auto-release.yml`'s `dispatch-release` job (attempt-token
correlation, `gh workflow run` + poll-by-title-and-timestamp, wait on
`status` to `completed`, then verify the actual durable side effect
independent of the run's own conclusion) is extracted into
`.github/actions/wing-commander-dispatch-and-wait/`, parameterized by
target workflow, dispatch inputs, and the correlation/poll timings
`auto-release.yml` already uses as defaults. `auto-release.yml`'s
`dispatch-release` job is repointed at the new composite in the same
change; the prove step is the second caller, re-driving whichever
Actions-only workflow the fix changed.

**Rationale**: FR-042 needs exactly this shape (dispatch, correlate, poll
to terminal, verify independently) and CLAUDE.md's single-home rule
triggers the moment this feature needs it a second time — the idiom is
currently invisible-until-divergent-fix inline in one workflow only.

## D15: Actions-only decision is a path-based rule (FR-041)

**Decision**: The merged fix is Actions-only unless every changed path in
its diff is either under `docs/**` or `specs/**` (no runtime behavior) or
is a `.github/scripts/verify-*.py` gate script whose own PR-time run
already re-executed and proved it as part of the merged PR's required
checks (so a fresh dispatch would prove nothing FR-066's readiness report
did not already prove). Any path under `.github/workflows/**` or
`.github/actions/**` (excluding the verify-script carve-out) makes the fix
Actions-only.

**Rationale**: A deterministic, path-based rule keeps FR-041's "decide
whether the fixed behaviour runs only inside Actions" code-decided
(Principle IX) rather than an agent's guess, and matches the observation
that almost every runtime behavior in this repository IS Actions-only by
construction — the rule only needs to name the narrow exception (a gate
script already proven by the PR's own CI run).

## D16: Stand-down detection reads live pipeline run state

**Decision**: "An implement cycle is in flight" (FR-049) is decided by
`gh run list --workflow=implement.yml --status=in_progress --json
databaseId` returning non-empty at the moment the loop would start — read
directly from Actions' own run state, never inferred from usage metrics
or elapsed time (the spec's own Assumptions section: "read from the
pipeline's own run state, not inferred from usage metrics").

**Rationale**: This is the literal, cheapest-available signal: an
in-progress `implement.yml` run *is* an implement cycle in flight, with no
derivation step that could drift from what Actions itself reports.

## D17: Stop-comment handling reuses `pr-conversation.yml`'s `stop` procedure, retargeted

**Decision**: The board loop's own `stop` handling follows
`pr-conversation.yml`'s existing procedure exactly — scan the thread (the
issue's own comments, since the loop's durable-action announcements post
there per FR-044) for the loop's most recent status comment carrying a
`**Run:**` URL, extract and `gh run cancel` that run ID, skip the current
run's own announcement by `GITHUB_RUN_ID` — retargeted from a PR thread to
an issue thread, with the same authorized-actor check (FR-052).

**Rationale**: FR-052 explicitly requires "the same `stop` semantics the
pr-conversation stage already uses"; only the thread the loop posts to
changes (issue, not PR), not the cancellation mechanism itself.

**What counts as a stop request** (issue #539): a *command*, not the word.
pr-conversation classifies a comment into its `stop` category with an LLM
— the comment has to *be* a stop request. The board loop's check
(`board_stop_check.is_stop_command()`, whose module docstring is the
canonical statement) is deterministic, so it matches a first-line command
instead, and errs toward "not a stop": a false stop wedges the board.

1. Skip `>` quote lines, fenced code (a line starting with ```` ``` ```` or
   `~~~` toggles the fence; fence lines and their contents are skipped)
   and whole-line `<!-- … -->` comments. Take the first remaining
   non-empty line; if none remains, it is not a stop.
2. Normalise it: delete U+FEFF and zero-width characters (U+200B/200C/
   200D/2060), strip whitespace, drop leading `@handle` tokens
   (`^(?:@[\w-]+(?:\[bot\])?[\s,:]+)+`), then leading `*`/`_` emphasis.
3. It must start (case-insensitive) with an optional `please` plus
   separator, then `stop` or `/stop`, optional closing `*`/`_`, then one
   of: end of line; punctuation `. ! : , ; … ) 。 ！ ）`; a dash (`—`, `–`,
   or `-` not followed by a word character); or whitespace followed by a
   dash or colon. The rest of the line is the reason.

So `stop`, `Stop.`, `/stop`, `**stop**`, `Please stop.`,
`@wing-commander stop`, `stop: bad plan`, `/stop — reason`, and `stop`
under a quote-reply or a fenced log all count. Prose never does, including
prose that begins with "Stop" (`stop this please`,
`Stop the presses: this is great`), a question (`stop?`), `stopped`,
`non-stop`, `stop's`, a `stop` only on a later line, and a first line that
does not start with stop (`Hold on, stop`, `Wait — stop`). The original
`\bstop\b` word match read #402's owner analysis ("it should stop
retrying and finish") as a stop and wedged the board on it.

## D18: Round budget, turn ceiling, and model tier are reused constants

**Decision**: Round budget = 5 (the spec's own Assumptions section: "the
implement ⟲ converge cap is the nearest precedent at 5"), declared as a
checked-in constant in `board-loop.yml` alongside the size-and-path
backstop's own thresholds (D5). Per-agent turn ceiling reuses the existing
`Compute agent turn ceiling` step shape already present in `implement.yml`
(same formula, same `max-turns`-vs-ceiling distinction). Model tier
resolution reuses `wing-commander-9-pr-conversation.yml`'s `resolve-model`
job verbatim: default `vars.WING_COMMANDER_BOARD_LOOP_MODEL` (fallback
`claude-sonnet-5`), overridden to `claude-opus-5` when the issue (for
triage/route) or PR (for fix/review) carries the `model:opus` label
(FR-027).

**Rationale**: FR-050/FR-027 ask for a bounded budget and the existing
opus escalation "honoured" — reusing the exact precedent avoids a second,
subtly different tiering rule for one more stage.

## D19: Credential refresh across a fix→review cycle that can outlive one token

**Decision**: Every agent step this feature adds (triage-propose,
route-propose, fixer, reviewer, repeated per round) gets its own
post-agent credential-refresh triple exactly as spec 052 establishes:
`wing-commander-context`'s relay variable (`WC_BOT_TOKEN`) is re-minted
immediately after each agent step via an `if: always()` step, and every
subsequent step in the job reads the relayed variable rather than a
raw earlier output.

**Rationale**: The spec's own edge case ("The fix→review cycle outlives
the agent credential (over an hour)... must be exercised, not assumed")
names spec 052's mechanism directly; applying it uniformly is the reused
mechanism, not a new one.

## D20: Metrics and cost line reuse `wing-commander-metrics-summary`

**Decision**: Every agent step is immediately followed by
`wing-commander-metrics-summary` with the correct `transcript-path`/
`model`/`max-turns`/`ceiling` inputs, exactly as every other stage already
does, emitting the run's cost line and durable metrics record (FR-047,
SC-010).

**Rationale**: CLAUDE.md names this composite as the per-run cost line's
single home; a ninth stage reimplementing the formatter inline is exactly
what `verify-metrics-summary-record-emission.py` already exists to catch.

## D21: Board item state is a marker comment plus live GitHub state, not a new storage layer

**Decision**: The loop's own idea of "where an item is" is never trusted
from the marker alone. An HTML-comment marker
(`<!-- wing-commander-board-item: {"step":...,"round":...,"pr":...,"branch":...,"base_sha":...} -->`)
embedded in the loop's own latest status comment on the issue is the fast
path a resuming run reads first; every run additionally re-derives the
same fact from live GitHub state before acting (an existing PR referencing
the issue, the fix branch's existence, the PR's `state`) so a missing or
stale marker degrades to "read GitHub directly" rather than to undefined
behavior (FR-054, data-model.md "Board Item Marker").

**Rationale**: FR-054 requires "an interrupted run must leave the item in
a state the next run can read" and "MUST NOT open a second branch or PR
for an issue that already has one" — a marker alone is a single point of
failure if it is ever lost mid-run (e.g., the branch/PR exist but the
status comment never posted); re-deriving from GitHub's own state is the
same defense-in-depth this repository already applies to `spec-meta.json`
via `check-prerequisites.sh`.

**Alternatives considered**: A dedicated persisted file (a `board-state`
branch or a repository-variable JSON blob) — rejected; GitHub Issues/PRs
are already the durable, GitHub-native store this repository's Principle
III requires, and a second storage layer would need its own consistency
story with the issue/PR state it must never contradict.

## D22: `board:stalled` is a new label, documented the existing (manual) way

**Decision**: `board:stalled` is added to `docs/setup.md`'s existing
manual label table (this repository has no `.github/labels.yml` or other
machine-readable label config; every existing label, including
`spec-request` and `found-by:*`, is documented the same way).

**Rationale**: Matches the existing convention exactly; introducing a
labels-as-code mechanism for one new label would be out of proportion to
this feature and orthogonal to it.

## D23: No web tools, least-privilege allowlist per step

**Decision**: Every agent step's tool composition follows the existing
per-stage `default-disallowed-tools`/`extra-allowed-tools`/
`allowed-tools-override` input shape (`implement.yml`'s pattern), with
`WebSearch,WebFetch` always in the disallowed set (FR-057) and each step
(triage-propose, route-propose, fixer, reviewer) granted only the tools
its own task needs — the fixer gets write/push tools the reviewer never
does, the reviewer gets read/PR-comment tools the fixer never does.

**Rationale**: FR-057 requires least-privilege per step; reusing the
existing parameterized-allowlist composition avoids a new one-off
allowlist mechanism for this stage alone.

## D24: New gates, all reachable through the existing registry

**Decision**: Five new gate scripts
(`verify-board-eligibility.py`, `verify-board-triage.py`,
`verify-board-route-backstop.py`, `verify-board-readiness.py`,
`verify-board-review-finding-schema.py`) are each registered as a new
`Gate N — <description>` step in `lint-workflows.yml`; `verify-single-home-idioms.py`
gains two new `DECLARED_HOMES` entries
(`wing-commander-size-path-backstop`, `wing-commander-dispatch-and-wait`).
No manifest edit is needed for `run-local-gates.py` itself — it already
derives its invocation list by parsing `lint-workflows.yml`
(`wc_gate_registry.py`), so adding the CI step is the only registration
step required (FR-065).

**Rationale**: This is the existing registration mechanism working exactly
as designed; a second manifest would duplicate what
`wc_gate_registry.py` already automates.

## D25: FR-064's fixture enumeration maps one-to-one onto the four decision gates

**Decision**: The four gates FR-064 enumerates are exactly D3
(eligibility), D4 (triage), D5/D6 (route backstop, covering both the
size/path composite's own fixtures and the board-specific
contract-widening/final-diff-breach fixtures), and D13 (readiness) — no
fifth decision gate is needed beyond D11's schema self-test, which FR-064
does not separately enumerate but Principle VIII still requires for a new
schema.

**Rationale**: Confirms the five-gate scope in the project structure
(plan.md) traces directly to FR-064's own four bullets plus the
schema-validator precedent every new schema in this repository already
carries (spec 056's `verify-stage-finding-schema.py`).

## D26: The size-and-path backstop composite carries its own fixtures; board-loop's numbers are a separate constant

**Decision**: `wing-commander-size-path-backstop`'s own `tests/` fixtures
cover the composite's generic behavior (under/over threshold, by files and
by lines independently) parameterized, never hardcoding either caller's
numbers; `board_route_backstop.py`'s fixtures (FR-064 bullet 3) additionally
cover the board's own threshold values plus the two board-specific checks
(contract-widening, post-push final-diff breach) the shared composite does
not perform.

**Rationale**: Keeps the shared composite's test surface caller-agnostic
(so a future third caller with a third threshold pair does not need to
touch it) while the board-specific fixtures live where the board-specific
logic does.

## D27: No adopter-facing documentation change beyond the one label

**Decision**: `docs/adoption.md` (the published-stage configuration
reference) is unchanged by this feature — `board-loop.yml` has no
`workflow_call` inputs to document there (D1/FR-062). The only
documentation touch is `docs/setup.md`'s label table (D22).

**Rationale**: FR-062/FR-063's "moves no adopter-pinned surface" is a
documentation fact as much as a workflow-trigger fact; recording it here
keeps tasks from inventing an adoption-doc section for a surface that does
not exist.
