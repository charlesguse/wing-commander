# Contract: Private-Registry Credentials Reaching Every Stage Job

Governs every one of Wing Commander's published `workflow_call`-only
stage workflows (FR-001 through FR-027) — the 12 lifecycle/maintenance
stages this contract was written against, plus the 13th,
`private-image-dogfood.yml`, added by this same feature (FR-027, research
D10) and bound by the identical mechanism. Companion to
`specs/010-reusable-pipeline/contracts/stage-interfaces.md`'s "Common
inputs" table, whose credential-secret rows this contract amends the
*description* of (reach, not name or type), and to
`specs/038-runner-container-passthrough/contracts/runner-container-
passthrough.md`, whose "Private-registry credentials — FR-009, as corrected
(#227)" section this contract directly supersedes.

**Research D3/D4's live-runner probes are resolved (2026-09-07): FR-026
Outcome 1.** Every section below states, inline, which parts were always
fixed regardless of probe outcome and which were contingent on it.

## Stage inputs and secrets (all 12 published stages: intake, clarify, plan,
tasks, implement, finalize, cleanup, watchdog, pr-conversation, rebase,
auto-update-spec-kit, metrics-persist — research D1)

| Name | Kind | Status | Required |
|---|---|---|---|
| `container-registry-username` | secret | **Unchanged** name, type, and `required: false` (FR-002). Description text updated: reaches every job, not only `verify-image-prerequisites`. | never |
| `container-registry-password` | secret | **Unchanged**, same as above. | never |
| `container-registry-authenticated` | input | **Not added.** Research D3's probe confirmed FR-026 Outcome 1 (2026-09-07) — the preferred, no-new-input path — so this Outcome-2 fallback input never shipped. Documented here only as the road not taken. | n/a |

No other existing input, secret, `permissions:` block, or output of any
stage changes (FR-025). This is fixed regardless of probe outcome.

## Binding mechanism (research D3, D5) — shipped, per P1's measured Outcome 1

