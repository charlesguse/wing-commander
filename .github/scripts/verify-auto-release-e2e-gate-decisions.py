#!/usr/bin/env python3
"""Gate 66: the two e2e gate-decision scripts cover every documented branch.

specs/055-unattended-e2e-gates/contracts/gate-decision-scripts.md is the
contract for two pure scripts auto-release.yml's `poll` step calls to
decide the clarification and PR-merge gates
(.github/actions/_shared/auto-release-e2e-clarify-decision.sh and
.github/actions/_shared/auto-release-e2e-merge-decision.sh). Both are pure
functions of already-fetched JSON (Constitution VIII, research.md D5/D6) --
no `gh` call, no network -- so this harness EXECUTES the shipped scripts
directly against fixture JSON, rather than a copy of their logic.

Follows verify-auto-release-report.py's checked-in-fixture-plus-mutation-
check style: every documented branch is a scenario, then MUTATION checks
put each defect back and assert the suite then fails. A test that cannot
fail is not a test.

Renamed from "Gate 63" to "Gate 66" in lint-workflows.yml to clear a
numbering collision with two other features landed on the same base (see
that file's own comment) -- this docstring and the self-test banner below
now say 66 to match (maintainer feedback on PR #389: the two had drifted).

Usage: python3 .github/scripts/verify-auto-release-e2e-gate-decisions.py
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

import subprocess  # noqa: E402

# Resolved from this file's own location, not the process cwd -- run-local-
# gates.py's parallel pool runs every gate as its own subprocess with the
# same inherited cwd, but a relative path here still ties this gate to
# "invoked from the repository root" for no reason, unlike verify-gate-
# 106.py's REPO_ROOT, which this mirrors.
REPO_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")

CLARIFY_SCRIPT = os.path.join(REPO_ROOT, ".github", "actions", "_shared",
                               "auto-release-e2e-clarify-decision.sh")
MERGE_SCRIPT = os.path.join(REPO_ROOT, ".github", "actions", "_shared",
                             "auto-release-e2e-merge-decision.sh")
ALLOWANCE_SCRIPT = os.path.join(REPO_ROOT, ".github", "actions", "_shared",
                                 "auto-release-e2e-gate-allowance-decision.sh")
POLL_WORKFLOW = os.path.join(REPO_ROOT, ".github", "workflows", "auto-release.yml")

BASH = None

PREPARED_ANSWER = (
    'Use the moment this workflow run started as "the timestamp." On a '
    "repeat run, overwrite the existing file rather than adding a new "
    "one. For anything else this question doesn't cover, use your own "
    "best judgement and proceed."
)

OPEN_MARKER = ("[!IMPORTANT]\nAnswer the open clarification questions in "
               "the comment below.")
REMAINING_MARKER = ("[!IMPORTANT]\nAnswer the remaining clarification "
                     "questions in the comment below.")

ISSUE_AUTHOR_ID = "555"


def comment(id_, login, user_id, created_at, body="the answer",
            user_type="User", association="NONE"):
    return {"id": id_, "user": {"login": login, "id": user_id, "type": user_type},
            "author_association": association, "body": body, "created_at": created_at}


def marker(id_, created_at, body=OPEN_MARKER):
    return comment(id_, "wing-commander[bot]", "1", created_at, body=body,
                   user_type="Bot", association="NONE")


def run_script(script_path, args, stdin_json):
    proc = subprocess.run([BASH, script_path, *args], input=stdin_json,
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace")
    return proc.returncode, proc.stdout, proc.stderr


# --------------------------------------------------------------------------
# Clarify-decision scenarios (contracts/gate-decision-scripts.md)
# --------------------------------------------------------------------------
CLARIFY_DECIDE_SCENARIOS = [
    dict(name="no marker comment at all: none",
         comments=[comment("c1", "wing-commander[bot]", "1", "2026-01-01T00:00:00Z",
                            body="hello", user_type="Bot")],
         author_id="999", rounds="0", expect_head="none"),
    dict(name="marker open, round 0: reply with the exact prepared answer",
         comments=[marker("c1", "2026-01-01T00:00:00Z")],
         author_id="999", rounds="0", expect_head="reply",
         expect_body=PREPARED_ANSWER),
    dict(name="marker open (remaining-questions wording), round 2: still replies",
         comments=[marker("c1", "2026-01-01T00:00:00Z", body=REMAINING_MARKER)],
         author_id="999", rounds="2", expect_head="reply",
         expect_body=PREPARED_ANSWER),
    dict(name="marker open, round 3 (bound exhausted): exhausted",
         comments=[marker("c1", "2026-01-01T00:00:00Z")],
         author_id="999", rounds="3", expect_head="exhausted"),
    dict(name="marker open, a qualifying (COLLABORATOR) reply postdates it: wait",
         comments=[marker("c1", "2026-01-01T00:00:00Z"),
                   comment("c2", "a-maintainer", "42", "2026-01-01T00:05:00Z",
                           association="COLLABORATOR")],
         author_id="999", rounds="1", expect_head="wait"),
    dict(name="marker open, the issue's own author (by id, NONE association) replies: wait",
         comments=[marker("c1", "2026-01-01T00:00:00Z"),
                   comment("c2", "the-reporter", ISSUE_AUTHOR_ID, "2026-01-01T00:05:00Z",
                           association="NONE")],
         author_id=ISSUE_AUTHOR_ID, rounds="0", expect_head="wait"),
    dict(name="marker open, a bot comment postdates it: still unanswered (reply) -- "
              "the original deadlock this feature closes",
         comments=[marker("c1", "2026-01-01T00:00:00Z"),
                   comment("c2", "metrics-bot[bot]", "9", "2026-01-01T00:05:00Z",
                           body="rollup", user_type="Bot", association="NONE")],
         author_id="999", rounds="0", expect_head="reply",
         expect_body=PREPARED_ANSWER),
    dict(name="marker open, a non-qualifying human (NONE, not the issue author) postdates it: "
              "still unanswered (reply)",
         comments=[marker("c1", "2026-01-01T00:00:00Z"),
                   comment("c2", "a-random-passerby", "777", "2026-01-01T00:05:00Z",
                           association="NONE")],
         author_id="999", rounds="0", expect_head="reply",
         expect_body=PREPARED_ANSWER),
    dict(name="marker open, a Bot account with a qualifying (COLLABORATOR) association "
              "postdates it: still unanswered (reply) -- the Bot check, not merely "
              "association, is what excludes it",
         comments=[marker("c1", "2026-01-01T00:00:00Z"),
                   comment("c2", "wing-commander[bot]", "1", "2026-01-01T00:05:00Z",
                           user_type="Bot", association="COLLABORATOR")],
         author_id="999", rounds="0", expect_head="reply",
         expect_body=PREPARED_ANSWER),
]

CLARIFY_SATISFIED_SCENARIOS = [
    dict(name="no markers ever: ok (vacuous)",
         comments=[comment("c1", "someone", "2", "2026-01-01T00:00:00Z", body="hi")],
         author_id="999", expect="ok"),
    dict(name="one marker, one qualifying reply after: ok",
         comments=[marker("c1", "2026-01-01T00:00:00Z"),
                   comment("c2", "a-maintainer", "42", "2026-01-01T00:05:00Z",
                           association="MEMBER")],
         author_id="999", expect="ok"),
    dict(name="one marker, only a non-qualifying reply after: unsatisfied",
         comments=[marker("c1", "2026-01-01T00:00:00Z"),
                   comment("c2", "metrics-bot[bot]", "9", "2026-01-01T00:05:00Z",
                           user_type="Bot", association="NONE")],
         author_id="999", expect="unsatisfied"),
    dict(name="two markers, only the first answered: unsatisfied",
         comments=[marker("c1", "2026-01-01T00:00:00Z"),
                   comment("c2", "a-maintainer", "42", "2026-01-01T00:05:00Z",
                           association="OWNER"),
                   marker("c3", "2026-01-01T00:10:00Z", body=REMAINING_MARKER)],
         author_id="999", expect="unsatisfied"),
    dict(name="two markers, both answered: ok",
         comments=[marker("c1", "2026-01-01T00:00:00Z"),
                   comment("c2", "a-maintainer", "42", "2026-01-01T00:05:00Z",
                           association="OWNER"),
                   marker("c3", "2026-01-01T00:10:00Z", body=REMAINING_MARKER),
                   comment("c4", "a-maintainer", "42", "2026-01-01T00:15:00Z",
                           association="OWNER")],
         author_id="999", expect="ok"),
]

CLARIFY_MARKERS_SCENARIOS = [
    dict(name="markers mode returns every marker, oldest first",
         comments=[marker("c2", "2026-01-01T00:10:00Z", body=REMAINING_MARKER),
                   marker("c1", "2026-01-01T00:00:00Z"),
                   comment("c3", "someone", "2", "2026-01-01T00:05:00Z", body="not a marker")],
         expect_ids=["c1", "c2"]),
]


def run_clarify_suite(script_path):
    failures = []
    for sc in CLARIFY_DECIDE_SCENARIOS:
        tag = f"[clarify decide: {sc['name']}]"
        comments_json = json.dumps(sc["comments"])
        rc, out, err = run_script(script_path, ["decide", sc["author_id"], sc["rounds"]], comments_json)
        if rc != 0:
            failures.append(f"{tag} script exited {rc}: {out}{err}")
            continue
        lines = out.splitlines()
        head = lines[0] if lines else ""
        if head != sc["expect_head"]:
            failures.append(f"{tag} expected head {sc['expect_head']!r}, got {head!r} (full: {out!r})")
            continue
        if "expect_body" in sc:
            body = "\n".join(lines[1:])
            if body != sc["expect_body"]:
                failures.append(f"{tag} reply body mismatch:\n  want: {sc['expect_body']!r}\n  got:  {body!r}")
    for sc in CLARIFY_SATISFIED_SCENARIOS:
        tag = f"[clarify satisfied: {sc['name']}]"
        comments_json = json.dumps(sc["comments"])
        rc, out, err = run_script(script_path, ["satisfied", sc["author_id"]], comments_json)
        if rc != 0:
            failures.append(f"{tag} script exited {rc}: {out}{err}")
            continue
        got = out.strip()
        if got != sc["expect"]:
            failures.append(f"{tag} expected {sc['expect']!r}, got {got!r}")
    for sc in CLARIFY_MARKERS_SCENARIOS:
        tag = f"[clarify markers: {sc['name']}]"
        comments_json = json.dumps(sc["comments"])
        rc, out, err = run_script(script_path, ["markers"], comments_json)
        if rc != 0:
            failures.append(f"{tag} script exited {rc}: {out}{err}")
            continue
        try:
            got_ids = [c["id"] for c in json.loads(out)]
        except (json.JSONDecodeError, TypeError, KeyError) as exc:
            failures.append(f"{tag} could not parse output as a JSON array of comments: {exc} (full: {out!r})")
            continue
        if got_ids != sc["expect_ids"]:
            failures.append(f"{tag} expected ids {sc['expect_ids']!r}, got {got_ids!r}")
    return failures


# --------------------------------------------------------------------------
# Merge-decision scenarios (contracts/gate-decision-scripts.md)
# --------------------------------------------------------------------------
DEFAULT_BASE = "main"


def pr(number, head_ref, base_ref=DEFAULT_BASE, mergeable="MERGEABLE",
       merge_state="CLEAN", is_draft=False, state="OPEN", status_checks=None):
    return {"number": number, "headRefName": head_ref, "baseRefName": base_ref,
            "mergeable": mergeable, "mergeStateStatus": merge_state,
            "isDraft": is_draft, "state": state,
            "statusCheckRollup": status_checks if status_checks is not None else []}


COMPLETED_CHECK = {"status": "COMPLETED", "conclusion": "FAILURE"}
PENDING_CHECK = {"status": "IN_PROGRESS", "conclusion": None}
# Legacy commit StatusContext shape -- no `status`/`conclusion` at all, only
# `state` (SUCCESS/PENDING/ERROR/FAILURE). A required check backed by the
# Status API (not a Check Run) reports this shape in statusCheckRollup.
STATUS_CONTEXT_SUCCESS = {"state": "SUCCESS"}
STATUS_CONTEXT_PENDING = {"state": "PENDING"}
# EXPECTED: the state a required legacy check reports before any status has
# been posted for the commit at all -- still pending, not yet resolved.
STATUS_CONTEXT_EXPECTED = {"state": "EXPECTED"}

MERGE_SCENARIOS = [
    dict(name="empty array: none", prs=[], prefix="spec-draft/", slug="055-foo",
         expected_base=DEFAULT_BASE, expect_head="none"),
    dict(name="mismatched headRefName: wrong-attempt",
         prs=[pr(1, "spec-draft/054-bar")],
         prefix="spec-draft/", slug="055-foo", expected_base=DEFAULT_BASE,
         expect_head="wrong-attempt"),
    dict(name="right head, mismatched baseRefName: wrong-base",
         prs=[pr(1, "spec-draft/055-foo", base_ref="some-other-branch")],
         prefix="spec-draft/", slug="055-foo", expected_base=DEFAULT_BASE,
         expect_head="wrong-base"),
    dict(name="draft PR: wait",
         prs=[pr(1, "spec-draft/055-foo", is_draft=True)],
         prefix="spec-draft/", slug="055-foo", expected_base=DEFAULT_BASE,
         expect_head="wait"),
    dict(name="mergeStateStatus UNKNOWN: wait",
         prs=[pr(1, "plan/055-foo", base_ref="spec/055-foo", merge_state="UNKNOWN")],
         prefix="plan/", slug="055-foo", expected_base="spec/055-foo",
         expect_head="wait"),
    dict(name="mergeStateStatus BEHIND: wait",
         prs=[pr(1, "plan/055-foo", base_ref="spec/055-foo", merge_state="BEHIND")],
         prefix="plan/", slug="055-foo", expected_base="spec/055-foo",
         expect_head="wait"),
    dict(name="mergeable CONFLICTING: conflicting",
         prs=[pr(1, "spec/055-foo", mergeable="CONFLICTING")],
         prefix="spec/", slug="055-foo", expected_base=DEFAULT_BASE,
         expect_head="conflicting"),
    dict(name="mergeStateStatus BLOCKED, no pending check: blocked",
         prs=[pr(1, "spec/055-foo", merge_state="BLOCKED",
                 status_checks=[COMPLETED_CHECK])],
         prefix="spec/", slug="055-foo", expected_base=DEFAULT_BASE,
         expect_head="blocked"),
    dict(name="mergeStateStatus BLOCKED, a check still running: blocked-pending, not durably blocked",
         prs=[pr(1, "spec/055-foo", merge_state="BLOCKED",
                 status_checks=[COMPLETED_CHECK, PENDING_CHECK])],
         prefix="spec/", slug="055-foo", expected_base=DEFAULT_BASE,
         expect_head="blocked-pending"),
    dict(name="mergeStateStatus BLOCKED, no check has registered yet (freshly opened PR): blocked-pending, not durably blocked",
         prs=[pr(1, "spec/055-foo", merge_state="BLOCKED", status_checks=[])],
         prefix="spec/", slug="055-foo", expected_base=DEFAULT_BASE,
         expect_head="blocked-pending"),
    dict(name="mergeStateStatus BLOCKED, a legacy StatusContext (state, no status/conclusion) still pending: blocked-pending",
         prs=[pr(1, "spec/055-foo", merge_state="BLOCKED",
                 status_checks=[STATUS_CONTEXT_PENDING])],
         prefix="spec/", slug="055-foo", expected_base=DEFAULT_BASE,
         expect_head="blocked-pending"),
    dict(name="mergeStateStatus BLOCKED, a legacy StatusContext (state, no status/conclusion) resolved: blocked",
         prs=[pr(1, "spec/055-foo", merge_state="BLOCKED",
                 status_checks=[STATUS_CONTEXT_SUCCESS])],
         prefix="spec/", slug="055-foo", expected_base=DEFAULT_BASE,
         expect_head="blocked"),
    dict(name="mergeStateStatus BLOCKED, a legacy StatusContext in EXPECTED "
              "(no status has posted yet): blocked-pending, not durably blocked",
         prs=[pr(1, "spec/055-foo", merge_state="BLOCKED",
                 status_checks=[STATUS_CONTEXT_EXPECTED])],
         prefix="spec/", slug="055-foo", expected_base=DEFAULT_BASE,
         expect_head="blocked-pending"),
    dict(name="clean and mergeable: merge <number>",
         prs=[pr(42, "spec-draft/055-foo")], prefix="spec-draft/", slug="055-foo",
         expected_base=DEFAULT_BASE, expect_head="merge", expect_number="42"),
]


def run_merge_suite(script_path):
    failures = []
    for sc in MERGE_SCENARIOS:
        tag = f"[merge: {sc['name']}]"
        prs_json = json.dumps(sc["prs"])
        rc, out, err = run_script(script_path, [sc["prefix"], sc["slug"], sc["expected_base"]], prs_json)
        if rc != 0:
            failures.append(f"{tag} script exited {rc}: {out}{err}")
            continue
        lines = out.splitlines()
        head = lines[0] if lines else ""
        if head != sc["expect_head"]:
            failures.append(f"{tag} expected head {sc['expect_head']!r}, got {head!r} (full: {out!r})")
            continue
        if "expect_number" in sc:
            number = lines[1] if len(lines) > 1 else ""
            if number != sc["expect_number"]:
                failures.append(f"{tag} expected PR number {sc['expect_number']!r}, got {number!r}")
    return failures


# --------------------------------------------------------------------------
# Allowance-decision scenarios (contracts/gate-allowance-decision.md)
# --------------------------------------------------------------------------
ALLOWANCE_SCENARIOS = [
    dict(name="blocked-pending, no prior blocked_since: start",
         merge_decision="blocked-pending", blocked_since="", now="100",
         allowance_seconds="1200", expect="start"),
    dict(name="blocked-pending, elapsed under the allowance: wait",
         merge_decision="blocked-pending", blocked_since="100", now="500",
         allowance_seconds="1200", expect="wait"),
    dict(name="blocked-pending, elapsed exactly at the allowance: stall",
         merge_decision="blocked-pending", blocked_since="100", now="1300",
         allowance_seconds="1200", expect="stall"),
    dict(name="blocked-pending, elapsed past the allowance: stall",
         merge_decision="blocked-pending", blocked_since="0", now="1500",
         allowance_seconds="1200", expect="stall"),
    dict(name="a merge decision (gate resolved to a pass) with a previously-set "
              "blocked_since: clear",
         merge_decision="merge", blocked_since="100", now="500",
         allowance_seconds="1200", expect="clear"),
    dict(name="a plain wait (draft PR / UNKNOWN / BEHIND) with a previously-set "
              "blocked_since: clear",
         merge_decision="wait", blocked_since="100", now="500",
         allowance_seconds="1200", expect="clear"),
]


def run_allowance_suite(script_path):
    failures = []
    for sc in ALLOWANCE_SCENARIOS:
        tag = f"[allowance: {sc['name']}]"
        rc, out, err = run_script(script_path,
                                   [sc["merge_decision"], sc["blocked_since"],
                                    sc["now"], sc["allowance_seconds"]], "")
        if rc != 0:
            failures.append(f"{tag} script exited {rc}: {out}{err}")
            continue
        got = out.strip()
        if got != sc["expect"]:
            failures.append(f"{tag} expected {sc['expect']!r}, got {got!r}")
    return failures


def run_all(clarify_path, merge_path, allowance_path):
    return (run_clarify_suite(clarify_path) + run_merge_suite(merge_path)
            + run_allowance_suite(allowance_path))


# --------------------------------------------------------------------------
# Poll-budget clamp scenario (specs/070-blocked-gate-dry-run, fold review on
# #533): a gate that first goes blocked-pending late enough in the poll
# budget that its allowance cannot fully elapse before the `poll` step's own
# `while [ "$SECONDS" -lt "$POLL_BUDGET_SECONDS" ]` condition goes false must
# still end the attempt as that gate's stall, not the generic timeout.
# Neither decision script above has any notion of the poll budget (both are
# pure functions of their own arguments, per contracts/gate-allowance-
# decision.md), so this cannot be exercised as another ALLOWANCE_SCENARIOS
# entry -- it EXECUTES the real "poll" step out of auto-release.yml
# (find_step/run_step), the same way verify-auto-release-specs-fallback.py's
# Gate 91 already does for a different corner of this step, rather than
# re-deriving the clamp as a third pure script (CLAUDE.md's single-home
# rule; this feature registers no new gate, research.md D5).
# --------------------------------------------------------------------------
POLL_STEP_NAME = "Poll the test repository to a verdict"

POLL_E2E_REPO = "wc-fixture/test-repo"
POLL_ISSUE = "42"
POLL_SLUG = "070-foo"

# POLL_BUDGET_SECONDS is deliberately tiny (not production's 8100) so this
# proves the clamp without a real multi-minute wait: the spec-draft gate
# goes blocked-pending on the very first observation (SECONDS~=0), the
# budget expires a couple of real seconds later, and
# GATE_BLOCKED_ALLOWANCE_SECONDS is left at production's real 1200 to prove
# elapsed time is nowhere close to it -- exactly the "allowance not clamped
# to the remaining budget" shape the fold review found.
POLL_CLAMP_ENV = {
    "GH_TOKEN": "dummy-gh-token",
    "HARNESS_TOKEN": "dummy-harness-token",
    "HARNESS_LOGIN": "machine-acct",
    "E2E_REPO": POLL_E2E_REPO,
    "DEFAULT_BRANCH": "main",
    "ISSUE": POLL_ISSUE,
    "ISSUE_URL": f"https://github.com/{POLL_E2E_REPO}/issues/{POLL_ISSUE}",
    "HEAD_SHA": "a" * 40,
    "POLL_BUDGET_SECONDS": "2",
    "GATE_BLOCKED_ALLOWANCE_SECONDS": "1200",
    "MAX_CLARIFICATION_ROUNDS": "3",
    "MODE": "default-runner",
}

# Keeps the spec-draft gate permanently BLOCKED with an empty
# statusCheckRollup (a freshly opened PR, per auto-release-e2e-merge-
# decision.sh -- "blocked-pending") and the plan/finalize gates absent
# ("none"); the issue itself never reaches a terminal state. Any `gh`
# invocation this stub does not recognise fails loudly (Gate 91's own
# idiom) rather than no-op'ing, so an unstubbed read is a hard error here,
# not a silently-green pass.
POLL_CLAMP_STUB_GH = '''#!/usr/bin/env bash
case "$*" in
  "api repos/wc-fixture/test-repo/issues/42 --jq .user.id")
    printf '1\\n'
    exit 0
    ;;
  "api repos/wc-fixture/test-repo/issues/42/comments --paginate --jq"*)
    exit 0
    ;;
  "pr list --repo wc-fixture/test-repo --state open --json headRefName,title")
    printf '%s\\n' '[{"headRefName":"spec-draft/070-foo","title":"spec-draft: 070-foo (#42)"}]'
    exit 0
    ;;
  "pr list --repo wc-fixture/test-repo --head spec-draft/070-foo --json number,headRefName,baseRefName,mergeable,mergeStateStatus,isDraft,state,statusCheckRollup")
    printf '%s\\n' '[{"number":7,"headRefName":"spec-draft/070-foo","baseRefName":"main","mergeable":"UNKNOWN","mergeStateStatus":"BLOCKED","isDraft":false,"state":"OPEN","statusCheckRollup":[]}]'
    exit 0
    ;;
  "pr list --repo wc-fixture/test-repo --head plan/070-foo --json number,headRefName,baseRefName,mergeable,mergeStateStatus,isDraft,state,statusCheckRollup")
    printf '[]\\n'
    exit 0
    ;;
  "pr list --repo wc-fixture/test-repo --head spec/070-foo --json number,headRefName,baseRefName,mergeable,mergeStateStatus,isDraft,state,statusCheckRollup")
    printf '[]\\n'
    exit 0
    ;;
  "issue view 42 --repo wc-fixture/test-repo --json state,labels")
    printf '%s\\n' '{"state":"OPEN","labels":[{"name":"stage:implement"}]}'
    exit 0
    ;;
  *)
    echo "unexpected gh invocation: $*" >&2
    exit 1
    ;;
esac
'''

# The loop's `sleep 30`/`sleep 60` are stubbed to no-ops so this scenario is
# bound only by how long real wall-clock time takes to cross the tiny
# POLL_BUDGET_SECONDS above, not by the production sleep durations.
POLL_CLAMP_STUB_SLEEP = "#!/usr/bin/env bash\nexit 0\n"

# The step invokes each of these by its repo-root-relative path -- copied
# into a scratch workdir the same way Gate 91 (verify-auto-release-specs-
# fallback.py) already does, since run_step executes the extracted step with
# workdir as its cwd, not the repository root.
POLL_CLAMP_SHARED_SCRIPTS = [
    "auto-release-verdict.sh",
    "auto-release-e2e-clarify-decision.sh",
    "auto-release-e2e-merge-decision.sh",
    "auto-release-e2e-gate-allowance-decision.sh",
]


def run_poll_clamp_suite(workflow_path):
    tag = ("[poll budget clamp: a gate blocked-pending late in the poll "
           "budget stalls, not the generic timeout]")
    step = find_step(workflow_path, POLL_STEP_NAME)
    script = str(step["run"])
    if "${{" in script:
        return [f"{tag} the extracted run: block contains an unresolved "
                f"${{{{ }}}} expression"]
    tmproot = tempfile.mkdtemp()
    try:
        workdir = tempfile.mkdtemp(dir=tmproot)
        runner_temp = tempfile.mkdtemp(dir=tmproot)
        bindir = tempfile.mkdtemp(dir=tmproot)
        shared_dir = os.path.join(workdir, ".github", "actions", "_shared")
        os.makedirs(shared_dir, exist_ok=True)
        for name in POLL_CLAMP_SHARED_SCRIPTS:
            shutil.copyfile(os.path.join(REPO_ROOT, ".github", "actions", "_shared", name),
                             os.path.join(shared_dir, name))
        gh_path = os.path.join(bindir, "gh")
        with open(gh_path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(POLL_CLAMP_STUB_GH)
        os.chmod(gh_path, 0o755)
        sleep_path = os.path.join(bindir, "sleep")
        with open(sleep_path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(POLL_CLAMP_STUB_SLEEP)
        os.chmod(sleep_path, 0o755)
        env = dict(POLL_CLAMP_ENV)
        env["PATH"] = bindir + os.pathsep + os.environ["PATH"]
        rc, out, outputs, _summary = run_step(BASH, script, workdir, env, runner_temp)
    finally:
        shutil.rmtree(tmproot, ignore_errors=True)
    if rc != 0:
        return [f"{tag} the step exited {rc}: {out}"]
    raw = outputs.get("verdict")
    verdict = None
    if raw is not None:
        try:
            verdict = json.loads(raw)
        except ValueError:
            verdict = None
    if not verdict:
        return [f"{tag} no JSON verdict emitted (outputs={outputs!r})"]
    failures = []
    if verdict.get("outcome") != "fail-gate-stall":
        failures.append(f"{tag} expected outcome fail-gate-stall, got "
                         f"{verdict.get('outcome')!r} (verdict={verdict})")
    if verdict.get("failing_check") != "spec-draft PR merge":
        failures.append(f"{tag} expected the spec-draft gate named, got "
                         f"{verdict.get('failing_check')!r} (verdict={verdict})")
    if "required checks never reported a result" not in (verdict.get("observed") or ""):
        failures.append(f"{tag} evidence lacks the expected text (verdict={verdict})")
    return failures


POLL_CLAMP_SCENARIOS = [
    dict(name="spec-draft gate blocked-pending since the first observation, "
              "still well within the 1200s allowance when the (tiny, "
              "fixtured) poll budget expires: fail-gate-stall, not "
              "fail-timeout"),
]

# The fold review's own regression, put back: the post-loop block writes the
# generic fail-timeout with no clamp check at all (this feature's own
# pre-fix shape).
POLL_CLAMP_FIXED_TEXT = (
    '          if [ "$terminal" != "true" ]; then\n'
    "            # specs/070-blocked-gate-dry-run edge case: a gate's waiting\n"
    "            # allowance is not clamped to the remaining poll budget, so a\n"
    "            # gate that first goes blocked-pending late enough that its\n"
    "            # 1200s allowance cannot fully elapse before the `while`\n"
    "            # condition above goes false must still end the attempt as that\n"
    "            # gate's stall here, not fall through to the generic timeout\n"
    "            # below (FR-007: the generic timeout is the outcome only when no\n"
    "            # gate is blocked).\n"
    '            for prefix in "spec-draft/" "plan/" "spec/"; do\n'
    '              if [ -n "${gate_blocked_since[$prefix]}" ]; then\n'
    '                write_verdict "fail-gate-stall" "${gate_name[$prefix]}" "gh pr merge succeeds" \\\n'
    '                  "PR #${gate_pr_number[$prefix]}: required checks never reported a result"\n'
    "                emit_verdict\n"
    "                exit 0\n"
    "              fi\n"
    "            done\n"
    '            write_verdict "fail-timeout" "end-to-end run reaching a terminal state" \\\n'
)
POLL_CLAMP_ORIGINAL_TEXT = (
    '          if [ "$terminal" != "true" ]; then\n'
    '            write_verdict "fail-timeout" "end-to-end run reaching a terminal state" \\\n'
)

POLL_CLAMP_MUTATIONS = [
    ("the poll budget's blocked-pending clamp removed (a gate mid-allowance "
     "when the budget expires falls back to the generic fail-timeout)",
     POLL_CLAMP_FIXED_TEXT, POLL_CLAMP_ORIGINAL_TEXT),
]


# --------------------------------------------------------------------------
# Mutations: each puts one documented-branch defect back into a scratch
# copy of the script, then asserts the suite fails against that copy.
# --------------------------------------------------------------------------
def mutate(src_path, old, new, label):
    text = open(src_path, encoding="utf-8").read()
    if text.count(old) != 1:
        sys.exit(f"::error::verify-auto-release-e2e-gate-decisions: expected exactly "
                 f"one occurrence of {old!r} in {src_path} to mutate for {label!r}, "
                 f"found {text.count(old)} -- the script text may have changed shape; "
                 f"update this harness alongside it.")
    return text.replace(old, new, 1)


CLARIFY_MUTATIONS = [
    ("exhausted collapsed into reply (round bound ignored)",
     'if [ "$rounds_answered" -lt "$MAX_CLARIFICATION_ROUNDS" ]; then',
     'if true; then'),
    ("wait collapsed into reply (a qualifying reply already posted is ignored)",
     'if [ "$reply_exists" = "true" ]; then\n      echo "wait"\n      exit 0\n    fi',
     'if false; then\n      echo "wait"\n      exit 0\n    fi'),
    ("the Bot filter is dropped from qualification (a bot comment would then count as a reply)",
     '((.user.type // "") != "Bot")',
     'true'),
]

MERGE_MUTATIONS = [
    ("wrong-attempt collapsed into merge (leftover PR from a previous attempt acted on)",
     'if [ "$head_ref" != "$expected_head" ]; then',
     'if false; then'),
    ("wrong-base collapsed into merge (a retargeted PR would be merged)",
     'if [ "$base_ref" != "$expected_base" ]; then',
     'if false; then'),
    ("conflicting collapsed into merge",
     'if [ "$mergeable" = "CONFLICTING" ]; then',
     'if false; then'),
    ("a pending required check reads as blocked instead of blocked-pending",
     'if [ "$still_pending" = "true" ]; then',
     'if false; then'),
    ("an empty statusCheckRollup (no check registered yet on a freshly "
     "opened PR) reads as blocked instead of blocked-pending",
     'if ($rollup | length) == 0 then true',
     'if ($rollup | length) == 0 then false'),
    ("a legacy StatusContext rollup entry (state, no status/conclusion) is "
     "read with the CheckRun-shaped predicate and always reads as pending, "
     "hanging forever",
     'if has("state") then (.state == "PENDING" or .state == "EXPECTED")',
     'if false then (.state == "PENDING" or .state == "EXPECTED")'),
    ("a legacy StatusContext in EXPECTED (no status posted yet) reads as "
     "resolved instead of still pending",
     '.state == "PENDING" or .state == "EXPECTED"',
     '.state == "PENDING"'),
    ("draft collapsed into merge",
     'if [ "$is_draft" = "true" ]; then',
     'if false; then'),
]

ALLOWANCE_MUTATIONS = [
    ("clear collapsed away (a non-blocked-pending decision never resets the timer)",
     'if [ "$merge_decision" != "blocked-pending" ]; then',
     'if false; then'),
    ("start collapsed away (a first blocked-pending observation is never timed)",
     'if [ -z "$blocked_since" ]; then',
     'if false; then'),
    ("stall collapsed away (an exhausted allowance never ends the attempt)",
     'if [ $((now - blocked_since)) -ge "$allowance_seconds" ]; then',
     'if false; then'),
    ("wait collapsed into clear (still-within-allowance is misreported as resolved)",
     'echo "wait"',
     'echo "clear"'),
]


def run_mutation(script_path, run_suite, label, old, new, failures):
    mutated_text = mutate(script_path, old, new, label)
    # Keyed on this process's own pid, not a fixed name -- two --self-test
    # invocations running in parallel (observed once on Windows) otherwise
    # race on the same file, and the loser's os.remove in the other's
    # `finally` raises FileNotFoundError (maintainer feedback on PR #389,
    # second review, Verify item: a race, not a logic defect).
    tmp_path = f"{script_path}.{os.getpid()}.mutated.tmp"
    with open(tmp_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(mutated_text)
    try:
        broke = run_suite(tmp_path)
    finally:
        os.remove(tmp_path)
    if broke:
        print(f"Mutation OK - {label}: {len(broke)} assertion(s) fail.")
    else:
        print(f"::error::MUTATION SURVIVED - reintroducing {label!r} broke nothing "
              f"in this suite, so the suite is not testing that defect.")
        failures.append(f"mutation survived: {label}")


def self_test():
    """Gate 66 self-test: each documented branch fails its own mutation."""
    failures = []
    for label, old, new in CLARIFY_MUTATIONS:
        run_mutation(CLARIFY_SCRIPT, run_clarify_suite, label, old, new, failures)
    for label, old, new in MERGE_MUTATIONS:
        run_mutation(MERGE_SCRIPT, run_merge_suite, label, old, new, failures)
    for label, old, new in ALLOWANCE_MUTATIONS:
        run_mutation(ALLOWANCE_SCRIPT, run_allowance_suite, label, old, new, failures)
    for label, old, new in POLL_CLAMP_MUTATIONS:
        run_mutation(POLL_WORKFLOW, run_poll_clamp_suite, label, old, new, failures)

    total = (len(CLARIFY_MUTATIONS) + len(MERGE_MUTATIONS) + len(ALLOWANCE_MUTATIONS)
             + len(POLL_CLAMP_MUTATIONS))
    print(f"Gate 66 self-test: {total} mutation(s); {len(failures)} failure(s).")
    return 1 if failures else 0


def main(argv):
    global BASH
    use_utf8_stdout()
    ensure_jq()
    BASH = resolve_bash()

    if (not os.path.isfile(CLARIFY_SCRIPT) or not os.path.isfile(MERGE_SCRIPT)
            or not os.path.isfile(ALLOWANCE_SCRIPT) or not os.path.isfile(POLL_WORKFLOW)):
        sys.exit(f"::error::{CLARIFY_SCRIPT}, {MERGE_SCRIPT}, {ALLOWANCE_SCRIPT}, "
                 f"or {POLL_WORKFLOW} not found relative to this script's own location.")

    if "--self-test" in argv:
        return self_test()

    failures = run_all(CLARIFY_SCRIPT, MERGE_SCRIPT, ALLOWANCE_SCRIPT) + run_poll_clamp_suite(POLL_WORKFLOW)
    for f in failures:
        print(f"::error::{f}")

    total = (len(CLARIFY_DECIDE_SCENARIOS) + len(CLARIFY_SATISFIED_SCENARIOS)
             + len(CLARIFY_MARKERS_SCENARIOS) + len(MERGE_SCENARIOS)
             + len(ALLOWANCE_SCENARIOS) + len(POLL_CLAMP_SCENARIOS))
    print(f"auto-release e2e gate decisions: "
          f"{total} scenario(s); "
          f"{len(failures)} failure(s).")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
