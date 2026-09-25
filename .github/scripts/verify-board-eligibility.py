#!/usr/bin/env python3
"""Gate — board_eligibility.py's classify_issue() resolves every FR-064
bullet-2 branch correctly (specs/057-autonomous-board-loop,
contracts/eligibility-and-selection.md), and in_flight_candidate() resolves
every FR-012 fixture case correctly (specs/061-marker-owned-in-flight,
contracts/in-flight-detection.md).

WHY THIS EXISTS
---------------
FR-008's whole point is that eligibility is decided from the `labeled`
timeline event's actor, never from label presence alone. A regression that
went back to "label present == eligible" would look identical to correct
behavior on every case except the one where the bot applies the same label
a maintainer could have -- exactly the branch this gate exists to pin.

FR-011/FR-012's whole point is that "is this issue an in-flight board item
of mine?" has exactly one home (in_flight_candidate()) and that home is
fixture-tested, so a regression that widened the decision back to reading
pull request bodies fails this gate rather than surfacing three weeks later
as a mis-selected issue in production.

Fixtures (FR-064 bullet 2), each a checked-in issue.json + timeline.json
pair under .github/scripts/tests/board-eligibility/<case>/:
  - maintainer-authored-no-label -> "maintainer-authored"
  - maintainer-applied-label     -> "maintainer-labeled"
  - bot-applied-same-label       -> "ineligible" (NOT admitted)
  - pipeline-only-label          -> "pipeline-labeled"

In-flight fixtures (FR-012), each a checked-in open_issues.json +
comments_by_issue.json + pr_state_by_number.json + expected.json set under
.github/scripts/tests/board-eligibility/in-flight/<case>/ -- see
contracts/in-flight-detection.md for the full case list. A case
whose expected.json also carries "select_issue_number" additionally
requires a labeled_events_by_issue.json and gets its result asserted
against select() itself, not just in_flight_candidate() -- used by
prove-no-pr to also pin that select()'s oldest-first fallback, not only
the priority path, skips a stuck `prove` marker (Maintainer Feedback,
board_eligibility.py's select()), and by the four awaiting-merge-* cases
(#532) to pin that a ready-and-handed-over item never holds the board:
never in-flight, passed over by the fallback while its PR is OPEN (or its
state is unknown), and eligible again once that PR is CLOSED or MERGED.
Each awaiting-merge-* case puts the awaiting-merge issue OLDEST, so
reverting the fallback skip makes select() return it and fails the case.

Fails loudly, not vacuously, if any fixture file is missing.
"""
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from board_eligibility import (  # noqa: E402
    AWAITING_MERGE_STEP, FIX_OR_LATER_STEPS, classify_issue, in_flight_candidate, select)

FIXTURES_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "tests", "board-eligibility")

IN_FLIGHT_FIXTURES_DIR = os.path.join(FIXTURES_DIR, "in-flight")

EXPECTED = {
    "maintainer-authored-no-label": "maintainer-authored",
    "maintainer-applied-label": "maintainer-labeled",
    "bot-applied-same-label": "ineligible",
    "pipeline-only-label": "pipeline-labeled",
}

