# Implementation Plan: Consumer-Chosen Runners and Container Images

**Branch**: `038-runner-container-passthrough` | **Date**: 2026-08-18 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/038-runner-container-passthrough/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

Every job of all eleven published `workflow_call`-only stages is hardcoded to
`runs-on: ubuntu-latest` with no `container:`. Adopters who must run on
self-hosted infrastructure, a larger/ARM runner, or inside an approved base
image are blocked outright, and — exactly like the deployment-environment
binding of specs/031 — cannot fix this from their own wrapper, because
`runs-on`/`container` are legal only inside the *called* workflow.

This plan adds two optional `workflow_call` inputs (`runner` string, default
`ubuntu-latest`; `container-image` string, default `""`) and two optional
`workflow_call` secrets (`container-registry-username`,
`container-registry-password`) to all eleven stage files, and binds every job
in every file to them:

```yaml
runs-on: ${{ startsWith(inputs.runner, '[') && fromJSON(inputs.runner) || inputs.runner }}
container:
  image: ${{ inputs.container-image }}
  credentials:
    username: ${{ secrets.container-registry-username }}
    password: ${{ secrets.container-registry-password }}
```

The `startsWith(...) && fromJSON(...) || ...` form is the standard
short-circuit ternary idiom for GitHub Actions expressions and is what lets
`runner` carry either a single label (`"ubuntu-latest"`,
`"my-larger-runner"`) or a JSON-array multi-label conjunction
(`'["self-hosted","linux","x64"]'`) from one string-typed input (FR-002,
FR-003) — the only shape a typed `workflow_call` input can carry (spec
Assumptions). An empty `container-image` is expected, per the requester's own
framing and by analogy with specs/031's verified empty-`environment` no-op,
to leave the job running directly on the runner with **no container at all**
— but unlike specs/031, this behavior has **not** been empirically probed in
this planning pass (no live-runner access from this stage); research.md D3
records this explicitly as a required implementation-time verification, not
an assumed fact, per FR-005/FR-018.

Two structural GitHub facts drive the rest of the design. First, a job's
`container:` (and therefore its credentials) resolves **before any step in
that job runs** — the same timing class as specs/031's environment
protection rules — so a step *inside* a stage's own job can never intercept
or improve a failed pull's error message, and a token-based registry
credential must be minted by the **calling wrapper**, before the stage's job
starts, never by a step inside the stage (spec edge case; research D4).
Second, satisfying FR-010 (a legible missing-credential message) and FR-011
(prerequisite tools checked before any agent cost) both require inspecting
the chosen image *before* the real per-job container is created, which is
only possible from a job that itself runs directly on the runner. This plan
therefore adds one new job per stage file, `verify-image-prerequisites`
(skipped outright when `container-image` is unset — zero added cost or
failure mode on the default path, FR-006/FR-011), that every other job in the
file depends on via a skip-tolerant `needs:`/`if:` pair (research D5). See
[research.md](./research.md) for the full decision record,
[contracts/runner-container-passthrough.md](./contracts/runner-container-passthrough.md)
for the interface contract, and [data-model.md](./data-model.md) for the
entity shapes.

## Technical Context

**Language/Version**: GitHub Actions workflow YAML — the pipeline itself has
no application language/runtime; this feature adds no new language to the
project.

**Primary Dependencies**: None new. No new third-party action, no new shared
composite `uses:` dependency for the binding itself — `runs-on`/`container`
are GitHub Actions' own native job keys. `verify-image-prerequisites` (a new
job, not a composite) needs only Docker, already present on every
GitHub-hosted `ubuntu-latest` runner and a documented adopter-side
requirement for self-hosted runners that want a container (spec edge case
"Containers require Docker on the runner").

