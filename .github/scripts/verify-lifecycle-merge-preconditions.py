#!/usr/bin/env python3
"""Gate — lifecycle_merge_preconditions.py's evaluate_from_snapshot()
resolves every FR-026/FR-027/data-model.md §5 branch correctly
(specs/062-lifecycle-review-gate, contracts/readiness-and-merge.md).

WHY THIS EXISTS
---------------
Auto-merge is the one thing this feature does that a human action has to
undo. Eight conditions stand between a lifecycle PR and a squash merge,
and each one has to fail for its OWN stated reason: a round that was clean
at a DIFFERENT head SHA, a round that came back with findings, and a
maintainer's standing CHANGES_REQUESTED are three different refusals, and
FR-027 requires the gate to say which. This pins all four documented
branches (mirroring verify-lifecycle-readiness.py's own EXPECTED_CASES
shape).

Fixtures, each a checked-in snapshot under
.github/scripts/tests/lifecycle-merge-preconditions/<case>/case.json.
Fails loudly, not vacuously, if any fixture file is missing.

    python3 .github/scripts/verify-lifecycle-merge-preconditions.py
    python3 .github/scripts/verify-lifecycle-merge-preconditions.py --self-test
"""
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lifecycle_merge_preconditions import (  # noqa: E402
    CONDITIONS, evaluate_from_snapshot)

FIXTURES_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "tests",
    "lifecycle-merge-preconditions")

EXPECTED_CASES = {
    "round-not-clean", "unresolved-human-review",
    "head-sha-moved-since-round", "all-clear",
    "clean-round-head-matches-reviewed-sha",
}


def _load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def run():
    failures = 0

    if not os.path.isdir(FIXTURES_DIR):
        print("::error::verify-lifecycle-merge-preconditions: fixtures "
              "directory {0} does not exist.".format(FIXTURES_DIR))
        return 1

    cases_found = {
        os.path.basename(path)
        for path in glob.glob(os.path.join(FIXTURES_DIR, "*"))
        if os.path.isdir(path)
    }
    missing_cases = sorted(EXPECTED_CASES - cases_found)
    if missing_cases:
        print("::error::verify-lifecycle-merge-preconditions: missing "
              "fixture case(s): {0}".format(", ".join(missing_cases)))
        return 1

    for case in sorted(EXPECTED_CASES):
        case_path = os.path.join(FIXTURES_DIR, case, "case.json")
        if not os.path.isfile(case_path):
            failures += 1
            print("::error::verify-lifecycle-merge-preconditions: {0} is "
                  "missing case.json.".format(case_path))
            continue
        spec = _load(case_path)
        got = evaluate_from_snapshot(
            spec["snapshot"], spec.get("review_gate"),
            spec["kill_switch_paused"], spec.get("reviews") or [],
            spec.get("bot_login") or "")
        expected = spec["expected"]

        ok = (got["may_merge"] == expected["may_merge"]
              and got.get("unmet_reason") == expected.get("unmet_reason"))
        if not ok:
            failures += 1
            print("::error::verify-lifecycle-merge-preconditions: {0}: "
                  "expected {1!r}, got {2!r}.".format(case, expected, got))
        else:
            print("[ok] {0}: may_merge={1!r} unmet_reason={2!r}".format(
                case, got["may_merge"], got.get("unmet_reason")))

    print("verify-lifecycle-merge-preconditions: {0} failure(s).".format(
        failures))
    return 1 if failures else 0


def _clear_snapshot():
    return {"headRefOid": "aaaa111",
            "statusCheckRollup": [
                {"name": "lint", "workflowName": "lint · workflows",
                 "conclusion": "SUCCESS"}],
            "mergeable": "MERGEABLE"}


def _clear_gate():
    return {"round": 1, "head_sha": "aaaa111", "outcome": "clean",
            "findings_open": 0, "folded_fingerprints": [],
            "filed_fingerprints": [], "updated_at": None}


