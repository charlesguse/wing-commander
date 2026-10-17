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

THE SHAPE, PER CALLER
--------------------
  [fold commit] -> fold-analyze (mode: stage) -> claude-code-action
  -> fold-analyze (mode: decide, agent-outcome from that agent step)
  -> fold-dispatch, whose `if:` admits only decision dispatch or skipped
     and never the negative `!= 'hold'` (an empty decision -- the decide
     step never ran -- must not dispatch an unchecked fold, FR-013).

The stage step and the agent share a job of their own, read-only:
`contents: read` and no write scope (the owner's decision on finding 15
of #1062's review), so the github.token the agent holds writes nothing.
The decide step runs in a later job that downloads the agent's
transcript and reads its outcome through that job's outputs. Its
open-holds input reads a wing-commander-fold-open-holds step in its own
job, so an open fold hold on the lifecycle turns a dispatch into
`blocked` (finding 9: an open hold blocks every fold dispatch until it is
answered).

The agent step: `--model claude-sonnet-5-5`, a `--max-turns` ceiling,
`--allowedTools` a subset of Read,Grep,Glob, and `--disallowedTools`
naming Write, Edit and Bash. Its prompt points at the composite's staged
instructions-file (the one home of the instructions). An agent that passes
`use_bedrock` is preceded in its job by wing-commander-bedrock-credentials,
or every Bedrock adopter's check fails and holds every fold.

The dispatch's `if:` also carries `!cancelled()`, so a failed post or log
upload between the decision and the dispatch cannot strand a fold the check
let through; a step that writes a hold's resolved marker runs after the
dispatch, never before it, so a release that never dispatched leaves the
hold open to answer again, and the step after it that records a
dispatched release carries `!cancelled()` so it is never skipped; a
release's dispatch names a step in its own job that re-reads the hold
(`wc_fold_hold.py resolve`), so two answers close together dispatch once,
and requires that step to find no other hold open;
and pr-conversation (the published caller)
replies on the PR when its fold is held or blocked, as it does when one
dispatches.

The fold-analyze steps' rationale comments live once, in
lifecycle-review-gate.yml; the other callers point at it (CLAUDE.md's
"Shared logic has exactly one home").

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
    # (workflow, its jobs in order -- the fold commit's, the read-only
    # analyze agent's, the deciding and dispatching one's -- and the
    # composite that must precede the stage step, if any; in pr-conversation
    # the fold commits run in an earlier job, and the hold-release workflow
    # re-checks a fold committed in an earlier run)
    (".github/workflows/lifecycle-review-gate.yml",
     ("disposition", "fold-analyze", "fold-decide"), "wing-commander-fold-commit"),
    (".github/workflows/pr-conversation.yml", ("fold-analyze", "dispatch-once"), None),
    (".github/workflows/wing-commander-fold-hold.yml", ("fold-analyze", "release"), None),
)
# The published caller: a held fold is answered on the PR, as a dispatched
# one is (constitution VII: nothing beyond one extra read-only agent run).
PUBLISHED_CALLER = ".github/workflows/pr-conversation.yml"
BEDROCK = "wing-commander-bedrock-credentials"
# The fold-analyze steps' rationale comments, and their one home.
CANONICAL_COMMENTS_HOME = ".github/workflows/lifecycle-review-gate.yml"
CANONICAL_COMMENTS = (
    "the decide step below is this check's own fallback",
    "The transcript is the only record of what the analyze agent did",
)
ANALYZE = "wing-commander-fold-analyze"
DISPATCH = "wing-commander-fold-dispatch"
OPEN_HOLDS = "wing-commander-fold-open-holds"
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


