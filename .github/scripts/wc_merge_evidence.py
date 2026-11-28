#!/usr/bin/env python3
"""The merge evidence audit (specs/125-merge-evidence-audit, contracts/
merge-evidence-report.md, data-model.md).

WHY THIS EXISTS
---------------
Nothing could answer "what was the evidence when this commit reached main?".
This module computes, in deterministic code and from a snapshot fetched fresh
for the exact head, one verdict per open pull request into main (hourly) and,
once a day, an audit of every merge of the last 30 days with the verdict as of
the moment it merged. It only records: it never merges, labels, comments,
pushes or writes a check or status (FR-017), and no merge job reads it
(FR-019).

It calls the existing condition code and copies none of it (FR-008):
board_merge (fix-PR and bump evidence, snapshot completeness, run
confirmation), board_readiness (the "every status counts" rule) and
lifecycle_merge_preconditions (the final-PR rule, which leaves the gate's own
status out, and the unresolved-human-review test). verify-merge-evidence.py
fails a copy.

The pure half (kinds, conditions, cut_snapshot, ledger, audit entries,
renderers) is driven by fixtures. The runtime half (collect, verdicts, audit)
is the only part that reads GitHub.
"""
import argparse
import datetime
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import board_merge  # noqa: E402
import board_readiness  # noqa: E402
import wc_board_status  # noqa: E402
import lifecycle_merge_preconditions as lmp  # noqa: E402
import lifecycle_readiness  # noqa: E402
import wc_lifecycle_review_marker  # noqa: E402
import wc_shared_review  # noqa: E402
from board_item_marker import last_converged_review_head  # noqa: E402
from board_triage import any_run_url_pattern  # noqa: E402

# The one home of both artifact names (T007); verify-merge-evidence.py checks
# them against the workflow's upload steps and wc_board_status.py reads the
# section one.
LEDGER_ARTIFACT = "merge-evidence-ledger"
SECTION_ARTIFACT = "merge-evidence-section"
WORKFLOW_FILE = "wing-commander-merge-evidence.yml"
LEDGER_FILE = "ledger.json"
SECTION_FILE = "merge-evidence-section.json"

KINDS = ("bump", "board-fix", "final", "spec", "maintainer")
RESULTS = ("met", "unmet", "not-read")
WINDOW_DAYS = 30
MERGED_KEEP_DAYS = 31
CLOSED_KEEP_DAYS = 7
RATE_LIMIT_FLOOR = 600
# Spec 119 (parked 2026-11-22) defines the hold label; nothing applies it yet.
HOLD_LABEL = "hold"
DECISION_RECORD_PREFIX = "**Session decision ("
RULE_ALL = "all-statuses"
RULE_NO_GATE = "without-gate-status"
UNREAD_STATE = "whether the pull request is still open (its state could not be read)"
NO_ROUND_RECORD_REASON = "no round record is counted for spec PRs: the shared reviewer reviews fix PRs only"
# Reported beside the verdict, never one of its conditions: it does not
# change first_unmet or the result (the first slice's rule that CI counts
# only for a pull request that changed nothing under .github/).
CI_DEFINITION_CONDITION = "ci_definition_from_default_branch"
_ISO_UTC_RE = re.compile(r"\A\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")
_PASS_REPORT_RE = re.compile(r"(?i)\b(review|validat\w*|verif\w*) (pass|report|verdict)\b|\bclean pass\b")
# A pass report also names itself in its title: the heading, or the leading
# bold span, that opens the comment after any HTML markers says review, pass,
# validation or verification, or the title line links an Actions run (a
# validator's evidence). Recall first: a reported record is never counted.
# Found by the SC-003 replay (T029): "Independent review:", "confirming
# pass", "post-split pass N" and a pre-merge run report went unlisted.
_TITLE_RE = re.compile(r"\A(?:[ \t]*<!--.*?-->[ \t]*\r?\n|[ \t]*\r?\n)*[ \t]*"
                       r"(?:#{1,6}[ \t]+(?P<heading>[^\n]*)|\*\*(?P<bold>[^\n]*?)\*\*(?P<rest>[^\n]*))")
_TITLE_NAMES_RE = re.compile(r"(?i)\b(?:review\w*|pass(?:es|ed)?|validat\w*|verif\w*)\b")
_RUN_LINK_RE = re.compile(any_run_url_pattern())
# A final PR's lifecycle issue: finalize.yml's own closing line first, else a
# GitHub closing keyword. A mention ("refs #N", "for #N") never links one.
_LIFECYCLE_LINE_RE = re.compile(r"(?m)^Lifecycle issue: #(\d+)[ \t\r]*$")
# The keyword fallback reads board_backlog_lines.closing_keyword_refs(), the
# closing-keyword pattern's one home (Gate 166 fails a copy here).
_FIX_ISSUE_RE = re.compile(r"fix/(\d+)-")


class LedgerError(Exception):
    """A ledger that is present but cannot be read: the run fails loudly."""


# --------------------------------------------------------------------------
# Pure half
# --------------------------------------------------------------------------
def _final_branch_re(prefix):
    return re.compile(r"{0}(?:[^/]+/)?\d+-[a-z0-9-]+".format(re.escape(prefix)))


def assign_kind(snap, bot_login, final_prefix="spec/", spec_prefix="spec-draft/", base_branch=None):
    """FR-002: (kind, kind_facts), first match wins; never an agent."""
    branch = snap.get("headRefName") or ""
    facts = {"branch": branch, "author": (snap.get("author") or {}).get("login"),
             "base": snap.get("baseRefName")}
    # One base branch for every kind (#1173 round 5, finding 1): board_merge's
    # bump and fix-PR tests compare against its own BASE_BRANCH, so they see
    # the snapshot with the run's base mapped onto it, and anything else off it.
    base = base_branch or board_merge.BASE_BRANCH
    on_base = snap.get("baseRefName") == base
    view = dict(snap, baseRefName=board_merge.BASE_BRANCH if on_base else None)
    if board_merge.attributed_to_auto_update(view, bot_login):
        return "bump", dict(facts, test="auto-update branch, bot author, tracking marker")
    if board_merge.eligible_fix_class(view, bot_login):
        return "board-fix", dict(facts, test="fix/<issue>-<slug> branch, bot author")
    same_repo = snap.get("cross_repository") is False
    if same_repo and on_base:
        if _final_branch_re(final_prefix).fullmatch(branch):
            return "final", dict(facts, test="head branch {0}[<P>/]<NNN-slug>".format(final_prefix))
        if _final_branch_re(spec_prefix).fullmatch(branch):
            return "spec", dict(facts, test="head branch {0}[<P>/]<NNN-slug>".format(spec_prefix))
    return "maintainer", dict(facts, test="no other kind matched",
                              cross_repository=snap.get("cross_repository"))


def linked_issue(kind, snap, repo=None):
    """The issue whose comments carry the kind's evidence, or None. `repo`
    (default GITHUB_REPOSITORY) says which repository a `owner/repo#N` or
    issue-URL closing reference must name."""
    if kind == "board-fix":
        match = _FIX_ISSUE_RE.match(snap.get("headRefName") or "")
        return int(match.group(1)) if match else None
    if kind == "final":
        body = snap.get("body") or ""
        match = _LIFECYCLE_LINE_RE.search(body)
        if match:
            return int(match.group(1))
        from board_backlog_lines import closing_keyword_refs
        refs = closing_keyword_refs(body, repo or os.environ.get("GITHUB_REPOSITORY") or "")
        return refs[0][0] if refs else None
    return None


def _cond(name, result, reason=""):
    return {"name": name, "result": result, "reason": "" if result == "met" else reason}


def _first_failing_entry(rollup, state_of):
    for entry in rollup:
        state = state_of(entry)
        if state not in board_readiness.GREEN_STATES:
            return "{0} is {1}".format(entry.get("name") or entry.get("context") or "a check", state or "unknown")
    return None


