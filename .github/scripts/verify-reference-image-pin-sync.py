#!/usr/bin/env python3
"""Gate 156 -- the reference-image pin sync does what its contract says
(specs/111-reference-image-pin-sync, contracts/pin-sync-script.md).

WHY THIS EXISTS
---------------
After a rebuild the sync writes WING_COMMANDER_CONTAINER_IMAGE on two
repositories with a credential that can write variables. Every way that can go
wrong is silent unless something drives it: a write after a failed check, a
credential that reaches more than the two repositories, a half-written pair
reported as success, a token echoed into a log.

WHAT IT CHECKS
--------------
1. Script behaviour: runs _shared/sync-reference-image-pin.sh against a
   stubbed `gh` (tests/reference-image-pin-sync/gh-stub.sh) for each case
   below, asserting the exit code, each repository's status, the exact set of
   writes, and that the token value appears in no output.
2. Workflow wiring (wing-commander-e2e-reference-image.yml): sync-pins needs
   build-and-publish and startup-check, serialises on its own concurrency
   group, startup-check exposes `passed`, the secret is bound to the one
   sync step, the failure steps are guarded to that step's failure, the
   issue is closed on success, and a last step re-fails the job.
3. Single home: no other workflow or composite carries a write of the
   variable, and auto-release.yml neither calls nor reads the script.
   (provision-e2e-target.sh pins a freshly provisioned target at its own
   creation and is a different mechanism, outside .github/workflows and
   .github/actions.)

Usage: python3 .github/scripts/verify-reference-image-pin-sync.py
Requires: bash, jq.
"""
import glob
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
GH_DIR = os.path.join(HERE, "..")
SCRIPT = os.path.join(GH_DIR, "actions", "_shared", "sync-reference-image-pin.sh")
STUB = os.path.join(HERE, "tests", "reference-image-pin-sync", "gh-stub.sh")
WORKFLOW = os.path.join(GH_DIR, "workflows", "wing-commander-e2e-reference-image.yml")

THIS = "octo/wing"
E2E = "octo/e2e"
IMAGE = "ghcr.io/octo/img"
DIGEST = "sha256:" + "a" * 64
OLD = IMAGE + "@sha256:" + "b" * 64
NEW = IMAGE + "@" + DIGEST
TOKEN = "ghp_SECRETTOKENVALUE123"
AMBIENT = "ambient-workflow-token"

# name: env overrides + stub state -> expectations
CASES = {
    "both-written": dict(
        vars={THIS: OLD, E2E: OLD}, reach=[THIS, E2E],
        exit=0, status={THIS: "written", E2E: "written"}, writes=[THIS, E2E]),
    "all-current": dict(
        vars={THIS: NEW, E2E: NEW}, reach=[THIS, E2E],
        exit=0, status={THIS: "current", E2E: "current"}, writes=[]),
    "checks-failed": dict(
        env={"CHECKS_PASSED": "false"}, vars={}, reach=[],
        exit=0, status={THIS: "skipped", E2E: "skipped"}, writes=[], no_api=True),
    "e2e-unset": dict(
        env={"E2E_REPO": ""}, vars={THIS: OLD}, reach=[THIS],
        exit=0, status={THIS: "written", "test repository": "skipped"}, writes=[THIS]),
    "superseded": dict(
        runs=[3, 99], vars={THIS: OLD, E2E: OLD}, reach=[THIS, E2E],
        exit=0, status={THIS: "skipped", E2E: "skipped"}, writes=[]),
    "token-unset": dict(
        env={"SYNC_TOKEN": ""}, vars={THIS: OLD, E2E: OLD}, reach=[THIS, E2E],
        exit=1, status={THIS: "failed", E2E: "failed"}, writes=[],
        reason="WING_COMMANDER_REFERENCE_IMAGE_SYNC_TOKEN"),
    "one-write-refused": dict(
        vars={THIS: OLD, E2E: OLD}, reach=[THIS, E2E], set_fail=[E2E],
        exit=1, status={THIS: "written", E2E: "failed"}, writes=[THIS],
        held={E2E: OLD}),
    "malformed-digest": dict(
        env={"DIGEST": "sha256:xyz"}, vars={THIS: OLD, E2E: OLD}, reach=[THIS, E2E],
        exit=1, status={THIS: "failed", E2E: "failed"}, writes=[], no_api=True),
    "empty-image": dict(
        env={"IMAGE": ""}, vars={THIS: OLD, E2E: OLD}, reach=[THIS, E2E],
        exit=1, status={THIS: "failed", E2E: "failed"}, writes=[], no_api=True),
    "probe-failed": dict(
        vars={THIS: OLD, E2E: OLD}, reach=[THIS, E2E], probe_fail=[E2E],
        exit=1, status={THIS: "failed", E2E: "failed"}, writes=[]),
    "over-reach": dict(
        vars={THIS: OLD, E2E: OLD}, reach=[THIS, E2E, "octo/extra"],
        exit=1, status={THIS: "failed", E2E: "failed"}, writes=[],
        reason="octo/extra"),
    "under-permission": dict(
        vars={THIS: OLD, E2E: OLD}, reach=[THIS],
        exit=1, status={THIS: "failed", E2E: "failed"}, writes=[]),
    "exact-reach-case-insensitive": dict(
        vars={THIS: OLD, E2E: OLD}, reach=["Octo/Wing", "OCTO/E2E"],
        exit=0, status={THIS: "written", E2E: "written"}, writes=[THIS, E2E]),
}


