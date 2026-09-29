# Contract: Duplicate Disposition

Single home for FR-001/FR-003/FR-004/FR-009/FR-010/FR-011/FR-015. A new
Python module (name TBD by tasks.md, shaped like
`.github/scripts/board_item_marker.py`'s `add_stalled_label()`), called
identically from board-loop.yml's three spec-request sites (FR-002):
route's spec-verdict step, fix's post-push-breach step, and readiness's
backstop-breach step (both the fresh-file and the reuse-an-existing-
spec-request paths).

## Operation shape

```python
def dispose_as_duplicate(originating_issue: int, spec_request_issue: int,
                          spec_request_url: str, reason: str) -> bool:
    """Closes `originating_issue` as a duplicate of `spec_request_issue`
    (FR-001/FR-015), idempotently (FR-009), leaving a state a maintainer
    can read and a later run can finish on partial failure (FR-010/FR-011).
    Returns True on success (including the already-disposed no-op case),
    False on any failure -- the caller fails its own step on False, the
    same way add_stalled_label()'s callers do today."""
```

## Sequence

1. **Idempotency pre-check** (FR-009, data-model.md's Disposition
   invariant): read `originating_issue`'s current `state` and `labels`
   (`gh issue view`). If `state == CLOSED` and `disposition:duplicate` is
   already present, return `True` without any further call.
2. **Close** (FR-001, FR-015, research.md D2):
   `gh api -X PATCH repos/OWNER/REPO/issues/<originating_issue> -f
   state=closed -f state_reason=duplicate`. If `state` was already `CLOSED`
   for any other reason (edge case: a maintainer closed it mid-run), this
   step is skipped rather than attempted (GitHub allows re-closing but this
   contract treats "already closed" as satisfied per the edge case's own
   wording), and the sequence continues to step 3.
3. **Label**: `gh issue edit <originating_issue> --add-label
   disposition:duplicate` (idempotent on GitHub's side regardless of step
   1's outcome).
4. **Reason comment on the originating issue** (FR-003): one comment
   stating `reason` and linking `spec_request_url`, posted only if step 1
   found it were not already present.
5. **Cross-link on the originating issue** (unchanged, FR-004): the
   existing `wing-commander-outstanding-task-item` "Routed to spec-request"
   checklist item, posted by the site exactly as it is today — this
   contract does not move that call, only sequences the new steps around
   it.
6. **Reciprocal cross-link on the spec-request** (FR-004, research.md D5):
   a second `wing-commander-outstanding-task-item` call, `issue-number:
   spec_request_issue`, a new phrase (e.g. `"Filed for the routed
   original"`), `artifact-url` the originating issue's URL. Skipped if
   step 1 found this comment already present (same idempotency rule).
7. **Marker**: `board_item_marker.write_marker("duplicate", round=0,
   pr=None, branch=None, base_sha=None)` extended with `spec_request=
   spec_request_issue` (data-model.md's Board Item Marker), posted as the
   step's own status comment — same shape every other marker write uses,
   never a second announcement convention.

Any failure at steps 2–7 returns `False`; the caller's step fails the job
(no `continue-on-error`), so a later run re-enters at step 1 and finishes
whatever step 1's pre-check finds incomplete (FR-010). Step order matters:
closing before commenting means a crash between steps 2 and 4 still leaves
the issue excluded from selection (`state == CLOSED` alone already excludes
it — data-model.md), so a maintainer reading it mid-failure sees a closed
issue that is not yet explained, never an open issue silently orphaned.

## Guard interaction with Gate 93 check 3 (#514)

The existing create-guard (`_create_guard_problems` in
`verify-issue-context-single-home.py`) already treats `gh issue close` as
an action that must not run before the spec-request URL is captured and
guarded (`ACT_BEFORE_GUARD_RE` already matches `gh\s+issue\s+...close`).
`dispose_as_duplicate()` is therefore only ever called AFTER that existing
guard passes — this contract adds no new ordering requirement Gate 93
doesn't already enforce, it only adds a new occupant to the "after the
guard" side of that boundary.

## Failure semantics table (FR-010/FR-011, for tasks.md's fixtures)

| Scenario | State left behind | Next run's behaviour |
|---|---|---|
| Create guard fails (spec-request never filed) | Originating issue untouched, no `disposition:duplicate`, no marker change | Retries the create from scratch (unchanged create-guard behaviour, FR-011) |
| Spec-request filed, close call fails | Originating issue still OPEN, no label, no comment | Idempotency pre-check finds `state != CLOSED`; re-runs from step 2 |
| Spec-request filed, close succeeds, label call fails | Originating issue CLOSED, no `disposition:duplicate` label yet | Pre-check's "already disposed" test requires BOTH closed AND labelled, so it re-enters at step 3 |
| Spec-request filed, close+label succeed, comment fails | Originating issue CLOSED + labelled, no reason comment | Pre-check treats closed+labelled as the "already disposed" signal for skipping steps 2–3, but comment-presence is checked independently per FR-009's "no duplicate comment" wording — the module checks for its own comment marker before posting, not merely closed+labelled, so a missing comment is still added |
| Everything succeeds, run re-executes disposition on the same issue anyway (idempotency drill, FR-009) | No change | Pre-check finds everything present; no-op `True` |
