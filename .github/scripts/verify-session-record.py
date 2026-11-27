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


# What a fixture says it expects. One with none of these would pass
# whatever the script does with it.
EXPECT_KEYS = ("expect_refused", "expect_body", "expect_none", "expect_record")


def run_case(case):
    """None, or what is wrong with one fixture's outcome."""
    if not any(key in case for key in EXPECT_KEYS):
        return "states none of {0}, so it would pass whatever the script does".format(
            ", ".join(EXPECT_KEYS))
    refused = case.get("expect_refused")
    try:
        if "build" in case:
            # The writer's own check first: a refusal raised by read() of a
            # comment build() wrote is the reader's, and a fixture that
            # expects a refusal must see the writer make it.
            rec = wsr.record(case["build"], case["fields"])
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
    if "build" in case:
        body = wsr.build(case["build"], case["fields"])
        try:
            again = wsr.read(body)
        except wsr.RecordError as error:
            return "the built comment reads back refused: {0}".format(error)
        if again != rec:
            return "the built comment does not read back as the same record"
    if "expect_body" in case and body != "\n".join(case["expect_body"]):
        return "built {0!r}".format(body)
    if case.get("expect_none") and again is not None:
        return "read as a {0} record".format(again["kind"])
    if "expect_record" in case and again != case["expect_record"]:
        return "read as {0!r}".format(again)
    return None


# One well-formed record of each kind OPENINGS names, and what its
# placeholders (N, YYYY-MM-DD) stand for in it.
_SHA = "0123456789abcdef0123456789abcdef01234567"
SAMPLES = {
    "review": ("review", {"pass": 3, "verdict": "clean", "started": _SHA,
                          "pushed": "nothing", "prose": "p"}),
    "proof": ("proof", {"outcome": "no-run", "date": "2026-11-14", "merge": _SHA, "why": "w"}),
    "decision": ("decision", {"date": "2026-11-14", "chosen": "c", "options": "o",
                              "evidence": "e", "undo": "u"}),
    "owner-decision": ("decision", {"by": "owner", "date": "2026-11-14", "chosen": "c",
                                    "question": "q"}),
}


def opening_problems():
    """Each OPENINGS entry, with its placeholders filled in, is how render()
    starts a record of that kind; a kind OPENINGS lacks or one it names
    that no sample builds is reported too."""
    problems = []
    if sorted(SAMPLES) != sorted(wsr.OPENINGS):
        problems.append("OPENINGS names {0}, and the gate builds {1}".format(
            sorted(wsr.OPENINGS), sorted(SAMPLES)))
    for name, (kind, fields) in sorted(SAMPLES.items()):
        if name not in wsr.OPENINGS:
            continue
        expected = wsr.OPENINGS[name].replace("YYYY-MM-DD", fields.get("date", "")).replace(
            " N ", " {0} ".format(fields.get("pass", "")))
        first = wsr.build(kind, fields).split("\n", 1)[0]
        if not (first == expected or first.startswith(expected + " ")):
            problems.append("OPENINGS[{0!r}] is `{1}`, and render() opens a {0} record "
                            "with `{2}`".format(name, wsr.OPENINGS[name], first))
    return problems


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


def edge_problems():
    """The small edges no fixture can hold (#889): the own-line refusal
    names the line; a date's year is read the same on every platform (a
    Windows-style strftime that pads the year must not let 0999 through);
    and the usage text says check takes none of --out, --footer, --date."""
    problems = []
    fields = dict(SAMPLES["decision"][1], evidence="e\n**Undo:** x")
    try:
        wsr.record("decision", fields)
        problems.append("a decision whose evidence holds an **Undo:** line was accepted")
    except wsr.RecordError as error:
        if not any("own lines" in p and "**Undo:** x" in p for p in error.problems):
            problems.append("the own-line refusal does not name the line: {0}".format(error.problems))
    import datetime as real

    class PaddedYear(real.datetime):
        def strftime(self, fmt):
            return super().strftime(fmt.replace("%Y", "{0:04d}".format(self.year)))

    saved = wsr.datetime
    wsr.datetime = type("datetime_shim", (), {"datetime": PaddedYear, "date": real.date,
                                              "timezone": real.timezone})
    try:
        for text, ok in (("0999-01-01", False), ("1000-01-01", True), ("2026-02-30", False),
                         ("2026-11-14", True), ("2026-1-14", False)):
            got = []
            wsr._date(text, got)
            if (not got) != ok:
                problems.append("date {0!r} under a year-padding strftime: {1}".format(
                    text, "accepted" if not got else "refused"))
    finally:
        wsr.datetime = saved
    doc = " ".join((wsr.__doc__ or "").split())
    if "Every kind but check also takes --out" not in doc or "Exit 2: not a record" not in doc:
        problems.append("the usage text no longer says check takes no --out, or its exit codes")
    return problems


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
    for problem in pointer_problems(root) + opening_problems() + out_problems() + edge_problems():
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
    if _fixture_failures() or pointer_problems(ROOT) or opening_problems():
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

    # A writer that leaves to the reader every refusal the reader also
    # makes: where read() of the comment it would write refuses for the
    # same parts, it writes that comment and refuses nothing itself.
    # Dropping all of a decision's checks instead is caught by fixtures
    # whose read-back refusal differs from the writer's, before #889 too,
    # so it would not show the writer's own refusal is what is checked.
    strict_record, strict_read = wsr.record, wsr.read

    def reader(body):
        wsr.record = strict_record
        try:
            return strict_read(body)
        finally:
            wsr.record = lax_record

    def lax_record(kind, fields):
        try:
            return strict_record(kind, fields)
        except wsr.RecordError as error:
            if kind not in wsr._KINDS:
                raise
            unchecked = wsr._KINDS[kind](fields, [])
            try:
                reader(wsr.render(unchecked))
            except wsr.RecordError as again:
                if _names(again.problems) == _names(error.problems):
                    return unchecked
            except (KeyError, TypeError, ValueError):
                pass
            raise

    wsr.record, wsr.read = lax_record, reader
    try:
        if not _fixture_failures():
            failures.append("a writer whose refusals only its reader makes passed every fixture")
    finally:
        wsr.record, wsr.read = strict_record, strict_read

    # The attribution pattern before #889: any marks and any link around
    # the phrase.
    footer_line = wsr.FOOTER_LINE_RE
    wsr.FOOTER_LINE_RE = re.compile(r"^[\W_]*" + wsr.FOOTER_RE.pattern + r"(?:\([^()\s]*\))?[\W_]*$")
    try:
        if not _fixture_failures():
            failures.append("an attribution pattern wider than the two real forms passed every fixture")
    finally:
        wsr.FOOTER_LINE_RE = footer_line

    kind, fields = SAMPLES["decision"]
    if run_case({"build": kind, "fields": fields}) is None:
        failures.append("a fixture that states no expectation passed")

    openings = wsr.OPENINGS
    wsr.OPENINGS = dict(openings, proof=openings["proof"].replace("after", "of"))
    try:
        if not opening_problems():
            failures.append("an OPENINGS entry render() does not write passed")
    finally:
        wsr.OPENINGS = openings

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