def check_caller(path, jobs, preceding):
    """jobs: [(name, job)] in order. The checks read their steps as one
    sequence, and each step's own job where a rule is per job."""
    steps = [s for _n, j in jobs for s in (j.get("steps") or [])]
    owner = [n for n, j in jobs for _s in (j.get("steps") or [])]
    by_name = dict(jobs)

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
    agent = next((i for i, s in enumerate(steps)
                  if AGENT in _uses(s) and stage < i < decide), None)
    if agent is None:
        failures.append(f"{path}: no {AGENT} step between the stage and decide "
                        f"steps -- the check has no agent.")
    else:
        failures += check_agent(path, steps[agent])
        agent_job = owner[agent]
        if owner[stage] != agent_job:
            failures.append(f"{path}: the stage step is not in the analyze agent's job "
                            f"{agent_job!r} -- the agent reads the section it stages.")
        failures += check_agent_job(path, agent_job, by_name[agent_job])
        outcome = str((steps[decide].get("with") or {}).get("agent-outcome") or "")
        agent_id = steps[agent].get("id") or ""
        reads = bool(agent_id) and f"steps.{agent_id}.outcome" in outcome
        if owner[decide] != agent_job:
            outputs = by_name[agent_job].get("outputs") or {}
            reads = bool(agent_id) and any(
                f"needs.{agent_job}.outputs.{k}" in outcome
                and f"steps.{agent_id}.outcome" in str(v) for k, v in outputs.items())
            fetched = any("download-artifact" in _uses(s)
                          and "claude-execution-output-fold-analyze" in str((s.get("with") or {}).get("name"))
                          for i, s in enumerate(steps[:decide]) if owner[i] == owner[decide])
            if not fetched or not (steps[decide].get("with") or {}).get("execution-output-path"):
                failures.append(f"{path}: the decide step in {owner[decide]!r} does not "
                                f"download the analyze agent's transcript from "
                                f"{agent_job!r} and read it (execution-output-path).")
        if not reads:
            failures.append(f"{path}: the decide step's agent-outcome does not read "
                            f"the analyze agent step's own outcome.")
        bedrock = str((steps[agent].get("with") or {}).get("use_bedrock") or "")
        if bedrock and bedrock != "false" and not any(
                BEDROCK in _uses(s) for i, s in enumerate(steps[:agent]) if owner[i] == agent_job):
            failures.append(f"{path}: the analyze agent passes use_bedrock but no "
                            f"{BEDROCK} step precedes it in its job -- a Bedrock "
                            f"adopter's check fails and holds every fold.")
    holds_in = str((steps[decide].get("with") or {}).get("open-holds") or "")
    readers = [s for i, s in enumerate(steps[:decide])
               if OPEN_HOLDS in _uses(s) and owner[i] == owner[decide] and s.get("id")
               and all(str((s.get("with") or {}).get(k) or "").strip()
                       for k in ("issue", "github-token", "bot-login"))]
    if not any(f"steps.{r['id']}.outputs.open-holds" in holds_in for r in readers):
        failures.append(f"{path}: the decide step's open-holds does not read a "
                        f"{OPEN_HOLDS} step in its own job (passing issue, github-token "
                        f"and bot-login) -- an open fold hold on the lifecycle would not "
                        f"block this fold's dispatch.")
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
        if "!cancelled()" not in cond:
            failures.append(f"{path}: the {DISPATCH} step's if: lacks !cancelled() -- "
                            f"a failed step between the decision and the dispatch "
                            f"strands a fold the check let through.")
        early = [s.get("name") for s in steps[:dispatch]
                 if "resolved-marker" in str(s.get("run") or "")]
        if early:
            failures.append(f"{path}: {early} writes a hold's resolved marker before "
                            f"{DISPATCH} runs -- a release that never dispatches "
                            f"would close the hold with nothing left to answer.")
        unrecorded = [s.get("name") for s in steps[dispatch + 1:]
                      if "resolved-marker" in str(s.get("run") or "")
                      and "!cancelled()" not in str(s.get("if") or "")]
        if unrecorded:
            failures.append(f"{path}: {unrecorded} records a dispatched release without "
                            f"!cancelled() -- a failed step above skips it, the hold "
                            f"stays open, and a second answer dispatches again.")
        releases = any("resolved-marker" in str(s.get("run") or "") for s in steps[dispatch + 1:])
        rechecks = [s.get("id") for i, s in enumerate(steps[:dispatch])
                    if "wc_fold_hold.py resolve" in str(s.get("run") or "") and s.get("id")
                    and owner[i] == owner[dispatch]]
        if releases and not any(f"steps.{r}.outcome == 'success'" in cond for r in rechecks):
            failures.append(f"{path}: the {DISPATCH} step's if: does not name a step in "
                            f"its own job that re-reads the hold with `wc_fold_hold.py "
                            f"resolve` -- two answers close together both find it open "
                            f"and the fold dispatches twice.")
        if releases and not any(f"steps.{r}.outputs.other-open == ''" in cond for r in rechecks):
            failures.append(f"{path}: the {DISPATCH} step's if: does not require that no "
                            f"other fold hold is open (`steps.<recheck>.outputs.other-open "
                            f"== ''`) -- answering one hold would dispatch past another.")
    if path == PUBLISHED_CALLER and not any(
            "decision == 'hold'" in str(s.get("if") or "")
            and "decision == 'blocked'" in str(s.get("if") or "")
            and "gh pr comment" in str(s.get("run") or "") for s in steps):
        failures.append(f"{path}: no step replies on the PR when the fold is held or "
                        f"blocked -- the review that folded gets no answer.")
    return failures


