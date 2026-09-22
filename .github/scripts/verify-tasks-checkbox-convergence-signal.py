#!/usr/bin/env python3
"""Gate 81 — converged means no task is left, and the signal reads tasks.md.

WHY THIS EXISTS
----------------
"Read back cycle outcome" (and its retry-arm twin) used to decide
`converged` from one proxy: whether a `converge:`-prefixed commit touching
`tasks.md` landed in the cycle's commit range. A cycle that stopped
healthy, with `tasks.md` still full of unchecked boxes, but whose own
convergence pass never ran (or ran and found nothing to append) was
reported `converged=true` anyway — spec 057's cycle 1 hit exactly this: 11
of 65 tasks ticked, no `converge:` commit, and finalization was reached
with 54 tasks never built. This feature (spec 059) replaces that proxy
with a deterministic read of `tasks.md`'s own checkbox state at the
cycle's pushed tip, gated by a progress test that tells "a later cycle
will finish this" apart from "no cycle ever will" (FR-010).

WHAT THIS CHECKS (this pass — US1 only; later phases extend this table)
-------------------------------------------------------------------------
Drives the SHIPPED `run:` text of "Read back cycle outcome" (via
`find_step`, never a copy), fed the env the new
`wing-commander-tasks-checkbox-count` composite's outputs now supply
(itself exercised for real, via the shared script it fronts —
`.github/actions/_shared/count-tasks-checkboxes.sh` — against a synthetic
git repo with a real bare remote), proving: a healthy cycle that makes
progress but lands no `converge:` commit is NOT converged while tasks
remain (User Story 1); a cycle whose `tasks.md` has zero unchecked tasks
at the tip IS converged regardless of a converge commit (SC-004); a
`- [ ]` inside a fenced code block is never counted (FR-004); a ref:path
the shared script cannot read fails loudly rather than resolving as
converged (FR-006, Principle VIII); and spec 057's own cycle-1 shape (11
of 65 ticked, no converge commit, healthy exit) now reports
`converged=false` (SC-003).

Usage: python3 .github/scripts/verify-tasks-checkbox-convergence-signal.py
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
GATE_PREFIX = "Gate 81"
THIS_SCRIPT = ".github/scripts/verify-tasks-checkbox-convergence-signal.py"
COUNT_TASKS_CHECKBOXES = ".github/actions/_shared/count-tasks-checkboxes.sh"
COMPOSITE = ".github/actions/wing-commander-tasks-checkbox-count/action.yml"

CYCLE_STEP = "Read back cycle outcome"
RETRY_STEP = "Read back retry outcome"
FINAL_STEP = "Consolidate final outcome"
DISPATCH_STEP = "Dispatch next step"

AGENT_AUTHOR_RE = r"claude\[bot\]|wing-commander-bot\[bot\]"
SPEC_PREFIX = "spec/"
SLUG = "059-fixture"
SPEC_DIR = f"specs/{SLUG}"
ITERATION = "3"
PRIOR_ITERATION = "2"

BASH = None


def sh(script, cwd):
    """Run a helper snippet through the same bash the steps get.

    Mirrors verify-truncated-cycle-carry-forward.py's own `sh` — the script
    file must live OUTSIDE `cwd` so a `git add -A` inside the fixture repo
    never sweeps it up.
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


def _meta(iteration, **extra):
    meta = {"stage": "implement", "iteration": int(iteration), "spec_dir": SPEC_DIR}
    meta.update(extra)
    return json.dumps(meta) + "\n"


def _tasks_md(checked, unchecked, start=0):
    lines = [f"- [x] T{i:03d} done" for i in range(start, start + checked)]
    lines += [f"- [ ] T{i:03d} todo" for i in range(start + checked, start + checked + unchecked)]
    return "\n".join(lines) + "\n"


FENCE_TASKS_MD_BASE = (
    "- [ ] T001 do a thing\n"
    "- [ ] T002 do another\n"
    "\n"
    "```markdown\n"
    "- [ ] FAKE not a real task, inside a fence\n"
    "```\n"
)
FENCE_TASKS_MD_TIP = (
    "- [x] T001 do a thing\n"
    "- [x] T002 do another\n"
    "\n"
    "```markdown\n"
    "- [ ] FAKE not a real task, inside a fence\n"
    "```\n"
)


