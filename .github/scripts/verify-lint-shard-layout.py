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
    step name ("Gate N self-test" pairs with "Gate N");
  * item 8: the gate set wc_gate_registry derives for run-local-gates.py
    (pr_time_invocations plus the runnable inline heredoc steps) equals the
    union of the units' own gate calls. The aggregate is exempt by name
    (wc_gate_registry.AGGREGATE_JOB, T006) because it may carry no gate at
    all: a repository script or a python heredoc in its steps fails here,
    so a gate cannot hide in the one job that is not a unit.

Which jobs are PR-time is the registry's own reading
(wc_gate_registry._job_runs_on_pull_request), so this gate and the local
runner cannot disagree about which jobs are units.

Usage:
    python3 .github/scripts/verify-lint-shard-layout.py
    python3 .github/scripts/verify-lint-shard-layout.py --self-test
"""
import copy
import os
import re
import sys
import tempfile

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wc_gate_registry as registry  # noqa: E402
import wc_gha_expr as gha  # noqa: E402

WORKFLOW = os.path.join(".github", "workflows", "lint-workflows.yml")
AGGREGATE = "lint"
NAME = "lint · workflows"
_CALL = re.compile(r"\.github/scripts/(verify-[\w.-]+\.py)((?:[ \t]+--[\w-]+)*)")
_PAIR = re.compile(r"^(Gate \S+) self-test\b")
_OUTCOME = re.compile(r"steps\.([\w-]+)\.outcome\s*!=\s*'failure'")


def _runs_on_pr(job):
    return registry._job_runs_on_pull_request(job)


def _is_checkout(step):
    return str((step or {}).get("uses") or "").startswith("actions/checkout")


class _Ctx(dict):
    """Status functions as given; every steps.<id>.outcome reads 'success'
    (a self-test's own gate passed, so its pair guard holds)."""

    def get(self, key, default=None):
        if str(key).startswith("steps.") and key.endswith(".outcome"):
            return "success"
        return super().get(key, default)


def _guarded(step):
    """FR-009: the step still runs when an EARLIER step failed (so one
    failing gate does not hide the rest), and on a clean run. Evaluated
    with wc_gha_expr, so `failure() && !cancelled()` or `always() && false`
    -- which a substring match accepts -- fail."""
    cond = (step or {}).get("if")
    if cond in (None, ""):
        return False
    expr = str(cond).strip()
    for ok, failed in ((True, False), (False, True)):
        ctx = _Ctx({"always()": True, "cancelled()": False,
                    "success()": ok, "failure()": failed})
        try:
            if not gha.evaluate_if(expr, ctx, known=("steps.", "github.")):
                return False
        except ValueError:
            return False
    return True


def _unit_gate_set(units):
    """(script, args) calls and runnable heredoc step names, over the units.

    Read per unit with the registry's own call reader, so a divergence
    between this and the registry's derived set is a job the registry
    reads differently, never a second grammar disagreeing with the first.
    """
    scripts = set(registry.gate_scripts())
    calls, inline = set(), set()
    for job in units.values():
        for s in (job or {}).get("steps") or []:
            run = str((s or {}).get("run") or "")
            if not run:
                continue
            if registry.LOOSE_PY_HEREDOC_RE.search(run):
                inline.add(str(s.get("name") or "(unnamed step)"))
            text = "\n".join(l for l in run.splitlines()
                             if not l.lstrip().startswith("#"))
            for script in scripts:
                for args in registry._invocations_in_run(text, script):
                    calls.add((script, tuple(args)))
    return calls, inline


def derived_gate_set(path):
    """What run-local-gates.py derives from the workflow at `path`."""
    calls = {(s, tuple(a))
             for s, a in registry.pr_time_invocations(workflow=path)}
    runnable, unrunnable = registry.pr_time_inline_steps(workflow=path)
    return calls, {n for n, _ in runnable} | {n for n, _ in unrunnable}


def check(doc, derived=None):
    """Contract failures for `doc`. `derived` is derived_gate_set() of the
    same workflow; None skips item 8 (a caller with no file on disk)."""
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
             if _runs_on_pr(j) and not registry._is_aggregate(k, j)}
    for k in units:
        if k not in needs:
            fails.append("PR-time unit '{0}' is not in the aggregate's "
                         "needs".format(k))
    for s in jobs[AGGREGATE].get("steps") or []:
        run = str((s or {}).get("run") or "")
        if (registry.REPO_SCRIPT_RE.search(run)
                or registry.LOOSE_PY_HEREDOC_RE.search(run)):
            fails.append("the aggregate step {0!r} runs a gate; the aggregate "
                         "is not a unit and may carry none".format(
                             s.get("name") or "?"))
    if derived is not None:
        mine = _unit_gate_set(units)
        for what, a, b in (("gate call", mine[0], derived[0]),
                           ("inline gate step", mine[1], derived[1])):
            for x in sorted(b - a, key=str):
                fails.append("run-local-gates.py derives {0} {1} that no unit "
                             "runs".format(what, x))
            for x in sorted(a - b, key=str):
                fails.append("a unit runs {0} {1} that run-local-gates.py "
                             "does not derive".format(what, x))
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
            if not _guarded(s):
                fails.append("step {0!r} in '{1}' has no !cancelled() "
                             "guard".format(label, k))
            m = _PAIR.match(name or "")
            if m:
                # Any separator pairs (em dash, colon, hyphen), so a renamed
                # gate step cannot silently drop the guard checks below
                # (code review of #1233). A self-test with no gate step in
                # its unit at all (Gates 40, 41 are standalone) has no pair.
                # The pair is found among every named step, not only those
                # with an `id:` (code review of #1233): a guarded self-test
                # whose gate step lost its id, or has no gate step in the
                # unit, read as having no pair, and the "names its own
                # pair" check below was skipped. The guard itself stays
                # optional (FR-009, contract item 7, R3).
                pair = next((p for p in steps if p.get("name")
                             and not _PAIR.match(p["name"])
                             and re.match(re.escape(m.group(1)) + r"(?!\w)",
                                          p["name"])), None)
                want = (pair or {}).get("id")
                got = _OUTCOME.search(str(s.get("if") or ""))
                if got and got.group(1) in ids.values() and pair is None:
                    fails.append("self-test step {0!r} guards on step id "
                                 "{1!r}, but '{2}' has no {3!r} gate step to "
                                 "pair it with; guard on the paired gate "
                                 "step's id or drop the guard".format(
                                     name, got.group(1), k, m.group(1)))
                elif got and pair is not None and not want:
                    fails.append("self-test step {0!r} guards on step id "
                                 "{1!r}, but its paired gate step {2!r} has "
                                 "no `id:`, so the pair cannot be checked; "
                                 "give the gate step that id or drop the "
                                 "guard".format(name, got.group(1),
                                                pair["name"]))
                elif not got and want:
                    fails.append("self-test step {0!r} lacks the paired "
                                 "steps.{1}.outcome != 'failure' guard".format(
                                     name, want))
                elif got and got.group(1) not in ids.values():
                    # A step id from another job reads as '' here, so the
                    # guard would never hold the self-test back: the pair
                    # was split across units.
                    fails.append("self-test step {0!r} guards on step id "
                                 "{1!r}, which is not a step of '{2}'; a "
                                 "gate and its self-test share a "
                                 "unit".format(name, got.group(1), k))
                elif got and want and got.group(1) != want:
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
        got = check(doc)
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
    case("a guard that skips after a failure fails",
         lambda d: J(d, "lint-shard-2")["steps"][0].update(
             {"if": "${{ failure() && !cancelled() }}"}),
         "no !cancelled() guard")
    case("a guard that is always false fails",
         lambda d: J(d, "lint-shard-2")["steps"][0].update(
             {"if": "${{ always() && false }}"}),
         "no !cancelled() guard")
    case("a self-test without its pair guard fails",
         lambda d: J(d, "lint-shard-1")["steps"][2].update(
             {"if": "${{ !cancelled() }}"}),
         "lacks the paired")
    case("an aggregate with no needs is one definition with the registry",
         lambda d: J(d, "lint").pop("needs"), "not in the aggregate's needs")
    case("a self-test guarded on another gate's id fails",
         lambda d: (J(d, "lint-shard-1")["steps"].append(
             {"name": "Gate 9 — other", "id": "other",
              "if": "${{ !cancelled() }}", "run": "true"}),
             J(d, "lint-shard-1")["steps"][2].update(
             {"if": "${{ !cancelled() && steps.other.outcome != 'failure' }}"})),
         "not its pair")
    case("a colon-named gate step still pairs, so a missing guard fails",
         lambda d: (J(d, "lint-shard-1")["steps"][1].update(
             {"name": "Gate 1: a"}),
             J(d, "lint-shard-1")["steps"][2].update(
             {"if": "${{ !cancelled() }}"})),
         "lacks the paired")
    case("a hyphen-named gate step still pairs, so a wrong guard fails",
         lambda d: (J(d, "lint-shard-1")["steps"][1].update(
             {"name": "Gate 1 - a"}),
             J(d, "lint-shard-1")["steps"].append(
             {"name": "Gate 9 — other", "id": "other",
              "if": "${{ !cancelled() }}", "run": "true"}),
             J(d, "lint-shard-1")["steps"][2].update(
             {"if": "${{ !cancelled() && steps.other.outcome != 'failure' }}"})),
         "not its pair")
    case("a guarded self-test whose gate step has no id fails",
         lambda d: J(d, "lint-shard-1")["steps"][1].pop("id"),
         "has no `id:`")
    case("a guard on another gate's id beside an id-less pair fails",
         lambda d: (J(d, "lint-shard-1")["steps"][1].pop("id"),
                    J(d, "lint-shard-1")["steps"].append(
                        {"name": "Gate 9 — other", "id": "other",
                         "if": "${{ !cancelled() }}", "run": "true"}),
                    J(d, "lint-shard-1")["steps"][2].update(
                        {"if": "${{ !cancelled() && steps.other.outcome != 'failure' }}"})),
         "has no `id:`")
    case("a guarded self-test with no gate step in its unit fails",
         lambda d: (J(d, "lint-shard-1")["steps"][1].update({"name": "Gate 7 — a"}),
                    J(d, "lint-shard-1")["steps"][2].update(
                        {"name": "Gate 8 self-test — a"})),
         "gate step to pair it with")
    case("an unguarded self-test whose gate step has no id passes (the guard is optional)",
         lambda d: (J(d, "lint-shard-1")["steps"][1].pop("id"),
                    J(d, "lint-shard-1")["steps"][2].update(
                        {"if": "${{ !cancelled() }}"})),
         None)
    case("a self-test split from its gate into another unit fails",
         lambda d: J(d, "lint-shard-2")["steps"].append(
             J(d, "lint-shard-1")["steps"].pop(2)),
         "share a unit")
    case("an aggregate that runs a gate script fails",
         lambda d: J(d, "lint")["steps"].append(
             {"name": "sneak", "run": "python3 .github/scripts/verify-c.py"}),
         "may carry none")
    case("an aggregate that runs a python heredoc fails",
         lambda d: J(d, "lint")["steps"].append(
             {"name": "sneak", "run": "python3 - <<'PY'\nprint(1)\nPY"}),
         "may carry none")
    results.extend(_derivation_cases())
    bad = results.count(False)
    print("verify-lint-shard-layout self-test: {0}/{1} passed".format(
        len(results) - bad, len(results)))
    return 1 if bad else 0


