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
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import board_readiness  # noqa: E402

CONDITIONS = ("checks_green", "gate_suite_green", "mergeable",
              "not_yet_reviewed", "kill_switch_clear")


# The commit-status context this gate itself posts on the PR head
# (lifecycle-review-gate.yml's `-f context=` writes). It is this gate's
# own output from an earlier round, never an input to whether a round
# may start: counting it made an inconclusive round's `error` status
# stand every later run down on that head for good.
OWN_STATUS_CONTEXT = "lifecycle-review-gate"


def _checks_green(rollup):
    """board_readiness.py's own _checks_green, called rather than copied
    (#889): an empty rollup is not green, and every check's newest result
    must have reached a terminal, non-failing state. This gate's own
    status (OWN_STATUS_CONTEXT) is left out before either test, so it can
    neither block a round nor stand in for a real check on an otherwise
    empty rollup."""
    return board_readiness.checks_green(
        [e for e in rollup if e.get("context") != OWN_STATUS_CONTEXT])


def _gate_suite_green(rollup):
    """board_readiness.py's own _gate_suite_green, called rather than
    copied (T006, #889): a CheckRun's own `name` is its job id ("lint"),
    never the workflow's display name, which only ever shows up in
    `workflowName`, and only the lint job's newest result counts."""
    return board_readiness.gate_suite_green(rollup)


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


# The conditions the workflow's `select` job applies to each candidate,
# oldest first, so an older PR that is not ready yet does not stand the
# whole run down while a younger, ready one waits (#889). Only the
# conditions that are facts about the PR's current head are here:
# not_yet_reviewed is select's own marker filter already (with the
# not-converging re-arm rule this module does not know), and
# kill_switch_clear is every job's own `if:`. The `readiness` job still
# evaluates all five on a fresh snapshot, and stays the last word before a
# review, so a PR whose checks change between select and readiness is
# still stood down there.
SELECT_CONDITIONS = ("checks_green", "gate_suite_green", "mergeable")


def select_prefilter(snapshot):
    """select's per-candidate check: evaluate_from_snapshot() restricted to
    SELECT_CONDITIONS, so the rules keep one home. Returns {"ready": bool,
    "unmet_reason": the first unmet SELECT_CONDITIONS name or None}."""
    decision = evaluate_from_snapshot(snapshot, None, False)
    unmet = next((c for c in SELECT_CONDITIONS if not decision[c]), None)
    return {"ready": unmet is None, "unmet_reason": unmet}


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
    """With --select, reads a bare `gh pr view --json
    headRefOid,statusCheckRollup,mergeable,mergeStateStatus` snapshot from
    stdin and prints select_prefilter() as JSON. Otherwise reads
    {"snapshot": {...}, "review_gate": {...}|null, "kill_switch_paused":
    bool} from stdin, prints the ReadinessDecision as JSON."""
    if sys.argv[1:] == ["--select"]:
        print(json.dumps(select_prefilter(json.load(sys.stdin))))
        return
    if sys.argv[1:]:
        sys.exit("usage: lifecycle_readiness.py [--select] < payload.json")
    payload = json.load(sys.stdin)
    decision = evaluate_from_snapshot(
        payload["snapshot"], payload.get("review_gate"),
        payload["kill_switch_paused"])
    print(json.dumps(decision))


if __name__ == "__main__":
    main()
