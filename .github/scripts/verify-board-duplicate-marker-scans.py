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
    notice (#874). Only the spec-request the issue's NEWEST duplicate
    marker names is "current", and only its closure may tell the issue
    that reopening returns the request to the board (FR-006, FR-017): a
    superseded one's notice goes on the spec-request alone, in words that
    say so (board_closed_without_landing.post_notices()).

Neither helper was held to being the only home: a workflow heredoc could
go back to calling the marker readers inline and nothing would fail
(#888). This gate pins both helpers' behaviour with direct unit cases, and
fails if any board-loop.yml run: block that deals in duplicate markers
calls a marker reader itself rather than the helper -- checked per
heredoc, so an unrelated marker read elsewhere in the same step is not a
false positive. Each MUTATION puts a pre-fix shape back and asserts the
suite then fails.

Usage: python3 .github/scripts/verify-board-duplicate-marker-scans.py
"""
import os
import re
import sys

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import board_closed_without_landing  # noqa: E402
import board_eligibility  # noqa: E402
from board_item_marker import find_markers_matching, read_marker_with_timestamp, write_marker  # noqa: E402

BOARD_LOOP = ".github/workflows/board-loop.yml"
BOT = "wing-commander-bot[bot]"
MARKER_READERS = ("read_marker_with_timestamp(", "find_latest_marker_matching(",
                  "find_markers_matching(", "find_latest_marker(", "read_marker(",
                  "last_marker_match(", "MARKER_RE")
DUPLICATE_SIGNS = ("DUPLICATE_STEP", '"duplicate"', "'duplicate'")
HEREDOC_RE = re.compile(r"<<-?\s*'?(\w+)'?[^\n]*\n(.*?)\n\s*\1\b", re.S)
# A multi-line `python3 -c "..."` program is checked the same way.
PYTHON_C_RE = re.compile(r'python3\s+(?:-I\s+)?-c\s+"(.*?)"\s*\)?', re.S)
JQ_DUPLICATE_RE = re.compile(r"\.step\s*==\s*\\?\"duplicate\\?\"")

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
    out.append(("an issue disposed, reopened and re-routed maps BOTH spec-requests (#874), "
                "only the newest as current (FR-006)",
                got == {100: {"issue": 11, "current": False}, 200: {"issue": 11, "current": True}},
                repr(got)))
    later = {"12": [comment("duplicate", "2026-01-01T00:00:00Z", 300),
                    comment("route", "2026-01-02T00:00:00Z")]}
    got = fn(later, BOT)
    out.append(("a later route marker does not hide the duplicate one, which stays current",
                got == {300: {"issue": 12, "current": True}}, repr(got)))
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
                got == {500: {"issue": 16, "current": True}}, repr(got)))
    return out


def resolve_cases(fn):
    """-> list of (name, ok, detail) for spec_request_numbers_to_resolve."""
    out = []
    labelled = [{"name": board_eligibility.DISPOSITION_LABEL}]
    issues = [{"number": 21, "state": "OPEN", "labels": labelled},
              {"number": 22, "state": "CLOSED", "labels": labelled},
              {"number": 23, "state": "OPEN", "labels": []},
              {"number": 24, "state": "OPEN", "labels": labelled},
              {"number": 25, "state": "OPEN", "labels": labelled}]
    comments = {"21": [comment("duplicate", "2026-01-01T00:00:00Z", 600),
                       comment("route", "2026-01-02T00:00:00Z")],
                22: [comment("duplicate", "2026-01-01T00:00:00Z", 700)],
                "23": [comment("duplicate", "2026-01-01T00:00:00Z", 800)],
                "24": [comment("route", "2026-01-01T00:00:00Z")],
                "25": [comment("duplicate", "2026-01-01T00:00:00Z", 900),
                       comment("duplicate", "2026-01-03T00:00:00Z", 950)]}
    got = fn(issues, comments, BOT)
    out.append(("only open labelled issues resolve, each through its NEWEST duplicate marker, "
                "even under a later route marker (#888)", got == [600, 950], repr(got)))
    return out


def notice_cases(post_notices):
    """-> list of (name, ok, detail) for the closed-without-landing notices."""
    out = []

    class Proc(object):
        returncode = 0
        stdout = ""
        stderr = ""

    calls = []

    def run(args, **_kwargs):
        calls.append(list(args))
        return Proc()

    superseded = {"number": 100, "spec_meta": None, "comments": [],
                  "originating_issue": None, "originating_comments": None, "superseded_on": 11}
    current = {"number": 200, "spec_meta": None, "comments": [],
               "originating_issue": 11, "originating_comments": [], "superseded_on": None}
    failed = post_notices([superseded], "o/r", run=run)
    posted_on = [c[3] for c in calls if c[:3] == ["gh", "issue", "comment"]]
    bodies = " ".join(c[-1] for c in calls)
    out.append(("a superseded spec-request is told alone, in words that say it was superseded (#874)",
                failed == 0 and posted_on == ["100"] and "routed to a newer spec-request" in bodies
                and "returns the request to the board." not in bodies, repr(calls)))
    del calls[:]
    failed = post_notices([current], "o/r", run=run)
    posted_on = [c[3] for c in calls if c[:3] == ["gh", "issue", "comment"]]
    out.append(("the current spec-request's closure tells both it and its originating issue",
                failed == 0 and posted_on == ["200", "11"], repr(calls)))
    return out


def _overall_newest_originating(comments_by_issue, bot_login):
    """The pre-#874 scan: each issue's overall-newest marker only."""
    found = {}
    for number, comments in comments_by_issue.items():
        pair = read_marker_with_timestamp(comments, bot_login)
        if pair is None or pair[1].get("step") != board_eligibility.DUPLICATE_STEP:
            continue
        try:
            found[int(pair[1].get("spec_request"))] = {"issue": int(number), "current": True}
        except (TypeError, ValueError):
            continue
    return found


def _every_marker_current(comments_by_issue, bot_login):
    """The first #874 fix, before its review: every duplicate marker mapped
    and every one treated as current."""
    found = {}
    for number, comments in comments_by_issue.items():
        try:
            issue = int(number)
        except (TypeError, ValueError):
            continue
        for _created_at, marker in find_markers_matching(
                comments, bot_login, lambda m: m.get("step") == board_eligibility.DUPLICATE_STEP):
            try:
                found[int(marker.get("spec_request"))] = {"issue": issue, "current": True}
            except (TypeError, ValueError):
                continue
    return found


def _oldest_duplicate_resolve(open_issues, comments_by_issue, bot_login):
    numbers = set()
    for issue in open_issues:
        if (issue.get("state") or "").upper() != "OPEN":
            continue
        if board_eligibility.DISPOSITION_LABEL not in {
                (label or {}).get("name") for label in issue.get("labels") or []}:
            continue
        comments = comments_by_issue.get(issue["number"]) or comments_by_issue.get(str(issue["number"])) or []
        found = find_markers_matching(
            comments, bot_login, lambda m: m.get("step") == board_eligibility.DUPLICATE_STEP)
        if found:
            numbers.add(int(found[0][1].get("spec_request")))
    return sorted(numbers)


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
    """Heredocs that deal in duplicate markers yet call a marker reader,
    and any jq program selecting on the duplicate step, in run: blocks."""
    bad = []
    for where, run in blocks:
        programs = [("heredoc " + name, body) for name, body in HEREDOC_RE.findall(run)]
        programs += [("python3 -c", body) for body in PYTHON_C_RE.findall(run)]
        for label, body in programs:
            if any(sign in body for sign in DUPLICATE_SIGNS) and any(r in body for r in MARKER_READERS):
                bad.append("{0} ({1})".format(where, label))
        if JQ_DUPLICATE_RE.search(run):
            bad.append("{0} (jq selects on the duplicate step)".format(where))
    return bad


def suite(originating_fn, resolve_fn, blocks, quiet=False,
          post_notices=board_closed_without_landing.post_notices):
    failed = []
    for name, ok, detail in (originating_cases(originating_fn) + resolve_cases(resolve_fn)
                             + notice_cases(post_notices)):
        if not ok:
            failed.append(name)
        if not quiet:
            check(name, ok, detail)
    bad = inline_scans(blocks)
    texts = "\n".join(run for _where, run in blocks)
    ok = not bad and "originating_issues_by_spec_request(" in texts \
        and "spec_request_numbers_to_resolve(" in texts and 'named["current"]' in texts
    if not ok:
        failed.append("single home")
    if not quiet:
        check("board-loop.yml reads duplicate markers only through the two helpers",
              ok, "inline scans in: {0}".format(bad or "none; a helper call is missing"))
    return failed


# The pre-#874 heredoc shape, put back into one block for the static check.
REINLINED = '''python3 - <<'PYEOF'
from board_eligibility import DUPLICATE_STEP
from board_item_marker import read_marker_with_timestamp
for number_str, comments in disposed_comments.items():
    pair = read_marker_with_timestamp(comments, bot_login)
PYEOF
'''
JQ_INLINED = '''jq '[.[] | select(.step == "duplicate")]' markers.json'''
PYTHON_C_INLINED = '''spec="$(python3 -c "
from board_item_marker import read_marker_with_timestamp
pair = read_marker_with_timestamp(comments, bot)
print(pair[1]['spec_request'] if pair and pair[1].get('step') == 'duplicate' else '')
")"'''


def _post_notices_ignoring_superseded(spec_requests, repository, run=None):
    """post_notices() without its #874 superseded branch."""
    stripped = [dict(entry, superseded_on=None) for entry in spec_requests]
    return board_closed_without_landing.post_notices(stripped, repository, run=run)


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
        ("a jq program selects on the duplicate step inline",
         board_eligibility.originating_issues_by_spec_request,
         board_eligibility.spec_request_numbers_to_resolve,
         blocks + [("mutated / jq scan", JQ_INLINED)]),
        ("a python3 -c program scans duplicate markers inline",
         board_eligibility.originating_issues_by_spec_request,
         board_eligibility.spec_request_numbers_to_resolve,
         blocks + [("mutated / python -c scan", PYTHON_C_INLINED)]),
        ("every duplicate marker treated as current (the first #874 fix)",
         _every_marker_current, board_eligibility.spec_request_numbers_to_resolve, blocks),
        ("the re-admission pre-read takes the oldest duplicate marker",
         board_eligibility.originating_issues_by_spec_request, _oldest_duplicate_resolve, blocks),
    )
    for name, originating_fn, resolve_fn, mutated_blocks in mutations:
        check("mutation caught: " + name,
              bool(suite(originating_fn, resolve_fn, mutated_blocks, quiet=True)),
              "the suite stayed green with this rule reverted")
    check("mutation caught: a superseded spec-request told 'reopening returns it to the board'",
          bool(suite(board_eligibility.originating_issues_by_spec_request,
                     board_eligibility.spec_request_numbers_to_resolve, blocks, quiet=True,
                     post_notices=_post_notices_ignoring_superseded)),
          "the suite stayed green with this rule reverted")
    if failures:
        print("verify-board-duplicate-marker-scans: {0} failure(s)".format(len(failures)))
        sys.exit(1)
    print("verify-board-duplicate-marker-scans: ok")


if __name__ == "__main__":
    main()
