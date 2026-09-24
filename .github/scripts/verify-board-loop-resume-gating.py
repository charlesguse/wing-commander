#!/usr/bin/env python3
"""Gate 97 -- board-loop.yml's resume jobs (fix, review, readiness) are
reachable on a cross-run resume, and a same-run handoff only reads an
upstream's outputs once that upstream actually succeeded.

WHY THIS EXISTS
---------------
#525: fix, review and readiness each have two entry branches in their
job-level `if:` -- a same-run handoff from the job above, and a cross-run
resume read off select's marker. None of the three carried a status
function, so GitHub wrapped each in its implicit `success()`, which is
false whenever ANY ancestor job was skipped. On a resume the ancestors
(triage, route, and on later steps fix/review) are always skipped, so
every resume past triage skipped the very job it existed to resume. Live:
run 36055743563 selected #396 at step=readiness and skipped every job,
and because the marker still read `readiness` every hourly run re-selected
#396 and did nothing -- the whole board wedged on one item.

#526: the fix job's post-push backstop breach files a spec-request and
stalls the item, but the job stays green with pr-number set, so review and
then readiness ran on the stalled PR in the same run and readiness filed a
second spec-request. review's same-run branch must exclude a breach.

WHAT IT CHECKS (static)
-----------------------
For each of fix / review / readiness, the job-level `if:` is parsed as a
GitHub expression and must:
  1. carry `!cancelled()` as a top-level conjunct, and no other status
     function (`always()` would start agent work on a cancelled run);
  2. carry `needs.select.result == 'success'` as a top-level conjunct, and
     `needs.resolve-model.result == 'success'` too when the job needs
     resolve-model (it runs an agent);
  3. guard every read of `needs.X.outputs.*` (X != select) with
     `needs.X.result == 'success'` in the SAME conjunction -- an OR branch
     never lends its guard to a sibling branch;
  4. keep the `vars.WING_COMMANDER_BOARD_LOOP_PAUSED != 'true'` conjunct.
review's branch that reads `needs.fix.outputs.pr-number` must also carry
`needs.fix.outputs.breach != 'true'`, and the fix job must export
`breach` from the final-diff-backstop step.

WHAT IT CHECKS (simulated)
--------------------------
A small evaluator runs the real `if:`s of select..readiness over the
fresh path and every resume scenario, modelling job-level `success()` as
"every transitive ancestor succeeded" (the skip-propagation rule), and
compares which jobs run against the expected set. `--simulate` prints the
table.

--self-test mutates the shipped workflow text (drops `!cancelled()`, a
result guard, the breach exclusion, the breach output, restores main's
pre-#525 conditions, ...) and asserts every mutation fails.
"""

import argparse
import os
import re
import sys

import yaml

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
WORKFLOW = os.path.join(ROOT, ".github", "workflows", "board-loop.yml")

RESUME_JOBS = ("fix", "review", "readiness")
SIM_JOBS = ("select", "resolve-model", "triage", "route", "fix", "review", "readiness")
PAUSE_VAR = "vars.WING_COMMANDER_BOARD_LOOP_PAUSED"
STATUS_FUNCS = ("success", "failure", "cancelled", "always")


# ---------------------------------------------------------------------------
# A minimal GitHub-expression parser: literals, property paths, function
# calls, !, ==, !=, &&, || and parentheses -- everything board-loop's
# job-level conditions use. Anything else is a parse error (and so a
# finding), never silently accepted.
# ---------------------------------------------------------------------------

_TOKEN = re.compile(r"""
    \s*(?:
      (?P<str>'(?:[^']|'')*')
    | (?P<num>\d+(?:\.\d+)?)
    | (?P<op>&&|\|\||==|!=|!|\(|\)|,)
    | (?P<ident>[A-Za-z_][A-Za-z0-9_\-]*(?:\.[A-Za-z_][A-Za-z0-9_\-]*)*)
    )""", re.X)


