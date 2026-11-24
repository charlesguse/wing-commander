#!/usr/bin/env python3
"""Gate 172 - a newer push to a pull request cancels lint's run for its
older head, and nothing else is ever cancelled.

WHY THIS EXISTS
---------------
lint-workflows.yml's lint job takes 20-30 minutes. With no concurrency:
block, every synchronize push started another full run beside the ones
still going, and PR #1184 once had three in flight at the same moment, two
of them on heads that nothing would read again: board and lifecycle
readiness read the head's own checks, never an older head's. The
workflow-level concurrency: block stops that. Nothing failed when it was
missing, so this gate is what keeps it from going missing again.

THE RULE
--------
The gate evaluates the shipped `concurrency.group` and
`concurrency.cancel-in-progress` for a set of simulated runs, the way
GitHub would, and fails when:

  * there is no workflow-level concurrency: block, or it is the bare
    string form (which never cancels anything);
  * two pull_request runs of the same PR (opened, then synchronize on a
    new head) land in different groups, so the newer push cancels nothing;
  * two different PRs share a group, so a push to one cancels the other;
  * cancel-in-progress is not the boolean true for a pull_request run
    (a quoted 'false' is a non-empty string, truthy, and still wrong);
  * two runs that are not for a pull request (a push to main, the daily
    schedule, a dispatch) share a group with each other or with a PR run.
    Such a run would be cancelled, or would wait behind another, and those
    runs are what prove main is green;
  * a job carries its own concurrency: block, which this gate does not
    model;
  * the expression uses a context or function the shared evaluator
    (wc_gha_expr.py) or this gate's simulated runs do not model. That
    fails loudly rather than guessing: extend them in the same PR.

It checks behaviour, not text: `pr.number || run_id` passes as well as
the shipped `event_name == 'pull_request' && format(...)` form.

Usage:
    python3 .github/scripts/verify-lint-supersedes-pr-runs.py
    python3 .github/scripts/verify-lint-supersedes-pr-runs.py --self-test
"""
import argparse
import os
import sys

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wc_gha_expr  # noqa: E402
from wc_gha_expr import to_str  # noqa: E402

WORKFLOW = os.path.join(".github", "workflows", "lint-workflows.yml")


class ExprError(Exception):
    """An expression this gate cannot evaluate: unmodelled, or unparsable."""


# ---------------------------------------------------------------------------
# Evaluation goes through the shared evaluator, wc_gha_expr (CLAUDE.md,
# "Shared logic has exactly one home"): its &&/|| stop as GitHub's do, a
# NaN is falsy, and a string comparison ignores case. A simulated run is
# flattened into the dotted names it reads. github.event.* is the one
# open prefix, so a payload property the run lacks is null, as on GitHub;
# any other name the run does not carry is unmodelled and fails the gate.
# ---------------------------------------------------------------------------

# The github.* keys a run of this workflow is simulated with. A group that
# reads any other one fails as unmodelled instead of evaluating to null.
GITHUB_KEYS = ("event_name", "event", "ref", "sha", "head_ref", "base_ref",
               "run_id", "run_number", "run_attempt", "workflow",
               "repository")
OPEN_PREFIXES = ("github.event.",)


def _flatten(value, prefix, out):
    out[prefix] = value
    if isinstance(value, dict):
        for k, v in value.items():
            _flatten(v, prefix + "." + k, out)
    return out


def evaluate_expr(expr, ctx):
    flat = _flatten(ctx["github"], "github", {})
    try:
        return wc_gha_expr.evaluate(expr, flat, OPEN_PREFIXES)
    except (ValueError, IndexError) as e:
        raise ExprError(str(e)) from None


def evaluate_value(value, ctx):
    """A YAML value as GitHub sees it: a non-string as itself, a string
    that is exactly one ${{ }} as that expression's value, and any other
    string as text with each ${{ }} interpolated."""
    if not isinstance(value, str):
        return value
    pieces, pos = [], 0
    while True:
        start = value.find("${{", pos)
        if start < 0:
            pieces.append(("text", value[pos:]))
            break
        pieces.append(("text", value[pos:start]))
        j, quoted = start + 3, False
        while j < len(value):
            if value[j] == "'":
                quoted = not quoted
            elif not quoted and value.startswith("}}", j):
                break
            j += 1
        else:
            raise ExprError("unterminated ${{ in {0!r}".format(value))
        pieces.append(("expr", value[start + 3:j]))
        pos = j + 2
    exprs = [p for p in pieces if p[0] == "expr"]
    texts = "".join(p[1] for p in pieces if p[0] == "text")
    if len(exprs) == 1 and texts.strip() == "":
        return evaluate_expr(exprs[0][1], ctx)
    return "".join(p[1] if p[0] == "text" else to_str(evaluate_expr(p[1], ctx))
                   for p in pieces)


# ---------------------------------------------------------------------------
# The simulated runs
# ---------------------------------------------------------------------------

