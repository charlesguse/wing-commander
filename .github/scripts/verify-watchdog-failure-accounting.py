#!/usr/bin/env python3
"""The watchdog's own failure accounting: a handled rate limit is not an
unhandled failure, and an unreadable self-dispatch chain is not depth 0.

WHY THIS EXISTS
---------------
Two steps in watchdog.yml decide, from the run's own state, whether the
watchdog reports on itself. Nothing executed either of them:

  #811  report-unhandled-failure's `Determine failed jobs` counted the
        diagnose agent step's raw `failure` outcome even when the
        rate-limited path had handled it (`outcome=rate-limited`, spec
        047). Every 429 therefore fired the safety net, and stage 8b filed
        a false watchdog-verify defect next to the usage-limit report.
  #889  act's `Self-dispatch depth` turned a failed `gh run list` into
        `[]` and a failed jq into 0, so an unreadable chain read as depth
        0 and the self-dispatch cap (FR-018 of spec 024) never applied.
        A read it cannot make now counts as capped, with an annotation.

This harness EXECUTES both shipped `run:` blocks through
wc_shell_harness.run_step. The depth step gets a `gh` stub that applies its
own `--jq` program to a fixture run list with real `jq -r` (#766). Each
MUTATION reverts one fix in the step text and asserts the suite then fails.

Usage: python3 .github/scripts/verify-watchdog-failure-accounting.py
Requires: bash, jq.
"""
import json
import os
import shutil
import stat
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_shell_harness import (ensure_jq, find_step, resolve_bash, run_step,  # noqa: E402
                              use_utf8_stdout)

WATCHDOG = ".github/workflows/watchdog.yml"
FAILED_JOBS = "Determine failed jobs"
DEPTH = "Self-dispatch depth"

STUB_GH = r'''#!/usr/bin/env bash
# `gh run list ... --jq PROG`: the fixture run list through the caller's
# own program, the way gh prints it; STUB_FAIL makes the read fail.
if [ -n "${STUB_FAIL:-}" ]; then
  echo "gh: HTTP 403: Resource not accessible by integration" >&2
  exit 1
fi
prog=""
while [ "$#" -gt 0 ]; do
  case "$1" in --jq) prog="$2"; shift ;; esac
  shift
done
jq -r "$prog" "$STUB_RUNS"
'''

BASH = None
failures = []


def check(name, cond, detail=""):
    if cond:
        print("[ok] {0}".format(name))
    else:
        failures.append(name)
        print("::error::verify-watchdog-failure-accounting: {0} -- {1}".format(name, detail))


def results(**over):
    env = {"COLLECT_RESULT": "success", "DIAGNOSE_RESULT": "success",
           "TRIAGE_RESULT": "skipped", "ACT_RESULT": "skipped",
           "FINDINGS_DROPPED_RESULT": "skipped",
           "DIAGNOSE_AGENT_OUTCOME": "success", "DIAGNOSE_OUTCOME": "passed-inspection"}
    env.update(over)
    return env


# (name, env, expected any-failed, substring the failed-jobs list must hold)
FAILED_JOBS_CASES = (
    ("#811: a rate-limited diagnose is handled, not an unhandled failure",
     results(DIAGNOSE_AGENT_OUTCOME="failure", DIAGNOSE_OUTCOME="rate-limited"),
     "false", ""),
    ("a crashed diagnose agent is still an unhandled failure",
     results(DIAGNOSE_AGENT_OUTCOME="failure", DIAGNOSE_OUTCOME="diagnose-failed"),
     "true", "diagnose:agent-step-failure"),
    ("a failed agent step under any other outcome is still counted",
     results(DIAGNOSE_AGENT_OUTCOME="failure", DIAGNOSE_OUTCOME="findings"),
     "true", "diagnose:agent-step-failure"),
    ("a red job beside a rate-limited diagnose is still counted",
     results(COLLECT_RESULT="failure", DIAGNOSE_AGENT_OUTCOME="failure",
             DIAGNOSE_OUTCOME="rate-limited"),
     "true", "collect:failure"),
    ("a clean run reports nothing",
     results(), "false", ""),
)


def runs(*events, start=100):
    """Newest first after the step's own sort: ids descend with time."""
    out = []
    for i, ev in enumerate(events):
        out.append({"databaseId": start - i, "event": ev,
                    "createdAt": "2026-10-01T00:{0:02d}:00Z".format(59 - i)})
    return out