def _derivation_cases():
    """Item 8 against the real registry, over a throwaway workflow file.

    The registry reads gate scripts from the working tree, so the fixture
    invokes real gate scripts; only the job layout is synthetic.
    """
    out = []
    real = ".github/scripts/verify-lint-aggregate.py"
    other = ".github/scripts/verify-lint-shard-layout.py"

    def case(label, doc, derived_override, expect):
        fd, path = tempfile.mkstemp(suffix=".yml")
        os.close(fd)
        try:
            with open(path, "w", encoding="utf-8") as fh:
                yaml.safe_dump(doc, fh, allow_unicode=True)
            derived = derived_gate_set(path)
            if derived_override:
                derived = derived_override(derived)
            got = check(doc, derived)
        finally:
            os.unlink(path)
        ok = (not got) if expect is None else any(expect in g for g in got)
        print("{0} {1}".format("ok  " if ok else "FAIL", label))
        if not ok:
            print("     expected {0!r}, got {1}".format(expect, got))
        out.append(ok)

    doc = _base()
    doc["jobs"]["lint-shard-1"]["steps"][1]["run"] = "python3 " + real
    doc["jobs"]["lint-shard-1"]["steps"][2]["run"] = (
        "python3 " + real + " --self-test")
    doc["jobs"]["lint-shard-2"]["steps"][0]["run"] = "python3 " + other
    doc["jobs"]["harness-tests"]["steps"][0]["run"] = (
        "python3 - <<'PY'\nprint(1)\nPY")
    case("the derived set equals the union over units", doc, None, None)
    case("a derived gate no unit runs fails", doc,
         lambda d: (d[0] | {(".github/scripts/verify-x.py", ())}, d[1]),
         "that no unit runs")
    case("a unit gate the derivation misses fails", doc,
         lambda d: (d[0] - {(other, ())}, d[1]),
         "does not derive")
    case("an inline step the derivation misses fails", doc,
         lambda d: (d[0], set()), "inline gate step")
    moved = copy.deepcopy(doc)
    step = moved["jobs"]["lint-shard-2"]["steps"].pop(0)
    moved["jobs"]["lint-shard-1"]["steps"].append(step)
    case("a gate moved to another unit is still derived (US3 scenario 2)",
         moved, None, None)
    return out


def main(argv):
    if "--self-test" in argv:
        return self_test()
    with open(WORKFLOW, encoding="utf-8") as fh:
        doc = yaml.safe_load(fh) or {}
    fails = check(doc, derived_gate_set(WORKFLOW))
    for f in fails:
        print("::error file={0}::Gate 174: {1}".format(WORKFLOW, f))
    if fails:
        return 1
    print("Gate 174: the sharded lint layout holds its contract.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
