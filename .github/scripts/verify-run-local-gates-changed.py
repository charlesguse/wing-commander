#!/usr/bin/env python3
"""Gate 176 - `run-local-gates.py --changed` runs the gates a change reaches.

The implement agent runs the gate suite before it pushes, and the whole
suite costs most of an hour. `--changed [BASE]` (#1180) runs only the gates
whose inputs differ from BASE, and falls back to every gate when it cannot
tell. It picks a gate by the union of two readings: what the gate was seen
to read when its reads were recorded (`--record-reads`, kept in
.github/scripts/gate-reads.json; wc_gate_reads.py describes it), and what
its text names.

Live (no arguments): the read map is fresh. Every gate the registry
derives from lint-workflows.yml has an entry, no entry names a gate that
is gone, and no traced entry is stale (the code its gate ran no longer has
the recorded digest). A stale or missing entry would let `--changed` pick
from reads the gate no longer makes. Refresh the map with

    python .github/scripts/run-local-gates.py --record-reads --changed

(every gate a change since origin/main reaches, which covers each stale
entry), or `--record-reads` alone for the whole suite.

--self-test: drives the shipped runner end to end against a small
synthetic repository. It records that repository's reads once with
`--record-reads`, then builds one git working tree per case with the map
committed, and checks which gates ran:

  * no change runs no gate and says so;
  * a gate script change picks that gate alone;
  * a workflow change picks every gate that reads that workflow, through
    an os.path.join or an imported helper, and not a gate whose docstring
    only names it;
  * a helper module change picks the gates that import it;
  * a gate that globs or lists its own directory through a name bound to
    `__file__`'s directory (`..` included) is picked by a change there,
    and so is one that walks a directory a def derives from `__file__`
    (its parent), or copies its own directory;
  * a gate that runs the code in a directory it names (unittest
    discovery) is picked by a change to a module that code imports;
  * the same three shapes in forms no reading of the text resolves (a
    def's return value, `.parents[0]`, a concatenated directory name) are
    picked through the traced reads alone;
  * a shell gate, whose own reads are not traced, is picked by every
    change, and a gate whose entry is stale is picked;
  * a harness data file picks that harness;
  * an unmapped path (untracked, or read only by a helper function no gate
    calls), or a gate the map lacks, runs every gate;
  * a change to lint-workflows.yml, which the registry reads the gate list
    from, runs every gate;
  * an explicit BASE is honoured, and a name filter still narrows.

It also runs the live check against that repository: passing on the
fresh map, failing on a stale entry and on a missing one. The tree and
the cases are fixtures/run-local-gates-changed/cases.json. With
`--changed` removed from the runner the flag reads as a filter that
matches no gate, so every selection case fails.

Usage:
    python3 .github/scripts/verify-run-local-gates-changed.py
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
sys.path.insert(0, HERE)
import wc_gate_reads  # noqa: E402
from wc_gate_registry import (gate_label, pr_time_inline_steps,  # noqa: E402
                              pr_time_invocations)

RUNNER = os.path.join(HERE, "run-local-gates.py")
CASES = os.path.join(HERE, "fixtures", "run-local-gates-changed", "cases.json")
ROW = re.compile(r"^(\S.*?)\s+(PASS|FAIL)\s+[\d.]+s$")
GIT_ENV = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
GIT_ENV.update(GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.invalid")
REFRESH = "python .github/scripts/run-local-gates.py --record-reads --changed"


def map_problems(root="."):
    """Why the read map at `root` is not fresh: registry gates it lacks,
    entries for gates that are gone, stale traced entries."""
    keys = [gate_label(sc, ar) for sc, ar in pr_time_invocations(root)]
    keys += wc_gate_reads.inline_gate_names(
        [name for name, _ in pr_time_inline_steps(root)[0]])
    entries = wc_gate_reads.load(root)
    problems = [f"no entry for {k}" for k in keys if k not in entries]
    problems += [f"an entry for {k}, which is no longer a gate"
                 for k in sorted(set(entries) - set(keys))]
    problems += [f"{k} is stale: code it ran changed since it was recorded"
                 for k in wc_gate_reads.stale_keys(
                     root, entries, [k for k in keys if k in entries])]
    return problems


def live():
    problems = map_problems()
    if problems:
        for p in problems[:20]:
            print(f"FAIL  {wc_gate_reads.MAP_PATH}: {p}")
        if len(problems) > 20:
            print(f"      ... and {len(problems) - 20} more")
        print(f"Gate 176: the read map is not fresh ({len(problems)} "
              f"problem(s)). Refresh it: {REFRESH}")
        return 1
    print(f"Gate 176: {wc_gate_reads.MAP_PATH} has a fresh entry for every "
          f"gate.")
    return 0


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


def build(tree, stale=()):
    """A git working tree holding `tree`, then each `stale` file touched,
    in one commit, with origin/main at that commit so the runner's
    default base resolves to it."""
    root = tempfile.mkdtemp(prefix="wc-changed-")
    for rel, text in tree.items():
        write(root, rel, text)
    for rel in stale:
        touch(root, rel)
    git(root, "init", "-q")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "fixture")
    git(root, "update-ref", "refs/remotes/origin/main", "HEAD")
    return root


def run(root, *args):
    proc = subprocess.run(
        [sys.executable, *args], cwd=root, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
        env=dict(os.environ, PYTHONUTF8="1"))
    return proc.returncode, proc.stdout + proc.stderr


def record(tree):
    """The fixture repository's read map, recorded by the shipped runner."""
    root = build(tree)
    try:
        rc, out = run(root, RUNNER, "--record-reads", "--jobs", "1")
        if rc != 0:
            raise SystemExit(f"Gate 176 self-test: --record-reads exited "
                             f"{rc}:\n{out}")
        with open(os.path.join(root, wc_gate_reads.MAP_PATH),
                  encoding="utf-8") as fh:
            return fh.read()
    finally:
        shutil.rmtree(root, ignore_errors=True)


