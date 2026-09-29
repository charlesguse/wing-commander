# Quickstart: validating the commit-message scratch path

This is a run guide, not an implementation checklist — see
[data-model.md](./data-model.md) for the nine sites and
[contracts/](./contracts/) for the composite action and gate's exact
behavior.

## Prerequisites

- The composite action `.github/actions/wing-commander-commit-message-guidance`
  exists and is consumed by all nine sites in data-model.md's table.
- `.github/scripts/verify-commit-message-scratch-path.py` exists and is
  registered in `.github/workflows/lint-workflows.yml`.

## 1. Gate suite passes locally

```
python .github/scripts/run-local-gates.py
```

Confirms SC-005 (the full PR-time gate suite is green) and, as part of that
suite, SC-001/SC-006/SC-008 (every in-scope site is either covered or
exempt, and the new gate itself is reachable and correct).

## 2. The gate actually catches a regression (User Story 3)

Pick one in-scope site (e.g. `plan.yml`'s direct-commit step) and delete its
`${{ steps.commit-guidance-plan-direct.outputs.guidance }}` interpolation
from the `prompt:` block in the working tree. Re-run:

```
python3 .github/scripts/verify-commit-message-scratch-path.py
```

Expected: non-zero exit, an `::error file=.github/workflows/plan.yml::...`
line naming the job and step (SC-006). Restore the file afterward (this is a
manual drill, not a committed change).

```
python3 .github/scripts/verify-commit-message-scratch-path.py --self-test
```

Expected: exit 0 — the gate's own self-test proves every failure branch
without needing the manual drill above (Constitution VIII).

## 3. A plan or tasks run composes a multi-line message (User Story 1, SC-002/SC-004)

Drive a plan run (either `mode`) whose agent judges its commit worth a body
— for example a run that records a "decision made without clarification."
On the resulting branch:

```
git log -1 --format=%B
```

Expected: subject line *and* body both present (SC-004), and the run's own
transcript/log shows no permission-denial tool-call attributed to message
composition and no retry of a denied form (SC-002).

Repeat for a `tasks.yml` run in either mode.

For `board-loop.yml`'s two fix-agent sites and `pr-conversation.yml`'s fold
agent — harder to drive on demand per spec.md's Independent Test note —
instead read the rendered prompt for each (the workflow file with the
composite action's output substituted, or a `gh workflow run` /
`act`-rendered log) and confirm it names a path and `git commit -F`,
matching Acceptance Scenario 3.

## 4. No scratch-file residue (User Story 2, SC-003)

After the runs in step 3:

```
git status --porcelain
git show --stat HEAD
```

Expected: `git status --porcelain` is clean; `git show --stat HEAD` lists
only the stage's own artifacts (`plan.md`, `research.md`, etc. — never a
`*-commit-message-*.txt` file).

## 5. One canonical source, confirmed by reading (SC-007)

```
cat .github/actions/wing-commander-commit-message-guidance/action.yml
```

Confirms the wording exists in exactly one file. Then, for any two in-scope
sites (including one of `implement.yml`'s two, per Acceptance Scenario 6),
compare their rendered prompts: they differ only in the substituted
filename (and, at the retry site, the trailing `extra-note`) — never in the
shared sentence itself.
