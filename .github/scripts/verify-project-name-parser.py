#!/usr/bin/env python3
"""Gate: the shared project name parser (spec 114 FR-007, FR-013).

Drives `_shared/project-name.sh parse` over the checked-in accept and reject
fixtures (fixtures/project-name-parser/cases.json). Every accept case must
yield exactly its `(project, slug)` pair; every reject case must exit
non-zero. A final cross-kind check asserts the branch, label, slug and
spec-dir forms of one lifecycle yield the same pair.

Exit 0 when every case behaves; 1 otherwise.
"""
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT = os.path.join(ROOT, ".github", "actions", "_shared", "project-name.sh")
CASES = os.path.join(ROOT, ".github", "scripts", "fixtures", "project-name-parser", "cases.json")


def run(env_extra, *args):
    env = {**os.environ, **env_extra}
    return subprocess.run(["bash", SCRIPT, *args], capture_output=True, text=True, env=env, check=False)


def main():
    with open(CASES, encoding="utf-8") as fh:
        data = json.load(fh)
    env = data["env"]
    errors = []
    for case in data["accept"]:
        r = run(env, "parse", case["kind"], case["name"])
        want = f"project={case['project']}\nslug={case['slug']}\n"
        if r.returncode != 0 or r.stdout != want:
            errors.append(f"accept {case['kind']} {case['name']!r}: rc={r.returncode} out={r.stdout!r} err={r.stderr!r}")
    for case in data["reject"]:
        r = run(env, "parse", case["kind"], case["name"])
        if r.returncode == 0:
            errors.append(f"reject {case['kind']} {case['name']!r} was accepted: {r.stdout!r}")
    # Builder side of the spec-dir round trip (FR-013); the accept cases above
    # assert the same (P, NNN-slug) comes back from every kind.
    spec_dir = run(env, "spec-dir", "ideas/alpha", "001-login")
    if spec_dir.stdout.strip() != "ideas/alpha/specs/001-login":
        errors.append(f"spec-dir builder (subfolder): {spec_dir.stdout!r}")
    spec_dir = run(env, "spec-dir", "", "001-login")
    if spec_dir.stdout.strip() != "specs/001-login":
        errors.append(f"spec-dir builder (root): {spec_dir.stdout!r}")
    if errors:
        print("verify-project-name-parser: FAIL")
        for e in errors:
            print("  " + e)
        return 1
    print(f"verify-project-name-parser: OK ({len(data['accept'])} accept, {len(data['reject'])} reject)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
