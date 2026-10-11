#!/usr/bin/env python3
"""Behavioral tests for watchdog.yml's "Collect: step summaries" step.

WHY THIS EXISTS
---------------
That step is the pipeline's own tripwire: it scrapes each job's log for the
sentinel phrases the stages emit, and everything downstream (diagnose, the
filed issue) can only ever reason about signals this step actually collected.
A sentinel it fails to collect does not degrade the watchdog — it makes the
watchdog silently blind to one class of problem while still reporting
"inspection passed", which is the single most expensive failure shape this
repository has hit (2026-07-24, and again at 2026-07-25's determinism audit).

Nothing tested it. The step is pure shell inside a `gh api` loop, so no gate
could see it, and its two scanning passes had already grown a real conflict:

  * The legacy pass matches ordinary English words (`stalled`, `rejected`,
    `denied`, `abandon`) and is capped at ONE match per job to bound volume.
  * The emitted-token pass matches `WC-SENTINEL: <token>` and is deliberately
    uncapped, because the cap had previously made those signals unreachable.

docs/agent-friendly-workflows.md recommends writing sentinels in exactly the
form `WC-SENTINEL: stalled` — which matched BOTH passes. One event then
emitted two signals carrying the same {job, matched-sentinel} pair, and since
that pair is precisely the identity the "Stamp signal ids" step hashes
(watchdog.yml, the step-summary branch of its projection), they collapsed to
one duplicated id. Worse, the duplicate consumed the legacy pass's single
match for that job, so an unrelated genuine `denied` later in the same log was
never collected — reintroducing, for the legacy pass, the exact masking the
token pass was added to escape.

This harness EXECUTES the shipped step against synthetic job logs, with `gh`
stubbed out, and asserts what lands in signals.json. It reads the step out of
watchdog.yml at run time, so there is no second copy to drift (same discipline
as gate 4's auto-update harness and gate 5's collector fixture — the latter
added after a verifier sat green while checking a filter that did not ship).

It ends with MUTATION checks that reintroduce the conflict and assert the
suite fails. A test that cannot fail is not a test.

It also executes diagnose's "Stage failed-job logs" step, which reads the
same fetch helper's output, against unreadable job listings: those must
reach the status file as `failed` (specs/101-read-only-gh-grants FR-019).

Usage: python3 .github/scripts/verify-sentinel-collector.py
Requires: bash, jq. See wc_shell_harness.py for running this on Windows.
"""
import copy
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_shell_harness import (  # noqa: E402
    ensure_jq, find_step, resolve_bash, run_step, step_shell,
    use_utf8_stdout)

WATCHDOG = ".github/workflows/watchdog.yml"
STEP = "Collect: step summaries"

BASH = None

# A real job log wraps every step's own script source and env dump between
# these markers. The shipped awk filter strips those blocks, because sentinel
# words in UNEXECUTED source self-matched on essentially every run — a
# 2026-07-24 audit traced 7 false findings, one of them a filed issue, to
# exactly that.
GROUP = "##[group]Run echo hello"
ENDGROUP = "##[endgroup]"


