# Implementation Plan: Every Granted Script Is Checked, Not Just The `.specify` Ones At Composite Call Sites

**Branch**: `082-script-grant-existence-scope` | **Date**: 2026-09-26 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/082-script-grant-existence-scope/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

Gate 27's script-grant existence check (`.github/scripts/verify-stage-tool-lists.py`,
`check_script_grants`) only ever looks at one grant surface (a
`wing-commander-tool-args` composite call site's `default-allowed-tools`) and
one path shape (`.specify/scripts/bash/<script>`, via `SCRIPT_GRANT`'s
hardcoded prefix). This plan widens both: (1) the path classifier becomes
"any token that is a path once its interpreter prefix is stripped, checked
case-sensitively against the tree" (FR-001/FR-002/FR-003), replacing the
hardcoded prefix; (2) the collector gains two new grant surfaces —
a reusable-workflow caller's `extra-allowed-tools`/`allowed-tools-override`
inputs, and a bare `claude_args --allowedTools` string on a
`claude-code-action` step (FR-004) — reported by workflow file, job (and step,
where one exists) since neither surface has a `step-label` (FR-005); (3) a new
`script-grant-waivers.json` file, alongside the repository's existing
`*-waivers.json` files, records the exact paths that are absent from the
checkout by design, and is itself stale-checked in the direction FR-007
requires (a waived path that now resolves is a failure); (4) an unexpanded
`${{ … }}` expression is skipped rather than resolved or waived (FR-008); (5)
a malformed workflow fails loudly instead of being silently skipped (FR-009);
(6) the existing per-path memoization and one-failure-per-(site,path)
discipline (FR-011) carries over to the two new surfaces; (7) the module
docstring and `--self-test` gain the widened scope statement and one mutation
per new failure branch (FR-013/FR-012/SC-004), per Constitution VIII. The
Overview's inventory has drifted since the spec was filed (PR #613's rename of
`board_git_read.py` → `git_read.py`, and new grants rooted at the run-time-
checked-out `.wing-commander-pipeline/` path); research.md D0 re-derives it
against `main` as of this planning day and the counts below supersede the
spec's own. No workflow file needs an edit: every grant the refreshed
inventory finds either already resolves against the tree or is covered by one
of the two waiver entries this plan adds — FR-015's "green on day one" is met
without touching any `.github/workflows/*.yml` file.

## Technical Context

