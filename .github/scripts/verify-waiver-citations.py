#!/usr/bin/env python3
"""Gate 124 - a waiver cites an open issue, or says it is permanent.

WHY THIS EXISTS
---------------
Every waiver register in this directory says the same thing about itself:
an exception lives "in the open, with a reason and a tracking issue", and a
stale-check makes sure it "cannot outlive its reason". The stale-checks are
real, but they only look at the CODE side - a pattern that stops matching,
a count that drifts, a path that starts existing. Nothing looked at the
ISSUE side. An audit of the registers found every cited tracker closed:
the work landed, was re-scoped, or was abandoned, and the waiver kept
pointing at it, still promising a follow-up that no open issue was going
to deliver. A citation to a closed issue reads as "someone is on this"
when nobody is.

THE RULE
--------
Every entry is exactly one of:

  tracked    `issue` cites one or more issues, and each of them is OPEN.
  permanent  `issue` cites none, and says so: `permanent` is true and
             `permanent_reason` is one short line on why the exception is
             the design rather than debt.

TWO CITATION FIELDS
-------------------
  issue       the open TRACKER for retiring the waiver. `--check-open`
              looks every one of these up.
  decided_by  optional PROVENANCE: the issue(s) that DECIDED the waiver
              (spec 073 FR-007 requires an exemption to cite its deciding
              issue). It usually closed long ago - that is its job - so
              `--check-open` never looks it up; only its shape is checked.

SCOPE
-----
Two kinds of register, discovered rather than listed, so a new one is
covered the day it lands:

  * JSON `.github/scripts/*-waivers.json` registers: each entry carries an
    `issue` key - a "#N" string, or null together with `"permanent": true`
    and a `permanent_reason` - and optionally `decided_by`, a "#N" string
    or a list of them.
  * `EXEMPT_*` / `WAIVE*` Python tables: a module-level assignment in a
    `.github/scripts/*.py` whose name matches, and whose value is a
    container. It must be a dict literal whose every value is a call
    carrying `issue=` as a keyword (a tuple of ints, `()` only when
    `permanent=True` with a `permanent_reason=`), plus an optional
    `decided_by=` tuple. Read with `ast`, never imported, so every one of
    those values must be a literal. It fails LOUDLY, rather than skipping,
    on a value that is not a call, a call with no `issue=` keyword
    (positional included), a `**` spread, or any later subscript write or
    mutating method call on the table - each is a way for an entry to
    exist that this gate would otherwise never see.

    The one opt-out is NAME_ONLY_TABLES below: tables that match the name
    but are string-valued allow-lists of (file, step) sites with no issue
    citations by design. Each is named explicitly, and still fails if it
    ever grows a call.

    A matching name whose value is a string or a `re.compile(...)` (the
    `EXEMPT_RE` marker patterns) is not a table. Any other value fails,
    since the gate cannot tell whether it is a register.

Other exception shapes (`EXCEPTIONS` dicts, `*_ALLOWED` sets, inline
`wc-*-exempt:` markers) are out of scope for this gate.

TWO HALVES, TWO PLACES
----------------------
Offline (the default, PR-time lint job): the SCHEMA above. It makes no
network call; the lint job runs offline and a PR cannot change whether an
issue is open.

Online (`--check-open`, lint-workflows.yml's scheduled `names-and-tags`
job): every `issue` citation is fetched with `gh api` and must be open.
That job already exists to check what "a PR's files cannot tell us" (Gate
1's registrations, Gate 26's tags) on a daily schedule with a read token,
so this adds one step rather than a new workflow or a watchdog collector
(the watchdog inspects an adopter's stage runs; these registers exist only
in this repository). An issue closing is not a pull-request event, so the
daily schedule is what bounds how long a waiver can cite a closed issue.
A lookup that fails is a failure, not a pass: an unreadable issue cannot
be shown to be open.

Usage:
    python3 .github/scripts/verify-waiver-citations.py
    python3 .github/scripts/verify-waiver-citations.py --self-test
    python3 .github/scripts/verify-waiver-citations.py --check-open
"""
import argparse
import ast
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

SCRIPTS_DIR = ".github/scripts"
JSON_GLOB = "*-waivers.json"
TABLE_NAME_RE = re.compile(r"^(EXEMPT|WAIVE)[A-Z0-9_]*$")
ISSUE_REF_RE = re.compile(r"^#([1-9][0-9]*)$")
MAX_PERMANENT_REASON = 240

