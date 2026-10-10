#!/usr/bin/env python3
"""implement.yml's gate-suite preflight skips, and says so, in a repository
that has no local gate suite.

WHY THIS EXISTS
---------------
The implement job runs `python3 .github/scripts/run-local-gates.py` ahead of
each agent step (spec 051 FR-009/FR-009a), preceded by a preflight that
degrades a missing prerequisite to a step-summary note. That preflight
checked pyyaml, jq and actionlint, never the suite script itself. In an
adopter repository, which has no run-local-gates.py, every tool was present,
so the suite step ran, python3 failed on the missing file, the cycle-outcome
artifact recorded `gate-suite-outcome: "fail"`, and the agent prompt told the
agent the suite was "red at cycle start" (#935, #936).

The preflight now checks the script first. When it is absent it emits
`script-exists=false`, forces `ready=false`, writes a step-summary note and
exits before the tool checks. The summary step reports
"skipped — no local gate suite in this repository" ahead of its other arms,
and its `paragraph` output, which the agent prompt interpolates, says the
repository has no suite in place of the "already ran once" text. With the
script present, that paragraph reads exactly as the prompt did before.

A suite script that is present but cannot run is the other skip (#989):
the preflight also emits `missing` (the prerequisites it could not find,
space-separated), the summary names them, and the paragraph says the suite
did not run, that the agent must not try to run it either, and that a
gate-run task stays unchecked -- never the "already ran once" text, which
used to send the agent into the same ModuleNotFoundError.

This harness EXECUTES the shipped preflight, summary and cycle-outcome steps
of both legs (cycle and retry) with wc_shell_harness.run_step, in a working
directory with and without the script. Static checks pin the env and prompt
wiring. Each MUTATION reverts one rule and asserts the suite then fails.

Usage: python3 .github/scripts/verify-implement-gate-suite-preflight.py
Requires: bash, jq, pyyaml.
"""
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_shell_harness import (ensure_jq, find_job, resolve_bash, run_step,  # noqa: E402
                              use_utf8_stdout)

WORKFLOW = ".github/workflows/implement.yml"
JOB = "implement"
SCRIPT = ".github/scripts/run-local-gates.py"
LEGS = ("cycle", "retry")
# Built by concatenation: a literal two-brace opener in this file's text is
# the shape the workflow linters read as an Actions expression.
OPEN = "$" + "{{ "
CLOSE = " }}"
AGENT_STEP = {"cycle": "Implement and converge (cycle)",
              "retry": "Implement and converge (retry at escalation model)"}
NO_SUITE = "skipped — no local gate suite in this repository"

BASH = None
failures = []


def check(name, cond, detail=""):
    if cond:
        print("[ok] {0}".format(name))
    else:
        failures.append(name)
        print("::error::verify-implement-gate-suite-preflight: {0} -- {1}".format(name, detail))


def expected_paragraph(leg, summary):
    """The prompt's gate-suite paragraph as both prompts carried it before
    #936, with the summary output interpolated. A present script must
    still produce exactly this text."""
    return ("The local gate suite (`python .github/scripts/run-local-gates.py`)\n"
            "already ran once, deterministically, before this agent step\n"
            "started, so its state at {0} start is known without spending a\n"
            "turn on it: {1}.\n"
            "That is a starting point only, not a substitute for the gate-suite\n"
            "run CLAUDE.md's \"Before pushing\" section still asks you to make\n"
            "yourself once your own changes are in place.").format(leg, summary)


def stub_bin(root, tools):
    """A bin dir holding a stub for each name in `tools` that exits 0."""
    d = os.path.join(root, "bin")
    os.makedirs(d, exist_ok=True)
    for t in tools:
        p = os.path.join(d, t)
        with open(p, "w", newline="\n") as fh:
            fh.write("#!/bin/sh\nexit 0\n")
        os.chmod(p, 0o755)
    return d


def missing_paragraph_ok(para, missing):
    """The missing-prerequisite paragraph names the gap, says the suite did
    not run, forbids the agent's own attempt and keeps gate-run tasks
    unchecked -- and never claims the suite already ran."""
    flat = " ".join(para.split())
    return (missing in flat and "did not run before this agent step" in flat
            and "Do not try to run it yourself" in flat
            and "gate-suite run unchecked" in flat
            and "already ran once" not in flat and "red at" not in flat)


