#!/usr/bin/env python3
"""Gate 98 -- board-loop's fix, review and readiness jobs run helpers from
a pristine snapshot, never from the working tree (#583).

WHY THIS EXISTS
---------------
The fixer and review-fixup agents hold Write/Edit on the checkout, and the
review and readiness jobs check out a branch those agents wrote. Steps
after that import .github/scripts helpers and then comment, push and label
with the App token. Importing them from the working tree runs code an
agent could have changed. Each of the three jobs therefore takes a copy of
.github/scripts and .github/schemas from $GITHUB_SHA (the commit whose
board-loop.yml is running) right after checkout, before any agent step,
into $RUNNER_TEMP/wc-pristine, and makes it read-only. Every later step
imports from that copy.

WHAT IT CHECKS
--------------
In each of fix, review and readiness:
  1. exactly one "Snapshot helper scripts" step, directly after the job's
     actions/checkout step, before any agent step and before any other
     step that references the snapshot;
  2. the three snapshot steps' run: blocks are identical;
  3. no other run: block references the working tree's .github/scripts,
     except the gate-suite steps' `python3 .github/scripts/run-local-gates.py`
     (the gate suite checks the agent's change, so it runs the agent's tree
     by design).
Then it runs the real snapshot step in a scratch git repository whose
working tree differs from the commit: the copy must hold the commit's
content, not the working tree's, and must be read-only.

--self-test applies one mutation per rule and asserts each is caught.

Usage: python3 .github/scripts/verify-board-loop-helper-provenance.py [--self-test]
Requires: bash, git, tar.
"""
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_shell_harness import resolve_bash, run_step, use_utf8_stdout  # noqa: E402

import yaml  # noqa: E402

WORKFLOW = os.path.join(".github", "workflows", "board-loop.yml")
JOBS = ("fix", "review", "readiness")
SNAPSHOT_NAME = "Snapshot helper scripts (before any agent runs)"
AGENT_USES = "anthropics/claude-code-action@"
GATE_SUITE_IDS = ("gate-suite", "gate-suite-review-fixup")
GATE_SUITE_CALL = "python3 .github/scripts/run-local-gates.py"
PRISTINE = "wc-pristine"
WORKTREE_SCRIPTS_RE = re.compile(
    r"\.github/scripts|\.github['\"]\s*,\s*['\"]scripts")


def structural_problems(doc):
    problems = []
    snapshot_runs = {}
    jobs = doc.get("jobs") or {}
    for job_id in JOBS:
        steps = (jobs.get(job_id) or {}).get("steps") or []
        if not steps:
            problems.append("job {0!r} not found or has no steps".format(job_id))
            continue
        checkout = [i for i, s in enumerate(steps)
                    if str((s or {}).get("uses", "")).startswith("actions/checkout@")]
        snaps = [i for i, s in enumerate(steps) if (s or {}).get("name") == SNAPSHOT_NAME]
        if len(checkout) != 1:
            problems.append("{0}: expected one actions/checkout step, found {1}".format(
                job_id, len(checkout)))
            continue
        if len(snaps) != 1:
            problems.append("{0}: expected one {1!r} step, found {2}".format(
                job_id, SNAPSHOT_NAME, len(snaps)))
            continue
        snap = snaps[0]
        if snap != checkout[0] + 1:
            problems.append("{0}: the snapshot step is not directly after checkout".format(job_id))
        snapshot_runs[job_id] = str(steps[snap].get("run", ""))
        for i, step in enumerate(steps):
            step = step or {}
            label = "{0}: step {1!r}".format(job_id, step.get("name", i))
            if AGENT_USES in str(step.get("uses", "")) and i < snap:
                problems.append("{0} runs an agent before the snapshot".format(label))
            if i == snap or "run" not in step:
                continue
            run = str(step["run"])
            if PRISTINE in run and i < snap:
                problems.append("{0} reads the snapshot before it is taken".format(label))
            scan = run
            if step.get("id") in GATE_SUITE_IDS:
                scan = scan.replace(GATE_SUITE_CALL, "")
            if WORKTREE_SCRIPTS_RE.search(scan):
                problems.append("{0} references the working tree's .github/scripts "
                                "instead of $RUNNER_TEMP/{1}/scripts".format(label, PRISTINE))
    if len(set(snapshot_runs.values())) > 1:
        problems.append("the snapshot steps' run: blocks differ between {0}".format(
            ", ".join(sorted(snapshot_runs))))
    return problems, snapshot_runs


