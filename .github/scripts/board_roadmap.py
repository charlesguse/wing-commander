#!/usr/bin/env python3
"""The board loop's line on the Roadmap issue's "Proposed" list (#1209).

When board-loop.yml files a `spec-proposal` (route's spec verdict, fix's
post-push breach, readiness's backstop breach), the proposal is listed
under the Roadmap issue's "### Proposed (waiting on the owner's
`spec-request`)" header, one line in the form

    - #N: <title>. Filed by the board loop YYYY-MM-DD from Maintenance backlog line `bl-xxxxxxxx`.

("from issue #M" when the item was an issue). Every spec-proposal site
already calls board_duplicate_disposition.py, which calls
record_proposal() here, so there is one call site and no workflow step.

The owner orders the Proposed list, so the line goes on a "Not yet
ordered" sub-list after that order, never into it (UNORDERED_LABEL).

The Roadmap is found the way the backlog is: the one open
`disposition:tracking` issue whose title starts "Roadmap"
(board_backlog_lines.resolve_tracking()), never a hard-coded number. The
write goes through board_backlog_edit.edit() -- fetch, apply, write, read
back, retry -- the single home of that loop; this module adds only the
pure apply/verify pair. Adding a line that is already there changes
nothing.

This is best effort by design: record_proposal() never raises and never
changes the caller's exit status. A missing Roadmap, a missing header or
a write that kept being dropped is reported as a warning and a run-summary
line, and nothing else is filed.
"""
import datetime
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import board_backlog_edit as bbe  # noqa: E402
import board_backlog_lines as bbl  # noqa: E402

TITLE_PREFIX = "Roadmap"
# Matches "### Proposed (waiting on the owner's `spec-request`)" and a
# reworded tail; the section runs to the next heading.
HEADER_RE = re.compile(r"^#{2,4}[ \t]+Proposed\b")
HEADING_RE = re.compile(r"^#{1,6}[ \t]")
LINE_ID_RE = re.compile(r"^bl-[0-9a-f]{8}$")
TITLE_MAX = 200

NOT_FOUND = "no_roadmap"
NO_HEADER = "no_header"
NOT_OPEN = "not_open"
HAND_EDIT = " Check the Roadmap's Proposed list and add its line by hand if it is missing."


LIST_ITEM_RE = re.compile(r"^(?:[-*]|\d+[.)])[ \t]")
# The owner orders the Proposed list (numbered, 2026-11-25); the loop never
# places an item in that order. It appends to this sub-list instead, which
# it creates after the section's first list when it is not there yet.
UNORDERED_RE = re.compile(r"^(?:\*\*)?Not yet ordered\b", re.IGNORECASE)
UNORDERED_LABEL = "Not yet ordered (filed by the board loop; the owner places each in the Proposed order):"
NUMBERED_RE = re.compile(r"^\d+[.)][ \t]")


def _section(lines):
    """(header_index, end_index) of the Proposed section in `lines`
    (keepends), or None when no header matches. The section runs to the
    next heading."""
    header = next((i for i, line in enumerate(lines) if HEADER_RE.match(line)), None)
    if header is None:
        return None
    end = next((j for j in range(header + 1, len(lines)) if HEADING_RE.match(lines[j])), len(lines))
    return header, end


def _numbered(text):
    return bool(NUMBERED_RE.match(text))


def _list_end(lines, start, end, skip_prose=True, loose=True):
    """Index just past the first list (bulleted or numbered, continuation
    lines included) at or after `start`, before `end`; None when there is
    none. With skip_prose=False only blank lines may come before the list.
    A loose list -- blank lines between its items -- is one list: a blank
    line ends it only when the next text is neither an item of the same
    kind nor indented under one (code review of #1222, pass 2). With
    loose=False any blank line after an item ends the list: the loop's
    own sub-list is always tight, so a list after a blank line below it is
    the owner's, never more of the loop's (pass 3)."""
    past = None
    numbered = None
    j = start
    while j < end:
        text = lines[j].rstrip("\r\n")
        if LIST_ITEM_RE.match(text):
            if past is None:
                numbered = _numbered(text)
            past = j + 1
        elif past is None:
            if not skip_prose and text.strip():
                return None
        elif text[:1] in (" ", "\t") and text.strip():
            past = j + 1
        elif not text.strip():
            if not loose:
                break
            nxt = next((m for m in range(j + 1, end) if lines[m].strip()), None)
            if nxt is None:
                break
            following = lines[nxt].rstrip("\r\n")
            if (LIST_ITEM_RE.match(following) and _numbered(following) == numbered) \
                    or following[:1] in (" ", "\t"):
                j = nxt
                continue
            break
        else:
            break
        j += 1
    return past


