#!/usr/bin/env python3
"""Gate — the records a session posts under the owner's account have one
writer, one reader and one form (wc_session_record.py).

Every kind builds to its fixed opening and parts and reads back as the
same record; a record with a part missing or malformed is refused, with
every problem named; a comment the command line cannot write is reported
on one line; and each document that tells a session to write a record
points at the script and quotes the opening the script writes.

    python3 .github/scripts/verify-session-record.py
    python3 .github/scripts/verify-session-record.py --self-test
"""
import contextlib
import glob
import io
import json
import os
import re
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import wc_session_record as wsr  # noqa: E402

FIXTURES = os.path.join(HERE, "tests", "session-record", "*.json")

# Each document that tells a session to write a record, and the command
# it has to name.
POINTERS = (
    ("CLAUDE.md", "decision"),
    (".claude/skills/review-until-clean/SKILL.md", "review"),
    (".claude/skills/prove-after-merge/SKILL.md", "proof"),
    (".claude/skills/answer-from-precedent/SKILL.md", "decision --by owner"),
)
# How a quoted opening of each kind starts and ends, whatever is between.
# A bare name (`**Session decision**`) is a mention, not an opening.
SHAPES = {
    "review": ("<!-- review-until-clean pass", "-->"),
    "proof": ("**Proof after merge", ":**"),
    "decision": ("**Session decision", ":**"),
    "owner-decision": ("**Owner decision", ":**"),
}
# The skill that tells a session's comment from the owner's by its
# attribution line; its jq test spells the pattern with doubled backslashes.
FOOTER_READER = ".claude/skills/answer-from-precedent/SKILL.md"


def _names(problems):
    return sorted(problem.split(":", 1)[0] for problem in problems)


def run_case(case):
    """None, or what is wrong with one fixture's outcome."""
    refused = case.get("expect_refused")
    try:
        if "build" in case:
            body = wsr.build(case["build"], case["fields"])
            again = wsr.read(body)
            if again != wsr.record(case["build"], case["fields"]):
                return "the built comment does not read back as the same record"
        else:
            body = None
            again = wsr.read("\n".join(case["read"]))
    except wsr.RecordError as error:
        if refused is None:
            return "refused: {0}".format(error)
        if _names(error.problems) != sorted(refused):
            return "refused for {0}, not {1}".format(_names(error.problems), sorted(refused))
        return None
    if refused is not None:
        return "accepted, but {0} should refuse it".format(sorted(refused))
    if "expect_body" in case and body != "\n".join(case["expect_body"]):
        return "built {0!r}".format(body)
    if case.get("expect_none") and again is not None:
        return "read as a {0} record".format(again["kind"])
    if "expect_record" in case and again != case["expect_record"]:
        return "read as {0!r}".format(again)
    return None


def quoted_openings(text):
    """(kind, span) for every backticked span shaped like an opening."""
    found = []
    for span in re.findall(r"`([^`\n]+)`", text):
        for kind, (start, end) in SHAPES.items():
            if span.startswith(start) and span.endswith(end):
                found.append((kind, span))
    return found


def pointer_problems(root):
    """Documents that do not point at the script for their kind, or that
    quote an opening the script does not write."""
    problems = []
    for relpath, command in POINTERS:
        with open(os.path.join(root, *relpath.split("/")), encoding="utf-8") as handle:
            text = handle.read()
        if "wc_session_record.py {0}".format(command) not in text:
            problems.append("{0}: does not point at `wc_session_record.py {1}`".format(relpath, command))
        for quoted_kind, span in quoted_openings(text):
            if span != wsr.OPENINGS[quoted_kind]:
                problems.append("{0}: quotes the opening `{1}`, and the script writes `{2}`".format(
                    relpath, span, wsr.OPENINGS[quoted_kind]))
        if relpath == FOOTER_READER and wsr.FOOTER_RE.pattern.replace("\\", "\\\\") not in text:
            problems.append("{0}: does not test for the attribution line with the script's "
                            "pattern, {1}".format(relpath, wsr.FOOTER_RE.pattern))
    return problems


