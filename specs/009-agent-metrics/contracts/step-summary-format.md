# Contract: `$GITHUB_STEP_SUMMARY` metrics block format

The rendered Markdown fragment the composite action
(`speckit-metrics-summary-action.md`) appends to the step's own run
summary (FR-002). This is the human-facing contract SC-001/SC-002 measure
against: a maintainer must be able to read every field below without
opening the execution artifact.

## Normal case (transcript parsed, result record found)

```markdown
### 🤖 Agent run metrics — <run-label, if set>

| Model | Turns | Duration | Tokens | Cost |
|---|---|---|---|---|
| <model> | <turns_used> / <turn_budget or "—"> | <duration> | <tokens or "unavailable"> | <cost or "unavailable"> |

<!-- only when turn_budget is known and turns_ratio >= warn-fraction -->
⚠️ **Turn budget warning**: this run used <turns_used>/<turn_budget> turns
(<percentage>%) — at or above the <warn-fraction*100>% warning threshold.

<!-- only when a per-model breakdown is present -->
**Per-model breakdown**: <model>: <tokens>/<cost>; ...
```

Rules:

- The table row's **Turns** cell is exactly `used / budgeted` when a
  budget was supplied, or exactly `used` alone (no `/ —`) when it wasn't
  (FR-005 — never render a placeholder budget).
- The warning line is **present if and only if** `turns_ratio >=
  warn-fraction`; there is no "under budget, all clear" line for the
  common case — silence is the not-flagged state (Acceptance Scenario 3).
- Any single field that couldn't be read renders literally as
  `unavailable` in its own cell; this never suppresses the other fields or
  the table itself.
- `<run-label>` in the heading is omitted (heading reads "Agent run
  metrics" alone) when the caller didn't set `run-label` — the common,
  single-invocation-per-job case.

## Unavailable case (no transcript, unparseable, or no result record)

```markdown
### 🤖 Agent run metrics — <run-label, if set>

_Metrics unavailable for this run (execution transcript missing or
unparseable)._
```

Rules:

- This is the **entire** block — no empty table, no partial fields (FR-009
  and spec.md's first Edge Case: a missing/unparseable transcript reports
  unavailable and never fails the stage).
- This block's presence/absence is itself the signal a maintainer needs;
  no `::error::`/`::warning::` annotation is required alongside it, since
  by construction (FR-009) this path never represents a stage failure.

## Multi-invocation ordering (FR-008)

When a job calls the composite action more than once (e.g.
`speckit-5-implement.yml`'s cycle → retry → progress-comment sequence,
research.md D3/D4), each invocation's block appears in the step summary in
the order the steps ran, each carrying its own `run-label` (`cycle`,
`retry`, `progress comment`) so a maintainer can tell at a glance which
invocation each block describes without cross-referencing step names in
the job log.
