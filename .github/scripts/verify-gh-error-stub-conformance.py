#!/usr/bin/env python3
"""Gate 127 - every gh-error-simulating stub in a covered-capture harness
uses the one shared home.

WHY THIS EXISTS
---------------
A harness gate that executes a shipped `run:` block against a stubbed `gh`
only proves anything if the stub fails the way real `gh` does: the JSON
error body on stdout, the human-readable line on stderr, exit 1 (#497).
Before this feature, each such harness hand-wrote that two-channel shape
itself (`verify-auto-release-specs-fallback.py`'s own STUB_GH did, twice,
in one file) -- exactly the "pasted until the first divergent fix" shape
CLAUDE.md's single-home rule forbids. wc_shell_harness.gh_error_stub_arm is
now the one home (specs/091-gh-api-error-capture); this gate keeps it that
way.

THREE INDEPENDENT CHECKS
-------------------------
1. Every harness-driven gate whose shipped subject block contains a
   covered `gh api` capture (the FR-015 retrofit set, research.md D7,
   derived by re-running wc_gh_capture's own scanner against each such
   harness's extracted `run:` text -- never a hand-maintained list) must
   route its gh-error simulation through `gh_error_stub_arm`, not a
   hand-rolled literal.
2. Independent of retrofit-set membership: the canonical JSON-error-body
   literal shape must not appear anywhere under `.github/scripts/` other
   than inside `wc_shell_harness.py` itself -- a hand-rolled duplicate is
   a violation regardless of which gate wrote it (research.md D8).
3. Stub builders quote a value into the stub's shell text with
   `shlex.quote`, never a hand-rolled `"'" + s.replace("'", ...) + "'"`
   helper: four harnesses carried their own copy until #889 moved them
   onto the standard library. Every `.py` and `.sh` under
   `.github/scripts/` is scanned.

Usage:
    python3 .github/scripts/verify-gh-error-stub-conformance.py
    python3 .github/scripts/verify-gh-error-stub-conformance.py --self-test
"""
import argparse
import glob
import importlib.util
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wc_gate_registry  # noqa: E402
import wc_shell_harness  # noqa: E402
from wc_gh_capture import find_capture_sites  # noqa: E402

SCRIPTS_DIR = ".github/scripts"
HARNESS_MODULE = "wc_shell_harness.py"

# This gate's own self-test fixtures necessarily quote the canonical
# literal shape as an example of what to catch (Gate 28's own docstring
# examples have the same self-reference problem) -- excluded from the
# duplicate-literal sweep the same way wc_shell_harness.py is, as the one
# other file allowed to contain the shape verbatim.
SELF_MODULE = os.path.basename(__file__)

# `find_step(<workflow-or-action-path>, <step-name>)` -- the shape every
# harness in the tree already calls to pull its own subject text out of the
# shipped workflow, per wc_shell_harness.extract_quoted_var's own docstring
# precedent of reading the live text rather than a hand-typed copy.
FIND_STEP_CALL_RE = re.compile(
    r"find_step\(\s*([A-Za-z_][A-Za-z0-9_.]*|\"[^\"]*\"|'[^']*')\s*,\s*"
    r"([A-Za-z_][A-Za-z0-9_.]*|\"[^\"]*\"|'[^']*')\s*\)")

# The canonical gh error-response shape: message, documentation_url,
# status, in that order -- specific enough that an unrelated JSON blob
# elsewhere in the tree (several gates print "message"/"status" fields for
# their OWN verdicts) does not false-positive.
JSON_ERROR_LITERAL_RE = re.compile(
    r'"message"\s*:\s*"[^"]*"\s*,\s*"documentation_url"\s*:\s*"[^"]*"\s*,\s*'
    r'"status"\s*:\s*"?\d+"?')


# The hand-rolled POSIX single-quote idiom: replace each `'` with `'\''`.
HAND_QUOTE_RE = re.compile(r"""\.replace\(\s*"'"\s*,\s*"'\\\\''"\s*\)""")


def posix(path):
    return path.replace(os.sep, "/")


def _resolve(token, module):
    token = token.strip()
    if token[:1] in "\"'":
        return token[1:-1]
    return getattr(module, token, None)