def tokenize(text):
    text = text.strip()
    if text.startswith("${{") and text.endswith("}}"):
        text = text[3:-2]
    pos, out = 0, []
    while pos < len(text):
        if text[pos:].strip() == "":
            break
        m = _TOKEN.match(text, pos)
        if not m or m.end() == pos:
            raise ValueError("cannot tokenize at: {0!r}".format(text[pos:pos + 30]))
        pos = m.end()
        if m.group("str") is not None:
            out.append(("lit", m.group("str")[1:-1].replace("''", "'")))
        elif m.group("num") is not None:
            out.append(("lit", m.group("num")))
        elif m.group("op") is not None:
            out.append(("op", m.group("op")))
        else:
            ident = m.group("ident")
            if ident in ("true", "false"):
                out.append(("lit", ident == "true"))
            else:
                out.append(("ident", ident))
    return out


class _Parser:
    def __init__(self, tokens):
        self.t, self.i = tokens, 0

    def peek(self):
        return self.t[self.i] if self.i < len(self.t) else (None, None)

    def take(self, kind=None, val=None):
        tok = self.peek()
        if tok[0] is None or (kind and tok[0] != kind) or (val and tok[1] != val):
            raise ValueError("expected {0} {1}, got {2}".format(kind, val, tok))
        self.i += 1
        return tok

    def parse(self):
        node = self.or_()
        if self.i != len(self.t):
            raise ValueError("trailing tokens: {0}".format(self.t[self.i:]))
        return node

    def or_(self):
        parts = [self.and_()]
        while self.peek() == ("op", "||"):
            self.take()
            parts.append(self.and_())
        return parts[0] if len(parts) == 1 else ("or", parts)

    def and_(self):
        parts = [self.cmp()]
        while self.peek() == ("op", "&&"):
            self.take()
            parts.append(self.cmp())
        return parts[0] if len(parts) == 1 else ("and", parts)

    def cmp(self):
        left = self.unary()
        if self.peek() in (("op", "=="), ("op", "!=")):
            op = self.take()[1]
            return (op, left, self.unary())
        return left

    def unary(self):
        if self.peek() == ("op", "!"):
            self.take()
            return ("not", self.unary())
        if self.peek() == ("op", "("):
            self.take()
            node = self.or_()
            self.take("op", ")")
            return node
        kind, val = self.peek()
        if kind == "lit":
            self.take()
            return ("lit", val)
        if kind == "ident":
            self.take()
            if self.peek() == ("op", "("):
                self.take()
                args = []
                if self.peek() != ("op", ")"):
                    args.append(self.or_())
                    while self.peek() == ("op", ","):
                        self.take()
                        args.append(self.or_())
                self.take("op", ")")
                return ("call", val, args)
            return ("path", val)
        raise ValueError("unexpected token {0}".format(self.peek()))


def parse_expr(text):
    return _Parser(tokenize(str(text))).parse()


def conjuncts(node):
    return node[1] if node[0] == "and" else [node]


def render(node):
    kind = node[0]
    if kind == "lit":
        return "'{0}'".format(node[1]) if isinstance(node[1], str) else str(node[1]).lower()
    if kind == "path":
        return node[1]
    if kind == "call":
        return "{0}({1})".format(node[1], ", ".join(render(a) for a in node[2]))
    if kind == "not":
        return "!" + render(node[1])
    if kind in ("==", "!="):
        return "{0} {1} {2}".format(render(node[1]), kind, render(node[2]))
    joiner = " && " if kind == "and" else " || "
    return "(" + joiner.join(render(p) for p in node[1]) + ")"


def uses_status_func(node):
    kind = node[0]
    if kind == "call":
        return node[1] in STATUS_FUNCS or any(uses_status_func(a) for a in node[2])
    if kind == "not":
        return uses_status_func(node[1])
    if kind in ("==", "!="):
        return uses_status_func(node[1]) or uses_status_func(node[2])
    if kind in ("and", "or"):
        return any(uses_status_func(p) for p in node[1])
    return False


