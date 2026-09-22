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


def _checks_green(head_sha, rollup):
    """FR-036/FR-037: every rollup entry belongs to head_sha; an empty
    rollup is not green (a docs-only PR with no triggered checks is never
    reported ready)."""
    if not rollup:
        return False
    for entry in rollup:
        if entry.get("headSha") and entry["headSha"] != head_sha:
            return False
        state = (entry.get("state") or entry.get("conclusion") or "").upper()
        if state not in ("SUCCESS", "NEUTRAL", "SKIPPED"):
            return False
    return True


def _gate_suite_green(rollup):
    """research.md D13: read from the lint-workflows entry within the same
    fresh rollup, never a second local re-run."""
    for entry in rollup:
        name = (entry.get("name") or entry.get("context") or "")
        if "lint-workflows" in name or "lint workflows" in name.lower():
            state = (entry.get("state") or entry.get("conclusion") or "").upper()
            return state in ("SUCCESS", "NEUTRAL", "SKIPPED")
    return False


def evaluate_from_snapshot(snapshot, open_in_scope_findings, backstop_holds,
                            kill_switch_paused):
    """snapshot: {"headRefOid": str, "statusCheckRollup": [{"headSha": str,
    "state"|"conclusion": str, "name"|"context": str}, ...]} -- the `gh pr
    view --json headRefOid,statusCheckRollup` shape, fetched fresh by the
    caller. Returns the ReadinessDecision dict (data-model.md)."""
    head_sha = snapshot.get("headRefOid")
    rollup = snapshot.get("statusCheckRollup") or []

    checks_green = _checks_green(head_sha, rollup)
    gate_suite_green = checks_green and _gate_suite_green(rollup)
    zero_open_findings = open_in_scope_findings == 0
    kill_switch_clear = not kill_switch_paused

    ready = (checks_green and gate_suite_green and zero_open_findings
             and backstop_holds and kill_switch_clear)

    unmet_reason = None
    if not ready:
        if not checks_green:
            if not rollup:
                unmet_reason = "no checks reported on head_sha {0}".format(head_sha)
            else:
                unmet_reason = "checks not green on head_sha {0} (stale or failing)".format(head_sha)
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
