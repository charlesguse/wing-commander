#!/usr/bin/env python3
"""Gate 123 - wing-commander-publish-stranded-commits' commits-published
count is driven against real git repositories, not merely asserted from
the rendered notice text a downstream consumer produces.

WHY THIS EXISTS
---------------
verify-chain-stop-notice-body.py (specs/071-agent-push-credential T060)
already proves that a given (commits-published, push-ok) pair renders the
right stall-notice wording, but it feeds those two values in as fixture
strings -- it never exercises the `git rev-list --count` comparison in
wing-commander-publish-stranded-commits/action.yml that actually PRODUCES
them. That comparison has two branches (T060): count commits ahead of
refs/remotes/origin/<branch> when that ref exists, falling back to
`${BEFORE_SHA}..HEAD` only when it does not -- the distinction between
"0 because the agent already pushed everything itself" and "N because
job start is the only reference point available" is exactly the fix T060
shipped, and a fixture that only checks the rendered notice text cannot
tell the two branches apart (both can render the same line from a fixture
value, however that value was computed). This gate drives the SHIPPED
`run:` text of the "Publish stranded commits" step (wc_shell_harness.py,
the same harness Gate 35/69 already use) against a real bare `origin` plus
a clone, so the counting logic itself is exercised, not re-typed.

WHAT THIS CHECKS
----------------
1. Everything already pushed (the agent pushed its own commits before this
   step ever runs, advancing the local refs/remotes/origin/<branch>):
   commits-published=0, push-ok=true, and no rendered notice line follows
   from that (verify-chain-stop-notice-body.py already covers the
   rendering half).
2. Two commits stranded locally, never pushed by anything before this
   step: commits-published=2, push-ok=true, and origin's branch tip
   actually advances to match the local HEAD this step pushed.
3. No refs/remotes/origin/<branch> exists locally at all (a checkout that
   never fetched it): falls back to `${BEFORE_SHA}..HEAD`.
4. --self-test: reverting the comparison to `${BEFORE_SHA}..HEAD`
   unconditionally must break scenario 1 -- with job-start's before-sha
   held fixed while the agent's own two commits are pushed directly (not
   through this step), the unconditional form recounts both of them
   (commits-published=2) instead of recognising they are already on
   origin (commits-published=0).

Usage: python3 .github/scripts/verify-stranded-commit-publish-shell.py [--self-test] [-v]
Requires: bash, jq, git (all present on ubuntu-latest runners).
"""
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_shell_harness import ensure_jq, find_step, resolve_bash, run_step, use_utf8_stdout

ACTION = ".github/actions/wing-commander-publish-stranded-commits/action.yml"
STEP_NAME = "Publish stranded commits"
BRANCH = "spec/999-gate123-fixture"

BASH = None
VERBOSE = "-v" in sys.argv[1:]


def log(*a):
    if VERBOSE:
        print(*a)