# ---------------------------------------------------------------------------
# Static checks
# ---------------------------------------------------------------------------

def _is_cmp(node, op, path, value):
    return (node[0] == op and node[1] == ("path", path) and node[2] == ("lit", value))


def _output_reads(node, guards, out):
    """Collect (job, guards-in-scope) for every needs.X.outputs.* read.
    Descending into an AND lends the sibling conjuncts as guards;
    descending into an OR lends nothing."""
    kind = node[0]
    if kind == "path":
        m = re.match(r"needs\.([A-Za-z0-9_\-]+)\.outputs\.", node[1])
        if m:
            out.append((m.group(1), node[1], list(guards)))
    elif kind == "and":
        for idx, part in enumerate(node[1]):
            siblings = [p for j, p in enumerate(node[1]) if j != idx]
            _output_reads(part, guards + siblings, out)
    elif kind == "or":
        for part in node[1]:
            _output_reads(part, guards, out)
    elif kind == "not":
        _output_reads(node[1], guards, out)
    elif kind in ("==", "!="):
        _output_reads(node[1], guards, out)
        _output_reads(node[2], guards, out)
    elif kind == "call":
        for a in node[2]:
            _output_reads(a, guards, out)


def _branches_reading(node, path_prefix):
    """Every AND-group (as a conjunct list) at any depth that directly
    contains a read of a path starting with path_prefix."""
    found = []

    def direct_reads(n):
        if n[0] == "path":
            return n[1].startswith(path_prefix)
        if n[0] in ("==", "!="):
            return direct_reads(n[1]) or direct_reads(n[2])
        if n[0] == "not":
            return direct_reads(n[1])
        return False

    def walk(n, in_and):
        if n[0] in ("and", "or"):
            if n[0] == "and" and any(direct_reads(p) for p in n[1]):
                found.append(n[1])
            for p in n[1]:
                walk(p, n[0] == "and")
        elif direct_reads(n) and not in_and:
            found.append([n])

    walk(node, False)
    return found


def _writes_output(run, key):
    """True when a run: block writes `key=` (exactly that key, as a
    shell echo or an inline Python write) and routes to GITHUB_OUTPUT."""
    if "GITHUB_OUTPUT" not in run:
        return False
    return re.search(r"""(?:^|["'\s]){0}=""".format(re.escape(key)), run, re.M) is not None


