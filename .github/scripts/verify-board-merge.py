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
Because that job merges, the documents unscoped_merge_claim_docs() lists may
not bring back the retired whole-loop "never merges" sentences
(UNSCOPED_MERGE_CLAIMS), the live contracts HANDOVER_CLAIM_DOCS lists may not
say readiness hands every ready PR to a human (HANDOVER_CLAIMS), and the
board-loop workflow contract's job list names the `merge` job.

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
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import board_merge  # noqa: E402
from board_readiness import CONDITIONS as READINESS_CONDITIONS  # noqa: E402
from board_item_marker import (last_converged_review_head, marker_json,  # noqa: E402
                               render_bump_verification, write_marker)

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
    # #889 (found by the code review of #1059): a rate limit, a rejected
    # token and a DNS or network failure are not GitHub refusing the PR,
    # so none may write the permanent handed-over record.
    "GraphQL: API rate limit exceeded for installation ID 12345. (mergePullRequest)",
    "HTTP 403: You have exceeded a secondary rate limit. Please wait a few minutes before you try again.",
    "HTTP 429: Too Many Requests (https://api.github.com/graphql)",
    "HTTP 401: Bad credentials (https://api.github.com/graphql)",
    "error connecting to api.github.com\ncheck your internet connection or https://githubstatus.com",
    'Post "https://api.github.com/graphql": dial tcp: lookup api.github.com on 127.0.0.53:53: no such host',
    'Post "https://api.github.com/graphql": dial tcp 140.82.112.6:443: connect: connection refused',
    'Post "https://api.github.com/graphql": net/http: TLS handshake timeout',
    'Post "https://api.github.com/graphql": unexpected EOF',
)
# A 403 that is no rate limit is a missing permission: GitHub refused this
# token, and a retry with the same grant cannot clear it.
NON_TRANSIENT_STDERRS = (
    "GraphQL: Resource not accessible by integration (mergePullRequest)",
    "HTTP 403: Resource not accessible by integration (https://api.github.com/graphql)",
)


def check_transient_refusals():
    """A failure that clears itself is never handed over as refused."""
    bad = [(err, board_merge.classify_refusal(err)) for err in TRANSIENT_STDERRS
           if board_merge.classify_refusal(err) not in getattr(board_merge, "RETRYABLE_REFUSAL_CLASSES", ())]
    for err, got in bad:
        fail("transient stderr {0!r} classified as {1!r}, which is handed over".format(err, got))
    if not bad:
        ok("head-moved, base-moved, 5xx, rate-limit, auth and network merge failures are retried, "
           "not handed over")
    wrongly = [err for err in NON_TRANSIENT_STDERRS
               if board_merge.classify_refusal(err) in getattr(board_merge, "RETRYABLE_REFUSAL_CLASSES", ())]
    for err in wrongly:
        fail("a missing permission {0!r} is classified retryable".format(err))
    if not wrongly:
        ok("a 403 that is no rate limit (missing permission) is not retried")


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


def _verification_run(head, run_id=1):
    """What fetch_snapshot() reads for a run that confirms a record at `head`."""
    return {"id": run_id, "path": board_merge.AUTO_UPDATE_WRAPPER_PATH, "event": "schedule",
            "head_branch": "main", "repository": "o/r", "status": "completed", "conclusion": "success",
            "referenced_workflows": [{"path": "o/r/{0}@abc0123".format(board_merge.AUTO_UPDATE_STAGE_PATH),
                                      "ref": "refs/heads/main"}],
            "artifacts": [board_merge.BUMP_VERIFICATION_ARTIFACT_PREFIX + head]}


def _bump_snapshot(number, created, head, comments=(), body_issue=77):
    """fetch_snapshot()'s shape: REST commits and comments, whole (counts),
    and the run the head's record names."""
    snap = {"number": number, "createdAt": created, "headRefOid": head,
            "author": {"login": "app/wing-commander", "is_bot": True},
            "headRefName": "auto-update-spec-kit/v1.2.{0}".format(number),
            "baseRefName": "main",
            "body": "Upgrade\nCloses #{0}\n{1}".format(body_issue, board_merge.BUMP_BODY_MARKER),
            "commits": [{"sha": head, "author": {"login": "wing-commander[bot]", "type": "Bot"}}],
            "files": [{"path": ".specify/x"}],
            "statusCheckRollup": [{"name": "lint", "workflowName": "lint \u00b7 workflows",
                                   "conclusion": "SUCCESS"}],
            "comments": list(comments), "verificationRun": _verification_run(head)}
    return _counted(snap)


def _counted(snap):
    """`snap` with the counts fetch_snapshot() reads beside its lists."""
    return dict(snap, counts={"files": len(snap["files"]), "commits": len(snap["commits"]),
                              "comments": len(snap["comments"]), "head_sha": snap["headRefOid"]})


def _bot_comment(body, cid, created="2026-10-01T00:00:00Z"):
    return {"user": {"login": "wing-commander[bot]", "type": "Bot"}, "created_at": created,
            "id": cid, "body": body}


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
    refused = _counted(dict(verified, comments=verified["comments"] + [_bot_comment(refusal, 11)]))
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
    """Review round 2, superseded by #889: a commit is the bot's only when
    GitHub resolved its author to the App's account (type Bot). A commit
    GitHub resolved to no account is never the bot's, whatever noreply email
    it asserts (anyone can commit as `<slug>[bot]@users.noreply...`), and
    no commit carries an email to decide by. Quoted stderr cannot close its
    code fence."""
    bot = "wing-commander[bot]"
    snap = _bump_snapshot(3, "2026-10-03T00:00:00Z", "ddd4", [_verified("ddd4", 20)])
    resolved = dict(snap, commits=[{"sha": "ddd4", "author": {"login": bot, "type": "Bot"}}])
    unresolved = dict(snap, commits=[{"sha": "ddd4", "author": None,
                                      "email": "wing-commander[bot]@users.noreply.github.com"}])
    user = dict(snap, commits=[{"sha": "ddd4", "author": {"login": bot, "type": "User"}}])
    if not board_merge._attributed_to_auto_update(resolved, bot):
        fail("a commit GitHub resolved to the App's bot account is not attributed to the bot")
    elif board_merge._attributed_to_auto_update(unresolved, bot):
        fail("a commit GitHub resolved to no account is attributed to the bot by its self-asserted email")
    elif board_merge._attributed_to_auto_update(user, bot):
        fail("a commit by a user account named like the App is attributed to the bot")
    else:
        ok("a commit is the bot's only when GitHub resolved its author to the App's bot account")
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