def log(*runtime_lines, echoed=()):
    """A synthetic job log: an echoed script block, then runtime output."""
    lines = [GROUP]
    lines += [f"2026-08-08T00:00:0{i}Z {t}" for i, t in enumerate(echoed)]
    lines.append(ENDGROUP)
    lines += [f"2026-08-08T00:01:0{i}Z {t}" for i, t in enumerate(runtime_lines)]
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------
# Scenarios: job log -> the {matched-sentinel} multiset the step must collect
# --------------------------------------------------------------------------
SCENARIOS = [
    dict(
        name="the documented sentinel form is collected exactly once",
        why="docs/agent-friendly-workflows.md tells stage authors to write "
            "'WC-SENTINEL: stalled'. That line matches the emitted-token "
            "regex AND the legacy bare-word alternation, so it produced two "
            "signals for one event — and because the id is hashed from "
            "{job, matched-sentinel}, two signals with one id.",
        log=log("WC-SENTINEL: stalled - the agent stopped making progress."),
        expect=["stalled"],
    ),
    dict(
        name="a token line does not mask an unrelated legacy word",
        why="The legacy pass takes the FIRST match in the whole job log and "
            "stops. When the token line also matched it, that one match was "
            "spent on an event already reported by the token pass, and the "
            "genuine 'denied' below it was never collected at all. A sentinel "
            "that another sentinel can silence is not a safety net.",
        log=log("WC-SENTINEL: stalled - watchdog token from a stage",
                "A tool call was denied by the permission policy."),
        expect=["stalled", "denied"],
    ),
    dict(
        name="the clarification sentinels this pipeline actually emits",
        why="Both 032 sentinels in one job, which is reachable: intake can "
            "author an orphaned questionnaire and disagree with the marker "
            "scan in the same run. Distinct tokens are uncapped.",
        log=log("WARN WC-SENTINEL: clarification-orphaned - no branch found.",
                "WARN WC-SENTINEL: clarification-mismatch - scan disagreed."),
        expect=["clarification-mismatch", "clarification-orphaned"],
    ),
    dict(
        name="a token that is a prefix of another keeps its own line",
        why="The trailing boundary in the token regex stops the shorter token "
            "from borrowing the longer one's line as its excerpt, which would "
            "attach misleading evidence to a real signal.",
        log=log("WC-SENTINEL: clarification-mismatch - the short one.",
                "WC-SENTINEL: clarification-mismatched - the long one."),
        expect=["clarification-mismatch", "clarification-mismatched"],
        expect_excerpts={"clarification-mismatch": "the short one",
                         "clarification-mismatched": "the long one"},
    ),
    dict(
        name="sentinel words in echoed script source are ignored",
        why="Actions echoes each step's own source into the log between "
            "##[group] and ##[endgroup]. This scanner's own regex lives "
            "there, so without the awk strip it matches itself on every "
            "single run. This is the 2026-07-24 false-finding class.",
        log=log("nothing interesting happened",
                echoed=["sentinels='stalled|rejected|denied|abandon'",
                        "token_re='WC-SENTINEL: [a-z][a-z0-9-]*'"]),
        expect=[],
    ),
    dict(
        name="a bare legacy word is still collected",
        why="The legacy pass is not being retired here, only kept disjoint. "
            "Stage output that predates the token convention must still be "
            "seen.",
        log=log("The run was abandoned after the third retry."),
        expect=["abandon"],
    ),
    dict(
        name="the legacy pass stays capped at one match per job",
        why="Those words occur incidentally in agent prose; the cap is what "
            "bounds signal volume, and removing it is not the fix for the "
            "masking above. Only the first is collected, deliberately.",
        log=log("The request was rejected by the API.",
                "A later tool call was denied as well.",
                "The job then stalled."),
        expect=["rejected"],
    ),
]


def render_step(step):
    """The step's run: block with its `${{ }}` env wired to fixture values."""
    script = str(step["run"])
    env = {}
    for k, v in (step.get("env") or {}).items():
        v = str(v)
        if "${{" in v:
            # Both are supplied by the harness; the token is never used
            # because `gh` is stubbed.
            v = {"GH_TOKEN": "dummy-token", "RUN_ID": "12345"}.get(k, "")
        env[k] = v
    if "${{" in script:
        sys.exit(f"::error file={WATCHDOG}::the extracted run: block contains a "
                 f"${{{{ }}}} expression this harness does not resolve.")
    return script, env


def stub_gh(bindir, fixture_dir, raw=False, jobs_rc=0, crash_logs=False):
    """A `gh` that answers the two api calls the fetch helper makes, from files.

    `raw=True` skips the `--jq` below and prints jobs.json as is, with exit
    status 0: the case where gh succeeds yet `jq -s` cannot parse what
    reached it, which gh's exit status alone does not report. `jobs_rc`
    makes the listing exit with that status after printing (gh failing on a
    later page); `crash_logs` makes a log read print part of the log and
    then kill the shell running it.

    The jobs listing is read with `--paginate --jq '.jobs[]'` (spec 036):
    under `--paginate` gh applies the filter to each page and emits one JSON
    value per line, and the step slurps that back with `jq -s '.'`. A stub
    that dumped the raw `{"jobs":[...]}` fixture would therefore hand the
    step `[{"jobs":[...]}]`, whose `.[]?.id` is empty — every scenario would
    report "no sentinels collected" and read as a defect in the collector.
    Applying the step's own `--jq` here keeps the fixture honest about the
    shape gh actually produces.
    """
    path = os.path.join(bindir, "gh")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(
            '#!/usr/bin/env bash\n'
            '# Stub for the two `gh api` reads the collector performs.\n'
            'p="$2"\n'
            f'd="{fixture_dir}"\n'
            'jqexpr=""\n'
            'prev=""\n'
            'for arg in "$@"; do\n'
            '  if [ "$prev" = "--jq" ]; then jqexpr="$arg"; fi\n'
            '  prev="$arg"\n'
            'done\n'
            'case "$p" in\n'
            '  */jobs)\n'
            + ('    cat "$d/jobs.json"\n' if raw else
               '    if [ -n "$jqexpr" ]; then jq -c "$jqexpr" "$d/jobs.json"; '
               'else cat "$d/jobs.json"; fi\n')
            + f'    rc=$?; [ {int(jobs_rc)} = 0 ] || rc={int(jobs_rc)}; exit $rc ;;\n'
            '  */logs) id="${p#*/actions/jobs/}"; id="${id%/logs}"; '
            + ('head -c 5 "$d/log-$id.txt"; kill -KILL "$PPID"; exit 137 ;;\n'
               if crash_logs else 'cat "$d/log-$id.txt" ;;\n')
            +
            '  *) echo "unexpected gh api path: $p" >&2; exit 1 ;;\n'
            'esac\n')
    os.chmod(path, 0o755)


