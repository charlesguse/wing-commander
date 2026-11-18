#!/usr/bin/env python3
"""The one writer and reader of the records a Claude Code session posts
under the owner's account: a review pass report, a proof after merge and a
decision record.

Each kind has one opening line and a few named parts. build() writes them
in one fixed order and refuses a record with a part missing or malformed;
read() is the only parser of the same lines. This script never calls
GitHub: a session posts what it prints, with `gh` or its own GitHub tools.

A record written here is a session's claim. Nothing ties it to a run, so
code may list it and never counts it as evidence for a merge or any other
durable action.

Single file, standard library only, so a session on a branch that predates
it can run main's copy (the prefix stops Git Bash on Windows rewriting the
argument; bash on Linux or macOS ignores it, and PowerShell needs the
command without it):

    MSYS_NO_PATHCONV=1 git show origin/main:.github/scripts/wc_session_record.py > "$SCRATCH/wc_session_record.py"

Usage (every part is checked at once; a missing one is named and nothing
is written):

    wc_session_record.py review --pass N --verdict clean|not-clean \\
        --started SHA --pushed SHA|nothing --prose FILE
    wc_session_record.py proof --outcome proven|not-proven --merge SHA \\
        --run URL --ran-on SHA --step TEXT --line TEXT --not-exercised TEXT
    wc_session_record.py proof --outcome pending --merge SHA --due TEXT [--run URL]
    wc_session_record.py proof --outcome no-run --merge SHA --why TEXT
    wc_session_record.py decision --chosen TEXT --options TEXT \\
        --evidence TEXT --undo TEXT [--about N]
    wc_session_record.py decision --by owner --chosen TEXT --question TEXT [--about N]
    wc_session_record.py check FILE

Every kind also takes --out FILE (written as UTF-8 bytes with LF line
ends; without it the comment goes to stdout the same way) and --footer
TEXT, the session's attribution line when its posting tool does not add
one. proof and decision take --date YYYY-MM-DD (default: today, UTC), and
proof takes --prose FILE for anything past the fixed parts.

A TEXT value that starts with `@` is read from that file. Pass a log line
or any text with a backtick, a `$` or a quote that way, so the shell
expands nothing in it.

check prints the record a comment body holds as JSON. Exit 0: a well-formed
record. Exit 1: it opens like a record and a part is missing or malformed.
Exit 2: not a record.
"""
import argparse
import datetime
import json
import re
import sys

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
RUN_RE = re.compile(
    r"^https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/actions/runs/\d+(?:/job/\d+)?$")
# What tells a session's comment from one the owner typed.
FOOTER_RE = re.compile(r"Generated (by|with) \[Claude Code\]")
# A line that is that attribution and nothing else: the phrase, its link
# and the marks around them (an emoji, emphasis). A sentence that quotes
# the phrase is not one.
FOOTER_LINE_RE = re.compile(r"^[\W_]*" + FOOTER_RE.pattern + r"(?:\([^()\s]*\))?[\W_]*$")

# The opening each kind starts with, as a document quotes it.
# verify-session-record.py fails a document that quotes another.
OPENINGS = {
    "review": "<!-- review-until-clean pass N -->",
    "proof": "**Proof after merge (YYYY-MM-DD):**",
    "decision": "**Session decision (YYYY-MM-DD):**",
    "owner-decision": "**Owner decision (YYYY-MM-DD):**",
}
VERDICTS = {"clean": "CLEAN", "not-clean": "NOT CLEAN"}
OUTCOMES = {
    "proven": "proven",
    "not-proven": "not proven",
    "pending": "pending",
    "no-run": "no run reaches it",
}
RAN = ("proven", "not-proven")  # the outcomes that rest on a finished run

