#!/usr/bin/env python3
"""Gate 70 -- 8b stands down on a skipped stage-8 run only when the run that
stage 8 was asked to inspect was itself skipped.

Stage 8 (wing-commander-8-watchdog.yml) declines a source run whose
conclusion is 'skipped': it executed nothing, so FR-026 leaves the watchdog
nothing to say about it. Every such decline makes the stage-8 run itself
conclude 'skipped', and 8b (wing-commander-8b-watchdog-self.yml) must not
file a pipeline-defect issue for it. But a stage-8 run can also conclude
'skipped' because a regression in its own `if:` gated off a source run that
DID execute -- and 8b's check 1 is the only thing that would ever notice. If
8b keyed on stage 8's conclusion alone, both cases would look the same and
the regression would pass as a healthy silence.

8b's workflow_run payload describes the stage-8 run, not its source, and a
run whose jobs were all gated off leaves no output behind. So stage 8 writes
the source's conclusion at the end of its `run-name:` and 8b reads it back
from `display_title`. The two files share a string convention with nothing
else holding them together; this gate is that thing. It evaluates the REAL
expressions from both files -- stage 8's run-name and job guards, 8b's job
guard -- for every source conclusion, paused and unpaused, event-driven and
dispatched, and asserts:

  * stage 8 runs exactly when unpaused and the source was not skipped;
  * 8b stands down when paused, or when stage 8 skipped a skipped source;
  * 8b still runs (so check 1 fires) when stage 8 concluded 'skipped' for a
    source that executed, or on a dispatch -- the regression case.

Setting `run-name:` also changes what the Actions API reports in a run's
`name`: it becomes the title, not the workflow's declared name. The
inspected run's identity -- which watchdog.yml keys its `case "$RUN_NAME"`
arms and its FR-018 self-dispatch cap on -- is derived in watchdog.yml's
own `collect` job since spec 058 folded stage 8's `resolve` job away, so
that step must read the workflow's own name (`--json workflowName`) and
never the run's `name`. Read from the title, a dispatched re-inspection of
a stage-8 run gives watchdog.yml "inspect ... (success)" where it expects
"Wing Commander · 8 watchdog", and the cap never engages. This gate
asserts the identity source too, now on the stage rather than the wrapper.

Four mutations -- 8b keyed on stage 8's conclusion alone, the run-name
suffix changed in one file only, stage 8's skipped-source guard dropped,
the inspected run's identity read from its run title -- must each break an
assertion, so the gate proves it can see the drift it exists for. It reads
the two workflow files only; it makes no network call.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# The GitHub-expression evaluator these assertions run on lives in one place
# (wc_gha_expr.py) -- Gate 73 evaluates watchdog.yml's guards with the same
# semantics, and a second copy would diverge on the first fix.
from wc_gha_expr import evaluate, interpolate, truthy  # noqa: E402
from wc_shell_harness import find_job, use_utf8_stdout  # noqa: E402

import yaml  # noqa: E402

STAGE8 = os.path.join(".github", "workflows", "wing-commander-8-watchdog.yml")
SELF = os.path.join(".github", "workflows", "wing-commander-8b-watchdog-self.yml")
# The stage the wrapper calls; since spec 058 it, not the wrapper, resolves
# the inspected run's identity (the wrapper's `resolve` job was folded away).
STAGE = os.path.join(".github", "workflows", "watchdog.yml")
# One job, since that fold: the wrapper's whole remaining body.
STAGE8_JOBS = ("watchdog",)
SELF_JOB = "verify"
PAUSE_VAR = "vars.WING_COMMANDER_WATCHDOG_PAUSED"
SOURCE_CONCLUSIONS = ("success", "failure", "cancelled", "timed_out", "skipped")


# --------------------------------------------------------------------------
# The subject expressions and the scenarios
# --------------------------------------------------------------------------
def load_subject():
    with open(STAGE8, encoding="utf-8") as fh:
        run_name = (yaml.safe_load(fh) or {}).get("run-name")
    if not isinstance(run_name, str) or not run_name.strip():
        sys.exit(f"::error file={STAGE8}::no `run-name:` -- 8b cannot tell a "
                 f"declined skipped source from a gating regression without it.")
    with open(STAGE, encoding="utf-8") as fh:
        subject = {"run-name": run_name, "stage:text": fh.read()}
    for job in STAGE8_JOBS:
        subject[f"stage8:{job}"] = str(find_job(STAGE8, job).get("if") or "")
    subject["8b"] = str(find_job(SELF, SELF_JOB).get("if") or "")
    for key, val in subject.items():
        if not val.strip():
            sys.exit(f"::error::{key} has no `if:` -- nothing to evaluate. "
                     f"Removing a guard is the regression this gate exists for.")
    return subject


def source_ctx(paused, conclusion):
    """Stage 8's context: event-driven (conclusion set) or dispatch (None)."""
    ctx = {PAUSE_VAR: "true" if paused else ""}
    if conclusion is None:
        ctx.update({"github.event_name": "workflow_dispatch", "inputs.run-id": "17712345678"})
    else:
        ctx.update({"github.event_name": "workflow_run",
                    "github.event.workflow_run.id": 17712345678.0,
                    "github.event.workflow.name": "Wing Commander · 2 clarify",
                    "github.event.workflow_run.conclusion": conclusion})
    return ctx


IDENTITY_MUST = ("workflowName",
                 "run_name=\"$(printf '%s' \"$json\" | jq -r '.workflowName // empty')\"")
