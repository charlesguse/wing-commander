# Data Model: Feature Health

All structures are plain JSON-compatible dicts; the pure half of `wc_feature_health.py` takes them as arguments.

## Registry entry (`feature-health-registry.json`)

| Field | Type | Rule |
|---|---|---|
| `name` | string | unique across the registry |
| `workflows` | list of Workflow ref | at least one; every `file` exists in `.github/workflows/` |
| `kill_switch` | string or null | a name in reference.md's "Kill switches" table |
| `requires_var` | string or null | a variable whose absence means *not configured* |
| `signal` | Signal or null | null means "not measured" (FR-008) |
| `quiet_days` | integer or absent | default 14 (FR-007); must be ≥ 1 |

**Workflow ref**: `file` (workflow filename), `cadence` (`"schedule"` or `"event"`), optional `stage` (lifecycle stages only, giving the row label; FR-018).

**Signal**: `kind` (one of `merged_pr`, `release`, `issue_or_comment`, `triage_close`, `branch_commit`, `issue_updated`, `issue_section`) plus kind-specific selectors (head-branch prefix, label, marker). A selector that a script already owns is referenced by name, not copied.

## Run

`workflow`, `id`, `event`, `started_at` (UTC), `conclusion` (`success`, `failure`, `cancelled`, `skipped`, other), finished only. *Qualifying* = conclusion in `success`/`failure`/other-non-skipped-non-cancelled. Skipped and cancelled count toward cadence only.

## Reading (collector → classifier input)

Per workflow: `{"runs": [Run...]}` or `{"unreadable": "reason"}`. Per feature: `{"signal_at": ISO | null}` or `{"unreadable": "reason"}`. Globally: `{"switches": {name: bool | "unreadable"}, "vars_set": {name: bool | "unreadable"}, "now": ISO, "window_days": int}`.

## Health state

Ordered, earliest wins: `unreadable` < `paused` < `not configured` < `failing` < `not running` < `quiet` < `idle` < `healthy`. Called out: `unreadable`, `paused`, `failing`, `not running`, `quiet`. Not called out: `not configured`, `idle`, `healthy`.

State rules (per workflow, then per feature):

1. any unreadable read for the workflow, its switch or its required variable, or a scheduled workflow with no cron found → `unreadable` with reason (checked before `paused`); an unreadable signal read makes the feature `unreadable` only when its state would otherwise be `quiet`, `idle` or `healthy`, else the state stays and the reason gains `signal: ...` (call-outs append `(signal unreadable: ...)`);
2. kill switch on → `paused`;
3. `requires_var` unset and every run skipped → `not configured`;
4. last 3 qualifying runs (or fewer) all failed, latest included → `failing`;
5. scheduled and no run started within interval + one interval → `not running`;
6. signal declared and not seen within `quiet_days` → `quiet` (never seen in the window reads as quiet);
7. no qualifying run in the window → `idle`;
8. otherwise `healthy`.

Feature state = worst across its workflows, ignoring `idle` workflows when a sibling has a qualifying run; `idle` only if all are. Lifecycle stage rows carry their own workflow state.

## Report rows

`feature`, `stage` (optional), `state`, `last_success`, `last_failure`, `last_signal` (date, `never in window`, or `not measured`), `threshold_days` (when a signal is declared), `reason` (unreadable states, and any state that kept its rank over a failed signal read; `unreadable_count` counts only `unreadable` rows). Report header: `built_at`, `unreadable_count`, call-out list (called-out states only).

## Publication status (writer side)

`built`, `paused`, `failed`, `never`, `unreadable`, plus `last_good` build date, decided by `wc_board_status.feature_health_snapshot()` from the workflow's finished default-branch runs (same status set as the proof list, FR-014).
