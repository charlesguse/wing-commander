#!/usr/bin/env python3
"""Gate 119 -- no test harness or standalone gate script lives under .github/actions/.

WHY THIS EXISTS
---------------
wc_gate_registry.gate_scripts() discovers gates under .github/scripts/ only
(FR-001) -- gate discovery reads only that root, so a run-tests.sh harness
or a standalone verify-*.py/verify-*.sh placed under .github/actions/
instead is invisible to it: `python .github/scripts/run-local-gates.py` --
the suite CLAUDE.md's "Before pushing" section tells every contributor to
trust -- would silently not run it, and neither would verify-gate-wiring.py
ever flag it as orphaned, because the file was never in gate_scripts()'s
notion of "a gate" to begin with. Test fixtures also have no business in
that directory: a published composite action's directory tree ships to
every adopter who pins it, and a fixture tree under
.github/actions/<composite>/tests/ would be dead weight nobody there asked
for (constitution VII).

A composite's test harness belongs at .github/scripts/<composite>-tests/
instead, and a standalone gate script at .github/scripts/ itself (where
gate discovery reads top-level verify-*), for both reasons above. This
gate makes that placement rule mechanical rather than a convention someone
has to remember -- see wc_gate_registry.unsupported_actions_scripts, which
walks .github/actions/ the same mechanical way gate_scripts() walks
.github/scripts/.

WHAT IT CHECKS
--------------
Calls wc_gate_registry.unsupported_actions_scripts(root), which walks
.github/actions/ (.github/actions/_shared/ excluded -- the one structural
carve-out, FR-014) and returns every run-tests.sh entrypoint, and, with no
sibling run-tests.sh, every standalone verify-*.py/verify-*.sh, every
test-named file (test_*.py, *_test.sh, *.bats), and every file inside a
composite's tests/, test/, spec/ or __tests__/ directory, fixture data
included, at any depth (FR-012, #877: a harness need not be named
run-tests.sh to be one). A composite's own run.sh outside such a
directory is its runtime entrypoint, not a harness, and is never flagged.

Each failure names a home: .github/scripts/verify-x.py for a standalone
verify-x.py; .github/scripts/<composite>-tests/run-tests.sh for an
entrypoint; for any other file, its path below the deepest directory
holding a flagged entrypoint above it (else below its harness directory),
so a nested tests/sub/run.sh and tests/sub/lib.sh land side by side.
Two entrypoints in one composite both map to run-tests.sh; merging two
harnesses into one is a choice for the author, not this gate.
Every result is an unconditional failure: there is no waiver file and no
legitimate exception to register one in.

Usage:
    python3 .github/scripts/verify-actions-no-gate-scripts.py
    python3 .github/scripts/verify-actions-no-gate-scripts.py --self-test
    python3 .github/scripts/verify-actions-no-gate-scripts.py --root <path>
"""
import argparse
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_gate_registry import (  # noqa: E402
    HARNESS_DIR_NAMES, HARNESS_ENTRYPOINT_NAMES, SUBDIR_ENTRYPOINT, TEST_FILE_RE,
    unsupported_actions_scripts)

SCRIPTS_DIR = ".github/scripts"
THIS_FILE = "verify-actions-no-gate-scripts.py"


def supported_location(offending_path, offenders=()):
    """The .github/scripts/ home an offending .github/actions/<composite>/...
    path belongs at instead -- computed mechanically from the offending
    path's own composite-directory name, never a lookup table
    (contracts/enforcement-gate-cli.md Behavior item 2).

    A standalone verify-* goes to .github/scripts/<basename>: gate
    discovery (wc_gate_registry.gate_scripts) reads top-level verify-* and
    */run-tests.sh only, so a <composite>-tests/verify-x.py would stay
    undiscovered. Everything else is a harness's and goes below
    .github/scripts/<composite>-tests/, relative to its harness root (see
    _harness_root), so files that `source` each other keep their places.
    `offenders` is the whole result set, which locates the entrypoints.
    """
    parts = offending_path.split("/")
    composite = parts[2]
    if _kind(offending_path) == "standalone gate script":
        return f"{SCRIPTS_DIR}/{parts[-1]}"
    # Any entrypoint lands as run-tests.sh: that is the one name gate
    # discovery (wc_gate_registry.gate_scripts) picks up there.
    if _is_entrypoint(parts):
        return f"{SCRIPTS_DIR}/{composite}-tests/{SUBDIR_ENTRYPOINT}"
    rest = parts[_harness_root(parts, offenders):]
    return f"{SCRIPTS_DIR}/{composite}-tests/{'/'.join(rest)}"


