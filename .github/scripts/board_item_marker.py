#!/usr/bin/env python3
"""Board item marker read/write (specs/057-autonomous-board-loop,
contracts/board-item-marker.md, data-model.md "Board Item Marker",
research.md D21).

The marker is a fast path only: every field it supplies MUST be re-derived
from live GitHub state before any durable action is taken (FR-054). This
module only reads/writes the marker's own HTML-comment shape -- it never
decides whether a re-derivation contradicts it.

Only a marker on a comment the loop's own GitHub App posted is read
(is_loop_marker_author(), issue #555). Anyone can comment on a public
repository's issue, so a marker in any other comment is ignored.
"""
import json
import os
import re

MARKER_RE = re.compile(
    r"<!--\s*wing-commander-board-item:\s*(\{.*?\})\s*-->", re.DOTALL)


def is_loop_marker_author(comment, bot_login):
    """True when `comment` was posted by the board loop's own GitHub App:
    `user.type == "Bot"` AND `user.login == bot_login` (the caller's
    `<app-slug>[bot]`, from wing-commander-context's `bot-slug` output).
    An empty/missing bot_login matches nothing. The one author predicate
    for what the loop reads back from its own comments: the board item
    marker (read_marker*, issue #555) and the stop check's `**Run:**`
    announcement (board_stop_check.find_stop_request(), issue #547)."""
    user = comment.get("user") or {}
    return bool(bot_login) and user.get("type") == "Bot" and user.get("login") == bot_login


def is_loop_branch(branch, issue_number):
    """True when `branch` is a name the fix job cuts for `issue_number`:
    `fix/<issue>-<slug>`, the slug being the title lowercased, reduced to
    [a-z0-9-] and cut to 40 characters (or `issue`). The resume step adopts
    a marker's branch only when this holds (issue #555)."""
    if not branch or not str(issue_number).isdigit():
        return False
    pattern = r"fix/{0}-[a-z0-9-]{{1,40}}".format(int(issue_number))
    return re.fullmatch(pattern, branch) is not None


def read_marker_with_timestamp(issue_comments, bot_login):
    """issue_comments: a list of {"created_at": "...", "body": "...",
    "user": {"login": "...", "type": "..."}} dicts (an issue's own
    comments, any order). bot_login: the loop's own App login
    (`<slug>[bot]`); required. Returns (created_at, marker) for the most
    recent well-formed board-item marker in a comment that
    is_loop_marker_author() accepts, or None when no such comment carries
    one, or the newest one is not valid JSON (missing/unparsable marker --
    degrade to None, never raise; the caller falls back to live GitHub
    state per FR-054)."""
    dated_matches = []
    for comment in issue_comments or []:
        if not is_loop_marker_author(comment, bot_login):
            continue
        body = comment.get("body") or ""
        match = MARKER_RE.search(body)
        if not match:
            continue
        dated_matches.append((comment.get("created_at") or "", match.group(1)))
    if not dated_matches:
        return None
    dated_matches.sort(key=lambda pair: pair[0])
    created_at, raw = dated_matches[-1]
    try:
        marker = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(marker, dict):
        return None
    return created_at, marker


def read_marker(issue_comments, bot_login):
    """As read_marker_with_timestamp(), returning only the marker dict (or
    None)."""
    pair = read_marker_with_timestamp(issue_comments, bot_login)
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