REVIEW_OPEN_RE = re.compile(r"^<!-- review-until-clean pass (\d+) -->$")
PROOF_OPEN_RE = re.compile(r"^\*\*Proof after merge \((\d{4}-\d{2}-\d{2})\):\*\* (.+)$")
DECISION_OPEN_RE = re.compile(r"^\*\*(Session|Owner) decision \((\d{4}-\d{2}-\d{2})\):\*\* (.+)$")
LABEL_RE = re.compile(r"^\*\*([^*\n]+?):\*\* ?(.*)$")
QUOTE_LEAD = "Quoted from the run:"
# A decision's parts by who made it: a session, or the owner in chat with
# a session writing it down.
DECISION_PARTS = {
    "session": (("Options considered", "options"), ("Evidence", "evidence"), ("Undo", "undo")),
    "owner": (("Question", "question"),),
}
# The last line of an owner's decision, so the comment says who wrote it.
OWNER_NOTE = "Decided in chat. Recorded by a Claude Code session."


class RecordError(ValueError):
    """A record with a part missing or malformed. `problems` names each."""

    def __init__(self, problems):
        ValueError.__init__(self, "; ".join(problems))
        self.problems = list(problems)


def _lf(text):
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _trim(text):
    """`text` with LF line ends, no leading blank lines and no trailing space."""
    lines = _lf(text).split("\n")
    while lines and not lines[0].strip():
        lines.pop(0)
    return "\n".join(lines).rstrip()


def _split_footer(text):
    """(text without its trailing attribution line, that line or None). A
    `---` rule directly above the line goes with it: a posting tool appends
    the two together. A rule with a blank line under it is the text's own
    and stays: render() puts a blank line above the footer, so read() takes
    off what build() put on and no more."""
    lines = _trim(text).split("\n")
    if not FOOTER_LINE_RE.match(lines[-1]):
        return "\n".join(lines), None
    footer = lines.pop().strip()
    if lines and lines[-1].strip() == "---":
        lines.pop()
    return "\n".join(lines).rstrip(), footer


def _line(name, value, problems):
    text = _lf(value or "").strip()
    if not text:
        problems.append("{0}: missing".format(name))
    elif "\n" in text:
        problems.append("{0}: must be one line".format(name))
    return text


def _sha(name, value, problems):
    text = (value or "").strip()
    if not text:
        problems.append("{0}: missing".format(name))
    elif not SHA_RE.match(text):
        problems.append("{0}: not a full 40-character commit SHA (git rev-parse expands a short one)".format(name))
    return text


def _date(value, problems):
    text = (value or "").strip()
    try:
        if datetime.datetime.strptime(text, "%Y-%m-%d").strftime("%Y-%m-%d") != text:
            raise ValueError(text)
    except ValueError:
        problems.append("date: not YYYY-MM-DD")
    return text


def _run(value, problems, required):
    text = (value or "").strip()
    if not text:
        if required:
            problems.append("run: missing")
        return None
    if not RUN_RE.match(text):
        problems.append("run: not an Actions run URL (https://github.com/OWNER/NAME/actions/runs/ID)")
    return text


def _absent(fields, names, why, problems):
    for name in names:
        if (fields.get(name) or "").strip():
            problems.append("{0}: {1}".format(name.replace("_", "-"), why))


def _footer(fields, text, problems):
    """(text, footer): the footer the caller gave, else the attribution
    line `text` ends with, taken off it."""
    given = _lf(fields.get("footer") or "").strip()
    if not given:
        return _split_footer(text)
    if "\n" in given or not FOOTER_LINE_RE.match(given):
        problems.append("footer: not a one-line Claude Code attribution")
    return _trim(text), given


def _review(fields, problems):
    number = fields.get("pass")
    if isinstance(number, bool) or not isinstance(number, int) or number < 1:
        problems.append("pass: missing or not a whole number from 1")
    verdict = fields.get("verdict")
    if verdict not in VERDICTS:
        problems.append("verdict: missing or not one of {0}".format(", ".join(sorted(VERDICTS))))
    started = _sha("started", fields.get("started"), problems)
    pushed = (fields.get("pushed") or "").strip()
    if pushed == "nothing":
        pushed = None
    elif not pushed:
        problems.append("pushed: missing (a commit SHA, or the word nothing)")
    else:
        pushed = _sha("pushed", pushed, problems)
        if pushed == started:
            problems.append("pushed: equals started (say nothing when the pass pushed no commit)")
    prose, footer = _footer(fields, fields.get("prose") or "", problems)
    if not prose:
        problems.append("prose: missing (the report itself)")
    return {"kind": "review", "pass": number, "verdict": verdict, "started": started,
            "pushed": pushed, "prose": prose, "footer": footer}


