#!/usr/bin/env python3
"""Gate 140 -- wc_shell_harness.run_step runs a step under the shell
production gives THAT step, not one shell for every step.

WHY THIS EXISTS
---------------
run_step used to run every extracted block as `bash -e`, and its comment
said production has no pipefail. That is true only of a workflow step that
names no shell. A step with `shell: bash` -- every composite action's run:
step, and every workflow step that says so even under a
`defaults.run.shell: bash -e {0}` -- runs as
`bash --noprofile --norc -eo pipefail {0}`. So for most of the steps the
harness gates execute, a pipeline whose early stage fails failed the step
in CI and passed it under the gate: the harness was less strict than the
runner exactly where a latent pipefail bug would hide (Maintenance backlog
#889, found investigating #959).

This gate has its own reader of the shipped YAML (it does not ask the
harness which steps are which), picks real shipped steps of each shape,
prepends a probe whose pipeline's FIRST stage fails, and runs the result
through run_step with no shell named -- the way nearly every caller calls
it:

  * a composite `shell: bash` step must FAIL at the probe (pipefail);
  * a workflow `shell: bash` step under `defaults.run.shell: bash -e {0}`
    must FAIL at the probe too (the step key beats the default);
  * a workflow step with no shell on a hosted runner must SURVIVE the probe
    (`bash -e`, no pipefail -- the harness must not be stricter than CI
    either).

It also pins production_shell()'s resolution table, that an explicit
shell= is honoured, that a script traceable to no shipped step is refused
rather than guessed at, that one whose plausible origins (near-copies of a
step) run under different shells is refused too, that a shipped-step cache
file another user could have written is not trusted (nor a FIFO
planted at its name allowed to block the reader), and that no other harness
script carries a shell argv of its own (the mapping's single home is
wc_shell_harness).

Usage: python3 .github/scripts/verify-shell-harness-parity.py
Requires: bash. See wc_shell_harness.py for running this on Windows.
"""
import glob
import os
import re
import sys
import tempfile

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import wc_shell_harness as harness  # noqa: E402

failures = []

# A pipeline whose first stage fails and last succeeds: fatal under
# `-eo pipefail`, ignored under plain `-e`. If the step survives it, the
# probe's output says so.
PROBE = ('false | true\n'
         'echo "probe=survived" >> "$GITHUB_OUTPUT"\n'
         'exit 0\n')


def fail(case, msg):
    failures.append(f"{case}: {msg}")
    print(f"::error::{case}: {msg}")


def _defaults_shell(doc):
    return (((doc or {}).get("defaults") or {}).get("run") or {}).get("shell")


def shipped_steps():
    """[(rel_path, step_name, run, kind)] with kind one of composite-bash,
    workflow-bash-over-default, workflow-unspecified-hosted -- this gate's
    own reading of the YAML, independent of the harness's."""
    out = []
    for path in sorted(glob.glob(os.path.join(ROOT, ".github", "actions", "**",
                                              "action.y*ml"), recursive=True)):
        doc = yaml.safe_load(open(path, encoding="utf-8")) or {}
        for step in (doc.get("runs") or {}).get("steps") or []:
            if isinstance(step.get("run"), str) and step.get("shell") == "bash":
                out.append((path, step.get("name"), step["run"], "composite-bash"))
    for path in sorted(glob.glob(os.path.join(ROOT, ".github", "workflows",
                                              "*.yml"))):
        doc = yaml.safe_load(open(path, encoding="utf-8")) or {}
        wf_default = _defaults_shell(doc)
        for job in (doc.get("jobs") or {}).values():
            job_default = _defaults_shell(job)
            for step in (job or {}).get("steps") or []:
                if not isinstance(step.get("run"), str):
                    continue
                if (step.get("shell") == "bash" and job_default is None
                        and wf_default == "bash -e {0}"):
                    kind = "workflow-bash-over-default"
                elif (step.get("shell") is None and job_default is None
                      and wf_default is None and "container" not in job):
                    kind = "workflow-unspecified-hosted"
                else:
                    continue
                out.append((path, step.get("name"), step["run"], kind))
    return out


