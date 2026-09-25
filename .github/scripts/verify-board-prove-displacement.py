#!/usr/bin/env python3
"""Gate 92 — board_prove_displacement.find_undetected_merges() resolves
FR-010b correctly (specs/060-self-redrive-concurrency research.md D8).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from board_prove_displacement import find_undetected_merges  # noqa: E402

MARKER = '<!-- wing-commander-board-item: {{"step": "{step}", "round": 0, "pr": null, "branch": null, "base_sha": null}} -->'

BOT_LOGIN = "wing-commander-bot[bot]"
BOT_USER = {"login": BOT_LOGIN, "type": "Bot"}

CASES = [
    # A later prove marker exists -- the run genuinely reached prove-gate/
    # prove and recorded something (whether or not it succeeded); not
    # flagged.
    (
        "later prove marker recorded",
        [{"issue": 1, "pr": 101, "merged_at": "2026-01-01T00:00:00Z"}],
        {1: [{"created_at": "2026-01-01T01:00:00Z",
              "body": "Not proven: -- " + MARKER.format(step="prove"),
              "user": BOT_USER}]},
        [],
    ),
    # A later proven marker (success) exists; not flagged.
    (
        "later proven marker recorded",
        [{"issue": 2, "pr": 201, "merged_at": "2026-01-01T00:00:00Z"}],
        {2: [{"created_at": "2026-01-01T01:00:00Z",
              "body": "Proven -- " + MARKER.format(step="proven"),
              "user": BOT_USER}]},
        [],
    ),
    # No marker at all after the merge -- the run never even reached
    # prove-gate/prove; flagged.
    (
        "no marker at all",
        [{"issue": 3, "pr": 301, "merged_at": "2026-01-01T00:00:00Z"}],
        {3: []},
        [{"issue": 3, "merged_pr": 301, "recorded_reason": "prove run displaced"}],
    ),
    # The latest marker predates the merge (stale, from an earlier board
    # iteration on the same issue) -- still flagged, since nothing recorded
    # anything for THIS merge.
    (
        "marker older than the merge",
        [{"issue": 4, "pr": 401, "merged_at": "2026-01-02T00:00:00Z"}],
        {4: [{"created_at": "2026-01-01T00:00:00Z",
              "body": "Readiness -- " + MARKER.format(step="readiness")}]},
        [{"issue": 4, "merged_pr": 401, "recorded_reason": "prove run displaced"}],
    ),
]


def run():
    failures = 0
    for name, merged_prs, issues_by_number, expected in CASES:
        got = find_undetected_merges(merged_prs, issues_by_number, BOT_LOGIN)
        if got != expected:
            failures += 1
            print("::error::verify-board-prove-displacement: {0}: expected "
                  "{1!r}, got {2!r}.".format(name, expected, got))
        else:
            print("[ok] {0}: find_undetected_merges() == {1!r}".format(name, got))

    print("verify-board-prove-displacement: {0} failure(s).".format(failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(run())