def run_case(name, case, tmp):
    stub_dir = os.path.join(tmp, "stub")
    bin_dir = os.path.join(tmp, "bin")
    os.makedirs(os.path.join(stub_dir, "vars"))
    os.makedirs(bin_dir)
    gh = os.path.join(bin_dir, "gh")
    shutil.copy(STUB, gh)
    os.chmod(gh, os.stat(gh).st_mode | stat.S_IXUSR)
    for repo, value in case.get("vars", {}).items():
        with open(os.path.join(stub_dir, "vars", repo.replace("/", "__")), "w") as f:
            f.write(value)
    for fname, items in (("reach", case.get("reach", [])),
                         ("runs", case.get("runs", [])),
                         ("probe_fail", case.get("probe_fail", [])),
                         ("set_fail", case.get("set_fail", []))):
        with open(os.path.join(stub_dir, fname), "w") as f:
            f.write("".join(f"{i}\n" for i in items))
    open(os.path.join(stub_dir, "log"), "w").close()
    outcome = os.path.join(tmp, "outcome.json")
    summary = os.path.join(tmp, "summary.md")
    env = {
        "PATH": bin_dir + os.pathsep + os.environ["PATH"],
        "STUB_DIR": stub_dir, "GH_TOKEN": AMBIENT, "SYNC_TOKEN": TOKEN,
        "IMAGE": IMAGE, "DIGEST": DIGEST, "THIS_REPO": THIS, "E2E_REPO": E2E,
        "CHECKS_PASSED": "true", "RUN_NUMBER": "7",
        "OUTCOME_FILE": outcome, "GITHUB_STEP_SUMMARY": summary,
        "HOME": tmp,
    }
    env.update(case.get("env", {}))
    proc = subprocess.run(["bash", SCRIPT], env=env, capture_output=True, text=True)
    with open(os.path.join(stub_dir, "log")) as f:
        log = f.read().splitlines()
    return proc, outcome, summary, log


def check_case(name, case):
    errs = []
    with tempfile.TemporaryDirectory() as tmp:
        proc, outcome, summary, log = run_case(name, case, tmp)
        if proc.returncode != case["exit"]:
            errs.append(f"exit {proc.returncode}, want {case['exit']} ({proc.stderr.strip()})")
        try:
            with open(outcome) as f:
                rows = json.load(f)
        except (OSError, ValueError) as e:
            return errs + [f"outcome file unreadable: {e}"]
        by_repo = {r["repo"]: r for r in rows}
        for repo, status in case["status"].items():
            got = by_repo.get(repo, {}).get("status")
            if got != status:
                errs.append(f"{repo}: status {got!r}, want {status!r}")
        for repo, held in case.get("held", {}).items():
            r = by_repo.get(repo, {})
            if r.get("held") != held or r.get("expected") != NEW:
                errs.append(f"{repo}: held/expected {r.get('held')!r}/{r.get('expected')!r}")
        if "reason" in case and not any(case["reason"] in r["reason"] for r in rows):
            errs.append(f"no reason names {case['reason']!r}")
        writes = []
        for line in log:
            if re.search(r"\bvariable\b", line):
                m = re.search(r"variable set (\S+) --repo (\S+)", line)
                if not m or m.group(1) != "WING_COMMANDER_CONTAINER_IMAGE":
                    errs.append(f"a gh variable call that is not the one write: {line}")
                else:
                    writes.append(m.group(2))
        for line in log:
            if line.startswith("REFUSED "):
                writes.remove(line.split()[1])
        if sorted(writes) != sorted(case["writes"]):
            errs.append(f"writes {writes}, want {case['writes']}")
        if case.get("no_api") and any(re.search(r"\bapi\b", line) for line in log):
            errs.append("a gh api call was made before validation/skip")
        for line in log:
            if "run list" in line and f"GH_TOKEN={AMBIENT} " not in line:
                errs.append("run list did not use the ambient workflow token")
        blob = proc.stdout + proc.stderr
        for path in (outcome, summary):
            if os.path.exists(path):
                with open(path) as f:
                    blob += f.read()
        if TOKEN in blob:
            errs.append("the token value appears in output, summary or outcome file")
    return errs


