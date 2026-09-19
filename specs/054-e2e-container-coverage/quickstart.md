# Quickstart: Validating Container-Mode Coverage

This guide runs the spec's own Independent Tests (spec.md, User Stories
1-4) against a real repository. It assumes the one-time maintainer setup
below is already done — the feature's own FR-015 requires that setup to be
the *only* manual step, so this guide starts there rather than treating it
as optional.

## Prerequisites

1. `.github/workflows/wing-commander-e2e-reference-image.yml` has run at
   least once (via its `push` trigger or `workflow_dispatch`) and published
   `ghcr.io/charlesguse/wing-commander-e2e-image` — check its most recent
   run's job summary for the printed digest.
2. On the end-to-end test repository (the one named by this repository's
   `WING_COMMANDER_AUTO_RELEASE_E2E_REPO` variable): set the repository
   variable `WING_COMMANDER_CONTAINER_IMAGE` to that digest-pinned reference
   (`ghcr.io/charlesguse/wing-commander-e2e-image@sha256:...`). If the image
   was published private, also set
   `WING_COMMANDER_CONTAINER_REGISTRY_USERNAME`/`_PASSWORD` secrets there
   (docs/adoption.md, "Runners and container images").
3. Confirm `WING_COMMANDER_AUTO_RELEASE_E2E_CONTAINER_PAUSED` is unset (or
   `false`) on wing-commander itself, so the container leg is in rotation.

## Scenario A — a healthy container-mode run passes and records its mode (User Story 1, Acceptance Scenario 1)

1. Dispatch `auto-release.yml` (`workflow_dispatch`) on a day whose
   UTC day-of-year is odd (or wait for a scheduled run to land on one) so
   the run's derived mode is `container` — confirm by reading the `mode`
   step's output in the run log.
2. Wait for `verify-e2e` to reach a terminal verdict.
3. **Expected**: `outcome: "pass"`, `mode: "container"`,
   `container_image_configured: true`; the test repository's kickoff issue
   is closed with `stage:done`, and its timeline carries every stage label
   (`stage:spec stage:plan stage:tasks stage:implement stage:review`).
4. Open the `verify-image-prerequisites` job run for any scaffolded stage in
   the test repository (linked from `evidence_url` on a container-mode
   verdict) and confirm its `docker pull`/`docker login` log lines name the
   digest set in Prerequisites step 2.

## Scenario B — a broken container path is caught (User Story 1, Acceptance Scenario 2)

1. On a branch, introduce a deliberate container-path defect — e.g. add a
   `run:` step to a published stage that assumes bash-only syntax without
   pinning `shell: bash` inside a caller-supplied `container:` job (the
   exact defect class `container-shell-safety` exists to catch).
2. Point `WING_COMMANDER_AUTO_RELEASE_E2E_REPO`'s test repository at this
   branch's commit for a manually dispatched `auto-release.yml` run (or
   land the change on `main` if this is a pre-release drill), with the run's
   mode forced to `container` (temporarily flip
   `WING_COMMANDER_AUTO_RELEASE_E2E_CONTAINER_PAUSED` off if needed, or pick
   an odd day-of-year).
3. **Expected**: `outcome` is a `fail-*` class naming the broken stage,
   `mode: "container"`, and `report`'s failure body identifies the leg as
   container-mode (FR-007) — and `dispatch-release` does not run (SC-002).

## Scenario C — an unset image reference is a known gap, not yet a failure (User Story 2, Acceptance Scenario 1; FR-004 accepted gap, #390)

This scenario documents what the verification does NOT catch today; it is
not a pass/fail check. Do not run it expecting `fail-infra`.

1. Unset `WING_COMMANDER_CONTAINER_IMAGE` on the test repository.
2. Dispatch `auto-release.yml` on a day whose mode resolves to `container`.
3. **Observed today**: the wrappers fall back to hosted runners,
   `verify-image-prerequisites` succeeds vacuously, the chain completes, and
   the run reports `outcome: "pass"`, `mode: "container"` with
   `container_image_configured: true` -- indistinguishable from a real
   container run, and claiming an image was resolved that never was. Closing
   this needs read access to the test
   repository's variable or Actions run data (#390); once it exists, this
   scenario becomes `outcome: "fail-infra"` naming the unset variable.

## Scenario D — pausing the container leg (User Story 3, Acceptance Scenario 1)

1. Set `WING_COMMANDER_AUTO_RELEASE_E2E_CONTAINER_PAUSED` to `true` on
   wing-commander.
2. Dispatch `auto-release.yml` on a day whose date-parity would otherwise
   select `container`.
3. **Expected**: the run executes the default-runner leg instead,
   `mode: "default-runner"`, `paused: true`, and — if the leg passes —
   `dispatch-release` still runs (pausing the container leg does not pause
   auto-release, FR-009).

## Scenario E — Gate 62 catches Dockerfile/required-tools.txt drift (User Story 4, Acceptance Scenario 2)

1. Locally, add an entry to `.github/scripts/required-tools.txt` without
   updating `.github/docker/e2e-reference-image/Dockerfile`.
2. Run `python3 .github/scripts/run-local-gates.py` (or open a PR).
3. **Expected**: Gate 62 fails, naming the missing tool, before the change
   can reach the default branch (SC-008).

## Scenario F — alternation never gets stuck (Edge Case: "the alternation loses its place")

1. Manually cancel a scheduled `auto-release.yml` run mid-flight.
2. Dispatch (or wait for) the next run.
3. **Expected**: the next run's `mode` step still resolves from that run's
   own calendar date (research.md D1) — independent of the cancelled run's
   outcome — so the rotation is never observed "stuck" on one mode across
   consecutive calendar days.
