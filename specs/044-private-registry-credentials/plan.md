# Implementation Plan: Private-Image Credentials That Reach Every Stage Job

**Branch**: `044-private-registry-credentials` | **Date**: 2026-09-07 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/044-private-registry-credentials/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

specs/038 gave every published stage a `container-image` input and two
optional secrets, `container-registry-username`/`container-registry-password`,
but the credentials never reached a stage's real jobs: issue #227 measured
(PR #226, real GitHub-hosted runners) that a job's `container.credentials`
key can never be conditionally absent — an empty value is a template error
that stops every ordinary run, and a non-empty value is always acted on, so
it fails a public image's pull. The fix that shipped (#228) kept `image:` on
every job's `container:` block and removed `credentials:` entirely, so today
the two secrets authenticate only `verify-image-prerequisites` — a fact
`docs/adoption.md` and the job's own warning both state as a hard limitation.

This plan closes that gap without repeating #224/#227: it does not touch a
stage file until a live probe on real GitHub-hosted runners has answered the
one question #227 left open — whether `container.credentials` can be given a
value that is present (never absent, avoiding the template error) but
inert (never triggers a login attempt, avoiding the public-image failure).
The candidate is a per-job expression that resolves `credentials` to a
genuinely **empty JSON object** (`{}`, not `null`, not a placeholder string)
whenever the adopter's two secrets are not both non-empty, and to a real
`{username, password}` object when they are:

```yaml
container:
  image: ${{ inputs.container-image }}
  credentials: >-
    ${{
      (secrets.container-registry-username != '' && secrets.container-registry-password != '')
        && fromJSON(format('{{"username":{0},"password":{1}}}', toJSON(secrets.container-registry-username), toJSON(secrets.container-registry-password)))
        || fromJSON('{}')
    }}
```

Round 2 of PR #226 already proved the `null` variant of this fails (a
template error, indistinguishable from an empty string); it never tried an
empty **object**. Whether GitHub treats `{}` as "credentials present but
nothing to authenticate with, so skip the login" (which would let this one
expression serve all three shapes of FR-003 with zero new stage input —
FR-026 outcome 1, the preferred outcome) or rejects/attempts-and-fails it
exactly like the already-measured cases (which would force FR-026 outcome 2,
one new opt-in input, or outcome 3, measured-and-not-possible) is not
knowable from documentation or from re-reading #226/#227 — it is a new,
undocumented platform behavior, and FR-016/User Story 5 forbid this plan from
assuming an answer. A second, independent platform behavior is equally
undemonstrated and equally blocking for User Story 3: whether a credential
minted in one wrapper job, masked with `::add-mask::`, and forwarded through
`needs.<job>.outputs.*` into the `secrets:` block of a sibling job's
`uses:` call to a stage — the only legal shape, since a job whose body is
`uses:` cannot carry additional steps of its own to mint the credential
in-line — stays masked across that hand-off (FR-012).

Both probes require dispatching a throwaway `workflow_dispatch` workflow
against real GitHub-hosted runners and reading its run output — exactly the
method PR #226 used, and exactly the thing this plan's own tool allowlist
cannot do (no `.github/workflows` write access, no push outside this spec
branch, no PR authority, no confirmed `gh workflow run`/`gh api` dispatch
access). Per the same precedent specs/038's plan/implement stages recorded
against T001 when they hit the identical gap, this plan does not invent an
answer: it fully specifies both probes as the first, blocking task(s) of
`tasks.md`, to be run by the tasks/implement stage (which holds the branch,
dispatch, and PR authority this plan stage lacks) before any published stage
file is touched, and it designs the rest of the feature — the
`verify-image-prerequisites` amendment, the Gate 22 extension, the
`wing-commander-ecr-credentials` component (FR-013), the repository-scoped-
token worked example, this repository's own FR-027 dogfood check, and the
documentation rewrite — so that either probe outcome has a concrete,
recorded path forward rather than a stall. See
[research.md](./research.md) for the full decision record (including the
already-ruled-out mechanisms, cited directly from #226/#227, that do **not**
need re-probing),
[contracts/private-registry-credentials.md](./contracts/private-registry-credentials.md)
for the interface contract, and [data-model.md](./data-model.md) for the
entity shapes.

