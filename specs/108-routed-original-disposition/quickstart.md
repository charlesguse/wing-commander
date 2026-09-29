# Quickstart: Routed-Original Disposition

Validation scenarios for this feature, mapped to spec.md's Independent
Tests and Acceptance Scenarios. Run the gate suite first — most of this
feature's correctness is gate-provable, not just demo-able (Principle VIII:
a manual demonstration is evidence for the reviewer who ran it, not
coverage for the next one).

## 0. Gate suite (does the wiring hold at all three sites)

```
python .github/scripts/run-local-gates.py verify-issue-context-single-home
python .github/scripts/run-local-gates.py verify-board-eligibility
```

Expected: both pass, including their `--self-test` fixture runs (contracts/
gate-93-check-3-delta.md, contracts/eligibility-and-readmission-delta.md).
A fixture workflow with a spec-request site that omits the disposition call
must fail Gate 93 by name (spec.md User Story 3, Acceptance Scenario 1);
the real `board-loop.yml` must pass (Acceptance Scenario 2); a fixture with
no spec-request site at all must still fail rather than pass vacuously
(Acceptance Scenario 3).

## 1. One open issue per routed request (User Story 1)

Prerequisite: a maintainer-authored (or maintainer-labelled) open issue the
route step judges spec-shaped, and `WING_COMMANDER_BOARD_LOOP_PAUSED` clear.

```
gh workflow run board-loop.yml   # or wait for the next scheduled tick
```

After the route step's spec-verdict site finishes on that issue:

```
gh issue view <originating> --json state,labels,comments
gh issue view <spec-request> --json state,labels,comments,body
```

Expected: originating issue `state == CLOSED`, carries
`disposition:duplicate`, has a comment stating the reason and linking the
spec-request (FR-003), and still carries the pre-existing "Routed to
spec-request" checklist comment. The spec-request has a new checklist-item
comment linking back to the originating issue (FR-004, research.md D5).
Counting open issues attributable to this request: exactly one (the
spec-request) — spec.md's own Independent Test for this story.

Repeat by forcing the fix job's post-push backstop and the readiness job's
backstop (or reading a run where either already fired) to confirm the same
single-open-issue outcome at those two sites (Acceptance Scenarios 2–3).

## 2. State survives the disposition (User Story 2)

- **Re-admission ground**: on the disposed originating issue, remove
  `board:stalled` if present (it should not be — research.md D1) or any
  label at all; confirm the next `select` run does not pick it (Acceptance
  Scenario 2) — it stays `CLOSED`, so `is_excluded()`'s first branch alone
  keeps it out regardless of labels.
- **Stop request mid-flight**: on a request that hit the fix job's
  post-push breach (PR still open), post a stop-request comment on the
  originating issue (now closed) before the readiness job's next run;
  confirm the run halts before its next durable action (Acceptance
  Scenario 3, research.md D7 — no code change there, but worth one live
  confirmation since it is the one contract item this plan deliberately
  left unmodified).
- **Reopen**: `gh issue reopen <originating>` while its linked spec-request
  is still open; confirm the next `select` run does NOT re-file a second
  spec-request (FR-006 last sentence) and does NOT re-admit it (contracts/
  eligibility-and-readmission-delta.md fixture 6). Close the spec-request,
  then reopen the originating issue again; confirm this time `select`
  admits it and routes it exactly once (Acceptance Scenario 4).

## 3. Closed-without-landing notice (FR-017, Edge Cases)

Close a spec-request this loop filed without merging a final PR for it
(e.g. `gh issue close <spec-request>` by hand, in a throwaway test repo —
never on a real request). On the next `select` run:

```
gh issue view <spec-request> --json comments
gh issue view <originating> --json comments
```

Expected: one notice comment on each, stating that reopening the
originating issue returns the request to the board. Run `select` again;
confirm no second notice is posted on either issue (idempotency).

## 4. Documentation (FR-014)

`docs/setup.md`'s `board:stalled` row and
`specs/057-autonomous-board-loop/contracts/eligibility-and-selection.md`/
`contracts/labels-and-cross-links.md` state that a disposed issue's
re-admission path is reopening, not label removal alone — read them and
confirm they no longer describe label-removal as universally sufficient.
