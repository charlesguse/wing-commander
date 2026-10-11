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
  2. carry `needs.select.result == 'success'` as a top-level conjunct
     (review/readiness may instead carry
     `(needs.select.result == 'success' || inputs.directed-stage ==
     '<job>')` -- PR #490 review, 2026-09-28: select is skipped by design
     on a directed dispatch, so the bare form would always skip the job),
     and `needs.resolve-model.result == 'success'` too when the job needs
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
resume step's PR-ownership jq is run on OWNED_CASES. A marker PR that is
OPEN but not the loop's own holds as the no-op step awaiting-merge with
nothing passed on (FR-054: triage could cut a second branch/PR), and the
select lookup must record such a PR as UNOWNED_OPEN_PR_STATE so select
does not re-choose the held item every run (Gate 81 pins that side).

WHAT IT CHECKS (#557)
---------------------
"Fetch failed" is not "no marker". Every issue-comments fetch in a
marker-reading step (select, resume, prove-gate) must be the condition of
an `if ! gh api ...; then` whose branch emits `::error::` and exits 1 --
no `||` swallow, no `[]` written in the comments' place. The three steps
are also RUN, under `bash -e` against a stub gh: a failed fetch must fail
each step loudly without writing its decision output, and a successful
one must not. The one exception is select's HTTP 404/410 on one issue's
comments ("issue gone"). That issue is dropped from the candidates with a
::warning:: and select succeeds. A 500 still fails the step. prove-gate must apply BOARD_PR_OWNED_JQ to the event's
pull_request: a merged PR without board:owned, or from another
repository, is not a board item (and its issue's comments are never
fetched). A simulator scenario pins that a select job failed in resume
runs nothing after it.

WHAT IT CHECKS (#564)
---------------------
The same rule for the other live lookups: select's PR-state lookup, and
resume's marker-PR lookup, board:owned fallback search and branch
`git ls-remote`. Statically, none may drop stderr or `||`-swallow, each
must be followed by an `::error::` + `exit 1` branch, and the "not found"
test must be there (HTTP 404 for a PR, ls-remote exit 2 for a branch).
Under the stub gh (plus a stub git): a 404 leaves select's state absent
and resume's meaning unchanged (falls to the fallback, then branch, then
triage) and the step succeeds; a 500, a failed fallback search, or
ls-remote exit 128 fails the step with `::error::` and no decision output.

WHAT IT CHECKS (#530)
---------------------
A failed spec-request create at fix's post-push breach must be retried,
not reviewed. Before #530 the breach wrote no marker before the create
(push-pr's step=review marker is never posted on a breach), so the newest
marker stayed triage's step=route. The next run's resume adopted the open
PR through the board:owned fallback as step=review, and the reviewer ran
on a PR the size check had already rejected. Now:
  - fix's post-push-breach step posts a board_eligibility.BREACH_STEP
    marker (with the PR) before its `gh issue create` (static);
  - BREACH_STEP is in FIX_OR_LATER_STEPS, so select looks up its PR
    (executed, select lookup), and resume resolves it to step=breach --
    also when only the board:owned fallback finds the PR, never review
    (executed, RESUME_CASES);
  - readiness, never review, runs on step=breach (simulated), and its
    backstop step is forced to breach there with breach-retry=true
    whatever the fresh measure says (executed on an empty diff);
  - the retry looks for a spec-request already filed first: a lookup
    step gated on breach-retry feeds report-unmet's EXISTING_SPEC_URL,
    which report-unmet reuses in place of a create (static), and the
    lookup's BREACH_SPEC_REQUEST_JQ is run on SPEC_REQUEST_CASES.

WHAT IT CHECKS (#604)
---------------------
(a) Every stalled marker board-loop.yml writes goes through
board_item_marker.py with `--issue "$ISSUE_NUMBER" --add-label
"board:stalled"` and a `|| { echo "::error::..."; exit 1; }` guard (a
`--step "$var"` render whose var can be `stalled` must pass them through
`"${stall_args[@]}"`); no step applies board:stalled with a bare gh call
or writes a marker inline. The CLI itself is run against a stub gh
(STALL_CLI_CASES): `--step stalled` without the add is refused, a failed
add renders nothing and exits non-zero, a successful one calls gh first
and keeps gh's stdout out of the marker.
(b) In readiness, every step after `killswitch-recheck` that writes to
GitHub (gh issue/pr writes, a marker, the cross-link composite) carries
`steps.killswitch-recheck.outputs.paused == 'false'` as a top-level `if:`
conjunct, none writes before it, and the re-check itself is neither
conditional nor tolerated (FR-051/FR-052).

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

# spec 095: fix-agent (the fixer) and fix (the publisher, after the
# credential-free gate-suite-fix) carry the same resume gating.
RESUME_JOBS = ("fix-agent", "fix", "review", "readiness")
# spec 095: fix publishes what fix-agent wrote. A pause set between the two
# is found by its own killswitch-recheck, which records the stand-down; a
# job-level pause check would skip it silently (code review of #990).
PAUSE_BY_STEP = ("fix",)
SIM_JOBS = ("select", "resolve-model", "triage", "route", "fix-agent", "gate-suite-fix", "fix",
            "review", "readiness")
PAUSE_VAR = "vars.WING_COMMANDER_BOARD_LOOP_PAUSED"

# specs/060-self-redrive-concurrency, PR #490 review (2026-09-28): select is
# skipped by design on a directed dispatch (`inputs.directed-stage != ''`),
# so review/readiness may OR their `needs.select.result == 'success'` guard
# with the matching `inputs.directed-stage` value instead of carrying it
# bare. `fix` has no directed-stage branch (aimable_jobs excludes it,
# board_prove.py T002) and must keep the bare form.
DIRECTED_STAGE_BY_JOB = {"review": "review", "readiness": "readiness"}
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

def _has_conjunct(cond, node):
    """True when the `if:` text `cond` carries `node` as a top-level
    conjunct (#604: readiness's steps now AND the stop gate on)."""
    if cond is None:
        return False
    try:
        return node in conjuncts(parse_expr(cond))
    except ValueError:
        return False


def _is_cmp(node, op, path, value):
    return (node[0] == op and node[1] == ("path", path) and node[2] == ("lit", value))


def _guards_select_result(node, job_name):
    """True when `node` is an accepted top-level form of the select guard
    for `job_name`: the bare `needs.select.result == 'success'`, or (for a
    job in DIRECTED_STAGE_BY_JOB) an OR of that comparison with
    `inputs.directed-stage == '<job_name>'` (PR #490 review, 2026-09-28)."""
    if _is_cmp(node, "==", "needs.select.result", "success"):
        return True
    directed = DIRECTED_STAGE_BY_JOB.get(job_name)
    if directed and node[0] == "or":
        parts = node[1]
        return (any(_is_cmp(p, "==", "needs.select.result", "success") for p in parts)
                and any(_is_cmp(p, "==", "inputs.directed-stage", directed) for p in parts))
    return False


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


def _writes_marker(run):
    """True if `run` writes a board item marker anywhere, via either the
    inline write_marker(...) call or the board_item_marker.py CLI
    entrypoint (#607)."""
    return "write_marker(" in run or "board_item_marker.py" in run


def _writes_marker_step(run, step):
    """True if `run` writes a board item marker for the given literal step
    name (e.g. 'stalled') or symbolic token (BREACH_STEP/AWAITING_MERGE_STEP),
    via either the inline write_marker(...) call or the board_item_marker.py
    CLI entrypoint's `--step` flag (#607)."""
    if "--step {0}".format(step) in run and "board_item_marker.py" in run:
        return True
    if step in ("BREACH_STEP", "AWAITING_MERGE_STEP"):
        return "write_marker({0},".format(step) in run
    return "write_marker({0!r}".format(step) in run


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
            if up == "select":
                ok = any(_guards_select_result(p, name) for p in top)
            else:
                ok = any(_is_cmp(p, "==", "needs.{0}.result".format(up), "success") for p in top)
            if not ok:
                findings.append(
                    "{0}: if: lacks top-level `needs.{1}.result == 'success'`".format(name, up))
        if name in PAUSE_BY_STEP:
            if any(_is_cmp(p, "!=", PAUSE_VAR, "true") for p in top):
                findings.append(
                    "{0}: if: checks `{1}` at job level -- a pause set after the job before "
                    "it would skip this job with nothing recorded; its killswitch-recheck "
                    "step finds and records it (spec 095)".format(name, PAUSE_VAR))
            steps = job.get("steps") or []
            if not any(isinstance(st, dict) and st.get("id") == "killswitch-recheck"
                       and "wing-commander-board-stop-check" in str(st.get("uses", ""))
                       for st in steps):
                findings.append("{0}: no killswitch-recheck step to find a pause".format(name))
        elif not any(_is_cmp(p, "!=", PAUSE_VAR, "true") for p in top):
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
                   and _has_conjunct(s.get("if"), ("==", ("path", "steps.decide.outputs.ready"), ("lit", "true")))
                   and _writes_marker(str(s.get("run", "")))]
    if not ready_steps:
        findings.append("readiness: no step gated on `steps.decide.outputs.ready == 'true'` writes "
                        "a board item marker (#532)")
    for s in ready_steps:
        run = str(s.get("run", ""))
        if not _writes_marker_step(run, "AWAITING_MERGE_STEP"):
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
    if parts[0] == "inputs" and len(parts) == 2:
        # specs/060-self-redrive-concurrency: every scenario this gate
        # simulates is an ordinary (non-directed) trigger, so every
        # `inputs.*` reference (e.g. `inputs.directed-stage`) reads as
        # empty here -- the same value GitHub Actions gives a
        # workflow_dispatch input on a schedule/pull_request-triggered run.
        return (ctx.vars.get("__inputs") or {}).get(parts[1], "")
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
     ("select", "resolve-model", "triage", "route", "fix-agent", "gate-suite-fix", "fix", "review")),
    ("fresh: route=fix, post-push breach (#526)",
     {"outputs": {"select": _item("triage"), "triage": {"outcome": "proceed"},
                  "route": {"decision": "fix"}, "fix": {"pr-number": "42", "breach": "true"},
                  "review": {"pr-number": "42", "outcome": "converged"}}},
     ("select", "resolve-model", "triage", "route", "fix-agent", "gate-suite-fix", "fix")),
    ("fresh: route=fix, fix job fails",
     {"fail": ("fix",),
      "outputs": {"select": _item("triage"), "triage": {"outcome": "proceed"},
                  "route": {"decision": "fix"}, "fix": {"pr-number": "42", "breach": "false"}}},
     ("select", "resolve-model", "triage", "route", "fix-agent", "gate-suite-fix", "fix")),
    # spec 095: the fixer's job failing skips its gate job and the
    # publisher -- nothing is pushed and review never runs.
    ("fresh: route=fix, fix-agent fails",
     {"fail": ("fix-agent",),
      "outputs": {"select": _item("triage"), "triage": {"outcome": "proceed"},
                  "route": {"decision": "fix"}}},
     ("select", "resolve-model", "triage", "route", "fix-agent")),
    # A failed gate-suite job is a red verdict, not a skipped publisher:
    # fix still runs and reads the (absent) verdict as a failure.
    ("fresh: route=fix, gate-suite-fix fails",
     {"fail": ("gate-suite-fix",),
      "outputs": {"select": _item("triage"), "triage": {"outcome": "proceed"},
                  "route": {"decision": "fix"}, "fix": {"pr-number": "", "breach": ""}}},
     ("select", "resolve-model", "triage", "route", "fix-agent", "gate-suite-fix", "fix")),
    ("fresh: route=spec",
     {"outputs": {"select": _item("triage"), "triage": {"outcome": "proceed"},
                  "route": {"decision": "spec"}}},
     ("select", "resolve-model", "triage", "route")),
    ("fresh: route=defer (rate-limited route agent) runs nothing after route",
     {"outputs": {"select": _item("triage"), "triage": {"outcome": "proceed"},
                  "route": {"decision": "defer"}}},
     ("select", "resolve-model", "triage", "route")),
    ("fresh: triage=defer (rate-limited triage agent) skips route",
     {"outputs": {"select": _item("triage"), "triage": {"outcome": "defer"}}},
     ("select", "resolve-model", "triage")),
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
     ("select", "resolve-model", "fix-agent", "gate-suite-fix", "fix", "review", "readiness")),
    ("resume step=fix, fix job fails",
     {"fail": ("fix",),
      "outputs": {"select": _item("fix", branch="board/396"),
                  "fix": {"pr-number": "42", "breach": "false"}}},
     ("select", "resolve-model", "fix-agent", "gate-suite-fix", "fix")),
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
    # #557: resume's comments fetch failed -- select's issue-number is set,
    # resume wrote nothing, and the job is red.
    ("select fails in resume (comments fetch) after choosing an issue",
     {"fail": ("select",),
      "outputs": {"select": {"issue-number": "396", "step": "", "pr": "", "branch": "", "round": ""}}},
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
     ("select", "resolve-model", "triage", "route", "fix-agent", "gate-suite-fix", "fix", "review")),
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
    # #530: fix's post-push breach posted step=breach, then its spec-request
    # create failed. The next run retries the spec-request in readiness's
    # forced-breach path; the oversized PR is never reviewed.
    ("resume after a failed post-push breach create (step=breach) -> no review (#530)",
     {"outputs": {"select": _item("breach", pr="42", branch="fix/396-board-item")}},
     ("select", "resolve-model", "readiness")),
    ("resume step=breach, board paused (#530)",
     {"vars": {"WING_COMMANDER_BOARD_LOOP_PAUSED": "true"},
      "outputs": {"select": _item("breach", pr="42", branch="fix/396-board-item")}},
     ("select", "resolve-model")),
    # PR #490 review, 2026-09-28: select is skipped by design on a directed
    # dispatch (`inputs.directed-stage != ''`), so review/readiness must
    # reach their job through the `inputs.directed-stage` branch of their
    # own select guard, not the (always-false-here) `needs.select.result ==
    # 'success'` branch. This is the exact gap that let a directed
    # review/readiness dispatch conclude 'success' -- and outcome_reason
    # record 'proven' -- while cascade-skipping the job it was dispatched
    # to run.
    ("directed dispatch: review reaches the job",
     {"vars": {"__inputs": {"directed-stage": "review", "directed-issue": "396"}}},
     ("resolve-model", "review")),
    ("directed dispatch: readiness reaches the job",
     {"vars": {"__inputs": {"directed-stage": "readiness", "directed-issue": "396"}}},
     ("resolve-model", "readiness")),
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
                pr_owned=True, marker_extra=None, pr_head_sha=""):
    marker = {"step": step} if step else None
    if marker is not None and marker_extra:
        marker.update(marker_extra)
    return {
        "MARKER_STEP": step, "MARKER_JSON": json.dumps(marker) if marker is not None else "null",
        "BRANCH": branch, "MARKER_PR": marker_pr,
        "PR_FROM_MARKER": "true" if pr_from_marker else "false",
        "PR_FROM_FALLBACK": "true" if from_fallback else "false",
        "PR_STATE": pr_state, "PR_NUMBER": pr_number, "PR_HEAD_SHA": pr_head_sha,
        "MARKER_ROUND": round_, "MARKER_BASE_SHA": base_sha,
        "PR_OWNED": "true" if pr_owned else "false", "ISSUE_NUMBER": "396",
        # spec 100 FR-006b: clause 2b reads COMMENTS_PATH unconditionally
        # once pr_from_fallback fires (board_item_marker.
        # head_moved_since_last_review()'s own comments argument) -- an
        # empty array here is fine, since none of these cases assert on
        # review-vs-readiness, only on the three-way step split itself
        # (that split's own fixtures live under verify-board-loop-
        # readmission.py's Gate 134).
        "COMMENTS_PATH": ".github/scripts/tests/board-loop-readmission/no-open-pr-falls-to-triage/comments.json",
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
    ("awaiting-merge, PR MERGED (issue still open) -> prove, FR-022 cleared "
     "(specs/096-durable-prove-entry FR-007/FR-008/FR-009)",
     _resume_env("awaiting-merge", "42", True, "MERGED", "42"),
     dict(_CLEARED, step="prove")),
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
    # FR-054: an OPEN PR that is not the loop's own (e.g. board:owned
    # removed) holds as a no-op; triage could cut a second branch/PR.
    ("review, PR OPEN without board:owned or from another repo -> no-op hold, nothing passed on (#555)",
     _resume_env("review", "42", True, "OPEN", "42", pr_owned=False),
     dict(_CLEARED, step="awaiting-merge", recovered_via_fallback=False)),
    ("readiness, PR OPEN not board:owned -> no-op hold, nothing passed on (#555)",
     _resume_env("readiness", "42", True, "OPEN", "42", pr_owned=False),
     dict(_CLEARED, step="awaiting-merge")),
    ("fix, PR OPEN not board:owned, foreign branch too -> no-op hold (#555)",
     _resume_env("fix", "42", True, "OPEN", "42", pr_owned=False, branch="main"),
     dict(_CLEARED, step="awaiting-merge")),
    ("review, PR CLOSED not board:owned -> triage, FR-022 cleared (#555)",
     _resume_env("review", "42", True, "CLOSED", "42", pr_owned=False),
     dict(_CLEARED, step="triage")),
    ("review, PR MERGED not board:owned -> triage, FR-022 cleared (#555)",
     _resume_env("review", "42", True, "MERGED", "42", pr_owned=False),
     dict(_CLEARED, step="triage")),
    ("awaiting-merge, PR OPEN not board:owned -> no-op, PR not passed on (#555)",
     _resume_env("awaiting-merge", "42", True, "OPEN", "42", pr_owned=False),
     {"step": "awaiting-merge", "recovered_via_fallback": False, "pr_number": ""}),
    # #530: a step=breach marker (fix's post-push breach, spec-request not
    # yet filed) resumes at breach -- never review, even when only the
    # board:owned fallback finds its PR.
    ("breach, PR OPEN -> breach, never review (#530)",
     _resume_env("breach", "42", True, "OPEN", "42"),
     {"step": "breach", "pr_number": "42", "recovered_via_fallback": False}),
    ("breach, PR unresolved, board:owned fallback PR found -> breach, never review (#530)",
     _resume_env("breach", "42", False, "OPEN", "42", from_fallback=True),
     {"step": "breach", "pr_number": "42"}),
    ("breach, PR CLOSED -> triage, FR-022 cleared (#530)",
     _resume_env("breach", "42", True, "CLOSED", "42"),
     dict(_CLEARED, step="triage")),
    ("breach, PR OPEN not board:owned -> no-op hold (#530, #555)",
     _resume_env("breach", "42", True, "OPEN", "42", pr_owned=False),
     dict(_CLEARED, step="awaiting-merge")),
    # The pre-#530 shape of the same item (step=route newest, the breach's
    # PR found by the fallback) still resolves to review: the retry needs
    # the breach marker, which fix now posts before its create.
    ("regression: route marker, board:owned fallback PR -> review",
     _resume_env("route", "", False, "OPEN", "42", from_fallback=True, branch=""),
     {"step": "review", "pr_number": "42", "recovered_via_fallback": True}),
    # specs/093-not-ready-board-release FR-007/FR-008/D7: this feature's
    # own stalled handover marker uniquely carries pr/nr_head_sha -- a
    # board:stalled removal never resolves to triage; review-vs-readiness is
    # head_moved_since_last_review()'s call (T039), so this table (no
    # converged review comment, no gh stub) only pins the safe default.
    # The readiness side lives in verify-board-loop-readmission.py's
    # not-ready-handover-* fixtures.
    ("not-ready handover (stalled, pr+nr_head_sha), no converged review resolvable -> review, round + 1",
     _resume_env("stalled", "42", True, "OPEN", "42",
                 marker_extra={"pr": 42, "nr_head_sha": "deadbeef"}, pr_head_sha="deadbeef"),
     {"step": "review", "pr_number": "42", "round": "3"}),
    # A handover whose PR was merged or closed since is not resumed on that
    # PR (code review of #1010): it falls to a fresh triage with the PR
    # cleared, like any pr-less stall with no open PR -- never prove, which
    # nothing in the job graph consumes (_merged_fix_holds(), #532).
    ("not-ready handover (stalled, pr+nr_head_sha), PR MERGED -> triage",
     _resume_env("stalled", "42", True, "MERGED", "42", branch="",
                 marker_extra={"pr": 42, "nr_head_sha": "deadbeef"}, pr_head_sha="deadbeef"),
     {"step": "triage", "pr_number": ""}),
    ("not-ready handover (stalled, pr+nr_head_sha), PR CLOSED -> triage",
     _resume_env("stalled", "42", True, "CLOSED", "42", branch="",
                 marker_extra={"pr": 42, "nr_head_sha": "deadbeef"}, pr_head_sha="deadbeef"),
     {"step": "triage", "pr_number": ""}),
    # FR-015: a stalled marker from any other stall site keeps pr: null and
    # is unaffected -- still resolved by the generic board:owned fallback
    # clause, never triage.
    ("regression: stalled marker from any other stall site (pr absent) -> review",
     _resume_env("stalled", "", False, "OPEN", "42", from_fallback=True),
     {"step": "review", "pr_number": "42", "recovered_via_fallback": True}),
    # specs/093-not-ready-board-release FR-001/FR-007 (US3): a durable
    # not-ready record on a readiness marker holds while the head is
    # unchanged (regression, now exercised with nr_* fields present), and
    # re-admits at review -- never readiness -- the moment the head moves,
    # carrying the marker's own round forward rather than resetting it.
    ("regression: readiness, durable not-ready record, head unmoved -> readiness",
     _resume_env("readiness", "42", True, "OPEN", "42",
                 marker_extra={"pr": 42, "nr_count": 1, "nr_head_sha": "deadbeef", "nr_class": "durable"},
                 pr_head_sha="deadbeef", round_="2"),
     {"step": "readiness", "pr_number": "42", "round": "2"}),
    # SC-009 (code review of #1010): the re-admission spends one round, so
    # a converged re-review cannot be bought for free by every push.
    ("readiness, durable not-ready record, head moved -> review, round continued (+1)",
     _resume_env("readiness", "42", True, "OPEN", "42",
                 marker_extra={"pr": 42, "nr_count": 1, "nr_head_sha": "deadbeef", "nr_class": "durable"},
                 pr_head_sha="cafefeed", round_="2"),
     {"step": "review", "pr_number": "42", "round": "3"}),
    # FR-005: a self-clearing record never holds -- on an unchanged head it
    # resolves readiness like an ordinary readiness marker; on a moved head
    # it goes to review, since no review covered the new commits (SC-010,
    # code review of #1010).
    ("regression: readiness, self-clearing not-ready record, head unmoved -> readiness",
     _resume_env("readiness", "42", True, "OPEN", "42",
                 marker_extra={"pr": 42, "nr_count": 1, "nr_head_sha": "deadbeef", "nr_class": "self-clearing"},
                 pr_head_sha="deadbeef"),
     {"step": "readiness", "pr_number": "42"}),
    ("readiness, self-clearing not-ready record, head moved -> review",
     _resume_env("readiness", "42", True, "OPEN", "42",
                 marker_extra={"pr": 42, "nr_count": 1, "nr_head_sha": "deadbeef", "nr_class": "self-clearing"},
                 pr_head_sha="cafefeed"),
     {"step": "review", "pr_number": "42"}),
    # FR-007/FR-012/SC-009 (US3 AS5/AS6): re-admission continues the
    # existing round budget rather than resetting it -- an already
    # -exhausted budget is carried through unchanged into review, whose
    # own existing (unmodified) "Decide the round outcome" step takes its
    # spec 057 FR-030 budget-exhausted stall from there; this feature adds
    # no second, parallel handover for that case.
    ("readiness, durable not-ready record, head moved, round budget already exhausted -> review, round carried",
     _resume_env("readiness", "42", True, "OPEN", "42",
                 marker_extra={"pr": 42, "nr_count": 1, "nr_head_sha": "deadbeef", "nr_class": "durable"},
                 pr_head_sha="cafefeed", round_="5"),
     {"step": "review", "pr_number": "42", "round": "6"}),
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


def owned_jq_findings(doc, scripts_root=ROOT):
    """The workflow-level BOARD_PR_OWNED_JQ (#555), run on OWNED_CASES; the
    resume step and the select lookup both apply it, and the select lookup
    records an OPEN, not-owned PR as board_eligibility.UNOWNED_OPEN_PR_STATE."""
    prog = (doc.get("env") or {}).get("BOARD_PR_OWNED_JQ")
    if not prog:
        return ["workflow env has no BOARD_PR_OWNED_JQ (#555)"]
    findings = []
    use = 'jq -r --arg repo "$GITHUB_REPOSITORY" "$BOARD_PR_OWNED_JQ"'
    for job, step_id in (("select", "select"), ("select", "resume"), ("prove-gate", "gate")):
        if use not in _step_run(doc, job, step_id):
            findings.append("{0}/{1}: does not apply `{2}` (#555, #557)".format(job, step_id, use))
    rc, const, err = _exec_heredoc(
        "import sys\nsys.path.insert(0, '.github/scripts')\n"
        "from board_eligibility import UNOWNED_OPEN_PR_STATE\nprint(UNOWNED_OPEN_PR_STATE)\n",
        {}, scripts_root)
    const = const.strip()
    if rc != 0 or not const:
        findings.append("board_eligibility.UNOWNED_OPEN_PR_STATE not importable: {0}".format(err.strip()))
    elif 'pr_state="{0}"'.format(const) not in _step_run(doc, "select", "select"):
        findings.append("select/select: an OPEN PR that fails BOARD_PR_OWNED_JQ is not recorded "
                        "as {0!r} -- select would keep choosing an item resume only holds (#555)".format(const))
    for title, payload, want in OWNED_CASES:
        proc = subprocess.run(["jq", "-r", "--arg", "repo", _REPO, prog],
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

    def marker(step, pr, user=None, extra=None):
        fields = {"step": step, "round": 0, "pr": pr, "branch": None, "base_sha": None}
        fields.update(extra or {})
        return {"created_at": "2026-01-05T00:00:00Z",
                "user": user or {"login": BOT_LOGIN, "type": "Bot"},
                "body": "<!-- wing-commander-board-item: " + json.dumps(fields) + " -->"}

    comments = {"1": [marker("awaiting-merge", 42)], "2": [marker("review", 43)],
                "3": [marker("route", None)],
                "4": [marker("review", 44, {"login": "outsider", "type": "User"})],
                "5": [marker("breach", 45)],
                # specs/093 D7: the not-ready handover names its PR.
                "6": [marker("stalled", 46, extra={"nr_head_sha": "deadbeef"})],
                # Every other stall site's marker names none.
                "7": [marker("stalled", None)]}
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
    if "45" not in listed:
        findings.append(
            "select: pr_numbers_to_check does not list a breach marker's PR -- the item is "
            "then never in-flight and resume cannot confirm its PR is open (BREACH_STEP must "
            "stay in FIX_OR_LATER_STEPS, #530)")
    if "46" not in listed:
        findings.append(
            "select: pr_numbers_to_check does not list a not-ready handover marker's PR -- a PR a "
            "human took over (board:owned removed) is then never held as unowned, and the item is "
            "re-selected every run (specs/093 D7, code review of #1010)")
    return findings


# ---------------------------------------------------------------------------
# #530: a failed post-push-breach spec-request create is retried in
# readiness's forced-breach path, never reviewed, and the retry reuses a
# spec-request that create already filed.
# ---------------------------------------------------------------------------

_SERVER_REPO = "https://github.com/example/wing-commander"
_FOOTER = "Originating issue: {0}/issues/396".format(_SERVER_REPO)


def _spec_request(body, login=BOT_LOGIN, type_="Bot", created="2026-01-05T00:00:00Z",
                  url="{0}/issues/900".format(_SERVER_REPO)):
    return {"html_url": url, "created_at": created, "body": body,
            "user": {"login": login, "type": type_}}


_FIX_NOTICE = ("The fix at {0}/pull/42 grew past the board's size-and-path backstop "
               "on its final diff (measured={{}}).\n\nNo drafted body.\n\n---\n{1}").format(
                   _SERVER_REPO, _FOOTER)
_READINESS_NOTICE = ("PR #42 grew past the board's size-and-path backstop by readiness time."
                     "\n\nNo drafted body.\n\n---\n{0}").format(_FOOTER)

# (title, issues listing, expected html_url or "") -- BREACH_SPEC_REQUEST_JQ
# run with bot=BOT_LOGIN, footer=_FOOTER, pr=42.
SPEC_REQUEST_CASES = [
    ("fix's post-push-breach spec-request for PR 42", [_spec_request(_FIX_NOTICE)],
     _SERVER_REPO + "/issues/900"),
    ("readiness's breach spec-request for PR 42", [_spec_request(_READINESS_NOTICE)],
     _SERVER_REPO + "/issues/900"),
    ("nothing filed yet", [], ""),
    ("same text, posted by someone else",
     [_spec_request(_FIX_NOTICE, login="outsider", type_="User")], ""),
    ("same login, not a Bot", [_spec_request(_FIX_NOTICE, type_="User")], ""),
    ("another PR (420)", [_spec_request(_FIX_NOTICE.replace("/pull/42 ", "/pull/420 "))], ""),
    ("another issue's footer (3960)",
     [_spec_request(_FIX_NOTICE.replace("/issues/396", "/issues/3960"))], ""),
    ("footer only quoted inside a line",
     [_spec_request(_FIX_NOTICE.replace("\n" + _FOOTER, "\n> " + _FOOTER))], ""),
    ("two filed -> the oldest",
     [_spec_request(_FIX_NOTICE, created="2026-01-06T00:00:00Z", url=_SERVER_REPO + "/issues/902"),
      _spec_request(_FIX_NOTICE, created="2026-01-05T00:00:00Z", url=_SERVER_REPO + "/issues/901")],
     _SERVER_REPO + "/issues/901"),
]


def _step(doc, job, step_id):
    for s in ((doc.get("jobs") or {}).get(job) or {}).get("steps") or []:
        if isinstance(s, dict) and s.get("id") == step_id:
            return s
    return {}


def _run_readiness_backstop(code, resume_step, scripts_root):
    """Runs readiness's final-diff-backstop heredoc on an empty diff with
    RESUME_STEP set; returns (rc, {output: value}, stderr)."""
    with tempfile.TemporaryDirectory() as tmp:
        pristine = os.path.join(tmp, "wc-pristine")
        os.makedirs(pristine)
        os.symlink(os.path.join(os.path.abspath(scripts_root), ".github", "scripts"),
                   os.path.join(pristine, "scripts"))
        open(os.path.join(tmp, "board-readiness-final-diff.patch"), "w").close()
        # The step lists its paths with diff_name_list(BASE_SHA): an empty
        # repository diffed against its own HEAD.
        work = os.path.join(tmp, "work")
        os.makedirs(work)
        git = ["git", "-C", work, "-c", "user.name=t", "-c", "user.email=t@t"]
        subprocess.run(git[:3] + ["init", "-q"], check=True)
        subprocess.run(git + ["commit", "-q", "--allow-empty", "-m", "base"], check=True)
        base_sha = subprocess.run(git[:3] + ["rev-parse", "HEAD"], check=True,
                                  capture_output=True, text=True).stdout.strip()
        out_path = os.path.join(tmp, "github_output")
        env = dict(os.environ, RUNNER_TEMP=tmp, GITHUB_OUTPUT=out_path, BASE_SHA=base_sha,
                   BOARD_MAX_FILES="6", BOARD_MAX_LINES="120", RESUME_STEP=resume_step)
        proc = subprocess.run([sys.executable, "-"], input=code, text=True,
                              capture_output=True, env=env, cwd=work)
        outputs = {}
        if os.path.exists(out_path):
            with open(out_path, encoding="utf-8") as fh:
                for line in fh:
                    key, _, value = line.rstrip("\n").partition("=")
                    outputs[key] = value
        return proc.returncode, outputs, proc.stderr


def breach_retry_findings(doc, scripts_root=ROOT):
    findings = []

    # Fix: the step=breach marker is posted before the create.
    run = str(_step(doc, "fix", "post-push-breach").get("run", ""))
    lines = run.split("\n")
    create_at = next((i for i, l in enumerate(lines) if "gh issue create" in l), None)
    marker_at = next((i for i, l in enumerate(lines)
                      if _writes_marker_step(l, "BREACH_STEP") and "--pr" in l), None)
    post_at = next((i for i, l in enumerate(lines)
                    if "gh issue comment" in l and "$breach_marker" in l), None)
    if create_at is None:
        findings.append("fix/post-push-breach: no `gh issue create` found (#530)")
    elif marker_at is None or post_at is None or not (marker_at < post_at < create_at):
        findings.append(
            "fix/post-push-breach: does not post a write_marker(BREACH_STEP, ..., PR, ...) "
            "marker before its `gh issue create` -- a failed create leaves step=route newest "
            "and the next run reviews the oversized PR (#530)")

    # Both breach sites' board:stalled-before-marker rule (#530) is now
    # every stall site's: stall_label_findings() below (#604).

    # Readiness: forced breach on step=breach, executed.
    backstop = _step(doc, "readiness", "final-diff-backstop")
    if (backstop.get("env") or {}).get("RESUME_STEP") != "${{ needs.select.outputs.step }}":
        findings.append("readiness/final-diff-backstop: env RESUME_STEP is not "
                        "`${{ needs.select.outputs.step }}` (#530)")
    m = re.search(r"<<'PYEOF'\n(.*?)\nPYEOF", str(backstop.get("run", "")), re.S)
    if m is None:
        findings.append("readiness/final-diff-backstop: no heredoc found (#530)")
    else:
        for resume_step, want in (("breach", {"holds": "false", "breach-retry": "true"}),
                                  ("readiness", {"holds": "true", "breach-retry": "false"})):
            rc, outputs, err = _run_readiness_backstop(m.group(1), resume_step, scripts_root)
            got = {k: outputs.get(k) for k in want}
            if rc != 0 or got != want:
                findings.append(
                    "readiness/final-diff-backstop on an empty diff with step={0}: expected {1}, "
                    "got {2} {3} (#530: a breach resume must never report ready)".format(
                        resume_step, want, got, err.strip()[-200:]))

    # Readiness: the retry looks for an existing spec-request first.
    lookup = _step(doc, "readiness", "breach-retry-lookup")
    cond = str(lookup.get("if", "")).replace(" ", "")
    if "steps.final-diff-backstop.outputs.breach-retry=='true'" not in cond:
        findings.append("readiness: no step `breach-retry-lookup` gated on "
                        "`steps.final-diff-backstop.outputs.breach-retry == 'true'` (#530)")
    unmet = _step(doc, "readiness", "report-unmet")
    unmet_env = unmet.get("env") or {}
    unmet_run = str(unmet.get("run", ""))
    if (unmet_env.get("EXISTING_SPEC_URL") != "${{ steps.breach-retry-lookup.outputs.existing-spec-url }}"
            or unmet_env.get("BREACH_RETRY") != "${{ steps.final-diff-backstop.outputs.breach-retry }}"):
        findings.append("readiness/report-unmet: env does not carry EXISTING_SPEC_URL from "
                        "breach-retry-lookup and BREACH_RETRY from final-diff-backstop (#530)")
    reuse_at = unmet_run.find('existing_spec_url="$EXISTING_SPEC_URL"')
    guard_at = unmet_run.find('if [ -n "$existing_spec_url" ]; then')
    create_at = unmet_run.find("gh issue create")
    if not (0 <= reuse_at < guard_at < create_at):
        findings.append("readiness/report-unmet: does not reuse EXISTING_SPEC_URL in place of "
                        "`gh issue create` -- a retry after a create that succeeded files a "
                        "second spec-request (#530)")
    prog = (lookup.get("env") or {}).get("BREACH_SPEC_REQUEST_JQ")
    if not prog:
        findings.append("readiness/breach-retry-lookup: no env BREACH_SPEC_REQUEST_JQ (#530)")
    else:
        for title, issues, want in SPEC_REQUEST_CASES:
            proc = subprocess.run(["jq", "-r", "--arg", "bot", BOT_LOGIN, "--arg", "footer", _FOOTER,
                                   "--arg", "pr", "42", prog],
                                  input=json.dumps(issues), text=True, capture_output=True)
            got = proc.stdout.strip()
            if proc.returncode != 0 or got != want:
                findings.append("BREACH_SPEC_REQUEST_JQ `{0}`: expected {1!r}, got {2!r} {3}".format(
                    title, want, got, proc.stderr.strip()))
    return findings


# ---------------------------------------------------------------------------
# #604 (a): every stalled marker board-loop.yml writes adds board:stalled
# first, and fails loudly when it cannot. The one home of that sequence is
# board_item_marker.py's add_stalled_label(); this checks each call site
# uses it and that the CLI itself refuses to render a stalled marker
# without the add.
# ---------------------------------------------------------------------------

_MARKER_CLI = re.compile(r'board_item_marker\.py"?\s+--step\s+("\$\w+"|\$\w+|"?[A-Za-z_-]+)')
_FAIL_LOUD = re.compile(r'\|\|\s*\{\s*echo\s+"::error::[^\n]*;\s*exit\s+1;\s*\}\s*$')
_STALL_FLAGS = re.compile(r'--issue\s+"\$ISSUE_NUMBER"\s+--add-label\s+"board:stalled"')
_BARE_STALLED_APPLY = re.compile(r'\bgh\s+(?:issue|pr|api)\b.*(?:--add-label|--label|labels\[\]).*board:stalled')


def _logical_lines(run):
    return re.sub(r"\\\n\s*", " ", run).split("\n")


def _all_steps(doc):
    for job_name, job in (doc.get("jobs") or {}).items():
        for i, step in enumerate((job or {}).get("steps") or []):
            if isinstance(step, dict):
                yield job_name, i, step


def _stub_gh(tmp, rc):
    bin_dir = os.path.join(tmp, "bin-{0}".format(rc))
    os.makedirs(bin_dir)
    gh = os.path.join(bin_dir, "gh")
    with open(gh, "w", encoding="utf-8") as fh:
        fh.write('#!/bin/sh\necho "$@" >> "{0}"\necho https://github.com/o/r/issues/7\nexit {1}\n'.format(
            os.path.join(tmp, "gh-calls.log"), rc))
    os.chmod(gh, 0o755)
    return bin_dir


def _run_marker_cli(args, gh_rc, scripts_root):
    """Runs board_item_marker.py as board-loop.yml does (`python3 -I`)
    against a stub gh exiting gh_rc. Returns (rc, stdout, stderr, gh calls).
    Memoized on the CLI's own source: workflow mutations never change it."""
    script = os.path.join(scripts_root, ".github", "scripts", "board_item_marker.py")
    with open(script, encoding="utf-8") as fh:
        key = ("marker-cli", fh.read(), tuple(args), gh_rc)
    if key not in _RUN_CACHE:
        _RUN_CACHE[key] = _run_marker_cli_uncached(args, gh_rc, scripts_root)
    return _RUN_CACHE[key]


def _run_marker_cli_uncached(args, gh_rc, scripts_root):
    with tempfile.TemporaryDirectory() as tmp:
        env = dict(os.environ, GITHUB_REPOSITORY="o/r",
                   PATH=_stub_gh(tmp, gh_rc) + os.pathsep + os.environ.get("PATH", ""))
        for key in ("GITHUB_SERVER_URL", "GITHUB_RUN_ID"):
            env.pop(key, None)
        proc = subprocess.run(
            [sys.executable, "-I", os.path.join(scripts_root, ".github", "scripts", "board_item_marker.py")] + args,
            text=True, capture_output=True, env=env, cwd=tmp)
        log = os.path.join(tmp, "gh-calls.log")
        calls = open(log, encoding="utf-8").read().splitlines() if os.path.exists(log) else []
        return proc.returncode, proc.stdout, proc.stderr, calls


STALL_CLI_CASES = [
    # (title, args, gh exit code, want marker printed, want gh calls)
    ("--step stalled without --issue/--add-label is refused",
     ["--step", "stalled"], 0, False, []),
    ("--step stalled with --issue but no --add-label is refused",
     ["--step", "stalled", "--issue", "7"], 0, False, []),
    ("--step stalled --add-label another label is refused",
     ["--step", "stalled", "--issue", "7", "--add-label", "board:owned"], 0, False, []),
    ("--issue/--add-label on a non-stalled step are refused",
     ["--step", "review", "--issue", "7", "--add-label", "board:stalled"], 0, False, []),
    ("the label add fails -> no marker, non-zero",
     ["--step", "stalled", "--issue", "7", "--add-label", "board:stalled"], 1, False,
     ["issue edit 7 -R o/r --add-label board:stalled"]),
    ("the label add succeeds -> the marker, after the add, and gh's stdout kept out of it",
     ["--step", "stalled", "--issue", "7", "--add-label", "board:stalled"], 0, True,
     ["issue edit 7 -R o/r --add-label board:stalled"]),
    ("regression: a non-stalled step calls no gh",
     ["--step", "review", "--pr", "42"], 0, True, []),
]


def stall_label_findings(doc, scripts_root=ROOT):
    findings = []
    stall_sites = 0
    for job, i, step in _all_steps(doc):
        run = str(step.get("run", ""))
        where = "{0}/{1}".format(job, step.get("id") or step.get("name") or i)
        if "write_marker(" in run:
            findings.append("{0}: writes a marker inline with write_marker( -- every board-loop.yml "
                            "marker goes through the board_item_marker.py CLI, whose --step stalled "
                            "adds board:stalled first (#604)".format(where))
        for line in _logical_lines(run):
            if _BARE_STALLED_APPLY.search(line):
                findings.append(
                    "{0}: applies board:stalled with a bare gh call -- the label goes on only "
                    "through board_item_marker.py --step stalled --issue --add-label, before its "
                    "marker (#604): `{1}`".format(where, line.strip()[:160]))
            m = _MARKER_CLI.search(line)
            if not m:
                continue
            arg = m.group(1).strip('"')
            is_stall = False
            if arg.startswith("$"):
                var = arg[1:]
                can_stall = re.search(r"\b{0}=\"?stalled\"?(?:\s|;|$)".format(re.escape(var)), run, re.M)
                if can_stall:
                    is_stall = True
                    stall_sites += 1
                    if not (_STALL_FLAGS.search(run) and "${stall_args[@]}" in line):
                        findings.append(
                            "{0}: --step \"${1}\" can be stalled but the invocation does not pass "
                            "--issue \"$ISSUE_NUMBER\" --add-label \"board:stalled\" for it (#604)".format(where, var))
            elif arg == "stalled":
                is_stall = True
                stall_sites += 1
                if not _STALL_FLAGS.search(line):
                    findings.append(
                        "{0}: renders a stalled marker without --issue \"$ISSUE_NUMBER\" --add-label "
                        "\"board:stalled\" -- the label must go on before the marker (#604)".format(where))
            if _FAIL_LOUD.search(line):
                continue
            if is_stall:
                findings.append(
                    "{0}: a stalled-marker render is not followed by `|| {{ echo \"::error::...\"; exit 1; }}` "
                    "-- a failed board:stalled add would post a marker-less comment and carry on (#604)".format(where))
            else:
                # #786: errexit already stops a step on a failed render; the
                # guard is what names why, and what keeps the render
                # fail-closed if a step ever runs without errexit.
                findings.append(
                    "{0}: a `--step {1}` marker render is not followed by `|| {{ echo \"::error::...\"; "
                    "exit 1; }}` -- a failed render must stop the step and say why, never leave a "
                    "comment the next run cannot read as this step's (#786)".format(where, arg))
    if stall_sites == 0:
        findings.append("no stalled-marker site found in board-loop.yml -- the #604 check is vacuous")
    for title, args, gh_rc, want_marker, want_calls in STALL_CLI_CASES:
        rc, out, err, calls = _run_marker_cli(args, gh_rc, scripts_root)
        printed = "wing-commander-board-item:" in out
        ok = (rc == 0) == want_marker and printed == want_marker and calls == want_calls
        if want_marker and "issues/7" in out:
            ok = False
        if not want_marker and out.strip():
            ok = False
        if not ok:
            findings.append("board_item_marker.py `{0}`: rc={1} stdout={2!r} gh calls={3!r} stderr={4!r} "
                            "(#604)".format(title, rc, out.strip()[:120], calls, err.strip()[-160:]))
    return findings


# ---------------------------------------------------------------------------
# #604 (b): readiness's stop re-check gates every durable action it takes
# (FR-051/FR-052), not only the `ready` decision.
# ---------------------------------------------------------------------------

_DURABLE_RUN = re.compile(
    r"\bgh\s+(?:issue\s+(?:comment|create|edit|close|reopen)|pr\s+(?:comment|edit|close|review)"
    r"|label\s+create)\b|\bgh\s+api\b[^\n]*-X\s+(?:POST|PATCH|PUT|DELETE)|board_item_marker\.py")
# Composites readiness calls that write to GitHub. The labels composite
# (repository label setup, idempotent, run before the re-check) is not an
# item action and stays outside this rule.
_DURABLE_USES = ("wing-commander-outstanding-task-item",)
_STOP_GATE = ("==", ("path", "steps.killswitch-recheck.outputs.paused"), ("lit", "false"))


def readiness_stop_gate_findings(doc):
    findings = []
    steps = ((doc.get("jobs") or {}).get("readiness") or {}).get("steps") or []
    recheck_at = next((i for i, s in enumerate(steps)
                       if isinstance(s, dict) and s.get("id") == "killswitch-recheck"), None)
    if recheck_at is None:
        return ["readiness: no `killswitch-recheck` step (FR-051/FR-052, #604)"]
    recheck = steps[recheck_at]
    if "if" in recheck or recheck.get("continue-on-error"):
        findings.append("readiness/killswitch-recheck: carries an `if:` or continue-on-error -- the "
                        "re-check must always run and a failed one must stop the job (#604)")
    durable = 0
    for i, step in enumerate(steps):
        if not isinstance(step, dict):
            continue
        name = step.get("id") or step.get("name") or str(i)
        is_durable = (_DURABLE_RUN.search(str(step.get("run", "")))
                      or any(u in str(step.get("uses", "")) for u in _DURABLE_USES))
        if not is_durable:
            continue
        if i < recheck_at:
            findings.append("readiness/{0}: takes a durable action before the stop re-check "
                            "(FR-051/FR-052, #604)".format(name))
            continue
        durable += 1
        if not _has_conjunct(step.get("if"), _STOP_GATE):
            findings.append(
                "readiness/{0}: a durable action whose `if:` does not carry "
                "`steps.killswitch-recheck.outputs.paused == 'false'` as a top-level conjunct -- "
                "a stop request that lands mid-run still lets it write (FR-051/FR-052, #604)".format(name))
    if durable == 0:
        findings.append("readiness: no durable step found after the stop re-check -- the #604 check is vacuous")
    return findings


# ---------------------------------------------------------------------------
# #557: a comments fetch that feeds a marker reader fails its step on error
# (never `[]`, never a null marker), and prove-gate enters prove only for a
# PR that passes BOARD_PR_OWNED_JQ. Checked statically on the text and by
# running the three shipped steps against a stub gh.
# ---------------------------------------------------------------------------

_COMMENTS_FETCH = re.compile(r'gh api "repos/\$GITHUB_REPOSITORY/issues/\$\w+/comments"')


def fetch_handling_findings(doc):
    """Every comments fetch in a marker-reading step is the condition of an
    `if ! ...; then` whose body emits ::error:: and exits 1 -- no `||`
    swallow in the command, no `[]` written in its place (#557)."""
    findings = []
    for job, step_id in MARKER_READERS:
        where = "{0}/{1}".format(job, step_id)
        run = _step_run(doc, job, step_id)
        for m in _COMMENTS_FETCH.finditer(run):
            line_start = run.rfind("\n", 0, m.start()) + 1
            if run[line_start:m.start()].strip() != "if !":
                findings.append(
                    "{0}: comments fetch is not the condition of `if ! gh api ...; then` -- a "
                    "failed fetch is not handled explicitly (#557)".format(where))
                continue
            then_at = run.find("; then\n", m.end())
            # The `fi` closing THIS if: same indentation as its `if !` line
            # (a nested if -- select's 404/410 branch -- closes earlier).
            indent = run[line_start:m.start()][:len(run[line_start:m.start()]) - len(
                run[line_start:m.start()].lstrip())]
            fi = (re.compile(r"\n" + re.escape(indent) + r"fi\b").search(run, then_at)
                  if then_at >= 0 else None)
            if fi is None:
                findings.append("{0}: comments fetch has no `; then ... fi` failure branch (#557)".format(where))
                continue
            cmd, body = run[m.start():then_at], run[then_at:fi.start()]
            if "||" in cmd:
                findings.append("{0}: comments fetch swallows its failure with `||` (#557)".format(where))
            if "'[]'" in body or "exit 1" not in body or "::error::" not in body:
                findings.append(
                    "{0}: comments fetch failure branch does not emit ::error:: and `exit 1` "
                    "(or writes `[]` in place of the comments) (#557)".format(where))
    return findings


# #564: the other live lookups that feed select's in-flight decision or
# resume's step resolution. (job, step id, needle, what, text that must
# follow the lookup in the same step: its "not found" test).
_LIVE_LOOKUPS = (
    ("select", "select", 'gh api "repos/$GITHUB_REPOSITORY/pulls/$pr_number"',
     "PR-state lookup", "grep -qE 'HTTP 404'"),
    ("select", "resume", 'gh api "repos/$GITHUB_REPOSITORY/pulls/$marker_pr"',
     "marker-PR lookup", "grep -qE 'HTTP 404'"),
    ("select", "resume", "-f state=open -f labels=board:owned",
     "board:owned fallback search", None),
    ("select", "resume", "git ls-remote --exit-code --heads origin",
     "branch lookup", '-ne 2 ]'),
)
_SWALLOWS = ("2>/dev/null", "2>&1", "|| continue", "|| true", "|| echo")


def lookup_handling_findings(doc):
    """#564: each live lookup keeps its stderr (no /dev/null), has no `||`
    swallow, tells "not found" apart where one exists, and is followed in
    its step by an ::error:: + `exit 1` branch. The stub-gh run in
    fetch_behaviour_findings() proves the behaviour; this names the line."""
    findings = []
    for job, step_id, needle, what, not_found in _LIVE_LOOKUPS:
        where = "{0}/{1}: {2}".format(job, step_id, what)
        run = _step_run(doc, job, step_id)
        at = run.find(needle)
        if at < 0:
            findings.append("{0} not found (#564)".format(where))
            continue
        lines = run.split("\n")
        idx = run.count("\n", 0, at)
        first = idx
        while first > 0 and lines[first - 1].rstrip().endswith("\\"):
            first -= 1
        last = idx
        while last < len(lines) - 1 and lines[last].rstrip().endswith("\\"):
            last += 1
        stmt = "\n".join(lines[first:last + 1])
        for bad in _SWALLOWS:
            if bad in stmt:
                findings.append("{0} swallows its failure with `{1}` (#564)".format(where, bad))
        rest = "\n".join(lines[last + 1:last + 25])
        if not_found and not_found not in rest:
            findings.append("{0} does not tell \"not found\" (`{1}`) apart from other errors "
                            "(#564)".format(where, not_found))
        if "::error::" not in rest or "exit 1" not in rest:
            findings.append("{0} has no ::error:: + `exit 1` failure branch (#564)".format(where))
    return findings


_STUB_GH = r"""#!/usr/bin/env bash
# Gate 97 stub gh (#557). Emits the already --jq-projected lines.
echo "gh $*" >> "$STUB_LOG"
case "$*" in
  "api repos/$GITHUB_REPOSITORY/issues/"*"/comments"*)
    if [ -n "${STUB_COMMENTS_FAIL:-}" ] && { [ -z "${STUB_FAIL_ISSUE:-}" ] || [[ "$*" == *"/issues/$STUB_FAIL_ISSUE/comments"* ]]; }; then
      case "$STUB_COMMENTS_FAIL" in
        404) echo "gh: Not Found (HTTP 404)" >&2 ;;
        410) echo "gh: This issue was deleted (HTTP 410)" >&2 ;;
        *) echo "gh: Server Error (HTTP $STUB_COMMENTS_FAIL)" >&2 ;;
      esac
      exit 1
    fi
    cat "$STUB_COMMENTS" ;;
  "api repos/$GITHUB_REPOSITORY/issues/"*"/timeline"*) ;;
  "api repos/$GITHUB_REPOSITORY/issues -X GET"*"labels=board:owned"*)
    if [ -n "${STUB_OWNED_FAIL:-}" ]; then echo "gh: Server Error (HTTP $STUB_OWNED_FAIL)" >&2; exit 1; fi
    if [ -n "${STUB_OWNED:-}" ]; then cat "$STUB_OWNED"; fi ;;
  "api repos/$GITHUB_REPOSITORY/issues -X GET"*)
    echo '{"number":7,"author":{"login":"alice"},"authorAssociation":"OWNER","labels":[],"state":"OPEN","createdAt":"2026-01-01T00:00:00Z"}'
    echo '{"number":8,"author":{"login":"alice"},"authorAssociation":"OWNER","labels":[],"state":"OPEN","createdAt":"2026-01-02T00:00:00Z"}' ;;
  "api repos/$GITHUB_REPOSITORY/pulls/"*)
    case "${STUB_PULLS:-404}" in
      ok) cat "$STUB_PR" ;;
      404) echo "gh: Not Found (HTTP 404)" >&2; exit 1 ;;
      *) echo "gh: Server Error (HTTP $STUB_PULLS)" >&2; exit 1 ;;
    esac ;;
  "issue comment"*) ;;
  *) echo "stub gh: unexpected call: $*" >&2; exit 3 ;;
esac
"""

# #564: resume's branch lookup. Exit 2 is --exit-code's "no such ref";
# 128 is what git gives for an unreachable remote or bad credentials.
_STUB_GIT = r"""#!/usr/bin/env bash
echo "git $*" >> "$STUB_LOG"
case "$1" in
  ls-remote)
    rc="${STUB_LS_REMOTE_RC:-2}"
    if [ "$rc" = 128 ]; then echo "fatal: unable to access 'origin': Could not resolve host" >&2; fi
    exit "$rc" ;;
  *) echo "stub gh: unexpected call: git $*" >&2; exit 3 ;;
esac
"""

_STUB_REPO = "example/wing-commander"


def _pr_event(labels, head_repo):
    return {"pull_request": {"number": 42, "merged": True, "body": "Fixes #7",
                             "labels": [{"name": n} for n in labels],
                             "head": {"repo": {"full_name": head_repo} if head_repo else None}}}


def _fetch_cases():
    """(title, job, step id, env overrides, pull_request event or None,
    comments fetch failure ("" = none, else the HTTP status the stub
    returns), check(rc, out, outputs, gh_log, runner_temp) -> problem|None).
    STUB_FAIL_ISSUE in the env overrides limits the failure to one issue."""
    owned = _pr_event(["board:owned"], _STUB_REPO)

    def failed_loudly(key, bad):
        def check(rc, out, outputs, log, rt):
            if rc == 0:
                return "step succeeded on a failed comments fetch (#557)"
            if "::error::" not in out:
                return "step failed without an ::error:: annotation (#557)"
            if outputs.get(key, "") == bad:
                return "step still wrote {0}={1}".format(key, bad)
            return None
        return check

    def ok_with(key, want):
        def check(rc, out, outputs, log, rt):
            if rc != 0:
                return "step failed (rc {0}): {1}".format(rc, out.strip().splitlines()[-3:])
            if want is not None and outputs.get(key) != want:
                return "expected {0}={1}, got {2!r}".format(key, want, outputs.get(key))
            return None
        return check

    pr_marker = {"STUB_COMMENTS": "{tmp}/comments-pr.jsonl", "STUB_PR": "{tmp}/pr-open-owned.json"}

    def lookup_failed(key):
        # #564: a failed lookup other than "not found" fails the step with
        # ::error:: and writes no decision output at all.
        def check(rc, out, outputs, log, rt):
            if rc == 0:
                return "step succeeded on a failed lookup (#564)"
            if "::error::" not in out:
                return "step failed without an ::error:: annotation (#564)"
            if key in outputs:
                return "step still wrote {0}={1!r} (#564)".format(key, outputs[key])
            return None
        return check

    def pr_states(want):
        def check(rc, out, outputs, log, rt):
            if rc != 0:
                return "step failed (rc {0}): {1}".format(rc, out.strip().splitlines()[-3:])
            try:
                with open(os.path.join(rt, "board-eligibility-input.json"), encoding="utf-8") as fh:
                    got = json.load(fh)["pr_state_by_number"]
            except (OSError, ValueError, KeyError) as exc:
                return "no board-eligibility-input.json to inspect: {0}".format(exc)
            if got != want:
                return "expected pr_state_by_number {0}, got {1}".format(want, got)
            return None
        return check

    def not_owned(rc, out, outputs, log, rt):
        if rc != 0:
            return "step failed (rc {0})".format(rc)
        if outputs.get("eligible") != "false":
            return "a PR that fails BOARD_PR_OWNED_JQ entered prove (eligible={0!r})".format(
                outputs.get("eligible"))
        if "/comments" in log:
            return "fetched the issue's comments for a PR that is not a board item"
        return None

    def gone_dropped(rc, out, outputs, log, rt):
        if rc != 0:
            return ("a 404/410 on one issue's comments failed select (rc {0}); it should drop "
                    "that issue and continue".format(rc))
        if "::warning::" not in out:
            return "the dropped issue was not reported with a ::warning::"
        try:
            with open(os.path.join(rt, "board-eligibility-input.json"), encoding="utf-8") as fh:
                numbers = [i.get("number") for i in json.load(fh)["open_issues"]]
        except (OSError, ValueError, KeyError) as exc:
            return "no board-eligibility-input.json to inspect: {0}".format(exc)
        if numbers != [8]:
            return "expected candidates [8] after dropping gone issue #7, got {0}".format(numbers)
        return None

    return [
        ("select: per-issue comments fetch fails (HTTP 502)", "select", "select", {}, None, "502",
         failed_loudly("issue-number", "7")),
        ("select: one issue's comments fetch fails (HTTP 500)", "select", "select",
         {"STUB_FAIL_ISSUE": "8"}, None, "500", failed_loudly("issue-number", "7")),
        ("select: issue gone (HTTP 404) -> dropped, select continues", "select", "select",
         {"STUB_FAIL_ISSUE": "7"}, None, "404", gone_dropped),
        ("select: issue gone (HTTP 410) -> dropped, select continues", "select", "select",
         {"STUB_FAIL_ISSUE": "7"}, None, "410", gone_dropped),
        ("select: comments fetch succeeds (stub sanity)", "select", "select", {}, None, "",
         ok_with("issue-number", None)),
        ("resume: comments fetch fails", "select", "resume", {"ISSUE_NUMBER": "7"}, None, "502",
         failed_loudly("step", "triage")),
        ("resume: comments fetch succeeds (stub sanity)", "select", "resume", {"ISSUE_NUMBER": "7"},
         None, "", ok_with("step", None)),
        # #564: select's PR-state lookup and resume's live lookups. The
        # marker (review, pr 42, branch fix/7-thing) is on every issue.
        ("select: marker PR 404 -> state absent, select succeeds", "select", "select",
         dict(pr_marker, STUB_PULLS="404"), None, "", pr_states({})),
        ("select: marker PR found -> state recorded (stub sanity)", "select", "select",
         dict(pr_marker, STUB_PULLS="ok"), None, "", pr_states({"42": "OPEN"})),
        ("select: marker PR lookup fails (HTTP 500)", "select", "select",
         dict(pr_marker, STUB_PULLS="500"), None, "", lookup_failed("issue-number")),
        ("resume: marker PR 404, branch absent (ls-remote 2), no fallback -> triage", "select",
         "resume", dict(pr_marker, ISSUE_NUMBER="7", STUB_PULLS="404", STUB_LS_REMOTE_RC="2"),
         None, "", ok_with("step", "triage")),
        ("resume: marker PR 404 -> board:owned fallback adopted", "select", "resume",
         dict(pr_marker, ISSUE_NUMBER="7", STUB_PULLS="404", STUB_OWNED="{tmp}/owned-prs.jsonl"),
         None, "", ok_with("pr", "50")),
        ("resume: marker PR 404, branch present (ls-remote 0) -> fix", "select", "resume",
         dict(pr_marker, ISSUE_NUMBER="7", STUB_PULLS="404", STUB_LS_REMOTE_RC="0"),
         None, "", ok_with("step", "fix")),
        ("resume: marker PR found (stub sanity) -> review", "select", "resume",
         dict(pr_marker, ISSUE_NUMBER="7", STUB_PULLS="ok"), None, "", ok_with("step", "review")),
        ("resume: marker PR lookup fails (HTTP 500)", "select", "resume",
         dict(pr_marker, ISSUE_NUMBER="7", STUB_PULLS="500"), None, "", lookup_failed("step")),
        ("resume: board:owned fallback search fails (HTTP 500)", "select", "resume",
         dict(pr_marker, ISSUE_NUMBER="7", STUB_PULLS="404", STUB_OWNED_FAIL="500"), None, "",
         lookup_failed("step")),
        ("resume: branch lookup fails (ls-remote 128)", "select", "resume",
         dict(pr_marker, ISSUE_NUMBER="7", STUB_PULLS="404", STUB_LS_REMOTE_RC="128"), None, "",
         lookup_failed("step")),
        ("prove-gate: owned PR, marker present -> prove", "prove-gate", "gate", {}, owned, "",
         ok_with("eligible", "true")),
        ("prove-gate: owned PR, comments fetch fails", "prove-gate", "gate", {}, owned, "502",
         failed_loudly("eligible", "true")),
        ("prove-gate: merged PR without board:owned -> not a board item", "prove-gate", "gate", {},
         _pr_event(["bug"], _STUB_REPO), "", not_owned),
        ("prove-gate: board:owned PR from another repository -> not a board item", "prove-gate",
         "gate", {}, _pr_event(["board:owned"], "someone/fork"), "", not_owned),
        ("prove-gate: board:owned PR whose head repository was deleted -> not a board item",
         "prove-gate", "gate", {}, _pr_event(["board:owned"], None), "", not_owned),
    ]


def _marker_comment_line(pr=None, branch=None):
    return json.dumps({
        "created_at": "2026-01-05T00:00:00Z", "user": {"login": BOT_LOGIN, "type": "Bot"},
        "body": "<!-- wing-commander-board-item: " + json.dumps(
            {"step": "review", "round": 1, "pr": pr, "branch": branch,
             "base_sha": None}) + " -->"})


def fetch_behaviour_findings(doc):
    """Runs select/select, select/resume and prove-gate/gate for real under
    `bash -e` (the runner's default shell) against a stub gh (#557)."""
    try:
        from wc_shell_harness import ensure_jq, resolve_bash, run_step
    except ImportError as exc:
        return ["cannot import wc_shell_harness: {0}".format(exc)]
    env_block = doc.get("env") or {}
    runs = {(j, s): _step_run(doc, j, s) for j, s in MARKER_READERS}
    key = ("fetch-behaviour", tuple(sorted(env_block.items())), tuple(sorted(runs.items())))
    if key in _RUN_CACHE:
        return list(_RUN_CACHE[key])
    ensure_jq()
    bash = resolve_bash()
    findings = []
    with tempfile.TemporaryDirectory() as tmp:
        workdir = os.path.join(tmp, "work")
        shutil.copytree(os.path.join(ROOT, ".github", "scripts"),
                        os.path.join(workdir, ".github", "scripts"),
                        ignore=shutil.ignore_patterns("tests", "fixtures", "__pycache__"))
        bindir = os.path.join(tmp, "bin")
        os.makedirs(bindir)
        gh = os.path.join(bindir, "gh")
        with open(gh, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(_STUB_GH)
        os.chmod(gh, 0o755)
        git = os.path.join(bindir, "git")
        with open(git, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(_STUB_GIT)
        os.chmod(git, 0o755)
        with open(os.path.join(tmp, "comments-pr.jsonl"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(_marker_comment_line(pr=42, branch="fix/7-thing") + "\n")
        with open(os.path.join(tmp, "pr-open-owned.json"), "w", encoding="utf-8") as fh:
            json.dump({"number": 42, "state": "open", "merged": False,
                       "labels": [{"name": "board:owned"}],
                       "head": {"repo": {"full_name": _STUB_REPO}}}, fh)
        with open(os.path.join(tmp, "owned-prs.jsonl"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps({"number": 50, "body": "Fixes #7"}) + "\n")
        comments = os.path.join(tmp, "comments.jsonl")
        with open(comments, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(_marker_comment_line() + "\n")
        for idx, (title, job, step_id, env_over, event, fail, check) in enumerate(_fetch_cases()):
            run = runs[(job, step_id)]
            if not run:
                findings.append("fetch `{0}`: step {1}/{2} not found".format(title, job, step_id))
                continue
            runner_temp = os.path.join(tmp, "rt{0}".format(idx))
            os.makedirs(runner_temp)
            log = os.path.join(tmp, "gh{0}.log".format(idx))
            open(log, "w").close()
            event_path = os.path.join(tmp, "event{0}.json".format(idx))
            with open(event_path, "w", encoding="utf-8") as fh:
                json.dump(event or {}, fh)
            env = {"PATH": bindir + os.pathsep + os.environ["PATH"],
                   "GITHUB_REPOSITORY": _STUB_REPO, "GITHUB_EVENT_PATH": event_path,
                   "GH_TOKEN": "stub", "BOT_LOGIN": BOT_LOGIN,
                   "BOARD_PR_OWNED_JQ": str(env_block.get("BOARD_PR_OWNED_JQ", "")),
                   "BOARD_PR_STATE_JQ": str(env_block.get("BOARD_PR_STATE_JQ", "")),
                   "STUB_LOG": log, "STUB_COMMENTS": comments,
                   "STUB_COMMENTS_FAIL": fail, "STUB_FAIL_ISSUE": "", "STUB_PULLS": "404",
                   "STUB_OWNED": "", "STUB_OWNED_FAIL": "", "STUB_LS_REMOTE_RC": "2",
                   "PR_BODY": "Fixes #7", "PR_NUMBER": "42", "MERGED": "true",
                   # specs/060-self-redrive-concurrency: prove-gate's "gate"
                   # step now branches on EVENT_NAME (workflow_dispatch vs.
                   # the ordinary pull_request: closed trigger these fixtures
                   # exercise) and reads DIRECTED_ISSUE on that other branch.
                   "EVENT_NAME": "pull_request", "MERGED_EVENT": "true", "DIRECTED_ISSUE": ""}
            env.update({k: v.replace("{tmp}", tmp) for k, v in env_over.items()})
            rc, out, outputs, _summary = run_step(bash, run, workdir, env, runner_temp)
            with open(log, encoding="utf-8") as fh:
                gh_log = fh.read()
            unexpected = [l for l in out.splitlines() if "stub gh: unexpected call" in l]
            if unexpected:
                findings.append("fetch `{0}`: {1}".format(title, unexpected[0]))
                continue
            problem = check(rc, out, outputs, gh_log, runner_temp)
            if problem:
                findings.append("fetch `{0}`: {1}".format(title, problem))
    _RUN_CACHE[key] = tuple(findings)
    return findings


# specs/093-not-ready-board-release FR-002/FR-004(a)/FR-008/FR-013: the
# readiness job's not-ready report step records the outcome (a readiness
# marker carrying nr_count/nr_head_sha/nr_class) and, at the threshold, hands
# the item over (a stalled marker carrying pr/nr_head_sha, board:stalled
# added first). Dropping either leaves every other check green, so pin both.
def not_ready_report_findings(doc):
    steps = ((doc.get("jobs") or {}).get("readiness") or {}).get("steps") or []
    run = next((str(s.get("run", "")) for s in steps
                if isinstance(s, dict) and "not_ready_handover_due(" in str(s.get("run", ""))), None)
    if run is None:
        return ["readiness: no not-ready report step calling not_ready_handover_due() (specs/093 FR-004(a))"]
    findings = []
    lines = _logical_lines(run)
    if not any("--step readiness" in ln and "--nr-count" in ln and "--nr-head-sha" in ln
               and "--nr-class" in ln for ln in lines):
        findings.append("readiness: the not-ready report no longer writes a readiness marker with "
                        "--nr-count/--nr-head-sha/--nr-class (specs/093 FR-002)")
    if not any("--step stalled" in ln and "--pr" in ln and "--nr-head-sha" in ln
               and '--add-label "board:stalled"' in ln for ln in lines):
        findings.append("readiness: the not-ready threshold no longer hands over with a stalled marker "
                        "carrying --pr/--nr-head-sha and board:stalled (specs/093 FR-004(a)/FR-008)")
    if "not_ready_handover_due(" not in run or not re.search(
            r"case \"\$handover_due\" in\s*\n\s*true\|false\) ;;\s*\n\s*\*\)[^\n]*exit 1", run):
        findings.append("readiness: the handover decision is not board_eligibility.not_ready_handover_due()'s, "
                        "or an unanswered call is not refused -- the handover would be silently skipped "
                        "(specs/093 FR-003/FR-004(a))")
    if not any("--step readiness" in ln and "--nr-reason" in ln for ln in lines):
        findings.append("readiness: the not-ready record no longer carries --nr-reason, the unmet "
                        "condition FR-002 requires (and FR-009's dedup reads)")
    # Code review of #1010: the count and round survive every hop, a
    # directed run and a review-fixup round advance included.
    jobs = doc.get("jobs") or {}
    nr_env = next((str((s.get("env") or {}).get("NR_COUNT", "")) for s in steps
                   if isinstance(s, dict) and "not_ready_handover_due(" in str(s.get("run", ""))), "")
    if nr_env.strip() != "${{ steps.pr.outputs.nr-count }}":
        findings.append("readiness: NR_COUNT is not the PR step's own nr-count -- a second chain "
                        "decides which upstream count readiness writes")
    for job in ("review", "readiness"):
        for s in (jobs.get(job) or {}).get("steps") or []:
            if isinstance(s, dict) and s.get("id") == "pr":
                w = s.get("with") or {}
                for key in (("nr-count",) if job == "review" else ("nr-count", "round")):
                    if "steps.resolve-directed-pr.outputs." + key not in str(w.get(key, "")):
                        findings.append("{0}: the PR step's {1} does not fall back to resolve-directed-pr's".format(job, key))
    for ln in lines:
        if "gh issue comment" in ln and "--body \"$body\"" in ln and "|| {" not in ln:
            findings.append("readiness: a not-ready comment post is unchecked -- a failed post "
                            "silently writes no record (specs/093 FR-002)")
    publish = "\n".join(_logical_lines("\n".join(
        str(s.get("run", "")) for s in (jobs.get("review-fixup-publish") or {}).get("steps") or []
        if isinstance(s, dict))))
    for ln in publish.split("\n"):
        if "--step review" in ln and "board_item_marker.py" in ln and "--nr-count" not in ln:
            findings.append("review-fixup-publish: the round-advance marker drops --nr-count, resetting "
                            "the not-ready count (specs/093 research.md D5)")
    # FR-003: resume asks board_eligibility whether a hold ended; it never
    # compares the record's head SHA itself.
    resume = _step_run(doc, "select", "resume")
    if "not_ready_head_moved(" not in resume or '["head_sha"]' in resume:
        findings.append("select: resume re-derives the not-ready hold inline instead of calling "
                        "board_eligibility.not_ready_head_moved() (specs/093 FR-003)")
    return findings


# specs/093-not-ready-board-release FR-009 (code review of #1010): the
# dedup finds the newest loop marker for the same PR, head SHA and unmet
# condition by the marker's own nr_reason (never the prose) and returns
# THAT comment's id to edit -- not the bot's newest comment, which may be a
# later marker-less one.
_BOT = "wing-commander-bot[bot]"


def _dedup_comment(cid, created_at, marker):
    body = "Not ready.\n\n"
    if marker is not None:
        body += "<!-- wing-commander-board-item: {0} -->".format(json.dumps(marker, sort_keys=True))
    return {"id": cid, "created_at": created_at, "body": body,
            "user": {"login": _BOT, "type": "Bot"}}


_NR = {"step": "readiness", "pr": 42, "nr_head_sha": "deadbeef", "nr_class": "self-clearing",
       "nr_count": 1, "nr_reason": "checks not green on head_sha deadbeef (stale or failing)"}
DEDUP_CASES = [
    ("same pr/head/reason, a later marker-less bot comment -> the marker comment's id",
     [_dedup_comment(111, "2026-01-01T00:00:00Z", _NR), _dedup_comment(222, "2026-01-02T00:00:00Z", None)],
     "111"),
    ("a marker-less loop comment in the same second as the marker comment -> the marker comment's id",
     [_dedup_comment(333, "2026-01-01T00:00:00Z", None), _dedup_comment(111, "2026-01-01T00:00:00Z", _NR)],
     "111"),
    ("different unmet condition -> new comment",
     [_dedup_comment(111, "2026-01-01T00:00:00Z", dict(_NR, nr_reason="1 open in-scope finding(s)"))], ""),
    ("different head -> new comment",
     [_dedup_comment(111, "2026-01-01T00:00:00Z", dict(_NR, nr_head_sha="cafefeed"))], ""),
    ("marker without nr_reason (prose only) -> new comment",
     [_dedup_comment(111, "2026-01-01T00:00:00Z", {k: v for k, v in _NR.items() if k != "nr_reason"})], ""),
]


def not_ready_dedup_findings(doc, scripts_root=ROOT):
    steps = ((doc.get("jobs") or {}).get("readiness") or {}).get("steps") or []
    run = next((str(s.get("run", "")) for s in steps
                if isinstance(s, dict) and "not_ready_handover_due(" in str(s.get("run", ""))), "")
    code = _heredoc(run, "same_comment_id")
    if code is None:
        return ["readiness: no `same_comment_id` dedup heredoc in the not-ready report (specs/093 FR-009)"]
    findings = []
    if "--edit-last" in run:
        findings.append("readiness: the not-ready dedup edits with --edit-last, not by the matched comment's id")
    if not any(isinstance(s, dict) and "dedup-comment-id" in str(s.get("if", ""))
               and "issues/comments/$COMMENT_ID" in str(s.get("run", "")) for s in steps):
        findings.append("readiness: no step edits the matched not-ready comment by its id (dedup-comment-id)")
    with tempfile.TemporaryDirectory() as tmp:
        os.makedirs(os.path.join(tmp, "wc-pristine"))
        os.symlink(os.path.join(os.path.abspath(scripts_root), ".github", "scripts"),
                   os.path.join(tmp, "wc-pristine", "scripts"))
        for i, (title, comments, expected) in enumerate(DEDUP_CASES):
            # One file per case: _exec_heredoc memoizes on the env.
            path = os.path.join(tmp, "comments-{0}.json".format(i))
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(comments, fh)
            env = {"RUNNER_TEMP": tmp, "COMMENTS_PATH": path, "BOT_LOGIN": _BOT, "PR_NUMBER": "42",
                   "HEAD_SHA": "deadbeef", "UNMET": _NR["nr_reason"]}
            rc, out, err = _exec_heredoc(code, env, scripts_root)
            if rc != 0 or out.strip() != expected:
                findings.append("dedup `{0}`: expected {1!r}, got rc={2} {3!r} {4}".format(
                    title, expected, rc, out.strip(), err.strip()[-200:]))
    return findings


def all_findings(text, table=None, scripts_root=ROOT):
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        return ["board-loop.yml does not parse: {0}".format(exc)]
    return (static_findings(doc) + simulation_findings(doc, table)
            + resume_findings(doc, scripts_root) + select_lookup_findings(doc, scripts_root)
            + owned_jq_findings(doc, scripts_root) + marker_reader_findings(doc)
            + fetch_handling_findings(doc) + lookup_handling_findings(doc)
            + fetch_behaviour_findings(doc) + breach_retry_findings(doc, scripts_root)
            + stall_label_findings(doc, scripts_root) + readiness_stop_gate_findings(doc)
            + not_ready_report_findings(doc) + not_ready_dedup_findings(doc, scripts_root))


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

# #564: the four live lookups as shipped, and as they were before #564.
_SELECT_PR_LOOKUP = (
    "              if ! gh api \"repos/$GITHUB_REPOSITORY/pulls/$pr_number\" \\\n"
    "                  > \"$RUNNER_TEMP/board-lookup-pr.json\" 2> \"$RUNNER_TEMP/board-lookup-pr.err\"; then\n"
    "                if grep -qE 'HTTP 404' \"$RUNNER_TEMP/board-lookup-pr.err\"; then\n"
    "                  continue\n"
    "                fi\n"
    "                cat \"$RUNNER_TEMP/board-lookup-pr.err\" >&2\n")
_SELECT_PR_LOOKUP_PRE_564 = (
    "              gh api \"repos/$GITHUB_REPOSITORY/pulls/$pr_number\" \\\n"
    "                > \"$RUNNER_TEMP/board-lookup-pr.json\" 2>/dev/null || continue\n"
    "              if false; then\n")
_RESUME_PR_LOOKUP = (
    "            if gh api \"repos/$GITHUB_REPOSITORY/pulls/$marker_pr\" \\\n"
    "                > \"$RUNNER_TEMP/board-marker-pr.json\" 2> \"$RUNNER_TEMP/board-marker-pr.err\"; then\n")
_RESUME_PR_LOOKUP_PRE_564 = (
    "            if gh api \"repos/$GITHUB_REPOSITORY/pulls/$marker_pr\" \\\n"
    "                > \"$RUNNER_TEMP/board-marker-pr.json\" 2>/dev/null; then\n")
_RESUME_FALLBACK = (
    "            if ! gh api \"repos/$GITHUB_REPOSITORY/issues\" -X GET --paginate \\\n"  # wc-pagination-exempt: Gate 97 self-test mutation text, not a real invocation
    "                -f state=open -f labels=board:owned \\\n"
    "                --jq '.[] | {number, body}' | jq -s '.' \\\n"
    "                > \"$RUNNER_TEMP/board-owned-prs.json\"; then\n")
# Pre-#564 this sat bare in a $(...) assignment: under the runner's
# `bash -e` plus pipefail a failure still stopped the step, but silently.
_RESUME_FALLBACK_PRE_564 = (
    "            gh api \"repos/$GITHUB_REPOSITORY/issues\" -X GET --paginate \\\n"  # wc-pagination-exempt: Gate 97 self-test mutation text, not a real invocation
    "                -f state=open -f labels=board:owned \\\n"
    "                --jq '.[] | {number, body}' 2>/dev/null | jq -s '.' \\\n"
    "                > \"$RUNNER_TEMP/board-owned-prs.json\"\n"
    "            if false; then\n")
_RESUME_LS_REMOTE = (
    "            git ls-remote --exit-code --heads origin \"$marker_branch\" >/dev/null \\\n"
    "              2> \"$RUNNER_TEMP/board-ls-remote.err\" || ls_remote_rc=$?\n")
_RESUME_LS_REMOTE_PRE_564 = (
    "            git ls-remote --exit-code --heads origin \"$marker_branch\" >/dev/null \\\n"
    "              2>&1 || ls_remote_rc=2\n")

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
    sub("review without !cancelled()",
        "      !cancelled()\n      && (needs.select.result == 'success' || inputs.directed-stage == 'review')",
        "      (needs.select.result == 'success' || inputs.directed-stage == 'review')", after="\n  review:\n")
    sub("readiness without !cancelled()",
        "      !cancelled()\n      && (needs.select.result == 'success' || inputs.directed-stage == 'readiness')",
        "      (needs.select.result == 'success' || inputs.directed-stage == 'readiness')",
        after="\n  readiness:\n")
    # PR #490 review, 2026-09-28: reverting to the bare select guard makes a
    # directed review/readiness dispatch skip its own job -- select is
    # skipped by design on that trigger, so `== 'success'` alone is never
    # true. Caught by simulation (the "directed dispatch" scenarios below),
    # not by any static shape check.
    sub("review select guard reverted to the pre-#490-fix bare form",
        "(needs.select.result == 'success' || inputs.directed-stage == 'review')",
        "needs.select.result == 'success'", after="\n  review:\n")
    sub("readiness select guard reverted to the pre-#490-fix bare form",
        "(needs.select.result == 'success' || inputs.directed-stage == 'readiness')",
        "needs.select.result == 'success'", after="\n  readiness:\n")
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
        "      && (needs.select.result == 'success' || inputs.directed-stage == 'review')\n", "",
        after="\n  review:\n")
    sub("fix without resolve-model.result guard",
        "      && needs.resolve-model.result == 'success'\n", "", after="\n  fix:\n")
    sub("fix (the publisher) checks the pause at job level again (spec 095)",
        "        || (needs.select.outputs.step == 'fix' && needs.select.outputs.branch != '' && needs.select.outputs.pr == '')\n      )\n",
        "        || (needs.select.outputs.step == 'fix' && needs.select.outputs.branch != '' && needs.select.outputs.pr == '')\n      ) && vars.WING_COMMANDER_BOARD_LOOP_PAUSED != 'true'\n",
        after="\n  fix:\n")
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
        "      !cancelled()\n      && (needs.select.result == 'success' || inputs.directed-stage == 'readiness')",
        "      always()\n      && (needs.select.result == 'success' || inputs.directed-stage == 'readiness')",
        after="\n  readiness:\n")
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
        'board_item_marker.py" --step AWAITING_MERGE_STEP --pr "$PR_NUMBER")"',
        'board_item_marker.py" --step readiness --pr "$PR_NUMBER")"')
    sub("readiness resumes on an awaiting-merge marker",
        "|| (needs.select.outputs.step == 'readiness' && needs.select.outputs.pr != '')",
        "|| ((needs.select.outputs.step == 'readiness' || needs.select.outputs.step == "
        "'awaiting-merge') && needs.select.outputs.pr != '')",
        after="\n  readiness:\n")
    sub("resume clause 0 (awaiting-merge hold) disabled",
        "elif marker_step == AWAITING_MERGE_STEP and (not pr_from_marker or pr_state == \"OPEN\"):",
        "elif False:")
    # specs/096-durable-prove-entry FR-007/FR-008/FR-009 (research.md D7):
    # a resolved-by-number, MERGED, issue-still-open marker must resolve to
    # prove, not fall through to the sibling triage clause.
    sub("resume merged-fix-awaiting-proof clause reverted to triage "
        "(specs/096-durable-prove-entry)",
        "elif pr_from_marker and marker_step in FIX_OR_LATER_STEPS and pr_state == \"MERGED\":",
        "elif False:")
    # specs/093-not-ready-board-release FR-013: the not-ready record write
    # and the threshold handover are each load-bearing.
    sub("not-ready report drops its record write (--nr-count)",
        '--nr-count "$new_count" ', "")
    # Code review of #1010.
    sub("not-ready dedup ignores the unmet condition (nr_reason)",
        '\n                      and marker.get("nr_reason") == os.environ["UNMET"]', "")
    sub("not-ready handover decision left unguarded",
        "*) echo \"::error::board-loop readiness (not ready): board_eligibility.not_ready_handover_due() gave no answer",
        "XX) echo \"::error::board-loop readiness (not ready): board_eligibility.not_ready_handover_due() gave no answer")
    sub("resume clause 0.5a resumes a merged/closed handover PR",
        'elif handover_marker and pr_from_marker and pr_state == "OPEN":',
        'elif handover_marker and pr_from_marker:')
    sub("review-fixup-publish round advance drops --nr-count",
        '--branch "$BRANCH" --nr-count "$NR_COUNT")"', '--branch "$BRANCH")"',
        after="\n  review-fixup-publish:\n")
    sub("directed readiness nr-count restarts at 0",
        "steps.resolve-directed-pr.outputs.nr-count || 0 }}", "0 }}", after="\n  readiness:\n")
    sub("not-ready comment post left unchecked",
        '--body "$body" \\\n                    || { echo "::error::board-loop readiness (not ready): the not-ready comment could not be posted',
        '--body "$body"\n                    true || { echo "::error::board-loop readiness (not ready): the not-ready comment could not be posted')
    sub("not-ready handover drops its nr_head_sha",
        '--step stalled --pr "$PR_NUMBER" --round "$ROUND" --nr-head-sha "$head_sha" ',
        '--step stalled --round "$ROUND" ')
    # #555: the resume step's branch and PR guards, and the marker readers'
    # author plumbing.
    sub("resume branch-name guard dropped",
        "if branch and not is_loop_branch(branch, issue_number):", "if False:")
    sub("resume PR-ownership guard dropped",
        "foreign_pr = pr_from_marker and not pr_owned", "foreign_pr = False")
    sub("resume open-unowned-PR hold dropped (FR-054)",
        "elif foreign_pr and pr_state == \"OPEN\":", "elif False:")
    sub("select lookup does not mark an open, unowned PR",
        'pr_state="OPEN_UNOWNED"', 'pr_state="OPEN"')
    sub("select lookup does not apply BOARD_PR_OWNED_JQ",
        '"$(jq -r --arg repo "$GITHUB_REPOSITORY" "$BOARD_PR_OWNED_JQ" "$RUNNER_TEMP/board-lookup-pr.json")"',
        '"true"')
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
    # #557: a comments fetch feeding a marker reader swallowed or left
    # bare, and prove-gate without its ownership check.
    sub("select comments fetch swallowed as [] (pre-#557)",
        "              echo \"::error::board-loop: could not fetch the comments of issue #$number -- its "
        "board item marker cannot be read, so no item is selected this run (#557).\"\n"
        "              exit 1\n",
        "              echo '[]' > \"$RUNNER_TEMP/board-comments-$number.json\"\n")
    sub("select comments fetch failure branch without exit 1",
        "selected this run (#557).\"\n              exit 1\n",
        "selected this run (#557).\"\n")
    sub("select 'issue gone' branch widened to every HTTP error",
        "grep -qE 'HTTP (404|410)'", "grep -qE 'HTTP [0-9]+'")
    sub("select 'issue gone' branch fails instead of dropping the issue",
        "dropped from this run's candidates (#557).\"\n", "dropped from this run's candidates (#557).\"\n"
        "                exit 1\n")
    sub("select 'issue gone' branch does not drop the issue from the candidates",
        "'map(select(.number != ($n|tonumber)))'", "'.'")
    sub("resume comments fetch swallowed with || true",
        "> \"$RUNNER_TEMP/board-issue-comments.json\"; then",
        "> \"$RUNNER_TEMP/board-issue-comments.json\" || true; then")
    sub("resume comments fetch left bare (pre-#557)",
        "          if ! gh api \"repos/$GITHUB_REPOSITORY/issues/$ISSUE_NUMBER/comments\" --paginate \\\n"  # wc-pagination-exempt: Gate 97 self-test mutation text, not a real invocation
        "            --jq '.[] | {created_at, body, user: {login: .user.login, type: .user.type}}' | jq -s '.' > "
        "\"$RUNNER_TEMP/board-issue-comments.json\"; then\n",
        "          gh api \"repos/$GITHUB_REPOSITORY/issues/$ISSUE_NUMBER/comments\" --paginate \\\n"  # wc-pagination-exempt: Gate 97 self-test mutation text, not a real invocation
        "            --jq '.[] | {created_at, body, user: {login: .user.login, type: .user.type}}' | jq -s '.' > "
        "\"$RUNNER_TEMP/board-issue-comments.json\"\n          if false; then\n")
    sub("prove-gate comments fetch swallowed with || echo '[]'",
        "> \"$RUNNER_TEMP/board-prove-comments.json\"; then",
        "> \"$RUNNER_TEMP/board-prove-comments.json\" || echo '[]' > \"$RUNNER_TEMP/board-prove-comments.json\"; then")
    sub("prove-gate without the BOARD_PR_OWNED_JQ check (pre-#557)",
        'if [ "$(jq -r --arg repo "$GITHUB_REPOSITORY" "$BOARD_PR_OWNED_JQ" "$RUNNER_TEMP/board-prove-pr.json")" != "true" ]; then',
        'if false; then')
    sub("prove-gate ownership read off the wrong object",
        "jq '.pull_request' \"$GITHUB_EVENT_PATH\"", "jq '.' \"$GITHUB_EVENT_PATH\"")
    # #564: each live lookup restored to its pre-#564 swallow, and each
    # "not found" test widened or broken.
    sub("select PR-state lookup swallowed with || continue (pre-#564)",
        _SELECT_PR_LOOKUP, _SELECT_PR_LOOKUP_PRE_564)
    sub("select PR-state lookup treats every error as 404",
        "grep -qE 'HTTP 404' \"$RUNNER_TEMP/board-lookup-pr.err\"", "true")
    sub("select PR-state lookup fails on a 404",
        "\"$RUNNER_TEMP/board-lookup-pr.err\"; then\n                  continue\n",
        "\"$RUNNER_TEMP/board-lookup-pr.err\"; then\n                  exit 1\n")
    # Pre-#564 had no failure branch either: stderr gone, every error "absent".
    muts.append(("resume marker-PR lookup swallowed to /dev/null (pre-#564)",
                 text.replace(_RESUME_PR_LOOKUP, _RESUME_PR_LOOKUP_PRE_564, 1).replace(
                     "elif ! grep -qE 'HTTP 404' \"$RUNNER_TEMP/board-marker-pr.err\"; then",
                     "elif false; then", 1)))
    sub("resume marker-PR lookup treats every error as 404",
        "elif ! grep -qE 'HTTP 404' \"$RUNNER_TEMP/board-marker-pr.err\"; then", "elif false; then")
    sub("resume board:owned fallback search swallowed (pre-#564)",
        _RESUME_FALLBACK, _RESUME_FALLBACK_PRE_564)
    sub("resume board:owned fallback search failure branch without exit 1",
        "without them (#564).\"\n              exit 1\n", "without them (#564).\"\n")
    sub("resume branch lookup swallowed (pre-#564)", _RESUME_LS_REMOTE, _RESUME_LS_REMOTE_PRE_564)
    sub("resume branch lookup treats every nonzero exit as 'no such ref'",
        'elif [ "$ls_remote_rc" -ne 2 ]; then', "elif false; then")
    sub("resume branch lookup fails on exit 2 (no such ref)",
        'elif [ "$ls_remote_rc" -ne 2 ]; then', 'elif [ "$ls_remote_rc" -ne 0 ]; then')
    sub("select eligibility payload without bot_login",
        ",\n              bot_login: $bot_login}", "}")
    # #530: the breach retry -- its marker, its resume, its consumer, its
    # forced breach and its duplicate check.
    sub("fix posts no step=breach marker before the create",
        '          gh issue comment "$ISSUE_NUMBER" -R "$GITHUB_REPOSITORY" --body "$(printf \'Post-push '
        'backstop breach on %s (measured=%s) -- the PR will not be reviewed;',
        '          : "$(printf \'Post-push backstop breach on %s (measured=%s) -- the PR will not be reviewed;')
    sub("fix step=breach marker written as step=review",
        'board_item_marker.py" --step BREACH_STEP --pr "$PR_NUMBER" --branch "$BRANCH" --base-sha "$BASE_SHA")"',
        'board_item_marker.py" --step review --pr "$PR_NUMBER" --branch "$BRANCH" --base-sha "$BASE_SHA")"')
    sub("resume fallback sends a breach marker to review",
        "              if marker_step == BREACH_STEP:", "              if False:")
    sub("readiness without the step=breach resume branch",
        "        || (needs.select.outputs.step == 'breach' && needs.select.outputs.pr != '')\n", "",
        after="\n  readiness:\n")
    sub("review resumes on a breach marker",
        "|| (needs.select.outputs.step == 'review' && needs.select.outputs.pr != '')",
        "|| ((needs.select.outputs.step == 'review' || needs.select.outputs.step == 'breach') "
        "&& needs.select.outputs.pr != '')", after="\n  review:\n")
    sub("readiness backstop does not force a breach on step=breach",
        "          if breach_retry:\n              holds = False\n", "")
    sub("readiness backstop without RESUME_STEP",
        "          RESUME_STEP: ${{ needs.select.outputs.step }}\n", "", after="\n  readiness:\n")
    sub("breach-retry lookup not gated on breach-retry",
        " && steps.final-diff-backstop.outputs.breach-retry == 'true'", "", after="\n  readiness:\n")
    sub("report-unmet ignores the spec-request already filed",
        'existing_spec_url="$EXISTING_SPEC_URL"', 'existing_spec_url=""')
    # #604 (a): every stall site. Each render loses its label flags, and
    # each loses its fail-loud check; plus the pre-#604 shape (marker, then
    # a bare label add) at route, and triage's handover without stall_args.
    stall_flags = ' --issue "$ISSUE_NUMBER" --add-label "board:stalled")"'
    render_at = [m.start() for m in re.finditer(r"--step stalled[^\n]*" + re.escape(stall_flags), text)]
    # spec 108: route's spec-verdict, fix's post-push-breach and
    # readiness's backstop-breach sites no longer render a stalled marker
    # at all -- they dispose of the originating issue as a duplicate
    # instead (contracts/duplicate-disposition.md) -- so the count drops
    # from 7 to 4 (triage's hand-over, fix's gate-red, review's three
    # stalls). The three workflow-scope holds (route's, fix's pre-push and
    # review-fixup's) render theirs inside board_workflow_scope_hold.py,
    # their one home, which verify-board-route-backstop.py gates.
    # specs/093-not-ready-board-release adds a fifth: readiness's
    # not-ready handover.
    if len(render_at) != 5:
        raise AssertionError("self-test: expected 5 literal stalled renders, found {0}".format(len(render_at)))
    for n, at in enumerate(render_at):
        flags_at = text.index(stall_flags, at)
        muts.append(("stalled render #{0}: no --issue/--add-label".format(n + 1),
                     text[:flags_at] + ')"' + text[flags_at + len(stall_flags):]))
        guard_start = text.index(" \\\n", flags_at)
        guard_end = text.index("\n", text.index("exit 1; }", guard_start)) + 1
        muts.append(("stalled render #{0}: failure not checked".format(n + 1),
                     text[:guard_start] + "\n" + text[guard_end:]))
    # #786: every other render's fail-loud check, one mutation each. The
    # guard is the last continuation line before the render's end, so a
    # multi-line render (select's prove markers) loses only its guard.
    other_at = [m.start() for m in re.finditer(r'board_item_marker\.py"? --step (?!stalled\b)', text)]
    # select's two prove markers, fix's review hand-off and breach, review's
    # readiness and round, readiness's awaiting-merge, triage's hand-over
    # ("$marker_step"), prove's three (close-on-merge, proven, prove), and
    # readiness's not-ready record (specs/093-not-ready-board-release).
    if len(other_at) != 12:
        raise AssertionError("self-test: expected 12 non-stalled marker renders, found {0}".format(len(other_at)))
    for n, at in enumerate(other_at):
        guard_at = text.index('|| { echo "::error::', at)
        guard_start = text.rindex(" \\\n", at, guard_at)
        guard_end = text.index("\n", text.index("exit 1; }", guard_at)) + 1
        muts.append(("marker render #{0} ({1}): failure not checked".format(
                         n + 1, text[at:text.index(" ", text.index("--step", at) + 7)].split("--step ")[-1]),
                     text[:guard_start] + "\n" + text[guard_end:]))
    # spec 108: route's spec-verdict site no longer posts a stalled marker
    # at all (contracts/duplicate-disposition.md) -- the pre-#604
    # marker-then-bare-label-add anti-pattern this mutation guarded is no
    # longer physically expressible there, so it is retired rather than
    # kept as dead fixture text.
    sub("triage handover renders without stall_args",
        '--step "$marker_step" "${stall_args[@]}")"', '--step "$marker_step")"')
    sub("an inline write_marker( stalled marker",
        '          set -uo pipefail\n          # #604: every stall below',
        '          set -uo pipefail\n          python3 -c "from board_item_marker import write_marker; '
        'print(write_marker(\'stalled\', 0, None, None, None))"\n          # #604: every stall below')
    # #604 (b): each durable readiness step without the stop gate, and the
    # gate spelled `!= 'true'` (an empty output would act).
    for step_if in (
            "        if: steps.decide.outputs.ready == 'true' && steps.killswitch-recheck.outputs.paused == 'false'\n",
            "        id: report-unmet\n        if: steps.decide.outputs.ready != 'true' && steps.killswitch-recheck.outputs.paused == 'false'\n",
            "        if: steps.report-unmet.outputs.spec-url != '' && steps.killswitch-recheck.outputs.paused == 'false'\n"):
        sub("readiness step without the stop gate: {0}".format(step_if.strip().splitlines()[-1][:60]),
            step_if, step_if.replace(" && steps.killswitch-recheck.outputs.paused == 'false'", ""))
    sub("readiness report-unmet gated `paused != 'true'`",
        "        id: report-unmet\n        if: steps.decide.outputs.ready != 'true' && steps.killswitch-recheck.outputs.paused == 'false'\n",
        "        id: report-unmet\n        if: steps.decide.outputs.ready != 'true' && steps.killswitch-recheck.outputs.paused != 'true'\n")
    sub("readiness stop re-check tolerated (continue-on-error)",
        "        id: killswitch-recheck\n        uses: ./.wc-pristine-repo/.github/actions/wing-commander-board-stop-check\n",
        "        id: killswitch-recheck\n        continue-on-error: true\n"
        "        uses: ./.wc-pristine-repo/.github/actions/wing-commander-board-stop-check\n",
        after="\n  readiness:\n")
    sub("breach lookup jq ignores the author",
        'select(.user.type == "Bot" and .user.login == $bot)', "select(true)")
    sub("breach lookup jq ignores the PR number",
        '| select((.body // "") | test("(/pull/|PR #)" + $pr + "([^0-9]|$)"))', "")
    sub("breach lookup jq matches the PR number as a prefix",
        '"([^0-9]|$)"', '""')
    sub("breach lookup jq matches the footer as a substring",
        'any((.body // "") | split("\\n")[] | rtrimstr("\\r"); . == $footer)',
        '(.body // "") | contains($footer)')
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
        if ("pre-#525" in label or "breach exclusion" in label or "awaiting-merge marker" in label
                or "step=breach resume branch" in label or "resumes on a breach marker" in label):
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
    # board_eligibility.py mutation (#530): without BREACH_STEP in
    # FIX_OR_LATER_STEPS select never looks up a breach marker's PR and
    # resume cannot resolve step=breach.
    label = "BREACH_STEP dropped from FIX_OR_LATER_STEPS"
    with tempfile.TemporaryDirectory() as tmp:
        scripts = os.path.join(tmp, ".github", "scripts")
        shutil.copytree(os.path.join(ROOT, ".github", "scripts"), scripts,
                        ignore=shutil.ignore_patterns("tests", "fixtures", "__pycache__"))
        module = os.path.join(scripts, "board_eligibility.py")
        with open(module, encoding="utf-8") as fh:
            src = fh.read()
        old = '{"fix", BREACH_STEP, "review",'
        if old not in src:
            failures.append("mutation `{0}`: fixture text not found in board_eligibility.py".format(label))
        else:
            with open(module, "w", encoding="utf-8") as fh:
                fh.write(src.replace(old, '{"fix", "review",', 1))
            doc = yaml.safe_load(text)
            found = select_lookup_findings(doc, tmp) + resume_findings(doc, tmp)
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
    # board_item_marker.py mutations (#604): a CLI that renders a stalled
    # marker without the label add, or after a failed one, must fail
    # stall_label_findings()'s executed cases.
    for label, old, new in (
            ("board_item_marker renders a stalled marker without --add-label",
             "        if step != STALLED_STEP or args.issue is None or args.add_label != STALLED_LABEL:\n",
             "        if False:\n"),
            ("board_item_marker ignores a failed board:stalled add",
             "        if not add_stalled_label(args.issue, args.add_label):\n            sys.exit(1)\n",
             "        add_stalled_label(args.issue, args.add_label)\n"),
            ("board_item_marker lets gh's stdout into the marker",
             "                   stdout=sys.stderr)\n", "                   )\n")):
        with tempfile.TemporaryDirectory() as tmp:
            scripts = os.path.join(tmp, ".github", "scripts")
            shutil.copytree(os.path.join(ROOT, ".github", "scripts"), scripts,
                            ignore=shutil.ignore_patterns("tests", "fixtures", "__pycache__"))
            module = os.path.join(scripts, "board_item_marker.py")
            with open(module, encoding="utf-8") as fh:
                src = fh.read()
            if old not in src:
                failures.append("mutation `{0}`: fixture text not found in board_item_marker.py".format(label))
                continue
            with open(module, "w", encoding="utf-8") as fh:
                fh.write(src.replace(old, new, 1))
            found = stall_label_findings(yaml.safe_load(text), tmp)
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
