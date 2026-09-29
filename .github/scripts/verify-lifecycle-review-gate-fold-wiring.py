#!/usr/bin/env python3
"""Gate 109 - lifecycle-review-gate.yml's `disposition` job never carries a
wing-commander-fold-commit call without the findings-partition step that
feeds it, or vice versa (specs/062-lifecycle-review-gate T041).

WHY THIS EXISTS
---------------
Mirroring Gate 72's per-step (not whole-file) discipline: a future edit
that drops the partition step while leaving the fold-commit call in place
would fold garbage (an unrendered or stale section-file); dropping the
fold-commit call while leaving partition in place would silently strand
every not-clean round's in-scope findings, never folding them despite the
partition step having computed exactly what to fold. Nothing else keeps
these two in lockstep.

Usage: python3 .github/scripts/verify-lifecycle-review-gate-fold-wiring.py
"""
import os
import sys

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_shell_harness import use_utf8_stdout  # noqa: E402

WORKFLOW = ".github/workflows/lifecycle-review-gate.yml"
JOB = "disposition"
PARTITION_STEP = "Partition, dedup, and render this round's findings"
FOLD_COMMIT_USES = "wing-commander-fold-commit"


def _steps():
    doc = yaml.safe_load(open(WORKFLOW, encoding="utf-8")) or {}
    job = (doc.get("jobs") or {}).get(JOB)
    if job is None:
        sys.exit(f"::error file={WORKFLOW}::no job keyed {JOB!r}.")
    return job.get("steps") or []


def check(steps):
    has_partition = any((s or {}).get("name") == PARTITION_STEP for s in steps)
    has_fold_commit = any(FOLD_COMMIT_USES in str((s or {}).get("uses") or "")
                          for s in steps)
    failures = []
    if has_fold_commit and not has_partition:
        failures.append(
            f"{WORKFLOW}: {JOB!r} calls {FOLD_COMMIT_USES} but has no "
            f"{PARTITION_STEP!r} step -- it would fold whatever a stale or "
            f"missing section-file happens to contain.")
    if has_partition and not has_fold_commit:
        failures.append(
            f"{WORKFLOW}: {JOB!r} has a {PARTITION_STEP!r} step but never "
            f"calls {FOLD_COMMIT_USES} -- every not-clean round's in-scope "
            f"findings would be computed and then silently stranded.")
    return failures


def self_test():
    use_utf8_stdout()
    steps = _steps()
    failures = 0

    def check_case(name, cond, detail=""):
        nonlocal failures
        if cond:
            print(f"PASS {name}")
        else:
            failures += 1
            print(f"FAIL {name} {detail}")

    real = check(steps)
    check_case("the shipped disposition job has neither side missing",
              not real, f"real failures: {real!r}")

    no_partition = [s for s in steps if (s or {}).get("name") != PARTITION_STEP]
    caught = check(no_partition)
    check_case("a fold-commit call with no partition step is caught",
              len(caught) == 1)

    no_fold_commit = [s for s in steps
                      if FOLD_COMMIT_USES not in str((s or {}).get("uses") or "")]
    caught2 = check(no_fold_commit)
    check_case("a partition step with no fold-commit call is caught",
              len(caught2) == 1)

    print(f"{failures} failure(s).")
    return 1 if failures else 0


def main(argv):
    use_utf8_stdout()
    if argv == ["--self-test"]:
        return self_test()
    if argv:
        sys.exit(f"unknown arguments {argv!r}; takes --self-test or nothing.")
    failures = check(_steps())
    for f in failures:
        print(f"::error::{f}")
    print(f"Gate 109: {len(failures)} failure(s).")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
