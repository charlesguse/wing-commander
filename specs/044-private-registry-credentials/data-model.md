# Data Model: Private-Image Credentials That Reach Every Stage Job

This feature has no application data store; its "entities" are
configuration values that flow through GitHub Actions `workflow_call`
interfaces, plus GitHub-native container/credential concepts this pipeline
never stores. This document specifies their shape, validation rules, and
lifecycle, mirroring the spec's Key Entities section and
specs/038-runner-container-passthrough's data-model.md structure — the
container-image entity itself is unchanged from specs/038 and is not
restated here beyond what this feature touches.

## Entity: Registry credential pair

The username and password a stage's jobs use to pull a private image.

| Attribute | Type | Notes |
|---|---|---|
| `container-registry-username` | secret (`workflow_call` secret, all 12 published stages, `required: false`) | Unchanged from specs/038 — a static registry username, or a fixed value a cloud registry's docker-login convention expects (e.g. ECR's literal `AWS`). |
| `container-registry-password` | secret (`workflow_call` secret, all 12 published stages, `required: false`) | Unchanged from specs/038 — a static password, or a short-lived token minted by the calling wrapper before the stage's job starts (research D4). |
| Reach | **changed by this feature** | Was: authenticates `verify-image-prerequisites` only (post-#227 state). Becomes (contingent on research D3's probe): authenticates every job of the stage that carries the container binding — the same granularity as `runner`/`container-image` (FR-008). |
| Inertness | derived, unchanged in effect, changed in mechanism | Inert whenever `container-image` is empty (FR-006) and whenever exactly zero or both secrets are supplied identically-empty for a non-empty image alongside no real credential (FR-005) — previously achieved by the key's total absence from `container:`; now achieved by the amended expression resolving to `fromJSON('{}')` (research D3/D5), pending that value being proven inert by the probe. |
| Opacity | unchanged | The pair is opaque to the stage: it never learns who issued it or how long it lives (spec Key Entities). |

**Validation rules**: none performed by the pipeline on the credential
values themselves, except the existing `verify-image-prerequisites` pull
attempt (unchanged role, FR-014) and its sharpened "exactly one supplied"
message (FR-007, research D6). The per-job expression (research D5) performs
only an emptiness check (`!= ''`), never a format or correctness check.

**State transitions**: none — resolved fresh per invocation, never
persisted, never logged (GitHub's own `secrets.*` masking, unchanged from
specs/038 — no new masking code for the static-pair path; the *dynamic*,
cross-job-minted path is the one masking guarantee this feature must
demonstrate rather than assume, per research D4/FR-012).

**Ownership**: unchanged from specs/038 — arrives only via the calling
wrapper's own `secrets:` block, never `secrets: inherit`, never derived from
`github.event.*`/`vars.*` read by the stage itself.

## Entity: Container binding

What a stage job declares about where it runs and what it runs inside.

| Attribute | Type | Notes |
|---|---|---|
| `runs-on` | unchanged from specs/038 | Not touched by this feature. |
| `container.image` | unchanged from specs/038 | `${{ inputs.container-image }}` on every job — not touched by this feature. |
| `container.credentials` | **new value, same key position** | Was: absent from every job (post-#227 fix). Becomes: the amended expression from research D5, present on every job unconditionally, resolving to `{}` (inert) or a real `{username, password}` object depending on whether both secrets are non-empty — contingent on research D3's probe confirming `{}` is treated as inert rather than as a failed or malformed login attempt. |
| `container-registry-authenticated` (provisional) | **new input, added only under FR-026 outcome 2** | If research D3's probe rules out inferring the shape from secret presence alone, this one opt-in input (string, `"true"`/`"false"`, default `"false"`) gates which of two whole `container:` shapes a job uses. Not added at all under the preferred outcome 1. |
| Uniformity | unchanged in principle, extended in scope | Must be identical across every job of a stage (FR-008) — Gate 22 (research D7) extends its existing uniformity check from `image:` alone to include the new `credentials:` expression (and the new input's binding, if it ships). |

**Validation rules**: none on the adopter's values (FR-008's pass-through
principle, unchanged from specs/038). Gate 22 validates the *pipeline's own*
shape (every job's expression matches exactly), never the adopter's
credential values.

**State transitions**: none — a per-invocation value, recomputed fresh every
stage invocation, never persisted to `spec-meta.json` or any other lifecycle
record.

**Ownership**: unchanged from specs/038 — `runner`/`container-image` from
the calling wrapper's `with:` block, the two secrets from its `secrets:`
block, and (if it ships) the new opt-in input from `with:` alongside them.

## Entity: Caller-side minting step

The work an adopter performs before a stage call to produce a credential
their registry will accept.

| Attribute | Type | Notes |
|---|---|---|
| Timing | structural, unchanged from specs/038 D4 | Must complete before the stage's job's `container:` resolves — i.e., before the stage's `uses:` call, in a step of the *caller's own* job. |
| Job-boundary requirement | **new to this feature** | A job whose body is `uses: <reusable workflow>` cannot carry additional steps of its own (documented GitHub constraint, not a probed one) — so a minting step that must run "before the stage call" and a stage call that is itself a whole job body cannot share one job. The credential must be minted in a separate job and cross a `needs.<job>.outputs.*` boundary (research D4) into the calling job's `secrets:` block. |
| Masking guarantee across that boundary | **unverified, blocking (research D4/P2)** | FR-012 requires this be demonstrated, not assumed, before `wing-commander-ecr-credentials` (below) ships. |
| Ownership | unchanged from specs/038 | The adopter's own wrapper; the pipeline supplies the pattern (and, now, an optional component), never the execution. |

**Validation rules**: none — the pipeline neither validates nor inspects a
minted credential's shape or freshness (spec Assumptions: "the stage never
manages a credential's lifecycle").

**State transitions**: none — minted once per wrapper run, consumed once by
the stage call it precedes, never refreshed or retried by the pipeline
(documented lifetime contract, FR-024).

## Entity: Provider adapter (`wing-commander-ecr-credentials`)

A supported, versioned, optional component for one registry family (AWS
ECR), turning an adopter's cloud identity into a username/password pair.

| Attribute | Type | Notes |
|---|---|---|
| Inputs | `aws-role-arn` (required), `aws-region` (required), `registry` (optional override) | Minimal contract fixed by FR-013's own text; see research D8 for the full `action.yml`. |
| Outputs | `username` (fixed `"AWS"`), `password` (short-lived token, masked) | **New relative to the precedent component** (`wing-commander-bedrock-credentials`, which has no `outputs:` at all) — required because this component's result must cross a job boundary (Caller-side minting step, above), unlike Bedrock's same-job environment-variable pattern. |
| Location | `.github/actions/wing-commander-ecr-credentials/` — published contract surface (constitution VII), referenced by no stage | Optional, edge-located, additive; an adopter who does not use it is unaffected by its existence (FR-013). |
| Ships only after | research D4's probe (P2) confirms the masked hand-off is safe | Not released speculatively — the whole component exists to serve a hand-off this feature must first prove is safe. |
| Long-lived credential requirement | none — MUST NOT require the adopter to store one (FR-013) | OIDC role assumption (`aws-actions/configure-aws-credentials@v4`) is the only identity input; the adopter's own repository declares the trust policy that permits it, entirely outside this pipeline (spec Edge Cases: "a caller-side permission the caller must grant"). |

**Validation rules**: none performed by the pipeline beyond what
`aws-actions/configure-aws-credentials`/`aws ecr get-login-password`
themselves enforce (a real AWS OIDC trust failure surfaces as their own
error, not a pipeline-authored one).

**State transitions**: none — minted fresh per invocation of the wrapper
job that calls it, never cached or reused across runs.

**Ownership**: the adopter's own AWS account and OIDC trust policy; this
pipeline stores nothing about either (constitution VI).

## Entity: Prerequisite check (`verify-image-prerequisites`)

Unchanged role and placement from specs/038 (FR-014): runs before any other
job's container is created, pulls the named image, checks it for the
canonical required-tool list.

| Attribute | Type | Notes |
|---|---|---|
| Warning about credential reach | **removed, contingent on research D3/D5 landing on FR-026 outcome 1 or 2** | FR-015: once credentials genuinely reach every job, the warning stating they reach only this check is false and must go, along with every document repeating the same claim (FR-023, SC-009). |
| Warning, alternative branch | **updated, not removed, if research D3 forces FR-026 outcome 3** | Continues to state the limitation, now citing this feature's own probe evidence rather than #227's, so a future reader does not re-propose the same idea unread (research D6). |
| "Exactly one credential supplied" message | **sharpened** | Names which of the two secrets is missing (FR-007), using the same emptiness check the per-job binding expression already performs (research D5/D6) — a messaging change, not a new check. |
| Required-tool list | unchanged from specs/038 | Not touched by this feature (spec Assumptions). |

## Entity: Probe evidence

The recorded results of exercising the candidate mechanism on real hosted
runners, across all three shapes of FR-003 and the cross-job masking
question of FR-012, before any stage file is changed (FR-016).

| Attribute | Type | Notes |
|---|---|---|
| P1 (research D3) | Blocking, not yet run | Whether `container.credentials` resolving to `{}` suppresses a login attempt — decides FR-026's outcome. |
| P2 (research D4) | Blocking, not yet run | Whether a masked value crossing a `needs.<job>.outputs.*` boundary into a `uses:`-call's `secrets:` stays masked — decides whether FR-013 ships as designed. |
| Recording location | `research.md`, replacing the "Blocking prerequisite for tasks.md" section once run | Mirrors specs/038's PR #226 evidence, later recorded into its own contract document. |
| Consequence of a negative result | Recorded, not discarded (FR-017) | A rejected candidate and its measured reason stay in `research.md` so a future feature does not re-propose it unread — exactly how this feature itself treats D2a/D2b from #226/#227. |

## Relationship between the entities

Registry credential pair and Container binding compose exactly as they did
under specs/038: the pair is meaningful only when the image is non-empty,
and (new to this feature, contingent on the probe) the pair's presence
alone — no adopter-visible declaration beyond the two secrets — now decides
whether the credential reaches the job, rather than only the prerequisite
check. Caller-side minting step and Provider adapter are new-to-this-feature
concepts that exist only for the cloud-registry (ECR) path; a static-pair
registry (Assumption, FR-010) needs neither. Probe evidence gates all of the
above: no other entity's design in this document is treated as final until
its corresponding probe (P1 for the binding, P2 for the adapter's hand-off)
is recorded.
