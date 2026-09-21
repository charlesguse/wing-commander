#!/usr/bin/env python3
"""Gate 78 -- a run whose metrics artifact expired before the sweep reached
it is recorded once, accounted for, and never chased again (FR-028).

The sweep trades latency for cost: a signal-bearing watchdog inspection is
collected the next morning rather than seconds after it concludes. That is
safe only while artifacts outlive the gap — and sometimes one will not
(retention lapses, an artifact deleted by hand, a run purged). The wrong
outcomes are both quiet:

  * retry it forever. The high-water mark cannot advance past a run the
    sweep refuses to finish with, so every subsequent sweep re-lists it,
    re-fails, and drags the window back over everything after it.
  * drop it silently. The spend history acquires a hole with nothing
    saying why, and the rollup's "$X across N agent run(s)" quietly
    under-counts with no way to tell that from a quiet week.

FR-028's answer is a durable ledger line — one per lost run, naming it and
the reason — with the mark advancing past it regardless. This gate drives
the shipped discover/retrieve/validate/append steps against a fixture
where one of two discovered runs lists its artifact but cannot serve it
(exactly what `gh run download` does against an expired one), then
re-sweeps the same window and asserts the ledger did not grow.

Three mutations -- the ledger line not written, the mark held back to the
last successfully retrieved run, and the ledger appended without the
per-run dedup -- must each break an assertion.

Wiring: lint-workflows.yml, Gate 78.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_metrics_harness import (ACTION, APPEND, RETRIEVE,  # noqa: E402
                                SWEEP_STEPS, cleanup, metrics_record,
                                record_keys, resolved_key, resweep, run_sweep)
from wc_shell_harness import (find_step, resolve_bash,  # noqa: E402
                              use_utf8_stdout)

GONE_ID = "8001"
GONE_WORKFLOW = "Wing Commander · 8 watchdog"
LATEST = "2026-09-20T05:00:00Z"

RUNS = [
    # Discovered (its artifact is listed) but not retrievable: the artifact
    # expired between the run concluding and the sweep reaching it.
    {"run_id": GONE_ID, "workflow": GONE_WORKFLOW,
     "concluded_at": "2026-09-20T02:00:00Z", "expired": True,
     "records": [metrics_record(GONE_ID, "diagnose")]},
    {"run_id": "8002", "workflow": "Wing Commander · 5 implement",
     "concluded_at": LATEST, "records": [metrics_record("8002", "implement")]},
]


def suite(bash, mutate=None):
    broke = []
    work = tempfile.mkdtemp(prefix="wc-gate78-")
    try:
        first = run_sweep(work, RUNS, bash=bash, mutate=mutate)
        if first["rc"] != 0:
            broke.append(f"a sweep containing an expired artifact failed "
                         f"outright: {first['steps'][-1][2].strip()[:300]} -- "
                         f"one lost run must not fail the whole sweep")
            return broke

        # The run that survived is persisted; the one that did not is not
        # invented from thin air.
        keys = record_keys(first["records"])
        if keys != [resolved_key("8002")]:
            broke.append(f"records.jsonl holds {keys}; only the retrievable "
                         f"run's record can be there")

        ledger = first["unpersisted"]
        matching = [ln for ln in ledger if ln.get("run_id") == GONE_ID]
        if len(matching) != 1:
            broke.append(f"the ledger holds {len(matching)} line(s) for run "
                         f"{GONE_ID}, expected exactly 1: {ledger}")
        else:
            line = matching[0]
            if line.get("reason") != "artifact_expired":
                broke.append(f"the ledger line's reason is "
                             f"{line.get('reason')!r}, not 'artifact_expired'")
            if line.get("workflow") != GONE_WORKFLOW:
                broke.append(f"the ledger line does not name the workflow "
                             f"({line.get('workflow')!r}) -- a bare run id is "
                             f"unreadable once the run itself is gone")
            if not line.get("discovered_at"):
                broke.append("the ledger line carries no discovered_at")
        if len(ledger) != 1:
            broke.append(f"the ledger holds {len(ledger)} line(s); only the "
                         f"unretrievable run belongs in it: {ledger}")

        if first["sweep_state"] != {"high_water_mark": LATEST}:
            broke.append(f"the mark is {first['sweep_state']!r}, not {LATEST!r} "
                         f"-- it must advance PAST the lost run, which is "
                         f"accounted for rather than retried")

        second = resweep(work, first, RUNS, bash=bash, mutate=mutate)
        if second["rc"] != 0:
            broke.append(f"the second sweep failed: "
                         f"{second['steps'][-1][2].strip()[:300]}")
        elif second["unpersisted"] != ledger:
            broke.append(f"re-sweeping re-logged the lost run: {ledger} -> "
                         f"{second['unpersisted']}")
    finally:
        cleanup(work)
    return broke


# --------------------------------------------------------------------------
# Mutations
# --------------------------------------------------------------------------
def mut_no_ledger_line(name, script):
    if name != RETRIEVE:
        return script
    return script.replace('>> "$base/unpersisted.jsonl"',
                          '>> /dev/null')


def mut_mark_held_back_to_the_last_retrieved(name, script):
    if name != APPEND:
        return script
    # The mark stops at the newest run that actually yielded a record, so
    # the lost one is re-listed by every subsequent sweep.
    return script.replace("[.[].concluded_at] | max // empty",
                          "[.[].concluded_at] | min // empty")


def mut_ledger_dedup_dropped(name, script):
    if name != APPEND:
        return script
    return script.replace(
        'if [ -n "$urid" ] && grep -qF "\\"run_id\\":\\"$urid\\"" unpersisted.jsonl 2>/dev/null; then',
        'if [ -n "$urid" ] && false; then')


MUTATIONS = [
    ("a lost run leaves no ledger line", mut_no_ledger_line),
    ("the mark is held back to the last retrieved run",
     mut_mark_held_back_to_the_last_retrieved),
    ("the ledger is appended without its per-run dedup",
     mut_ledger_dedup_dropped),
]


def mutation_applies(mutate):
    return any(mutate(n, find_step(ACTION, n)["run"]) != find_step(ACTION, n)["run"]
               for n in SWEEP_STEPS)


def main():
    use_utf8_stdout()
    bash = resolve_bash()
    failures = suite(bash)
    for f in failures:
        print(f"::error::{f}")
    mutation_failures = 0
    for label, mutate in MUTATIONS:
        if not mutation_applies(mutate):
            print(f"::error::mutation {label!r} changed nothing -- the shipped "
                  f"line it targets has moved; update the mutation with it.")
            mutation_failures += 1
            continue
        if suite(bash, mutate=mutate):
            print(f"Mutation OK - {label}.")
        else:
            print(f"::error::MUTATION SURVIVED - {label} broke nothing in this gate.")
            mutation_failures += 1
    print(f"Gate 78: 2 sweep pass(es) over {len(RUNS)} run(s), one of them "
          f"unretrievable, {len(MUTATIONS)} mutation(s); {len(failures)} "
          f"failure(s), {mutation_failures} mutation failure(s).")
    return 1 if failures or mutation_failures else 0


if __name__ == "__main__":
    sys.exit(main())
