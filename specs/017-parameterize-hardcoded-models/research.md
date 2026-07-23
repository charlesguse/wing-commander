# Phase 0 Research: Parameterize Hardcoded Models

No `[NEEDS CLARIFICATION]` markers remain in `spec.md` (both clarification
questions were resolved on issue #87, session 2026-07-22 — see
`checklists/requirements.md`). This document instead records the *design*
decisions needed to turn the spec's per-tier requirements into a concrete set
of override points, since the spec deliberately stops at "map every
hardcoded location to a tier" without naming the tiers' variables.

## D1: Inventory of hardcoded (unparameterized) model literals

Grepped every `.github/workflows/*.yml`, `.github/actions/*/action.yml`, and
`.specify/scripts/bash/*.sh` for `claude-*` / Bedrock-style
(`anthropic.claude*`, `us.anthropic*`) model identifiers.

**Decision**: The only executable literals are in `implement.yml`'s retry
(escalation) and progress-comment steps:

| File:Line | Literal | Role |
|---|---|---|
| `implement.yml:542` | `claude-opus-4-8` | Guard: `if: ... inputs.model != 'claude-opus-4-8'` (skip retry if already at escalation tier) |
| `implement.yml:614` | `claude-opus-4-8` | `--model claude-opus-4-8` on the retry `claude-code-action` step |
| `implement.yml:635` | `claude-opus-4-8` | `model: claude-opus-4-8` passed to `wing-commander-metrics-summary` for the retry step |
| `implement.yml:664` | `claude-opus-4-8` | Step-summary text: `"Retry attempt (claude-opus-4-8) also failed..."` |
| `implement.yml:708` | `claude-opus-4-8` | `tier="claude-opus-4-8"` in outcome consolidation (surfaces in the stalled-report message) |
| `implement.yml:785` | `claude-haiku-4-5` | `--model claude-haiku-4-5` on the progress-comment `claude-code-action` step |
| `implement.yml:799` | `claude-haiku-4-5` | `model: claude-haiku-4-5` passed to `wing-commander-metrics-summary` for the progress-comment step |

