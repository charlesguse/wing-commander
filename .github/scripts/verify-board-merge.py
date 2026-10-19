#!/usr/bin/env python3
"""Gate — the board loop's self-merge decision and its `merge` job stay inside
the bounds Principle X authorizes (specs/115-board-loop-self-merge,
contracts/board-merge.md, FR-015).

WHY THIS EXISTS
---------------
board_merge.py decides whether a PR may be squash-merged without the owner.
Every merge-blocking condition and every refusal branch must have a checked-in
fixture that proves it blocks (or classifies), so a condition dropped from the
evaluator cannot look identical to a working one. The workflow half is
structural: the `merge` job may call `gh pr merge` only pinned to the head SHA
it evaluated, never with `--admin`, `--auto`, an approval, or a second merge
method, only behind both switches, and without dispatching proof runs itself.

Fixtures live in .github/scripts/fixtures/board-merge/, named
`<class>-<condition>[-variant].json` (a case where that condition is the
first unmet one), `<class>-pass[-variant].json` (every condition holds) and
`refusal-<class>.json` (gh stderr plus the expected refusal class).

    python3 .github/scripts/verify-board-merge.py
"""
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import board_merge  # noqa: E402
from board_readiness import CONDITIONS as READINESS_CONDITIONS  # noqa: E402
from board_item_marker import render_bump_verification  # noqa: E402

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
FIXTURES_DIR = os.path.join(SCRIPTS_DIR, "fixtures", "board-merge")
BOARD_LOOP = ".github/workflows/board-loop.yml"
AUTO_UPDATE = ".github/workflows/auto-update-spec-kit.yml"
WORKFLOWS_DIR = ".github/workflows"

failures = 0


def fail(message):
    global failures
    failures += 1
    print("::error::verify-board-merge: {0}".format(message))


def ok(message):
    print("[ok] {0}".format(message))


def _load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def check_decision_fixtures():
    for klass, names in (("fix", board_merge.CONDITIONS_FIX), ("bump", board_merge.CONDITIONS_BUMP)):
        passes = sorted(glob.glob(os.path.join(FIXTURES_DIR, "{0}-pass*.json".format(klass))))
        if not passes:
            fail("no all-pass fixture for class {0}".format(klass))
        cases = [(path, None) for path in passes]
        for name in names:
            found = sorted(glob.glob(os.path.join(FIXTURES_DIR, "{0}-{1}*.json".format(klass, name))))
            if not found:
                fail("condition {0} of class {1} has no fixture".format(name, klass))
            cases += [(path, name) for path in found]
        for path, blocked_by in cases:
            spec = _load(path)
            got = board_merge.decide(spec["inputs"])
            want = spec["expect"]
            label = os.path.basename(path)
            if (got["may_merge"] != want["may_merge"] or got["unmet_reason"] != want["unmet_reason"]
                    or got["unmet_reason"] != blocked_by):
                fail("{0}: expected {1!r} (named by its file), got may_merge={2} unmet_reason={3!r}".format(
                    label, want, got["may_merge"], got["unmet_reason"]))
            elif list(got["conditions"]) != list(names):
                fail("{0}: decision lists conditions {1}, expected {2}".format(
                    label, list(got["conditions"]), list(names)))
            else:
                ok("{0}: may_merge={1} unmet_reason={2!r}".format(label, got["may_merge"], got["unmet_reason"]))


def check_refusal_fixtures():
    for name in board_merge.REFUSAL_CLASSES:
        path = os.path.join(FIXTURES_DIR, "refusal-{0}.json".format(name))
        if not os.path.isfile(path):
            fail("refusal class {0} has no fixture".format(name))
            continue
        spec = _load(path)
        got = board_merge.classify_refusal(spec["stderr"])
        if got != name or spec["expect_class"] != name:
            fail("refusal-{0}.json classified as {1!r}".format(name, got))
        else:
            ok("refusal-{0}.json classifies as {0}".format(name))


TRANSIENT_STDERRS = (
    "GraphQL: Head branch was modified. Review and try the merge again. (mergePullRequest)",
    "GraphQL: Base branch was modified. Review and try the merge again. (mergePullRequest)",
    "HTTP 502: Bad Gateway (https://api.github.com/graphql)",
    "HTTP 503: Service Unavailable",
    # Pass 2 of review-until-clean on PR #1059: the API's own refusal while
    # mergeability is unknown (gh's pre-check saw no blocked state).
    "GraphQL: Pull Request is not mergeable (mergePullRequest)",
)


