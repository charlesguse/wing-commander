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
Structurally, for each of plan.yml / tasks.yml: the dispatch step carries
`id: dispatch-auto`; a sibling callout step ("Report cost of an auto-mode
hand-off") exists, is gated on `steps.dispatch-auto.outputs.dispatched ==
'true'` and on auto mode, and posts via wing-commander-callout with the cost
line as its body.

Behaviorally: the dispatch step's shipped `run:` block is EXECUTED (never a
copy -- gate 5 exists because a copy sat green for weeks checking a filter
that did not ship), via wc_shell_harness.run_step, against a `gh` stubbed to
log its argv rather than call the network. Two scenarios:

  * next-workflow empty (standalone): `dispatched` must NOT be `true` (else
    the callout below would fire beside the standalone comment this same
    branch posts, double-reporting the cost with a summary -- "was
    dispatched automatically" -- that is false on this path); `gh` must have
    been called as `issue comment ...`, and one of its arguments must carry
    the cost line.
  * next-workflow set: `dispatched` must be `true` (else the callout can
    never fire and no auto-mode hand-off ever reports its cost); `gh` must
    have been called as `workflow run ...`, and NOT as `issue comment ...`
    (a stray comment here would double-post once the callout also fires).

A purely static check of "does the string `dispatched=true` appear in the
run: block" cannot tell a correctly-gated emission from the same line
hoisted above the branch (which would pass a string-presence check while
failing the first scenario above), and cannot tell a `$COST_LINE` reference
from one silently blanked -- both defects were found in review of this gate
before it shipped (b81d818's review). Running the step is what closes the
gap.

Self-test (--self-test): loads the real shipped steps, then reintroduces
each way this could regress -- the callout step missing entirely, the id
dropped, either half of its `if:` conjunct stripped, its cost line dropped
from `with.body`, its `uses:` swapped, the dispatch step's `dispatched=true`
emission hoisted above the branch (the double-post regression), and the
standalone comment's `$COST_LINE` blanked -- and asserts each one fails. A
gate that cannot fail proves nothing.

Usage: python3 .github/scripts/verify-plan-tasks-cost-line.py [--self-test]
Requires: bash (same prerequisites every other shell-harness gate needs).
"""
import copy
import io
import os
import sys
import tempfile

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_shell_harness import resolve_bash, run_step, use_utf8_stdout  # noqa: E402

FILES = {
    ".github/workflows/plan.yml":
        ("Dispatch tasks stage (auto)", "Report cost of an auto-mode hand-off"),
    ".github/workflows/tasks.yml":
        ("Dispatch implement stage (auto)", "Report cost of an auto-mode hand-off"),
}

DISPATCHED_COND = "steps.dispatch-auto.outputs.dispatched == 'true'"
COST_SENTINEL = "**Cost**: $9.99 GATE62-SENTINEL"
NEXT_WORKFLOW_SET = "some-other-stage.yml"

BASH = None


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


# --------------------------------------------------------------------------
# Structural checks -- facts a `uses:` composite step can't be executed to
# prove, so they stay static.
# --------------------------------------------------------------------------
def check_structure(path, dispatch, report, report_name):
    failures = []

    if dispatch.get("id") != "dispatch-auto":
        failures.append(
            f"{path}: the dispatch step must carry id: dispatch-auto -- "
            f"{report_name!r} gates on that id's output to know whether a "
            f"hand-off actually happened")

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


# --------------------------------------------------------------------------
# Behavioral checks -- execute the shipped dispatch step against a stubbed
# `gh` that logs its argv instead of calling the network.
# --------------------------------------------------------------------------
GH_STUB = (
    '#!/bin/sh\n'
    'n=$(cat "$GH_CALL_COUNT" 2>/dev/null || echo 0)\n'
    'n=$((n + 1))\n'
    'echo "$n" > "$GH_CALL_COUNT"\n'
    'for a in "$@"; do\n'
    '  printf \'%s\\0\' "$a" >> "$GH_CALL_DIR/call-$n.args"\n'
    'done\n'
    'exit 0\n'
)


def _read_calls(call_dir, count):
    """-> [[arg, ...], ...], one entry per `gh` invocation, 1-indexed."""
    calls = []
    for i in range(1, count + 1):
        p = os.path.join(call_dir, f"call-{i}.args")
        if not os.path.isfile(p):
            calls.append([])
            continue
        with open(p, "rb") as fh:
            raw = fh.read()
        parts = raw.split(b"\x00")
        if parts and parts[-1] == b"":
            parts = parts[:-1]
        calls.append([part.decode("utf-8", errors="replace") for part in parts])
    return calls


def run_dispatch(dispatch, next_workflow, root):
    """Execute the shipped dispatch step's run: block against a stubbed
    `gh`. -> (rc, output, outputs, calls)."""
    workdir = tempfile.mkdtemp(dir=root)
    runner_temp = os.path.join(workdir, "runner_temp")
    bindir = os.path.join(workdir, "bin")
    call_dir = os.path.join(workdir, "calls")
    call_count_file = os.path.join(workdir, "gh_call_count")
    os.makedirs(runner_temp, exist_ok=True)
    os.makedirs(bindir, exist_ok=True)
    os.makedirs(call_dir, exist_ok=True)
    open(call_count_file, "w").close()
    with open(os.path.join(bindir, "gh"), "w", encoding="utf-8",
              newline="\n") as fh:
        fh.write(GH_STUB)
    os.chmod(os.path.join(bindir, "gh"), 0o755)

    # Every key the shipped step's env: block declares gets a harmless
    # placeholder; NEXT_WORKFLOW and COST_LINE (and ISSUE, which gates
    # whether the standalone branch posts at all) get values this harness
    # actually cares about.
    env = {k: f"test-{k.lower()}" for k in (dispatch.get("env") or {})}
    env["NEXT_WORKFLOW"] = next_workflow
    if "COST_LINE" in env:
        env["COST_LINE"] = COST_SENTINEL
    if "ISSUE" in env:
        env["ISSUE"] = "999"
    env["GH_CALL_COUNT"] = call_count_file
    env["GH_CALL_DIR"] = call_dir
    env["PATH"] = bindir + os.pathsep + os.environ["PATH"]

    rc, out, outputs, _ = run_step(BASH, str(dispatch["run"]), workdir, env,
                                   runner_temp)
    with open(call_count_file, encoding="utf-8") as fh:
        raw = fh.read().strip()
    calls = _read_calls(call_dir, int(raw) if raw else 0)
    return rc, out, outputs, calls


def _calls_matching(calls, *argv_prefix):
    return [c for c in calls if list(c[:len(argv_prefix)]) == list(argv_prefix)]


def check_behavior(path, dispatch, report_name, root):
    failures = []

    # -- standalone (next-workflow empty): must post the comment, must NOT
    # emit dispatched=true. --
    rc, out, outputs, calls = run_dispatch(dispatch, "", root)
    if rc != 0:
        failures.append(f"{path}: the dispatch step exited {rc} on the "
                        f"standalone (empty next-workflow) path:\n{out}")
    if outputs.get("dispatched") == "true":
        failures.append(
            f"{path}: the dispatch step emits dispatched=true on the "
            f"standalone path -- {report_name!r} would then fire beside "
            f"the standalone-mode comment this same branch already posts, "
            f"double-posting the cost with a summary that falsely claims "
            f"the hand-off was dispatched")
    comment_calls = _calls_matching(calls, "issue", "comment")
    if not comment_calls:
        failures.append(f"{path}: the dispatch step never called "
                        f"`gh issue comment` on the standalone path "
                        f"(got calls: {calls!r})")
    elif not any(COST_SENTINEL in arg for c in comment_calls for arg in c):
        failures.append(
            f"{path}: the standalone-mode comment does not carry the cost "
            f"line -- a run that spent money and found no next-workflow "
            f"configured would report none of it (#377)")

    # -- next-workflow set: must dispatch, must emit dispatched=true, must
    # NOT also post the standalone comment. --
    rc, out, outputs, calls = run_dispatch(dispatch, NEXT_WORKFLOW_SET, root)
    if rc != 0:
        failures.append(f"{path}: the dispatch step exited {rc} when "
                        f"next-workflow was configured:\n{out}")
    if outputs.get("dispatched") != "true":
        failures.append(
            f"{path}: the dispatch step does not emit dispatched=true when "
            f"it actually calls `gh workflow run` -- {report_name!r} can "
            f"never fire, so no auto-mode hand-off ever reports its cost "
            f"(#377)")
    if not _calls_matching(calls, "workflow", "run"):
        failures.append(f"{path}: the dispatch step never called "
                        f"`gh workflow run` with next-workflow configured "
                        f"(got calls: {calls!r})")
    if _calls_matching(calls, "issue", "comment"):
        failures.append(
            f"{path}: the dispatch step ALSO called `gh issue comment` "
            f"while dispatching -- that would double-post alongside "
            f"{report_name!r} once it fires")

    return failures


def scan(loaded, root):
    failures = []
    for path, (dispatch_name, report_name) in FILES.items():
        steps = loaded[path]
        dispatch = steps.get(dispatch_name)
        if dispatch is None:
            failures.append(f"{path}: missing step {dispatch_name!r}")
            continue
        report = steps.get(report_name)
        if report is None:
            failures.append(
                f"{path}: missing step {report_name!r} -- the auto-mode "
                f"hand-off posts nothing to the lifecycle issue, so a run "
                f"that spent real money and dispatched cleanly reports "
                f"none of it (#377)")
            continue
        failures += check_structure(path, dispatch, report, report_name)
        failures += check_behavior(path, dispatch, report_name, root)
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


def mut_hoist_dispatched(loaded):
    """b81d818's review, finding 1: `dispatched=true` moved above the
    branch fires it on the standalone path too -- a pure string-presence
    check cannot see this, only executing the step can."""
    line = 'echo "dispatched=true" >> "$GITHUB_OUTPUT"'
    marker = 'if [ -z "$NEXT_WORKFLOW" ]; then'
    for path, (dispatch_name, _report_name) in FILES.items():
        step = loaded[path][dispatch_name]
        run = str(step["run"])
        assert line in run and marker in run, (path, "fixture assumption broken")
        step["run"] = run.replace(line, "", 1).replace(marker, line + "\n" + marker, 1)


def mut_drop_standalone_cost_line(loaded):
    """b81d818's review, finding 2: the standalone comment's $COST_LINE
    silently blanked -- nothing but executing the step catches this."""
    for path, (dispatch_name, _report_name) in FILES.items():
        step = loaded[path][dispatch_name]
        run = str(step["run"])
        assert '"$COST_LINE"' in run, (path, "fixture assumption broken")
        step["run"] = run.replace('"$COST_LINE"', '""')


MUTATIONS = [
    ("the cost callout dropped entirely", mut_drop_report_step),
    ("the dispatch step's id: dispatch-auto dropped", mut_drop_id),
    ("the callout's gate on dispatched == 'true' stripped (double-post risk)",
     mut_drop_dispatched_conjunct),
    ("the callout's gate on auto mode stripped", mut_drop_mode_conjunct),
    ("the callout posting without the cost line", mut_drop_cost_line),
    ("the callout posting through a different action", mut_swap_composite),
    ("dispatched=true hoisted above the standalone branch (double-post)",
     mut_hoist_dispatched),
    ("the standalone comment's $COST_LINE silently blanked",
     mut_drop_standalone_cost_line),
]


def self_test():
    base = load_all()
    problems = []
    tmproot = tempfile.mkdtemp(prefix="verify_plan_tasks_cost_line_")
    try:
        clean = scan(copy.deepcopy(base), tmproot)
        if clean:
            problems.append("clean copy of the real tree FAILED: " + "; ".join(clean))

        for label, apply_mutation in MUTATIONS:
            mutated = copy.deepcopy(base)
            apply_mutation(mutated)
            if mutated == base:
                problems.append(f"mutation {label!r} changed nothing -- the "
                                f"code it edits was rewritten; update the "
                                f"mutation.")
                continue
            broke = scan(mutated, tmproot)
            if not broke:
                problems.append(f"MUTATION SURVIVED -- reintroducing {label!r} "
                                f"broke nothing in this gate.")
            else:
                print(f"Mutation OK -- {label}: {len(broke)} assertion(s) fail.")
    finally:
        import shutil
        shutil.rmtree(tmproot, ignore_errors=True)

    for p in problems:
        print(f"::error::Gate 62 self-test: {p}")
    if problems:
        return 1
    print("Gate 62 self-test: clean tree passes; each mutation fails.")
    return 0


def main(argv):
    global BASH
    use_utf8_stdout()
    BASH = resolve_bash()

    if "--self-test" in argv:
        return self_test()

    tmproot = tempfile.mkdtemp(prefix="verify_plan_tasks_cost_line_")
    try:
        failures = scan(load_all(), tmproot)
    finally:
        import shutil
        shutil.rmtree(tmproot, ignore_errors=True)

    for f in failures:
        print(f"::error::Gate 62: {f}")
    print(f"Gate 62: plan/tasks auto-mode cost-line reporting; "
          f"{len(failures)} failure(s).")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
