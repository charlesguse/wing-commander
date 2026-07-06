# Contract: `speckit-4-tasks.yml`

This project has no library/API surface; its "interfaces" are the GitHub
Actions trigger contract, the repo-level configuration variable, and the
workflow it dispatches onward. This document is the contract the
implementation (tasks phase, next stage) must satisfy.

## Trigger contract

```yaml
on:
  pull_request:
    types: [closed]
    branches: ["spec/**"]
    paths: ["specs/**"]
```

Job-level gate (`tasks` job):

```
github.event.pull_request.merged == true &&
startsWith(github.event.pull_request.head.ref, 'plan/')
```

Job-level gate (`stalled` job):

```
github.event.pull_request.merged == false &&
startsWith(github.event.pull_request.head.ref, 'tasks/')
```

**Refusal contract (FR-012)**: if the resolved slug fails
`^[0-9]{3}-[a-z0-9][a-z0-9-]*$`, or `specs/$slug/{spec.md,spec-meta.json,plan.md}`
are not all present on `spec/$slug`, the job fails loudly
(`::error::`, `$GITHUB_STEP_SUMMARY`, and a PR comment if a PR number is
available) and performs no further action.

## Configuration contract: `vars.SPECKIT_TASKS_REVIEW`

| Value | Behavior |
|---|---|
| unset or `auto` | Direct-commit mode (FR-004, FR-005) |
| `pr` | Review-required mode (FR-006, FR-007) |
| any other value | Treated as `auto` (fail open to the automation-first default rather than erroring on a typo — no functional requirement demands otherwise) |

## Outbound dispatch contract

On success (tasks committed in `auto` mode, or tasks PR merged in `pr`
mode), exactly one of:

```bash
gh workflow run speckit-5-implement.yml \
  -f spec_dir="specs/$SLUG" \
  -f issue="$ISSUE" \
  -f iteration=1
```

This matches `speckit-5-implement.yml`'s existing `workflow_dispatch` input
contract (`spec_dir`, `issue`, `iteration`) documented in
`docs/architecture.md` §Stage 4 — this feature does not change that
workflow, only calls it.

## Lifecycle record contract: `specs/NNN-slug/spec-meta.json`

Precondition: `stage == "plan"` (else no-op, see data-model.md).
Postcondition on success: `stage == "tasks"`. Postcondition on the stalled
path: `stage == "stalled"`. All other fields unchanged.

## Lifecycle issue contract

- Success: label transitions to `stage:tasks` (removing `stage:plan`);
  comment includes task count, per-story breakdown, MVP scope, and — in
  `pr` mode — the review PR link; in `auto` mode, confirmation that
  implementation has started.
- Stalled: label transitions to `stage:stalled` (removing `stage:tasks`);
  comment explains the tasks PR was closed unmerged and states the manual
  restart procedure (delete `tasks/NNN-slug`, restart the tasks stage).

## Non-goals (explicitly out of contract, per spec.md Assumptions)

- The internal structure/format of `tasks.md` — owned by
  `.specify/templates/tasks-template.md` and the `/speckit-tasks` skill,
  unchanged by this feature.
- The implementation stage's internal behavior once dispatched.
- Merging or approving the task-list review PR — a human always does this
  (FR-010).
