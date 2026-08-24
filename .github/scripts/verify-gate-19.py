#!/usr/bin/env python3
"""Behavioral tests for watchdog.yml's "Collect: annotations" step (Gate 19),
plus failure-injection coverage (T021, T031) for the not-found-vs-other-
failure branches of two neighboring collectors ("Collect: execution-output
artifacts", "Collect: branch drift") and the "Aggregate signals" step
(T022, T030) that folds every collector's read outcome into
untrusted-collectors.

WHY THIS EXISTS
---------------
`gh api ... --paginate` applies whatever `--jq` filter it is given to EACH
page separately and concatenates the raw outputs — it does not slurp first.
Before this feature, the annotation collector's jobs-listing read carried no
`--jq` at all and its annotations read fed a separate `jq -c '[...]']` pass
downstream; both shapes silently drop data once a job has more than one page
of annotations, under `set -uo pipefail` with no `-e`, so the failure never
surfaces as a step failure — it just reads as "nothing to report" (spec
036, issue #182). No harness exercised this step at all before this feature;
`verify-sentinel-collector.py` (Gate 9) covers only its neighbor, "Collect:
step summaries".

This harness EXECUTES the shipped step against synthetic multi-page `gh`
responses, with `gh` stubbed to apply the step's own `--jq` filter to each
page independently and concatenate the results with no added separator —
the same byte shape real `gh --paginate --jq` produces — so a filter that
wraps its result in `[...]` (the T067 defect shape) is caught the same way
it would be caught against the real API. It reads the step out of
watchdog.yml at run time, so there is no second copy to drift (same
discipline as Gate 9).

It ends with a MUTATION check that reintroduces the array-collecting
`--jq '[...]'` shape and asserts the suite then fails to collect the
annotations it should. A test that cannot fail is not a test.

Usage: python3 .github/scripts/verify-gate-19.py
Requires: bash, jq. See wc_shell_harness.py for running this on Windows.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_shell_harness import (  # noqa: E402
    ensure_jq, find_step, resolve_bash, run_step, use_utf8_stdout)

WATCHDOG = ".github/workflows/watchdog.yml"
STEP = "Collect: annotations"

BASH = None

# A `gh` stand-in that applies the step's own --jq filter to each PAGE of a
# fixture independently and concatenates the outputs with no added
# separator — reproducing exactly the byte shape real `gh --paginate --jq`
# emits across more than one page (research.md D4/D5), rather than gh's HTTP
# pagination mechanics, which this stub has no need to simulate.
STUB_GH_TEMPLATE = r'''#!/usr/bin/env bash
p="$2"
d=__FIXTURE_DIR__
jqbin=jq
jqexpr=""
prev=""
for arg in "$@"; do
  if [ "$prev" = "--jq" ]; then jqexpr="$arg"; fi
  prev="$arg"
done
case "$p" in
  */jobs)
    if [ -n "${GH_STUB_FAIL_JOBS:-}" ]; then
      echo "gh: injected failure for jobs listing (GH_STUB_FAIL_JOBS)" >&2
      exit 1
    fi
    pages_file="$d/jobs-pages.json"
    ;;
  */check-runs/*/annotations)
    id="${p#*/check-runs/}"; id="${id%/annotations}"
    if [ -n "${GH_STUB_FAIL_ANNOTATIONS:-}" ] && [ "${GH_STUB_FAIL_ANNOTATIONS}" = "$id" ]; then
      echo "gh: injected failure for annotations of job $id (GH_STUB_FAIL_ANNOTATIONS)" >&2
      exit 1
    fi
    pages_file="$d/anns-pages-$id.json"
    ;;
  *)
    echo "unexpected gh api path: $p" >&2
    exit 1
    ;;
esac
if [ ! -f "$pages_file" ]; then
  echo "no fixture for $p ($pages_file)" >&2
  exit 1
fi
n="$("$jqbin" 'length' "$pages_file")"
i=0
while [ "$i" -lt "$n" ]; do
  page="$("$jqbin" -c ".[$i]" "$pages_file")"
  if [ -n "$jqexpr" ]; then
    printf '%s' "$page" | "$jqbin" -c "$jqexpr"
  else
    printf '%s\n' "$page"
  fi
  i=$((i + 1))
done
'''


def shell_quote(s):
    return "'" + s.replace("'", "'\\''") + "'"


def stub_gh(bindir, fixture_dir):
    path = os.path.join(bindir, "gh")
    content = STUB_GH_TEMPLATE.replace("__FIXTURE_DIR__", shell_quote(fixture_dir))
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(content)
    os.chmod(path, 0o755)


STUB_JQ_TEMPLATE = r'''#!/usr/bin/env bash
# jq's Windows build opens stdout in text mode and terminates each line
# with CRLF. The shipped collector then does
#
#     for job_id in $(printf '%s' "$jobs_json" | jq -r '.[]?.id // empty')
#
# and word-splitting leaves the CR attached, so the next line requests
# `.../check-runs/1<CR>/annotations`, gets nothing back, and every job but
# the last contributes no annotations. On an Actions ubuntu runner jq
# emits LF and the same code is correct - which is why the scenario named
# "no job's annotations displace another's" was reporting a defect the
# shipped collector does not have (#213).
#
# Normalised here rather than by adding a `tr -d` to the shipped shell:
# the collector is not wrong, the local jq is different. `set -o pipefail`
# keeps jq's own exit status visible, which several scenarios assert on.
set -o pipefail
__REAL_JQ__ "$@" | tr -d '\r'
'''


CRLF = bytes((13, 10))
_JQ_EMITS_CRLF = None


def jq_emits_crlf():
    """Does the jq on PATH terminate lines with CRLF? Probed once.

    False on every Actions runner, so CI installs no wrapper and behaves
    exactly as it did before this probe existed - the normalisation is a
    local-machine correction, not a change to what CI tests. It is also
    why the probe is worth doing: wrapping jq unconditionally costs an
    extra bash + tr process per invocation, and this harness makes
    hundreds of them.
    """
    global _JQ_EMITS_CRLF
    if _JQ_EMITS_CRLF is None:
        try:
            out = subprocess.run(["jq", "-r", ".a"],
                                 input=b'{"a":1}',
                                 stdout=subprocess.PIPE,
                                 timeout=30).stdout
        except (OSError, subprocess.SubprocessError):
            out = b""
        _JQ_EMITS_CRLF = CRLF in out
    return _JQ_EMITS_CRLF


def stub_jq(bindir):
    """Put a CRLF-normalising `jq` on PATH ahead of the real one, where
    the local jq needs it. A no-op on LF platforms."""
    if not jq_emits_crlf():
        return
    real = shutil.which("jq")
    if not real:
        sys.exit("::error::verify-gate-19: jq not found on PATH")
    path = os.path.join(bindir, "jq")
    content = STUB_JQ_TEMPLATE.replace(
        "__REAL_JQ__", shell_quote(real.replace(os.sep, "/")))
    with open(path, "w", encoding="utf-8", newline=chr(10)) as fh:
        fh.write(content)
    os.chmod(path, 0o755)

def render_step(step):
    """The step's run: block with its `${{ }}` env wired to fixture values."""
    script = str(step["run"])
    env = {}
    for k, v in (step.get("env") or {}).items():
        v = str(v)
        if "${{" in v:
            v = {"GH_TOKEN": "dummy-token", "ACTIONS_TOKEN": "dummy-actions-token",
                 "RUN_ID": "12345"}.get(k, "")
        env[k] = v
    if "${{" in script:
        sys.exit(f"::error file={WATCHDOG}::the extracted run: block contains a "
                 f"${{{{ }}}} expression this harness does not resolve.")
    return script, env


