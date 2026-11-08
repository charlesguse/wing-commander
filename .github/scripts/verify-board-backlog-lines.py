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
LINE_ENV = "BOARD_LINE_ID"  # board_item_marker.LINE_ENV

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
        if case.get("no_closing") and bbl.closing_keyword_hits(actual, "", []):
            return "title carries a closing keyword: {0!r}".format(actual)
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
        matching = bim.find_latest_marker_matching(comments, case["bot"], lambda m: True)
        if (matching is None) != case["issue_path_ignores"]:
            return "marker: matching reader read {0!r}".format(matching)
        return None
    if op == "context":
        fn = getattr(bbl, "line_context", None)
        actual = fn(body, case["issue"], case["line_id"]) if fn else "<no line_context()>"
        if case.get("expect_none"):
            return None if actual is None else "context: expected None, got {0!r}".format(actual)
        errors = ["context lacks {0!r}".format(n) for n in case["contains"] if n not in (actual or "")]
        errors += ["context carries {0!r}".format(n) for n in case.get("absent", []) if n in (actual or "")]
        return "; ".join(errors) or None
    if op == "stall":
        return run_stall(case)
    if op == "line-readers":
        return run_line_readers(case)
    if op == "chain":
        for number, step in enumerate(case["steps"]):
            new_body = OPS[step["op"]](body, *step["args"])
            if new_body != case["expect_after"][number]:
                return "step {0} ({1}): got {2!r}".format(number, step["op"], new_body)
            if new_body is not None:
                body = new_body
        return None
    return "unknown op {0!r}".format(op)


class _Env:
    """Sets BOARD_LINE_ID (board_item_marker.LINE_ENV) for one case."""

    def __init__(self, line_id):
        self.line_id = line_id

    def __enter__(self):
        self.saved = os.environ.get(LINE_ENV)
        if self.line_id is None:
            os.environ.pop(LINE_ENV, None)
        else:
            os.environ[LINE_ENV] = self.line_id

    def __exit__(self, *exc):
        if self.saved is None:
            os.environ.pop(LINE_ENV, None)
        else:
            os.environ[LINE_ENV] = self.saved


def run_stall(case):
    """The stall rule under BOARD_LINE_ID (specs/121 FR-014/FR-016/FR-017):
    a line is held by its annotation, the backlog issue is never labelled,
    and a line that is gone stands down with a report on the backlog."""
    import board_backlog_edit as bbe
    import board_item_marker as bim
    store = {"body": case["body"]}
    labelled, comments = [], []
    saved = (bbe.gh_fetch, bbe.gh_write, getattr(bbe, "gh_comment", None))
    bbe.gh_fetch = lambda _issue: store["body"]
    bbe.gh_write = lambda _issue, body: store.__setitem__("body", body)
    bbe.gh_comment = lambda issue, body: comments.append(body)

    class _Proc:
        returncode = 0

    def run_label(cmd, **_kw):
        labelled.append(cmd)
        return _Proc()

    summary = os.path.join(os.environ.get("TMPDIR", "/tmp"), "bbl-stall-summary.txt")
    saved_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    os.environ["GITHUB_STEP_SUMMARY"] = summary
    saved_repo = os.environ.get("GITHUB_REPOSITORY")
    os.environ["GITHUB_REPOSITORY"] = "o/r"
    open(summary, "w").close()
    import contextlib
    import io
    try:
        with _Env(case.get("line_id")), contextlib.redirect_stderr(io.StringIO()):
            ok = bim.add_stalled_label(889, "board:stalled", run=run_label)
            if ok:
                bim.record_stall_summary(889, case.get("from_step", "fix (gate suite red)"))
            marker = bim.write_marker("stalled", 0, None, None, None)
    finally:
        bbe.gh_fetch, bbe.gh_write, bbe.gh_comment = saved
        for key, value in (("GITHUB_STEP_SUMMARY", saved_summary), ("GITHUB_REPOSITORY", saved_repo)):
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    errors = []
    if ok != case["expect_ok"]:
        errors.append("add_stalled_label returned {0!r}".format(ok))
    if bool(labelled) != case["expect_labelled"]:
        errors.append("labelled the issue: {0!r}".format(labelled))
    if "expect_body" in case and store["body"] != case["expect_body"]:
        errors.append("body {0!r}".format(store["body"]))
    if bool(comments) != case.get("expect_report", False):
        errors.append("backlog report {0!r}".format(comments))
    line_key = '"line": "{0}"'.format(case["line_id"]) if case.get("line_id") else '"line"'
    if (line_key in marker) != bool(case.get("line_id")):
        errors.append("marker line key: {0!r}".format(marker))
    with open(summary, encoding="utf-8") as fh:
        text = fh.read()
    for needle in case.get("summary_contains", []):
        if needle not in text:
            errors.append("summary lacks {0!r}: {1!r}".format(needle, text))
    return "; ".join(errors) or None


