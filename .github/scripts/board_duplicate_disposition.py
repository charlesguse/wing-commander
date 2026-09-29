#!/usr/bin/env python3
"""Duplicate disposition of a routed original issue (specs/
108-routed-original-disposition, contracts/duplicate-disposition.md,
research.md D1-D5).

The single home for closing an issue the board loop routed to a
spec-request, as a duplicate of that spec-request (REST `state_reason:
duplicate`), labelling it `disposition:duplicate`, and posting the reason
comment -- called identically from board-loop.yml's three spec-request
sites (route's spec-verdict step, fix's post-push-breach step, readiness's
backstop-breach step), replacing three inline close/label/comment copies
with one (CLAUDE.md "shared logic has exactly one home").

Idempotent (FR-009): every mutating step is gated on its own pre-check
read of the originating issue's live state/labels/comments, so a run that
finds everything already in place makes no further `gh` call at all.
Failure semantics (FR-010/FR-011): any `gh` failure returns False
immediately, leaving the issue in whatever partial state the failed
attempt reached -- the next run's own pre-check resumes at whichever step
was left undone, never re-filing a second spec-request or re-posting a
duplicate comment.
"""
import argparse
import json
import os
import subprocess
import sys

# `python3 -I` (the board-loop.yml pristine-snapshot invocation shape used
# at the fix/readiness call sites) excludes this script's own directory
# from sys.path, so the board_item_marker import below would otherwise
# raise ModuleNotFoundError -- see board_item_marker.py's own main() for
# the same fix (maintainer review of #607, fold leg-1). The snapshot
# directory is trusted (Gate 98), so adding it back is safe.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from board_eligibility import DISPOSITION_LABEL, DUPLICATE_STEP  # noqa: E402
from board_item_marker import is_loop_marker_author, last_marker_match, write_marker  # noqa: E402

RECIPROCAL_PHRASE = "Filed for the routed original"


def _view_issue(issue_number, json_fields, repository, run):
    """`gh issue view <issue_number> -R repository --json json_fields`,
    parsed. Returns (parsed_dict_or_None, ok)."""
    proc = run(["gh", "issue", "view", str(issue_number), "-R", repository,
                "--json", json_fields], capture_output=True, text=True)
    if proc.returncode != 0:
        return None, False
    try:
        parsed = json.loads(proc.stdout)
    except ValueError:
        return None, False
    if not isinstance(parsed, dict):
        return None, False
    return parsed, True


def _has_own_duplicate_comment(comments, bot_login):
    """True when one of `comments` (an issue's own comments) carries a
    loop-authored board-item marker (board_item_marker.is_loop_marker_
    author/last_marker_match) whose step is "duplicate" -- the disposition
    operation's own reason+marker comment (contract step 4), read back the
    same way every other marker consumer in this repository does."""
    for comment in comments or []:
        if not is_loop_marker_author(comment, bot_login):
            continue
        match = last_marker_match(comment.get("body") or "")
        if not match:
            continue
        try:
            marker = json.loads(match.group(1))
        except ValueError:
            continue
        if isinstance(marker, dict) and marker.get("step") == DUPLICATE_STEP:
            return True
    return False


def spec_request_needs_reciprocal_link(spec_request_comments):
    """True when none of `spec_request_comments` already carries the
    reciprocal cross-link checklist item (research.md D5, contract step 6)
    -- matched on the wing-commander-outstanding-task-item composite's own
    rendered shape, "- [ ] " + RECIPROCAL_PHRASE, the same way T003's
    design decision instructs."""
    needle = "- [ ] {0}".format(RECIPROCAL_PHRASE)
    return not any(needle in (comment.get("body") or "")
                   for comment in spec_request_comments or [])


