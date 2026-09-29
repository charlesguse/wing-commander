# Feature Specification: Guard the pipeline checkout against every tree-mutating step, not just `actions/checkout`

**Feature Branch**: `107-pipeline-guard-tree-mutations`

**Created**: 2026-09-29

**Status**: Draft

**Input**: Lifecycle issue #789, routed from the board loop (originating issue #674), found by the code review of #673:

> Two more ways a branch can land files over the `.wing-commander-pipeline`
> checkout: metrics-persist's `git checkout -B`, and agent-driven `git rebase`.
>
> #673 guards every `actions/checkout` that follows the pipeline checkout
> (#611), but two other paths can still put branch-controlled files in the
> workspace root:
>
> 1. `wing-commander-metrics-persist` runs `git checkout -B <metrics-branch>`
>    in the workspace root. A metrics branch that tracks paths under
>    `.wing-commander-pipeline/` would overwrite the trusted checkout the same
>    way #611 describes.
> 2. Agent-driven `git rebase` (rebase stage, and implement's agent) checks out
>    and replays commits in the workspace root. A rebased-onto commit that
>    tracks `.wing-commander-pipeline/` paths lands those files before any later
>    step loads a composite.
>
> Gate 116 (`verify-pipeline-checkout-guard.py`, from #673) only scans
> `actions/checkout` steps, so neither path is covered.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A replayed commit cannot become pipeline code (Priority: P1)

The rebase stage replays a consumer branch's commits onto the default branch in
the workspace root, and later in the same job loads composites and scripts from
`.wing-commander-pipeline/` with the App token in hand. Today the pipeline
checkout is verified once — immediately after the branch is checked out — and
never again, even though the rebase that follows rewrites the working tree from
commits nobody has inspected. The pipeline owner needs the replayed tree to be
subject to the same refusal as the checked-out tree: if what lands in the
workspace tracks anything under `.wing-commander-pipeline/`, the job stops
before the next composite loads.

**Why this priority**: This is the path with a hostile actor already in the
threat model. The rebase stage runs on branches the pipeline itself does not
author, the tree mutation happens after the one existing verification point, and
the very next steps in the job are `uses: ./.wing-commander-pipeline/...`. It is
the shortest route from a crafted commit to pipeline-privileged code execution.

**Independent Test**: Drive the rebase stage on a branch whose commits track a
file under `.wing-commander-pipeline/`; confirm the job fails with the #611
`::error::` after the replay and before any later pipeline composite resolves,
and that the trusted files are restored or the directory removed.

**Acceptance Scenarios**:

1. **Given** a job that has checked the pipeline out at
   `.wing-commander-pipeline/` and then replays branch commits in the workspace
   root, **When** the replayed tree tracks one or more paths under
   `.wing-commander-pipeline/`, **Then** the job fails with the guard's
   `::error::` naming the offending commit and the remediation, and no later
   step in that job loads a composite from the overwritten directory.
2. **Given** the same job, **When** the replay leaves the tree tracking nothing
   under `.wing-commander-pipeline/`, **Then** the guard passes and the job
   continues unchanged.
3. **Given** a replay that deleted or replaced `.wing-commander-pipeline`
   itself (a tracked symlink, a missing `.git`, a different commit), **When**
   the guard runs, **Then** it removes whatever sits at that path and fails,
   rather than reading the guard from the branch's own copy.
4. **Given** an agent step that holds a tool grant able to mutate the tree
   (`git rebase --continue`, `git rebase --abort`, `git add`, `Edit`), **When**
   the step ends by any route — success, hard failure, or a refused tool —
   **Then** the guard still runs before the job's next pipeline-composite load.

### User Story 2 - The metrics branch cannot overwrite the pipeline checkout (Priority: P2)

`wing-commander-metrics-persist` runs `git checkout -B <metrics-branch>
origin/<metrics-branch>` in the workspace root, inside a retry loop, to append
this run's records. That checkout brings the metrics branch's tree into the
workspace. If the metrics branch tracks paths under `.wing-commander-pipeline/`,
the pipeline's trusted files are overwritten, and every later step — including
the rest of metrics-persist and any composite the calling job loads afterwards —
runs code from that branch. The pipeline owner needs this checkout held to the
same standard as the `actions/checkout` sites #673 covered.

**Why this priority**: Same exposure class, narrower reachability — the metrics
branch is written by the pipeline's own bot, so landing a hostile tree there
takes push access to the consumer repository. Real, but a step behind US1.

**Independent Test**: Point metrics-persist at a destination branch that tracks
a file under `.wing-commander-pipeline/`; confirm the guard refuses it and the
step reports the #611 error instead of appending records against an overwritten
pipeline checkout.

**Acceptance Scenarios**:

1. **Given** metrics-persist has checked the destination branch out in the
   workspace root, **When** that branch tracks any path under
   `.wing-commander-pipeline/`, **Then** the guard refuses it before any
   subsequent pipeline composite or script loads.
2. **Given** the destination branch does not yet exist and metrics-persist
   creates it as an orphan with an emptied tree, **When** the guard runs,
   **Then** it passes — an orphan reset lands no branch-controlled files.
3. **Given** the retry loop runs several attempts, each re-deriving branch
   newness and re-checking the branch out, **When** any attempt's checkout lands
   pipeline-tracked paths, **Then** that is caught rather than being masked by a
   later attempt.

### User Story 3 - A new tree-mutating step cannot forget the guard (Priority: P3)

Gate 116 exists because a guard one new step forgets is no guard. It currently
pins placement only for `actions/checkout` steps, which is exactly why these two
paths were missed. The pipeline owner needs the gate to recognise the wider
class, so the next `git checkout`, `git rebase`, or agent step added ahead of a
pipeline-composite load fails CI instead of quietly opening the hole again.

**Why this priority**: The durable part of the fix, but it has no value until
US1 and US2 have added the call sites it pins.

**Independent Test**: Run the gate's self-test; each newly covered site class
must fail when its guard is removed, and must fail when a new unguarded step of
that class is inserted ahead of a pipeline-composite load.

**Acceptance Scenarios**:

1. **Given** the real tree with every required guard in place, **When** the gate
   runs, **Then** it passes and reports a non-zero count of guarded sites for
   each covered class.
2. **Given** an in-memory mutation that deletes the guard following a
   tree-mutating step, **When** the gate runs, **Then** it fails naming that
   step.
3. **Given** an in-memory mutation that inserts a new unguarded tree-mutating
   step ahead of a pipeline-composite load, **When** the gate runs, **Then** it
   fails naming the inserted step.
4. **Given** a pasted second copy of the guard's invocation anywhere under
   `.github/workflows/` or `.github/actions/`, **When** the gate runs, **Then**
   it fails on the single-home check.
5. **Given** a tree with zero sites of a covered class, **When** the gate runs,
   **Then** it fails as having no subject rather than passing vacuously.

### Edge Cases

- **A mutation inside a single `run:` block.** metrics-persist's `git checkout
  -B` sits inside an eight-attempt retry loop in one shell step. A guard step
  cannot be interposed between loop iterations, so the guard must either run
  once after the step or be reachable from inside that block — and either way
  the invocation must not become a second home for the guard's text. See
  [NEEDS CLARIFICATION #2].
- **A mutating step that failed.** The rebase attempt is deliberately allowed to
  exit non-zero, and the conflict-resolution agent may hard-fail. The tree is at
  its most unpredictable exactly then, so the guard must run on those paths too —
  which means its gating condition must not be one that skips on failure.
- **Teardown that mutates the tree again.** `rebase.yml` runs `git rebase
  --abort` in cleanup. Whether a guard is required after a teardown mutation
  depends on whether anything after it loads a pipeline composite.
- **Jobs that never load a pipeline composite after the mutation.** Requiring a
  guard there adds cost and noise with nothing to protect; the requirement is
  conditioned on a later load in the same job.
- **The mutating step lives in a composite loaded from the pipeline checkout.**
  metrics-persist is itself such a composite. Its guard invocation must still
  read the guard from the verified repository's object store, never from a
  working tree the mutation may just have rewritten.
- **A mutation that removes `.wing-commander-pipeline` entirely** (a replayed
  commit tracking the path as a symlink) must be refused by the inline
  verification, not by code read out of the replaced directory.
- **`git checkout --orphan` followed by `git rm -rf .`** lands no tracked files;
  the guard must pass rather than report a false positive.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The pipeline-checkout guard MUST run after every step that can
  bring branch-controlled files into the workspace root, in any job or composite
  that loads a composite or script from `.wing-commander-pipeline/` after that
  step. Coverage MUST no longer be limited to `actions/checkout` steps.
- **FR-002**: The set of step kinds treated as tree-mutating MUST be defined
  explicitly and enforceable by static inspection of the workflow and composite
  files. [NEEDS CLARIFICATION: how wide is the class? (a) exactly the two paths
  this issue names — metrics-persist's branch checkout and the rebase stage's
  replay; (b) those plus every agent step in a job that later loads a pipeline
  composite; (c) every in-shell `git checkout`/`switch`/`reset --hard`/`rebase`/
  `cherry-pick`/`merge` against the workspace root, plus every agent step.]
- **FR-003**: `wing-commander-metrics-persist`'s workspace-root checkout of the
  destination branch MUST be guarded, on every retry attempt that performs it.
- **FR-004**: The rebase stage MUST be guarded after the deterministic rebase
  attempt and after the agent-driven conflict resolution, on every outcome path
  (clean, conflict, error, agent failure).
- **FR-005**: Where a tree mutation occurs inside a shell block rather than as a
  distinct step, the placement rule MUST still be stated and enforced. [NEEDS
  CLARIFICATION: for an in-shell mutation such as metrics-persist's retry loop,
  is the guard required (a) once, as the next step after the mutating step;
  (b) inside the loop, immediately after each checkout; or (c) both — inside for
  early refusal and after the step as the pinned, gate-visible site? Each choice
  changes what the gate can pin byte for byte and how the single-home rule
  expresses an in-shell call site.]
- **FR-006**: A guard refusal MUST keep the existing failure contract: print the
  `::error::` naming the offending commit, the count of offending paths, and the
  remediation; restore the pipeline checkout's tracked files from its own HEAD,
  or remove the path when it is no longer the trusted checkout; and fail the
  step.
- **FR-007**: The guard MUST continue to be read from the verified pipeline
  repository's object store at HEAD, never from a working tree, at every new
  call site — including sites inside composites that themselves live in the
  pipeline checkout.
- **FR-008**: Before reading anything out of `.wing-commander-pipeline/`, every
  new call site MUST perform the same inline verification the existing sites do:
  the path is not a symlink, holds a real `.git` directory, is its own
  repository's top level, and sits at the job's resolved pipeline ref when that
  ref is a full SHA.
- **FR-009**: [NEEDS CLARIFICATION: what does a guard refusal inside
  metrics-persist do to the run? (a) fail the step and the metrics job, dropping
  this run's records — fail closed, consistent with every other guard site;
  (b) abandon the append, emit the error, and let the job report degraded so
  metrics loss is visible but not itself a failure; (c) fail closed but exclude
  the metrics job from whatever treats a red job as a pipeline defect.]
- **FR-010**: Gate 116 (`verify-pipeline-checkout-guard.py`) MUST be extended to
  pin placement for every newly covered site class, and MUST fail when a site of
  any covered class is unguarded, when its guard's gating condition does not
  cover the mutating step's failure paths, when the guard carries
  `continue-on-error`, or when the guard lacks `shell: bash`.
- **FR-011**: Gate 116's single-home check MUST continue to fail on any second
  copy of the guard's text or of the tracked-path listing under
  `.github/workflows/` or `.github/actions/`, under whatever invocation form
  FR-005 settles on.
- **FR-012**: Gate 116 MUST remain non-vacuous: it MUST fail if it finds zero
  sites of a covered class, so a refactor that removes the last site is reported
  rather than passing silently.
- **FR-013**: Gate 116's self-test MUST gain one failing mutation per newly
  covered site class (guard removed; new unguarded site inserted; guard gated so
  it skips the mutating step's failure path), plus a scratch-repository scenario
  that drives a replayed/checked-out tree tracking `.wing-commander-pipeline/`
  through the guard and asserts refusal, restoration, and no stray workflow
  commands.
- **FR-014**: The rationale for the widened coverage MUST live in exactly one
  canonical comment, with every other site pointing at it, per this
  repository's single-home rule.

### Key Entities

- **Pipeline checkout**: the trusted `.wing-commander-pipeline/` directory inside
  the workspace, from which composites and scripts are loaded for the rest of a
  job with the App token available.
- **Tree-mutating step**: a workflow or composite step that can change the
  workspace root's working tree to content controlled by a branch or commit the
  pipeline did not author — today an `actions/checkout`, a `git checkout -B`, a
  replay (`git rebase`), or an agent holding a tree-writing tool grant.
- **Guarded site**: a tree-mutating step paired with the guard invocation that
  must immediately follow it; the unit Gate 116 counts and pins.
- **Guard invocation**: the single canonical form — inline verification of the
  pipeline checkout, then the guard read from that repository's object store and
  piped to `bash`.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Zero unguarded tree-mutating sites remain: for every job and
  composite that loads something from the pipeline checkout after a tree
  mutation, a guard sits between them. The gate reports the count and it matches
  the inventory.
- **SC-002**: The two paths this issue names are demonstrably closed — a tree
  that tracks a path under `.wing-commander-pipeline/`, arriving via the rebase
  stage's replay or via metrics-persist's branch checkout, is refused before any
  later pipeline composite loads, in both cases with the offending commit named.
- **SC-003**: Every newly covered site class has at least one self-test mutation
  that fails the gate, and the gate passes on the unmutated tree; removing any
  single new guard turns the gate red.
- **SC-004**: The guard's text has exactly one home; a pasted copy of it, or of
  the tracked-path listing, anywhere under `.github/workflows/` or
  `.github/actions/`, fails the gate.
- **SC-005**: No false positives: a full pipeline run whose tree mutations are
  all benign — including a clean rebase, a conflict resolved by the agent, a
  first-time orphan metrics branch, and an existing metrics branch — completes
  with no new guard failures.
- **SC-006**: Added cost is negligible: each new guard site adds a single
  sub-second check, and the run's total step count grows by no more than the
  number of guarded sites.

## Assumptions

- Relocating the pipeline checkout outside the workspace — which the issue notes
  would remove this whole class of problem — is explicitly **out of scope** here.
  This feature closes the remaining holes in the in-workspace guard; the
  relocation stays a separate, larger change.
- The #611 threat model holds unchanged: the pipeline checkout is trusted, the
  workspace root's checked-out or replayed tree is not, and code loaded from the
  pipeline checkout runs with the App token available.
- The existing guard script and its refusal/restore behaviour are correct and
  are reused as-is; this feature adds call sites and gate coverage, not a second
  guard.
- The metrics destination branch is treated as untrusted input even though the
  pipeline's own bot writes it, because anyone with push access to the consumer
  repository can write it too.
- A job that performs a tree mutation and then loads nothing from the pipeline
  checkout needs no guard; the requirement is conditioned on a later load in the
  same job.
- The implement stage's agent is in scope only to the extent that its job loads a
  pipeline composite after the agent step; the exact inventory of agent steps
  that qualify is derived during planning, not asserted here.
- Gate 116 stays the single gate for this rule — its number, name, and
  registration in `lint-workflows.yml` are extended rather than duplicated by a
  new gate.

## Dependencies

- `.github/scripts/pipeline-checkout-guard.sh` (the guard, from #611/#673).
- `.github/scripts/verify-pipeline-checkout-guard.py` (Gate 116, from #673) and
  its registration in `.github/workflows/lint-workflows.yml`.
- `.github/actions/wing-commander-metrics-persist/action.yml` (US2's site).
- `.github/workflows/rebase.yml` (US1's sites).
- The repository's single-home rules and the comment-canonical-pointer gate.
