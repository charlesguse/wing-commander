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
values -- each job's `result` and outputs -- with `gh`/`git` stubbed for the
two live reads the step still makes. Every attribution path the step has is
a scenario: the two quiet days, each verdict class, each job-result crash,
the collision, released (correlated and uncorrelated), branch-advanced, and
a real release failure (with and without a correlated run).

specs/048-correlated-release-dispatch (FR-007/FR-007a/FR-013) replaced the
step's `RELEASE_OUTCOME`/`RELEASE_RUN_ID` reads (a run's own conclusion)
with `TAG_MATCHES`/`CORRELATION`/`CORRELATED_RUN_ID`/`CORRELATED_RUN_URL`
(tag state, decided independently of any run) -- this harness's scenarios
and mutations were updated alongside that rewrite so the release-time
answer and this self-test cannot drift apart.

specs/049-single-home-release-idioms then moved the dedup-by-label
lookup/create/comment/close mechanics that used to live inline in this step
(shared, byte-for-byte, with auto-update-spec-kit.yml's four report sites)
into `.github/actions/_shared/durable-failure-issue`, a `uses:` step this
step's own script can no longer perform (a `run:` block cannot invoke a
composite action). The step under test here -- renamed "Determine this
run's outcome" -- now only DECIDES what happened and writes that decision
to `$GITHUB_OUTPUT` (`action`: report | close | empty, plus `title` and
`close-comment`) and to the failure-body file; the two follow-up `uses:`
steps in the real workflow read those outputs and call the composite. This
harness therefore asserts on the decision (action/title/close-comment/
body/summary), not on `gh` issue calls -- the composite's own
report/close/dedup mechanics are its own concern, not re-tested here.

It ends with MUTATION checks that put each defect back and assert the
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
STEP = "Determine this run's outcome"

BASH = None

# Since specs/049 moved the issue mechanics into the durable-failure-issue
# composite, the step's only remaining `gh` call is the branch-advanced/
# release-failed classifier's default-branch read. Any other invocation is
# a regression -- a report/close site that crept back inline, where Gate 60
# would also fail -- so the stub refuses it loudly instead of no-op'ing.
STUB_GH = r'''#!/usr/bin/env bash
if [ "$1 $2" = "repo view" ]; then
  printf '%s\n' "${GH_STUB_DEFAULT_BRANCH:-main}"
  exit 0
fi
echo "unexpected gh invocation: $*" >&2
exit 1
'''

# The report step's only `git` call is the branch-advanced/release-failed
# classifier's `git ls-remote ... refs/heads/main` (T012) -- a live read
# this harness answers with a scripted tip rather than the network.
STUB_GIT = r'''#!/usr/bin/env bash
if [ "$1" = "ls-remote" ]; then
  printf '%s\trefs/heads/main\n' "${GIT_STUB_CURRENT_TIP:-0000000000000000000000000000000000000000}"
  exit 0
fi
echo "unexpected git invocation: $*" >&2
exit 1
'''

RUN_URL = "https://github.com/charlesguse/wing-commander/actions/runs/777"
CORRELATED_RUN_URL = "https://github.com/charlesguse/wing-commander/actions/runs/4242"
HEAD = "0123456789abcdef0123456789abcdef01234567"
OTHER_SHA = "abcdefabcdefabcdefabcdefabcdefabcdefabcd"
PASS = json.dumps({"outcome": "pass", "verified_head": HEAD,
                   "mode": "container", "container_image_configured": True})
WRONG_OUTPUT = json.dumps({"outcome": "fail-wrong-output", "verified_head": HEAD,
                           "failing_check": "spec.md content",
                           "expected": "the fixture's heading",
                           "observed": "an empty file",
                           "evidence_url": "https://example.invalid/e2e",
                           "mode": "default-runner"})

# Every scenario starts from a run where nothing has happened yet -- every
# result `skipped`, every output empty -- and overrides what its situation
# sets. `action` is the decision the step wrote to $GITHUB_OUTPUT for the
# two follow-up composite steps to act on: "report", "close", or None (it
# decided nothing needed doing). `close_comment_contains` asserts on the
# note a "close" decision carries. `current_tip` feeds the ls-remote stub
# (defaults to HEAD -- the branch has not advanced).
REQUEST_TIME = "2024-01-01T00:00:00Z"