def _github(event_name, run_id, ref, sha, event, head_ref="", base_ref=""):
    return {"github": {
        "event_name": event_name, "event": event, "ref": ref, "sha": sha,
        "head_ref": head_ref, "base_ref": base_ref, "run_id": run_id,
        "run_number": run_id % 10000, "run_attempt": 1,
        "workflow": "lint · workflows", "repository": "owner/repo"}}


def pr_run(number, head_sha, run_id, action="synchronize"):
    event = {"action": action, "number": number, "pull_request": {
        "number": number,
        "head": {"sha": head_sha, "ref": "branch-{0}".format(number)},
        "base": {"sha": "base0", "ref": "main"}}}
    return _github("pull_request", run_id,
                   "refs/pull/{0}/merge".format(number),
                   "merge-" + head_sha, event,
                   head_ref="branch-{0}".format(number), base_ref="main")


def other_run(event_name, run_id, sha):
    event = {"after": sha} if event_name == "push" else {}
    return _github(event_name, run_id, "refs/heads/main", sha, event)


PR_SAME = [("PR #5 opened", pr_run(5, "aaa1", 45300000001, "opened")),
           ("PR #5 pushed", pr_run(5, "bbb2", 45300000002)),
           ("PR #5 pushed again", pr_run(5, "ccc3", 45300000003))]
PR_OTHER = ("PR #6 pushed", pr_run(6, "ddd4", 45300000004))
NON_PR = [("push to main", other_run("push", 45300000011, "e1")),
          ("another push to main", other_run("push", 45300000012, "e2")),
          ("daily schedule", other_run("schedule", 45300000013, "e2")),
          ("next daily schedule", other_run("schedule", 45300000014, "e2")),
          ("dispatch", other_run("workflow_dispatch", 45300000015, "e2"))]


def check(doc):
    """Failures (a list of strings) for a parsed lint-workflows.yml."""
    failures = []
    for name, job in sorted((doc.get("jobs") or {}).items()):
        if isinstance(job, dict) and "concurrency" in job:
            failures.append(
                "job {0!r} has its own concurrency: block; this gate models "
                "only the workflow-level one, so extend it before adding "
                "one".format(name))
    conc = doc.get("concurrency")
    if conc is None:
        failures.append(
            "lint-workflows.yml has no workflow-level concurrency: block, "
            "so a newer push to a pull request no longer cancels the run "
            "for its older head")
        return failures
    if not isinstance(conc, dict) or "group" not in conc:
        failures.append(
            "concurrency: must be a mapping with group: and "
            "cancel-in-progress: true; the bare string form never cancels "
            "a superseded run")
        return failures

    unreadable = object()

    def ev(label, run, key):
        try:
            return evaluate_value(conc.get(key, False), run)
        except ExprError as e:
            failures.append("{0} for {1}: {2}".format(key, label, e))
            return unreadable

    pr_groups = []
    for label, run in PR_SAME + [PR_OTHER]:
        group = ev(label, run, "group")
        cancel = ev(label, run, "cancel-in-progress")
        pr_groups.append((label, to_str(group)))
        if cancel is not unreadable and cancel is not True:
            failures.append(
                "cancel-in-progress is {0!r}, not the boolean true, for {1}, "
                "so a newer push queues behind the older run instead of "
                "cancelling it".format(cancel, label))
    if failures:
        return failures
    same = {g for _, g in pr_groups[:len(PR_SAME)]}
    if len(same) != 1:
        failures.append(
            "runs of the same pull request land in different groups ({0}), "
            "so a newer push cancels nothing".format(
                ", ".join("{0} -> {1!r}".format(l, g)
                          for l, g in pr_groups[:len(PR_SAME)])))
    elif pr_groups[-1][1] in same:
        failures.append(
            "PR #5 and PR #6 share group {0!r}, so a push to one pull "
            "request would cancel the other's run".format(pr_groups[-1][1]))

    seen = {g: l for l, g in pr_groups}
    for label, run in NON_PR:
        group = ev(label, run, "group")
        if group is unreadable:
            continue
        group = to_str(group)
        if group in seen:
            failures.append(
                "the {0} run shares group {1!r} with the {2} run, so one of "
                "them would be cancelled or wait behind the other; a run "
                "that is not for a pull request needs a group of its own"
                .format(label, group, seen[group]))
        else:
            seen[group] = label
    return failures


def run(root="."):
    path = os.path.join(root, WORKFLOW)
    with open(path, encoding="utf-8") as fh:
        doc = yaml.safe_load(fh)
    return check(doc)


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

