#!/usr/bin/env python3
"""A turn-exhausted cycle is carried forward only with positive evidence.

WHY THIS EXISTS
---------------
"Read back cycle outcome" used to see only success/failure: a cycle that ran
out of its turn budget was indistinguishable from a genuine error, so it took
the escalated-redo path and then, if that redo also ran out of turns, got
marked stalled — cold-restarting real, already-pushed work instead of
continuing it. This feature adds a third classification, "truncated",
collapsed onto the existing `ok` boolean so every downstream gate (the retry
step's `steps.outcome.outputs.ok == 'false'`, the `stalled` job's
`needs.implement.outputs.final-ok == 'false'`) already stops firing for it
without an edit — but ONLY when the lifecycle record actually advanced AND
the branch shows real progress (spec.md R1's blocking risk: a naive flip
would hand an unbuilt feature to finalization as "converged" the moment a
run happened to be cut off before writing its converge: commit).

WHAT THIS CHECKS
----------------
Drives the SHIPPED `run:` blocks of "Read back cycle outcome", "Read back
retry outcome", "Consolidate final outcome", "Record truncated-cycle count",
and "Dispatch next step" (via `find_step`, never a copy) against synthetic
git history — a real repo with a local bare remote, so the counter's
commit/push path executes for real — and a stubbed upstream verdict env var,
proving: an exhausted+advanced+progressed cycle carries forward
(ok=true, truncated=true) with convergence forced false WITHOUT ever running
the converge-commit scan (US1, US2); an exhausted cycle with no progress
beyond its own lifecycle-record advance still escalates exactly as today
(US3); a truncated retry is classified by the identical rule against its OWN
base, never the primary attempt's (US4, FR-016); the consecutive-truncation
counter increments and resets correctly (US5, FR-011); and the lifecycle
issue report names truncation without ever saying "failed" or showing an
empty remaining-work block (US5, FR-013/FR-014/FR-015).

Six mutations at the end reintroduce the forced-false rule, the no-progress
guard, either arm of the progress test, counting the lifecycle-record
advance itself as progress, and widening truncation to ordinary failures —
each independently must fail at least one scenario the unmutated suite
passes (FR-019) — plus a reflexive check that Gate 30 itself is still wired
into lint-workflows.yml (FR-020).

Usage: python3 .github/scripts/verify-truncated-cycle-carry-forward.py
Requires: bash, jq, git (all present on ubuntu-latest runners).
"""
import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_shell_harness import (ensure_jq, find_step, resolve_bash, run_step,
                              use_utf8_stdout)

STAGE = ".github/workflows/implement.yml"
LINT_WORKFLOW = ".github/workflows/lint-workflows.yml"
GATE_PREFIX = "Gate 30"
THIS_SCRIPT = ".github/scripts/verify-truncated-cycle-carry-forward.py"

CYCLE_STEP = "Read back cycle outcome"
RETRY_STEP = "Read back retry outcome"
FINAL_STEP = "Consolidate final outcome"
COUNT_STEP = "Record truncated-cycle count"
DISPATCH_STEP = "Dispatch next step"

SPEC_PREFIX = "spec/"
SLUG = "040-fixture"
SPEC_DIR = f"specs/{SLUG}"
ITERATION = "3"
PRIOR_ITERATION = "2"
PRIMARY_MODEL = "claude-sonnet-5"
ESCALATION_MODEL = "claude-opus-5"
BOT_SLUG = "wing-commander-bot"

BASH = None


def sh(script, cwd):
    """Run a helper snippet through the same bash the steps get.

    The script file itself must live OUTSIDE `cwd` — `cwd` is usually the
    git working tree under test, and a helper script written inside it would
    be swept up by the next `git add -A`, polluting the very commit history
    Arm B's "any file outside $SPEC_DIR changed" test reads.
    """
    fd, path = tempfile.mkstemp(suffix=".sh")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(script)
        return subprocess.run([BASH, "-e", path.replace("\\", "/")], cwd=cwd,
                              capture_output=True, text=True, encoding="utf-8",
                              errors="replace")
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def _tasks_md(checked, unchecked):
    lines = [f"- [x] T{i:03d} done" for i in range(checked)]
    lines += [f"- [ ] T{i:03d} todo" for i in range(checked, checked + unchecked)]
    return "\n".join(lines) + "\n"


