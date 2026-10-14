#!/usr/bin/env python3
"""Gate: per-project feature numbering (spec 114 FR-009, FR-010, research D6/D13).

Runs the real shell over fixtures/project-numbering/cases.json:
  * `_shared/project-name.sh next-number <P>` in a scratch clone of a scratch
    bare origin carrying the fixture's `specs/` directories and branches: the
    number is the highest of `P/specs/` and P's own anchored draft/spec
    branches plus one; nested, sibling and root refs never count for P; the
    root counts only refs with no `/` after the prefix; a torn-down branch's
    landed directory keeps its number taken;
  * watchdog.yml's "Collect: spec collision" step, with a fake `gh` serving
    the open PRs: only the inspected lifecycle's own project can claim its
    number, so another project's `004` is never a collision.

Exit 0 when every case behaves; 1 otherwise.
"""
import json
import os
import stat
import subprocess
import sys
import tempfile

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT = os.path.join(ROOT, ".github", "actions", "_shared", "project-name.sh")
WATCHDOG = os.path.join(ROOT, ".github", "workflows", "watchdog.yml")
CASES = os.path.join(ROOT, ".github", "scripts", "fixtures", "project-numbering", "cases.json")

FAKE_GH = """#!/usr/bin/env bash
if [ "$1 $2" = "pr list" ]; then cat "$FAKE_PRS"; exit 0; fi
echo "fake gh: unexpected $*" >&2; exit 2
"""


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def touch_dirs(base, dirs):
    for d in dirs:
        os.makedirs(os.path.join(base, d), exist_ok=True)
        with open(os.path.join(base, d, "spec.md"), "w", encoding="utf-8") as fh:
            fh.write("x\n")


def next_number(case, env):
    with tempfile.TemporaryDirectory() as tmp:
        origin, work = os.path.join(tmp, "origin.git"), os.path.join(tmp, "work")
        git(tmp, "init", "-q", "--bare", origin)
        git(tmp, "init", "-q", work)
        git(work, "config", "user.email", "g@example.invalid")
        git(work, "config", "user.name", "gate")
        git(work, "remote", "add", "origin", origin)
        touch_dirs(work, case["dirs"])
        with open(os.path.join(work, "README"), "w", encoding="utf-8") as fh:
            fh.write("x\n")
        git(work, "add", "-A")
        git(work, "commit", "-q", "-m", "base")
        for b in case["branches"]:
            git(work, "push", "-q", "origin", f"HEAD:refs/heads/{b}")
        r = subprocess.run(["bash", SCRIPT, "next-number", case["project"]], cwd=work,
                           capture_output=True, text=True, env={**os.environ, **env}, check=False)
        return r


def collision_step():
    with open(WATCHDOG, encoding="utf-8") as fh:
        doc = yaml.safe_load(fh)
    for job in doc["jobs"].values():
        for s in job.get("steps") or []:
            if s.get("id") == "collect-spec-collision":
                return s["run"]
    raise KeyError("collect-spec-collision")


def collision(case, script, env):
    with tempfile.TemporaryDirectory() as tmp:
        work, temp, bindir = (os.path.join(tmp, d) for d in ("work", "temp", "bin"))
        for d in (work, temp, bindir):
            os.makedirs(d)
        touch_dirs(work, case["dirs"])
        prs = os.path.join(tmp, "prs.json")
        with open(prs, "w", encoding="utf-8") as fh:
            json.dump([{"number": n, "headRefName": b} for n, b in case["prs"]], fh)
        gh = os.path.join(bindir, "gh")
        with open(gh, "w", encoding="utf-8") as fh:
            fh.write(FAKE_GH)
        os.chmod(gh, os.stat(gh).st_mode | stat.S_IXUSR)
        for name in ("signals.json", "collector-outcomes.json"):
            with open(os.path.join(temp, name), "w", encoding="utf-8") as fh:
                fh.write("[]")
        summary = os.path.join(tmp, "summary")
        # The collector's project and bare slug come from the shared parser
        # through wing-commander-inspected-run-identity (T066); derive them
        # the same way.
        parsed = subprocess.run(["bash", SCRIPT, "names", "slug", case["slug"]], capture_output=True,
                                text=True, check=False).stdout
        names = dict(line.split("=", 1) for line in parsed.splitlines() if "=" in line)
        full = {**os.environ, **env,
                "PATH": bindir + os.pathsep + os.environ.get("PATH", ""),
                "GH_TOKEN": "fake", "GITHUB_REPOSITORY": "o/r", "FAKE_PRS": prs,
                "RESOLVED_STAGE": "intake", "RESOLVED_STAGE_SOURCE": "name",
                "RUN_CONCLUSION": "failure", "SLUG": case["slug"],
                "OWN_PROJECT": names.get("project", ""), "LIFECYCLE_SLUG": names.get("slug", ""),
                "RUNNER_TEMP": temp, "GITHUB_STEP_SUMMARY": summary}
        r = subprocess.run(["bash", "-e", "-c", script], cwd=work, capture_output=True,
                           text=True, env=full, check=False)
        with open(os.path.join(temp, "signals.json"), encoding="utf-8") as fh:
            signals = json.load(fh)
        return r, signals


def main():
    with open(CASES, encoding="utf-8") as fh:
        data = json.load(fh)
    env = data["env"]
    errors = []
    for case in data["next_number"]:
        r = next_number(case, env)
        if r.returncode != 0 or r.stdout.strip() != case["want"]:
            errors.append(f"next-number {case['name']!r}: rc={r.returncode} got={r.stdout.strip()!r} "
                          f"want={case['want']!r} err={r.stderr.strip()!r}")
    script = collision_step()
    for case in data["collision"]:
        r, signals = collision(case, script, env)
        claimants = [c for s in signals for c in s.get("facts", {}).get("claimants", [])]
        if r.returncode != 0 or len(claimants) != case["claimants"]:
            errors.append(f"collision {case['name']!r}: rc={r.returncode} claimants={claimants!r} "
                          f"want {case['claimants']} err={r.stderr.strip()!r}")
    if errors:
        print("verify-project-numbering: FAIL")
        for e in errors:
            print("  " + e)
        return 1
    print(f"verify-project-numbering: OK ({len(data['next_number'])} numbering, "
          f"{len(data['collision'])} collision)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