def _checks_condition(rollup, rule):
    if rollup is None:
        return _cond("checks_green_with_gate_suite", "not-read", "the head's checks were not read")
    if rule == RULE_NO_GATE:
        green = lmp.checks_green_without_gate_status(rollup)
        gate = lmp.gate_suite_green_in_rollup(rollup)
        counted = [e for e in rollup if e.get("context") != lifecycle_readiness.OWN_STATUS_CONTEXT]
    else:
        green = board_readiness.checks_green(rollup)
        gate = board_readiness.gate_suite_green(rollup)
        counted = rollup
    if not counted:
        return _cond("checks_green_with_gate_suite", "unmet", "no checks on the head")
    if not green:
        why = (_first_failing_entry(board_readiness.latest_per_check(counted),
                                    board_readiness._entry_state) or "a check is not green")
        return _cond("checks_green_with_gate_suite", "unmet", why)
    if not gate:
        return _cond("checks_green_with_gate_suite", "unmet", "the gate suite (lint) is not among the green checks")
    return _cond("checks_green_with_gate_suite", "met")


def reported_kind(comment, bot_login):
    """FR-009/FR-015: a record under a maintainer's account is listed, never
    counted. None for a comment that is no record of evidence at all."""
    if board_merge.is_app_user(comment.get("user"), bot_login):
        return None
    body = (comment.get("body") or "").lstrip()
    if body.startswith(DECISION_RECORD_PREFIX):
        return "decision-record"
    if _PASS_REPORT_RE.search(body) or _titled_pass_report(body):
        return "pass-report"
    return None


def _titled_pass_report(body):
    title = _TITLE_RE.match(body)
    if not title:
        return False
    named = title.group("heading") if title.group("heading") is not None else title.group("bold")
    line = "".join(title.group(g) or "" for g in ("heading", "bold", "rest"))
    return bool(_TITLE_NAMES_RE.search(named)) or bool(_RUN_LINK_RE.search(line))


def comment_url(comment, thread_url=None):
    """The comment's link: REST's html_url, else built from its id on its
    thread (board_merge.fetch_snapshot keeps only id, time, body and user;
    #1173 final review F2)."""
    url = comment.get("html_url") or comment.get("url")
    if not url and thread_url and comment.get("id") is not None:
        url = "{0}#issuecomment-{1}".format(thread_url, comment["id"])
    return url or ""


def reported_records(comments, bot_login, thread_url=None):
    out = []
    for comment in comments or []:
        kind = reported_kind(comment, bot_login)
        if kind:
            out.append({"url": comment_url(comment, thread_url), "id": comment.get("id"),
                        "author": (comment.get("user") or {}).get("login"), "kind": kind,
                        "created_at": comment.get("created_at")})
    return out


def pr_url(repo, number):
    return "{0}/{1}/pull/{2}".format(os.environ.get("GITHUB_SERVER_URL") or "https://github.com", repo, number)


def _bump_conditions(snap, bot_login):
    records = board_merge.bump_records(snap.get("comments"), bot_login)
    head = snap.get("headRefOid")
    record = board_merge.latest_record_at_head(records, head)
    if record is None:
        elsewhere = [r.get("head_sha") for r in records]
        why = ("the verification record names another commit ({0})".format(elsewhere[-1][:12])
               if elsewhere and elsewhere[-1] else "no pipeline verification record for this head")
        return [_cond("verification_confirmed", "unmet", why)]
    if record.get("result") != "passed":
        return [_cond("verification_confirmed", "unmet", "the verification at this head did not pass")]
    if not board_merge.verification_run_confirms(record, snap.get("verificationRun"), head):
        return [_cond("verification_confirmed", "unmet",
                      "the Actions API does not confirm the run the record names")]
    return [_cond("verification_confirmed", "met")]


def _board_fix_conditions(snap, bot_login):
    comments = snap.get("issue_comments")
    if comments is None:
        why = "the fix issue's comments were not read"
        return [_cond("review_verdict_at_head", "not-read", why), _cond("zero_open_findings", "not-read", why)]
    head = snap.get("headRefOid")
    seen = last_converged_review_head(snap.get("number"), comments, bot_login)
    if seen == head and head:
        # A converged verdict means the round cleared every in-scope finding.
        return [_cond("review_verdict_at_head", "met"), _cond("zero_open_findings", "met")]
    why = ("the newest converged review verdict names another commit ({0})".format(seen[:12]) if seen
           else "no converged review verdict from the pipeline's App")
    return [_cond("review_verdict_at_head", "unmet", why),
            _cond("zero_open_findings", "unmet", "no converged verdict at this head to show zero open findings")]


def _final_conditions(snap, bot_login):
    names = ("gate_round_at_head", "round_clean", "zero_open_in_scope",
             "no_unresolved_changes_requested", "no_hold_label")
    out = []
    comments = snap.get("issue_comments")
    if comments is None:
        out += [_cond(n, "not-read", "the lifecycle issue's comments were not read") for n in names[:3]]
    else:
        marker = wc_lifecycle_review_marker.read_marker(comments, bot_login) or {}
        head = snap.get("headRefOid")
        # FR-008: the review gate's reading of its own marker is the lifecycle
        # merge preconditions' (called, never re-typed; #1173 final review F1).
        pre = lmp.evaluate_from_snapshot({"headRefOid": head, "statusCheckRollup": []}, marker, False, [],
                                         bot_login)
        # Evidence naming another commit counts for nothing (FR-010).
        at_head = bool(pre["reviewed_at_this_head"]) and bool(head)
        if not marker:
            out.append(_cond(names[0], "unmet", "no lifecycle review gate round recorded"))
        elif not at_head:
            out.append(_cond(names[0], "unmet", "the latest round names another commit ({0})".format(
                (marker.get("head_sha") or "?")[:12])))
        else:
            out.append(_cond(names[0], "met"))
        out.append(_cond(names[1], "met") if at_head and pre["round_clean"]
                   else _cond(names[1], "unmet", "no clean round at this head"))
        out.append(_cond(names[2], "met") if at_head and pre["no_open_findings"]
                   else _cond(names[2], "unmet", "open in-scope findings, or no round at this head"))
    reviews = snap.get("reviews")
    if reviews is None:
        out.append(_cond(names[3], "not-read", "the pull request's reviews were not read"))
    elif lmp.no_unresolved_human_review(reviews, bot_login):
        out.append(_cond(names[3], "met"))
    else:
        out.append(_cond(names[3], "unmet", "a human changes-requested review is unresolved"))
    labels = snap.get("labels")
    if labels is None:
        out.append(_cond(names[4], "not-read", "the lifecycle issue's labels were not read"))
    elif HOLD_LABEL in labels:
        out.append(_cond(names[4], "unmet", "the lifecycle issue carries the hold label"))
    else:
        out.append(_cond(names[4], "met"))
    return out