# (script basename, table name): string-valued allow-lists of sites that
# match TABLE_NAME_RE but carry no issue citations by design. Explicit and
# narrow - each must stay free of calls, or it fails like any other table.
NAME_ONLY_TABLES = {
    ("verify-rate-limited-exemption.py", "EXEMPT_SITES"),
    ("verify-commit-message-scratch-path.py", "EXEMPT_SITES"),
}

_MUTATING_METHODS = {"update", "setdefault", "add", "append", "extend",
                     "insert", "__setitem__", "pop", "popitem", "clear",
                     "discard", "remove"}


class Entry(object):
    """One register entry, normalised: `issues`/`decided_by` are int lists."""

    def __init__(self, where, issues, permanent, permanent_reason,
                 decided_by=()):
        self.where = where
        self.issues = issues
        self.permanent = permanent
        self.permanent_reason = permanent_reason
        self.decided_by = list(decided_by)


def _check_permanence(where, has_issue, permanent, reason):
    """-> failure strings for the issue XOR permanent+reason rule."""
    out = []
    if permanent not in (True, False, None):
        out.append("{0}: `permanent` must be true or absent, got {1!r}."
                   .format(where, permanent))
        return out
    if has_issue and permanent:
        out.append(
            "{0} cites an issue AND is marked permanent. Pick one: a "
            "tracked waiver is retired when its issue closes; a permanent "
            "one has no issue to close.".format(where))
    elif not has_issue and not permanent:
        out.append(
            "{0} cites no issue and is not marked permanent. Cite the OPEN "
            "issue that tracks retiring it, or set `permanent: true` with a "
            "one-line `permanent_reason` - an exception with neither is a "
            "promise nobody holds.".format(where))
    if permanent:
        if not isinstance(reason, str) or not reason.strip():
            out.append("{0} is permanent but has no `permanent_reason`: say "
                       "in one line why this is the design, not debt."
                       .format(where))
        elif "\n" in reason or len(reason) > MAX_PERMANENT_REASON:
            out.append("{0}'s `permanent_reason` must be one line of at most "
                       "{1} characters; the long story belongs in `reason` "
                       "or git log.".format(where, MAX_PERMANENT_REASON))
    elif reason is not None:
        out.append("{0} carries a `permanent_reason` but is not permanent."
                   .format(where))
    return out


def _is_issue_number(n):
    return isinstance(n, int) and not isinstance(n, bool) and n > 0


# --------------------------------------------------------------------------
# JSON registers
# --------------------------------------------------------------------------
def _json_decided_by(where, value):
    """-> (numbers, failures) for an optional JSON `decided_by`."""
    if value is None:
        return [], []
    refs = value if isinstance(value, list) else [value]
    nums = []
    for ref in refs:
        m = ISSUE_REF_RE.match(ref) if isinstance(ref, str) else None
        if not m:
            return [], ["{0}: `decided_by` must be a \"#N\" reference or a "
                        "list of them, got {1!r}.".format(where, value)]
        nums.append(int(m.group(1)))
    if not nums:
        return [], ["{0}: `decided_by` is an empty list; omit it instead."
                    .format(where)]
    return nums, []


def json_entries(root="."):
    """-> (entries, failures) across every *-waivers.json."""
    entries, failures = [], []
    for path in sorted(glob.glob(os.path.join(root, SCRIPTS_DIR, JSON_GLOB))):
        rel = os.path.relpath(path, root).replace(os.sep, "/")
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError) as exc:
            failures.append("{0} could not be read ({1}).".format(rel, exc))
            continue
        waivers = data.get("waivers") if isinstance(data, dict) else None
        if not isinstance(waivers, list):
            failures.append('{0} must contain a "waivers" list.'.format(rel))
            continue
        for index, w in enumerate(waivers):
            where = "{0} entry {1}".format(rel, index)
            if not isinstance(w, dict):
                failures.append("{0} is not an object.".format(where))
                continue
            if "issue" not in w:
                failures.append(
                    "{0} has no `issue` key. Every waiver entry states its "
                    "tracking issue as \"#N\", or `null` together with "
                    "`permanent: true`.".format(where))
                continue
            issue = w["issue"]
            issues = []
            if issue is not None:
                m = ISSUE_REF_RE.match(issue) if isinstance(issue, str) else None
                if not m:
                    failures.append(
                        "{0}: `issue` must be a single \"#N\" reference or "
                        "null, got {1!r}.".format(where, issue))
                    continue
                issues = [int(m.group(1))]
            decided, bad = _json_decided_by(where, w.get("decided_by"))
            failures += bad
            failures += _check_permanence(
                where, bool(issues), w.get("permanent"),
                w.get("permanent_reason"))
            entries.append(Entry(where, issues, w.get("permanent"),
                                 w.get("permanent_reason"), decided))
    return entries, failures


