#!/usr/bin/env python3
"""Gate 74 -- a healthy watchdog inspection emits no metrics record, and the
cumulative rollup does not list it AT ALL (FR-031).

Spec 043 made every agent run durable: the run uploads a `metrics-record*`
artifact, metrics-persist appends it to records.jsonl, and the lifecycle
rollup comment says "$X across N agent run(s)" with a per-run history line
for each. Spec 058's clean path runs no agent, so there is nothing to
record -- and the failure mode that matters is not "the record is missing"
but "the rollup says a record existed and could not be retrieved". A run
listed as unretrievable is indistinguishable, to a reader, from spec 043's
real failure (an artifact that expired before persistence reached it), and
it would put a permanent unexplained hole in the spend history of every
healthy inspection.

So this gate asserts both halves:

  1. Nothing uploads a `metrics-record*` artifact on the clean path. Every
     such upload in watchdog.yml must live in `diagnose`, and `diagnose`'s
     SHIPPED `if:` must evaluate false on the full-pass and partial-pass
     fixtures -- plus, for the signal-bearing path where the job does run,
     the upload step's own guard must still decline when the agent step was
     skipped.
  2. The rollup genuinely omits it. This runs the SHIPPED "Update cumulative
     rollup" block from wing-commander-metrics-persist/action.yml over a
     record set holding two OTHER runs and no watchdog inspection, and
     asserts the region names those two (the positive control -- an absence
     proves nothing if the builder never ran) and says nothing whatsoever
     about the inspection: not a history line, not an inflated run count,
     not an "incomplete/unavailable" row.

Three mutations (diagnose stops keying on the signal set, the upload's
agent-skipped guard dropped, a record upload added to `collect`) must each
break an assertion.

Wiring: lint-workflows.yml, Gate 74.
"""
import os
import shutil
import stat
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_gha_expr import evaluate, truthy  # noqa: E402
from wc_shell_harness import (ensure_jq, find_step, resolve_bash,  # noqa: E402
                              run_step, use_utf8_stdout)

import yaml  # noqa: E402

WF = os.path.join(".github", "workflows", "watchdog.yml")
ACTION = os.path.join(".github", "actions", "wing-commander-metrics-persist",
                      "action.yml")
ROLLUP_STEP = "Update cumulative rollup"
RECORD_ARTIFACT_PREFIX = "metrics-record"
DIAGNOSE_JOB = "diagnose"

SPEC_DIR = "specs/058-per-job-minute-floor"
# The inspection that emitted nothing. Its record key is what must be absent.
ABSENT_KEY = "9001:diagnose:0"
PRESENT_KEYS = ("1000:implement:0", "1001:clarify:0")

GH_STUB = """#!/usr/bin/env bash
# No prior rollup comment: the shipped step's lookup returns an empty object
# and it POSTs. Every call is recorded; none of it matters to this gate,
# which reads the region file the step writes.
printf '%s\\n' "$*" >> "$WC_GH_LOG"
[ "${1:-}" = "api" ] && echo '{}'
exit 0
"""


def record(key, stage):
    return (
        '{"schema_version":1,"spec":{"spec_dir":"%s","issue":434,'
        '"identity_available":true},"stage":"%s","cost_available":true,'
        '"cost_usd":0.5,"turns":{"available":true,"counted":6},'
        '"tokens":{"available":true,"input":100,"output":200},'
        '"model":"claude-sonnet-5","run":{"record_key":"%s"},'
        '"emitted_at":"2026-01-01T00:00:00Z"}' % (SPEC_DIR, stage, key))


RECORDS = "\n".join(record(k, s) for k, s in
                    zip(PRESENT_KEYS, ("implement", "clarify"))) + "\n"


# --------------------------------------------------------------------------
# Half 1: nothing uploads a record on the clean path
# --------------------------------------------------------------------------
def record_uploads(jobs):
    """(job_id, step_name, step_if) for every metrics-record* upload."""
    found = []
    for job_id, job in jobs.items():
        for step in (job or {}).get("steps") or []:
            name = str(((step or {}).get("with") or {}).get("name") or "")
            if name.startswith(RECORD_ARTIFACT_PREFIX):
                found.append((job_id, str(step.get("name") or "?"),
                              str(step.get("if") or "")))
    return found


