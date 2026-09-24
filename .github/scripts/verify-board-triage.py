#!/usr/bin/env python3
"""Gate — board_triage.py's triage() and _first_divergent_pin() resolve
every FR-064 bullet-1 branch correctly (specs/057-autonomous-board-loop,
contracts/triage.md).

WHY THIS EXISTS
---------------
Triage is the one place this feature is allowed to close an issue with no
human in the loop. A regression that closed on an agent's say-so, or that
missed a genuine 429, would be invisible on every fixture except the exact
one it broke -- this gate pins all six documented branches, including the
one FR-012 exists to forbid (an "already fixed" proposal must NOT close).

Fixtures (FR-064 bullet 1), each a checked-in transcript/workflow-pin pair
under .github/scripts/tests/board-triage/<case>/. Fails loudly, not
vacuously, if any fixture file is missing.
"""
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from board_triage import triage, _first_divergent_pin  # noqa: E402

FIXTURES_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "tests", "board-triage")

TRIAGE_CASES = {
    "429-present": {"outcome": "closed", "ground": "rate_limit"},
    "429-absent-genuine-failure": {"outcome": "proceed", "ground": None},
    "evidence-unavailable": {"outcome": "proceed", "ground": "evidence_unavailable"},
    "already-fixed-proposal": {"outcome": "handover", "ground": "already_fixed_proposal"},
}
PIN_CASES = {
    "action-bump-ahead": "divergent",
    "pins-equal": "none",
}
EXPECTED = dict.fromkeys(list(TRIAGE_CASES) + list(PIN_CASES))

CWD = os.getcwd()


def _load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def run():
    failures = 0

    if not os.path.isdir(FIXTURES_DIR):
        print("::error::verify-board-triage: fixtures directory {0} does "
              "not exist.".format(FIXTURES_DIR))
        return 1

    cases_found = {
        os.path.basename(path)
        for path in glob.glob(os.path.join(FIXTURES_DIR, "*"))
        if os.path.isdir(path)
    }
    missing_cases = sorted(set(EXPECTED) - cases_found)
    if missing_cases:
        print("::error::verify-board-triage: missing fixture case(s): "
              "{0}".format(", ".join(missing_cases)))
        return 1

    for case, expected in sorted(TRIAGE_CASES.items()):
        case_dir = os.path.join(FIXTURES_DIR, case)
        issue_path = os.path.join(case_dir, "issue.json")
        if not os.path.isfile(issue_path):
            failures += 1
            print("::error::verify-board-triage: {0} is missing "
                  "issue.json.".format(case_dir))
            continue
        issue = _load(issue_path)
        # Fixture-declared transcript paths are repo-root-relative;
        # normalise against this process's own cwd so the gate is safe to
        # invoke from any directory.
        transcript_path = issue.get("cited_run_transcript_path")
        if transcript_path and not os.path.isabs(transcript_path):
            issue = dict(issue)
            issue["cited_run_transcript_path"] = os.path.join(CWD, transcript_path)
        got = triage(issue, cited_run="https://github.com/example/example/actions/runs/1")
        ok = got.get("outcome") == expected["outcome"] and got.get("ground") == expected["ground"]
        if case == "already-fixed-proposal" and got.get("outcome") == "closed":
            ok = False  # FR-012: never a close ground, regardless of anything else
        if not ok:
            failures += 1
            print("::error::verify-board-triage: {0}: expected outcome={1!r} "
                  "ground={2!r}, got {3!r}.".format(
                      case, expected["outcome"], expected["ground"], got))
        else:
            print("[ok] {0}: triage() == outcome={1!r} ground={2!r}".format(
                case, got.get("outcome"), got.get("ground")))

    for case, expected in sorted(PIN_CASES.items()):
        case_dir = os.path.join(FIXTURES_DIR, case)
        pins_path = os.path.join(case_dir, "pins.json")
        if not os.path.isfile(pins_path):
            failures += 1
            print("::error::verify-board-triage: {0} is missing "
                  "pins.json.".format(case_dir))
            continue
        pins = _load(pins_path)
        got = _first_divergent_pin(
            pins["workflow_file"], pins["run_pins"], pins["main_pins"])
        got_shape = "divergent" if got is not None else "none"
        if got_shape != expected:
            failures += 1
            print("::error::verify-board-triage: {0}: expected {1!r}, "
                  "got {2!r} ({3!r}).".format(case, expected, got_shape, got))
        else:
            print("[ok] {0}: _first_divergent_pin() == {1!r}".format(case, got))

    print("verify-board-triage: {0} failure(s).".format(failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(run())
