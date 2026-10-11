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
2. Workflow wiring (wing-commander-e2e-reference-image.yml): startup-check
   dispatches and waits through wing-commander-dispatch-and-wait and its
   verdict step (run verbatim) passes only a found, successful run;
   sync-pins needs build-and-publish and startup-check, runs only after a
   passed check, serialises on its own concurrency group, the secret is bound to the one
   sync step, the failure steps are guarded to that step's failure, the
   issue is closed on success, and a last step re-fails the job.
3. Single home: every `gh variable set` in the e2e reference-image
   workflow is in the sync step (the FR-005 permission probe and the
   write), and no other workflow or composite
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

def run_jobs(check, sync_step, job="same"):
    """`gh run view --json jobs` for a run: startup-check concluded `check`,
    and sync-pins' sync step `sync_step` (None: not run yet). `job` is the
    sync-pins job's own conclusion: "same" as the step, None while it is
    still running, or a later step's failure."""
    sync_job = sync_step if job == "same" else job
    sync_steps = None if sync_step is None else [
        {"name": "Checkout", "conclusion": "success"},
        {"name": "Sync the reference-image pins", "conclusion": sync_step}]
    return {"jobs": [
        {"name": "build-and-publish", "conclusion": "success", "steps": []},
        {"name": "startup-check", "conclusion": check, "steps": []},
        {"name": "sync-pins", "conclusion": sync_job, "steps": sync_steps},
    ]}


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
        runs=[3, 99], jobs={99: run_jobs("success", "success")},
        vars={THIS: OLD, E2E: OLD}, reach=[THIS, E2E],
        exit=0, status={THIS: "skipped", E2E: "skipped"}, writes=[], reason="run 99"),
    # FR-010: a newer run still finishing (its sync-pins job not yet
    # concluded) whose check passed and whose sync step succeeded has moved
    # the pins; so has one whose sync-pins job failed in a later step.
    "superseded-newer-still-finishing": dict(
        runs=[8], jobs={8: run_jobs("success", "success", job=None)},
        vars={THIS: OLD, E2E: OLD}, reach=[THIS, E2E],
        exit=0, status={THIS: "skipped", E2E: "skipped"}, writes=[], reason="run 8"),
    "superseded-newer-close-failed": dict(
        runs=[8], jobs={8: run_jobs("success", "success", job="failure")},
        vars={THIS: OLD, E2E: OLD}, reach=[THIS, E2E],
        exit=0, status={THIS: "skipped", E2E: "skipped"}, writes=[], reason="run 8"),
    # A newer run whose check failed, or whose sync has not run yet (it
    # queues after this one and writes the newer digest last), does not stop
    # this write; the search stops at the first run that is not newer.
    "not-superseded": dict(
        runs=[5, 8, 9, 11],
        jobs={8: run_jobs("failure", "success"), 9: run_jobs("failure", "cancelled"),
              11: run_jobs("success", None, job=None),
              5: run_jobs("success", "success")},
        vars={THIS: OLD, E2E: OLD}, reach=[THIS, E2E],
        exit=0, status={THIS: "written", E2E: "written"}, writes=[THIS, E2E],
        never_viewed=[5]),
    # A newer run that passed its check but whose sync step failed (it may
    # have written part of its newer digest) or whose pending sync-pins was
    # cancelled: writing this older digest could roll the pins back.
    "newer-sync-failed": dict(
        runs=[8], jobs={8: run_jobs("success", "failure")},
        vars={THIS: OLD, E2E: OLD}, reach=[THIS, E2E],
        exit=1, status={THIS: "failed", E2E: "failed"}, writes=[],
        reason="re-run that run's sync-pins job"),
    "newer-sync-cancelled": dict(
        runs=[8], jobs={8: run_jobs("success", None, job="cancelled")},
        vars={THIS: OLD, E2E: OLD}, reach=[THIS, E2E],
        exit=1, status={THIS: "failed", E2E: "failed"}, writes=[],
        reason="newer run 8"),
    # A newer run re-run after it synced: attempt 2 has not decided yet,
    # attempt 1 synced.
    "superseded-by-earlier-attempt": dict(
        runs=[8], jobs={8: [run_jobs("success", "success"), run_jobs(None, None, job=None)]},
        vars={THIS: OLD, E2E: OLD}, reach=[THIS, E2E],
        exit=0, status={THIS: "skipped", E2E: "skipped"}, writes=[], reason="run 8"),
    # A newer run re-run after its sync failed: attempt 2 passed its check
    # and its sync is still pending, so it will write last; attempt 1's
    # failure no longer decides.
    "newer-rerun-pending": dict(
        runs=[8], jobs={8: [run_jobs("success", "failure"), run_jobs("success", None, job=None)]},
        vars={THIS: OLD, E2E: OLD}, reach=[THIS, E2E],
        exit=0, status={THIS: "written", E2E: "written"}, writes=[THIS, E2E]),
    # A newer run whose sync is still pending writes last, so no lower run
    # (here one whose pending sync was cancelled) is read at all.
    "newer-pending-shadows-lower": dict(
        runs=[8, 9], jobs={9: run_jobs("success", None, job=None),
                           8: run_jobs("success", None, job="cancelled")},
        vars={THIS: OLD, E2E: OLD}, reach=[THIS, E2E],
        exit=0, status={THIS: "written", E2E: "written"}, writes=[THIS, E2E],
        never_viewed=[8]),
    # A newer run re-run in full after its sync failed: attempt 2's check
    # is still running (gh reports an empty conclusion), so attempt 1's
    # failure no longer decides...
    "newer-rerun-check-running": dict(
        runs=[8], jobs={8: [run_jobs("success", "failure"), run_jobs("", None, job=None)]},
        vars={THIS: OLD, E2E: OLD}, reach=[THIS, E2E],
        exit=0, status={THIS: "written", E2E: "written"}, writes=[THIS, E2E]),
    "newer-rerun-check-null": dict(
        runs=[8], jobs={8: [run_jobs("success", "failure"), run_jobs(None, None, job=None)]},
        vars={THIS: OLD, E2E: OLD}, reach=[THIS, E2E],
        exit=0, status={THIS: "written", E2E: "written"}, writes=[THIS, E2E]),
    # ...but an older attempt's finished sync still supersedes.
    "newer-rerun-check-running-after-sync": dict(
        runs=[8], jobs={8: [run_jobs("success", "success"), run_jobs("", None, job=None)]},
        vars={THIS: OLD, E2E: OLD}, reach=[THIS, E2E],
        exit=0, status={THIS: "skipped", E2E: "skipped"}, writes=[], reason="run 8"),
    # A newer attempt whose check failed leaves the decision to older ones.
    "newer-rerun-check-failed": dict(
        runs=[8], jobs={8: [run_jobs("success", "failure"), run_jobs("failure", None, job="skipped")]},
        vars={THIS: OLD, E2E: OLD}, reach=[THIS, E2E],
        exit=1, status={THIS: "failed", E2E: "failed"}, writes=[], reason="newer run 8"),
    # A newer sync-pins that ended without a finished sync step (timed out,
    # lost its runner, step cancelled) may have written part of a newer
    # digest: fail closed rather than write over it.
    "newer-sync-timed-out": dict(
        runs=[8], jobs={8: run_jobs("success", "cancelled", job="failure")},
        vars={THIS: OLD, E2E: OLD}, reach=[THIS, E2E],
        exit=1, status={THIS: "failed", E2E: "failed"}, writes=[], reason="(failure)"),
    # A "re-run failed jobs" attempt that synced supersedes even when it
    # does not list the startup-check it did not re-run.
    "superseded-by-rerun-failed-jobs": dict(
        runs=[8], jobs={8: [run_jobs("success", "failure"),
                            {"jobs": [j for j in run_jobs("success", "success")["jobs"]
                                      if j["name"] == "sync-pins"]}]},
        vars={THIS: OLD, E2E: OLD}, reach=[THIS, E2E],
        exit=0, status={THIS: "skipped", E2E: "skipped"}, writes=[], reason="run 8"),
    # A "re-run failed jobs" attempt (no startup-check listed) whose sync
    # failed again: it ended, so it may have written part of a newer digest.
    "rerun-failed-jobs-sync-failed": dict(
        runs=[8], jobs={8: [run_jobs("success", "failure"),
                            {"jobs": [j for j in run_jobs("success", "failure")["jobs"]
                                      if j["name"] == "sync-pins"]}]},
        vars={THIS: OLD, E2E: OLD}, reach=[THIS, E2E],
        exit=1, status={THIS: "failed", E2E: "failed"}, writes=[], reason="newer run 8"),
    # A newer run cancelled before its check passed never synced: the
    # cancelled sync-pins it records does not block this write.
    "newer-cancelled-before-check": dict(
        runs=[8], jobs={8: run_jobs("cancelled", None, job="cancelled")},
        vars={THIS: OLD, E2E: OLD}, reach=[THIS, E2E],
        exit=0, status={THIS: "written", E2E: "written"}, writes=[THIS, E2E]),
    # A completed newer run that never created its sync-pins job (cancelled
    # before its dependents existed) is not pending: the scan reads on, and
    # the run below it whose sync failed after a possible write decides.
    "completed-run-without-sync-job": dict(
        runs=[8, 9], jobs={9: {"jobs": [{"name": "build-and-publish", "conclusion": "cancelled",
                                         "steps": []}]},
                           8: run_jobs("success", "failure")},
        status_override={9: "completed"},
        vars={THIS: OLD, E2E: OLD}, reach=[THIS, E2E],
        exit=1, status={THIS: "failed", E2E: "failed"}, writes=[], reason="newer run 8"),
    # A run-list row that does not parse fails closed.
    "run-list-malformed": dict(
        runs=[8], attempts_override={8: None},
        vars={THIS: OLD, E2E: OLD}, reach=[THIS, E2E],
        exit=1, status={THIS: "failed", E2E: "failed"}, writes=[]),
    "e2e-is-this-repo": dict(
        env={"E2E_REPO": "OCTO/Wing"}, vars={THIS: OLD}, reach=[THIS],
        exit=0, status={THIS: "written", "test repository": "skipped"}, writes=[THIS]),
    "run-view-error": dict(
        runs=[8],
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
    # FR-005: a token that can read but not write one repository's
    # variables changes nothing on either; the refusal is proven first.
    "write-permission-missing": dict(
        vars={THIS: OLD, E2E: OLD}, reach=[THIS, E2E], set_fail=[E2E],
        exit=1, status={THIS: "failed", E2E: "failed"}, writes=[],
        reason="cannot write WING_COMMANDER_CONTAINER_IMAGE on octo/e2e (HTTP 403); nothing was changed"),
    # A repository with no value yet is written first, so its refusal still
    # changes nothing anywhere.
    "absent-variable-refused": dict(
        vars={THIS: OLD}, reach=[THIS, E2E], set_fail=[E2E],
        exit=1, status={THIS: "failed", E2E: "failed"}, writes=[]),
    # A write refused after the probe passed: nothing after it is written.
    "write-refused-after-probe": dict(
        vars={THIS: OLD, E2E: OLD}, reach=[THIS, E2E], set_fail_expected=[THIS],
        exit=1, status={THIS: "failed", E2E: "failed"}, writes=[],
        held={THIS: OLD, E2E: OLD}, reason="not written: the write on octo/wing was refused"),
    "token-rejected": dict(
        reach_fail=True, vars={THIS: OLD, E2E: OLD}, reach=[THIS, E2E],
        exit=1, status={THIS: "failed", E2E: "failed"}, writes=[], reason="(HTTP 401)"),
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
          "absent-variable", "not-superseded", "hand-set-held-value", "newer-rerun-pending",
          "newer-pending-shadows-lower", "newer-rerun-check-running", "newer-rerun-check-null",
          "newer-cancelled-before-check"}


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
                         ("probe_fail", case.get("probe_fail", [])),
                         ("set_fail", case.get("set_fail", [])),
                         ("set_fail_expected", case.get("set_fail_expected", []))):
        with open(os.path.join(stub_dir, fname), "w") as f:
            f.write("".join(f"{i}\n" for i in items))
    # jobs: {run number: one jobs document, or a list of them per attempt}
    attempts = {n: (doc if isinstance(doc, list) else [doc])
                for n, doc in case.get("jobs", {}).items()}
    with open(os.path.join(stub_dir, "runs.json"), "w") as f:
        # A run is in progress while its newest attempt has a job with no
        # conclusion yet, unless the case says otherwise.
        def run_status(n):
            if n in case.get("status_override", {}):
                return case["status_override"][n]
            docs = attempts.get(n)
            if docs and any(j.get("conclusion") in (None, "") for j in docs[-1]["jobs"]):
                return "in_progress"
            return "completed"
        json.dump([{"number": n, "databaseId": 100 + n,
                    "attempt": case.get("attempts_override", {}).get(n, len(attempts.get(n, [1]))),
                    "status": run_status(n)}
                   for n in case.get("runs", [])], f)
    os.makedirs(os.path.join(stub_dir, "jobs"))
    for n, docs in attempts.items():
        for i, doc in enumerate(docs, 1):
            with open(os.path.join(stub_dir, "jobs", f"{100 + n}-{i}.json"), "w") as f:
                json.dump(doc, f)
    for flag in ("run_list_fail", "reach_fail"):
        if case.get(flag):
            open(os.path.join(stub_dir, flag), "w").close()
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
    final = {}
    for repo in (THIS, E2E):
        vf = os.path.join(stub_dir, "vars", repo.replace("/", "__"))
        final[repo] = open(vf).read() if os.path.exists(vf) else None
    return rc, output, outputs, outcome, table, summary, log, final