# --------------------------------------------------------------------------
# Fixture builders. Each "page" is the raw payload gh's real API would return
# for one page: `{"jobs": [...]}` for the jobs endpoint, a bare `[...]` for
# the annotations endpoint.
# --------------------------------------------------------------------------
def jobs_pages(*pages):
    return [{"jobs": list(p)} for p in pages]


def anns_pages(*pages):
    return [list(p) for p in pages]


def job(id_, name, conclusion="success"):
    return {"id": id_, "name": name, "conclusion": conclusion}


def ann(level, message):
    return {"annotation_level": level, "message": message}


# --------------------------------------------------------------------------
# Scenarios: jobs (paged) + per-job annotations (paged) -> the annotation
# {level, message} multiset the step must collect (spec 036's Acceptance
# Scenarios 1-5 and Edge Cases).
# --------------------------------------------------------------------------
SCENARIOS = [
    dict(
        name="one job, annotations spanning two pages: every annotation from "
             "both pages reaches signals.json exactly once",
        jobs=jobs_pages([job(1, "build")]),
        anns={1: anns_pages([ann("warning", "page 1 warning")],
                            [ann("failure", "page 2 failure")])},
        expect=[("warning", "page 1 warning"), ("failure", "page 2 failure")],
        expect_outcome="ok",
    ),
    dict(
        name="evidence gathered by earlier collectors is preserved",
        jobs=jobs_pages([job(1, "build")]),
        anns={1: anns_pages([ann("warning", "only annotation")])},
        existing_signals=[{"source": "step-summary", "class-hint": None,
                            "facts": {"job": "intake", "matched-sentinel": "stalled",
                                      "job-conclusion": "success", "matched-line": "x"}}],
        expect=[("warning", "only annotation")],
        expect_existing_preserved=True,
    ),
    dict(
        name="several jobs, each spanning more than one page: annotations "
             "from every job are present, no job's annotations displace "
             "another's",
        jobs=jobs_pages([job(1, "build"), job(2, "test")]),
        anns={1: anns_pages([ann("warning", "job1 page1")], [ann("warning", "job1 page2")]),
              2: anns_pages([ann("failure", "job2 page1")], [ann("failure", "job2 page2")])},
        expect=[("warning", "job1 page1"), ("warning", "job1 page2"),
                ("failure", "job2 page1"), ("failure", "job2 page2")],
    ),
    dict(
        name="a job with fewer annotations than one page: output identical "
             "to today's pre-fix single-page behavior",
        jobs=jobs_pages([job(1, "build")]),
        anns={1: anns_pages([ann("warning", "single page warning")])},
        expect=[("warning", "single page warning")],
    ),
    dict(
        name="a job with genuinely zero warning/failure annotations: "
             "evidence set unchanged, not reported as a failed read",
        jobs=jobs_pages([job(1, "build")]),
        anns={1: anns_pages([ann("notice", "informational, not warning or failure")])},
        expect=[],
        expect_outcome="ok",
    ),
    dict(
        name="a page boundary landing exactly on the last item: second page "
             "empty, no trailing empty element",
        jobs=jobs_pages([job(1, "build")]),
        anns={1: anns_pages([ann("warning", "last item on page 1")], [])},
        expect=[("warning", "last item on page 1")],
    ),
    dict(
        name="a failed annotations read is distinguishable from an empty "
             "one: collector-outcomes.json records collect-annotations as "
             "failed, not merely an empty signals.json contribution "
             "(FR-010, quickstart.md item 7)",
        jobs=jobs_pages([job(1, "build")]),
        anns={1: anns_pages([ann("warning", "never collected")])},
        extra_env={"GH_STUB_FAIL_ANNOTATIONS": "1"},
        expect=[],
        expect_outcome="failed",
    ),
    # Attribution invariant (spec 024 FR-026): a job that itself never ran
    # owes no annotation signal, even if sibling jobs in the same run did.
    # A real annotations fixture is seeded for the skipped/cancelled job so
    # that, if the per-job guard is ever removed, its content would surface
    # in `entries` and this scenario's `expect` assertion would catch it —
    # an absent fixture would only prove the guard by accident (an
    # unrelated "no fixture" error), which is not the same claim.
    dict(
        name="a sibling job is skipped: its annotations are never fetched (FR-026)",
        jobs=jobs_pages([job(1, "build"), job(2, "cleanup", conclusion="skipped")]),
        anns={1: anns_pages([ann("warning", "job1 warning")]),
              2: anns_pages([ann("failure", "should never be collected")])},
        expect=[("warning", "job1 warning")],
        expect_outcome="ok",
    ),
    dict(
        name="a sibling job is cancelled: its annotations are never fetched (FR-026)",
        jobs=jobs_pages([job(1, "build"), job(2, "cleanup", conclusion="cancelled")]),
        anns={1: anns_pages([ann("warning", "job1 warning")]),
              2: anns_pages([ann("failure", "should never be collected")])},
        expect=[("warning", "job1 warning")],
        expect_outcome="ok",
    ),
]


