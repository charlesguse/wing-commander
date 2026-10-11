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
1. Script behaviour: runs the sync-pins job's shipped `Sync the
   reference-image pins` run: block VERBATIM (wc_shell_harness, under the
   production shell) against a stubbed `gh`
   (tests/reference-image-pin-sync/gh-stub.sh) for each case below,
   asserting the exit code, each repository's status, the exact set of
   writes, which token every gh call ran under, and that the token value
   appears in no output. The block is inline rather than an _shared/
   script so Gate 12 can resolve each call's token.
2. Workflow wiring (wing-commander-e2e-reference-image.yml): sync-pins needs
   build-and-publish and startup-check, serialises on its own concurrency
   group, startup-check exposes `passed`, the secret is bound to the one
   sync step, the failure steps are guarded to that step's failure, the
   issue is closed on success, and a last step re-fails the job.
3. Single home: the e2e reference-image workflow carries exactly one
   `gh variable set`, in the sync step, and no other workflow or composite
   carries a write of the variable (auto-release.yml included).
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
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wc_shell_harness as H  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
GH_DIR = os.path.join(HERE, "..")
SYNC_STEP = "Sync the reference-image pins"
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
        runs=["3 3", "99 99"],
        jobs={"99": ["startup-check success", "sync-pins success"]},
        vars={THIS: OLD, E2E: OLD}, reach=[THIS, E2E],
        exit=0, status={THIS: "skipped", E2E: "skipped"}, writes=[], reason="run 99"),
    # FR-010: a newer run whose check passed and whose sync-pins has ended
    # (still finishing, or failed after a write it may have made) has moved
    # the pins; an older run must not move them back.
    "superseded-newer-still-finishing": dict(
        runs=["8 108"],
        jobs={"108": ["build-and-publish success", "startup-check success", "sync-pins success"]},
        vars={THIS: OLD, E2E: OLD}, reach=[THIS, E2E],
        exit=0, status={THIS: "skipped", E2E: "skipped"}, writes=[], reason="run 8"),
    "superseded-newer-sync-failed": dict(
        runs=["8 108"],
        jobs={"108": ["startup-check success", "sync-pins failure"]},
        vars={THIS: OLD, E2E: OLD}, reach=[THIS, E2E],
        exit=0, status={THIS: "skipped", E2E: "skipped"}, writes=[], reason="run 8"),
    # A newer run whose check failed, whose sync has not ended or was
    # cancelled, or an older run, does not supersede this one.
    "not-superseded": dict(
        runs=["8 108", "9 109", "10 110", "5 105"],
        jobs={"108": ["startup-check failure", "sync-pins success"],
              "109": ["startup-check success", "sync-pins null"],
              "110": ["startup-check success", "sync-pins cancelled"],
              "105": ["startup-check success", "sync-pins success"]},
        vars={THIS: OLD, E2E: OLD}, reach=[THIS, E2E],
        exit=0, status={THIS: "written", E2E: "written"}, writes=[THIS, E2E]),
    "run-view-error": dict(
        runs=["8 108"],
        vars={THIS: OLD, E2E: OLD}, reach=[THIS, E2E],
        exit=1, status={THIS: "failed", E2E: "failed"}, writes=[]),
    # A hand-set held value cannot break the table's columns.
    "hand-set-held-value": dict(
        vars={THIS: "a|b`c", E2E: OLD}, reach=[THIS, E2E],
        exit=0, status={THIS: "written", E2E: "written"}, writes=[THIS, E2E]),
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
    # A repository that has never held the variable: the probe's 404 is
    # "not set yet", and the write creates it.
    "absent-variable": dict(
        vars={E2E: OLD}, reach=[THIS, E2E],
        exit=0, status={THIS: "written", E2E: "written"}, writes=[THIS, E2E],
        held={THIS: ""}),
    # A rebuild dispatched on another branch is checked but never pinned.
    "branch-build": dict(
        env={"REF": "refs/heads/experiment"}, vars={THIS: OLD, E2E: OLD}, reach=[THIS, E2E],
        exit=0, status={THIS: "skipped", E2E: "skipped"}, writes=[], no_api=True,
        reason="not the default branch"),
    # The superseded guard fails closed: no run list, no write.
    "run-list-error": dict(
        run_list_fail=True, vars={THIS: OLD, E2E: OLD}, reach=[THIS, E2E],
        exit=1, status={THIS: "failed", E2E: "failed"}, writes=[]),
}