def _proof(fields, problems):
    outcome = fields.get("outcome")
    if outcome not in OUTCOMES:
        problems.append("outcome: missing or not one of {0}".format(", ".join(sorted(OUTCOMES))))
    rec = {"kind": "proof", "date": _date(fields.get("date"), problems), "outcome": outcome,
           "merge": _sha("merge", fields.get("merge"), problems),
           "run": None, "ran_on": None, "step": None, "line": None,
           "not_exercised": None, "due": None, "why": None}
    if outcome in RAN:
        rec["run"] = _run(fields.get("run"), problems, True)
        rec["ran_on"] = _sha("ran-on", fields.get("ran_on"), problems)
        rec["step"] = _line("step", fields.get("step"), problems)
        rec["not_exercised"] = _line("not-exercised", fields.get("not_exercised"), problems)
        rec["line"] = _lf(fields.get("line") or "").strip("\n")
        if not rec["line"].strip():
            problems.append("line: missing (the log line the run printed, quoted)")
        _absent(fields, ("due", "why"), "only a pending or no-run proof has one", problems)
    elif outcome == "pending":
        rec["due"] = _line("due", fields.get("due"), problems)
        rec["run"] = _run(fields.get("run"), problems, False)
        _absent(fields, ("ran_on", "step", "line", "not_exercised", "why"),
                "a pending proof has no result yet", problems)
    elif outcome == "no-run":
        rec["why"] = _line("why", fields.get("why"), problems)
        _absent(fields, ("run", "ran_on", "step", "line", "not_exercised", "due"),
                "no run reaches the change", problems)
    rec["prose"], rec["footer"] = _footer(fields, fields.get("prose") or "", problems)
    return rec


def _decision(fields, problems):
    by = fields.get("by") or "session"
    if by not in DECISION_PARTS:
        problems.append("by: not one of {0}".format(", ".join(sorted(DECISION_PARTS))))
        by = "session"
    rec = {"kind": "decision", "by": by, "date": _date(fields.get("date"), problems),
           "chosen": _line("chosen", fields.get("chosen"), problems), "about": None}
    about = fields.get("about")
    if about is not None:
        if isinstance(about, bool) or not isinstance(about, int) or about < 1:
            problems.append("about: not an issue or pull request number")
        rec["about"] = about
    labels = tuple("**{0}:**".format(label) for label, _key in DECISION_PARTS[by])
    texts = dict((key, _lf(fields.get(key) or "").strip()) for _label, key in DECISION_PARTS[by])
    # A session decision's last part runs to the end of the comment when it
    # has more than one line (render() starts it under its label), so an
    # attribution line it ends with is the comment's footer, as with a
    # report's prose: read() takes it as that. One line sits on its label's
    # line, which read() never takes for a footer, and an owner's decision
    # ends with OWNER_NOTE.
    last = DECISION_PARTS[by][-1][1]
    if by == "session" and "\n" in texts[last]:
        texts[last], rec["footer"] = _footer(fields, texts[last], problems)
    else:
        _none, rec["footer"] = _footer(fields, "", problems)
    for label, key in DECISION_PARTS[by]:
        text = texts[key]
        if not text:
            problems.append("{0}: missing".format(key))
        elif any(row.startswith(labels) or row.strip() == OWNER_NOTE for row in text.split("\n")):
            problems.append("{0}: a line is one of the record's own lines".format(key))
        rec[key] = text
    for other, parts in sorted(DECISION_PARTS.items()):
        if other != by:
            _absent(fields, [key for _label, key in parts],
                    "not a part of a decision by the {0}".format(by), problems)
    return rec


