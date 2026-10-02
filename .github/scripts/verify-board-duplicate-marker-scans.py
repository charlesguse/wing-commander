#!/usr/bin/env python3
"""The board loop's two duplicate-marker scans have one home each, and each
reads every duplicate marker it needs.

WHY THIS EXISTS
---------------
An issue disposed as a duplicate carries a step == "duplicate" marker
naming its spec-request. Two board-loop steps read those markers:

  - select's re-admission pre-read, through
    board_eligibility.spec_request_numbers_to_resolve(): the newest
    duplicate marker on each open labelled issue, never the issue's
    overall-newest marker, which a later route/fix marker supersedes;
  - the closed-without-landing scan, through
    board_eligibility.originating_issues_by_spec_request(): EVERY
    duplicate marker on every disposed issue. It used to read only each
    issue's overall-newest marker, so an issue disposed, reopened and
    re-routed to a second spec-request lost the first spec-request's
    notice (#874).

Neither helper was held to being the only home: a workflow heredoc could
go back to calling the marker readers inline and nothing would fail
(#888). This gate pins both helpers' behaviour with direct unit cases, and
fails if any board-loop.yml run: block that deals in duplicate markers
calls a marker reader itself rather than the helper. Each MUTATION puts a
pre-fix shape back and asserts the suite then fails.

Usage: python3 .github/scripts/verify-board-duplicate-marker-scans.py
"""
import os
import re
import sys

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import board_eligibility  # noqa: E402
from board_item_marker import read_marker_with_timestamp, write_marker  # noqa: E402

BOARD_LOOP = ".github/workflows/board-loop.yml"
BOT = "wing-commander-bot[bot]"
MARKER_READERS = ("read_marker_with_timestamp(", "find_latest_marker_matching(",
                  "find_markers_matching(", "find_latest_marker(", "read_marker(")
DUPLICATE_SIGNS = ("DUPLICATE_STEP", '"duplicate"', "'duplicate'")

failures = []


def check(name, cond, detail=""):
    if cond:
        print("[ok] {0}".format(name))
    else:
        failures.append(name)
        print("::error::verify-board-duplicate-marker-scans: {0} -- {1}".format(name, detail))


def comment(step, when, spec_request=None, login=BOT, kind="Bot"):
    body = "status\n\n" + write_marker(step, 0, None, None, None, spec_request=spec_request)
    return {"created_at": when, "body": body, "user": {"login": login, "type": kind}}


def originating_cases(fn):
    """-> list of (name, ok, detail) for originating_issues_by_spec_request."""
    out = []
    rerouted = {"11": [comment("duplicate", "2026-01-01T00:00:00Z", 100),
                       comment("route", "2026-01-02T00:00:00Z"),
                       comment("duplicate", "2026-01-03T00:00:00Z", 200),
                       comment("fix", "2026-01-04T00:00:00Z")]}
    got = fn(rerouted, BOT)
    out.append(("an issue disposed, reopened and re-routed maps BOTH spec-requests (#874)",
                got == {100: 11, 200: 11}, repr(got)))
    later = {"12": [comment("duplicate", "2026-01-01T00:00:00Z", 300),
                    comment("route", "2026-01-02T00:00:00Z")]}
    got = fn(later, BOT)
    out.append(("a later route marker does not hide the duplicate one",
                got == {300: 12}, repr(got)))
    foreign = {"13": [comment("duplicate", "2026-01-01T00:00:00Z", 400, login="someone", kind="User")]}
    got = fn(foreign, BOT)
    out.append(("a duplicate marker someone else posted is ignored", got == {}, repr(got)))
    junk = {"14": [comment("duplicate", "2026-01-01T00:00:00Z", "not-a-number")], "x": []}
    got = fn(junk, BOT)
    out.append(("a non-numeric spec_request or issue key is skipped", got == {}, repr(got)))
    both = {"15": [comment("duplicate", "2026-01-01T00:00:00Z", 500)],
            "16": [comment("duplicate", "2026-01-05T00:00:00Z", 500)]}
    got = fn(both, BOT)
    out.append(("two issues naming one spec-request: the newest marker wins",
                got == {500: 16}, repr(got)))
    return out


