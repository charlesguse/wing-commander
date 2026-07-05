# Phase 1 Data Model: Plan Stage

This feature has no application data model — its "entities" are the git/GitHub
objects the pipeline creates and reads. This document specifies their shape
and the state transitions this stage is responsible for.

## Entity: Lifecycle record (`specs/NNN-slug/spec-meta.json`)

The durable, machine-readable source of truth for a specification's pipeline
state. Committed to the persistent `spec/NNN-slug` branch.

| Field | Type | Description |
|---|---|---|
| `issue` | integer \| null | Lifecycle issue number. `null` only for a hand-submitted spec before this stage creates one (FR-007). |
| `spec_dir` | string | `specs/NNN-slug` — repeated here for self-description. |
| `feature_num` | string | `NNN`, zero-padded feature number. |
| `stage` | enum: `spec` \| `plan` \| `stalled` \| `tasks` \| `implement` \| `review` \| `done` | Current pipeline stage. This feature writes `plan` (FR-005) or `stalled` (FR-012). |
| `iteration` | integer | Implement⟲converge iteration counter; untouched by this stage. |
| `spec_branch` | string \| null | `spec/NNN-slug`. This feature sets it the first time the persistent branch is created/confirmed. |

**State transitions owned by this stage**:

```
stage: "spec"    --[plan PR opened]-->     stage: "plan"
stage: "plan"    --[plan PR closed         stage: "stalled"
                   without merging]-->
stage: "stalled" --[maintainer deletes
                   plan/NNN-slug and
                   dispatches workflow]-->  stage: "plan"   (manual, FR-012)
```

No other stage's fields are read or written by this feature beyond `issue`,
`stage`, and `spec_branch`.

## Entity: Persistent working branch (`spec/NNN-slug`)

Long-lived, created once per specification from `main` at the moment its
draft spec PR merges. Never deleted by this stage (cleanup is stage 6's
concern). Reused, not recreated, by every later stage (tasks, implement,
finalize) — see spec.md Assumptions.

| Property | Value |
|---|---|
| Created from | `main`, at the merge commit of the draft spec PR |
| Created by | This stage, if it doesn't already exist (FR-002) |
| Naming | `spec/<feature_num>-<slug>` |
| Lifetime | Survives across plan → tasks → implement → finalize |

## Entity: Plan work branch (`plan/NNN-slug`)

Short-lived branch holding the generated plan artifacts, opened as a PR
against `spec/NNN-slug`. Its existence is also this stage's de-duplication
signal (FR-009) — see research.md §3.

| Property | Value |
|---|---|
| Created from | `spec/NNN-slug` |
| Contains | `plan.md`, `research.md`, `data-model.md`, `contracts/`, `quickstart.md`, updated `spec-meta.json`, and any agent-context file update |
| Merged into | `spec/NNN-slug` (human gate) |
| On merge | Stage 3 (tasks) picks up from `spec/NNN-slug` |
| On close without merge | This stage's `stalled` job runs (FR-012) |

## Entity: Implementation plan (plan artifact)

The set of files listed above as "Contains." Not a single file — `plan.md` is
the entry point; `research.md`, `data-model.md`, `contracts/*`, and
`quickstart.md` are its supporting artifacts, per the existing
`/speckit-plan` skill's Phase 0/Phase 1 outputs. This feature does not change
their internal structure, only when/how they are generated and delivered.

## Entity: Plan pull request

| Property | Value |
|---|---|
| Head | `plan/NNN-slug` |
| Base | `spec/NNN-slug` (never `main` — FR-004) |
| Title | `Plan: <feature name> (#<issue>)` |
| Body | Technical approach summary, generated artifacts, constitution-check outcome, "Decisions made without clarification" (omitted if none), `Lifecycle issue: #<issue>` |
| Created by | The `speckit-bot` App identity, via `gh pr create` |
| Merge/approve | Never performed by the bot (FR-008) — human reviews and merges |

## Entity: Lifecycle issue (GitHub issue)

Not created by this feature in the common case (stage 1 creates it); this
feature only creates one for the hand-submitted path (FR-007) and otherwise
updates it.

| Property | This stage's effect |
|---|---|
| Labels | Adds `stage:plan` (creating it if missing); removes `stage:spec`/`stage:clarify` if present (best-effort). For hand-submitted specs, also creates/attaches `spec:NNN-slug` first. |
| Comments | One comment: plan summary + plan PR link (FR-006), added only after the plan PR is verified to exist. |
| Created by (hand-submitted only) | Title `Lifecycle: <feature name>`, body noting it was auto-created by the plan stage. |