def out_problems():
    """What the command line does wrong with a comment it cannot write.
    That is a file error like any other: one `wc_session_record:` line and
    exit 1, never a traceback."""
    root = tempfile.mkdtemp(prefix="session-record-")
    argv = ["decision", "--date", "2026-11-14", "--chosen", "c", "--options", "o",
            "--evidence", "e", "--undo", "u",
            "--out", os.path.join(root, "no-such-directory", "comment.md")]
    said = io.StringIO()
    try:
        with contextlib.redirect_stderr(said):
            code = wsr.main(argv)
    except OSError as error:
        return ["--out in a missing directory: raised {0}, where a file that cannot "
                "be read is reported on one line".format(type(error).__name__)]
    finally:
        shutil.rmtree(root, ignore_errors=True)
    lines = said.getvalue().splitlines()
    if code != 1 or len(lines) != 1 or not lines[0].startswith("wc_session_record: "):
        return ["--out in a missing directory: exit {0} and {1!r}, not exit 1 and one "
                "`wc_session_record:` line".format(code, said.getvalue())]
    return []


def run(root=ROOT):
    failures = 0
    paths = sorted(glob.glob(FIXTURES))
    if not paths:
        failures += 1
        print("::error::verify-session-record: no fixtures under tests/session-record/")
    for path in paths:
        with open(path, encoding="utf-8") as handle:
            error = run_case(json.load(handle))
        if error:
            failures += 1
            print("::error::verify-session-record: {0}: {1}".format(os.path.basename(path), error))
        else:
            print("[ok] {0}".format(os.path.basename(path)))
    for problem in pointer_problems(root) + out_problems():
        failures += 1
        print("::error::verify-session-record: {0}".format(problem))
    return failures


def _fixture_failures():
    count = 0
    for path in sorted(glob.glob(FIXTURES)):
        with open(path, encoding="utf-8") as handle:
            count += 1 if run_case(json.load(handle)) else 0
    return count


def _tree(edit):
    """A copy of the pointed-at documents with `edit(relpath, text)` applied."""
    root = tempfile.mkdtemp(prefix="session-record-")
    for relpath, _kind in POINTERS:
        with open(os.path.join(ROOT, *relpath.split("/")), encoding="utf-8") as handle:
            text = edit(relpath, handle.read())
        target = os.path.join(root, *relpath.split("/"))
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
    return root


def self_test():
    """Each mutation must make the gate fail; the shipped tree must not."""
    failures = []
    if _fixture_failures() or pointer_problems(ROOT):
        failures.append("the shipped tree does not pass, so no mutation can be judged")

    render = wsr.render
    wsr.render = lambda rec: "\n".join(
        row for row in render(rec).split("\n") if not row.startswith("**Review pass"))
    try:
        if not _fixture_failures():
            failures.append("a writer that drops the review verdict line passed every fixture")
    finally:
        wsr.render = render

    sha = wsr._sha
    wsr._sha = lambda name, value, problems: (value or "").strip()
    try:
        if not _fixture_failures():
            failures.append("a checker that takes any text for a commit SHA passed every fixture")
    finally:
        wsr._sha = sha

    drifted = wsr.OPENINGS["decision"].replace("(YYYY-MM-DD)", "of YYYY-MM-DD")
    mutations = (
        ("a document that quotes a drifted opening", "quotes the opening",
         lambda relpath, text: text.replace(wsr.OPENINGS["decision"], drifted)),
        ("a document that no longer points at the script", "does not point at",
         lambda relpath, text: text.replace("wc_session_record.py", "session_record.py")
         if relpath.endswith("prove-after-merge/SKILL.md") else text),
    )
    for what, phrase, edit in mutations:
        root = _tree(edit)
        try:
            if not any(phrase in problem for problem in pointer_problems(root)):
                failures.append("{0} passed".format(what))
        finally:
            shutil.rmtree(root, ignore_errors=True)

    for failure in failures:
        print("::error::verify-session-record --self-test: {0}".format(failure))
    return 1 if failures else 0


def main(argv):
    if argv == ["--self-test"]:
        return self_test()
    if argv:
        sys.exit("takes --self-test or nothing.")
    failures = run()
    print("verify-session-record: {0} failure(s).".format(failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
