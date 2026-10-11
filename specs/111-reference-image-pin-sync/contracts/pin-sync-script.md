# Contract: `.github/actions/_shared/sync-reference-image-pin.sh`

Live contract; fixed like code.

## Inputs (environment)
| Name | Source | Notes |
|---|---|---|
| `SYNC_TOKEN` | secret `WING_COMMANDER_REFERENCE_IMAGE_SYNC_TOKEN` | exported as `GH_TOKEN` only for the script's own `gh` calls; never echoed |
| `IMAGE` | workflow `E2E_IMAGE` | |
| `DIGEST` | `build-and-publish` output | must match `^sha256:[0-9a-f]{64}$` |
| `THIS_REPO` | `github.repository` | |
| `E2E_REPO` | `vars.WING_COMMANDER_AUTO_RELEASE_E2E_REPO` | may be empty |
| `CHECKS_PASSED` | `startup-check` output | `true` required |
| `RUN_NUMBER` | `github.run_number` | ordering guard (FR-010) |
| `OUTCOME_FILE` | path | outcome JSON written here |

## Behaviour (order is part of the contract)
1. `CHECKS_PASSED != true` → every repo `skipped` ("image check did not pass"); exit 0 (the failed check run is itself the signal).
2. Malformed `DIGEST` or empty `IMAGE` → every repo `failed`; exit 1; no call to the variables API.
3. Superseded by a higher successful run → `skipped`, exit 0.
4. Reach check: sorted reachable set must equal the sync set, else all `failed` ("credential reaches <names>"), exit 1, no write.
5. Probe each repo (read the variable); failure → all `failed`, no write.
6. Per repo: equal → `current`; else write only `WING_COMMANDER_CONTAINER_IMAGE`; refused → `failed` with held/expected.
7. Append the per-repo table to `$GITHUB_STEP_SUMMARY`.

## Outputs
- `OUTCOME_FILE`: JSON array of `{repo,status,reason,held,expected}`.
- Exit 0 unless any outcome is `failed`.

## Invariants
- Only `gh variable set WING_COMMANDER_CONTAINER_IMAGE` is ever a write; only on sync-set repositories.
- No secret value appears in stdout, stderr, the summary or the outcome file.
- `auto-release.yml` neither calls nor reads this script.
