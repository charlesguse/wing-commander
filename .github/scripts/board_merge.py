#!/usr/bin/env python3
"""Board loop self-merge decision (specs/115-board-loop-self-merge,
contracts/board-merge.md, data-model.md "MergeDecision").

WHY THIS EXISTS
---------------
board-loop.yml's `merge` job may squash-merge two classes of PR when
`vars.WING_COMMANDER_BOARD_AUTO_MERGE` is on: the fix PR the loop opened for a
board item, and a verified Spec Kit upgrade PR the auto-update stage opened.
Whether it may is decided HERE, in deterministic code (Principle IX), from a
snapshot of the PR's exact head SHA that the job fetched fresh -- never in
workflow shell and never by an agent. This module is the one home of the
condition names, the class rules and the refusal classifier; the workflow and
the gate (verify-board-merge.py) read them from here.

`evaluate_fix()`/`evaluate_bump()` are the pure decisions, fixturable without a
live `gh` call; `decide()` is the payload wrapper the CLI and the gate share.
`fetch_snapshot()` is the one place the job's snapshot is read from GitHub:
every list a condition reads is fetched whole over REST, with the counts that
prove it whole, and a bump PR's verification run is read beside it, so
`decide()` stays pure.
The fix class reuses board_readiness's `_checks_green`/`_gate_suite_green`, so
an empty rollup is never green (Principle VIII).
"""
import argparse
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from board_item_marker import (BUMP_VERIFICATION_MARKER, is_loop_marker_author,  # noqa: E402
                               last_converged_review_head, last_marker_match, marker_regexes,
                               render_bump_verification)
from board_prove import actions_only  # noqa: E402
from board_readiness import _checks_green, _gate_suite_green  # noqa: E402

CONDITIONS_FIX = ("switch_on", "kill_switch_clear", "snapshot_complete", "eligible_class", "checks_green",
                  "gate_suite_green", "review_converged", "backstop_holds")
CONDITIONS_BUMP = ("switch_on", "kill_switch_clear", "snapshot_complete", "attributed_to_auto_update",
                   "checks_green", "gate_suite_green", "verification_passed_at_head")
REFUSAL_CLASSES = ("workflow-scope", "transient", "conflict", "protection", "other")
# A `transient` failure (the head or base moved under --match-head-commit, a
# 5xx, mergeability still being computed) is not a refusal of this PR: the
# merge job re-derives the decision from a fresh snapshot and tries once more,
# and a second transient failure is announced without a handover, so the item
# is never released as refused for a failure that clears itself.
RETRYABLE_REFUSAL_CLASSES = ("transient",)
OUTCOMES = ("merged", "refused", "transient", "not-merged")

# The `gh pr view --json` fields every snapshot carries (fetch_snapshot(),
# the one fetch for the candidate scan, the fresh fetch and the retry). Its
# files, commits and comments are NOT among them: gh truncates those lists
# (100 files, the last 100 commits), so fetch_snapshot() reads each whole
# over REST, with the pull's own counts beside them (snapshot_complete).
SNAPSHOT_FIELDS = "number,createdAt,headRefOid,statusCheckRollup,author,headRefName,baseRefName,body"
# A `wc-bump-verification` record is built from public values, so anything
# holding the App token could post a byte-exact one. It counts only when the
# Actions API confirms the run it names (#889): a completed, successful
# scheduled or dispatched run of the auto-update wrapper, calling the stage's
# own workflow, that uploaded the artifact naming the verified head -- which
# only that run's own jobs can upload (auto-update-spec-kit.yml "Record the
# verified head on the run").
AUTO_UPDATE_WRAPPER_PATH = ".github/workflows/wing-commander-auto-update-spec-kit.yml"
AUTO_UPDATE_STAGE_PATH = ".github/workflows/auto-update-spec-kit.yml"
AUTO_UPDATE_RUN_EVENTS = ("schedule", "workflow_dispatch")
BUMP_VERIFICATION_ARTIFACT_PREFIX = "wc-bump-verification-"
# Appended to every merge announcement on the PR: which head, which outcome,
# which reason. It is what keeps a repeated outcome from being re-announced
# every hourly run, and what releases a refused bump PR until its head moves.
MERGE_OUTCOME_MARKER = "wc-board-merge-outcome"

