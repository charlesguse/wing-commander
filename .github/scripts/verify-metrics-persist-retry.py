#!/usr/bin/env python3
"""Gate 41 — the metrics persistence append-with-retry algorithm survives a
concurrent writer and fails loudly under sustained contention
(specs/043-durable-metrics-record, research.md R7/R8).

WHY THIS EXISTS
---------------
The original version of this gate was a standalone reimplementation of the
algorithm's SHAPE (fetch, diff, commit, push, retry) rather than an
extraction of the shipped `run:` block — the same drift risk gate 5 exists
to close for the denied-tool collector. It also had no fixture where the
FIRST push attempt fails: every scenario that raced a concurrent writer did
so against an already-created branch. Both gaps let a real defect (PR #267
review, MF-B3) ship past 16 green checks: on a failed create-push, the
composite's separate up-front "Create destination branch" step left the
batch already written into the working tree, so the very next fetch/diff in
the retry loop read its own unpushed file as "already persisted" and
reported success with zero records actually pushed — for both a genuinely
failed create AND, more subtly, a merely-raced-but-eventually-successful one
(persisted-count=0 either way).

This runs the SHIPPED "Append records with retry" `run:` block (same
extraction technique as gate 43/44's harnesses — no copied logic to drift
out of sync) against real local bare git repositories, so branch creation
and append share one code path under test exactly as they do in production.

WHY THE VALIDATE STEP IS UNDER TEST TOO
---------------------------------------
Every case above feeds the append step a hand-written, already one-line
batch. Production feeds it the batch the SHIPPED "Validate records and
build the new-records batch" step wrote — and for the first two weeks that
step never produced a batch the append step could read. Persist runs
34562607603 and 34287169782 died in the append step with

    jq: parse error: Unfinished JSON term at EOF at line 1, column 1

(exit 5), and origin/metrics:records.jsonl stayed at 0 bytes after its
init commit. The chain: wing-commander-metrics-summary writes its record
pretty-printed; the validate step re-serialised it to one line ONLY on
the branch that resolved a numeric job_id, and that lookup matched
`.name == $job_key` exactly — but every stage job here is a reusable-
workflow job, which the jobs API names `<caller job> / <callee job>`
(`watchdog / diagnose`), while the record carries `github.job`
(`diagnose`). The lookup missed every time, the 52-line record went into
the JSONL batch verbatim, and the append step's per-line jq read `{` as
a whole record. case_validate_then_append_persists_reusable_workflow_
records runs both shipped steps back to back on a pretty-printed record
with a `watchdog / diagnose`-style job name (plus a multi-model one), so
a batch the append step cannot read fails here, not on the metrics branch.
"""
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_shell_harness import (  # noqa: E402
    ensure_jq, find_step, resolve_bash, run_step, use_utf8_stdout)

ACTION = ".github/actions/wing-commander-metrics-persist/action.yml"
STEP_NAME = "Append records with retry"
VALIDATE_STEP_NAME = "Validate records and build the new-records batch"
SCRIPT = find_step(ACTION, STEP_NAME)["run"]
VALIDATE_SCRIPT = find_step(ACTION, VALIDATE_STEP_NAME)["run"]
BASH = None
DEST_PATH = "records.jsonl"
# Gate 39's multi-model positive fixture, read (never copied) so the two
# gates cannot disagree on what a valid multi-model record looks like.
# Gate 39 pins that directory's file count, so nothing is added there.
MULTI_MODEL_FIXTURE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "fixtures", "metrics-record-schema", "valid-multi-model-sums-correct.json")

failures = []


def fail(case, msg):
    failures.append(f"{case}: {msg}")
    print(f"::error file={ACTION}::{case}: {msg}")


def note(msg):
    print(f"note: {msg}")


def _git(*args, cwd=None, check=True):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True,
                           text=True, encoding="utf-8", errors="replace",
                           check=check)


def new_bare_repo(tmp, name):
    path = os.path.join(tmp, name)
    _git("init", "-q", "--bare", path)
    return path


def new_clone(tmp, origin, name):
    path = os.path.join(tmp, name)
    _git("clone", "-q", origin, path)
    return path


