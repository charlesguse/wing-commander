# Implementation Plan: Rate-limited agent verdict

**Branch**: `spec/047-rate-limited-verdict` | **Date**: 2026-09-14 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/047-rate-limited-verdict/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

When the org's five-hour usage window is exhausted, an agent step's model
call is rejected on its first turn, at zero cost. Today the shared
`wing-commander-agent-verdict` composite has no way to tell that apart
from a genuine crash — it reads the transcript's terminal `result`
record, sees a failure, and emits `failed`. The watchdog's diagnose
reporter then says "the diagnose agent failed... not inspected," and the
deterministic stage-8b verifier (`verify-watchdog-run.sh`) files a
`pipeline-defect` issue over a run that was never broken (#278 ×2,
#300).

This plan teaches the classifier a fifth verdict, `rate-limited`,
detected from two transcript-only signals already written by the
runtime: a `rate_limit_event` record and a terminal `result` record
whose failure is an API 429 — no network call, no second agent
invocation (FR-002). Three consumers change to act on it: the watchdog's
diagnose outcome gains a distinct "usage window exhausted" report (never
worded as a crash) and a new `usage-limit`-labelled, dedup-accumulating
issue that replaces the `pipeline-defect` filing (FR-007-FR-013); the
stage-8b verifier suppresses exactly the fail reasons rate-limiting
explains (the crashed-agent reporter, the missing successful terminal
result, the too-fast duration) while still filing for anything it
doesn't explain (FR-010-FR-012a); and every other agent call site's
"fail loud" step stays red for `rate-limited` exactly as for any other
non-healthy verdict (FR-015), while the narrower set of call sites that
write an issue or comment on a verdict gain an explicit exemption,
enumerated in one place and enforced by a new mechanically-enumerating
gate so a future call site cannot silently reintroduce the filing
(FR-015a/FR-015b). `wing-commander-metrics-summary` and
`docs/architecture.md` gain the fifth value everywhere the existing four
are named (FR-014/FR-017), and Gate 22
(`verify-agent-verdict.py`) gains the three synthetic cases FR-016
requires.

No new composite action and no new persisted state beyond the
`usage-limit` issue itself — this is an additive branch inside an
existing classifier, plus wiring at a small, enumerable set of
consumers, following the same shape spec 037 already established for
this exact composite.

## Technical Context

**Language/Version**: Bash (GitHub Actions `run:` steps and composite
`action.yml` files), YAML (workflow/action definitions), `jq` for JSON,
Python 3 (`lint-workflows.yml` gate scripts) — identical toolchain to
every existing composite and gate this repository already has; no new
language.

**Primary Dependencies**: GitHub Actions (`workflow_call` reusable
stages and composites), `jq`, `bash`, `gh` CLI (issue list/create/comment
for the new `usage-limit` issue and the existing `pipeline-defect`
filing), `python3`/`pyyaml` (lint-workflows.yml gates), the existing
`wing-commander-agent-verdict` composite (extended, not replaced),
`wing-commander-metrics-summary` (extended), reached via the same
`.wing-commander-pipeline/` self-checkout every stage already performs
(constitution VII). No new composite action and no new shared script
under `.github/actions/_shared/` — the rate-limit signal is read
entirely from the same transcript file and same `result_json` variable
`wing-commander-agent-verdict` already isolates, so there is nothing to
factor out.

**Storage**: No new persisted state beyond an ordinary GitHub issue: the
`usage-limit`-labelled issue FR-012/FR-013 describe, created and
accumulated by `gh issue create`/`gh issue comment` exactly like the
existing `pipeline-defect` issue, just keyed on a different label and a
looser dedup rule (research.md R5). No new artifact, no new database, no
new file format.

**Testing**: No automated test suite exists for any pipeline stage in
this repository — static validation via `lint-workflows.yml`'s gates is
the whole test surface (confirmed by every prior plan, unchanged here).
This feature extends Gate 22 (`verify-agent-verdict.py`) with the three
cases FR-016 names, using the same shipped-script-extraction-plus-
mutation discipline the gate already follows; extends Gate 36
(`verify-watchdog-run-failure-paths.sh`) with fixtures proving the new
suppression branches in `verify-watchdog-run.sh` both fire when
warranted and stay silent when an unrelated failure is present
(constitution VIII: every failure/suppression branch needs a checked-in
fixture); and adds one new gate for FR-015b's call-site enumeration
(research.md R6).

**Target Platform**: GitHub Actions (`ubuntu-latest` runners) — same as
every existing composite and gate touched by this feature.

**Project Type**: Single project — CI/CD automation under
`.github/workflows/` and `.github/actions/`, extending an existing
composite and lint gates. No frontend/backend split.

**Performance Goals**: SC-001 (zero `pipeline-defect` filings and zero
red stage-8b runs for usage-window exhaustion, down from three over two
weeks) and SC-002 (a maintainer reaches "not a defect" from a single
report, under one minute, versus today's log dive). Not latency-
sensitive: classification is a `jq` read of an already-produced
transcript file, and the new `usage-limit` issue write is a single
extra `gh` call on the already-slow (network-bound) diagnose-reporting
path — negligible relative to the job's own runtime.

**Constraints**: FR-002 — the classification itself must stay
transcript-only, no network call and no second agent invocation
(the `usage-limit`/`pipeline-defect` issue writes are downstream
*consumers* of the verdict, not part of classification). FR-005/FR-006
— every existing verdict and its single-home guarantee are unchanged;
the new branch is additive inside the one composite, never a second
copy. Edge case "the classifier itself must never fail" — the new
branch preserves the composite's existing unconditional `exit 0`
contract (research.md R4 of spec 037, unchanged here). FR-015 — the
generic "fail loud on non-healthy verdict" step at every call site stays
untouched and still fails on `rate-limited`; only the narrower set of
issue/comment-writing call sites gains an exemption, and FR-015b
requires that set to be enumerated and mechanically checked rather than
trusted to code review.

**Scale/Scope**: 1 composite extended
(`wing-commander-agent-verdict` — new branch, one new output), 1
composite extended (`wing-commander-metrics-summary` — allow-list
addition only), 1 workflow extended with new logic
(`watchdog.yml` — new outcome branch, new report step, new
`usage-limit` issue step), 1 script extended
(`verify-watchdog-run.sh` — suppression of 2 of its 8 checks, gated on
one new step-conclusion read), 1 existing gate extended with 3 new
cases (Gate 22), 1 existing gate extended with new fixtures (Gate 36),
1 new gate added (research.md R6, FR-015b), a small enumerated set of
non-watchdog issue/comment-writing call sites gaining an exemption
condition (re-enumerated by the new gate itself, not hand-counted at
plan time — research.md R6), and 1 `docs/architecture.md` paragraph
extended (no new file — existing convention is inline, not a catalog).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Guide**: This feature is itself built through the pipeline
  (#306 → this spec → this plan → tasks → implementation on
  `spec/047-rate-limited-verdict`), and closes a defect the pipeline's
  own watchdog and stage-8b verifier hit against themselves (#278 ×2,
  #300) — the repository fixing its own false alarm is the worked
  example. **Pass.**
- **II. Cost-Conscious Model Tiering**: No agent invocation is added,
  removed, or retiered. The classifier stays a zero-cost `jq` read; the
  new `usage-limit` issue write and the report-step wording change add
  no model call. **Pass.**
- **III. Simple, GitHub-Native Interaction**: The maintainer-visible
  surface is still exactly the lifecycle/findings issue and the run's
  own step summary — a rate-limited run now posts a *different*, more
  honest comment there (FR-007/FR-008) and, distinctly, an accumulating
  `usage-limit` issue (FR-012/FR-013) using the same `gh issue
  create`/`comment` mechanism every other watchdog finding already uses.
  No new dashboard, no new CLI. **Pass.**
- **IV. Automation-First**: Removes a manual step this defect currently
  forces — a maintainer opening the `pipeline-defect` issue, downloading
  the artifact, and concluding "not a defect" by hand (SC-002). Nothing
  about this feature introduces a new manual step; closing/sweeping the
  `usage-limit` issue stays deliberately manual (spec.md Assumptions),
  matching how re-driving a rate-limited run already stays manual today.
  **Pass.**
- **V. Security (NON-NEGOTIABLE)**: The verdict is derived solely from
  the already-uploaded transcript (FR-002); no new network call inside
  classification, no elevated permission, no change to which refs are
  checked out or which App mints tokens. The new `usage-limit` issue
  write uses the same token and the same `gh issue create`/`comment`
  calls the existing `pipeline-defect` path already makes from the same
  job. **Pass.**
- **VI. Portability**: The extended composite and the extended gates
  live under `.github/actions/` and `.github/scripts/` in this
  repository, resolved through the same `.wing-commander-pipeline/`
  self-checkout every existing composite already uses — an adopter
  pinning a release tag gets the fifth verdict for free. No
  consuming-repo-owned file is newly read or required (`usage-limit` is
  a label this feature creates on first use, the same pattern
  `pipeline-defect` and the per-finding `🐕 · <class>` labels already
  follow). **Pass.**
- **VII. Two Interfaces**: `wing-commander-agent-verdict`'s `verdict`
  output gains one new possible value and one new optional output
  (`rate-limit-reset`); both are additive to a composite this repository
  documents as unpublished implementation detail (same status as
  `wing-commander-turn-ceiling` today, per spec 037's plan), so no
  published `workflow_call` surface changes name, type, or default.
  **Pass.**
- **VIII. A Green Check Means What It Says**: Directly on point — this
  entire feature exists because the stage-8b verifier's green check
  meant "verified healthy," not "not a defect I recognize," for a shape
  it had no way to distinguish. The fix keeps that gate able to fail its
  own subject (an unrelated failure alongside a rate-limited run still
  fails it, US1 Acceptance Scenario 4/FR-011) while narrowing exactly
  the reasons it no longer over-reports, and every suppression branch it
  gains gets a checked-in fixture in Gate 36 (research.md R4). **Pass.**
- **IX. Judgment That Gates a Durable Action Belongs in Deterministic
  Code**: The suppression that keeps stage-8b green, the classification
  that produces `rate-limited` in the first place, and the dedup that
  decides whether a run folds into the open `usage-limit` issue are all
  deterministic `jq`/`bash` reads of fixed transcript fields and step
  conclusions — no agent judgment gates any of these writes or
  suppressions (mirrors the existing `pipeline-defect` dedup and
  verifier design this feature extends rather than reworks). **Pass.**

No violations — Complexity Tracking is not needed.

## Project Structure

### Documentation (this feature)

```text
specs/047-rate-limited-verdict/
├── plan.md                    # This file (/speckit-plan command output)
├── research.md                 # Phase 0 output (/speckit-plan command)
├── data-model.md                # Phase 1 output (/speckit-plan command)
├── quickstart.md                # Phase 1 output (/speckit-plan command)
├── contracts/                   # Phase 1 output (/speckit-plan command)
│   ├── agent-verdict-extension.md   # the classifier's new branch/output, metrics-summary allow-list
│   ├── watchdog-reporting.md        # diagnose outcome branch, the new report step, the usage-limit issue
│   ├── verifier-suppression.md      # verify-watchdog-run.sh's new evidence read and 2 suppressed checks
│   └── exemption-gate.md            # FR-015a/b: the enumerated exemption and its new gate
└── tasks.md                     # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
.github/
├── actions/
│   ├── wing-commander-agent-verdict/
│   │   └── action.yml                    # EXTENDED — new `rate-limited` branch in "Classify agent run
│   │                                        #            verdict"; new `rate-limit-reset` output; `verdict`
│   │                                        #            output description gains the fifth value
│   └── wing-commander-metrics-summary/
│       └── action.yml                    # EXTENDED — `rate-limited` added to the outcome allow-list
│                                            #            (case statement); NOT added to the standalone
│                                            #            fallback classifier (research.md R2)
├── scripts/
│   ├── verify-agent-verdict.py           # UPDATED — Gate 22 gains 3 cases (FR-016): terminal 429,
│   │                                        #           recovered mid-run 429, non-429 API error
│   ├── verify-watchdog-run.sh            # UPDATED — reads the new "Report rate-limited..." step's
│   │                                        #           conclusion; suppresses the check-7 (successful
│   │                                        #           terminal result) and check-2 floor-breach reasons
│   │                                        #           only when that step ran
│   ├── verify-watchdog-run-failure-paths.sh  # UPDATED — Gate 36 gains fixtures for both suppression
│   │                                        #              branches (fires / stays silent) plus the
│   │                                        #              "unrelated failure still reported" case
│   └── verify-rate-limited-exemption.py  # NEW — FR-015b's gate: enumerates every verdict-gated
│                                            #        issue/comment-writing step and fails when one is
│                                            #        not in the registered-exempt set
├── workflows/
│   ├── lint-workflows.yml                # UPDATED — new gate step added (research.md R6 for the number)
│   └── watchdog.yml                      # UPDATED — diagnose job: new `rate-limited` outcome branch in
│                                            #           "Read back diagnose outcome"; new "Report
│                                            #           rate-limited to lifecycle issue" step; new "Ensure
│                                            #           usage-limit issue" step
docs/
└── architecture.md                        # UPDATED — the existing verdict-vocabulary paragraph (line
                                              #            ~234) gains the fifth value and both gate
                                              #            references (FR-017)
```

A small, currently-unenumerated set of non-watchdog workflows may also
need a one-line `if:` change at whichever issue/comment-writing call
sites the new FR-015b gate finds are not already exempt (candidates
identified during research: `finalize.yml`, `cleanup.yml` — see
research.md R7). This plan does not hand-enumerate that set the way
spec 037 hand-enumerated its 19 call sites, because FR-015b's whole
point is that the set is mechanically discovered, not trusted to a
plan-time list that can silently go stale the next time a stage gains a
new issue-writing step (research.md R6).

**Structure Decision**: Single-project CI/CD feature, additive-extension
shape — no new composite action, matching this repository's own
precedent for adding a value to an already-shared enum (the closest
analog is spec 037 itself introducing the four-value vocabulary this
feature extends to five). The one genuinely new component is the
FR-015b enumeration gate, following the same dynamic-enumeration-plus-
registered-exception-list template `verify-gate-23.py` already
established for a structurally similar problem (every call site of a
kind must carry a specific piece of wiring, checked by parsing the YAML
rather than by a hand-kept list).

## Complexity Tracking

> Not applicable — no Constitution Check violations.
