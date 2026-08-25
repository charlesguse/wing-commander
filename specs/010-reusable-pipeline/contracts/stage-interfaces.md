# Contract: Published Stage Interfaces

The `workflow_call` signature of every published stage. Input/secret names
below are normative; implementation may add inputs but may not remove or
repurpose these without a major version bump (see [versioning.md](versioning.md)).

## Conventions shared by all stages

**Secrets** (declared by every stage that runs an agent or writes to the repo):

| Secret | Required |
|---|---|
| `claude-code-oauth-token` | one of the two Claude credentials (agent stages) |
| `anthropic-api-key` | one of the two Claude credentials (agent stages) |
| `speckit-app-id` | yes — GitHub App identity for pushes/PRs/comments |
| `speckit-app-private-key` | yes |

Credential behavior: see [credentials.md](credentials.md).

**Common inputs**:

| Input | Type | Default | Purpose |
|---|---|---|---|
| `pipeline-repo` | string | the publishing repository | Where the stage checks out its own shared composite actions, at `github.job_workflow_sha` (research D3). Only forks that republish need to set it. |
| `default-branch` | string | `""` = derive | The consuming repository's default branch. When empty, the stage derives it itself (`gh repo view --json defaultBranchRef`) — stages never assume `main` (spec edge case 3). |
| `use-bedrock` | boolean | `false` | Route the stage's agent step(s) through AWS Bedrock instead of the Anthropic API. Off by default — a zero-change no-op for Anthropic adopters ([`specs/016-bedrock-support/`](../../016-bedrock-support/contracts/bedrock-provider.md)). |
| `aws-role-arn` | string | `""` | IAM role ARN the stage assumes via OIDC for Bedrock. Required when `use-bedrock` is true. |
| `aws-region` | string | `""` | AWS region for both credential configuration and the Bedrock endpoint. Required when `use-bedrock` is true. |
| `spec-draft-prefix`, `spec-prefix`, `plan-prefix`, `tasks-prefix`, `impl-prefix` | string | per-branch-type: `spec-draft/`, `spec/`, `plan/`, `tasks/`, `impl/` | Optional per-branch-type overrides for the pipeline's branch-name prefixes, newly common across the CREATE-capable stages. Each defaults to its literal shown, so a consumer can override branch naming without touching the rest of the artifact contract. |
| `environment` | string | `""` | Name of a GitHub deployment environment (in the consuming repository) to bind every job in the stage to, applying its protection rules before any step runs. Empty is a verified true no-op — no environment applied, no gate, no deployment record ([`specs/031-stage-environment-binding/`](../../031-stage-environment-binding/contracts/environment-binding.md)). |
| `environment-deployment` | boolean | `true` | Whether binding to `environment` creates a GitHub deployment record. `true` mirrors GitHub's own default (every protection-rule type, including custom App rules, works out of the box); `false` keeps the gate but suppresses the deployment record. |
| `runner` | string | `ubuntu-latest` | Runner label(s) every job in the stage runs on. A single label, or a JSON array applied as a conjunction (e.g. `["self-hosted","linux","x64"]`) — a value starting with `[` is parsed as JSON, anything else is used verbatim ([`specs/038-runner-container-passthrough/`](../../038-runner-container-passthrough/contracts/runner-container-passthrough.md)). |
| `container-image` | string | `""` | Container image every job in the stage runs inside. Empty means no container — every job runs directly on the runner, unchanged from today. A dedicated `verify-image-prerequisites` job checks the named image for every required tool before any agent-bearing job's own container is created. |
| `extra-allowed-tools` | string | `""` | FR-001. Comma-separated tool list, same syntax as the pipeline's own `--allowedTools` values (e.g. `Bash(gh pr view:*),Read`). Added to the stage's default allowed tools — union, not replacement. Unset/empty = no addition (SC-005). ([specs/026-configurable-tool-lists](../../026-configurable-tool-lists/contracts/tool-list-inputs.md); default lists per stage below.) |
| `extra-disallowed-tools` | string | `""` | FR-002. Comma-separated tool list. Added to the stage's default disallowed tools — union, not replacement. Unset/empty = no addition (SC-005). |
| `allowed-tools-override` | string | `__unset__` (sentinel — see below) | FR-003. When set to any value other than the sentinel default (including `""`), replaces the stage's default allowed tools entirely. `""` means "replace with nothing" (an explicit, intentional empty list), distinct from leaving the input unset. |
| `disallowed-tools-override` | string | `__unset__` (sentinel — see below) | FR-004. Same semantics as `allowed-tools-override`, for the disallowed list. |

