#!/usr/bin/env python3
"""Fail a pull request whose title, body or commits would close a tracking issue.

WHY THIS EXISTS
---------------
The open `disposition:tracking` issues (the Maintenance backlog, the Roadmap,
Board status, ...) are meant to stay open for good: waiver registers cite
them as trackers, and Gate 124 (verify-waiver-citations.py --check-open)
turns main red the moment one closes. Seven batch PRs titled
"Fix #889 batch: ..." closed the Maintenance backlog through GitHub's
closing keyword anyway, and every close turned main red until someone
reopened it. Gate 124 runs on pushes to main and on the schedule, never on
a pull request, so nothing caught the keyword before the merge.

This check runs on every pull request (pr-closing-keyword-guard.yml, no
paths: filter, and on `edited` too, so a body changed after the last push
is checked again) and fails when any of these would close an open
`disposition:tracking` issue:

  title     GitHub reads closing keywords in a PR title and body when the
  body      PR merges into the default branch.
  commits   This repository squashes with COMMIT_MESSAGES and allows merge
            and rebase merges, so every commit message on the PR reaches
            main and its keywords close issues too.

The set of tracking issues is read LIVE from the label (an ordinary REST
issues listing, not GraphQL), never from a constant here: the label is the
one home, so a new tracking issue is guarded the day it is labelled.

A keyword is close/closes/closed, fix/fixes/fixed, resolve/resolves/
resolved, any case, then a colon or whitespace, then a reference: `#N`,
`GH-N`, `owner/repo#N` for this repository, or this repository's issue URL.
The pattern is board_backlog_lines.CLOSING_RE, the board loop's keyword
hold's own (its one home; verify-board-backlog-lines.py fails if a copy
reappears here), read through closing_keyword_refs(). Write
"addresses #889" or "(#889)" instead.

Usage:
  python3 .github/scripts/verify-pr-closing-keywords.py            # live, CI
  python3 .github/scripts/verify-pr-closing-keywords.py --self-test

Live mode reads PR_TITLE, PR_BODY, PR_NUMBER, GITHUB_REPOSITORY and GH_TOKEN
from the environment (the workflow passes the title and body through env:,
never into the script text).
"""
import argparse
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from board_backlog_lines import closing_keyword_refs  # noqa: E402

LABEL = "disposition:tracking"


def find_violations(sources, repo, tracking):
    """sources: [(where, text)]; tracking: set of open tracking issue numbers."""
    bad = []
    for where, text in sources:
        for n, hit in closing_keyword_refs(text, repo):
            if n in tracking:
                bad.append((where, n, hit))
    return bad


def _gh_json(path):
    r = subprocess.run(
        ["gh", "api", "--paginate", "--slurp", path],
        capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"gh api {path} failed: {r.stderr.strip()}")
    pages = json.loads(r.stdout)
    return [item for page in pages for item in page]


def tracking_issues(repo):
    items = _gh_json(
        f"repos/{repo}/issues?labels={LABEL}&state=open&per_page=100")
    return {i["number"] for i in items if "pull_request" not in i}


def pr_commit_messages(repo, number):
    items = _gh_json(f"repos/{repo}/pulls/{number}/commits?per_page=100")
    return [(f"commit {c['sha'][:8]}", c["commit"]["message"]) for c in items]


def report(bad):
    for where, n, hit in bad:
        print(f"::error::PR {where} uses the closing keyword {hit!r} on "
              f"#{n}, an open {LABEL} issue; merging would close it and turn "
              f"main red at Gate 124. Write 'addresses #{n}' or '(#{n})'.")


def live():
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    number = os.environ.get("PR_NUMBER", "")
    if not repo or not number.isdigit():
        print("::error::GITHUB_REPOSITORY and PR_NUMBER must be set")
        return 2
    try:
        tracking = tracking_issues(repo)
        commits = pr_commit_messages(repo, number)
    except (RuntimeError, ValueError, KeyError) as e:
        print(f"::error::could not read the PR or the {LABEL} issues: {e}")
        return 2
    sources = [("title", os.environ.get("PR_TITLE", "")),
               ("body", os.environ.get("PR_BODY", ""))] + commits
    bad = find_violations(sources, repo, tracking)
    if bad:
        report(bad)
        return 1
    print(f"ok: no closing keyword on the open {LABEL} issues "
          f"({', '.join(f'#{n}' for n in sorted(tracking)) or 'none open'}) "
          f"in the title, body or {len(commits)} commit message(s)")
    return 0


def self_test():
    repo = "owner/repo"
    tracking = {889, 890}
    fail_cases = [
        "Fix #889 batch: rebase decide fails closed",
        "fixes #889",
        "FIXED: #890",
        "Closes:#889",
        "closed #889",
        "Resolve #889",
        "resolves: #889",
        "RESOLVED #890",
        "close #889",
        "This is it.\n\nfix #889\n",
        "Fixes owner/repo#889",
        "fixes OWNER/Repo#889",
        "Closes https://github.com/owner/repo/issues/889",
        "(fix #889)",
        "Fixes #1, fixes #889",
        "Fixes GH-889",
    ]
    pass_cases = [
        "Maintenance (#889): one line",
        "addresses #889",
        "prefix #889",
        "Fix #8890 batch",
        "Fix #88 batch",
        "Fixes #1234",
        "fixes other/repo#889",
        "Closes https://github.com/other/repo/issues/889",
        "fixed-up #889",
        "fix a bug (#889)",
        "Fix the backlog edit; see #889",
        "",
    ]
    failures = 0
    for text in fail_cases:
        if not find_violations([("body", text)], repo, tracking):
            print(f"FAIL: expected a violation for {text!r}")
            failures += 1
    for text in pass_cases:
        bad = find_violations([("body", text)], repo, tracking)
        if bad:
            print(f"FAIL: expected no violation for {text!r}, got {bad}")
            failures += 1
    # Only open tracking issues count: the same keyword on a closed or
    # non-tracking issue is the ordinary way to close it.
    if find_violations([("title", "Fixes #889")], repo, {890}):
        print("FAIL: #889 is not in the tracking set but was flagged")
        failures += 1
    # Every source is read: a commit message alone must fail.
    bad = find_violations(
        [("title", "Maintenance (#889): x"), ("body", "addresses #889"),
         ("commit deadbeef", "fix(x): y\n\nFixes #889")], repo, tracking)
    if [b[0] for b in bad] != ["commit deadbeef"]:
        print(f"FAIL: commit message violation not attributed: {bad}")
        failures += 1
    # Live mode never takes the PR text from argv or the script text.
    src = open(__file__, encoding="utf-8").read()
    for name in ("PR_TITLE", "PR_BODY"):
        if f'os.environ.get("{name}"' not in src:
            print(f"FAIL: live mode no longer reads {name} from env")
            failures += 1
    if failures:
        print(f"self-test: {failures} failure(s)")
        return 1
    print(f"self-test: {len(fail_cases)} violating and {len(pass_cases)} "
          "clean texts, the tracking-set filter and commit attribution "
          "all behave")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    return self_test() if args.self_test else live()


if __name__ == "__main__":
    sys.exit(main())
