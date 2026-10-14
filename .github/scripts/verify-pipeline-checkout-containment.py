#!/usr/bin/env python3
"""Gate: pipeline-checkout containment under a project working directory
(spec 114 FR-025).

A job that runs its agent from a project folder P resolves every relative
path against P, so a read-only grant naming `.wing-commander-pipeline/...`
or a repository tooling script (`.github/scripts/...`) would point inside P
instead of at the workspace-root checkout. Such grants must be absolute
(`${GITHUB_WORKSPACE}/...` or `${{ github.workspace }}/...`).

Checks:
  * fixtures/project-checkout-containment/cases.json: the grant rule accepts
    absolute grants and refuses relative ones in a project-wired job, and
    leaves an unwired (root) job alone;
  * the real workflows: in every job that uses wing-commander-project, every
    allowed-tools style grant string obeys the same rule;
  * the branch-tracking refusal (P/.wing-commander-pipeline/x) is owned by
    verify-pipeline-checkout-guard.py's nested-branch scenario; this gate
    asserts the guard script still pathspecs it at any depth.

Exit 0 when everything behaves; 1 otherwise.
"""
import json
import os
import re
import sys

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CASES = os.path.join(ROOT, ".github", "scripts", "fixtures", "project-checkout-containment", "cases.json")
GUARD = os.path.join(ROOT, ".github", "scripts", "pipeline-checkout-guard.sh")

# A grant token naming a path that must resolve at the workspace root.
ROOTED = re.compile(r"(?<![\w/.}])(\.wing-commander-pipeline/|\.github/scripts/)")
ABSOLUTE = re.compile(r"(\$\{GITHUB_WORKSPACE\}|\$\{\{\s*github\.workspace\s*\}\})/$")


def relative_rooted_paths(grant):
    """-> the rooted path prefixes in grant that are not workspace-absolute."""
    bad = []
    for m in ROOTED.finditer(grant):
        before = grant[: m.start()]
        # `.wing-commander-pipeline/.github/scripts/` is one path: judge it
        # by what precedes the outer prefix only.
        if before.endswith(".wing-commander-pipeline/"):
            continue
        if not ABSOLUTE.search(before):
            bad.append(m.group(1))
    return bad


def check_case(case):
    if not case["project_wired"]:
        return []
    return relative_rooted_paths(case["grant"])


def check_workflows(errors):
    wf_dir = os.path.join(ROOT, ".github", "workflows")
    for fn in sorted(os.listdir(wf_dir)):
        if not fn.endswith(".yml"):
            continue
        with open(os.path.join(wf_dir, fn), encoding="utf-8") as fh:
            doc = yaml.safe_load(fh)
        for job_name, job in ((doc or {}).get("jobs") or {}).items():
            steps = (job or {}).get("steps") or []
            if not any("wing-commander-project" in str(s.get("uses", "")) for s in steps if isinstance(s, dict)):
                continue
            for s in steps:
                if not isinstance(s, dict):
                    continue
                w = s.get("with") or {}
                for key in ("default-allowed-tools", "extra-allowed-tools", "allowed-tools-override"):
                    val = w.get(key)
                    if isinstance(val, str):
                        for prefix in relative_rooted_paths(val):
                            errors.append(f"{fn}:{job_name}: {key} grant names {prefix!r} relative to a project working directory")


def check_guard_script(errors):
    with open(GUARD, encoding="utf-8") as fh:
        text = fh.read()
    if ':(glob)**/$PIPE' not in text:
        errors.append("pipeline-checkout-guard.sh no longer refuses a nested tracked .wing-commander-pipeline/")


def main():
    with open(CASES, encoding="utf-8") as fh:
        data = json.load(fh)
    errors = []
    for name, case in data["grants"].items():
        bad = check_case(case)
        if case["expect"] == "pass" and bad:
            errors.append(f"grant {name}: expected pass, got relative {bad}")
        if case["expect"] == "fail" and not bad:
            errors.append(f"grant {name}: expected refusal, passed")
    check_workflows(errors)
    check_guard_script(errors)
    if errors:
        print("verify-pipeline-checkout-containment: FAIL")
        for e in errors:
            print("  " + e)
        return 1
    print("verify-pipeline-checkout-containment: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
