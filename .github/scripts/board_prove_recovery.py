#!/usr/bin/env python3
"""FR-011, research.md D5: whether a board item's own `prove` marker names a
proof run that never happened at all -- displaced from its queue slot
(board_prove_displacement.RECORDED_REASON) or never correlated to a
dispatch (the literal "uncorrelated" outcome_reason, Q3) -- and is therefore
a candidate for the `select` job's own directed re-dispatch (research.md
D3/D6), at most once per stranding.

This module only judges; it never reads GitHub or writes anything. The
`select` job step that calls find_recoverable_items() is the one place that
turns a recoverable candidate into a durable dispatch + marker
(board-loop.yml "Recover a stranded prove (FR-011)").
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import board_prove_displacement  # noqa: E402
from board_item_marker import read_marker_with_timestamp  # noqa: E402

# research.md D5/D6: the one spelling of the `workflow_dispatch` input name
# a recovery dispatch sets -- imported by the board-loop.yml step and by
# verify-board-prove-recovery.py rather than re-typed (CLAUDE.md single-home).
RECOVERY_DIRECTED_INPUT = "directed-recovery"


def is_recoverable(marker):
    """True iff `marker` names a stranded, unspent prove: `step == "prove"`
    and `outcome_reason` is exactly board_prove_displacement.RECORDED_REASON
    or the literal "uncorrelated" (Q3), and `recovery_attempted` is not
    truthy. A marker with no `outcome_reason` key (every pre-feature
    marker) or a `failure`/`unfinished` reason matches neither literal and
    reads as "not recoverable" with no special case (FR-011c)."""
    if marker.get("step") != "prove":
        return False
    if marker.get("recovery_attempted"):
        return False
    return marker.get("outcome_reason") in (
        board_prove_displacement.RECORDED_REASON, "uncorrelated")


def find_recoverable_items(merged_prs_by_issue, comments_by_issue, open_issue_numbers, bot_login):
    """`merged_prs_by_issue`: the `board-recent-merges-by-issue.json` shape
    (`[{"issue": N, "pr": M, "merged_at": "..."}, ...]`). `comments_by_issue`:
    `{"<issue>": [comment, ...], ...}` (string keys, as written by the
    `select` job's own displacement step). `open_issue_numbers`: an iterable
    of currently-open issue numbers. `bot_login`: forwarded to
    `read_marker_with_timestamp()` so only the loop's own comments are read.

    Filters `merged_prs_by_issue` to issues present in `open_issue_numbers`,
    reads each one's newest marker, and returns the `is_recoverable()`
    matches as `[{"issue": N, "merged_pr": M, "marker_created_at": "...",
    "outcome_reason": "..."}, ...]`, sorted oldest-`marker_created_at`-first
    (FR-011b fairness, matching board_eligibility.select()'s own
    fallback-scan ordering)."""
    open_issue_numbers = set(open_issue_numbers)
    candidates = []
    for row in merged_prs_by_issue:
        issue = row["issue"]
        if issue not in open_issue_numbers:
            continue
        comments = comments_by_issue.get(str(issue)) or []
        pair = read_marker_with_timestamp(comments, bot_login)
        if pair is None:
            continue
        created_at, marker = pair
        if not is_recoverable(marker):
            continue
        candidates.append({
            "issue": issue,
            "merged_pr": row["pr"],
            "marker_created_at": created_at,
            "outcome_reason": marker.get("outcome_reason"),
        })
    candidates.sort(key=lambda candidate: candidate["marker_created_at"])
    return candidates
