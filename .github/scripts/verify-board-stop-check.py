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

Issue #539 adds the stop-COMMAND rule (board_stop_check.py's module
docstring): stop-command-cases.json is an accept/reject table run through
is_stop_command() and, as a lone OWNER comment after a `**Run:**` marker,
through find_stop_request(); regression-402-prose-stop.json is #402's real
owner analysis ("it should stop retrying and finish"), which must not
stop. A mutation self-test then swaps the predicate back to the pre-#539
bare `\bstop\b` word search and requires the fixtures to FAIL -- a gate
that still passed would not be guarding the rule.
"""
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import board_stop_check  # noqa: E402
from board_stop_check import find_stop_request  # noqa: E402

FIXTURES_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "tests", "board-stop-check")

EXPECTED_FILES = {
    "maintainer-stop.json", "non-maintainer-stop-ignored.json",
    "no-stop-mentioned.json", "skips-own-run.json",
    "stale-stop-predates-run.json", "first-pass-own-run-only.json",
    "evidence-link-not-a-marker.json", "regression-402-prose-stop.json",
}
COMMAND_CASES_FILE = "stop-command-cases.json"
MARKER_BODY = ("**Run:** https://github.com/example/example/actions/runs/111"
               "\n\n<!-- wing-commander-board-item: {} -->")


def run_fixtures(verbose=True):
    failures = 0
    for name in sorted(EXPECTED_FILES):
        with open(os.path.join(FIXTURES_DIR, name), encoding="utf-8") as fh:
            spec = json.load(fh)
        got = find_stop_request(spec["comments"], spec["current_run_id"])
        expected = spec["expected_run_id"]
        if got != expected:
            failures += 1
            if verbose:
                print("::error::verify-board-stop-check: {0}: expected {1!r}, "
                      "got {2!r}.".format(name, expected, got))
        elif verbose:
            print("[ok] {0}: find_stop_request() == {1!r}".format(name, got))
    return failures


def run_command_cases(verbose=True):
    with open(os.path.join(FIXTURES_DIR, COMMAND_CASES_FILE), encoding="utf-8") as fh:
        cases = json.load(fh)
    failures = 0
    for want, bodies in ((True, cases["accept"]), (False, cases["reject"])):
        for body in bodies:
            comments = [
                {"body": MARKER_BODY, "author_association": "NONE",
                 "created_at": "2026-01-01T00:00:00Z"},
                {"body": body, "author_association": "OWNER",
                 "created_at": "2026-01-01T00:05:00Z"},
            ]
            got_pred = board_stop_check.is_stop_command(body)
            got_run = find_stop_request(comments, "999")
            want_run = "111" if want else None
            if got_pred != want or got_run != want_run:
                failures += 1
                if verbose:
                    print("::error::verify-board-stop-check: {0}: {1!r}: "
                          "expected is_stop_command()={2}/run {3!r}, got "
                          "{4}/{5!r}.".format(COMMAND_CASES_FILE, body, want,
                                              want_run, got_pred, got_run))
            elif verbose:
                print("[ok] {0}: {1!r} -> {2}".format(
                    COMMAND_CASES_FILE, body, "stop" if want else "no stop"))
    return failures


def mutation_check():
    """Reverting to the pre-#539 bare word match must fail the fixtures."""
    old_re = re.compile(r"\bstop\b", re.IGNORECASE)
    original = board_stop_check.is_stop_command
    board_stop_check.is_stop_command = lambda body: bool(old_re.search(body or ""))
    try:
        caught = run_fixtures(verbose=False) + run_command_cases(verbose=False)
    finally:
        board_stop_check.is_stop_command = original
    if not caught:
        print("::error::verify-board-stop-check: mutation 'bare \\bstop\\b "
              "word match' was NOT caught by any fixture.")
        return 1
    print("note: mutation caught (bare \\bstop\\b word match fails {0} "
          "case(s)).".format(caught))
    return 0


def run():
    failures = 0

    if not os.path.isdir(FIXTURES_DIR):
        print("::error::verify-board-stop-check: fixtures directory {0} "
              "does not exist.".format(FIXTURES_DIR))
        return 1

    found = {os.path.basename(p) for p in glob.glob(os.path.join(FIXTURES_DIR, "*.json"))}
    missing = sorted((EXPECTED_FILES | {COMMAND_CASES_FILE}) - found)
    if missing:
        print("::error::verify-board-stop-check: missing fixture(s): "
              "{0}".format(", ".join(missing)))
        return 1

    failures += run_fixtures()
    failures += run_command_cases()
    failures += mutation_check()

    print("verify-board-stop-check: {0} failure(s).".format(failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(run())
