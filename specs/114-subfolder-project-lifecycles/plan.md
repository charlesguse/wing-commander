# Implementation Plan: Subfolder Project Lifecycles

**Branch**: `spec/114-subfolder-project-lifecycles` | **Date**: 2026-10-14 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/114-subfolder-project-lifecycles/spec.md` (lifecycle issue #1020)

## Summary

Let one repository hold many Wing Commander projects as folders. A lifecycle names its project `P` once, at intake, through a maintainer-applied `node:<path>` label. Deterministic code validates `P` and records it in the lifecycle's durable names: branches `<prefix>P/<NNN-slug>`, label `spec:P/<NNN-slug>`, and the repository-relative spec directory `P/specs/<NNN-slug>`. Every later stage, the watchdog and the fold-cycle guard recover `P` through one shared parser. Nothing is re-inferred.

Technical approach (details in [research.md](research.md)):

1. **One project-resolution home.** A new composite `wing-commander-project` validates the path, checks the real-entry (no symlink) rule, and emits `project`, `spec-dir`, `spec-dir-rel`, `slug-qualified` and `slug-budget`. It sources a new shared script `_shared/project-name.sh`, which holds the grammar, the name parser (both directions) and the label-budget arithmetic. Workflows consume outputs and keep at most a one-line fallback.
2. **Project-aware existing actions.** `wing-commander-preflight`, `wing-commander-context`, `wing-commander-inspected-run-identity`, `wing-commander-spec-meta` and `read-spec-meta.sh`, `wing-commander-write-boundary` and `classify-out-of-boundary-tasks.sh`, and the fold-queue and chain-stop actions take a project-aware spec directory. Root values are byte-identical to today's.
3. **Agents work in `P`.** Each Edit/Write agent runs with `P` as working directory. Every reference to the trusted checkout and to repository-level tooling is an absolute workspace-root path (FR-025).
4. **Containment in two layers.** The deny list (single `no-write-paths` definition, spec 090) gains project-derived `.claude/` and `.git/` denies. A deterministic post-agent diff guard fails the stage on any change outside `P` (FR-021).
5. **Intake gets the only new input**, `routing-label-prefix` (default empty), plus per-project numbering, label-first creation, slug budget, re-run refusal, and two-level concurrency.
6. **Verification** by new `verify-*.py` gates with checked-in fixtures, registered in `run-local-gates.py`. The constitution amendment 2.4.0 → 2.5.0 ships as a separate human-merged PR.

## Technical Context

**Language/Version**: Bash (POSIX-leaning, `set -euo pipefail`) in composite actions and workflow `run:` blocks; Python 3 for `verify-*.py` gates; `jq`; GitHub Actions YAML.

**Primary Dependencies**: `anthropics/claude-code-action` (agent steps), `gh` CLI, `git`, vendored Spec Kit v1.0.5+ (unchanged; nearest-`.specify/` resolution is relied on, no vendored edits).

**Storage**: Git refs, labels, repository files (`spec-meta.json`, `specs/`), and the existing metrics artifacts. No new persistent store.

**Testing**: Gate suite via `python .github/scripts/run-local-gates.py`. New gates are `verify-*.py` with fixtures under `.github/scripts/fixtures/` or `tests/`. Behaviour that only runs in Actions is proven after merge (`prove-after-merge`).

**Target Platform**: GitHub Actions Linux runners, including adopter-supplied containers (`container-shell-safety` applies to any new `run:` step in a container job).

**Project Type**: Pipeline of reusable workflows and composite actions (the published contract), plus this repository's wrappers (the consuming instrument).

**Performance Goals**: No added agent turns. Resolution is a handful of local `git` and `test` calls per stage.

**Constraints**: Additive-only interface (FR-017). Root behaviour byte-identical (FR-016). `spec:` labels ≤ 50 characters, so `P` ≤ 28. The prefix must be a single segment ending in `/`. Workflow comments are load-bearing, so the suite is re-run after comment edits.

**Scale/Scope**: About 9 stage workflows, about 12 composites, 1 shared script, 6–8 new gates, `docs/adoption.md`, and one constitution amendment.

## Constitution Check

*GATE: passed before Phase 0; re-checked after Phase 1 (below).*

| Principle | Assessment |
|---|---|
| I. Guide | Pass. The feature is built through the pipeline. The amendment is a human PR, as spec 110 FR-003 set the precedent. |
| II. Model tiering | Pass. No new agent invocations and no model or turn-budget changes. |
| III. GitHub-native | Pass. Routing is an ordinary label; callouts go on the lifecycle issue. |
| IV. Automation-first | Pass. The only manual steps are creating the `node:` labels and widening wrapper path filters, both reported in the adoption guide (FR-018). |
| V. Security | Pass, with attention. `P` is untrusted and validated in deterministic code. The routing label is read only at intake from live labels. Denies for `.claude/` and `.git/` are extended, never relaxed. The trusted checkout is referenced by workspace-root absolute path, and a tracked `.wing-commander-pipeline/` at any depth is refused. |
| VI. Portability | **Needs amendment.** Its artifact list is "read from the consuming repository's checkout" with root-relative paths. Resolving relative to the project folder is what FR-024 amends. |
| VII. Two interfaces | Pass. The one new input is optional with an empty default. This repository's wrappers need no edit. |
| VIII. Green means it | Pass. Every new validation has accept and reject fixtures (FR-019) and a single-home gate (FR-020). |
| IX. Judgment → deterministic code | Pass. Path validation, label counting, prefix validation, budget, containment diff and refusal are all code. The agent receives its slug budget; it does not compute it. |
| X. Bounded autonomy | Pass. The amendment never reaches `main` through the lifecycle PR merge. |

Gate result: **no unjustified violations**. The Principle V/VI and Operational Constraints changes are the planned amendment (research D12), not a violation.

Post-design re-check: unchanged. The design adds no write capability, no new credential, and no new trigger.

## Project Structure

### Documentation (this feature)

```text
specs/114-subfolder-project-lifecycles/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── project-path-and-names.md      # grammar, name forms, shared parser
│   ├── routing-and-intake.md          # routing-label-prefix input, intake behaviour
│   └── containment-and-trusted-checkout.md
└── tasks.md                           # created by the tasks stage
```

### Source Code (repository root)

```text
.github/
├── actions/
│   ├── _shared/
│   │   ├── project-name.sh              # NEW  grammar, parser, budget (single home)
│   │   ├── read-spec-meta.sh            # project-aware spec_dir rule
│   │   ├── classify-out-of-boundary-tasks.sh   # P/specs/** classification
│   │   └── normalize-write-path-prefix.sh
│   ├── wing-commander-project/          # NEW  resolve + validate P; outputs
│   ├── wing-commander-containment/      # NEW  post-agent "no change outside P" guard
│   ├── wing-commander-preflight/        # P-aware .specify/skills/version drift
│   ├── wing-commander-context/          # P-aware spec-dir derivation
│   ├── wing-commander-inspected-run-identity/
│   ├── wing-commander-spec-meta/
│   ├── wing-commander-tool-args/        # project-derived .claude/.git denies; root-anchored grants
│   ├── wing-commander-write-boundary/ (+ -lookup)
│   ├── wing-commander-fold-queue-*/ and wing-commander-chain-stop-notice/
│   └── wing-commander-tasks-checkbox-count/
├── workflows/
│   ├── intake.yml                       # routing-label-prefix, numbering, label-first, refusal, groups
│   ├── clarify.yml plan.yml tasks.yml implement.yml finalize.yml
│   ├── rebase.yml cleanup.yml pr-conversation.yml
│   ├── watchdog.yml fold-cycle-guard.yml
│   └── lint-workflows.yml               # registers new gates
└── scripts/
    ├── verify-project-path-grammar.py
    ├── verify-project-name-parser.py
    ├── verify-project-single-home.py     # FR-020 root-only patterns + fixtures
    ├── verify-intake-routing.py
    ├── verify-project-numbering.py
    ├── verify-subfolder-containment.py
    ├── verify-pipeline-checkout-containment.py
    ├── verify-spec-meta-self-identity.py (extend if present)
    └── fixtures/project-*/
docs/adoption.md                         # FR-018 section
.specify/memory/constitution.md          # amendment 2.5.0 — separate human-merged PR
.specify/memory/constitution-history.md  # Sync Impact Report moved to top, same commit
```

**Structure Decision**: Extend the existing composite-action and shared-script layout. No new top-level directories. Project logic has exactly one home, `_shared/project-name.sh`, consumed through `wing-commander-project`. Gate `verify-project-single-home.py` fails if a workflow or composite reintroduces a root-only pattern (FR-020), per CLAUDE.md's "shared logic has exactly one home" rule.

## Complexity Tracking

No constitution violations to justify. Two deliberate extra moving parts are recorded for reviewers.

| Addition | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| Both a deny list and a post-agent diff guard | The deny list cannot express "everything except `P`" for Edit/Write. The diff guard also catches Bash-driven writes. | A deny list alone leaves shell writes outside `P` uncaught. A diff guard alone lets the agent rewrite `.claude/` mid-run, which Principle V forbids. |
| New `wing-commander-project` composite | Seven stages need identical resolution and validation. | Per-workflow `run:` blocks would be pasted copies, which CLAUDE.md forbids. |
