# Quickstart: Validating Container-Mode Evidence

This guide validates the feature end-to-end against a real (or fixture-
driven) `auto-release.yml` container-mode turn. It maps directly onto
spec.md's Acceptance Scenarios; run it after implementation, before
declaring FR-001/FR-006/FR-015 satisfied.

## Prerequisites

- `WING_COMMANDER_AUTO_RELEASE_E2E_MAINTAINER_TOKEN` and
  `WING_COMMANDER_AUTO_RELEASE_E2E_MAINTAINER_USERNAME` set on this
  repository (already required by `specs/055`; unchanged here).
- A dedicated end-to-end test repository configured per `docs/setup.md`
  (`WING_COMMANDER_AUTO_RELEASE_E2E_REPO`).
- Write access to the test repository's `WING_COMMANDER_CONTAINER_IMAGE`
  variable, to manipulate it between scenarios.
- `WING_COMMANDER_AUTO_RELEASE_E2E_CONTAINER_PAUSED` left unset (or `false`)
  so container-mode turns are reachable.

## Scenario 1 — Unset variable fails before kickoff (spec Acceptance Scenario 1, FR-002, FR-011, SC-001, SC-003)

1. Unset `WING_COMMANDER_CONTAINER_IMAGE` on the test repository.
2. Force or wait for a container-mode turn of `auto-release.yml`.
3. Confirm: the run ends with `outcome: fail-infra`,
   `failing_check: "container image not configured on the test repository"`,
   `container_image_configured: false`.
4. Confirm: no issue was created on the test repository for this turn
   (check the test repository's issue list directly — the kickoff step
   must not have run).
5. Confirm: the test repository is left clean (no dangling scaffolded
   branch state a later run can't reuse).

## Scenario 2 — Empty value is treated the same as unset (Acceptance Scenario 2)

1. Set `WING_COMMANDER_CONTAINER_IMAGE` to an empty string on the test
   repository (not unset — an explicit empty value).
2. Repeat Scenario 1's run and assertions; the verdict must be identical
   in shape to Scenario 1's.

## Scenario 3 — Correctly configured turn reaches a real pass (Acceptance Scenario 3, SC-002)

1. Set `WING_COMMANDER_CONTAINER_IMAGE` on the test repository to exactly
   this repository's own pinned reference image (`provision-e2e-target.sh`
   sets this automatically; confirm it matches).
2. Run a full container-mode turn to completion.
3. Confirm: `outcome: pass`, `container_image_configured: true`, and the
   verdict's evidence fields record both the matching image reference and
   the observation that the stage jobs executed inside a container.
4. **Required before trusting this path in CI** (research.md D4): fetch
   this run's own Jobs API response
   (`gh api repos/<test-repo>/actions/runs/<id>/jobs`) and inspect a stage
   job's `steps[]` array by hand. Confirm an `Initialize containers` step
   is present. If it is absent, misnamed, or inconsistent, do not ship the
   `steps[]`-based check — fall back to the job-log scan documented in
   research.md D4 and repeat this confirmation.

## Scenario 4 — Unpullable/unauthorized image keeps its existing classification (Acceptance Scenario 4)

1. Set `WING_COMMANDER_CONTAINER_IMAGE` on the test repository to a value
   that is non-empty, matches this repository's pin is not required here —
   use a value the test repository cannot pull or authorize (e.g. a
   private, inaccessible reference), distinct from the drift case.
2. Run a container-mode turn.
3. Confirm: the existing chain-stop-notice detection still classifies this
   as it does today (`failing_check` unchanged from pre-feature behavior),
   not reclassified as "not configured" or "drift."

## Scenario 5 — Default-runner turn is unaffected (Acceptance Scenario 5, SC-008)

1. Force a default-runner-mode turn (or wait for the alternation).
2. Confirm: no container-evidence step runs, no new `failing_check` value
   appears, and the run's duration/outcome distribution matches
   pre-feature behavior.

## Scenario 6 — Drift is named and blocked (Acceptance Scenario 6)

1. Set `WING_COMMANDER_CONTAINER_IMAGE` on the test repository to a
   non-empty value that differs from this repository's own pin.
2. Run a container-mode turn.
3. Confirm: `outcome: fail-infra`,
   `failing_check: "container image configured but does not match this
   repository's pin"`, `expected` names this repository's pin, `observed`
   names the drifted value, no release dispatched.

## Scenario 7 — Configured but never consumed (Acceptance Scenario 7, FR-006)

1. Set `WING_COMMANDER_CONTAINER_IMAGE` correctly, but arrange for the
   scaffolded wrapper's passthrough to not actually apply it (e.g. a
   deliberately broken fixture for this test only — do not ship this
   state).
2. Run a container-mode turn to completion.
3. Confirm: `outcome: fail-infra`,
   `failing_check: "container image configured but stage jobs did not
   execute inside a container"`, naming the stage jobs that ran on hosted
   runners, no release dispatched.

## Scenario 8 — Evidence unreadable fails closed (US2 AC1/AC2)

1. Temporarily invalidate `WING_COMMANDER_AUTO_RELEASE_E2E_MAINTAINER_TOKEN`
   (or its permission) in a disposable test run.
2. Confirm: `outcome: fail-infra`,
   `failing_check: "container-mode evidence unreadable"`, naming the
   credential to restore.
3. Separately, simulate a rate-limited read (or verify via the gate's
   fixture, since inducing a real GitHub rate limit is impractical) and
   confirm the distinct `failing_check: "container-mode evidence
   rate-limited"` value.

## Gate validation (FR-015, SC-006)

Run the new gate locally and confirm every fixture in
`contracts/container-evidence-decision-script.md`'s behavior table passes,
then confirm the gate fails when the `pass`-writing `write_verdict` call's
guard is deliberately loosened (a mutation test, matching Gate 60/64's
existing idiom):

```text
python .github/scripts/run-local-gates.py
```

## Documentation check (FR-016, SC-007)

```text
grep -ri "known limitation" docs/setup.md docs/architecture.md
grep -ri "accepted gap" specs/054-e2e-container-coverage/spec.md specs/054-e2e-container-coverage/contracts/e2e-container-coverage.md
```

Both MUST return no matches referring to the unset container-image
variable after this feature ships.
