# Contract: board-loop `merge` job

This contract is live and is fixed like code.

## Trigger

```yaml
merge:
  needs: [select, readiness]
  if: >-
    !cancelled()
    && github.event_name != 'pull_request'
    && inputs.directed-stage == ''
    && vars.WING_COMMANDER_BOARD_AUTO_MERGE == 'true'
    && vars.WING_COMMANDER_BOARD_LOOP_PAUSED != 'true'
  concurrency:
    group: wing-commander-board-loop
    cancel-in-progress: false
```

The job never exists on the switch-off path. The readiness report and marker stay as they are today.

## Steps, in order

1. Trusted checkout and a pristine snapshot of `.github/scripts`, as the other jobs do.
2. Resolve the candidate: the fix PR from readiness, or else one bump PR picked by `board_merge.pick_bump_candidate` from a snapshot of every auto-update-shaped open PR. A PR handed over at its current head, or with no tracking issue, is skipped; the oldest that may merge wins, else the oldest, so one stuck PR never hides a newer verified one.
3. Re-check the kill switch (`wing-commander-board-stop-check`); the switch variable is the job-start `vars` value (no token can re-read a variable).
4. Fetch the snapshot fresh. The fix class's backstop is the one `readiness` measured, trusted only while the snapshot's head equals the head readiness measured it on (`readiness_head_sha`); a moved head fails `backstop_holds`.
5. `board_merge.py` evaluates and writes a decision JSON.
6. If `may_merge`, run `gh pr merge --squash <pr> --match-head-commit <head_sha>`, capturing stderr. A failure `classify_refusal` calls `transient` (head or base moved, a 5xx, mergeability still being computed) is retried once, only after the snapshot is re-fetched and the decision re-derived from it, pinned to the head that decision names. A second transient failure is outcome `transient`, never `refused`.
7. Announce on the PR and the issue, once per head, outcome and reason: every announcement ends with a `wc-board-merge-outcome` marker (`head_sha`, `class`, `outcome`, `reason`), and an outcome the PR's snapshot already carries from the App is not posted again.
8. Fix class: write the issue marker `merged` or `handed-over`. Bump class: no board item marker; the `refused` outcome marker on the PR releases it until its head moves.

## Forbidden

`--admin`, `--auto`, `gh pr review --approve`, a second merge method, and any push to `main`. Gate `verify-board-merge.py` enforces this.

## Announcement

Fix PR: posted on the PR and the resolved issue. Bump: posted on the PR and the `auto-update:tracking` issue.

- **Merged**: head SHA, class, every condition's result, and the prove disposition (re-drive pending, or why not needed).
- **Refused**: head SHA, `refusal_class`, GitHub's stderr quoted, and the sentence "handed to a maintainer".
- **Transient**: head SHA, the class, GitHub's stderr quoted, and that it is not handed over as refused.
- **Not merged**: the failed condition's name.

Quoted text never carries a marker: `<!--` in it is defanged before the App posts it.

## `board_merge.py` interface

- `evaluate_fix(snapshot, review_converged, backstop_holds, paused, switch_on)` returns a MergeDecision.
- `evaluate_bump(snapshot, records, bot_login, paused, switch_on)` returns a MergeDecision.
- `classify_refusal(stderr)` returns one of `workflow-scope`, `transient`, `conflict`, `protection`, `other`; `RETRYABLE_REFUSAL_CLASSES` names the ones retried (`transient`).
- `pick_bump_candidate(snapshots, bot_login)` returns `{pr, issue}` or None; `handed_over_at_head(snapshot, bot_login)` and `already_announced(snapshot, bot_login, record)` read the App's own outcome markers.
- `CONDITIONS_FIX`, `CONDITIONS_BUMP` and `REFUSAL_CLASSES` are the name tuples the gate cross-checks against the fixtures.

## Auto-update stage change

The act job posts one `wc-bump-verification` marker comment per verification on the upgrade PR, bound to the commit it verified and pushed (never a re-read of the PR's head). The comment is the record and nothing else: `board_merge.bump_records()` counts a marker only when the App comment's whole body is exactly what `board_item_marker.render_bump_verification()` renders for it. Other App comments quote untrusted text (issue bodies, GitHub's stderr), so a marker quoted inside one is never a pass, even when it copies a real record byte for byte.

A failed post is retried; a lasting failure fails the step and says on the issue that the PR awaits a human merge. The PR stays open and its branch stays, so the next run's guard declines the candidate as already open; the stage never closes the PR to re-propose it, which would repeat the same lasting failure on every scheduled run. The stage never merges its own PR (FR-013).