def seed_branch(tmp, origin, branch, records_jsonl):
    """Land BRANCH's first commit directly, bypassing the script under
    test — mirrors research.md R8, but is not this gate's subject, so
    scenarios needing a pre-existing branch set it up out of band."""
    work = new_clone(tmp, origin, f"seed-{branch}")
    _git("checkout", "-q", "--orphan", branch, cwd=work)
    with open(os.path.join(work, DEST_PATH), "w", encoding="utf-8") as f:
        f.write(records_jsonl)
    _git("add", DEST_PATH, cwd=work)
    _git("-c", "user.name=test", "-c", "user.email=test@example.com",
         "commit", "-q", "-m", "seed", cwd=work)
    _git("push", "-q", "origin", f"HEAD:refs/heads/{branch}", cwd=work)
    shutil.rmtree(work, ignore_errors=True)


def run_append(tmp, origin, branch, batch_records, run_id, label):
    """Execute the shipped step once; return (rc, output, outputs, workdir)."""
    work = new_clone(tmp, origin, f"{label}-work")
    runner_temp = os.path.join(tmp, f"{label}-runnertemp")
    wc_dir = os.path.join(runner_temp, "wc-metrics-persist")
    os.makedirs(wc_dir, exist_ok=True)
    with open(os.path.join(wc_dir, "new-records.jsonl"), "w", encoding="utf-8") as f:
        f.write(batch_records)
    env = {"BRANCH": branch, "DEST_PATH": DEST_PATH, "RUN_ID": run_id,
           "GH_TOKEN": "stub-token"}
    rc, output, outputs, _summary = run_step(BASH, SCRIPT, work, env, runner_temp)
    return rc, output, outputs, work


def fetch_dest(tmp, origin, branch, name):
    work = new_clone(tmp, origin, name)
    try:
        _git("checkout", "-q", branch, cwd=work)
    except subprocess.CalledProcessError:
        # A missing destination branch is a scenario OUTCOME to assert on,
        # not a harness crash - a traceback here aborted the remaining
        # cases and made the red verdict illegible (PR #267 re-review).
        return None, work
    path = os.path.join(work, DEST_PATH)
    text = open(path, encoding="utf-8").read() if os.path.exists(path) else None
    return text, work


def _write_exec(path, content):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
    os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


REJECT_ALWAYS_HOOK = """#!/bin/sh
echo "rejected by fixture: simulating sustained contention" >&2
exit 1
"""


def install_hook(origin, content):
    hooks_dir = os.path.join(origin, "hooks")
    os.makedirs(hooks_dir, exist_ok=True)
    _write_exec(os.path.join(hooks_dir, "pre-receive"), content)