def write_fixtures(fixture_dir, jobs, anns):
    with open(os.path.join(fixture_dir, "jobs-pages.json"), "w", encoding="utf-8") as fh:
        json.dump(jobs, fh)
    for job_id, pages in anns.items():
        with open(os.path.join(fixture_dir, f"anns-pages-{job_id}.json"),
                  "w", encoding="utf-8") as fh:
            json.dump(pages, fh)


# Environment variables the Actions runner exports into every step, which a
# shipped `run:` block therefore reads without declaring in its own `env:`.
# Outside CI nothing exports them, so under `set -u` the step aborts on its
# first line and the scenario asserts nothing about the code it names - it
# only proves that an unbound variable stops bash. Two of the three suites
# here had exactly that hole: `run_one` compensated by hand and the other two
# did not, so the execution-output scenarios passed in CI only because the
# real runner leaked GITHUB_REPOSITORY in, and failed everywhere else (#213).
#
# Seeded in ONE place so a fourth suite cannot reintroduce the gap by
# forgetting, and seeded rather than inherited so a green run means the same
# thing on a maintainer's machine as it does on a runner.
ACTIONS_DEFAULT_ENV = {
    "GITHUB_REPOSITORY": "charlesguse/wing-commander",
}


def with_actions_defaults(env):
    """Base env plus the runner-provided defaults, without clobbering the
    step's own declared values."""
    out = dict(ACTIONS_DEFAULT_ENV)
    out.update(env)
    return out


def run_one(script, env, sc, tmproot):
    """Execute the collector against one fixture; return (rc, out, signals,
    outcomes) — outcomes is the parsed collector-outcomes.json, the same
    accumulate-and-merge file every collector in watchdog.yml's `collect`
    job writes to (T016), pre-seeded here the way "Initialize
    collector-outcomes file" does in the real job."""
    workdir = tempfile.mkdtemp(dir=tmproot)
    runner_temp = tempfile.mkdtemp(dir=tmproot)
    fixtures = tempfile.mkdtemp(dir=tmproot)
    bindir = tempfile.mkdtemp(dir=tmproot)

    with open(os.path.join(runner_temp, "signals.json"), "w", encoding="utf-8") as fh:
        json.dump(sc.get("existing_signals", []), fh)
    with open(os.path.join(runner_temp, "collector-outcomes.json"), "w",
              encoding="utf-8") as fh:
        fh.write("[]")
    write_fixtures(fixtures, sc["jobs"], sc["anns"])
    stub_gh(bindir, fixtures.replace("\\", "/"))
    stub_jq(bindir)

    env = with_actions_defaults(env)
    env["PATH"] = bindir + os.pathsep + os.environ["PATH"]
    for k, v in (sc.get("extra_env") or {}).items():
        env[k] = v

    rc, out, _, _ = run_step(BASH, script, workdir, env, runner_temp)
    with open(os.path.join(runner_temp, "signals.json"), encoding="utf-8") as fh:
        signals = json.load(fh)
    with open(os.path.join(runner_temp, "collector-outcomes.json"), encoding="utf-8") as fh:
        outcomes = json.load(fh)
    for d in (workdir, runner_temp, fixtures, bindir):
        shutil.rmtree(d, ignore_errors=True)
    return rc, out, signals, outcomes


def suite(script, env, tmproot):
    failures = []
    for sc in SCENARIOS:
        tag = f"[{sc['name']}]"
        rc, out, signals, outcomes = run_one(script, env, sc, tmproot)
        if rc != 0:
            failures.append(f"{tag} the collector exited {rc}:\n{out}")
            continue

        if sc.get("expect_existing_preserved"):
            for e in sc.get("existing_signals", []):
                if e not in signals:
                    failures.append(
                        f"{tag} evidence already gathered by an earlier "
                        f"collector was lost: {e}")

        got = sorted((s["facts"]["level"], s["facts"]["message"])
                     for s in signals
                     if isinstance(s, dict) and s.get("source") == "annotations")
        want = sorted(sc["expect"])
        if got != want:
            failures.append(
                f"{tag} wrong annotations collected.\n"
                f"    expected: {want or '(none)'}\n"
                f"    actual:   {got or '(none)'}")

        expect_outcome = sc.get("expect_outcome")
        if expect_outcome is not None:
            entries = [o for o in outcomes
                      if isinstance(o, dict) and o.get("collector") == "collect-annotations"]
            got_outcome = entries[-1].get("outcome") if entries else None
            if got_outcome != expect_outcome:
                failures.append(
                    f"{tag} collector-outcomes.json for collect-annotations "
                    f"reads {got_outcome!r}, expected {expect_outcome!r} "
                    f"(FR-010: a failed read must be distinguishable from an "
                    f"empty one, not merely absent from signals.json). "
                    f"outcomes: {outcomes}")
    return failures


# --------------------------------------------------------------------------
# Mutations
# --------------------------------------------------------------------------
def strip_conclusion_guard(script, var_name):
    """Remove a `case "$var_name" in ... esac` attribution-invariant guard
    (spec 024 FR-026), whatever body it wraps. Used as a mutation to prove
    each suite below actually detects the guard's absence, rather than
    passing regardless of whether it ships (Constitution VIII). A regex
    rather than a literal string match: the guard's body text (the
    ::warning:: message) differs per collector, only the case/esac shape
    it shares does not.
    """
    pattern = re.compile(r'case "\$' + re.escape(var_name) + r'" in\b.*?\n[ \t]*esac\n',
                          re.DOTALL)
    new = pattern.sub("", script, count=1)
    if new == script:
        sys.exit(f"::error::verify-gate-19: could not locate the {var_name!r} "
                  f"attribution guard to mutate — the step text may have "
                  f"changed shape; update this harness alongside it.")
    return new


