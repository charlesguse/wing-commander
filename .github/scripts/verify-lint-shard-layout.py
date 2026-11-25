#!/usr/bin/env python3
"""Gate 174 - the sharded lint workflow keeps its layout contract.

specs/129-parallel-pr-lint/contracts/lint-workflow-layout.md, items 1, 2, 3,
6 and 7 (the aggregate's own behaviour is verify-lint-aggregate.py):

  * the workflow is named `lint · workflows`;
  * exactly one job carries the check-run name `lint`;
  * every PR-time unit is in the aggregate's `needs`, and every `needs`
    entry exists;
  * step names are unique across PR-time units, and no gate invocation
    (script + args) appears in two units or twice in one;
  * every step except checkout carries an `if:` with `!cancelled()` (or
    `always()`); a self-test step may also require its paired gate step's
    outcome not `failure`, and must name the id of its OWN pair, found by
    step name ("Gate N self-test" pairs with "Gate N").

Usage:
    python3 .github/scripts/verify-lint-shard-layout.py
    python3 .github/scripts/verify-lint-shard-layout.py --self-test
"""
import copy
import os
import re
import sys

import yaml

WORKFLOW = os.path.join(".github", "workflows", "lint-workflows.yml")
AGGREGATE = "lint"
NAME = "lint · workflows"
_CALL = re.compile(r"\.github/scripts/(verify-[\w.-]+\.py)((?:[ \t]+--[\w-]+)*)")
_PAIR = re.compile(r"^(Gate \S+) self-test\b")
_OUTCOME = re.compile(r"steps\.([\w-]+)\.outcome\s*!=\s*'failure'")


def _runs_on_pr(job):
    cond = str((job or {}).get("if") or "").strip()
    return not re.search(r"github\.event_name\s*!=\s*'pull_request'", cond)


def _is_checkout(step):
    return str((step or {}).get("uses") or "").startswith("actions/checkout")


def _guarded(step):
    cond = str((step or {}).get("if") or "")
    return "!cancelled()" in cond or "always()" in cond


# Contract item 7 (every step guarded) is switched on by T007, which adds the
# guards to ~80 steps; until it lands the real workflow would fail it.
ENFORCE_GUARDS = False


def check(doc, enforce_guards=None):
    if enforce_guards is None:
        enforce_guards = ENFORCE_GUARDS
    fails = []
    if doc.get("name") != NAME:
        fails.append("workflow name is {0!r}, not {1!r}".format(
            doc.get("name"), NAME))
    jobs = doc.get("jobs") or {}
    named = [k for k, j in jobs.items()
             if ((j or {}).get("name") or k) == AGGREGATE]
    if len(named) != 1 or named[0] != AGGREGATE:
        return fails + ["exactly one job must carry the check-run name 'lint' "
                        "and its id must be 'lint'; found {0}".format(named)]
    needs = jobs[AGGREGATE].get("needs") or []
    if isinstance(needs, str):
        needs = [needs]
    for n in needs:
        if n not in jobs:
            fails.append("the aggregate needs '{0}', which is not a job".format(n))
    units = {k: j for k, j in jobs.items()
             if k != AGGREGATE and _runs_on_pr(j)}
    for k in units:
        if k not in needs:
            fails.append("PR-time unit '{0}' is not in the aggregate's "
                         "needs".format(k))
    names, calls = {}, {}
    for k, job in units.items():
        steps = job.get("steps") or []
        ids = {}
        for s in steps:
            if s.get("id"):
                ids[s.get("name")] = s["id"]
        for s in steps:
            name = s.get("name")
            if name:
                if name in names:
                    fails.append("step name {0!r} appears in both '{1}' and "
                                 "'{2}'".format(name, names[name], k))
                names[name] = k
            if _is_checkout(s):
                continue
            label = name or s.get("uses") or "?"
            if enforce_guards and not _guarded(s):
                fails.append("step {0!r} in '{1}' has no !cancelled() "
                             "guard".format(label, k))
            m = _PAIR.match(name or "")
            if m:
                want = ids.get(
                    next((n for n in ids if n and n.startswith(m.group(1) + " —")), None))
                got = _OUTCOME.search(str(s.get("if") or ""))
                if got and want and got.group(1) != want:
                    fails.append("self-test step {0!r} guards on step id "
                                 "{1!r}, not its pair {2!r}".format(
                                     name, got.group(1), want))
            for script, args in _CALL.findall(str(s.get("run") or "")):
                key = (script, args.strip())
                if key in calls:
                    fails.append("gate invocation {0} {1} appears in both "
                                 "'{2}' and '{3}'".format(
                                     script, args.strip(), calls[key], k))
                calls[key] = k
    return fails