# --------------------------------------------------------------------------
# Python exemption tables
# --------------------------------------------------------------------------
def _literal(node):
    try:
        return True, ast.literal_eval(node)
    except (ValueError, SyntaxError, TypeError):
        return False, None


def _is_re_compile(node):
    return (isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "compile"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "re")


def _table_assignments(tree):
    """-> [(name, value_node, lineno)] for module-level matching names."""
    out = []
    for stmt in tree.body:
        if isinstance(stmt, ast.Assign):
            for t in stmt.targets:
                if isinstance(t, ast.Name) and TABLE_NAME_RE.match(t.id):
                    out.append((t.id, stmt.value, stmt.lineno))
        elif (isinstance(stmt, ast.AnnAssign)
              and isinstance(stmt.target, ast.Name)
              and TABLE_NAME_RE.match(stmt.target.id)
              and stmt.value is not None):
            out.append((stmt.target.id, stmt.value, stmt.lineno))
    return out


def _table_mutations(tree, names, rel):
    """Failures for any write into a table after its literal: a subscript
    assignment/augassign/delete, or a mutating method call, anywhere in the
    module (a function body included)."""
    out = []

    def hit(node, lineno, how):
        out.append(
            "{0}:{1}: {2} writes into {3} outside its literal. Every entry "
            "must be in the one dict literal this gate reads; an entry "
            "added any other way is never checked.".format(
                rel, lineno, how, node))

    for node in ast.walk(tree):
        targets = []
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
            targets = [node.target]
        elif isinstance(node, ast.Delete):
            targets = node.targets
        for t in targets:
            if (isinstance(t, ast.Subscript) and isinstance(t.value, ast.Name)
                    and t.value.id in names):
                hit(t.value.id, node.lineno, "a subscript write")
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id in names
                and node.func.attr in _MUTATING_METHODS):
            hit(node.func.value.id, node.lineno,
                "`.{0}()`".format(node.func.attr))
    return out


def _table_entries(rel, name, value, lineno):
    """-> (entries, failures) for one non-opted-out table's dict literal."""
    entries, failures = [], []
    if not isinstance(value, ast.Dict):
        return [], ["{0}:{1}: {2} must be a dict literal of entries, so "
                    "every entry is readable without running the file."
                    .format(rel, lineno, name)]
    for key, val in zip(value.keys, value.values):
        at = getattr(val, "lineno", lineno)
        where = "{0}:{1} {2} entry".format(rel, at, name)
        if key is None:
            failures.append("{0} is a `**` spread; entries must be written "
                            "out in the literal.".format(where))
            continue
        if not isinstance(val, ast.Call):
            failures.append(
                "{0} is not a call. Every {1} entry is a call carrying "
                "`issue=` (and `permanent=`/`permanent_reason=` when it has "
                "none); a bare value cannot cite anything.".format(where, name))
            continue
        kw = {k.arg: k.value for k in val.keywords if k.arg}
        if "issue" not in kw:
            failures.append(
                "{0} has no `issue=` keyword{1}. Pass the tracker as "
                "`issue=` by keyword, so the citation is visible here.".format(
                    where, " (positional arguments are not read)"
                    if val.args else ""))
            continue
        ok, issue = _literal(kw["issue"])
        ok_p, permanent = (_literal(kw["permanent"])
                           if "permanent" in kw else (True, None))
        ok_r, reason = (_literal(kw["permanent_reason"])
                        if "permanent_reason" in kw else (True, None))
        ok_d, decided = (_literal(kw["decided_by"])
                         if "decided_by" in kw else (True, ()))
        if not (ok and ok_p and ok_r and ok_d):
            failures.append(
                "{0}: `issue`, `permanent`, `permanent_reason` and "
                "`decided_by` must be literals so the register is readable "
                "without running it.".format(where))
            continue
        if not isinstance(issue, tuple) or not all(
                _is_issue_number(n) for n in issue):
            failures.append(
                "{0}: `issue` must be a tuple of issue numbers (empty only "
                "when permanent), got {1!r}.".format(where, issue))
            continue
        if not isinstance(decided, tuple) or not all(
                _is_issue_number(n) for n in decided):
            failures.append(
                "{0}: `decided_by` must be a tuple of issue numbers, got "
                "{1!r}.".format(where, decided))
            continue
        failures += _check_permanence(where, bool(issue), permanent, reason)
        entries.append(Entry(where, list(issue), permanent, reason, decided))
    return entries, failures