def checkbox_count_env(repo, ref):
    """Stand in for the wing-commander-tasks-checkbox-count composite calls
    that precede each read-back (research.md D2): runs the REAL shared
    script against `ref`'s tasks.md, returning (checked-count,
    unchecked-count, unchecked-items) the way the composite's own outputs
    would -- unchecked-items is the heredoc-style block the composite
    relays straight into $GITHUB_OUTPUT (count-tasks-checkboxes.sh's own
    header comment)."""
    script = os.path.abspath(COUNT_TASKS_CHECKBOXES).replace("\\", "/")
    proc = sh(f"cd '{repo}' && bash '{script}' '{ref}' '{SPEC_DIR}/tasks.md'", repo)
    if proc.returncode != 0:
        sys.exit(f"::error::checkbox_count_env: count-tasks-checkboxes.sh failed "
                 f"against a fixture that should be readable: {proc.stdout}{proc.stderr}")
    lines = proc.stdout.splitlines()
    checked = lines[0].split("=", 1)[1] if lines and "=" in lines[0] else "0"
    unchecked = lines[1].split("=", 1)[1] if len(lines) > 1 and "=" in lines[1] else "0"
    items = ""
    if len(lines) > 2 and "<<" in lines[2]:
        delim = lines[2].split("<<", 1)[1]
        body = []
        for line in lines[3:]:
            if line == delim:
                break
            body.append(line)
        items = "\n".join(body) + ("\n" if body else "")
    return checked, unchecked, items


READ_SPEC_META = ".github/actions/_shared/read-spec-meta.sh"


def read_spec_meta_env(repo):
    """Stand in for the `Read spec-meta.json from the spec branch` composite
    step that precedes each read-back (#340) -- see
    verify-truncated-cycle-carry-forward.py's identical helper."""
    script = os.path.abspath(READ_SPEC_META).replace("\\", "/")
    proc = sh(f"cd '{repo}' && bash '{script}' '{SPEC_PREFIX}' '{SLUG}' '{SPEC_DIR}'", repo)
    kv = dict(line.split("=", 1) for line in proc.stdout.splitlines() if "=" in line)
    return {"META_IDENTITY_OK": kv.get("meta_identity_ok", ""),
            "META_STAGE": kv.get("meta_stage", ""),
            "META_ITERATION": kv.get("meta_iteration", "")}


def make_workspace(root, base_tasks_md, prior_iteration=PRIOR_ITERATION):
    """A git repo + bare remote, seeded with one commit on the spec branch.

    Mirrors verify-truncated-cycle-carry-forward.py's make_workspace: a
    REAL bare remote so the checkbox-count composite's own `git show
    origin/...` executes against a real fetched ref, not a mock.
    """
    branch = f"{SPEC_PREFIX}{SLUG}"
    work = tempfile.mkdtemp(dir=root)
    remote = os.path.join(work, "remote.git")
    repo = os.path.join(work, "repo")
    setup = f"""
git init --bare -q -b main '{remote}'
git clone -q '{remote}' '{repo}'
cd '{repo}'
git config user.email 'claude[bot]@users.noreply.invalid'
git config user.name 'claude[bot]'
"""
    proc = sh(setup, work)
    if proc.returncode != 0:
        sys.exit(f"::error::harness could not build a git workspace: "
                 f"{proc.stdout}{proc.stderr}")
    write_file(repo, f"{SPEC_DIR}/tasks.md", base_tasks_md)
    write_file(repo, f"{SPEC_DIR}/spec-meta.json", _meta(prior_iteration))
    write_file(repo, "README.md", "unrelated\n")
    git_commit(repo, "seed")
    git_push(repo, "main")
    proc = sh(f"cd '{repo}' && git checkout -q -b '{branch}'", repo)
    if proc.returncode != 0:
        sys.exit(f"::error::branching failed: {proc.stdout}{proc.stderr}")
    git_push(repo, branch)
    base_sha = rev_parse(repo)
    return work, repo, base_sha, branch


def build_scenario(root, *, base_tasks_md, tip_tasks_md, converge=False,
                    iteration=ITERATION, prior_iteration=PRIOR_ITERATION,
                    advance=True):
    """One synthetic cycle's history: a base commit, a commit that leaves
    tasks.md in its tip state (a plain "implement:" commit, or a
    "converge:"-prefixed one), and — unless `advance` is False — a commit
    advancing spec-meta.json the way /speckit-implement's step 2 does.

    A FR-010 zero-progress cycle realistically never touches tasks.md at
    all, so when `tip_tasks_md` is byte-identical to `base_tasks_md` this
    skips the tasks.md commit entirely rather than handing git an empty
    commit."""
    work, repo, base_sha, branch = make_workspace(root, base_tasks_md, prior_iteration)
    if tip_tasks_md != base_tasks_md:
        write_file(repo, f"{SPEC_DIR}/tasks.md", tip_tasks_md)
        git_commit(repo, "converge: add convergence phase" if converge else "implement: tick tasks")
    if advance:
        write_file(repo, f"{SPEC_DIR}/spec-meta.json", _meta(iteration))
        git_commit(repo, "implement: advance lifecycle record")
    git_push(repo, branch)
    return work, repo, base_sha, branch


