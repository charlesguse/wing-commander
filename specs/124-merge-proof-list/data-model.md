# Data Model: The Proof List

All structures are in-memory (JSON in fixtures); the only persisted form is the rendered report section.

## Entry
| Field | Type | Notes |
|---|---|---|
| `sha` | string | first-parent commit on `main` |
| `merged_at` | UTC timestamp | commit time on main (FR-001) |
| `pr` | int \| null | null for a direct push |
| `named_issues` | int[] | issues the PR closes or names as board item (since #1147) |
| `lifecycle_issue` | int \| null | final PR only |
| `changed_paths` | string[] | empty allowed (→ state 1 per `actions_only`) |
| `state` | 1..5 | computed |

## ReachingWorkflow
`path`, `reached_via` (`scan` \| `nightly-e2e`), computed from the entry's own tree (FR-004/005). Per workflow, not per job.

## FinishedRun
`workflow`, `run_id`, `event`, `conclusion`, `head_sha`, `started_at`. Qualifies only when started after `merged_at` and `merged_at`'s commit is an ancestor of `head_sha`. Otherwise it is *set apart* (counted, never listed).

## RecordComment
`where` (pr / issue N), `run_id`, `account`, `account_type` (User/Bot), `marker_step` (`proven` \| `prove` \| none), `posted_at`, `names_pr` (bool, needed on shared issues).

Qualification (FR-006/007/009): posted after merge; names a qualifying run; if bot account → marker_step == `proven`; if marker_step == `prove` → never; if the issue is shared → `names_pr` true.

## State (first that fits)
1. `actions_only(changed_paths)` false → needs no run
2. ≥1 qualifying RecordComment
3. no ReachingWorkflow
4. ReachingWorkflow present, zero FinishedRuns
5. FinishedRuns present, no qualifying comment

Invariants: exactly one state per entry; same inputs → same state; no field encodes a verdict (FR-010).

## Report
`built_at`, `status` (`built` \| `failed` \| `paused`), `last_good_at` \| null, `counts` {1..5}, `aged_out`, `set_apart`, `shortened` (bool), `entries` (states 4 and 5 only, with reaching workflows and, for state 5, per-workflow counts by event×conclusion + earliest/latest run).