def run_case(tree, case):
    root = build(tree, case.get("stale", []))
    try:
        for rel in case.get("edit", []):
            touch(root, rel)
        for rel in case.get("add", []):
            write(root, rel, "new\n")
        for commit in case.get("commit", []):
            for rel in commit:
                touch(root, rel)
            git(root, "commit", "-q", "-am", "change")
        if "live" in case:
            rc, out = run(root, os.path.abspath(__file__))
        else:
            rc, out = run(root, RUNNER, "--jobs", "1", *case["args"])
    finally:
        shutil.rmtree(root, ignore_errors=True)
    problems = []
    if "live" in case:
        if rc != case["live"]:
            problems.append(f"live check exited {rc}, expected {case['live']}")
    else:
        ran = sorted(m.group(1) for m in map(ROW.match, out.splitlines()) if m)
        if rc != 0:
            problems.append(f"exit {rc}")
        if ran != sorted(case["expect"]):
            problems.append(f"ran {ran}, expected {sorted(case['expect'])}")
    if case["say"] not in out:
        problems.append(f"output lacks {case['say']!r}")
    return problems, out


def self_test():
    with open(CASES, encoding="utf-8") as fh:
        data = json.load(fh)
    recorded = record(data["tree"])
    failed = 0
    for case in data["cases"]:
        entries = json.loads(recorded)
        for key in case.get("drop", []):
            entries.pop(key)
        tree = dict(data["tree"])
        tree[wc_gate_reads.MAP_PATH] = json.dumps(entries, indent=1,
                                                  sort_keys=True) + "\n"
        problems, out = run_case(tree, case)
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
    if sys.argv[1:] == ["--self-test"]:
        sys.exit(self_test())
    if sys.argv[1:]:
        sys.exit("usage: verify-run-local-gates-changed.py [--self-test]")
    sys.exit(live())