def run_collector(script, env, tmproot, listing, raw=False, logs=None,
                  fetch=None, crash_jq=False):
    """Run the shared fetch helper (`fetch`, else the shipped one) against
    `listing` (see run_fetch), then
    the collector on its output, the way the collect job does. -> (rc,
    output, signals, collector outcomes)."""
    workdir = tempfile.mkdtemp(dir=tmproot)
    runner_temp = tempfile.mkdtemp(dir=tmproot)
    try:
        # Seeded the way the collect job's "Initialize ..." steps do (spec
        # 036 T016): every collector appends its own read-outcome record to
        # collector-outcomes.json, and jq reading a file that does not exist
        # is a hard failure under the runner's `bash -e`.
        for name in ("signals.json", "collector-outcomes.json"):
            with open(os.path.join(runner_temp, name), "w",
                      encoding="utf-8") as fh:
                fh.write("[]")
        # The collector reads what the wing-commander-fetch-job-logs
        # composite staged (specs/101-read-only-gh-grants); hand the step
        # the helper's result.
        env = dict(env)
        env["FETCH_RESULT"] = run_fetch(
            fetch or shipped_fetch(), listing,
            os.path.join(runner_temp, "cs-job-logs"),
            tmproot, raw=raw, logs=logs, crash_jq=crash_jq)[1] or ""
        rc, out, _, _ = run_step(BASH, script, workdir, env, runner_temp)
        return (rc, out,
                _load_json(os.path.join(runner_temp, "signals.json")),
                _load_json(os.path.join(runner_temp, "collector-outcomes.json")))
    finally:
        for d in (workdir, runner_temp):
            shutil.rmtree(d, ignore_errors=True)


def run_one(script, env, sc, tmproot):
    """Execute the collector against one fixture; return collected signals."""
    rc, out, signals, _ = run_collector(
        script, env, tmproot,
        json.dumps({"jobs": [{"id": 777, "name": "intake",
                              "conclusion": "success"}]}),
        logs={777: sc["log"]})
    if signals is None:
        return 1, out + "\n(signals.json is missing or not JSON)", []
    return rc, out, signals


def suite(script, env, tmproot):
    failures = []
    for sc in SCENARIOS:
        tag = f"[{sc['name']}]"
        rc, out, signals = run_one(script, env, sc, tmproot)
        if rc != 0:
            failures.append(f"{tag} the collector exited {rc}:\n{out}")
            continue

        got = sorted(s["facts"]["matched-sentinel"] for s in signals)
        if got != sorted(sc["expect"]):
            failures.append(
                f"{tag} wrong sentinels collected.\n"
                f"    expected: {sorted(sc['expect']) or '(none)'}\n"
                f"    actual:   {got or '(none)'}\n    {sc['why']}")

        # {job, matched-sentinel} IS the identity the "Stamp signal ids" step
        # hashes for source=step-summary, so a repeated pair is not merely
        # untidy — it is two signals with one id, i.e. one event presented to
        # diagnose as corroborating evidence for itself.
        pairs = [(s["facts"]["job"], s["facts"]["matched-sentinel"])
                 for s in signals]
        dupes = {p for p in pairs if pairs.count(p) > 1}
        if dupes:
            failures.append(
                f"{tag} the same {{job, sentinel}} pair was collected more "
                f"than once ({sorted(dupes)}). That pair is what the signal id "
                f"is hashed from, so these are duplicate ids describing a "
                f"single event. {sc['why']}")

        for tok, want in (sc.get("expect_excerpts") or {}).items():
            line = next((s["facts"]["matched-line"] for s in signals
                         if s["facts"]["matched-sentinel"] == tok), None)
            if line is None:
                continue      # already reported by the multiset check above
            if want not in line:
                failures.append(
                    f"{tag} the excerpt for {tok!r} should quote its own line "
                    f"({want!r}), got {line!r}. Evidence attached to the wrong "
                    f"line is worse than none. {sc['why']}")
    return failures


# --------------------------------------------------------------------------
# Mutations
# --------------------------------------------------------------------------
def mut_overlapping_passes(script):
    """Let the legacy pass see emitted-token lines again (the shipped bug)."""
    return script.replace("""grep -Fv 'WC-SENTINEL: ' | grep -Eim1 "$sentinels\"""",
                          """grep -Eim1 "$sentinels\"""")


def mut_no_group_strip(script):
    """Scan the whole log, echoed script source included."""
    return script.replace(
        'runtime="$(printf \'%s\' "$log" | awk',
        'runtime="$(printf \'%s\' "$log" | cat)" # awk')