def check_agent_job(path, name, job):
    """The analyze agent's job is read-only: `contents: read` and no write
    scope (the owner's decision on finding 15 of #1062's review), so the
    github.token it holds, and any credential its checkout could leave,
    writes nothing."""
    perms = job.get("permissions")
    if not isinstance(perms, dict) or str(perms.get("contents")) != "read" or any(
            str(v) == "write" for v in perms.values()):
        return [f"{path}: job {name!r} runs the analyze agent with permissions "
                f"{perms!r}; it must have `contents: read` and no write scope."]
    return []


def check_comment_homes(texts):
    """texts: {caller path: raw text}. Each rationale lives in its home only."""
    failures = []
    for phrase in CANONICAL_COMMENTS:
        homes = sorted(p for p, t in texts.items() if phrase in t)
        if homes != [CANONICAL_COMMENTS_HOME]:
            failures.append(f"the fold-analyze comment {phrase!r} is in {homes}; it "
                            f"lives once, in {CANONICAL_COMMENTS_HOME}, and the other "
                            f"callers point at it (-- see).")
    return failures


def _caller_texts():
    texts = {}
    for path, _jobs, _pre in CALLERS:
        with open(path, encoding="utf-8") as fh:
            texts[path] = fh.read()
    return texts


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


def _jobs(path, names):
    doc = _load(path)
    return [(n, _find_job(doc, n)) for n in names]


