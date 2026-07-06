# Phase 0 Research: Implement/Converge Stage — Iterative Build to Convergence

`spec.md`'s own checklist (`checklists/requirements.md`) confirms no
`[NEEDS CLARIFICATION]` markers remain — the core loop shape, the
cap-reached outcome, per-cycle reporting, and the model default/opt-in are
all fully determined by `docs/architecture.md`'s Stage 4 section and the
constitution's model-tiering table. What follows are the implementation-level
decisions `spec.md` deliberately leaves open ("this specification concerns
the orchestration of the implement-then-reassess loop... not the internal
behavior of the implementation or convergence tooling") that a plan must pin
down before tasks can be generated.

## Decision: No per-iteration work branch or PR — direct commits to `spec/NNN-slug`

**Decision**: Each cycle checks out the persistent `spec/NNN-slug` branch
directly (no `impl/NNN-slug-iterN` branch, no PR) and pushes its commits
straight to it.

**Rationale**: `docs/architecture.md`'s Stage 4 design says explicitly:
"checkout `spec/NNN-slug`; ... commits pushed to the spec branch as task
phases complete" — no branch or PR is mentioned anywhere in the design's four
numbered steps. `spec.md` reinforces this independently: FR-001 and FR-015
both say progress is committed to the specification's "persistent working
branch" (singular — the same `spec/NNN-slug` established by earlier stages,
per the Assumptions section: "this stage does not introduce new such
concepts"), and FR-015 explicitly forbids this stage from opening a PR at
all. The constitution's Operational Constraints section lists
`impl/<NNN-slug>-iterN` alongside `plan/<NNN-slug>` as an available branch
*naming convention*, but that is a taxonomy entry, not a mandate that every
future stage exercise it — the plan and tasks stages already show that not
every stage that could open a PR does (the tasks stage's `auto` mode also
commits directly with no PR). Since no functional requirement calls for a
review artifact at this stage (there is no human-in-the-loop gate here per
`docs/architecture.md`'s stage table — the machine gate is "tasks.md
unchanged after converge"), direct commit is the correct, simpler reading.

**Alternatives considered**: Opening an `impl/NNN-slug-iterN` PR per
iteration and auto-merging it — rejected: FR-015 forbids this stage from
opening, approving, or merging any PR, and an auto-merged PR provides no
human review value while adding an extra branch/PR per cycle (up to 5 by
default) that would need its own cleanup.

## Decision: Loop-condition signal — commit-message convention, not a live working-tree diff

**Decision**: Within one dispatched run, the agent step (a) runs
`/speckit-implement`, committing implementation progress with messages
prefixed `implement:`; (b) then runs `/speckit-converge`. Per the converge
skill's own append-only contract, this either leaves `tasks.md`
byte-for-byte unchanged (nothing to commit) or appends a new
`## Phase N: Convergence` section, which the agent commits separately with a
message prefixed `converge:`. A deterministic step (no agent turns) records
the spec branch's HEAD commit SHA *before* invoking the agent, and after the
agent pushes, walks the new commit range (`git log <before-sha>..origin/spec/NNN-slug`)
for a commit touching `$SPEC_DIR/tasks.md` whose subject starts with
`converge:`. Its presence is the not-converged signal (FR-002/FR-003); its
absence is the converged signal (FR-004).

**Rationale**: `docs/architecture.md`'s own sketch — "the loop condition is
machine-checkable: `if git status --porcelain -- $SPEC_DIR/tasks.md`" —
assumes a single live working tree where converge's edits are still
uncommitted at the moment of the check. That doesn't translate directly
across a job boundary once implementation's own commits (which legitimately
mark task checkboxes `[ ]` → `[X]` in `tasks.md`, per the implement skill's
"Done When") are pushed first — a raw before/after byte-diff of `tasks.md`
across the whole cycle would conflate implement's checkbox edits with
converge's phase-append and could never read as "unchanged" even on a
converged run. Keying off the converge skill's own append-only contract
(either nothing to commit, or exactly one new commit touching `tasks.md`)
gives an unambiguous, deterministic, git-native signal that doesn't require
parsing `tasks.md` content at all, and doubles as this stage's audit trail
(FR-014): every cycle's implement and converge commits are individually
visible in `git log`.

**Alternatives considered**: Having the agent write a machine-readable
outcome file (e.g. `.speckit-converge-result.json`) — rejected as a second,
redundant source of truth alongside the commit history and `tasks.md`
itself, and one more artifact this stage would need to clean up. Diffing
`tasks.md` phase-header counts before/after — rejected as strictly more
complex than the commit-message check for the same guarantee, since the
converge skill already commits-or-doesn't atomically.

## Decision: Model tier ladder is exactly `claude-sonnet-5` → `claude-opus-4-8` (no Haiku rung)

**Decision**: The implementation model for a cycle's normal (non-retry) run
is `vars.SPECKIT_IMPLEMENT_MODEL` (default `claude-sonnet-5`), escalated to
`claude-opus-4-8` if the lifecycle issue carries the `model:opus` label
(`docs/setup.md`'s documented opt-in). The FR-013 failure-retry escalation
ladder for *this* stage is exactly these same two rungs: sonnet → opus. If
the failing attempt was already on `claude-opus-4-8` (either because
`SPECKIT_IMPLEMENT_MODEL` was set to it repo-wide, or because `model:opus`
was applied), there is no higher rung, so a failure goes straight to stalled
with no retry attempted.

**Rationale**: The constitution's model-tiering table (Principle II) and
`docs/architecture.md`'s own tiering table both reserve `claude-haiku-4-5`
exclusively for "triage, classification, labeling, and summaries" and name
only `claude-sonnet-5` (default) / `claude-opus-4-8` (opt-in) for
"implementation and convergence." Introducing Haiku as a rung that actually
*writes code and commits* for a retried implement/converge pass would
contradict that table and the cost/quality rationale behind it — Haiku is
sized for cheap classification work, not for authoring an implementation.
FR-013's "(for example, Haiku → Sonnet → Opus)" reads as an illustrative,
generic escalation-ladder example (the parenthetical explicitly says "for
example"), not a mandate to add a third tier this stage's own governing
tiering table doesn't otherwise define. This decision is recorded here as an
interpretation made without further clarification, to be called out in the
plan PR body.

**Alternatives considered**: A three-rung ladder starting at Haiku —
rejected for contradicting the constitution's tiering table above. Always
retrying at Opus regardless of starting tier (even if the starting tier
already was Opus) — rejected; FR-013 is explicit that no further tier to
escalate to means stall, not a same-tier retry.

## Decision: Progress comment is a separate Haiku step, not authored by the implement/converge agent itself

**Decision**: After each cycle's implement+converge agent step completes (or
fails), a separate `claude-haiku-4-5` step summarizes what happened
(`git log`/`git diff --stat` for the cycle's commits, plus the deterministic
converged/not-converged signal) and posts that as the lifecycle issue
progress comment (FR-008).

**Rationale**: This is the one place `docs/architecture.md`'s Stage 4 design
diverges from the plan/tasks stages' precedent (where the same agent that
does the work also writes its own issue comment) — architecture.md's design
says plainly: "Post a brief progress comment (`claude-haiku-4-5` summary)
each iteration," matching the constitution's tiering table entry for "diff
summaries" being Haiku's job specifically. Unlike the tasks stage (whose
sonnet agent already has the full task list in context to summarize for
free), an implement/converge cycle's own transcript is a long, code-focused
session; distilling it into a short progress update is exactly the
after-the-fact "diff summary" role the constitution carves out for Haiku, and
keeping it a separate deterministic-triggered step means the progress
comment still posts even when the main agent step fails outright (the
retry/stalled paths need to report too, per FR-013).