def python_entries(root="."):
    """-> (entries, failures) across every EXEMPT_*/WAIVE* Python table."""
    entries, failures = [], []
    for path in sorted(glob.glob(os.path.join(root, SCRIPTS_DIR, "*.py"))):
        rel = os.path.relpath(path, root).replace(os.sep, "/")
        base = os.path.basename(path)
        try:
            with open(path, encoding="utf-8") as fh:
                tree = ast.parse(fh.read(), filename=rel)
        except (OSError, SyntaxError) as exc:
            failures.append("{0} could not be parsed ({1}).".format(rel, exc))
            continue
        tables = set()
        for name, value, lineno in _table_assignments(tree):
            if isinstance(value, ast.Constant) and isinstance(
                    value.value, str) or _is_re_compile(value):
                continue  # a marker string or pattern, not a table
            tables.add(name)
            if (base, name) in NAME_ONLY_TABLES:
                ok, _ = _literal(value)
                if not ok or any(isinstance(n, ast.Call)
                                 for n in ast.walk(value)):
                    failures.append(
                        "{0}:{1}: {2} is opted out of Gate 124 as a "
                        "string-valued site list, but it is no longer a "
                        "plain literal. Remove it from NAME_ONLY_TABLES and "
                        "give its entries `issue=` citations.".format(
                            rel, lineno, name))
                continue
            e, f = _table_entries(rel, name, value, lineno)
            entries += e
            failures += f
        if tables:
            failures += _table_mutations(tree, tables, rel)
    return entries, failures


def collect(root="."):
    a, fa = json_entries(root)
    b, fb = python_entries(root)
    return a + b, fa + fb


