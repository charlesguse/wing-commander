#!/usr/bin/env python3
"""Shared fixtures and drivers for the metrics-persistence gates.

Three things live here rather than in any one gate:

1. A schema-version-1 metrics record in the exact shape
   wing-commander-metrics-summary emits. Gate 40's retry harness and spec
   058's three sweep gates all need one, and a record that drifts from the
   emitter is a fixture that proves nothing — the validate step's own
   strict field check would start rejecting it and every gate built on it
   would go red for a reason that has nothing to do with what it tests.

2. `run_sweep`/`resweep` — the driver that executes the SHIPPED
   discover/retrieve/validate/append steps of
   wing-commander-metrics-persist/action.yml, in order, in sweep mode,
   against a real local git remote and a `gh` stub. Gates 76, 77 and 78
   each assert a different property of one sweep; they must all be
   asserting it about the same shipped shell, driven the same way.

3. `run_window` — the same treatment for metrics-persist.yml's own
   "Resolve the sweep window and list its runs" step, which owns the
   high-water-mark read and the fixed one-hour overlap (research.md R-C3).

Nothing here reaches the network. `origin` is a bare repository on disk,
and its `update` hook is what injects a push rejection when a gate needs
to prove that two files retry together rather than separately.
"""
import functools
import json
import os
import shutil
import stat
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_shell_harness import (ensure_jq, find_step, resolve_bash,  # noqa: E402
                              run_step)

ACTION = os.path.join(".github", "actions", "wing-commander-metrics-persist",
                      "action.yml")
STAGE = os.path.join(".github", "workflows", "metrics-persist.yml")
DISCOVER = "Discover jobs and metrics-record artifacts"
RETRIEVE = "Retrieve metrics-record artifacts"
VALIDATE = "Validate records and build the new-records batch"
APPEND = "Append records with retry"
WINDOW = "Resolve the sweep window and list its runs"
SWEEP_STEPS = (DISCOVER, RETRIEVE, VALIDATE, APPEND)

REPO = "acme/wing-commander"
BRANCH = "metrics"
DEST = "records.jsonl"
STATE = "sweep-state.json"
LEDGER = "unpersisted.jsonl"


# --------------------------------------------------------------------------
# The record fixture
# --------------------------------------------------------------------------
def metrics_record(run_id, job_key, step_index=0):
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


def write_pretty(path, record):
    # indent=2, deliberately: the emitter writes its record pretty-printed
    # (`jq -n` without -c), and a compact fixture here would pass against
    # the exact validate step that shipped broken.
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(record, f, indent=2)
        f.write("\n")


def fixture_job_id(run_id, index):
    """The numeric job id this harness gives a fixture run's Nth job.

    The validate step resolves `job_key` -> numeric `job_id` against the
    jobs API and REWRITES record_key to `run_id:job_id:step_index` when the
    match is unambiguous (spec 043's R6). A fixture that served no jobs
    would leave every record on the un-rewritten fallback path and quietly
    stop covering the one these gates' record_keys actually take in
    production, so the fixtures serve real ids and the expectations are
    derived from the same function.
    """
    return int(run_id) * 100 + index


def resolved_key(run_id, index=0, step_index=0):
    return f"{run_id}:{fixture_job_id(run_id, index)}:{step_index}"


def persisted_record(run_id, job_key, index=0, step_index=0):
    """What a record looks like AFTER the validate step rewrote it — i.e.
    what a line already in records.jsonl holds."""
    rec = metrics_record(run_id, job_key, step_index)
    rec["run"]["job_id"] = fixture_job_id(run_id, index)
    rec["run"]["record_key"] = resolved_key(run_id, index, step_index)
    return rec


def record_line(record):
    return json.dumps(record, separators=(",", ":")) + "\n"


def record_keys(lines):
    keys = []
    for line in lines:
        try:
            keys.append(json.loads(line)["run"]["record_key"])
        except (ValueError, KeyError, TypeError):
            keys.append(f"<unparseable:{line[:40]}>")
    return keys