def _is_entrypoint(parts):
    """run-tests.sh anywhere, or a run.sh/run inside a harness directory."""
    return (parts[-1] == SUBDIR_ENTRYPOINT
            or (parts[-1] in HARNESS_ENTRYPOINT_NAMES
                and _tests_dir_index(parts) is not None))


def _harness_root(parts, offenders):
    """Index into `parts` where the harness-relative path starts: just
    below the deepest directory holding a flagged entrypoint that contains
    this file (so tests/sub/lib.sh beside tests/sub/run.sh lands beside
    run-tests.sh), else just below its first harness directory (so
    tests/fixtures/case.sh keeps fixtures/), else the basename."""
    entry_dirs = {tuple(o.split("/")[:-1]) for o in offenders
                  if _is_entrypoint(o.split("/"))}
    for i in range(len(parts) - 1, 2, -1):
        if tuple(parts[:i]) in entry_dirs:
            return i
    tests_at = _tests_dir_index(parts)
    return tests_at + 1 if tests_at is not None else len(parts) - 1


def _tests_dir_index(parts):
    """Index of the first harness directory below the composite, or None."""
    for i in range(3, len(parts) - 1):
        if parts[i] in HARNESS_DIR_NAMES:
            return i
    return None


def _kind(offending_path):
    parts = offending_path.split("/")
    if _is_entrypoint(parts):
        return "test harness entrypoint"
    if _tests_dir_index(parts) is not None:
        return "test harness file"
    if TEST_FILE_RE.match(parts[-1]):
        return "test file"
    return "standalone gate script"


def failure_for(offending_path, offenders=()):
    kind = _kind(offending_path)
    supported = supported_location(offending_path, offenders)
    return (f"{offending_path} is a {kind} under .github/actions/; gate "
            f"discovery reads only {SCRIPTS_DIR}/, so it belongs at "
            f"{supported} instead. See {THIS_FILE} for why.")


def check(root="."):
    """-> (offenders, failures)."""
    offenders = unsupported_actions_scripts(root)
    return offenders, [failure_for(p, offenders) for p in offenders]


def main(root="."):
    offenders, failures = check(root)
    for f in failures:
        print(f"::error::verify-actions-no-gate-scripts: {f}")
    print(f"verify-actions-no-gate-scripts: {len(offenders)} unsupported "
          f"location(s) found under .github/actions/; {len(failures)} "
          f"failure(s).")
    return 1 if failures else 0


# ----------------------------------------------------------------------------
# Self-test
# ----------------------------------------------------------------------------
def _write(root, relpath, content):
    full = os.path.join(root, *relpath.split("/"))
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(content)


def _assert_contract(path, failures):
    """FR-006/FR-009: each failing fixture's message names the offending
    path, the supported root, and this gate's own filename -- the
    "Failure message contract" in contracts/enforcement-gate-cli.md."""
    joined = " | ".join(failures)
    return (path in joined and SCRIPTS_DIR + "/" in joined
            and THIS_FILE in joined)