**Storage**: N/A — no persisted state. `runner`, `container-image`, and the
two credential secrets are per-invocation `workflow_call` values, never
written to `spec-meta.json` or any other lifecycle record (mirrors specs/031
Storage entry; spec Key Entities: "Not validated by the pipeline" / "Inert
unless an image is named").

**Testing**: `.github/workflows/lint-workflows.yml` must gain two new gates
(research D7): Gate 22 (input declarations and the `runs-on:`/`container:`
binding are byte-for-byte uniform across all 33 jobs, mirroring Gate 7's
shape for specs/031) and Gate 23 (`verify-image-prerequisites` exists per
stage file and every entry job's `needs:`/`if:` correctly tolerates a
`skipped` result, plus the FR-011a drift check that the canonical
required-tool list agrees with what stage/composite `run:` blocks actually
invoke — dual-check discipline mirroring Gate 5). Unlike specs/031's D8
(`environment.deployment` tripped a real actionlint diagnostic), `container:`,
`image:`, and `credentials:` are all standard, long-published Actions
workflow-syntax keys, so no actionlint schema risk is expected here — this
must still be confirmed against the pinned actionlint (1.7.7) at
implementation time rather than assumed. Beyond lint, only the cross-file
consistency check (User Story 2) is mechanically verifiable in this
repository; every scenario requiring a real self-hosted runner, a real
container pull, or real registry credentials requires a scratch adopter
repository, per the spec's own Independent Test vehicles (mirrors specs/031's
Testing section).

**Target Platform**: GitHub Actions reusable (`workflow_call`) workflows,
consumed cross-repository by adopters, running on whatever runner/image the
adopter names (default: `ubuntu-latest`, no container).

**Project Type**: Infrastructure-as-configuration — GitHub Actions reusable
workflows, not a conventional application with a `src/`/`tests/` split. See
Project Structure below for the actual layout.

**Performance Goals**: When both controls are left unset, zero added latency,
zero added network call, and zero behavioral difference (SC-002) —
`verify-image-prerequisites` is skipped outright (`if:
inputs.container-image != ''`), and the `runs-on`/`container` expressions
collapse to today's literal values. When `container-image` is set, one
additional job pulls the image once before any agent-bearing job attempts
its own (second, GitHub-cached-where-possible) pull of the same image — an
accepted, documented cost of the credential/prerequisite check design
(research D5), not something this plan optimizes away.

**Constraints**:
- Strictly additive interface change — no existing input, secret, or output
  of any stage is renamed, removed, or has its default changed.
- The same four names (two inputs, two secrets), types, and defaults must
  appear identically across all eleven stage files (FR-001, FR-004).
- Both `runner` and `container-image` are the sole source of the binding —
  never defaulted from `vars.*`, never derived from ambient repository state
  (FR-012, constitution VII) — mirrored exactly by the two new secrets, which
  a stage may only read via its own declared `secrets:` block, never
  `secrets: inherit`.
- Both values, and the credentials, pass through entirely unvalidated by the
  pipeline: no runner-label allowlist, no image-reference rewriting, no
  fallback image (FR-008).
- The prerequisite check (FR-011) must run before any agent-bearing step in
  the stage and must not change the outcome, latency, or failure surface of
  a run with no image named (FR-006 is not compromised by FR-011).
- A job that must deviate from the uniform binding carries a registered,
  machine-checked exception naming the reason (FR-015), exactly like Gate 7's
  one existing `pr-conversation.act` exception.