def write_file(repo, relpath, content):
    path = os.path.join(repo, relpath)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(content)


def git_commit(repo, message):
    proc = sh(f"""cd '{repo}'
git add -A
git commit -q -m {json.dumps(message)}
""", repo)
    if proc.returncode != 0:
        sys.exit(f"::error::commit {message!r} failed: {proc.stdout}{proc.stderr}")


def git_push(repo, branch):
    proc = sh(f"cd '{repo}' && git push -q origin '{branch}'", repo)
    if proc.returncode != 0:
        sys.exit(f"::error::push of '{branch}' failed: {proc.stdout}{proc.stderr}")


def rev_parse(repo, rev="HEAD"):
    return sh(f"cd '{repo}' && git rev-parse {rev}", repo).stdout.strip()


def make_workspace(root, base_checked=0, base_unchecked=3,
                    prior_iteration=PRIOR_ITERATION):
    """A git repo + bare remote, seeded with one commit on the spec branch.

    Mirrors verify-stall-restart-runbook.py's make_workspace: a REAL bare
    remote so the counter step's commit/push path (research.md D5) executes
    for real rather than being asserted against a mocked git.
    """
    branch = f"{SPEC_PREFIX}{SLUG}"
    work = tempfile.mkdtemp(dir=root)
    remote = os.path.join(work, "remote.git")
    repo = os.path.join(work, "repo")
    setup = f"""
git init --bare -q -b main '{remote}'
git clone -q '{remote}' '{repo}'
cd '{repo}'
git config user.email harness@example.invalid
git config user.name harness
git checkout -q -b '{branch}'
"""
    proc = sh(setup, work)
    if proc.returncode != 0:
        sys.exit(f"::error::harness could not build a git workspace: "
                 f"{proc.stdout}{proc.stderr}")
    write_file(repo, f"{SPEC_DIR}/tasks.md", _tasks_md(base_checked, base_unchecked))
    write_file(repo, f"{SPEC_DIR}/spec-meta.json",
               json.dumps({"stage": "implement", "iteration": int(prior_iteration)}) + "\n")
    write_file(repo, "README.md", "unrelated\n")
    git_commit(repo, "seed")
    git_push(repo, branch)
    base_sha = rev_parse(repo)
    return work, repo, base_sha, branch


def build_scenario(root, *, tick_task=False, outside_file=False, advance=True,
                    converge=False, iteration=ITERATION, base_checked=0,
                    base_unchecked=3, prior_iteration=PRIOR_ITERATION):
    """One synthetic cycle's history on top of a fresh base commit."""
    work, repo, base_sha, branch = make_workspace(
        root, base_checked, base_unchecked, prior_iteration)
    checked, unchecked = base_checked, base_unchecked
    if tick_task:
        checked += 1
        unchecked = max(unchecked - 1, 0)
        write_file(repo, f"{SPEC_DIR}/tasks.md", _tasks_md(checked, unchecked))
        git_commit(repo, "implement: tick a task")
    if outside_file:
        write_file(repo, "src/feature.py", "feature\n")
        git_commit(repo, "implement: add feature file")
    if advance:
        write_file(repo, f"{SPEC_DIR}/spec-meta.json",
                   json.dumps({"stage": "implement", "iteration": int(iteration)}) + "\n")
        git_commit(repo, "implement: advance lifecycle record")
    if converge:
        content = _tasks_md(checked, unchecked) + "\n## Convergence Phase\n- [ ] C001 leftover item\n"
        write_file(repo, f"{SPEC_DIR}/tasks.md", content)
        git_commit(repo, "converge: add convergence phase")
    git_push(repo, branch)
    return work, repo, base_sha, branch


def run_cycle_step(steps, repo, base_sha, *, verdict, cycle_result,
                    iteration=ITERATION):
    runner_temp = tempfile.mkdtemp(dir=os.path.dirname(repo))
    env = {"SLUG": SLUG, "SPEC_DIR": SPEC_DIR, "ITERATION": str(iteration),
           "BASE_SHA": base_sha, "CYCLE_RESULT": cycle_result,
           "VERDICT": verdict, "SPEC_PREFIX": SPEC_PREFIX}
    return run_step(BASH, steps[CYCLE_STEP], repo, env, runner_temp)


