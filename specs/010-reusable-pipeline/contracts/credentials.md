# Contract: Credential Handling

Governs every published stage that runs Claude agent work (FR-003, FR-004,
SC-005; spec clarification session 2026-07-11).

## Accepted credentials

| Secret (stage interface name) | Source | Plan type |
|---|---|---|
| `claude-code-oauth-token` | `claude setup-token` | Claude subscription (Pro/Max/Team/Enterprise) |
| `anthropic-api-key` | Claude Console | Metered API billing |

Both are declared optional in every agent stage's `workflow_call` signature;
the invariant below makes exactly-zero an error.

## Preflight invariant (deterministic, pre-agent)

Before any agent step in any stage:

1. If **both** secrets are empty/absent → the job fails with a message naming
   both exact secret names and stating that exactly one is sufficient, e.g.:
   > No Claude credential configured. Add one of these repository secrets and
   > pass it to the stage: `claude-code-oauth-token` (from `claude setup-token`,
   > subscription plans) or `anthropic-api-key` (from the Claude Console).
   > See docs/adoption.md#credentials.
2. If at least one is present → proceed. No validity probe is performed
   (an invalid credential fails at the first agent call, still before any
   successful billable work).

The check is a plain shell step in the shared preflight composite — no agent,
no network, cannot itself incur cost.

The same composite carries the pipeline's supported spec-kit version as a
`SPECKIT_SUPPORTED_VERSION` constant declared at the top of its `action.yml`
(updated whenever the constitution's spec-kit pin changes); it is the reference
value for the best-effort version-mismatch warning (research D7).

## Precedence when both are configured

Both secrets are passed through to `anthropics/claude-code-action`
(`anthropic_api_key` and `claude_code_oauth_token` inputs). No selection logic
exists in the pipeline: Claude Code's own documented authentication precedence
applies, in which `ANTHROPIC_API_KEY` outranks `CLAUDE_CODE_OAUTH_TOKEN`.

**Documented rule for adopters** (must appear in docs/adoption.md): *if you
configure both, the API key is used.* Link to the upstream precedence
documentation (code.claude.com/docs/en/authentication#authentication-precedence).

## Verification posture

- OAuth path: continuously verified — this repository's dogfooded runs use it.
- API-key path: implemented and code-reviewed as first-class; live verification
  deferred to adopter feedback (spec clarification). Review must confirm both
  action inputs are wired in every agent stage and the preflight accepts
  API-key-only configuration.

## Non-goals

- No shared/publisher credentials, proxying, or billing (spec assumption 6).
- No credential validity/expiry probing in preflight.
- No support here for Vertex/Foundry credentials (out of scope for v1; would
  be a non-breaking additive input later). Bedrock support has since been added
  as exactly such a non-breaking additive input — see
  [`specs/016-bedrock-support/contracts/bedrock-provider.md`](../../016-bedrock-support/contracts/bedrock-provider.md).
