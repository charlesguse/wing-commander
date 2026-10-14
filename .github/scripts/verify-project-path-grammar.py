#!/usr/bin/env python3
"""Gate: the project path grammar, folder rules, label budget and routing
prefix validation (spec 114 FR-002, FR-005, FR-014, FR-023).

Drives `_shared/project-name.sh` over fixtures/project-path-grammar/cases.json.
Folder cases build a real tree in a temp directory (including symlinks) and
run `check-folder` from inside it.

Exit 0 when every case behaves; 1 otherwise.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT = os.path.join(ROOT, ".github", "actions", "_shared", "project-name.sh")
CASES = os.path.join(ROOT, ".github", "scripts", "fixtures", "project-path-grammar", "cases.json")


def sh(args, cwd=None):
    return subprocess.run(["bash", SCRIPT, *args], capture_output=True, text=True, cwd=cwd, check=False)


def build(tree, case):
    for rel in case["files"]:
        path = os.path.join(tree, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("x\n")
    link = case.get("symlink")
    if link:
        elsewhere = os.path.join(tree, "..", "elsewhere", link.replace("/", "_"))
        os.makedirs(os.path.dirname(elsewhere), exist_ok=True)
        path = os.path.join(tree, link)
        if os.path.exists(path):
            shutil.move(path, elsewhere)
        elif link.endswith(".md"):
            with open(elsewhere, "w", encoding="utf-8") as fh:
                fh.write("x\n")
        else:
            os.makedirs(elsewhere)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        os.symlink(os.path.abspath(elsewhere), path)


def folder(case):
    with tempfile.TemporaryDirectory() as tmp:
        tree = os.path.join(tmp, "repo")
        os.makedirs(tree)
        build(tree, case)
        return sh(["check-folder", case["project"]], cwd=tree)


def main():
    with open(CASES, encoding="utf-8") as fh:
        data = json.load(fh)
    errors = []
    for p in data["accept"]:
        r = sh(["validate-path", p])
        if r.returncode != 0 or r.stdout != f"project={p}\n":
            errors.append(f"path accept {p!r}: rc={r.returncode} {r.stderr!r}")
    for name, p in data["reject"].items():
        if sh(["validate-path", p]).returncode == 0:
            errors.append(f"path reject {name} {p!r} was accepted")
    for p, want in data["budget"].items():
        r = sh(["slug-budget", p])
        if r.stdout.strip() != str(want):
            errors.append(f"budget {p!r}: got {r.stdout!r}, want {want}")
    for p in data["prefix_accept"]:
        if sh(["validate-prefix", p]).returncode != 0:
            errors.append(f"prefix accept {p!r} was rejected")
    for name, p in data["prefix_reject"].items():
        if sh(["validate-prefix", p]).returncode == 0:
            errors.append(f"prefix reject {name} {p!r} was accepted")
    r = folder(data["folder_accept"])
    if r.returncode != 0:
        errors.append(f"folder accept: {r.stderr!r}")
    for name, case in data["folder_reject"].items():
        r = folder(case)
        if r.returncode == 0:
            errors.append(f"folder reject {name} was accepted")
        elif case["project"] not in r.stderr:
            errors.append(f"folder reject {name} does not name the folder: {r.stderr!r}")
    if errors:
        print("verify-project-path-grammar: FAIL")
        for e in errors:
            print("  " + e)
        return 1
    print("verify-project-path-grammar: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
