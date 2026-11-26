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
ordered" sub-list directly under the header, never into that order
(UNORDERED_LABEL).

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


# The owner orders the Proposed list (numbered, 2026-11-25); the loop never
# places an item in that order. Its lines go on this sub-list instead, at a
# fixed anchor: the label sits directly under the Proposed header, and each
# new line goes directly under the label (newest first). The loop never
# works out where any list ends, so no shape of the owner's list can pull
# a line into it (code review of #1222, pass 4: passes 2 and 3 each found
# a list shape the list-end parser misread).
UNORDERED_RE = re.compile(r"^(?:\*\*)?Not yet ordered\b", re.IGNORECASE)
LOOP_ITEM_RE = re.compile(r"^- #\d+: .* Filed by the board loop \d{4}-\d{2}-\d{2} from ")
UNORDERED_LABEL = "Not yet ordered (filed by the board loop, newest first; the owner places each in the Proposed order):"


def _section(lines):
    """(header_index, end_index) of the Proposed section in `lines`
    (keepends), or None unless exactly one header matches. The section
    runs to the next heading."""
    headers = [i for i, line in enumerate(lines) if HEADER_RE.match(line)]
    # The header is the loop's anchor: with two candidates (a "Proposed
    # changes" heading elsewhere) it stands down rather than guess.
    if len(headers) != 1:
        return None
    header = headers[0]
    end = next((j for j in range(header + 1, len(lines)) if HEADING_RE.match(lines[j])), len(lines))
    return header, end


def _item_re(number):
    return re.compile(r"^[ \t]*(?:[-*]|\d+[.)])[ \t]+(?:\[[ xX]\][ \t]+)?[*_]{{0,2}}\[?#{0}(?!\d)".format(int(number)))


def is_listed(body, number):
    """True when any list line on the Roadmap already starts with #number:
    Proposed, or a section the owner has since moved it to (In flight,
    Queued, Parked), so a re-run never lists it again."""
    item = _item_re(number)
    return any(item.match(line) for line in (body or "").splitlines())


# One rule for the title (code review of #1222, pass 4, after passes 1-3
# each found another way a title could render as markup): every @name
# becomes a code span, and every other character that can start Markdown
# or HTML -- emphasis, code, links and images, raw HTML, entities, strike,
# tables, math -- is backslash-escaped, so the rest of the title is plain
# text. A bare @name in a body edit would notify that user or team, and
# GitHub finds mentions in rendered text, so escaping alone would not stop
# one; a code span does. Every @name is wrapped, whatever precedes it.
MENTION_RE = re.compile(r"(@[\w-]+(?:/[\w.-]+)?)")
ACTIVE_RE = re.compile(r"([\\`*_\[\]<>&!~|$])")


def _clean_title(title):
    text = str(title or "").replace("<!--", " ").replace("-->", " ")
    text = re.sub(r"\s+", " ", text).strip().rstrip(" .")
    # Truncate before escaping, so a cut never splits an escape or a span.
    if len(text) > TITLE_MAX:
        text = text[:TITLE_MAX - 3].rstrip() + "..."
    parts = MENTION_RE.split(text)
    text = "".join("`{0}`".format(part) if i % 2 else ACTIVE_RE.sub(r"\\\1", part)
                   for i, part in enumerate(parts))
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
    """`body` with `line` directly under the Proposed section's "Not yet
    ordered" label, the label first created directly under the header
    when missing; `body` unchanged when #number is already listed
    anywhere on the Roadmap; None unless there is one Proposed header
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
        insert, block = label + 1, [line + newline]
        # Only the loop's own older items continue the list; anything
        # else, an owner's list included, is set apart by a blank line.
        joins = lambda text: bool(LOOP_ITEM_RE.match(text))  # noqa: E731
    else:
        insert, block = header + 1, [UNORDERED_LABEL + newline, line + newline]
        # Whatever was under the header (the owner's order, prose) starts
        # after a blank line, never as more of the loop's list.
        joins = lambda text: False  # noqa: E731
    following = lines[insert].rstrip("\r\n") if insert < len(lines) else ""
    if following.strip() and not joins(following):
        block.append(newline)
    if not lines[insert - 1].endswith(("\n", "\r")):
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
                outcome, message = NO_HEADER, ("the Roadmap (#{0}) has no single \"### Proposed\" header, "
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