def mut_array_collecting_annotations(script):
    """Reintroduce the array-collecting --jq '[...]' shape (the T067 defect):
    wrapping the per-item filter in [...] makes gh emit one ARRAY per page
    under --paginate, instead of one value per line."""
    old = ('--jq \'.[] | select(.annotation_level=="warning" or '
           '.annotation_level=="failure") | {source:"annotations",'
           '"class-hint":null,facts:{level:.annotation_level,message:.message}}\'')
    new = ('--jq \'[.[] | select(.annotation_level=="warning" or '
           '.annotation_level=="failure") | {source:"annotations",'
           '"class-hint":null,facts:{level:.annotation_level,message:.message}}]\'')
    return script.replace(old, new)


def mut_annotations_attribution_guard(script):
    return strip_conclusion_guard(script, "job_conclusion")


MUTATIONS = [
    ("the annotations filter collecting results into an array per page",
     mut_array_collecting_annotations),
    ("the annotations collector's per-job attribution guard (FR-026)",
     mut_annotations_attribution_guard),
]


# --------------------------------------------------------------------------
# T031: failure-injection coverage for the two collectors whose not-found-
# vs-other-failure branch (T029) nothing previously executed —
# `collect-execution-output`'s `gh run download` and `collect-branch-drift`'s
# `git fetch`. Gate 19 already injects a read failure into
# `collect-annotations`; these two branches were desk-read only, the same
# "a verifier nothing runs is not a verifier" shape Gate 5/9 exist to
# prevent, and the T029 bug (a `no valid artifacts` phrasing that fell
# through the old `grep -qi "no artifact"` check) would have been caught
# here.
# --------------------------------------------------------------------------
EXEC_STEP = "Collect: execution-output artifacts"
BD_STEP = "Collect: branch drift"

STUB_GH_DOWNLOAD_TEMPLATE = r'''#!/usr/bin/env bash
if [ "$1" = "run" ] && [ "$2" = "download" ]; then
  if [ -n "${GH_STUB_DOWNLOAD_FAIL:-}" ]; then
    printf '%s\n' __MSG__ >&2
    exit 1
  fi
  exit 0
fi
echo "unexpected gh invocation: $*" >&2
exit 1
'''

STUB_GIT_TEMPLATE = r'''#!/usr/bin/env bash
case "$1" in
  fetch)
    if [ -n "${GIT_STUB_FETCH_FAIL:-}" ]; then
      printf '%s\n' __MSG__ >&2
      exit 1
    fi
    exit 0
    ;;
  rev-parse)
    if [ -n "${GIT_STUB_REVPARSE_FAIL:-}" ]; then
      echo "fatal: injected rev-parse failure" >&2
      exit 1
    fi
    echo "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef"
    exit 0
    ;;
  rev-list)
    if [ -n "${GIT_STUB_REVLIST_FAIL:-}" ]; then
      echo "fatal: injected rev-list failure" >&2
      exit 1
    fi
    echo "${GIT_STUB_REVLIST_COUNT:-0}"
    exit 0
    ;;
esac
exit 1
'''


def stub_bin(bindir, name, template, msg):
    path = os.path.join(bindir, name)
    content = template.replace("__MSG__", shell_quote(msg))
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(content)
    os.chmod(path, 0o755)


EXEC_SCENARIOS = [
    dict(
        name="gh's 'no artifact matches' phrasing: a genuine not-found is ok",
        fail=True,
        msg="gh: no artifact matches any of the names or patterns provided",
        expect_outcome="ok",
    ),
    dict(
        name="gh's 'no valid artifacts found to download' phrasing "
             "(T029): a genuine not-found is ok even though it contains "
             "no 'no artifact' substring",
        fail=True,
        msg="gh: no valid artifacts found to download",
        expect_outcome="ok",
    ),
    dict(
        name="a permission/network-flavored download failure is failed",
        fail=True,
        msg="gh: HTTP 403: Resource not accessible by integration",
        expect_outcome="failed",
    ),
    # Attribution invariant (spec 024 FR-026): a run that skipped or was
    # cancelled executed nothing, so no denial artifact is attributable to
    # it — the step must exit before ever attempting the download, which
    # shows up here as NO collect-execution-output entry at all (the outcome
    # append line sits after the download attempt), not as an "ok" entry.
    dict(
        name="run conclusion skipped: nothing executed, no download attempted (FR-026)",
        fail=False,
        msg="",
        run_conclusion="skipped",
        expect_outcome=None,
    ),
    dict(
        name="run conclusion cancelled: nothing executed, no download attempted (FR-026)",
        fail=False,
        msg="",
        run_conclusion="cancelled",
        expect_outcome=None,
    ),
]

BD_SCENARIOS = [
    dict(
        name="branch already torn down: a genuine not-found is ok",
        fetch_fail=True,
        fetch_msg="fatal: couldn't find remote ref refs/heads/spec/999-torn-down",
        revparse_fail=True,
        revlist_fail=False,
        expect_outcome="ok",
    ),
    dict(
        name="a permission/network-flavored fetch failure is failed",
        fetch_fail=True,
        fetch_msg="fatal: unable to access 'https://github.com/...': Could not "
                  "resolve host",
        revparse_fail=True,
        revlist_fail=False,
        expect_outcome="failed",
    ),
    dict(
        name="fetch succeeds but rev-parse unexpectedly fails: not the "
             "torn-down case, so the read is untrusted (T032)",
        fetch_fail=False,
        fetch_msg="",
        revparse_fail=True,
        revlist_fail=False,
        expect_outcome="failed",
    ),
    dict(
        name="fetch and rev-parse succeed but rev-list unexpectedly fails "
             "(T032)",
        fetch_fail=False,
        fetch_msg="",
        revparse_fail=False,
        revlist_fail=True,
        expect_outcome="failed",
    ),
    dict(
        name="every read succeeds: outcome is ok (FR-005/SC-007 baseline)",
        fetch_fail=False,
        fetch_msg="",
        revparse_fail=False,
        revlist_fail=False,
        expect_outcome="ok",
    ),
    # Attribution invariant (spec 024 FR-026): a run that skipped or was
    # cancelled executed nothing, so "this stage should have pushed
    # commits" was never in force — the step must exit before ever fetching
    # the branch, which shows up here as NO collect-branch-drift entry at
    # all (the outcome append lines all sit after the fetch), not "ok".
    dict(
        name="run conclusion skipped: nothing executed, no fetch attempted (FR-026)",
        run_conclusion="skipped",
        fetch_fail=False,
        fetch_msg="",
        revparse_fail=False,
        revlist_fail=False,
        expect_outcome=None,
    ),
    dict(
        name="run conclusion cancelled: nothing executed, no fetch attempted (FR-026)",
        run_conclusion="cancelled",
        fetch_fail=False,
        fetch_msg="",
        revparse_fail=False,
        revlist_fail=False,
        expect_outcome=None,
    ),
]


