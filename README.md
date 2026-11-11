# Wing Commander

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

**Spec-Driven Development as a GitHub-native pipeline.** Open an issue describing
what you want; the pipeline turns it into a reviewed specification, a plan,
tasks, an implementation and a pull request. It is built so that no single
agent owns a change end to end: one writes, a different one with no shared
context reviews, deterministic checks decide what may merge, and a run after
the merge proves it. It is built on [GitHub spec-kit](https://github.com/github/spec-kit) and
[Claude Code](https://github.com/anthropics/claude-code-action), and all of it
runs in GitHub Actions.

This repository **dogfoods itself**: the pipeline is built through the
pipeline. The first spec ever produced here is the spec for the intake stage —
see [`specs/001-spec-intake/`](specs/001-spec-intake/spec.md).

| If you want to | Read |
|---|---|
| Understand what happens to an issue | [How it works](#how-it-works) |
| Know who does what here, and how to drive it from a Claude Code session | [How this repository is operated](#how-this-repository-is-operated) |
| Look up a loop, a default, a limit or a switch | [docs/reference.md](docs/reference.md) |
| Use the pipeline in your own repository | [Using this on your own project](#using-this-on-your-own-project) |
| Work on this repository | [CLAUDE.md](CLAUDE.md) (the board rules), [CONTRIBUTING.md](CONTRIBUTING.md) |

## How it works

```
you: open an issue describing a feature
maintainer: applies the `spec-request` label                  ← human gate ¶
  🤖 intake     /speckit-specify → draft spec PR to main
  🤖 clarify    questions posted on your issue — just reply   ← your answers
  🤖 review †   an independent reviewer checks the settled spec
maintainer: reviews & merges the spec PR                      ← human gate ¶
  🤖 plan       /speckit-plan → plan PR on the spec branch
maintainer: reviews & merges the plan PR                      ← human gate §
  🤖 tasks      /speckit-tasks → tasks.md
  🤖 implement  /speckit-implement ⟲ /speckit-converge until done (capped)
  🤖 finalize   final PR to main + any remaining manual steps on your issue
  🤖 review †   an independent reviewer; its findings go back for a fix cycle
maintainer: reviews & merges the final PR                     ← human gate ‡
  🤖 cleanup    branches deleted, labels flipped, issue closed

† runs only in this repository, not part of the published stages
‡ the review gate can merge it instead, when that switch is on
§ skipped when `WING_COMMANDER_PLAN_REVIEW` is `auto`, as it is in this repository
¶ in this repository one of the owner's sessions may do this, under the
  constitution's promotion and spec-merge rules
```

Your issue is the feature's **lifecycle issue**: every stage reports its status
there, and its labels (`spec:NNN-slug`, `stage:*`) always show where things
stand. To change course, use ordinary GitHub actions: comment to answer or
clarify, review the pull request to reshape it, close to cancel.

Beside the lifecycle, this repository runs loops that keep it healthy without
anyone asking:

| Loop | What it does |
|---|---|
| Board loop | Hourly, takes one small open issue from triage to a reviewed fix PR, merges it when its switch is on, and proves the fix with a run. Anything that needs a design decision it files as a `spec-proposal` instead of fixing. |
| Watchdog | After every stage run, looks for a stage that lost work, drifted or ran out of budget, and files what it finds. It never fixes anything; the board loop picks its issues up. |
| Review gates | Independent reviewers for settled spec PRs and for final PRs. |
| Auto-release | Daily, drives a trivial feature through the whole lifecycle in a test repository at the unreleased commit, and tags a release when it passes. |
| Spec Kit updater | Daily, detects a new Spec Kit release, verifies it and opens the upgrade PR. |
| Board status | Daily, rewrites one issue with what waits on the owner, what the pipeline is doing, and the state of `main`. |

[docs/reference.md](docs/reference.md) has each loop's schedule, limits and
switches. [docs/architecture.md](docs/architecture.md) has the design, stage
by stage.

## How this repository is operated

Three parties work this repository. Knowing which one acts is most of
understanding it.

- **The owner** sets direction: chooses which proposals become specs, answers
  the questions no earlier decision settles, and owns credentials, settings
  and spend.
- **A Claude Code session** is how the owner works. The owner talks to a
  session, on a desktop, a phone or in the cloud, and rarely to GitHub
  directly. The session reads the board, drives the pipeline through issues,
  labels, comments and dispatches, reviews and fixes pull requests, and
  reports back. It acts under the owner's GitHub account, so what it posts
  carries the owner's authority: its comment on a lifecycle issue starts
  clarify exactly as the owner's would. Its rules are in
  [CLAUDE.md](CLAUDE.md); its procedures are the skills in
  [`.claude/skills/`](.claude/skills/).
- **The pipeline** is the workflows, acting as a GitHub App
  (`wing-commander-bot`). It does the stage work, works its own board, and
  merges only the classes of pull request the
  [constitution](.specify/memory/constitution.md) names.

GitHub is the record. A decision made in a chat is written down on the issue
or pull request it governs, so the next session finds it.

### Where to look

| For | Look at |
|---|---|
| What waits on the owner, what is moving, `main`'s CI, the last release, the merge switches | the open issue titled "Board status", rewritten daily |
| Which specs are in flight, queued, proposed or parked; goals; owner decisions | the open issue titled "Roadmap" |
| Small defects waiting for a fix | the open issue titled "Maintenance backlog", one checklist line each |
| One feature's whole history | its lifecycle issue |
| What a run cost in turns and tokens | `records.jsonl` on the `metrics` branch |

The three titled issues carry the `disposition:tracking` label. The board
loop never selects them.

### Asking a session

A session needs no special commands. These requests map onto the repository's
own procedures:

| Say | The session | Procedure |
|---|---|---|
| "What's on me?" | reports what waits on the owner, what is moving without them, and what needs nothing | `whats-on-me` skill |
| "Review and merge #N" | runs fresh review passes until one comes back clean, fixes each finding with a test that fails without it, and merges when CI is green on that exact commit | `review-until-clean` skill |
| "Answer them if there's a precedent" | answers each open question an earlier decision already settles, citing it, and brings back only the rest, with options and a recommendation | `answer-from-precedent` skill |
| "Prove it" | after a fix to behaviour that only runs in Actions, re-drives one run that reaches the change and records the evidence | `prove-after-merge` skill |
| "File it" | adds a small defect as a line on the Maintenance backlog, or files work that needs a design decision as a `spec-proposal` | [CLAUDE.md](CLAUDE.md), "Working the issue board" |

A session does not wait to be asked for everything. The owner guides this
repository and does not gate it: a session decides what is reversible and
already settled, records the decision where the owner can read it later, and
asks only on new ground. The rules are in [CLAUDE.md](CLAUDE.md), "Deciding
without the owner".

### Who decides what

| Decision | Who |
|---|---|
| A reversible choice between options, inside the constitution and the published contract | a session: it decides and records, or builds the options and compares them |
| The owner's by kind: a contract break, a security boundary, a constitution amendment, spend or model tier, a new credential or setting, deleted history, reversing an owner decision, the rules agents run under | the owner |
| Which proposals become specs (`spec-request`) | the owner; or a session, for a proposal the Roadmap lists, that it did not file itself and that asks the owner nothing, while fewer than three lifecycles are in flight |
| Answers to clarification questions | the owner; a session answers the ones an earlier decision settles |
| Merging a spec PR | the owner; or a session that took no part in that spec, once the automatic spec review reports the exact commit ready and a fresh session's review of that commit is clean. Not while the automatic review is paused |
| Merging a plan PR or a constitution amendment | a human |
| Merging a final PR | a human, or the lifecycle review gate when its switch is on |
| Merging a board loop fix PR or a verified Spec Kit upgrade | the board loop when its switch is on, otherwise a human |
| Merging a fix PR a session opened | a session, when checks are green on the exact commit and a fresh review pass at that commit is clean. Never one that touches the rules agents run under, an agent's tools or prompt, what decides a merge, a review or a fix's shape, a removed, disabled or loosened gate, a credential or the published contract: those wait for the owner |
| Whether a change is a direct fix or needs a spec | its shape. For the board loop: small, checkable and free of design trade-offs is a fix, and anything else is filed as a proposal. For a session, a reversible design choice inside a fix does not make it a spec |
| Settings and switches (every repository variable), credentials, App permissions, model tier | the owner |

"A human" here is usually a session acting on the owner's explicit
instruction for that pull request. Where a session may act without that
instruction, the constitution's Principle X states the conditions, and the
session posts what it read in a `**Session decision**` comment before it
acts. A line starting `- [ ] STOP:` under "Owner decisions" on the Roadmap
issue stops a session until the owner ticks or removes it. The exact conditions behind each bot merge, and what this repository
has switched on, are in
[docs/reference.md](docs/reference.md#merge-classes).

### What a session cannot do

- Read or change repository variables and secrets when its token lacks that
  scope, which a cloud sandbox's token usually does. The session hands the
  owner the command to run.
- Grant the App a permission or create a credential. Those are the owner's
  acts.
- Change a repository variable or setting. Those are the owner's, whatever
  the session's token can do.
- Push to `main` around a refused merge. A merge GitHub refuses goes back to
  the owner.

## Vocabulary

| Term | Meaning |
|---|---|
| Lifecycle | one feature's trip from issue to merged code |
| Lifecycle issue | the issue that started it; every stage reports there |
| Stage | one step of a lifecycle, published as a reusable workflow (`intake.yml` … `cleanup.yml`) |
| Wrapper | this repository's thin `wing-commander-*.yml` workflow that owns a stage's trigger and its checks |
| Spec PR, final PR | the draft spec (`spec-draft/NNN-slug` → `main`) and the implementation (`spec/NNN-slug` → `main`) |
| Cycle | one implement ⟲ converge run; a lifecycle gets a capped number of them |
| Converged | no buildable task is left unchecked in `tasks.md` |
| Stalled | a stage or loop stopped and handed the item to a human: `stage:stalled` on a lifecycle, `board:stalled` on a board item |
| Round | one review of a pull request by a review loop |
| Fold | turning a review's findings into tasks that one more cycle builds |
| Fix-shaped, spec-shaped | small, checkable and free of design trade-offs, so it is fixed directly; or anything else, which becomes a proposal |
| Spec proposal, spec request | `spec-proposal` marks work that would need a spec; `spec-request` starts one, applied by the owner or by a session under the promotion rule |
| Decision record | a comment starting `**Session decision**`: what a session chose without asking, the options, the evidence and how to undo it |
| Gate | a deterministic check in the lint suite (`verify-*.py`). A *human gate* is a point where the pipeline waits for a person; the *review gate* is the workflow that reviews final PRs |
| Prove | re-driving a run after a merge to show the fix took effect |
| Finding, signal | a finding is something the watchdog or a reviewer reports, filed as an issue or posted on the pull request; a signal is a watchdog class (`denied-tool`, `narrative-drift`) that is reported on the lifecycle issue and not filed |
| Kill switch | a `WING_COMMANDER_*_PAUSED` repository variable that stops one loop |
| Parked | a lifecycle closed with the `parked` label while it waits on the owner |

## Status

Every stage is published as a reusable `workflow_call` workflow (a bare
`<stage>.yml`) that any repository can pin; the matching
`wing-commander-*.yml` file is this repository's own thin wrapper around it
(triggers + gates only).

These are two distinct things, and the constitution governs them separately
(Principle VII — Two Interfaces). The **published contract** is the
`<stage>.yml` workflows plus the composite actions under `.github/actions/**`
that they resolve through self-checkout: adopters pin it by release tag, so
its input, secret, and output names are a compatibility surface and removing
or renaming one is a breaking change. The **consuming instrument** is the
`wing-commander-*.yml` wrappers together with this repository's `.specify/`,
`specs/`, labels, and repository variables — one adopter's configuration that
doubles as the worked example, pinned by nobody and free to change. Stage
workflows own no triggers and read no ambient repository state; wrappers own
the triggers, the gates, and the event→input extraction. The two columns
below are that split, row by row.

| Stage | Published stage | This repo's wrapper | State |
|---|---|---|---|
| 1 · Intake (issue → spec PR) | `intake.yml` | `wing-commander-1-intake.yml` | ✅ — [spec](specs/001-spec-intake/spec.md) |
| 1b · Clarification loop | `clarify.yml` | `wing-commander-2-clarify.yml` | ✅ — [spec](specs/004-clarify-on-pr/spec.md) |
| 2 · Plan | `plan.yml` | `wing-commander-3-plan.yml` | ✅ — [spec](specs/002-plan-stage/spec.md) |
| 3 · Tasks | `tasks.yml` | `wing-commander-4-tasks.yml` | ✅ — [spec](specs/003-tasks-stage/spec.md) |
| 4 · Implement ⟲ converge | `implement.yml` | `wing-commander-5-implement.yml` | ✅ — [spec](specs/005-implement-converge/spec.md) |
| 5 · Finalize | `finalize.yml` | `wing-commander-6-finalize.yml` | ✅ — [spec](specs/006-finalize-stage/spec.md) |
| 6 · Cleanup | `cleanup.yml` | `wing-commander-7-cleanup.yml` | ✅ — [spec](specs/007-cleanup-stage/spec.md) |
| Rebase | `rebase.yml` | `wing-commander-rebase.yml` | ✅ — [spec](specs/008-auto-rebase/spec.md) |
| Watchdog | `watchdog.yml` | `wing-commander-8-watchdog.yml` | ✅ — [spec](specs/015-pipeline-watchdog/spec.md) |
| PR conversation | `pr-conversation.yml` | `wing-commander-9-pr-conversation.yml` | ✅ — [spec](specs/033-pr-conversation-commands/spec.md) |
| Spec Kit updater | `auto-update-spec-kit.yml` | `wing-commander-auto-update-spec-kit.yml` | ✅ — [spec](specs/027-auto-update-spec-kit/spec.md) |
| Metrics | `metrics-persist.yml` | `wing-commander-metrics-persist.yml` | ✅ — [spec](specs/043-durable-metrics-record/spec.md) |

Three more workflows are published for stages and wrappers to call, and are
not stages of their own: `fold-cycle-guard.yml`, `agent-startup-check.yml` and
`private-image-dogfood.yml`.

Workflows that exist only in this repository, with no published stage: the
board loop (`board-loop.yml`, [spec](specs/057-autonomous-board-loop/spec.md)),
the lifecycle review gate (`lifecycle-review-gate.yml`,
[spec](specs/062-lifecycle-review-gate/spec.md)), spec PR review
(`spec-pr-review.yml`, [spec](specs/122-settled-spec-pr-review/spec.md)),
board status (`board-status.yml`), auto-release (`auto-release.yml`,
[spec](specs/045-auto-release-verified-head/spec.md)) and the gate suite
(`lint-workflows.yml`).

## Quickstart

1. Follow [docs/setup.md](docs/setup.md): create the `wing-commander-bot` GitHub App,
   add the secrets (a Claude credential — `CLAUDE_CODE_OAUTH_TOKEN` or
   `ANTHROPIC_API_KEY` — plus `WING_COMMANDER_APP_ID` and `WING_COMMANDER_APP_PRIVATE_KEY`),
   and create the labels.
2. Open an issue describing a feature in plain language.
3. Apply the `spec-request` label (maintainers only — this is the approval gate).
4. Review the spec PR that appears; answer any clarification questions by
   replying on your issue.

Prefer writing specs by hand? Run spec-kit locally (`/speckit-specify` in Claude
Code) and open the PR yourself — the pipeline picks up from the merge exactly the
same way.

## Using this on your own project

The pipeline operates on **your** project's artifacts, not this repository's:
every path it touches — the constitution (`.specify/memory/constitution.md`),
spec templates and scripts (`.specify/`), the spec-kit skills
(`.claude/skills/speckit-*`), and the `specs/` directory — resolves relative to
the repository the workflows run in. Wing Commander ships pipeline mechanics;
it never ships or reads project content of its own. This repository's
constitution governs this repository only — yours governs yours.

To adopt it today:

1. Run `specify init` in your repo (pin the same spec-kit version this repo
   does — `speckit_version` in `.specify/init-options.json`) so it has its own `.specify/` and `.claude/skills/speckit-*` —
   then write your constitution with `/speckit-constitution`.
2. Add thin wrapper workflows that call the published stage workflows
   (`intake.yml` … `rebase.yml`) by reference, version-pinned — copy-paste
   set, per-stage reference, and pinning guidance in
   **[docs/adoption.md](docs/adoption.md)**. You never copy stage logic, and
   moving your pin picks up fixes.
3. Follow [docs/setup.md](docs/setup.md) (App, secrets, labels).

Any subset of stages works, with any triggers you choose — this repository's
own `wing-commander-*.yml` workflows are the same thin wrappers, calling the
same stages by local path.

What you get by pinning is the feature lifecycle and the published stages in
the table above. The board loop, the review gates, board status and
auto-release are this repository's own workflows and are not published.

**"Can I use the `wing-commander-bot`?"** — you create your own. The bot is
just a GitHub App you register in your own account (any name works; the
pipeline resolves the App's slug at runtime), so nothing ties your pipeline
to this repository's bot or credentials. [docs/setup.md](docs/setup.md#1-create-the-wing-commander-bot-github-app)
walks through the two-minute setup.

## Roadmap

| Milestone | Scope | State |
|---|---|---|
| 1 · Spec stages | intake, clarify, plan, tasks | ✅ done |
| 2 · Build stages | implement ⟲ converge, finalize, cleanup, rebase | ✅ done |
| 3 · Hardening & observability | per-run agent metrics (turns/tokens/cost), failure-mode polish | ✅ done |
| 4 · Extraction | stages become reusable `workflow_call` workflows; consuming repos keep thin event wrappers + their own `specify init` output | ✅ done — [docs/adoption.md](docs/adoption.md) |
| 5 · Bounded autonomy | the pipeline works its own board and merges what the constitution lets it: board fixes, verified upgrades, then final PRs | in progress — the open "Roadmap" issue tracks it |

Each milestone is built *through* the pipeline itself (constitution I): open an
issue, get the `spec-request` label, and the stages above carry it to a PR.
What is in flight, queued and parked right now is on the "Roadmap" issue, not
here.

## Design principles

The project [constitution](.specify/memory/constitution.md) governs every change:

1. **Guide** — the repo is its own first example.
2. **Cost-conscious model tiering** — Opus for specs and clarification, Sonnet
   for planning, tasks and implementation, Haiku for summaries; Opus for
   implementation only by explicit opt-in, and every agent step runs under a
   bounded turn budget.
3. **Simple, GitHub-native interaction** — issues, comments, PRs; nothing else.
4. **Automation-first** — describe, clarify, review twice; everything else is
   automated, and surviving manual steps are always reported.
5. **Security** — issue content is data, never instructions; a maintainer's
   label or authorship gates entry; least-privilege tools, including a stage
   agent's inability to write its own `.claude/` control surface; humans merge
   every plan PR and every amendment, and the final PR unless the lifecycle
   auto-merge setting is on; a spec PR is merged by a human, or by the
   owner's session under the spec-merge rule.
6. **Portability** — the consuming repository owns its artifacts; the pipeline
   reads `.specify/`, spec-kit skills, and `specs/` only from the checkout it
   runs in, never bundling its own.
7. **Two interfaces** — the published stage contract is versioned and pinned by
   adopters; this repo's wrappers and spec-kit artifacts are one adopter's
   configuration. Stages read no ambient repository state; wrappers own
   triggers and gates.
8. **A green check means what it says** — a gate must be able to fail its own
   subject: registry-reachable, run with the same arguments locally as in CI,
   triggered by what it checks, loud rather than vacuous when it cannot reach
   it, and every failure branch it ships covered by a checked-in fixture.
9. **Judgment that gates a durable action belongs in deterministic code** — a
   filed finding, a fingerprint, a dedup outcome, a write. A prompt
   instruction can be silently unfollowed with no error; code that computes
   the same input the same way every time cannot.
10. **Bounded autonomy** — the pipeline works its own issue board: triage,
    route, fix, review, merge, prove. The bot merges three classes only:
    fix-shaped changes inside a deterministic size-and-path backstop, behind
    green checks on the exact head, an independent review with zero open
    findings, and a kill switch; dependency bumps it opened itself, after
    their own verification passed; and, only while
    `WING_COMMANDER_LIFECYCLE_AUTO_MERGE` is on (it defaults to off), a
    lifecycle's final PR, behind deterministic conditions at the exact head,
    a clean review round, and its own kill switch. Spec-shaped work is filed
    as a `spec-proposal`, which the bot never promotes. The owner's session
    may take two acts on conditions it reads and posts first: merge a spec
    PR it took no part in, once the automatic spec review and a fresh
    session both report the exact commit clean; and promote a proposal it
    did not file, while fewer than three lifecycles are in flight. Every
    other merge stays human.

Full stage-by-stage design: [docs/architecture.md](docs/architecture.md).

## Repository map

```
.github/workflows/<stage>.yml      the published stages (workflow_call; what adopters
                                   pin): intake, clarify, plan, tasks, implement,
                                   finalize, cleanup, rebase, pr-conversation,
                                   watchdog, auto-update-spec-kit, metrics-persist,
                                   fold-cycle-guard, agent-startup-check,
                                   private-image-dogfood
.github/workflows/wing-commander-*.yml  this repo's thin wrappers — triggers + gates only
.github/workflows/board-loop.yml   this repo only: the hourly maintenance loop
.github/workflows/lifecycle-review-gate.yml, spec-pr-review.yml
                                   this repo only: independent review of final and spec PRs
.github/workflows/auto-release.yml, release.yml
                                   this repo only: prove the head end to end, then tag
                                   vX.Y.Z and advance the floating major tag
.github/workflows/lint-workflows.yml    the gate suite, run on pull requests that touch
                                   workflows, actions, scripts, docs or Markdown
.github/actions/wing-commander-*/  composite actions the stages share (published)
.github/actions/_shared/           scripts shared between composites (internal)
.github/scripts/verify-*.py        the gates; run-local-gates.py runs the same set locally
.github/scripts/board_*.py, wc_*.py     the deterministic logic behind the loops
.claude/skills/speckit-*/ spec-kit skills (installed by `specify init`; pin in .specify/init-options.json)
.claude/skills/<other>/   this repo's own session procedures (review-until-clean,
                          answer-from-precedent, whats-on-me, prove-after-merge, …)
.specify/                 spec-kit scripts, templates, memory/constitution.md
specs/NNN-slug/           one directory per feature: spec.md, plan.md, tasks.md,
                          spec-meta.json (lifecycle state), checklists/, contracts/
docs/                     setup + adoption + architecture + reference
CLAUDE.md                 the rules a session follows when working this repository
```

## License

[MIT](LICENSE) — see [CONTRIBUTING.md](CONTRIBUTING.md) for how to get
involved. Wing Commander is built on [GitHub spec-kit](https://github.com/github/spec-kit)
and [Claude Code](https://github.com/anthropics/claude-code-action), which are
their own projects under their own licenses; Wing Commander is not affiliated
with or endorsed by the Spec Kit project.
