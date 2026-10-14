#!/usr/bin/env python3
"""Gate: intake routing-prefix validation and slug budget (spec 114 FR-001, FR-014, FR-023).

Drives `_shared/project-name.sh validate-prefix` and `slug-budget` over
fixtures/project-intake-routing/cases.json. Every accepted prefix must exit 0,
every rejected prefix must exit non-zero, and each budget case must print its
integer.

Exit 0 when every case behaves; 1 otherwise.
"""
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT = os.path.join(ROOT, ".github", "actions", "_shared", "project-name.sh")
CASES = os.path.join(ROOT, ".github", "scripts", "fixtures", "project-intake-routing", "cases.json")


def run(env_extra, *args):
    env = {**os.environ, **env_extra}
    return subprocess.run(["bash", SCRIPT, *args], capture_output=True, text=True, env=env, check=False)


def main():
    with open(CASES, encoding="utf-8") as fh:
        data = json.load(fh)
    env = data["env"]
    errors = []
    for pfx in data["prefix_accept"]:
        r = run(env, "validate-prefix", pfx)
        if r.returncode != 0:
            errors.append(f"accept prefix {pfx!r} refused: {r.stderr!r}")
    for pfx in data["prefix_reject"]:
        if run(env, "validate-prefix", pfx).returncode == 0:
            errors.append(f"reject prefix {pfx!r} was accepted")
    for case in data["budget"]:
        r = run(env, "slug-budget", case["project"])
        if r.returncode != 0 or r.stdout.strip() != str(case["budget"]):
            errors.append(f"slug-budget {case['project']!r}: rc={r.returncode} out={r.stdout!r}")
    if errors:
        print("verify-intake-routing: FAIL")
        for e in errors:
            print("  " + e)
        return 1
    print(f"verify-intake-routing: OK ({len(data['prefix_accept'])} accept, {len(data['prefix_reject'])} reject, {len(data['budget'])} budget)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
