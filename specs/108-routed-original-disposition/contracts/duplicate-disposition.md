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
2. **Label** (idempotent on GitHub's side regardless of the other steps'
   outcome): `gh issue edit <originating_issue> --add-label
   disposition:duplicate`.
3. **Reason comment on the originating issue** (FR-003): one comment
   stating `reason` and linking `spec_request_url`, posted only if step 1
   found it were not already present.
4. **Close** (FR-001, FR-015, research.md D2):
   `gh api -X PATCH repos/OWNER/REPO/issues/<originating_issue> -f
   state=closed -f state_reason=duplicate`. If `state` was already `CLOSED`
   for any other reason (edge case: a maintainer closed it mid-run), this
   step is skipped rather than attempted (GitHub allows re-closing but this
   contract treats "already closed" as satisfied per the edge case's own
   wording).
5. **Cross-link on the originating issue** (unchanged, FR-004): the
   existing `wing-commander-outstanding-task-item` "Routed to a spec
   proposal" checklist item (the loop files a `spec-proposal` since the
   board reset of 2026-10-01; constitution X 2.2.0), posted by the site exactly as it is today — this
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
whatever step 1's pre-check finds incomplete (FR-010). Step order matters
the other way from an earlier draft of this contract: labelling and
commenting BEFORE closing means a crash after a successful close never
strands the issue CLOSED with no `disposition:duplicate` label and no
marker. `is_excluded()` (`board_eligibility.py`) returns `(True, "closed")`
on `state == CLOSED` alone, before it ever looks at labels
(`board_eligibility.py`'s exclusion order) — so a closed-but-unlabelled
issue is never re-selected for a later run's pre-check to resume, and the
FR-017 closed-without-landing scan also can't find it without the label.
Closing last means the only way an issue ends up CLOSED is with its label
and marker already in place (maintainer review, fold leg-0: FR-006,
FR-010, FR-017).

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
| Spec-request filed, label call fails | Originating issue still OPEN, no label, no comment | Pre-check finds `disposition:duplicate` absent; re-runs from step 2 (label) |
| Spec-request filed, label succeeds, comment call fails | Originating issue OPEN + labelled, no reason comment | Pre-check's own comment-presence check (independent of labelled/closed state, per FR-009's "no duplicate comment" wording) finds it missing; re-enters at step 3 (comment) |
| Spec-request filed, label+comment succeed, close call fails | Originating issue OPEN + labelled + commented | Pre-check finds `state != CLOSED`; re-enters at step 4 (close) — never re-posts a second comment, since the comment-presence check already found its own marker |
| Everything succeeds, run re-executes disposition on the same issue anyway (idempotency drill, FR-009) | No change | Pre-check finds everything present; no-op `True` |
