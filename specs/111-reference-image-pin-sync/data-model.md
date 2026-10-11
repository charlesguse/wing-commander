# Data Model: Reference-Image Pin Sync

## Reference-image pin
- Actions variable `WING_COMMANDER_CONTAINER_IMAGE` on a repository.
- Valid value: `ghcr.io/charlesguse/wing-commander-e2e-image@sha256:<64 hex>`
  (image name equals the workflow's `E2E_IMAGE`; never a tag).

## Sync set
- `{GITHUB_REPOSITORY}` ∪ `{vars.WING_COMMANDER_AUTO_RELEASE_E2E_REPO}` when
  non-empty. Compared case-insensitively. Size 1 or 2.

## Sync credential
- Secret `WING_COMMANDER_REFERENCE_IMAGE_SYNC_TOKEN`. Valid when its reachable
  repository set equals the sync set and a variable probe succeeds on each.
  Never logged or written to the outcome record.

## Sync outcome (per repository)
| Field | Meaning |
|---|---|
| `repo` | `owner/name` |
| `status` | `written` \| `current` \| `skipped` \| `failed` |
| `reason` | empty for written/current; why for skipped/failed |
| `held` | value found before the run (empty if unset) |
| `expected` | the value that should be held |

State: a repository moves `unknown → probed → (current | written | failed)`;
`skipped` is assigned before probing (no test repository, superseded, a check
failed). Any `failed` makes the job fail.

## Sync-failure issue
- Label `reference-image-sync:failed`; at most one open. Body lists each
  `failed` outcome with `repo`, `held`, `expected`, `reason` and the run URL.
  Closed by the next fully successful sync.