def last_outcome(outcomes, collector):
    entries = [o for o in outcomes
               if isinstance(o, dict) and o.get("collector") == collector]
    return entries[-1].get("outcome") if entries else None


def run_exec_one(script, env, sc, tmproot):
    workdir = tempfile.mkdtemp(dir=tmproot)
    runner_temp = tempfile.mkdtemp(dir=tmproot)
    bindir = tempfile.mkdtemp(dir=tmproot)

    with open(os.path.join(runner_temp, "collector-outcomes.json"), "w",
              encoding="utf-8") as fh:
        fh.write("[]")
    with open(os.path.join(runner_temp, "signals.json"), "w", encoding="utf-8") as fh:
        fh.write("[]")
    stub_bin(bindir, "gh", STUB_GH_DOWNLOAD_TEMPLATE, sc["msg"])
    stub_jq(bindir)

    run_env = with_actions_defaults(env)
    run_env["PATH"] = bindir + os.pathsep + os.environ["PATH"]
    run_env["RUN_CONCLUSION"] = sc.get("run_conclusion", "success")
    if sc["fail"]:
        run_env["GH_STUB_DOWNLOAD_FAIL"] = "1"

    rc, out, _, _ = run_step(BASH, script, workdir, run_env, runner_temp)
    with open(os.path.join(runner_temp, "collector-outcomes.json"), encoding="utf-8") as fh:
        outcomes = json.load(fh)
    for d in (workdir, runner_temp, bindir):
        shutil.rmtree(d, ignore_errors=True)
    return rc, out, outcomes


def suite_exec(script, env, tmproot):
    failures = []
    for sc in EXEC_SCENARIOS:
        tag = f"[execution-output: {sc['name']}]"
        rc, out, outcomes = run_exec_one(script, env, sc, tmproot)
        if rc != 0:
            failures.append(f"{tag} the collector exited {rc}:\n{out}")
            continue
        got = last_outcome(outcomes, "collect-execution-output")
        if got != sc["expect_outcome"]:
            failures.append(
                f"{tag} collector-outcomes.json for collect-execution-output "
                f"reads {got!r}, expected {sc['expect_outcome']!r} (FR-010). "
                f"outcomes: {outcomes}")
    return failures


def run_bd_one(script, env, sc, tmproot):
    workdir = tempfile.mkdtemp(dir=tmproot)
    runner_temp = tempfile.mkdtemp(dir=tmproot)
    bindir = tempfile.mkdtemp(dir=tmproot)

    with open(os.path.join(runner_temp, "collector-outcomes.json"), "w",
              encoding="utf-8") as fh:
        fh.write("[]")
    with open(os.path.join(runner_temp, "signals.json"), "w", encoding="utf-8") as fh:
        fh.write("[]")
    stub_bin(bindir, "git", STUB_GIT_TEMPLATE, sc["fetch_msg"])
    stub_jq(bindir)

    run_env = with_actions_defaults(env)
    run_env["PATH"] = bindir + os.pathsep + os.environ["PATH"]
    run_env["RUN_NAME"] = "Wing Commander · 5 implement"
    run_env["RUN_CONCLUSION"] = sc.get("run_conclusion", "success")
    run_env["HEAD_BRANCH"] = "spec/999-torn-down"
    run_env["HEAD_SHA"] = "0000000000000000000000000000000000000000"
    run_env["SLUG"] = ""
    run_env["META_STAGE"] = ""
    run_env["STALLED_LABEL"] = "false"
    run_env["SPEC_PREFIX"] = "spec/"
    if sc["fetch_fail"]:
        run_env["GIT_STUB_FETCH_FAIL"] = "1"
    if sc["revparse_fail"]:
        run_env["GIT_STUB_REVPARSE_FAIL"] = "1"
    if sc["revlist_fail"]:
        run_env["GIT_STUB_REVLIST_FAIL"] = "1"

    rc, out, _, _ = run_step(BASH, script, workdir, run_env, runner_temp)
    with open(os.path.join(runner_temp, "collector-outcomes.json"), encoding="utf-8") as fh:
        outcomes = json.load(fh)
    for d in (workdir, runner_temp, bindir):
        shutil.rmtree(d, ignore_errors=True)
    return rc, out, outcomes


def suite_bd(script, env, tmproot):
    failures = []
    for sc in BD_SCENARIOS:
        tag = f"[branch-drift: {sc['name']}]"
        rc, out, outcomes = run_bd_one(script, env, sc, tmproot)
        if rc != 0:
            failures.append(f"{tag} the collector exited {rc}:\n{out}")
            continue
        got = last_outcome(outcomes, "collect-branch-drift")
        if got != sc["expect_outcome"]:
            failures.append(
                f"{tag} collector-outcomes.json for collect-branch-drift "
                f"reads {got!r}, expected {sc['expect_outcome']!r} (FR-010). "
                f"outcomes: {outcomes}")
    return failures


# --------------------------------------------------------------------------
# Attribution invariant (spec 024 FR-026), the two collectors above and
# `collect-annotations` shared code fixtures for; these two do not fit that
# shape (no gh/git subprocess to stub) and previously had no coverage at
# all — the gap the maintainer feedback on PR #240 named directly:
# `collect-spec-meta` (RUN_CONCLUSION-gated, no external read) and
# `collect-step-summary` (job_conclusion-gated, per job, like annotations
# but reading job LOGS rather than the annotations endpoint).
# --------------------------------------------------------------------------
SPEC_META_STEP = "Collect: spec-meta state vs. expected stage"