def static_findings(doc):
    findings = []
    jobs = doc.get("jobs") or {}
    for name in RESUME_JOBS:
        job = jobs.get(name)
        if not job:
            findings.append("{0}: job missing from board-loop.yml".format(name))
            continue
        cond = job.get("if")
        if cond is None:
            findings.append("{0}: no job-level if:".format(name))
            continue
        try:
            tree = parse_expr(cond)
        except ValueError as exc:
            findings.append("{0}: if: does not parse ({1})".format(name, exc))
            continue
        top = conjuncts(tree)
        needs = job.get("needs") or []
        needs = [needs] if isinstance(needs, str) else list(needs)

        # Exactly `!cancelled()`: `always()` would also lift the implicit
        # success(), but would start the fixer/reviewer/readiness work on
        # a run someone cancelled.
        if not any(p == ("not", ("call", "cancelled", [])) for p in top):
            findings.append(
                "{0}: if: has no top-level `!cancelled()` conjunct -- the implicit "
                "success() skips this job whenever any ancestor was skipped, i.e. on "
                "every cross-run resume (#525); `always()` is not a substitute, it runs "
                "on a cancelled run too".format(name))
        if uses_status_func(("and", [p for p in top if p != ("not", ("call", "cancelled", []))])):
            findings.append(
                "{0}: if: uses a status function other than the one `!cancelled()` "
                "conjunct".format(name))
        for up in ["select"] + (["resolve-model"] if "resolve-model" in needs else []):
            if not any(_is_cmp(p, "==", "needs.{0}.result".format(up), "success") for p in top):
                findings.append(
                    "{0}: if: lacks top-level `needs.{1}.result == 'success'`".format(name, up))
        if not any(_is_cmp(p, "!=", PAUSE_VAR, "true") for p in top):
            findings.append("{0}: if: lacks the `{1} != 'true'` pause check".format(name, PAUSE_VAR))

        reads = []
        _output_reads(tree, [], reads)
        for up, path, guards in reads:
            if up == "select":
                continue
            if not any(_is_cmp(g, "==", "needs.{0}.result".format(up), "success") for g in guards):
                findings.append(
                    "{0}: if: reads `{1}` in a branch with no `needs.{2}.result == 'success'` "
                    "guard".format(name, path, up))

    fix = jobs.get("fix") or {}
    breach_out = str((fix.get("outputs") or {}).get("breach", ""))
    if "steps.final-diff-backstop.outputs.breach" not in breach_out:
        findings.append("fix: outputs: lacks `breach: ${{ steps.final-diff-backstop.outputs.breach }}` (#526)")
    # The output line alone proves nothing: it must name a step that
    # exists and actually writes `breach=` to GITHUB_OUTPUT, or `breach`
    # is always empty and review's exclusion never fires.
    backstop = [s for s in (fix.get("steps") or [])
                if isinstance(s, dict) and s.get("id") == "final-diff-backstop"]
    if not backstop:
        findings.append("fix: no step with id `final-diff-backstop` -- the `breach` output reads "
                        "a step that does not exist (#526)")
    elif not _writes_output(str(backstop[0].get("run", "")), "breach"):
        findings.append("fix: step `final-diff-backstop` never writes `breach=` to GITHUB_OUTPUT "
                        "-- the `breach` output is always empty (#526)")

    review = jobs.get("review") or {}
    try:
        rtree = parse_expr(review.get("if", "false"))
    except ValueError:
        rtree = None
    if rtree is not None:
        branches = _branches_reading(rtree, "needs.fix.outputs.pr-number")
        if not branches:
            findings.append("review: if: has no same-run branch reading needs.fix.outputs.pr-number")
        for branch in branches:
            if not any(_is_cmp(p, "!=", "needs.fix.outputs.breach", "true") for p in branch):
                findings.append(
                    "review: same-run branch lacks `needs.fix.outputs.breach != 'true'` -- a "
                    "post-push breach would still be reviewed and sent to readiness (#526)")
    return findings


# ---------------------------------------------------------------------------
# Simulation
# ---------------------------------------------------------------------------

class _Ctx:
    def __init__(self, results, outputs, ancestors, job, variables):
        self.results, self.outputs = results, outputs
        self.ancestors, self.job, self.vars = ancestors, job, variables


def _lookup(path, ctx):
    parts = path.split(".")
    if parts[0] == "vars":
        return ctx.vars.get(parts[1], "")
    if parts[0] == "needs" and len(parts) >= 3:
        dep = parts[1]
        if parts[2] == "result":
            return ctx.results.get(dep, "")
        if parts[2] == "outputs" and len(parts) == 4:
            # A failed job still exposes whatever its steps set before
            # failing; only a job that never ran has empty outputs.
            if ctx.results.get(dep) not in ("success", "failure"):
                return ""
            return ctx.outputs.get(dep, {}).get(parts[3], "")
    if parts[0] == "github" and parts[1] == "event_name":
        return ctx.vars.get("__event", "schedule")
    raise ValueError("simulator does not model `{0}`".format(path))


def _truthy(v):
    return bool(v) and v != "0"


