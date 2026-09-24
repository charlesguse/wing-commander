#!/usr/bin/env python3
"""Gate 79 -- the metrics wrapper no longer reacts to the watchdog, and its
daily sweep does not collide with another schedule (FR-030(b)/(c)).

Spec 058 stops persisting per watchdog completion. That trigger fired for
every inspection in the repository, and after FR-031 a healthy one emits
no record at all — so the run it started discovered nothing and billed a
job-minute for the privilege. A signal-bearing inspection still emits, and
the daily sweep is what collects it.

Both halves of that are one-line facts in a trigger block, which is
exactly the kind of thing a later edit restores without noticing:

  * re-adding "Wing Commander · 8 watchdog" to workflow_run.workflows
    silently reinstates the per-inspection run, and nothing fails;
  * a `schedule:` entry that shares its minute AND hour with another
    scheduled workflow in this repository queues behind it. GitHub's
    scheduled dispatch is best-effort and already skews under load; two
    workflows asking for the same instant is a self-inflicted delay on the
    one job this feature deliberately added (research.md R-C6).

This gate reads the trigger blocks of every workflow in the repository and
asserts both, plus that the `sweep` job the schedule exists to start is
actually wired to it. Four mutations must each break an assertion.

Wiring: lint-workflows.yml, Gate 79.
"""
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_gha_expr import evaluate, truthy  # noqa: E402
from wc_shell_harness import use_utf8_stdout  # noqa: E402

import yaml  # noqa: E402

WRAPPER = os.path.join(".github", "workflows", "wing-commander-metrics-persist.yml")
WORKFLOWS = os.path.join(".github", "workflows")
# The delta document states this trigger block literally, as the contract an
# adopter forking the wrapper reads. A document that drifts from the file it
# describes is worse than no document: it is the one a reader trusts.
CONTRACT = os.path.join("specs", "058-per-job-minute-floor", "contracts",
                        "metrics-persist-sweep-delta.md")
WATCHDOG_NAME = "Wing Commander · 8 watchdog"
SWEEP_JOB = "sweep"
PERSIST_JOB = "persist"


def triggers(doc):
    """A workflow's `on:` block. PyYAML resolves the bare key `on` to the
    boolean True (YAML 1.1 truthiness), so both spellings are checked."""
    return doc.get("on") or doc.get(True) or {}


def load(path):
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def other_crons():
    """(workflow path, cron) for every scheduled workflow but the wrapper."""
    found = []
    for path in sorted(glob.glob(os.path.join(WORKFLOWS, "*.yml"))
                       + glob.glob(os.path.join(WORKFLOWS, "*.yaml"))):
        if os.path.abspath(path) == os.path.abspath(WRAPPER):
            continue
        for entry in (triggers(load(path)).get("schedule") or []):
            cron = str((entry or {}).get("cron") or "").strip()
            if cron:
                found.append((path, cron))
    return found


def minute_hour(cron):
    parts = cron.split()
    return tuple(parts[:2]) if len(parts) >= 2 else (cron, "")


def contract_block():
    """The `on:` block the delta document publishes as the amended
    contract, parsed as YAML — not scanned for substrings, so a clause
    that moved rather than changed still reads correctly."""
    with open(CONTRACT, encoding="utf-8") as fh:
        text = fh.read()
    # The document carries an "Amended contract" paragraph per delta; the
    # one with the trigger block is the wrapper's, so anchor on its heading
    # rather than on the first match.
    marker = "**Amended contract**:"
    section = text.find("## Wrapper")
    at = text.find(marker, section) if section != -1 else -1
    if section == -1 or at == -1:
        sys.exit(f"::error file={CONTRACT}::no '## Wrapper' section with an "
                 f"'{marker}' paragraph -- this gate compares the shipped "
                 f"trigger block against the one this document publishes; "
                 f"update them together.")
    fence = text.find("```yaml", at)
    end = text.find("```", fence + 7)
    if fence == -1 or end == -1:
        sys.exit(f"::error file={CONTRACT}::the amended contract no longer "
                 f"carries a ```yaml block to compare against.")
    return triggers(yaml.safe_load(text[fence + 7:end]) or {})