def pick(steps, kind):
    """The largest step of `kind` whose text appears nowhere else, so the
    probe is a small edit of exactly one shipped step."""
    counts = {}
    for _p, _n, run, _k in steps:
        counts[run] = counts.get(run, 0) + 1
    cands = [s for s in steps if s[3] == kind and counts[s[2]] == 1
             and "${{" not in s[2] and s[1]]
    if not cands:
        sys.exit(f"::error::no shipped step of kind {kind!r} to probe -- "
                 f"update this gate's subject selection.")
    return max(cands, key=lambda s: (len(s[2].splitlines()), s[0], s[1]))


def probe_survived(outputs):
    """Whether the probe's pipeline let the step go on: read from the line
    it writes after that pipeline, never from the exit code -- the step
    body's own exit, after the probe, proves nothing about pipefail."""
    return outputs.get("probe") == "survived"


def run_probe(bash, script, **kw):
    with tempfile.TemporaryDirectory() as work:
        rc, out, outputs, _ = harness.run_step(bash, script, work, {}, work, **kw)
    return rc, out, outputs


def case_shipped_step(bash, steps, kind, must_survive):
    path, name, run, _ = pick(steps, kind)
    rel = os.path.relpath(path, ROOT).replace(os.sep, "/")
    case = f"{kind} step {rel}: {name!r}"
    try:
        rc, out, outputs = run_probe(bash, PROBE + run)
    except RuntimeError as exc:
        fail(case, f"run_step could not place the probed step: {exc}")
        return
    survived = probe_survived(outputs)
    if must_survive and not survived:
        fail(case, f"production runs this step as `bash -e {{0}}` (no "
                   f"pipefail), but under the harness a pipeline whose first "
                   f"stage fails killed it (exit {rc}): {out.strip()[:300]}")
    elif not must_survive and survived:
        fail(case, "production runs this step as `bash --noprofile --norc "
                   "-eo pipefail {0}`, but under the harness a pipeline whose "
                   "first stage fails did not fail it -- the harness is less "
                   "strict than CI")
    else:
        print(f"ok: {case} -- probe {'survived' if survived else 'failed the step'}")


def case_probe_verdict_ignores_body(bash):
    """The probed subject is a real shipped step run with none of its
    inputs, so its own body may well exit non-zero after the probe. That
    exit says nothing about pipefail: if it were read as "the probe failed
    the step", a harness that dropped pipefail would still pass the
    must-fail cases whenever the chosen step happens to fail on its own."""
    case = "probe verdict independent of the step body"
    body_fails = PROBE.replace("exit 0\n", "") + "exit 3\n"
    rc, _o, outputs = run_probe(bash, body_fails,
                                shell=harness.UNSPECIFIED_SHELL_HOSTED)
    if not probe_survived(outputs):
        fail(case, f"under `bash -e` the probe ran past its pipeline (probe="
                   f"{outputs.get('probe')!r}) but a later exit {rc} in the "
                   f"step body was read as the probe failing the step")
    rc, _o, outputs = run_probe(bash, body_fails,
                                shell=harness.NAMED_SHELLS["bash"])
    if probe_survived(outputs):
        fail(case, "under pipefail the probe's pipeline was read as survived")


def case_resolution_table():
    case = "production_shell resolution"
    ps = getattr(harness, "production_shell", None)
    if ps is None:
        fail(case, "wc_shell_harness has no production_shell(): the shell a "
                   "step runs under is not derived from the step at all")
        return
    pipefail = ("bash", "--noprofile", "--norc", "-eo", "pipefail", "{0}")
    rows = [
        ("composite shell: bash", ({"shell": "bash"}, None, None), pipefail),
        ("workflow step, no shell, hosted",
         ({}, {"steps": []}, {"jobs": {}}), ("bash", "-e", "{0}")),
        ("workflow step, no shell, container job",
         ({}, {"container": "img"}, {"jobs": {}}), ("sh", "-e", "{0}")),
        ("workflow default bash -e {0}",
         ({}, {}, {"defaults": {"run": {"shell": "bash -e {0}"}}}),
         ("bash", "-e", "{0}")),
        ("shell: bash over workflow default",
         ({"shell": "bash"}, {}, {"defaults": {"run": {"shell": "bash -e {0}"}}}),
         pipefail),
        ("job default over workflow default",
         ({}, {"defaults": {"run": {"shell": "bash"}}},
          {"defaults": {"run": {"shell": "bash -e {0}"}}}), pipefail),
        ("custom shell without {0}", ({"shell": "bash -x"}, {}, {}),
         ("bash", "-x", "{0}")),
        ("shell: sh", ({"shell": "sh"}, {}, {}), ("sh", "-e", "{0}")),
    ]
    for label, (step, job, wf), want in rows:
        got = tuple(ps(step, job, wf))
        if got != want:
            fail(case, f"{label}: got {got}, want {want}")
    try:
        ps({"run": "true"})
        fail(case, "a composite run: step with no shell: resolved to a shell; "
                   "the runner refuses that step")
    except ValueError:
        pass