def case_zero_artifact_batch_against_existing_branch_is_zero_failure():
    case = "zero-artifact batch against an existing branch"
    tmp = tempfile.mkdtemp(prefix="wc-metrics-retry-")
    try:
        origin = new_bare_repo(tmp, "origin.git")
        seed_branch(tmp, origin, "metrics", "")

        rc, output, outputs, _work = run_append(tmp, origin, "metrics", "", "1000", "a")
        if rc != 0:
            fail(case, f"exited {rc}: {output.strip()[:300]}")
            return
        if outputs.get("persisted-count") != "0":
            fail(case, f"expected persisted-count=0, got {outputs.get('persisted-count')!r}")
        if outputs.get("unpersisted-record-keys", "") != "":
            fail(case, f"expected no unpersisted keys, got {outputs.get('unpersisted-record-keys')!r}")

        text, work = fetch_dest(tmp, origin, "metrics", "b")
        if text != "":
            fail(case, f"destination file changed after a zero-artifact run: {text!r}")
        shutil.rmtree(work, ignore_errors=True)
        note("a zero-artifact batch against an already-existing branch persisted nothing and reported success")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def case_first_write_creates_missing_destination_branch():
    case = "first write creates the missing destination branch"
    tmp = tempfile.mkdtemp(prefix="wc-metrics-retry-")
    try:
        origin = new_bare_repo(tmp, "origin.git")
        if _git("ls-remote", "--exit-code", origin, "refs/heads/metrics",
                cwd=None, check=False).returncode == 0:
            fail(case, "the destination branch already exists before the first write")
            return

        batch = '{"run":{"record_key":"run-first:cycle:0"},"cost_usd":5}\n'
        rc, output, outputs, _work = run_append(tmp, origin, "metrics", batch, "2000", "a")
        if rc != 0:
            fail(case, f"exited {rc}: {output.strip()[:300]}")
            return
        if outputs.get("persisted-count") != "1":
            fail(case, "a successful first write must report the record(s) it just "
                       f"persisted, not zero — got persisted-count={outputs.get('persisted-count')!r} "
                       "(incident PR #267 MF-B3)")

        text, work = fetch_dest(tmp, origin, "metrics", "b")
        if text is None or "run-first:cycle:0" not in text:
            fail(case, f"the first record is missing from the newly created destination: {text!r}")
        shutil.rmtree(work, ignore_errors=True)
        note("a first write onto a missing branch created it and correctly reported its own persisted-count")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def case_transient_first_push_failure_with_no_concurrent_writer_recovers():
    # A narrower MF-B3 regression than the concurrent-writer fixture below:
    # the first push to a not-yet-existing branch fails for a reason with
    # NO side effect on origin (a transient network blip, not a rival
    # writer) — so origin still has no such ref when this attempt retries.
    # That is exactly the case the concurrent-writer fixture cannot cover,
    # because there origin/BRANCH exists on retry and `checkout -B` self-
    # heals regardless of whether stale local state was cleaned up. Here,
    # with origin still empty, a naive retry re-attempting
    # `git checkout --orphan "$BRANCH"` fails outright (the branch already
    # exists LOCALLY from attempt 1) and falls through to reusing that
    # stale, already-committed local branch — whose existing_keys diff then
    # sees the whole batch as already present, appends nothing new, and
    # (without the fix) can still push successfully while reporting
    # persisted-count=0 for a run that had one record to persist.
    case = "transient first push failure with no concurrent writer recovers"
    tmp = tempfile.mkdtemp(prefix="wc-metrics-retry-")
    try:
        origin = new_bare_repo(tmp, "origin.git")

        real_git = shutil.which("git")
        state_file = os.path.join(tmp, "wrapper-fired")
        stub_dir = os.path.join(tmp, "stubbin")
        os.makedirs(stub_dir, exist_ok=True)
        wrapper = f"""#!/bin/sh
if [ "$1" = "push" ] && [ ! -f "{state_file}" ]; then
  touch "{state_file}"
  exit 1
fi
exec "{real_git}" "$@"
"""
        _write_exec(os.path.join(stub_dir, "git"), wrapper)

        batch = '{"run":{"record_key":"run-solo:cycle:0"},"cost_usd":4}\n'
        work = new_clone(tmp, origin, "a-work")
        runner_temp = os.path.join(tmp, "a-runnertemp")
        wc_dir = os.path.join(runner_temp, "wc-metrics-persist")
        os.makedirs(wc_dir, exist_ok=True)
        with open(os.path.join(wc_dir, "new-records.jsonl"), "w", encoding="utf-8") as f:
            f.write(batch)
        env = {"BRANCH": "metrics", "DEST_PATH": DEST_PATH, "RUN_ID": "3500",
               "GH_TOKEN": "stub-token",
               "PATH": stub_dir + os.pathsep + os.environ.get("PATH", "")}
        rc, output, outputs, _summary = run_step(BASH, SCRIPT, work, env, runner_temp)
        shutil.rmtree(work, ignore_errors=True)

        if rc != 0:
            fail(case, f"exited {rc}: {output.strip()[:500]}")
            return
        if not os.path.exists(state_file):
            fail(case, "the fixture wrapper never fired — this scenario proves nothing "
                       "about recovering from a transient first-push failure")
        if outputs.get("persisted-count") != "1":
            fail(case, "a transient first-push failure recovered by retry must still "
                       f"report its record as persisted, not zero — got "
                       f"persisted-count={outputs.get('persisted-count')!r} "
                       "(incident PR #267 MF-B3)")

        text, final_work = fetch_dest(tmp, origin, "metrics", "final")
        if text is None or "run-solo:cycle:0" not in text:
            fail(case, f"the record is missing from the destination after recovery: {text!r}")
        shutil.rmtree(final_work, ignore_errors=True)
        note("a transient first-push failure with no concurrent writer recovered on "
             "retry and correctly reported its own persisted-count")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def case_first_push_rejected_by_concurrent_writer_recovers_without_loss():
    # MF-F1 / MF-B3's core regression fixture: the FIRST push attempt fails
    # because a concurrent writer's commit lands on the destination branch
    # between this run's fetch and its push — during branch CREATION, the
    # exact shape MF-B3 broke (the create step's failed/raced push left a
    # pre-loaded working tree that made the next diff see the batch as
    # already persisted). A `git` wrapper on PATH injects that concurrent
    # commit the instant this run first calls `git push` (a real, separate
    # push to origin — not nested inside a pre-receive hook, which git's
    # own quarantine forbids from touching refs while another push is being
    # processed) so the shipped push is rejected by ordinary non-fast-
    # forward semantics, no custom rejection logic required. The retry loop
    # must then recover BOTH writers' records with zero loss and report
    # only its own count.
    case = "first push rejected by a concurrent writer recovers without loss"
    tmp = tempfile.mkdtemp(prefix="wc-metrics-retry-")
    try:
        origin = new_bare_repo(tmp, "origin.git")

        b_clone = new_clone(tmp, origin, "writer-b")
        _git("checkout", "-q", "--orphan", "metrics", cwd=b_clone)
        with open(os.path.join(b_clone, DEST_PATH), "w", encoding="utf-8") as f:
            f.write('{"run":{"record_key":"run-B:cycle:0"},"cost_usd":9}\n')
        _git("add", DEST_PATH, cwd=b_clone)
        _git("-c", "user.name=test", "-c", "user.email=test@example.com",
             "commit", "-q", "-m", "writer B", cwd=b_clone)

        real_git = shutil.which("git")
        state_file = os.path.join(tmp, "wrapper-fired")
        stub_dir = os.path.join(tmp, "stubbin")
        os.makedirs(stub_dir, exist_ok=True)
        wrapper = f"""#!/bin/sh
if [ "$1" = "push" ] && [ ! -f "{state_file}" ]; then
  touch "{state_file}"
  "{real_git}" -C "{b_clone}" push -q "{origin}" "HEAD:refs/heads/metrics" >/dev/null 2>&1
fi
exec "{real_git}" "$@"
"""
        _write_exec(os.path.join(stub_dir, "git"), wrapper)

        batch = '{"run":{"record_key":"run-A:cycle:0"},"cost_usd":2}\n'
        work = new_clone(tmp, origin, "a-work")
        runner_temp = os.path.join(tmp, "a-runnertemp")
        wc_dir = os.path.join(runner_temp, "wc-metrics-persist")
        os.makedirs(wc_dir, exist_ok=True)
        with open(os.path.join(wc_dir, "new-records.jsonl"), "w", encoding="utf-8") as f:
            f.write(batch)
        env = {"BRANCH": "metrics", "DEST_PATH": DEST_PATH, "RUN_ID": "3000",
               "GH_TOKEN": "stub-token",
               "PATH": stub_dir + os.pathsep + os.environ.get("PATH", "")}
        rc, output, outputs, _summary = run_step(BASH, SCRIPT, work, env, runner_temp)
        shutil.rmtree(work, ignore_errors=True)

        if rc != 0:
            fail(case, f"exited {rc}: {output.strip()[:500]}")
            return
        if not os.path.exists(state_file):
            fail(case, "the fixture wrapper never fired — this scenario proves nothing "
                       "about recovering from a rejected first push")
        if outputs.get("persisted-count") != "1":
            fail(case, "this run's own persisted-count must count only the record it "
                       f"pushed, not zero and not the concurrent writer's — got "
                       f"{outputs.get('persisted-count')!r}")

        text, final_work = fetch_dest(tmp, origin, "metrics", "final")
        if text is None or "run-A:cycle:0" not in text:
            fail(case, f"writer A's own record is missing after recovery: {text!r}")
        if text is None or "run-B:cycle:0" not in text:
            fail(case, f"the concurrent writer's record was lost: {text!r}")
        shutil.rmtree(final_work, ignore_errors=True)
        note("a first push rejected by a genuine concurrent writer recovered both "
             "records with zero loss and reported only its own persisted-count")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def case_sustained_contention_fails_loudly_naming_the_key():
    case = "sustained contention fails loudly, naming the key"
    tmp = tempfile.mkdtemp(prefix="wc-metrics-retry-")
    try:
        origin = new_bare_repo(tmp, "origin.git")
        seed_branch(tmp, origin, "metrics", "")
        install_hook(origin, REJECT_ALWAYS_HOOK)

        batch = '{"run":{"record_key":"run-victim:cycle:0"},"cost_usd":3}\n'
        rc, output, outputs, _work = run_append(tmp, origin, "metrics", batch, "4000", "a")

        if rc == 0:
            fail(case, "exhausted retry against a hook that rejects every push must "
                       "fail, not exit 0")
            return
        if outputs.get("unpersisted-record-keys", "").strip() != "run-victim:cycle:0":
            fail(case, "exhausted retry must name the specific unwritten record_key — "
                       f"got {outputs.get('unpersisted-record-keys')!r}")
        if outputs.get("persisted-count") != "0":
            fail(case, f"expected persisted-count=0 on total exhaustion, got {outputs.get('persisted-count')!r}")
        if "::error::" not in output:
            fail(case, "exhausted retry must surface an ::error:: annotation")
        note("exhausted retry under 100% contention failed loudly and named the unwritten key")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def case_idempotent_repeat_persistence_is_byte_for_byte_unchanged():
    case = "idempotent repeat persistence is byte-for-byte unchanged"
    tmp = tempfile.mkdtemp(prefix="wc-metrics-retry-")
    try:
        origin = new_bare_repo(tmp, "origin.git")
        batch = '{"run":{"record_key":"run-idem:cycle:0"},"cost_usd":7}\n'

        rc1, out1, outputs1, work1 = run_append(tmp, origin, "metrics", batch, "5000", "a")
        if rc1 != 0:
            fail(case, f"first run exited {rc1}: {out1.strip()[:300]}")
            return
        shutil.rmtree(work1, ignore_errors=True)

        before_text, before_work = fetch_dest(tmp, origin, "metrics", "before")
        shutil.rmtree(before_work, ignore_errors=True)

        rc2, out2, outputs2, work2 = run_append(tmp, origin, "metrics", batch, "5000", "b")
        shutil.rmtree(work2, ignore_errors=True)
        if rc2 != 0:
            fail(case, f"second (repeat) run exited {rc2}: {out2.strip()[:300]}")
            return
        if outputs2.get("persisted-count") != "0":
            fail(case, "repeat persistence of an already-present record must report "
                       f"zero newly persisted, got {outputs2.get('persisted-count')!r}")

        after_text, after_work = fetch_dest(tmp, origin, "metrics", "after")
        shutil.rmtree(after_work, ignore_errors=True)
        if before_text != after_text:
            fail(case, "the destination store changed after a repeat run over an "
                       "already-persisted record_key — not byte-for-byte unchanged")
        note("a repeat run over an already-persisted record_key left the store byte-for-byte unchanged")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _reusable_workflow_record(run_id, job_key, step_index=0):
    """A schema-version-1 record exactly as wing-commander-metrics-summary
    emits it for a reusable-workflow job: job_id null, record_key in its
    emission-time run_id:job_key:step_index form. Shape mirrors the
    metrics-record-diagnose artifact of run 34562449781."""
    return {
        "schema_version": 1, "record_available": True,
        "run": {"workflow_run_id": run_id, "job_key": job_key,
                "job_id": None, "step_index": step_index,
                "record_key": f"{run_id}:{job_key}:{step_index}"},
        "stage": "watchdog", "stage_available": True, "run_label": job_key,
        "spec": {"spec_dir": None, "issue": None, "identity_available": False},
        "model": "claude-opus-5", "model_available": True,
        "turns": {"counted": 2, "reported": 4, "intended_budget": 30,
                  "enforced_ceiling": 75, "available": True},
        "tokens": {"input": 4, "output": 663, "cache_read": 21730,
                   "cache_creation": 21978, "available": True},
        "cost_usd": 0.24724, "cost_available": True,
        "duration_ms": 58418, "duration_available": True,
        "outcome": "healthy",
        "per_model": [{"model": "claude-opus-5", "input_tokens": 4,
                       "output_tokens": 663, "cache_read_tokens": 21730,
                       "cache_creation_tokens": 21978, "cost_usd": 0.24724}],
        "per_model_available": True,
        "emitted_at": "2026-09-11T04:32:29Z",
    }


