# Reference: Current Default Tool Lists Per Stage (FR-013)

**Feature**: 026-configurable-tool-lists

Draft of the per-stage default reference FR-013 requires ("a consumer can
determine, from documentation alone, what each stage's default tool lists
are" — SC-006). These are the tool lists **already shipped today**, as
literal inline `--allowedTools`/`--disallowedTools` values in each stage
workflow — this feature does not change any of them, only makes them
extendable/replaceable. Carried into `specs/010-reusable-pipeline/contracts/
stage-interfaces.md` verbatim at implementation time (research.md D7).

Every list below additionally has `ScheduleWakeup`, `Monitor`, `SendMessage`
in its disallowed set — interactive-resume tools a one-shot Action can
never service, stripped unconditionally regardless of consumer
configuration intent (they stay functionally inert even if a consumer's
`extra-allowed-tools`/override re-adds them, D-note in research.md
"Constitutional considerations").

| Stage | Internal step (`step-label`) | Default allowed | Default disallowed |
|---|---|---|---|
| intake | `intake` | `Skill,Read,Write,Edit,Glob,Grep,Bash(git status:*),Bash(git add:*),Bash(git commit:*),Bash(git checkout:*),Bash(git switch:*),Bash(git push:*),Bash(git branch:*),Bash(git log:*),Bash(git diff:*),Bash(git show:*),Bash(git ls-tree:*),Bash(echo:*),Bash(ls:*),Bash(mkdir:*),Bash(cat:*),Bash(gh issue view:*),Bash(gh issue edit:*),Bash(gh issue comment:*),Bash(gh pr create:*),Bash(gh label create:*)` | `WebFetch,ScheduleWakeup,Monitor,SendMessage` |
| clarify | `clarify` | `Read,Edit,Write,Glob,Grep,Bash(git status:*),Bash(git add:*),Bash(git commit:*),Bash(git push:*),Bash(git log:*),Bash(git diff:*),Bash(cat:*),Bash(gh issue view:*),Bash(gh issue comment:*),Bash(gh pr list:*),Bash(gh pr view:*),Bash(gh pr edit:*)` | `WebSearch,WebFetch,ScheduleWakeup,Monitor,SendMessage` |
| plan | `plan.direct-commit` | `Skill,Read,Write,Edit,Glob,Grep,Bash(git status:*),Bash(git add:*),Bash(git commit:*),Bash(git push:*),Bash(git log:*),Bash(git diff:*),Bash(git show:*),Bash(git ls-tree:*),Bash(git branch:*),Bash(echo:*),Bash(ls:*),Bash(mkdir:*),Bash(cat:*),Bash(.specify/scripts/bash/setup-plan.sh:*),Bash(bash .specify/scripts/bash/setup-plan.sh:*),Bash(.specify/scripts/bash/check-prerequisites.sh:*),Bash(bash .specify/scripts/bash/check-prerequisites.sh:*),Bash(.specify/scripts/bash/update-agent-context.sh:*),Bash(bash .specify/scripts/bash/update-agent-context.sh:*),Bash(gh issue view:*),Bash(gh issue comment:*)` | `WebFetch,ScheduleWakeup,Monitor,SendMessage` |
| plan | `plan.pr` | same as `plan.direct-commit` plus `Bash(git checkout:*),Bash(git switch:*),Bash(gh pr create:*),Bash(gh pr list:*)` | `WebFetch,ScheduleWakeup,Monitor,SendMessage` |
| tasks | `tasks.direct-commit` | `Skill,Read,Write,Edit,Glob,Grep,Bash(git status:*),Bash(git add:*),Bash(git commit:*),Bash(git push:*),Bash(git log:*),Bash(git diff:*),Bash(git show:*),Bash(git ls-tree:*),Bash(git branch:*),Bash(echo:*),Bash(ls:*),Bash(cat:*),Bash(.specify/scripts/bash/setup-tasks.sh:*),Bash(bash .specify/scripts/bash/setup-tasks.sh:*),Bash(.specify/scripts/bash/check-prerequisites.sh:*),Bash(bash .specify/scripts/bash/check-prerequisites.sh:*),Bash(gh issue view:*),Bash(gh issue comment:*)` | `WebSearch,WebFetch,ScheduleWakeup,Monitor,SendMessage` |
| tasks | `tasks.pr` | same as `tasks.direct-commit` plus `Bash(git checkout:*),Bash(git switch:*),Bash(gh pr create:*),Bash(gh pr list:*)` | `WebSearch,WebFetch,ScheduleWakeup,Monitor,SendMessage` |
| implement (⟲ converge) | `implement.cycle` | `Skill,Read,Write,Edit,Glob,Grep,Bash(git status:*),Bash(git add:*),Bash(git commit:*),Bash(git push:*),Bash(git log:*),Bash(git diff:*),Bash(git ls-tree:*),Bash(git branch:*),Bash(echo:*),Bash(git show:*),Bash(ls:*),Bash(cat:*),Bash(yamllint:*),Bash(actionlint:*),Bash(shellcheck:*),Bash(jq:*),Bash(mkdir:*),Bash(.specify/scripts/bash/check-prerequisites.sh:*),Bash(bash .specify/scripts/bash/check-prerequisites.sh:*),Bash(gh issue view:*),Bash(gh issue comment:*)` | `WebSearch,WebFetch,ScheduleWakeup,Monitor,SendMessage` |
| implement (⟲ converge) | `implement.retry` | same as `implement.cycle` plus `Bash(git pull:*),Bash(git fetch:*),Bash(git reset:*)` | `WebSearch,WebFetch,ScheduleWakeup,Monitor,SendMessage` |
| implement (⟲ converge) | `implement.post-progress-comment` | `Bash(git log:*),Bash(git diff:*),Bash(git show:*),Bash(gh issue comment:*)` | `WebSearch,WebFetch,ScheduleWakeup,Monitor,SendMessage` |
| finalize | `finalize` | `Read,Glob,Grep,Bash(git log:*),Bash(git diff:*),Bash(git show:*),Write` | `WebSearch,WebFetch,ScheduleWakeup,Monitor,SendMessage` |
| cleanup | `cleanup` | `Read,Glob,Grep,Bash(git log:*),Bash(git diff:*),Bash(git show:*),Write` | `WebSearch,WebFetch,ScheduleWakeup,Monitor,SendMessage` |
| rebase | `rebase` | `Read,Edit,Grep,Glob,Bash(git status:*),Bash(git diff:*),Bash(git add:*),Bash(git rebase --continue:*),Bash(git rebase --abort:*)` | `WebSearch,WebFetch,ScheduleWakeup,Monitor,SendMessage` |
| watchdog | `watchdog.diagnose` | `Read,Grep,Bash(gh:*),Bash(git log:*),Bash(git diff:*)` (deliberately read-only) | `WebSearch,WebFetch,Write,Edit,Bash(git commit:*),Bash(git push:*),ScheduleWakeup,Monitor,SendMessage` |
| watchdog | `watchdog.propose-fix` | `Read,Grep,Glob,Edit,Write` | `WebSearch,WebFetch,Bash,ScheduleWakeup,Monitor,SendMessage` |

`implement.cycle`/`implement.retry` no longer carry `Bash(gh run view:*)`/
`Bash(gh run list:*)` (specs/033-pr-conversation-commands T064, Gate 12 of
`lint-workflows.yml`): the agent step's `GH_TOKEN` is the App token, which
per `docs/setup.md` has no Actions permission, and the prompt never
instructed the agent to use either tool — same class of defect as T065's
removal from `pr-conversation.act` below.

Sources: `.github/workflows/{intake,clarify,plan,tasks,implement,finalize,
cleanup,rebase,watchdog}.yml` (`claude_args:` blocks, each stage's agent
step(s)) as of this feature's planning date. If a future change to those
files edits a default list, this table (and its carried-over copy in
`specs/010-.../contracts/stage-interfaces.md`) must be updated in the same
change — the composite action reads these as literal call-site inputs
(`tool-composition-action.md`), so drift here is a documentation bug, not a
behavior bug.
