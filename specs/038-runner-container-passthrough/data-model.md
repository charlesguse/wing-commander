# Data Model: Consumer-Chosen Runners and Container Images

This feature has no application data store; its "entities" are
configuration values that flow through GitHub Actions `workflow_call`
interfaces, plus GitHub-native scheduling/registry concepts this pipeline
never stores. This document specifies their shape, validation rules, and
lifecycle, mirroring the spec's Key Entities section and
specs/031-stage-environment-binding's data-model.md structure.

## Entity: Runner selection

The set of labels a stage's jobs target, supplied per stage call.

| Attribute | Type | Notes |
|---|---|---|
| `runner` (raw input value) | string (`workflow_call` input, all eleven published stages) | Default `ubuntu-latest` (FR-001). Any string. |
| Reading | derived, not stored | If the value starts with `[`, read as a JSON array and each element is one label, applied as a **conjunction** (FR-002) via `fromJSON`. Otherwise read as one single label. Never both — the convention is unambiguous by construction (research D2), not by pipeline-side detection heuristics beyond the leading-`[` check. |
| Applied via | `runs-on: ${{ startsWith(inputs.runner, '[') && fromJSON(inputs.runner) || inputs.runner }}` | Identical expression on every job of every stage (FR-007). Not yet empirically verified against a live runner in this planning pass (research D2) — implementation must confirm both the single-label and JSON-array paths before shipping. |

**Validation rules**: none performed by this pipeline (FR-008 — pass-through,
no allowlist, no existence check of the named runner/labels). GitHub's own
scheduling behavior governs what happens when no runner carries the named
label(s) (spec Acceptance Scenario: "GitHub queues the job per its own
behavior").

**State transitions**: none — a per-invocation value, recomputed fresh every
stage invocation from the input, never persisted to `spec-meta.json` or any
other lifecycle record.

**Ownership**: originates only from the calling wrapper's own `with:` block
— never from `github.event.*`, `vars.*` read by the *stage* itself, or any
other ambient state (FR-012, constitution VII). This repository's own
wrappers source it from `vars.WING_COMMANDER_RUNNER` (research D8) — that
`vars.*` read happens in the **wrapper**, which is allowed to read ambient
repository configuration; the *stage* files themselves never do.

## Entity: Container image reference

The image a stage's jobs run inside, as the adopter writes it.

| Attribute | Type | Notes |
|---|---|---|
| `container-image` (raw input value) | string (`workflow_call` input, all eleven published stages) | Default `""` (FR-004). Any string the adopter writes verbatim — registry, repository, tag or digest, exactly as they'd write it for `docker pull` (spec Key Entities: "as the adopter writes it"). |
| Emptiness | meaningful, distinct from any other value | `""` is intended to mean **no container at all** — not an empty/default one (FR-005). This is the one behavior in this feature not yet empirically verified (research D3); until verified, it must not be relied upon as a proven fact by any later stage. |
| Applied via | `container: { image: ${{ inputs.container-image }}, credentials: {...} }` | Identical mapping-form block on every job of every stage (FR-007), mirroring specs/031's `environment:` mapping-form precedent. |

**Validation rules**: none on the reference itself — no implicit registry, no
implicit tag, no rewriting, no fallback image (FR-008). The only validation
this feature performs at all is the **prerequisite check** (see Image
prerequisite contract below), which inspects the environment the pulled
image provides, never the reference string itself (FR-008's own carve-out:
"The prerequisite check of FR-011 is not an exception: it inspects the
environment the job is already running in, never the adopter's values").

**State transitions**: none — per-invocation, never persisted.

**Ownership**: same as Runner selection — `workflow_call` input only, this
repository's own wrappers source it from `vars.WING_COMMANDER_CONTAINER_IMAGE`
(research D8).

## Entity: Registry credentials

What the runner needs to pull a non-public image.

| Attribute | Type | Notes |
|---|---|---|
| `container-registry-username` | secret (`workflow_call` secret, all eleven published stages, `required: false`) | A static registry username, or a fixed value a cloud registry's docker-login convention expects (e.g. ECR's literal `AWS`). |
| `container-registry-password` | secret (`workflow_call` secret, all eleven published stages, `required: false`) | A static registry password, **or** a short-lived token minted by the calling wrapper before the stage's job starts (research D4) — the stage cannot distinguish, and does not need to. |
| Inertness | derived | Both values are consumed only inside the `container.credentials` mapping (Container image reference, above); when `container-image` is empty, both are never read by anything the pull touches (FR-009: "inert unless an image is named"). |

**Validation rules**: none performed by the pipeline on the credential
values themselves. The one active check this feature adds — the
`verify-image-prerequisites` job's pull attempt (Image prerequisite
contract, below) — reacts to a pull *failure*, not to the credential values
in isolation, and cannot run at all once `container-image` is empty.

