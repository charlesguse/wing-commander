#!/usr/bin/env python3
"""Behavioral tests for watchdog.yml's "Collect: annotations" step (Gate 19),
plus failure-injection coverage (T021, T031) for the not-found-vs-other-
failure branches of two neighboring collectors ("Collect: execution-output
artifacts", "Collect: branch drift"), the "Aggregate signals" step
(T022, T030) that folds every collector's read outcome into
untrusted-collectors, and (#322) the "Resolve inspected run's spec slug and
lifecycle issue" step's metrics-record fallback that branch-drift's
dispatched-implement measurement depends on. Since #330 that step is the
single step of the wing-commander-inspected-run-identity composite, which
watchdog.yml's collect AND report-unhandled-failure jobs both call; this
harness runs the composite's step, and a SINGLE-HOME check fails if a copy
of the derivation (the branch-prefix case statement) reappears in
watchdog.yml or either job stops calling the composite.

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
# #330: the spec-slug step's one home. Both watchdog jobs `uses:` it.
SPEC_SLUG_ACTION = ".github/actions/wing-commander-inspected-run-identity/action.yml"
SPEC_SLUG_ACTION_USES = "/.github/actions/wing-commander-inspected-run-identity"
SPEC_SLUG_CALLERS = ("collect", "report-unhandled-failure")

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

def render_step(step, path=WATCHDOG):
    """The step's run: block with its `${{ }}` env wired to fixture values.

    `path` names the file the step came from, for the error below — a
    composite's step (SPEC_SLUG_ACTION) is rendered the same way, its
    `${{ inputs.* }}` env entries mapped by key like a workflow's."""
    script = str(step["run"])
    env = {}
    for k, v in (step.get("env") or {}).items():
        v = str(v)
        if "${{" in v:
            v = {"GH_TOKEN": "dummy-token", "ACTIONS_TOKEN": "dummy-actions-token",
                 "RUN_ID": "12345"}.get(k, "")
        env[k] = v
    if "${{" in script:
        sys.exit(f"::error file={path}::the extracted run: block contains a "
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


def reintroduce_slug_hole(script):
    """Put back the #318 defect exactly as it shipped: branch-drift's
    push-target guard read `[ -n "$SLUG" ] && [ "$HEAD_BRANCH" != ... ]`, so
    an EMPTY slug (a dispatch-triggered run whose head is the default
    branch) skipped the guard instead of the measurement, and `main` was
    measured for commits it never owed. The fixed guard is
    `[ -z "$SLUG" ] || [ ... ]`. Mutation for the scenario that exercises it."""
    fixed = 'if [ -z "$SLUG" ] || [ "$HEAD_BRANCH" != '
    broken = 'if [ -n "$SLUG" ] && [ "$HEAD_BRANCH" != '
    if script.count(fixed) != 1:
        sys.exit("::error::verify-gate-19: could not locate branch-drift's "
                 "unresolved-slug guard (#318) to mutate — the step text may "
                 "have changed shape; update this harness alongside it.")
    return script.replace(fixed, broken, 1)


def reintroduce_implement_skip(script):
    """Put back the pre-#322 blind spot: a dispatched implement run (head is
    the default branch, slug recovered from the metrics record) was skipped
    instead of measured on spec/<slug>. The fixed step selects the
    since-created arm where the old one exited; this mutation exits there
    again, so the scenarios that expect spec/<slug> to be fetched and a
    lost-progress signal on zero commits must fail."""
    pattern = re.compile(r'^([ \t]*)baseline="since-created"\n', re.MULTILINE)
    if len(pattern.findall(script)) != 1:
        sys.exit("::error::verify-gate-19: could not locate branch-drift's "
                 "since-created arm (#322) to mutate — the step text may "
                 "have changed shape; update this harness alongside it.")
    return pattern.sub(lambda m: m.group(1) + "exit 0\n", script, count=1)


def run_script_mutation(label, suite_fn, mutated, env, tmproot):
    """Rerun `suite_fn` on an already-mutated script and confirm at least one
    scenario breaks. run_attribution_mutation below is the case/esac-guard
    front end for this; a guard of any other shape mutates itself and calls
    this directly."""
    broke = suite_fn(mutated, env, tmproot)
    if broke:
        print(f"Mutation OK - {label}: {len(broke)} assertion(s) fail.")
        return []
    print(f"::error::MUTATION SURVIVED - removing {label} broke nothing "
          f"in this suite, so the suite is not testing that defect.")
    return [f"mutation survived: {label}"]


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
# Every invocation is appended to $GIT_STUB_LOG (when set) so a scenario can
# assert WHICH ref was fetched and WHICH baseline rev-list was given — the
# #322 arm is distinguishable from the exact-SHA arm only by its arguments.
if [ -n "${GIT_STUB_LOG:-}" ]; then printf '%s\n' "$*" >> "$GIT_STUB_LOG"; fi
case "$1" in
  show)
    # GIT_STUB_SHOW_ONLY_REF (when set) is the one ref that has the file:
    # any other ref answers as a branch with no record would (#376).
    if [ -n "${GIT_STUB_SHOW_ONLY_REF:-}" ]; then
      case "$2" in
        "$GIT_STUB_SHOW_ONLY_REF":*) ;;
        *) echo "fatal: invalid object name (stub)" >&2; exit 128 ;;
      esac
    fi
    if [ -n "${GIT_STUB_SHOW_JSON:-}" ]; then
      printf '%s\n' "$GIT_STUB_SHOW_JSON"
      exit 0
    fi
    echo "fatal: path not in tree (stub)" >&2
    exit 128
    ;;
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
    # #318: a workflow_dispatch-triggered stage reports the default branch
    # as its head and spec-slug resolves nothing from it. The collector
    # measured `main` across implement run 34709026525, found the zero
    # commits main correctly had, and filed lost-progress while the run's
    # sixteen commits sat on spec/045-auto-release-verified-head. An
    # unresolved slug means the head is not a pipeline branch and owes no
    # commits: no fetch, no outcome entry, no signal.
    dict(
        name="no spec slug resolved (dispatch-triggered run, head is the "
             "default branch): the head owes no commits, nothing fetched (#318)",
        head_branch="main",
        slug="",
        fetch_fail=False,
        fetch_msg="",
        revparse_fail=False,
        revlist_fail=False,
        expect_outcome=None,
    ),
    dict(
        name="slug resolved but the head is not the branch this stage pushes "
             "to (draft-branch head, plan run): nothing fetched (#112)",
        run_name="Wing Commander · 3 plan",
        head_branch="spec-draft/999-torn-down",
        slug="999-torn-down",
        fetch_fail=False,
        fetch_msg="",
        revparse_fail=False,
        revlist_fail=False,
        expect_outcome=None,
    ),
    # #322: a dispatched IMPLEMENT run reports the default branch as its
    # head, but spec-slug now recovers the slug from the run's metrics
    # record, and implement pushes unconditionally to spec/<slug> — so
    # that branch is measured, with the run's creation time as the
    # baseline (HEAD_SHA is main's tip and would count the spec branch's
    # whole history). Zero commits since is lost-progress on spec/<slug>.
    dict(
        name="dispatched implement run (head is the default branch, slug "
             "from the metrics record): spec/<slug> is measured since the "
             "run was created; zero commits is lost-progress (#322)",
        head_branch="main",
        slug="999-torn-down",
        fetch_fail=False,
        fetch_msg="",
        revparse_fail=False,
        revlist_fail=False,
        revlist_count="0",
        expect_outcome="ok",
        expect_fetch_ref="refs/heads/spec/999-torn-down",
        expect_since=True,
        expect_signal=dict(branch="spec/999-torn-down", since="2026-09-12T17:42:27Z",
                           **{"before-sha": None}),
    ),
    dict(
        name="dispatched implement run with commits on spec/<slug> since it "
             "was created: measured, no signal (#322)",
        head_branch="main",
        slug="999-torn-down",
        fetch_fail=False,
        fetch_msg="",
        revparse_fail=False,
        revlist_fail=False,
        revlist_count="16",
        expect_outcome="ok",
        expect_fetch_ref="refs/heads/spec/999-torn-down",
        expect_since=True,
        expect_signal=None,
    ),
    # specs/050-branch-drift-sha-baseline: a run's own metrics record
    # already carries the exact before/after/commits it observed — the
    # primary arm, exercised here instead of falling through to
    # since-created. No live branch read backs this baseline (research.md
    # R7/FR-019), so no `expect_fetch_ref`/`expect_since` assertion applies.
    dict(
        name="exact-sha evidence on the run's own metrics record shows "
             "forward progress: baseline is exact-sha, no signal",
        head_branch="main",
        slug="999-exact-sha",
        fetch_fail=False,
        fetch_msg="",
        revparse_fail=False,
        revlist_fail=False,
        gh_records=json.dumps({"branch_advance": {
            "available": True,
            "before_sha": "1111111111111111111111111111111111111a",
            "after_sha": "2222222222222222222222222222222222222b",
            "commits": 5}}),
        expect_outcome="ok",
        expect_signal=None,
    ),
    # The bug specs/050-branch-drift-sha-baseline's spec.md Edge Cases
    # section names directly: a force-push/reset leaves the two recorded
    # points different while the branch went backward, so the recorded
    # commits count is zero. SHA identity alone would call this healthy;
    # the collector must use the recorded count instead (mirrors the
    # since-created arm's own "commits == 0 is lost-progress" rule above).
    dict(
        name="exact-sha evidence shows a backward reset (SHAs differ, "
             "recorded commits is zero): lost-progress, not healthy",
        head_branch="main",
        slug="999-exact-sha",
        fetch_fail=False,
        fetch_msg="",
        revparse_fail=False,
        revlist_fail=False,
        gh_records=json.dumps({"branch_advance": {
            "available": True,
            "before_sha": "2222222222222222222222222222222222222b",
            "after_sha": "1111111111111111111111111111111111111a",
            "commits": 0}}),
        expect_outcome="ok",
        expect_signal=dict(
            branch="spec/999-exact-sha",
            **{"before-sha": "2222222222222222222222222222222222222b",
               "after-sha": "1111111111111111111111111111111111111a",
               "commits": 0}),
    ),
    # Tasks is dispatched too, but pushes to spec/<slug> only in `auto`
    # review mode (pr mode goes to tasks/<slug>), and the record does not
    # say which — so the #322 arm is implement-only and tasks still skips.
    dict(
        name="dispatched tasks run with a recovered slug: the push target "
             "depends on review mode, so nothing is fetched (#322 scope)",
        run_name="Wing Commander · 4 tasks",
        head_branch="main",
        slug="999-torn-down",
        fetch_fail=False,
        fetch_msg="",
        revparse_fail=False,
        revlist_fail=False,
        expect_outcome=None,
    ),
    # The exact-SHA arm is untouched: when the head IS the spec branch the
    # baseline is HEAD_SHA, not the creation time.
    dict(
        name="head is the spec branch: measured against HEAD_SHA, not the "
             "creation time (exact-baseline arm unchanged by #322)",
        head_branch="spec/999-torn-down",
        slug="999-torn-down",
        fetch_fail=False,
        fetch_msg="",
        revparse_fail=False,
        revlist_fail=False,
        revlist_count="0",
        expect_outcome="ok",
        expect_fetch_ref="refs/heads/spec/999-torn-down",
        expect_since=False,
        expect_signal=dict(branch="spec/999-torn-down", since=None,
                           **{"before-sha": "0000000000000000000000000000000000000000"}),
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
    # specs/050-branch-drift-sha-baseline: the exact-sha arm's `gh run
    # download` needs a stub too, or it makes a real, unstubbed network
    # call (reusing the spec-slug step's existing fixture-laying template
    # rather than adding a new one — same `-D`-directory/one-JSON-per-line
    # shape `gh run download` itself produces).
    stub_bin(bindir, "gh", STUB_GH_SPECSLUG_TEMPLATE, "")
    stub_jq(bindir)

    run_env = with_actions_defaults(env)
    run_env["PATH"] = bindir + os.pathsep + os.environ["PATH"]
    run_env["GH_STUB_RECORDS"] = sc.get("gh_records", "")
    run_env["RUN_NAME"] = sc.get("run_name", "Wing Commander · 5 implement")
    run_env["RUN_CONCLUSION"] = sc.get("run_conclusion", "success")
    # The head IS the branch the stage pushes to unless a scenario says
    # otherwise: before #318 the harness ran with SLUG empty, a shape the
    # collector now (correctly) declines to measure at all.
    run_env["HEAD_BRANCH"] = sc.get("head_branch", "spec/999-torn-down")
    run_env["HEAD_SHA"] = "0000000000000000000000000000000000000000"
    # Implement run 34709026525's creation time (#318/#322) — the baseline
    # the since-created arm hands to rev-list.
    run_env["RUN_CREATED_AT"] = "2026-09-12T17:42:27Z"
    run_env["SLUG"] = sc.get("slug", "999-torn-down")
    run_env["META_STAGE"] = ""
    run_env["STALLED_LABEL"] = "false"
    run_env["SPEC_PREFIX"] = "spec/"
    git_log = os.path.join(runner_temp, "git-stub.log")
    run_env["GIT_STUB_LOG"] = git_log.replace("\\", "/")
    if sc["fetch_fail"]:
        run_env["GIT_STUB_FETCH_FAIL"] = "1"
    if sc["revparse_fail"]:
        run_env["GIT_STUB_REVPARSE_FAIL"] = "1"
    if sc["revlist_fail"]:
        run_env["GIT_STUB_REVLIST_FAIL"] = "1"
    if "revlist_count" in sc:
        run_env["GIT_STUB_REVLIST_COUNT"] = sc["revlist_count"]

    rc, out, _, _ = run_step(BASH, script, workdir, run_env, runner_temp)
    with open(os.path.join(runner_temp, "collector-outcomes.json"), encoding="utf-8") as fh:
        outcomes = json.load(fh)
    with open(os.path.join(runner_temp, "signals.json"), encoding="utf-8") as fh:
        signals = json.load(fh)
    git_calls = []
    if os.path.exists(git_log):
        with open(git_log, encoding="utf-8") as fh:
            git_calls = [ln.rstrip("\r\n") for ln in fh if ln.strip()]
    for d in (workdir, runner_temp, bindir):
        shutil.rmtree(d, ignore_errors=True)
    return rc, out, outcomes, signals, git_calls


def suite_bd(script, env, tmproot):
    failures = []
    for sc in BD_SCENARIOS:
        tag = f"[branch-drift: {sc['name']}]"
        rc, out, outcomes, signals, git_calls = run_bd_one(script, env, sc, tmproot)
        if rc != 0:
            failures.append(f"{tag} the collector exited {rc}:\n{out}")
            continue
        got = last_outcome(outcomes, "collect-branch-drift")
        if got != sc["expect_outcome"]:
            failures.append(
                f"{tag} collector-outcomes.json for collect-branch-drift "
                f"reads {got!r}, expected {sc['expect_outcome']!r} (FR-010). "
                f"outcomes: {outcomes}")
        # #322: which ref was measured, and against which baseline. Only
        # asserted where a scenario says; the failure-injection scenarios
        # above care about the outcome record alone.
        if "expect_fetch_ref" in sc:
            fetches = [c for c in git_calls if c.startswith("fetch ")]
            if not any(sc["expect_fetch_ref"] + ":" in c for c in fetches):
                failures.append(
                    f"{tag} expected a fetch of {sc['expect_fetch_ref']!r}; "
                    f"git was invoked as: {git_calls or '(never)'}")
        if "expect_since" in sc:
            revlists = [c for c in git_calls if c.startswith("rev-list ")]
            used_since = any("--since=" in c for c in revlists)
            if used_since != sc["expect_since"]:
                failures.append(
                    f"{tag} rev-list baseline: expected "
                    f"{'--since=<createdAt>' if sc['expect_since'] else 'HEAD_SHA..after'}"
                    f", got: {revlists or '(no rev-list)'}")
        if "expect_signal" in sc:
            bd = [x for x in signals
                  if isinstance(x, dict) and x.get("source") == "branch-drift"]
            want = sc["expect_signal"]
            if want is None:
                if bd:
                    failures.append(f"{tag} expected no branch-drift signal, got {bd}")
            else:
                if len(bd) != 1:
                    failures.append(f"{tag} expected exactly one branch-drift "
                                    f"signal, got {bd}")
                else:
                    facts = bd[0].get("facts") or {}
                    for k, v in want.items():
                        if facts.get(k) != v:
                            failures.append(
                                f"{tag} signal fact {k!r} reads {facts.get(k)!r}, "
                                f"expected {v!r}; facts: {facts}")
                    if bd[0].get("class-hint") != "lost-progress":
                        failures.append(
                            f"{tag} class-hint reads {bd[0].get('class-hint')!r}, "
                            f"expected 'lost-progress'")
    return failures


# --------------------------------------------------------------------------
# #322: the "Resolve inspected run's spec slug and lifecycle issue" step's
# metrics-record fallback. A dispatched run reports the default branch as
# its head, so the head-branch case derives nothing; the step then reads
# spec.spec_dir from the run's metrics-record* artifact(s). Nothing executed
# this step before #322 — it was desk-read only, the "a verifier nothing
# runs is not a verifier" shape Gate 5/9 exist to prevent — and the
# dispatched-implement branch-drift scenarios above are only as good as the
# slug this step hands them.
#
# Since #330 the step lives in the wing-commander-inspected-run-identity
# composite (SPEC_SLUG_ACTION), called by collect with run-meta's head
# branch and by report-unhandled-failure with none — the composite then
# reads the head itself with `gh run view`, so that read is stubbed too.
#
# `gh` is stubbed for `run view` (answers a fixture head branch, or fails),
# `run download` (lays the fixture record out the way gh does:
# <dest>/<artifact-name>/wing-commander-metrics-record.json) and
# `issue view`; `git` for `fetch` (no-op) and `show` (answers from a
# fixture spec-meta.json, or fails as it would for a branch with none).
# --------------------------------------------------------------------------
SPEC_SLUG_STEP = "Resolve inspected run's spec slug and lifecycle issue"

STUB_GH_SPECSLUG_TEMPLATE = r'''#!/usr/bin/env bash
if [ -n "${GH_STUB_LOG:-}" ]; then printf '%s\n' "$*" >> "$GH_STUB_LOG"; fi
if [ "$1" = "run" ] && [ "$2" = "view" ]; then
  if [ -n "${GH_STUB_RUN_VIEW_FAIL:-}" ]; then
    printf '%s\n' "$GH_STUB_RUN_VIEW_FAIL" >&2
    exit 1
  fi
  printf '%s\n' "${GH_STUB_RUN_VIEW_BRANCH:-}"
  exit 0
fi
if [ "$1" = "run" ] && [ "$2" = "download" ]; then
  if [ -n "${GH_STUB_DOWNLOAD_FAIL:-}" ]; then
    printf '%s\n' "$GH_STUB_DOWNLOAD_FAIL" >&2
    exit 1
  fi
  dest=""
  prev=""
  for arg in "$@"; do
    if [ "$prev" = "-D" ]; then dest="$arg"; fi
    prev="$arg"
  done
  [ -n "$dest" ] || { echo "stub gh: no -D given" >&2; exit 1; }
  i=0
  while IFS= read -r rec; do
    [ -n "$rec" ] || continue
    i=$((i + 1))
    mkdir -p "$dest/metrics-record-fixture-$i"
    printf '%s\n' "$rec" > "$dest/metrics-record-fixture-$i/wing-commander-metrics-record.json"
  done <<< "${GH_STUB_RECORDS:-}"
  exit 0
fi
if [ "$1" = "issue" ] && [ "$2" = "view" ]; then
  echo "${GH_STUB_STALLED_LABEL:-false}"
  exit 0
fi
echo "unexpected gh invocation: $*" >&2
exit 1
'''

SPEC_META_FIXTURE = json.dumps({"spec_dir": "specs/045-auto-release-verified-head",
                                "issue": 296, "stage": "implement"})
RECORD_045 = json.dumps({"schema_version": 1, "stage": "implement",
                         "spec": {"spec_dir": "specs/045-auto-release-verified-head",
                                  "issue": 296, "identity_available": True}})
RECORD_046 = json.dumps({"schema_version": 1, "stage": "rebase",
                         "spec": {"spec_dir": "specs/046-watchdog-supervision-collectors",
                                  "issue": 274, "identity_available": True}})
SPEC_META_DRAFT_FIXTURE = json.dumps({"spec_dir": "specs/045-auto-release-verified-head",
                                      "issue": 296, "stage": "spec"})
SPEC_META_OTHER_DIR_FIXTURE = json.dumps({"spec_dir": "specs/001-some-other-spec",
                                          "issue": 7, "stage": "implement"})
DRAFT_REF_045 = "refs/remotes/origin/spec-draft/045-auto-release-verified-head"
RECORD_NO_IDENTITY = json.dumps({"schema_version": 1, "stage": "implement",
                                 "spec": {"spec_dir": None, "issue": None,
                                          "identity_available": False}})

SPEC_SLUG_SCENARIOS = [
    dict(
        name="head is a spec branch: slug from the head, no artifact read",
        head_branch="spec/045-auto-release-verified-head",
        records=[RECORD_045],
        show_json=SPEC_META_FIXTURE,
        expect=dict(slug="045-auto-release-verified-head", **{"slug-source": "head-branch"},
                    **{"spec-dir": "specs/045-auto-release-verified-head",
                       "lifecycle-issue": "296", "meta-stage": "implement"}),
        expect_download=False,
    ),
    dict(
        name="head is the default branch and the run's metrics record names "
             "a spec: slug read from the record (#322)",
        head_branch="main",
        records=[RECORD_045],
        show_json=SPEC_META_FIXTURE,
        expect=dict(slug="045-auto-release-verified-head", **{"slug-source": "metrics-record"},
                    **{"spec-dir": "specs/045-auto-release-verified-head",
                       "lifecycle-issue": "296", "meta-stage": "implement"}),
        expect_download=True,
    ),
    dict(
        name="head is the default branch and a first record carries no spec "
             "identity: the next record that does is used (#322)",
        head_branch="main",
        records=[RECORD_NO_IDENTITY, RECORD_045],
        show_json=SPEC_META_FIXTURE,
        expect=dict(slug="045-auto-release-verified-head", **{"slug-source": "metrics-record"}),
        expect_download=True,
    ),
    dict(
        name="head is the default branch and no record names a spec: no "
             "slug, no issue, step still succeeds",
        head_branch="main",
        records=[RECORD_NO_IDENTITY],
        show_json="",
        expect=dict(slug="", **{"slug-source": "", "spec-dir": "", "lifecycle-issue": "",
                                "meta-stage": ""}),
        expect_download=True,
    ),
    dict(
        name="head is the default branch and the artifact download fails "
             "(expired, or Actions:read missing): no slug, step still "
             "succeeds — best-effort, never a refusal gate",
        head_branch="main",
        records=[],
        download_fail="gh: HTTP 403: Resource not accessible by integration",
        show_json="",
        expect=dict(slug="", **{"slug-source": "", "lifecycle-issue": ""}),
        expect_download=True,
    ),
    # Only the six single-spec stages get the fallback. The watchdog's own
    # diagnose record borrows the INSPECTED run's spec identity, and a
    # rebase run writes one record per matrix slug — "first record wins"
    # would tie either to an arbitrary spec. No download, no slug.
    dict(
        name="a watchdog run with the default-branch head: its record names "
             "the spec it inspected, not one it advanced — no artifact read, "
             "no slug",
        run_name="Wing Commander · 8 watchdog",
        head_branch="main",
        records=[RECORD_045],
        show_json=SPEC_META_FIXTURE,
        expect=dict(slug="", **{"slug-source": "", "lifecycle-issue": ""}),
        expect_download=False,
    ),
    dict(
        name="a rebase run with the default-branch head: one record per "
             "rebased spec, none of them 'the' spec — no artifact read, no slug",
        run_name="Wing Commander · rebase",
        head_branch="main",
        records=[RECORD_045, RECORD_046],
        show_json=SPEC_META_FIXTURE,
        expect=dict(slug="", **{"slug-source": "", "lifecycle-issue": ""}),
        expect_download=False,
    ),
    dict(
        name="a dispatched tasks run: single-spec stage, slug read from the "
             "record like implement",
        run_name="Wing Commander · 4 tasks",
        head_branch="main",
        records=[RECORD_045],
        show_json=SPEC_META_FIXTURE,
        expect=dict(slug="045-auto-release-verified-head", **{"slug-source": "metrics-record",
                                                              "lifecycle-issue": "296"}),
        expect_download=True,
    ),
    dict(
        name="slug from the record but the spec branch has no spec-meta.json: "
             "slug and spec-dir resolve, issue does not",
        head_branch="main",
        records=[RECORD_045],
        show_json="",
        expect=dict(slug="045-auto-release-verified-head", **{"slug-source": "metrics-record"},
                    **{"spec-dir": "specs/045-auto-release-verified-head",
                       "lifecycle-issue": "", "meta-stage": ""}),
        expect_download=True,
    ),
    # #376: a spec still in intake or clarify has no spec branch, only its
    # spec-draft branch. Both stages run off the default branch, so the slug
    # comes from the record and the issue from the DRAFT's spec-meta.json.
    # Before this every intake and clarify run resolved a slug and no issue.
    dict(
        name="an intake run whose spec exists only as a draft: the spec "
             "branch has no record, the spec-draft branch's is used (#376)",
        run_name="Wing Commander · 1 intake",
        head_branch="main",
        records=[RECORD_045],
        show_json=SPEC_META_DRAFT_FIXTURE,
        show_only_ref=DRAFT_REF_045,
        expect=dict(slug="045-auto-release-verified-head", **{"slug-source": "metrics-record"},
                    **{"spec-dir": "specs/045-auto-release-verified-head",
                       "lifecycle-issue": "296", "meta-stage": "spec"}),
        expect_download=True,
        expect_draft_read=True,
    ),
    dict(
        name="a run on a spec-draft head: slug from the head, issue from the "
             "draft's record (#376)",
        run_name="Wing Commander · 2 clarify",
        head_branch="spec-draft/045-auto-release-verified-head",
        records=[RECORD_045],
        show_json=SPEC_META_DRAFT_FIXTURE,
        show_only_ref=DRAFT_REF_045,
        expect=dict(slug="045-auto-release-verified-head", **{"slug-source": "head-branch"},
                    **{"lifecycle-issue": "296", "meta-stage": "spec"}),
        expect_download=False,
        expect_draft_read=True,
    ),
    dict(
        name="the spec branch HAS a record but it identifies another "
             "directory: refused, and the draft is not consulted to paper "
             "over it (#376)",
        head_branch="main",
        records=[RECORD_045],
        show_json=SPEC_META_OTHER_DIR_FIXTURE,
        expect=dict(slug="045-auto-release-verified-head",
                    **{"lifecycle-issue": "", "meta-stage": ""}),
        expect_download=True,
        expect_draft_read=False,
    ),
    # #330: the report-unhandled-failure job hands in no head branch (it has
    # no run-meta step of its own), so the composite reads it with `gh run
    # view` and the rest of the derivation runs unchanged.
    dict(
        name="no head branch handed in (report job): read with gh run view, "
             "slug from the head it answers",
        head_branch="",
        run_view_branch="impl/045-auto-release-verified-head-iter2",
        records=[RECORD_045],
        show_json=SPEC_META_FIXTURE,
        expect=dict(slug="045-auto-release-verified-head", **{"slug-source": "head-branch"},
                    **{"lifecycle-issue": "296", "meta-stage": "implement"}),
        expect_download=False,
        expect_run_view=True,
    ),
    dict(
        name="no head branch handed in and gh run view fails (no token, or "
             "Actions:read missing): the record fallback still runs, step "
             "still succeeds",
        head_branch="",
        run_view_fail="gh: HTTP 403: Resource not accessible by integration",
        records=[RECORD_045],
        show_json=SPEC_META_FIXTURE,
        expect=dict(slug="045-auto-release-verified-head", **{"slug-source": "metrics-record"},
                    **{"lifecycle-issue": "296"}),
        expect_download=True,
        expect_run_view=True,
    ),
    dict(
        name="no head branch handed in, gh run view fails and the stage is not "
             "a single-spec one: nothing resolves, step still succeeds",
        head_branch="",
        run_name="Wing Commander · 8 watchdog",
        run_view_fail="gh: HTTP 403: Resource not accessible by integration",
        records=[RECORD_045],
        show_json=SPEC_META_FIXTURE,
        expect=dict(slug="", **{"slug-source": "", "lifecycle-issue": ""}),
        expect_download=False,
        expect_run_view=True,
    ),
]


def run_spec_slug_one(script, env, sc, tmproot):
    workdir = tempfile.mkdtemp(dir=tmproot)
    runner_temp = tempfile.mkdtemp(dir=tmproot)
    bindir = tempfile.mkdtemp(dir=tmproot)

    gh_path = os.path.join(bindir, "gh")
    with open(gh_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(STUB_GH_SPECSLUG_TEMPLATE)
    os.chmod(gh_path, 0o755)
    stub_bin(bindir, "git", STUB_GIT_TEMPLATE, "")
    stub_jq(bindir)

    run_env = with_actions_defaults(env)
    run_env["PATH"] = bindir + os.pathsep + os.environ["PATH"]
    # The step sources $GITHUB_ACTION_PATH/../_shared/read-spec-meta.sh
    # (#340): point it at the real action directory so the real shared
    # script runs, against the stubbed git and gh on PATH.
    run_env["GITHUB_ACTION_PATH"] = os.path.abspath(
        os.path.dirname(SPEC_SLUG_ACTION)).replace("\\", "/")
    run_env["HEAD_BRANCH"] = sc["head_branch"]
    run_env["RUN_NAME"] = sc.get("run_name", "Wing Commander · 5 implement")
    run_env["GH_STUB_RECORDS"] = "\n".join(sc["records"])
    if sc.get("download_fail"):
        run_env["GH_STUB_DOWNLOAD_FAIL"] = sc["download_fail"]
    if sc.get("run_view_branch"):
        run_env["GH_STUB_RUN_VIEW_BRANCH"] = sc["run_view_branch"]
    if sc.get("run_view_fail"):
        run_env["GH_STUB_RUN_VIEW_FAIL"] = sc["run_view_fail"]
    if sc.get("show_json"):
        run_env["GIT_STUB_SHOW_JSON"] = sc["show_json"]
    if sc.get("show_only_ref"):
        run_env["GIT_STUB_SHOW_ONLY_REF"] = sc["show_only_ref"]
    gh_log = os.path.join(runner_temp, "gh-stub.log")
    run_env["GH_STUB_LOG"] = gh_log.replace("\\", "/")
    git_log = os.path.join(runner_temp, "git-stub.log")
    run_env["GIT_STUB_LOG"] = git_log.replace("\\", "/")

    rc, out, outputs, summary = run_step(BASH, script, workdir, run_env, runner_temp)
    gh_calls = []
    if os.path.exists(gh_log):
        with open(gh_log, encoding="utf-8") as fh:
            gh_calls = [ln.rstrip("\r\n") for ln in fh if ln.strip()]
    git_calls = []
    if os.path.exists(git_log):
        with open(git_log, encoding="utf-8") as fh:
            git_calls = [ln.rstrip("\r\n") for ln in fh if ln.strip()]
    for d in (workdir, runner_temp, bindir):
        shutil.rmtree(d, ignore_errors=True)
    return rc, out, outputs, summary, gh_calls, git_calls


def suite_spec_slug(script, env, tmproot):
    failures = []
    for sc in SPEC_SLUG_SCENARIOS:
        tag = f"[spec-slug: {sc['name']}]"
        rc, out, outputs, summary, gh_calls, git_calls = run_spec_slug_one(script, env, sc, tmproot)
        if rc != 0:
            failures.append(f"{tag} the step exited {rc} — it is best-effort and "
                            f"must never fail the collect job:\n{out}")
            continue
        for k, v in sc["expect"].items():
            if outputs.get(k, "") != v:
                failures.append(f"{tag} output {k!r} reads {outputs.get(k)!r}, "
                                f"expected {v!r}. outputs: {outputs}")
        downloaded = any(c.startswith("run download ") for c in gh_calls)
        if downloaded != sc["expect_download"]:
            failures.append(
                f"{tag} expected the metrics-record artifact "
                f"{'to be' if sc['expect_download'] else 'NOT to be'} downloaded; "
                f"gh was invoked as: {gh_calls or '(never)'}")
        viewed = any(c.startswith("run view ") for c in gh_calls)
        if viewed != sc.get("expect_run_view", False):
            failures.append(
                f"{tag} expected the head branch "
                f"{'to be' if sc.get('expect_run_view') else 'NOT to be'} read with "
                f"gh run view (a handed-in head must be used as-is); "
                f"gh was invoked as: {gh_calls or '(never)'}")
        if "expect_draft_read" in sc:
            draft_read = any(c.startswith("show refs/remotes/origin/spec-draft/")
                             for c in git_calls)
            if draft_read != sc["expect_draft_read"]:
                failures.append(
                    f"{tag} expected the spec-draft branch's spec-meta.json "
                    f"{'to be' if sc['expect_draft_read'] else 'NOT to be'} read; "
                    f"git was invoked as: {git_calls or '(never)'}")
    return failures


# --------------------------------------------------------------------------
# #330 single-home check. CLAUDE.md: when shared logic is consolidated, the
# nearest gate gets the "single home" check, or the rule lasts until the
# next session. The derivation's distinctive fragments are its branch-prefix
# case ARMS (`"${SPEC_DRAFT_PREFIX}"*)` ...) and the impl-branch iteration
# strip (`slug%-iter`). Not the prefix default expansions themselves
# (`SPEC_PREFIX:-spec/`): a collector legitimately defaults a prefix to
# name a branch it measures (branch-drift) or to map many branches to spec
# numbers (spec-collision, specs/046) — that is prefix USE, not a second
# copy of "which spec did this run advance". Neither fragment may reappear
# in watchdog.yml, and both jobs that need the answer must `uses:` the
# composite.
# --------------------------------------------------------------------------
DERIVATION_FRAGMENTS = ("slug%-iter", '"${SPEC_DRAFT_PREFIX}"*)', '"${SPEC_PREFIX}"*)',
                        '"${PLAN_PREFIX}"*)', '"${TASKS_PREFIX}"*)', '"${IMPL_PREFIX}"*)')


def single_home_failures(watchdog_text):
    """Failures for a watchdog.yml text that has grown a second copy of the
    spec-slug derivation, or dropped a caller of the composite."""
    import yaml
    failures = []
    for n, line in enumerate(watchdog_text.splitlines(), 1):
        for frag in DERIVATION_FRAGMENTS:
            if frag in line:
                failures.append(
                    f"[single-home] {WATCHDOG}:{n} carries {frag!r}, a fragment "
                    f"of the spec-slug derivation that lives ONLY in "
                    f"{SPEC_SLUG_ACTION} since #330 — call the composite "
                    f"instead of pasting the case statement back.")
    doc = yaml.safe_load(watchdog_text) or {}
    for job_id in SPEC_SLUG_CALLERS:
        steps = ((doc.get("jobs") or {}).get(job_id) or {}).get("steps") or []
        if not any(str((s or {}).get("uses", "")).endswith(SPEC_SLUG_ACTION_USES)
                   for s in steps):
            failures.append(
                f"[single-home] {WATCHDOG} job {job_id!r} no longer calls "
                f"{SPEC_SLUG_ACTION_USES.lstrip('/')} — both collect and "
                f"report-unhandled-failure must resolve the inspected run's "
                f"lifecycle issue through the one composite (#330).")
    return failures


def run_single_home_check():
    """The check against the shipped file, then against two fixtures built
    from it that must fail: a pasted-back copy of the derivation, and the
    report job with its composite call removed (constitution VIII — a check
    that cannot fail is not a check)."""
    with open(WATCHDOG, encoding="utf-8") as fh:
        text = fh.read()
    failures = single_home_failures(text)

    pasted = text.replace(
        "      - name: Initialize signals file\n",
        "      - name: Derive slug again\n"
        "        run: |\n"
        "          slug=\"${HEAD_BRANCH#impl/}\"; slug=\"${slug%-iter*}\"\n"
        "      - name: Initialize signals file\n", 1)
    if pasted == text:
        failures.append("[single-home self-check] could not build the pasted-copy "
                        "fixture — the 'Initialize signals file' anchor moved; "
                        "update this harness alongside watchdog.yml.")
    elif not any("slug%-iter" in f for f in single_home_failures(pasted)):
        failures.append("[single-home self-check] a pasted copy of the derivation "
                        "was NOT detected — the check is broken.")

    uses_line = f"        uses: ./.wing-commander-pipeline{SPEC_SLUG_ACTION_USES}\n"
    if text.count(uses_line) != len(SPEC_SLUG_CALLERS):
        failures.append(f"[single-home self-check] expected exactly "
                        f"{len(SPEC_SLUG_CALLERS)} `uses:` lines for the composite "
                        f"in {WATCHDOG}, found {text.count(uses_line)}.")
    else:
        head, _, tail = text.rpartition(uses_line)
        dropped = head + "        run: echo dropped\n" + tail
        if not any("report-unhandled-failure" in f for f in single_home_failures(dropped)):
            failures.append("[single-home self-check] the report job losing its "
                            "composite call was NOT detected — the check is broken.")
    return failures


def remove_record_fallback(script):
    """Mutation: the pre-#322 step, which derived the slug from the head
    branch and nothing else. Disabling the fallback's entry condition must
    break every scenario that expects a slug from the record."""
    fixed = 'if [ -z "$slug" ] && [ -n "$RUN_ID" ] && [ "$record_fallback" = "true" ]; then'
    if script.count(fixed) != 1:
        sys.exit("::error::verify-gate-19: could not locate spec-slug's "
                 "metrics-record fallback (#322) to mutate — the step text "
                 "may have changed shape; update this harness alongside it.")
    return script.replace(fixed, "if false; then", 1)


DRAFT_FALLBACK_GUARD = 'if [ "$meta_found" != "true" ]; then'


def mutate_draft_fallback(script, replacement):
    """Mutations of the #376 spec-draft fallback's entry condition: "if false"
    is the pre-#376 step (a draft-only spec resolves no issue); "if true"
    consults the draft even when the spec branch HAS a record, which lets the
    draft's record stand in for one that failed its identity check."""
    if script.count(DRAFT_FALLBACK_GUARD) != 1:
        sys.exit("::error::verify-gate-19: could not locate spec-slug's "
                 "spec-draft fallback (#376) to mutate — the step text may "
                 "have changed shape; update this harness alongside it.")
    return script.replace(DRAFT_FALLBACK_GUARD, replacement, 1)


# --------------------------------------------------------------------------
# #376: the "Collect: cost report" step, EXECUTED. verify-cost-report-
# collector.sh fixtures the step's two jq programs, but nothing ran the bash
# around them, and that is where all three #376 defects lived: an unresolved
# lifecycle issue was reported as a missing cost line; the run's "own"
# comment was the earliest one by ANY author; and a `grep` that matched
# nothing killed the step under errexit for every run whose issue did
# resolve. run_step runs the script as `bash -e`, and the script sets
# pipefail itself, so this suite runs under the flags the runner uses.
#
# `gh` is stubbed for `run download` (lays out the fixture metrics record)
# and `api .../comments` (applies the step's own --jq to the fixture page,
# as the real --paginate --jq does, or fails).
# --------------------------------------------------------------------------
COST_REPORT_STEP = "Collect: cost report"

STUB_GH_COST_TEMPLATE = r"""#!/usr/bin/env bash
if [ "$1" = "run" ] && [ "$2" = "download" ]; then
  dest=""
  prev=""
  for arg in "$@"; do
    if [ "$prev" = "-D" ]; then dest="$arg"; fi
    prev="$arg"
  done
  [ -n "$dest" ] || { echo "stub gh: no -D given" >&2; exit 1; }
  mkdir -p "$dest/metrics-record-cycle"
  printf '%s\n' "$GH_STUB_RECORD" > "$dest/metrics-record-cycle/wing-commander-metrics-record.json"
  if [ -n "${GH_STUB_SHADOW_RECORD:-}" ]; then
    # Maintainer review of #354: a metrics-record-branch-advance artifact
    # sorts alphabetically before metrics-record-cycle, so a selection that
    # picked the first glob match instead of the named artifact would pick
    # this transcript-less, cost_available:false record instead of the
    # real one above.
    mkdir -p "$dest/metrics-record-branch-advance"
    printf '%s\n' "$GH_STUB_SHADOW_RECORD" > "$dest/metrics-record-branch-advance/wing-commander-metrics-record-branch-advance.json"
  fi
  exit 0
fi
if [ "$1" = "api" ]; then
  if [ -n "${GH_STUB_COMMENTS_FAIL:-}" ]; then
    echo "gh: HTTP 502: injected failure (GH_STUB_COMMENTS_FAIL)" >&2
    exit 1
  fi
  jqexpr=""
  prev=""
  for arg in "$@"; do
    if [ "$prev" = "--jq" ]; then jqexpr="$arg"; fi
    prev="$arg"
  done
  printf '%s' "$GH_STUB_COMMENTS" | jq -c "$jqexpr"
  exit 0
fi
echo "unexpected gh invocation: $*" >&2
exit 1
"""

COST_RECORD = json.dumps({"schema_version": 1, "stage": "clarify", "cost_available": True})
COST_SHADOW_RECORD = json.dumps({
    "schema_version": 1, "record_available": False, "stage": "implement",
    "stage_available": True, "cost_available": False,
    "branch_advance": {"available": True, "branch": "spec/999-x",
                        "before_sha": "a" * 40, "before_available": True,
                        "after_sha": "a" * 40, "after_available": True,
                        "commits": 0, "commits_available": True},
})
COST_SINCE = "2026-09-16T23:46:22Z"
COST_UNTIL = "2026-09-16T23:51:53Z"


COST_BOT_SLUG = "wing-commander-bot"
APP = COST_BOT_SLUG + "[bot]"
ACTIONS = "github-actions[bot]"
OTHER_BOT = "dependabot[bot]"


def api_comment(created_at, login, body):
    return {"created_at": created_at, "user": {"login": login}, "body": body}


STARTED = api_comment("2026-09-16T23:46:40Z", APP, "📝 **Wing Commander · intake** — started")
# The owner's own cost guess is not currency-shaped on purpose: an attribution
# that admitted a person's comment would read "$99" as malformed, so every
# scenario holding this comment kills that mutation, not just the ones where
# it is the only comment.
OWNER_REPLY = api_comment("2026-09-16T23:46:27Z", "charlesguse", "Q1: a\nQ2: b\n\nCost: $99 is my guess")
WITH_COST = api_comment("2026-09-16T23:51:46Z", APP,
                        "> **Action needed**\n>\n> **Cost**: $1.90 · 37/40 turns · claude-opus-5\n")
ACTIONS_COST = api_comment("2026-09-16T23:51:46Z", ACTIONS, "**Cost**: $0.0042 · 3/10 turns")
NO_COST = api_comment("2026-09-16T23:50:00Z", APP, "Thanks — I could not map this reply.")
LEAKED = api_comment("2026-09-16T23:51:46Z", APP, "**Cost**: $COST_LINE · 40 turns")
BEFORE_RUN = api_comment("2026-09-16T23:35:22Z", APP, "**Cost**: $1.53 · 19/50 turns")
AFTER_RUN = api_comment("2026-09-16T23:59:00Z", APP, "**Cost**: $2.22 · 9/40 turns")
OTHER_BOT_COST = api_comment("2026-09-16T23:49:00Z", OTHER_BOT, "Bumps foo. Cost: $12 (est.)")

COST_SCENARIOS = [
    dict(
        name="no lifecycle issue resolved: nothing is searched, so nothing is "
             "reported — not-checked is never checked-and-absent (#376)",
        issue="", comments=[],
        expect=[], expect_outcome="ok",
    ),
    dict(
        name="the run's first comment is its 'started' announcement and a "
             "later one carries the cost line: no signal, and the step "
             "survives the cost-less comment under errexit (#376)",
        issue="362", comments=[STARTED, WITH_COST],
        expect=[], expect_outcome="ok",
    ),
    dict(
        name="the owner replies again seconds after the run starts: a "
             "person's comment is never the run's own, even one that "
             "mentions a cost (#376)",
        issue="362", comments=[OWNER_REPLY, WITH_COST],
        expect=[], expect_outcome="ok",
    ),
    dict(
        name="github-actions[bot] posted the line (a default-token step): it "
             "is the pipeline's own identity too",
        issue="362", comments=[STARTED, ACTIONS_COST],
        expect=[], expect_outcome="ok",
    ),
    dict(
        name="another bot commented in the window with a dollar figure: not a "
             "pipeline identity, so not the run's — cost-line-missing, none "
             "found (a login match, not 'any bot')",
        issue="362", comments=[OTHER_BOT_COST],
        expect=[("cost-line-missing", False)], expect_outcome="ok",
    ),
    dict(
        name="the run's end time is unknown: an open-ended window cannot tell "
             "this run's comments from the next run's — not checked, no "
             "signal (#376)",
        issue="362", comments=[STARTED, NO_COST], updated_at="",
        expect=[], expect_outcome="ok",
    ),
    dict(
        name="the App slug is unknown: the run's own comments cannot be "
             "identified — not checked, no signal (#376)",
        issue="362", comments=[STARTED, NO_COST], bot_slug="",
        expect=[], expect_outcome="ok",
    ),
    dict(
        name="the run commented but never posted a cost line (#366's shape): "
             "cost-line-missing with lifecycle-comment-found true",
        issue="362", comments=[OWNER_REPLY, NO_COST],
        expect=[("cost-line-missing", True)], expect_outcome="ok",
    ),
    dict(
        name="only a person commented during the run: cost-line-missing with "
             "lifecycle-comment-found false",
        issue="362", comments=[OWNER_REPLY],
        expect=[("cost-line-missing", False)], expect_outcome="ok",
    ),
    dict(
        name="cost lines posted before the run started and after it ended "
             "belong to other runs: cost-line-missing, none found",
        issue="362", comments=[BEFORE_RUN, AFTER_RUN],
        expect=[("cost-line-missing", False)], expect_outcome="ok",
    ),
    dict(
        name="the literal $COST_LINE leak (#272): cost-line-malformed carrying "
             "the whole observed line",
        issue="362", comments=[STARTED, LEAKED],
        expect=[("cost-line-malformed", "Cost: $COST_LINE · 40 turns")],
        expect_outcome="ok",
    ),
    dict(
        name="a skipped run executed nothing, so it owes no cost line "
             "(FR-026) — no signal, and no outcome record either",
        issue="362", comments=[NO_COST], conclusion="skipped",
        expect=[], expect_outcome=None,
    ),
    dict(
        name="the comment read fails: no signal either way, and the collector "
             "is recorded untrusted (#376)",
        issue="362", comments=[], comments_fail=True,
        expect=[], expect_outcome="failed",
    ),
    dict(
        name="a metrics-record-branch-advance artifact (maintainer review of "
             "#354) sorts before metrics-record-cycle in glob order but must "
             "not shadow it — the cost-line-missing signal still fires off "
             "the real cycle record's own cost_available:true",
        issue="362", comments=[OWNER_REPLY, NO_COST], shadow=True,
        expect=[("cost-line-missing", True)], expect_outcome="ok",
    ),
]


def run_cost_one(script, env, sc, tmproot):
    workdir = tempfile.mkdtemp(dir=tmproot)
    runner_temp = tempfile.mkdtemp(dir=tmproot)
    bindir = tempfile.mkdtemp(dir=tmproot)
    for name in ("signals.json", "collector-outcomes.json"):
        with open(os.path.join(runner_temp, name), "w", encoding="utf-8") as fh:
            fh.write("[]")
    gh_path = os.path.join(bindir, "gh")
    with open(gh_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(STUB_GH_COST_TEMPLATE)
    os.chmod(gh_path, 0o755)
    stub_jq(bindir)

    run_env = with_actions_defaults(env)
    run_env["PATH"] = bindir + os.pathsep + os.environ["PATH"]
    run_env.update({"RUN_CONCLUSION": sc.get("conclusion", "success"), "CREATED_AT": COST_SINCE,
                    "UPDATED_AT": sc.get("updated_at", COST_UNTIL), "ISSUE": sc["issue"],
                    "BOT_SLUG": sc.get("bot_slug", COST_BOT_SLUG),
                    "GH_STUB_RECORD": COST_RECORD,
                    "GH_STUB_COMMENTS": json.dumps(sc["comments"])})
    if sc.get("comments_fail"):
        run_env["GH_STUB_COMMENTS_FAIL"] = "1"
    if sc.get("shadow"):
        run_env["GH_STUB_SHADOW_RECORD"] = COST_SHADOW_RECORD

    rc, out, _, _ = run_step(BASH, script, workdir, run_env, runner_temp)
    with open(os.path.join(runner_temp, "signals.json"), encoding="utf-8") as fh:
        signals = json.load(fh)
    with open(os.path.join(runner_temp, "collector-outcomes.json"), encoding="utf-8") as fh:
        outcomes = json.load(fh)
    for d in (workdir, runner_temp, bindir):
        shutil.rmtree(d, ignore_errors=True)
    return rc, out, signals, outcomes


def suite_cost_report(script, env, tmproot):
    failures = []
    for sc in COST_SCENARIOS:
        tag = f"[cost-report: {sc['name']}]"
        rc, out, signals, outcomes = run_cost_one(script, env, sc, tmproot)
        if rc != 0:
            failures.append(f"{tag} the collector exited {rc}:\n{out}")
            continue
        got = []
        for sig in signals:
            facts = sig.get("facts") or {}
            hint = sig.get("class-hint")
            got.append((hint, facts.get("lifecycle-comment-found")
                        if hint == "cost-line-missing" else facts.get("observed-text")))
        if got != sc["expect"]:
            failures.append(f"{tag} signals read {got}, expected {sc['expect']}. "
                            f"signals.json: {signals}")
        got_outcome = last_outcome(outcomes, "collect-cost-report")
        if got_outcome != sc["expect_outcome"]:
            failures.append(f"{tag} collector-outcomes.json for collect-cost-report "
                            f"reads {got_outcome!r}, expected {sc['expect_outcome']!r}.")
    return failures


def mutate_cost_report(script, old, new, what):
    if script.count(old) != 1:
        sys.exit(f"::error::verify-gate-19: could not locate cost-report's {what} "
                 f"(#376) to mutate — the step text may have changed shape; update "
                 f"this harness alongside it.")
    return script.replace(old, new, 1)


COST_MUTATIONS = [
    ("cost-report's not-checked guard (#376)",
     'elif ($in.comments_checked // false) != true then []',
     'elif false then []'),
    ("cost-report's pipeline-identity filter on the run's own comments (#376)",
     '| select(.userLogin as $l | any(($in.logins // [])[]; . == $l))', ''),
    ("cost-report taking any bot's comment for the run's own (#376)",
     '| select(.userLogin as $l | any(($in.logins // [])[]; . == $l))',
     '| select((.userLogin // "") | endswith("[bot]"))'),
    ("cost-report checking with an open-ended window (#376)",
     'elif [ -z "$CREATED_AT" ] || [ -z "$UPDATED_AT" ] || [ -z "$BOT_SLUG" ]; then',
     'elif false; then'),
    ("cost-report's end-of-run bound on the run's own comments (#376)",
     '| select(($in.until // "") == "" or .createdAt <= $in.until) ]', ']'),
    ("cost-report searching every own comment, not only the earliest (#376)",
     '| sort_by(.createdAt) as $own', '| (sort_by(.createdAt) | .[0:1]) as $own'),
]


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
                 "collect-annotations", "collect-turn-budget",
                 "collect-cost-report", "collect-final-pr-claims",
                 "collect-spec-collision"]

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
        name="one collector's read failed, the other eight succeeded",
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
    dict(
        name="all nine collector STEPS outright error: evidence-available "
             "flips to false",
        why="specs/046-watchdog-supervision-collectors leg-1 — the "
            "collectors-failed >= collectors-total comparison must track "
            "the loop's own length, not a stale literal, or a run where "
            "every one of this feature's four new collectors (in addition "
            "to the five pre-existing ones) errors would be miscounted as "
            "a partial pass instead of 'could not inspect this run.'",
        outcomes=[{"collector": c, "outcome": "ok"} for c in COLLECTOR_IDS],
        step_outcomes={c: "failure" for c in COLLECTOR_IDS},
        expect_untrusted=[],
        expect_evidence_available="false",
        expect_signals=[],
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
    return run_script_mutation(label, suite_fn,
                               strip_conclusion_guard(script, var_name), env, tmproot)


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
        bd_failures.extend(run_script_mutation(
            "branch-drift's unresolved-slug guard (#318)",
            suite_bd, reintroduce_slug_hole(bd_script), bd_env, bd_tmproot))
        bd_failures.extend(run_script_mutation(
            "branch-drift's dispatched-implement measurement (#322)",
            suite_bd, reintroduce_implement_skip(bd_script), bd_env, bd_tmproot))
    finally:
        shutil.rmtree(bd_tmproot, ignore_errors=True)
    for f in bd_failures:
        print(f"::error::{f}")
    failures.extend(bd_failures)

    spec_slug_step = find_step(SPEC_SLUG_ACTION, SPEC_SLUG_STEP)
    spec_slug_script, spec_slug_env = render_step(spec_slug_step, SPEC_SLUG_ACTION)
    spec_slug_tmproot = tempfile.mkdtemp()
    try:
        spec_slug_failures = suite_spec_slug(spec_slug_script, spec_slug_env, spec_slug_tmproot)
        spec_slug_failures.extend(run_script_mutation(
            "spec-slug's metrics-record fallback (#322)",
            suite_spec_slug, remove_record_fallback(spec_slug_script),
            spec_slug_env, spec_slug_tmproot))
        spec_slug_failures.extend(run_script_mutation(
            "spec-slug's spec-draft fallback (#376)",
            suite_spec_slug, mutate_draft_fallback(spec_slug_script, "if false; then"),
            spec_slug_env, spec_slug_tmproot))
        spec_slug_failures.extend(run_script_mutation(
            "spec-slug's spec-draft fallback being limited to a spec branch "
            "with no record (#376)",
            suite_spec_slug, mutate_draft_fallback(spec_slug_script, "if true; then"),
            spec_slug_env, spec_slug_tmproot))
    finally:
        shutil.rmtree(spec_slug_tmproot, ignore_errors=True)
    spec_slug_failures.extend(run_single_home_check())
    for f in spec_slug_failures:
        print(f"::error::{f}")
    failures.extend(spec_slug_failures)

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

    cost_step = find_step(WATCHDOG, COST_REPORT_STEP)
    cost_script, cost_env = render_step(cost_step)
    cost_tmproot = tempfile.mkdtemp()
    try:
        cost_failures = suite_cost_report(cost_script, cost_env, cost_tmproot)
        cost_failures.extend(run_attribution_mutation(
            "cost-report's RUN_CONCLUSION attribution guard (FR-026)",
            suite_cost_report, cost_script, cost_env, cost_tmproot,
            "RUN_CONCLUSION"))
        for label, old, new in COST_MUTATIONS:
            cost_failures.extend(run_script_mutation(
                label, suite_cost_report,
                mutate_cost_report(cost_script, old, new, label),
                cost_env, cost_tmproot))
    finally:
        shutil.rmtree(cost_tmproot, ignore_errors=True)
    for f in cost_failures:
        print(f"::error::{f}")
    failures.extend(cost_failures)

    aggregate_failures = run_aggregate_suite()
    for f in aggregate_failures:
        print(f"::error::{f}")
    failures.extend(aggregate_failures)

    print(f"annotation collector: {len(SCENARIOS)} scenario(s); "
          f"execution-output collector: {len(EXEC_SCENARIOS)} scenario(s); "
          f"branch-drift collector: {len(BD_SCENARIOS)} scenario(s); "
          f"spec-slug step: {len(SPEC_SLUG_SCENARIOS)} scenario(s) + single-home check; "
          f"spec-meta collector: {len(SPEC_META_SCENARIOS)} scenario(s); "
          f"step-summary collector: {len(STEPSUM_SCENARIOS)} scenario(s); "
          f"cost-report collector: {len(COST_SCENARIOS)} scenario(s); "
          f"aggregate: {len(AGGREGATE_CASES)} case(s); "
          f"{len(failures)} failure(s).")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
