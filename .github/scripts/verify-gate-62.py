#!/usr/bin/env python3
"""Gate 62 - the e2e reference image's tool set agrees with required-tools.txt.

Gate 23's existing drift check is purely textual: it compares the
`REQUIRED_TOOLS=` string literal embedded in each stage's
verify-image-prerequisites job against .github/scripts/required-tools.txt.
That check cannot fail if .github/docker/e2e-reference-image/Dockerfile
silently stops installing a tool the text still claims to install --
Constitution VIII ("a green check means what it says") is violated the
moment a check like that is trusted to guard a real artifact it never
inspects.

This gate is the version of the check that CAN fail on its own subject: it
`docker build`s the reference image locally (no push) and runs the exact
same one-container-start-checks-everything probe every stage's
verify-image-prerequisites job already runs against an adopter's image
(research.md D6):

    docker run --rm --entrypoint sh "$IMAGE" -c \
      'for t in $REQUIRED_TOOLS; do command -v "$t" || echo "missing:$t"; done'

against .github/scripts/required-tools.txt, naming every missing tool at
once rather than stopping at the first.

required-tools.txt is the ADOPTER contract, and it deliberately omits what
only this repository's own implement jobs need: wing-commander pins its
WING_COMMANDER_CONTAINER_IMAGE to this image, so its implement jobs run the
local gate suite and lint inside it. The image once lacked pyyaml, so
implement.yml's "Preflight: gate-suite prerequisites" step reported
ready=false on every cycle, the suite never ran, and gate-run tasks could
never be checked (#989). The gate therefore also checks, with no copy of
either list of its own:

  * implement.yml's own preflight steps (both legs), run verbatim inside
    the built image the way the job's default `bash -e {0}` runs them, must
    report ready=true. A tool the job installs for itself in an earlier
    step (JOB_INSTALLED) is stubbed onto PATH, since the image is not where
    it comes from.
  * every lint tool the implement agent prompt names in its "Where the
    list above includes them:" sentence must be on the image's PATH (less
    JOB_INSTALLED), so the prompt never advertises a command the agent's
    container does not have.

Self-test (--self-test): copies the Dockerfile, required-tools.txt and
implement.yml into an isolated temp tree, then (a) builds the real,
unmodified set and expects a clean pass, (b) removes one real tool's install
from a copy of the Dockerfile and expects the failure to name that tool --
proving this gate's failure branch actually fails on its own subject
(Constitution VIII), the exact gap Gate 23's textual-only check leaves open
-- and (c) removes the gate-suite and lint packages and expects the
preflight check to name pyyaml and the lint check to name the lint tools.

Usage: python3 .github/scripts/verify-gate-62.py [--self-test]
"""
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

DOCKERFILE_DIR = ".github/docker/e2e-reference-image"
REQUIRED_TOOLS_FILE = ".github/scripts/required-tools.txt"
IMAGE_TAG = "wing-commander-gate-62-reference-image:local"
IMPLEMENT_WORKFLOW = ".github/workflows/implement.yml"
IMPLEMENT_JOB = "implement"
PREFLIGHT_STEPS = ("Preflight: gate-suite prerequisites (cycle)",
                   "Preflight: gate-suite prerequisites (retry)")
AGENT_STEPS = ("Implement and converge (cycle)",
               "Implement and converge (retry at escalation model)")
# The agent prompt's lint-tool sentence: every `backticked` command between
# these two markers is a tool the prompt tells the agent to use.
LINT_SENTENCE = ("Where the list above includes them:", "Lint the files")
# Tools the implement job installs for itself, before the preflight, in the
# named step -- not taken from the image, so stubbed / not required here.
JOB_INSTALLED = {"actionlint": "Install actionlint for the agent"}


