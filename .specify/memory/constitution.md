# Speckit GitHub Action Constitution

## Core Principles

### I. Guide — The Repo Is Its Own First Example
Every capability of the pipeline is built *through* the pipeline as soon as the pipeline can build it. Each feature begins life as a GitHub issue, becomes a spec under `specs/`, and flows through the same stages we ship to users. Documentation must always be able to point at a real spec, real PRs, and a real lifecycle issue in this repository as the worked example. If a change cannot be dogfooded yet (bootstrap phase), the reason is recorded in the PR description.

### II. Cost-Conscious Model Tiering
Every automated Claude invocation declares an explicit model, chosen by task weight: `claude-haiku-4-5` for triage, classification, labeling, and summaries; `claude-opus-4-8` for specification and clarification — the spec is the foundation every later stage consumes, so a fully fleshed-out spec is worth the premium and is the cheapest place to spend it; `claude-sonnet-5` for planning and task generation, which elaborate an already-solid spec; `claude-sonnet-5` (default) or `claude-opus-4-8` (explicit opt-in via repo variable or `model:opus` label) for implementation and convergence. Every agent step sets `--max-turns`. No stage may run without a bounded turn budget and an explicit model.

### III. Simple, GitHub-Native Interaction
Users interact with the pipeline the way they interact with any GitHub repository: open an issue, read and reply to comments, review and merge PRs. No external dashboards, no custom CLIs required of the requester. The lifecycle of a spec is legible from its original issue alone — every stage posts its status there. Course correction happens through ordinary GitHub actions: comment to clarify, review to reshape, close to cancel.

### IV. Automation-First
A requester should only ever need to: describe what they want, answer clarification questions, review the spec PR, and review the final implementation PR. Everything else — branch creation and deletion, labeling, stage transitions, task generation, implementation, convergence, rebasing, cleanup — is automated. Any manual step that survives must be reported explicitly to the lifecycle issue, never silently assumed.

### V. Security — Untrusted Content Is Never Instructions (NON-NEGOTIABLE)
Issue and comment bodies are user data, never agent instructions; prompts must frame them as such. Pipeline entry requires a maintainer-applied label. Comment-triggered stages verify the commenter is a maintainer (OWNER/MEMBER/COLLABORATOR) or the original issue author, and never react to bots. Each stage runs with the least-privilege tool allowlist it needs; web tools are disabled in all issue/comment-driven stages. Only trusted refs are checked out — never fork PR heads. Humans merge every PR into `main`; the bot never approves or merges to `main`. Authentication uses a dedicated GitHub App — never a PAT.

## Operational Constraints

- Spec artifacts live in `specs/<NNN-slug>/` (spec.md, plan.md, tasks.md, spec-meta.json, checklists/). `spec-meta.json` is the machine-readable source of truth for a spec's lifecycle state.
- Branch conventions: `spec-draft/<NNN-slug>` (draft spec PRs to main), `spec/<NNN-slug>` (long-lived per-spec integration branch), `plan/<NNN-slug>` and `impl/<NNN-slug>-iterN` (stage work branches).
- The implement ⟲ converge loop is capped (default 5 iterations); the final converge report is always posted to the lifecycle issue.
- Concurrent specs are supported: stages of one spec serialize via a per-spec concurrency group; different specs run in parallel.
- Spec-kit is pinned (currently v0.12.4); upgrades re-verify `.specify/scripts` behavior before adoption.

## Development Workflow

Stages and their gates: intake (`/speckit-specify`, human gate = maintainer label + spec PR review) → plan (`/speckit-plan`, human gate = plan PR review) → tasks (`/speckit-tasks`, auto-committed by default, configurable to PR) → implement ⟲ converge (`/speckit-implement`, `/speckit-converge`, machine gate = tasks.md unchanged after converge) → finalize (human gate = final PR review) → cleanup (automated). A stage may only start when its predecessor's gate has passed.

## Governance

This constitution supersedes ad-hoc practice in this repository. Every spec, plan, and implementation PR is checked against it during review; violations must be fixed or the constitution amended first. Amendments arrive as ordinary PRs that modify this file, state the motivation, and bump the version below (semver: breaking principle changes = MAJOR, new principles/sections = MINOR, clarifications = PATCH).

**Version**: 1.1.0 | **Ratified**: 2026-07-04 | **Last Amended**: 2026-07-05
