#!/usr/bin/env python3
"""Gate 75 -- the watchdog wrapper is one job, and the stage resolves its own
run-name (FR-020).

`wing-commander-8-watchdog.yml` used to carry a `resolve` job whose entire
output was two strings: the inspected run's id and the display name of the
workflow it belongs to. A wrapper job is a runner allocation, and GitHub
bills a whole minute however short it runs, so that two-second job cost as
much as the inspection it fed. Spec 058 folds it away: the id is a one-line
expression, and the name is resolved inside `watchdog.yml`'s own `collect`
job, which was already calling `gh run view` for five other fields.

The fold is only safe while both halves hold, and each can regress alone:

  * the wrapper must not grow a second job back, must call the stage
    directly (`uses:`), and must NOT pass `run-name:` -- passing an empty
    string explicitly is the same as passing nothing today, but passing a
    WRONG one (the run's title rather than its workflow name) is the defect
    Gate 70 exists for, and the cheapest way to keep it impossible here is
    for the wrapper not to speak about run-name at all;
  * the stage must actually resolve the name when the input is empty. A
    silently-empty run-name is not a visible failure: watchdog.yml's
    `case "$RUN_NAME"` arms simply match nothing, every stage-scoped
    collector skips itself as "not the right stage", and the inspection
    reports a clean pass having looked at almost nothing.

So this gate reads the wrapper's shape from YAML and EXECUTES the stage's
shipped resolution block twice -- once with the input empty (the wrapper's
own invocation), once with a caller-supplied value (the compatibility case
FR-020 promises is unchanged) -- against a `gh` stub.

Four mutations (the wrapper passes run-name again, the wrapper regains a
second job, the wrapper stops calling the stage directly, the stage's
empty-input fallback dropped) must each break an assertion.

Wiring: lint-workflows.yml, Gate 75.
"""
import os
import shutil
import stat
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_shell_harness import (ensure_jq, find_step, resolve_bash,  # noqa: E402
                              run_step, use_utf8_stdout)

import yaml  # noqa: E402

WRAPPER = os.path.join(".github", "workflows", "wing-commander-8-watchdog.yml")
STAGE = os.path.join(".github", "workflows", "watchdog.yml")
WRAPPER_JOB = "watchdog"
RESOLVE_STEP = "Fetch inspected run metadata"
COLLECT_JOB = "collect"

RUN_ID = "17712345678"
WORKFLOW_NAME = "Wing Commander · 5 implement"
CALLER_SUPPLIED = "Wing Commander · 8 watchdog"

GH_STUB = """#!/usr/bin/env bash
# `gh run view <id> --repo <r> --json <fields>` -> the fields the shipped
# step asks for. workflowName is the workflow's declared name, which is what
# the stage must key on (Gate 70 owns the never-the-run-title half).
cat <<'JSON'
{"headBranch":"spec/058-per-job-minute-floor","headSha":"deadbeef",
 "conclusion":"success","url":"https://example.invalid/runs/17712345678",
 "event":"workflow_run","createdAt":"2026-01-01T00:00:00Z",
 "updatedAt":"2026-01-01T00:01:00Z","databaseId":17712345678,
 "workflowName":"WORKFLOW_NAME_PLACEHOLDER"}
JSON
"""


def load_subject():
    wrapper = yaml.safe_load(open(WRAPPER, encoding="utf-8")) or {}
    stage = yaml.safe_load(open(STAGE, encoding="utf-8")) or {}
    # PyYAML resolves the `on:` key to the boolean True (YAML 1.1 truthy).
    triggers = stage.get("on") or stage.get(True) or {}
    collect = (stage.get("jobs") or {}).get(COLLECT_JOB) or {}
    return {
        "wrapper:jobs": dict(wrapper.get("jobs") or {}),
        "stage:run-name-input": dict(
            ((triggers.get("workflow_call") or {}).get("inputs") or {})
            .get("run-name") or {}),
        "stage:collect-outputs": dict(collect.get("outputs") or {}),
        "stage:resolve-run": str(find_step(STAGE, RESOLVE_STEP).get("run") or ""),
        "stage:text": open(STAGE, encoding="utf-8").read(),
    }


