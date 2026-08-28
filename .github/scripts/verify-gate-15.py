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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_lint_gate_source import extract_gate_step  # noqa: E402

LINT_WORKFLOW = ".github/workflows/lint-workflows.yml"
STEP_PREFIX = "Gate 15"


def extract_gate(path=LINT_WORKFLOW):
    """Return Gate 15's python source, read out of the shipped workflow."""
    return extract_gate_step(path, STEP_PREFIX, "verify-gate-15")


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

    # --- second rule: an `if` arm that can never be read (#224) ----------
    #
    # The chain above is not the only way a job goes silent. specs/038 gave
    # every stage a `verify-image-prerequisites` job skip-conditioned on a
    # plain `if: inputs.container-image != ''` — no status-check function, so
    # invisible to the walk above — and had its dependents "tolerate" the
    # skip with `result == 'skipped'`. GitHub never read that arm: the
    # implicit success() over needs had already skipped those jobs. Eleven
    # stages ran as no-ops for a day and every run stayed green.

    ("the second defect: an if: arm for a skipped need, with no status "
     "function to make it readable",
     {"w.yml": wf([("check", [], "inputs.image != ''"),
                   ("entry", ["check"],
                    "needs.check.result == 'success' || "
                    "needs.check.result == 'skipped'")])},
     True, ("'entry'", "implicit success()", "!cancelled()")),

    ("the fix: the same arm under always()",
     {"w.yml": wf([("check", [], "inputs.image != ''"),
                   ("entry", ["check"],
                    "always() && (needs.check.result == 'success' || "
                    "needs.check.result == 'skipped')")])},
     False, ()),

    ("the fix: the same arm under !cancelled() (quoted — a leading `!` is a "
     "YAML anchor)",
     {"w.yml": wf([("check", [], "inputs.image != ''"),
                   ("entry", ["check"],
                    '"!cancelled() && (needs.check.result == \'success\' || '
                    'needs.check.result == \'skipped\')"')])},
     False, ()),

    ("a failure arm is unreadable for the same reason",
     {"w.yml": wf([("a", [], None),
                   ("b", ["a"], "needs.a.result == 'failure'")])},
     True, ("'b'",)),

    ("no false positive: an ordinary success-only guard needs no status "
     "function",
     {"w.yml": wf([("a", [], None),
                   ("b", ["a"], "needs.a.result == 'success'")])},
     False, ()),

    # --- specs/041-implement-stall-notice: the output-based cousin -------
    #
    # `stalled`'s pre-fix condition was `needs.implement.outputs.final-ok ==
    # 'false'` — an OUTPUT comparison, not a `.result` comparison, so it was
    # invisible to NON_SUCCESS_ARM's original pattern even though it carries
    # the identical tell: it only means something when the entry job did NOT
    # succeed, and has no status-check function of its own. These three
    # cases are the regression proof (FR-015) — the defect this whole
    # feature exists to fix must be mechanically detectable going forward,
    # not merely observed once and fixed by hand.

    ("the regression: stalled's actual pre-fix condition (output-based, no "
     "status function)",
     {"w.yml": wf([("a", [], None),
                   ("b", ["a"], "needs.a.outputs.final-ok == 'false'")])},
     True, ("'b'",)),

    ("the fix: the same output-based condition with !cancelled() prefixed",
     {"w.yml": wf([("a", [], None),
                   ("b", ["a"],
                    '"!cancelled() && needs.a.outputs.final-ok == \'false\'"')])},
     False, ()),

    ("regression guard: an existing-style .result comparison is still "
     "flagged after the widening",
     {"w.yml": wf([("a", [], None),
                   ("b", ["a"], "needs.a.result == 'skipped'")])},
     True, ("'b'",)),
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
