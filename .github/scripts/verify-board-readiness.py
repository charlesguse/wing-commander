#!/usr/bin/env python3
"""Gate — board_readiness.py's evaluate_from_snapshot() resolves every
FR-064 bullet-4 branch correctly, and board-loop.yml itself never calls a
merge/approve API (specs/057-autonomous-board-loop,
contracts/readiness-report.md).

WHY THIS EXISTS
---------------
FR-068 is a hard invariant: this loop never merges, approves, or enables
auto-merge. The one thing standing between "ready" and a maintainer being
told to merge stale evidence is this decision — a regression that reported
ready against a check that ran on an earlier push, or against unresolved
findings, would look identical to correct behavior on every fixture except
the one it broke. This gate pins all six documented branches.

`check_no_merge_invariant()` (T066, SC-004) is the second, structural half
of that same invariant: the six snapshot fixtures below prove the decision
logic never *reports* ready on stale/absent/failing evidence, but nothing
before T066 read board-loop.yml's own text to prove the workflow never
*acts* on readiness with a merge, approval, or auto-merge call. Textual,
line-based, in the shape verify-correlated-release-dispatch.py's Gate 59
already uses for the same kind of raw-YAML invariant.

Fixtures (FR-064 bullet 4), each a checked-in `gh pr view` JSON snapshot
under .github/scripts/tests/board-readiness/<case>/. Fails loudly, not
vacuously, if any fixture file is missing.

    python3 .github/scripts/verify-board-readiness.py
    python3 .github/scripts/verify-board-readiness.py --self-test
"""
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from board_readiness import evaluate_from_snapshot  # noqa: E402

FIXTURES_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "tests", "board-readiness")

EXPECTED_CASES = {
    "stale-check-summary", "no-checks", "open-findings",
    "backstop-breach", "kill-switch-set", "all-clear",
}

BOARD_LOOP_FILE = ".github/workflows/board-loop.yml"

# FR-068: none of these API shapes may appear anywhere in board-loop.yml.
# Matched as regexes against the raw line text so a merge call split across
# `gh pr merge "$PR" \` / `  --squash` is still caught on whichever line
# carries the flag.
FORBIDDEN_PATTERNS = [
    (re.compile(r"gh\s+pr\s+merge\b"), "a `gh pr merge` call"),
    (re.compile(r"--auto\b"), "a `--auto` (auto-merge) flag"),
    (re.compile(r"--(merge|squash|rebase)\b"), "a merge-strategy flag"),
    (re.compile(r"event=APPROVE\b"), "an `event=APPROVE` review call"),
    (re.compile(r"event=REQUEST_CHANGES\b"), "an `event=REQUEST_CHANGES` review call"),
]


def check_no_merge_invariant(lines, path=BOARD_LOOP_FILE):
    """FR-068/SC-004 (T066): fails if any forbidden merge/approve shape
    appears anywhere in `lines`. Returns a list of ::error lines, empty on
    a clean file."""
    errors = []
    for i, line in enumerate(lines):
        for pattern, label in FORBIDDEN_PATTERNS:
            if pattern.search(line):
                errors.append(
                    "{0}:{1}:{2}".format(path, i + 1, line))
                errors.append(
                    "::error::{0} contains {1} -- board-loop.yml must "
                    "never merge, approve, or enable auto-merge on any PR "
                    "(FR-068).".format(path, label))
    return errors


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

    if not os.path.isfile(BOARD_LOOP_FILE):
        failures += 1
        print("::error::verify-board-readiness: {0} does not exist -- run "
              "this gate from the repository root.".format(BOARD_LOOP_FILE))
    else:
        with open(BOARD_LOOP_FILE, encoding="utf-8") as fh:
            board_loop_lines = fh.read().splitlines()
        merge_errors = check_no_merge_invariant(board_loop_lines)
        if merge_errors:
            failures += 1
            for line in merge_errors:
                print(line)
        else:
            print("[ok] no-merge-invariant: {0} contains no merge/approve/"
                  "auto-merge call.".format(BOARD_LOOP_FILE))

    print("verify-board-readiness: {0} failure(s).".format(failures))
    return 1 if failures else 0


# One isolated line per forbidden shape, for check_no_merge_invariant()'s
# --self-test (SC-004: a fixture in both directions). Each line is written
# so it trips exactly one FORBIDDEN_PATTERNS entry; `gh api` calls carry an
# explicit `-X POST` so Gate 28 (verify-gh-api-explicit-method.py) does not
# also flag these fixture strings.
_DIRTY_SINGLE_MATCH_LINES = [
    '        run: gh pr merge "$PR_NUMBER"',
    "        run: some-other-command --auto",
    "        run: some-other-command --squash",
    "        run: some-other-command --rebase",
    '        run: gh api -X POST "repos/:owner/:repo/pulls/:number/reviews" -f event=APPROVE',
    '        run: gh api -X POST "repos/:owner/:repo/pulls/:number/reviews" -f event=REQUEST_CHANGES',
]

_CLEAN_LINES = [
    "      - name: Post the readiness report",
    '        run: gh issue comment "$ISSUE_NUMBER" --body "Ready -- awaiting a human merge."',
    "      - name: Post the review",
    '        run: gh api -X POST "repos/:owner/:repo/pulls/:number/reviews" -f event=COMMENT',
]


def self_test():
    """check_no_merge_invariant() catches each forbidden shape in isolation
    and stays silent on a clean fixture (SC-004: both directions)."""
    failures = 0

    def check(name, cond, detail=""):
        nonlocal failures
        if cond:
            print("PASS {0}".format(name))
        else:
            failures += 1
            print("FAIL {0} {1}".format(name, detail))

    clean_errors = check_no_merge_invariant(_CLEAN_LINES, path="fixture.yml")
    check("a clean fixture (report + COMMENT review) passes", not clean_errors,
          "got {0!r}".format(clean_errors))

    for dirty_line in _DIRTY_SINGLE_MATCH_LINES:
        errors = check_no_merge_invariant([dirty_line], path="fixture.yml")
        check("line {0!r} is caught, naming only itself".format(dirty_line.strip()),
              len(errors) == 2, "got {0!r}".format(errors))

    all_errors = check_no_merge_invariant(_DIRTY_SINGLE_MATCH_LINES, path="fixture.yml")
    check("every forbidden line in the dirty fixture is caught",
          len(all_errors) == 2 * len(_DIRTY_SINGLE_MATCH_LINES),
          "got {0} error line(s) for {1} dirty line(s)".format(
              len(all_errors), len(_DIRTY_SINGLE_MATCH_LINES)))

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
