#!/usr/bin/env python3
"""Gate 173 - the `lint` aggregate job cannot go green by omission.

specs/129-parallel-pr-lint splits the PR-time lint suite into shard jobs plus
`harness-tests`; one aggregate job named `lint` stays the required check.
This gate holds the aggregate's shape (contract items 2-5, 9):

  * exactly one job carries the check-run name `lint`;
  * its `if:` has `always()` (so a failed/cancelled/skipped unit still runs
    it) and admits `pull_request` only;
  * its `needs` lists every other PR-time job and nothing that is missing;
  * its step fails unless each needed result is exactly `success`, reads
    `toJSON(needs)`, and names every non-success unit.

Usage:
    python3 .github/scripts/verify-lint-aggregate.py
    python3 .github/scripts/verify-lint-aggregate.py --self-test
"""
import copy
import os
import re
import sys

import yaml

WORKFLOW = os.path.join(".github", "workflows", "lint-workflows.yml")
AGGREGATE = "lint"


def _runs_on_pr(job):
    cond = str((job or {}).get("if") or "").strip()
    if not cond:
        return True
    return not re.search(r"github\.event_name\s*!=\s*'pull_request'", cond)


def check(doc):
    """Failures (list of strings) for a parsed lint-workflows.yml."""
    jobs = doc.get("jobs") or {}
    named = [k for k, j in jobs.items()
             if ((j or {}).get("name") or k) == AGGREGATE]
    if len(named) != 1 or named[0] != AGGREGATE:
        return ["exactly one job must carry the check-run name 'lint' and "
                "its id must be 'lint'; found {0}".format(named)]
    agg = jobs[AGGREGATE]
    fails = []
    cond = str(agg.get("if") or "")
    if "always()" not in cond:
        fails.append("the aggregate's if: lacks always(), so a failed or "
                     "cancelled unit would skip it and read as green")
    if "github.event_name == 'pull_request'" not in cond:
        fails.append("the aggregate's if: does not restrict to pull_request")
    if "!cancelled()" in cond:
        fails.append("the aggregate's if: uses !cancelled(); a cancelled "
                     "unit would skip it")
    needs = agg.get("needs") or []
    if isinstance(needs, str):
        needs = [needs]
    for n in needs:
        if n not in jobs:
            fails.append("the aggregate needs '{0}', which is not a job".format(n))
    for k, j in jobs.items():
        if k != AGGREGATE and _runs_on_pr(j) and k not in needs:
            fails.append("PR-time job '{0}' is not in the aggregate's "
                         "needs".format(k))
    steps = agg.get("steps") or []
    text = "\n".join(
        str((s or {}).get("run") or "") + str(((s or {}).get("env") or {}))
        for s in steps)
    if "toJSON(needs)" not in text:
        fails.append("the aggregate step does not read toJSON(needs)")
    if not re.search(r'result\s*!=\s*"success"', text):
        fails.append("the aggregate step does not fail on every result other "
                     "than exactly 'success' (skip-tolerant check)")
    if "exit 1" not in text:
        fails.append("the aggregate step never exits non-zero")
    if "to_entries" not in text and ".key" not in text:
        fails.append("the aggregate step does not name the non-success units")
    return fails


def _base():
    shards = {"lint-shard-%d" % i: {"if": "github.event_name == 'pull_request'",
                                    "steps": []} for i in (1, 2)}
    shards["harness-tests"] = {"name": "harness tests",
                               "if": "github.event_name == 'pull_request'",
                               "steps": []}
    shards["names-and-tags"] = {"if": "github.event_name != 'pull_request'",
                                "steps": []}
    shards["lint"] = {
        "if": "${{ always() && github.event_name == 'pull_request' }}",
        "needs": ["lint-shard-1", "lint-shard-2", "harness-tests"],
        "steps": [{
            "env": {"NEEDS": "${{ toJSON(needs) }}"},
            "run": ("bad=\"$(printf '%s' \"$NEEDS\" | jq -r 'to_entries[] | "
                    "select(.value.result != \"success\") | .key')\"\n"
                    "[ -n \"$bad\" ] && exit 1\n")}]}
    return {"jobs": shards}


def self_test():
    cases = []

    def case(label, mutate, expect):
        doc = copy.deepcopy(_base())
        mutate(doc)
        got = check(doc)
        ok = (not got) if expect is None else any(expect in g for g in got)
        cases.append(ok)
        print("{0} {1}".format("ok  " if ok else "FAIL", label))
        if not ok:
            print("     expected {0!r}, got {1}".format(expect, got))

    def j(d):
        return d["jobs"]["lint"]

    case("the real shape passes", lambda d: None, None)
    case("no always() fails",
         lambda d: j(d).update({"if": "github.event_name == 'pull_request'"}),
         "lacks always()")
    case("!cancelled() fails",
         lambda d: j(d).update({"if": "${{ always() && !cancelled() && "
                                      "github.event_name == 'pull_request' }}"}),
         "!cancelled()")
    case("a non-PR aggregate fails",
         lambda d: j(d).update({"if": "${{ always() }}"}),
         "restrict to pull_request")
    case("an aggregate that omits harness-tests fails",
         lambda d: j(d).update({"needs": ["lint-shard-1", "lint-shard-2"]}),
         "'harness-tests' is not in")
    case("an aggregate needing a missing job fails",
         lambda d: j(d)["needs"].append("lint-shard-9"),
         "'lint-shard-9', which is not a job")
    case("a skip-tolerant result check fails",
         lambda d: j(d)["steps"][0].update(
             {"run": "jq 'to_entries[] | select(.value.result == \"failure\")'"
                     " <<<\"$NEEDS\"; exit 1"}),
         "skip-tolerant")
    case("a step that never exits non-zero fails",
         lambda d: j(d)["steps"][0].update(
             {"run": j(d)["steps"][0]["run"].replace("exit 1", "true")}),
         "never exits non-zero")
    case("a step that does not name units fails",
         lambda d: j(d)["steps"][0].update(
             {"run": "printf '%s' \"$NEEDS\" | jq -e 'all(.value.result != "
                     "\"success\")'; exit 1"}) or j(d)["steps"][0]["run"],
         None if False else "name the non-success units")
    case("a shard named lint fails",
         lambda d: d["jobs"]["lint-shard-1"].update({"name": "lint"}),
         "exactly one job")
    case("an unlisted PR-time shard fails",
         lambda d: d["jobs"].update({"lint-shard-3": {
             "if": "github.event_name == 'pull_request'", "steps": []}}),
         "'lint-shard-3' is not in")
    case("a missing aggregate fails",
         lambda d: d["jobs"].pop("lint"),
         "exactly one job")
    bad = cases.count(False)
    print("verify-lint-aggregate self-test: {0}/{1} passed".format(
        len(cases) - bad, len(cases)))
    return 1 if bad else 0


def main(argv):
    if "--self-test" in argv:
        return self_test()
    with open(WORKFLOW, encoding="utf-8") as fh:
        doc = yaml.safe_load(fh) or {}
    fails = check(doc)
    for f in fails:
        print("::error file={0}::Gate 173: {1}".format(WORKFLOW, f))
    if fails:
        return 1
    print("Gate 173: the `lint` aggregate runs always() on pull_request, "
          "needs every PR-time unit and fails unless each is success.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
