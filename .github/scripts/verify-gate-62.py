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
# The implement prompt's gate-suite paragraph names the suite command; the
# interpreter word in front of the script is a command the agent will run.
SUMMARY_STEPS = ("Summarize gate-suite outcome (cycle)",
                 "Summarize gate-suite outcome (retry)")
SUITE_COMMAND = re.compile(r"`([A-Za-z][A-Za-z0-9_.-]*) \.github/scripts/run-local-gates\.py")
# Set "true" in the implement job's container: env -- see docker_missing_result.
DOCKERLESS_ENV = "WC_GATE_SUITE_DOCKERLESS"


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


def docker_missing_result(env):
    """-> (exit code, message) for a machine where docker is not on PATH.

    Off CI this is a clear skip (SF1): a maintainer running
    run-local-gates.py on a machine without Docker gets one skipped gate
    instead of a traceback that ends the whole sweep. On CI
    (GITHUB_ACTIONS=true) the same condition is a defect: the hosted runner
    image is expected to carry Docker, and if it ever stopped doing so this
    gate would otherwise pass silently over nothing, which is exactly the
    green check that proves less than it says.

    The one exception is a job that declares, by setting DOCKERLESS_ENV to
    "true", that it runs the suite inside a container with no Docker by
    design: implement.yml's implement job sets it in its container: env
    (#989), since failing there would leave the suite red at every cycle
    start for a reason no agent can fix. It is an explicit opt-out rather
    than container sniffing, so a CI job that merely happens to run in a
    container still fails here; scan() checks that implement.yml keeps it.
    """
    if env.get("GITHUB_ACTIONS") == "true" and env.get(DOCKERLESS_ENV) == "true":
        return 0, (f"Gate 62: skipped -- this CI job sets {DOCKERLESS_ENV}=true: "
                   f"it runs the gate suite inside a container with no Docker "
                   f"(the implement job, #989), so the reference image cannot be "
                   f"built here. lint-workflows.yml runs this gate where Docker "
                   f"is present, and a missing binary fails it there.")
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
    """-> (preflight scripts {step name: run text}, prompted commands, problems).

    Prompted commands are the suite interpreter the prompt's gate-suite
    paragraph names plus the lint tools its lint sentence names. Both are
    read from implement.yml itself, so the gate keeps no copy of the
    preflight's prerequisite list or of the prompt's commands."""
    import yaml
    problems = []
    path = os.path.join(root, IMPLEMENT_WORKFLOW)
    with io.open(path, encoding="utf-8") as fh:
        wf = yaml.safe_load(fh) or {}
    job = (wf.get("jobs") or {}).get(IMPLEMENT_JOB) or {}
    steps = job.get("steps") or []
    by_name = {(st or {}).get("name"): (st or {}) for st in steps}
    index = {(st or {}).get("name"): i for i, st in enumerate(steps)}
    container_env = (job.get("container") or {}).get("env") or {} \
        if isinstance(job.get("container"), dict) else {}
    if str(container_env.get(DOCKERLESS_ENV)) != "true":
        problems.append(f"{IMPLEMENT_WORKFLOW} job {IMPLEMENT_JOB!r} no longer sets "
                        f"{DOCKERLESS_ENV}: \"true\" in its container: env, so "
                        f"this gate fails the gate suite the job runs in its "
                        f"Docker-less container at every cycle start (#989)")
    preflights = {}
    for name in PREFLIGHT_STEPS:
        run = by_name.get(name, {}).get("run")
        if not run:
            problems.append(f"{IMPLEMENT_WORKFLOW} job {IMPLEMENT_JOB!r} has no "
                            f"step {name!r} with a run: block -- if it was "
                            f"renamed, update PREFLIGHT_STEPS here with it")
        elif "${{" in str(run) or by_name[name].get("env"):
            problems.append(f"{IMPLEMENT_WORKFLOW} step {name!r} now uses an "
                            f"expression or an env: block, which this gate "
                            f"cannot reproduce when it runs the step's text "
                            f"inside the image -- extend check_preflight first")
        else:
            preflights[name] = str(run)
    for tool, step in JOB_INSTALLED.items():
        run = str(by_name.get(step, {}).get("run", ""))
        late = [n for n in PREFLIGHT_STEPS
                if n in index and index.get(step, len(steps)) > index[n]]
        if step not in by_name or tool not in run or late:
            problems.append(f"{IMPLEMENT_WORKFLOW} job {IMPLEMENT_JOB!r} has no "
                            f"step {step!r} that installs {tool} ahead of "
                            f"{', '.join(late) or 'the preflight steps'}, yet "
                            f"this gate stubs {tool} as installed by it -- "
                            f"update JOB_INSTALLED")
    commands = []
    for name in SUMMARY_STEPS:
        found = SUITE_COMMAND.findall(str(by_name.get(name, {}).get("run", "")))
        if not found:
            problems.append(f"{IMPLEMENT_WORKFLOW} step {name!r}: no "
                            f"`<interpreter> .github/scripts/run-local-gates.py` "
                            f"in its prompt paragraph -- update SUITE_COMMAND")
        commands.extend(t for t in found if t not in commands)
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
        commands.extend(t for t in found if t not in commands)
    return preflights, commands, problems


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
  printf '#!/bin/sh\nexit 0\n' > "$w/bin/$t"
  chmod +x "$w/bin/$t"