CONSTITUTION_PATH = ".specify/memory/constitution.md"
# FR-005: every autonomous merge is a squash commit on main. `gh pr merge`
# merges into whatever base the PR targets now, so a PR retargeted at any
# other branch is in neither class.
BASE_BRANCH = "main"
BUMP_BRANCH_RE = re.compile(r"auto-update-spec-kit/v\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?")
# The body the auto-update act job writes (auto-update-spec-kit.yml "Open
# version-bump PR"): its hidden marker and the `Closes #N` that links the
# `auto-update:tracking` lifecycle issue the announcement is also posted on.
BUMP_BODY_MARKER = "<!-- wing-commander-auto-update-spec-kit: version-bump -->"
BUMP_ISSUE_RE = re.compile(r"^Closes #(\d+)\s*$", re.MULTILINE)
FIX_BRANCH_RE = re.compile(r"fix/\d+-[a-z0-9-]{1,40}")
# A spec, plan or lifecycle (final implementation) PR is never a candidate
# (FR-012); the fix-branch shape already excludes them, this names the reason.
NON_CANDIDATE_BRANCH_PREFIXES = ("spec/", "plan/", "lifecycle/")


def _slug(login):
    """`app/<slug>`, `<slug>[bot]` and `<slug>` name the same App across the
    REST and `gh pr view` shapes."""
    login = (login or "").strip()
    if login.startswith("app/"):
        login = login[len("app/"):]
    if login.endswith("[bot]"):
        login = login[:-len("[bot]")]
    return login.lower()


def _is_bot(login, bot_login):
    return bool(bot_login) and _slug(login) == _slug(bot_login)


def _bot_pr_author(pr, bot_login):
    """A `gh pr view`/`gh pr list` author is the App only when GitHub says it
    is a bot account: a user whose login equals the App slug is not."""
    author = (pr or {}).get("author") or {}
    return author.get("is_bot") is True and _is_bot(author.get("login"), bot_login)


def _is_app_user(user, bot_login):
    """A REST `user`/commit `author` object is the App: the one predicate
    (board_item_marker.is_loop_marker_author), type Bot and the exact login."""
    return is_loop_marker_author({"user": user or {}}, bot_login)


def snapshot_complete(snapshot):
    """#889: every list a condition reads is whole. fetch_snapshot() records
    the pull's own `changed_files`, `commits` and `comments` counts and its
    head; a list shorter than its count (REST stops at 3000 files and 250
    commits), a missing count, or lists read at another head is not a
    snapshot any condition may be decided from. A comment posted after the
    count was read only lengthens its list."""
    counts = snapshot.get("counts")
    head = snapshot.get("headRefOid")
    if not isinstance(counts, dict) or not head or counts.get("head_sha") != head:
        return False
    lists = {name: snapshot.get(name) for name in ("files", "commits", "comments")}
    if not all(isinstance(value, list) for value in lists.values()):
        return False
    if not all(isinstance(counts.get(name), int) for name in lists):
        return False
    if len(lists["files"]) != counts["files"] or len(lists["commits"]) != counts["commits"]:
        return False
    if len(lists["comments"]) < counts["comments"]:
        return False
    return any((c or {}).get("sha") == head for c in lists["commits"])


def _targets_main(snapshot):
    return snapshot.get("baseRefName") == BASE_BRANCH


def _touches_constitution(snapshot):
    return any((f or {}).get("path") == CONSTITUTION_PATH for f in snapshot.get("files") or [])


def _decision(snapshot, klass, names, results):
    conditions = {name: bool(results[name]) for name in names}
    unmet = next((name for name in names if not conditions[name]), None)
    return {"head_sha": snapshot.get("headRefOid"), "class": klass,
            "may_merge": unmet is None, "unmet_reason": unmet, "conditions": conditions}


def eligible_fix_class(snapshot, bot_login):
    """FR-001/FR-012: a fix PR is one the loop opened -- its App is the PR's
    author (a branch name anyone can push or fork under is not enough) -- on
    the loop's own `fix/<issue>-<slug>` branch; never a spec, plan or
    lifecycle PR, never one touching the constitution, and only into main."""
    if not _targets_main(snapshot):
        return False
    if not _bot_pr_author(snapshot, bot_login):
        return False
    branch = snapshot.get("headRefName") or ""
    if branch.startswith(NON_CANDIDATE_BRANCH_PREFIXES):
        return False
    if FIX_BRANCH_RE.fullmatch(branch) is None:
        return False
    return not _touches_constitution(snapshot)