def run_retry_step(steps, repo, base_sha, *, verdict, retry_result,
                    iteration=ITERATION):
    runner_temp = tempfile.mkdtemp(dir=os.path.dirname(repo))
    env = {"SLUG": SLUG, "SPEC_DIR": SPEC_DIR, "ITERATION": str(iteration),
           "BASE_SHA": base_sha, "RETRY_RESULT": retry_result,
           "VERDICT": verdict, "ESCALATION_MODEL": ESCALATION_MODEL,
           "SPEC_PREFIX": SPEC_PREFIX}
    return run_step(BASH, steps[RETRY_STEP], repo, env, runner_temp)


def run_final_step(steps, env_overrides, root):
    workdir = tempfile.mkdtemp(dir=root)
    runner_temp = os.path.join(workdir, "runner_temp")
    os.makedirs(runner_temp, exist_ok=True)
    env = {
        "RETRY_RAN": "false",
        "PRIMARY_OK": "true", "PRIMARY_TRUNCATED": "false",
        "PRIMARY_CONVERGED": "true", "PRIMARY_REMAINING": "",
        "PRIMARY_TIER": PRIMARY_MODEL,
        "RETRY_OK": "", "RETRY_TRUNCATED": "", "RETRY_CONVERGED": "",
        "RETRY_REMAINING": "",
        "PRIMARY_REASON": "", "RETRY_REASON": "",
        "ESCALATION_MODEL": ESCALATION_MODEL,
    }
    env.update(env_overrides)
    return run_step(BASH, steps[FINAL_STEP], workdir, env, runner_temp)


def make_count_workspace(root, starting_count):
    branch = f"{SPEC_PREFIX}{SLUG}"
    work, repo, _, _ = make_workspace(root, prior_iteration=ITERATION)
    write_file(repo, f"{SPEC_DIR}/spec-meta.json",
               json.dumps({"stage": "implement", "iteration": int(ITERATION),
                          "truncated_count": starting_count}) + "\n")
    git_commit(repo, "implement: seed truncated_count")
    git_push(repo, branch)
    return work, repo, branch


def run_count_step(steps, repo, truncated):
    runner_temp = tempfile.mkdtemp(dir=os.path.dirname(repo))
    env = {"SLUG": SLUG, "SPEC_DIR": SPEC_DIR, "SPEC_PREFIX": SPEC_PREFIX,
           "TRUNCATED": truncated, "BOT_SLUG": BOT_SLUG}
    return run_step(BASH, steps[COUNT_STEP], repo, env, runner_temp)


GH_STUB = """#!/bin/sh
orig="$*"
while [ "$#" -gt 0 ]; do
  if [ "$1" = "--body" ]; then
    printf '%s' "$2" > "$GH_BODY_FILE"
  fi
  shift
done
echo "gh $orig" >> "$GH_CALLS"
exit 0
"""


def run_dispatch_step(steps, env_overrides, root):
    workdir = tempfile.mkdtemp(dir=root)
    runner_temp = os.path.join(workdir, "runner_temp")
    bindir = os.path.join(workdir, "bin")
    body_file = os.path.join(workdir, "gh_body")
    calls_file = os.path.join(workdir, "gh_calls")
    os.makedirs(runner_temp, exist_ok=True)
    os.makedirs(bindir, exist_ok=True)
    open(body_file, "w").close()
    open(calls_file, "w").close()
    with open(os.path.join(bindir, "gh"), "w", encoding="utf-8",
              newline="\n") as fh:
        fh.write(GH_STUB)
    os.chmod(os.path.join(bindir, "gh"), 0o755)
    env = {
        "SPEC_DIR": SPEC_DIR, "ISSUE": "999", "ITERATION": "2", "MAX": "5",
        "CONVERGED": "false", "TRUNCATED": "false", "TRUNCATED_COUNT": "0",
        "TIER": PRIMARY_MODEL, "REMAINING": "",
        "SELF_WORKFLOW": "wing-commander-5-implement.yml", "NEXT_WORKFLOW": "",
        "APP_TOKEN": "x", "DISPATCH_TOKEN": "x",
        "GH_BODY_FILE": body_file, "GH_CALLS": calls_file,
        "GITHUB_SERVER_URL": "https://example.invalid",
        "GITHUB_REPOSITORY": "acme/repo", "GITHUB_RUN_ID": "1",
        "PATH": bindir + os.pathsep + os.environ["PATH"],
    }
    env.update(env_overrides)
    rc, out, outputs, summary = run_step(BASH, steps[DISPATCH_STEP], workdir,
                                         env, runner_temp)
    with open(body_file, encoding="utf-8") as fh:
        body = fh.read()
    with open(calls_file, encoding="utf-8") as fh:
        calls = fh.read()
    return rc, out, outputs, body, calls, summary