done
printf '%s\n' "$WC_PREFLIGHT" > "$w/step.sh"
: > "$w/output"
cd "$w/work" || exit 97
GITHUB_OUTPUT="$w/output" GITHUB_STEP_SUMMARY=/dev/null \
  PATH="$w/bin:$PATH" bash -e "$w/step.sh"
echo "rc:$?"
sed 's/^/output:/' "$w/output"
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
    preflights, commands, problems = read_implement_subject(root)
    failures.extend(problems)
    wanted = [t for t in commands if t not in JOB_INSTALLED and t not in tools]
    ok, log = build_image(root, tag)
    if not ok:
        failures.append(
            f"docker build of {DOCKERFILE_DIR}/Dockerfile failed -- {log[-2000:]}")
        return failures
    try:
        # One container start probes required-tools.txt and the prompted
        # commands together; the misses are reported per list.
        missing, log = check_tools(tag, tools + wanted)
        if missing is None:
            failures.append(
                f"could not run a POSIX shell inside the built image to check its "
                f"prerequisites -- {log[-1000:]}")
            missing = []
        req_missing = [t for t in missing if t in tools]
        if req_missing:
            failures.append(
                f"the reference image built from {DOCKERFILE_DIR}/Dockerfile is "
                f"missing required tool(s) named in {REQUIRED_TOOLS_FILE}: "
                + ", ".join(req_missing))
        # The legs are pinned identical but for the leg name by
        # verify-implement-gate-suite-preflight.py, so a leg whose text only
        # differs by that name is not run a second time.
        seen = set()
        for name, script in preflights.items():
            key = script.replace("retry", "cycle")
            if key in seen:
                continue
            seen.add(key)
            failure = check_preflight(tag, name, script)
            if failure:
                failures.append(failure)
        missing = [t for t in missing if t in wanted]
        if missing:
            failures.append(
                f"the reference image is missing command(s) the implement "
                f"agent prompt in {IMPLEMENT_WORKFLOW} tells the agent to run: "
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


def _static_self_test(root):
    """-> problems: each implement.yml drift read_implement_subject must report."""
    import yaml
    problems = []
    cases = []

    def drop_env(wf):
        wf["jobs"][IMPLEMENT_JOB]["container"]["env"].pop(DOCKERLESS_ENV)
    cases.append(("the container: env opt-out dropped", drop_env, DOCKERLESS_ENV))

    def late_install(wf):
        steps = wf["jobs"][IMPLEMENT_JOB]["steps"]
        i = next(i for i, st in enumerate(steps)
                 if st.get("name") == JOB_INSTALLED["actionlint"])
        steps.append(steps.pop(i))
    cases.append(("the actionlint install moved after the preflight", late_install,
                  JOB_INSTALLED["actionlint"]))

    def expression(wf):
        st = next(st for st in wf["jobs"][IMPLEMENT_JOB]["steps"]
                  if st.get("name") == PREFLIGHT_STEPS[0])
        st["run"] = "echo ${{ github.sha }}\n" + st["run"]
    cases.append(("an expression in the preflight", expression, PREFLIGHT_STEPS[0]))

    def no_suite_command(wf):
        st = next(st for st in wf["jobs"][IMPLEMENT_JOB]["steps"]
                  if st.get("name") == SUMMARY_STEPS[1])
        st["run"] = st["run"].replace(".github/scripts/run-local-gates.py", "the suite")
    cases.append(("the suite command dropped from a prompt paragraph",
                  no_suite_command, SUMMARY_STEPS[1]))

    _, _, base = read_implement_subject(".")
    if base:
        problems.append("static fixture base already has problems: " + "; ".join(base))
        return problems
    for label, mutate, needle in cases:
        d = os.path.join(root, "static")
        shutil.rmtree(d, ignore_errors=True)
        os.makedirs(os.path.dirname(os.path.join(d, IMPLEMENT_WORKFLOW)))
        with io.open(IMPLEMENT_WORKFLOW, encoding="utf-8") as fh:
            wf = yaml.safe_load(fh)
        mutate(wf)
        with io.open(os.path.join(d, IMPLEMENT_WORKFLOW), "w", encoding="utf-8") as fh:
            yaml.safe_dump(wf, fh, allow_unicode=True, sort_keys=False)
        _, _, got = read_implement_subject(d)
        if not any(needle in g for g in got):
            problems.append(f"{label} was NOT reported (expected a problem naming "
                            f"{needle!r}); got: {got}")
    return problems


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
    code, _message = docker_missing_result({"GITHUB_ACTIONS": "true", DOCKERLESS_ENV: "true"})
    if code != 0:
        problems.append(f"a missing docker binary in a CI job that sets {DOCKERLESS_ENV}=true "
                         f"(the implement job's container) was not a clear skip")
    code, _message = docker_missing_result({DOCKERLESS_ENV: "false", "GITHUB_ACTIONS": "true"})
    if code != 1:
        problems.append(f"a missing docker binary on CI with {DOCKERLESS_ENV} not 'true' "
                         f"did NOT fail the gate")

    root = tempfile.mkdtemp(prefix="verify_gate_62_")
    try:
        # (s) static drift in implement.yml, no image needed: each edit must
        # surface as a problem from read_implement_subject.
        problems.extend(_static_self_test(root))

        # (a) the real Dockerfile, required-tools.txt and implement.yml, unmodified
        clean = os.path.join(root, "clean")
        _copy_subject(clean)
        got = scan(clean, tag=IMAGE_TAG + "-clean")
        if got:
            problems.append("clean copy of the real image FAILED: " + "; ".join(got))

        # (b) one drifted build: the Dockerfile silently drops jq -- the
        # exact gap Gate 23's textual-only check cannot see, since the
        # embedded REQUIRED_TOOLS= literal and required-tools.txt both stay
        # untouched here -- and every package only this repository's
        # implement jobs need. yamllint depends on python3-yaml, so both go
        # together, or pyyaml would still arrive as a dependency.
        drifted = os.path.join(root, "drifted")
        _copy_subject(drifted)
        dropped = ("jq", "python3-yaml", "python-is-python3", "yamllint", "shellcheck")
        absent = _drop_installs(drifted, dropped)
        if absent:
            problems.append("fixture setup: expected the reference Dockerfile to "
                             "install each of " + ", ".join(absent) + " on its "
                             "own continuation line -- self-test can no longer "
                             "construct its drift fixture, update it")
        else:
            got = scan(drifted, tag=IMAGE_TAG + "-drifted")
            req = [g for g in got if REQUIRED_TOOLS_FILE in g]
            if not (req and "jq" in req[0]):
                problems.append(f"a Dockerfile that stopped installing jq was NOT "
                                 f"detected as missing jq; got: {got}")
            pre = [g for g in got if "Preflight: gate-suite prerequisites" in g]
            if not pre or not all("pyyaml" in g for g in pre):
                problems.append(f"a Dockerfile that stopped installing python3-yaml "
                                 f"was NOT failed by the implement preflight "
                                 f"naming pyyaml; got: {got}")
            cmds = [g for g in got if "command(s) the implement" in g]
            if not (cmds and all(t in cmds[0].split(": ", 1)[-1].split(" -- ")[0]
                                 for t in ("yamllint", "shellcheck", "python"))):
                problems.append(f"a Dockerfile that stopped installing yamllint, "
                                 f"shellcheck and python-is-python3 was NOT failed by "
                                 f"the prompted-command check naming all three; "
                                 f"got: {got}")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    for p in problems:
        print(f"::error::Gate 62 self-test: {p}")
    if problems:
        return 1
    print("Gate 62 self-test: a clean build of the real image passes; a Dockerfile "
          "that silently stops installing a required tool, the gate suite's "
          "pyyaml, or a prompted command fails, naming it; implement.yml drift "
          "the gate depends on is reported.")
    return 0


def main(argv):
    if not docker_available():
        # A build-and-inspect check has nothing to inspect without Docker.
        # Off CI that is a clear skip (a maintainer running
        # run-local-gates.py on a machine without it); on CI it fails --
        # see docker_missing_result. The implement.yml drift checks need no
        # image, so they still run here -- including where the skip itself
        # depends on implement.yml's opt-out.
        if "--self-test" in argv:
            static = _static_self_test(tempfile.mkdtemp(prefix="verify_gate_62_"))
        else:
            static = read_implement_subject(".")[2]
        for p in static:
            print(f"::error::Gate 62: {p}")
        code, message = docker_missing_result(os.environ)
        print(message)
        return 1 if static else code
    if "--self-test" in argv:
        return self_test()
    failures = scan(".")
    for f in failures:
        print(f"::error::Gate 62: {f}")
    print(f"Gate 62: the e2e reference image's tool set agrees with "
          f"{REQUIRED_TOOLS_FILE} and passes {IMPLEMENT_WORKFLOW}'s gate-suite "
          f"preflight and has every command its agent prompt names; {len(failures)} failure(s).")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
