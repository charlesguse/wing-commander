#!/usr/bin/env python3
"""Gate 128 -- the fold-queue admission wiring actually serializes stage-9's
concurrency contenders and bounds fold-cycle-guard's automatic re-dispatch.

Renumbered from Gate 126 (T051, maintainer review of #821): five open
Finalize PRs all claimed Gate 126 at tasks time. The maintainer's
allocation is spec 091 (#818) keeps 126/127, this feature takes 128, spec
089 takes 129, spec 108 takes 130/131, spec 109 takes 132.

WHY THIS EXISTS
---------------
specs/074-serialized-fold-dispatch (research.md D1-D9): PR #414 showed two
overlapping stage-9 runs each joining `wing-commander-<spec-dir>` directly
could evict each other's pending job. The fix threads every entry into that
group through a ticket -- `fold-turn-act`/`fold-turn-dispatch`/
`fold-turn-implement` each block on `wing-commander-fold-queue-admit` before
the job they gate (`act`/`dispatch-once`/`implement`) is even scheduled --
and bounds `fold-cycle-guard.yml`'s automatic re-dispatch of a cycle lost to
a concurrency replacement at exactly one attempt (FR-016/FR-016a). Neither
property is provable by reading the YAML: it depends on the REAL `if:`/
`needs:` text (a dropped `needs:` entry silently reopens the race) and the
REAL shell inside `fold-queue-ledger.sh`'s `claim-dispatch` transform and
fold-cycle-guard.yml's `decide` step (a collapsed condition silently widens
who gets notified or redispatched).

WHAT THIS GATE LOADS (Principle VIII -- verbatim, never restated)
-------------------------------------------------------------
- `pr-conversation.yml`: `fold-turn-act`'s/`act`'s/`fold-turn-dispatch`'s/
  `dispatch-once`'s `if:`, `needs:`, and (`act`/`dispatch-once`'s)
  `concurrency.group`.
- `implement.yml`: `fold-turn-implement`'s/`implement`'s/`stalled`'s `if:`,
  `needs:`, and (`implement`/`stalled`'s) `concurrency.group`.
- `fold-cycle-guard.yml`'s `guard` job, step id `decide` ("Detect a lost
  cycle and react") -- run directly (`wc_shell_harness.run_step`, the same
  technique Gate 34/71 use), never re-typed as a description of what it does.
  Step id `react` ("React to the redispatch claim")'s `run:` text is loaded
  the same way but only pattern-matched (scenario 9), never executed --
  it calls the real `gh workflow run`, which this gate does not stub.
- `.github/actions/_shared/fold-queue-ledger.sh`'s `claim-dispatch` and
  `claim-redispatch` transforms -- run directly against a throwaway local
  bare repository (`LEDGER_REMOTE_URL`, the same fixture convention
  `.github/scripts/wing-commander-fold-queue-claim-dispatch-tests/run-tests.sh`
  and `.github/scripts/wing-commander-fold-queue-ledger-tests/run-tests.sh`
  already use; this gate's own value is proving MUTATIONS of those
  transforms, which the manual quickstart drill does not).

The two composites' own step lists (peek, peek-implement-run, claim) are
NOT re-run here -- fold-cycle-guard.yml's `decide` step already takes their
outputs as plain environment variables (PEEK_OUT/ROUND_OUT), which is
exactly the seam this gate fixtures at, matching decide's real shape rather
than reaching around it.

SCENARIOS (`suite(subject)`, contracts/gates.md)
-------------------------------------------------
1. Single run, no contention -- fold-turn-act's ticket grants immediately
   (modelled as `needs.fold-turn-act.result == 'success'`); `act` then runs.
   The zero-extra-poll-iteration guarantee itself is
   `wing-commander-fold-queue-admit`'s own contract, proven by its T009
   fixtures ("a clean immediate grant") -- this gate's own scope is the
   workflow-level consequence: the ticket gates entry at all.
2. Two overlapping runs -- `act` must not run ahead of its OWN fold-turn-act
   ticket (modelled as that ticket's result being anything but 'success'),
   and `act`'s `needs:` must still name it (so GitHub itself blocks
   scheduling, never merely `if:`).
3. Three overlapping runs -- the identical two checks extended to
   `dispatch-once`/`fold-turn-dispatch` and `implement`/`fold-turn-implement`,
   proving the invariant is not special-cased to one call site.
4. Dispatch claim while a fold is still outstanding -- a dispatch ticket
   reaches the queue head with an `act`-kind ticket still queued behind it;
   `claim-dispatch` must resolve `should-dispatch: false` (FR-007).
5. Dispatch claim after the round empties -- a dispatch ticket reaches an
   empty queue and wins (`should-dispatch: true`, an `implement`-kind ticket
   enqueued atomically behind it); a second, concurrent dispatch-kind
   ticket enqueued behind the winner can never even attempt a valid claim
   (it is not at the queue head) -- `claim-dispatch` against it is a
   caller-error, not a second `true` (FR-009/SC-003).
6. A `stop`-only run (every classified leg is `stop` -- the stop procedure
   runs INSIDE `act`, so `legs` is never `[]` for this case; T054/B2) --
   `fold-turn-act`'s/`fold-turn-dispatch`'s `if:` resolve false whenever
   classify-and-announce's `stop-only` output is `true`, so their only
   `enqueue` step never runs, and `act`/`dispatch-once` accept that skip
   ONLY when `stop-only` agrees it was deliberate, never as a blanket
   substitute for a real grant (FR-005/SC-009/FR-017a).
7. `fold-cycle-guard`'s `decide` step: never-started + a correlated entrant
   -> proceeds toward redispatch; never-started + no correlated entrant ->
   `action-taken: none`; ran a step then was cancelled -> `action-taken:
   none` regardless of correlation (FR-012/FR-013).
8. Re-dispatch bound -- a round whose peeked `redispatch-count` is already
   `1` must resolve to a report-only outcome, never a second redispatch
   attempt (FR-016a).
9. Re-dispatch claim enqueues a fresh ticket atomically (T038) -- a winning
   `claim-redispatch` call must enqueue an `implement`-kind ticket in the
   SAME write as the `redispatch_count` CAS and return its token, and the
   `react` step must thread that token onto its `gh workflow run`
   re-dispatch as `fold_queue_token` -- otherwise the recovered cycle
   re-enters `implement.yml`'s concurrency group unticketed, exposed to
   the very eviction FR-016 exists to recover from.
10. No-own-folds never wins, in any queue order (2026-09-29 reconciliation
    with spec 075, spec 075 FR-014) -- declines against both an
    already-empty, unclaimed round and a round with an outstanding
    act-kind ticket; never `requeued` (own_folds == 0 short-circuits
    before the round-emptiness check is even reached).
11. A folding run requeues behind an outstanding act-kind ticket rather
    than stepping aside (2026-09-29 reconciliation with spec 075) -- the
    ledger actually reorders the queue (proven via `peek`, not just the
    outcome label), and the same ticket wins once that act-kind ticket
    clears.
12. The winning claim's `folded-items` names every contributing run in the
    round, each attributed to its own `run_id` -- not only the winning
    run's own evidence (2026-09-29 reconciliation with spec 075, FR-011).
13. Standalone mode (T046): a winning claim with `implement-configured:
    false` claims the round (`dispatch_claimed_by` set, a sibling claim
    still declines) but returns an empty `implement-token` and never
    enqueues an implement-kind ticket -- nothing will ever come to
    release one.
14. Idempotent win (T050): a retried `claim-dispatch` call carrying the
    SAME dispatch token, after that token's own prior call already won,
    resolves `outcome: won` again (not `declined`) and returns the SAME
    `implement-token` rather than enqueueing a second one.
15. No ticket job carries its own concurrency: group (T061, maintainer
    review of #821, B9) -- fold-turn-act/fold-turn-dispatch/
    fold-turn-implement (admit/claim-dispatch/await) each carry no
    concurrency: block of their own, or a wait running inside one could
    deadlock against the very group it is awaiting entry to (T045's exact
    defect, before the claim was moved out of dispatch-once).

MUTATIONS (each proven to break the gate -- FR-022)
----------------------------------------------------
- `mut_drop_fold_turn_needs` -- strips the `fold-turn-*` prerequisite out of
  the downstream job's `needs:` (defect #1 restored). Fails scenarios 2/3.
- `mut_unconditional_dispatch` -- removes the round-emptiness check from
  `claim-dispatch`'s own jq filter (defect #2 restored: dispatch-once would
  fire once per run again, not once per round). Fails scenarios 4/5.
- `mut_collapse_manual_and_replaced` -- forces `decide`'s correlation check
  to always report a match, collapsing the distinction an unexplained
  pending-cancel (stay silent, research.md D7) and a correlated one (notify)
  into always-notify (defect #3 restated). Fails scenario 7.
- `mut_unbounded_redispatch` -- removes `decide`'s own `redispatch_count ==
  1` fast-path check, so it would attempt a second redispatch instead of
  reporting once and stopping. Fails scenario 8.
- `mut_redispatch_no_enqueue` -- reverts `claim-redispatch`'s jq filter to
  only flip `redispatch_count` without enqueueing the implement-kind ticket
  (the T038 defect restored). Fails scenario 9.
- `mut_drop_redispatch_token_thread` -- removes the `-f fold_queue_token=`
  argument from `react`'s `gh workflow run` call (the T038 defect
  restored). Fails scenario 9.
- `mut_requeue_replaced_by_stepaside` -- reverts `claim-dispatch`'s requeue
  branch to a plain decline with no queue mutation, so a folding run facing
  an outstanding act-kind ticket steps aside instead of requeuing. Fails
  scenario 11 (and scenario 12, which depends on the requeued ticket
  surviving to win).
- `mut_own_folds_check_dropped` -- disables the own-folds gate so a
  no-fold run can fall through to win (spec 075 FR-014 regression). Fails
  scenario 10.
- `mut_round_list_narrowed_to_claimant` -- narrows the winning claim's
  `folded-items` back to the claimant's own `run_id`, dropping every other
  contributing run's folds from the reply. Fails scenario 12.
- `mut_standalone_still_enqueues` -- ignores `implement_configured` and
  always enqueues the implement-kind ticket (the T046 defect restored: a
  standalone-mode win would wedge every later admission for the spec-dir
  behind a ticket nothing will ever release). Fails scenario 13.
- `mut_win_retry_declines` -- reverts the winning branch's idempotent-retry
  check to a plain decline (the T050 defect restored: a retried claim from
  the same run that already won would report `declined` instead of `won`,
  contradicting this file's own "every transform is idempotent under
  retry"). Fails scenario 14.
- `mut_drop_stop_only_handling` -- reverts fold-turn-act/fold-turn-dispatch
  to admitting a ticket even for a stop-only run, and act/dispatch-once to
  requiring a bare `success` result from them (the T054/B2 defect
  restored). Fails scenario 6.
- `mut_ticket_job_gains_concurrency_group` -- gives fold-turn-dispatch a
  concurrency: block of its own (the T061/B9 regression item 1's own fix
  removed). Fails scenario 15.

`main()` runs `suite()` against the untouched subject (must be 0 failures),
then re-runs it under each mutation and requires a failure -- identical to
Gate 70's own `main()` shape (contracts/gates.md), including no separate
`--self-test` step: the mutations ARE this gate's self-test, in the same
single invocation.
"""
import json
import os
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_gha_expr import evaluate, truthy  # noqa: E402
from wc_shell_harness import (ensure_jq, find_job, find_step, resolve_bash,
                              run_step, use_utf8_stdout)  # noqa: E402

