#!/usr/bin/env python3
"""The single home for editing the Maintenance backlog issue body
(specs/121-board-backlog-line-items, contracts/backlog-lines.md, FR-024).

edit() fetches the body, applies a pure function, writes it, then re-fetches
and checks the change survived; a concurrent writer that dropped it makes the
loop re-apply against the fresh body. On exhaustion the body is left as last
fetched -- never a forced write.

    python .github/scripts/board_backlog_edit.py --issue N --op tick-fixed --line-id ID [--detail TEXT]
"""
import argparse
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import board_backlog_lines as bbl  # noqa: E402

APPLIED = "applied"
STAND_DOWN = "stand_down"
FAILED = "failed"


def edit(issue, apply_fn, verify_fn, *, fetch, write, max_attempts=5):
    """Returns APPLIED, STAND_DOWN (apply_fn returned None) or FAILED."""
    for attempt in range(max_attempts):
        body = fetch(issue)
        if attempt and verify_fn(body):
            return APPLIED  # an earlier write of ours landed; the read-back was stale
        new_body = apply_fn(body)
        if new_body is None:
            return STAND_DOWN
        if new_body == body:
            return APPLIED
        write(issue, new_body)
        if verify_fn(fetch(issue)):
            return APPLIED
    return FAILED


def _operations(op, line_id, detail, url=""):
    """(apply_fn, verify_fn) for a named CLI operation."""
    def state_of(body):
        hits = [line for line in bbl.parse_lines(body) if line["id"] == line_id]
        return hits[0] if len(hits) == 1 else None

    table = {
        "claim": (lambda b: bbl.claim(b, line_id, detail), "in-progress", False),
        "progress": (lambda b: bbl.annotate(b, line_id, "in-progress", detail), "in-progress", False),
        "hold": (lambda b: bbl.annotate(b, line_id, "held", detail), "held", False),
        "route-proposal": (lambda b: bbl.annotate(b, line_id, "proposal", detail), "proposal", False),
        "tick-evidence": (lambda b: bbl.tick(b, line_id, "evidence", detail), "evidence", True),
        "tick-fixed": (lambda b: bbl.tick(b, line_id, "fixed", detail), "fixed", True),
        "note-proof": (lambda b: bbl.note_proof(b, line_id, detail, url), "fixed", True),
        "release": (lambda b: bbl.clear_note(b, line_id), None, False),
    }
    if op not in table:
        raise SystemExit("unknown --op {0!r}".format(op))
    apply_fn, state, checked = table[op]

    def verify(body):
        line = state_of(body)
        if state is None:
            return line is not None and line["state"] is None
        if line is None or line["state"] != state or line["checked"] != checked:
            return False
        if op in ("progress", "hold", "route-proposal", "tick-evidence", "tick-fixed"):
            return (line["detail"] or "") == bbl._sanitise(detail)
        if op == "note-proof":
            reason = bbl._sanitise(detail)
            return (line["detail"] or "") == ("not-proven: " + reason if reason else "")
        return True

    return apply_fn, verify


def _gh(args, stdin=None):
    proc = subprocess.run(["gh"] + args, input=stdin, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError("gh {0} failed: {1}".format(" ".join(args[:2]), proc.stderr.strip()))
    return proc.stdout


def gh_fetch(issue):
    repo = os.environ.get("GITHUB_REPOSITORY")
    repo_args = ["-R", repo] if repo else []
    out = _gh(["issue", "view", str(issue)] + repo_args + ["--json", "body", "--jq", ".body"])
    # --jq appends exactly one newline; strip only that one.
    return out[:-1] if out.endswith("\n") else out


def gh_write(issue, body):
    repo = os.environ.get("GITHUB_REPOSITORY")
    repo_args = ["-R", repo] if repo else []
    _gh(["issue", "edit", str(issue)] + repo_args + ["--body-file", "-"], stdin=body)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--issue", type=int, required=True)
    parser.add_argument("--op", required=True)
    parser.add_argument("--line-id", required=True)
    parser.add_argument("--detail", default="")
    parser.add_argument("--url", default="")
    args = parser.parse_args()
    apply_fn, verify = _operations(args.op, args.line_id, args.detail, args.url)
    result = edit(args.issue, apply_fn, verify, fetch=gh_fetch, write=gh_write)
    print(result)
    sys.exit(1 if result == FAILED else 0)


if __name__ == "__main__":
    main()
