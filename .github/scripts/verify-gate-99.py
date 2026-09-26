#!/usr/bin/env python3
"""Container-mode evidence gates a container-mode `pass` (Gate 99).

WHY THIS EXISTS
---------------
specs/067-e2e-container-image-evidence closes the gap specs/054-e2e-
container-coverage's own tasks.md T009 documented as an accepted limitation:
a container-mode end-to-end turn used to earn `pass` without ever confirming
the test repository was actually configured to run the fixture in a
container, or that any stage job it drove actually executed inside one. A
revoked credential, an unset variable, or a regression that skips the new
checks must all fail the run rather than silently restore that gap.

This gate combines two techniques (research.md D7), one per half of what
FR-015 requires:

  structural  scans auto-release.yml to prove the poll step's one `pass`-
              writing write_verdict call site is reachable only through the
              unbroken step-guard chain from container-evidence-config
              through cleanup/reset/speckit-version/scaffold/kickoff to
              poll, AND that the poll step's own execution-evidence
              fragment checks its decision's failing_check and exits before
              the pass call is ever reached.
  executed    extracts and runs, VERBATIM, the shipped container-evidence-
              config step and the shipped poll step's execution-evidence
              fragment (modeled on Gate 52's verify-auto-release-report.py
              and this repository's marker-extraction idiom, wc_shell_
              harness.extract_quoted_var), under stubbed `gh`/`date`,
              against one fixture per FR-005 branch (SC-006): not
              configured, empty value, drift, unreadable, rate-limited
              (config half); unreadable, rate-limited, not containerized,
              and the passing case (execution half).

It ends with a --self-test mode that puts each defect back and asserts the
suite then fails. A test that cannot fail is not a test (Constitution VIII).

Usage: python3 .github/scripts/verify-gate-99.py [--self-test]
Requires: bash, jq. See wc_shell_harness.py for running this on Windows.
"""
import json
import os
import re
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_shell_harness import (  # noqa: E402
    ensure_jq, find_step, resolve_bash, run_step, use_utf8_stdout)

WORKFLOW = ".github/workflows/auto-release.yml"
CONFIG_STEP_NAME = "Read container-mode configuration evidence"
DECISION_SCRIPT_REL = os.path.join(
    ".github", "actions", "_shared",
    "auto-release-container-evidence-decision.sh")
VERDICT_SCRIPT_REL = os.path.join(
    ".github", "actions", "_shared", "auto-release-verdict.sh")
CHECKS_SCRIPT_REL = os.path.join(
    ".github", "scripts", "e2e-provisioning", "checks.sh")

# The poll step's execution-evidence fragment is not its own step -- it is
# a marked-off portion of the `poll` step's `run:` text (research.md D2:
# read "immediately before" the sole pass-writing call). Extracted by
# exact, shipped literal text rather than a hand-typed copy (the same
# reason wc_shell_harness.extract_quoted_var exists): a future edit that
# changes this text without updating these markers fails loudly here
# rather than silently drifting.
FRAGMENT_START_MARKER = 'execution_pass_observed=""'
FRAGMENT_END_MARKER = 'write_verdict "pass"'
PREAMBLE_END_MARKER = 'author_id=""'

HEAD = "0123456789abcdef0123456789abcdef01234567"


def fail(msg):
    print(f"::error::{msg}")
    sys.exit(1)


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


# --------------------------------------------------------------------------
# Structural half (T011, FR-015, research.md D7)
# --------------------------------------------------------------------------
GUARD_CHAIN = [
    # (step id, the id its `if:` must reference)
    ("cleanup", "container-evidence-config"),
    ("reset-branch", "cleanup"),
    ("reset", "cleanup"),
    ("speckit-version", "reset"),
    ("scaffold", "speckit-version"),
    ("kickoff", "scaffold"),
    ("poll", "kickoff"),
]


