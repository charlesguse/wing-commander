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
  * cancel-in-progress is not the YAML boolean true for a pull_request
    run. A quoted 'true' or 'false' is a string, and this gate does not
    guess how GitHub coerces one: write the boolean;
  * two runs that are not for a pull request (a push to main, the daily
    schedule, a dispatch) share a group with each other or with a PR run.
    Such a run would be cancelled, or would wait behind another, and those
    runs are what prove main is green;
  * a group does not start with `lint-workflows-`, or another workflow's
    group does. Concurrency groups are shared by every workflow in the
    repository, so the prefix is what keeps lint's groups its own;
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
WORKFLOWS_DIR = os.path.join(".github", "workflows")
GROUP_PREFIX = "lint-workflows-"


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

OPEN_PREFIXES = ("github.event.",)


def _flatten(value, prefix, out):
    out[prefix] = value
    if isinstance(value, dict):
        for k, v in value.items():
            _flatten(v, prefix + "." + k, out)
    return out


def evaluate_value(value, ctx):
    """A YAML value as GitHub sees it, through wc_gha_expr.evaluate_value."""
    flat = _flatten(ctx["github"], "github", {})
    try:
        return wc_gha_expr.evaluate_value(value, flat, OPEN_PREFIXES)
    except (ValueError, IndexError) as e:
        raise ExprError(str(e)) from None


# ---------------------------------------------------------------------------
# The simulated runs
# ---------------------------------------------------------------------------

# A run carries exactly the github.* keys _github() sets; a group that reads
# any other one fails as unmodelled instead of evaluating to null.
def _github(event_name, run_id, run_number, ref, sha, event, head_ref="",
            base_ref=""):
    return {"github": {
        "event_name": event_name, "event": event, "ref": ref, "sha": sha,
        "head_ref": head_ref, "base_ref": base_ref, "run_id": run_id,
        "run_number": run_number, "run_attempt": 1,
        "workflow": "lint · workflows", "repository": "owner/repo"}}


# Both PRs come from forks with the same branch name, as fork PRs often
# do, so a group keyed by the head branch puts them together.
def pr_run(number, head_sha, run_id, run_number, fork,
           action="synchronize"):
    event = {"action": action, "number": number, "pull_request": {
        "number": number,
        "head": {"sha": head_sha, "ref": "patch-1",
                 "repo": {"full_name": fork + "/repo"}},
        "base": {"sha": "base0", "ref": "main",
                 "repo": {"full_name": "owner/repo"}}}}
    return _github("pull_request", run_id, run_number,
                   "refs/pull/{0}/merge".format(number),
                   "merge-" + head_sha, event,
                   head_ref="patch-1", base_ref="main")


def other_run(event_name, run_id, run_number, sha):
    event = {"after": sha} if event_name == "push" else {}
    return _github(event_name, run_id, run_number, "refs/heads/main", sha,
                   event)


# Run numbers count from 1 for each workflow, in the same range as PR
# numbers, so the non-PR runs are numbered 5 and 6 like the two PRs: a
# group that falls back to github.run_number collides on GitHub.
PR_SAME = [("PR #5 opened", pr_run(5, "aaa1", 45300000001, 1, "fork-a",
                                   "opened")),
           ("PR #5 pushed", pr_run(5, "bbb2", 45300000002, 2, "fork-a")),
           ("PR #5 pushed again", pr_run(5, "ccc3", 45300000003, 3,
                                         "fork-a"))]
PR_OTHER = ("PR #6 pushed", pr_run(6, "ddd4", 45300000004, 4, "fork-b"))
NON_PR = [("push to main", other_run("push", 45300000011, 5, "e1")),
          ("another push to main", other_run("push", 45300000012, 6, "e2")),
          ("daily schedule", other_run("schedule", 45300000013, 7, "e2")),
          ("next daily schedule", other_run("schedule", 45300000014, 8,
                                            "e2")),
          ("dispatch", other_run("workflow_dispatch", 45300000015, 9, "e2"))]