Every job in every one of the 12 pre-existing stage files that already
carries `container: { image: ${{ inputs.container-image }} }` (42 jobs, per
research D1), plus the one job of the 13th stage this feature adds
(`private-image-dogfood.yml`'s `dogfood` job, research D10), carries a
`credentials:` sibling key:

```yaml
jobs:
  <job-id>:
    container:
      image: ${{ inputs.container-image }}
      credentials: >-
        ${{
          (secrets.container-registry-username != '' && secrets.container-registry-password != '')
            && fromJSON(format('{{"username":{0},"password":{1}}}', toJSON(secrets.container-registry-username), toJSON(secrets.container-registry-password)))
            || fromJSON('{}')
        }}
```

added unconditionally — no `if:`, no per-job selection, no distinction
between agent-bearing and agent-free jobs (FR-008, User Story 4 acceptance
scenario 1: "which jobs authenticate is not a hidden per-job rule"). Gate 22
(below) checks this byte-for-byte, mirroring how it already checks
`image:`.

**This section shipped because research D3's probe (P1) confirmed that
`fromJSON('{}')` suppresses the login attempt on a public image with no
credentials supplied** (measured 2026-09-07, run 34162867583) — FR-026
Outcome 1, the preferred, no-new-input path. The FR-026 Outcome 2 shape (one
opt-in input gating the whole `container:` value) and Outcome 3
("measured not possible") were the alternatives this section would have
become had P1 failed; neither applies.

**A job whose body is a local `uses: ./.github/workflows/<other>.yml` call
is exempt** — `container:` is illegal on such a job, the same carve-out
Gate 22/7 already apply for `runs-on:`/`environment:`. No job in any of the
12 stages is shaped this way today.

### Why `credentials:` cannot be conditionally absent (research D2, fixed regardless of probe outcome)

Measured by PR #226 (2026-08-21) and issue #227: once `container.credentials`
is written as a YAML key, its resolved value can never legitimately be
`null` or an empty string — both are template errors that stop the job
before its first step, identical in effect regardless of which expression
produces them or whether an image is even named. A non-empty value is
always acted on: GitHub attempts a login whenever `container.image` is
non-empty and `container.credentials` is present with any value, real or
placeholder, and that attempt fails if the value is wrong for the target
registry. **These two facts are why no design that ever resolves
`container.credentials` to `null`/`''` can serve all three shapes of
FR-003, and why this contract's entire premise rests on `{}` — an object
that is present (avoiding the first failure) but has never been measured
against the second.**

### The one open question this contract's viability rests on (research D3)

| Shape | Measured (PR #226, #227) or open |
|---|---|
| `image: ''`, no `credentials:` | Measured: runs, no container. |
| `image: ''`, `credentials:` empty string | Measured: template error. |
| `image: <public>`, `credentials:` placeholder object | Measured: login attempted, fails. |
| `credentials: ${{ fromJSON('null') }}` | Measured: template error, same as empty string. |
| `credentials: ${{ fromJSON('{...}') }}` (populated) | Measured: runs — the mapping may come from an expression, if it is an object. |
| `credentials: ${{ fromJSON('{}') }}` (empty object) on a public image | **Measured 2026-09-07 (research D3, P1.2, run 34162867583): runs clean, no login attempted, image pulled anonymously.** Resolves this contract's viability — FR-026 Outcome 1 ships. |

## Timing invariant — unchanged from specs/038 (research D4, fixed regardless of probe outcome)

A job's `container:` (image and credentials) resolves before any step in
that job runs. Two consequences, both load-bearing:

1. A credential minted by a step inside the stage is always too late — it
   must be minted by the calling wrapper, in a step before its `uses:` call
   (research D4, User Story 3).
2. No step inside the real job can improve a failed pull's error message or
   inspect the image's contents before the job's steps begin — this is why
   `verify-image-prerequisites` (below) exists as a separate job, unchanged
   from specs/038.

## The cross-job masked hand-off (research D4) — measured 2026-09-07, governs FR-013 only

A `uses:`-bodied job cannot carry additional steps, so a wrapper that mints
a cloud-registry credential and then calls a stage needs two jobs. **The
hand-off is safe only in the P2.3 shape**: the mint step does not mask its
own output, and the value is forwarded exclusively as a `secrets:` value
into a `uses:` call, never through a plain step:

```yaml
jobs:
  mint-ecr-credentials:
    runs-on: ubuntu-latest
    permissions:
      id-token: write   # required for the OIDC role assumption
      contents: read
    outputs:
      username: ${{ steps.ecr.outputs.username }}
      password: ${{ steps.ecr.outputs.password }}
    steps:
      - id: ecr
        uses: charlesguse/wing-commander/.github/actions/wing-commander-ecr-credentials@<ref>
        with:
          aws-role-arn: ${{ secrets.ECR_ROLE_ARN }}
          aws-region: us-east-1

  call-plan-stage:
    needs: mint-ecr-credentials
    uses: charlesguse/wing-commander/.github/workflows/plan.yml@<ref>
    with:
      container-image: <account-id>.dkr.ecr.us-east-1.amazonaws.com/<repo>:<tag>
    secrets:
      container-registry-username: ${{ needs.mint-ecr-credentials.outputs.username }}
      container-registry-password: ${{ needs.mint-ecr-credentials.outputs.password }}
```

**FR-012's masking guarantee is demonstrated for this exact shape (research
D4, P2.3, run 34163031595): the value arrives intact and is masked in every
job's log by the callee's own `secrets:` context — no explicit
`::add-mask::` at the mint site.** Masking the value at the mint site
instead (`::add-mask::` before it crosses `needs.*.outputs.*`) was also
measured and found to silently **drop** the value at that boundary (P2/A,
P2.1, P2.2) — not merely redundant, actively unsafe for this hand-off, since
the value never arrives at all. Consuming the value in a plain sibling step
instead of a `secrets:`-bound `uses:` call has no safe variant either
(P2.4: leaks once in that step's own `env:` log header). `wing-commander-
ecr-credentials` (below) is built to the P2.3 shape specifically: it never
masks or prints its own output, relying entirely on the caller forwarding
it as shown above.

## `wing-commander-ecr-credentials` — FR-013 (research D8, P2.3 shape)

| Field | Value |
|---|---|
| Location | `.github/actions/wing-commander-ecr-credentials/action.yml` — published contract, referenced by no stage |
| Inputs | `aws-role-arn` (required), `aws-region` (required), `registry` (optional override) |
| Outputs | `username` (fixed `"AWS"`), `password` (short-lived token; **not** masked at this source — safe only when the caller forwards it as a `secrets:` value into a `uses:` call, per P2.3) |
| Long-lived credential | None required or stored — OIDC role assumption only (`aws-actions/configure-aws-credentials@v4`) |
| Caller-side permission | The adopter's own wrapper job must declare `id-token: write` (for OIDC) — the pipeline requests no new permission for itself (spec Edge Cases) |
| Contract stability | Once shipped, inputs/outputs are maintained as published contract surface (FR-013's own text) — not a convenience that can silently narrow |

## Repository-scoped-token worked example (research D9) — reaches every job, per P1's measured Outcome 1

```yaml
with:
  container-image: ghcr.io/${{ github.repository_owner }}/<private-package>:latest
secrets:
  container-registry-username: ${{ github.actor }}
  container-registry-password: ${{ secrets.GITHUB_TOKEN }}
```

Requires `packages: read` in the calling wrapper job's own `permissions:`
block. No adapter, no extra wrapper job, no long-lived secret — the
no-adapter path FR-023/FR-010/SC-005 all require at least one worked example
of.

## `verify-image-prerequisites` — unchanged role, updated messaging (research D6)

Unchanged from specs/038 (FR-014): runs before any other job's container is
created, pulls the named image, checks the canonical required-tool list,
fails with every missing prerequisite named at once.

**Changed, per P1's measured Outcome 1**:
- The `::warning::` stating credentials "authenticate this check only" is
  removed (FR-015).
- The "exactly one credential supplied" failure message names which secret
  is missing, using the same emptiness check the binding expression
  performs.

**If P1 forces FR-026 outcome 3**: the warning is updated (not removed) to
cite this feature's own recorded evidence instead of #227's, stating the
limitation is still measured to hold.

## PR-time enforcement — Gate 22 amended in place (research D7) — FR-019, FR-020, FR-021

**Gate 22** (`lint-workflows.yml`, unchanged number — added by specs/038,
extended here, not replaced): for every workflow declaring
`on.workflow_call` (derived, never listed — a 13th stage cannot be born
exempt), asserts every job with no local `uses:` carries the exact
`container.credentials` expression from this contract's Binding mechanism
section (or the FR-026-outcome-2 shape, if that is what shipped), verbatim.

**Registered exceptions** (FR-021): `verify-image-prerequisites` is expected
to need one — it must invoke Docker directly on the runner, never inside
its own credentialed container, exactly the same carve-out it already has
for `container:` entirely. Any other deviation carries a registered reason
in Gate 22's own exception table, checked by the same mechanism, never an
undeclared deviation and never a code comment alone (constitution VII, IX).

**Self-test** (FR-020): `verify-gate-22.py` gains one synthetic fixture per
new failure branch this amendment introduces — at minimum: the pre-044
bare `image:`-only shape (now a failure, since credentials must reach every
job); the pre-#227 raw-secrets shape (D2a, still forbidden); a
`credentials:` value present but not matching the exact expression
(drift); and, if FR-026 outcome 2 ships, a job whose new-input-gated
expression is mismatched.

## FR-027 — this repository's own dogfood check (research D10)

One new workflow, scheduled and `workflow_dispatch`-triggered (mirroring
`auto-update-spec-kit.yml`), separate from every lifecycle stage, pulling a
new private GHCR package scoped to this repository through the exact
binding this contract ships, authenticated with `secrets.GITHUB_TOKEN` (or a
repository secret, if needed) — no cloud account or cloud-registry identity
owned by this repository. This repository's own lifecycle stages are not
moved onto this image.

## Non-goals (unchanged from specs/038, restated for this contract's boundary)

- Per-job credential selection within one stage call — one pair per stage
  call, matching `runner`/`container-image`'s existing granularity
  (Assumptions).
- Multi-registry pulls for one image — out of scope (Edge Cases).
- Credential lifecycle management of any kind (minting, refreshing,
  validating) by the pipeline itself — the stage forwards what it is
  handed (Assumptions, FR-024).
- Registries that cannot present a username/password pair — the
  pre-authenticated-runner fallback remains documented for them (Edge
  Cases, FR-023).