def resolve_cases(fn):
    """-> list of (name, ok, detail) for spec_request_numbers_to_resolve."""
    out = []
    labelled = [{"name": board_eligibility.DISPOSITION_LABEL}]
    issues = [{"number": 21, "state": "OPEN", "labels": labelled},
              {"number": 22, "state": "CLOSED", "labels": labelled},
              {"number": 23, "state": "OPEN", "labels": []},
              {"number": 24, "state": "OPEN", "labels": labelled}]
    comments = {"21": [comment("duplicate", "2026-01-01T00:00:00Z", 600),
                       comment("route", "2026-01-02T00:00:00Z")],
                22: [comment("duplicate", "2026-01-01T00:00:00Z", 700)],
                "23": [comment("duplicate", "2026-01-01T00:00:00Z", 800)],
                "24": [comment("route", "2026-01-01T00:00:00Z")]}
    got = fn(issues, comments, BOT)
    out.append(("only open labelled issues resolve, through their newest duplicate marker "
                "even under a later route marker (#888)", got == [600], repr(got)))
    return out


def _overall_newest_originating(comments_by_issue, bot_login):
    """The pre-#874 scan: each issue's overall-newest marker only."""
    found = {}
    for number, comments in comments_by_issue.items():
        pair = read_marker_with_timestamp(comments, bot_login)
        if pair is None or pair[1].get("step") != board_eligibility.DUPLICATE_STEP:
            continue
        try:
            found[int(pair[1].get("spec_request"))] = int(number)
        except (TypeError, ValueError):
            continue
    return found


def _overall_newest_resolve(open_issues, comments_by_issue, bot_login):
    numbers = set()
    for issue in open_issues:
        if (issue.get("state") or "").upper() != "OPEN":
            continue
        if board_eligibility.DISPOSITION_LABEL not in {
                (label or {}).get("name") for label in issue.get("labels") or []}:
            continue
        comments = comments_by_issue.get(issue["number"]) or comments_by_issue.get(str(issue["number"])) or []
        pair = read_marker_with_timestamp(comments, bot_login)
        if pair is None or pair[1].get("step") != board_eligibility.DUPLICATE_STEP:
            continue
        numbers.add(int(pair[1].get("spec_request")))
    return sorted(numbers)


def run_blocks(path):
    doc = yaml.safe_load(open(path, encoding="utf-8")) or {}
    for job_name, job in (doc.get("jobs") or {}).items():
        for step in (job or {}).get("steps") or []:
            run = (step or {}).get("run")
            if run:
                yield "{0} / {1}".format(job_name, (step or {}).get("name")), str(run)


def inline_scans(blocks):
    """run: blocks that deal in duplicate markers yet call a marker reader."""
    bad = []
    for where, run in blocks:
        if any(sign in run for sign in DUPLICATE_SIGNS) and any(r in run for r in MARKER_READERS):
            bad.append(where)
    return bad


def suite(originating_fn, resolve_fn, blocks, quiet=False):
    failed = []
    for name, ok, detail in originating_cases(originating_fn) + resolve_cases(resolve_fn):
        if not ok:
            failed.append(name)
        if not quiet:
            check(name, ok, detail)
    bad = inline_scans(blocks)
    texts = "\n".join(run for _where, run in blocks)
    ok = not bad and "originating_issues_by_spec_request(" in texts \
        and "spec_request_numbers_to_resolve(" in texts
    if not ok:
        failed.append("single home")
    if not quiet:
        check("board-loop.yml reads duplicate markers only through the two helpers",
              ok, "inline scans in: {0}".format(bad or "none; a helper call is missing"))
    return failed


# The pre-#874 heredoc shape, put back into one block for the static check.
REINLINED = '''from board_eligibility import DUPLICATE_STEP
from board_item_marker import read_marker_with_timestamp
for number_str, comments in disposed_comments.items():
    pair = read_marker_with_timestamp(comments, bot_login)
'''


def main():
    blocks = list(run_blocks(BOARD_LOOP))
    suite(board_eligibility.originating_issues_by_spec_request,
          board_eligibility.spec_request_numbers_to_resolve, blocks)
    mutations = (
        ("the closed-without-landing map reads only the overall-newest marker (pre-#874)",
         _overall_newest_originating, board_eligibility.spec_request_numbers_to_resolve, blocks),
        ("the re-admission pre-read reads only the overall-newest marker",
         board_eligibility.originating_issues_by_spec_request, _overall_newest_resolve, blocks),
        ("a board-loop heredoc scans duplicate markers inline again (#888)",
         board_eligibility.originating_issues_by_spec_request,
         board_eligibility.spec_request_numbers_to_resolve,
         blocks + [("mutated / inline scan", REINLINED)]),
    )
    for name, originating_fn, resolve_fn, mutated_blocks in mutations:
        check("mutation caught: " + name,
              bool(suite(originating_fn, resolve_fn, mutated_blocks, quiet=True)),
              "the suite stayed green with this rule reverted")
    if failures:
        print("verify-board-duplicate-marker-scans: {0} failure(s)".format(len(failures)))
        sys.exit(1)
    print("verify-board-duplicate-marker-scans: ok")


if __name__ == "__main__":
    main()
