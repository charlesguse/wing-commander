#!/usr/bin/env python3
"""Gate 48 -- the shellcheck pass over the opt-in list, and the list's closure.

Two checks that used to run only on a workflow_dispatch release, as
inline bash in release.yml's Gate 1a ("pass 2"), now run on every pull
request and in run-local-gates.py as well -- and release.yml calls this
same script, so the release-time answer and the PR-time answer cannot
drift (the Gate 31 arrangement). Issue #291; the gap bit twice:

  2026-08-20  pr-conversation.yml (specs/033) shipped as a published
              stage in neither list below. Every release dispatch from
              that merge onwards went red on the closure check.
  2026-09-08  #286 added private-image-dogfood.yml, again in neither
              list, and gave every stage a container.credentials
              expression whose two actionlint diagnostics pass 1
              counted but pass 2's hand-written -ignore list did not
              know. The v2.7.0 dispatch failed on both; #290 fixed the
              symptoms, this fixes the timing.

THE CLOSURE CHECK (#149)
------------------------
The shellcheck pass is an opt-IN: SHELL_LINTED names the files it
covers, and #149 is the ticket for widening it. An opt-in list is
exactly the shape #149 was about, so the exemption is stated rather
than implied: every published stage (wc_published_stages.py, the same
derivation Gate 7 and release.yml use -- a hardcoded stage list is what
caused #149) must be in SHELL_LINTED or in SHELL_EXEMPT with a reason,
and a new stage cannot become exempt by being forgotten. Both lists are
stale-checked the way stage-invariant-waivers.json is: an exemption for
a file that is no longer a published stage fails, a linted file that no
longer exists fails, a file on both lists fails, and an empty
derivation fails rather than reading as a clean pass.

THE SHELLCHECK PASS (release.yml pass 2)
----------------------------------------
Every bash/sh `run:` step of every SHELL_LINTED file goes through
shellcheck at --severity=warning: the gate blocks on real problems, not
style/info nits. The pass used to be actionlint's own shellcheck
integration; this script drives shellcheck directly and reproduces
that integration's contract line for line (actionlint 1.7.7
rule_shellcheck.go): the shell is the step's `shell:`, else the job's
or workflow's `defaults.run.shell`, else bash (pwsh on a literal
windows runner label), and only bash/sh scripts are linted; `${{ }}`
expressions are replaced by underscores of the same length before
linting; the runner's own prologue (`set -eo pipefail` for bash,
`set -e` for sh) is prepended; and the same six codes are excluded
(SC1091 sourced files, and the constant-expression / unassigned-
variable / one-iteration-loop codes that the placeholders provoke).

Why not just call actionlint with -shellcheck: its process runner
writes the whole script into the child's stdin pipe BEFORE starting
the child (process.go, cmdExecution.run), and a Windows anonymous pipe
holds 4 KiB, so every run: block over 4 KiB blocks forever on a
maintainer's machine -- five of the eleven linted files do -- while
the 64 KiB Linux pipe hides it on the runner. Measured 2026-09-11;
the threshold is exact. Nothing is lost by the move: pass 2's
actionlint schema/expression lint over these eleven files was a
strict subset of pass 1 (verify-actionlint.py, every workflow file),
and with actionlint out of pass 2 there is no second -ignore list for
pass 1's counted allowances to drift from. That was the second half
of the 2026-09-08 failure; it is now impossible by construction.

Pyflakes: actionlint's integration also ran pyflakes over
`shell: python` steps when a pyflakes was on PATH, silently skipping
otherwise. No linted file has such a step, and this gate fails the day
one does (shell_python_steps), which is the moment to pin pyflakes the
way shellcheck is pinned below rather than lint by luck of the image.

SHELLCHECK AVAILABILITY
-----------------------
This gate never consults PATH: wc_actionlint.ensure_shellcheck()
downloads the pinned release (koalaman/shellcheck v0.10.0, Windows zip
or linux/darwin tar.xz) into the same temp cache Gate 46 uses for
actionlint, and runs that binary by path. Offline, the download fails
loudly and so does the gate; it is not skippable by being unreachable.
The self-test's positive fixture is what proves shellcheck is engaged
rather than skipped.

USAGE
-----
    python3 .github/scripts/verify-stage-shell-lint.py
    python3 .github/scripts/verify-stage-shell-lint.py --self-test
"""
import concurrent.futures
import json
import os
import re
import subprocess
import sys
import tempfile

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_actionlint import ensure_shellcheck  # noqa: E402
from wc_published_stages import published_stages  # noqa: E402
from wc_shell_harness import use_utf8_stdout  # noqa: E402