**Language/Version**: Python 3 (`.github/scripts/verify-stage-tool-lists.py`, run by GitHub Actions' `python3` and locally by `run-local-gates.py`), YAML (the new waiver JSON file; no workflow YAML edits are needed — see Summary) — the same stack every prior change to this gate (051, 026) used. No new runtime.

**Primary Dependencies**: `.github/scripts/verify-stage-tool-lists.py` (Gate 27, the sole file this feature extends); `pyyaml` (already a Gate 27 dependency, used to parse the newly-collected reusable-workflow-caller and `claude-code-action` sites the same way it already parses composite call sites); `run-local-gates.py` (the PR-time regression suite this change must itself pass, unchanged).

**Storage**: A new hand-maintained JSON file, `.github/scripts/script-grant-waivers.json`, holding exact absent-by-design paths — same shape and same directory as `single-home-waivers.json`/`stage-invariant-waivers.json`/`spec-branch-push-waivers.json`, but a distinct schema (FR-006 rules out those files' pattern+count shape; see data-model.md item 3). No database, no other storage.

**Testing**: Gate 27's existing `--self-test` mutation-injection pattern (`_mutations()`, the ghost-grant replay, the case-mismatch fixture), extended with one mutation per new failure branch (research.md D9/contracts/gate-27-extension.md's self-test table); `python .github/scripts/run-local-gates.py` as the full PR-time suite this change must pass, including its own extended self-test.

**Target Platform**: GitHub Actions (`ubuntu-latest` runners, and any consumer-supplied `runner`/`container-image`) — Gate 27 already runs identically in CI and locally via `run-local-gates.py` (Constitution VIII).

**Project Type**: Single repository — a GitHub Actions pipeline and its supporting gate scripts. No frontend/backend split.

**Performance Goals**: N/A (not a latency/throughput feature). SC-006 requires no perceptible added time to the local gate suite; the existing per-path memoization (`exists` dict in `check_script_grants`) is preserved and extended to cover the new surfaces' paths in the same cache.

**Constraints**: FR-011 (at most one failure per distinct (grant site, path) pair, no repeated filesystem lookup for a resolved path); Constitution VIII (every new check and every new failure branch needs a checked-in self-test fixture, reachable through the gate registry, same subject locally and in CI); Constitution IX (the waiver mechanism is deterministic code reading a hand-maintained JSON file, not a judgment left to a reviewer's prose reading); FR-015 (the repository is green under the widened check the day it lands, with no other file needing to change).

**Scale/Scope**: 1 gate script gains a generalized path/token classifier, two new grant-surface collectors, a waiver loader with its own stale check, and a widened docstring; 1 new waiver JSON file with 2 entries; the self-test gains 6 new mutation cases per research.md D9. No workflow file, composite action, or stage prompt changes.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Guide**: Worked through the pipeline (issue #599 → this spec → this plan → tasks → implement), same as every prior Gate 27 change (051, 026). PASS.
- **II. Cost-Conscious Model Tiering**: No agent step is added, changed, or removed; this is a deterministic gate-script and data-file change with no model invocation. PASS.
- **III. Simple, GitHub-Native Interaction**: No change to how a requester interacts with the pipeline. The lifecycle issue (#599) is the visible thread this plan's own comment posts to. PASS.
- **IV. Automation-First**: No new manual step; the widened check runs exactly where Gate 27 already runs (PR-time CI and local `run-local-gates.py`). PASS.
- **V. Security — Untrusted Content Is Never Instructions**: This feature narrows nothing and widens no tool grant — it only widens what the *check* inspects. No stage gains a new capability; SECURITY.md (specs/011-security-policy) needs no edit. PASS.
- **VI. Portability**: The gate script reads only this repository's own tree (`.github/workflows/`, the new waiver file); nothing hardcodes an adopter's identity. Gate 27 itself is a consuming-instrument tool (it is not part of the published `workflow_call` stage contract), so this stays entirely inside VI's "consuming repository owns its artifacts" lane. PASS.
- **VII. Two Interfaces**: Per the spec's own Assumptions, this feature does not ask `stage-interfaces.md`'s table to grow rows for the two non-composite surfaces — that table stays the documentation of the *composite's* defaults (FR-013/SC-006 of specs/026), and this feature's widened check is an internal verification tool, not a new published-contract input. No published surface is added, renamed, or removed. PASS.
- **VIII. A Green Check Means What It Says**: This is the principle's direct subject. FR-012/SC-004 require a self-test mutation for every new branch the widened check can take (a missing non-`.specify` script at a composite site, a missing script at each newly-in-scope surface, a bare command raising nothing, an expression-valued grant raising nothing, a stale waiver entry, and the real repository passing clean). PASS, contingent on tasks.md actually adding each mutation research.md D9 lists — a plan gate, not an implementation gate.
- **IX. Judgment That Gates a Durable Action Belongs in Deterministic Code**: "Is this token a path or a bare command," "does this path resolve," and "is this waiver stale" are each pure functions over parsed input (research.md D1-D6) — none is left to an agent's or reviewer's prose reading. The waiver file itself is the deterministic record FR-006 requires, not an in-script constant or comment marker. PASS.
- **X. Bounded Autonomy**: Governs how this PR is *routed and merged* (fix-shaped vs. spec-shaped), not this plan's content — this feature was already routed to the spec pipeline by the lifecycle issue, so X does not constrain the plan itself. N/A to this Constitution Check.

No violations requiring the Complexity Tracking table.

## Project Structure

### Documentation (this feature)

```text
specs/082-script-grant-existence-scope/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
│   ├── gate-27-extension.md
│   └── waiver-schema.md
└── tasks.md              # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

This is not an application with a src/tests split; it is a GitHub Actions
pipeline. The feature's real "source" is the existing gate script, edited in
place, plus one new data file — no other file needs to change (see Summary).

```text
.github/
└── scripts/
    ├── verify-stage-tool-lists.py     # Gate 27 — widened classifier, two new
    │                                  # collectors, waiver loader, widened
    │                                  # docstring, new self-test mutations
    │                                  # (FR-001..FR-013)
    └── script-grant-waivers.json      # NEW — the two absent-by-design paths
                                        # (FR-006/FR-007)
```

**Structure Decision**: No new source tree. Every behavioral change lands in
the one existing gate script Gate 27 already is; the one new file is a data
file the script reads, not code. This matches how the spec's own Assumptions
describe scope ("the check stays inside Gate 27 rather than becoming a new
numbered gate... splitting it would duplicate the collection the gate already
does") and how every prior change to this same script (051, 026) shipped.

## Complexity Tracking

*No Constitution Check violations. Table intentionally omitted.*
