#!/usr/bin/env python3
"""Gate 28 - no `gh api` read is turned into a write by a field flag.

THE DEFECT THIS EXISTS FOR
--------------------------
`gh api` defaults to GET, but only until it is given a body. The moment any
of `-f`/`-F`/`--field`/`--raw-field`/`--input` appears without an explicit
`-X`/`--method`, gh switches the request to POST. Nothing in the command
says so, and nothing in the output says so either: the call reads exactly
like a parameterised GET, and the failure surfaces one step later as
whatever the POST endpoint happened to answer.

pr-conversation.yml resolved the lifecycle issue number with

  (wc-gh-method-exempt: the next line quotes the defect, it is not a call)
    gh api "repos/$R/contents/$SPEC_DIR/spec-meta.json" -f ref="$SPEC_BRANCH" ...

which is a create-a-file request against the contents API. Measured in run
32671719013 (2026-08-23): `gh: Not Found (HTTP 404)`, then `base64: invalid
input`, then the step's own `::error::cannot resolve the lifecycle issue
number`. The stage had therefore never resolved a lifecycle issue in
production - every maintainer review or comment on an implementation PR
died there, before classification. It could not be caught by dogfooding
before it merged, because GitHub only dispatches review events from
default-branch workflow files (specs/033).

WHY THE RULE IS "EXPLICIT METHOD", NOT "NO FIELDS ON A READ"
------------------------------------------------------------
A checker cannot know from the call site whether the author meant a POST.
It can know whether the author SAID so. So the rule is strict and
mechanical: a `gh api` invocation carrying a field flag must also carry
`-X`/`--method`. A genuine POST costs one `-X POST` to say out loud, and a
reader of the diff then sees a write where a write is happening. That is
the only form in which "this is a POST" is checkable at all.

The escape hatch is a same-line or immediately-preceding
`# wc-gh-method-exempt: <reason>` comment, and a bare marker with no reason
does not count - same shape as Gate 18's.

SCOPE
-----
Every `.github/workflows/*.yml|yaml`, every `.github/actions/**/action.yml|yaml`,
and every checked-in script under `.github/scripts/`. Raw lines, not just
parsed `run:` blocks: a composite action's `if:` expression, a heredoc body
and a documentation string can all carry a shipped invocation, and the point
of a class check is that the class cannot land anywhere in the tree.

Usage:
    python3 .github/scripts/verify-gh-api-explicit-method.py
    python3 .github/scripts/verify-gh-api-explicit-method.py --self-test
"""
import argparse
import glob
import os
import re
import sys

# --------------------------------------------------------------- detection

# `gh api` as an actual command word. The lookbehind keeps `foogh api` out;
# requiring whitespace (or end of line) after `api` keeps the allow-list
# spelling `Bash(gh api:*)` out, which appears in every agent step's
# --allowedTools string and is a grant, not an invocation.
GH_API_RE = re.compile(r"(?<![\w./-])gh\s+api(?=\s|$)")

# One alternative per flag gh treats as a body. Written as a tuple rather
# than one blob so that removing any single alternative is a one-line
# mutation the self-test can perform - and must kill (see MUTATIONS).
#
#   -f/-F         cobra shorthands, value attached (`-fref=main`) or not
#   --field       typed field
#   --raw-field   string field
#   --input       request body from a file or stdin
FIELD_FLAG_ALTERNATIVES = (
    r"-[fF](?:=?\S*)?",
    r"--field(?:=.*)?",
    r"--raw-field(?:=.*)?",
    r"--input(?:=.*)?",
)

# `-X`/`-XGET`/`--method GET`/`--method=GET`.
METHOD_FLAG_ALTERNATIVES = (
    r"-X\S*",
    r"--method(?:=.*)?",
)

EXEMPT_RE = re.compile(r"wc-gh-method-exempt:\s*\S")