**Scale/Scope**: Eleven published `workflow_call`-only stage files — `intake`,
`clarify`, `plan`, `tasks`, `implement`, `finalize`, `cleanup`, `watchdog`,
`pr-conversation`, `rebase`, `auto-update-spec-kit` — verified today
(2026-08-18) to carry 33 jobs total, all with a direct `runs-on:` (none
delegate via a local `uses:`). Each file gains 2 new `workflow_call` inputs, 2
new `workflow_call` secrets, one new `runs-on:`/`container:` pair per
existing job (33 edits each), and one new `verify-image-prerequisites` job
(11 new jobs) plus `needs:`/`if:` wiring on each file's entry job(s) — exact
per-file DAG wiring (which jobs count as "entry" given each file's existing
`needs:` graph and any `if: always()` survivors, per Gate 15's own finding)
is deferred to `tasks.md`, matching how specs/031 deferred its exact 40-job
enumeration. This repository's own eleven `wing-commander-*.yml` wrappers
each gain the same two inputs/two secrets sourced from repository
configuration (FR-016, User Story 6). Two new `lint-workflows.yml` gates (22,
23). Documentation updates (`docs/adoption.md`, `docs/setup.md`,
`specs/010-reusable-pipeline/contracts/stage-interfaces.md`) are scoped to
the implementation stage, matching the `016-bedrock-support` and
`031-stage-environment-binding` precedent — this plan's own artifacts stay
inside `specs/038-runner-container-passthrough/`.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Result |
|---|---|---|
| I. Guide — repo is its own first example | Built through the pipeline itself (issue #219 → this spec → this plan → tasks → implement). Unlike specs/031 (which needed an out-of-band GitHub Settings resource and so recorded a bootstrap deferral), User Story 6 requires **no** external resource — a repository variable is directly settable — so this repository's own wrappers dogfood the feature in the same PR cycle that ships it, no deferral recorded. | ✅ Pass |
| II. Cost-Conscious Model Tiering | This plan runs at `claude-sonnet-5` (`plan.yml`'s default, planning-weight). The feature adds no new agent invocation and changes no stage's model tiering — it adds one deterministic, non-agent job (`verify-image-prerequisites`) per stage. | ✅ Pass |
| III. Simple, GitHub-Native Interaction | The entire mechanism is GitHub Actions' own native `runs-on:`/`container:` job syntax — no external dashboard, no new CLI, nothing outside GitHub. | ✅ Pass |
| IV. Automation-First | No new manual step. A prerequisite-check failure (FR-011) or a pull failure due to an absent credential (FR-010) is reported explicitly — in the job's own log/summary, before any agent step — never a silent stop. | ✅ Pass |
| V. Security — untrusted content is never instructions | `runner`, `container-image`, and the two credential secrets arrive strictly as `workflow_call` inputs/secrets set in the calling wrapper's own `with:`/`secrets:` block — never derived from `github.event.*`, `vars.*` read by the *stage* itself, issue/comment text, or any other ambient state (FR-012). GitHub Actions masks `secrets.*` values in logs automatically — no bespoke masking code is needed, and no design here writes a credential value to a job summary, artifact, or output. | ✅ Pass |
| VI. Portability — consuming repo owns its artifacts | The chosen runner, image, and any registry credentials are owned entirely by the adopter's own repository (Settings, secrets) and infrastructure; the pipeline stores nothing about them — no `spec-meta.json` field, no other artifact. | ✅ Pass |
| VII. Two Interfaces — published contract vs. consuming instrument | **Deliberate, registered deviation** (see Complexity Tracking): the controls must live in the *stage* (published contract), not the wrapper, because GitHub itself makes `jobs.<job_id>.runs-on` and `jobs.<job_id>.container` illegal in a job whose body is `uses: <reusable workflow>`, and `on.workflow_call.inputs` has no mechanism to accept either from the caller — the exact same structural exception specs/031 already registered for `environment:`. The other half of the principle holds: no stage discovers a runner, image, or credential on its own (FR-012). | ⚠️ Deviation — justified below |

**Post-Phase-1 re-check**: Unchanged. The Phase 1 design
(data-model.md, contracts/runner-container-passthrough.md, quickstart.md)
introduces one new deterministic job per stage and two new lint gates — no
new agent invocation, no new untrusted-input path (the new job's own
`docker`/tool-check logic still reads only the same trusted `workflow_call`
inputs/secrets), and no new persisted state. The Principle VII deviation is
unavoidable by construction (research D2), not merely convenient, so Phase 1
does not change its justification.

## Project Structure

### Documentation (this feature)

```text
specs/038-runner-container-passthrough/
├── plan.md                                  # This file (/speckit-plan command output)
├── research.md                              # Phase 0 output (/speckit-plan command)
├── data-model.md                            # Phase 1 output (/speckit-plan command)
├── quickstart.md                            # Phase 1 output (/speckit-plan command)
├── contracts/                               # Phase 1 output (/speckit-plan command)
│   └── runner-container-passthrough.md
├── checklists/
│   └── requirements.md                      # already present (intake stage output)
├── spec-meta.json
└── tasks.md                                 # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source code (repository root)

This repository is a GitHub Actions pipeline, not a conventional
library/service — there is no `src/`/`tests/` split. The real layout this
feature touches:

```text
.github/
├── workflows/
│   ├── intake.yml                  # + runner/container-image inputs,
│   ├── clarify.yml                 #   + container-registry-username/
│   ├── plan.yml                    #   password secrets, + runs-on:/
│   ├── tasks.yml                   #   container: on every existing job,
│   ├── implement.yml               #   + one new verify-image-prerequisites
│   ├── finalize.yml                #   job with needs:/if: wiring on each
│   ├── cleanup.yml                 #   file's entry job(s) (research D5) —
│   ├── watchdog.yml                #   applies to all eleven files
│   ├── pr-conversation.yml         #
│   ├── rebase.yml                  #
│   ├── auto-update-spec-kit.yml    #
│   └── lint-workflows.yml          # + Gate 22 (input/binding uniformity)
│                                    #   + Gate 23 (verify-image-prerequisites
│                                    #   wiring + FR-011a tool-list drift check)
│                                    #   + two self-tests (research D7)
│
.github/actions/**                  # UNCHANGED — the binding itself is job
                                     #   attributes, not a step; no composite
                                     #   needs to know about runner/container
                                     #   selection. (wing-commander-preflight
                                     #   is NOT extended — the prerequisite
                                     #   check lives in the new job instead,
                                     #   research D5's rationale.)
(wing-commander-1-intake.yml ... wing-commander-9-pr-conversation.yml,
 wing-commander-rebase.yml, wing-commander-auto-update-spec-kit.yml)
                                     # this repo's own dogfooded wrappers —
                                     #   each gains runner/container-image
                                     #   sourced from vars.WING_COMMANDER_RUNNER
                                     #   / vars.WING_COMMANDER_CONTAINER_IMAGE
                                     #   (literal-fallback convention, research
                                     #   D8) and the two credential secrets
                                     #   forwarded from repository secrets
                                     #   (FR-016, User Story 6)

docs/
├── adoption.md                     # implementation-stage edit: new
│                                    #   "Runners and container images"
│                                    #   section (FR-017's copy-pasteable
│                                    #   example, multi-label convention,
│                                    #   prerequisite list, credential setup)
│                                    #   + Stage reference intro bullet
├── setup.md                        # implementation-stage edit: new
│                                    #   WING_COMMANDER_RUNNER /
│                                    #   WING_COMMANDER_CONTAINER_IMAGE
│                                    #   repository-variable rows + the two
│                                    #   registry credential secrets
└── architecture.md                 # implementation-stage edit (optional):
                                     #   the Principle VII deviation this
                                     #   feature registers could join the
                                     #   existing environment-binding note

specs/010-reusable-pipeline/contracts/stage-interfaces.md
                                     # implementation-stage edit: Common
                                     #   inputs table gains runner/
                                     #   container-image rows (same
                                     #   convention 031/016 followed)
```

**Structure Decision**: No new top-level directories. The feature is
implemented entirely within the existing `.github/workflows/` (eleven stage
files, plus `lint-workflows.yml`) and `wing-commander-*.yml` wrapper layout
this pipeline already has, with zero changes to `.github/actions/**`. One new
kind of job (`verify-image-prerequisites`) is added, once per stage file —
the only new *unit* this feature introduces; everything else is new inputs,
secrets, and job attributes on units that already exist. Documentation
updates are scoped to the implementation stage, consistent with
`016-bedrock-support` and `031-stage-environment-binding` — this plan's own
artifacts stay inside `specs/038-runner-container-passthrough/`.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|---------------------------------------|
| Principle VII: runner and container selection are owned by the *stage* (published contract), not the wrapper (which normally owns every security/config gate) | `jobs.<job_id>.runs-on` and `jobs.<job_id>.container` are legal **only** inside a called (`workflow_call`) workflow's own job definitions. GitHub rejects both outright on a job whose `uses:` points at a reusable workflow, and `on.workflow_call.inputs` has no mechanism to accept or forward either — so there is no syntax by which a wrapper could apply these to a stage it calls. | A wrapper-side selection — impossible, not merely more complex: GitHub's own parser refuses both keywords in that position. The only alternative that keeps the wrapper "in charge" — forking the stage file per adopter — is exactly what constitution VII and this feature both exist to avoid (spec Overview: "the *only* thing an adopter cannot fix from their own wrapper"). |
