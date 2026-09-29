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

It also pins the job ORDERING that lets production reach those states
(T082): every lifecycle-review-gate.yml job that reads the review_gate
marker (`wc_lifecycle_review_marker.py read`) and is not itself upstream
of the marker's writer (`... write`, `report`) must depend on that writer,
directly or transitively, and require its success in its own `if:`. A
fixture that asserts "clean round at this head merges" means nothing if
`merge` can read the marker before this round's value lands.

Fixtures, each a checked-in snapshot under
.github/scripts/tests/lifecycle-merge-preconditions/<case>/case.json.
Fails loudly, not vacuously, if any fixture file is missing.

    python3 .github/scripts/verify-lifecycle-merge-preconditions.py
    python3 .github/scripts/verify-lifecycle-merge-preconditions.py --self-test
"""
import copy
import glob
import json
import os
import re
import sys

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lifecycle_merge_preconditions import (  # noqa: E402
    CONDITIONS, evaluate_from_snapshot)

FIXTURES_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "tests",
    "lifecycle-merge-preconditions")

WORKFLOW = os.path.join(".github", "workflows", "lifecycle-review-gate.yml")
MARKER_SCRIPT = "wc_lifecycle_review_marker.py"


def _needs(job):
    needs = (job or {}).get("needs") or []
    return [needs] if isinstance(needs, str) else list(needs)


def _ancestors(jobs, job_id):
    seen, stack = set(), list(_needs(jobs.get(job_id)))
    while stack:
        dep = stack.pop()
        if dep not in seen:
            seen.add(dep)
            stack.extend(_needs(jobs.get(dep)))
    return seen


def _marker_jobs(jobs, verb):
    pattern = re.compile(re.escape(MARKER_SCRIPT) + r"\s+" + verb + r"\b")
    return sorted(
        job_id for job_id, job in jobs.items()
        if any(pattern.search(str((step or {}).get("run") or ""))
               for step in (job or {}).get("steps") or []))


def ordering_problems(doc):
    """T082: every marker reader downstream of the writer waits for it."""
    jobs = (doc or {}).get("jobs") or {}
    writers = _marker_jobs(jobs, "write")
    readers = _marker_jobs(jobs, "read")
    problems = []
    if len(writers) != 1:
        return ["expected exactly one review_gate marker writer job, found "
                "{0!r}".format(writers)]
    if "merge" not in readers:
        problems.append("the merge job no longer reads the review_gate "
                        "marker -- this check has lost its subject")
    writer = writers[0]
    upstream_of_writer = _ancestors(jobs, writer)
    for reader in readers:
        if reader == writer or reader in upstream_of_writer:
            continue  # reads the PRIOR round by design (select/review/...)
        if writer not in _ancestors(jobs, reader):
            problems.append("job {0!r} reads the review_gate marker but does "
                            "not depend on its writer {1!r}".format(
                                reader, writer))
            continue
        cond = str(jobs[reader].get("if") or "")
        if not re.search(r"needs\.{0}\.result\s*==\s*'success'".format(
                re.escape(writer)), cond):
            problems.append("job {0!r} reads the review_gate marker but its "
                            "if: does not require needs.{1}.result == "
                            "'success'".format(reader, writer))
    return problems


def run_ordering():
    with open(WORKFLOW, encoding="utf-8") as fh:
        doc = yaml.safe_load(fh)
    problems = ordering_problems(doc)
    for problem in problems:
        print("::error::verify-lifecycle-merge-preconditions: {0}: {1}".format(
            WORKFLOW, problem))
    if not problems:
        print("[ok] marker-ordering: every downstream review_gate reader "
              "waits for its writer")
    return len(problems)


EXPECTED_CASES = {
    "round-not-clean", "unresolved-human-review",
    "head-sha-moved-since-round", "all-clear",
    "clean-round-head-matches-reviewed-sha",
}


def _load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def run():
    failures = run_ordering()

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

    # T082: the shipped workflow orders merge after report, and dropping
    # either half of that ordering (the needs: edge, or the success check
    # in the if:) is caught.
    with open(WORKFLOW, encoding="utf-8") as fh:
        shipped = yaml.safe_load(fh)
    check("marker-ordering-shipped-clean", ordering_problems(shipped) == [],
          "got {0!r}".format(ordering_problems(shipped)))

    dropped_edge = copy.deepcopy(shipped)
    dropped_edge["jobs"]["merge"]["needs"] = [
        n for n in _needs(dropped_edge["jobs"]["merge"]) if n != "report"]
    got = ordering_problems(dropped_edge)
    check("marker-ordering-dropped-needs-edge-caught",
          any("does not depend on its writer" in p for p in got),
          "got {0!r}".format(got))

    dropped_if = copy.deepcopy(shipped)
    dropped_if["jobs"]["merge"]["if"] = re.sub(
        r"\s*&&\s*needs\.report\.result\s*==\s*'success'", "",
        str(dropped_if["jobs"]["merge"]["if"]))
    got = ordering_problems(dropped_if)
    check("marker-ordering-dropped-success-check-caught",
          any("does not require needs.report.result" in p for p in got),
          "got {0!r}".format(got))

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
