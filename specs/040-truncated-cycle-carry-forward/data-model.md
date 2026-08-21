# Phase 1 Data Model: A Turn-Exhausted Implement Cycle Is Carried Forward, Not Redone from Cold

This feature introduces no persisted data store beyond one new field on the
existing `spec-meta.json` lifecycle record. Every other shape below exists
only for the duration of one job's execution (step outputs) or one test run
(coverage fixtures). Spec's Key Entities section names these at the
requirements level; this document gives each a concrete shape and cites the
exact step it flows through.

## Agent run record (existing entity, spec Key Entities — read via the verdict composite, never re-parsed)

| Field | Source | Notes |
|---|---|---|
| `verdict` | `steps.cycle-verdict.outputs.verdict` (cycle) / `steps.retry-verdict.outputs.verdict` (retry) — `wing-commander-agent-verdict` composite | `healthy` \| `exhausted` \| `failed` \| `unclassifiable` (research.md D1). `exhausted` is the only value this feature newly acts on; every other value's handling is unchanged. |
| `reason` | Same composite | Free text, unchanged — folded into `steps.outcome.outputs.reason` on the failed path exactly as today. |

## Cycle outcome (existing entity, spec Key Entities — now three-way, encoded as `ok` + `truncated`)

| Field | Type | Meaning |
|---|---|---|
| `ok` | `"true"`/`"false"` | Unchanged meaning: "advance / hand off, do not retry." Now also `"true"` for a truncated cycle with progress (research.md D2). |
| `truncated` | `"true"`/`"false"` (new) | `"true"` only when `verdict=="exhausted"` AND the lifecycle record advanced AND the progress test (below) passed. Drives forced non-convergence (D4), the counter (below), and reporting wording (D6). |
| `converged` | `"true"`/`"false"`/empty | Unchanged derivation for `truncated=="false"`. Forced `"false"`, scan skipped entirely, when `truncated=="true"` (D4) — never inferred from converge-commit absence for a cut-off run. |
| `reason` | string | Unchanged — the human-readable explanation, already existing on the failed path. |
| `remaining` | string | Unchanged shape (diff of the converge commit's tasks.md additions) when not truncated. Overridden to a fixed "the last cycle ran out of turns before it could assess what remained" string when truncated at the iteration cap (FR-014, D6). |

The three classifications are the three reachable `(ok, truncated)` pairs:
`(true, false)` = completed, `(true, true)` = truncated,
`(false, false)` = failed. `(false, true)` is unreachable by construction —
`truncated` is only ever set `"true"` inside the `ok=="true"` branch
(research.md D2).

## Progress evidence (existing entity, spec Key Entities — now a concrete two-arm test)

| Arm | Test | Scope |
|---|---|---|
| A — task list | Count of `- [x]`/`- [X]` lines in `tasks.md` at `origin/<branch>` tip > the same count at `BASE_SHA` (`steps.base.outputs.base-sha` for the primary cycle; a new retry-specific base for the retry — research.md D7) | `$SPEC_DIR/tasks.md` only |
| B — outside-spec-dir work | `git diff --name-only BASE_SHA..tip -- . ":(exclude)$SPEC_DIR/**"` non-empty | Everything except `$SPEC_DIR` |

Progress = Arm A **OR** Arm B (FR-004). The lifecycle-record advance
(`spec-meta.json`, inside `$SPEC_DIR`, not `tasks.md`) satisfies neither
arm by construction (research.md D3, FR-004a). Only evaluated when
`verdict=="exhausted"` AND the lifecycle record advanced — a cycle that
completed normally or failed outright never runs this test.

## Consecutive-truncation count (new — `spec-meta.json` field `truncated_count`)

| Field | Type | Written by | Meaning |
|---|---|---|---|
| `truncated_count` | integer, absent/0 default | New "Record truncated-cycle count" step (research.md D5), deterministic jq-patch-commit-push, unconditional on `truncated` vs. not | Incremented by 1 when the just-consolidated cycle is `truncated`; reset to 0 on any `completed` or `failed` cycle (FR-011). Committed only when the value changes (no-op commit avoided). |

Full `spec-meta.json` shape after this feature (delta from today's four
fields — `implement.yml`'s own advance of `stage`/`iteration` is
unchanged):

```json
{
  "issue": 179,
  "spec_dir": "specs/040-truncated-cycle-carry-forward",
  "feature_num": "040",
  "stage": "implement",
  "iteration": 3,
  "spec_branch": "spec/040-truncated-cycle-carry-forward",
  "truncated_count": 2
}
```

`truncated_count` is read (default 0 when absent, e.g. every spec created
before this feature ships) at the start of "Record truncated-cycle count"
and is the only new persisted state this feature adds. It is never read by
the idempotency guard or the iteration cap — both are unchanged (FR-022;
this feature does not affect how many iterations run, only what happens on
a turn-exhausted one).

## Lifecycle issue report (existing entity — new wording branches only)

| Situation | `converged` | `truncated` | At cap? | Report body (D6) |
|---|---|---|---|---|
| Normal converged | `true` | `false` | n/a | Unchanged: "✅ Implementation converged" |
| Normal unconverged, below cap | `false` | `false` | no | Unchanged: "🔁 Cycle N completed without converging" + remaining list |
| Truncated with progress, below cap | `false` | `true` | no | New: "⏱️ Cycle N ran out of its turn budget. ... cycle N+1 continues on `$TIER` (consecutive truncations: K)." Never "failed." |
| Truncated with progress, at cap | `false` | `true` | yes | New: "⚠️ Iteration cap reached — the last cycle ran out of turns before it could assess what remained." No empty remaining-work block (FR-014). |
| At cap, not truncated | `false` | `false` | yes | Unchanged: "⚠️ Iteration cap reached" + remaining list |
| No progress (escalates) | n/a (failed path) | `false` | n/a | Unchanged failed/retry/stalled reporting |

## `implement.yml` step outputs (delta — new outputs only; existing outputs unchanged in name and meaning)

| Step | New output | Type |
|---|---|---|
| `outcome` ("Read back cycle outcome") | `truncated` | `"true"`/`"false"` |
| `retry-outcome` ("Read back retry outcome") | `truncated` | `"true"`/`"false"` |
| `final` ("Consolidate final outcome") | `truncated` | `"true"`/`"false"` — picked from retry's or primary's, same selection rule as `ok`/`converged`/`remaining`/`tier` today |
| new step "Record retry base SHA" | `base-sha` | git SHA — retry's own start point (research.md D7) |
| new step "Record truncated-cycle count" | `count` | integer as string — the just-written `truncated_count` |

No `workflow_call` input or output of `implement.yml` itself changes
(FR-021) — every new output above is a step-level output internal to the
`implement` job, consumed only by later steps in the same job.

## Coverage fixtures (new, ephemeral — Gate 26 only, never touches the shipped composite or a real API)

| Field | Type | Meaning |
|---|---|---|
| scenario | one of the six named in research.md D8 | Selects the synthetic git history (which commits land between `BASE_SHA` and tip) and the `VERDICT`/`CYCLE_RESULT` env pair `run_step` supplies in place of the upstream verdict step |
| synthetic repo | real git repo + local bare remote, per-scenario, torn down with the rest of the test's temp directory | Proves the commit/push side effects (the counter write, D5) execute for real, matching Gate 14's existing shape |
| mutation | one of the five in research.md D8 | Applied to a copy of the shipped step text; the same scenario suite is re-run against the mutated text and must fail at least one scenario it passed unmutated |
