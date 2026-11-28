#!/usr/bin/env python3
"""Gate: per-project feature numbering (spec 114 FR-009, FR-010, research D6/D13).

Runs the real shell over fixtures/project-numbering/cases.json:
  * `_shared/project-name.sh next-number <P>` in a scratch clone of a scratch
    bare origin carrying the fixture's `specs/` directories and branches: the
    number is the highest of `P/specs/` and P's own anchored draft/spec
    branches plus one; nested, sibling and root refs never count for P; the
    root counts only refs with no `/` after the prefix; a torn-down branch's
    landed directory keeps its number taken;
  * wing-commander-project's "Allocate feature number" and "Release
    feature-number reservation" steps (the real run blocks), with a fake
    `gh` whose label store creates atomically (mkdir) and answers a
    second create of one name `already_exists`, as GitHub does: a taken
    number moves on, a number a branch took while it was being reserved is
    given back and the next one won, any other API error fails holding
    nothing, and three reservations started at once win three different
    numbers -- intake holds no repository-wide group (#889), so this is
    what keeps feature numbers unique;
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
import urllib.parse

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT = os.path.join(ROOT, ".github", "actions", "_shared", "project-name.sh")
WATCHDOG = os.path.join(ROOT, ".github", "workflows", "watchdog.yml")
PROJECT_ACTION = os.path.join(ROOT, ".github", "actions", "wing-commander-project")
CASES = os.path.join(ROOT, ".github", "scripts", "fixtures", "project-numbering", "cases.json")

FAKE_GH = """#!/usr/bin/env bash
if [ "$1 $2" = "pr list" ]; then cat "$FAKE_PRS"; exit 0; fi
echo "fake gh: unexpected $*" >&2; exit 2
"""


# A label store with GitHub's create semantics: POST of an existing name is a
# 422 `already_exists` (body on stdout, status on stderr, exit 1). mkdir is
# the atomic create. FAKE_RACE_NUM: when that number's label is created,
# first push a branch carrying it, as a spec whose intake already released
# its reservation would. FAKE_FAIL: every POST is a 500.
FAKE_LABEL_GH = r"""#!/usr/bin/env bash
store="$FAKE_STORE"
if [ "$1 $2 $3" = "api -X POST" ] && [ "$4" = "repos/$GH_REPO/labels" ]; then
  name=""
  shift 4
  while [ "$#" -gt 0 ]; do
    case "$1" in -f) case "$2" in name=*) name="${2#name=}" ;; esac; shift 2 ;; *) shift ;; esac
  done
  if [ -n "${FAKE_FAIL:-}" ]; then echo '{"message":"Server Error"}'; echo "gh: Server Error (HTTP 500)" >&2; exit 1; fi
  enc="$(printf '%s' "$name" | jq -sRr @uri)"
  if [ -n "${FAKE_RACE_NUM:-}" ] && [ "${name##*/}" = "spec-number:$FAKE_RACE_NUM" -o "${name##*/}" = "$FAKE_RACE_NUM" ]; then
    git push -q origin "HEAD:refs/heads/spec-draft/${FAKE_RACE_PROJECT:+$FAKE_RACE_PROJECT/}$FAKE_RACE_NUM-race" >/dev/null 2>&1
  fi
  if mkdir "$store/$enc" 2>/dev/null; then echo "{\"name\":\"$name\"}"; exit 0; fi
  echo '{"message":"Validation Failed","errors":[{"resource":"Label","code":"already_exists","field":"name"}]}'
  echo "gh: Validation Failed (HTTP 422)" >&2
  exit 1
fi
if [ "$1 $2 $3" = "api -X DELETE" ]; then
  enc="${4#repos/$GH_REPO/labels/}"
  rmdir "$store/$enc" 2>/dev/null && exit 0
  echo '{"message":"Not Found"}'; echo "gh: Not Found (HTTP 404)" >&2; exit 1
fi
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


def scratch_repo(tmp, dirs, branches):
    origin, work = os.path.join(tmp, "origin.git"), os.path.join(tmp, "work")
    git(tmp, "init", "-q", "--bare", origin)
    git(tmp, "init", "-q", work)
    git(work, "config", "user.email", "g@example.invalid")
    git(work, "config", "user.name", "gate")
    git(work, "remote", "add", "origin", origin)
    touch_dirs(work, dirs)
    with open(os.path.join(work, "README"), "w", encoding="utf-8") as fh:
        fh.write("x\n")
    git(work, "add", "-A")
    git(work, "commit", "-q", "-m", "base")
    for b in branches:
        git(work, "push", "-q", "origin", f"HEAD:refs/heads/{b}")
    return work