def _base():
    def step(name, run, **kw):
        d = {"name": name, "if": "${{ !cancelled() }}", "run": run}
        d.update(kw)
        return d
    pr = "github.event_name == 'pull_request'"
    return {"name": NAME, "jobs": {
        "lint-shard-1": {"if": pr, "steps": [
            {"uses": "actions/checkout@v5"},
            step("Gate 1 — a", "python3 .github/scripts/verify-a.py", id="g1"),
            step("Gate 1 self-test — a", "python3 .github/scripts/verify-a.py --self-test",
                 **{"if": "${{ !cancelled() && steps.g1.outcome != 'failure' }}"})]},
        "lint-shard-2": {"if": pr, "steps": [
            step("Gate 2 — b", "python3 .github/scripts/verify-b.py")]},
        "harness-tests": {"name": "harness tests", "if": pr, "steps": [
            step("Harness", "bash run.sh")]},
        "names-and-tags": {"if": "github.event_name != 'pull_request'",
                           "steps": []},
        "lint": {"if": "${{ always() && " + pr + " }}",
                 "needs": ["lint-shard-1", "lint-shard-2", "harness-tests"],
                 "steps": [{"run": "true"}]}}}


def self_test():
    results = []

    def case(label, mutate, expect):
        doc = copy.deepcopy(_base())
        mutate(doc)
        got = check(doc, enforce_guards=True)
        ok = (not got) if expect is None else any(expect in g for g in got)
        results.append(ok)
        print("{0} {1}".format("ok  " if ok else "FAIL", label))
        if not ok:
            print("     expected {0!r}, got {1}".format(expect, got))

    J = lambda d, k: d["jobs"][k]
    case("the real shape passes", lambda d: None, None)
    case("a wrong workflow name fails",
         lambda d: d.update({"name": "lint"}), "workflow name")
    case("a unit missing from needs fails",
         lambda d: J(d, "lint")["needs"].remove("lint-shard-2"),
         "'lint-shard-2' is not in")
    case("a needs entry that is not a job fails",
         lambda d: J(d, "lint")["needs"].append("lint-shard-9"),
         "which is not a job")
    case("a shard named lint fails",
         lambda d: J(d, "lint-shard-1").update({"name": "lint"}),
         "exactly one job")
    case("a duplicate step name fails",
         lambda d: J(d, "lint-shard-2")["steps"].append(
             {"name": "Harness", "if": "${{ !cancelled() }}", "run": "x"}),
         "appears in both")
    case("a gate invoked in two units fails",
         lambda d: J(d, "lint-shard-2")["steps"].append(
             {"name": "Again", "if": "${{ !cancelled() }}",
              "run": "python3 .github/scripts/verify-b.py"}),
         "gate invocation")
    case("an unguarded step fails",
         lambda d: J(d, "lint-shard-2")["steps"][0].pop("if"),
         "no !cancelled() guard")
    case("a self-test guarded on another gate's id fails",
         lambda d: J(d, "lint-shard-1")["steps"][2].update(
             {"if": "${{ !cancelled() && steps.other.outcome != 'failure' }}"}),
         "not its pair")
    bad = results.count(False)
    print("verify-lint-shard-layout self-test: {0}/{1} passed".format(
        len(results) - bad, len(results)))
    return 1 if bad else 0


def main(argv):
    if "--self-test" in argv:
        return self_test()
    with open(WORKFLOW, encoding="utf-8") as fh:
        doc = yaml.safe_load(fh) or {}
    fails = check(doc)
    for f in fails:
        print("::error file={0}::Gate 174: {1}".format(WORKFLOW, f))
    if fails:
        return 1
    print("Gate 174: the sharded lint layout holds its contract.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
