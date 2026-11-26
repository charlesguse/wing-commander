# Contract: the feature-health section of "Board status"

Layer: consuming instrument. This is not part of the `workflow_call` published contract; it is the shape `wc_board_status.py` and the gate `verify-feature-health.py` both check.

## Artifact

- Name: `feature-health-section` (one constant in `wc_board_status.py`; the gate checks it against the upload step).
- Content: one Markdown file, UTF-8, produced by `wc_feature_health.py build` on the default branch.
- Producer permissions: `contents`, `actions`, `issues`, `pull-requests` read. No write, no agent, no dispatch.

## Section layout

```text
<!-- wing-commander-feature-health -->
**Feature health** — built YYYY-MM-DD HH:MMZ · N features · U unreadable

**Needs a look:**
- `<feature>` — failing: last success D1, last failure D2
- `<feature>` — quiet: no <signal> since D (threshold T days)
- `<feature>` — quiet: no <signal> in the last T days
- `<feature>` — not running: no run since D
- `<feature>` — not running: no run in the window
- `<feature>` — paused: <WING_COMMANDER_..._PAUSED>
- `<feature>` — unreadable: <reason>
(or "Nothing needs a look.")
(a failing, not running or paused call-out whose signal read failed ends with " (signal unreadable: <reason>)")

<details><summary>All features</summary>

| Feature | State | Last success | Last failure | Last output signal |
|---|---|---|---|---|
| lifecycle | healthy | … | … | … (threshold 14d) |
| &nbsp;&nbsp;implement | … | … | … | not measured |
</details>
<!-- /wing-commander-feature-health -->
```

Rules:
- Dates are `YYYY-MM-DD`; a missing date is `never in window`, except that a *quiet* call-out says "in the last T days" and a *not running* call-out says "in the window" instead (a *failing* call-out keeps `never in window`); a feature with no declared signal says `not measured`, and so does a feature whose signal read failed.
- Call-outs list only *failing*, *quiet*, *not running*, *paused*, *unreadable*; sorted by state order then name. A *failing*, *not running* or *paused* call-out whose signal read failed ends with ` (signal unreadable: <reason>)`; *not configured* is never called out, even then.
- Stage rows sit directly beneath the lifecycle row.
- Every registry feature appears exactly once in the table (SC-002).
- Deterministic: the same input JSON and `now` give byte-identical output (SC-003).

## Writer statuses

| Status | Section shows |
|---|---|
| `built` | the artifact content |
| `paused` | "paused (`WING_COMMANDER_FEATURE_HEALTH_PAUSED`)" and the last good build date |
| `failed` | "latest build failed" and the last good build date |
| `never` | "not yet built" |
| `unreadable` | "could not read the latest build" and the last good build date |
| stale (older than 48h) | the content with a "stale" notice and its build date |

Over-size: the table is dropped, call-outs kept, with a "table shortened" line.

## Registry file contract

`.github/scripts/feature-health-registry.json`: an array of entries as in data-model.md. The gate fails when: a table row of reference.md's three tables has no entry (and is not in `EXEMPT_UNREGISTERED`); an entry names a missing workflow; a `kill_switch` is not in the Kill switches table; a name repeats; `quiet_days` is below 1.

## Non-actions

The build never comments, labels, closes or edits an issue or PR, never starts a run, and files nothing (FR-013).
