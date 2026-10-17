#!/usr/bin/env python3
"""Gate — the review-convergence arithmetic has exactly one home
(specs/116-review-convergence-analyze, FR-010, T016).

The attribution (git blame), churn (rewritten-range diff), diff-size
(numstat) arithmetic and the stop thresholds live in
.github/scripts/wc_convergence.py. A workflow, composite action or skill
script that carries its own copy drifts silently the next time the shared
one changes -- the same failure the per-run cost line once had in 12
run-blocks (see verify-metrics-summary-record-emission.py).

Scanned: every .github/workflows/*.yml, every file under .github/actions/,
and every script under .claude/skills/*/scripts/ -- the review-until-clean
skill's thrash_signals.py included: since T005 it is a thin CLI over the
module and must carry no copy of its own. wc_convergence.py itself and its
tests live under .github/scripts/ and are not scanned at all.

The skill's thrash check must also CALL the module (US4 scenario 1): a
skill script that drops the module and prints nothing would carry no copy
and still pass the scan, so the skill script is required to import it.

Each failure branch has a checked-in fixture in
verify-convergence-single-home-fixtures/ (Constitution VIII): `bad-*` files
must be rejected, `ok-*` files must pass. A scan that rejects no `bad-*`
fixture proves nothing about the real tree and fails the gate.
"""
import glob
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from wc_convergence import THRESHOLDS  # noqa: E402

ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
FIXTURES = os.path.join(HERE, "verify-convergence-single-home-fixtures")

# Arithmetic: blame attribution, rewritten-range diff, diff-size numstat.
ARITHMETIC_RE = re.compile(
    r"\bgit\s+blame\b|\"blame\"|'blame'|--numstat|\bremoved_ranges\b|"
    r"\bdef\s+blame_commits\b|\bdef\s+diff_size\b")
# Threshold literals: the names of the THRESHOLDS table's keys, read from
# the module so a new threshold is covered the day it is added.
THRESHOLD_RE = re.compile(
    "|".join(r"\b{0}\b".format(re.escape(k)) for k in sorted(THRESHOLDS)))

SKILL_CALLER = ".claude/skills/review-until-clean/scripts/thrash_signals.py"
IMPORT_RE = re.compile(r"^\s*(?:import\s+wc_convergence\b|from\s+wc_convergence\s+import\b)",
                       re.MULTILINE)

failures = []


def fail(msg):
    failures.append(msg)
    print("::error::verify-convergence-single-home: " + msg)


def scan_text(text):
    """Reasons a file's text carries a copy of the convergence arithmetic."""
    reasons = []
    if ARITHMETIC_RE.search(text):
        reasons.append("blame/churn/diff-size arithmetic")
    if THRESHOLD_RE.search(text):
        reasons.append("threshold literal")
    return reasons


def tree_files():
    paths = glob.glob(os.path.join(ROOT, ".github", "workflows", "*.y*ml"))
    for base in (os.path.join(ROOT, ".github", "actions"),):
        for dirpath, _dirs, names in os.walk(base):
            paths += [os.path.join(dirpath, n) for n in names]
    paths += glob.glob(os.path.join(ROOT, ".claude", "skills", "*", "scripts", "*"))
    return sorted(p for p in paths if os.path.isfile(p))


def case_real_tree_has_no_copy():
    scanned = 0
    for path in tree_files():
        rel = os.path.relpath(path, ROOT).replace(os.sep, "/")
        if "/_tests/" in rel or "-tests/" in rel:
            continue
        try:
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
        except UnicodeDecodeError:
            continue
        scanned += 1
        reasons = scan_text(text)
        if reasons:
            fail("{0} carries {1}; the only home is "
                 ".github/scripts/wc_convergence.py -- call its CLI "
                 "instead of copying it".format(rel, " and ".join(reasons)))
    if scanned == 0:
        fail("scanned zero files; the scan has stopped matching the tree")
    else:
        print("note: {0} file(s) scanned; none carries a copy of the "
              "convergence arithmetic or thresholds".format(scanned))


def calls_module(text):
    return bool(IMPORT_RE.search(text))


def case_skill_calls_the_module():
    path = os.path.join(ROOT, SKILL_CALLER)
    if not os.path.isfile(path):
        fail("{0} is missing; the review-until-clean skill's thrash check "
             "has no CLI".format(SKILL_CALLER))
        return
    with open(path, encoding="utf-8") as fh:
        if not calls_module(fh.read()):
            fail("{0} does not import wc_convergence; the skill's thrash "
                 "check must call the one home of the arithmetic".format(SKILL_CALLER))
    for name in sorted(os.listdir(FIXTURES)):
        if not name.startswith(("caller-bad-", "caller-ok-")):
            continue
        with open(os.path.join(FIXTURES, name), encoding="utf-8") as fh:
            got = calls_module(fh.read())
        if got != name.startswith("caller-ok-"):
            fail("fixture {0} was judged {1} by the caller check".format(
                name, "a caller" if got else "not a caller"))


def case_fixtures_are_judged_correctly():
    names = sorted(os.listdir(FIXTURES)) if os.path.isdir(FIXTURES) else []
    bad = [n for n in names if n.startswith("bad-")]
    ok = [n for n in names if n.startswith("ok-")]
    if not bad or not ok:
        fail("fixtures directory must hold at least one bad-* and one ok-* "
             "file: {0}".format(FIXTURES))
        return
    for n in bad:
        with open(os.path.join(FIXTURES, n), encoding="utf-8") as fh:
            if not scan_text(fh.read()):
                fail("fixture {0} carries a copy but the scan did not reject "
                     "it, so its verdict on the real tree proves nothing".format(n))
    for n in ok:
        with open(os.path.join(FIXTURES, n), encoding="utf-8") as fh:
            reasons = scan_text(fh.read())
        if reasons:
            fail("fixture {0} calls the shared module correctly but the scan "
                 "rejected it ({1})".format(n, ", ".join(reasons)))
    print("note: {0} bad and {1} ok fixture(s) judged correctly".format(
        len(bad), len(ok)))


def main():
    case_real_tree_has_no_copy()
    case_fixtures_are_judged_correctly()
    case_skill_calls_the_module()
    if failures:
        print("verify-convergence-single-home: {0} failure(s)".format(len(failures)))
        return 1
    print("verify-convergence-single-home: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
