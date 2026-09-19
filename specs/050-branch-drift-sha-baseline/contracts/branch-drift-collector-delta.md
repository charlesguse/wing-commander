# Contract Delta: Watchdog Branch-Drift Collector (`watchdog.yml`, `collect-branch-drift`)

This is a delta against the shipped behavior and comments of
`watchdog.yml`'s `collect-branch-drift` step (~lines 628-805 at plan
time), which has no prior published contract document of its own — its
current behavior is the base, established across issues #112/#318/#322
and read directly from the shipped step. Only the dispatched-implement
arm changes; the push-expected-stages gate (lines ~655-661), the
spec-branch-head arm (`baseline="head-sha"`), and the already-handled/
stalled short-circuit are unchanged.

## Baseline selection for a dispatched implement run

**Current contract**: A run whose head branch is not the branch the
stage pushes to (the dispatched-implement case, resolved via
`wing-commander-inspected-run-identity`'s slug) always measures with
`baseline="since-created"`: `git rev-list --count --since=<RUN_CREATED_AT>
after_sha`, an open-ended window with no lower SHA bound. Two miss cases
are documented as permanent in the step's own comments (quoted in
spec.md's Input): a `rebase.yml` force-push between the run finishing
and the watchdog inspecting it inflates the count (committer dates
rewritten), and a later run on the same branch that has already pushed
by inspection time adds its own commits inside the open-ended window.
Both err toward a missed detection, never a false one.

**Amended contract**: The step first attempts to resolve
`baseline="exact-sha"` by downloading the inspected run's
`metrics-record*` artifact (the same `gh run download ... -p
'metrics-record*'` pattern `wing-commander-inspected-run-identity`'s
`record_fallback` already performs) and locating a record with
`branch_advance.available == true`. When found:

- `before_sha` / `after_sha` are read directly from the record's
  `branch_advance.before_sha` / `.after_sha`.
- The verdict is `before_sha == after_sha` (lost-progress when equal) —
  no `git fetch`/`rev-list` against the branch's current state is
  needed for the verdict itself.
- `commits` in the emitted signal is `branch_advance.commits`, read
  verbatim — the collector performs no walk of the recorded range
  (FR-019 of specs/050), so a force-push that later orphans the
  recorded commits cannot break this reading.

When no record with `branch_advance.available == true` is found (an
older pipeline version, an expired 90-day artifact retention window, a
cycle whose push step never reached the recording point — spec.md's
User Story 3), the step falls back to exactly today's
`baseline="since-created"` mechanism, unchanged in every particular.
The step summary explicitly names which of the two baselines this run
used (FR-013).

This closes both previously-permanent miss cases for any run whose
record carries the new evidence: the comparison depends only on the two
SHAs the stage itself recorded, at the moment it held them, which is
invariant to anything the branch looks like at inspection time —
neither an intervening force-push nor an intervening later run's push
can change the verdict (SC-003 of specs/050). Both miss cases survive,
exactly as documented today, only for a run whose record lacks the new
evidence (FR-018).

## Signal emission

**Current contract**: `facts: {branch, "before-sha": null,
since:"<RUN_CREATED_AT>", "after-sha", commits: 0}` for the
since-created arm (the fixed `commits: 0` reflects that this arm only
ever fires on a zero count — see data-model.md's note).

**Amended contract**: The `exact-sha` arm emits `facts: {branch,
"before-sha", since: null, "after-sha", commits: <recorded commits>}`.
The since-created arm's shape is unchanged. The already-handled/stalled
short-circuit (`META_STAGE == "stalled" || STALLED_LABEL == "true"` →
`alreadyHandledBy` instead of `class-hint: "lost-progress"`) applies
identically to both arms, unchanged from today (FR-014).

## No change to identity resolution, non-dispatched-implement runs, or dedup

`wing-commander-inspected-run-identity`'s own slug-resolution logic is
unchanged — this delta only adds a *second*, independent artifact
download for the branch-pair evidence, reusing the same download
pattern rather than the same composite output. The spec-branch-head arm,
the push-expected-stages gate, and every non-dispatched-implement code
path (a skipped/cancelled run, a non-push-expected stage) are unchanged
(FR-012). The fingerprint/dedup mechanism downstream of this collector
is unaffected (research.md R11; Out of Scope).

## Replaced comments (FR-015)

The comment block documenting the two miss cases as permanent (quoted
above, and in spec.md's Input) is replaced with a comment stating: why
`HEAD_SHA..spec/<slug>` still cannot be used directly for a dispatched
run (the part of the reasoning that is unchanged), that the exact-SHA
arm now closes both previously-permanent misses for a record carrying
`branch_advance`, and that the since-created arm survives only as the
named fallback for a record that lacks it.
