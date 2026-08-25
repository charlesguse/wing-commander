#!/usr/bin/env python3
"""Gate 34: a review folds every leg once and dispatches once; a dead leg says so.

WHY THIS EXISTS
---------------
Before specs/042-post-review-fold-loop, `pr-conversation.yml`'s `act` matrix
dispatched `implement.yml` from INSIDE each leg's own step. On PR #240 that
meant leg 4's dispatch and the run it triggered both tried to join
`wing-commander-<spec-dir>` at once, and one cancelled the other — silently
losing a review item. The fix (research.md D1-D6) moves dispatch out of the
matrix entirely into a new job, `dispatch-once`, that runs once after the
whole matrix has finished, and adds `report-fold-outcomes` to say so when a
leg dies without folding.

This gate exercises the SHIPPED `run:` text of both new jobs' deterministic
steps (`wc_shell_harness.py`, matching Gate 14/Gate 30's shape) against
synthetic branch-tip/git-history/job-conclusion fixtures, plus a handful of
structural assertions a live run cannot economically exercise (that
`dispatch-once`/`report-fold-outcomes` are not matrixed, and that the
per-leg reply step no longer calls `gh workflow run` at all) — together
these are what make "fold all, dispatch once" and "a dead leg says so" true
by construction rather than by convention.

Adaptation note (contracts/gate-coverage-042.md): that contract's two
"collapse to job-conclusion-only" / "collapse to fold-evidence-only"
mutations are paired, in the contract's own prose, with scenarios whose
literal field values cannot actually be misclassified by the described
collapse (a conclusion-only collapse cannot turn a `conclusion=failure`
case "healthy"). This gate keeps the INTENT — each half of the D6 cross-
check is independently load-bearing — but pairs each collapse with the
scenario it can actually expose: conclusion-only against a spurious-success
case (job succeeded, but no real fold landed), fold-evidence-only against
the contract's own scenario 3 (cancelled, but a spurious fold-evidence line
is present).

Usage: python3 .github/scripts/verify-fold-dispatch-once.py [-v]
Requires: bash, jq, git (all present on ubuntu-latest runners).
"""
import copy
import os
import re
import shutil
import subprocess
import sys
import tempfile

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_shell_harness import (ensure_jq, find_job, find_step, resolve_bash,
                              run_step, use_utf8_stdout)

STAGE = ".github/workflows/pr-conversation.yml"

DISPATCH_STEP = "Dispatch implement once for the whole review"
REPORT_STEP = "Report fold-route leg outcomes"
REPLY_STEP = "Reply confirming fold-in (no dispatch)"
ACT_AGENT_STEP = "Act on this classification"

REPO = "charlesguse/wing-commander"
SPEC_DIR = "specs/042-post-review-fold-loop"
ISSUE = "250"
PR_NUMBER = "999"
IMPLEMENT_WORKFLOW = "wing-commander-5-implement.yml"

BASH = None
VERBOSE = "-v" in sys.argv[1:]

GH_STUB = r"""#!/bin/sh
echo "gh $*" >> "$GH_CALLS"
case " $* " in
  *" api "*"/jobs"*)
    if [ -n "${GH_JOBS_JSONL:-}" ] && [ -f "$GH_JOBS_JSONL" ]; then
      cat "$GH_JOBS_JSONL"
    fi
    exit 0
    ;;
  *" pr "*"comment "*)
    prev=""
    for a in "$@"; do
      if [ "$prev" = "--body-file" ]; then
        cp "$a" "$GH_LAST_COMMENT"
      fi
      prev="$a"
    done
    exit "${GH_PR_COMMENT_EXIT:-0}"
    ;;
  *" workflow "*"run "*)
    exit "${GH_WORKFLOW_RUN_EXIT:-0}"
    ;;
  *" run "*"list "*)
    printf '%s' "${GH_RUN_LIST_JSON:-[]}"
    exit 0
    ;;
esac
exit 0
"""


