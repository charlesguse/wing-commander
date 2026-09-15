# Phase 0 Research: Exact-SHA Branch-Drift Baseline

spec.md carries no literal `[NEEDS CLARIFICATION]` markers — the issue's
own proposed change (#331's body) already resolves the design trade-off
the issue flags as needing owner decision (the `spec-request` routing
itself was that decision). What remains for planning is translating
FR-001–FR-020 into concrete edits against the files spec.md names:
`.github/actions/wing-commander-metrics-summary`, `.github/workflows/
implement.yml`, `.github/workflows/watchdog.yml`, and their published
contract and gates. Each decision below cites the exact current
structure it changes; where a decision resolves a genuine ambiguity
spec.md leaves to planning judgment (not a `[NEEDS CLARIFICATION]`
marker), it is called out as such so the issue comment can list it.

## R1 — "Before" reuses `implement.yml`'s existing `Record base SHA` step; no new capture point

**Decision**: The cycle's "before" point is `steps.base.outputs.base-sha`
(`implement.yml:647-650`, `git rev-parse HEAD` immediately after the spec
branch is checked out). No new step captures it.

**Rationale**: This value already exists, is already computed at exactly
the right moment (cycle start, before the agent runs), and is already
used for an unrelated purpose (`Read back cycle outcome`'s convergence
range). Duplicating the capture would create the exact "pasted logic"
CLAUDE.md's "shared logic has exactly one home" rule warns against — the
single home for "the spec branch's tip at cycle start" is this existing
step's output, read a second time by the new step (R2) rather than
recomputed.

**Availability**: `implement.yml`'s own precondition ("Verify spec
artifacts match the dispatch", ~528-544) already requires `tasks.md` to
exist on the spec branch before a cycle can start, which means the spec
branch itself already exists by the time "Record base SHA" runs — the
"branch did not exist at cycle start" edge case (FR-004) cannot currently
be reached from `implement.yml`'s own cycle. The new step (R2) still
treats an empty/failed `base-sha` defensively as `before_available:false`
rather than assuming it is always populated, because FR-020 makes the
field stage-neutral: a future `plan`-stage populator's first cycle
*does* create the branch from `main`, and the schema/gate contract must
support that state now even though no current call site exercises it
live (Gate 39's fixtures cover it synthetically — FR-008).

## R2 — A new, fourth, transcript-less metrics-summary call site captures "after"; the three existing call sites are not reused

**Decision**: Add one new step, "Record branch advance (cycle)"
(step-index `3`), between "Record truncated-cycle count" (~1900-1958) and
"Flip stage label (first cycle)" (~1962) in `implement.yml`'s `cycle`
job. It computes `after_sha` by re-reading `origin/<branch>` at that
point and calls `wing-commander-metrics-summary` a fourth time with an
intentionally nonexistent `transcript-path`. The three existing call
sites (`cycle`=0 at 894, `retry`=1 at 1330, `progress comment`=2 at 1835)
are unchanged.

**Rationale — why not add the fields to the existing `cycle` record
(step-index 0)**: That was the first design considered, since it is the
"natural" record for "the pushing cycle" the spec's Edge Cases section
describes. It does not work, because of a genuine ordering constraint,
confirmed by tracing the full step list: `Agent run metrics summary
(cycle)` (894) must run *before* the retry agent step (1157) — the retry
step, sharing the same transcript temp path, overwrites the file this
step must still read, so the comment on the step already states "read
here, before any retry step overwrites the shared transcript path."
That same constraint pins `Agent run metrics summary (retry)` (1330)
before the progress-comment agent step (1691), and `Agent run metrics
summary (progress comment)` (1835) has no such pin but is still, by
plain file order, before "Record truncated-cycle count" (1900) — the
step that can add a *second* push on top of whatever the agent(s)
pushed (verified: it fires whenever `steps.final.outputs.truncated`
flips, independent of this cycle's own verdict, e.g. resetting a prior
truncation streak). Since "Record truncated-cycle count" additionally
depends on `steps.final.outputs.truncated`/`.tier` — set by "Consolidate
final outcome" (1532), itself downstream of the retry's own outcome read
— it cannot be moved earlier than 1532 either. No existing call site can
therefore observe the branch's state *after every push the cycle can
make* without either breaking the transcript-overwrite protection three
comments already document, or silently under-counting the bookkeeping
push the Edge Cases section explicitly requires counting ("the stage
pushes more than once in a cycle... the recorded after point must be the
tip the cycle finished with").

**Rationale — why a fourth call site rather than a bespoke step**:
Reusing `wing-commander-metrics-summary` keeps "one home" for record
emission (`record_key` composition, the JSON writer, the artifact-upload
naming convention) rather than hand-rolling a second writer that has to
independently match the same schema. Pointing `transcript-path` at a
path that does not exist deliberately drives the action's own existing
"missing transcript" degraded-record path (already gate-covered by Gate
43) — `record_available:false`, but `run.*`/`stage`/`spec.*`/`model`
still populate from the caller's literal inputs exactly as they do for
every other degraded record — so the fourth record's non-branch fields
degrade using code that already exists and is already tested, and the
new `branch_advance` group is simply added on top, independent of
`record_available`.

**This is a planning-judgment call, not something spec.md dictates
directly** (it satisfies FR-001's "in its own metrics record for a
cycle" by treating "a cycle" as the whole `cycle` job's one pass, which
can legitimately span more than one of the job's existing per-agent-step
records) — flag it in the issue comment as a decision made without an
explicit `[NEEDS CLARIFICATION]` marker to resolve.

## R3 — Composite gains seven additive, all-optional inputs; existing three call sites need zero changes

**Decision**: `wing-commander-metrics-summary/action.yml` gains:
`branch` (string, default `''`), `before-sha` (default `''`),
`before-sha-available` (`'true'`/`'false'`, default `'false'`),
`after-sha` (default `''`), `after-sha-available` (default `'false'`),
`commits` (default `''`), `commits-available` (default `'false'`). When
none are passed (every existing call site), `emit_record()` writes
`branch_advance: {available: false, branch: null, before_sha: null,
before_available: false, after_sha: null, after_available: false,
commits: null, commits_available: false}` — additive per FR-006, and
`available` is computed as `true` only when the caller passes at least
`branch` and one of the two SHA-available flags, so a caller has to
opt in explicitly rather than the group silently turning on.

**Rationale**: Mirrors the existing `turns`/`tokens` groups' own
`*_available` sibling convention (data-model.md, this contract's
"Unavailable-value convention"), extended to per-field granularity
inside the new group because FR-002 requires "before missing, after
present" to be independently expressible (the rejected-push and
not-yet-created-branch edge cases need exactly this). Keeping every new
input optional-with-a-degrading-default is what makes the three existing
call sites require zero line changes — the contract's compatibility rule
1 ("a field may be added; no field... removed, renamed...") is satisfied
by construction, and Gate 39's `check_fields_match_contract` cross-check
(the mechanism that fails a contract/code drift by construction) is
satisfied by adding the group to both the contract's `## Shape` block and
`REQUIRED_*` maps in the same change.

## R4 — "After" capture and the rejected-push case fall out of one `git fetch` + `rev-parse`, no special-casing needed

**Decision**: The new step does exactly what "Read back cycle outcome"
(966) already does for a different purpose — `git fetch origin
"+refs/heads/$BRANCH:refs/remotes/origin/$BRANCH"` then `git rev-parse
refs/remotes/origin/$BRANCH` — and sets `after-sha` to the result,
`after-sha-available` to `'true'` unless the fetch/rev-parse itself
fails (network/transient — degrades to `'false'`, matching spec.md's
Assumption "a failure to read the branch tip degrades that field to
unavailable and does not fail the cycle").

**Rationale — the rejected-push edge case needs no special code path**:
If the cycle's push was rejected (a concurrent force-push, FR-005's Edge
Case), `origin/$BRANCH` never advanced past what "Record base SHA"
already observed, so the freshly-fetched tip *is* `before-sha` —
`after_sha == before_sha`, `commits: 0`, both `available: true`. This is
not a degraded/unavailable state; it is a normally-measured "zero
progress" state, and it is exactly the shape acceptance scenario 1
(spec.md US1) wants: "When those two SHAs are equal, a lost-progress
signal is emitted." No branch of the new step needs to detect "was my
push rejected" explicitly — re-reading the branch's actual tip already
tells the truth.

## R5 — Commit count: `git rev-list --count $BEFORE..$AFTER`, computed once, stage-side, never re-derived

**Decision**: `commits` = `git rev-list --count "$BEFORE_SHA..$AFTER_SHA"`
(0 when equal). `commits-available` is `'false'` only when either SHA
itself is unavailable, or the range fails to resolve for a reason other
than "0 commits" (should not happen locally, since both refs are held by
the same checkout that just fetched them, but degrades rather than fails
the cycle, per the same best-effort assumption as R4).

**Rationale — the "reset backwards" edge case is a data shape, not new
logic**: When `after_sha` is an ancestor of `before_sha` (a branch reset
backwards — spec.md Edge Cases), `rev-list --count before..after` is `0`
by git's own semantics, while the two SHAs still differ — this is
already exactly the distinguishing signal FR-010's "compare the two
recorded points" rule needs (no lost-progress signal fires, since the
SHAs differ), and the record faithfully carries `commits: 0` alongside
differing SHAs without any extra code, matching FR-008's required
fixture ("a recorded count of zero alongside two differing points").
FR-019 forbids the watchdog from ever re-walking this range itself
(so a force-push orphaning the recorded commits after the fact cannot
break the finding) — the stage computes it once, here, while it still
holds both refs locally.

## R6 — `branch_advance` group shape

**Decision** (data-model.md has the full table):

```json
"branch_advance": {
  "available": true,
  "branch": "spec/050-branch-drift-sha-baseline",
  "before_sha": "5f2a1c...",
  "before_available": true,
  "after_sha": "5f2a1c...",
  "after_available": true,
  "commits": 0,
  "commits_available": true
}
```

**Rationale**: `available` gates the group as a whole (was this call
site even attempting to record a branch advance) so a reader can
distinguish "this record never carries this evidence" (the three
existing per-step records) from "this record tried and partially
succeeded" (a real but incomplete `branch_advance`). `branch` is not
independently availability-marked — FR-003 requires it be always
explicit whenever the group is populated at all (recorded literally by
the stage, `${{ inputs.spec-prefix }}${{ steps.spec.outputs.slug }}`,
never re-derived by a reader), so its absence is fully covered by the
group's own `available` flag. `before_sha`/`after_sha`/`commits` each
get independent `*_available` flags because FR-002 requires exactly that
granularity.

## R7 — Watchdog reads `branch_advance` via the existing artifact-download pattern, filters by `.available`, verdict is SHA equality

**Decision**: `collect-branch-drift`'s dispatched-implement arm (today's
`baseline="since-created"` branch, `watchdog.yml` ~720-732) downloads
the inspected run's `metrics-record*` artifact set the same way
`wing-commander-inspected-run-identity`'s `record_fallback` already does
(`gh run download ... -p 'metrics-record*'`, iterate `find ... -name
'*.json' | sort`), and reads the first record whose `.branch_advance
.available == true`. This is a genuinely new download at this call
site — `wing-commander-inspected-run-identity` only ever surfaces the
*slug*, not the whole record, as its own composite output, and re-using
its already-resolved artifact download (rather than repeating the `gh
run download`) is left as a follow-up simplification rather than
changing that composite's own output contract in this feature (research
decision, not spec-mandated — flagged for the issue comment).

