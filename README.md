# speckit-action

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

| Stage | Workflow | State |
|---|---|---|
| 1 · Intake (issue → spec PR) | `speckit-1-intake.yml` | ✅ implemented |
| 1b · Clarification loop | `speckit-2-clarify.yml` | ✅ implemented |
| 2 · Plan | `speckit-3-plan.yml` | ✅ implemented — [spec](specs/002-plan-stage/spec.md) |
| 3 · Tasks | `speckit-4-tasks.yml` | 🧩 stub |
| 4 · Implement ⟲ converge | `speckit-5-implement.yml` | 🧩 stub |
| 5 · Finalize | `speckit-6-finalize.yml` | 🧩 stub |
| 6 · Cleanup | `speckit-7-cleanup.yml` | 🧩 stub |
| Auto-rebase | `speckit-rebase.yml` | 🧩 stub |

The stubs have their real triggers and gates in place; their bodies are the next
things to be built *through* the pipeline (open an issue, label it `spec-request`).

## Quickstart

1. Follow [docs/setup.md](docs/setup.md): create the `speckit-bot` GitHub App,
   add three secrets (`CLAUDE_CODE_OAUTH_TOKEN`, `SPECKIT_APP_ID`,
   `SPECKIT_APP_PRIVATE_KEY`), and create the labels.
2. Open an issue describing a feature in plain language.
3. Apply the `spec-request` label (maintainers only — this is the approval gate).
4. Review the spec PR that appears; answer any clarification questions by
   replying on your issue.

Prefer writing specs by hand? Run spec-kit locally (`/speckit-specify` in Claude
Code) and open the PR yourself — the pipeline picks up from the merge exactly the
same way.

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

Full stage-by-stage design: [docs/architecture.md](docs/architecture.md).

## Repository map

```
.github/workflows/        the pipeline stages (speckit-1 … speckit-rebase)
.github/actions/speckit-context/   shared App-token + spec-identity resolution
.claude/skills/speckit-*/ spec-kit skills (installed by `specify init`, pinned v0.12.4)
.specify/                 spec-kit scripts, templates, memory/constitution.md
specs/NNN-slug/           one directory per feature: spec.md, plan.md, tasks.md,
                          spec-meta.json (lifecycle state), checklists/
docs/                     setup + architecture
```
