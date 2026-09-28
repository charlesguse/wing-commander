# Phase 0 Research: A Run That Spent Money Says So

No `[NEEDS CLARIFICATION]` markers remain in spec.md. This document
records the technical decisions plan-time research made in order to turn
the spec's FRs into a concrete, gate-checkable design.

## Decision 1: The uniform report is a new composite action, not a bigger `wing-commander-metrics-summary` and not a re-typed `wing-commander-callout` call at each site

**Decision**: Add `.github/actions/wing-commander-cost-report/action.yml`,
a thin composite that takes `token`, `issue-number`, `cost-line`, and
`stage-label` (e.g. `Intake`, `Clarify`, `Plan`, `Tasks`) and posts one
comment via the existing `wing-commander-callout` composite (`kind: info`,
a fixed summary template composed from `stage-label`, body = `cost-line`
verbatim). Each of the four stage workflows calls it exactly once.

**Rationale**: The spec's own complaint (US3) is not that clarify and
plan/tasks failed to reuse `wing-commander-callout` — they already did —
it is that the *step that decides when to fire, with what summary text*
was pasted independently three times (#366, then #377 twice more). Per
CLAUDE.md's "Shared logic has exactly one home," that decision belongs in
a composite action under `.github/actions/`, consumed by the workflows,
not repeated as workflow YAML in four files. Putting it in a *new*
composite, rather than growing `wing-commander-metrics-summary`, keeps
that action's contract single-purpose ("compute and format this run's
metrics") — it is called from other places (e.g. the implement/converge
stages) that have no lifecycle-issue-posting need, and giving it an
`issue-number` input and a `gh issue comment` side effect would widen its
contract for callers that don't want it. `wing-commander-callout` itself
also stays single-purpose (a generic outcome-announcement primitive that
already predates this feature); the new composite sits beside it as a
narrow, cost-specific caller.

**Alternatives considered**:
- *Extend `wing-commander-metrics-summary`* — rejected: conflates metrics
  computation with issue-posting, and forces every existing non-issue
  caller to reason about a new side-effecting input it never asked for.
- *No new composite; each workflow calls `wing-commander-callout` directly
  with a locally-authored summary* — rejected: this is the status quo
  shape (three independently-typed call sites) that US3 explicitly asks
  to retire; a fourth independently-typed call site in intake would meet
  FR-001 but fail FR-002/SC-006/SC-007 outright.
- *A reusable `workflow_call` sub-workflow instead of a composite action*
  — rejected: the four call sites are steps inside larger stage jobs, not
  separate jobs; a composite action is the right granularity, and it's
  what the two existing shared behaviors (`wing-commander-metrics-summary`,
  `wing-commander-callout`) already use.

## Decision 2: The report's `if:` is unconditioned by outcome, conditioned only on "agent ran" and "not cancelled"

**Decision**: Each call site's step reads
`if: always() && !cancelled() && steps.agent.outcome != 'skipped'`
(matching the existing gate already used to decide whether
`wing-commander-metrics-summary` itself runs), placed as an unconditional
step that runs after the stage's outcome-decision logic but is never
nested inside any of that logic's own `if:` branches.

**Rationale**: FR-001/FR-003/FR-012 together require the report to fire on
*every* live path exactly once, including the two paths that fail the run
outright (the readiness veto over unresolved clarification markers, and
the contradiction veto) and every one of intake's four silent paths — but
never on a path where the agent never ran (FR-013) or the job was
cancelled (FR-013, edge case "a cancelled run"). Because the step's
condition names none of the outcome branches, it cannot double-fire
alongside them and cannot be accidentally left out of a future branch the
way three independently-authored copies could drift. `always()` (rather
than a plain `if:` on a prior step's success) is what keeps FR-012a's
"not strandable by a failing step above it" true; `!cancelled()` is what
keeps the cancelled-run edge case silent, matching the
`review-step-gating` skill's stated distinction between the two guards —
this change will get that skill's pass before it ships, per CLAUDE.md.

**Alternatives considered**:
- *Gate the report on each outcome branch's negation (i.e., fire it only
  when no callout fired)* — rejected: this reintroduces exactly the
  bug FR-002a is closing, because a maintainer adding a fifth outcome
  branch later must remember to also extend the report's negated
  condition, whereas an unconditioned step needs no such upkeep.
- *Post the report from inside each outcome-callout step itself, then
  add a fifth copy for the silent paths* — rejected: this is the "fourth
  bespoke copy" the requester explicitly declined (spec Overview, "The
  requester chose the uniform answer").

## Decision 3: Outcome callouts lose the cost line everywhere, not just on intake's silent paths

**Decision**: Every existing embedding of the cost line inside an outcome
callout body — intake's "Announce clarification needed" and "Announce
spec PR ready for review," clarify's questionnaire/ready callouts, and
plan/tasks' non-silent "plan committed"/"tasks ready" callouts — drops the
cost line from its `body:`. The callout's `summary:` and its firing
condition are untouched (FR-008).

