# Quickstart: validating auto-release end-to-end

This is a maintainer-run validation guide, not implementation code. It
proves the feature works the way `spec.md`'s Independent Test sections
for each user story describe. See `contracts/` for the exact interfaces
and `data-model.md` for the shapes referenced below.

## Prerequisites

1. A dedicated test repository, onboarded exactly as
   `contracts/e2e-repository-wiring.md`'s "What a maintainer sets up
   once" section describes (App install, Claude credential, `spec-request`
   label).
2. In this repository: `WING_COMMANDER_AUTO_RELEASE_E2E_REPO` set to that
   repository's `OWNER/NAME`.
3. At least one existing `vX.Y.Z` release tag on this repository (the
   feature has no baseline otherwise — see Scenario 3).

## Scenario 1 — no-op path (User Story 3)

1. Confirm `main`'s tip is exactly the commit the latest release tag
   points at (`git rev-parse HEAD` vs. `git rev-parse <tag>`).
2. Dispatch `auto-release.yml` manually (`workflow_dispatch`, FR-005).
3. **Expect**: the run completes with the `verify-e2e`, `decide-version`,
   and `dispatch-release` jobs skipped; the `report` job's summary states
   "no new work since `<tag>`"; the test repository is untouched (no new
   issue, no branch reset); no agent step ran anywhere.

## Scenario 2 — a passing run cuts a release (User Story 1)

1. Merge a trivial, non-breaking change to `main` (no `release:minor`
   label on its PR).
2. Dispatch `auto-release.yml` manually (don't wait for the schedule).
3. **Expect**: `verify-e2e` resets the test repository's default branch,
   scaffolds it at the new head, opens and labels an issue there, and
   polls it through `stage:spec` → … → `stage:done` (watch the test
   repository's own lifecycle issue directly to see this happen in real
   time — it is a real Wing Commander run, indistinguishable from an
   adopter's own). `decide-version` computes a patch bump. `dispatch-
   release` triggers `release.yml`, which creates `vX.Y.<Z+1>` and force-
   moves the floating `vX` tag. `report`'s summary states `released
   vX.Y.<Z+1>`.
4. Confirm the new tag exists at exactly the commit merged in step 1, and
   the release notes show a `## Breaking changes` section stating "None."
   — indistinguishable in shape from a hand-dispatched release (Scenario
   6 of User Story 1's acceptance criteria).
5. Re-dispatch `auto-release.yml` immediately with no further merges.
   **Expect**: no-op (Scenario 1's assertions again) — one head yields at
   most one release (FR-022).

## Scenario 3 — minor label (User Story 1, acceptance scenario 3)

1. Merge a PR labeled `release:minor` (and, optionally, one or more
   unlabelled PRs alongside it in the same range).
2. Dispatch `auto-release.yml`.
3. **Expect**: `decide-version` resolves `bump: minor` regardless of how
   many unlabelled merges accompany it; the cut release is `vX.<Y+1>.0`.

## Scenario 4 — a failing verification blocks the release and reports why
(User Story 2)

1. Force a failure in a controlled way — the simplest lever is pointing
   `WING_COMMANDER_AUTO_RELEASE_E2E_REPO` at a repository the App is not
   installed on (`fail-infra`), or temporarily editing the trivial
   feature's fixture to something a stage will reject (`fail-incomplete`
   / `fail-wrong-output`).
2. Dispatch `auto-release.yml`.
3. **Expect**: zero tags created or moved; the latest release tag
   byte-identical to before; a new (or updated) issue on this repository
   labeled `auto-release:failed`, naming the verified head, the failing
   check, and expected-vs-observed, classified as infrastructure or
   pipeline defect per which failure mode was forced — readable without
   opening any workflow run log (SC-007).
4. Dispatch again without fixing anything. **Expect**: the same
   `auto-release:failed` issue gains a new comment rather than a second
   issue being filed (FR-028).
5. Undo the forced failure and dispatch once more. **Expect**: a passing
   run per Scenario 2, and the `auto-release:failed` issue closes with a
   comment naming the version that shipped.

## Scenario 5 — kill switch (User Story 5)

1. Set `WING_COMMANDER_AUTO_RELEASE_PAUSED` to `true`.
2. Dispatch `auto-release.yml` (or wait for the schedule).
3. **Expect**: every job in the run shows as skipped in the Actions UI
   itself — no job starts, nothing is billed, the test repository is
   untouched.
4. Clear the variable and dispatch again. **Expect**: normal behavior
   resumes (whichever of Scenarios 1–4 applies to the current state of
   `main`).

## Scenario 6 — breaking changes stay manual (User Story 4)

Confirm by inspection rather than by running anything: `contracts/
release-dispatch.md`'s version-computation section shows the only two
`bump` values this feature can produce are `patch` and `minor`; `breaking`
is hardcoded `false` in every dispatch (`contracts/release-dispatch.md`'s
input table). There is no code path, input, or label that flips it. The
existing manual dispatch (`breaking: true` with migration notes) is
untouched by this feature (FR-021) — confirm by dispatching `release.yml`
directly exactly as before and observing no new precondition.