def check_transient_refusals():
    """A failure that clears itself is never handed over as refused."""
    bad = [(err, board_merge.classify_refusal(err)) for err in TRANSIENT_STDERRS
           if board_merge.classify_refusal(err) not in getattr(board_merge, "RETRYABLE_REFUSAL_CLASSES", ())]
    for err, got in bad:
        fail("transient stderr {0!r} classified as {1!r}, which is handed over".format(err, got))
    if not bad:
        ok("head-moved, base-moved and 5xx merge failures are retried, not handed over")


# gh's own refusal before it calls the API (pkg/cmd/pr/merge blockedReason):
# BLOCKED and BEHIND are branch protection, DIRTY is a conflict. All three
# say "is not mergeable", so the class comes from the reason after it.
GH_BLOCKED_REASONS = (
    ("X Pull request o/r#12 is not mergeable: the base branch policy prohibits the merge.", "protection"),
    ("X Pull request o/r#12 is not mergeable: the head branch is not up to date with the base branch.",
     "protection"),
    ("X Pull request o/r#12 is not mergeable: the merge commit cannot be cleanly created.", "conflict"),
)


def check_gh_blocked_reasons():
    """Full review of PR #1059: the handover names the refusal reason
    (FR-010), so a protection refusal is never announced as a conflict."""
    bad = [(err, want, board_merge.classify_refusal(err)) for err, want in GH_BLOCKED_REASONS
           if board_merge.classify_refusal(err) != want]
    for err, want, got in bad:
        fail("gh's refusal {0!r} classifies as {1!r}, expected {2!r}".format(err, got, want))
    if not bad:
        ok("gh's own not-mergeable reasons classify as protection or conflict by their reason")


def _bump_snapshot(number, created, head, comments=(), body_issue=77):
    return {"number": number, "createdAt": created, "headRefOid": head,
            "author": {"login": "app/wing-commander"},
            "headRefName": "auto-update-spec-kit/v1.2.{0}".format(number),
            "baseRefName": "main",
            "body": "Upgrade\nCloses #{0}\n{1}".format(body_issue, board_merge.BUMP_BODY_MARKER),
            "commits": [{"authors": [{"login": "app/wing-commander"}]}],
            "files": [{"path": ".specify/x"}],
            "statusCheckRollup": [{"name": "lint", "workflowName": "lint \u00b7 workflows",
                                   "conclusion": "SUCCESS"}],
            "comments": list(comments)}


def _bot_comment(body, cid, created="2026-10-01T00:00:00Z"):
    return {"author": {"login": "app/wing-commander"}, "createdAt": created,
            "url": "https://github.com/o/r/pull/1#issuecomment-{0}".format(cid), "body": body}


def _verified(head, cid):
    return _bot_comment(render_bump_verification(head, "lightweight", "passed", "1"), cid)