def run_cycle_step(steps, repo, base_sha, *, verdict, cycle_result,
                    iteration=ITERATION):
    runner_temp = tempfile.mkdtemp(dir=os.path.dirname(repo))
    checked_base, _, _ = checkbox_count_env(repo, base_sha)
    checked_tip, unchecked_tip, items_tip = checkbox_count_env(repo, f"origin/{SPEC_PREFIX}{SLUG}")
    env = {"SLUG": SLUG, "SPEC_DIR": SPEC_DIR, "ITERATION": str(iteration),
           "BASE_SHA": base_sha, "CYCLE_RESULT": cycle_result,
           "VERDICT": verdict, "SPEC_PREFIX": SPEC_PREFIX,
           "AGENT_AUTHOR_RE": AGENT_AUTHOR_RE,
           "DEFAULT_BRANCH": "main",
           "CHECKED_BASE": checked_base, "CHECKED_TIP": checked_tip,
           "UNCHECKED_TIP": unchecked_tip, "REMAINING_TIP": items_tip}
    env.update(read_spec_meta_env(repo))
    return run_step(BASH, steps[CYCLE_STEP], repo, env, runner_temp)


def run_retry_step(steps, repo, base_sha, *, verdict, retry_result):
    """Runs "Read back retry outcome" against the SAME fixture repo/base a
    run_cycle_step call already used, to prove the two arms compute
    `converged` from one shared definition (FR-007) rather than two copies
    that could drift -- US2 acceptance scenario 3."""
    runner_temp = tempfile.mkdtemp(dir=os.path.dirname(repo))
    checked_base, _, _ = checkbox_count_env(repo, base_sha)
    checked_tip, unchecked_tip, items_tip = checkbox_count_env(repo, f"origin/{SPEC_PREFIX}{SLUG}")
    env = {"SLUG": SLUG, "SPEC_DIR": SPEC_DIR, "ITERATION": ITERATION,
           "BASE_SHA": base_sha, "RETRY_RESULT": retry_result,
           "VERDICT": verdict, "ESCALATION_MODEL": "claude-opus-5",
           "SPEC_PREFIX": SPEC_PREFIX, "AGENT_AUTHOR_RE": AGENT_AUTHOR_RE,
           "DEFAULT_BRANCH": "main",
           "CHECKED_BASE": checked_base, "CHECKED_TIP": checked_tip,
           "UNCHECKED_TIP": unchecked_tip, "REMAINING_TIP": items_tip}
    env.update(read_spec_meta_env(repo))
    return run_step(BASH, steps[RETRY_STEP], repo, env, runner_temp)


# ---------------------------------------------------------------------------
# Scenarios (contracts/convergence-signal.md, data-model.md's decision table)
# ---------------------------------------------------------------------------

SIGNAL_SCENARIOS = [
    dict(name="US1: progress made, no converge commit -- not converged",
         base_tasks_md=_tasks_md(0, 3), tip_tasks_md=_tasks_md(1, 2),
         converge=False, verdict="healthy", cycle_result="success",
         expect=dict(ok="true", truncated="false", converged="false")),
    dict(name="US2 acceptance scenario 1: CYCLE_RESULT=success and VERDICT "
              "claim the run finished, but tasks remain -- not converged "
              "regardless of what the agent's own verdict says (T005/T007 "
              "never read CYCLE_RESULT/VERDICT to decide converged; this "
              "fixture pins that against a future regression)",
         base_tasks_md=_tasks_md(0, 2), tip_tasks_md=_tasks_md(1, 1),
         converge=False, verdict="healthy", cycle_result="success",
         expect=dict(ok="true", truncated="false", converged="false")),
    dict(name="SC-004 / US2 acceptance scenario 2: zero unchecked tasks at "
              "the tip -- converged regardless of verdict wording",
         base_tasks_md=_tasks_md(0, 3), tip_tasks_md=_tasks_md(3, 0),
         converge=False, verdict="healthy", cycle_result="success",
         expect=dict(ok="true", truncated="false", converged="true")),
    dict(name="FR-004: a '- [ ]' inside a fenced code block is not counted",
         base_tasks_md=FENCE_TASKS_MD_BASE, tip_tasks_md=FENCE_TASKS_MD_TIP,
         converge=False, verdict="healthy", cycle_result="success",
         expect=dict(ok="true", truncated="false", converged="true")),
    dict(name="SC-003: spec-057 replay -- 11 of 65 ticked, no converge "
              "commit, healthy exit -- not converged",
         base_tasks_md=_tasks_md(0, 65), tip_tasks_md=_tasks_md(11, 54),
         converge=False, verdict="healthy", cycle_result="success",
         expect=dict(ok="true", truncated="false", converged="false")),
    dict(name="US4/FR-010: zero progress, no converge commit -- hand off "
              "to finalize rather than looping to the cap",
         base_tasks_md=_tasks_md(0, 3), tip_tasks_md=_tasks_md(0, 3),
         converge=False, verdict="healthy", cycle_result="success",
         expect=dict(ok="true", truncated="false", converged="false",
                     progressed="false", handoff="true")),
    dict(name="US4/FR-010: zero progress but a converge commit landed -- "
              "new work exists, NOT the FR-010 hand-off",
         base_tasks_md=_tasks_md(0, 3),
         tip_tasks_md=_tasks_md(0, 3) + "- [ ] C001 leftover item\n",
         converge=True, verdict="healthy", cycle_result="success",
         expect=dict(ok="true", truncated="false", converged="false",
                     progressed="false", handoff="false")),
    dict(name="FR-010a: a cycle that ticks one task and unticks another -- "
              "no progress, even though a box moved",
         base_tasks_md="- [x] T001 done\n- [ ] T002 todo\n- [ ] T003 todo\n",
         tip_tasks_md="- [ ] T001 todo\n- [x] T002 done\n- [ ] T003 todo\n",
         converge=False, verdict="healthy", cycle_result="success",
         expect=dict(ok="true", truncated="false", progressed="false")),
]

