# Contract: persisting job and persist-stage inputs

Layer: the **published contract** (stage inputs, section 2) and the
**consuming instrument** (wrapper job, section 1). Live; fixed like code.

## 1. Wrapper job (consuming instrument)

Present in `wing-commander-5-implement.yml` and `wing-commander-6-finalize.yml`:

- `uses: ./.github/workflows/metrics-persist.yml`
- `needs` includes the stage call job (and `resolve-model` for implement).
- `if` contains `always()`, the `WING_COMMANDER_METRICS_PAUSED != 'true'`
  kill switch, a "something started" clause, and excludes a `skipped` stage
  result. It MUST NOT be `success()`/`!cancelled()` alone. Exception:
  finalize carries no "something started" clause (owner decision
  2026-11-08, T017; research R2's fallback). Its job starts as a
  zero-record no-op in a run cancelled while queued, a measured exception
  to FR-011 recorded in the finalize wrapper's comment.
- `with`: `run-id: ${{ github.run_id }}` (string-formatted), destination branch
  and path from `vars.WING_COMMANDER_METRICS_*` with the same defaults as
  `wing-commander-metrics-persist.yml`, runner, container-image,
  `run-in-cancelled-run: true`, `tolerate-failure: true`.
- `secrets`: exactly `pipeline-repo-token`, `container-registry-username`,
  `container-registry-password`.
- `permissions`: `contents: write`, `issues: write`, `actions: read`,
  `id-token: write`.
- No `concurrency:` key. No inline discovery/append/rollup shell.

## 2. Stage inputs (published, `metrics-persist.yml`)

| Input | Type | Default | Semantics |
|---|---|---|---|
| `run-in-cancelled-run` | boolean | `false` | `true`: `persist` uses `always()` gating so it runs in a cancelled run. `verify-image-prerequisites` keeps its Gate 22-pinned `if: inputs.container-image != ''` (skipped in a cancelled run); `persist` only stops on a `failure` result of that check, so it tolerates the skip. `false`: today's gating bit for bit. |
| `tolerate-failure` | boolean | `false` | `true`: `continue-on-error` on both jobs; a failing `persist` ends with a `::warning::` and step-summary line naming the sweep as backstop, from a separate `warn-sweep-backstop` job that carries no `container:` so it still warns when the caller's image fails to pull or start. `false`: today's fail-loud. |

`persisted-count` and `unpersisted-record-keys` outputs unchanged.

## 3. Invariants checked by Gate 79 (extended)

1. Both wrappers contain the job per section 1.
2. Neither the `workflow_run` job nor the `sweep` job in
   `wing-commander-metrics-persist.yml` passes either new input.
3. Both inputs exist with `default: false`.
4. No App secret / `APP_TOKEN` reaches the job; no `concurrency:`.
5. Each failure branch has a checked-in fixture under
   `.github/scripts/` fixtures for the gate.

## 4. Rollup line

The composite `wing-commander-metrics-persist` renders the FR-006 sentence; no
other file contains its prose.
