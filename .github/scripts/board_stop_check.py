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
A stop request is a *command*, never the word "stop" in prose -- a false
stop wedges the board (the pre-#539 bare `\bstop\b` search of the whole
body read #402's owner analysis, "it should stop retrying and finish", as
a stop on every run). pr-conversation.yml classifies a comment as `stop`
with an LLM; this loop is deterministic and uses the first-line command
rule below instead (research.md D17). is_stop_command() and
STOP_COMMAND_RE are its single home.

1. Skip, line by line: `>` quote lines; fenced code (a line whose stripped
   text starts with ``` or ~~~ toggles the fence; the fence lines and
   everything inside are skipped; an unclosed fence runs to the end); HTML
   comments (a whole-line `<!-- ... -->`, or a `<!--` line with no `-->`
   through the next line containing `-->`; a line with text after its
   one-line comment is NOT skipped); and `---` horizontal rules
   (a line of three or more `-`). Take the FIRST remaining line that is
   non-empty after normalisation (step 2). Nothing remaining (e.g. a body
   of only `> stop`) is not a stop request.
2. Normalise that line: delete U+FEFF and zero-width characters (U+200B,
   U+200C, U+200D, U+2060), strip whitespace, drop leading @handle tokens
   (`^(?:@[\w-]+(?:\[bot\])?(?:[\s,:]+|$))+` -- a handle-only line
   becomes empty and is passed over), then drop leading markdown emphasis
   (`*`/`_`).
3. Match STOP_COMMAND_RE at the start, case-insensitively: an optional
   `please` plus separator, then `stop` or `/stop`, optional closing
   emphasis (`*`/`_`), then one of:
   - end of line;
   - punctuation `. ! : , ; … ) 。 ！ ）` (NOT `?` -- a
     question is not a command -- and not `'`/`’`, so `stop's` fails);
   - a dash: `—`, `–`, or `-` not followed by a word character;
   - whitespace, then either a dash, colon or `. ! …` (the reason
     follows), or a run of one or more of the words `now`, `please`,
     `pls`, `immediately` (`STOP NOW PLEASE`) that is NOT followed by
     whitespace and another word.
   Anything after that on the line is the reason.

Accepted: `stop`, `Stop.`, `STOP!`, `/stop`, `Stop…`, `stop)`,
`**stop**`, `Please stop.`, `@wing-commander stop`, `@bot /stop`,
`STOP NOW`, `stop please`, `stop immediately!`, `stop ...`, `stop !`,
`stop - wrong approach`, `stop: bad plan`, `/stop — reason`,
`stop, this is wrong`, and `stop` after a quote-reply, fenced log, HTML
comment, `---` rule or handle-only line. Rejected: prose
(`We should stop retrying`), prose that merely BEGINS with "Stop"
(`stop this please`, `Stop worrying about the flake`,
`Stop now and then it flakes`, `stop please the build`,
`Stop the presses: this is great`), questions (`stop?`,
`Stop? not sure we should`), `stopped`, `Stopping`, `non-stop`,
`stop-gap`, `stop's`, a "stop" only on a later line, and a first line
that does not start with stop (`Hold on, stop`, `Wait — stop`).
An `@someone stop - ...` addressed to another human also counts; that is
accepted (the handle is dropped before matching).
"""
import os
import re
import sys

import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# The one author predicate for the loop's own comments (issue #555); it is
# looked up here as a module global so find_stop_request() uses it.
from board_item_marker import is_loop_marker_author  # noqa: E402,F401

MAINTAINER_ASSOCIATIONS = {"OWNER", "MEMBER", "COLLABORATOR"}
STOP_COMMAND_RE = re.compile(
    r"(?:please[\s,:]+)?/?stop[*_]*"
    r"(?:$|[.!:,;\u2026)\u3002\uff01\uff09\u2014\u2013]|-(?!\w)"
    r"|\s+(?:[-\u2014\u2013:.!\u2026]|(?:now|please|pls|immediately)(?:\s+(?:now|please|pls|immediately))*\b(?!\s+\w)))",
    re.IGNORECASE)
_ZERO_WIDTH_RE = re.compile("[\ufeff\u200b\u200c\u200d\u2060]")
_HANDLES_RE = re.compile(r"^(?:@[\w-]+(?:\[bot\])?(?:[\s,:]+|$))+")
_HORIZONTAL_RULE_RE = re.compile(r"^-{3,}$")
# Anchored to the start of a line (issue #547): write_marker() renders the
# announcement as its own `**Run:** <url>` line, so a `**Run:**` inside
# prose, a `>` quote or a code span is never one. `[ \t]*`, not `\s*`, so
# the URL cannot be taken from the NEXT line either.
MARKER_RUN_RE = re.compile(
    r"^\*\*Run:\*\*[ \t]*(https://\S+/actions/runs/(\d+))", re.MULTILINE)


def last_run_match(body):
    """The LAST MARKER_RUN_RE match in `body`, or None (issue #580). The
    loop's comments embed agent text, and write_marker() always writes its
    `**Run:**` line after it (just before the marker, at the end of the
    comment), so an earlier `**Run:**` line in the same comment is never
    the loop's own -- the same rule as board_item_marker.last_marker_match().
    """
    last = None
    for match in MARKER_RUN_RE.finditer(body or ""):
        last = match
    return last


def _command_line(body):
    """The first line of `body` that step 1 of the module docstring's rule
    does not skip, normalised per step 2; None when nothing remains."""
    fence = False
    html_comment = False
    for raw in (body or "").splitlines():
        line = _ZERO_WIDTH_RE.sub("", raw).strip()
        if html_comment:
            html_comment = "-->" not in line
            continue
        if line.startswith("```") or line.startswith("~~~"):
            fence = not fence
            continue
        if fence or line.startswith(">") or _HORIZONTAL_RULE_RE.match(line):
            continue
        if line.startswith("<!--"):
            if "-->" not in line[4:]:
                html_comment = True
                continue
            if line.endswith("-->"):
                continue
        line = _HANDLES_RE.sub("", line).lstrip("*_").strip()
        if line:
            return line
    return None


def is_stop_command(body):
    """True when `body` is a stop command (see the module docstring). The
    one predicate every board-loop stop check uses."""
    line = _command_line(body)
    return bool(line and STOP_COMMAND_RE.match(line))


def find_stop_request(comments, current_run_id, bot_login):
    """comments: [{"body": str, "author_association": str, "created_at": str,
    "user": {"login": str, "type": str}}, ...], any order (sorted here).
    bot_login: the loop's own App login (`<slug>[bot]`). Returns the run_id
    (str) to `gh run cancel` when an authorized, unactioned stop request
    exists, else None.

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

    Only a `**Run:**` line at the start of a line (board_item_marker.
    write_marker()'s own convention, MARKER_RUN_RE) in a comment the loop's
    own App posted (is_loop_marker_author(), issue #547), and only the last
    such line in that comment (last_run_match(), issue #580), counts as a
    run announcement -- an unrelated `.../actions/runs/N` link (e.g. a
    human-pasted post-merge proof URL, this repo's own convention for
    closing out a fix issue) must never be mistaken for one, and neither
    may a `**Run:**` line any other commenter types, maintainer or not.
    The stop request itself is still honoured only from
    MAINTAINER_ASSOCIATIONS -- a different author rule for a different
    comment."""
    ordered = sorted(comments or [], key=lambda c: c.get("created_at") or "")
    current_run_id = str(current_run_id)

    baseline = ""
    last_other_run_id = None
    for comment in ordered:
        if not is_loop_marker_author(comment, bot_login):
            continue
        match = last_run_match(comment.get("body"))
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
    """Reads {"comments": [...], "current_run_id": "...", "bot_login": "..."}
    from stdin, prints the run_id to cancel (or nothing)."""
    payload = json.load(sys.stdin)
    run_id = find_stop_request(payload.get("comments") or [], payload.get("current_run_id"),
                               payload.get("bot_login"))
    if run_id:
        print(run_id)


if __name__ == "__main__":
    main()