SCENARIOS_BY_NAME = {s["name"]: s for s in SIGNAL_SCENARIOS}


def run_cycle_scenario(steps, scenario, root):
    """(rc, out, outputs, failures) for one SIGNAL_SCENARIOS entry."""
    work, repo, base_sha, _ = build_scenario(
        root, base_tasks_md=scenario["base_tasks_md"],
        tip_tasks_md=scenario["tip_tasks_md"],
        converge=scenario["converge"])
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
    for scenario in SIGNAL_SCENARIOS:
        _, _, _, f = run_cycle_scenario(steps, scenario, root)
        failures.extend(f)
    return failures


ARMS_AGREE_FIXTURE = dict(base_tasks_md=_tasks_md(0, 3), tip_tasks_md=_tasks_md(1, 2))


def check_arms_agree(steps, root):
    """US2 acceptance scenario 3 / FR-007: the primary and retry arms share
    ONE definition, never two copies that could drift. Drives the
    IDENTICAL fixture (same base, same tip) through both arms' shipped
    step bodies and asserts a byte-identical `converged` verdict. Also the
    target Phase 7's "mutation applied to only one arm" proof mutates
    (SC-008)."""
    failures = []
    work, repo, base_sha, _ = build_scenario(
        root, base_tasks_md=ARMS_AGREE_FIXTURE["base_tasks_md"],
        tip_tasks_md=ARMS_AGREE_FIXTURE["tip_tasks_md"], converge=False)
    rc_c, out_c, outputs_c, _ = run_cycle_step(
        steps, repo, base_sha, verdict="healthy", cycle_result="success")
    rc_r, out_r, outputs_r, _ = run_retry_step(
        steps, repo, base_sha, verdict="healthy", retry_result="success")
    if rc_c != 0 or rc_r != 0:
        failures.append(f"US2 arms-agree fixture: cycle rc={rc_c}, retry "
                        f"rc={rc_r} (expected both 0). cycle out={out_c!r} "
                        f"retry out={out_r!r}")
        return failures
    if outputs_c.get("converged") != outputs_r.get("converged"):
        failures.append(f"US2/FR-007: the primary and retry arms disagreed "
                        f"on converged for the identical fixture -- "
                        f"primary={outputs_c.get('converged')!r}, "
                        f"retry={outputs_r.get('converged')!r}.")
    return failures


FENCE_AWK_MARKER = "in_fence = !in_fence"


def check_single_home_no_pasted_idiom():
    """US2 / research.md D2's closing paragraph: no third hand-rolled copy
    of the fence-aware checkbox-counting awk idiom (T002's one home) is
    pasted into implement.yml now that the composite exists -- modeled on
    Gate 61's verify-spec-meta-single-home.py. Distinct from Gate 30's own
    pre-existing Arm-A `grep -c '^\\s*- \\[[xX]\\]'` comparison, which is a
    different (non-fence-aware) idiom Phase 5 replaces separately."""
    text = open(STAGE, encoding="utf-8").read()
    if FENCE_AWK_MARKER in text:
        return [f"{STAGE} contains the fence-aware checkbox-counting awk "
                f"idiom ({FENCE_AWK_MARKER!r}) -- the one home is "
                f"{COUNT_TASKS_CHECKBOXES}; call the "
                f"wing-commander-tasks-checkbox-count composite instead of "
                f"pasting a third copy into the workflow."]
    return []


