#!/usr/bin/env python3
"""board-loop.yml's review-fixup push holds a workflow-file follow-up for a
maintainer, and never advances the round on a push that did not land.

WHY THIS EXISTS
---------------
The review job's "Push the follow-up commit and advance the round" step had
no workflow-scope hold (found by the code review of #901, on #889). The fix
job holds a change to `.github/workflows/` under board:stalled before
GitHub refuses the push (the App holds no Workflows permission);
review-fixup's own commit went straight to `git push`, so every later run
resumed into the same refusal.

The harness also pins the refused-push path: the step's default shell is
`bash -e`, so a refused push stops it before the round advances, and the
annotation names why.

Spec 095 moved review-fixup's push into the review-fixup-publish job and
split it into three steps: the hold (HOLD_STEP), the push through the
wing-commander-hardened-push composite, and the round advance
(ADVANCE_STEP), which runs only on `steps.push.outcome == 'success'`.

This harness EXECUTES the shipped hold and advance steps through
wc_shell_harness.run_step, and the composite's body
(_shared/hardened-push.sh) between them the way the composite runs it,
against a real local git origin, with the real board_item_marker.py staged
where the steps expect their pristine copy and a `gh` stub that records
each call. A push refusal is a real one: the origin's pre-receive hook
rejects it. Each MUTATION reverts one fix and asserts the suite then fails.

Usage: python3 .github/scripts/verify-board-review-fixup-push.py
Requires: bash, git, python3.
"""
import os
import shutil
import stat
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from wc_shell_harness import find_step, resolve_bash, run_step, use_utf8_stdout  # noqa: E402

BOARD_LOOP = ".github/workflows/board-loop.yml"
HOLD_STEP = "Hold a workflow-file follow-up for a maintainer (review-fixup)"
ADVANCE_STEP = "Advance the round"
ADVANCE_IF = "steps.push.outcome == 'success'"
HARDENED_PUSH = os.path.join(HERE, "..", "actions", "_shared", "hardened-push.sh")
BRANCH = "board/fix-7"

STUB_GH = '#!/usr/bin/env bash\nprintf "%s\\n" "$*" >> "$STUB_LOG"\nexit 0\n'

BASH = None
failures = []


def check(name, cond, detail=""):
    if cond:
        print("[ok] {0}".format(name))
    else:
        failures.append(name)
        print("::error::verify-board-review-fixup-push: {0} -- {1}".format(name, detail))


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                          text=True).stdout.strip()


def build(tmp, touched, refuse):
    """A PR branch on a local origin, and a work tree one fixup commit ahead
    that touches `touched`. Returns (work, origin, reviewed_sha)."""
    origin = os.path.join(tmp, "origin.git")
    work = os.path.join(tmp, "work")
    git(tmp, "init", "-q", "--bare", origin)
    git(tmp, "init", "-q", "-b", "main", work)
    for k, v in (("user.email", "h@example.invalid"), ("user.name", "harness"),
                 ("commit.gpgsign", "false")):
        git(work, "config", k, v)
    os.makedirs(os.path.join(work, ".github", "workflows"))
    open(os.path.join(work, ".github", "workflows", "w.yml"), "w").write("on: push\n")
    open(os.path.join(work, "src.txt"), "w").write("a\n")
    git(work, "add", "-A")
    git(work, "commit", "-q", "-m", "base")
    git(work, "remote", "add", "origin", origin)
    git(work, "push", "-q", "origin", "HEAD:refs/heads/" + BRANCH)
    reviewed = git(work, "rev-parse", "HEAD")
    with open(os.path.join(work, touched), "a") as fh:
        fh.write("fixup\n")
    git(work, "commit", "-q", "-am", "review fixup")
    if refuse:
        hook = os.path.join(origin, "hooks", "pre-receive")
        open(hook, "w").write("#!/bin/sh\necho 'refusing allowed to be pushed' >&2\nexit 1\n")
        os.chmod(hook, os.stat(hook).st_mode | stat.S_IEXEC)
    return work, origin, reviewed


