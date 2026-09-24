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

## Non-maintainer content

The marker itself is written only by the loop's own deterministic code —
never derived from or influenced by a non-maintainer's comment text
(FR-056). A non-maintainer comment on the issue is data the loop may read
when deciding what to show a human, never a value that changes `step`,
`round`, `branch`, or `pr`.
