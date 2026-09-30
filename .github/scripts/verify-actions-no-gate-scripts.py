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

A composite's test harness or standalone gate script belongs at
.github/scripts/<composite>-tests/ instead, for both reasons above. This
gate makes that placement rule mechanical rather than a convention someone
has to remember -- see wc_gate_registry.unsupported_actions_scripts, which
walks .github/actions/ the same mechanical way gate_scripts() walks
.github/scripts/.

WHAT IT CHECKS
--------------
Calls wc_gate_registry.unsupported_actions_scripts(root), which walks
.github/actions/ (.github/actions/_shared/ excluded -- the one structural
carve-out, FR-014) and returns every run-tests.sh entrypoint, or standalone
verify-*.py/verify-*.sh with no sibling run-tests.sh, at any depth (FR-012).
#877: it also returns a harness under any other name -- a script under a
tests/ (or test/, fixtures/, ...) directory, or named run*/test*, that its
composite's action.yml never invokes. A spec-074 harness named tests/run.sh
was invisible to the run-tests.sh-only rule; a script the action.yml does
run is that composite's helper and is not flagged.
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
    STANDALONE_VERIFY_RE, unsupported_actions_scripts)

SCRIPTS_DIR = ".github/scripts"
THIS_FILE = "verify-actions-no-gate-scripts.py"


def supported_location(offending_path):
    """The .github/scripts/<composite>-tests/<basename> home an offending
    .github/actions/<composite>/... path belongs at instead -- computed
    mechanically from the offending path's own composite-directory name,
    never a lookup table (contracts/enforcement-gate-cli.md Behavior item 2).
    """
    composite = offending_path.split("/")[2]
    basename = offending_path.split("/")[-1]
    return f"{SCRIPTS_DIR}/{composite}-tests/{basename}"


def failure_for(offending_path):
    name = os.path.basename(offending_path)
    if name == "run-tests.sh":
        kind = "test harness entrypoint"
    elif STANDALONE_VERIFY_RE.match(name):
        kind = "standalone gate script"
    else:
        kind = "test harness script its action.yml never invokes"
    supported = supported_location(offending_path)
    return (f"{offending_path} is a {kind} under .github/actions/; gate "
            f"discovery reads only {SCRIPTS_DIR}/, so it belongs at "
            f"{supported} instead. See {THIS_FILE} for why.")


def check(root="."):
    """-> (offenders, failures)."""
    offenders = unsupported_actions_scripts(root)
    return offenders, [failure_for(p) for p in offenders]


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
        ok = (offenders == want
              and all(_assert_contract(p, failures) for p in want))
        return ok, f"got offenders={offenders!r} failures={failures!r}"
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


def _fixture_any_name_harness():
    """#877: a harness under any other name -- tests/run.sh, the spec-074
    shape -- fails, naming the path and the canonical location. The
    composite's action.yml exists and does not invoke it; a comment naming
    the file does not count as an invocation."""
    root = tempfile.mkdtemp(prefix="wc-actions-no-gate-scripts-")
    try:
        path = ".github/actions/widget/tests/run.sh"
        _write(root, ".github/actions/widget/action.yml",
               "name: widget\n# fixtures: tests/run.sh\nruns:\n"
               "  using: composite\n  steps:\n    - run: echo hi\n"
               "      shell: bash\n")
        _write(root, path, "echo hi\n")
        _write(root, ".github/actions/widget/tests/case1/input.json", "{}\n")
        offenders, failures = check(root)
        ok = (offenders == [path] and _assert_contract(path, failures)
              and ".github/scripts/widget-tests/run.sh" in " ".join(failures)
              and "never invokes" in " ".join(failures))
        return ok, f"got offenders={offenders!r} failures={failures!r}"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _fixture_run_star_unreferenced():
    """#877: a run*.sh at the composite's top level that its action.yml
    never invokes fails too -- a harness need not sit under tests/."""
    root = tempfile.mkdtemp(prefix="wc-actions-no-gate-scripts-")
    try:
        path = ".github/actions/widget/run-fixtures.sh"
        _write(root, ".github/actions/widget/action.yml", "name: widget\n")
        _write(root, path, "echo hi\n")
        offenders, failures = check(root)
        ok = offenders == [path] and _assert_contract(path, failures)
        return ok, f"got offenders={offenders!r} failures={failures!r}"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _fixture_invoked_helper_not_flagged():
    """A run.sh the composite's own action.yml invokes (via
    $GITHUB_ACTION_PATH, ${{ github.action_path }}, or its repo path) is
    that composite's helper, not a harness; nor is a script whose name and
    directory look nothing like a harness, nor a non-script fixture file."""
    root = tempfile.mkdtemp(prefix="wc-actions-no-gate-scripts-")
    try:
        _write(root, ".github/actions/widget/action.yml",
               'runs:\n  steps:\n    - run: bash "$GITHUB_ACTION_PATH/run.sh"\n'
               "    - run: bash ${{ github.action_path }}/scripts/test-input.sh\n"
               "    - run: python3 .github/actions/widget/runner.py\n")
        _write(root, ".github/actions/widget/run.sh", "echo hi\n")
        _write(root, ".github/actions/widget/scripts/test-input.sh", "echo hi\n")
        _write(root, ".github/actions/widget/runner.py", "print('hi')\n")
        _write(root, ".github/actions/widget/lib.sh", "echo hi\n")
        _write(root, ".github/actions/_shared/tests/run.sh", "echo hi\n")
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
    ("a standalone verify-widget.py AND verify-widget.sh under "
     ".github/actions/<composite>/ both fail", _fixture_standalone_verify_both),
    ("a helper at .github/actions/_shared/run-tests.sh is not flagged",
     _fixture_shared_not_flagged),
    ("a composite with no harness at all is a clean pass",
     _fixture_no_harness_clean),
    ("a same-shaped violation outside .github/actions/ (e.g. repo root) is "
     "correctly ignored", _fixture_outside_actions_ignored),
    ("#877: a harness under any other name (tests/run.sh) that its "
     "action.yml never invokes fails", _fixture_any_name_harness),
    ("#877: an uninvoked run*.sh at a composite's top level fails",
     _fixture_run_star_unreferenced),
    ("a script its own action.yml invokes, a non-harness-shaped helper, and "
     "a _shared/ script are not flagged", _fixture_invoked_helper_not_flagged),
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
