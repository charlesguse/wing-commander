#!/usr/bin/env python3
"""Gate 158 -- spec-pr-review.yml is wired the way specs/122 requires.

Static structure only (yaml.safe_load plus text scans). Asserts:

  FR-010  no APPROVE / REQUEST_CHANGES review event and no merge call anywhere
          in the workflow (the posted review is the post-review-comment
          composite, which posts event=COMMENT).
  FR-015b every git push goes through wing-commander-hardened-push, and no
          bare `git push` appears in a run: block.
  FR-015c the label move step is gated on the push step's success
          (the plan's move_label, which plan-actions sets only when markers
          were pushed) and never runs unconditionally.
  FR-016  the commit-status context is `spec-pr-review`, which differs from
          lifecycle-review-gate's; the failure state is the default and
          success is reachable only from "ready for the owner".
  FR-020  the kill-switch variable is read in the `select` job.
  FR-022  no workflow_call trigger (no input, secret or output surface).
  FR-023  the cost line comes from the metrics-summary composite; the
          formatter is not inlined.
  model/effort come from the two variables, with the stated defaults.

Usage: python3 .github/scripts/verify-spec-pr-review-wiring.py [--self-test]
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import yaml  # noqa: E402

WORKFLOW = os.path.join(".github", "workflows", "spec-pr-review.yml")
OTHER_CONTEXT = "lifecycle-review-gate"


def check(text):
    problems = []
    doc = yaml.safe_load(text)
    triggers = doc.get(True, doc.get("on")) or {}
    if "workflow_call" in triggers:
        problems.append("FR-022: a workflow_call trigger was added")
    for forbidden in ("APPROVE", "REQUEST_CHANGES", "gh pr merge", "gh pr review"):
        if forbidden in text:
            problems.append("FR-010: %r appears in the workflow" % forbidden)
    uses = text
    if "wing-commander-post-review-comment" not in uses:
        problems.append("FR-011: the review is not posted through wing-commander-post-review-comment")
    if "wing-commander-metrics-summary" not in uses or "cost-line" not in uses:
        problems.append("FR-024: the cost line is not read from the metrics-summary composite")
    if re.search(r"\$\s*\{\s*COST|cost_usd|total_cost", text):
        problems.append("FR-023: a cost formatter is inlined")
    jobs = doc.get("jobs", {})
    for name in ("select", "review", "act"):
        if name not in jobs:
            problems.append("missing job %r" % name)
    for job_name, job in jobs.items():
        for step in job.get("steps", []):
            run = step.get("run") or ""
            if re.search(r"(^|[\s;&|])git push\b", run):
                problems.append("FR-015b: %s / %s runs a bare git push" % (job_name, step.get("name")))
    act_steps = jobs.get("act", {}).get("steps", [])
    push = [s for s in act_steps if "wing-commander-hardened-push" in str(s.get("uses", ""))]
    if len(push) != 1:
        problems.append("FR-015b: the act job must push through exactly one hardened-push step")
    elif not str(push[0].get("with", {}).get("branch", "")).strip():
        problems.append("FR-015b: the hardened-push step names no branch")
    label = [s for s in act_steps if "stage:clarify" in (s.get("run") or "")]
    if len(label) != 1:
        problems.append("FR-015c: expected exactly one label-move step")
    elif "move_label == 'true'" not in str(label[0].get("if", "")):
        problems.append("FR-015c: the label move is not gated on the plan's move_label")
    status = [s for s in act_steps if "statuses/" in (s.get("run") or "")]
    if len(status) != 1:
        problems.append("FR-016: expected exactly one commit-status step")
    else:
        run = status[0]["run"]
        if 'context="spec-pr-review"' not in run:
            problems.append("FR-016: the status context is not spec-pr-review")
        if OTHER_CONTEXT in run:
            problems.append("FR-016: the status reuses spec 062's context")
        if "state=failure" not in run.split("if ")[0]:
            problems.append("FR-016: the status does not default to failure")
        if run.count("state=success") != 1 or 'VERDICT" = "ready for the owner"' not in run:
            problems.append("FR-016: success is reachable other than from 'ready for the owner'")
    select = jobs.get("select", {})
    if "WING_COMMANDER_SPEC_REVIEW_PAUSED" not in str(select):
        problems.append("FR-020: the kill switch is not read in the select job")
    # FR-018/FR-019: select reads the persisted stop note and the snapshot
    # carries it, so a stopped PR is skipped before any billable step.
    select_run = "\n".join(s.get("run") or "" for s in select.get("steps", []))
    if "spec-pr-review-stopped" not in select_run or "stop_note" not in select_run:
        problems.append("FR-018: the select job does not read the stop note")
    if "wc_convergence.py rearmed" not in select_run:
        problems.append("FR-019: select does not re-arm through wc_convergence.py rearmed")
    for s in act_steps:
        if "spec-pr-review-stopped" in str(s.get("with", {}).get("body", "")):
            break
    else:
        problems.append("FR-018: no act step records the stop note")
    if "claude-opus-5-5" not in text or "WING_COMMANDER_SPEC_REVIEW_MODEL" not in text:
        problems.append("FR-008: reviewer model is not the variable with its default")
    if "WING_COMMANDER_SPEC_REVIEW_EFFORT" not in text or ":-high" not in text:
        problems.append("FR-008: reviewer effort is not the variable with its default")
    return problems


def self_test(text):
    mutations = {
        "an APPROVE event": text + "\n# event=APPROVE\n",
        "a workflow_call trigger": text.replace("  workflow_dispatch:", "  workflow_call:\n  workflow_dispatch:", 1),
        "a bare git push": text.replace("echo \"sha=$(git rev-parse HEAD)\" >> \"$GITHUB_OUTPUT\"",
                                        "git push origin HEAD", 1),
        "an ungated label move": text.replace("steps.plan.outputs.move_label == 'true'", "always()", 1),
        "the other status context": text.replace('context="spec-pr-review"', 'context="lifecycle-review-gate"', 1),
        "no kill switch read": text.replace("WING_COMMANDER_SPEC_REVIEW_PAUSED", "SOMETHING_ELSE"),
        "select ignoring the stop note": text.replace("<!-- spec-pr-review-stopped head=(?<sha>",
                                                      "<!-- spec-pr-review-other head=(?<sha>", 1),
        "select without the rearm check": text.replace("wc_convergence.py rearmed", "wc_convergence.py other"),
        "no act step recording the stop note": text.replace("<!-- spec-pr-review-stopped head={0}",
                                                            "<!-- spec-pr-review-x head={0}", 1),
    }
    bad = 0
    for label, mutated in mutations.items():
        if mutated == text or not check(mutated):
            print("self-test FAIL: %s was not detected" % label)
            bad += 1
        else:
            print("Mutation OK -- %s" % label)
    return bad


def main():
    with open(WORKFLOW, encoding="utf-8") as fh:
        text = fh.read()
    problems = check(text)
    for p in problems:
        print("::error::Gate 158: %s" % p)
    if "--self-test" in sys.argv:
        problems += ["self-test"] * self_test(text)
    if problems:
        print("Gate 158: %d failure(s)." % len(problems))
        return 1
    print("Gate 158: spec-pr-review.yml is wired per specs/122; 0 failure(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
