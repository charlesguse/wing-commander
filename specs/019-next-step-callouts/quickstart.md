# Quickstart: Validating Clear Next-Step Callouts

Validation scenarios for spec 019, cross-referenced to the acceptance
scenarios in `spec.md` and the contracts in `contracts/callout-format.md`
and `contracts/callout-points.md`. This repo has no unit-test harness for
workflow YAML (`plan.md` Technical Context); validation is a mix of static
contract checks and dogfooded live runs, the same style specs 014/016/017/018
used.

## Prerequisites

- A checkout of this repository (or an adopting repo with its own
  `specify init` output) on a branch containing this feature's changes.
- `gh` CLI authenticated with repo scope, for inspecting issues/PRs and
  triggering workflow runs.
- (Optional, for full end-to-end scenarios) A test issue with the
  `spec-request` label to drive a real pipeline run — expensive in agent
  cost, so most scenarios below are static/contract checks instead, with
  scenario 6 as the one recommended live-run check before merging.

## Scenario 1 — Implementation-phase PR review is announced (User Story 1, FR-002, FR-003, SC-001)

**Steps**: Drive (or dogfood) a spec through `finalize.yml` to the point the
final PR opens, or statically:

```bash
grep -n "wing-commander-callout" .github/workflows/finalize.yml
```

**Expected**: A `wing-commander-callout` invocation appears immediately
after the "Open the final pull request" / "Verify the final pull request was
created" steps, with `kind: action` and a `pr-url` sourced from the verified
PR. On a live run, the lifecycle issue receives a comment rendered as a
colored `[!IMPORTANT]` box stating "Action needed: Review the implementation
PR" with a working link to the PR — this did not exist before this feature
(`research.md` current-state findings).

## Scenario 2 — Spec-phase and implementation-phase callouts share one recognizable format (Acceptance Scenario 2, FR-003)

**Steps**:
```bash
grep -A3 "kind: action" .github/workflows/intake.yml | grep "pr-label"
grep -A3 "kind: action" .github/workflows/finalize.yml | grep "pr-label"
```

**Expected**: Both resolve through the identical `wing-commander-callout`
template (`contracts/callout-format.md`); the only difference is `pr-label`
(`"the spec PR"` vs `"the implementation PR"`) and `summary` text — same
alert box, same `**PR:**`/`**When:**` line shape.

## Scenario 3 — Action-required vs informational are visually distinct with no ambiguous cases (User Story 2, FR-004, FR-005, SC-003)

**Setup**: Pick a spec that has completed its full lifecycle (or a
representative fixture set of comment bodies).

**Steps**: For every pipeline-authored comment on the issue, classify it by
inspection:
```bash
gh issue view <issue-number> --json comments \
  --jq '.comments[] | select(.author.login | test("bot")) | .body' \
  | grep -c '^> \[!IMPORTANT\]'
```

**Expected**: Every comment produced by a row in
`contracts/callout-points.md` either starts with `> [!IMPORTANT]` (action-
required) or contains no `[!IMPORTANT]`/`"Action needed:"` text at all
(informational) — no comment is ambiguous between the two. Comments outside
this feature's scope (watchdog, plan's gate-mode warning) are unaffected and
already don't claim action (FR-005 was already true for them; confirmed by
the current-state audit in `research.md`).

## Scenario 4 — Remaining manual work is framed as a human to-do with timing (User Story 3, FR-006, FR-007, SC-004)

**Setup**: Drive a spec whose `tasks.md` has at least one unchecked item
through to `finalize.yml`.

**Steps**:
```bash
gh issue view <issue-number> --json comments \
  --jq '.comments[] | select(.body | test("Complete the remaining manual work"))'
```

**Expected**: The matching comment is a `[!IMPORTANT]` box, states the tasks
as items the human must do, and includes a `**When:** after this PR merges`
line. Run the same check against a spec with zero unchecked items:

```bash
gh issue view <issue-number-with-no-remaining-work> --json comments \
  --jq '.comments[] | select(.body == "No manual work remains.")'
```

**Expected**: This comment has no `[!IMPORTANT]` wrapper (informational,
FR-009).

## Scenario 5 — No PR at an action moment still reads as action-required (Edge Case "no PR exists", FR-008)

**Steps**: Trigger `intake.yml` on an issue whose spec draft leaves
`[NEEDS CLARIFICATION]` markers in `spec.md`.

**Expected**: The posted comment is a `[!IMPORTANT]` box with `"Action
needed: Answer the open clarification questions"` and no `**PR:**` line
(there is no PR at this point — the clarification happens on the draft
before any further review gate). Confirm by:
```bash
gh issue view <issue-number> --json comments \
  --jq '.comments[] | select(.body | test("Action needed: Answer")) | .body' \
  | grep -c "\*\*PR:\*\*"
```
**Expected output**: `0`.

## Scenario 6 — Full lifecycle dogfooded run (thorough, real run — do this at least once before merging)

**Steps**: Trigger a live pipeline run on a throwaway test issue through
`spec-request`, driving it through intake → (clarify, if applicable) → plan
→ tasks → implement → finalize.

**Expected**: The lifecycle issue shows, in order:
1. An `action`-kind callout when the spec PR opens (or, if clarification was
   needed, a clarification callout first, then the spec-PR-ready callout
   once resolved) — Scenario 1/2's format.
2. Purely informational comments for plan/tasks/implement progress,
   unchanged in shape from today.
3. An `action`-kind callout the moment the final PR opens (Scenario 1) —
   this is the change a maintainer should look for first, since it did not
   exist before this feature.
4. A `finalize` remaining-manual-work callout (Scenario 4) — `action` if
   `tasks.md` has leftover human-only items, `info` otherwise.

A person unfamiliar with the pipeline, shown only this issue, should be able
to state within 15 seconds whether it is currently waiting on them and, if
so, on what and via which PR (SC-002) — this is the acceptance bar to
manually confirm on the dogfooded run.

## Scenario 7 — Maintainer audit: every FR-011 site is migrated, nothing else is (contracts/callout-points.md)

**Steps**:
```bash
grep -Lrn "wing-commander-callout" \
  .github/workflows/{intake,clarify,finalize,implement,rebase,cleanup}.yml
grep -rLn "wing-commander-callout" .github/workflows/{plan,tasks,watchdog}.yml
```

**Expected**: The first command returns no files (all six are migrated,
`contracts/callout-points.md` rows 1–10 present); the second command lists
all three (`plan`, `tasks`, `watchdog` are deliberately unmigrated per
`research.md`'s scope decision).
