# Contract: `reusable-pr-conversation.yml` (draft)

Draft of the row this feature adds to
`specs/010-reusable-pipeline/contracts/stage-interfaces.md`, in that file's
own normative table format. This plan stage only drafts the content; the
actual edit to that shared file happens during the implement stage
(`plan.md` Project Structure — the same deferral 029-intake-issue-comments
and 031-stage-environment-binding used for their own contract additions).

## reusable-pr-conversation.yml

| | |
|---|---|
| Inputs | `pr-number` (number, required); `event-kind` (string `review`\|`review-comment`\|`issue-comment`, required); `comment-id` or `review-id` (number, required — whichever `event-kind` implies); `body` (string, required — the untrusted request text); `actor-login` (string, required); `actor-association` (string, required); `confirm-categories` (string, default `""` — comma-separated `RequestClassification.category` values, or `all`); `confirm-environment` (string, default `pr-conversation-confirm`); `model` (string, default `claude-sonnet-5`); `max-turns` (number, default `40`); plus the common inputs every stage declares identically (`pipeline-repo`, `default-branch`, `use-bedrock`/`aws-role-arn`/`aws-region`, `spec-prefix`/`spec-draft-prefix`/`plan-prefix`/`tasks-prefix` — for the `PullRequestIdentity.qualifies` check, data-model.md — `environment`/`environment-deployment`, the four tool-list inputs) |
| Preconditions | spec-kit present; `PullRequestIdentity.qualifies == true` (data-model.md — base ref is the default branch, head ref starts with `spec-prefix` and not `spec-draft-prefix`/`plan-prefix`/`tasks-prefix`); lifecycle issue (resolved from the PR's `spec:` label) is open |
| Behavior | Two jobs. `classify-and-announce` (unprotected, no `environment:` binding): validate `PullRequestIdentity`; stage `body` as untrusted data (mirrors `clarify.yml`); run the bounded classify+draft agent step (`contracts/classification-schema.md`) producing 1..N `RequestClassification`s; deterministically compute `requires-confirmation` per classification against `confirm-categories` (never agent-decided — FR-020); post one `IntentAnnouncement` callout per classification via the existing `wing-commander-callout` composite, embedding the run URL, before job 2 starts (FR-023). `act` (job-level `environment: {name: <confirm-environment-or-empty>, deployment: false}`, per classification — spec 031's binding contract): execute each classification's route per `contracts/converge-fold-in.md` (in-scope-change), `contracts/spinoff-routing.md` (new-functionality, small-unrelated-change, manual-step-permission), or a direct reply (question, needs-info, push-back, no-action), and `contracts/autonomy-and-confirmation.md`'s stop procedure (stop). Every out-of-PR artifact triggers an `OutstandingTaskItem` post to the lifecycle issue (FR-008/FR-013) in the same job. |
| Outputs | none (side effects only): PR replies (one per classification, FR-014); for in-scope-change, a `spec-meta.json`+`tasks.md` commit on `spec/<slug>` plus a `wing-commander-5-implement.yml` dispatch (no output — outcome is reported asynchronously by that stage's own existing progress-comment step, per `contracts/converge-fold-in.md`); for spin-off categories, a new issue or PR plus a lifecycle-issue outstanding-task-item comment |

## New "Wrapper gate obligations" bullet (for the shared conventions section)

> commenter is an authorized maintainer (OWNER/MEMBER/COLLABORATOR — **no**
> requester carve-out) and not a bot before pr-conversation.

## New default tool list rows (for the "Per-stage default tool lists" table)

| Stage | Internal step (`step-label`) | Default allowed | Default disallowed |
|---|---|---|---|
| pr-conversation | `pr-conversation.classify` | `Read,Grep,Glob,Bash(git log:*),Bash(git diff:*),Bash(git show:*),Bash(cat:*),Bash(gh pr view:*),Bash(gh issue view:*),Bash(gh search issues:*)` (deliberately read-only — mirrors `watchdog.diagnose`) | `Write,Edit,WebSearch,WebFetch,Bash(git push:*),Bash(git commit:*),ScheduleWakeup,Monitor,SendMessage` |
| pr-conversation | `pr-conversation.act` | `Read,Write,Edit,Glob,Grep,Bash(git status:*),Bash(git add:*),Bash(git commit:*),Bash(git push:*),Bash(git log:*),Bash(git diff:*),Bash(cat:*),Bash(gh issue view:*),Bash(gh issue comment:*),Bash(gh issue create:*),Bash(gh issue edit:*),Bash(gh pr view:*),Bash(gh pr comment:*),Bash(gh pr create:*),Bash(gh pr edit:*),Bash(gh api:*),Bash(gh run list:*),Bash(gh run cancel:*),Bash(gh workflow run:*),Bash(gh label create:*),Bash(gh search issues:*),Bash(gh search prs:*)` | `WebSearch,WebFetch,ScheduleWakeup,Monitor,SendMessage` |

The classify step is scoped strictly read-only (like `watchdog.diagnose`)
so a misjudged classification cannot itself mutate anything before the
intent-announcement is posted (FR-023's ordering guarantee is structural,
not merely procedural). `pr-conversation.act`'s broad `gh` allowlist
reflects the breadth of FR-003's eight routes; each route is still
individually deterministic-gated (data-model.md), not left to the agent's
own tool discretion.