SPEC_META_SCENARIOS = [
    dict(
        name="run executed and the recorded stage disagrees with expected: "
             "a stage-mismatch signal is emitted",
        run_conclusion="success",
        run_name="Wing Commander · 3 plan",
        meta_stage="spec",
        slug="024-watchdog-precision-hardening",
        expect_signal=True,
    ),
    dict(
        name="run executed and the recorded stage matches: no signal",
        run_conclusion="success",
        run_name="Wing Commander · 3 plan",
        meta_stage="plan",
        slug="024-watchdog-precision-hardening",
        expect_signal=False,
    ),
    dict(
        name="run conclusion skipped: the stage never ran, so a would-be "
             "mismatch is not attributable to it (FR-026, issue #125)",
        run_conclusion="skipped",
        run_name="Wing Commander · 3 plan",
        meta_stage="spec",
        slug="024-watchdog-precision-hardening",
        expect_signal=False,
    ),
    dict(
        name="run conclusion cancelled: the stage never ran (FR-026)",
        run_conclusion="cancelled",
        run_name="Wing Commander · 3 plan",
        meta_stage="spec",
        slug="024-watchdog-precision-hardening",
        expect_signal=False,
    ),
]


def run_spec_meta_one(script, env, sc, tmproot):
    workdir = tempfile.mkdtemp(dir=tmproot)
    runner_temp = tempfile.mkdtemp(dir=tmproot)
    with open(os.path.join(runner_temp, "collector-outcomes.json"), "w",
              encoding="utf-8") as fh:
        fh.write("[]")
    with open(os.path.join(runner_temp, "signals.json"), "w", encoding="utf-8") as fh:
        fh.write("[]")

    run_env = dict(env)
    run_env["RUN_NAME"] = sc["run_name"]
    run_env["RUN_CONCLUSION"] = sc["run_conclusion"]
    run_env["META_STAGE"] = sc["meta_stage"]
    run_env["SLUG"] = sc["slug"]

    rc, out, _, _ = run_step(BASH, script, workdir, run_env, runner_temp)
    with open(os.path.join(runner_temp, "signals.json"), encoding="utf-8") as fh:
        signals = json.load(fh)
    for d in (workdir, runner_temp):
        shutil.rmtree(d, ignore_errors=True)
    return rc, out, signals


def suite_spec_meta(script, env, tmproot):
    failures = []
    for sc in SPEC_META_SCENARIOS:
        tag = f"[spec-meta: {sc['name']}]"
        rc, out, signals = run_spec_meta_one(script, env, sc, tmproot)
        if rc != 0:
            failures.append(f"{tag} the collector exited {rc}:\n{out}")
            continue
        got_signal = any(isinstance(s, dict) and s.get("source") == "spec-meta"
                          for s in signals)
        if got_signal != sc["expect_signal"]:
            failures.append(
                f"{tag} spec-meta signal present={got_signal}, expected "
                f"{sc['expect_signal']} (FR-026 attribution invariant). "
                f"signals: {signals}")
    return failures


STEPSUM_STEP = "Collect: step summaries"

# Single-page fixtures only — pagination itself is already proven for this
# same jobs/logs shape by the annotations suite above; this stub's whole job
# is exercising the per-job attribution guard, not re-proving pagination.
STUB_GH_STEPSUM_TEMPLATE = r'''#!/usr/bin/env bash
p="$2"
d=__FIXTURE_DIR__
case "$p" in
  */jobs)
    if [ -n "${GH_STUB_FAIL_JOBS:-}" ]; then
      echo "gh: injected failure for jobs listing (GH_STUB_FAIL_JOBS)" >&2
      exit 1
    fi
    jq -c '.[]' "$d/jobs.json"
    ;;
  */logs)
    id="${p%/logs}"; id="${id##*/}"
    f="$d/log-$id.txt"
    if [ ! -f "$f" ]; then
      echo "gh: no fixture for job $id log ($f)" >&2
      exit 1
    fi
    cat "$f"
    ;;
  *)
    echo "unexpected gh api path: $p" >&2
    exit 1
    ;;
esac
'''


def stub_stepsum_gh(bindir, fixture_dir):
    path = os.path.join(bindir, "gh")
    content = STUB_GH_STEPSUM_TEMPLATE.replace("__FIXTURE_DIR__", shell_quote(fixture_dir))
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(content)
    os.chmod(path, 0o755)


def write_stepsum_fixtures(fixture_dir, jobs, logs):
    with open(os.path.join(fixture_dir, "jobs.json"), "w", encoding="utf-8") as fh:
        json.dump(jobs, fh)
    for job_id, text in logs.items():
        with open(os.path.join(fixture_dir, f"log-{job_id}.txt"), "w",
                  encoding="utf-8", newline="\n") as fh:
            fh.write(text)


# Attribution invariant (spec 024 FR-026), applied per-job like annotations:
# a job that itself never ran owes no step-summary sentinel, even if sibling
# jobs in the same run did. The skipped/cancelled sibling's log fixture is
# deliberately OMITTED (rather than seeded and asserted absent) so that, if
# the per-job guard is ever removed, fetching it fails on "no fixture" and
# flips this collector's own outcome to "failed" — a second, independent
# tripwire alongside the missing sentinel itself.
STEPSUM_SCENARIOS = [
    dict(
        name="a sibling job is skipped: its log is never fetched, only the "
             "executed job's sentinel is collected (FR-026)",
        jobs=[job(1, "build", conclusion="success"),
              job(2, "cleanup", conclusion="skipped")],
        logs={1: "2026-08-24T00:00:00.0000000Z WC-SENTINEL: stalled - job build stalled\n"},
        expect=[("build", "stalled")],
        expect_outcome="ok",
    ),
    dict(
        name="a sibling job is cancelled: its log is never fetched (FR-026)",
        jobs=[job(1, "build", conclusion="success"),
              job(2, "cleanup", conclusion="cancelled")],
        logs={1: "2026-08-24T00:00:00.0000000Z WC-SENTINEL: stalled - job build stalled\n"},
        expect=[("build", "stalled")],
        expect_outcome="ok",
    ),
]