When found: `baseline="exact-sha"`, verdict is `before_sha == after_sha`
(lost-progress when equal, per FR-010), `commits` is read verbatim from
the record (FR-019 — never recomputed). When absent (no record carries
`branch_advance.available:true` — an older pipeline version, an expired
artifact, a cycle that crashed before the new step ran): unchanged
`baseline="since-created"` behavior (FR-018), with the step summary
explicitly naming which baseline this run used (FR-013).

**Rationale — filtering by `.available`, not by step-index or run-label**:
FR-020 requires the fields be stage-neutral; a filter keyed to "the
implement stage's step-index 3" would silently stop working the moment a
`plan`/`tasks` populator (the FR-020 follow-up) uses a different
step-index or job shape. Filtering on the group's own `available` flag
is the one thing every future populator is guaranteed to set correctly,
since it is the same flag Gate 39 already validates as part of the
schema.

**Rationale — why the comparison stays a string equality, not a
`rev-list` walk**: This is the change that closes both miss cases.
Today's mechanism re-derives progress from the *branch's current state*
at inspection time (`--since=<createdAt>` against whatever `origin/
<branch>` looks like right now), which is exactly what a later rebase or
a later cycle's push can corrupt. Comparing the two SHAs the stage
itself recorded, at the moment it held them, is invariant to anything
that happens to the branch afterward (SC-003) — no fetch of the
*current* branch tip is even needed for the comparison itself (though
FR-011 still requires reporting `branch` alongside the SHAs, which the
record already carries).

