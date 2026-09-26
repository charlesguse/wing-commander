#!/usr/bin/env python3
"""Gate 63 - plan.yml and tasks.yml report the run's cost on every path
whose agent stepped, auto-mode and PR-mode alike.

WHY THIS EXISTS
---------------
Both stages compute `steps.cost-line.outputs.line` unconditionally (whenever
one of their two mutually exclusive agent steps -- agent-auto or agent-pr --
ran) but originally handed that value to the lifecycle issue only on the
auto-mode hand-off's standalone (next-workflow empty) branch. Every other
path -- a clean auto-mode dispatch, and EVERY mode == 'pr' (human-reviewed)
run -- posted nothing (#377): plan run 35177818925 cost $2.27 and said
nothing about it on #362, and mode == 'pr' runs never posted a cost
statement at all, not even a bespoke one.

specs/065-intake-silent-path-cost replaced the bespoke "Report cost of an
auto-mode hand-off" callout (#377's original, narrower fix, itself mirroring
#366's clarify-only fix) with a single `Report run cost` step calling the
shared `wing-commander-cost-report` composite, gated ONLY on "one of the two
agent steps ran" and "not cancelled" -- never on `dispatched`, never on
`mode == 'auto'` -- so it fires on the auto-mode standalone path, the
auto-mode dispatched path, AND the mode == 'pr' path alike.

WHAT THIS CHECKS
----------------
Structurally, for each of plan.yml / tasks.yml: the dispatch step still
carries `id: dispatch-auto` (the auto-mode hand-off logic that step alone
still owns); a sibling `Report run cost` step exists, posts via
`wing-commander-cost-report` with the cost line as its `cost-line` input,
and its `if:` requires `always()`, `!cancelled()`, and BOTH agent-ran
disjuncts (`steps.agent-auto.outcome != 'skipped'` /
`steps.agent-pr.outcome != 'skipped'`) -- the second of which is new
structural coverage for the PR-mode gap #377 never touched. The report is
NOT gated on `dispatched` or on `mode == 'auto'` any more; a regression that
reintroduces either gate is exactly what used to make the report miss the
PR-mode path (and, before #377, miss the auto-mode path too).

Behaviorally: the dispatch step's shipped `run:` block is EXECUTED (never a
copy -- gate 5 exists because a copy sat green for weeks checking a filter
that did not ship), via wc_shell_harness.run_step, against a `gh` stubbed to
log its argv rather than call the network. Two scenarios:

  * next-workflow empty (standalone): `dispatched` must NOT be `true`; `gh`
    must have been called as `issue comment ...`; the comment must NOT carry
    the cost line any more (FR-002a moved it onto the uniform report, so the
    standalone comment double-posting it would be a regression, not a fix).
  * next-workflow set: `dispatched` must be `true`; `gh` must have been
    called as `workflow run ...`, and NOT as `issue comment ...` (a stray
    comment here would double-post alongside the report once it fires).

A third check confirms the report's own `if:` evaluates true on a
mode == 'pr' run (agent-pr ran, agent-auto skipped) -- the `||` and
dual-mode condition are not expressible in verify-clarification-gating.py's
restricted `evaluate_if()` grammar (which hard-errors on `||`), so this gate
carries its own small evaluator rather than importing that one.

Self-test (--self-test): loads the real shipped steps, then reintroduces
each way this could regress -- the report dropped entirely, the dispatch
step's id dropped, either the report's `always()` or `!cancelled()` term
stripped, the agent-pr disjunct dropped (reintroducing the PR-mode gap),
its cost line dropped from `with.cost-line`, its `uses:` swapped, the
dispatch step's `dispatched=true` emission hoisted above the branch (the
double-post regression), and asserts each one fails. A gate that cannot
fail proves nothing.

Usage: python3 .github/scripts/verify-plan-tasks-cost-line.py [--self-test]
Requires: bash (same prerequisites every other shell-harness gate needs).
"""
import copy
import io
import os
import re
import sys
import tempfile

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_shell_harness import resolve_bash, run_step, use_utf8_stdout  # noqa: E402

