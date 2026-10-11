# Implementation Plan: Haiku 5.5 Tier Upgrade and Measured Trial

**Branch**: `spec/110-haiku-5-5-tier-trial` | **Date**: 2026-10-09 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/110-haiku-5-5-tier-trial/spec.md`

## Summary

Four parts. (1) Replace every pipeline-chosen `claude-haiku-4-5` with
`claude-haiku-5-5` and add a gate that fails if one reappears. (2) Amend
Principle II (MINOR 2.3.1 → 2.4.0) in a separate human-merged PR that lands before
the lifecycle PR. (3) Add an opt-in Haiku 5.5 shadow to the watchdog's diagnose job
(extract its agent call into a composite; run a second, read-only, last-in-job step;
compare deterministically; write a distinct trial record; self-expire at 60 days or
300 compared runs, switched by one repository variable). (4) Add the per-lifecycle
`model:haiku` implement opt-in in wrapper 5 (Sonnet escalation, `max-turns` 180) and
a deterministic trial summary read from the metrics branch. Decisions: [research.md](research.md).

## Technical Context

**Language/Version**: GitHub Actions YAML, bash, jq, Python 3 (stdlib only, as the existing `verify-*.py` gates)

**Primary Dependencies**: `anthropics/claude-code-action@v1`, existing composites `wing-commander-metrics-summary`, `-agent-verdict`, `-turn-ceiling`, `-tool-args`, `-metrics-persist`

**Storage**: metrics branch `records.jsonl` (existing); no new store

**Testing**: gate suite via `python .github/scripts/run-local-gates.py`; checked-in fixtures per failure branch; one post-merge re-drive of a watchdog run and an implement cycle (CLAUDE.md "prove")

**Target Platform**: GitHub Actions runners

**Project Type**: CI pipeline (workflows, composites, gate scripts)

**Performance Goals**: shadow adds ≤5 min to the diagnose job; Haiku 5.5 prompts (~23K tokens) stay on the low rate card

**Constraints**: shadow never acts (FR-009); published stage contract widens only additively (VII); ≤3 lifecycles in implement; `claude-haiku-5-5` acceptance by the action is verified, not assumed (research D1)

**Scale/Scope**: ~4 diagnose runs/day outside bursts; 300-run / 60-day cap

## Constitution Check

*Gate, evaluated against constitution 2.3.1; re-checked after design below.*

| Principle | Assessment |
|---|---|
| I Guide | Built through the pipeline; lifecycle #972. Pass. |
| II Tiering | Every new agent step declares model and `--max-turns` (shadow: `claude-haiku-5-5`, own budget; implement-Haiku: explicit). The shadow and the `model:haiku` opt-in are tiering changes, so the MINOR amendment precedes them (D5). The diagnose carve-out stays in force for the acting step. Pass with amendment. |
| III GitHub-native | Opt-in is a label; switch is a repo variable; summary is a job summary. Pass. |
| IV Automation-first | The amendment PR hand-off is a manual step, reported on the lifecycle issue. Pass. |
| V Security | Shadow is read-only, uses `github.token`, has no write tools, never acts; untrusted-data framing is inherited from the shared prompt. The amendment is human-merged. Pass. |
| VI Portability | No repo names hardcoded; trial vars are wrapper-side. Pass. |
| VII Two interfaces | Additive `watchdog.yml` inputs (`diagnose-shadow-enabled`, `diagnose-shadow-model`, `diagnose-shadow-max-turns`), documented as deliberate widening; stages read no `vars.*` for them; implement.yml unchanged; T026 gains no input. Pass. |
| VIII Green means green | Each new gate ships failure fixtures and is registered and triggered by its subject. Pass. |
| IX Deterministic judgment | Comparison, bound and summary are scripts, never an agent. Pass. |
| X Bounded autonomy | Unchanged; amendment never reaches `main` through the lifecycle merge. Pass. |

**No violations; Complexity Tracking empty.**

**Post-design re-check**: the composite extraction (D7) and the wrapper-side bound
(D10) keep VII intact; the one residual item is the duplicated literal `180` (D11),
held by a gate. Pass.

## Project Structure

### Documentation (this feature)

```text
specs/110-haiku-5-5-tier-trial/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── trial-record.md
│   └── trial-switches.md
└── tasks.md            # tasks stage
```

### Source Code (repository root)

```text
.github/workflows/
├── implement.yml  finalize.yml  cleanup.yml     # summary-model default -> claude-haiku-5-5
├── watchdog.yml                                 # shadow step, 3 additive inputs
├── auto-update-spec-kit.yml                     # T026 literal
├── wing-commander-5-implement.yml               # model:haiku resolution, max-turns
├── wing-commander-6-finalize.yml  wing-commander-7-cleanup.yml   # fallbacks
├── wing-commander-8-watchdog.yml  wing-commander-8b-watchdog-self.yml  # trial-bound
└── wing-commander-trial-summary.yml             # new, workflow_dispatch only
.github/actions/
├── wing-commander-diagnose-agent/               # new: prompt + claude-code-action call
├── wing-commander-trial-record/                 # new: add `trial` to a metrics record
├── wing-commander-trial-bound/                  # new: enabled/disabled decision
└── wing-commander-metrics-summary/              # additive `refusal` field
.github/scripts/
├── compare-diagnose-shadow.py  trial-summary.py  trial-bound.py   # new
├── verify-haiku-tier-model-id.py  verify-diagnose-shadow-acts-on-nothing.py
├── verify-compare-diagnose-shadow.py  verify-trial-bound.py  verify-trial-summary.py  # new gates
└── fixtures/                                    # per failure branch
.specify/memory/  constitution.md, constitution-history.md   # amendment PR only
docs/  setup.md  adoption.md  architecture.md
```

**Structure Decision**: all changes live in the existing workflow / composite / script
layout; no new top-level directory. Cross-workflow logic goes in composites per
CLAUDE.md "Shared logic has exactly one home".

## Delivery order (feeds tasks)

1. Verify action accepts `claude-haiku-5-5` (D1) and audit 400-triggering settings (D4).
2. Tier upgrade + FR-006 gate (Story 1); open the amendment PR hand-off (D5).
3. Extraction-only commit of `wing-commander-diagnose-agent`, gate suite green (D7).
4. Comparator, trial-record, bound composites + gates (Story 2); shadow step.
5. `model:haiku` wrapper resolution + defaults-match gate (Story 3).
6. Trial summary script + dispatch wrapper + gate (Story 4); docs.
7. Post-merge proof: re-drive one watchdog run (shadow on and off give identical
   filed outcomes) and one Haiku implement cycle; record evidence on #972.

## Complexity Tracking

None.