**Why a sentinel default instead of `""`** (for `allowed-tools-override`/
`disallowed-tools-override`): GitHub Actions resolves an unset optional string
`workflow_call` input to the same value as an explicitly-passed `""` — there is
no native "not provided" for strings. FR-009 requires the pipeline to tell "not
provided" (keep defaults) apart from "explicitly empty" (an intentional
replace-with-nothing). `__unset__` is reserved for this purpose; it is not a
legal tool name and a consumer should never pass it deliberately.

**Append vs. replace** (evaluated independently per direction — a stage may
append on `allowed` while replacing `disallowed`): `extra-*` layers onto the
stage's built-in defaults (union); `*-override` discards those defaults and
uses exactly the supplied list. Supplying both `extra-allowed-tools` and a
non-sentinel `allowed-tools-override` (or the disallowed equivalent) is a
conflict (FR-010) — the stage fails before any agent step runs, naming the
stage, the direction, and both values. On multi-step stages (currently only
`implement`), the four inputs are stage-scoped: they apply identically to
*every* internal agent step, each composed against that step's own defaults
(D5). See the per-stage default lists below and
[specs/026-configurable-tool-lists](../../026-configurable-tool-lists/contracts/tool-list-inputs.md).

**What the agent is *told*, not only what it is permitted**: on `implement`,
the prompt's tooling paragraph embeds a complete sentence naming the shell
commands permitted for that run, rendered from the same composed allowed and
disallowed lists the step enforces (the composite's `shell-commands` output)
rather than from a hand-maintained copy. Configuring any of the four inputs
therefore changes the prompt as well as the enforcement. The statement
excludes every command the composed disallowed list fully covers, states an
unrestricted (`Bash`) grant as permitting any command — naming any surviving
command-specific denials as exceptions rather than staying silent about the
narrowing — and distinguishes an exact-command-only grant from an
any-arguments grant for the same command; non-`Bash` entries are omitted,
since the statement is about shell commands and the other tools are conveyed
by the tool interface itself. Render contract and guarantees enumerated in
[tool-composition-action.md](../../026-configurable-tool-lists/contracts/tool-composition-action.md#outputs).

**Universal behavior**:
- `on:` is `workflow_call` **only**; stages never read `github.event` — all
  event facts arrive as inputs (research D2).
- Deterministic preflight runs before any agent step: credential invariant +
  spec-kit presence + the stage's preconditions (research D4/D7). Failure stops
  the run with a message naming the missing item and the step that provides it
  (FR-004, FR-009).
- Every agent step declares `--model` and `--max-turns` from inputs/defaults
  (constitution II) and is followed by the metrics-summary step.
- All side effects land in the consuming repository only (FR-005).
- No branch-convention hardcoding: every reference to the consuming
  repository's default branch (checkout refs, PR bases, rebase targets) uses
  the `default-branch` input or its derived value — never a literal `main`
  (spec edge case 3). The `spec-draft/`, `spec/`, `plan/`, `tasks/`, `impl/`
  branch *prefixes* are configurable-with-defaults: each is a `workflow_call`
  input on the CREATE-capable stages (and, in this repo's wrappers, a
  repository variable `WING_COMMANDER_*_PREFIX`), defaulting to the literal
  shown, and remains part of the shared artifact contract (spec assumption 5).
- Chaining is opt-in: `next-workflow`-style inputs default to `""` = no
  dispatch, so any stage runs standalone (FR-002/US2). When set, the stage
  dispatches that workflow *file in the consuming repository* via
  `gh workflow run`, using the chaining payload contract below.
- Per-spec serialization: every stage that checks out and publishes to a
  specification's `spec/NNN-slug` working branch — `rebase`, `plan`, `tasks`
  (both `mode: generate` and `mode: approved`), `implement`, and `finalize` —
  declares the same job-level `concurrency: wing-commander-<spec-dir>` group
  (`cancel-in-progress: false`), so at most one of them ever runs against a
  given specification at a time (specs/013-serialize-rebase-stages/contracts/concurrency-groups.md).

**Wrapper gate obligations** (documented, adopter-owned — constitution V
guidance shipped in docs/adoption.md): maintainer-label entry gate before
intake; commenter is maintainer-or-author and not a bot before clarify;
never pass fork-PR head refs as checkout targets; commenter/reviewer is
`OWNER`/`MEMBER`/`COLLABORATOR` and not a bot before pr-conversation — with
**no** requester carve-out, unlike clarify/intake
(`specs/033-pr-conversation-commands/contracts/wrapper-gate.md`).

**Chaining payload contract**: when a stage dispatches a `next-workflow` /
`self-workflow`, the dispatch target is a *wrapper file in the consuming
repository*, and that wrapper's `workflow_dispatch` signature is therefore
part of this contract. A dispatch-target wrapper MUST declare these
`workflow_dispatch` inputs (snake_case — these are the historical dispatch
names; the wrapper translates them to the stage's kebab-case inputs):

| Dispatch target | Required `workflow_dispatch` inputs |
|---|---|
| implement wrapper (`next-workflow` of tasks; `self-workflow` of implement) | `spec_dir` (string), `issue` (string), `iteration` (string) |
| finalize wrapper (`next-workflow` of implement) | `spec_dir` (string), `issue` (string), `converged` (string) |

docs/adoption.md's wrapper examples MUST show these signatures verbatim.

## reusable-intake.yml

| | |
|---|---|
| Inputs | `issue-number` (number, required); `model` (string, default `claude-opus-5`); `max-turns` (number, default `50`) |
| Preconditions | spec-kit present in consumer checkout |
| Behavior | Allocate next feature number (scans `specs/` + open pipeline branches); fetch the issue's comments and stage only those from OWNER/MEMBER/COLLABORATOR accounts or the original issue author (never bots) to a data file, posting a visible notice if substantive comments existed but none qualified (specs/029-intake-issue-comments); run `/speckit-specify` against the issue title, body, and staged qualifying comments; create `spec-draft/NNN-slug` + draft spec PR to the default branch, write `spec-meta.json`, label issue (`spec:NNN-slug`, `stage:spec`), post clarification questions or ready-for-review comment |
| Outputs | `spec-dir`, `feature-num` |

## reusable-clarify.yml

| | |
|---|---|
| Inputs | `issue-number` (number, required); `comment-id` (number, required); `model` (string, default `claude-opus-5`); `max-turns` (number, default `40`) |
| Preconditions | spec-kit present; open `spec-draft/NNN-slug` PR for the issue's `spec:` label |
| Behavior | Fold the answers from the referenced comment into the draft spec PR, confirm on the issue |
| Outputs | none |

## reusable-plan.yml

| | |
|---|---|
| Inputs | `head-ref` (string) **or** `slug` (string) — one required; `merged` (boolean, default `true`); `model` (string, default `claude-sonnet-5`); `max-turns` (number, default `110`); `plan-review` (string `pr`\|`auto`, default `pr`); `next-workflow` (string, default `""`) — wrapper filename to dispatch for tasks |
| Preconditions | `specs/NNN-slug/spec.md` + `spec-meta.json` exist on the default branch; no existing `plan/NNN-slug` branch (duplicate guard) |
| Behavior | Derive+validate slug internally from `head-ref` (`spec-draft/` prefix) or take `slug` directly; create/reuse `spec/NNN-slug`; create lifecycle issue for hand-submitted specs; run `/speckit-plan`; `pr` opens a plan PR → `spec/NNN-slug` and stops — no dispatch; `auto` commits the plan directly to `spec/NNN-slug` and (if `next-workflow` set) dispatches tasks directly; either mode advances `spec-meta.json` to `plan` and flips the label; an unrecognized `plan-review` value fails open to `pr` and is surfaced (`::warning::`, step summary, lifecycle-issue comment) |
| Outputs | `spec-branch`, `spec-dir` |

## reusable-tasks.yml

| | |
|---|---|
| Inputs | `mode` (string `generate`\|`approved`, default `generate`); `head-ref` or `slug` (one required); `tasks-review` (string `auto`\|`pr`, default `auto`); `model` (string, default `claude-sonnet-5`); `max-turns` (number, default `60`); `next-workflow` (string, default `""`) — wrapper filename to dispatch for implement |
| Preconditions | `generate`: `plan.md` exists; `spec-meta.json.stage == "plan"` (or `stalled` on manual restart). `approved`: `spec-meta.json.stage == "tasks"` and `head-ref` is a `tasks/NNN-slug` branch |
| Behavior | `generate`: run `/speckit-tasks`; `auto` commits tasks.md to the spec branch and (if `next-workflow` set) dispatches implement directly; `pr` opens a `tasks/NNN-slug` PR and stops — no dispatch. `approved` (no agent work): the entry point for a merged tasks PR in `pr` review mode — validates the slug and dispatches `next-workflow` with `spec_dir`, `issue`, `iteration=1`. A `workflow_call` workflow has no triggers of its own, so the **wrapper** owns the `pull_request: closed` (base `spec/**`, head `tasks/*`, merged) trigger and calls this stage with `mode: approved` |
| Outputs | `spec-dir` |

## reusable-implement.yml

| | |
|---|---|
| Inputs | `spec-dir` (string, required); `issue-number` (number, required); `iteration` (number, required); `model` (string, default `claude-sonnet-5`); `max-turns` (number, default `180`); `max-iterations` (number, default `5`); `self-workflow` (string, default `""`) — wrapper filename for iteration N+1 re-dispatch; `next-workflow` (string, default `""`) — wrapper filename for finalize |
| Preconditions | `tasks.md` exists; `spec/NNN-slug` branch exists; `iteration <= max-iterations` |
| Behavior | One implement ⟲ converge iteration on the spec branch (deterministic convergence check, single tier-up retry on outright failure, stall marking — all internal, as today); converged or capped ⇒ dispatch `next-workflow` (if set) with `converged`; not converged ⇒ dispatch `self-workflow` (if set) with `iteration+1`; empty chaining inputs ⇒ report to issue and stop |
| Outputs | `converged` (boolean) |

## reusable-finalize.yml

| | |
|---|---|
| Inputs | `spec-dir` (string, required); `issue-number` (number, required); `converged` (boolean, required); `summary-model` (string, default `claude-haiku-4-5`); `max-turns` (number, default `20`) |
| Preconditions | `spec/NNN-slug` branch exists with commits ahead of the default branch |
| Behavior | Summarize diff + unchecked/manual tasks; open final PR `spec/NNN-slug` → default branch; comment manual-task list on issue; label `stage:review` |
| Outputs | `pr-number` |

## reusable-cleanup.yml

| | |
|---|---|
| Inputs | `head-ref` (string, required); `base-ref` (string, required); `merged` (boolean, required); `summary-model` (string, default `claude-haiku-4-5`); `max-turns` (number, default `20`) |
| Preconditions | identity-refusal check: derived slug's artifacts exist and self-identify consistently |
| Behavior | Self-select exactly one outcome from the three PR-closure shapes (teardown-done / teardown-rejected / mark-stalled) internally — wrappers pass raw PR facts on any `pull_request: closed` event; every non-matching shape is a no-op |
| Outputs | `outcome` (string) |

## reusable-rebase.yml

The stage the spec calls "auto-rebase" — `rebase` is its canonical published id.

| | |
|---|---|
| Inputs | `model` (string, default `claude-sonnet-5`); `max-turns` (number, default `50`) |
| Preconditions | none (discovers in-flight `spec/*` branches itself; empty discovery is a clean no-op) |
| Behavior | Discover → fan-out per-branch rebase onto the default branch; clean push with lease, agent conflict resolution with deterministic scope check, escalate-once marker on stuck branches — all internal, as today |
| Outputs | none |

## reusable-watchdog.yml

The run-validation-and-triage stage (`specs/015-pipeline-watchdog/`). Its
wrapper (`wing-commander-8-watchdog.yml`) owns the `workflow_run: [completed]`
trigger across all nine stage display names (including `"8 - Watchdog"` for
self-inspection) plus a `workflow_dispatch` `run-id` for manual re-inspection,
and resolves `run-id`/`run-name` before calling this stage.

| | |
|---|---|
| Inputs | `run-id` (string, required); `run-name` (string, required) — inspected run's display name; `diagnose-model` (string, default `claude-opus-5`); `diagnose-max-turns` (number, default `30`); `propose-fix-model` (string, default `claude-sonnet-5`) and `propose-fix-max-turns` (number, default `30`) — **deprecated**, accepted for v2 compatibility only: propose-fix was removed by spec 024 (FR-014) and no step reads either input; removal scheduled for the next major version, see issue #140 |
| Preconditions | none as a refusal gate — spec-slug/lifecycle-issue resolution is best-effort (a run not tied to a spec is still inspected and reported against its own run URL). The credential invariant still applies to the stage's one agent step (`watchdog.diagnose`) |
| Behavior | `collect → diagnose → triage → act`: five deterministic FR-006 collectors into one `signals.json`; one read-only `claude-opus-5` diagnose step emits zero+ Findings, each citing collector signal ids and a `class` drawn from a label-derived enum. Per Finding, `triage` runs a coexistence-suppression check, an evidence-validity gate, a signal-derived fingerprint, and a bounded, strongly-consistent `gh issue list` dedup read scoped to `pipeline-defect` + that finding's own `🐕 · <class>` label (not a search index — FR-018–FR-020 of spec 024). The dedup step records exactly one of five outcomes: `none` (file a new issue), `match-open` (comment on it), `match-closed` (reopen + comment), `data-integrity` (more than one issue carries the fingerprint — reported, never auto-acted on), and `unknown` (**the lookup itself failed** — filing is suppressed pending a maintainer's manual check, sharing no code path with `none`, so a broken lookup can never masquerade as "nothing found"). `act` performs that one remediation and always reports every Finding to the lifecycle issue. There is **no fix-proposal agent step, no rung ladder, and no guardrail config file** — the stage is a pure reporter (FR-014 of spec 024). `vars.WING_COMMANDER_WATCHDOG_PAUSED` is enforced wrapper-side, where no job starts at all; the stage-side write-suppression read of it survives only as a deprecated compatibility shim for a wrapper with no such gate (#152) — it stops writes but not work. `vars.WING_COMMANDER_WATCHDOG_SELF_DISPATCH_CAP` (default `3`) is genuinely stage-side: the run is still inspected and reported, only `act`'s write is suppressed. Identical rules apply to self-inspection (FR-018/FR-021) |
| Outputs | none (side effects only): a lifecycle-issue comment for every Finding on every run (FR-022) — the one write every path performs unconditionally — and, unless suppressed, one fingerprint-marked `pipeline-defect` issue per Finding, created/reused/reopened and labelled `pipeline-defect` + `🐕 · <class>`. **No pull request**: this stage opens none |

## reusable-auto-update-spec-kit.yml

The Spec Kit version auto-updater (`specs/027-auto-update-spec-kit/`). Like
`rebase` and `watchdog` it is an unnumbered maintenance stage with no
per-spec identity. Its wrapper (`wing-commander-auto-update-spec-kit.yml`)
owns the `schedule`/`workflow_dispatch`/`pull_request: [closed]`/`issue_comment:
[created]` triggers and the `WING_COMMANDER_AUTO_UPDATE_SPEC_KIT_PAUSED` gate,
resolving a single `trigger` input before calling this stage.

| | |
|---|---|
| Inputs | `trigger` (string, required — `scheduled`\|`dispatch`\|`pr-merged`\|`comment-reply`); `pr-number` (string); `pr-merged` (boolean, default `false`); `issue-number` (string); `comment-id` (string); `commenter-association` (string); `commenter-id` (string); `issue-author-id` (string); `stabilization-checks` (string, default `1`); `model` (string, default `claude-sonnet-5`) |
| Preconditions | none as a refusal gate — self-recognition is best-effort and marker-based (a `pull_request`/`issue_comment` event lacking this feature's PR/issue marker is a silent no-op; the `comment-reply` path additionally gates the commenter to a maintainer or the issue author). One `concurrency: wing-commander-auto-update-spec-kit` group serializes all cycles |
| Behavior | `health-check → detect → settle → evaluate-path → prepare → verify → act` plus `pr-merged`/`comment-reply` entry jobs: re-verify the pinned version (rollback on failure); detect the latest eligible upstream release and classify the delta; run a consecutive-daily-check settle window in the lifecycle issue's body marker; one read-only agent decides clean-bump / needs-migration / ambiguous-options; prepare the version-bump diff; verify it (lightweight always, +end-to-end for minor/major) in an isolated worktree; open the version-bump PR (pass), flag the issue (fail), or open a revert PR (health-check failure) |
| Outputs | none (side effects only): lifecycle-issue comments/label (`auto-update:failed` on any failure/rollback) and a version-bump/revert PR to the default branch — **never merged by this stage** (constitution V, FR-017); the success path closes its issue only via the PR's own `Closes #N` keyword on merge |

## reusable-pr-conversation.yml

Classifies and routes a maintainer's PR conversation on an implementation PR
(`specs/033-pr-conversation-commands/`). Its wrapper
(`wing-commander-9-pr-conversation.yml`) owns the `pull_request_review:
[submitted]` / `pull_request_review_comment: [created]` / `issue_comment:
[created]` triggers, the actor gate (see "Wrapper gate obligations" above),
and event→input extraction — this stage never reads `github.event`. Unlike
every other stage, it has **no `workflow_dispatch`** entry point: purely
event-triggered.

| | |
|---|---|
| Inputs | `pr-number` (number, required); `event-kind` (string `review`\|`review-comment`\|`issue-comment`, required); `body` (string, required, untrusted); `actor-login`/`actor-association` (string, required); `comment-id`/`review-id` (number, default `0`); `thread-path`/`thread-diff-hunk` (string, default `""`); `confirm-categories` (string, default `""` — comma-separated category list, or `all`); `confirm-environment` (string, default `pr-conversation-confirm`); `confirm-timeout-minutes` (number, default `1440` — bounds how long a confirm-gated leg may wait on its `environment:` approval before GitHub cancels the job outright, specs/042-post-review-fold-loop); `model` (string, default `claude-sonnet-5`); `max-turns` (number, default `40`); `implement-workflow` (string, default `""` — the consumer's implement wrapper filename, dispatched after a fold-in and cancelled alongside the announced run by `stop`; empty = no dispatch, per the opt-in chaining convention above) |
| Preconditions | PR base is the default branch and head starts with `spec-prefix` (not `spec-draft-prefix`/`plan-prefix`/`tasks-prefix`) — otherwise the whole run short-circuits with no reply; lifecycle issue is open |
| Behavior | `classify-and-announce → act → dispatch-once + report-fold-outcomes`: PR-identity + authorized-actor gates; stage the untrusted request; a read-only agent step classifies each distinguishable request into one of nine categories (`in-scope-change`, `question`, `needs-info`, `push-back`, `new-functionality`, `small-unrelated-change`, `manual-step-permission`, `stop`, `no-action`) and drafts its route's content; a deterministic (never agent-decided) gate computes per-classification confirmation requirements against `confirm-categories`; one `IntentAnnouncement` posted per classification before `act`'s `environment:` binding can begin evaluating. `act` runs one matrix leg per classification (`max-parallel: 1`): `in-scope-change`/`new-functionality current-spec` fold into `tasks.md` + `spec-meta.json` and reply confirming the fold-in — dispatch itself is no longer a per-leg effect (specs/042-post-review-fold-loop D1: a per-leg dispatch could contend for the same serialization slot as the implementation cycle it started, cancelling one against the other); `new-functionality new-spec` opens a `spec-request`-labeled issue; `small-unrelated-change` opens a PR within a deterministic size backstop (≤3 files, ≤40 lines) or re-routes to a new-spec issue otherwise; `manual-step-permission` performs/explains/opens a `permission-request`-labeled PR (deduped via a conservative-bias search); `needs-info`/`push-back`/`question` reply with no mutation; `stop` cancels the run named in the most recent bot-posted `IntentAnnouncement`, plus any in-progress `implement-workflow` run on the same branch. Once every leg of `act` has finished (`if: always()`), `dispatch-once` checks the branch tip against the pre-fold `base-sha`: unchanged means nothing folded and it no-ops; changed means it issues **at most one** `gh workflow run` for the consumer's `implement-workflow` (empty = no dispatch), joining the same concurrency group `act` used only after `act` has released it — never contending with it. Alongside it, `report-fold-outcomes` (also `if: always()`) cross-references this run's own job conclusions against git-history fold evidence to post one PR comment naming any fold-route item that died without folding cleanly ("not folded" vs. "partly folded"), posting nothing when every item folded cleanly. Every out-of-PR artifact is cross-linked from the lifecycle issue as one `OutstandingTaskItem` line |
| Outputs | none (side effects only) — `qualifies`/`spec-dir`/`slug`/`base-sha`/`concurrency-group` exist as *job*-level outputs of `classify-and-announce` for `act`/`dispatch-once`/`report-fold-outcomes`'s own use, and are deliberately not re-exported as `workflow_call` outputs a caller could read |

## Per-stage default tool lists

The `--allowedTools`/`--disallowedTools` values each agent-running stage ships
today, and against which the `extra-*`/`*-override` common inputs above compose
(specs/026-configurable-tool-lists, FR-013/SC-006). A consumer who sets none of
those four inputs gets exactly these lists (SC-005). Multi-step stages
(`plan`, `tasks`, `implement`) list one row per internal agent step; the
`step-label` is what a conflict/validation error names. `watchdog` runs a
single agent step (`watchdog.diagnose`) since spec 024 made it a pure
reporter.

Every list additionally carries `ScheduleWakeup`, `Monitor`, `SendMessage` in
its disallowed set — interactive-resume tools a one-shot Action can never
service, stripped regardless of consumer configuration (they stay functionally
inert even if an `extra-allowed-tools`/override re-adds them) — **except**
`watchdog.diagnose`, whose shipped disallowed literal omits those three (it is
already read-only via its allowed list; see footnote).

| Stage | Internal step (`step-label`) | Default allowed | Default disallowed |
|---|---|---|---|
| intake | `intake` | `Skill,Read,Write,Edit,Glob,Grep,Bash(git status:*),Bash(git add:*),Bash(git commit:*),Bash(git checkout:*),Bash(git switch:*),Bash(git push:*),Bash(git branch:*),Bash(git log:*),Bash(git diff:*),Bash(git show:*),Bash(git ls-tree:*),Bash(echo:*),Bash(ls:*),Bash(mkdir:*),Bash(cat:*),Bash(gh issue view:*),Bash(gh issue edit:*),Bash(gh issue comment:*),Bash(gh pr create:*),Bash(gh label create:*)` | `WebFetch,ScheduleWakeup,Monitor,SendMessage` |
| clarify | `clarify` | `Read,Edit,Write,Glob,Grep,Bash(git status:*),Bash(git add:*),Bash(git commit:*),Bash(git push:*),Bash(git log:*),Bash(git diff:*),Bash(cat:*),Bash(gh issue view:*),Bash(gh issue comment:*),Bash(gh pr list:*),Bash(gh pr view:*),Bash(gh pr edit:*)` | `WebSearch,WebFetch,ScheduleWakeup,Monitor,SendMessage` |
| plan | `plan.direct-commit` | `Skill,Read,Write,Edit,Glob,Grep,Bash(git status:*),Bash(git add:*),Bash(git commit:*),Bash(git push:*),Bash(git log:*),Bash(git diff:*),Bash(git show:*),Bash(git ls-tree:*),Bash(git branch:*),Bash(echo:*),Bash(ls:*),Bash(mkdir:*),Bash(cat:*),Bash(.specify/scripts/bash/setup-plan.sh:*),Bash(bash .specify/scripts/bash/setup-plan.sh:*),Bash(.specify/scripts/bash/check-prerequisites.sh:*),Bash(bash .specify/scripts/bash/check-prerequisites.sh:*),Bash(.specify/scripts/bash/update-agent-context.sh:*),Bash(bash .specify/scripts/bash/update-agent-context.sh:*),Bash(gh issue view:*),Bash(gh issue comment:*)` | `WebFetch,ScheduleWakeup,Monitor,SendMessage` |
| plan | `plan.pr` | same as `plan.direct-commit` plus `Bash(git checkout:*),Bash(git switch:*),Bash(gh pr create:*),Bash(gh pr list:*)` | `WebFetch,ScheduleWakeup,Monitor,SendMessage` |
| tasks | `tasks.direct-commit` | `Skill,Read,Write,Edit,Glob,Grep,Bash(git status:*),Bash(git add:*),Bash(git commit:*),Bash(git push:*),Bash(git log:*),Bash(git diff:*),Bash(git show:*),Bash(git ls-tree:*),Bash(git branch:*),Bash(echo:*),Bash(ls:*),Bash(cat:*),Bash(.specify/scripts/bash/setup-tasks.sh:*),Bash(bash .specify/scripts/bash/setup-tasks.sh:*),Bash(.specify/scripts/bash/check-prerequisites.sh:*),Bash(bash .specify/scripts/bash/check-prerequisites.sh:*),Bash(gh issue view:*),Bash(gh issue comment:*)` | `WebSearch,WebFetch,ScheduleWakeup,Monitor,SendMessage` |
| tasks | `tasks.pr` | same as `tasks.direct-commit` plus `Bash(git checkout:*),Bash(git switch:*),Bash(gh pr create:*),Bash(gh pr list:*)` | `WebSearch,WebFetch,ScheduleWakeup,Monitor,SendMessage` |
| implement (⟲ converge) | `implement.cycle` | `Skill,Read,Write,Edit,Glob,Grep,Bash(git status:*),Bash(git add:*),Bash(git commit:*),Bash(git push:*),Bash(git log:*),Bash(git diff:*),Bash(git ls-tree:*),Bash(git branch:*),Bash(echo:*),Bash(git show:*),Bash(ls:*),Bash(cat:*),Bash(yamllint:*),Bash(actionlint:*),Bash(shellcheck:*),Bash(jq:*),Bash(mkdir:*),Bash(.specify/scripts/bash/check-prerequisites.sh:*),Bash(bash .specify/scripts/bash/check-prerequisites.sh:*),Bash(gh issue view:*),Bash(gh issue comment:*),Bash(git rm:*)` | `WebSearch,WebFetch,ScheduleWakeup,Monitor,SendMessage` |
| implement (⟲ converge) | `implement.retry` | same as `implement.cycle` plus `Bash(git pull:*),Bash(git fetch:*),Bash(git reset:*)` | `WebSearch,WebFetch,ScheduleWakeup,Monitor,SendMessage` |
| implement (⟲ converge) | `implement.post-progress-comment` | `Bash(git log:*),Bash(git diff:*),Bash(git show:*),Bash(gh issue comment:*)` | `WebSearch,WebFetch,ScheduleWakeup,Monitor,SendMessage` |
| finalize | `finalize` | `Read,Glob,Grep,Bash(git log:*),Bash(git diff:*),Bash(git show:*),Write` | `WebSearch,WebFetch,ScheduleWakeup,Monitor,SendMessage` |
| cleanup | `cleanup` | `Read,Glob,Grep,Bash(git log:*),Bash(git diff:*),Bash(git show:*),Write` | `WebSearch,WebFetch,ScheduleWakeup,Monitor,SendMessage` |
| rebase | `rebase` | `Read,Edit,Grep,Glob,Bash(git status:*),Bash(git diff:*),Bash(git add:*),Bash(git rebase --continue:*),Bash(git rebase --abort:*)` | `WebSearch,WebFetch,ScheduleWakeup,Monitor,SendMessage` |
| watchdog | `watchdog.diagnose` | `Read,Grep,Bash(gh:*),Bash(git log:*),Bash(git diff:*)` (deliberately read-only) | `WebSearch,WebFetch,Write,Edit,Bash(git commit:*),Bash(git push:*)` † |
| pr-conversation | `pr-conversation.classify` | `Read,Grep,Glob,Bash(git log:*),Bash(git diff:*),Bash(git show:*),Bash(cat:*),Bash(gh pr view:*),Bash(gh issue view:*),Bash(gh search issues:*)` (deliberately read-only) | `Write,Edit,WebSearch,WebFetch,Bash(git push:*),Bash(git commit:*),ScheduleWakeup,Monitor,SendMessage` |
| pr-conversation | `pr-conversation.act` | `Read,Write,Edit,Glob,Grep,Bash(git status:*),Bash(git add:*),Bash(git commit:*),Bash(git push:*),Bash(git log:*),Bash(git diff:*),Bash(git checkout:*),Bash(git switch:*),Bash(git branch:*),Bash(cat:*),Bash(gh issue view:*),Bash(gh issue comment:*),Bash(gh issue create:*),Bash(gh issue edit:*),Bash(gh pr view:*),Bash(gh pr comment:*),Bash(gh pr create:*),Bash(gh pr edit:*),Bash(gh api:*),Bash(gh label create:*),Bash(gh search issues:*),Bash(gh search prs:*)` | `WebSearch,WebFetch,ScheduleWakeup,Monitor,SendMessage` |

† `watchdog.diagnose`'s shipped disallowed literal omits `ScheduleWakeup,
Monitor,SendMessage` (unlike every other stage). This is the actual inline
value in `watchdog.yml` today; it is carried verbatim so a consumer who sets
none of the four tool-list inputs gets a byte-for-byte identical list (SC-005).

Sources: `.github/workflows/{intake,clarify,plan,tasks,implement,finalize,cleanup,rebase,watchdog,pr-conversation}.yml`
(`claude_args:` blocks, now composed via the `wing-commander-tool-args`
composite action). A future change that edits a stage's default list must
update this table in the same change — the composite action reads these as
literal call-site inputs, so drift here is a documentation bug, not a behavior
bug.
