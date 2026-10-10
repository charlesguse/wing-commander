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
# Every gate-suite result reference must itself be compared to 'success'.
GATE_EXPLICIT_RE = re.compile(
    r"needs\.gate-suite[\w-]*\.result\s*==\s*'success'")
IF_LINE_RE = re.compile(r"^(\s*)(?:-\s+)?if:\s*(.*?)\s*$")


def publisher_if_ok(expr):
    """True when every gate-suite result a condition names is demanded to be
    exactly 'success'; conditions that do not name one are not this rule's
    concern. A reference with any other comparison (or none) is red."""
    refs = len(GATE_RESULT_RE.findall(expr))
    if not refs:
        return True
    return len(GATE_EXPLICIT_RE.findall(expr)) == refs and "!=" not in expr \
        and not re.search(r"!\s*\(", expr)


def if_expressions(text):
    """Yield (lineno, expression) for every `if:` value, joining `>-`/`|`
    block scalars and plain multi-line continuations."""
    lines = text.splitlines()
    for idx, line in enumerate(lines):
        match = IF_LINE_RE.match(line)
        if not match:
            continue
        indent = len(match.group(1)) + (2 if line.lstrip().startswith("-") else 0)
        expr = match.group(2)
        if expr in (">", ">-", ">+", "|", "|-", "|+") or not expr:
            expr = ""
        parts = [expr]
        for nxt in lines[idx + 1:]:
            if nxt.strip() and len(nxt) - len(nxt.lstrip()) <= indent:
                break
            parts.append(nxt.strip())
        yield idx + 1, " ".join(p for p in parts if p)


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
            for lineno, expr in if_expressions(fh.read()):
                if not publisher_if_ok(expr):
                    errors.append("{0}:{1}: publisher `if:` treats a skipped "
                                  "or cancelled gate-suite job as green"
                                  .format(name, lineno))
    return errors


COMPOSITE = os.path.join(HERE, "..", "actions", "wing-commander-gate-verdict", "action.yml")


def check_composite_read(composite=COMPOSITE):
    """The reader's front door, executed: a gate job replaced while pending
    (gate-job-result=cancelled) reads outcome=cancelled -- never pass, and
    never a red suite -- while a missing artifact with no such result still
    reads fail (code review of #990)."""
    from wc_shell_harness import find_step, resolve_bash, run_step
    errors = []
    script = find_step(composite, "Read gate verdict (fail-closed)")["run"]
    with tempfile.TemporaryDirectory() as tmp:
        base = {"SITE": "board-fix", "EXPECTED_HEAD_SHA": "a" * 40,
                "VERDICT_FILE": os.path.join(tmp, "absent.json"),
                "GITHUB_ACTION_PATH": os.path.dirname(os.path.abspath(composite)),
                "GITHUB_SHA": "b" * 40}
        for result, want in (("cancelled", "cancelled"), ("", "fail"), ("failure", "fail")):
            rc, out, outputs, _ = run_step(resolve_bash(), script, tmp,
                                           dict(base, GATE_JOB_RESULT=result), tmp)
            if rc != 0 or outputs.get("outcome") != want:
                errors.append("composite read with gate-job-result={0!r}: outcome {1!r}, want "
                              "{2!r}\n{3}".format(result, outputs.get("outcome"), want, out[-300:]))
    return errors


def run():
    errors = (check_reader_cases(FIXTURES) + check_workflows(WORKFLOWS)
              + check_composite_read())
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
    if publisher_if_ok("needs.gate-suite-x.result == 'success' || "
                       "needs.gate-suite-y.result != 'failure'"):
        failures.append("second unguarded gate reference accepted")
    multi = list(if_expressions(
        "    if: >-\n      !cancelled() &&\n      needs.gate-suite-x.result != 'failure'\n"
        "    steps: []\n"))
    if not multi or publisher_if_ok(multi[0][1]):
        failures.append("multi-line skipped-as-green if accepted")
    with tempfile.TemporaryDirectory() as tmp:
        with open(os.path.join(tmp, "w.yml"), "w", encoding="utf-8") as fh:
            fh.write("    if: needs.gate-suite-x.result != 'failure'\n")
        if not check_workflows(tmp):
            failures.append("workflow with skipped-as-green if passed")
        with open(os.path.join(tmp, "w.yml"), "w", encoding="utf-8") as fh:
            fh.write("    if: needs.gate-suite-x.result == 'success'\n")
        if check_workflows(tmp):
            failures.append("workflow with explicit-pass if failed")
    with tempfile.TemporaryDirectory() as tmp:
        mutated_dir = os.path.join(tmp, "wing-commander-gate-verdict")
        os.makedirs(mutated_dir)
        text = open(COMPOSITE, encoding="utf-8").read()
        old = 'if [ "$GATE_JOB_RESULT" = "cancelled" ]; then'
        if old not in text:
            failures.append("composite read step changed: update the mutation")
        with open(os.path.join(mutated_dir, "action.yml"), "w", encoding="utf-8") as fh:
            fh.write(text.replace(old, "if false; then"))
        mutated = check_composite_read(os.path.join(mutated_dir, "action.yml"))
        if not any("cancelled" in e for e in mutated):
            failures.append("a read step that ignores a cancelled gate job was not caught")
    if check_composite_read():
        failures.append("the shipped composite read already fails: {0}".format(
            check_composite_read()))
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