def sh(script, cwd):
    path = os.path.join(cwd, "_helper.sh")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(script)
    proc = subprocess.run([BASH, "-e", path.replace("\\", "/")], cwd=cwd,
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace")
    if proc.returncode != 0:
        sys.exit(f"::error::gate123 harness setup failed: {proc.stdout}{proc.stderr}")
    return proc.stdout


def make_workspace(root):
    """A bare `origin` plus a clone checked out on BRANCH, one commit deep.
    Returns (work, remote, runner_temp, initial_sha)."""
    work = tempfile.mkdtemp(dir=root, prefix="work-")
    remote = tempfile.mkdtemp(dir=root, prefix="origin-")
    runner_temp = os.path.join(root, "runner_temp")
    os.makedirs(runner_temp, exist_ok=True)
    out = sh(f"""
git init -q --bare -b main '{remote}'
git clone -q '{remote}' '{work}'
cd '{work}'
git config user.email gate123@example.invalid
git config user.name gate123
echo one > f.txt
git add f.txt
git commit -q -m init
git checkout -q -b '{BRANCH}'
git push -q -u origin '{BRANCH}'
git rev-parse HEAD
""", root)
    initial_sha = out.strip().splitlines()[-1]
    return work, remote, runner_temp, initial_sha


def run_publish(work, runner_temp, before_sha, action_path=ACTION):
    step = find_step(action_path, STEP_NAME)
    script = step["run"]
    # spec 095: the step sources _shared/git-push-hardening.sh beside the
    # shipped composite, so the action path is the real one even when the
    # step text under test is a mutated copy.
    env_extra = {"BEFORE_SHA": before_sha, "WORKDIR": "", "PUSH_TOKEN": "", "PUSH_REPO": "",
                 "GITHUB_ACTION_PATH": os.path.dirname(os.path.abspath(ACTION))}
    rc, out, outputs, _ = run_step(BASH, script, work, env_extra, runner_temp)
    log(out)
    return rc, out, outputs


def scenario_everything_already_pushed(root, action_path=ACTION):
    """The agent pushes its own two commits directly (a real `git push`,
    advancing the local refs/remotes/origin/<branch>) before this step ever
    runs -- job-start's before-sha still names the ORIGINAL commit, so the
    unconditional before-sha..HEAD comparison this scenario's mutation
    reintroduces would recount both; the shipped origin-ref comparison
    reports 0."""
    failures = []
    where = "scenario: everything already pushed"
    work, remote, runner_temp, before_sha = make_workspace(root)
    sh(f"""
cd '{work}'
git commit -q --allow-empty -m "agent commit 1"
git commit -q --allow-empty -m "agent commit 2"
git push -q origin '{BRANCH}'
""", root)
    rc, out, outputs = run_publish(work, runner_temp, before_sha, action_path=action_path)
    if rc != 0:
        failures.append(f"{where}: {STEP_NAME!r} exited {rc}: {out}")
        return failures
    if outputs.get("commits-published") != "0":
        failures.append(f"{where}: commits-published={outputs.get('commits-published')!r}, expected '0'")
    if outputs.get("push-ok") != "true":
        failures.append(f"{where}: push-ok={outputs.get('push-ok')!r}, expected 'true'")
    return failures


def scenario_two_stranded_commits(root):
    failures = []
    where = "scenario: 2 stranded commits"
    work, remote, runner_temp, before_sha = make_workspace(root)
    sh(f"""
cd '{work}'
git commit -q --allow-empty -m "stranded 1"
git commit -q --allow-empty -m "stranded 2"
""", root)
    rc, out, outputs = run_publish(work, runner_temp, before_sha)
    if rc != 0:
        failures.append(f"{where}: {STEP_NAME!r} exited {rc}: {out}")
        return failures
    if outputs.get("commits-published") != "2":
        failures.append(f"{where}: commits-published={outputs.get('commits-published')!r}, expected '2'")
    if outputs.get("push-ok") != "true":
        failures.append(f"{where}: push-ok={outputs.get('push-ok')!r}, expected 'true'")
    remote_head = sh(f"git rev-parse '{BRANCH}'", remote).strip()
    local_head = sh("git rev-parse HEAD", work).strip()
    if remote_head != local_head:
        failures.append(f"{where}: origin/{BRANCH} ({remote_head}) does not "
                        f"match the pushed local HEAD ({local_head}) -- "
                        f"the step's own push did not actually land.")
    return failures


def scenario_no_remote_tracking_ref(root):
    """No refs/remotes/origin/<branch> exists locally at all -- falls back
    to `${BEFORE_SHA}..HEAD`."""
    failures = []
    where = "scenario: no remote-tracking ref (before-sha fallback)"
    work, remote, runner_temp, before_sha = make_workspace(root)
    sh(f"""
cd '{work}'
git commit -q --allow-empty -m "local only, never fetched"
git update-ref -d 'refs/remotes/origin/{BRANCH}'
""", root)
    rc, out, outputs = run_publish(work, runner_temp, before_sha)
    if rc != 0:
        failures.append(f"{where}: {STEP_NAME!r} exited {rc}: {out}")
        return failures
    if outputs.get("commits-published") != "1":
        failures.append(f"{where}: commits-published={outputs.get('commits-published')!r}, "
                        f"expected '1' (the before-sha..HEAD fallback)")
    return failures


SCENARIOS = [scenario_everything_already_pushed, scenario_two_stranded_commits,
             scenario_no_remote_tracking_ref]


def run_scenarios(root):
    failures = []
    for scenario in SCENARIOS:
        failures += scenario(root)
    return failures


MUTATION_MARKER = (
    'if git rev-parse --verify --quiet "refs/remotes/origin/$branch" >/dev/null; then\n'
    '            count="$(git rev-list --count "refs/remotes/origin/${branch}..HEAD" 2>/dev/null)" || count=0\n'
    '          else\n'
    '            count="$(git rev-list --count "${BEFORE_SHA}..HEAD" 2>/dev/null)" || count=0\n'
    '          fi')
MUTATION_REPLACEMENT = 'count="$(git rev-list --count "${BEFORE_SHA}..HEAD" 2>/dev/null)" || count=0'


def self_test():
    problems = []

    root = tempfile.mkdtemp(prefix="gate123-clean-")
    try:
        clean = run_scenarios(root)
    finally:
        shutil.rmtree(root, ignore_errors=True)
    if clean:
        problems.append("clean scenarios FAILED: " + "; ".join(clean))
    else:
        print(f"[ok] {len(SCENARIOS)} clean scenario(s) pass")

    with open(ACTION, encoding="utf-8") as fh:
        text = fh.read()
    if MUTATION_MARKER not in text:
        problems.append(
            "self-test mutation (d): could not find the origin-ref "
            "comparison block in " + ACTION + " to mutate -- the shell was "
            "rewritten; update this gate's MUTATION_MARKER to match.")
    else:
        mut_dir = tempfile.mkdtemp(prefix="gate123-mut-")
        try:
            mutated_action = os.path.join(mut_dir, "action.yml")
            with open(mutated_action, "w", encoding="utf-8") as fh:
                fh.write(text.replace(MUTATION_MARKER, MUTATION_REPLACEMENT))
            ws = tempfile.mkdtemp(prefix="gate123-mutws-")
            try:
                broke = scenario_everything_already_pushed(ws, action_path=mutated_action)
            finally:
                shutil.rmtree(ws, ignore_errors=True)
            if broke:
                print(f"[ok] reverting to BEFORE_SHA..HEAD unconditionally: "
                     f"{len(broke)} assertion(s) fail.")
            else:
                problems.append(
                    "MUTATION SURVIVED -- reverting the comparison to "
                    "BEFORE_SHA..HEAD unconditionally did not break the "
                    "'everything already pushed' scenario.")
        finally:
            shutil.rmtree(mut_dir, ignore_errors=True)

    for p in problems:
        print(f"::error::Gate 123 self-test: {p}")
    if problems:
        return 1
    print("Gate 123 self-test: clean scenarios pass; the documented mutation fails.")
    return 0


def main():
    global BASH
    use_utf8_stdout()
    ensure_jq()
    BASH = resolve_bash()
    if not shutil.which("git"):
        sys.exit("::error::git is not on PATH. The shipped step under test "
                 "commits and pushes, so nothing here can run without it.")

    if "--self-test" in sys.argv[1:]:
        return self_test()

    root = tempfile.mkdtemp(prefix="gate123-")
    try:
        failures = run_scenarios(root)
    finally:
        shutil.rmtree(root, ignore_errors=True)
    for f in failures:
        print(f"::error::Gate 123: {f}")
    print(f"Gate 123: stranded-commit-publish shell; {len(SCENARIOS)} "
          f"scenario(s), {len(failures)} failure(s).")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