def check_bump_pick_and_dedup():
    """Review round 1 of PR #1059: one stuck bump PR never hides a newer
    verified one; a PR refused at its head is released until the head moves;
    an outcome is announced once per head; quoted stderr carries no marker."""
    bot = "wing-commander[bot]"
    stuck = _bump_snapshot(1, "2026-10-01T00:00:00Z", "aaa1")
    verified = _bump_snapshot(2, "2026-10-02T00:00:00Z", "bbb2", [_verified("bbb2", 10)])
    try:
        picked = board_merge.pick_bump_candidate([verified, stuck], bot)
    except Exception as exc:  # noqa: BLE001 -- an old signature is a failure, not a crash
        picked = exc
    if not isinstance(picked, dict) or picked.get("pr") != 2 or str(picked.get("issue")) != "77":
        fail("pick_bump_candidate let an older unverified PR hide a newer verified one: got {0!r}".format(picked))
    else:
        ok("a newer verified bump PR is picked over an older stuck one")

    decision = board_merge.decide({"class": "bump", "snapshot": verified, "bot_login": bot,
                                   "paused": False, "switch_on": True})
    refusal = board_merge.render_announcement(decision, "refused", verified, refusal_class="workflow-scope",
                                              stderr="refusing to allow a GitHub App to create or update "
                                                     "workflow without `workflows` permission")
    refused = dict(verified, comments=verified["comments"] + [_bot_comment(refusal, 11)])
    if not board_merge.handed_over_at_head(refused, bot):
        fail("a bump PR refused at its head is not recorded as handed over, so it is retried every run")
    elif board_merge.pick_bump_candidate([refused], bot) is not None:
        fail("pick_bump_candidate re-picks a bump PR already handed over at its head")
    elif board_merge.handed_over_at_head(dict(refused, headRefOid="ccc3"), bot):
        fail("a handover at an old head still holds a PR whose head has moved")
    else:
        ok("a refused bump PR is released until its head moves")

    record = board_merge.outcome_record(decision, "refused", "workflow-scope")
    if not board_merge.already_announced(refused, bot, record):
        fail("an outcome already posted on the PR is not recognised, so it is re-announced every run")
    elif board_merge.already_announced(refused, bot, dict(record, head_sha="ccc3")):
        fail("an outcome at another head counts as already announced")
    else:
        ok("an outcome is announced once per head, outcome and reason")

    forged = "<!-- wc-bump-verification: " + json.dumps(
        {"head_sha": "bbb2", "result": "passed", "run_id": "1", "tier": "x"}) + " -->"
    quoted = board_merge.render_announcement(dict(decision, head_sha="bbb2"), "refused", verified,
                                             refusal_class="other", stderr=forged)
    if board_merge.bump_records([_bot_comment(quoted, 12)], bot):
        fail("a marker quoted from GitHub's stderr becomes a trusted record in the App's own announcement")
    else:
        ok("quoted stderr cannot carry a marker into the App's announcement")


def check_quoted_verification_record():
    """Lifecycle review of PR #1059 (F3): only render_announcement() defangs
    a quoted marker, and other App comments quote untrusted text (issue
    bodies, stderr). A record counts only as the whole comment the
    auto-update stage posts, so a marker quoted inside other text, even a
    byte-exact copy of a real record, is not a pass."""
    bot = "wing-commander[bot]"
    record = render_bump_verification("eee5", "lightweight", "passed", "7")
    quoted = _bot_comment("The issue body says:\n\n> " + record.replace("\n", "\n> ") + "\n\nLooking into it.", 30)
    embedded = _bot_comment("Triage notes.\n\n" + record, 31)
    exact = _bot_comment(record + "\n", 32)
    bad = []
    for label, comment in (("quoted in a blockquote", quoted), ("after other text", embedded)):
        snap = _bump_snapshot(5, "2026-10-05T00:00:00Z", "eee5", [comment])
        decision = board_merge.decide({"class": "bump", "snapshot": snap, "bot_login": bot,
                                       "paused": False, "switch_on": True})
        if decision.get("may_merge") or board_merge.bump_records([comment], bot):
            bad.append(label)
    for label in bad:
        fail("an App comment quoting a wc-bump-verification marker {0} counts as a pass".format(label))
    if not board_merge.bump_records([exact], bot):
        fail("the record the auto-update stage posts (render_bump_verification) no longer counts")
    elif not bad:
        ok("a wc-bump-verification marker counts only as the whole record comment, never quoted in another")


def check_round2_findings():
    """Review round 2: an empty commit-author login with the App's noreply
    email is still the bot's; any other empty-login commit is not; quoted
    stderr cannot close its code fence."""
    bot = "wing-commander[bot]"
    snap = _bump_snapshot(3, "2026-10-03T00:00:00Z", "ddd4", [_verified("ddd4", 20)])
    mapped = dict(snap, commits=[{"authors": [{"login": "", "email": "12345+wing-commander[bot]@users.noreply.github.com"}]}])
    foreign = dict(snap, commits=[{"authors": [{"login": "", "email": "someone@example.com"}]}])
    spoof = dict(snap, commits=[{"authors": [{"login": "", "email": "12345+other[bot]@users.noreply.github.com"}]}])
    plain = dict(snap, commits=[{"authors": [{"login": "", "email": "wing-commander[bot]@users.noreply.github.com"}]}])
    if not board_merge._attributed_to_auto_update(mapped, bot):
        fail("a bot commit whose login gh reports empty (noreply email) is not attributed to the bot")
    elif not board_merge._attributed_to_auto_update(plain, bot):
        fail("a bot commit with the auto-update stage's plain <slug>[bot] noreply email is not attributed to the bot")
    elif board_merge._attributed_to_auto_update(foreign, bot) or board_merge._attributed_to_auto_update(spoof, bot):
        fail("an empty-login commit by someone other than the bot is attributed to the bot")
    else:
        ok("an empty-login bot commit is attributed by its noreply email; others are not")
    decision = board_merge.decide({"class": "bump", "snapshot": snap, "bot_login": bot,
                                   "paused": False, "switch_on": True})
    text = board_merge.render_announcement(decision, "refused", snap, refusal_class="other",
                                           stderr="boom\n```\n# injected heading")
    if text.count("```") != 2:
        fail("quoted stderr closes its code fence: {0} fence markers".format(text.count("```")))
    else:
        ok("quoted stderr cannot close its code fence")