def run_stepsum_one(script, env, sc, tmproot):
    workdir = tempfile.mkdtemp(dir=tmproot)
    runner_temp = tempfile.mkdtemp(dir=tmproot)
    fixtures = tempfile.mkdtemp(dir=tmproot)
    bindir = tempfile.mkdtemp(dir=tmproot)

    with open(os.path.join(runner_temp, "signals.json"), "w", encoding="utf-8") as fh:
        fh.write("[]")
    with open(os.path.join(runner_temp, "collector-outcomes.json"), "w",
              encoding="utf-8") as fh:
        fh.write("[]")
    write_stepsum_fixtures(fixtures, sc["jobs"], sc["logs"])
    stub_stepsum_gh(bindir, fixtures.replace("\\", "/"))
    stub_jq(bindir)

    run_env = with_actions_defaults(env)
    run_env["PATH"] = bindir + os.pathsep + os.environ["PATH"]

    rc, out, _, _ = run_step(BASH, script, workdir, run_env, runner_temp)
    with open(os.path.join(runner_temp, "signals.json"), encoding="utf-8") as fh:
        signals = json.load(fh)
    with open(os.path.join(runner_temp, "collector-outcomes.json"), encoding="utf-8") as fh:
        outcomes = json.load(fh)
    for d in (workdir, runner_temp, fixtures, bindir):
        shutil.rmtree(d, ignore_errors=True)
    return rc, out, signals, outcomes


def suite_stepsum(script, env, tmproot):
    failures = []
    for sc in STEPSUM_SCENARIOS:
        tag = f"[step-summary: {sc['name']}]"
        rc, out, signals, outcomes = run_stepsum_one(script, env, sc, tmproot)
        if rc != 0:
            failures.append(f"{tag} the collector exited {rc}:\n{out}")
            continue
        got = sorted((s["facts"]["job"], s["facts"]["matched-sentinel"])
                     for s in signals
                     if isinstance(s, dict) and s.get("source") == "step-summary")
        want = sorted(sc["expect"])
        if got != want:
            failures.append(
                f"{tag} wrong step-summary signals collected.\n"
                f"    expected: {want or '(none)'}\n"
                f"    actual:   {got or '(none)'}")
        expect_outcome = sc.get("expect_outcome")
        if expect_outcome is not None:
            got_outcome = last_outcome(outcomes, "collect-step-summary")
            if got_outcome != expect_outcome:
                failures.append(
                    f"{tag} collector-outcomes.json for collect-step-summary "
                    f"reads {got_outcome!r}, expected {expect_outcome!r}. "
                    f"outcomes: {outcomes}")
    return failures


# --------------------------------------------------------------------------
# T022: the `collect` job's "Aggregate signals" step — folds each
# collector's own read-outcome tracking (T016-T017) into the additive
# untrusted-collectors output, without changing collectors-failed or
# evidence-available's existing behavior (contracts/watchdog-read-outcome.md).
# --------------------------------------------------------------------------
AGGREGATE_STEP = "Aggregate signals"
COLLECTOR_IDS = ["collect-execution-output", "collect-branch-drift",
                 "collect-spec-meta", "collect-step-summary",
                 "collect-annotations"]

# Acceptance Scenario 3 requires more than "evidence-available stays true"
# — the successful collectors' own contributions to signals.json must
# survive a partial failure untouched. A representative multi-source set,
# seeded into signals.json before the step runs and asserted to come back
# byte-identical through the "signals" output, is what actually proves that
# half of the scenario (T030).
SIGNALS_FIXTURE = [
    {"source": "annotations", "class-hint": None,
     "facts": {"level": "warning", "message": "deprecated input used"}},
    {"source": "result-record", "class-hint": "denied-tool",
     "facts": {"tool": "Bash", "denials": 2, "denied-commands": ["rm -rf /"]}},
    {"source": "step-summary", "class-hint": None,
     "facts": {"job": "build", "conclusion": "failure"}},
]

AGGREGATE_CASES = [
    dict(
        name="every collector's read succeeded: untrusted-collectors is []",
        why="Acceptance Scenario 4 / FR-005/SC-007 — this is every "
            "historical run, and nothing about this feature may change "
            "its outcome.",
        outcomes=[{"collector": c, "outcome": "ok"} for c in COLLECTOR_IDS],
        step_outcomes={c: "success" for c in COLLECTOR_IDS},
        expect_untrusted=[],
        expect_evidence_available="true",
        expect_signals=SIGNALS_FIXTURE,
    ),
    dict(
        name="one collector's read failed, the other four succeeded",
        why="Acceptance Scenario 3 — untrusted-collectors names exactly the "
            "failed collector, evidence-available stays true (a partial "
            "failure still reaches a verdict), and this is true even though "
            "the failed collector's own STEP outcome is 'success' (T016: "
            "outcome is never derived from the step's overall exit code). "
            "The successful collectors' own evidence in signals.json must "
            "also survive the partial failure unchanged (T030).",
        outcomes=([{"collector": c, "outcome": "ok"} for c in COLLECTOR_IDS
                   if c != "collect-annotations"]
                  + [{"collector": "collect-annotations", "outcome": "failed"}]),
        step_outcomes={c: "success" for c in COLLECTOR_IDS},
        expect_untrusted=["collect-annotations"],
        expect_evidence_available="true",
        expect_signals=SIGNALS_FIXTURE,
    ),
]


def render_aggregate(step, subst):
    """The aggregate step embeds ${{ steps.<id>.outcome }} directly in its
    run: text (no env: block routes it), so it needs its own substitution
    pass — the same EXPR->VALUE convention
    auto-update-spec-kit-tests/subst.py uses."""
    script = str(step["run"])

    def repl(m):
        return subst.get(m.group(1).strip(), "")
    return re.sub(r"\$\{\{(.*?)\}\}", repl, script)


def run_aggregate(outcomes, step_outcomes):
    step = find_step(WATCHDOG, AGGREGATE_STEP)
    subst = {f"steps.{cid}.outcome": val for cid, val in step_outcomes.items()}
    script = render_aggregate(step, subst)
    if "${{" in script:
        sys.exit(f"::error file={WATCHDOG}::verify-gate-19 could not resolve "
                 f"every ${{{{ }}}} expression in the {AGGREGATE_STEP!r} step.")

    workdir = tempfile.mkdtemp()
    runner_temp = tempfile.mkdtemp()
    try:
        with open(os.path.join(runner_temp, "collector-outcomes.json"), "w",
                  encoding="utf-8") as fh:
            json.dump(outcomes, fh)
        with open(os.path.join(runner_temp, "signals.json"), "w", encoding="utf-8") as fh:
            json.dump(SIGNALS_FIXTURE, fh)
        return run_step(BASH, script, workdir, {}, runner_temp)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
        shutil.rmtree(runner_temp, ignore_errors=True)


