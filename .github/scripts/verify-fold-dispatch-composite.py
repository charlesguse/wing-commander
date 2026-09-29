#!/usr/bin/env python3
"""Gate 111 - wing-commander-fold-dispatch's own `run:` step re-reads the
spec branch's tip, dispatches implement-workflow only when it moved and a
target is configured, and reports which iteration a standalone-mode
caller should dispatch manually (specs/062-lifecycle-review-gate
T034/T035).

WHY THIS EXISTS
---------------
This composite is the single home CLAUDE.md's "Shared logic has exactly
one home" rule requires before pr-conversation.yml's `dispatch-once` job
(T036) and lifecycle-review-gate.yml's `disposition` job (T038) can both
bump-and-dispatch without pasting the tip-compare/iteration-bump/dispatch
sequence a second time. Running the SHIPPED step (via
wc_shell_harness.run_step against a real git clone/remote, not a copy of
it and not a mock of git) is the whole point: a copy could sit green for
weeks while checking a sequence that did not ship.

    python3 .github/scripts/verify-fold-dispatch-composite.py
    python3 .github/scripts/verify-fold-dispatch-composite.py --self-test
"""
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_shell_harness import (ensure_jq, find_step, resolve_bash, run_step,  # noqa: E402
                              use_utf8_stdout)

ACTION = ".github/actions/wing-commander-fold-dispatch/action.yml"
STEP_NAME = "Re-read the tip and dispatch if it moved"
SPEC_DIR = "specs/999-fold-dispatch-harness"
SPEC_BRANCH = "spec/999-fold-dispatch-harness"
ISSUE = "250"
IMPLEMENT_WORKFLOW = "wing-commander-5-implement.yml"
REPO = "charlesguse/wing-commander"
BASH = None

GH_STUB = r"""#!/bin/sh
echo "gh $*" >> "$GH_CALLS"
case " $* " in
  *" workflow "*"run "*)
    exit "${GH_WORKFLOW_RUN_EXIT:-0}"
    ;;
  *" run "*"list "*)
    printf '%s' "${GH_RUN_LIST_JSON:-[]}" | jq -r '.[0].url // empty'
    exit 0
    ;;
esac
exit 0
"""


