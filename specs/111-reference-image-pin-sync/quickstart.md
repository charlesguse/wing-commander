# Quickstart: validating the pin sync

Prerequisites: secret `WING_COMMANDER_REFERENCE_IMAGE_SYNC_TOKEN` set
(Variables write on this repository and the test repository only);
`WING_COMMANDER_AUTO_RELEASE_E2E_REPO` set.

## Local (deterministic)
1. `python .github/scripts/run-local-gates.py` — includes
   `verify-reference-image-pin-sync.py`, which drives the script against a
   stubbed `gh` for each case in [contracts/pin-sync-script.md](contracts/pin-sync-script.md).
   Expect: all cases pass (written, current, over-reach, under-permission,
   refused write, malformed digest, test repository unset, superseded).

## After merge (proof, Actions only)
1. `gh workflow run wing-commander-e2e-reference-image.yml`.
2. Read the run: `startup-check` concludes, then `sync-pins` summary lists
   both repositories as `written` or `current`.
3. `gh variable get WING_COMMANDER_CONTAINER_IMAGE` on both repositories
   equals `<image>@<digest>` from the build summary (SC-001).
4. Re-dispatch: summary reports both `current` (US1 scenario 3).
5. Failure injection: temporarily unset the secret, dispatch, expect a red run
   and one open `reference-image-sync:failed` issue; dispatch again and
   expect that issue commented, not duplicated (SC-003). Restore the secret.
6. Next container-mode auto-release run passes the pin-match check.
