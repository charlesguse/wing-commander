#!/usr/bin/env python3
"""Shared plumbing for harnesses that EXECUTE shell extracted from workflows.

WHY THIS EXISTS
---------------
Several gates in lint-workflows.yml work the same way: pull a `run:` block out
of a shipped workflow, feed it synthetic inputs, and assert on what it does.
Running the shipped block (rather than a copy of it) is the whole point — gate
5 exists because a copy sat green for weeks while checking a filter that did
not ship.

The mechanics of "run this block the way the runner would" are identical for
every such gate, and three of them are non-obvious enough that each new
harness rediscovered them the hard way — usually as a wall of failures that
looks like a defect in the workflow and is not:

  1. `bash` on PATH is not always a bash that can run this. On Windows it is
     typically C:\\Windows\\System32\\bash.exe, the WSL launcher: a separate
     Linux VM that does not inherit the Windows process environment (that
     needs WSLENV) and cannot see Windows temp paths. Every RUNNER_TEMP,
     GITHUB_OUTPUT and GITHUB_STEP_SUMMARY arrives empty and every scenario
     fails on a missing file.
  2. The script must be handed over as a FILE, not as `bash -c <string>`.
     That is what Actions itself does (`bash -e {0}`), and it is the only
     thing that survives Windows argv quoting: an MSYS bash re-parses the
     Windows command line and treats backslashes as escapes, so a jq program
     containing gsub("\\\\|"; "\\\\|") arrives as gsub("\\|"; "\\|") and jq
     rejects it as an invalid escape.
  3. Output must be decoded as UTF-8 explicitly. The pipeline's sentinels
     carry a warning sign and em dashes; Python's text mode defaults to the
     locale codec, and cp1252 cannot decode them, which kills the subprocess
     reader thread mid-run.

On ubuntu-latest all three resolve on the first try and cost one extra
subprocess for the bash probe. None of this changes what CI does; it only
makes these gates runnable on a maintainer's machine, which is the difference
between a gate that gets exercised before it is pushed and one that does not.

Set WC_BASH to override the bash choice.
"""
import os
import shutil
import subprocess
import sys


def use_utf8_stdout():
    """Make this process's own output able to carry what it is quoting.

    lint-workflows gate 6 solves the same problem by holding its prints to
    ASCII, which works because it only ever prints its own words. These
    harnesses cannot: their failure messages quote workflow text verbatim,
    and the pipeline's sentinels contain a warning sign and em dashes. On a
    Windows console (cp1252) the encode fails and the gate dies inside the
    print instead of reporting its verdict — turning a real finding into a
    traceback. Replacing unencodable characters keeps the verdict readable.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass          # already wrapped, or not a reconfigurable stream


def _inherits_env(exe):
    """True if `exe` is a bash that receives this process's environment.

    Every harness here rests on handing the shipped shell its env vars, so a
    bash that silently drops them must be rejected at selection time rather
    than diagnosed a dozen scenarios later.
    """
    try:
        proc = subprocess.run(
            [exe, "-c", 'printf %s "$WC_BASH_PROBE"'],
            env={**os.environ, "WC_BASH_PROBE": "inherited"},
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=60)
    except (OSError, subprocess.SubprocessError):
        return False
    return proc.returncode == 0 and proc.stdout.strip() == "inherited"


def resolve_bash():
    """First bash on the candidate list that actually inherits the env."""
    candidates = [
        os.environ.get("WC_BASH"),
        shutil.which("bash"),
        r"C:\Program Files\Git\bin\bash.exe",
        r"C:\Program Files\Git\usr\bin\bash.exe",
        r"C:\Program Files (x86)\Git\bin\bash.exe",
    ]
    seen = set()
    for cand in candidates:
        if not cand or cand in seen:
            continue
        seen.add(cand)
        if os.path.exists(cand) and _inherits_env(cand):
            return cand
    sys.exit(
        "::error::no usable bash found. Tried: "
        + ", ".join(repr(c) for c in candidates if c)
        + ". On Windows, `bash` on PATH is typically the WSL launcher, which "
          "does not inherit this process's environment; install Git for "
          "Windows or point WC_BASH at a POSIX bash.")


def ensure_jq():
    """Put jq on PATH for the child shells, or say precisely what is missing.

    The shipped shell calls `jq` by name, so it must be on the PATH the child
    bash inherits — not merely installed somewhere. On ubuntu-latest it
    already is and this returns on the first line.
    """
    if shutil.which("jq"):
        return
    for cand in (os.path.join(os.environ.get("LOCALAPPDATA", ""),
                              "Microsoft", "WinGet", "Links"),
                 r"C:\ProgramData\chocolatey\bin",
                 r"C:\Program Files\Git\usr\bin"):
        if cand and os.path.exists(os.path.join(cand, "jq.exe")):
            os.environ["PATH"] = cand + os.pathsep + os.environ["PATH"]
            return
    sys.exit("::error::jq is not on PATH. The shipped shell under test calls "
             "it, so nothing here can run without it.")


def run_step(bash, script, workdir, env_extra, runner_temp):
    """Run one extracted `run:` block; return (rc, output, outputs, summary).

    `outputs` is the parsed $GITHUB_OUTPUT, `summary` the raw
    $GITHUB_STEP_SUMMARY text — the two side channels a step publishes
    through, both of which the caller usually needs to assert on.
    """
    out_file = os.path.join(workdir, "gh_output")
    sum_file = os.path.join(workdir, "gh_summary")
    open(out_file, "w").close()
    open(sum_file, "w").close()

    env = dict(os.environ)
    env.update({"RUNNER_TEMP": runner_temp,
                "GITHUB_OUTPUT": out_file,
                "GITHUB_STEP_SUMMARY": sum_file})
    env.update(env_extra)

    # GitHub's default shell for a `run:` step with no `shell:` key on Linux
    # is `bash -e {0}` — errexit, and NOT pipefail. Adding -o pipefail would
    # make these harnesses stricter than production. {0} is a file; see this
    # module's docstring for why passing the script any other way breaks.
    script_file = os.path.join(workdir, "step.sh")
    with open(script_file, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(script)
    proc = subprocess.run([bash, "-e", script_file.replace("\\", "/")],
                          cwd=workdir, env=env, capture_output=True,
                          text=True, encoding="utf-8", errors="replace")

    outputs = {}
    with open(out_file, encoding="utf-8") as fh:
        for line in fh:
            if "=" in line:
                k, v = line.rstrip("\n").split("=", 1)
                outputs[k] = v
    with open(sum_file, encoding="utf-8") as fh:
        summary = fh.read()
    return proc.returncode, proc.stdout + proc.stderr, outputs, summary


def find_step(path, name):
    """The step dict named `name` in the single job of workflow `path`."""
    import yaml
    wf = yaml.safe_load(open(path, encoding="utf-8")) or {}
    for job in (wf.get("jobs") or {}).values():
        for step in (job or {}).get("steps") or []:
            if (step or {}).get("name") == name:
                return step
    sys.exit(f"::error file={path}::no step named {name!r}. If it was renamed, "
             f"update the workflow and its harness together — do not drop the "
             f"check.")