def _write_pretty(path, record):
    # indent=2, deliberately: the emitter writes its record pretty-printed
    # (`jq -n` without -c), and a compact fixture here would pass against
    # the exact validate step that shipped broken.
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(record, f, indent=2)
        f.write("\n")


def case_validate_then_append_persists_reusable_workflow_records():
    # The production path end to end (see the module docstring): the shipped
    # validate step reads pretty-printed artifacts and a jobs listing whose
    # names carry the reusable-workflow `<caller> / <callee>` prefix, then
    # the shipped append step reads the batch validate wrote.
    case = "validate then append persists reusable-workflow records"
    tmp = tempfile.mkdtemp(prefix="wc-metrics-retry-")
    try:
        origin = new_bare_repo(tmp, "origin.git")
        seed_branch(tmp, origin, "metrics", "")

        run_id = "34562449781"
        diagnose_job_id = 103147908588
        work = new_clone(tmp, origin, "a-work")
        runner_temp = os.path.join(tmp, "a-runnertemp")
        wc_dir = os.path.join(runner_temp, "wc-metrics-persist")
        dl_dir = os.path.join(wc_dir, "downloaded")
        for name in ("metrics-record-diagnose", "metrics-record-act",
                     "metrics-record-collect"):
            os.makedirs(os.path.join(dl_dir, name), exist_ok=True)
        # The jobs listing exactly as the discover step stores it: an array
        # of the jobs API's objects, named the way GitHub displays reusable-
        # workflow jobs. No job is named bare "diagnose". Two callers share
        # the "collect" suffix, so that job_key is ambiguous.
        with open(os.path.join(wc_dir, "jobs.json"), "w", encoding="utf-8") as f:
            json.dump([
                {"id": 103147788791, "name": "resolve"},
                {"id": 103147821739, "name": "watchdog / collect"},
                {"id": 103147821740, "name": "watchdog-self / collect"},
                {"id": diagnose_job_id, "name": "watchdog / diagnose"},
                {"id": 103148182551, "name": "watchdog / act"},
            ], f)
        _write_pretty(os.path.join(dl_dir, "metrics-record-diagnose",
                                   "wing-commander-metrics-record.json"),
                      _reusable_workflow_record(run_id, "diagnose"))
        # An ambiguous suffix must keep job_id null and the emission-time
        # record_key — never guess one of the two ids — and still persist.
        _write_pretty(os.path.join(dl_dir, "metrics-record-collect",
                                   "wing-commander-metrics-record.json"),
                      _reusable_workflow_record(run_id, "collect"))
        # A multi-model record whose per_model entries sum to its own
        # totals must pass validation, not be rejected with a warning
        # (persist run 34311334476's shape once the emitter sums correctly).
        with open(MULTI_MODEL_FIXTURE, encoding="utf-8") as f:
            multi = json.load(f)
        multi["run"] = {"workflow_run_id": run_id, "job_key": "act",
                        "job_id": None, "step_index": 0,
                        "record_key": f"{run_id}:act:0"}
        _write_pretty(os.path.join(dl_dir, "metrics-record-act",
                                   "wing-commander-metrics-record.json"), multi)

        rc, output, outputs, _summary = run_step(
            BASH, VALIDATE_SCRIPT, work, {"RUN_ID": run_id}, runner_temp)
        if rc != 0:
            fail(case, f"validate step exited {rc}: {output.strip()[:500]}")
            return
        if outputs.get("rejected", "").strip():
            fail(case, "validate rejected a well-formed record: "
                       f"{outputs.get('rejected')!r} — a multi-model record "
                       "whose per_model sums to its own totals must persist")
        batch_path = os.path.join(wc_dir, "new-records.jsonl")
        with open(batch_path, encoding="utf-8") as f:
            batch_lines = [line for line in f.read().split("\n") if line.strip()]
        if len(batch_lines) != 3:
            fail(case, "the batch must hold exactly one line per record "
                       f"(JSONL), got {len(batch_lines)} non-empty line(s) — "
                       "a pretty-printed record appended verbatim is what the "
                       "append step's per-line jq dies on ('Unfinished JSON "
                       "term at EOF', persist runs 34562607603/34287169782)")
            return
        by_key = {}
        for line in batch_lines:
            try:
                rec = json.loads(line)
            except ValueError as exc:
                fail(case, f"batch line is not one JSON record: {exc}: {line[:120]!r}")
                return
            by_key[rec["run"]["job_key"]] = rec
        diag = by_key.get("diagnose", {}).get("run", {})
        if diag.get("job_id") != diagnose_job_id:
            fail(case, "job_key 'diagnose' must resolve to the job the API "
                       f"names 'watchdog / diagnose' (id {diagnose_job_id}), "
                       f"got job_id={diag.get('job_id')!r} — reusable-workflow "
                       "jobs are displayed as '<caller job> / <callee job>', "
                       "never as the bare github.job the record carries")
        want_key = f"{run_id}:{diagnose_job_id}:0"
        if diag.get("record_key") != want_key:
            fail(case, f"expected the persisted record_key rewritten to "
                       f"{want_key!r}, got {diag.get('record_key')!r}")
        coll = by_key.get("collect", {}).get("run", {})
        if coll.get("job_id") is not None or coll.get("record_key") != f"{run_id}:collect:0":
            fail(case, "job_key 'collect' matches two callers ('watchdog / "
                       "collect' and 'watchdog-self / collect'), so it must "
                       "keep job_id null and its emission-time record_key "
                       f"rather than guess — got job_id={coll.get('job_id')!r}, "
                       f"record_key={coll.get('record_key')!r}")

        rc, output, outputs, _summary = run_step(
            BASH, SCRIPT, work,
            {"BRANCH": "metrics", "DEST_PATH": DEST_PATH, "RUN_ID": run_id,
             "GH_TOKEN": "stub-token"}, runner_temp)
        shutil.rmtree(work, ignore_errors=True)
        if rc != 0:
            fail(case, f"append step exited {rc} on the batch validate "
                       f"wrote: {output.strip()[:500]}")
            return
        if outputs.get("persisted-count") != "3":
            fail(case, f"expected persisted-count=3, got {outputs.get('persisted-count')!r}")

        text, final_work = fetch_dest(tmp, origin, "metrics", "final")
        shutil.rmtree(final_work, ignore_errors=True)
        dest_lines = [line for line in (text or "").split("\n") if line.strip()]
        if len(dest_lines) != 3 or want_key not in (text or "") \
                or f"{run_id}:collect:0" not in (text or ""):
            fail(case, f"destination must hold exactly the three records, one "
                       f"per line (numeric-job_id key for the resolved one, "
                       f"emission-time key for the ambiguous one); got: {text!r}")
        note("pretty-printed records from a 'watchdog / diagnose'-style job, "
             "an ambiguous two-caller 'collect' job (job_id kept null), and "
             "a multi-model run all validated and persisted as one JSONL "
             "line each")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


CASES = [
    case_zero_artifact_batch_against_existing_branch_is_zero_failure,
    case_first_write_creates_missing_destination_branch,
    case_transient_first_push_failure_with_no_concurrent_writer_recovers,
    case_first_push_rejected_by_concurrent_writer_recovers_without_loss,
    case_sustained_contention_fails_loudly_naming_the_key,
    case_idempotent_repeat_persistence_is_byte_for_byte_unchanged,
    case_validate_then_append_persists_reusable_workflow_records,
]


def main():
    global BASH
    use_utf8_stdout()
    ensure_jq()
    BASH = resolve_bash()
    for case in CASES:
        case()
    if failures:
        print(f"{len(failures)} failure(s).")
        return 1
    print(f"verify-metrics-persist-retry: {len(CASES)} case(s) checked; all passed.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--self-test":
        sys.exit(main())
    sys.exit("verify-metrics-persist-retry: no live subject in the repository "
             "(the metrics branch is a runtime artifact) — run with --self-test.")
