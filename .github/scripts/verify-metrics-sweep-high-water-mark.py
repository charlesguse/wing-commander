#!/usr/bin/env python3
"""Gate 77 -- the sweep's high-water mark advances with the records it
persisted, in the SAME commit, and the next window resumes from it
(FR-027, research.md R-C2/R-C3).

The mark is the only thing that makes a daily sweep bounded. Two ways it
can be wrong, and both look fine in a green run:

  * it advances in its own commit. A push is a contended write — the
    append loop retries up to eight times against a branch other writers
    are also pushing to. A mark committed separately can land while the
    records push is still losing that race, and the next sweep then
    resumes past runs nobody persisted. Those records are not late; they
    are gone, because the artifacts they came from expire.
  * it is read but never applied. The window still reaches back over
    everything, every sweep re-lists the whole retention period, and
    nothing fails — it just costs more every day, which is the shape this
    whole feature exists to stop.

So this gate drives BOTH shipped halves: the composite's four steps for
the write (wc_metrics_harness.run_sweep), including a fixture whose first
push is rejected by the destination repository's own `update` hook, so the
retry path is the one under test; and metrics-persist.yml's own window
step for the read, against a destination branch that does and does not
already carry a mark.

Four mutations -- the mark written in a second commit, the mark taken from
the first run rather than the latest, the one-hour overlap dropped, and the
mark read but ignored -- must each break an assertion.

Wiring: lint-workflows.yml, Gate 77.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_metrics_harness import (ACTION, APPEND, STAGE, STATE,  # noqa: E402
                                SWEEP_STEPS, WINDOW, cleanup, metrics_record,
                                run_sweep, run_window)
from wc_shell_harness import (find_step, resolve_bash,  # noqa: E402
                              use_utf8_stdout)

EARLY = "2026-09-20T01:00:00Z"
LATEST = "2026-09-20T03:00:00Z"
RUNS = [
    {"run_id": "6001", "workflow": "Wing Commander · 5 implement",
     "concluded_at": EARLY, "records": [metrics_record("6001", "implement")]},
    {"run_id": "6002", "workflow": "Wing Commander · 8 watchdog",
     "concluded_at": LATEST, "records": [metrics_record("6002", "diagnose")]},
]

# What the Actions API would stream back for the window step: one run that
# concluded well before the mark, one inside the fixed one-hour overlap
# (so it MUST be re-listed), and one after it.
MARK = "2026-09-20T12:00:00Z"
CANDIDATES = [
    {"run_id": "7001", "workflow": "old", "concluded_at": "2026-09-19T08:00:00Z"},
    {"run_id": "7002", "workflow": "in-overlap", "concluded_at": "2026-09-20T11:30:00Z"},
    {"run_id": "7003", "workflow": "after-mark", "concluded_at": "2026-09-20T18:00:00Z"},
]


def write_failures(bash, mutate=None):
    """The write half: the mark rides the records commit, through a retry."""
    broke = []
    # reject_pushes=1: the first push is refused, so what lands is what the
    # retry produced — which is the interesting case, not the happy one.
    work = tempfile.mkdtemp(prefix="wc-gate77-w-")
    try:
        state = run_sweep(work, RUNS, reject_pushes=1, bash=bash, mutate=mutate)
        if state["rc"] != 0:
            broke.append(f"the sweep failed after a rejected push: "
                         f"{state['steps'][-1][2].strip()[:300]}")
            return broke
        if state["sweep_state"] != {"high_water_mark": LATEST}:
            broke.append(f"sweep-state.json is {state['sweep_state']!r}; the "
                         f"mark must be the LATEST concluded run the sweep "
                         f"processed ({LATEST}), not the first or the oldest")
        sweep_commits = [c for c in state["commits"]
                         if STATE in c["files"] or "records.jsonl" in c["files"]]
        carrying_both = [c for c in sweep_commits
                         if STATE in c["files"] and "records.jsonl" in c["files"]]
        if not carrying_both:
            broke.append(
                f"no single commit carries both records.jsonl and {STATE}: "
                f"{[(c['subject'], c['files']) for c in sweep_commits]} -- a "
                f"mark that advances in its own commit can land while the "
                f"records push is still losing the contention race")
        if len(state["records"]) != len(RUNS):
            broke.append(f"the sweep persisted {len(state['records'])} record(s), "
                         f"expected {len(RUNS)} -- the retry must re-append the "
                         f"whole batch, not a remnant of it")
    finally:
        cleanup(work)
    return broke


def read_failures(bash, mutate=None):
    """The read half: the next window resumes from the mark, with overlap."""
    broke = []
    work = tempfile.mkdtemp(prefix="wc-gate77-r-")
    try:
        got = run_window(work, CANDIDATES, mark=MARK, bash=bash, mutate=mutate)
        if got["rc"] != 0:
            broke.append(f"the window step failed: {got['out'].strip()[:300]}")
            return broke
        if got["outputs"].get("since") != MARK:
            broke.append(f"the window resumed from "
                         f"{got['outputs'].get('since')!r}, not the mark "
                         f"{MARK!r} on the destination branch")
        ids = got["listed_ids"]
        if "7001" in ids:
            broke.append("a run that concluded a day before the mark was "
                         "re-listed -- the sweep would re-walk the whole "
                         "retention window every day")
        for rid, why in (("7002", "inside the fixed one-hour overlap"),
                         ("7003", "after the mark")):
            if rid not in ids:
                broke.append(f"run {rid}, {why}, was not listed: {ids}")
    finally:
        cleanup(work)

    # No mark yet: a bounded bootstrap, not the repository's whole history.
    work = tempfile.mkdtemp(prefix="wc-gate77-b-")
    try:
        got = run_window(work, CANDIDATES, mark=None, bash=bash, mutate=mutate)
        if got["rc"] != 0:
            broke.append(f"the window step failed with no mark present: "
                         f"{got['out'].strip()[:300]}")
        elif not got["outputs"].get("since"):
            broke.append("with no sweep-state.json the step produced no window "
                         "at all -- the first sweep on a fresh destination "
                         "branch would collect nothing, forever")
    finally:
        cleanup(work)
    return broke


# MF-02(a)/(b): a run whose OWN `if:` skipped it, and a run outside the
# wrapper-supplied workflow-path allowlist, must never reach the
# composite -- each would otherwise cost two API calls (jobs + artifacts)
# confirming what this step already knew.
FILTER_CANDIDATES = [
    {"run_id": "7101", "workflow": ".github/workflows/wing-commander-1-intake.yml",
     "concluded_at": "2026-09-20T18:00:00Z", "conclusion": "success"},
    {"run_id": "7102", "workflow": ".github/workflows/wing-commander-2-clarify.yml",
     "concluded_at": "2026-09-20T18:05:00Z", "conclusion": "skipped"},
    {"run_id": "7103", "workflow": ".github/workflows/wing-commander-e2e-reference-image.yml",
     "concluded_at": "2026-09-20T18:10:00Z", "conclusion": "success"},
]
FILTER_ALLOWED = [".github/workflows/wing-commander-1-intake.yml",
                  ".github/workflows/wing-commander-2-clarify.yml"]


def filter_failures(bash, mutate=None):
    """MF-02: a skipped run and a run outside the allowlist never reach
    sweep-runs, regardless of concluding inside the window."""
    broke = []
    work = tempfile.mkdtemp(prefix="wc-gate77-f-")
    try:
        got = run_window(work, FILTER_CANDIDATES, mark=EARLY,
                         workflow_paths=FILTER_ALLOWED, bash=bash, mutate=mutate)
        if got["rc"] != 0:
            broke.append(f"the window step failed on the filter fixture: "
                         f"{got['out'].strip()[:300]}")
            return broke
        ids = got["listed_ids"]
        if "7101" not in ids:
            broke.append(f"7101 (allowed workflow, not skipped) was dropped: {ids}")
        if "7102" in ids:
            broke.append(f"7102 (conclusion=skipped) reached sweep-runs: {ids} -- "
                         f"MF-02(a): a skipped run carries no metrics-record "
                         f"artifact and never will")
        if "7103" in ids:
            broke.append(f"7103 (outside the workflow-path allowlist) reached "
                         f"sweep-runs: {ids} -- MF-02(b): the caller's allowlist "
                         f"must actually restrict discovery")
    finally:
        cleanup(work)
    return broke


def suite(bash, mutate=None):
    return write_failures(bash, mutate) + read_failures(bash, mutate) + filter_failures(bash, mutate)


# --------------------------------------------------------------------------
# Mutations
# --------------------------------------------------------------------------
def mut_mark_committed_separately(name, script):
    if name != APPEND:
        return script
    # Stage the mark, then commit it on its own before the records commit.
    return script.replace(
        "git add sweep-state.json\n",
        "git add sweep-state.json\n"
        "            git commit -m 'metrics: advance the sweep mark' "
        "--allow-empty >/dev/null\n")


def mut_mark_taken_from_the_first_run(name, script):
    if name != APPEND:
        return script
    return script.replace(
        "[.[] | select((.run_id|tostring) as $rid | ($hb | index($rid)) == null) | .concluded_at] | max // empty",
        "[.[] | select((.run_id|tostring) as $rid | ($hb | index($rid)) == null) | .concluded_at] | first // empty")


def mut_overlap_dropped(name, script):
    if name != WINDOW:
        return script
    # MF-09: window_start is jq-derived, not `date -d`, so the overlap this
    # mutation drops is the `- 3600` (one hour, in seconds) term.
    return script.replace("(($s | fromdate) - 3600) | todate",
                          "($s | fromdate) | todate")


def mut_mark_ignored(name, script):
    if name != WINDOW:
        return script
    return script.replace("jq -r '.high_water_mark // empty'", "jq -r 'empty'")


def mut_skipped_conclusion_not_dropped(name, script):
    if name != WINDOW:
        return script
    return script.replace(' | select(.conclusion != "skipped")', "")


def mut_workflow_allowlist_not_applied(name, script):
    if name != WINDOW:
        return script
    return script.replace(
        ' | select(($wf | length) == 0 or ((.workflow as $cw | $wf | index($cw)) != null))', "")


MUTATIONS = [
    ("the mark advances in its own commit", mut_mark_committed_separately),
    ("the mark is taken from the first run, not the latest",
     mut_mark_taken_from_the_first_run),
    ("the fixed one-hour overlap is dropped", mut_overlap_dropped),
    ("the durable mark is read and then ignored", mut_mark_ignored),
    ("a skipped run is not dropped before the composite (MF-02(a))",
     mut_skipped_conclusion_not_dropped),
    ("the caller's workflow-path allowlist is not applied (MF-02(b))",
     mut_workflow_allowlist_not_applied),
]


def mutation_applies(mutate):
    for name, path in [(n, ACTION) for n in SWEEP_STEPS] + [(WINDOW, STAGE)]:
        original = find_step(path, name)["run"]
        if mutate(name, original) != original:
            return True
    return False


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
    print(f"Gate 77: 1 contended sweep + 3 window shape(s), "
          f"{len(MUTATIONS)} mutation(s); {len(failures)} failure(s), "
          f"{mutation_failures} mutation failure(s).")
    return 1 if failures or mutation_failures else 0


if __name__ == "__main__":
    sys.exit(main())
