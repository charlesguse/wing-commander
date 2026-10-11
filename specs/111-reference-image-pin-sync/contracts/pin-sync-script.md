# Contract: the `sync-pins` job's sync step

Live contract; fixed like code.

The script is the `run:` block of the `Sync the reference-image pins` step
in `.github/workflows/wing-commander-e2e-reference-image.yml`, its single
home. It is inline rather than an `.github/actions/_shared/` script because
Gate 12 cannot resolve the token of a `gh` call inside a shared script; every
sync call names `GH_TOKEN="$SYNC_TOKEN"` on its own command line so Gate 12
can see it. `verify-reference-image-pin-sync.py` runs the block verbatim.

## Inputs (environment)
| Name | Source | Notes |
|---|---|---|
| `SYNC_TOKEN` | secret `WING_COMMANDER_REFERENCE_IMAGE_SYNC_TOKEN` | passed as `GH_TOKEN` on each sync `gh` call's own command line; never echoed |
| `IMAGE` | workflow `E2E_IMAGE` | |
| `DIGEST` | `build-and-publish` output | must match `^sha256:[0-9a-f]{64}$` |
| `THIS_REPO` | `github.repository` | |
| `E2E_REPO` | `vars.WING_COMMANDER_AUTO_RELEASE_E2E_REPO` | may be empty |
| `CHECKS_PASSED` | `startup-check` output | `true` required |
| `RUN_NUMBER` | `github.run_number` | ordering guard (FR-010) |
| `OUTCOME_FILE` | path | outcome JSON written here |
| `TABLE_FILE` | path | the rendered per-repository table, written once; the summary and the failure issue body both read it |
| `REF`, `DEFAULT_BRANCH` | `github.ref`, the repository's default branch | step 0 |
| `GH_TOKEN` | `github.token` | used only for the `gh run list` of step 3 (`actions: read`) |

## Behaviour (order is part of the contract)
0. `REF` is not `refs/heads/<DEFAULT_BRANCH>` → every repo `skipped` ("built from <ref>, not the default branch"); exit 0; no API call.
1. `CHECKS_PASSED != true` → every repo `skipped` ("image check did not pass"); exit 0 (the failed check run is itself the signal).
2. Malformed `DIGEST` or empty `IMAGE` → every repo `failed`; exit 1; no call to the variables API.
3. Superseded by a higher-numbered default-branch run → `skipped`, exit 0. A higher run supersedes when it concluded `success`, or when it is still finishing but its own `startup-check` and `sync-pins` jobs both already concluded `success` (FR-010). If the run list, or a still-finishing run's jobs, cannot be read → every repo `failed`, exit 1, no write.
4. Reach check: sorted reachable set must equal the sync set, else all `failed` ("credential reaches <names>"), exit 1, no write.
5. Probe each repo (read the variable); a 404 means not set yet (held `""`, written in step 6); any other failure → all `failed`, no write.
6. Per repo: equal → `current`; else write only `WING_COMMANDER_CONTAINER_IMAGE`; refused → `failed` with held/expected.
7. Append the per-repo table to `$GITHUB_STEP_SUMMARY`.

## Outputs
- `OUTCOME_FILE`: JSON array of `{repo,status,reason,held,expected}`.
- `TABLE_FILE`: the markdown table, header included.
- Step output `synced=true` only when every sync-set repository is `written` or `current`; only then is the failure issue closed.
- Exit 0 unless any outcome is `failed`.

## Invariants
- Only `gh variable set WING_COMMANDER_CONTAINER_IMAGE` is ever a write; only on sync-set repositories.
- No secret value appears in stdout, stderr, the summary or the outcome file.
- No other workflow or composite (`auto-release.yml` included) carries a write of the variable.