**Rationale**: FR-002a is written stage-agnostically ("Outcome callouts
MUST stop carrying the cost line," not "intake's callouts"), and FR-003
forbids a path that already announces an outcome from *also* getting a
separate cost statement. Since Decision 2 makes the new report fire on
every path unconditionally, leaving cost embedded in the non-silent
callouts too would double-post on those paths. This must be verified
call-site by call-site during implementation — the Explore-stage research
behind this plan confirmed the pattern on clarify (three mutually
exclusive posting steps) and intake (two callouts) directly; plan.yml and
tasks.yml's normal (non-hand-off) outcome callouts were not individually
line-verified and must be re-confirmed against the current file during
tasks/implement.

**Alternatives considered**: Leaving the happy-path callouts' embedded
cost line alone and only adding the new report to previously-silent paths
— rejected: produces exactly the double-statement defect FR-003 and
SC-005 name, on every path that already worked correctly.

## Decision 4: FR-010 is met by extending `verify-clarification-gating.py`'s existing scenario harness, not a new gate script

**Decision**: `verify-clarification-gating.py` already extracts and
executes intake.yml's real run-blocks against synthetic agent outputs for
each of its `INTAKE_SCENARIOS` (including the four silent-path scenarios
this spec names). Add, per scenario, an assertion that the new cost-report
step's `if:` evaluates true and its resolved body is non-empty whenever
the scenario's synthetic agent outcome is "ran" (i.e. every scenario in
the existing table, since none of them currently model "agent skipped").
Add self-test mutations mirroring the existing Gate 63
(`verify-plan-tasks-cost-line.py`) pattern: report step removed, `if:`
losing `always()`/`!cancelled()`/the skip check, `uses:` pointed at the
wrong action, and the body blanked — each must fail the gate.

**Rationale**: Constitution VIII requires a gate to run the same subject
locally and in CI and to ship a fixture per failure branch; the existing
harness already does the former for intake's outcome logic, so extending
it keeps one execution path proving both properties instead of building a
second harness that re-parses the same workflow file. This is also the
more direct reading of FR-010's "gate that exercises each intake outcome
path" — the existing scenario table *is* that enumeration.

**Alternatives considered**: A brand-new `verify-cost-report-presence.py`
— rejected: would duplicate the run-block-extraction machinery
`verify-clarification-gating.py` already has, doubling the maintenance
surface FR-002/US3 is trying to shrink elsewhere in this same feature.

## Decision 5: FR-010a is met by extending `verify-metrics-summary-record-emission.py`'s single-home scan

**Decision**: Add a sibling check next to
`case_cost_line_formatter_has_exactly_one_home` that scans every workflow
file and every `.github/actions/**` file (excluding the new action itself)
for reappearance of: (a) the retired bespoke step names ("Report cost of a
reply that answered nothing," "Report cost of an auto-mode hand-off"), and
(b) a `gh issue comment` invocation, or a `wing-commander-callout` call,
whose body embeds `steps.cost-line.outputs.line` (or equivalent) from
outside `wing-commander-cost-report/action.yml` itself. Either hit fails
with a message naming the one home, matching the existing check's failure
message shape.

**Rationale**: FR-010a explicitly asks for this to join "the same way the
existing metrics-summary check guards the cost line's formatter today" —
same file, same scan-and-exclude structure, same failure message
convention, so a future reader finds both single-home rules in one place.

**Alternatives considered**: A `grep`-only shell gate — rejected: the
existing Python check already parses YAML and walks the actions tree
correctly (handling both `action.yml`/`action.yaml` and embedded scripts);
duplicating that walk in shell would itself violate "shared logic has
exactly one home."

## Decision 6: `verify-plan-tasks-cost-line.py` (Gate 63) is re-pointed, not deleted

**Decision**: Gate 63's structural and behavioral checks currently assert
properties of the bespoke "Report cost of an auto-mode hand-off" steps in
plan.yml/tasks.yml (the `dispatch-auto`/`mode==auto` gating, the
`wing-commander-callout` call, the non-empty body). Once those steps are
replaced by calls to `wing-commander-cost-report`, update Gate 63's
`check_structure`/`check_behavior`/self-test mutations to assert the same
properties of the new call sites (correct `uses:`, correct `if:`, correct
inputs) rather than removing the gate.

**Rationale**: Constitution VIII: every shipped failure branch must stay
fixture-covered; deleting Gate 63 rather than re-pointing it would silently
drop the plan/tasks-specific double-post regression tests (e.g.
"`dispatched=true` hoisted" from Gate 63's existing self-test list) that
have no equivalent in `verify-clarification-gating.py`'s intake-only
scenario table.

**Alternatives considered**: Fold Gate 63 entirely into
`verify-clarification-gating.py` — rejected as out of scope: that harness
executes intake.yml specifically; generalizing it to also parse
plan.yml/tasks.yml is a larger refactor than this feature's FRs call for,
and Gate 63 already exists as the right-shaped home for plan/tasks'
call-site checks.

## Decision 7: No change to attribution mechanics (FR-007)

**Decision**: The new composite posts through `wing-commander-callout`,
which posts with the same GitHub App identity every existing callout
already uses, inside the same run. The watchdog's
`verify-cost-report-collector.sh` attribution filter already matches
comments by `userLogin` (the pipeline's bot identities) within a run's
time window — no change needed there.

**Rationale**: FR-007 asks for attributability that this mechanism already
has; introducing a second attribution channel (e.g. a machine-readable
marker in the comment body) would be scope the spec's Out of Scope section
rules out ("The supervision layer's own behaviour, fingerprints, or
defect wording").

**Alternatives considered**: Embedding a hidden HTML comment marker
identifying the stage/run — rejected: unnecessary given the existing
identity+window filter already works, and it would be a second format
convention nobody asked for.

## Open item carried into tasks.md

Decision 3 flags that plan.yml's and tasks.yml's *non-hand-off* outcome
callouts were not individually line-verified for an embedded cost line
during this planning pass. The tasks stage must re-confirm (by reading the
current file, not this document) whether those callouts carry the cost
line today, and if so, add a task to strip it, so FR-002a's coverage is
complete rather than assumed.