def _fixture_run_tests_direct():
    """A run-tests.sh directly under .github/actions/<composite>/ fails,
    naming the path and the canonical location (research.md D8, first
    bullet)."""
    root = tempfile.mkdtemp(prefix="wc-actions-no-gate-scripts-")
    try:
        path = ".github/actions/widget/run-tests.sh"
        _write(root, path, "echo hi\n")
        offenders, failures = check(root)
        ok = (offenders == [path] and _assert_contract(path, failures)
              and ".github/scripts/widget-tests/run-tests.sh"
              in " ".join(failures))
        return ok, f"got offenders={offenders!r} failures={failures!r}"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _fixture_run_tests_nested():
    """A run-tests.sh two levels deep fails the same way (FR-012's "at any
    depth", research.md D8, second bullet)."""
    root = tempfile.mkdtemp(prefix="wc-actions-no-gate-scripts-")
    try:
        path = ".github/actions/widget/tests/nested/run-tests.sh"
        _write(root, path, "echo hi\n")
        offenders, failures = check(root)
        ok = (offenders == [path] and _assert_contract(path, failures)
              and ".github/scripts/widget-tests/run-tests.sh"
              in " ".join(failures))
        return ok, f"got offenders={offenders!r} failures={failures!r}"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _fixture_run_sh_in_tests():
    """#877: a harness named tests/run.sh, and a helper script beside it,
    both fail; the entrypoint's supported home is run-tests.sh."""
    root = tempfile.mkdtemp(prefix="wc-actions-no-gate-scripts-")
    try:
        run_path = ".github/actions/widget/tests/run.sh"
        helper_path = ".github/actions/widget/tests/helper.py"
        _write(root, run_path, "echo hi\n")
        _write(root, helper_path, "print('hi')\n")
        offenders, failures = check(root)
        joined = " ".join(failures)
        ok = (offenders == sorted([helper_path, run_path])
              and all(_assert_contract(p, failures) for p in (run_path, helper_path))
              and ".github/scripts/widget-tests/run-tests.sh" in joined
              and "test harness file" in joined)
        return ok, f"got offenders={offenders!r} failures={failures!r}"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _fixture_test_dir_bash_nested():
    """#877: a `test/` directory (not only `tests/`) is a harness's, a
    `.bash` script counts, and a file below it keeps its place in the
    supported home."""
    root = tempfile.mkdtemp(prefix="wc-actions-no-gate-scripts-")
    try:
        path = ".github/actions/widget/test/cases/case.bash"
        _write(root, path, "echo hi\n")
        offenders, failures = check(root)
        ok = (offenders == [path] and _assert_contract(path, failures)
              and ".github/scripts/widget-tests/cases/case.bash" in " ".join(failures)
              and "test harness file" in " ".join(failures))
        return ok, f"got offenders={offenders!r} failures={failures!r}"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _fixture_runtime_helper_not_flagged():
    """A composite's own runtime scripts outside any tests/ directory --
    its `run.sh` entrypoint (`${{ github.action_path }}/run.sh`) among
    them -- are not a harness and are not flagged."""
    root = tempfile.mkdtemp(prefix="wc-actions-no-gate-scripts-")
    try:
        _write(root, ".github/actions/widget/render.sh", "echo hi\n")
        _write(root, ".github/actions/widget/run.sh", "echo hi\n")
        _write(root, ".github/actions/widget/lib/run.sh", "echo hi\n")
        offenders, _ = check(root)
        return offenders == [], f"got offenders={offenders!r}"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _fixture_standalone_verify_both():
    """A standalone verify-widget.py AND verify-widget.sh under
    .github/actions/<composite>/ both fail (research.md D8, third
    bullet)."""
    root = tempfile.mkdtemp(prefix="wc-actions-no-gate-scripts-")
    try:
        py_path = ".github/actions/widget/verify-widget.py"
        sh_path = ".github/actions/widget/verify-widget.sh"
        _write(root, py_path, "print('hi')\n")
        _write(root, sh_path, "echo hi\n")
        offenders, failures = check(root)
        want = sorted([py_path, sh_path])
        joined = " ".join(failures)
        # Code review of #939: the advice is a home gate discovery reads
        # (top-level verify-*), never .github/scripts/widget-tests/.
        ok = (offenders == want
              and all(_assert_contract(p, failures) for p in want)
              and "belongs at .github/scripts/verify-widget.py " in joined
              and "belongs at .github/scripts/verify-widget.sh " in joined
              and "widget-tests" not in joined)
        return ok, f"got offenders={offenders!r} failures={failures!r}"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _home_of(failures, path):
    """The `belongs at <home>` a failure names for `path`, or None."""
    for f in failures:
        if f.startswith(path + " "):
            return f.split(" belongs at ", 1)[1].split(" instead.", 1)[0]
    return None