def check_unreadable_tasks_md(root):
    """FR-006/Principle VIII: a ref:path the shared script cannot read
    fails loudly, never resolving as a count of zero (which would read as
    "converged" -- exactly the false pass a scan that cannot reach its
    subject must not produce). Runs the REAL shared script against a ref
    that does not exist, and confirms the composite's own step carries no
    continue-on-error or exit-code swallow that would hide that failure
    from the job."""
    failures = []
    work, repo, _, _ = make_workspace(root, _tasks_md(0, 1))
    script = os.path.abspath(COUNT_TASKS_CHECKBOXES).replace("\\", "/")
    proc = sh(f"cd '{repo}' && bash '{script}' 'refs/heads/does-not-exist' '{SPEC_DIR}/tasks.md'", repo)
    if proc.returncode == 0:
        failures.append("count-tasks-checkboxes.sh exited 0 against an unreadable "
                        "ref:path -- FR-006 requires a loud failure, never a quiet "
                        "zero count.")
    if "count-tasks-checkboxes.sh" not in proc.stderr:
        failures.append(f"count-tasks-checkboxes.sh's failure carried no message on "
                        f"stderr identifying what it could not read (got stderr={proc.stderr!r}).")

    doc = yaml.safe_load(open(COMPOSITE, encoding="utf-8")) or {}
    step = None
    for s in (doc.get("runs") or {}).get("steps") or []:
        if (s or {}).get("id") == "read":
            step = s
            break
    if step is None:
        failures.append(f"{COMPOSITE}: no step id 'read' found -- the gate's own "
                        f"target moved, update GATE_PREFIX/COMPOSITE together.")
    else:
        if str(step.get("continue-on-error", "")).strip().lower() == "true":
            failures.append(f"{COMPOSITE}: its step carries continue-on-error: true "
                            f"-- a failing shared-script call would be swallowed "
                            f"instead of failing the job (FR-006).")
        run_text = str(step.get("run", ""))
        if "|| true" in run_text or "|| :" in run_text:
            failures.append(f"{COMPOSITE}: its run: block swallows the shared "
                            f"script's exit code (FR-006).")
    return failures


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
    """Drives the shipped "Dispatch next step" text with a stubbed `gh`,
    recording every invocation (and the last posted --body) so a test can
    assert which workflow was dispatched with which payload and comment
    text (mirrors verify-truncated-cycle-carry-forward.py's identical
    helper)."""
    workdir = tempfile.mkdtemp(dir=root)
    runner_temp = os.path.join(workdir, "runner_temp")
    bindir = os.path.join(workdir, "bin")
    calls_file = os.path.join(workdir, "gh_calls")
    body_file = os.path.join(workdir, "gh_body")
    os.makedirs(runner_temp, exist_ok=True)
    os.makedirs(bindir, exist_ok=True)
    open(calls_file, "w").close()
    open(body_file, "w").close()
    with open(os.path.join(bindir, "gh"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(GH_STUB)
    os.chmod(os.path.join(bindir, "gh"), 0o755)
    env = {
        "SPEC_DIR": SPEC_DIR, "ISSUE": "999", "ITERATION": "2", "MAX": "5",
        "CONVERGED": "false", "TRUNCATED": "false", "TRUNCATED_COUNT": "0",
        "HANDOFF": "false", "REASON": "the cycle ended with tasks outstanding",
        "TIER": "claude-sonnet-5", "REMAINING": "- [ ] T099 leftover",
        "SELF_WORKFLOW": "wing-commander-5-implement.yml", "NEXT_WORKFLOW": "wing-commander-6-finalize.yml",
        "APP_TOKEN": "x", "DISPATCH_TOKEN": "x",
        "GH_CALLS": calls_file, "GH_BODY_FILE": body_file,
        "GITHUB_SERVER_URL": "https://example.invalid",
        "GITHUB_REPOSITORY": "acme/repo", "GITHUB_RUN_ID": "1",
        "PATH": bindir + os.pathsep + os.environ["PATH"],
    }
    env.update(env_overrides)
    rc, out, outputs, summary = run_step(BASH, steps[DISPATCH_STEP], workdir,
                                         env, runner_temp)
    with open(calls_file, encoding="utf-8") as fh:
        calls = fh.read()
    with open(body_file, encoding="utf-8") as fh:
        body = fh.read()
    return rc, out, outputs, calls, body, summary


def check_dispatch_next_cycle(steps, root):
    """FR-019: unchecked tasks with progress and no converge commit ⇒
    false, next cycle dispatched -- the plain below-cap self-dispatch
    branch, unaffected by this feature's HANDOFF branch, still fires."""
    failures = []
    rc, out, outputs, calls, body, summary = run_dispatch_step(
        steps, {"CONVERGED": "false", "TRUNCATED": "false", "HANDOFF": "false",
                "ITERATION": "2", "MAX": "5"}, root)
    if rc != 0:
        failures.append(f"check_dispatch_next_cycle: {DISPATCH_STEP!r} exited {rc}: {out.strip()}")
    elif "wing-commander-5-implement.yml" not in calls:
        failures.append(f"FR-019: progress + no converge commit did not dispatch "
                        f"the next cycle (SELF_WORKFLOW) -- gh calls were: {calls!r}")
    return failures


def check_dispatch_cap_reached(steps, root):
    """FR-012/FR-013: the at-cap, non-truncated, non-handoff branch (the
    shared post_handoff_remaining_work body, D4) still dispatches finalize
    with converged=false, posts the reason, and never an empty remaining
    block -- the same assertions check_dispatch_handoff makes for the
    HANDOFF branch, made here for its sibling caller of the same shared
    function."""
    failures = []
    rc, out, outputs, calls, body, summary = run_dispatch_step(
        steps, {"CONVERGED": "false", "TRUNCATED": "false", "HANDOFF": "false",
                "ITERATION": "5", "MAX": "5",
                "REASON": "the cycle ended with tasks outstanding"}, root)
    if rc != 0:
        failures.append(f"check_dispatch_cap_reached: {DISPATCH_STEP!r} exited {rc}: {out.strip()}")
        return failures
    if "wing-commander-6-finalize.yml" not in calls or "converged=false" not in calls:
        failures.append(f"cap-reached branch did not dispatch NEXT_WORKFLOW with "
                        f"converged=false -- gh calls were: {calls!r}")
    if "wing-commander-5-implement.yml" in calls:
        failures.append(f"cap-reached branch wrongly dispatched a next cycle -- "
                        f"gh calls were: {calls!r}")
    if "the cycle ended with tasks outstanding" not in body:
        failures.append(f"FR-013: the cap-reached comment did not carry the "
                        f"reason narrative -- body={body!r}")
    if "T099 leftover" not in body:
        failures.append(f"FR-012: the cap-reached comment did not carry the "
                        f"remaining-work text -- body={body!r}")
    return failures


def check_dispatch_handoff(steps, root):
    """T020/US4: "Dispatch next step" posts the remaining work and
    dispatches finalize with converged=false when HANDOFF=true, and takes
    that branch even when ITERATION < MAX (the reused terminal path,
    contracts/convergence-signal.md §4) -- never a next-cycle
    self-dispatch."""
    failures = []
    rc, out, outputs, calls, body, summary = run_dispatch_step(
        steps, {"CONVERGED": "false", "TRUNCATED": "false", "HANDOFF": "true",
                "ITERATION": "2", "MAX": "5",
                "REASON": "the cycle checked nothing new, so the loop is ending here rather than dispatching another cycle"}, root)
    if rc != 0:
        failures.append(f"check_dispatch_handoff: {DISPATCH_STEP!r} exited {rc}: {out.strip()}")
        return failures
    if "wing-commander-6-finalize.yml" not in calls or "converged=false" not in calls:
        failures.append(f"US4/FR-010: HANDOFF=true did not dispatch NEXT_WORKFLOW "
                        f"with converged=false -- gh calls were: {calls!r}")
    if "wing-commander-5-implement.yml" in calls:
        failures.append(f"US4/FR-010: HANDOFF=true wrongly dispatched a next cycle "
                        f"(SELF_WORKFLOW) instead of handing off -- gh calls were: {calls!r}")
    if "checked nothing new" not in body:
        failures.append(f"FR-013: the HANDOFF comment did not carry the hand-off "
                        f"reason phrasing -- body={body!r}")
    return failures


def check_remaining_work_report(steps, root):
    """FR-012/FR-013/SC-006: the remaining-work text is the tip's own
    outstanding items (D6), never empty on the no-converge-commit path,
    and the reason narrative names why -- without double-reporting the
    same task list when both a converge commit and outstanding progress
    fire at once."""
    failures = []

    work, repo, base_sha, _ = build_scenario(
        root, base_tasks_md=_tasks_md(0, 3), tip_tasks_md=_tasks_md(1, 2),
        converge=False)
    rc, out, outputs, _ = run_cycle_step(
        steps, repo, base_sha, verdict="healthy", cycle_result="success")
    if rc != 0:
        failures.append(f"check_remaining_work_report(a): {CYCLE_STEP!r} exited {rc}: {out.strip()}")
    else:
        if not outputs.get("remaining", "").strip():
            failures.append("FR-012: the no-converge-commit path rendered an EMPTY remaining block.")
        if "tasks outstanding" not in outputs.get("reason", ""):
            failures.append(f"FR-013: reason did not name tasks outstanding -- "
                            f"got {outputs.get('reason')!r}")

    # A converge commit appends a phase whose own tasks are unchecked, AND
    # this cycle also made progress on pre-existing tasks -- both reasons
    # fire at once; the appended item's text must be listed exactly once
    # (SC-006's "must not report the same work twice").
    base_md = _tasks_md(0, 3)
    tip_md = _tasks_md(1, 2) + "- [ ] C001 leftover item\n"
    work, repo, base_sha, _ = build_scenario(
        root, base_tasks_md=base_md, tip_tasks_md=tip_md, converge=True)
    rc, out, outputs, _ = run_cycle_step(
        steps, repo, base_sha, verdict="healthy", cycle_result="success")
    if rc != 0:
        failures.append(f"check_remaining_work_report(b): {CYCLE_STEP!r} exited {rc}: {out.strip()}")
    else:
        remaining = outputs.get("remaining", "")
        reason = outputs.get("reason", "")
        if "converge appended new work" not in reason or "tasks outstanding" not in reason:
            failures.append(f"FR-013: the both-reasons-fire case did not name both "
                            f"reasons -- got reason={reason!r}")
        count = remaining.count("C001 leftover item")
        if count != 1:
            failures.append(f"SC-006: the appended item was listed {count} time(s), "
                            f"not exactly once -- remaining={remaining!r}")
    return failures


CONVERGED_DECISION = (
    '  if [ "${UNCHECKED_TIP:-1}" -eq 0 ]; then\n'
    '    converged=true\n'
    '  else\n'
    '    converged=false\n'
    '  fi\n'
)
PROGRESS_TEST = (
    '  if [ "${CHECKED_TIP:-0}" -gt "${CHECKED_BASE:-0}" ]; then\n'
    '    progressed=true\n'
    '  else\n'
    '    progressed=false\n'
    '  fi\n'
)


def _mut_converge_sha_only(steps):
    """FR-020(a): revert the decision to consult only converge_sha (spec
    057's exact bug) -- must flip the US1 no-converge-commit scenario's
    converged from false back to (wrongly) true."""
    steps[CYCLE_STEP] = steps[CYCLE_STEP].replace(
        CONVERGED_DECISION,
        '  if [ -z "$converge_sha" ]; then\n'
        '    converged=true\n'
        '  else\n'
        '    converged=false\n'
        '  fi\n', 1)


def _mut_one_arm_only(steps):
    """FR-020(b): a regression applied to only ONE arm -- the cycle arm
    always reports converged=true regardless of tasks.md, the retry arm is
    untouched. Must flip check_arms_agree's identical fixture to a
    cycle/retry DISAGREEMENT, proving the gate attributes a one-arm-only
    regression rather than merely re-checking the cycle arm alone."""
    steps[CYCLE_STEP] = steps[CYCLE_STEP].replace(
        CONVERGED_DECISION, '  converged=true\n', 1)


def _mut_drop_progress_test(steps):
    """FR-020(c): remove/invert the FR-010 progress test -- checked-count
    rising against base always reads as progressed=true, so the
    zero-progress hand-off scenario wrongly reports progressed=true and
    handoff=false instead of handing off."""
    steps[CYCLE_STEP] = steps[CYCLE_STEP].replace(
        PROGRESS_TEST, '  progressed=true\n', 1)


MUTATIONS = [
    ("revert to consulting only converge_sha (spec 057's exact bug)",
     _mut_converge_sha_only,
     "US1: progress made, no converge commit -- not converged",
     {"converged": "true"}),
    ("remove/invert the FR-010 progress test",
     _mut_drop_progress_test,
     "US4/FR-010: zero progress, no converge commit -- hand off "
     "to finalize rather than looping to the cap",
     {"progressed": "true", "handoff": "false"}),
]


def check_one_arm_mutation(steps, root):
    """FR-020(b): see _mut_one_arm_only's docstring."""
    mutated = copy.deepcopy(steps)
    _mut_one_arm_only(mutated)
    if mutated[CYCLE_STEP] == steps[CYCLE_STEP]:
        print("::error::mutation 'one-arm-only regression' changed nothing -- "
              "the code it edits was rewritten. Update the mutation so this "
              "harness keeps proving it can fail.")
        return ["mutation inapplicable: one-arm-only regression"]
    work, repo, base_sha, _ = build_scenario(
        root, base_tasks_md=ARMS_AGREE_FIXTURE["base_tasks_md"],
        tip_tasks_md=ARMS_AGREE_FIXTURE["tip_tasks_md"], converge=False)
    rc_c, out_c, outputs_c, _ = run_cycle_step(
        mutated, repo, base_sha, verdict="healthy", cycle_result="success")
    rc_r, out_r, outputs_r, _ = run_retry_step(
        mutated, repo, base_sha, verdict="healthy", retry_result="success")
    if (rc_c == 0 and rc_r == 0 and outputs_c.get("converged") == "true"
            and outputs_r.get("converged") == "false"):
        print("Mutation OK -- one-arm-only regression: caught (cycle wrongly "
              "reports converged=true while the retry arm, untouched, "
              "correctly reports false).")
        return []
    return [f"mutation survived: one-arm-only regression did not make the "
            f"two arms disagree on the identical fixture (cycle "
            f"converged={outputs_c.get('converged')!r}, retry "
            f"converged={outputs_r.get('converged')!r}, rc_c={rc_c}, rc_r={rc_r})"]


def run_mutations(steps, root):
    failures = []
    for label, apply_mutation, target_name, expect_wrong in MUTATIONS:
        mutated = copy.deepcopy(steps)
        apply_mutation(mutated)
        if mutated[CYCLE_STEP] == steps[CYCLE_STEP]:
            print(f"::error::mutation {label!r} changed nothing -- the code "
                  f"it edits was rewritten. Update the mutation so this "
                  f"harness keeps proving it can fail.")
            failures.append(f"mutation inapplicable: {label}")
            continue
        scenario = SCENARIOS_BY_NAME[target_name]
        rc, out, outputs, _ = run_cycle_scenario(mutated, scenario, root)
        wrong = rc == 0 and all(outputs.get(k) == v for k, v in expect_wrong.items())
        if wrong:
            print(f"Mutation OK -- {label}: caught (now wrongly reports {expect_wrong}).")
        else:
            print(f"::error::MUTATION SURVIVED -- reintroducing {label!r} did "
                  f"not flip scenario {target_name!r} to {expect_wrong} (got "
                  f"rc={rc}, outputs={outputs}, out={out!r}). Fix the "
                  f"scenarios, not the mutation.")
            failures.append(f"mutation survived: {label}")
    failures.extend(check_one_arm_mutation(steps, root))
    return failures


def check_gate_wired():
    """FR-020's reflexive check (mirrors Gate 30's own check_gate_wired):
    this script cannot see its own absence from a workflow it isn't in, so
    it reads lint-workflows.yml directly and confirms Gate 81 is present,
    enabled, and invokes this script by path."""
    wf = yaml.safe_load(open(LINT_WORKFLOW, encoding="utf-8")) or {}
    for job in (wf.get("jobs") or {}).values():
        for step in (job or {}).get("steps") or []:
            name = (step or {}).get("name") or ""
            if name.startswith(GATE_PREFIX):
                if str(step.get("if", "")).strip().lower() == "false":
                    return [f"{GATE_PREFIX} step is present in {LINT_WORKFLOW} "
                            f"but disabled (if: false) -- its own coverage "
                            f"would not run (FR-020)."]
                if THIS_SCRIPT not in str(step.get("run", "")):
                    return [f"{GATE_PREFIX} step in {LINT_WORKFLOW} does not "
                            f"invoke {THIS_SCRIPT} -- the gate registry entry "
                            f"and this script have drifted apart (FR-020)."]
                return []
    return [f"no step named {GATE_PREFIX!r} found in {LINT_WORKFLOW} -- this "
            f"script's own coverage would not run if it were dropped from "
            f"the registry (FR-020)."]


STEPS_CACHE = {}


def load_steps():
    for name in (CYCLE_STEP, RETRY_STEP, FINAL_STEP, DISPATCH_STEP):
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
        failures.extend(check_arms_agree(steps, root))
        failures.extend(check_single_home_no_pasted_idiom())
        failures.extend(check_unreadable_tasks_md(root))
        failures.extend(check_dispatch_next_cycle(steps, root))
        failures.extend(check_dispatch_cap_reached(steps, root))
        failures.extend(check_dispatch_handoff(steps, root))
        failures.extend(check_remaining_work_report(steps, root))
        failures.extend(run_mutations(steps, root))
        failures.extend(check_gate_wired())
    finally:
        shutil.rmtree(root, ignore_errors=True)

    print(f"tasks-checkbox convergence signal: {len(SIGNAL_SCENARIOS)} "
          f"scenario(s); {len(failures)} failure(s).")
    for f in failures:
        print(f"::error::{f}")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
