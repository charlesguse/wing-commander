# Contract: `wing-commander-9-pr-conversation.yml` Trigger and Actor Gate

Ground with zero existing precedent in this repository (research.md D1) —
no published stage or wrapper today listens to `pull_request_review` or
`pull_request_review_comment`. This contract is the wrapper-owned half of
constitution VII's split: the stage (`pr-conversation.yml`) reads no
`github.event.*`; every event fact below arrives as a declared
`workflow_call` input per `contracts/reusable-pr-conversation.md`.

## Triggers

```yaml
on:
  pull_request_review:
    types: [submitted]
  pull_request_review_comment:
    types: [created]
  issue_comment:
    types: [created]
```

## Event → input extraction (per `event-kind`)

| `event-kind` | Fires on | `pr-number` | `body` | `comment-id`/`review-id` | actor fields |
|---|---|---|---|---|---|
| `review` | `pull_request_review` | `github.event.pull_request.number` | `github.event.review.body` | `github.event.review.id` | `github.event.review.user.{login,type}`, `github.event.review.author_association` |
| `review-comment` | `pull_request_review_comment` | `github.event.pull_request.number` | `github.event.comment.body` | `github.event.comment.id` | `github.event.comment.user.{login,type}`, `github.event.comment.author_association` |
| `issue-comment` | `issue_comment`, filtered to `github.event.issue.pull_request != null` | `github.event.issue.number` | `github.event.comment.body` | `github.event.comment.id` | `github.event.comment.user.{login,type}`, `github.event.comment.author_association` |

A plain-issue `issue_comment` (no `pull_request` key on the issue) never
reaches the `if:` — that traffic stays exclusively `clarify.yml`'s, exactly
as `wing-commander-2-clarify.yml`'s own `!github.event.issue.pull_request`
guard excludes PR comments from clarify today (the inverse guard, applied
here).

## Actor gate (job-level `if:`, FR-002/FR-019/FR-021)

```yaml
jobs:
  pr-conversation:
    if: >-
      (github.event.review.user.type != 'Bot' || github.event.comment.user.type != 'Bot') &&
      contains(
        fromJSON('["OWNER","MEMBER","COLLABORATOR"]'),
        github.event.review.author_association || github.event.comment.author_association
      )
```

The illustrative expression above is refined at implementation time to the
exact per-event-kind field access (only one of `review`/`comment` is
populated per invocation — the `||` fallback pattern already used
elsewhere in this repository's `if:` expressions for the same reason).
**Deliberately, unlike `wing-commander-2-clarify.yml` and `wing-commander-1-intake.yml`'s
comment-reading precedents, there is no `|| actor.id == issue.author.id`
carve-out** — FR-019 states plainly that "a non-maintainer, including the
original requester of the lifecycle issue, cannot command the stage
directly." A bot actor fails the gate and the job's `if:` prevents the run
from starting at all — no reply is posted (FR-002, FR-021's second
sentence), distinct from the non-bot-unauthorized case (FR-021's first
sentence), which the *stage* handles by replying with a notice, since only
the stage — not the cheap wrapper `if:` — can post a PR comment.

Because the wrapper's `if:` can only stop the run outright (bot case) and
cannot itself post a reply, the non-bot-unauthorized notice (FR-021) is
produced by a **second**, narrower gate: the wrapper always dispatches to
the stage when the actor is non-bot, passing `actor-association` through
as an input; the stage's own first deterministic step checks authorization
and, if it fails, posts the notice and stops before the classify agent
step runs (no cost incurred on an unauthorized request beyond one cheap
`gh` call).

## Non-goals

- No `workflow_dispatch` entry point on this wrapper — unlike the
  chained stages (`implement`, `finalize`, ...), `pr-conversation` has no
  predecessor stage that dispatches it; it is purely event-triggered.
- No filtering on PR identity (`PullRequestIdentity.qualifies`,
  data-model.md) at the wrapper level — that check requires a `gh api`
  call (the base/head refs aren't in any of the three trigger payloads'
  cheap fields in a form the wrapper can evaluate without a checkout), so
  it lives in the stage's own preflight, mirroring `tasks.yml`'s
  `mode: approved` precedent of validating deeper preconditions inside the
  stage rather than the wrapper `if:`.
