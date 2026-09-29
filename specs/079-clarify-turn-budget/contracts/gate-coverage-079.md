# Gate Coverage: FR-018's new check

Follows spec 058's `contracts/gate-coverage-058.md` precedent: one table,
every new/amended gate this feature adds, every failure branch it ships
mapped to a checked-in fixture (constitution VIII — no manual-only
demonstration).

## New gate: `verify-stage-turn-budget-docs.py`

Enforces FR-017 (docs agree with the workflow default they describe) —
the rule FR-018 requires a gate behind, so it cannot drift back silently.

| Branch | Behavior | Fixture |
|---|---|---|
| All nine stages' workflow default and `docs/adoption.md` default agree (post-change: clarify at `65`/`65`) | Exit 0 | `fixtures/stage-turn-budget-docs/all-agree/` — a full nine-stage snapshot with clarify already at 65 |
| One workflow default changed, docs untouched | Exit 1, names the stage, both values | `fixtures/stage-turn-budget-docs/workflow-drifted/` — clarify workflow at `70`, docs still say `65` |
| One docs default changed, workflow untouched | Exit 1, names the stage, both values | `fixtures/stage-turn-budget-docs/docs-drifted/` — docs say `70`, workflow still `65` |
| A stage's docs section omits its `max-turns` cell while the workflow declares one | Exit 1, names the stage explicitly — never silently skipped | `fixtures/stage-turn-budget-docs/docs-missing-cell/` |
| Zero stage files discovered (wrong working directory, path typo) | Exit 1 — a subject the gate cannot reach is a failure, not a vacuous pass (constitution VIII) | `fixtures/stage-turn-budget-docs/no-subjects/` — run against an empty scratch directory |

`--self-test` runs all five fixtures and reports each by name, matching
the convention `verify-versioning-refs.py` and its siblings already use.

## Registration

Added to `lint-workflows.yml`'s gate registry; number assigned at
implementation time (the next unused number after the highest currently
registered gate — 98 as of this plan). `run-local-gates.py` needs no
separate edit: per CLAUDE.md, it derives its invocation list from what
`lint-workflows.yml` actually calls, so registering the gate there is
sufficient for both CI and the local pre-push command to pick it up.

## No amendment to an existing gate

Gates 22/23 (`verify-agent-verdict.py`, `verify-gate-23.py`) already
prove every agent call site — clarify's included — carries the
ceiling/verdict/fail-loud wiring; their fixtures encode the *shape* of
that wiring, not clarify's specific budget literal, so raising `40` to
`65` requires no change to either (research.md R3). This feature adds
exactly one new gate and touches zero existing ones.
