# Implementation Plan: Agent-Authored Code Never Runs Beside the Loop's Write Token

**Branch**: `spec/095-agent-code-credential-containment` | **Date**: 2026-10-09 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/095-agent-code-credential-containment/spec.md`

## Summary

Move every execution of agent-authored gate code (`run-local-gates.py` and the
`verify-*.py` it dispatches) into a separate `gate-suite` job holding
`permissions: contents: read` and no App token. The credential-bearing job
hands that job a `git bundle` of the agent's commits; the gate job returns a
head-SHA-bound verdict artifact; one reader (`wc_gate_verdict.py`) turns
absence or malformation into `outcome=fail`. That one change closes spec paths
1 and 2 (the token, the snapshot rewrite, `$GITHUB_ENV`/`$GITHUB_PATH`).
Path 3 is already closed on `main` (research R1), so only a gate that reads
composite `run:` bodies is added. Path 4 gets a `.git/**` deny at each covered
agent and a single hardened-push composite at each push site. Each new
behaviour has its own `verify-*.py` gate with checked-in fixtures, registered
in `lint-workflows.yml`.

## Technical Context

**Language/Version**: Python 3.11+ (gate scripts, helpers); Bash in composite and workflow `run:` steps; GitHub Actions YAML

**Primary Dependencies**: `actions/upload-artifact` / `download-artifact` (already used), `PyYAML` (gates), `jq`, `git` ≥ 2.31 (`GIT_CONFIG_COUNT`), existing `wc_step_output.py`, `wc_gate_registry.py`, `board_spec_request_body.fenced_section`

**Storage**: Workflow artifacts (bundle, verdict). No persistent state

**Testing**: Gate scripts with `--self-test` and checked-in fixtures under `.github/scripts/fixtures/`; `python .github/scripts/run-local-gates.py`; post-merge re-drive of one board-loop run and one lifecycle stage run (FR-024)

**Target Platform**: GitHub-hosted Ubuntu runners; adopters on self-hosted runners (constraint recorded, research R9)

**Project Type**: CI/CD pipeline repository (workflows, composite actions, gate scripts)

**Performance Goals**: A modest per-call-site increase (job start + checkout); no budget asserted (spec Assumptions)

**Constraints**: Fail closed on any absent or malformed verdict; workflow comments are load-bearing (re-run the suite after comment edits); lifecycle stages and `.github/actions/**` are the published contract (Principle VII); the repository is public, so no downstream names anywhere

**Scale/Scope**: 2 board-loop sites and the implement cycle site (retry conditional, R6); 3 push sites; 4 agent tool-list sites; ~5 new gates

## Constitution Check

*GATE: passed before Phase 0; re-checked after Phase 1.*

| Principle | Assessment |
|-----------|------------|
| I Guide / dogfood | Built through the pipeline; contained suite is the shipped pattern. PASS |
| II Model tiering | No new agent invocation. PASS |
| III GitHub-native | Artifacts and comments only. PASS |
| IV Automation-first | No new manual step. Deferrals are reported to #737. PASS |
| V Security (non-negotiable) | Strengthens least privilege; adds `.git/**` deny beside the `.claude/` deny; no PAT. PASS |
| VI Portability | Gate job guards on `run-local-gates.py` existing, as the preflight does today (adopters have none, #935); nothing repo-specific hard-coded. PASS |
| VII Two interfaces | Implement and `.github/actions/**` changes widen the published surface. Mitigation: new inputs optional with defaults, no removed or renamed input/output; new composites are additive. PASS with note |
| VIII Green means what it says | Core of the feature: missing verdict = red; every failure branch has a fixture (FR-020). PASS |
| IX Deterministic judgment | The push decision reads a schema-validated artifact via one script, not model judgment. PASS |
| X Bounded autonomy | Behaviour on both gate outcomes unchanged (FR-002); in-flight items do not hard-fail. PASS |

**Post-design re-check**: unchanged. No violations; Complexity Tracking empty.

## Project Structure

### Documentation (this feature)

```text
specs/095-agent-code-credential-containment/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── gate-verdict.schema.json     # verdict artifact (live, fixed like code)
│   ├── workspace-bundle.md          # bundle artifact contract
│   └── new-gates.md                 # gate-by-gate FR coverage and fixtures
└── tasks.md                         # produced by the tasks stage
```

### Source Code (repository root)

```text
.github/
├── workflows/
│   ├── board-loop.yml          # fix + review: bundle upload, gate-suite job(s), verdict-gated publish, hardened push
│   ├── implement.yml           # pre-agent gate-suite job; hardened push; .git/** deny (via write-boundary set)
│   ├── pr-conversation.yml     # .git/** deny + push hardening only
│   └── lint-workflows.yml      # register new gates + self-tests
├── actions/
│   ├── wing-commander-contained-gate-suite/   # steps shared by every gate-suite job
│   ├── wing-commander-hardened-push/          # the one hardened-push idiom
│   └── _shared/                               # shared script(s) used by both
└── scripts/
    ├── wc_gate_verdict.py                     # verdict writer + fail-closed reader (single home)
    ├── verify-gate-suite-credential-free.py   # FR-001/FR-005/FR-006/FR-004
    ├── verify-gate-verdict-fail-closed.py     # FR-002/FR-004 reader branches
    ├── verify-snapshot-integrity-statement.py # FR-007-FR-010 comment + isolation claim
    ├── verify-composite-run-provenance.py     # FR-011/FR-013/FR-014
    ├── verify-hardened-push.py                # FR-015-FR-017, single home (FR-022)
    ├── verify-agent-git-deny.py               # FR-018 first half
    └── fixtures/095-*/                        # one per failure branch
```

**Structure Decision**: Pipeline-repository layout. Shared logic follows
CLAUDE.md "one home": a composite for the contained job's steps, a composite
for the push idiom, one Python module for the verdict. Workflow call sites keep
at most a one-line fallback.

## Phasing for the tasks stage

1. **Foundation**: `wc_gate_verdict.py`, schema, bundle contract, hardened-push
   composite, with their gates and fixtures (no workflow wired yet).
2. **Board loop**: `fix` then review-fixup — bundle, `gate-suite` job, publish
   reads verdict; Gate 98/104 amended where the carve-out moves.
3. **Implement**: pre-agent cycle gate job; hardened push; deny entry in the
   spec-090 set; retry per R6.
4. **Remaining**: `pr-conversation` deny and push hardening; composite-`run:`
   gate (R1); snapshot comment (FR-009/FR-010).
5. **Proof**: read-access audit (R8), `run-local-gates.py`, post-merge
   re-drive and evidence (FR-024).

Hot spot to sequence carefully: Gate 98's `run-local-gates.py` carve-out and
`verify-implement-gate-suite-preflight.py` both assert the current in-job step
shape and must change in the same commit as the workflow.

## Complexity Tracking

No constitution violations.
