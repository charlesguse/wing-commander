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
ROOT_COMPAT = os.path.join(ROOT, ".github", "scripts", "fixtures", "project-root-compat", "cases.json")


def run(env_extra, *args):
    env = {**os.environ, **env_extra}
    return subprocess.run(["bash", SCRIPT, *args], capture_output=True, text=True, env=env, check=False)


def main():
    with open(CASES, encoding="utf-8") as fh:
        data = json.load(fh)
    env = data["env"]
    errors = []
    for case in data["accept"]:
        # A case may override the prefixes (overlapping-prefix configurations).
        r = run({**env, **case.get("env", {})}, "parse", case["kind"], case["name"])
        want = f"project={case['project']}\nslug={case['slug']}\n"
        if r.returncode != 0 or r.stdout != want:
            errors.append(f"accept {case['kind']} {case['name']!r}: rc={r.returncode} out={r.stdout!r} err={r.stderr!r}")
    for case in data["reject"]:
        r = run(env, "parse", case["kind"], case["name"])
        if r.returncode == 0:
            errors.append(f"reject {case['kind']} {case['name']!r} was accepted: {r.stdout!r}")
    # A grammar check tests the whole value, never one line of it: an
    # embedded newline is refused by every validator.
    for mode, value in (("validate-path", "ok\n../../etc"), ("validate-prefix", "node:\n$(x)")):
        if run(env, mode, value).returncode == 0:
            errors.append(f"{mode} accepted the multi-line value {value!r}")
    # Builder side of the spec-dir round trip (FR-013); the accept cases above
    # assert the same (P, NNN-slug) comes back from every kind.
    spec_dir = run(env, "spec-dir", "ideas/alpha", "001-login")
    if spec_dir.stdout.strip() != "ideas/alpha/specs/001-login":
        errors.append(f"spec-dir builder (subfolder): {spec_dir.stdout!r}")
    spec_dir = run(env, "spec-dir", "", "001-login")
    if spec_dir.stdout.strip() != "specs/001-login":
        errors.append(f"spec-dir builder (root): {spec_dir.stdout!r}")
    # `names` (MF-21/T066): every derived name from one parse, for callers
    # that used to split a path inline; plan and tasks branches parse when
    # their prefixes are set.
    names_env = {**env, "PLAN_PREFIX": "plan/", "TASKS_PREFIX": "tasks/"}
    for kind, name, want in (
        ("slug", "ideas/alpha/001-login", ("ideas/alpha", "001-login", "ideas/alpha/001-login",
                                           "ideas/alpha/specs/001-login", "specs/001-login")),
        ("spec-dir", "specs/001-login", ("", "001-login", "001-login", "specs/001-login", "specs/001-login")),
        ("branch", "plan/ideas/alpha/001-login", ("ideas/alpha", "001-login", "ideas/alpha/001-login",
                                                  "ideas/alpha/specs/001-login", "specs/001-login")),
        ("branch", "tasks/001-login", ("", "001-login", "001-login", "specs/001-login", "specs/001-login")),
    ):
        r = run(names_env, "names", kind, name)
        expect = "".join(f"{k}={v}\n" for k, v in zip(("project", "slug", "qualified", "spec_dir", "spec_dir_rel"), want))
        if r.returncode != 0 or r.stdout != expect:
            errors.append(f"names {kind} {name!r}: rc={r.returncode} out={r.stdout!r}, want {expect!r}")
    if run(names_env, "names", "slug", "/001-login").returncode == 0:
        errors.append("names: a name with an empty project was accepted")
    if run(env, "names", "branch", "plan/001-login").returncode == 0:
        errors.append("names: a plan branch parsed with no plan prefix configured")
    # Attribution (FR-013, research D13): the watchdog and the fold-cycle
    # guard attribute a run by parsing whichever name they hold. Every form of
    # one lifecycle must give its own (P, slug) and spec-dir, and lifecycles
    # sharing an NNN-slug across projects must never collapse into one.
    attributed = 0
    for group in data.get("attribution", []):
        seen = set()
        for lc in group["lifecycles"]:
            pair = (lc["project"], lc["slug"])
            if pair in seen:
                errors.append(f"attribution fixture lists {pair!r} twice")
            seen.add(pair)
            for n in lc["names"]:
                r = run(env, "parse", n["kind"], n["name"])
                got = dict(line.split("=", 1) for line in r.stdout.splitlines() if "=" in line)
                if r.returncode != 0 or (got.get("project"), got.get("slug")) != pair:
                    errors.append(f"attribution {n['kind']} {n['name']!r}: got {got!r}, want {pair!r}")
                    continue
                d = run(env, "spec-dir", got["project"], got["slug"]).stdout.strip()
                if d != lc["spec_dir"]:
                    errors.append(f"attribution {n['kind']} {n['name']!r}: spec-dir {d!r}, want {lc['spec_dir']!r}")
                attributed += 1
    # Root compatibility (FR-016, SC-003): every root name parses to the empty
    # project and its own slug, and builds the same spec-dir and budget.
    with open(ROOT_COMPAT, encoding="utf-8") as fh:
        compat = json.load(fh)
    for n in compat["names"]:
        r = run(compat["env"], "parse", n["kind"], n["name"])
        if r.returncode != 0 or r.stdout != f"project=\nslug={n['slug']}\n":
            errors.append(f"root-compat {n['kind']} {n['name']!r}: rc={r.returncode} out={r.stdout!r}")
        d = run(compat["env"], "spec-dir", "", n["slug"]).stdout.strip()
        if d != compat["spec_dir"]:
            errors.append(f"root-compat {n['name']!r}: spec-dir {d!r}, want {compat['spec_dir']!r}")
    b = run(compat["env"], "slug-budget", "").stdout.strip()
    if b != str(compat["slug_budget"]):
        errors.append(f"root-compat slug-budget {b!r}, want {compat['slug_budget']}")
    if errors:
        print("verify-project-name-parser: FAIL")
        for e in errors:
            print("  " + e)
        return 1
    print(f"verify-project-name-parser: OK ({len(data['accept'])} accept, {len(data['reject'])} reject, {attributed} attributed)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
