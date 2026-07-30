# Implementation Plan: Auto-Update Spec Kit

**Branch**: `spec/027-auto-update-spec-kit` | **Date**: 2026-07-30 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/027-auto-update-spec-kit/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

Add a maintenance stage-pair, `auto-update-spec-kit.yml` (+ wrapper
`wing-commander-auto-update-spec-kit.yml`), that keeps the repository's
pinned Spec Kit version (`.specify/init-options.json`'s `speckit_version`,
currently `0.12.4`, and the matching `SPECKIT_SUPPORTED_VERSION` constant
`wing-commander-preflight` warns against) current with upstream
`github/spec-kit` releases without a human remembering to do it.
Mechanically, on its **daily schedule** (plus on-demand
`workflow_dispatch`):

1. **Health-checks** the *currently pinned* version first, via the same
   lightweight verification described in step 3 — if that ever fails,
   the process reads the prior pinned value straight out of git history
   (the most recent commit that changed `speckit_version`, before the
   one that broke it) and opens an automatic revert PR plus a flagged
   issue (FR-006/FR-007), rather than tracking a separate "last known
   working version" ledger that could desync from reality
   (research.md).
2. **Detects** the latest eligible (stable, non-prerelease) upstream
   release deterministically (`gh api repos/github/spec-kit/releases` +
   semver compare, no LLM) and classifies the jump as patch/minor/major.
3. **Settles** before ever preparing an upgrade: a freshly detected
   version opens the singular lifecycle issue in a "watching" state and
   the run stops; only once a *later* daily check observes the *same*
   target again (no fixed calendar window — a repo-variable-configurable
   count of consecutive unchanged daily checks, default one) does
   preparation begin — this is what keeps a same-day patch race from
   getting adopted mid-flight (FR-002).
4. **Evaluates the upgrade path** with one judgment-bearing agent step
   (`claude-sonnet-5`, reading only `gh api`-fetched release notes and a
   diff of what the candidate's `.specify/` artifacts would change,
   never live web browsing): clean bump → prepares it; needs more than a
   version bump (script/template migration) → routes to a human without
   applying anything (FR-018); genuinely ambiguous upstream options →
   posts the options with reasoning and sources as a question on the
   issue and stops, awaiting a maintainer's reply (FR-012).
5. **Verifies** the prepared candidate with a **tiered** smoke test —
   lightweight (run `.specify/scripts/bash/*.sh` in an isolated worktree)
   always; additionally, for minor/major jumps, one real throwaway
   spec-kit-driven stage run (FR-004).
6. **Acts**: on pass, opens a version-bump PR (never merges it —
   constitution V is NON-NEGOTIABLE here) whose body carries `Closes
   #<issue>` so the lifecycle issue closes itself the moment a human
   merges (FR-009, FR-017); on fail, leaves the pin untouched, flags the
   issue with an `auto-update:failed` label, and stays open (FR-010).

