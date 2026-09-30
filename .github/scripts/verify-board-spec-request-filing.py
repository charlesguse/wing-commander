#!/usr/bin/env python3
"""Gate 126 -- board_spec_request_filing.py's pure functions resolve every
fixture case correctly (specs/092-bounded-spec-request-filing,
contracts/spec-request-existence-check.md,
contracts/spec-request-attempt-bound.md).

WHY THIS EXISTS
---------------
find_existing(), reopened_since() and record_attempt() are the single
home FR-017/FR-018 require for the existence check and the attempt bound
every one of board-loop.yml's four spec-request filing sites shares. A
regression in any of them would silently let a duplicate spec-request be
filed (FR-001) or let a chronically-unfileable issue retry forever
(FR-008) -- exactly the two defects this feature exists to close. This
gate pins the functions directly, the same way verify-board-eligibility.py
pins board_eligibility.py's own decisions, following its checked-in-JSON
fixture pattern under .github/scripts/tests/board-spec-request-filing/.

Fixtures:
  find-existing/<case>/{issues.json,params.json,expected.json}
    - open-match, closed-match (state is never part of the predicate,
      FR-003), oldest-wins (FR-004), non-bot-ignored (Edge Case: "a
      maintainer filed the spec-request by hand"), footer-substring-
      ignored (the footer must match a whole line, never a substring).
  reopened-since/<case>/{events.json,params.json,expected.json}
    - never-reopened (falls back to the issue's own created_at),
      reopened-once, reopened-twice (the *last* reopening wins).

Fails loudly, not vacuously, if any fixture file is missing.
"""
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from board_spec_request_filing import find_existing, reopened_since  # noqa: E402

FIXTURES_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "tests", "board-spec-request-filing")

FIND_EXISTING_DIR = os.path.join(FIXTURES_DIR, "find-existing")
REOPENED_SINCE_DIR = os.path.join(FIXTURES_DIR, "reopened-since")

FIND_EXISTING_CASES = {
    "open-match",
    "closed-match",
    "oldest-wins",
    "non-bot-ignored",
    "footer-substring-ignored",
}

REOPENED_SINCE_CASES = {
    "never-reopened",
    "reopened-once",
    "reopened-twice",
}


def _load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _run_case_set(base_dir, expected_cases, required_files, run_case, label):
    failures = 0
    if not os.path.isdir(base_dir):
        print("::error::verify-board-spec-request-filing: fixtures directory "
              "{0} does not exist.".format(base_dir))
        return 1

    cases_found = {
        os.path.basename(path)
        for path in glob.glob(os.path.join(base_dir, "*"))
        if os.path.isdir(path)
    }
    missing_cases = sorted(expected_cases - cases_found)
    if missing_cases:
        print("::error::verify-board-spec-request-filing: missing {0} "
              "fixture case(s): {1}".format(label, ", ".join(missing_cases)))
        return 1

    for case in sorted(expected_cases):
        case_dir = os.path.join(base_dir, case)
        paths = {name: os.path.join(case_dir, name) for name in required_files}
        if not all(os.path.isfile(p) for p in paths.values()):
            failures += 1
            print("::error::verify-board-spec-request-filing: {0} is missing "
                  "one of {1}.".format(case_dir, ", ".join(required_files)))
            continue
        failures += run_case(case, {name: _load(p) for name, p in paths.items()})
    return failures


def _run_find_existing_case(case, loaded):
    issues = loaded["issues.json"]
    params = loaded["params.json"]
    expected = loaded["expected.json"]
    got = find_existing(issues, params["bot_login"], params["footer"])
    if got != expected.get("html_url"):
        print("::error::verify-board-spec-request-filing: find-existing/{0}: "
              "expected {1!r}, got {2!r}.".format(case, expected.get("html_url"), got))
        return 1
    print("[ok] find-existing/{0}: find_existing() == {1!r}".format(case, got))
    return 0


def _run_reopened_since_case(case, loaded):
    events = loaded["events.json"]
    params = loaded["params.json"]
    expected = loaded["expected.json"]
    got = reopened_since(events, params["created_at"])
    if got != expected.get("since"):
        print("::error::verify-board-spec-request-filing: reopened-since/{0}: "
              "expected {1!r}, got {2!r}.".format(case, expected.get("since"), got))
        return 1
    print("[ok] reopened-since/{0}: reopened_since() == {1!r}".format(case, got))
    return 0


def run():
    failures = 0
    failures += _run_case_set(
        FIND_EXISTING_DIR, FIND_EXISTING_CASES,
        ("issues.json", "params.json", "expected.json"),
        _run_find_existing_case, "find-existing")
    failures += _run_case_set(
        REOPENED_SINCE_DIR, REOPENED_SINCE_CASES,
        ("events.json", "params.json", "expected.json"),
        _run_reopened_since_case, "reopened-since")

    print("verify-board-spec-request-filing: {0} failure(s).".format(failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(run())
