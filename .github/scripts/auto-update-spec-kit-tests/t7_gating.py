"""Job-level `if:` gating: evaluate the REAL expressions from the workflow.

Expressions are read out of the YAML (never retyped), translated to Python with
a faithful model of the Actions subset in use (==, !=, &&, ||, parens,
always(), contains(fromJSON(...), x)), and driven through each quickstart
scenario's job-result matrix. GitHub semantics modelled:
  * a skipped/never-run job's `needs.X.outputs.Y` renders as the empty string
  * an unset `steps.X.outputs.Y` (a step that has not run yet) also renders
    as the empty string, the same way
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


def load_step_ifs(path, job):
    """[(step name, if-expression)] for one job, in file order."""
    doc = yaml.safe_load(open(path, encoding="utf-8"))
    return [(s.get("name", "<unnamed>"), str(s.get("if", "")).strip())
            for s in doc["jobs"][job]["steps"]]


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

    e = re.sub(r"\b(inputs|needs|vars|steps)\.[A-Za-z0-9_.\-]+", lambda m: repr(lookup(m.group(0), ctx)), e)
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


def step_scenario(label, steps, ctx, expected_running):
    """Assert the EXACT set of steps that run, by name.

    Job-level gating alone is not enough for `act`: it is the one job with
    four mutually exclusive arms (rollback / bump / verify-failed /
    prepare-failed) selected entirely by step `if:`. Widening the job gate
    to admit a new arm silently admits it to every pre-existing step too,
    and the failure mode is ugly — download-artifact looking for a bundle a
    failed prepare never uploaded, or a callout posting to an empty issue
    number. Asserting the exact set (not a subset) also means a step added
    later with no `if:` fails here rather than firing on every arm.
    """
    global PASS, FAIL
    print("\n--- %s ---" % label)
    got = {name for name, expr in steps if evaluate(expr, ctx)}
    want = set(expected_running)
    if got == want:
        PASS += 1
        print("    ok   %d step(s) run: %s" % (len(got), ", ".join(sorted(got))))
    else:
        FAIL += 1
        FAILED.append(label)
        print("    FAIL step set mismatch")
        for extra in sorted(got - want):
            print("         unexpectedly RUNS: %s" % extra)
        for missing in sorted(want - got):
            print("         unexpectedly SKIPPED: %s" % missing)


# Steps with no `if:` at all — the shared bootstrap every act arm needs.
ACT_ALWAYS = [
    "Checkout consumer repository (bootstrap, default token)",
    "Resolve pipeline ref",
    "Checkout pipeline repository (shared composite actions)",
    "Wing Commander context",
    "Resolve default branch",
]


def act_steps(ifs_steps, ctx, arm):
    step_scenario("act steps — %s" % arm, ifs_steps, ctx, ACT_ALWAYS + {
        "prepare failed": [
            "Label the issue as failed (prepare failed)",
            "Comment the prepare failure on the issue",
            "Apply the failed label (prepare failed)",
        ],
        "verify failed": [
            "Download prepared branch bundle",
            "Fetch prepared branch from bundle",
            "Label the issue as failed",
            "Comment verification failure on the issue",
            "Apply the failed label",
        ],
        "verify passed": [
            "Download prepared branch bundle",
            "Fetch prepared branch from bundle",
            "Open version-bump PR",
        ],
        "rollback": ["Rollback (health-check failed)"],
    }[arm])


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

    # ---- 035-auto-update-pr-guard: guard-skip outcome routing ----------
    scenario("guard-skip: no prepare, no verify, no act (US1, same 'route to a human' matrix as ambiguous-options)", ifs, {
        "inputs.trigger": "scheduled",
        "needs.health-check.result": "success", "needs.health-check.outputs.pinned-ok": "true",
        "needs.detect.result": "success", "needs.detect.outputs.newer": "true",
        "needs.settle.result": "success", "needs.settle.outputs.settled": "true",
        "needs.comment-reply.result": "skipped",
        "needs.evaluate-path.result": "success", "needs.evaluate-path.outputs.outcome": "guard-skip",
        "needs.prepare.result": "skipped", "needs.verify.result": "skipped",
    }, {"evaluate-path": True, "prepare": False, "verify": False, "act": False})

    scenario("no matching open PR: proceeds through prepare/verify/act exactly as clean-bump (US1 Acceptance #4)", ifs, {
        "inputs.trigger": "scheduled",
        "needs.health-check.result": "success", "needs.health-check.outputs.pinned-ok": "true",
        "needs.detect.result": "success", "needs.detect.outputs.newer": "true",
        "needs.settle.result": "success", "needs.settle.outputs.settled": "true",
        "needs.comment-reply.result": "skipped",
        "needs.evaluate-path.result": "success", "needs.evaluate-path.outputs.outcome": "clean-bump",
        "needs.prepare.result": "success", "needs.verify.result": "success",
    }, {"evaluate-path": True, "prepare": True, "verify": True, "act": True})

    # ---- evaluate-path's own guard step, at step level (US1, FR-004) ---
    # Job-level gating alone would not catch a regression that widens the
    # job's outcome switch but forgets the step-level `if:` — the guard
    # must suppress the judgment step ITSELF (FR-004), not just its
    # downstream outcome. Only the two billed steps are asserted here
    # (not the full step set act_steps() checks) because evaluate-path has
    # many always-run bootstrap steps with no `if:` of their own that are
    # irrelevant to this guard.
    ep_steps = load_step_ifs(STAGE, "evaluate-path")
    ep_billed = [(n, e) for n, e in ep_steps
                 if n in ("Fetch candidate release notes", "Decide upgrade path")]
    print("\nevaluate-path billed-step gates (verbatim from the workflow):")
    for name, expr in ep_billed:
        print("  %-32s if: %s" % (name, re.sub(r"\s+", " ", expr) or "(none)"))

    step_scenario("evaluate-path steps — guard fires: billed steps do not run", ep_billed, {
        "steps.entry.outputs.resumed": "false",
        "steps.guard.outputs.skip": "true",
    }, [])

    step_scenario("evaluate-path steps — no matching PR: billed steps run", ep_billed, {
        "steps.entry.outputs.resumed": "false",
        "steps.guard.outputs.skip": "false",
    }, ["Fetch candidate release notes", "Decide upgrade path"])

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

    # ---- prepare failure (#157 defect 1) -------------------------------
    # verify is gated on `prepare.result == 'success'`, so it stays skipped
    # here — that is correct and unchanged. What must NOT happen is act
    # skipping too: that was the silent-death path, where the lifecycle
    # issue kept reading "waiting for the patch stream to settle" forever.
    scenario("prepare FAILS (e.g. uvx/spec-kit CLI assumption wrong): act still reports", ifs, {
        "inputs.trigger": "scheduled",
        "needs.health-check.result": "success", "needs.health-check.outputs.pinned-ok": "true",
        "needs.detect.result": "success", "needs.detect.outputs.newer": "true",
        "needs.settle.result": "success", "needs.settle.outputs.settled": "true",
        "needs.comment-reply.result": "skipped",
        "needs.evaluate-path.result": "success", "needs.evaluate-path.outputs.outcome": "clean-bump",
        "needs.prepare.result": "failure", "needs.verify.result": "skipped",
    }, {"prepare": True, "verify": False, "act": True})

    # Same, reached through the resumed-reply re-entry rather than the
    # schedule: health-check is skipped there, so `pinned-ok` is the empty
    # string and act's rollback arm must not be what carries it.
    scenario("prepare FAILS after a resumed reply: act still reports", ifs, {
        "inputs.trigger": "comment-reply", "inputs.commenter-association": "OWNER",
        "inputs.commenter-id": "1", "inputs.issue-author-id": "1",
        "needs.health-check.result": "skipped", "needs.health-check.outputs.pinned-ok": "",
        "needs.detect.result": "skipped", "needs.settle.result": "skipped",
        "needs.comment-reply.result": "success", "needs.comment-reply.outputs.resumed": "true",
        "needs.evaluate-path.result": "success", "needs.evaluate-path.outputs.outcome": "clean-bump",
        "needs.prepare.result": "failure", "needs.verify.result": "skipped",
    }, {"evaluate-path": True, "prepare": True, "verify": False, "act": True})

    # prepare CANCELLED is deliberately still a no-act path: a cancellation
    # is a human stopping the run, not an outcome the issue needs narrating.
    scenario("prepare CANCELLED: act does not run", ifs, {
        "inputs.trigger": "scheduled",
        "needs.health-check.result": "success", "needs.health-check.outputs.pinned-ok": "true",
        "needs.detect.result": "success", "needs.detect.outputs.newer": "true",
        "needs.settle.result": "success", "needs.settle.outputs.settled": "true",
        "needs.comment-reply.result": "skipped",
        "needs.evaluate-path.result": "success", "needs.evaluate-path.outputs.outcome": "clean-bump",
        "needs.prepare.result": "cancelled", "needs.verify.result": "skipped",
    }, {"prepare": True, "verify": False, "act": False})

    # ---- e2e-stage / verify gating (US3/US4, T027) ----------------------
    scenario("e2e-stage runs for a minor bump (contract's e2e-stage job)", ifs, {
        "needs.prepare.result": "success", "needs.prepare.outputs.release-type": "minor",
    }, {"e2e-stage": True})

    scenario("e2e-stage runs for a major bump", ifs, {
        "needs.prepare.result": "success", "needs.prepare.outputs.release-type": "major",
    }, {"e2e-stage": True})

    scenario("e2e-stage does NOT run for a patch bump (Scenario 8, Edge Case)", ifs, {
        "needs.prepare.result": "success", "needs.prepare.outputs.release-type": "patch",
    }, {"e2e-stage": False})

    # T004's always(): verify must still run — and read needs.e2e-stage.* —
    # even when e2e-stage itself failed or timed out, as long as prepare
    # succeeded. Without always(), GitHub's implicit "skip if any needed
    # job did not succeed" would skip verify here, silently dropping the
    # combine step's fourth gating check.
    scenario("verify still runs when e2e-stage fails, as long as prepare succeeded (T004)", ifs, {
        "needs.prepare.result": "success", "needs.e2e-stage.result": "failure",
    }, {"verify": True})

    scenario("verify does not run when prepare itself did not succeed", ifs, {
        "needs.prepare.result": "failure", "needs.e2e-stage.result": "skipped",
    }, {"verify": False})

    # ---- the scratch-repository lifecycle jobs must NOT come back --------
    # There is no issue-closed job and no reap-scratch-repos job: the scratch
    # repository is pre-created and never deleted by this feature, because a
    # GitHub App installation token cannot create a repository on a user
    # account, and the Administration rights that would let it delete one
    # would also let every stage in this pipeline delete THIS repository.
    # Asserted structurally — a re-added job would otherwise sit here
    # ungated and unnoticed until it ran.
    wrap_doc = yaml.safe_load(open(WRAP, encoding="utf-8"))
    trigger_expr = str(wrap_doc["jobs"]["auto-update-spec-kit"]["with"]["trigger"])
    # YAML 1.1 (what safe_load implements) resolves the bare key `on` to the
    # boolean True, so the trigger block is NOT under the string "on".
    wrap_on = wrap_doc.get("on", wrap_doc.get(True)) or {}
    print("\n--- no repository-lifecycle jobs, no issues trigger ---")
    global PASS, FAIL
    for job in ("issue-closed", "reap-scratch-repos"):
        if job not in ifs:
            PASS += 1
            print("    ok   no %s job" % job)
        else:
            FAIL += 1
            FAILED.append("job %s is back" % job)
            print("    FAIL %s job is back: if: %s" % (job, ifs[job]))
    if "issues" not in wrap_on:
        PASS += 1
        print("    ok   wrapper does not subscribe to the issues event")
    else:
        FAIL += 1
        FAILED.append("wrapper on.issues")
        print("    FAIL wrapper still subscribes to issues: %r" % (wrap_on["issues"],))
    if "issue-closed" not in trigger_expr:
        PASS += 1
        print("    ok   trigger expression resolves no issue-closed arm")
    else:
        FAIL += 1
        FAILED.append("wrapper trigger: issue-closed arm")
        print("    FAIL trigger expression still has an issue-closed arm:\n         %s"
              % re.sub(r"\s+", " ", trigger_expr))

    # ---- act's four arms, at step level --------------------------------
    act = load_step_ifs(STAGE, "act")
    print("\nact step gates (verbatim from the workflow):")
    for name, expr in act:
        print("  %-48s if: %s" % (name[:48], re.sub(r"\s+", " ", expr) or "(none)"))

    act_steps(act, {
        "needs.health-check.outputs.pinned-ok": "true",
        "needs.prepare.result": "failure", "needs.verify.result": "skipped",
        "needs.verify.outputs.passed": "",
    }, "prepare failed")

    act_steps(act, {
        "needs.health-check.outputs.pinned-ok": "true",
        "needs.prepare.result": "success", "needs.verify.result": "success",
        "needs.verify.outputs.passed": "false",
    }, "verify failed")

    act_steps(act, {
        "needs.health-check.outputs.pinned-ok": "true",
        "needs.prepare.result": "success", "needs.verify.result": "success",
        "needs.verify.outputs.passed": "true",
    }, "verify passed")

    # health-check failure short-circuits the whole chain, so prepare is
    # skipped rather than successful — the rollback arm must not depend on
    # any prepare-derived state.
    act_steps(act, {
        "needs.health-check.outputs.pinned-ok": "false",
        "needs.prepare.result": "skipped", "needs.verify.result": "skipped",
        "needs.verify.outputs.passed": "",
    }, "rollback")

    # ---- wrapper pause kill-switch -------------------------------------
    # (PASS/FAIL are already declared global above, at the first assignment
    # in this function — a second declaration after them is a SyntaxError.)
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
