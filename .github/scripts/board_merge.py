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

from board_item_marker import BUMP_VERIFICATION_MARKER, last_marker_match, marker_regexes  # noqa: E402
from board_prove import actions_only  # noqa: E402
from board_readiness import _checks_green, _gate_suite_green  # noqa: E402

CONDITIONS_FIX = ("switch_on", "kill_switch_clear", "eligible_class", "checks_green",
                  "gate_suite_green", "review_converged", "backstop_holds")
CONDITIONS_BUMP = ("switch_on", "kill_switch_clear", "attributed_to_auto_update", "checks_green",
                   "gate_suite_green", "verification_passed_at_head")
REFUSAL_CLASSES = ("workflow-scope", "conflict", "protection", "other")

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
        if not authors or not all(_is_bot((a or {}).get("login"), bot_login) for a in authors):
            return False
    return not _touches_constitution(snapshot)


def bump_records(comments, bot_login):
    """The `wc-bump-verification` markers in bot-authored PR comments, oldest
    first. A marker in any other login's comment is ignored (a record is a
    trust surface: only the App's own counts)."""
    marker_re, open_re = marker_regexes(BUMP_VERIFICATION_MARKER)
    dated = []
    for comment in comments or []:
        if not _is_bot(((comment or {}).get("author") or {}).get("login"), bot_login):
            continue
        match = last_marker_match(comment.get("body") or "", marker_re, open_re)
        if not match:
            continue
        try:
            record = json.loads(match.group(1))
        except ValueError:
            continue
        if isinstance(record, dict):
            dated.append((comment.get("createdAt") or "", record))
    dated.sort(key=lambda pair: pair[0])
    return [record for _created, record in dated]


def evaluate_bump(snapshot, records, bot_login, paused, switch_on):
    """No size backstop: the verification gates the merge (Principle X)."""
    rollup = snapshot.get("statusCheckRollup") or []
    checks_green = _checks_green(rollup)
    latest = records[-1] if records else {}
    results = {
        "switch_on": switch_on,
        "kill_switch_clear": not paused,
        "attributed_to_auto_update": _attributed_to_auto_update(snapshot, bot_login),
        "checks_green": checks_green,
        "gate_suite_green": checks_green and _gate_suite_green(rollup),
        "verification_passed_at_head": (latest.get("result") == "passed"
                                        and bool(snapshot.get("headRefOid"))
                                        and latest.get("head_sha") == snapshot.get("headRefOid")),
    }
    return _decision(snapshot, "bump", CONDITIONS_BUMP, results)


_REFUSAL_PATTERNS = (
    ("workflow-scope", re.compile(r"workflows?`?\s+(permission|scope)|without\s+`?workflows?`?|"
                                  r"workflow\s+scope", re.IGNORECASE)),
    ("conflict", re.compile(r"not mergeable|merge conflict|conflicts? with", re.IGNORECASE)),
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
    "Announcement"): merged, refused or not-merged."""
    head = decision.get("head_sha")
    klass = decision.get("class")
    results = ", ".join("{0}={1}".format(name, "pass" if ok else "FAIL")
                        for name, ok in (decision.get("conditions") or {}).items())
    if outcome == "merged":
        return ("Merged ({0} class) at head_sha {1}; squash commit {2}.\n\nConditions: {3}.\n\n"
                "Proof: {4}.".format(klass, head, merge_sha, results, prove_disposition(snapshot or {})))
    if outcome == "refused":
        return ("GitHub refused the merge of head_sha {0} ({1} class), refusal_class {2}:\n\n```\n{3}\n```\n\n"
                "Nothing reached main by another route; handed to a maintainer.".format(
                    head, klass, refusal_class, (stderr or "").strip()))
    return ("Not merged ({0} class) at head_sha {1}: unmet condition `{2}`.\n\nConditions: {3}.".format(
        klass, head, decision.get("unmet_reason"), results))


def bump_tracking_issue(body):
    """The `auto-update:tracking` issue number a bump PR's body closes, or ''."""
    match = BUMP_ISSUE_RE.search(body or "")
    return match.group(1) if match else ""


def pick_bump_candidate(prs, bot_login):
    """Research D5: at most one open PR with the auto-update shape (bot author
    and branch); the oldest wins. `prs` is `gh pr list --json
    number,author,headRefName,createdAt`. Full attribution is decide()'s."""
    matching = [pr for pr in prs or []
                if _is_bot((pr.get("author") or {}).get("login"), bot_login)
                and BUMP_BRANCH_RE.fullmatch(pr.get("headRefName") or "")]
    matching.sort(key=lambda pr: pr.get("createdAt") or "")
    return matching[0]["number"] if matching else None


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    decide_cmd = sub.add_parser("decide", help="payload JSON on stdin -> MergeDecision JSON on stdout")
    decide_cmd.set_defaults(func=lambda _a: print(json.dumps(decide(json.load(sys.stdin)))))
    refusal_cmd = sub.add_parser("classify-refusal", help="stderr on stdin -> refusal class")
    refusal_cmd.set_defaults(func=lambda _a: print(classify_refusal(sys.stdin.read())))
    issue_cmd = sub.add_parser("tracking-issue", help="gh pr view JSON on stdin -> the bump's tracking issue")
    issue_cmd.set_defaults(func=lambda _a: print(bump_tracking_issue(json.load(sys.stdin).get("body"))))
    announce_cmd = sub.add_parser("announce", help="render the comment for a merge outcome")
    announce_cmd.add_argument("--decision", required=True, help="decision JSON file")
    announce_cmd.add_argument("--snapshot", required=True, help="gh pr view JSON file")
    announce_cmd.add_argument("--outcome", required=True, choices=("merged", "refused", "not-merged"))
    announce_cmd.add_argument("--merge-sha", default=None)
    announce_cmd.add_argument("--refusal-class", default=None)
    announce_cmd.add_argument("--stderr-file", default=None)

    def _announce(a):
        with open(a.decision, encoding="utf-8") as fh:
            decision = json.load(fh)
        with open(a.snapshot, encoding="utf-8") as fh:
            snapshot = json.load(fh)
        err = None
        if a.stderr_file:
            with open(a.stderr_file, encoding="utf-8") as fh:
                err = fh.read()
        print(render_announcement(decision, a.outcome, snapshot, a.merge_sha, a.refusal_class, err))
    announce_cmd.set_defaults(func=_announce)
    bump_cmd = sub.add_parser("pick-bump", help="gh pr list JSON on stdin -> PR number or empty")
    bump_cmd.add_argument("--bot-login", required=True)
    bump_cmd.set_defaults(func=lambda a: print(pick_bump_candidate(json.load(sys.stdin), a.bot_login) or ""))
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