def _review_round_conditions(snap, bot_login, base_branch=None):
    """A session fix PR (kind `maintainer`): the newest shared-reviewer round
    record at the exact head must be clean and confirmed by the run it
    names. An older clean round never stands in for a newer one that is
    unconfirmed (its run may still be going) or not clean. The record
    format, its parse and the confirmation are wc_shared_review's (called,
    never re-typed). `shared_review_runs` maps each run id a record names to
    the run's facts, or to None when the run does not exist; a run id
    missing from it was not read."""
    name = "review_round_record"
    if snap.get("comments") is None:
        return [_cond(name, "not-read", "the pull request's comments were not read")]
    records = wc_shared_review.parse_records(snap.get("comments"), bot_login)
    if not records:
        return [_cond(name, "unmet", "no shared-reviewer round record on the pull request")]
    head = snap.get("headRefOid")
    record = wc_shared_review.latest_round_for_commit(records, head) if head else None
    if record is None:
        return [_cond(name, "unmet", "the newest shared-reviewer round names another commit ({0})".format(
            str(records[-1].get("head_sha"))[:12]))]
    run_id = str(record.get("run_id") or "")
    if not run_id.isdigit():
        return [_cond(name, "unmet", "the newest shared-reviewer round at this head names no run")]
    runs = snap.get("shared_review_runs")
    if runs is None or run_id not in runs:
        return [_cond(name, "not-read", "run {0}, which the newest shared-reviewer round at this head names, "
                                        "was not read".format(run_id))]
    branch = base_branch or board_merge.BASE_BRANCH
    as_of = snap.get("as_of")
    if as_of and runs[run_id] is not None and _after(runs[run_id].get("updated_at"), as_of):
        # FR-012: a run that completed (or was re-run) after the merge is
        # evidence dated after it, so it is left out.
        return [_cond(name, "unmet", "run {0}, which the newest shared-reviewer round at this head names, "
                                     "completed after the merge".format(run_id))]
    if runs[run_id] is None or not wc_shared_review.confirm_record(record, runs[run_id], branch):
        return [_cond(name, "unmet", "the newest shared-reviewer round at this head (round {0}) is not "
                                     "confirmed by the run it names".format(record.get("round")))]
    if record.get("verdict") != "clean":
        return [_cond(name, "unmet", "the shared reviewer's round {0} at this head reads {1}".format(
            record.get("round"), record.get("verdict")))]
    return [_cond(name, "met")]


def _ci_definition_condition(snap):
    """Reported only: whether the pull request's CI ran a workflow
    definition the pull request itself could have written."""
    files = snap.get("files")
    if files is None:
        return _cond(CI_DEFINITION_CONDITION, "not-read", "the pull request's files were not read")
    touched = sorted({p for f in files for p in ((f or {}).get("path"), (f or {}).get("previousPath"))
                      if isinstance(p, str) and p.startswith(".github/")})
    if touched:
        return _cond(CI_DEFINITION_CONDITION, "unmet",
                     "it changes {0} path(s) under .github/ (first: {1}), so its CI ran a definition it "
                     "could have written".format(len(touched), touched[0]))
    return _cond(CI_DEFINITION_CONDITION, "met")


# The kinds whose conditions read records the pipeline App writes.
APP_EVIDENCE_KINDS = ("bump", "board-fix", "final")


def _app_seen(snap, bot_login):
    """True when any comment or review read for this PR is by the App."""
    for comment in list(snap.get("comments") or []) + list(snap.get("issue_comments") or []):
        if board_merge.is_app_user(comment.get("user"), bot_login):
            return True
    return any(board_merge._is_bot((r.get("author") or {}).get("login"), bot_login)
               for r in snap.get("reviews") or [])


def evaluate(snap, bot_login, now, final_prefix="spec/", spec_prefix="spec-draft/", base_branch=None):
    """One VerdictRecord (data-model.md) for `snap`, at its head. A snapshot
    the runtime half built carries the kind it assigned while choosing the
    evidence issue to read (`assigned_kind`); that one is reused, so the
    kind and the evidence read can never disagree."""
    assigned = snap.get("assigned_kind")
    kind, facts = assigned if assigned else assign_kind(snap, bot_login, final_prefix, spec_prefix, base_branch)
    rule = RULE_NO_GATE if kind == "final" else RULE_ALL
    not_read = list(snap.get("not_read") or [])
    complete = board_merge.snapshot_complete(snap) and not not_read
    if not board_merge.snapshot_complete(snap):
        not_read.append("snapshot lists (files, commits, comments)")
    if not bot_login:
        complete = False
        not_read.append("the pipeline App's login (no record can be told from a maintainer's)")
    elif kind in APP_EVIDENCE_KINDS and not _app_seen(snap, bot_login):
        # A wrong login reads like evidence that is not there yet; say so
        # (#1173 round 5, finding 4).
        complete = False
        not_read.append("any record by the App login `{0}`: no comment or review on the pull request or "
                        "its evidence issue is by it (is WING_COMMANDER_BOT_LOGIN right?)".format(bot_login))
    conditions = [_checks_condition(snap.get("statusCheckRollup"), rule)]
    if kind == "bump":
        conditions += _bump_conditions(snap, bot_login)
    elif kind == "board-fix":
        conditions += _board_fix_conditions(snap, bot_login)
    elif kind == "final":
        conditions += _final_conditions(snap, bot_login)
    elif kind == "maintainer":
        conditions += _review_round_conditions(snap, bot_login, base_branch)
    else:
        conditions.append(_cond("review_round_record", "unmet", NO_ROUND_RECORD_REASON))
    reported_conditions = [_ci_definition_condition(snap)]
    if not complete:
        # FR-005: nothing that depended on a part not read may report met.
        why = "snapshot incomplete: " + "; ".join(not_read)
        conditions = [conditions[0]] + [_cond(c["name"], "not-read", why) if c["result"] == "met" else c
                                        for c in conditions[1:]]
        reported_conditions = [_cond(c["name"], "not-read", why) if c["result"] == "met" else c
                               for c in reported_conditions]
    reported = (reported_records(snap.get("comments"), bot_login, snap.get("pr_url"))
                + reported_records(snap.get("issue_comments"), bot_login))
    return {"pr": snap.get("number"), "head": snap.get("headRefOid"), "kind": kind, "kind_facts": facts,
            "rule_applied": rule, "complete": complete, "not_read": not_read,
            "conditions": conditions, "first_unmet": first_unmet(conditions),
            "reported": reported, "reported_conditions": reported_conditions, "computed_at": now}


class RecordError(ValueError):
    """A VerdictRecord that breaks data-model.md's shape: it is never
    written to the ledger or the audit (the run fails loudly instead)."""


_RECORD_FIELDS = (("pr", int), ("head", str), ("kind", str), ("kind_facts", dict), ("rule_applied", str),
                  ("complete", bool), ("not_read", list), ("conditions", list), ("reported", list),
                  ("reported_conditions", list), ("computed_at", str))


def _condition_problems(where, cond):
    if not isinstance(cond, dict) or set(cond) != {"name", "result", "reason"}:
        return ["{0}: a condition is not exactly {{name, result, reason}}".format(where)]
    out = []
    if not isinstance(cond["name"], str) or not cond["name"]:
        out.append("{0}: a condition has no name".format(where))
    if cond["result"] not in RESULTS:
        out.append("{0}: condition {1!r} has result {2!r}".format(where, cond.get("name"), cond["result"]))
    if not isinstance(cond["reason"], str) or bool(cond["reason"]) == (cond["result"] == "met"):
        out.append("{0}: condition {1!r} needs a reason exactly when it is not met".format(where, cond.get("name")))
    return out