# The opt-in. release.yml is not a published stage (workflow_dispatch),
# but it is release-blocking bash and has always been linted here.
SHELL_LINTED = tuple(
    f".github/workflows/{name}.yml" for name in (
        "intake", "clarify", "plan", "tasks", "implement", "finalize",
        "cleanup", "rebase", "metrics-persist", "private-image-dogfood",
        "release"))

# Published stages knowingly outside the shellcheck pass (issue #149).
# Anything published and NOT in SHELL_LINTED must be here, with the
# reason, so the exemption is a decision someone wrote down rather than a
# file nobody added.
SHELL_EXEMPT = {
    ".github/workflows/watchdog.yml":
        "Agent-bearing stage predating the opt-in; widening the pass to "
        "it is #149's scope, not a release-blocking gate's.",
    ".github/workflows/auto-update-spec-kit.yml":
        "Same as watchdog.yml: waits on #149 rather than opting into "
        "shellcheck untested in a release-blocking gate.",
    ".github/workflows/pr-conversation.yml":
        "specs/033. Exempt because this check caught it: it shipped as a "
        "published stage without joining either list, and turned every "
        "release dispatch red from that merge onwards -- the 2026-08-20 "
        "attempt included, which is how it was found. Exempting it changed "
        "nothing about what is linted (pass 2 had never seen it); it wrote "
        "the decision down and unblocked releases. An agent-bearing stage of "
        "watchdog's size and shape, so it waits on #149 with the other two.",
}

SHELLCHECK_OPTS = "--severity=warning"
# actionlint 1.7.7 rule_shellcheck.go, verbatim: the codes its
# placeholder substitution and CI-only sources would otherwise provoke.
SHELLCHECK_EXCLUDES = "SC1091,SC2194,SC2050,SC2154,SC2157,SC2043"
# The key may open a step (`- shell: python`) or follow one.
SHELL_PYTHON_RE = re.compile(r"^[ \t]*(?:-[ \t]+)?shell:[ \t]*[\"']?python", re.M)
EXPR_RE = re.compile(r"\$\{\{.*?\}\}", re.S)


def closure_errors(stages, linted, exempt, root="."):
    """The list-closure rules, as a pure function over the three sets.

    `stages` is the derived published-stage set; `linted` and `exempt`
    are the two opt lists. Returns the failure strings; empty means the
    lists are closed over the fleet and stale-free.
    """
    errors = []
    if not stages:
        errors.append(
            "no workflow declares on.workflow_call -- the closure check "
            "checked nothing. Either the published stages moved or the "
            "derivation (wc_published_stages.py) has broken.")
    both = sorted(set(linted) & set(exempt))
    for f in both:
        errors.append(f"{f} is in both SHELL_LINTED and SHELL_EXEMPT; "
                      f"pick one.")
    for f in linted:
        if not os.path.isfile(os.path.join(root, f)):
            errors.append(f"{f} is in SHELL_LINTED but does not exist -- "
                          f"a stale entry; remove it or fix the path.")
    for f in exempt:
        if f not in stages:
            errors.append(f"{f} is in SHELL_EXEMPT but is not a published "
                          f"stage -- a stale exemption; remove it.")
    for f in stages:
        if f not in linted and f not in exempt:
            errors.append(
                f"{f} is a published stage but is in neither the shellcheck "
                f"list nor the declared exemption list. Add it to "
                f"SHELL_LINTED, or to SHELL_EXEMPT with a note on the "
                f"tracking issue -- a new stage must not become exempt by "
                f"being forgotten (#149).")
    return errors


