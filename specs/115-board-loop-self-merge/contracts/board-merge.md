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
2. Resolve the candidate: the fix PR from readiness, or else one bump PR picked by `board_merge.pick_bump_candidate` from a snapshot of every auto-update-shaped open PR. A PR handed over at its current head, with no tracking issue, or whose tracking issue carries `board:stalled` (from the open `board:stalled` issues the job lists; a failed list looks for no bump candidate that run) is skipped; the oldest that may merge wins, else the oldest, so one stuck PR never hides a newer verified one.
3. Re-check the kill switch (`wing-commander-board-stop-check`); the switch variable is the job-start `vars` value (no token can re-read a variable).
4. Fetch the snapshot fresh with `board_merge.py snapshot` (`fetch_snapshot()`, the one fetch the candidate scan, this step and the merge retry share), and for the fix class the issue's comments. The snapshot is `gh pr view` for the head, checks, author, branch, base and body, plus the PR's files, commits and issue comments, each read whole over REST, beside the pull's own `changed_files`, `commits` and `comments` counts and head. A bump PR's snapshot also carries `verificationRun`: the Actions API's facts (id, path, event, head branch, repository, status, conclusion, called workflows, artifact names) for the run named by its latest `wc-bump-verification` record at the head, read with `github.token` (`WC_ACTIONS_TOKEN`), or null when it cannot be read. `decide()` stays pure: it only reads the snapshot. The fix class's backstop is the one `readiness` measured, trusted only while the snapshot's head equals the head readiness measured it on (`readiness_head_sha`: the head its backstop step checked out, and empty when a later read of the PR saw another); a moved head fails `backstop_holds`. `review_converged` needs readiness's `ready` and the issue's newest review verdict for the PR (`board_item_marker.last_converged_review_head`) to have converged on the snapshot's head: readiness resumed from an earlier run's marker never re-checks that the review saw this head (FR-003).
5. `board_merge.py` evaluates and writes a decision JSON.
6. If `may_merge`, run `gh pr merge --squash <pr> --match-head-commit <head_sha>`, capturing stderr. A failure `classify_refusal` calls `transient` (head or base moved, a 5xx, mergeability still being computed, including the API's bare "Pull Request is not mergeable" that reaches stderr only when gh's own pre-check saw no blocked state) is retried once, only after the snapshot is re-fetched and the decision re-derived from it, pinned to the head that decision names. A second transient failure is outcome `transient`, never `refused`.
7. Announce on the PR and the issue, once per head, outcome and reason: every announcement ends with a `wc-board-merge-outcome` marker (`head_sha`, `class`, `outcome`, `reason`), and an outcome the PR's snapshot already carries from the App is not posted again.
8. Fix class: write the issue marker `merged` or `handed-over`. Bump class: no board item marker; the `refused` outcome marker on the PR releases it until its head moves. A maintainer `/stop` on the `auto-update:tracking` issue is recorded there by step 3's stop check (`board:stalled` and a `step=stalled` marker), and the pick skips that issue's bump PRs until a maintainer removes `board:stalled`, as for a fix item.

## Forbidden

`--admin`, `--auto`, `gh pr review --approve`, a second merge method, and any push to `main`. Gate `verify-board-merge.py` enforces this.

## Announcement

Fix PR: posted on the PR and the resolved issue. Bump: posted on the PR and the `auto-update:tracking` issue.

- **Merged**: head SHA, class, every condition's result, and the prove disposition (re-drive pending, or why not needed).
- **Refused**: head SHA, `refusal_class`, GitHub's stderr quoted, and the sentence "handed to a maintainer".
- **Transient**: head SHA, the class, GitHub's stderr quoted, and that it is not handed over as refused.
- **Not merged**: the failed condition's name. A PR merged by someone else, or at another head, is announced as merged elsewhere (`merged_elsewhere`), never as "Not merged".

Quoted text never carries a marker: `<!--` in it is defanged before the App posts it.

## `board_merge.py` interface

