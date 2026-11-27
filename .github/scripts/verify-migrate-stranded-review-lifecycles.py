#!/usr/bin/env python3
"""Gate -- stranded-review migration decisions (specs/123 FR-018).

Drives `migration/` fixtures (`<name>.tasks.md` plus `<name>.expected` of
`key=value` lines: issue-state, stage, marker, decision) through
count-tasks-checkboxes.sh (the one classification home) and the migration
script's pure `decide` mode. Also checks the script never counts tasks itself.
"""
import importlib.util
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
SCRIPT = os.path.join(ROOT, ".github", "actions", "_shared", "migrate-stranded-review-lifecycles.sh")
spec = importlib.util.spec_from_file_location(
    "vbc", os.path.join(HERE, "verify-buildable-classification.py"))
vbc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vbc)


GH_STUB = """#!/bin/sh
echo "gh $*" >> "$GH_CALLS"
exit 0
"""


def crafted_iteration_failures():
    """#889 (found by the code review of #1279): the Hand off step runs the
    shipped `run:` text against a spec-meta.json whose .iteration is a
    crafted string. Shell arithmetic would evaluate `ISSUE[$(cmd)0]` as
    code (ISSUE is set, and reads as a number); the step must refuse it
    before any write: non-zero exit, the command never run, nothing pushed
    and no gh call."""
    import json
    import shutil
    import tempfile
    sys.path.insert(0, HERE)
    from wc_shell_harness import find_step, resolve_bash, run_step
    wf_path = os.path.join(".github", "workflows", "migrate-stranded-review-lifecycles.yml")
    script = find_step(wf_path, "Hand off").get("run") or ""
    failures = []
    root = tempfile.mkdtemp(prefix="wc-migrate-crafted-")
    try:
        remote = os.path.join(root, "remote.git")
        repo = os.path.join(root, "repo")
        pwned = os.path.join(root, "pwned")
        spec_dir = "specs/999-migrate-harness"
        branch = "spec/999-migrate-harness"
        meta = json.dumps({"spec_dir": spec_dir, "stage": "review",
                           "iteration": f"ISSUE[$(touch {pwned})0]"})

        def git(*args, cwd=repo):
            return subprocess.run(["git", *args], cwd=cwd, capture_output=True,
                                  text=True, check=True).stdout.strip()

        subprocess.run(["git", "init", "-q", "--bare", "-b", branch, remote], check=True)
        subprocess.run(["git", "clone", "-q", remote, repo], check=True,
                       capture_output=True)
        git("config", "user.email", "harness@example.invalid")
        git("config", "user.name", "harness")
        os.makedirs(os.path.join(repo, spec_dir))
        with open(os.path.join(repo, spec_dir, "spec-meta.json"), "w") as fh:
            fh.write(meta + "\n")
        git("checkout", "-q", "-b", branch)
        git("add", "-A")
        git("commit", "-q", "-m", "seed")
        git("push", "-q", "origin", branch)
        tip = git("rev-parse", "HEAD")
        bindir = os.path.join(root, "bin")
        os.makedirs(bindir)
        with open(os.path.join(bindir, "gh"), "w") as fh:
            fh.write(GH_STUB)
        os.chmod(os.path.join(bindir, "gh"), 0o755)
        calls = os.path.join(root, "gh_calls")
        open(calls, "w").close()
        runner_temp = os.path.join(root, "runner_temp")
        os.makedirs(runner_temp)
        env = {"GH_TOKEN": "x", "ISSUE": "250", "BRANCH": branch,
               "SPEC_DIR": spec_dir, "COUNT": "1", "ITEMS": "- [ ] T001",
               "MAINT": "", "VERDICT": "decision=migrate",
               "DECIDED_TIP": tip, "GITHUB_REPOSITORY": "example/repo",
               "GH_CALLS": calls,
               "PATH": bindir + os.pathsep + os.environ.get("PATH", "")}
        rc, out, _outputs, _summary = run_step(resolve_bash(), script, repo,
                                               env, runner_temp)
        where = "migrate workflow: crafted spec-meta.json iteration"
        if rc == 0:
            failures.append(f"{where}: the Hand off step exited 0: {out.strip()}")
        if os.path.exists(pwned):
            failures.append(f"{where}: shell arithmetic evaluated the "
                            f"iteration as code (its command ran)")
        if git("rev-parse", branch, cwd=remote) != tip:
            failures.append(f"{where}: the hand-off pushed although the "
                            f"iteration was refused")
        if open(calls).read().strip():
            failures.append(f"{where}: gh was called although the iteration "
                            f"was refused: {open(calls).read().strip()!r}")
    finally:
        shutil.rmtree(root, ignore_errors=True)
    return failures


