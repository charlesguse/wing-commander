#!/usr/bin/env python3
"""Lifecycle review gate readiness (specs/062-lifecycle-review-gate,
contracts/readiness-and-merge.md, data-model.md "Readiness Decision").

WHY THIS EXISTS
---------------
A lifecycle PR may sit at `stage: "review"` while it is not actually safe
to review yet — a check still running, a merge conflict, or a round that
already reviewed this exact head SHA. Every condition is re-derived
against the PR's exact head SHA, fetched fresh at evaluation time — never
a value an earlier step captured, mirroring board_readiness.py's own
freshness guarantee.

`evaluate_from_snapshot()` is the pure decision, fixturable without a live
`gh` call; `evaluate()` is the runtime wrapper that fetches the snapshot.
"""
import json
import subprocess
import sys

CONDITIONS = ("checks_green", "gate_suite_green", "mergeable",
              "not_yet_reviewed", "kill_switch_clear")


# The commit-status context this gate itself posts on the PR head
# (lifecycle-review-gate.yml's `-f context=` writes). It is this gate's
# own output from an earlier round, never an input to whether a round
# may start: counting it made an inconclusive round's `error` status
# stand every later run down on that head for good.
OWN_STATUS_CONTEXT = "lifecycle-review-gate"


def _checks_green(rollup):
    """Mirrors board_readiness.py's own _checks_green: an empty rollup is
    not green, and every entry must have reached a terminal, non-failing
    state. This gate's own status (OWN_STATUS_CONTEXT) is left out before
    either test, so it can neither block a round nor stand in for a real
    check on an otherwise empty rollup."""
    rollup = [e for e in rollup if e.get("context") != OWN_STATUS_CONTEXT]
    if not rollup:
        return False
    for entry in rollup:
        state = (entry.get("state") or entry.get("conclusion") or "").upper()
        if state not in ("SUCCESS", "NEUTRAL", "SKIPPED"):
            return False
    return True


def _gate_suite_green(rollup):
    """Reuses board_readiness.py::_gate_suite_green's exact matching logic
    (T006) rather than re-deriving it: a CheckRun's own `name` is its job
    id ("lint"), never the workflow's display name, which only ever shows
    up in `workflowName`."""
    for entry in rollup:
        name = entry.get("name") or entry.get("context") or ""
        workflow_name = (entry.get("workflowName") or "").lower()
        if name == "lint" and "workflow" in workflow_name:
            state = (entry.get("state") or entry.get("conclusion") or "").upper()
            return state in ("SUCCESS", "NEUTRAL", "SKIPPED")
    return False


def evaluate_from_snapshot(snapshot, review_gate, kill_switch_paused):
    """snapshot: {"headRefOid": str, "statusCheckRollup": [...],
    "mergeable": str} -- the `gh pr view --json
    headRefOid,statusCheckRollup,mergeable,mergeStateStatus` shape, fetched
    fresh by the caller. review_gate: the spec-meta.json review_gate
    object (or None/{} before any round has run). Returns the
    ReadinessDecision dict (data-model.md), five conditions evaluated in
    order, unmet_reason naming the first failing condition's own name."""
    head_sha = snapshot.get("headRefOid")
    rollup = snapshot.get("statusCheckRollup") or []
    review_gate = review_gate or {}

    checks_green = _checks_green(rollup)
    gate_suite_green = _gate_suite_green(rollup)
    mergeable = snapshot.get("mergeable") == "MERGEABLE"
    not_yet_reviewed = review_gate.get("head_sha") != head_sha
    kill_switch_clear = not kill_switch_paused

    ready = (checks_green and gate_suite_green and mergeable
             and not_yet_reviewed and kill_switch_clear)

    unmet_reason = None
    if not checks_green:
        unmet_reason = "checks_green"
    elif not gate_suite_green:
        unmet_reason = "gate_suite_green"
    elif not mergeable:
        unmet_reason = "mergeable"
    elif not not_yet_reviewed:
        unmet_reason = "not_yet_reviewed"
    elif not kill_switch_clear:
        unmet_reason = "kill_switch_clear"

    return {
        "head_sha": head_sha,
        "checks_green": checks_green,
        "gate_suite_green": gate_suite_green,
        "mergeable": mergeable,
        "not_yet_reviewed": not_yet_reviewed,
        "kill_switch_clear": kill_switch_clear,
        "ready": ready,
        "unmet_reason": unmet_reason,
    }


def evaluate(pr_number, review_gate, kill_switch_paused):
    """Runtime entry point: `gh pr view <pr_number> --json
    headRefOid,statusCheckRollup,mergeable,mergeStateStatus`, fresh at this
    exact moment."""
    proc = subprocess.run(
        ["gh", "pr", "view", str(pr_number), "--json",
         "headRefOid,statusCheckRollup,mergeable,mergeStateStatus"],
        capture_output=True, text=True, check=True)
    snapshot = json.loads(proc.stdout)
    return evaluate_from_snapshot(snapshot, review_gate, kill_switch_paused)


def main():
    """Reads {"snapshot": {...}, "review_gate": {...}|null,
    "kill_switch_paused": bool} from stdin, prints the ReadinessDecision as
    JSON."""
    payload = json.load(sys.stdin)
    decision = evaluate_from_snapshot(
        payload["snapshot"], payload.get("review_gate"),
        payload["kill_switch_paused"])
    print(json.dumps(decision))


if __name__ == "__main__":
    main()