def _load_module(path):
    name = "wc_gh_error_stub_conformance_subject_" + re.sub(
        r"[^A-Za-z0-9_]", "_", path)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception:  # noqa: BLE001 - a subject module's own import cost
        return None     # is not this gate's concern; treat as unresolvable
    return module


def subject_text(path, source, module):
    """Every `run:` text this harness's own `find_step(...)` calls name."""
    texts = []
    for m in FIND_STEP_CALL_RE.finditer(source):
        wf = _resolve(m.group(1), module)
        step_name = _resolve(m.group(2), module)
        if not isinstance(wf, str) or not isinstance(step_name, str):
            continue
        if not os.path.isfile(wf):
            continue
        try:
            step = wc_shell_harness.find_step(wf, step_name)
        except SystemExit:
            continue
        if step and step.get("run"):
            texts.append(str(step["run"]))
    return "\n".join(texts)


def gh_stubbing_scripts(scripts):
    """Every gate script that stubs `gh` (STUB_GH*-shaped constant)."""
    out = []
    for path in scripts:
        if not path.endswith(".py"):
            continue
        with open(path, encoding="utf-8") as fh:
            source = fh.read()
        if "STUB_GH" in source:
            out.append((path, source))
    return out


def derive_retrofit_set(scripts):
    """[(path, source)] members: gh-stubbing scripts whose own subject
    `run:` text contains at least one covered `gh api` capture."""
    members = []
    for path, source in gh_stubbing_scripts(scripts):
        module = _load_module(path)
        if module is None:
            continue
        text = subject_text(path, source, module)
        if find_capture_sites(text, path):
            members.append((path, source))
    return members


def duplicate_literal_hits(paths):
    """(path, line) for every canonical error-literal occurrence outside
    wc_shell_harness.py."""
    hits = []
    for path in paths:
        if os.path.basename(path) in (HARNESS_MODULE, SELF_MODULE):
            continue
        with open(path, encoding="utf-8") as fh:
            for i, line in enumerate(fh, 1):
                if JSON_ERROR_LITERAL_RE.search(line):
                    hits.append((path, i))
    return hits


def hand_quote_hits(paths):
    """(path, line) for every hand-rolled shell-quote helper."""
    hits = []
    for path in paths:
        if os.path.basename(path) == SELF_MODULE:
            continue
        with open(path, encoding="utf-8") as fh:
            for i, line in enumerate(fh, 1):
                if HAND_QUOTE_RE.search(line):
                    hits.append((path, i))
    return hits


def hand_quote_messages(paths):
    return [
        "::error file={0},line={1}::Gate 127: this hand-rolled shell-quote "
        "helper duplicates the standard library - call shlex.quote(...) "
        "instead.".format(posix(path), line)
        for path, line in hand_quote_hits(paths)]


def evaluate(scripts, all_py_paths):
    """(members, non_conforming_messages, duplicate_messages)."""
    members = derive_retrofit_set(scripts)
    member_paths = set(p for p, _ in members)
    non_conforming, duplicates = [], []
    for path, line in duplicate_literal_hits(all_py_paths):
        if path in member_paths:
            non_conforming.append(
                "::error file={0},line={1}::Gate 127: this gate script "
                "hand-writes the gh error-response literal instead of "
                "calling wc_shell_harness.gh_error_stub_arm(...).".format(
                    posix(path), line))
        else:
            duplicates.append(
                "::error file={0},line={1}::Gate 127: this gh "
                "error-response literal duplicates the one canonical shape "
                "in wc_shell_harness.py - call gh_error_stub_arm(...) "
                "instead.".format(posix(path), line))
    return members, non_conforming, duplicates


LINT_WORKFLOW = ".github/workflows/lint-workflows.yml"


