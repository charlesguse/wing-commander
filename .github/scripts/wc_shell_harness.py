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
  4. A stub executable prepended to PATH does not necessarily win. Git for
     Windows' bin\\bash.exe wrapper prepends /mingw64/bin:/usr/bin ahead of
     whatever PATH the harness supplied, so a fixture `git` or `date` loses
     to the real one bundled there — while a `gh` or `jq` stub wins, because
     nothing by that name lives in the prepended dirs. The failure shape is
     nasty: the scenario runs green against the REAL tool and the gate
     either passes while proving nothing or fails on the assertion that the
     fixture ever fired. run_step re-applies the caller's own PATH additions
     inside the step, inferred from env_extra's PATH or taken verbatim from
     path_prepend=; when a PATH is present but neither applies it raises
     rather than silently skip the preamble. Using usr\\bin\\bash.exe
     instead is not an option — invoked directly it prepends nothing,
     leaving no coreutils (grep/sed/mv/head) on PATH at all.

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


def parse_github_output(path):
    """Parse a $GITHUB_OUTPUT file the way the runner does.

    Actions accepts TWO forms, and a harness that knows only the first is the
    "green while checking nothing" shape these gates exist to prevent:

        name=value                      single line
        name<<DELIM \n ...\n DELIM      multi-line (what actions/core emits
                                        for any value containing a newline)

    Read with a bare `if "=" in line`, the second form yields a junk key
    (`name<<EOF`) plus one stray entry per content line, and the output the
    caller then asserts on is simply absent — so the assertion passes against
    an empty string. No step under test publishes a multi-line output today;
    the first one that does would land on exactly that.

    An unterminated heredoc is a hard error, not a shrug: the runner rejects
    it too, and a silently-truncated value is the same class of lie.
    """
    outputs = {}
    with open(path, encoding="utf-8") as fh:
        lines = fh.read().splitlines()

    i = 0
    while i < len(lines):
        line = lines[i]
        i += 1
        eq, lt = line.find("="), line.find("<<")
        # Whichever delimiter comes FIRST decides the form, so `k=a<<b` is a
        # single-line value and not a malformed heredoc.
        if lt != -1 and (eq == -1 or lt < eq):
            key, delim = line[:lt], line[lt + 2:]
            body = []
            while i < len(lines) and lines[i] != delim:
                body.append(lines[i])
                i += 1
            if i >= len(lines):
                sys.exit(f"::error::{path}: output {key!r} opened a "
                         f"{delim!r} heredoc that is never closed. The runner "
                         f"rejects this too — fix the step, do not let the "
                         f"harness assert against a truncated value.")
            i += 1                      # consume the closing delimiter
            outputs[key] = "\n".join(body)
        elif eq != -1:
            outputs[line[:eq]] = line[eq + 1:]
    return outputs


