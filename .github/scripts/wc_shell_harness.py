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
     That is what Actions itself does (`bash -e {0}`, or `bash --noprofile
     --norc -eo pipefail {0}` for `shell: bash` -- NAMED_SHELLS below
     derives which for the step under test), and it is the only
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
import functools
import os
import shutil
import stat
import subprocess
import sys
import tempfile


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


# The Windows build of jq ends raw (-r) output lines with CRLF, and a
# harness that builds a path from `jq -r` output (as Gates 76-78 do) inherits
# a trailing CR on that platform while CI (Linux) stays green (#446, #459).
# The pipeline targets ubuntu-latest, so nothing shipped changes: this shim
# is written only where the local jq is observed to emit a CR, and strips
# it. ensure_jq() is the one place every such harness gets jq from, so this
# is that shim's only home -- see verify-metrics-persist-retry.py's
# case_jq_cr_shim_has_exactly_one_home for the gate that keeps it that way.
JQ_CR_SHIM = """#!/usr/bin/env bash
# jq whose lines never end in a carriage return (#446); the real jq is {real}.
# Only a CR at the end of a line goes: one inside a value is data.
"{real}" "$@" | sed 's/\\r$//'
exit "${{PIPESTATUS[0]}}"
"""


@functools.lru_cache(maxsize=1)
def _jq_emitting_cr(real):
    """The real jq's own answer never changes within one process, so a
    caller that re-probes on every ensure_jq() call (there can be several
    per gate) re-spawns jq to re-derive an already-known answer."""
    out = subprocess.run([real, "-nr", '"x"'], capture_output=True).stdout
    return b"\r" in out


# Set once _shim_jq_cr() has installed a shim dir, so a second call in the
# same process is a no-op rather than stacking another dir on PATH. Keying
# this off shutil.which("jq") instead is not reliable: on Windows the shim
# is written without a .exe suffix (it is a bash script, run by the bash
# under test, never by Windows directly) and shutil.which there generally
# will not resolve an extensionless name, so a caller that re-derives
# `real` on every ensure_jq() call would see the SAME real jq each time
# (correctly) but a fresh, unshimmed one -- and _shim_jq_cr would then
# mkdtemp and prepend again, growing PATH and leaking a tempdir per call.
_JQ_SHIM_DIR = None


def _shim_jq_cr(real):
    """Prepend a CR-stripping jq shim ahead of `real` on PATH if needed.

    Installs at most once per process (see _JQ_SHIM_DIR above); the one
    shim dir this creates is left for the OS to reclaim at process exit,
    matching the rest of this module's tempdirs (run_step's workdir/
    out_file/sum_file are the caller's to clean up, never this module's)."""
    global _JQ_SHIM_DIR
    if _JQ_SHIM_DIR is not None:
        return
    _JQ_SHIM_DIR = tempfile.mkdtemp(prefix="wc-jq-cr-shim-")
    path = os.path.join(_JQ_SHIM_DIR, "jq")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(JQ_CR_SHIM.format(real=real.replace("\\", "/")))
    os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    os.environ["PATH"] = _JQ_SHIM_DIR + os.pathsep + os.environ["PATH"]


def ensure_jq():
    """Put jq on PATH for the child shells, or say precisely what is missing.

    The shipped shell calls `jq` by name, so it must be on the PATH the child
    bash inherits — not merely installed somewhere. On ubuntu-latest it
    already is and this returns after the CR check on the first line.
    """
    real = shutil.which("jq")
    if not real:
        for cand in (os.path.join(os.environ.get("LOCALAPPDATA", ""),
                                  "Microsoft", "WinGet", "Links"),
                     r"C:\ProgramData\chocolatey\bin",
                     r"C:\Program Files\Git\usr\bin"):
            if cand and os.path.exists(os.path.join(cand, "jq.exe")):
                real = os.path.join(cand, "jq.exe")
                os.environ["PATH"] = cand + os.pathsep + os.environ["PATH"]
                break
        else:
            sys.exit("::error::jq is not on PATH. The shipped shell under "
                     "test calls it, so nothing here can run without it.")
    if _jq_emitting_cr(real):
        _shim_jq_cr(real)


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


