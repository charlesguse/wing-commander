#!/usr/bin/env python3
"""Gate — board_stop_check.py's find_stop_request() resolves every
documented branch correctly (specs/057-autonomous-board-loop, research.md
D17, FR-052/FR-053).

WHY THIS EXISTS
---------------
The stop path is the one mechanism a maintainer relies on to halt an
in-flight item -- a regression that let a non-maintainer's "stop" cancel a
run (or that cancelled the run's own just-posted announcement) would look
identical to correct behavior on every fixture except the one it broke.

Fixtures, each a checked-in comments/expected-run-id pair under
.github/scripts/tests/board-stop-check/. Fails loudly, not vacuously, if
any fixture file is missing.
"""
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from board_stop_check import find_stop_request  # noqa: E402

FIXTURES_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "tests", "board-stop-check")

EXPECTED_FILES = {
    "maintainer-stop.json", "non-maintainer-stop-ignored.json",
    "no-stop-mentioned.json", "skips-own-run.json",
    "stale-stop-predates-run.json", "first-pass-own-run-only.json",
    "evidence-link-not-a-marker.json",
}


def run():
    failures = 0

    if not os.path.isdir(FIXTURES_DIR):
        print("::error::verify-board-stop-check: fixtures directory {0} "
              "does not exist.".format(FIXTURES_DIR))
        return 1

    found = {os.path.basename(p) for p in glob.glob(os.path.join(FIXTURES_DIR, "*.json"))}
    missing = sorted(EXPECTED_FILES - found)
    if missing:
        print("::error::verify-board-stop-check: missing fixture(s): "
              "{0}".format(", ".join(missing)))
        return 1

    for name in sorted(EXPECTED_FILES):
        with open(os.path.join(FIXTURES_DIR, name), encoding="utf-8") as fh:
            spec = json.load(fh)
        got = find_stop_request(spec["comments"], spec["current_run_id"])
        expected = spec["expected_run_id"]
        if got != expected:
            failures += 1
            print("::error::verify-board-stop-check: {0}: expected {1!r}, "
                  "got {2!r}.".format(name, expected, got))
        else:
            print("[ok] {0}: find_stop_request() == {1!r}".format(name, got))

    print("verify-board-stop-check: {0} failure(s).".format(failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(run())