# Tokens that end a simple command, so a field flag belonging to some other
# command in a pipeline is never blamed on `gh api`.
TERMINATORS = set("|;&<>)`")


def _flag_re(alternatives):
    return re.compile("^(?:" + "|".join(alternatives) + ")$")


class Detector(object):
    """The rule, with every knob the self-test's mutations turn.

    Production always uses the default instance. The knobs exist so that a
    mutation is a change to THIS object rather than a second, edited copy of
    the detector that could drift from the one that ships.
    """

    def __init__(self, field_alternatives=FIELD_FLAG_ALTERNATIVES,
                 method_alternatives=METHOD_FLAG_ALTERNATIVES,
                 join_continuations=True, quote_aware=True):
        self.field_re = _flag_re(field_alternatives)
        self.method_re = _flag_re(method_alternatives)
        self.join_continuations = join_continuations
        self.quote_aware = quote_aware

    # -- tokenising ------------------------------------------------------

    def _args(self, text):
        """[(token, started_unquoted)] for the command beginning at text[0].

        Quote-aware because a `--jq` filter routinely contains a `|`
        (`--jq '.[] | .name'`), and a scanner that stopped at the first `|`
        it saw would stop reading a real invocation halfway through and miss
        every flag after the filter.
        """
        if not self.quote_aware:
            head = text.split("|")[0]
            return [(tok, True) for tok in head.split()]
        args = []
        tok = []
        started = False
        unquoted = False
        quote = None
        i, n = 0, len(text)
        while i < n:
            c = text[i]
            if quote:
                if c == quote:
                    quote = None
                elif quote == '"' and c == "\\" and i + 1 < n:
                    tok.append(text[i + 1])
                    i += 2
                    continue
                else:
                    tok.append(c)
                i += 1
                continue
            if c in "'\"":
                if not started:
                    started, unquoted = True, False
                quote = c
                i += 1
                continue
            if c == "\\" and i + 1 < n:
                if not started:
                    started, unquoted = True, False
                tok.append(text[i + 1])
                i += 2
                continue
            if c.isspace():
                if started:
                    args.append(("".join(tok), unquoted))
                    tok, started, unquoted = [], False, False
                i += 1
                continue
            if c in TERMINATORS:
                break
            if not started:
                started, unquoted = True, True
            tok.append(c)
            i += 1
        if started:
            args.append(("".join(tok), unquoted))
        return args

    # -- the rule --------------------------------------------------------

    def offenders(self, logical_line):
        """The `gh api` invocations on this line that ship an unstated method.

        Returns the offending flag for each, so the error can quote it.
        """
        found = []
        for m in GH_API_RE.finditer(logical_line):
            args = self._args(logical_line[m.end():])
            field = None
            method = False
            for token, started_unquoted in args:
                if not started_unquoted:
                    continue        # a quoted string is data, not a flag
                if self.method_re.match(token):
                    method = True
                elif field is None and self.field_re.match(token):
                    field = token
            if field is not None and not method:
                found.append(field)
        return found

    # -- file sweep ------------------------------------------------------

    def logical_lines(self, lines):
        """(joined line, index of its first physical line).

        A `\\`-continued invocation is one command, and a per-physical-line
        scanner sees neither half of it: the first line has the `gh api` and
        no flags, the second has the flags and no `gh api`. Both halves read
        clean while the command they form does not.
        """
        i, n = 0, len(lines)
        while i < n:
            first = i
            parts = [lines[i]]
            while (self.join_continuations
                   and parts[-1].rstrip().endswith("\\") and i + 1 < n):
                i += 1
                parts.append(lines[i])
            yield " ".join(p.rstrip().rstrip("\\").rstrip()
                           for p in parts), first
            i += 1

    def scan_text(self, path, text):
        """Every failure line for one file's contents."""
        lines = text.splitlines()
        failures = []
        for line, idx in self.logical_lines(lines):
            for flag in self.offenders(line):
                if _is_exempt(lines, idx):
                    continue
                failures.append(
                    "::error file={0},line={1}::Gate 28: this `gh api` call "
                    "passes `{2}` with no `-X`/`--method`, which makes it a "
                    "POST whether or not that was meant - gh switches method "
                    "the moment it is given a body. If it is a read, write "
                    "`-X GET` (or move the parameter into the path as a query "
                    "string); if it is a write, say `-X POST` out loud. An "
                    "intentional exception needs a same-line or "
                    "immediately-preceding `# wc-gh-method-exempt: <reason>` "
                    "comment.".format(path, idx + 1, flag))
        return failures


