#!/usr/bin/env python3
"""Gate: subfolder containment (spec 114 FR-021, FR-022).

Runs the real shell of two composites against fixtures/project-containment/
cases.json:
  * wing-commander-tool-args -- the project-aware .claude/ and .git/ denies,
    which must hold even when no-write-paths is overridden by the caller;
  * wing-commander-containment -- fails on any change outside the project
    folder, passes for changes (moves, child-index edits) inside it.
It also checks that every workflow step running claude-code-action in a
workflow that composes tool-args consumes the composed allowed-tools output.

Exit 0 when every case behaves; 1 otherwise.
"""
import json
import os
import re
import subprocess
import sys
import tempfile

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ACTIONS = os.path.join(ROOT, ".github", "actions")
CASES = os.path.join(ROOT, ".github", "scripts", "fixtures", "project-containment", "cases.json")


def action_script(name):
    with open(os.path.join(ACTIONS, name, "action.yml"), encoding="utf-8") as fh:
        doc = yaml.safe_load(fh)
    return doc["runs"]["steps"][0]["run"]


def run_script(script, env, cwd, name):
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "output")
        summary = os.path.join(tmp, "summary")
        for p in (out, summary):
            open(p, "w", encoding="utf-8").close()
        full = dict(os.environ)
        full.update(env)
        full.update(
            GITHUB_OUTPUT=out,
            GITHUB_STEP_SUMMARY=summary,
            GITHUB_ACTION_PATH=os.path.join(ACTIONS, name),
        )
        r = subprocess.run(["bash", "-c", script], capture_output=True, text=True, cwd=cwd, env=full, check=False)
        with open(out, encoding="utf-8") as fh:
            return r, fh.read()


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def tool_args(case, script):
    env = {
        "STEP_LABEL": "fixture",
        "DEFAULT_ALLOWED": case.get("default_allowed", "Read,Edit,Write"),
        "DEFAULT_DISALLOWED": "",
        "EXTRA_ALLOWED": "",
        "EXTRA_DISALLOWED": "",
        "ALLOWED_OVERRIDE": "__unset__",
        "DISALLOWED_OVERRIDE": case.get("disallowed_override", "__unset__"),
        "NO_WRITE_PATHS": case.get("no_write_paths", ""),
        "PROJECT": case["project"],
    }
    r, out = run_script(script, env, ROOT, "wing-commander-tool-args")
    if r.returncode != 0:
        return None, None, r.stderr
    m = re.search(r"^disallowed-tools=(.*)$", out, re.M)
    a = re.search(r"^allowed-tools=(.*)$", out, re.M)
    return (m.group(1) if m else ""), (a.group(1) if a else ""), ""


def contain(case, script):
    with tempfile.TemporaryDirectory() as tmp:
        git(tmp, "init", "-q")
        git(tmp, "config", "user.email", "g@example.invalid")
        git(tmp, "config", "user.name", "gate")
        for rel in case["base_files"]:
            path = os.path.join(tmp, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("x\n")
        git(tmp, "add", "-A")
        git(tmp, "commit", "-q", "-m", "base")
        base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=tmp, capture_output=True, text=True, check=True).stdout.strip()
        for rel in case.get("modify", []):
            with open(os.path.join(tmp, rel), "a", encoding="utf-8") as fh:
                fh.write("y\n")
        for rel in case.get("create", []):
            path = os.path.join(tmp, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("z\n")
        for src, dst in case.get("move", []):
            os.makedirs(os.path.dirname(os.path.join(tmp, dst)), exist_ok=True)
            git(tmp, "mv", src, dst)
        if case.get("commit"):
            git(tmp, "add", "-A")
            git(tmp, "commit", "-q", "-m", "agent")
        r, _ = run_script(script, {"PROJECT": case["project"], "BASE_SHA": base}, tmp, "wing-commander-containment")
        return r


def check_wiring(errors):
    wf_dir = os.path.join(ROOT, ".github", "workflows")
    for fn in sorted(os.listdir(wf_dir)):
        if not fn.endswith(".yml"):
            continue
        with open(os.path.join(wf_dir, fn), encoding="utf-8") as fh:
            text = fh.read()
        if "wing-commander-tool-args" not in text or "claude-code-action" not in text:
            continue
        doc = yaml.safe_load(text)
        for job_name, job in (doc.get("jobs") or {}).items():
            steps = job.get("steps") or []
            composes = any("wing-commander-tool-args" in str(s.get("uses", "")) for s in steps)
            if not composes:
                continue
            for s in steps:
                if "claude-code-action" not in str(s.get("uses", "")):
                    continue
                if "outputs.allowed-tools" not in json.dumps(s):
                    errors.append(f"{fn}:{job_name}: claude-code-action step {s.get('name')!r} does not consume tool-args")


def main():
    with open(CASES, encoding="utf-8") as fh:
        data = json.load(fh)
    errors = []
    ta = action_script("wing-commander-tool-args")
    for name, case in data["tool_args"].items():
        got, allowed, err = tool_args(case, ta)
        if got is None:
            errors.append(f"tool_args {name}: composite failed: {err!r}")
            continue
        if "allowed" in case and allowed.split(",") != case["allowed"]:
            errors.append(f"tool_args {name}: allowed-tools {allowed!r}, want {case['allowed']!r}")
        for want in case.get("denied", []):
            for tool in ("Edit", "Write"):
                if f"{tool}({want})" not in got.split(","):
                    errors.append(f"tool_args {name}: {tool}({want}) missing from {got!r}")
        for bad in case.get("not_denied", []):
            if bad in got:
                errors.append(f"tool_args {name}: unexpected {bad!r} in {got!r}")
    cs = action_script("wing-commander-containment")
    for name, case in data["containment"].items():
        r = contain(case, cs)
        if case["expect"] == "pass" and r.returncode != 0:
            errors.append(f"containment {name}: expected pass, rc={r.returncode} {r.stderr!r}")
        if case["expect"] == "fail":
            if r.returncode == 0:
                errors.append(f"containment {name}: expected fail, passed")
            for p in case.get("names", []):
                if p not in r.stdout + r.stderr:
                    errors.append(f"containment {name}: output does not name {p!r}")
    check_wiring(errors)
    if errors:
        print("verify-subfolder-containment: FAIL")
        for e in errors:
            print("  " + e)
        return 1
    print("verify-subfolder-containment: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
