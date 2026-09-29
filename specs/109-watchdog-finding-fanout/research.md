# Phase 0 Research: Watchdog Dedup That Survives Partial Signal Overlap and Class Fan-Out

`spec.md` carries no `[NEEDS CLARIFICATION]` marker — all three raised
during specification were answered on issue #792 before this plan started
(Clarifications section). What follows are the implementation-shape
decisions needed to turn FR-001–FR-025 into something `tasks.md` can build
against, grounded in the current `watchdog.yml` implementation (surveyed
below, file-by-file) and in spec 024's own precedent for amending spec
015's dedup contract in place.

## Decision: Overlap matching reads every candidate's accumulated id set from ONE bulk `gh issue list` call, not a per-candidate follow-up

**Decision**: The `Dedup search` step (`watchdog.yml:3175-3225`) adds
`comments` to its existing `--json number,state,body` field list:

```bash
gh issue list --repo "$GITHUB_REPOSITORY" --label "pipeline-defect" \
  --label "$class_label" --state all --limit 200 \
  --json number,state,body,comments
```

`gh issue list --json comments` returns each candidate's full comment
list (author, body, createdAt — the same shape `gh issue view --json
comments` already returns), in the one already-budgeted API call. Each
candidate's **matchable id set** is computed locally (`jq`, no further
`gh` calls) as the union of: the ids recorded in the issue body's new
marker (below) plus the ids recorded in each comment's marker, read back
with a plain string match on the marker's own delimiters — never parsed
as, or trusted as, agent-authored prose (Constitution IX).