_KINDS = {"review": _review, "proof": _proof, "decision": _decision}


def record(kind, fields):
    """`fields` checked and put in one shape. Raises RecordError naming
    every part that is missing or malformed."""
    if kind not in _KINDS:
        raise RecordError(["kind: not one of {0}".format(", ".join(sorted(_KINDS)))])
    problems = []
    rec = _KINDS[kind](fields, problems)
    if problems:
        raise RecordError(problems)
    return rec


def _fence(text):
    longest = max([len(run) for run in re.findall(r"`+", text)] or [0])
    return "`" * max(3, longest + 1)


def render(rec):
    """The comment body for a record() result."""
    kind = rec["kind"]
    if kind == "review":
        out = ["<!-- review-until-clean pass {0} -->".format(rec["pass"]),
               "**Review pass {0}:** {1}".format(rec["pass"], VERDICTS[rec["verdict"]]),
               "**Started from:** `{0}`".format(rec["started"]),
               "**Pushed:** " + ("`{0}`".format(rec["pushed"]) if rec["pushed"] else "nothing"),
               "", rec["prose"]]
    elif kind == "proof":
        out = ["**Proof after merge ({0}):** {1}".format(rec["date"], OUTCOMES[rec["outcome"]]),
               "**Merge:** `{0}`".format(rec["merge"])]
        if rec["outcome"] in RAN:
            fence = _fence(rec["line"])
            out += ["**Run:** " + rec["run"],
                    "**Ran on:** `{0}`".format(rec["ran_on"]),
                    "**Step:** " + rec["step"],
                    "**Not exercised:** " + rec["not_exercised"],
                    "", QUOTE_LEAD, "", fence + "text", rec["line"], fence]
        elif rec["outcome"] == "pending":
            out.append("**Due:** " + rec["due"])
            if rec["run"]:
                out.append("**Run:** " + rec["run"])
        else:
            out.append("**Why:** " + rec["why"])
        if rec["prose"]:
            out += ["", rec["prose"]]
    else:
        out = ["**{0} decision ({1}):** {2}".format(
            rec["by"].capitalize(), rec["date"], rec["chosen"])]
        if rec["about"]:
            out.append("**About:** #{0}".format(rec["about"]))
        for label, key in DECISION_PARTS[rec["by"]]:
            # A part of several lines starts under its label, so a list in it renders.
            out += ["", "**{0}:**{1}{2}".format(label, "\n" if "\n" in rec[key] else " ", rec[key])]
        if rec["by"] == "owner":
            out += ["", OWNER_NOTE]
    if rec["footer"]:
        out += ["", rec["footer"]]
    return "\n".join(out)


def build(kind, fields):
    """The comment body for a record of `kind`, or RecordError."""
    return render(record(kind, fields))


def _header(lines, start):
    """The `**Label:** value` lines from `start` to the first other line."""
    pairs, at = [], start
    while at < len(lines):
        match = LABEL_RE.match(lines[at])
        if not match:
            break
        pairs.append((match.group(1), match.group(2).strip()))
        at += 1
    return pairs, at


def _ticked(value):
    return value[1:-1] if len(value) > 1 and value.startswith("`") and value.endswith("`") else value


def _expect(pairs, labels, what):
    got = [label for label, _value in pairs]
    if got != list(labels):
        raise RecordError(["{0}: the lines after the opening are {1}, not {2}".format(
            what, ", ".join(got) or "none", ", ".join(labels))])
    return [value for _label, value in pairs]


def _rest(lines, at):
    while at < len(lines) and not lines[at].strip():
        at += 1
    return "\n".join(lines[at:]).rstrip()


def _read_review(lines, footer):
    match = REVIEW_OPEN_RE.match(lines[0])
    if not match:
        raise RecordError(["review: the opening is not `{0}`".format(OPENINGS["review"])])
    number = int(match.group(1))
    pairs, at = _header(lines, 1)
    verdict, started, pushed = _expect(
        pairs, ("Review pass {0}".format(number), "Started from", "Pushed"), "review")
    verdicts = dict((word, key) for key, word in VERDICTS.items())
    return {"pass": number, "verdict": verdicts.get(verdict), "started": _ticked(started),
            "pushed": _ticked(pushed), "prose": _rest(lines, at), "footer": footer}


