# Phase 0 Research: Plan and Tasks Stages Record Their Own Branch Advance

spec.md carries no literal `[NEEDS CLARIFICATION]` marker — issue #511's
own subject (FR-020 of specs/050-branch-drift-sha-baseline) already names
the gap and the mechanism it must reuse. What remains for planning is
translating FR-001–FR-023 into concrete edits against the files spec.md
names: `.github/workflows/plan.yml`, `.github/workflows/tasks.yml`,
`.github/workflows/implement.yml`, `.github/workflows/watchdog.yml`,
their composite actions, and the gates spec 050 already shipped. Each
decision below is a planning judgment, not something spec.md dictates
directly, unless noted otherwise — flagged for the issue comment.

## R1 — A new composite, `wing-commander-branch-advance`, owns the "after" + "commits" computation; "before" stays each caller's own concern

**Decision**: Extract the git plumbing inside `implement.yml`'s existing
"Record branch advance (cycle)" step (`implement.yml:2396-2432`) — the
`git fetch origin "+refs/heads/$branch:refs/remotes/origin/$branch"` /
`git rev-parse` / `git rev-list --count "$before..$after"` sequence —
into a new composite action, `.github/actions/wing-commander-branch-
advance/action.yml`. Inputs: `branch` (string), `before-sha` (string,
may be empty), `before-sha-available` (`'true'`/`'false'`). Outputs:
`after-sha`, `after-sha-available`, `commits`, `commits-available` —
named identically to the `wing-commander-metrics-summary` inputs they
feed, so a call site pipes them straight through with no renaming.

`implement.yml`'s own step becomes a single `uses:` call passing
`branch: ${{ inputs.spec-prefix }}${{ steps.spec.outputs.slug }}` and
`before-sha`/`before-sha-available` computed exactly as today from
`steps.base.outputs.base-sha` (research.md R1 of specs/050 — reused
unchanged here too). `plan.yml` and `tasks.yml` each gain the same kind
of call site, with their own "before" (R2 below) and their own `branch`
(the persistent spec branch in `auto` mode, the review branch in `pr`
mode — FR-004).

**Rationale**: FR-011 requires "exactly one home shared by implement,
plan and tasks, rather than a second and third copy of the implement
stage's block." "Before" cannot be folded into the same composite,
because each stage's "before" already comes from a different existing
source (implement: an existing, unrelated step's output; plan/tasks: a
new capture this feature adds, R2) — forcing it through one composite
input is exactly what R1 of specs/050 already decided against for
implement's own case ("the single home for... is this existing step's
output, read a second time... rather than recomputed"). The "after" +
"commits" math, by contrast, is byte-identical git plumbing regardless
of which stage or review mode calls it — one `git fetch`/`rev-parse` of
whatever branch name the caller passes, one `rev-list --count` of
whatever before/after pair it holds. Keeping record emission
(`wing-commander-metrics-summary`) a separate call, as today, preserves
that composite's own single responsibility (specs/050 R2's rationale)
rather than growing it a second, unrelated job.

**Composite publication status**: Like `wing-commander-metrics-summary`,
this composite is an internal implementation detail three published
stage workflows resolve through self-checkout — not itself enumerated by
`stage-interfaces.md`'s `workflow_call` surface (specs/050's own
Constitution Check VII reasoning applies verbatim). It is a non-
underscore-prefixed name (`wing-commander-branch-advance`, not
`_shared/branch-advance`) because, per constitution VII's underscore
clause, `_shared/` is reserved for internal helpers with no direct
stage-workflow consumer of their own; here all three consumers ARE
published stage workflows resolving it directly, the same shape as
`wing-commander-metrics-summary` and `wing-commander-spec-meta`.

## R2 — Plan/tasks "before": one new step, right after the existing spec-branch checkout, shared by both review modes

