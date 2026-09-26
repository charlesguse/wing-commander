# Contract: Container-Mode Coverage in End-to-End Release Verification

This feature adds no new `workflow_call` interface — the published stage
contract (`intake.yml` … `cleanup.yml`, `rebase.yml`, and the composite
actions under `.github/actions/**`) is unchanged (research.md D2). The
contract surfaces this feature *does* introduce or change are: two
repository variables, an extension to `auto-release.yml`'s existing verdict
JSON, and one new gate. Each is documented here the way
`specs/038-runner-container-passthrough/contracts/runner-container-passthrough.md`
documents the existing container-mode contract it builds on.

## 1. Repository variables

### `WING_COMMANDER_CONTAINER_IMAGE` (existing name, new consumer)

- **Set on**: the end-to-end test repository named by
  `WING_COMMANDER_AUTO_RELEASE_E2E_REPO` (not on wing-commander itself).
- **Existing behavior** (unchanged): every scaffolded stage wrapper already
  reads this variable and forwards it as the `container-image` input to the
  published stage it calls (docs/adoption.md, "Runners and container
  images").
- **New behavior this feature adds**: on a scheduled run whose derived mode
  (below) is `container`, this variable is what makes the leg exercise
  container mode — no new code reads it; it is consumed exactly as an
  adopter's own configuration would be. On a run whose mode is
  `default-runner`, `auto-release.yml`'s `scaffold` step blanks the copied
  wrapper's reference to this variable before pushing, so a permanently-set
  value here does not leak into a default-runner-leg run.
- **Unset behavior**: detected (FR-004; the gap the repository owner
  accepted on #373, tracked in #390, is closed). See
  `specs/067-e2e-container-image-evidence/contracts/container-evidence-
  outcomes.md` for the current behavior and `failing_check` vocabulary.
- **Value shape**: an image reference pinned **by digest**
  (`ghcr.io/<owner>/<image>@sha256:...`), never a moving tag (Edge Case:
  "the image changes underneath the pin").

### `WING_COMMANDER_AUTO_RELEASE_E2E_CONTAINER_PAUSED` (new)

- **Set on**: wing-commander itself (this repository), read the same way
  `WING_COMMANDER_AUTO_RELEASE_PAUSED` already is.
- **Default**: unset (container leg active, subject to alternation).
- **Behavior when `"true"`**: every scheduled run's `mode` step forces
  `mode: "default-runner"` regardless of the day-of-year parity result, and
  the verdict/report state "container mode not exercised: paused" (FR-009).
- **Scope**: independent of `WING_COMMANDER_AUTO_RELEASE_PAUSED` — pausing
  the container leg does not pause auto-release as a whole, and vice versa.

## 2. Verdict JSON extension

Existing shape (unchanged fields): `{outcome, verified_head, failing_check,
expected, observed, evidence_url}`. New fields, always present as of this
feature:

```jsonc
{
  "outcome": "pass | fail-infra | fail-timeout | fail-incomplete | fail-wrong-output",
  "verified_head": "<sha>",
  "failing_check": "<string, names the stage for a container-leg failure>",
  "expected": "<string>",
  "observed": "<string>",
  "evidence_url": "<url — for a container-mode run, the verify-image-prerequisites job run>",
  "mode": "container | default-runner",
  "container_image_configured": "<boolean, present only when mode == container>"
}
```

Consumers of this JSON today (`decide-version`, `report`) already read it via
`fromJSON(needs.verify-e2e.outputs.verdict || '{}')` and must tolerate
unknown/additional fields (they already do, reading named fields rather than
asserting an exact key set) — no consumer-side breaking change.

## 3. Gate 62 — reference image tool set agrees with the canonical list

- **Subject**: `.github/docker/e2e-reference-image/Dockerfile`, built
  locally (no push) and inspected the same way every stage's
  `verify-image-prerequisites` job inspects an adopter's image:
  `docker run --rm --entrypoint sh "$IMAGE" -c 'for t in $REQUIRED_TOOLS; do command -v "$t" || echo "missing:$t"; done'`.
- **Canonical list**: `.github/scripts/required-tools.txt` (unchanged file,
  new consumer).
- **Registration**: a step in `.github/workflows/lint-workflows.yml`
  invoking `python3 .github/scripts/verify-gate-62.py`, plus a
  `--selftest` companion step, following Gates 23/27's existing
  registration shape so `run-local-gates.py` and `verify-gate-wiring.py`
  pick it up with no separate manifest (Constitution VIII: reachable
  through the gate registry, runs the same subject locally and in CI).
- **Failure mode**: names every missing tool at once (SC-007), the same
  one-container-start-checks-everything shape the run-time prerequisite
  check already uses — not a per-tool failure that stops at the first
  miss.
- **Trigger**: runs unconditionally on every PR through `lint-workflows.yml`
  (no path-filtered trigger — matches this repository's existing
  convention; no gate in `lint-workflows.yml` is currently path-filtered),
  so it is also triggered by the one class of change it exists to catch: an
  edit to the Dockerfile or to `required-tools.txt` (Constitution VIII: "a
  gate MUST be triggered by changes to the tree or document it checks").

## 4. Reference image build/publish workflow

- **File**: `.github/workflows/wing-commander-e2e-reference-image.yml`.
- **Not a published stage**: no `workflow_call` trigger; `on: push` (paths
  `.github/docker/e2e-reference-image/**`,
  `.github/scripts/required-tools.txt`) and `workflow_dispatch`.
- **Output**: pushes `ghcr.io/charlesguse/wing-commander-e2e-image:latest`
  and `:<sha>`, and prints the resulting digest in the job summary for a
  maintainer to copy into the test repository's `WING_COMMANDER_CONTAINER_IMAGE`
  (this workflow never writes that variable itself — no mechanism exists for
  wing-commander to write an arbitrary test repository's configuration, and
  none is added by this feature).