def read_required_tools(root="."):
    tools = []
    with io.open(os.path.join(root, REQUIRED_TOOLS_FILE), encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            tools.append(line)
    return tools


def docker_available():
    return shutil.which("docker") is not None


def in_container():
    """True inside a Docker (/.dockerenv) or Podman (/run/.containerenv)
    container -- e.g. this repository's own implement job, whose container
    runs the gate suite with GITHUB_ACTIONS=true and no Docker."""
    return os.path.exists("/.dockerenv") or os.path.exists("/run/.containerenv")


def docker_missing_result(env, containerised=None):
    """-> (exit code, message) for a machine where docker is not on PATH.

    Off CI this is a clear skip (SF1): a maintainer running
    run-local-gates.py on a machine without Docker gets one skipped gate
    instead of a traceback that ends the whole sweep. On CI
    (GITHUB_ACTIONS=true) the same condition is a defect: the hosted runner
    image is expected to carry Docker, and if it ever stopped doing so this
    gate would otherwise pass silently over nothing, which is exactly the
    green check that proves less than it says.

    A CI job that itself runs inside a container is the exception: the
    implement stage runs this suite in its job container (#989), which has
    no Docker by design, and failing there would leave the suite red at
    every cycle start for a reason no agent can fix. lint-workflows.yml's
    own runs are not containerised, so they still fail on a missing binary.
    """
    if containerised is None:
        containerised = in_container()
    if env.get("GITHUB_ACTIONS") == "true" and containerised:
        return 0, ("Gate 62: skipped -- this CI job runs inside a container "
                   "with no Docker (e.g. the implement stage's job "
                   "container), so the reference image cannot be built here. "
                   "lint-workflows.yml runs this gate on a non-container "
                   "runner, where a missing docker binary fails it.")
    if env.get("GITHUB_ACTIONS") == "true":
        return 1, ("::error::Gate 62: docker is not installed or not on PATH "
                   "on a CI runner, so the e2e reference image cannot be built "
                   "and inspected. The runner image is expected to carry "
                   "Docker; a missing binary must fail this gate rather than "
                   "let it pass over nothing.")
    return 0, ("Gate 62: skipped -- docker is not installed or not on PATH. "
               "This check builds and inspects the reference image, so it "
               "cannot run without Docker; CI always has it. Install Docker "
               "to exercise this gate locally.")


def build_image(root, tag):
    """-> (True/False, log). Raises only for reasons other than a missing
    docker binary -- callers check docker_available() first so a
    Docker-less machine gets a clear skip (SF1) instead of an uncaught
    FileNotFoundError, which used to crash run-local-gates.py's whole
    sweep instead of just this one gate."""
    proc = subprocess.run(
        ["docker", "build", "-t", tag, os.path.join(root, DOCKERFILE_DIR)],
        capture_output=True, text=True,
    )
    return proc.returncode == 0, (proc.stdout + proc.stderr)


def check_tools(tag, tools):
    """-> (missing tools or None if no shell could be started, log tail)."""
    proc = subprocess.run(
        ["docker", "run", "--rm", "-e", "REQUIRED_TOOLS=" + " ".join(tools),
         "--entrypoint", "sh", tag, "-c",
         'for t in $REQUIRED_TOOLS; do command -v "$t" >/dev/null 2>&1 || '
         'echo "missing:$t"; done'],
        capture_output=True, text=True,
    )
    missing = [line.split("missing:", 1)[1]
               for line in proc.stdout.splitlines() if line.startswith("missing:")]
    if proc.returncode != 0 and not proc.stdout.strip():
        return None, (proc.stdout + proc.stderr)
    return missing, (proc.stdout + proc.stderr)


def read_implement_subject(root="."):
    """-> (preflight scripts {step name: run text}, lint tools, problems).

    Both read from implement.yml itself, so the gate keeps no copy of the
    preflight's prerequisite list or of the prompt's lint tools."""
    import yaml
    problems = []
    path = os.path.join(root, IMPLEMENT_WORKFLOW)
    with io.open(path, encoding="utf-8") as fh:
        wf = yaml.safe_load(fh) or {}
    steps = ((wf.get("jobs") or {}).get(IMPLEMENT_JOB) or {}).get("steps") or []
    by_name = {(st or {}).get("name"): (st or {}) for st in steps}
    preflights = {}
    for name in PREFLIGHT_STEPS:
        run = by_name.get(name, {}).get("run")
        if not run:
            problems.append(f"{IMPLEMENT_WORKFLOW} job {IMPLEMENT_JOB!r} has no "
                            f"step {name!r} with a run: block -- if it was "
                            f"renamed, update PREFLIGHT_STEPS here with it")
        else:
            preflights[name] = str(run)
    for tool, step in JOB_INSTALLED.items():
        if step not in by_name:
            problems.append(f"{IMPLEMENT_WORKFLOW} job {IMPLEMENT_JOB!r} has no "
                            f"step {step!r}, yet this gate stubs {tool} as "
                            f"installed by it -- update JOB_INSTALLED")
    lint_tools = []
    start, end = LINT_SENTENCE
    for name in AGENT_STEPS:
        prompt = " ".join(str((by_name.get(name, {}).get("with") or {})
                              .get("prompt", "")).split())
        i = prompt.find(start)
        j = prompt.find(end, i + 1) if i >= 0 else -1
        found = re.findall(r"`([A-Za-z][A-Za-z0-9_.-]*)`",
                           prompt[i + len(start):j]) if j > i >= 0 else []
        if not found:
            problems.append(f"{IMPLEMENT_WORKFLOW} step {name!r}: no "
                            f"`backticked` tool found between {start!r} and "
                            f"{end!r} in its prompt -- if the sentence was "
                            f"reworded, update LINT_SENTENCE here with it")
        lint_tools.extend(t for t in found if t not in lint_tools)
    return preflights, lint_tools, problems


# Runs one preflight step's text the way the job's `bash -e {0}` default
# runs it, in a scratch checkout holding a stub run-local-gates.py, with a
# stub for each JOB_INSTALLED tool ahead of the image's own PATH, and prints
# the step's $GITHUB_OUTPUT lines prefixed "output:".
PREFLIGHT_DRIVER = r"""
set -u
w=$(mktemp -d)
mkdir -p "$w/bin" "$w/work/.github/scripts"
: > "$w/work/.github/scripts/run-local-gates.py"
for t in $WC_JOB_INSTALLED; do
  printf '#!/bin/sh
exit 0
' > "$w/bin/$t"
  chmod +x "$w/bin/$t"
done
printf '%s
' "$WC_PREFLIGHT" > "$w/step.sh"
: > "$w/output"
: > "$w/summary"
cd "$w/work" || exit 97
GITHUB_OUTPUT="$w/output" GITHUB_STEP_SUMMARY="$w/summary"   PATH="$w/bin:$PATH" bash -e "$w/step.sh"
echo "rc:$?"
sed 's/^/output:/' "$w/output"
sed 's/^/summary:/' "$w/summary"
"""


def check_preflight(tag, name, script):
    """-> failure message or None. Runs one implement.yml preflight step
    inside the built image and requires ready=true."""
    proc = subprocess.run(
        ["docker", "run", "--rm", "-e", "WC_PREFLIGHT=" + script,
         "-e", "WC_JOB_INSTALLED=" + " ".join(sorted(JOB_INSTALLED)),
         "--entrypoint", "bash", tag, "-c", PREFLIGHT_DRIVER],
        capture_output=True, text=True,
    )
    outputs = {}
    for line in proc.stdout.splitlines():
        if line.startswith("output:") and "=" in line:
            k, v = line[len("output:"):].split("=", 1)
            outputs[k] = v
    if outputs.get("ready") == "true":
        return None
    missing = outputs.get("missing") or "(the step recorded no missing list)"
    return (f"the reference image fails {IMPLEMENT_WORKFLOW}'s {name!r} step "
            f"(ready={outputs.get('ready', '<unset>')}, missing: {missing}). "
            f"This repository's own implement jobs run in this image, so the "
            f"local gate suite would be skipped every cycle and no gate-run "
            f"task could be checked (#989). Install what is missing in "
            f"{DOCKERFILE_DIR}/Dockerfile -- {(proc.stdout + proc.stderr)[-1500:]}")


def scan(root=".", tag=IMAGE_TAG):
    failures = []
    tools = read_required_tools(root)
    preflights, lint_tools, problems = read_implement_subject(root)
    failures.extend(problems)
    ok, log = build_image(root, tag)
    if not ok:
        failures.append(
            f"docker build of {DOCKERFILE_DIR}/Dockerfile failed -- {log[-2000:]}")
        return failures
    try:
        missing, log = check_tools(tag, tools)
        if missing is None:
            failures.append(
                f"could not run a POSIX shell inside the built image to check its "
                f"prerequisites -- {log[-1000:]}")
        elif missing:
            failures.append(
                f"the reference image built from {DOCKERFILE_DIR}/Dockerfile is "
                f"missing required tool(s) named in {REQUIRED_TOOLS_FILE}: "
                + ", ".join(missing))
        for name, script in preflights.items():
            failure = check_preflight(tag, name, script)
            if failure:
                failures.append(failure)
        wanted = [t for t in lint_tools if t not in JOB_INSTALLED]
        if wanted:
            missing, log = check_tools(tag, wanted)
            if missing is None:
                failures.append(
                    f"could not run a POSIX shell inside the built image to check "
                    f"the implement prompt's lint tools -- {log[-1000:]}")
            elif missing:
                failures.append(
                    f"the reference image is missing lint tool(s) the implement "
                    f"agent prompt in {IMPLEMENT_WORKFLOW} tells the agent to use: "
                    + ", ".join(missing) + f" -- install them in "
                    f"{DOCKERFILE_DIR}/Dockerfile, or stop naming them in the prompt")
    finally:
        subprocess.run(["docker", "rmi", "-f", tag], capture_output=True, text=True)
    return failures


def _copy_subject(dst):
    shutil.copytree(DOCKERFILE_DIR, os.path.join(dst, DOCKERFILE_DIR))
    os.makedirs(os.path.dirname(os.path.join(dst, REQUIRED_TOOLS_FILE)), exist_ok=True)
    shutil.copy(REQUIRED_TOOLS_FILE, os.path.join(dst, REQUIRED_TOOLS_FILE))
    os.makedirs(os.path.dirname(os.path.join(dst, IMPLEMENT_WORKFLOW)), exist_ok=True)
    shutil.copy(IMPLEMENT_WORKFLOW, os.path.join(dst, IMPLEMENT_WORKFLOW))


def _drop_installs(root, packages):
    """Remove each package's own continuation line from the copied
    Dockerfile; -> the packages that had no such line (fixture drift)."""
    path = os.path.join(root, DOCKERFILE_DIR, "Dockerfile")
    with io.open(path, encoding="utf-8") as fh:
        lines = fh.readlines()
    kept = [ln for ln in lines if ln.strip().rstrip("\\").strip() not in packages]
    absent = [p for p in packages
              if not any(ln.strip().rstrip("\\").strip() == p for ln in lines)]
    with io.open(path, "w", encoding="utf-8") as fh:
        fh.writelines(kept)
    return absent


def self_test():
    problems = []

    # (0) the Docker-less decision. This self-test only runs where Docker is
    # present (CI), so it is the place the CI branch of
    # docker_missing_result is checked on every run.
    code, _message = docker_missing_result({"GITHUB_ACTIONS": "true"})
    if code != 1:
        problems.append("a missing docker binary on a CI runner (GITHUB_ACTIONS=true) "
                         "did NOT fail the gate")
    code, _message = docker_missing_result({})
    if code != 0:
        problems.append("a missing docker binary off CI was not a clear skip")
    code, _message = docker_missing_result({"GITHUB_ACTIONS": "true"}, containerised=True)
    if code != 0:
        problems.append("a missing docker binary inside a CI job's container (the "
                         "implement stage's gate-suite run) was not a clear skip")
    code, _message = docker_missing_result({"GITHUB_ACTIONS": "true"}, containerised=False)
    if code != 1:
        problems.append("a missing docker binary on a non-container CI runner did "
                         "NOT fail the gate")

    root = tempfile.mkdtemp(prefix="verify_gate_62_")
    try:
        # (a) the real Dockerfile and required-tools.txt, unmodified
        clean = os.path.join(root, "clean")
        _copy_subject(clean)
        got = scan(clean, tag=IMAGE_TAG + "-clean")
        if got:
            problems.append("clean copy of the real image FAILED: " + "; ".join(got))

        # (b) the Dockerfile silently drops one real tool's install -- the
        # exact gap Gate 23's textual-only check cannot see, since the
        # embedded REQUIRED_TOOLS= literal and required-tools.txt both stay
        # untouched here.
        drifted = os.path.join(root, "drifted")
        _copy_subject(drifted)
        dockerfile_path = os.path.join(drifted, DOCKERFILE_DIR, "Dockerfile")
        with io.open(dockerfile_path, encoding="utf-8") as fh:
            lines = fh.readlines()
        kept = [ln for ln in lines if ln.strip().rstrip("\\").strip() != "jq"]
        if len(kept) == len(lines):
            problems.append("fixture setup: expected the reference Dockerfile to "
                             "install jq on its own continuation line -- self-test "
                             "can no longer construct its drift fixture, update it "
                             "to drop a different tool")
        else:
            with io.open(dockerfile_path, "w", encoding="utf-8") as fh:
                fh.writelines(kept)
            got = scan(drifted, tag=IMAGE_TAG + "-drifted")
            if not any("jq" in g for g in got):
                problems.append(f"a Dockerfile that stopped installing jq was NOT "
                                 f"detected as missing jq; got: {got}")

        # (c) the Dockerfile drops what only this repository's implement jobs
        # need. yamllint depends on python3-yaml, so both go together, or
        # pyyaml would still arrive as a dependency.
        extras = os.path.join(root, "extras")
        _copy_subject(extras)
        absent = _drop_installs(extras, ("python3-yaml", "yamllint", "shellcheck"))
        if absent:
            problems.append("fixture setup: expected the reference Dockerfile to "
                             "install each of " + ", ".join(absent) + " on its "
                             "own continuation line -- update fixture (c)")
        else:
            got = scan(extras, tag=IMAGE_TAG + "-extras")
            pre = [g for g in got if "Preflight: gate-suite prerequisites" in g]
            if len(pre) != len(PREFLIGHT_STEPS) or not all("pyyaml" in g for g in pre):
                problems.append(f"a Dockerfile that stopped installing python3-yaml "
                                 f"was NOT failed by both implement preflight legs "
                                 f"naming pyyaml; got: {got}")
            lint = [g for g in got if "lint tool(s)" in g]
            if not (lint and "yamllint" in lint[0] and "shellcheck" in lint[0]):
                problems.append(f"a Dockerfile that stopped installing yamllint and "
                                 f"shellcheck was NOT failed by the lint-tool check "
                                 f"naming both; got: {got}")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    for p in problems:
        print(f"::error::Gate 62 self-test: {p}")
    if problems:
        return 1
    print("Gate 62 self-test: a clean build of the real image passes; a Dockerfile "
          "that silently stops installing a required tool, the gate suite's "
          "pyyaml, or a prompted lint tool fails, naming it.")
    return 0


def main(argv):
    if not docker_available():
        # A build-and-inspect check has nothing to inspect without Docker.
        # Off CI that is a clear skip (a maintainer running
        # run-local-gates.py on a machine without it); on CI it fails --
        # see docker_missing_result.
        code, message = docker_missing_result(os.environ)
        print(message)
        return code
    if "--self-test" in argv:
        return self_test()
    failures = scan(".")
    for f in failures:
        print(f"::error::Gate 62: {f}")
    print(f"Gate 62: the e2e reference image's tool set agrees with "
          f"{REQUIRED_TOOLS_FILE} and passes {IMPLEMENT_WORKFLOW}'s gate-suite "
          f"preflight and prompted lint tools; {len(failures)} failure(s).")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
