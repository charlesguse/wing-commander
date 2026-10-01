#!/usr/bin/env python3
"""Gate 128 — board_prove_recovery.is_recoverable()/find_recoverable_items()
resolve FR-011/FR-011a/FR-011b/FR-011c correctly (specs/096-durable-prove-
entry research.md D5), and board_item_marker.write_marker()/main() carry
the two fields this feature adds (research.md D4) round-trip, including a
pre-feature marker (five keys only) reading back
`outcome_reason=None, recovery_attempted=False` rather than raising.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from board_item_marker import write_marker, read_marker_with_timestamp  # noqa: E402
from board_prove_displacement import RECORDED_REASON  # noqa: E402
from board_prove_recovery import (  # noqa: E402
    RECOVERY_DIRECTED_INPUT, is_recoverable, find_recoverable_items,
)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REPO_BOARD_LOOP = os.path.join(REPO_ROOT, ".github", "workflows", "board-loop.yml")

BOT_LOGIN = "wing-commander-bot[bot]"
BOT_USER = {"login": BOT_LOGIN, "type": "Bot"}

def marker_dict(step="prove", outcome_reason=None, recovery_attempted=False):
    return {"step": step, "round": 0, "pr": None, "branch": None, "base_sha": None,
            "outcome_reason": outcome_reason, "recovery_attempted": recovery_attempted}


IS_RECOVERABLE_CASES = [
    ("no outcome_reason key (pre-feature marker)",
     {"step": "prove", "round": 0, "pr": None, "branch": None, "base_sha": None},
     False),
    ("outcome_reason group-busy", marker_dict(outcome_reason="group-busy"), False),
    ("outcome_reason not-started", marker_dict(outcome_reason="not-started"), False),
    ("outcome_reason unfinished", marker_dict(outcome_reason="unfinished"), False),
    ("outcome_reason displaced", marker_dict(outcome_reason="displaced"), False),
    ("outcome_reason no-target", marker_dict(outcome_reason="no-target"), False),
    ("outcome_reason nothing-reaches", marker_dict(outcome_reason="nothing-reaches"), False),
    ("outcome_reason failure", marker_dict(outcome_reason="failure"), False),
    ("outcome_reason RECORDED_REASON", marker_dict(outcome_reason=RECORDED_REASON), True),
    ("outcome_reason uncorrelated", marker_dict(outcome_reason="uncorrelated"), True),
    ("RECORDED_REASON but recovery_attempted",
     marker_dict(outcome_reason=RECORDED_REASON, recovery_attempted=True), False),
    ("uncorrelated but recovery_attempted",
     marker_dict(outcome_reason="uncorrelated", recovery_attempted=True), False),
    ("step not prove", marker_dict(step="proven", outcome_reason=RECORDED_REASON), False),
]


def run_is_recoverable():
    failures = 0
    for name, marker, expected in IS_RECOVERABLE_CASES:
        got = is_recoverable(marker)
        if got != expected:
            failures += 1
            print("::error::verify-board-prove-recovery: is_recoverable {0}: "
                  "expected {1!r}, got {2!r}.".format(name, expected, got))
        else:
            print("[ok] is_recoverable {0} == {1!r}".format(name, got))
    return failures


def comment(created_at, outcome_reason=None, recovery_attempted=False, step="prove"):
    return {"created_at": created_at,
            "body": "Not proven -- " + write_marker(
                step, 0, None, None, None,
                outcome_reason=outcome_reason, recovery_attempted=recovery_attempted),
            "user": BOT_USER}


def run_find_recoverable_items():
    failures = 0

    merged_prs_by_issue = [
        {"issue": 10, "pr": 110, "merged_at": "2026-01-01T00:00:00Z"},
        {"issue": 11, "pr": 111, "merged_at": "2026-01-02T00:00:00Z"},
        {"issue": 12, "pr": 112, "merged_at": "2026-01-03T00:00:00Z"},
    ]
    comments_by_issue = {
        "10": [comment("2026-01-01T01:00:00Z", outcome_reason=RECORDED_REASON)],
        "11": [comment("2026-01-01T00:30:00Z", outcome_reason="uncorrelated")],
        "12": [comment("2026-01-03T01:00:00Z", outcome_reason=RECORDED_REASON)],
    }
    open_issue_numbers = {10, 11}  # issue 12 is excluded (not open)

    expected = [
        {"issue": 11, "merged_pr": 111, "marker_created_at": "2026-01-01T00:30:00Z",
         "outcome_reason": "uncorrelated"},
        {"issue": 10, "merged_pr": 110, "marker_created_at": "2026-01-01T01:00:00Z",
         "outcome_reason": RECORDED_REASON},
    ]
    got = find_recoverable_items(merged_prs_by_issue, comments_by_issue, open_issue_numbers, BOT_LOGIN)
    if got != expected:
        failures += 1
        print("::error::verify-board-prove-recovery: find_recoverable_items two candidates: "
              "expected {0!r}, got {1!r}.".format(expected, got))
    else:
        print("[ok] find_recoverable_items two candidates, oldest-first, excludes closed issue")

    # Issue 11 is recoverable but absent from open_issue_numbers here --
    # excluded even though its own marker would otherwise qualify.
    expected_excluding_11 = [
        {"issue": 10, "merged_pr": 110, "marker_created_at": "2026-01-01T01:00:00Z",
         "outcome_reason": RECORDED_REASON},
    ]
    got = find_recoverable_items(merged_prs_by_issue, comments_by_issue, {10}, BOT_LOGIN)
    if got != expected_excluding_11:
        failures += 1
        print("::error::verify-board-prove-recovery: find_recoverable_items issue-not-open: "
              "expected {0!r}, got {1!r}.".format(expected_excluding_11, got))
    else:
        print("[ok] find_recoverable_items excludes a candidate absent from open_issue_numbers")

    return failures


def run_marker_round_trip():
    failures = 0

    cases = [
        ("no outcome_reason/recovery_attempted (defaults)", {}, None, False),
        ("outcome_reason set, recovery_attempted false",
         {"outcome_reason": RECORDED_REASON}, RECORDED_REASON, False),
        ("outcome_reason set, recovery_attempted true",
         {"outcome_reason": "uncorrelated", "recovery_attempted": True}, "uncorrelated", True),
    ]
    for name, kwargs, expected_reason, expected_attempted in cases:
        rendered = write_marker("prove", 0, None, None, None, **kwargs)
        comment_body = "Not proven -- " + rendered
        pair = read_marker_with_timestamp(
            [{"created_at": "2026-01-01T00:00:00Z", "body": comment_body, "user": BOT_USER}],
            BOT_LOGIN)
        if pair is None:
            failures += 1
            print("::error::verify-board-prove-recovery: marker round-trip {0}: "
                  "no marker read back.".format(name))
            continue
        _created_at, marker = pair
        if marker.get("outcome_reason") != expected_reason or marker.get("recovery_attempted") != expected_attempted:
            failures += 1
            print("::error::verify-board-prove-recovery: marker round-trip {0}: "
                  "expected (outcome_reason={1!r}, recovery_attempted={2!r}), "
                  "got (outcome_reason={3!r}, recovery_attempted={4!r}).".format(
                      name, expected_reason, expected_attempted,
                      marker.get("outcome_reason"), marker.get("recovery_attempted")))
        else:
            print("[ok] marker round-trip {0}".format(name))

    # A marker written before this feature (five keys only) reads back with
    # the two new fields defaulted, rather than raising.
    pre_feature_payload = json.dumps(
        {"step": "prove", "round": 0, "pr": None, "branch": None, "base_sha": None},
        sort_keys=True)
    pre_feature_marker = "<!-- wing-commander-board-item: {0} -->".format(pre_feature_payload)
    pair = read_marker_with_timestamp(
        [{"created_at": "2026-01-01T00:00:00Z",
          "body": "Not proven -- " + pre_feature_marker, "user": BOT_USER}],
        BOT_LOGIN)
    if pair is None:
        failures += 1
        print("::error::verify-board-prove-recovery: pre-feature marker (five keys): not read back at all.")
    else:
        _created_at, marker = pair
        if marker.get("outcome_reason") is not None or marker.get("recovery_attempted"):
            failures += 1
            print("::error::verify-board-prove-recovery: pre-feature marker (five keys): "
                  "expected outcome_reason=None, recovery_attempted=False, got {0!r}.".format(marker))
        else:
            print("[ok] pre-feature marker (five keys) reads outcome_reason=None, recovery_attempted=False")

    return failures


def run_directed_recovery_input_spelling():
    """research.md D5/D6: board-loop.yml cannot import
    RECOVERY_DIRECTED_INPUT (a workflow_dispatch input name is YAML schema,
    resolved before any step runs) -- so this checks the same literal
    appears, verbatim, at the three sites that would otherwise silently
    drift from it: the input's own declaration, the recovery step's
    dispatch flag, and at least one `inputs.<name>` read."""
    failures = 0
    with open(REPO_BOARD_LOOP, encoding="utf-8") as fh:
        text = fh.read()

    declaration = "      {0}:".format(RECOVERY_DIRECTED_INPUT)
    if declaration not in text:
        failures += 1
        print("::error::verify-board-prove-recovery: board-loop.yml declares no "
              "`{0}` workflow_dispatch input (expected {1!r}).".format(
                  RECOVERY_DIRECTED_INPUT, declaration))
    else:
        print("[ok] board-loop.yml declares the `{0}` workflow_dispatch input".format(
            RECOVERY_DIRECTED_INPUT))

    dispatch_flag = "-f {0}=true".format(RECOVERY_DIRECTED_INPUT)
    if dispatch_flag not in text:
        failures += 1
        print("::error::verify-board-prove-recovery: board-loop.yml's recovery dispatch "
              "never sets `{0}` (expected {1!r}).".format(RECOVERY_DIRECTED_INPUT, dispatch_flag))
    else:
        print("[ok] board-loop.yml's recovery dispatch sets `{0}`".format(RECOVERY_DIRECTED_INPUT))

    read_expr = "inputs.{0}".format(RECOVERY_DIRECTED_INPUT)
    if text.count(read_expr) < 2:
        failures += 1
        print("::error::verify-board-prove-recovery: board-loop.yml reads `{0}` fewer than "
              "twice (expected the recovery notice and the metrics-label branch both to "
              "read it).".format(read_expr))
    else:
        print("[ok] board-loop.yml reads `{0}` at least twice".format(read_expr))

    return failures


def run():
    failures = (run_is_recoverable() + run_find_recoverable_items() + run_marker_round_trip()
                + run_directed_recovery_input_spelling())
    print("verify-board-prove-recovery: {0} failure(s).".format(failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(run())
