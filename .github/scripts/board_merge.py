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
The fix class reuses board_readiness's `_checks_green`/`_gate_suite_green`, so
an empty rollup is never green (Principle VIII).
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from board_item_marker import (BUMP_VERIFICATION_MARKER, last_marker_match, marker_regexes,  # noqa: E402
                               render_bump_verification)
from board_prove import actions_only  # noqa: E402
from board_readiness import _checks_green, _gate_suite_green  # noqa: E402

CONDITIONS_FIX = ("switch_on", "kill_switch_clear", "eligible_class", "checks_green",
                  "gate_suite_green", "review_converged", "backstop_holds")
CONDITIONS_BUMP = ("switch_on", "kill_switch_clear", "attributed_to_auto_update", "checks_green",
                   "gate_suite_green", "verification_passed_at_head")
REFUSAL_CLASSES = ("workflow-scope", "transient", "conflict", "protection", "other")
# A `transient` failure (the head or base moved under --match-head-commit, a
# 5xx, mergeability still being computed) is not a refusal of this PR: the
# merge job re-derives the decision from a fresh snapshot and tries once more,
# and a second transient failure is announced without a handover, so the item
# is never released as refused for a failure that clears itself.
RETRYABLE_REFUSAL_CLASSES = ("transient",)
OUTCOMES = ("merged", "refused", "transient", "not-merged")

# The `gh pr view --json` fields every snapshot carries: one list for the
# candidate scan and the fresh fetch, so both hold the same shape.
SNAPSHOT_FIELDS = ("number,createdAt,headRefOid,statusCheckRollup,author,headRefName,"
                   "commits,files,comments,body")
# Appended to every merge announcement on the PR: which head, which outcome,
# which reason. It is what keeps a repeated outcome from being re-announced
# every hourly run, and what releases a refused bump PR until its head moves.
MERGE_OUTCOME_MARKER = "wc-board-merge-outcome"

CONSTITUTION_PATH = ".specify/memory/constitution.md"
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


def _touches_constitution(snapshot):
    return any((f or {}).get("path") == CONSTITUTION_PATH for f in snapshot.get("files") or [])


def _decision(snapshot, klass, names, results):
    conditions = {name: bool(results[name]) for name in names}
    unmet = next((name for name in names if not conditions[name]), None)
    return {"head_sha": snapshot.get("headRefOid"), "class": klass,
            "may_merge": unmet is None, "unmet_reason": unmet, "conditions": conditions}


def eligible_fix_class(snapshot):
    """FR-012: a fix PR is the loop's own `fix/<issue>-<slug>` branch; never a
    spec, plan or lifecycle PR, and never one touching the constitution."""
    branch = snapshot.get("headRefName") or ""
    if branch.startswith(NON_CANDIDATE_BRANCH_PREFIXES):
        return False
    if FIX_BRANCH_RE.fullmatch(branch) is None:
        return False
    return not _touches_constitution(snapshot)


def evaluate_fix(snapshot, review_converged, backstop_holds, paused, switch_on):
    rollup = snapshot.get("statusCheckRollup") or []
    checks_green = _checks_green(rollup)
    results = {
        "switch_on": switch_on,
        "kill_switch_clear": not paused,
        "eligible_class": eligible_fix_class(snapshot),
        "checks_green": checks_green,
        "gate_suite_green": checks_green and _gate_suite_green(rollup),
        "review_converged": review_converged,
        "backstop_holds": backstop_holds,
    }
    return _decision(snapshot, "fix", CONDITIONS_FIX, results)


def _bot_commit_author(author, bot_login):
    """`gh` reports an empty login for a commit whose git email maps to no
    GitHub account. The App's own commits then still carry its noreply email,
    either `<slug>[bot]@users.noreply.github.com` (what the auto-update stage
    configures) or `<id>+<slug>[bot]@users.noreply.github.com`, which only that
    App can author; any other empty-login commit is not the bot's."""
    author = author or {}
    if (author.get("login") or "").strip():
        return _is_bot(author.get("login"), bot_login)
    email = (author.get("email") or "").strip().lower()
    slug = _slug(bot_login)
    if not slug:
        return False
    suffix = "{0}[bot]@users.noreply.github.com".format(slug)
    return email == suffix or (email.endswith("+" + suffix) and email[:-len(suffix) - 1].isdigit())


