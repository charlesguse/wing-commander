# Research: The Proof Run Can Actually Start

Spec 060 states that "no way to direct a run at one stage of the board loop
exists in the tree today; building it is this feature's work" (spec.md
Assumptions). This document makes the concrete engineering decisions that
mechanism needs, each derived from the current tree rather than guessed at.
Every decision below is a plan-time judgment call, not a spec clarification —
the spec's FR-002/FR-010/FR-014 answers are fixed inputs; these decisions are
how to build the mechanism those answers require.

## D1: The directed-stage mechanism is a new `workflow_dispatch` input triad on `board-loop.yml`, plus a job-level `uses` map

**Decision**: Add three `workflow_dispatch` inputs to `board-loop.yml`
(`.github/workflows/board-loop.yml:19-33`), alongside the existing
`attempt-token`:

- `directed-stage` (string, default `""`) — the job name the run is aimed
  at. Empty means "ordinary run" (schedule, plain manual dispatch, or the
  `pull_request: closed` path), preserving every existing trigger's
  behaviour unchanged.
- `directed-issue` (string, default `""`) — the issue number the directed
  run acts on.
- `directed-pr` (string, default `""`) — the PR number the directed run
  acts on (only `prove-gate`/`prove` need this; other directed stages act
  on the issue alone).

