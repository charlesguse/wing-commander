# Contract: `wing-commander-cost-report` composite action

**Kind**: New composite action, joining the published contract (Constitution
VII) — it is called directly by four `workflow_call` stage workflows.

**Location**: `.github/actions/wing-commander-cost-report/action.yml`

## Purpose

The single home for posting a cost-bearing stage's already-computed cost
line to its lifecycle issue, independent of whatever outcome (if any) that
stage announces. Replaces the bespoke reports added for #366 and #377, and
is the mechanism intake's four silent paths gain.

## Inputs

| Name | Required | Description |
|---|---|---|
| `token` | yes | GitHub token with permission to comment on the lifecycle issue (same token every existing callout call site already threads through). |
| `issue-number` | yes | The lifecycle issue number. |
| `cost-line` | yes | The fully formatted cost line to post verbatim — either the real `**Cost**: ...` line or the `**Cost**: metrics unavailable` fallback. This action MUST NOT reformat, round, or otherwise recompute this value (FR-004). |
| `stage-label` | yes | Human-readable stage name for the report's summary text (e.g. `Intake`, `Clarify`, `Plan`, `Tasks`). Used only to compose the summary; never affects gating. |

## Outputs

None required. (If an output proves useful for gate assertions during
implementation — e.g. echoing whether the post succeeded — it may be
added, but no caller depends on one today.)

## Behavior

1. Compose a fixed-shape summary from `stage-label` (exact wording is an
   implementation detail for tasks.md/implementation to fix once; it must
   not describe any stage-specific *outcome*, only that a cost is being
   reported — FR-008 forbids this action from becoming a second place that
   announces what a stage decided).
2. Call `wing-commander-callout` with `kind: info`, the composed summary,
   and `body: <cost-line input, verbatim>`.
3. Do not gate internally on run outcome, agent status, or cancellation —
   that judgment belongs entirely to the caller's `if:` (Decision 2,
   research.md), keeping this action a pure "post what I'm given" primitive
   per Constitution IX.

## Call-site contract (every cost-bearing stage workflow)

Each of `intake.yml`, `clarify.yml`, `plan.yml`, `tasks.yml` calls this
action from exactly one step, with:

```yaml
if: always() && !cancelled() && steps.agent.outcome != 'skipped'
```

and `cost-line: ${{ steps.cost-line.outputs.line }}` (the same
already-computed value each workflow's existing `cost-line` step
produces — no new computation is added at the call site).

## Failure semantics (FR-009)

A failure of this action's own `gh issue comment` call (API error,
permissions) MUST NOT be allowed to change the run's conclusion. The
call-site step's own failure handling (e.g. `continue-on-error` scoped
correctly, subject to a `review-step-gating` pass) must not let a lost
cost comment turn a healthy run red or mask one that should have failed.

## What this contract does NOT cover

- The exact summary wording (implementation detail; FR-008 only
  constrains that it must not describe a stage's *outcome*).
- Any change to `wing-commander-metrics-summary` or
  `wing-commander-callout`'s own existing contracts — both are unchanged.