def run_step(bash, script, workdir, env_extra, runner_temp, path_prepend=None):
    """Run one extracted `run:` block; return (rc, output, outputs, summary).

    `outputs` is the parsed $GITHUB_OUTPUT, `summary` the raw
    $GITHUB_STEP_SUMMARY text — the two side channels a step publishes
    through, both of which the caller usually needs to assert on.

    `path_prepend`, if given, is used verbatim as the dirs to re-prepend
    ahead of the Git-for-Windows bash wrapper's own dirs (docstring point 4)
    and inference is skipped entirely. Pass it when env_extra['PATH'] was
    not built the blessed way — appended instead of prepended, built from a
    PATH captured earlier, or separator-normalized — so the inference below
    would not apply to it.

    When path_prepend is omitted and env_extra carries a PATH, the prepend
    is inferred by checking that the caller's PATH ends with this process's
    PATH *as of this call* (os.environ['PATH'] read right here, not at
    import time) and diffing off the non-matching prefix. That comparison
    base is deliberately the live os.environ['PATH'], because ensure_jq()
    can mutate it (prepending a jq dir) before run_step is ever called —
    callers that build their env_extra PATH as
    `bindir + os.pathsep + os.environ['PATH']` after any ensure_jq() call
    stay in agreement with this base and the inference succeeds.

    If a PATH is present in env_extra but neither path_prepend nor the
    inference applies, this raises RuntimeError instead of silently running
    the step with no preamble: a stub bindir that loses quietly to
    /mingw64/bin would pass green while proving nothing, the exact shape
    the module docstring's point 4 warns about.
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

    # Docstring point 4: on Windows the bash wrapper prepends its own dirs
    # ahead of env["PATH"], demoting the caller's stub dirs below the real
    # git/date. Isolate what the caller ADDED in front of the process PATH
    # and re-prepend exactly that inside the step, leaving every other
    # entry's order untouched (blanket re-prepending the full PATH would
    # instead promote Windows' own find.exe/sort.exe above coreutils). On
    # a POSIX bash the preamble re-prepends dirs that are already first —
    # a no-op — so CI behavior is unchanged.
    #
    # `added` is path_prepend verbatim when given (inference skipped); else
    # the inferred diff between env_extra's PATH and the CURRENT
    # os.environ['PATH'] (see run_step's docstring for why "current" is the
    # right comparison base — ensure_jq() can have mutated it already). A
    # PATH that doesn't fit either case is a caller that will silently lose
    # its stub to /mingw64/bin, so this raises instead of leaving `added`
    # unset.
    preamble = ""
    caller_path, base_path = env_extra.get("PATH"), os.environ.get("PATH", "")
    if path_prepend is not None:
        added = path_prepend
    elif caller_path and base_path and caller_path.endswith(base_path):
        added = caller_path[:len(caller_path) - len(base_path)].rstrip(os.pathsep)
    elif caller_path:
        raise RuntimeError(
            "run_step: env_extra['PATH'] does not end with this process's "
            "current os.environ['PATH'], so the harness cannot infer what "
            "to re-prepend past the Git-for-Windows bash wrapper (module "
            "docstring point 4). Running the step with no preamble in this "
            "situation would let a fixture git/date stub silently lose to "
            "the real one in /mingw64/bin, and the gate would pass green "
            "while proving nothing. Fix by either building the caller's "
            "PATH as `bindir + os.pathsep + os.environ['PATH']` at call "
            "time — after any ensure_jq() call, since that can mutate "
            "os.environ['PATH'] — or by passing path_prepend= explicitly.\n"
            f"  env_extra['PATH']:   {caller_path!r}\n"
            f"  os.environ['PATH']:  {base_path!r}")
    else:
        added = None

    if added:
        env["WC_HARNESS_PATH_PREPEND"] = added
        preamble = (
            '# wc_shell_harness preamble (not part of the step under test):\n'
            '# re-apply the harness-supplied PATH additions ahead of the dirs\n'
            '# the Git-for-Windows bash wrapper prepends. See run_step.\n'
            'if [ -n "${WC_HARNESS_PATH_PREPEND:-}" ]; then\n'
            '  if command -v cygpath >/dev/null 2>&1; then\n'
            '    PATH="$(cygpath -up "$WC_HARNESS_PATH_PREPEND"):$PATH"\n'
            '  else\n'
            '    PATH="$WC_HARNESS_PATH_PREPEND:$PATH"\n'
            '  fi\n'
            '  export PATH\n'
            'fi\n')

    # GitHub's default shell for a `run:` step with no `shell:` key on Linux
    # is `bash -e {0}` — errexit, and NOT pipefail. Adding -o pipefail would
    # make these harnesses stricter than production. {0} is a file; see this
    # module's docstring for why passing the script any other way breaks.
    script_file = os.path.join(workdir, "step.sh")
    with open(script_file, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(preamble)
        fh.write(script)
    proc = subprocess.run([bash, "-e", script_file.replace("\\", "/")],
                          cwd=workdir, env=env, capture_output=True,
                          text=True, encoding="utf-8", errors="replace")

    outputs = parse_github_output(out_file)
    with open(sum_file, encoding="utf-8") as fh:
        summary = fh.read()
    return proc.returncode, proc.stdout + proc.stderr, outputs, summary


def find_step(path, name):
    """The step dict named `name` in workflow OR composite action `path`.

    A workflow's steps live under `jobs.<id>.steps`; a composite action
    (no `jobs:` at all) keeps its single step list under `runs.steps`
    instead (specs/041-implement-stall-notice's wing-commander-chain-stop-
    notice and its callers both need step lookups, one of each shape) — so
    this checks both rather than making every composite-testing harness
    carry its own duplicate of this function.
    """
    import yaml
    doc = yaml.safe_load(open(path, encoding="utf-8")) or {}
    for job in (doc.get("jobs") or {}).values():
        for step in (job or {}).get("steps") or []:
            if (step or {}).get("name") == name:
                return step
    for step in (doc.get("runs") or {}).get("steps") or []:
        if (step or {}).get("name") == name:
            return step
    sys.exit(f"::error file={path}::no step named {name!r}. If it was renamed, "
             f"update the workflow and its harness together — do not drop the "
             f"check.")


def find_job(path, job_id):
    """The job dict keyed `job_id` in workflow `path` — `needs:`/`if:` and all.

    `find_step` above answers "what does this STEP do"; this answers "when
    does this JOB run at all". Gate 28 (specs/041-implement-stall-notice)
    needs the latter: it evaluates a survivor job's own `if:` against
    modelled `needs.*` values, which requires the job-level dict, not a step
    within it. `job_id` is the YAML key (e.g. "stalled"), not the `name:`
    field — jobs are addressed by key everywhere else in this file's own
    `needs:` handling, and `wf.get("jobs")` is already a dict keyed the same
    way.
    """
    import yaml
    wf = yaml.safe_load(open(path, encoding="utf-8")) or {}
    job = (wf.get("jobs") or {}).get(job_id)
    if job is None:
        sys.exit(f"::error file={path}::no job keyed {job_id!r}. If it was "
                 f"renamed, update the workflow and its harness together — "
                 f"do not drop the check.")
    return job
