#!/usr/bin/env python3
"""Self-test for lint-workflows.yml's Gate 22.

Gate 22 asserts that every job of every published stage carries the
runner/container-image passthrough block (specs/038-runner-container-
passthrough, FR-001-FR-004, FR-007, FR-009). The fleet it guards is uniform
today and should stay that way, so the gate will print "0 failure(s)"
forever — whether its detection works or not. Gate 7's self-test exists for
the same reason applied to specs/031's environment binding; this mirrors it.

So this script feeds Gate 22 synthetic stage files that each carry one known
defect (or one known NON-defect) and asserts the verdict, including what the
error text names.

Drift-proofing: the gate's source is EXTRACTED from lint-workflows.yml at run
time rather than copied here, so there is no second copy to fall out of sync
(same technique as verify-gate-6.py / verify-gate-7.py).

Usage: python3 .github/scripts/verify-gate-22.py
"""
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_lint_gate_source import extract_gate_step  # noqa: E402

LINT_WORKFLOW = ".github/workflows/lint-workflows.yml"
STEP_PREFIX = "Gate 22"


def extract_gate(path=LINT_WORKFLOW):
    """Return Gate 22's python source, read out of the shipped workflow."""
    return extract_gate_step(path, STEP_PREFIX)


# ---------------------------------------------------------------- fixtures
#
# Tiny and self-contained rather than mutated copies of the real stages: the
# real files change for unrelated reasons, and a self-test that breaks on
# every unrelated edit gets deleted rather than fixed.

INPUTS_OK = """\
    inputs:
      runner:
        type: string
        required: false
        default: ubuntu-latest
      container-image:
        type: string
        required: false
        default: ""
    secrets:
      container-registry-username:
        required: false
      container-registry-password:
        required: false
"""

INPUTS_WRONG_DEFAULT = INPUTS_OK.replace("default: ubuntu-latest", "default: self-hosted")

INPUTS_MISSING = ""

SECRET_REQUIRED_TRUE = INPUTS_OK.replace(
    "container-registry-password:\n        required: false",
    "container-registry-password:\n        required: true",
)

BOUND = """\
    runs-on: ${{ startsWith(inputs.runner, '[') && fromJSON(inputs.runner) || inputs.runner }}
    container:
      image: ${{ inputs.container-image }}
"""

# Same binding, no whitespace inside the expressions — the gate compares the
# input/secret a value forwards, not the byte string, so this must still pass.
BOUND_TIGHT = """\
    runs-on: ${{startsWith(inputs.runner, '[') && fromJSON(inputs.runner) || inputs.runner}}
    container:
      image: ${{inputs.container-image}}
"""

BOUND_NO_CONTAINER = """\
    runs-on: ${{ startsWith(inputs.runner, '[') && fromJSON(inputs.runner) || inputs.runner }}
"""

BOUND_NO_CREDENTIALS = """\
    runs-on: ${{ startsWith(inputs.runner, '[') && fromJSON(inputs.runner) || inputs.runner }}
    container:
      image: ${{ inputs.container-image }}
"""

BOUND_LITERAL_IMAGE = """\
    runs-on: ${{ startsWith(inputs.runner, '[') && fromJSON(inputs.runner) || inputs.runner }}
    container:
      image: python:3.12
"""

BOUND_PLAIN_RUNS_ON = """\
    runs-on: ubuntu-latest
    container:
      image: ${{ inputs.container-image }}
"""

# Any credentials: mapping at all is the defect now (PR #226): the key
# cannot be conditionally absent, and an empty value stops the job before
# its first step.
BOUND_WITH_CREDENTIALS = """\
    runs-on: ${{ startsWith(inputs.runner, '[') && fromJSON(inputs.runner) || inputs.runner }}
    container:
      image: ${{ inputs.container-image }}
      credentials:
        username: ${{ secrets.container-registry-username }}
        password: ${{ secrets.container-registry-password }}
"""

UNBOUND = ""

# Deliberately non-forwarding container.image, mirroring what a registered
# Gate 22 exception would look like (none exist yet — contract's own
# statement — so this fixture only exercises the exception-table mechanism
# itself, not a real deviation).
BOUND_MATRIX_LEG = """\
    runs-on: my-runner
    container:
      image: pinned-image:latest
"""


# The one job Gate 22 special-cases: no container: of its own (it invokes
# Docker directly on the runner, before any other job's container exists),
# but the runner ternary like every other job, and a zero permission grant
# DECLARED rather than inherited from whatever the file's top-level
# permissions happen to be.
PREREQ_OK = """\
    permissions: {}
    runs-on: ${{ startsWith(inputs.runner, '[') && fromJSON(inputs.runner) || inputs.runner }}
"""

