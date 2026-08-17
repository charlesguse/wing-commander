# Implementation Plan: A Successful Agent Step Is No Longer Failed by the Wrong Turn Counter

**Branch**: `spec/037-agent-turn-budget-guard` | **Date**: 2026-08-17 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/037-agent-turn-budget-guard/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

`anthropics/claude-code-action` rejects a healthy, finished agent step
post-hoc by comparing `.num_turns` (1.0x-2.3x inflated, always upward)
against `--max-turns` — a defect already diagnosed once
(`auto-update-spec-kit.yml`'s `decide` site, 15→30) and re-hit 31 hours
later at `clarify.yml` (run 31918153816, #204), stranding $1.98 of
committed, correct work behind a red run with no lifecycle callout. This
plan splits the single overloaded `--max-turns` value into two: an
**intended turn budget** (unchanged public meaning — what a maintainer
tunes and what usage is reported against) and a **runaway ceiling**
(`intended × 2.5`, the literal value now handed to the CLI flag, sized
from this repository's own 1.0x-2.3x divergence sample), and introduces
one shared, transcript-only **agent run verdict** — healthy / exhausted /
failed / unclassifiable — computed once and consumed by every agent call
site, replacing eight hand-duplicated `is_error`/`subtype` checks and the
~11 sites that had no such check at all (issue #193's rescue wiring,
subsumed here per FR-016).

Mechanically: two new composite actions
(`wing-commander-turn-ceiling`, deterministic, fails fast if no bounded
intended budget is declared; `wing-commander-agent-verdict`, never fails
the step, reuses the exact turn-counting rule
`wing-commander-metrics-summary` already implements correctly — pulled
out to a shared script both composites call, closing the one drift risk
a second copy would open) are wired into all 19 enumerated call sites
(re-enumerated during this plan — see research.md R8 for the two
sites, `claude.yml`/`claude-code-review.yml`, deliberately excluded and
why). Each site's downstream gating moves from
`steps.<agent>.outcome == 'success'` (or a looser outcome-only check) to
`steps.<verdict>.outputs.verdict == 'healthy'`, with a uniform "fail
loud on non-healthy verdict" step (genuine failures still stop the run,
FR-003/FR-005) and, for stages that already post to the lifecycle issue,
a uniform "report over-budget" step (FR-017 — reaching the intended
budget is observability, not failure). `wing-commander-metrics-summary`
gains two optional passthrough display inputs so the verdict and its
turns appear in the same step-summary table it already renders (FR-012)
— no new decision logic there.

Coverage is enforced mechanically, not by convention: a new lint gate
(Gate 22) behaviorally tests the shared verdict script exactly like Gate
11 already tests turn-counting (mutation-tested), and a second new gate
(Gate 23) dynamically enumerates every `claude-code-action` step across
every workflow file that declares `--max-turns` and fails, naming the
site, when the ceiling composite is bypassed, the verdict composite is
missing, or a ceiling traces back to a literal instead of the ceiling
composite's output (User Story 3's "lowers a ceiling back to its
intended budget" case). A drafted upstream report to
`anthropics/claude-code-action` (FR-018) is committed alongside the code
as `upstream-report.md`, filing left to the maintainers.

## Technical Context

**Language/Version**: Bash (GitHub Actions `run:` steps and composite
`action.yml` files), YAML (workflow/action definitions), `jq` for JSON,
`awk` for the ceiling's arithmetic — identical toolchain to every
existing composite and gate in this repository; no new language.

**Primary Dependencies**: GitHub Actions (`workflow_call` composites and
reusable stages), `anthropics/claude-code-action@v1` (the 19 call
sites), `jq`, `awk`, `bash`, `python3`/`yaml`/`pyyaml` (lint-workflows.yml
gates), the repository's own `wing-commander-metrics-summary`,
`wing-commander-callout`, `wing-commander-lifecycle-gate` composites
(extended, not replaced) reached via the same
`.wing-commander-pipeline/` self-checkout every stage already performs
(constitution VII). Two brand-new composites
(`wing-commander-turn-ceiling`, `wing-commander-agent-verdict`) and one
new shared (non-action, non-gate) script
`.github/actions/_shared/count-turns.sh`, resolved by both composites via
`$GITHUB_ACTION_PATH`-relative paths — the first script shared across
composite actions in this repository (research.md R5); every prior
shared-logic case in this codebase duplicates and gates the duplicate in
sync (Gate 5, Gate 11) rather than sharing a script file, and this plan
documents why turn-counting specifically is worth the new pattern instead
of a third hand-kept copy.

**Storage**: No new persisted state. The only new on-disk artifact
outside `.github/` is `specs/037-agent-turn-budget-guard/upstream-report.md`
(FR-018/SC-010), which nothing in the pipeline reads at runtime.

**Testing**: No automated test suite exists for any pipeline stage in
this repository (confirmed by every prior plan — static validation via
`lint-workflows.yml`'s gates is the whole test surface). This feature
follows the exact discipline `verify-metrics-turn-accounting.py` (Gate
11) already established: extract the *shipped* script (now the shared
`count-turns.sh` plus the verdict composite's classification logic) and
execute it against synthetic transcripts covering FR-015's five
representative cases (healthy-but-rejected, genuinely errored, exhausted,
schema-violating — call-site layer, see research.md R2 — and
unreadable), with a mutation phase proving each check can fail. Coverage
(Gate 23) gets its own self-test, matching Gate 6/7/12's "the detector
actually detects" precedent.

**Target Platform**: GitHub Actions (`ubuntu-latest` runners); the
composites are pure `shell: bash` steps like every existing composite in
this repository — no platform-specific behavior beyond what
`wc_shell_harness.py`'s `resolve_bash()` already guards against for the
gate scripts that test them.

**Project Type**: Single project — CI/CD automation under
`.github/workflows/` and `.github/actions/`, extending existing
composites and lint gates. No frontend/backend split.

**Performance Goals**: SC-001/SC-003 — zero pipeline runs end red (and
zero lifecycle callouts are lost) for a healthy agent step whose counted
turns are within its intended budget, measured from adoption forward
against the two-in-31-hours baseline. Not latency-sensitive: the verdict
and ceiling composites are sub-second `jq`/`awk` reads of an
already-produced transcript file, adding negligible wall-clock to any
job (comparable to `wing-commander-metrics-summary`'s existing cost).

**Constraints**: The runaway ceiling must remain a real, bounded stop —
no agent step may run unbounded (constitution II) — so the ceiling
composite fails fast (unlike every other composite touched by this
feature) when no positive intended budget is supplied; a genuinely
runaway agent still spends at most `intended × 2.5` before the CLI cuts
it off (SC-008). The intended budget's public meaning must not change
for adopters pinning a release tag (constitution VII: `max-turns` is a
declared `workflow_call` input on 8 of the 19 sites' parent stages) —
this plan reinterprets what happens to that value internally, never its
name or its documented "what a maintainer tunes" semantics. Schema-shape
validation (FR-004) stays call-site-owned rather than centralized
(research.md R2) — the shared verdict answers "did the runtime say this
succeeded," never "does this specific site's JSON match its specific
schema." `implement.yml`'s existing git-state-based convergence/stall
loop is unchanged (research.md R13) — this feature exposes a new
machine-readable `over-budget`/`exhausted` signal for any stage to
consume, it does not rewire logic that already works independently of
turn counting.

**Scale/Scope**: 19 call sites across 11 workflow files
(`auto-update-spec-kit.yml` ×3, `clarify.yml` ×1, `cleanup.yml` ×1,
`finalize.yml` ×1, `implement.yml` ×3, `intake.yml` ×1, `plan.yml` ×2,
`pr-conversation.yml` ×2, `rebase.yml` ×1, `tasks.yml` ×2, `watchdog.yml`
×2); 2 new composite actions + 1 new shared script; 1 extended composite
(`wing-commander-metrics-summary`, additive-only inputs); 2 new
lint-workflows.yml gates (22, 23) plus 2 new `.github/scripts/verify-*.py`
files and their self-tests; 1 `docs/architecture.md` section extension
(no new file — existing convention is inline, not a catalog); 1 new
`specs/037-agent-turn-budget-guard/upstream-report.md`.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Guide**: This feature is itself built through the pipeline
  (#206 → this spec → this plan → tasks → implementation on
  `spec/037-agent-turn-budget-guard`), and its own landing run is the
  worked example: the same `clarify`/`plan`/`tasks`/`implement` stages
  this feature rewires will be running under the new verdict/ceiling
  wiring by the time this spec reaches `finalize`. **Pass.**
- **II. Cost-Conscious Model Tiering**: No agent invocation is added or
  removed by this feature — the same 19 sites keep the same models. Every
  site continues to declare an explicit model and, now doubly so, a
  bounded turn cap: the intended budget (unchanged) plus a ceiling that
  is *also* a hard, finite number (`intended × 2.5`, never unbounded).
  The two sites found with no `--max-turns` at all
  (`claude.yml`/`claude-code-review.yml`) are pre-existing, out of this
  feature's scope, and documented as a follow-up rather than silently
  folded in (research.md R8) — silently changing their behavior would be
  undeclared scope creep on a constitution gap this issue's evidence
  never touched. **Pass, with a documented follow-up recommendation.**
- **III. Simple, GitHub-Native Interaction**: A healthy-but-rejected run
  now produces the *same* lifecycle-issue callout it always should have
  (FR-002/SC-003) instead of silence; an over-budget-but-healthy run adds
  one more sentence to that same callout (FR-017) rather than a new
  surface. No new dashboard, no new CLI — the run's own step summary and
  the existing lifecycle issue remain the only two places state is
  legible. **Pass.**
- **IV. Automation-First**: Removes exactly one manual step this defect
  created — a maintainer noticing a red-but-healthy run and posting the
  callout by hand (the #204 worked example). Nothing about this feature
  introduces a new manual step. **Pass.**
- **V. Security (NON-NEGOTIABLE)**: The verdict is derived solely from
  the already-uploaded transcript file (FR-014) — no new network call, no
  new agent invocation, no elevated permission. The transcript is treated
  as data the whole way through (parsed with `jq`, never interpolated
  into a shell command or a prompt). No change to which refs are checked
  out, which App mints tokens, or who may trigger a stage. **Pass.**
- **VI. Portability**: The two new composites and the shared script live
  under `.github/actions/` in this repository, resolved through the same
  self-checkout (`.wing-commander-pipeline/`) every existing composite
  already uses — an adopter pinning a release tag gets the new
  composites for free with no adoption action required, exactly like
  `wing-commander-metrics-summary` today. No consuming-repo-owned file is
  read or required. **Pass.**
- **VII. Two Interfaces**: The `max-turns` `workflow_call` input on the
  8 published stages that declare it keeps its name, type, and default —
  its *meaning* (intended budget vs. literal ceiling) was always
  underspecified at the interface level (the issue itself is proof:
  nothing in the published contract said which counter it capped), so
  clarifying it internally is not a breaking change to the declared
  surface. No published stage gains, loses, or renames an input as part
  of this feature. The two new composites and the shared script are
  themselves unpublished implementation detail, same status as
  `wing-commander-tool-args`/`wing-commander-preflight` today. **Pass.**

No violations — Complexity Tracking is not needed.

## Project Structure

### Documentation (this feature)

```text
specs/037-agent-turn-budget-guard/
├── plan.md                    # This file (/speckit-plan command output)
├── research.md                 # Phase 0 output (/speckit-plan command)
├── data-model.md                # Phase 1 output (/speckit-plan command)
├── quickstart.md                # Phase 1 output (/speckit-plan command)
├── upstream-report.md           # FR-018/SC-010 — drafted report to anthropics/claude-code-action
├── contracts/                   # Phase 1 output (/speckit-plan command)
│   ├── agent-verdict-composite.md   # wing-commander-turn-ceiling, wing-commander-agent-verdict,
│   │                                  # and the metrics-summary extension
│   └── coverage-gate.md             # Gate 22 (verdict self-test) and Gate 23 (coverage enumeration)
└── tasks.md                     # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
.github/
├── actions/
│   ├── _shared/
│   │   └── count-turns.sh                       # NEW — extracted from wing-commander-metrics-summary;
│   │                                               #       both new composites and metrics-summary call it
│   │                                               #       via a $GITHUB_ACTION_PATH-relative path
│   ├── wing-commander-turn-ceiling/
│   │   └── action.yml                            # NEW — intended-turns -> ceiling, fails fast if unbounded
│   ├── wing-commander-agent-verdict/
│   │   └── action.yml                            # NEW — transcript -> verdict/reason/counted+reported turns/
│   │                                               #       over-budget; never fails the step itself
│   └── wing-commander-metrics-summary/
│       └── action.yml                            # EXTENDED — two new optional display inputs (verdict,
│                                                    #            verdict-reason); counting logic now calls
│                                                    #            the shared script instead of inlining it
├── scripts/
│   ├── verify-agent-verdict.py                   # NEW — Gate 22, same discipline as verify-metrics-turn-accounting.py
│   ├── verify-gate-23.py                         # NEW — Gate 23's self-test (matches verify-gate-6/7/12.py)
│   └── verify-metrics-turn-accounting.py         # UPDATED — tests the shared script, not an inlined copy
├── workflows/
│   ├── lint-workflows.yml                        # UPDATED — Gate 22, Gate 23 added
│   ├── auto-update-spec-kit.yml                  # UPDATED — 3 call sites rewired
│   ├── clarify.yml                                # UPDATED — 1 call site rewired
│   ├── cleanup.yml                                # UPDATED — 1 call site rewired
│   ├── finalize.yml                               # UPDATED — 1 call site rewired
│   ├── implement.yml                              # UPDATED — 3 call sites rewired
│   ├── intake.yml                                 # UPDATED — 1 call site rewired
│   ├── plan.yml                                   # UPDATED — 2 call sites rewired
│   ├── pr-conversation.yml                        # UPDATED — 2 call sites rewired (also gains metrics-summary,
│                                                    #            absent today)
│   ├── rebase.yml                                 # UPDATED — 1 call site rewired
│   ├── tasks.yml                                  # UPDATED — 2 call sites rewired
│   └── watchdog.yml                               # UPDATED — 2 call sites rewired
docs/
└── architecture.md                                # UPDATED — extends the existing turn-counter-divergence
                                                      #            paragraph (lines ~172-197) with the
                                                      #            intended-budget/ceiling split and gates 22/23
```

**Structure Decision**: Single-project CI/CD feature, additive-plus-rewire
shape matching `026-configurable-tool-lists` (a shared composite consumed
by every call site) crossed with `009-agent-metrics`'s "one composite,
tested like a gate" precedent. No `src/`/`tests/` split — the pipeline
has never had one. The two new composites are the only genuinely new
components; everything else is either a small, mechanical per-site rewire
(19 sites, same shape each time — see contracts/agent-verdict-composite.md
for the exact before/after step pattern) or a new lint gate following an
established, already-precedented template (Gate 11's shipped-script
extraction for Gate 22; Gate 6/7/12's dynamic enumeration + self-test for
Gate 23).

## Complexity Tracking

> Not applicable — no Constitution Check violations.
