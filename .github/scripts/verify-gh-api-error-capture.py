#!/usr/bin/env python3
"""Gate 126 - no `gh api` capture carries an unhandled error body downstream.

WHY THIS EXISTS
---------------
On an HTTP error, `gh api ... --jq '<filter>'` still prints the raw JSON
error body to stdout while the human-readable line goes to stderr and the
filter is never applied -- so `x="$(gh api ...)"` leaves `x` holding
`{"message":"Not Found",...}` on failure, not an empty string. #497 fixed
one site; specs/091-gh-api-error-capture's own audit (User Story 1) fixed
or confirmed every other live capture. This gate is what keeps a NEW
capture from regressing the same way: it classifies every covered `gh api`
capture's failure path and fails on any that does not exit the step,
reassign the captured variable, leave the loop iteration, or carry a
stated-reason `# wc-gh-api-error-exempt: <reason>` marker.

SCOPE
-----
`.github/workflows/*.yml|yaml` and `.github/actions/**/action.yml|yaml`.
Only `gh api` captures (wc_gh_capture.COVERED_GH_SUBCOMMANDS, FR-013) --
`gh issue view`/`gh pr list`/etc. are out of scope.

Usage:
    python3 .github/scripts/verify-gh-api-error-capture.py
    python3 .github/scripts/verify-gh-api-error-capture.py --self-test
"""
import argparse
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_gh_capture import classify_failure_path, find_capture_sites  # noqa: E402


def posix(path):
    return path.replace(os.sep, "/")


def subject_files():
    paths = (glob.glob(".github/workflows/*.yml")
             + glob.glob(".github/workflows/*.yaml")
             + glob.glob(".github/actions/**/action.yml", recursive=True)
             + glob.glob(".github/actions/**/action.yaml", recursive=True))
    return sorted(set(posix(p) for p in paths))


def _message(site, classification):
    fix = ("reassign `{0}` before its next use, exit the step, or add "
           "`# wc-gh-api-error-exempt: <reason>` if retaining the error "
           "body is deliberate".format(site.variable))
    return (
        "::error file={0},line={1}::Gate 126: `{2}` captures `gh {3}` but "
        "its failure path does not {4} - a failed read would leave `{2}` "
        "holding the raw error body, not empty. Fix: {5}.".format(
            site.file, site.line, site.variable, site.subcommand,
            "reassign, exit, or carry a wc-gh-api-error-exempt marker",
            fix))


def _marker_message(site):
    return (
        "::error file={0},line={1}::Gate 126: `{2}`'s "
        "`# wc-gh-api-error-exempt:` marker has no reason after the colon. "
        "A bare marker does not count - state why retaining the error body "
        "is deliberate.".format(site.file, site.line, site.variable))


def scan_text(path, text):
    unsafe, bare_markers = [], []
    for site in find_capture_sites(text, path):
        c = classify_failure_path(text, site)
        if c.verdict == "unsafe":
            unsafe.append(_message(site, c))
        elif c.verdict == "bare-marker":
            bare_markers.append(_marker_message(site))
    return unsafe, bare_markers


LINT_WORKFLOW = ".github/workflows/lint-workflows.yml"


def sweep():
    if not os.path.isfile(LINT_WORKFLOW):
        sys.exit("::error::run this from the repository root; {0} not "
                 "found.".format(LINT_WORKFLOW))
    files = subject_files()
    if not files:
        sys.exit("::error::Gate 126 matched no workflows or composite "
                 "actions at all. That is a broken sweep, not a clean tree.")
    unsafe, bare_markers = [], []
    for path in files:
        with open(path, encoding="utf-8") as fh:
            u, b = scan_text(path, fh.read())
        unsafe.extend(u)
        bare_markers.extend(b)
    for line in unsafe + bare_markers:
        print(line)
    n, m = len(unsafe), len(bare_markers)
    print("verify-gh-api-error-capture: {0} unsafe capture(s), {1} bare "
          "marker(s); {2} failure(s).".format(n, m, n + m))
    return 1 if (n + m) else 0


# --------------------------------------------------------------- self-test