PREREQ_NO_PERMISSIONS = """\
    runs-on: ${{ startsWith(inputs.runner, '[') && fromJSON(inputs.runner) || inputs.runner }}
"""

PREREQ_WIDE_PERMISSIONS = """\
    permissions:
      contents: write
      issues: write
    runs-on: ${{ startsWith(inputs.runner, '[') && fromJSON(inputs.runner) || inputs.runner }}
"""

PREREQ_PINNED_RUNNER = """\
    permissions: {}
    runs-on: ubuntu-latest
"""


def job(name, binding):
    return f"  {name}:\n{binding}    steps:\n      - run: echo work\n"


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
     True, ("'second'",)),

    ("every job unbound",
     {"stage.yml": stage(job("only", UNBOUND))},
     True, ("'only'",)),

    ("no false positive: expressions without inner whitespace",
     {"stage.yml": stage(job("only", BOUND_TIGHT))},
     False, ()),

    ("job has runs-on: but no container: block at all",
     {"stage.yml": stage(job("only", BOUND_NO_CONTAINER))},
     True, ("'only'", "no container")),

    ("no false positive: a container: block with no credentials: mapping is "
     "the required shape",
     {"stage.yml": stage(job("only", BOUND_NO_CREDENTIALS))},
     False, ()),

    ("container.image hardcoded instead of forwarding the input",
     {"stage.yml": stage(job("only", BOUND_LITERAL_IMAGE))},
     True, ("'only'", "container.image")),

    ("runs-on: is a plain string instead of the passthrough ternary",
     {"stage.yml": stage(job("only", BOUND_PLAIN_RUNS_ON))},
     True, ("'only'", "runs-on")),

    ("the PR #226 defect: a credentials: mapping stops every job that names "
     "no image before its first step",
     {"stage.yml": stage(job("only", BOUND_WITH_CREDENTIALS))},
     True, ("'only'", "credentials")),

    ("jobs bound but the inputs are never declared",
     {"stage.yml": stage(job("only", BOUND), inputs=INPUTS_MISSING)},
     True, ("runner", "does not declare")),

    ("a changed input default is a contract change, not a detail",
     {"stage.yml": stage(job("only", BOUND), inputs=INPUTS_WRONG_DEFAULT)},
     True, ("runner", "default")),

    ("a registry secret declared required: true breaks the inert-by-default contract",
     {"stage.yml": stage(job("only", BOUND), inputs=SECRET_REQUIRED_TRUE)},
     True, ("container-registry-password", "required: false")),

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

    # Constitution VII: an EXCEPTIONS entry, if one ever exists, must not
    # read as "any job with this shape passes" or "any job in this file
    # passes" — but Gate 22 ships with an EMPTY EXCEPTIONS dict (contract:
    # "none exist yet at plan time"), so a deviating job must fail exactly
    # like any other unbound job, with no registered escape hatch yet.
    ("no exception is registered yet, so a deviating job still fails "
     "even in a file/job name that would plausibly be exempted later",
     {"pr-conversation.yml": stage(job("act", BOUND_MATRIX_LEG))},
     True, ("'act'",)),

    # The verify-image-prerequisites carve-out. Gate 22 exempts this job
    # from the container: check — it must invoke Docker on the runner, not
    # inside a container — but not from the runner ternary, and it requires
    # the zero grant to be declared on the job rather than inherited.
    ("healthy: the special-cased verify-image-prerequisites job",
     {"stage.yml": stage(job("first", BOUND),
                         job("verify-image-prerequisites", PREREQ_OK))},
     False, ()),

    ("verify-image-prerequisites with no permissions: block silently "
     "inherits the file's top-level grants",
     {"stage.yml": stage(job("first", BOUND),
                         job("verify-image-prerequisites",
                             PREREQ_NO_PERMISSIONS))},
     True, ("verify-image-prerequisites", "permissions")),

    ("verify-image-prerequisites with a non-empty grant",
     {"stage.yml": stage(job("first", BOUND),
                         job("verify-image-prerequisites",
                             PREREQ_WIDE_PERMISSIONS))},
     True, ("verify-image-prerequisites", "permissions")),

    ("the carve-out excuses the container: block, not the runner ternary",
     {"stage.yml": stage(job("first", BOUND),
                         job("verify-image-prerequisites",
                             PREREQ_PINNED_RUNNER))},
     True, ("verify-image-prerequisites", "runs-on")),

    ("the carve-out is job-name-scoped: another job cannot skip its "
     "container: block by wearing the same shape",
     {"stage.yml": stage(job("first", BOUND),
                         job("other", PREREQ_NO_PERMISSIONS))},
     True, ("'other'", "container")),
]