def case_explicit_shell_and_refusal(bash):
    case = "explicit shell= and untraceable scripts"
    if not hasattr(harness, "NAMED_SHELLS"):
        fail(case, "wc_shell_harness has no NAMED_SHELLS table")
        return
    rc, _o, _ = run_probe(bash, PROBE, shell=harness.NAMED_SHELLS["bash"])
    if rc == 0:
        fail(case, "shell=NAMED_SHELLS['bash'] did not run with pipefail")
    rc, out, _ = run_probe(bash, PROBE, shell=harness.UNSPECIFIED_SHELL_HOSTED)
    if rc != 0:
        fail(case, f"shell=UNSPECIFIED_SHELL_HOSTED ran with pipefail: {out}")
    try:
        run_probe(bash, "echo unrelated-to-any-shipped-step\n")
        fail(case, "a script no shipped step resembles was run under a "
                   "guessed shell instead of being refused")
    except RuntimeError:
        pass


def case_divergent_near_copies():
    """Two near-copies of one step under different shells: a mutated copy
    nearer the `bash -e` one must be refused, not run under it -- the next
    one-line edit to either copy would otherwise flip its shell silently."""
    case = "near-copies under different shells"
    match = getattr(harness, "match_shell", None)
    if match is None:
        fail(case, "wc_shell_harness has no match_shell(): the tracing rule "
                   "cannot be exercised on entries of this gate's own")
        return
    common = [f'echo "shared line number {i}" >> "$GITHUB_STEP_SUMMARY"'
              for i in range(7)]
    plain = "\n".join(common + ['jq ".a" in.json > "$RUNNER_TEMP/out.json"',
                                'mv "$RUNNER_TEMP/out.json" in.json']) + "\n"
    piped = "\n".join(common + ['jq ".b" in.json > "$RUNNER_TEMP/out.json"',
                                'cp "$RUNNER_TEMP/out.json" other.json']) + "\n"
    entries = [
        (plain, harness.UNSPECIFIED_SHELL_HOSTED, "a.yml: Mark", None,
         harness._significant_lines(plain)),
        (piped, harness.NAMED_SHELLS["bash"], "b.yml: Mark", None,
         harness._significant_lines(piped)),
    ]
    mutated = plain.replace('".a"', '".a | .x = 0"')
    argv, why = match(mutated, entries)
    if argv is not None:
        fail(case, f"a mutated copy sharing 8/9 lines with a `bash -e` step "
                   f"and 7/9 with a `shell: bash` copy of it was run under "
                   f"{' '.join(argv)} instead of being refused")
    argv, why = match(mutated, entries[:1])
    if tuple(argv or ()) != harness.UNSPECIFIED_SHELL_HOSTED:
        fail(case, f"with no rival copy the same script was not traced to its "
                   f"one plausible origin: {why}")


