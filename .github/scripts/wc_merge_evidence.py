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
import lifecycle_merge_preconditions as lmp  # noqa: E402
import wc_lifecycle_review_marker  # noqa: E402
from board_item_marker import last_converged_review_head  # noqa: E402

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
NO_ROUND_RECORD_REASON = "no counted round record exists for this kind (#1142 not built)"
_PASS_REPORT_RE = re.compile(r"(?i)\b(review|validat\w*|verif\w*) (pass|report|verdict)\b|\bclean pass\b")
_LINKED_ISSUE_RE = re.compile(r"(?i)\b(?:closes|fixes|resolves|refs?|for)\s+#(\d+)")
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
    if board_merge.attributed_to_auto_update(snap, bot_login):
        return "bump", dict(facts, test="auto-update branch, bot author, tracking marker")
    if board_merge.eligible_fix_class(snap, bot_login):
        return "board-fix", dict(facts, test="fix/<issue>-<slug> branch, bot author")
    same_repo = snap.get("cross_repository") is False
    if same_repo and snap.get("baseRefName") == (base_branch or board_merge.BASE_BRANCH):
        if _final_branch_re(final_prefix).fullmatch(branch):
            return "final", dict(facts, test="head branch {0}[<P>/]<NNN-slug>".format(final_prefix))
        if _final_branch_re(spec_prefix).fullmatch(branch):
            return "spec", dict(facts, test="head branch {0}[<P>/]<NNN-slug>".format(spec_prefix))
    return "maintainer", dict(facts, test="no other kind matched",
                              cross_repository=snap.get("cross_repository"))


def linked_issue(kind, snap):
    """The issue whose comments carry the kind's evidence, or None."""
    if kind == "board-fix":
        match = _FIX_ISSUE_RE.match(snap.get("headRefName") or "")
        return int(match.group(1)) if match else None
    if kind == "final":
        match = _LINKED_ISSUE_RE.search(snap.get("body") or "")
        return int(match.group(1)) if match else None
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
        counted = [e for e in rollup if e.get("context") != "lifecycle-review-gate"]
    else:
        green = board_readiness.checks_green(rollup)
        gate = board_readiness.gate_suite_green(rollup)
        counted = rollup
    if not counted:
        return _cond("checks_green_with_gate_suite", "unmet", "no checks on the head")
    if not green:
        why = _first_failing_entry(counted, board_readiness._entry_state) or "a check is not green"
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
    if _PASS_REPORT_RE.search(body):
        return "pass-report"
    return None