def self_test():
    results = []

    def case(label, conc, expect, jobs=None):
        doc = {"jobs": jobs or {"lint": {"runs-on": "ubuntu-latest"}}}
        if conc is not None:
            doc["concurrency"] = conc
        failures = check(doc)
        text = "\n".join(failures)
        ok = (not failures) if expect is None else (
            bool(failures) and expect in text)
        results.append(ok)
        print("[{0}] {1}{2}".format("ok" if ok else "FAIL", label,
                                    "" if ok else " -- got: " + repr(text)))

    def expr_case(label, expr, ctx, want):
        try:
            got = evaluate_value(expr, ctx)
        except ExprError as e:
            got = "ExprError: {0}".format(e)
        ok = got == want
        results.append(ok)
        print("[{0}] {1}{2}".format("ok" if ok else "FAIL", label,
                                    "" if ok else " -- got: " + repr(got)))

    # The real file's block is checked by the plain run, not here: these
    # cases exercise the checker, so they carry their own expressions and
    # never a copy of the shipped one.
    event_form = ("lint-${{ github.event_name == 'pull_request' && "
                  "format('pr-{0}', github.event.pull_request.number) || "
                  "format('run-{0}', github.run_id) }}")
    pr5, push = PR_SAME[1][1], NON_PR[0][1]

    expr_case("format() interpolates a PR number as an integer",
              "${{ format('pr-{0}', github.event.pull_request.number) }}",
              pr5, "pr-5")
    expr_case("&& and || return operands: a push run falls through to its "
              "run id",
              "x-${{ github.event.pull_request.number && 'pr' || "
              "format('run-{0}', github.run_id) }}",
              push, "x-run-45300000011")
    expr_case("string comparison ignores case, as on GitHub",
              "${{ 'PULL_REQUEST' == github.event_name }}", pr5, True)
    expr_case("a missing event property is null",
              "${{ github.event.pull_request.number }}", push, None)
    expr_case("format() unescapes doubled braces",
              "${{ format('{{x}}-{0}', 1) }}", pr5, "{x}-1")
    expr_case("|| stops at a truthy left side, as on GitHub: the right "
              "side's bad format() index is never evaluated",
              "${{ true || format('{1}', github.run_id) }}", pr5, True)
    expr_case("&& stops at a falsy left side the same way",
              "${{ github.event.pull_request.number && "
              "format('{1}', github.run_id) }}", push, None)

    case("the event_name && format() || format() form passes",
         {"group": event_form, "cancel-in-progress": True}, None)
    case("an equivalent form passes: the gate reads behaviour, not text",
         {"group": "lint-${{ github.event.pull_request.number || "
                   "github.run_id }}",
          "cancel-in-progress": "${{ github.event_name == 'pull_request' }}"},
         None)
    case("the regression: no concurrency block fails", None,
         "has no workflow-level concurrency")
    case("the bare string form fails: it never cancels",
         "lint-${{ github.event.pull_request.number }}", "bare string form")
    case("cancel-in-progress false fails",
         {"group": event_form, "cancel-in-progress": False},
         "not the boolean true")
    case("a quoted 'false' fails: a non-empty string is not the boolean "
         "true",
         {"group": event_form, "cancel-in-progress": "false"},
         "cancel-in-progress is 'false', not the boolean true")
    case("a group keyed by the head sha fails: a new push cancels nothing",
         {"group": "lint-${{ github.event.pull_request.head.sha || "
                   "github.run_id }}", "cancel-in-progress": True},
         "land in different groups")
    case("a group keyed by run id alone fails the same way",
         {"group": "lint-${{ github.run_id }}", "cancel-in-progress": True},
         "land in different groups")
    case("a constant group fails: PR #5 cancels PR #6",
         {"group": "lint-workflows", "cancel-in-progress": True},
         "PR #5 and PR #6 share group")
    case("a group keyed by github.ref fails: pushes to main cancel each "
         "other",
         {"group": "lint-${{ github.ref }}", "cancel-in-progress": True},
         "shares group 'lint-refs/heads/main'")
    case("a group whose non-PR arm is the event name fails: two "
         "schedules collide",
         {"group": "lint-${{ github.event.pull_request.number || "
                   "github.event_name }}", "cancel-in-progress": True},
         "daily schedule run shares group")
    case("an unmodelled context fails loudly",
         {"group": "lint-${{ vars.LINT_GROUP }}", "cancel-in-progress": True},
         "unmodelled context reference 'vars.LINT_GROUP'")
    case("an unmodelled github key fails loudly",
         {"group": "lint-${{ github.actor }}", "cancel-in-progress": True},
         "unmodelled context reference 'github.actor'")
    case("an unmodelled function fails loudly",
         {"group": "lint-${{ toJSON(github.event) }}",
          "cancel-in-progress": True}, "unsupported function toJSON()")
    case("a job-level concurrency block fails",
         {"group": event_form, "cancel-in-progress": True},
         "has its own concurrency", jobs={"lint": {"concurrency": "x"}})

    passed = sum(results)
    print("verify-lint-supersedes-pr-runs self-test: {0}/{1} passed".format(
        passed, len(results)))
    return passed == len(results)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--root", default=".")
    args = ap.parse_args()
    if args.self_test:
        return 0 if self_test() else 1
    failures = run(args.root)
    for f in failures:
        print("::error::Gate 172: " + f)
    if not failures:
        print("Gate 172: a newer push to a pull request cancels lint's run "
              "for its older head; push, schedule and dispatch runs each "
              "get a group of their own.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