## Technical Context

**Language/Version**: GitHub Actions workflow YAML — the pipeline itself has
no application language/runtime; this feature adds no new language to the
project.

**Primary Dependencies**: None new for the per-job binding itself —
`container.credentials` is a native Actions job key, already declared and
already working (for the true/positive case) since specs/038. One new
dependency for FR-013's optional edge component: `aws-actions/configure-aws-
credentials@v4`, already a dependency of this repository's existing
`wing-commander-bedrock-credentials` composite (specs/016), reused rather
than a new action being introduced.

**Storage**: N/A — no persisted state. The credential pair, the opt-in
control (if FR-026 outcome 2 ships), and the ECR adapter's inputs/outputs are
all per-invocation `workflow_call`/job values, never written to
`spec-meta.json` or any other lifecycle record.

**Testing**: `.github/workflows/lint-workflows.yml`'s existing Gate 22 (the
gate specs/038 added and that today hard-fails any job whose `container:`
carries a `credentials:` key at all, citing #227/PR #226 by name) is
amended, not replaced or renumbered: it must recognize and require the new
`credentials:` expression (research D5/D7) rather than forbid the key
outright, and its self-test (`verify-gate-22.py`) gains fixtures for every
new failure branch the amendment introduces (FR-020), plus a registered-
exception table for FR-021. Beyond lint, this repository's own PR checks
cannot exercise a real container pull, a real registry login, or a real
cross-job secret hand-off — those are exactly the two live-runner probes
(research D3, D4) and the scratch-adopter-repository scenarios in
`quickstart.md`, mirroring specs/038's and specs/031's identical testing
boundary.

**Target Platform**: GitHub Actions reusable (`workflow_call`) workflows,
consumed cross-repository by adopters, running on whatever runner/image the
adopter names (unchanged from specs/038) with credentials now reaching every
job that runs inside that image.

**Project Type**: Infrastructure-as-configuration — GitHub Actions reusable
workflows, not a conventional application with a `src/`/`tests/` split.

**Performance Goals**: Identical to today when neither secret is set
(SC-002) — the new `credentials:` expression's false branch (`fromJSON('{}')`)
must collapse to the same no-login behavior the current bare `image:`-only
block already has; no added network call, no added latency. When both
secrets are set, no additional cost beyond what specs/038 already accepted
(`verify-image-prerequisites` pulls the image once; each real containerized
job pulls it again — unchanged, not something this plan optimizes).

**Constraints**:
- Strictly additive interface change on the current major line (FR-025): the
  two existing secret names are unchanged; no existing input, secret, or
  output of any published stage is renamed or removed. FR-026 outcome 2's one
  permitted opt-in input is the only new stage-interface surface this feature
  may add, and only if the probe (research D3) forces that outcome.
- The credential binding must be byte-for-byte identical across every job of
  a stage that carries the container binding (FR-008) — the same granularity
  Gate 22 already enforces for `runs-on:`/`container.image`.
- The published stages stay registry-agnostic: no provider name, region,
  role, or endpoint in any stage file (FR-009) — provider-specific minting
  lives only in the optional, edge-located `wing-commander-ecr-credentials`
  component (FR-013), never referenced by a published stage.
- No stage file changes before both live-runner probes (research D3, D4)
  are run and recorded, per FR-016/User Story 5 — this is a process
  constraint on `tasks.md`'s own ordering, not a YAML constraint.
- A job that must deviate from the uniform credential binding carries a
  registered, machine-checked exception naming the reason (FR-021) — never
  an unregistered deviation, never a code comment alone (constitution VII,
  IX).

**Scale/Scope**: 12 published `workflow_call`-only stage files today —
verified 2026-09-07 by deriving the set structurally (every file under
`.github/workflows/` declaring `on.workflow_call`, excluding
`lint-workflows.yml`, which is a gate workflow, not a stage): `intake`,
`clarify`, `plan`, `tasks`, `implement`, `finalize`, `cleanup`, `watchdog`,
`pr-conversation`, `rebase`, `auto-update-spec-kit`, `metrics-persist` — one
more than specs/038's eleven (`metrics-persist` shipped afterward, already
carrying the same two secrets and the same bare `image:`-only binding).
Together they carry 42 jobs with the `container: { image: ... }` block this
feature amends (verified by grep, 2026-09-07) — up from specs/038's 33,
consistent with FR-019's requirement that the stage set stay derived rather
than listed. One new composite action (`wing-commander-ecr-credentials`,
FR-013). One new scheduled/on-demand workflow for this repository's own
FR-027 dogfood check, following the `auto-update-spec-kit.yml` scheduling
precedent. Exact per-file, per-job edit list and the two probe workflows'
exact content are deferred to `tasks.md`, matching how specs/038 and
specs/031 both deferred their own exact enumeration.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Result |
|---|---|---|
| I. Guide — repo is its own first example | Built through the pipeline itself (issue #283 → this spec → this plan → tasks → implement). FR-027 requires this repository to dogfood the private-image path on its own infrastructure, on a schedule, through the same stage-file shape adopters use — unlike specs/031's environment binding and specs/016's Bedrock support (both undogfooded by this repository's own wrappers to this day), this feature does not get to leave that gap open. No bootstrap deferral needed: the dogfood target is a private package in this repository's own registry, requiring no external resource this repository does not already control. | ✅ Pass |
| II. Cost-Conscious Model Tiering | This plan runs at `claude-sonnet-5` (`plan.yml`'s default, planning-weight). The feature adds no new agent invocation and changes no stage's model tiering — every new piece (the amended `container.credentials` expression, the ECR composite, the dogfood workflow) is deterministic YAML/shell, not an agent step. | ✅ Pass |
| III. Simple, GitHub-Native Interaction | The core mechanism is GitHub Actions' own native `container.credentials` job key; the optional edge component uses `aws-actions/configure-aws-credentials`, already precedented in this repository (specs/016). No external dashboard, no new CLI. | ✅ Pass |
| IV. Automation-First | No new manual step in the adopter-facing path: `verify-image-prerequisites` still fails fast and automatically (FR-007). The one manual/deferred piece this plan itself introduces — the two live-runner probes this plan stage cannot execute under its own tool allowlist — is reported explicitly here and in research.md as a blocking first task for the next stage, never silently assumed away, exactly as this principle requires and exactly as specs/038's T001 note already precedents. | ✅ Pass (deferral explicitly reported) |
| V. Security — untrusted content is never instructions | `container-registry-username`/`password` remain `workflow_call` secrets, read only via the stage's own declared `secrets:` block, never `secrets: inherit`, never derived from `github.event.*`/`vars.*` inside a stage. GitHub's own log masking still requires no bespoke code. FR-012 requires the new cross-job masked hand-off (a wrapper's minted ECR token crossing a `needs.<job>.outputs.*` boundary into a stage call's `secrets:`) to be **demonstrated**, not assumed — research D4 is exactly that demonstration, required before FR-013 ships. The ECR component requests no new GitHub App permission; the adopter's own OIDC role is declared entirely in their own wrapper. | ✅ Pass (masking guarantee demonstrated, not assumed, per research D4) |
| VI. Portability — consuming repo owns its artifacts | The image reference, the credential pair, and (for FR-013 users) the adopter's own cloud identity are owned entirely by the adopter's repository/secrets/OIDC provider; the pipeline stores nothing about any of them. FR-027's dogfood image is this repository's own artifact, in this repository's own registry namespace — consistent with this principle even where this repository is itself the "adopter." | ✅ Pass |
| VII. Two Interfaces — published contract vs. consuming instrument | The `container.credentials` binding stays inside the *stage* (published contract) — the same already-registered structural deviation specs/038 justified (a wrapper cannot set a called job's `container:`), extended rather than newly introduced. The new `wing-commander-ecr-credentials` composite is itself a **published-contract addition** (`.github/actions/**` is contract surface per this principle's own text) — additive, optional, referenced by no stage (FR-013). **Conditional**: if the live probe (research D3) forces FR-026 outcome 2, exactly one new opt-in stage input is added — a deliberate, bounded widening of the published contract surface that FR-002/FR-010 explicitly pre-authorize for this one case. See Complexity Tracking. | ⚠️ Conditional — see Complexity Tracking |
| VIII. A Green Check Means What It Says | Gate 22's amendment keeps deriving its stage set structurally (unchanged from specs/038 D1/D7 — FR-019). FR-020 requires every new failure branch the amendment ships to be exercised by a checked-in fixture, which is this principle's own text verbatim. Exact fixtures are implementation-stage work (mirroring how specs/038 itself deferred writing `verify-gate-22.py`'s fixtures past its own plan), but the requirement is fixed here, not left implicit. | ✅ Pass (fixture authorship deferred to tasks.md, scope fixed here) |
| IX. Judgment That Gates a Durable Action Belongs in Deterministic Code | FR-021 requires a job's deviation from the uniform credential binding to be a registered, machine-checked exception — never a code comment a reviewer must trust by reading prose. This is a direct application of this principle: whether a deviation is legitimate is answered by Gate 22's exception table (deterministic code), not by an agent's or reviewer's judgment about whether a comment's stated reason is good enough. | ✅ Pass |

**Post-Phase-1 re-check**: Unchanged for Principles I–VI, VIII, IX. Phase 1's
design (data-model.md, contracts/private-registry-credentials.md,
quickstart.md) introduces no new agent invocation, no new persisted state,
and no new untrusted-input path — the ECR component's inputs are the same
class of caller-declared, non-secret values (`aws-role-arn`, `aws-region`)
`wing-commander-bedrock-credentials` already establishes as safe. Principle
VII's conditional flag is unchanged by Phase 1 design: it remains contingent
on research D3's probe outcome, which Phase 1 cannot itself resolve (it
requires a live run, not a design decision).

## Project Structure

### Documentation (this feature)

```text
specs/044-private-registry-credentials/
├── plan.md                              # This file (/speckit-plan command output)
├── research.md                          # Phase 0 output (/speckit-plan command)
├── data-model.md                        # Phase 1 output (/speckit-plan command)
├── quickstart.md                        # Phase 1 output (/speckit-plan command)
├── contracts/                           # Phase 1 output (/speckit-plan command)
│   └── private-registry-credentials.md
├── checklists/
│   └── requirements.md                  # already present (intake stage output)
├── spec-meta.json
└── tasks.md                             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source code (repository root)

This repository is a GitHub Actions pipeline, not a conventional
library/service — there is no `src/`/`tests/` split. The real layout this
feature touches (exact per-file/per-job edits deferred to `tasks.md`):

```text
.github/
├── workflows/
│   ├── intake.yml                  # + amended container.credentials
│   ├── clarify.yml                 #   expression on every job that
│   ├── plan.yml                    #   already carries container.image
│   ├── tasks.yml                   #   (research D5/D7) — contingent on
│   ├── implement.yml               #   the D3 probe's outcome; if it forces
│   ├── finalize.yml                #   FR-026 outcome 2, also + one new
│   ├── cleanup.yml                 #   opt-in input, uniformly
│   ├── watchdog.yml                #
│   ├── pr-conversation.yml         #
│   ├── rebase.yml                  #
│   ├── auto-update-spec-kit.yml    #
│   ├── metrics-persist.yml         #
│   └── lint-workflows.yml          # Gate 22 amended (not renumbered):
│                                    #   recognizes/requires the new
│                                    #   credentials: shape instead of
│                                    #   forbidding the key outright;
│                                    #   verify-image-prerequisites' warning
│                                    #   about credential reach removed
│                                    #   (FR-015, contingent on D3); new
│                                    #   fixtures + exception table
│                                    #   (FR-020/FR-021)
│
├── actions/
│   └── wing-commander-ecr-credentials/   # NEW (FR-013): optional, edge-
│       └── action.yml                    #   located, referenced by no
│                                          #   published stage; inputs
│                                          #   (identity, region, optional
│                                          #   registry override) -> outputs
│                                          #   (username, password), masked
│                                          #   per research D4
│
│   .github/scripts/verify-gate-22.py     # extended: new synthetic
│                                          #   fixtures for the amended
│                                          #   shape's failure branches
│                                          #   (FR-020) + exception-table
│                                          #   coverage (FR-021)
│
(new: a scheduled + workflow_dispatch workflow for FR-027's dogfood check,
 plus its thin wing-commander-*.yml wrapper — exact name/placement deferred
 to tasks.md, following the auto-update-spec-kit.yml scheduling precedent;
 pulls a private GHCR package scoped to this repository, through the same
 container.credentials shape adopters use, authenticated with this
 repository's own workflow token or a repository secret — no cloud account
 or cloud-registry identity owned by this repository)

(wing-commander-1-intake.yml ... wing-commander-9-pr-conversation.yml,
 wing-commander-rebase.yml, wing-commander-auto-update-spec-kit.yml,
 wing-commander-metrics-persist.yml)
                                     # this repository's own dogfooded
                                     #   wrappers — unchanged by this
                                     #   feature beyond whatever FR-027's
                                     #   new dogfood wrapper adds; the two
                                     #   credential secrets these wrappers
                                     #   already forward (specs/038 D8) are
                                     #   unchanged in name and meaning

docs/
├── adoption.md                     # implementation-stage edit: removes
│                                    #   the "these credentials reach the
│                                    #   prerequisite check and nothing
│                                    #   else" statement (FR-015, contingent
│                                    #   on D3 succeeding), adds the two
│                                    #   worked examples (FR-023) and the
│                                    #   credential-lifetime statement
│                                    #   (FR-024)
└── setup.md                        # implementation-stage edit, if FR-026
                                     #   outcome 2's opt-in input ships

specs/010-reusable-pipeline/contracts/stage-interfaces.md
                                     # implementation-stage edit: the
                                     #   existing credential-secret rows'
                                     #   description updated to state they
                                     #   now reach every job, not only the
                                     #   prerequisite check
```

**Structure Decision**: No new top-level directories. The core change is an
amendment to a value already present in every job's `container:` block
(`credentials:`), not a new job shape — unlike specs/038, this feature adds
no new per-stage job. One new composite action (`wing-commander-ecr-
credentials`) and one new scheduled workflow (FR-027's dogfood check) are the
only new *units*. Documentation updates are scoped to the implementation
stage, consistent with the `016-bedrock-support`/`031-stage-environment-
binding`/`038-runner-container-passthrough` precedent — this plan's own
artifacts stay inside `specs/044-private-registry-credentials/`.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|---------------------------------------|
| Principle VII (conditional): one new opt-in stage input, added to all 12 published stages, if and only if research D3's live probe shows the empty-object `credentials: {}` expression does not suppress a login attempt on a public image with no credentials supplied | FR-026 requires this outcome be tried only as the second preference, and only for the stated reason: without it, no expression available to this feature can distinguish "adopter named a public image and set no credentials" from "adopter named a private image and forgot to set credentials," because both states are string-identical (both secrets empty) and — per this same probe's negative result — an always-present, always-attempted `credentials:` key cannot represent "do not attempt a login" any other way GitHub recognizes. | FR-026 outcome 1 (no new input, inferred purely from secret presence) is the alternative, and it is not "rejected" here — it is this plan's own primary, preferred design (research D3/D5). This row exists only to pre-register the fallback, per FR-026's own text, so that if the probe forces it, `tasks.md` is not left inventing an unregistered stage-interface change mid-implementation. |

This plan carries no other Complexity Tracking entries: the credential
binding's presence inside the *stage* (rather than the wrapper) is not a new
deviation — it is specs/038's already-justified one, unchanged in kind by
this feature.
