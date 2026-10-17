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
and every script under .claude/skills/*/scripts/. Exempt: wc_convergence.py
itself and its tests (not scanned at all), and the review-until-clean
skill's thrash_signals.py, which is the skill's CLI over the module.

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

# Allowed callers of the shared module (relative to the repo root).
EXEMPT = {
    ".claude/skills/review-until-clean/scripts/thrash_signals.py",
}

# Arithmetic: blame attribution, rewritten-range diff, diff-size numstat.
ARITHMETIC_RE = re.compile(
    r"\bgit\s+blame\b|\"blame\"|'blame'|--numstat|\bremoved_ranges\b|"
    r"\bdef\s+blame_commits\b|\bdef\s+diff_size\b")
# Threshold literals: the names of the THRESHOLDS table's keys, read from
# the module so a new threshold is covered the day it is added.
THRESHOLD_RE = re.compile(
    "|".join(r"\b{0}\b".format(re.escape(k)) for k in sorted(THRESHOLDS)))

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
        if rel in EXEMPT:
            continue
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
    if failures:
        print("verify-convergence-single-home: {0} failure(s)".format(len(failures)))
        return 1
    print("verify-convergence-single-home: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