def evaluate_fix(snapshot, review_converged, backstop_holds, paused, switch_on, bot_login):
    rollup = snapshot.get("statusCheckRollup") or []
    checks_green = _checks_green(rollup)
    results = {
        "switch_on": switch_on,
        "kill_switch_clear": not paused,
        "snapshot_complete": snapshot_complete(snapshot),
        "eligible_class": eligible_fix_class(snapshot, bot_login),
        "checks_green": checks_green,
        "gate_suite_green": checks_green and _gate_suite_green(rollup),
        "review_converged": review_converged,
        "backstop_holds": backstop_holds,
    }
    return _decision(snapshot, "fix", CONDITIONS_FIX, results)


def _bot_commit(commit, bot_login):
    """#889: a commit is the App's only when GitHub resolved its author to the
    App's own account (REST `author`: type Bot, the App's login). A git email
    is self-asserted -- anyone can commit as `<slug>[bot]@users.noreply...`
    -- so a commit GitHub resolved to no account is never the bot's. The
    stage's `<slug>[bot]` noreply email resolves to the App."""
    return _is_app_user((commit or {}).get("author"), bot_login)


def _attributed_to_auto_update(snapshot, bot_login):
    """Research D4: bot author, the stage's branch shape, the tracking marker
    in the body, every commit bot-authored, no constitution change, and
    only into main (FR-005)."""
    if not _targets_main(snapshot):
        return False
    if not _bot_pr_author(snapshot, bot_login):
        return False
    if BUMP_BRANCH_RE.fullmatch(snapshot.get("headRefName") or "") is None:
        return False
    body = snapshot.get("body") or ""
    if BUMP_BODY_MARKER not in body or BUMP_ISSUE_RE.search(body) is None:
        return False
    commits = snapshot.get("commits") or []
    if not commits:
        return False
    if not all(_bot_commit(commit, bot_login) for commit in commits):
        return False
    return not _touches_constitution(snapshot)


def _comment_order(comment):
    """(created_at, comment id): created_at has one-second resolution, so two
    records posted in the same second are ordered by the numeric id GitHub
    assigns, never by list position."""
    comment = comment or {}
    cid = comment.get("id")
    return (comment.get("created_at") or "", cid if isinstance(cid, int) else 0)


def _bot_marker_records(comments, bot_login, name, whole_body=None):
    """(order, record) for each `name` marker in a comment the App posted.
    `comments` are REST issue comments (fetch_snapshot()): a comment counts
    only when its `user` is the App's account (type Bot), so a user whose
    login equals the App slug is ignored (a record is a trust surface: only
    the App's own counts). With `whole_body`, a record counts only when the
    comment is exactly `whole_body(record)` and nothing else."""
    marker_re, open_re = marker_regexes(name)
    found = []
    for comment in comments or []:
        if not is_loop_marker_author(comment or {}, bot_login):
            continue
        body = comment.get("body") or ""
        match = last_marker_match(body, marker_re, open_re)
        if not match:
            continue
        try:
            record = json.loads(match.group(1))
        except ValueError:
            continue
        if not isinstance(record, dict):
            continue
        if whole_body is not None and body.replace("\r\n", "\n").strip() != whole_body(record):
            continue
        found.append((_comment_order(comment), record))
    found.sort(key=lambda pair: pair[0])
    return found


def _rendered_bump_verification(record):
    return render_bump_verification(record.get("head_sha"), record.get("tier"), record.get("result"),
                                    record.get("run_id"))


def bump_records(comments, bot_login):
    """The `wc-bump-verification` records in bot-authored PR comments, oldest
    first. A record counts only as the whole comment the auto-update stage
    posts, byte for byte what render_bump_verification() writes. Other App
    comments quote untrusted text (issue bodies, stderr), and a marker quoted
    inside one would otherwise read as a pass the stage never recorded."""
    return [record for _order, record in _bot_marker_records(comments, bot_login, BUMP_VERIFICATION_MARKER,
                                                             _rendered_bump_verification)]


def latest_record_at_head(records, head_sha):
    """The latest of the records bound to `head_sha`, or None. A record for
    any other head says nothing about this one, so a late record for an old
    head never voids a valid one for this head; among this head's own records
    the latest wins, so a failed re-run does void an earlier pass."""
    at_head = [record for record in records or [] if head_sha and record.get("head_sha") == head_sha]
    return at_head[-1] if at_head else None


