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

WHAT COUNTS AS A STOP REQUEST (issue #539)
------------------------------------------
A stop request is a *command*, never the word "stop" in prose. A
maintainer comment is a stop request only when its FIRST NON-EMPTY LINE,
stripped of leading/trailing whitespace, is:

    /?stop  followed by nothing, or by one of  whitespace . ! ? : , ; — –
            or a "-" that is not followed by a word character,
            and then anything (a short reason) to the end of that line

matched case-insensitively (is_stop_command() below, STOP_COMMAND_RE -- the
single home for this rule). So `stop`, `Stop.`, `STOP!`, `/stop`,
`stop - wrong approach`, `/stop: bad plan` and `stop, this is wrong` stop
the item; `We should stop retrying`, `Stopping here for today`, `stopped`,
`non-stop`, `stop-gap` and a "stop" only on a later line do not. A first
non-empty line that is a `>` quote or a code-fence opener is not a command
either (it never starts with `stop`), so a quoted or fenced "stop" never
counts. pr-conversation.yml classifies a comment as `stop` with an LLM;
this loop is deterministic and uses this first-line command rule instead
(research.md D17). The pre-#539 rule, a bare `\bstop\b` search of the
whole body, wedged the board on #402, whose only comment is an owner
analysis saying "it should stop retrying and finish".
"""
import re
import sys

import json

MAINTAINER_ASSOCIATIONS = {"OWNER", "MEMBER", "COLLABORATOR"}
STOP_COMMAND_RE = re.compile(
    r"/?stop(?:$|[\s.!?:,;\u2014\u2013]|-(?!\w))", re.IGNORECASE)
MARKER_RUN_RE = re.compile(r"\*\*Run:\*\*\s*(https://\S+/actions/runs/(\d+))")


def is_stop_command(body):
    """True when `body`'s first non-empty line is a stop command (see the
    module docstring). The one predicate every board-loop stop check uses."""
    for line in (body or "").splitlines():
        line = line.strip()
        if line:
            return bool(STOP_COMMAND_RE.match(line))
    return False


def find_stop_request(comments, current_run_id):
    """comments: [{"body": str, "author_association": str, "created_at": str}, ...],
    any order (sorted here). Returns the run_id (str) to `gh run cancel`
    when an authorized, unactioned stop request exists, else None.

    Board-loop.yml runs triage through readiness as ONE long scheduled
    run, unlike pr-conversation.yml's per-comment-triggered stop
    (research.md D17 ports that stage's idiom, but the run a maintainer's
    "stop" is almost always about is THIS run, still in flight -- not a
    separate later run reacting to the comment). So:

    - The baseline a "stop" must be posted after is the most recent
      `**Run:**`-marker comment of EITHER this run or an earlier one --
      whichever announcement the item is currently "about". A stop from
      before that announcement is about an item that already ended or was
      superseded (FR-052 stops the *in-flight* item, not every issue that
      ever had the word said near it).
    - The run_id handed back to `gh run cancel` prefers an EARLIER run's
      own marker (skipping this run's own, current_run_id) when one
      exists -- that is a genuinely different, still-possibly-running
      attempt worth cancelling. When no earlier run announced itself yet
      (an item's first pass through this run, the common case), this
      function still returns current_run_id -- the caller (issue #461
      review, wing-commander-board-stop-check/action.yml) is the one that
      recognizes that case and skips the `gh run cancel` call rather than
      cancelling the run executing its own step; `paused=true` is what
      actually halts further durable action either way. (Earlier, the App
      token this call ran under had no `actions` permission, so the
      cancel silently 403'd regardless of target -- fixed in #461, which
      is what made this self-cancel case reachable for the first time and
      is why the caller now guards against it explicitly.)

    Only a `**Run:**`-prefixed marker (board_item_marker.write_marker()'s
    own convention) counts as a run announcement -- an unrelated
    `.../actions/runs/N` link (e.g. a human-pasted post-merge proof URL,
    this repo's own convention for closing out a fix issue) must never be
    mistaken for one."""
    ordered = sorted(comments or [], key=lambda c: c.get("created_at") or "")
    current_run_id = str(current_run_id)

    baseline = ""
    last_other_run_id = None
    for comment in ordered:
        match = MARKER_RUN_RE.search(comment.get("body") or "")
        if not match:
            continue
        baseline = comment.get("created_at") or baseline
        run_id = match.group(2)
        if run_id != current_run_id:
            last_other_run_id = run_id

    stop_seen = False
    for comment in ordered:
        if (comment.get("created_at") or "") < baseline:
            continue
        if (comment.get("author_association") in MAINTAINER_ASSOCIATIONS
                and is_stop_command(comment.get("body"))):
            stop_seen = True

    if not stop_seen:
        return None

    return last_other_run_id if last_other_run_id is not None else current_run_id


def main():
    """Reads {"comments": [...], "current_run_id": "..."} from stdin,
    prints the run_id to cancel (or nothing)."""
    payload = json.load(sys.stdin)
    run_id = find_stop_request(payload.get("comments") or [], payload.get("current_run_id"))
    if run_id:
        print(run_id)


if __name__ == "__main__":
    main()