# ---------------------------------------------------------------------------
# Scenarios (contracts/truncated-cycle-coverage.md)
# ---------------------------------------------------------------------------

CYCLE_SCENARIOS = [
    dict(name="1: exhausted, Arm-A progress, no converge commit",
         tick_task=True, outside_file=False, advance=True, converge=False,
         verdict="exhausted", cycle_result="failure",
         expect=dict(ok="true", truncated="true", converged="false")),
    dict(name="2: exhausted, only the lifecycle-record advance landed",
         tick_task=False, outside_file=False, advance=True, converge=False,
         verdict="exhausted", cycle_result="failure",
         expect=dict(ok="false", truncated="false", converged="")),
    dict(name="3: exhausted, Arm-A-only progress",
         tick_task=True, outside_file=False, advance=True, converge=False,
         verdict="exhausted", cycle_result="failure",
         expect=dict(ok="true", truncated="true", converged="false")),
    dict(name="4: exhausted, Arm-B-only progress",
         tick_task=False, outside_file=True, advance=True, converge=False,
         verdict="exhausted", cycle_result="failure",
         expect=dict(ok="true", truncated="true", converged="false")),
    dict(name="5: ordinary failure, no progress at all",
         tick_task=False, outside_file=False, advance=False, converge=False,
         verdict="failed", cycle_result="failure",
         expect=dict(ok="false", truncated="false", converged="")),
    dict(name="5b: ordinary failure with incidental progress markers",
         tick_task=True, outside_file=False, advance=True, converge=False,
         verdict="failed", cycle_result="failure",
         expect=dict(ok="false", truncated="false", converged="")),
    dict(name="6a: normal successful cycle, no converge commit (converged)",
         tick_task=True, outside_file=False, advance=True, converge=False,
         verdict="healthy", cycle_result="success",
         expect=dict(ok="true", truncated="false", converged="true")),
    dict(name="6b: normal successful cycle, converge commit present (not yet converged)",
         tick_task=True, outside_file=False, advance=True, converge=True,
         verdict="healthy", cycle_result="success",
         expect=dict(ok="true", truncated="false", converged="false")),
    dict(name="US2: exhausted with progress, but a converge: commit is ALSO "
              "present (cut off after its convergence pass ran) — the scan "
              "must be skipped entirely, not run and overridden",
         tick_task=True, outside_file=False, advance=True, converge=True,
         verdict="exhausted", cycle_result="failure",
         expect=dict(ok="true", truncated="true", converged="false")),
]

SCENARIOS_BY_NAME = {s["name"]: s for s in CYCLE_SCENARIOS}


def run_cycle_scenario(steps, scenario, root):
    """(rc, out, outputs, failures) for one CYCLE_SCENARIOS entry."""
    work, repo, base_sha, _ = build_scenario(
        root, tick_task=scenario["tick_task"], outside_file=scenario["outside_file"],
        advance=scenario["advance"], converge=scenario["converge"])
    rc, out, outputs, summary = run_cycle_step(
        steps, repo, base_sha, verdict=scenario["verdict"],
        cycle_result=scenario["cycle_result"])
    failures = []
    where = scenario["name"]
    if rc != 0:
        failures.append(f"{where}: {CYCLE_STEP!r} exited {rc}: {out.strip()}")
        return rc, out, outputs, failures
    for key, want in scenario["expect"].items():
        got = outputs.get(key, "")
        if got != want:
            failures.append(f"{where}: expected {key}={want!r}, got {got!r}")
    return rc, out, outputs, failures


def suite_cycle(steps, root):
    failures = []
    for scenario in CYCLE_SCENARIOS:
        _, _, _, f = run_cycle_scenario(steps, scenario, root)
        failures.extend(f)
    return failures


# ---------------------------------------------------------------------------
# US4 — the retry, when it itself truncates, is classified by the identical
# rule against ITS OWN base (research.md D7, FR-016) — not the primary
# attempt's base, which would let the retry inherit the primary's partial
# progress even if the retry itself achieved nothing.
# ---------------------------------------------------------------------------