**Alternatives considered**: The implement/converge agent posts its own
comment (tasks-stage precedent) — rejected per architecture.md's explicit
design choice above, and because it wouldn't cover the failed-attempt case
without duplicating comment logic into the failure/retry path too.

## Decision: Idempotency guard keys off `spec-meta.json`'s `stage` and `iteration` together

**Decision**: Before doing anything else, read `stage` and `iteration` from
`specs/NNN-slug/spec-meta.json` on `spec/NNN-slug`. Proceed only if:
- `stage == "tasks"` and the dispatched `iteration` input is `1` (first
  cycle, handed off from the tasks stage, which never touches `iteration`),
  or
- `stage == "implement"` and the dispatched `iteration` input equals the
  recorded `iteration + 1` (the next expected cycle).

Any other combination (a re-delivered or duplicated dispatch for an
iteration already completed, or a dispatch arriving after this specification
has already moved on to `"review"`/`"done"`/`"stalled"`) is treated as a
duplicate/out-of-order notification: log it and exit successfully without
running a cycle, posting a comment, or dispatching anything (FR-011).

**Rationale**: `stage` is already the durable, machine-checked idempotency
field the plan and tasks stages use for exactly this purpose; pairing it
with `iteration` (a field that exists in the schema specifically for "this
stage owns it from iteration 1 onward") is the natural extension for a stage
that, unlike its predecessors, can be legitimately dispatched more than once
for the *same* specification — so "already handled" must be judged per
iteration, not just per stage name.

**Alternatives considered**: A separate processed-iterations ledger file —
rejected as an unnecessary second source of truth alongside
`spec-meta.json`, mirroring the tasks stage's research.md's rejection of the
analogous idea.

## Decision: Outright-failure detection combines the agent step's own exit status with a post-hoc verification

**Decision**: A cycle's attempt counts as an outright failure (FR-013's
"cannot complete because of a resource or tooling failure," triggering
retry/stall) when *either* (a) the `claude-code-action` step itself exits
non-zero, or (b) it exits zero but a deterministic post-step finds
`spec-meta.json` on `spec/NNN-slug` was not updated to `stage == "implement"`
and `iteration == <this cycle's iteration>` as instructed. Only a run that
passes both checks is treated as "completed" (whether converged or not).

**Rationale**: A resource/tooling failure can surface as a hard step failure,
but it can also surface as the agent's turn budget or tool access running
out silently mid-task, leaving the branch not actually advanced —
distinguishing that from "genuinely converged" or "genuinely still has
gaps" requires confirming the expected state change actually landed, exactly
like the plan and tasks stages' own "Verify ... " deterministic steps
already do for their PR/commit postconditions.

**Alternatives considered**: Trusting the action's exit code alone —
rejected; a silently-incomplete run that exits 0 without pushing the
expected state change would otherwise be misread as "converged" (nothing
changed) rather than "failed," which is the exact failure mode FR-013 exists
to catch.