_RUN_KEY_RE = re.compile(r"^(\s*(?:-\s+)?)run:(?:\s+(.*))?$")


def _run_blocks_text(lines):
    """The non-comment lines of every `run:` body in `lines` -- a workflow,
    a job or a step -- and nothing else: an `env:`, `if:` or `with:` value
    is not code the job runs, so a rule about what the job runs must not
    fire on it (#889, code review of #1059). A block scalar (`run: |`)
    runs to the first non-blank line indented no deeper than its key; an
    inline value (`run: cmd`) is that one line."""
    out = []
    lines = list(lines)
    i = 0
    while i < len(lines):
        match = _RUN_KEY_RE.match(lines[i])
        i += 1
        if not match:
            continue
        value = (match.group(2) or "").strip()
        if value and value[0] not in "|>":
            out.append(value)
            continue
        key_col = len(match.group(1))
        while i < len(lines):
            line = lines[i]
            if line.strip() and len(line) - len(line.lstrip()) <= key_col:
                break
            if not line.lstrip().startswith("#"):
                out.append(line)
            i += 1
    return "\n".join(out)


def check_run_blocks_text_self_test():
    """_run_blocks_text() reads `run:` bodies only: a forbidden flag or a
    refusal phrase in an `env:`, `if:` or `with:` value, or in a comment, is
    not in its text, and a block or inline `run:` is."""
    workflow = (
        "jobs:\n"
        "  merge:\n"
        "    if: \"!contains(github.event.head_commit.message, '--admin')\"\n"
        "    steps:\n"
        "      - name: Merge\n"
        "        env:\n"
        "          NOTE: not mergeable\n"
        "        with:\n"
        "          args: --auto\n"
        "        run: |\n"
        "          # --admin in a comment\n"
        "          gh pr merge \"$PR\" --squash\n"
        "\n"
        "          echo done\n"
        "        shell: bash\n"
        "      - run: echo inline\n"
        "      - name: After\n"
        "        if: always()\n")
    code = _run_blocks_text(workflow.splitlines())
    leaked = [word for word in ("--admin", "not mergeable", "--auto", "shell:", "always()")
              if word in code]
    missing = [word for word in ("gh pr merge", "echo done", "echo inline") if word not in code]
    if leaked or missing:
        fail("self-test: _run_blocks_text() read {0} outside a `run:` body and missed {1} "
             "inside one".format(leaked, missing))
    else:
        ok("self-test: _run_blocks_text() reads `run:` bodies only, block and inline")


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


STALE_READINESS_CLAIMS = ("Awaiting a human merge", "this loop never merges, approves, or enables auto-merge")


def readiness_stale_claims(text):
    """Each STALE_READINESS_CLAIMS phrase found in a non-comment line of the
    readiness job (case-insensitive)."""
    job = job_block(text.splitlines(), "readiness") or []
    code = _run_blocks_text(job).lower()
    return [claim for claim in STALE_READINESS_CLAIMS if claim.lower() in code]


def check_readiness_stale_claims_self_test():
    old = ("  readiness:\n    steps:\n      - run: |\n          body=\"$(printf 'decision: %s\\n\\n"
           "Awaiting a human merge -- this loop never merges, approves, or enables auto-merge.' x)\"\n"
           "  merge:\n")
    if readiness_stale_claims(old) != list(STALE_READINESS_CLAIMS):
        fail("self-test: the old readiness sentence is not caught: {0}".format(readiness_stale_claims(old)))
    elif readiness_stale_claims(old.replace("          body", "          # body")):
        fail("self-test: a commented-out readiness line is flagged")
    else:
        ok("self-test: the old readiness sentence is caught, a comment is not")


# The prose half of the same claim (#889, found by the code review of #1227):
# the `merge` job can merge, so these retired sentences, each of which said
# the whole loop never merges, must not come back. Exact sentences, a
# regression guard, not a paraphrase detector. Matched after comment markers,
# quotes and line breaks are folded away, so a phrase wrapped across comment
# or docstring lines is still found.
UNSCOPED_MERGE_CLAIMS = (
    "this loop never merges, approves, or enables auto-merge",
    "the loop may report a pr ready, but it may never merge",
    "the loop stops at ready to merge",
    # select's resume note and the closing-step header comment (#889, found
    # by the code review of #1237): with the switch on, the merge job may
    # merge an awaiting-merge PR and posts its own announcement.
    "is awaiting a human merge",
    "the unmet condition, the human merge",
)
# Every board_*.py module (glob, so a new one is read without an edit here)
# and board-loop.yml itself, besides the documents named below: a fixed list
# of four missed board_eligibility.py's AWAITING_MERGE_STEP comment (found by
# the code review of #1237).
UNSCOPED_MERGE_CLAIM_DOCS = (
    ".github/scripts/verify-board-readiness.py",
    ".github/workflows/board-loop.yml",
    ".github/workflows/lint-workflows.yml",
    "specs/057-autonomous-board-loop/contracts/readiness-report.md",
)
UNSCOPED_MERGE_CLAIM_GLOB = ".github/scripts/board_*.py"


def unscoped_merge_claim_docs():
    modules = sorted(glob.glob(UNSCOPED_MERGE_CLAIM_GLOB))
    return list(UNSCOPED_MERGE_CLAIM_DOCS) + modules


