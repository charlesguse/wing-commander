#!/usr/bin/env python3
"""Gate 62 - plan.yml and tasks.yml report the run's cost on every auto-mode
hand-off.

WHY THIS EXISTS
---------------
Both stages compute `steps.cost-line.outputs.line` unconditionally (whenever
their agent step ran) and then hand off to the next stage with
`gh workflow run` when `inputs.next-workflow` is configured (auto mode). That
hand-off step posted nothing to the lifecycle issue -- the cost line was only
ever consumed inside the SAME step's other branch, the one that fires when
`next-workflow` is empty (standalone mode). So every auto-mode plan or tasks
run that dispatched its successor cleanly reported none of its cost (#377):
plan run 35177818925 cost $2.27 and said nothing about it on #362, and the
same held for every auto-mode plan/tasks run once the watchdog's cost-report
collector stopped silently erroring on this shape (#376/#378).

The fix mirrors #366's fix in clarify.yml for the analogous gap (the agent's
early-STOP path there): a small info callout, gated on the hand-off having
actually happened, carrying the cost line.

WHAT THIS CHECKS
----------------
For each of plan.yml / tasks.yml:

  * the dispatch step ("Dispatch tasks/implement stage (auto)") carries
    `id: dispatch-auto` and its `run:` emits `dispatched=true` right after
    the `gh workflow run` call that only executes when next-workflow is
    configured;
  * a sibling step ("Report cost of an auto-mode hand-off") exists, is
    gated on `steps.dispatch-auto.outputs.dispatched == 'true'` (so it can
    never double-post alongside the standalone-mode comment the dispatch
    step already posts on the OTHER branch) and on auto mode, and posts via
    the wing-commander-callout composite with the cost line as its body.

Self-test (--self-test): loads the real shipped steps, then reintroduces
each way this could regress -- the step missing entirely, the id dropped,
the output never emitted, either half of the gating conjunct stripped, the
cost line dropped from the body, and the composite swapped out -- and
asserts each one fails. A gate that cannot fail proves nothing.

Usage: python3 .github/scripts/verify-plan-tasks-cost-line.py [--self-test]
"""
import copy
import io
import sys

import yaml

FILES = {
    ".github/workflows/plan.yml":
        ("Dispatch tasks stage (auto)", "Report cost of an auto-mode hand-off"),
    ".github/workflows/tasks.yml":
        ("Dispatch implement stage (auto)", "Report cost of an auto-mode hand-off"),
}

DISPATCHED_LINE = 'echo "dispatched=true" >> "$GITHUB_OUTPUT"'
DISPATCHED_COND = "steps.dispatch-auto.outputs.dispatched == 'true'"


def load_steps(path):
    """Map step name -> step dict for every job in the workflow at `path`."""
    wf = yaml.safe_load(io.open(path, encoding="utf-8")) or {}
    steps = {}
    for job in (wf.get("jobs") or {}).values():
        for step in (job or {}).get("steps") or []:
            name = (step or {}).get("name")
            if name and name not in steps:
                steps[name] = step
    return steps


def load_all():
    return {path: load_steps(path) for path in FILES}


def check_steps(path, steps, dispatch_name, report_name):
    """-> list of failure strings for one workflow's already-loaded steps."""
    failures = []

    dispatch = steps.get(dispatch_name)
    if dispatch is None:
        failures.append(f"{path}: missing step {dispatch_name!r}")
        return failures

    report = steps.get(report_name)
    if report is None:
        failures.append(
            f"{path}: missing step {report_name!r} -- the auto-mode "
            f"hand-off posts nothing to the lifecycle issue, so a run that "
            f"spent real money and dispatched cleanly reports none of it "
            f"(#377)")
        return failures

    if dispatch.get("id") != "dispatch-auto":
        failures.append(
            f"{path}: {dispatch_name!r} must carry id: dispatch-auto -- "
            f"{report_name!r} gates on that id's output to know whether a "
            f"hand-off actually happened")

    run = str(dispatch.get("run", ""))
    if DISPATCHED_LINE not in run:
        failures.append(
            f"{path}: {dispatch_name!r} never emits dispatched=true -- "
            f"{report_name!r} can never fire, so no auto-mode hand-off "
            f"ever reports its cost")

    cond = str(report.get("if", "") or "")
    if DISPATCHED_COND not in cond:
        failures.append(
            f"{path}: {report_name!r}'s if: does not require "
            f"{DISPATCHED_COND} -- without it the callout could fire on "
            f"every auto-mode run, including the standalone (next-workflow "
            f"empty) path that already posts its own comment, double-"
            f"posting the cost")
    if "mode == 'auto'" not in cond:
        failures.append(
            f"{path}: {report_name!r}'s if: does not require auto mode")

    body = str((report.get("with") or {}).get("body", ""))
    if "steps.cost-line.outputs.line" not in body:
        failures.append(
            f"{path}: {report_name!r} posts without the cost line -- a run "
            f"that spent money on the auto hand-off would report none of "
            f"it (#377)")

    uses = str(report.get("uses", ""))
    if "wing-commander-callout" not in uses:
        failures.append(
            f"{path}: {report_name!r} must post via the wing-commander-"
            f"callout composite, the single home for the action/info "
            f"comment convention (spec 019), like the over-budget callout "
            f"beside it")

    return failures