def check(doc, other_groups=()):
    """Failures (a list of strings) for a parsed lint-workflows.yml.
    other_groups is (file, group text) for every other workflow's
    concurrency group, workflow- or job-level."""
    failures = []
    for path, group in other_groups:
        if str(group).startswith(GROUP_PREFIX.rstrip("-")):
            failures.append(
                "{0} has concurrency group {1!r}; the {2!r} prefix is "
                "lint-workflows.yml's own, so that workflow could cancel or "
                "queue a lint run".format(path, group, GROUP_PREFIX))
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
    unread = []

    def ev(label, run, key):
        try:
            return evaluate_value(conc.get(key, False), run)
        except ExprError as e:
            failures.append("{0} for {1}: {2}".format(key, label, e))
            unread.append(label)
            return unreadable

    pr_groups, bad_cancel = [], []
    for label, run in PR_SAME + [PR_OTHER]:
        group = ev(label, run, "group")
        cancel = ev(label, run, "cancel-in-progress")
        pr_groups.append((label, to_str(group)))
        if cancel is not unreadable and cancel is not True:
            bad_cancel.append((label, cancel))
    if bad_cancel:
        failures.append(
            "cancel-in-progress is not the YAML boolean true for {0}, so a "
            "newer push is not sure to cancel the older run".format(
                ", ".join("{0} ({1!r})".format(l, c) for l, c in bad_cancel)))
    # Only an unreadable group stops here; any other failure above still
    # lets the group rules below report, so one CI round shows them all.
    if unread:
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
    unprefixed = sorted(g for g in set(g for _, g in pr_groups) | set(seen)
                        if not g.startswith(GROUP_PREFIX))
    if unprefixed:
        failures.append(
            "group {0} does not start with {1!r}; groups are shared by "
            "every workflow in the repository, so an unprefixed one can "
            "collide with another workflow's".format(
                ", ".join(repr(g) for g in unprefixed[:3])
                + (" and {0} more".format(len(unprefixed) - 3)
                   if len(unprefixed) > 3 else ""), GROUP_PREFIX))
    return failures


def other_workflow_groups(root):
    """(file, group) for every concurrency group in the other workflows."""
    out = []
    wdir = os.path.join(root, WORKFLOWS_DIR)
    for fn in sorted(os.listdir(wdir)):
        path = os.path.join(WORKFLOWS_DIR, fn)
        if not fn.endswith((".yml", ".yaml")) or path == WORKFLOW:
            continue
        with open(os.path.join(root, path), encoding="utf-8") as fh:
            doc = yaml.safe_load(fh)
        if not isinstance(doc, dict):
            continue
        blocks = [doc.get("concurrency")] + [
            j.get("concurrency") for j in (doc.get("jobs") or {}).values()
            if isinstance(j, dict)]
        for c in blocks:
            group = c.get("group") if isinstance(c, dict) else c
            if group is not None:
                out.append((path, group))
    return out


def run(root="."):
    path = os.path.join(root, WORKFLOW)
    with open(path, encoding="utf-8") as fh:
        doc = yaml.safe_load(fh)
    return check(doc, other_workflow_groups(root))


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

