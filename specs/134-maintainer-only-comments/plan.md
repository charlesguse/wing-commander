# Implementation Plan: Comment-Triggered Stages Act Only on Maintainers

**Branch**: `134-maintainer-only-comments` | **Date**: 2026-11-23 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/134-maintainer-only-comments/spec.md`

## Summary

Every surface that admits a comment, or passes one to an agent, follows one rule: the author is a non-bot `OWNER`, `MEMBER` or `COLLABORATOR`. The issue-author exception is removed from five places:
- the clarify wrapper;
- the shared comment trust filter;
- intake's callout text;
- the Spec Kit updater's comment-reply gate;
- the auto-release e2e clarify decision.

The published clarify stage also checks the triggering comment itself, so a consumer's older wrapper obeys the rule. Clarify's agent loses its thread-reading grant. When a lifecycle issue's author is not a maintainer, the clarification-question comments say up front that only a maintainer's reply is folded in. A new gate fails if an identity-based admission comes back. The rationale is the owner's decision of 2026-11-23 and constitution 3.0.0 (PR #1194).

## Technical Context

**Language/Version**: GitHub Actions workflow YAML; bash and jq in `run:` steps and composites; Python 3 for gates.

**Primary Dependencies**: `gh` CLI; the existing composites `wing-commander-callout`, `wing-commander-lifecycle-gate` and `wing-commander-issue-context`.

**Storage**: N/A.

**Testing**: `verify-*.py` gates with `--self-test` and mutants, run by `lint-workflows.yml` and locally by `run-local-gates.py`. Shell-step harnesses use `wc_shell_harness.run_step` with a fake `gh`.

**Target Platform**: GitHub-hosted runners, and consumers' runners and container images.

**Project Type**: Published reusable workflows and composites, plus this repository's wrappers (Principle VII).

**Performance Goals**: No new job. At most one extra API read per clarify run and per clarification-question post.

**Constraints**:
- No published input, secret or output is removed or renamed (D2).
- Shared logic has exactly one home (CLAUDE.md).
- Workflow comments are load-bearing.
- Rationale stays policy-only.

**Scale/Scope**:
- Three comment-triggered wrappers (clarify, pr-conversation, Spec Kit updater); two of them change.
- One reusable stage gains a check (clarify).
- One shared filter.
- One internal e2e script.
- About eight docs or contracts.
- One new gate.

## Constitution Check

*GATE: must pass before Phase 0 research, and again after Phase 1 design.*

| Principle | Check | Result |
|---|---|---|
| I. Guide | This repository's own wrappers are the worked example of the rule. | Pass |
| II. Model tiering | No model or turn-budget change. | Pass |
| III. GitHub-native | Requesters still use ordinary comments, and a maintainer relays them. | Pass |
| IV. Automation-first | Matches 3.0.0: a requester who is not a maintainer answers through one, and the relay text tells them so (FR-008). | Pass |
| V. Security | Implements "Comment-triggered stages verify the commenter is a maintainer … and never react to bots". Comment bodies stay untrusted data. FR-007 narrows a grant. | Pass |
| VI. Portability | The stage reads the comment through the API by its id, with no consumer-specific state. | Pass |
| VII. Two interfaces | The published contract keeps every input (`issue-author-id` stays, ignored). The behaviour tightening ships non-breaking, by precedent (D2). The consuming wrappers change freely. | Pass |
| VIII. Green check | The new gate's mutants prove it fails on the exception (FR-010). | Pass |
| IX. Deterministic judgment | The admit/refuse decision is deterministic shell, not an agent's. | Pass |
| X. Bounded autonomy | Board-loop entry is unchanged. Its comment context narrows through the shared filter (FR-003). | Pass |

Post-design re-check: still all Pass, because D1–D7 add no job, no input and no new permission.

## Project Structure

### Documentation (this feature)

```text
specs/134-maintainer-only-comments/
├── spec.md
├── plan.md               # this file
├── research.md           # D1–D7
├── data-model.md
├── quickstart.md
├── contracts/
│   └── comment-author-rule.md
└── checklists/requirements.md
```

### Source Code (repository root)

```text
.github/workflows/
├── wing-commander-2-clarify.yml          # FR-001: drop the author clause; header comments
├── clarify.yml                           # FR-006 stage check (D1); FR-007 grant; FR-008 relay note on follow-ups
├── intake.yml                            # FR-004 callout text; FR-008 relay note on first questions
├── auto-update-spec-kit.yml              # FR-002 gate; issue-author-id documented as ignored
├── wing-commander-auto-update-spec-kit.yml  # stops passing issue-author-id
├── auto-release.yml                      # FR-005: stop reading the issue author id (D5)
├── pr-conversation.yml / wing-commander-9-pr-conversation.yml  # comments that contrast with clarify
└── lint-workflows.yml                    # registers the new gate
.github/actions/
├── wing-commander-issue-context/action.yml   # FR-003 filter
├── wing-commander-requester-relay-note/action.yml  # NEW, the single home of the relay text (D3)
└── _shared/auto-release-e2e-clarify-decision.sh   # FR-005
.github/scripts/
├── verify-maintainer-only-comments.py   # NEW gate (FR-010, D7)
└── (fixture updates) verify-clarification-gating.py, verify-issue-context-single-home.py,
    verify-auto-release-e2e-gate-decisions.py and others found in T001
docs/adoption.md, docs/architecture.md, docs/reference.md (new gate row)
specs/{010,027,029,033,055,057}-*/contracts/*.md    # live contracts (FR-009)
```

**Structure Decision**: Edit in place. The only new files are one composite (the relay text's single home) and one gate.

## Complexity Tracking

No constitution violations to justify.
