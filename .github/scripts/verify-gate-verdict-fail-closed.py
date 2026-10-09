#!/usr/bin/env python3
"""Gate verdict reads fail closed (spec 095 FR-002/FR-003/FR-004).

Drives every branch of wc_gate_verdict.read_verdict through the checked-in
fixtures in .github/scripts/fixtures/095-gate-verdict/ (expectations.json
lists each case and the outcome and reason it must produce), and checks the
publisher `if:` rule: a condition that gates on a gate-suite job's result
must demand an explicit pass (`== 'pass'` / `== 'success'`); a negated
test (`!= 'failure'`) treats a skipped or cancelled gate job as green.

The same rule is applied to every `if:` in the workflows that names a
`needs.gate-suite*.result`, so a publisher added later is held to it.

Usage:
    python3 .github/scripts/verify-gate-verdict-fail-closed.py
    python3 .github/scripts/verify-gate-verdict-fail-closed.py --self-test
"""
import json
import os
import re
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import wc_gate_verdict  # noqa: E402

FIXTURES = os.path.join(HERE, "fixtures", "095-gate-verdict")
WORKFLOWS = os.path.join(HERE, "..", "workflows")
GATE_RESULT_RE = re.compile(r"needs\.gate-suite[\w-]*\.result")
EXPLICIT_RE = re.compile(r"(outcome|result)\s*==\s*'(pass|success)'")
IF_LINE_RE = re.compile(r"^\s*(?:-\s+)?if:\s*(.+?)\s*$")


def publisher_if_ok(expr):
    """True when a condition naming a gate-suite result demands an explicit
    pass; conditions that do not name one are not this rule's concern."""
    if not GATE_RESULT_RE.search(expr):
        return True
    return bool(EXPLICIT_RE.search(expr))


def check_reader_cases(fixture_dir):
    errors = []
    with open(os.path.join(fixture_dir, "expectations.json"),
              encoding="utf-8") as fh:
        spec = json.load(fh)
    for case in spec["reader_cases"]:
        got = wc_gate_verdict.read_verdict(
            os.path.join(fixture_dir, case["file"]),
            spec["expected_head_sha"], spec["trusted_sha"])
        if got[0] != case["outcome"] or case["reason"] not in got[1]:
            errors.append("reader case {0}: got {1!r}, want outcome {2} / "
                          "reason containing {3!r}".format(
                              case["name"], got[:2], case["outcome"],
                              case["reason"]))
    for case in spec["publisher_if_cases"]:
        with open(os.path.join(fixture_dir, case["file"]),
                  encoding="utf-8") as fh:
            ok = publisher_if_ok(fh.read().strip())
        if ok != case["ok"]:
            errors.append("publisher if case {0}: rule said {1}, want {2}"
                          .format(case["name"], ok, case["ok"]))
    return errors


def check_workflows(workflow_dir):
    errors = []
    if not os.path.isdir(workflow_dir):
        return ["workflow directory not found: " + workflow_dir]
    for name in sorted(os.listdir(workflow_dir)):
        if not name.endswith(".yml"):
            continue
        with open(os.path.join(workflow_dir, name), encoding="utf-8") as fh:
            for lineno, line in enumerate(fh, 1):
                match = IF_LINE_RE.match(line)
                if match and not publisher_if_ok(match.group(1)):
                    errors.append("{0}:{1}: publisher `if:` treats a skipped "
                                  "or cancelled gate-suite job as green"
                                  .format(name, lineno))
    return errors


def run():
    errors = check_reader_cases(FIXTURES) + check_workflows(WORKFLOWS)
    for err in errors:
        print("::error::" + err)
    if not errors:
        print("verify-gate-verdict-fail-closed: ok")
    return 1 if errors else 0


def self_test():
    failures = []
    if publisher_if_ok("needs.gate-suite-fix.result != 'failure'"):
        failures.append("negated gate result accepted")
    if not publisher_if_ok("needs.gate-suite-fix.result == 'success'"):
        failures.append("explicit success rejected")
    if not publisher_if_ok("github.event_name == 'push'"):
        failures.append("unrelated condition rejected")
    with tempfile.TemporaryDirectory() as tmp:
        with open(os.path.join(tmp, "w.yml"), "w", encoding="utf-8") as fh:
            fh.write("    if: needs.gate-suite-x.result != 'failure'\n")
        if not check_workflows(tmp):
            failures.append("workflow with skipped-as-green if passed")
        with open(os.path.join(tmp, "w.yml"), "w", encoding="utf-8") as fh:
            fh.write("    if: needs.gate-suite-x.result == 'success'\n")
        if check_workflows(tmp):
            failures.append("workflow with explicit-pass if failed")
    # A broken reader must be caught: a fixture expecting pass from a fail.
    with tempfile.TemporaryDirectory() as tmp:
        for entry in os.listdir(FIXTURES):
            with open(os.path.join(FIXTURES, entry), "rb") as src, \
                    open(os.path.join(tmp, entry), "wb") as dst:
                dst.write(src.read())
        with open(os.path.join(tmp, "expectations.json"),
                  encoding="utf-8") as fh:
            spec = json.load(fh)
        spec["reader_cases"][0]["outcome"] = "pass"
        with open(os.path.join(tmp, "expectations.json"), "w",
                  encoding="utf-8") as fh:
            json.dump(spec, fh)
        if not check_reader_cases(tmp):
            failures.append("wrong expectation not detected")
    for failure in failures:
        print("SELF-TEST FAIL: " + failure, file=sys.stderr)
    if failures:
        return 1
    print("verify-gate-verdict-fail-closed self-test: ok")
    return 0


if __name__ == "__main__":
    sys.exit(self_test() if "--self-test" in sys.argv else run())
