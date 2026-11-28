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
from wc_lint_gate_source import LINT_WORKFLOW, case_env, extract_gate_step  # noqa: E402

STEP_PREFIX = "Gate 7"


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

# The registry, relative to a case's .github/workflows directory.
REGISTRY = "../scripts/unpublished-callables.json"

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

    # specs/095: implement.yml's credential-free gate-suite job is unbound
    # by design, and the exemption is file- and job-scoped.
    ("registered exemption: an unbound gate-suite-implement-cycle in "
     "implement.yml passes beside bound siblings",
     {"implement.yml": stage(job("implement", BOUND),
                             job("gate-suite-implement-cycle", UNBOUND))},
     False, ()),

    ("the gate-suite exemption is asserted, not merely skipped: binding "
     "gate-suite-implement-cycle back fails",
     {"implement.yml": stage(job("implement", BOUND),
                             job("gate-suite-implement-cycle", BOUND))},
     True, ("gate-suite-implement-cycle", "environment:")),

    ("the gate-suite exemption is file-scoped: the same unbound job in "
     "another stage still fails",
     {"stage.yml": stage(job("gate-suite-implement-cycle", UNBOUND))},
     True, ("'gate-suite-implement-cycle'", "no environment")),

    ("the exemption is job-name-scoped: a differently named unbound job in "
     "a file that also has the exempt one still fails",
     {"stage.yml": stage(job("verify-image-prerequisites", UNBOUND),
                         job("other", UNBOUND))},
     True, ("'other'", "no environment")),

    # specs/127: a callable registered in unpublished-callables.json with a
    # reason is internal, not a stage. The registry is read only through
    # wc_published_stages.unpublished_callables(), which ignores an entry
    # with an empty reason, so an exemption can never be silent.
    ("registered unpublished callable: an unbound callable with a reason "
     "is not a stage",
     {"internal.yml": stage(job("only", UNBOUND)),
      "stage.yml": stage(job("first", BOUND)),
      REGISTRY: '{"internal.yml": "internal callable, reached only by a wrapper"}'},
     False, ()),

    ("an unpublished-callables entry with an empty reason exempts nothing",
     {"internal.yml": stage(job("only", UNBOUND)),
      "stage.yml": stage(job("first", BOUND)),
      REGISTRY: '{"internal.yml": "  "}'},
     True, ("'only'", "no environment")),
]


def norm(path):
    """A workflow path in the one spelling both derivations can be compared in.

    glob joins with os.sep, so the same file is `.github/workflows/x.yml` on
    the runner and `.github/workflows\\x.yml` locally — a difference that would
    make every path look like a disagreement on Windows and nowhere else.
    """
    p = path.strip().replace("\\", "/")
    return p[2:] if p.startswith("./") else p


# The registry's one home (CLAUDE.md "Shared logic has exactly one home").
REGISTRY_HOME = "wc_published_stages.py"
# A string literal naming the registry file: what a second loader opens.
REGISTRY_LITERAL = re.compile(r"unpublished-callables\.json[\"']")


def registry_second_homes(texts):
    """Paths in `texts` ({path: text}) that open unpublished-callables.json
    themselves instead of calling wc_published_stages.unpublished_callables().

    Gates 7, 22 and 186 each once carried a pasted copy of the loader, and
    those copies skipped the empty-reason rule the module applies. Comment
    lines are prose and do not count."""
    found = []
    for path, text in sorted(texts.items()):
        if os.path.basename(path) in (REGISTRY_HOME, os.path.basename(__file__)):
            continue
        for line in text.splitlines():
            if line.lstrip().startswith("#"):
                continue
            if REGISTRY_LITERAL.search(line):
                found.append(path)
                break
    return found


def check_registry_single_home():
    """No workflow, action or script but wc_published_stages.py reads the
    unpublished-callables registry, and the check itself detects a pasted
    loader (so a green result means something)."""
    import glob
    paths = (glob.glob(".github/workflows/*.y*ml")
             + glob.glob(".github/actions/**/*.y*ml", recursive=True)
             + glob.glob(".github/actions/**/*.sh", recursive=True)
             + glob.glob(".github/scripts/**/*.py", recursive=True)
             + glob.glob(".github/scripts/**/*.sh", recursive=True))
    texts = {p.replace(os.sep, "/"): io.open(p, encoding="utf-8", errors="replace").read()
             for p in paths}
    problems = []
    for path in registry_second_homes(texts):
        problems.append(f"{path} reads unpublished-callables.json itself; call "
                        f"wc_published_stages.unpublished_callables() instead")
    pasted = ('          try:\n'
              '              UNPUBLISHED = json.load(open(".github/scripts/'
              'unpublished-callables.json"))\n'
              '          except (OSError, ValueError):\n'
              '              UNPUBLISHED = {}\n')
    if registry_second_homes({".github/workflows/x.yml": pasted}) != [".github/workflows/x.yml"]:
        problems.append("the single-home check does not detect a pasted registry loader")
    if registry_second_homes({".github/workflows/x.yml":
                              "  # registered in unpublished-callables.json (spec 127)\n"}):
        problems.append("the single-home check flags a comment that only names the registry")
    if problems:
        return [("unpublished-callables registry has one home", problems, "")]
    print("ok    the unpublished-callables registry has one reader (wc_published_stages.py)")
    return []


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

    gate_src = extract_gate_step(STEP_PREFIX)
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
    for name, problems, out in check_registry_single_home():
        record(name, problems, out)
    try:
        for name, files, expect_fail, must_mention in CASES:
            case_dir = tempfile.mkdtemp(prefix="case_", dir=root)
            wf_dir = os.path.join(case_dir, ".github", "workflows")
            os.makedirs(wf_dir)
            for fname, body in files.items():
                target = os.path.normpath(os.path.join(wf_dir, fname))
                os.makedirs(os.path.dirname(target), exist_ok=True)
                io.open(target, "w", encoding="utf-8").write(body)

            proc = subprocess.run([sys.executable, gate_path], cwd=case_dir, env=case_env(),
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

    # +3: the shared-derivation, real-fleet and registry single-home checks
    # are checks too, and
    # counting only the fixtures made a derivation failure read as "1 of 14
    # scenarios" when all 14 scenarios had just passed.
    total = len(CASES) + 3
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
