#!/usr/bin/env python3
"""Gate — board_backlog_lines.py parses, selects and annotates Maintenance
backlog lines exactly as the fixtures under
.github/scripts/tests/board-backlog-lines/ say (specs/121-board-backlog-line-items,
FR-019).

    python3 .github/scripts/verify-board-backlog-lines.py
    python3 .github/scripts/verify-board-backlog-lines.py --self-test
"""
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import board_backlog_lines as bbl  # noqa: E402

FIXTURES = os.path.join(HERE, "tests", "board-backlog-lines", "*.json")

OPS = {
    "claim": bbl.claim,
    "annotate": bbl.annotate,
    "tick": bbl.tick,
    "clear": bbl.clear_note,
    "note_proof": bbl.note_proof,
}


def _subset(expected, actual):
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(
            key in actual and _subset(value, actual[key]) for key, value in expected.items())
    if isinstance(expected, list):
        return (isinstance(actual, list) and len(expected) == len(actual)
                and all(_subset(e, a) for e, a in zip(expected, actual)))
    return expected == actual


def run_case(case):
    """Returns an error string or None."""
    op = case["op"]
    body = case.get("body", "")
    if op == "parse":
        actual = bbl.parse_lines(body)
        return None if _subset(case["expect"], actual) else "parse: got {0!r}".format(actual)
    if op == "select":
        actual = bbl.select_line(body)
        return None if _subset(case["expect"], actual) else "select: got {0!r}".format(actual)
    if op == "resolve":
        actual = list(bbl.resolve_backlog(case["issues"], case["bot"], case.get("maintainers", ())))
        return None if actual == case["expect"] else "resolve: got {0!r}".format(actual)
    if op == "gate":
        actual = list(bbl.selection_gate(case["env"]))
        return None if actual == case["expect"] else "gate: got {0!r}".format(actual)
    if op == "title":
        actual = bbl.title_for(case["text"])
        if len(actual) > 200 or ("max_len" in case and len(actual) > case["max_len"]):
            return "title too long: {0}".format(len(actual))
        return None if actual.startswith(case["expect_prefix"]) else "title: got {0!r}".format(actual)
    if op == "branch":
        actual = bbl.branch_for(case["issue"], case["line_id"])
        return None if actual == case["expect"] else "branch: got {0!r}".format(actual)
    if op == "closing":
        actual = bbl.closing_keyword_hits(case["title"], case["body"], case["commits"])
        return None if bool(actual) == case["expect_hit"] else "closing: got {0!r}".format(actual)
    if op == "render":
        actual = bbl.render_line_text_for_body(case["text"])
        return None if not bbl.closing_keyword_hits("", actual, []) else "render: keyword survived {0!r}".format(actual)
    if op == "marker":
        import board_item_marker as bim
        text = bim.write_marker("fix", 1, None, case["branch"], "abc", line=case.get("line"))
        comments = [{"created_at": "2026-01-01T00:00:00Z", "body": text,
                     "user": {"login": case["bot"], "type": "Bot"}}]
        found = bim.find_latest_marker(comments, case["bot"])
        read_back = found[1].get("line") if found else None
        issue_path = bim.read_marker(comments, case["bot"])
        if read_back != case.get("line"):
            return "marker: line round trip got {0!r}".format(read_back)
        if (issue_path is None) != case["issue_path_ignores"]:
            return "marker: issue path read {0!r}".format(issue_path)
        return None
    if op == "chain":
        for number, step in enumerate(case["steps"]):
            new_body = OPS[step["op"]](body, *step["args"])
            if new_body != case["expect_after"][number]:
                return "step {0} ({1}): got {2!r}".format(number, step["op"], new_body)
            if new_body is not None:
                body = new_body
        return None
    return "unknown op {0!r}".format(op)


def run(fixtures=None, verbose=True):
    failures = 0
    paths = sorted(glob.glob(FIXTURES)) if fixtures is None else fixtures
    if not paths:
        print("::error::verify-board-backlog-lines: no fixtures found")
        return 1
    for path in paths:
        with open(path, encoding="utf-8") as fh:
            case = json.load(fh)
        error = run_case(case)
        name = os.path.basename(path)
        if error:
            failures += 1
            print("::error::verify-board-backlog-lines: {0}: {1}".format(name, error))
        elif verbose:
            print("[ok] {0}".format(name))
    return failures


def self_test():
    """A parser that ignores fences must fail the structure fixture."""
    original = bbl.FENCE_RE
    try:
        import re
        bbl.FENCE_RE = re.compile(r"^never-matches$")
        broken = run(verbose=False)
    finally:
        bbl.FENCE_RE = original
    if not broken:
        print("::error::verify-board-backlog-lines --self-test: a parser ignoring fences passed")
        return 1
    return 0


def main(argv):
    if argv == ["--self-test"]:
        return self_test()
    if argv:
        sys.exit("takes --self-test or nothing.")
    failures = run()
    print("verify-board-backlog-lines: {0} failure(s).".format(failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
