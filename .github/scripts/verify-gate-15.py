#!/usr/bin/env python3
"""Self-test for lint-workflows.yml's Gate 15.

Gate 15 passing against a healthy fleet proves nothing: a gate that never
fires is indistinguishable from one whose detection logic is broken. Gate 5
exists because a verifier sat green for weeks while checking a code path
that did not ship, so every detector here carries one of these.

The defect Gate 15 exists for was invisible to every other gate:
auto-update-spec-kit.yml's `prepare` and `verify` had no status-check
function, so GitHub suppressed them through the needs-closure of an
`always()`-gated `evaluate-path` before their `if` was ever evaluated. The
adopt path did nothing while every run stayed green.

Drift-proofing: the gate's source is EXTRACTED from lint-workflows.yml at
run time rather than copied here, so there is no second copy to fall out of
sync.

Usage: python3 .github/scripts/verify-gate-15.py
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile

import yaml

LINT_WORKFLOW = ".github/workflows/lint-workflows.yml"
STEP_PREFIX = "Gate 15"
HEREDOC_OPEN = "python3 - <<'PYEOF'"
HEREDOC_CLOSE = "PYEOF"


def extract_gate(path=LINT_WORKFLOW):
    """Return Gate 15's python source, read out of the shipped workflow."""
    wf = yaml.safe_load(io.open(path, encoding="utf-8")) or {}
    run = None
    for job in (wf.get("jobs") or {}).values():
        for step in (job or {}).get("steps") or []:
            name = (step or {}).get("name", "")
            if name.startswith(STEP_PREFIX) and "self-test" not in name:
                run = step.get("run")
    if run is None:
        sys.exit(f"::error file={path}::verify-gate-15 could not find a step named "
                 f"{STEP_PREFIX!r}. If it was renamed, update this script and the "
                 f"workflow together.")

    lines = run.splitlines()
    try:
        start = next(i for i, l in enumerate(lines) if l.strip() == HEREDOC_OPEN)
        end = next(i for i, l in enumerate(lines)
                   if i > start and l.strip() == HEREDOC_CLOSE)
    except StopIteration:
        sys.exit(f"::error file={path}::verify-gate-15 found the {STEP_PREFIX} step but "
                 f"not the {HEREDOC_OPEN} ... {HEREDOC_CLOSE} block it keys on — the "
                 f"step's shape has changed.")
    return "\n".join(lines[start + 1:end]) + "\n"


# ---------------------------------------------------------------- fixtures
#
# Tiny and self-contained rather than mutations of the real fleet: the real
# files change for unrelated reasons, and a self-test that breaks on every
# unrelated edit gets deleted rather than fixed.

ALWAYS_IF = ("always() && ((needs.a.result == 'success') || "
             "(needs.b.result == 'success'))")


def wf(jobs):
    """Build a one-file workflow from (name, needs, if) triples."""
    out = ["name: fixture", "on:", "  workflow_dispatch: {}", "jobs:"]
    for name, needs, cond in jobs:
        out.append(f"  {name}:")
        if needs:
            out.append(f"    needs: [{', '.join(needs)}]")
        if cond:
            out.append(f"    if: {cond}")
        out.append("    runs-on: ubuntu-latest")
        out.append("    steps:")
        out.append("      - run: echo hi")
    return "\n".join(out) + "\n"


# The real chain, reduced: `b` never runs on this path, `mid` survives it
# with always(), and `tail` is whatever we are testing.
def chain(tail_if, tail2_if=None):
    jobs = [
        ("a", [], None),
        ("b", [], "false"),
        ("mid", ["a", "b"], ALWAYS_IF),
        ("tail", ["mid"], tail_if),
    ]
    if tail2_if is not None:
        jobs.append(("tail2", ["tail"], tail2_if))
    return wf(jobs)


CASES = [
    # name, files, expect_fail, must_mention
    ("the real defect: unguarded job downstream of an always() job",
     {"w.yml": chain("needs.mid.result == 'success' && "
                     "needs.mid.outputs.outcome == 'clean-bump'")},
     True, ("w.yml", "'tail'", "'mid'", "always() &&")),

    ("the fix: the same job with always() prefixed",
     {"w.yml": chain("always() && needs.mid.result == 'success' && "
                     "needs.mid.outputs.outcome == 'clean-bump'")},
     False, ()),

    ("a job with no `if` at all is suppressed just the same",
     {"w.yml": chain(None)},
     True, ("w.yml", "'tail'")),

    ("guarding only the first descendant moves the silence one job down",
     {"w.yml": chain("always() && needs.mid.result == 'success'",
                     "needs.tail.result == 'success'")},
     True, ("'tail2'",)),

    ("both descendants guarded: the chain is whole",
     {"w.yml": chain("always() && needs.mid.result == 'success'",
                     "always() && needs.tail.result == 'success'")},
     False, ()),

    ("success() counts as a status-check function too",
     {"w.yml": chain("success() && needs.mid.outputs.outcome == 'clean-bump'")},
     False, ()),

    ("no false positive: an ordinary chain with no always() anywhere",
     {"w.yml": wf([("a", [], None),
                   ("c", ["a"], "needs.a.result == 'success'"),
                   ("d", ["c"], "needs.c.result == 'success'")])},
     False, ()),

    ("no false positive: a lone conditional job with no dependents",
     {"w.yml": wf([("only", [], "always() && github.event_name == 'push'")])},
     False, ()),
]


def main():
    # Same reason as PYTHONIOENCODING below — a cp1252 console must not turn
    # a reported failure into a UnicodeEncodeError traceback that hides it.
    try:
        sys.stdout.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass
    if not os.path.isfile(LINT_WORKFLOW):
        sys.exit(f"::error::run this from the repository root; {LINT_WORKFLOW} not found.")

    gate_src = extract_gate()
    root = tempfile.mkdtemp(prefix="verify_gate15_")
    gate_path = os.path.join(root, "gate15.py")
    io.open(gate_path, "w", encoding="utf-8").write(gate_src)

    failures = []
    try:
        for name, files, expect_fail, must_mention in CASES:
            case_dir = tempfile.mkdtemp(prefix="case_", dir=root)
            wf_dir = os.path.join(case_dir, ".github", "workflows")
            os.makedirs(wf_dir)
            for fname, body in files.items():
                io.open(os.path.join(wf_dir, fname), "w", encoding="utf-8").write(body)

            # This repository is developed on Windows, where the child would
            # otherwise write its error text in cp1252 and every non-ASCII
            # character would come back as U+FFFD.
            env = dict(os.environ, PYTHONIOENCODING="utf-8")
            proc = subprocess.run([sys.executable, gate_path], cwd=case_dir,
                                  capture_output=True, text=True, env=env,
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
        print(f"::error file={LINT_WORKFLOW}::Gate 15 self-test: "
              f"{len(failures)} of {len(CASES)} scenarios behaved wrongly. Gate 15's "
              f"detection logic does not do what its name claims, so a green Gate 15 "
              f"on the real fleet means nothing.")
        return 1
    print(f"Gate 15 self-test: all {len(CASES)} scenarios behaved as expected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
