# Phase 0 Research: The Per-Job Minute Floor

spec.md's own Clarifications session already resolved the three
highest-leverage ambiguities (the agent-skip key, the resolve fold-in
scope, the persistence model). What remains for this phase is mechanical:
how each of the three sub-problems is actually built against this
repository's existing job graph, gate registry, and composite
conventions. Each item is a plan-level decision, flagged where a
reasonable alternative was rejected.

## A. The image check

### R-A1: The check job gains a job-level `if:`; every direct dependent gains an explicit tolerant condition

**Decision**: `verify-image-prerequisites` gains
`if: inputs.container-image != ''` at the **job** level (today only its
one step carries that condition). Every job that names
`verify-image-prerequisites` in its `needs:` gains an explicit `if:`
that tolerates a `skipped` result for that one dependency while still
requiring `success` from every other dependency, in one of three shapes:

| Shape | Today | After |
|---|---|---|
| **Entry job** (image check is its only dependency, no `if:` today) | bare `needs: verify-image-prerequisites` | `if: !cancelled() && needs.verify-image-prerequisites.result != 'failure'` |
| **Entry job with other dependencies** | bare `needs: [verify-image-prerequisites, X]` | `if: !cancelled() && needs.verify-image-prerequisites.result != 'failure' && needs.X.result == 'success'` |
| **Survivor job** (already uses a status function, e.g. `stalled`, `report-unhandled-failure`) | `needs.verify-image-prerequisites.result == 'success'` inside a larger `!cancelled() && ...` expression | the same clause narrows to `!= 'failure'`; every other clause is unchanged |