def _git(cwd, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                    "-c", "commit.gpgsign=false"] + list(args),
                   cwd=cwd, check=True, capture_output=True)


def behaviour_problems(bash, snapshot_run, tmproot):
    """Runs the snapshot step in a scratch repository whose working tree
    has been edited after the commit."""
    repo = tempfile.mkdtemp(dir=tmproot)
    runner_temp = tempfile.mkdtemp(dir=tmproot)
    for sub in ("scripts", "schemas"):
        os.makedirs(os.path.join(repo, ".github", sub))
    with open(os.path.join(repo, ".github", "scripts", "helper.py"), "w") as fh:
        fh.write("PRISTINE = True\n")
    with open(os.path.join(repo, ".github", "schemas", "s.json"), "w") as fh:
        fh.write("{}\n")
    _git(repo, "init", "-q")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "c")
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, check=True,
                         capture_output=True, text=True).stdout.strip()
    # The agent's edit: the working tree no longer matches the commit.
    with open(os.path.join(repo, ".github", "scripts", "helper.py"), "w") as fh:
        fh.write("PRISTINE = False\n")
    with open(os.path.join(repo, ".github", "scripts", "planted.py"), "w") as fh:
        fh.write("PLANTED = True\n")
    problems = []
    try:
        rc, out, _o, _s = run_step(bash, snapshot_run, repo, {"GITHUB_SHA": sha}, runner_temp)
        if rc != 0:
            return ["the snapshot step exited {0}: {1}".format(rc, out.strip()[-400:])]
        base = os.path.join(runner_temp, PRISTINE)
        helper = os.path.join(base, "scripts", "helper.py")
        if not os.path.isfile(helper):
            return ["the snapshot has no scripts/helper.py"]
        if open(helper).read() != "PRISTINE = True\n":
            problems.append("the snapshot holds the working tree's edited helper, not the commit's")
        if os.path.exists(os.path.join(base, "scripts", "planted.py")):
            problems.append("the snapshot holds a file only the working tree has")
        if not os.path.isfile(os.path.join(base, "schemas", "s.json")):
            problems.append("the snapshot has no schemas/ beside scripts/")
        if os.stat(helper).st_mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH):
            problems.append("the snapshot is writable")
    finally:
        for root, dirs, files in os.walk(runner_temp):
            for name in dirs + files:
                try:
                    os.chmod(os.path.join(root, name), 0o755)
                except OSError:
                    pass
    return problems


def check(doc, bash, tmproot):
    problems, runs = structural_problems(doc)
    if runs:
        problems += behaviour_problems(bash, next(iter(runs.values())), tmproot)
    return problems


# --- self-test mutations: each must be caught ------------------------------

ONE_LINER = "sys.path.insert(0, os.path.join(os.environ['RUNNER_TEMP'], 'wc-pristine', 'scripts'))"
HEREDOC = 'sys.path.insert(0, os.path.join(os.environ["RUNNER_TEMP"], "wc-pristine", "scripts"))'
SPEC_CALL = 'python3 "$RUNNER_TEMP/wc-pristine/scripts/board_spec_request_body.py"'


def _replace_once(text, old, new):
    if old not in text:
        sys.exit("::error::Gate 98 self-test: {0!r} not found in {1}; update the "
                 "self-test alongside the workflow.".format(old[:60], WORKFLOW))
    return text.replace(old, new, 1)