# How the Actions runner turns a step's effective `shell:` into a command
# line (GitHub docs, "jobs.<job_id>.steps[*].shell"). NAMED_SHELLS and
# production_shell() are the ONE HOME of that mapping for every harness in
# this directory: run_step() derives the invocation from them for the step
# under test, and no gate passes shell flags of its own.
#
#   * `shell: bash` is NOT `bash -e`. The runner runs it as
#     `bash --noprofile --norc -eo pipefail {0}`, so a pipeline whose early
#     stage fails fails the step even when its last stage succeeds. Every
#     composite action's run: step here declares `shell: bash` (the runner
#     refuses a composite run: step without one), as do many workflow steps.
#   * A workflow step with no `shell:`, after job and then workflow
#     `defaults.run.shell`, runs as `bash -e {0}` on a hosted Linux runner
#     (errexit, no pipefail) and as `sh -e {0}` inside a job `container:`
#     (the runner execs sh there whatever the image ships -- see the
#     container-shell-safety skill).
#   * Any other value is a custom shell, run exactly as written with {0}
#     the script file -- substituted wherever it appears, inside an
#     argument too (`bash -c ". '{0}'"`), as the runner does; the runner
#     appends {0} when the template omits it. The `defaults.run.shell:
#     bash -e {0}` several workflows set is one of these, which is why a
#     step there that ALSO says `shell: bash` gets pipefail and its
#     neighbours do not.
#   * pwsh, powershell, cmd and python are named shells too, mapped here
#     so a step using one resolves to what the runner really runs. run_step
#     refuses every template whose program is not bash or sh (RUNNABLE_
#     SHELL_PROGRAMS): it writes the block, after a bash PATH preamble, to
#     a .sh file, which reproduces nothing else -- a pwsh step would fail
#     to exec here, and a python one would run the preamble as python.
NAMED_SHELLS = {
    "bash": ("bash", "--noprofile", "--norc", "-eo", "pipefail", "{0}"),
    "sh": ("sh", "-e", "{0}"),
    "pwsh": ("pwsh", "-command", ". '{0}'"),
    "powershell": ("powershell", "-command", ". '{0}'"),
    "cmd": ("%ComSpec%", "/D", "/E:ON", "/V:OFF", "/S", "/C", 'CALL "{0}"'),
    "python": ("python", "{0}"),
}
RUNNABLE_SHELL_PROGRAMS = ("bash", "sh")
UNSPECIFIED_SHELL_HOSTED = ("bash", "-e", "{0}")
UNSPECIFIED_SHELL_CONTAINER = ("sh", "-e", "{0}")


def _defaults_shell(doc):
    return (((doc or {}).get("defaults") or {}).get("run") or {}).get("shell")


def production_shell(step, job=None, workflow=None):
    """The argv template ({0} = the script file) the runner uses for `step`.

    For a workflow step pass its enclosing `job` and `workflow` dicts; for a
    composite action's step pass neither. Resolution order is the runner's:
    the step's `shell:`, the job's `defaults.run.shell`, the workflow's
    `defaults.run.shell`, then the platform default (container-aware).
    """
    import shlex
    shell = (step or {}).get("shell")
    if shell is None and job is not None:
        shell = _defaults_shell(job)
    if shell is None and workflow is not None:
        shell = _defaults_shell(workflow)
    if shell is None:
        if job is None and workflow is None:
            raise ValueError(
                "production_shell: a composite action's run: step has no "
                "shell: -- the runner refuses that step, so there is no "
                "production shell to reproduce")
        if (job or {}).get("container") is not None:
            return UNSPECIFIED_SHELL_CONTAINER
        return UNSPECIFIED_SHELL_HOSTED
    shell = str(shell).strip()
    if shell in NAMED_SHELLS:
        return NAMED_SHELLS[shell]
    argv = tuple(shlex.split(shell))
    return argv if any("{0}" in a for a in argv) else argv + ("{0}",)


def _shell_program(template):
    """The program a shell template execs, as a bare lowercase name
    (`/usr/bin/bash` and `C:\\...\\bash.exe` are both `bash`)."""
    prog = str(template[0]) if template else ""
    prog = prog.replace("\\", "/").rsplit("/", 1)[-1].lower()
    return prog[:-4] if prog.endswith(".exe") else prog


def _iter_steps(path):
    """Yield (step, job, workflow) for every step in workflow OR composite
    action `path`; job/workflow are None for a composite's steps, which is
    exactly the context production_shell() needs to tell the two apart."""
    import yaml
    doc = yaml.safe_load(open(path, encoding="utf-8")) or {}
    for job in (doc.get("jobs") or {}).values():
        for step in (job or {}).get("steps") or []:
            yield step or {}, job or {}, doc
    for step in (doc.get("runs") or {}).get("steps") or []:
        yield step or {}, None, None


