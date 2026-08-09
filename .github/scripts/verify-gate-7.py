#!/usr/bin/env python3
"""Self-test for lint-workflows.yml's Gate 7.

Gate 7 asserts that every job of every published stage carries the
`environment:` binding (specs/031-stage-environment-binding, FR-004). The
fleet it guards is uniform today and should stay that way, so the gate will
print "0 failure(s)" forever — whether its detection works or not. Gate 5
exists in the same file because that exact failure mode already happened
here: a verifier sat green for weeks while checking a code path that did
not ship.

So this script feeds Gate 7 synthetic stage files that each carry one known
defect (or one known NON-defect) and asserts the verdict, including what the
error text names.

Drift-proofing: the gate's source is EXTRACTED from lint-workflows.yml at
run time rather than copied here, so there is no second copy to fall out of
sync. (verify-gate-6.py does the same thing; the extractor is duplicated
rather than shared because a module whose filename contains hyphens cannot
be imported.)

Usage: python3 .github/scripts/verify-gate-7.py
"""
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

import yaml

LINT_WORKFLOW = ".github/workflows/lint-workflows.yml"
STEP_PREFIX = "Gate 7"
HEREDOC_OPEN = "python3 - <<'PYEOF'"
HEREDOC_CLOSE = "PYEOF"


def extract_gate(path=LINT_WORKFLOW):
    """Return Gate 7's python source, read out of the shipped workflow."""
    wf = yaml.safe_load(io.open(path, encoding="utf-8")) or {}
    run = None
    for job in (wf.get("jobs") or {}).values():
        for step in (job or {}).get("steps") or []:
            name = (step or {}).get("name", "")
            if name.startswith(STEP_PREFIX) and "self-test" not in name:
                run = step.get("run")
    if run is None:
        sys.exit(f"::error file={path}::verify-gate-7 could not find a step named "
                 f"{STEP_PREFIX!r}. If it was renamed, update this script and the "
                 f"workflow together.")

    lines = run.splitlines()
    try:
        start = next(i for i, l in enumerate(lines) if l.strip() == HEREDOC_OPEN)
        end = next(i for i, l in enumerate(lines)
                   if i > start and l.strip() == HEREDOC_CLOSE)
    except StopIteration:
        sys.exit(f"::error file={path}::verify-gate-7 found the {STEP_PREFIX} step but "
                 f"not the {HEREDOC_OPEN} ... {HEREDOC_CLOSE} block it keys on — the "
                 f"step's shape has changed.")
    return "\n".join(lines[start + 1:end]) + "\n"


# ---------------------------------------------------------------- fixtures
#
# Tiny and self-contained rather than mutated copies of the real stages: the
# real files change for unrelated reasons, and a self-test that breaks on
# every unrelated edit gets deleted rather than fixed.

INPUTS_OK = """\
    inputs:
      environment:
        type: string
        required: false
        default: ""
      environment-deployment:
        type: boolean
        required: false
        default: true
"""

INPUTS_WRONG_DEFAULT = INPUTS_OK.replace("default: true", "default: false")

INPUTS_MISSING = ""

BOUND = """\
    environment:
      name: ${{ inputs.environment }}
      deployment: ${{ inputs.environment-deployment }}
"""

# Same binding, no whitespace inside the expressions — the gate compares the
# input a value forwards, not the byte string, so this must still pass.
BOUND_TIGHT = """\
    environment:
      name: ${{inputs.environment}}
      deployment: ${{inputs.environment-deployment}}
"""

BOUND_NO_DEPLOYMENT = """\
    environment:
      name: ${{ inputs.environment }}
"""

BOUND_SHORTHAND = """\
    environment: ${{ inputs.environment }}
"""

BOUND_LITERAL_NAME = """\
    environment:
      name: production
      deployment: ${{ inputs.environment-deployment }}
"""

BOUND_WRONG_INPUT = """\
    environment:
      name: ${{ inputs.environment }}
      deployment: ${{ inputs.environment }}
"""

UNBOUND = ""


def job(name, binding):
    return f"  {name}:\n    runs-on: ubuntu-latest\n{binding}"\
           f"    steps:\n      - run: echo work\n"


def stage(*jobs, inputs=INPUTS_OK):
    return (f"name: stage\non:\n  workflow_call:\n{inputs}"
            f"jobs:\n{''.join(jobs)}")


PLAIN_WORKFLOW = """\
name: not a stage
on:
  pull_request: {}
jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - run: echo no binding here, and none wanted
"""

CALLER_JOB = """\
  call-other:
    uses: ./.github/workflows/other.yml
"""

