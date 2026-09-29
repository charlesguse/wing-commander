#!/usr/bin/env python3
"""Gate 117 -- auto-release's tag-state decision, proven by execution.

Gate 59 (`verify-correlated-release-dispatch.py`) checks 3-5 are textual:
they prove the right constructs appear in the right place, never that
running them produces the right verdict. specs/081-composite-aware-
dispatch-gate T019 closes that gap for check 4 (FR-025) the way Gate 67
already closes it for `auto-release.yml`'s credential step: extract the
REAL "Decide release outcome from tag state" step out of the workflow
with `wc_shell_harness.find_step`, run it with `run_step` against a
stubbed `git` on PATH, and assert `tag-matches` on the shipped step's own
output -- never a hand-typed copy of its logic.

(Gate 88's `dispatch-and-wait-tests/run-tests.sh` is this same runtime-
proof shape for the correlation/wait invariants, checks 3 and 5 --
proving the widened `wing-commander-dispatch-and-wait` composite, not
this job's own step. Gate 117 is check 4's counterpart: the one invariant
FR-027 keeps out of that composite, proven here instead.)

THE THREE SCENARIOS (FR-025)
-----------------------------
1. the tag exists and points at VERIFIED_HEAD -- tag-matches must be true.
2. the tag exists but points elsewhere -- tag-matches must be false.
3. the tag does not exist -- tag-matches must be false.

A mutation swaps the tag comparison for a decision keyed off `correlation`
instead (the shape FR-007/FR-007a forbid: deciding `released` from run
state rather than tag state) and must break at least one scenario above,
so this gate proves it can see the defect it exists for.

USAGE
-----
    python3 .github/scripts/verify-auto-release-tag-state-runtime.py
"""
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_shell_harness import (  # noqa: E402
    find_step, resolve_bash, run_step, use_utf8_stdout)

WORKFLOW = os.path.join(".github", "workflows", "auto-release.yml")
STEP = "Decide release outcome from tag state"
VERSION = "9.9.9"
HEAD = "a" * 40
OTHER = "b" * 40
BASH = None

# Answers the step's two `git` calls from the environment:
#   git fetch origin "refs/tags/<version>:refs/tags/<version>"  -> exit 0, no-op
#   git rev-parse -q --verify "refs/tags/<version>^{commit}"    -> exit 0 iff GIT_STUB_TAG_PRESENT=true
#   git rev-parse "<version>^{commit}"                           -> prints GIT_STUB_TAG_SHA
STUB_GIT = r'''#!/usr/bin/env bash
set -uo pipefail
if [ "$1" = "fetch" ]; then
  exit 0
fi
if [ "$1" = "rev-parse" ]; then
  if [ "$2" = "-q" ]; then
    [ "${GIT_STUB_TAG_PRESENT:-false}" = "true" ] && exit 0
    exit 1
  fi
  printf '%s\n' "${GIT_STUB_TAG_SHA-}"
  exit 0
fi
exit 1
'''

BASE = {
    "VERSION": VERSION,
    "VERIFIED_HEAD": HEAD,
    "CORRELATION": "found",
    "CORRELATED_RUN_ID": "12345",
    "REQUEST_TIME": "2026-01-01T00:00:00Z",
    "DISPATCH_REJECTED": "false",
}

# name, env overrides, expected tag-matches
SCENARIOS = [
    ("tag exists and points at VERIFIED_HEAD",
     {"GIT_STUB_TAG_PRESENT": "true", "GIT_STUB_TAG_SHA": HEAD}, "true"),
    ("tag exists but points elsewhere",
     {"GIT_STUB_TAG_PRESENT": "true", "GIT_STUB_TAG_SHA": OTHER}, "false"),
    ("tag does not exist",
     {"GIT_STUB_TAG_PRESENT": "false", "GIT_STUB_TAG_SHA": ""}, "false"),
]


def run_scenario(script, overrides, tmproot):
    workdir = tempfile.mkdtemp(dir=tmproot)
    runner_temp = tempfile.mkdtemp(dir=tmproot)
    bindir = tempfile.mkdtemp(dir=tmproot)
    git_path = os.path.join(bindir, "git")
    with open(git_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(STUB_GIT)
    os.chmod(git_path, 0o755)
    env = dict(BASE)
    env.update(overrides)
    env["PATH"] = bindir + os.pathsep + os.environ["PATH"]
    try:
        rc, out, outputs, _summary = run_step(BASH, script, workdir, env, runner_temp)
    finally:
        for d in (workdir, runner_temp, bindir):
            shutil.rmtree(d, ignore_errors=True)
    return rc, out, outputs


def suite(script, tmproot):
    failures = []
    for name, overrides, want_tag_matches in SCENARIOS:
        rc, out, outputs = run_scenario(script, overrides, tmproot)
        if rc != 0:
            failures.append(f"{name}: the step exited {rc}, expected 0 -- {out!r}")
            continue
        got = outputs.get("tag-matches")
        if got != want_tag_matches:
            failures.append(f"{name}: tag-matches={got!r}, expected {want_tag_matches!r}")
    return failures


def mut_decide_from_correlation(script):
    """FR-007/FR-007a's forbidden shape: `released` decided from run state
    (here, the correlation outcome) rather than tag state."""
    old = ('tag_matches=false\n'
           'if git rev-parse -q --verify "refs/tags/${VERSION}^{commit}" >/dev/null 2>&1; then\n'
           '  if [ "$(git rev-parse "${VERSION}^{commit}")" = "$VERIFIED_HEAD" ]; then\n'
           '    tag_matches=true\n'
           '  fi\n'
           'fi')
    new = ('tag_matches=false\n'
           'if [ "$CORRELATION" = "found" ]; then\n'
           '  tag_matches=true\n'
           'fi')
    return script.replace(old, new)


MUTATIONS = [
    ("the tag comparison swapped for a correlation-keyed decision",
     mut_decide_from_correlation),
]


def main():
    global BASH
    use_utf8_stdout()
    BASH = resolve_bash()
    if not os.path.isfile(WORKFLOW):
        sys.exit(f"::error::run this from the repository root; {WORKFLOW} not found.")
    step = find_step(WORKFLOW, STEP)
    script = str(step["run"])
    if "${{" in script:
        sys.exit(f"::error file={WORKFLOW}::the extracted run: block contains a "
                 f"${{{{ }}}} expression this harness does not resolve.")

    tmproot = tempfile.mkdtemp()
    failures = []
    try:
        failures = suite(script, tmproot)
        for f in failures:
            print(f"::error::{f}")
        for label, mutate in MUTATIONS:
            mutated = mutate(script)
            if mutated == script:
                print(f"::error::mutation {label!r} changed nothing -- the code it "
                      f"edits was rewritten. Update the mutation so this gate keeps "
                      f"proving it can fail.")
                failures.append(f"mutation inapplicable: {label}")
                continue
            broke = suite(mutated, tmproot)
            if broke:
                print(f"Mutation OK - {label}: {len(broke)} assertion(s) fail.")
            else:
                print(f"::error::MUTATION SURVIVED - {label} broke nothing in this "
                      f"suite, so the suite is not testing that defect. Fix the "
                      f"scenarios, not the mutation.")
                failures.append(f"mutation survived: {label}")
    finally:
        shutil.rmtree(tmproot, ignore_errors=True)

    print(f"Gate 117: {len(SCENARIOS)} scenario(s), {len(MUTATIONS)} mutation(s); "
          f"{len(failures)} failure(s).")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
