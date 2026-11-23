#!/usr/bin/env python3
"""Gate: the shared reviewer's trust boundaries hold (specs/127-shared-pr-reviewer,
SC-008 (a)-(d), FR-012, FR-022, FR-027).

  (a) the `code-run` job has `permissions: {}` and references no secret, and
      a hostile PR check finds no token or Actions variable in its
      environment;
  (b) nothing the PR's code writes reaches the staged result except its
      exit codes and output: the hostile check overwrites the result file
      and appends to GITHUB_ENV, GITHUB_OUTPUT and GITHUB_STEP_SUMMARY at
      once, and leaves a detached background writer that tries again after
      the check exits. The shipped code-run step is run as written, under
      bash, and none of it may have any effect, no process of the sandbox
      user may survive, and the background writer must never wake;
  (c) the only commands stage_code_run runs are the discovered named check
      and the default branch's run-local-gates.py;
  (d) neither agent job holds a write token, a web tool or a Bash tool.

The dynamic proof of (a) and (b) needs a Linux runner with passwordless
sudo (the code-run sandbox, wc_shared_review.UidSandbox). Under GitHub
Actions it is required; elsewhere, where the sandbox cannot be set up, it
is reported as not proven here and the static checks still run.

`--self-test` proves the static checks fail on a mutated workflow and that
the proof is required under Actions.
"""
import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import wc_shared_review  # noqa: E402

WORKFLOW = os.path.join(HERE, "..", "workflows", "shared-pr-reviewer.yml")
HOSTILE = os.path.join(HERE, "tests", "fixtures", "shared-review-hostile")
PROBE = "verify-probe-check.py"
WEB_TOOLS = ("WebSearch", "WebFetch")
RUNNER_FILES = ("GITHUB_ENV", "GITHUB_OUTPUT", "GITHUB_STEP_SUMMARY")
BACKGROUND_DELAY = 3


def _text(obj):
    return yaml.safe_dump(obj)


def code_run_step(wf):
    for step in ((wf.get("jobs") or {}).get("code-run") or {}).get("steps") or []:
        if " code-run " in " {0} ".format(str((step or {}).get("run") or "")).replace("\n", " "):
            return step
    return None


def static_problems(wf):
    problems = []
    jobs = wf.get("jobs") or {}
    code = jobs.get("code-run")
    if not isinstance(code, dict):
        return ["the callable has no code-run job"]
    if code.get("permissions") != {}:
        problems.append("code-run must declare `permissions: {}`")
    if "secrets" in _text(code) or "app-private-key" in _text(code):
        problems.append("code-run references a secret")
    step = code_run_step(wf)
    run = str((step or {}).get("run") or "")
    if step is None:
        problems.append("code-run has no step running wc_shared_review.py code-run")
    else:
        if "--out out/code-run.json" not in run:
            problems.append("code-run's result is not written by the runner side (--out)")
        if "mkdir -m 700 out" not in run:
            problems.append("code-run's result directory is not the runner's alone (mkdir -m 700 out)")
        if "> out/code-run.json" in run.split("||")[0]:
            problems.append("code-run's result is a shell redirect open while PR code runs")
    for name in ("find", "check"):
        job = jobs.get(name)
        if not isinstance(job, dict):
            problems.append("the callable has no {0} job".format(name))
            continue
        if job.get("permissions") != {"contents": "read"}:
            problems.append("{0} must hold only `contents: read`".format(name))
        text = _text(job)
        if "create-github-app-token" in text or "app-private-key" in text:
            problems.append("{0} mints or reads an App credential".format(name))
        for s in job.get("steps") or []:
            w = (s or {}).get("with") or {}
            if "default-allowed-tools" in w:
                allowed = [t.strip() for t in str(w["default-allowed-tools"]).split(",")]
                if any(t.startswith("Bash") or t in WEB_TOOLS or t in ("Write", "Edit") for t in allowed):
                    problems.append("{0} allows a Bash, web or write tool".format(name))
                disallowed = str(w.get("default-disallowed-tools", ""))
                for tool in WEB_TOOLS:
                    if tool not in disallowed:
                        problems.append("{0} does not disallow {1}".format(name, tool))
    return problems