# --------------------------------------------------------------------------
# Online half: every `issue` citation is open (never `decided_by`)
# --------------------------------------------------------------------------
def gh_issue_state(number):
    """-> 'open' | 'closed' | None (lookup failed). Scheduled job only."""
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if not repo:
        return None
    try:
        r = subprocess.run(
            ["gh", "api", "-X", "GET",
             "repos/{0}/issues/{1}".format(repo, number), "--jq", ".state"],
            capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    state = r.stdout.strip() if r.returncode == 0 else ""
    return state if state in ("open", "closed") else None


def check_open(entries, fetch_state):
    """-> failure strings. `fetch_state(n)` -> 'open'|'closed'|None."""
    failures = []
    cache = {}
    for e in entries:
        for n in e.issues:
            if n not in cache:
                cache[n] = fetch_state(n)
            state = cache[n]
            if state == "open":
                continue
            if state == "closed":
                failures.append(
                    "{0} cites #{1}, which is CLOSED. The waiver has outlived "
                    "its tracker: retire the waiver, repoint it at the open "
                    "issue that now tracks it, or mark it permanent with a "
                    "one-line reason.".format(e.where, n))
            else:
                failures.append(
                    "{0} cites #{1}, whose state could not be read. An "
                    "unreadable issue cannot be shown to be open, so this "
                    "fails rather than passes.".format(e.where, n))
    return failures


# --------------------------------------------------------------------------
# Self-test
# --------------------------------------------------------------------------
_GOOD_JSON = {"waivers": [
    {"file": "a.yml", "issue": "#12", "decided_by": "#90", "reason": "r"},
    {"file": "b.yml", "issue": None, "permanent": True,
     "permanent_reason": "the design, not debt", "decided_by": ["#91", "#92"],
     "reason": "r"},
]}

_GOOD_PY = '''
import re
ExemptionEntry = object
EXEMPT_RE = re.compile(r"marker")
EXEMPTED_WITH_REASON = "a fixture string"
EXEMPT_JOBS = {
    ("a.yml", "j"): ExemptionEntry(reason="r", issue=(7, 8), condition=None,
                                   decided_by=(93,)),
    ("b.yml", "k"): ExemptionEntry(reason="r", issue=(), condition=None,
                                   permanent=True,
                                   permanent_reason="bounded by design"),
}
OTHER = {"x": ExemptionEntry(issue=None)}
'''

_OPT_OUT_PY = '''
EXEMPT_SITES = {
    ("watchdog.yml", "Ensure usage-limit issue"),
}
'''


def _tree(files):
    root = tempfile.mkdtemp(prefix="wc-waiver-citations-")
    for rel, text in files.items():
        path = os.path.join(root, *rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text if isinstance(text, str) else json.dumps(text))
    return root


def _mutate_json(fn):
    data = json.loads(json.dumps(_GOOD_JSON))
    fn(data["waivers"])
    return {SCRIPTS_DIR + "/x-waivers.json": data}


class _FakeRun(object):
    def __init__(self, returncode, stdout, exc=None):
        self.returncode, self.stdout, self.exc = returncode, stdout, exc
        self.calls = []

    def __call__(self, argv, **kwargs):
        self.calls.append(argv)
        if self.exc:
            raise self.exc
        return self


def self_test():
    bad = 0

    def report(ok, label, detail=""):
        nonlocal bad
        print("{0} {1}".format("PASS" if ok else "FAIL", label))
        if not ok:
            if detail:
                print("    {0}".format(detail))
            bad += 1

    def expect(label, files, want_fail, needle=None):
        root = _tree(files)
        try:
            entries, failures = collect(root)
        finally:
            shutil.rmtree(root, ignore_errors=True)
        joined = "\n".join(failures)
        ok = bool(failures) == want_fail and (
            needle is None or needle in joined)
        report(ok, label, "failures: {0}".format(failures or "none"))
        return entries

    rl = SCRIPTS_DIR + "/verify-rate-limited-exemption.py"
    base = {SCRIPTS_DIR + "/x-waivers.json": _GOOD_JSON,
            SCRIPTS_DIR + "/verify-x.py": _GOOD_PY,
            rl: _OPT_OUT_PY}
    entries = expect("well-formed registers pass (marker regex/string and "
                     "the named opt-out table are not tables)", base, False)
    got = sorted(n for e in entries for n in e.issues)
    report(got == [7, 8, 12], "discovery reads every `issue` citation",
           "got {0}".format(got))
    got = sorted(n for e in entries for n in e.decided_by)
    report(got == [90, 91, 92, 93], "discovery reads every `decided_by`",
           "got {0}".format(got))
    report(len(entries) == 4, "a table not named EXEMPT_*/WAIVE* is not "
           "read as a register", "{0} entries".format(len(entries)))

    def drop(key, i=0):
        return lambda w: w[i].pop(key)

    def put(key, val, i=0):
        return lambda w: w[i].__setitem__(key, val)

    json_mutations = [
        ("JSON: missing issue key", drop("issue"), "no `issue` key"),
        ("JSON: bare-number issue", put("issue", "12"), "single \"#N\""),
        ("JSON: two issues in one string", put("issue", "#12, #13"),
         "single \"#N\""),
        ("JSON: issue AND permanent", put("permanent", True), "AND is marked"),
        ("JSON: null issue, not permanent", drop("permanent", 1),
         "not marked permanent"),
        ("JSON: permanent without reason", drop("permanent_reason", 1),
         "no `permanent_reason`"),
        ("JSON: permanent reason multi-line",
         put("permanent_reason", "a\nb", 1), "one line"),
        ("JSON: permanent reason too long",
         put("permanent_reason", "x" * 241, 1), "one line"),
        ("JSON: permanent given as a string", put("permanent", "yes", 1),
         "must be true or absent"),
        ("JSON: permanent_reason on a tracked entry",
         put("permanent_reason", "why"), "not permanent"),
        ("JSON: malformed decided_by", put("decided_by", "558"),
         "`decided_by` must be"),
        ("JSON: empty decided_by list", put("decided_by", [], 1),
         "empty list"),
    ]
    for label, fn, needle in json_mutations:
        expect(label, _mutate_json(fn), True, needle)

    good_call = ('ExemptionEntry(reason="r", issue=(7, 8), condition=None,\n'
                 '                                   decided_by=(93,))')
    py_mutations = [
        ("Python: issue=() without permanent",
         _GOOD_PY.replace("permanent=True,\n", ""), "not marked permanent"),
        ("Python: permanent without reason",
         _GOOD_PY.replace('permanent_reason="bounded by design"', ""),
         "no `permanent_reason`"),
        ("Python: issue AND permanent",
         _GOOD_PY.replace("issue=(), condition", "issue=(9,), condition"),
         "AND is marked"),
        ("Python: non-literal issue",
         _GOOD_PY.replace("issue=(7, 8)", "issue=ISSUES"), "literals"),
        ("Python: issue as a string",
         _GOOD_PY.replace("issue=(7, 8)", 'issue="#7"'), "tuple of issue"),
        ("Python: malformed decided_by",
         _GOOD_PY.replace("decided_by=(93,)", 'decided_by=("#93",)'),
         "`decided_by` must be"),
        ("Python: WAIVE* table is discovered too",
         _GOOD_PY.replace("EXEMPT_JOBS", "WAIVED_JOBS").replace(
             "permanent=True,\n", ""), "WAIVED_JOBS"),
        ("Python: an entry passing issue positionally fails loudly",
         _GOOD_PY.replace(good_call,
                          'ExemptionEntry("r", (7, 8), None)'),
         "positional arguments are not read"),
        ("Python: a non-call entry fails loudly",
         _GOOD_PY.replace(good_call, '"just a reason string"'),
         "is not a call"),
        ("Python: a later subscript write into the table fails loudly",
         _GOOD_PY + '\nEXEMPT_JOBS[("c.yml", "z")] = ExemptionEntry('
                    'reason="r", issue=(), condition=None)\n',
         "a subscript write"),
        ("Python: a subscript write inside a function fails loudly",
         _GOOD_PY + '\ndef add():\n    EXEMPT_JOBS["k"] = None\n',
         "a subscript write"),
        ("Python: a .update() into the table fails loudly",
         _GOOD_PY + '\nEXEMPT_JOBS.update({})\n', "`.update()`"),
        ("Python: a ** spread in the table fails loudly",
         _GOOD_PY.replace('    ("b.yml", "k")', '    **OTHER,\n    ("b.yml", "k")'),
         "spread"),
        ("Python: a table that is not a dict literal fails loudly",
         _GOOD_PY + '\nEXEMPT_MORE = dict(a=1)\n', "must be a dict literal"),
    ]
    for label, text, needle in py_mutations:
        expect(label, {SCRIPTS_DIR + "/verify-x.py": text}, True, needle)

    expect("an un-named EXEMPT_SITES-shaped table is NOT opted out",
           {SCRIPTS_DIR + "/verify-other.py": _OPT_OUT_PY}, True,
           "must be a dict literal")
    expect("an opted-out table that grows a call fails loudly",
           {rl: _OPT_OUT_PY.replace(
               '("watchdog.yml", "Ensure usage-limit issue")',
               'Entry(issue=(1,))')}, True, "no longer a plain literal")
    expect("a subscript write into an opted-out table fails loudly",
           {rl: _OPT_OUT_PY + '\nEXEMPT_SITES.add(("x", "y"))\n'}, True,
           "`.add()`")
    expect("unparseable register fails",
           {SCRIPTS_DIR + "/x-waivers.json": "{not json"}, True,
           "could not be read")

    # Online half, with an injected state reader (no network).
    root = _tree(base)
    try:
        entries, _ = collect(root)
    finally:
        shutil.rmtree(root, ignore_errors=True)
    calls = []

    def states(table):
        def fetch(n):
            calls.append(n)
            return table.get(n)
        return fetch

    cases = [
        ("check-open: every cited issue open passes",
         {7: "open", 8: "open", 12: "open"}, 0, None),
        ("check-open: a closed cited issue fails, naming entry and issue",
         {7: "open", 8: "closed", 12: "open"}, 1, "cites #8, which is CLOSED"),
        ("check-open: an unreadable issue fails closed",
         {7: "open", 8: "open"}, 1, "cites #12, whose state could not"),
        ("check-open: an unexpected state string fails closed",
         {7: "open", 8: "open", 12: "OPEN"}, 1, "could not be read"),
    ]
    for label, table, want, needle in cases:
        del calls[:]
        failures = check_open(entries, states(table))
        ok = len(failures) == want and (
            needle is None or needle in "\n".join(failures))
        report(ok, label, "failures: {0}".format(failures or "none"))
    report(sorted(set(calls)) == [7, 8, 12],
           "check-open looks up every `issue` and never a `decided_by`",
           "looked up {0}".format(sorted(set(calls))))
    report(check_open([e for e in entries if e.permanent],
                      lambda n: "closed") == [],
           "check-open looks nothing up for a permanent entry")

    # gh_issue_state, with subprocess.run stubbed.
    saved_env = os.environ.get("GITHUB_REPOSITORY")
    saved_run = subprocess.run
    try:
        os.environ.pop("GITHUB_REPOSITORY", None)
        report(gh_issue_state(1) is None,
               "gh_issue_state without GITHUB_REPOSITORY fails closed")
        os.environ["GITHUB_REPOSITORY"] = "o/r"
        for label, fake, want in [
                ("gh_issue_state reads an open issue",
                 _FakeRun(0, "open\n"), "open"),
                ("gh_issue_state reads a closed issue",
                 _FakeRun(0, "closed\n"), "closed"),
                ("gh_issue_state: a non-zero gh exit fails closed even "
                 "with 'open' on stdout", _FakeRun(1, "open\n"), None),
                ("gh_issue_state: a junk state fails closed",
                 _FakeRun(0, '{"message":"Not Found"}\n'), None),
                ("gh_issue_state: gh missing fails closed",
                 _FakeRun(0, "", exc=OSError("no gh")), None)]:
            subprocess.run = fake
            got = gh_issue_state(5)
            report(got == want and fake.calls and
                   fake.calls[0][-3] == "repos/o/r/issues/5",
                   label, "got {0!r}, calls {1}".format(got, fake.calls))
    finally:
        subprocess.run = saved_run
        if saved_env is None:
            os.environ.pop("GITHUB_REPOSITORY", None)
        else:
            os.environ["GITHUB_REPOSITORY"] = saved_env

    # main() really runs check_open under --check-open, and only then.
    g = globals()
    saved_fetch, saved_argv, saved_cwd = g["gh_issue_state"], sys.argv, \
        os.getcwd()
    root = _tree(base)
    looked = []
    try:
        os.chdir(root)
        g["gh_issue_state"] = lambda n: looked.append(n) or "closed"
        for argv, want_rc, want_looked, label in [
                (["x", "--check-open"], 1, True,
                 "main --check-open looks up cited issues and fails on a "
                 "closed one"),
                (["x"], 0, False,
                 "main without --check-open makes no lookup")]:
            del looked[:]
            sys.argv = argv
            devnull = open(os.devnull, "w")
            saved_out, sys.stdout = sys.stdout, devnull
            try:
                rc = main()
            finally:
                sys.stdout = saved_out
                devnull.close()
            report(rc == want_rc and bool(looked) == want_looked, label,
                   "rc {0}, looked up {1}".format(rc, looked))
    finally:
        g["gh_issue_state"] = saved_fetch
        sys.argv = saved_argv
        os.chdir(saved_cwd)
        shutil.rmtree(root, ignore_errors=True)

    print("Gate 124 self-test: {0} failure(s).".format(bad))
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--check-open", action="store_true",
                    help="also require every cited `issue` to be open "
                         "(needs gh, GH_TOKEN and GITHUB_REPOSITORY)")
    args = ap.parse_args()
    if args.self_test:
        return self_test()
    entries, failures = collect(".")
    if args.check_open and not failures:
        failures = check_open(entries, gh_issue_state)
    for f in failures:
        print("::error::{0}".format(f))
    tracked = sum(1 for e in entries if e.issues)
    print("Gate 124: {0} waiver entries ({1} tracked, {2} permanent){3}; "
          "{4} failure(s).".format(
              len(entries), tracked, len(entries) - tracked,
              ", every cited issue checked open" if args.check_open else "",
              len(failures)))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