FILES = {
    ".github/workflows/plan.yml":
        ("Dispatch tasks stage (auto)", "Report run cost", "steps.dupe.outputs.skip"),
    ".github/workflows/tasks.yml":
        ("Dispatch implement stage (auto)", "Report run cost", "steps.guard.outputs.skip"),
}

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
# A tiny evaluator for the report step's dual-mode `if:` -- unlike
# verify-clarification-gating.py's evaluate_if(), this one supports the one
# `||` group these two workflows' report steps actually use, since that
# grammar hard-errors on `||` by design (see that module's docstring).
# --------------------------------------------------------------------------
TERM_RE = re.compile(r"^\s*([A-Za-z0-9_.\-]+)\s*(==|!=)\s*'([^']*)'\s*$")


def _eval_term(term, ctx):
    term = term.strip()
    if term in ("always()", "!cancelled()"):
        return True
    m = TERM_RE.match(term)
    if not m:
        raise ValueError(f"cannot parse if: term {term!r}")
    lhs, op, rhs = m.groups()
    actual = ctx.get(lhs, "")
    return (actual == rhs) if op == "==" else (actual != rhs)


def eval_dual_mode_if(expr, ctx):
    """Evaluate an `A && B && ... && (C || D)` expression -- the one shape
    every report step's `if:` in this file actually has. Not a general
    parser: a second parenthesized group, or nesting, is a hard error."""
    expr = str(expr).strip()
    # "always()" is itself a parenthesized (empty) group -- only a group
    # that actually contains a `||` is the OR group this function handles.
    groups = [g for g in re.findall(r"\(([^()]*)\)", expr) if "||" in g]
    if len(groups) > 1:
        raise ValueError(f"cannot evaluate if: with more than one "
                         f"OR group: {expr!r}")
    if groups:
        or_result = any(_eval_term(p, ctx) for p in groups[0].split("||"))
        replacement = "true" if or_result else "false"
        expr = re.sub(r"\(([^()]*)\)",
                      lambda m: replacement if "||" in m.group(1) else m.group(0),
                      expr)
    result = True
    for term in expr.split("&&"):
        term = term.strip()
        if term in ("true", "false"):
            if term == "false":
                result = False
            continue
        if not _eval_term(term, ctx):
            result = False
    return result


# --------------------------------------------------------------------------
# Structural checks -- facts a `uses:` composite step can't be executed to
# prove, so they stay static.
# --------------------------------------------------------------------------
def check_structure(path, dispatch, report, report_name):
    failures = []

    if dispatch.get("id") != "dispatch-auto":
        failures.append(
            f"{path}: the dispatch step must carry id: dispatch-auto -- "
            f"the auto-mode hand-off logic (workflow run vs. standalone "
            f"comment) keys off it")

    cond = str(report.get("if", "") or "")
    for needed, why in (
        ("always()", "without it the report would be strandable by any "
         "failing step above it (FR-012a)"),
        ("!cancelled()", "without it the report could post on a cancelled "
         "run (FR-013)"),
        ("steps.agent-auto.outcome != 'skipped'", "without it an auto-mode "
         "run that actually stepped its agent would never be recognized"),
        ("steps.agent-pr.outcome != 'skipped'", "without it a mode == 'pr' "
         "run reports no cost at all -- the wider gap #377 never touched"),
    ):
        if needed not in cond:
            failures.append(
                f"{path}: {report_name!r}'s if: does not require {needed} "
                f"-- {why}")

    body = str((report.get("with") or {}).get("cost-line", ""))
    if "steps.cost-line.outputs.line" not in body:
        failures.append(
            f"{path}: {report_name!r} posts without the cost line -- a run "
            f"that spent money would report none of it (#377)")

    uses = str(report.get("uses", ""))
    if "wing-commander-cost-report" not in uses:
        failures.append(
            f"{path}: {report_name!r} must post via the wing-commander-"
            f"cost-report composite, the single home for posting a stage's "
            f"cost line to its lifecycle issue (specs/065-intake-silent-"
            f"path-cost)")

    return failures


