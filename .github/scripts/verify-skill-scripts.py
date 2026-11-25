#!/usr/bin/env python3
"""Gate 173 -- the skill scripts under .claude/skills/*/scripts/ keep working.

specs/131-skill-script-gate. Those scripts reach into .github/scripts and no
other gate noticed when a name they import was renamed (the diff_name_list
rename in redrive_candidates.py), and nothing ran their --self-test. This gate
checks both, statically and offline:

  python3 .github/scripts/verify-skill-scripts.py             check the tree
  python3 .github/scripts/verify-skill-scripts.py --self-test seeded defects

Loader inventory (T001, research D2/D3) -- how the six scripts reach the tree
today. Only these patterns are recognised; any other loader fails loudly as
`unrecognised-loader` instead of being skipped:

  * sys.path.insert(0, <repo>/.github/scripts) then `from M import n`
    (unpinned-container-steps.py, redrive_candidates.py)
  * the same insertion then `import M as m` with `m.attr` loads
    (thrash_signals.py as wc, board_now.py as wc_board_status)
  * importlib.util.spec_from_file_location with a literal "<module>.py"
    argument (none today; counted as a module reach)
  * stdlib and third-party imports (yaml) are never repo names
  * --self-test is declared by the string "--self-test" in an add_argument
    call or a comparison (thrash_signals.py today)

A skill script is never imported or executed except as `<script> --self-test`
in a subprocess with GH_TOKEN/GITHUB_TOKEN unset and a 60 s timeout.
"""
import ast
import glob
import os
import subprocess
import sys
import tempfile
import warnings

# Parsing other scripts must not print their own escape-sequence warnings.
warnings.filterwarnings("ignore", category=SyntaxWarning)

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, ".."))
REPO_ROOT = os.path.dirname(REPO_ROOT)
FIXTURES = os.path.join(HERE, "verify-skill-scripts-fixtures")
TIMEOUT = 60

# (skills glob, modules dir) relative to a root; fixtures use a flatter shape
# so no fixture needs a `.claude/` directory of its own.
REAL_LAYOUT = (os.path.join(".claude", "skills", "*", "scripts", "*.py"),
               os.path.join(".github", "scripts"))
FIXTURE_LAYOUT = (os.path.join("skills", "*", "scripts", "*.py"), "scripts")


def parse(path):
    with open(path, encoding="utf-8") as fh:
        return ast.parse(fh.read(), filename=path)