def input_guard_failures():
    """#889 (found by the code review of #1119): the branch input must be a
    spec/* branch, and a spec-meta.json that fails the self-identity check
    must decide nothing. Runs the shipped `run:` text of Derive slug and
    Decide; Decide must refuse before it fetches or calls gh."""
    import shutil
    import tempfile
    sys.path.insert(0, HERE)
    from wc_shell_harness import find_step, resolve_bash, run_step
    wf_path = os.path.join(".github", "workflows", "migrate-stranded-review-lifecycles.yml")
    bash = resolve_bash()
    failures = []
    root = tempfile.mkdtemp(prefix="wc-migrate-guard-")
    try:
        slug_script = find_step(wf_path, "Derive slug").get("run") or ""
        cases = (("spec/123-implement-task-completion", True),
                 ("spec/P/123-x", True),
                 ("main", False), ("fix/889-x", False), ("spec/", False),
                 ("spec/../main", False), ("spec/-x", False),
                 ("refs/heads/spec/1-x", False), ("spec/1-x\nmain", False))
        for i, (branch, ok) in enumerate(cases):
            rt = os.path.join(root, f"rt-slug-{i}")
            os.makedirs(rt)
            rc, out, outputs, _ = run_step(bash, slug_script, root,
                                           {"BRANCH": branch}, rt)
            if ok and (rc != 0 or outputs.get("slug") != branch[len("spec/"):]):
                failures.append(f"migrate workflow: Derive slug refused spec branch {branch!r}: {out.strip()}")
            if not ok and (rc == 0 or outputs.get("slug")):
                failures.append(f"migrate workflow: Derive slug accepted non-spec branch {branch!r}")
        decide = find_step(wf_path, "Decide")
        if "steps.meta.outputs.identity-ok" not in str((decide.get("env") or {}).get("META_IDENTITY_OK", "")):
            failures.append("migrate workflow: Decide does not read the spec-meta identity-ok output")
        bindir = os.path.join(root, "bin")
        os.makedirs(bindir)
        calls = os.path.join(root, "calls")
        for tool in ("gh", "git"):
            with open(os.path.join(bindir, tool), "w") as fh:
                fh.write(f'#!/bin/sh\necho "{tool} $*" >> "$GH_CALLS"\nexit 0\n')
            os.chmod(os.path.join(bindir, tool), 0o755)
        for i, ident in enumerate(("false", "")):
            open(calls, "w").close()
            rt = os.path.join(root, f"rt-decide-{i}")
            os.makedirs(rt)
            env = {"GH_TOKEN": "x", "STAGE": "review", "META_IDENTITY_OK": ident,
                   "ISSUE": "250", "BRANCH": "spec/999-x", "SPEC_DIR": "specs/999-x",
                   "GITHUB_REPOSITORY": "example/repo", "GH_CALLS": calls,
                   "PATH": bindir + os.pathsep + os.environ.get("PATH", "")}
            rc, out, outputs, _ = run_step(bash, decide.get("run") or "", root, env, rt)
            where = f"migrate workflow: Decide with identity-ok={ident!r}"
            if rc == 0:
                failures.append(f"{where} exited 0")
            if outputs.get("verdict"):
                failures.append(f"{where} wrote a verdict: {outputs.get('verdict')!r}")
            if open(calls).read().strip():
                failures.append(f"{where} ran git/gh before refusing: {open(calls).read().strip()!r}")
    finally:
        shutil.rmtree(root, ignore_errors=True)
    return failures


def main():
    failures = []
    d = os.path.join(vbc.FIXTURES, "migration")
    names = sorted(f[: -len(".tasks.md")] for f in os.listdir(d) if f.endswith(".tasks.md"))
    if len(names) < 4:
        failures.append("expected at least 4 migration fixtures")
    for name in names:
        proc = vbc.run_counter(open(os.path.join(d, name + ".tasks.md")).read())
        if proc.returncode != 0:
            failures.append(f"{name}: counter exited {proc.returncode}")
            continue
        count = vbc.parse_outputs(proc.stdout).get("buildable-unchecked-count", "")
        exp = dict(l.split("=", 1) for l in open(os.path.join(d, name + ".expected")).read().splitlines() if "=" in l)
        out = subprocess.run(
            ["bash", SCRIPT, "decide", exp["issue-state"], exp["stage"], exp["marker"], count],
            capture_output=True, text=True)
        got = out.stdout.strip()
        # The script prints `decision=<verdict>`; the fixture key carries the
        # bare verdict, so the prefix is asserted exactly once here.
        if got != "decision=" + exp["decision"]:
            failures.append(f"migration/{name}: expected {exp['decision']!r}, got {got!r}")
    text = open(SCRIPT).read()
    if "grep -c" in text:
        failures.append("migration script holds its own task counter")
    wf = open(os.path.join(ROOT, ".github", "workflows", "migrate-stranded-review-lifecycles.yml")).read()
    for needle, why in (
        ('git commit -m "implement: hand off stranded review lifecycle (stage stalled)" || exit 1', "commit must abort the hand-off"),
        ('git push origin "$BRANCH" || exit 1', "push must abort the hand-off"),
        ('--remove-label "stage:review"', "hand-off must drop stage:review"),
        ("iteration=$next_iter", "iteration must be computed"),
        ("decision=comment-only", "partial run must be recoverable"),
    ):
        if needle not in wf:
            failures.append(f"migrate workflow: {why} (missing {needle!r})")
    # #889: the marker test must not pipe gh into `grep -q` -- under
    # pipefail, gh SIGPIPE'd by grep's early exit on a long comment history
    # reads as "no marker" and the comment is posted again.
    import re
    code = "\n".join(l for l in wf.splitlines() if not l.lstrip().startswith("#"))
    if re.search(r"\bgh\b[^\n]*\|\s*grep\s+-q", code):
        failures.append("migrate workflow: the marker check pipes gh into grep -q (capture the bodies first)")
    if "--jq '.comments[].body')\" || exit 1" not in wf:
        failures.append("migrate workflow: a failed comments read must stop the decision, not read as no marker")
    if "iteration=recorded+1" in wf:
        failures.append("migrate workflow: literal recorded+1 iteration")
    failures.extend(crafted_iteration_failures())
    failures.extend(input_guard_failures())
    if failures:
        for f in failures:
            print(f"FAIL: {f}")
        return 1
    print("migrate stranded review lifecycles: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
