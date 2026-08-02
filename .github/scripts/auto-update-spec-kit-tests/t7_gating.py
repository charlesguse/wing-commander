"""Job-level `if:` gating: evaluate the REAL expressions from the workflow.

Expressions are read out of the YAML (never retyped), translated to Python with
a faithful model of the Actions subset in use (==, !=, &&, ||, parens,
always(), contains(fromJSON(...), x)), and driven through each quickstart
scenario's job-result matrix. GitHub semantics modelled:
  * a skipped/never-run job's `needs.X.outputs.Y` renders as the empty string
  * `needs.X.result` is one of success | failure | cancelled | skipped
  * a job with a custom `if:` does NOT get the implicit success() check
"""
import os
import subprocess
import re
import sys

import yaml

REPO = subprocess.run(
    ["git", "-C", os.path.dirname(os.path.abspath(__file__)), "rev-parse", "--show-toplevel"],
    capture_output=True, text=True, check=True).stdout.strip()
STAGE = os.path.join(REPO, ".github", "workflows", "auto-update-spec-kit.yml")
WRAP = os.path.join(REPO, ".github", "workflows", "wing-commander-auto-update-spec-kit.yml")

PASS = FAIL = 0
FAILED = []


def load_ifs(path):
    doc = yaml.safe_load(open(path, encoding="utf-8"))
    return {name: str(job.get("if", "")).strip() for name, job in doc["jobs"].items()}


def evaluate(expr, ctx):
    """Translate the Actions expression subset to Python and evaluate it."""
    if not expr:
        return True  # no `if:` == runs (subject to needs succeeding)
    e = expr
    def _ref(name):
        return repr(lookup(name, ctx))

    e = re.sub(r"\balways\(\)", "True", e)
    # contains(fromJSON('[...]'), X) -> (X in [...])
    def _contains(m):
        return "(%s in %s)" % (_ref(m.group(2).strip()), m.group(1))
    e = re.sub(r"contains\(\s*fromJSON\('(\[[^)]*?\])'\)\s*,\s*([^)]+?)\s*\)", _contains, e)
    e = e.replace("&&", " and ").replace("||", " or ").replace("'", '"')

    e = re.sub(r"\b(inputs|needs|vars)\.[A-Za-z0-9_.\-]+", lambda m: repr(lookup(m.group(0), ctx)), e)
    return bool(eval(e, {"__builtins__": {}}, {}))


def lookup(ref, ctx):
    if ref in ctx:
        return ctx[ref]
    # unset needs.*.outputs.* / inputs.* render as empty string
    return ""


def scenario(label, ifs, ctx, expected):
    """expected: {job: True/False}"""
    global PASS, FAIL
    print("\n--- %s ---" % label)
    for job, want in expected.items():
        got = evaluate(ifs[job], ctx)
        ok = got == want
        if ok:
            PASS += 1
            print("    ok   %-14s runs=%-5s" % (job, got))
        else:
            FAIL += 1
            FAILED.append("%s / %s" % (label, job))
            print("    FAIL %-14s runs=%-5s expected %s\n         if: %s" % (job, got, want, ifs[job]))


