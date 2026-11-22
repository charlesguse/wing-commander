# Quickstart: validating Feature Health

Contracts: [feature-health-report.md](contracts/feature-health-report.md). Entities: [data-model.md](data-model.md).

## 1. Local gates

```bash
python .github/scripts/run-local-gates.py
python .github/scripts/verify-feature-health.py
python .github/scripts/verify-board-status.py
```

Expected: all pass. The fixtures under `.github/scripts/fixtures/feature-health/` cover each state and each failure branch:

| Fixture | Expected |
|---|---|
| `failing` (last 3 runs failed) | *failing* with last success/failure dates |
| `single-failure` | not *failing*; last failure shown |
| `quiet` (green runs, signal older than threshold) | *quiet* |
| `not-running` (scheduled, no run in interval + 1) | *not running* |
| `event-idle` (event-driven, no runs) | *idle*, not called out |
| `paused` (switch on, green runs) | *paused* |
| `not-configured` (var unset, runs skipped) | *not configured* |
| `healthy` | *healthy* |
| `skipped-and-cancelled` | neither break nor extend a failure run |
| `multi-workflow-worst` / `idle-sibling` | worst-of, idle left out when a sibling ran |
| `unreadable-runs`, `unreadable-signal`, `unreadable-switch`, `over-cap` | *unreadable* with reason; the rest classified; count shown |
| `all-unreadable` | build fails |
| `registry-missing` | gate fails (SC-007) |
| `repeat-build` | identical states (SC-003) |

## 2. SC-001 replay

The replay check classifies the checked-in 2026-10-14..2026-11-12 corpus and compares with `expected.json`: private-image dogfood *failing*, spec PR review *paused*, board loop *quiet*, Spec Kit updater, auto-release and watchdog *healthy*. It reports "not yet captured" under `EXEMPT_SC001_PENDING` until the `[maintainer]` capture lands.

## 3. After merge (`[maintainer]`)

1. The owner creates `WING_COMMANDER_FEATURE_HEALTH_PAUSED` only if a pause is wanted (unset means running).
2. Dispatch `wing-commander-feature-health.yml` from the default branch; confirm the artifact `feature-health-section` exists and the run is read-only.
3. Dispatch `board-status.yml`; read the section with `gh issue view <Board status number>` (SC-005).
4. Dispatch the feature-health workflow from another branch; confirm it is refused.
5. Set and clear the switch; confirm the section shows *paused* with the last good build date, then recovers.
6. Confirm no issue, comment or backlog line was created by any of these (FR-013).
