#!/usr/bin/env python3
"""Gate 173 - the `lint` aggregate job cannot go green by omission.

specs/129-parallel-pr-lint splits the PR-time lint suite into shard jobs plus
`harness-tests`; one aggregate job named `lint` is the check every verdict
reader matches. This gate holds the aggregate's behaviour (contract items 2,
3, 4, 5 and 9) by EVALUATING the shipped workflow, not by matching its text:

  * exactly one job carries the check-run name `lint`, and its id is `lint`;
  * its `needs` lists every other PR-time job (the registry's own reading of
    which jobs are PR-time) and nothing that is not a job;
  * its job `if:` and its step's `if:`, evaluated with wc_gha_expr over
    every event and every needs-result combination, on a run that was and
    was not cancelled: on `pull_request` both are true in every state (so a
    failed, cancelled or skipped unit, or a cancelled run, still runs the
    step and turns the check red rather than leaving it skipped); on
    `push`, `schedule` and `workflow_dispatch` the job is false, and so is
    every unit's, so neither changes the run's conclusion;
  * its step, run for real under CI's `bash -e` with `NEEDS` set the way
    `toJSON(needs)` renders it, exits non-zero unless every result is
    exactly `success`, and names every non-success unit in its log and in
    $GITHUB_STEP_SUMMARY (SC-005).

An in-progress unit needs no case: a job's `needs` hold it until every
needed job has finished, so the aggregate cannot conclude while one runs.

Usage:
    python3 .github/scripts/verify-lint-aggregate.py
    python3 .github/scripts/verify-lint-aggregate.py --self-test
"""
import copy
import itertools
import json
import os
import shutil
import subprocess
import sys
import tempfile

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wc_gate_registry as registry  # noqa: E402
import wc_gha_expr as gha  # noqa: E402

WORKFLOW = os.path.join(".github", "workflows", "lint-workflows.yml")
AGGREGATE = "lint"
EVENTS = ("pull_request", "push", "schedule", "workflow_dispatch")
RESULTS = ("success", "failure", "cancelled", "skipped")
NEEDS_ENV = "${{ toJSON(needs) }}"


def _ctx(event, results, run_cancelled, job_level):
    """The status functions GitHub resolves for an `if:`.

    Job level: success()/failure() read the needed jobs' results. Step
    level (the aggregate's first and only step): nothing earlier in the
    job has failed, so success() is simply "the run was not cancelled".
    """
    vals = list(results.values())
    if job_level:
        ok = all(r == "success" for r in vals) and not run_cancelled
        failed = any(r == "failure" for r in vals)
    else:
        ok, failed = not run_cancelled, False
    return {"github.event_name": event, "always()": True,
            "cancelled()": run_cancelled, "success()": ok,
            "failure()": failed}


def _runs(cond, ctx):
    """Whether a job/step with `if: cond` runs. An absent if: is success()."""
    expr = str(cond).strip() if cond not in (None, "") else "success()"
    has_status = any(f in expr for f in ("success()", "failure()",
                                         "cancelled()", "always()"))
    if not has_status:
        expr = "success() && (" + expr.replace("${{", "").replace("}}", "") + ")"
    return gha.evaluate_if(expr, ctx, known=("github.",))


def _combos(needs):
    """All success, every unit alone at every non-success result, and a few
    mixed states: enough to catch a check that tolerates any one value."""
    yield {n: "success" for n in needs}
    for n, r in itertools.product(needs, RESULTS[1:]):
        d = {m: "success" for m in needs}
        d[n] = r
        yield d
    for r in RESULTS[1:]:
        yield {n: r for n in needs}
    yield {n: RESULTS[i % len(RESULTS)] for i, n in enumerate(needs)}