def build_retry_scenario(root, *, retry_tick_task, retry_outside_file,
                          retry_advance=True):
    """Primary attempt ticks ONE task and fails to advance (hence a retry
    fires); the retry's own base is the tip AFTER that partial push. The
    retry's own commits are layered on top of that.
    """
    work, repo, base_sha, branch = make_workspace(root, 0, 3)
    write_file(repo, f"{SPEC_DIR}/tasks.md", _tasks_md(1, 2))
    git_commit(repo, "implement: primary partial progress")
    git_push(repo, branch)
    retry_base_sha = rev_parse(repo)
    if retry_tick_task:
        write_file(repo, f"{SPEC_DIR}/tasks.md", _tasks_md(2, 1))
        git_commit(repo, "implement: retry ticks another task")
    if retry_outside_file:
        write_file(repo, "src/feature.py", "feature\n")
        git_commit(repo, "implement: retry adds feature file")
    if retry_advance:
        write_file(repo, f"{SPEC_DIR}/spec-meta.json",
                   json.dumps({"stage": "implement", "iteration": int(ITERATION)}) + "\n")
        git_commit(repo, "implement: retry advances lifecycle record")
    git_push(repo, branch)
    return work, repo, base_sha, retry_base_sha, branch


def check_retry_no_own_progress(root):
    """FR-016: a retry that itself achieves nothing must NOT be carried
    forward, even though the primary attempt DID make partial progress —
    proving the base used is the retry's own, not the original.
    """
    failures = []
    _, repo, base_sha, retry_base_sha, _ = build_retry_scenario(
        root, retry_tick_task=False, retry_outside_file=False)
    steps = {RETRY_STEP: STEPS_CACHE[RETRY_STEP]}
    rc, out, outputs, _ = run_retry_step(
        steps, repo, retry_base_sha, verdict="exhausted", retry_result="failure")
    where = "retry with no progress of its own (measured against retry-base)"
    if rc != 0:
        failures.append(f"{where}: exited {rc}: {out.strip()}")
    else:
        if outputs.get("ok") != "false" or outputs.get("truncated") != "false":
            failures.append(
                f"{where}: expected ok=false/truncated=false (the retry's own "
                f"delta shows no progress), got ok={outputs.get('ok')!r}, "
                f"truncated={outputs.get('truncated')!r}")

    # Demonstrating WHY the base matters: feeding the ORIGINAL (pre-primary)
    # base to the identical, unmutated step text would wrongly show progress
    # (the primary attempt's own partial work), which is exactly the failure
    # mode research.md D7 requires "Read back retry outcome" to avoid by
    # reading steps.retry-base.outputs.base-sha, not steps.base.outputs.base-sha.
    rc2, out2, outputs2, _ = run_retry_step(
        steps, repo, base_sha, verdict="exhausted", retry_result="failure")
    if rc2 == 0 and outputs2.get("truncated") == "true":
        pass  # confirms the base choice is load-bearing; not itself a failure
    else:
        failures.append(
            "retry-base-matters sanity check: feeding the ORIGINAL base to "
            "the same step text unexpectedly did not show spurious progress "
            "— the demonstration that base choice matters no longer holds; "
            "update this check alongside the step.")
    return failures


def check_retry_with_own_progress(root):
    """FR-016: a retry that DOES make its own progress is carried forward,
    identically to the primary-cycle rule (US1 Scenario 1's shape, but for
    the retry step)."""
    failures = []
    _, repo, _, retry_base_sha, _ = build_retry_scenario(
        root, retry_tick_task=True, retry_outside_file=False)
    steps = {RETRY_STEP: STEPS_CACHE[RETRY_STEP]}
    rc, out, outputs, _ = run_retry_step(
        steps, repo, retry_base_sha, verdict="exhausted", retry_result="failure")
    where = "retry with its own progress (measured against retry-base)"
    if rc != 0:
        failures.append(f"{where}: exited {rc}: {out.strip()}")
        return failures
    for key, want in (("ok", "true"), ("truncated", "true"), ("converged", "false")):
        got = outputs.get(key, "")
        if got != want:
            failures.append(f"{where}: expected {key}={want!r}, got {got!r}")
    return failures


