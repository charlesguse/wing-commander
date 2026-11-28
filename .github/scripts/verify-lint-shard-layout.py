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
  * one number, one gate: no two gate scripts the workflow runs open their
    docstring with the same "Gate N", and a step that runs a script which
    declares "Gate N" is itself named "Gate N ..." (two gates merged on the
    same day both took Gate 174, #889; the dispatch-input-types gate is
    now Gate 175). The step names hold the same rule for gates whose script
    claims no number: the steps named "Gate N" with nothing between the
    number and the separator ("Gate N — ...", "Gate N: ...") are one gate's
    own steps, so they must all run the same repository scripts (or be one
    inline step). A qualified step ("Gate N self-test", "Gate N fixtures")
    is a part of gate N and is not compared. Gates 22, 23, 157, 158, 166
    and 167 each named two different gates, and Gate 165 three, before
    #889 renumbered them to 185-192.

Which jobs are PR-time is the registry's own reading
(wc_gate_registry._job_runs_on_pull_request), so this gate and the local
runner cannot disagree about which jobs are units.

Usage:
    python3 .github/scripts/verify-lint-shard-layout.py
    python3 .github/scripts/verify-lint-shard-layout.py --self-test
"""
import ast
import copy
import os
import re
import shutil
import sys
import tempfile
import warnings

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
_CLAIM = re.compile(r"\s*Gate (\d+)\b")
_STEP_GATE = re.compile(r"^Gate (\d+)\b")
# What follows "Gate N" up to the first separator is the step's qualifier
# ("self-test", "fixtures", "wiring self-test"); none makes it a gate step.
_QUALIFIER_END = re.compile(r"\s+(?:\u2014|\u2013|--|-)\s|:")
_REPO_SCRIPT = re.compile(r"\.github/(?:scripts|actions)/[\w./-]+")
SCRIPTS = os.path.join(".github", "scripts")


def gate_claims(doc, scripts_dir=SCRIPTS):
    """{script: N} for every verify-*.py the workflow `doc` runs whose module
    docstring opens with "Gate N". A script with no such opening claims no
    number (many older gates name theirs only in the step)."""
    out = {}
    for job in (doc.get("jobs") or {}).values():
        for s in (job or {}).get("steps") or []:
            for script, _ in _CALL.findall(str((s or {}).get("run") or "")):
                path = os.path.join(scripts_dir, script)
                if script in out or not os.path.isfile(path):
                    continue
                with open(path, encoding="utf-8") as fh:
                    src = fh.read()
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    try:
                        ds = ast.get_docstring(ast.parse(src)) or ""
                    except SyntaxError:
                        continue
                m = _CLAIM.match(ds)
                if m:
                    out[script] = m.group(1)
    return out


def _claim_failures(doc, claims):
    """One number, one gate: no two scripts claim the same Gate N, and the
    step that runs a claiming script is named for that number."""
    fails, owners = [], {}
    for script, n in sorted(claims.items()):
        owners.setdefault(n, []).append(script)
    for n, scripts in sorted(owners.items(), key=lambda x: int(x[0])):
        if len(scripts) > 1:
            fails.append("Gate {0} is claimed by both {1}; give all but one "
                         "the next free gate number".format(
                             n, " and ".join(scripts)))
    for k, job in (doc.get("jobs") or {}).items():
        for s in (job or {}).get("steps") or []:
            name = str((s or {}).get("name") or "")
            m = _STEP_GATE.match(name)
            for script, _ in _CALL.findall(str((s or {}).get("run") or "")):
                n = claims.get(script)
                if n is not None and (not m or m.group(1) != n):
                    fails.append("step {0!r} in '{1}' runs {2}, which "
                                 "declares Gate {3}; name the step "
                                 "'Gate {3} ...'".format(name or "?", k,
                                                         script, n))
    return fails


def _step_number_failures(doc):
    """One number, one gate, read from step names alone: every unqualified
    "Gate N" step runs the same set of repository scripts, or N has one
    such step. A script's arguments do not count (Gate 124's open-issue
    check runs its own script with --check-open), and an inline step with
    no script is a gate of its own."""
    gates = {}
    for k, job in (doc.get("jobs") or {}).items():
        for s in (job or {}).get("steps") or []:
            name = str((s or {}).get("name") or "")
            m = _STEP_GATE.match(name)
            if not m or _QUALIFIER_END.split(name[m.end():], 1)[0].strip():
                continue
            run = "\n".join(l for l in str(s.get("run") or "").splitlines()
                             if not l.lstrip().startswith("#"))
            key = frozenset(_REPO_SCRIPT.findall(run)) or ("inline", k, name)
            gates.setdefault(m.group(1), {}).setdefault(key, []).append(
                "{0!r} in '{1}'".format(name, k))
    fails = []
    for n, keys in sorted(gates.items(), key=lambda x: int(x[0])):
        if len(keys) > 1:
            fails.append("Gate {0} names {1} different gates: {2}; give all "
                         "but one the next free gate number".format(
                             n, len(keys), "; ".join(
                                 v[0] for v in keys.values())))
    return fails


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


def check(doc, derived=None, claims=None):
    """Contract failures for `doc`. `derived` is derived_gate_set() of the
    same workflow; None skips item 8 (a caller with no file on disk).
    `claims` is gate_claims() of it; None skips the one-number-one-gate
    rule for the same reason."""
    fails = [] if claims is None else _claim_failures(doc, claims)
    fails += _step_number_failures(doc)
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

    def case(label, mutate, expect, claims=None):
        doc = copy.deepcopy(_base())
        mutate(doc)
        got = check(doc, claims=claims)
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
    claims = {"verify-a.py": "1", "verify-b.py": "2"}
    case("gate scripts with distinct numbers, each in a step of its number, pass",
         lambda d: None, None, claims=claims)
    case("two gate scripts claiming one number fail (the two Gate 174s, #889)",
         lambda d: J(d, "lint-shard-2")["steps"][0].update(
             {"name": "Gate 1 — b"}),
         "Gate 1 is claimed by both verify-a.py and verify-b.py",
         claims={"verify-a.py": "1", "verify-b.py": "1"})
    case("a step named for another number than its script declares fails",
         lambda d: J(d, "lint-shard-2")["steps"][0].update(
             {"name": "Gate 3 — b"}),
         "declares Gate 2", claims=claims)
    case("a self-test step named for another number fails",
         lambda d: J(d, "lint-shard-1")["steps"][2].update(
             {"name": "Gate 3 self-test — a"}),
         "declares Gate 1", claims=claims)
    step = lambda name, run: {"name": name, "if": "${{ !cancelled() }}",
                              "run": run}
    case("two unqualified steps of one number running different scripts "
         "fail (the two Gate 157s, #889)",
         lambda d: J(d, "lint-shard-2")["steps"][0].update(
             {"name": "Gate 1 — b"}),
         "Gate 1 names 2 different gates")
    case("an inline step and a script step of one number fail (the two "
         "Gate 23s, #889)",
         lambda d: J(d, "lint-shard-2")["steps"].append(
             step("Gate 1: inline", "python3 - <<'PY'\nprint(1)\nPY")),
         "Gate 1 names 2 different gates")
    case("two inline steps of one number fail",
         lambda d: (J(d, "lint-shard-2")["steps"].append(
             step("Gate 5 — x", "python3 - <<'PY'\nprint(1)\nPY")),
             J(d, "lint-shard-2")["steps"].append(
             step("Gate 5 — y", "python3 - <<'PY'\nprint(2)\nPY"))),
         "Gate 5 names 2 different gates")
    case("three gates on one number are all named (the three Gate 165s)",
         lambda d: (J(d, "lint-shard-2")["steps"][0].update(
             {"name": "Gate 1 — b"}),
             J(d, "lint-shard-2")["steps"].append(
             step("Gate 1 - c", "python3 .github/scripts/verify-c.py"))),
         "Gate 1 names 3 different gates")
    case("one gate's script run twice with other arguments, in two jobs, "
         "passes (Gate 124's --check-open)",
         lambda d: J(d, "names-and-tags")["steps"].append(
             step("Gate 1 — a, on main", "python3 .github/scripts/verify-a.py "
                  "--check-open")), None)
    case("qualified parts of one gate running other scripts pass (Gate "
         "171's fixtures and wiring)",
         lambda d: J(d, "lint-shard-1")["steps"].extend([
             step("Gate 1 fixtures — a", "bash .github/scripts/a-tests/run.sh"),
             step("Gate 1 wiring self-test — a",
                  "python3 .github/scripts/verify-a-wiring.py")]), None)
    case("a commented-out script in a gate step does not make it another gate",
         lambda d: J(d, "lint-shard-2")["steps"].append(
             step("Gate 2 — b, again", "# was .github/scripts/verify-z.py\n"
                  "python3 .github/scripts/verify-b.py --x")), None)
    results.extend(_claim_reader_cases())
    results.extend(_derivation_cases())
    bad = results.count(False)
    print("verify-lint-shard-layout self-test: {0}/{1} passed".format(
        len(results) - bad, len(results)))
    return 1 if bad else 0


def _claim_reader_cases():
    """gate_claims() over real files: a docstring that opens "Gate N" (after
    a shebang) claims N, one that only mentions a gate later claims none, and
    two files claiming one number fail check()."""
    out = []
    tmp = tempfile.mkdtemp()
    try:
        bodies = {
            "verify-a.py": '#!/usr/bin/env python3\n"""Gate 1 - a."""\n',
            "verify-b.py": '"""Gate 1: b, pasted with a\\w stray escape."""\n',
            "verify-c.py": '"""c, which Gate 1 only mentions."""\n'}
        for name, body in bodies.items():
            with open(os.path.join(tmp, name), "w", encoding="utf-8") as fh:
                fh.write(body)
        doc = copy.deepcopy(_base())
        doc["jobs"]["lint-shard-2"]["steps"][0]["name"] = "Gate 1 — b"
        doc["jobs"]["lint-shard-2"]["steps"].append(
            {"name": "C", "if": "${{ !cancelled() }}",
             "run": "python3 .github/scripts/verify-c.py"})
        got = gate_claims(doc, tmp)
        for label, ok in (
                ("the reader takes Gate N from each opening docstring",
                 got == {"verify-a.py": "1", "verify-b.py": "1"}),
                ("check() fails the duplicate the reader found",
                 any("claimed by both" in f
                     for f in check(doc, claims=got)))):
            out.append(ok)
            print("{0} {1}".format("ok  " if ok else "FAIL", label))
            if not ok:
                print("     got {0}".format(got))
    finally:
        shutil.rmtree(tmp)
    return out


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
    fails = check(doc, derived_gate_set(WORKFLOW), gate_claims(doc))
    for f in fails:
        print("::error file={0}::Gate 174: {1}".format(WORKFLOW, f))
    if fails:
        return 1
    print("Gate 174: the sharded lint layout holds its contract.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