def mut_cap_token_pass(script):
    """Put the emitted tokens back under the legacy first-match-wins cap."""
    return script.replace(
        "token_re='WC-SENTINEL: [a-z][a-z0-9-]*'",
        "token_re='WC-SENTINEL: nothing-matches-this'")


MUTATIONS = [
    ("the legacy pass matching emitted-token lines (double-count + masking)",
     mut_overlapping_passes),
    ("scanning echoed script source as if it were runtime output",
     mut_no_group_strip),
    ("the emitted-token pass no longer matching anything", mut_cap_token_pass),
]


# --------------------------------------------------------------------------
# Diagnose's "Stage failed-job logs" (specs/101-read-only-gh-grants FR-019)
# --------------------------------------------------------------------------
# The same fetch helper feeds diagnose's staging step, which writes the status
# file the read-only agent reads. An unreadable job listing must reach that
# file as `failed`, never as `ok` with no jobs ("nothing failed").
STAGE_STEP = "Stage failed-job logs"
FETCH_ACTION = ".github/actions/wing-commander-fetch-job-logs/action.yml"
FETCH_STEP = "Fetch job logs"
UNREADABLE_LISTING = '[{"id": 901, "name": "implement", "conclusion": "fail'
UNCHECKED = object()
FAILED_JOBS = [{"id": 901, "name": "implement", "conclusion": "failure"},
               {"id": 902, "name": "lint", "conclusion": "success"}]


_FETCH = []


def shipped_fetch():
    """The shipped helper's run: script, read once."""
    if not _FETCH:
        _FETCH.append(str(find_step(FETCH_ACTION, FETCH_STEP)["run"]))
    return _FETCH[0]


def run_fetch(fetch_script, listing, out_dir, tmproot, raw=False, logs=None,
              jobs_rc=0, fail_mv=False, crash_jq=False, stale=None,
              crash_logs=False):
    """Run the shared helper against stub_gh. `listing` is jobs.json for the
    stub: printed as is when `raw`, else a `{"jobs": [...]}` page gh's own
    `--jq` is applied to; the listing exits `jobs_rc`. A listed job's log is
    `logs[id]`, or one line when `logs` does not name it; `fail_mv` makes
    every `mv` fail; `crash_jq` makes the listing's `jq -s` print part of
    its output and then kill the shell running it, as a runner that dies
    mid-write would; `stale` is a jobs.json left in `out_dir` beforehand;
    `crash_logs` kills it the same way during a log read. Returns
    (step rc, `result` output or None, jobs.json text or None, reason.txt
    text or None, the .log files left in `out_dir`)."""
    workdir = tempfile.mkdtemp(dir=tmproot)
    runner_temp = tempfile.mkdtemp(dir=tmproot)
    fixtures = tempfile.mkdtemp(dir=tmproot)
    bindir = tempfile.mkdtemp(dir=tmproot)
    try:
        with open(os.path.join(fixtures, "jobs.json"), "w", encoding="utf-8",
                  newline="\n") as fh:
            fh.write(listing)
        if not raw:
            for job in json.loads(listing)["jobs"]:
                body = (logs or {}).get(job["id"], "log line\n")
                if body is None:                        # this job's log read fails
                    continue
                with open(os.path.join(fixtures, f"log-{job['id']}.txt"), "w",
                          encoding="utf-8", newline="\n") as fh:
                    fh.write(body)
        stub_gh(bindir, fixtures.replace("\\", "/"), raw=raw,
                jobs_rc=jobs_rc, crash_logs=crash_logs)
        if stale is not None:
            os.makedirs(out_dir, exist_ok=True)
            with open(os.path.join(out_dir, "jobs.json"), "w", encoding="utf-8") as fh:
                fh.write(stale)
        # The helper's one retry waits `sleep 10`; nothing here needs the wait.
        with open(os.path.join(bindir, "sleep"), "w", encoding="utf-8",
                  newline="\n") as fh:
            fh.write("#!/usr/bin/env bash\nexit 0\n")
        os.chmod(os.path.join(bindir, "sleep"), 0o755)
        if crash_jq:
            real_jq = shutil.which("jq")
            with open(os.path.join(bindir, "jq"), "w", encoding="utf-8",
                      newline="\n") as fh:
                fh.write("#!/usr/bin/env bash\n"
                         'if [ "$1" = "-s" ]; then head -c 12; kill -KILL "$PPID"; exit 137; fi\n'
                         f'exec "{real_jq}" "$@"\n')
            os.chmod(os.path.join(bindir, "jq"), 0o755)
        if fail_mv:
            with open(os.path.join(bindir, "mv"), "w", encoding="utf-8",
                      newline="\n") as fh:
                fh.write("#!/usr/bin/env bash\nexit 1\n")
            os.chmod(os.path.join(bindir, "mv"), 0o755)
        env = {"PATH": bindir + os.pathsep + os.environ["PATH"],
               "GITHUB_REPOSITORY": "charlesguse/wing-commander",
               "RUN_ID": "1", "GH_TOKEN": "x", "OUT_DIR": out_dir}
        rc, _out, outs, _sum = run_step(
            BASH, fetch_script, workdir, env, runner_temp,
            shell=step_shell(FETCH_ACTION, FETCH_STEP))

        def text(name):
            try:
                with open(os.path.join(out_dir, name), encoding="utf-8") as fh:
                    return fh.read()
            except OSError:
                return None
        logs_left = sorted(f for f in (os.listdir(out_dir) if os.path.isdir(out_dir) else [])
                           if f.endswith(".log"))
        return (rc, outs.get("result"), text("jobs.json"), text("reason.txt"),
                logs_left)
    finally:
        for d in (workdir, runner_temp, fixtures, bindir):
            shutil.rmtree(d, ignore_errors=True)