def _run_step(step, results, bash):
    """(exit code, log, summary) of the aggregate step under `results`."""
    tmp = tempfile.mkdtemp(prefix="gate173-")
    try:
        script = os.path.join(tmp, "step.sh")
        summary = os.path.join(tmp, "summary.md")
        with open(script, "w", encoding="utf-8") as fh:
            fh.write(str(step.get("run") or ""))
        open(summary, "w").close()
        env = dict(os.environ)
        env["NEEDS"] = json.dumps(
            {k: {"result": v, "outputs": {}} for k, v in results.items()},
            indent=2)
        env["GITHUB_STEP_SUMMARY"] = summary
        p = subprocess.run([bash, "-e", script], env=env, cwd=tmp,
                           capture_output=True, text=True, timeout=60)
        with open(summary, encoding="utf-8") as fh:
            return p.returncode, p.stdout + p.stderr, fh.read()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def check(doc, bash=None):
    """Failures (list of strings) for a parsed lint-workflows.yml."""
    bash = bash or shutil.which("bash")
    jobs = doc.get("jobs") or {}
    named = [k for k, j in jobs.items()
             if ((j or {}).get("name") or k) == AGGREGATE]
    if len(named) != 1 or named[0] != AGGREGATE:
        return ["exactly one job must carry the check-run name 'lint' and "
                "its id must be 'lint'; found {0}".format(named)]
    agg = jobs[AGGREGATE] or {}
    fails = []
    needs = agg.get("needs") or []
    if isinstance(needs, str):
        needs = [needs]
    for n in needs:
        if n not in jobs:
            fails.append("the aggregate needs '{0}', which is not a "
                         "job".format(n))
    units = [k for k, j in jobs.items()
             if k != AGGREGATE and registry._job_runs_on_pull_request(j)]
    for k in units:
        if k not in needs:
            fails.append("PR-time job '{0}' is not in the aggregate's "
                         "needs".format(k))
    needs = [n for n in needs if n in jobs]
    if fails:
        return fails

    # Item 9: on every other event no unit runs.
    for k in units:
        for event in EVENTS[1:]:
            if _runs(jobs[k].get("if"), _ctx(event, {}, False, True)):
                fails.append("unit '{0}' runs on {1}; units must be skipped "
                             "off pull_request".format(k, event))
                break

    steps = agg.get("steps") or []
    if len(steps) != 1:
        return fails + ["the aggregate must have exactly one step; it has "
                        "{0}".format(len(steps))]
    step = steps[0]
    if str((step.get("env") or {}).get("NEEDS") or "").strip() != NEEDS_ENV:
        fails.append("the aggregate step's env NEEDS is not exactly "
                     "{0}".format(NEEDS_ENV))
    if step.get("shell") or step.get("uses"):
        fails.append("the aggregate step must be a plain run: step under "
                     "CI's default shell")

    # Item 4: the job and its step, every event, every result, cancelled
    # run or not.
    job_bad = step_bad = None
    for event in EVENTS:
        for results in _combos(needs):
            for cancelled in (False, True):
                runs = _runs(agg.get("if"),
                             _ctx(event, results, cancelled, True))
                if event != "pull_request":
                    if runs and job_bad is None:
                        job_bad = ("the aggregate runs on {0}; it must be "
                                   "skipped off pull_request".format(event))
                    continue
                state = "{0}{1}".format(
                    ", ".join("{0}={1}".format(k, v)
                              for k, v in results.items() if v != "success")
                    or "every unit success",
                    " on a cancelled run" if cancelled else "")
                if not runs and job_bad is None:
                    job_bad = ("the aggregate's job if: skips it on "
                               "pull_request when {0}, which reads as green "
                               "by omission; it needs always()".format(state))
                if runs and not _runs(step.get("if"),
                                      _ctx(event, results, cancelled, False)):
                    if step_bad is None:
                        step_bad = ("the aggregate step is skipped on "
                                    "pull_request when {0}; its if: needs "
                                    "always() so the check fails instead "
                                    "of skipping".format(state))
    fails += [f for f in (job_bad, step_bad) if f]

    # Item 5 and SC-005: run the step itself.
    if not bash:
        return fails + ["no bash on PATH to run the aggregate step"]
    for results in _combos(needs):
        code, log, summary = _run_step(step, results, bash)
        bad = [k for k, v in results.items() if v != "success"]
        if not bad and code != 0:
            fails.append("the aggregate step fails when every unit "
                         "succeeded (exit {0}): {1}".format(code, log.strip()))
            break
        if bad and code == 0:
            fails.append("the aggregate step passes when {0}".format(
                ", ".join("{0}={1}".format(k, results[k]) for k in bad)))
            break
        unnamed = [k for k in bad if k not in log]
        if unnamed:
            fails.append("the aggregate step's log does not name the "
                         "non-success unit(s) {0}".format(unnamed))
            break
        unsummed = [k for k in bad if k not in summary]
        if unsummed:
            fails.append("the aggregate step does not write the non-success "
                         "unit(s) {0} to $GITHUB_STEP_SUMMARY".format(unsummed))
            break
    return fails