# name, text, expect_fail, must_mention
CASES = [
    ("exits: if ! x=$(...); then exit 1; fi",
     'if ! x=$(gh api "repos/$R/x" --jq .a 2>/dev/null); then\n'
     '  exit 1\n'
     'fi',
     False, ()),

    ("reassigns: if ! x=$(...); then x=\"\"; fi",
     'if ! x=$(gh api "repos/$R/x" --jq .a 2>/dev/null); then\n'
     '  x=""\n'
     'fi',
     False, ()),

    ("loop-exits: if ! x=$(...); then continue; fi inside a for loop",
     'for n in $nums; do\n'
     '  if ! runs=$(gh api -X GET "repos/$R/runs/$n" --jq .a); then\n'
     '    echo "::warning::skip"\n'
     '    continue\n'
     '  fi\n'
     'done',
     False, ()),

    ("the #497 shape: failure branch only logs, never resets or exits",
     'if ! x=$(gh api "repos/$R/x" --jq .a 2>/dev/null); then\n'
     '  echo "::warning::gh api failed"\n'
     'fi',
     True, ("x", "reassign")),

    ("bare capture with no guard at all",
     'x=$(gh api "repos/$R/x" --jq .a 2>/dev/null)',
     True, ("x",)),

    ("pipeline capture with no status test",
     'x=$(gh api "repos/$R/x" --jq .a | jq -s \'.\')',
     True, ("x",)),

    ("exempt marker with a reason: passes",
     'x=$(gh api "repos/$R/x" --jq .a)  '
     '# wc-gh-api-error-exempt: deliberately retaining the error body',
     False, ()),

    ("bare exempt marker with no reason: fails, distinctly",
     'x=$(gh api "repos/$R/x" --jq .a)  # wc-gh-api-error-exempt:',
     True, ("marker", "reason")),

    ("non-covered subcommand: gh issue view is out of scope",
     'x=$(gh issue view "$N" --json state --jq .state)',
     False, ()),

    ("or-fallback that reassigns: x=$(...) || x=default",
     "x=\"$(gh api \"repos/$R/x\" --jq .a 2>/dev/null)\" || x='[]'",
     False, ()),

    ("or-fallback that only swallows status: x=$(...) || true",
     "x=\"$(gh api \"repos/$R/x\" --jq .a 2>/dev/null)\" || true",
     True, ("x",)),

    ("|| true masked INSIDE the substitution: outer form reads as bare",
     'x="$(gh api "repos/$R/x" --jq .a 2>/dev/null || true)"',
     True, ("x",)),

    ("continue with no enclosing loop: not credited as loop-exits",
     'if ! x=$(gh api "repos/$R/x" --jq .a); then\n'
     '  continue\n'
     'fi',
     True, ("x",)),

    ("exits via a locally-defined helper whose body calls exit",
     'fail_infra_on_read() {\n'
     '  echo "::error::$1" >&2\n'
     '  exit 1\n'
     '}\n'
     'if ! x=$(gh api "repos/$R/x" --jq .a); then\n'
     '  fail_infra_on_read "reading x"\n'
     'fi',
     False, ()),
]


class _Mutant:
    """Wraps the real detector functions, letting a mutation swap in a
    weakened variant of one of them for the duration of a self-test run."""

    def __init__(self, find=find_capture_sites, classify=classify_failure_path):
        self.find = find
        self.classify = classify

    def verdicts(self, text):
        out = []
        for site in self.find(text, "fixture.sh"):
            out.append(self.classify(text, site))
        return out


def _no_exit_helpers(text, site):
    """Mutation: never recognise a helper function as an exit."""
    import wc_gh_capture as m
    real = m._exit_helpers
    m._exit_helpers = lambda t: set()
    try:
        return classify_failure_path(text, site)
    finally:
        m._exit_helpers = real


def _no_loop_check(text, site):
    import wc_gh_capture as m
    real = m._inside_loop
    m._inside_loop = lambda t, i: True
    try:
        return classify_failure_path(text, site)
    finally:
        m._inside_loop = real


def _ignore_marker(text, site):
    import wc_gh_capture as m
    real = m._exempt_marker
    m._exempt_marker = lambda t, l: None
    try:
        return classify_failure_path(text, site)
    finally:
        m._exempt_marker = real


MUTATIONS = [
    ("stop recognising exit-helper calls", _no_exit_helpers),
    ("treat every loop-exits candidate as inside a loop", _no_loop_check),
    ("stop honouring the exempt marker", _ignore_marker),
]


def _fires(text):
    unsafe, bare = scan_text("fixture.sh", text)
    return bool(unsafe or bare), "\n".join(unsafe + bare)


def self_test():
    problems = []
    baseline = []
    for name, text, expect_fail, must_mention in CASES:
        fired, output = _fires(text)
        baseline.append(fired)
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
        else:
            print("ok    {0}".format(name))

    print()
    for label, mutate in MUTATIONS:
        flipped = []
        for (name, text, _, _), was_fired in zip(CASES, baseline):
            sites = find_capture_sites(text, "fixture.sh")
            if not sites:
                continue
            mutated_fired = any(
                mutate(text, s).verdict in ("unsafe", "bare-marker")
                for s in sites)
            if mutated_fired != was_fired:
                flipped.append(name)
        if flipped:
            print("killed   {0}  (caught by: {1})".format(
                label, "; ".join(flipped[:2])))
        else:
            problems.append((label, ["mutation survived: no fixture noticed"]))
            print("SURVIVED {0}".format(label))

    print()
    if problems:
        print("::error::verify-gh-api-error-capture self-test: {0} "
              "problem(s).".format(len(problems)))
        return 1
    print("verify-gh-api-error-capture self-test: all {0} fixtures behaved "
          "as specified and all {1} mutations were killed.".format(
              len(CASES), len(MUTATIONS)))
    return 0


def main(argv):
    try:
        sys.stdout.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(
        description="Gate 126 - every gh api capture's failure path is safe")
    ap.add_argument("--self-test", action="store_true",
                    help="run the detector against its fixtures and mutations")
    args = ap.parse_args(argv)
    return self_test() if args.self_test else sweep()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