# Cases whose outcome may close the failure issue (every sync-set repository
# written or current); every other case must leave `synced` unset.
SYNCED = {"both-written", "all-current", "exact-reach-case-insensitive",
          "absent-variable", "not-superseded", "hand-set-held-value"}


def run_case(name, case, tmp, bash, script):
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
    os.makedirs(os.path.join(stub_dir, "jobs"))
    for rid, lines in case.get("jobs", {}).items():
        with open(os.path.join(stub_dir, "jobs", rid), "w") as f:
            f.write("".join(f"{l}\n" for l in lines))
    if case.get("run_list_fail"):
        open(os.path.join(stub_dir, "run_list_fail"), "w").close()
    open(os.path.join(stub_dir, "log"), "w").close()
    outcome = os.path.join(tmp, "outcome.json")
    table = os.path.join(tmp, "table.md")
    env = {
        "PATH": bin_dir + os.pathsep + os.environ["PATH"],
        "STUB_DIR": stub_dir, "GH_TOKEN": AMBIENT, "SYNC_TOKEN": TOKEN,
        "IMAGE": IMAGE, "DIGEST": DIGEST, "THIS_REPO": THIS, "E2E_REPO": E2E,
        "CHECKS_PASSED": "true", "RUN_NUMBER": "7",
        "OUTCOME_FILE": outcome, "TABLE_FILE": table, "HOME": tmp,
        "REF": "refs/heads/main", "DEFAULT_BRANCH": "main",
    }
    env.update(case.get("env", {}))
    workdir = os.path.join(tmp, "work")
    os.makedirs(workdir)
    rc, output, outputs, summary = H.run_step(
        bash, script, workdir, env, tmp, shell=H.step_shell(WORKFLOW, SYNC_STEP))
    with open(os.path.join(stub_dir, "log")) as f:
        log = f.read().splitlines()
    return rc, output, outputs, outcome, table, summary, log


def check_case(name, case, bash, script):
    errs = []
    with tempfile.TemporaryDirectory() as tmp:
        rc, output, outputs, outcome, table, summary, log = run_case(name, case, tmp, bash, script)
        if rc != case["exit"]:
            errs.append(f"exit {rc}, want {case['exit']} ({output.strip()})")
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
            if line.startswith("REFUSED "):
                continue
            if "run list" in line or "run view" in line:
                if not line.startswith(f"GH_TOKEN={AMBIENT} "):
                    errs.append("run list/view did not use the ambient workflow token")
                if "run list" in line and "--branch main" not in line:
                    errs.append("run list must count only default-branch runs as newer")
            elif not line.startswith(f"GH_TOKEN={TOKEN} "):
                errs.append(f"a sync call did not run under the sync token: {line}")
        blob = output + summary
        if os.path.exists(outcome):
            with open(outcome) as f:
                blob += f.read()
        want_synced = "true" if name in SYNCED else None
        if outputs.get("synced") != want_synced:
            errs.append(f"synced output {outputs.get('synced')!r}, want {want_synced!r}")
        if os.path.exists(table):
            with open(table) as f:
                tbl = f.read()
            if tbl not in summary or not tbl.startswith("| Repository |"):
                errs.append("the job summary must carry the one rendered TABLE_FILE")
            for row in tbl.splitlines():
                if len(re.findall(r"(?<!\\)\|", row)) != 6:
                    errs.append(f"table row does not have exactly 5 cells: {row!r}")
        else:
            errs.append("TABLE_FILE was not written")
        if TOKEN in blob:
            errs.append("the token value appears in output, summary or outcome file")
    return errs