def _base():
    pr = "github.event_name == 'pull_request'"
    jobs = {"lint-shard-%d" % i: {"if": pr, "steps": []} for i in (1, 2)}
    jobs["harness-tests"] = {"name": "harness tests", "if": pr, "steps": []}
    jobs["names-and-tags"] = {"if": "github.event_name != 'pull_request'",
                              "steps": []}
    jobs["lint"] = {
        "if": "${{ always() && " + pr + " }}",
        "needs": ["lint-shard-1", "lint-shard-2", "harness-tests"],
        "steps": [{
            "name": "Every lint unit succeeded",
            "if": "${{ always() }}",
            "env": {"NEEDS": NEEDS_ENV},
            "run": ("bad=\"$(printf '%s' \"$NEEDS\" | jq -r 'to_entries[] | "
                    "select(.value.result != \"success\") | "
                    "\"\\(.key): \\(.value.result)\"')\"\n"
                    "if [ -n \"$bad\" ]; then\n"
                    "  printf '%s\\n' \"$bad\"\n"
                    "  printf '%s\\n' \"$bad\" >> \"$GITHUB_STEP_SUMMARY\"\n"
                    "  exit 1\n"
                    "fi\n")}]}
    return {"jobs": jobs}


def self_test():
    cases = []

    def case(label, mutate, expect):
        doc = copy.deepcopy(_base())
        mutate(doc)
        got = check(doc)
        ok = (not got) if expect is None else any(expect in g for g in got)
        cases.append(ok)
        print("{0} {1}".format("ok  " if ok else "FAIL", label))
        if not ok:
            print("     expected {0!r}, got {1}".format(expect, got))

    def j(d):
        return d["jobs"]["lint"]

    def s(d):
        return j(d)["steps"][0]

    pr = "github.event_name == 'pull_request'"
    case("the real shape passes", lambda d: None, None)
    case("a job if: without always() fails",
         lambda d: j(d).update({"if": pr}), "it needs always()")
    case("a job if: with !cancelled() fails on a cancelled run",
         lambda d: j(d).update({"if": "${{ !cancelled() && " + pr + " }}"}),
         "on a cancelled run")
    case("an aggregate that also runs on push fails",
         lambda d: j(d).update({"if": "${{ always() }}"}),
         "the aggregate runs on push")
    case("a step with no if: fails on a cancelled run",
         lambda d: s(d).pop("if"), "aggregate step is skipped")
    case("a step guarded !cancelled() fails on a cancelled run",
         lambda d: s(d).update({"if": "${{ !cancelled() }}"}),
         "aggregate step is skipped")
    case("a skip-tolerant result check fails",
         lambda d: s(d).update({"run": s(d)["run"].replace(
             '.value.result != "success"',
             '.value.result == "failure"')}),
         "passes when")
    case("a step that never exits non-zero fails",
         lambda d: s(d).update({"run": s(d)["run"].replace("exit 1", "true")}),
         "passes when")
    case("a step that fails when every unit succeeded fails",
         lambda d: s(d).update({"run": "exit 1"}), "every unit succeeded")
    case("a step that does not name the units fails",
         lambda d: s(d).update({"run": s(d)["run"].replace(
             "\\(.key): ", "")}), "does not name")
    case("a step that skips the step summary fails",
         lambda d: s(d).update({"run": s(d)["run"].replace(
             '>> "$GITHUB_STEP_SUMMARY"', ">/dev/null")}),
         "GITHUB_STEP_SUMMARY")
    case("a NEEDS env that is not toJSON(needs) fails",
         lambda d: s(d)["env"].update({"NEEDS": "${{ needs }}"}),
         "env NEEDS")
    case("an aggregate that omits harness-tests fails",
         lambda d: j(d).update({"needs": ["lint-shard-1", "lint-shard-2"]}),
         "'harness-tests' is not in")
    case("an aggregate needing a missing job fails",
         lambda d: j(d)["needs"].append("lint-shard-9"),
         "'lint-shard-9', which is not a job")
    case("a shard named lint fails",
         lambda d: d["jobs"]["lint-shard-1"].update({"name": "lint"}),
         "exactly one job")
    case("an unlisted PR-time shard fails",
         lambda d: d["jobs"].update({"lint-shard-3": {"if": pr, "steps": []}}),
         "'lint-shard-3' is not in")
    case("a unit that also runs on push fails",
         lambda d: d["jobs"]["lint-shard-2"].pop("if"),
         "unit 'lint-shard-2' runs on push")
    case("a missing aggregate fails",
         lambda d: d["jobs"].pop("lint"), "exactly one job")
    bad = cases.count(False)
    print("verify-lint-aggregate self-test: {0}/{1} passed".format(
        len(cases) - bad, len(cases)))
    return 1 if bad else 0


def main(argv):
    if "--self-test" in argv:
        return self_test()
    with open(WORKFLOW, encoding="utf-8") as fh:
        doc = yaml.safe_load(fh) or {}
    fails = check(doc)
    for f in fails:
        print("::error file={0}::Gate 173: {1}".format(WORKFLOW, f))
    if fails:
        return 1
    print("Gate 173: the `lint` aggregate runs on every pull_request state, "
          "cancelled runs included, needs every PR-time unit and fails "
          "unless each is success.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