A maintainer's reply to an FR-012 question, and the PR-merge event
itself, are two more trigger reasons the same wrapper routes into the
same stage via one typed `trigger` input — no separate resume-stage file
(research.md's "one wrapper multiplexes three trigger types" decision) —
so this feature's total new footprint is exactly one stage file and one
wrapper file, matching `rebase.yml`/`watchdog.yml`'s maintenance-workflow
shape rather than the eight numbered per-spec lifecycle stages.

## Technical Context

**Language/Version**: Bash (GitHub Actions `run:` steps), YAML (workflow
definitions), `jq` for JSON — identical toolchain to every other pipeline
stage; no new language introduced.

**Primary Dependencies**: GitHub Actions, `gh` CLI (`gh api
repos/github/spec-kit/releases`, `gh search issues`, `gh pr create`,
`gh issue comment`/`create`/`edit`), `jq`, `git`, `anthropics/claude-code-action@v1`
(two agent steps: `evaluate-path`, comment-reply interpretation — see
research.md), the repo's own `.github/actions/wing-commander-context`,
`wing-commander-preflight`, `wing-commander-callout`, and
`wing-commander-metrics-summary` composites, reached via the same
pipeline-repo self-checkout every other stage performs. No new external
service, SDK, or vendored copy of Spec Kit's source.

**Storage**: No new persisted state file. Settle-window tracking lives in
a hidden marker (`<!-- wing-commander-auto-update-spec-kit:
candidate=X.Y.Z observed=N -->`) in the singular open lifecycle issue's
body, discovered via `gh search issues` (reusing `rebase.yml`/
`watchdog.yml`'s marker-in-body dedup convention). "Last known working
version" is derived from `git log -p -- .specify/init-options.json`, not
stored separately (research.md — mirrors `015-pipeline-watchdog/research.md`'s
explicit rejection of a second source of truth for durable dedup state).
`vars.WING_COMMANDER_AUTO_UPDATE_SPEC_KIT_PAUSED`,
`_STABILIZATION_CHECKS`, and `_MODEL` are repo variables, not files, so a
maintainer can change them without a PR.

**Testing**: No automated test suite exists for any pipeline stage in
this repository (confirmed: no `package.json`, no test directories,
static validation only — matching `015-pipeline-watchdog/plan.md`'s same
finding). This stage is validated the same way — this plan's
`quickstart.md` scenarios exercise all four user stories and the spec's
edge cases against scratch runs/issues/PRs, cross-checked against
`lint-workflows.yml` (YAML/bash-syntax gate over every workflow file,
including the two new ones).

**Target Platform**: GitHub Actions (`ubuntu-latest` runners), triggered
by `schedule` (daily), `workflow_dispatch` (on-demand, FR-002),
`pull_request: {types: [closed]}` (filtered to this feature's own
version-bump/revert PRs, for the close-with-summary step), and
`issue_comment: {types: [created]}` (filtered to the singular open
auto-update issue, for resuming an FR-012 question) — all resolved to
one typed `trigger` input at the wrapper, never read as raw event data
inside the reusable stage (constitution VII).

**Project Type**: Single project — CI/CD automation under
`.github/workflows/`, reusing existing composite actions. No
frontend/backend split.

**Performance Goals**: SC-001 — the routine "new eligible version exists"
→ "reviewable version-bump PR" path completes with zero human actions
before review. Not latency-sensitive (a daily cadence has no tight time
budget); the lightweight verification tier is bash/script execution
(seconds), and the end-to-end tier (minor/major only) is bounded to one
throwaway spec-kit-driven stage run, not a full pipeline traversal.

**Constraints**: Never adopts a version the same day it's first observed
(FR-002); never applies a partial/best-effort migration when the upgrade
needs more than a pinned-version bump (FR-018); never guesses silently
when upstream offers genuinely ambiguous upgrade paths (FR-012); never
merges its own version-bump or revert PR (FR-017, constitution V
NON-NEGOTIABLE); never leaves the pin on a version that failed
verification (FR-006, SC-003); treats every fetched release-notes body
and every issue-comment reply as untrusted data, never instructions
(constitution V) — the comment-reply path additionally verifies the
commenter is OWNER/MEMBER/COLLABORATOR or the issue's own author before
treating a reply as a decision at all, reusing `wing-commander-2-clarify.yml`'s
exact author-association check. Least-privilege `--allowedTools` per
agent step; no web-browsing tools (`WebSearch`/`WebFetch`) on either
agent step — `evaluate-path`'s "sources" come from `gh api`-fetched
release-notes text, never live browsing (research.md). Only trusted refs
are ever checked out.

**Scale/Scope**: Two new workflow files (`auto-update-spec-kit.yml`,
`wing-commander-auto-update-spec-kit.yml`), zero new
`.specify/memory/*.json` config files (research.md's two "no new ledger"
decisions), and a `docs/architecture.md` section documenting the new
stage-pair (tasks-phase concern). No changes to any of the eight
numbered lifecycle stage files or to `watchdog.yml`/`rebase.yml` — this
feature reads `wing-commander-preflight`'s existing
`SPECKIT_SUPPORTED_VERSION` constant only insofar as its own version-bump
PR must update that constant alongside `.specify/init-options.json`
(same PR, not a separate change to the action itself).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Guide**: This feature is itself built through the pipeline (issue
  #153 → this spec → this plan → tasks → implementation), and its own
  first live run will be a real worked example of the pipeline updating
  its own pinned tooling — the dogfooding case constitution I asks for
  directly, on a value (`speckit_version`) this repository already
  depends on today. **Pass.**
- **II. Cost-Conscious Model Tiering**: `evaluate-path` (judgment +
  diff-authoring) runs `claude-sonnet-5`, matching rebase's
  conflict-resolution tier; comment-reply interpretation (a closed-set
  classification) runs `claude-haiku-4-5`, matching cleanup's summary
  tier. Detection, settle-tracking, health-check, and verification are
  entirely deterministic bash/`gh`/`jq` — no model runs at all for the
  common "nothing to do today" case, keeping the daily cadence cheap by
  default. Every agent step declares `--model` and `--max-turns`. **Pass.**
- **III. Simple, GitHub-Native Interaction**: The entire lifecycle is
  legible from the one open auto-update issue — detection, settle
  status, decision reasoning and sources, verification outcome, and
  final state (closed via `Closes #N` on merge, or flagged
  `auto-update:failed` and left open). Course correction is an ordinary
  issue comment (FR-012's question) or the pause repo variable — no new
  dashboard, no new CLI. **Pass.**
- **IV. Automation-First**: The one surviving manual step — clicking
  merge on the version-bump/revert PR — is the same manual step every
  other stage already reports explicitly via the PR itself and a
  lifecycle-issue comment; nothing about this feature assumes a human
  action happened without confirming it (the `pr-merged` trigger only
  fires once GitHub itself reports the merge). **Pass.**
- **V. Security (NON-NEGOTIABLE)**: Release-notes bodies and issue-comment
  replies are always framed and handled as data, never instructions
  (research.md's "evaluate-path" and "ambiguous-path resume" decisions).
  The comment-reply path verifies the commenter's identity before acting
  on their reply at all, reusing `clarify.yml`'s existing check. No web
  tools on either agent step. Only trusted refs (`main`, this feature's
  own generated branches) are ever checked out — never a fork PR head.
  **This stage never merges or approves its own PRs at any point** —
  every write that reaches `main` (a version bump or a revert) is a PR
  awaiting a human's own merge click; this is the precise point the
  requester's own auto-merge request (spec.md's Assumptions, final
  paragraph) was flagged back rather than silently granted or silently
  dropped. Auth via the same `wing-commander-bot` App token every other
  stage mints via `wing-commander-context`. **Pass.**
- **VI. Portability**: No new consuming-repo-owned config file is
  introduced (research.md); the two repo variables this feature adds
  follow the existing `WING_COMMANDER_<PURPOSE>_<KNOB>` naming
  convention documented in `docs/setup.md`. The stage resolves the
  repository it runs in the same way every other stage does
  (`${{ github.repository }}`, composite self-checkout at
  `github.job_workflow_sha`) — nothing hardcodes Wing Commander itself
  beyond the existing `charlesguse/wing-commander` pipeline-repo input
  default every other wrapper already carries. **Pass.**
- **VII. Two Interfaces**: The reusable stage (`auto-update-spec-kit.yml`)
  is `workflow_call`-only and reads no `github.event.*`/`vars.*`
  directly — the wrapper resolves all four trigger reasons into typed
  inputs (`trigger`, `pr-number`, `comment-id`, etc.) before calling it,
  matching every published stage's contract exactly (and deliberately
  *not* repeating `watchdog.yml`'s known, tracked deviation — issue
  #149 — of reading `vars.*` inside the stage itself). The pause
  kill-switch check lives in the wrapper's `if:`, not the stage's,
  applying the lesson `wing-commander-8-watchdog.yml` already learned
  (a stage-side pause check still bills for steps before discovering
  it's paused). **Pass.**

No violations — Complexity Tracking is not needed.

## Project Structure

### Documentation (this feature)

```text
specs/027-auto-update-spec-kit/
├── plan.md               # This file (/speckit-plan command output)
├── research.md            # Phase 0 output (/speckit-plan command)
├── data-model.md          # Phase 1 output (/speckit-plan command)
├── quickstart.md          # Phase 1 output (/speckit-plan command)
├── contracts/             # Phase 1 output (/speckit-plan command)
│   └── auto-update-spec-kit-workflow.md
└── tasks.md               # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
.github/
└── workflows/
    ├── auto-update-spec-kit.yml               # NEW — reusable stage (workflow_call only)
    └── wing-commander-auto-update-spec-kit.yml # NEW — thin wrapper: schedule + workflow_dispatch +
                                                  #       pull_request(closed) + issue_comment(created),
                                                  #       resolved to one typed `trigger` input

.specify/
└── init-options.json     # UPDATED by this feature's own version-bump PRs (speckit_version), not by this plan

docs/
└── architecture.md        # Gains a section documenting the new stage-pair (tasks-phase concern,
                            # not this plan, but the target design this plan fixes)
```

No `.specify/memory/*.json` file is added (research.md) — unlike
`015-pipeline-watchdog`'s `watchdog-guardrails.json`, this feature has no
maintainer-tunable allowlist; its verification-depth rule is a fixed
function of release type (FR-004/FR-014), and its two other knobs are
plain repo variables.

**Structure Decision**: Single-project CI/CD feature, no `src/`/`tests/`
split, matching every prior stage's own footprint. The primary artifact
is the new reusable stage `auto-update-spec-kit.yml` (jobs: `health-check`
→ `detect` → `settle` → `evaluate-path` → `prepare` → `verify` → `act`,
branching by the wrapper-supplied `trigger` input for the `pr-merged` and
`comment-reply` reasons) plus its wrapper. No existing workflow file
needs any job added or retired — this feature is additive-only at the
workflow-file level, touching `.specify/init-options.json` and the
`wing-commander-preflight` version constant only through its own
generated PRs, never directly by this plan or by a human editing this
plan's output.

## Complexity Tracking

> Not applicable — no Constitution Check violations.
