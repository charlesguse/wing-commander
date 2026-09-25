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

#532: readiness's ready-report step (the one gated on
`steps.decide.outputs.ready == 'true'`) must write its marker with
board_eligibility.AWAITING_MERGE_STEP, never 'readiness' -- a ready item
left at step=readiness stays in-flight while its PR is open, so every run
re-selected it, re-ran readiness, and re-posted the same report until a
human merged, the same one-item wedge as #525 by a different road.

WHAT IT CHECKS (simulated)
--------------------------
A small evaluator runs the real `if:`s of select..readiness over the
fresh path and every resume scenario, modelling job-level `success()` as
"every transitive ancestor succeeded" (the skip-propagation rule), and
compares which jobs run against the expected set. `--simulate` prints the
table.

WHAT IT CHECKS (executed, #532)
-------------------------------
The resume step's `step_resolution_json` heredoc is extracted and run
against RESUME_CASES: an awaiting-merge marker whose PR is OPEN or
unresolved (with or without a board:owned fallback PR) resolves to the
no-op step awaiting-merge with no fallback adoption; one whose PR is
CLOSED/MERGED goes to triage with pr/branch/round/base_sha cleared; plus
readiness/prove regression rows. The select step's `pr_numbers_to_check`
heredoc is run against a fixture and must list an awaiting-merge marker's
PR (i.e. AWAITING_MERGE_STEP stays in FIX_OR_LATER_STEPS).

WHAT IT CHECKS (#555)
---------------------
Board item markers are read only from the loop's own App comments. Each
marker-reading step (select, resume, prove-gate) must take BOT_LOGIN from
wing-commander-context, project user{login,type} in its comments fetch,
and pass BOT_LOGIN to its reader; the select lookup must skip a marker
another author posted. RESUME_CASES also pin the resume guards: a marker
branch not named fix/<issue>-<slug>, or a marker PR that is not
board:owned with its head in this repository, is not adopted (triage,
FR-022 cleared; an awaiting-merge marker still holds as a no-op). The
resume step's PR-ownership jq is run on OWNED_CASES.

--self-test mutates the shipped workflow text (drops `!cancelled()`, a
result guard, the breach exclusion, the breach output, restores main's
pre-#525 conditions, ...) and asserts every mutation fails.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

import yaml

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
WORKFLOW = os.path.join(ROOT, ".github", "workflows", "board-loop.yml")
BOT_LOGIN = "wing-commander-bot[bot]"

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

    readiness = jobs.get("readiness") or {}
    ready_steps = [s for s in (readiness.get("steps") or [])
                   if isinstance(s, dict)
                   and str(s.get("if", "")).replace(" ", "") == "steps.decide.outputs.ready=='true'"
                   and "write_marker(" in str(s.get("run", ""))]
    if not ready_steps:
        findings.append("readiness: no step gated on `steps.decide.outputs.ready == 'true'` writes "
                        "a board item marker (#532)")
    for s in ready_steps:
        run = str(s.get("run", ""))
        if ("from board_eligibility import AWAITING_MERGE_STEP" not in run
                or "write_marker(AWAITING_MERGE_STEP," not in run):
            findings.append(
                "readiness: ready-report step `{0}` does not write its marker with "
                "board_eligibility.AWAITING_MERGE_STEP -- a ready item left at any other step "
                "holds the board until a human merges (#532)".format(s.get("name")))
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
    # #532: select() never picks an awaiting-merge item while its PR is
    # open, but if a race hands one to resume anyway, resume resolves it to
    # step=awaiting-merge (with the PR still set) and nothing past
    # resolve-model may run -- above all not readiness again.
    ("resume step=awaiting-merge, PR still open (#532)",
     {"outputs": {"select": _item("awaiting-merge", pr="42")}},
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


# ---------------------------------------------------------------------------
# Executed heredocs (#532): the select job's PR-lookup pass and the resume
# step's step resolution are inline Python in board-loop.yml. Both are
# pulled out of the workflow and run for real against board_eligibility.py,
# so a dropped awaiting-merge clause or an awaiting-merge step missing from
# FIX_OR_LATER_STEPS fails here, not in production.
# ---------------------------------------------------------------------------

_RUN_CACHE = {}


def _heredoc(run, var):
    m = re.search(re.escape(var) + r"=.*?<<'PYEOF'\n(.*?)\nPYEOF", run, re.S)
    return m.group(1) if m else None


def _step_run(doc, job, step_id):
    for s in ((doc.get("jobs") or {}).get(job) or {}).get("steps") or []:
        if isinstance(s, dict) and s.get("id") == step_id:
            return str(s.get("run", ""))
    return ""


def _exec_heredoc(code, env, scripts_root):
    """Runs one extracted heredoc with cwd=scripts_root (it imports from
    the relative .github/scripts, exactly as it does on the runner).
    Memoized: most self-test mutations leave the heredocs untouched."""
    key = (code, scripts_root, tuple(sorted(env.items())))
    if key not in _RUN_CACHE:
        full_env = dict(os.environ)
        full_env.update(env)
        proc = subprocess.run([sys.executable, "-"], input=code, text=True,
                              capture_output=True, env=full_env, cwd=scripts_root)
        _RUN_CACHE[key] = (proc.returncode, proc.stdout, proc.stderr)
    return _RUN_CACHE[key]


def _resume_env(step, marker_pr, pr_from_marker, pr_state, pr_number,
                from_fallback=False, branch="fix/396-board-item", round_="2", base_sha="abc1234",
                pr_owned=True):
    return {
        "MARKER_STEP": step, "MARKER_JSON": '{"step": "%s"}' % step if step else "null",
        "BRANCH": branch, "MARKER_PR": marker_pr,
        "PR_FROM_MARKER": "true" if pr_from_marker else "false",
        "PR_FROM_FALLBACK": "true" if from_fallback else "false",
        "PR_STATE": pr_state, "PR_NUMBER": pr_number,
        "MARKER_ROUND": round_, "MARKER_BASE_SHA": base_sha,
        "PR_OWNED": "true" if pr_owned else "false", "ISSUE_NUMBER": "396",
    }


_CLEARED = {"pr_number": "", "pr_state": "", "branch": "", "round": "0", "base_sha": ""}

# (title, env, expected subset of the step_resolution_json output)
RESUME_CASES = [
    ("awaiting-merge, PR OPEN -> no-op",
     _resume_env("awaiting-merge", "42", True, "OPEN", "42"),
     {"step": "awaiting-merge", "recovered_via_fallback": False, "pr_number": "42"}),
    ("awaiting-merge, PR unresolved, no fallback PR -> no-op",
     _resume_env("awaiting-merge", "42", False, "", ""),
     {"step": "awaiting-merge", "recovered_via_fallback": False, "pr_number": ""}),
    # The transient-5xx case: without clause 0 this became step=review on
    # a PR a human now owns (spec 057 FR-054).
    ("awaiting-merge, PR unresolved, board:owned fallback PR found -> no-op",
     _resume_env("awaiting-merge", "42", False, "OPEN", "99", from_fallback=True),
     {"step": "awaiting-merge", "recovered_via_fallback": False, "pr_number": ""}),
    ("awaiting-merge, PR CLOSED -> triage, FR-022 cleared",
     _resume_env("awaiting-merge", "42", True, "CLOSED", "42"),
     dict(_CLEARED, step="triage")),
    ("awaiting-merge, PR MERGED (issue still open) -> triage, FR-022 cleared",
     _resume_env("awaiting-merge", "42", True, "MERGED", "42"),
     dict(_CLEARED, step="triage")),
    ("regression: readiness, PR OPEN -> readiness",
     _resume_env("readiness", "42", True, "OPEN", "42"),
     {"step": "readiness", "pr_number": "42"}),
    ("regression: prove, no pr -> prove",
     _resume_env("prove", "", False, "", "", branch=""),
     {"step": "prove"}),
    # #555: a marker's branch and PR are adopted only when they are this
    # loop's own; otherwise the marker is stale (triage, FR-022 cleared).
    ("regression: fix, own branch, no PR -> fix on that branch",
     _resume_env("fix", "", False, "", ""),
     {"step": "fix", "branch": "fix/396-board-item"}),
    ("regression: review, own branch, board:owned PR OPEN -> review",
     _resume_env("review", "42", True, "OPEN", "42"),
     {"step": "review", "pr_number": "42", "branch": "fix/396-board-item"}),
    ("fix, branch not named fix/<issue>-<slug> -> triage, FR-022 cleared (#555)",
     _resume_env("fix", "", False, "", "", branch="main"),
     dict(_CLEARED, step="triage")),
    ("fix, another issue's fix branch -> triage, FR-022 cleared (#555)",
     _resume_env("fix", "", False, "", "", branch="fix/3960-board-item"),
     dict(_CLEARED, step="triage")),
    ("review, PR OPEN without board:owned or from another repo -> triage, FR-022 cleared (#555)",
     _resume_env("review", "42", True, "OPEN", "42", pr_owned=False),
     dict(_CLEARED, step="triage", recovered_via_fallback=False)),
    ("readiness, PR OPEN not board:owned -> triage, FR-022 cleared (#555)",
     _resume_env("readiness", "42", True, "OPEN", "42", pr_owned=False),
     dict(_CLEARED, step="triage")),
    ("awaiting-merge, PR OPEN not board:owned -> no-op, PR not passed on (#555)",
     _resume_env("awaiting-merge", "42", True, "OPEN", "42", pr_owned=False),
     {"step": "awaiting-merge", "recovered_via_fallback": False, "pr_number": ""}),
]

# #555: the resume step's PR-ownership jq, run on these PR payloads
# (pulls/N REST shape) -- (title, payload, expected "true"/"false").
_REPO = "example/wing-commander"
OWNED_CASES = [
    ("board:owned, head in this repository",
     {"labels": [{"name": "board:owned"}], "head": {"repo": {"full_name": _REPO}}}, "true"),
    ("no board:owned label",
     {"labels": [{"name": "bug"}], "head": {"repo": {"full_name": _REPO}}}, "false"),
    ("board:owned, head in another repository",
     {"labels": [{"name": "board:owned"}], "head": {"repo": {"full_name": "someone/fork"}}}, "false"),
    ("board:owned, head repository deleted",
     {"labels": [{"name": "board:owned"}], "head": {"repo": None}}, "false"),
]


def resume_findings(doc, scripts_root=ROOT):
    code = _heredoc(_step_run(doc, "select", "resume"), "step_resolution_json")
    if code is None:
        return ["resume: no `step_resolution_json` heredoc found in select's resume step"]
    findings = []
    for title, env, expected in RESUME_CASES:
        rc, out, err = _exec_heredoc(code, env, scripts_root)
        if rc != 0:
            findings.append("resume `{0}`: step resolution crashed: {1}".format(
                title, err.strip().splitlines()[-1:] or err))
            continue
        try:
            got = json.loads(out)
        except ValueError:
            findings.append("resume `{0}`: output is not JSON: {1!r}".format(title, out))
            continue
        diff = {k: got.get(k) for k, v in expected.items() if got.get(k) != v}
        if diff:
            findings.append("resume `{0}`: expected {1}, got {2}".format(
                title, {k: expected[k] for k in diff}, diff))
    return findings


def owned_jq_findings(doc):
    """The resume step's jq that sets pr_owned (#555), run on OWNED_CASES."""
    run = _step_run(doc, "select", "resume")
    m = re.search(r"pr_owned=\"\$\(jq -r --arg repo \"\$GITHUB_REPOSITORY\" \\\n\s*'([^']*)'", run)
    if not m:
        return ["resume: no `pr_owned=$(jq -r --arg repo ...)` PR-ownership check found (#555)"]
    findings = []
    for title, payload, want in OWNED_CASES:
        proc = subprocess.run(["jq", "-r", "--arg", "repo", _REPO, m.group(1)],
                              input=json.dumps(payload), text=True, capture_output=True)
        got = proc.stdout.strip()
        if proc.returncode != 0 or got != want:
            findings.append("resume PR-ownership jq `{0}`: expected {1}, got {2!r} {3}".format(
                title, want, got, proc.stderr.strip()))
    return findings


# #555: every step that reads a board item marker, by (job, step id).
MARKER_READERS = (("select", "select"), ("select", "resume"), ("prove-gate", "gate"))
_BOT_LOGIN_ENV = "${{ steps.ctx.outputs.bot-slug }}[bot]"
_USER_PROJECTION = "user: {login: .user.login, type: .user.type}"


def marker_reader_findings(doc):
    """Each marker-reading step gets BOT_LOGIN from wing-commander-context
    (id ctx, earlier in the same job), projects user{login,type} in its
    comments fetch, and passes BOT_LOGIN to its reader (#555)."""
    findings = []
    for job, step_id in MARKER_READERS:
        steps = ((doc.get("jobs") or {}).get(job) or {}).get("steps") or []
        ids = [s.get("id") for s in steps if isinstance(s, dict)]
        step = next((s for s in steps if isinstance(s, dict) and s.get("id") == step_id), None)
        where = "{0}/{1}".format(job, step_id)
        if step is None:
            findings.append("{0}: step not found".format(where))
            continue
        if "ctx" not in ids or ids.index("ctx") > ids.index(step_id):
            findings.append("{0}: no wing-commander-context step (id ctx) before it".format(where))
        if (step.get("env") or {}).get("BOT_LOGIN") != _BOT_LOGIN_ENV:
            findings.append("{0}: env BOT_LOGIN is not `{1}`".format(where, _BOT_LOGIN_ENV))
        run = str(step.get("run", ""))
        fetches = re.findall(r"issues/\$\w+/comments\" --paginate \\\n\s*--jq '([^']*)'", run)
        if not fetches:
            findings.append("{0}: no issue comments fetch found".format(where))
        for jq_prog in fetches:
            if _USER_PROJECTION not in jq_prog:
                findings.append("{0}: comments fetch does not project `{1}`".format(
                    where, _USER_PROJECTION))
        reads = re.findall(r"read_marker(?:_with_timestamp)?\(([^)]*)\)", run)
        if not reads:
            findings.append("{0}: no marker reader call found".format(where))
        for args in reads:
            if 'os.environ["BOT_LOGIN"]' not in args:
                findings.append("{0}: read_marker call `{1}` does not pass BOT_LOGIN".format(
                    where, args))
    if "bot_login: $bot_login" not in _step_run(doc, "select", "select"):
        findings.append("select/select: board_eligibility.py's stdin payload carries no bot_login")
    return findings


def select_lookup_findings(doc, scripts_root=ROOT):
    """The select job's pr_numbers_to_check pass must list an
    awaiting-merge marker's PR; otherwise _awaiting_merge_holds() only
    ever sees an unknown state and the item drops off the board forever."""
    code = _heredoc(_step_run(doc, "select", "select"), "pr_numbers_to_check")
    if code is None:
        return ["select: no `pr_numbers_to_check` heredoc found in select's select step"]

    def marker(step, pr, user=None):
        return {"created_at": "2026-01-05T00:00:00Z",
                "user": user or {"login": BOT_LOGIN, "type": "Bot"},
                "body": "<!-- wing-commander-board-item: " + json.dumps(
                    {"step": step, "round": 0, "pr": pr, "branch": None,
                     "base_sha": None}) + " -->"}

    comments = {"1": [marker("awaiting-merge", 42)], "2": [marker("review", 43)],
                "3": [marker("route", None)],
                "4": [marker("review", 44, {"login": "outsider", "type": "User"})]}
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "comments.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(comments, fh)
        rc, out, err = _exec_heredoc(code, {"COMMENTS_BY_ISSUE_PATH": path,
                                            "BOT_LOGIN": BOT_LOGIN}, scripts_root)
    if rc != 0:
        return ["select: pr_numbers_to_check pass crashed: {0}".format(err.strip())]
    listed = set(out.split())
    findings = []
    if "42" not in listed:
        findings.append(
            "select: pr_numbers_to_check does not list an awaiting-merge marker's PR -- "
            "select() then never learns it is CLOSED/MERGED and the item drops off the "
            "board forever (AWAITING_MERGE_STEP must stay in FIX_OR_LATER_STEPS, #532)")
    if "43" not in listed:
        findings.append("select: pr_numbers_to_check does not list a review marker's PR")
    if "44" in listed:
        findings.append("select: pr_numbers_to_check lists a PR named by a marker another "
                        "author posted (#555)")
    return findings


def all_findings(text, table=None, scripts_root=ROOT):
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        return ["board-loop.yml does not parse: {0}".format(exc)]
    return (static_findings(doc) + simulation_findings(doc, table)
            + resume_findings(doc, scripts_root) + select_lookup_findings(doc, scripts_root)
            + owned_jq_findings(doc) + marker_reader_findings(doc))


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
    # #532: the ready report re-recording step=readiness (the pre-#532
    # write), and readiness resuming on an awaiting-merge marker.
    sub("ready report writes step=readiness (pre-#532)",
        "from board_eligibility import AWAITING_MERGE_STEP; from board_item_marker import "
        "write_marker; print(write_marker(AWAITING_MERGE_STEP,",
        "from board_item_marker import write_marker; print(write_marker('readiness',")
    sub("readiness resumes on an awaiting-merge marker",
        "|| (needs.select.outputs.step == 'readiness' && needs.select.outputs.pr != '')",
        "|| ((needs.select.outputs.step == 'readiness' || needs.select.outputs.step == "
        "'awaiting-merge') && needs.select.outputs.pr != '')",
        after="\n  readiness:\n")
    sub("resume clause 0 (awaiting-merge hold) disabled",
        "elif marker_step == AWAITING_MERGE_STEP and (not pr_from_marker or pr_state == \"OPEN\"):",
        "elif False:")
    # #555: the resume step's branch and PR guards, and the marker readers'
    # author plumbing.
    sub("resume branch-name guard dropped",
        "if branch and not is_loop_branch(branch, issue_number):", "if False:")
    sub("resume PR-ownership guard dropped",
        "if pr_from_marker and not pr_owned:", "if False:")
    sub("resume PR-ownership jq ignores the head repository",
        " and ((.head.repo.full_name // \"\") == $repo)", "")
    sub("resume PR-ownership jq ignores board:owned",
        "any(.labels[]?; .name == \"board:owned\") and ", "")
    sub("resume comments fetch without the user projection",
        "{created_at, body, user: {login: .user.login, type: .user.type}}' | jq -s '.' > "
        "\"$RUNNER_TEMP/board-issue-comments.json\"",
        "{created_at, body}' | jq -s '.' > \"$RUNNER_TEMP/board-issue-comments.json\"")
    sub("prove-gate reader without BOT_LOGIN",
        "read_marker(comments, os.environ[\"BOT_LOGIN\"]) else", "read_marker(comments, None) else")
    sub("prove-gate BOT_LOGIN env dropped",
        "          BOT_LOGIN: ${{ steps.ctx.outputs.bot-slug }}[bot]\n", "",
        after="\n  prove-gate:\n")
    sub("select eligibility payload without bot_login",
        ",\n              bot_login: $bot_login}", "}")
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
        if "pre-#525" in label or "breach exclusion" in label or "awaiting-merge marker" in label:
            sim = simulation_findings(yaml.safe_load(mutated))
            if not sim:
                failures.append("mutation `{0}`: the simulation alone did NOT detect it".format(label))
            else:
                print("    simulated: {0}".format(sim[0]))
    # board_eligibility.py mutation (#532): the unmutated workflow run
    # against a copy of .github/scripts whose FIX_OR_LATER_STEPS has lost
    # AWAITING_MERGE_STEP must fail the select lookup check.
    label = "AWAITING_MERGE_STEP dropped from FIX_OR_LATER_STEPS"
    with tempfile.TemporaryDirectory() as tmp:
        scripts = os.path.join(tmp, ".github", "scripts")
        shutil.copytree(os.path.join(ROOT, ".github", "scripts"), scripts,
                        ignore=shutil.ignore_patterns("tests", "fixtures", "__pycache__"))
        module = os.path.join(scripts, "board_eligibility.py")
        with open(module, encoding="utf-8") as fh:
            src = fh.read()
        old = '"readiness", AWAITING_MERGE_STEP, "prove"'
        if old not in src:
            failures.append("mutation `{0}`: fixture text not found in board_eligibility.py".format(label))
        else:
            with open(module, "w", encoding="utf-8") as fh:
                fh.write(src.replace(old, '"readiness", "prove"', 1))
            found = select_lookup_findings(yaml.safe_load(text), tmp)
            if not found:
                failures.append("mutation `{0}` was NOT detected".format(label))
            else:
                print("  detected: {0} -> {1}".format(label, found[0]))
    # board_item_marker.py mutation (#555): the reader without its author
    # check must fail the select lookup check (a forged marker's PR listed).
    label = "board_item_marker reader author check dropped"
    with tempfile.TemporaryDirectory() as tmp:
        scripts = os.path.join(tmp, ".github", "scripts")
        shutil.copytree(os.path.join(ROOT, ".github", "scripts"), scripts,
                        ignore=shutil.ignore_patterns("tests", "fixtures", "__pycache__"))
        module = os.path.join(scripts, "board_item_marker.py")
        with open(module, encoding="utf-8") as fh:
            src = fh.read()
        old = "        if not is_loop_marker_author(comment, bot_login):\n            continue\n"
        if old not in src:
            failures.append("mutation `{0}`: fixture text not found in board_item_marker.py".format(label))
        else:
            with open(module, "w", encoding="utf-8") as fh:
                fh.write(src.replace(old, "", 1))
            found = select_lookup_findings(yaml.safe_load(text), tmp)
            if not found:
                failures.append("mutation `{0}` was NOT detected".format(label))
            else:
                print("  detected: {0} -> {1}".format(label, found[0]))
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