def validate_record(record):
    """The gate decision as a type (the first slice's payload types): raise
    RecordError naming every way `record` breaks the VerdictRecord shape,
    else return it unchanged."""
    if not isinstance(record, dict):
        raise RecordError("a verdict record is not an object")
    problems = []
    for key, typ in _RECORD_FIELDS:
        value = record.get(key)
        if key not in record or not isinstance(value, typ) or (typ is int and isinstance(value, bool)):
            problems.append("{0} is missing or not {1}".format(key, typ.__name__))
    if "first_unmet" not in record or not (record["first_unmet"] is None or isinstance(record["first_unmet"], str)):
        problems.append("first_unmet is missing or neither null nor a name")
    if problems:
        raise RecordError("; ".join(problems))
    if not record["head"]:
        problems.append("head is empty")
    if record["kind"] not in KINDS:
        problems.append("kind {0!r} is not one of {1}".format(record["kind"], ", ".join(KINDS)))
    if record["rule_applied"] not in (RULE_ALL, RULE_NO_GATE):
        problems.append("rule_applied {0!r} is not a known rule".format(record["rule_applied"]))
    if not _ISO_UTC_RE.match(record["computed_at"]):
        problems.append("computed_at {0!r} is not a UTC time".format(record["computed_at"]))
    conditions = record["conditions"]
    if not conditions or not isinstance(conditions[0], dict) or conditions[0].get("name") != "checks_green_with_gate_suite":
        problems.append("conditions do not open with checks_green_with_gate_suite")
    for where, conds in (("conditions", conditions), ("reported_conditions", record["reported_conditions"])):
        names = []
        for cond in conds:
            problems += _condition_problems(where, cond)
            names.append(cond.get("name") if isinstance(cond, dict) else None)
        if len(set(names)) != len(names):
            problems.append("{0}: a condition name repeats".format(where))
    if not problems and record["first_unmet"] != first_unmet(conditions):
        problems.append("first_unmet {0!r} is not the first condition that is not met".format(record["first_unmet"]))
    if record["complete"] == bool(record["not_read"]):
        problems.append("complete must be true exactly when nothing is listed as not read")
    if not record["complete"] and not problems and any(c["result"] == "met" for c in conditions[1:]):
        problems.append("an incomplete record reports a condition past the checks met (FR-005)")
    for entry in record["reported"]:
        if not isinstance(entry, dict) or entry.get("kind") not in ("pass-report", "decision-record", "other"):
            problems.append("a reported record has no known kind")
    if problems:
        raise RecordError("; ".join(problems))
    return record


def first_unmet(conditions):
    return next((c["name"] for c in conditions if c["result"] != "met"), None)


def result_of(record):
    return "met" if record and record.get("first_unmet") is None and record.get("complete") else "unmet"


# ---- as of the merge (D5) ----
def _after(stamp, merged_at):
    """A record whose time cannot be read is treated as after the merge."""
    return not stamp or str(stamp) > merged_at


def cut_rollup(rollup, merged_at):
    """-> (entries as of `merged_at`, how many were left out as later).

    `rollup` holds every check run (all attempts) and every commit status
    ever set on the head, as _rest_rollup() reads them. A commit status
    (`context`) counts as its latest state set at or before the merge; a
    check run as the latest attempt of its check started at or before it,
    and one that had not finished by the merge counts as not finished,
    whatever it concluded later. Entries started after the merge are left
    out.

    A check is board_readiness._check_key's, the rule live readiness keys
    latest_per_check() by (#889, found by the code review of #1226): a
    check run by its workflow run (the run id in its `detailsUrl`) and job
    name, so a separate run of one workflow on the head -- a bot review's
    skipped wing-commander-9-pr-conversation run after a human review's
    failed one -- is a check of its own and never hides the other. As
    there, an entry with no key (no workflow or no run id) or with no time
    is never merged with another, and check-run attempts tied at the
    newest start are all kept; a status tie keeps the first seen, since
    GitHub lists statuses newest first."""
    left_out = 0
    latest = {}
    for index, entry in enumerate(rollup):
        status = "context" in entry
        stamp = entry.get("startedAt") if status else (entry.get("startedAt") or entry.get("completedAt"))
        # A queued check run with no time at all existed, unfinished, at the
        # merge: keep it as not finished rather than leave it out.
        unstamped_check = not status and not stamp
        if _after(stamp, merged_at) and not unstamped_check:
            left_out += 1
            continue
        if not status and _after(entry.get("completedAt"), merged_at):
            entry = dict(entry, status="IN_PROGRESS", conclusion="")
        key = board_readiness._check_key(entry)
        if key is None or not stamp:
            latest[("unmerged", index)] = (stamp or "", [(index, entry)])
            continue
        if key not in latest or stamp > latest[key][0]:
            latest[key] = (stamp, [(index, entry)])
        elif stamp == latest[key][0] and not status:
            latest[key][1].append((index, entry))
    kept = sorted((pair for _stamp, pairs in latest.values() for pair in pairs), key=lambda t: t[0])
    return [entry for _index, entry in kept], left_out


def cut_snapshot(snap, merged_at):
    """FR-012: the snapshot with everything dated after `merged_at` left out,
    so the same evaluators judge the merge as of the moment it happened."""
    cut = dict(snap)
    left_out = 0

    def keep(items, field):
        nonlocal left_out
        if items is None:
            return None
        kept = [i for i in items if not _after((i or {}).get(field), merged_at)]
        left_out += len(items) - len(kept)
        return kept

    if snap.get("statusCheckRollup") is not None:
        rollup, left_out_checks = cut_rollup(snap["statusCheckRollup"], merged_at)
        left_out += left_out_checks
        cut["statusCheckRollup"] = rollup
    cut["comments"] = keep(snap.get("comments"), "created_at")
    if snap.get("issue_comments") is not None:
        cut["issue_comments"] = keep(snap["issue_comments"], "created_at")
    if snap.get("reviews") is not None:
        cut["reviews"] = keep(snap["reviews"], "submittedAt")
    # Label history: the label is on at the merge when its last event up to
    # the merge was `labeled`.
    if snap.get("label_events") is not None:
        state = {}
        for event in sorted(snap["label_events"], key=lambda e: e.get("created_at") or ""):
            if not _after(event.get("created_at"), merged_at):
                state[event.get("name")] = event.get("event") == "labeled"
        cut["labels"] = sorted(name for name, on in state.items() if on)
    if isinstance(snap.get("counts"), dict) and cut.get("comments") is not None:
        # The count described the full list. Only a whole read makes the cut
        # list whole too; a truncated read keeps its count, so the snapshot
        # stays incomplete (#1173 round 5, finding 2).
        full = snap.get("comments") or []
        if isinstance(snap["counts"].get("comments"), int) and len(full) >= snap["counts"]["comments"]:
            cut["counts"] = dict(snap["counts"], comments=len(cut["comments"]))
    # The shared reviewer's runs are read after the merge: the as-of time
    # lets _review_round_conditions leave out a run that completed after it.
    cut["as_of"] = merged_at
    cut["left_out"] = left_out
    return cut


# ---- ledger ----
def empty_ledger():
    return {"schema": 1, "first_written_at": None, "written_at": None, "written_by_run": None, "records": {}}


def stamp_ledger(ledger, now, run_id):
    """Marks the ledger written by this run. `first_written_at` is set once,
    by the run that first writes the ledger, and carried forward by every
    later one: the watching period (FR-024) is counted from it."""
    if not ledger.get("first_written_at"):
        ledger["first_written_at"] = now
    ledger["written_at"], ledger["written_by_run"] = now, run_id
    return ledger


def load_ledger(path):
    """Absent starts empty; present but unparseable fails (data-model.md)."""
    if path is None or not os.path.exists(path):
        return empty_ledger(), False
    try:
        with open(path, encoding="utf-8") as fh:
            ledger = json.load(fh)
        if (not isinstance(ledger, dict) or ledger.get("schema") != 1
                or not isinstance(ledger.get("records"), dict)):
            raise ValueError("not a schema-1 ledger")
    except (OSError, ValueError) as exc:
        raise LedgerError("the merge evidence ledger is present but unreadable: {0}".format(exc))
    return ledger, True


def ledger_key(pr, head):
    return "{0}@{1}".format(pr, head)


def replace_record(ledger, record):
    """FR-011: a later run for the same (pr, head) replaces the entry."""
    ledger["records"][ledger_key(record["pr"], record["head"])] = record
    return ledger


def _days_between(later, earlier):
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    return (datetime.datetime.strptime(later, fmt) - datetime.datetime.strptime(earlier, fmt)).total_seconds() / 86400


def prune(ledger, pr_states, now):
    """D2: kept while the PR is open and for 31 days after its merge; dropped
    7 days after a close without merge; an entry whose PR cannot be found is
    kept. `pr_states`: {pr: {"state": open|merged|closed, "at": time}}."""
    dropped = []
    for key, record in list(ledger["records"].items()):
        state = pr_states.get(record["pr"])
        if not state or state.get("state") == "open" or not state.get("at"):
            continue
        age = _days_between(now, state["at"])
        limit = MERGED_KEEP_DAYS if state["state"] == "merged" else CLOSED_KEEP_DAYS
        if age > limit:
            del ledger["records"][key]
            dropped.append(key)
    return dropped