def check_report_pr_mode(path, report, report_name, skip_ref):
    """The report must fire on a mode == 'pr' run (agent-pr ran, agent-auto
    did not) -- the structural agent-pr disjunct check above proves the
    term is textually present, not that the whole expression evaluates true
    with it; this proves the latter."""
    ctx = {skip_ref: "false",
           "steps.agent-auto.outcome": "skipped",
           "steps.agent-pr.outcome": "success"}
    try:
        result = eval_dual_mode_if(report.get("if", ""), ctx)
    except ValueError as exc:
        return [f"{path}: cannot evaluate {report_name!r}'s if: for a "
                f"mode == 'pr' run: {exc}"]
    if not result:
        return [f"{path}: {report_name!r}'s if: evaluates False on a "
                f"mode == 'pr' run (agent-pr ran, agent-auto skipped) -- "
                f"a human-reviewed run would report no cost at all (#377)"]
    return []


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
    # placeholder; NEXT_WORKFLOW gets a value this harness actually cares
    # about, ISSUE (which gates whether the standalone branch posts at all)
    # gets a non-empty one.
    env = {k: f"test-{k.lower()}" for k in (dispatch.get("env") or {})}
    env["NEXT_WORKFLOW"] = next_workflow
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
    # emit dispatched=true, must NOT carry the cost line any more (that
    # moved onto the uniform report -- FR-002a). --
    rc, out, outputs, calls = run_dispatch(dispatch, "", root)
    if rc != 0:
        failures.append(f"{path}: the dispatch step exited {rc} on the "
                        f"standalone (empty next-workflow) path:\n{out}")
    if outputs.get("dispatched") == "true":
        failures.append(
            f"{path}: the dispatch step emits dispatched=true on the "
            f"standalone path -- {report_name!r} would then double-count "
            f"against a hand-off that never happened")
    comment_calls = _calls_matching(calls, "issue", "comment")
    if not comment_calls:
        failures.append(f"{path}: the dispatch step never called "
                        f"`gh issue comment` on the standalone path "
                        f"(got calls: {calls!r})")
    elif any(COST_SENTINEL in arg for c in comment_calls for arg in c):
        failures.append(
            f"{path}: the standalone-mode comment still carries the cost "
            f"line -- FR-002a moved that onto {report_name!r}, so a run "
            f"finding no next-workflow configured would now double-report "
            f"it")

    # -- next-workflow set: must dispatch, must emit dispatched=true, must
    # NOT also post the standalone comment. --
    rc, out, outputs, calls = run_dispatch(dispatch, NEXT_WORKFLOW_SET, root)
    if rc != 0:
        failures.append(f"{path}: the dispatch step exited {rc} when "
                        f"next-workflow was configured:\n{out}")
    if outputs.get("dispatched") != "true":
        failures.append(
            f"{path}: the dispatch step does not emit dispatched=true when "
            f"it actually calls `gh workflow run`")
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
    for path, (dispatch_name, report_name, skip_ref) in FILES.items():
        steps = loaded[path]
        dispatch = steps.get(dispatch_name)
        if dispatch is None:
            failures.append(f"{path}: missing step {dispatch_name!r}")
            continue
        report = steps.get(report_name)
        if report is None:
            failures.append(
                f"{path}: missing step {report_name!r} -- a run that spent "
                f"real money reports none of it (#377)")
            continue
        failures += check_structure(path, dispatch, report, report_name)
        failures += check_report_pr_mode(path, report, report_name, skip_ref)
        failures += check_behavior(path, dispatch, report_name, root)
    return failures