def _read_proof(lines, footer):
    match = PROOF_OPEN_RE.match(lines[0])
    if not match:
        raise RecordError(["proof: the opening is not `{0}` and an outcome".format(OPENINGS["proof"])])
    outcomes = dict((word, key) for key, word in OUTCOMES.items())
    fields = {"date": match.group(1), "outcome": outcomes.get(match.group(2).strip()), "footer": footer}
    if not fields["outcome"]:
        raise RecordError(["proof: the outcome is not one of {0}".format(", ".join(sorted(outcomes)))])
    pairs, at = _header(lines, 1)
    if fields["outcome"] in RAN:
        merge, run, ran_on, step, not_exercised = _expect(
            pairs, ("Merge", "Run", "Ran on", "Step", "Not exercised"), "proof")
        fields.update(run=run, ran_on=_ticked(ran_on), step=step, not_exercised=not_exercised)
        while at < len(lines) and not lines[at].strip():
            at += 1
        block = lines[at:at + 3]
        opener = re.match(r"^(`{3,})text$", block[2]) if len(block) == 3 else None
        if not opener or block[0] != QUOTE_LEAD or block[1].strip():
            raise RecordError(["proof: no quoted line from the run"])
        try:
            close = lines.index(opener.group(1), at + 3)
        except ValueError:
            raise RecordError(["proof: the quoted line's code fence never closes"])
        fields["line"] = "\n".join(lines[at + 3:close])
        at = close + 1
    elif fields["outcome"] == "pending":
        labels = ("Merge", "Due", "Run") if len(pairs) == 3 else ("Merge", "Due")
        values = _expect(pairs, labels, "proof")
        merge = values[0]
        fields.update(due=values[1], run=values[2] if len(values) == 3 else None)
    else:
        merge, why = _expect(pairs, ("Merge", "Why"), "proof")
        fields["why"] = why
    fields.update(merge=_ticked(merge), prose=_rest(lines, at))
    return fields


def _read_decision(lines, footer):
    match = DECISION_OPEN_RE.match(lines[0])
    if not match:
        raise RecordError(["decision: the opening is not `{0}` or `{1}`, then what was chosen".format(
            OPENINGS["decision"], OPENINGS["owner-decision"])])
    by = match.group(1).lower()
    fields = {"by": by, "date": match.group(2), "chosen": match.group(3).strip(), "footer": footer}
    if by == "owner":
        if lines[-1].strip() != OWNER_NOTE:
            raise RecordError(["decision: the last line is not `{0}`".format(OWNER_NOTE)])
        lines = lines[:-1]
    pairs, at = _header(lines, 1)
    if pairs:
        (about,) = _expect(pairs, ("About",), "decision")
        fields["about"] = int(about[1:]) if re.match(r"^#\d+$", about) else 0
    rows = lines[at:]
    starts = []
    for label, _key in DECISION_PARTS[by]:
        hits = [i for i, row in enumerate(rows) if row.startswith("**{0}:**".format(label))]
        if len(hits) > 1:
            raise RecordError(["decision: `**{0}:**` starts more than one line".format(label)])
        starts.append(hits[0] if hits else None)
    present = [start for start in starts if start is not None]
    if present != sorted(present):
        raise RecordError(["decision: the parts are out of order"])
    if present and any(row.strip() for row in rows[:present[0]]):
        raise RecordError(["decision: text between the opening and the first part"])
    for index, (label, key) in enumerate(DECISION_PARTS[by]):
        if starts[index] is None:
            continue
        later = [start for start in starts[index + 1:] if start is not None]
        part = rows[starts[index]:later[0] if later else len(rows)]
        part[0] = part[0][len("**{0}:**".format(label)):]
        fields[key] = "\n".join(part).strip()
    return fields


