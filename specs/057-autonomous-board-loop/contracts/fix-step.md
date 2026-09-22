# Contract: Fix Step

## Sequence

1. `git fetch origin main` (fresh, this run — research.md D7); record
   `base-sha` as a step output the same way `implement.yml`'s `steps.base`
   already does.
2. `git checkout -b fix/<issue_number>-<slug> <base-sha>` (FR-023's naming
   rule — a human reading the branch list can tell what it's for).
3. Fixer agent step: model tier per research.md D18, tool allowlist per
   research.md D23 (write/push tools granted, web tools never), issue body
   and non-maintainer comments framed as data only (FR-055/FR-056).
4. Post-agent credential refresh + metrics-summary (research.md D19/D20).
5. `python3 .github/scripts/run-local-gates.py` — the exact CI invocation
   (research.md D8). Non-zero exit: stop here, comment the failing gate
   name on the issue, push nothing, open no PR (FR-024).
6. On green: push the branch, open the PR (body cites the issue per
   FR-026), comment the PR link on the issue via
   `wing-commander-outstanding-task-item` (research.md D9).

## Guard against a second branch/PR (FR-054)

Before step 1, the job checks live GitHub state (contracts/board-item-marker.md)
for an existing branch/PR already associated with this issue. If one
exists, the fix step is skipped and the loop resumes at whatever step the
existing PR's state implies (review or readiness), never cutting a second
branch.

## Failure mid-step

If the run ends between step 2 and step 6 (branch exists, no PR yet), the
next run's guard (above) finds the branch, has no PR to resume review on,
and re-enters the fix step from step 3 on the existing branch rather than
cutting a second one.