def _eval(node, ctx):
    kind = node[0]
    if kind == "lit":
        return node[1]
    if kind == "path":
        return _lookup(node[1], ctx)
    if kind == "not":
        return not _truthy(_eval(node[1], ctx))
    if kind == "==":
        return str(_eval(node[1], ctx)).lower() == str(_eval(node[2], ctx)).lower()
    if kind == "!=":
        return str(_eval(node[1], ctx)).lower() != str(_eval(node[2], ctx)).lower()
    if kind == "and":
        return all(_truthy(_eval(p, ctx)) for p in node[1])
    if kind == "or":
        return any(_truthy(_eval(p, ctx)) for p in node[1])
    if kind == "call":
        anc = [ctx.results[a] for a in ctx.ancestors[ctx.job]]
        if node[1] == "success":
            return all(r == "success" for r in anc)
        if node[1] == "failure":
            return any(r == "failure" for r in anc)
        if node[1] == "cancelled":
            return False
        if node[1] == "always":
            return True
    raise ValueError("simulator does not model {0}".format(render(node)))


def _ancestors(jobs):
    memo = {}

    def rec(j):
        if j not in memo:
            deps = jobs[j].get("needs") or []
            deps = [deps] if isinstance(deps, str) else list(deps)
            acc = set()
            for d in deps:
                acc.add(d)
                acc |= rec(d)
            memo[j] = acc
        return memo[j]

    return {j: sorted(rec(j)) for j in SIM_JOBS}


def simulate(doc, scenario):
    """Returns {job: 'success'|'failure'|'skipped'} for one scenario.
    A job that runs takes the scenario's outputs for it; it fails only
    when the scenario says so."""
    jobs = doc["jobs"]
    ancestors = _ancestors(jobs)
    results, outputs = {}, {}
    variables = dict(scenario.get("vars", {}))
    for name in SIM_JOBS:
        cond = jobs[name].get("if")
        tree = parse_expr(cond) if cond is not None else ("lit", True)
        if not uses_status_func(tree):
            tree = ("and", [("call", "success", []), tree])
        ctx = _Ctx(results, outputs, ancestors, name, variables)
        if _truthy(_eval(tree, ctx)):
            results[name] = "failure" if name in scenario.get("fail", ()) else "success"
            outputs[name] = dict(scenario.get("outputs", {}).get(name, {}))
        else:
            results[name] = "skipped"
    return results


def _item(step, pr="", branch="", round_="0"):
    return {"issue-number": "396", "step": step, "pr": pr, "branch": branch, "round": round_}