def job_block(lines, job):
    """The lines of top-level job `job` (two-space indent) up to the next job."""
    span = job_span(lines, job)
    return lines[span[0]:span[1]] if span else None


def job_span(lines, job):
    """(start, end) line indices of top-level job `job`, or None."""
    start = None
    for i, line in enumerate(lines):
        if line == "  {0}:".format(job):
            start = i
        elif start is not None and re.fullmatch(r"  [A-Za-z0-9_-]+:", line):
            return start, i
    return (start, len(lines)) if start is not None else None


def merge_calls_outside(lines):
    """Every non-comment `gh pr merge` line outside the merge job's own line
    span. By position, not by text: an identical line pasted into another
    job is still outside it."""
    span = job_span(lines, "merge") or (0, 0)
    return [line for i, line in enumerate(lines)
            if not span[0] <= i < span[1] and re.search(r"gh\s+pr\s+merge\b", line)
            and not line.lstrip().startswith("#")]


# GITHUB_TOKEN never holds a write it could merge or push with: every merge
# and comment in the job is the App token's. actions: write is the
# kill-switch re-check's cancel-token (wing-commander-board-stop-check).
MERGE_JOB_PERMISSIONS = {"contents": "read", "issues": "write", "pull-requests": "read", "actions": "write"}


def merge_job_shape_problems(merge_job):
    """Structural rules on the merge job's own lines (review round 1 of
    PR #1059): its github.token permissions are exactly
    MERGE_JOB_PERMISSIONS; no `gh` read is piped into `grep -q`, whose early
    exit SIGPIPEs the reader under pipefail so the pipeline fails even when
    it matched; and a transient merge failure is retried, not handed over."""
    problems = []
    perms, inside = {}, False
    for line in merge_job:
        if line == "    permissions:":
            inside = True
            continue
        if inside:
            if line.lstrip().startswith("#"):
                continue
            match = re.fullmatch(r"      ([a-z-]+):\s*(\S+)", line)
            if not match:
                break
            perms[match.group(1)] = match.group(2)
    if perms != MERGE_JOB_PERMISSIONS:
        problems.append("the merge job's permissions are {0}, expected exactly {1}".format(
            perms, MERGE_JOB_PERMISSIONS))
    code = _run_blocks_text(merge_job)
    if re.search(r"\bgh\b[^\n]*\|\s*grep\s+-\w*q", code):
        problems.append("the merge job pipes a `gh` read into `grep -q`; read it to a file first "
                        "(grep -q's early exit fails the pipeline under pipefail)")
    if not re.search(r"board_merge\.py\"?\s+retryable\b", code):
        problems.append("the merge step never asks board_merge.py whether a refusal is retryable, "
                        "so a transient failure would be handed over as refused")
    return problems


def find_merge_calls(code):
    """Every `gh pr merge` call with its backslash-continued lines. A line is
    any run of characters that is not a backslash-newline, so a continuation's
    flags are part of the call and are checked with it."""
    line_re = r"(?:[^\\\n]|\\(?!\n))*"
    return re.findall(r"gh\s+pr\s+merge\b" + line_re + r"(?:\\\n" + line_re + r")*", code)


def _run_blocks_text(lines):
    return "\n".join(line for line in lines if not line.lstrip().startswith("#"))