def load_subject():
    doc = load(WRAPPER)
    on = triggers(doc)
    documented = contract_block()
    return {
        "workflows": list((on.get("workflow_run") or {}).get("workflows") or []),
        "schedule": [str((e or {}).get("cron") or "").strip()
                     for e in (on.get("schedule") or [])],
        "dispatch-inputs": dict((on.get("workflow_dispatch") or {}).get("inputs") or {}),
        "jobs": dict(doc.get("jobs") or {}),
        "documented-workflows": list(
            (documented.get("workflow_run") or {}).get("workflows") or []),
        "documented-schedule": [str((e or {}).get("cron") or "").strip()
                                for e in (documented.get("schedule") or [])],
    }


# Every trigger shape the wrapper can see, and which job must own it.
# (label, context, job that must run)
EVENTS = [
    ("a stage completion", {"github.event_name": "workflow_run",
                            "github.event.workflow_run.conclusion": "success",
                            "inputs.since": ""}, PERSIST_JOB),
    ("the daily schedule", {"github.event_name": "schedule",
                            "github.event.workflow_run.conclusion": "",
                            "inputs.since": ""}, SWEEP_JOB),
    ("a single-run dispatch", {"github.event_name": "workflow_dispatch",
                               "github.event.workflow_run.conclusion": "",
                               "inputs.since": ""}, PERSIST_JOB),
    ("a sweep dispatch", {"github.event_name": "workflow_dispatch",
                          "github.event.workflow_run.conclusion": "",
                          "inputs.since": "2026-09-01T00:00:00Z"}, SWEEP_JOB),
]
PAUSE_VAR = "vars.WING_COMMANDER_METRICS_PAUSED"


def suite(subject):
    broke = []

    if WATCHDOG_NAME in subject["workflows"]:
        broke.append(f"{WRAPPER} still lists {WATCHDOG_NAME!r} under "
                     f"workflow_run.workflows -- that reinstates one whole "
                     f"persistence run per inspection, and after FR-031 a "
                     f"healthy inspection has no record for it to find")
    if not subject["workflows"]:
        broke.append(f"{WRAPPER} lists no workflow_run workflows at all -- the "
                     f"per-completion path for the nine promptly-read stages "
                     f"is not supposed to go away with the watchdog's")

    crons = subject["schedule"]
    if len(crons) != 1:
        broke.append(f"the wrapper declares {len(crons)} cron entr(ies) "
                     f"({crons}); FR-030(c) is one daily sweep")
    else:
        mine = minute_hour(crons[0])
        for path, cron in other_crons():
            if minute_hour(cron) == mine:
                broke.append(f"the sweep's cron {crons[0]!r} shares its minute "
                             f"and hour with {path} ({cron!r}) -- two "
                             f"workflows asking for the same instant queue "
                             f"behind each other (research.md R-C6)")

    if subject["documented-workflows"] != subject["workflows"]:
        broke.append(f"{CONTRACT}'s published workflow_run list "
                     f"{subject['documented-workflows']} does not match the "
                     f"shipped one {subject['workflows']} -- an adopter forking "
                     f"this wrapper reads the document, not the file")
    if subject["documented-schedule"] != subject["schedule"]:
        broke.append(f"{CONTRACT} publishes cron {subject['documented-schedule']} "
                     f"and the wrapper ships {subject['schedule']}")

    if "since" not in subject["dispatch-inputs"]:
        broke.append("workflow_dispatch declares no `since` input -- the "
                     "hand-driven sweep re-drive has no way in")

    # The schedule has to start something. Evaluate the real job guards.
    for label, ctx, want in EVENTS:
        full = dict(ctx)
        full[PAUSE_VAR] = ""
        ran = []
        for job_id in (PERSIST_JOB, SWEEP_JOB):
            expr = str((subject["jobs"].get(job_id) or {}).get("if") or "")
            if not expr.strip():
                broke.append(f"job {job_id!r} has no `if:` -- it would run on "
                             f"every trigger this wrapper hears")
                continue
            try:
                if truthy(evaluate(expr, full)):
                    ran.append(job_id)
            except (ValueError, IndexError) as exc:
                broke.append(f"{label}: job {job_id!r}'s if: did not evaluate: {exc}")
        if ran != [want]:
            broke.append(f"{label}: job(s) {ran} run, expected exactly "
                         f"[{want!r}] -- a schedule reaching `persist` would "
                         f"persist run-id '', and a completion reaching "
                         f"`sweep` would sweep on every stage run")

    # The kill switch covers both jobs, including the one added here.
    for job_id in (PERSIST_JOB, SWEEP_JOB):
        expr = str((subject["jobs"].get(job_id) or {}).get("if") or "")
        if PAUSE_VAR not in expr:
            broke.append(f"job {job_id!r}'s `if:` does not read {PAUSE_VAR} -- "
                         f"the wrapper owns the pause switch (constitution VII) "
                         f"and a job it does not cover cannot be paused")
    return broke


