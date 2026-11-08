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
    if "iteration=recorded+1" in wf:
        failures.append("migrate workflow: literal recorded+1 iteration")
    if failures:
        for f in failures:
            print(f"FAIL: {f}")
        return 1
    print("migrate stranded review lifecycles: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
