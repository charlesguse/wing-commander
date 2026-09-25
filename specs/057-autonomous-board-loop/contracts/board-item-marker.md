# Contract: Board Item Marker

## Write

At the end of every job that changes a board item's step, the loop posts
(or updates, by editing its own most recent status comment rather than
appending a duplicate) a comment on the issue whose body ends with:

```html
<!-- wing-commander-board-item: {"step":"<step>","round":<n>,"pr":<n|null>,"branch":"<name|null>","base_sha":"<sha|null>"} -->
```

The visible part of the comment is the human-legible outcome (FR-044);
the marker is never the only content — a maintainer reading the comment
sees the same information the marker encodes.

## Read (resume)

A run that finds an eligible/selected issue first checks for this marker
on the issue's most recent bot comment. The marker is a **fast path
only** (research.md D21): every field it supplies is re-derived from live
GitHub state before any durable action is taken:

| Marker field | Re-derived from |
|---|---|
| `branch` | `git ls-remote origin 'refs/heads/<branch>'` |
| `pr` | `gh pr list --search "<issue_number> in:body" --json number,state` |
| `step` | the PR's own state (open/merged/closed) and review-finding count, not trusted from the marker alone |

If the marker is missing, unparsable, or contradicts live state (e.g. it
names a branch that was deleted), the loop falls back to what live state
shows and proceeds from there — never to a second branch/PR for an issue
that already has one (FR-054), and never to undefined behavior.

## Author rule (issue #555)

A marker is read only from a comment the loop's own GitHub App posted:
`user.type == "Bot"` and `user.login == <app-slug>[bot]`, the slug coming
from `wing-commander-context`'s `bot-slug` output.
`board_item_marker.is_loop_marker_author()` is the one predicate; the
stop check's `**Run:**` scan uses the same one (#547).
`read_marker()` / `read_marker_with_timestamp()` take the bot login as a
required argument and skip every other comment, so a marker typed by
anyone else, a maintainer or another App included, is ignored. Every
reader (the select job's in-flight detection and PR lookup, the resume
step, prove-gate) fetches comments with `user{login,type}` and passes the
login. `board_eligibility.py` exits non-zero when its stdin payload has
no `bot_login`, or only `[bot]` (an empty App slug).

The resume step also checks the fields it adopts. It adopts a marker
`branch` only when it is named `fix/<issue>-<slug>`, as the fix job names
branches (`board_item_marker.is_loop_branch()`). It adopts a marker `pr`
only when that PR carries `board:owned` and its head repository is this
repository (`BOARD_PR_OWNED_JQ` in board-loop.yml). Anything else is a
stale marker: triage, with PR, branch, round and base-sha cleared
(FR-022). Two exceptions hold instead, as the no-op step `awaiting-merge`,
passing nothing on: an `awaiting-merge` marker whose PR may still be open,
and a marker PR that is still OPEN but fails the ownership check (e.g.
`board:owned` removed), since triage could then cut a second branch/PR
beside it (FR-054). The select job's PR lookup records such a PR as
`board_eligibility.UNOWNED_OPEN_PR_STATE`, so the item is neither
in-flight nor picked by the fallback until the PR closes; the hold is
reached only on a race, never every run.

## Non-maintainer content

The marker itself is written only by the loop's own deterministic code —
never derived from or influenced by a non-maintainer's comment text
(FR-056). A non-maintainer comment on the issue is data the loop may read
when deciding what to show a human, never a value that changes `step`,
`round`, `branch`, or `pr`.
