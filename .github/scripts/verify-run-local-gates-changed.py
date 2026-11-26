#!/usr/bin/env python3
"""Gate 176 - `run-local-gates.py --changed` runs the gates a change reaches.

The implement agent runs the gate suite before it pushes, and the whole
suite costs most of an hour. `--changed [BASE]` (#1180) runs only the gates
whose inputs differ from BASE, and falls back to every gate when it cannot
tell. This gate drives the shipped runner end to end against a small
synthetic repository, one git working tree per case, and checks which gates
ran:

  * no change runs no gate and says so;
  * a gate script change picks that gate alone;
  * a workflow change picks every gate that reads that workflow, through
    an os.path.join or an imported helper, and not a gate whose docstring
    only names it;
  * a helper module change picks the gates that import it;
  * a harness data file picks that harness;
  * an unmapped path (untracked, or read only by a helper function no gate
    calls) runs every gate;
  * a change to lint-workflows.yml, which the registry reads the gate list
    from, runs every gate;
  * an explicit BASE is honoured, and a name filter still narrows.

The repository's tree and the cases are fixtures/run-local-gates-changed/
cases.json. With `--changed` removed from the runner the flag reads as a
filter that matches no gate, so every case fails.

Usage:
    python3 .github/scripts/verify-run-local-gates-changed.py --self-test
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
RUNNER = os.path.join(HERE, "run-local-gates.py")
CASES = os.path.join(HERE, "fixtures", "run-local-gates-changed", "cases.json")
ROW = re.compile(r"^(\S.*?)\s+(PASS|FAIL)\s+[\d.]+s$")
GIT_ENV = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
GIT_ENV.update(GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.invalid")


def git(root, *args):
    subprocess.run(["git", "-C", root, *args], env=GIT_ENV, check=True,
                   capture_output=True)


def write(root, rel, text):
    path = os.path.join(root, *rel.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def touch(root, rel):
    with open(os.path.join(root, *rel.split("/")), "a", encoding="utf-8",
              newline="\n") as fh:
        fh.write("# changed\n")


def build(tree):
    """A git working tree holding `tree`, one commit, with origin/main at
    that commit so the runner's default base resolves to it."""
    root = tempfile.mkdtemp(prefix="wc-changed-")
    for rel, text in tree.items():
        write(root, rel, text)
    git(root, "init", "-q")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "fixture")
    git(root, "update-ref", "refs/remotes/origin/main", "HEAD")
    return root


def run_case(tree, case):
    root = build(tree)
    try:
        for rel in case.get("edit", []):
            touch(root, rel)
        for rel in case.get("add", []):
            write(root, rel, "new\n")
        for commit in case.get("commit", []):
            for rel in commit:
                touch(root, rel)
            git(root, "commit", "-q", "-am", "change")
        proc = subprocess.run(
            [sys.executable, RUNNER, "--jobs", "1", *case["args"]],
            cwd=root, capture_output=True, text=True, encoding="utf-8",
            errors="replace", env=dict(os.environ, PYTHONUTF8="1"))
    finally:
        shutil.rmtree(root, ignore_errors=True)
    out = proc.stdout + proc.stderr
    ran = sorted(m.group(1) for m in map(ROW.match, out.splitlines()) if m)
    problems = []
    if proc.returncode != 0:
        problems.append(f"exit {proc.returncode}")
    if ran != sorted(case["expect"]):
        problems.append(f"ran {ran}, expected {sorted(case['expect'])}")
    if case["say"] not in out:
        problems.append(f"output lacks {case['say']!r}")
    return problems, out


def self_test():
    with open(CASES, encoding="utf-8") as fh:
        data = json.load(fh)
    failed = 0
    for case in data["cases"]:
        problems, out = run_case(data["tree"], case)
        if problems:
            failed += 1
            print(f"FAIL  {case['name']}: {'; '.join(problems)}")
            print("      " + "\n      ".join(out.strip().splitlines()))
        else:
            print(f"ok    {case['name']}")
    if failed:
        print(f"Gate 176 self-test: {failed} of {len(data['cases'])} case(s) failed.")
        return 1
    print(f"Gate 176 self-test: {len(data['cases'])} case(s) pick the gates "
          f"they state.")
    return 0


if __name__ == "__main__":
    if sys.argv[1:] != ["--self-test"]:
        sys.exit("usage: verify-run-local-gates-changed.py --self-test")
    sys.exit(self_test())