**State transitions**: none — resolved fresh per invocation from
`secrets:`, and (like every stage secret today) never logged: GitHub Actions
masks any `secrets.*` value that appears in a job's log output
automatically, with no bespoke masking code required (FR-009's "MUST NOT
appear in run logs or job configuration" — the "job configuration" half is
satisfied by these two values only ever appearing as `secrets.*`
expressions, never resolved into a plain job-level field a workflow-file
viewer could read).

**Ownership**: arrives only via the calling wrapper's own `secrets:` block —
this repository's own wrappers forward `secrets.WING_COMMANDER_CONTAINER_
REGISTRY_USERNAME`/`_PASSWORD` (research D8). A wrapper using a token-based
or cloud-registry credential mints it in a step of its **own** job, before
its `uses:` call to the stage — the stage never mints, refreshes, or
otherwise manages a credential's lifecycle (research D4).

## Entity: Image prerequisite contract

The tools and runtimes a chosen image must provide for the stage's own
steps and shared composite actions to run — both documented (FR-017) and
machine-checked (FR-011, FR-011a).

| Attribute | Type | Notes |
|---|---|---|
| Canonical tool list | fixed set, checked into the repository (research D6) | Seeded from what stage/composite `run:` blocks actually invoke today: `git`, `gh`, `jq`, `curl`, `python3`, `bash` — plus Node.js, an *inferred* (not directly observed) runtime dependency of `anthropics/claude-code-action@v1`, used by every agent-bearing job across all eleven stages. |
| Check timing | before any agent-bearing job's own container is created | Performed by the new `verify-image-prerequisites` job (research D5), which itself never runs inside a container — it pulls the named image and inspects it directly, then exits before any agent step's job begins (FR-011, SC-005). |
| Check outcome | fail-all-at-once | A missing tool is reported alongside every other missing tool in the same failure, not one-at-a-time (FR-011: "naming every missing prerequisite rather than only the first one encountered"). |
| Drift protection | machine-checked on this pipeline's own PRs | Gate 23 (research D7) cross-references the canonical list against actual tool invocations in `run:` blocks repository-wide, failing when a newly-invoked tool is absent from the list (FR-011a). |

**Validation rules**: this is the pipeline's *own* environment-inspection
logic — the one place this feature validates anything at all (contrasted
with the adopter's `runner`/`container-image`/credential values, which are
never validated). It inspects the pulled image's contents, never the
adopter's chosen reference string (FR-008's carve-out, restated above).

**State transitions**: none. Re-run on every stage invocation that names an
image; never cached or persisted across runs (no artifact records "this
image already passed the check once").

**Ownership**: the canonical list itself is owned by this repository (a
maintained fact about what the pipeline needs), not by any adopter input.

## Relationship between the entities

Runner selection and Container image reference are independent
`workflow_call` inputs applied to the same job, always together (both, or
neither's `container:` half, depending on `container-image`'s emptiness).
Registry credentials are meaningful only when Container image reference is
non-empty — there is no independent lifecycle for "supply credentials" with
no image to pull. Image prerequisite contract is the one entity this feature
actively evaluates rather than passes through, and it only ever runs when
Container image reference is non-empty (mirroring Registry credentials'
same conditionality). This is a 1(Runner):1(Image):1(Credentials, if
Image):1(Prerequisite check, if Image) composition — not a persisted
relationship of any kind, recomputed fresh every stage invocation exactly as
specs/031's equivalent relationship was.