A job with no other dependency has "nothing left to require" once the
check is tolerant (spec.md's own edge case) — `!cancelled() &&
needs.verify-image-prerequisites.result != 'failure'` is that job's
complete condition, not an omission.

**Rationale**: the check job's own in-repo comment
(`intake.yml`: "this job must NEVER skip, or the whole needs-closure
silently no-ops every stage (#224)") names the exact failure mode a
naive job-level `if:` would reintroduce — GitHub's default `if:` for a
job with no explicit condition is `success()` over its `needs:`, and
`success()` treats a **skipped** dependency the same as a **failed**
one: propagate the skip. #224 is why the condition was pushed down to
the step instead. FR-004 requires the opposite fix: keep the job-level
skip (so GitHub doesn't bill a runner) but make every dependent
explicitly tolerant, rather than relying on default propagation ever
again. `!cancelled()` is required (not optional) the moment any job's
`if:` stops being the bare default, because overriding `if:` also
opts a job out of GitHub's automatic cancellation handling — the
existing `stalled`/`report-unhandled-failure` jobs already carry it for
this reason, and Gate 15 already exists to catch a status-function `if:`
that forgets an ancestor.

**Alternatives considered**: `needs.verify-image-prerequisites.result ==
'success' || needs.verify-image-prerequisites.result == 'skipped'` —
equivalent in truth table to `!= 'failure'` for this job (a `needs:`
result is only ever `success`, `failure`, `cancelled`, or `skipped`, and
`cancelled` is already excluded by the leading `!cancelled()`), but
`!= 'failure'` is what FR-004's own text ("tolerate a *skipped* check")
reads as and is one comparison instead of two; both are acceptable, this
plan picks the shorter form uniformly so Gate 23's amendment (R-A3) has
one literal shape to check for, not two.

### R-A2: A chain job (check → middle → late) also needs a rewrite, because adding ANY status function upstream disables GitHub's implicit protection for the whole closure

**Decision, corrected from this document's original sketch** (MF-04;
commit fec7b6a): every job in the check's closure carries a status
function plus explicit guards — not just the jobs naming
`verify-image-prerequisites` directly in `needs:`. Gate 23 enforces it;
verified empirically across the shipped tree: 45 jobs in the closure, 0
without a status function.

**Why the original sketch was wrong**: GitHub's implicit `success()`
default only protects a job whose `if:` is entirely absent. The moment
ANY job upstream in a chain gains an explicit status-function `if:` (R-A1's
`!cancelled() && needs.verify-image-prerequisites.result != 'failure'`,
added to the *middle* job so it tolerates a skipped check), GitHub's
automatic "skip if any transitive dependency failed" behavior stops
applying to jobs downstream of it too — not because the *late* job's own
`if:` changed, but because `middle`'s `result` becoming `success` no
longer implies every one of ITS OWN dependencies also succeeded. A late
job reading only `needs.middle.result == 'success'` — with no `if:` at
all, relying on the implicit default — silently loses the protection the
implicit default used to give it, because the implicit default itself
requires the immediate dependency to have no `if:`, and `middle` now
does. `plan.yml`'s `plan` job is the shipped example: it depends on
`resolve-spec` (which now carries `!cancelled()`), and needed its OWN
explicit `!cancelled() && needs.verify-image-prerequisites.result !=
'failure' && needs.resolve-spec.result == 'success'` — naming
`verify-image-prerequisites` in `needs:` directly, restated at every
subsequent link — to keep the protection GitHub used to give it for free.

**Rationale**: this is still spec.md's own edge case ("a stage whose jobs
form a chain through the image check"), but the shipped mechanism is
"restate the guard at every link," not "GitHub's default skip-propagation
already does the right thing" — that default is precisely what a
status-function `if:` anywhere in the chain switches off.

### R-A3: Gate amendments — 22 and 23 change, 15 grows for free

**Decision**:

- **Gate 22** (byte-for-byte `runs-on:`/`container:` passthrough
  uniformity across the 13 stages' `verify-image-prerequisites` job):
  its fixed comparison block gains the new `if:
  inputs.container-image != ''` line, asserted identical (not merely
  present) across all 13 — this is a textual addition to what the gate
  already diffs, not a new check.
- **Gate 23** (asserts every entry/survivor job depends on the check,
  `REQUIRED_TOOLS=` matches `required-tools.txt`, the contract's tool
  table agrees): gains the FR-007 assertion — for every job in every
  published stage whose `needs:` includes `verify-image-prerequisites`,
  its `if:` MUST contain the literal comparison
  `needs.verify-image-prerequisites.result != 'failure'` (R-A1's shape).
  A job with `needs:` naming the check but no `if:` at all, or an `if:`
  that omits this comparison, fails the gate by name (stage + job) —
  this is FR-007's own acceptance test (Scenario 5) made concrete: a
  reverted job is bare `needs:` again, which is exactly what the new
  assertion is built to catch.
- **Gate 15** (a status-function `if:` must explicitly re-check every
  ancestor's `.result`) needs **no code change**. It already walks every
  job whose `if:` contains a status function; R-A1 turns ~40 previously
  bare jobs into exactly that shape, so Gate 15's existing walk covers
  them automatically the moment they exist. Its self-test fixture set
  gains one new case (a rewritten entry job that references the image
  check's result but not a second real dependency's) to prove the
  broadened population is actually exercised, not just structurally
  included.

**Rationale**: FR-006 requires amendment, never a bypass; the specific
split above keeps each gate checking what it already owns (Gate 22:
shape uniformity: Gate 23: existence + reversion) rather than growing a
new gate for a check three gates apart could already express between
them, with Gate 15 doing double duty as the constitution VIII "not
suppressible by an unrelated gate's failure" backstop for the
`!cancelled()` clause specifically.

**Alternatives considered**: a brand-new Gate 73 dedicated purely to
FR-007 — rejected: Gate 23 already walks the exact job population
(every job depending on the check) for a related reason (tool-list
tolerance), so the new assertion is one more field checked per job in
an existing walk, not a second traversal of the same 13 stages' job
graphs.

### R-A4: No composite extraction — 13 inline copies stay 13 inline copies

**Decision**: the `docker login`/`pull`/`run --entrypoint sh` bash block
inside each stage's `verify-image-prerequisites` step is untouched by
this feature beyond the new job-level `if:` line. It is not factored
into a shared composite action.

**Rationale**: out of scope — spec.md's Out of Scope section rules out
"reducing the count of jobs inside `collect`, `diagnose`, `triage` or
`act` on paths that actually do work," and by the same reasoning this
feature targets the job's *allocation*, never its body (spec.md's own
Assumptions: "this feature changes when it is allocated, never whether
it exists"). Extracting a composite here is a legitimate future
CLAUDE.md "shared logic has exactly one home" candidate, but it is a
separate, larger-blast-radius change (13 files' steps, not 13 files'
one new line) than this spec asked for.

## B. The watchdog's clean path

### R-B1: The agent-skip condition moves from `evidence-available` to the signal set itself

**Decision**: `diagnose`'s `if:` changes from
`needs.collect.outputs.evidence-available != 'false'` to additionally
requiring a non-empty signal set:

```
if: |
  needs.collect.outputs.evidence-available != 'false' &&
  needs.collect.outputs.signals != '' &&
  needs.collect.outputs.signals != '[]'
```

The all-failed case (`evidence-available == 'false'`) keeps today's
"could not inspect" path unchanged (FR-013) — this clause is untouched,
only added to.

**Rationale**: FR-019 states the rule directly: key on an empty
aggregate signal set alone, not on "zero signals AND zero failed
collectors." A run with one or more failed collectors, at least one
that reported, and an empty signal set must now skip the agent and post
the *partial* pass (R-B2) instead of running `diagnose` the way it does
today — this is the one behavior change FR-019 introduces beyond what a
naive "signals empty" check alone would already give the all-collectors-
succeeded case.

### R-B2: The passed-inspection record moves into `collect`, beside the aggregate step

**Decision**: a new deterministic step is added to the `collect` job,
immediately after the existing `aggregate` step, gated:

```
if: |
  steps.aggregate.outcome == 'success' &&
  steps.aggregate.outputs.evidence-available != 'false' &&
  (steps.aggregate.outputs.signals == '' || steps.aggregate.outputs.signals == '[]')
```

It posts the lifecycle-issue comment FR-009/FR-010 require, choosing the
full-pass or partial-pass wording (reusing the two existing wording
strings the `diagnose` job's own "Report 'passed inspection'" step
already carries — this feature relocates the strings, it does not
invent new ones) by reading `steps.aggregate.outputs.collectors-failed`:
`0` → full; `> 0` → partial (FR-011). `diagnose`, `triage`, and `act` all
skip via R-B1/existing conditions; the only other job that still runs on
this path is `report-unhandled-failure` (unchanged, FR-017).

**Rationale**: FR-010 requires the record to be "produced beside the
aggregate that decided it" and written by deterministic code, never an
agent — since `diagnose` no longer runs at all on this path, the
posting step cannot live there anymore. Gating on
`steps.aggregate.outcome == 'success'` (not just reading its outputs)
is spec.md's own edge case: "no passed-inspection record may be posted
on the strength of an aggregate that did not complete" — an aggregate
step that itself failed leaves its outputs stale or empty, and reading
them without checking `outcome` first would risk posting a false
"passed" on a broken run. This placement also directly produces FR-018's
"collection job plus at most one guaranteed-report job" — no third job
is added.

The existing "Report 'passed inspection'" step inside `diagnose` is
**not removed** — it still fires on FR-012's path (diagnose ran, found
zero *actionable* Findings after weighing real signals). That is a
different event from this one (diagnose never ran at all because there
was nothing to weigh) and keeps its own wording and code path unchanged,
per FR-012's "same agent invocation, same filing, triage and action
behaviour" as today.

**Alternatives considered**: a new standalone job (e.g. `no-signal-
report`) between `collect` and `report-unhandled-failure` — rejected: it
would itself be a billed job, directly contradicting FR-018's "at most
two jobs total" outcome the whole sub-problem exists to reach; a step
inside the job that already computed the aggregate is the only shape
that adds zero jobs.

### R-B3: FR-031 — no metrics record on the no-finding path, by omission not suppression

**Decision**: nothing new is added to `collect`'s new step to *suppress*
a metrics record — the run-summary call site (R-B2's neighbor,
`wing-commander-metrics-summary`) lives inside the `diagnose` job's
agent step (see contracts/watchdog-clean-path-delta.md), which R-B1
already causes to skip entirely on this path. The metrics record is
absent because the step that would have produced it never ran, not
because a new conditional hides it.

**Rationale**: FR-031's requirement — "the diagnose job held the only
run-summary call site" — is a statement about the existing code, not a
new suppression this plan must build; R-B1 alone already satisfies it.
What this plan must still confirm is that the lifecycle rollup and any
other reader of the records store treat a run with zero records as
ordinary (spec.md's edge case: "nothing downstream may report it as a
record that existed and could not be retrieved") — this is verified,
not built: `wing-commander-metrics-persist`'s existing discovery step
already tolerates "no `metrics-record*` artifact found" as
`persisted-count: 0` rather than an error (spec 043's own contract), and
the rollup already computes its "every agent run appears exactly once"
invariant from the records store's own contents, never from an
independent count of runs — a run that contributed no record was never
counted as one to begin with. No code changes to either composite are
needed for FR-031; sub-problem C's own change (R-C-watchdog-trigger,
below) is what stops a persistence run from being spent looking for a
record that FR-031 guarantees will never exist.

### R-B4: FR-020 — fold the wrapper's `resolve` job into the watchdog stage

**Decision**: `wing-commander-8-watchdog.yml`'s `resolve` job is
removed. `run-name` becomes an optional input on the published
`watchdog.yml` stage (default `''`). When empty, the stage resolves it
itself, inside `collect`'s existing early steps (which already do an
inspected-run lookup for spec-dir/issue resolution), via the same
`gh run view --json workflowName` call the wrapper's `resolve` job made
today. The wrapper's `watchdog` job becomes the workflow's only job: a
bare `uses: ./.github/workflows/watchdog.yml` with `run-id:
${{ format('{0}', inputs.run-id || github.event.workflow_run.id) }}`
and no `run-name:` input supplied at all (letting the stage's own
default/resolution apply) — the same shape
`contracts/wrapper-contract.md` already documents for the
metrics-persist wrapper's own, earlier removal of its `resolve` job
(spec 043), reused here rather than re-derived.

**Rationale**: FR-020 requires exactly this — "the wrapper reduces to a
single `uses:` job that allocates no runner of its own" — because a
`uses:` job that calls a reusable workflow is not itself billed as a
runner-minute; only the called stage's own jobs are. This is additive
(a new optional input with a default that preserves today's behavior
when a caller still supplies `run-name` explicitly) and is a versioned,
non-breaking (minor) change per `contracts/versioning.md`'s existing
rule that new optional inputs are additive.

**Alternatives considered**: keeping `resolve` as a job but skipping it
when `run-name` is already known (e.g. from a `workflow_dispatch` input)
— rejected: `resolve`'s only job on the live `workflow_run` path (the
overwhelming majority of invocations) is producing `run-name`, so a
conditional resolve job still bills a runner exactly on the path this
sub-problem targets; removing the job outright, with the stage doing
the same lookup work it already does for other identity fields, is the
only shape that removes the billed minute.

### R-B5: FR-032 — the self-verifier's floor is re-scaled, not re-derived from data that doesn't exist yet

**Decision**: `verify-watchdog-run.sh`'s duration-floor logic already
computes `floor = max(ABSOLUTE_FLOOR, median(recent successful
durations) * 2/5)` from run history (a dynamic, self-adjusting
component) plus one hardcoded absolute floor constant (`40`, calibrated
assuming every healthy run carried an agent step). This plan lowers only
the absolute constant, to a value derived from this feature's own
components — `collect` (~25s, unchanged by this feature) plus
`report-unhandled-failure` (~8s, unchanged) run sequentially on the
no-finding path, so a conservative new constant sits under that
combined figure with headroom (the exact number is an implementation-
time measurement against real post-merge runs, not a plan-time guess —
research cannot observe a population that doesn't exist yet). The
median-based term needs no code change: it already recomputes itself
from whatever the history window contains, so it naturally drifts down
as new-shape runs accumulate post-merge. The self-verifier's separate,
tighter diagnose-duration ceiling check gains a new branch: `diagnose`
being `skipped` (rather than having run under its ceiling) is added as
a passing case, alongside the passed-inspection comment and the absence
of an execution-output artifact/metrics record (FR-032's full list of
what the new healthy shape looks like).

**Rationale**: FR-032 requires the floor to be "re-derived from the new
healthy population rather than removed" — read literally this cannot
happen inside a planning artifact, since the new population is created
by this feature's own deployment. The plan's obligation is to make the
mechanism capable of re-deriving itself (already true of the median
term) and to fix the one piece that is a static assumption baked in at
a time when the new shape didn't exist (the absolute constant), which a
future run population cannot self-correct on its own. Without lowering
the constant, spec.md's own text is explicit that "the self-verifier
would file a pipeline-defect issue for every healthy inspection — the
cascade #403 closed, reopened from the other side."

**Alternatives considered**: removing the absolute floor entirely,
relying only on the median term — rejected by FR-032's own text
("re-derived... rather than removed"), and because the median term is
undefined/degenerate with fewer than 3 prior successful runs (today's
existing guard), which is exactly the state the very first post-merge
runs are in; the absolute floor is what protects that bootstrap window.

## C. Metrics persistence

### R-C1: The stage gains one additive `since` input; sweep mode is the same pipeline run over many runs instead of one

**Decision**: `metrics-persist.yml` gains an optional `since` input
(ISO-8601 timestamp string, default `''`). When empty (today's only
value), behavior is unchanged: process the single `run-id`. When
non-empty, the stage instead lists every workflow run in the repository
that concluded at or after `since` (paginated `gh api
.../actions/runs`, filtered client-side per the existing Gate 18
per-page-not-whole-result caution this repository already documents),
and runs the existing discover → retrieve → validate →
append-with-retry pipeline once per discovered run-id, batching every
run's records into a single append-with-retry pass (one git commit, not
one per run) so a sweep of N runs costs one push-contention cycle, not
N.

**Rationale**: FR-029 requires the new input to be additive with a
default preserving today's single-run behavior, recorded as a versioned
(minor) decision in the stage's contract — exactly `contracts/
versioning.md`'s existing rule for a new optional input. Reusing the
same discover/retrieve/validate/append pipeline per run (rather than a
parallel sweep-specific code path) is spec.md's own Assumption:
"existing machinery is reused, not re-typed."

### R-C2: High-water mark lives beside the records, updated in the same push

**Decision**: a second small file, `sweep-state.json`, lives on the same
destination branch as `records.jsonl` (default `metrics`), containing
`{"high_water_mark": "<ISO-8601 timestamp of the latest concluded run
the last successful sweep or completion-triggered persist has fully
accounted for>"}`. A sweep run reads it at the start of its append-with-
retry loop (R7 of spec 043) and writes the new value — the maximum
`concluded_at` among the runs it just processed, or left unchanged if it
found none — in the **same** commit as any `records.jsonl` append, so
the mark and the records it accounts for can never observably diverge
under the existing retry-on-contention loop (a rejected push retries
both files together, from a freshly-refetched base, exactly as R7 of
spec 043 already does for `records.jsonl` alone).

A completion-triggered `persist` run (the nine-stage path, unchanged
trigger) does **not** advance `sweep-state.json` — only a sweep run does.
This keeps the two paths from racing over who owns the mark: the
completion path's job is "persist this one run's record if not already
present," or the sweep's overlap window (see R-C3) would double-count.

**Rationale**: FR-027's "resumes from a durable high-water mark rather
than a fixed lookback" is the requirement; storing it beside the
records it describes (not in a separate mechanism, e.g. a repository
variable) keeps the "the persistence composite's idempotence... and the
run-listing capability... reused" assumption true, and keeps the single
retry-safe write path spec 043 already built as this feature's only
concurrency primitive, rather than inventing a second one for a second
piece of durable state.

**Alternatives considered**: a repository variable
(`WING_COMMANDER_METRICS_SWEEP_MARK`) — rejected: repository variables
are not written transactionally alongside a git push, so a crash between
the two writes could silently lose or duplicate coverage across a
restart, exactly the failure mode append-with-retry exists to prevent
for the records file itself.

### R-C3: The sweep re-scans a small overlap window, relying on `record_key` idempotence for safety

**Decision**: a sweep lists runs concluded since `high_water_mark minus
one hour` (a fixed, generous overlap — not configurable), not exactly
`high_water_mark`. Runs already persisted (by the completion trigger or
a prior sweep) are silently no-ops via the existing `record_key` dedup
(spec 043); only runs that reach the sweep with no existing record cost
any real work.

**Rationale**: spec.md's edge case "a run that concludes while a
scheduled sweep is already past the point where it would have seen it"
— GitHub's own run-listing API is filtered on `created`/timestamps that
can momentarily lag a run's true conclusion; an exact boundary read
risks a one-run gap between "the sweep already scanned past this point"
and "the run's conclusion timestamp is now visible to the API." A fixed
backward overlap combined with the existing idempotent append (FR-022,
unchanged) trades a small amount of redundant listing work (cheap: one
more page of `gh api` output) for the guarantee that no run is
"stranded between two" sweeps.

### R-C4: FR-028 — an expired artifact gets a durable, explicit outcome, not a records-file entry

**Decision**: `unpersisted-record-keys` (an existing composite output,
today ephemeral — visible only in that run's own step summary) gains a
durable form for the sweep path only: a run whose artifacts have
expired (the retrieve step's existing 404/expired-artifact case) is
appended, in the same commit as R-C2's push, to a third small file,
`unpersisted.jsonl`, on the same destination branch — one line per such
run, `{"run_id", "workflow", "reason": "artifact_expired",
"discovered_at"}`. The sweep still advances the high-water mark past
that run (it is accounted for, just not persisted) so it is not
rediscovered and re-logged on every subsequent sweep.

**Rationale**: FR-028 requires "recorded with an explicit outcome rather
than silently dropped, and the run is not retried forever" — a
durable ledger entry satisfies "explicit" (a maintainer or a future gate
can read it), and advancing the mark past it satisfies "not retried
forever." Keeping it out of `records.jsonl` itself avoids polluting the
rollup's cost/token sums with a line that carries no actual metrics
(it would need every `*_available` flag false, which is a legitimate
shape for a *readable-but-malformed* record, not for "we never got to
read it at all" — a different failure class the schema doesn't need to
grow a case for).

### R-C5: Watchdog leaves the completion trigger; the sweep is its only path

**Decision**: `wing-commander-metrics-persist.yml`'s `workflow_run:
workflows:` list drops `"Wing Commander · 8 watchdog"`. A signal-bearing
watchdog inspection (the only shape that still emits a record, per
FR-031/R-B3) is now reached only by the next scheduled sweep.

**Rationale**: FR-030(b) states this directly. After FR-031, every
*other* watchdog completion emits no record, so a completion-triggered
persist run against it billed a job to discover nothing — precisely
sub-problem C's target. FR-023's "within minutes" latency guarantee is
scoped to the nine stages that keep the completion trigger; a
signal-bearing watchdog inspection's record instead lands "within one
sweep interval" (FR-023's second clause, SC-011's matching split).

### R-C6: Sweep cadence — daily, offset from existing scheduled workflows

**Decision**: `schedule: cron: "37 6 * * *"` (arbitrary minute/hour,
chosen only to avoid colliding with the existing `lint-workflows.yml`
(`43 5`), `wing-commander-rebase.yml` (`17 4`), `wing-commander-7-
cleanup.yml` (`53 6`), and `wing-commander-auto-update-spec-kit.yml`
(`13 7`) crons), added to `wing-commander-metrics-persist.yml` alongside
its existing `workflow_run`/`workflow_dispatch` triggers. The existing
`workflow_dispatch` `run-id` input is unchanged (single-run re-drive,
FR-024); the sweep is reached only by `schedule:` or by a maintainer
passing the new `since` input explicitly via `workflow_dispatch` — the
same dispatch entry point gains one more optional input rather than a
second `workflow_dispatch` block, matching how every other scheduled
wrapper in this repository (`auto-release.yml`, `wing-commander-7-
cleanup.yml`) pairs `schedule:` with the same `workflow_dispatch:` it
already had.

**Rationale**: FR-030(c) requires "a daily scheduled sweep"; this
repository already has four precedents for pairing a `schedule:` trigger
with `workflow_dispatch:` on one wrapper, none of which needed a second
dispatch surface — reusing that shape is spec.md's own "the scheduled
wrappers as the precedent for the daily sweep's trigger" Assumption made
concrete.

### R-C7: No concurrency-based coalescing (FR-030(d), explicit non-decision)

**Decision**: no `concurrency:` group is added to gate overlapping
persistence runs against each other. A completion-triggered run and a
sweep run (or two sweep runs, if a manual dispatch races the schedule)
may execute concurrently; safety is entirely `record_key` idempotence
(existing) plus R-C2's same-commit high-water-mark write (retried on
contention exactly like a records append already is).

**Rationale**: FR-030(d) states this is a deliberate composition
choice, not an oversight — a `concurrency:` group's pending-slot
replacement would cancel a queued run rather than let it complete, which
at this pipeline's rhythm (a handful of completions per hour, one sweep
per day) would fire rarely enough to save no real minutes while adding
a second contract change (the group's name/scope) for no measured
benefit.

## Decisions made without an explicit spec answer

None of these contradict spec.md; each fills a mechanical gap the spec
left to plan-level judgment, listed here for the lifecycle issue
comment:

- The exact `if:` comparison operator for R-A1 (`!= 'failure'` over the
  two-clause `== 'success' || == 'skipped'` form) — spec.md requires
  tolerance, not a specific expression.
- Where the FR-007 reversion check lives (an amendment to Gate 23,
  rather than a new gate number) — spec.md requires the check to exist,
  not which existing gate script hosts it.
- The passed-inspection step's exact placement (a new step inside
  `collect`, immediately after `aggregate`) — spec.md requires
  "produced beside the aggregate," which this plan reads as literally
  adjacent in the same job.
- The self-verifier's new absolute floor constant is left as an
  implementation-time measurement against real post-merge run
  durations, not a number fixed in this plan (R-B5) — spec.md requires
  re-derivation, which by definition cannot be computed against data
  that does not exist until after this feature ships.
- The high-water mark's storage shape (`sweep-state.json` beside
  `records.jsonl`, one shared commit) and the one-hour re-scan overlap
  window (R-C3) — spec.md requires "durable" and "never stranded," not
  a file name or a window size.
- The expired-artifact ledger (`unpersisted.jsonl`, R-C4) as a new file
  rather than an extension of the record schema — spec.md requires an
  explicit, non-retried outcome, not a specific storage shape.
- The sweep's cron time (`37 6 * * *`) — spec.md requires "daily," not a
  specific minute/hour.
- Gate numbers throughout are left unassigned, following spec 043's own
  precedent (research.md R12 there): sequential numbering is this
  repository's convention, decided at implementation time so concurrent
  in-flight specs cannot collide over the same number.
