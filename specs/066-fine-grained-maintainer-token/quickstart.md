# Quickstart: Validating the Fine-Grained Maintainer Token

This is a runbook for proving the feature works, per the spec's own
Independent Tests (User Stories 1–4). It assumes
`specs/055-unattended-e2e-gates`'s unattended end-to-end run already passes
under the classic credential — this feature changes what credential shape
the same run accepts, not what the run does.

## Prerequisites (one-time maintainer acts, outside the pipeline — FR-005)

1. Decide the credential shape you are migrating to. Dual acceptance
   (FR-003) means you can do this at your own pace; the steps below are for
   moving to the fine-grained shape.
2. **Transfer** the end-to-end test repository (`WING_COMMANDER_AUTO_RELEASE_E2E_REPO`)
   to the fixture maintainer identity's own account (research.md D8's
   fallout list, in order):
   a. Transfer ownership in the GitHub UI.
   b. If the transfer changed `OWNER/NAME`, update the
      `WING_COMMANDER_AUTO_RELEASE_E2E_REPO` repository variable to match.
   c. Reinstall the wing-commander App on the repository at its new
      location.
   d. Re-set the repository's own Claude credential secret (it moved with
      the repository if the transfer preserved secrets; verify rather than
      assume).
   e. Re-point the repository's container-image variable if it names the
      old `OWNER/NAME`.
   f. Confirm the `spec-request` label still exists on the repository
      (transfers preserve labels; verify).
   A partially completed transfer surfaces as the existing "test repository
   reachability" or "App installation" `fail-infra` branch (research.md
   D8) — no new check is added for this list, and none is needed.
3. Issue a **fine-grained personal access token** for the account, scoped
   to the transferred repository alone, with Contents (read), Issues
   (read and write), Pull requests (read and write) permissions and no
   Administration permission, and an expiry no longer than your release
   cadence (FR-006). Store it as
   `WING_COMMANDER_AUTO_RELEASE_E2E_MAINTAINER_TOKEN`, replacing the
   classic token.
4. (Optional) Set
   `WING_COMMANDER_AUTO_RELEASE_E2E_MAINTAINER_TOKEN_EXPIRY_WARNING_DAYS`
   if the default (14) does not suit your rotation cadence
   (research.md D2).
5. `WING_COMMANDER_AUTO_RELEASE_PAUSED` must be cleared for a live
   validation dispatch — the same caution specs/055's quickstart states
   applies here unchanged: a passing run cuts a real release.

## Scenario 1 — the fine-grained credential passes and drives all four gates (User Story 1, Independent Test)

1. Complete the Prerequisites above.
2. Dispatch `auto-release.yml` with new work relative to the latest release
   tag.
3. Confirm the "Confirm the fixture maintainer identity's credential" step
   reports `ok=true` with no verdict output.
4. Confirm the run proceeds exactly as specs/055's own Scenario 1 describes
   — clarification reply, three PR merges, all attributed to the fixture
   maintainer identity's login.

**Pass condition**: SC-001, SC-006 hold for this run; its evidence
(the run URL, and the head SHA it verified) is recorded on the PR or on
issue #506, per FR-022/SC-006.

## Scenario 2 — every misconfiguration is named before any spend (User Story 2, Independent Test)

Run against the extended Gate 67 (`verify-auto-release-credential-step.py`)
locally — no network call, no live dispatch needed for this scenario:

```text
python3 .github/scripts/verify-auto-release-credential-step.py
```

Confirm it exercises, and separately distinguishes, every row of
`data-model.md`'s Credential precheck outcome table: the malformed-shape
branch, an expired fine-grained credential, a fine-grained credential
missing Issues or Pull-requests write, one that grants Administration, and
a containment call that fails outright versus one that returns an empty
set. Confirm the gate's own mutations each break at least one assertion
(Constitution VIII).

**Pass condition**: SC-002 holds — zero of these scenarios reach a live
dispatch; every one is caught in Gate 67's stubbed-`gh` suite.

## Scenario 3 — containment still discriminates under the new shape (User Story 3, Independent Test)

1. Using Gate 67's stub, confirm: a correctly scoped fine-grained token
   passes containment; a token whose stubbed reachable set includes one
   extra repository fails, naming it with the account's login redacted; a
   stubbed `gh api user/repos` call that itself fails (nonzero exit) is
   reported as "containment could not be established," never as "reached 0
   repositories" (research.md D4).
2. Live-side (optional, at your discretion): issue a fine-grained token
   scoped to "all repositories" for an account that also owns something
   else, and confirm a dispatch ends `fail-infra` naming the extra
   repository — demonstrating research.md D3's claim that the existing
   invariant already catches this edge case without new code.

**Pass condition**: SC-005 holds — the containment check is demonstrably
able to fail, and its three outcomes (pass / over-scoped / unobservable)
never collapse into two.

## Scenario 4 — one canonical statement, everywhere else a pointer (User Story 4, Independent Test)

1. Run the new canonical-statement gate (`contracts/canonical-statement-
   gate.md`) locally, as part of the full gate suite:

   ```text
   python .github/scripts/run-local-gates.py
   ```

2. Confirm it passes against the post-migration text of `docs/setup.md`,
   `auto-release.yml`'s comment block, Gate 67's own docstring/scenarios,
   and specs/055's annotated D1/D2 and Clarifications session.
3. Reintroduce, temporarily, an unqualified "not fine-grained" sentence at
   one of the three pointer sites and confirm the gate fails naming that
   site; revert the change.

**Pass condition**: SC-004 holds — the sweep finds zero contradicting
statements today, and is demonstrably able to fail when one reappears.

## Notes on what this quickstart does not (re-)test

Everything specs/055-unattended-e2e-gates' own quickstart already covers
about the four human gates themselves — the clarification reply, the three
PR merges, the `fail-gate-stall` classification — is unchanged by this
feature and is not re-verified here; this feature changes only which
credential shape authenticates the identity that drives them.
