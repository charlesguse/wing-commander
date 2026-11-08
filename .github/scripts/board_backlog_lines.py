#!/usr/bin/env python3
"""Maintenance backlog line parsing and annotation
(specs/121-board-backlog-line-items, data-model.md, contracts/backlog-lines.md).

Pure and stdlib-only: every function takes the issue body (a string) and
returns a value; nothing here touches GitHub. Writes go through
board_backlog_edit.edit() (the single home for backlog-body edits).

A *line* is a column-0 `- [ ] ` or `- [x] ` checklist line outside fenced
code blocks and blockquotes. Nested or indented checkboxes are not lines.
A line may carry one annotation token `[wc:<id> <state>( <detail>)?]`.
"""
import json
import re
import sys

LINE_RE = re.compile(r"^- \[( |x|X)\] (.*)$")
ANNOTATION_RE = re.compile(r"\[wc:([a-z0-9-]{1,40}) ([a-z-]+)(?: ([^\]\n]*))?\]")
FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})")

STATES = ("in-progress", "held", "proposal", "fixed", "evidence")


def _sanitise(detail):
    """One line, no `]` (it would close the token), no HTML comment openers."""
    text = re.sub(r"\s+", " ", str(detail or "")).strip()
    return text.replace("]", ")").replace("<!--", "").replace("-->", "")


def parse_lines(body):
    """Returns a list of {"index", "checked", "raw", "text", "id", "state",
    "detail"} for each line in `body`; `index` is the 0-based line number."""
    lines = []
    fence = None      # the opening fence marker while inside a fenced block
    in_comment = False
    for index, raw in enumerate((body or "").split("\n")):
        raw = raw.rstrip("\r")
        opener = FENCE_RE.match(raw)
        if fence is not None:
            # Only a fence of the same character, at least as long, closes it.
            if (opener and opener.group(1)[0] == fence[0]
                    and len(opener.group(1)) >= len(fence)
                    and not raw.strip()[len(opener.group(1)):].strip()):
                fence = None
            continue
        if in_comment:
            if "-->" in raw:
                in_comment = False
            continue
        if opener:
            fence = opener.group(1)
            continue
        if raw.startswith("<!--") and "-->" not in raw:
            in_comment = True
            continue
        if raw.startswith(">"):
            continue
        match = LINE_RE.match(raw)
        if not match:
            continue
        rest = match.group(2)
        annotation = ANNOTATION_RE.search(rest)
        entry = {"index": index, "checked": match.group(1) != " ", "raw": raw,
                 "id": None, "state": None, "detail": None}
        if annotation:
            entry["id"] = annotation.group(1)
            entry["state"] = annotation.group(2)
            entry["detail"] = annotation.group(3) or ""
            rest = (rest[:annotation.start()] + rest[annotation.end():])
        entry["text"] = re.sub(r"\s+", " ", rest).strip()
        lines.append(entry)
    return lines


def _find(body, line_id):
    hits = [line for line in parse_lines(body) if line["id"] == line_id]
    return hits[0] if len(hits) == 1 else None


def _replace(body, index, new_raw):
    parts = body.split("\n")
    if parts[index].endswith("\r"):
        new_raw += "\r"
    parts[index] = new_raw
    return "\n".join(parts)


# Which current states each annotation may replace (None = un-annotated):
# a stale progress write must not un-hold a held line, nor a proposal.
ANNOTATE_FROM = {
    "in-progress": (None, "in-progress"),
    "held": (None, "in-progress", "held"),
    "proposal": (None, "in-progress", "proposal"),
}


def annotate(body, line_id, state, detail=""):
    """Annotates the line carrying `line_id` (or, for a claim, the topmost
    unchecked un-annotated line whose text is passed as `detail`'s owner via
    claim()). Returns the new body, or None for a missing, duplicated or
    ticked line (stand down)."""
    if state not in STATES:
        raise ValueError("unknown state {0!r}".format(state))
    line = _find(body, line_id)
    if line is None or line["checked"]:
        return None
    if line["state"] not in ANNOTATE_FROM.get(state, (line["state"],)):
        return None
    token = "[wc:{0} {1}{2}]".format(line_id, state, " " + _sanitise(detail) if _sanitise(detail) else "")
    prefix = "- [ ] "
    return _replace(body, line["index"], prefix + (line["text"] + " " + token).strip())