# (label, diagnose-job context, agent-step outcome, record expected?)
FIXTURES = [
    ("full pass (no signal, no failed collector)",
     {"needs.collect.result": "success",
      "needs.collect.outputs.evidence-available": "true",
      "needs.collect.outputs.signals": "[]"}, None, False),
    ("partial pass (no signal, some collectors failed)",
     {"needs.collect.result": "success",
      "needs.collect.outputs.evidence-available": "true",
      "needs.collect.outputs.signals": "[]"}, None, False),
    # diagnose DOES run here, so the upload step's own guard is what decides.
    ("signal-bearing run whose agent step was skipped",
     {"needs.collect.result": "success",
      "needs.collect.outputs.evidence-available": "true",
      "needs.collect.outputs.signals": '[{"id":"a1b2c3d4"}]'}, "skipped", False),
    ("signal-bearing run whose agent step ran (spec 043, unchanged)",
     {"needs.collect.result": "success",
      "needs.collect.outputs.evidence-available": "true",
      "needs.collect.outputs.signals": '[{"id":"a1b2c3d4"}]'}, "success", True),
]


def load_subject():
    wf = yaml.safe_load(open(WF, encoding="utf-8")) or {}
    jobs = wf.get("jobs") or {}
    subject = {"jobs": jobs,
               "diagnose:if": str((jobs.get(DIAGNOSE_JOB) or {}).get("if") or ""),
               "uploads": record_uploads(jobs)}
    if not subject["uploads"]:
        sys.exit(f"::error file={WF}::no `{RECORD_ARTIFACT_PREFIX}*` artifact "
                 f"upload found at all. Spec 043's durable record is supposed "
                 f"to exist on the signal-bearing path -- this gate cannot "
                 f"prove its absence on the clean path if it is absent "
                 f"everywhere.")
    if not subject["diagnose:if"].strip():
        sys.exit(f"::error file={WF}::the {DIAGNOSE_JOB!r} job has no `if:` -- "
                 f"nothing to evaluate.")
    return subject


def emission_failures(subject):
    broke = []
    off_diagnose = sorted({j for j, _n, _i in subject["uploads"]} - {DIAGNOSE_JOB})
    if off_diagnose:
        broke.append(f"a `{RECORD_ARTIFACT_PREFIX}*` artifact is uploaded from "
                     f"job(s) {off_diagnose} as well as {DIAGNOSE_JOB!r}; a job "
                     f"that still runs on the clean path would emit a record "
                     f"for an inspection that invoked no agent (FR-031)")
    for label, needs, agent_outcome, want in FIXTURES:
        jctx = {"cancelled()": False, "always()": True,
                "needs.verify-image-prerequisites.result": "skipped"}
        jctx.update(needs)
        try:
            job_runs = truthy(evaluate(subject["diagnose:if"], jctx))
        except (ValueError, IndexError) as exc:
            broke.append(f"{label}: diagnose's if: did not evaluate: {exc}")
            continue
        for job_id, step_name, step_if in subject["uploads"]:
            if job_id != DIAGNOSE_JOB:
                continue          # already reported above
            emitted = job_runs
            if emitted and step_if.strip():
                sctx = {"always()": True, "cancelled()": False,
                        "steps.diagnose.outcome": agent_outcome or ""}
                try:
                    emitted = truthy(evaluate(step_if, sctx))
                except (ValueError, IndexError) as exc:
                    broke.append(f"{label}: {step_name!r}'s if: did not "
                                 f"evaluate: {exc}")
                    continue
            if emitted != want:
                broke.append(f"{label}: {step_name!r} emits={emitted}, "
                             f"expected {want}")
    return broke


