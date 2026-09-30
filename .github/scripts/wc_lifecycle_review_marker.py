#!/usr/bin/env python3
"""Lifecycle review gate marker (specs/062-lifecycle-review-gate, T074/F3,
contracts/lifecycle-review-gate-workflow.md, data-model.md §1).

WHY THIS EXISTS
---------------
`review_gate` state (round, the head SHA a round reviewed, its outcome,
open finding count, and the folded/filed fingerprint sets FR-021's dedup
needs) used to live in `spec-meta.json`, written by a commit `disposition`
pushed to the lifecycle PR's own branch. Maintainer review 5355876805 (F3)
found that fatal for auto-merge: the push advances the PR's real head past
the SHA the round just recorded, so `lint-workflows` never runs on the
bookkeeping commit, the `lifecycle-review-gate` status never lands on the
real head, and `merge` can never see a clean round at the current tip. It
also stacked on F1/F2: a branch-authored commit deciding facts that same
branch is judged by, peeled back by commit *subject* alone (T069's
`wc_review_gate_settled_head.py`, deleted alongside this module landing --
F2), is a forgeable trust boundary.

The fix: record `review_gate` on the LIFECYCLE ISSUE's own comments
instead, the way `board_item_marker.py` records a board loop item's state
-- never a commit to the pull request whose merge that state gates. This
module reuses that module's own `find_latest_marker()`/
`is_loop_marker_author()` (the "latest bot-authored comment, last opener
wins" algorithm) rather than re-deriving it a second time (CLAUDE.md's
single-home rule); only the marker's own name and payload shape are new.

`report` appends `write_marker()`'s output to the same round-outcome
comment it already posts on the lifecycle issue (never the comment's only
content, matching `board_item_marker.write_marker()`'s own discipline).
`select`, `review`, `disposition` and `merge` read it back via
`read_marker()`, given the lifecycle issue's own comments as the REST API
returns them and this App's own bot login -- see read_marker() for the
shape, and why `gh issue view --json comments` cannot supply it (#826).

This marker is the single source of truth for `review_gate` state -- there
is no second, git-committed copy to cross-check it against once
spec-meta.json no longer carries the field (data-model.md §1, amended).
A missing or unparsable marker means no round has ever completed for this
PR, exactly as an absent `spec-meta.json.review_gate` did before."""
import argparse
import json
import os
import sys

# `python3 -I` (the pristine-snapshot invocation shape `review`'s own
# "Gather review inputs" step uses, T073) excludes this script's own
# directory from sys.path, so the sibling import below would otherwise
# raise ModuleNotFoundError -- board_item_marker.py's own main() documents
# the identical fix for its `-I`-invoked callers. The snapshot directory is
# trusted, so adding it back is safe.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from board_item_marker import find_latest_marker, marker_regexes  # noqa: E402

MARKER_NAME = "wing-commander-lifecycle-review-gate"
MARKER_RE, MARKER_OPEN_RE = marker_regexes(MARKER_NAME)


def read_marker(issue_comments, bot_login):
    """The latest review_gate marker this App posted on the lifecycle
    issue's own comments, or None when no round has ever completed.

    issue_comments must be REST-shaped -- `gh api
    "repos/$GITHUB_REPOSITORY/issues/<n>/comments" --paginate --jq '.[]' |
    jq -s '.'`, each comment carrying `user: {login, type}` -- because
    board_item_marker.is_loop_marker_author() requires `user.type ==
    "Bot"`. `gh issue view --json comments` returns `author: {login}` and
    no `user` at all, so every comment in that shape reads as someone
    else's and the marker is always None (#826). Gate 112
    (verify-lifecycle-merge-preconditions.py) fails a workflow step that
    feeds a marker reader from `--json comments`."""
    pair = find_latest_marker(issue_comments, bot_login, MARKER_RE, MARKER_OPEN_RE)
    return pair[1] if pair else None


def write_marker(round_, head_sha, outcome, findings_open,
                  folded_fingerprints, filed_fingerprints, updated_at):
    """Renders the HTML-comment marker line, appended to `report`'s own
    human-legible round-outcome comment on the lifecycle issue (never the
    comment's only content) -- the shape `board_item_marker.write_marker()`
    documents for the board loop's own item state, applied to this
    feature's own payload (data-model.md §1)."""
    payload = json.dumps(
        {"round": round_, "head_sha": head_sha, "outcome": outcome,
         "findings_open": findings_open,
         "folded_fingerprints": folded_fingerprints or [],
         "filed_fingerprints": filed_fingerprints or [],
         "updated_at": updated_at},
        sort_keys=True)
    return "<!-- {0}: {1} -->".format(MARKER_NAME, payload)


