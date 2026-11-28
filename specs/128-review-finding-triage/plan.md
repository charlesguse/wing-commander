# Implementation Plan: Review findings — fix now, record only what fails silently, drop the rest

**Branch**: `spec/128-review-finding-triage` | **Date**: 2026-11-26 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/128-review-finding-triage/spec.md`

## Summary

Put the owner-approved filing rule into deterministic code that both stage
paths share: a new pure module `wc_finding_triage.py` decides
fix-now / record / drop / reject from four optional finding fields
(`failure_class`, `silent_description`, `severity`, `security`). The
lifecycle review gate uses it in the review job (annotate and render the
dropped/rejected list in the round's review body) and in the disposition
job (filter out-of-scope survivors before the 3-slot cap). The
`wing-commander-stage-findings` composite uses it before its cap and in its
run summary. A new PR-time gate checks the renderer lists every drop and
reject with its reason and that nothing important/security is dropped. The
board loop's reviewer and the PR-conversation stage are untouched. The #889
sweep (FR-012) is a post-merge owner-session action, not built.

## Technical Context

**Language/Version**: Python 3 (stdlib only) for the module and gate; Bash and embedded Python in GitHub Actions YAML for call sites

**Primary Dependencies**: none new; reuses `wc_convergence`, `wc_review_finding_fingerprint`, `wing-commander-durable-failure-issue`

**Storage**: files only (`lifecycle-review-findings.json` artifact, `state.json` in the composite)

**Testing**: checked-in fixture corpora plus `verify-*.py` gates via `run-local-gates.py`; existing `stage-findings-tests/run_fixtures.py`

**Target Platform**: GitHub Actions runners (ubuntu)

**Project Type**: CI pipeline / repository tooling

**Performance Goals**: N/A

**Constraints**: composite always exits 0; no new workflow input/secret/output (published contract unchanged); finding text is agent-authored data and never enters annotations (FR-026); drops must not suppress existing failure reporting (FR-013)

**Scale/Scope**: ≤ 25 findings shown per gate round, 3 filing slots per path

## Constitution Check

*Gate: passes before research; re-checked after design.*

- I Guide: built through the pipeline; the spec is the worked example. Pass.
- II Model tiering: no new agent invocation; the existing reviewer prompt gains fields. Pass.
- III GitHub-native: dropped findings are named in the PR review body / run summary. Pass.
- V Security: finding fields are untrusted data; the router validates types, never executes them; no `.claude/` writes. Pass.
- VII Two interfaces: only optional fields on internal schemas; no published input/output renamed. The composite's outputs (`filed`, `appended`, `dropped-*`, `summary`) are unchanged in name. Pass. If implement finds a published output must be added, that is a widening and goes back to the owner.
- VIII Green check means what it says: new gate registered, triggered by the files it checks, fails loudly on an unreachable subject, ships a fixture per failure branch. Pass.
- IX Deterministic judgment: record/drop is code reading a structured field; the agent only proposes the class and description. Pass (this feature is the principle's application).
- X Bounded autonomy: board loop's reviewer unchanged, so its out-of-scope-to-issue rule stands; no amendment needed. Pass.

Post-design re-check: unchanged; no violations, Complexity Tracking empty.

## Project Structure

### Documentation (this feature)

```text
specs/128-review-finding-triage/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/finding-triage.md
└── tasks.md            # tasks stage
```

### Source Code (repository root)

```text
.github/
├── scripts/
│   ├── wc_finding_triage.py                 # NEW: single home of the rule + renderer
│   ├── verify-finding-triage-report.py      # NEW: PR-time gate (FR-011, single-home, parity)
│   ├── fixtures/finding-triage/             # NEW: positive + one fixture per failure branch
│   ├── verify-board-review-finding-schema.py   # accept the 4 optional fields
│   └── verify-stage-finding-schema.py          # accept the 4 optional fields
├── schemas/
│   ├── board-review-finding.schema.json     # + optional fields
│   └── stage-finding.schema.json            # + optional fields
├── actions/wing-commander-stage-findings/action.yml   # triage before cap; summary; body section
└── workflows/
    ├── lifecycle-review-gate.yml            # extract annotate, review-body render, partition filter, reviewer prompt
    ├── lint-workflows.yml                   # register the new gate
    └── (stage workflows' findings prompts)  # emit the 4 fields
docs/reference.md                            # findings defaults / cap wording
specs/056-…/contracts/wing-commander-stage-findings.md   # live contract updated
specs/062-…/contracts/review-and-findings.md             # live contract updated
```

**Structure Decision**: one shared script module in `.github/scripts/`
(the repository's existing home for shared Python, imported by both
workflows and composites), no new composite. Call sites keep at most a
one-line fallback if the module cannot be loaded: the fallback is
*record* (fail toward visibility), never drop.

## Key design points

1. **Precedence and reasons** are in [data-model.md](data-model.md); the API
   and guarantees in [contracts/finding-triage.md](contracts/finding-triage.md).
2. **Gate flow**: extract annotates → review body renders the
   "Dropped and rejected" section → disposition re-derives outcomes and keeps
   only `record` ones for the `[:3]` slots. Fix-now (in-scope) path is
   untouched, so readiness and the round budget count it as today.
3. **Composite flow**: prepare routes survivors after errata/in-flight
   filtering and before the cap; `triaged_out` goes to `state.json`; Emit
   summary renders it; a rejection also warns. `routed-task` is exempt.
4. **Rejected findings** are neither filed nor dropped; the report names them
   with `silent, no description` and the run carries a warning (FR-009).
5. **Single-home enforcement**: the new gate fails if either call site
   reimplements the rule (a literal `fails loudly` / `no output change`
   outside the module and fixtures), per CLAUDE.md.
6. **Post-merge**: FR-012 sweep and `prove-after-merge` on one gate round and
   one stage run; recorded for the owner session, not built by implement.

## Risks

- The board loop shares `board-review-finding.schema.json`; the added fields
  are optional, and a gate check asserts its fixtures still validate.
- Workflow comments are byte-compared by gates: re-run the full suite after
  any comment edit.
- A reviewer that omits `failure_class` yields *record*, so volume only drops
  once prompts emit it; SC-001 is measured after the prompt change lands.

## Complexity Tracking

No constitution violations.