def _fold_prose(text):
    """Lowercased text with `#` comment markers, quote characters and every
    run of whitespace folded to one space."""
    text = re.sub(r"(?m)^\s*#+", " ", text.lower())
    text = re.sub(r"[\"'`“”]", "", text)
    return re.sub(r"\s+", " ", text)


def unscoped_merge_claims(text):
    folded = _fold_prose(text)
    return [claim for claim in UNSCOPED_MERGE_CLAIMS if claim in folded]


def check_unscoped_merge_claims_self_test():
    wrapped = ("      # re-derived head-SHA evidence, and this loop never merges, approves,\n"
               "      # or enables auto-merge -- these six fixtures\n")
    contract = 'the\nloop stops at "ready to merge", so the item releases the board\n'
    docstring = "The loop may report a PR ready, but it may never merge, approve, or enable\n"
    scoped = ("The readiness job itself never merges, approves, or enables auto-merge;\n"
              "# no board-loop job but `merge` merges, approves, or enables auto-merge\n")
    select_note = ('                  note = "recorded pr {0} is awaiting a human merge ({1}) -- nothing to do '
                   'this run".format(\n')
    closing = ("# readiness report or the unmet condition, the human merge, and the proof\n"
               "# run, per whichever step that job represents\n")
    if unscoped_merge_claims(select_note) != [UNSCOPED_MERGE_CLAIMS[3]]:
        fail("self-test: select's old 'awaiting a human merge' resume note is not caught")
    elif unscoped_merge_claims(closing) != [UNSCOPED_MERGE_CLAIMS[4]]:
        fail("self-test: the old closing-step comment's 'the human merge' is not caught")
    elif unscoped_merge_claims(wrapped) != [UNSCOPED_MERGE_CLAIMS[0]]:
        fail("self-test: a wrapped 'this loop never merges' comment is not caught")
    elif unscoped_merge_claims(docstring) != [UNSCOPED_MERGE_CLAIMS[1]]:
        fail("self-test: the old board_readiness docstring claim is not caught")
    elif unscoped_merge_claims(contract) != [UNSCOPED_MERGE_CLAIMS[2]]:
        fail("self-test: the old contract's 'stops at \"ready to merge\"' is not caught")
    elif unscoped_merge_claims(scoped):
        fail("self-test: a claim scoped to the readiness job is flagged")
    else:
        ok("self-test: unscoped 'never merges' prose is caught, a scoped claim is not")


def check_unscoped_merge_claims():
    docs = unscoped_merge_claim_docs()
    for module in (".github/scripts/board_readiness.py", ".github/scripts/board_eligibility.py"):
        if module not in docs:
            fail("{0} matched no {1}; the unscoped-claim scan has lost its board modules".format(
                module, UNSCOPED_MERGE_CLAIM_GLOB))
    for path in docs:
        if not os.path.isfile(path):
            fail("{0} does not exist; run from the repository root".format(path))
            continue
        with open(path, encoding="utf-8") as fh:
            found = unscoped_merge_claims(fh.read())
        if found:
            fail("{0} says the whole board loop never merges, though its `merge` job does with "
                 "WING_COMMANDER_BOARD_AUTO_MERGE on; scope it to the readiness job: {1}".format(path, found))
        else:
            ok("{0} makes no unscoped 'never merges' claim".format(path))


# The live contracts' half of the same scoping (#889, found by the code review
# of #1237): with WING_COMMANDER_BOARD_AUTO_MERGE on, the `merge` job may merge
# what readiness reported ready, so no live contract may say readiness hands
# every such PR to a human, that the whole board loop never merges, or that
# the no-merge invariant forbids merge calls in all of board-loop.yml. Exact
# retired sentences, folded as UNSCOPED_MERGE_CLAIMS are.
HANDOVER_CLAIMS = (
    "handed the pr to a human",
    "handed it to a human",
    "the board loop never checks this because it never merges",
    "scans board-loop.yml for merge calls that must not exist",
    "deferring merge to a human",
)
HANDOVER_CLAIM_DOCS = (
    BOARD_LOOP,
    ".github/scripts/verify-constitution-merge-class-parity.py",
    "specs/057-autonomous-board-loop/contracts/readiness-report.md",
    "specs/061-marker-owned-in-flight/contracts/in-flight-detection.md",
    "specs/061-marker-owned-in-flight/contracts/resume-recovery.md",
    "specs/062-lifecycle-review-gate/contracts/readiness-and-merge.md",
)
BOARD_LOOP_CONTRACT = "specs/057-autonomous-board-loop/contracts/board-loop-workflow.md"
MERGE_CONTRACT = "specs/115-board-loop-self-merge/contracts/board-merge.md"


def handover_claims(text):
    folded = _fold_prose(text)
    return [claim for claim in HANDOVER_CLAIMS if claim in folded]


def _jobs_section(text):
    """The board-loop workflow contract's "## Jobs ..." sections, joined."""
    parts = re.split(r"(?m)^## ", text)
    return "\n".join(part for part in parts if part.startswith("Job"))


def lists_merge_job(contract_text):
    """True when a numbered entry in the contract's job list names the
    `merge` job and points at its own contract."""
    return re.search(r"(?m)^\d+\. `merge` \S+ " + re.escape(MERGE_CONTRACT),
                     _jobs_section(contract_text)) is not None


