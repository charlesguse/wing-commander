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
Every entry in every register is exactly one of:

  tracked    it cites one or more issues, and each of them is OPEN.
  permanent  it cites none, and says so: `permanent` is true and
             `permanent_reason` is one short line on why the exception is
             the design rather than debt.

Registers, discovered rather than listed (a new register is covered the
day it lands):

  * every `.github/scripts/*-waivers.json`: each entry carries an `issue`
    key - a "#N" string, or null together with `"permanent": true` and a
    `permanent_reason`.
  * every module-level `EXEMPT_*` / `WAIVE*` table in a
    `.github/scripts/*.py` gate whose entries are calls carrying an
    `issue=` keyword (Gate 68's EXEMPT_JOBS today): `issue=` a non-empty
    tuple of ints, or `issue=()` with `permanent=True` and a
    `permanent_reason=` string. Read with `ast`, never imported, so the
    values must be literals - which is also what keeps them auditable in
    one diff.

TWO HALVES, TWO PLACES
----------------------
Offline (the default, PR-time lint job): the SCHEMA - issue XOR
permanent+reason, well-formed issue refs, literal Python values. It makes
no network call; the lint job runs offline and a PR cannot change whether
an issue is open.

Online (`--check-open`, lint-workflows.yml's scheduled `names-and-tags`
job): every cited issue is fetched with `gh api` and must be open. That
job already exists to check what "a PR's files cannot tell us" (Gate 1's
registrations, Gate 26's tags) on a daily schedule with a read token, so
this adds one step rather than a new workflow or a watchdog collector (the
watchdog inspects an adopter's stage runs; these registers exist only in
this repository). An issue closing is not a pull-request event, so the
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


class Entry(object):
    """One register entry, normalised: `issues` is a list of ints."""

    def __init__(self, where, issues, permanent, permanent_reason):
        self.where = where
        self.issues = issues
        self.permanent = permanent
        self.permanent_reason = permanent_reason


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


# --------------------------------------------------------------------------
# JSON registers
# --------------------------------------------------------------------------
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
            failures += _check_permanence(
                where, bool(issues), w.get("permanent"),
                w.get("permanent_reason"))
            entries.append(Entry(where, issues, w.get("permanent"),
                                 w.get("permanent_reason")))
    return entries, failures


# --------------------------------------------------------------------------
# Python exemption tables
# --------------------------------------------------------------------------
def _literal(node):
    try:
        return True, ast.literal_eval(node)
    except (ValueError, SyntaxError, TypeError):
        return False, None


def python_entries(root="."):
    """-> (entries, failures) across every EXEMPT_*/WAIVE* table whose
    entries are calls carrying an `issue=` keyword."""
    entries, failures = [], []
    for path in sorted(glob.glob(os.path.join(root, SCRIPTS_DIR, "*.py"))):
        rel = os.path.relpath(path, root).replace(os.sep, "/")
        try:
            with open(path, encoding="utf-8") as fh:
                tree = ast.parse(fh.read(), filename=rel)
        except (OSError, SyntaxError) as exc:
            failures.append("{0} could not be parsed ({1}).".format(rel, exc))
            continue
        for stmt in tree.body:
            targets = []
            if isinstance(stmt, ast.Assign):
                targets = [t for t in stmt.targets if isinstance(t, ast.Name)]
            elif isinstance(stmt, ast.AnnAssign) and isinstance(
                    stmt.target, ast.Name) and stmt.value is not None:
                targets = [stmt.target]
            names = [t.id for t in targets if TABLE_NAME_RE.match(t.id)]
            if not names:
                continue
            for call in ast.walk(stmt.value):
                if not isinstance(call, ast.Call):
                    continue
                kw = {k.arg: k.value for k in call.keywords if k.arg}
                if "issue" not in kw:
                    continue
                where = "{0}:{1} {2} entry".format(rel, call.lineno, names[0])
                ok, issue = _literal(kw["issue"])
                ok_p, permanent = (_literal(kw["permanent"])
                                   if "permanent" in kw else (True, None))
                ok_r, reason = (_literal(kw["permanent_reason"])
                                if "permanent_reason" in kw else (True, None))
                if not (ok and ok_p and ok_r):
                    failures.append(
                        "{0}: `issue`, `permanent` and `permanent_reason` "
                        "must be literals so the register is readable "
                        "without running it.".format(where))
                    continue
                if not isinstance(issue, tuple) or not all(
                        isinstance(n, int) and not isinstance(n, bool)
                        and n > 0 for n in issue):
                    failures.append(
                        "{0}: `issue` must be a tuple of issue numbers "
                        "(empty only when permanent), got {1!r}."
                        .format(where, issue))
                    continue
                failures += _check_permanence(where, bool(issue), permanent,
                                              reason)
                entries.append(Entry(where, list(issue), permanent, reason))
    return entries, failures


def collect(root="."):
    a, fa = json_entries(root)
    b, fb = python_entries(root)
    return a + b, fa + fb


# --------------------------------------------------------------------------
# Online half: every cited issue is open
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
    {"file": "a.yml", "issue": "#12", "reason": "tracked"},
    {"file": "b.yml", "issue": None, "permanent": True,
     "permanent_reason": "the design, not debt", "reason": "r"},
]}

