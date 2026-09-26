# Contract Delta: `clarify.yml`'s declared turn budget

Base contract: `.github/workflows/clarify.yml`'s published `workflow_call`
interface (`contracts/stage-interfaces.md` in the base pipeline spec).
This is an amendment, not a rewrite — mirrors the delta-document pattern
spec 058 used for `watchdog.yml`/`metrics-persist.yml`.

## What changes

`workflow_call.inputs.max-turns.default`: `40` -> `65`.

That is the entire interface change. The input's name, type (`number`),
`required: false`, and description remain as published; only the literal
default moves. No input is added, removed, or renamed (FR-008/SC-004);
the multiplier `wing-commander-turn-ceiling` applies remains its own
default (`2.5`), untouched (FR-003).

## What does not change

- An adopter who already passes their own `max-turns` value to this
  stage (directly, or via their wrapper) keeps that value untouched —
  a `default:` only takes effect when the caller supplies nothing
  (FR-010). This is ordinary `workflow_call` semantics, not new
  behavior this feature adds.
- The runaway ceiling formula (`wing-commander-turn-ceiling`,
  `ceil(intended-turns * multiplier)`) is unchanged; it simply receives
  a larger `intended-turns` for callers that inherit the new default.
- The invalid-budget guard inside `wing-commander-turn-ceiling` (empty,
  zero, negative, non-numeric -> loud failure) is unchanged and untested
  by this delta — it is a function of whatever `intended-turns` value
  arrives, not of clarify specifically (research.md R3).
- `wing-commander-metrics-summary`, `wing-commander-agent-verdict`, and
  the watchdog's `collect-turn-budget` all continue reading whatever
  single `max-turns` value the call site supplies; none of them is
  edited by this feature (FR-015).

## Where the reasoning is recorded (FR-001)

Beside the `default: 65` line, an inline comment in `clarify.yml` states:
the accepted range (`39-61` counted turns), the source (issue #587's
recorded history), and the resulting ceiling (`163`) — so a maintainer
reading the input alone, not just this spec directory, finds the
reasoning. The same three facts are restated in `docs/adoption.md`'s
`### clarify` row and in `docs/architecture.md`'s new procedure
subsection (data-model.md's "Written procedure" table), per FR-017's "no
stale number left behind" — all three locations move together in the
same change.

## Consequence for adopters (Edge Cases, spec.md)

An adopting repository that passes no `max-turns` to clarify inherits the
new default (`65`) and its wider ceiling (`163`) the moment it pins a
release containing this change — the intended consequence of re-basing
rather than adding a knob (Out of Scope: "adding a repository variable...
for per-stage budget tuning"). This is stated in the change's own
description/release notes, not left for an adopter to discover by
diffing defaults.