def check_case(name, case, bash, script):
    errs = []
    with tempfile.TemporaryDirectory() as tmp:
        rc, output, outputs, outcome, table, summary, log, final = run_case(name, case, tmp, bash, script)
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
        # Writes are judged by where the pins end up (the stub keeps what
        # was written), and every set call must be the one variable, written
        # with the new value or with the value that repository already held
        # (the FR-005 permission probe).
        initial = case.get("vars", {})
        writes = [r for r in (THIS, E2E) if final[r] == NEW and initial.get(r) != NEW]
        for r in (THIS, E2E):
            if final[r] not in (NEW, initial.get(r)):
                errs.append(f"{r} ends holding {final[r]!r}")
        for line in log:
            if re.search(r"\bvariable\b", line) and not line.startswith("REFUSED "):
                m = re.search(r"variable set (\S+) --repo (\S+) --body (.*)$", line)
                if not m or m.group(1) != "WING_COMMANDER_CONTAINER_IMAGE":
                    errs.append(f"a gh variable call that is not the one write: {line}")
                elif m.group(3) not in (NEW, initial.get(m.group(2))):
                    errs.append(f"a write of a value that is neither new nor held: {line}")
        if sorted(writes) != sorted(case["writes"]):
            errs.append(f"writes {writes}, want {case['writes']}")
        for n in case.get("never_viewed", []):
            if any(f"run view {100 + n} " in line for line in log):
                errs.append(f"run {n} is not newer and must not be read")
        if case.get("no_api") and any(re.search(r"\bapi\b", line) for line in log):
            errs.append("a gh api call was made before validation/skip")
        for line in log:
            if line.startswith("REFUSED "):
                continue
            if "run list" in line or "run view" in line:
                if not line.startswith(f"GH_TOKEN={AMBIENT} "):
                    errs.append("run list/view did not use the ambient workflow token")
                if "run list" in line and ("--branch main" not in line or "--limit 100" not in line):
                    errs.append("run list must read the last 100 default-branch runs")
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
VERDICT_STEP = "Record the start-up check verdict"


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