def claim(body, line_id, text):
    """Annotates the topmost unchecked un-annotated line whose text equals
    `text` as in-progress with `line_id`. None when nothing matches or
    `line_id` is already present."""
    if any(line["id"] == line_id for line in parse_lines(body)):
        return None
    for line in parse_lines(body):
        if not line["checked"] and line["id"] is None and line["text"] == text:
            return _replace(body, line["index"],
                            "- [ ] {0} [wc:{1} in-progress]".format(line["text"], line_id))
    return None


def tick(body, line_id, annotation_state, detail=""):
    """Ticks the line and replaces its annotation with `annotation_state`
    (`fixed` or `evidence`). None for a missing, duplicated or ticked line."""
    line = _find(body, line_id)
    if line is None or line["checked"]:
        return None
    token = "[wc:{0} {1}{2}]".format(
        line_id, annotation_state, " " + _sanitise(detail) if _sanitise(detail) else "")
    return _replace(body, line["index"], "- [x] " + (line["text"] + " " + token).strip())


def clear_note(body, line_id):
    """Removes the line's annotation (releasing a hold). None when the line
    is missing, duplicated, ticked or not held (it never clears a claim)."""
    line = _find(body, line_id)
    if line is None or line["checked"] or line["state"] != "held":
        return None
    return _replace(body, line["index"], "- [ ] " + line["text"])


def note_proof(body, line_id, reason, url=""):
    """Replaces any earlier not-proven note on a ticked `fixed` line."""
    line = _find(body, line_id)
    if line is None or not line["checked"]:
        return None
    # The link stays outside the token (a `]` or `)` would end it) and any
    # earlier note's link is dropped, so a later note replaces the earlier.
    text = re.sub(r"\s*\[run\]\([^)]*\)", "", line["text"]).strip()
    token = "[wc:{0} fixed not-proven: {1}]".format(line_id, _sanitise(reason))
    suffix = " [run]({0})".format(re.sub(r"[\s)\]]", "", url)) if url else ""
    return _replace(body, line["index"], "- [x] " + text + " " + token + suffix)


def select_line(body):
    """The topmost unchecked, un-annotated line, or None."""
    for line in parse_lines(body):
        if not line["checked"] and line["id"] is None:
            return line
    return None


def resolve_backlog(open_issues, bot_login, maintainer_logins=()):
    """FR-002: exactly one open `disposition:tracking` issue titled
    "Maintenance backlog…", authored by a maintainer or the App. Returns
    (issue_number, None) or (None, reason)."""
    allowed = set(maintainer_logins) | {bot_login}
    hits = []
    for issue in open_issues:
        labels = [l if isinstance(l, str) else l.get("name") for l in issue.get("labels", [])]
        if str(issue.get("state", "open")).lower() != "open" or "disposition:tracking" not in labels:
            continue
        if not str(issue.get("title", "")).startswith("Maintenance backlog"):
            continue
        hits.append(issue)
    if not hits:
        return None, "no open Maintenance backlog issue"
    if len(hits) > 1:
        return None, "ambiguous: {0} Maintenance backlog candidates".format(len(hits))
    author = hits[0].get("author")
    if isinstance(author, dict):
        author = author.get("login")
    assoc = str(hits[0].get("authorAssociation") or hits[0].get("author_association") or "").upper()
    if assoc in ("OWNER", "MEMBER"):
        return hits[0]["number"], None
    if author not in allowed:
        return None, "backlog issue author {0!r} is not a maintainer or the App".format(author)
    return hits[0]["number"], None