def check_handover_claims_self_test():
    in_flight = ("    `awaiting-merge` (#532) never qualifies either, whatever its PR's\n"
                 "    state: readiness already handed the PR to a human, and no job\n")
    resume = "   ready and handed it to a human), and its pr either resolves OPEN or\n"
    mergeable = ("   `mergeable` field is `MERGEABLE` (not `UNKNOWN`/`CONFLICTING`); the\n"
                 "   board loop never checks this because it never merges, so no existing\n")
    docstring = ("verify-board-readiness.py's `check_no_merge_invariant`, which scans\n"
                 "board-loop.yml for merge calls that must not exist. Here the merge call is\n")
    header = ("# closed resume path, prove) -- deferring merge to a human (FR-003).\n")
    scoped = ("    state: the readiness job stopped at ready, and the `merge` job\n"
              "   board loop's readiness job never checks this because it never merges\n"
              "board-loop.yml outside its `merge` job (spec 115) for merge calls that must\n")
    stale_jobs = ("## Jobs (schedule/dispatch path)\n\n"
                  "6. `readiness` — contracts/readiness-report.md. Never merges (FR-068).\n\n"
                  "## Job (resume path)\n\n7. `prove` — contracts/prove-step.md\n")
    listed_jobs = stale_jobs.replace(
        "\n\n## Job (resume path)",
        "\n7. `merge` — {0}.\n\n## Job (resume path)".format(MERGE_CONTRACT))
    elsewhere = stale_jobs + "\n## Notes\n\n7. `merge` — {0}.\n".format(MERGE_CONTRACT)
    if handover_claims(in_flight) != [HANDOVER_CLAIMS[0]]:
        fail("self-test: in-flight-detection.md's 'handed the PR to a human' is not caught")
    elif handover_claims(resume) != [HANDOVER_CLAIMS[1]]:
        fail("self-test: resume-recovery.md's 'handed it to a human' is not caught")
    elif handover_claims(mergeable) != [HANDOVER_CLAIMS[2]]:
        fail("self-test: readiness-and-merge.md's 'board loop never checks this' is not caught")
    elif handover_claims(docstring) != [HANDOVER_CLAIMS[3]]:
        fail("self-test: the parity gate's whole-file no-merge description is not caught")
    elif handover_claims(header) != [HANDOVER_CLAIMS[4]]:
        fail("self-test: board-loop.yml's header 'deferring merge to a human' is not caught")
    elif handover_claims(scoped):
        fail("self-test: a claim scoped to the readiness job or outside `merge` is flagged")
    elif lists_merge_job(stale_jobs):
        fail("self-test: a job list with no `merge` entry passes")
    elif not lists_merge_job(listed_jobs):
        fail("self-test: a job list naming `merge` and its contract is not recognised")
    elif lists_merge_job(elsewhere):
        fail("self-test: a `merge` entry outside the Jobs sections passes")
    else:
        ok("self-test: 'handed to a human' contract prose is caught, and the job list must name `merge`")


def check_handover_claims():
    for path in HANDOVER_CLAIM_DOCS + tuple(unscoped_merge_claim_docs()):
        if not os.path.isfile(path):
            fail("{0} does not exist; run from the repository root".format(path))
            continue
        with open(path, encoding="utf-8") as fh:
            found = handover_claims(fh.read())
        if found:
            fail("{0} says readiness hands the PR to a human or the board loop never merges, "
                 "though the `merge` job may merge it with WING_COMMANDER_BOARD_AUTO_MERGE on; "
                 "say the readiness job stops at ready and the `merge` job or a human takes it: "
                 "{1}".format(path, found))
        else:
            ok("{0} makes no 'handed to a human' claim".format(path))
    if not os.path.isfile(BOARD_LOOP) or not os.path.isfile(BOARD_LOOP_CONTRACT):
        fail("{0} or {1} does not exist; run from the repository root".format(
            BOARD_LOOP, BOARD_LOOP_CONTRACT))
        return
    with open(BOARD_LOOP, encoding="utf-8") as fh:
        has_merge_job = re.search(r"(?m)^  merge:\s*$", fh.read()) is not None
    with open(BOARD_LOOP_CONTRACT, encoding="utf-8") as fh:
        listed = lists_merge_job(fh.read())
    if has_merge_job and not listed:
        fail("{0} has a `merge` job but {1}'s job list has no `merge` entry pointing at {2}".format(
            BOARD_LOOP, BOARD_LOOP_CONTRACT, MERGE_CONTRACT))
    else:
        ok("{0}'s job list names the `merge` job".format(BOARD_LOOP_CONTRACT))


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

    # Owner, 2026-11-25: the readiness report said "Awaiting a human merge --
    # this loop never merges, approves, or enables auto-merge." while the
    # merge job below merged fix-class PRs with the switch on. Neither half
    # of that sentence may come back.
    stale = readiness_stale_claims(text)
    if stale:
        fail("board-loop.yml's readiness report carries a stale merge claim again: {0}".format(stale))
    else:
        ok("readiness report makes no 'awaiting a human merge' / 'never merges' claim")

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


SNAPSHOT_STEP = "Fetch the PR snapshot at its current head"
ISSUE_COMMENTS_FETCH = 'issues/$ISSUE_NUMBER/comments" --paginate'


def step_block(job_lines, name):
    """The lines of the step named `name` in a job, up to the job's next step."""
    start = None
    for i, line in enumerate(job_lines):
        if re.fullmatch(r"      - name: (.*)", line):
            if start is not None:
                return job_lines[start:i]
            if line == "      - name: {0}".format(name):
                start = i
    return job_lines[start:] if start is not None else []


def review_head_binding_problems(merge_job):
    """Follow-up review of PR #1059 (FR-003): readiness's "ready" can come
    from an earlier run's step=readiness marker that never re-checks the
    head the review converged on, so decide() also needs the issue's newest
    review verdict to have converged on the snapshot's head
    (fixtures/board-merge/fix-review_converged-stale-head.json). The merge
    job must read those verdicts fresh and hand them to every decide call,
    the retry's included, or the fixture's guard never runs live. The fetch
    is looked for in the snapshot step itself (pass 6 of review-until-clean):
    the Announce step's own fetch of the same comments, for the marker's
    round, runs after the decision and feeds none of it."""
    code = _run_blocks_text(merge_job)
    decides = re.findall(r"board_merge\.py\" decide\b(?:[^\n]*\\\n)*[^\n]*", code)
    problems = []
    if ISSUE_COMMENTS_FETCH not in _run_blocks_text(step_block(merge_job, SNAPSHOT_STEP)):
        problems.append("the merge job's '{0}' step does not fetch the fix issue's comments".format(SNAPSHOT_STEP))
    if len(decides) < 2:
        problems.append("expected the decision and the retry's re-decision, found {0} decide call(s)".format(
            len(decides)))
    for call in decides:
        if '--issue-comments "$RUNNER_TEMP/board-merge-issue-comments.json"' not in call:
            problems.append("a decide call does not pass the freshly read issue comments")
    return problems