_SELF_TEST_WORKFLOW = """jobs:
  merge:
    permissions:
      contents: read
      issues: write
      pull-requests: read
      actions: write
    steps:
      - run: |
          gh pr merge "$PR" --squash --match-head-commit "$SHA"
          python3 -I "$scripts/board_merge.py" retryable "$c"
  other:
    steps:
      - run: |
          gh pr merge "$PR" --squash --match-head-commit "$SHA"
"""


def check_structural_self_test():
    """The workflow rules can tell a violation from a clean job: a pasted
    identical `gh pr merge` line in another job, a widened permission, and a
    `gh ... | grep -q` pipe each fail."""
    lines = _SELF_TEST_WORKFLOW.splitlines()
    if not merge_calls_outside(lines):
        fail("self-test: an identical `gh pr merge` line pasted into another job is not caught")
    clean = job_block(lines, "merge")
    if merge_job_shape_problems(clean):
        fail("self-test: a clean merge job is flagged: {0}".format(merge_job_shape_problems(clean)))
    widened = [line.replace("contents: read", "contents: write") for line in clean]
    piped = clean + ['          gh api "repos/x/issues/1/comments" --paginate --jq \'.[].body\' | grep -qF -- "$key"']
    unretried = [line for line in clean if "retryable" not in line]
    for label, job in (("contents: write", widened), ("gh | grep -q", piped), ("no retry", unretried)):
        if not merge_job_shape_problems(job):
            fail("self-test: a merge job with {0} is not caught".format(label))
    continued = find_merge_calls('gh pr merge "$PR" --squash \\\n  --rebase --match-head-commit "$SHA"\n')
    if len(continued) != 1 or "--rebase" not in continued[0] or "--match-head-commit" not in continued[0]:
        fail("self-test: flags on a backslash-continued `gh pr merge` line are not part of the call")
    if not failures:
        ok("self-test: the merge-job rules catch a pasted merge line, widened permissions, "
           "a gh | grep -q pipe and a missing retry")