def self_test():
    """Exercised by Gate 107's own self-test (verify-lifecycle-readiness.py),
    the same "fold it into an existing gate's self-test, never a bare
    --self-test step nothing invokes" idiom T069/#476 established for the
    module this one replaces -- this repository's gate suite is discovered
    from verify-*.py/.sh invocations in lint-workflows.yml
    (wc_gate_registry.py)."""
    failures = []

    def check(name, cond, detail=""):
        if not cond:
            failures.append("{0} {1}".format(name, detail))

    written = write_marker(2, "deadbeef", "findings", 1, ["fp1"], [], "2026-01-01T00:00:00Z")
    check("write-marker-embeds-name", MARKER_NAME in written)
    body = "lifecycle-review-gate: round 2 -- 1 finding open.\n\n" + written
    # The REST shape (`gh api .../issues/<n>/comments`), trimmed to the
    # fields the reader uses plus a few it ignores -- never a hand-made
    # shape no production read returns (#826).
    comments = [{"id": 1, "created_at": "2026-01-01T00:00:00Z",
                 "updated_at": "2026-01-01T00:00:00Z", "body": body,
                 "author_association": "NONE",
                 "user": {"login": "wing-commander-bot[bot]", "type": "Bot"}}]
    got = read_marker(comments, "wing-commander-bot[bot]")
    check("round-trip", got == {"round": 2, "head_sha": "deadbeef",
                                "outcome": "findings", "findings_open": 1,
                                "folded_fingerprints": ["fp1"],
                                "filed_fingerprints": [],
                                "updated_at": "2026-01-01T00:00:00Z"},
          "got {0!r}".format(got))

    # A human commenting on the lifecycle issue cannot forge a marker --
    # only this App's own bot-authored comments are read (is_loop_marker_author).
    forged = [{"created_at": "2026-01-02T00:00:00Z", "body": written,
               "user": {"login": "an-outsider", "type": "User"}}]
    check("non-bot-comment-ignored",
          read_marker(forged, "wing-commander-bot[bot]") is None)

    # #826: the same bot comment in `gh issue view --json comments`'s shape
    # (GraphQL: `author: {login}`, `createdAt`, no `user`) reads as no
    # marker. This pins WHY the workflow reads through REST; if it ever
    # started passing, is_loop_marker_author() changed and every reader of
    # it needs a second look.
    graphql_shaped = [{"createdAt": "2026-01-01T00:00:00Z", "body": body,
                       "author": {"login": "wing-commander-bot"}}]
    check("gh-json-comments-shape-reads-as-no-marker",
          read_marker(graphql_shaped, "wing-commander-bot[bot]") is None)

    # No round has ever completed: no marker at all, never a crash.
    check("no-marker-returns-none", read_marker([], "wing-commander-bot[bot]") is None)
    check("no-comments-returns-none", read_marker(None, "wing-commander-bot[bot]") is None)

    # This module's own marker name is never confused with the board loop's
    # (both can appear in the same comment, once each gate posts its own
    # status on the lifecycle issue).
    other_marker = "<!-- wing-commander-board-item: {\"step\": \"review\"} -->"
    mixed = [{"created_at": "2026-01-03T00:00:00Z",
              "body": other_marker + "\n" + written,
              "user": {"login": "wing-commander-bot[bot]", "type": "Bot"}}]
    check("distinct-from-board-item-marker",
          read_marker(mixed, "wing-commander-bot[bot]") is not None)

    for f in failures:
        print("::error::wc_lifecycle_review_marker --self-test: {0}".format(f))
    if failures:
        print("{0} failure(s).".format(len(failures)))
        return 1
    print("wc_lifecycle_review_marker --self-test: ok.")
    return 0


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="mode", required=True)

    read_p = sub.add_parser(
        "read", help="reads a JSON array of REST-shaped issue comments "
        "(gh api .../issues/<n>/comments, never gh issue view --json "
        "comments) from stdin, prints the marker dict (or {}) to stdout")
    read_p.add_argument("--bot-login", required=True)

    write_p = sub.add_parser(
        "write", help="prints the rendered marker line to stdout")
    write_p.add_argument("--round", type=int, required=True)
    write_p.add_argument("--head-sha", required=True)
    write_p.add_argument("--outcome", required=True)
    write_p.add_argument("--findings-open", type=int, required=True)
    write_p.add_argument("--folded-fingerprints", default="",
                          help="comma-separated; empty means none")
    write_p.add_argument("--filed-fingerprints", default="",
                          help="comma-separated; empty means none")
    write_p.add_argument("--updated-at", required=True)

    sub.add_parser("self-test")

    args = parser.parse_args()
    if args.mode == "self-test":
        sys.exit(self_test())
    elif args.mode == "read":
        comments = json.load(sys.stdin)
        marker = read_marker(comments, args.bot_login)
        json.dump(marker if marker is not None else {}, sys.stdout)
    else:
        folded = [f for f in args.folded_fingerprints.split(",") if f]
        filed = [f for f in args.filed_fingerprints.split(",") if f]
        print(write_marker(args.round, args.head_sha, args.outcome,
                            args.findings_open, folded, filed,
                            args.updated_at))


if __name__ == "__main__":
    main()
