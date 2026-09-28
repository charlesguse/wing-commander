# Data Model: Classify the cancel call's own error instead of racing a pre-read status

**Feature**: `087-stop-cancel-error-classification` | **Issue**: #621

This feature has no persistent storage, database, or long-lived record. Its
"entities" (spec.md's own term) are values that exist for the duration of a
single `board-loop.yml` job step or a single `pr-conversation.yml` Stop
procedure run. They are documented here as the shapes `/speckit-tasks` and
implementation need, not as a schema.

## Cancellation target

The earlier run a stop request names, already qualified by ownership (this
workflow, this repository) and by not being the run performing the check —
unchanged by this feature (Key Entities, spec.md).

| Field | Type | Source | Notes |
|---|---|---|---|
| `stop_run_id` | string (numeric) | `find_stop_request()` (`board_stop_check.py`), unchanged | The run to cancel. |
| `cancel_target_path` | string | `gh api repos/{repo}/actions/runs/{id}` `.path` | Still read and still gates the cancel attempt — FR-002. |
| `cancel_target_repo` | string | same read, `.repository.full_name` | Still read and still gates the cancel attempt — FR-002. |
| ~~`cancel_target_status`~~ | — | — | **Removed by this feature.** No longer extracted, no longer consulted anywhere (FR-002, SC-006). |

## Cancellation outcome

The result of attempting the cancellation — determined *after* the call
from its own error output, never from a value read before the attempt
(Key Entities, spec.md).

| Outcome | Determined by | Board-stop-check reporting (FR-010) | pr-conversation.yml reporting (unchanged site, FR-009) |
|---|---|---|---|
| `cancelled` | `gh run cancel` exits 0 | Nothing emitted (absence of both other lines) | `outcome="cancelled"`, comment names the run |
| `already-terminal` | `gh run cancel` fails; its error text matches the shared vocabulary (see below) | One plain, non-`::...::` informational line naming the run — never a warning | `outcome="already-completed"`, its own distinct comment body |
| `failed` | `gh run cancel` fails; its error text does not match the shared vocabulary — including empty output | One `::warning::` naming the run, carrying the *neutralised* error text (FR-011) | `outcome="cancel-failed"`, its own distinct comment body |

Every row leaves the step's exit status and the `paused` output unchanged
(FR-006); `pr-conversation.yml`'s own step exit status and comment-posting
behaviour are likewise unaffected beyond the outcome label itself.

## Already-terminal vocabulary

The set of error signatures that identify a refusal as "this run can no
longer be cancelled." Owned by one shared script, consumed by both stop
procedures (FR-009); its status-code term is anchored to its protocol
prefix (FR-005).

| Signature | Anchoring | Matches (examples) | Does not match |
|---|---|---|---|
| HTTP 409 | `HTTP 409` (protocol-prefixed), not bare `409` | `HTTP 409: Conflict` | `run 40912 already exists` (bare digits, no prefix) |
| "already completed" phrase | substring, case-insensitive | `Cannot cancel a workflow run that has already completed.` | — |
| "cannot cancel" phrase | substring, case-insensitive | `cannot cancel this workflow run` | — |

**Contract** (implemented by `.github/actions/_shared/cancel-already-terminal.sh`,
see `research.md` D1): given the cancellation call's raw error text as `$1`,
exit 0 if any signature matches, exit 1 otherwise. No stdout contract — this
is a predicate, not a transform.

## Relationships

```
stop request (unchanged)
      │ names
      ▼
cancellation target ──ownership check (unchanged)──▶ pass/fail
      │ pass
      ▼
gh run cancel (attempted unconditionally, FR-001)
      │
      ├─ exit 0 ─────────────────────────────▶ cancelled
      │
      └─ exit ≠0 ─▶ error text ─▶ cancel-already-terminal.sh
                                        │
                          ┌─────────────┴─────────────┐
                          │ exit 0 (match)             │ exit 1 (no match)
                          ▼                            ▼
                    already-terminal                 failed
                 (informational line)          (neutralised ::warning::)
```

No new entity is durable across runs; nothing here is written to an issue,
a file, or a database.
