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
1. `CHECKS_PASSED != true` → every repo `skipped` ("image check did not pass"); exit 0. Defensive: the `sync-pins` job runs only after a passed check (a failed-check run must not queue in the concurrency group, where it would cancel a passed run's pending sync), and `startup-check`'s verdict step writes the skip to the summary itself.
2. Malformed `DIGEST` or empty `IMAGE` → every repo `failed`; exit 1; no call to the variables API.
3. Never move the pins back (FR-010). The last 100 default-branch runs are read newest first, and each higher-numbered run's attempts newest first. An attempt whose sync step concluded `success` → this run `skipped` ("superseded by run N"), exit 0 (`sync-pins` runs only after a passed check, so this needs no `startup-check` line; a "re-run failed jobs" attempt may not list one). An attempt whose `sync-pins` job ended any other way than `success` or `skipped`, and whose `startup-check` is `success` or not listed (`sync-pins` runs only after a passed check, so a "re-run failed jobs" attempt needs no `startup-check` line) (sync step failed; job cancelled while pending in the concurrency group, timed out, or lost its runner) → every repo `failed` ("newer run N passed its check but its sync did not finish (<conclusion>); re-run that run's sync-pins job, not this one"), exit 1, no write, since this older digest could roll back a partial newer write. The newest attempt of a run that is not `completed`, whose `sync-pins` has not ended or whose check has not finished → this run proceeds, that run's older attempts can only supersede, and no lower-numbered run is read (it decides after this run and writes last). An attempt whose check failed or was cancelled (`sync-pins` skipped or cancelled with it) leaves the decision to that run's older attempts. If the run list, or a newer run's jobs, cannot be read, or a run-list row (number, id, attempt, status) does not parse → every repo `failed`, exit 1, no write. The `sync-pins` job itself runs only for a default-branch build whose check passed, so neither a branch build nor a failed check queues in the concurrency group and cancels a pending sync.
4. Reach check: `user/repos?affiliation=owner,collaborator,organization_member` lists the repositories the token can see, each with its `private` flag. A listed repository outside the sync set is reached, with no further call, when the token is not fine-grained (no `github_pat_` prefix: a classic token carries its user's access to every repository it lists, push included) or the repository is private (a fine-grained token lists a private repository only when it selects it). A fine-grained token can read every public repository, so that list alone is not reach for a public one: it is probed with `GET repos/<r>/actions/variables?per_page=1` under the sync token: 200 → reached; 404, or a 403 that is not a rate limit (`rate limit` or `abuse` in the message) → not reached (a token's permissions are the same on every repository it selects, and one that cannot read a repository's variables cannot write them); any other answer → all `failed` ("could not tell whether WING_COMMANDER_REFERENCE_IMAGE_SYNC_TOKEN reaches <r> (HTTP NNN)"), exit 1, no write. Any reached repository outside the sync set, or any sync-set repository missing from the list → all `failed` ("credential reaches <names>[; does not reach <names>]"), exit 1, no write.
5. Probe each repo (read the variable); a 404 means not set yet (held `""`, written in step 6); any other failure → all `failed`, no write.
5b. Write-permission proof (FR-005): each repo whose held value is non-empty and differs is rewritten with that same held value; a refusal → all `failed`, exit 1, nothing changed.
6. Per repo: equal → `current`; else write only `WING_COMMANDER_CONTAINER_IMAGE`, repos with no value yet first; refused → `failed` with held/expected, and every repo not yet written → `failed` ("not written: the write on <repo> was refused"), with no further write. Failure reasons carry the gh call's `HTTP NNN` status when it named one, never its message.
7. Append the per-repo table to `$GITHUB_STEP_SUMMARY`.

## Outputs
- `OUTCOME_FILE`: JSON array of `{repo,status,reason,held,expected}`.
- `TABLE_FILE`: the markdown table, header included. A test repository that is unset, or names this repository, gets a `skipped` row.
- Step output `pinned=true` only when this repository's own row (`THIS_REPO`, compared case-insensitively) is `written` or `current`: this run's digest is now this repository's pin. It gates the dogfood copy below, so a superseded, skipped or failed run never copies its digest.
- Step output `synced=true` only when every outcome, the test repository's included, is `written` or `current`; only then is the failure issue closed. Table cells are escaped (`|`, backticks, newlines).
- Exit 0 unless any outcome is `failed`.

## Invariants
- Only `gh variable set WING_COMMANDER_CONTAINER_IMAGE` is ever a write; only on sync-set repositories.
- No secret value appears in stdout, stderr, the summary or the outcome file.
- No other workflow or composite (`auto-release.yml` included) carries a write of the variable.

# The dogfood copy step

The `Copy the pinned digest to the dogfood image` step (`id: dogfood`) of the
same `sync-pins` job, after the pin sync, is the single home of the copy
(no other workflow or composite carries `imagetools create`).
`verify-reference-image-pin-sync.py` runs it verbatim against a stubbed
`docker`. It runs when `!cancelled()` and
`steps.sync.outputs.pinned == 'true'`, and is never gated on the sync step's
outcome: a test-repository write that fails after this repository's pin was
written leaves this repository pinned to the digest, so the copy still runs.
The job's concurrency group serialises it with every other run's sync and
copy.

## Inputs (environment)
| Name | Source | Notes |
|---|---|---|
| `TARGET` | `vars.WING_COMMANDER_PRIVATE_IMAGE_DOGFOOD_IMAGE` | the only source of the target; may be empty |
| `IMAGE` | workflow `E2E_IMAGE` | the copy's source image |
| `DIGEST` | `build-and-publish` output | must match `^sha256:[0-9a-f]{64}$` |
| `OWNER` | `github.repository_owner` | the namespace the target must be in |
| `THIS_REPO` | `github.repository` | named in the permission message |
| `REGISTRY_TOKEN`, `REGISTRY_USER` | `secrets.GITHUB_TOKEN` (job `packages: write`), `github.actor` | bound to this step only; the token is passed on stdin, never echoed |
| `BODY_FILE` | path | the failure issue body, written only on failure |

## Behaviour (order is part of the contract)
1. `TARGET` empty → `::notice::`, summary "Skipped", output `dogfood=skipped`, exit 0; no `docker` call.
2. `TARGET` (lower-cased) not under `ghcr.io/<OWNER lower-cased>/` → fail "outside ghcr.io/<owner>/"; its name without the tag, lower-cased, is `IMAGE` (lower-cased) → fail "is the reference image itself"; `TARGET` as written not `ghcr.io/<path>[:tag]`, with every path component lower case in Docker's grammar (`[a-z0-9]+(([._]|__|-+)[a-z0-9]+)*`, so no `..` and no leading or trailing separator) and the tag case-sensitive `[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}` (a digest reference, an upper-case or malformed name) → fail "not a lower-case ghcr.io image name"; `DIGEST` malformed → fail. No `docker` call before these pass.
3. `docker login ghcr.io` with the token on stdin; refused → fail. Once logged in, the step's exit runs `docker logout ghcr.io`.
4. Read `TARGET` (`imagetools inspect --format '{{json .Manifest}}'`), classifying its stderr with the `TARGET` and source names taken out. Already `DIGEST` → `dogfood=current`, exit 0, no push. Not found (`not found`, `manifest unknown`, `name unknown`, 404) → fail "does not resolve yet": the step never creates the package, since a package a first `GITHUB_TOKEN` push creates can come out public; the message tells the owner to create it private first, then grant access. A denial (`denied`, `forbidden`, `unauthorized`, 401/403) → fail "refused to read", naming the grant below. An answer that says both → fail naming both fixes, create-private first. Any other error, or no digest → fail "could not read". None of these pushes.
5. `docker buildx imagetools create --tag TARGET IMAGE@DIGEST` (a server-side manifest copy: no build, no pull). Refused → fail; a denial (`denied`, `forbidden`, `unauthorized`, 401/403) names the fix: grant this repository write access on the package (package settings → Manage Actions access); any other error names it as the likely cause.
6. Read `TARGET` back: it must resolve to `DIGEST`, else fail. Then `dogfood=copied`, exit 0.

"fail" means: `::error::` with the reason, summary "Failed: <reason>", output `dogfood=failed`, the reason written to `BODY_FILE`, exit 1.

## Failure reporting
On the step's failure, one `dogfood-image-sync:failed` issue is filed or commented (wing-commander-durable-failure-issue, body `BODY_FILE`); after a `copied` or `current` outcome it is closed. The step never creates a package and never changes a package's visibility: it pushes only to a tag that already resolves, which keeps the existing package's.