def selection_gate(env):
    """FR-023/FR-025: (True, None) or (False, reason). `env` carries
    backlog_lines_switch, loop_paused and constitution_text (None when
    unreadable)."""
    if env.get("backlog_lines_switch") != "true":
        return False, "backlog lines switch is not true"
    if env.get("loop_paused") in (True, "true"):
        return False, "board loop is paused"
    text = env.get("constitution_text")
    if text is None:
        return False, "constitution unreadable"
    match = re.search(r"^### X\..*?(?=^### |\Z)", text, re.S | re.M)
    if not match or "Maintenance backlog line" not in match.group(0):
        return False, "constitution Principle X does not authorise backlog lines"
    return True, None


def mint_id(body):
    """`bl-` + 8 hex, never present in `body`."""
    import secrets
    while True:
        candidate = "bl-" + secrets.token_hex(4)
        if candidate not in (body or ""):
            return candidate


def branch_for(issue, line_id):
    """Fix branch for a line; asserts the shape board_merge accepts."""
    from board_merge import FIX_BRANCH_RE
    branch = "fix/{0}-{1}".format(issue, line_id)
    if FIX_BRANCH_RE.fullmatch(branch) is None:
        raise ValueError("branch {0!r} does not match FIX_BRANCH_RE".format(branch))
    return branch


def title_for(text, prefix="Fix: "):
    """PR/proposal title: annotation stripped, whitespace collapsed,
    truncated with an ellipsis so the whole title is at most 200 chars."""
    text = re.sub(r"\s+", " ", ANNOTATION_RE.sub("", text or "")).strip()
    text = re.sub(r"#(?=\d)", "#​", text).replace("/issues/", "/issues​/")
    text = re.sub(r"(?i)\bGH-(?=\d)", "GH-​", text)
    if len(prefix + text) > 200:
        text = text[:200 - len(prefix) - 1].rstrip() + "…"
    return prefix + text


CLOSING_RE = re.compile(
    r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\b[:\s]+"
    r"(?:https?://github\.com/[\w.-]+/[\w.-]+/issues/\d+|[\w.-]+/[\w.-]+#\d+|#\d+|GH-\d+)",
    re.I)


def closing_keyword_hits(title, body, commit_messages):
    """Returns the list of (where, match) closing-keyword hits."""
    hits = []
    for where, text in [("title", title), ("body", body)] + [
            ("commit", m) for m in (commit_messages or [])]:
        for match in CLOSING_RE.finditer(text or ""):
            hits.append((where, match.group(0)))
    return hits


def render_line_text_for_body(text):
    """Code span with `#` references defanged so no closing keyword forms."""
    safe = (text or "").replace("`", "'").replace("#", "#​").replace("/issues/", "/issues​/")
    safe = re.sub(r"(?i)\bGH-(?=\d)", "GH-​", safe)
    return "`{0}`".format(re.sub(r"\s+", " ", safe).strip())


def main():
    try:
        request = json.load(sys.stdin)
        op = request["op"]
        body = request.get("body", "")
        if op == "parse":
            result = parse_lines(body)
        elif op == "select":
            result = select_line(body)
        elif op == "check-closing-keywords":
            result = closing_keyword_hits(request.get("title", ""), body,
                                          request.get("commits", []))
        elif op in ("claim", "progress", "hold", "release", "route-proposal",
                    "tick-evidence", "tick-fixed", "note-proof"):
            import board_backlog_edit as bbe
            apply_fn, verify = bbe._operations(op, request["line_id"], request.get("detail", ""),
                                               request.get("url", ""))
            result = bbe.edit(request["issue"], apply_fn, verify,
                              fetch=bbe.gh_fetch, write=bbe.gh_write)
        else:
            raise ValueError("unknown op {0!r}".format(op))
    except (ValueError, KeyError) as exc:
        print("::error::board_backlog_lines: {0}".format(exc), file=sys.stderr)
        sys.exit(2)
    except RuntimeError as exc:
        print("::error::board_backlog_lines: {0}".format(exc), file=sys.stderr)
        sys.exit(1)
    print(json.dumps(result, sort_keys=True))
    if result == "failed":
        sys.exit(1)


if __name__ == "__main__":
    main()