def proof_required(environ):
    """The dynamic proof may be skipped only off Actions."""
    return environ.get("GITHUB_ACTIONS") == "true"


def sandbox_unavailable_reason():
    if os.name != "posix" or not shutil.which("bash"):
        return "not a POSIX host with bash"
    try:
        wc_shared_review.UidSandbox()._check_host()
    except wc_shared_review.SandboxUnavailable as exc:
        return str(exc)
    return None


def _reviewer_tree(dest):
    """The default branch's scripts, with a stub gate runner, so the proof
    does not run the whole gate suite against the hostile tree."""
    scripts = os.path.join(dest, ".github", "scripts")
    os.makedirs(scripts)
    for name in os.listdir(HERE):
        if name.endswith(".py"):
            shutil.copy2(os.path.join(HERE, name), scripts)
    with open(os.path.join(scripts, "run-local-gates.py"), "w", encoding="utf-8") as fh:
        fh.write("import sys\nprint('stub gate suite')\nsys.exit(3)\n")


def _read(path):
    try:
        with open(path, "rb") as fh:
            return fh.read()
    except OSError:
        return None


def dynamic_problems(wf):
    """Runs the shipped code-run step against the hostile tree (SC-008 (a), (b))."""
    step = code_run_step(wf)
    if step is None:
        return ["no code-run step to run"]
    problems = []
    work = tempfile.mkdtemp(prefix="wc-isolation-")
    alive = os.path.join(tempfile.gettempdir(), "wc-hostile-alive-" + uuid.uuid4().hex)
    try:
        os.chmod(work, 0o755)
        trees = os.path.join(work, "trees")
        shutil.copytree(HOSTILE, os.path.join(trees, "pr-tree"))
        _reviewer_tree(os.path.join(trees, "reviewer-tree"))
        os.makedirs(os.path.join(work, "input"))
        with open(os.path.join(work, "input", "added-files.txt"), "w", encoding="utf-8") as fh:
            fh.write(PROBE + "\n")
        env = dict(os.environ)
        runner_files = {}
        fake = os.path.join(work, "_runner_file_commands")
        for var in RUNNER_FILES:
            path = os.environ.get(var)
            if not path:
                os.makedirs(fake, exist_ok=True)
                path = os.path.join(fake, var.lower())
                open(path, "w").close()
                os.chmod(path, 0o644)
            env[var] = path
            runner_files[var] = path
        before = {var: _read(path) for var, path in runner_files.items()}
        result = os.path.join(work, "out", "code-run.json")
        targets = {"runner_files": list(runner_files.values()), "result": result,
                   "alive_marker": alive, "delay": BACKGROUND_DELAY}
        with open(os.path.join(trees, "pr-tree", "hostile-targets.json"), "w", encoding="utf-8") as fh:
            json.dump(targets, fh)
        # Secrets in the step's own environment must not reach the probe.
        env.update({"GH_TOKEN": "x", "ACTIONS_RUNTIME_TOKEN": "x", "ANTHROPIC_API_KEY": "x"})
        script = os.path.join(work, "step.sh")
        with open(script, "w", encoding="utf-8") as fh:
            fh.write(str(step.get("run")))
        proc = subprocess.run(["bash", "--noprofile", "--norc", "-eo", "pipefail", script], cwd=work,
                              env=env, capture_output=True, text=True, timeout=600)
        if proc.returncode != 0:
            problems.append("the code-run step failed ({0}): {1}".format(
                proc.returncode, (proc.stdout + proc.stderr)[-800:]))
        staged_at_end = _read(result)
        # Outlast the background writer before judging anything.
        time.sleep(BACKGROUND_DELAY + 3)
        staged = _read(result)
        if staged != staged_at_end:
            problems.append("the staged result changed after the code-run step ended")
        try:
            data = json.loads((staged or b"").decode("utf-8"))
        except ValueError:
            data = {}
        if data.get("status") != "staged":
            problems.append("the staged result is not `staged`: {0!r}".format((staged or b"")[:300]))
        named = data.get("named_check") or {}
        tail = named.get("output_tail", "")
        if "LEAKED:" not in tail:
            problems.append("the hostile probe did not run, so isolation is unproven")
        else:
            leaked = tail.split("LEAKED:")[-1].split("\n")[0].strip()
            if leaked:
                problems.append("variables reached the PR's check: " + leaked)
        if "BACKGROUND-STARTED" not in tail:
            problems.append("the hostile probe's background writer never started, so (b) is unproven")
        forged = tail.split("FORGED-AT-ONCE:")[-1].split("\n")[0].strip() if "FORGED-AT-ONCE:" in tail else ""
        if forged:
            problems.append("the PR's check wrote runner-side files: " + forged)
        if named.get("exit") in (0, None):
            problems.append("the failing hostile check was not staged as a non-zero exit")
        if (data.get("gate_suite") or {}).get("exit") != 3:
            problems.append("the gate suite's exit code was not staged as data")
        for var, path in runner_files.items():
            if _read(path) != before[var]:
                problems.append("{0} was written by the PR's code".format(var))
        if os.path.exists(alive):
            problems.append("a background process of the PR's code outlived the run")
        user = wc_shared_review.SANDBOX_USER
        if wc_shared_review.UidSandbox().live_pids():
            problems.append("a process of {0} is still running".format(user))
    finally:
        subprocess.run(["sudo", "-n", "rm", "-rf", "--one-file-system", work, alive], capture_output=True)
        shutil.rmtree(work, ignore_errors=True)
    return problems


