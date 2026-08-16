#!/usr/bin/env python3
"""Behavioral tests for watchdog.yml's "Collect: annotations" step (Gate 19).

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
]


def write_fixtures(fixture_dir, jobs, anns):
    with open(os.path.join(fixture_dir, "jobs-pages.json"), "w", encoding="utf-8") as fh:
        json.dump(jobs, fh)
    for job_id, pages in anns.items():
        with open(os.path.join(fixture_dir, f"anns-pages-{job_id}.json"),
                  "w", encoding="utf-8") as fh:
            json.dump(pages, fh)


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

    env = dict(env)
    env["PATH"] = bindir + os.pathsep + os.environ["PATH"]
    env["GITHUB_REPOSITORY"] = "charlesguse/wing-commander"
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


MUTATIONS = [
    ("the annotations filter collecting results into an array per page",
     mut_array_collecting_annotations),
]


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
    ),
    dict(
        name="one collector's read failed, the other four succeeded",
        why="Acceptance Scenario 3 — untrusted-collectors names exactly the "
            "failed collector, evidence-available stays true (a partial "
            "failure still reaches a verdict), and this is true even though "
            "the failed collector's own STEP outcome is 'success' (T016: "
            "outcome is never derived from the step's overall exit code).",
        outcomes=([{"collector": c, "outcome": "ok"} for c in COLLECTOR_IDS
                   if c != "collect-annotations"]
                  + [{"collector": "collect-annotations", "outcome": "failed"}]),
        step_outcomes={c: "success" for c in COLLECTOR_IDS},
        expect_untrusted=["collect-annotations"],
        expect_evidence_available="true",
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
            fh.write("[]")
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

    aggregate_failures = run_aggregate_suite()
    for f in aggregate_failures:
        print(f"::error::{f}")
    failures.extend(aggregate_failures)

    print(f"annotation collector: {len(SCENARIOS)} scenario(s); "
          f"aggregate: {len(AGGREGATE_CASES)} case(s); "
          f"{len(failures)} failure(s).")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