def verification_run_confirms(record, run, head_sha):
    """#889 (the owner's choice: bind the record to its run): `run` is what
    fetch_snapshot() read from the Actions API for the record's `run_id`
    (None when it could not be read). It confirms the record only as a
    completed, successful scheduled or dispatched run of the auto-update
    wrapper, calling the stage's own workflow, that uploaded the artifact
    naming `head_sha`. Anything unconfirmed fails closed."""
    if not isinstance(record, dict) or not isinstance(run, dict) or not head_sha:
        return False
    if not str(record.get("run_id") or "").isdigit() or str(run.get("id")) != str(record.get("run_id")):
        return False
    if run.get("path") != AUTO_UPDATE_WRAPPER_PATH or run.get("event") not in AUTO_UPDATE_RUN_EVENTS:
        return False
    if run.get("status") != "completed" or run.get("conclusion") != "success":
        return False
    called = [str(path).split("@", 1)[0] for path in run.get("referenced_workflows") or []]
    if not any(path.endswith("/" + AUTO_UPDATE_STAGE_PATH) for path in called):
        return False
    return BUMP_VERIFICATION_ARTIFACT_PREFIX + head_sha in (run.get("artifacts") or [])


def verification_passed_at_head(records, head_sha, run=None):
    """The latest record bound to `head_sha` passed, and the Actions API
    confirms the run it names (verification_run_confirms)."""
    record = latest_record_at_head(records, head_sha)
    return (record is not None and record.get("result") == "passed"
            and verification_run_confirms(record, run, head_sha))


def evaluate_bump(snapshot, records, bot_login, paused, switch_on):
    """No size backstop: the verification gates the merge (Principle X).
    The verification run is the snapshot's `verificationRun`, which
    fetch_snapshot() read for the latest record at the head."""
    rollup = snapshot.get("statusCheckRollup") or []
    checks_green = _checks_green(rollup)
    results = {
        "switch_on": switch_on,
        "kill_switch_clear": not paused,
        "snapshot_complete": snapshot_complete(snapshot),
        "attributed_to_auto_update": _attributed_to_auto_update(snapshot, bot_login),
        "checks_green": checks_green,
        "gate_suite_green": checks_green and _gate_suite_green(rollup),
        "verification_passed_at_head": verification_passed_at_head(records, snapshot.get("headRefOid"),
                                                                    snapshot.get("verificationRun")),
    }
    return _decision(snapshot, "bump", CONDITIONS_BUMP, results)


# Checked in this order: a missing scope is never mistaken for a transient
# failure, and a transient one is checked before `not mergeable`, which
# GitHub also says while mergeability is still being computed. gh refuses a
# known conflict itself ("Pull request #N is not mergeable: <reason>"), so
# the API's bare "Pull Request is not mergeable" reaches stderr only when gh
# saw no blocked state, i.e. mergeability was still unknown: it is
# transient, and the retry's gh pre-check names a real conflict by its
# reason. Protection is checked before conflict: gh's own pre-merge refusal
# reads "is not mergeable: <reason>" for a policy block and an out-of-date
# head too, so the reason, not the prefix, names the class.
_REFUSAL_PATTERNS = (
    ("workflow-scope", re.compile(r"workflows?`?\s+(permission|scope)|without\s+`?workflows?`?|"
                                  r"workflow\s+scope", re.IGNORECASE)),
    ("transient", re.compile(r"(head|base) branch was modified|try the merge again|"
                             r"HTTP 5\d\d|bad gateway|service unavailable|gateway time-?out|"
                             r"timed out|connection reset|mergeab\w+ (state )?(is )?(still )?"
                             r"(unknown|being computed)|pull request is not mergeable|"
                             r"merge already in progress", re.IGNORECASE)),
    ("protection", re.compile(r"protected branch|required status|required review|review is required|"
                              r"approving review|branch protection|base branch policy|"
                              r"repository rule|not up to date with the base", re.IGNORECASE)),
    ("conflict", re.compile(r"not mergeable|merge conflict|conflicts? with|cannot be cleanly created",
                            re.IGNORECASE)),
)


def classify_refusal(stderr):
    """The refusal class of `gh pr merge`'s stderr; `other` when none match."""
    for name, pattern in _REFUSAL_PATTERNS:
        if pattern.search(stderr or ""):
            return name
    return "other"


