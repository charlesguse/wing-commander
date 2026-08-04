# Contract: Comment Trust Gate

The deterministic step this feature adds to `intake.yml`, placed after the
existing "Report run started on issue" step and before "Compose tool args
(intake)" — the same relative position `clarify.yml` uses for its own
"Stage the answer as a data file" step, run with the bot token
(`steps.ctx.outputs.token`) that step already establishes, gated on
`steps.lifecycle-gate.outputs.is-open == 'true'` like every other step in
the job.

## Inputs

| Source | Field(s) used |
|---|---|
| `gh api repos/${GITHUB_REPOSITORY}/issues/${{ inputs.issue-number }}` | `.user.id` (issue author id) |
| `gh api repos/${GITHUB_REPOSITORY}/issues/${{ inputs.issue-number }}/comments --paginate` | `.user.id`, `.user.login`, `.user.type`, `.author_association`, `.created_at`, `.body` per comment |

Both calls use `steps.ctx.outputs.token` (the App-installation token every
other read/write in this stage already uses) via `GH_TOKEN`.

## Qualification rule (FR-002, FR-003 — data-model.md's `qualifies()`)

A comment qualifies for incorporation if and only if:

1. `user.type != "Bot"` — unconditional; a bot's `author_association` is
   never consulted (FR-003: "regardless of the bot account's association").
2. AND at least one of:
   - `author_association` ∈ `{OWNER, MEMBER, COLLABORATOR}`, or
   - `user.id == <issue author's id>` (comparison by id, not login).

This is exactly `wing-commander-2-clarify.yml`'s existing trigger-level `if:`
condition, applied per-comment instead of to one triggering comment.

## Outputs (step outputs — this step's public contract)

| Output | Type | Meaning |
|---|---|---|
| `comments-file` | string (path) | Path to the staged qualifying-comments file (contracts/comment-staging-format.md), or empty if `qualifying-count == 0` (no file is written in that case — nothing for the agent to read). |
| `qualifying-count` | integer (string) | Number of comments that passed the rule above. `0` reproduces today's body-only behavior (FR-007). |
| `total-count` | integer (string) | Total comments on the issue, qualifying or not, bot or not. |
| `excluded-human-count` | integer (string) | Comments where `user.type != "Bot"` but the rule's clause 2 failed — the signal `contracts/notice-callout.md`'s condition is built from. |

No output ever carries comment body text or login/id values for
non-qualifying comments — only counts and the path to a file whose contents
are, by construction (comment-staging-format.md), qualifying-only.

## Failure mode

This step MUST NOT hard-fail the job on an empty comment list (zero
comments is the common case and is explicitly in scope — FR-007) or on a
`gh api` pagination edge (empty array is valid JSON, handled by the same
jq filter as any other count). It follows `wing-commander-preflight`'s
established convention only for genuine API failures (non-2xx from `gh
api`), which propagate as an ordinary step failure like any other `gh`
call already in this workflow — no bespoke error handling beyond what
`clarify.yml`'s existing `gh api` step already relies on (`set -e`
default, no `continue-on-error`).

## Consumers

- `contracts/comment-staging-format.md` — defines what `comments-file`
  actually contains.
- `contracts/notice-callout.md` — consumes `qualifying-count` and
  `excluded-human-count`.
- The agent step's prompt — consumes `comments-file` (path only, read via
  the `Read` tool) and is told to treat it, and only it, as comment content
  (research.md D5).
