#!/usr/bin/env python3
"""Self-test for lint-workflows.yml's Gate 16.

Gate 16 passing against a healthy fleet proves nothing: a gate that never
fires is indistinguishable from one whose detection logic is broken. Gate 5
exists because a verifier sat green for weeks while checking a code path
that did not ship, so every detector here carries one of these.

The defect Gate 16 exists for: `anthropics/claude-code-action` writes its
transcript to ${{ runner.temp }}/claude-execution-output.json, and an upload
step with no status-check function inherits `success()` — so the log is
dropped on exactly the runs where the agent failed. auto-update-spec-kit's
`e2e-stage` agent shipped with no upload at all; its read-back reports "the
agent step did not complete" without ever looking inside, so a failure left
nothing at all to diagnose from.

The two false-positive cases matter as much as the detections. Two upload
shapes are both in the fleet and both legitimate — a job-wide catch-all
(`if: always()`, no per-step key) and a per-agent upload keyed on
`steps.<id>.outcome != 'skipped'` — and a gate that rejected either would
be reverted rather than obeyed.

Drift-proofing: the gate's source is EXTRACTED from lint-workflows.yml at
run time rather than copied here, so there is no second copy to fall out of
sync.

Usage: python3 .github/scripts/verify-gate-16.py
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
STEP_PREFIX = "Gate 16"


def extract_gate(path=LINT_WORKFLOW):
    """Return Gate 16's python source, read out of the shipped workflow."""
    return extract_gate_step(path, STEP_PREFIX, "verify-gate-16")


# ---------------------------------------------------------------- fixtures
#
# Tiny and self-contained rather than mutations of the real fleet: the real
# files change for unrelated reasons, and a self-test that breaks on every
# unrelated edit gets deleted rather than fixed.

LOG_PATH = "${{ runner.temp }}/claude-execution-output.json"


def agent(step_id, name="Run the agent"):
    return {"name": name, "id": step_id,
            "uses": "anthropics/claude-code-action@v1",
            "continue-on-error": True}


def upload(cond, name="Upload Claude execution log"):
    step = {"name": name, "uses": "actions/upload-artifact@v4",
            "with": {"name": "claude-execution-output", "path": LOG_PATH,
                     "if-no-files-found": "ignore"}}
    if cond is not None:
        step["if"] = cond
    return step


def wf(steps, published=True):
    """A one-job workflow, published (workflow_call) unless told otherwise."""
    on = {"workflow_call": {}} if published else {"workflow_dispatch": {}}
    doc = {"name": "fixture", "on": on,
           "jobs": {"stage": {"runs-on": "ubuntu-latest",
                              "steps": [{"name": "Checkout",
                                         "uses": "actions/checkout@v5"}] + steps}}}
    return yaml.safe_dump(doc, sort_keys=False)


KEYED = "always() && steps.{}.outcome != 'skipped'"
GATED_KEYED = ("steps.lifecycle-gate.outputs.is-open == 'true' && always() && "
               "steps.{}.outcome != 'skipped'")

CASES = [
    # name, files, expect_fail, must_mention

    ("the real defect: an agent step with no upload anywhere in the job",
     {"w.yml": wf([agent("decide")])},
     True, ("w.yml", "'decide'", "'stage'", "no step in this job uploads it at all")),

    ("the fix: a keyed upload with always()",
     {"w.yml": wf([agent("decide"), upload(KEYED.format("decide"))])},
     False, ()),

    ("no false positive: the job-wide catch-all shape (always(), no key)",
     {"w.yml": wf([agent("agent-auto"), agent("agent-pr"), upload("always()")])},
     False, ()),

    ("no false positive: a lifecycle-gated keyed upload is still guarded",
     {"w.yml": wf([agent("cycle"), upload(GATED_KEYED.format("cycle"))])},
     False, ()),

    ("an upload with no status-check function is dropped on the failure path",
     {"w.yml": wf([agent("decide"),
                   upload("steps.decide.outcome != 'skipped'")])},
     True, ("'decide'", "no status-check function")),

    ("a bare upload with no `if` at all inherits success()",
     {"w.yml": wf([agent("decide"), upload(None)])},
     True, ("'decide'",)),

    ("a second agent added to an already-covered job goes uncaptured",
     {"w.yml": wf([agent("cycle"), upload(KEYED.format("cycle")),
                   agent("retry"), upload(KEYED.format("retry")),
                   agent("progress")])},
     True, ("'progress'", "keyed to other steps")),

    ("all three covered: the same job once the third upload lands",
     {"w.yml": wf([agent("cycle"), upload(KEYED.format("cycle")),
                   agent("retry"), upload(KEYED.format("retry")),
                   agent("progress"), upload(KEYED.format("progress"))])},
     False, ()),

    ("no false positive: an upload of some other artifact does not count",
     {"w.yml": wf([agent("decide"),
                   {"name": "Upload the bundle", "if": "always()",
                    "uses": "actions/upload-artifact@v4",
                    "with": {"name": "bundle", "path": "x/prepare.bundle"}}])},
     True, ("'decide'", "no step in this job uploads it at all")),

    ("no false positive: an unpublished workflow is out of scope",
     {"w.yml": wf([agent("claude")], published=False)},
     False, ()),

    ("no false positive: a published stage with no agent step at all",
     {"w.yml": wf([{"name": "Deterministic check", "run": "echo hi"}])},
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
    root = tempfile.mkdtemp(prefix="verify_gate16_")
    gate_path = os.path.join(root, "gate16.py")
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
        print(f"::error file={LINT_WORKFLOW}::Gate 16 self-test: "
              f"{len(failures)} of {len(CASES)} scenarios behaved wrongly. Gate 16's "
              f"detection logic does not do what its name claims, so a green Gate 16 "
              f"on the real fleet means nothing.")
        return 1
    print(f"Gate 16 self-test: all {len(CASES)} scenarios behaved as expected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
