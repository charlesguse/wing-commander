#!/usr/bin/env python3
"""auto-release.yml's `report` job says what actually happened (Gate 52).

WHY THIS EXISTS
---------------
`report` runs under `always()` and reads every earlier job's outputs. A job
that crashed before writing its outputs hands it empty strings, and before
#325 every branch of the step was written for a different situation: a
`detect` crash printed "no release tag exists yet -- nothing to compare
against" (an infrastructure failure reported as a normal quiet day, every
day, filing nothing); a `decide-version` crash after a passing verdict fell
through to "release dispatch failed for ." and told the maintainer to look
at release.yml's run, which was never dispatched; the stale-head guard's
own failed read of main's tip set `release-outcome=failed` before any
dispatch and pointed at the same non-existent run.

This harness EXECUTES the shipped step (read out of auto-release.yml at run
time, so there is no second copy to drift) against synthetic `needs.*`
values -- each job's `result` and outputs -- with `gh` stubbed to record
what would have been filed, commented, or closed. Every attribution path
the step has is a scenario: the two quiet days, each verdict class, each
job-result crash, the collision, the tip-unresolved read, released, the
stale head, and both shapes of a real release failure (with and without an
observed release.yml run).

It ends with MUTATION checks that put each #325 defect back and assert the
suite then fails. A test that cannot fail is not a test.

Usage: python3 .github/scripts/verify-auto-release-report.py
Requires: bash, jq. See wc_shell_harness.py for running this on Windows.
"""
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_shell_harness import (  # noqa: E402
    ensure_jq, find_step, resolve_bash, run_step, use_utf8_stdout)

WORKFLOW = ".github/workflows/auto-release.yml"
STEP = "Report this run's outcome"

BASH = None

# A `gh` stand-in that records every invocation and answers the four calls
# the step makes: `issue list` (the open auto-release:failed issue, if the
# scenario says one exists), `issue create`, `issue comment`, `issue close`
# and `label create` (all no-ops beyond the log).
STUB_GH = r'''#!/usr/bin/env bash
if [ -n "${GH_STUB_LOG:-}" ]; then printf '%s\n' "$*" >> "$GH_STUB_LOG"; fi
case "$1 $2" in
  "issue list")
    printf '%s\n' "${GH_STUB_EXISTING_ISSUE:-}"
    exit 0
    ;;
  "issue create"|"issue comment"|"issue close"|"label create")
    exit 0
    ;;
esac
echo "unexpected gh invocation: $*" >&2
exit 1
'''

RUN_URL = "https://github.com/charlesguse/wing-commander/actions/runs/777"
HEAD = "0123456789abcdef0123456789abcdef01234567"
PASS = json.dumps({"outcome": "pass", "verified_head": HEAD})
WRONG_OUTPUT = json.dumps({"outcome": "fail-wrong-output", "verified_head": HEAD,
                           "failing_check": "spec.md content",
                           "expected": "the fixture's heading",
                           "observed": "an empty file",
                           "evidence_url": "https://example.invalid/e2e"})

# Every scenario starts from a run where nothing has happened yet -- every
# result `skipped`, every output empty -- and overrides what its situation
# sets. `filed` is what the step did with the failure issue: "create",
# "comment" (dedup onto the existing one), or None.
BASE = dict(DETECT_RESULT="skipped", VERIFY_RESULT="skipped",
            DECIDE_RESULT="skipped", DISPATCH_RESULT="skipped",
            HEAD_SHA="", HAS_NEW_WORK="", TAG_EXISTS="", LATEST_TAG="",
            VERDICT_JSON="", NEXT_VERSION="", COLLISION="",
            RELEASE_OUTCOME="", RELEASE_RUN_ID="")