BODY_STEP = "Build the failure issue body"
WATCH_STEP = "Wait for the start-up check verdict"


def check_body_step(bash):
    """The failure issue body reads the one table, and still says something
    when the sync step died before writing it."""
    errs = []
    script = str(H.find_step(WORKFLOW, BODY_STEP).get("run") or "")
    for have_table in (True, False):
        with tempfile.TemporaryDirectory() as tmp:
            table = os.path.join(tmp, "pin-sync-table.md")
            if have_table:
                with open(table, "w") as f:
                    f.write("| Repository | Status |\n|---|---|\n| `octo/wing` | failed |\n")
            work = os.path.join(tmp, "work")
            os.makedirs(work)
            env = {"TABLE_FILE": table, "GITHUB_SERVER_URL": "https://github.com",
                   "GITHUB_REPOSITORY": THIS, "GITHUB_RUN_ID": "1"}
            rc, out, _o, _s = H.run_step(bash, script, work, env, tmp,
                                         shell=H.step_shell(WORKFLOW, BODY_STEP))
            body_path = os.path.join(tmp, "pin-sync-failure-body.md")
            body = open(body_path).read() if os.path.exists(body_path) else ""
            if rc != 0:
                errs.append(f"body step exits {rc} (table present: {have_table}): {out.strip()}")
            if have_table and "`octo/wing` | failed" not in body:
                errs.append("body step must carry the rendered table")
            if not have_table and "ended before it recorded an outcome" not in body:
                errs.append("body step must say the sync died before recording outcomes")
    return errs


WATCH_STUB = r"""#!/usr/bin/env bash
echo "$*" >> "${STUB_DIR}/log"
case "${1:-} ${2:-}" in
  "run list")
    expr=""; prev=""
    for a in "$@"; do [ "$prev" = "--jq" ] && expr="$a"; prev="$a"; done
    jq -r "$expr" "${STUB_DIR}/runs.json"
    ;;
  "run watch") exit 0 ;;
  *) exit 2 ;;
esac
"""


