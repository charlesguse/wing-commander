#!/usr/bin/env python3
"""FR-010b: a merged fix PR whose hosting `pull_request: closed` run never
even reached `prove-gate`/`prove` (specs/060-self-redrive-concurrency
research.md D8).

WHY THIS EXISTS
---------------
contracts/concurrency-groups.md's "What does not change" section keeps this
repository's existing behaviour: the hourly schedule tick can still displace
a queued `pull_request: closed` run's own pending slot in
`wing-commander-board-loop` before that run's `prove-gate`/`prove` jobs ever
execute. Nothing about this feature's own directed-proof mechanism helps
here -- that mechanism only exists once `prove-gate` has already run and
decided `eligible`. This module detects the displacement AFTER the fact,
from durable state, so the merge is not silently forgotten.
"""
import sys

sys.path.insert(0, ".github/scripts")
from board_item_marker import read_marker_with_timestamp

RECORDED_REASON = "prove run displaced"

# research.md D6/data-model.md "Proof Record": the two board-item-marker
# steps write_marker() only ever reaches once prove-gate/prove genuinely
# ran for a merge -- "prove" for every non-success outcome_reason
# (group-busy through failure), "proven" on success. Any other step (or no
# marker at all, or one older than the merge) means neither job ever wrote
# anything for this specific merge.
PROVEN_STEPS = ("prove", "proven")


def find_undetected_merges(merged_prs, issues_by_number, bot_login):
    """research.md D8, FR-010b: an issue whose most recently merged,
    loop-labeled fix PR left no later `prove`/`proven` marker -- the
    signature of a `pull_request: closed` run displaced from its own
    pending slot before `prove-gate`/`prove` ever ran.

    `merged_prs`: `[{"issue": int, "pr": int, "merged_at": iso8601 str}, ...]`
    -- the repo's recently-merged, loop-labeled fix PRs (the same
    `Fixes #N` + board-item-marker convention `prove-gate` already reads),
    one row per issue's own most recent merge (the caller's own job to
    pre-filter to that, never this function's).

    `issues_by_number`: `{issue_number: [{"created_at": iso8601 str,
    "body": str, "user": {"login": str, "type": str}}, ...]}` -- each cited
    issue's own comments, any order.

    `bot_login`: the loop's own App login (`<slug>[bot]`), forwarded to
    `read_marker_with_timestamp()` so only the loop's own comments are read
    (board_item_marker.is_loop_marker_author(), issue #555) -- required.

    Returns `[{"issue": int, "merged_pr": int, "recorded_reason":
    "prove run displaced"}, ...]`, deterministic and code-derived
    (Principle IX) -- never an agent's read of the issue thread."""
    undetected = []
    for row in merged_prs:
        issue_number = row["issue"]
        comments = issues_by_number.get(issue_number) or []
        pair = read_marker_with_timestamp(comments, bot_login)
        if pair is not None:
            created_at, marker = pair
            if marker.get("step") in PROVEN_STEPS and created_at >= row["merged_at"]:
                continue
        undetected.append({
            "issue": issue_number,
            "merged_pr": row["pr"],
            "recorded_reason": RECORDED_REASON,
        })
    return undetected