**Rationale**: FR-003 requires a later run to read back "the full set of
collector signal ids its accumulated occurrences have cited — not only
those of the first occurrence," and Acceptance Scenario 3 (User Story 1)
requires a match on an id that was only ever cited in a *recurrence
comment*, never the original body — so body-only reads (today's shape)
are insufficient. The alternative of a separate `gh issue view --json
comments` call per candidate would multiply the read cost by up to 200 per
triaged finding (the existing `--limit 200` bound); folding `comments`
into the one bulk `gh issue list` call keeps the dedup lookup's read cost
exactly what it is today — one API call per finding, not one plus N.

**Alternatives considered**: A ledger file or a second GitHub-native store
mapping signal id → issue number — rejected on the same grounds spec 015's
and spec 024's own research already rejected it: a second source of truth
that can desync from the issues it describes, and unnecessary now that
`gh issue list --json comments` supplies the same information in the
existing call shape. Editing the issue body on each recurrence to append
new ids — rejected outright: FR-003 and the edge cases explicitly forbid
editing an issue body after creation ("the watchdog MUST NOT edit an issue
body"), matching today's shipped behavior and preserving the original
`_Fingerprint facts:_` line as an unaltered anchor for the exact-match path
(FR-015).

## Decision: A new readable marker carries the ids each occurrence cites; the opaque `fingerprint=` marker is kept unchanged for the closed-issue exact-match path

**Decision**: The issue body (on create) and every recurrence comment
gain a second HTML-comment marker alongside the existing
`<!-- wing-commander-watchdog: fingerprint=<hash> -->`:

```
<!-- wing-commander-watchdog: signal-ids=<id1>,<id2>,... -->
```

listing exactly the ids *that occurrence* cited (post-validation, the same
`valid` array `Compute fingerprint` already derives) — sorted, comma-joined,
same normalization the fingerprint basis already uses, so the marker is
itself deterministic and diffable. The human-readable text alongside it
(FR-017) states which of those ids the match was made on and which are new
to this occurrence, e.g. "Matched on `<id>`. New to this issue: `<id2>`."
The exact `fingerprint=<hash>` marker is unchanged in meaning and format —
it still identifies one specific *citation set*, and remains the sole
mechanism the closed-issue path matches on (FR-006, FR-015): a closed
issue's original citation set may or may not overlap a new finding's ids,
but only an exact re-hit reopens it, exactly as today.

**Rationale**: FR-002 requires the match identity to depend only on
deterministic collector output, never on diagnose's prose — a marker
listing raw ids (not a narrative sentence) keeps the read-back mechanical.
FR-015 requires pre-existing issues (carrying only the opaque hash) to stay
matchable through the unchanged exact path, which this design satisfies by
leaving that marker and its matching code untouched and additive-only.

**Alternatives considered**: Replacing the opaque `fingerprint=` marker
with the readable id list outright — rejected: it would silently change
the exact-match identity's format for every future write, and the edge
case "issues filed before this change... stay matchable through the
existing exact-fingerprint path" requires that path to keep working
unmodified; two independent markers achieves that with no migration step.

## Decision: The matchable id set is capped at the 30 most-recently-cited distinct ids per issue, oldest evicted first

**Decision**: When a candidate's body/comment markers are unioned (first
decision above), only the 30 most recent distinct ids (by occurrence order:
body first, then comments oldest-to-newest) count toward the matchable
set. An issue that has accumulated more than 30 distinct ids across its
occurrences keeps matching on its most recent 30; an id that ages out of
the window still remains legible in its own occurrence's comment (FR-017
is about *that occurrence's* record, which is never edited), it simply
stops contributing to *future* matches. The cap is a literal constant in
the matching step's own code, named in a comment there (FR-008).

**Rationale**: FR-008 requires a stated bound so a long-lived issue's
matchable identity cannot grow without limit. 30 is chosen against the
observed corpus this spec cites: the three-issue `gate-suite-failure`
chain (#729/#732/#765) reached 3 occurrences and at most 4 distinct ids
across all of them: 30 gives roughly an order of magnitude of headroom
above every recurrence count actually observed, so no realistic issue in
this corpus is affected by the cap, while still bounding the pathological
case (a single issue open for months, accumulating a new id on almost
every run) from drifting toward "matches nearly anything the class has
ever produced" — the transitive-growth edge case this spec names.

**Alternatives considered**: Capping by occurrence count (e.g., "only the
last 10 occurrences contribute ids") rather than by distinct id count —
rejected as a weaker bound: a single occurrence can cite several ids at
once (Acceptance Scenario 1's `{A,C,D}` example), so an occurrence-count
cap does not actually bound the id-set size the way FR-008 asks for. No
cap at all — rejected outright; that is the transitive-growth edge case
FR-008 exists to close.

## Decision: Multi-match resolution acts on `sort -n | head -1` over open matches; the occurrence record on that issue names the rest

**Decision**: The dedup-search step's overlap branch computes the full
list of open candidates whose matchable id set intersects the finding's
cited ids, sorts by issue number ascending, and reports `outcome=overlap`
with `issue-number=<lowest>` plus a new `other-matches=<n2>,<n3>,...`
output. `act`'s "Ensure pipeline-defect issue" step comments on
`issue-number` only — never writes to `other-matches` — and the comment
body's human-readable line names them: "Also matches #n2, #n3 (not
merged — a maintainer can combine them by hand)." No issue in
`other-matches` is labeled, commented on, closed, reopened, or relabeled by
this feature (FR-007).

**Rationale**: FR-007 is explicit about the resolution (lowest-numbered)
and explicit that multi-match is not `data-integrity` and must not close
or merge anything. Reusing `data-integrity`'s existing "report, do not
write" shape for a *different* condition (more than one *exact* match,
which stays an actual integrity problem — two issues should never carry
the identical fingerprint) would conflate two conditions FR-019 requires
to stay distinct: multi-match is decided and routine under overlap
matching, exact-duplicate-fingerprint is still an unexplained anomaly.

**Alternatives considered**: Newest-numbered match, or the match with the
largest id overlap — rejected: the spec's own answer to Q2 names
lowest-numbered explicitly, precisely because it is the deterministic,
argument-free tiebreak (Constitution IX) and tends toward the
longest-tracked issue for a chain that has been open the longest.

## Decision: Gate-suite finding detection and the FR-009 cycle-state condition share one new artifact implement.yml uploads and watchdog.yml downloads

**Decision**: `implement.yml`'s existing "Read back cycle outcome" step
(the one computing `converged`/`handoff`/`reason`, `implement.yml:1379-1442`,
FR-010 of spec 059) gains one more step immediately after it,
`Record cycle outcome for watchdog`, which writes and uploads a small JSON
artifact (mirroring the existing `claude-execution-output-*` artifact
convention `collect-execution-output` already downloads,
`watchdog.yml:515-562`):

```json
{"converged": false, "handoff": false,
 "gate-suite-outcome": "fail", "gate-suite-first-failure": "..."}
```

`gate-suite-outcome`/`gate-suite-first-failure` are read from whichever of
`gate-suite-cycle`/`gate-suite-retry` ran last in that attempt
(`implement.yml:797-813`, `1511-1525`). `watchdog.yml`'s `collect` job
gains a new collector, `Collect: cycle outcome`, downloading this artifact
the same attribution-guarded way `collect-execution-output` does (a
missing artifact — the inspected run predates this feature, is not an
implement run, or the upload itself failed — is a successful *empty*
contribution, never a step failure, satisfying FR-010's "when that state
cannot be determined, the finding MUST be triaged as normal"). When
`gate-suite-outcome == "fail"`, the SAME step also emits a new signal into
`signals.json`: `{kind: "gate-suite-failure", ident: {"first-failure":
<normalized>}}` (per-source projection, same convention as every other
`Stamp signal ids` branch) — this is the one new signal kind diagnose can
cite, and it is what makes a finding a "gate-suite finding" (below).

**Rationale**: Job/step *outputs* are not retrievable from the Actions API
for an already-completed run (only logs and artifacts are) — `converged`/
`handoff` exist today only as `$GITHUB_OUTPUT` values scoped to
`implement.yml`'s own job graph, never surfaced anywhere `watchdog.yml`
(inspecting that run after the fact, over the API) can read them back.
FR-010 names these exact facts as "already emit[ted]," which is true of
their *existence* but not of their *visibility* to an external inspector;
this decision is the missing visibility step, not a new fact. The artifact
convention (rather than the job-log/WC-SENTINEL-token convention the
`step-summary` collector uses) is chosen because this is genuinely
*structured*, multi-field data (two booleans plus an enum plus free text),
which the token convention was built for single bare words, not key-value
payloads — reusing the collector shape that already exists for
structured facts is the smaller change.

**Alternatives considered**: A `WC-SENTINEL: cycle-converged`/`WC-SENTINEL:
cycle-continuing` token pair, reusing the step-summary collector's
existing log-scan mechanism — rejected as the primary mechanism: it would
need three-to-four distinct bare tokens to cover
converged/handoff/gate-suite-outcome jointly, loses the free-text
first-failure detail FR-017-adjacent legibility benefits from, and the
job-log-scan collector already carries a documented masking hazard
(`watchdog.yml:1176-1189`) between its two passes that a new multi-token
addition would need to reason about. Determining "converging" purely from
`spec-meta` stage/`stalled` label without a new fact — rejected: neither
distinguishes "this cycle will dispatch another" from "this cycle handed
off to finalize," which is exactly the FR-009(i)/(ii) boundary; both facts
are needed together, matching FR-010's own text ("together with the
spec-meta stage and stalled label the watchdog already reads").

## Decision: A gate-suite finding is one whose cited ids are *entirely* `gate-suite-failure`-kind; the FR-009 condition is `gate-suite finding ∧ ¬stalled ∧ cycle-outcome present ∧ converged=false ∧ handoff=false`

**Decision**: Triage computes, per finding, whether every one of its
(validated) cited signal ids has kind `gate-suite-failure` (from the same
`signals.json` the fingerprint step already cross-checks cited ids
against). If so, and the run's cycle-outcome artifact is present with
`converged=false` and `handoff=false`, and neither `spec-meta` stage
`stalled` nor the `stalled` label apply, the finding gets a new triage
outcome, `converging-gate-suite`, which suppresses the write exactly like
`data-integrity`/`unknown` do but is reported under its own distinct
wording (FR-011, FR-019) — never as `data-integrity` or `unknown`, which
mean "could not decide" rather than "decided this is not a defect."

**Rationale**: Key Entities defines a gate-suite finding as one "whose
cited signals come from the inspected run's gate suite failure" (singular
subject: the failure, not "at least one of several unrelated problems") —
and Acceptance Scenario 5 (User Story 2) requires a run whose findings mix
gate-suite evidence with unrelated evidence to suppress *only* the
gate-suite ones. "All cited ids are gate-suite-kind" is the reading under
which a finding that also cites, say, a `tool-denial` id is correctly left
unsuppressed (it is not purely a gate-suite finding), while a finding
citing only `gate-suite-failure` ids — whatever class label diagnose
assigned it, per FR-009's "whatever class the diagnose agent assigned it"
— is. Requiring the stalled checks to override even a "continuing"-looking
cycle-outcome matches Acceptance Scenario 3 exactly ("an implement stage
that stalled... filed as normal") and FR-010's undeterminable-state
default (missing artifact ⇒ file as normal, never suppress on a guess).

**Alternatives considered**: "At least one cited id is gate-suite-kind" —
rejected: this would suppress a finding that legitimately combines
gate-suite evidence with an unrelated, independently real problem, which
Acceptance Scenario 5 forbids. A new finding *class* (`gate-suite-failure`)
that diagnose is instructed to always choose for such findings — rejected:
the spec's own pinned reading is explicit that "gate-suite finding" is not
one class and the six-class run 36484099706 is the motivating
counter-example; scoping by class would contradict the very observation
that opened this feature.

## Decision: FR-013's `{stage, tool}` denial separation needs no code change — it is already guaranteed by the existing per-source signal-id projection, and is verified by a fixture rather than reimplemented

**Decision**: `Stamp signal ids` already keys `tool-denial` ids by
`{stage, tool}` (`watchdog.yml:1928-1930`, #266) — two denial findings
from different `{stage, tool}` pairs cite *disjoint* signal ids by
construction, so overlap matching (which only ever matches on a *shared*
id) cannot merge them regardless of any new matching logic this feature
adds. No change lands in the `tool-denial` collector or its id projection.
This feature's obligation here is entirely the FR-021 fixture (three
denial pairs replayed, asserting three issues, `quickstart.md` Scenario
and `tasks.md`'s coverage item) — a regression test for a guarantee that
already holds, not new behavior.

**Rationale**: FR-013 asks that the separation "be preserved," and User
Story 3's own framing calls it "a correctness bound... rather than a
feature of its own" whose risk is a *silent* regression — the risk this
feature could introduce is accidentally widening the matching scope (e.g.,
if a future edit computed overlap on some coarser projection of the id),
not a missing capability today. Recording "no code change, verified by
fixture" explicitly (rather than silently skipping it) follows spec 024's
own precedent of stating a no-change decision as a decision, not an
oversight.

**Alternatives considered**: None — the existing id-keying scheme already
provides the guarantee; there is no simpler or more-correct alternative
implementation to consider here.

## Decision: FR-016's truncation guard compares the fetched candidate count against the `--limit 200` ceiling before trusting a "none"/"no overlap" result

**Decision**: The dedup-search step checks `count(results) == 200`
(the exact limit) as a proxy for "the class label may have more open
issues than were fetched." When true, the outcome is `unknown`
(write-suppressed, reported) rather than `none` or a computed overlap
result, regardless of what the fetched 200 do or don't match — mirroring
FR-028 of spec 015's existing `unknown`-vs-`none` distinction, applied to
a second failure shape (silent truncation, not an API error).

**Rationale**: FR-016 states this exactly: a truncated candidate set "MUST
NOT be 'matched nothing.'" A count that lands exactly on the requested
limit is gh's own signal that more results may exist server-side (the same
heuristic `--paginate`-aware call sites elsewhere in this repository already
apply); 200 open+closed `pipeline-defect` issues of one class has never
occurred in this corpus, so this branch is not expected to fire in
practice, but its absence is exactly the kind of gap this feature's own
motivating defects came from (a filter nobody suspected until three
duplicates sat on the board).

**Alternatives considered**: Raising `--limit` instead of adding a
truncation guard — rejected: the spec explicitly keeps the fetch bound
("the fetch does not widen") and asks only that a truncation be *reported*
truthfully, not that truncation be made less likely.

## Open items intentionally deferred beyond this plan

- The exact gate number for the new self-test fixtures (FR-020–FR-022) is
  `tasks.md`-level detail — `run-local-gates.py` currently allocates
  through Gate 124; issue #660 already tracks this repository's own
  gate-numbering collision risk across in-flight specs, so the literal
  number is assigned at implementation time, not fixed here.
- The precise wording of the amended FR-012–FR-016 text inside
  `specs/015-pipeline-watchdog/spec.md` (which identifiers are edited in
  place vs. superseded) is `tasks.md`-level detail, following spec 024's
  own precedent for the identical kind of amendment; this plan fixes which
  requirements change and why (Phase 1 contracts below), not the final
  diff text.
- Whether the new `Collect: cycle outcome` collector's artifact is a
  dedicated upload or folded into the existing execution-output artifact's
  own JSON shape is left to `tasks.md`; either satisfies this plan's
  contract as long as the four fields above are present and the
  attribution guard (skipped/cancelled ⇒ empty contribution) applies.

## Decisions made without clarification (recorded per this run's instructions)

None of these were `[NEEDS CLARIFICATION]` markers in `spec.md` — all
three of those were resolved on issue #792 before this plan started. The
items below are ordinary plan-stage implementation-shape choices spec.md
deliberately left open (per the requirements checklist's own note: "The
spec deliberately does not choose the marker format for FR-003, the lookup
mechanics for FR-016, the bound's value for FR-008... those are plan-stage
decisions"), listed here for visibility:

- The FR-008 bound is fixed at **30 distinct signal ids per issue,
  oldest-evicted-first**.
- The FR-003/FR-017 readable record is a second `signal-ids=` HTML-comment
  marker, additive alongside the unchanged opaque `fingerprint=` marker.
- The FR-009/FR-010 cycle-state facts are surfaced via a new artifact
  `implement.yml` uploads and `watchdog.yml` downloads, rather than a
  log-scanned sentinel token.
- "Gate-suite finding" (FR-009) is read as *all* cited ids being
  gate-suite-kind, not *any*.