SCENARIOS = [
    dict(
        name="detect crashed before writing outputs: infrastructure, filed, "
             "naming detect and this run -- not a quiet day (#325 case 1)",
        env=dict(DETECT_RESULT="failure"),
        filed="create",
        body_contains=["infrastructure", "`detect`", RUN_URL, "unknown"],
        body_excludes=["release.yml was dispatched"],
        summary_contains="infrastructure failure",
        summary_excludes="no release tag exists yet",
    ),
    dict(
        name="run cancelled during detect: summarised, nothing filed",
        env=dict(DETECT_RESULT="cancelled"),
        filed=None,
        summary_contains="cancelled",
    ),
    dict(
        name="quiet day with a baseline tag (FR-003): nothing filed",
        env=dict(DETECT_RESULT="success", HAS_NEW_WORK="false", TAG_EXISTS="true",
                 LATEST_TAG="v2.7.2", HEAD_SHA=HEAD),
        filed=None,
        summary_contains="no new work since v2.7.2",
    ),
    dict(
        name="no baseline tag yet (FR-004): nothing filed",
        env=dict(DETECT_RESULT="success", HAS_NEW_WORK="false", TAG_EXISTS="false",
                 HEAD_SHA=HEAD),
        filed=None,
        summary_contains="no release tag exists yet",
    ),
    dict(
        name="new work but verify-e2e crashed with no verdict: fail-infra "
             "naming the missing verdict and the job result",
        env=dict(DETECT_RESULT="success", HAS_NEW_WORK="true", TAG_EXISTS="true",
                 LATEST_TAG="v2.7.2", HEAD_SHA=HEAD, VERIFY_RESULT="failure"),
        filed="create",
        body_contains=["infrastructure", "verify-e2e produced no verdict",
                       "job result: failure", RUN_URL],
        summary_contains="verification failed",
    ),
    dict(
        name="run cancelled during verify-e2e (a hung poll stopped by hand): "
             "summarised, nothing filed -- not an infrastructure failure",
        env=dict(DETECT_RESULT="success", HAS_NEW_WORK="true", TAG_EXISTS="true",
                 LATEST_TAG="v2.7.2", HEAD_SHA=HEAD, VERIFY_RESULT="cancelled"),
        filed=None,
        summary_contains="cancelled",
        summary_excludes="verification failed",
    ),
    dict(
        name="verify-e2e succeeded but its verdict is not a JSON object: "
             "fail-infra whose body says the contract broke, not that the "
             "job stopped",
        env=dict(DETECT_RESULT="success", HAS_NEW_WORK="true", TAG_EXISTS="true",
                 LATEST_TAG="v2.7.2", HEAD_SHA=HEAD, VERIFY_RESULT="success",
                 VERDICT_JSON="pass"),
        filed="create",
        body_contains=["infrastructure", "verify-e2e produced no verdict", "contract broken"],
        body_excludes=["the job stopped"],
    ),
    dict(
        name="a fail-wrong-output verdict: pipeline defect, filed with the "
             "verdict's own fields",
        env=dict(DETECT_RESULT="success", HAS_NEW_WORK="true", TAG_EXISTS="true",
                 LATEST_TAG="v2.7.2", HEAD_SHA=HEAD, VERIFY_RESULT="success",
                 VERDICT_JSON=WRONG_OUTPUT),
        filed="create",
        body_contains=["pipeline defect", "spec.md content", "https://example.invalid/e2e"],
        body_excludes=["infrastructure"],
    ),
    dict(
        name="verdict passed but decide-version crashed: infrastructure "
             "naming decide-version -- not 'release dispatch failed for .' "
             "(#325 case 2)",
        env=dict(DETECT_RESULT="success", HAS_NEW_WORK="true", TAG_EXISTS="true",
                 LATEST_TAG="v2.7.2", HEAD_SHA=HEAD, VERIFY_RESULT="success",
                 VERDICT_JSON=PASS, DECIDE_RESULT="failure"),
        filed="create",
        body_contains=["infrastructure", "`decide-version`", RUN_URL],
        body_excludes=["release.yml was dispatched", "release failure"],
        summary_excludes="release dispatch failed",
    ),
    dict(
        name="run cancelled during decide-version: summarised, nothing filed",
        env=dict(DETECT_RESULT="success", HAS_NEW_WORK="true", TAG_EXISTS="true",
                 LATEST_TAG="v2.7.2", HEAD_SHA=HEAD, VERIFY_RESULT="success",
                 VERDICT_JSON=PASS, DECIDE_RESULT="cancelled"),
        filed=None,
        summary_contains="cancelled",
    ),
    dict(
        name="version collision: filed as a collision, no dispatch attempted",
        env=dict(DETECT_RESULT="success", HAS_NEW_WORK="true", TAG_EXISTS="true",
                 LATEST_TAG="v2.7.2", HEAD_SHA=HEAD, VERIFY_RESULT="success",
                 VERDICT_JSON=PASS, DECIDE_RESULT="success", NEXT_VERSION="v2.8.0",
                 COLLISION="true"),
        filed="create",
        body_contains=["version collision", "v2.8.0"],
        summary_contains="version collision",
    ),
    dict(
        name="released: the open failure issue is closed, nothing filed",
        env=dict(DETECT_RESULT="success", HAS_NEW_WORK="true", TAG_EXISTS="true",
                 LATEST_TAG="v2.7.2", HEAD_SHA=HEAD, VERIFY_RESULT="success",
                 VERDICT_JSON=PASS, DECIDE_RESULT="success", NEXT_VERSION="v2.8.0",
                 COLLISION="false", DISPATCH_RESULT="success",
                 RELEASE_OUTCOME="released", RELEASE_RUN_ID="4242"),
        existing_issue="42",
        filed=None,
        closed="42",
        summary_contains="released v2.8.0",
    ),
    dict(
        name="stale head: expected behaviour, nothing filed",
        env=dict(DETECT_RESULT="success", HAS_NEW_WORK="true", TAG_EXISTS="true",
                 LATEST_TAG="v2.7.2", HEAD_SHA=HEAD, VERIFY_RESULT="success",
                 VERDICT_JSON=PASS, DECIDE_RESULT="success", NEXT_VERSION="v2.8.0",
                 COLLISION="false", DISPATCH_RESULT="success",
                 RELEASE_OUTCOME="stale-head"),
        filed=None,
        summary_contains="main advanced past the verified head",
    ),
    dict(
        name="the stale-head guard's own tip read failed: infrastructure, "
             "nothing was dispatched -- not 'see release.yml's own run' "
             "(#325 case 3)",
        env=dict(DETECT_RESULT="success", HAS_NEW_WORK="true", TAG_EXISTS="true",
                 LATEST_TAG="v2.7.2", HEAD_SHA=HEAD, VERIFY_RESULT="success",
                 VERDICT_JSON=PASS, DECIDE_RESULT="success", NEXT_VERSION="v2.8.0",
                 COLLISION="false", DISPATCH_RESULT="success",
                 RELEASE_OUTCOME="tip-unresolved"),
        filed="create",
        body_contains=["infrastructure", "current tip", RUN_URL],
        body_excludes=["release failure", "release.yml was dispatched"],
        summary_excludes="release dispatch failed",
    ),
    dict(
        name="dispatch-release crashed with no outcome: infrastructure "
             "naming dispatch-release",
        env=dict(DETECT_RESULT="success", HAS_NEW_WORK="true", TAG_EXISTS="true",
                 LATEST_TAG="v2.7.2", HEAD_SHA=HEAD, VERIFY_RESULT="success",
                 VERDICT_JSON=PASS, DECIDE_RESULT="success", NEXT_VERSION="v2.8.0",
                 COLLISION="false", DISPATCH_RESULT="failure"),
        filed="create",
        body_contains=["infrastructure", "`dispatch-release`", RUN_URL],
        body_excludes=["release failure"],
    ),
    dict(
        name="dispatch-release skipped after a pass (paused mid-run): "
             "summarised, nothing filed",
        env=dict(DETECT_RESULT="success", HAS_NEW_WORK="true", TAG_EXISTS="true",
                 LATEST_TAG="v2.7.2", HEAD_SHA=HEAD, VERIFY_RESULT="success",
                 VERDICT_JSON=PASS, DECIDE_RESULT="success", NEXT_VERSION="v2.8.0",
                 COLLISION="false", DISPATCH_RESULT="skipped"),
        filed=None,
        summary_contains="did not run",
    ),
    dict(
        name="release.yml ran and failed: release failure linking that run",
        env=dict(DETECT_RESULT="success", HAS_NEW_WORK="true", TAG_EXISTS="true",
                 LATEST_TAG="v2.7.2", HEAD_SHA=HEAD, VERIFY_RESULT="success",
                 VERDICT_JSON=PASS, DECIDE_RESULT="success", NEXT_VERSION="v2.8.0",
                 COLLISION="false", DISPATCH_RESULT="success",
                 RELEASE_OUTCOME="failed", RELEASE_RUN_ID="9999"),
        filed="create",
        body_contains=["release failure", "actions/runs/9999"],
        body_excludes=["never observed"],
        summary_contains="release dispatch failed for v2.8.0",
    ),
    dict(
        name="release.yml was never observed running (dispatch rejected or "
             "no run appeared): release failure saying so, not pointing at "
             "a run that does not exist",
        env=dict(DETECT_RESULT="success", HAS_NEW_WORK="true", TAG_EXISTS="true",
                 LATEST_TAG="v2.7.2", HEAD_SHA=HEAD, VERIFY_RESULT="success",
                 VERDICT_JSON=PASS, DECIDE_RESULT="success", NEXT_VERSION="v2.8.0",
                 COLLISION="false", DISPATCH_RESULT="success",
                 RELEASE_OUTCOME="failed"),
        filed="create",
        body_contains=["release failure", "never observed", RUN_URL],
        body_excludes=["see its run:"],
    ),
    dict(
        name="a failure with an open report already filed: commented onto "
             "it, not filed twice (research.md D13)",
        env=dict(DETECT_RESULT="failure"),
        existing_issue="42",
        filed="comment",
        body_contains=["infrastructure", "`detect`"],
    ),
]


