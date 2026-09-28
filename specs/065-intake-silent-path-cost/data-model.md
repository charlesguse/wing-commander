# Phase 1 Data Model: A Run That Spent Money Says So

This feature has no application data model — it is workflow/gate
plumbing. "Entities" here are the artifacts and records the design in
plan.md and research.md operate on, restated concretely so tasks.md can
turn each into checkable work.

## Cost Line

**What it is**: The single per-run spend statement, e.g. `**Cost**:
$1.74 · 6 turns · claude-opus-5`, or the degraded form `**Cost**: metrics
unavailable`.

**Source of truth**: `wing-commander-metrics-summary`'s `cost-line`
output — unchanged by this feature (FR-004). Format rule (unchanged):
2 decimal places at or above $1.00, 4 decimal places below.

**Consumers after this change**: exactly one — `wing-commander-cost-report`
(new). No workflow computes or reformats this value a second time.

## Outcome Callout

**What it is**: A comment posted via `wing-commander-callout` announcing
what the requester should do next (answer questions, review a PR) or,
for clarify/plan/tasks' internal handoffs, that something happened
automatically.

**Fields relevant to this change**: `kind` (`action`|`info`), `summary`,
`body`/`body-file`. `body` (or the file it points at) MUST NOT contain the
cost line after this change (FR-002a).

**Instances in scope**:

| Stage | Callout | File (per Explore-stage research) |
|---|---|---|
| intake | "Announce clarification needed" | `.github/workflows/intake.yml` |
| intake | "Announce spec PR ready for review" | `.github/workflows/intake.yml` |
| clarify | questionnaire / ready callouts | `.github/workflows/clarify.yml` |
| clarify | "Report cost of a reply that answered nothing" (#366) | `.github/workflows/clarify.yml` — **retired**, replaced by the uniform report |
| plan | normal "plan ready" callout | `.github/workflows/plan.yml` |
| plan | "Report cost of an auto-mode hand-off" (#377) | `.github/workflows/plan.yml` — **retired** |
| tasks | normal "tasks ready" callout | `.github/workflows/tasks.yml` |
| tasks | "Report cost of an auto-mode hand-off" (#377) | `.github/workflows/tasks.yml` — **retired** |

Exact line ranges are not restated here since they will shift as soon as
implementation edits the files; tasks.md work items locate them fresh by
searching for the step names above.

## Uniform Cost Report (new)

**What it is**: The one shared per-stage report that delivers the cost
line to the lifecycle issue, defined once and consumed by every
cost-bearing stage.

**Implementation**: `.github/actions/wing-commander-cost-report`
(composite action). See `contracts/cost-report-action.md` for its
input/output contract.

**Firing rule** (identical at every call site):
`if: always() && !cancelled() && steps.agent.outcome != 'skipped'`,
never conditioned on which outcome branch the stage took. Exactly one
call site per stage workflow.

**Invariant it must uphold (FR-003)**: for a given run, the count of
{outcome callouts carrying a cost line} + {uniform cost reports posted}
= 1 if the agent ran and the run was not cancelled, else 0.

## Silent Outcome Path

**What it is**: An intake result that deliberately announces no outcome.
Four are recorded today in `verify-clarification-gating.py`'s
`INTAKE_SCENARIOS`. This feature restates the record (FR-011) so
"announces no outcome" and "posts nothing at all" are two independent
booleans on each scenario, not one:

| Scenario (existing `INTAKE_SCENARIOS` entry) | Announces outcome? | Posts a cost report? |
|---|---|---|
| 1. No feature request, no questions | No | **Yes** (was: No) |
| 2. No feature request, with questions | No | **Yes** (was: No) |
| 3. Spec authored, no questions, no branch resolved | No | **Yes** (was: No) |
| 4. `specified:false`, marker-free branch resolved (contradiction) | No | **Yes** (was: No) |
| (every other, non-silent, scenario) | Yes | **Yes**, via the report, not the callout |

The "Posts a cost report?" column is the new column this feature adds to
the table; "Announces outcome?" is the existing, unchanged decision.

## Lifecycle Issue

Unchanged. Still the requester-facing record of a spec's life and the
place the supervision layer reads.

## Cost-Report Signal

Unchanged consumer: the watchdog's cost-report collector
(`verify-cost-report-collector.sh` is its checked-in fixture). This
feature is what makes the signal stop firing on the four silent paths and
on clarify/plan/tasks' equivalent gaps — no change to the collector
itself is in scope (spec Out of Scope).