def case_unrunnable_shells(bash):
    """A shell the harness cannot run faithfully must be refused, not run
    under bash: run_step writes the block (and its bash PATH preamble) to a
    file and executes it, which reproduces only a bash or sh step. pwsh,
    powershell and cmd used to fall through as custom shells, and `shell:
    python` ran its script after a bash preamble -- a gate built on either
    would test something no runner executes."""
    case = "shells the harness cannot reproduce"
    for shell in ("pwsh", "powershell", "cmd", "python", "pwsh -File {0}",
                  "python3 {0}", "perl {0}"):
        try:
            argv = harness.production_shell({"shell": shell})
        except ValueError as exc:
            argv = None
            why = str(exc)
        if argv is not None:
            try:
                run_probe(bash, PROBE, shell=argv)
                fail(case, f"shell: {shell} resolved to {' '.join(argv)} and "
                           f"run_step ran the block under it instead of "
                           f"refusing")
                continue
            except RuntimeError as exc:
                why = str(exc)
            except OSError as exc:
                fail(case, f"shell: {shell} resolved to {' '.join(argv)} and "
                           f"run_step tried to exec it instead of refusing: "
                           f"{exc}")
                continue
        if "cannot" not in why:
            fail(case, f"shell: {shell} was refused without saying why: {why}")
    # ...while every bash/sh form keeps running.
    for shell in ("bash", "sh", "bash -e {0}", "bash -x", "/bin/bash -e {0}"):
        try:
            rc, out, _ = run_probe(bash, "echo probe\n",
                                   shell=harness.production_shell(
                                       {"shell": shell}))
        except (ValueError, RuntimeError) as exc:
            fail(case, f"shell: {shell} was refused: {exc}")
            continue
        if rc != 0:
            fail(case, f"shell: {shell} did not run a trivial block: {out}")


def case_placeholder_inside_argument(bash):
    """The runner substitutes {0} wherever it appears in the template
    (`bash -c ". '{0}'"`), not only as a whole argument; run_step used to
    hand bash the literal `{0}`."""
    case = "{0} inside an argument"
    argv = harness.production_shell({"shell": "bash -ec \". '{0}'\""})
    if argv != ("bash", "-ec", ". '{0}'"):
        fail(case, f"custom shell parsed as {argv}")
        return
    try:
        rc, out, outputs = run_probe(bash, PROBE, shell=argv)
    except RuntimeError as exc:
        fail(case, f"run_step refused a bash custom shell: {exc}")
        return
    if rc != 0 or outputs.get("probe") != "survived":
        fail(case, f"`bash -ec \". '{{0}}'\"` did not run the script file "
                   f"(exit {rc}): {out.strip()[:300]}")


def case_every_composite_traced(steps):
    """Every composite `shell: bash` step, at any depth under
    .github/actions/ (the _shared/ ones included), must be traced by its
    exact text to the pipefail shell. The harness's table once globbed only
    .github/actions/*/action.yml, so a _shared/ composite's step was
    refused as untraceable, or traced by its lines to a near-copy in a
    workflow running under another shell."""
    case = "every composite step traced"
    for path, name, run, kind in steps:
        if kind != "composite-bash":
            continue
        argv, where = harness.shell_for_script(run)
        if argv is None:
            # Byte-identical copies elsewhere under another shell are the
            # one legitimate refusal; the harness says so by name.
            if "different shells" in (where or ""):
                continue
            fail(case, f"{os.path.relpath(path, ROOT)}: {name!r} is not in "
                       f"the harness's shipped-step table: {where}")
        elif tuple(argv) != harness.NAMED_SHELLS["bash"]:
            fail(case, f"{os.path.relpath(path, ROOT)}: {name!r} traced to "
                       f"{where} under {' '.join(argv)}, not its own "
                       f"`shell: bash`")


def case_foreign_cache_ignored():
    """The shipped-step parse is cached in the shared temp dir under a key
    anyone can compute from the public files, and its argv is what run_step
    execs. A cache file another user could have written must be re-derived,
    not trusted."""
    case = "shipped-step cache written by someone else"
    if not hasattr(os, "geteuid"):
        return          # per-user temp dir; no other writer to refuse
    import json
    saved = tempfile.tempdir
    with tempfile.TemporaryDirectory() as tmp:
        try:
            tempfile.tempdir = tmp
            harness.shipped_step_shells.cache_clear()
            harness.shipped_step_shells()
            caches = glob.glob(os.path.join(tmp, "wc-shipped-step-shells-*"))
            if len(caches) != 1:
                fail(case, f"expected one cache file in {tmp}, saw {caches}")
                return
            planted = os.path.join(tmp, "planted-shell")
            with open(caches[0], "w", encoding="utf-8") as fh:
                json.dump([["echo planted\n", [planted, "{0}"], "x.yml: s"]],
                          fh)
            os.chmod(caches[0], 0o666)
            harness.shipped_step_shells.cache_clear()
            if any(planted in e[1] for e in harness.shipped_step_shells()):
                fail(case, "a world-writable cache file was trusted: its "
                           "argv would be exec'd by run_step")
        finally:
            tempfile.tempdir = saved
            harness.shipped_step_shells.cache_clear()
            harness.shell_for_script.cache_clear()