# --------------------------------------------------------------------------
# Half 2: the rollup does not list the inspection, in any form
# --------------------------------------------------------------------------
def _write_exec(path, content):
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(content)
    os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def rollup_failures(bash, script):
    broke = []
    tmp = tempfile.mkdtemp(prefix="wc-gate74-")
    try:
        stub_dir = os.path.join(tmp, "stubbin")
        os.makedirs(stub_dir)
        _write_exec(os.path.join(stub_dir, "gh"), GH_STUB)
        os.makedirs(os.path.join(tmp, "wc-metrics-persist"))
        with open(os.path.join(tmp, "records.jsonl"), "w", encoding="utf-8") as fh:
            fh.write(RECORDS)
        env = {"DEST_PATH": "records.jsonl", "BRANCH": "metrics",
               "SPEC_DIRS": SPEC_DIR, "GITHUB_REPOSITORY": "acme/wing-commander",
               "GH_TOKEN": "stub-token", "WC_GH_LOG": os.path.join(tmp, "gh.log"),
               "PATH": stub_dir + os.pathsep + os.environ.get("PATH", "")}
        rc, out, _outputs, _summary = run_step(bash, script, tmp, env, tmp)
        region_path = os.path.join(tmp, "wc-metrics-persist", "rollup-region.md")
        if rc != 0 or not os.path.exists(region_path):
            broke.append(f"the shipped rollup step exited {rc} and wrote "
                         f"{'no' if not os.path.exists(region_path) else 'a'} "
                         f"region: {out.strip()[:300]}")
            return broke
        with open(region_path, encoding="utf-8") as fh:
            region = fh.read()
        # Positive control first: an absence proves nothing if the builder
        # produced an empty region.
        for key in PRESENT_KEYS:
            if key not in region:
                broke.append(f"the rollup region omits {key!r}, a run that DID "
                             f"emit a record -- this gate's absence assertions "
                             f"below would be vacuous")
        if f"across {len(PRESENT_KEYS)} agent run(s)" not in region:
            broke.append(f"the rollup region does not count exactly "
                         f"{len(PRESENT_KEYS)} agent run(s): {region!r}")
        if ABSENT_KEY in region:
            broke.append(f"the rollup region lists {ABSENT_KEY!r} -- a healthy "
                         f"inspection that ran no agent must not appear at all")
        for phrase in ("Incomplete:", "unavailable"):
            if phrase in region:
                broke.append(f"the rollup region carries {phrase!r} over a "
                             f"record set with no missing metrics -- a healthy "
                             f"inspection must never read as a record that "
                             f"existed and could not be retrieved (FR-031)")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return broke


# --------------------------------------------------------------------------
# Mutations
# --------------------------------------------------------------------------
def mut_diagnose_ignores_signals(subject):
    s = dict(subject)
    s["diagnose:if"] = (subject["diagnose:if"]
                        .replace(" && needs.collect.outputs.signals != ''", "")
                        .replace(" && needs.collect.outputs.signals != '[]'", ""))
    return s


def mut_upload_ignores_skipped_agent(subject):
    s = dict(subject)
    s["uploads"] = [(j, n, i.replace(" && steps.diagnose.outcome != 'skipped'", ""))
                    for j, n, i in subject["uploads"]]
    return s


def mut_collect_uploads_a_record(subject):
    s = dict(subject)
    s["uploads"] = subject["uploads"] + [
        ("collect", "Upload metrics record (injected by this gate's mutation)",
         "always()")]
    return s


MUTATIONS = [
    ("diagnose stops keying on the signal set", mut_diagnose_ignores_signals),
    ("the record upload stops declining a skipped agent step",
     mut_upload_ignores_skipped_agent),
    ("a record upload is added to collect", mut_collect_uploads_a_record),
]


def main():
    use_utf8_stdout()
    ensure_jq()
    bash = resolve_bash()
    script = find_step(ACTION, ROLLUP_STEP)["run"]
    subject = load_subject()

    failures = emission_failures(subject) + rollup_failures(bash, script)
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
        if emission_failures(mutated):
            print(f"Mutation OK - {label}.")
        else:
            print(f"::error::MUTATION SURVIVED - {label} broke nothing in this gate.")
            mutation_failures += 1

    print(f"Gate 74: {len(FIXTURES)} inspection shape(s) + 1 rollup region, "
          f"{len(MUTATIONS)} mutation(s); {len(failures)} failure(s), "
          f"{mutation_failures} mutation failure(s).")
    return 1 if failures or mutation_failures else 0


if __name__ == "__main__":
    sys.exit(main())
