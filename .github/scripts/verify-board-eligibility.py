#!/usr/bin/env python3
"""Gate — board_eligibility.py's classify_issue() resolves every FR-064
bullet-2 branch correctly (specs/057-autonomous-board-loop,
contracts/eligibility-and-selection.md).

WHY THIS EXISTS
---------------
FR-008's whole point is that eligibility is decided from the `labeled`
timeline event's actor, never from label presence alone. A regression that
went back to "label present == eligible" would look identical to correct
behavior on every case except the one where the bot applies the same label
a maintainer could have -- exactly the branch this gate exists to pin.

Fixtures (FR-064 bullet 2), each a checked-in issue.json + timeline.json
pair under .github/scripts/tests/board-eligibility/<case>/:
  - maintainer-authored-no-label -> "maintainer-authored"
  - maintainer-applied-label     -> "maintainer-labeled"
  - bot-applied-same-label       -> "ineligible" (NOT admitted)
  - pipeline-only-label          -> "pipeline-labeled"

Fails loudly, not vacuously, if any fixture file is missing.
"""
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from board_eligibility import classify_issue  # noqa: E402

FIXTURES_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "tests", "board-eligibility")

EXPECTED = {
    "maintainer-authored-no-label": "maintainer-authored",
    "maintainer-applied-label": "maintainer-labeled",
    "bot-applied-same-label": "ineligible",
    "pipeline-only-label": "pipeline-labeled",
}


def _load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def run():
    failures = 0

    if not os.path.isdir(FIXTURES_DIR):
        print("::error::verify-board-eligibility: fixtures directory {0} "
              "does not exist.".format(FIXTURES_DIR))
        return 1

    cases_found = {
        os.path.basename(path)
        for path in glob.glob(os.path.join(FIXTURES_DIR, "*"))
        if os.path.isdir(path)
    }
    missing_cases = sorted(set(EXPECTED) - cases_found)
    if missing_cases:
        print("::error::verify-board-eligibility: missing fixture case(s): "
              "{0}".format(", ".join(missing_cases)))
        return 1

    for case, expected in sorted(EXPECTED.items()):
        case_dir = os.path.join(FIXTURES_DIR, case)
        issue_path = os.path.join(case_dir, "issue.json")
        timeline_path = os.path.join(case_dir, "timeline.json")
        if not os.path.isfile(issue_path) or not os.path.isfile(timeline_path):
            failures += 1
            print("::error::verify-board-eligibility: {0} is missing "
                  "issue.json or timeline.json.".format(case_dir))
            continue
        issue = _load(issue_path)
        timeline = _load(timeline_path)
        got = classify_issue(issue, timeline)
        if got != expected:
            failures += 1
            print("::error::verify-board-eligibility: {0}: expected {1!r}, "
                  "got {2!r}.".format(case, expected, got))
        else:
            print("[ok] {0}: classify_issue() == {1!r}".format(case, got))

    print("verify-board-eligibility: {0} failure(s).".format(failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(run())
