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
  * wing-commander-tool-args, the one home for grants (research D10): for a
    project it composes, beside each relative `.wing-commander-pipeline/` or
    `.github/scripts/` Bash grant, its twin absolute under GITHUB_WORKSPACE,
    and for the root it composes nothing new (fixtures `tool_args`);
  * the real workflows: in every job that uses wing-commander-project, every
    tool-args call passes the project and its default grants compose those
    twins. The agent itself still starts at the workspace root (research D9:
    the Spec Kit project-root override, not a working directory), so the
    relative grant stays valid beside its twin;
  * the branch-tracking refusal (P/.wing-commander-pipeline/x) is owned by
    verify-pipeline-checkout-guard.py's nested-branch scenario; this gate
    asserts the guard script still pathspecs it at any depth.

Exit 0 when everything behaves; 1 otherwise.
"""
import json
import os
import re
import subprocess
import sys
import tempfile

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TOOL_ARGS = os.path.join(ROOT, ".github", "actions", "wing-commander-tool-args", "action.yml")
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


WS = "/gate-ws"


def compose(default_allowed, project):
    """-> the allowed-tools wing-commander-tool-args composes (D10's one home)."""
    with open(TOOL_ARGS, encoding="utf-8") as fh:
        script = yaml.safe_load(fh)["runs"]["steps"][0]["run"]
    with tempfile.TemporaryDirectory() as tmp:
        out, summary = os.path.join(tmp, "out"), os.path.join(tmp, "summary")
        for p in (out, summary):
            open(p, "w", encoding="utf-8").close()
        env = {**os.environ, "STEP_LABEL": "gate-161", "DEFAULT_ALLOWED": default_allowed,
               "DEFAULT_DISALLOWED": "", "EXTRA_ALLOWED": "", "EXTRA_DISALLOWED": "",
               "ALLOWED_OVERRIDE": "__unset__", "DISALLOWED_OVERRIDE": "__unset__",
               "NO_WRITE_PATHS": "", "PROJECT": project, "GITHUB_WORKSPACE": WS,
               "GITHUB_OUTPUT": out, "GITHUB_STEP_SUMMARY": summary,
               "GITHUB_ACTION_PATH": os.path.dirname(TOOL_ARGS)}
        r = subprocess.run(["bash", "-c", script], capture_output=True, text=True, env=env, check=False)
        with open(out, encoding="utf-8") as fh:
            m = re.search(r"^allowed-tools=(.*)$", fh.read(), re.M)
    if r.returncode != 0 or not m:
        raise RuntimeError(f"tool-args failed: {r.stderr!r}")
    return m.group(1).split(",")


def missing_twins(default_allowed, project):
    """Rooted relative Bash grants whose workspace-absolute twin is not composed."""
    composed = compose(default_allowed, project)
    missing = []
    for grant in composed:
        if not grant.startswith("Bash(") or not relative_rooted_paths(grant):
            continue
        twin = re.sub(r"(?<![\w/.}])(\.wing-commander-pipeline/|\.github/scripts/)", WS + r"/\1", grant)
        if twin not in composed:
            missing.append(grant)
    return missing, composed


def check_tool_args(data, errors):
    """The composite adds the twins for a project and nothing for the root."""
    for name, case in data.get("tool_args", {}).items():
        missing, composed = missing_twins(case["default_allowed"], case["project"])
        if case["project"] and missing:
            errors.append(f"tool_args {name}: no workspace-absolute twin for {missing}")
        if not case["project"] and composed != case["default_allowed"].split(","):
            errors.append(f"tool_args {name}: the root composition changed: {composed!r}")


def check_workflows(errors):
    """Every project-wired job's tool-args call composes the absolute twins."""
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
                if not isinstance(s, dict) or "wing-commander-tool-args" not in str(s.get("uses", "")):
                    continue
                w = s.get("with") or {}
                if "project" not in w:
                    errors.append(f"{fn}:{job_name}: tool-args step {s.get('name')!r} in a project-wired job passes no project")
                    continue
                val = w.get("default-allowed-tools")
                if isinstance(val, str):
                    missing, _ = missing_twins(val, "ideas/alpha")
                    for grant in missing:
                        errors.append(f"{fn}:{job_name}: {grant!r} composes no workspace-absolute twin for a project")


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
    check_tool_args(data, errors)
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