# --------------------------------------------------------------------------
# Mutations
# --------------------------------------------------------------------------
def mut_watchdog_restored(subject):
    s = dict(subject)
    s["workflows"] = subject["workflows"] + [WATCHDOG_NAME]
    return s


def mut_cron_collides(subject):
    s = dict(subject)
    collide = other_crons()
    s["schedule"] = [collide[0][1]] if collide else ["43 5 * * *"]
    return s


def mut_schedule_reaches_persist(subject):
    s = dict(subject)
    jobs = {k: dict(v) for k, v in subject["jobs"].items()}
    jobs[PERSIST_JOB] = dict(jobs.get(PERSIST_JOB, {}),
                             **{"if": f"{PAUSE_VAR} != 'true'"})
    s["jobs"] = jobs
    return s


def mut_sweep_unpausable(subject):
    s = dict(subject)
    jobs = {k: dict(v) for k, v in subject["jobs"].items()}
    jobs[SWEEP_JOB] = dict(jobs.get(SWEEP_JOB, {}), **{
        "if": "github.event_name == 'schedule' || "
              "(github.event_name == 'workflow_dispatch' && inputs.since != '')"})
    s["jobs"] = jobs
    return s


def mut_contract_cron_drifts(subject):
    s = dict(subject)
    s["documented-schedule"] = ["5 5 * * *"]
    return s


MUTATIONS = [
    ("the watchdog is restored to the completion trigger", mut_watchdog_restored),
    ("the published contract's cron drifts from the shipped one",
     mut_contract_cron_drifts),
    ("the sweep's cron collides with another schedule", mut_cron_collides),
    ("the schedule also reaches the single-run job", mut_schedule_reaches_persist),
    ("the sweep job stops honouring the pause switch", mut_sweep_unpausable),
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
            print(f"::error::mutation {label!r} changed nothing -- the shape it "
                  f"targets has moved; update the mutation with it.")
            mutation_failures += 1
            continue
        if suite(mutated):
            print(f"Mutation OK - {label}.")
        else:
            print(f"::error::MUTATION SURVIVED - {label} broke nothing in this gate.")
            mutation_failures += 1
    print(f"Gate 79: {len(EVENTS)} trigger shape(s), "
          f"{len(other_crons())} other schedule(s), {len(MUTATIONS)} "
          f"mutation(s); {len(failures)} failure(s), "
          f"{mutation_failures} mutation failure(s).")
    return 1 if failures or mutation_failures else 0


if __name__ == "__main__":
    sys.exit(main())