def run(steps, touched, can_push="false", refuse=False):
    """`steps`: (hold run text, advance if: text, advance run text)."""
    hold, advance_if, advance = steps
    tmp = tempfile.mkdtemp(prefix="wc-review-fixup-push-")
    try:
        work, origin, reviewed = build(tmp, touched, refuse)
        runner_temp = os.path.join(tmp, "runner-temp")
        os.makedirs(runner_temp)
        shutil.copytree(HERE, os.path.join(runner_temp, "wc-pristine", "scripts"),
                        ignore=shutil.ignore_patterns("__pycache__"))
        bindir = os.path.join(tmp, "bin")
        os.makedirs(bindir)
        gh = os.path.join(bindir, "gh")
        open(gh, "w").write(STUB_GH)
        os.chmod(gh, os.stat(gh).st_mode | stat.S_IEXEC)
        log = os.path.join(tmp, "gh.log")
        open(log, "w").close()
        env = {"PATH": bindir + os.pathsep + os.environ["PATH"],
               "GH_TOKEN": "x", "GITHUB_REPOSITORY": "o/r", "STUB_LOG": log,
               "ISSUE_NUMBER": "7", "PR_NUMBER": "70", "BRANCH": BRANCH,
               "CURRENT_ROUND": "1", "REVIEWED_SHA": reviewed,
               "CAN_PUSH_WORKFLOWS": can_push}
        rc, output, outputs, summary = run_step(BASH, hold, work, env, runner_temp)
        push_outcome = "skipped"
        if rc == 0 and outputs.get("held") == "false":
            push = subprocess.run(
                ["bash", HARDENED_PUSH, BRANCH, git(work, "rev-parse", "HEAD")], cwd=work,
                env=dict(os.environ, PUSH_SERVER_URL="file://" + tmp,
                         GITHUB_REPOSITORY="origin"),
                capture_output=True, text=True)
            output += push.stdout + push.stderr
            push_outcome = "success" if push.returncode == 0 else "failure"
            rc = rc or push.returncode
        # The advance step's own `if:`, as shipped: on the push's success, or
        # (a mutated condition) whenever the hold ran.
        runs = (push_outcome == "success" if advance_if.strip() == ADVANCE_IF
                else push_outcome != "skipped")
        if runs:
            rc2, out2, _, summary2 = run_step(BASH, advance, work, env, runner_temp)
            rc, output, summary = rc or rc2, output + out2, summary + summary2
        pushed = subprocess.run(["git", "rev-parse", BRANCH], cwd=origin, capture_output=True,
                                text=True).stdout.strip() == git(work, "rev-parse", "HEAD")
        return rc, output, summary, open(log).read(), pushed
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def suite(script, quiet=False):
    failed = []

    def ck(name, cond, detail=""):
        if not cond:
            failed.append(name)
        if not quiet:
            check(name, cond, detail)

    rc, out, summary, calls, pushed = run(script, ".github/workflows/w.yml")
    ck("a workflow-file follow-up is held, not pushed",
       rc == 0 and not pushed and "--add-label board:stalled" in calls
       and "issue comment 7" in calls and "Review round" not in calls
       and "review-fixup (workflow-scope hold)" in summary,
       "rc={0} pushed={1}\ncalls:\n{2}\nsummary:\n{3}\n{4}".format(rc, pushed, calls, summary, out))
    rc, out, summary, calls, pushed = run(script, ".github/workflows/w.yml", can_push="true")
    ck("with WING_COMMANDER_BOARD_CAN_PUSH_WORKFLOWS true it is pushed",
       rc == 0 and pushed and "board:stalled" not in calls and "Review round 2" in calls,
       "rc={0} pushed={1}\ncalls:\n{2}\n{3}".format(rc, pushed, calls, out))
    rc, out, summary, calls, pushed = run(script, "src.txt")
    ck("any other follow-up is pushed and the round advances",
       rc == 0 and pushed and "board:stalled" not in calls and "Review round 2" in calls,
       "rc={0} pushed={1}\ncalls:\n{2}\n{3}".format(rc, pushed, calls, out))
    rc, out, summary, calls, pushed = run(script, "src.txt", refuse=True)
    ck("a refused push fails the step and posts nothing",
       rc != 0 and not pushed and calls.strip() == ""
       and "::error::hardened push: pushing" in out,
       "rc={0} pushed={1}\ncalls:\n{2}\n{3}".format(rc, pushed, calls, out))
    return failed


# (name, which of the three texts it edits, old, new)
MUTATIONS = (
    ("workflow-scope hold removed", 0,
     'if [ "$held" = "held" ]; then', 'if false; then'),
    ("the round advances whether or not the push landed", 1,
     ADVANCE_IF, "steps.push-hold.outputs.held == 'false'"),
)


def main():
    global BASH
    use_utf8_stdout()
    BASH = resolve_bash()
    advance = find_step(BOARD_LOOP, ADVANCE_STEP)
    steps = (find_step(BOARD_LOOP, HOLD_STEP)["run"], str(advance.get("if", "")),
             advance["run"])
    for name, which, old, _new in MUTATIONS:
        if steps[which].count(old) != 1:
            sys.exit("::error file={0}::mutation {1!r} no longer matches the step text "
                     "exactly once. Update the mutation with the step.".format(BOARD_LOOP, name))
    suite(steps)
    for name, which, old, new in MUTATIONS:
        mutated = list(steps)
        mutated[which] = mutated[which].replace(old, new)
        check("mutation caught: " + name, bool(suite(tuple(mutated), quiet=True)),
              "the suite stayed green with this fix reverted")
    if failures:
        print("verify-board-review-fixup-push: {0} failure(s)".format(len(failures)))
        sys.exit(1)
    print("verify-board-review-fixup-push: ok")


if __name__ == "__main__":
    main()
