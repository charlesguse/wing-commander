# Implementation Plan: Gate 12 — gh call-site authoring rule and shared locator

**Branch**: `113-gh-callsite-locator` | **Date**: 2026-10-10 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/113-gh-callsite-locator/spec.md`

## Summary

Replace Gate 12's ~690-line inline bash parser with a small fail-closed
pure-Python locator (`wc_gh_callsites.py`) that accepts a written set of
allowed `gh` call-site shapes and treats every unprovable mention as a call.
Move the gate body out of `lint-workflows.yml` into
`verify-gate-12-token-permissions.py`, keep its token/permission logic
unchanged, move Gate 28 onto the locator, add a single-home check, and prove
the whole thing with PR #969's 183-scenario corpus, a seeded real-bash
differential with a stub `gh`, and a mutation check. See research.md.

## Technical Context

**Language/Version**: Python 3 (stdlib + PyYAML, as existing gates); bash for the differential oracle

**Primary Dependencies**: none new (FR-019)

**Storage**: files only (corpus JSON, waiver JSON)

**Testing**: self-test `verify-gate-12.py`, `run-local-gates.py` full suite

**Target Platform**: GitHub Actions runners and local Linux

**Project Type**: CI gate tooling (scripts + workflows)

**Performance Goals**: locator linear in `run:` block size (FR-008)

**Constraints**: no new dependency; Gate 12 numbering preserved; no change to stage inputs/outputs/secrets

**Scale/Scope**: 87 workflow/action files, 478 executable calls, ~80 mentions

## Constitution Check

*Pre-design and post-design evaluation against `.specify/memory/constitution.md`.*

- I Guide: new rule documented once in contributor docs — PASS.
- VII Two Interfaces: internal scripts and docs only; no published input/output/secret change; underscore/script paths not adopter surface — PASS.
- VIII Green Check: gate in registry, same args local/CI, path-triggered, every failure branch has a fixture, mutation test, fail-closed on unreachable subject — PASS (this is the feature's purpose).
- IX Deterministic judgment: classification is deterministic code — PASS.
- V Security: no untrusted content used as instruction; locator only reads files — PASS.
- II/III/IV/VI/X: not affected — PASS.
- CLAUDE.md single-home rule: locator is the one home; single-home gate extended; one waiver cited to #889 — PASS.

No violations; Complexity Tracking empty. Post-design re-check: PASS.

## Project Structure

### Documentation (this feature)

```text
specs/113-gh-callsite-locator/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── locator-api.md
│   └── authoring-rule.md
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
.github/scripts/
├── wc_gh_callsites.py                    # NEW shared locator (~250 lines)
├── verify-gate-12-token-permissions.py   # NEW gate body moved from lint-workflows.yml
├── verify-gate-12.py                     # self-test: imports gate, corpus, mutation, differential
├── gate-12-corpus.json                   # NEW 183 scenarios from archive/pr-969-gate-12-corpus
├── gate-12-fuzz/                         # NEW generator + real-bash runner from archive
├── verify-gh-api-explicit-method.py      # Gate 28 migrated to locator
├── verify-single-home-idioms.py          # extended: no second gh locator
├── single-home-waivers.json              # + waiver for verify-stop-point-recording.py (#889 line)
└── wc_shell_harness.py                   # stub-gh argv recording if missing
.github/workflows/lint-workflows.yml      # Gate 12 step -> script call; path triggers
<contributor doc>                         # authoring-rule section (R8)
```

**Structure Decision**: scripts-only change in `.github/scripts/` plus the
one workflow step and one doc section; call-site migrations (expected
0–2, plus quoted-heredoc-delimiter fixes for mentions) edit workflows and
actions with no behavioural change.

## Complexity Tracking

None.