def decide(payload):
    """payload: {"class": "fix"|"bump", "snapshot": fetch_snapshot() JSON,
    "switch_on", "paused", and for fix "review_converged", "backstop_holds",
    "readiness_head_sha", "issue_comments"; "bot_login" for both}. A fix
    backstop measured on a head other than the snapshot's is not a backstop
    that holds. Nor is readiness's "ready" a converged review unless the
    issue's newest review verdict, read fresh by the merge job, converged on
    the snapshot's head (FR-003): readiness resumed from an earlier run's
    marker never re-checks that the review saw this head."""
    snapshot = payload["snapshot"]
    bot_login = payload.get("bot_login") or ""
    if payload["class"] == "fix":
        head = snapshot.get("headRefOid")
        backstop = bool(payload.get("backstop_holds")) and payload.get("readiness_head_sha") == head
        review = bool(payload.get("review_converged")) and bool(head) and last_converged_review_head(
            snapshot.get("number"), payload.get("issue_comments"), bot_login) == head
        return evaluate_fix(snapshot, review, backstop,
                            bool(payload["paused"]), bool(payload["switch_on"]), bot_login)
    return evaluate_bump(snapshot, bump_records(snapshot.get("comments"), bot_login), bot_login,
                         bool(payload["paused"]), bool(payload["switch_on"]))


def merged_by_us(pr, bot_login, head_sha):
    """`pr` is `gh pr view --json mergedBy,headRefOid` of a MERGED PR: this
    App merged it, at `head_sha`. Anyone else's merge, or one at another
    head, is not this run's merge to announce."""
    pr = pr or {}
    return (bool(head_sha) and pr.get("headRefOid") == head_sha
            and _is_bot((pr.get("mergedBy") or {}).get("login"), bot_login))


def _not_merged_reason(decision):
    """The unmet condition; a decision that allowed the merge but whose PR
    was merged by someone else, or at another head, has none, so it is named."""
    return decision.get("unmet_reason") or "merged_elsewhere"


def outcome_record(decision, outcome, refusal_class=None):
    """The MERGE_OUTCOME_MARKER payload for one announcement."""
    reason = refusal_class if outcome in ("refused", "transient") else (
        _not_merged_reason(decision) if outcome == "not-merged" else None)
    return {"head_sha": decision.get("head_sha"), "class": decision.get("class"),
            "outcome": outcome, "reason": reason}


def _outcome_records(snapshot, bot_login):
    return [record for _order, record in
            _bot_marker_records((snapshot or {}).get("comments"), bot_login, MERGE_OUTCOME_MARKER)]


def already_announced(snapshot, bot_login, record):
    """The App already posted this exact outcome (head, outcome, reason) on
    the PR, so posting it again would only repeat it every hourly run."""
    return any(previous == record for previous in _outcome_records(snapshot, bot_login))


def handed_over_at_head(snapshot, bot_login):
    """GitHub refused this PR at its current head and the App handed it to a
    maintainer. It is released until its head moves (FR-010): a new push is a
    new candidate, the same head is never re-attempted."""
    head = (snapshot or {}).get("headRefOid")
    return bool(head) and any(record.get("outcome") == "refused" and record.get("head_sha") == head
                              for record in _outcome_records(snapshot, bot_login))


def _defang(text):
    """Quoted text (GitHub's stderr, a path) can never carry a marker into
    the App's own comment, where a reader would trust it."""
    return (text or "").replace("<!--", "<\u200b!--")


def _unfence(text):
    """Quoted stderr goes inside a ``` fence, so a ``` of its own must not
    close it."""
    return (text or "").replace("```", "``\u200b`")


def prove_disposition(snapshot):
    """What follows a merge, in the words of the announcement. The classifier
    is board_prove.actions_only() -- the one prove-gate/prove use -- never a
    second rule here (research D8)."""
    paths = [(f or {}).get("path") for f in snapshot.get("files") or [] if (f or {}).get("path")]
    only, reason = actions_only(paths)
    if only:
        return "a proof re-drive follows the merge ({0})".format(reason)
    return "no proof re-drive is needed ({0})".format(reason)


