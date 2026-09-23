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
import os
import re

MARKER_RE = re.compile(
    r"<!--\s*wing-commander-board-item:\s*(\{.*?\})\s*-->", re.DOTALL)


def read_marker_with_timestamp(issue_comments):
    """issue_comments: a list of {"created_at": "...", "body": "..."}
    dicts (an issue's own comments, any order). Returns
    (created_at, marker) for the most recent well-formed board-item marker
    found in any comment body, or None when no comment carries one, or the
    newest one is not valid JSON (missing/unparsable marker -- degrade to
    None, never raise; the caller falls back to live GitHub state per
    FR-054)."""
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
    return dated_markers[-1]


def read_marker(issue_comments):
    """issue_comments: a list of {"created_at": "...", "body": "..."}
    dicts (an issue's own comments, any order). Returns the most recent
    well-formed board-item marker dict found in any comment body, or None
    when no comment carries one, or the newest one is not valid JSON
    (missing/unparsable marker -- degrade to None, never raise; the caller
    falls back to live GitHub state per FR-054)."""
    pair = read_marker_with_timestamp(issue_comments)
    return pair[1] if pair else None


def write_marker(step, round, pr, branch, base_sha):
    """Renders the run announcement plus the HTML-comment marker line.
    Appended to the loop's own human-legible status comment -- never the
    comment's only content (FR-044) -- by the caller.

    Every call carries a `**Run:** <url>` line (research.md D17,
    contracts/board-loop-workflow.md's stop procedure, spec 057 T051): the
    same shape pr-conversation.yml's own announcements already use, so the
    stop procedure's scan (`test("\\*\\*Run:\\*\\*")`, newest-first,
    skipping this run's own announcement by GITHUB_RUN_ID) finds this
    comment without a second announcement convention. GITHUB_SERVER_URL/
    GITHUB_REPOSITORY/GITHUB_RUN_ID are ambient in every Actions step, so
    every existing write_marker() call site gets this for free."""
    payload = json.dumps(
        {"step": step, "round": round, "pr": pr, "branch": branch,
         "base_sha": base_sha},
        sort_keys=True)
    marker = "<!-- wing-commander-board-item: {0} -->".format(payload)

    server_url = os.environ.get("GITHUB_SERVER_URL")
    repository = os.environ.get("GITHUB_REPOSITORY")
    run_id = os.environ.get("GITHUB_RUN_ID")
    if server_url and repository and run_id:
        run_url = "{0}/{1}/actions/runs/{2}".format(server_url, repository, run_id)
        return "**Run:** {0}\n\n{1}".format(run_url, marker)
    return marker
