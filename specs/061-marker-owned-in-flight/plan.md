# Implementation Plan: The Loop Recognizes Its Own Work — In-Flight Detection Reads the Board Item Marker

**Branch**: `061-marker-owned-in-flight` | **Date**: 2026-09-23 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/061-marker-owned-in-flight/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

`board-loop.yml`'s `select` and `resume` jobs currently decide "am I already
mid-flight on something?" by pattern-matching pull request bodies
repository-wide (`gh pr list ... capture("Fixes #...")`) — a search that
cannot tell the loop's own PR from an ordinary maintainer's fix PR that
happens to be open when the schedule fires (the confirmed live failure,
run 35839986595). This feature moves that decision onto the board item
marker the loop already writes on its own issues, folded into
`board_eligibility.py` (the existing eligibility/exclusion decision, per
this repository's single-home rule) as a new `in_flight_candidate()`
function that `select()` consults before its oldest-first fallback scan.
Resume's PR/branch recovery moves from an unrestricted body search to (1) a
direct by-number lookup of the marker's own recorded PR, re-validated live,
and (2) a narrow fallback restricted to open PRs carrying a new `board:owned`
ownership label the fix step now applies at PR-creation time, for the case
where a run died before writing its marker. Resume's step resolution is
corrected so no state resolves to an empty step (the other half of the live
failure: six downstream jobs silently reporting `skipped`). The whole
decision is covered by eleven checked-in fixtures under the existing Gate 81
(`verify-board-eligibility.py`), per FR-012 and Constitution VIII.

## Technical Context

**Language/Version**: Python 3 (matches `board_eligibility.py`,
`board_item_marker.py`, and every other `.github/scripts/*.py` gate/decision
module — no version pin beyond what the repository's `ubuntu-latest`
Actions runner already provides) + Bash (`run:` steps in `board-loop.yml`,
this repository's existing idiom for workflow orchestration).

**Primary Dependencies**: `gh` CLI (already the sole GitHub API client this
repository's workflows use — no new dependency); `jq` (already used
throughout `board-loop.yml`'s `run:` steps). No new Python package —
`board_eligibility.py` and `board_item_marker.py` use only the standard
library today and continue to.

**Storage**: N/A — every fact this feature reads or writes already lives on
GitHub itself (issue comments carrying the marker, PR labels, PR/issue
state); no new file, database, or artifact is introduced. Fixture files
(`.github/scripts/tests/board-eligibility/in-flight/<case>/*.json`) are
checked-in test data, not runtime storage.

**Testing**: `python3 .github/scripts/run-local-gates.py` (this
repository's own PR-time gate suite, the same one CI runs via
`lint-workflows.yml`) — specifically Gate 81
(`verify-board-eligibility.py`), extended with the fixture cases FR-012
names. No new test framework; fixtures are plain JSON files asserted
against with plain Python equality checks, matching every other gate in
this repository.

**Target Platform**: GitHub Actions (`ubuntu-latest`), scoped to this
repository's own `board-loop.yml` — not a published stage (see that
workflow's own header comment: FR-062/FR-063-equivalent reasoning already
recorded there), so this feature has no adopter-facing compatibility
surface (Constitution VII does not apply to it).

**Project Type**: Single repository, CI/workflow automation (no
frontend/backend split — this is entirely `.github/` tooling).

**Performance Goals**: Not a latency-sensitive path — the `select` job runs
once per scheduled hour and already makes O(open issues) API calls; this
feature adds at most one narrow `gh api pulls/:number` call per issue whose
marker names a fix-or-later step (in the steady state, zero or one such
issue), so the added cost is bounded and small relative to the existing
per-issue comment/timeline fetch loop.

**Constraints**: Must not widen the WING_COMMANDER App's granted permission
set (Contents/Issues/Pull requests only, per docs/setup.md) — every new `gh`
call this feature adds (`pulls/:number` read, `pr create --label`) fits
within "Pull requests" and "Issues", already granted. Must not turn
`board_eligibility.py` into something that makes network calls (Constitution
VIII: gates must run identically, offline, in CI and locally).

**Scale/Scope**: One workflow (`board-loop.yml`), two Python modules
(`board_eligibility.py`, `board_item_marker.py`), one gate script
(`verify-board-eligibility.py`), eleven new fixture directories, one new label,
one documentation table row (`docs/setup.md`). No other workflow, stage, or
published contract is touched.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Guide**: This feature is itself worked through the pipeline (issue
  #473 → this spec/plan). No violation.
- **II. Cost-Conscious Model Tiering**: This feature adds no new agent
  invocation and changes no existing one's model — `triage-propose` and
  `route-propose`'s prompts, models, and turn ceilings are untouched. N/A.
- **III. Simple, GitHub-Native Interaction**: Unaffected — this feature
  changes the loop's own internal selection/resume logic, not how a human
  interacts with it. N/A.
- **IV. Automation-First**: The feature is itself a correction to
  automation the loop already performs unattended; no new manual step is
  introduced. Pass.
- **V. Security**: No new agent step, no new trust boundary. Issue/PR body
  text is, if anything, trusted *less* after this feature (FR-001/FR-007
  forbid deriving a candidate or a PR adoption from body text at all,
  narrowing what a non-maintainer's PR description can influence — a strict
  tightening of V's existing "untrusted content is never instructions"
  posture, not a new exposure). Pass.
- **VI. Portability**: `board-loop.yml` already operates exclusively on this
  repository's own board (its header comment states this explicitly); this
  feature changes nothing about that scope. N/A.
- **VII. Two Interfaces**: `board-loop.yml` is not a published `workflow_call`
  stage (confirmed by its own header comment) — it is this repository's own
  consuming instrument, free to change without a compatibility concern. N/A.
- **VIII. A Green Check Means What It Says**: This is the principle User
  Story 3 exists to satisfy directly. The in-flight decision moves from an
  inline shell pipeline no fixture could exercise (Gate 81 could not fail on
  it because it was not part of Gate 81's subject) into `board_eligibility.
  py`, gaining eleven checked-in fixtures (FR-012) that assert exact results
  and fail loudly on a missing fixture file, mirroring Gate 81's own
  existing "fail loudly, not vacuously" pattern for `classify_issue()`.
  Pass, once implemented per this plan's contracts.
- **IX. Judgment That Gates a Durable Action Belongs in Deterministic Code**:
  The in-flight decision was already deterministic shell/Python, not a model
  prompt, before this feature — this feature does not change *what kind* of
  judgment gates the durable action, only *where* that deterministic
  judgment lives and how thoroughly it is tested. Pass; not the principle
  this feature's own motivation is about (that is VIII), but consistent
  with it.
- **X. Bounded Autonomy**: This is fix-shaped work on the board loop's own
  machinery — a corrected gate-shaped decision plus a narrowly-scoped label
  addition, no design trade-off once the spec's clarifications settled the
  two open questions. It was nonetheless routed through the full spec
  lifecycle (intake → clarify → plan) rather than fixed directly, consistent
  with CLAUDE.md's routing rule for a change judged to benefit from the
  clarify stage's questions (this defect's two clarification questions
  confirm that judgment was correct). This plan touches only
  `board-loop.yml`, `board_eligibility.py`, `board_item_marker.py`,
  `verify-board-eligibility.py`, fixtures, and `docs/setup.md` — no merge
  gate, kill switch, or concurrency-group behavior X governs is modified.
  Pass.

No violations requiring the Complexity Tracking table below.

## Project Structure

### Documentation (this feature)

```text
specs/[###-feature]/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
.github/
├── workflows/
│   ├── board-loop.yml                  # select/resume jobs, fix job's PR-create step (all edited)
│   └── lint-workflows.yml              # Gate 81 step (fixture list grows; step body unchanged)
├── scripts/
│   ├── board_eligibility.py            # in_flight_candidate() added, select() extended
│   ├── board_item_marker.py            # read_marker_with_timestamp() added
│   ├── verify-board-eligibility.py     # new fixture cases + assertions for in_flight_candidate()
│   └── tests/
│       └── board-eligibility/
│           └── in-flight/              # new: 11 fixture case directories (FR-012)
│               └── <case>/
│                   ├── open_issues.json
│                   ├── comments_by_issue.json
│                   ├── pr_state_by_number.json
│                   └── expected.json

docs/
└── setup.md                            # board:owned label documented + creation script
```

**Structure Decision**: This is a pure `.github/` workflow-and-scripts
change with no application source tree — the existing single-repository
layout `board_eligibility.py` and its gate already use is reused unchanged;
no new top-level directory, package, or project is introduced.

## Complexity Tracking

Not applicable — the Constitution Check above found no violations to
justify.