# --------------------------------------------------------------------------
# Stubs
# --------------------------------------------------------------------------
GH_STUB = """#!/usr/bin/env bash
# Serves the Actions-API shapes the shipped steps ask for, out of
# $WC_FIX/. The shipped calls pass --jq; like every other stub in this
# repository's harnesses, this one emits the POST-filter shape rather than
# running the filter itself.
if [ "${1:-}" = "api" ]; then
  path="$2"
  case "$path" in
    */actions/runs\\?*)
      # The sweep window's own listing call.
      cat "$WC_FIX/candidates.ndjson" 2>/dev/null
      exit 0;;
  esac
  rest="${path#*/actions/runs/}"
  rid="${rest%%/*}"
  case "$path" in
    */jobs*)      cat "$WC_FIX/$rid/jobs.ndjson" 2>/dev/null; exit 0;;
    */artifacts*) cat "$WC_FIX/$rid/artifacts.ndjson" 2>/dev/null; exit 0;;
  esac
  echo "gh-stub: unmodelled api path $path" >&2
  exit 1
fi
if [ "${1:-}" = "run" ] && [ "${2:-}" = "download" ]; then
  rid="$3"
  dir=""
  prev=""
  for a in "$@"; do
    [ "$prev" = "-D" ] && dir="$a"
    prev="$a"
  done
  if [ -d "$WC_FIX/$rid/artifacts" ] && [ -n "$dir" ]; then
    mkdir -p "$dir"
    cp -R "$WC_FIX/$rid/artifacts/." "$dir/"
    exit 0
  fi
  echo "no artifacts match metrics-record* for run $rid (expired)" >&2
  exit 1
fi
echo "gh-stub: unmodelled command $*" >&2
exit 1
"""

# Rejects the first N pushes, then accepts. A real non-fast-forward is the
# shape the shipped loop is written against, but any rejection drives the
# same branch, and a hook is the only way to make one happen on demand.
UPDATE_HOOK = """#!/bin/sh
f="$GIT_DIR/reject-count"
n=$(cat "$f" 2>/dev/null || echo 0)
if [ "$n" -gt 0 ]; then
  echo "$((n - 1))" > "$f"
  echo "fixture hook: rejecting this push" >&2
  exit 1
fi
exit 0
"""


def _exec(path, content):
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(content)
    os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def _git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True,
                          text=True, encoding="utf-8", errors="replace")


