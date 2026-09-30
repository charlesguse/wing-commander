#!/usr/bin/env python3
"""Gate 33 — a stage that dies at entry reaches the chain-stop notice, and
nothing else does.

Called "Gate 28" throughout specs/041-implement-stall-notice's plan/tasks/
data-model docs, written against a base state where that number was free.
By the time this merged, Gate 28 already named the gh-api-explicit-method
check and 29-32 were taken by #243/#235/#244 and PR #240's act-dedup gate,
so this is 33 — the next free number, same script, same contract.

WHY THIS EXISTS
----------------
This whole feature (specs/041-implement-stall-notice) exists because
`implement.yml`'s `stalled` job's condition, `needs.implement.outputs.
final-ok == 'false'`, carried no status-check function — so GitHub's
implicit `success()` over the needs-closure suppressed it before that arm
was ever read, for every cause except the one the condition's own text
named. Gate 15 (amended alongside this gate) proves the CONDITION'S SHAPE is
readable; it does not prove the condition actually admits the failure
shapes it claims to. Only evaluating the shipped `if:` against modelled
`needs.*` values proves that — which is what this gate does, for exactly
the seven survivor-job call sites this feature ships (data-model.md's
condition table).

WHAT THIS CHECKS
----------------
1. Extracts each of the seven survivor-job `if:` strings directly from the
   shipped workflow YAML (`wc_shell_harness.find_job`).
2. Evaluates each against a fixture table of modelled `needs.*` result/
   output combinations (contracts/chain-stop-gate-coverage.md), asserting
   the boolean matches the intended reachability: fires on dependency
   failure, entry-job failure/skip, and (implement only) the exhausted-
   retry flag; stays silent on a healthy run, a cancelled run, and a
   refusal-flagged failure.
3. Applies the four required mutations (data-model.md's mutation table) to
   a COPY of each extracted condition and re-runs step 2, asserting at
   least one row now disagrees for every mutation (FR-013) — the same
   `if mutated == original` guard `verify-stall-restart-runbook.py`
   establishes, so a mutation that silently failed to apply cannot produce
   a false pass.
4. Rejects a dead `needs.<job>.result == 'failure'` arm nested under a
   top-level `needs.<job>.result != 'failure'` guard on the same job, in
   every survivor job (the seven above plus pr-conversation's
   `stalled-mark`). The guard makes such an arm unreachable, so step 2's
   evaluation cannot see it; it only reads like a live admission path, and
   the image-prerequisite copy of it is what produced #728's
   false-contradiction report (spec 041 D11 excludes that case). A
   mutation re-adds the image arm to each job and asserts this check
   flags every one.

The extraction/evaluator/fixture-table machinery is shared with the
refusal-exclusion check (User Story 3) via `wc_chain_stop_conditions.py`,
so the two cannot silently drift apart on what a "survivor-job condition"
even means.

Usage: python3 .github/scripts/verify-chain-stop-notice.py
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_shell_harness import use_utf8_stdout
from wc_chain_stop_conditions import (CALL_SITES, dead_failure_arms,
                                      extract_condition, run_suite)
from wc_shell_harness import find_job


def _mut_remove_status_guard(cond):
    """Strip !cancelled() — the condition is provably suppressed on a
    cancelled run, the exact defect this feature closes."""
    return cond.replace("!cancelled() &&", "").replace("!cancelled() && ", "")


def _mut_narrow_drop_failure_arm(cond):
    """Drop the entry-job-itself-failed arm, keeping only 'skipped'.

    Identifies the ENTRY job by its 'skipped' arm — only the entry job's own
    result is ever compared against 'skipped' in these conditions — so this
    only ever touches the entry job's own failure arm, never an upstream
    one (which would also break the upstream-dependency row and understate
    what this mutation proves).
    """
    m = re.search(r"needs\.([A-Za-z0-9_-]+)\.result == 'skipped'", cond)
    if not m:
        return cond
    entry = re.escape(m.group(1))
    # Flexible whitespace: the block scalar's stripped indentation differs
    # by call site (implement.yml's base indent is not clarify.yml's), so a
    # literal "\n        " would silently no-op on some files and only ever
    # get exercised by whichever site happened to match.
    pat = re.compile(rf"needs\.{entry}\.result == 'failure' \|\|\s*")
    return pat.sub("", cond, count=1)


def _mut_widen_admit_success(cond):
    """Widen to also fire on the entry job's own success — the healthy-run
    and refusal rows would now wrongly reach the notice."""
    m = re.search(r"needs\.([A-Za-z0-9_-]+)\.result == 'skipped'", cond)
    if not m:
        return cond
    entry = m.group(1)
    return cond.replace(f"needs.{entry}.result == 'skipped'",
                        f"needs.{entry}.result == 'skipped' || "
                        f"needs.{entry}.result == 'success'")


def _mut_bespoke_condition(cond):
    """Point the call site at a condition that does not match the shared
    shape at all — always true, i.e. `always()`."""
    return "always()"


def _mut_remove_image_prereq_guard(cond):
    """Strip the `needs.verify-image-prerequisites.result != 'failure' &&`
    leading conjunct (spec 058 narrowed this from `== 'success'`, since the
    check job now legitimately reports `skipped` too) — the notice would
    fire from inside the adopter's own already-failed container again
    (Gate 23)."""
    pat = re.compile(
        r"needs\.verify-image-prerequisites\.result != 'failure' &&\s*")
    return pat.sub("", cond, count=1)


MUTATIONS = [
    ("remove the !cancelled() status-check guard", _mut_remove_status_guard),
    ("narrow: drop the entry-job-itself-failed arm", _mut_narrow_drop_failure_arm),
    ("widen: also fire on the entry job's own success", _mut_widen_admit_success),
    ("bespoke: not the shared shape at all (always())", _mut_bespoke_condition),
    ("remove the verify-image-prerequisites success guard",
     _mut_remove_image_prereq_guard),
]


# Every survivor job whose `if:` step 4 scans: the evaluated call sites plus
# pr-conversation's `stalled-mark`, whose `if:` is kept in lockstep with
# `stalled` (specs/077-stalled-per-spec-group data-model.md).
DEAD_ARM_SITES = [(site["file"], site["job_id"]) for site in CALL_SITES] + [
    (".github/workflows/pr-conversation.yml", "stalled-mark"),
]

_GROUP_OPEN_RE = re.compile(r"\(\s*needs\.")


def _mut_reintroduce_dead_image_arm(cond):
    """Re-add #728's dead arm as the first arm of the parenthesized group."""
    return _GROUP_OPEN_RE.sub(
        "( needs.verify-image-prerequisites.result == 'failure' ||\n  needs.",
        cond, count=1)