Every other `claude-*` occurrence is already a `${{ inputs.* }}` reference
with a `default:` reproducing today's behavior (`intake.yml`, `clarify.yml`,
`plan.yml`, `tasks.yml`, `rebase.yml`, `finalize.yml`, `cleanup.yml`,
`watchdog.yml` all declare a `model`/`summary-model`/`diagnose-model`/
`propose-fix-model` input), or is a prose comment / artifact filename token
(both explicitly out of scope per spec.md's Assumptions).

**Rationale**: FR-001 and FR-004 target exactly these — the escalation path
and its "cosmetic" siblings (step-summary text, outcome-consolidation tier
label) are included because leaving them as literals would desync the
displayed model name from the actual (now-overridable) escalation model the
run used, which is itself a discoverability regression (FR-007).

**Alternatives considered**: Leaving lines 664/708 (report text only, no
`--model`/`model:` flag) untouched as "cosmetic, not an invocation." Rejected
— SC-001 requires *zero* embedded identifiers in executable logic, and an
operator who overrides the escalation model would otherwise see a stalled
report that lies about which model actually ran.

## D2: New `workflow_call` inputs on `implement.yml`

**Decision**: Add two inputs to `implement.yml`, both `type: string`,
`required: false`:

- `escalation-model`, `default: claude-opus-4-8` — replaces all five
  `claude-opus-4-8` literals (D1 rows 1-5).
- `summary-model`, `default: claude-haiku-4-5` — replaces both
  `claude-haiku-4-5` literals (D1 rows 6-7).

The retry guard becomes `inputs.model != inputs.escalation-model` (was
`!= 'claude-opus-4-8'`) — this generalizes correctly: if an operator sets
`escalation-model` equal to their primary `model`, the retry step is skipped
exactly as it is today when the primary model already equals the (previously
hardcoded) opus escalation target, preserving the existing "don't retry with
the same model" behavior (spec edge case "Cost-tiering integrity").

**Rationale**: Mirrors the existing `model`/`summary-model` input pattern
already used by `finalize.yml`/`cleanup.yml` for their own read-only summary
steps — no new pattern introduced, just applied to the two locations that
were missing it.

**Alternatives considered**: A single shared `escalation-model` input used
for *both* the retry step and the progress-comment step. Rejected — the
progress-comment step is not an escalation; it is a triage/summary-weight
step (same class as `finalize.yml`/`cleanup.yml`'s `summary-model`,
`watchdog.yml`'s `diagnose-model`) that happens to live inside
`implement.yml`. Collapsing them would violate FR-008 (distinct tiers must
stay distinct) by forcing a single override to serve two different-weight
purposes.

## D3: Task-tier → repository-variable mapping

**Decision**: Five repository variables cover the spec's four illustrative
tiers (`triage`, `plan/tasks`, `spec/clarify`, `implement/escalation`); the
`implement` tier itself keeps its existing variable unchanged and gains a
sibling for escalation:

| Tier | Variable | Default | Wired into |
|---|---|---|---|
| spec/clarify | `WING_COMMANDER_SPEC_MODEL` *(new)* | `claude-opus-4-8` | `intake.yml` `model`, `clarify.yml` `model` |
| plan/tasks | `WING_COMMANDER_PLAN_MODEL` *(new)* | `claude-sonnet-5` | `plan.yml` `model`, `tasks.yml` `model`, `rebase.yml` `model` |
| triage/summary | `WING_COMMANDER_SUMMARY_MODEL` *(new)* | `claude-haiku-4-5` | `cleanup.yml` `summary-model`, `finalize.yml` `summary-model`, `watchdog.yml` `diagnose-model`, `implement.yml` `summary-model` (D2) |
| implement | `WING_COMMANDER_IMPLEMENT_MODEL` *(existing, unchanged)* | `claude-sonnet-5` (or `claude-opus-4-8` via `model:opus` label) | `implement.yml` `model`, `watchdog.yml` `propose-fix-model` *(newly wired — see below)* |
| implement/escalation | `WING_COMMANDER_IMPLEMENT_ESCALATION_MODEL` *(new)* | `claude-opus-4-8` | `implement.yml` `escalation-model` (D2) |

**Rationale — why `watchdog.yml`'s `propose-fix-model` joins
`WING_COMMANDER_IMPLEMENT_MODEL` rather than getting its own variable or
joining `WING_COMMANDER_PLAN_MODEL`**: its own input description already
self-identifies as "constitution II tiering: implementation-weight" and its
default (`claude-sonnet-5`) matches the implement tier's non-escalated
default exactly. FR-001's "locations sharing a tier resolve to the same
override" directs same-tier, same-default locations to share a variable
rather than accreting a sixth one. `diagnose-model` (default
`claude-haiku-4-5`, explicitly "triage/classification") maps the same way to
`WING_COMMANDER_SUMMARY_MODEL` for the identical reason.

**Alternatives considered**:
1. One variable per hardcoded location (7 new variables). Rejected — directly
   contradicts FR-001's explicit tiering intent and SC-004/FR-006's
   independence requirement is about tiers, not raw locations; over-splitting
   adds configuration surface without adding control (a Bedrock consumer
   would have to set 9+ variables to guarantee full coverage instead of 5).
2. Collapsing everything to a single `WING_COMMANDER_MODEL` variable.
   Rejected — explicitly the failure mode FR-008 and the "Cost-tiering
   integrity" edge case forbid: it would collapse haiku/opus/sonnet cost
   tiering into one knob.
3. Naming the new implement-escalation variable
   `WING_COMMANDER_IMPLEMENT_MODEL_ESCALATION` (concern-first) instead of
   `WING_COMMANDER_IMPLEMENT_ESCALATION_MODEL` (tier-first). Kept the
   tier-first form to match the existing `WING_COMMANDER_WATCHDOG_SELF_DISPATCH_CAP`
   /`WING_COMMANDER_WATCHDOG_PAUSED` convention of `WING_COMMANDER_<AREA>_<THING>`,
   where `<AREA>` here is `IMPLEMENT_ESCALATION`.

## D4: `watchdog.yml` keeps its direct-`vars.*`-read exception

**Decision**: `watchdog.yml` reads `vars.WING_COMMANDER_SUMMARY_MODEL` and
`vars.WING_COMMANDER_IMPLEMENT_MODEL` directly inside itself (each with a
`|| 'default'` fallback), the same way it already reads
`vars.WING_COMMANDER_WATCHDOG_PAUSED` (line 1317) and
`vars.WING_COMMANDER_WATCHDOG_SELF_DISPATCH_CAP` (line 1271) today, rather
than adding a `resolve-model`-style job to its wrapper
(`wing-commander-8-watchdog.yml`) and threading the value through `with:`.

**Rationale**: `watchdog.yml` is already the one reusable stage excluded from
`release.yml`'s "no `vars.*`" grep gate (the gate's file list is the other 8
stages by name); it is not on the list a maintainer would need to update, and
using the same mechanism watchdog already uses for its two existing
variables is more consistent than introducing a second pattern (wrapper-side
resolve job) for the same file. The `vars` context in a reusable workflow
resolves against the repository actually running the job (the caller), so
this works identically for local (`uses: ./...`) and pinned
(`uses: owner/repo/...@ref`) callers — the same property that already makes
`WATCHDOG_PAUSED` work for adopters without them touching the wrapper.

**Alternatives considered**: Route through `wing-commander-8-watchdog.yml`
via a `resolve-model`-style job, matching `implement`'s pattern exactly.
Rejected as unnecessary complexity — `implement`'s `resolve-model` job exists
because it layers `model:opus` *label* logic on top of the variable, which
`watchdog.yml`'s two inputs have no equivalent of; a plain `vars.X || default`
expression needs no job.

## D5: CI gate (`release.yml`) impact

**Decision**: No change to `release.yml`'s Gate 1b (`actionlint` +
published-stage invariant checks). Its `vars\.` grep is scoped to
`{intake,clarify,plan,tasks,implement,finalize,cleanup,rebase}.yml`; all new
`vars.*` reads in this feature land either in the `wing-commander-*.yml`
wrapper files (outside that list entirely) or in `watchdog.yml` (already
excluded per D4). The "every agent step declares `--model` and `--max-turns`"
sub-check is also unaffected: `implement.yml`'s retry and progress-comment
agent steps already declare both flags today (via the literals being
replaced) and will continue to after they reference `inputs.escalation-model`
/ `inputs.summary-model` instead — same count of `--model` occurrences,
different right-hand side.

