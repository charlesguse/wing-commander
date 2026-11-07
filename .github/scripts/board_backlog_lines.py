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
FENCE_RE = re.compile(r"^\s*(```|~~~)")

STATES = ("in-progress", "held", "proposal", "fixed", "evidence")


def _sanitise(detail):
    """One line, no `]` (it would close the token), no HTML comment openers."""
    text = re.sub(r"\s+", " ", str(detail or "")).strip()
    return text.replace("]", ")").replace("<!--", "").replace("-->", "")


def parse_lines(body):
    """Returns a list of {"index", "checked", "raw", "text", "id", "state",
    "detail"} for each line in `body`; `index` is the 0-based line number."""
    lines = []
    in_fence = False
    for index, raw in enumerate((body or "").split("\n")):
        raw = raw.rstrip("\r")
        if FENCE_RE.match(raw):
            in_fence = not in_fence
            continue
        if in_fence or raw.startswith(">"):
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
    parts[index] = new_raw
    return "\n".join(parts)


def annotate(body, line_id, state, detail="", *, allow_new=True, only_unannotated=False):
    """Annotates the line carrying `line_id` (or, for a claim, the topmost
    unchecked un-annotated line whose text is passed as `detail`'s owner via
    claim()). Returns the new body, or None for a missing, duplicated or
    ticked line (stand down)."""
    if state not in STATES:
        raise ValueError("unknown state {0!r}".format(state))
    line = _find(body, line_id)
    if line is None or line["checked"]:
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
    is missing, duplicated or ticked."""
    line = _find(body, line_id)
    if line is None or line["checked"]:
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


def select_line(body, *, claimed_ids=()):
    """The topmost unchecked, un-annotated line, or None."""
    for line in parse_lines(body):
        if not line["checked"] and line["id"] is None and line["id"] not in claimed_ids:
            return line
    return None


def main():
    try:
        request = json.load(sys.stdin)
        op = request["op"]
        body = request.get("body", "")
        if op == "parse":
            result = parse_lines(body)
        elif op == "select":
            result = select_line(body)
        else:
            raise ValueError("unknown op {0!r}".format(op))
    except (ValueError, KeyError) as exc:
        print("::error::board_backlog_lines: {0}".format(exc), file=sys.stderr)
        sys.exit(2)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
