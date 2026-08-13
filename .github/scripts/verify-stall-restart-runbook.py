#!/usr/bin/env python3
"""The stalled-restart runbook hands out a command the guard will accept.

WHY THIS EXISTS
---------------
When implement stalls it posts a runbook telling the maintainer how to restart
it. One step writes that advice; a different step in a different job — the
idempotency guard, which admits a `stalled` stage only at `recorded + 1` —
decides whether it works. Nothing tied the two together and they disagreed:
the runbook printed the iteration that had just failed, so every restart
command was classified as a duplicate dispatch.

It fails silently. `skip=true` turns each later step's `if:` false, so the run
REPORTS SUCCESS in ~11s, posts nothing to the lifecycle issue, and leaves the
watchdog no failed conclusion. Seen on #184: run 31596632026 (iteration=1, as
advised — green no-op) vs 31597726542 (iteration=2 — runs the agent).

A stall arrives in either of two states, and `recorded` is the ONLY input that
separates them: the failed pass either got its commit in (record advanced to the
dispatched iteration) or did not ("the branch never advanced" — the record still
reads the previous one, or the 0 intake seeds). Advice derived from the
dispatched iteration is admitted in the first and dropped as a duplicate in the
second, which is exactly how the first fix here shipped broken past a green
version of this gate. Hence SCENARIOS below varies the relationship between the
two, not just the number.

WHAT THIS CHECKS
----------------
The round trip, executing the SHIPPED blocks rather than a copy (gate 5 exists
because a copy sat green for weeks while checking a filter that did not ship):

  1. `Mark lifecycle record stalled` against a synthetic spec-meta.json, then
     read back what it recorded — assuming what that file holds is the bug
     class this gate covers. It runs in a real git repo with a local bare
     remote so the step's commit/push path executes for real.
  2. `Report stalled on lifecycle issue`, parsing the runbook it wrote.
  3. That runbook's own advice fed to `Idempotency guard`, requiring
     `skip=false`.

Step 3 is the point: the advice must be ACCEPTED, not equal to a number this
file also hardcodes. Either step can be rewritten freely; the gate fails only
when they stop agreeing. `spec_dir` and `issue` are checked too — a command
naming the wrong spec is equally unrunnable.

Mutations at the end reintroduce the shipped defect and two plausible drifts
and assert the suite fails on each.

Usage: python3 .github/scripts/verify-stall-restart-runbook.py
Requires: bash, jq, git (all present on ubuntu-latest runners).

On Windows, invoke with `python` — `python3` on PATH is usually the Microsoft
Store stub, which exits 49 without running anything. See wc_shell_harness for
why `bash` on PATH is also probed rather than trusted.
"""
import copy
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_shell_harness import (ensure_jq, find_step, resolve_bash, run_step,
                              use_utf8_stdout)

STAGE = ".github/workflows/implement.yml"

MARK_STEP = "Mark lifecycle record stalled"
REPORT_STEP = "Report stalled on lifecycle issue"
GUARD_STEP = "Idempotency guard"

# (recorded, dispatched): what spec-meta.json holds when the stall lands, and
# which iteration was dispatched into that failure. Varying the NUMBER without
# varying the RELATIONSHIP is what let the first fix here ship broken — it read
# the dispatched iteration, which is only the recorded one in the top group.
#
#   recorded == dispatched  the pass recorded its iteration, then failed
#   recorded <  dispatched  the pass never got its push in ("the branch never
#                           advanced" — implement.yml classifies this by name),
#                           so the record still reads the previous iteration;
#                           0 is what intake seeds, i.e. a stall at iteration 1
SCENARIOS = [(1, 1), (2, 2), (4, 4), (0, 1), (2, 3)]

SPEC_DIR = "specs/034-e2e-verification-tier"
SLUG = "034-e2e-verification-tier"
ISSUE = "184"
SELF_WORKFLOW = "wing-commander-5-implement.yml"
REPO = "charlesguse/wing-commander"

BASH = None

# `gh` is called for labels before the runbook is composed; under `bash -e` a
# missing binary would kill the step before it writes anything. Only exit
# status matters here — no call site reads gh's output.
GH_STUB = """#!/bin/sh
echo "gh $*" >> "$GH_CALLS"
exit 0
"""