def _load_json(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def run_staging(stage_script, fetch_script, sc, tmproot):
    """Run the helper (or plant its output), then the staging step; return
    (run_fetch's tuple or None, staging rc, status object, untrusted
    collectors)."""
    workdir = tempfile.mkdtemp(dir=tmproot)
    runner_temp = tempfile.mkdtemp(dir=tmproot)
    try:
        fetch_dir = os.path.join(runner_temp, "dj-fetch")
        with open(os.path.join(runner_temp,
                               "watchdog-untrusted-collectors.json"),
                  "w", encoding="utf-8") as fh:
            fh.write("[]")
        if "gh_listing" in sc:
            f_rc, result, f_jobs, f_reason, f_logs = run_fetch(
                fetch_script, sc["gh_listing"], fetch_dir, tmproot,
                raw=sc.get("raw", True), jobs_rc=sc.get("gh_rc", 0),
                fail_mv=sc.get("fail_mv", False), crash_jq=sc.get("crash_jq", False),
                stale=sc.get("stale"), crash_logs=sc.get("crash_logs", False))
            helper = (f_rc, result, f_jobs, f_reason, f_logs)
        else:
            os.makedirs(fetch_dir)
            name = "jobs.json" if sc["jobs_json"] is not None else "jobs.json.tmp"
            with open(os.path.join(fetch_dir, name), "w", encoding="utf-8") as fh:
                fh.write(sc["jobs_json"] or UNREADABLE_LISTING)
            result = sc["fetch_result"]
            helper = None
        rc, _out, _, _ = run_step(BASH, stage_script, workdir,
                                  {"FETCH_RESULT": result or ""}, runner_temp,
                                  shell=step_shell(WATCHDOG, STAGE_STEP))
        return (helper, rc,
                _load_json(os.path.join(runner_temp,
                                        "watchdog-job-logs-status.json")),
                _load_json(os.path.join(runner_temp,
                                        "watchdog-untrusted-collectors.json")))
    finally:
        for d in (workdir, runner_temp):
            shutil.rmtree(d, ignore_errors=True)


STAGING_SCENARIOS = [
    dict(
        name="a crashed helper leaves no jobs.json: a gather failure",
        # A helper that died mid-write: no `result` output, no reason.txt,
        # only its temp file.
        jobs_json=None, fetch_result="",
        expect_outcome="failed", expect_reason="jobs-list",
        expect_files={},
    ),
    dict(
        name="a truncated jobs.json is a gather failure, not 'no failed jobs'",
        jobs_json=UNREADABLE_LISTING, fetch_result="",
        expect_outcome="failed", expect_reason="jobs-unreadable",
        expect_files={},
    ),
    dict(
        name="an empty object is not a job list",
        jobs_json="{}", fetch_result="",
        expect_outcome="failed", expect_reason="jobs-unreadable",
        expect_files={},
    ),
    dict(
        name="a list holding a non-job is not a job list",
        jobs_json="[null]", fetch_result="",
        expect_outcome="failed", expect_reason="jobs-unreadable",
        expect_files={},
    ),
    dict(
        name="valid JSON that is not a job array is a gather failure",
        jobs_json='{"message": "Not Found"}', fetch_result="ok",
        expect_outcome="failed", expect_reason="jobs-unreadable",
        expect_files={},
    ),
    dict(
        name="a listing jq -s cannot parse fails the helper, then the status",
        gh_listing=UNREADABLE_LISTING,
        expect_helper=(0, "failed", "[]", "jobs-list"),
        expect_outcome="failed", expect_reason="jobs-list",
        expect_files={},
    ),
    dict(
        name="gh failing after a parseable page fails the helper",
        gh_listing=json.dumps({"jobs": FAILED_JOBS}), raw=False, gh_rc=1,
        expect_helper=(0, "failed", "[]", "jobs-list"),
        expect_outcome="failed", expect_reason="jobs-list",
        expect_files={},
    ),
    dict(
        name="a helper killed mid-write leaves no half-written jobs.json",
        gh_listing=json.dumps({"jobs": FAILED_JOBS}), raw=False, crash_jq=True,
        # Whether the step dies with it is up to the shell's process layout;
        # either way nothing is left in jobs.json.
        expect_helper=(UNCHECKED, UNCHECKED, None, None),
        expect_outcome="failed", expect_reason="jobs-list",
        expect_files={},
    ),
    dict(
        name="a helper killed mid-write leaves no earlier run's jobs.json",
        gh_listing=json.dumps({"jobs": FAILED_JOBS}), raw=False, crash_jq=True,
        stale=json.dumps([FAILED_JOBS[1]]),
        expect_helper=(UNCHECKED, UNCHECKED, None, None),
        expect_outcome="failed", expect_reason="jobs-list",
        expect_files={},
    ),
    dict(
        name="a helper killed mid-log leaves no partial log",
        gh_listing=json.dumps({"jobs": FAILED_JOBS}), raw=False, crash_logs=True,
        expect_helper=(UNCHECKED, UNCHECKED, UNCHECKED, None, []),
        expect_outcome="failed", expect_reason=UNCHECKED,
        expect_files=UNCHECKED,
    ),
    dict(
        name="a helper that died after a readable listing is incomplete",
        jobs_json=json.dumps([FAILED_JOBS[1]]), fetch_result="",
        expect_outcome="failed", expect_reason="fetch-incomplete",
        expect_files={},
    ),
    dict(
        name="a failed helper that left no reason is incomplete",
        jobs_json="[]", fetch_result="failed",
        expect_outcome="failed", expect_reason="fetch-incomplete",
        expect_files={},
    ),
    dict(
        name="a failed move into place fails the helper",
        gh_listing=json.dumps({"jobs": FAILED_JOBS}), raw=False, fail_mv=True,
        expect_helper=(0, "failed", "[]", "jobs-list"),
        expect_outcome="failed", expect_reason="jobs-list",
        expect_files={},
    ),
    dict(
        name="control: a readable listing stages the failed job's log",
        gh_listing=json.dumps({"jobs": FAILED_JOBS}), raw=False,
        expect_helper=(0, "ok", UNCHECKED, None),
        expect_outcome="ok", expect_reason=None,
        expect_files={901: True},
    ),
    dict(
        name="control: a readable listing with no failed job is ok and empty",
        jobs_json=json.dumps([FAILED_JOBS[1]]), fetch_result="ok",
        expect_outcome="ok", expect_reason=None, expect_files={},
    ),
]


def staging_suite(stage_script, fetch_script, collector, tmproot):
    failures = []
    for sc in STAGING_SCENARIOS:
        tag = f"[staging: {sc['name']}]"
        helper, rc, status, untrusted = run_staging(
            stage_script, fetch_script, sc, tmproot)
        if "expect_helper" in sc:
            # (rc, result, jobs.json, reason.txt[, .log files left]); None
            # means the output is absent, UNCHECKED leaves that slot alone.
            if any(w is not UNCHECKED and g != w
                   for g, w in zip(helper, sc["expect_helper"])):
                failures.append(f"{tag} helper (rc, result, jobs.json, "
                                f"reason.txt, logs) {helper!r} does not match "
                                f"the expectation.")
        if rc != 0 or status is None or not isinstance(untrusted, list):
            failures.append(f"{tag} the step exited {rc} or left an "
                            f"unreadable status or untrusted-collectors "
                            f"file.")
            continue
        if status.get("outcome") != sc["expect_outcome"] or (
                sc["expect_reason"] is not UNCHECKED
                and status.get("reason") != sc["expect_reason"]):
            failures.append(
                f"{tag} status outcome/reason {status.get('outcome')!r}/"
                f"{status.get('reason')!r}, expected "
                f"{sc['expect_outcome']!r}/{sc['expect_reason']!r} (FR-019).")
        want_untrusted = sc["expect_outcome"] != "ok"
        if ("job-logs" in untrusted) != want_untrusted:
            failures.append(f"{tag} untrusted collectors {untrusted!r}; "
                            f"job-logs expected: {want_untrusted}.")
        got_files = {j["id"]: j["file"] is not None
                     for j in status.get("jobs") or []}
        if sc["expect_files"] is not UNCHECKED and got_files != sc["expect_files"]:
            failures.append(f"{tag} staged jobs {got_files!r}, expected "
                            f"{sc['expect_files']!r}.")

    # The collector reads the same helper: an unparseable listing must
    # record collect-step-summary as failed, not as a trusted "no sentinels".
    tag = "[collector: a listing jq -s cannot parse is a failed read]"
    script, env = collector
    _rc, _out, _sig, outcomes = run_collector(
        script, env, tmproot, UNREADABLE_LISTING, raw=True, fetch=fetch_script)
    got = [o.get("outcome") for o in outcomes or []
           if isinstance(o, dict) and o.get("collector") == "collect-step-summary"]
    if got != ["failed"]:
        failures.append(f"{tag} collect-step-summary outcome(s) {got!r}, "
                        f"expected ['failed'] (FR-019).")
    tag = "[collector: a job log that cannot be read is a failed read]"
    rc, _out, _sig, outcomes = run_collector(
        script, env, tmproot, json.dumps({"jobs": FAILED_JOBS}), fetch=fetch_script,
        logs={901: None})
    got = [o.get("outcome") for o in outcomes or []
           if isinstance(o, dict) and o.get("collector") == "collect-step-summary"]
    if rc != 0 or got != ["failed"]:
        failures.append(f"{tag} collector rc {rc}, collect-step-summary outcome(s) "
                        f"{got!r}, expected rc 0 and ['failed'] (FR-019).")
    tag = "[collector: a helper that died is a failed read]"
    rc, _out, _sig, outcomes = run_collector(
        script, env, tmproot, json.dumps({"jobs": FAILED_JOBS}), fetch=fetch_script,
        crash_jq=True)
    got = [o.get("outcome") for o in outcomes or []
           if isinstance(o, dict) and o.get("collector") == "collect-step-summary"]
    if rc != 0 or got != ["failed"]:
        failures.append(f"{tag} collect-step-summary outcome(s) {got!r}, "
                        f"expected ['failed'] (FR-019).")
    return failures


def mut_stage_no_type_guard(script):
    """Read any JSON jq can iterate as a job list."""
    return script.replace(
        """jq -r 'if type == "array" then .[] else error("not a job list") end | if type == "object" then . else error("not a job") end | select(""",
        """jq -r '.[] | select(""")


def mut_stage_trust_dead_helper(script):
    """Read a helper that set no result as if it had finished."""
    return script.replace(
        '[ "$fetch_out" = "ok" ] || [ "$fetch_reason" = "log-read" ] || { outcome="failed"; reason="fetch-incomplete"; }',
        ":")


def mut_collect_unguarded_jobs_read(script):
    """Let a missing jobs.json end the collector under `bash -e`."""
    return script.replace('2>/dev/null)" || jobs_json=""', '2>/dev/null)"')


def mut_collect_unguarded_log_read(script):
    """Let a missing log file end the collector under `bash -e`."""
    return script.replace('2>/dev/null)" || log=""', '2>/dev/null)"')


def mut_collect_trust_dead_helper(script):
    """Default a missing helper result to ok in the collector."""
    return script.replace('fetch_out="${FETCH_RESULT:-failed}"', 'fetch_out="${FETCH_RESULT:-ok}"')


def mut_fetch_log_in_place(script):
    """Stream each log straight into place, not through a temp file."""
    return script.replace('/logs" > "$OUT_DIR/$id.log.tmp"', '/logs" > "$OUT_DIR/$id.log"').replace(
        '[ ! -s "$OUT_DIR/$id.log.tmp" ] \\\n                || ! mv "$OUT_DIR/$id.log.tmp" "$OUT_DIR/$id.log"',
        '[ ! -s "$OUT_DIR/$id.log" ]')


def mut_stage_unchecked_read(script):
    """Pick the failed jobs with the read's status ignored again (the bug)."""
    return script.replace(
        """"$fetch_dir/jobs.json" 2>/dev/null)"; then""",
        """"$fetch_dir/jobs.json" 2>/dev/null || true)"; then""")


def mut_fetch_no_listing_check(script):
    """Trust gh's exit status alone, so a jq parse failure reads as [] ok
    (the shipped bug)."""
    return script.replace(
        """> "$OUT_DIR/jobs.json.tmp" || jobs_rc=$?""",
        '> "$OUT_DIR/jobs.json.tmp" || jobs_rc="${PIPESTATUS[0]}"')


def mut_fetch_jq_status_only(script):
    """Keep jq's status and lose gh's, so a gh failure after a parseable
    page reads as a complete listing."""
    return script.replace(
        """> "$OUT_DIR/jobs.json.tmp" || jobs_rc=$?""",
        '> "$OUT_DIR/jobs.json.tmp" || jobs_rc="${PIPESTATUS[1]}"')


def mut_fetch_keep_stale(script):
    """Leave an earlier run's jobs.json in place at the start."""
    return script.replace('rm -f "$OUT_DIR/reason.txt" "$OUT_DIR/jobs.json" ',
                          'rm -f "$OUT_DIR/reason.txt" ')


def mut_fetch_unchecked_move(script):
    """Ignore a failed move of jobs.json into place."""
    return script.replace(' || jobs_rc="move"', "")


def mut_fetch_direct_write(script):
    """Write the listing straight into jobs.json, not through a temp file."""
    return script.replace(
        '\'.\' > "$OUT_DIR/jobs.json.tmp" || jobs_rc=$?',
        '\'.\' > "$OUT_DIR/jobs.json" || jobs_rc=$?\n'
        '          cp "$OUT_DIR/jobs.json" "$OUT_DIR/jobs.json.tmp"')


STAGING_MUTATIONS = [
    ("staging reading an unreadable jobs.json unchecked", "stage",
     mut_stage_unchecked_read),
    ("staging reading any iterable JSON as a job list", "stage",
     mut_stage_no_type_guard),
    ("staging trusting a helper that set no result", "stage",
     mut_stage_trust_dead_helper),
    ("the collector trusting a helper that set no result", "collect",
     mut_collect_trust_dead_helper),
    ("the collector dying on a missing log", "collect", mut_collect_unguarded_log_read),
    ("the collector dying on a missing jobs.json", "collect",
     mut_collect_unguarded_jobs_read),
    ("the helper streaming a log straight into place", "fetch", mut_fetch_log_in_place),
    ("the helper accepting an unparseable listing", "fetch",
     mut_fetch_no_listing_check),
    ("the helper ignoring gh's own listing status", "fetch",
     mut_fetch_jq_status_only),
    ("the helper ignoring a failed move", "fetch", mut_fetch_unchecked_move),
    ("the helper keeping an earlier run's jobs.json", "fetch", mut_fetch_keep_stale),
    ("the helper writing jobs.json in place", "fetch", mut_fetch_direct_write),
]


def run_staging_checks(tmproot):
    stage_script = str(find_step(WATCHDOG, STAGE_STEP)["run"])
    fetch_script = shipped_fetch()
    collector = render_step(find_step(WATCHDOG, STEP))
    failures = staging_suite(stage_script, fetch_script, collector, tmproot)
    for f in failures:
        print(f"::error::{f}")
    for label, which, mutate in STAGING_MUTATIONS:
        target = {"stage": stage_script, "fetch": fetch_script,
                  "collect": collector[0]}[which]
        mutated = mutate(target)
        if mutated == target:
            print(f"::error::mutation {label!r} changed nothing -- update it.")
            failures.append(f"mutation inapplicable: {label}")
            continue
        broke = staging_suite(
            mutated if which == "stage" else stage_script,
            mutated if which == "fetch" else fetch_script,
            (mutated, collector[1]) if which == "collect" else collector, tmproot)
        if broke:
            print(f"Mutation OK - {label}: {len(broke)} assertion(s) fail.")
        else:
            print(f"::error::MUTATION SURVIVED - {label} broke nothing.")
            failures.append(f"mutation survived: {label}")
    return failures


def main():
    global BASH
    use_utf8_stdout()
    ensure_jq()
    BASH = resolve_bash()

    step = find_step(WATCHDOG, STEP)
    if step.get("continue-on-error") is not True:
        print(f"::warning file={WATCHDOG}::{STEP!r} no longer carries "
              f"continue-on-error; a collector that can fail the watchdog job "
              f"is a behavior change worth a second look.")
    script, env = render_step(step)

    tmproot = tempfile.mkdtemp()
    try:
        failures = suite(script, env, tmproot)
        for f in failures:
            print(f"::error::{f}")

        for label, mutate in MUTATIONS:
            mutated = mutate(script)
            if mutated == script:
                print(f"::error::mutation {label!r} changed nothing — the code "
                      f"it edits was rewritten. Update the mutation so this "
                      f"harness keeps proving it can fail.")
                failures.append(f"mutation inapplicable: {label}")
                continue
            broke = suite(mutated, env, tmproot)
            if broke:
                print(f"Mutation OK - {label}: {len(broke)} assertion(s) fail.")
            else:
                print(f"::error::MUTATION SURVIVED - reintroducing {label} "
                      f"broke nothing in this suite, so the suite is not "
                      f"testing that defect. Fix the scenarios, not the "
                      f"mutation.")
                failures.append(f"mutation survived: {label}")
        failures += run_staging_checks(tmproot)
    finally:
        shutil.rmtree(tmproot, ignore_errors=True)

    # ASCII only: this also runs on a maintainer's Windows shell, where a
    # cp1252 stdout cannot encode a dash and the gate would die in the print
    # instead of reporting its verdict (same reason as lint-workflows gate 6).
    print(f"sentinel collector: {len(SCENARIOS)} scenario(s), "
          f"{len(STAGING_SCENARIOS)} staging scenario(s); "
          f"{len(failures)} failure(s).")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
