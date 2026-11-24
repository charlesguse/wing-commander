#!/usr/bin/env python3
"""Gate 173 -- every `.claude/skills/*/scripts/*.py` still imports, and
`thrash_signals.py --self-test` still passes.

The skill scripts import helpers from `.github/scripts` (board_prove,
board_route_backstop, wc_board_status, wc_convergence, wc_shell_pin ...).
A rename there broke a skill with every other gate green, because no gate
ran the skill scripts. Each script is loaded here by path (its
`if __name__ == "__main__"` guard keeps that side-effect free), so a
missing module or name fails at import.

    verify-skill-scripts-import.py             check the real tree
    verify-skill-scripts-import.py --self-test a broken import fails
"""
import ast
import glob
import importlib.util
import os
import subprocess
import sys
import tempfile

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
SELF_TESTED = ("thrash_signals.py",)


def load(path):
    name = "skillscript_" + os.path.basename(path)[:-3].replace("-", "_")
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def missing_attrs(mod, path):
    """`module.name` uses that importing alone never resolves (call-time access)."""
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    missing = set()
    for node in ast.walk(tree):
        if (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
                and isinstance(getattr(mod, node.value.id, None), type(sys))
                and not hasattr(getattr(mod, node.value.id), node.attr)):
            missing.add(node.value.id + "." + node.attr)
    return sorted(missing)


def check(root):
    problems = []
    paths = sorted(glob.glob(os.path.join(root, ".claude", "skills", "*", "scripts", "*.py")))
    if not paths:
        problems.append("no skill scripts found under .claude/skills/*/scripts")
    for path in paths:
        rel = os.path.relpath(path, root)
        try:
            gone = missing_attrs(load(path), path)
            if gone:
                problems.append(f"{rel}: names missing from imported modules: {', '.join(gone)}")
                continue
        except BaseException as exc:  # SystemExit from a bad import too
            problems.append(f"{rel}: import failed: {type(exc).__name__}: {exc}")
            continue
        if os.path.basename(path) in SELF_TESTED:
            r = subprocess.run([sys.executable, path, "--self-test"], cwd=root,
                               capture_output=True, text=True)
            if r.returncode != 0:
                problems.append(f"{rel}: --self-test exited {r.returncode}: "
                                f"{(r.stdout + r.stderr).strip()[-300:]}")
    return problems


def self_test():
    sys.path.insert(0, os.path.join(REPO_ROOT, ".github", "scripts"))
    with tempfile.TemporaryDirectory() as d:
        sdir = os.path.join(d, ".claude", "skills", "x", "scripts")
        os.makedirs(sdir)
        with open(os.path.join(sdir, "good.py"), "w") as f:
            f.write("import os\n")
        if check(d):
            print("FAIL: a clean script was flagged")
            return 1
        with open(os.path.join(sdir, "bad.py"), "w") as f:
            f.write("from board_prove import renamed_away\n")
        if not any("bad.py" in p for p in check(d)):
            print("FAIL: a broken import passed")
            return 1
        with open(os.path.join(sdir, "bad.py"), "w") as f:
            f.write("import os\n\ndef f():\n    return os.renamed_away\n")
        if not any("os.renamed_away" in p for p in check(d)):
            print("FAIL: a call-time attribute rename passed")
            return 1
    with tempfile.TemporaryDirectory() as empty:
        if not check(empty):
            print("FAIL: an empty tree passed")
            return 1
    print("self-test OK")
    return 0


def main():
    if "--self-test" in sys.argv[1:]:
        return self_test()
    problems = check(REPO_ROOT)
    for p in problems:
        print("FAIL:", p)
    if not problems:
        print("OK: every skill script imports")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