def job_block(text, job):
    m = re.search(rf"^  {re.escape(job)}:\n(.*?)(?=^  [A-Za-z0-9_-]+:\n|\Z)", text, re.S | re.M)
    return m.group(1) if m else None


def step_blocks(block):
    parts = re.split(r"^      - name: ", block, flags=re.M)[1:]
    return ["- name: " + p for p in parts]


def check_wiring():
    errs = []
    with open(WORKFLOW) as f:
        text = f.read()
    sync = job_block(text, "sync-pins")
    check = job_block(text, "startup-check")
    if sync is None or check is None:
        return ["sync-pins or startup-check job missing"]
    if not re.search(r"needs:\s*\[build-and-publish,\s*startup-check\]", sync):
        errs.append("sync-pins must need build-and-publish and startup-check")
    if not re.search(r"group:\s*reference-image-pin-sync\b", sync) or \
            not re.search(r"cancel-in-progress:\s*false", sync):
        errs.append("sync-pins needs its own non-cancelling concurrency group")
    if not re.search(r"passed:\s*\$\{\{\s*steps\.watch\.outputs\.passed\s*\}\}", check):
        errs.append("startup-check must expose the `passed` output")
    if "needs.startup-check.outputs.passed" not in sync:
        errs.append("sync-pins must read startup-check's passed output")
    steps = step_blocks(sync)
    holders = [s for s in steps if "WING_COMMANDER_REFERENCE_IMAGE_SYNC_TOKEN" in s]
    if len(holders) != 1 or "id: sync" not in holders[0] or \
            "sync-reference-image-pin.sh" not in holders[0]:
        errs.append("the token secret must be bound to the one sync step")
    for wf in glob.glob(os.path.join(GH_DIR, "workflows", "*.yml")):
        with open(wf) as f:
            body = f.read()
        n = len(re.findall(r"secrets\.WING_COMMANDER_REFERENCE_IMAGE_SYNC_TOKEN", body))
        want = 1 if os.path.abspath(wf) == os.path.abspath(WORKFLOW) else 0
        if n != want:
            errs.append(f"{os.path.basename(wf)} references the token secret {n} times, want {want}")
    guarded = [s for s in steps if "durable-failure-issue" in s and "operation: report" in s]
    if len(guarded) != 1 or "label: reference-image-sync:failed" not in guarded[0] or \
            "steps.sync.outcome == 'failure'" not in guarded[0]:
        errs.append("the report step must be guarded to the sync step's failure with the sync label")
    if not any("durable-failure-issue" in s and "operation: close" in s and
               "label: reference-image-sync:failed" in s for s in steps):
        errs.append("a successful sync must close the failure issue")
    if "issues: write" not in sync:
        errs.append("sync-pins needs issues: write")
    if not steps or "exit 1" not in steps[-1] or "steps.sync.outcome == 'failure'" not in steps[-1]:
        errs.append("the last sync-pins step must re-fail the job after a failed sync")
    return errs


def check_single_home():
    errs = []
    paths = glob.glob(os.path.join(GH_DIR, "workflows", "*.yml"))
    paths += [p for p in glob.glob(os.path.join(GH_DIR, "actions", "**", "*"), recursive=True)
              if os.path.isfile(p)]
    for p in paths:
        if os.path.abspath(p) == os.path.abspath(SCRIPT):
            continue
        with open(p, errors="replace") as f:
            body = f.read()
        rel = os.path.relpath(p, GH_DIR)
        if re.search(r"gh variable set\s+WING_COMMANDER_CONTAINER_IMAGE", body):
            errs.append(f"{rel} carries a copy of the pin write")
        if "sync-reference-image-pin" in body and \
                os.path.abspath(p) != os.path.abspath(WORKFLOW):
            errs.append(f"{rel} references the sync script; only the e2e reference-image workflow may")
    return errs


def main():
    failures = []
    for name, case in CASES.items():
        for e in check_case(name, case):
            failures.append(f"case {name}: {e}")
    failures += [f"wiring: {e}" for e in check_wiring()]
    failures += [f"single-home: {e}" for e in check_single_home()]
    if failures:
        for f in failures:
            print("FAIL " + f)
        print(f"FAIL  {len(failures)} problem(s)")
        return 1
    print(f"PASS  verify-reference-image-pin-sync.py ({len(CASES)} cases, wiring, single home)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