def check_final_selects_retry_truncated(root):
    """T008/T009: "Consolidate final outcome" selects the RETRY's truncated
    value when the retry ran, and the PRIMARY's when it did not — same
    selection rule already governing ok/converged/remaining/tier."""
    failures = []
    steps = {FINAL_STEP: STEPS_CACHE[FINAL_STEP]}
    rc, out, outputs, _ = run_final_step(steps, {
        "RETRY_RAN": "true", "PRIMARY_TRUNCATED": "false",
        "RETRY_TRUNCATED": "true", "RETRY_OK": "true", "RETRY_CONVERGED": "false",
    }, root)
    if rc != 0:
        failures.append(f"final(retry ran): exited {rc}: {out.strip()}")
    elif outputs.get("truncated") != "true" or outputs.get("tier") != ESCALATION_MODEL:
        failures.append(
            f"final(retry ran): expected truncated=true, tier={ESCALATION_MODEL!r} "
            f"(the retry's own values), got truncated={outputs.get('truncated')!r}, "
            f"tier={outputs.get('tier')!r}")

    rc2, out2, outputs2, _ = run_final_step(steps, {
        "RETRY_RAN": "false", "PRIMARY_TRUNCATED": "true", "PRIMARY_OK": "true",
        "PRIMARY_CONVERGED": "false",
    }, root)
    if rc2 != 0:
        failures.append(f"final(retry did not run): exited {rc2}: {out2.strip()}")
    elif outputs2.get("truncated") != "true" or outputs2.get("tier") != PRIMARY_MODEL:
        failures.append(
            f"final(retry did not run): expected truncated=true, "
            f"tier={PRIMARY_MODEL!r} (the primary's own values), got "
            f"truncated={outputs2.get('truncated')!r}, tier={outputs2.get('tier')!r}")
    return failures


# ---------------------------------------------------------------------------
# US5 — the consecutive-truncation counter and lifecycle-issue reporting
# ---------------------------------------------------------------------------

def check_counter(root):
    failures = []
    steps = {COUNT_STEP: STEPS_CACHE[COUNT_STEP]}

    _, repo1, _ = make_count_workspace(root, 1)
    rc, out, outputs, _ = run_count_step(steps, repo1, "true")
    if rc != 0:
        failures.append(f"counter(start=1, truncated=true): exited {rc}: {out.strip()}")
    elif outputs.get("count") != "2":
        failures.append(f"counter(start=1, truncated=true): expected count=2, "
                        f"got {outputs.get('count')!r}")

    _, repo2, _ = make_count_workspace(root, 2)
    rc2, out2, outputs2, _ = run_count_step(steps, repo2, "false")
    if rc2 != 0:
        failures.append(f"counter(start=2, truncated=false): exited {rc2}: {out2.strip()}")
    elif outputs2.get("count") != "0":
        failures.append(f"counter(start=2, truncated=false): expected count=0 "
                        f"(reset on completed/failed), got {outputs2.get('count')!r}")

    _, repo3, _ = make_count_workspace(root, 2)
    rc3, out3, outputs3, _ = run_count_step(steps, repo3, "true")
    if rc3 != 0:
        failures.append(f"counter(start=2, truncated=true): exited {rc3}: {out3.strip()}")
    elif outputs3.get("count") != "3":
        failures.append(f"counter(start=2, truncated=true): expected count=3 "
                        f"(a second consecutive truncation), got {outputs3.get('count')!r}")
    return failures