def main():
    ifs = load_ifs(STAGE)
    wrap = load_ifs(WRAP)
    print("Expressions under test (verbatim from the workflow):")
    for k, v in ifs.items():
        print("  %-14s if: %s" % (k, re.sub(r"\s+", " ", v) or "(none)"))
    print("  %-14s if: %s" % ("[wrapper]", re.sub(r"\s+", " ", wrap["auto-update-spec-kit"])))

    # ---- Scenario 1: nothing newer ------------------------------------
    scenario("Scenario 1 — up to date: detect runs, everything after it stops", ifs, {
        "inputs.trigger": "scheduled",
        "needs.health-check.result": "success", "needs.health-check.outputs.pinned-ok": "true",
        "needs.detect.result": "success", "needs.detect.outputs.newer": "false",
        "needs.settle.result": "skipped", "needs.comment-reply.result": "skipped",
        "needs.evaluate-path.result": "skipped", "needs.prepare.result": "skipped",
        "needs.verify.result": "skipped",
    }, {"health-check": True, "detect": True, "settle": False, "evaluate-path": False,
        "prepare": False, "verify": False, "act": False, "pr-merged": False, "comment-reply": False})

    # ---- Scenario 2/3/4: settling -------------------------------------
    scenario("Scenario 2/4 — detected but not settled: stops before evaluate-path", ifs, {
        "inputs.trigger": "scheduled",
        "needs.health-check.result": "success", "needs.health-check.outputs.pinned-ok": "true",
        "needs.detect.result": "success", "needs.detect.outputs.newer": "true",
        "needs.settle.result": "success", "needs.settle.outputs.settled": "false",
        "needs.comment-reply.result": "skipped",
        "needs.evaluate-path.result": "skipped", "needs.prepare.result": "skipped",
        "needs.verify.result": "skipped",
    }, {"health-check": True, "detect": True, "settle": True, "evaluate-path": False,
        "prepare": False, "verify": False, "act": False})

    # ---- Scenario 5: clean bump all the way through --------------------
    scenario("Scenario 5 — settled clean-bump, verification passes: act opens the PR", ifs, {
        "inputs.trigger": "scheduled",
        "needs.health-check.result": "success", "needs.health-check.outputs.pinned-ok": "true",
        "needs.detect.result": "success", "needs.detect.outputs.newer": "true",
        "needs.settle.result": "success", "needs.settle.outputs.settled": "true",
        "needs.comment-reply.result": "skipped",
        "needs.evaluate-path.result": "success", "needs.evaluate-path.outputs.outcome": "clean-bump",
        "needs.prepare.result": "success", "needs.verify.result": "success",
    }, {"health-check": True, "detect": True, "settle": True, "evaluate-path": True,
        "prepare": True, "verify": True, "act": True})

    # ---- Scenario 6: verification fails --------------------------------
    scenario("Scenario 6 — verify job succeeds with passed=false: act runs the failure branch", ifs, {
        "inputs.trigger": "scheduled",
        "needs.health-check.result": "success", "needs.health-check.outputs.pinned-ok": "true",
        "needs.detect.result": "success", "needs.detect.outputs.newer": "true",
        "needs.settle.result": "success", "needs.settle.outputs.settled": "true",
        "needs.comment-reply.result": "skipped",
        "needs.evaluate-path.result": "success", "needs.evaluate-path.outputs.outcome": "clean-bump",
        "needs.prepare.result": "success", "needs.verify.result": "success",
        "needs.verify.outputs.passed": "false",
    }, {"prepare": True, "verify": True, "act": True})

    # ---- Scenario 8: health-check fails --------------------------------
    scenario("Scenario 8 — health-check fails: chain short-circuits straight to act's rollback", ifs, {
        "inputs.trigger": "scheduled",
        "needs.health-check.result": "success", "needs.health-check.outputs.pinned-ok": "false",
        "needs.detect.result": "skipped", "needs.settle.result": "skipped",
        "needs.comment-reply.result": "skipped", "needs.evaluate-path.result": "skipped",
        "needs.prepare.result": "skipped", "needs.verify.result": "skipped",
    }, {"health-check": True, "detect": False, "settle": False, "evaluate-path": False,
        "prepare": False, "verify": False, "act": True})

    # ---- Scenario 12: ambiguous options --------------------------------
    scenario("Scenario 12 — ambiguous-options: no prepare, no verify, no act (no silent adoption)", ifs, {
        "inputs.trigger": "scheduled",
        "needs.health-check.result": "success", "needs.health-check.outputs.pinned-ok": "true",
        "needs.detect.result": "success", "needs.detect.outputs.newer": "true",
        "needs.settle.result": "success", "needs.settle.outputs.settled": "true",
        "needs.comment-reply.result": "skipped",
        "needs.evaluate-path.result": "success", "needs.evaluate-path.outputs.outcome": "ambiguous-options",
        "needs.prepare.result": "skipped", "needs.verify.result": "skipped",
    }, {"evaluate-path": True, "prepare": False, "verify": False, "act": False})

    scenario("needs-migration — routed to a human, nothing prepared or acted on", ifs, {
        "inputs.trigger": "scheduled",
        "needs.health-check.result": "success", "needs.health-check.outputs.pinned-ok": "true",
        "needs.detect.result": "success", "needs.detect.outputs.newer": "true",
        "needs.settle.result": "success", "needs.settle.outputs.settled": "true",
        "needs.comment-reply.result": "skipped",
        "needs.evaluate-path.result": "success", "needs.evaluate-path.outputs.outcome": "needs-migration",
        "needs.prepare.result": "skipped", "needs.verify.result": "skipped",
    }, {"prepare": False, "verify": False, "act": False})

    # ---- Scenario 9: pr-merged ----------------------------------------
    scenario("Scenario 9 — merged PR", ifs, {
        "inputs.trigger": "pr-merged", "inputs.pr-merged": True,
        "needs.health-check.result": "skipped", "needs.verify.result": "skipped",
        "needs.settle.result": "skipped", "needs.comment-reply.result": "skipped",
        "needs.detect.result": "skipped", "needs.evaluate-path.result": "skipped",
        "needs.prepare.result": "skipped",
    }, {"pr-merged": True, "health-check": False, "detect": False, "act": False, "comment-reply": False})

    scenario("Scenario 9b — PR closed WITHOUT merging: pr-merged does not run", ifs, {
        "inputs.trigger": "pr-merged", "inputs.pr-merged": False,
        "needs.health-check.result": "skipped", "needs.verify.result": "skipped",
        "needs.settle.result": "skipped", "needs.comment-reply.result": "skipped",
        "needs.detect.result": "skipped", "needs.evaluate-path.result": "skipped",
        "needs.prepare.result": "skipped",
    }, {"pr-merged": False, "act": False})

    # ---- Scenario 13: commenter verification ---------------------------
    base_cr = {
        "inputs.trigger": "comment-reply",
        "needs.health-check.result": "skipped", "needs.detect.result": "skipped",
        "needs.settle.result": "skipped", "needs.evaluate-path.result": "skipped",
        "needs.prepare.result": "skipped", "needs.verify.result": "skipped",
        "needs.comment-reply.result": "skipped",
    }
    for assoc, cid, aid, want, label in [
        ("OWNER", "1", "1", True, "OWNER"),
        ("MEMBER", "9", "1", True, "MEMBER"),
        ("COLLABORATOR", "9", "1", True, "COLLABORATOR"),
        ("NONE", "7", "7", True, "non-maintainer but IS the issue author"),
        ("NONE", "9", "1", False, "drive-by NONE"),
        ("CONTRIBUTOR", "9", "1", False, "CONTRIBUTOR"),
        ("FIRST_TIME_CONTRIBUTOR", "9", "1", False, "FIRST_TIME_CONTRIBUTOR"),
    ]:
        ctx = dict(base_cr, **{"inputs.commenter-association": assoc,
                               "inputs.commenter-id": cid, "inputs.issue-author-id": aid})
        scenario("Scenario 13 — commenter=%s" % label, ifs, ctx, {"comment-reply": want})

    # ---- Scenario 13 resume re-entry -----------------------------------
    scenario("Scenario 13 — verified reply resumes evaluate-path -> prepare -> verify -> act", ifs, {
        "inputs.trigger": "comment-reply", "inputs.commenter-association": "OWNER",
        "inputs.commenter-id": "1", "inputs.issue-author-id": "1",
        "needs.health-check.result": "skipped", "needs.health-check.outputs.pinned-ok": "",
        "needs.detect.result": "skipped", "needs.settle.result": "skipped",
        "needs.comment-reply.result": "success", "needs.comment-reply.outputs.resumed": "true",
        "needs.evaluate-path.result": "success", "needs.evaluate-path.outputs.outcome": "clean-bump",
        "needs.prepare.result": "success", "needs.verify.result": "success",
    }, {"comment-reply": True, "evaluate-path": True, "prepare": True, "verify": True, "act": True})

    scenario("Scenario 13b — unrecognized reply: resumed!=true, chain does not re-enter", ifs, {
        "inputs.trigger": "comment-reply", "inputs.commenter-association": "OWNER",
        "inputs.commenter-id": "1", "inputs.issue-author-id": "1",
        "needs.health-check.result": "skipped", "needs.settle.result": "skipped",
        "needs.comment-reply.result": "success", "needs.comment-reply.outputs.resumed": "",
        "needs.evaluate-path.result": "skipped", "needs.prepare.result": "skipped",
        "needs.verify.result": "skipped",
    }, {"comment-reply": True, "evaluate-path": False, "prepare": False, "act": False})

    # ---- prepare failure -----------------------------------------------
    scenario("prepare FAILS (e.g. uvx/spec-kit CLI assumption wrong)", ifs, {
        "inputs.trigger": "scheduled",
        "needs.health-check.result": "success", "needs.health-check.outputs.pinned-ok": "true",
        "needs.detect.result": "success", "needs.detect.outputs.newer": "true",
        "needs.settle.result": "success", "needs.settle.outputs.settled": "true",
        "needs.comment-reply.result": "skipped",
        "needs.evaluate-path.result": "success", "needs.evaluate-path.outputs.outcome": "clean-bump",
        "needs.prepare.result": "failure", "needs.verify.result": "skipped",
    }, {"prepare": True, "verify": False, "act": False})

    # ---- wrapper pause kill-switch -------------------------------------
    global PASS, FAIL
    print("\n--- wrapper pause kill-switch ---")
    for val, want in [("true", False), ("false", True), ("", True)]:
        got = evaluate(wrap["auto-update-spec-kit"],
                       {"vars.WING_COMMANDER_AUTO_UPDATE_SPEC_KIT_PAUSED": val})
        if got == want:
            PASS += 1
            print("    ok   PAUSED=%-6r runs=%s" % (val, got))
        else:
            FAIL += 1
            FAILED.append("pause=%r" % val)
            print("    FAIL PAUSED=%r runs=%s expected %s" % (val, got, want))

    print("\n==================== T7 job gating ====================")
    print("passed: %d   failed: %d" % (PASS, FAIL))
    for f in FAILED:
        print("  failing: %s" % f)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