**Decision**: Add one new step, "Record branch tip before agent," in
both `plan.yml` and `tasks.yml`, immediately after "Checkout spec branch
as wing-commander-bot" (`plan.yml:666-673`; the analogous step in
`tasks.yml`) and before either mode-specific agent step. It runs
whenever the job has not already stopped (`dupe`/`guard` skip checks,
matching the surrounding steps' own conditions) and does two things:

1. `branch = mode == 'auto' ? "${SPEC_PREFIX}${SLUG}" : "${PLAN_PREFIX}${SLUG}"`
   (or `TASKS_PREFIX` in `tasks.yml`) — computed from `steps.mode.outputs.mode`,
   which this point in the job already has (`Resolve review mode` runs
   before the checkout in both files).
2. `before-sha = git rev-parse HEAD` (the tip of the just-checked-out
   spec branch), `before-sha-available = true` unless the rev-parse
   fails.

**Rationale — one capture point serves both modes and both branch-
creation cases (FR-005)**: The checkout at this point is always
`${SPEC_PREFIX}${SLUG}` — identical regardless of which mode the run
resolved to (mode is decided, and the checkout ref is fixed, before
either agent step runs). In `auto` mode the agent commits directly to
this same checked-out branch, so `HEAD` at this point IS the branch's
tip before the run's work — the ordinary case. In `pr` mode the agent's
own first act is `git checkout -b ${PLAN_PREFIX}${SLUG}` (or
`TASKS_PREFIX`) from this same `HEAD` (`plan.yml:928`,
`tasks.yml`'s analogous prompt step) — so the same `git rev-parse HEAD`
read, at the same point, is exactly "the commit the review branch was
created from," satisfying FR-005 ("before" is "the point the run
advanced the branch from") with no special-casing for the create-vs-
reuse distinction. This is the same reasoning specs/050 R1 already
established for implement's "before" (a value the stage already
computes for an unrelated reason, reused rather than duplicated) — here
applied one step earlier, before agent dispatch rather than before cycle
dispatch, because plan/tasks have no analogous existing capture to reuse
(unlike implement's `steps.base.outputs.base-sha`).

**Availability**: `plan.yml`'s own precondition ("Ensure persistent spec
branch," `plan.yml:568-578`) already guarantees `${SPEC_PREFIX}${SLUG}`
exists by the time this checkout runs — creating it from the default
branch if this is the first plan attempt for the spec. `tasks.yml`
requires `plan.md` on the spec branch before it starts (`tasks.yml:604`),
so the spec branch already exists there unconditionally. `before-sha` is
therefore always resolvable in practice for both stages; the step still
degrades to `before-sha-available: false` defensively on a `rev-parse`
failure rather than assuming success, matching the stage-neutral,
best-effort convention FR-008 requires.

## R3 — Plan/tasks "after": one capture point per file, after both mode branches converge, before the agent-verdict gate can exit the job

**Decision**: Add one new step, "Record branch advance (after agent),"
in both `plan.yml` and `tasks.yml`, placed after the mode-specific
post-agent steps ("Re-establish Wing Commander context," "Refresh
authenticated spec-branch remote" — the last steps both `auto` and `pr`
paths run before they reconverge) and before "Compute agent run verdict"
/ "Fail loud on non-healthy agent verdict." Condition:
`!cancelled() && (steps.agent-auto.outcome != 'skipped' ||
steps.agent-pr.outcome != 'skipped')` — the same condition the existing
unconditional "Agent run metrics summary" step already uses
(`plan.yml:1073-1076`, `tasks.yml`'s analogous step) — with
`continue-on-error: true`. It calls `wing-commander-branch-advance`
(R1) with the `branch`/`before-sha`/`before-sha-available` values R2's
step produced, then a transcript-less `wing-commander-metrics-summary`
call (mirroring implement's fourth call site, specs/050 R2) with
`stage: plan` (or `tasks`), and an "Upload metrics record (branch
advance)" step, `continue-on-error: true`, `if-no-files-found: ignore`.

**Rationale — placement before the verdict gate, not after**: `plan.yml`
and `tasks.yml` each have a step ("Fail loud on non-healthy agent
verdict (auto/pr)") that `exit 1`s the job outright on an unhealthy
verdict, with no `always()`/`continue-on-error` protecting the steps
after it — so a step placed after it never runs for exactly the runs
this feature most needs to measure (a truncated, rejected-push, or
otherwise unhealthy cycle). Placing the capture before that gate,
gated only on "an agent step actually attempted to run" (mirroring the
existing metrics-summary step's own condition, not the verdict), is
required for FR-001 to hold for a run that pushed nothing because it
never got the chance to finish healthily — precisely User Story 1's
scenario. This mirrors implement.yml's own placement rule (specs/050
R2: the capture must run regardless of the cycle's own verdict).

**Rationale — one call site per file rather than one per mode**: Unlike
`implement.yml` (whose cycle job has no mode branching), `plan.yml` and
`tasks.yml` already converge their two mode-specific paths into a single
downstream metrics-summary call today (`plan.yml:1071-1088`,
`tasks.yml:1052-1069`) using exactly this `steps.agent-auto.outcome !=
'skipped' || steps.agent-pr.outcome != 'skipped'` disjunction, because
the two agent steps are mutually exclusive per run. The new branch-
advance capture follows the same established convention rather than
duplicating itself once per mode — a second within-file duplication
FR-011's "exactly one home" reasoning would flag just as readily as a
second cross-file one.

**Rationale — no bookkeeping push to wait for, unlike implement**: FR-006
requires "after" observe every push the run could make "including any
deterministic bookkeeping push that follows the agent's own." Neither
`plan.yml` nor `tasks.yml` has a deterministic step that pushes commits
after the agent step (unlike implement's "Record truncated-cycle count"
bookkeeping push) — the only steps between the agent step and this
capture are read-only (`gh`/`git fetch` verification, label edits). The
capture point chosen already sits after everything that could push, so
FR-006 is satisfied without needing to hunt for a later insertion point
the way specs/050 R2 had to for implement.

## R4 — The rejected-push, not-yet-created-branch, and multiple-push edge cases need no special code in either new step

**Decision**: No branch of either new step explicitly detects "was the
push rejected," "did the agent push more than once," or "did the branch
not exist before this run" (`pr`-mode's first attempt). Each falls out
of the same fetch-then-compare mechanics specs/050 R4/R5 already
established for implement:

- **Rejected push**: `origin/<branch>` never advances past what R2's
  step observed, so R3's fresh fetch returns the same tip —
  `after_sha == before_sha`, `commits: 0`, both `available: true`. Not a
  degraded state; the correctly-measured "zero progress" shape US1
  requires.
- **Multiple pushes** (a `pr`-mode agent that pushes, then amends and
  force-pushes again before finishing): R3's fetch runs once, after the
  agent step has fully completed — it observes whatever the branch's
  tip is at that moment, which is by construction the last of however
  many pushes happened, with no dependency on how many there were.
- **Branch did not exist before this run** (`pr` mode's first attempt for
  a spec, or an `auto`-mode plan run that itself created the spec
  branch in "Ensure persistent spec branch"): R2 already resolves
  "before" to the point the branch was created from in this case (its
  own rationale). If the `pr`-mode agent then never runs the `git
  checkout -b` at all (crashes immediately), R3's fetch of
  `${PLAN_PREFIX}${SLUG}` fails outright (no such ref) —
  `after-sha-available: false`, distinct from the rejected-push case
  (which resolves `after` successfully, to the unchanged tip) — exactly
  the distinction FR-016/SC-002 need between "measured, zero progress"
  and "not measurable at all."

**Rationale**: This is the same "no special-casing needed" result
specs/050 R4/R5 reached for implement, carried over because the
underlying git mechanics (fetch, rev-parse, rev-list) are unchanged by
this feature — only the caller and the branch name differ.

## R5 — Watchdog collector: the exact-sha lookup moves outside the implement-only guard; the since-created fallback stays implement-only

**Decision**: In `watchdog.yml`'s `collect-branch-drift` step, the block
that downloads the inspected run's `metrics-record*` artifact set and
scans for `branch_advance.available == true` (currently gated inside
`if [ "$RUN_NAME" != "Wing Commander · 5 implement" ] || [ -z
"$RUN_CREATED_AT" ]; then ... fi`, `watchdog.yml:772-827`) moves to run
for plan, tasks, and implement alike — the outer `case "$RUN_NAME"`
gate at the top of the step (`watchdog.yml:684-690`) already restricts
the whole step to exactly those three stages, so no new stage becomes
reachable. When a record with `branch_advance.available == true` and
both points present is found, `baseline="exact-sha"` fires exactly as
today, with one change: `measure_branch` is *always* taken from the
record's own `branch_advance.branch` field (never a `${_spec_prefix}
${SLUG}`-derived guess) — FR-004 forbids deriving the branch from a
prefix or a mode, and for a `pr`-mode plan/tasks run the prefix-derived
guess would be wrong anyway (it would name the spec branch, not the
review branch the run actually advanced). Today's implement-only code
already prefers the record's own `branch_advance.branch` when present
(`watchdog.yml:820-823`) — this decision makes that the unconditional
rule for the exact-sha arm rather than an implement-specific override,
which is a behavior-preserving generalization for implement (its
records already carry the same value the prefix guess would produce)
and the only correct rule for plan/tasks.

When no such record is found, the two stages diverge, unchanged from
today in each case:

- **Implement**: falls through to `baseline="since-created"` exactly as
  today, measuring `${_spec_prefix}${SLUG}` since `$RUN_CREATED_AT`
  (FR-018 — this fallback is Out of Scope to touch).
- **Plan/tasks**: there is no analogous fallback to fall through to —
  today's behavior for a plan/tasks run is an unconditional skip with no
  signal, and FR-016/FR-017/FR-018 require that exact outcome to survive
  unchanged for a run whose record carries no usable pair. The step
  summary states "no recorded branch-advance evidence on this
  <plan|tasks> run — skipping" rather than attempting a measurement this
  feature does not define for these two stages.

**Rationale — why plan/tasks get no since-created fallback**: The
since-created window's own baseline branch (`${_spec_prefix}${SLUG}`) is
only correct for a run that actually pushes to the spec branch — true
for implement unconditionally, but only true for plan/tasks in `auto`
mode (FR-004). Guessing it for a `pr`-mode run would silently measure
the wrong branch — the persistent spec branch, which a `pr`-mode plan/
tasks run never touches — and could produce a *false* lost-progress
signal on a perfectly healthy `pr`-mode run whose review branch nobody
merged yet. FR-016 ("MUST NOT produce a false lost-progress signal") and
Out of Scope ("changing the timestamp-window baseline that survives for
implement runs... predate spec 050") both point the same direction: the
missing-evidence case for plan/tasks stays exactly what it is today —
no signal — rather than gaining a new, mode-blind approximation this
spec never asked for.

**This is a planning-judgment call** (spec.md does not spell out the
missing-evidence behavior for plan/tasks beyond "keep exactly today's
outcome," which this decision satisfies by construction): flag it in
the issue comment.

## R6 — Signal emission for plan/tasks reuses the exact-sha arm's existing shape unchanged

**Decision**: No change to the signal-emission block
(`watchdog.yml:928-938`). A plan or tasks run whose exact-sha arm fires
emits exactly the same `facts: {branch, "before-sha", since: null,
"after-sha", commits}` shape implement's exact-sha arm already produces
(specs/050 data-model.md) — `branch` is now `plan/<slug>` or
`spec/<slug>` rather than always `spec/<slug>`, and the stage name in
the surrounding log line differs, but the fact shape and the
already-handled/stalled short-circuit (`META_STAGE`/`STALLED_LABEL`,
unchanged) are identical for all three stages. FR-014 and FR-019 are
satisfied by the existing code with zero additional lines.

## R7 — Comment replacement at `watchdog.yml` (FR-023)

**Decision**: The two comment blocks that currently state plan/tasks
runs are skipped because their head branch is never the branch they
push to (`watchdog.yml:696-699` and the "Plan and tasks push to
spec/<slug> only in auto review mode... so with a non-spec head they
still skip" sentence inside `watchdog.yml:719-731`, both quoted in
spec.md's Overview) are replaced with a comment stating: (a) why a
`pull_request`/`workflow_dispatch`-triggered plan/tasks run's head
branch is still never the branch it advances (the part of the reasoning
that is unchanged — a draft or default-branch head is not evidence of
what the run pushed), and (b) that a plan or tasks run's own metrics
record now carries the exact branch/before/after/commits quadruple it
observed (this feature), read the same way implement's already is,
closing the total gap the two replaced comments used to document as
permanent. CLAUDE.md's "workflow comments are load-bearing" rule
applies — this is a behavior-describing edit, reviewed as such.

## R8 — Gate 39 (`verify-metrics-record-schema.py`): no code change, three new fixtures

**Decision**: The schema, the composite's `emit_record()`, and Gate 39's
`REQUIRED_BRANCH_ADVANCE`/contract cross-check are all already stage-
neutral (specs/050 shipped them that way on purpose — FR-020 of that
spec). Populating the group from a second and third call site changes
no shape and needs no code change to the gate itself. FR-020 of *this*
spec still requires fixture coverage naming the two scenarios this
feature specifically introduces, even though they are not new JSON
*shapes*:

- A record whose `before_sha`/`before_available: true` is the commit a
  branch was *created* from (R2/R4) — schema-identical to the existing
  `valid-branch-advance-both-present-different.json` fixture, added as
  its own file so FR-020's "a run that created the branch it advanced"
  case is traceable to a fixture by name, not merely subsumed silently.
- Two fixtures whose only difference is the literal value of `branch` —
  one naming a persistent spec branch (`spec/<slug>`), one naming a
  review branch (`plan/<slug>`) — so FR-020's "the fixtures MUST include
  a record naming a persistent spec branch and one naming a review
  branch" is satisfied by name, not only by the pre-existing fixtures'
  incidental `spec/050-...` values.

The eight existing branch-advance fixtures (both-present-different,
both-present-equal, before-unavailable, after-unavailable,
backwards-reset, commits-unavailable, both-unavailable, plus the seven
wrong-typed negatives) already cover the remaining scenarios FR-020
lists verbatim — reused unchanged.

## R9 — Gate 53 (`verify-branch-drift-sha-baseline.py`): extended with plan/tasks cases on both arms

**Decision**: Add four new scenario functions to the existing harness,
reusing its established `GH_STUB`/local-git-repository fixture
machinery (no new harness infrastructure):

1. A plan run (`RUN_NAME = "Wing Commander · 3 plan"`) with a downloaded
   record carrying `branch_advance.available: true`,
   `branch: "plan/068-..."`, `before_sha == after_sha` → the same
   lost-progress signal shape as implement's own case 1, naming the
   `plan/` branch.
2. A tasks run, same shape, `before_sha != after_sha` → no signal
   (mirrors implement's case 2).
3. A plan run whose downloaded artifact set carries no record with
   `branch_advance.available: true` → **no signal, and no
   since-created fallback attempted** — the collector's step summary
   names "no recorded branch-advance evidence... skipping," not a
   fallback baseline (this is the behavioral assertion that
   distinguishes plan/tasks from implement's own no-record case, and is
   the one genuinely new code path this gate must prove, per R5).
4. The same as 3, for a tasks run.

Case 5 in specs/050's own gate ("a spec-branch-head run and a
non-push-expected stage are unaffected") already exercises plan/tasks
in the *head-sha* arm and is unaffected by this change; it stays as a
regression check. No new fixture files are required beyond synthetic
run-metadata JSON already inline in the harness's Python (matching its
existing style) — the branch-advance *records* these scenarios download
are the same synthetic JSON shape specs/050's own cases 1/2 already
build, with `stage`/`branch_advance.branch` values changed.

## R10 — Gate 60 (`verify-single-home-idioms.py`): one new check, `branch-advance-capture`

**Decision**: Add a tenth idiom check to Gate 60, keyed on the
co-occurrence, in one file, of the two fragments that (after R1's
extraction) exist only inside the new composite:
`git fetch origin "+refs/heads/$` (the refspec-form fetch, distinctive
because no other idiom in the fleet fetches by explicit refspec into a
named remote-tracking ref) and `git rev-list --count "$` immediately
followed by a `..` range (the commit-count read). `DECLARED_HOMES
["branch-advance-capture"] = ".github/actions/wing-commander-branch-
advance/action.yml"`. This is the CLAUDE.md-mandated step: "When you
consolidate something like this, add the 'single home' check to the
nearest existing gate the same way" — Gate 60 is that nearest existing
gate (its own module docstring already frames itself as exactly this
kind of registry, and its `DECLARED_HOMES` mechanism, waiver file, and
promotion-prevention pass need no structural change to accept an
eleventh... [tenth] entry).

**Rationale for the fragment choice**: `all_subject_files()` already
scans every workflow and composite; picking a fragment pair unique to
this idiom (verified by grepping the pre-refactor tree: the refspec-form
fetch and the `..`-range `rev-list --count` appear together only in
`implement.yml`'s current "Record branch advance (cycle)" step) avoids
the false-positive risk Gate 60's own `check_failure_issue` comment
warns about for a single common fragment used alone elsewhere (plain
`git fetch origin` and plain `git rev-list --count` each appear
unrelatedly elsewhere in the fleet; the refspec/`..`-range spellings,
together, do not).

## R11 — Contract updates

**Decision**: `specs/050-branch-drift-sha-baseline/contracts/metrics-
record-schema-delta.md` and `.../branch-drift-collector-delta.md`
already describe the *shape* this feature reuses unchanged; this
feature's own contract deltas (see `contracts/`) describe only what
changes: which stages populate the group (three, not one), how the
"before" point generalizes for plan/tasks (R2/R4), and the collector's
widened exact-sha arm (R5). The base contract this feature amends is
`specs/043-durable-metrics-record/contracts/metrics-record-schema.md`
(already carrying spec 050's `branch_advance` clause) — FR-010 requires
it be updated in place to state that implement, plan, and tasks all
populate the group now, which this feature's delta document expresses
as a further amendment to the same clause, not a new one.

## R12 — No agent turn or model change anywhere (FR-007, SC-007)

**Decision**: Every new value in this feature — `branch`, `before-sha`,
`after-sha`, `commits`, and their `*-available` flags — is produced by
a deterministic step (`git rev-parse`, `git fetch`, `git rev-list
--count`) reading state the stage's own checkout already holds, or an
env-var computed from an already-resolved `steps.mode.outputs.mode`
output. No prompt in `plan.yml`'s or `tasks.yml`'s agent step changes;
neither gains a new Bash allowance, since the new steps are entirely
outside the agent's own tool surface (they run before/after it, as
plain `run:`/`uses:` steps the agent never invokes).