def main():
    wf = yaml.safe_load(open(WORKFLOW, encoding="utf-8")) or {}
    problems = static_problems(wf)
    if "--self-test" in sys.argv:
        bad = 0
        mutations = {
            "code-run gains a secret": lambda w: w["jobs"]["code-run"].update(
                {"env": {"T": "${{ secrets.x }}"}}),
            "code-run loses its empty permissions": lambda w: w["jobs"]["code-run"].pop("permissions"),
            "find gains a write token": lambda w: w["jobs"]["find"].update(
                {"permissions": {"contents": "write"}}),
            "code-run's result goes back to a shell redirect": lambda w: code_run_step(w).update(
                {"run": "mkdir -p out\npython3 -I x.py code-run --pr-tree a --reviewer-tree b "
                        "--added-files c > out/code-run.json || true\n"}),
        }
        for label, mutate in mutations.items():
            clone = copy.deepcopy(wf)
            mutate(clone)
            if not static_problems(clone):
                print("::error::self-test: mutation not caught: " + label)
                bad += 1
        if not proof_required({"GITHUB_ACTIONS": "true"}) or proof_required({}):
            print("::error::self-test: the isolation proof is not required exactly under Actions")
            bad += 1
        return 1 if bad else (1 if problems else 0)
    reason = sandbox_unavailable_reason()
    if reason is None:
        problems += dynamic_problems(wf)
    elif proof_required(os.environ):
        problems.append("the code-run sandbox cannot be set up on this runner ({0}), "
                        "so SC-008 (a)/(b) is unproven".format(reason))
    else:
        print("note: SC-008 (a)/(b) not proven here: {0}; it is proven on the lint "
              "runner".format(reason))
    for p in problems:
        print("::error::verify-shared-review-isolation: " + p)
    if not problems:
        print("verify-shared-review-isolation: {0}".format(
            "static checks and the hostile code-run proof hold" if reason is None
            else "static checks hold"))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