def check_structural(text):
    findings = []

    pass_calls = text.count('write_verdict "pass"')
    if pass_calls != 1:
        findings.append(
            f"expected exactly one write_verdict \"pass\" call site in "
            f"{WORKFLOW}, found {pass_calls} -- a second pass path can "
            f"bypass the evidence checks (FR-015).")

    import yaml
    doc = yaml.safe_load(text) or {}
    steps_by_id = {}
    for job in (doc.get("jobs") or {}).values():
        for step in (job or {}).get("steps") or []:
            step = step or {}
            sid = step.get("id")
            if sid:
                steps_by_id[sid] = step

    for step_id, must_gate_on in GUARD_CHAIN:
        step = steps_by_id.get(step_id)
        if step is None:
            findings.append(f"no step with id: {step_id!r} found -- the "
                            f"guard chain this gate checks has moved; "
                            f"update GUARD_CHAIN alongside it.")
            continue
        cond = str(step.get("if") or "")
        needle = f"steps.{must_gate_on}.outputs.ok"
        if needle not in cond:
            findings.append(
                f"step {step_id!r}'s if: ({cond!r}) does not consult "
                f"{needle!r} -- the pass call site would be reachable "
                f"without that step's evidence check having run (FR-015).")

    if FRAGMENT_START_MARKER not in text or FRAGMENT_END_MARKER not in text:
        findings.append("could not locate the execution-evidence fragment "
                        "markers -- update this gate alongside the poll "
                        "step's text.")
    else:
        start = text.index(FRAGMENT_START_MARKER)
        end = text.index(FRAGMENT_END_MARKER, start)
        fragment = text[start:end]
        if "auto-release-container-evidence-decision.sh execution" not in fragment:
            findings.append(
                "the execution-evidence fragment no longer calls the "
                "decision script with check=execution -- a pass could be "
                "reached without consulting it (FR-015).")
        if not re.search(r'if\s*\[\s*-n\s*"\$failing_check"\s*\]', fragment):
            findings.append(
                "the execution-evidence fragment no longer branches on a "
                "non-empty failing_check -- update this gate if the shape "
                "changed, or fix the regression.")
        if "exit 0" not in fragment:
            findings.append(
                "the execution-evidence fragment's failing branch no "
                "longer exits before the pass call -- a failing "
                "containerization check could fall through to pass "
                "(FR-015).")

    return findings


# --------------------------------------------------------------------------
# Executed-step half: container-evidence-config (T012)
# --------------------------------------------------------------------------
STUB_GH_CONFIG = r'''#!/usr/bin/env bash
if [ "$1 $2" = "variable list" ]; then
  if [ "${GH_STUB_VAR_FAIL:-}" = "true" ]; then
    echo "${GH_STUB_VAR_ERR:-unexpected error}" >&2
    exit 1
  fi
  printf '%s' "${GH_STUB_VAR_VALUE-}"
  exit 0
fi
echo "unexpected gh invocation: $*" >&2
exit 1
'''


REPO_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")


