# Contract: Bedrock Model Provider Selection

Governs every published stage that runs Claude agent work (FR-001 through
FR-011). Companion to `specs/010-reusable-pipeline/contracts/credentials.md`,
which this contract extends rather than replaces — the Anthropic
credential rules there are unchanged; this document adds the Bedrock branch
and the precedence between the two.

## New stage inputs (all nine agent-running stages: intake, clarify, plan,
tasks, implement, finalize, cleanup, rebase, watchdog)

| Input | Type | Default | Required |
|---|---|---|---|
| `use-bedrock` | boolean | `false` | never (optional, off by default — FR-005) |
| `aws-role-arn` | string | `""` | only when `use-bedrock: true` (validated at runtime, not declaratively — FR-008) |
| `aws-region` | string | `""` | only when `use-bedrock: true` (validated at runtime, not declaratively — FR-008) |

No `secrets:` additions. No changes to any existing input or secret
(`claude-code-oauth-token`, `anthropic-api-key`, `model` and its per-stage
variants, `max-turns`, `pipeline-repo`, `pipeline-ref`, `default-branch`,
etc.) — this is a strictly additive interface change (research D6).

## Preflight invariant (deterministic, pre-agent) — extends
`contracts/credentials.md`'s existing invariant

Before any agent step in any stage, the shared `wing-commander-preflight`
composite now branches on `use-bedrock`:

1. **`use-bedrock: true`**:
   - The existing Anthropic-credential-empty check (both
     `claude-code-oauth-token` and `anthropic-api-key` absent) is **skipped**
     — Bedrock mode never requires an Anthropic credential (FR-004).
   - If `aws-role-arn` is empty → fail, naming `aws-role-arn` specifically.
   - If `aws-region` is empty → fail, naming `aws-region` specifically.
   - (Both checked; a run missing both is told about both.)
   - No validity probe against AWS — an invalid role ARN or region fails at
     the first `aws-actions/configure-aws-credentials` STS call, still before
     any agent step runs (FR-008: fail clearly, not opaquely; not a silent
     fallback to Anthropic).

2. **`use-bedrock: false` / unset (default)**: unchanged — the existing
   Anthropic-credential-empty check from `contracts/credentials.md` applies
   exactly as it does today (FR-005, SC-002 — zero behavior change for
   adopters who don't opt in).

The check remains a plain shell step in the shared preflight composite — no
agent, no network, cannot itself incur cost (same posture as the existing
Anthropic check).

## AWS credential configuration (new, gated)

When `use-bedrock: true`, each stage job runs `aws-actions/configure-aws-
credentials` (via the new `wing-commander-bedrock-credentials` shared
composite) once per job containing an agent step, using `aws-role-arn` as the
role to assume via OIDC and `aws-region` as the region — no long-lived AWS
secrets, consistent with how the pipeline already avoids long-lived GitHub
tokens in favor of the GitHub App / OIDC patterns (FR-003). This step is a
no-op (does not run) when `use-bedrock` is `false`/unset.

The calling (wrapper) workflow's job must grant `id-token: write` for this to
succeed — the same permission every stage already requires for its own
GitHub-OIDC pipeline-ref resolution (research D7); adopting Bedrock does not
add a new permission requirement beyond what every stage already needs.

## `claude-code-action` wiring

Every existing `anthropics/claude-code-action@v1` call site
(~13 across the nine stages) additionally passes:

```yaml
with:
  use_bedrock: ${{ inputs.use-bedrock }}
```

alongside the existing `claude_code_oauth_token` and `anthropic_api_key`
inputs, which remain wired unconditionally and unchanged (see Precedence,
below). AWS credentials/region reach the action via the ambient job
environment variables `aws-actions/configure-aws-credentials` exports
(`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`,
`AWS_REGION`) — no additional `env:`/`with:` plumbing of the region/keys into
the action call itself.

## Precedence when both an Anthropic credential and `use-bedrock` are supplied

`use-bedrock: true` takes effect — the run uses Bedrock — even if
`claude-code-oauth-token` and/or `anthropic-api-key` are also configured
(FR-010). The pipeline performs no selection logic of its own: all three
values (`use_bedrock`, `claude_code_oauth_token`, `anthropic_api_key`) are
passed through to `claude-code-action` unconditionally, exactly as the two
Anthropic credentials already are today; upstream Claude Code's own Bedrock
mode takes priority when enabled (research D4 — asserted, flagged for
implementation-time verification, not independently re-verified against the
pinned action version during this planning pass since this pass had no
outbound web access).

**Documented rule for adopters** (belongs in docs/adoption.md, written during
implementation, not in this plan-stage contract): *if you set `use-bedrock:
true`, Bedrock is used regardless of whether an Anthropic credential is also
configured.*

## Model identifier pass-through

No new model input. When `use-bedrock: true`, the consumer supplies a
Bedrock-compatible model identifier through each stage's existing `model`
input (or `summary-model`/`diagnose-model`/`propose-fix-model` where those
exist) in place of the default Anthropic model name; the pipeline conveys it
to `claude-code-action` unchanged (FR-006). A missing or Bedrock-incompatible
identifier is expected to surface as a `claude-code-action` invocation error
at the first agent call, not a pipeline-level check — the pipeline does not
parse or validate model identifier syntax for either provider today, and this
feature does not add such validation (pure pass-through, no translation).

## Non-goals (unchanged from `contracts/credentials.md`, restated for this
contract's scope)

- No shared/publisher AWS credentials, proxying, or billing.
- No credential validity/expiry probing for either the Anthropic or the AWS
  path.
- No support for other alternate providers (Vertex, Foundry) — Bedrock only
  (spec Assumption).
- No translation of Anthropic default model tiers to Bedrock equivalents.
- No live, end-to-end Bedrock round-trip test in this repository — deferred
  to a separate consuming repository per the spec's stated scope.