def render_announcement(decision, outcome, snapshot=None, merge_sha=None, refusal_class=None, stderr=None):
    """The PR/issue comment for a MergeOutcome (contracts/board-merge.md
    "Announcement"): merged, refused, transient or not-merged, ending with
    its MERGE_OUTCOME_MARKER."""
    head = decision.get("head_sha")
    klass = decision.get("class")
    results = ", ".join("{0}={1}".format(name, "pass" if ok else "FAIL")
                        for name, ok in (decision.get("conditions") or {}).items())
    quoted = _unfence((stderr or "").strip())
    if outcome == "merged":
        text = ("Merged ({0} class) at head_sha {1}; squash commit {2}.\n\nConditions: {3}.\n\n"
                "Proof: {4}.".format(klass, head, merge_sha or "(not yet reported by GitHub)", results,
                                     prove_disposition(snapshot or {})))
    elif outcome == "refused":
        text = ("GitHub refused the merge of head_sha {0} ({1} class), refusal_class {2}:\n\n```\n{3}\n```\n\n"
                "Nothing reached main by another route; handed to a maintainer.".format(
                    head, klass, refusal_class, quoted))
    elif outcome == "transient":
        after = ("the readiness report's hand-off stands, so a maintainer may merge it"
                 if klass == "fix" else "the next board-loop run re-evaluates it from a fresh snapshot")
        text = ("The merge of head_sha {0} ({1} class) failed transiently twice, refusal_class {2}:\n\n"
                "```\n{3}\n```\n\nNothing reached main. Not handed over as refused: {4}.".format(
                    head, klass, refusal_class, quoted, after))
    elif _not_merged_reason(decision) == "merged_elsewhere":
        text = ("Merged elsewhere (`merged_elsewhere`): this PR ({0} class) was merged, but not by the board "
                "loop at head_sha {1}, so this run announces no merge of its own.\n\nConditions: {2}.".format(
                    klass, head, results))
    else:
        text = ("Not merged ({0} class) at head_sha {1}: unmet condition `{2}`.\n\nConditions: {3}.".format(
            klass, head, _not_merged_reason(decision), results))
    record = json.dumps(outcome_record(decision, outcome, refusal_class), sort_keys=True)
    return "{0}\n\n<!-- {1}: {2} -->".format(_defang(text), MERGE_OUTCOME_MARKER, record)


def bump_tracking_issue(body):
    """The `auto-update:tracking` issue number a bump PR's body closes, or ''."""
    match = BUMP_ISSUE_RE.search(body or "")
    return match.group(1) if match else ""


def bump_shaped(prs, bot_login):
    """The open PRs with the auto-update shape (bot author and branch, research
    D5), oldest first. `prs` is `gh pr list --json
    number,author,headRefName,createdAt`."""
    matching = [pr for pr in prs or []
                if _bot_pr_author(pr, bot_login)
                and BUMP_BRANCH_RE.fullmatch(pr.get("headRefName") or "")]
    matching.sort(key=lambda pr: pr.get("createdAt") or "")
    return [pr["number"] for pr in matching]


def pick_bump_candidate(snapshots, bot_login, stalled_issues=()):
    """Research D5: the one bump PR this run evaluates, from a snapshot of
    every auto-update-shaped PR. A PR handed over at its current head, with
    no tracking issue to announce on, or whose tracking issue is in
    `stalled_issues` (it carries `board:stalled`, as a maintainer `/stop`
    there leaves it; removing the label releases it, as for a fix item) is
    skipped; of the rest the oldest that may merge wins, else the oldest
    (its unmet condition is announced once). So one stuck PR never hides a newer verified one. The switches
    are the same for every candidate, so they are taken as on here; decide()
    re-derives everything from the merge job's own fresh fetch."""
    # '' (no tracking issue) is skipped like a stalled one.
    skipped_issues = {""} | {str(n) for n in stalled_issues or ()}
    usable = [snap for snap in snapshots or []
              if _bot_pr_author(snap, bot_login)
              and BUMP_BRANCH_RE.fullmatch(snap.get("headRefName") or "")
              and bump_tracking_issue(snap.get("body")) not in skipped_issues
              and not handed_over_at_head(snap, bot_login)]
    usable.sort(key=lambda snap: snap.get("createdAt") or "")
    if not usable:
        return None
    mergeable = [snap for snap in usable
                 if decide({"class": "bump", "snapshot": snap, "bot_login": bot_login,
                            "paused": False, "switch_on": True})["may_merge"]]
    chosen = (mergeable or usable)[0]
    return {"pr": chosen.get("number"), "issue": bump_tracking_issue(chosen.get("body"))}