def check_verdict_step(bash):
    """startup-check dispatches and waits through the dispatch-and-wait
    single home (correlated by its attempt token, on this run's ref), and
    reports passed=true only for a found run that concluded success."""
    import yaml
    errs = []
    with open(WORKFLOW) as f:
        wf = yaml.safe_load(f)
    jobs = wf.get("jobs") or {}
    steps = (jobs.get("startup-check") or {}).get("steps") or []
    check = [st for st in steps if st.get("id") == "check"]
    if len(check) != 1 or check[0].get("uses") != "./.github/actions/wing-commander-dispatch-and-wait":
        return ["startup-check must dispatch and wait through wing-commander-dispatch-and-wait"]
    w = check[0].get("with") or {}
    if w.get("workflow-file") != "wing-commander-private-image-dogfood.yml":
        errs.append("the composite must dispatch wing-commander-private-image-dogfood.yml")
    if "needs.build-and-publish.outputs.digest" not in str(w.get("workflow-inputs")) or \
            "container-image" not in str(w.get("workflow-inputs")):
        errs.append("the dispatch must pass the published digest as container-image")
    if "github.run_id" not in str(w.get("attempt-token")):
        errs.append("the attempt-token must be this run's own id")
    if "github.ref_name" not in str(w.get("ref")):
        errs.append("the check must be dispatched on this run's own ref")
    if int(w.get("poll-interval-seconds", 0)) < 30:
        errs.append("poll-interval-seconds must be 30 or more (github.token rate limit)")
    if int(w.get("poll-interval-seconds", 0)) * int(w.get("wait-attempts", 0)) > 55 * 60:
        errs.append("the wait must end inside startup-check's 60-minute timeout")
    if not any(str(st.get("uses", "")).startswith("actions/checkout@") for st in steps[:steps.index(check[0])]):
        errs.append("startup-check must check out before using a local composite")
    sync_if = str((jobs.get("sync-pins") or {}).get("if"))
    if "needs.startup-check.outputs.passed == 'true'" not in sync_if:
        errs.append("sync-pins must run only after a passed check (a queued job is cancelled "
                    "by the next to queue in its concurrency group)")
    if "github.ref == format('refs/heads/{0}', github.event.repository.default_branch)" \
            not in sync_if:
        errs.append("sync-pins must run only for a default-branch build (a branch build "
                    "queued in the concurrency group cancels main's pending sync)")
    dogfood = os.path.join(GH_DIR, "workflows", "wing-commander-private-image-dogfood.yml")
    with open(dogfood) as f:
        df = f.read()
    if not re.search(r"^run-name:.*\{0\} \[attempt:\{1\}\]', inputs\.container-image, "
                     r"inputs\.attempt-token\)", df, re.M):
        errs.append("wing-commander-private-image-dogfood.yml's run-name must carry the "
                    "container-image and '[attempt:<attempt-token>]'")
    script = str(H.find_step(WORKFLOW, VERDICT_STEP).get("run") or "")
    for corr, concl, want in (("found", "success", "true"), ("found", "failure", None),
                              ("ambiguous", "", None), ("not-observed", "", None),
                              ("found", "timeout", None)):
        with tempfile.TemporaryDirectory() as tmp:
            work = os.path.join(tmp, "work")
            os.makedirs(work)
            env = {"CORRELATION": corr, "CONCLUSION": concl, "RUN_URL": "https://x/runs/1"}
            rc, out, outputs, summary = H.run_step(bash, script, work, env, tmp,
                                                   shell=H.step_shell(WORKFLOW, VERDICT_STEP))
        if outputs.get("passed") != want or (rc == 0) != (want == "true"):
            errs.append(f"verdict {corr}/{concl!r}: passed={outputs.get('passed')!r} rc={rc}")
        if want is None and "no `WING_COMMANDER_CONTAINER_IMAGE` pin was written" not in summary:
            errs.append(f"verdict {corr}/{concl!r}: the summary must say the sync was skipped")
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
    if n_step < 1 or n_wf != n_step:
        errs.append(f"the e2e reference-image workflow carries {n_wf} `gh variable set` "
                    f"call(s), {n_step} in the sync step; want every one in the sync step")
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
    failures += [f"startup-check: {e}" for e in check_verdict_step(bash)]
    if failures:
        for f in failures:
            print("FAIL " + f)
        print(f"FAIL  {len(failures)} problem(s)")
        return 1
    print(f"PASS  verify-reference-image-pin-sync.py ({len(CASES)} cases, wiring, single home)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