`board_prove.py` gains `scan_job_uses_graph(workflow_path)`, a sibling of
`scan_dispatchable_and_uses_graph()` that parses the *same* checked-out
`board-loop.yml` with the same `yaml.safe_load`, but walks
`doc["jobs"][job]["steps"]` per job instead of the whole file, applying the
same `WORKFLOW_REF_RE`/`COMPOSITE_REF_RE` (plus D4's script-import
resolution) to each job's own step text. This produces `{job_name:
sorted(referenced_paths)}` — which changed path(s) each job of
`board-loop.yml` actually executes.

`redrive_target()` is unchanged (FR-005: it still picks a *workflow*,
board-loop.yml or, someday, a second dispatchable member). A new
`directed_stage(changed_paths, job_uses_graph, aimable_jobs)` runs only
when the chosen redrive target's basename is `board-loop.yml` (covering
both of `redrive_target()`'s case 1 and case 2, which the spec's own
analysis shows always resolve to board-loop.yml on the current tree — spec.md
lines 78-87): it intersects `changed_paths` against each aimable job's
referenced set, and:

- exactly one aimable job's set intersects → that job is the directed
  stage;
- more than one does (a shared helper like `board_item_marker.py`) → tied
  broken by pipeline order, latest-stage-wins (`prove` > `readiness` >
  `review` > `triage`), because a later stage's own proof subsumes an
  earlier stage's use of the same helper and `prove` is the one FR-002a
  makes mandatory;
- none does → `None`, which is FR-010a's "no directed run reaches the
  changed behaviour" branch, never a fallback to a whole iteration
  (FR-002b).

**Rationale**: This reuses `scan_dispatchable_and_uses_graph()`'s existing
parse-and-regex idiom (single home, CLAUDE.md) rather than inventing a
second scanner, and keeps `redrive_target()`'s existing contract (which
`contracts/prove-step.md` and Gate 89 already depend on) untouched —
`directed_stage()` is purely additive, called only after a target is
already chosen.

**Alternatives considered**: A single function computing workflow-target
and job-target together was rejected because it would change
`redrive_target()`'s existing signature and break Gate 89's current
fixtures for no benefit — the two questions ("which workflow" and "which
job inside it") are genuinely separable, and case 2's external-target
future (FR-004) never has a job-level answer at all.

## D2: The aimable-stage set excludes `select`, `route`, and `fix`

**Decision**: `aimable_jobs = {"triage", "review", "readiness", "prove"}`
(where `"prove"` covers the `prove-gate` → `prove` pair jointly — both
gated by the same `directed-stage == 'prove'` condition, mirroring how they
already chain via `needs`). `select`, `route`, and `fix` are never
directed-stage targets; a changed path whose *only* executor is one of
those three renders FR-010a's "no directed run reaches this changed
behaviour," not a directed run of that job.

**Rationale**: FR-002 requires, of *every* directed proof run, that it
"MUST NOT select a board item and MUST NOT open a fix PR." `select`'s own
job body *is* the item-picking logic (`board_eligibility.select()`) — a
directed run of `select` alone would either pick nothing (proving
nothing) or pick a real item off the backlog (violating FR-002 outright).
`route` can push a branch/PR for the size-and-path backstop's post-push
breach case (contracts/board-loop-workflow.md: "branch/PR still cut only
for the post-push breach case, FR-021"), and `fix` exists to open the fix
PR — both are mutating actions FR-002 forbids a directed run from taking,
and neither job has a "dry-run" mode in the tree today; building one is
strictly more mechanism than this feature needs, since SC-001 only
promises "working for every changed stage a directed proof run *can be
aimed at*, with the rest recorded under FR-010a rather than mis-recorded" —
FR-010a's fallback is the correct, spec-sanctioned outcome for these three,
not a gap.

**Alternatives considered**: Building a dry-run flag for `fix`/`route` that
runs their real logic up to but not including `gh pr create`/branch push
was rejected as disproportionate — it would require threading a new mode
through the fix agent's own prompt and tool allowlist, which is exactly the
kind of scope creep CLAUDE.md's "don't design for hypothetical future
requirements" warns against, for stages this feature has no FR obligating
it to reach. `select`'s entry gates (kill switch, `board_stand_down.py`)
are already unit-tested directly against their own fixtures
(`.github/scripts/tests/board-eligibility/`) without needing a live
directed run at all, so nothing is lost by excluding `select`.

**Flag for the issue comment**: this narrows scope more than the spec
states outright — worth calling out as a decision made without
clarification, distinct from the spec's own three answered questions.

## D3: Concurrency moves from one workflow-level block to per-job blocks, keyed by directed-vs-ordinary

**Decision**: Replace `board-loop.yml`'s single workflow-level
`concurrency:` block (lines 40-46) with per-job blocks:

- `select`, `triage`, `route`, `fix`, `review`, `readiness`: unchanged
  group, `wing-commander-board-loop`, `cancel-in-progress: false`.
- `prove-gate`, `prove`: `group:` becomes a conditional expression —
  `wing-commander-board-loop-directed-proof` when
  `github.event_name == 'workflow_dispatch' && inputs.directed-stage != ''`
  (a directed dispatch), else `wing-commander-board-loop` (the ordinary
  `pull_request: closed` path, unchanged).

**Rationale**: This repo already uses per-job (not workflow-level)
`concurrency:` blocks keyed by a shared group name across several job
instances as its normal idiom for "some jobs of this workflow serialize
together, others don't" — `plan.yml:435-436`, `tasks.yml:461-462` /
`1375-1376` / `1547-1548` / `1692-1693`, `finalize.yml:310-311` /
`1429-1430`, `implement.yml:363-364` / `2706-2707`, and
`cleanup.yml:451-452` / `1012-1013` / `1263-1264` all key a job-level group
off a dynamic expression rather than a workflow-level literal.
`board-loop.yml` is the *only* workflow in the tree using a workflow-level
block at all (confirmed: `grep -n "^concurrency:"` across
`.github/workflows/*.yml` returns only `board-loop.yml:40`,
`auto-release.yml:22`, `auto-update-spec-kit.yml:208`, `intake.yml`'s
reusable-workflow-level block, `release.yml:55`, and `watchdog.yml:237` —
none of which face this feature's problem, since none of them
self-dispatches into its own group). Switching to per-job groups is
therefore not a novel pattern this feature introduces; it is bringing
`board-loop.yml` in line with the rest of the repo, and it is what
actually resolves the deadlock: a directed dispatch's `prove-gate`/`prove`
job instances never enter `wing-commander-board-loop` at all, so they are
never queued behind the run that dispatched them (which holds that group
via its own, separate `prove`/`prove-gate` job instance).

This is deliberately narrower than shape (a) from "What the owner decided"
(spec.md lines 119-131) — a separate group *alone*, without FR-002's
directed-run restriction, is what fact 3 rejects (spec.md lines 171-176:
"admits two full board iterations at once"). Because `select`/`route`/`fix`
are excluded from the aimable set (D2), nothing dispatched into
`wing-commander-board-loop-directed-proof` can ever pick a board item or
open a fix PR — so this group split combines shape (a)'s mechanism with
FR-002's directed-run bound, which is exactly what Story 5 says the
directed shape needs to avoid weakening FR-048: "only if 'takes no board
item' is checked rather than asserted" (spec.md line 367-368; the check
itself is D7/FR-017).

**Alternatives considered**: A single shared `wing-commander-board-loop`
group for directed dispatches too (no split) was rejected — it is the
literal status quo and reproduces the deadlock. A *per-run* directed group
(keyed by `attempt-token`, so every directed dispatch gets its own,
unshared group) was rejected because the edge case "Two directed proof
runs contend for one group" (spec.md lines 401-404) is explicit that two
merges proven close together *do* contend for one group — a per-run key
would make that edge case unreachable, contradicting the spec's own stated
scenario and FR-001a's need for a busy-check to have anything to check.

## D4: FR-001 (static) is a tree-read comparing group names; FR-001a (dynamic) reuses `board_stand_down.py`'s `gh run list` idiom against a run-name marker

**Decision — FR-001, static**: Before dispatching, `board_prove.py` gains
`joins_directed_group(target_workflow_path, target_job)` returning whether
dispatching `target_job` of `target_workflow_path` would join a
concurrency group the *calling* run also holds. For the self-target case
(target is `board-loop.yml`, `target_job` in `aimable_jobs`), this is
`True` by construction once D3 ships (directed dispatch → the separate
group, never the caller's own) — checked, not argued, by Gate 89's
extension (D6) reading `board-loop.yml`'s own per-job `concurrency.group:`
expressions off the tree and asserting the directed branch differs
literally from the ordinary branch. For a future external target (FR-004),
the check reads *that* workflow's own `concurrency:` block text and
confirms its group name is not `wing-commander-board-loop` (or, once this
feature ships, not `wing-commander-board-loop-directed-proof` either) —
still a tree-read, still deterministic, satisfying FR-001's "determined
before the dispatch... never by observing the timeout after the fact."

**Decision — FR-001a, dynamic**: `board-loop.yml`'s own `run-name:`
expression (currently line 36:
`${{ inputs.attempt-token && format('board-loop [attempt:{0}]',
inputs.attempt-token) || 'board-loop' }}`) gains a second token for a
directed dispatch: `board-loop [attempt:{0}] [directed:{1}]` where `{1}` is
`inputs.directed-stage`. Before the `prove` job's `redrive` step
dispatches a directed proof run, a new step runs
`gh run list --workflow=board-loop.yml --json databaseId,displayTitle,status -L 20`
and calls a new `board_prove.directed_proof_group_busy(run_list_json)`
that returns `True` if any row's `status` is not `completed` and its
`displayTitle` contains `[directed:`. This generalizes
`board_stand_down.py`'s existing `implement_cycle_in_flight()` shape
(`.github/scripts/board_stand_down.py`: `gh run list --workflow=X
--status=Y --json databaseId`) from one fixed workflow/status pair to a
display-title-marker filter, because GitHub's Actions API does not expose
a run's concurrency-group membership directly — the run-name marker is the
only deterministic, tree-derived way to identify "a run currently
occupying `wing-commander-board-loop-directed-proof`" without guessing at
undocumented API surface.

If `directed_proof_group_busy()` is `True`, the `redrive` step is skipped
(new `if:` clause) and the outcome step (D6) records the new "proof group
busy" reason (FR-001a) instead of dispatching into a wait it cannot win.

**Rationale**: Reuses the one existing precedent for "read run occupancy
via `gh run list --json`" in this codebase rather than inventing a second
idiom, and keeps the judgment (what counts as "busy") in a pure,
testable function per Principle IX.

**Alternatives considered**: Querying GitHub's REST API for the literal
concurrency-group state was investigated and rejected — the Actions API
surfaces a run's `status`/`conclusion`/`event`/`display_title` but not
which concurrency group it queued into; a run-name marker is the only
observable proxy the tree can construct for itself.

## D5: The reachability graph resolves `.github/scripts/**` Python imports (FR-013/FR-014/FR-015)

**Decision**: `scan_dispatchable_and_uses_graph()` (and the new
per-job `scan_job_uses_graph()`, D1) gain a `SCRIPT_IMPORT_RE` pass:
within any step's `run:` text that also contains the literal
`sys.path.insert(0, ".github/scripts")` (or `'.github/scripts'`), match
`from (\w+) import` and `import (\w+)` and resolve each captured module
name to `.github/scripts/<module>.py` if that file exists. This resolves
the module-loading idiom the explore pass confirmed is how
`board_item_marker`, `board_prove`, `board_stand_down`, and siblings are
actually loaded (`board-loop.yml:2550-2551` is one of many call sites).

Because a helper can import another helper (`board_prove.py` importing
`board_item_marker` in the future, say), the resolution also parses each
`.github/scripts/board_*.py` file's own top-level `from X import Y`/`import
X` lines (a static AST-free regex pass is sufficient — these are
first-party files with a uniform import style) to build a transitive
closure: if job J's steps load module A, and module A imports module B,
then B is in J's referenced set too.

The same `SCRIPT_IMPORT_RE` pass also applies to `.github/actions/**/action.yml`
composite files' own `run:` steps, so a helper executed only inside a
composite the workflow `uses:` is captured too (FR-014's third clause:
"helpers executed inside a composite the workflow uses").

FR-021's real-tree assertion (already the pattern Gate 89 uses — see the
Explore report's finding that it asserts `"board-loop.yml" in
real_dispatchable_basenames`) gains a new assertion: every
`.github/scripts/board_*.py` file resolves to at least one job in
`board-loop.yml`'s job-uses-graph, exactly as FR-014 requires
("FR-021's real-tree assertion MUST include that every
`.github/scripts/board_*.py` helper resolves to at least one stage").

**Rationale**: This is a direct, minimal extension of the exact regex-based
scanning idiom `scan_dispatchable_and_uses_graph()` already uses (single
home; no second parser). Ordering matters here per the spec's own
constraint (FR-014: "MUST NOT ship ahead of FR-002") — D5 only becomes safe
to route merges through once D1-D3 exist, because before D3's group split,
routing a board-helper-only merge into the re-drive branch would dispatch
straight into the same deadlock. This plan's task ordering (see plan.md
Project Structure) sequences D1-D3 before D5 for exactly that reason.

**Alternatives considered**: Requiring every helper to also appear as a
literal path string somewhere in `board-loop.yml` (so no import-resolution
is needed) was rejected — it would mean rewriting every board helper's
loading idiom repo-wide as a "single home" migration far outside this
feature's scope, purely to make a scanner's regex simpler.

## D6: The outcome-recording step gains a five-way (not three-way) branch, and a new gate covers the reason taxonomy

**Decision**: The `prove` job's "Record the proof outcome" step
(`board-loop.yml:2741-2769`) and its sibling "Determine this run's outcome
for the metrics record" step (`:2775-2789`) branch on a new, explicit
reason enum computed by `board_prove.py` rather than re-derived ad hoc in
the `run:` block's shell conditionals (Principle IX: this judgment gates a
durable action — closing or leaving open an issue — so it belongs in
tested Python, not shell `if`/`elif` chains reasoned about only at
review time):

| Reason (new field `outcome_reason`) | FR | Condition |
|---|---|---|
| `group-busy` | FR-001a | `directed_proof_group_busy()` was `True`; no dispatch attempted |
| `not-started` | FR-006/FR-007 | dispatched, correlated (`run-url` set), but `conclusion == "timeout"` **and** the correlated run's own `status` never left `queued` — distinguished from `unfinished` by a second `gh run view --json status,startedAt` read the `redrive` step's wrapper takes once, right after `wing-commander-dispatch-and-wait` returns `timeout`, never inside the composite itself (Out of Scope: no change to the composite's own mechanism) |
| `unfinished` | FR-006 | dispatched, correlated, `conclusion == "timeout"`, but the run *did* start (`startedAt` set) |
| `displaced` | FR-007 | correlation itself returned empty `run-url` *and* a follow-up `gh run list` (same call already made for D4's busy-check, re-used) shows no matching row at all — the queued run was evicted from the pending slot, not merely never observed |
| `uncorrelated` | existing (FR-043's current empty-run-url branch, kept) | correlation returned empty `run-url` for any other reason (ambiguous correlation) |
| `no-target` | FR-010a | `directed_stage()` returned `None` — no directed run reaches the changed behaviour |
| `nothing-reaches` | existing (kept, now distinct from `no-target`) | `redrive_target()` itself returned `None` — no dispatchable workflow at all references the change |
| `success` / `failure` | existing | `conclusion` from the composite, dispatch actually ran to completion |

**Rationale**: FR-006 requires "never started" and "started but
unfinished" be distinct; FR-007 requires displacement be distinct from
both; FR-010a requires "no directed run reaches this" be distinct from
"nothing in the repository reaches this change" (FR-013's existing
`nothing-reaches` case, which is about the *workflow* level, not the
*job* level). Collapsing these into one shell `if [ -z "$RUN_URL" ]`
branch, as today's code does, is exactly SC-003's five-condition list
undercounted to one. Computing the label in `board_prove.py` (invoked the
same way `steps.decide` already is, `board-loop.yml:2646-2674`) keeps the
judgment testable via Gate 89's fixture style rather than shell-quoted
conditionals nobody fixtures today.

**Alternatives considered**: Leaving the branching in the workflow's own
`run:` shell (as today) was rejected on Principle IX grounds — five
mutually-exclusive string comparisons in a bash `if`/`elif` chain, gating
whether an issue closes, is exactly the shape IX exists to move into code.

## D7: FR-017's overlap check is structural, not a new selection rule

**Decision**: `in_flight_candidate()` and `select()`
(`.github/scripts/board_eligibility.py`, lines ~140-216 per the Explore
report) already exclude `step in {"prove", "proven", ...TERMINAL_STEPS}`
from ordinary selection — this predates spec 060. FR-017's new obligation
is a *check* that this holds under the new overlap D3 introduces, not new
exclusion logic. Gate 89 (or a new, narrowly-scoped
`verify-directed-proof-no-item-conflict.py`, TBD at tasks time by whichever
keeps the single-home rule cleanest) gains:

1. A structural assertion that `aimable_jobs` (D2) contains none of
   `{"select", "route", "fix"}` — read directly from the constant in
   `board_prove.py`, so a future edit widening the aimable set without
   updating this reasoning fails the gate rather than silently regressing
   FR-002.
2. A fixture reusing `board_eligibility.py`'s existing test fixtures
   (`.github/scripts/tests/board-eligibility/in-flight/`) extended with one
   new case: an open issue carrying a `step: prove` marker *and* a second,
   concurrently-running board-loop schedule tick's `select()` call over the
   same issue set — asserting `select()` returns a different issue (or
   none), never the one being proven, exercising the specific case FR-017
   names ("the issue being proven is still open... while its proof run is
   in flight").

**Rationale**: This is D2 and existing `board_eligibility.py` logic
*checked together*, which is what "established by a check rather than by
argument" (FR-017) requires — no new runtime mechanism, because the
existing exclusion already covers it; the gap was only that nothing
asserted the combination.

## D8: FR-010b (a displaced prove run) is a new step in `select`, not a new scheduled workflow

**Decision**: A new module `.github/scripts/board_prove_displacement.py`
exposes `find_undetected_merges(merged_prs, issues_by_number)`: given the
repo's recently-merged, loop-labeled fix PRs (the same `Fixes #N` +
board-item-marker convention `prove-gate` already reads,
`board-loop.yml:2527-2556`) and each cited issue's current marker history,
returns issues whose most recent PR merged but whose marker history never
advanced to `prove`/`proven` and carries no proof-outcome comment at all —
exactly the signature of a `prove-gate`/`prove` run that never started
because its own hosting `pull_request: closed` run was displaced from
`wing-commander-board-loop`'s pending slot before it began.

