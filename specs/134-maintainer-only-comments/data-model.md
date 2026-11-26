# Data Model: Comment-Triggered Stages Act Only on Maintainers

No stored data. These are the values the rule reads and the outputs it produces.

## Comment (GitHub REST `issues/comments/{id}`)

| Field | Use |
|---|---|
| `id` | The stage's existing `comment-id` input. |
| `user.type` | `Bot` never qualifies. |
| `author_association` | Qualifies only when `OWNER`, `MEMBER` or `COLLABORATOR`. |
| `body` | Staged as untrusted data, unchanged. |
| `user.login` | Staged as the author file, unchanged. |

## Issue (GitHub REST `issues/{number}`)

| Field | Use |
|---|---|
| `author_association` | Decides whether the relay paragraph is appended (FR-008). |
| `user.id` | No longer read by any filter or gate. |

## Maintainer set

`{OWNER, MEMBER, COLLABORATOR}`, the same literal set every gate already uses (`fromJSON('["OWNER","MEMBER","COLLABORATOR"]')`).

## Outputs

| Producer | Output | Values |
|---|---|---|
| clarify's check step (D1) | `maintainer` | `true` / `false`. A failed read fails the step; it never yields `true`. |
| `wing-commander-requester-relay-note` (D3) | appends to `body-file` | One paragraph, or nothing. |
| `wing-commander-issue-context` (D4) | `qualifying-count`, `excluded-human-count`, `comments-file` | Same names and formats as today; only membership changes. |
