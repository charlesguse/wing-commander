#!/usr/bin/env python3
"""Board loop stop-comment handling (specs/057-autonomous-board-loop,
research.md D17, FR-052/FR-053).

WHY THIS EXISTS
---------------
A maintainer's stop comment on the in-flight issue must halt the loop
before its NEXT durable action, not only at job start (FR-051) -- this
module is the reusable check every job's own "re-check kill switch before
any durable action" step also performs (T052), retargeted from
pr-conversation.yml's PR-thread stop procedure to the issue thread this
loop actually posts to (research.md D17): scan the issue's own comments
for the most recent maintainer stop request, gated by the same
OWNER/MEMBER/COLLABORATOR association check pr-conversation.yml already
uses, and hand the caller the run URL to cancel (never a second
authorization rule).
"""
import re
import sys

import json

MAINTAINER_ASSOCIATIONS = {"OWNER", "MEMBER", "COLLABORATOR"}
STOP_RE = re.compile(r"\bstop\b", re.IGNORECASE)
RUN_URL_RE = re.compile(r"https://\S+/actions/runs/(\d+)")


def find_stop_request(comments, current_run_id):
    """comments: [{"body": str, "author_association": str, "created_at": str}, ...],
    newest-first or any order (sorted here). Returns the run_id (str) to
    cancel, or None when no authorized, unactioned stop request exists.

    A maintainer comment containing the word "stop" is the request
    (FR-052); the run to cancel is the most recent `**Run:**`-bearing
    comment's own run ID, excluding current_run_id (never self-cancel,
    research.md D17)."""
    ordered = sorted(comments or [], key=lambda c: c.get("created_at") or "")

    stop_seen = False
    for comment in ordered:
        if (comment.get("author_association") in MAINTAINER_ASSOCIATIONS
                and STOP_RE.search(comment.get("body") or "")):
            stop_seen = True

    if not stop_seen:
        return None

    for comment in reversed(ordered):
        body = comment.get("body") or ""
        match = RUN_URL_RE.search(body)
        if not match:
            continue
        run_id = match.group(1)
        if run_id != str(current_run_id):
            return run_id
    return None


def main():
    """Reads {"comments": [...], "current_run_id": "..."} from stdin,
    prints the run_id to cancel (or nothing)."""
    payload = json.load(sys.stdin)
    run_id = find_stop_request(payload.get("comments") or [], payload.get("current_run_id"))
    if run_id:
        print(run_id)


if __name__ == "__main__":
    main()