SCENARIOS = [
    ("fresh: triage -> route=fix -> fix -> review converged -> readiness",
     {"outputs": {"select": _item("triage"), "triage": {"outcome": "proceed"},
                  "route": {"decision": "fix"}, "fix": {"pr-number": "42", "breach": "false"},
                  "review": {"pr-number": "42", "outcome": "converged"}}},
     SIM_JOBS),
    ("fresh: route=fix, review continues (not converged)",
     {"outputs": {"select": _item("triage"), "triage": {"outcome": "proceed"},
                  "route": {"decision": "fix"}, "fix": {"pr-number": "42", "breach": "false"},
                  "review": {"pr-number": "42", "outcome": "continue"}}},
     ("select", "resolve-model", "triage", "route", "fix", "review")),
    ("fresh: route=fix, post-push breach (#526)",
     {"outputs": {"select": _item("triage"), "triage": {"outcome": "proceed"},
                  "route": {"decision": "fix"}, "fix": {"pr-number": "42", "breach": "true"},
                  "review": {"pr-number": "42", "outcome": "converged"}}},
     ("select", "resolve-model", "triage", "route", "fix")),
    ("fresh: route=fix, fix job fails",
     {"fail": ("fix",),
      "outputs": {"select": _item("triage"), "triage": {"outcome": "proceed"},
                  "route": {"decision": "fix"}, "fix": {"pr-number": "42", "breach": "false"}}},
     ("select", "resolve-model", "triage", "route", "fix")),
    ("fresh: route=spec",
     {"outputs": {"select": _item("triage"), "triage": {"outcome": "proceed"},
                  "route": {"decision": "spec"}}},
     ("select", "resolve-model", "triage", "route")),
    ("fresh: triage closes",
     {"outputs": {"select": _item("triage"), "triage": {"outcome": "close"}}},
     ("select", "resolve-model", "triage")),
    ("no eligible item",
     {"outputs": {"select": {"issue-number": "", "step": ""}}},
     ("select",)),
    ("resume step=fix (branch, no PR) -> review converged -> readiness",
     {"outputs": {"select": _item("fix", branch="board/396"),
                  "fix": {"pr-number": "42", "breach": "false"},
                  "review": {"pr-number": "42", "outcome": "converged"}}},
     ("select", "resolve-model", "fix", "review", "readiness")),
    ("resume step=fix, fix job fails",
     {"fail": ("fix",),
      "outputs": {"select": _item("fix", branch="board/396"),
                  "fix": {"pr-number": "42", "breach": "false"}}},
     ("select", "resolve-model", "fix")),
    ("resume step=review, round continues",
     {"outputs": {"select": _item("review", pr="42", branch="board/396", round_="2"),
                  "review": {"pr-number": "42", "outcome": "continue"}}},
     ("select", "resolve-model", "review")),
    ("resume step=review -> converged -> readiness",
     {"outputs": {"select": _item("review", pr="42", branch="board/396", round_="2"),
                  "review": {"pr-number": "42", "outcome": "converged"}}},
     ("select", "resolve-model", "review", "readiness")),
    # An upstream that FAILS after setting its outputs: those outputs are
    # still readable, so only the explicit result guard keeps the next job
    # from acting on them.
    ("select fails after setting step=readiness",
     {"fail": ("select",),
      "outputs": {"select": _item("readiness", pr="42", branch="board/396")}},
     ("select",)),
    ("fresh: triage fails after outcome=proceed",
     {"fail": ("triage",),
      "outputs": {"select": _item("triage"), "triage": {"outcome": "proceed"},
                  "route": {"decision": "fix"}}},
     ("select", "resolve-model", "triage")),
    ("fresh: route fails after decision=fix",
     {"fail": ("route",),
      "outputs": {"select": _item("triage"), "triage": {"outcome": "proceed"},
                  "route": {"decision": "fix"}}},
     ("select", "resolve-model", "triage", "route")),
    ("fresh: review fails after outcome=converged",
     {"fail": ("review",),
      "outputs": {"select": _item("triage"), "triage": {"outcome": "proceed"},
                  "route": {"decision": "fix"}, "fix": {"pr-number": "42", "breach": "false"},
                  "review": {"pr-number": "42", "outcome": "converged"}}},
     ("select", "resolve-model", "triage", "route", "fix", "review")),
    ("resume step=review, review fails after outcome=converged",
     {"fail": ("review",),
      "outputs": {"select": _item("review", pr="42", branch="board/396", round_="2"),
                  "review": {"pr-number": "42", "outcome": "converged"}}},
     ("select", "resolve-model", "review")),
    ("resume step=readiness, resolve-model fails (readiness runs no agent)",
     {"fail": ("resolve-model",),
      "outputs": {"select": _item("readiness", pr="42", branch="board/396")}},
     ("select", "resolve-model", "readiness")),
    ("resume step=readiness (run 36055743563, #396)",
     {"outputs": {"select": _item("readiness", pr="42", branch="board/396")}},
     ("select", "resolve-model", "readiness")),
    ("resume step=readiness, board paused",
     {"vars": {"WING_COMMANDER_BOARD_LOOP_PAUSED": "true"},
      "outputs": {"select": _item("readiness", pr="42", branch="board/396")}},
     ("select", "resolve-model")),
    ("resume step=review, resolve-model fails",
     {"fail": ("resolve-model",),
      "outputs": {"select": _item("review", pr="42", branch="board/396")}},
     ("select", "resolve-model")),
]


def simulation_findings(doc, table=None):
    findings = []
    for title, scenario, expected in SCENARIOS:
        try:
            results = simulate(doc, scenario)
        except (ValueError, KeyError) as exc:
            findings.append("simulate `{0}`: {1}".format(title, exc))
            continue
        ran = tuple(j for j in SIM_JOBS if results[j] != "skipped")
        if table is not None:
            table.append((title, results))
        if set(ran) != set(expected):
            findings.append("simulate `{0}`: ran {1}, expected {2}".format(
                title, list(ran), list(expected)))
    return findings


