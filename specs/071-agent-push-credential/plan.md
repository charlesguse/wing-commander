# Implementation Plan: The Agent's Own Push Credential Outlives Its Cycle

**Branch**: `spec/071-agent-push-credential` | **Date**: 2026-09-26 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/071-agent-push-credential/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

Spec 052 re-established the wing-commander-bot App credential once,
immediately after each agent step, so every *deterministic* step following
an agent step stays credentialed for as long as a cycle runs. It
deliberately left the credential the *running* agent pushes with out of
scope (FR-008) — that credential is the one `actions/checkout@v5` embeds at
job start, fixed for the life of the job, and it still expires at minute
sixty regardless of how long a healthy cycle keeps committing.

This plan closes that gap with the mechanism the spec's own Clarification
selected: a git credential helper that resolves a fresh App installation
token at the moment of every push, so the agent's own `git push` calls need
no change in behaviour to keep succeeding (research.md D1–D5). The helper
is a small shell script (`mint-credential.sh`, signing its own GitHub App
JWT with `openssl` and minting via the REST API directly, since the
existing `actions/create-github-app-token` JS action cannot be invoked
mid-push by git) living beside one new composite,
`wing-commander-agent-push-credential`, that every in-scope stage's
agent-bearing job calls once, before its agent step, parameterized by
owner/repo so the same composite also covers the end-to-end arm's scratch
repository (FR-008, research.md D9).

Two more mechanisms round out the spec's five user stories. A short,
single-homed prompt addition (research.md D7) tells an agent to recognise
the credential-expiry signature (or the helper's own mint-failure
signature) and stop retrying a doomed push after two attempts, satisfying
FR-010–FR-014 without asking a model to judge anything it cannot already
observe literally. A new deterministic step,
`wing-commander-publish-stranded-commits`, runs immediately after each
agent step's existing post-agent credential re-mint and pushes whatever
commits are still locally ahead of `origin` — replacing what research.md
D8 found to be an *incidental* rescue today (a later agent step's own push
happening to carry stranded work with it) with a rescue that runs whether
or not a later agent step ever does, closing FR-015–FR-018 for the cases
User Story 4 names (a killed step, a runaway-ceiling cutoff) that today's
incidental path cannot reach.