def sweep():
    if not os.path.isfile(LINT_WORKFLOW):
        sys.exit("::error::run this from the repository root; {0} not "
                 "found.".format(LINT_WORKFLOW))
    scripts = wc_gate_registry.gate_scripts()
    all_py = sorted(glob.glob(os.path.join(SCRIPTS_DIR, "**", "*.py"),
                              recursive=True))
    all_sh = sorted(glob.glob(os.path.join(SCRIPTS_DIR, "**", "*.sh"),
                              recursive=True))
    members, non_conforming, duplicates = evaluate(scripts, all_py)
    hand_quotes = hand_quote_messages(all_py + all_sh)
    for line in non_conforming + duplicates + hand_quotes:
        print(line)
    n, d, q = len(non_conforming), len(duplicates), len(hand_quotes)
    print("verify-gh-error-stub-conformance: {0} retrofit member(s) "
          "checked, {1} non-conforming stub(s), {2} duplicate literal(s), "
          "{3} hand-rolled shell quote(s); {4} failure(s).".format(
              len(members), n, d, q, n + d + q))
    return 1 if (n + d + q) else 0


# --------------------------------------------------------------- self-test

_FIXTURE_WF_WITH_CAPTURE = """
on: push
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - name: subject
        run: |
          x=$(gh api "repos/$R/x" --jq .a)
"""

_FIXTURE_WF_NO_CAPTURE = """
on: push
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - name: subject
        run: |
          echo hi
"""

_BAD_STUB_SOURCE = """
import wc_shell_harness

WORKFLOW = {workflow!r}
STEP = "subject"

STUB_GH = '''#!/usr/bin/env bash
case "$*" in
  *)
    printf '%s\\n' '{{"message":"Not Found","documentation_url":"https://docs.github.com/rest","status":"404"}}'
    exit 1
    ;;
esac
'''


def build_stub():
    return wc_shell_harness.find_step(WORKFLOW, STEP), STUB_GH
"""

_GOOD_STUB_SOURCE = """
import wc_shell_harness

WORKFLOW = {workflow!r}
STEP = "subject"

STUB_GH = ('''#!/usr/bin/env bash
case "$*" in
  *)
'''
    + wc_shell_harness.gh_error_stub_arm("*", "404", "Not Found")
    + '''    ;;
esac
''')


def build_stub():
    return wc_shell_harness.find_step(WORKFLOW, STEP), STUB_GH
"""

_NONMEMBER_SOURCE = """
import wc_shell_harness

WORKFLOW = {workflow!r}
STEP = "subject"
STUB_GH = 'case "$*" in *) exit 0 ;; esac\\n'


def build_stub():
    return wc_shell_harness.find_step(WORKFLOW, STEP)
"""

_UNRELATED_DUPLICATE_SOURCE = '''
# not a harness at all -- just a script that happens to hand-write the
# canonical error shape somewhere, e.g. a copy-pasted fixture.
LITERAL = '{"message":"Not Found","documentation_url":"https://docs.github.com/rest","status":"404"}'
'''


_HAND_QUOTE_PY_SOURCE = """
def shell_quote(s):
    return "'" + s.replace("'", "'\\\\''") + "'"
"""

_HAND_QUOTE_SH_SOURCE = """#!/usr/bin/env bash
python3 - <<'PY'
def _sq(text):
    return "'" + text.replace("'", "'\\\\''") + "'"
PY
"""

_SHLEX_QUOTE_SOURCE = """
import shlex
STUB = "d=" + shlex.quote("/tmp/it's")
"""