# ---- audit ----
def build_audit_entry(pr_info, verdict, ledger):
    """data-model.md "Audit entry". `verdict` is the as-of-merge VerdictRecord."""
    merged_at = pr_info["merged_at"]
    prior = [r for r in ledger["records"].values()
             if r["pr"] == pr_info["pr"] and r["head"] == pr_info["last_head"]
             and (r.get("computed_at") or "9") <= merged_at]
    prior.sort(key=lambda r: r["computed_at"])
    latest = prior[-1] if prior else None
    entry = {"pr": pr_info["pr"], "kind": verdict["kind"], "merged_commit": pr_info["merged_commit"],
             "last_head": pr_info["last_head"], "merged_at": merged_at, "merged_by": pr_info["merged_by"],
             "verdict_as_of_merge": verdict, "mark": "recorded" if latest else "reconstructed",
             "prior_record_result": None, "decision_record": None}
    if latest and (result_of(latest) != result_of(verdict) or latest.get("first_unmet") != verdict.get("first_unmet")):
        entry["prior_record_result"] = {"result": result_of(latest), "first_unmet": latest.get("first_unmet")}
    decisions = [r for r in verdict.get("reported") or [] if r["kind"] == "decision-record"]
    entry["decision_record"] = decisions[0]["url"] if decisions else None
    return entry


def unpaired_commits(commits, merged_prs):
    """FR-014: first-parent commits on main that no merged PR produced."""
    produced = set()
    for p in merged_prs:
        if p.get("merged_commit"):
            produced.add(p["merged_commit"])
        produced.update(p.get("commits") or [])  # a rebase merge lands several
    return [c for c in commits if c["sha"] not in produced]


def _line(entry):
    v = entry["verdict_as_of_merge"]
    first = v["first_unmet"] or "none"
    text = "- #{0} {1} `{2}` as of merge: {3}, first unmet: {4}; merged by {5}; {6}".format(
        entry["pr"], entry["kind"], (entry["merged_commit"] or "unknown")[:12], result_of(v), first,
        entry["merged_by"], entry["mark"])
    if entry.get("prior_record_result"):
        text += "; earlier record: {0}, first unmet {1}".format(
            entry["prior_record_result"]["result"], entry["prior_record_result"]["first_unmet"] or "none")
    if not v.get("complete"):
        text += "; INCOMPLETE ({0})".format("; ".join(v.get("not_read") or []))
    if entry.get("decision_record"):
        text += "; decision record: {0}".format(entry["decision_record"])
    return text


def render_markdown(section, names_only=False):
    """The collapsed section's content. Names-only keeps every entry."""
    w = section["window"]
    out = ["Window {0} to {1}; built {2}. Watching period ends {3}. Owner and session merges are not told apart "
           "(both merge under the owner's account).".format(w["start"][:10], w["end"][:10], section["built_at"],
                                                           section.get("watching_ends") or "unknown"), ""]
    if names_only:
        out.append("Shortened: names only.")
        out.append("")
    out.append("**Merged into main ({0})**".format(len(section["entries"])))
    out.append("")
    for e in section["entries"]:
        out.append("- #{0} {1} {2}".format(e["pr"], result_of(e["verdict_as_of_merge"]), e["mark"])
                   if names_only else _line(e))
    if not section["entries"]:
        out.append("None.")
    out += ["", "**Reached main without a pull request ({0})**".format(len(section["unpaired"])), ""]
    for c in section["unpaired"]:
        note = " (could not be checked for a pull request)" if c.get("unchecked") else ""
        out.append("- `{0}`{1}".format(c["sha"][:12], note) if names_only else
                   "- `{0}` author {1}, committer {2}, {3}{4}".format(c["sha"][:12], c["author"], c["committer"],
                                                                     c["committed_at"], note))
    if not section["unpaired"]:
        out.append("None.")
    out += ["", "**Open pull requests ({0})**".format(len(section["open_verdicts"])), ""]
    for v in section["open_verdicts"]:
        out.append("- #{0} head `{1}` {2}".format(v["pr"], (v["head"] or "")[:12], result_of(v)) if names_only
                   else "- #{0} {1} head `{2}`: {3}, first unmet: {4}{5}".format(
                       v["pr"], v["kind"], (v["head"] or "")[:12], result_of(v), v["first_unmet"] or "none",
                       "" if v.get("complete") else "; INCOMPLETE ({0})".format("; ".join(v.get("not_read") or []))))
    if not section["open_verdicts"]:
        out.append("None.")
    return "\n".join(out) + "\n"


def build_section(entries, unpaired, open_verdicts, window, now, ledger, rebuilt_from_ledger_at=None):
    # FR-024: a fixed 30 days from the ledger's first write, never from a
    # record, since records are replaced hourly and pruned.
    first = ledger.get("first_written_at")
    ends = None
    if first:
        start = datetime.datetime.strptime(first, "%Y-%m-%dT%H:%M:%SZ")
        ends = (start + datetime.timedelta(days=WINDOW_DAYS)).strftime("%Y-%m-%d")
    counts = {"merged": len(entries), "unpaired": len(unpaired), "open": len(open_verdicts),
              "recorded": sum(1 for e in entries if e["mark"] == "recorded"),
              "reconstructed": sum(1 for e in entries if e["mark"] == "reconstructed"),
              "unmet": sum(1 for e in entries if result_of(e["verdict_as_of_merge"]) != "met")}
    section = {"schema": 1, "status": "built", "built_at": now, "window": window,
               "watching_ends": ends, "ledger_written_at": ledger.get("written_at"),
               "entries": entries, "unpaired": unpaired, "open_verdicts": open_verdicts, "counts": counts}
    section["full"] = render_markdown(section)
    section["names_only"] = render_markdown(section, names_only=True)
    return section


