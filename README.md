# Wing Commander

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

**Spec-Driven Development as a GitHub-native pipeline.** Open an issue describing
what you want; the pipeline turns it into a reviewed specification, a reviewed
plan, generated tasks, an implementation, and finally a pull request — powered by
[GitHub spec-kit](https://github.com/github/spec-kit) and
[Claude Code](https://github.com/anthropics/claude-code-action), with humans
gating every merge.

This repository **dogfoods itself**: the pipeline is being built through the
pipeline. The first spec ever produced here is the spec for the intake stage —
see [`specs/001-spec-intake/`](specs/001-spec-intake/spec.md).

## How it works

```
you: open an issue describing a feature
maintainer: applies the `spec-request` label        ← human gate 1
  🤖 /speckit-specify → draft spec PR to main
  🤖 clarification questions posted on your issue — just reply
maintainer: reviews & merges the spec PR             ← human gate 2
  🤖 /speckit-plan → plan PR on a dedicated spec branch
maintainer: reviews & merges the plan PR             ← human gate 3
  🤖 /speckit-tasks → tasks.md (auto-committed)
  🤖 /speckit-implement ⟲ /speckit-converge until done (capped)
  🤖 final PR to main + any remaining manual tasks reported on your issue
maintainer: reviews & merges the final PR            ← human gate 4
  🤖 branches deleted, labels flipped, issue closed
```

Your issue is the feature's **lifecycle thread**: every stage reports its status
there, and its labels (`spec:NNN-slug`, `stage:*`) always show where things stand.

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

1. Run `specify init` in your repo (pin the same spec-kit version, currently
   v0.12.4) so it has its own `.specify/` and `.claude/skills/speckit-*` —
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

Each milestone is built *through* the pipeline itself (constitution I): open an
issue, get the `spec-request` label, and the stages above carry it to a PR.

## Design principles

The project [constitution](.specify/memory/constitution.md) governs every change:

1. **Guide** — the repo is its own first example.
2. **Cost-conscious model tiering** — Haiku for triage, Sonnet for spec work,
   Opus only by explicit opt-in for implementation.
3. **Simple, GitHub-native interaction** — issues, comments, PRs; nothing else.
4. **Automation-first** — describe, clarify, review twice; everything else is
   automated, and surviving manual steps are always reported.
5. **Security** — issue content is data, never instructions; maintainer labels
   gate entry; least-privilege tools; humans merge everything.
6. **Portability** — the consuming repository owns its artifacts; the pipeline
   reads `.specify/`, spec-kit skills, and `specs/` only from the checkout it
   runs in, never bundling its own.
7. **Two interfaces** — the published stage contract is versioned and pinned by
   adopters; this repo's wrappers and spec-kit artifacts are one adopter's
   configuration. Stages read no ambient repository state; wrappers own
   triggers and gates.

Full stage-by-stage design: [docs/architecture.md](docs/architecture.md).

## Repository map

```
.github/workflows/<stage>.yml      the published stages (workflow_call; what adopters
                                   pin): intake, clarify, plan, tasks, implement,
                                   finalize, cleanup, rebase, watchdog
.github/workflows/wing-commander-*.yml  this repo's thin wrappers — triggers + gates only
.github/workflows/release.yml      tag vX.Y.Z, advance the floating major tag
.github/actions/wing-commander-context/   shared App-token + spec-identity resolution
.github/actions/wing-commander-preflight/ credential + prerequisite fail-fast checks
.github/actions/wing-commander-metrics-summary/  per-run agent metrics rendering
.claude/skills/speckit-*/ spec-kit skills (installed by `specify init`, pinned v0.12.4)
.specify/                 spec-kit scripts, templates, memory/constitution.md
specs/NNN-slug/           one directory per feature: spec.md, plan.md, tasks.md,
                          spec-meta.json (lifecycle state), checklists/
docs/                     setup + adoption + architecture
```

## License

[MIT](LICENSE) — see [CONTRIBUTING.md](CONTRIBUTING.md) for how to get
involved. Wing Commander is built on [GitHub spec-kit](https://github.com/github/spec-kit)
and [Claude Code](https://github.com/anthropics/claude-code-action), which are
their own projects under their own licenses; Wing Commander is not affiliated
with or endorsed by the Spec Kit project.