def mut_one_liner_worktree(text):
    return _replace_once(text, ONE_LINER, "sys.path.insert(0, '.github/scripts')")


def mut_heredoc_worktree(text):
    return _replace_once(text, HEREDOC, 'sys.path.insert(0, ".github/scripts")')


def mut_spec_builder_worktree(text):
    return _replace_once(text, SPEC_CALL, "python3 .github/scripts/board_spec_request_body.py")


def _job_steps(doc, job_id):
    return doc["jobs"][job_id]["steps"]


def _snapshot_index(steps):
    return next(i for i, s in enumerate(steps) if (s or {}).get("name") == SNAPSHOT_NAME)


def mut_snapshot_dropped(doc):
    steps = _job_steps(doc, "readiness")
    del steps[_snapshot_index(steps)]
    return doc


def mut_snapshot_after_agent(doc):
    steps = _job_steps(doc, "review")
    snap = steps.pop(_snapshot_index(steps))
    agent = next(i for i, s in enumerate(steps) if AGENT_USES in str((s or {}).get("uses", "")))
    steps.insert(agent + 1, snap)
    return doc


def mut_snapshot_from_worktree(text):
    return re.sub(r"git archive [^\n]*\| tar [^\n]*\n",
                  'cp -R .github/scripts .github/schemas "$dest"/\n', text)


def mut_snapshot_writable(text):
    if 'chmod -R a-w "$dest"' not in text:
        sys.exit("::error::Gate 98 self-test: no chmod in the snapshot step; update the self-test.")
    return text.replace('chmod -R a-w "$dest"', 'true')


# (label, mutation, True when it edits the parsed document rather than text)
MUTATIONS = [
    ("a post-agent one-liner imports from the working tree", mut_one_liner_worktree, False),
    ("a post-agent heredoc imports from the working tree", mut_heredoc_worktree, False),
    ("the spec-request builder runs from the working tree", mut_spec_builder_worktree, False),
    ("readiness's snapshot step is removed", mut_snapshot_dropped, True),
    ("the review job's snapshot is taken after the reviewer agent", mut_snapshot_after_agent, True),
    ("the snapshot copies the working tree instead of $GITHUB_SHA", mut_snapshot_from_worktree, False),
    ("the snapshot is left writable", mut_snapshot_writable, False),
]


def main():
    use_utf8_stdout()
    self_test = "--self-test" in sys.argv[1:]
    if not os.path.isfile(WORKFLOW):
        sys.exit("::error::run this from the repository root; {0} not found.".format(WORKFLOW))
    bash = resolve_bash()
    text = open(WORKFLOW, encoding="utf-8").read()
    tmproot = tempfile.mkdtemp()
    failures = []
    try:
        base = check(yaml.safe_load(text), bash, tmproot)
        if self_test:
            if base:
                failures += ["the shipped workflow already fails: {0}".format(p) for p in base]
            for label, mutate, on_doc in MUTATIONS:
                doc = mutate(yaml.safe_load(text)) if on_doc else yaml.safe_load(mutate(text))
                caught = check(doc, bash, tmproot)
                if caught:
                    print("note: mutation caught ({0}): {1}".format(label, caught[0]))
                else:
                    failures.append("mutation {0!r} was NOT caught".format(label))
        else:
            failures = base
    finally:
        for root, dirs, files in os.walk(tmproot):
            for name in dirs:
                try:
                    os.chmod(os.path.join(root, name), 0o755)
                except OSError:
                    pass
        shutil.rmtree(tmproot, ignore_errors=True)
    for f in failures:
        print("::error file={0}::Gate 98: {1}".format(WORKFLOW, f))
    if failures:
        return 1
    if self_test:
        print("Gate 98 self-test: {0} mutation(s), each caught.".format(len(MUTATIONS)))
    else:
        print("Gate 98: fix, review and readiness import helpers only from the "
              "pristine $GITHUB_SHA snapshot, taken before any agent runs.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