def case_cache_fifo_does_not_hang():
    """Anyone can create a FIFO at the computable cache name. Opening it
    for reading blocks until a writer appears, so a reader that opens
    before checking the file type hangs every gate that traces a script.
    The harness must fall back to a fresh parse instead."""
    case = "FIFO planted at the shipped-step cache name"
    if not hasattr(os, "mkfifo"):
        return
    import subprocess
    saved = tempfile.tempdir
    with tempfile.TemporaryDirectory() as tmp:
        try:
            tempfile.tempdir = tmp
            harness.shipped_step_shells.cache_clear()
            harness.shipped_step_shells()
            caches = glob.glob(os.path.join(tmp, "wc-shipped-step-shells-*"))
            if len(caches) != 1:
                fail(case, f"expected one cache file in {tmp}, saw {caches}")
                return
            os.remove(caches[0])
            os.mkfifo(caches[0])
            env = dict(os.environ, TMPDIR=tmp)
            try:
                proc = subprocess.run(
                    [sys.executable, "-c",
                     "import sys; sys.path.insert(0, sys.argv[1]); "
                     "import wc_shell_harness as h; "
                     "print(len(h.shipped_step_shells()))", HERE],
                    env=env, capture_output=True, text=True, timeout=60)
            except subprocess.TimeoutExpired:
                fail(case, "shipped_step_shells() blocked opening a FIFO "
                           "at the cache path")
                return
            if proc.returncode != 0 or not proc.stdout.strip().isdigit():
                fail(case, f"shipped_step_shells() failed: {proc.stderr}")
        finally:
            tempfile.tempdir = saved
            harness.shipped_step_shells.cache_clear()
            harness.shell_for_script.cache_clear()


# A literal shell argv anywhere but the harness is a second home for the
# mapping -- the shape that let `bash -e` drift from production unnoticed.
_LITERAL_SHELL_RE = re.compile(
    r'''shell\s*=\s*[(\[]|["']--norc["']\s*,\s*["']-eo["']''')


def case_single_home():
    case = "shell mapping single home"
    canonical = os.path.join(HERE, "wc_shell_harness.py")
    this = os.path.abspath(__file__)
    for path in sorted(glob.glob(os.path.join(HERE, "**", "*.py"),
                                 recursive=True)):
        if os.path.abspath(path) in (canonical, this):
            continue
        text = open(path, encoding="utf-8").read()
        if "wc_shell_harness" not in text:
            continue
        for n, line in enumerate(text.splitlines(), 1):
            if _LITERAL_SHELL_RE.search(line):
                fail(case, f"{os.path.relpath(path, ROOT)}:{n} spells out a "
                           f"shell argv; derive it with wc_shell_harness."
                           f"step_shell()/production_shell() instead: "
                           f"{line.strip()}")


def main():
    harness.use_utf8_stdout()
    bash = harness.resolve_bash()
    steps = shipped_steps()
    case_resolution_table()
    case_probe_verdict_ignores_body(bash)
    case_explicit_shell_and_refusal(bash)
    case_divergent_near_copies()
    case_unrunnable_shells(bash)
    case_placeholder_inside_argument(bash)
    case_shipped_step(bash, steps, "composite-bash", must_survive=False)
    case_shipped_step(bash, steps, "workflow-bash-over-default",
                      must_survive=False)
    case_shipped_step(bash, steps, "workflow-unspecified-hosted",
                      must_survive=True)
    case_every_composite_traced(steps)
    case_foreign_cache_ignored()
    case_cache_fifo_does_not_hang()
    case_single_home()
    if failures:
        print(f"FAIL: {len(failures)} failure(s).")
        return 1
    print("ok: run_step reproduces each step's production shell.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
