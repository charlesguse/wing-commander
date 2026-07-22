# Data Model: AWS Bedrock Support for Consuming Repositories

This feature has no application data store; its "entities" are configuration
values that flow through GitHub Actions `workflow_call` interfaces. This
document specifies their shape, validation rules, and lifecycle, mirroring
the spec's Key Entities section.

## Entity: Model Provider Selection

The per-run, per-stage-invocation choice of which backend serves an agent's
model requests.

| Attribute | Type | Values | Notes |
|---|---|---|---|
| `use-bedrock` | boolean (`workflow_call` input, all 9 agent-running stages) | `true` \| `false` | Default `false` (FR-005). The sole selector — no third value; Vertex/other providers are out of scope (spec Assumption). |
| Active provider | derived, not stored | `anthropic` \| `bedrock` | `bedrock` iff `use-bedrock == true`, regardless of whether Anthropic credentials are also present (FR-010, research D4). Never persisted — recomputed each stage run from the input. |

**Validation rules**:
- No validation on `use-bedrock` itself (a boolean input); its *consequences*
  (below) are what get validated.
- Unset/`false` is a no-op relative to today's behavior — no other field on
  this entity is read (SC-002).

**State transitions**: none — this is a per-invocation value, not a
persisted record. It does not appear in `spec-meta.json` or any other
lifecycle bookkeeping (FR-009: enabling Bedrock changes only the model
provider, not lifecycle state).

## Entity: Bedrock Configuration

The consumer-supplied, trusted configuration required to serve requests
through Bedrock when Model Provider Selection is `bedrock`.

| Attribute | Type | Values | Required when | Notes |
|---|---|---|---|---|
| `aws-role-arn` | string (`workflow_call` input) | AWS IAM role ARN | `use-bedrock == true` | Default `""`. Assumed via OIDC (`aws-actions/configure-aws-credentials`) inside the stage job — never a long-lived secret (FR-003). |
| `aws-region` | string (`workflow_call` input) | AWS region code (e.g. `us-west-2`) | `use-bedrock == true` | Default `""`. Used both for STS role assumption and as the Bedrock endpoint region (edge case: "Bedrock requests are region-scoped"). |
| Model identifier(s) | string (existing `model`/`summary-model`/`diagnose-model`/`propose-fix-model` inputs, unchanged) | Bedrock-compatible model ID/inference-profile identifier | `use-bedrock == true` | No new field — FR-006 pure pass-through through the *existing* per-stage model inputs; the pipeline never inspects or translates the value. |

**Ownership**: Every field here originates only from a `workflow_call`
`inputs:` value set by the consumer's own wrapper workflow — never from issue
or comment text (FR-007). This mirrors how `model`/`max-turns`/`pipeline-repo`
are already trusted-only inputs today.

**Validation rules** (enforced by the extended `wing-commander-preflight`
composite, research D3):
1. If `use-bedrock == true` and `aws-role-arn` is empty → fail, naming
   `aws-role-arn` as the missing input (FR-008).
2. If `use-bedrock == true` and `aws-region` is empty → fail, naming
   `aws-region` as the missing input (FR-008). (Both may be reported together
   if both are missing.)
3. If `use-bedrock == true` and both are present → no further validation;
   an invalid role ARN or region fails at the first
   `aws-actions/configure-aws-credentials` STS call (before any agent step),
   not at preflight — same "no validity probe" posture the existing Anthropic
   credential check already uses.
4. If `use-bedrock` is `false`/unset → none of the above checks run; absence
   of `aws-role-arn`/`aws-region` is not an error (FR-005, SC-002: "no AWS
   configuration is required and none is requested").

**State transitions**: none — evaluated fresh each stage invocation from the
inputs the calling wrapper supplies that run.

## Relationship between the two entities

Bedrock Configuration is only meaningful, and only validated, when Model
Provider Selection's `use-bedrock` is `true`. There is no independent
lifecycle for Bedrock Configuration — it has no existence (and requires no
values) when Bedrock is not selected. This is a 1:1 conditional dependency,
not a separate persisted relationship.