def _gh(args, token=None):
    env = dict(os.environ)
    if token:
        env["GH_TOKEN"] = token
    return subprocess.run(["gh"] + list(args), capture_output=True, text=True, check=True, env=env).stdout


def _gh_items(path, token=None, items=".[]"):
    """Every item of a paginated REST list (`items` picks it out of each
    page), read as one compact JSON object a line."""
    out = _gh(["api", path, "--paginate", "--jq", items + " | tojson"], token)
    return [json.loads(line) for line in out.splitlines() if line.strip()]


def _fetch_verification_run(repo, record, token):
    """The Actions API's facts for the run a record names, or None when it
    cannot be read (verification_run_confirms() then fails closed)."""
    run_id = str((record or {}).get("run_id") or "")
    if not run_id.isdigit():
        return None
    try:
        run = json.loads(_gh(["api", "repos/{0}/actions/runs/{1}".format(repo, run_id)], token))
        artifacts = _gh_items("repos/{0}/actions/runs/{1}/artifacts?per_page=100".format(repo, run_id), token,
                              ".artifacts[]")
    except (subprocess.CalledProcessError, ValueError):
        return None
    return {"id": run.get("id"), "path": run.get("path"), "event": run.get("event"),
            "status": run.get("status"), "conclusion": run.get("conclusion"),
            "referenced_workflows": [(w or {}).get("path") for w in run.get("referenced_workflows") or []],
            "artifacts": [(a or {}).get("name") for a in artifacts]}