**Rationale**: Confirms the design has no CI-gate side effects to plan for;
verified by reading Gate 1b's exact grep scope and logic in `release.yml`
(lines ~68-115) rather than assuming.

## D6: Documentation surface for discoverability (FR-007, SC-005)

**Decision**: `docs/setup.md`'s existing "3. Repository variables" table
gains four new rows (`WING_COMMANDER_SPEC_MODEL`, `WING_COMMANDER_PLAN_MODEL`,
`WING_COMMANDER_SUMMARY_MODEL`, `WING_COMMANDER_IMPLEMENT_ESCALATION_MODEL`),
in the same `| Variable | Default | Meaning |` format as the existing
`WING_COMMANDER_IMPLEMENT_MODEL` row, placed adjacent to it so all five
model-tier variables read together.

**Rationale**: This table is already the single documented enumeration of
every repo-variable override point (`WING_COMMANDER_PLAN_REVIEW`,
`WING_COMMANDER_TASKS_REVIEW`, `WING_COMMANDER_IMPLEMENT_MODEL`,
`WING_COMMANDER_MAX_ITERATIONS`, the two watchdog variables) — SC-005
requires a reviewer to enumerate every model a run may select "by reading
configuration alone, in under 5 minutes, without inspecting pipeline logic,"
and this table is exactly that surface today for the one tier it already
covers. Extending it (rather than creating a new document) keeps one
canonical location.

**Alternatives considered**: A dedicated new doc listing only model tiers.
Rejected — would fragment the configuration surface SC-005 asks reviewers to
read "alone," splitting it across two documents instead of one.

## Summary of override points (cross-reference to data-model.md)

5 override points, 4 illustrative tiers, 0 changed defaults, 7 literals
eliminated, 4 new repository variables, 1 existing repository variable
extended to a second consumer (`watchdog.yml` `propose-fix-model`). Full
field-level detail in `data-model.md`; full wiring/consumer contract in
`contracts/model-override-points.md`.