def run_aggregate_suite():
    failures = []
    for case in AGGREGATE_CASES:
        tag = f"[aggregate: {case['name']}]"
        rc, out, outputs, _ = run_aggregate(case["outcomes"], case["step_outcomes"])
        if rc != 0:
            failures.append(f"{tag} the aggregate step exited {rc}:\n{out}")
            continue
        got_untrusted = json.loads(outputs.get("untrusted-collectors", "null") or "null")
        if got_untrusted != case["expect_untrusted"]:
            failures.append(
                f"{tag} untrusted-collectors = {got_untrusted!r}, expected "
                f"{case['expect_untrusted']!r}. {case['why']}")
        got_avail = outputs.get("evidence-available")
        if got_avail != case["expect_evidence_available"]:
            failures.append(
                f"{tag} evidence-available = {got_avail!r}, expected "
                f"{case['expect_evidence_available']!r}. {case['why']}")
        got_signals = json.loads(outputs.get("signals", "null") or "null")
        if got_signals != case["expect_signals"]:
            failures.append(
                f"{tag} signals = {got_signals!r}, expected the seeded "
                f"fixture to survive unchanged: {case['expect_signals']!r}. "
                f"{case['why']}")
    return failures


def run_attribution_mutation(label, suite_fn, script, env, tmproot, var_name):
    """Common tail for the collectors whose attribution guard (spec 024
    FR-026) is a `case "$var_name" in skipped|cancelled) ... esac` block:
    rerun `suite_fn` with that guard stripped and confirm at least one
    scenario then breaks. A guard with no fixture that exercises its
    removal is not proven to do anything (Constitution VIII)."""
    mutated = strip_conclusion_guard(script, var_name)
    broke = suite_fn(mutated, env, tmproot)
    if broke:
        print(f"Mutation OK - {label}: {len(broke)} assertion(s) fail.")
        return []
    print(f"::error::MUTATION SURVIVED - removing {label} broke nothing "
          f"in this suite, so the suite is not testing that defect.")
    return [f"mutation survived: {label}"]


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
    failures = []
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
    finally:
        shutil.rmtree(tmproot, ignore_errors=True)

    exec_step = find_step(WATCHDOG, EXEC_STEP)
    exec_script, exec_env = render_step(exec_step)
    bd_step = find_step(WATCHDOG, BD_STEP)
    bd_script, bd_env = render_step(bd_step)

    exec_tmproot = tempfile.mkdtemp()
    try:
        exec_failures = suite_exec(exec_script, exec_env, exec_tmproot)
        exec_failures.extend(run_attribution_mutation(
            "execution-output's RUN_CONCLUSION attribution guard (FR-026)",
            suite_exec, exec_script, exec_env, exec_tmproot, "RUN_CONCLUSION"))
    finally:
        shutil.rmtree(exec_tmproot, ignore_errors=True)
    for f in exec_failures:
        print(f"::error::{f}")
    failures.extend(exec_failures)

    bd_tmproot = tempfile.mkdtemp()
    try:
        bd_failures = suite_bd(bd_script, bd_env, bd_tmproot)
        bd_failures.extend(run_attribution_mutation(
            "branch-drift's RUN_CONCLUSION attribution guard (FR-026)",
            suite_bd, bd_script, bd_env, bd_tmproot, "RUN_CONCLUSION"))
    finally:
        shutil.rmtree(bd_tmproot, ignore_errors=True)
    for f in bd_failures:
        print(f"::error::{f}")
    failures.extend(bd_failures)

    spec_meta_step = find_step(WATCHDOG, SPEC_META_STEP)
    spec_meta_script, spec_meta_env = render_step(spec_meta_step)
    spec_meta_tmproot = tempfile.mkdtemp()
    try:
        spec_meta_failures = suite_spec_meta(spec_meta_script, spec_meta_env, spec_meta_tmproot)
        spec_meta_failures.extend(run_attribution_mutation(
            "spec-meta's RUN_CONCLUSION attribution guard (FR-026)",
            suite_spec_meta, spec_meta_script, spec_meta_env, spec_meta_tmproot,
            "RUN_CONCLUSION"))
    finally:
        shutil.rmtree(spec_meta_tmproot, ignore_errors=True)
    for f in spec_meta_failures:
        print(f"::error::{f}")
    failures.extend(spec_meta_failures)

    stepsum_step = find_step(WATCHDOG, STEPSUM_STEP)
    stepsum_script, stepsum_env = render_step(stepsum_step)
    stepsum_tmproot = tempfile.mkdtemp()
    try:
        stepsum_failures = suite_stepsum(stepsum_script, stepsum_env, stepsum_tmproot)
        stepsum_failures.extend(run_attribution_mutation(
            "step-summary's per-job job_conclusion attribution guard (FR-026)",
            suite_stepsum, stepsum_script, stepsum_env, stepsum_tmproot,
            "job_conclusion"))
    finally:
        shutil.rmtree(stepsum_tmproot, ignore_errors=True)
    for f in stepsum_failures:
        print(f"::error::{f}")
    failures.extend(stepsum_failures)

    aggregate_failures = run_aggregate_suite()
    for f in aggregate_failures:
        print(f"::error::{f}")
    failures.extend(aggregate_failures)

    print(f"annotation collector: {len(SCENARIOS)} scenario(s); "
          f"execution-output collector: {len(EXEC_SCENARIOS)} scenario(s); "
          f"branch-drift collector: {len(BD_SCENARIOS)} scenario(s); "
          f"spec-meta collector: {len(SPEC_META_SCENARIOS)} scenario(s); "
          f"step-summary collector: {len(STEPSUM_SCENARIOS)} scenario(s); "
          f"aggregate: {len(AGGREGATE_CASES)} case(s); "
          f"{len(failures)} failure(s).")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