def check_board_loop():
    if not os.path.isfile(BOARD_LOOP):
        fail("{0} does not exist; run from the repository root".format(BOARD_LOOP))
        return
    with open(BOARD_LOOP, encoding="utf-8") as fh:
        text = fh.read()
    lines = text.splitlines()
    merge_job = job_block(lines, "merge")
    if merge_job is None:
        fail("{0} has no `merge` job".format(BOARD_LOOP))
        return
    code = _run_blocks_text(lines)
    merge_code = _run_blocks_text(merge_job)

    for pattern, label in ((r"--admin\b", "--admin"), (r"--auto\b", "--auto"),
                           (r"gh\s+pr\s+review\b[^\n]*--approve", "gh pr review --approve"),
                           (r"event=APPROVE\b", "event=APPROVE")):
        if re.search(pattern, code):
            fail("{0} contains {1}".format(BOARD_LOOP, label))
    merge_calls = find_merge_calls(merge_code)
    if not merge_calls:
        fail("the merge job never calls `gh pr merge`")
    for call in merge_calls:
        if "--match-head-commit" not in call:
            fail("a `gh pr merge` call without --match-head-commit: {0}".format(call.splitlines()[0]))
        if "--squash" not in call or re.search(r"--(merge|rebase)\b", call):
            fail("a `gh pr merge` call that is not --squash only: {0}".format(call.splitlines()[0]))
    outside = merge_calls_outside(lines)
    if outside:
        fail("`gh pr merge` outside the merge job: {0}".format(outside[0].strip()))
    for problem in merge_job_shape_problems(merge_job):
        fail(problem)

    # The `if:` expression runs from its key to the next job-level key (the
    # `runs-on:` line), not a fixed number of lines.
    if_lines = []
    in_if = False
    for line in merge_job[1:]:
        if re.match(r"^    if:", line):
            in_if = True
        elif in_if and re.match(r"^    \S", line):
            break
        if in_if:
            if_lines.append(line.strip())
    condition = " ".join(if_lines)
    if "WING_COMMANDER_BOARD_AUTO_MERGE" not in condition or "WING_COMMANDER_BOARD_LOOP_PAUSED" not in condition:
        fail("the merge job's `if:` must carry both WING_COMMANDER_BOARD_AUTO_MERGE and "
             "WING_COMMANDER_BOARD_LOOP_PAUSED")
    elif not re.search(r"WING_COMMANDER_BOARD_AUTO_MERGE\s*==\s*'true'", condition):
        fail("the merge job runs unless the switch is exactly 'true' -- it must be off by default")
    else:
        ok("merge job: pinned --squash merge, no --admin/--auto/approve, both switches in its `if:`")

    if "Awaiting a human merge" not in text:
        fail("the switch-off readiness text 'Awaiting a human merge' is gone (SC-006)")
    else:
        ok("switch-off readiness text unchanged")

    issue_post = merge_code.find("gh issue comment \"$ISSUE_NUMBER\"")
    pr_post = merge_code.find("gh pr comment \"$PR_NUMBER\"")
    if issue_post < 0 or pr_post < 0 or issue_post > pr_post:
        fail("the announce step must post the issue comment (with its marker) before the PR comment, "
             "which is the dedup source")
    if '"MERGED"' not in merge_code:
        fail("the merge step must treat an already-MERGED PR as merged before classifying a failure")
    if "--carry-round-from" not in merge_code or "--base-sha" not in merge_code:
        fail("the merged/handed-over markers must carry branch, base_sha and the round")
    if re.search(r"gh\s+workflow\s+run\b", merge_code):
        fail("the merge job dispatches a run itself; proof comes only from prove-gate (research D8)")
    else:
        ok("merge job dispatches no run")
    # A merged item reaches prove-gate through the PR's closed event, which
    # only an App-token merge starts (a GITHUB_TOKEN one starts no workflow).
    merge_step = next((block for block in re.split(r"\n      - name: ", "\n".join(merge_job))
                       if "gh pr merge" in block), "")
    if "GH_TOKEN: ${{ env.WC_BOT_TOKEN }}" not in merge_step:
        fail("the merge step must run with the App token (env.WC_BOT_TOKEN) so the closed event "
             "reaches prove-gate")
    prove_gate = job_block(lines, "prove-gate")
    if prove_gate is None or "github.event_name == 'pull_request'" not in "\n".join(prove_gate):
        fail("prove-gate no longer runs on the pull_request closed event a merge produces")
    else:
        ok("merge runs as the App and prove-gate takes its closed event")

    # The decision logic has one home: board_merge.py (CLAUDE.md). `switch_on`
    # and `review_converged` also name payload keys the job passes in.
    names = ((set(board_merge.CONDITIONS_FIX) | set(board_merge.CONDITIONS_BUMP))
             - set(READINESS_CONDITIONS) - {"switch_on", "review_converged"})
    for path in sorted(glob.glob(os.path.join(WORKFLOWS_DIR, "*.yml"))):
        with open(path, encoding="utf-8") as fh:
            body = _run_blocks_text(fh.read().splitlines())
        for name in sorted(names):
            if name in body:
                fail("{0} carries the merge condition name {1}; it lives in board_merge.py only".format(path, name))
        if "not mergeable" in body or "approving review" in body:
            fail("{0} carries a refusal regex; classify_refusal() is its one home".format(path))


def check_readiness_head_binding():
    """Full review of PR #1059: decide() trusts readiness's backstop only at
    `readiness_head_sha`, so that output must be the head the backstop step
    measured (its own `git rev-parse HEAD` after the branch fetch), not only
    the head a later `gh pr view` read: a push between the two would bind a
    backstop measured on one head to another."""
    with open(BOARD_LOOP, encoding="utf-8") as fh:
        readiness = job_block(fh.read().splitlines(), "readiness")
    if readiness is None:
        fail("{0} has no `readiness` job".format(BOARD_LOOP))
        return
    text = "\n".join(readiness)
    steps = {block.split("\n", 1)[0]: block for block in re.split(r"\n      - name: ", text)}
    backstop = steps.get("Re-apply the route backstop to the current final diff", "")
    evaluate = steps.get("Evaluate readiness", "")
    problems = []
    if 'MEASURED_HEAD_SHA="$(git rev-parse HEAD)"' not in backstop or "head-sha=" not in backstop:
        problems.append("the backstop step does not output the head it measured (git rev-parse HEAD)")
    if "BACKSTOP_HEAD_SHA: ${{ steps.final-diff-backstop.outputs.head-sha }}" not in evaluate:
        problems.append("Evaluate readiness does not read the backstop step's measured head")
    elif not re.search(r'decision\["head_sha"\] == backstop_head', evaluate):
        problems.append("Evaluate readiness writes head-sha without comparing it to the backstop's measured head")
    if "head-sha: ${{ steps.decide.outputs.head-sha }}" not in text:
        problems.append("the readiness job's head-sha output is not Evaluate readiness's bound head")
    for problem in problems:
        fail("readiness head binding: {0}".format(problem))
    if not problems:
        ok("readiness's head-sha output is the head its backstop measured, or empty")