def sh(script, cwd):
    """Run a helper snippet through the same bash the steps get."""
    path = os.path.join(cwd, "_helper.sh")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(script)
    return subprocess.run([BASH, "-e", path.replace("\\", "/")], cwd=cwd,
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace")


def make_workspace(root, recorded):
    """A git repo with a working remote, holding a pre-stall spec-meta.json.

    The stall step commits and pushes; a real bare remote runs that path
    instead of stubbing git and asserting against a step that wrote nothing.
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
printf '%s\\n' '{{"issue": {ISSUE}, "spec_dir": "{SPEC_DIR}", "stage": "implement", "iteration": {recorded}}}' > '{SPEC_DIR}/spec-meta.json'
git add -A
git commit -q -m seed
git push -q origin main
"""
    proc = sh(setup, work)
    if proc.returncode != 0:
        sys.exit(f"::error::harness could not build a git workspace: "
                 f"{proc.stdout}{proc.stderr}")
    return work, repo


def parse_runbook(text):
    """The dispatch inputs, read from BOTH forms the runbook prints.

    The table and the gh line come from separate echoes, so returning both
    lets the caller require a fix reached each of them.
    """
    row = re.search(r"\|\s*`iteration`\s*\|\s*`([^`]*)`\s*\|", text)
    cmd = re.search(r"gh workflow run\s+(\S+).*?-f\s+spec_dir=(\S+)\s+"
                    r"-f\s+issue=(\S+)\s+-f\s+iteration=(\S+)", text)
    return {
        "table_iteration": row.group(1) if row else None,
        "workflow": cmd.group(1) if cmd else None,
        "spec_dir": cmd.group(2) if cmd else None,
        "issue": cmd.group(3) if cmd else None,
        "cmd_iteration": cmd.group(4) if cmd else None,
    }


def scenario(steps, seeded, iteration, root):
    """One stall-then-restart round trip. Returns a list of failures."""
    failures = []
    where = f"recorded {seeded}, dispatched {iteration}"
    work, repo = make_workspace(root, seeded)
    runner_temp = os.path.join(work, "runner_temp")
    bindir = os.path.join(work, "bin")
    calls = os.path.join(work, "gh_calls")
    os.makedirs(runner_temp, exist_ok=True)
    os.makedirs(bindir, exist_ok=True)
    open(calls, "w").close()
    with open(os.path.join(bindir, "gh"), "w", encoding="utf-8",
              newline="\n") as fh:
        fh.write(GH_STUB)
    os.chmod(os.path.join(bindir, "gh"), 0o755)

    # 1. What the stall actually records — read back, not assumed.
    rc, out, _, _ = run_step(
        BASH, steps[MARK_STEP], repo,
        {"SPEC_DIR": SPEC_DIR, "SLUG": SLUG, "BOT_SLUG": "wing-commander-bot",
         "ITERATION": str(iteration)},
        runner_temp)
    if rc != 0:
        failures.append(f"{where}: {MARK_STEP!r} exited {rc}: {out.strip()}")
        return failures
    with open(os.path.join(repo, SPEC_DIR, "spec-meta.json"),
              encoding="utf-8") as fh:
        meta = json.load(fh)
    if meta.get("stage") != "stalled":
        failures.append(f"{where}: {MARK_STEP!r} left stage="
                        f"{meta.get('stage')!r}, not 'stalled' — the guard's "
                        f"stalled branch cannot be reached at all.")
        return failures
    recorded = meta.get("iteration")
    # The stall commit sets `.stage` alone. If it ever starts writing
    # `.iteration` too, the guard compares against a number no pass produced and
    # the restart rewinds (or skips) the loop.
    if recorded != seeded:
        failures.append(f"{where}: {MARK_STEP!r} changed the recorded iteration "
                        f"from {seeded} to {recorded!r} — only the agent may "
                        f"write it, and the guard compares against it.")
        return failures

    # 2. The runbook the maintainer is told to follow.
    stall_md = os.path.join(work, "stall-comment.md")
    sh("rm -f /tmp/stall-comment.md", work)
    rc, out, _, _ = run_step(
        BASH, steps[REPORT_STEP], repo,
        {"GH_TOKEN": "x", "ISSUE": ISSUE, "ITERATION": str(iteration),
         "SPEC_DIR": SPEC_DIR, "TIER": "claude-opus-5",
         "REASON": "the retry's agent step itself finished 'failure'",
         "AGENT_MSG": "You've hit your session limit",
         "SELF_WORKFLOW": SELF_WORKFLOW, "RUN_URL": "https://example.invalid/r",
         "GITHUB_REPOSITORY": REPO, "GH_CALLS": calls,
         "PATH": bindir + os.pathsep + os.environ["PATH"]},
        runner_temp)
    if rc != 0:
        failures.append(f"{where}: {REPORT_STEP!r} exited {rc}: {out.strip()}")
        return failures
    if sh(f"cp /tmp/stall-comment.md '{stall_md}'", work).returncode != 0:
        failures.append(f"{where}: {REPORT_STEP!r} wrote no runbook to "
                        f"/tmp/stall-comment.md.")
        return failures
    with open(stall_md, encoding="utf-8") as fh:
        advice = parse_runbook(fh.read())

    missing = [k for k, v in advice.items() if v is None]
    if missing:
        failures.append(
            f"{where}: the runbook no longer states {', '.join(missing)} in "
            f"the form this gate reads. If it was reformatted, update "
            f"parse_runbook — dropping the check leaves the restart command "
            f"unverified.")
        return failures

    if advice["table_iteration"] != advice["cmd_iteration"]:
        failures.append(
            f"{where}: the runbook's inputs table says iteration="
            f"{advice['table_iteration']} but its gh command says "
            f"{advice['cmd_iteration']} — whichever the maintainer copies, "
            f"one of them is wrong.")

    for key, want in (("spec_dir", SPEC_DIR), ("issue", ISSUE),
                      ("workflow", SELF_WORKFLOW)):
        if advice[key] != want:
            failures.append(f"{where}: runbook {key}={advice[key]!r}, "
                            f"expected {want!r} — the command names the wrong "
                            f"target and cannot restart this spec.")

    # 3. Does the guard let that advice through?
    for label, value in (("inputs table", advice["table_iteration"]),
                         ("gh command", advice["cmd_iteration"])):
        if not re.fullmatch(r"-?\d+", value or ""):
            failures.append(f"{where}: runbook's {label} iteration "
                            f"{value!r} is not an integer; the guard's "
                            f"`-eq` cannot compare it.")
            continue
        rc, out, outputs, summary = run_step(
            BASH, steps[GUARD_STEP], repo,
            {"STAGE": "stalled", "RECORDED": str(recorded), "ITERATION": value},
            runner_temp)
        if rc != 0:
            failures.append(f"{where}: {GUARD_STEP!r} exited {rc}: "
                            f"{out.strip()}")
            continue
        if outputs.get("skip") != "false":
            failures.append(
                f"{where}: the runbook's {label} tells the maintainer to "
                f"dispatch iteration={value}, but the guard refuses it "
                f"(skip={outputs.get('skip')!r}) against the stage='stalled', "
                f"iteration={recorded} the stall just recorded — the restart "
                f"is a green no-op. Guard said: "
                f"{summary.strip() or '(no summary)'}")
    return failures


def suite(steps, root):
    return [f for seeded, it in SCENARIOS
            for f in scenario(steps, seeded, it, root)]


def load_steps():
    return {name: find_step(STAGE, name)["run"]
            for name in (MARK_STEP, REPORT_STEP, GUARD_STEP)}


def _mut_runbook_prints_failed_iteration(steps):
    """The shipped defect: advise the iteration that just failed."""
    steps[REPORT_STEP] = steps[REPORT_STEP].replace(
        "$restart_iteration", "$ITERATION")


def _mut_guard_wants_two_ahead(steps):
    """Drift on the guard side rather than the runbook side."""
    steps[GUARD_STEP] = steps[GUARD_STEP].replace(
        "next=$((RECORDED + 1))", "next=$((RECORDED + 2))")


def _mut_stall_resets_recorded_iteration(steps):
    """The stall commit stops preserving the iteration the guard compares to."""
    steps[MARK_STEP] = steps[MARK_STEP].replace(
        """jq '.stage = "stalled"'""", """jq '.stage = "stalled" | .iteration = 0'""")


def _mut_runbook_derives_from_dispatched(steps):
    """The first fix's defect: advise dispatched+1 instead of recorded+1.

    Indistinguishable from correct whenever the record advanced, so only the
    lagging-record scenarios can catch it. If this one ever survives, the
    SCENARIOS table has lost its `recorded < dispatched` rows.
    """
    steps[REPORT_STEP] = steps[REPORT_STEP].replace(
        "restart_iteration=$((recorded + 1))",
        "restart_iteration=$((ITERATION + 1))")


MUTATIONS = [
    ("runbook advises the iteration that just failed",
     _mut_runbook_prints_failed_iteration),
    ("runbook advises dispatched+1 rather than recorded+1",
     _mut_runbook_derives_from_dispatched),
    ("guard admits only recorded+2", _mut_guard_wants_two_ahead),
    ("stall commit resets the recorded iteration",
     _mut_stall_resets_recorded_iteration),
]


def main():
    global BASH
    use_utf8_stdout()
    ensure_jq()
    BASH = resolve_bash()
    if not shutil.which("git"):
        sys.exit("::error::git is not on PATH. The shipped step under test "
                 "commits and pushes, so nothing here can run without it.")

    steps = load_steps()
    root = tempfile.mkdtemp()
    try:
        failures = suite(steps, root)
        for f in failures:
            print(f"::error::{f}")

        for label, apply_mutation in MUTATIONS:
            mutated = copy.deepcopy(steps)
            apply_mutation(mutated)
            if mutated == steps:
                print(f"::error::mutation {label!r} changed nothing — the code "
                      f"it edits was rewritten. Update the mutation so this "
                      f"harness keeps proving it can fail.")
                failures.append(f"mutation inapplicable: {label}")
                continue
            if suite(mutated, root):
                print(f"Mutation OK — {label}: caught.")
            else:
                print(f"::error::MUTATION SURVIVED — reintroducing {label} "
                      f"broke nothing in this suite, so the suite is not "
                      f"testing that defect. Fix the scenarios, not the "
                      f"mutation.")
                failures.append(f"mutation survived: {label}")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    print(f"stall restart runbook: {len(SCENARIOS)} round trip(s), "
          f"{len(MUTATIONS)} mutation(s); {len(failures)} failure(s).")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
