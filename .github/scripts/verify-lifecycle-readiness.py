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
after a genuine new push. This gate pins all six documented branches,
plus two cases for the gate's own commit status, which is never an
input to readiness; context_pin_problems() ties that status's name to
the workflow's own status writes
(mirroring verify-board-readiness.py's own EXPECTED_CASES shape).

Fixtures, each a checked-in snapshot under
.github/scripts/tests/lifecycle-readiness/<case>/case.json. Fails loudly,
not vacuously, if any fixture file is missing.

    python3 .github/scripts/verify-lifecycle-readiness.py
    python3 .github/scripts/verify-lifecycle-readiness.py --self-test
"""
import ast
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lifecycle_readiness import (  # noqa: E402
    OWN_STATUS_CONTEXT, SELECT_CONDITIONS, evaluate_from_snapshot, select_prefilter)
from wc_lifecycle_review_marker import self_test as _marker_self_test  # noqa: E402

FIXTURES_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "tests", "lifecycle-readiness")

WORKFLOW = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "workflows",
    "lifecycle-review-gate.yml")
CONTEXT_WRITE_RE = re.compile(r'-f\s+context=["\']?([^"\'\s\\]+)')


def context_pin_problems(workflow_text):
    """Every commit status the workflow writes must use the context
    lifecycle_readiness.py filters out as the gate's own. A rename on one
    side only would silently bring back the deadlock the filter exists to
    prevent, with every snapshot fixture still green."""
    found = CONTEXT_WRITE_RE.findall(workflow_text)
    if not found:
        return ["no `-f context=` status write found in lifecycle-review-gate.yml"]
    return ["status write uses context {0!r}, but lifecycle_readiness."
            "OWN_STATUS_CONTEXT is {1!r}".format(c, OWN_STATUS_CONTEXT)
            for c in found if c != OWN_STATUS_CONTEXT]


LIFECYCLE_READINESS = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "lifecycle_readiness.py")
# The checks rules have one home, board_readiness.py (#889); a pasted copy
# brings these literals back (CLAUDE.md "Shared logic has exactly one home").
# Read from the module's syntax tree, so quote style or an `in` instead of
# `==` cannot hide one (code review of #1226, pass 3).
COPIED_RULE_LITERALS = ("SUCCESS", "NEUTRAL", "SKIPPED", "lint")
# Each wrapper's body is its docstring and one `return board_readiness.<fn>(...)`.
DELEGATES = {"_checks_green": "checks_green", "_gate_suite_green": "gate_suite_green"}


def _docstring_nodes(tree):
    nodes = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(
                    getattr(body[0], "value", None), ast.Constant) and isinstance(
                    body[0].value.value, str):
                nodes.add(id(body[0].value))
    return nodes


def _delegates_only(func, target):
    body = list(func.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(
            getattr(body[0], "value", None), ast.Constant):
        body = body[1:]
    if len(body) != 1 or not isinstance(body[0], ast.Return):
        return False
    call = body[0].value
    return (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
            and call.func.attr == target and isinstance(call.func.value, ast.Name)
            and call.func.value.id == "board_readiness")


def single_home_problems(source):
    """lifecycle_readiness.py calls board_readiness.py's checks rules
    rather than re-typing them (code review of #1226, passes 1 and 3)."""
    tree = ast.parse(source)
    docstrings = _docstring_nodes(tree)
    problems = ["lifecycle_readiness.py contains {0!r} (line {1}), a copy of a "
                "board_readiness.py checks rule".format(node.value, node.lineno)
                for node in ast.walk(tree)
                if isinstance(node, ast.Constant) and isinstance(node.value, str)
                and id(node) not in docstrings and node.value in COPIED_RULE_LITERALS]
    funcs = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
    for name, target in sorted(DELEGATES.items()):
        if name not in funcs or not _delegates_only(funcs[name], target):
            problems.append("lifecycle_readiness.py's {0} is not just `return "
                            "board_readiness.{1}(...)`".format(name, target))
    return problems


EXPECTED_CASES = {
    "stale-check-summary", "no-checks", "not-mergeable",
    "already-reviewed-at-this-sha", "kill-switch-set", "all-clear",
    "own-status-error-ignored", "own-status-only",
    # #889 (found by the code review of #1196): only each check's newest
    # result counts, for select_prefilter as for the full decision.
    "cancelled-superseded-ready", "cancelled-newest-not-ready",
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

    # #889: select_prefilter() agrees with the full decision on every
    # fixture whose unmet condition is one select applies, and accepts the
    # ones that fail only a condition select leaves to its own filters.
    for case in sorted(EXPECTED_CASES):
        spec = _load(os.path.join(FIXTURES_DIR, case, "case.json"))
        full = evaluate_from_snapshot(spec["snapshot"], spec.get("review_gate"),
                                      spec["kill_switch_paused"])
        want = full["unmet_reason"] if full["unmet_reason"] in SELECT_CONDITIONS else None
        got = select_prefilter(spec["snapshot"])
        if got != {"ready": want is None, "unmet_reason": want}:
            failures += 1
            print("::error::verify-lifecycle-readiness: {0}: select_prefilter "
                  "returned {1!r}, expected unmet_reason {2!r}.".format(case, got, want))
        else:
            print("[ok] {0}: select_prefilter unmet_reason={1!r}".format(case, want))

    with open(WORKFLOW, encoding="utf-8") as fh:
        problems = context_pin_problems(fh.read())
    for problem in problems:
        failures += 1
        print("::error::verify-lifecycle-readiness: {0}".format(problem))
    if not problems:
        print("[ok] every status write uses context {0!r}".format(
            OWN_STATUS_CONTEXT))

    with open(LIFECYCLE_READINESS, encoding="utf-8") as fh:
        problems = single_home_problems(fh.read())
    for problem in problems:
        failures += 1
        print("::error::verify-lifecycle-readiness: {0}".format(problem))
    if not problems:
        print("[ok] lifecycle_readiness.py calls board_readiness.py's checks rules")

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

    # T074: wc_lifecycle_review_marker.py -- review_gate's actual storage
    # now that it no longer lives in spec-meta.json (F3). Folded in here
    # (this repository's gate suite is discovered from verify-*.py/.sh
    # invocations, wc_gate_registry.py) rather than its own standalone
    # `--self-test` workflow step, which would never actually run at PR
    # time -- the same idiom T069 established for the module this one
    # replaces (wc_review_gate_settled_head.py, deleted by T075).
    check("lifecycle-review-marker", _marker_self_test() == 0)

    # The own-status pin: a renamed status write, or none at all, fails.
    good = '            -f context="{0}" \\\n'.format(OWN_STATUS_CONTEXT)
    check("context-pin-clean", context_pin_problems(good * 3) == [])
    check("context-pin-renamed-write-caught",
          len(context_pin_problems(good + good.replace(
              OWN_STATUS_CONTEXT, "lifecycle-review")))== 1)
    check("context-pin-no-write-caught", len(context_pin_problems("")) == 1)

    # The single-home check: the real module is clean, and the copy this
    # module carried before #889 is caught.
    with open(LIFECYCLE_READINESS, encoding="utf-8") as fh:
        real = fh.read()
    check("single-home-clean", single_home_problems(real) == [],
          repr(single_home_problems(real)))
    pasted = real.replace(
        "board_readiness.checks_green(", "_old_checks_green(").replace(
        "return board_readiness.gate_suite_green(rollup)",
        'return any(e.get("name") == "lint" and (e.get("conclusion") or "").upper() '
        'in ("SUCCESS", "NEUTRAL", "SKIPPED") for e in rollup)')
    check("single-home-copy-caught", len(single_home_problems(pasted)) >= 4,
          repr(single_home_problems(pasted)))
    # A copy in single quotes, beside the delegating calls, is caught too.
    beside = real.replace(
        "    return board_readiness.gate_suite_green(rollup)",
        "    for e in rollup:\n"
        "        if e.get('name') in ('lint',) and e.get('conclusion') in ('SUCCESS',):\n"
        "            return True\n"
        "    return board_readiness.gate_suite_green(rollup)")
    check("single-home-single-quoted-copy-caught", len(single_home_problems(beside)) >= 3,
          repr(single_home_problems(beside)))

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