# (name, run list or None for a failed read, cap, expected capped, depth,
#  RUN_ID, the warning the case must emit or "")
DEPTH_CASES = (
    ("an unbroken self-inspection chain at the cap is capped",
     runs("workflow_run", "workflow_run", "workflow_run", "workflow_dispatch"), "3", "true", "3",
     "100", ""),
    ("a chain broken by a dispatch counts only up to the break",
     runs("workflow_run", "workflow_dispatch", "workflow_run", "workflow_run"), "3", "false", "1",
     "100", ""),
    ("a failed run-list read counts as capped, not depth 0",
     None, "3", "true", "unknown", "100",
     "::warning::self-dispatch depth: could not list prior watchdog runs"),
    ("a depth jq cannot compute counts as capped, not depth 0",
     runs("workflow_run"), "3", "true", "unknown", "",
     "::warning::self-dispatch depth: could not compute the depth"),
)


def tmpdirs():
    tmp = tempfile.mkdtemp(prefix="wc-watchdog-accounting-")
    rt = os.path.join(tmp, "runner-temp")
    os.makedirs(rt)
    return tmp, rt


def run_failed_jobs(script, quiet, failed):
    def ck(name, cond, detail=""):
        if not cond:
            failed.append(name)
        if not quiet:
            check(name, cond, detail)

    for name, env, want, holds in FAILED_JOBS_CASES:
        tmp, rt = tmpdirs()
        try:
            rc, output, outputs, _ = run_step(BASH, script, tmp, env, rt)
            got = outputs.get("any-failed")
            ck(name, rc == 0 and got == want and holds in outputs.get("failed-jobs", ""),
               "rc={0} any-failed={1!r} failed-jobs={2!r}\n{3}".format(
                   rc, got, outputs.get("failed-jobs"), output))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


def run_depth(script, quiet, failed):
    def ck(name, cond, detail=""):
        if not cond:
            failed.append(name)
        if not quiet:
            check(name, cond, detail)

    for name, run_list, cap, want_capped, want_depth, run_id, warning in DEPTH_CASES:
        tmp, rt = tmpdirs()
        try:
            bindir = os.path.join(tmp, "bin")
            os.makedirs(bindir)
            gh = os.path.join(bindir, "gh")
            open(gh, "w").write(STUB_GH)
            os.chmod(gh, os.stat(gh).st_mode | stat.S_IEXEC)
            runs_path = os.path.join(tmp, "runs.json")
            json.dump(run_list or [], open(runs_path, "w"))
            env = {"PATH": bindir + os.pathsep + os.environ["PATH"],
                   "GH_TOKEN": "x", "ACTIONS_TOKEN": "x", "RUN_ID": run_id,
                   "CAP_INPUT": cap, "GITHUB_REPOSITORY": "o/r",
                   "STUB_RUNS": runs_path, "STUB_FAIL": "1" if run_list is None else ""}
            rc, output, outputs, _ = run_step(BASH, script, tmp, env, rt)
            ok = (rc == 0 and outputs.get("capped") == want_capped
                  and outputs.get("depth") == want_depth)
            if warning:
                ok = ok and warning in output
            ck(name, ok, "rc={0} outputs={1}\n{2}".format(rc, outputs, output))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


MUTATIONS = (
    ("#811 rate-limited arm removed", FAILED_JOBS,
     'if [ "$DIAGNOSE_OUTCOME" = "rate-limited" ]; then\n      :\n    elif', 'if'),
    ("depth read swallowed into [] again (the pre-fix read)", DEPTH,
     '2>"$RUNNER_TEMP/sdd-err.txt")"; then', '2>/dev/null || echo \'[]\')"; then'),
    ("depth jq failure read as 0 again (the pre-fix arm)", DEPTH,
     '\' 2>/dev/null)" || capped_unread "could not compute the depth from the run list"',
     '\' 2>/dev/null || echo 0)"'),
    ("failed read reported as uncapped", DEPTH,
     'echo "capped=true"\n  } >> "$GITHUB_OUTPUT"\n  exit 0\n}',
     'echo "capped=false"\n  } >> "$GITHUB_OUTPUT"\n  exit 0\n}'),
)

RUNNERS = {FAILED_JOBS: run_failed_jobs, DEPTH: run_depth}


def main():
    global BASH
    use_utf8_stdout()
    ensure_jq()
    BASH = resolve_bash()
    scripts = {name: find_step(WATCHDOG, name)["run"] for name in RUNNERS}
    for name, step, old, _new in MUTATIONS:
        if scripts[step].count(old) != 1:
            sys.exit("::error file={0}::mutation {1!r} no longer matches {2!r}'s text "
                     "exactly once. Update the mutation with the step.".format(WATCHDOG, name, step))
    for step, runner in RUNNERS.items():
        runner(scripts[step], False, [])
    for name, step, old, new in MUTATIONS:
        caught = []
        RUNNERS[step](scripts[step].replace(old, new), True, caught)
        check("mutation caught: " + name, bool(caught), "the suite stayed green with this fix reverted")
    if failures:
        print("verify-watchdog-failure-accounting: {0} failure(s)".format(len(failures)))
        sys.exit(1)
    print("verify-watchdog-failure-accounting: ok")


if __name__ == "__main__":
    main()