def _is_exempt(lines, idx):
    for i in (idx, idx - 1):
        if 0 <= i < len(lines) and EXEMPT_RE.search(lines[i]):
            return True
    return False


def posix(path):
    """Repo-relative with forward slashes, whatever glob returned.

    Windows glob emits the platform separator for the components it expands,
    and a maintainer's local run printing `.github\\actions\\x\\action.yml`
    where CI prints the POSIX form means `::error file=` resolves in one and
    not the other, for the same defect.
    """
    return path.replace(os.sep, "/")


LINT_WORKFLOW = ".github/workflows/lint-workflows.yml"


def subject_files():
    paths = (glob.glob(".github/workflows/*.yml")
             + glob.glob(".github/workflows/*.yaml")
             + glob.glob(".github/actions/**/action.yml", recursive=True)
             + glob.glob(".github/actions/**/action.yaml", recursive=True)
             + glob.glob(".github/scripts/**/*.sh", recursive=True)
             + glob.glob(".github/scripts/**/*.py", recursive=True))
    return sorted(set(posix(p) for p in paths))


def sweep():
    # Every glob above is relative, because `::error file=` only resolves
    # against repo-relative paths. That makes the working directory
    # load-bearing, and a load-bearing assumption that is not asserted is how
    # a gate ends up reporting "0 failure(s)" having opened nothing (#213).
    if not os.path.isfile(LINT_WORKFLOW):
        sys.exit("::error::run this from the repository root; {0} not "
                 "found.".format(LINT_WORKFLOW))
    detector = Detector()
    files = subject_files()
    if not files:
        sys.exit("::error::Gate 28 matched no workflows, composite actions or "
                 "scripts at all. That is a broken sweep, not a clean tree.")
    failures = []
    for path in files:
        with open(path, encoding="utf-8") as fh:
            failures.extend(detector.scan_text(path, fh.read()))
    for f in failures:
        print(f)
    print("Gate 28: scanned {0} workflow/action/script file(s) for `gh api` "
          "calls that pass a field with no explicit method; {1} "
          "failure(s).".format(len(files), len(failures)))
    return 1 if failures else 0


# --------------------------------------------------------------- self-test
#
# Fixtures are literal command text rather than mutations of the real tree:
# the real files change for unrelated reasons, and a self-test that breaks on
# every unrelated edit gets deleted rather than fixed.
#
# Every fixture line below that would itself trip the sweep carries the
# exemption marker, because this file is inside the sweep's own scope. A gate
# that excluded itself would be the one file in the tree where the defect
# could land.

SHIPPED_DEFECT = (  # wc-gh-method-exempt: the measured defect, quoted as a self-test fixture
    'issue=$(gh api "repos/$GITHUB_REPOSITORY/contents/$SPEC_DIR/spec-meta.json"'
    ' -f ref="$SPEC_BRANCH" --jq \'.content\' | base64 -d | jq -r \'.issue\')')

SHIPPED_FIX = (
    'issue=$(gh api -X GET'
    ' "repos/$GITHUB_REPOSITORY/contents/$SPEC_DIR/spec-meta.json"'
    ' -f ref="$SPEC_BRANCH" --jq \'.content\' | base64 -d | jq -r \'.issue\')')