def check_review_head_binding():
    """Follow-up review of PR #1059 (FR-003): readiness's "ready" can come
    from an earlier run's step=readiness marker that never re-checks the
    head the review converged on, so decide() also needs the issue's newest
    review verdict to have converged on the snapshot's head
    (fixtures/board-merge/fix-review_converged-stale-head.json). The merge
    job must read those verdicts fresh and hand them to every decide call,
    the retry's included, or the fixture's guard never runs live."""
    with open(BOARD_LOOP, encoding="utf-8") as fh:
        merge_job = job_block(fh.read().splitlines(), "merge") or []
    code = _run_blocks_text(merge_job)
    decides = re.findall(r"board_merge\.py\" decide\b(?:[^\n]*\\\n)*[^\n]*", code)
    problems = []
    if 'issues/$ISSUE_NUMBER/comments" --paginate' not in code:
        problems.append("the merge job does not fetch the fix issue's comments")
    if len(decides) < 2:
        problems.append("expected the decision and the retry's re-decision, found {0} decide call(s)".format(
            len(decides)))
    for call in decides:
        if '--issue-comments "$RUNNER_TEMP/board-merge-issue-comments.json"' not in call:
            problems.append("a decide call does not pass the freshly read issue comments")
    for problem in problems:
        fail("review head binding: {0}".format(problem))
    if not problems:
        ok("the merge job re-reads the review verdicts and every decide call binds them to its head")


def check_pass2_findings():
    """Pass 2 of review-until-clean on PR #1059: whether the App merged a PR
    is decided by board_merge.merged_by_us(), never by a second copy of the
    login normalization in workflow jq; a PR merged by someone else is
    announced as merged elsewhere, never as "Not merged"; and the merge job,
    which reads no history, checks out shallow."""
    bot = "wing-commander[bot]"
    merged_by_us = getattr(board_merge, "merged_by_us", None)
    if merged_by_us is None:
        fail("board_merge.py has no merged_by_us(): who merged the PR is decided in workflow shell")
    else:
        cases = (({"mergedBy": {"login": "app/wing-commander"}, "headRefOid": "aaa1"}, "aaa1", True),
                 ({"mergedBy": {"login": "Wing-Commander[bot]"}, "headRefOid": "aaa1"}, "aaa1", True),
                 ({"mergedBy": {"login": "app/wing-commander"}, "headRefOid": "bbb2"}, "aaa1", False),
                 ({"mergedBy": {"login": "someone"}, "headRefOid": "aaa1"}, "aaa1", False),
                 ({"mergedBy": None, "headRefOid": "aaa1"}, "aaa1", False),
                 ({"mergedBy": {"login": "app/wing-commander"}, "headRefOid": ""}, "", False))
        bad = [(pr, head) for pr, head, want in cases if merged_by_us(pr, bot, head) != want]
        for pr, head in bad:
            fail("merged_by_us({0!r}, head {1!r}) is wrong".format(pr, head))
        if not bad:
            ok("merged_by_us() holds only for this App's merge at the pinned head")
    with open(BOARD_LOOP, encoding="utf-8") as fh:
        merge_job = job_block(fh.read().splitlines(), "merge") or []
    merge_code = _run_blocks_text(merge_job)
    if re.search(r"sub\(\s*\"\^app/", merge_code) or "merged-by-us" not in merge_code:
        fail("the merge step normalizes mergedBy.login in jq instead of asking board_merge.py merged-by-us "
             "(the login rule's one home is board_merge._slug)")
    elif any(re.fullmatch(r"\s*fetch-depth:\s*0\s*", line) for line in merge_job):
        fail("the merge job checks out with fetch-depth: 0; it reads no history")
    else:
        ok("the merge job asks board_merge.py who merged the PR and checks out shallow")
    decision = {"head_sha": "aaa1", "class": "fix", "may_merge": True, "unmet_reason": None,
                "conditions": {"switch_on": True}}
    text = board_merge.render_announcement(decision, "not-merged", {})
    if text.startswith("Not merged") or "merged_elsewhere" not in text:
        fail("a PR merged by someone else is announced as {0!r}".format(text.split("\n", 1)[0]))
    else:
        ok("a PR merged elsewhere is announced as merged elsewhere, keeping its outcome record")