BASE = dict(DETECT_RESULT="skipped", VERIFY_RESULT="skipped",
            DECIDE_RESULT="skipped", DISPATCH_RESULT="skipped",
            HEAD_SHA="", HAS_NEW_WORK="", TAG_EXISTS="", LATEST_TAG="",
            VERDICT_JSON="", NEXT_VERSION="", COLLISION="",
            TAG_MATCHES="", CORRELATION="", CORRELATED_RUN_ID="",
            CORRELATED_RUN_URL="", REQUEST_TIME=REQUEST_TIME,
            DISPATCH_REJECTED="false", PAUSED="false")

SCENARIOS = [
    dict(
        name="detect crashed before writing outputs: infrastructure, filed, "
             "naming detect and this run -- not a quiet day (#325 case 1)",
        env=dict(DETECT_RESULT="failure"),
        action="report",
        body_contains=["infrastructure", "`detect`", RUN_URL, "unknown"],
        body_excludes=["release.yml was dispatched"],
        summary_contains="infrastructure failure",
        summary_excludes="no release tag exists yet",
    ),
    dict(
        name="run cancelled during detect: summarised, nothing filed",
        env=dict(DETECT_RESULT="cancelled"),
        action=None,
        summary_contains="cancelled",
    ),
    dict(
        name="quiet day with a baseline tag (FR-003): nothing filed, and "
             "a standing report from an earlier attempt is closed as stale "
             "-- the latest tag already points at HEAD",
        env=dict(DETECT_RESULT="success", HAS_NEW_WORK="false", TAG_EXISTS="true",
                 LATEST_TAG="v2.7.2", HEAD_SHA=HEAD),
        action="close",
        close_comment_contains="v2.7.2 already released",
        summary_contains="no new work since v2.7.2",
    ),
    dict(
        name="no baseline tag yet (FR-004): nothing filed",
        env=dict(DETECT_RESULT="success", HAS_NEW_WORK="false", TAG_EXISTS="false",
                 HEAD_SHA=HEAD),
        action=None,
        summary_contains="no release tag exists yet",
    ),
    dict(
        name="new work but verify-e2e crashed with no verdict: fail-infra "
             "naming the missing verdict and the job result",
        env=dict(DETECT_RESULT="success", HAS_NEW_WORK="true", TAG_EXISTS="true",
                 LATEST_TAG="v2.7.2", HEAD_SHA=HEAD, VERIFY_RESULT="failure"),
        action="report",
        body_contains=["infrastructure", "verify-e2e produced no verdict",
                       "job result: failure", RUN_URL],
        summary_contains="verification failed",
    ),
    dict(
        name="run cancelled during verify-e2e (a hung poll stopped by hand): "
             "summarised, nothing filed -- not an infrastructure failure",
        env=dict(DETECT_RESULT="success", HAS_NEW_WORK="true", TAG_EXISTS="true",
                 LATEST_TAG="v2.7.2", HEAD_SHA=HEAD, VERIFY_RESULT="cancelled"),
        action=None,
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
        action="report",
        body_contains=["infrastructure", "verify-e2e produced no verdict", "contract broken"],
        body_excludes=["the job stopped"],
    ),
    dict(
        name="a fail-infra verdict naming an unresolved container image "
             "(specs/054 MF1): infrastructure, never a pipeline defect, "
             "even though it came from the poll step's own terminal-state "
             "check rather than an earlier job crash",
        env=dict(DETECT_RESULT="success", HAS_NEW_WORK="true", TAG_EXISTS="true",
                 LATEST_TAG="v2.7.2", HEAD_SHA=HEAD, VERIFY_RESULT="success",
                 VERDICT_JSON=json.dumps({
                     "outcome": "fail-infra", "verified_head": HEAD,
                     "failing_check": "container image pulled/authorized for the stage that ran it",
                     "expected": "the reference image resolves and its registry credentials (if any) are accepted",
                     "observed": "verify-image-prerequisites failed: wing-commander verify-image-prerequisites: failed to pull ghcr.io/example/image",
                     "evidence_url": "https://github.com/owner/repo/actions/runs/555",
                     "mode": "container", "container_image_configured": False})),
        action="report",
        body_contains=["infrastructure", "container image pulled/authorized",
                       "https://github.com/owner/repo/actions/runs/555"],
        body_excludes=["pipeline defect"],
    ),
    dict(
        name="a fail-wrong-output verdict: pipeline defect, filed with the "
             "verdict's own fields",
        env=dict(DETECT_RESULT="success", HAS_NEW_WORK="true", TAG_EXISTS="true",
                 LATEST_TAG="v2.7.2", HEAD_SHA=HEAD, VERIFY_RESULT="success",
                 VERDICT_JSON=WRONG_OUTPUT),
        action="report",
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
        action="report",
        body_contains=["infrastructure", "`decide-version`", RUN_URL],
        body_excludes=["release.yml was dispatched", "release failure"],
        summary_excludes="release dispatch failed",
    ),
    dict(
        name="run cancelled during decide-version: summarised, nothing filed",
        env=dict(DETECT_RESULT="success", HAS_NEW_WORK="true", TAG_EXISTS="true",
                 LATEST_TAG="v2.7.2", HEAD_SHA=HEAD, VERIFY_RESULT="success",
                 VERDICT_JSON=PASS, DECIDE_RESULT="cancelled"),
        action=None,
        summary_contains="cancelled",
    ),
    dict(
        name="version collision: filed as a collision, no dispatch attempted",
        env=dict(DETECT_RESULT="success", HAS_NEW_WORK="true", TAG_EXISTS="true",
                 LATEST_TAG="v2.7.2", HEAD_SHA=HEAD, VERIFY_RESULT="success",
                 VERDICT_JSON=PASS, DECIDE_RESULT="success", NEXT_VERSION="v2.8.0",
                 COLLISION="true"),
        action="report",
        body_contains=["version collision", "v2.8.0"],
        summary_contains="version collision",
    ),
    dict(
        name="released, own run correlated (FR-007): the open failure "
             "issue is closed, nothing filed, the correlated run linked",
        env=dict(DETECT_RESULT="success", HAS_NEW_WORK="true", TAG_EXISTS="true",
                 LATEST_TAG="v2.7.2", HEAD_SHA=HEAD, VERIFY_RESULT="success",
                 VERDICT_JSON=PASS, DECIDE_RESULT="success", NEXT_VERSION="v2.8.0",
                 COLLISION="false", DISPATCH_RESULT="success",
                 TAG_MATCHES="true", CORRELATION="found",
                 CORRELATED_RUN_ID="4242", CORRELATED_RUN_URL=CORRELATED_RUN_URL),
        action="close",
        close_comment_contains="v2.8.0 released",
        summary_contains=f"released v2.8.0 (mode: container) -- [correlated run]({CORRELATED_RUN_URL})",
    ),
    dict(
        name="released, own run never correlated (Edge Case: the release "
             "happened but was never correlated) -- still reports released, "
             "the standing issue still closes (FR-007a)",
        env=dict(DETECT_RESULT="success", HAS_NEW_WORK="true", TAG_EXISTS="true",
                 LATEST_TAG="v2.7.2", HEAD_SHA=HEAD, VERIFY_RESULT="success",
                 VERDICT_JSON=PASS, DECIDE_RESULT="success", NEXT_VERSION="v2.8.0",
                 COLLISION="false", DISPATCH_RESULT="success",
                 TAG_MATCHES="true", CORRELATION="not-observed"),
        action="close",
        close_comment_contains="v2.8.0 released",
        summary_contains="released v2.8.0 (mode: container) -- own run not correlated",
    ),
    dict(
        name="released while a container-mode turn was paused (FR-009): "
             "reports the default-runner mode the run actually exercised, "
             "annotated as paused rather than a plain default-runner pass",
        env=dict(DETECT_RESULT="success", HAS_NEW_WORK="true", TAG_EXISTS="true",
                 LATEST_TAG="v2.7.2", HEAD_SHA=HEAD, VERIFY_RESULT="success",
                 VERDICT_JSON=json.dumps({"outcome": "pass", "verified_head": HEAD,
                                          "mode": "default-runner"}),
                 DECIDE_RESULT="success", NEXT_VERSION="v2.8.0",
                 COLLISION="false", DISPATCH_RESULT="success",
                 TAG_MATCHES="true", CORRELATION="found",
                 CORRELATED_RUN_ID="4242", CORRELATED_RUN_URL=CORRELATED_RUN_URL,
                 PAUSED="true"),
        action="close",
        close_comment_contains="v2.8.0 released",
        summary_contains=f"released v2.8.0 (mode: default-runner (container mode "
                         f"not exercised: paused)) -- [correlated run]({CORRELATED_RUN_URL})",
    ),
    dict(
        name="branch-advanced (FR-013): expected behaviour, nothing filed, "
             "names both the verified head and the observed tip",
        env=dict(DETECT_RESULT="success", HAS_NEW_WORK="true", TAG_EXISTS="true",
                 LATEST_TAG="v2.7.2", HEAD_SHA=HEAD, VERIFY_RESULT="success",
                 VERDICT_JSON=PASS, DECIDE_RESULT="success", NEXT_VERSION="v2.8.0",
                 COLLISION="false", DISPATCH_RESULT="success",
                 TAG_MATCHES="false", CORRELATION="not-observed"),
        current_tip=OTHER_SHA,
        action=None,
        summary_contains=f"the branch advanced past the verified head ({HEAD})",
    ),
    dict(
        name="not-observed correlation names the version and request time "
             "(FR-006)",
        env=dict(DETECT_RESULT="success", HAS_NEW_WORK="true", TAG_EXISTS="true",
                 LATEST_TAG="v2.7.2", HEAD_SHA=HEAD, VERIFY_RESULT="success",
                 VERDICT_JSON=PASS, DECIDE_RESULT="success", NEXT_VERSION="v2.8.0",
                 COLLISION="false", DISPATCH_RESULT="success",
                 TAG_MATCHES="false", CORRELATION="not-observed"),
        current_tip=OTHER_SHA,
        action=None,
        summary_contains=f"not observed within the correlation window for v2.8.0 requested at {REQUEST_TIME}",
    ),
    dict(
        name="dispatch rejected outright: distinguished from both a run "
             "failure and a run simply not being observed (FR-006/SC-004)",
        env=dict(DETECT_RESULT="success", HAS_NEW_WORK="true", TAG_EXISTS="true",
                 LATEST_TAG="v2.7.2", HEAD_SHA=HEAD, VERIFY_RESULT="success",
                 VERDICT_JSON=PASS, DECIDE_RESULT="success", NEXT_VERSION="v2.8.0",
                 COLLISION="false", DISPATCH_RESULT="success",
                 TAG_MATCHES="false", CORRELATION="not-observed",
                 DISPATCH_REJECTED="true"),
        action="report",
        body_contains=[f"the dispatch of v2.8.0 requested at {REQUEST_TIME} was rejected outright"],
        body_excludes=["own run was not observed within the correlation window"],
        summary_contains="release dispatch failed for v2.8.0",
    ),
    dict(
        name="dispatch-release crashed with no outcome: infrastructure "
             "naming dispatch-release",
        env=dict(DETECT_RESULT="success", HAS_NEW_WORK="true", TAG_EXISTS="true",
                 LATEST_TAG="v2.7.2", HEAD_SHA=HEAD, VERIFY_RESULT="success",
                 VERDICT_JSON=PASS, DECIDE_RESULT="success", NEXT_VERSION="v2.8.0",
                 COLLISION="false", DISPATCH_RESULT="failure"),
        action="report",
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
        action=None,
        summary_contains="did not run",
    ),
    dict(
        name="release-failed, own run correlated: branch never moved, no "
             "tag landed -- filed, linking the correlated run",
        env=dict(DETECT_RESULT="success", HAS_NEW_WORK="true", TAG_EXISTS="true",
                 LATEST_TAG="v2.7.2", HEAD_SHA=HEAD, VERIFY_RESULT="success",
                 VERDICT_JSON=PASS, DECIDE_RESULT="success", NEXT_VERSION="v2.8.0",
                 COLLISION="false", DISPATCH_RESULT="success",
                 TAG_MATCHES="false", CORRELATION="found",
                 CORRELATED_RUN_ID="9999", CORRELATED_RUN_URL=CORRELATED_RUN_URL),
        action="report",
        body_contains=["pipeline defect", CORRELATED_RUN_URL],
        body_excludes=["not correlated (see tag state below)"],
        summary_contains="release dispatch failed for v2.8.0",
    ),
    dict(
        name="release-failed, own run not correlated (ambiguous): filed, "
             "the diagnostic gap named honestly rather than pointing at a "
             "run that was never identified (FR-005/FR-006)",
        env=dict(DETECT_RESULT="success", HAS_NEW_WORK="true", TAG_EXISTS="true",
                 LATEST_TAG="v2.7.2", HEAD_SHA=HEAD, VERIFY_RESULT="success",
                 VERDICT_JSON=PASS, DECIDE_RESULT="success", NEXT_VERSION="v2.8.0",
                 COLLISION="false", DISPATCH_RESULT="success",
                 TAG_MATCHES="false", CORRELATION="ambiguous"),
        action="report",
        body_contains=["pipeline defect", "not correlated (see tag state below)",
                       f"could not be uniquely identified among the candidate runs "
                       f"matched for v2.8.0 requested at {REQUEST_TIME}"],
        summary_contains="release dispatch failed for v2.8.0",
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


VERDICT_SCRIPT_REL = os.path.join(".github", "actions", "_shared", "auto-release-verdict.sh")


def _stage_verdict_script(workdir):
    """Copy the real verdict helper into workdir at its shipped relative
    path. The step under test resolves it as `.github/actions/_shared/
    auto-release-verdict.sh` -- correct when the real workflow runs from a
    repository checkout, but this harness's workdir is a bare tempdir, so
    the same relative path has to be staged there for each scenario."""
    src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                       "actions", "_shared", "auto-release-verdict.sh")
    dst = os.path.join(workdir, VERDICT_SCRIPT_REL)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copyfile(src, dst)


def run_scenario(script, env, sc, tmproot):
    workdir = tempfile.mkdtemp(dir=tmproot)
    runner_temp = tempfile.mkdtemp(dir=tmproot)
    bindir = tempfile.mkdtemp(dir=tmproot)
    _stage_verdict_script(workdir)

    gh_path = os.path.join(bindir, "gh")
    with open(gh_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(STUB_GH)
    os.chmod(gh_path, 0o755)

    git_path = os.path.join(bindir, "git")
    with open(git_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(STUB_GIT)
    os.chmod(git_path, 0o755)

    run_env = dict(env)
    run_env.update(BASE)
    run_env.update(sc["env"])
    run_env["PATH"] = bindir + os.pathsep + os.environ["PATH"]
    run_env["GITHUB_SERVER_URL"] = "https://github.com"
    run_env["GITHUB_REPOSITORY"] = "charlesguse/wing-commander"
    run_env["GITHUB_RUN_ID"] = "777"
    run_env["GIT_STUB_CURRENT_TIP"] = sc.get("current_tip") or run_env.get("HEAD_SHA") or HEAD

    rc, out, outputs, summary = run_step(BASH, script, workdir, run_env, runner_temp)
    body = ""
    body_path = os.path.join(runner_temp, "auto-release-failure-body.md")
    if os.path.exists(body_path):
        with open(body_path, encoding="utf-8") as fh:
            body = fh.read()
    for d in (workdir, runner_temp, bindir):
        shutil.rmtree(d, ignore_errors=True)
    return rc, out, summary, outputs, body


def suite(script, env, tmproot):
    failures = []
    for sc in SCENARIOS:
        tag = f"[{sc['name']}]"
        rc, out, summary, outputs, body = run_scenario(script, env, sc, tmproot)
        if rc != 0:
            failures.append(f"{tag} the step exited {rc}:\n{out}")
            continue
        action = outputs.get("action") or None
        if action != sc["action"]:
            failures.append(f"{tag} expected action={sc['action']!r}, got "
                            f"{action!r}; outputs: {outputs}")
        # The composite the decision feeds needs a title to create an issue
        # with and a comment to close one with; an empty one reaches GitHub
        # as a blank title or "Resolved: " with nothing after it.
        if sc["action"] == "report" and not outputs.get("title"):
            failures.append(f"{tag} action=report but no title output was set")
        if sc["action"] == "close" and not outputs.get("close-comment"):
            failures.append(f"{tag} action=close but no close-comment output was set")
        want_note = sc.get("close_comment_contains")
        if want_note and want_note not in (outputs.get("close-comment") or ""):
            failures.append(f"{tag} close-comment lacks {want_note!r}: "
                            f"{outputs.get('close-comment')!r}")
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
    old = 'if [ "$DISPATCH_RESULT" = "failure" ]; then'
    if script.count(old) != 1:
        sys.exit(f"::error::verify-auto-release-report: expected exactly one "
                 f"{old!r} to mutate, found {script.count(old)} — the step text "
                 f"may have changed shape; update this harness alongside it.")
    return script.replace(old, 'if [ "mutated-$DISPATCH_RESULT" = "failure" ]; then', 1)


def mut_no_verdict_always_stopped(script):
    old = 'if [ "$VERIFY_RESULT" = "success" ]; then'
    if script.count(old) != 1:
        sys.exit("::error::verify-auto-release-report: could not locate the "
                 "no-verdict wording branch to mutate — the step text may have "
                 "changed shape; update this harness alongside it.")
    return script.replace(old, 'if false; then', 1)


def mut_branch_advanced_reported_as_failure(script):
    """specs/048 FR-013: the branch-advanced/release-failed split must be
    live, not skipped -- put back "the tip never moved" as the only answer."""
    old = 'if [ "$current_tip" != "$HEAD_SHA" ]; then'
    if script.count(old) != 1:
        sys.exit("::error::verify-auto-release-report: could not locate the "
                 "branch-advanced classifier to mutate — the step text may "
                 "have changed shape; update this harness alongside it.")
    return script.replace(old, 'if false; then', 1)


def mut_dispatch_rejected_collapsed_into_not_observed(script):
    """specs/048 FR-006/SC-004: "the request was rejected" must read
    distinctly from "own run was not observed" -- put back the pre-T024
    shape where a rejected dispatch fell through to the same not-observed
    wording."""
    old = 'if [ "$DISPATCH_REJECTED" = "true" ]; then'
    if script.count(old) != 1:
        sys.exit("::error::verify-auto-release-report: could not locate the "
                 "dispatch-rejected branch to mutate — the step text may "
                 "have changed shape; update this harness alongside it.")
    return script.replace(old, 'if false; then', 1)


def mut_released_ignores_tag_matches(script):
    """specs/048 FR-007/FR-007a: `released` must come from TAG_MATCHES
    alone -- put back a correlation-only decision (the pre-048 defect this
    feature exists to close, reworded onto the new variable names)."""
    old = 'if [ "$TAG_MATCHES" = "true" ]; then'
    if script.count(old) != 1:
        sys.exit("::error::verify-auto-release-report: could not locate the "
                 "TAG_MATCHES released branch to mutate — the step text may "
                 "have changed shape; update this harness alongside it.")
    return script.replace(old, 'if [ "$CORRELATION" = "found" ]; then', 1)


MUTATIONS = [
    ("report ignoring detect's job result (#325 case 1)", mut_ignore_detect_result),
    ("report filing a cancelled verify-e2e as infrastructure", mut_ignore_verify_result),
    ("a succeeded verify-e2e with no verdict described as 'the job stopped'",
     mut_no_verdict_always_stopped),
    ("report ignoring decide-version's job result (#325 case 2)", mut_ignore_decide_result),
    ("report ignoring dispatch-release's job result", mut_ignore_dispatch_result),
    ("branch-advanced always reported as a release failure (FR-013)",
     mut_branch_advanced_reported_as_failure),
    ("`released` decided from correlation instead of tag state (FR-007/FR-007a)",
     mut_released_ignores_tag_matches),
    ("a rejected dispatch collapsed into 'not observed' wording (FR-006/SC-004)",
     mut_dispatch_rejected_collapsed_into_not_observed),
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
