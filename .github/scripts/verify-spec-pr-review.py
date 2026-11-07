#!/usr/bin/env python3
"""Gate: every spec_pr_review.py subcommand is exercised by checked-in fixtures.

Each file in .github/scripts/spec-pr-review-fixtures/ is
`<subcommand>-<case>.json` holding {"input": ..., "expect": ...}. The runner
feeds `input` to the subcommand and requires every key in `expect` to match
the output (subset match). A subcommand with no fixture fails the gate.
"""
import glob
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURES = os.path.join(HERE, "spec-pr-review-fixtures")
MODULE = os.path.join(HERE, "spec_pr_review.py")
SUBCOMMANDS = ("select", "eligible", "verdict", "check-fixes",
               "plan-actions", "failed-cap")


def subset(expect, got):
    if isinstance(expect, dict):
        return (isinstance(got, dict)
                and all(k in got and subset(v, got[k])
                        for k, v in expect.items()))
    return expect == got


def main():
    failures, seen = [], set()
    paths = sorted(glob.glob(os.path.join(FIXTURES, "*.json")))
    for path in paths:
        name = os.path.basename(path)[:-5]
        cmd = next((c for c in sorted(SUBCOMMANDS, key=len, reverse=True)
                    if name.startswith(c + "-")), None)
        if cmd is None:
            cmd = "verdict" if name.startswith("replay-") else None
        if cmd is None:
            failures.append("%s: name does not start with a subcommand" % name)
            continue
        with open(path) as fh:
            case = json.load(fh)
        cmd = case.get("subcommand", cmd)
        seen.add(cmd)
        proc = subprocess.run(
            [sys.executable, MODULE, cmd], input=json.dumps(case["input"]),
            capture_output=True, text=True)
        if proc.returncode != 0:
            failures.append("%s: exit %d: %s" % (name, proc.returncode,
                                                 proc.stderr.strip()))
            continue
        got = json.loads(proc.stdout)
        if not subset(case["expect"], got):
            failures.append("%s: expected %s, got %s" % (
                name, json.dumps(case["expect"]), json.dumps(got)))
    for cmd in SUBCOMMANDS:
        if cmd not in seen:
            failures.append("subcommand %s has no fixture" % cmd)
    if failures:
        print("verify-spec-pr-review: FAIL")
        for f in failures:
            print("  " + f)
        return 1
    print("verify-spec-pr-review: ok (%d fixtures)" % len(paths))
    return 0


if __name__ == "__main__":
    sys.exit(main())