def shell_python_steps(files, root="."):
    """Linted files carrying a `shell: python` step -- pyflakes' subject."""
    hits = []
    for f in files:
        with open(os.path.join(root, f), encoding="utf-8") as fh:
            if SHELL_PYTHON_RE.search(fh.read()):
                hits.append(f)
    return hits


def sanitize_expressions(script):
    """`${{ ... }}` -> underscores of the same length (actionlint's
    sanitizeExpressionsInScript): spaces would change the syntax
    (`if ${{ x }}; then`), underscores keep it parseable, and the same
    length keeps shellcheck's columns honest."""
    return EXPR_RE.sub(lambda m: "_" * len(m.group(0)), script)


def _shell_name(shell):
    """actionlint's getShellName reduced to what shellcheck can lint:
    "bash", "sh", or None for any other shell."""
    if shell in ("bash", "sh"):
        return shell
    if shell.startswith("bash "):
        return "bash"
    if shell.startswith("sh "):
        return "sh"
    return None


def _default_shell(job):
    runs_on = job.get("runs-on")
    labels = [runs_on] if isinstance(runs_on, str) else \
        list(runs_on) if isinstance(runs_on, list) else \
        list((runs_on or {}).get("labels") or []) \
        if isinstance(runs_on, dict) else []
    if any(isinstance(l, str) and "windows" in l.lower() for l in labels):
        return "pwsh"
    return "bash"


def _node_lines(path):
    """{(job id, step index): 1-based line of that step's `run:` key},
    read off the YAML node tree so a finding can name the line the way
    actionlint does; the values come from safe_load in run_blocks()."""
    with open(path, encoding="utf-8") as fh:
        root = yaml.compose(fh)
    lines = {}
    if not isinstance(root, yaml.MappingNode):
        return lines
    for k, v in root.value:
        if k.value != "jobs" or not isinstance(v, yaml.MappingNode):
            continue
        for jk, jv in v.value:
            if not isinstance(jv, yaml.MappingNode):
                continue
            for sk, sv in jv.value:
                if sk.value != "steps" or not isinstance(sv, yaml.SequenceNode):
                    continue
                for i, step in enumerate(sv.value):
                    if not isinstance(step, yaml.MappingNode):
                        continue
                    for pk, _ in step.value:
                        if pk.value == "run":
                            lines[(jk.value, i)] = pk.start_mark.line + 1
    return lines


def run_blocks(path):
    """Every shellcheck-able `run:` step of a workflow, resolved the way
    actionlint resolves it.

    -> [(job id, step index, step name, shell, script, line)], shell in
    {"bash", "sh"}. Steps whose shell is anything else are left out,
    exactly as actionlint leaves them out.
    """
    with open(path, encoding="utf-8") as fh:
        wf = yaml.safe_load(fh) or {}
    lines = _node_lines(path)
    wf_shell = ((wf.get("defaults") or {}).get("run") or {}).get("shell")
    out = []
    for jid, job in (wf.get("jobs") or {}).items():
        job = job or {}
        job_shell = ((job.get("defaults") or {}).get("run") or {}).get("shell")
        for i, step in enumerate(job.get("steps") or []):
            step = step or {}
            run = step.get("run")
            if run is None:
                continue
            shell = step.get("shell") or job_shell or wf_shell \
                or _default_shell(job)
            sh = _shell_name(str(shell))
            if sh is None:
                continue
            out.append((jid, i, str(step.get("name") or ""), sh, str(run),
                        lines.get((jid, i), 0)))
    return out