A new gate, provisionally **Gate 99** (`verify-agent-push-credential-
helper.py` — renumbering possible if another PR claims 99 first, per spec
052's own documented precedent), makes the remedy durable: it fails when
an in-scope agent step lacks the credential-helper installation or the
stranded-commit publish step, when a second, independently-authored copy
of the minting shell appears outside its one composite, or when it cannot
locate its 8-workflow subject at all (research.md D10, Constitution
Principle VIII).

FR-023's documentation consolidation replaces the FR-008 residual-risk
paragraph in `docs/architecture.md` and its workflow-comment pointer with
one canonical statement describing the mechanism that actually ships
(research.md D11); FR-009/SC-010 need no new teardown step, since every
credential this feature mints is the same already-expiring App
installation-token kind the pipeline has always used (research.md D12).

See [research.md](./research.md) for the full decision record (twelve
decisions, none requiring further clarification beyond the spec's own two
resolved questions), [data-model.md](./data-model.md) for the composite,
script, and gate-registry shapes, and [contracts/](./contracts/) for the
credential-helper composite's interface, the stranded-commit publish
step's contract, and the new gate's contract.

## Technical Context

**Language/Version**: YAML (GitHub Actions workflows and composite
actions), Bash (`run:` steps and the new `mint-credential.sh`, matching
every existing composite in this fleet), Python 3
(`.github/scripts/verify-*.py`, matching every existing gate script) — no
new language introduced.

**Primary Dependencies**: `openssl` (new — JWT signing for the on-demand
mint; verified present as part of Phase 1's quickstart rather than assumed
silently, research.md D2), `curl`/`jq` (existing, already load-bearing in
this repository's own OIDC-token-decoding step in `implement.yml`), `git`
(existing — the credential helper is wired through `git config
credential.https://github.com.helper`, a stock git mechanism, no new git
version requirement), `actions/checkout@v5` (existing, unchanged — its
embedded extraheader is cleared the same way `wing-commander-refresh-
remote` already clears it), `wc_gate_registry.py` / `wc_shell_harness.py`
(existing, reused for the new gate's wiring and its behavioural
companion's script execution), PyYAML (existing, used by every
`verify-*.py` gate that parses workflow YAML).

**Storage**: `spec-meta.json` on each spec's long-lived branch (existing
mechanism, existing schema — no field added or renamed). No new persisted
state: the installation-id cache (research.md D3) and the staged
private-key file (research.md D4) are both job-scoped files under
`$RUNNER_TEMP`, gone when the runner is destroyed, and the `WC_AGENT_PUSH_*`
environment variables are job-scoped like `WC_BOT_TOKEN` already is.

**Testing**: New `.github/scripts/verify-agent-push-credential-helper.py`
(Gate 99, structural) and its behavioural companion (Gate 100,
provisionally, following the Gate 68/69 split), both wired into
`.github/workflows/lint-workflows.yml` as new PR-time steps.
`verify-implement-stall-notice-unchanged.py`'s existing pinned-step family
is checked for non-interference (the new stranded-commit publish step
lands beside, not inside, the pinned steps that gate already covers) and
extended with a fixture for the "commits published" line's presence/
absence branch. `review-step-gating` and `container-shell-safety` skill
passes run over the diff per CLAUDE.md, since this feature adds
`continue-on-error:` and `if:` conditions at 16 new call sites (2 per
in-scope stage × 8) and a `run:` step (`mint-credential.sh`'s invocation
site) inside jobs that carry a `container:` block.

**Target Platform**: GitHub Actions, `ubuntu-latest` runner (gate scripts)
and whatever runner/container each of the 8 stages already targets — no
new runner requirement beyond `openssl`'s presence, which this plan
verifies rather than assumes (quickstart.md).

**Project Type**: Single project — a GitHub Actions reusable-workflow
pipeline component; no application `src`/`tests` split applies.

**Performance Goals**: Zero additional agent turns or agent invocations
(FR-005, SC-003) — every new step is deterministic shell, a JWT signed and
exchanged over HTTPS, or a prompt paragraph the agent reads once; none of
it is a model call. Added cost per in-scope agent step: one installation-
id lookup (cached per job, research.md D3) plus one token mint per `git
push` the agent actually makes (twelve to eighteen in the observed cycles,
explicitly accepted by the spec's own Assumptions) plus one deterministic
stranded-commit push attempt per agent step.

**Constraints**:
- FR-002/FR-025/SC-009: no `workflow_call` input, secret, or output of any
  of the 8 published stage workflows changes. The credential helper and
  the stranded-commit publisher are new internal steps inside each job,
  not new declared inputs (research.md D5; Constitution Principle VII).
- FR-005/SC-003: no agent invocation or turn-budget change of any kind;
  the retry-bound guidance (research.md D7) is prose inside an existing
  `prompt:` block, not a new tool.
- FR-007/SC-007: all 8 stages' push-capable agent steps changed in this one
  sweep; FR-025 exempts only agent steps that never push, and that
  exemption must be checkable (Gate 99), not asserted in prose alone.
- FR-008: the end-to-end arm's scratch-repository push is covered by the
  same composite, parameterized (research.md D9) — not a second
  mechanism.
- FR-019: the stranded-commit publish step (research.md D8) inherits the
  same `!cancelled()` gating spec 052's post-agent refresh already carries;
  this feature does not widen it.
- FR-009/SC-010: no live credential outlives the job — every mint this
  feature adds is the same expiring App-installation-token kind the
  pipeline already uses, with the same implicit-expiry teardown behaviour
  (research.md D12).

**Scale/Scope**: One new composite pair
(`.github/actions/wing-commander-agent-push-credential/{action.yml,
mint-credential.sh}`); one new composite
(`.github/actions/wing-commander-publish-stranded-commits/`); one new
composite (`.github/actions/wing-commander-agent-push-credential-status/`)
for FR-006's mint-failure attribution; 8 workflow files each gaining, per
push-capable agent step, one credential-helper installation call, one
stranded-commit publish call, and one short prompt paragraph
(`implement.yml` ×3 for its cycle/retry/progress steps); two new gate
scripts (`verify-agent-push-credential-helper.py` and its behavioural
companion); two documentation sites corrected
(`docs/architecture.md`'s Identity & chaining section,
`implement.yml`'s FR-008 pointer comment) plus the canonical prompt-
paragraph pointer comments at the other 7 stages' call sites.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Result |
|---|---|---|
| I. Guide — repo is its own first example | Built through the pipeline itself (issue #402 → issue #545 → this spec → this plan → tasks → implement), the direct follow-up spec 052's own FR-008 required be filed. | ✅ Pass |
| II. Cost-Conscious Model Tiering | This plan runs at `claude-sonnet-5` (planning-weight default, unchanged). The feature adds no agent invocation of any kind — every new/changed step is a deterministic JWT sign-and-mint, a shell push, or a Python gate script; the one prompt addition is read, not invoked (FR-005). | ✅ Pass |
| III. Simple, GitHub-Native Interaction | The stranded-commit publish step's "commits published" line lands on the existing lifecycle-issue callouts spec 041 already renders — no new interaction surface. | ✅ Pass |
| IV. Automation-First | This is the residual risk spec 052 recorded and issue #402 tracked precisely because it was NOT yet automated — an agent whose long cycle silently lost pushable work needed a human to notice the stall notice's wrong wording. This feature removes that manual-attention dependency. | ✅ Pass |
| V. Security — untrusted content is never instructions | No new untrusted-content path. The credential helper reads only this repository's own App private key (an existing trusted secret) and mints against this repository's own installation; it never reads `github.event.*` body text. Authentication continues through the dedicated wing-commander-bot App, never widened to a PAT (Out of Scope; the mechanism this plan adds mints the *same kind* of App-scoped token `wing-commander-context` already does, just more often and closer to the point of use). | ✅ Pass |
| VI. Portability — consuming repo owns its artifacts | No change to what this feature reads or writes outside the calling repository's own checkout, its own App installation, and its own lifecycle issue; the new composites and gate script live under `.github/actions/**` / `.github/scripts/**`, resolved the same way every existing one is. | ✅ Pass |
| VII. Two Interfaces — published contract vs. consuming instrument | No stage workflow's `workflow_call` interface changes (FR-002/FR-025, Technical Context above). The new composites' inputs/outputs are themselves new (they did not exist before), but they are internal call-site plumbing inside each stage's job, never a `workflow_call` input/secret/output — the exact class of change Principle VII's adopters-pin-by-tag guarantee absorbs for free. | ✅ Pass |
| VIII. A Green Check Means What It Says | This is what FR-020–FR-023 and User Story 5 restate at the spec level. Gate 99 is reachable through the registry (`wc_gate_registry.py`'s filename convention), runs the same subject with the same arguments locally and in CI (`run-local-gates.py` derives its invocation from `lint-workflows.yml`), is triggered by changes to the workflows/composites it inspects (existing `.github/workflows/**` / `.github/actions/**` path triggers already cover it), fails loudly rather than passing vacuously when it cannot locate its 8-file subject (research.md D10 check 4), and every failure branch it ships is exercised by a fixture (research.md D10, contracts/agent-push-credential-gate.md). | ✅ Pass |
| IX. Judgment that gates a durable action belongs in deterministic code | The retry-bound guidance (FR-010–FR-014) is deliberately NOT a new judgment: the signature the agent keys on is a literal string match, given to it as a fact, exactly the shape Out of Scope requires ("nothing in this feature asks a model to decide whether a credential expired"). The mint-failure attribution (FR-006, research.md D6) and the stranded-commit count (FR-016/FR-017, research.md D8) are both deterministic code reading a literal signature or a `git rev-list --count`, never a model's account of what happened. | ✅ Pass |

**Post-Phase-1 re-check**: Unchanged. Phase 1 design (data-model.md,
contracts/, quickstart.md) confirms every new piece of state is job-scoped
and ephemeral (no new persisted schema, no new `workflow_call` surface),
and the two new gates' fixtures follow spec 052's own established
mutation-over-live-tree convention rather than introducing a second
fixture style.

## Project Structure

### Documentation (this feature)

```text
specs/071-agent-push-credential/
├── plan.md                                    # This file (/speckit-plan command output)
├── research.md                                # Phase 0 output (/speckit-plan command)
├── data-model.md                              # Phase 1 output (/speckit-plan command)
├── quickstart.md                              # Phase 1 output (/speckit-plan command)
├── contracts/                                 # Phase 1 output (/speckit-plan command)
│   ├── agent-push-credential-helper.md        # composite + mint-credential.sh contract
│   ├── stranded-commit-publish.md             # publish step's contract
│   └── agent-push-credential-gate.md          # new Gate 99/100's contract
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
│   ├── wing-commander-agent-push-credential/
│   │   ├── action.yml                       # NEW — stages the App key,
│   │   │                                    #   exports WC_AGENT_PUSH_*,
│   │   │                                    #   wires credential.helper
│   │   └── mint-credential.sh               # NEW — JWT sign + mint,
│   │                                        #   invoked by git itself
│   ├── wing-commander-publish-stranded-commits/
│   │   └── action.yml                       # NEW — deterministic push of
│   │                                        #   whatever is locally ahead
│   ├── wing-commander-agent-push-credential-status/
│   │   └── action.yml                       # NEW — FR-006 attribution,
│   │                                        #   mirrors wing-commander-
│   │                                        #   post-agent-credential-status
│   └── wing-commander-refresh-remote/       # unchanged — still used for
│                                             #   spec 052's own post-agent
│                                             #   deterministic-step refresh
├── scripts/
│   ├── verify-agent-push-credential-helper.py     # NEW — Gate 99
│   └── verify-agent-push-credential-shell.py      # NEW — Gate 100
│                                                    #   (behavioural companion)
└── workflows/
    ├── lint-workflows.yml                   # + Gate 99 + Gate 100 steps
    ├── intake.yml                           # + credential-helper install,
    │                                        #   stranded-commit publish,
    │                                        #   prompt paragraph (if its
    │                                        #   agent step pushes)
    ├── clarify.yml                          # same, PLUS the canonical
    │                                        #   retry-bound prompt-paragraph
    │                                        #   comment block
    ├── plan.yml                             # same shape, both entry jobs
    ├── tasks.yml                            # same shape, both entry jobs
    ├── implement.yml                        # + THREE credential-helper +
    │                                        #   stranded-commit-publish
    │                                        #   pairs (cycle/retry/
    │                                        #   progress); FR-008
    │                                        #   residual-risk comment
    │                                        #   replaced with a pointer to
    │                                        #   the corrected architecture
    │                                        #   doc section
    ├── finalize.yml                         # same shape as intake.yml
    ├── pr-conversation.yml                  # same shape, both agent jobs
    └── auto-update-spec-kit.yml             # e2e-stage job only: the
                                              #   scratch-token arm calls
                                              #   the SAME composite with
                                              #   scratch owner/repo inputs
                                              #   (research.md D9)

docs/
└── architecture.md                          # "Identity & chaining" section
                                              #   gains the credential-
                                              #   helper mechanism paragraph
                                              #   and drops the FR-008
                                              #   residual-risk sentence,
                                              #   replacing the pointer to
                                              #   issue #402 with a
                                              #   statement that it is
                                              #   closed by this feature
```

**Structure Decision**: Three new composites, each a single home for one
concern (credential minting, stranded-commit publication, mint-failure
attribution), applied uniformly at every in-scope call site rather than
duplicated per stage — consistent with CLAUDE.md's single-home rule and
this repository's own precedent (`wing-commander-refresh-remote`,
`wing-commander-agent-ran-signal`, `wing-commander-post-agent-credential-
status` are each exactly this shape). The retry-bound prompt paragraph is
published everywhere an agent step's allowed-tools include `git push`
(uniform, cheap — FR-025 exempts only agent steps that cannot push at
all). No new top-level directory, no change to any stage's declared
`workflow_call` surface, no change to the watchdog.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No violations — table intentionally omitted.