def stored(store):
    return sorted(urllib.parse.unquote(n) for n in os.listdir(store))


def composite_step(sid):
    with open(os.path.join(PROJECT_ACTION, "action.yml"), encoding="utf-8") as fh:
        doc = yaml.safe_load(fh)
    step = next((s for s in doc["runs"]["steps"] if s.get("id") == sid), None)
    return step["run"] if step else f"echo 'no composite step {sid}'; exit 1"


def run_composite(sid, cwd, env, tmp, tag):
    """Start one composite step's run block the way a `shell: bash` step runs."""
    out = os.path.join(tmp, f"out-{tag}")
    open(out, "w", encoding="utf-8").close()
    full = {**env, "GITHUB_ACTION_PATH": PROJECT_ACTION, "GITHUB_OUTPUT": out,
            "GITHUB_STEP_SUMMARY": os.path.join(tmp, f"summary-{tag}")}
    proc = subprocess.Popen(["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", composite_step(sid)],
                            cwd=cwd, env=full, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    return proc, out


def read_outputs(path):
    with open(path, encoding="utf-8") as fh:
        return dict(line.rstrip("\n").split("=", 1) for line in fh if "=" in line)


def reserve(case, env):
    """Run the allocate step (case["parallel"] copies at once) against the fake
    label store; returns ([(rc, outputs, log)], labels left in the store)."""
    with tempfile.TemporaryDirectory() as tmp:
        work = scratch_repo(tmp, case["dirs"], case["branches"])
        store, bindir = os.path.join(tmp, "store"), os.path.join(tmp, "bin")
        os.makedirs(store)
        os.makedirs(bindir)
        for name in case.get("labels", []):
            os.makedirs(os.path.join(store, urllib.parse.quote(name, safe="")))
        gh = os.path.join(bindir, "gh")
        with open(gh, "w", encoding="utf-8") as fh:
            fh.write(FAKE_LABEL_GH)
        os.chmod(gh, os.stat(gh).st_mode | stat.S_IXUSR)
        full = {**os.environ, **env, **case.get("env", {}), "PATH": bindir + os.pathsep + os.environ.get("PATH", ""),
                "GH_TOKEN": "fake", "GH_REPO": "o/r", "FAKE_STORE": store, "PROJECT": case["project"]}
        procs = [run_composite("number", work, full, tmp, i) for i in range(case.get("parallel", 1))]
        results = []
        for p, out in procs:
            log, _ = p.communicate(timeout=60)
            results.append((p.returncode, read_outputs(out), log.strip()))
        if case.get("release"):
            labels = [o["reservation"] for _, o, _ in results if o.get("reservation")]
            for n, label in enumerate(labels + ["spec:001-not-a-reservation"]):
                p, _ = run_composite("release", work, {**full, "LABEL": label}, tmp, f"r{n}")
                log, _ = p.communicate(timeout=60)
                if (p.returncode == 0) != label.startswith("spec-number:"):
                    results.append((1, {}, f"release of {label!r}: rc={p.returncode} {log.strip()}"))
        return results, stored(store)


def check_reserve(case, env):
    results, left = reserve(case, env)
    want = case["want"]
    if want is None:
        if any(rc == 0 for rc, _, _ in results) or left != sorted(case.get("labels", [])):
            return f"rc={[r[0] for r in results]} left={left!r}, want a failure holding nothing new"
        return None
    if any(rc != 0 for rc, _, _ in results):
        return f"failed: {[(rc, err) for rc, _, err in results if rc != 0]!r}"
    got = sorted(o.get("num", "") for _, o, _ in results)
    if got != sorted(want):
        return f"numbers {got!r}, want {sorted(want)!r}"
    for _, o, _ in results:
        if o.get("reservation") != "spec-number:" + (case["project"] + "/" if case["project"] else "") + o["num"]:
            return f"reservation {o.get('reservation')!r} does not name number {o['num']!r}"
    if left != sorted(case["left"]):
        return f"labels left {left!r}, want {sorted(case['left'])!r}"
    return None


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
    for case in data["reserve"]:
        err = check_reserve(case, env)
        if err:
            errors.append(f"reserve-number {case['name']!r}: {err}")
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
          f"{len(data['reserve'])} reserve, {len(data['collision'])} collision)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