def _attributed_to_auto_update(snapshot, bot_login):
    """Research D4: bot author, the stage's branch shape, the tracking marker
    in the body, every commit bot-authored, and no constitution change."""
    if not _is_bot((snapshot.get("author") or {}).get("login"), bot_login):
        return False
    if BUMP_BRANCH_RE.fullmatch(snapshot.get("headRefName") or "") is None:
        return False
    body = snapshot.get("body") or ""
    if BUMP_BODY_MARKER not in body or BUMP_ISSUE_RE.search(body) is None:
        return False
    commits = snapshot.get("commits") or []
    if not commits:
        return False
    for commit in commits:
        authors = (commit or {}).get("authors") or []
        if not authors or not all(_bot_commit_author(a, bot_login) for a in authors):
            return False
    return not _touches_constitution(snapshot)


def _comment_order(comment):
    """(createdAt, comment id): createdAt has one-second resolution, so two
    records posted in the same second are ordered by the numeric id GitHub
    assigns (the `issuecomment-<id>` in the comment's url), never by list
    position."""
    match = re.search(r"issuecomment-(\d+)", (comment or {}).get("url") or "")
    return ((comment or {}).get("createdAt") or "", int(match.group(1)) if match else 0)


def _bot_marker_records(comments, bot_login, name, whole_body=None):
    """(order, record) for each `name` marker in a bot-authored comment. A
    marker in any other login's comment is ignored (a record is a trust
    surface: only the App's own counts). With `whole_body`, a record counts
    only when the comment is exactly `whole_body(record)` and nothing else."""
    marker_re, open_re = marker_regexes(name)
    found = []
    for comment in comments or []:
        if not _is_bot(((comment or {}).get("author") or {}).get("login"), bot_login):
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


def verification_passed_at_head(records, head_sha):
    """The latest of the records bound to `head_sha` passed. A record for any
    other head says nothing about this one, so a late record for an old head
    never voids a valid one for this head; among this head's own records the
    latest wins, so a failed re-run does void an earlier pass."""
    at_head = [record for record in records or [] if head_sha and record.get("head_sha") == head_sha]
    return bool(at_head) and at_head[-1].get("result") == "passed"


def evaluate_bump(snapshot, records, bot_login, paused, switch_on):
    """No size backstop: the verification gates the merge (Principle X)."""
    rollup = snapshot.get("statusCheckRollup") or []
    checks_green = _checks_green(rollup)
    results = {
        "switch_on": switch_on,
        "kill_switch_clear": not paused,
        "attributed_to_auto_update": _attributed_to_auto_update(snapshot, bot_login),
        "checks_green": checks_green,
        "gate_suite_green": checks_green and _gate_suite_green(rollup),
        "verification_passed_at_head": verification_passed_at_head(records, snapshot.get("headRefOid")),
    }
    return _decision(snapshot, "bump", CONDITIONS_BUMP, results)


# Checked in this order: a missing scope is never mistaken for a transient
# failure, and a transient one is checked before `not mergeable`, which
# GitHub also says while mergeability is still being computed.
_REFUSAL_PATTERNS = (
    ("workflow-scope", re.compile(r"workflows?`?\s+(permission|scope)|without\s+`?workflows?`?|"
                                  r"workflow\s+scope", re.IGNORECASE)),
    ("transient", re.compile(r"(head|base) branch was modified|try the merge again|"
                             r"HTTP 5\d\d|bad gateway|service unavailable|gateway time-?out|"
                             r"timed out|connection reset|mergeab\w+ (state )?(is )?(still )?"
                             r"(unknown|being computed)|merge already in progress", re.IGNORECASE)),
    ("conflict", re.compile(r"not mergeable|merge conflict|conflicts? with|cannot be cleanly created",
                            re.IGNORECASE)),
    ("protection", re.compile(r"protected branch|required status|required review|review is required|"
                              r"approving review|branch protection|base branch policy|"
                              r"repository rule", re.IGNORECASE)),
)


def classify_refusal(stderr):
    """The refusal class of `gh pr merge`'s stderr; `other` when none match."""
    for name, pattern in _REFUSAL_PATTERNS:
        if pattern.search(stderr or ""):
            return name
    return "other"


