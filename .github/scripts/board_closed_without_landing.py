#!/usr/bin/env python3
"""Closed-without-landing notice (specs/108-routed-original-disposition,
contracts/closed-without-landing-notice.md, research.md D8, FR-017).

A spec-request this loop filed can close without the work it covers ever
landing -- no final PR merged for it. This module decides which CLOSED,
bot-filed spec-requests fall into that state, and posts one idempotent
notice on each of the spec-request and the originating issue it disposed
of, naming reopening the originating issue as the path back onto the
board.

FINALIZE_TERMINAL_STAGE: `specs/<NNN-slug>/spec-meta.json`'s `stage` field
is only ever set to "review" by finalize.yml (the stage that opens the
final PR) and never advanced further by any later pipeline step -- a
specification's own completion is recorded on the GitHub issue (closed,
`stage:done`), never by a further spec-meta.json write (confirmed by
reading every `.stage = "..."` assignment in .github/workflows/*.yml:
finalize.yml writes "review", implement.yml/cleanup.yml write "stalled"
on an unmerged stage PR, and nothing ever writes "done"). So "never
reached the finalize stage's terminal completed value" (research.md D8)
means: never reached stage == "review" at all, or fell back to "stalled"
after reaching it (a rejected final PR). This is the value this
repository's own pipeline already writes on completion of the finalize
stage's own work -- not invented here (spec 006, this feature's own
finalize-stage predecessor, sits at exactly this value in its own
spec-meta.json, having shipped through this same pipeline).
"""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

FINALIZE_TERMINAL_STAGE = "review"
# The legacy bare marker, posted before notices were keyed by spec-request.
# Still read (see _has_notice()), never written.
NOTICE_MARKER = "<!-- wing-commander-closed-without-landing -->"
NOTICE_MARKER_KEYED = "<!-- wing-commander-closed-without-landing spec-request={0} -->"


def notice_marker(spec_request_number):
    """The marker a notice about `spec_request_number`'s closure carries.
    Keyed, because an originating issue can be reopened and re-routed to a
    second spec-request: a bare marker left by the first closure's notice
    suppressed the second's (found by the code review of #937)."""
    return NOTICE_MARKER_KEYED.format(spec_request_number)


def closed_without_landing(spec_requests):
    """`spec_requests`: [{"number": int, "spec_meta": dict|None, ...}, ...]
    -- one entry per CLOSED, spec-request-labelled, bot-authored issue.
    Returns the subset whose work never landed (research.md D8): no
    spec-meta.json names this spec-request at all, or one whose `stage`
    never reached FINALIZE_TERMINAL_STAGE."""
    result = []
    for entry in spec_requests:
        meta = entry.get("spec_meta")
        if meta is None or meta.get("stage") != FINALIZE_TERMINAL_STAGE:
            result.append(entry)
    return result


def _has_notice(comments, issue_number, spec_request_number):
    """True when `comments` (on `issue_number`) already carry the notice
    about `spec_request_number`'s closure: its keyed marker, or a legacy
    bare marker that can only have been about it -- on the spec-request
    itself, which has one closure, or on an originating issue whose notice
    names `(#N)` (_originating_notice_body())."""
    keyed = notice_marker(spec_request_number)
    named = "(#{0})".format(spec_request_number)
    for comment in comments or []:
        body = comment.get("body") or ""
        if keyed in body:
            return True
        if NOTICE_MARKER in body and (issue_number == spec_request_number or named in body):
            return True
    return False


def post_notice(issue_number, repository, body, existing_comments, spec_request_number, run=None):
    """Posts `body` + notice_marker(spec_request_number) on `issue_number`
    unless `existing_comments` already carries that notice (idempotency,
    same presence-check shape as board_duplicate_disposition.py's own
    comment gating). Returns True on success (including the already-posted
    no-op), False on any `gh` failure."""
    if _has_notice(existing_comments, issue_number, spec_request_number):
        return True
    run = run or subprocess.run
    proc = run(["gh", "issue", "comment", str(issue_number), "-R", repository,
                "--body", "{0}\n\n{1}".format(body, notice_marker(spec_request_number))],
               capture_output=True, text=True)
    if proc.returncode != 0:
        print("::error::board_closed_without_landing: could not post the closed-without-landing "
              "notice on issue #{0} -- {1}".format(issue_number, (proc.stderr or "").strip()),
              file=sys.stderr)
        return False
    return True


def _spec_request_notice_body():
    return ("This spec-request closed without its work landing -- its linked specification "
            "never reached the finalize stage's final PR. Reopening the originating issue "
            "returns the request to the board.")


def _superseded_notice_body(originating_issue):
    return ("This spec-request closed without its work landing. Its originating issue "
            "#{0} has since been routed to a newer spec-request, so whether reopening it "
            "returns the request to the board depends on that newer spec-request, not on "
            "this one.").format(originating_issue)


def _originating_notice_body(spec_request_number):
    return ("The spec-request filed for this issue (#{0}) closed without its work landing -- "
            "reopening this issue returns the request to the board.").format(spec_request_number)


def post_notices(spec_requests, repository, run=None):
    """Posts the notices for every entry closed_without_landing() keeps;
    returns the number of failed posts. An entry carrying `superseded_on`
    (#874) gets only its own superseded-wording notice; any other entry
    gets its own notice and, when its originating issue resolved, that
    issue's notice too."""
    failures = 0
    for entry in closed_without_landing(spec_requests):
        number = entry.get("number")
        superseded_on = entry.get("superseded_on")
        if superseded_on is not None:
            # #874: the originating issue's newest duplicate marker names a
            # later spec-request, so telling it "reopening returns the
            # request to the board" would be false (FR-006, FR-017). Only
            # the spec-request itself is told, in words that say so.
            if not post_notice(number, repository, _superseded_notice_body(superseded_on),
                                entry.get("comments"), number, run=run):
                failures += 1
            continue
        if not post_notice(number, repository, _spec_request_notice_body(),
                            entry.get("comments"), number, run=run):
            failures += 1
            continue
        originating = entry.get("originating_issue")
        if originating is None:
            print("note: board_closed_without_landing: spec-request #{0} closed without "
                  "landing, but no originating issue could be resolved for it -- only its own "
                  "notice was posted.".format(number))
            continue
        if not post_notice(originating, repository, _originating_notice_body(number),
                            entry.get("originating_comments"), number, run=run):
            failures += 1
    return failures


def main():
    payload = json.load(sys.stdin)
    repository = os.environ.get("GITHUB_REPOSITORY")
    if not repository:
        print("::error::board_closed_without_landing: GITHUB_REPOSITORY is unset.", file=sys.stderr)
        sys.exit(1)
    if post_notices(payload.get("spec_requests") or [], repository):
        sys.exit(1)


if __name__ == "__main__":
    main()