def fetch_snapshot(repo, pr, bot_login, actions_token=None):
    """The snapshot every decision reads (#889): `gh pr view` for the head,
    the checks and the author, then the pull's counts, and its files,
    commits and issue comments, each whole over REST (snapshot_complete()
    compares them). For a PR on the auto-update branch, the run its latest
    record at the head names, read with `actions_token`. Raises on any
    failed read but the run's, which only leaves `verificationRun` empty."""
    snapshot = json.loads(_gh(["pr", "view", str(pr), "-R", repo, "--json", SNAPSHOT_FIELDS]))
    pull = json.loads(_gh(["api", "repos/{0}/pulls/{1}".format(repo, pr)]))
    snapshot["counts"] = {"files": pull.get("changed_files"), "commits": pull.get("commits"),
                          "comments": pull.get("comments"), "head_sha": (pull.get("head") or {}).get("sha")}
    snapshot["files"] = [{"path": f.get("filename")}
                         for f in _gh_items("repos/{0}/pulls/{1}/files?per_page=100".format(repo, pr))]
    snapshot["commits"] = [{"sha": c.get("sha"),
                            "author": ({"login": c["author"].get("login"), "type": c["author"].get("type")}
                                       if c.get("author") else None)}
                           for c in _gh_items("repos/{0}/pulls/{1}/commits?per_page=100".format(repo, pr))]
    snapshot["comments"] = [{"id": c.get("id"), "created_at": c.get("created_at"), "body": c.get("body"),
                             "user": {"login": (c.get("user") or {}).get("login"),
                                      "type": (c.get("user") or {}).get("type")}}
                            for c in _gh_items("repos/{0}/issues/{1}/comments?per_page=100".format(repo, pr))]
    snapshot["verificationRun"] = None
    if BUMP_BRANCH_RE.fullmatch(snapshot.get("headRefName") or ""):
        record = latest_record_at_head(bump_records(snapshot["comments"], bot_login), snapshot.get("headRefOid"))
        if record is not None:
            snapshot["verificationRun"] = _fetch_verification_run(repo, record, actions_token)
    return snapshot


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    decide_cmd = sub.add_parser("decide", help="inputs JSON + snapshot JSON -> MergeDecision JSON on stdout")
    decide_cmd.add_argument("--inputs", required=True, help="the payload without its snapshot (JSON file)")
    decide_cmd.add_argument("--snapshot", required=True, help="gh pr view JSON file")
    decide_cmd.add_argument("--issue-comments", default=None,
                            help="the fix issue's REST comments array (JSON file)")

    def _decide(a):
        with open(a.inputs, encoding="utf-8") as fh:
            payload = json.load(fh)
        with open(a.snapshot, encoding="utf-8") as fh:
            payload["snapshot"] = json.load(fh)
        if a.issue_comments:
            with open(a.issue_comments, encoding="utf-8") as fh:
                payload["issue_comments"] = json.load(fh)
        print(json.dumps(decide(payload)))
    decide_cmd.set_defaults(func=_decide)
    snapshot_cmd = sub.add_parser("snapshot", help="fetch one PR's whole snapshot -> JSON on stdout "
                                                   "(exit 1 when any part of it could not be read)")
    snapshot_cmd.add_argument("--repo", required=True)
    snapshot_cmd.add_argument("--pr", required=True)
    snapshot_cmd.add_argument("--bot-login", required=True)

    def _snapshot(a):
        try:
            snap = fetch_snapshot(a.repo, a.pr, a.bot_login, os.environ.get("WC_ACTIONS_TOKEN") or None)
        except (subprocess.CalledProcessError, ValueError) as exc:
            print("board_merge.py snapshot: could not read PR #{0}: {1}".format(
                a.pr, getattr(exc, "stderr", None) or exc), file=sys.stderr)
            sys.exit(1)
        print(json.dumps(snap))
    snapshot_cmd.set_defaults(func=_snapshot)
    refusal_cmd = sub.add_parser("classify-refusal", help="stderr on stdin -> refusal class")
    refusal_cmd.set_defaults(func=lambda _a: print(classify_refusal(sys.stdin.read())))
    retry_cmd = sub.add_parser("retryable", help="exit 0 when the refusal class is retried once")
    retry_cmd.add_argument("refusal_class")
    retry_cmd.set_defaults(func=lambda a: sys.exit(0 if a.refusal_class in RETRYABLE_REFUSAL_CLASSES else 1))
    announce_cmd = sub.add_parser("announce", help="render the comment for a merge outcome; "
                                                   "prints nothing when the PR already carries it")
    announce_cmd.add_argument("--decision", required=True, help="decision JSON file")
    announce_cmd.add_argument("--snapshot", required=True, help="gh pr view JSON file")
    announce_cmd.add_argument("--outcome", required=True, choices=OUTCOMES)
    announce_cmd.add_argument("--bot-login", required=True)
    announce_cmd.add_argument("--merge-sha", default=None)
    announce_cmd.add_argument("--refusal-class", default=None)
    announce_cmd.add_argument("--stderr-file", default=None)

    def _announce(a):
        with open(a.decision, encoding="utf-8") as fh:
            decision = json.load(fh)
        with open(a.snapshot, encoding="utf-8") as fh:
            snapshot = json.load(fh)
        if already_announced(snapshot, a.bot_login, outcome_record(decision, a.outcome, a.refusal_class)):
            return
        err = None
        if a.stderr_file:
            with open(a.stderr_file, encoding="utf-8") as fh:
                err = fh.read()
        print(render_announcement(decision, a.outcome, snapshot, a.merge_sha, a.refusal_class, err))
    announce_cmd.set_defaults(func=_announce)
    merged_by_cmd = sub.add_parser("merged-by-us", help="gh pr view --json mergedBy,headRefOid on stdin -> "
                                                        "exit 0 when this App merged it at --head-sha")
    merged_by_cmd.add_argument("--bot-login", required=True)
    merged_by_cmd.add_argument("--head-sha", required=True)

    def _merged_by(a):
        try:
            pr = json.load(sys.stdin)
        except ValueError:
            sys.exit(1)
        sys.exit(0 if isinstance(pr, dict) and merged_by_us(pr, a.bot_login, a.head_sha) else 1)
    merged_by_cmd.set_defaults(func=_merged_by)
    shaped_cmd = sub.add_parser("bump-shaped", help="gh pr list JSON on stdin -> auto-update-shaped PR numbers")
    shaped_cmd.add_argument("--bot-login", required=True)
    shaped_cmd.set_defaults(func=lambda a: print(" ".join(str(n) for n in bump_shaped(json.load(sys.stdin),
                                                                                       a.bot_login))))
    bump_cmd = sub.add_parser("pick-bump", help="JSON array of snapshots on stdin -> "
                                                "{pr, issue} JSON or nothing")
    bump_cmd.add_argument("--bot-login", required=True)
    bump_cmd.add_argument("--stalled-issues", default="",
                          help="space-separated numbers of the open issues carrying board:stalled")

    def _pick(a):
        picked = pick_bump_candidate(json.load(sys.stdin), a.bot_login, a.stalled_issues.split())
        if picked:
            print(json.dumps(picked))
    bump_cmd.set_defaults(func=_pick)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