CASES = [
    # name, files, expect_fail, must_mention
    ("healthy: every job of the stage is bound",
     {"stage.yml": stage(job("first", BOUND), job("second", BOUND))},
     False, ()),

    ("the defect this gate exists for: one job of two is unbound",
     {"stage.yml": stage(job("first", BOUND), job("second", UNBOUND))},
     True, ("'second'", "no environment")),

    ("every job unbound",
     {"stage.yml": stage(job("only", UNBOUND))},
     True, ("'only'",)),

    ("shorthand string form cannot carry the deployment sub-key",
     {"stage.yml": stage(job("only", BOUND_SHORTHAND))},
     True, ("'only'", "shorthand")),

    ("mapping form missing the deployment sub-key",
     {"stage.yml": stage(job("only", BOUND_NO_DEPLOYMENT))},
     True, ("'only'", "deployment")),

    ("name hardcoded instead of forwarding the input",
     {"stage.yml": stage(job("only", BOUND_LITERAL_NAME))},
     True, ("'only'", "name")),

    ("deployment forwards the wrong input",
     {"stage.yml": stage(job("only", BOUND_WRONG_INPUT))},
     True, ("'only'", "deployment")),

    ("no false positive: expressions without inner whitespace",
     {"stage.yml": stage(job("only", BOUND_TIGHT))},
     False, ()),

    ("jobs bound but the inputs are never declared",
     {"stage.yml": stage(job("only", BOUND), inputs=INPUTS_MISSING)},
     True, ("environment-deployment", "does not declare")),

    ("a changed input default is a contract change, not a detail",
     {"stage.yml": stage(job("only", BOUND), inputs=INPUTS_WRONG_DEFAULT)},
     True, ("environment-deployment", "default")),

    ("no false positive: a workflow that is not a published stage",
     {"lint.yml": PLAIN_WORKFLOW},
     True, ("checked nothing",)),   # no stage at all — the gate must say so

    ("no false positive: a non-stage workflow alongside a healthy stage",
     {"lint.yml": PLAIN_WORKFLOW, "stage.yml": stage(job("only", BOUND))},
     False, ()),

    ("no false positive: a job that calls another workflow is not bindable",
     {"stage.yml": stage(job("only", BOUND)) + CALLER_JOB},
     False, ()),

    ("a stage declaring workflow_call with no inputs at all is still a stage",
     {"stage.yml": "name: stage\non:\n  workflow_call:\njobs:\n"
                   + job("only", BOUND)},
     True, ("does not declare",)),
]


def check_derivations_agree(gate_path):
    """Gate 7's inline stage detection vs the one release.yml uses.

    Two places need to know which workflows are published stages: this gate
    (which checks their bindings on every PR) and release.yml's actionlint
    pass (which is the only pre-release lint watchdog.yml and
    auto-update-spec-kit.yml get). They must not answer differently — a
    stage visible to one and invisible to the other is exactly issue #149,
    where a file went unlinted for a whole release while the gate reported
    success.

    So release.yml calls wc_published_stages.py, and this asserts that module
    still agrees with the gate's own inline logic on the real repository.
    Comparing on the real fleet rather than on a fixture is deliberate: a
    fixture would only ever exercise the shapes someone thought to write
    down, and the shapes nobody thought of are the whole risk.
    """
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    try:
        from wc_published_stages import published_stages
    except ImportError as exc:
        return [("shared stage derivation", [f"cannot import "
                 f"wc_published_stages ({exc}); release.yml's pass 1 depends "
                 f"on it"], "")]

    module_stages = published_stages()
    proc = subprocess.run([sys.executable, gate_path], cwd=".",
                          capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    out = (proc.stdout or "") + (proc.stderr or "")
    m = re.search(r"Gate 7: (\d+) published stage\(s\)", out)
    if not m:
        return [("shared stage derivation",
                 ["could not read the stage count out of Gate 7's own output; "
                  "its summary line has changed shape"], out.strip())]

    gate_count = int(m.group(1))
    if gate_count != len(module_stages):
        return [("shared stage derivation", [
            f"Gate 7 sees {gate_count} published stage(s) but "
            f"wc_published_stages.py (which release.yml's actionlint pass "
            f"uses) sees {len(module_stages)}: {module_stages}. One of them "
            f"is about to check a file the other does not know exists."], "")]
    print(f"ok    the shared stage derivation agrees with Gate 7 "
          f"({gate_count} published stages)")
    return []


def main():
    if not os.path.isfile(LINT_WORKFLOW):
        sys.exit(f"::error::run this from the repository root; {LINT_WORKFLOW} not found.")

    gate_src = extract_gate()
    root = tempfile.mkdtemp(prefix="verify_gate7_")
    gate_path = os.path.join(root, "gate7.py")
    io.open(gate_path, "w", encoding="utf-8").write(gate_src)

    failures = []
    failures += check_derivations_agree(gate_path)
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
        print(f"::error file={LINT_WORKFLOW}::Gate 7 self-test: "
              f"{len(failures)} of {len(CASES)} scenarios behaved wrongly. Gate 7's "
              f"detection logic does not do what its name claims, so a green Gate 7 "
              f"on the real fleet means nothing.")
        return 1
    print(f"Gate 7 self-test: all {len(CASES)} scenarios behaved as expected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