def _sh(script, cwd):
    global BASH
    if BASH is None:
        BASH = resolve_bash()
    path = os.path.join(cwd, "_setup.sh")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(script)
    return subprocess.run([BASH, "-e", path.replace("\\", "/")], cwd=cwd,
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace")


def make_repo(root, iteration, fold_commits):
    """A real git repo (bare remote + clone) on SPEC_BRANCH, seeded with
    spec-meta.json, then one commit per (id, summary) in fold_commits, each
    message `fold(<id>): <summary>`. Returns (repo_path, base_sha, tip_sha).
    """
    work = tempfile.mkdtemp(dir=root)
    remote = os.path.join(work, "remote.git")
    repo = os.path.join(work, "repo")
    setup = f"""
git init --bare -q -b {SPEC_BRANCH} '{remote}'
git clone -q '{remote}' '{repo}'
cd '{repo}'
git config user.email harness@example.invalid
git config user.name harness
mkdir -p '{SPEC_DIR}'
printf '%s\\n' '{{"issue": {ISSUE}, "spec_dir": "{SPEC_DIR}", "stage": "implement", "iteration": {iteration}}}' > '{SPEC_DIR}/spec-meta.json'
git add -A
git commit -q -m seed
git push -q origin {SPEC_BRANCH}
git rev-parse HEAD
"""
    proc = _sh(setup, work)
    if proc.returncode != 0:
        sys.exit(f"::error::verify-fold-dispatch-composite: harness could "
                 f"not seed a git workspace: {proc.stdout}{proc.stderr}")
    base_sha = proc.stdout.strip().splitlines()[-1]

    tip_sha = base_sha
    for idx, (fold_id, summary) in enumerate(fold_commits):
        commit_script = f"""
cd '{repo}'
echo 'change {idx}' >> '{SPEC_DIR}/tasks.md'
git add -A
git commit -q -m 'fold({fold_id}): {summary}'
git push -q origin {SPEC_BRANCH}
git rev-parse HEAD
"""
        proc = _sh(commit_script, work)
        if proc.returncode != 0:
            sys.exit(f"::error::verify-fold-dispatch-composite: harness "
                     f"could not seed a fold commit: {proc.stdout}{proc.stderr}")
        tip_sha = proc.stdout.strip().splitlines()[-1]
    return repo, base_sha, tip_sha


def _stub_gh(root):
    bindir = os.path.join(root, "bin")
    os.makedirs(bindir, exist_ok=True)
    path = os.path.join(bindir, "gh")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(GH_STUB)
    os.chmod(path, 0o755)
    calls = os.path.join(root, "gh_calls")
    open(calls, "w").close()
    return bindir, calls


def gh_call_count(calls_path, *substrings):
    with open(calls_path, encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    return sum(1 for line in lines if all(s in line for s in substrings))


def run_dispatch(root, step_script, base_sha, repo, implement_workflow,
                 run_list_json='[{"url":"https://example.invalid/runs/1"}]'):
    runner_temp = os.path.join(root, "runner_temp_{}".format(os.getpid()))
    os.makedirs(runner_temp, exist_ok=True)
    bindir, calls = _stub_gh(root)
    path = bindir + os.pathsep + os.environ.get("PATH", "")
    env = {
        "DISPATCH_TOKEN": "x", "SPEC_DIR": SPEC_DIR, "ISSUE": ISSUE,
        "BASE_SHA": base_sha, "SPEC_BRANCH": SPEC_BRANCH,
        "IMPLEMENT_WORKFLOW": implement_workflow,
        "GITHUB_REPOSITORY": REPO, "GH_CALLS": calls,
        "GH_RUN_LIST_JSON": run_list_json, "PATH": path,
    }
    rc, out, outputs, _summary = run_step(BASH, step_script, repo, env,
                                          runner_temp)
    return rc, out, outputs, calls


def run():
    failures = []
    root = tempfile.mkdtemp(prefix="wc-fold-dispatch-")
    try:
        step = find_step(ACTION, STEP_NAME)
        script = step.get("run") or ""
        if not script:
            sys.exit(f"::error::verify-fold-dispatch-composite: step "
                     f"{STEP_NAME!r} in {ACTION} has no run: body.")

        # Case 1: tip unchanged -- nothing folded, nothing dispatched.
        repo1, base1, tip1 = make_repo(root, 3, [])
        rc, out, outputs, calls = run_dispatch(root, script, base1, repo1,
                                               IMPLEMENT_WORKFLOW)
        if rc != 0:
            failures.append(f"case 1 (tip unchanged): step exited {rc}: {out}")
        else:
            if outputs.get("folded") != "false":
                failures.append(f"case 1: expected folded=false, got "
                                f"{outputs.get('folded')!r}")
            if outputs.get("dispatched") != "false":
                failures.append(f"case 1: expected dispatched=false, got "
                                f"{outputs.get('dispatched')!r}")
            if gh_call_count(calls, "workflow run") != 0:
                failures.append("case 1: a gh workflow run call was made "
                                "despite the tip not moving.")
        if not failures:
            print("[ok] case 1: tip unchanged -> folded=false, dispatched=false")

        # Case 2: tip moved, implement-workflow configured -> dispatched.
        before = len(failures)
        repo2, base2, tip2 = make_repo(
            root, 3, [("leg-0", "first item"), ("leg-1", "second item")])
        rc, out, outputs, calls = run_dispatch(root, script, base2, repo2,
                                               IMPLEMENT_WORKFLOW)
        if rc != 0:
            failures.append(f"case 2 (tip moved, dispatch): step exited "
                            f"{rc}: {out}")
        else:
            if outputs.get("folded") != "true":
                failures.append(f"case 2: expected folded=true, got "
                                f"{outputs.get('folded')!r}")
            if outputs.get("dispatched") != "true":
                failures.append(f"case 2: expected dispatched=true, got "
                                f"{outputs.get('dispatched')!r}")
            if outputs.get("new-iteration") != "4":
                failures.append(f"case 2: expected new-iteration=4 "
                                f"(recorded 3 + 1), got "
                                f"{outputs.get('new-iteration')!r}")
            summary = outputs.get("folded-summary", "")
            for leg_id in ("leg-0", "leg-1"):
                if leg_id not in summary:
                    failures.append(f"case 2: folded-summary does not name "
                                    f"{leg_id!r}: {summary!r}")
            if gh_call_count(calls, "workflow run") != 1:
                failures.append(f"case 2: expected exactly 1 gh workflow "
                                f"run call, got "
                                f"{gh_call_count(calls, 'workflow run')}.")
            if outputs.get("run-url") != "https://example.invalid/runs/1":
                failures.append(f"case 2: expected run-url to be polled "
                                f"from gh run list, got "
                                f"{outputs.get('run-url')!r}")
        if len(failures) == before:
            print("[ok] case 2: tip moved + implement-workflow set -> "
                 "dispatched=true, new-iteration bumped, run-url polled")

        # Case 3: tip moved, implement-workflow empty (standalone mode).
        before = len(failures)
        repo3, base3, tip3 = make_repo(root, 7, [("leg-a", "solo item")])
        rc, out, outputs, calls = run_dispatch(root, script, base3, repo3, "")
        if rc != 0:
            failures.append(f"case 3 (standalone): step exited {rc}: {out}")
        else:
            if outputs.get("folded") != "true":
                failures.append(f"case 3: expected folded=true, got "
                                f"{outputs.get('folded')!r}")
            if outputs.get("dispatched") != "false":
                failures.append(f"case 3: expected dispatched=false in "
                                f"standalone mode, got "
                                f"{outputs.get('dispatched')!r}")
            if outputs.get("new-iteration") != "8":
                failures.append(f"case 3: expected new-iteration=8 "
                                f"(recorded 7 + 1) even in standalone mode, "
                                f"got {outputs.get('new-iteration')!r}")
            if gh_call_count(calls, "workflow run") != 0:
                failures.append("case 3: a gh workflow run call was made "
                                "in standalone mode.")
            if outputs.get("run-url", "") != "":
                failures.append(f"case 3: expected an empty run-url in "
                                f"standalone mode, got "
                                f"{outputs.get('run-url')!r}")
        if len(failures) == before:
            print("[ok] case 3: tip moved + implement-workflow empty -> "
                 "folded=true, dispatched=false, new-iteration still bumped")
    finally:
        import shutil
        shutil.rmtree(root, ignore_errors=True)

    for f in failures:
        print(f"::error::verify-fold-dispatch-composite: {f}")
    print(f"verify-fold-dispatch-composite: {len(failures)} failure(s).")
    return 1 if failures else 0


def _mutate_ignores_tip_move(script):
    needle = 'if [ -z "$tip" ] || [ "$tip" = "$BASE_SHA" ]; then'
    if script.count(needle) != 1:
        sys.exit("::error::verify-fold-dispatch-composite --self-test: "
                 "expected one tip-unchanged guard; update this harness.")
    return script.replace(needle, 'if true; then', 1)


def _mutate_always_dispatches(script):
    needle = 'if [ -z "$IMPLEMENT_WORKFLOW" ]; then'
    if script.count(needle) != 1:
        sys.exit("::error::verify-fold-dispatch-composite --self-test: "
                 "expected one standalone-mode guard; update this harness.")
    return script.replace(needle, 'if false; then', 1)


def self_test():
    use_utf8_stdout()
    failures = 0

    def check(name, cond, detail=""):
        nonlocal failures
        if cond:
            print(f"PASS {name}")
        else:
            failures += 1
            print(f"FAIL {name} {detail}")

    step = find_step(ACTION, STEP_NAME)
    script = step.get("run") or ""

    root = tempfile.mkdtemp(prefix="wc-fold-dispatch-selftest-")
    try:
        # A mutation that always takes the "tip unchanged" early-exit branch
        # must be caught: a tip that DID move (a fold commit landed) must
        # still be reported as folded=true.
        mutated = _mutate_ignores_tip_move(script)
        repo, base, _tip = make_repo(root, 1, [("leg-z", "z")])
        rc, _out, outputs, calls = run_dispatch(root, mutated, base, repo,
                                                IMPLEMENT_WORKFLOW)
        caught = rc != 0 or outputs.get("folded") != "true"
        check("a mutation that ignores 'tip moved' is caught", caught,
             f"outputs={outputs!r} rc={rc}")

        # A mutation that dispatches even in standalone mode must be caught.
        mutated2 = _mutate_always_dispatches(script)
        repo2, base2, _tip2 = make_repo(root, 1, [("leg-x", "x")])
        rc2, _out2, outputs2, calls2 = run_dispatch(root, mutated2, base2,
                                                    repo2, "")
        caught2 = (rc2 != 0 or outputs2.get("dispatched") == "true" or
                  gh_call_count(calls2, "workflow run") > 0)
        check("a mutation that dispatches in standalone mode is caught",
             caught2, f"outputs={outputs2!r} rc={rc2}")

        # Control: the unmutated step still behaves correctly.
        repo3, base3, _tip3 = make_repo(root, 1, [("leg-y", "y")])
        rc3, _out3, outputs3, calls3 = run_dispatch(root, script, base3,
                                                    repo3, IMPLEMENT_WORKFLOW)
        control_ok = (rc3 == 0 and outputs3.get("folded") == "true" and
                     outputs3.get("dispatched") == "true" and
                     gh_call_count(calls3, "workflow run") == 1)
        check("the unmutated step still dispatches correctly (control)",
             control_ok, f"outputs={outputs3!r} rc={rc3}")
    finally:
        import shutil
        shutil.rmtree(root, ignore_errors=True)

    print(f"{failures} failure(s).")
    return 1 if failures else 0


def main(argv):
    use_utf8_stdout()
    ensure_jq()
    global BASH
    BASH = resolve_bash()
    if argv == ["--self-test"]:
        return self_test()
    if argv:
        sys.exit(f"unknown arguments {argv!r}; takes --self-test or nothing.")
    return run()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