def check_review_head_binding():
    with open(BOARD_LOOP, encoding="utf-8") as fh:
        merge_job = job_block(fh.read().splitlines(), "merge") or []
    problems = review_head_binding_problems(merge_job)
    for problem in problems:
        fail("review head binding: {0}".format(problem))
    if not problems:
        ok("the merge job re-reads the review verdicts and every decide call binds them to its head")
    # Self-test: the merge job with the snapshot step's fetch removed, the
    # Announce step's fetch left in place, is caught.
    snapshot = step_block(merge_job, SNAPSHOT_STEP)
    if not snapshot:
        fail("review head binding self-test: the merge job has no '{0}' step".format(SNAPSHOT_STEP))
        return
    start = merge_job.index(snapshot[0])
    mutated = (merge_job[:start] + [line for line in snapshot if ISSUE_COMMENTS_FETCH not in line]
               + merge_job[start + len(snapshot):])
    if not review_head_binding_problems(mutated):
        fail("review head binding self-test: a snapshot step without the issue-comments fetch is not caught "
             "(another step's fetch of the same comments feeds no decision)")
    else:
        ok("review head binding self-test: a snapshot step without the issue-comments fetch is caught")


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
        # gh renders a bot merger as {"is_bot": true, "login": "app/<slug>"}
        # (mergedBy{login,...on User{id,name}}, the same shape as author).
        # A user whose login equals the App slug is not the App (#889,
        # found by the code review of #1084).
        cases = (({"mergedBy": {"login": "app/wing-commander", "is_bot": True}, "headRefOid": "aaa1"}, "aaa1", True),
                 ({"mergedBy": {"login": "Wing-Commander[bot]", "is_bot": True}, "headRefOid": "aaa1"},
                  "aaa1", True),
                 ({"mergedBy": {"login": "wing-commander", "is_bot": False, "id": "U_1"}, "headRefOid": "aaa1"},
                  "aaa1", False),
                 ({"mergedBy": {"login": "wing-commander"}, "headRefOid": "aaa1"}, "aaa1", False),
                 ({"mergedBy": {"login": "app/wing-commander", "is_bot": True}, "headRefOid": "bbb2"},
                  "aaa1", False),
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


SNAPSHOT_CALL_RE = re.compile(r"board_merge\.py\"? snapshot\b")


def snapshot_fetch_problems(merge_job):
    """#889: every snapshot a decision reads comes from board_merge.py
    snapshot (whole REST lists, their counts, the verification run), never
    a bare `gh pr view --json` of the truncating lists; and each step that
    fetches one hands it the token it reads the run with."""
    problems = []
    code = _run_blocks_text(merge_job)
    # Any `gh pr view --json` naming a truncating list, or a field list it
    # cannot see (a variable), is a snapshot read outside fetch_snapshot().
    if re.search(r"gh\s+pr\s+view\b[^\n]*--json[\s=]+(\"?\$|[\w,]*\b(files|commits|comments)\b)", code) \
            or "snapshot-fields" in code:
        problems.append("the merge job reads files, commits or comments with a bare `gh pr view --json`")
    steps = [block for block in re.split(r"\n      - name: ", "\n".join(merge_job))[1:]]
    fetching = [block for block in steps if SNAPSHOT_CALL_RE.search(_run_blocks_text(block.splitlines()))]
    if len(fetching) < 3:
        problems.append("expected the candidate scan, the fresh fetch and the retry to use board_merge.py "
                        "snapshot, found {0} step(s)".format(len(fetching)))
    for block in fetching:
        if "WC_ACTIONS_TOKEN: ${{ github.token }}" not in block:
            problems.append("step '{0}' fetches a snapshot without WC_ACTIONS_TOKEN".format(block.split("\n", 1)[0]))
    return problems


def check_889_findings():
    """#889, before WING_COMMANDER_BOARD_AUTO_MERGE is enabled: identity is
    the account GitHub resolved (type Bot), never a login or email alone;
    each list is whole; a verification record counts only when the Actions
    API confirms its run. The decision fixtures cover the rules; this covers
    the bump-shape filters and the workflows that feed them."""
    bot = "wing-commander[bot]"
    impostor = {"number": 9, "author": {"login": "wing-commander", "is_bot": False},
                "headRefName": "auto-update-spec-kit/v1.2.9", "createdAt": "2026-10-09T00:00:00Z"}
    snap = dict(_bump_snapshot(9, "2026-10-09T00:00:00Z", "hhh9", [_verified("hhh9", 50)]),
                author=impostor["author"])
    if board_merge.bump_shaped([impostor], bot) or board_merge.pick_bump_candidate([snap], bot) is not None:
        fail("a user account named like the App is taken as the bot's auto-update PR")
    else:
        ok("a user account named like the App is never an auto-update PR author")
    with open(BOARD_LOOP, encoding="utf-8") as fh:
        merge_job = job_block(fh.read().splitlines(), "merge") or []
    problems = snapshot_fetch_problems(merge_job)
    for problem in problems:
        fail("snapshot fetch: {0}".format(problem))
    if not problems:
        ok("every merge-job snapshot is board_merge.py snapshot's whole, run-bound read")
    for pasted_read in ('gh pr view "$n" -R "$GITHUB_REPOSITORY" --json "$fields" > x.json',
                        'gh pr view "$n" -R "$GITHUB_REPOSITORY" --json "$snapshot_fields" > x.json',
                        'gh pr view "$n" -R "$GITHUB_REPOSITORY" --json number,files,commits,comments > x.json'):
        if not snapshot_fetch_problems(merge_job + ["      - run: |", "          " + pasted_read]):
            fail("snapshot fetch self-test: a pasted `{0}` read is not caught".format(pasted_read))
        else:
            ok("snapshot fetch self-test: a pasted `{0}` read is caught".format(pasted_read))
    wrapper = board_merge.AUTO_UPDATE_WRAPPER_PATH
    if not os.path.isfile(wrapper):
        fail("AUTO_UPDATE_WRAPPER_PATH {0} does not exist".format(wrapper))
    else:
        with open(wrapper, encoding="utf-8") as fh:
            if "uses: ./{0}".format(board_merge.AUTO_UPDATE_STAGE_PATH) not in fh.read():
                fail("{0} does not call {1}".format(wrapper, board_merge.AUTO_UPDATE_STAGE_PATH))
            else:
                ok("the verification run's workflow paths name the real wrapper and stage")
    with open(AUTO_UPDATE, encoding="utf-8") as fh:
        stage = fh.read()
    upload = "name: {0}${{{{ steps.open-pr.outputs.verified-head }}}}".format(
        board_merge.BUMP_VERIFICATION_ARTIFACT_PREFIX)
    if upload not in stage or 'echo "verified-head=$head_sha"' not in stage:
        fail("{0} does not upload the artifact naming the head its record verified ({1})".format(AUTO_UPDATE, upload))
    else:
        ok("the auto-update run uploads the artifact that binds its record to the head")
    for problem in verified_head_upload_problems(stage):
        fail("{0}: {1}".format(AUTO_UPDATE, problem))
    check_verification_run_read_warns()
    check_verification_run_keeps_ref()
    check_merge_contract_names_stage_ref()


def verified_head_upload_problems(stage):
    """Once the record is posted, nothing between it and the upload may fail
    the step (a skipped upload strands a verified PR, unconfirmable for
    good), and a missing record file fails the upload instead of leaving a
    green run with no artifact."""
    problems = []
    lines = stage.splitlines()
    start = next((i for i, line in enumerate(lines) if 'echo "verified-head=$head_sha"' in line), None)
    end = next((i for i, line in enumerate(lines) if "- name: Record the verified head on the run" in line), None)
    if start is None or end is None or end < start:
        return ["the open-pr step's verified-head output or the upload step is missing"]
    commands = re.sub(r"\\\n\s*", " ", "\n".join(lines[start + 1:end])).splitlines()
    for line in commands:
        code = line.strip()
        if code.startswith("gh ") and "||" not in code:
            problems.append("`{0}` after the verified-head output can fail the step and skip the upload".format(
                code[:60]))
    upload = "\n".join(lines[end:end + 12])
    if "if-no-files-found: error" not in upload:
        problems.append("the verified-head upload does not set `if-no-files-found: error`")
    return problems


def check_verification_run_read_warns():
    """A verification run that cannot be read fails closed and says why on
    stderr (a 403 is a token or permission fault, not an unverified PR)."""
    import contextlib
    import io
    import subprocess

    def refused(args, token=None):
        raise subprocess.CalledProcessError(1, ["gh"] + list(args), stderr="HTTP 403: Resource not accessible")
    saved, err = board_merge._gh, io.StringIO()
    board_merge._gh = refused
    try:
        with contextlib.redirect_stderr(err):
            run = board_merge._fetch_verification_run("o/r", {"run_id": "9"}, "t")
    finally:
        board_merge._gh = saved
    if run is not None or "HTTP 403" not in err.getvalue():
        fail("an unreadable verification run is not reported on stderr (got {0!r})".format(err.getvalue()))
    else:
        ok("an unreadable verification run fails closed and names the refusal")


def check_verification_run_keeps_ref():
    """#889 (found by the code review of #1084): the snapshot carries each
    called workflow's resolved `ref` beside its path, and a run whose stage
    call resolved to a ref other than main does not confirm a record, even
    with head_branch main. The shape is the Actions API's (a schedule run
    of the wrapper on main: path `<repo>/<stage>@<sha>`, ref refs/heads/main)."""
    import json as _json
    api_run = {"id": 9, "path": board_merge.AUTO_UPDATE_WRAPPER_PATH, "event": "schedule",
               "head_branch": "main", "repository": {"full_name": "o/r"}, "status": "completed",
               "conclusion": "success",
               "referenced_workflows": [{"path": "o/r/{0}@abc0123".format(board_merge.AUTO_UPDATE_STAGE_PATH),
                                         "ref": "refs/heads/main", "sha": "abc0123"}]}
    head = "cccc333"
    saved_gh, saved_items = board_merge._gh, board_merge._gh_items
    board_merge._gh = lambda args, token=None: _json.dumps(api_run)
    board_merge._gh_items = lambda path, token, jq: [
        {"name": board_merge.BUMP_VERIFICATION_ARTIFACT_PREFIX + head}]
    try:
        run = board_merge._fetch_verification_run("o/r", {"run_id": "9"}, "t")
    finally:
        board_merge._gh, board_merge._gh_items = saved_gh, saved_items
    record = {"run_id": "9", "head_sha": head, "result": "passed"}
    problems = []
    if not board_merge.verification_run_confirms(record, run, head):
        problems.append("a fetched main run calling the stage from main does not confirm its record")
    for ref in ("refs/heads/attacker-branch", None):
        other = dict(run, referenced_workflows=[dict(w, ref=ref) for w in run["referenced_workflows"]])
        if board_merge.verification_run_confirms(record, other, head):
            problems.append("a run whose stage call resolved to {0!r} confirms a record".format(ref))
    for problem in problems:
        fail(problem)
    if not problems:
        ok("the verification run's stage call must resolve to refs/heads/main")


def merge_contract_stage_ref_problems(text):
    """#889 (found by the code review of #1284): the live contract says
    what verification_run_confirms() checks, so the stage call's resolved
    `ref` must appear in both places the contract names the run's facts:
    step 4's snapshot (called workflows with their `ref`) and the
    evaluate_bump bullet (the call's `ref` is refs/heads/<BASE_BRANCH>)."""
    problems = []
    want = "`refs/heads/{0}`".format(board_merge.BASE_BRANCH)
    step4 = re.search(r"(?m)^4\. .*$", text)
    if not step4 or "called workflows each with the `ref`" not in step4.group(0):
        problems.append("step 4 does not say the snapshot keeps each called workflow's `ref`")
    bullet = re.search(r"(?m)^- `evaluate_bump\(.*$", text)
    if not bullet or "AUTO_UPDATE_STAGE_PATH" not in bullet.group(0) or want not in bullet.group(0):
        problems.append("the evaluate_bump bullet does not require the stage call's `ref` to be {0}".format(want))
    return problems


def check_merge_contract_names_stage_ref():
    with open(MERGE_CONTRACT, encoding="utf-8") as fh:
        text = fh.read()
    problems = merge_contract_stage_ref_problems(text)
    for problem in problems:
        fail("{0}: {1}".format(MERGE_CONTRACT, problem))
    stale = text.replace(" each with the `ref` the call resolved to", "").replace(
        " and that call's `ref` is `refs/heads/{0}`".format(board_merge.BASE_BRANCH), "")
    if stale == text or len(merge_contract_stage_ref_problems(stale)) != 2:
        fail("the contract stage-ref check does not refuse a contract without the ref requirement")
    if not problems:
        ok("{0} names the stage call's ref requirement".format(MERGE_CONTRACT))


MARKER_DROPPED_FIELDS = ("spec_request", "outcome_reason", "recovery_attempted", "nr_*")
# The board_item_marker.py flags that would carry one of those fields (or a
# backlog line id) onto a merged or handed-over marker.
MARKER_DROPPED_FLAGS = ("--outcome-reason", "--recovery-attempted", "--nr-count",
                        "--nr-head-sha", "--nr-class", "--nr-reason", "--spec-request", "--line")


def merge_contract_marker_fields_problems(text):
    """#889 (found by the code review of #1059), settled by the session
    decision on #1321: merged and handed-over markers keep dropping the
    newest marker's other fields, and step 8 says so."""
    step8 = re.search(r"(?m)^8\. .*$", text)
    if not step8:
        return ["the contract has no step 8"]
    line = step8.group(0)
    problems = []
    if "carry only the round, the branch and the base" not in line:
        problems.append("step 8 does not say merged and handed-over markers carry only the round, the branch and the base")
    missing = [f for f in MARKER_DROPPED_FIELDS if "`{0}`".format(f) not in line]
    if missing:
        problems.append("step 8 does not name the fields it drops: {0}".format(", ".join(missing)))
    return problems


def merge_marker_flag_problems(merge_code):
    """The merge job's merged/handed-over render passes no dropped field."""
    render = re.search(r"marker_args=\((.*?)\)", merge_code, re.S)
    if not render:
        return ["the merge job no longer builds its marker from marker_args=(...)"]
    calls = [l for l in merge_code.splitlines()
             if "board_item_marker.py" in l and re.search(r"--step\s+(merged|handed-over)\b", l)]
    if len(calls) != 2:
        return ["expected one merged and one handed-over board_item_marker.py render, found {0}".format(len(calls))]
    text = render.group(1) + "\n" + "\n".join(calls)
    return ["the merged/handed-over marker passes {0}, a field step 8 says it drops".format(flag)
            for flag in MARKER_DROPPED_FLAGS if re.search(re.escape(flag) + r"\b", text)]


def check_merge_contract_marker_fields():
    with open(MERGE_CONTRACT, encoding="utf-8") as fh:
        text = fh.read()
    problems = merge_contract_marker_fields_problems(text)
    for problem in problems:
        fail("{0}: {1}".format(MERGE_CONTRACT, problem))
    stale = re.sub(r"(?m)^(8\. Fix class: write the issue marker `merged` or `handed-over`\. ).*?\(#889\)[^.]*\. ",
                   r"\1", text)
    if stale == text or len(merge_contract_marker_fields_problems(stale)) != 2:
        fail("the step-8 marker-fields check does not refuse a contract without the sentence")
    with open(BOARD_LOOP, encoding="utf-8") as fh:
        merge_code = _run_blocks_text(job_block(fh.read().splitlines(), "merge") or [])
    flag_problems = merge_marker_flag_problems(merge_code)
    for problem in flag_problems:
        fail(problem)
    carried = merge_code.replace('--base-sha "$BASE_SHA"', '--base-sha "$BASE_SHA" --outcome-reason "$r"', 1)
    if carried == merge_code or not merge_marker_flag_problems(carried):
        fail("the marker-flag check does not refuse a merged marker that carries --outcome-reason")
    if not problems and not flag_problems:
        ok("merged and handed-over markers carry only the round, branch and base, as step 8 says")


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


def check_merged_proof_disposition():
    """#889: prove-gate enters prove only for the board loop's own fix PR,
    so a merged bump's announcement must not promise a re-drive. On all four
    bumps merged before this (#1089, #1109, #1124, #1136) it said "a proof
    re-drive follows the merge" and the closed-PR run skipped prove. A fix
    PR's disposition is still board_prove.actions_only()'s."""
    bot = "wing-commander[bot]"
    snap = _bump_snapshot(10, "2026-10-10T00:00:00Z", "iii0", [_verified("iii0", 60)])
    decision = board_merge.decide({"class": "bump", "snapshot": snap, "bot_login": bot,
                                   "paused": False, "switch_on": True})
    text = board_merge.render_announcement(decision, "merged", snap, merge_sha="mmm0")
    proof = next((line for line in text.splitlines() if line.startswith("Proof: ")), "")
    if "re-drive follows the merge" in proof or "no proof re-drive follows" not in proof:
        fail("a merged bump's announcement promises a proof re-drive prove never runs: {0!r}".format(proof))
    elif "not needed" in proof:
        fail("a merged bump's announcement says a proof is not needed, a decision nobody made: {0!r}".format(proof))
    else:
        ok("a merged bump's announcement says no proof re-drive follows")
    fix = dict(decision, **{"class": "fix"})
    for files, want in (([{"path": ".github/workflows/x.yml"}], "a proof re-drive follows the merge"),
                        ([{"path": "docs/x.md"}], "no proof re-drive is needed"),
                        # #889: a rename away from a workflow is an Actions change.
                        ([{"path": "docs/x.yml", "previousPath": ".github/workflows/x.yml"}],
                         "a proof re-drive follows the merge")):
        line = next((l for l in board_merge.render_announcement(fix, "merged", dict(snap, files=files),
                                                                 merge_sha="mmm0").splitlines()
                     if l.startswith("Proof: ")), "")
        if want not in line:
            fail("a merged fix PR touching {0} is announced {1!r}, want {2!r}".format(files[0], line, want))
        else:
            ok("a merged fix PR touching {0} keeps the actions_only() disposition".format(files[0]))


def _board_marker(payload):
    return "<!-- wing-commander-board-item: {0} -->".format(marker_json(payload))


def check_marker_round_and_verdict():
    """#889 (found by the code review of #1059). A merged/handed-over
    marker carries the round of the newest well-formed marker, so an
    unparsable newest marker does not hand a re-admitted item its review
    round budget back; and a review verdict counts as converged only as
    the whole comment the review job posts, never the sentence quoted in
    another loop comment."""
    bot = "wing-commander[bot]"
    comments = [
        _bot_comment("Review round 3: pushed a follow-up.\n\n" + _board_marker(
            {"step": "review", "round": 3, "pr": 42, "branch": "fix/12-thing", "base_sha": None}),
            40, "2026-10-01T00:00:00Z"),
        _bot_comment("Status.\n\n<!-- wing-commander-board-item: {not json} -->", 41, "2026-10-02T00:00:00Z"),
    ]
    script = os.path.join(SCRIPTS_DIR, "board_item_marker.py")
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "comments.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(comments, fh)
        env = {key: value for key, value in os.environ.items()
               if key not in ("GITHUB_RUN_ID", "BOARD_LINE_ID")}
        proc = subprocess.run([sys.executable, "-I", script, "--step", "handed-over", "--pr", "42",
                               "--branch", "fix/12-thing", "--carry-round-from", path, "--bot-login", bot],
                              capture_output=True, text=True, env=env)
    match = re.search(r'"round": (\d+)', proc.stdout)
    if proc.returncode != 0 or not match or match.group(1) != "3":
        fail("--carry-round-from past an unparsable newest marker gave round {0!r} (rc={1}), expected 3".format(
            match.group(1) if match else proc.stdout, proc.returncode))
    else:
        ok("--carry-round-from carries the newest well-formed marker's round past an unparsable one")

    head = "a" * 40
    # The converged comment exactly as the review job renders it: board-loop.yml's
    # own printf format around write_marker()'s own output, with and without the
    # `**Run:**` line, so a wording change on either side fails here rather than
    # silently in every later merge and resume (review of #1321).
    found = None
    if os.path.isfile(BOARD_LOOP):
        with open(BOARD_LOOP, encoding="utf-8") as fh:
            found = re.search(r"printf '(Review round %s converged -- [^']*)'", fh.read())
    if found is None:
        fail("{0} has no `printf 'Review round %s converged -- ...'` comment to check the verdict reader "
             "against".format(BOARD_LOOP))
        return
    fmt = found.group(1).replace("\\n", "\n").replace("%s", "{}")
    run_keys = ("GITHUB_SERVER_URL", "GITHUB_REPOSITORY", "GITHUB_RUN_ID")
    saved = {key: os.environ.get(key) for key in run_keys + ("BOARD_LINE_ID",)}
    rendered = []
    try:
        os.environ.pop("BOARD_LINE_ID", None)
        for run_env in ({}, dict(zip(run_keys, ("https://github.com", "o/r", "1")))):
            for key in run_keys:
                os.environ.pop(key, None)
            os.environ.update(run_env)
            rendered.append(fmt.format(2, 42, head, write_marker("readiness", 2, 42, "fix/12-thing", None,
                                                                   nr_count=0)))
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    sentence = rendered[0].split("\n\n", 1)[0]
    marker = _board_marker({"step": "readiness", "round": 2, "pr": 42})
    quoted = _bot_comment("Triage notes:\n\n> {0}\n\n{1}".format(sentence, marker), 43)
    trailing = _bot_comment("{0}\n\nA later note.\n\n{1}".format(sentence, marker), 44)
    if any(last_converged_review_head(42, [_bot_comment(body, 42)], bot) != head for body in rendered):
        fail("the converged verdict the review job posts (board-loop.yml's printf around write_marker()) "
             "is no longer read as converged")
    elif last_converged_review_head(42, [quoted], bot) is not None:
        fail("a converged verdict quoted inside another loop comment is read as converged")
    elif last_converged_review_head(42, [trailing], bot) is not None:
        fail("a converged verdict followed by other text is read as converged")
    else:
        ok("a review verdict counts as converged only as the review job's whole comment")


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
    check_marker_round_and_verdict()
    check_run_blocks_text_self_test()
    check_structural_self_test()
    check_gh_blocked_reasons()
    check_readiness_stale_claims_self_test()
    check_unscoped_merge_claims_self_test()
    check_unscoped_merge_claims()
    check_handover_claims_self_test()
    check_handover_claims()
    check_board_loop()
    check_readiness_head_binding()
    check_review_head_binding()
    check_pass2_findings()
    check_stalled_tracking_issue()
    check_889_findings()
    check_merged_proof_disposition()
    check_merge_contract_marker_fields()
    check_auto_update()
    print("verify-board-merge: {0} failure(s).".format(failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
