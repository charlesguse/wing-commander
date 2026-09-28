# Contract: gate extensions for FR-010 / FR-010a

This feature extends three existing gate scripts rather than introducing a
new one. Each extension's contract — what it must assert, and what
checked-in fixture proves each failure branch — is recorded here so
tasks.md can turn it into discrete work and so a future reader does not
need to re-derive it from the spec.

## 1. `verify-clarification-gating.py` (intake outcome-path coverage — FR-010)

**New assertion, per existing `INTAKE_SCENARIOS` entry**: when the
scenario's synthetic agent outcome represents "the agent ran" (true of
every entry in the table today), the extended harness must confirm:
- the `wing-commander-cost-report` call site's `if:` evaluates true, and
- its resolved `cost-line` input is non-empty.

**Required self-test failure fixtures** (mirroring Gate 63's existing
mutation list):
1. The report step is removed from intake.yml → gate fails.
2. The step's `if:` loses `always()` → gate fails (would be strandable by
   an upstream failing step, violating FR-012a).
3. The step's `if:` loses `!cancelled()` → gate fails (would post on a
   cancelled run, violating FR-013).
4. The step's `if:` loses the `steps.agent.outcome != 'skipped'` check →
   gate fails (would post when no agent ran, violating FR-013).
5. The step's `cost-line` input is blanked → gate fails (empty body,
   FR-010's "carries an empty body").
6. The step's `uses:` is swapped away from
   `wing-commander-cost-report` → gate fails.

**Also required**: extend the existing scenario table/report (per
data-model.md's Silent Outcome Path table) so each of the four silent-path
scenarios explicitly asserts `expect_cost_report=True` alongside its
existing `expect_silent_green`/no-outcome-callout assertion — this is the
mechanical form of FR-011's "distinguishable" requirement.

## 2. `verify-metrics-summary-record-emission.py` (single-home enforcement — FR-010a)

**New sibling check** next to
`case_cost_line_formatter_has_exactly_one_home`, scanning the same
workflow-file and `.github/actions/**` walk (excluding
`wing-commander-cost-report/action.yml` itself) for:
- the retired step names ("Report cost of a reply that answered nothing,"
  "Report cost of an auto-mode hand-off"), and
- any `gh issue comment` or `wing-commander-callout` invocation whose body
  references `steps.cost-line.outputs.line` (or the workflow's local
  `cost-line` step output) from outside the new composite.

**Required self-test fixture**: a synthetic workflow snippet containing a
pasted copy of the retired report shape → gate fails, naming the one home,
matching the existing formatter check's failure-message convention.

## 3. `verify-plan-tasks-cost-line.py` / Gate 63 (re-pointed, not deleted)

**Change**: `check_structure` and `check_behavior` move from asserting
properties of the bespoke "Report cost of an auto-mode hand-off" steps to
asserting the same properties (fires exactly once, correctly gated,
non-empty body, no double-post when hoisted) of the
`wing-commander-cost-report` call sites in `plan.yml`/`tasks.yml`.

**Required**: every self-test mutation already in this gate's list today
(report step dropped, id dropped, either `if:` conjunct stripped, cost
line dropped from body, `uses:` swapped, `dispatched=true` hoisted,
standalone `$COST_LINE` blanked) continues to exist against the new call
sites — none may be dropped in the re-point, per Constitution VIII's
"every shipped failure branch MUST be exercised by a checked-in fixture."

## Registry and wiring (unaffected)

All three scripts are already discovered by `wc_gate_registry.py`'s
naming convention and already invoked from `lint-workflows.yml` /
`run-local-gates.py`. No new wiring is needed; `verify-gate-wiring.py`'s
existing bidirectional check continues to hold as long as no gate script
is renamed.
