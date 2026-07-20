# Phase 1 Data Model: Configurable Human Review Gates

This feature has no application data model — it manipulates a repository
variable, git branches, GitHub PRs/issues, and one JSON file. The "entities"
below are the ones named in `spec.md`'s Key Entities section, expressed as
their concrete on-disk/on-GitHub representation.

## Review Gate (conceptual — not a stored record)

| Gate | Stage transition it guards | Merges into `main`? | Configurable by this feature? |
|---|---|---|---|
| Gate 1 — Pipeline entry | issue → intake | No (it's a label, not a merge) | No (FR-011, constitution Principle V — NON-NEGOTIABLE) |
| Gate 2 — Spec review | spec-draft PR → intake accepted | Yes | No (FR-011, NON-NEGOTIABLE) |
| **Gate 3 — Plan review** | plan → tasks | No (`plan/NNN-slug` → `spec/NNN-slug`) | **Yes — this feature** |
| (Tasks step, already configurable) | tasks → implement | No (`tasks/NNN-slug` → `spec/NNN-slug`) | Already yes (`003-tasks-stage`); unchanged, unaffected by this feature (FR-003) |
| Gate 4 — Final review | final PR → `main` | Yes | No (FR-011, NON-NEGOTIABLE) |

Only Gate 3's row changes state as a result of this feature. The table itself
is documentation (`docs/architecture.md`), not a runtime record — there is no
"Review Gate" object stored anywhere; it is realized purely by which stage's
`workflow_call` input a wrapper wires to a repository variable (or, for Gates
1/2/4, wires to nothing at all).

## Gate Configuration (repository variable `WING_COMMANDER_PLAN_REVIEW`)

| Value | Meaning | Default |
|---|---|---|
| unset | Gate 3 enabled (`pr`) | Yes (absent variable ⇒ `pr`) |
| `pr` | Gate 3 enabled — plan PR opened, pipeline waits for a human merge | — |
| `auto` | Gate 3 disabled — plan committed directly to the spec branch, tasks stage dispatched automatically | No |
| any other value | Treated as `pr` (FR-008: invalid config MUST NOT weaken a gate); surfaced via `::warning::`, step summary, and a note on the lifecycle issue | — |

Repository-level only (FR-012) — read fresh by the wrapper on every dispatch;
no per-specification override exists or is planned. Independent of
`WING_COMMANDER_TASKS_REVIEW` (FR-003): the two variables are read by two
different workflows and neither is consulted when resolving the other.

## Lifecycle record (`specs/NNN-slug/spec-meta.json`)

Unchanged shape from all prior stages (`001`–`013`); this feature only adds a
new *path* by which the existing `"plan"` value gets written, and reads no
new fields.

| Field | Type | Written by this feature? | Notes |
|---|---|---|---|
| `issue` | integer | read only | Resolved, never created, by the plan stage (unchanged). |
| `spec_dir` | string | read only | `specs/NNN-slug`. |
| `feature_num` | string | read only | `NNN`. |
| `stage` | string | **written** (both modes) | `"spec"` → `"plan"` on success, exactly as today; the `auto` path writes the same value via a direct commit instead of a merged PR. |
| `iteration` | integer | read only | Untouched by the plan stage. |
| `spec_branch` | string | read only/written once | `spec/NNN-slug`; set the same way in both modes. |

**State transition** (the slice of the pipeline state machine this feature's
Gate 3 change is responsible for):

```
"spec" ──(plan PR merged, pr mode — Gate 3 enabled, unchanged)───▶ "plan"
"spec" ──(plan committed directly, auto mode — Gate 3 disabled)──▶ "plan"
```

Both transitions produce the identical `stage: "plan"` end state; only the
mechanism (human merge vs. automatic commit) differs. Everything downstream
of `stage == "plan"` (the tasks stage's own idempotency guard) cannot
distinguish which path produced it, by design — it doesn't need to.

## Plan artifact placement (`specs/NNN-slug/{plan.md,research.md,data-model.md,contracts/,quickstart.md}`)

| `WING_COMMANDER_PLAN_REVIEW` | Where the plan artifacts land | Who commits them | Human action required? |
|---|---|---|---|
| `pr` (default) | `plan/NNN-slug` branch, via a PR targeting `spec/NNN-slug` | The plan-stage agent opens the PR; a human merges it | Yes — merge the plan PR |
| `auto` | Directly on `spec/NNN-slug` | The plan-stage agent, in the same commit as the `spec-meta.json` stage update | No |

In both cases the artifacts are produced and persisted (FR-006) — bypassing
Gate 3 never means skipping plan generation, only skipping the human-merge
step.

## Lifecycle issue (GitHub issue, unchanged shape from prior stages)

This feature's writes, by mode:

- **`pr` mode (unchanged)**: "planning started" comment; on completion, plan
  summary + plan PR link + "merging advances to task generation"; label flip
  to `stage:plan` (via the existing "Verify plan PR and flip stage label"
  step).
- **`auto` mode (new)**: "planning started" comment (same as today); on
  completion, plan summary + confirmation that the plan was committed
  directly and the tasks stage was dispatched automatically because Gate 3 is
  disabled (FR-005); label flip to `stage:plan` (via a new verify-then-flip
  step parallel to the `pr`-mode one, gated on the deterministic artifact
  check in research.md's FR-007 decision).
- **Invalid configuration (either mode)**: an additional note appended to the
  "planning started" comment when `WING_COMMANDER_PLAN_REVIEW` held an
  unrecognized value, naming the bad value and stating Gate 3 defaulted to
  enabled (FR-008).

No new label is introduced — `stage:plan` already exists and means the same
thing regardless of which path produced it.