def check_reporting(root):
    failures = []
    steps = {DISPATCH_STEP: STEPS_CACHE[DISPATCH_STEP]}

    rc, out, outputs, body, calls, _ = run_dispatch_step(steps, {
        "TRUNCATED": "true", "ITERATION": "2", "MAX": "5",
        "TRUNCATED_COUNT": "3", "SELF_WORKFLOW": "wing-commander-5-implement.yml",
    }, root)
    where = "below-cap truncated report (FR-013, FR-015)"
    if rc != 0:
        failures.append(f"{where}: exited {rc}: {out.strip()}")
    else:
        if "failed" in body.lower():
            failures.append(f"{where}: body must never say 'failed': {body!r}")
        if "3" not in body:
            failures.append(f"{where}: body must carry the consecutive-"
                            f"truncation count (3): {body!r}")
        if "workflow run wing-commander-5-implement.yml" not in calls:
            failures.append(f"{where}: expected the next cycle to still be "
                            f"dispatched; gh calls were: {calls!r}")

    rc2, out2, outputs2, body2, calls2, _ = run_dispatch_step(steps, {
        "TRUNCATED": "true", "ITERATION": "5", "MAX": "5",
        "TRUNCATED_COUNT": "4", "NEXT_WORKFLOW": "wing-commander-6-finalize.yml",
    }, root)
    where2 = "at-cap truncated report (FR-014)"
    if rc2 != 0:
        failures.append(f"{where2}: exited {rc2}: {out2.strip()}")
    else:
        if "ran out of turns before it could assess what remained" not in body2:
            failures.append(f"{where2}: expected the 'ran out of turns before "
                            f"it could assess what remained' wording: {body2!r}")
        if "```markdown\n\n```" in body2 or "```markdown\n```" in body2:
            failures.append(f"{where2}: body presents an empty fenced "
                            f"remaining-work block: {body2!r}")
        if "workflow run wing-commander-6-finalize.yml" not in calls2:
            failures.append(f"{where2}: expected finalize to still be "
                            f"dispatched (converged=false); gh calls were: "
                            f"{calls2!r}")
    return failures


# ---------------------------------------------------------------------------
# US6 — mutations (FR-019) and the reflexive gate-wiring check (FR-020)
# ---------------------------------------------------------------------------

def _mut_remove_forced_false(steps):
    """Let the converge-commit scan run unconditionally instead of forcing
    converged=false on the truncated path (research.md D4's rejected shape)."""
    steps[CYCLE_STEP] = steps[CYCLE_STEP].replace(
        'if [ "$ok" = "true" ] && [ "$truncated" = "true" ]; then',
        'if false; then', 1)


def _mut_remove_no_progress_guard(steps):
    """Classify any exhausted+advanced run as truncated without checking
    either arm."""
    steps[CYCLE_STEP] = steps[CYCLE_STEP].replace(
        'if [ "$arm_a" = "true" ] || [ "$arm_b" = "true" ]; then',
        'if true; then', 1)


def _mut_drop_arm_a(steps):
    steps[CYCLE_STEP] = steps[CYCLE_STEP].replace(
        'if [ "$arm_a" = "true" ] || [ "$arm_b" = "true" ]; then',
        'if [ "$arm_b" = "true" ]; then', 1)


def _mut_drop_arm_b(steps):
    steps[CYCLE_STEP] = steps[CYCLE_STEP].replace(
        'if [ "$arm_a" = "true" ] || [ "$arm_b" = "true" ]; then',
        'if [ "$arm_a" = "true" ]; then', 1)


def _mut_count_advance_as_progress(steps):
    """Widen Arm B to no longer exclude $SPEC_DIR, so the lifecycle-record
    advance commit itself (which lives inside $SPEC_DIR) satisfies Arm B —
    a different mechanism than removing the guard outright."""
    steps[CYCLE_STEP] = steps[CYCLE_STEP].replace(
        'git diff --name-only "$BASE_SHA..origin/${SPEC_PREFIX}$SLUG" -- . ":(exclude)$SPEC_DIR/**"',
        'git diff --name-only "$BASE_SHA..origin/${SPEC_PREFIX}$SLUG"', 1)


def _mut_widen_exhausted_to_failed(steps):
    """Widen BOTH the advance-detection gate and the branch selector — a
    mutation that widened only the selector would still gate "advanced" on
    CYCLE_RESULT=='success', so a "failed" verdict would never reach the
    (mutated) truncated branch at all."""
    steps[CYCLE_STEP] = steps[CYCLE_STEP].replace(
        '[ "$VERDICT" = "exhausted" ]',
        '[ "$VERDICT" = "exhausted" ] || [ "$VERDICT" = "failed" ]')


MUTATIONS = [
    ("remove the forced converged=false on the truncated path",
     _mut_remove_forced_false, "1: exhausted, Arm-A progress, no converge commit",
     {"converged": "true"}),
    ("remove the no-progress guard",
     _mut_remove_no_progress_guard, "2: exhausted, only the lifecycle-record advance landed",
     {"truncated": "true"}),
    ("drop Arm A (task-checkbox count)",
     _mut_drop_arm_a, "3: exhausted, Arm-A-only progress",
     {"truncated": "false"}),
    ("drop Arm B (outside-spec-dir file change)",
     _mut_drop_arm_b, "4: exhausted, Arm-B-only progress",
     {"truncated": "false"}),
    ("count the lifecycle-record advance itself as progress",
     _mut_count_advance_as_progress, "2: exhausted, only the lifecycle-record advance landed",
     {"truncated": "true"}),
    ("widen VERDICT=='exhausted' to also match 'failed'",
     _mut_widen_exhausted_to_failed, "5b: ordinary failure with incidental progress markers",
     {"ok": "true", "truncated": "true"}),
]


