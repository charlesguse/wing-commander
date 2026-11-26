# Implementation Plan: One Reviewer for Every Kind of Pull Request

**Branch**: `spec/127-shared-pr-reviewer` | **Date**: 2026-11-22 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/127-shared-pr-reviewer/spec.md`

Layer: this plan describes the consuming instrument (this repository's own workflows and scripts); nothing is added to the published contract.

## Summary

Add one report-only reviewer: a callable workflow `shared-pr-reviewer.yml` and a thin wrapper `wing-commander-shared-pr-reviewer.yml` (dispatch only). A round is `guard` → `prepare` → `code-run` (no secret, runs only the named check and the gate suite) → `find` agent → `check` agent (no shared context) → `record` (deterministic, the only writer). All judgment that gates the record (identity, open set, blocking, verdict, budget, run confirmation) lives in one tested Python module `wc_shared_review.py`. The record uses its own marker `wing-commander-shared-review-round`, so spec 116's `read_round_records` can never count it and no existing reviewer changes. Details: [research.md](research.md), [data-model.md](data-model.md), [contracts/round-record.md](contracts/round-record.md), [quickstart.md](quickstart.md).

## Technical Context

**Language/Version**: Python 3.11+ for scripts (as the existing `.github/scripts`), GitHub Actions YAML, bash only in `run:` steps with `shell: bash` where in a container

**Primary Dependencies**: existing `board_item_marker.py`, `wc_review_finding_fingerprint.py`, `wing-commander-tool-args` composite, `anthropics/claude-code-action` as used by sibling reviewers; no new third-party dependency

**Storage**: PR comments (record marker); Actions artifacts for staged code-run results and run binding

**Testing**: pytest-style fixtures under `.github/scripts/tests/`, plus new `verify-*.py` gates registered in the gate registry and run by `run-local-gates.py`

**Target Platform**: GitHub Actions ubuntu runners

**Project Type**: CI workflow plus helper scripts

**Performance Goals**: N/A; bounded by turn budgets and a 5-round budget per PR

**Constraints**: explicit models and `--max-turns` (Principle II); no secret in the code-run job; agents hold no write token and no web tools; runs from the default branch only

**Scale/Scope**: a handful of session fix PRs in the report-only period (SC-001: at least 5)

No unresolved NEEDS CLARIFICATION.

## Constitution Check

| Principle | Result |
|---|---|
| I Guide | Pass: built through the pipeline; first use dogfoods on session fix PRs |
| II Model tiering | Pass: both agents `claude-sonnet-5-5` default, var-overridable, `--max-turns` set (FR-024). Sonnet for review is within the "weight-matched" rule; recorded as a default the owner approves with the spec |
| III GitHub-native | Pass: output is one PR comment; refusals in run summary |
| IV Automation-first | Pass with accepted gap: dispatch is manual by the session (owner decision, FR-004) |
| V Security | Pass: untrusted text framed as data; no write token or web tools for agents; maintainers' dispatch only; default-branch-only; PR head never supplies prompts; code-run holds no secret |
| VI Portability | Pass: nothing repo-name-specific; wrapper owns repo conventions |
| VII Two interfaces | Pass with a registered exception: the callable workflow sits among stage workflows but is registered as unpublished (research D3); reads no `vars`/`github.event` itself, inputs typed |
| VIII Green check | Pass: every failure branch gets a fixture; verifiers for isolation, marker disjointness, tool lists |
| IX Deterministic judgment | Pass: identity, status, blocking, verdict, budget, confirmation are code (research D2, D6, D7) |
| X Bounded autonomy | Pass: reviewer authorizes nothing (FR-028), writes only its record, merges nothing; kill switch `WING_COMMANDER_SHARED_REVIEWER_PAUSED` |

Post-design re-check: unchanged, all pass. No Complexity Tracking entries.

## Project Structure

### Documentation

```text
specs/127-shared-pr-reviewer/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/round-record.md
└── tasks.md            # tasks stage
```

### Source Code

```text
.github/workflows/
├── shared-pr-reviewer.yml                  # callable: guard, prepare, code-run, find, check, record
└── wing-commander-shared-pr-reviewer.yml   # wrapper: workflow_dispatch, vars, concurrency per PR
.github/scripts/
├── wc_shared_review.py                     # identity, open set, blocking, verdict, budget, confirm, record
├── shared_review_compare.py                # side-by-side with the hand review (FR-029)
├── verify-shared-review-*.py               # marker disjointness, code-run isolation, agent tool lists, kill switch/guard wiring
└── tests/test_wc_shared_review.py          # fixtures for every Story/SC case
.github/prompts or inline                   # find and check prompts, default-branch copies only
CLAUDE.md                                   # the one fix-PR line (FR-004), implement stage
docs/reference.md                           # loop, defaults, limits, switch
```

**Structure Decision**: single module for logic, workflows thin; no composite added since no second workflow shares the logic yet.

## Phases and order

1. `wc_shared_review.py` with tests (pure logic first: Stories 2, 3, 5; SC-002, SC-004).
2. Guard, prepare and record jobs; marker/disjointness and wiring verifiers.
3. Code-run job and hostile fixture; isolation verifier (SC-008).
4. Agent jobs, prompts, tool lists, schemas.
5. Wrapper, kill switch, docs/reference.md, the CLAUDE.md line, published-contract exemption entry.
6. Gate suite (`python .github/scripts/run-local-gates.py`) plus `review-step-gating` and `container-shell-safety` skill passes; post-merge `prove-after-merge` live round.

## Decisions made without clarification

See research.md: D1 distinct marker; D3 job split and unpublished registration; D5 confirmation binding via artifact; D9 turn-budget defaults (40/40); D10 purpose-version fallback. All are plan-level and reversible.