def check_all():
    failures = check_composite(_load(COMPOSITE))
    for path, names, preceding in CALLERS:
        jobs = _jobs(path, names)
        missing = [n for n, j in jobs if not j.get("steps")]
        if missing:
            failures.append(f"{path}: no steps found for job(s) {missing!r}.")
            continue
        failures += check_caller(path, jobs, preceding)
    failures += check_comment_homes(_caller_texts())
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

    def is_stage(s):
        return ANALYZE in _uses(s) and _mode(s) == "stage"

    def is_decide(s):
        return ANALYZE in _uses(s) and _mode(s) == "decide"

    def is_agent(s):
        return AGENT in _uses(s) and s.get("id") == "analyze-agent"

    def is_dispatch(s):
        return DISPATCH in _uses(s)

    def loc(jobs, pred):
        """(that job's steps list, index) of the first step matching pred."""
        for _n, j in jobs:
            for i, st in enumerate(j["steps"]):
                if pred(st):
                    return j["steps"], i
        raise LookupError("no matching step")

    def step(jobs, pred):
        lst, i = loc(jobs, pred)
        return lst[i]

    def drop(jobs, pred):
        for _n, j in jobs:
            j["steps"] = [st for st in j["steps"] if not pred(st)]
        return jobs

    def caller(n):
        path, names, preceding = CALLERS[n]
        base = _jobs(path, names)

        def fresh():
            return copy.deepcopy(base)

        def check(jobs):
            return check_caller(path, jobs, preceding)
        return path, preceding, fresh, check

    path, preceding, fresh, check = caller(0)

    def caught(jobs, word):
        return any(word in f for f in check(jobs))

    case("a caller without the stage step is caught", caught(drop(fresh(), is_stage), "unchecked"))
    case("a caller without the decide step is caught", caught(drop(fresh(), is_decide), "unchecked"))
    case("a caller without the agent step is caught", caught(drop(fresh(), is_agent), "no agent"))

    swapped = fresh()
    dl, d = loc(swapped, is_decide)
    pl, p = loc(swapped, is_dispatch)
    moved = pl.pop(p)
    dl.insert(dl.index(step(swapped, is_decide)), moved)
    case("dispatch before the decision is caught", caught(swapped, "before the analyze decision"))

    for cond, label in (("true", "an ungated dispatch"),
                        ("steps.analyze-fold.outputs.decision != 'hold'",
                         "the negative != 'hold' form (an empty decision dispatches)")):
        mutated = fresh()
        step(mutated, is_dispatch)["if"] = cond
        case(f"{label} is caught", caught(mutated, "admit only"))

    early = fresh()
    cl, c = loc(early, lambda st: preceding in _uses(st))
    commit = cl.pop(c)
    early[-1][1]["steps"].append(commit)
    case("staging before the fold commit is caught", caught(early, "stages before"))

    rewired = fresh()
    step(rewired, is_decide)["with"]["agent-outcome"] = "success"
    case("a decide step that ignores the agent's outcome is caught", caught(rewired, "agent-outcome"))

    blind = drop(fresh(), lambda st: "download-artifact" in _uses(st)
                 and "fold-analyze" in str((st.get("with") or {}).get("name")))
    case("a decide job that never fetches the agent's transcript is caught",
         caught(blind, "transcript"))

    unblocked = fresh()
    step(unblocked, is_decide)["with"].pop("open-holds")
    case("a decide step that cannot see the open holds is caught", caught(unblocked, "open fold hold"))
    unread = drop(fresh(), lambda st: OPEN_HOLDS in _uses(st))
    case("a decide job that never reads the open holds is caught", caught(unread, "open fold hold"))

    for label, perms in (("contents: write", {"contents": "write"}),
                         ("a write scope beside contents: read", {"contents": "read", "issues": "write"}),
                         ("no permissions block", None)):
        widened = fresh()
        agent_job = next(j for _n, j in widened if any(is_agent(st) for st in j["steps"]))
        if perms is None:
            agent_job.pop("permissions", None)
        else:
            agent_job["permissions"] = perms
        case(f"an analyze agent job with {label} is caught", caught(widened, "no write scope"))

    # The pre-decision layout: the agent inside the job that holds
    # contents: write to commit the fold and dispatch.
    merged = fresh()
    all_steps = [st for _n, j in merged for st in j["steps"]]
    merged = [(merged[0][0], dict(merged[0][1], steps=all_steps))]
    case("the agent in the fold commit's own write-capable job is caught",
         caught(merged, "no write scope"))

    def agent_mutation(fn):
        mutated = fresh()
        fn(step(mutated, is_agent)["with"])
        return check(mutated)

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

    uncancelled = fresh()
    step(uncancelled, is_dispatch)["if"] = "steps.analyze-fold.outputs.decision == 'dispatch'"
    case("a dispatch without !cancelled() is caught", caught(uncancelled, "!cancelled()"))

    pub_path, _pub_pre, pub_fresh, pub_check = caller(1)

    def pub_caught(jobs, word):
        return any(word in f for f in pub_check(jobs))

    case("the published caller's analyze agent without Bedrock credentials is caught",
         pub_caught(drop(pub_fresh(), lambda st: BEDROCK in _uses(st)), "use_bedrock"))
    case("the published caller without a PR reply on a hold or block is caught",
         pub_caught(drop(pub_fresh(), lambda st: "decision == 'hold'" in str(st.get("if") or "")
                         and "gh pr comment" in str(st.get("run") or "")), "replies on the PR"))

    rel_path, _rel_pre, rel_fresh, rel_check = caller(2)

    def rel_caught(jobs, word):
        return any(word in f for f in rel_check(jobs))

    closed_early = rel_fresh()
    sl, si = loc(closed_early, is_decide)
    sl.insert(si, {"name": "Close the hold before a retry",
                   "run": "python3 wc_fold_hold.py resolved-marker --fold-id x --resolution retry"})
    case("a resolved marker written before the dispatch is caught",
         rel_caught(closed_early, "resolved marker"))

    implicit = rel_fresh()
    rec = step(implicit, lambda st: "resolved-marker" in str(st.get("run") or ""))
    rec["if"] = rec["if"].replace("!cancelled() && ", "")
    case("a release record without !cancelled() is caught", rel_caught(implicit, "second answer"))

    unchecked = rel_fresh()
    d = step(unchecked, is_dispatch)
    d["if"] = d["if"].replace("steps.recheck.outcome == 'success' && ", "")
    case("a release dispatch that does not re-read the hold in its own job is caught",
         rel_caught(unchecked, "dispatches twice"))

    past_others = rel_fresh()
    d = step(past_others, is_dispatch)
    d["if"] = d["if"].replace(" && steps.recheck.outputs.other-open == ''", "")
    case("a release dispatch that ignores the other open holds is caught",
         rel_caught(past_others, "dispatch past another"))

    texts = _caller_texts()
    pasted = dict(texts)
    pasted[rel_path] += "\n# " + CANONICAL_COMMENTS[0] + "\n"
    case("a fold-analyze rationale comment pasted into a second caller is caught",
         any("lives once" in f for f in check_comment_homes(pasted)))

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