def run_preflight(script, with_suite, missing_actionlint=False, missing_pyyaml=False):
    """-> (rc, output, outputs, summary)."""
    root = tempfile.mkdtemp(prefix="wc-gate-suite-preflight-")
    try:
        work = os.path.join(root, "work")
        os.makedirs(os.path.join(work, ".github", "scripts"))
        if with_suite:
            with open(os.path.join(work, SCRIPT), "w") as fh:
                fh.write("print('gate suite')\n")
        runner_temp = os.path.join(root, "runner-temp")
        os.makedirs(runner_temp)
        if missing_actionlint:
            # Only python3 and jq on PATH: the step's own tests are bash
            # builtins, so actionlint is missing whatever the host has.
            bindir = os.path.join(root, "only")
            os.makedirs(bindir)
            os.symlink(sys.executable, os.path.join(bindir, "python3"))
            os.symlink(shutil.which("jq"), os.path.join(bindir, "jq"))
            return run_step(BASH, script, work, {"PATH": bindir}, runner_temp,
                            path_prepend=bindir)
        if missing_pyyaml:
            # python3 is a stub whose every import fails, as on an image
            # without pyyaml; jq and actionlint are present.
            bindir = os.path.join(root, "only")
            os.makedirs(bindir)
            with open(os.path.join(bindir, "python3"), "w", newline="\n") as fh:
                fh.write("#!/bin/sh\nexit 1\n")
            os.chmod(os.path.join(bindir, "python3"), 0o755)
            os.symlink(shutil.which("jq"), os.path.join(bindir, "jq"))
            stub_bin(root, ["actionlint"])
            path = bindir + os.pathsep + os.path.join(root, "bin")
            return run_step(BASH, script, work, {"PATH": path}, runner_temp,
                            path_prepend=path)
        bindir = stub_bin(root, ["actionlint"])
        env = {"PATH": bindir + os.pathsep + os.environ["PATH"]}
        return run_step(BASH, script, work, env, runner_temp)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def run_plain(script, env):
    root = tempfile.mkdtemp(prefix="wc-gate-suite-summary-")
    try:
        runner_temp = os.path.join(root, "runner-temp")
        os.makedirs(runner_temp)
        script = script.replace(OPEN + "runner.temp" + CLOSE, "$RUNNER_TEMP")
        rc, out, outputs, summary = run_step(BASH, script, root, env, runner_temp)
        files = {}
        for name in os.listdir(runner_temp):
            with open(os.path.join(runner_temp, name), encoding="utf-8") as fh:
                files[name] = fh.read()
        return rc, out, outputs, summary, files
    finally:
        shutil.rmtree(root, ignore_errors=True)