def norm(path):
    """A workflow path in the one spelling both derivations can be compared in.

    glob joins with os.sep, so the same file is `.github/workflows/x.yml` on
    the runner and `.github/workflows\\x.yml` locally — a difference that would
    make every path look like a disagreement on Windows and nowhere else.
    """
    p = path.strip().replace("\\", "/")
    return p[2:] if p.startswith("./") else p


def check_derivations_agree(gate_path):
    """Gate 22's inline stage detection vs the shared wc_published_stages module.

    Two places need to know which workflows are published stages: this gate
    (which checks their runner/container-image bindings on every PR) and
    release.yml's actionlint pass (via wc_published_stages.py). They must not
    answer differently — a stage visible to one and invisible to the other is
    exactly issue #149, where a file went unlinted for a whole release while
    the gate reported success.

    Comparing on the real fleet rather than on a fixture is deliberate: a
    fixture only ever exercises shapes someone thought to write down.
    """
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    try:
        from wc_published_stages import published_stages
    except ImportError as exc:
        return [("shared stage derivation", [f"cannot import "
                 f"wc_published_stages ({exc}); release.yml's pass 1 depends "
                 f"on it"], "")]

    module_stages = {norm(p) for p in published_stages()}
    proc = subprocess.run([sys.executable, gate_path], cwd=".",
                          capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    out = (proc.stdout or "") + (proc.stderr or "")
    m = re.search(r"Gate 22: (\d+) published stage\(s\)", out)
    if not m:
        return [("shared stage derivation",
                 ["could not read the stage count out of Gate 22's own output; "
                  "its summary line has changed shape"], out.strip())]

    gate_count = int(m.group(1))
    gate_stages = {norm(p) for p in
                   re.findall(r"^note: (.+): published stage$", out, re.M)}
    if len(gate_stages) != gate_count:
        return [("shared stage derivation", [
            f"Gate 22's summary says {gate_count} published stage(s) but it "
            f"named {len(gate_stages)} of them."], out.strip())]

    if gate_stages != module_stages:
        only_gate = sorted(gate_stages - module_stages)
        only_module = sorted(module_stages - gate_stages)
        return [("shared stage derivation", [
            f"Gate 22 and wc_published_stages.py disagree about which "
            f"workflows are published stages. Seen only by Gate 22: "
            f"{only_gate or '(none)'}. Seen only by wc_published_stages.py: "
            f"{only_module or '(none)'}."], "")]
    print(f"ok    the shared stage derivation agrees with Gate 22 "
          f"({gate_count} published stages)")
    return []


def check_real_fleet(gate_path):
    """Gate 22 must actually PASS against this repository's own eleven stages.

    The fixture cases above prove the DETECTOR works; this proves the thing
    it is detecting on has actually been fixed (T033) — a self-test that
    only ever runs synthetic fixtures could ship green next to a real fleet
    that still fails Gate 22 for real, and nobody would notice until CI ran.
    """
    proc = subprocess.run([sys.executable, gate_path], cwd=".",
                          capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    out = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0:
        return [("Gate 22 against the real repository",
                 ["Gate 22 fails when run against this repository's own "
                  "eleven published stages — the fixtures above can be "
                  "green while the real surface is not."], out.strip())]
    print("ok    Gate 22 passes against this repository's own real fleet")
    return []


def main():
    if not os.path.isfile(LINT_WORKFLOW):
        sys.exit(f"::error::run this from the repository root; {LINT_WORKFLOW} not found.")

    gate_src = extract_gate()
    root = tempfile.mkdtemp(prefix="verify_gate22_")
    gate_path = os.path.join(root, "gate22.py")
    io.open(gate_path, "w", encoding="utf-8").write(gate_src)

    failures = []

    def record(name, problems, out):
        failures.append((name, problems, out))
        print(f"FAIL  {name}")
        for problem in problems:
            print(f"        - {problem}")
        for line in (out or "").strip().splitlines():
            print(f"        | {line}")

    for name, problems, out in check_derivations_agree(gate_path):
        record(name, problems, out)
    for name, problems, out in check_real_fleet(gate_path):
        record(name, problems, out)
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
                record(name, problems, out)
            else:
                print(f"ok    {name}")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    # +2: the shared-derivation check and the real-fleet check are checks
    # too, and counting only the fixtures made either failure read as "1 of
    # N scenarios" when all N fixture scenarios had just passed.
    total = len(CASES) + 2
    print()
    if failures:
        print(f"::error file={LINT_WORKFLOW}::Gate 22 self-test: "
              f"{len(failures)} of {total} check(s) behaved wrongly "
              f"({', '.join(name for name, _, _ in failures)}). Gate 22's "
              f"detection logic does not do what its name claims, so a green Gate 22 "
              f"on the real fleet means nothing.")
        return 1
    print(f"Gate 22 self-test: all {total} checks behaved as expected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
