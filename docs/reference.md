# Reference: what the pipeline does, its defaults and its limits

This page is the map: every loop this repository runs, what each one may do,
the default for each knob, and what this repository has set it to. It is
written to be looked things up in. Explanations live in one place each and
are not repeated here:

| For | Read |
|---|---|
| What a repository variable means | [setup.md §3](setup.md#3-repository-variables) |
| Every input of a published stage | [adoption.md, "Stage reference"](adoption.md#stage-reference) |
| How a stage works inside | [architecture.md](architecture.md) |
| The rules a session follows on the board | [CLAUDE.md](../CLAUDE.md) |
| Why a rule exists | [the constitution](../.specify/memory/constitution.md) |

**Two layers** (constitution VII), marked on every section below:

- **Published**: a `workflow_call` stage (`.github/workflows/<stage>.yml`)
  that any repository can pin. Its defaults are the stage's own input
  defaults.
- **This repository**: a wrapper (`wing-commander-*.yml`) or a workflow that
  exists only here. An adopter gets none of it by pinning a stage.

When this page and the code disagree, the code is right; fix the page. Nothing
checks it against the workflows yet (see [Keeping this current](#keeping-this-current)).

## At a glance

| Loop | What it does | Layer | Runs on | Uses an agent | Can merge |
|---|---|---|---|---|---|
| [Feature lifecycle](#feature-lifecycle) | issue → spec → plan → tasks → implement → final PR → cleanup | published stages, this repository's wrappers | events and dispatches | yes | no |
| [Spec PR review](#spec-pr-review) | reviews a settled draft spec PR, pushes small fixes, reports | this repository | hourly | yes | no |
| [Lifecycle review gate](#lifecycle-review-gate) | reviews a final PR, sends findings back for a fix cycle, may merge | this repository | hourly | yes | final PRs, behind a switch |
| [PR conversation](#pr-conversation) | acts on a maintainer's comment or review on a final PR | published stage, this repository's wrapper | PR comments and reviews | yes | no |
| [Board loop](#board-loop) | works one open issue: triage → route → fix → review → merge → prove | this repository | hourly | yes | its own fix PRs and verified Spec Kit bumps, behind a switch |
| [Watchdog](#watchdog) | inspects every finished stage run and files defects | published stage, this repository's wrapper | after each stage run | yes | no |
| [Auto-release](#releases-and-upgrades) | proves the unreleased head end to end, then tags a release | this repository | daily | no (it drives the stages, which do) | no (it tags) |
| [Spec Kit updater](#releases-and-upgrades) | detects, verifies and proposes a Spec Kit upgrade | published stage, this repository's wrapper | daily | yes | no (the board loop merges its PR) |
| [Housekeeping](#housekeeping-and-observability) | rebase, cleanup, metrics, board status, image checks | mixed | events and daily | rebase and cleanup | no |

## Feature lifecycle

*Published stages; the triggers are this repository's wrappers.*

| Stage | Starts when (wrapper) | Model default | Turn budget | Produces |
|---|---|---|---|---|
| intake | a maintainer applies `spec-request` to an issue | `claude-opus-5-5` | 50 | draft spec PR (`spec-draft/NNN-slug` → `main`), `spec:NNN-slug` and `stage:spec` labels, clarification questions on the issue |
| clarify | a maintainer or the requester comments on a lifecycle issue in `stage:spec` or `stage:clarify` | `claude-opus-5-5` | 65 | the answers folded into the draft spec PR |
| plan | the spec PR merges | `claude-sonnet-5-5` | 110 | the plan on `spec/NNN-slug`; a plan PR, or a direct commit (see `plan-review`) |
| tasks | the plan lands | `claude-sonnet-5-5` | 60 | `tasks.md`, then a dispatch of implement |
| implement | dispatched by tasks, by itself for the next cycle, or by a review fold | `claude-sonnet-5-5` | 180 | one implement ⟲ converge cycle; then the next cycle or a dispatch of finalize |
| finalize | dispatched by implement | `claude-haiku-5-5` | 20 | the final PR (`spec/NNN-slug` → `main`), `stage:review`, manual steps reported on the issue |
| cleanup | a lifecycle PR closes; also daily | `claude-haiku-5-5` | 20 | when the final PR merges: branches deleted, `stage:done`, issue closed. A draft spec PR closed unmerged: draft branch deleted, issue left open. Any other lifecycle PR closed unmerged: `stage:stalled`, branches kept |

Limits and rules:

| Rule | Default | Knob |
|---|---|---|
| Entry | only a maintainer's `spec-request` label starts intake | none (constitution V) |
| Plan review | `pr`: a plan PR waits for a human merge. `auto` commits the plan and goes on to tasks | `WING_COMMANDER_PLAN_REVIEW` |
| Tasks review | `auto`: `tasks.md` is committed. `pr` opens a tasks PR | `WING_COMMANDER_TASKS_REVIEW` |
| Implement cycles per lifecycle | 5, then a `stage:stalled` hand-off that names how to resume | `WING_COMMANDER_MAX_ITERATIONS` |
| A failed implement pass | retried once, one tier up (`claude-opus-5-5`); a second failure stalls the lifecycle | `WING_COMMANDER_IMPLEMENT_ESCALATION_MODEL` |
| Implement on Opus | off; the `model:opus` label on the lifecycle issue opts in | label, or `WING_COMMANDER_IMPLEMENT_MODEL` |
| Implement on Haiku | off; the `model:haiku` label opts in (retry goes to Sonnet, `model:opus` wins) | label, `WING_COMMANDER_IMPLEMENT_HAIKU_MAX_TURNS` (180) |
| Hard turn stop | every agent step's `--max-turns` is 2.5 × its turn budget, rounded up | fixed (`wing-commander-turn-ceiling`) |
| Paths the implement agent may not write | `.claude/`, `.git/` | `WING_COMMANDER_IMPLEMENT_NO_WRITE_PATHS` |
| Defects a stage files while working | implement and finalize file them, intake, clarify, plan and tasks do not; at most 3 per run, labelled `found-by:<stage>` | `WING_COMMANDER_<STAGE>_FINDINGS_FILING_ENABLED`, `WING_COMMANDER_FINDINGS_CAP`, `WING_COMMANDER_FINDINGS_LABEL_PREFIX` |
| Concurrency | one spec's stages run one at a time; different specs run in parallel; intake runs one at a time | fixed |
| Lifecycles in implement at once | three, by convention only ([CLAUDE.md](../CLAUDE.md)); no code enforces it | none |
| Lifecycles in flight when a session promotes a proposal | fewer than three: open issues carrying `spec-request` or a `spec:` label (constitution X's promotion rule). The session counts them; no code enforces it | none |
| Runner and container | `ubuntu-latest`, no container | `WING_COMMANDER_RUNNER`, `WING_COMMANDER_CONTAINER_IMAGE` |
| Project in a subfolder | off; a maintainer routes a lifecycle to a project folder | [adoption.md](adoption.md#multiple-projects-in-one-repository) |

What still needs a person in a lifecycle: an answer to any clarification
question no earlier decision settles, the plan PR merge when `plan-review` is
`pr`, and the final PR merge unless [lifecycle auto-merge](#merge-classes) is
on. Applying `spec-request` and merging the spec PR are the owner's too,
unless a session does them under the two rules in
[What a session may do without being asked](#what-a-session-may-do-without-being-asked).

### Spec PR review

*This repository only: `spec-pr-review.yml`, hourly at :41 UTC, or dispatched with a PR number.*

| Rule | Value |
|---|---|
| Reviews | an open draft spec PR (`spec-draft/*`) that is settled: `stage:spec` and not `stage:clarify`, no open clarification marker, and the head is no newer than the bot's "ready" announcement. A dispatch by a human maintainer skips the announcement check |
| Reviewer | `claude-opus-5-5`, effort `high`, turn budget 30 (`WING_COMMANDER_SPEC_REVIEW_MODEL`, `WING_COMMANDER_SPEC_REVIEW_EFFORT`) |
| Rounds | 5 per spec PR; 2 failed attempts per head, then it stops |
| May push | fixes and clarification markers inside the spec's own directory, at most 200 changed lines per push |
| Never | approves, requests changes or merges. It posts one comment review and the `spec-pr-review` commit status, which is `success` only for "ready for the owner" |
| Kill switch | `WING_COMMANDER_SPEC_REVIEW_PAUSED` |

[CLAUDE.md](../CLAUDE.md) separately tells sessions to give a spec PR at most
three review rounds before the owner decides. That is a rule for sessions; the
5 above is this workflow's own budget.

### Lifecycle review gate

*This repository only: `lifecycle-review-gate.yml`, hourly at :27 UTC.*

| Rule | Value |
|---|---|
| Reviews | one open final PR per run, oldest first: `spec/NNN-slug` → `main`, stage `review`, no buildable task left unchecked, head not yet reviewed |
| Reviewer | `claude-sonnet-5-5`, turn budget 30 (`WING_COMMANDER_LIFECYCLE_REVIEW_GATE_MODEL`) |
| Findings | in-scope findings are folded into `tasks.md` and built by one more implement cycle; the next round reviews the new head |
| Rounds | 5. A round that fails to parse does not count |
| Stops early | from round 3, as `not-converging`, when the count of findings is not falling, half or more are in code an earlier round wrote, a folded finding comes back, the diff churns two rounds running, or the diff grew by more than half. The PR is handed to a human |
| Merges | only when `WING_COMMANDER_LIFECYCLE_AUTO_MERGE` is `true` (default off), and only when all eight conditions hold on the exact head: checks green, gate suite green, mergeable, reviewed at this head, kill switch clear, round clean, no open findings, no unresolved human changes-requested review |
| Kill switch | `WING_COMMANDER_LIFECYCLE_REVIEW_GATE_PAUSED` stops the review and the merge |

The constitution names a ninth condition, no hold label on the lifecycle
issue. It arrives with spec 119 and is not in the code on `main` yet.

### PR conversation

*Published stage `pr-conversation.yml`; this repository's wrapper listens to reviews, review comments and comments on pull requests.*

A maintainer's comment or review on a final PR is classified and acted on:
review findings become tasks and one more implement cycle builds them. Bots
get no run, and a non-maintainer gets a reply naming who can ask. Model
`claude-sonnet-5-5` with a turn budget of 40 (`WING_COMMANDER_PR_CONVERSATION_MODEL`;
a `model:opus` label escalates). To make it propose and wait for approval
before it acts, set `WING_COMMANDER_PR_CONVERSATION_CONFIRM_CATEGORIES`.

A comment on a lifecycle *issue* is not handled here: it starts clarify.

## Board loop

*This repository only: `board-loop.yml`, hourly at :13 UTC. One item at a time; it stands down while an implement cycle is running.*

| Step | What it does | Limit |
|---|---|---|
| select | picks an in-flight item first, else the oldest eligible open issue | one item per run |
| triage | checks the issue against current `main`; closes it only on evidence the code read itself (a failed cited run that ended on a rate-limit rejection or an API 429, in one turn at zero cost; or an upstream action bump) | turn budget 15 |
| route | decides fix-shaped or spec-shaped. Spec-shaped work is filed as a `spec-proposal` and never fixed | turn budget 25 |
| fix | writes the fix on `fix/<issue>-<slug>` and opens a PR labelled `board:owned` | turn budget 60; 6 files and 120 changed lines |
| review | a second agent with no shared context reviews; in-scope findings are fixed in the same PR | 5 rounds; the same `not-converging` rule as the review gate |
| merge | squash-merges at the exact reviewed head | only when the merge switch is on |
| prove | re-drives one run that reaches the change and records the evidence; skipped for a change to docs, specs or a gate script only | one dispatch |

| Rule | Value |
|---|---|
| Eligible issue | authored by a maintainer, labelled by a maintainer, or filed by the pipeline under its own labels (`pipeline-defect`, `auto-update:*`, `found-by:*`) |
| Never selected | `board:stalled`, any `disposition:*` label (a reopened `disposition:duplicate` issue is re-admitted once the `spec-request` it duplicated has closed), any `stage:*` or `spec:*` label, `spec-proposal`, `spec-request`, and the two issues their own workflows manage, `auto-update:tracking` and `auto-release:failed` |
| Spec-shaped, whatever its size | a change to a published stage's inputs or a composite's inputs and outputs |
| Workflow files | a fix that edits `.github/workflows/` is held under `board:stalled` unless `WING_COMMANDER_BOARD_CAN_PUSH_WORKFLOWS` is `true` (default off), which also needs the App's Workflows permission |
| Stalled | `board:stalled` after the round budget is spent, a review that stops converging, a backstop breach, a fix it cannot push, or three not-ready outcomes on one PR. Only a human removing the label re-admits the issue |
| Model | `claude-sonnet-5-5` (`WING_COMMANDER_BOARD_LOOP_MODEL`); a `model:opus` label on the issue opts in to Opus |
| Fix PR merge needs | switch on, kill switch clear, a complete snapshot of the head, an eligible fix PR (the App's own, `fix/<number>-…` → `main`, not touching the constitution), checks green, gate suite green, review converged, backstop holds |
| Spec Kit bump merge needs | switch on, kill switch clear, a complete snapshot, the updater's own PR, checks green, gate suite green, verification passed at that head. No size limit |
| Merge switch | `WING_COMMANDER_BOARD_AUTO_MERGE`, default off. Off, the loop still fixes, reviews and reports, and a human merges |
| Maintenance backlog lines | off. With `WING_COMMANDER_BOARD_BACKLOG_LINES` set to `true`, the loop takes one unchecked line from the "Maintenance backlog" issue when no issue is eligible |
| Kill switch | `WING_COMMANDER_BOARD_LOOP_PAUSED` |

## Watchdog

*Published stage `watchdog.yml`; this repository's wrapper runs it after every run of stages 1–7 and rebase, and on dispatch to re-inspect a run.*

| Rule | Value |
|---|---|
| Does | collects signals from the finished run, diagnoses them, and files, comments on or reopens one `pipeline-defect` issue per finding, titled `watchdog: <class>` and labelled `🐕 · <class>`. It reports every finding on the lifecycle issue |
| Never | proposes a diff, opens a PR or fixes anything. The board loop picks its issues up |
| Diagnose model | `claude-opus-5-5`, turn budget 30 (`WING_COMMANDER_DIAGNOSE_MODEL`) |
| Reported but not filed | `denied-tool` and `narrative-drift` |
| Usage window exhausted | one `usage-limit` issue instead of a finding per stalled run |
| Turn-budget trend | flags a stage whose runs keep reaching their turn budget. It looks at the stage's last 10 runs and raises a trend finding: `watch` at 3 runs in a row at or over budget, `elevated` when any run in that window used 0.6 or more of the hard stop, `critical` when both hold (`WING_COMMANDER_TURN_BUDGET_*`) |
| Watching itself | `wing-commander-8b-watchdog-self.yml` checks each watchdog run with no agent; a chain of the watchdog inspecting itself stops writing after 3 (`WING_COMMANDER_WATCHDOG_SELF_DISPATCH_CAP`) |
| Haiku shadow trial | off. Setting `WING_COMMANDER_DIAGNOSE_SHADOW_SINCE` runs `claude-haiku-5-5` beside diagnose (turn budget 8) for 60 days or 300 compared runs. It is recorded and acts on nothing |
| Kill switch | `WING_COMMANDER_WATCHDOG_PAUSED` |

## Releases and upgrades

*This repository only, except the Spec Kit updater stage.*

| Workflow | Runs | Does | Limits and switches |
|---|---|---|---|
| `auto-release.yml` | daily, 09:09 UTC | if `main` has moved past the last `vX.Y.Z` tag, or that day's mode has an earlier failure to clear, scaffolds the test repository with the stages at that commit and drives one trivial feature through the whole lifecycle with no human; a pass with unreleased work tags a release | 150-minute cap. Alternates by day between the default runner and the container image. Patch by default; minor when a merged PR carries `release:minor`; never major. Kill switches `WING_COMMANDER_AUTO_RELEASE_PAUSED` (set through `auto-release-switch.yml`) and `WING_COMMANDER_AUTO_RELEASE_E2E_CONTAINER_PAUSED`. A failure opens an `auto-release:failed` issue |
| `release.yml` | dispatched by auto-release, or by hand | lints the published stages, creates the exact tag and the GitHub Release, and moves the floating major tag forward | a breaking release must start a new major |
| Spec Kit updater | daily, 07:13 UTC | re-checks the pinned version, detects a newer upstream release, waits for it to settle, verifies it (minor and major candidates also run in a scratch repository) and opens a bump PR, or a revert PR when the pinned version stops passing | settle window 1 daily check. Models `claude-sonnet-5-5`. Kill switch `WING_COMMANDER_AUTO_UPDATE_SPEC_KIT_PAUSED`. The board loop merges the PR when its merge switch is on; otherwise a human does |
| `wing-commander-e2e-reference-image.yml` | when the image's files change on `main` | rebuilds the reference container image, checks the agent starts in it, then moves the `WING_COMMANDER_CONTAINER_IMAGE` pin | needs `WING_COMMANDER_REFERENCE_IMAGE_SYNC_TOKEN` |
| Private-image dogfood | daily, 08:37 UTC | proves a stage can pull a private image with the registry secrets | skipped while `WING_COMMANDER_PRIVATE_IMAGE_DOGFOOD_IMAGE` is unset |

## Housekeeping and observability

| Workflow | Layer | Runs | Does |
|---|---|---|---|
| rebase | published stage, wrapper | every push to `main` by a non-bot actor; nightly, 04:17 UTC | brings each open spec branch up to date with `main` (`rebase`, or `merge` with `WING_COMMANDER_SPEC_BRANCH_SYNC`); an agent resolves conflicts (`claude-sonnet-5-5`, turn budget 50); one it cannot resolve is left untouched and reported on the lifecycle issue |
| cleanup | published stage, wrapper | a lifecycle PR closes; daily, 06:53 UTC | see the lifecycle table |
| metrics-persist | published stage, wrapper | after each stage run; a daily sweep at 06:37 UTC | appends one record per agent run (turns, tokens and cost, where the run reports them) to `records.jsonl` on the `metrics` branch (`WING_COMMANDER_METRICS_BRANCH`, `_PATH`, `_PAUSED`) |
| `board-status.yml` | this repository | daily, 07:17 UTC | rewrites the "Board status" issue: what waits on the owner, what is in the pipeline, the backlog's size, `main`'s CI, the last release and the merge switches. No agent. `WING_COMMANDER_BOARD_STATUS_PAUSED` stops it |
| fold-cycle-guard | published stage, wrapper | after an implement run | re-dispatches, once, an implement run that was cancelled while still queued |
| `lint-workflows.yml` | this repository | every pull request that touches workflows, actions, scripts, docs or a root Markdown file; pushes to `main` that touch workflows; daily | the gate suite. `python .github/scripts/run-local-gates.py` runs the same set locally |
| agent-startup-check | published stage | called by the image workflows | checks that the agent action can start inside a container image |

Dispatch-only helpers in this repository: `wing-commander-trial-summary.yml`
(summarises the shadow trial), `wing-commander-watchdog-test.yml` (injects a
failure for the watchdog to find), `migrate-stranded-review-lifecycles.yml`,
`auto-update-spec-kit-scratch-preflight.yml` (readiness check for a test
repository) and `auto-release-switch.yml`.

## Merge classes

Who may merge what. The bot is the pipeline's GitHub App.

| Pull request | Default | The bot merges it when | Reverted by |
|---|---|---|---|
| Spec PR | a human, or a session under the spec-merge rule below | never | one revert of the squash commit |
| Plan PR (only with `plan-review: pr`) | a human | never | — |
| Final PR of a lifecycle | a human | `WING_COMMANDER_LIFECYCLE_AUTO_MERGE` is `true` and the [review gate's](#lifecycle-review-gate) conditions hold | one revert of the squash commit |
| Board loop fix PR | a human | `WING_COMMANDER_BOARD_AUTO_MERGE` is `true` and the [board loop's](#board-loop) conditions hold | one revert of the squash commit |
| Spec Kit bump PR | a human | the same switch, after its verification passed | one revert of the squash commit |
| Constitution amendment | a human | never | — |
| A fix PR one of the owner's sessions opened | that session, on the evidence rule below | never | one revert of the squash commit |
| Any other PR (a contributor's) | a human | never | — |

A merge GitHub refuses, for example a workflow-file change without the
Workflows permission, goes to a maintainer. Nothing is pushed to `main`
another way.

"A human" includes a Claude Code session acting on the owner's instruction
for that pull request, under the owner's GitHub account; see the
[README](../README.md#how-this-repository-is-operated).

### What a session may do without being asked

Three acts, each only when every condition holds at the moment it acts. The
session first posts what it read in a comment starting
`**Session decision**`.

| Act | Conditions | The rule |
|---|---|---|
| Merge a spec PR | checks green on the exact head; two clean independent review passes in a row, each posted on the PR with the head it reviewed, the later one at that head; no more than three passes; no clarification question open; no unresolved changes-requested review; the lifecycle issue not held; the merging session neither wrote nor reviewed the spec | constitution X, the spec-merge rule |
| Apply `spec-request` to a `spec-proposal` | a maintainer or the App filed it; fewer than three lifecycles in flight; no contract break, moved security boundary, new credential, permission, repository setting or model tier; the owner has not parked, held or declined it | constitution X, the promotion rule |
| Merge a fix PR one of the owner's sessions opened | every check run on the exact head completed successfully; the latest `review-until-clean` pass reviewed that head and is CLEAN; the merging session did not review it | [CLAUDE.md](../CLAUDE.md), "Merging on evidence" |

The owner's word stops any of the three: an instruction in the session, a
changes-requested review, the hold label, or a line under "Owner decisions"
on the Roadmap issue.

Always the owner's: a constitution amendment, a plan PR merge, a final PR
merge while the lifecycle switch is off, an answer to a clarification question
no earlier decision settles, model tier and spend, credentials, App
permissions and repository variables, and any spec PR merge or promotion that
does not meet the rules above.

## Kill switches

Each is a repository variable; only the exact value `true` pauses, and unset
means running. A pause takes effect no later than the next run.

| Switch | Stops |
|---|---|
| `WING_COMMANDER_BOARD_LOOP_PAUSED` | the board loop, including its merges |
| `WING_COMMANDER_LIFECYCLE_REVIEW_GATE_PAUSED` | the lifecycle review gate's reviews and merges |
| `WING_COMMANDER_SPEC_REVIEW_PAUSED` | spec PR review |
| `WING_COMMANDER_WATCHDOG_PAUSED` | the watchdog and its self-check |
| `WING_COMMANDER_AUTO_RELEASE_PAUSED` | auto-release (set it by dispatching `auto-release-switch.yml`) |
| `WING_COMMANDER_AUTO_RELEASE_E2E_CONTAINER_PAUSED` | only auto-release's container runs |
| `WING_COMMANDER_AUTO_UPDATE_SPEC_KIT_PAUSED` | the Spec Kit updater |
| `WING_COMMANDER_BOARD_STATUS_PAUSED` | the daily Board status rewrite |
| `WING_COMMANDER_METRICS_PAUSED` | metrics records |

The feature lifecycle has no pause variable. To stop one lifecycle, close its
issue or its PR; to stop new ones, do not apply `spec-request`, and pause
promotion with a line under "Owner decisions" on the Roadmap issue, which a
session reads before it promotes a proposal or merges a spec PR.

## Schedules

All times UTC.

| When | Workflow |
|---|---|
| hourly at :13 | board loop |
| hourly at :27 | lifecycle review gate |
| hourly at :41 | spec PR review |
| 04:17 | rebase |
| 05:43 | the gate suite on `main` |
| 06:37 | metrics-persist sweep |
| 06:53 | cleanup |
| 07:13 | Spec Kit updater |
| 07:17 | board status |
| 08:37 | private-image dogfood |
| 09:09 | auto-release |

Pipeline agent runs and Claude Code sessions draw on one usage window when the
pipeline authenticates with a Claude subscription token.

## Labels

[setup.md §4](setup.md#4-labels) lists the labels to create and what each means.
The pipeline also creates these as it needs them:

| Label | Written by | Means |
|---|---|---|
| `spec:NNN-slug` | intake | ties an issue to its spec directory |
| `stage:stalled` | tasks, implement, finalize, cleanup | a stage could not finish; the comment beside it says how to resume |
| `pipeline-defect`, `🐕 · <class>` | watchdog | a finding and its class |
| `found-by:<stage>` | a stage's filing step | a defect a stage met during its own work |
| `route-out-of-boundary:<stage>` | implement, finalize | a task the stage may not write, routed to a maintainer |
| `auto-update:tracking`, `auto-update:failed` | Spec Kit updater | its tracking issue; a failed upgrade |
| `auto-release:failed` | auto-release | a release attempt that did not pass |
| `usage-limit` | watchdog | the shared usage window ran out |
| `rebase:blocked` | rebase | a spec branch it could not bring up to date |

Applied by a maintainer or a session: `spec-request`, `model:opus`,
`model:haiku`, `release:minor`, `disposition:confirmed`,
`disposition:false-positive`, `disposition:tracking` (the three tracking
issues; the board loop never selects them) and `parked` (a closed lifecycle
that waits on the owner).

## This repository's settings

*This repository's instance, as read on 2026-11-10. A snapshot: check a live
value with `gh variable list`, or read the merge switches in the daily "Board
status" issue. Any variable not listed is unset and takes its default.*

| Variable | Default | Here |
|---|---|---|
| `WING_COMMANDER_PLAN_REVIEW` | `pr` | `auto`: no plan PR; the plan is committed and tasks follows |
| `WING_COMMANDER_TASKS_REVIEW` | `auto` | `auto` |
| `WING_COMMANDER_MAX_ITERATIONS` | 5 | 5 |
| `WING_COMMANDER_BOARD_AUTO_MERGE` | off | `true`: the board loop merges its fix PRs and verified Spec Kit bumps |
| `WING_COMMANDER_BOARD_CAN_PUSH_WORKFLOWS` | off | `true`: the board loop may fix workflow files |
| `WING_COMMANDER_BOARD_BACKLOG_LINES` | off | off |
| `WING_COMMANDER_LIFECYCLE_AUTO_MERGE` | off | off: a human merges every final PR |
| `WING_COMMANDER_SPEC_REVIEW_PAUSED` | not paused | `true`: spec PR review is paused |
| `WING_COMMANDER_WATCHDOG_PAUSED` | not paused | `false` |
| `WING_COMMANDER_DIAGNOSE_SHADOW_SINCE` | unset | `2026-10-22`: the Haiku shadow trial is running |
| `WING_COMMANDER_CONTAINER_IMAGE` | no container | set to a digest of the reference image, so every stage job runs in the container |
| `WING_COMMANDER_PRIVATE_IMAGE_DOGFOOD_IMAGE` | unset | set |
| `WING_COMMANDER_AUTO_RELEASE_E2E_REPO` | unset | set, so auto-release runs |
| `WING_COMMANDER_AUTO_UPDATE_SPEC_KIT_E2E_SCRATCH_REPO` | unset | set, so minor and major Spec Kit upgrades can be verified |

Every model variable is unset, so each stage runs on the default in the
tables above. No kill switch is set except spec PR review's.

## Known limits

- The board loop, the review gates, the watchdog's self-check, board status
  and auto-release exist only in this repository. An adopter that pins the
  stages gets the feature lifecycle, rebase, PR conversation, the watchdog and
  the Spec Kit updater, and writes its own wrappers for each.
- The lifecycle review gate can stop `not-converging` on a pull request a
  fresh reviewer would pass, and the PR then waits for a human (#1110).
- An implement cycle builds what fits in one agent run. A lifecycle whose
  remaining tasks all edit one very large file can make little progress per
  cycle and reach the iteration cap.
- A session in a sandbox whose token cannot read Actions variables cannot see
  the settings above. The "Board status" issue shows the merge switches only.
- Nothing enforces the three-lifecycle limit in implement.
- No code checks the conditions under which a session merges a spec PR,
  promotes a proposal or merges its own fix PR. The session's
  `**Session decision**` comment is the record that makes each act checkable
  afterwards.

## Keeping this current

Nothing checks this page yet. Until a gate does (#1093), a change that adds,
removes or renames one of these updates this page in the same pull request:

- a workflow, or a workflow's schedule or trigger;
- a repository variable a workflow reads (the meaning goes in
  [setup.md §3](setup.md#3-repository-variables), the default and this
  repository's value here);
- a default model, turn budget, round budget or size limit;
- a label the pipeline writes or reads;
- a merge condition or a kill switch.