PR_CONV = os.path.join(".github", "workflows", "pr-conversation.yml")
IMPLEMENT = os.path.join(".github", "workflows", "implement.yml")
GUARD = os.path.join(".github", "workflows", "fold-cycle-guard.yml")
LEDGER_SH = os.path.join(".github", "actions", "_shared", "fold-queue-ledger.sh")
DECIDE_STEP_NAME = "Detect a lost cycle and react"
REACT_STEP_NAME = "React to the redispatch claim"

BASH = None

EXPECTED_ACT_GROUP = "${{ needs.classify-and-announce.outputs.concurrency-group }}"
EXPECTED_SPEC_GROUP = "wing-commander-${{ inputs.spec-dir }}"


# --------------------------------------------------------------------------
# Subject loading -- verbatim, never restated
# --------------------------------------------------------------------------
def needs_of(job):
    n = (job or {}).get("needs") or []
    return [n] if isinstance(n, str) else list(n)


def load_expr_subject():
    subject = {}
    for jid in ("fold-turn-act", "act", "fold-turn-dispatch", "dispatch-once"):
        job = find_job(PR_CONV, jid)
        subject[f"{jid}:if"] = str(job.get("if") or "")
        subject[f"{jid}:needs"] = needs_of(job)
    for jid in ("act", "dispatch-once"):
        job = find_job(PR_CONV, jid)
        subject[f"{jid}:group"] = str((job.get("concurrency") or {}).get("group") or "")

    for jid in ("fold-turn-implement", "implement", "stalled"):
        job = find_job(IMPLEMENT, jid)
        subject[f"{jid}:if"] = str(job.get("if") or "")
        subject[f"{jid}:needs"] = needs_of(job)
    for jid in ("implement", "stalled"):
        job = find_job(IMPLEMENT, jid)
        subject[f"{jid}:group"] = str((job.get("concurrency") or {}).get("group") or "")

    # T061 (maintainer review of #821, B9): item 1's own fix -- admit,
    # claim-dispatch and await (fold-turn-act/fold-turn-dispatch/
    # fold-turn-implement) must run in a job with NO concurrency: block of
    # its own, or a waiter blocked inside one of these jobs' own group
    # could never see the ticket it awaits clear (T045's exact deadlock,
    # research.md D1) -- nothing before this task asserted it.
    for jid, path in (("fold-turn-act", PR_CONV), ("fold-turn-dispatch", PR_CONV),
                      ("fold-turn-implement", IMPLEMENT)):
        job = find_job(path, jid)
        subject[f"{jid}:has-concurrency"] = job.get("concurrency") is not None

    for key, val in subject.items():
        if key.endswith(":if") and not val.strip():
            sys.exit(f"::error::{key} has no if: -- nothing to evaluate. "
                     f"Removing a guard is the regression this gate exists for.")

    decide = find_step(GUARD, DECIDE_STEP_NAME)
    subject["decide:run"] = str(decide.get("run") or "")
    if not subject["decide:run"].strip():
        sys.exit(f"::error file={GUARD}::step {DECIDE_STEP_NAME!r} has no run: -- "
                 f"nothing to execute.")

    react = find_step(GUARD, REACT_STEP_NAME)
    subject["react:run"] = str(react.get("run") or "")
    if not subject["react:run"].strip():
        sys.exit(f"::error file={GUARD}::step {REACT_STEP_NAME!r} has no run: -- "
                 f"nothing to execute.")

    with open(LEDGER_SH, encoding="utf-8") as fh:
        subject["ledger:text"] = fh.read()

    return subject


# --------------------------------------------------------------------------
# pr-conversation.yml / implement.yml expression contexts
# --------------------------------------------------------------------------
def pr_ctx(legs='["leg-1"]', qualifies="true", fold_turn_act="success",
           fold_turn_dispatch="success", stop_only="false"):
    return {
        "cancelled()": False,
        "always()": True,
        "needs.verify-image-prerequisites.result": "success",
        "needs.classify-and-announce.result": "success",
        "needs.classify-and-announce.outputs.qualifies": qualifies,
        "needs.classify-and-announce.outputs.legs": legs,
        "needs.classify-and-announce.outputs.stop-only": stop_only,
        "needs.fold-turn-act.result": fold_turn_act,
        "needs.fold-turn-dispatch.result": fold_turn_dispatch,
    }


def impl_ctx(fold_turn_implement="success", implement_result="success",
             final_ok="true", refusal_reason=""):
    return {
        "cancelled()": False,
        "needs.verify-image-prerequisites.result": "success",
        "needs.fold-turn-implement.result": fold_turn_implement,
        "needs.implement.result": implement_result,
        "needs.implement.outputs.final-ok": final_ok,
        "needs.implement.outputs.refusal-reason": refusal_reason,
    }


# --------------------------------------------------------------------------
# Scenarios 1-3, 6: expression + structural wiring
# --------------------------------------------------------------------------
def scenario_single_run_no_contention(subject):
    failures = []
    ctx = pr_ctx()
    if not truthy(evaluate(subject["fold-turn-act:if"], ctx)):
        failures.append("scenario 1: fold-turn-act:if did not run for a "
                        "qualifying review with a granted ticket")
    if not truthy(evaluate(subject["act:if"], ctx)):
        failures.append("scenario 1: act:if did not run once its own "
                        "fold-turn-act ticket was granted (result=success)")
    if subject["act:group"] != EXPECTED_ACT_GROUP:
        failures.append(f"scenario 1: act's concurrency.group is "
                        f"{subject['act:group']!r}, expected "
                        f"{EXPECTED_ACT_GROUP!r} -- unchanged by contract")
    return failures