def check_watch_step(bash):
    """The verdict wait watches the run dispatched for THIS image, never an
    earlier dogfood run in the same window, and polls at >= 30s."""
    errs = []
    script = str(H.find_step(WORKFLOW, WATCH_STEP).get("run") or "")
    mine = IMAGE + "@" + DIGEST
    runs = [
        {"databaseId": 11, "createdAt": "2026-01-01T00:00:01Z",
         "displayTitle": "Wing Commander · private-image-dogfood"},
        {"databaseId": 10, "createdAt": "2026-01-01T00:00:00Z",
         "displayTitle": "Wing Commander · private-image-dogfood · " + mine},
        {"databaseId": 12, "createdAt": "2026-01-01T00:00:02Z",
         "displayTitle": "Wing Commander · private-image-dogfood · " + OLD},
        {"databaseId": 13, "createdAt": "2026-01-01T00:00:03Z",
         "displayTitle": "Wing Commander · private-image-dogfood · " + mine},
    ]
    with tempfile.TemporaryDirectory() as tmp:
        stub_dir = os.path.join(tmp, "stub")
        bin_dir = os.path.join(tmp, "bin")
        os.makedirs(stub_dir)
        os.makedirs(bin_dir)
        with open(os.path.join(stub_dir, "runs.json"), "w") as f:
            json.dump(runs, f)
        open(os.path.join(stub_dir, "log"), "w").close()
        gh = os.path.join(bin_dir, "gh")
        with open(gh, "w", newline="\n") as f:
            f.write(WATCH_STUB)
        os.chmod(gh, os.stat(gh).st_mode | stat.S_IXUSR)
        work = os.path.join(tmp, "work")
        os.makedirs(work)
        env = {"PATH": bin_dir + os.pathsep + os.environ["PATH"], "STUB_DIR": stub_dir,
               "SINCE": "2026-01-01T00:00:00Z", "CHECKED_IMAGE": mine,
               "GITHUB_REF_NAME": "main", "GH_TOKEN": AMBIENT}
        rc, out, outputs, _s = H.run_step(bash, script, work, env, tmp,
                                          shell=H.step_shell(WORKFLOW, WATCH_STEP))
        with open(os.path.join(stub_dir, "log")) as f:
            log = f.read().splitlines()
    watched = [l for l in log if l.startswith("run watch")]
    listed = [l for l in log if l.startswith("run list")]
    for flag in ("--event workflow_dispatch", "--branch main",
                 "--created >=2026-01-01T00:00:00Z"):
        if not listed or flag not in listed[0]:
            errs.append(f"the verdict wait's run list must filter on {flag!r}")
    dispatch = str(H.find_step(WORKFLOW, "Dispatch the start-up check against the published digest")
                   .get("run") or "")
    if not re.search(r"since=\$\(date -u -d '-\d+ minutes?'", dispatch):
        errs.append("SINCE must be taken a margin early (runner and server clocks differ)")
    if outputs.get("passed") != "true":
        errs.append(f"watch step did not report passed=true ({out.strip()})")
    if len(watched) != 1 or not watched[0].startswith("run watch 13 "):
        errs.append(f"watch step must watch run 13 (the newest dispatched for this digest), "
                    f"watched {watched}")
    m = re.search(r"--interval\s+(\d+)", watched[0] if watched else "")
    if not m or int(m.group(1)) < 30:
        errs.append("gh run watch must poll at --interval 30 or more (github.token rate limit)")
    dogfood = os.path.join(GH_DIR, "workflows", "wing-commander-private-image-dogfood.yml")
    with open(dogfood) as f:
        df = f.read()
    if not re.search(r"^run-name:.*format\('Wing Commander · private-image-dogfood · \{0\}', "
                     r"inputs\.container-image\)", df, re.M):
        errs.append("wing-commander-private-image-dogfood.yml's run-name must end with "
                    "' · <container-image>' for the watch step to find its run")
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
            not holders[0].startswith(f"- name: {SYNC_STEP}\n"):
        errs.append("the token secret must be bound to the one sync step")
    sync_run = str(H.find_step(WORKFLOW, SYNC_STEP).get("run") or "")
    if re.search(r"^\s*(?:bash|sh|source|\.)\s+\S*\.sh\b", sync_run, re.M):
        errs.append("the sync step must carry its shell inline (Gate 12 cannot resolve "
                    "the token of a gh call inside a sourced or invoked script)")
    for wf in glob.glob(os.path.join(GH_DIR, "workflows", "*.yml")):
        with open(wf) as f:
            body = f.read()
        n = len(re.findall(r"secrets\.WING_COMMANDER_REFERENCE_IMAGE_SYNC_TOKEN", body))
        want = 1 if os.path.abspath(wf) == os.path.abspath(WORKFLOW) else 0
        if n != want:
            errs.append(f"{os.path.basename(wf)} references the token secret {n} times, want {want}")
    jq_row = r'"| `\(.repo'
    if text.count(jq_row) != 1:
        errs.append(f"the outcome table's row rendering appears {text.count(jq_row)} times; "
                    f"want once (finish() writes TABLE_FILE, every reader cats it)")
    guarded = [s for s in steps if "durable-failure-issue" in s and "operation: report" in s]
    if len(guarded) != 1 or "label: reference-image-sync:failed" not in guarded[0] or \
            "steps.sync.outcome == 'failure'" not in guarded[0]:
        errs.append("the report step must be guarded to the sync step's failure with the sync label")
    closers = [s for s in steps if "durable-failure-issue" in s and "operation: close" in s
               and "label: reference-image-sync:failed" in s]
    if len(closers) != 1:
        errs.append("a successful sync must close the failure issue")
    elif "steps.sync.outputs.synced == 'true'" not in closers[0]:
        errs.append("the close step must be gated on synced == 'true' (a skipped sync is "
                    "not a fixed one)")
    if "issues: write" not in sync:
        errs.append("sync-pins needs issues: write")
    if not steps or "exit 1" not in steps[-1] or "steps.sync.outcome == 'failure'" not in steps[-1]:
        errs.append("the last sync-pins step must re-fail the job after a failed sync")
    return errs


