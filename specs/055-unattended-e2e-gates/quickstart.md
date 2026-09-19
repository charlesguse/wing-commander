# Quickstart: Validating Unattended Passage of the Pipeline's Human Gates

This is a runbook for proving the feature works end-to-end, per the spec's
own Independent Tests (User Stories 1–5). It assumes
`specs/053-e2e-scratch-provisioning`'s test repository already exists and
is onboarded (App installed, `spec-request` label present, wrapper set
installed) — this feature adds one more prerequisite on top of that.

## Prerequisites

1. `WING_COMMANDER_AUTO_RELEASE_E2E_REPO` is already set (existing,
   `docs/setup.md:126`).
2. A dedicated GitHub user account exists, is invited as a **Write**
   collaborator to the test repository named above, and holds no access to
   this repository or any other (FR-011). This is a one-time maintainer
   act performed in the GitHub UI, outside the pipeline (FR-003a).
3. A classic personal access token for that account (not fine-grained — a
   fine-grained PAT can only reach repositories the account itself owns,
   never one it merely collaborates on, so it cannot be issued for this
   Write-collaborator setup), with `repo` scope, is stored as the
   repository secret `WING_COMMANDER_AUTO_RELEASE_E2E_MAINTAINER_TOKEN`.
   "Scoped to the test repository alone" (FR-011) is enforced by the
   account's own memberships plus `verify-e2e`'s runtime containment
   check, not by the token's own scoping. The account's username is
   stored alongside it as
   `WING_COMMANDER_AUTO_RELEASE_E2E_MAINTAINER_USERNAME`.
4. `WING_COMMANDER_AUTO_RELEASE_PAUSED` must be **cleared** for a validation
   dispatch, and a run that passes will cut a real release. The switch gates
   the `detect` job (`auto-release.yml:40`) and every job after it
   (`verify-e2e`, `decide-version`, `dispatch-release`, `report`)
   regardless of the trigger, so a dispatch while it is set does nothing; and
   a `pass` goes on to `decide-version` and `dispatch-release`. Plan for the
   release before clearing the switch (#396).

## Scenario 1 — a full unattended pass (User Story 1, Independent Test)

1. Ensure the checked-out branch (or the default branch, for a real
   scheduled run) carries new work relative to the latest release tag.
2. Dispatch `auto-release.yml` (or wait for the schedule, once the pause
   switch is eventually cleared per research.md D14).
3. Watch the test repository's lifecycle issue. Expect, with no human
   action:
   - a clarification question appears and is answered by the fixture
     maintainer identity within one poll interval;
   - the `spec-draft/<slug>` PR appears and is merged by the same
     identity;
   - the `plan/<slug>` PR appears and is merged;
   - the `spec/<slug>` (finalize) PR appears and is merged;
   - the issue closes with `stage:done`.
4. Confirm the workflow run's `verify-e2e` job output is
   `{"outcome":"pass", ...}` and the `report` job's summary names all four
   gates with their evidence (PR numbers, comment ids) per
   `data-model.md`'s Gate evidence table.
5. Confirm, in the test repository's own audit trail (issue/PR timeline,
   "merged by"), that every gate-satisfying act is attributed to the
   fixture maintainer identity, never a human account (FR-015, Acceptance
   Scenario 6).

**Pass condition**: SC-001, SC-002, SC-004 all hold for this run.

## Scenario 2 — a gate stall is reported distinctly (User Story 3,
Independent Test)

1. Temporarily revoke the fixture maintainer identity's write access to
   the test repository (or invalidate the secret), then dispatch a run.
2. Expect the attempt to still open the kickoff issue and reach the
   clarification gate, but the harness's reply attempt fails (or, if the
   revocation is caught by research.md D2's up-front check, the attempt
   ends `fail-infra` immediately instead — confirm which failure mode the
   specific revocation method triggers, since a revoked collaborator grant
   and an invalidated token surface differently).
3. Confirm the run's verdict is `fail-gate-stall` (or `fail-infra`, per
   step 2), not `fail-timeout`, and the durable failure issue's
   classification reads "gate stall" (or "infrastructure"), not
   "pipeline defect."
4. Restore access before the next scheduled/dispatched attempt.

**Pass condition**: SC-010 holds — the failure is never reported as
`fail-timeout`.

## Scenario 3 — no clarification question is asked (Edge Case)

Not independently forceable without changing the fixture feature's
request text (out of scope for a validation run) — covered instead by the
`auto-release-e2e-clarify-decision.sh` fixture test (contracts/gate-
decision-scripts.md) asserting `none` on a comment list with no marker
comment, and by the pass-path assertion (research.md D12) treating the
clarification gate as N/A rather than failing when it never opens.

## Scenario 4 — containment (User Story 4, Independent Test)

1. List the fixture maintainer identity's repository access (GitHub
   Settings → the account's own repository list, or an org audit log if
   the account belongs to one) and confirm it is exactly the one test
   repository.
2. Diff the published stage workflows (`.github/workflows/{intake,clarify,
   plan,tasks,implement,converge,finalize,cleanup,watchdog}.yml`) against
   the previous release tag; confirm no actor gate, merge gate, or human-
   gate condition changed.
3. Temporarily set `WING_COMMANDER_AUTO_RELEASE_E2E_REPO` to this
   repository's own `OWNER/NAME` and dispatch; confirm the existing
   self-repository refusal (research.md D3) still fires before any new
   code runs.

**Pass condition**: SC-003 and SC-008 hold.

## Scenario 5 — resume condition (User Story 5)

Not a dispatchable scenario — this is the real first production run.
Once Scenario 1 has passed for real (not a validation dispatch) and its
evidence is on tracker issue #385, open the follow-up PR research.md D14
describes: it records the evidence and clears
`WING_COMMANDER_AUTO_RELEASE_PAUSED` in the same change (FR-028).

**Pass condition**: SC-007.