# --------------------------------------------------------------------------
# Self-test -- mutations reintroducing each way this could regress.
# --------------------------------------------------------------------------
def mut_drop_report_step(loaded):
    for path, (_dispatch_name, report_name, _skip_ref) in FILES.items():
        loaded[path].pop(report_name, None)


def mut_drop_id(loaded):
    for path, (dispatch_name, _report_name, _skip_ref) in FILES.items():
        loaded[path][dispatch_name].pop("id", None)


def _strip_conjunct(step, needle):
    terms = [t.strip() for t in str(step["if"]).split("&&")]
    step["if"] = " && ".join(t for t in terms if needle not in t)


def mut_drop_always(loaded):
    for path, (_dispatch_name, report_name, _skip_ref) in FILES.items():
        _strip_conjunct(loaded[path][report_name], "always()")


def mut_drop_cancelled(loaded):
    for path, (_dispatch_name, report_name, _skip_ref) in FILES.items():
        _strip_conjunct(loaded[path][report_name], "!cancelled()")


def mut_drop_pr_disjunct(loaded):
    """Reintroduces #377's wider, never-fixed gap: a mode == 'pr' run
    reports no cost at all."""
    for path, (_dispatch_name, report_name, _skip_ref) in FILES.items():
        step = loaded[path][report_name]
        run_if = str(step["if"])
        new_if = re.sub(
            r"\(steps\.agent-auto\.outcome != 'skipped' \|\|\s*"
            r"steps\.agent-pr\.outcome != 'skipped'\)",
            "steps.agent-auto.outcome != 'skipped'", run_if)
        assert new_if != run_if, (path, "fixture assumption broken")
        step["if"] = new_if


def mut_drop_cost_line(loaded):
    for path, (_dispatch_name, report_name, _skip_ref) in FILES.items():
        loaded[path][report_name]["with"]["cost-line"] = ""


def mut_swap_composite(loaded):
    for path, (_dispatch_name, report_name, _skip_ref) in FILES.items():
        loaded[path][report_name]["uses"] = "actions/checkout@v4"


def mut_hoist_dispatched(loaded):
    """b81d818's review, finding 1: `dispatched=true` moved above the
    branch fires it on the standalone path too -- a pure string-presence
    check cannot see this, only executing the step can."""
    line = 'echo "dispatched=true" >> "$GITHUB_OUTPUT"'
    marker = 'if [ -z "$NEXT_WORKFLOW" ]; then'
    for path, (dispatch_name, _report_name, _skip_ref) in FILES.items():
        step = loaded[path][dispatch_name]
        run = str(step["run"])
        assert line in run and marker in run, (path, "fixture assumption broken")
        step["run"] = run.replace(line, "", 1).replace(marker, line + "\n" + marker, 1)


MUTATIONS = [
    ("the cost report dropped entirely", mut_drop_report_step),
    ("the dispatch step's id: dispatch-auto dropped", mut_drop_id),
    ("the report's if: losing always() (strandable by a failing step above it)",
     mut_drop_always),
    ("the report's if: losing !cancelled() (would post on a cancelled run)",
     mut_drop_cancelled),
    ("the report's if: losing the agent-pr disjunct (PR-mode gets no report, "
     "#377's wider gap)", mut_drop_pr_disjunct),
    ("the report posting without the cost line", mut_drop_cost_line),
    ("the report posting through a different action", mut_swap_composite),
    ("dispatched=true hoisted above the standalone branch (double-post)",
     mut_hoist_dispatched),
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
        print(f"::error::Gate 63 self-test: {p}")
    if problems:
        return 1
    print("Gate 63 self-test: clean tree passes; each mutation fails.")
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
        print(f"::error::Gate 63: {f}")
    print(f"Gate 63: plan/tasks cost-line reporting (auto and PR mode); "
          f"{len(failures)} failure(s).")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