def check_single_home():
    errs = []
    sync_run = str(H.find_step(WORKFLOW, SYNC_STEP).get("run") or "")
    with open(WORKFLOW) as f:
        wf_body = f.read()
    n_wf = len(re.findall(r"\bgh variable set\b", wf_body))
    n_step = len(re.findall(r"\bgh variable set\b", sync_run))
    if n_step != 1 or n_wf != 1:
        errs.append(f"the e2e reference-image workflow carries {n_wf} `gh variable set` "
                    f"call(s), {n_step} in the sync step; want exactly one, in the sync step")
    paths = glob.glob(os.path.join(GH_DIR, "workflows", "*.yml"))
    paths += [p for p in glob.glob(os.path.join(GH_DIR, "actions", "**", "*"), recursive=True)
              if os.path.isfile(p)]
    for p in paths:
        if os.path.abspath(p) == os.path.abspath(WORKFLOW):
            continue
        with open(p, errors="replace") as f:
            body = f.read()
        rel = os.path.relpath(p, GH_DIR)
        if pin_write_copies(body):
            errs.append(f"{rel} carries a copy of the pin write")
    return errs


PIN = "WING_COMMANDER_CONTAINER_IMAGE"


def pin_write_copies(body):
    """Ways a file can write the pin: `gh variable set` naming it directly or
    through a shell variable assigned it, or a PATCH/POST on its variables
    endpoint. A file that merely mentions the name writes nothing."""
    hits = re.findall(rf"\bgh\s+variable\s+set\s+[\"']?{PIN}\b", body)
    for var in re.findall(rf"\b(\w+)=[\"']?{PIN}\b", body):
        hits += re.findall(rf"\bgh\s+variable\s+set\s+[\"']?\$\{{?{var}\b", body)
    for line in body.splitlines():
        if re.search(rf"actions/variables(?:/{PIN}\b|\b)", line) and PIN in line and \
                re.search(r"(?:-X|--method)\s+[\"']?(?:PATCH|POST)\b", line):
            hits.append(line)
    return hits


def check_pin_write_detector():
    errs = []
    samples = {
        f"gh variable set {PIN} --body x": True,
        f'VAR={PIN}\ngh variable set "$VAR" --repo r --body x': True,
        f"gh api -X PATCH repos/o/r/actions/variables/{PIN} -f value=x": True,
        f"# reads {PIN}\ngh variable set WING_COMMANDER_AUTO_RELEASE_PAUSED --body true": False,
        f"gh api repos/o/r/actions/variables/{PIN} --jq .value": False,
    }
    for text, want in samples.items():
        if bool(pin_write_copies(text)) != want:
            errs.append(f"pin-write detector {'missed' if want else 'false-positive on'}: {text!r}")
    return errs


def main():
    H.use_utf8_stdout()
    H.ensure_jq()
    bash = H.resolve_bash()
    script = str(H.find_step(WORKFLOW, SYNC_STEP).get("run") or "")
    failures = []
    for name, case in CASES.items():
        for e in check_case(name, case, bash, script):
            failures.append(f"case {name}: {e}")
    failures += [f"wiring: {e}" for e in check_wiring()]
    failures += [f"single-home: {e}" for e in check_single_home()]
    failures += [f"single-home detector: {e}" for e in check_pin_write_detector()]
    failures += [f"body step: {e}" for e in check_body_step(bash)]
    failures += [f"watch step: {e}" for e in check_watch_step(bash)]
    if failures:
        for f in failures:
            print("FAIL " + f)
        print(f"FAIL  {len(failures)} problem(s)")
        return 1
    print(f"PASS  verify-reference-image-pin-sync.py ({len(CASES)} cases, wiring, single home)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