CONTINUED_RED = [
    'gh api "repos/$GITHUB_REPOSITORY/contents/$SPEC_DIR/spec-meta.json" \\',
    '  -f ref="$SPEC_BRANCH" \\',  # wc-gh-method-exempt: continuation half of a self-test fixture
    "  --jq '.content'",
]

CONTINUED_GREEN = [
    'gh api -X GET \\',
    '  "repos/$GITHUB_REPOSITORY/contents/$SPEC_DIR/spec-meta.json" \\',
    '  -f ref="$SPEC_BRANCH" \\',  # wc-gh-method-exempt: continuation half of a self-test fixture
    "  --jq '.content'",
]

# name, text, expect_fail, must_mention
CASES = [
    ("the measured defect: a contents read with -f and no method",
     SHIPPED_DEFECT, True, ("-f",)),

    ("the fix: the same read with -X GET",
     SHIPPED_FIX, False, ()),

    ("an intentional write that says so: -X POST with -f",
     'gh api -X POST "repos/$R/issues/$N/labels" -f labels[]=bug',
     False, ()),

    ("-X PATCH with -f (the shipped comment edit)",
     'gh api -X PATCH "$edit_path" -f body="$new_body" >/dev/null 2>&1 || true',
     False, ()),

    ("a method with its value attached: -XGET",
     'gh api -XGET "repos/$R/contents/x" -f ref=main',
     False, ()),

    ("a long method flag with =: --method=GET",
     'gh api --method=GET "repos/$R/contents/x" --field ref=main',
     False, ()),

    ("a long method flag with a separate value: --method GET",
     'gh api --method GET "repos/$R/contents/x" --raw-field ref=main',
     False, ()),

    ("--field with no method",  # wc-gh-method-exempt: self-test fixture text
     'gh api "repos/$R/contents/x" --field ref=main',
     True, ("--field",)),

    ("--raw-field with no method",  # wc-gh-method-exempt: self-test fixture text
     'gh api "repos/$R/contents/x" --raw-field ref=main',
     True, ("--raw-field",)),

    ("--input with no method",  # wc-gh-method-exempt: self-test fixture text
     'gh api "repos/$R/issues" --input payload.json',
     True, ("--input",)),

    ("-F with no method",  # wc-gh-method-exempt: self-test fixture text
     'gh api "repos/$R/issues" -F number=@number.txt',
     True, ("-F",)),

    ("a field value attached to the shorthand: -fref=main",  # wc-gh-method-exempt: self-test fixture text
     'gh api "repos/$R/contents/x" -fref=main',
     True, ("-fref=main",)),

    ("a multi-line \\-continued call is one command: method missing",
     "\n".join(CONTINUED_RED), True, ("-f",)),

    ("the same multi-line call with -X GET on the first line",
     "\n".join(CONTINUED_GREEN), False, ()),

    ("no false positive: a plain read with no field at all",
     'gh api "repos/$R/contents/.github/workflows?ref=$BRANCH" --jq \'.[].path\'',
     False, ()),

    ("no false positive: --paginate read, filter carries a | inside quotes",
     'gh api "repos/$R/issues/$N/comments" --paginate '
     '--jq \'.[] | {id, body}\' | jq -s \'.\'',
     False, ()),

    ("a field AFTER a quoted filter containing | is still seen",  # wc-gh-method-exempt: self-test fixture text
     'gh api "repos/$R/x" --jq \'.a | .b\' -f ref=main',
     True, ("-f",)),

    ("no false positive: a field flag belongs to the next command in the pipe",
     "gh api \"repos/$R/x\" --jq '.[].name' | grep -f patterns.txt",
     False, ()),

    ("no false positive: the allow-list grant Bash(gh api:*)",
     '--allowedTools "Read,Grep,Bash(gh api:*),Bash(grep -f:*)"',
     False, ()),

    ("no false positive: an exempted call that states its reason",  # wc-gh-method-exempt: self-test fixture text
     'gh api "repos/$R/x" -f ref=main  '
     '# wc-gh-method-exempt: gh is deliberately POSTing here',
     False, ()),

    ("a bare exemption marker with no reason does not count",  # wc-gh-method-exempt: self-test fixture text
     'gh api "repos/$R/x" -f ref=main  # wc-gh-method-exempt',
     True, ("-f",)),
]

