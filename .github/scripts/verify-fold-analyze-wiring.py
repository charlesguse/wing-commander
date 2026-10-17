#!/usr/bin/env python3
"""Gate - wing-commander-fold-analyze sits between the fold commit and the
fold dispatch in both callers, and its own composite stays a read-only,
bounded, pinned-model check (specs/116-review-convergence-analyze,
contracts/fold-analyze.md).

WHY THIS EXISTS
---------------
The analyze check is the only thing between a folded review task that
contradicts the constitution and the implement stage that would build it.
Nothing but this gate notices a caller that drops the step, dispatches
without honouring a hold, or a composite edit that widens the agent's tools,
removes its turn ceiling, or runs a `run:` step without `shell: bash`.

Usage: python3 .github/scripts/verify-fold-analyze-wiring.py [--self-test]
"""
import copy
import os
import sys

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_shell_harness import use_utf8_stdout  # noqa: E402

COMPOSITE = ".github/actions/wing-commander-fold-analyze/action.yml"
CALLERS = (
    # (workflow, job, the composite that must precede analyze, if any; in
    # pr-conversation the fold commit runs in an earlier job)
    (".github/workflows/lifecycle-review-gate.yml", "disposition",
     "wing-commander-fold-commit"),
    (".github/workflows/pr-conversation.yml", "dispatch-once",
     None),
)
ANALYZE = "wing-commander-fold-analyze"
DISPATCH = "wing-commander-fold-dispatch"
MODEL = "claude-sonnet-5-5"
READ_ONLY_TOOLS = {"Read", "Grep", "Glob"}


def _load(path):
    return yaml.safe_load(open(path, encoding="utf-8")) or {}


def _uses(step):
    return str((step or {}).get("uses") or "")


def check_caller(path, steps, preceding):
    idx = {}
    for i, s in enumerate(steps):
        for key in (ANALYZE, DISPATCH, preceding):
            if key and key in _uses(s):
                idx.setdefault(key, i)
    failures = []
    if ANALYZE not in idx:
        return [f"{path}: no step calls {ANALYZE} -- a folded task would "
                f"reach implement unchecked."]
    if DISPATCH not in idx:
        failures.append(f"{path}: no step calls {DISPATCH}.")
    elif idx[ANALYZE] > idx[DISPATCH]:
        failures.append(f"{path}: {ANALYZE} runs after {DISPATCH}; the check "
                        f"must precede the dispatch.")
    else:
        cond = str(steps[idx[DISPATCH]].get("if") or "")
        if "decision != 'hold'" not in cond:
            failures.append(f"{path}: the {DISPATCH} step's if: does not "
                            f"withhold dispatch on a hold decision.")
    if preceding and preceding in idx and idx[preceding] > idx[ANALYZE]:
        failures.append(f"{path}: {ANALYZE} runs before {preceding}.")
    return failures


def _find_job(doc, job):
    return (doc.get("jobs") or {}).get(job) or {}


def check_composite(doc):
    steps = (doc.get("runs") or {}).get("steps") or []
    failures = []
    agents = [s for s in steps if "claude-code-action" in _uses(s)]
    if len(agents) != 1:
        return [f"{COMPOSITE}: expected exactly one claude-code-action step, "
                f"found {len(agents)}."]
    args = str((agents[0].get("with") or {}).get("claude_args") or "")
    if f"--model {MODEL}" not in args:
        failures.append(f"{COMPOSITE}: the agent is not pinned to --model {MODEL}.")
    if "--max-turns" not in args:
        failures.append(f"{COMPOSITE}: the agent has no --max-turns ceiling.")
    tools = None
    if "--allowedTools" in args:
        raw = args.split("--allowedTools", 1)[1].strip().split()[0].strip('"\'')
        tools = set(t for t in raw.split(",") if t)
    if tools is None:
        failures.append(f"{COMPOSITE}: the agent has no --allowedTools list.")
    elif not tools or not tools <= READ_ONLY_TOOLS:
        failures.append(f"{COMPOSITE}: the agent's tools {sorted(tools)} are "
                        f"not read-only (allowed: {sorted(READ_ONLY_TOOLS)}).")
    for s in steps:
        if "run" in s and s.get("shell") != "bash":
            failures.append(f"{COMPOSITE}: run step {s.get('name')!r} lacks "
                            f"`shell: bash`.")
    return failures


def check_all():
    failures = check_composite(_load(COMPOSITE))
    for path, job, preceding in CALLERS:
        steps = _find_job(_load(path), job).get("steps") or []
        if not steps:
            failures.append(f"{path}: no steps found for job {job!r}.")
            continue
        failures += check_caller(path, steps, preceding)
    return failures


def self_test():
    use_utf8_stdout()
    failures = 0

    def case(name, cond):
        nonlocal failures
        print(("PASS " if cond else "FAIL ") + name)
        if not cond:
            failures += 1

    real = check_all()
    case(f"the shipped wiring is clean {real!r}", not real)

    path, job, preceding = CALLERS[0]
    steps = _find_job(_load(path), job)["steps"]
    case("a caller without the analyze step is caught",
         len(check_caller(path, [s for s in steps
                                 if ANALYZE not in _uses(s)], preceding)) == 1)
    swapped = copy.deepcopy(steps)
    a = next(i for i, s in enumerate(swapped) if ANALYZE in _uses(s))
    d = next(i for i, s in enumerate(swapped) if DISPATCH in _uses(s))
    swapped[a], swapped[d] = swapped[d], swapped[a]
    case("analyze after dispatch is caught",
         any("after" in f for f in check_caller(path, swapped, preceding)))
    ungated = copy.deepcopy(steps)
    ungated[next(i for i, s in enumerate(ungated)
                 if DISPATCH in _uses(s))]["if"] = "true"
    case("a dispatch that ignores a hold is caught",
         any("withhold" in f for f in check_caller(path, ungated, preceding)))

    comp = _load(COMPOSITE)

    def mutate(fn):
        c = copy.deepcopy(comp)
        for s in c["runs"]["steps"]:
            fn(s)
        return check_composite(c)

    def agent_args(s, old, new):
        if "claude-code-action" in _uses(s):
            s["with"]["claude_args"] = s["with"]["claude_args"].replace(old, new)

    case("an unpinned model is caught",
         any("pinned" in f for f in mutate(
             lambda s: agent_args(s, f"--model {MODEL}", "--model other"))))
    case("a missing turn ceiling is caught",
         any("max-turns" in f for f in mutate(
             lambda s: agent_args(s, "--max-turns", "--x-turns"))))
    case("a widened tool list is caught",
         any("read-only" in f for f in mutate(
             lambda s: agent_args(s, "Read,Grep,Glob", "Read,Write,Bash"))))

    def drop_shell(s):
        if "run" in s:
            s.pop("shell", None)

    case("a run step without shell: bash is caught",
         any("shell: bash" in f for f in mutate(drop_shell)))

    print(f"{failures} failure(s).")
    return 1 if failures else 0


def main(argv):
    use_utf8_stdout()
    if argv == ["--self-test"]:
        return self_test()
    if argv:
        sys.exit(f"unknown arguments {argv!r}; takes --self-test or nothing.")
    failures = check_all()
    for f in failures:
        print(f"::error::{f}")
    print(f"fold-analyze wiring: {len(failures)} failure(s).")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
