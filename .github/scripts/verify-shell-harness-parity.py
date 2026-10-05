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
rather than guessed at, and that no other harness script carries a shell
argv of its own (the mapping's single home is wc_shell_harness).

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
    for path in sorted(glob.glob(os.path.join(ROOT, ".github", "actions", "*",
                                              "action.yml"))):
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
    survived = rc == 0 and outputs.get("probe") == "survived"
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
    case_explicit_shell_and_refusal(bash)
    case_shipped_step(bash, steps, "composite-bash", must_survive=False)
    case_shipped_step(bash, steps, "workflow-bash-over-default",
                      must_survive=False)
    case_shipped_step(bash, steps, "workflow-unspecified-hosted",
                      must_survive=True)
    case_single_home()
    if failures:
        print(f"FAIL: {len(failures)} failure(s).")
        return 1
    print("ok: run_step reproduces each step's production shell.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
