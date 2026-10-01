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
import collections
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

StopDecision = collections.namedtuple("StopDecision", ["stand_down", "cancel_run_id"])


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
    bot_login: the loop's own App login (`<slug>[bot]`). Returns a
    StopDecision(stand_down, cancel_run_id) two-fact answer: `stand_down` is
    True iff an authorized, unactioned stop request exists; `cancel_run_id`
    is the earlier run worth cancelling with `gh run cancel`, or None when
    there is nothing to cancel. The current run is never a valid
    `cancel_run_id` under any input -- Gate 87 mutation-proves this.

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
    - `cancel_run_id` prefers an EARLIER run's own marker (skipping this
      run's own, current_run_id) when one exists -- that is a genuinely
      different, still-possibly-running attempt worth cancelling. When no
      earlier run announced itself yet (an item's first pass through this
      run, the common case), `cancel_run_id` is None -- there is nothing
      to cancel, since the run executing this check is never a cancel
      target itself; `stand_down=True` is what actually halts further
      durable action either way. (Earlier, the App token this call ran
      under had no `actions` permission, so the cancel silently 403'd
      regardless of target -- fixed in #461, which is what made this
      self-cancel case reachable for the first time and is why the caller
      still guards against it explicitly, as belt-and-braces defence in
      depth.)

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
    comment.

    specs/097-recorded-stop-point (FR-006/FR-008, maintainer review fold
    leg-1): a marker carrying THIS run's own id never advances the
    baseline, however many of them exist or in what order -- only a marker
    from a DIFFERENT run can. This run's own stop-point record is exactly
    such a same-run marker (write_marker()'s `**Run:**` line, posted by the
    same bot, after honouring a stop within this very run); if it were
    allowed to set the baseline the way an other-run marker does, it would
    move the baseline past the very stop comment it just recorded, and a
    later job checking again in this same run would wrongly see
    stand_down=False -- undoing the stand-down the record exists to make
    durable. Excluding every same-run marker from baseline-setting is also
    the semantically right rule on its own terms, not just a workaround:
    within one continuous run, a stop posted partway through must stay
    honoured for the rest of that run regardless of what other same-run
    progress markers accumulate after it (FR-006). A marker from a
    DIFFERENT (earlier) run is unaffected and still sets the baseline
    exactly as before -- that is the separate FR-009/FR-016 case, where a
    PAST run's own stop-point record correctly suppresses its own old stop
    comment from re-triggering the NEXT run."""
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
        run_id = match.group(2)
        if run_id == current_run_id:
            continue
        baseline = comment.get("created_at") or baseline
        last_other_run_id = run_id

    stop_seen = False
    for comment in ordered:
        if (comment.get("created_at") or "") < baseline:
            continue
        if (comment.get("author_association") in MAINTAINER_ASSOCIATIONS
                and is_stop_command(comment.get("body"))):
            stop_seen = True

    if not stop_seen:
        return StopDecision(False, None)

    return StopDecision(True, last_other_run_id)


def find_stop_command_comment(comments, current_run_id, bot_login):
    """As find_stop_request()'s own stop-detection loop, but returns the
    WINNING comment itself rather than a bare boolean (specs/097-recorded-
    stop-point, research.md D2). Recomputes the same baseline
    find_stop_request() computes -- including the same-run-id handling
    FR-006/FR-008 require (no current-run-id marker, including this run's
    own stop-point record, ever advances the baseline; see
    find_stop_request()'s docstring) -- then returns the LAST comment at or
    after that baseline where `author_association in
    MAINTAINER_ASSOCIATIONS and is_stop_command(body)`, or None when none
    exists.

    Invariant (Gate 128 checks this over Gate 87's own fixture corpus):
    `find_stop_request(comments, run_id, bot_login).stand_down ==
    (find_stop_command_comment(comments, run_id, bot_login) is not None)`
    for every input -- the two functions must never disagree on whether a
    comment won. This function does not itself decide the baseline
    differently; it is a deliberate, independently-testable duplicate of
    the same ~15 lines (research.md D1), not a refactor of
    find_stop_request() into a shared helper -- that function's own
    StopDecision contract and Gate 87's mutation coverage of it stay
    untouched."""
    ordered = sorted(comments or [], key=lambda c: c.get("created_at") or "")
    current_run_id = str(current_run_id)

    baseline = ""
    for comment in ordered:
        if not is_loop_marker_author(comment, bot_login):
            continue
        match = last_run_match(comment.get("body"))
        if not match:
            continue
        run_id = match.group(2)
        if run_id == current_run_id:
            continue
        baseline = comment.get("created_at") or baseline

    winner = None
    for comment in ordered:
        if (comment.get("created_at") or "") < baseline:
            continue
        if (comment.get("author_association") in MAINTAINER_ASSOCIATIONS
                and is_stop_command(comment.get("body"))):
            winner = comment

    return winner


def stop_command_reason(body):
    """The free text the maintainer wrote after the stop command token on
    its own line -- "" when the stop command carried no reason (e.g. a bare
    `stop.`), reusing the same `_command_line()`/STOP_COMMAND_RE is_stop_
    command() itself matches against (research.md D2)."""
    line = _command_line(body)
    if not line:
        return ""
    match = STOP_COMMAND_RE.match(line)
    if not match:
        return ""
    return line[match.end():].strip()


def main():
    """Reads {"comments": [...], "current_run_id": "...", "bot_login": "..."}
    from stdin, prints exactly one line of JSON on success --
    {"stand_down": <bool>, "cancel_run_id": <string> | null} -- the
    StopDecision two-fact contract find_stop_request() documents. A
    malformed payload raises inside json.load/dict access, writing a
    traceback to stderr and exiting non-zero with nothing on stdout.

    `--stop-comment` (specs/097-recorded-stop-point, FR-018): reads
    {"comments": [...], "current_run_id": "...", "bot_login": "..."}
    instead, and prints the winning stop-command comment's identity --
    {"html_url", "login", "created_at", "reason"} -- or {} when
    find_stop_command_comment() finds none. `current_run_id` is required
    here too (maintainer review fold leg-1, FR-006/FR-008): without it,
    this run's own stop-point record -- posted moments earlier by the
    `check` step's own stand_down=true path, carrying a `**Run:**` line
    with this same run's id -- would be indistinguishable from a marker
    from a genuinely different run, and would wrongly suppress the very
    stop comment this call is looking up. The one home for this read so
    the composite's own `run:` shell never re-derives the match/
    authorization rule itself."""
    if len(sys.argv) > 1 and sys.argv[1] == "--stop-comment":
        payload = json.load(sys.stdin)
        comment = find_stop_command_comment(
            payload.get("comments") or [], payload.get("current_run_id"), payload.get("bot_login"))
        if comment is None:
            print(json.dumps({}))
            return
        print(json.dumps({
            "html_url": comment.get("html_url"),
            "login": (comment.get("user") or {}).get("login"),
            "created_at": comment.get("created_at"),
            "reason": stop_command_reason(comment.get("body")),
        }))
        return

    payload = json.load(sys.stdin)
    decision = find_stop_request(payload.get("comments") or [], payload.get("current_run_id"),
                                  payload.get("bot_login"))
    print(json.dumps(decision._asdict()))


if __name__ == "__main__":
    main()