def step_shell(path, name):
    """production_shell() of the step named `name` in `path` -- for a caller
    whose script is a synthetic stand-in for that step (a self-test's
    drifted copy) and so cannot be matched back to it by run_step."""
    for step, job, wf in _iter_steps(path):
        if step.get("name") == name:
            return production_shell(step, job, wf)
    sys.exit(f"::error file={path}::no step named {name!r}. If it was "
             f"renamed, update the workflow and its harness together.")


def _shipped_runs(root, paths):
    """[(run_text, argv, where)] for every `run:` step in `paths`."""
    out = []
    for path in paths:
        rel = os.path.relpath(path, root).replace(os.sep, "/")
        for step, job, wf in _iter_steps(path):
            run = step.get("run")
            if not isinstance(run, str):
                continue
            try:
                argv = production_shell(step, job, wf)
            except ValueError:
                continue    # a composite step the runner itself would refuse
            out.append((run, list(argv),
                        f"{rel}: {step.get('name') or '<unnamed>'}"))
    return out


@functools.lru_cache(maxsize=1)
def shipped_step_shells():
    """[(run_text, argv, where, template_regex_or_None, significant_lines)]
    for every `run:` step in .github/workflows/ and .github/actions/
    (composites at any depth)."""
    import glob
    import hashlib
    import json
    import re
    root = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))
    paths = sorted(
        glob.glob(os.path.join(root, ".github", "workflows", "*.y*ml"))
        # Any depth: the composites under .github/actions/_shared/ are
        # shipped steps too.
        + glob.glob(os.path.join(root, ".github", "actions", "**",
                                 "action.y*ml"), recursive=True))
    # Parsing every workflow costs ~3s, paid by each gate process that
    # traces a script -- dozens per suite run. The parse is cached on disk
    # under a key over this module and every file read, so any edit to
    # either misses the cache. JSON, not pickle: the temp dir is shared.
    # JSON alone is not enough there: the cached argv is what run_step
    # execs, and the key is computable from public files, so a cache file
    # this user did not write (or one anyone else can write) is ignored.
    # O_NONBLOCK and the S_ISREG check: a FIFO planted at the name would
    # otherwise block the open forever.
    key = hashlib.sha256()
    for path in [os.path.abspath(__file__)] + paths:
        key.update(path.encode("utf-8") + b"\0")
        with open(path, "rb") as fh:
            key.update(fh.read() + b"\0")
    cache = os.path.join(tempfile.gettempdir(),
                         f"wc-shipped-step-shells-{key.hexdigest()[:24]}.json")
    try:
        fd = os.open(cache, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                     | getattr(os, "O_NONBLOCK", 0))
        with os.fdopen(fd, encoding="utf-8") as fh:
            st = os.fstat(fh.fileno())
            if not stat.S_ISREG(st.st_mode):
                raise OSError("cache is not a regular file")
            if hasattr(os, "geteuid") and (st.st_uid != os.geteuid()
                                           or st.st_mode & 0o022):
                raise OSError("cache not written by this user")
            runs = json.load(fh)
    except (OSError, ValueError):
        runs = _shipped_runs(root, paths)
        tmp = None
        try:
            fd, tmp = tempfile.mkstemp(dir=os.path.dirname(cache),
                                       suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(runs, fh)
            os.replace(tmp, cache)
        except OSError:
            # an unwritable temp dir (or another user's file at `cache`)
            # only costs the next process a parse
            if tmp is not None and os.path.exists(tmp):
                os.remove(tmp)
    out = []
    for run, argv, where in runs:
        # A harness substitutes the `${{ }}` expressions the runner would
        # have expanded before handing the block over, so the shipped
        # text is a template for what arrives: each one is a wildcard.
        rx = None
        if "${{" in run:
            parts = re.split(r"\$\{\{.*?\}\}", run, flags=re.S)
            rx = re.compile("(?s)" + ".*?".join(map(re.escape, parts)))
        out.append((run, tuple(argv), where, rx, _significant_lines(run)))
    return out


def _significant_lines(text):
    return frozenset(ln.strip() for ln in text.splitlines()
                     if len(ln.strip()) >= 8 and not ln.strip().startswith("#"))


# A script that matches no shipped step verbatim is a harness's MUTATED copy
# of one (a self-test's drifted line, an injected stub call) far more often
# than anything else, and it must run under the shell of the step it was
# cut from. Every shipped step holding at least this share of its
# significant lines is a plausible origin; below it the match means nothing
# and run_step refuses rather than guess.
#
# The plausible origins must ALL run under one shell -- it is not enough
# that the single nearest one does. Near-copies of a step live in several
# workflows under different shells (implement.yml's and cleanup.yml's "Mark
# lifecycle record stalled" share 7 of 9 lines; one is `bash -e`, the other
# `shell: bash`), so "nearest wins" let a one-line mutation, or an unrelated
# edit to the other copy, silently move a script to the other shell and
# change a gate's verdict. Disagreement refuses instead; the caller names
# its step with shell=step_shell(path, name).
NEAREST_STEP_MIN_SHARE = 0.5


def match_shell(script, entries):
    """(argv, where) for the step in `entries` (shipped_step_shells() rows)
    that `script` is, or was cut from, else (None, why). The pure core of
    shell_for_script, so the rule can be tested on entries of one's own."""
    texts = {script, script if script.endswith("\n") else script + "\n"}
    hits = {(e[1], e[2]) for e in entries if e[0] in texts}
    if not hits:
        hits = {(e[1], e[2]) for e in entries if e[3] is not None
                and any(e[3].fullmatch(t) for t in texts)}
    if not hits:
        lines = _significant_lines(script)
        scored = [(len(lines & e[4]) / len(lines), e[1], e[2])
                  for e in entries] if lines else []
        best = max((sc for sc, _a, _w in scored), default=0.0)
        if best < NEAREST_STEP_MIN_SHARE:
            return None, (f"no shipped run: step shares as much as "
                          f"{NEAREST_STEP_MIN_SHARE:.0%} of its lines "
                          f"(best {best:.0%})")
        plausible = sorted(((sc, argv, where) for sc, argv, where in scored
                            if sc >= NEAREST_STEP_MIN_SHARE),
                           key=lambda t: (-t[0], t[2]))
        if len({argv for _sc, argv, _w in plausible}) > 1:
            return None, (
                "it shares at least "
                f"{NEAREST_STEP_MIN_SHARE:.0%} of its lines with shipped "
                "steps that run under different shells: " + "; ".join(
                    f"{where} ({sc:.0%}, {' '.join(argv)})"
                    for sc, argv, where in plausible[:4]))
        hits = {(argv, where) for sc, argv, where in scored if sc == best}
    argvs = {argv for argv, _w in hits}
    wheres = sorted(where for _a, where in hits)
    if len(argvs) > 1:
        return None, ("it matches shipped steps that run under different "
                      "shells: " + "; ".join(wheres[:4]))
    return argvs.pop(), wheres[0]


@functools.lru_cache(maxsize=512)
def shell_for_script(script):
    """(argv, where) for the shipped step `script` came from, else
    (None, why). Exact text first, then `${{ }}`-substituted text, then the
    shipped steps sharing its lines (see NEAREST_STEP_MIN_SHARE)."""
    return match_shell(script, shipped_step_shells())


def run_step(bash, script, workdir, env_extra, runner_temp, path_prepend=None,
             shell=None):
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

    `shell` is the production argv template (production_shell() /
    step_shell()) to run the block under. Omitted, it is derived from the
    shipped step `script` is, or was cut from (shell_for_script): a
    composite's `shell: bash` step runs with pipefail exactly as on the
    runner, a workflow step with no `shell:` without it. A script that
    cannot be traced to one shipped step raises RuntimeError rather than
    guess -- pass shell=step_shell(path, name) for the step it stands in for.
    """
    if shell is None:
        shell_template, where = shell_for_script(script)
        if shell_template is None:
            raise RuntimeError(
                "run_step: cannot tell which production shell this script "
                f"runs under: {where}. Pass shell=step_shell(path, name) "
                "for the shipped step it stands in for.\n"
                f"  script begins: {script[:200]!r}")
    else:
        shell_template = tuple(shell)
    if _shell_program(shell_template) not in RUNNABLE_SHELL_PROGRAMS:
        raise RuntimeError(
            f"run_step: cannot reproduce `{' '.join(shell_template)}`: the "
            "harness runs a step as a bash or sh script file and nothing "
            "else (see NAMED_SHELLS). Test this step with a harness that "
            "runs its real interpreter.\n"
            f"  script begins: {script[:200]!r}")
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

    # The step runs under the shell production gives IT -- see NAMED_SHELLS
    # for why that is `bash -eo pipefail` for a `shell: bash` step and
    # `bash -e` for one that names no shell. {0} is a file; see this
    # module's docstring for why passing the script any other way breaks.
    script_file = os.path.join(workdir, "step.sh")
    with open(script_file, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(preamble)
        fh.write(script)
    argv = [{"bash": bash, "sh": shutil.which("sh") or "sh"}.get(arg, arg)
            for arg in shell_template]
    argv = [arg.replace("{0}", script_file.replace("\\", "/"))
            for arg in argv]
    proc = subprocess.run(argv,
                          cwd=workdir, env=env, capture_output=True,
                          text=True, encoding="utf-8", errors="replace")

    outputs = parse_github_output(out_file)
    with open(sum_file, encoding="utf-8") as fh:
        summary = fh.read()
    return proc.returncode, proc.stdout + proc.stderr, outputs, summary


def extract_quoted_var(path, varname):
    """The single-quoted bash string assigned to `varname='...'` in `path`.

    specs/046-watchdog-supervision-collectors leg-2: several gates fixture a
    workflow step's jq filter by retyping it as a second `FILTER='...'`
    literal in the gate script itself, which is exactly the copy constitution
    VIII forbids — mutation testing showed each one stayed green through a
    shipped-line break because the gate never looked at the shipped text at
    all. This extracts the live single-quoted assignment instead, so the
    caller can feed jq the text watchdog.yml actually ships.
    """
    import re
    text = open(path, encoding="utf-8").read()
    m = re.search(re.escape(varname) + r"='\n(.*?)\n[ \t]*'\n", text, re.S)
    if not m:
        sys.exit(f"::error file={path}::could not find a bash single-quoted "
                 f"assignment to {varname!r} in {path}. If it was renamed or "
                 f"reshaped, update the workflow and its harness together — "
                 f"do not let the harness fall back to a hand-typed copy.")
    return m.group(1)


# gh's observed two-stream error shape (FR-012, specs/091-gh-api-error-
# capture). Re-verify this comment's version list whenever a stub built
# from gh_error_stub_arm starts failing against a newer `gh` on a
# maintainer's machine -- that is the signal the two-stream behaviour
# changed, not that the stub is wrong.
# Observed: gh 2.63.2, gh 2.81.0 (#497 code review, 2026-08).
def gh_error_stub_arm(match_glob, status, message, stderr_extra=""):
    """One `case` arm's body simulating a failed covered `gh` read: stdout
    gets the raw JSON error body (the `--jq` filter, if any, is never
    applied -- this is the whole point, #497), stderr gets
    `gh: <message> (HTTP <status>)` plus any `stderr_extra`, exit code 1.

    `match_glob` is the caller's own `case "$*" in` pattern, recorded here
    only so a reader of the call site sees which invocation this arm is
    for -- this function returns just the body between `)` and `;;`, so
    callers keep authoring their own dispatch the way every existing
    STUB_GH already does. This is not a second stub-authoring framework,
    only the one repeated fragment CLAUDE.md's single-home rule applies
    to (research.md D8).
    """
    extra = "\n    " + stderr_extra if stderr_extra else ""
    return (
        "    # {0}\n"
        '    printf \'%s\\n\' \'{{"message":"{1}","documentation_url":'
        '"https://docs.github.com/rest","status":"{2}"}}\'\n'
        '    echo "gh: {1} (HTTP {2})" >&2{3}\n'
        "    exit 1\n"
    ).format(match_glob, message, status, extra)


def find_step(path, name):
    """The step dict named `name` in workflow OR composite action `path`.

    A workflow's steps live under `jobs.<id>.steps`; a composite action
    (no `jobs:` at all) keeps its single step list under `runs.steps`
    instead (specs/041-implement-stall-notice's wing-commander-chain-stop-
    notice and its callers both need step lookups, one of each shape) — so
    this checks both rather than making every composite-testing harness
    carry its own duplicate of this function.
    """
    for step, _job, _wf in _iter_steps(path):
        if step.get("name") == name:
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