## R8 — Comment replacement at `watchdog.yml` (FR-015)

**Decision**: The block at `watchdog.yml` ~704-716 (the comment
documenting the rebase and second-run miss cases as permanent, "Both err
toward a missed detection, never a false one, but they are baked in" —
quoted in spec.md's own Input) is replaced with a comment describing:
(a) why `HEAD_SHA..spec/<slug>` still cannot be used directly for a
dispatched run (the pre-existing reasoning about `HEAD_SHA` being the
default branch's tip stays, since that part of the mechanism is
unchanged), (b) that a dispatched implement run's own metrics record now
carries the exact before/after pair the stage observed, closing both
previously-permanent misses, and (c) that the `--since=<createdAt>` arm
survives only as the fallback for a record that predates this feature or
never reached the recording point (FR-018), not as the primary
mechanism. This is a comment-only content change layered onto the
logic change R7 already makes — CLAUDE.md's "workflow comments are
load-bearing" rule applies, so this edit is reviewed as a behavior
change, not a copy edit.

## R9 — Gate plan: extend three, add one

**Decision**:
- **Gate 39** (`verify-metrics-record-schema.py`): `branch_advance`
  added to `REQUIRED_TOP`'s nested-group set (mirroring how `turns`/
  `tokens` are already declared) and to the contract's `## Shape` +
  degraded-record blocks in the same change; seven new fixtures under
  `.github/scripts/fixtures/metrics-record-schema/` (FR-008: both points
  present+different, both present+equal, before-unavailable, after-
  unavailable, count=0 with differing points, count-unavailable-with-
  both-points-present, one wrong-typed new field).
