#!/usr/bin/env python3
"""Gate 166 - the fold-time analyze check sits between the fold commit and
the fold dispatch in every caller, its agent stays read-only, bounded and on
its pinned model, and its composite stays deterministic
(specs/116-review-convergence-analyze, contracts/fold-analyze.md).

WHY THIS EXISTS
---------------
The analyze check is the only thing between a folded review task that
contradicts the constitution and the implement stage that would build it.
Nothing but this gate notices a caller that drops a step, dispatches
without honouring a hold, or reads a failed check as a pass; or an edit that
widens the agent's tools, removes its turn ceiling, moves it off
claude-sonnet-5-5 (FR-016), or puts the agent back inside the composite
(verify-actions-layer-invariants.py: a composite never invokes the agent).

THE SHAPE, PER CALLER JOB
-------------------------
  [fold commit] -> fold-analyze (mode: stage) -> claude-code-action
  -> fold-analyze (mode: decide, agent-outcome from that agent step)
  -> fold-dispatch, whose `if:` admits only decision dispatch or skipped
     and never the negative `!= 'hold'` (an empty decision -- the decide
     step never ran -- must not dispatch an unchecked fold, FR-013).

The agent step: `--model claude-sonnet-5-5`, a `--max-turns` ceiling,
`--allowedTools` a subset of Read,Grep,Glob, and `--disallowedTools`
naming Write, Edit and Bash. Its prompt points at the composite's staged
instructions-file (the one home of the instructions).

Every failure branch is exercised by --self-test, which mutates the real
tree's own shapes (Constitution VIII); it also runs wc_fold_hold.py's
self-test, the hold-release logic this gate's callers post through.

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
    # (workflow, job, the composite that must precede the stage step, if
    # any; in pr-conversation the fold commits run in an earlier job, and
    # the hold-release job re-checks a fold committed in an earlier run)
    (".github/workflows/lifecycle-review-gate.yml", "disposition",
     "wing-commander-fold-commit"),
    (".github/workflows/pr-conversation.yml", "dispatch-once", None),
    (".github/workflows/wing-commander-fold-hold.yml", "release", None),
)
ANALYZE = "wing-commander-fold-analyze"
DISPATCH = "wing-commander-fold-dispatch"
AGENT = "claude-code-action"
MODEL = "claude-sonnet-5-5"
READ_ONLY_TOOLS = {"Read", "Grep", "Glob"}
MUST_DISALLOW = {"Write", "Edit", "Bash"}


def _load(path):
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _uses(step):
    return str((step or {}).get("uses") or "")


def _mode(step):
    return str(((step or {}).get("with") or {}).get("mode") or "")


def _tools(args, flag):
    if flag not in args:
        return None
    raw = args.split(flag, 1)[1].strip().split()[0].strip('"\'')
    return set(t for t in raw.split(",") if t)


def check_agent(path, step):
    w = step.get("with") or {}
    args = str(w.get("claude_args") or "")
    failures = []
    if f"--model {MODEL}" not in args:
        failures.append(f"{path}: the analyze agent is not pinned to --model {MODEL}.")
    if "--max-turns" not in args:
        failures.append(f"{path}: the analyze agent has no --max-turns ceiling.")
    allowed = _tools(args, "--allowedTools")
    if allowed is None:
        failures.append(f"{path}: the analyze agent has no --allowedTools list.")
    elif not allowed or not allowed <= READ_ONLY_TOOLS:
        failures.append(f"{path}: the analyze agent's tools {sorted(allowed)} are "
                        f"not read-only (allowed: {sorted(READ_ONLY_TOOLS)}).")
    denied = _tools(args, "--disallowedTools") or set()
    if not MUST_DISALLOW <= denied:
        failures.append(f"{path}: the analyze agent's --disallowedTools does not "
                        f"name {sorted(MUST_DISALLOW - denied)}.")
    if "instructions-file" not in str(w.get("prompt") or ""):
        failures.append(f"{path}: the analyze agent's prompt does not point at the "
                        f"composite's staged instructions-file.")
    return failures


def check_caller(path, steps, preceding):
    def first(pred):
        return next((i for i, s in enumerate(steps) if pred(s)), None)

    stage = first(lambda s: ANALYZE in _uses(s) and _mode(s) == "stage")
    decide = first(lambda s: ANALYZE in _uses(s) and _mode(s) == "decide")
    dispatch = first(lambda s: DISPATCH in _uses(s))
    if stage is None or decide is None:
        return [f"{path}: no {ANALYZE} step in mode "
                f"{'stage' if stage is None else 'decide'} -- a folded task "
                f"would reach implement unchecked."]
    failures = []
    agent = first(lambda s: AGENT in _uses(s)
                  and stage < steps.index(s) < decide)
    if agent is None:
        failures.append(f"{path}: no {AGENT} step between the stage and decide "
                        f"steps -- the check has no agent.")
    else:
        failures += check_agent(path, steps[agent])
        outcome = str((steps[decide].get("with") or {}).get("agent-outcome") or "")
        agent_id = steps[agent].get("id") or ""
        if not agent_id or f"steps.{agent_id}.outcome" not in outcome:
            failures.append(f"{path}: the decide step's agent-outcome does not read "
                            f"the analyze agent step's own outcome.")
    if decide < stage:
        failures.append(f"{path}: the decide step runs before the stage step.")
    if preceding is not None:
        commit = first(lambda s: preceding in _uses(s))
        if commit is None or commit > stage:
            failures.append(f"{path}: {ANALYZE} stages before {preceding} runs.")
    if dispatch is None:
        failures.append(f"{path}: no step calls {DISPATCH}.")
    elif dispatch < decide:
        failures.append(f"{path}: {DISPATCH} runs before the analyze decision; the "
                        f"check must precede the dispatch.")
    else:
        cond = " ".join(str(steps[dispatch].get("if") or "").split())
        if "decision == 'dispatch'" not in cond or "!= 'hold'" in cond:
            failures.append(f"{path}: the {DISPATCH} step's if: does not admit only "
                            f"decision dispatch/skipped -- a hold, or a decide step "
                            f"that never ran, must withhold dispatch.")
    return failures


def check_composite(doc):
    steps = (doc.get("runs") or {}).get("steps") or []
    failures = []
    if any(AGENT in _uses(s) for s in steps):
        failures.append(f"{COMPOSITE}: invokes {AGENT}; the agent runs in the "
                        f"calling job, never inside a composite.")
    modes = {str(s.get("if") or "") for s in steps}
    for mode in ("stage", "decide"):
        if not any(f"inputs.mode == '{mode}'" in m for m in modes):
            failures.append(f"{COMPOSITE}: has no step for mode {mode!r}.")
    for s in steps:
        if "run" in s and s.get("shell") != "bash":
            failures.append(f"{COMPOSITE}: run step {s.get('name')!r} lacks "
                            f"`shell: bash`.")
    return failures


def _find_job(doc, job):
    return (doc.get("jobs") or {}).get(job) or {}


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

    def idx(lst, pred):
        return next(i for i, s in enumerate(lst) if pred(s))

    def is_stage(s):
        return ANALYZE in _uses(s) and _mode(s) == "stage"

    def is_decide(s):
        return ANALYZE in _uses(s) and _mode(s) == "decide"

    def is_agent(s):
        return AGENT in _uses(s) and s.get("id") == "analyze-agent"

    def is_dispatch(s):
        return DISPATCH in _uses(s)

    def caught(mutated, word):
        return any(word in f for f in check_caller(path, mutated, preceding))

    case("a caller without the stage step is caught",
         caught([s for s in steps if not is_stage(s)], "unchecked"))
    case("a caller without the decide step is caught",
         caught([s for s in steps if not is_decide(s)], "unchecked"))
    case("a caller without the agent step is caught",
         caught([s for s in steps if not is_agent(s)], "no agent"))

    swapped = copy.deepcopy(steps)
    d, p = idx(swapped, is_decide), idx(swapped, is_dispatch)
    moved = swapped.pop(p)
    swapped.insert(d, moved)
    case("dispatch before the decision is caught", caught(swapped, "before the analyze decision"))

    for cond, label in (("true", "an ungated dispatch"),
                        ("steps.analyze-fold.outputs.decision != 'hold'",
                         "the negative != 'hold' form (an empty decision dispatches)")):
        mutated = copy.deepcopy(steps)
        mutated[idx(mutated, is_dispatch)]["if"] = cond
        case(f"{label} is caught", caught(mutated, "admit only"))

    early = copy.deepcopy(steps)
    c = idx(early, lambda s: preceding in _uses(s))
    commit = early.pop(c)
    early.append(commit)
    case("staging before the fold commit is caught", caught(early, "stages before"))

    rewired = copy.deepcopy(steps)
    rewired[idx(rewired, is_decide)]["with"]["agent-outcome"] = "success"
    case("a decide step that ignores the agent's outcome is caught",
         caught(rewired, "agent-outcome"))

    def agent_mutation(fn):
        mutated = copy.deepcopy(steps)
        fn(mutated[idx(mutated, is_agent)]["with"])
        return check_caller(path, mutated, preceding)

    def args_replace(old, new):
        def fn(w):
            w["claude_args"] = w["claude_args"].replace(old, new)
        return fn

    case("an unpinned model is caught",
         any("pinned" in f for f in agent_mutation(args_replace(f"--model {MODEL}", "--model other"))))
    case("a missing turn ceiling is caught",
         any("max-turns" in f for f in agent_mutation(args_replace("--max-turns", "--x-turns"))))
    case("a widened tool list is caught",
         any("read-only" in f for f in agent_mutation(args_replace('"Read,Grep,Glob"', '"Read,Write,Bash"'))))
    case("a missing allowed-tools list is caught",
         any("no --allowedTools" in f for f in agent_mutation(args_replace("--allowedTools", "--tools"))))
    case("a deny list that drops Bash is caught",
         any("disallowedTools" in f for f in agent_mutation(args_replace(",Bash\"", "\""))))

    def drop_prompt(w):
        w["prompt"] = "Run /speckit-analyze."
    case("a prompt that does not use the staged instructions is caught",
         any("instructions-file" in f for f in agent_mutation(drop_prompt)))

    comp = _load(COMPOSITE)

    def comp_mutation(fn):
        c = copy.deepcopy(comp)
        fn(c["runs"]["steps"])
        return check_composite(c)

    case("an agent inside the composite is caught",
         any("never inside a composite" in f for f in comp_mutation(
             lambda st: st.append({"uses": "anthropics/claude-code-action@v1"}))))
    case("a composite without its decide mode is caught",
         any("mode 'decide'" in f for f in comp_mutation(
             lambda st: st.__setitem__(slice(None), [s for s in st if "decide" not in str(s.get("if"))]))))

    def drop_shell(st):
        for s in st:
            s.pop("shell", None)
    case("a run step without shell: bash is caught",
         any("shell: bash" in f for f in comp_mutation(drop_shell)))

    import wc_fold_hold
    case("wc_fold_hold.py's own self-test passes", wc_fold_hold.self_test() == 0)

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