- `snapshot_complete` (both classes, after `kill_switch_clear`): the snapshot carries its counts, read at the snapshot's head; the files and commits lists are exactly their counts long (REST stops at 3000 files and 250 commits, so a longer PR fails here), the comments list is at least its count, and the head is among the commits. A truncated or inconsistent snapshot is not merged, never decided from a partial list.
- Identity is the account GitHub resolved, never a login or email alone: the PR author needs `author.is_bot` and the App's login (both classes, and the bump-shape filters `bump_shaped`/`pick_bump_candidate`); every commit's REST `author` must be the App's account (`type` Bot, the App's login), so a commit GitHub resolved to no account is never the bot's (GitHub resolves that author from the commit's git email, which anyone with push access can set, so this is attribution; what proves the head is the stage's own is the run binding below); and only comments whose REST `user` is the App's account (`board_item_marker.is_loop_marker_author`) carry a verification or outcome record.
- `evaluate_fix(snapshot, review_converged, backstop_holds, paused, switch_on, bot_login)` returns a MergeDecision. `decide(payload)` derives its `review_converged` and `backstop_holds` from the payload's readiness values, `readiness_head_sha` and `issue_comments`, as step 4 says. `eligible_class` holds only for a PR the App authored (`author.is_bot` and the App's login) on a `fix/<issue>-<slug>` branch whose base is `main` (FR-005); `attributed_to_auto_update` also requires base `main`.
- `evaluate_bump(snapshot, records, bot_login, paused, switch_on)` returns a MergeDecision. `verification_passed_at_head` needs the latest record at the head to have passed and `verification_run_confirms(record, snapshot["verificationRun"], head)`: the run's id is the record's `run_id`, its path is `AUTO_UPDATE_WRAPPER_PATH`, its event is `schedule` or `workflow_dispatch`, its `head_branch` is `main` (a dispatch on another branch runs that branch's workflows), it is `completed` with conclusion `success`, it called this repository's `AUTO_UPDATE_STAGE_PATH` (`<repo>/<path>`), and it carries the artifact `wc-bump-verification-<head_sha>`. Anything unconfirmed fails closed.
- `classify_refusal(stderr)` returns one of `workflow-scope`, `transient`, `conflict`, `protection`, `other`; `RETRYABLE_REFUSAL_CLASSES` names the ones retried (`transient`).
- `pick_bump_candidate(snapshots, bot_login, stalled_issues=())` returns `{pr, issue}` or None, skipping a PR whose tracking issue is in `stalled_issues`; `handed_over_at_head(snapshot, bot_login)` and `already_announced(snapshot, bot_login, record)` read the App's own outcome markers.
- `CONDITIONS_FIX`, `CONDITIONS_BUMP` and `REFUSAL_CLASSES` are the name tuples the gate cross-checks against the fixtures.

## Auto-update stage change

The act job posts one `wc-bump-verification` marker comment per verification on the upgrade PR, bound to the commit it verified and pushed (never a re-read of the PR's head). The comment is the record and nothing else: `board_merge.bump_records()` counts a marker only when the App comment's whole body is exactly what `board_item_marker.render_bump_verification()` renders for it. Other App comments quote untrusted text (issue bodies, GitHub's stderr), so a marker quoted inside one is never a pass, even when it copies a real record byte for byte.

The record's values are public, so anything holding the App token (a stage agent that may comment, a conversation reply posted verbatim) could post a byte-exact one. After posting it, the act job uploads the artifact `wc-bump-verification-<head_sha>` ("Record the verified head on the run", `if-no-files-found: error`), naming the head the record names; nothing between the post and the upload may fail the step. Only that run's own jobs can upload into it, so the merge decision counts a record only for a run that carries it (`verification_run_confirms`).

A failed post is retried; a lasting failure fails the step and says on the issue that the PR awaits a human merge. The PR stays open and its branch stays, so the next run's guard declines the candidate as already open; the stage never closes the PR to re-propose it, which would repeat the same lasting failure on every scheduled run. The stage never merges its own PR (FR-013).
