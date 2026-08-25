# Contract: `pr-conversation.yml` — fold-then-dispatch-once and leg-death reporting

Delta against the published stage contract
(`specs/010-reusable-pipeline/contracts/stage-interfaces.md`) and
specs/033's `contracts/reusable-pr-conversation.md`. No declared
`workflow_call` input, output, or secret is removed or renamed (FR-016);
one input is added (below), preserving current default behavior.

## New input

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `confirm-timeout-minutes` | number | false | `1440` | Upper bound, in minutes, a held-for-confirmation leg may wait for its `environment:` approval before GitHub Actions cancels the job (research.md D5). Applies to the `act` job's `timeout-minutes:` — uniform across every leg in the matrix, not held legs alone. |

## Job graph change

Today: `verify-image-prerequisites` → `classify-and-announce` → `act`
(matrix, folds AND dispatches per leg) → `stalled`.

After this feature:

```
verify-image-prerequisites
  └─ classify-and-announce  (+ new output: base-sha)
       ├─ act  (matrix, max-parallel: 1 — UNCHANGED group/gating;
       │        folds only, no longer dispatches; each leg's fold
       │        commit message becomes "fold(<id>): <summary>")
       │    ├─ dispatch-once        (NEW — needs: [classify-and-announce, act], if: always())
       │    └─ report-fold-outcomes (NEW — needs: [classify-and-announce, act], if: always())
       └─ stalled  (UNCHANGED)
```

`dispatch-once` and `report-fold-outcomes` both depend on `act` and run in
parallel with each other once it completes; neither depends on the other.

## Behavioral guarantees (per FR)

- **FR-001/FR-002/FR-003**: `dispatch-once` is the only step in the
  workflow that calls `gh workflow run` for `implement.yml`, and it runs
  exactly once per `pr-conversation` run, after every leg of the matrix
  has finished. A review whose classifications are all abandoned/held/
  question/no-action produces zero dispatches (research.md D3 — branch
  tip unchanged from `base-sha`).
- **FR-004**: `act`'s concurrency group is unchanged
  (`wing-commander-${SPEC_DIR}`); `dispatch-once` joins the same group but
  only after `act`'s `needs:` dependency is satisfied, so no dispatch
  Started by this review's `act` job can ever contend with that same
  `act` job for the group slot (research.md D2).
- **FR-004a/FR-004b**: unchanged mechanism — `act`'s membership in
  `wing-commander-${SPEC_DIR}` still makes a review's fold wait for an
  in-flight implementation cycle for the same spec (this predates this
  feature — specs/033 D6). The wait itself cannot be mistaken for a
  terminated leg because `act`'s own job status while queued is `queued`,
  not `cancelled` — `report-fold-outcomes` only classifies a leg as
  terminated when its job `conclusion` (not status) is non-success.
- **FR-005/FR-005a**: `act`'s existing leg ordering (specs/033's
  `sort_by`) still runs every ready leg before any held one; the new
  `confirm-timeout-minutes` job timeout ensures a held leg cannot wait
  indefinitely, and its expiry is picked up by `report-fold-outcomes` like
  any other leg termination.
- **FR-006/FR-006a**: `report-fold-outcomes` derives every outcome from
  (a) the run's own job `conclusion`s (GitHub-platform-set, not leg-
  published) and (b) git history (durable, not leg-published) — see
  `data-model.md` §4's outcome table. It runs `if: always()`, so neither
  `act`'s own failure/cancellation nor any individual leg's suppresses it.
- **FR-007**: no change to classification categories, the question/
  no-action legs, or announce-before-work ordering — `act`'s existing
  announce step (1258–1298) and its `environment:` binding timing
  (1393–1395) are untouched.

## What this contract does NOT change

- The classification schema (specs/033's `contracts/classification-schema.md`),
  beyond adding the `id` field (data-model.md §1).
- The `confirm-categories`/`confirm-environment` inputs or their semantics.
- The `stop` route's separate concurrency group (1220–1241) — a stop-only
  run still bypasses `wing-commander-${SPEC_DIR}` entirely.
- Any reply-style step's wording for question/needs-info/push-back routes.
