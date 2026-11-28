# Implementation Plan: Workflow security — static-analysis gate, `./` references, trigger docs

**Branch**: `spec/132-workflow-trigger-security` | **Date**: 2026-11-25 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/132-workflow-trigger-security/spec.md` (issue #1188)

## Summary

Add three deterministic gates and one register, fix the three template-injection sites, SHA-pin third-party actions outside a trusted-publisher set, add pin-update automation, and document the events adopters must allow.

1. **zizmor gate** (`verify-zizmor.py`): runs pinned zizmor 1.33.1 offline over `.github/workflows` and `.github/actions` (discovered by glob, so `_shared/` and nested actions are included), reads JSON output, and subtracts the accepted-findings register. Fails on unwaived findings, stale records, missing analyser, empty file set, unparsable output.
2. **Register** `.github/scripts/zizmor-findings-waivers.json`: the `*-waivers.json` name means gate 124 discovers it with no change to that gate (FR-013). Records are keyed on `(file, audit, job-or-step identity)`, never a line number.
3. **Trusted-publisher list** has one home, `.github/zizmor.yml`'s `unpinned-uses` policy, which is also what zizmor reads. The gate reads the same file; a second copy elsewhere under `.github/` fails (FR-009a).
4. **Untrusted-checkout gate** (`verify-untrusted-checkout-local-uses.py`): for each job (and each composite reached through its calling jobs), tracks every checkout/extract that places content in the workspace, classifies each as trusted copy or untrusted tree by repository and ref, and fails when a `./` reference resolves inside an untrusted tree (FR-016a). Repo-only reusable workflows are listed in one JSON file the gate reads (FR-016b).
5. **Trigger-inventory gate** (`verify-adopter-event-policy.py`): compares events declared under `on:` in `wing-commander-*.yml` with the sample policy block in `docs/adoption.md` (FR-020).
6. **Fixes**: three injection sites to `env:`; `github-env`, `artipacked`, `excessive-permissions`, `github-app` fixed or recorded one at a time; exposed jobs fixed (FR-015); SHA pins plus update automation (FR-009b); Gate 170 register rows (FR-017a).

## Technical Context

**Language/Version**: Python 3 (stdlib only, like the existing `verify-*.py` gates); GitHub Actions YAML; zizmor 1.33.1 binary (pinned)

**Primary Dependencies**: zizmor 1.33.1 (installed from a pinned release; the install step is SHA-pinned and checksum-verified); PyYAML only if already used by sibling gates, otherwise the repo's existing YAML helpers

**Storage**: JSON registers and one YAML config under `.github/`; no runtime state

**Testing**: each gate ships `--self-test` with checked-in fixtures, one per failure branch (FR-006); run through `python .github/scripts/run-local-gates.py`

**Target Platform**: GitHub-hosted Linux runners and local Linux/macOS

**Project Type**: CI gates + workflow edits + docs

**Performance Goals**: zizmor offline over about 150 files finishes in seconds; no budget concern

**Constraints**: offline by default, no token (FR-004); identical version/config/file set locally and in CI (FR-001); published stage interfaces unchanged (FR-015, FR-016b); `./` kept (FR-016)

**Scale/Scope**: 557 findings in the baseline scan, 224 suppressed; 193 `self-repository` (audit disabled), 103 `unpinned-uses`, 7 `dangerous-triggers`, 3 `template-injection`

No NEEDS CLARIFICATION markers remain in spec.md; choices the spec left to the plan are decided in research.md.

## Constitution Check

| Principle | Result |
|---|---|
| I Guide | Pass. Built through the pipeline. |
| II Model tiering | N/A. No agent invocation added. |
| III GitHub-native | Pass. Findings surface as PR check failures. |
| IV Automation-first | Pass. Pin-update PRs are automated; merged by a human (FR-009b). |
| V Security | Pass. Strengthens it. No new trigger, no fork-head checkout. The untrusted-checkout gate encodes "only trusted refs". |
| VI Portability | Pass. The register and config are this repository's own. Adopter docs are generic. |
| VII Two interfaces | Pass. No input, secret or output added to a published stage. SHA pins change resolution, not interface (FR-018a states it). Gate and register live in the consuming instrument. |
| VIII Green check | Pass by design. Registry-reachable, same args locally and in CI, triggered by the tree it checks, fails loudly when it cannot run, every failure branch has a fixture. |
| IX Deterministic judgment | Pass. All decisions are code. |
| X Bounded autonomy | Pass. Bump PRs are human-merged, not a bot merge class. |

Result: no violations, so the Complexity Tracking table stays empty. Re-checked after design: unchanged.

## Project Structure

### Documentation (this feature)

```text
specs/132-workflow-trigger-security/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── zizmor-gate.md
│   ├── findings-register.schema.json
│   └── untrusted-checkout-gate.md
└── tasks.md             # tasks stage
```

### Source Code (repository root)

```text
.github/
├── zizmor.yml                                    # NEW: audit config; unpinned-uses policy = trusted-publisher home; self-repository disabled with reason
├── scripts/
│   ├── verify-zizmor.py                          # NEW gate: run, parse, subtract register, stale check
│   ├── zizmor-findings-waivers.json              # NEW register (gate 124 picks it up by name)
│   ├── verify-untrusted-checkout-local-uses.py   # NEW gate (FR-016a/b)
│   ├── repo-only-reusable-workflows.json         # NEW: FR-016b single home
│   ├── verify-adopter-event-policy.py            # NEW gate (FR-020)
│   ├── verify-trusted-publisher-single-home.py   # NEW gate (FR-009a); may fold into verify-zizmor.py
│   ├── action-runtime-pins.json                  # EDIT: rows for SHA refs (FR-017a)
│   ├── verify-board-loop-composite-provenance.py # EDIT: checkout-ordering rule moves to the new gate
│   └── verify-lifecycle-review-gate-composite-provenance.py  # EDIT: same
├── workflows/
│   ├── lint-workflows.yml                        # EDIT: gate steps + paths triggers
│   ├── board-loop.yml, wing-commander-rebase.yml # EDIT: env: for injection sites
│   ├── pr-conversation.yml etc.                  # EDIT: exposure fixes; SHA pins
│   └── update-action-pins.yml                    # NEW: pin-update automation (research D6)
docs/
├── adoption.md                                   # EDIT: events, gates, sample policy, fork limit, permissions
└── reference.md                                  # EDIT: every new gate, register and default (FR-023)
```

**Structure Decision**: follow the repo's existing pattern of one `verify-*.py` per gate, JSON waiver register named `*-waivers.json`, and each step added to lint-workflows.yml with a `--self-test` sibling. Details in research.md and contracts/.

## Phasing for tasks

1. Config, pin, register skeleton and `verify-zizmor.py` with fixtures (US1/US2, P1).
2. Fix the three injection sites; triage github-env/artipacked/excessive-permissions/github-app; record the 7 dangerous-triggers.
3. SHA pins, trusted-publisher home, update automation, Gate 170 rows.
4. Exposure audit, untrusted-checkout gate, fold the older provenance rules, fix exposed jobs (US3).
5. Adopter docs, event-policy gate, reference.md (US4).