def _item_re(number):
    return re.compile(r"^[ \t]*(?:[-*]|\d+[.)])[ \t]+(?:\[[ xX]\][ \t]+)?[*_]{{0,2}}\[?#{0}(?!\d)".format(int(number)))


def is_listed(body, number):
    """True when any list line on the Roadmap already starts with #number:
    Proposed, or a section the owner has since moved it to (In flight,
    Queued, Parked), so a re-run never lists it again."""
    item = _item_re(number)
    return any(item.match(line) for line in (body or "").splitlines())


def _clean_title(title):
    text = str(title or "").replace("<!--", " ").replace("-->", " ")
    text = re.sub(r"\s+", " ", text).strip().rstrip(" .")
    # Truncate before the @-wrapping below, so a cut never reopens a mention.
    if len(text) > TITLE_MAX:
        text = text[:TITLE_MAX - 3].rstrip() + "..."
    # Raw HTML in a title (an unclosed <details>) would restyle the rest of
    # the owner's Roadmap; show it as text.
    text = text.replace("<", "&lt;").replace(">", "&gt;")
    # A bare @name in a body edit would notify that user or team. Escape
    # the title's own backslashes and backticks first, so the code spans
    # wrapped round each @name below are the only live ones: an odd
    # backtick in the title can then never pair with one of them and leave
    # the name bare (code review of #1222, pass 3).
    text = text.replace("\\", "\\\\").replace("`", "\\`")
    text = re.sub(r"(?<!\w)@([\w-]+(?:/[\w.-]+)?)", r"`@\1`", text)
    return text or "(untitled)"


def proposed_line(number, title, date, line_id=None, originating=None):
    """The one line the loop adds for spec-proposal #number."""
    if line_id and LINE_ID_RE.match(str(line_id)):
        source = "Maintenance backlog line `{0}`".format(line_id)
    elif originating:
        source = "issue #{0}".format(int(originating))
    else:
        source = "the board loop's work item"
    title = _clean_title(title)
    stop = "" if title.endswith((".", "?", "!")) else "."
    return "- #{0}: {1}{2} Filed by the board loop {3} from {4}.".format(
        int(number), title, stop, date, source)


def add_line(body, number, line):
    """`body` with `line` appended to the Proposed section's "Not yet
    ordered" sub-list, created after the section's first list (the
    owner's ordered one) when missing; `body` unchanged when #number is
    already listed in the section; None when there is no Proposed header
    (board_backlog_edit.edit() reads None as a stand-down)."""
    body = body or ""
    lines = body.splitlines(True)
    section = _section(lines)
    if section is None:
        return None
    if is_listed(body, number):
        return body
    newline = "\r\n" if "\r\n" in body else "\n"
    header, end = section
    label = next((j for j in range(header + 1, end) if UNORDERED_RE.match(lines[j].strip())), None)
    if label is not None:
        insert = _list_end(lines, label + 1, end, skip_prose=False, loose=False) or label + 1
        block = [line + newline]
    else:
        # After the owner's numbered order; with none, under the header.
        first = next((j for j in range(header + 1, end) if _numbered(lines[j])), None)
        insert = _list_end(lines, first, end) if first is not None else header + 1
        block = [UNORDERED_LABEL + newline, line + newline]
        if insert > header + 1:
            block.insert(0, newline)  # a blank line ends the ordered list above
    if insert < len(lines) and lines[insert].strip():
        block.append(newline)  # never glue the text below onto the new item
    if insert > 0 and not lines[insert - 1].endswith(("\n", "\r")):
        lines[insert - 1] += newline
    lines[insert:insert] = block
    return "".join(lines)


