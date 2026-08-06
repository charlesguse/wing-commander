# Data Model: Bind Pipeline Stages to a Deployment Environment

This feature has no application data store; its "entities" are configuration
values that flow through GitHub Actions `workflow_call` interfaces, plus one
entity (Deployment environment) that is owned entirely by GitHub and the
adopter's own repository, never by this pipeline. This document specifies
their shape, validation rules, and lifecycle, mirroring the spec's Key
Entities section.

## Entity: Deployment environment

A GitHub-native, per-repository named scope, owned and stored entirely by
the adopter's own repository — **not modeled, stored, or created by this
pipeline in any form.**

| Attribute | Type | Notes |
|---|---|---|
| Name | string | Case-insensitive, unique per repository, capped at 255 characters, no character restrictions (spec Key Entities). |
| Protection rules | GitHub-native, adopter-configured | Required reviewers, wait timer, deployment branch/tag policy, custom (GitHub App) rules. The pipeline never reads, sets, or reasons about these — GitHub alone evaluates them (FR-006). |
| Existence | created on first reference | A name that doesn't already exist is auto-created by GitHub with no protection rules the first time a job's `environment:` names it (verified behavior, research D2 item 4) — not an error, not validated (FR-007). |

**Validation rules**: none performed by this pipeline (FR-007 — explicitly
pass-through, no existence check, no allowlist).

**State transitions**: entirely GitHub's own (environment lifecycle,
protection-rule configuration, deployment history) — out of this pipeline's
model and out of this feature's scope to track.

## Entity: Environment input (per stage invocation)

The optional `workflow_call` input a wrapper sets to name the environment a
given call of a given stage should bind to.

| Attribute | Type | Values | Notes |
|---|---|---|---|
| `environment` | string (`workflow_call` input, all 10 published stages) | any string, or `""` | Default `""` (FR-001). `""` means no binding — a verified true no-op (research D2 item 1), not a sentinel requiring pipeline-side branching. |
| Active binding | derived, not stored | bound to `environment`'s value \| unbound | Unbound iff `environment == ""`. Never persisted — recomputed fresh every stage invocation from the input, exactly as GitHub itself re-evaluates the job's `environment:` key on every run. |

**Validation rules**:
- None on the input itself (FR-007) — no existence check, no format check,
  no allowlist. GitHub's own create-on-reference behavior is the only
  "validation" that occurs, and it never fails the run.
- Unset/`""` is a no-op relative to today's behavior — no other field on this
  entity, and no field of Deployment-record control, is consulted when
  `environment` is empty (SC-001; research D2 item 1 confirms this holds
  even when `environment-deployment` is simultaneously non-default).

**State transitions**: none — a per-invocation value, not a persisted
record. It does not appear in `spec-meta.json` or any other lifecycle
bookkeeping (spec edge case: "no other new artifact appears anywhere in the
repository").

**Ownership**: originates only from a `workflow_call` `inputs:` value set by
the consumer's own wrapper workflow's `with:` block — never from
`github.event.*`, `vars.*`, issue/comment text, or any other ambient state
(FR-011, constitution VII). This mirrors how `model`/`max-turns`/
`pipeline-repo` are already trusted-only inputs today.

## Entity: Deployment-record control (per stage invocation)

The optional `workflow_call` input controlling whether a bound job creates a
GitHub deployment record.

| Attribute | Type | Values | Notes |
|---|---|---|---|
| `environment-deployment` | boolean (`workflow_call` input, all 10 published stages) | `true` \| `false` | Default `true` (FR-002), mirroring GitHub's own default for a bound job. |
| Deployment record created? | derived, not stored | yes \| no | `true` (default) → yes, every protection-rule type works including custom App rules that require the deployment object (FR-002). `false` → no, but the environment's protection rules still apply (FR-008) — GitHub's own `deployment: false` mapping key (research D2 item 3), not pipeline logic. |

**Validation rules**: none on the input itself (a boolean). Its only effect
is meaningful when `environment` is non-empty; when `environment == ""` the
whole binding is a no-op and this field's value has no observable effect
(research D2 item 1 — verified for both string and mapping forms, so this
holds regardless of `environment-deployment`'s value).

**State transitions**: none — evaluated fresh each stage invocation from the
inputs the calling wrapper supplies for that run.

## Relationship between the entities

Environment input and Deployment-record control are independent
`workflow_call` inputs, but Deployment-record control is only *meaningful*
when Environment input is non-empty — there is no independent lifecycle for
"suppress the deployment record" when there is no environment to bind in the
first place. Both map onto a single GitHub-native Deployment environment,
which the pipeline never models beyond passing its name and the
deployment-record flag through unvalidated. This is a 1:1:1 conditional
composition (binding → environment → GitHub's own protection-rule
evaluation), not a persisted relationship of any kind.
