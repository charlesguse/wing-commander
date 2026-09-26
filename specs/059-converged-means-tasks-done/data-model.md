# Phase 1 Data Model: Converged Means No Task Is Left

This feature has no database or application data model. Its "entities" are
values computed by deterministic shell inside GitHub Actions steps and
carried as step/job outputs. This document names each one, its shape, where
it is computed, and the rules that relate them — the workflow-native
equivalent of a data model for this project type (a CI/CD pipeline).

## Entities

### Outstanding-task count (`unchecked-count`)

- **Shape**: non-negative integer.
- **Computed by**: `count-tasks-checkboxes.sh` (via the
  `wing-commander-tasks-checkbox-count` composite), reading `tasks.md` at a
  given git ref, counting lines matching `^\s*- \[ \]` that are not inside a
  fenced code block (D3).
- **Read at**: the cycle's pushed tip (`origin/${SPEC_PREFIX}$SLUG`), for
  the convergence decision (FR-001, FR-002).
- **Validation rule**: FR-006 — if the ref:path cannot be read at all, the
  composite step fails the job outright; `unchecked-count` is never reported
  as `0` in that case (that would read as "converged" and is exactly the
  false pass Principle VIII forbids).

### Checked-task count (`checked-count`)

- **Shape**: non-negative integer.
- **Computed by**: the same composite call as `unchecked-count` (one script
  pass over the file emits both), counting `^\s*- \[[xX]\]` outside a
  fenced block.
- **Read at**: both the cycle's own base (`BASE_SHA` for the primary arm, the
  retry's own recorded base for the retry arm — FR-007, FR-010a) and the
  pushed tip, one call each, to compute Cycle progress (below).

### Cycle progress (`progressed`)

- **Shape**: boolean (`true`/`false`).
- **Computed by**: `Read back cycle outcome` / `Read back retry outcome`,
  from `checked-count` at base and at tip: `progressed = tip_checked >
  base_checked` (D1, FR-010a).
- **Relates to**: gates the FR-010 hand-off. A cycle that ticks one box and
  unticks another still has `tip_checked == base_checked` (or lower) and so
  reads as `progressed=false` — the spec's own conservative reading (edge
  case: "a cycle whose checked count did not rise counts as no progress even
  though a box moved").
- **Scope note**: computed only when the cycle is healthy (`ok=true`) and
  not `truncated` — a truncated cycle's `converged` is already forced
  `false` without running this or the outstanding-task scan (FR-005),
  because the branch state a truncated run leaves may not reflect a
  completed cycle's intent.

### Converge-commit presence (`converge_sha`, pre-existing)

- **Shape**: a commit SHA or empty string.
- **Computed by**: the existing `case "$subject" in converge:*)` scan over
  `git log $BASE..$TIP -- $SPEC_DIR/tasks.md` (unchanged by this feature).
- **Relates to**: one of the two independent reasons `converged` can be
  `false` (the other being outstanding tasks); also one of the two
  conditions the FR-010 hand-off requires be absent (a landed converge
  commit means there *is* new work a later cycle can do — edge case: "a
  cycle that checks no box but whose converge pass appended a phase... is
  not the FR-010 hand-off").

### Convergence signal (`converged`)

- **Shape**: boolean, unchanged in name and type (FR-017).
- **Computed by**: the decision table below, replacing the current
  "no converge commit ⇒ true" rule.
- **Decision table** (evaluated in this order, per FR-010b — zero
  outstanding decides before the progress test is consulted):

  | `ok` | `truncated` | `unchecked-count` (tip) | `converge_sha` | `converged` |
  |---|---|---|---|---|
  | `false` | — | — | — | unset (existing failed/stalled path, unchanged) |
  | `true` | `true` | — | — | `false` (forced, no scan — FR-005, unchanged) |
  | `true` | `false` | `0` | any | `true` (FR-010b: zero outstanding wins regardless of progress or a converge commit) |
  | `true` | `false` | `>0` | non-empty | `false` (converge appended new work — Acceptance Scenario 3/4) |
  | `true` | `false` | `>0` | empty, `progressed=true` | `false`, next cycle dispatched (User Story 1) |
  | `true` | `false` | `>0` | empty, `progressed=false` | `false`, **hand-off** to finalize (FR-010, User Story 4) |

### Non-convergence reason (`reason` narrative)

- **Shape**: free text, assembled (not agent-authored) from the booleans
  above, for the issue comment (FR-013) and the step summary (FR-014).
- **Cases**: "converge appended new work"; "the cycle ended with tasks
  outstanding" (progress made, another cycle follows); "the cycle ended with
  tasks outstanding" **and** "converge appended new work" (both, listed
  without duplicating the task list itself — D6); the FR-010 hand-off
  variant, which additionally states "the cycle checked nothing new, so the
  loop is ending here rather than dispatching another cycle" (FR-013); the
  pre-existing truncated/cap-reached narratives (unchanged).

### Remaining-work text (`remaining`)

- **Shape**: newline-delimited list of literal unchecked task-list lines.
- **Computed by**: the outstanding-item text the checkbox-count composite
  emits for the tip's `tasks.md` (D3), when `converged=false` is driven by
  outstanding tasks (with or without a converge commit) — replacing the
  current `git show $converge_sha -- tasks.md` diff extraction (D6).
- **Validation rule**: FR-012 — MUST NOT be empty whenever `converged=false`
  is driven by outstanding tasks; SC-006 requires every such issue comment
  name its reason and list at least one item.

### Cycle outcome read-back (process, not a value)

- The two call sites — "Read back cycle outcome" (primary) and "Read back
  retry outcome" (retry) — that own this entire decision. FR-007 requires
  they share one definition; this plan achieves that by having both call
  the same composite (D2) and apply the identical decision table above,
  each against its own base (D1's "own base" requirement, matching how the
  retry arm already isolates its own base for the pre-existing progress
  test at truncated-classification time).

## Relationships

```
tasks.md @ base ref ──┐
                       ├─▶ count-tasks-checkboxes.sh ─▶ checked-count(base)
tasks.md @ tip ref ────┤                                checked-count(tip)
                       └─▶ count-tasks-checkboxes.sh ─▶ unchecked-count(tip)
                                                          unchecked-items(tip)

checked-count(base), checked-count(tip) ─▶ progressed (D1)

ok, truncated, unchecked-count(tip), converge_sha, progressed
                                        ─▶ converged (decision table)
                                        ─▶ handoff (ok && !truncated &&
                                                     !converged &&
                                                     converge_sha=="" &&
                                                     !progressed)

converged, handoff, converge_sha, progressed ─▶ reason narrative
unchecked-items(tip) ─▶ remaining text

converged, handoff, ITERATION, MAX_ITERATIONS ─▶ Dispatch next step's branch
                                                   (next cycle | finalize)
```

## State: what does *not* change

- `implement.yml`'s `workflow_call` inputs and outputs (FR-017).
- `max-iterations` and its default of 5, and the cap-reached terminal
  behavior itself (FR-009) — this feature adds one new *path into* that
  terminal behavior (the hand-off), not a new terminal behavior.
- The truncated-cycle classification (Arm A/Arm B, spec 040) — `progressed`
  reuses Arm A's comparison but does not alter when a cycle is classified
  `truncated` vs `failed`.
- `tasks.md`'s own schema — no marker vocabulary, no new heading convention
  (Out of Scope).