def _stage_shared_scripts(workdir, source_root=REPO_ROOT):
    """Copy the shared scripts a scenario's step invokes into `workdir` at
    their shipped relative path. `source_root` defaults to the real repo
    (the common case: only auto-release.yml/the poll fragment are under
    test), but a mutation run passes the scratch `root` a possibly-
    mutated decision script was staged into (run_full_suite) -- staging
    from the real repo unconditionally would silently run every scenario
    against the PRISTINE decision script even while testing a mutated one."""
    for rel in (DECISION_SCRIPT_REL, VERDICT_SCRIPT_REL, CHECKS_SCRIPT_REL):
        src = os.path.join(source_root, rel)
        dst = os.path.join(workdir, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(src, dst)


def render_step(step):
    script = str(step["run"])
    env = {}
    for k, v in (step.get("env") or {}).items():
        v = str(v)
        if "${{" in v:
            env[k] = ""
        else:
            env[k] = v
    return script, env


CONFIG_BASE_ENV = dict(
    E2E_REPO="owner/e2e-target", HEAD_SHA=HEAD, MODE="container",
    WC_SOURCE_CONTAINER_IMAGE="ghcr.io/example/image:1.2.3",
    GH_STUB_VAR_VALUE="", GH_STUB_VAR_FAIL="", GH_STUB_VAR_ERR="",
)

CONFIG_SCENARIOS = [
    dict(
        name="default-runner turn: no-op, ok=true, no gh call made",
        env=dict(MODE="default-runner"),
        ok="true", verdict=None,
    ),
    dict(
        name="FR-005(i) not configured: variable absent on the test repository",
        env=dict(GH_STUB_VAR_VALUE=""),
        ok="false",
        failing_check="container image not configured on the test repository",
    ),
    dict(
        name="FR-005(i) not configured: variable present but empty (Edge Case)",
        env=dict(GH_STUB_VAR_VALUE=""),
        ok="false",
        failing_check="container image not configured on the test repository",
    ),
    dict(
        name="FR-005(ii) drift: variable set to a different image",
        env=dict(GH_STUB_VAR_VALUE="ghcr.io/example/image:9.9.9"),
        ok="false",
        failing_check="container image configured but does not match this repository's pin",
    ),
    dict(
        name="FR-005(v) unreadable: gh variable list fails, not rate-limited",
        env=dict(GH_STUB_VAR_FAIL="true", GH_STUB_VAR_ERR="HTTP 403: access denied"),
        ok="false",
        failing_check="container-mode evidence unreadable",
    ),
    dict(
        name="FR-005(v, rate-limited) gh variable list fails, rate limit text",
        env=dict(GH_STUB_VAR_FAIL="true", GH_STUB_VAR_ERR="API rate limit exceeded for installation"),
        ok="false",
        failing_check="container-mode evidence rate-limited",
    ),
    dict(
        name="FR-005(vi) configured and matching: proceeds",
        env=dict(GH_STUB_VAR_VALUE="ghcr.io/example/image:1.2.3"),
        ok="true", verdict=None,
        expected_image="ghcr.io/example/image:1.2.3",
        observed_image="ghcr.io/example/image:1.2.3",
    ),
]


def run_config_scenario(script, env, sc, tmproot, source_root=REPO_ROOT):
    workdir = tempfile.mkdtemp(dir=tmproot)
    runner_temp = tempfile.mkdtemp(dir=tmproot)
    bindir = tempfile.mkdtemp(dir=tmproot)
    _stage_shared_scripts(workdir, source_root)

    gh_path = os.path.join(bindir, "gh")
    with open(gh_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(STUB_GH_CONFIG)
    os.chmod(gh_path, 0o755)

    run_env = dict(env)
    run_env.update(CONFIG_BASE_ENV)
    run_env.update(sc["env"])
    run_env["PATH"] = bindir + os.pathsep + os.environ["PATH"]

    rc, out, outputs, _summary = run_step(BASH, script, workdir, run_env, runner_temp)
    verdict = None
    v = outputs.get("verdict")
    if v:
        try:
            verdict = json.loads(v)
        except json.JSONDecodeError:
            verdict = {"_unparseable": v}
    for d in (workdir, runner_temp, bindir):
        shutil.rmtree(d, ignore_errors=True)
    return rc, out, outputs, verdict


def suite_config(script, env, tmproot, source_root=REPO_ROOT):
    failures = []
    for sc in CONFIG_SCENARIOS:
        tag = f"[config: {sc['name']}]"
        rc, out, outputs, verdict = run_config_scenario(script, env, sc, tmproot, source_root)
        if rc != 0:
            failures.append(f"{tag} the step exited {rc}:\n{out}")
            continue
        ok = outputs.get("ok")
        if ok != sc["ok"]:
            failures.append(f"{tag} expected ok={sc['ok']!r}, got {ok!r}")
        want_fc = sc.get("failing_check")
        if want_fc is not None:
            if verdict is None:
                failures.append(f"{tag} expected a verdict naming "
                                f"{want_fc!r}, got none; outputs: {outputs}")
            elif verdict.get("failing_check") != want_fc:
                failures.append(f"{tag} expected failing_check={want_fc!r}, "
                                f"got {verdict.get('failing_check')!r}")
            elif verdict.get("outcome") != "fail-infra":
                failures.append(f"{tag} expected outcome=fail-infra, got "
                                f"{verdict.get('outcome')!r}")
        if sc.get("verdict") is None and want_fc is None and verdict is not None:
            failures.append(f"{tag} expected no verdict output, got {verdict!r}")
        if "expected_image" in sc and outputs.get("expected-image") != sc["expected_image"]:
            failures.append(f"{tag} expected-image={sc['expected_image']!r}, "
                            f"got {outputs.get('expected-image')!r}")
        if "observed_image" in sc and outputs.get("observed-image") != sc["observed_image"]:
            failures.append(f"{tag} observed-image={sc['observed_image']!r}, "
                            f"got {outputs.get('observed-image')!r}")
    return failures


# --------------------------------------------------------------------------
# Executed-step half: poll step's execution-evidence fragment (T012)
# --------------------------------------------------------------------------
STUB_GH_EXECUTION = r'''#!/usr/bin/env bash
if [ "$1 $2" = "run list" ]; then
  if [ "${GH_STUB_RUNS_FAIL:-}" = "true" ]; then
    echo "${GH_STUB_RUNS_ERR:-unexpected error}" >&2
    exit 1
  fi
  printf '%s' "${GH_STUB_RUNS_JSON:-[]}"
  exit 0
fi
if [ "$1" = "api" ]; then
  if [ "${GH_STUB_JOBS_FAIL:-}" = "true" ]; then
    echo "${GH_STUB_JOBS_ERR:-unexpected error}" >&2
    exit 1
  fi
  case "$2" in
    repos/*/actions/runs/111/jobs) printf '%s\n' "${GH_STUB_JOBS_111:-}" ;;
    repos/*/actions/runs/222/jobs) printf '%s\n' "${GH_STUB_JOBS_222:-}" ;;
    *) echo "unexpected gh api invocation: $*" >&2; exit 1 ;;
  esac
  exit 0
fi
echo "unexpected gh invocation: $*" >&2
exit 1
'''

JOB_CONTAINERIZED = json.dumps({
    "name": "implement", "steps": [
        {"name": "Set up job"}, {"name": "Initialize containers"},
        {"name": "Run agent"}, {"name": "Stop containers"}]})
JOB_NOT_CONTAINERIZED = json.dumps({
    "name": "implement", "steps": [
        {"name": "Set up job"}, {"name": "Run agent"}]})

EXECUTION_BASE_ENV = dict(
    MODE="container", E2E_REPO="owner/e2e-target", HEAD_SHA=HEAD,
    HARNESS_TOKEN="dummy-token", HARNESS_LOGIN="dummy-login",
    ISSUE="1", ISSUE_URL="https://example.invalid/issues/1",
    GH_STUB_RUNS_JSON=json.dumps([{"databaseId": 111}]),
    GH_STUB_JOBS_111=JOB_CONTAINERIZED, GH_STUB_JOBS_222="",
    GH_STUB_RUNS_FAIL="", GH_STUB_RUNS_ERR="",
    GH_STUB_JOBS_FAIL="", GH_STUB_JOBS_ERR="",
)

EXECUTION_SCENARIOS = [
    dict(
        name="FR-005(vi) every stage job containerized: reaches pass",
        env=dict(),
        reached_pass=True,
    ),
    dict(
        name="FR-005(iv) a stage job did not execute inside a container",
        env=dict(GH_STUB_JOBS_111=JOB_NOT_CONTAINERIZED),
        reached_pass=False,
        failing_check="container image configured but stage jobs did not execute inside a container",
    ),
    dict(
        name="FR-005(v) unreadable: gh run list fails, not rate-limited",
        env=dict(GH_STUB_RUNS_FAIL="true", GH_STUB_RUNS_ERR="HTTP 403: access denied"),
        reached_pass=False,
        failing_check="container-mode evidence unreadable",
    ),
    dict(
        name="FR-005(v, rate-limited) gh run list fails, rate limit text",
        env=dict(GH_STUB_RUNS_FAIL="true", GH_STUB_RUNS_ERR="API rate limit exceeded"),
        reached_pass=False,
        failing_check="container-mode evidence rate-limited",
    ),
    dict(
        name="FR-005(v) unreadable: gh api .../jobs fails, not rate-limited",
        env=dict(GH_STUB_JOBS_FAIL="true", GH_STUB_JOBS_ERR="HTTP 500: server error"),
        reached_pass=False,
        failing_check="container-mode evidence unreadable",
    ),
    dict(
        name="FR-005(v, rate-limited) gh api .../jobs fails, rate limit text",
        env=dict(GH_STUB_JOBS_FAIL="true", GH_STUB_JOBS_ERR="secondary rate limit"),
        reached_pass=False,
        failing_check="container-mode evidence rate-limited",
    ),
    dict(
        name="default-runner turn: fragment is a no-op, reaches pass",
        env=dict(MODE="default-runner", GH_STUB_RUNS_FAIL="true"),
        reached_pass=True,
    ),
]

SENTINEL = "WC_GATE99_FRAGMENT_REACHED_PASS"


def build_execution_script(preamble, fragment):
    return preamble + fragment + f'\necho {SENTINEL}\n'


def run_execution_scenario(script, sc, tmproot, source_root=REPO_ROOT):
    workdir = tempfile.mkdtemp(dir=tmproot)
    runner_temp = tempfile.mkdtemp(dir=tmproot)
    bindir = tempfile.mkdtemp(dir=tmproot)
    _stage_shared_scripts(workdir, source_root)

    gh_path = os.path.join(bindir, "gh")
    with open(gh_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(STUB_GH_EXECUTION)
    os.chmod(gh_path, 0o755)

    run_env = dict(EXECUTION_BASE_ENV)
    run_env.update(sc["env"])
    run_env["PATH"] = bindir + os.pathsep + os.environ["PATH"]

    rc, out, outputs, _summary = run_step(BASH, script, workdir, run_env, runner_temp)
    verdict = None
    v = outputs.get("verdict")
    if v:
        try:
            verdict = json.loads(v)
        except json.JSONDecodeError:
            verdict = {"_unparseable": v}
    for d in (workdir, runner_temp, bindir):
        shutil.rmtree(d, ignore_errors=True)
    return rc, out, verdict


def suite_execution(preamble, fragment, tmproot, source_root=REPO_ROOT):
    failures = []
    script = build_execution_script(preamble, fragment)
    for sc in EXECUTION_SCENARIOS:
        tag = f"[execution: {sc['name']}]"
        rc, out, verdict = run_execution_scenario(script, sc, tmproot, source_root)
        if rc != 0:
            failures.append(f"{tag} the fragment exited {rc}:\n{out}")
            continue
        reached = SENTINEL in out
        if reached != sc["reached_pass"]:
            failures.append(f"{tag} expected reached_pass={sc['reached_pass']}, "
                            f"got {reached} (stdout tail: {out[-300:]!r})")
        want_fc = sc.get("failing_check")
        if want_fc is not None:
            if verdict is None:
                failures.append(f"{tag} expected a verdict naming "
                                f"{want_fc!r}, got none")
            elif verdict.get("failing_check") != want_fc:
                failures.append(f"{tag} expected failing_check={want_fc!r}, "
                                f"got {verdict.get('failing_check')!r}")
    return failures


# --------------------------------------------------------------------------
# Mutations (T013): put each defect back, assert the suite then fails.
# --------------------------------------------------------------------------
def mut_config_drift_ignored(text):
    old = 'elif [ "$observed" != "$expected" ]; then'
    if text.count(old) != 1:
        fail(f"verify-gate-99: expected exactly one {old!r} to mutate in "
             f"the decision script, found {text.count(old)}.")
    return text.replace(old, 'elif false; then', 1)


def mut_execution_gate_removed_in_workflow(text):
    old = FRAGMENT_START_MARKER
    if text.count(old) != 1:
        fail(f"verify-gate-99: expected exactly one {old!r} marker in "
             f"{WORKFLOW}, found {text.count(old)}.")
    start = text.index(old)
    end = text.index(FRAGMENT_END_MARKER, start)
    fragment = text[start:end]
    needle = 'if [ -n "$failing_check" ]; then'
    if fragment.count(needle) != 1:
        fail("verify-gate-99: could not locate the execution fragment's "
             "failing_check branch to mutate -- update this gate alongside it.")
    mutated_fragment = fragment.replace(needle, 'if false; then', 1)
    return text[:start] + mutated_fragment + text[end:]


def mut_cleanup_guard_loosened(text):
    old = ('        id: cleanup\n'
           '        # specs/067-e2e-container-image-evidence T006: re-pointed from\n'
           '        # steps.maintainer-credential.outputs.ok so an unconfigured,\n'
           '        # drifted, or unreadable container-mode turn cannot reach cleanup/\n'
           '        # reset/speckit-version/scaffold/kickoff (FR-011, SC-003) --\n'
           '        # container-evidence-config\'s own no-op sets ok=true on every\n'
           '        # default-runner turn, so this guard is unchanged for that mode.\n'
           '        if: steps.container-evidence-config.outputs.ok == \'true\'')
    if text.count(old) != 1:
        fail("verify-gate-99: could not locate the cleanup step's guard to "
             "mutate -- update this gate alongside it.")
    return text.replace(
        old,
        '        id: cleanup\n'
        "        if: steps.maintainer-credential.outputs.ok == 'true'",
        1)


WORKFLOW_MUTATIONS = [
    ("the execution-evidence fragment's failing_check branch removed "
     "(a non-containerized stage job would reach pass)",
     mut_execution_gate_removed_in_workflow),
    ("cleanup's guard loosened back to maintainer-credential (an "
     "unconfigured/drifted container-mode turn would reach cleanup/"
     "scaffold/kickoff again)",
     mut_cleanup_guard_loosened),
]

DECISION_MUTATIONS = [
    ("the config decision's drift comparison disabled (a differing "
     "image would read as configured)",
     mut_config_drift_ignored),
]


def run_full_suite(workflow_text, decision_text, tmproot):
    """Stage a (possibly mutated) copy of the two subject files into a
    scratch root and run every scenario against it. Returns the combined
    failures list; empty means everything passed. `root` (not the real
    repository) is used as every scenario's source_root, so a mutated
    decision_text actually reaches the scenarios that execute it -- see
    _stage_shared_scripts' own docstring."""
    root = tempfile.mkdtemp(dir=tmproot)
    wf_path = os.path.join(root, WORKFLOW)
    os.makedirs(os.path.dirname(wf_path), exist_ok=True)
    with open(wf_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(workflow_text)
    decision_path = os.path.join(root, DECISION_SCRIPT_REL)
    os.makedirs(os.path.dirname(decision_path), exist_ok=True)
    with open(decision_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(decision_text)
    for rel in (VERDICT_SCRIPT_REL, CHECKS_SCRIPT_REL):
        src = os.path.join(REPO_ROOT, rel)
        dst = os.path.join(root, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(src, dst)

    failures = list(check_structural(workflow_text))

    step = find_step(wf_path, CONFIG_STEP_NAME)
    script, env = render_step(step)
    failures += suite_config(script, env, tmproot, source_root=root)

    poll_text = str(find_step(wf_path, "Poll the test repository to a verdict")["run"])
    if PREAMBLE_END_MARKER not in poll_text or FRAGMENT_START_MARKER not in poll_text:
        failures.append("could not locate the poll step's preamble/fragment "
                        "markers to build the executed-step half's script.")
    else:
        preamble = poll_text[:poll_text.index(PREAMBLE_END_MARKER)]
        start = poll_text.index(FRAGMENT_START_MARKER)
        end = poll_text.index(FRAGMENT_END_MARKER, start)
        fragment = poll_text[start:end]
        failures += suite_execution(preamble, fragment, tmproot, source_root=root)

    shutil.rmtree(root, ignore_errors=True)
    return failures


BASH = None


def run_selftest(workflow_text, decision_text):
    tmproot = tempfile.mkdtemp()
    failures = []
    try:
        for label, mutate in WORKFLOW_MUTATIONS:
            mutated = mutate(workflow_text)
            if mutated == workflow_text:
                print(f"::error::mutation {label!r} changed nothing.")
                failures.append(f"mutation inapplicable: {label}")
                continue
            broke = run_full_suite(mutated, decision_text, tmproot)
            if broke:
                print(f"Mutation OK - {label}: {len(broke)} assertion(s) fail.")
            else:
                print(f"::error::MUTATION SURVIVED - {label}.")
                failures.append(f"mutation survived: {label}")
        for label, mutate in DECISION_MUTATIONS:
            mutated = mutate(decision_text)
            if mutated == decision_text:
                print(f"::error::mutation {label!r} changed nothing.")
                failures.append(f"mutation inapplicable: {label}")
                continue
            broke = run_full_suite(workflow_text, mutated, tmproot)
            if broke:
                print(f"Mutation OK - {label}: {len(broke)} assertion(s) fail.")
            else:
                print(f"::error::MUTATION SURVIVED - {label}.")
                failures.append(f"mutation survived: {label}")
    finally:
        shutil.rmtree(tmproot, ignore_errors=True)
    return failures


def main():
    global BASH
    use_utf8_stdout()
    ensure_jq()
    BASH = resolve_bash()
    if not os.path.isfile(WORKFLOW):
        fail(f"run this from the repository root; {WORKFLOW} not found.")

    workflow_text = read(WORKFLOW)
    decision_text = read(DECISION_SCRIPT_REL)

    self_test = "--self-test" in sys.argv[1:]

    tmproot = tempfile.mkdtemp()
    try:
        failures = run_full_suite(workflow_text, decision_text, tmproot)
        for f in failures:
            print(f"::error::{f}")

        if self_test:
            failures += run_selftest(workflow_text, decision_text)
    finally:
        shutil.rmtree(tmproot, ignore_errors=True)

    n_scenarios = len(CONFIG_SCENARIOS) + len(EXECUTION_SCENARIOS)
    print(f"container-mode evidence (Gate 99): {n_scenarios} scenario(s); "
          f"{len(failures)} failure(s).")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
