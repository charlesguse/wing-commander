#!/usr/bin/env python3
"""Gate — board_readiness.py's evaluate_from_snapshot() resolves every
FR-064 bullet-4 branch correctly (specs/057-autonomous-board-loop,
contracts/readiness-report.md).

WHY THIS EXISTS
---------------
FR-068 is a hard invariant: this loop never merges, approves, or enables
auto-merge. The one thing standing between "ready" and a maintainer being
told to merge stale evidence is this decision — a regression that reported
ready against a check that ran on an earlier push, or against unresolved
findings, would look identical to correct behavior on every fixture except
the one it broke. This gate pins all six documented branches.

Fixtures (FR-064 bullet 4), each a checked-in `gh pr view` JSON snapshot
under .github/scripts/tests/board-readiness/<case>/. Fails loudly, not
vacuously, if any fixture file is missing.
"""
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from board_readiness import evaluate_from_snapshot  # noqa: E402

FIXTURES_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "tests", "board-readiness")

EXPECTED_CASES = {
    "stale-check-summary", "no-checks", "open-findings",
    "backstop-breach", "kill-switch-set", "all-clear",
}


def _load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def run():
    failures = 0

    if not os.path.isdir(FIXTURES_DIR):
        print("::error::verify-board-readiness: fixtures directory {0} "
              "does not exist.".format(FIXTURES_DIR))
        return 1

    cases_found = {
        os.path.basename(path)
        for path in glob.glob(os.path.join(FIXTURES_DIR, "*"))
        if os.path.isdir(path)
    }
    missing_cases = sorted(EXPECTED_CASES - cases_found)
    if missing_cases:
        print("::error::verify-board-readiness: missing fixture case(s): "
              "{0}".format(", ".join(missing_cases)))
        return 1

    for case in sorted(EXPECTED_CASES):
        case_path = os.path.join(FIXTURES_DIR, case, "case.json")
        if not os.path.isfile(case_path):
            failures += 1
            print("::error::verify-board-readiness: {0} is missing "
                  "case.json.".format(case_path))
            continue
        spec = _load(case_path)
        got = evaluate_from_snapshot(
            spec["snapshot"], spec["open_in_scope_findings"],
            spec["backstop_holds"], spec["kill_switch_paused"])
        expected = spec["expected"]

        ok = got["ready"] == expected["ready"]
        if expected.get("reason_contains"):
            ok = ok and expected["reason_contains"] in (got.get("unmet_reason") or "")
        if not ok:
            failures += 1
            print("::error::verify-board-readiness: {0}: expected {1!r}, "
                  "got {2!r}.".format(case, expected, got))
        else:
            print("[ok] {0}: ready={1!r} unmet_reason={2!r}".format(
                case, got["ready"], got.get("unmet_reason")))

    print("verify-board-readiness: {0} failure(s).".format(failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(run())
