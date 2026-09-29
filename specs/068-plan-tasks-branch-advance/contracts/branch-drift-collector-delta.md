# Contract Delta: Watchdog Branch-Drift Collector (`watchdog.yml`, `collect-branch-drift`)

This is a delta against `specs/050-branch-drift-sha-baseline/contracts/
branch-drift-collector-delta.md`, which remains the base for the
head-sha arm, the push-expected-stages gate, and the already-handled/
stalled short-circuit — all unchanged by this feature. Only the
exact-sha lookup's reach and the missing-evidence fallback change.

## Widened reach: the exact-sha lookup applies to plan and tasks too

**Current contract** (post-050): The metrics-record download and
`branch_advance.available` scan run only when `"$RUN_NAME" =
"Wing Commander · 5 implement"` (nested inside the "run's head branch is
not the branch the stage pushes to" arm). A plan or tasks run reaching
that same arm — which is every plan/tasks run today, since neither
stage's head branch is ever the branch it pushes to (spec.md's Overview)
— falls straight to "the head branch owes no commits — skipping," never
attempting the download.

**Amended contract**: The download-and-scan block runs for all three
push-expected stages (the outer `case "$RUN_NAME"` gate at the top of
the step already limits the whole step to `plan`/`tasks`/`implement`).
When a record with `branch_advance.available == true` and both points
present is found, `baseline="exact-sha"` fires for whichever of the
three stages produced it, with `measure_branch` always read from that
record's own `branch_advance.branch` (never a `${spec-prefix}${slug}`
guess) — required for plan/tasks because a `pr`-mode run's branch is
`plan/<slug>`/`tasks/<slug>`, which no prefix-derived guess would ever
produce (FR-004). This is a strict generalization for implement (its
own records already carry the same value a prefix guess would) and the
only correct behavior for plan/tasks.

## Fallback selection now depends on which stage produced the run

**Current contract**: When no usable record is found, the step falls
back to `baseline="since-created"` unconditionally (for the one stage —
implement — that could ever reach this point).

**Amended contract**: The since-created fallback fires **only when
`RUN_NAME` is `"Wing Commander · 5 implement"`** (and `RUN_CREATED_AT`
is non-empty, unchanged). A plan or tasks run with no usable record
produces **no signal and attempts no fallback measurement** — the step
summary states "no recorded branch-advance evidence on this
`<plan|tasks>` run — skipping," and the collector's outcome is recorded
as `"ok"` (trustworthy), not `"failed"`, matching data-model.md's
step-summary text and FR-016's "an absent optional field is data, not a
failed read."

**Rationale for the asymmetry**: The since-created baseline branch
(`${spec-prefix}${slug}`) is only the branch a plan/tasks run actually
advanced in `auto` mode; guessing it for a `pr`-mode run would measure
a branch that run never touched and risks a false lost-progress signal
on a healthy `pr`-mode run whose review branch is simply still open
(FR-016; research.md R5). Implement has no review mode and always
advances `${spec-prefix}${slug}`, so its own fallback stays exactly as
specs/050 shipped it (Out of Scope: "changing the timestamp-window
baseline that survives for implement runs whose records predate spec
050").

## Signal emission — unchanged shape, now reachable for three stages

**Current contract**: The `exact-sha` arm's `facts: {branch,
"before-sha", since: null, "after-sha", commits}` shape and the
already-handled/stalled short-circuit are implement-only in practice
(the only stage that ever reaches the arm).

**Amended contract**: Identical shape, now reachable for a plan or a
tasks run too — `branch` in the emitted facts is the record's own value
(`plan/<slug>`, `tasks/<slug>`, or `spec/<slug>`), and the
already-handled/stalled short-circuit applies identically regardless of
which of the three stages produced the evidence (FR-014; unchanged
code — no new branch needed, since the short-circuit already keys on
`META_STAGE`/`STALLED_LABEL`, not on `RUN_NAME`).

## No change to identity resolution, the head-sha arm, or dedup

`wing-commander-inspected-run-identity`'s slug resolution already
handles plan and tasks runs today (a `spec-draft/<slug>` head resolves
directly; a dispatched tasks run or a workflow_dispatch-triggered plan
run resolves via the same metrics-record fallback implement already
uses — confirmed against the shipped composite, unrelated to this
feature). The head-sha arm, the push-expected-stages gate
(`watchdog.yml:684-690`), and the fingerprint/dedup mechanism downstream
of this collector are unaffected (research.md R6; Out of Scope).

## Replaced comments (FR-023)

The two comment blocks documenting "plan and tasks push to the
persistent spec branch, but... the collector skips it" and "plan and
tasks push to spec/<slug> only in auto review mode... so with a non-spec
head they still skip" (`watchdog.yml:696-699`, `:719-731`, both quoted
verbatim in spec.md's Overview) are replaced with a comment describing:
(a) why a plan/tasks run's head branch still cannot be used directly
(unchanged reasoning — a draft or default-branch head names nothing
about what the run pushed), and (b) that a plan/tasks run's own metrics
record now carries the exact quadruple it observed, read the same way
implement's already is, closing the gap the replaced comments described
as total. Comment-only content change layered onto the logic change
above — reviewed as a behavior change per CLAUDE.md's load-bearing-
comments rule.
