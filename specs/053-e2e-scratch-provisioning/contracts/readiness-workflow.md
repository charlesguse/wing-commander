# Contract: the generalized readiness-check workflow

**Location**: `.github/workflows/auto-update-spec-kit-scratch-preflight.yml`,
generalized in place (research.md D2) rather than replaced by a new
dispatcher. This is a `wing-commander-*.yml`-style consuming-instrument
workflow (Constitution VII), not a published stage — it is never pinned by
an adopter and is free to change.

## Trigger

`workflow_dispatch` only, same as today — no pause kill-switch, by design
(this is the tool a maintainer or agent dispatches specifically to diagnose
why a target is not ready, so it must run even while the main pipeline is
paused).

## Inputs

| Input | Type | Default | Description |
|---|---|---|---|
| `target` | string | `''` | `OWNER/NAME` to check. Empty string preserves today's behaviour: read `vars.WING_COMMANDER_AUTO_UPDATE_SPEC_KIT_E2E_SCRATCH_REPO`. |
| `profile` | choice: `auto-release` \| `spec-kit-scratch` | `spec-kit-scratch` | Selects the `TargetProfile`. Default preserves today's single-element scratch check as the no-input-changed behaviour (FR-011: existing hand-onboarded targets keep working unchanged). |

## Behavior

1. Resolve `target`: if the input is empty, fall back to
   `vars.WING_COMMANDER_AUTO_UPDATE_SPEC_KIT_E2E_SCRATCH_REPO` when
   `profile == spec-kit-scratch`, or to
   `vars.WING_COMMANDER_AUTO_RELEASE_E2E_REPO` when
   `profile == auto-release`. Fails loudly (constitution VIII), naming
   `docs/setup.md`, if the resolved value is unset or malformed — same
   error shape the job already produces today.
2. Mint an App-scoped token via `create-github-app-token@v3` with `owner`/
   `repositories` narrowed to the resolved target, exactly as today.
   `continue-on-error: true`, rechecked next step (unchanged pattern).
3. Source `.github/scripts/e2e-provisioning/checks.sh` (checked out from
   this repository at the dispatch ref) and invoke
   `provision-e2e-target.sh --repo <target> --profile <profile> --check-only`
   using the minted token as `GH_TOKEN` — no privileged action is ever
   attempted from this workflow, so the App token's existing permissions
   (Contents read/write for the scratch profile; whatever the auto-release
   profile's checks need to read) are sufficient without any grant change
   (FR-003, SC-005).
4. Write the `ReadinessReport` as a `GITHUB_STEP_SUMMARY` table (one row per
   element, ✅/❌, remaining action for each ❌) and exit non-zero if
   `ready` is `false` — same "loud failure, not a silent pass" contract the
   existing preflight job already honors (User Story 2, Acceptance
   Scenario 3; Constitution VIII).

## Cost contract (SC-006)

Zero Claude quota (no agent step of any kind), one job, no checkout beyond
this repository's own scripts, no clone of the target, no push — matching
today's documented cost of "one runner minute and zero Claude quota... no
checkout, no clone, no push, no agent step, no writes of any kind."

## Compatibility

A dispatch with no inputs reproduces today's exact behaviour byte-for-byte
(same target resolution, same single-element scratch check, same summary
shape) — this is what keeps FR-011 satisfied while the job is generalized
to also accept `profile: auto-release`.