def shellcheck_script(shellcheck, sh, script):
    """shellcheck's JSON findings for one script, run as actionlint runs
    it: --norc, -x, the six excludes, the runner prologue prepended, and
    SHELLCHECK_OPTS set here unconditionally -- the severity floor is
    part of what this gate IS, and a maintainer's shell must not be
    able to loosen or tighten it.

    Fed as UTF-8 bytes through a pipe the child is already reading (the
    subprocess module starts the process before it writes), which is
    the difference from actionlint's runner on Windows.
    """
    setup = "set -eo pipefail" if sh == "bash" else "set -e"
    payload = f"{setup}\n{sanitize_expressions(script)}\n".encode("utf-8")
    cmd = [shellcheck, "--norc", "-f", "json", "-x", "--shell", sh,
           "-e", SHELLCHECK_EXCLUDES, "-"]
    env = dict(os.environ, SHELLCHECK_OPTS=SHELLCHECK_OPTS)
    proc = subprocess.run(cmd, input=payload, capture_output=True, env=env)
    stdout = proc.stdout.decode("utf-8", errors="replace")
    # 0 is clean and 1 is "findings"; 2/3/4 mean shellcheck did not run
    # the script (bad option, unsupported shell, internal error) and its
    # stdout is empty -- which must not read as "no findings", the exact
    # silent-skip shape this gate exists to rule out.
    if proc.returncode not in (0, 1):
        sys.exit(f"shellcheck exited {proc.returncode} without linting the "
                 f"script: {proc.stderr.decode('utf-8', 'replace').strip()!r}")
    try:
        findings = json.loads(stdout or "[]")
    except json.JSONDecodeError:
        sys.exit(f"could not parse shellcheck's JSON output (exit "
                 f"{proc.returncode}): stdout={stdout!r} "
                 f"stderr={proc.stderr.decode('utf-8', 'replace')!r}")
    if not isinstance(findings, list):
        sys.exit(f"unexpected shellcheck output shape: {stdout!r}")
    return findings


def lint_files(shellcheck, files, jobs=8):
    """Diagnostic lines, actionlint's format, for every bash/sh run:
    step of `files`. The line in `SC####:level:LINE:COL` is relative to
    the script with the one-line prologue subtracted, as actionlint
    reports it."""
    blocks = [(f,) + b for f in files for b in run_blocks(f)]

    def one(block):
        f, jid, i, name, sh, script, line = block
        out = []
        for e in shellcheck_script(shellcheck, sh, script):
            msg = str(e.get("message", "")).rstrip(".")
            out.append(f"{f}:{line}:9: shellcheck reported issue in this "
                       f"script (job {jid}, step {i + 1}"
                       f"{' ' + repr(name) if name else ''}): "
                       f"SC{e.get('code')}:{e.get('level')}:"
                       f"{int(e.get('line', 1)) - 1}:{e.get('column')}: "
                       f"{msg}")
        return out

    diags = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as pool:
        for lines in pool.map(one, blocks):
            diags.extend(lines)
    return len(blocks), diags


def run_gate():
    stages = published_stages()
    errors = closure_errors(stages, SHELL_LINTED, SHELL_EXEMPT)
    for f in shell_python_steps([f for f in SHELL_LINTED
                                 if os.path.isfile(f)]):
        errors.append(
            f"{f} has a `shell: python` step, and this gate lints bash/sh "
            f"only. Pin a pyflakes the way wc_actionlint.py pins shellcheck "
            f"and lint it, or the step goes unlinted.")
    blocks, diags = 0, []
    if not errors:
        # Only once the lists are sound: linting a list with a missing
        # file would fail on the open() on top of the closure error that
        # already names it.
        blocks, diags = lint_files(ensure_shellcheck(), SHELL_LINTED)
        for line in diags:
            print(line)
        if diags:
            errors.append(
                f"shellcheck ({SHELLCHECK_OPTS}) reported {len(diags)} "
                f"finding(s) over the shell-linted files.")
        if blocks == 0:
            errors.append(
                "the shell-linted files contain no bash/sh run: step -- "
                "this pass linted nothing. Either every step moved to "
                "another shell or run_blocks() has broken.")
    for e in errors:
        print(f"::error::{e}")
    print(f"Gate 48: {len(stages)} published stage(s), {len(SHELL_LINTED)} "
          f"shell-linted file(s) ({blocks} run: step(s)), "
          f"{len(SHELL_EXEMPT)} exempt, {len(diags)} finding(s).")
    return 1 if errors else 0


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