_READERS = (("<!-- review-until-clean pass", "review", _read_review),
            ("**Proof after merge", "proof", _read_proof),
            ("**Session decision", "decision", _read_decision),
            ("**Owner decision", "decision", _read_decision))


def read(body):
    """The record a comment body holds, in record()'s shape, or None when
    the body does not open like one. Raises RecordError when it opens like
    a record and a part is missing or malformed."""
    text, footer = _split_footer(body or "")
    lines = text.split("\n")
    for prefix, kind, reader in _READERS:
        if lines[0].startswith(prefix):
            return record(kind, reader(lines, footer))
    return None


def _text(value):
    """A flag's value; `@path` reads that file."""
    if value is None or not value.startswith("@"):
        return value
    with open(value[1:], encoding="utf-8-sig") as handle:
        return handle.read()


def _args(argv):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    kinds = parser.add_subparsers(dest="kind")

    def kind(name, with_date):
        sub = kinds.add_parser(name)
        sub.add_argument("--out", metavar="FILE")
        sub.add_argument("--footer", metavar="TEXT")
        if with_date:
            sub.add_argument("--date", metavar="YYYY-MM-DD")
        return sub

    review = kind("review", False)
    review.add_argument("--pass", dest="pass_", type=int, metavar="N")
    review.add_argument("--verdict")
    review.add_argument("--started", metavar="SHA")
    review.add_argument("--pushed", metavar="SHA|nothing")
    review.add_argument("--prose", metavar="FILE")

    proof = kind("proof", True)
    proof.add_argument("--outcome")
    proof.add_argument("--merge", metavar="SHA")
    proof.add_argument("--run", metavar="URL")
    proof.add_argument("--ran-on", metavar="SHA")
    for flag in ("--step", "--line", "--not-exercised", "--due", "--why"):
        proof.add_argument(flag, metavar="TEXT")
    proof.add_argument("--prose", metavar="FILE")

    decision = kind("decision", True)
    decision.add_argument("--by", metavar="session|owner")
    decision.add_argument("--about", type=int, metavar="N")
    for flag in ("--chosen", "--options", "--evidence", "--undo", "--question"):
        decision.add_argument(flag, metavar="TEXT")

    check = kinds.add_parser("check")
    check.add_argument("file", metavar="FILE", help="a comment body, or - for stdin")
    args = parser.parse_args(argv)
    if not args.kind:
        parser.error("name a kind: review, proof, decision or check")
    return args


def _fields(args):
    fields = dict((key, _text(value) if isinstance(value, str) else value)
                  for key, value in vars(args).items() if key not in ("kind", "out", "prose"))
    if "pass_" in fields:
        fields["pass"] = fields.pop("pass_")
    if "date" in fields and not fields["date"]:
        fields["date"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    if getattr(args, "prose", None):
        fields["prose"] = _text("@" + args.prose)
    return fields


def main(argv=None):
    args = _args(sys.argv[1:] if argv is None else argv)
    try:
        if args.kind == "check":
            if args.file == "-":
                raw = sys.stdin.buffer.read()
            else:
                with open(args.file, "rb") as handle:
                    raw = handle.read()
            rec = read(raw.decode("utf-8-sig"))
            if rec is None:
                print("wc_session_record: not a session record", file=sys.stderr)
                return 2
            data = json.dumps(rec, indent=2, sort_keys=True)
        else:
            data = build(args.kind, _fields(args))
        # Written inside the try, so a file that cannot be written is
        # reported like one that cannot be read.
        payload = (data + "\n").encode("utf-8")
        out = getattr(args, "out", None)
        if out:
            with open(out, "wb") as handle:
                handle.write(payload)
        else:
            sys.stdout.buffer.write(payload)
    except RecordError as error:
        for problem in error.problems:
            print("wc_session_record: {0}".format(problem), file=sys.stderr)
        return 1
    except (OSError, UnicodeDecodeError) as error:
        print("wc_session_record: {0}".format(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