# --------------------------------------------------------------------------
# Workspace
# --------------------------------------------------------------------------
def make_workspace(work, seed_files=None, reject_pushes=0):
    """A bare `origin` holding `metrics`, and a working clone beside it."""
    origin = os.path.join(work, "origin.git")
    repo = os.path.join(work, "repo")
    os.makedirs(origin, exist_ok=True)
    os.makedirs(repo, exist_ok=True)
    _git(origin, "init", "--bare", "-q")
    if reject_pushes:
        hooks = os.path.join(origin, "hooks")
        os.makedirs(hooks, exist_ok=True)
        _exec(os.path.join(hooks, "update"), UPDATE_HOOK)
        with open(os.path.join(origin, "reject-count"), "w", encoding="utf-8") as fh:
            fh.write(str(reject_pushes))
    _git(repo, "init", "-q")
    _git(repo, "config", "user.name", "fixture")
    _git(repo, "config", "user.email", "fixture@example.invalid")
    _git(repo, "remote", "add", "origin", origin)
    for path, content in (seed_files if seed_files is not None else {DEST: ""}).items():
        with open(os.path.join(repo, path), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(content)
        _git(repo, "add", path)
    _git(repo, "commit", "-q", "-m", "fixture: seed the destination branch")
    _git(repo, "push", "-q", "origin", f"HEAD:refs/heads/{BRANCH}")
    _git(repo, "checkout", "-q", "--detach")
    return origin, repo


# The Windows build of jq ends raw (-r) output lines with CRLF, and the
# shipped composite builds a per-run directory from `jq -r` output
# (runs/<id>/artifacts.json), so on a Windows checkout every path carries a
# trailing CR and the three sweep gates fail while CI (Linux) is green (#446).
# The pipeline targets ubuntu-latest, so nothing shipped changes: this shim is
# written only where the local jq is observed to emit a CR, and strips it.
JQ_SHIM = """#!/usr/bin/env bash
# jq whose lines never end in a carriage return (#446); the real jq is {real}.
# Only a CR at the end of a line goes: one inside a value is data.
"{real}" "$@" | sed 's/\\r$//'
exit "${{PIPESTATUS[0]}}"
"""


@functools.lru_cache(maxsize=1)
def _jq_emitting_cr():
    """The real jq's own answer never changes within one process (#449
    review) -- _bindir() runs once per run_sweep()/run_window() call, and
    each of Gates 76-78's mutation scenarios calls one of those, so an
    unmemoized probe re-spawns jq to re-derive an already-known answer."""
    real = shutil.which("jq")
    if not real:
        return None
    out = subprocess.run([real, "-nr", '"x"'], capture_output=True).stdout
    return real if b"\r" in out else None


def _bindir(work):
    bindir = os.path.join(work, "bin")
    os.makedirs(bindir, exist_ok=True)
    _exec(os.path.join(bindir, "gh"), GH_STUB)
    real = _jq_emitting_cr()
    if real:
        _exec(os.path.join(bindir, "jq"),
              JQ_SHIM.format(real=real.replace("\\", "/")))
    return bindir


def write_fixtures(work, runs):
    """$WC_FIX/<run-id>/{jobs.ndjson,artifacts.ndjson,artifacts/...}."""
    fix = os.path.join(work, "fixtures")
    for run in runs:
        rid = str(run["run_id"])
        rdir = os.path.join(fix, rid)
        os.makedirs(rdir, exist_ok=True)
        records = run.get("records") or []
        with open(os.path.join(rdir, "jobs.ndjson"), "w", encoding="utf-8", newline="\n") as fh:
            for i, rec in enumerate(records):
                fh.write(json.dumps({"id": fixture_job_id(rid, i),
                                     "name": rec["run"]["job_key"]}) + "\n")
        names = run.get("artifact_names")
        if names is None:
            names = [f"metrics-record-{r['run']['job_key']}" for r in records]
        # An "expired" run lists its artifact but has no directory to serve,
        # so `gh run download` fails exactly as it does against an artifact
        # past its retention window -- and (MF-03) the listing itself says
        # so via `expired: true`, the real API's own field this fixture
        # mirrors so the shipped step can tell that apart from a live
        # artifact whose download merely failed (`download_fails`, below).
        run_expired = bool(run.get("expired"))
        with open(os.path.join(rdir, "artifacts.ndjson"), "w", encoding="utf-8", newline="\n") as fh:
            for name in names:
                fh.write(json.dumps({"name": name, "expired": run_expired}) + "\n")
        if run_expired:
            continue
        download_fails = set(run.get("download_fails") or [])
        for rec in records:
            name = f"metrics-record-{rec['run']['job_key']}"
            if name in download_fails:
                # MF-03: listed, not expired, but its directory is withheld
                # so `gh run download` fails against it exactly as it would
                # on a transient retrieval error -- a DIFFERENT outcome from
                # the whole-run `expired` case above.
                continue
            adir = os.path.join(rdir, "artifacts", name)
            os.makedirs(adir, exist_ok=True)
            write_pretty(os.path.join(adir, "wing-commander-metrics-record.json"), rec)
    return fix


def sweep_runs_json(runs):
    return json.dumps([{"run_id": str(r["run_id"]),
                        "workflow": r.get("workflow", ""),
                        "concluded_at": r["concluded_at"]} for r in runs],
                      separators=(",", ":"))


# --------------------------------------------------------------------------
# Driver: one whole sweep through the composite's four shipped steps
# --------------------------------------------------------------------------
def run_sweep(work, runs, seed_records="", reject_pushes=0, bash=None,
              mutate=None):
    """Drive one whole sweep. Returns per-step results plus the destination
    branch's post-sweep state (records, sweep_state, unpersisted, commits).

    `mutate(step_name, script) -> script` lets a gate prove one of the
    shipped guards is load-bearing (constitution VIII).
    """
    bash = bash or resolve_bash()
    ensure_jq()
    _origin, repo = make_workspace(work, {DEST: seed_records}, reject_pushes)
    _bindir(work)
    return _drive(work, repo, runs, bash, 1, mutate)


def resweep(work, result, runs, bash=None, pass_no=2, mutate=None):
    """A second sweep over the same destination branch, as the next day's
    schedule would run it — a fresh RUNNER_TEMP, the same origin."""
    return _drive(work, result["repo"], runs, bash or resolve_bash(), pass_no,
                  mutate)


def _drive(work, repo, runs, bash, pass_no, mutate=None):
    fix = write_fixtures(work, runs)
    # A fresh RUNNER_TEMP per sweep: the runner's temp is per-run, and a
    # reused one would hand the second sweep the first one's batch file.
    tmp = os.path.join(work, f"tmp{pass_no}")
    os.makedirs(tmp, exist_ok=True)
    env = {"GH_TOKEN": "stub-token", "RUN_ID": "",
           "SWEEP_RUNS": sweep_runs_json(runs),
           "GITHUB_REPOSITORY": REPO, "BRANCH": BRANCH, "DEST_PATH": DEST,
           "WC_FIX": fix,
           "PATH": os.path.join(work, "bin") + os.pathsep
                   + os.environ.get("PATH", "")}

    result = {"steps": [], "repo": repo}
    outputs = {}
    for name in SWEEP_STEPS:
        # The retrieve step's own `if:` — GitHub evaluates it, so the driver
        # must, or a zero-artifact sweep would exercise a step the runner
        # would have skipped.
        if name == RETRIEVE and outputs.get("count", "0") == "0":
            result["steps"].append((name, "skipped", ""))
            continue
        script = find_step(ACTION, name)["run"]
        if mutate is not None:
            script = mutate(name, script)
        rc, out, step_outputs, _summary = run_step(bash, script, repo, env, tmp)
        outputs.update(step_outputs)
        result["steps"].append((name, rc, out))
        if rc != 0:
            break
    result["outputs"] = outputs
    result["rc"] = max((s[1] for s in result["steps"]
                        if isinstance(s[1], int)), default=0)
    result.update(read_branch_state(repo))
    return result


def read_branch_state(repo):
    """What the destination branch holds now, and in which commits."""
    _git(repo, "fetch", "--no-tags", "-q", "origin",
         f"+refs/heads/{BRANCH}:refs/remotes/origin/{BRANCH}")

    def show(path):
        proc = _git(repo, "show", f"origin/{BRANCH}:{path}")
        return proc.stdout if proc.returncode == 0 else None

    log = _git(repo, "log", "--format=%x00%s", "--name-only", f"origin/{BRANCH}")
    commits = []
    for chunk in log.stdout.split("\0"):
        if not chunk.strip():
            continue
        lines = [ln for ln in chunk.splitlines() if ln.strip()]
        commits.append({"subject": lines[0], "files": lines[1:]})
    records, state, ledger = show(DEST), show(STATE), show(LEDGER)
    return {
        "records": [ln for ln in (records or "").splitlines() if ln.strip()],
        "sweep_state": json.loads(state) if state else None,
        "unpersisted": [json.loads(ln) for ln in (ledger or "").splitlines()
                        if ln.strip()],
        "commits": commits,
    }


# --------------------------------------------------------------------------
# Driver: the stage's own window resolution
# --------------------------------------------------------------------------
def run_window(work, candidates, mark=None, since_input="", bash=None,
               mutate=None, workflow_paths=None):
    """Execute metrics-persist.yml's window step against a destination
    branch that does (or does not) already carry a high-water mark.

    `candidates` is what the Actions API would stream back:
    [{"run_id", "workflow", "concluded_at"}, ...] — every completed run in
    the server-side `created` bound, before the client-side window filter
    the step applies. A candidate may also carry "conclusion" (MF-02(a) —
    "skipped" is dropped before it ever reaches the composite); absent
    means non-skipped, matching a real API response's usual shape.

    `workflow_paths`, when given, is a list of workflow file paths passed
    through as the step's WORKFLOW_PATHS input (MF-02(b)) -- None means
    "no restriction", the same as an unset input in production.
    """
    bash = bash or resolve_bash()
    ensure_jq()
    seed = {DEST: ""}
    if mark is not None:
        seed[STATE] = json.dumps({"high_water_mark": mark}) + "\n"
    _origin, repo = make_workspace(work, seed)
    fix = os.path.join(work, "fixtures")
    os.makedirs(fix, exist_ok=True)
    with open(os.path.join(fix, "candidates.ndjson"), "w", encoding="utf-8", newline="\n") as fh:
        for c in candidates:
            fh.write(json.dumps(c) + "\n")
    tmp = os.path.join(work, "wtmp")
    os.makedirs(tmp, exist_ok=True)
    script = find_step(STAGE, WINDOW)["run"]
    if mutate is not None:
        script = mutate(WINDOW, script)
    env = {"GH_TOKEN": "stub-token", "SINCE_INPUT": since_input,
           "BRANCH": BRANCH, "GITHUB_REPOSITORY": REPO, "WC_FIX": fix,
           "WORKFLOW_PATHS": json.dumps(workflow_paths) if workflow_paths is not None else "",
           "PATH": _bindir(work) + os.pathsep + os.environ.get("PATH", "")}
    rc, out, outputs, summary = run_step(bash, script, repo, env, tmp)
    listed = []
    if outputs.get("sweep-runs"):
        try:
            listed = json.loads(outputs["sweep-runs"])
        except ValueError:
            listed = []
    return {"rc": rc, "out": out, "outputs": outputs, "summary": summary,
            "listed": listed, "listed_ids": [r.get("run_id") for r in listed]}


def cleanup(work):
    shutil.rmtree(work, ignore_errors=True)