STAGE_HEAD = ("on:\n"
              "  workflow_call:\n"
              "jobs:\n"
              "  a:\n"
              "    runs-on: ubuntu-latest\n"
              "    steps:\n")


def self_test():
    """The closure rules fire on each shape they exist to catch, and the
    shellcheck pass is actually engaged -- not silently skipped -- at
    the severity, with the substitutions, and over the steps this gate
    claims.
    """
    failures = 0

    def check(name, cond, detail=""):
        nonlocal failures
        if cond:
            print(f"PASS {name}")
        else:
            failures += 1
            print(f"FAIL {name} {detail}")

    # --- closure, over a throwaway repository root ---------------------
    with tempfile.TemporaryDirectory() as td:
        wf = os.path.join(td, ".github", "workflows")
        for name in ("s1", "s2", "s3"):
            _write(os.path.join(wf, f"{name}.yml"),
                   STAGE_HEAD + "      - run: echo ok\n")
        _write(os.path.join(wf, "dispatch.yml"),
               "on: workflow_dispatch\njobs:\n  a:\n"
               "    runs-on: ubuntu-latest\n    steps:\n"
               "      - run: echo ok\n")
        stages = published_stages(td)
        # published_stages(root) returns root-prefixed paths; the lists
        # are repo-relative, so strip the root the way run_gate sees it.
        stages = [s[len(td.replace(os.sep, "/")) + 1:] for s in stages]
        check("fixture derives three published stages",
              stages == [".github/workflows/s1.yml",
                         ".github/workflows/s2.yml",
                         ".github/workflows/s3.yml"], f"got {stages!r}")
        linted = (".github/workflows/s1.yml", ".github/workflows/dispatch.yml")
        exempt = {".github/workflows/s2.yml": "reason"}
        errs = closure_errors(stages, linted, exempt, root=td)
        check("an unlisted published stage fails the closure",
              len(errs) == 1 and "s3.yml is a published stage" in errs[0],
              f"got {errs!r}")
        errs = closure_errors(stages, linted + (".github/workflows/s3.yml",),
                              exempt, root=td)
        check("listing it (a non-stage dispatch file alongside) is clean",
              not errs, f"got {errs!r}")
        errs = closure_errors(stages, linted + (".github/workflows/s3.yml",),
                              dict(exempt, **{".github/workflows/dispatch.yml": "r"}),
                              root=td)
        check("an exemption for a non-stage is a stale exemption",
              any("stale exemption" in e for e in errs), f"got {errs!r}")
        errs = closure_errors(stages, linted + (".github/workflows/s3.yml",
                                                ".github/workflows/gone.yml"),
                              exempt, root=td)
        check("a linted file missing from disk is a stale entry",
              any("stale entry" in e for e in errs), f"got {errs!r}")
        errs = closure_errors(stages, linted + (".github/workflows/s2.yml",
                                                ".github/workflows/s3.yml"),
                              exempt, root=td)
        check("a file on both lists is refused",
              any("both SHELL_LINTED and SHELL_EXEMPT" in e for e in errs),
              f"got {errs!r}")
        errs = closure_errors([], linted, exempt, root=td)
        check("an empty derivation is a failure, not a clean pass",
              any("checked nothing" in e for e in errs), f"got {errs!r}")
        _write(os.path.join(wf, "py.yml"),
               STAGE_HEAD + "      - shell: python\n        run: print(1)\n")
        check("a shell: python step is noticed (this gate lints bash/sh only)",
              shell_python_steps([".github/workflows/py.yml",
                                  ".github/workflows/s1.yml"], root=td)
              == [".github/workflows/py.yml"])

    # --- the shellcheck pass, against the pinned binary -----------------
    shellcheck = ensure_shellcheck()
    with tempfile.TemporaryDirectory() as td:
        warn = os.path.join(td, "warn.yml")
        _write(warn, STAGE_HEAD + "      - run: echo $(ls)\n")
        blocks, diags = lint_files(shellcheck, [warn])
        check("a warning-level finding (SC2046) fails the pass, naming the "
              "run: line",
              blocks == 1 and len(diags) == 1 and "SC2046:warning" in diags[0]
              and f"{warn}:7:9:" in diags[0],
              f"blocks={blocks} diags={diags!r}")

        info = os.path.join(td, "info.yml")
        _write(info, STAGE_HEAD + "      - run: echo $HOME\n")
        blocks, diags = lint_files(shellcheck, [info])
        check("an info-level finding (SC2086) is below the severity floor",
              blocks == 1 and not diags, f"diags={diags!r}")

        big = os.path.join(td, "big.yml")
        body = "".join(f"          echo line{i}\n" for i in range(200))
        _write(big, STAGE_HEAD + "      - run: |\n" + body
               + "          echo $(ls)\n")
        blocks, diags = lint_files(shellcheck, [big])
        check("a run: block over 4 KiB is linted, not hung (the actionlint "
              "runner defect this driver exists to sidestep)",
              len(body) > 4096 and len(diags) == 1
              and "SC2046:warning:201:" in diags[0],
              f"len={len(body)} diags={diags!r}")

        expr = os.path.join(td, "expr.yml")
        _write(expr, STAGE_HEAD +
               "      - run: |\n"
               "          if [ \"${{ inputs.flag }}\" = \"x\" ]; then\n"
               "            for f in ${{ inputs.files }}; do echo \"$f\"; done\n"
               "          fi\n"
               "          echo \"$UNDEFINED_FROM_ENV\"\n")
        blocks, diags = lint_files(shellcheck, [expr])
        check("${{ }} placeholders and env-provided variables provoke "
              "nothing (actionlint's excludes are honoured)",
              blocks == 1 and not diags, f"diags={diags!r}")
        check("sanitizing keeps the script's length and shape",
              sanitize_expressions("a ${{ x }} b") == "a ________ b")

        shells = os.path.join(td, "shells.yml")
        _write(shells, STAGE_HEAD +
               "      - shell: pwsh\n        run: Write-Host $(ls)\n"
               "      - shell: bash -e {0}\n        run: echo $(ls)\n"
               "      - shell: sh\n        run: echo $(ls)\n")
        got = [(sh, i) for _, i, _, sh, _, _ in run_blocks(shells)]
        check("a pwsh step is skipped; `bash -e {0}` and sh are linted",
              got == [("bash", 1), ("sh", 2)], f"got {got!r}")
        blocks, diags = lint_files(shellcheck, [shells])
        check("and both linted steps are reported, the pwsh one never",
              blocks == 2 and len(diags) == 2
              and all("SC2046" in d for d in diags), f"diags={diags!r}")

        win = os.path.join(td, "win.yml")
        _write(win, "on: push\njobs:\n  a:\n    runs-on: windows-latest\n"
                    "    steps:\n      - run: echo $(ls)\n")
        check("a literal windows runner defaults to pwsh and is skipped",
              run_blocks(win) == [])

        dflt = os.path.join(td, "dflt.yml")
        _write(dflt, "on: push\ndefaults:\n  run:\n    shell: sh\n"
                     "jobs:\n  a:\n    runs-on: ubuntu-latest\n"
                     "    steps:\n      - run: echo $(ls)\n")
        got = [sh for _, _, _, sh, _, _ in run_blocks(dflt)]
        check("a workflow-level defaults.run.shell is honoured",
              got == ["sh"], f"got {got!r}")

    print(f"{failures} failure(s).")
    return 1 if failures else 0


def main(argv):
    # Findings quote step names verbatim; a cp1252 console must not turn
    # a non-ASCII one into a traceback in place of the verdict.
    use_utf8_stdout()
    if argv == ["--self-test"]:
        return self_test()
    if argv:
        sys.exit(f"unknown arguments {argv!r}; takes --self-test or "
                 f"nothing.")
    return run_gate()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
