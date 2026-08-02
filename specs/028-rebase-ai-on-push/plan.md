# Implementation Plan: Auto-Rebase AI Conflict Resolution on Push-Triggered Rebases

**Branch**: `028-rebase-ai-on-push` | **Date**: 2026-08-02 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/028-rebase-ai-on-push/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

`anthropics/claude-code-action@v1` rejects the `push` event outright
("Unsupported event type: push"), and `github.event_name` propagates
unchanged through a `workflow_call` boundary — a reusable workflow invoked
from a push-triggered caller still sees `push`, not `workflow_call` — so the
conflict-resolution agent step inside `rebase.yml`'s matrixed `rebase` job
fails immediately on every run the wrapper's `push: {branches: [main]}`
trigger starts (FR-001). The fix stays entirely inside
`wing-commander-rebase.yml`, the repository's own consuming-instrument
wrapper (constitution VII), and does not touch `rebase.yml`, the published
`workflow_call`-only stage contract (FR-006, FR-007): the wrapper's single
`rebase` job splits into two. A new `redispatch` job runs only on
`github.event_name == 'push'` (keeping today's `!endsWith(github.actor,
'[bot]')` loop guard, since that guard's whole purpose is push-specific) and
calls `gh workflow run wing-commander-rebase.yml` — `workflow_dispatch`,
already proven to reach a `claude-code-action` step successfully in this
repository's own `implement`/`finalize`/`plan`/`tasks` wrappers — instead of
invoking the reusable stage directly. The renamed `rebase` job keeps the
unchanged `uses: ./.github/workflows/rebase.yml` call but restricts its
`if:` to `github.event_name == 'schedule' || github.event_name ==
'workflow_dispatch'` — both events already empirically proven to reach a
`claude-code-action` step in this repository (`schedule` via
`auto-update-spec-kit.yml`'s `evaluate-path` job; `workflow_dispatch` via
four other wrapper/stage pairs). A push now takes one extra
`workflow_dispatch` hop before reaching the stage, but the stage itself, its
inputs, and its behavior are byte-for-byte unchanged (FR-002, FR-003,
FR-004, FR-005) — the fix changes *how the run gets there*, not what runs.
`on:` gains `workflow_dispatch: {}` so the redispatch target exists.

A new Gate 6 in `lint-workflows.yml` closes the recurrence path (FR-008
through FR-011): for every wrapper job that locally `uses:` a reusable
stage, resolve that stage and check whether any of its jobs contains a
`claude-code-action` step; if so, compute which of the wrapper's declared
`on:` events can reach that job by reading `github.event_name ==
'<event>'`/`!= '<event>'` clauses out of the job's own `if:` (a job with no
recognizable clause is conservatively treated as reachable by every
wrapper-declared event — fail toward flagging, never toward silently
passing); flag any reachable event outside a fixed, conservative supported
list encoded in the gate itself (`issues`, `issue_comment`, `pull_request`,
`workflow_dispatch`, `workflow_run`, `schedule` — every event this
repository's production wrappers already exercise against a
`claude-code-action` step today). This is deliberately the same static,
regex-over-YAML-text style Gates 2/3/5 already use, not a full GitHub
Actions expression evaluator.

Two documentation deltas travel with the code change so a maintainer or
adopter reading them isn't misled by a now-stale description: `docs/
architecture.md`'s "Rebase" section trigger line, and `docs/adoption.md`'s
§8 copy-paste wrapper template (currently ships the *exact* pre-fix
pattern to every adopter who follows it).

## Technical Context

**Language/Version**: GitHub Actions workflow YAML (`ubuntu-latest` runner
defaults) + Bash (`gh workflow run`, unchanged `git`/`jq` in `rebase.yml`,
untouched) + Python 3 (`lint-workflows.yml`'s existing inline
`python3 - <<'PYEOF'` heredoc convention, extended with one more gate)

**Primary Dependencies**: `gh` CLI (already available on `ubuntu-latest`,
already used by every other wrapper's stage-chaining `gh workflow run` call
— docs/architecture.md "Identity & chaining"); `anthropics/claude-code-action@v1`
(unchanged pin, unchanged inputs — the fix works around its event-type
restriction rather than modifying it, per FR-007); `PyYAML` (already a
dependency of every existing `lint-workflows.yml` gate)

**Storage**: N/A — no new persisted state; `spec-meta.json`'s existing
`stage`/`issue`/`spec_dir` fields are read the same way `discover` already
reads them (unchanged)

**Testing**: No unit-test framework for workflow YAML in this repo
(dogfooding per constitution I, consistent with `specs/025-lint-composite-actions/`
and `specs/020-fix-watchdog/`). Two different verification modes apply
here, matching the spec's two user-story shapes: (1) the wrapper fix is
verified by a **live, deliberately induced merge conflict on the real push
path** (FR-012 explicitly forbids relying on source inspection alone —
see quickstart.md); (2) the new Gate 6 is verified the same way Gates 2/3/5
already are — a scenario-based PR against a throwaway branch that
introduces (then removes) the exact defect class the gate exists to catch

**Target Platform**: GitHub Actions, `ubuntu-latest` runners, this
repository's own `wing-commander-rebase.yml` (consuming-instrument wrapper,
constitution VII) and `lint-workflows.yml` (repo-local guard, no
`workflow_call` trigger, not part of the published stage contract)

**Project Type**: Single project — a GitHub Actions pipeline; no
application `src/`/`tests/` split applies

**Performance Goals**: Not applicable per the spec's success criteria. The
fix adds one `gh workflow run` API call and one extra queued run per
push-triggered rebase cycle (previously: one run; now: a lightweight
redispatch run plus the real rebase run) — not a latency-sensitive path,
and the existing nightly `schedule` trigger is unaffected. Gate 6 adds one
more bounded static-analysis pass over the same already-loaded workflow
YAML set Gates 2/3 already parse.

**Constraints**: Constitution II (no new agent step or model tier — the
existing `rebase.yml` conflict-resolution step's model/turn-budget inputs
are unchanged; Gate 6 is pure deterministic static analysis like Gates
2/3/5, no LLM call); Constitution V (least privilege — the new `redispatch`
job needs only `actions: write` to call `gh workflow run`, nothing else;
Gate 6's job needs only the `contents: read` the `lint` job already has);
Constitution VI/VII (the published stage contract `rebase.yml` — its
inputs, secrets, outputs, and `on: workflow_call` trigger — is completely
unchanged; every change lives in the consuming-instrument wrapper
`wing-commander-rebase.yml` plus the repo-local `lint-workflows.yml` guard,
matching FR-006's "wrapper only" scope and FR-007's "no third-party
change"); FR-005 (the existing abort/escalate safety behavior in
`rebase.yml` must not regress — it isn't touched at all, so this holds by
construction, not by re-verification of its internals)

**Scale/Scope**: One wrapper file (`wing-commander-rebase.yml`) gains one
job and a narrowed `if:` on its existing job; one guard file
(`lint-workflows.yml`) gains one gate, scoped to the wrapper↔stage
`uses: ./.github/workflows/*.yml` pattern Gate 3 already detects (not every
`claude-code-action`-bearing file in the repo — see research.md R7 for why
`claude.yml`/`claude-code-review.yml`, which embed the agent step directly
rather than through a wrapper/stage split, are out of this gate's scope);
two documentation files gain a trigger-description/example update each.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Result |
|---|---|---|
| I. Guide — the repo is its own first example | Fix flows through spec → plan → tasks → implement → converge, against a real issue (#72) and a real lifecycle issue; SC-002 requires the fix to be proven against a genuine induced conflict in this very repository, not merely asserted | PASS |
| II. Cost-conscious model tiering | No agent step is added, removed, or retiered — `rebase.yml`'s conflict-resolution step keeps its existing `claude-sonnet-5` default and `--max-turns` budget untouched; Gate 6 is deterministic static analysis, no LLM call | PASS |
| III. Simple, GitHub-native interaction | The escalation/lifecycle-issue behavior (User Story 3) is untouched; Gate 6 failures surface as `::error` annotations on the pull request, identical in shape to Gates 2/3/5 — no new external surface | PASS |
| IV. Automation-first | Restores an automatic resolution attempt that today silently degrades to full escalation on the dominant trigger; no new manual step is introduced — the extra `workflow_dispatch` hop is itself automatic (`redispatch` job) | PASS |
| V. Security — untrusted content is never instructions | No new tool allowlist, no new write surface for the agent step (unchanged `rebase.yml` prompt and allowed-tools). The new `redispatch` job runs no agent and reads no issue/PR/comment body — it only calls `gh workflow run` with no user-controlled input. Gate 6 reads only repository-controlled workflow YAML already in the checkout, same as Gates 2/3/5 | PASS |
| VI. Portability | `rebase.yml`, the published stage adopters pin by tag, is untouched — zero behavior change for any adopter who hasn't copied this repo's wrapper pattern; `lint-workflows.yml` is this repository's own guard, not a published artifact | PASS |
| VII. Two Interfaces | This is the principle's worked example: the defect lived in the published/consuming split (a wrapper's trigger choice silently broke a published stage's agent step), and the fix is entirely a consuming-instrument (wrapper) change — the published contract's compatibility surface (inputs, secrets, outputs, `on: workflow_call`) does not move | PASS |

No violations — Complexity Tracking is not needed.

## Project Structure

### Documentation (this feature)

```text
specs/028-rebase-ai-on-push/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md         # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
│   ├── rebase-wrapper-delta.md
│   └── workflow-lint-gate-6.md
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

This repository has no application `src/`/`tests/` split — it *is* a
GitHub Actions pipeline. The feature's changes are confined to:

```text
.github/workflows/
├── wing-commander-rebase.yml   # on: gains workflow_dispatch: {}; the single
│                                # `rebase` job splits into `redispatch`
│                                # (push-only, loop-guarded, `gh workflow run`
│                                # itself) and a narrowed `rebase` job
│                                # (`if:` allow-lists schedule/workflow_dispatch,
│                                # unchanged `uses: ./.github/workflows/rebase.yml`
│                                # call and inputs)
├── rebase.yml                  # UNCHANGED — published stage contract;
│                                # constitution VII, FR-006, FR-007
└── lint-workflows.yml          # gains Gate 6: agent-bearing wrapper ↔
                                 # supported-event check, alongside the
                                 # existing `lint` job's Gates 2/3/5

docs/
├── architecture.md             # "Rebase" section trigger line updated
│                                # (push + nightly + workflow_dispatch hop)
└── adoption.md                 # §8 wrapper copy-paste template updated to
                                 # the fixed pattern — today it ships adopters
                                 # the exact pre-fix defect

specs/028-rebase-ai-on-push/    # this feature's own spec-kit artifacts
```

**Structure Decision**: Single project, no option-1/2/3 split applies.
Every behavioral change lives inside `wing-commander-rebase.yml` (job
split) and `lint-workflows.yml` (new gate); `rebase.yml` — the published,
adopter-pinned stage — is not modified, keeping the fix inside the
consuming-instrument layer constitution VII names. The two documentation
files are updated to stay consistent with the wrapper's new shape, not
because any functional requirement names them directly.

## Complexity Tracking

> Not applicable — Constitution Check has no violations to justify.
