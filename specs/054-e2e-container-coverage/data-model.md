# Data Model: Container-Mode Coverage in End-to-End Release Verification

This feature has no application data model — it is a GitHub Actions
pipeline change. The entities below are the spec's Key Entities section
(spec.md), made concrete against the design decisions in research.md: the
shapes that actually appear in `auto-release.yml`'s step outputs, verdict
JSON, and the two new files research.md introduces.

## Execution mode

The container-mode leg's unit of coverage. Not a persisted value (research.md
D1) — computed once per run by the `mode` step and threaded through as a
step output for the rest of `verify-e2e`.

| Field | Type | Values | Notes |
|---|---|---|---|
| `mode` | string enum | `"container"` \| `"default-runner"` | Derived from UTC day-of-year parity (D1); overridden to `"default-runner"` when `WING_COMMANDER_AUTO_RELEASE_E2E_CONTAINER_PAUSED` is `true` (D3). |
| `paused` | boolean | — | `true` only when the override in the row above fired; carried separately from `mode` so the report can distinguish "today's turn was default-runner" from "container was due but paused" (FR-009's Acceptance Scenario). |

## Reference image

The minimal container image the container-mode leg pins. Not a runtime
record — a build artifact plus the two repository-variable/documentation
facts that describe it.

| Field | Where it lives | Notes |
|---|---|---|
| Build definition | `.github/docker/e2e-reference-image/Dockerfile` (this repository) | Installs exactly the tools `.github/scripts/required-tools.txt` names (FR-016, FR-019). |
| Published location | `ghcr.io/charlesguse/wing-commander-e2e-image`, tagged `:latest` + commit SHA | Published by `.github/workflows/wing-commander-e2e-reference-image.yml` (research.md D5). |
| Pin used by the container leg | `WING_COMMANDER_CONTAINER_IMAGE` repository variable, **set on the test repository** | Maintainer-set once, by digest, never by the moving `:latest` tag (Edge Case: "the image changes underneath the pin"). |
| Visibility | Public (default, research.md D4) | Private remains supported via the existing `WING_COMMANDER_CONTAINER_REGISTRY_USERNAME`/`_PASSWORD` secrets on the test repository (FR-014), unchanged mechanism. |
| Upkeep trigger | A change to `.github/scripts/required-tools.txt` | Documented in docs/adoption.md (FR-013); enforced at PR time by Gate 62 (research.md D6) and at run time by each stage's existing `verify-image-prerequisites` job. |

## Verification leg

One complete end-to-end feature run through the stage chain in a single
execution mode, against a test repository, producing exactly one verdict.
Unchanged in shape from the existing `verify-e2e` job — this feature adds
fields to its output, not a new entity.

| Field | Type | Notes |
|---|---|---|
| `mode` | Execution mode (above) | New. |
| `verified_head` | string (SHA) | Existing. |
| `verdict` | Verdict (below) | Existing, extended. |

## Verdict

The machine-readable outcome of a leg. Existing shape
(`{outcome, verified_head, failing_check, expected, observed, evidence_url}`),
extended per research.md D9:

| Field | Type | Values / Notes |
|---|---|---|
| `outcome` | string enum | Existing: `"pass"` \| `"fail-infra"` \| `"fail-timeout"` \| `"fail-incomplete"` \| `"fail-wrong-output"`. Unchanged vocabulary (Assumptions: "the vocabulary this feature extends, rather than a new taxonomy"). |
| `verified_head` | string (SHA) | Existing, unchanged. |
| `failing_check` | string | Existing, unchanged; for a container-leg failure, its value now includes which stage failed, satisfying FR-007 without a separate field. |
| `expected` / `observed` | string | Existing, unchanged. |
| `evidence_url` | string (URL or reference) | Existing field, new use per D7: for a container-mode run, points at the leg's `verify-image-prerequisites` job run rather than (or in addition to) the repository-level pointer used today — this is how "the image reference used" (FR-003) is recorded without a new App permission. |
| `mode` | string enum | **New.** `"container"` \| `"default-runner"` — always present, satisfying FR-003/FR-020 ("state explicitly when container mode was not exercised", "runs must remain distinguishable by mode after the fact"). |
| `container_image_configured` | boolean | **New.** Present only when `mode == "container"`. Defaults to `false` on every container-mode verdict (`_shared/auto-release-verdict.sh`), so "unknown" never reads as "true"; only the poll step's own `pass`, reached once the whole scaffolded chain closed `stage:done`, sets it `true`. That distinguishes "the leg was configured to run but the image was never resolved" from "the leg ran and failed inside the image" (FR-006) on every route except one: a variable left **unset** on the test repository reaches that same `pass` and so carries `true` although nothing ran in a container. That is the accepted gap on FR-004 (tracked in #390), not an infra-class failure yet. |

## Required-tool list

Unchanged entity — `.github/scripts/required-tools.txt` remains the sole
canonical source (Constitution's existing "one home" convention). This
feature adds a *second consumer* (Gate 62, D6, builds and inspects the real
reference image against it) alongside the existing consumers (each stage's
embedded `REQUIRED_TOOLS=` literal, Gate 23's textual drift check, the
`verify-image-prerequisites` job at run time).