# A mutation must break at least one fixture. A mutation that changes the
# shipped behaviour and breaks nothing means the fixture set is not holding
# the detector to that behaviour - the failure branch would be free to rot.
MUTATIONS = [
    ("drop the -f/-F alternative from the field-flag regex",
     Detector(field_alternatives=FIELD_FLAG_ALTERNATIVES[1:])),
    ("drop the --field alternative",
     Detector(field_alternatives=(FIELD_FLAG_ALTERNATIVES[0],)
              + FIELD_FLAG_ALTERNATIVES[2:])),
    ("drop the --raw-field alternative",
     Detector(field_alternatives=FIELD_FLAG_ALTERNATIVES[:2]
              + FIELD_FLAG_ALTERNATIVES[3:])),
    ("drop the --input alternative",
     Detector(field_alternatives=FIELD_FLAG_ALTERNATIVES[:3])),
    ("drop the --method alternative from the method regex",
     Detector(method_alternatives=METHOD_FLAG_ALTERNATIVES[:1])),
    ("drop the -X alternative from the method regex",
     Detector(method_alternatives=METHOD_FLAG_ALTERNATIVES[1:])),
    ("stop joining \\-continued lines",
     Detector(join_continuations=False)),
    ("stop tracking quotes when reading the argument list",
     Detector(quote_aware=False)),
]


def _verdicts(detector):
    """(fired, output) per fixture, under the given detector."""
    out = []
    for name, text, _, _ in CASES:
        failures = detector.scan_text("fixture.sh", text)
        out.append((bool(failures), "\n".join(failures)))
    return out


def self_test():
    baseline = _verdicts(Detector())
    problems = []

    for (name, _text, expect_fail, must_mention), (fired, output) in zip(
            CASES, baseline):
        issues = []
        if fired != expect_fail:
            issues.append("expected {0}, got {1}".format(
                "FAIL" if expect_fail else "PASS",
                "FAIL" if fired else "PASS"))
        for token in must_mention:
            if token not in output:
                issues.append("error text never quotes {0!r}".format(token))
        if issues:
            problems.append((name, issues))
            print("FAIL  {0}".format(name))
            for i in issues:
                print("        - {0}".format(i))
            for line in output.splitlines():
                print("        | {0}".format(line))
        else:
            print("ok    {0}".format(name))

    print()
    for label, mutant in MUTATIONS:
        mutated = _verdicts(mutant)
        flipped = [CASES[i][0] for i in range(len(CASES))
                   if mutated[i][0] != baseline[i][0]]
        if flipped:
            print("killed   {0}  (caught by: {1})".format(
                label, "; ".join(flipped[:2])))
        else:
            problems.append((label, ["mutation survived: no fixture noticed"]))
            print("SURVIVED {0}".format(label))

    print()
    if problems:
        print("::error file={0}::Gate 28 self-test: {1} problem(s). The "
              "detector does not do what its name claims, so a green Gate 28 "
              "over the real tree means nothing.".format(
                  LINT_WORKFLOW, len(problems)))
        return 1
    print("Gate 28 self-test: all {0} fixtures behaved as specified and all "
          "{1} mutations were killed.".format(len(CASES), len(MUTATIONS)))
    return 0


def main(argv):
    try:
        sys.stdout.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(
        description="Gate 28 - every `gh api` call that passes a field "
                    "states its method")
    ap.add_argument("--self-test", action="store_true",
                    help="run the detector against its fixtures and mutations")
    args = ap.parse_args(argv)
    return self_test() if args.self_test else sweep()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
