#!/usr/bin/env python3
"""Self-test for lint-workflows.yml's Gate 3.

Gate 3 passing against a healthy workflow fleet proves nothing: a gate that
never fires is indistinguishable from one whose detection logic is broken.
#880 is that failure mode: the gate compared only the called workflow's
TOP-LEVEL permissions, and only by key NAME, so PR #821 passed it with a
caller granting `actions: read` to a called workflow whose top level was
`permissions: {}` and whose `guard` job asked for `actions: write`.

So this script feeds Gate 3 synthetic workflow trees that each contain one
known defect (or one known NON-defect) and asserts the verdict and the
error text. The gate's source is EXTRACTED from lint-workflows.yml at run
time (wc_lint_gate_source), not copied, so there is no second copy to drift.

Usage: python3 .github/scripts/verify-gate-3.py
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_lint_gate_source import LINT_WORKFLOW, extract_gate_step  # noqa: E402

STEP_PREFIX = "Gate 3 —"  # the em dash keeps Gates 30-39 and the self-test step out


def caller(job_perms=None, wf_perms=None, uses="./.github/workflows/called.yml"):
    """A wrapper with one `call` job. Each *_perms is the literal YAML body
    placed after `permissions:` (e.g. " read-all" or "\\n  actions: read")."""
    top = f"permissions:{wf_perms}\n" if wf_perms is not None else ""
    job = f"    permissions:{job_perms}\n" if job_perms is not None else ""
    return (f"name: wrapper\non:\n  workflow_dispatch: {{}}\n{top}"
            f"jobs:\n  call:\n{job}    uses: {uses}\n")


def called(wf_perms=None, job_perms=None):
    """A reusable workflow with one `guard` job; same *_perms convention."""
    top = f"permissions:{wf_perms}\n" if wf_perms is not None else ""
    job = f"    permissions:{job_perms}\n" if job_perms is not None else ""
    return (f"name: called\non:\n  workflow_call: {{}}\n{top}"
            f"jobs:\n  guard:\n    runs-on: ubuntu-latest\n{job}"
            f"    steps:\n      - run: echo hi\n")


A_WRITE = "\n      actions: write"
A_READ = "\n      actions: read"
A_WRITE_TOP = "\n  actions: write"
A_READ_TOP = "\n  actions: read"
A_WRITE_ISSUES_READ = "\n      actions: write\n      issues: read"

CASES = [
    # name, files, expect_fail, must_mention
    ("healthy: the caller grants exactly what the called job asks for",
     {"wrapper.yml": caller(job_perms=A_WRITE),
      "called.yml": called(wf_perms=" {}", job_perms=A_WRITE)},
     False, ()),

    ("mutation (a), the #821 shape: the caller's grant downgraded from write "
     "to read, the called job still asking for write, behind `permissions: {}`",
     {"wrapper.yml": caller(job_perms=A_READ),
      "called.yml": called(wf_perms=" {}", job_perms=A_WRITE)},
     True, ("wrapper.yml", "'call'", "'guard'", "actions", "write (granted read)")),

    ("mutation (b): the called job asks for a key the caller does not grant",
     {"wrapper.yml": caller(job_perms=A_WRITE),
      "called.yml": called(job_perms=A_WRITE_ISSUES_READ)},
     True, ("wrapper.yml", "'guard'", "issues", "read (granted none)")),

    ("the old top-level check still holds: top level asks for more than granted",
     {"wrapper.yml": caller(job_perms=A_READ),
      "called.yml": called(wf_perms=A_WRITE_TOP)},
     True, ("top-level", "actions")),

    ("a called job with no block of its own inherits the called top level",
     {"wrapper.yml": caller(job_perms=A_WRITE),
      "called.yml": called(wf_perms=A_WRITE_TOP)},
     False, ()),

    ("a calling job with no block is held to its workflow's top level",
     {"wrapper.yml": caller(wf_perms=A_READ_TOP),
      "called.yml": called(job_perms=A_WRITE)},
     True, ("top-level permissions: does not grant", "actions")),

    ("the calling job's own block wins over its workflow's top level",
     {"wrapper.yml": caller(job_perms=A_WRITE, wf_perms=" {}"),
      "called.yml": called(job_perms=A_WRITE)},
     False, ()),

    ("no grant anywhere inherits the repository default: not resolvable, skipped",
     {"wrapper.yml": caller(),
      "called.yml": called(job_perms=A_WRITE)},
     False, ()),

    ("an empty-map grant grants nothing",
     {"wrapper.yml": caller(job_perms=" {}"),
      "called.yml": called(job_perms=A_READ)},
     True, ("actions", "read (granted none)")),

    ("an empty-map request asks for nothing",
     {"wrapper.yml": caller(job_perms=" {}"),
      "called.yml": called(wf_perms=" {}", job_perms=" {}")},
     False, ()),

    ("write-all satisfies any request",
     {"wrapper.yml": caller(job_perms=" write-all"),
      "called.yml": called(job_perms=A_WRITE_ISSUES_READ)},
     False, ()),

    ("read-all satisfies a read request",
     {"wrapper.yml": caller(job_perms=" read-all"),
      "called.yml": called(job_perms=A_READ)},
     False, ()),

    ("read-all does not satisfy a write request",
     {"wrapper.yml": caller(job_perms=" read-all"),
      "called.yml": called(job_perms=A_WRITE)},
     True, ("actions", "write (granted read)")),

    ("read-all grants no id-token, which has no read level",
     {"wrapper.yml": caller(job_perms=" read-all"),
      "called.yml": called(job_perms="\n      id-token: write")},
     True, ("id-token", "write (granted none)")),

    ("a called job asking for write-all needs more than an explicit map grants",
     {"wrapper.yml": caller(job_perms=A_WRITE),
      "called.yml": called(job_perms=" write-all")},
     True, ("contents", "write (granted none)")),

    ("an unresolvable local callee is reported, not silently skipped",
     {"wrapper.yml": caller(job_perms=A_WRITE, uses="./.github/workflows/typo.yml"),
      "called.yml": called(job_perms=A_WRITE)},
     True, ("does not exist",)),
]


def main():
    if not os.path.isfile(LINT_WORKFLOW):
        sys.exit(f"::error::run this from the repository root; {LINT_WORKFLOW} not found.")

    gate_src = extract_gate_step(STEP_PREFIX)
    root = tempfile.mkdtemp(prefix="verify_gate3_")
    gate_path = os.path.join(root, "gate3.py")
    io.open(gate_path, "w", encoding="utf-8").write(gate_src)

    failures = []
    try:
        for name, files, expect_fail, must_mention in CASES:
            case_dir = tempfile.mkdtemp(prefix="case_", dir=root)
            wf_dir = os.path.join(case_dir, ".github", "workflows")
            os.makedirs(wf_dir)
            for fname, body in files.items():
                io.open(os.path.join(wf_dir, fname), "w", encoding="utf-8").write(body)

            proc = subprocess.run([sys.executable, gate_path], cwd=case_dir,
                                  capture_output=True, text=True,
                                  encoding="utf-8", errors="replace")
            out = (proc.stdout or "") + (proc.stderr or "")
            fired = proc.returncode != 0

            problems = []
            if fired != expect_fail:
                problems.append(
                    f"expected the gate to {'FAIL' if expect_fail else 'PASS'}, "
                    f"it {'FAILED' if fired else 'PASSED'}")
            for token in must_mention:
                if token not in out:
                    problems.append(f"error text never mentions {token!r}")

            if problems:
                failures.append((name, problems, out.strip()))
                print(f"FAIL  {name}")
                for p in problems:
                    print(f"        - {p}")
                for line in out.strip().splitlines():
                    print(f"        | {line}")
            else:
                print(f"ok    {name}")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    print()
    if failures:
        print(f"::error file={LINT_WORKFLOW}::Gate 3 self-test: "
              f"{len(failures)} of {len(CASES)} scenarios behaved wrongly. Gate 3's "
              f"detection logic does not do what its name claims, so a green Gate 3 "
              f"on the real fleet means nothing.")
        return 1
    print(f"Gate 3 self-test: all {len(CASES)} scenarios behaved as expected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
