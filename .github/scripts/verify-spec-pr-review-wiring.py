#!/usr/bin/env python3
"""Gate 188 -- spec-pr-review.yml is wired the way specs/122 requires.

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
  FR-019  the `select` job's checkout has full history (fetch-depth: 0),
          so the stop-note re-arm can diff the stopped head.
  FR-020  the kill-switch variable is read in the `select` job.
  FR-011  the stale notice is composed into the review body, never appended
          after it, so the round record stays last.
  FR-005  the review job's `outcome` is `failed` when the review POST did not
          succeed, so a round with no round record gets the failed marker.
  FR-028  the failed-attempt marker is written only for outcome `failed`
          (a re-check that stood down before any reviewer ran is not a
          failed attempt), and at the cap (spec_pr_review.py failed-cap,
          fed select's failed-attempts) the act job posts a hand-off, once
          per head: only from the round that reaches the cap, and only after
          that round's failed marker was recorded.
  FR-022  no workflow_call trigger (no input, secret or output surface).
  FR-023  the cost line comes from the metrics-summary composite; the
          formatter is not inlined.
  model/effort come from the two variables, with the stated defaults.
  #890    owner decisions 2026-11-26/27: the reviewer's prompt defines
          `in_scope` (true|false); the budget stop reads the decision
          module's in-scope count (one home, no recount in jq); out-of-scope
          findings get no question and are recorded for the plan stage by an
          App-authored callout gated on the plan's record_out_of_scope; the
          plan is told whether the round stopped (no announcement); and the
          stop note names the commit the round pushed, so that push does not
          re-arm it.

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
    # FR-019: the re-arm diffs the stopped head against main, which a
    # shallow checkout cannot do.
    first = next((s for s in select.get("steps", [])
                  if "actions/checkout" in str(s.get("uses", ""))), {})
    if str((first.get("with") or {}).get("fetch-depth")) != "0":
        problems.append("FR-019: the select job's checkout is shallow (needs fetch-depth: 0)")
    for s in act_steps:
        if "spec-pr-review-stopped" in str(s.get("with", {}).get("body", "")):
            break
    else:
        problems.append("FR-018: no act step records the stop note")
    review = jobs.get("review", {})
    review_steps = review.get("steps", [])
    ids = [s.get("id") for s in review_steps]
    compose_at = ids.index("compose-review") if "compose-review" in ids else None
    if compose_at is None or "stale" not in ids or ids.index("stale") > compose_at:
        problems.append("FR-011: the stale check does not run before the review body is composed")
    else:
        for s in review_steps[compose_at + 1:]:
            if re.search(r">>\s*\"?\$RUNNER_TEMP/spec-review-body\.md", s.get("run") or ""):
                problems.append("FR-011: %s appends to the review body after the round record" % s.get("name"))
        if "STALE_NOW" not in (review_steps[compose_at].get("run") or ""):
            problems.append("FR-011: the composed review body does not carry the stale notice")
    post = [s for s in review_steps if "wing-commander-post-review-comment" in str(s.get("uses", ""))]
    out = str((review.get("outputs") or {}).get("outcome", ""))
    if len(post) != 1 or not post[0].get("id") or \
            "steps.%s.outcome != 'success' && 'failed'" % post[0].get("id") not in out:
        problems.append("FR-005: the review outcome does not turn failed when the review POST fails")
    failed_body = [s for s in act_steps if "spec-pr-review-failed" in str(s.get("with", {}).get("body", ""))]
    if len(failed_body) != 1:
        problems.append("FR-028: expected exactly one step writing the failed-attempt marker")
    elif "needs.review.outputs.outcome == 'failed'" not in str(failed_body[0]["with"]["body"]):
        problems.append("FR-028: the failed-attempt marker is not gated on outcome 'failed'")
    cap = [s for s in act_steps if "spec_pr_review.py" in (s.get("run") or "")
           and re.search(r'(spec_pr_review\.py|\$\w+)"\s+failed-cap\b', s.get("run") or "")]
    if len(cap) != 1 or "needs.select.outputs.failed-attempts" not in str(cap[0].get("env", {})) \
            or "failed-attempts" not in str(select.get("outputs", {})):
        problems.append("FR-028: the act job does not run failed-cap on select's failed-attempts")
    else:
        handoff = [s for s in act_steps if "steps.%s.outputs.stop == 'true'" % cap[0].get("id") in str(s.get("if", ""))
                   and "wing-commander-callout" in str(s.get("uses", ""))]
        if not handoff:
            problems.append("FR-028: no hand-off is posted at the failed-attempt cap")
        elif not all("steps.%s.outputs.reached == 'true'" % cap[0].get("id") in str(s.get("if", "")) for s in handoff):
            problems.append("FR-028: the cap hand-off is not limited to the round that reaches the cap "
                            "(a dispatched retry of a capped head would post it again)")
        # The cap counts this round's failure, so it may act only once that
        # failure's marker is on the issue; otherwise select re-picks the
        # head and the next failure posts the hand-off a second time.
        if len(failed_body) == 1 and (not failed_body[0].get("id") or
                                      "steps.%s.outcome == 'success'" % failed_body[0]["id"] not in str(cap[0].get("if", ""))):
            problems.append("FR-028: the failed-cap check does not wait for this round's failed marker to be recorded")
    problems.extend(check_scope_and_stop(jobs))
    if "claude-opus-5-5" not in text or "WING_COMMANDER_SPEC_REVIEW_MODEL" not in text:
        problems.append("FR-008: reviewer model is not the variable with its default")
    if "WING_COMMANDER_SPEC_REVIEW_EFFORT" not in text or ":-high" not in text:
        problems.append("FR-008: reviewer effort is not the variable with its default")
    return problems


def check_scope_and_stop(jobs):
    problems = []
    review_steps = jobs.get("review", {}).get("steps", [])
    act_steps = jobs.get("act", {}).get("steps", [])
    by_id = {s.get("id"): s for s in review_steps + act_steps if s.get("id")}
    prompt = str((by_id.get("reviewer", {}).get("with") or {}).get("prompt", ""))
    if '"in_scope": true|false' not in prompt or "plan-level" not in prompt:
        problems.append("#890: the reviewer's prompt does not define in_scope as true|false")
    verdict_run = by_id.get("verdict", {}).get("run") or ""
    if "in-scope-count=" not in verdict_run or "in_scope_count" not in verdict_run:
        problems.append("#890: the verdict step does not output the module's in-scope count")
    stop = by_id.get("stop", {})
    if "steps.verdict.outputs.in-scope-count" not in str(stop.get("env", {})) \
            or re.search(r"jq\s+'length'", stop.get("run") or ""):
        problems.append("#890: the budget stop recounts findings instead of reading the in-scope count")
    plan = by_id.get("plan", {})
    if "needs.review.outputs.stop-reason" not in str(plan.get("env", {}).get("STOPPED", "")) \
            or "stopped: $stopped" not in (plan.get("run") or ""):
        problems.append("#890: plan-actions is not told whether the round stopped")
    if "in_scope: .in_scope" not in (plan.get("run") or ""):
        problems.append("#890: plan-actions is not given each finding's in_scope")
    record = [s for s in act_steps if "record_out_of_scope == 'true'" in str(s.get("if", ""))]
    if len(record) != 1 or "wing-commander-callout" not in str(record[0].get("uses", "")) \
            or "spec-review-out-of-scope.md" not in str(record[0].get("with", {}).get("body-file", "")):
        problems.append("#890: out-of-scope findings are not recorded by one App callout gated on record_out_of_scope")
    questions = [s for s in act_steps if "stage:clarify" in (s.get("run") or "")]
    if questions and 'select(.class == "owner-decision")' not in questions[0]["run"]:
        problems.append("#890: the questions step does not keep to owner-decision items")
    note = [s for s in act_steps if "spec-pr-review-stopped" in str(s.get("with", {}).get("body", ""))]
    if note and "steps.push.outcome == 'success' && steps.commit.outputs.sha" not in str(note[0]["with"]["body"]):
        problems.append("#890: the stop note does not name the commit the round pushed")
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
        "a shallow select checkout": text.replace("          fetch-depth: 0\n          persist-credentials: false\n\n      - name: Checkout this job's own trusted copy",
                                                  "          persist-credentials: false\n\n      - name: Checkout this job's own trusted copy", 1),
        "a stale notice appended after the round record": text.replace(
            "      - name: Post the review on the PR\n",
            "      - name: Late stale notice\n        run: printf 'x' >> \"$RUNNER_TEMP/spec-review-body.md\"\n\n"
            "      - name: Post the review on the PR\n", 1),
        "an outcome blind to the review POST": text.replace(
            "steps.post-review.outcome != 'success' && 'failed'", "false", 1),
        "a failed marker for a stood-down round": text.replace(
            "body: ${{ needs.review.outputs.outcome == 'failed' && format('<!-- spec-pr-review-failed",
            "body: ${{ needs.review.outputs.outcome != 'reviewed' && format('<!-- spec-pr-review-failed", 1),
        "no failed-cap check": text.replace('"$S" failed-cap', '"$S" verdict'),
        "no hand-off at the cap": text.replace("steps.failcap.outputs.stop == 'true'", "false", 1),
        "a cap hand-off on every failure past the cap": text.replace(
            " && steps.failcap.outputs.reached == 'true'", "", 1),
        "a cap check that ignores the failed marker's write": text.replace(
            " && steps.outcome-line.outcome == 'success'", "", 1),
        "a prompt without in_scope true|false": text.replace('"in_scope": true|false,', '"in_scope": true,', 1),
        "a budget stop that recounts findings": text.replace(
            '[ "${IN_SCOPE_COUNT:-1}" != "0" ]',
            '[ "$(jq ' + "'length'" + ' "$RUNNER_TEMP/spec-review-findings.json")" -gt 0 ]', 1),
        "a plan blind to the stop": text.replace("stopped: $stopped}", "stopped: false}", 1),
        "a plan blind to in_scope": text.replace("{in_scope: .in_scope}", "{}", 1),
        "no out-of-scope record": text.replace("steps.plan.outputs.record_out_of_scope == 'true'", "false", 1),
        "questions posted for every item": text.replace('select(.class == "owner-decision") |', '', 1),
        "a stop note on the reviewed head": text.replace(
            "steps.push.outcome == 'success' && steps.commit.outputs.sha || needs.select.outputs.head-sha",
            "needs.select.outputs.head-sha", 1),
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
        print("::error::Gate 188: %s" % p)
    if "--self-test" in sys.argv:
        problems += ["self-test"] * self_test(text)
    if problems:
        print("Gate 188: %d failure(s)." % len(problems))
        return 1
    print("Gate 188: spec-pr-review.yml is wired per specs/122; 0 failure(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
