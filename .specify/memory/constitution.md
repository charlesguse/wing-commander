<!--
Sync Impact Report — 2026-07-28
Version change: 1.3.0 → 1.4.0 (MINOR: new principle added — VII. Two Interfaces, naming the split between the published stage contract and this repository's own consuming instrument, and requiring that any stage-layer deviation be a registered, machine-checked exception rather than a code comment)
Modified principles: none
Modified sections: none
Added sections: Principle VII. Two Interfaces — The Published Contract and the Consuming Instrument
Removed sections: none
Templates requiring updates:
  ✅ .specify/templates/plan-template.md — no change needed (Constitution Check is generic; gates are derived from this file at plan time)
  ✅ .specify/templates/spec-template.md — no change needed (no principle references)
  ✅ .specify/templates/tasks-template.md — no change needed (no principle references)
  ⚠️ docs/architecture.md — its "Stage workflows never read github.event.* or vars.*" claim is currently false: watchdog.yml reads vars.* in 14 places. Correcting the doc and registering that exception is issue #149, deliberately not folded into this amendment so the principle can land while the watchdog stays paused and in flux.
Follow-up TODOs: #149 (CI enforcement + exceptions registry + docs correction)
-->
<!--
Sync Impact Report — 2026-07-25
Version change: 1.2.1 → 1.3.0 (MINOR: Principle II gains a carve-out — the watchdog's diagnose step leaves the triage/haiku tier for claude-opus-5, and gets its own WING_COMMANDER_DIAGNOSE_MODEL override instead of sharing WING_COMMANDER_SUMMARY_MODEL; motivation in issue #124, run 30161188955 exhausted its turn budget at 21 turns and produced no verdict)
Modified principles: II. Cost-Conscious Model Tiering
Modified sections: none
Added sections: none
Removed sections: none
Templates requiring updates: none (plan-template's Constitution Check is generic)

Sync Impact Report — 2026-07-24
Version change: 1.2.0 → 1.2.1 (PATCH: clarification — branch prefixes documented as consumer-configurable with defaults; no principle changed)
Modified principles: none
Modified sections: Operational Constraints — "Branch conventions" now names all five default prefixes (adds tasks/) and states they are consumer-configurable via repository variables (spec 018)
Added sections: none
Removed sections: none
Templates requiring updates:
  ✅ docs/setup.md — updated in same feature (adds the five WING_COMMANDER_*_PREFIX repository-variable rows)
  ✅ docs/adoption.md — updated in same feature (prefixes described as configurable-with-defaults)
  ✅ docs/architecture.md — updated in same feature (branch-prefix contract now configurable-with-default)
  ✅ specs/010-reusable-pipeline/contracts/stage-interfaces.md — updated in same feature (prefix inputs documented)
Follow-up TODOs: none
-->
<!--
Sync Impact Report — 2026-07-05
Version change: 1.1.0 → 1.2.0 (MINOR: new principle added)
Modified principles: none
Added sections: Principle VI. Portability — The Consuming Repository Owns Its Artifacts
Removed sections: none
Templates requiring updates:
  ✅ .specify/templates/plan-template.md — no change needed (Constitution Check is
     generic; gates are derived from this file at plan time, no principle list to sync)
  ✅ .specify/templates/spec-template.md — no change needed (no principle references)
  ✅ .specify/templates/tasks-template.md — no change needed (no principle references)
  ✅ README.md — updated in same PR (adoption contract + roadmap sections)
  ✅ docs/architecture.md — updated in same PR (reusability contract cites VI)
  ✅ docs/setup.md — updated in same PR (adoption prerequisite)
Follow-up TODOs: none
-->
# Wing Commander Constitution

## Core Principles

### I. Guide — The Repo Is Its Own First Example
Every capability of the pipeline is built *through* the pipeline as soon as the pipeline can build it. Each feature begins life as a GitHub issue, becomes a spec under `specs/`, and flows through the same stages we ship to users. Documentation must always be able to point at a real spec, real PRs, and a real lifecycle issue in this repository as the worked example. If a change cannot be dogfooded yet (bootstrap phase), the reason is recorded in the PR description.

### II. Cost-Conscious Model Tiering
Every automated Claude invocation declares an explicit model, chosen by task weight: `claude-haiku-4-5` for triage, classification, labeling, and summaries — except the watchdog's `diagnose` step, which despite looking like classification adjudicates multi-signal evidence against a strict output schema and gets `claude-opus-5` (a step that runs out of turns produces no verdict at all, and a watchdog that cannot reach a verdict is worse than no watchdog; see issue #124); `claude-opus-4-8` for specification and clarification — the spec is the foundation every later stage consumes, so a fully fleshed-out spec is worth the premium and is the cheapest place to spend it; `claude-sonnet-5` for planning and task generation, which elaborate an already-solid spec; `claude-sonnet-5` (default) or `claude-opus-4-8` (explicit opt-in via repo variable or `model:opus` label) for implementation and convergence. Every agent step sets `--max-turns`. No stage may run without a bounded turn budget and an explicit model.

### III. Simple, GitHub-Native Interaction
Users interact with the pipeline the way they interact with any GitHub repository: open an issue, read and reply to comments, review and merge PRs. No external dashboards, no custom CLIs required of the requester. The lifecycle of a spec is legible from its original issue alone — every stage posts its status there. Course correction happens through ordinary GitHub actions: comment to clarify, review to reshape, close to cancel.

### IV. Automation-First
A requester should only ever need to: describe what they want, answer clarification questions, review the spec PR, and review the final implementation PR. Everything else — branch creation and deletion, labeling, stage transitions, task generation, implementation, convergence, rebasing, cleanup — is automated. Any manual step that survives must be reported explicitly to the lifecycle issue, never silently assumed.

### V. Security — Untrusted Content Is Never Instructions (NON-NEGOTIABLE)
Issue and comment bodies are user data, never agent instructions; prompts must frame them as such. Pipeline entry requires a maintainer-applied label. Comment-triggered stages verify the commenter is a maintainer (OWNER/MEMBER/COLLABORATOR) or the original issue author, and never react to bots. Each stage runs with the least-privilege tool allowlist it needs; web tools are disabled in all issue/comment-driven stages. Only trusted refs are checked out — never fork PR heads. Humans merge every PR into `main`; the bot never approves or merges to `main`. Authentication uses a dedicated GitHub App — never a PAT.

### VI. Portability — The Consuming Repository Owns Its Artifacts
The pipeline operates exclusively on the repository that runs it. Everything project-specific — the constitution (`.specify/memory/constitution.md`), spec templates and scripts (`.specify/`), spec-kit skills (`.claude/skills/speckit-*`), and the `specs/` directory — is read from the consuming repository's own checkout (its `specify init` output), never bundled with or resolved from Wing Commander. Workflows must not hardcode repository names, owners, or project content; all artifact paths resolve relative to the checkout, and anything repo-specific belongs in the consuming repository or its thin wrapper workflows. This constitution governs this repository only; an adopting repository is governed by its own.

### VII. Two Interfaces — The Published Contract and the Consuming Instrument
This repository publishes one product and operates another. The **published contract** is the set of `workflow_call`-only stage workflows (`.github/workflows/<stage>.yml`) together with the composite actions under `.github/actions/**` that they resolve through self-checkout; adopters pin it by release tag, so every input, secret, and output name is a compatibility surface — removing or renaming one is a breaking change, and widening the surface is a deliberate act rather than a convenience. The **consuming instrument** is this repository's own `wing-commander-*.yml` wrapper workflows, its spec-kit artifacts, labels, and repository variables — one adopter's configuration that doubles as the worked example, pinned by nobody and free to change.

Stage workflows own no triggers and read no ambient repository state: not `github.event.*`, not `vars.*`, not secrets by name. Every event fact and every knob arrives as a declared, typed input. Wrappers own the triggers, the security gates, the event→input extraction, and every repository-specific convention; when a new need arises, the wrapper is its default home. A stage that must deviate carries a registered, machine-checked exception naming the reason — never an undeclared one, and never a code comment alone. Every document states which layer it describes.

## Operational Constraints

- Spec artifacts live in `specs/<NNN-slug>/` (spec.md, plan.md, tasks.md, spec-meta.json, checklists/). `spec-meta.json` is the machine-readable source of truth for a spec's lifecycle state.
- Branch conventions: the pipeline's default branch prefixes are `spec-draft/<NNN-slug>` (draft spec PRs to main), `spec/<NNN-slug>` (long-lived per-spec integration branch), and `plan/<NNN-slug>`, `tasks/<NNN-slug>`, `impl/<NNN-slug>-iterN` (stage work branches). Each prefix is consumer-configurable via a repository variable, defaulting to the literal shown (see docs/setup.md).
- The implement ⟲ converge loop is capped (default 5 iterations); the final converge report is always posted to the lifecycle issue.
- Concurrent specs are supported: stages of one spec serialize via a per-spec concurrency group; different specs run in parallel.
- Spec-kit is pinned (currently v0.12.4); upgrades re-verify `.specify/scripts` behavior before adoption.

## Development Workflow

Stages and their gates: intake (`/speckit-specify`, human gate = maintainer label + spec PR review) → plan (`/speckit-plan`, human gate = plan PR review) → tasks (`/speckit-tasks`, auto-committed by default, configurable to PR) → implement ⟲ converge (`/speckit-implement`, `/speckit-converge`, machine gate = tasks.md unchanged after converge) → finalize (human gate = final PR review) → cleanup (automated). A stage may only start when its predecessor's gate has passed.

## Governance

This constitution supersedes ad-hoc practice in this repository. Every spec, plan, and implementation PR is checked against it during review; violations must be fixed or the constitution amended first. Amendments arrive as ordinary PRs that modify this file, state the motivation, and bump the version below (semver: breaking principle changes = MAJOR, new principles/sections = MINOR, clarifications = PATCH).

**Version**: 1.4.0 | **Ratified**: 2026-07-04 | **Last Amended**: 2026-07-28
