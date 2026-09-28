#!/usr/bin/env python3
"""Gate 99 -- the fold-queue admission wiring actually serializes stage-9's
concurrency contenders and bounds fold-cycle-guard's automatic re-dispatch.

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
- `.github/actions/_shared/fold-queue-ledger.sh`'s `claim-dispatch`
  transform -- run directly against a throwaway local bare repository
  (`LEDGER_REMOTE_URL`, the same fixture convention
  `wing-commander-fold-queue-claim-dispatch/tests/run.sh` already uses; this
  gate's own value is proving MUTATIONS of that transform, which the manual
  quickstart drill does not).

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
6. A `stop`-only run (zero fold-route legs) -- `fold-turn-act`'s `if:`
   resolves false regardless of the image-prerequisites/classify result, so
   its steps (the only place `enqueue` is ever called) never run at all
   (FR-005/FR-017a).
7. `fold-cycle-guard`'s `decide` step: never-started + a correlated entrant
   -> proceeds toward redispatch; never-started + no correlated entrant ->
   `action-taken: none`; ran a step then was cancelled -> `action-taken:
   none` regardless of correlation (FR-012/FR-013).
8. Re-dispatch bound -- a round whose peeked `redispatch-count` is already
   `1` must resolve to a report-only outcome, never a second redispatch
   attempt (FR-016a).

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

`main()` runs `suite()` against the untouched subject (must be 0 failures),
then re-runs it under each mutation and requires a failure -- identical to
Gate 70's own `main()` shape (contracts/gates.md), including no separate
`--self-test` step: the mutations ARE this gate's self-test, in the same
single invocation.
"""
import os
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

    for key, val in subject.items():
        if key.endswith(":if") and not val.strip():
            sys.exit(f"::error::{key} has no if: -- nothing to evaluate. "
                     f"Removing a guard is the regression this gate exists for.")

    decide = find_step(GUARD, DECIDE_STEP_NAME)
    subject["decide:run"] = str(decide.get("run") or "")
    if not subject["decide:run"].strip():
        sys.exit(f"::error file={GUARD}::step {DECIDE_STEP_NAME!r} has no run: -- "
                 f"nothing to execute.")

    with open(LEDGER_SH, encoding="utf-8") as fh:
        subject["ledger:text"] = fh.read()

    return subject


# --------------------------------------------------------------------------
# pr-conversation.yml / implement.yml expression contexts
# --------------------------------------------------------------------------
def pr_ctx(legs='["leg-1"]', qualifies="true", fold_turn_act="success",
           fold_turn_dispatch="success"):
    return {
        "cancelled()": False,
        "always()": True,
        "needs.verify-image-prerequisites.result": "success",
        "needs.classify-and-announce.result": "success",
        "needs.classify-and-announce.outputs.qualifies": qualifies,
        "needs.classify-and-announce.outputs.legs": legs,
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


def scenario_stop_only(subject):
    failures = []
    for qualifies in ("true", "false"):
        ctx = pr_ctx(legs="[]", qualifies=qualifies)
        if truthy(evaluate(subject["fold-turn-act:if"], ctx)):
            failures.append(f"scenario 6: fold-turn-act:if ran for a "
                            f"stop-only review (legs=[], qualifies="
                            f"{qualifies}) -- it would enqueue a ticket for "
                            f"a run with nothing to fold (FR-005/FR-017a)")
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
    act-kind ticket still queued behind it must not be granted."""
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
                       "DISPATCH_TOKEN": "run-500-dispatch", "ITERATION": "2"})
    result = parse_kv(proc.stdout)
    if result.get("should-dispatch") != "false":
        failures.append(f"scenario 4: claim-dispatch resolved "
                        f"should-dispatch={result.get('should-dispatch')!r} "
                        f"while an act-kind ticket remained queued behind "
                        f"the dispatch ticket; expected 'false'. stderr: "
                        f"{proc.stderr.strip()}")
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
                       "DISPATCH_TOKEN": "run-600-dispatch", "ITERATION": "2"})
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
                        "DISPATCH_TOKEN": "run-601-dispatch", "ITERATION": "2"})
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
    failures += scenario_stop_only(subject)
    failures += scenario_dispatch_while_outstanding(subject, root)
    failures += scenario_dispatch_after_round_empties(subject, root)
    failures += scenario_guard_classification(subject, root)
    failures += scenario_redispatch_bound(subject, root)
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
    s = dict(subject)
    needle = "if ($round_empty and $unclaimed) then"
    replacement = "if ($unclaimed) then"
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


MUTATIONS = [
    ("fold-turn-* prerequisite dropped from needs:", mut_drop_fold_turn_needs),
    ("claim-dispatch's round-emptiness check removed", mut_unconditional_dispatch),
    ("decide's correlated-entrant check collapsed to always-true", mut_collapse_manual_and_replaced),
    ("decide's redispatch_count bound removed", mut_unbounded_redispatch),
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

    print(f"Gate 99: 8 scenario(s), {len(MUTATIONS)} mutation(s); "
          f"{len(failures)} failure(s), {mutation_failures} mutation failure(s).")
    return 1 if failures or mutation_failures else 0


if __name__ == "__main__":
    sys.exit(main())
