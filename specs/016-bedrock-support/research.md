# Research: AWS Bedrock Support for Consuming Repositories

## Context recap

Wing Commander publishes nine `workflow_call` stages (`intake`, `clarify`,
`plan`, `tasks`, `implement`, `finalize`, `cleanup`, `rebase`, `watchdog`).
Every agent-running step in every stage calls `anthropics/claude-code-action@v1`
directly (~13 call sites across 9 files; no shared composite wraps the action
call itself). Credential wiring today is two optional secrets
(`claude-code-oauth-token`, `anthropic-api-key`) passed straight through to the
action's `with:` block, gated by a deterministic, agent-free preflight check
(`.github/actions/wing-commander-preflight`) that fails fast if both are
empty (`contracts/credentials.md` in specs/010-reusable-pipeline). No AWS
usage, OIDC-to-AWS pattern, or Bedrock wiring exists anywhere in the repo
today (confirmed by repo-wide search — the only hits are the spec itself and
specs/010's credentials contract, whose "Non-goals" section explicitly defers
Bedrock as "a non-breaking additive input later"). This feature is that
addition.

The spec (specs/016-bedrock-support/spec.md) already resolved its two
[NEEDS CLARIFICATION] markers during the clarify stage (see
checklists/requirements.md notes): (1) AWS config reaches each isolated stage
job via role-ARN + region stage inputs, with `configure-aws-credentials`
(OIDC) run inside each stage — no long-lived AWS secrets; (2) Bedrock model
identifiers are pure pass-through via the existing per-stage `model` inputs.
Both are treated as settled inputs to this plan, not re-litigated here.

## Decisions

### D1: `use_bedrock` is the literal `anthropics/claude-code-action` input name

