# Contract: board-loop `merge` job

This contract is live and is fixed like code.

## Trigger

```yaml
merge:
  needs: [select, readiness]
  if: >-
    !cancelled()
    && vars.WING_COMMANDER_BOARD_AUTO_MERGE == 'true'
    && vars.WING_COMMANDER_BOARD_LOOP_PAUSED != 'true'
  concurrency:
    group: wing-commander-board-loop
    cancel-in-progress: false
```

The job never exists on the switch-off path. The readiness report and marker stay as they are today.

## Steps, in order

1. Trusted checkout and a pristine snapshot of `.github/scripts`, as the other jobs do.
2. Resolve the candidate (fix PR from readiness, or one D4-attributed bump PR).
3. Fetch the snapshot fresh, then recompute the backstop (fix class).
4. Re-check the kill switch (`wing-commander-board-stop-check`) and re-read the switch variable.
5. `board_merge.py` evaluates and writes a decision JSON.
6. If `may_merge`, run `gh pr merge --squash <pr> --match-head-commit <head_sha>`, capturing stderr.
7. Announce on the PR and the issue.
8. Write the issue marker: `merged` or `handed-over`.

## Forbidden

`--admin`, `--auto`, `gh pr review --approve`, a second merge method, and any push to `main`. Gate `verify-board-merge.py` enforces this.

## Announcement

Fix PR: posted on the PR and the resolved issue. Bump: posted on the PR and the `auto-update:tracking` issue.

- **Merged**: head SHA, class, every condition's result, and the prove disposition (re-drive pending, or why not needed).
- **Refused**: head SHA, `refusal_class`, GitHub's stderr quoted, and the sentence "handed to a maintainer".
- **Not merged**: the failed condition's name.

## `board_merge.py` interface

- `evaluate_fix(snapshot, review_converged, backstop_holds, paused, switch_on)` returns a MergeDecision.
- `evaluate_bump(snapshot, records, bot_login, paused, switch_on)` returns a MergeDecision.
- `classify_refusal(stderr)` returns one of `workflow-scope`, `conflict`, `protection`, `other`.
- `CONDITIONS_FIX`, `CONDITIONS_BUMP` and `REFUSAL_CLASSES` are the name tuples the gate cross-checks against the fixtures.

## Auto-update stage change

The act job posts one `wc-bump-verification` marker comment per verification on the upgrade PR. The stage never merges its own PR (FR-013).