def self_test():
    """The eight conditions are evaluated in order, unmet_reason names only
    the first one that fails (constitution IX's plain lookup, never
    narrated prose), and the merge-only conditions each refuse for their
    own reason."""
    failures = 0

    def check(name, cond, detail=""):
        nonlocal failures
        if cond:
            print("PASS {0}".format(name))
        else:
            failures += 1
            print("FAIL {0} {1}".format(name, detail))

    check("eight-conditions", len(CONDITIONS) == 8,
          "got {0!r}".format(CONDITIONS))

    # Every condition fails at once: unmet_reason names only the first.
    got = evaluate_from_snapshot(
        {"headRefOid": "x", "statusCheckRollup": [],
         "mergeable": "CONFLICTING"},
        {"round": 1, "head_sha": "other", "outcome": "findings",
         "findings_open": 3, "folded_fingerprints": [],
         "filed_fingerprints": [], "updated_at": None},
        True,
        [{"author": {"login": "a-maintainer"}, "state": "CHANGES_REQUESTED"}],
        "wing-commander-bot")
    check("first-failing-condition-only", got["unmet_reason"] == "checks_green",
          "got {0!r}".format(got))
    check("not-merging-when-any-condition-fails", got["may_merge"] is False)

    # A review_gate that has never run is not a clean round at this head --
    # never a crash, and never a merge.
    got = evaluate_from_snapshot(_clear_snapshot(), None, False, [], "bot")
    check("null-review-gate-never-merges", got["may_merge"] is False
          and got["unmet_reason"] == "reviewed_at_this_head",
          "got {0!r}".format(got))

    # The bot's own COMMENT review (the one this gate itself posts every
    # round) must never block its own merge -- including when the caller
    # threads the `<slug>[bot]` spelling rather than the bare slug the
    # reviews API reports.
    for caller_spelling in ("wing-commander-bot", "wing-commander-bot[bot]"):
        got = evaluate_from_snapshot(
            _clear_snapshot(), _clear_gate(), False,
            [{"author": {"login": "wing-commander-bot"},
              "state": "CHANGES_REQUESTED"}],
            caller_spelling)
        check("own-bot-review-never-blocks[{0}]".format(caller_spelling),
              got["may_merge"] is True, "got {0!r}".format(got))

    # A human's CHANGES_REQUESTED stands until that same human approves or
    # dismisses it -- a later plain COMMENT from anyone does not clear it.
    got = evaluate_from_snapshot(
        _clear_snapshot(), _clear_gate(), False,
        [{"author": {"login": "a-maintainer"}, "state": "CHANGES_REQUESTED"},
         {"author": {"login": "a-maintainer"}, "state": "COMMENTED"}],
        "wing-commander-bot")
    check("comment-does-not-clear-changes-requested",
          got["unmet_reason"] == "no_unresolved_human_review",
          "got {0!r}".format(got))

    got = evaluate_from_snapshot(
        _clear_snapshot(), _clear_gate(), False,
        [{"author": {"login": "a-maintainer"}, "state": "CHANGES_REQUESTED"},
         {"author": {"login": "a-maintainer"}, "state": "APPROVED"}],
        "wing-commander-bot")
    check("approval-clears-changes-requested", got["may_merge"] is True,
          "got {0!r}".format(got))

    # findings_open is checked independently of outcome (contract condition
    # 7: a finding could be reopened without outcome changing).
    got = evaluate_from_snapshot(
        _clear_snapshot(), dict(_clear_gate(), findings_open=1), False, [],
        "bot")
    check("open-findings-refuse-independently",
          got["unmet_reason"] == "no_open_findings", "got {0!r}".format(got))

    # The kill switch stops a merge mid-round (FR-006/T059's edge case).
    got = evaluate_from_snapshot(
        _clear_snapshot(), _clear_gate(), True, [], "bot")
    check("kill-switch-stops-the-merge",
          got["unmet_reason"] == "kill_switch_clear", "got {0!r}".format(got))

    # T074: review_gate now lives on the lifecycle issue's own marker, never
    # a commit to the reviewed branch -- so `head_sha` is compared directly,
    # with no peel. A head that genuinely moved past the reviewed SHA (a new
    # commit landed, not this gate's own bookkeeping, which no longer
    # exists) must still refuse by name.
    got = evaluate_from_snapshot(
        dict(_clear_snapshot(), headRefOid="a-later-real-commit-sha"),
        _clear_gate(), False, [], "bot")
    check("moved-head-refuses-directly-with-no-peel",
          got["unmet_reason"] == "reviewed_at_this_head", "got {0!r}".format(got))

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