This is wired as a new early step in the `select` job (which already runs
every schedule tick and already fetches open issues,
`board-loop.yml:162-165`), *after* the entry gates and *before* the
picking logic, so it runs whether or not `select` goes on to pick anything
this tick, and records "prove run displaced" on any issue it finds without
gating `select`'s own proceed/no-op decision.

**Rationale**: `select` is the one job structurally guaranteed to run on
every non-`pull_request` trigger, making it the natural periodic check
point — no new schedule, no new workflow, no new concurrency group to
reason about. It has to be a step inside a job that already holds no
special relationship to the specific merge being checked (unlike `prove`,
which by construction cannot run for a merge whose hosting run never
started).

**Alternatives considered**: A dedicated new scheduled workflow was
rejected — it would need its own concurrency group, its own kill-switch
check, and its own entry into the gate registry's wiring check, all to run
a check `select` can absorb as one more step at negligible marginal cost.

## D9: `contracts/prove-step.md` and `contracts/board-loop-workflow.md` (both under specs/057) are edited during implementation, not during this plan

The plan stage may only write inside `specs/060-self-redrive-concurrency/`.
FR-019's contract update is real implementation work — `tasks.md` carries
a task to fold this spec's `contracts/directed-proof-run.md`,
`contracts/concurrency-groups.md`, and `contracts/proof-outcome-taxonomy.md`
(all new, under specs/060) into `specs/057-autonomous-board-loop/contracts/
prove-step.md`'s existing three-branch table and
`board-loop-workflow.md`'s "Concurrency" section, so the two documents
agree with the shipped code (SC-006) rather than duplicating spec 060's
own contracts as a permanent second copy.