def suite(leg, steps, quiet=False):
    """Every behavioural scenario for one leg; -> list of failed names."""
    failed = []

    def ck(name, cond, detail=""):
        name = "({0}) {1}".format(leg, name)
        if not cond:
            failed.append(name)
        if not quiet:
            check(name, cond, detail)

    pre, summ, record = steps["preflight"], steps["summary"], steps["record"]

    rc, out, o, summary = run_preflight(pre, with_suite=False)
    ck("no suite script: the preflight exits 0 with script-exists=false and ready=false",
       rc == 0 and o.get("script-exists") == "false" and o.get("ready") == "false",
       "rc={0} outputs={1}\n{2}".format(rc, o, out))
    ck("no suite script: the step summary says there is no local gate suite, not a missing tool",
       "no local gate suite in this repository" in summary
       and "missing prerequisites" not in summary, repr(summary))
    ck("no suite script: ready is written once, so the tool checks never ran",
       list(o).count("ready") == 1 and summary.count("\n") == 1, repr(summary))

    rc, out, o, summary = run_preflight(pre, with_suite=True)
    ck("suite script present, tools present: script-exists=true and ready=true, no note",
       rc == 0 and o.get("script-exists") == "true" and o.get("ready") == "true"
       and summary == "", "rc={0} outputs={1} summary={2!r}\n{3}".format(rc, o, summary, out))

    if os.name == "posix":
        rc, out, o, summary = run_preflight(pre, with_suite=True, missing_actionlint=True)
        ck("suite script present, actionlint missing: script-exists=true, ready=false, the tool note",
           rc == 0 and o.get("script-exists") == "true" and o.get("ready") == "false"
           and "missing prerequisites" in summary and "actionlint" in summary,
           "rc={0} outputs={1} summary={2!r}\n{3}".format(rc, o, summary, out))
        ck("suite script present, actionlint missing: the missing output names exactly actionlint",
           o.get("missing") == "actionlint", "outputs={0}".format(o))

        rc, out, o, summary = run_preflight(pre, with_suite=True, missing_pyyaml=True)
        ck("suite script present, pyyaml missing: ready=false and the missing output names exactly pyyaml",
           rc == 0 and o.get("ready") == "false" and o.get("missing") == "pyyaml"
           and "pyyaml" in summary,
           "rc={0} outputs={1} summary={2!r}\n{3}".format(rc, o, summary, out))

    def summarize(script_exists, ready, outcome="", first=""):
        return run_plain(summ, {"SCRIPT_EXISTS": script_exists, "READY": ready,
                                "OUTCOME": outcome, "FIRST_FAILURE": first})

    rc, out, o, _s, _f = summarize("false", "false")
    ck("no suite script: summary reports the skip ahead of the missing-tool arm",
       rc == 0 and o.get("summary") == NO_SUITE, "rc={0} outputs={1}\n{2}".format(rc, o, out))
    para = o.get("paragraph", "")
    ck("no suite script: the prompt paragraph says there is no local gate suite",
       "has no local gate suite" in para and "does not apply" in para
       and "already ran once" not in para and "red at" not in para, repr(para))

    rc, out, o, _s, _f = summarize("true", "true", "pass")
    ck("suite passed: summary is pass and the paragraph reads exactly as before",
       rc == 0 and o.get("summary") == "pass"
       and o.get("paragraph") == expected_paragraph(leg, "pass"),
       "outputs={0}\n{1}".format(o, out))

    first = "FAIL gate-7 (the fixture's first failure)"
    rc, out, o, _s, _f = summarize("true", "true", "fail", first)
    red = "red at {0} start — first failure: {1}".format(leg, first)
    ck("suite red: summary names the first failure and the paragraph reads exactly as before",
       o.get("summary") == red and o.get("paragraph") == expected_paragraph(leg, red),
       "outputs={0}\n{1}".format(o, out))

    def summarize_missing(missing):
        return run_plain(summ, {"SCRIPT_EXISTS": "true", "READY": "false",
                                "MISSING": missing, "OUTCOME": "", "FIRST_FAILURE": ""})

    rc, out, o, _s, _f = summarize_missing("pyyaml")
    ck("missing tool: summary names the missing prerequisite",
       rc == 0 and o.get("summary") == "skipped — missing prerequisite(s): pyyaml",
       "rc={0} outputs={1}\n{2}".format(rc, o, out))
    para = o.get("paragraph", "")
    ck("missing tool: the prompt paragraph names it, says the suite did not run and "
       "tells the agent not to run it or check a gate-run task",
       missing_paragraph_ok(para, "pyyaml"), repr(para))

    rc, out, o, _s, files = run_plain(record, {"CONVERGED": "false", "HANDOFF": "",
                                               "GATE_OUTCOME": "", "FIRST_FAILURE": ""})
    blob = files.get("wing-commander-cycle-outcome-{0}.json".format(leg), "")
    try:
        got = json.loads(blob)
    except ValueError:
        got = {}
    ck("no suite script: the cycle-outcome artifact records skipped, never fail",
       got.get("gate-suite-outcome") == "skipped" and got.get("gate-suite-first-failure") is None,
       "rc={0} artifact={1!r}\n{2}".format(rc, blob, out))
    return failed