def wrapper_failures(subject):
    broke = []
    jobs = subject["wrapper:jobs"]
    if sorted(jobs) != [WRAPPER_JOB]:
        broke.append(f"{WRAPPER} declares job(s) {sorted(jobs)}; the fold "
                     f"leaves exactly [{WRAPPER_JOB!r}] -- every extra job is a "
                     f"billed runner minute that only gates and forwards")
    job = jobs.get(WRAPPER_JOB) or {}
    if not str(job.get("uses") or "").strip():
        broke.append(f"the {WRAPPER_JOB!r} job is not a `uses:` call -- the "
                     f"wrapper must call the stage directly, not re-implement "
                     f"any part of it")
    if job.get("steps"):
        broke.append(f"the {WRAPPER_JOB!r} job declares `steps:` -- a wrapper "
                     f"job that runs its own steps is the resolve job under "
                     f"another name")
    with_ = dict(job.get("with") or {})
    if "run-name" in with_:
        broke.append(f"the wrapper still passes `run-name:` ({with_['run-name']!r}). "
                     f"FR-020 hands that resolution to the stage; a wrapper "
                     f"that supplies it can supply the run TITLE by mistake, "
                     f"which is the defect Gate 70 exists for")
    if not str(with_.get("run-id") or "").strip():
        broke.append("the wrapper passes no `run-id:` -- the stage has no way "
                     "to know what it is inspecting")
    return broke


def stage_contract_failures(subject):
    broke = []
    spec = subject["stage:run-name-input"]
    if not spec:
        broke.append(f"{STAGE} no longer declares a `run-name` workflow_call "
                     f"input; the wrapper stopped passing one, so removing it "
                     f"outright breaks every adopter that still does")
    else:
        if spec.get("required", False):
            broke.append("`run-name` is declared required: the wrapper does not "
                         "pass it, so the stage would fail to start")
        if spec.get("default", None) != "":
            broke.append(f"`run-name`'s default is {spec.get('default')!r}, not "
                         f"'' -- the empty default is what selects the stage's "
                         f"own resolution")
    if subject["stage:collect-outputs"].get("run-name", "") == "":
        broke.append(f"the {COLLECT_JOB!r} job publishes no `run-name` output -- "
                     f"the resolved name never reaches the jobs and comments "
                     f"that key on it")
    elif "needs.collect.outputs.run-name" not in subject["stage:text"]:
        broke.append("nothing in the stage consumes "
                     "`needs.collect.outputs.run-name` -- the resolution would "
                     "be dead code and an empty value would go unnoticed")
    return broke


def _write_exec(path, content):
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(content)
    os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def resolution_failures(subject, bash):
    """Run the shipped resolution block for both invocation shapes."""
    broke = []
    # (label, the run-name input the caller supplied, what must come out)
    cases = [("the wrapper's own invocation (no run-name supplied)", "", WORKFLOW_NAME),
             ("an adopter still supplying run-name (FR-020 compatibility)",
              CALLER_SUPPLIED, CALLER_SUPPLIED)]
    for label, supplied, want in cases:
        tmp = tempfile.mkdtemp(prefix="wc-gate75-")
        try:
            bindir = os.path.join(tmp, "bin")
            os.makedirs(bindir)
            _write_exec(os.path.join(bindir, "gh"),
                        GH_STUB.replace("WORKFLOW_NAME_PLACEHOLDER", WORKFLOW_NAME))
            env = {"GH_TOKEN": "app-token", "ACTIONS_TOKEN": "actions-token",
                   "RUN_ID": RUN_ID, "RUN_NAME_INPUT": supplied,
                   "GITHUB_REPOSITORY": "acme/wing-commander",
                   "PATH": bindir + os.pathsep + os.environ.get("PATH", "")}
            rc, out, outputs, _summary = run_step(
                bash, subject["stage:resolve-run"], tmp, env, tmp)
            if rc != 0:
                broke.append(f"{label}: the resolution step exited {rc}: "
                             f"{out.strip()[:200]}")
                continue
            got = outputs.get("run-name", "")
            if got != want:
                broke.append(f"{label}: run-name resolved to {got!r}, expected "
                             f"{want!r}")
            # The other five fields must survive the change untouched -- the
            # same `gh run view` call feeds them.
            if outputs.get("url", "") == "":
                broke.append(f"{label}: the step stopped publishing `url`; the "
                             f"posted comments link the inspected run with it")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    return broke


