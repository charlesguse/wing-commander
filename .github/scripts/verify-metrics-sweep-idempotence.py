#!/usr/bin/env python3
"""Gate 76 -- a sweep persists each run exactly once, and re-sweeping the
same window adds nothing (FR-022, FR-027).

Spec 058 gives metrics persistence a second way in. The nine
promptly-read stages still persist per completion; the daily sweep picks
up whatever that trigger did not. The two overlap by design -- the sweep's
window deliberately reaches back over runs the completion trigger already
persisted (research.md R-C3's fixed one-hour overlap), and a hand-driven
re-drive can run while a sweep is in flight (FR-024) -- so "each record
lands exactly once" now rests entirely on record_key idempotence in the
append step, under inputs that never occurred before this feature.

That is a claim about shipped shell, so this gate runs the shipped shell:
the real discover/retrieve/validate/append steps of
wing-commander-metrics-persist/action.yml, in sweep mode, against a local
git remote and a `gh` stub (wc_metrics_harness). Two sweeps, over:

  * a run already persisted by the completion trigger, and
  * a run reachable only by the sweep;

asserting after the first sweep that each record_key appears exactly once
in records.jsonl, and after the second (identical window) that the file is
byte-for-byte unchanged and no new records commit was made.

Two mutations -- the append step's existing-key skip removed, and the
sweep's per-run loop collapsed to the first run -- must each break an
assertion.

Wiring: lint-workflows.yml, Gate 76.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_metrics_harness import (ACTION, APPEND, DISCOVER,  # noqa: E402
                                SWEEP_STEPS, cleanup, metrics_record,
                                persisted_record, record_keys, record_line,
                                resolved_key, resweep, run_sweep)
from wc_shell_harness import (find_step, resolve_bash,  # noqa: E402
                              use_utf8_stdout)


def mutation_applies(mutate):
    """A mutation that matched nothing proves nothing — the shipped line it
    targets has moved, and the gate must say so rather than score the
    no-op as a surviving mutant."""
    return any(mutate(n, find_step(ACTION, n)["run"]) != find_step(ACTION, n)["run"]
               for n in SWEEP_STEPS)

# 5001 was persisted the moment it concluded; 5002's stage is not on the
# completion trigger any more, so only the sweep will ever see it.
ALREADY = metrics_record("5001", "implement")
ONLY_SWEEP = metrics_record("5002", "diagnose")

RUNS = [
    {"run_id": "5001", "workflow": "Wing Commander · 5 implement",
     "concluded_at": "2026-09-20T01:00:00Z", "records": [ALREADY]},
    {"run_id": "5002", "workflow": "Wing Commander · 8 watchdog",
     "concluded_at": "2026-09-20T03:00:00Z", "records": [ONLY_SWEEP]},
]
WANT_KEYS = sorted([resolved_key("5001"), resolved_key("5002")])
# What the completion trigger already wrote for 5001: the same record, with
# its job id resolved, exactly as it sits in records.jsonl today.
SEED = record_line(persisted_record("5001", "implement"))


def records_commits(state):
    return [c for c in state["commits"] if "records.jsonl" in c["files"]]


def suite(bash, mutate=None):
    """Every broken assertion, as a message. Empty = idempotence holds."""
    broke = []
    work = tempfile.mkdtemp(prefix="wc-gate76-")
    try:
        first = run_sweep(work, RUNS, seed_records=SEED,
                          bash=bash, mutate=mutate)
        if first["rc"] != 0:
            broke.append(f"the first sweep failed: "
                         f"{[(n, rc) for n, rc, _o in first['steps']]} -- "
                         f"{first['steps'][-1][2].strip()[:300]}")
            return broke
        keys = record_keys(first["records"])
        if sorted(keys) != WANT_KEYS:
            broke.append(f"after one sweep records.jsonl holds {keys}, expected "
                         f"{WANT_KEYS} -- each run exactly once, the one the "
                         f"completion trigger already persisted included")
        after_first = list(first["records"])
        n_commits = len(records_commits(first))

        second = resweep(work, first, RUNS, bash=bash, mutate=mutate)
        if second["rc"] != 0:
            broke.append(f"the second sweep failed: "
                         f"{second['steps'][-1][2].strip()[:300]}")
            return broke
        if second["records"] != after_first:
            broke.append(f"re-sweeping the same window changed records.jsonl: "
                         f"{record_keys(after_first)} -> "
                         f"{record_keys(second['records'])}")
        if len(records_commits(second)) != n_commits:
            broke.append(f"re-sweeping the same window added "
                         f"{len(records_commits(second)) - n_commits} more "
                         f"records commit(s); an idempotent repeat writes none")
    finally:
        cleanup(work)
    return broke


# --------------------------------------------------------------------------
# Mutations
# --------------------------------------------------------------------------
def mut_append_forgets_existing_keys(name, script):
    if name != APPEND:
        return script
    return script.replace(
        'if [ -n "$key" ] && grep -qxF "$key" "$existing_keys" 2>/dev/null; then',
        'if [ -n "$key" ] && false; then')


def mut_discover_only_takes_the_first_run(name, script):
    if name != DISCOVER:
        return script
    return script.replace("jq -r '.[].run_id'", "jq -r '.[0].run_id'")


MUTATIONS = [
    ("the append step stops skipping already-persisted keys",
     mut_append_forgets_existing_keys),
    ("discovery only covers the sweep's first run",
     mut_discover_only_takes_the_first_run),
]


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
    print(f"Gate 76: 2 sweep pass(es) over {len(RUNS)} run(s), "
          f"{len(MUTATIONS)} mutation(s); {len(failures)} failure(s), "
          f"{mutation_failures} mutation failure(s).")
    return 1 if failures or mutation_failures else 0


if __name__ == "__main__":
    sys.exit(main())