def self_test():
    results = []

    def case(label, conc, expect, jobs=None, other_groups=(),
             count=None):
        doc = {"jobs": jobs or {"lint": {"runs-on": "ubuntu-latest"}}}
        if conc is not None:
            doc["concurrency"] = conc
        failures = check(doc, other_groups)
        text = "\n".join(failures)
        expects = [expect] if isinstance(expect, str) else expect
        ok = (not failures) if expect is None else (
            bool(failures) and all(e in text for e in expects))
        if ok and count is not None:
            ok = text.count(count[0]) == count[1]
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
    event_form = ("lint-workflows-${{ github.event_name == 'pull_request' && "
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
    expr_case("a quoted '}}' does not end the expression, as on GitHub",
              "x-${{ format('{0}}}', 'a') }}-y", pr5, "x-a}-y")
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
         {"group": "lint-workflows-${{ github.event.pull_request.number || "
                   "github.run_id }}",
          "cancel-in-progress": "${{ github.event_name == 'pull_request' }}"},
         None)
    case("the regression: no concurrency block fails", None,
         "has no workflow-level concurrency")
    case("the bare string form fails: it never cancels",
         "lint-${{ github.event.pull_request.number }}", "bare string form")
    case("cancel-in-progress false fails",
         {"group": event_form, "cancel-in-progress": False},
         "not the YAML boolean true")
    case("a quoted 'false' fails: a non-empty string is not the boolean "
         "true",
         {"group": event_form, "cancel-in-progress": "false"},
         "PR #5 opened ('false')")
    case("a group keyed by the head sha fails: a new push cancels nothing",
         {"group": "lint-workflows-${{ github.event.pull_request.head.sha || "
                   "github.run_id }}", "cancel-in-progress": True},
         "land in different groups")
    case("a group keyed by run id alone fails the same way",
         {"group": "lint-workflows-${{ github.run_id }}", "cancel-in-progress": True},
         "land in different groups")
    case("a constant group fails: PR #5 cancels PR #6",
         {"group": "lint-workflows-all", "cancel-in-progress": True},
         "PR #5 and PR #6 share group")
    case("a group keyed by github.ref fails: pushes to main cancel each "
         "other",
         {"group": "lint-workflows-${{ github.ref }}", "cancel-in-progress": True},
         "shares group 'lint-workflows-refs/heads/main'")
    case("a group whose non-PR arm is the event name fails: two "
         "schedules collide",
         {"group": "lint-workflows-${{ github.event.pull_request.number || "
                   "github.event_name }}", "cancel-in-progress": True},
         "daily schedule run shares group")
    case("an unmodelled context fails loudly",
         {"group": "lint-workflows-${{ vars.LINT_GROUP }}", "cancel-in-progress": True},
         "unmodelled context reference 'vars.LINT_GROUP'")
    case("an unmodelled github key fails loudly",
         {"group": "lint-workflows-${{ github.actor }}", "cancel-in-progress": True},
         "unmodelled context reference 'github.actor'")
    case("an unmodelled function fails loudly",
         {"group": "lint-workflows-${{ toJSON(github.event) }}",
          "cancel-in-progress": True}, "unsupported function toJSON()")
    case("a job-level concurrency block fails",
         {"group": event_form, "cancel-in-progress": True},
         "has its own concurrency", jobs={"lint": {"concurrency": "x"}})
    case("a job-level block does not hide a broken group: both are "
         "reported in one run",
         {"group": "lint-workflows-${{ github.run_id }}",
          "cancel-in-progress": True},
         ["has its own concurrency", "land in different groups"],
         jobs={"lint": {"concurrency": "x"}})
    case("a wrong cancel-in-progress is reported once, not once per run, "
         "and the group rules still run",
         {"group": "lint-workflows-${{ github.run_id }}",
          "cancel-in-progress": False},
         ["not the YAML boolean true", "land in different groups"],
         count=("cancel-in-progress is not", 1))
    case("a group that falls back to github.run_number fails: push run #5 "
         "shares PR #5's group",
         {"group": "lint-workflows-${{ github.event.pull_request.number "
                   "|| github.run_number }}", "cancel-in-progress": True},
         "push to main run shares group 'lint-workflows-5' with the PR #5")
    case("a group keyed by the head branch fails: two fork PRs from "
         "patch-1 share it",
         {"group": "lint-workflows-${{ github.head_ref || github.run_id }}",
          "cancel-in-progress": True}, "PR #5 and PR #6 share group")
    case("a group keyed by pull_request.head.ref fails the same way",
         {"group": "lint-workflows-${{ github.event.pull_request.head.ref "
                   "|| github.run_id }}", "cancel-in-progress": True},
         "PR #5 and PR #6 share group")
    case("an unprefixed group fails: another workflow's bare-number group "
         "could share it",
         {"group": "${{ github.event.pull_request.number || "
                   "github.run_id }}", "cancel-in-progress": True},
         "does not start with 'lint-workflows-'")
    case("another workflow using the lint-workflows prefix fails",
         {"group": event_form, "cancel-in-progress": True},
         "other.yml has concurrency group 'lint-workflows-x'",
         other_groups=[(".github/workflows/other.yml", "lint-workflows-x")])

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