def scenario_two_overlapping(subject):
    failures = []
    if "fold-turn-act" not in subject["act:needs"]:
        failures.append("scenario 2: act:needs does not name fold-turn-act "
                        "-- GitHub's own needs: skip-propagation is the only "
                        "lever that stops a second run's act from joining "
                        "the concurrency group ahead of its ticket")
        return failures
    ctx = pr_ctx(fold_turn_act="failure")
    if truthy(evaluate(subject["act:if"], ctx)):
        failures.append("scenario 2: act:if ran despite fold-turn-act not "
                        "having granted the ticket (result=failure)")
    return failures


def scenario_three_overlapping(subject):
    failures = []
    for downstream, ticket, key in (
        ("dispatch-once", "fold-turn-dispatch", "needs.fold-turn-dispatch.result"),
        ("implement", "fold-turn-implement", "needs.fold-turn-implement.result"),
    ):
        if ticket not in subject[f"{downstream}:needs"]:
            failures.append(f"scenario 3: {downstream}:needs does not name "
                            f"{ticket} -- the same invariant as act/"
                            f"fold-turn-act must hold at every call site, "
                            f"not just the first one")
            continue
        if downstream == "implement":
            ctx = impl_ctx(fold_turn_implement="failure")
            if truthy(evaluate(subject[f"{downstream}:if"], ctx)):
                failures.append(f"scenario 3: implement:if ran despite "
                                f"fold-turn-implement not having granted "
                                f"the ticket")
        else:
            ctx = pr_ctx(fold_turn_dispatch="failure")
            if truthy(evaluate(subject[f"{downstream}:if"], ctx)):
                failures.append(f"scenario 3: dispatch-once:if ran despite "
                                f"fold-turn-dispatch not having granted "
                                f"the ticket")
    if subject["implement:group"] != EXPECTED_SPEC_GROUP:
        failures.append(f"scenario 3: implement's concurrency.group is "
                        f"{subject['implement:group']!r}, expected "
                        f"{EXPECTED_SPEC_GROUP!r} -- unchanged by contract")
    if subject["stalled:group"] != EXPECTED_SPEC_GROUP:
        failures.append(f"scenario 3: stalled's concurrency.group is "
                        f"{subject['stalled:group']!r}, expected "
                        f"{EXPECTED_SPEC_GROUP!r} -- unchanged by contract")
    return failures


def scenario_ticket_jobs_carry_no_concurrency_group(subject):
    """T061 (B9): admit (fold-turn-act), claim-dispatch (fold-turn-dispatch)
    and await (fold-turn-implement) must each run in a job carrying NO
    concurrency: block of its own -- a waiter polling for a ticket to
    clear, from inside a group that ticket's own owning run cannot itself
    join, can never see it clear (T045's exact deadlock when the claim
    briefly lived inside dispatch-once's own group instead)."""
    failures = []
    for jid in ("fold-turn-act", "fold-turn-dispatch", "fold-turn-implement"):
        if subject[f"{jid}:has-concurrency"]:
            failures.append(f"scenario 15: {jid} carries a concurrency: "
                            f"block -- admit/claim-dispatch/await must run "
                            f"in a job with none, or a wait inside it can "
                            f"deadlock against the very group it is "
                            f"awaiting entry to (T045, research.md D1)")
    return failures


def scenario_stop_only(subject):
    """T054 (B2): the stop procedure runs INSIDE `act` (contracts/
    workflow-changes.md), so a stop-only run's `legs` is never `[]` -- it
    carries the stop leg itself. classify-and-announce's `stop-only` output
    (true only when every classified leg is `stop`) is what fold-turn-act/
    fold-turn-dispatch skip on, not an empty `legs`; the downstream `act`/
    `dispatch-once` jobs must then accept that skip, but ONLY when
    stop-only agrees -- a skip for any other reason (a real admission
    timeout on a mutating run) must still block them."""
    failures = []
    real_stop_legs = '[{"id": "leg-1", "category": "stop"}]'
    for qualifies in ("true", "false"):
        ctx = pr_ctx(legs=real_stop_legs, qualifies=qualifies, stop_only="true")
        if truthy(evaluate(subject["fold-turn-act:if"], ctx)):
            failures.append(f"scenario 6: fold-turn-act:if ran for a "
                            f"stop-only review (a real stop leg, qualifies="
                            f"{qualifies}) -- it would enqueue a ticket for "
                            f"a run with nothing to fold (FR-005/FR-017a)")
        ctx = pr_ctx(legs=real_stop_legs, qualifies=qualifies, stop_only="true",
                     fold_turn_dispatch="skipped")
        if truthy(evaluate(subject["fold-turn-dispatch:if"], ctx)):
            failures.append(f"scenario 6: fold-turn-dispatch:if ran for a "
                            f"stop-only review (a real stop leg, qualifies="
                            f"{qualifies}) -- it would enqueue a dispatch-"
                            f"claim ticket for a run with no folds to "
                            f"dispatch (FR-005/SC-009)")

    # `act` must accept its own fold-turn-act's skip, but only when
    # classify-and-announce agrees this run is stop-only.
    ctx = pr_ctx(legs=real_stop_legs, stop_only="true", fold_turn_act="skipped")
    if not truthy(evaluate(subject["act:if"], ctx)):
        failures.append("scenario 6: act:if did not run for a stop-only "
                        "review whose fold-turn-act skipped as designed -- "
                        "the stop leg itself (run inside act) would never "
                        "execute, and the run it targets would wait out "
                        "the very ticket this fix removes (FR-005/SC-009)")

    # A skip for any OTHER reason (e.g. a mutating run whose fold-turn-act
    # job was itself skipped by some upstream failure) must NOT be treated
    # as a stop-only pass-through.
    ctx = pr_ctx(legs='["leg-1"]', stop_only="false", fold_turn_act="skipped")
    if truthy(evaluate(subject["act:if"], ctx)):
        failures.append("scenario 6: act:if ran despite fold-turn-act "
                        "skipping on a run classify-and-announce does NOT "
                        "consider stop-only -- the stop-only skip must not "
                        "be a blanket substitute for a real ticket grant")

    ctx = pr_ctx(legs=real_stop_legs, stop_only="true", fold_turn_dispatch="skipped")
    if not truthy(evaluate(subject["dispatch-once:if"], ctx)):
        failures.append("scenario 6: dispatch-once:if did not run for a "
                        "stop-only review whose fold-turn-dispatch skipped "
                        "as designed (FR-005/SC-009)")

    ctx = pr_ctx(legs='["leg-1"]', stop_only="false", fold_turn_dispatch="skipped")
    if truthy(evaluate(subject["dispatch-once:if"], ctx)):
        failures.append("scenario 6: dispatch-once:if ran despite "
                        "fold-turn-dispatch skipping on a run classify-and-"
                        "announce does NOT consider stop-only")
    return failures


# --------------------------------------------------------------------------
# Scenarios 4-5: the real claim-dispatch transform, local bare-repo fixture
# --------------------------------------------------------------------------
def parse_kv(text):
    out = {}
    for line in text.splitlines():
        if "=" in line:
            k, _, v = line.partition("=")
            out[k] = v
    return out


def new_bare_remote(root):
    remote = os.path.join(tempfile.mkdtemp(dir=root), "fold-queue-remote.git")
    subprocess.run(["git", "init", "--quiet", "--bare", remote], check=True)
    return remote


