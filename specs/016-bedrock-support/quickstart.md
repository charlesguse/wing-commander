# Quickstart: Validating AWS Bedrock Support

Per the spec's stated scope, a live Bedrock round-trip is validated in a
separate consuming repository after this side is implemented. This
quickstart covers what **is** validated in this repository: correct plumbing
of the `use-bedrock` flag and its AWS configuration, and that existing
(non-Bedrock) behavior is unchanged. See `contracts/bedrock-provider.md` for
the full interface and `data-model.md` for field-level validation rules.

## Prerequisites

- A checkout of this repository on the feature branch with the implementation
  applied (new `use-bedrock`/`aws-role-arn`/`aws-region` inputs on all nine
  stage workflows, the extended `wing-commander-preflight` composite, and the
  new `wing-commander-bedrock-credentials` composite — see
  `contracts/bedrock-provider.md`).
- `act` or equivalent local GitHub Actions runner, **or** a scratch repository
  with `id-token: write` permission and an AWS IAM role configured to trust
  GitHub's OIDC provider (only needed for the live-credential scenario below;
  the default-path and preflight-failure scenarios need neither AWS nor a
  live agent call).

## Scenario 1 — Default path is unchanged (Story 2, SC-002)

1. Invoke any stage (e.g. `intake.yml`) as today, with `use-bedrock` left
   unset and a valid `anthropic-api-key` or `claude-code-oauth-token`
   configured.
2. **Expected**: identical behavior to before this feature — preflight
   passes on the Anthropic-credential check exactly as it does today; no
   `wing-commander-bedrock-credentials` step runs (AWS is never touched); the
   agent step's `claude_code_oauth_token`/`anthropic_api_key` wiring is
   unchanged.

## Scenario 2 — Bedrock enabled, AWS configuration missing (FR-008, SC-004)

1. Invoke a stage with `use-bedrock: true` and both `aws-role-arn` and
   `aws-region` left empty (their default).
2. **Expected**: the stage fails in the preflight step, before any agent
   step runs, with a message naming both `aws-role-arn` and `aws-region` as
   missing — not an opaque failure and not a silent fallback to the
   Anthropic path.
3. Repeat with only one of the two missing.
4. **Expected**: the failure message names only the missing one.

## Scenario 3 — Bedrock enabled, no Anthropic credential supplied (FR-004)

1. Invoke a stage with `use-bedrock: true`, valid `aws-role-arn` and
   `aws-region`, and neither `claude-code-oauth-token` nor
   `anthropic-api-key` set.
2. **Expected**: preflight passes (the Anthropic-credential check is skipped
   entirely when `use-bedrock: true`); the run proceeds to the
   `wing-commander-bedrock-credentials` step.

## Scenario 4 — Both an Anthropic credential and Bedrock supplied (FR-010)

1. Invoke a stage with `use-bedrock: true`, valid AWS configuration, **and**
   a valid `anthropic-api-key`.
2. **Expected**: the run proceeds via Bedrock (the `use_bedrock` input is
   still passed to `claude-code-action` unconditionally) — confirm by
   inspecting the uploaded `claude-execution-output.json` artifact / job logs
   for Bedrock-mode indicators, not an Anthropic-API call. This is the one
   scenario whose full confirmation depends on the upstream action's
   documented precedence (research D4) and is expected to be re-checked
   against the pinned `claude-code-action` version during implementation
   review.

## Scenario 5 — Consistency across every stage (Story 3, SC-001)

1. Grep all nine stage workflow files for `use-bedrock`, `aws-role-arn`,
   `aws-region`, and `use_bedrock` — confirm every stage's `workflow_call`
   declares the three inputs and every `anthropics/claude-code-action` call
   site within it passes `use_bedrock: ${{ inputs.use-bedrock }}`.
2. **Expected**: no stage is missing the surface; the enablement mechanism is
   identical everywhere (same input names, same defaults, same preflight
   branch).

## Scenario 6 — Model identifier pass-through (FR-006)

1. Invoke a stage with `use-bedrock: true` and a `model` input set to a
   Bedrock-style identifier (e.g. an inference-profile ARN) instead of the
   default Anthropic model name.
2. **Expected**: the pipeline does not rewrite, validate, or reject the
   value — it reaches `claude-code-action`'s `--model` argument unchanged.
   Any mismatch (wrong/unsupported identifier) surfaces as an error from the
   agent invocation itself, not from a pipeline-side check.

## Out of scope for this repository's validation

- An actual successful Bedrock model response (live AWS Bedrock round-trip)
  — validated in the separate consuming repository referenced by the spec.
- Bedrock inference-profile provisioning, quota, or regional model
  availability — consumer-side AWS configuration, not this pipeline's
  concern.