MUTATIONS = (
    ("preflight", "the preflight's suite-script check removed",
     "if [ ! -f .github/scripts/run-local-gates.py ]; then", "if false; then"),
    ("preflight", "the preflight falls through to the tool checks",
     "skipping it for this {leg}.\" >> \"$GITHUB_STEP_SUMMARY\"\n  exit 0\n",
     "skipping it for this {leg}.\" >> \"$GITHUB_STEP_SUMMARY\"\n"),
    ("summary", "the summary's no-suite arm removed",
     'if [ "$SCRIPT_EXISTS" = "false" ]; then\n  summary=', 'if false; then\n  summary='),
    ("summary", "the prompt paragraph left unconditional",
     'if [ "$SCRIPT_EXISTS" = "false" ]; then\n  paragraph=', 'if false; then\n  paragraph='),
    ("summary", "the missing-prerequisite paragraph arm removed (#989)",
     'elif [ "$READY" != "true" ]; then\n  paragraph=', 'elif false; then\n  paragraph='),
    ("summary", "the summary stops naming the missing prerequisite",
     'missing prerequisite(s): ${{MISSING:-unrecorded}}"\nelif', 'missing prerequisite(s): unrecorded"\nelif'),
    ("preflight", "the preflight stops emitting its missing output",
     'echo "missing=${{missing# }}" >> "$GITHUB_OUTPUT"\n', ''),
)


def main():
    global BASH
    use_utf8_stdout()
    BASH = resolve_bash()
    ensure_jq()
    steps = find_job(WORKFLOW, JOB).get("steps") or []
    by_name = {(s or {}).get("name"): s for s in steps}
    texts = {}
    for leg in LEGS:
        names = {"preflight": "Preflight: gate-suite prerequisites ({0})".format(leg),
                 "summary": "Summarize gate-suite outcome ({0})".format(leg),
                 "record": "Record cycle outcome for watchdog ({0})".format(leg),
                 "agent": AGENT_STEP[leg]}
        found = {}
        for key, name in names.items():
            if name not in by_name:
                sys.exit("::error file={0}::no step named {1!r} in job {2!r}. If it was renamed, "
                         "update the workflow and this harness together.".format(WORKFLOW, name, JOB))
            found[key] = by_name[name]
        env = found["summary"].get("env") or {}
        check("({0}) the summary step reads the preflight's script-exists output".format(leg),
              env.get("SCRIPT_EXISTS") == OPEN + "steps.gate-suite-preflight-{0}.outputs.script-exists".format(leg) + CLOSE,
              "env={0}".format(env))
        check("({0}) the summary step reads the preflight's missing output".format(leg),
              env.get("MISSING") == OPEN + "steps.gate-suite-preflight-{0}.outputs.missing".format(leg) + CLOSE,
              "env={0}".format(env))
        prompt = str((found["agent"].get("with") or {}).get("prompt", ""))
        ref = OPEN + "steps.gate-suite-summary-{0}.outputs.paragraph".format(leg) + CLOSE
        check("({0}) the agent prompt interpolates the summary's paragraph, not a fixed copy".format(leg),
              ref in prompt and "already ran once" not in prompt, "")
        record_env = found["record"].get("env") or {}
        check("({0}) the cycle-outcome artifact reads the suite step's own outcome".format(leg),
              record_env.get("GATE_OUTCOME") == OPEN + "steps.gate-suite-{0}.outputs.outcome".format(leg) + CLOSE,
              "env={0}".format(record_env))
        run_steps = {k: str(found[k]["run"]) for k in ("preflight", "summary", "record")}
        texts[leg] = run_steps
        for target, name, old, _new in MUTATIONS:
            if run_steps[target].count(old.format(leg=leg)) != 1:
                sys.exit("::error file={0}::mutation {1!r} no longer matches the ({2}) {3} step "
                         "exactly once. Update the mutation with the step.".format(
                             WORKFLOW, name, leg, target))
        suite(leg, run_steps)
        for target, name, old, new in MUTATIONS:
            mutated = dict(run_steps)
            mutated[target] = mutated[target].replace(old.format(leg=leg), new.format(leg=leg))
            check("({0}) mutation caught: {1}".format(leg, name),
                  bool(suite(leg, mutated, quiet=True)),
                  "the suite stayed green with this rule reverted")
    # The two legs carry the same preflight and summary text but for the
    # leg's own name, so a wording fix that lands in one leg only fails here.
    for target in ("preflight", "summary"):
        check("the cycle and retry {0} steps match but for the leg name".format(target),
              texts["cycle"][target] == texts["retry"][target].replace("retry", "cycle"),
              "a change landed in one leg only -- make the same edit in both")
    if failures:
        print("verify-implement-gate-suite-preflight: {0} failure(s)".format(len(failures)))
        sys.exit(1)
    print("verify-implement-gate-suite-preflight: ok")


if __name__ == "__main__":
    main()
