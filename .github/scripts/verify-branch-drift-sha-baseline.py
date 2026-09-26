#!/usr/bin/env python3
"""Gate 53: the branch-drift collector compares the implement run's own
recorded SHAs, not a commits-since-run-created window.

WHY THIS EXISTS
---------------
specs/050-branch-drift-sha-baseline closes two permanent detection misses
in watchdog.yml's `collect-branch-drift` step (issue #331): a rebase.yml
force-push between a dispatched implement run finishing and the watchdog
inspecting it, and a later run on the same branch that has already pushed
by inspection time. Both were structurally impossible to catch under the
old `--since=<createdAt>` window, because that window re-derives progress
from the branch's CURRENT state at inspection time rather than from what
the stage itself observed. The fix downloads the inspected run's own
metrics-record artifact and, when it carries a `branch_advance` group,
compares the two SHAs the stage recorded directly — no re-walk of the
branch's live state at all.

No gate before this one drove `collect-branch-drift`'s own shipped bash.
This harness extracts the REAL step text from watchdog.yml and runs it via
subprocess against a `gh` stub (serving canned `gh run download` fixture
records) and, for the arms that still need one, a real local git
repository (mirroring verify-finalize-refresh.py's discipline).

Usage: python3 .github/scripts/verify-branch-drift-sha-baseline.py [-v]
Requires: bash, jq, git (all present on ubuntu-latest runners).
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_shell_harness import (ensure_jq, find_step, resolve_bash, run_step,
                              use_utf8_stdout)

STAGE = ".github/workflows/watchdog.yml"
STEP_NAME = "Collect: branch drift"

REPO = "charlesguse/wing-commander"
SLUG = "050-branch-drift-sha-baseline"
SPEC_PREFIX = "spec/"
BRANCH = SPEC_PREFIX + SLUG
RUN_ID = "999000111"
RUN_CREATED_AT = "2026-09-14T00:00:00Z"

BASH = None
VERBOSE = "-v" in sys.argv[1:]

GH_STUB = r"""#!/bin/sh
case " $* " in
  *" run "*"download "*)
    dest=""
    prev=""
    for arg in "$@"; do
      if [ "$prev" = "-D" ]; then dest="$arg"; fi
      prev="$arg"
    done
    mkdir -p "$dest" 2>/dev/null
    if [ -n "${GH_DOWNLOAD_FIXTURE_DIR:-}" ] && [ -d "${GH_DOWNLOAD_FIXTURE_DIR}" ]; then
      cp "${GH_DOWNLOAD_FIXTURE_DIR}"/*.json "$dest"/ 2>/dev/null
      exit 0
    fi
    exit 1
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


def new_stub_dir(work):
    bindir = os.path.join(work, "bin")
    os.makedirs(bindir, exist_ok=True)
    with open(os.path.join(bindir, "gh"), "w", encoding="utf-8",
              newline="\n") as fh:
        fh.write(GH_STUB)
    os.chmod(os.path.join(bindir, "gh"), 0o755)
    return bindir


def make_repo(root):
    """A bare remote + clone with a spec branch one commit ahead of `main`
    — real git state for the arms that still fetch/rev-list (head-sha,
    since-created)."""
    work = tempfile.mkdtemp(dir=root)
    remote = os.path.join(work, "remote.git")
    repo = os.path.join(work, "repo")
    setup = f"""
git init --bare -q -b main '{remote}'
git clone -q '{remote}' '{repo}'
cd '{repo}'
git config user.email harness@example.invalid
git config user.name harness
echo root > README.md
git add -A
git commit -q -m 'seed main'
git push -q origin main
git checkout -q -b '{BRANCH}'
echo one >> README.md
git commit -q -am 'seed spec branch'
git push -q -u origin '{BRANCH}'
git rev-parse HEAD
"""
    proc = sh(setup, work)
    if proc.returncode != 0:
        sys.exit(f"::error::harness could not seed a git workspace: "
                 f"{proc.stdout}{proc.stderr}")
    tip = proc.stdout.strip().splitlines()[-1]
    return repo, work, tip


def add_commit(repo, work, message="progress"):
    """Pushes one more commit to BRANCH — used to simulate an intervening
    rebase/force-push or a later run's own push between two collector
    runs."""
    script = f"""
cd '{repo}'
echo change >> README.md
git commit -q -am '{message}'
git push -q origin '{BRANCH}'
git rev-parse HEAD
"""
    proc = sh(script, work)
    if proc.returncode != 0:
        sys.exit(f"::error::harness could not add a commit: "
                 f"{proc.stdout}{proc.stderr}")
    return proc.stdout.strip().splitlines()[-1]


def make_fixture_dir(root, branch_advance):
    """A directory holding one metrics-record*.json, the shape
    `gh run download -p 'metrics-record*'` would have populated."""
    d = tempfile.mkdtemp(dir=root)
    record = {
        "schema_version": 1,
        "record_available": False,
        "branch_advance": branch_advance,
    }
    with open(os.path.join(d, "record.json"), "w", encoding="utf-8") as fh:
        json.dump(record, fh)
    return d


def load_step():
    return find_step(STAGE, STEP_NAME)["run"]


def base_env(bindir, extra=None):
    env = {
        "GH_TOKEN": "x",
        "ACTIONS_TOKEN": "x",
        "GITHUB_REPOSITORY": REPO,
        "RUN_ID": RUN_ID,
        "RUN_NAME": "Wing Commander · 5 implement",
        "RUN_CONCLUSION": "success",
        "HEAD_BRANCH": "main",
        "HEAD_SHA": "0" * 40,
        "RUN_CREATED_AT": RUN_CREATED_AT,
        "META_STAGE": "implement",
        "STALLED_LABEL": "false",
        "SLUG": SLUG,
        "SPEC_PREFIX": SPEC_PREFIX,
        "PATH": bindir + os.pathsep + os.environ["PATH"],
    }
    if extra:
        env.update(extra)
    return env


def run_collector(step_text, workdir, runner_temp, env):
    """Seeds signals.json/collector-outcomes.json the way the earlier
    'Reset signals'/'Reset collector outcomes' steps in the real job do,
    runs the extracted step, and returns (rc, out, signals, outcomes,
    summary)."""
    os.makedirs(runner_temp, exist_ok=True)
    with open(os.path.join(runner_temp, "signals.json"), "w",
              encoding="utf-8") as fh:
        fh.write("[]")
    with open(os.path.join(runner_temp, "collector-outcomes.json"), "w",
              encoding="utf-8") as fh:
        fh.write("[]")
    rc, out, _outputs, summary = run_step(BASH, step_text, workdir, env,
                                          runner_temp)
    with open(os.path.join(runner_temp, "signals.json"),
              encoding="utf-8") as fh:
        signals = json.load(fh)
    with open(os.path.join(runner_temp, "collector-outcomes.json"),
              encoding="utf-8") as fh:
        outcomes = json.load(fh)
    return rc, out, signals, outcomes, summary


# --------------------------------------------------------------- scenarios

def scenario_exact_sha_equal_fires_lost_progress(step_text, root):
    """US1 AS1: branch_advance.available, before_sha == after_sha ->
    lost-progress naming the branch, both SHAs, and the recorded commits
    (a deliberately non-zero, non-derivable value — see the module's
    mutation below)."""
    failures = []
    work = tempfile.mkdtemp(dir=root)
    bindir = new_stub_dir(work)
    fixture_dir = make_fixture_dir(root, {
        "available": True, "branch": BRANCH,
        "before_sha": "a" * 40, "before_available": True,
        "after_sha": "a" * 40, "after_available": True,
        # Deliberately inconsistent with what a local walk would compute
        # (0, since before==after) — proves the collector reads this
        # verbatim rather than recomputing it (FR-019, T019's mutation).
        "commits": 7, "commits_available": True,
    })
    env = base_env(bindir, {"GH_DOWNLOAD_FIXTURE_DIR": fixture_dir})
    runner_temp = os.path.join(work, "runner_temp")
    rc, out, signals, outcomes, summary = run_collector(
        step_text, work, runner_temp, env)
    if rc != 0:
        failures.append(f"exact-sha-equal: exited {rc}: {out.strip()[:300]}")
        return failures
    if len(signals) != 1:
        failures.append(f"exact-sha-equal: expected exactly one signal, "
                        f"got {len(signals)}: {signals!r}")
        return failures
    entry = signals[0]
    if entry.get("class-hint") != "lost-progress":
        failures.append(f"exact-sha-equal: expected class-hint "
                        f"'lost-progress', got {entry.get('class-hint')!r}")
    facts = entry.get("facts") or {}
    if facts.get("branch") != BRANCH:
        failures.append(f"exact-sha-equal: facts.branch = "
                        f"{facts.get('branch')!r}, expected {BRANCH!r}")
    if facts.get("before-sha") != "a" * 40:
        failures.append(f"exact-sha-equal: facts['before-sha'] = "
                        f"{facts.get('before-sha')!r}, expected the "
                        f"recorded before_sha")
    if facts.get("after-sha") != "a" * 40:
        failures.append(f"exact-sha-equal: facts['after-sha'] = "
                        f"{facts.get('after-sha')!r}, expected the "
                        f"recorded after_sha")
    if facts.get("since") is not None:
        failures.append(f"exact-sha-equal: facts.since = "
                        f"{facts.get('since')!r}, expected null on the "
                        f"exact-sha arm")
    if facts.get("commits") != 7:
        failures.append(f"exact-sha-equal: facts.commits = "
                        f"{facts.get('commits')!r}, expected 7 (the "
                        f"RECORDED value — FR-019 forbids recomputing it)")
    if {"collector": "collect-branch-drift", "outcome": "ok"} not in outcomes:
        failures.append(f"exact-sha-equal: collector-outcomes.json does "
                        f"not record an 'ok' outcome: {outcomes!r}")
    if "recorded before/after SHAs" not in summary:
        failures.append(f"exact-sha-equal: step summary does not name the "
                        f"exact-sha baseline: {summary!r}")
    return failures


def scenario_exact_sha_differ_no_signal(step_text, root):
    """US1 AS3: branch_advance.available, before_sha != after_sha -> no
    signal."""
    failures = []
    work = tempfile.mkdtemp(dir=root)
    bindir = new_stub_dir(work)
    fixture_dir = make_fixture_dir(root, {
        "available": True, "branch": BRANCH,
        "before_sha": "a" * 40, "before_available": True,
        "after_sha": "b" * 40, "after_available": True,
        "commits": 5, "commits_available": True,
    })
    env = base_env(bindir, {"GH_DOWNLOAD_FIXTURE_DIR": fixture_dir})
    runner_temp = os.path.join(work, "runner_temp")
    rc, out, signals, outcomes, _summary = run_collector(
        step_text, work, runner_temp, env)
    if rc != 0:
        failures.append(f"exact-sha-differ: exited {rc}: {out.strip()[:300]}")
        return failures
    if signals:
        failures.append(f"exact-sha-differ: expected no signal, got "
                        f"{signals!r}")
    if {"collector": "collect-branch-drift", "outcome": "ok"} not in outcomes:
        failures.append(f"exact-sha-differ: collector-outcomes.json does "
                        f"not record an 'ok' outcome: {outcomes!r}")
    return failures


def scenario_exact_sha_commits_unavailable_reads_healthy(step_text, root):
    """FR-019/FR-017/SC-002 (maintainer review of #354): a differing pair
    whose recorded commits count is itself unavailable must read as
    healthy, exactly like a differing pair with a positive count — the
    verdict is the SHA equal/not-equal comparison alone, never gated on
    the count also being present. A version of this collector that
    required commits to be a resolved non-zero value before treating a
    differing pair as healthy would wrongly fire lost-progress here."""
    failures = []
    work = tempfile.mkdtemp(dir=root)
    bindir = new_stub_dir(work)
    fixture_dir = make_fixture_dir(root, {
        "available": True, "branch": BRANCH,
        "before_sha": "a" * 40, "before_available": True,
        "after_sha": "b" * 40, "after_available": True,
        "commits": None, "commits_available": False,
    })
    env = base_env(bindir, {"GH_DOWNLOAD_FIXTURE_DIR": fixture_dir})
    runner_temp = os.path.join(work, "runner_temp")
    rc, out, signals, outcomes, _summary = run_collector(
        step_text, work, runner_temp, env)
    if rc != 0:
        failures.append(f"exact-sha-commits-unavailable: exited {rc}: "
                        f"{out.strip()[:300]}")
        return failures
    if signals:
        failures.append(f"exact-sha-commits-unavailable: expected no "
                        f"signal for a differing pair with commits "
                        f"unavailable, got {signals!r}")
    if {"collector": "collect-branch-drift", "outcome": "ok"} not in outcomes:
        failures.append(f"exact-sha-commits-unavailable: collector-"
                        f"outcomes.json does not record an 'ok' outcome: "
                        f"{outcomes!r}")
    return failures


def scenario_exact_sha_ignores_live_branch_state(step_text, root):
    """US2 AS1-2 / T021: the exact-sha arm's verdict cannot be affected by
    the measured branch's CURRENT state — pointing the fixture repo's
    remote branch tip at a commit the record knows nothing about, between
    two runs of the SAME record, must not change the verdict (SC-001,
    SC-003)."""
    failures = []
    repo, work, tip = make_repo(root)
    bindir = new_stub_dir(work)
    fixture_dir = make_fixture_dir(root, {
        "available": True, "branch": BRANCH,
        "before_sha": tip, "before_available": True,
        "after_sha": tip, "after_available": True,
        "commits": 0, "commits_available": True,
    })
    env = base_env(bindir, {"GH_DOWNLOAD_FIXTURE_DIR": fixture_dir})

    runner_temp_1 = os.path.join(work, "runner_temp_1")
    rc1, out1, signals1, _outcomes1, _s1 = run_collector(
        step_text, repo, runner_temp_1, env)
    if rc1 != 0:
        failures.append(f"exact-sha-invariant (first run): exited {rc1}: "
                        f"{out1.strip()[:300]}")
        return failures

    # Simulate an intervening rebase/second-run push: the branch's REMOTE
    # tip moves on, but the (unchanged) record still says before==after==tip.
    add_commit(repo, work, "an intervening push after the cycle finished")

    runner_temp_2 = os.path.join(work, "runner_temp_2")
    rc2, out2, signals2, _outcomes2, _s2 = run_collector(
        step_text, repo, runner_temp_2, env)
    if rc2 != 0:
        failures.append(f"exact-sha-invariant (second run): exited {rc2}: "
                        f"{out2.strip()[:300]}")
        return failures

    if signals1 != signals2:
        failures.append(
            "exact-sha-invariant: the verdict changed after the measured "
            f"branch's remote tip advanced — the exact-sha arm must never "
            f"read the branch's current state. first={signals1!r} "
            f"second={signals2!r}")
    if len(signals1) != 1 or signals1[0].get("class-hint") != "lost-progress":
        failures.append(f"exact-sha-invariant: expected a lost-progress "
                        f"signal from the (unchanged) equal-SHA record, "
                        f"got {signals1!r}")
    return failures


def scenario_stalled_short_circuits_exact_sha(step_text, root):
    """US1 AS4 / FR-014: the already-handled/stalled short-circuit applies
    to the exact-sha arm exactly as it does to since-created."""
    failures = []
    work = tempfile.mkdtemp(dir=root)
    bindir = new_stub_dir(work)
    fixture_dir = make_fixture_dir(root, {
        "available": True, "branch": BRANCH,
        "before_sha": "a" * 40, "before_available": True,
        "after_sha": "a" * 40, "after_available": True,
        "commits": 0, "commits_available": True,
    })
    env = base_env(bindir, {"GH_DOWNLOAD_FIXTURE_DIR": fixture_dir,
                            "META_STAGE": "stalled"})
    runner_temp = os.path.join(work, "runner_temp")
    rc, out, signals, _outcomes, _summary = run_collector(
        step_text, work, runner_temp, env)
    if rc != 0:
        failures.append(f"stalled-short-circuit: exited {rc}: "
                        f"{out.strip()[:300]}")
        return failures
    if len(signals) != 1:
        failures.append(f"stalled-short-circuit: expected exactly one "
                        f"entry, got {len(signals)}: {signals!r}")
        return failures
    entry = signals[0]
    if entry.get("class-hint") is not None:
        failures.append(f"stalled-short-circuit: expected class-hint "
                        f"null, got {entry.get('class-hint')!r}")
    if not entry.get("alreadyHandledBy"):
        failures.append(f"stalled-short-circuit: expected an "
                        f"alreadyHandledBy field, got {entry!r}")
    return failures


def scenario_plan_exact_sha_equal_fires_lost_progress(step_text, root):
    """specs/068-plan-tasks-branch-advance T013 (US1 AS1): a plan run's own
    downloaded record, branch_advance.available with before_sha ==
    after_sha, fires lost-progress naming the plan/ review branch it
    recorded -- the same mechanism
    scenario_exact_sha_equal_fires_lost_progress proves for implement, now
    reachable for plan too (T011 widened the exact-sha arm beyond
    implement-only)."""
    failures = []
    work = tempfile.mkdtemp(dir=root)
    bindir = new_stub_dir(work)
    plan_branch = "plan/" + SLUG
    fixture_dir = make_fixture_dir(root, {
        "available": True, "branch": plan_branch,
        "before_sha": "c" * 40, "before_available": True,
        "after_sha": "c" * 40, "after_available": True,
        "commits": 0, "commits_available": True,
    })
    env = base_env(bindir, {"GH_DOWNLOAD_FIXTURE_DIR": fixture_dir,
                            "RUN_NAME": "Wing Commander · 3 plan"})
    runner_temp = os.path.join(work, "runner_temp")
    rc, out, signals, outcomes, _summary = run_collector(
        step_text, work, runner_temp, env)
    if rc != 0:
        failures.append(f"plan-exact-sha-equal: exited {rc}: "
                        f"{out.strip()[:300]}")
        return failures
    if len(signals) != 1:
        failures.append(f"plan-exact-sha-equal: expected exactly one "
                        f"signal, got {len(signals)}: {signals!r}")
        return failures
    entry = signals[0]
    if entry.get("class-hint") != "lost-progress":
        failures.append(f"plan-exact-sha-equal: expected class-hint "
                        f"'lost-progress', got {entry.get('class-hint')!r}")
    facts = entry.get("facts") or {}
    if facts.get("branch") != plan_branch:
        failures.append(f"plan-exact-sha-equal: facts.branch = "
                        f"{facts.get('branch')!r}, expected {plan_branch!r} "
                        f"-- a plan run's record names its own review "
                        f"branch, never a prefix-derived guess")
    if facts.get("before-sha") != "c" * 40 or facts.get("after-sha") != "c" * 40:
        failures.append(f"plan-exact-sha-equal: facts SHAs did not match "
                        f"the recorded pair: {facts!r}")
    if facts.get("commits") != 0:
        failures.append(f"plan-exact-sha-equal: facts.commits = "
                        f"{facts.get('commits')!r}, expected 0")
    if {"collector": "collect-branch-drift", "outcome": "ok"} not in outcomes:
        failures.append(f"plan-exact-sha-equal: collector-outcomes.json "
                        f"does not record an 'ok' outcome: {outcomes!r}")
    return failures


def scenario_tasks_exact_sha_differ_no_signal(step_text, root):
    """specs/068-plan-tasks-branch-advance T013 (US1 AS3): a tasks run's
    own downloaded record, branch_advance.available with before_sha !=
    after_sha, produces no signal -- the healthy-progress mirror of
    scenario_plan_exact_sha_equal_fires_lost_progress above."""
    failures = []
    work = tempfile.mkdtemp(dir=root)
    bindir = new_stub_dir(work)
    tasks_branch = "tasks/" + SLUG
    fixture_dir = make_fixture_dir(root, {
        "available": True, "branch": tasks_branch,
        "before_sha": "d" * 40, "before_available": True,
        "after_sha": "e" * 40, "after_available": True,
        "commits": 5, "commits_available": True,
    })
    env = base_env(bindir, {"GH_DOWNLOAD_FIXTURE_DIR": fixture_dir,
                            "RUN_NAME": "Wing Commander · 4 tasks"})
    runner_temp = os.path.join(work, "runner_temp")
    rc, out, signals, outcomes, _summary = run_collector(
        step_text, work, runner_temp, env)
    if rc != 0:
        failures.append(f"tasks-exact-sha-differ: exited {rc}: "
                        f"{out.strip()[:300]}")
        return failures
    if signals:
        failures.append(f"tasks-exact-sha-differ: expected no signal, got "
                        f"{signals!r}")
    if {"collector": "collect-branch-drift", "outcome": "ok"} not in outcomes:
        failures.append(f"tasks-exact-sha-differ: collector-outcomes.json "
                        f"does not record an 'ok' outcome: {outcomes!r}")
    return failures


def scenario_plan_exact_sha_ignores_live_branch_state(step_text, root):
    """specs/068-plan-tasks-branch-advance T014 (US2 AS1-2): the exact-sha
    arm's verdict for a plan run cannot be affected by an intervening push
    either -- mirrors scenario_exact_sha_ignores_live_branch_state, but for
    a plan/<slug>-branch record and RUN_NAME "Wing Commander · 3 plan"
    (T011 widened the exact-sha arm beyond implement-only)."""
    failures = []
    repo, work, tip = make_repo(root)
    bindir = new_stub_dir(work)
    plan_branch = "plan/" + SLUG
    fixture_dir = make_fixture_dir(root, {
        "available": True, "branch": plan_branch,
        "before_sha": tip, "before_available": True,
        "after_sha": tip, "after_available": True,
        "commits": 0, "commits_available": True,
    })
    env = base_env(bindir, {"GH_DOWNLOAD_FIXTURE_DIR": fixture_dir,
                            "RUN_NAME": "Wing Commander · 3 plan"})

    runner_temp_1 = os.path.join(work, "runner_temp_1")
    rc1, out1, signals1, _outcomes1, _s1 = run_collector(
        step_text, repo, runner_temp_1, env)
    if rc1 != 0:
        failures.append(f"plan-exact-sha-invariant (first run): exited "
                        f"{rc1}: {out1.strip()[:300]}")
        return failures

    # Simulate an intervening push on the local fixture repo -- the
    # record's own plan/<slug> branch is not even present in this repo,
    # which is the point: the exact-sha arm never fetches or rev-parses
    # the branch it names, so nothing about the repo's state can move
    # this verdict.
    add_commit(repo, work, "an intervening push after the run finished")

    runner_temp_2 = os.path.join(work, "runner_temp_2")
    rc2, out2, signals2, _outcomes2, _s2 = run_collector(
        step_text, repo, runner_temp_2, env)
    if rc2 != 0:
        failures.append(f"plan-exact-sha-invariant (second run): exited "
                        f"{rc2}: {out2.strip()[:300]}")
        return failures

    if signals1 != signals2:
        failures.append(
            "plan-exact-sha-invariant: the verdict changed after the "
            f"local repo advanced — the exact-sha arm must never read "
            f"live branch state, for plan/tasks any more than for "
            f"implement. first={signals1!r} second={signals2!r}")
    if len(signals1) != 1 or signals1[0].get("class-hint") != "lost-progress":
        failures.append(f"plan-exact-sha-invariant: expected a "
                        f"lost-progress signal from the (unchanged) "
                        f"equal-SHA record, got {signals1!r}")
    if signals1 and signals1[0].get("facts", {}).get("branch") != plan_branch:
        failures.append(f"plan-exact-sha-invariant: facts.branch = "
                        f"{signals1[0].get('facts', {}).get('branch')!r}, "
                        f"expected {plan_branch!r}")
    return failures


def scenario_plan_no_branch_advance_no_signal_no_fallback(step_text, root):
    """specs/068-plan-tasks-branch-advance T019 (US4; FR-016/FR-017/FR-018;
    research.md R9 case 3): a plan run whose downloaded artifact set
    carries no record with branch_advance.available: true produces no
    signal, attempts no since-created fallback measurement (unlike
    implement's own no-record case, which does fall back), names T018's
    exact skip wording in the step summary, and the collector's own
    outcome is "ok" — an absent optional field is data, not a failed
    read. This same no-record shape (no GH_DOWNLOAD_FIXTURE_DIR set)
    doubles as T021's confirmation that a record predating this feature
    (no branch_advance key at all) produces no false detection."""
    failures = []
    work = tempfile.mkdtemp(dir=root)
    bindir = new_stub_dir(work)
    # No GH_DOWNLOAD_FIXTURE_DIR set -> the gh stub's `run download` exits 1,
    # exactly like an expired/absent artifact -- mirrors
    # scenario_no_branch_advance_falls_back_to_since_created's own setup.
    env = base_env(bindir, {"RUN_NAME": "Wing Commander · 3 plan"})
    runner_temp = os.path.join(work, "runner_temp")
    rc, out, signals, outcomes, summary = run_collector(
        step_text, work, runner_temp, env)
    if rc != 0:
        failures.append(f"plan-no-evidence: exited {rc}: {out.strip()[:300]}")
        return failures
    if signals:
        failures.append(f"plan-no-evidence: expected no signal, got "
                        f"{signals!r}")
    if {"collector": "collect-branch-drift", "outcome": "ok"} not in outcomes:
        failures.append(f"plan-no-evidence: collector-outcomes.json does "
                        f"not record an 'ok' outcome: {outcomes!r}")
    if ("no recorded branch-advance evidence on this plan run — skipping"
            not in summary):
        failures.append(f"plan-no-evidence: step summary does not name "
                        f"T018's exact skip wording: {summary!r}")
    return failures


def scenario_tasks_no_branch_advance_no_signal_no_fallback(step_text, root):
    """specs/068-plan-tasks-branch-advance T019 (US4; research.md R9 case
    4): the tasks mirror of
    scenario_plan_no_branch_advance_no_signal_no_fallback above."""
    failures = []
    work = tempfile.mkdtemp(dir=root)
    bindir = new_stub_dir(work)
    env = base_env(bindir, {"RUN_NAME": "Wing Commander · 4 tasks"})
    runner_temp = os.path.join(work, "runner_temp")
    rc, out, signals, outcomes, summary = run_collector(
        step_text, work, runner_temp, env)
    if rc != 0:
        failures.append(f"tasks-no-evidence: exited {rc}: {out.strip()[:300]}")
        return failures
    if signals:
        failures.append(f"tasks-no-evidence: expected no signal, got "
                        f"{signals!r}")
    if {"collector": "collect-branch-drift", "outcome": "ok"} not in outcomes:
        failures.append(f"tasks-no-evidence: collector-outcomes.json does "
                        f"not record an 'ok' outcome: {outcomes!r}")
    if ("no recorded branch-advance evidence on this tasks run — skipping"
            not in summary):
        failures.append(f"tasks-no-evidence: step summary does not name "
                        f"T018's exact skip wording: {summary!r}")
    return failures


def scenario_no_branch_advance_falls_back_to_since_created(step_text, root):
    """US3 / FR-013, FR-018: no downloaded record carries
    branch_advance.available:true -> the since-created fallback fires
    unchanged, and the step summary names it as the fallback."""
    failures = []
    repo, work, _tip = make_repo(root)
    bindir = new_stub_dir(work)
    # No GH_DOWNLOAD_FIXTURE_DIR set -> the gh stub's `run download` exits 1,
    # exactly like an expired/absent artifact.
    env = base_env(bindir, {
        # Far enough in the future that --since excludes every commit on
        # the seeded branch, so the since-created arm reports commits=0
        # and fires (deterministic, no need to control commit dates).
        "RUN_CREATED_AT": "2099-01-01T00:00:00Z",
    })
    runner_temp = os.path.join(work, "runner_temp")
    rc, out, signals, outcomes, summary = run_collector(
        step_text, repo, runner_temp, env)
    if rc != 0:
        failures.append(f"since-created-fallback: exited {rc}: "
                        f"{out.strip()[:300]}")
        return failures
    if len(signals) != 1:
        failures.append(f"since-created-fallback: expected exactly one "
                        f"signal, got {len(signals)}: {signals!r}")
        return failures
    facts = signals[0].get("facts") or {}
    if facts.get("before-sha") is not None:
        failures.append(f"since-created-fallback: facts['before-sha'] "
                        f"should stay null on this arm, got "
                        f"{facts.get('before-sha')!r}")
    if facts.get("since") != "2099-01-01T00:00:00Z":
        failures.append(f"since-created-fallback: facts.since = "
                        f"{facts.get('since')!r}, expected the run's "
                        f"created-at timestamp")
    if facts.get("commits") != 0:
        failures.append(f"since-created-fallback: facts.commits = "
                        f"{facts.get('commits')!r}, expected the fixed 0 "
                        f"placeholder this arm has always emitted")
    if {"collector": "collect-branch-drift", "outcome": "ok"} not in outcomes:
        failures.append(f"since-created-fallback: collector-outcomes.json "
                        f"does not record an 'ok' outcome: {outcomes!r}")
    if "no recorded branch-advance evidence on this run" not in summary:
        failures.append(f"since-created-fallback: step summary does not "
                        f"name the fallback baseline: {summary!r}")
    return failures


def scenario_head_sha_arm_unaffected(step_text, root):
    """FR-012 regression: a spec-branch-head run (plan/tasks pushing to
    their own head) is unaffected — baseline stays head-sha, never
    downloads an artifact."""
    failures = []
    repo, work, tip = make_repo(root)
    bindir = new_stub_dir(work)
    env = base_env(bindir, {
        "RUN_NAME": "Wing Commander · 3 plan",
        "HEAD_BRANCH": BRANCH,
        "HEAD_SHA": tip,
    })
    runner_temp = os.path.join(work, "runner_temp")
    rc, out, signals, _outcomes, _summary = run_collector(
        step_text, repo, runner_temp, env)
    if rc != 0:
        failures.append(f"head-sha-arm: exited {rc}: {out.strip()[:300]}")
        return failures
    if len(signals) != 1:
        failures.append(f"head-sha-arm: expected exactly one signal (no "
                        f"progress since HEAD_SHA), got {len(signals)}: "
                        f"{signals!r}")
        return failures
    facts = signals[0].get("facts") or {}
    if facts.get("before-sha") != tip:
        failures.append(f"head-sha-arm: facts['before-sha'] = "
                        f"{facts.get('before-sha')!r}, expected HEAD_SHA "
                        f"({tip!r}) — this arm's shape must stay untouched")
    if facts.get("since") is not None:
        failures.append(f"head-sha-arm: facts.since should stay null, got "
                        f"{facts.get('since')!r}")
    return failures


def scenario_non_push_expected_stage_unaffected(step_text, root):
    """FR-012 regression: a non-push-expected stage's run skips before any
    download is attempted."""
    failures = []
    work = tempfile.mkdtemp(dir=root)
    bindir = new_stub_dir(work)
    env = base_env(bindir, {"RUN_NAME": "Wing Commander · 8 watchdog"})
    runner_temp = os.path.join(work, "runner_temp")
    rc, out, signals, outcomes, summary = run_collector(
        step_text, work, runner_temp, env)
    if rc != 0:
        failures.append(f"non-push-expected: exited {rc}: "
                        f"{out.strip()[:300]}")
        return failures
    if signals:
        failures.append(f"non-push-expected: expected no signal, got "
                        f"{signals!r}")
    if outcomes:
        failures.append(f"non-push-expected: expected no collector "
                        f"outcome recorded, got {outcomes!r}")
    if "not a push-expected stage" not in summary:
        failures.append(f"non-push-expected: step summary does not "
                        f"explain the skip: {summary!r}")
    return failures


def scenario_skipped_run_unaffected(step_text, root):
    """FR-012 regression: a skipped/cancelled run executed nothing, so the
    pre-existing early exit fires before any of this feature's new code —
    unaffected by T013-T015's new arm."""
    failures = []
    work = tempfile.mkdtemp(dir=root)
    bindir = new_stub_dir(work)
    env = base_env(bindir, {"RUN_CONCLUSION": "cancelled"})
    runner_temp = os.path.join(work, "runner_temp")
    rc, out, signals, outcomes, summary = run_collector(
        step_text, work, runner_temp, env)
    if rc != 0:
        failures.append(f"skipped-run: exited {rc}: {out.strip()[:300]}")
        return failures
    if signals:
        failures.append(f"skipped-run: expected no signal, got {signals!r}")
    if outcomes:
        failures.append(f"skipped-run: expected no collector outcome "
                        f"recorded, got {outcomes!r}")
    if "nothing executed" not in summary:
        failures.append(f"skipped-run: step summary does not explain the "
                        f"skip: {summary!r}")
    return failures


def scenario_unresolved_created_at_exits_quietly(step_text, root):
    """Regression (contracts/gate-coverage-050.md assertion 6): a
    dispatched implement run whose RUN_CREATED_AT cannot be resolved still
    exits quietly, unaffected by this feature — the pre-existing guard
    fires before the new artifact-download attempt is ever reached."""
    failures = []
    work = tempfile.mkdtemp(dir=root)
    bindir = new_stub_dir(work)
    env = base_env(bindir, {"RUN_CREATED_AT": ""})
    runner_temp = os.path.join(work, "runner_temp")
    rc, out, signals, outcomes, _summary = run_collector(
        step_text, work, runner_temp, env)
    if rc != 0:
        failures.append(f"unresolved-created-at: exited {rc}: "
                        f"{out.strip()[:300]}")
        return failures
    if signals:
        failures.append(f"unresolved-created-at: expected no signal, got "
                        f"{signals!r}")
    if outcomes:
        failures.append(f"unresolved-created-at: expected no collector "
                        f"outcome recorded, got {outcomes!r}")
    return failures


def scenario_unresolved_slug_exits_quietly(step_text, root):
    """Regression: an unresolved slug (a run whose head is not a pipeline
    branch and whose metrics record names no spec) still exits quietly,
    unaffected by this feature (contracts/gate-coverage-050.md assertion
    6)."""
    failures = []
    work = tempfile.mkdtemp(dir=root)
    bindir = new_stub_dir(work)
    env = base_env(bindir, {"SLUG": "", "HEAD_BRANCH": "main"})
    runner_temp = os.path.join(work, "runner_temp")
    rc, out, signals, outcomes, summary = run_collector(
        step_text, work, runner_temp, env)
    if rc != 0:
        failures.append(f"unresolved-slug: exited {rc}: {out.strip()[:300]}")
        return failures
    if signals:
        failures.append(f"unresolved-slug: expected no signal, got "
                        f"{signals!r}")
    if outcomes:
        failures.append(f"unresolved-slug: expected no collector outcome "
                        f"recorded, got {outcomes!r}")
    if "no spec slug resolved" not in summary:
        failures.append(f"unresolved-slug: step summary does not explain "
                        f"the skip: {summary!r}")
    return failures


SCENARIOS = [
    scenario_exact_sha_equal_fires_lost_progress,
    scenario_exact_sha_differ_no_signal,
    scenario_exact_sha_commits_unavailable_reads_healthy,
    scenario_exact_sha_ignores_live_branch_state,
    scenario_stalled_short_circuits_exact_sha,
    scenario_plan_exact_sha_equal_fires_lost_progress,
    scenario_tasks_exact_sha_differ_no_signal,
    scenario_plan_exact_sha_ignores_live_branch_state,
    scenario_plan_no_branch_advance_no_signal_no_fallback,
    scenario_tasks_no_branch_advance_no_signal_no_fallback,
    scenario_no_branch_advance_falls_back_to_since_created,
    scenario_head_sha_arm_unaffected,
    scenario_non_push_expected_stage_unaffected,
    scenario_skipped_run_unaffected,
    scenario_unresolved_created_at_exits_quietly,
    scenario_unresolved_slug_exits_quietly,
]


def suite(step_text, root):
    return [f for fn in SCENARIOS for f in fn(step_text, root)]


# ------------------------------------------------------------------ mutation

def _mut_rederive_commits_via_rev_list(step_text):
    """FR-019: reverts the "never re-walk the recorded range" invariant —
    the exact-sha arm recomputes `commits` via a live `git rev-list` over
    the recorded SHAs instead of reading `branch_advance.commits` verbatim.
    Run against a real local checkout of the fixture record's SHAs (both
    equal), a live walk reports 0 — disagreeing with
    scenario_exact_sha_equal_fires_lost_progress's recorded 7, which is
    exactly the divergence this mutation must be caught by.
    """
    return step_text.replace(
        'commits="$exact_commits"',
        'commits="$(git rev-list --count '
        '"$exact_before_sha..$exact_after_sha" 2>/dev/null || echo 0)"')


def scenario_exact_sha_equal_in_real_repo(step_text, root):
    """Same as scenario_exact_sha_equal_fires_lost_progress, but run inside
    a real git checkout that actually holds the recorded SHA (needed for
    the mutation above's live `git rev-list` to resolve at all instead of
    erroring on an unknown ref)."""
    failures = []
    repo, work, tip = make_repo(root)
    bindir = new_stub_dir(work)
    fixture_dir = make_fixture_dir(root, {
        "available": True, "branch": BRANCH,
        "before_sha": tip, "before_available": True,
        "after_sha": tip, "after_available": True,
        "commits": 7, "commits_available": True,
    })
    env = base_env(bindir, {"GH_DOWNLOAD_FIXTURE_DIR": fixture_dir})
    runner_temp = os.path.join(work, "runner_temp")
    rc, out, signals, _outcomes, _summary = run_collector(
        step_text, repo, runner_temp, env)
    if rc != 0:
        failures.append(f"exact-sha-equal (real repo): exited {rc}: "
                        f"{out.strip()[:300]}")
        return failures
    if len(signals) != 1 or (signals[0].get("facts") or {}).get("commits") != 7:
        failures.append(f"exact-sha-equal (real repo): expected recorded "
                        f"commits=7, got {signals!r}")
    return failures


MUTATIONS = [
    ("FR-019 reverted: commits re-derived via a live git rev-list instead "
     "of read from the record",
     _mut_rederive_commits_via_rev_list,
     scenario_exact_sha_equal_in_real_repo),
]


def main():
    global BASH
    use_utf8_stdout()
    ensure_jq()
    BASH = resolve_bash()
    if not shutil.which("git"):
        sys.exit("::error::git is not on PATH. The shipped step under test "
                 "runs git fetch/rev-parse/rev-list on its fallback arms, "
                 "so nothing here can run without it.")

    step_text = load_step()
    root = tempfile.mkdtemp()
    failures = []
    try:
        behavioral_failures = suite(step_text, root)
        failures.extend(behavioral_failures)
        for f in behavioral_failures:
            print(f"::error::{f}")

        for label, apply_mutation, scenario_fn in MUTATIONS:
            mutated = apply_mutation(step_text)
            if mutated == step_text:
                print(f"::error::mutation {label!r} changed nothing — the "
                      f"code it edits was rewritten. Update the mutation.")
                failures.append(f"mutation inapplicable: {label}")
                continue
            if scenario_fn(mutated, root):
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

    print(f"Gate 53: {len(SCENARIOS)} scenario(s), {len(MUTATIONS)} "
          f"mutation(s); {len(failures)} failure(s).")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