def render_step(step):
    """The step's run: block; its `${{ }}` env values become fixture
    values (GH_TOKEN a dummy, everything else empty for BASE to fill)."""
    script = str(step["run"])
    env = {}
    for k, v in (step.get("env") or {}).items():
        v = str(v)
        if "${{" in v:
            v = "dummy-token" if k == "GH_TOKEN" else ""
        env[k] = v
    if "${{" in script:
        sys.exit(f"::error file={WORKFLOW}::the extracted run: block contains a "
                 f"${{{{ }}}} expression this harness does not resolve.")
    return script, env


def run_scenario(script, env, sc, tmproot):
    workdir = tempfile.mkdtemp(dir=tmproot)
    runner_temp = tempfile.mkdtemp(dir=tmproot)
    bindir = tempfile.mkdtemp(dir=tmproot)

    gh_path = os.path.join(bindir, "gh")
    with open(gh_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(STUB_GH)
    os.chmod(gh_path, 0o755)

    run_env = dict(env)
    run_env.update(BASE)
    run_env.update(sc["env"])
    run_env["PATH"] = bindir + os.pathsep + os.environ["PATH"]
    run_env["GITHUB_SERVER_URL"] = "https://github.com"
    run_env["GITHUB_REPOSITORY"] = "charlesguse/wing-commander"
    run_env["GITHUB_RUN_ID"] = "777"
    gh_log = os.path.join(runner_temp, "gh-stub.log")
    run_env["GH_STUB_LOG"] = gh_log.replace("\\", "/")
    if sc.get("existing_issue"):
        run_env["GH_STUB_EXISTING_ISSUE"] = sc["existing_issue"]

    rc, out, _, summary = run_step(BASH, script, workdir, run_env, runner_temp)
    gh_calls = []
    if os.path.exists(gh_log):
        with open(gh_log, encoding="utf-8") as fh:
            gh_calls = [ln.rstrip("\r\n") for ln in fh if ln.strip()]
    body = ""
    body_path = os.path.join(runner_temp, "auto-release-failure-body.md")
    if os.path.exists(body_path):
        with open(body_path, encoding="utf-8") as fh:
            body = fh.read()
    for d in (workdir, runner_temp, bindir):
        shutil.rmtree(d, ignore_errors=True)
    return rc, out, summary, gh_calls, body


def suite(script, env, tmproot):
    failures = []
    for sc in SCENARIOS:
        tag = f"[{sc['name']}]"
        rc, out, summary, gh_calls, body = run_scenario(script, env, sc, tmproot)
        if rc != 0:
            failures.append(f"{tag} the step exited {rc}:\n{out}")
            continue
        created = any(c.startswith("issue create ") for c in gh_calls)
        commented = any(c.startswith("issue comment ") for c in gh_calls)
        closed = [c for c in gh_calls if c.startswith("issue close ")]
        filed = "create" if created else ("comment" if commented else None)
        if filed != sc["filed"]:
            failures.append(f"{tag} expected filed={sc['filed']!r}, got {filed!r}; "
                            f"gh calls: {gh_calls or '(none)'}")
        want_closed = sc.get("closed")
        if want_closed:
            if not any(c.startswith(f"issue close {want_closed} ") for c in closed):
                failures.append(f"{tag} expected `gh issue close {want_closed}`; "
                                f"gh calls: {gh_calls or '(none)'}")
        elif closed:
            failures.append(f"{tag} closed an issue it should not have: {closed}")
        for needle in sc.get("body_contains", []):
            if needle not in body:
                failures.append(f"{tag} failure body lacks {needle!r}:\n{body}")
        for needle in sc.get("body_excludes", []):
            if needle in body:
                failures.append(f"{tag} failure body wrongly contains {needle!r}:\n{body}")
        if "summary_contains" in sc and sc["summary_contains"] not in summary:
            failures.append(f"{tag} step summary lacks {sc['summary_contains']!r}: "
                            f"{summary!r}")
        if "summary_excludes" in sc and sc["summary_excludes"] in summary:
            failures.append(f"{tag} step summary wrongly contains "
                            f"{sc['summary_excludes']!r}: {summary!r}")
    return failures


# --------------------------------------------------------------------------
# Mutations: each puts one #325 defect back.
# --------------------------------------------------------------------------
def blind_case(script, var_name):
    """Make the `case "$VAR" in` that reads a job result match nothing: the
    subject becomes a string no arm names, so the step behaves as if it
    never read that result -- the pre-#325 shape -- while the script stays
    syntactically whole. (Deleting the block instead left an empty `if`
    body for the one case nested inside an `if`, which failed every
    scenario with a bash parse error rather than for the reason under test.)"""
    old = 'case "$' + var_name + '" in'
    if script.count(old) != 1:
        sys.exit(f"::error::verify-auto-release-report: expected exactly one "
                 f"{old!r} to mutate, found {script.count(old)} — the step text "
                 f"may have changed shape; update this harness alongside it.")
    return script.replace(old, 'case "mutated-$' + var_name + '" in', 1)


def mut_ignore_detect_result(script):
    return blind_case(script, "DETECT_RESULT")


def mut_ignore_verify_result(script):
    return blind_case(script, "VERIFY_RESULT")


def mut_ignore_decide_result(script):
    return blind_case(script, "DECIDE_RESULT")


def mut_ignore_dispatch_result(script):
    return blind_case(script, "DISPATCH_RESULT")


def mut_no_verdict_always_stopped(script):
    old = 'if [ "$VERIFY_RESULT" = "success" ]; then'
    if script.count(old) != 1:
        sys.exit("::error::verify-auto-release-report: could not locate the "
                 "no-verdict wording branch to mutate — the step text may have "
                 "changed shape; update this harness alongside it.")
    return script.replace(old, 'if false; then', 1)


def mut_tip_unresolved_is_a_release_failure(script):
    old = 'if [ "$RELEASE_OUTCOME" = "tip-unresolved" ]; then'
    if script.count(old) != 1:
        sys.exit("::error::verify-auto-release-report: could not locate the "
                 "tip-unresolved arm to mutate — the step text may have "
                 "changed shape; update this harness alongside it.")
    return script.replace(old, 'if [ "$RELEASE_OUTCOME" = "tip-unresolved-never" ]; then', 1)


def mut_always_point_at_release_run(script):
    old = 'if [ -n "$RELEASE_RUN_ID" ]; then'
    if script.count(old) != 1:
        sys.exit("::error::verify-auto-release-report: could not locate the "
                 "release-run-id branch to mutate — the step text may have "
                 "changed shape; update this harness alongside it.")
    return script.replace(old, 'if true; then', 1)


MUTATIONS = [
    ("report ignoring detect's job result (#325 case 1)", mut_ignore_detect_result),
    ("report filing a cancelled verify-e2e as infrastructure", mut_ignore_verify_result),
    ("a succeeded verify-e2e with no verdict described as 'the job stopped'",
     mut_no_verdict_always_stopped),
    ("report ignoring decide-version's job result (#325 case 2)", mut_ignore_decide_result),
    ("report ignoring dispatch-release's job result", mut_ignore_dispatch_result),
    ("tip-unresolved reported as a release failure (#325 case 3)",
     mut_tip_unresolved_is_a_release_failure),
    ("a release failure always pointing at a release.yml run",
     mut_always_point_at_release_run),
]


def main():
    global BASH
    use_utf8_stdout()
    ensure_jq()
    BASH = resolve_bash()
    if not os.path.isfile(WORKFLOW):
        sys.exit(f"::error::run this from the repository root; {WORKFLOW} not found.")

    step = find_step(WORKFLOW, STEP)
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
                print(f"::error::MUTATION SURVIVED - reintroducing {label} broke "
                      f"nothing in this suite, so the suite is not testing that "
                      f"defect. Fix the scenarios, not the mutation.")
                failures.append(f"mutation survived: {label}")
    finally:
        shutil.rmtree(tmproot, ignore_errors=True)

    print(f"auto-release report: {len(SCENARIOS)} scenario(s), "
          f"{len(MUTATIONS)} mutation(s); {len(failures)} failure(s).")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
