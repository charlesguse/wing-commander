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


def _section(lines):
    """(header_index, insert_index, end_index) of the Proposed section in
    `lines` (keepends), or None when no header matches. insert_index is
    just past the last item of the section's first list (continuation
    lines included), or just past the header when the list is empty."""
    header = next((i for i, line in enumerate(lines) if HEADER_RE.match(line)), None)
    if header is None:
        return None
    end = next((j for j in range(header + 1, len(lines)) if HEADING_RE.match(lines[j])), len(lines))
    insert, seen = header + 1, False
    for j in range(header + 1, end):
        text = lines[j].rstrip("\r\n")
        if re.match(r"^[-*][ \t]", text):
            seen, insert = True, j + 1
        elif not seen:
            continue
        elif text[:1] in (" ", "\t") and text.strip():
            insert = j + 1
        else:
            break
    return header, insert, end


def _item_re(number):
    return re.compile(r"^[ \t]*[-*][ \t]+(?:\[[ xX]\][ \t]+)?#{0}(?!\d)".format(int(number)))


def is_listed(body, number):
    """True when the Proposed section already has a list line for #number."""
    lines = (body or "").splitlines(True)
    section = _section(lines)
    if section is None:
        return False
    header, _insert, end = section
    item = _item_re(number)
    return any(item.match(lines[j]) for j in range(header + 1, end))


def _clean_title(title):
    text = str(title or "").replace("<!--", " ").replace("-->", " ")
    text = re.sub(r"\s+", " ", text).strip().rstrip(" .")
    if len(text) > TITLE_MAX:
        text = text[:TITLE_MAX - 3].rstrip() + "..."
    return text or "(untitled)"


def proposed_line(number, title, date, line_id=None, originating=None):
    """The one line the loop adds for spec-proposal #number."""
    if line_id and LINE_ID_RE.match(str(line_id)):
        source = "Maintenance backlog line `{0}`".format(line_id)
    elif originating:
        source = "issue #{0}".format(int(originating))
    else:
        source = "the board loop's work item"
    return "- #{0}: {1}. Filed by the board loop {2} from {3}.".format(
        int(number), _clean_title(title), date, source)


def add_line(body, number, line):
    """`body` with `line` appended to the Proposed list; `body` unchanged
    when #number is already listed there; None when there is no Proposed
    header (board_backlog_edit.edit() reads None as a stand-down)."""
    body = body or ""
    lines = body.splitlines(True)
    section = _section(lines)
    if section is None:
        return None
    if is_listed(body, number):
        return body
    newline = "\r\n" if "\r\n" in body else "\n"
    _header, insert, _end = section
    if insert > 0 and not lines[insert - 1].endswith(("\n", "\r")):
        lines[insert - 1] += newline
    lines.insert(insert, line + newline)
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
                    run=None, fetch=None, write=None, today=None, title=None):
    """Lists spec-proposal #spec_number on the Roadmap. Returns
    (outcome, message): outcome is board_backlog_edit's APPLIED, FAILED,
    or NOT_FOUND / NO_HEADER. Never raises; every outcome but APPLIED is
    also printed as a ::warning:: and every outcome is written to the run
    summary."""
    run = run or subprocess.run
    repository = repository or os.environ.get("GITHUB_REPOSITORY") or ""
    bot_login = bot_login if bot_login is not None else os.environ.get("BOT_LOGIN") or ""
    fetch = fetch or bbe.gh_fetch
    write = write or bbe.gh_write
    today = today or datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    try:
        roadmap, reason = bbl.resolve_tracking(list_tracking(repository, run), bot_login, TITLE_PREFIX)
        if roadmap is None:
            outcome, message = NOT_FOUND, "the Roadmap issue was not found ({0})".format(reason)
        else:
            if title is None:
                title = _gh_text(run, ["issue", "view", str(spec_number), "-R", repository,
                                       "--json", "title", "--jq", ".title"]).strip()
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
        outcome, message = bbe.FAILED, "the Roadmap could not be updated ({0})".format(
            str(exc).splitlines()[0] if str(exc) else type(exc).__name__)
    text = "board-loop: spec-proposal #{0}: {1}.".format(spec_number, message)
    if outcome != bbe.APPLIED:
        print("::warning::{0} Add its line to the Roadmap's Proposed list by hand.".format(text),
              file=sys.stderr)
    _summary(text if outcome == bbe.APPLIED else text + " Add its line to the Roadmap's Proposed list by hand.")
    return outcome, message