def _gh_text(run, args):
    proc = run(["gh"] + args, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError("gh {0} failed: {1}".format(" ".join(args[:2]), (proc.stderr or "").strip()))
    return proc.stdout


def list_tracking(repository, run):
    """The open `disposition:tracking` issues, in resolve_tracking()'s shape
    -- the same read board-loop.yml's select job makes for the backlog."""
    import json
    out = _gh_text(run, [
        "api", "repos/{0}/issues".format(repository), "-X", "GET", "--paginate",
        "-f", "state=open", "-f", "labels=disposition:tracking", "-f", "per_page=100",
        "--jq", '.[] | select(has("pull_request") | not) | {number, title, '
                'author: {login: .user.login}, authorAssociation: .author_association, '
                'labels: [.labels[] | {name}], state: (.state | ascii_upcase)}'])
    return [json.loads(line) for line in out.splitlines() if line.strip()]


def _summary(text):
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    try:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(text + "\n")
    except OSError:
        pass


def record_proposal(spec_number, line_id=None, originating=None, repository=None, bot_login=None,
                    run=None, fetch=None, write=None, today=None, title=None, state=None):
    """Lists spec-proposal #spec_number on the Roadmap. Returns
    (outcome, message): outcome is board_backlog_edit's APPLIED, FAILED,
    or NOT_FOUND / NO_HEADER / NOT_OPEN. Never raises; FAILED, NOT_FOUND
    and NO_HEADER are also printed as a ::warning:: and every outcome is
    written to the run summary. A proposal that is no longer open (a
    retry reusing one the owner has since closed) is never listed."""
    run = run or subprocess.run
    repository = repository or os.environ.get("GITHUB_REPOSITORY") or ""
    bot_login = bot_login if bot_login is not None else os.environ.get("BOT_LOGIN") or ""
    fetch = fetch or bbe.gh_fetch
    write = write or bbe.gh_write
    today = today or datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    try:
        roadmap, reason = bbl.resolve_tracking(list_tracking(repository, run), bot_login, TITLE_PREFIX)
        if roadmap is not None and title is None:
            state, _tab, title = _gh_text(run, [
                "issue", "view", str(spec_number), "-R", repository,
                "--json", "state,title", "--jq", '.state + "\\t" + .title']).strip().partition("\t")
        if roadmap is None:
            outcome, message = NOT_FOUND, "the Roadmap issue was not found ({0})".format(reason)
        elif state is not None and state.upper() != "OPEN":
            outcome, message = NOT_OPEN, "it is {0}, so it is not listed on the Roadmap".format(state.lower())
        else:
            line = proposed_line(spec_number, title, today, line_id=line_id, originating=originating)
            result = bbe.edit(roadmap, lambda b: add_line(b, spec_number, line),
                              lambda b: is_listed(b, spec_number), fetch=fetch, write=write)
            if result == bbe.APPLIED:
                outcome, message = bbe.APPLIED, "listed under Proposed on the Roadmap (#{0})".format(roadmap)
            elif result == bbe.STAND_DOWN:
                outcome, message = NO_HEADER, ("the Roadmap (#{0}) has no \"### Proposed\" header, "
                                               "so nothing was added".format(roadmap))
            else:
                outcome, message = bbe.FAILED, ("concurrent edits kept dropping the line on the "
                                                "Roadmap (#{0}); its body was left as it is".format(roadmap))
    except Exception as exc:  # noqa: BLE001 -- best effort: never fail the routing
        # A failure can come after a write that landed (the read-back fetch),
        # so this never claims the line is absent.
        outcome, message = bbe.FAILED, "the Roadmap update did not finish ({0})".format(
            str(exc).splitlines()[0] if str(exc) else type(exc).__name__)
    text = "board-loop: spec-proposal #{0}: {1}.".format(spec_number, message)
    if outcome in (bbe.APPLIED, NOT_OPEN):
        _summary(text)
    else:
        text += HAND_EDIT
        print("::warning::{0}".format(text), file=sys.stderr)
        _summary(text)
    return outcome, message