def reported_records(comments, bot_login):
    out = []
    for comment in comments or []:
        kind = reported_kind(comment, bot_login)
        if kind:
            out.append({"url": comment.get("html_url") or comment.get("url") or "",
                        "author": (comment.get("user") or {}).get("login"), "kind": kind,
                        "created_at": comment.get("created_at")})
    return out


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
        if not marker:
            out.append(_cond(names[0], "unmet", "no lifecycle review gate round recorded"))
        elif marker.get("head_sha") != head:
            out.append(_cond(names[0], "unmet", "the latest round names another commit ({0})".format(
                (marker.get("head_sha") or "?")[:12])))
        else:
            out.append(_cond(names[0], "met"))
        # Evidence naming another commit counts for nothing (FR-010).
        at_head = marker.get("head_sha") == head and bool(head)
        out.append(_cond(names[1], "met") if at_head and marker.get("outcome") == "clean"
                   else _cond(names[1], "unmet", "no clean round at this head"))
        out.append(_cond(names[2], "met") if at_head and marker.get("findings_open") == 0
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


def evaluate(snap, bot_login, now, final_prefix="spec/", spec_prefix="spec-draft/", base_branch=None):
    """One VerdictRecord (data-model.md) for `snap`, at its head."""
    kind, facts = assign_kind(snap, bot_login, final_prefix, spec_prefix, base_branch)
    rule = RULE_NO_GATE if kind == "final" else RULE_ALL
    not_read = list(snap.get("not_read") or [])
    complete = board_merge.snapshot_complete(snap) and not not_read
    if not board_merge.snapshot_complete(snap):
        not_read.append("snapshot lists (files, commits, comments)")
    if not bot_login:
        complete = False
        not_read.append("the pipeline App's login (no record can be told from a maintainer's)")
    conditions = [_checks_condition(snap.get("statusCheckRollup"), rule)]
    if kind == "bump":
        conditions += _bump_conditions(snap, bot_login)
    elif kind == "board-fix":
        conditions += _board_fix_conditions(snap, bot_login)
    elif kind == "final":
        conditions += _final_conditions(snap, bot_login)
    else:
        conditions.append(_cond("review_round_record", "unmet", NO_ROUND_RECORD_REASON))
    if not complete:
        # FR-005: nothing that depended on a part not read may report met.
        why = "snapshot incomplete: " + "; ".join(not_read)
        conditions = [conditions[0]] + [_cond(c["name"], "not-read", why) if c["result"] == "met" else c
                                        for c in conditions[1:]]
    comments = list(snap.get("comments") or []) + list(snap.get("issue_comments") or [])
    return {"pr": snap.get("number"), "head": snap.get("headRefOid"), "kind": kind, "kind_facts": facts,
            "rule_applied": rule, "complete": complete, "not_read": not_read,
            "conditions": conditions, "first_unmet": first_unmet(conditions),
            "reported": reported_records(comments, bot_login), "computed_at": now}


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
    check run as the latest attempt of its (workflow, name) started at or
    before it, and one that had not finished by the merge counts as not
    finished, whatever it concluded later. Entries started after the merge
    are left out."""
    left_out = 0
    latest = {}
    for index, entry in enumerate(rollup):
        status = "context" in entry
        stamp = entry.get("startedAt") if status else (entry.get("startedAt") or entry.get("completedAt"))
        if _after(stamp, merged_at):
            left_out += 1
            continue
        if not status and _after(entry.get("completedAt"), merged_at):
            entry = dict(entry, status="IN_PROGRESS", conclusion="")
        key = ("status", entry.get("context")) if status else ("check", entry.get("workflowName"), entry.get("name"))
        # Ties keep the first seen: GitHub lists statuses newest first.
        if key not in latest or str(stamp) > str(latest[key][0]):
            latest[key] = (stamp, index, entry)
    return [entry for _stamp, _index, entry in sorted(latest.values(), key=lambda t: t[1])], left_out


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
        # The count described the full list; the cut list is whole by definition.
        cut["counts"] = dict(snap["counts"], comments=len(cut["comments"]))
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
        out.append("- `{0}`".format(c["sha"][:12]) if names_only else
                   "- `{0}` author {1}, committer {2}, {3}".format(c["sha"][:12], c["author"], c["committer"],
                                                                  c["committed_at"]))
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
    for artifact in candidates:
        run_id = (artifact.get("workflow_run") or {}).get("id")
        run = _gh_json(["api", "repos/{0}/actions/runs/{1}".format(repo, run_id)], "gh api actions/runs")
        if not run or not (run.get("path") or "").endswith("/" + WORKFLOW_FILE):
            continue
        r = _run(["gh", "run", "download", str(run_id), "-R", repo, "-n", LEDGER_ARTIFACT, "-D", directory])
        if r.returncode == 0:
            return os.path.join(directory, LEDGER_FILE)
        if "(HTTP 404)" in (r.stderr or "") or "no valid artifacts" in (r.stderr or ""):
            continue
        raise subprocess.CalledProcessError(r.returncode, "gh run download", r.stdout, r.stderr)
    return None


def _issue_comments(repo, number):
    return [{"id": c.get("id"), "created_at": c.get("created_at"), "body": c.get("body"),
             "html_url": c.get("html_url"),
             "user": {"login": (c.get("user") or {}).get("login"), "type": (c.get("user") or {}).get("type")}}
            for c in board_merge.gh_items("repos/{0}/issues/{1}/comments?per_page=100".format(repo, number))]


def _extend_with_evidence(repo, snap, bot_login, not_read, base_branch=None):
    """Reviews, labels and the kind's evidence issue; each part that cannot be
    read is named, never defaulted."""
    pull = json.loads(_gh_ok(["pr", "view", str(snap["number"]), "-R", repo, "--json",
                              "reviews,isCrossRepository"]))
    snap["reviews"] = pull.get("reviews") or []
    snap["cross_repository"] = bool(pull.get("isCrossRepository"))
    kind, _facts = assign_kind(snap, bot_login, base_branch=base_branch)
    issue = linked_issue(kind, snap)
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


def collect(repo, bot_login, actions_token=None, default_branch="main"):
    """FR-004: a fresh whole snapshot per open PR head into the default branch."""
    snapshots = []
    prs = board_merge.gh_items("repos/{0}/pulls?state=open&base={1}&per_page=100".format(repo, default_branch))
    for pr in prs:
        not_read = []
        try:
            snap = board_merge.fetch_snapshot(repo, pr["number"], bot_login, actions_token)
            snap["number"] = pr["number"]
            snap["not_read"] = not_read
            _extend_with_evidence(repo, snap, bot_login, not_read, default_branch)
        except (subprocess.CalledProcessError, ValueError) as exc:
            snap = {"number": pr["number"], "headRefOid": (pr.get("head") or {}).get("sha"),
                    "headRefName": (pr.get("head") or {}).get("ref"), "baseRefName": default_branch,
                    "statusCheckRollup": None,
                    "not_read": ["the snapshot: {0}".format((getattr(exc, "stderr", "") or str(exc)).strip())]}
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
    for snap in collect(repo, bot_login, os.environ.get("WC_ACTIONS_TOKEN") or None, default_branch):
        open_prs.add(snap["number"])
        replace_record(ledger, evaluate(snap, bot_login, now, final_prefix, spec_prefix, default_branch))
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
                       "workflowName": suites.get((c.get("check_suite") or {}).get("id"), "")})
    for line in _gh_ok(["api", "repos/{0}/commits/{1}/statuses?per_page=100".format(repo, sha), "--paginate",
                        "--jq", ".[] | tojson"]).splitlines():
        if not line.strip():
            continue
        s = json.loads(line)
        rollup.append({"context": s.get("context"), "state": (s.get("state") or "").upper(),
                       "startedAt": s.get("created_at")})
    return rollup


def _merged_snapshot(repo, pull, bot_login, actions_token):
    """A merged PR's snapshot at its last head, from REST, shaped as
    fetch_snapshot() shapes an open one."""
    number, head = pull["number"], pull["head"]["sha"]
    not_read = []
    snap = {"number": number, "headRefOid": head, "headRefName": pull["head"]["ref"],
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
    kind, _facts = assign_kind(snap, bot_login)
    issue = linked_issue(kind, snap)
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
    found = [p for p in board_merge.gh_items(
        "repos/{0}/pulls?state=closed&base={1}&sort=updated&direction=desc&per_page=100".format(repo, default_branch))
        if p.get("merged_at") and window["start"] <= p["merged_at"] <= window["end"]]
    merged, entries = [], []
    for item in found:
        pull = json.loads(_gh_ok(["api", "repos/{0}/pulls/{1}".format(repo, item["number"])]))
        if not pull.get("merged_at") or not (window["start"] <= pull["merged_at"] <= window["end"]):
            continue
        info = {"pr": pull["number"], "merged_commit": pull.get("merge_commit_sha"),
                "last_head": pull["head"]["sha"], "merged_at": pull["merged_at"],
                "merged_by": (pull.get("merged_by") or {}).get("login")}
        merged.append(info)
        snap = cut_snapshot(_merged_snapshot(repo, pull, bot_login, token), pull["merged_at"])
        entries.append(build_audit_entry(info, evaluate(snap, bot_login, now, final_prefix, spec_prefix, default_branch), ledger))
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
    unpaired = [c for c in unpaired_commits(commits, merged) if not _belongs_to_merged_pr(repo, c["sha"])]
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
    produced one is told by GitHub, so a commit with a merged PR is paired."""
    try:
        pulls = json.loads(_gh_ok(["api", "repos/{0}/commits/{1}/pulls".format(repo, sha)]))
    except (subprocess.CalledProcessError, ValueError):
        return False
    return any(p.get("merged_at") for p in pulls)


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
    args = parser.parse_args(argv)
    if not args.repo:
        parser.error("--repo or GITHUB_REPOSITORY is required")
    if args.command == "collect":
        json.dump(collect(args.repo, args.bot_login, os.environ.get("WC_ACTIONS_TOKEN") or None,
                          args.default_branch), sys.stdout)
    elif args.command == "verdicts":
        run_verdicts(args.repo, args.bot_login, args.default_branch, args.out, args.final_prefix,
                     args.spec_prefix, os.environ.get("GITHUB_RUN_ID"))
    else:
        # No window argument exists: the report never supplies its own (FR-012).
        run_audit(args.repo, args.bot_login, args.default_branch, args.out, args.final_prefix, args.spec_prefix)
    return 0


if __name__ == "__main__":
    sys.exit(main())