IN_FLIGHT_CASES = {
    "no-marker",
    "pre-fix-no-pr",
    "fix-or-later-pr-open",
    "fix-or-later-pr-closed",
    "fix-or-later-pr-merged",
    "terminal-step",
    "excluded-issue",
    "unparsable-marker",
    "two-non-terminal",
    "unrelated-pr-no-marker",
    "prove-no-pr",
    "awaiting-merge-pr-open",
    "awaiting-merge-pr-closed",
    "awaiting-merge-pr-merged",
    "awaiting-merge-pr-unknown",
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

    if not os.path.isdir(IN_FLIGHT_FIXTURES_DIR):
        print("::error::verify-board-eligibility: fixtures directory {0} "
              "does not exist.".format(IN_FLIGHT_FIXTURES_DIR))
        return 1

    in_flight_cases_found = {
        os.path.basename(path)
        for path in glob.glob(os.path.join(IN_FLIGHT_FIXTURES_DIR, "*"))
        if os.path.isdir(path)
    }
    missing_in_flight_cases = sorted(IN_FLIGHT_CASES - in_flight_cases_found)
    if missing_in_flight_cases:
        print("::error::verify-board-eligibility: missing in-flight fixture "
              "case(s): {0}".format(", ".join(missing_in_flight_cases)))
        return 1

    for case in sorted(IN_FLIGHT_CASES):
        case_dir = os.path.join(IN_FLIGHT_FIXTURES_DIR, case)
        open_issues_path = os.path.join(case_dir, "open_issues.json")
        comments_path = os.path.join(case_dir, "comments_by_issue.json")
        pr_state_path = os.path.join(case_dir, "pr_state_by_number.json")
        expected_path = os.path.join(case_dir, "expected.json")
        if not all(os.path.isfile(p) for p in
                   (open_issues_path, comments_path, pr_state_path, expected_path)):
            failures += 1
            print("::error::verify-board-eligibility: {0} is missing one of "
                  "open_issues.json, comments_by_issue.json, "
                  "pr_state_by_number.json, expected.json.".format(case_dir))
            continue

        open_issues = _load(open_issues_path)
        comments_by_issue = {
            int(number): comments
            for number, comments in _load(comments_path).items()
        }
        pr_state_by_number = {
            int(number): state
            for number, state in _load(pr_state_path).items()
        }
        expected = _load(expected_path)

        issue_number, multiple_found = in_flight_candidate(
            open_issues, comments_by_issue, pr_state_by_number)
        got = {"issue_number": issue_number, "multiple_found": multiple_found}
        expected_in_flight = {
            "issue_number": expected.get("issue_number"),
            "multiple_found": expected.get("multiple_found"),
        }
        if got != expected_in_flight:
            failures += 1
            print("::error::verify-board-eligibility: in-flight/{0}: expected "
                  "{1!r}, got {2!r}.".format(case, expected_in_flight, got))
        else:
            print("[ok] in-flight/{0}: in_flight_candidate() == {1!r}".format(case, got))

        if "select_issue_number" in expected:
            labeled_events_path = os.path.join(case_dir, "labeled_events_by_issue.json")
            if not os.path.isfile(labeled_events_path):
                failures += 1
                print("::error::verify-board-eligibility: {0} declares "
                      "select_issue_number in expected.json but is missing "
                      "labeled_events_by_issue.json.".format(case_dir))
                continue
            labeled_events_by_issue = {
                int(number): events
                for number, events in _load(labeled_events_path).items()
            }
            selected = select(open_issues, labeled_events_by_issue,
                               comments_by_issue, pr_state_by_number)
            expected_selected = expected["select_issue_number"]
            if selected != expected_selected:
                failures += 1
                print("::error::verify-board-eligibility: in-flight/{0}: "
                      "select() expected {1!r}, got {2!r}.".format(
                          case, expected_selected, selected))
            else:
                print("[ok] in-flight/{0}: select() == {1!r} (oldest-first "
                      "fallback)".format(case, selected))

    # #532: the select job's PR-state lookup pass resolves only PRs named
    # by FIX_OR_LATER_STEPS markers. Without awaiting-merge in that set,
    # _awaiting_merge_holds() only ever sees an unknown state and a
    # handed-over item drops off the board forever, even after its PR
    # closes. (Gate 97 also runs the workflow's lookup heredoc itself.)
    if AWAITING_MERGE_STEP not in FIX_OR_LATER_STEPS:
        failures += 1
        print("::error::verify-board-eligibility: AWAITING_MERGE_STEP is not in "
              "FIX_OR_LATER_STEPS -- the select job would never look up an "
              "awaiting-merge marker's PR, so the item could never become "
              "eligible again (#532).")
    else:
        print("[ok] AWAITING_MERGE_STEP is in FIX_OR_LATER_STEPS (select looks up its PR)")

    print("verify-board-eligibility: {0} failure(s).".format(failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(run())
