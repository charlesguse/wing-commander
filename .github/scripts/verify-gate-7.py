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
sync. (verify-gate-6.py does the same thing; the shared extractor lives in
wc_lint_gate_source.py, a `wc_`-prefixed module rather than a second
verify-gate-N.py import, since a module whose filename contains hyphens
cannot be imported.)

Usage: python3 .github/scripts/verify-gate-7.py
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
STEP_PREFIX = "Gate 7"


def extract_gate(path=LINT_WORKFLOW):
    """Return Gate 7's python source, read out of the shipped workflow."""
    return extract_gate_step(path, STEP_PREFIX)


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

# Deliberately non-forwarding, mirroring the real pr-conversation.yml `act`
# job's per-leg confirm binding — the exact shape Gate 7's EXCEPTIONS dict
# names as (pr-conversation.yml, act).
BOUND_MATRIX_LEG = """\
    environment:
      name: ${{ matrix['confirm-environment'] }}
      deployment: false
"""


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

    # Constitution VII / T044: a registered (file, job) exception is allowed
    # to deviate from verbatim forwarding, but ONLY that exact pair — the
    # exception must not read as "any job with this binding shape passes"
    # or "any job in this file passes".
    ("registered exception: pr-conversation.yml's act job may bind its "
     "own matrix leg instead of forwarding inputs.environment verbatim",
     {"pr-conversation.yml": stage(job("act", BOUND_MATRIX_LEG))},
     False, ()),

    ("the same non-forwarding binding on a job NOT named in the exception "
     "list still fails, even in the exact registered file",
     {"pr-conversation.yml": stage(job("other", BOUND_MATRIX_LEG))},
     True, ("'other'",)),

    ("the same non-forwarding binding on a job named 'act' in a "
     "DIFFERENT file still fails — the exception is not file-agnostic",
     {"stage.yml": stage(job("act", BOUND_MATRIX_LEG))},
     True, ("'act'",)),

    # specs/038-runner-container-passthrough: verify-image-prerequisites is
    # the one job deliberately left UNBOUND, and the gate asserts that in
    # the deviating direction — an exemption that only skips its job cannot
    # notice the binding being added back.
    ("registered exemption: an unbound verify-image-prerequisites passes "
     "beside bound siblings",
     {"stage.yml": stage(job("first", BOUND),
                         job("verify-image-prerequisites", UNBOUND))},
     False, ()),

    ("the exemption is asserted, not merely skipped: binding "
     "verify-image-prerequisites back fails",
     {"stage.yml": stage(job("first", BOUND),
                         job("verify-image-prerequisites", BOUND))},
     True, ("verify-image-prerequisites", "environment:")),

    ("the exemption is job-name-scoped: a differently named unbound job in "
     "a file that also has the exempt one still fails",
     {"stage.yml": stage(job("verify-image-prerequisites", UNBOUND),
                         job("other", UNBOUND))},
     True, ("'other'", "no environment")),
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

    The comparison is set-vs-set, not count-vs-count. Counts agree whenever
    the two derivations see the same NUMBER of files, which is exactly what
    happens when one skips a malformed stage (wc_published_stages.py swallows
    yaml.YAMLError and continues) while picking up a different one — the
    disagreement this exists to catch, passing.
    """
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
    m = re.search(r"Gate 7: (\d+) published stage\(s\)", out)
    if not m:
        return [("shared stage derivation",
                 ["could not read the stage count out of Gate 7's own output; "
                  "its summary line has changed shape"], out.strip())]

    gate_count = int(m.group(1))
    gate_stages = {norm(p) for p in
                   re.findall(r"^note: (.+): published stage$", out, re.M)}
    if len(gate_stages) != gate_count:
        return [("shared stage derivation", [
            f"Gate 7's summary says {gate_count} published stage(s) but it "
            f"named {len(gate_stages)} of them. This check reads the "
            f"'note: <path>: published stage' lines to compare the two "
            f"derivations file by file; if the gate stopped emitting one per "
            f"stage, restore it rather than falling back to counts."],
            out.strip())]

    if gate_stages != module_stages:
        only_gate = sorted(gate_stages - module_stages)
        only_module = sorted(module_stages - gate_stages)
        return [("shared stage derivation", [
            f"Gate 7 and wc_published_stages.py (which release.yml's "
            f"actionlint pass uses) disagree about which workflows are "
            f"published stages. Seen only by Gate 7: {only_gate or '(none)'}. "
            f"Seen only by wc_published_stages.py: {only_module or '(none)'}. "
            f"One of them is about to check a file the other does not know "
            f"exists — that is #149, where a stage went unlinted for a whole "
            f"release while the gate reported success."], "")]
    print(f"ok    the shared stage derivation agrees with Gate 7 "
          f"({gate_count} published stages)")
    return []


def check_real_fleet(gate_path):
    """Gate 7 must actually PASS against this repository's own eleven stages.

    The fixture cases above prove the DETECTOR works; this proves the thing
    it detects on is actually clean. A self-test that only ever runs
    synthetic fixtures ships green next to a real fleet that fails Gate 7
    for real, and nobody finds out until CI runs — which is exactly what
    happened when specs/038 added `verify-image-prerequisites` to all
    eleven stage files with no environment: block and no exemption here:
    every fixture in this file stayed green while the real Gate 7 returned
    eleven failures. verify-gate-22.py and verify-gate-23.py carry the same
    helper for the same reason.
    """
    proc = subprocess.run([sys.executable, gate_path], cwd=".",
                          capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    out = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0:
        return [("Gate 7 against the real repository",
                 ["Gate 7 fails when run against this repository's own "
                  "eleven published stages — the fixtures above can be "
                  "green while the real surface is not."], out.strip())]
    print("ok    Gate 7 passes against this repository's own real fleet")
    return []


def main():
    if not os.path.isfile(LINT_WORKFLOW):
        sys.exit(f"::error::run this from the repository root; {LINT_WORKFLOW} not found.")

    gate_src = extract_gate()
    root = tempfile.mkdtemp(prefix="verify_gate7_")
    gate_path = os.path.join(root, "gate7.py")
    io.open(gate_path, "w", encoding="utf-8").write(gate_src)

    failures = []

    def record(name, problems, out):
        """Append a failure AND say what it was.

        Every failure goes through here. The derivation check used to append
        straight to `failures` while only the fixture loop below knew how to
        print, so a genuine derivation disagreement produced the summary line
        ("1 of N scenarios behaved wrongly") and nothing else — pointing the
        maintainer at a fixture suite that had just printed `ok` N times, for
        a failure that is not one of the fixtures at all.
        """
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

    # +2: the shared-derivation and real-fleet checks are checks too, and
    # counting only the fixtures made a derivation failure read as "1 of 14
    # scenarios" when all 14 scenarios had just passed.
    total = len(CASES) + 2
    print()
    if failures:
        print(f"::error file={LINT_WORKFLOW}::Gate 7 self-test: "
              f"{len(failures)} of {total} check(s) behaved wrongly "
              f"({', '.join(name for name, _, _ in failures)}). Gate 7's "
              f"detection logic does not do what its name claims, so a green Gate 7 "
              f"on the real fleet means nothing.")
        return 1
    print(f"Gate 7 self-test: all {total} checks behaved as expected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