def module_names(path):
    """Top-level names of a module, by AST only. Returns (names, has_star)."""
    names, star = set(), False

    def targets(node):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, (ast.Tuple, ast.List)):
            for elt in node.elts:
                targets(elt)

    def walk(body):
        nonlocal star
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names.add(node.name)
            elif isinstance(node, ast.Assign):
                for t in node.targets:
                    targets(t)
                if any(isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets):
                    for c in ast.walk(node.value):
                        if isinstance(c, ast.Constant) and isinstance(c.value, str):
                            names.add(c.value)
            elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
                targets(node.target)
            elif isinstance(node, ast.Import):
                for a in node.names:
                    names.add(a.asname or a.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                for a in node.names:
                    if a.name == "*":
                        star = True
                    else:
                        names.add(a.asname or a.name)
            elif isinstance(node, (ast.If, ast.Try, ast.With, ast.For, ast.While)):
                for field in ("body", "orelse", "finalbody"):
                    walk(getattr(node, field, []))
                for h in getattr(node, "handlers", []):
                    walk(h.body)

    walk(parse(path).body)
    return names, star


def has_self_test(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr == "add_argument":
            if any(isinstance(a, ast.Constant) and a.value == "--self-test" for a in node.args):
                return True
        if isinstance(node, ast.Compare):
            for c in [node.left] + node.comparators:
                if isinstance(c, ast.Constant) and c.value == "--self-test":
                    return True
    return False


def inserts_scripts_path(tree):
    """True when the script puts a scripts directory on sys.path."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr in ("insert", "append") \
                and isinstance(node.func.value, ast.Attribute) \
                and node.func.value.attr == "path":
            return True
    return False


def third_party_names(mod_dir, repo_mods):
    """Top-level imports used by the repo's own scripts that are neither
    stdlib nor repo modules: the third-party allowlist, read from the tree."""
    found = set()
    for path in glob.glob(os.path.join(mod_dir, "*.py")):
        try:
            tree = parse(path)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                found.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
                found.add(node.module.split(".")[0])
    return {n for n in found if n not in sys.stdlib_module_names and n not in repo_mods}


def collect_reaches(tree, repo_mods, scripts_on_path, third_party):
    """Yield (module, name|None, kind, line); `name` None for module reaches.
    A reason string instead of kind marks an unrecognised loader."""
    alias = {}  # local name -> module
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and not node.level:
            top = node.module.split(".")[0]
            if top in repo_mods:
                for a in node.names:
                    out.append((top, a.name, "from-import", node.lineno))
            elif scripts_on_path and top not in sys.stdlib_module_names \
                    and top not in third_party:
                out.append((top, None, "module", node.lineno))
        elif isinstance(node, ast.Import):
            for a in node.names:
                top = a.name.split(".")[0]
                if top in repo_mods:
                    alias[a.asname or top] = top
                    out.append((top, None, "module", node.lineno))
                elif scripts_on_path and top not in sys.stdlib_module_names \
                        and top not in third_party:
                    out.append((top, None, "module", node.lineno))
        elif isinstance(node, ast.Call):
            fn = node.func
            if isinstance(fn, ast.Attribute) and fn.attr == "spec_from_file_location":
                lits = [c.value for a in node.args for c in ast.walk(a)
                        if isinstance(c, ast.Constant) and isinstance(c.value, str)
                        and c.value.endswith(".py")]
                if lits:
                    out.append((os.path.basename(lits[0])[:-3], None, "module", node.lineno))
                else:
                    out.append(("<loader>", None, "unrecognised-loader", node.lineno))
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) \
                and isinstance(node.ctx, ast.Load) and node.value.id in alias:
            out.append((alias[node.value.id], node.attr, "attribute", node.lineno))
    return out


def run_self_test_of(script, root):
    env = {k: v for k, v in os.environ.items() if k not in ("GH_TOKEN", "GITHUB_TOKEN")}
    try:
        proc = subprocess.run([sys.executable, script, "--self-test"], cwd=root, env=env,
                              capture_output=True, text=True, timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        return False
    return proc.returncode == 0


def check(root, layout):
    """Return (findings, scripts, reaches, selftests). A finding is
    (relpath, module, name, reason)."""
    skills_glob, mods_rel = layout
    mod_dir = os.path.join(root, mods_rel)
    scripts = sorted(glob.glob(os.path.join(root, skills_glob)))
    findings = []
    if not scripts:
        return [("-", "-", "-", "no-skill-scripts")], 0, 0, 0
    repo_mods = {os.path.basename(p)[:-3] for p in glob.glob(os.path.join(mod_dir, "*.py"))}
    repo_mods |= {os.path.basename(os.path.dirname(p))
                  for p in glob.glob(os.path.join(mod_dir, "*", "__init__.py"))}
    third = third_party_names(mod_dir, repo_mods)
    cache = {}
    reach_count = selftests = 0
    for script in scripts:
        rel = os.path.relpath(script, root)
        tree = parse(script)
        reaches = collect_reaches(tree, repo_mods, inserts_scripts_path(tree), third)
        for module, name, kind, _line in reaches:
            reach_count += 1
            if kind == "unrecognised-loader":
                findings.append((rel, module, "-", "unrecognised-loader"))
                continue
            mpath = os.path.join(mod_dir, module + ".py")
            if not (module in repo_mods):
                findings.append((rel, module, "-", "missing-module"))
                continue
            if name is None:
                continue
            if module not in cache:
                cache[module] = module_names(mpath) if os.path.exists(mpath) else (set(), True)
            names, star = cache[module]
            sub = os.path.join(mod_dir, module, name)
            if name in names or star or os.path.exists(sub + ".py") or os.path.isdir(sub):
                continue
            findings.append((rel, module, name, "missing-name"))
        if has_self_test(tree):
            selftests += 1
            if not run_self_test_of(script, root):
                findings.append((rel, os.path.basename(script)[:-3], "--self-test",
                                 "self-test-failed"))
    return findings, len(scripts), reach_count, selftests


def report(findings, scripts, reaches, selftests):
    for rel, module, name, reason in findings:
        print(f"skill-script: {rel}: {module}.{name}: {reason}")
    if findings:
        print(f"verify-skill-scripts: {len(findings)} finding(s)")
        return 1
    print(f"verify-skill-scripts: OK ({scripts} scripts, {reaches} reaches, "
          f"{selftests} self-tests)")
    return 0


# case directory -> reasons that must appear (empty set: must pass clean)
SEEDED = {
    "bad-missing-name": {"missing-name"},
    "bad-attribute": {"missing-name"},
    "bad-missing-module": {"missing-module"},
    "bad-self-test": {"self-test-failed"},
    "bad-new-script": {"missing-name"},
    "ok-stdlib-thirdparty": set(),
    "ok-self-test": set(),
}


def self_test():
    failures = []
    for case, want in SEEDED.items():
        root = os.path.join(FIXTURES, case)
        if not os.path.isdir(root):
            failures.append(f"{case}: fixture directory missing")
            continue
        found, scripts, _r, _t = check(root, FIXTURE_LAYOUT)
        reasons = {f[3] for f in found}
        if want and not want <= reasons:
            failures.append(f"{case}: expected {sorted(want)}, got {sorted(reasons)}")
        if not want and found:
            failures.append(f"{case}: expected clean, got {found}")
    # bad-new-script: the finding names the second script, found with no list.
    found, _s, _r, _t = check(os.path.join(FIXTURES, "bad-new-script"), FIXTURE_LAYOUT)
    if not any("second.py" in f[0] for f in found):
        failures.append("bad-new-script: the newly added script was not discovered")
    with tempfile.TemporaryDirectory() as empty:
        found, scripts, _r, _t = check(empty, FIXTURE_LAYOUT)
        if scripts != 0 or not found:
            failures.append("empty tree: a gate with no subject must fail loudly")
    for line in failures:
        print(f"verify-skill-scripts --self-test: FAIL {line}")
    if failures:
        return 1
    print(f"verify-skill-scripts --self-test: OK ({len(SEEDED) + 1} cases caught)")
    return 0


def main(argv):
    if "--self-test" in argv:
        return self_test()
    return report(*check(REPO_ROOT, REAL_LAYOUT))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
