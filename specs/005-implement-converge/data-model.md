# Phase 1 Data Model: Implement/Converge Stage — Iterative Build to Convergence

This feature has no application data model — it manipulates one git branch,
GitHub issue comments/labels, and one JSON file, and dispatches two GitHub
Actions workflows. The "entities" below are the ones named in `spec.md`'s Key
Entities section, expressed as their concrete on-disk/on-GitHub
representation.

## Lifecycle record (`specs/NNN-slug/spec-meta.json`)

Durable source of truth for a specification's pipeline position (already
defined by stages 1–3; this stage reads `iteration`/`stage` for its
idempotency guard and is the first stage to write `iteration`).

| Field | Type | Written by this stage? | Notes |
|---|---|---|---|
| `issue` | integer | read only | Lifecycle issue number; resolved from the `workflow_dispatch` input. |
| `spec_dir` | string | read only | `specs/NNN-slug`. |
| `feature_num` | string | read only | `NNN`. |
| `stage` | string | **written** | Set to `"implement"` on the first cycle (transition from `"tasks"`) and left at `"implement"` for every subsequent cycle; set to `"stalled"` only on the exhausted-retry failure path. The hand-off to finalize (converged or not) does not itself change `stage` — that transition (`"implement" → "review"`) belongs to the finalize stage, out of scope here (spec.md Assumptions). |
| `iteration` | integer | **written** | Set to the cycle number just completed at the end of each successful cycle (starts at `1`). This is the field this stage "owns from iteration 1 onward" per the schema's existing description, and the value the idempotency guard keys off. |
| `spec_branch` | string | read only | `spec/NNN-slug`; already set by the plan stage. |

**State transition** (the slice of the full pipeline state machine this
stage is responsible for):

```
"tasks"     ──(cycle 1 completes)───────────────────▶ "implement" (iteration=1)
"implement" ──(cycle N completes, not converged, N<max)▶ "implement" (iteration=N)  [re-dispatch N+1]
"implement" ──(cycle N completes, converged)──────────▶ "implement" (iteration=N)  [dispatch finalize, converged=true]
"implement" ──(cycle N completes, cap reached, not converged)▶ "implement" (iteration=N) [dispatch finalize, converged=false]
"implement" ──(cycle fails, retry also fails / no higher tier)▶ "stalled"
```

Only a run whose observed `(stage, iteration)` matches the next expected
value performs a transition; every other observed combination is treated as
already-handled (idempotency, FR-011) or out of scope for this stage.

## Build-and-reassess cycle (iteration)

One dispatched run of `speckit-5-implement.yml` for a given `spec_dir` and
`iteration` number. Not a persisted entity of its own — its existence is
recorded by the git commits it produces on `spec/NNN-slug` (implement
commit(s), an optional converge commit) and, on success, the `iteration`
value written to `spec-meta.json`. Each cycle is independently auditable via
`git log` on the spec branch (FR-014).

| Attribute | Source |
|---|---|
| `spec_dir` / `issue` / `iteration` | `workflow_dispatch` inputs |
| Implementation commit(s) | Pushed by the agent step, message prefix `implement:` |
| Convergence commit (if any) | Pushed by the agent step, message prefix `converge:`, touches `tasks.md` |
| Model tier used | `vars.SPECKIT_IMPLEMENT_MODEL` or `claude-opus-4-8` (label opt-in or retry escalation) |
| Outcome | `converged` \| `not-converged` \| `failed` (research.md's commit-based signal) |

## Convergence reassessment outcome

Derived, not stored — computed by the deterministic post-agent step by
walking the commit range pushed during the cycle for a `converge:`-prefixed
commit touching `$SPEC_DIR/tasks.md` (research.md). Two possible readings:

| Signal | Meaning | Next action |
|---|---|---|
| No `converge:` commit found | `/speckit-converge` left `tasks.md` unchanged — converged | Dispatch finalize, `converged=true` (FR-004) |
| A `converge:` commit found | `/speckit-converge` appended a `## Phase N: Convergence` section — not converged | Re-dispatch iteration+1, or (cap reached) dispatch finalize, `converged=false` (FR-003/FR-006) |

## Cycle maximum (configuration — repo variable `SPECKIT_MAX_ITERATIONS`)

| Value | Meaning | Default |
|---|---|---|
| unset | Falls back to the default | `5` |
| positive integer | Hard cap on cycles for any one specification | — |

Repository-level only (not per-specification), per `spec.md`'s Assumptions
and `docs/setup.md`'s existing documentation of this variable.

## Implementation model (configuration — repo variable `SPECKIT_IMPLEMENT_MODEL` + `model:opus` label)

| Source | Value | Applies to |
|---|---|---|
| `vars.SPECKIT_IMPLEMENT_MODEL` unset or any value other than an opt-in | `claude-sonnet-5` | Normal cycle default |
| `vars.SPECKIT_IMPLEMENT_MODEL` set to `claude-opus-4-8`, or the lifecycle issue carries `model:opus` | `claude-opus-4-8` | Normal cycle opt-in (FR-009) |
| A cycle's attempt at the resolved tier fails outright (FR-013) | Escalate one rung: `claude-sonnet-5` → `claude-opus-4-8` | Automatic retry, same iteration |
| The failing attempt was already `claude-opus-4-8` | No higher rung | Mark stalled, no retry (research.md) |

## Task list (`specs/NNN-slug/tasks.md`)

Owned by `/speckit-implement` (marks `[ ]` → `[X]` as tasks complete) and
`/speckit-converge` (appends `## Phase N: Convergence` sections, per its
append-only contract) — both unchanged by this feature. This stage's concern
is only detecting *whether* converge appended anything (see above), not the
list's internal structure.

## Lifecycle issue (GitHub issue, unchanged shape from stages 1–3)

This stage's writes:
- **Label**: add `stage:implement` on the first cycle (removing
  `stage:tasks`); on the exhausted-retry failure path, add `stage:stalled`
  (removing `stage:implement`). No label change on ordinary cycle-to-cycle
  progress or on the successful hand-off to finalize (the finalize stage
  owns the `stage:review` transition, per `docs/architecture.md` §Stage 5,
  out of scope here).
- **Comment**: one Haiku-authored progress comment per cycle (FR-008); on
  the cap-reached-without-convergence hand-off, the remaining work from the
  final `converge:` commit's appended tasks (FR-006, SC-005); on the stalled
  path, the failure and manual-restart instructions (FR-013).