def decide(payload):
    """payload: {"class": "fix"|"bump", "snapshot": gh pr view JSON,
    "switch_on", "paused", and for fix "review_converged", "backstop_holds",
    "readiness_head_sha"; for bump "bot_login"}. A fix backstop measured on a
    head other than the snapshot's is not a backstop that holds."""
    snapshot = payload["snapshot"]
    if payload["class"] == "fix":
        backstop = bool(payload.get("backstop_holds")) and (
            payload.get("readiness_head_sha") == snapshot.get("headRefOid"))
        return evaluate_fix(snapshot, bool(payload.get("review_converged")), backstop,
                            bool(payload["paused"]), bool(payload["switch_on"]))
    bot_login = payload.get("bot_login") or ""
    return evaluate_bump(snapshot, bump_records(snapshot.get("comments"), bot_login), bot_login,
                         bool(payload["paused"]), bool(payload["switch_on"]))


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
                if _is_bot((pr.get("author") or {}).get("login"), bot_login)
                and BUMP_BRANCH_RE.fullmatch(pr.get("headRefName") or "")]
    matching.sort(key=lambda pr: pr.get("createdAt") or "")
    return [pr["number"] for pr in matching]


def pick_bump_candidate(snapshots, bot_login):
    """Research D5: the one bump PR this run evaluates, from a snapshot of
    every auto-update-shaped PR. A PR handed over at its current head, or
    with no tracking issue to announce on, is skipped; of the rest the oldest
    that may merge wins, else the oldest (its unmet condition is announced
    once). So one stuck PR never hides a newer verified one. The switches
    are the same for every candidate, so they are taken as on here; decide()
    re-derives everything from the merge job's own fresh fetch."""
    usable = [snap for snap in snapshots or []
              if _is_bot((snap.get("author") or {}).get("login"), bot_login)
              and BUMP_BRANCH_RE.fullmatch(snap.get("headRefName") or "")
              and bump_tracking_issue(snap.get("body"))
              and not handed_over_at_head(snap, bot_login)]
    usable.sort(key=lambda snap: snap.get("createdAt") or "")
    if not usable:
        return None
    mergeable = [snap for snap in usable
                 if decide({"class": "bump", "snapshot": snap, "bot_login": bot_login,
                            "paused": False, "switch_on": True})["may_merge"]]
    chosen = (mergeable or usable)[0]
    return {"pr": chosen.get("number"), "issue": bump_tracking_issue(chosen.get("body"))}


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    decide_cmd = sub.add_parser("decide", help="inputs JSON + snapshot JSON -> MergeDecision JSON on stdout")
    decide_cmd.add_argument("--inputs", required=True, help="the payload without its snapshot (JSON file)")
    decide_cmd.add_argument("--snapshot", required=True, help="gh pr view JSON file")

    def _decide(a):
        with open(a.inputs, encoding="utf-8") as fh:
            payload = json.load(fh)
        with open(a.snapshot, encoding="utf-8") as fh:
            payload["snapshot"] = json.load(fh)
        print(json.dumps(decide(payload)))
    decide_cmd.set_defaults(func=_decide)
    fields_cmd = sub.add_parser("snapshot-fields", help="the gh pr view --json field list")
    fields_cmd.set_defaults(func=lambda _a: print(SNAPSHOT_FIELDS))
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
    shaped_cmd = sub.add_parser("bump-shaped", help="gh pr list JSON on stdin -> auto-update-shaped PR numbers")
    shaped_cmd.add_argument("--bot-login", required=True)
    shaped_cmd.set_defaults(func=lambda a: print(" ".join(str(n) for n in bump_shaped(json.load(sys.stdin),
                                                                                       a.bot_login))))
    bump_cmd = sub.add_parser("pick-bump", help="JSON array of snapshots on stdin -> "
                                                "{pr, issue} JSON or nothing")
    bump_cmd.add_argument("--bot-login", required=True)

    def _pick(a):
        picked = pick_bump_candidate(json.load(sys.stdin), a.bot_login)
        if picked:
            print(json.dumps(picked))
    bump_cmd.set_defaults(func=_pick)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