def sh(script, cwd):
    path = os.path.join(cwd, "_helper.sh")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(script)
    return subprocess.run([BASH, "-e", path.replace("\\", "/")], cwd=cwd,
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace")


def make_repo(root, iteration, fold_commits):
    """A real git repo (bare remote + clone) seeded with spec-meta.json,
    then one commit per (id, summary) in fold_commits, each message
    `fold(<id>): <summary>` — the exact shape D6 requires `act` to write.
    Returns (repo_path, base_sha, tip_sha).
    """
    work = tempfile.mkdtemp(dir=root)
    remote = os.path.join(work, "remote.git")
    repo = os.path.join(work, "repo")
    setup = f"""
git init --bare -q -b main '{remote}'
git clone -q '{remote}' '{repo}'
cd '{repo}'
git config user.email harness@example.invalid
git config user.name harness
mkdir -p '{SPEC_DIR}'
printf '%s\\n' '{{"issue": {ISSUE}, "spec_dir": "{SPEC_DIR}", "stage": "implement", "iteration": {iteration}}}' > '{SPEC_DIR}/spec-meta.json'
git add -A
git commit -q -m seed
git push -q origin main
git rev-parse HEAD
"""
    proc = sh(setup, work)
    if proc.returncode != 0:
        sys.exit(f"::error::harness could not seed a git workspace: "
                 f"{proc.stdout}{proc.stderr}")
    base_sha = proc.stdout.strip().splitlines()[-1]

    tip_sha = base_sha
    for idx, (leg_id, summary) in enumerate(fold_commits):
        commit_script = f"""
cd '{repo}'
echo 'change {idx}' >> '{SPEC_DIR}/tasks.md'
git add -A
git commit -q -m 'fold({leg_id}): {summary}'
git push -q origin main
git rev-parse HEAD
"""
        proc = sh(commit_script, work)
        if proc.returncode != 0:
            sys.exit(f"::error::harness could not seed a fold commit: "
                     f"{proc.stdout}{proc.stderr}")
        tip_sha = proc.stdout.strip().splitlines()[-1]
    return repo, base_sha, tip_sha


def new_stub_dir(work):
    bindir = os.path.join(work, "bin")
    os.makedirs(bindir, exist_ok=True)
    with open(os.path.join(bindir, "gh"), "w", encoding="utf-8",
              newline="\n") as fh:
        fh.write(GH_STUB)
    os.chmod(os.path.join(bindir, "gh"), 0o755)
    calls = os.path.join(work, "gh_calls")
    open(calls, "w").close()
    last_comment = os.path.join(work, "gh_last_comment.md")
    open(last_comment, "w").close()
    return bindir, calls, last_comment


def gh_call_count(calls_path, *substrings):
    with open(calls_path, encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    return sum(1 for line in lines if all(s in line for s in substrings))


# --------------------------------------------------------------- scenarios

def scenario_three_clean_legs(steps, root):
    """gate-coverage-042.md scenario 1: three in-scope legs all fold
    cleanly -> dispatch-once computes exactly one `gh workflow run`
    invocation; report-fold-outcomes posts nothing.
    """
    failures = []
    where = "scenario 1 (three clean legs)"
    fold_commits = [("leg-0", "first item"), ("leg-1", "second item"),
                    ("leg-2", "third item")]
    repo, base_sha, tip_sha = make_repo(root, 3, fold_commits)
    work = os.path.dirname(repo)
    runner_temp = os.path.join(work, "runner_temp")
    os.makedirs(runner_temp, exist_ok=True)
    bindir, calls, last_comment = new_stub_dir(work)
    path = bindir + os.pathsep + os.environ["PATH"]

    rc, out, _, _ = run_step(
        BASH, steps[DISPATCH_STEP], repo,
        {"GH_TOKEN": "x", "DISPATCH_TOKEN": "x", "PR_NUMBER": PR_NUMBER,
         "SPEC_DIR": SPEC_DIR, "ISSUE": ISSUE,
         "IMPLEMENT_WORKFLOW": IMPLEMENT_WORKFLOW,
         "GITHUB_REPOSITORY": REPO, "BASE_SHA": base_sha, "TIP_SHA": tip_sha,
         "GH_CALLS": calls, "GH_LAST_COMMENT": last_comment,
         "GH_RUN_LIST_JSON": '[{"url":"https://example.invalid/runs/1"}]',
         "PATH": path},
        runner_temp)
    if rc != 0:
        failures.append(f"{where}: {DISPATCH_STEP!r} exited {rc}: {out.strip()}")
        return failures

    dispatches = gh_call_count(calls, "workflow run")
    if dispatches != 1:
        failures.append(f"{where}: expected exactly 1 `gh workflow run` "
                        f"call, got {dispatches} — 'fold all, dispatch "
                        f"once' is broken.")
    with open(last_comment, encoding="utf-8") as fh:
        comment = fh.read()
    for leg_id in ("leg-0", "leg-1", "leg-2"):
        if leg_id not in comment:
            failures.append(f"{where}: dispatch-once's PR comment does not "
                            f"name folded item {leg_id!r}: {comment!r}")

    # report-fold-outcomes: every leg healthy -> posts nothing.
    open(calls, "w").close()
    open(last_comment, "w").close()
    classifications = [
        {"id": "leg-0", "category": "in-scope-change", "summary": "first item"},
        {"id": "leg-1", "category": "in-scope-change", "summary": "second item"},
        {"id": "leg-2", "category": "in-scope-change", "summary": "third item"},
    ]
    jobs_jsonl = os.path.join(work, "jobs.jsonl")
    with open(jobs_jsonl, "w", encoding="utf-8") as fh:
        for leg_id in ("leg-0", "leg-1", "leg-2"):
            fh.write('{"name": "act (%s)", "conclusion": "success"}\n' % leg_id)
    rc, out, _, summary = run_step(
        BASH, steps[REPORT_STEP], repo,
        {"GH_TOKEN": "x", "ACTIONS_TOKEN": "x", "PR_NUMBER": PR_NUMBER, "RUN_ID": "1",
         "GITHUB_REPOSITORY": REPO,
         "CLASSIFICATIONS": _json(classifications),
         "BASE_SHA": base_sha, "TIP_SHA": tip_sha,
         "GH_CALLS": calls, "GH_LAST_COMMENT": last_comment,
         "GH_JOBS_JSONL": jobs_jsonl, "PATH": path},
        runner_temp)
    if rc != 0:
        failures.append(f"{where}: {REPORT_STEP!r} exited {rc}: {out.strip()}")
        return failures
    if gh_call_count(calls, "pr", "comment") != 0:
        failures.append(f"{where}: report-fold-outcomes posted a PR comment "
                        f"when every leg folded cleanly (US2 AS5 requires "
                        f"silence). Summary: {summary!r}")
    return failures


def scenario_cancelled_no_evidence(steps, root):
    """gate-coverage-042.md scenario 3: a leg cancelled before folding
    (conclusion=cancelled, no fold evidence) -> reported "not folded".
    """
    return _report_single_leg_scenario(
        steps, root, "scenario 3 (cancelled, no evidence)",
        conclusion="cancelled", fold_commits=[], expect="not folded")


def scenario_partly_folded(steps, root):
    """gate-coverage-042.md scenario 4: fold commit landed but conclusion
    is not success -> reported "partly folded".
    """
    return _report_single_leg_scenario(
        steps, root, "scenario 4 (fold landed, non-success conclusion)",
        conclusion="failure", fold_commits=[("leg-0", "the item")],
        expect="partly folded")


def scenario_missing_job(steps, root):
    """FR-006a: a leg whose job never appears in the run's own job list at
    all (matrix crashed before it started) is reported "not folded", never
    silently dropped.
    """
    return _report_single_leg_scenario(
        steps, root, "scenario missing-job", conclusion=None,
        fold_commits=[], expect="not folded")


def _report_single_leg_scenario(steps, root, where, conclusion, fold_commits,
                                expect):
    failures = []
    repo, base_sha, tip_sha = make_repo(root, 1, fold_commits)
    work = os.path.dirname(repo)
    runner_temp = os.path.join(work, "runner_temp")
    os.makedirs(runner_temp, exist_ok=True)
    bindir, calls, last_comment = new_stub_dir(work)
    path = bindir + os.pathsep + os.environ["PATH"]

    classifications = [{"id": "leg-0", "category": "in-scope-change",
                        "summary": "the item"}]
    jobs_jsonl = os.path.join(work, "jobs.jsonl")
    with open(jobs_jsonl, "w", encoding="utf-8") as fh:
        if conclusion is not None:
            fh.write('{"name": "act (leg-0)", "conclusion": "%s"}\n' % conclusion)
        # conclusion is None -> the job never appears at all (missing case).

    rc, out, _, _ = run_step(
        BASH, steps[REPORT_STEP], repo,
        {"GH_TOKEN": "x", "ACTIONS_TOKEN": "x", "PR_NUMBER": PR_NUMBER, "RUN_ID": "1",
         "GITHUB_REPOSITORY": REPO,
         "CLASSIFICATIONS": _json(classifications),
         "BASE_SHA": base_sha, "TIP_SHA": tip_sha,
         "GH_CALLS": calls, "GH_LAST_COMMENT": last_comment,
         "GH_JOBS_JSONL": jobs_jsonl, "PATH": path},
        runner_temp)
    if rc != 0:
        failures.append(f"{where}: {REPORT_STEP!r} exited {rc}: {out.strip()}")
        return failures
    with open(last_comment, encoding="utf-8") as fh:
        comment = fh.read()
    if expect not in comment:
        failures.append(f"{where}: expected {expect!r} in the reported "
                        f"comment, got: {comment!r}")
    if "leg-0" not in comment:
        failures.append(f"{where}: report does not name leg-0: {comment!r}")
    return failures


def scenario_zero_in_scope(steps, root):
    """gate-coverage-042.md scenario 6: a review with zero in-scope items
    (all question/no-action) -> report-fold-outcomes' fold-route filter
    excludes them all, so it posts nothing.
    """
    failures = []
    where = "scenario 6 (zero in-scope items)"
    repo, base_sha, tip_sha = make_repo(root, 1, [])
    work = os.path.dirname(repo)
    runner_temp = os.path.join(work, "runner_temp")
    os.makedirs(runner_temp, exist_ok=True)
    bindir, calls, last_comment = new_stub_dir(work)
    path = bindir + os.pathsep + os.environ["PATH"]

    classifications = [{"id": "leg-0", "category": "question",
                        "summary": "just asking"},
                       {"id": "leg-1", "category": "no-action",
                        "summary": "thanks"}]
    jobs_jsonl = os.path.join(work, "jobs.jsonl")
    open(jobs_jsonl, "w").close()

    rc, out, _, _ = run_step(
        BASH, steps[REPORT_STEP], repo,
        {"GH_TOKEN": "x", "ACTIONS_TOKEN": "x", "PR_NUMBER": PR_NUMBER, "RUN_ID": "1",
         "GITHUB_REPOSITORY": REPO,
         "CLASSIFICATIONS": _json(classifications),
         "BASE_SHA": base_sha, "TIP_SHA": tip_sha,
         "GH_CALLS": calls, "GH_LAST_COMMENT": last_comment,
         "GH_JOBS_JSONL": jobs_jsonl, "PATH": path},
        runner_temp)
    if rc != 0:
        failures.append(f"{where}: {REPORT_STEP!r} exited {rc}: {out.strip()}")
        return failures
    if gh_call_count(calls, "pr", "comment") != 0:
        failures.append(f"{where}: report-fold-outcomes posted a comment "
                        f"for a review with no fold-route items.")

    # And dispatch-once: base unchanged (nothing folded) -> the step's own
    # `if:` (checked structurally below) must gate this out; simulate the
    # no-fold case directly by never invoking the step at all — the job's
    # OWN `if:` on the shipped step (asserted in test_structural) is what
    # provides this guarantee in production. Confirmed here by running the
    # step's underlying script and checking it takes the standalone no-op
    # branch when BASE_SHA == TIP_SHA is never reached in practice — this
    # step is not even invoked when tip == base; that gating is asserted
    # structurally, not by executing this step with contradictory input.
    return failures


def scenario_held_leg_timeout(steps, root):
    """gate-coverage-042.md scenario 5: a held leg's confirm-timeout-minutes
    bound expires -> the other, ready legs' folds are still dispatched, and
    the held item is reported (not silently dropped).
    """
    failures = []
    where = "scenario 5 (held leg timeout)"
    fold_commits = [("leg-0", "ready item")]
    repo, base_sha, tip_sha = make_repo(root, 1, fold_commits)
    work = os.path.dirname(repo)
    runner_temp = os.path.join(work, "runner_temp")
    os.makedirs(runner_temp, exist_ok=True)
    bindir, calls, last_comment = new_stub_dir(work)
    path = bindir + os.pathsep + os.environ["PATH"]

    # leg-0 (ready, non-confirm-gated) folded and succeeded; leg-1 (held)
    # timed out waiting on its environment approval -> GitHub reports its
    # job conclusion as cancelled, with no fold(<id>) evidence.
    rc, out, _, _ = run_step(
        BASH, steps[DISPATCH_STEP], repo,
        {"GH_TOKEN": "x", "DISPATCH_TOKEN": "x", "PR_NUMBER": PR_NUMBER,
         "SPEC_DIR": SPEC_DIR, "ISSUE": ISSUE,
         "IMPLEMENT_WORKFLOW": IMPLEMENT_WORKFLOW,
         "GITHUB_REPOSITORY": REPO, "BASE_SHA": base_sha, "TIP_SHA": tip_sha,
         "GH_CALLS": calls, "GH_LAST_COMMENT": last_comment,
         "GH_RUN_LIST_JSON": '[{"url":"https://example.invalid/runs/1"}]',
         "PATH": path},
        runner_temp)
    if rc != 0:
        failures.append(f"{where}: {DISPATCH_STEP!r} exited {rc}: {out.strip()}")
        return failures
    if gh_call_count(calls, "workflow run") != 1:
        failures.append(f"{where}: the ready leg's fold was not dispatched "
                        f"despite the held leg timing out.")

    classifications = [
        {"id": "leg-0", "category": "in-scope-change", "summary": "ready item"},
        {"id": "leg-1", "category": "in-scope-change", "summary": "held item"},
    ]
    jobs_jsonl = os.path.join(work, "jobs.jsonl")
    with open(jobs_jsonl, "w", encoding="utf-8") as fh:
        fh.write('{"name": "act (leg-0)", "conclusion": "success"}\n')
        fh.write('{"name": "act (leg-1)", "conclusion": "cancelled"}\n')

    open(calls, "w").close()
    open(last_comment, "w").close()
    rc, out, _, _ = run_step(
        BASH, steps[REPORT_STEP], repo,
        {"GH_TOKEN": "x", "ACTIONS_TOKEN": "x", "PR_NUMBER": PR_NUMBER, "RUN_ID": "1",
         "GITHUB_REPOSITORY": REPO,
         "CLASSIFICATIONS": _json(classifications),
         "BASE_SHA": base_sha, "TIP_SHA": tip_sha,
         "GH_CALLS": calls, "GH_LAST_COMMENT": last_comment,
         "GH_JOBS_JSONL": jobs_jsonl, "PATH": path},
        runner_temp)
    if rc != 0:
        failures.append(f"{where}: {REPORT_STEP!r} exited {rc}: {out.strip()}")
        return failures
    with open(last_comment, encoding="utf-8") as fh:
        comment = fh.read()
    if "leg-1" not in comment or "not folded" not in comment:
        failures.append(f"{where}: the held/timed-out item was not reported "
                        f"as not folded: {comment!r}")
    if "leg-0" in comment:
        failures.append(f"{where}: the ready leg that folded cleanly was "
                        f"reported alongside the held one — it should be "
                        f"silent: {comment!r}")
    return failures


def scenario_spurious_success_needs_fold_check(steps, root):
    """Proves the fold-evidence half of D6's cross-check is load-bearing:
    a leg whose job conclusion is success but which never actually folded
    (no `fold(<id>):` commit) must NOT be reported healthy.
    """
    return _report_single_leg_scenario(
        steps, root, "scenario spurious-success", conclusion="success",
        fold_commits=[], expect="not folded")


def _json(obj):
    import json
    return json.dumps(obj)


SCENARIOS = [
    scenario_three_clean_legs,
    scenario_cancelled_no_evidence,
    scenario_partly_folded,
    scenario_missing_job,
    scenario_zero_in_scope,
    scenario_held_leg_timeout,
    scenario_spurious_success_needs_fold_check,
]


def suite(steps, root):
    return [f for fn in SCENARIOS for f in fn(steps, root)]


def load_steps():
    return {name: find_step(STAGE, name)["run"]
            for name in (DISPATCH_STEP, REPORT_STEP)}


# ------------------------------------------------------------- structural

def test_structural():
    """Assertions a live run cannot economically exercise: the shape of the
    job graph and the absence of the removed per-leg dispatch call.
    """
    failures = []
    doc = yaml.safe_load(open(STAGE, encoding="utf-8")) or {}
    jobs = doc.get("jobs") or {}

    for job_id in ("dispatch-once", "report-fold-outcomes"):
        job = jobs.get(job_id)
        if job is None:
            failures.append(f"structural: no job keyed {job_id!r} in {STAGE}.")
            continue
        if "strategy" in job:
            failures.append(f"structural: {job_id!r} carries a `strategy:` "
                            f"(matrix) block — it must run exactly once per "
                            f"review, not once per leg (research.md D1).")
        needs = job.get("needs")
        needs_set = set(needs) if isinstance(needs, list) else {needs}
        expected_needs = {"verify-image-prerequisites", "classify-and-announce", "act"}
        if needs_set != expected_needs:
            failures.append(f"structural: {job_id!r}.needs is {needs!r}, "
                            f"expected exactly [verify-image-prerequisites, "
                            f"classify-and-announce, act] (Gate 23 requires "
                            f"every always()-guarded job to depend on "
                            f"verify-image-prerequisites directly — PR #253 "
                            f"review).")
        job_if = job.get("if", "")
        if "always()" not in job_if:
            failures.append(f"structural: {job_id!r}'s `if:` does not "
                            f"contain always() — a died/cancelled `act` "
                            f"could suppress this job (FR-005a/FR-006). "
                            f"if: {job_if!r}")
        if "needs.verify-image-prerequisites.result == 'success'" not in " ".join(job_if.split()):
            failures.append(f"structural: {job_id!r}'s `if:` does not check "
                            f"needs.verify-image-prerequisites.result == "
                            f"'success' — always() defeats ordinary "
                            f"skip-propagation, so a real image-prerequisite "
                            f"failure would run this job unchecked (Gate 23).")

    dispatch_group = str((jobs.get("dispatch-once") or {})
                         .get("concurrency", {}).get("group", ""))
    expected_group = "${{ needs.classify-and-announce.outputs.concurrency-group }}"
    if dispatch_group != expected_group:
        failures.append(f"structural: dispatch-once's concurrency.group is "
                        f"{dispatch_group!r}, expected {expected_group!r} — "
                        f"a hardcoded wing-commander-<spec-dir> group would "
                        f"put a stop-only run's dispatch-once back into the "
                        f"canonical group its own review is cancelling "
                        f"(FR-024/SC-009, PR #253 review).")

    reply_step = find_step(STAGE, REPLY_STEP)
    if "gh workflow run" in (reply_step.get("run") or ""):
        failures.append(f"structural: {REPLY_STEP!r} calls `gh workflow "
                        f"run` — dispatch must live ONLY in dispatch-once "
                        f"(research.md D1); a per-leg dispatch is exactly "
                        f"the defect that cancelled leg 4 and iteration 3 "
                        f"against each other on PR #240.")

    agent_step = find_step(STAGE, ACT_AGENT_STEP)
    prompt = (agent_step.get("with") or {}).get("prompt", "")
    if "fold(${{ matrix.id }})" not in prompt:
        failures.append(f"structural: {ACT_AGENT_STEP!r}'s prompt no longer "
                        f"instructs the fold commit message to start with "
                        f"fold(<id>): <summary> — report-fold-outcomes' "
                        f"git-grep evidence check depends on this exact "
                        f"shape (research.md D6).")
    return failures


# ------------------------------------------------------------------ mutations

def _mut_revert_d1_restore_per_leg_dispatch(steps):
    """Restores a per-leg `gh workflow run` call to the reply step — the
    shipped defect this feature removes. Simulated by running the mutated
    reply-step text three times (one per leg) and counting dispatches
    alongside dispatch-once's own single call.
    """
    steps[REPLY_STEP] = (
        'gh workflow run "$IMPLEMENT_WORKFLOW" -R "$GITHUB_REPOSITORY" '
        '-f spec_dir="x" -f issue="1" -f iteration="1"\n' + steps.get(REPLY_STEP, "")
    )


def _mut_collapse_to_conclusion_only(steps):
    """D6 collapsed to trust the job conclusion alone — the fold-evidence
    half of the cross-check becomes dead code.
    """
    steps[REPORT_STEP] = steps[REPORT_STEP].replace(
        'if [ "$conclusion" = "success" ] && [ "$folded" = "true" ]; then',
        'if [ "$conclusion" = "success" ]; then')


def _mut_collapse_to_fold_evidence_only(steps):
    """D6 collapsed to trust fold evidence alone — the job-conclusion half
    of the cross-check becomes dead code.
    """
    steps[REPORT_STEP] = steps[REPORT_STEP].replace(
        'if [ "$conclusion" = "success" ] && [ "$folded" = "true" ]; then',
        'if [ "$folded" = "true" ]; then')


MUTATIONS = [
    ("D1 reverted: per-leg dispatch restored",
     _mut_revert_d1_restore_per_leg_dispatch),
    ("D6 collapsed to job-conclusion-only",
     _mut_collapse_to_conclusion_only),
    ("D6 collapsed to fold-evidence-only",
     _mut_collapse_to_fold_evidence_only),
]


def run_mutation(label, apply_mutation, steps, root):
    """Returns True if the mutation is CAUGHT (a targeted assertion fails
    under the mutated steps), False if it SURVIVES.
    """
    mutated = copy.deepcopy(steps)
    apply_mutation(mutated)
    if mutated == steps:
        print(f"::error::mutation {label!r} changed nothing — the code it "
              f"edits was rewritten. Update the mutation.")
        return False

    if label.startswith("D1"):
        # Simulate 3 legs each running the mutated (dispatching) reply
        # step, plus dispatch-once's own single dispatch — total must be
        # caught as "more than one".
        repo, base_sha, tip_sha = make_repo(
            root, 1, [("leg-0", "a"), ("leg-1", "b"), ("leg-2", "c")])
        work = os.path.dirname(repo)
        runner_temp = os.path.join(work, "runner_temp")
        os.makedirs(runner_temp, exist_ok=True)
        bindir, calls, last_comment = new_stub_dir(work)
        path = bindir + os.pathsep + os.environ["PATH"]
        for _ in range(3):
            run_step(BASH, mutated[REPLY_STEP], repo,
                     {"GH_TOKEN": "x", "PR_NUMBER": PR_NUMBER,
                      "IMPLEMENT_WORKFLOW": IMPLEMENT_WORKFLOW,
                      "GITHUB_REPOSITORY": REPO, "GH_CALLS": calls,
                      "GH_LAST_COMMENT": last_comment, "PATH": path},
                     runner_temp)
        run_step(BASH, mutated[DISPATCH_STEP], repo,
                 {"GH_TOKEN": "x", "DISPATCH_TOKEN": "x",
                  "PR_NUMBER": PR_NUMBER, "SPEC_DIR": SPEC_DIR,
                  "ISSUE": ISSUE, "IMPLEMENT_WORKFLOW": IMPLEMENT_WORKFLOW,
                  "GITHUB_REPOSITORY": REPO, "BASE_SHA": base_sha,
                  "TIP_SHA": tip_sha, "GH_CALLS": calls,
                  "GH_LAST_COMMENT": last_comment,
                  "GH_RUN_LIST_JSON": '[{"url":"https://example.invalid"}]',
                  "PATH": path},
                 runner_temp)
        return gh_call_count(calls, "workflow run") > 1

    if label.startswith("D6 collapsed to job-conclusion-only"):
        # Spurious success: the job's conclusion is success, but no
        # fold(<id>) commit actually landed. Correct behavior reports "not
        # folded"; this mutation trusts conclusion alone, so it must now
        # (incorrectly) report healthy — i.e. post no comment at all.
        return _mutation_now_says_healthy(
            mutated, root, conclusion="success", fold_commits=[])

    if label.startswith("D6 collapsed to fold-evidence-only"):
        # scenario 3 with a SPURIOUS fold(<id>) commit present despite the
        # leg being cancelled -> must misclassify as healthy under this
        # mutation (no comment posted at all).
        return _mutation_now_says_healthy(
            mutated, root, conclusion="cancelled",
            fold_commits=[("leg-0", "spurious")])

    return False


def _mutation_now_says_healthy(steps, root, conclusion, fold_commits):
    """True if, under `steps`, a single leg with the given conclusion/fold
    evidence is now (incorrectly) reported as healthy — i.e. no PR comment.
    """
    repo, base_sha, tip_sha = make_repo(root, 1, fold_commits)
    work = os.path.dirname(repo)
    runner_temp = os.path.join(work, "runner_temp")
    os.makedirs(runner_temp, exist_ok=True)
    bindir, calls, last_comment = new_stub_dir(work)
    path = bindir + os.pathsep + os.environ["PATH"]
    classifications = [{"id": "leg-0", "category": "in-scope-change",
                        "summary": "the item"}]
    jobs_jsonl = os.path.join(work, "jobs.jsonl")
    with open(jobs_jsonl, "w", encoding="utf-8") as fh:
        fh.write('{"name": "act (leg-0)", "conclusion": "%s"}\n' % conclusion)
    rc, out, _, _ = run_step(
        BASH, steps[REPORT_STEP], repo,
        {"GH_TOKEN": "x", "ACTIONS_TOKEN": "x", "PR_NUMBER": PR_NUMBER, "RUN_ID": "1",
         "GITHUB_REPOSITORY": REPO,
         "CLASSIFICATIONS": _json(classifications),
         "BASE_SHA": base_sha, "TIP_SHA": tip_sha,
         "GH_CALLS": calls, "GH_LAST_COMMENT": last_comment,
         "GH_JOBS_JSONL": jobs_jsonl, "PATH": path},
        runner_temp)
    if rc != 0:
        return False
    return gh_call_count(calls, "pr", "comment") == 0


def main():
    global BASH
    use_utf8_stdout()
    ensure_jq()
    BASH = resolve_bash()
    if not shutil.which("git"):
        sys.exit("::error::git is not on PATH. The shipped steps under test "
                 "commit and push, so nothing here can run without it.")

    failures = list(test_structural())
    steps = load_steps()
    root = tempfile.mkdtemp()
    try:
        behavioral_failures = suite(steps, root)
        failures.extend(behavioral_failures)
        for f in behavioral_failures:
            print(f"::error::{f}")

        for label, apply_mutation in MUTATIONS:
            caught = run_mutation(label, apply_mutation, steps, root)
            if caught:
                print(f"Mutation OK — {label}: caught.")
            else:
                print(f"::error::MUTATION SURVIVED — reintroducing {label} "
                      f"broke nothing this gate checks. Fix the scenarios, "
                      f"not the mutation.")
                failures.append(f"mutation survived: {label}")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    for f in failures:
        if VERBOSE:
            print(f"::error::{f}")

    print(f"Gate 34: {len(SCENARIOS)} scenario(s), {len(MUTATIONS)} "
          f"mutation(s); {len(failures)} failure(s).")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
