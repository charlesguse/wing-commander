#!/usr/bin/env python3
"""Board loop readiness (specs/057-autonomous-board-loop,
contracts/readiness-report.md, data-model.md "Readiness Decision").

WHY THIS EXISTS
---------------
The loop may report a PR ready, but it may never merge, approve, or enable
auto-merge (FR-068) -- readiness is a report, not an action. Every
condition is re-derived against the PR's exact head SHA, fetched fresh at
evaluation time (FR-036) -- never a value this run captured earlier, since
a check that completed against an earlier push must never be read as
covering a later one (FR-037).

`evaluate_from_snapshot()` is the pure decision, fixturable without a live
`gh` call; `evaluate()` is the runtime wrapper that fetches the snapshot.
"""
import json
import subprocess
import sys

CONDITIONS = ("checks_green", "gate_suite_green", "zero_open_findings",
              "backstop_holds", "kill_switch_clear")


GREEN_STATES = ("SUCCESS", "NEUTRAL", "SKIPPED")


def _check_key(entry):
    """One check's identity within a rollup: a commit status by its
    context, a check run by its workflow and job name. None for an entry
    that names neither, which is never merged with another."""
    if entry.get("context"):
        return ("status", entry["context"])
    if entry.get("name"):
        return ("check", entry.get("workflowName") or "", entry["name"])
    return None


def latest_per_check(rollup):
    """The rollup without each check's superseded results (#889, found by
    the code review of #1196). One check can report more than once on the
    same head: a re-run of an older head's run, a reopened PR, the same
    commit pushed again. Only the newest result describes the head, as on
    GitHub's own checks list, so an entry is dropped when another entry of
    the same check started strictly later. An entry with no `startedAt` (a
    run still queued) is never dropped and never drops another, so a
    result is only ever set aside for one that provably came after it. The
    order of what is kept is unchanged."""
    rollup = list(rollup or [])
    newest = {}
    for entry in rollup:
        key, started = _check_key(entry), entry.get("startedAt")
        if key is not None and started and started > newest.get(key, ""):
            newest[key] = started
    return [entry for entry in rollup
            if _check_key(entry) is None or not entry.get("startedAt")
            or entry["startedAt"] >= newest[_check_key(entry)]]


def _checks_green(rollup):
    """FR-036/FR-037: an empty rollup is not green (a docs-only PR with no
    triggered checks is never reported ready), and every check's newest
    result (latest_per_check) must have reached a terminal, non-failing
    state. Freshness (FR-036) comes from
    the caller fetching `headRefOid` and `statusCheckRollup` together in
    one `gh pr view` call, never a value this run captured earlier --
    `gh` does not expose a per-entry commit SHA to re-check here
    (confirmed against both CheckRun and legacy StatusContext shapes,
    neither of which carries one), so there is nothing for this function
    itself to re-verify per entry; a caller that assembles a snapshot from
    more than one fetch breaks that guarantee with no code-level check to
    catch it."""
    rollup = latest_per_check(rollup)
    if not rollup:
        return False
    return all(_entry_state(entry) in GREEN_STATES for entry in rollup)


def _gate_suite_green(rollup):
    """research.md D13: read from the lint-workflows entry within the same
    fresh rollup, never a second local re-run. A CheckRun's own `name` is
    its job id ("lint"), never the workflow's name -- lint-workflows.yml's
    display name ("lint · workflows") only ever shows up in
    `workflowName` -- so both are checked together to find the right job
    among any repository's same-named jobs, rather than a `name` guess
    that never matches a real rollup entry. Only the lint job's newest
    result counts (latest_per_check)."""
    for entry in latest_per_check(rollup):
        name = entry.get("name") or entry.get("context") or ""
        workflow_name = (entry.get("workflowName") or "").lower()
        if name == "lint" and "workflow" in workflow_name:
            return _entry_state(entry) in GREEN_STATES
    return False


# Public names for the merge-evidence audit (specs/125-merge-evidence-audit,
# FR-008): it calls the "every status counts" rule, never copies it.
checks_green = _checks_green
gate_suite_green = _gate_suite_green

# A legacy StatusContext carries `state` (PENDING/EXPECTED); an Actions
# CheckRun that has not concluded carries `status` (QUEUED/IN_PROGRESS/
# WAITING/REQUESTED/PENDING) with an empty `conclusion` and no `state`.
NOT_CONCLUDED_STATES = ("QUEUED", "IN_PROGRESS", "WAITING", "REQUESTED", "PENDING", "EXPECTED")

# A check whose run was stopped before it reached a result: a newer push
# in a cancel-in-progress group (lint-workflows.yml's since #1196), a
# re-run of an older head's run in that group, or a person. It is not
# green, so nothing is ready or merges on it, but it is not a failure
# either: a re-run, or the run a newer push starts, decides the check. So
# it makes a not-ready record self-clearing, never durable (#889).
STOPPED_STATES = ("CANCELLED",)


def _entry_state(entry):
    """A rollup entry's state: a concluded CheckRun's `conclusion`, a
    StatusContext's `state`, else a not-yet-concluded CheckRun's `status`."""
    return (entry.get("state") or entry.get("conclusion") or entry.get("status") or "").upper()