**Decision**: The pipeline's new stage input is named `use-bedrock` (kebab
case, matching this repo's input-naming convention) and is passed to the
action as `with: use_bedrock: ${{ inputs.use-bedrock }}` (snake_case, matching
the action's own input name).

**Rationale**: The original feature request names the flag literally
(`use_bedrock`), which matches `anthropics/claude-code-action`'s documented
`use_bedrock` boolean `with:` input (parallel to its `use_vertex` input for
Google Vertex) — the action sets `CLAUDE_CODE_USE_BEDROCK` for the underlying
Claude Code CLI and expects AWS credentials/region to already be present in
the job environment (via standard AWS env vars: `AWS_ACCESS_KEY_ID`,
`AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`, `AWS_REGION`). This repo's own
convention names `workflow_call` inputs in kebab-case
(`claude-code-oauth-token`, `pipeline-repo`, `default-branch`) while passing
them into the action's `with:` block under the action's own snake_case names
(`claude_code_oauth_token`) — `use-bedrock` → `use_bedrock` follows the same
mapping.

**Alternatives considered**:
- Naming the stage input `use_bedrock` (matching the action verbatim) —
  rejected, breaks this repo's consistent kebab-case input convention and
  would read as inconsistent next to `claude-code-oauth-token`.
- A generic `model-provider: anthropic|bedrock` enum input instead of a
  boolean — rejected as scope creep beyond what the spec asks for (Assumption:
  "Scope is AWS Bedrock only"); a boolean mirrors the action's own shape
  exactly and is the smallest change that satisfies FR-001/FR-002.

**Decision made without clarification** (spec.md has no marker for this; it's
an implementation-level choice): the exact upstream `claude-code-action`
Bedrock interface (`use_bedrock` input name, reliance on ambient AWS env vars
rather than action-level AWS credential inputs) is asserted from the action's
documented behavior and from the requester's own naming of the flag, not
independently re-verified against the pinned action version in this planning
pass (this environment had no outbound web access during planning). **Action
for implementation**: the first task that wires `use_bedrock` into a stage
workflow must confirm the exact input/env-var contract against the pinned
`anthropics/claude-code-action@v1` release notes/README before the change is
considered done, the same verification posture specs/010's credentials
contract already applies to its API-key path ("implemented and code-reviewed
as first-class; live verification deferred").

### D2: AWS credential configuration is a new shared composite, gated by `use-bedrock`

**Decision**: Add `.github/actions/wing-commander-bedrock-credentials`, a
composite action that runs `aws-actions/configure-aws-credentials` as a single
conditional step (`if: inputs.use-bedrock == 'true'`), taking `use-bedrock`,
`aws-role-arn`, and `aws-region` as inputs. Each stage job invokes it once,
early in the job (immediately after the existing preflight step), before any
agent step. `aws-actions/configure-aws-credentials` exports
`AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`/`AWS_SESSION_TOKEN`/`AWS_REGION` as
job-scoped environment variables, so a single invocation per job is sufficient
even for stages with multiple agent steps in the same job (confirmed:
`implement.yml`'s three `claude-code-action` call sites — primary cycle, opus
retry, haiku progress-comment — all sit inside the single `implement` job).
Stages whose agent steps span more than one job (e.g. `watchdog.yml`'s
`diagnose` and `act` jobs run in separate jobs) need the composite invoked
once per job that contains an agent step — a mechanical, per-job repetition,
not a new mechanism.

**Rationale**: Follows the same "new shared composite living under
`.github/actions/`, resolved from the pipeline's own self-checkout at
`.wing-commander-pipeline/`" convention every other cross-cutting concern in
this pipeline already uses (`wing-commander-preflight`,
`wing-commander-context`, `wing-commander-metrics-summary`) — see the header
comment convention in `wing-commander-context/action.yml`. Gating the
credential step at `if:` inside the composite (rather than duplicating an
`if:` on every call site in every stage workflow) keeps each stage workflow's
own diff to "add three inputs + one composite `uses:` line + one `with:
use_bedrock: ...` line per agent step," matching the size of change FR-002
implies ("exposed consistently across every stage").

**Alternatives considered**:
- Inlining `aws-actions/configure-aws-credentials` directly into each stage
  workflow instead of a composite — rejected: would duplicate the same
  conditional block ~9+ times (once per job with an agent step) with no
  reuse, against this repo's established pattern of factoring cross-cutting,
  non-agent logic into shared composites.
- Folding the AWS credential step into `wing-commander-preflight` itself —
  rejected: preflight's existing contract is "deterministic checks, never a
  side-effecting configuration step" (its own header: "Pure shell — no agent,
  no network"); `configure-aws-credentials` performs a real STS network call
  and mutates the job environment, which is a different responsibility.
  Preflight instead gains the *validation* half (D3 below); the *action* half
  (calling STS) is the new composite.

### D3: Preflight's credential invariant branches on `use-bedrock`

**Decision**: Extend `wing-commander-preflight`'s existing credential-check
step with three new inputs (`use-bedrock`, `aws-role-arn`, `aws-region`) and
this branching rule, replacing the single unconditional Anthropic-credential
check:

- `use-bedrock` is `"true"`: skip the Anthropic-credential check entirely
  (FR-004 — the run must not fail for lack of an Anthropic credential); fail
  with a message naming the specific missing input(s) if `aws-role-arn` and/or
  `aws-region` is empty (FR-008); do not perform a validity probe against AWS
  (same "no probe" posture `contracts/credentials.md` already applies to
  Anthropic credentials — an invalid role/region fails at the first
  `configure-aws-credentials` STS call, still before any billable agent work).
- `use-bedrock` is `"false"`/unset (default): unchanged existing behavior —
  the Anthropic-credential-empty check still applies exactly as today
  (FR-005, SC-002).

**Rationale**: This is the same "deterministic, pre-agent, no-cost" gate the
constitution and specs/010 already established for the Anthropic path
(FR-009); reusing and branching the existing composite keeps exactly one
place that owns "can this stage even start" logic, rather than a second
parallel preflight mechanism.

**Alternatives considered**:
- A brand-new `wing-commander-bedrock-preflight` composite — rejected: would
  duplicate the `fail()` helper and step-summary conventions already in
  `wing-commander-preflight/action.yml` for no benefit; the invariant is a
  branch of the same "what must be configured before an agent can run"
  question, not a new question.

### D4: Precedence (FR-010) needs no pipeline-side selection logic

**Decision**: When both an Anthropic credential and `use-bedrock: true` are
supplied, the pipeline passes all of `use_bedrock`, `claude_code_oauth_token`,
and `anthropic_api_key` through to `claude-code-action` unchanged (exactly as
it already passes both Anthropic secrets through unconditionally today,
letting the action/CLI's own documented precedence resolve which is used).
No new pipeline-side conditional ("if bedrock, don't pass the Anthropic
secrets") is introduced.

**Rationale**: `contracts/credentials.md`'s existing precedent (FR-010's
sibling rule for the two Anthropic credentials) already established the
pattern: "No selection logic exists in the pipeline: Claude Code's own
documented authentication precedence applies." Bedrock mode in Claude Code is
understood to take priority over API-key/OAuth-token auth when
`CLAUDE_CODE_USE_BEDROCK` is set (Bedrock is a distinct auth mode selected
explicitly, not raced against the default path) — extending the same
"pass everything through, let upstream precedence decide" posture avoids the
pipeline growing bespoke provider-arbitration logic it would have to maintain
independent of upstream changes.

**Decision made without clarification**: as in D1, the exact upstream
precedence behavior (Bedrock mode overriding Anthropic auth when both are
configured) is asserted from documented Claude Code behavior, not
independently re-verified in this planning pass. **Action for
implementation**: the acceptance check for FR-010 (both configured → Bedrock
takes effect) must be exercised against the pinned action version — a code-
review-level check, consistent with the "review must confirm" verification
posture `contracts/credentials.md` already applies to its own precedence
rule.

### D5: Model identifiers stay pure pass-through — no new input

**Decision**: No new "Bedrock model" input is introduced. Bedrock-compatible
model identifiers travel through each stage's existing `model` input (and
`summary-model`/`diagnose-model`/`propose-fix-model` where those exist) —
callers simply supply a Bedrock model ID (e.g. an inference-profile ARN or
Bedrock model ID string) in place of the default Anthropic model name when
`use-bedrock` is enabled.

**Rationale**: This is FR-006 verbatim ("pure pass-through... MUST NOT
translate its default Anthropic model tiers to Bedrock equivalents") and
matches the spec's own edge-case resolution. The two hardcoded (non-input)
model literals in `implement.yml` (opus retry at line 580, haiku
progress-comment at line 750) are the one place this repo does NOT already
expose a model as an input; they are out of scope for a "make Bedrock IDs
pass-through-able" change unless a later task decides they also need to
become inputs — flagged here, not resolved, since the spec's Independent Test
for Story 3 only requires that "the set of stages that run an agent" exposes
a consistent enablement surface, and these two literals are secondary
retry/progress paths, not primary per-stage model settings.

**Alternatives considered**: Adding per-stage Bedrock-specific model inputs
(e.g. `bedrock-model`) distinct from `model` — rejected, contradicts FR-006's
explicit "existing per-stage model settings," and would require documenting
two parallel model-input systems adopters must reconcile.

### D6: `use-bedrock`, `aws-role-arn`, `aws-region` are plain `workflow_call` inputs, not secrets

**Decision**: All three new fields are declared under each stage's
`workflow_call.inputs:`, not `secrets:`.

**Rationale**: FR-003 already establishes OIDC role assumption specifically
so "no long-lived AWS secrets are needed" — an IAM role ARN and an AWS region
are identifiers, not credentials (nothing sensitive is disclosed by their
value appearing in workflow logs), matching how `aws-actions/configure-
credentials`'s own examples and this repo's other non-secret identifiers
(`pipeline-repo`, `default-branch`) are modeled as inputs. FR-007 (trusted
configuration only, never inferred from untrusted content) is satisfied by
inputs the same way `model`/`max-turns` already are — inputs only ever
originate from a wrapper's own `with:` block, never from issue/comment text.

**Alternatives considered**: Modeling `aws-role-arn` as a secret for
organizations that prefer obscuring account IDs — rejected as the default;
nothing prevents an adopter from storing the value in a repository secret and
interpolating it into the `with:` block themselves (`with: aws-role-arn:
${{ secrets.AWS_ROLE_ARN }}` works today with a plain string input), so no
pipeline-side `secrets:` entry is needed to support that adopter preference.

### D7: No permission changes needed at the reusable-workflow level

**Decision**: No stage's `permissions:` block changes. `id-token: write` is
already granted at the job level in every stage (used today for the
pipeline-ref OIDC-claim fallback); the same permission covers requesting an
OIDC token for AWS's `sts.amazonaws.com` audience via
`configure-aws-credentials`. GitHub reusable-workflow permission inheritance
means the *calling* (wrapper) workflow's job must already grant `id-token:
write` for the existing GH-OIDC fallback to work at all — so the spec's edge
case ("the caller must grant the workflow `id-token: write` permission") is a
restatement of a constraint that already exists, not a new one this feature
introduces. Documentation should make this explicit so adopters don't think
a *new* permission grant is required.

**Rationale**: Confirmed by reading every stage's job `permissions:` block
(all already list `id-token: write`) and the `id-token: write`-derived OIDC
flow already implemented for pipeline-ref resolution
(`intake.yml`'s "Resolve pipeline ref" step). Two OIDC audiences
(`sts.amazonaws.com` for AWS, `wing-commander-pipeline-ref` for the existing
ref-resolution fallback) can both be requested under the same job-level
`id-token: write` permission — audience is chosen per token request, not per
permission grant.

## Summary of new stage-input surface (applies uniformly to all nine stages)

| Input | Type | Default | Purpose |
|---|---|---|---|
| `use-bedrock` | boolean | `false` | FR-001/FR-005: opt-in flag, passed to `claude-code-action` as `use_bedrock` |
| `aws-role-arn` | string | `""` | FR-003: IAM role assumed via OIDC when `use-bedrock` is true |
| `aws-region` | string | `""` | FR-003/edge case "region-scoped": AWS region for both credential configuration and the Bedrock endpoint |

No changes to `secrets:` blocks; existing `model` (and stage-specific model
variants) carry Bedrock-compatible IDs unchanged (D5); `claude-code-oauth-
token`/`anthropic-api-key` remain as-is (D4).
