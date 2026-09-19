# Implementation Plan: Bot Credential Lifetime Across Long Agent Cycles

**Branch**: `052-agent-credential-lifetime` | **Date**: 2026-09-19 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/052-agent-credential-lifetime/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

Every agent-stage workflow mints the wing-commander-bot App credential once,
before its agent step, in a "Wing Commander context" step
(`.github/actions/wing-commander-context`). The credential is valid for one
hour; an agent step's only hard bound is a turn ceiling, not the clock, so a
healthy cycle can outlive the credential — every step after the agent that
still acts as the bot then fails with `HTTP 401: Bad credentials` (spec 049,
run 34804973881, lifecycle issue #326).

This plan re-establishes the credential once immediately after each agent
step, per the spec's own clarification (FR-002), via one mechanism applied
uniformly across all 8 agent-stage workflows (intake, clarify, plan, tasks,
implement, finalize, pr-conversation, auto-update's `e2e-stage` arm):
`wing-commander-context` gains an internal step that relays its token into a
job-scoped environment variable (`WC_BOT_TOKEN`); every bot-acting step in
the job — before or after the agent — reads that variable instead of the
composite's raw step output; and an `if: always()` step immediately after
each agent step re-invokes the composite, overwriting the variable so every
step below it sees the fresh value with no further per-step edits
(research.md D1). The same job also refreshes the authenticated git remote
`actions/checkout@v5` embedded at the first checkout, via `git remote
set-url` rather than a second checkout, so `git`-based composites (the
spec-meta read-back among them) are not left pointed at the same stale
credential (research.md D2). `implement.yml`'s three sequential agent steps
(`cycle` → `retry` → `progress`) each get their own refresh triple, and
`auto-update-spec-kit.yml`'s independent `scratch-token` gets the identical
treatment under its own relay variable (research.md D8).

Alongside the credential fix, two deterministic fixes close the blast
radius the source issue names: an `if: always()` step immediately after
each agent step publishes a prose-free `agent-ran`/`agent-conclusion` job
output, consumed by the six stages that already have a `stalled`/survivor
job (spec 041) so a post-agent failure is reported as what it is — the
agent ran, and a named step after it failed — never as "the stage failed
before it could run its own steps" (research.md D3, D4); and the 12
"Report over-budget agent run" call sites, already documented in place as
observability rather than failure but never enforced as such, gain
`continue-on-error: true` so a callout's own failure can no longer strand
the deterministic read-back and everything below it (research.md D5).

A new gate, `.github/scripts/verify-post-agent-credential-refresh.py`
(Gate 68 — renumbered from the provisional Gate 67 claimed at plan time,
which #401 landed first as `verify-auto-release-credential-step.py`), makes
the remedy durable: it fails when a
post-agent step reads a pre-agent-captured credential, when a second agent
step in a job has no re-establishment before it, or when a declared-
observability step in the audited region is not tolerated — and fails
loudly, rather than passing vacuously, when it cannot locate its 8-workflow
subject (research.md D6, Constitution Principle VIII).

The credential a running agent step pushes with (checked out under the
same, still-aging credential) is explicitly out of scope (FR-008) — recorded
as a residual risk in `docs/architecture.md`'s identity/chaining section and
at `implement.yml`'s read-back, with a follow-up issue to be filed when this
feature's PR opens (research.md D7, D9).

See [research.md](./research.md) for the full decision record — nine
decisions, none requiring further clarification beyond the spec's own three
resolved questions — [data-model.md](./data-model.md) for the env-var,
job-output, and gate-population shapes, and [contracts/](./contracts/) for
the composite amendment, the agent-ran signal, and the new gate's contract.

## Technical Context

**Language/Version**: YAML (GitHub Actions workflows and composite
actions), Bash (`run:` steps, matching every existing composite in this
fleet), Python 3 (`.github/scripts/verify-*.py`, matching every existing
gate script) — no new language introduced.

**Primary Dependencies**: `actions/create-github-app-token@v3` (existing,
unchanged inputs — reused for the post-agent re-mint), `actions/
checkout@v5` (existing, unchanged — its embedded credential is refreshed by
`git remote set-url`, not a second invocation), `gh`/`jq`/`git` (existing,
already the sole dependencies of the stall path this plan extends),
`wc_gate_registry.py` / `wc_shell_harness.py` (existing, reused for the new
gate's wiring and any step-body execution its self-test needs), PyYAML
(existing, used by every `verify-*.py` gate that parses workflow YAML).

**Storage**: `spec-meta.json` on each spec's long-lived branch (existing
mechanism, existing schema — no field added or renamed; the "stalled" value
this feature causes to be written more accurately is a value the schema
already has). No new persisted state — `WC_BOT_TOKEN`/`WC_SCRATCH_TOKEN`
and the `agent-ran`/`agent-conclusion` outputs are job-scoped and ephemeral.

**Testing**: New `.github/scripts/verify-post-agent-credential-refresh.py`,
wired into `.github/workflows/lint-workflows.yml` as a new PR-time step
(Gate 68), following the existing `verify-plan-tasks-cost-
line.py` live-tree-mutation self-test convention. `.github/scripts/
verify-implement-stall-notice-unchanged.py`'s existing pinned-step family is
checked for non-interference (this feature's stall-wording change lands on
the abnormal-termination branch, a different set of steps than that gate
pins) and extended with a new fixture for the `agent-ran == 'true'` wording
branch. `review-step-gating` and `container-shell-safety` skill passes are
run over the diff per CLAUDE.md, since this feature touches `continue-on-
error:` and `if:` at more than a dozen sites.

**Target Platform**: GitHub Actions, `ubuntu-latest` runner (gate scripts)
and whatever runner/container each of the 8 stages already targets — no new
runner requirement; every new step runs in the same job/runner context that
already exists.

**Project Type**: Single project — a GitHub Actions reusable-workflow
pipeline component; no application `src`/`tests` split applies.

**Performance Goals**: Zero additional agent turns or agent invocations
(FR-006, SC-007) — every new step is deterministic shell or a composite
re-invocation that mints a token, not a model call. Added cost per agent
stage run: one extra `create-github-app-token` mint (and, for `implement`,
up to three) plus a handful of trivial shell steps — accepted explicitly by
the spec's own Assumptions ("establishing a credential is cheap and fast
relative to an agent cycle").

**Constraints**:
- FR-002/FR-025/SC-008: no `workflow_call` input, secret, or output of any
  of the 8 published stage workflows, nor of `wing-commander-context`
  itself, changes. The env-var relay is a plumbing addition to the
  composite's internal `runs.steps`, not its `inputs:`/`outputs:` (research.md
  D1; Constitution Principle VII).
- FR-006/SC-007: no agent invocation or turn-budget change of any kind.
- FR-007/SC-005: all 8 stages changed in this one sweep; no stage deferred.
- FR-008/Out of Scope: the agent's own push credential is untouched;
  documented as a residual risk, not fixed.
- FR-014: the agent-ran signal carries no model-authored prose — enum
  values only (research.md D3).
- FR-009/SC-009: no live credential outlives the job that established it —
  the post-agent re-mint follows the same App-installation-token mechanism
  every mint already uses, with the same implicit expiry; nothing new is
  left for teardown to revoke.

**Scale/Scope**: One amended composite
(`.github/actions/wing-commander-context/action.yml`); one analogous inline
amendment to `auto-update-spec-kit.yml`'s `scratch-token` mint; 8 workflow
files gaining a post-agent refresh step (or, for `implement.yml`, three) and
an agent-ran signal step each; 12 call sites gaining `continue-on-error:
true`; 6 stages' existing "Determine which dependency did not start" steps
amended to read the new signal; one new gate script
(`verify-post-agent-credential-refresh.py`); two documentation sites
corrected (`clarify.yml`'s canonical comment block, `docs/architecture.md`'s
identity/chaining section) plus 7 pointer-comment updates.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Result |
|---|---|---|
| I. Guide — repo is its own first example | Built through the pipeline itself (issue #345 → this spec → this plan → tasks → implement), found by re-driving spec 049 through the same pipeline it hardens. | ✅ Pass |
| II. Cost-Conscious Model Tiering | This plan runs at `claude-sonnet-5` (planning-weight default, unchanged). The feature adds no agent invocation of any kind — every new/changed step is a deterministic credential mint, shell command, or Python gate script (FR-006). | ✅ Pass |
| III. Simple, GitHub-Native Interaction | The corrected stall notice (User Story 2) lands on the same lifecycle issue a maintainer already watches, through the existing `wing-commander-chain-stop-notice` composite's existing posting mechanism — no new interaction surface. | ✅ Pass |
| IV. Automation-First | This is a defect this principle exists to catch — a long, healthy agent cycle's own bookkeeping was silently failing and misreporting itself as never having started. This feature makes that reporting accurate and automatic, adding no new manual step. | ✅ Pass |
| V. Security — untrusted content is never instructions | No new untrusted-content path. The relay and refresh steps read only the App-installation-token mint (an existing trusted mechanism) and this repository's own step outputs — never `github.event.*` body text. Authentication continues to use the dedicated wing-commander-bot App, never widened to a PAT (FR-002 leaves the auth mechanism itself untouched). | ✅ Pass |
| VI. Portability — consuming repo owns its artifacts | No change to what this feature reads or writes outside the calling repository's own checkout and its own lifecycle issue; the new gate script lives under `.github/scripts/**`, resolved the same way every existing gate is. | ✅ Pass |
| VII. Two Interfaces — published contract vs. consuming instrument | The central constraint this plan is built around: `wing-commander-context`'s `inputs:`/`outputs:` are unchanged (research.md D1), and no stage workflow's `workflow_call` interface changes (FR-002/FR-025, checked explicitly in Technical Context above). The composite's one new internal step and the 8 stages' new internal steps are implementation detail behind an unchanged published surface — exactly the class of change Principle VII's adopters-pin-by-tag guarantee is meant to absorb for free. | ✅ Pass |
| VIII. A Green Check Means What It Says | This is what FR-020–FR-023 and User Story 4 restate at the spec level. The new gate is reachable through the registry (`wc_gate_registry.py`'s filename convention), runs the same subject with the same arguments locally and in CI (`run-local-gates.py` derives its invocation from `lint-workflows.yml`), is triggered by changes to the workflows/composite it inspects (existing `.github/workflows/**` / `.github/actions/**` path triggers already cover it), fails loudly rather than passing vacuously when it cannot locate its 8-file subject (research.md D6 check 4), and every failure branch it ships is exercised by a mutation-derived fixture in the same script (research.md D6, contracts/post-agent-credential-refresh-gate.md). | ✅ Pass |
| IX. Judgment that gates a durable action belongs in deterministic code | The agent-ran signal (FR-010–FR-015) is exactly this principle's own shape: whether a post-agent failure is reported as "never started" or "ran, then failed" is decided by a job output a deterministic step writes (research.md D3), never inferred by a prompt or by the stall notice's own judgment over ambiguous evidence. The new gate's three structural checks are likewise deterministic code, not a review checklist. | ✅ Pass |

**Post-Phase-1 re-check**: Unchanged. Phase 1 design (data-model.md,
contracts/, quickstart.md) confirms every new piece of state is job-scoped
and ephemeral (no new persisted schema), the only two new files under
`.github/actions/**`/`.github/scripts/**` are the amended composite (no
interface change) and the new gate script, and the six-stage stall-path
consumption (research.md D4) reuses spec 041's existing composite and
notice-rendering contract without amending its own `inputs:`/`outputs:`.

## Project Structure

### Documentation (this feature)

```text
specs/052-agent-credential-lifetime/
├── plan.md                                    # This file (/speckit-plan command output)
├── research.md                                # Phase 0 output (/speckit-plan command)
├── data-model.md                              # Phase 1 output (/speckit-plan command)
├── quickstart.md                              # Phase 1 output (/speckit-plan command)
├── contracts/                                 # Phase 1 output (/speckit-plan command)
│   ├── wing-commander-context-relay.md        # composite amendment + call-site convention
│   ├── agent-ran-signal.md                    # publication + stall-path consumption
│   └── post-agent-credential-refresh-gate.md  # new Gate 68's contract
├── checklists/
│   └── requirements.md                        # already present (intake stage output)
├── spec-meta.json
└── tasks.md                                   # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source code (repository root)

This repository is a GitHub Actions pipeline, not a conventional
library/service — there is no `src`/`tests` split. The real layout this
feature touches:

```text
.github/
├── actions/
│   └── wing-commander-context/
│       └── action.yml                       # + internal token-relay step
│                                             #   (WC_BOT_TOKEN via $GITHUB_ENV);
│                                             #   inputs:/outputs: unchanged
├── scripts/
│   ├── verify-post-agent-credential-refresh.py   # NEW — Gate 68
│   └── verify-implement-stall-notice-unchanged.py # + one fixture for the
│                                                    #   agent-ran=='true' wording
└── workflows/
    ├── lint-workflows.yml                   # + Gate 68 step
    ├── intake.yml                           # + post-agent refresh + agent-ran
    │                                         #   signal; token refs migrated to
    │                                         #   env.WC_BOT_TOKEN; over-budget
    │                                         #   callout + continue-on-error;
    │                                         #   stall-path reason amended
    ├── clarify.yml                          # same, PLUS the canonical
    │                                         #   credential-relay comment block
    ├── plan.yml                             # + post-agent refresh (both
    │                                         #   auto/pr branches); token refs
    │                                         #   migrated; over-budget callout
    │                                         #   tolerated. No stalled job to
    │                                         #   amend (research.md D4).
    ├── tasks.yml                            # same as plan.yml, both entry jobs
    │                                         #   (generate/approved); DOES have
    │                                         #   stalled jobs — stall-path
    │                                         #   reason amended in both
    ├── implement.yml                        # + THREE post-agent refresh
    │                                         #   triples (cycle/retry/progress);
    │                                         #   agent-ran signal after each;
    │                                         #   token refs migrated; three
    │                                         #   over-budget callouts tolerated;
    │                                         #   stall-path reason amended;
    │                                         #   FR-008 residual-risk comment
    │                                         #   at the read-back site
    ├── finalize.yml                         # same shape as intake.yml
    ├── pr-conversation.yml                  # same shape, both jobs with an
    │                                         #   agent step (classify-and-
    │                                         #   announce, act)
    └── auto-update-spec-kit.yml             # e2e-stage job only: + post-agent
                                              #   refresh for BOTH steps.ctx and
                                              #   steps.scratch-token; token refs
                                              #   migrated to env.WC_BOT_TOKEN /
                                              #   env.WC_SCRATCH_TOKEN; agent-ran
                                              #   signal published, no consumer

docs/
└── architecture.md                          # "Identity & chaining" section
                                              #   corrected: one-hour lifetime,
                                              #   the relay mechanism, the
                                              #   remote refresh, and the
                                              #   FR-008 residual-risk statement
```

**Structure Decision**: One amended composite (`wing-commander-context`,
interface unchanged), applied uniformly at 8 call sites via a shared
call-site convention (contracts/wing-commander-context-relay.md) rather
than 8 independent implementations of the same idea — consistent with
CLAUDE.md's single-home rule. The agent-ran signal (contracts/agent-ran-
signal.md) is published everywhere the credential relay is (uniform, cheap)
but consumed only where spec 041 already built a stall path to consume it
(`plan.yml` and `auto-update-spec-kit.yml`'s `e2e-stage` publish with no
reader — research.md D4). No new top-level directory, no change to any
stage's declared `workflow_call` surface, no change to the watchdog.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No violations — table intentionally omitted.