def _fixture_test_shapes():
    """Code review of #939: test-named files beside action.yml, a .bats
    file, an extensionless tests/run, fixture data under tests/, and
    spec/ and __tests__/ directories are all caught, each with a home
    below .github/scripts/widget-tests/."""
    root = tempfile.mkdtemp(prefix="wc-actions-no-gate-scripts-")
    try:
        _write(root, ".github/actions/widget/action.yml", "name: widget\n")
        want = {
            ".github/actions/widget/test_widget.py": "test_widget.py",
            ".github/actions/widget/widget_test.sh": "widget_test.sh",
            ".github/actions/widget/widget.bats": "widget.bats",
            ".github/actions/widget/tests/run": "run-tests.sh",
            ".github/actions/widget/tests/case.bats": "case.bats",
            ".github/actions/widget/tests/fixtures/event.json": "fixtures/event.json",
            ".github/actions/widget/spec/widget_spec.rb": "widget_spec.rb",
            ".github/actions/widget/__tests__/widget.test.js": "widget.test.js",
        }
        for path in want:
            _write(root, path, "x\n")
        offenders, failures = check(root)
        got = {p: _home_of(failures, p) for p in want}
        ok = (offenders == sorted(want)
              and all(_assert_contract(p, failures) for p in want)
              and all(got[p] == f"{SCRIPTS_DIR}/widget-tests/{h}"
                      for p, h in want.items()))
        return ok, f"got offenders={offenders!r} homes={got!r}"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _fixture_nested_harness_one_home():
    """Code review of #939: a nested harness's entrypoint and the files
    beside and below it share one home, so a relative `source` between
    tests/sub/run.sh and tests/sub/lib.sh still resolves after the move."""
    root = tempfile.mkdtemp(prefix="wc-actions-no-gate-scripts-")
    try:
        want = {
            ".github/actions/widget/tests/sub/run.sh": "run-tests.sh",
            ".github/actions/widget/tests/sub/lib.sh": "lib.sh",
            ".github/actions/widget/tests/sub/data/case.json": "data/case.json",
        }
        for path in want:
            _write(root, path, "x\n")
        offenders, failures = check(root)
        got = {p: _home_of(failures, p) for p in want}
        ok = (offenders == sorted(want)
              and all(got[p] == f"{SCRIPTS_DIR}/widget-tests/{h}"
                      for p, h in want.items()))
        return ok, f"got offenders={offenders!r} homes={got!r}"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _fixture_shared_not_flagged():
    """A helper at .github/actions/_shared/run-tests.sh is NOT flagged --
    the carve-out is structural (research.md D8, fourth bullet; spec.md
    Acceptance Scenario 3, Story 2)."""
    root = tempfile.mkdtemp(prefix="wc-actions-no-gate-scripts-")
    try:
        _write(root, ".github/actions/_shared/run-tests.sh", "echo hi\n")
        offenders, _ = check(root)
        return offenders == [], f"got offenders={offenders!r}"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _fixture_no_harness_clean():
    """A composite with no harness at all is a clean pass (research.md D8,
    fifth bullet)."""
    root = tempfile.mkdtemp(prefix="wc-actions-no-gate-scripts-")
    try:
        _write(root, ".github/actions/widget/action.yml", "name: widget\n")
        offenders, _ = check(root)
        return offenders == [], f"got offenders={offenders!r}"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _fixture_outside_actions_ignored():
    """The walk is rooted at <root>/.github/actions specifically: a
    same-shaped violation placed outside that directory (e.g. repo root) is
    correctly ignored (research.md D8, sixth bullet)."""
    root = tempfile.mkdtemp(prefix="wc-actions-no-gate-scripts-")
    try:
        _write(root, "run-tests.sh", "echo hi\n")
        offenders, _ = check(root)
        return offenders == [], f"got offenders={offenders!r}"
    finally:
        shutil.rmtree(root, ignore_errors=True)


# Each entry: (name, fixture_fn), fixture_fn() -> (ok: bool, detail: str).
# A fixture builds and tears down its own tempdir, so a FAILing fixture never
# leaves scratch state for the next one to trip over.
FIXTURES = [
    ("a run-tests.sh directly under .github/actions/<composite>/ fails, "
     "naming the path and the canonical location", _fixture_run_tests_direct),
    ("a run-tests.sh two levels deep fails the same way (FR-012 'at any "
     "depth')", _fixture_run_tests_nested),
    ("a harness named tests/run.sh and a script beside it both fail (#877)",
     _fixture_run_sh_in_tests),
    ("a .bash script under a test/ directory fails, keeping its place "
     "below it in the supported home (#877)", _fixture_test_dir_bash_nested),
    ("a composite's runtime scripts outside tests/, its own run.sh "
     "included, are not flagged", _fixture_runtime_helper_not_flagged),
    ("a standalone verify-widget.py AND verify-widget.sh under "
     ".github/actions/<composite>/ both fail, each told to move to "
     ".github/scripts/", _fixture_standalone_verify_both),
    ("test-named files, .bats, an extensionless tests/run, fixture data, "
     "and spec/ and __tests__/ directories fail (code review of #939)",
     _fixture_test_shapes),
    ("a nested harness's files share one home with its entrypoint (code "
     "review of #939)", _fixture_nested_harness_one_home),
    ("a helper at .github/actions/_shared/run-tests.sh is not flagged",
     _fixture_shared_not_flagged),
    ("a composite with no harness at all is a clean pass",
     _fixture_no_harness_clean),
    ("a same-shaped violation outside .github/actions/ (e.g. repo root) is "
     "correctly ignored", _fixture_outside_actions_ignored),
]


def self_test():
    bad = 0
    for name, fixture_fn in FIXTURES:
        ok, detail = fixture_fn()
        if ok:
            print(f"[ok] {name}")
        else:
            bad += 1
            print(f"[FAIL] {name}: {detail}")
    print(f"verify-actions-no-gate-scripts self-test: "
          f"{len(FIXTURES) - bad}/{len(FIXTURES)} fixtures behaved as "
          f"specified.")
    return 1 if bad else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="No test harness or standalone gate script lives under "
                    ".github/actions/ (outside _shared/).")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--root", default=".")
    cli_args = parser.parse_args()
    sys.exit(self_test() if cli_args.self_test else main(cli_args.root))