def run_ledger(ledger_path, transform, remote, env_extra):
    env = dict(os.environ)
    env.update({"LEDGER_REMOTE_URL": remote, "GH_TOKEN": "x",
               "GITHUB_REPOSITORY": "x/x"})
    env.update(env_extra)
    proc = subprocess.run([BASH, ledger_path, transform], env=env,
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace")
    return proc


def scenario_dispatch_while_outstanding(subject, root):
    """Scenario 4 (FR-007): a dispatch ticket at the queue head with an
    act-kind ticket still queued behind it, and folds of its own, must
    requeue (never win) -- should-dispatch stays 'false' either way, but
    the 2026-09-29 reconciliation with spec 075 distinguishes 'requeued'
    (own folds, round not empty) from 'declined' (no own folds)."""
    failures = []
    remote = new_bare_remote(root)
    spec = "specs/999-fixture"
    run_ledger(LEDGER_SH, "enqueue", remote,
              {"SPEC_DIR": spec, "KIND": "act", "RUN_ID": "500"})
    run_ledger(LEDGER_SH, "release", remote,
              {"SPEC_DIR": spec, "TOKEN": "run-500-act", "RUN_ID": "500",
               "OUTCOME": "folded", "COMMIT_SHA": "cafe", "LEG_ID": "leg-1",
               "SUMMARY": "s"})
    run_ledger(LEDGER_SH, "enqueue", remote,
              {"SPEC_DIR": spec, "KIND": "dispatch", "RUN_ID": "500"})
    run_ledger(LEDGER_SH, "enqueue", remote,
              {"SPEC_DIR": spec, "KIND": "act", "RUN_ID": "501"})
    proc = run_ledger(LEDGER_SH, "claim-dispatch", remote,
                      {"SPEC_DIR": spec, "ROUND": "1",
                       "DISPATCH_TOKEN": "run-500-dispatch", "ITERATION": "2",
                       "OWN_FOLDS": "1"})
    result = parse_kv(proc.stdout)
    if result.get("should-dispatch") != "false":
        failures.append(f"scenario 4: claim-dispatch resolved "
                        f"should-dispatch={result.get('should-dispatch')!r} "
                        f"while an act-kind ticket remained queued behind "
                        f"the dispatch ticket; expected 'false'. stderr: "
                        f"{proc.stderr.strip()}")
    if result.get("outcome") != "requeued":
        failures.append(f"scenario 4: a dispatch ticket with own folds "
                        f"(own-folds=1) facing an outstanding act-kind "
                        f"ticket resolved outcome={result.get('outcome')!r}, "
                        f"expected 'requeued' -- it must not silently step "
                        f"aside (2026-09-29 reconciliation with spec 075)")
    return failures


def scenario_dispatch_after_round_empties(subject, root):
    """Scenario 5 (FR-009/SC-003): the winning claimant gets should-dispatch
    true and atomically enqueues an implement ticket; a second, concurrent
    dispatch-kind ticket enqueued behind the winner is never at the queue
    head, so a claim attempted with its token is a caller error, never a
    second 'true'."""
    failures = []
    remote = new_bare_remote(root)
    spec = "specs/999-fixture"
    run_ledger(LEDGER_SH, "enqueue", remote,
              {"SPEC_DIR": spec, "KIND": "act", "RUN_ID": "600"})
    run_ledger(LEDGER_SH, "release", remote,
              {"SPEC_DIR": spec, "TOKEN": "run-600-act", "RUN_ID": "600",
               "OUTCOME": "folded", "COMMIT_SHA": "feed", "LEG_ID": "leg-1",
               "SUMMARY": "s"})
    run_ledger(LEDGER_SH, "enqueue", remote,
              {"SPEC_DIR": spec, "KIND": "dispatch", "RUN_ID": "600"})
    run_ledger(LEDGER_SH, "enqueue", remote,
              {"SPEC_DIR": spec, "KIND": "dispatch", "RUN_ID": "601"})

    proc = run_ledger(LEDGER_SH, "claim-dispatch", remote,
                      {"SPEC_DIR": spec, "ROUND": "1",
                       "DISPATCH_TOKEN": "run-600-dispatch", "ITERATION": "2",
                       "OWN_FOLDS": "1"})
    result = parse_kv(proc.stdout)
    if result.get("should-dispatch") != "true":
        failures.append(f"scenario 5: winning claimant resolved "
                        f"should-dispatch={result.get('should-dispatch')!r} "
                        f"against an empty round; expected 'true'. stderr: "
                        f"{proc.stderr.strip()}")
    if result.get("implement-token") != "run-600-implement":
        failures.append(f"scenario 5: winning claimant's implement-token is "
                        f"{result.get('implement-token')!r}, expected "
                        f"'run-600-implement'")

    proc2 = run_ledger(LEDGER_SH, "claim-dispatch", remote,
                       {"SPEC_DIR": spec, "ROUND": "1",
                        "DISPATCH_TOKEN": "run-601-dispatch", "ITERATION": "2",
                        "OWN_FOLDS": "1"})
    result2 = parse_kv(proc2.stdout)
    if result2.get("should-dispatch") == "true":
        failures.append("scenario 5: a SECOND, concurrent dispatch-kind "
                        "ticket also resolved should-dispatch=true -- "
                        "exactly one of two concurrent claimants may win")
    if "error" not in proc2.stdout and proc2.returncode == 0:
        failures.append(f"scenario 5: the second claimant (not at the "
                        f"queue head) neither errored nor reported "
                        f"should-dispatch=false plainly: {proc2.stdout!r}")
    return failures


def scenario_no_own_folds_never_wins(subject, root):
    """Scenario 10 (c) (spec 075 FR-014, reconciled 2026-09-29): a run with
    no folds of its own never wins the claim, in any queue order -- neither
    against an already-empty, unclaimed round (where the pre-reconciliation
    shape would have won) nor against a round with an outstanding act-kind
    ticket (where it must decline, never requeue -- requeuing is reserved
    for a run that DID fold something of its own)."""
    failures = []
    remote = new_bare_remote(root)
    spec = "specs/999-fixture-nofolds-a"
    run_ledger(LEDGER_SH, "enqueue", remote,
              {"SPEC_DIR": spec, "KIND": "act", "RUN_ID": "700"})
    run_ledger(LEDGER_SH, "release", remote,
              {"SPEC_DIR": spec, "TOKEN": "run-700-act", "RUN_ID": "700",
               "OUTCOME": "not-folded", "LEG_ID": "leg-1"})
    run_ledger(LEDGER_SH, "enqueue", remote,
              {"SPEC_DIR": spec, "KIND": "dispatch", "RUN_ID": "700"})
    proc = run_ledger(LEDGER_SH, "claim-dispatch", remote,
                      {"SPEC_DIR": spec, "ROUND": "1",
                       "DISPATCH_TOKEN": "run-700-dispatch", "ITERATION": "2",
                       "OWN_FOLDS": "0"})
    result = parse_kv(proc.stdout)
    if result.get("should-dispatch") != "false" or result.get("outcome") != "declined":
        failures.append(f"scenario 10a: a no-own-folds ticket against an "
                        f"empty, unclaimed round resolved "
                        f"should-dispatch={result.get('should-dispatch')!r} "
                        f"outcome={result.get('outcome')!r}, expected "
                        f"should-dispatch=false outcome=declined")

    spec_b = "specs/999-fixture-nofolds-b"
    run_ledger(LEDGER_SH, "enqueue", remote,
              {"SPEC_DIR": spec_b, "KIND": "act", "RUN_ID": "701"})
    run_ledger(LEDGER_SH, "release", remote,
              {"SPEC_DIR": spec_b, "TOKEN": "run-701-act", "RUN_ID": "701",
               "OUTCOME": "not-folded", "LEG_ID": "leg-1"})
    run_ledger(LEDGER_SH, "enqueue", remote,
              {"SPEC_DIR": spec_b, "KIND": "dispatch", "RUN_ID": "701"})
    run_ledger(LEDGER_SH, "enqueue", remote,
              {"SPEC_DIR": spec_b, "KIND": "act", "RUN_ID": "702"})
    proc2 = run_ledger(LEDGER_SH, "claim-dispatch", remote,
                       {"SPEC_DIR": spec_b, "ROUND": "1",
                        "DISPATCH_TOKEN": "run-701-dispatch", "ITERATION": "2",
                        "OWN_FOLDS": "0"})
    result2 = parse_kv(proc2.stdout)
    if result2.get("should-dispatch") != "false" or result2.get("outcome") != "declined":
        failures.append(f"scenario 10b: a no-own-folds ticket against a "
                        f"round with an outstanding act-kind ticket resolved "
                        f"should-dispatch={result2.get('should-dispatch')!r} "
                        f"outcome={result2.get('outcome')!r}, expected "
                        f"should-dispatch=false outcome=declined (never "
                        f"'requeued' -- that path is reserved for a run "
                        f"that folded something of its own)")
    return failures


def scenario_requeue_behind_outstanding_then_wins(subject, root):
    """Scenario 11 (a) (2026-09-29 reconciliation with spec 075): a
    dispatch ticket with folds of its own, facing another run's
    outstanding act-kind ticket (itself a run that folds nothing), does
    NOT step aside -- it requeues behind that ticket (proven by the queue
    actually reordering, not just the outcome label), then wins once that
    ticket clears."""
    failures = []
    remote = new_bare_remote(root)
    spec = "specs/999-fixture-requeue"
    run_ledger(LEDGER_SH, "enqueue", remote,
              {"SPEC_DIR": spec, "KIND": "act", "RUN_ID": "800"})
    run_ledger(LEDGER_SH, "release", remote,
              {"SPEC_DIR": spec, "TOKEN": "run-800-act", "RUN_ID": "800",
               "OUTCOME": "folded", "COMMIT_SHA": "aaaa", "LEG_ID": "leg-1",
               "SUMMARY": "s"})
    run_ledger(LEDGER_SH, "enqueue", remote,
              {"SPEC_DIR": spec, "KIND": "dispatch", "RUN_ID": "800"})
    run_ledger(LEDGER_SH, "enqueue", remote,
              {"SPEC_DIR": spec, "KIND": "act", "RUN_ID": "801"})

    proc1 = run_ledger(LEDGER_SH, "claim-dispatch", remote,
                       {"SPEC_DIR": spec, "ROUND": "1",
                        "DISPATCH_TOKEN": "run-800-dispatch", "ITERATION": "2",
                        "OWN_FOLDS": "1"})
    result1 = parse_kv(proc1.stdout)
    if result1.get("outcome") != "requeued":
        failures.append(f"scenario 11: expected outcome=requeued while "
                        f"run-801's act ticket was still outstanding, got "
                        f"{result1.get('outcome')!r}. stderr: "
                        f"{proc1.stderr.strip()}")
        return failures

    peek_proc = run_ledger(LEDGER_SH, "peek", remote,
                           {"SPEC_DIR": spec, "PEEK_TOKEN": "run-800-dispatch"})
    peek_result = parse_kv(peek_proc.stdout)
    if peek_result.get("position") == "0":
        failures.append("scenario 11: run-800-dispatch is still reported at "
                        "the queue head after a 'requeued' outcome -- it "
                        "must actually move, not just change its label")
    if peek_result.get("head-token") != "run-801-act" or peek_result.get("head-granted-at") == "":
        failures.append(f"scenario 11: expected run-801-act to be the new, "
                        f"granted queue head after run-800-dispatch "
                        f"requeued behind it; peek={peek_result!r}")

    run_ledger(LEDGER_SH, "release", remote,
              {"SPEC_DIR": spec, "TOKEN": "run-801-act", "RUN_ID": "801",
               "OUTCOME": "not-folded", "LEG_ID": "leg-1"})

    proc2 = run_ledger(LEDGER_SH, "claim-dispatch", remote,
                       {"SPEC_DIR": spec, "ROUND": "1",
                        "DISPATCH_TOKEN": "run-800-dispatch", "ITERATION": "2",
                        "OWN_FOLDS": "1"})
    result2 = parse_kv(proc2.stdout)
    if result2.get("should-dispatch") != "true" or result2.get("outcome") != "won":
        failures.append(f"scenario 11: expected the requeued ticket to win "
                        f"once run-801's act ticket cleared; got "
                        f"should-dispatch={result2.get('should-dispatch')!r} "
                        f"outcome={result2.get('outcome')!r}. stderr: "
                        f"{proc2.stderr.strip()}")
    return failures


def scenario_won_reply_names_every_contributing_run(subject, root):
    """Scenario 12 (b) (2026-09-29 reconciliation with spec 075): two
    folding runs in the same round produce exactly one dispatch, whose
    folded-items list names BOTH runs' folds, each still attributed to its
    own run_id -- the deliberate widening from the winning run's own
    evidence to the round's whole accumulated evidence."""
    failures = []
    remote = new_bare_remote(root)
    spec = "specs/999-fixture-round-list"
    run_ledger(LEDGER_SH, "enqueue", remote,
              {"SPEC_DIR": spec, "KIND": "act", "RUN_ID": "900"})
    run_ledger(LEDGER_SH, "release", remote,
              {"SPEC_DIR": spec, "TOKEN": "run-900-act", "RUN_ID": "900",
               "OUTCOME": "folded", "COMMIT_SHA": "1111", "LEG_ID": "leg-1",
               "SUMMARY": "s"})
    run_ledger(LEDGER_SH, "enqueue", remote,
              {"SPEC_DIR": spec, "KIND": "dispatch", "RUN_ID": "900"})
    run_ledger(LEDGER_SH, "enqueue", remote,
              {"SPEC_DIR": spec, "KIND": "act", "RUN_ID": "901"})
    run_ledger(LEDGER_SH, "claim-dispatch", remote,
              {"SPEC_DIR": spec, "ROUND": "1", "DISPATCH_TOKEN": "run-900-dispatch",
               "ITERATION": "2", "OWN_FOLDS": "1"})
    run_ledger(LEDGER_SH, "release", remote,
              {"SPEC_DIR": spec, "TOKEN": "run-901-act", "RUN_ID": "901",
               "OUTCOME": "folded", "COMMIT_SHA": "2222", "LEG_ID": "leg-1",
               "SUMMARY": "s"})

    proc = run_ledger(LEDGER_SH, "claim-dispatch", remote,
                      {"SPEC_DIR": spec, "ROUND": "1", "DISPATCH_TOKEN": "run-900-dispatch",
                       "ITERATION": "2", "OWN_FOLDS": "1"})
    result = parse_kv(proc.stdout)
    if result.get("should-dispatch") != "true" or result.get("outcome") != "won":
        failures.append(f"scenario 12: expected the second attempt to win "
                        f"once run-901's act ticket cleared; got "
                        f"should-dispatch={result.get('should-dispatch')!r} "
                        f"outcome={result.get('outcome')!r}. stderr: "
                        f"{proc.stderr.strip()}")
        return failures
    folded_items = json.loads(result.get("folded-items", "[]") or "[]")
    run_ids = sorted(item.get("run_id") for item in folded_items)
    if run_ids != ["900", "901"]:
        failures.append(f"scenario 12: winning claim's folded-items names "
                        f"run_ids {run_ids!r}, expected ['900', '901'] -- "
                        f"the round's WHOLE accumulated list, not only the "
                        f"winning run's own evidence")
    return failures


def scenario_standalone_never_enqueues_implement_ticket(subject, root):
    """Scenario 13 (T046): implement-configured=false still claims the round
    (a sibling's claim still declines) but returns an empty implement-token
    and never enqueues an implement-kind ticket -- nothing (no dispatched
    implement.yml run) will ever come to release one, so a spec-dir with no
    implement-workflow configured must not wedge every later admission
    behind an orphaned ticket."""
    failures = []
    remote = new_bare_remote(root)
    spec = "specs/999-fixture-standalone"
    run_ledger(LEDGER_SH, "enqueue", remote,
              {"SPEC_DIR": spec, "KIND": "act", "RUN_ID": "1000"})
    run_ledger(LEDGER_SH, "release", remote,
              {"SPEC_DIR": spec, "TOKEN": "run-1000-act", "RUN_ID": "1000",
               "OUTCOME": "folded", "COMMIT_SHA": "abcd", "LEG_ID": "leg-1",
               "SUMMARY": "s"})
    run_ledger(LEDGER_SH, "enqueue", remote,
              {"SPEC_DIR": spec, "KIND": "dispatch", "RUN_ID": "1000"})
    proc = run_ledger(LEDGER_SH, "claim-dispatch", remote,
                      {"SPEC_DIR": spec, "ROUND": "1",
                       "DISPATCH_TOKEN": "run-1000-dispatch", "ITERATION": "2",
                       "OWN_FOLDS": "1", "IMPLEMENT_CONFIGURED": "false"})
    result = parse_kv(proc.stdout)
    if result.get("should-dispatch") != "true" or result.get("outcome") != "won":
        failures.append(f"scenario 13: a standalone-mode claim with own "
                        f"folds and an empty round resolved "
                        f"should-dispatch={result.get('should-dispatch')!r} "
                        f"outcome={result.get('outcome')!r}; expected "
                        f"should-dispatch=true outcome=won -- the round is "
                        f"still claimed, only the ticket is skipped. stderr: "
                        f"{proc.stderr.strip()}")
    if result.get("implement-token", "unset") != "":
        failures.append(f"scenario 13: a standalone-mode win returned "
                        f"implement-token={result.get('implement-token')!r}, "
                        f"expected '' -- no implement.yml run will ever "
                        f"exist to release a ticket")

    peek_proc = run_ledger(LEDGER_SH, "peek", remote,
                           {"SPEC_DIR": spec, "PEEK_TOKEN": "run-1000-implement"})
    peek_result = parse_kv(peek_proc.stdout)
    if peek_result.get("position", "-1") != "-1":
        failures.append(f"scenario 13: an implement-kind ticket "
                        f"'run-1000-implement' was enqueued despite "
                        f"implement-configured=false: peek={peek_result!r}")
    return failures


def scenario_idempotent_win_retry(subject, root):
    """Scenario 14 (T050): a retried claim-dispatch call carrying the same
    dispatch token as a prior WINNING call must resolve won again -- this
    file's own header claims every transform is idempotent under retry, but
    the winning branch alone declined a retry of its own win before this
    fix, mistaking it for a losing claimant of an already-claimed round."""
    failures = []
    remote = new_bare_remote(root)
    spec = "specs/999-fixture-idempotent-win"
    run_ledger(LEDGER_SH, "enqueue", remote,
              {"SPEC_DIR": spec, "KIND": "act", "RUN_ID": "1100"})
    run_ledger(LEDGER_SH, "release", remote,
              {"SPEC_DIR": spec, "TOKEN": "run-1100-act", "RUN_ID": "1100",
               "OUTCOME": "folded", "COMMIT_SHA": "beef", "LEG_ID": "leg-1",
               "SUMMARY": "s"})
    run_ledger(LEDGER_SH, "enqueue", remote,
              {"SPEC_DIR": spec, "KIND": "dispatch", "RUN_ID": "1100"})
    first = run_ledger(LEDGER_SH, "claim-dispatch", remote,
                       {"SPEC_DIR": spec, "ROUND": "1",
                        "DISPATCH_TOKEN": "run-1100-dispatch", "ITERATION": "2",
                        "OWN_FOLDS": "1"})
    first_result = parse_kv(first.stdout)
    if first_result.get("should-dispatch") != "true":
        failures.append(f"scenario 14: setup's first claim did not win: "
                        f"{first_result!r}. stderr: {first.stderr.strip()}")
        return failures

    retry = run_ledger(LEDGER_SH, "claim-dispatch", remote,
                       {"SPEC_DIR": spec, "ROUND": "1",
                        "DISPATCH_TOKEN": "run-1100-dispatch", "ITERATION": "2",
                        "OWN_FOLDS": "1"})
    retry_result = parse_kv(retry.stdout)
    if retry_result.get("should-dispatch") != "true" or retry_result.get("outcome") != "won":
        failures.append(f"scenario 14: a retry of the SAME dispatch token "
                        f"that already won resolved "
                        f"should-dispatch={retry_result.get('should-dispatch')!r} "
                        f"outcome={retry_result.get('outcome')!r}; expected "
                        f"should-dispatch=true outcome=won (idempotent under "
                        f"retry). stderr: {retry.stderr.strip()}")
    if retry_result.get("implement-token") != first_result.get("implement-token"):
        failures.append(f"scenario 14: a retried win returned a different "
                        f"implement-token ({retry_result.get('implement-token')!r}) "
                        f"than the original win ({first_result.get('implement-token')!r})")
    return failures


# --------------------------------------------------------------------------
# Scenarios 7-8: fold-cycle-guard.yml's decide step, run directly
# --------------------------------------------------------------------------
GH_STUB = r"""#!/bin/sh
echo "gh $*" >> "$GH_CALLS"
case " $* " in
  *"/jobs"*)
    cat "$GH_JOBS_JSON"
    exit 0
    ;;
  *" api "*"/actions/runs/"*)
    cat "$GH_RUN_JSON"
    exit 0
    ;;
  *" issue "*"comment "*)
    prev=""
    for a in "$@"; do
      if [ "$prev" = "--body-file" ]; then cp "$a" "$GH_LAST_COMMENT"; fi
      prev="$a"
    done
    exit 0
    ;;
esac
exit 0
"""


def new_gh_stub(work):
    bindir = os.path.join(work, "bin")
    os.makedirs(bindir, exist_ok=True)
    with open(os.path.join(bindir, "gh"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(GH_STUB)
    os.chmod(os.path.join(bindir, "gh"), 0o755)
    calls = os.path.join(work, "gh_calls")
    open(calls, "w").close()
    last_comment = os.path.join(work, "gh_last_comment.md")
    open(last_comment, "w").close()
    return bindir, calls, last_comment


def run_decide(subject, root, jobs_json, run_json, extra_env):
    work = tempfile.mkdtemp(dir=root)
    runner_temp = os.path.join(work, "runner_temp")
    os.makedirs(runner_temp, exist_ok=True)
    bindir, calls, last_comment = new_gh_stub(work)
    path = bindir + os.pathsep + os.environ["PATH"]

    jobs_json_file = os.path.join(work, "jobs.json")
    with open(jobs_json_file, "w", encoding="utf-8") as fh:
        fh.write(jobs_json)
    run_json_file = os.path.join(work, "run.json")
    with open(run_json_file, "w", encoding="utf-8") as fh:
        fh.write(run_json)

    env = {
        "GH_TOKEN": "x", "ISSUE_TOKEN": "y", "GITHUB_REPOSITORY": "o/r",
        "RUN_ID": "555000111", "CONCLUSION": "cancelled",
        "SPEC_DIR": "specs/999-fixture", "ISSUE": "123",
        "IMPLEMENT_WORKFLOW": "wing-commander-5-implement.yml",
        "DRY_RUN": "false",
        "GH_CALLS": calls, "GH_LAST_COMMENT": last_comment,
        "GH_JOBS_JSON": jobs_json_file, "GH_RUN_JSON": run_json_file,
        "PATH": path,
    }
    env.update(extra_env)
    return run_step(BASH, subject["decide:run"], work, env, runner_temp)


NEVER_STARTED_JOBS = '{"jobs": [{"started_at": null}, {"started_at": null}]}'
RAN_THEN_CANCELLED_JOBS = ('{"jobs": [{"started_at": "2026-01-01T00:00:00Z"}, '
                          '{"started_at": null}]}')
RUN_JSON = '{"updated_at": "2026-01-01T00:05:00Z"}'
CORRELATED_PEEK = "head-granted-at=2026-01-01T00:03:00Z"
UNCORRELATED_PEEK = "head-granted-at="
ROUND_OUT_FRESH = "round=7\nredispatch-count=0\niteration=3"
ROUND_OUT_ALREADY_REDISPATCHED = "round=7\nredispatch-count=1\niteration=3"


def scenario_guard_classification(subject, root):
    failures = []

    rc, out, outputs, _ = run_decide(
        subject, root, NEVER_STARTED_JOBS, RUN_JSON,
        {"PEEK_OUT": CORRELATED_PEEK, "ROUND_OUT": ROUND_OUT_FRESH})
    if rc != 0:
        failures.append(f"scenario 7 (correlated): decide exited {rc}: {out.strip()}")
    elif outputs.get("should-attempt-redispatch") != "true":
        failures.append(f"scenario 7 (correlated): expected "
                        f"should-attempt-redispatch=true, "
                        f"outputs={outputs!r}")
    elif outputs.get("round") != "7" or outputs.get("iteration") != "3":
        failures.append(f"scenario 7 (correlated): round/iteration not "
                        f"carried through from ROUND_OUT: {outputs!r}")

    rc, out, outputs, _ = run_decide(
        subject, root, NEVER_STARTED_JOBS, RUN_JSON,
        {"PEEK_OUT": UNCORRELATED_PEEK, "ROUND_OUT": ROUND_OUT_FRESH})
    if rc != 0:
        failures.append(f"scenario 7 (uncorrelated): decide exited {rc}: {out.strip()}")
    elif outputs.get("action-taken") != "none":
        failures.append(f"scenario 7 (uncorrelated): expected "
                        f"action-taken=none (research.md D7's silent "
                        f"default), got {outputs!r}")

    rc, out, outputs, _ = run_decide(
        subject, root, RAN_THEN_CANCELLED_JOBS, RUN_JSON,
        {"PEEK_OUT": CORRELATED_PEEK, "ROUND_OUT": ROUND_OUT_FRESH})
    if rc != 0:
        failures.append(f"scenario 7 (ran then cancelled): decide exited "
                        f"{rc}: {out.strip()}")
    elif outputs.get("action-taken") != "none":
        failures.append(f"scenario 7 (ran then cancelled): expected "
                        f"action-taken=none (FR-013's manual-cancel "
                        f"silence, unchanged), got {outputs!r}")
    return failures


def scenario_redispatch_claim_enqueues_ticket(subject, root):
    """Scenario 9 (T038): a winning claim-redispatch call enqueues a fresh
    implement-kind ticket atomically with the redispatch_count CAS and
    returns its token, so the react step has a real ticket to thread onto
    its re-dispatch -- not just a returned string with nothing behind it."""
    failures = []
    remote = new_bare_remote(root)
    spec = "specs/999-fixture"
    run_ledger(LEDGER_SH, "enqueue", remote,
              {"SPEC_DIR": spec, "KIND": "act", "RUN_ID": "700"})
    run_ledger(LEDGER_SH, "release", remote,
              {"SPEC_DIR": spec, "TOKEN": "run-700-act", "RUN_ID": "700",
               "OUTCOME": "folded", "COMMIT_SHA": "cafe", "LEG_ID": "leg-1",
               "SUMMARY": "s"})

    proc = run_ledger(LEDGER_SH, "claim-redispatch", remote,
                      {"SPEC_DIR": spec, "ROUND": "1", "RUN_ID": "900"})
    result = parse_kv(proc.stdout)
    if result.get("should-redispatch") != "true":
        failures.append(f"scenario 9: winning claim-redispatch resolved "
                        f"should-redispatch={result.get('should-redispatch')!r}; "
                        f"expected 'true'. stderr: {proc.stderr.strip()}")
    if result.get("implement-token") != "run-900-implement":
        failures.append(f"scenario 9: winning claim-redispatch's "
                        f"implement-token is "
                        f"{result.get('implement-token')!r}, expected "
                        f"'run-900-implement'")

    peek_proc = run_ledger(LEDGER_SH, "peek", remote,
                           {"SPEC_DIR": spec, "PEEK_TOKEN": "run-900-implement"})
    peek_result = parse_kv(peek_proc.stdout)
    if peek_result.get("granted") != "true":
        failures.append(f"scenario 9: claim-redispatch reported "
                        f"implement-token=run-900-implement but the ledger "
                        f"shows it was never actually enqueued/granted: "
                        f"{peek_result!r}")

    needle = '-f fold_queue_token="$implement_token"'
    if needle not in subject["react:run"]:
        failures.append("scenario 9: react's gh workflow run call does not "
                        "thread a fold_queue_token -- the redispatched "
                        "implement.yml run would re-enter the concurrency "
                        "group unticketed (the T038 defect)")
    return failures


def scenario_redispatch_bound(subject, root):
    failures = []
    rc, out, outputs, _ = run_decide(
        subject, root, NEVER_STARTED_JOBS, RUN_JSON,
        {"PEEK_OUT": CORRELATED_PEEK, "ROUND_OUT": ROUND_OUT_ALREADY_REDISPATCHED})
    if rc != 0:
        failures.append(f"scenario 8: decide exited {rc}: {out.strip()}")
    elif outputs.get("action-taken") != "notice-only":
        failures.append(f"scenario 8: a round already at "
                        f"redispatch_count=1 must resolve action-taken="
                        f"notice-only, never attempt a second redispatch "
                        f"(FR-016a); got {outputs!r}")
    elif outputs.get("should-attempt-redispatch") == "true":
        failures.append("scenario 8: should-attempt-redispatch=true despite "
                        "redispatch_count already being 1")
    return failures


# --------------------------------------------------------------------------
# suite()
# --------------------------------------------------------------------------
def suite(subject, root):
    failures = []
    failures += scenario_single_run_no_contention(subject)
    failures += scenario_two_overlapping(subject)
    failures += scenario_three_overlapping(subject)
    failures += scenario_ticket_jobs_carry_no_concurrency_group(subject)
    failures += scenario_stop_only(subject)
    failures += scenario_dispatch_while_outstanding(subject, root)
    failures += scenario_dispatch_after_round_empties(subject, root)
    failures += scenario_guard_classification(subject, root)
    failures += scenario_redispatch_bound(subject, root)
    failures += scenario_redispatch_claim_enqueues_ticket(subject, root)
    failures += scenario_no_own_folds_never_wins(subject, root)
    failures += scenario_requeue_behind_outstanding_then_wins(subject, root)
    failures += scenario_won_reply_names_every_contributing_run(subject, root)
    failures += scenario_standalone_never_enqueues_implement_ticket(subject, root)
    failures += scenario_idempotent_win_retry(subject, root)
    return failures


# --------------------------------------------------------------------------
# Mutations (FR-022)
# --------------------------------------------------------------------------
def mut_drop_fold_turn_needs(subject):
    s = dict(subject)
    s["act:needs"] = [n for n in subject["act:needs"] if n != "fold-turn-act"]
    s["dispatch-once:needs"] = [n for n in subject["dispatch-once:needs"]
                                if n != "fold-turn-dispatch"]
    s["implement:needs"] = [n for n in subject["implement:needs"]
                            if n != "fold-turn-implement"]
    return s


def mut_unconditional_dispatch(subject):
    """Removes the round-emptiness check from claim-dispatch's own jq
    filter -- a claim with own folds and an outstanding act-kind ticket
    would win immediately instead of requeuing (dispatch-once would fire
    once per run again, not once per round)."""
    s = dict(subject)
    needle = "elif ($round_empty | not) then"
    replacement = "elif false then"
    if needle not in subject["ledger:text"]:
        return s
    s["ledger:text"] = subject["ledger:text"].replace(needle, replacement)
    return s


def mut_collapse_manual_and_replaced(subject):
    s = dict(subject)
    needle = "correlated=false"
    replacement = "correlated=true"
    if needle not in subject["decide:run"]:
        return s
    s["decide:run"] = subject["decide:run"].replace(needle, replacement)
    return s


def mut_unbounded_redispatch(subject):
    s = dict(subject)
    needle = 'if [ "$redispatch_count" = "1" ]; then'
    replacement = 'if false; then'
    if needle not in subject["decide:run"]:
        return s
    s["decide:run"] = subject["decide:run"].replace(needle, replacement)
    return s


def mut_redispatch_no_enqueue(subject):
    s = dict(subject)
    needle = ('.specs[$spec].queue += [{"token": $impl_token, "kind": '
              '"implement", "run_id": $run_id, "enqueued_at": $now, '
              '"granted_at": null}]')
    replacement = "."
    if needle not in subject["ledger:text"]:
        return s
    s["ledger:text"] = subject["ledger:text"].replace(needle, replacement)
    return s


def mut_drop_redispatch_token_thread(subject):
    s = dict(subject)
    needle = ' -f fold_queue_token="$implement_token"'
    replacement = ""
    if needle not in subject["react:run"]:
        return s
    s["react:run"] = subject["react:run"].replace(needle, replacement)
    return s


def mut_requeue_replaced_by_stepaside(subject):
    """2026-09-29 reconciliation with spec 075: a folding run facing an
    outstanding act-kind ticket must requeue and re-attempt, never step
    aside for a later run to win by default. Reverts the requeue branch to
    a plain decline with no queue mutation -- the exact shape a maintainer
    reviewing a diff might mistake for a harmless simplification."""
    s = dict(subject)
    needle = '| { changed: true, ledger: ., result: { "should-dispatch": "false", outcome: "requeued" } }'
    replacement = '| { changed: false, ledger: ., result: { "should-dispatch": "false", outcome: "declined" } }'
    if needle not in subject["ledger:text"]:
        return s
    s["ledger:text"] = subject["ledger:text"].replace(needle, replacement)
    return s


def mut_own_folds_check_dropped(subject):
    """spec 075 FR-014, reconciled 2026-09-29: a run with no folds of its
    own must never win. Disables the own-folds gate so a no-fold run can
    fall through to the round-emptiness/unclaimed checks and win."""
    s = dict(subject)
    needle = "if ($own_folds == 0) then"
    replacement = "if false then"
    if needle not in subject["ledger:text"]:
        return s
    s["ledger:text"] = subject["ledger:text"].replace(needle, replacement)
    return s


def mut_round_list_narrowed_to_claimant(subject):
    """2026-09-29 reconciliation with spec 075: the winning reply must name
    every contributing run's folds, not only the claimant's own. Narrows
    the winning claim's folded-items back to the claimant's own run_id."""
    s = dict(subject)
    needle = '"folded-items": (.specs[$spec].rounds[$round].folded_items // [] | tojson),'
    replacement = '"folded-items": (.specs[$spec].rounds[$round].folded_items // [] | map(select(.run_id == $run_id)) | tojson),'
    if needle not in subject["ledger:text"]:
        return s
    s["ledger:text"] = subject["ledger:text"].replace(needle, replacement)
    return s


def mut_standalone_still_enqueues(subject):
    """T046: implement-configured must gate the implement-kind ticket
    enqueue. Forces the enqueue branch unconditionally, as if
    implement-configured were always "true"."""
    s = dict(subject)
    needle = 'if $implement_configured == "true" then\n             .specs[$spec].queue = ([.specs[$spec].queue[0]] + [{"token": $impl_token, "kind": "implement", "run_id": $run_id, "enqueued_at": $now, "granted_at": null}] + .specs[$spec].queue[1:])\n           else\n             .\n           end'
    replacement = '.specs[$spec].queue = ([.specs[$spec].queue[0]] + [{"token": $impl_token, "kind": "implement", "run_id": $run_id, "enqueued_at": $now, "granted_at": null}] + .specs[$spec].queue[1:])'
    if needle not in subject["ledger:text"]:
        return s
    s["ledger:text"] = subject["ledger:text"].replace(needle, replacement)
    return s


def mut_ticket_job_gains_concurrency_group(subject):
    """T061 (B9): simulates the regression item 1's own fix removed --
    fold-turn-dispatch (or either sibling) gaining a concurrency: block of
    its own, which would silently reopen T045's exact deadlock (a wait
    for a ticket to clear, running inside the very group that ticket's
    owning run cannot itself join)."""
    s = dict(subject)
    s["fold-turn-dispatch:has-concurrency"] = True
    return s


def mut_win_retry_declines(subject):
    """T050: a retry of a dispatch token that already won must resolve won
    again. Reverts the idempotent-retry branch to a plain decline."""
    s = dict(subject)
    needle = (
        'if ((.specs[$spec].rounds[$round].dispatch_claimed_by // null) == $run_id) then\n'
        '          ((.specs[$spec].queue | map(select(.kind == "implement" and .run_id == $run_id)) | .[0].token) // "") as $existing_impl_token\n'
        '          | {\n'
        '              changed: false,\n'
        '              ledger: .,\n'
        '              result: {\n'
        '                "should-dispatch": "true",\n'
        '                outcome: "won",\n'
        '                "implement-token": $existing_impl_token,\n'
        '                "iteration": (.specs[$spec].rounds[$round].iteration | tostring),\n'
        '                "folded-items": (.specs[$spec].rounds[$round].folded_items // [] | tojson),\n'
        '                "not-folded-items": (.specs[$spec].rounds[$round].not_folded_items // [] | tojson)\n'
        '              }\n'
        '            }\n'
        '        else\n'
        '          { changed: false, ledger: ., result: { "should-dispatch": "false", outcome: "declined" } }\n'
        '        end'
    )
    replacement = '{ changed: false, ledger: ., result: { "should-dispatch": "false", outcome: "declined" } }'
    if needle not in subject["ledger:text"]:
        return s
    s["ledger:text"] = subject["ledger:text"].replace(needle, replacement)
    return s


def mut_drop_stop_only_handling(subject):
    """T054 (B2): reverts fold-turn-act/fold-turn-dispatch to admitting a
    ticket even for a stop-only run, and act/dispatch-once to requiring a
    bare 'success' result from them -- the defect restored: a stop-only
    run queues behind the very run it was asked to cancel (FR-005/SC-009)."""
    s = dict(subject)
    admit_needle = re.compile(
        r"\s*&&\s*needs\.classify-and-announce\.outputs\.stop-only != 'true'")
    s["fold-turn-act:if"] = admit_needle.sub("", subject["fold-turn-act:if"], count=1)
    s["fold-turn-dispatch:if"] = admit_needle.sub(
        "", subject["fold-turn-dispatch:if"], count=1)
    accept_act = re.compile(
        r"\(needs\.fold-turn-act\.result == 'success' \|\|"
        r"\s*\(needs\.fold-turn-act\.result == 'skipped' && "
        r"needs\.classify-and-announce\.outputs\.stop-only == 'true'\)\)")
    s["act:if"] = accept_act.sub(
        "needs.fold-turn-act.result == 'success'", subject["act:if"])
    accept_dispatch = re.compile(
        r"\(needs\.fold-turn-dispatch\.result == 'success' \|\|"
        r"\s*\(needs\.fold-turn-dispatch\.result == 'skipped' && "
        r"needs\.classify-and-announce\.outputs\.stop-only == 'true'\)\)")
    s["dispatch-once:if"] = accept_dispatch.sub(
        "needs.fold-turn-dispatch.result == 'success'", subject["dispatch-once:if"])
    return s


MUTATIONS = [
    ("fold-turn-* prerequisite dropped from needs:", mut_drop_fold_turn_needs),
    ("claim-dispatch's round-emptiness check removed", mut_unconditional_dispatch),
    ("decide's correlated-entrant check collapsed to always-true", mut_collapse_manual_and_replaced),
    ("decide's redispatch_count bound removed", mut_unbounded_redispatch),
    ("claim-redispatch's implement-ticket enqueue removed", mut_redispatch_no_enqueue),
    ("react's fold_queue_token thread dropped", mut_drop_redispatch_token_thread),
    ("claim-dispatch's requeue replaced by a step-aside decline", mut_requeue_replaced_by_stepaside),
    ("claim-dispatch's own-folds check dropped", mut_own_folds_check_dropped),
    ("winning claim's round list narrowed to the claimant's own folds", mut_round_list_narrowed_to_claimant),
    ("standalone mode still enqueues an implement ticket", mut_standalone_still_enqueues),
    ("a retried win declines instead of winning again", mut_win_retry_declines),
    ("stop-only skip-and-accept handling reverted", mut_drop_stop_only_handling),
    ("a ticket job (fold-turn-dispatch) gains a concurrency: group", mut_ticket_job_gains_concurrency_group),
]


def _apply_ledger_mutation(subject, root):
    """A mutated ledger:text needs its own temp file on disk so run_ledger
    (which invokes `bash <path> claim-dispatch`) can execute it -- returns
    the path to use in place of LEDGER_SH, or LEDGER_SH itself if unchanged."""
    if subject["ledger:text"] == open(LEDGER_SH, encoding="utf-8").read():
        return LEDGER_SH
    path = os.path.join(tempfile.mkdtemp(dir=root), "fold-queue-ledger.sh")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(subject["ledger:text"])
    return path


def suite_with_mutated_ledger(subject, root):
    """Same as suite(), but scenarios 4/5 run against subject['ledger:text']
    (possibly mutated) instead of the literal LEDGER_SH path."""
    global LEDGER_SH
    original = LEDGER_SH
    LEDGER_SH = _apply_ledger_mutation(subject, root)
    try:
        return suite(subject, root)
    finally:
        LEDGER_SH = original


def main():
    global BASH
    use_utf8_stdout()
    ensure_jq()
    BASH = resolve_bash()

    subject = load_expr_subject()
    root = tempfile.mkdtemp()
    try:
        failures = suite(subject, root)
        for f in failures:
            print(f"::error::{f}")

        mutation_failures = 0
        for label, mutate in MUTATIONS:
            mutated = mutate(subject)
            if mutated == subject:
                print(f"::error::mutation {label!r} changed nothing -- the "
                      f"text it targets has moved; update the mutation with it.")
                mutation_failures += 1
                continue
            broke = suite_with_mutated_ledger(mutated, root)
            if broke:
                print(f"Mutation OK -- {label}: {len(broke)} assertion(s) fail.")
            else:
                print(f"::error::MUTATION SURVIVED -- {label} broke nothing "
                      f"this gate checks.")
                mutation_failures += 1
    finally:
        import shutil
        shutil.rmtree(root, ignore_errors=True)

    print(f"Gate 128: 15 scenario(s), {len(MUTATIONS)} mutation(s); "
          f"{len(failures)} failure(s), {mutation_failures} mutation failure(s).")
    return 1 if failures or mutation_failures else 0


if __name__ == "__main__":
    sys.exit(main())