def check_gate_wired():
    """FR-020's reflexive check — mirrors Gate 25's own D7 pattern
    (verify-lifecycle-gate-retry.py's check_gate_wired): this script cannot
    see its own absence from a workflow it isn't in, so it reads
    lint-workflows.yml directly and confirms Gate 30 is present, enabled,
    and invokes this script by path."""
    wf = yaml.safe_load(open(LINT_WORKFLOW, encoding="utf-8")) or {}
    for job in (wf.get("jobs") or {}).values():
        for step in (job or {}).get("steps") or []:
            name = (step or {}).get("name") or ""
            if name.startswith(GATE_PREFIX):
                if str(step.get("if", "")).strip().lower() == "false":
                    return [f"{GATE_PREFIX} step is present in {LINT_WORKFLOW} "
                            f"but disabled (if: false) — its own coverage "
                            f"would not run (FR-020)."]
                if THIS_SCRIPT not in str(step.get("run", "")):
                    return [f"{GATE_PREFIX} step in {LINT_WORKFLOW} does not "
                            f"invoke {THIS_SCRIPT} — the gate registry entry "
                            f"and this script have drifted apart (FR-020)."]
                return []
    return [f"no step named {GATE_PREFIX!r} found in {LINT_WORKFLOW} — this "
            f"script's own coverage would not run if it were dropped from "
            f"the registry (FR-020)."]


STEPS_CACHE = {}


def load_steps():
    for name in (CYCLE_STEP, RETRY_STEP, FINAL_STEP, COUNT_STEP, DISPATCH_STEP):
        STEPS_CACHE[name] = find_step(STAGE, name)["run"]
    return STEPS_CACHE


def main():
    global BASH
    use_utf8_stdout()
    ensure_jq()
    BASH = resolve_bash()
    if not shutil.which("git"):
        sys.exit("::error::git is not on PATH. The shipped steps under test "
                 "commit and push, so nothing here can run without it.")

    steps = load_steps()
    root = tempfile.mkdtemp()
    failures = []
    try:
        failures.extend(suite_cycle(steps, root))
        failures.extend(check_retry_no_own_progress(root))
        failures.extend(check_retry_with_own_progress(root))
        failures.extend(check_final_selects_retry_truncated(root))
        failures.extend(check_counter(root))
        failures.extend(check_reporting(root))

        for label, apply_mutation, target_name, expect_wrong in MUTATIONS:
            mutated = copy.deepcopy(steps)
            apply_mutation(mutated)
            if mutated[CYCLE_STEP] == steps[CYCLE_STEP]:
                print(f"::error::mutation {label!r} changed nothing — the "
                      f"code it edits was rewritten. Update the mutation so "
                      f"this harness keeps proving it can fail.")
                failures.append(f"mutation inapplicable: {label}")
                continue
            scenario = SCENARIOS_BY_NAME[target_name]
            rc, out, outputs, _ = run_cycle_scenario(mutated, scenario, root)
            wrong = rc == 0 and all(
                outputs.get(k) == v for k, v in expect_wrong.items())
            if wrong:
                print(f"Mutation OK — {label}: caught "
                      f"(now wrongly reports {expect_wrong}).")
            else:
                print(f"::error::MUTATION SURVIVED — reintroducing {label!r} "
                      f"did not flip scenario {target_name!r} to "
                      f"{expect_wrong} (got rc={rc}, outputs={outputs}). Fix "
                      f"the scenarios, not the mutation.")
                failures.append(f"mutation survived: {label}")

        failures.extend(check_gate_wired())
    finally:
        shutil.rmtree(root, ignore_errors=True)

    print(f"truncated cycle carry-forward: {len(CYCLE_SCENARIOS)} cycle "
          f"scenario(s), {len(MUTATIONS)} mutation(s); {len(failures)} "
          f"failure(s).")
    for f in failures:
        print(f"::error::{f}")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