_GOOD_PY = '''
ExemptionEntry = object
EXEMPT_JOBS = {
    ("a.yml", "j"): ExemptionEntry(reason="r", issue=(7, 8), condition=None),
    ("b.yml", "k"): ExemptionEntry(reason="r", issue=(), condition=None,
                                   permanent=True,
                                   permanent_reason="bounded by design"),
}
OTHER = {"x": ExemptionEntry(issue=None)}
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


def self_test():
    bad = 0

    def expect(label, files, want_fail, needle=None):
        nonlocal bad
        root = _tree(files)
        try:
            entries, failures = collect(root)
        finally:
            shutil.rmtree(root, ignore_errors=True)
        joined = "\n".join(failures)
        ok = bool(failures) == want_fail and (
            needle is None or needle in joined)
        print("{0} {1}".format("PASS" if ok else "FAIL", label))
        if not ok:
            print("    failures: {0}".format(failures or "none"))
            bad += 1
        return entries

    base = {SCRIPTS_DIR + "/x-waivers.json": _GOOD_JSON,
            SCRIPTS_DIR + "/verify-x.py": _GOOD_PY}
    entries = expect("well-formed JSON and Python registers pass", base, False)
    if sorted(n for e in entries for n in e.issues) != [7, 8, 12]:
        print("FAIL discovery found issues {0}, want [7, 8, 12]".format(
            sorted(n for e in entries for n in e.issues)))
        bad += 1
    if len(entries) != 4:
        print("FAIL a table not named EXEMPT_*/WAIVE* was read as a "
              "register ({0} entries)".format(len(entries)))
        bad += 1

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
    ]
    for label, fn, needle in json_mutations:
        expect(label, _mutate_json(fn), True, needle)

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
        ("Python: WAIVE* table is discovered too",
         _GOOD_PY.replace("EXEMPT_JOBS", "WAIVED_JOBS").replace(
             "permanent=True,\n", ""), "WAIVED_JOBS"),
    ]
    for label, text, needle in py_mutations:
        expect(label, {SCRIPTS_DIR + "/verify-x.py": text}, True, needle)

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
        print("{0} {1}".format("PASS" if ok else "FAIL", label))
        if not ok:
            print("    failures: {0}".format(failures or "none"))
            bad += 1
    if sorted(set(calls)) != [7, 8, 12]:
        print("FAIL check-open did not look up every cited issue: {0}"
              .format(sorted(set(calls))))
        bad += 1
    if check_open([e for e in entries if e.permanent],
                  lambda n: "closed") != []:
        print("FAIL check-open looked up an issue for a permanent entry")
        bad += 1
    saved = os.environ.pop("GITHUB_REPOSITORY", None)
    try:
        if gh_issue_state(1) is not None:
            print("FAIL gh_issue_state without GITHUB_REPOSITORY did not "
                  "fail closed")
            bad += 1
    finally:
        if saved is not None:
            os.environ["GITHUB_REPOSITORY"] = saved

    print("Gate 124 self-test: {0} failure(s).".format(bad))
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--check-open", action="store_true",
                    help="also require every cited issue to be open "
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
