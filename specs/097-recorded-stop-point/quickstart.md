# Quickstart: Validating the Recorded Stop Point

This is a validation guide, not an implementation guide — see plan.md,
data-model.md and contracts/ for design, and tasks.md (next stage) for the
implementation breakdown.

## Prerequisites

- A checkout of this repository with the implementation from this feature
  applied (`.github/actions/wing-commander-board-stop-check/action.yml`,
  `.github/scripts/board_stop_check.py`, `.github/workflows/board-loop.yml`
  updated per contracts/).
- `gh` authenticated against a repository where `board-loop.yml` runs (this
  repository itself, or a fork with the pipeline configured).
- Ability to post issue comments as a maintainer (OWNER/MEMBER/COLLABORATOR)
  — the stop-command authorization check is unchanged (FR-020).

## Local validation (no Actions run required)

1. Run the PR-time gate suite, including the new Gate 128:
   ```bash
   python .github/scripts/run-local-gates.py
   ```
   Confirm Gate 128 (and its self-test) both pass, and that Gate 87 still
   passes unchanged (`find_stop_request()` was not modified — research.md
   D1).

2. Exercise the new pure functions directly:
   ```python
   from board_stop_check import find_stop_request, find_stop_command_comment, stop_command_reason

   comments = [
       {"body": "stop - wrong approach", "author_association": "OWNER",
        "created_at": "2026-09-29T00:00:00Z",
        "user": {"login": "maintainer", "type": "User"},
        "html_url": "https://github.com/o/r/issues/402#issuecomment-1"},
   ]
   decision = find_stop_request(comments, "999", "wing-commander[bot]")
   winner = find_stop_command_comment(comments, "wing-commander[bot]")
   assert decision.stand_down is True
   assert winner is comments[0]
   assert stop_command_reason(winner["body"]) == "wrong approach"
   ```
   Confirms D2's invariant by hand before trusting Gate 128's automated
   version of the same check.

## End-to-end validation (Actions)

**Scenario A — User Story 1 (one stop halts one item, board keeps moving)**

1. Ensure at least two open, eligible board-loop issues exist, one already
   selected/in-flight (or let the loop select one naturally on the next
   scheduled tick / a manual `workflow_dispatch`).
2. As a maintainer, comment `stop - testing recorded stop point` on the
   in-flight issue.
3. Trigger (or wait for) the next `board-loop.yml` run.
4. **Expect**: the run's active job (triage/route/fix/review/readiness,
   whichever the item was at) stands down; the issue gains the `board:
   stalled` label and a new comment matching contracts/stop-point-
   record.md's template, naming the stop request, linking the comment
   posted in step 2, and stating "remove the `board:stalled` label."
5. Trigger a second run. **Expect**: the stopped issue is not selected; a
   *different* eligible issue is picked and worked instead (or the run
   reports an empty board if none exists) — confirms SC-001/SC-003.

**Scenario B — User Story 2 (legible on the issue)**

1. Repeat Scenario A steps 1–4, this time with a reason:
   `stop: the fix is wrong`.
2. Read the issue with no access to run logs. **Expect**: within under a
   minute, a maintainer can state why the loop stopped, which comment it
   acted on, and how to resume it — confirms SC-004. Confirm the reason
   text renders inside a fenced code block, not as live markdown (test with
   a reason containing `@someone` and a `#1` reference — neither should
   notify or link).

**Scenario C — User Story 3 (release and resume)**

1. On the issue from Scenario A, remove `board:stalled`.
2. Trigger the next run. **Expect**: the item is selected again; no second
   stop-point record is posted from the old stop comment (FR-009); no
   second branch or PR is opened for the issue (FR-054, unchanged).

**Scenario D — User Story 4 (ancient stop, empty baseline)**

1. Pick (or create) an issue the loop has never announced a run on, and
   post an authorized stop comment on it well before selecting it into the
   loop.
2. Let the loop select this issue for the first time.
3. **Expect**: the very first run that reaches a stop check on it honours
   the stop and records it (FR-016) — confirm via a second run that the
   item is not re-stood-down or re-recorded (SC-007).

**Scenario E — kill switch only (must write nothing)**

1. Set `WING_COMMANDER_BOARD_LOOP_PAUSED` to `true`, with no stop comment
   posted on the in-flight issue.
2. Trigger a run. **Expect**: no comment, no label change, no marker on the
   item (FR-011); clearing the switch afterward resumes the same item at
   the same step (SC-005).

**Scenario F — kill switch + stop request together**

1. Set the kill switch AND post an authorized stop comment on the in-flight
   issue.
2. Trigger a run. **Expect**: the stop point IS recorded (FR-012) — the
   item is now released only by removing `board:stalled`, independent of
   the kill switch.

## Metrics/cost-line check (FR-015, SC-008)

After any of Scenarios A/D/E above, inspect the uploaded `metrics-record-
<job>-outcome` artifact (or wherever this repository aggregates them) for
that run's job. **Expect**: its `run_label` field distinguishes a
stop-request stand-down (`"<job>: stopped (stop-request)"`) from a
kill-switch stand-down (`"<job>: stood down (kill-switch)"`) from an
ordinary run's own label — confirms an auditor could count stop-request
stand-downs from records alone, without reading logs.

## Proof after merge (CLAUDE.md: Actions-only behaviour)

Per this feature's own Assumptions section and CLAUDE.md's board rules, a
fix to behaviour that only runs in Actions is proven after merge by
re-driving one run (`gh workflow run board-loop.yml` or the appropriate
directed-dispatch input) and recording the evidence — Scenario A end-to-end
is the minimum bar for that post-merge proof.