def check_dead_arms():
    failures = []
    mutation_misses = []
    for path, job_id in DEAD_ARM_SITES:
        cond = find_job(path, job_id).get("if")
        if not isinstance(cond, str):
            failures.append(f"{path}:{job_id}: no string `if:` to scan")
            continue
        for job in dead_failure_arms(cond):
            failures.append(
                f"{path}:{job_id}: `needs.{job}.result == 'failure'` arm sits "
                f"under a top-level `needs.{job}.result != 'failure'` guard "
                f"and can never admit the job — remove it (#728, spec 041 "
                f"D11).")
        mutated = _mut_reintroduce_dead_image_arm(cond)
        if mutated == cond or "verify-image-prerequisites" not in \
                dead_failure_arms(mutated):
            mutation_misses.append(f"{path}:{job_id}")
    if mutation_misses:
        print("::error::MUTATION SURVIVED — reintroduce the dead "
              "verify-image-prerequisites failure arm: not flagged in "
              + ", ".join(mutation_misses))
        failures.append("mutation survived: reintroduce the dead image arm")
    else:
        print(f"Mutation OK — reintroduce the dead verify-image-prerequisites "
              f"failure arm: caught in all {len(DEAD_ARM_SITES)} survivor "
              f"jobs.")
    return failures


def main():
    use_utf8_stdout()
    if not os.path.isdir(".github/workflows"):
        sys.exit("::error::run this from the repository root.")

    failures = []
    conditions = {}
    for site in CALL_SITES:
        cond = extract_condition(site)
        conditions[(site["file"], site["job_id"])] = cond
        failures += run_suite(site, cond)

    for f in failures:
        print(f"::error::{f}")

    mutation_failures = []
    for label, apply_mutation in MUTATIONS:
        any_disagreed = False
        for site in CALL_SITES:
            original = conditions[(site["file"], site["job_id"])]
            mutated = apply_mutation(original)
            if mutated == original:
                continue  # this mutation may not apply to every call site
            if run_suite(site, mutated):
                any_disagreed = True
        if any_disagreed:
            print(f"Mutation OK — {label}: caught.")
        else:
            print(f"::error::MUTATION SURVIVED — {label}: no call site's "
                  f"fixture table disagreed after this mutation, or the "
                  f"mutation never applied to any of the seven conditions.")
            mutation_failures.append(label)
    failures += [f"mutation survived: {m}" for m in mutation_failures]

    dead_arm_failures = check_dead_arms()
    for f in dead_arm_failures:
        if not f.startswith("mutation survived"):
            print(f"::error::{f}")
    failures += dead_arm_failures

    print(f"Gate 33: {len(CALL_SITES)} survivor-job condition(s), "
          f"{len(MUTATIONS) + 1} mutation(s), {len(DEAD_ARM_SITES)} job(s) "
          f"scanned for dead guarded arms; {len(failures)} failure(s).")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