def _unmet_class(rollup, checks_green):
    """specs/093-not-ready-board-release contracts/not-ready-hold.md,
    research.md D2: "self-clearing" when every check's newest result
    (latest_per_check) is either green (SUCCESS/NEUTRAL/SKIPPED), not yet
    concluded, or stopped before it concluded (STOPPED_STATES: CANCELLED),
    and at least one is not green (checks_green false because something has
    not finished, not because anything failed) -- "durable"
    otherwise (a terminal failing check state, an empty rollup, or an
    unmet reason that is not about checks_green at all: gate_suite_green,
    zero_open_findings, backstop_holds, kill_switch_clear). FR-005: derived
    only from the rollup's own per-entry states, never from an agent's
    reading of them. The class of the checks alone: evaluate_from_snapshot()
    makes the record durable whenever a non-check condition (open findings,
    a breached backstop, the kill switch) is also unmet. (A paused loop
    writes no record at all -- FR-006 is the workflow's kill-switch gating,
    research.md D9.)"""
    if checks_green:
        return "durable"
    rollup = latest_per_check(rollup)
    if not rollup:
        return "durable"
    for entry in rollup:
        state = _entry_state(entry)
        if (state not in GREEN_STATES and state not in NOT_CONCLUDED_STATES
                and state not in STOPPED_STATES):
            return "durable"
    return "self-clearing"


def evaluate_from_snapshot(snapshot, open_in_scope_findings, backstop_holds,
                            kill_switch_paused):
    """snapshot: {"headRefOid": str, "statusCheckRollup": [{"state"|
    "conclusion": str, "name"|"context": str, "workflowName": str}, ...]}
    -- the `gh pr view --json headRefOid,statusCheckRollup` shape, fetched
    fresh by the caller. Returns the ReadinessDecision dict
    (data-model.md), now including "unmet_class" (specs/093-not-ready-board-release):
    "self-clearing" | "durable" | None (when ready)."""
    head_sha = snapshot.get("headRefOid")
    rollup = snapshot.get("statusCheckRollup") or []

    checks_green = _checks_green(rollup)
    gate_suite_green = checks_green and _gate_suite_green(rollup)
    zero_open_findings = open_in_scope_findings == 0
    kill_switch_clear = not kill_switch_paused

    ready = (checks_green and gate_suite_green and zero_open_findings
             and backstop_holds and kill_switch_clear)

    unmet_reason = None
    unmet_class = None
    if not ready:
        # Open findings, a breached backstop or the kill switch stay unmet
        # when the checks finish, so they are durable whatever the rollup
        # says.
        # The checks' own class, then the record's: the reason text below
        # reads the first, the record carries the second.
        checks_class = _unmet_class(rollup, checks_green)
        other_unmet = not (zero_open_findings and backstop_holds and kill_switch_clear)
        unmet_class = "durable" if other_unmet else checks_class
        if not checks_green:
            if not rollup:
                unmet_reason = "no checks reported on head_sha {0}".format(head_sha)
            elif checks_class == "self-clearing" and any(
                    _entry_state(entry) in STOPPED_STATES
                    for entry in latest_per_check(rollup)):
                # A check's newest run was cancelled: nothing failed, but it
                # will not finish on its own. Say so, so nr_reason tells it
                # from a run still going (#889).
                unmet_reason = ("a check was cancelled on head_sha {0} and has not been "
                                "re-run".format(head_sha))
            elif checks_class == "self-clearing":
                # Only running checks: say so, so FR-009's nr_reason tells a
                # pending outcome from a failed one on the same head.
                unmet_reason = "checks still running on head_sha {0}".format(head_sha)
            else:
                unmet_reason = "checks not green on head_sha {0} (stale or failing)".format(head_sha)
            # A condition no later run clears on its own is named too, so a
            # durable record never blames only a check that is still running.
            if not zero_open_findings:
                unmet_reason += "; {0} open in-scope finding(s)".format(open_in_scope_findings)
            if not backstop_holds:
                unmet_reason += "; the size-and-path backstop does not hold on the final diff"
            if not kill_switch_clear:
                unmet_reason += "; the kill switch is set"
        elif not gate_suite_green:
            unmet_reason = "the lint-workflows check is not green on head_sha {0}".format(head_sha)
        elif not zero_open_findings:
            unmet_reason = "{0} open in-scope finding(s)".format(open_in_scope_findings)
        elif not backstop_holds:
            unmet_reason = "the size-and-path backstop does not hold on the final diff"
        elif not kill_switch_clear:
            unmet_reason = "the kill switch is set"

    return {
        "head_sha": head_sha,
        "checks_green": checks_green,
        "gate_suite_green": gate_suite_green,
        "open_findings": open_in_scope_findings,
        "backstop_holds": backstop_holds,
        "ready": ready,
        "unmet_reason": unmet_reason,
        "unmet_class": unmet_class,
    }


def evaluate(pr_number, open_in_scope_findings, backstop_holds, kill_switch_paused):
    """Runtime entry point: `gh pr view <pr_number> --json
    headRefOid,statusCheckRollup`, fresh at this exact moment (FR-036)."""
    proc = subprocess.run(
        ["gh", "pr", "view", str(pr_number), "--json", "headRefOid,statusCheckRollup"],
        capture_output=True, text=True, check=True)
    snapshot = json.loads(proc.stdout)
    return evaluate_from_snapshot(snapshot, open_in_scope_findings, backstop_holds,
                                  kill_switch_paused)


def main():
    """Reads {"snapshot": {...}, "open_in_scope_findings": int,
    "backstop_holds": bool, "kill_switch_paused": bool} from stdin, prints
    the ReadinessDecision as JSON."""
    payload = json.load(sys.stdin)
    decision = evaluate_from_snapshot(
        payload["snapshot"], payload["open_in_scope_findings"],
        payload["backstop_holds"], payload["kill_switch_paused"])
    print(json.dumps(decision))


if __name__ == "__main__":
    main()