def self_test():
    problems = []
    with tempfile.TemporaryDirectory() as tmp:
        wf_capture = os.path.join(tmp, "wf_capture.yml")
        wf_no_capture = os.path.join(tmp, "wf_no_capture.yml")
        with open(wf_capture, "w", encoding="utf-8") as fh:
            fh.write(_FIXTURE_WF_WITH_CAPTURE)
        with open(wf_no_capture, "w", encoding="utf-8") as fh:
            fh.write(_FIXTURE_WF_NO_CAPTURE)

        bad = os.path.join(tmp, "gate_bad.py")
        good = os.path.join(tmp, "gate_good.py")
        nonmember = os.path.join(tmp, "gate_nonmember.py")
        dup = os.path.join(tmp, "unrelated_dup.py")
        with open(bad, "w", encoding="utf-8") as fh:
            fh.write(_BAD_STUB_SOURCE.format(workflow=wf_capture))
        with open(good, "w", encoding="utf-8") as fh:
            fh.write(_GOOD_STUB_SOURCE.format(workflow=wf_capture))
        with open(nonmember, "w", encoding="utf-8") as fh:
            fh.write(_NONMEMBER_SOURCE.format(workflow=wf_no_capture))
        with open(dup, "w", encoding="utf-8") as fh:
            fh.write(_UNRELATED_DUPLICATE_SOURCE)

        scripts = [bad, good, nonmember, dup]
        members, non_conforming, duplicates = evaluate(scripts, scripts)
        member_paths = set(p for p, _ in members)

        checks = [
            ("a harness whose subject block has a covered capture is a "
             "retrofit-set member",
             bad in member_paths and good in member_paths),
            ("a harness whose subject block has no covered capture is "
             "excluded from the retrofit set",
             nonmember not in member_paths),
            ("a fixture stub that hand-writes the literal fails, naming "
             "the fixture gate",
             any(bad in msg and "gh_error_stub_arm" in msg
                 for msg in non_conforming)),
            ("a fixture stub that calls gh_error_stub_arm(...) does not "
             "fail",
             not any(good in msg for msg in non_conforming + duplicates)),
            ("a duplicate literal outside wc_shell_harness.py, in a "
             "non-member file, fails as a duplicate (not a stub failure)",
             any(dup in msg and "wc_shell_harness.py" in msg
                 for msg in duplicates)
             and not any(dup in msg for msg in non_conforming)),
        ]
        quote_py = os.path.join(tmp, "gate_quote.py")
        quote_sh = os.path.join(tmp, "gate_quote.sh")
        shlex_ok = os.path.join(tmp, "gate_shlex.py")
        for path, source in ((quote_py, _HAND_QUOTE_PY_SOURCE),
                             (quote_sh, _HAND_QUOTE_SH_SOURCE),
                             (shlex_ok, _SHLEX_QUOTE_SOURCE)):
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(source)
        quoted = hand_quote_messages([quote_py, quote_sh, shlex_ok])
        checks += [
            ("a hand-rolled shell-quote helper in a .py fails, naming "
             "shlex.quote",
             any(quote_py in msg and "shlex.quote" in msg for msg in quoted)),
            ("a hand-rolled shell-quote helper in a .sh's Python fails",
             any(quote_sh in msg for msg in quoted)),
            ("a script calling shlex.quote(...) does not fail",
             not any(shlex_ok in msg for msg in quoted)),
        ]
        for name, ok in checks:
            if ok:
                print("ok    {0}".format(name))
            else:
                print("FAIL  {0}".format(name))
                problems.append(name)

    # Cross-harness proof (SC-004): verify-auto-release-specs-fallback.py's
    # own MUTATIONS (#482's regression, and the B1 uncleared-slug shape the
    # #482 code review found) are re-derived from the REAL shipped
    # auto-release.yml text on every run of its own main() -- if this
    # feature's migration onto gh_error_stub_arm had weakened the stub's
    # realism, that harness's own mutation proof would stop catching them
    # and its main() would report a survived mutation (non-zero exit).
    name = ("the migrated verify-auto-release-specs-fallback.py still "
            "catches its own #482/B1 mutations (SC-004)")
    try:
        import importlib
        mod = importlib.import_module("verify-auto-release-specs-fallback")
    except ImportError:
        spec = importlib.util.spec_from_file_location(
            "wc_gh_error_stub_conformance_fallback_check",
            os.path.join(SCRIPTS_DIR, "verify-auto-release-specs-fallback.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    rc = mod.main()
    if rc == 0:
        print("ok    {0}".format(name))
    else:
        print("FAIL  {0}".format(name))
        problems.append(name)

    print()
    if problems:
        print("::error::verify-gh-error-stub-conformance self-test: {0} "
              "problem(s).".format(len(problems)))
        return 1
    print("verify-gh-error-stub-conformance self-test: all fixtures "
          "behaved as specified.")
    return 0


def main(argv):
    try:
        sys.stdout.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(
        description="Gate 127 - every gh-error stub uses the shared home")
    ap.add_argument("--self-test", action="store_true",
                    help="run the detector against its fixtures")
    args = ap.parse_args(argv)
    return self_test() if args.self_test else sweep()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