def all_findings(text, table=None):
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        return ["board-loop.yml does not parse: {0}".format(exc)]
    return static_findings(doc) + simulation_findings(doc, table)


def print_table(table):
    short = {"resolve-model": "model"}
    heads = [short.get(j, j) for j in SIM_JOBS]
    width = max(len(t) for t, _ in table)
    print("{0}  {1}".format("scenario".ljust(width), "  ".join(h.ljust(9) for h in heads)))
    for title, results in table:
        cells = []
        for j in SIM_JOBS:
            r = results[j]
            cells.append({"success": "run", "failure": "run(fail)", "skipped": "-"}[r].ljust(9))
        print("{0}  {1}".format(title.ljust(width), "  ".join(cells)))


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

PRE_525 = {
    "fix": ("    if: (needs.route.outputs.decision == 'fix' || (needs.select.outputs.step == 'fix' "
            "&& needs.select.outputs.branch != '' && needs.select.outputs.pr == '')) "
            "&& vars.WING_COMMANDER_BOARD_LOOP_PAUSED != 'true'\n"),
}


def _replace_job_if(text, job, new_if_block):
    """Replaces a job's whole `if:` (single line or folded block) with
    new_if_block."""
    pat = re.compile(r"(^  {0}:\n(?:(?!  \S).*\n)*?)(    if: .*\n(?:      .*\n)*)".format(re.escape(job)), re.M)
    m = pat.search(text)
    if not m:
        raise AssertionError("self-test: cannot locate {0}'s if:".format(job))
    return text[:m.start(2)] + new_if_block + text[m.end(2):]