IDENTITY_MUST_NOT = ("jq -r '.name // empty'", "--json name --jq .name",
                     "github.event.workflow_run.name")


def identity_failures(text):
    """The inspected run's identity must be the workflow's declared name.

    A run's `name` in the Actions API is its run title once the workflow sets
    `run-name:` -- which stage 8 does -- so deriving identity from the run's
    name gives watchdog.yml a title like "inspect ... (success)" where it
    expects "Wing Commander · 8 watchdog", and its FR-018 self-dispatch cap
    never engages. Checked on watchdog.yml's text -- the stage resolves its
    own run-name since spec 058 -- comments included, so the forbidden forms
    may not be named there either.
    """
    broke = []
    for needle in IDENTITY_MUST:
        if needle not in text:
            broke.append(f"watchdog.yml no longer resolves identity via {needle!r}")
    for needle in IDENTITY_MUST_NOT:
        if needle in text:
            broke.append(f"watchdog.yml resolves identity via {needle!r} -- that is "
                         f"the run title once run-name: is set, not the workflow name")
    return broke


def suite(subject):
    """Every broken assertion, as a message. Empty = the pair is consistent."""
    broke = identity_failures(subject.get("stage:text", ""))
    for paused in (False, True):
        for source in SOURCE_CONCLUSIONS + (None,):
            where = f"paused={paused} source={source or 'dispatch'}"
            ctx = source_ctx(paused, source)
            try:
                title = interpolate(subject["run-name"], ctx)
                ran = [truthy(evaluate(subject[f"stage8:{j}"], ctx)) for j in STAGE8_JOBS]
            except (ValueError, IndexError) as exc:
                broke.append(f"{where}: stage 8 expression did not evaluate: {exc}")
                continue
            want = not paused and source != "skipped"
            for job, got in zip(STAGE8_JOBS, ran):
                if got != want:
                    broke.append(f"{where}: stage 8 job {job!r} runs={got}, expected {want}")

            # What 8b hears. A stage-8 run that executed concludes success or
            # failure; one whose jobs were all gated off concludes skipped --
            # whether by design (paused, skipped source) or by regression,
            # which is modelled by forcing 'skipped' whatever its guards said.
            outcomes = [("executed", "success"), ("executed", "failure"),
                        ("gated off", "skipped")]
            for how, stage8_conclusion in outcomes:
                deliberate = paused or source == "skipped"
                if how == "gated off":
                    want8b = not deliberate
                else:
                    want8b = not paused
                ctx8b = {PAUSE_VAR: ctx[PAUSE_VAR], "github.event_name": "workflow_run",
                         "github.event.workflow_run.conclusion": stage8_conclusion,
                         "github.event.workflow_run.display_title": title}
                try:
                    got8b = truthy(evaluate(subject["8b"], ctx8b))
                except (ValueError, IndexError) as exc:
                    broke.append(f"{where}: 8b's if: did not evaluate: {exc}")
                    break
                if got8b != want8b:
                    broke.append(f"{where}, stage 8 {how} ({stage8_conclusion}), title "
                                 f"{title!r}: 8b runs={got8b}, expected {want8b}")
    return broke


def mut_self_keys_on_stage8_alone(subject):
    s = dict(subject)
    s["8b"] = re.sub(r"\(\s*(github\.event\.workflow_run\.conclusion != 'skipped')\s*\|\|.*\)\s*$",
                     r"\1", subject["8b"], flags=re.S)
    return s


def mut_suffix_drifts(subject):
    s = dict(subject)
    s["run-name"] = subject["run-name"].replace("({2})", "[{2}]")
    return s


def mut_stage8_guard_dropped(subject):
    s = dict(subject)
    for job in STAGE8_JOBS:
        s[f"stage8:{job}"] = re.sub(r"&&\s*github\.event\.workflow_run\.conclusion != 'skipped'",
                                    "", subject[f"stage8:{job}"])
    return s


def mut_identity_from_run_title(subject):
    s = dict(subject)
    s["stage:text"] = subject["stage:text"].replace(
        IDENTITY_MUST[1],
        "run_name=\"$(printf '%s' \"$json\" | jq -r '.name // empty')\"")
    return s


MUTATIONS = [
    ("8b keys on stage 8's conclusion alone", mut_self_keys_on_stage8_alone),
    ("run-name suffix changed in stage 8 only", mut_suffix_drifts),
    ("stage 8's skipped-source guard dropped", mut_stage8_guard_dropped),
    ("inspected run's identity read from its run title", mut_identity_from_run_title),
]


def main():
    use_utf8_stdout()
    subject = load_subject()
    failures = suite(subject)
    for f in failures:
        print(f"::error::{f}")
    mutation_failures = 0
    for label, mutate in MUTATIONS:
        mutated = mutate(subject)
        if mutated == subject:
            print(f"::error::mutation {label!r} changed nothing -- the expression it "
                  f"targets has moved; update the mutation with it.")
            mutation_failures += 1
            continue
        broke = suite(mutated)
        if broke:
            print(f"Mutation OK - {label}: {len(broke)} assertion(s) fail.")
        else:
            print(f"::error::MUTATION SURVIVED - {label} broke nothing in this gate.")
            mutation_failures += 1
    print(f"Gate 70: {len(SOURCE_CONCLUSIONS) + 1} source shape(s) x paused/unpaused, "
          f"{len(MUTATIONS)} mutation(s); {len(failures)} failure(s), "
          f"{mutation_failures} mutation failure(s).")
    return 1 if failures or mutation_failures else 0


if __name__ == "__main__":
    sys.exit(main())