def run_line_readers(case):
    """Issue-path marker readers under BOARD_LINE_ID read only that line's
    markers; with it unset they skip every line marker (specs/121 D5)."""
    import board_item_marker as bim
    comments = []
    for number, marker in enumerate(case["markers"]):
        line = marker.get("line")
        text = bim.write_marker(marker["step"], 0, None, None, None, line=line or None) if line else (
            "<!-- wing-commander-board-item: {0} -->".format(json.dumps(
                {"step": marker["step"], "round": 0, "pr": None, "branch": None, "base_sha": None})))
        comments.append({"created_at": "2026-01-0{0}T00:00:00Z".format(number + 1), "body": text,
                         "user": {"login": "bot[bot]", "type": "Bot"}})
    errors = []
    for line_id, expect in case["expect"].items():
        with _Env(None if line_id == "-" else line_id):
            got = bim.read_marker(comments, "bot[bot]")
            matching = bim.find_latest_marker_matching(comments, "bot[bot]", lambda m: True)
        step = got.get("step") if got else None
        mstep = matching[1].get("step") if matching else None
        if step != expect or mstep != expect:
            errors.append("{0}: read {1!r}/{2!r}, want {3!r}".format(line_id, step, mstep, expect))
    for branch, line_id, want in case.get("branches", []):
        if getattr(bim, "is_line_branch", lambda *a: None)(branch, 889, line_id) != want:
            errors.append("is_line_branch({0!r}, {1!r}) != {2}".format(branch, line_id, want))
    return "; ".join(errors) or None


ISSUE_CONTEXT = os.path.join(os.path.dirname(HERE), "actions", "wing-commander-issue-context", "action.yml")


def issue_context_wiring():
    """The issue-context composite stages a line only through its
    line-id-gated step, and its issue path is skipped only then (FR-007,
    FR-020: with line-id unset the composite is unchanged)."""
    with open(ISSUE_CONTEXT, encoding="utf-8") as fh:
        text = fh.read()
    errors = []
    if "      id: fetch\n      if: inputs.line-id == ''\n" not in text:
        errors.append("the trust-filter step is not gated on line-id being unset")
    if "      id: line\n      if: inputs.line-id != ''\n" not in text:
        errors.append("the line step is not gated on line-id being set")
    if 'board_backlog_lines.py" --line-context' not in text:
        errors.append("the line step does not stage board_backlog_lines.line_context()")
    return errors


def run(fixtures=None, verbose=True):
    failures = 0
    paths = sorted(glob.glob(FIXTURES)) if fixtures is None else fixtures
    if not paths:
        print("::error::verify-board-backlog-lines: no fixtures found")
        return 1
    if fixtures is None:
        for error in issue_context_wiring():
            failures += 1
            print("::error::verify-board-backlog-lines: wing-commander-issue-context: {0}".format(error))
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
