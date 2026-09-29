#!/usr/bin/env python3
"""Gate — lifecycle_readiness.py's evaluate_from_snapshot() resolves every
FR-001/data-model.md "Readiness Decision" branch correctly
(specs/062-lifecycle-review-gate, contracts/readiness-and-merge.md).

WHY THIS EXISTS
---------------
Five conditions gate whether a lifecycle PR is reviewed at all: a check
that ran on a stale push, a merge conflict, or a round that already
reviewed this exact head SHA must never read as "ready" — that would
either waste a review on a PR nobody can merge yet, or skip re-review
after a genuine new push. This gate pins all six documented branches
(mirroring verify-board-readiness.py's own EXPECTED_CASES shape).

Fixtures, each a checked-in snapshot under
.github/scripts/tests/lifecycle-readiness/<case>/case.json. Fails loudly,
not vacuously, if any fixture file is missing.

    python3 .github/scripts/verify-lifecycle-readiness.py
    python3 .github/scripts/verify-lifecycle-readiness.py --self-test
"""
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lifecycle_readiness import evaluate_from_snapshot  # noqa: E402
from wc_review_gate_settled_head import self_test as _settled_head_self_test  # noqa: E402

FIXTURES_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "tests", "lifecycle-readiness")

EXPECTED_CASES = {
    "stale-check-summary", "no-checks", "not-mergeable",
    "already-reviewed-at-this-sha", "kill-switch-set", "all-clear",
}


def _load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def run():
    failures = 0

    if not os.path.isdir(FIXTURES_DIR):
        print("::error::verify-lifecycle-readiness: fixtures directory "
              "{0} does not exist.".format(FIXTURES_DIR))
        return 1

    cases_found = {
        os.path.basename(path)
        for path in glob.glob(os.path.join(FIXTURES_DIR, "*"))
        if os.path.isdir(path)
    }
    missing_cases = sorted(EXPECTED_CASES - cases_found)
    if missing_cases:
        print("::error::verify-lifecycle-readiness: missing fixture "
              "case(s): {0}".format(", ".join(missing_cases)))
        return 1

    for case in sorted(EXPECTED_CASES):
        case_path = os.path.join(FIXTURES_DIR, case, "case.json")
        if not os.path.isfile(case_path):
            failures += 1
            print("::error::verify-lifecycle-readiness: {0} is missing "
                  "case.json.".format(case_path))
            continue
        spec = _load(case_path)
        got = evaluate_from_snapshot(
            spec["snapshot"], spec.get("review_gate"),
            spec["kill_switch_paused"])
        expected = spec["expected"]

        ok = (got["ready"] == expected["ready"]
              and got.get("unmet_reason") == expected.get("unmet_reason"))
        if not ok:
            failures += 1
            print("::error::verify-lifecycle-readiness: {0}: expected "
                  "{1!r}, got {2!r}.".format(case, expected, got))
        else:
            print("[ok] {0}: ready={1!r} unmet_reason={2!r}".format(
                case, got["ready"], got.get("unmet_reason")))

    print("verify-lifecycle-readiness: {0} failure(s).".format(failures))
    return 1 if failures else 0


def self_test():
    """The five conditions are evaluated in order, and unmet_reason names
    only the first one that fails — the plain-lookup shape constitution IX
    requires, never narrated prose."""
    failures = 0

    def check(name, cond, detail=""):
        nonlocal failures
        if cond:
            print("PASS {0}".format(name))
        else:
            failures += 1
            print("FAIL {0} {1}".format(name, detail))

    # Every condition fails at once: unmet_reason names only the first
    # (checks_green), not gate_suite_green/mergeable/etc.
    got = evaluate_from_snapshot(
        {"headRefOid": "x", "statusCheckRollup": [], "mergeable": "CONFLICTING"},
        {"round": 1, "head_sha": "x", "outcome": "clean", "findings_open": 0,
         "folded_fingerprints": [], "filed_fingerprints": [], "updated_at": None},
        True)
    check("first-failing-condition-only", got["unmet_reason"] == "checks_green",
          "got {0!r}".format(got))
    check("not-ready-when-any-condition-fails", got["ready"] is False)

    # A review_gate of None (no round has ever run) is treated as
    # not-yet-reviewed, never a crash.
    got = evaluate_from_snapshot(
        {"headRefOid": "y", "statusCheckRollup": [
            {"name": "lint", "workflowName": "lint · workflows", "conclusion": "SUCCESS"}],
         "mergeable": "MERGEABLE"},
        None, False)
    check("null-review-gate-is-not-yet-reviewed", got["ready"] is True,
          "got {0!r}".format(got))

    # T069: wc_review_gate_settled_head.py -- the peel that lets `select`
    # and lifecycle_merge_preconditions.py recognise a PR whose only new
    # commit is this gate's own "review-gate: round ..." recording push as
    # still fully reviewed. Folded in here (this repository's gate suite
    # is discovered from verify-*.py/.sh invocations, wc_gate_registry.py)
    # rather than its own standalone `--self-test` workflow step, which
    # would never actually run at PR time.
    check("settled-head-peeling", _settled_head_self_test() == 0)

    print("{0} failure(s).".format(failures))
    return 1 if failures else 0


def main(argv):
    if argv == ["--self-test"]:
        return self_test()
    if argv:
        sys.exit("unknown arguments {0!r}; takes --self-test or nothing.".format(argv))
    return run()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