def dispose_as_duplicate(originating_issue, spec_request_issue, spec_request_url, reason,
                          repository=None, bot_login=None, run=None,
                          originating=None, spec_request=None):
    """Closes `originating_issue` as a duplicate of `spec_request_issue`
    (FR-001/FR-015), idempotently (FR-009), leaving a state a maintainer
    can read and a later run can finish on partial failure (FR-010/
    FR-011). Returns True on success (including the already-disposed
    no-op case), False on any failure -- the caller fails its own step on
    False, the same way add_stalled_label()'s callers do today.

    `originating`/`spec_request`: optional already-fetched `gh issue view`
    results (`--json state,labels,comments` / `--json comments`
    respectively) -- when omitted, this function fetches them itself; the
    CLI entry point (main()) fetches them once and passes them in, since
    it also needs the spec-request read for spec_request_needs_reciprocal_
    link(), and re-fetching would risk reading a second, inconsistent
    snapshot of GitHub's live state."""
    run = run or subprocess.run
    repository = repository or os.environ.get("GITHUB_REPOSITORY")
    bot_login = bot_login if bot_login is not None else os.environ.get("BOT_LOGIN")
    if not repository:
        print("::error::board_duplicate_disposition: GITHUB_REPOSITORY is unset -- cannot dispose of "
              "issue #{0} (contracts/duplicate-disposition.md step 1).".format(originating_issue),
              file=sys.stderr)
        return False

    if originating is None:
        originating, ok = _view_issue(originating_issue, "state,labels,comments", repository, run)
        if not ok:
            print("::error::board_duplicate_disposition: could not read issue #{0} (pre-check, step 1) "
                  "-- disposition not attempted; a later run retries from the pre-check.".format(
                      originating_issue), file=sys.stderr)
            return False
    if spec_request is None:
        spec_request, ok = _view_issue(spec_request_issue, "comments", repository, run)
        if not ok:
            print("::error::board_duplicate_disposition: could not read spec-request #{0} (pre-check, "
                  "step 1) -- disposition not attempted; a later run retries from the pre-check.".format(
                      spec_request_issue), file=sys.stderr)
            return False

    state = originating.get("state")
    label_names = {label.get("name") for label in (originating.get("labels") or [])}
    close_needed = state != "CLOSED"
    label_needed = DISPOSITION_LABEL not in label_names
    comment_needed = not _has_own_duplicate_comment(originating.get("comments"), bot_login)

    if close_needed:
        proc = run(["gh", "api", "-X", "PATCH", "repos/{0}/issues/{1}".format(repository, originating_issue),
                    "-f", "state=closed", "-f", "state_reason=duplicate"],
                   capture_output=True, text=True)
        if proc.returncode != 0:
            print("::error::board_duplicate_disposition: could not close issue #{0} as a duplicate of "
                  "#{1} (step 2) -- {2}".format(originating_issue, spec_request_issue,
                                                 (proc.stderr or "").strip()), file=sys.stderr)
            return False

    if label_needed:
        proc = run(["gh", "issue", "edit", str(originating_issue), "-R", repository,
                    "--add-label", DISPOSITION_LABEL], capture_output=True, text=True)
        if proc.returncode != 0:
            print("::error::board_duplicate_disposition: could not add {0} to issue #{1} (step 3) -- "
                  "{2}".format(DISPOSITION_LABEL, originating_issue, (proc.stderr or "").strip()),
                  file=sys.stderr)
            return False

    if comment_needed:
        marker = write_marker(DUPLICATE_STEP, round=0, pr=None, branch=None, base_sha=None,
                               spec_request=spec_request_issue)
        body = "Closed as a duplicate of {0} -- {1}\n\n{2}".format(spec_request_url, reason, marker)
        proc = run(["gh", "issue", "comment", str(originating_issue), "-R", repository, "--body", body],
                   capture_output=True, text=True)
        if proc.returncode != 0:
            print("::error::board_duplicate_disposition: could not post the reason/marker comment on "
                  "issue #{0} (step 4) -- {1}".format(originating_issue, (proc.stderr or "").strip()),
                  file=sys.stderr)
            return False

    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--originating", type=int, required=True)
    parser.add_argument("--spec-request-issue", type=int, required=True)
    parser.add_argument("--spec-request-url", required=True)
    parser.add_argument("--reason", required=True)
    args = parser.parse_args()

    repository = os.environ.get("GITHUB_REPOSITORY")
    bot_login = os.environ.get("BOT_LOGIN")
    if not repository:
        print("::error::board_duplicate_disposition: GITHUB_REPOSITORY is unset -- cannot dispose of "
              "issue #{0}.".format(args.originating), file=sys.stderr)
        sys.exit(1)

    originating, ok = _view_issue(args.originating, "state,labels,comments", repository, subprocess.run)
    if not ok:
        print("::error::board_duplicate_disposition: could not read issue #{0} (pre-check, step 1) -- "
              "disposition not attempted; a later run retries from the pre-check.".format(
                  args.originating), file=sys.stderr)
        sys.exit(1)
    spec_request, ok = _view_issue(args.spec_request_issue, "comments", repository, subprocess.run)
    if not ok:
        print("::error::board_duplicate_disposition: could not read spec-request #{0} (pre-check, step "
              "1) -- disposition not attempted; a later run retries from the pre-check.".format(
                  args.spec_request_issue), file=sys.stderr)
        sys.exit(1)

    disposed = dispose_as_duplicate(
        args.originating, args.spec_request_issue, args.spec_request_url, args.reason,
        repository=repository, bot_login=bot_login, originating=originating, spec_request=spec_request)
    if not disposed:
        sys.exit(1)

    needs_reciprocal_link = spec_request_needs_reciprocal_link(spec_request.get("comments"))
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as fh:
            fh.write("disposed=true\n")
            fh.write("needs-reciprocal-link={0}\n".format("true" if needs_reciprocal_link else "false"))


if __name__ == "__main__":
    main()