def window_bounds(now, days=WINDOW_DAYS):
    end = datetime.datetime.strptime(now, "%Y-%m-%dT%H:%M:%SZ")
    return {"start": (end - datetime.timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ"), "end": now}


# --------------------------------------------------------------------------
# Runtime half: the only code that reads GitHub. Never run by the fixtures.
# --------------------------------------------------------------------------
def _now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _run(args):
    return subprocess.run(args, capture_output=True, text=True)


def _gh_ok(args):
    r = _run(["gh"] + args)
    if r.returncode != 0:
        raise subprocess.CalledProcessError(r.returncode, ["gh"] + args, r.stdout, r.stderr)
    return r.stdout


def check_rate_limit(floor=RATE_LIMIT_FLOOR):
    """Fails below `floor` remaining core requests, rather than running half a read."""
    remaining = json.loads(_gh_ok(["api", "rate_limit"]))["resources"]["core"]["remaining"]
    if remaining < floor:
        raise RuntimeError("only {0} GitHub API requests remain (floor {1})".format(remaining, floor))
    return remaining


def _gh_json(args, what):
    """-> parsed JSON, None on a 404; any other failure raises."""
    r = _run(["gh"] + args)
    if r.returncode != 0:
        if "(HTTP 404)" in (r.stderr or ""):
            return None
        raise subprocess.CalledProcessError(r.returncode, what, r.stdout, r.stderr)
    return json.loads(r.stdout or "null")


def download_ledger(repo, default_branch, directory):
    """The newest unexpired `merge-evidence-ledger` artifact uploaded by this
    workflow on the default branch, or None when there is none. Found by
    name through the artifacts API, so any number of runs that upload none
    (audit and paused runs) cannot hide it. GitHub lists artifacts newest
    first and a run off the default branch is refused before its upload,
    so the first page holds the newest one. A 404 is told apart from other
    failures by gh's stderr."""
    listing = _gh_json(["api", "repos/{0}/actions/artifacts?name={1}&per_page=100".format(repo, LEDGER_ARTIFACT)],
                       "gh api actions/artifacts")
    artifacts = (listing or {}).get("artifacts") or []
    candidates = [a for a in artifacts if a.get("name") == LEDGER_ARTIFACT and not a.get("expired")
                  and (a.get("workflow_run") or {}).get("head_branch") == default_branch]
    candidates.sort(key=lambda a: a.get("created_at") or "", reverse=True)
    missed = []
    for artifact in candidates:
        run_id = (artifact.get("workflow_run") or {}).get("id")
        run = _gh_json(["api", "repos/{0}/actions/runs/{1}".format(repo, run_id)], "gh api actions/runs")
        # Only this repository's own scheduled or dispatched run: a fork PR's
        # run uses the same path and can name its head branch `main`
        # (#1173 review R1).
        if not run or not (run.get("path") or "").endswith("/" + WORKFLOW_FILE) \
                or not wc_board_status.trusted_watcher_run(run, repo) or run.get("head_branch") != default_branch:
            continue
        r = _run(["gh", "run", "download", str(run_id), "-R", repo, "-n", LEDGER_ARTIFACT, "-D", directory])
        if r.returncode == 0:
            return os.path.join(directory, LEDGER_FILE)
        if "(HTTP 404)" in (r.stderr or "") or "no valid artifacts" in (r.stderr or ""):
            missed.append(str(run_id))
            continue
        raise subprocess.CalledProcessError(r.returncode, "gh run download", r.stdout, r.stderr)
    if missed:
        # A ledger exists but none could be fetched: starting empty would
        # overwrite the history, so the run fails and uploads nothing
        # (#1173 round 5, finding 5).
        raise LedgerError("no merge-evidence-ledger could be downloaded from run(s) {0}".format(", ".join(missed)))
    return None


def _issue_comments(repo, number):
    # updated_at: wc_shared_review.parse_records refuses an edited round record.
    return [{"id": c.get("id"), "created_at": c.get("created_at"), "updated_at": c.get("updated_at"),
             "body": c.get("body"),
             "html_url": c.get("html_url"),
             "user": {"login": (c.get("user") or {}).get("login"), "type": (c.get("user") or {}).get("type")}}
            for c in board_merge.gh_items("repos/{0}/issues/{1}/comments?per_page=100".format(repo, number))]


def _assign_once(snap, bot_login, final_prefix, spec_prefix, base_branch):
    """The kind, computed once with the run's prefixes and base branch and
    kept on the snapshot for evaluate()."""
    kind, facts = assign_kind(snap, bot_login, final_prefix, spec_prefix, base_branch)
    snap["assigned_kind"] = [kind, facts]
    return kind


def _read_shared_review_runs(repo, snap, bot_login, actions_token, not_read, as_of=None):
    """For a session fix PR: the facts of the one run that can decide its
    verdict, the run the newest shared-reviewer round at its head names
    (wc_shared_review.fetch_run_facts, the read's one home). A failed read
    leaves `shared_review_runs` None and names it. `as_of`, for a merged PR,
    is its merge time: a record posted after it is cut before the verdict
    (cut_snapshot), so it is left out here by the same test."""
    # The record chosen here is the one _review_round_conditions judges
    # (the same comments, the same latest_round_for_commit), so a failed
    # read of a run no deciding record names never makes the verdict
    # not-read (#1346 passes 1 and 3).
    comments = snap.get("comments")
    if as_of and comments is not None:
        comments = [c for c in comments if not _after((c or {}).get("created_at"), as_of)]
    records = wc_shared_review.parse_records(comments, bot_login)
    head = snap.get("headRefOid")
    newest = wc_shared_review.latest_round_for_commit(records, head) if head else None
    run_ids = [str(newest["run_id"])] if newest is not None and str(newest.get("run_id") or "").isdigit() else []
    runs = {}
    try:
        for run_id in run_ids:
            runs[run_id] = wc_shared_review.fetch_run_facts(
                repo, run_id, lambda args: wc_shared_review._gh_api(args, actions_token))
    except wc_shared_review.GhReadError as exc:
        snap["shared_review_runs"] = None
        not_read.append("the shared reviewer's runs: {0}".format(exc))
        return snap
    snap["shared_review_runs"] = runs
    return snap


def _extend_with_evidence(repo, snap, bot_login, not_read, base_branch=None, final_prefix="spec/",
                          spec_prefix="spec-draft/", actions_token=None):
    """Reviews, labels and the kind's evidence issue; each part that cannot be
    read is named, never defaulted."""
    pull = json.loads(_gh_ok(["pr", "view", str(snap["number"]), "-R", repo, "--json",
                              "reviews,isCrossRepository"]))
    snap["reviews"] = pull.get("reviews") or []
    snap["cross_repository"] = bool(pull.get("isCrossRepository"))
    kind = _assign_once(snap, bot_login, final_prefix, spec_prefix, base_branch)
    if kind == "maintainer":
        _read_shared_review_runs(repo, snap, bot_login, actions_token, not_read)
    issue = linked_issue(kind, snap, repo)
    snap["issue_comments"] = None
    snap["labels"] = None
    if issue is not None:
        try:
            snap["issue_comments"] = _issue_comments(repo, issue)
            if kind == "final":
                snap["labels"] = [l["name"] for l in json.loads(_gh_ok(
                    ["api", "repos/{0}/issues/{1}".format(repo, issue)])).get("labels") or []]
        except (subprocess.CalledProcessError, ValueError) as exc:
            not_read.append("evidence issue #{0}: {1}".format(issue, (getattr(exc, "stderr", "") or str(exc)).strip()))
    elif kind in ("board-fix", "final"):
        not_read.append("no evidence issue is linked from the pull request")
    return snap


def collect(repo, bot_login, actions_token=None, default_branch="main", final_prefix="spec/",
            spec_prefix="spec-draft/"):
    """FR-004: a fresh whole snapshot per open PR head into the default branch."""
    snapshots = []
    prs = board_merge.gh_items("repos/{0}/pulls?state=open&base={1}&per_page=100".format(repo, default_branch))
    for pr in prs:
        not_read = []
        try:
            snap = board_merge.fetch_snapshot(repo, pr["number"], bot_login, actions_token)
            snap["number"] = pr["number"]
            snap["pr_url"] = pr_url(repo, pr["number"])
            snap["not_read"] = not_read
            _extend_with_evidence(repo, snap, bot_login, not_read, default_branch, final_prefix, spec_prefix,
                                  actions_token)
            # When this PR's snapshot was read, taken after the read: the
            # record's time (#1173 round 5, finding 6).
            snap["read_at"] = _now()
        except (subprocess.CalledProcessError, ValueError) as exc:
            snap = {"number": pr["number"], "headRefOid": (pr.get("head") or {}).get("sha"),
                    "headRefName": (pr.get("head") or {}).get("ref"), "baseRefName": default_branch,
                    "statusCheckRollup": None,
                    "author": {"login": (pr.get("user") or {}).get("login"),
                               "is_bot": (pr.get("user") or {}).get("type") == "Bot"},
                    "body": pr.get("body") or "",
                    "cross_repository": ((pr.get("head") or {}).get("repo") or {}).get("full_name") != repo,
                    "not_read": ["the snapshot: {0}".format((getattr(exc, "stderr", "") or str(exc)).strip())]}
            # The kind from what the PR list itself shows, so a read error
            # does not file the record under 'maintainer' by default.
            _assign_once(snap, bot_login, final_prefix, spec_prefix, default_branch)
            snap["read_at"] = _now()
        snapshots.append(snap)
    return snapshots


def _pr_state(repo, number):
    pull = json.loads(_gh_ok(["api", "repos/{0}/pulls/{1}".format(repo, number)]))
    if pull.get("merged_at"):
        return {"state": "merged", "at": pull["merged_at"]}
    if pull.get("state") == "closed":
        return {"state": "closed", "at": pull.get("closed_at")}
    return {"state": "open", "at": None}


def run_verdicts(repo, bot_login, default_branch, out_path, final_prefix, spec_prefix, run_id=None):
    check_rate_limit()
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        path = download_ledger(repo, default_branch, tmp)
        ledger, found = load_ledger(path)
    if not found:
        print("merge-evidence: no earlier ledger found; starting an empty one")
    now = _now()
    open_prs = set()
    for snap in collect(repo, bot_login, os.environ.get("WC_ACTIONS_TOKEN") or None, default_branch,
                        final_prefix, spec_prefix):
        open_prs.add(snap["number"])
        # Each record carries the time its own snapshot was read, never the
        # run's start, so a PR merged mid-run is never "recorded" from
        # evidence read after its merge.
        # A record that breaks the VerdictRecord shape fails the run before
        # it reaches the ledger (RecordError).
        replace_record(ledger, validate_record(evaluate(snap, bot_login, snap.get("read_at") or _now(), final_prefix,
                                                        spec_prefix, default_branch)))
    states = {}
    for pr in sorted({r["pr"] for r in ledger["records"].values()} - open_prs):
        try:
            states[pr] = _pr_state(repo, pr)
        except (subprocess.CalledProcessError, ValueError) as exc:
            print("merge-evidence: could not read PR #{0}: {1}; keeping its records".format(pr, exc))
    for key in prune(ledger, states, now):
        print("merge-evidence: pruned {0}".format(key))
    stamp_ledger(ledger, now, run_id)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(ledger, fh, sort_keys=True, indent=1)
    return ledger


def _rest_rollup(repo, sha):
    """Every check run (all attempts, `filter=all`) and every commit status
    ever set on the head (the full statuses history, not the combined
    latest-per-context status), in the rollup shape the reused evaluators
    read, each with its times. cut_rollup() picks what stood at the merge."""
    runs = _gh_ok(["api", "repos/{0}/actions/runs?head_sha={1}&per_page=100".format(repo, sha), "--paginate",
                   "--jq", ".workflow_runs[] | {check_suite_id, name} | tojson"])
    suites = {}
    for line in runs.splitlines():
        if line.strip():
            item = json.loads(line)
            suites[item["check_suite_id"]] = item["name"]
    rollup = []
    for line in _gh_ok(["api", "repos/{0}/commits/{1}/check-runs?filter=all&per_page=100".format(repo, sha), "--paginate",
                        "--jq", ".check_runs[] | tojson"]).splitlines():
        if not line.strip():
            continue
        c = json.loads(line)
        rollup.append({"name": c.get("name"), "status": (c.get("status") or "").upper(),
                       "conclusion": (c.get("conclusion") or "").upper(),
                       "completedAt": c.get("completed_at"), "startedAt": c.get("started_at"),
                       "detailsUrl": c.get("details_url") or "",
                       "workflowName": suites.get((c.get("check_suite") or {}).get("id"), "")})
    for line in _gh_ok(["api", "repos/{0}/commits/{1}/statuses?per_page=100".format(repo, sha), "--paginate",
                        "--jq", ".[] | tojson"]).splitlines():
        if not line.strip():
            continue
        s = json.loads(line)
        rollup.append({"context": s.get("context"), "state": (s.get("state") or "").upper(),
                       "startedAt": s.get("created_at")})
    return rollup


def _merged_snapshot(repo, pull, bot_login, actions_token, final_prefix="spec/", spec_prefix="spec-draft/",
                     base_branch=None):
    """A merged PR's snapshot at its last head, from REST, shaped as
    fetch_snapshot() shapes an open one."""
    number, head = pull["number"], pull["head"]["sha"]
    not_read = []
    snap = {"number": number, "pr_url": pull.get("html_url") or pr_url(repo, number),
            "headRefOid": head, "headRefName": pull["head"]["ref"],
            "baseRefName": pull["base"]["ref"], "body": pull.get("body") or "",
            "author": {"login": (pull.get("user") or {}).get("login"),
                       "is_bot": (pull.get("user") or {}).get("type") == "Bot"},
            "cross_repository": (pull["head"].get("repo") or {}).get("full_name") != repo,
            "not_read": not_read, "statusCheckRollup": None}
    base = "repos/{0}/pulls/{1}".format(repo, number)
    snap["counts"] = {"files": pull.get("changed_files"), "commits": pull.get("commits"),
                      "comments": pull.get("comments"), "head_sha": head}
    snap["files"] = [dict({"path": f.get("filename")},
                          **({"previousPath": f["previous_filename"]} if f.get("previous_filename") else {}))
                     for f in board_merge.gh_items(base + "/files?per_page=100")]
    snap["commits"] = [{"sha": c.get("sha"), "author": ({"login": c["author"].get("login"),
                                                         "type": c["author"].get("type")} if c.get("author") else None)}
                       for c in board_merge.gh_items(base + "/commits?per_page=100")]
    snap["comments"] = _issue_comments(repo, number)
    snap["reviews"] = [{"author": {"login": (r.get("user") or {}).get("login")}, "state": r.get("state"),
                        "submittedAt": r.get("submitted_at")}
                       for r in board_merge.gh_items(base + "/reviews?per_page=100")]
    try:
        snap["statusCheckRollup"] = _rest_rollup(repo, head)
    except (subprocess.CalledProcessError, ValueError) as exc:
        not_read.append("the head's checks: {0}".format((getattr(exc, "stderr", "") or str(exc)).strip()))
    snap["verificationRun"] = None
    if board_merge.BUMP_BRANCH_RE.fullmatch(snap["headRefName"]):
        record = board_merge.latest_record_at_head(board_merge.bump_records(snap["comments"], bot_login), head)
        if record is not None:
            snap["verificationRun"] = board_merge.fetch_verification_run(repo, record, actions_token)
    kind = _assign_once(snap, bot_login, final_prefix, spec_prefix, base_branch)
    if kind == "maintainer":
        _read_shared_review_runs(repo, snap, bot_login, actions_token, not_read, as_of=pull.get("merged_at"))
    issue = linked_issue(kind, snap, repo)
    snap["issue_comments"] = snap["labels"] = snap["label_events"] = None
    if issue is not None:
        try:
            snap["issue_comments"] = _issue_comments(repo, issue)
            if kind == "final":
                snap["label_events"] = [{"name": (e.get("label") or {}).get("name"), "event": e.get("event"),
                                         "created_at": e.get("created_at")}
                                        for e in board_merge.gh_items(
                                            "repos/{0}/issues/{1}/events?per_page=100".format(repo, issue))
                                        if e.get("event") in ("labeled", "unlabeled")]
        except (subprocess.CalledProcessError, ValueError) as exc:
            not_read.append("evidence issue #{0}: {1}".format(issue, (getattr(exc, "stderr", "") or str(exc)).strip()))
    elif kind in ("board-fix", "final"):
        not_read.append("no evidence issue is linked from the pull request")
    return snap


def _merge_info(pull):
    """The audit entry's merge facts, from the merged pull's REST object."""
    return {"pr": pull["number"], "merged_commit": pull.get("merge_commit_sha"),
            "last_head": pull["head"]["sha"], "merged_at": pull["merged_at"],
            "merged_by": (pull.get("merged_by") or {}).get("login")}


def capture_corpus(repo, bot_login, window, default_branch="main", final_prefix="spec/", spec_prefix="spec-draft/",
                   actions_token=None):
    """The SC-003 replay corpus (maintainer only, specs/125 tasks.md T029):
    every merge into the default branch with start <= merged_at < end, its
    merge facts and its _merged_snapshot() before the as-of-merge cut. The
    kind the capture assigned is dropped, so the replay runs assign_kind()
    and cut_snapshot() itself. Never run by the workflow (FR-012)."""
    check_rate_limit()
    merges = []
    for item in _closed_pulls_since(repo, default_branch, window["start"]):
        if not item.get("merged_at") or not window["start"] <= item["merged_at"] < window["end"]:
            continue
        pull = json.loads(_gh_ok(["api", "repos/{0}/pulls/{1}".format(repo, item["number"])]))
        snap = _merged_snapshot(repo, pull, bot_login, actions_token, final_prefix, spec_prefix, default_branch)
        snap.pop("assigned_kind", None)
        merges.append({"merge": _merge_info(pull), "snapshot": snap})
    merges.sort(key=lambda m: m["merge"]["pr"])
    return {"schema": 1, "repository": repo, "bot_login": bot_login, "default_branch": default_branch,
            "window": window, "captured_at": _now(), "merges": merges}


def run_audit(repo, bot_login, default_branch, out_path, final_prefix, spec_prefix, window=None):
    """Rebuilds the whole window; `window` is supplied by a test only (FR-012)."""
    check_rate_limit()
    import tempfile
    now = _now()
    window = window or window_bounds(now)
    with tempfile.TemporaryDirectory() as tmp:
        path = download_ledger(repo, default_branch, tmp)
        ledger, _found = load_ledger(path)
    token = os.environ.get("WC_ACTIONS_TOKEN") or None
    found = [p for p in _closed_pulls_since(repo, default_branch, window["start"])
             if p.get("merged_at") and window["start"] <= p["merged_at"] <= window["end"]]
    merged, entries = [], []
    for item in found:
        pull = json.loads(_gh_ok(["api", "repos/{0}/pulls/{1}".format(repo, item["number"])]))
        if not pull.get("merged_at") or not (window["start"] <= pull["merged_at"] <= window["end"]):
            continue
        info = _merge_info(pull)
        merged.append(info)
        snap = cut_snapshot(_merged_snapshot(repo, pull, bot_login, token, final_prefix, spec_prefix, default_branch),
                            pull["merged_at"])
        verdict = validate_record(evaluate(snap, bot_login, now, final_prefix, spec_prefix, default_branch))
        entries.append(build_audit_entry(info, verdict, ledger))
    entries.sort(key=lambda e: e["merged_at"], reverse=True)
    log = _run(["git", "log", "--first-parent", "--since", window["start"],
                                                "--format=%H%x09%an%x09%cn%x09%cI", "origin/" + default_branch])
    commits = []
    for line in (log.stdout if log.returncode == 0 else "").splitlines():
        parts = line.split("\t")
        if len(parts) == 4:
            commits.append({"sha": parts[0], "author": parts[1], "committer": parts[2], "committed_at": parts[3]})
    if log.returncode != 0:
        raise RuntimeError("git log of the window failed: {0}".format(log.stderr.strip()))
    open_verdicts = open_verdicts_latest(repo, ledger)
    unpaired = []
    for c in unpaired_commits(commits, merged):
        paired = _belongs_to_merged_pr(repo, c["sha"])
        if paired is None:
            unpaired.append(dict(c, unchecked=True))
        elif not paired:
            unpaired.append(c)
    section = build_section(entries, unpaired, open_verdicts, window, now, ledger)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(section, fh, sort_keys=True, indent=1)
    return section


def _is_open(repo, record):
    """True or False; None when the pull request's state could not be read."""
    try:
        return _pr_state(repo, record["pr"])["state"] == "open"
    except (subprocess.CalledProcessError, ValueError):
        return None


def latest_per_pr(records):
    """The newest record (by computed_at) of each pull request."""
    latest = {}
    for r in records:
        if r["pr"] not in latest or (r.get("computed_at") or "") > (latest[r["pr"]].get("computed_at") or ""):
            latest[r["pr"]] = r
    return [latest[pr] for pr in sorted(latest)]


def open_verdicts_latest(repo, ledger, is_open=None):
    """One record per open PR: its latest head; each PR's state read once.
    A PR whose state cannot be read is kept, as a copy marked incomplete
    that names what was not read (FR-005), never silently dropped."""
    is_open = is_open or _is_open
    out = []
    for record in latest_per_pr(ledger["records"].values()):
        state = is_open(repo, record)
        if state is None:
            out.append(dict(record, complete=False,
                            not_read=list(record.get("not_read") or []) + [UNREAD_STATE]))
        elif state:
            out.append(record)
    return out


def _belongs_to_merged_pr(repo, sha):
    """A rebase merge puts several commits on main; the pull request that
    produced one is told by GitHub, so a commit with a merged PR is paired.
    None when the lookup could not be read: the commit is then listed as
    could-not-be-checked, never as a direct push."""
    try:
        pulls = json.loads(_gh_ok(["api", "repos/{0}/commits/{1}/pulls".format(repo, sha)]))
    except (subprocess.CalledProcessError, ValueError):
        return None
    return any(p.get("merged_at") for p in pulls)


def _closed_pulls_since(repo, default_branch, start, read=None):
    """Closed PRs newest-updated first, paged by hand and stopped once a
    page's oldest updated_at is before `start` (a PR merged in the window was
    updated at or after its merge), so the cost does not grow with the
    repository's age."""
    read = read or (lambda page: json.loads(_gh_ok(["api", (
        "repos/{0}/pulls?state=closed&base={1}&sort=updated&direction=desc&per_page=100&page={2}"
        .format(repo, default_branch, page))])))
    out, page = [], 1
    while True:
        items = read(page)
        out += items
        if len(items) < 100 or min((p.get("updated_at") or "") for p in items) < start:
            return out
        page += 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("collect", "verdicts", "audit"):
        p = sub.add_parser(name)
        p.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY"))
        p.add_argument("--bot-login", default=os.environ.get("BOT_LOGIN", ""))
        p.add_argument("--default-branch", default="main")
        p.add_argument("--final-prefix", default=os.environ.get("FINAL_PREFIX") or "spec/")
        p.add_argument("--spec-prefix", default=os.environ.get("SPEC_PREFIX") or "spec-draft/")
        p.add_argument("--out", default={"verdicts": LEDGER_FILE, "audit": SECTION_FILE}.get(name, "-"))
    # The SC-003 corpus (maintainer only); its window is the replay's, never a report's.
    cap = sub.add_parser("capture", help="write the SC-003 replay corpus (maintainer only)")
    cap.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY"))
    cap.add_argument("--bot-login", required=True)
    cap.add_argument("--default-branch", default="main")
    cap.add_argument("--start", required=True)
    cap.add_argument("--end", required=True)
    cap.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    if not args.repo:
        parser.error("--repo or GITHUB_REPOSITORY is required")
    if args.command == "capture":
        doc = capture_corpus(args.repo, args.bot_login, {"start": args.start, "end": args.end}, args.default_branch,
                             actions_token=os.environ.get("WC_ACTIONS_TOKEN") or None)
        with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(doc, fh, sort_keys=True, indent=1, ensure_ascii=False)
            fh.write("\n")
        print("wrote {0}: {1} merges".format(args.out, len(doc["merges"])))
    elif args.command == "collect":
        json.dump(collect(args.repo, args.bot_login, os.environ.get("WC_ACTIONS_TOKEN") or None,
                          args.default_branch, args.final_prefix, args.spec_prefix), sys.stdout)
    elif args.command == "verdicts":
        run_verdicts(args.repo, args.bot_login, args.default_branch, args.out, args.final_prefix,
                     args.spec_prefix, os.environ.get("GITHUB_RUN_ID"))
    else:
        # No window argument exists: the report never supplies its own (FR-012).
        run_audit(args.repo, args.bot_login, args.default_branch, args.out, args.final_prefix, args.spec_prefix)
    return 0


if __name__ == "__main__":
    sys.exit(main())