- **Gate 41** (`verify-metrics-persist-retry.py`): one additional fixture
  record carrying a populated `branch_advance` group, appended through
  the existing case functions, proving dedup/retry is unchanged by the
  new fields' presence (FR-009) — no logic change, since dedup keys
  only on `run.record_key`.
- **Gate 43** (`verify-metrics-summary-record-emission.py`): extended to
  invoke the real composite a fourth time the way `implement.yml`'s new
  step does (populated inputs, absent transcript) and assert the emitted
  record's `branch_advance` group matches, alongside its two existing
  assertions (a healthy transcript record, a missing-transcript
  degraded record) and its existing three-call-sites-per-job shape
  assertion (now four).
- **New gate** (provisionally **Gate 53** — 52 is the highest gate number
  in `lint-workflows.yml` at plan time; confirmed at implementation time,
  per this repository's own convention for provisional gate numbers,
  e.g. specs/042's plan): exercises the real, shipped
  `collect-branch-drift` step text (not a reimplementation) against a
  local git repository fixture and synthetic run/record JSON, covering:
  exact-SHA equal → lost-progress signal naming branch/both SHAs/commits
  (US1 AS1); exact-SHA differ → no signal (US1 AS3); the already-
  handled/stalled short-circuit still fires under the new fact shape
  (US1 AS4, FR-014); no `branch_advance` on the record → since-created
  fallback fires and the step summary names it (US3, FR-013, FR-018); a
  non-dispatched-implement run (a spec-branch-head run, a non-push-
  expected stage, a skipped/cancelled run) is unaffected (FR-012). No
  live rebase or live second-run needs driving for SC-001/SC-003 — the
  gate proves the invariant those scenarios depend on (the verdict reads
  only the recorded pair, never the branch's live state), which is a
  stronger, cheaper guarantee than replaying the two live scenarios.
  Gate wiring follows constitution VIII: `!cancelled()`, its own PR
  trigger path entry, not suppressible by an unrelated gate.

**Rationale**: No gate today drives `collect-branch-drift`'s own shipped
bash (confirmed: `verify-watchdog-run-failure-paths.sh`/Gate 36 covers
the stage-8b self-checker's failure branches, a different file). The
rewritten comparison/fallback logic is genuinely new shipped behavior,
so per constitution VIII it needs its own fixture-backed coverage rather
than being folded into an existing gate whose subject is something else.

## R10 — The FR-020 follow-up issue is filed at implementation time, not by this plan

**Decision**: FR-020 requires "The plan/tasks gap MUST be filed as a
follow-up issue from this spec." This plan stage's own allowed tool
surface has no `gh issue create` (only `gh issue view`/`gh issue
comment`/`gh pr view`/`gh pr list`/`gh issue list`), so the issue is not
filed here. tasks.md should carry a task whose acceptance is "the
follow-up issue exists, titled around 'plan/tasks stages populate
branch_advance', referencing this spec and FR-020" for the implement
stage (which does have issue-creation tooling) to execute.

**Rationale**: Automation-First (constitution IV) requires every
manual/deferred step be reported explicitly rather than silently
assumed — recording this now, as a plan-stage decision with a named
owner (a tasks.md task), is that report.

## R11 — Signal fact-shape migration needs no dedup-identity change

**Decision**: The emitted signal's `facts` object changes from `{branch,
since, after-sha, commits}` to also (or instead, when the exact-SHA arm
fires) carry `before-sha` in place of `since`, and a real `commits`
value in place of today's hardcoded `commits:0` placeholder the
since-created arm always emits. Per spec.md's Assumption ("both the old
and the new fact shapes project to the same identity") and Out of Scope
("changing how findings are filed, deduplicated, or routed"), the
fingerprint/dedup mechanism downstream of the collector is untouched —
confirmed by re-reading spec 024's amended contract (`triage`'s
fingerprint is `sha256(class + "|signals:" + sorted-joined(signal
ids))`, never a hash of `facts` contents), so a fact-shape change here
cannot itself fragment or merge existing findings differently than
today.
