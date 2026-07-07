# Contract: `speckit-6-finalize.yml`

This project has no library/API surface; its "interfaces" are the GitHub
Actions trigger contract and the deterministic checks/writes that must run
in order. This document is the contract the implementation (tasks phase,
next stage) must satisfy.

## Trigger contract

```yaml
on:
  workflow_dispatch:
    inputs:
      spec_dir:   { required: true }             # e.g. specs/006-finalize-stage
      issue:      { required: true }              # lifecycle issue number
      converged:  { required: false, default: "true" }
```

Dispatched only by the implement/converge stage (`speckit-5-implement.yml`),
once per specification per hand-off (converged or cap-reached). This stage
dispatches nothing further itself — the hand-off to cleanup is a human
merging the final PR, an event outside this workflow. This is already the
stub's trigger contract and is unchanged by this feature.

## Refusal contract (FR-014)

If `spec_dir` doesn't match `^specs/[0-9]{3}-[a-z0-9][a-z0-9-]*$`, `issue`
doesn't match `^[0-9]+$`, `converged` doesn't match `^(true|false)$`, or
`specs/$slug/{spec.md,plan.md,tasks.md,spec-meta.json}` are not all present
on `spec/$slug`, or `spec-meta.json`'s own `issue`/`spec_dir` fields don't
match the dispatch inputs, the job fails loudly (`::error::`,
`$GITHUB_STEP_SUMMARY`) and performs no further action — no PR, no comment,
no metadata write.

## Idempotency contract (FR-012)

Checked immediately after the refusal contract passes, before the no-diff
check or the agent step:

```
gh pr list --head spec/$slug --base main --state all
```

Any result (open, merged, or closed-unmerged) means this specification is
already finalized or a final PR attempt is already in flight: log a
step-summary note and stop — no new PR, no metadata commit, no issue
comment, no label change.

## No-diff contract (FR-013)

Checked next (requires `git fetch origin main`, since the spec-branch
checkout doesn't otherwise have `main`'s history):

```
git diff --stat origin/main...HEAD    # empty ⇒ nothing to finalize
```

An empty diff is reported as an anomaly on the lifecycle issue and the job
stops — no agent step runs, no `gh pr create` is attempted.

## Change-summary / remaining-work contract (the one agent step)

Runs only once the refusal, idempotency, and no-diff contracts have all
passed:

1. Read-only `claude-haiku-4-5` step (`--allowedTools
   "Read,Glob,Grep,Bash(git log:*),Bash(git diff:*),Bash(git show:*),Write"`,
   `--disallowedTools "WebSearch,WebFetch"`, no `git commit`/`git
   push`/`gh` tool access) writes exactly two files:
   - A change-summary narrative (`${{ runner.temp }}/finalize-summary.md`).
   - The remaining-manual-work list — unchecked and human-only items from
     `tasks.md`, one per line (`${{ runner.temp }}/finalize-remaining.md`),
     empty if none remain.
2. **On outright failure** (the action step fails, or either file is
   missing/unreadable afterward — FR-015): report the failure on the
   lifecycle issue and stop. No `gh pr create` is attempted with
   incomplete content.

## PR contract (FR-004, FR-010)

Assembled deterministically once both temp files exist:

```
[⚠️ **Not fully converged — N tasks remain** — only when converged=false;
 N = non-empty line count of finalize-remaining.md]

<contents of finalize-summary.md>

## How to see it
<compare link: https://github.com/${{ github.repository }}/compare/main...spec/$slug>
<changed-file list: git diff --name-only origin/main...HEAD>

## Remaining manual work
<contents of finalize-remaining.md, or literal "No manual work remains."
 if that file is empty — FR-006>

Lifecycle issue: #$issue
```

```
gh pr create --base main --head spec/$slug --title "Finalize: <feature name> (#$issue)" --body-file <assembled body>
```

**On outright failure** (`gh pr create` itself fails, or a follow-up
`gh pr list --head spec/$slug --base main --state open` cannot confirm a
PR now exists — FR-015): report the failure on the lifecycle issue and
stop. None of the writes below run.

## Post-PR contract (FR-005, FR-007, FR-008)

Runs only once the PR is verified to exist, in this order:

1. Commit `spec-meta.json` (`"stage": "review"`) directly onto
   `spec/$slug` and push (no separate work branch — same direct-commit
   shape the implement stage already uses for its own metadata writes).
2. `gh issue comment $issue` with the same remaining-manual-work content
   used in the PR body (verbatim from `finalize-remaining.md`, or "No
   manual work remains.").
3. `gh label create "stage:review" --force`; `gh issue edit $issue
   --add-label "stage:review" --remove-label "stage:implement"`.

Exactly one PR, one metadata commit, one issue comment, and one label
transition happen per specification that reaches this contract (FR-012,
SC-001).

## Non-goals (explicitly out of contract, per spec.md Assumptions)

- Judging convergence — the `converged` input is consumed as-is.
- Anything the cleanup stage does after a human merges the final PR
  (branch deletion, issue closure) — out of scope, unimplemented
  (`speckit-7-cleanup.yml` remains a stub).
- The internal behavior of `/speckit-implement`/`/speckit-converge` and
  the exact wording task-list authors use to mark an item human-only —
  this stage extracts whatever the task list already records, per
  `spec.md`'s Assumptions.