def check_stalled_tracking_issue():
    """Owner's decision on pass 3's C2 (#903, option b): a maintainer /stop
    on a bump PR's auto-update:tracking issue leaves it board:stalled, and
    the pick skips every bump PR closing a stalled tracking issue, so the
    release is removing the label, as for a fix item. The merge job must
    hand the pick the open board:stalled issues."""
    bot = "wing-commander[bot]"
    stalled = _bump_snapshot(6, "2026-10-06T00:00:00Z", "fff6", [_verified("fff6", 40)], body_issue=88)
    other = _bump_snapshot(7, "2026-10-07T00:00:00Z", "ggg7", [_verified("ggg7", 41)], body_issue=77)
    try:
        held = board_merge.pick_bump_candidate([stalled], bot, ["88"])
        released = board_merge.pick_bump_candidate([stalled], bot, ["12"])
        next_up = board_merge.pick_bump_candidate([stalled, other], bot, [88])
    except TypeError as exc:
        fail("pick_bump_candidate takes no stalled tracking issues: {0}".format(exc))
        return
    if held is not None:
        fail("a bump PR whose tracking issue is board:stalled is still picked: got {0!r}".format(held))
    elif not isinstance(released, dict) or released.get("pr") != 6:
        fail("a bump PR is held although its tracking issue is not board:stalled: got {0!r}".format(released))
    elif not isinstance(next_up, dict) or next_up.get("pr") != 7:
        fail("a stalled tracking issue's bump PR hides another tracking issue's: got {0!r}".format(next_up))
    else:
        ok("a bump PR whose tracking issue is board:stalled is skipped until the label is removed")
    with open(BOARD_LOOP, encoding="utf-8") as fh:
        merge_code = _run_blocks_text(job_block(fh.read().splitlines(), "merge") or [])
    if not re.search(r"pick-bump\b[^\n]*--stalled-issues\s+\"\$\w+\"", merge_code) \
            or not re.search(r"gh\s+issue\s+list\b[^\n]*--state\s+open\b[^\n]*--json\s+number,labels\b", merge_code) \
            or 'index("board:stalled")' not in merge_code:
        fail("the merge job does not hand pick-bump the open board:stalled issues (--stalled-issues)")
    else:
        ok("the merge job hands pick-bump the open board:stalled issues")


def check_auto_update():
    if not os.path.isfile(AUTO_UPDATE):
        fail("{0} does not exist".format(AUTO_UPDATE))
        return
    with open(AUTO_UPDATE, encoding="utf-8") as fh:
        body = _run_blocks_text(fh.read().splitlines())
    if re.search(r"gh\s+pr\s+merge\b", body):
        fail("{0} merges a PR; the stage never merges its own (FR-013)".format(AUTO_UPDATE))
    if "--bump-verification" not in body:
        fail("{0} does not post the wc-bump-verification record (board_item_marker.py "
             "--bump-verification)".format(AUTO_UPDATE))
    if not failures:
        ok("auto-update stage posts the verification record and never merges")


def main():
    if not os.path.isdir(FIXTURES_DIR):
        fail("fixtures directory {0} does not exist".format(FIXTURES_DIR))
    else:
        check_decision_fixtures()
        check_refusal_fixtures()
    check_transient_refusals()
    check_bump_pick_and_dedup()
    check_round2_findings()
    check_quoted_verification_record()
    check_structural_self_test()
    check_gh_blocked_reasons()
    check_board_loop()
    check_readiness_head_binding()
    check_review_head_binding()
    check_pass2_findings()
    check_stalled_tracking_issue()
    check_auto_update()
    print("verify-board-merge: {0} failure(s).".format(failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
