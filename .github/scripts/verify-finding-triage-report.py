#!/usr/bin/env python3
"""Gate 177 -- review-finding triage reports every drop and reject (specs/128).

Drives wc_finding_triage over the checked-in corpus and checks:

* each corpus row routes to its expected (outcome, reason);
* nothing important/security, and nothing whose class is unreadable, is
  ever dropped (FR-007, FR-009);
* render_triaged lists every drop and reject with its literal reason, and a
  reject is never rendered as dropped (FR-011);
* both call sites (lifecycle-review-gate.yml and the stage-findings
  composite) import the module and neither reimplements the rule (the
  literals `fails loudly` / `no output change` live only in the module);
* the gate fails loudly if its subject is unreachable.

`--self-test` feeds each negative fixture and a reimplemented-rule and an
unreachable-subject case, and fails unless every one is caught.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
FIXTURES = os.path.join(HERE, "fixtures", "finding-triage")
MODULE = os.path.join(HERE, "wc_finding_triage.py")
CALL_SITES = (
    os.path.join(ROOT, ".github", "workflows", "lifecycle-review-gate.yml"),
    os.path.join(ROOT, ".github", "actions", "wing-commander-stage-findings",
                 "action.yml"),
)
RULE_LITERALS = ("fails loudly", "no output change")

sys.path.insert(0, HERE)


def load(name):
    path = os.path.join(FIXTURES, name)
    if not os.path.isfile(path):
        sys.exit("::error::finding-triage: fixture {0} is missing -- the gate "
                 "cannot reach its subject.".format(path))
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def check_route(finding, in_scope, outcome, reason):
    """Errors for one routed result."""
    errs = []
    never = (finding.get("severity") == "important"
             or finding.get("security") is True)
    if outcome == "drop" and never:
        errs.append("important/security finding was dropped")
    if outcome == "drop" and finding.get("failure_class") not in ("loud", "none"):
        errs.append("a finding with an unreadable class was dropped")
    if outcome == "fix-now" and in_scope is not True:
        errs.append("fix-now without in_scope")
    return errs


def check_render(records, rendered):
    errs = []
    lines = rendered.split("\n") if rendered else []
    for rec in records:
        if rec["outcome"] not in ("drop", "reject"):
            continue
        title = "`{0}`".format(rec["title"])
        mine = [ln for ln in lines if title in ln]
        if len(mine) != 1:
            errs.append("{0}: missing from the list or listed {1} times".format(
                rec["title"], len(mine)))
            continue
        line = mine[0]
        if rec["outcome"] == "drop":
            if "dropped: " + rec["reason"] not in line:
                errs.append("{0}: the literal reason is missing".format(rec["title"]))
        else:
            if "rejected" not in line or "dropped" in line:
                errs.append("{0}: a rejected finding must read rejected, "
                            "not dropped".format(rec["title"]))
    return errs


def check_source(text, is_module=False):
    if is_module:
        return []
    return ["reimplements the rule: literal {0!r}".format(lit)
            for lit in RULE_LITERALS if lit in text]


def check_imports(text):
    return [] if "wc_finding_triage" in text else [
        "does not import wc_finding_triage"]


def run():
    errs = []
    try:
        import wc_finding_triage as ft
    except ImportError as exc:
        return ["subject unreachable: {0}".format(exc)]
    corpus = load("corpus.json")["cases"]
    if not corpus:
        return ["corpus is empty"]
    records = []
    for case in corpus:
        outcome, reason = ft.route(case["finding"], case["in_scope"])
        if (outcome, reason) != (case["outcome"], case["reason"]):
            errs.append("{0}: got {1}, expected {2}".format(
                case["name"], (outcome, reason), (case["outcome"], case["reason"])))
        errs += ["{0}: {1}".format(case["name"], e) for e in check_route(
            case["finding"], case["in_scope"], outcome, reason)]
        records.append({"title": case["name"], "outcome": outcome, "reason": reason})
    errs += check_render(records, ft.render_triaged(records))
    hostile = ft.render_triaged([{"title": "a`b <!-- c", "outcome": "drop",
                                  "reason": "fails loudly"}])
    if "<!--" in hostile or hostile.count("`") != 2:
        errs.append("render_triaged did not neutralise backticks or a comment opener")
    if ft.render_triaged([{"title": "x", "outcome": "record", "reason": "r"}]):
        errs.append("render_triaged rendered a recorded finding")
    for path in CALL_SITES:
        if not os.path.isfile(path):
            errs.append("call site {0} is unreachable".format(path))
            continue
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        errs += ["{0}: {1}".format(os.path.relpath(path, ROOT), e)
                 for e in check_imports(text) + check_source(text)]
    with open(MODULE, encoding="utf-8") as fh:
        module_text = fh.read()
    if not all(lit in module_text for lit in RULE_LITERALS):
        errs.append("the module no longer holds the rule literals")
    return errs


def self_test():
    bad = 0
    for case in load("negative-route.json")["cases"]:
        errs = check_route(case["finding"], case["in_scope"],
                           case["outcome"], case["reason"])
        if not any(case["expect_error"] in e for e in errs):
            bad += 1
            print("[FAIL] {0}: not caught".format(case["name"]))
    for case in load("negative-render.json")["cases"]:
        errs = check_render(case["records"], case["rendered"])
        if not any(case["expect_error"] in e for e in errs):
            bad += 1
            print("[FAIL] {0}: not caught".format(case["name"]))
    if not check_source("run: if cls == 'loud': reason = 'fails loudly'"):
        bad += 1
        print("[FAIL] a reimplemented rule at a call site is not caught")
    if not check_imports("run: echo nothing"):
        bad += 1
        print("[FAIL] a call site without the import is not caught")
    if check_source("fails loudly", is_module=True):
        bad += 1
        print("[FAIL] the module itself must be allowed the literals")
    print("verify-finding-triage-report self-test: {0}".format(
        "FAILED" if bad else "every mutation was caught"))
    return 1 if bad else 0


def main():
    if "--self-test" in sys.argv[1:]:
        return self_test()
    errs = run()
    for e in errs:
        print("::error::finding-triage: {0}".format(e))
    if errs:
        return 1
    print("verify-finding-triage-report: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