def _mutations(text):
    muts = []

    def sub(label, old, new, count=1, after=None):
        start = text.index(after) if after else 0
        idx = text.find(old, start)
        if idx < 0:
            raise AssertionError("self-test: fixture text not found for `{0}`: {1!r}".format(label, old))
        muts.append((label, text[:idx] + new + text[idx + len(old):]))

    sub("fix without !cancelled()", "      !cancelled()\n      && needs.select.result == 'success'",
        "      needs.select.result == 'success'", after="\n  fix:\n")
    sub("review without !cancelled()", "      !cancelled()\n      && needs.select.result == 'success'",
        "      needs.select.result == 'success'", after="\n  review:\n")
    sub("readiness without !cancelled()", "      !cancelled()\n      && needs.select.result == 'success'",
        "      needs.select.result == 'success'", after="\n  readiness:\n")
    sub("fix route branch without route.result guard",
        "(needs.route.result == 'success' && needs.route.outputs.decision == 'fix')",
        "needs.route.outputs.decision == 'fix'")
    sub("review same-run branch without fix.result guard",
        "needs.fix.result == 'success' && needs.fix.outputs.pr-number != ''",
        "needs.fix.outputs.pr-number != ''")
    sub("readiness same-run branch without review.result guard",
        "needs.review.result == 'success' && needs.review.outputs.outcome == 'converged'",
        "needs.review.outputs.outcome == 'converged'")
    sub("review without the breach exclusion",
        " && needs.fix.outputs.breach != 'true'", "")
    sub("fix without the breach output",
        "      breach: ${{ steps.final-diff-backstop.outputs.breach }}\n", "")
    sub("review without select.result guard",
        "      && needs.select.result == 'success'\n", "", after="\n  review:\n")
    sub("fix without resolve-model.result guard",
        "      && needs.resolve-model.result == 'success'\n", "", after="\n  fix:\n")
    sub("readiness without the pause check",
        "      ) && vars.WING_COMMANDER_BOARD_LOOP_PAUSED != 'true'\n", "      )\n",
        after="\n  readiness:\n")
    # A guard in a SIBLING OR-branch must not count.
    sub("fix route guard moved to the resume branch",
        "(needs.route.result == 'success' && needs.route.outputs.decision == 'fix')\n"
        "        || (needs.select.outputs.step == 'fix'",
        "(needs.route.outputs.decision == 'fix')\n"
        "        || (needs.route.result == 'success' && needs.select.outputs.step == 'fix'")
    # always() lifts the implicit success() too, but also runs on a
    # cancelled run -- it is not an accepted substitute.
    sub("readiness with always() in place of !cancelled()",
        "      !cancelled()\n      && needs.select.result == 'success'",
        "      always()\n      && needs.select.result == 'success'", after="\n  readiness:\n")
    sub("fix with always() in place of !cancelled()",
        "      !cancelled()\n      && needs.select.result == 'success'",
        "      always()\n      && needs.select.result == 'success'", after="\n  fix:\n")
    # The breach output must name a real step that really writes breach=.
    sub("final-diff-backstop step id renamed",
        "        id: final-diff-backstop\n", "        id: final-diff-backstop-renamed\n")
    sub("final-diff-backstop writes breached= instead of breach=",
        'fh.write("breach={0}\\n"', 'fh.write("breached={0}\\n"', after="\n  fix:\n")
    # main's pre-#525 conditions, verbatim.
    muts.append(("fix restored to pre-#525", _replace_job_if(text, "fix", PRE_525["fix"])))
    muts.append(("review restored to pre-#525", _replace_job_if(text, "review",
        "    if: >-\n      (\n"
        "        (needs.fix.result == 'success' && needs.fix.outputs.pr-number != '')\n"
        "        || (needs.select.outputs.step == 'review' && needs.select.outputs.pr != '')\n"
        "      ) && vars.WING_COMMANDER_BOARD_LOOP_PAUSED != 'true'\n")))
    muts.append(("readiness restored to pre-#525", _replace_job_if(text, "readiness",
        "    if: >-\n      (\n"
        "        (needs.review.result == 'success' && needs.review.outputs.outcome == 'converged')\n"
        "        || (needs.select.outputs.step == 'readiness' && needs.select.outputs.pr != '')\n"
        "      ) && vars.WING_COMMANDER_BOARD_LOOP_PAUSED != 'true'\n")))
    return muts


def run_selftest(text):
    failures = []
    base = all_findings(text)
    if base:
        failures.append("unmutated board-loop.yml is not clean: {0}".format(base))
    for label, mutated in _mutations(text):
        if mutated == text:
            failures.append("mutation `{0}` changed nothing".format(label))
            continue
        found = all_findings(mutated)
        if not found:
            failures.append("mutation `{0}` was NOT detected".format(label))
        else:
            print("  detected: {0} -> {1}".format(label, found[0]))
        # The simulator must see the live behaviour on its own, not only
        # through the static rules: main's pre-#525 conditions and a
        # missing breach exclusion each change which jobs run.
        if "pre-#525" in label or "breach exclusion" in label:
            sim = simulation_findings(yaml.safe_load(mutated))
            if not sim:
                failures.append("mutation `{0}`: the simulation alone did NOT detect it".format(label))
            else:
                print("    simulated: {0}".format(sim[0]))
    for f in failures:
        print("FAIL: " + f)
    print("verify-board-loop-resume-gating --self-test: {0} failure(s).".format(len(failures)))
    return 1 if failures else 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--simulate", action="store_true", help="print the scenario table")
    parser.add_argument("--workflow", default=WORKFLOW)
    args = parser.parse_args()
    with open(args.workflow, encoding="utf-8") as fh:
        text = fh.read()
    if args.self_test:
        return run_selftest(text)
    table = [] if args.simulate else None
    findings = all_findings(text, table)
    if table is not None:
        print_table(table)
        print()
    for f in findings:
        print("FAIL: " + f)
    print("verify-board-loop-resume-gating: {0} finding(s).".format(len(findings)))
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
