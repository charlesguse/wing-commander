#!/usr/bin/env python3
"""Deterministic decisions for spec-pr-review.yml (spec 122).

Pure functions behind a stdin-JSON / stdout-JSON CLI. Every decision the
workflow acts on is made here, never read from agent prose (IX), and an
unreadable input exits non-zero rather than earning a pass (VIII).

    spec_pr_review.py select       list of snapshots   -> {selected, skips}
    spec_pr_review.py eligible     one snapshot        -> {eligible, reason}
    spec_pr_review.py verdict      findings[]          -> {verdict}
    spec_pr_review.py check-fixes  fixes + caps        -> {pushable, blocked}
    spec_pr_review.py plan-actions findings + results  -> ActionPlan
    spec_pr_review.py failed-cap   {failures}          -> {stop}

REUSE NOTES (T001) -- what this module consumes rather than re-implements:
  wc_convergence.decide(history, budget=)   the spec 116 stop arithmetic;
        a snapshot's `convergence_history` is run through it here.
  wc_review_finding_fingerprint.fingerprint(issue, title, file_path)
        the finding dedup key; findings keep that fingerprint_basis shape.
  wc_lifecycle_review_marker.read_marker(comments, bot_login)
        spec 062's head-SHA bookkeeping; the workflow turns the App's own
        reviews into this module's `rounds` (completed rounds only).
  .github/actions/wing-commander-clarification-marker
        owns the open-marker scan; a snapshot carries only its boolean
        result as `open_marker`.
  The workflow (not this module) calls git_read, the hardened-push and
  refresh-remote composites, and the post-review-comment composite.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import wc_convergence  # noqa: E402

READY = "ready for the owner"
NOT_READY = "not ready"
SPEC_BRANCH_PREFIX = "spec-draft/"
ROUND_BUDGET = 5
FAILED_ATTEMPT_CAP = 2
FIX_SIZE_CAP = 200  # changed lines per push
MAINTAINER_ASSOCIATIONS = ("OWNER", "MEMBER", "COLLABORATOR")
CLASSES = ("unambiguous-error", "owner-decision")
PRECEDENT_KINDS = ("default-branch", "head", "issue-comment")


class InputError(Exception):
    pass


def _need(obj, key, kind=None):
    if not isinstance(obj, dict) or key not in obj:
        raise InputError("missing field %r" % key)
    value = obj[key]
    if kind is not None and not isinstance(value, kind):
        raise InputError("field %r has the wrong type" % key)
    return value


def completed_rounds(snap):
    return [r for r in snap.get("rounds", []) if r.get("outcome") == "reviewed"]


def settledness(snap):
    """{settled, reason} per data-model.md 'Settledness'."""
    dispatch = snap.get("dispatch")
    labels = snap.get("stage_labels", [])
    if dispatch:
        if dispatch.get("actor_type") != "User":
            return {"settled": False, "reason": "unsettled:dispatch-bot-actor"}
        if dispatch.get("association") not in MAINTAINER_ASSOCIATIONS:
            return {"settled": False,
                    "reason": "unsettled:dispatch-not-maintainer"}
        if "stage:spec" not in labels:
            return {"settled": False, "reason": "unsettled:stage"}
        if snap.get("open_marker"):
            return {"settled": False, "reason": "unsettled:open-marker"}
        return {"settled": True, "reason": "ok"}
    if "stage:spec" not in labels or "stage:clarify" in labels:
        return {"settled": False, "reason": "unsettled:stage"}
    if snap.get("open_marker"):
        return {"settled": False, "reason": "unsettled:open-marker"}
    announced = [a for a in snap.get("announcements", [])
                 if a.get("author_is_app") and a.get("body_marker_present")]
    if not announced:
        return {"settled": False, "reason": "unsettled:no-announcement"}
    latest = max(a.get("created_at", "") for a in announced)
    if snap.get("head_committed_at", "") > latest:
        return {"settled": False, "reason": "unsettled:head-newer"}
    return {"settled": True, "reason": "ok"}


def failed_cap(data):
    failures = _need(data, "failures", int)
    return {"stop": failures >= FAILED_ATTEMPT_CAP}


def eligible(snap):
    _need(snap, "pr")
    if snap.get("pause"):
        return {"eligible": False, "reason": "paused"}
    ref = snap.get("head_ref") or ""
    if (snap.get("state", "open") != "open" or snap.get("final_or_plan")
            or not ref.startswith(SPEC_BRANCH_PREFIX)):
        return {"eligible": False, "reason": "not-spec-pr"}
    if snap.get("head_repo") != snap.get("repo"):
        return {"eligible": False, "reason": "fork"}
    issues = snap.get("issues", [])
    if not issues:
        return {"eligible": False, "reason": "no-issue"}
    if len(issues) > 1:
        return {"eligible": False, "reason": "multiple-issues"}
    s = settledness(snap)
    if not s["settled"]:
        return {"eligible": False, "reason": s["reason"]}
    rounds = completed_rounds(snap)
    if any(r.get("sha") == snap.get("head_sha") for r in rounds):
        return {"eligible": False, "reason": "already-reviewed"}
    if len(rounds) >= ROUND_BUDGET:
        return {"eligible": False, "reason": "budget-exhausted"}
    hist = snap.get("convergence_history")
    if hist and wc_convergence.decide(hist, budget=ROUND_BUDGET)["stop"]:
        return {"eligible": False, "reason": "convergence-stop"}
    # FR-018/FR-019: a persisted stop note (the App's durable note on the
    # lifecycle issue) holds until the diff against main moves; `rearmed` is
    # the select step's wc_convergence.py `rearmed` answer for the current head.
    note = snap.get("stop_note")
    if note and not note.get("rearmed"):
        return {"eligible": False,
                "reason": "budget-exhausted" if note.get("reason") == "budget-exhausted"
                else "convergence-stop"}
    failures = snap.get("failed_attempts", {}).get(snap.get("head_sha"), 0)
    if failures >= FAILED_ATTEMPT_CAP and not snap.get("dispatch"):
        return {"eligible": False, "reason": "failed-cap"}
    return {"eligible": True, "reason": "ok"}


def select(snaps):
    if not isinstance(snaps, list):
        raise InputError("select input must be a list")
    selected, skips = None, []
    for snap in snaps:
        d = eligible(snap)
        if d["eligible"] and selected is None:
            selected = {"pr": snap["pr"], "head_sha": snap.get("head_sha")}
        elif d["eligible"]:
            skips.append({"pr": snap["pr"], "reason": "one-per-run"})
        else:
            skips.append({"pr": snap["pr"], "reason": d["reason"]})
    return {"selected": selected, "skips": skips}


def verdict(findings):
    if not isinstance(findings, list):
        raise InputError("findings must be a list")
    return {"verdict": NOT_READY if findings else READY}


def _in_spec_dir(path, spec_dir, project_dir):
    base = spec_dir.strip("/")
    if project_dir:
        base = project_dir.strip("/") + "/" + base
    return (isinstance(path, str) and ".." not in path.split("/")
            and (path == base or path.startswith(base + "/")))


def check_fixes(data):
    spec_dir = _need(data, "spec_dir", str)
    project_dir = data.get("project_dir", "")
    cap = data.get("size_cap", FIX_SIZE_CAP)
    fixes = _need(data, "fixes", list)
    pushable, blocked = [], []
    for fx in fixes:
        finding = fx.get("finding")
        reason = None
        if not all(_in_spec_dir(p, spec_dir, project_dir)
                   for p in fx.get("paths", [])) or not fx.get("paths"):
            reason = "path-outside-spec-dir"
        elif fx.get("lines_changed", 0) > cap:
            reason = "over-size-cap"
        elif fx.get("kind", "fix") != "marker":
            prec = fx.get("precedent") or {}
            if prec.get("kind") not in PRECEDENT_KINDS or not prec.get("ref"):
                reason = "precedent-missing"
            elif not prec.get("resolved"):
                reason = "precedent-unresolvable"
        if reason:
            blocked.append({"finding": finding, "reason": reason})
        else:
            pushable.append(finding)
    return {"pushable": pushable, "blocked": blocked}


def plan_actions(data):
    findings = _need(data, "findings", list)
    results = data.get("push_results", {})
    fresh = data.get("freshness", {})
    writable = not (fresh.get("stale") or fresh.get("closed"))
    # Doubtful classification is an owner decision.
    decisions = [f for f in findings if f.get("class") != "unambiguous-error"]
    errors = [f for f in findings if f.get("class") == "unambiguous-error"]
    blocked = results.get("blocked_count", 0)
    push_fixes = writable and bool(errors)
    push_markers = writable and bool(decisions)
    fixes_ok = bool(results.get("fixes_pushed")) and not blocked
    markers_ok = bool(results.get("markers_pushed"))
    plan = {
        "push_fixes": push_fixes,
        "push_markers": push_markers,
        "move_label": writable and push_markers and markers_ok,
        "post_announcement": (writable and bool(errors) and not decisions
                              and fixes_ok),
        "status": "failure" if findings else "success",
        # Never APPROVE or REQUEST_CHANGES (FR-010).
        "review_event": "COMMENT",
    }
    if not writable:
        plan["issue_line"] = "Result is stale or the PR is closed; no writes."
    elif not findings:
        plan["issue_line"] = "Reviewed: ready for the owner."
    else:
        plan["issue_line"] = "Reviewed: not ready (%d finding%s)." % (
            len(findings), "" if len(findings) == 1 else "s")
    if decisions and not plan["move_label"]:
        plan["handoff"] = ("Owner decisions could not be written as markers; "
                           "a reply on the issue will not be folded. Answer by "
                           "editing the spec on the branch, then a maintainer "
                           "dispatches the review.")
    return plan


COMMANDS = {
    "select": select,
    "eligible": eligible,
    "verdict": verdict,
    "check-fixes": check_fixes,
    "plan-actions": plan_actions,
    "failed-cap": failed_cap,
}


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1 or argv[0] not in COMMANDS:
        sys.stderr.write("usage: spec_pr_review.py {%s}\n" % "|".join(COMMANDS))
        return 2
    try:
        data = json.load(sys.stdin)
        out = COMMANDS[argv[0]](data)
    except (ValueError, InputError, AttributeError, TypeError) as exc:
        sys.stderr.write("spec_pr_review: unreadable input: %s\n" % exc)
        return 1
    json.dump(out, sys.stdout, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
