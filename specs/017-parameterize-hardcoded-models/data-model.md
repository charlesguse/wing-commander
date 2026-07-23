# Phase 1 Data Model: Parameterize Hardcoded Models

This feature has no runtime data store; its "entities" are configuration
concepts realized as GitHub Actions `workflow_call` inputs and repository
Variables. This document specifies their fields, relationships, and
validation rules per spec.md's Key Entities section.

## Entity: Task Tier

A grouping of pipeline stages/code paths by task weight (constitution II),
to which exactly one Model Override Point applies.

| Field | Description |
|---|---|
| `name` | One of: `spec/clarify`, `plan/tasks`, `triage/summary`, `implement`, `implement/escalation` |
| `default_model` | The model identifier this tier resolves to when unconfigured |
| `member_locations` | The executable code paths whose model selection this tier governs |

| Tier | Default model | Member locations |
|---|---|---|
| `spec/clarify` | `claude-opus-4-8` | `intake.yml` (spec drafting), `clarify.yml` (clarification Q&A) |
| `plan/tasks` | `claude-sonnet-5` | `plan.yml` (planning), `tasks.yml` (task generation), `rebase.yml` (conflict resolution) |
| `triage/summary` | `claude-haiku-4-5` | `cleanup.yml` (completion summary), `finalize.yml` (completion summary), `watchdog.yml` (diagnose step), `implement.yml` (progress-comment step) |
| `implement` | `claude-sonnet-5` (or `claude-opus-4-8` via `model:opus` issue label) | `implement.yml` (primary build/converge attempt), `watchdog.yml` (propose-fix step) |
| `implement/escalation` | `claude-opus-4-8` | `implement.yml` (retry attempt after a failed primary attempt) |

**Relationships**: A Task Tier has exactly one Model Override Point (1:1). A
Task Tier has one-to-many Member Locations. A Member Location belongs to
exactly one Task Tier (no location is dual-tiered — this is what keeps
FR-006's independence property true: overriding one tier's variable cannot
partially affect a location governed by a different tier).

**Validation rules**: Every executable model selection in the pipeline's
GitHub Actions workflows MUST belong to exactly one Task Tier (SC-001,
FR-001). No Task Tier's `default_model` may change as part of this feature
(FR-002, FR-005).

## Entity: Model Override Point

A named, per-tier configurable setting — a repository Variable in the
consuming repository — that determines which model the code paths in a given
Task Tier select.

| Field | Description |
|---|---|
| `variable_name` | The `vars.*` repository-variable name a consumer sets |
| `tier` | The Task Tier this override point governs (1:1 with Task Tier) |
| `default_value` | Value used when the variable is unset or blank |
| `wired_workflow_inputs` | The `workflow_call` input(s) this variable's resolved value is passed into |
| `resolution_mechanism` | How the wrapper computes the effective value from the variable |

| `variable_name` | `tier` | `default_value` | `wired_workflow_inputs` | `resolution_mechanism` |
|---|---|---|---|---|
| `WING_COMMANDER_SPEC_MODEL` | `spec/clarify` | `claude-opus-4-8` | `intake.yml:model`, `clarify.yml:model` | Wrapper inline: `${{ vars.WING_COMMANDER_SPEC_MODEL \|\| 'claude-opus-4-8' }}` |
| `WING_COMMANDER_PLAN_MODEL` | `plan/tasks` | `claude-sonnet-5` | `plan.yml:model`, `tasks.yml:model`, `rebase.yml:model` | Wrapper inline: `${{ vars.WING_COMMANDER_PLAN_MODEL \|\| 'claude-sonnet-5' }}` |
| `WING_COMMANDER_SUMMARY_MODEL` | `triage/summary` | `claude-haiku-4-5` | `cleanup.yml:summary-model`, `finalize.yml:summary-model`, `watchdog.yml:diagnose-model`, `implement.yml:summary-model` | Wrapper inline for cleanup/finalize/implement; direct `vars.*` read inside `watchdog.yml` (D4) |
| `WING_COMMANDER_IMPLEMENT_MODEL` *(existing)* | `implement` | `claude-sonnet-5` (label escalation → `claude-opus-4-8`) | `implement.yml:model`, `watchdog.yml:propose-fix-model` | Existing `resolve-model` job (label-aware) for implement; direct `vars.*` read inside `watchdog.yml` for propose-fix (no label logic) |
| `WING_COMMANDER_IMPLEMENT_ESCALATION_MODEL` | `implement/escalation` | `claude-opus-4-8` | `implement.yml:escalation-model` | Wrapper inline (extends `wing-commander-5-implement.yml`'s existing job): `${{ vars.WING_COMMANDER_IMPLEMENT_ESCALATION_MODEL \|\| 'claude-opus-4-8' }}` |

**Validation rules** (from spec.md Edge Cases and Functional Requirements):

- **Blank/empty override** (FR-009): if `vars.<NAME>` is unset OR set to an
  empty string, the `||` fallback in the wrapper expression resolves to
  `default_value` — GitHub Actions expressions treat `''` as falsy for `||`,
  so this is a single mechanism covering both "unset" and "blank."
- **Independence** (FR-006): each override point's resolution is a pure
  function of its own variable (plus, for `WING_COMMANDER_IMPLEMENT_MODEL`
  only, the pre-existing `model:opus` issue label) — no override point's
  resolution reads another override point's variable.
- **Default reproduction** (FR-002, FR-005): `default_value` for every row
  above equals the value the corresponding literal or input default already
  produces today; this is the acceptance bar for Phase 2 (tasks.md) and
  implementation, not a new value chosen by this plan.
- **Discoverability** (FR-007, SC-005): every row's `variable_name` and
  `default_value` MUST appear in `docs/setup.md`'s repository-variables table
  (D6) — this is the single source a reviewer reads to enumerate all
  override points without inspecting workflow internals.

## Entity: Default Model Value

The value an override point resolves to when the consumer supplies nothing.
Not a separate stored entity — it is the `default_value` field of Model
Override Point and, redundantly during the transition, the `default:` on the
corresponding `workflow_call` input (both must agree; `contracts/model-override-points.md`
states this as an explicit contract clause). Existing outside this feature's
scope: `WING_COMMANDER_IMPLEMENT_MODEL`'s current default and label-escalation
behavior are unchanged.

## State / lifecycle

None of these entities have state transitions — they are static
configuration resolved once per workflow run, at the point the wrapper
workflow evaluates its `with:` block (before any job starts). There is no
runtime mutation, caching, or persistence beyond the GitHub Actions run
itself.