def scan(loaded):
    failures = []
    for path, (dispatch_name, report_name) in FILES.items():
        failures += check_steps(path, loaded[path], dispatch_name, report_name)
    return failures


# --------------------------------------------------------------------------
# Self-test -- mutations reintroducing each way this could regress.
# --------------------------------------------------------------------------
def mut_drop_report_step(loaded):
    for path, (_dispatch_name, report_name) in FILES.items():
        loaded[path].pop(report_name, None)


def mut_drop_id(loaded):
    for path, (dispatch_name, _report_name) in FILES.items():
        loaded[path][dispatch_name].pop("id", None)


def mut_drop_dispatched_emission(loaded):
    for path, (dispatch_name, _report_name) in FILES.items():
        step = loaded[path][dispatch_name]
        step["run"] = str(step["run"]).replace(DISPATCHED_LINE, "")


def mut_drop_dispatched_conjunct(loaded):
    for path, (_dispatch_name, report_name) in FILES.items():
        step = loaded[path][report_name]
        terms = [t.strip() for t in str(step["if"]).split("&&")]
        step["if"] = " && ".join(t for t in terms if DISPATCHED_COND not in t)


def mut_drop_mode_conjunct(loaded):
    for path, (_dispatch_name, report_name) in FILES.items():
        step = loaded[path][report_name]
        terms = [t.strip() for t in str(step["if"]).split("&&")]
        step["if"] = " && ".join(t for t in terms if "mode == 'auto'" not in t)


def mut_drop_cost_line(loaded):
    for path, (_dispatch_name, report_name) in FILES.items():
        loaded[path][report_name]["with"]["body"] = ""


def mut_swap_composite(loaded):
    for path, (_dispatch_name, report_name) in FILES.items():
        loaded[path][report_name]["uses"] = "actions/checkout@v4"


MUTATIONS = [
    ("the cost callout dropped entirely", mut_drop_report_step),
    ("the dispatch step's id: dispatch-auto dropped", mut_drop_id),
    ("the dispatch step no longer emits dispatched=true", mut_drop_dispatched_emission),
    ("the callout's gate on dispatched == 'true' stripped (double-post risk)",
     mut_drop_dispatched_conjunct),
    ("the callout's gate on auto mode stripped", mut_drop_mode_conjunct),
    ("the callout posting without the cost line", mut_drop_cost_line),
    ("the callout posting through a different action", mut_swap_composite),
]


def self_test():
    base = load_all()
    problems = []

    clean = scan(copy.deepcopy(base))
    if clean:
        problems.append("clean copy of the real tree FAILED: " + "; ".join(clean))

    for label, apply_mutation in MUTATIONS:
        mutated = copy.deepcopy(base)
        apply_mutation(mutated)
        if mutated == base:
            problems.append(f"mutation {label!r} changed nothing -- the code it "
                            f"edits was rewritten; update the mutation.")
            continue
        broke = scan(mutated)
        if not broke:
            problems.append(f"MUTATION SURVIVED -- reintroducing {label!r} broke "
                            f"nothing in this gate.")
        else:
            print(f"Mutation OK -- {label}: {len(broke)} assertion(s) fail.")

    for p in problems:
        print(f"::error::Gate 62 self-test: {p}")
    if problems:
        return 1
    print("Gate 62 self-test: clean tree passes; each mutation fails.")
    return 0


def main(argv):
    if "--self-test" in argv:
        return self_test()
    failures = scan(load_all())
    for f in failures:
        print(f"::error::Gate 62: {f}")
    print(f"Gate 62: plan/tasks auto-mode cost-line reporting; "
          f"{len(failures)} failure(s).")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
