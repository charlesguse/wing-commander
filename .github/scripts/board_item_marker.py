#!/usr/bin/env python3
"""Board item marker read/write (specs/057-autonomous-board-loop,
contracts/board-item-marker.md, data-model.md "Board Item Marker",
research.md D21).

The marker is a fast path only: every field it supplies MUST be re-derived
from live GitHub state before any durable action is taken (FR-054). This
module only reads/writes the marker's own HTML-comment shape -- it never
decides whether a re-derivation contradicts it.
"""
import json
import re

MARKER_RE = re.compile(
    r"<!--\s*wing-commander-board-item:\s*(\{.*?\})\s*-->", re.DOTALL)


def read_marker(issue_comments):
    """issue_comments: a list of {"created_at": "...", "body": "..."}
    dicts (an issue's own comments, any order). Returns the most recent
    well-formed board-item marker dict found in any comment body, or None
    when no comment carries one, or the newest one is not valid JSON
    (missing/unparsable marker -- degrade to None, never raise; the caller
    falls back to live GitHub state per FR-054)."""
    dated_markers = []
    for comment in issue_comments or []:
        body = comment.get("body") or ""
        match = MARKER_RE.search(body)
        if not match:
            continue
        try:
            marker = json.loads(match.group(1))
        except ValueError:
            continue
        if not isinstance(marker, dict):
            continue
        dated_markers.append((comment.get("created_at") or "", marker))
    if not dated_markers:
        return None
    dated_markers.sort(key=lambda pair: pair[0])
    return dated_markers[-1][1]


def write_marker(step, round, pr, branch, base_sha):
    """Renders the HTML-comment marker line. Appended to the loop's own
    human-legible status comment -- never the comment's only content
    (FR-044) -- by the caller."""
    payload = json.dumps(
        {"step": step, "round": round, "pr": pr, "branch": branch,
         "base_sha": base_sha},
        sort_keys=True)
    return "<!-- wing-commander-board-item: {0} -->".format(payload)