def suite(subject, bash):
    return (wrapper_failures(subject) + stage_contract_failures(subject)
            + resolution_failures(subject, bash))


# --------------------------------------------------------------------------
# Mutations
# --------------------------------------------------------------------------
def mut_wrapper_passes_run_name(subject):
    s = dict(subject)
    jobs = {k: dict(v) for k, v in subject["wrapper:jobs"].items()}
    job = jobs.get(WRAPPER_JOB, {})
    job["with"] = dict(job.get("with") or {},
                       **{"run-name": "${{ github.event.workflow_run.name }}"})
    jobs[WRAPPER_JOB] = job
    s["wrapper:jobs"] = jobs
    return s


def mut_wrapper_regains_a_resolve_job(subject):
    s = dict(subject)
    s["wrapper:jobs"] = dict(subject["wrapper:jobs"],
                             resolve={"runs-on": "ubuntu-latest", "steps": []})
    return s


def mut_wrapper_stops_calling_the_stage(subject):
    s = dict(subject)
    jobs = {k: dict(v) for k, v in subject["wrapper:jobs"].items()}
    job = jobs.get(WRAPPER_JOB, {})
    job.pop("uses", None)
    job["steps"] = [{"name": "inlined", "run": "echo hi"}]
    jobs[WRAPPER_JOB] = job
    s["wrapper:jobs"] = jobs
    return s


def mut_stage_drops_the_empty_input_fallback(subject):
    s = dict(subject)
    s["stage:resolve-run"] = subject["stage:resolve-run"].replace(
        "jq -r '.workflowName // empty'", "jq -r 'empty'")
    return s


MUTATIONS = [
    ("the wrapper passes run-name again", mut_wrapper_passes_run_name),
    ("the wrapper regains a resolve job", mut_wrapper_regains_a_resolve_job),
    ("the wrapper stops calling the stage directly",
     mut_wrapper_stops_calling_the_stage),
    ("the stage's empty-input fallback is dropped",
     mut_stage_drops_the_empty_input_fallback),
]


def main():
    use_utf8_stdout()
    ensure_jq()
    bash = resolve_bash()
    subject = load_subject()
    failures = suite(subject, bash)
    for f in failures:
        print(f"::error::{f}")
    mutation_failures = 0
    for label, mutate in MUTATIONS:
        mutated = mutate(subject)
        if mutated == subject:
            print(f"::error::mutation {label!r} changed nothing -- the shape it "
                  f"targets has moved; update the mutation with it.")
            mutation_failures += 1
            continue
        if suite(mutated, bash):
            print(f"Mutation OK - {label}.")
        else:
            print(f"::error::MUTATION SURVIVED - {label} broke nothing in this gate.")
            mutation_failures += 1
    print(f"Gate 75: wrapper shape + 2 invocation shape(s), "
          f"{len(MUTATIONS)} mutation(s); {len(failures)} failure(s), "
          f"{mutation_failures} mutation failure(s).")
    return 1 if failures or mutation_failures else 0


if __name__ == "__main__":
    sys.exit(main())
