#!/usr/bin/env python3
"""Gate — board_backlog_edit.edit() never loses a concurrent writer's change
and never forces a write (specs/121-board-backlog-line-items, SC-003, FR-024),
and no other script or workflow edits the backlog issue body.

    python3 .github/scripts/verify-board-backlog-edit.py
    python3 .github/scripts/verify-board-backlog-edit.py --self-test
"""
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import board_backlog_edit as bbe  # noqa: E402

FIXTURES = os.path.join(HERE, "tests", "board-backlog-edit", "*.json")


def run_case(case, max_attempts=5):
    store = {"body": case["initial"]}
    pending = list(case.get("after_write", []))
    writes = []

    stale = {"left": 1 if case.get("stale_read_after_write") else 0, "body": case["initial"]}

    def fetch(_issue):
        if writes and stale["left"]:
            stale["left"] -= 1
            return stale["body"]
        return store["body"]

    def write(_issue, body):
        writes.append(body)
        store["body"] = body
        if pending:
            store["body"] = pending.pop(0)

    apply_fn, verify = bbe._operations(case["op"], case["line_id"], case.get("detail", ""))
    result = bbe.edit(1, apply_fn, verify, fetch=fetch, write=write, max_attempts=max_attempts)
    errors = []
    if result != case["expect"]:
        errors.append("result {0!r} != {1!r}".format(result, case["expect"]))
    if "expect_writes" in case and len(writes) != case["expect_writes"]:
        errors.append("{0} writes != {1}".format(len(writes), case["expect_writes"]))
    for needle in case.get("final_contains", []):
        if needle not in store["body"]:
            errors.append("final body lost {0!r}".format(needle))
    if case.get("final_equals_initial") and store["body"] != case["initial"]:
        errors.append("body changed")
    if "final_equals" in case and store["body"] != case["final_equals"]:
        errors.append("final body {0!r}".format(store["body"]))
    return "; ".join(errors) or None


EDIT_RE = re.compile(
    r"gh\s+issue\s+edit\b[^\n]*--body"
    r"|gh\s+api\b[^\n]*(?:-X|--method)[\s=]+PATCH"
    r"|gh\s+api\b[^\n]*PATCH", re.I)
BACKLOG_RE = re.compile(r"backlog", re.I)


def statements(text):
    """(line number, joined text) per statement: backslash-continued lines
    are joined so a multi-line `gh issue edit ... \\ --body-file` is one."""
    out, buf, start = [], [], 1
    for number, line in enumerate(text.split("\n"), 1):
        if not buf:
            start = number
        if line.rstrip().endswith("\\"):
            buf.append(line.rstrip()[:-1])
            continue
        buf.append(line)
        out.append((start, " ".join(buf)))
        buf = []
    if buf:
        out.append((start, " ".join(buf)))
    return out


def single_home_violations(root):
    """Files other than board_backlog_edit.py that edit an issue body in a
    statement that names the maintenance backlog (a continued line counts as
    one statement; `gh api ... PATCH` and `--body-file` forms included)."""
    hits = []
    for pattern in ("scripts/*.py", "scripts/*.sh", "workflows/*.yml", "actions/**/*.yml", "actions/**/*.sh"):
        for path in glob.glob(os.path.join(root, pattern), recursive=True):
            if os.path.basename(path) in ("board_backlog_edit.py", "verify-board-backlog-edit.py"):
                continue
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
            for number, stmt in statements(text):
                if EDIT_RE.search(stmt) and BACKLOG_RE.search(stmt):
                    hits.append("{0}:{1}".format(os.path.relpath(path, root), number))
    return hits


def run():
    failures = 0
    for path in sorted(glob.glob(FIXTURES)):
        with open(path, encoding="utf-8") as fh:
            error = run_case(json.load(fh))
        if error:
            failures += 1
            print("::error::verify-board-backlog-edit: {0}: {1}".format(os.path.basename(path), error))
        else:
            print("[ok] {0}".format(os.path.basename(path)))
    for hit in single_home_violations(os.path.dirname(HERE)):
        failures += 1
        print("::error::verify-board-backlog-edit: {0} edits the backlog body outside board_backlog_edit.py (FR-024)".format(hit))
    return failures


def self_test():
    """A forced-write retry loop (ignoring verify) must fail the exhaustion case."""
    case = json.load(open(os.path.join(HERE, "tests", "board-backlog-edit", "concurrent-append.json"), encoding="utf-8"))
    original = bbe._operations

    def lax(op, line_id, detail):
        apply_fn, _verify = original(op, line_id, detail)
        return apply_fn, lambda _body: True

    bbe._operations = lax
    try:
        error = run_case(case)
    finally:
        bbe._operations = original
    if error is None:
        print("::error::verify-board-backlog-edit --self-test: a verify-less editor kept the concurrent writer's change")
        return 1
    return 0


def main(argv):
    if argv == ["--self-test"]:
        return self_test()
    if argv:
        sys.exit("takes --self-test or nothing.")
    failures = run()
    print("verify-board-backlog-edit: {0} failure(s).".format(failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
