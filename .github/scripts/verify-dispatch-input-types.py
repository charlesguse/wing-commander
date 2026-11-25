#!/usr/bin/env python3
"""Gate 174: a dispatch input reaches a typed reusable-workflow input through fromJSON.

WHY THIS EXISTS
---------------
A `workflow_dispatch` input arrives at the reusable-workflow call as a
string, whatever `type:` the dispatch declares. When the called workflow
declares that input `type: number` (or `boolean`), GitHub refuses the call
while composing the run: the run fails at startup with no jobs, the UI says
"This run likely failed because of a workflow file issue", and the only
detail is an annotation on the run page ("evaluate reusable workflow
inputs: ... Unexpected value '1217'"). actionlint passes it and so does
GitHub's own file validation (the workflow stays `active`), so nothing
fails until the first dispatch.

The shared PR reviewer's wrapper shipped that way (spec 127): it passed
`pr: ${{ inputs.pr }}` to shared-pr-reviewer.yml's `pr: type: number`,
and its first dispatch (run 45555932648) never started. The implement and
finalize wrappers already pass `${{ fromJSON(inputs.issue) }}`, which is
the fix: fromJSON turns the string into the number (or boolean) the callee
declared, and leaves a value that is already one unchanged.

THE RULE
--------
For every workflow with a `workflow_dispatch` trigger, every job that calls
a local reusable workflow (`uses: ./.github/workflows/X.yml`) may not pass
an expression that can evaluate to a dispatch input's string to a `number`
or `boolean` input of X. An expression is checked once its fromJSON(...)
calls are removed: if it still names a dispatch input (`inputs.NAME`,
`inputs['NAME']`, the `github.event.inputs.` forms, any letter case), it
fails, so a fallback such as `${{ inputs.NAME || 1 }}` or
`format('{0}', inputs.NAME)` fails like the bare reference does. Quoted
literals are blanked first, so a `<`, `!` or `inputs.` inside one counts
for nothing. `&&` and `||` return one of their operands, so the expression
is split on them (outside parentheses and quotes) and each operand is
checked: an operand with a comparison, a negation or
contains/startsWith/endsWith is already a boolean and is left alone, so
`${{ inputs.NAME != '' && inputs.NAME || 1 }}` still fails on its middle
operand.

One exception: the `inputs` context keeps a dispatch input declared
`type: boolean` a boolean (only `github.event.inputs` turns it into a
string), so `inputs.FLAG` of a boolean dispatch input may reach a boolean
callee input bare; the gate names only the other references.

The fix the gate names is `${{ fromJSON(inputs.NAME) }}`; for an optional
dispatch input with no default it is `fromJSON(inputs.NAME || '<default>')`,
because fromJSON('') fails at startup too.

Usage: python3 .github/scripts/verify-dispatch-input-types.py [--self-test]
"""
import glob
import os
import re
import shutil
import sys
import tempfile

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
TYPED = ("number", "boolean")
WHOLE = re.compile(r"^\$\{\{(.*)\}\}$", re.S)
REF = re.compile(
    r"(?<![A-Za-z0-9_.-])(github\.event\.)?inputs(?:\.([A-Za-z0-9_-]+)|\[\s*'([^']*)'\s*\])", re.I)
BOOLEAN_EXPR = re.compile(r"==|!=|<|>|!|\b(?:contains|startswith|endswith)\s*\(", re.I)
FROMJSON = re.compile(r"\bfromjson\s*\(", re.I)


def _strip_fromjson(expr):
    """Remove every fromJSON(...) call, balanced parentheses and quoted strings respected."""
    out = []
    i = 0
    while True:
        m = FROMJSON.search(expr, i)
        if not m:
            out.append(expr[i:])
            return "".join(out)
        out.append(expr[i:m.start()])
        depth, j, quoted = 1, m.end(), False
        while j < len(expr) and depth:
            c = expr[j]
            if quoted:
                if c == "'":
                    quoted = False
            elif c == "'":
                quoted = True
            elif c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
            j += 1
        out.append(" 0 ")
        i = j


LITERAL = re.compile(r"'(?:[^']|'')*'")
INDEXED = re.compile(r"(?<![A-Za-z0-9_.-])((?:github\.event\.)?inputs)\[\s*'([^']*)'\s*\]", re.I)


def _operands(expr):
    """The operands `expr` can return: split on top-level && and ||, parentheses unwrapped."""
    expr = expr.strip()
    parts, depth, start, i = [], 0, 0, 0
    while i < len(expr):
        c = expr[i]
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
        elif depth == 0 and expr[i:i + 2] in ("&&", "||"):
            parts.append(expr[start:i])
            start = i = i + 2
            continue
        i += 1
    parts.append(expr[start:])
    if len(parts) > 1:
        return [o for p in parts for o in _operands(p)]
    whole = parts[0].strip()
    if whole.startswith("(") and whole.endswith(")"):
        inner = whole[1:-1]
        depth = 0
        for c in inner:
            depth += {"(": 1, ")": -1}.get(c, 0)
            if depth < 0:
                break
        else:
            return _operands(inner)
    return [whole]


def _string_refs(value, kind, dispatch):
    """The dispatch inputs `value` can hand a `kind` callee input as a string."""
    m = WHOLE.match(value)
    if not m:
        return []
    # inputs['NAME'] becomes inputs.NAME before the literals are blanked.
    expr = INDEXED.sub(lambda r: r.group(1) + "." + r.group(2), _strip_fromjson(m.group(1)))
    expr = LITERAL.sub("''", expr)
    names = []
    for operand in _operands(expr):
        if BOOLEAN_EXPR.search(operand):
            continue
        for event, dotted, indexed in REF.findall(operand):
            name = (dotted or indexed).lower()
            if name not in dispatch or name in names:
                continue
            if kind == "boolean" and not event and str(dispatch[name].get("type")) == "boolean":
                continue
            names.append(name)
    return names


def _suggest(name, spec):
    if not spec.get("required") and spec.get("default") in (None, ""):
        return ("${{{{ fromJSON(inputs.{0} || '<default>') }}}} (inputs.{0} is optional with no default, "
                "and fromJSON('') fails at startup too)").format(name)
    return "${{{{ fromJSON(inputs.{0}) }}}}".format(name)


def _on(wf):
    # PyYAML reads the bare key `on` as the boolean True.
    on = wf.get("on", wf.get(True))
    if isinstance(on, str):
        return {on: None}
    if isinstance(on, list):
        return {k: None for k in on}
    return on or {}


def _load(path):
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def problems(root):
    found = []
    wf_dir = os.path.join(root, ".github", "workflows")
    for path in sorted(glob.glob(os.path.join(wf_dir, "*.yml")) + glob.glob(os.path.join(wf_dir, "*.yaml"))):
        wf = _load(path)
        on = _on(wf)
        if "workflow_dispatch" not in on:
            continue
        dispatch_inputs = {str(k).lower(): (v or {}) for k, v in
                           (((on.get("workflow_dispatch") or {}).get("inputs") or {}).items())}
        if not dispatch_inputs:
            continue
        rel = os.path.relpath(path, root)
        for job_name, job in (wf.get("jobs") or {}).items():
            uses = str((job or {}).get("uses") or "")
            if not uses.startswith("./.github/workflows/"):
                continue
            callee_path = os.path.join(root, uses[2:])
            if not os.path.isfile(callee_path):
                found.append("{0}: job {1} calls {2}, which does not exist".format(rel, job_name, uses))
                continue
            callee_inputs = ((_on(_load(callee_path)).get("workflow_call") or {}).get("inputs") or {})
            for key, value in ((job.get("with") or {}).items()):
                kind = str(((callee_inputs.get(key) or {}).get("type")) or "string")
                if kind not in TYPED:
                    continue
                for name in _string_refs(str(value).strip(), kind, dispatch_inputs):
                    found.append(
                        "{0}: job {1} passes dispatch input `{2}` to {3}'s {4} input `{5}` as `{6}`; "
                        "a dispatch input arrives as a string and the run fails at startup -- "
                        "pass {7}".format(
                            rel, job_name, name, os.path.basename(uses), kind, key, str(value).strip(),
                            _suggest(name, dispatch_inputs[name])))
                    break
    return found


# ------------------------------------------------------------------ self-test

def _wrapper(value, dispatch_type="number", extra_on="", required="true"):
    return ("name: w\non:\n{extra}  workflow_dispatch:\n    inputs:\n      pr:\n"
            "        required: {r}\n        type: {t}\npermissions: {{}}\njobs:\n  call:\n"
            "    uses: ./.github/workflows/called.yml\n    with:\n      pr: {v}\n"
            ).format(extra=extra_on, t=dispatch_type, v=value, r=required)


def _called(kind):
    return ("name: c\non:\n  workflow_call:\n    inputs:\n      pr:\n        type: {0}\n"
            "        required: true\njobs:\n  j:\n    runs-on: ubuntu-latest\n"
            "    steps:\n      - run: echo hi\n").format(kind)


CASES = [
    # name, wrapper, called, expect_fail
    ("the 1c94bbb shape: bare inputs.pr to a number input", _wrapper("${{ inputs.pr }}"), _called("number"), True),
    ("bare github.event.inputs.pr to a number input", _wrapper("${{ github.event.inputs.pr }}"), _called("number"), True),
    ("bare inputs.pr of a string dispatch input to a boolean input",
     _wrapper("${{inputs.pr}}", "string"), _called("boolean"), True),
    ("bare github.event.inputs.pr of a boolean dispatch input to a boolean input",
     _wrapper("${{ github.event.inputs.pr }}", "boolean"), _called("boolean"), True),
    ("a fallback still yields the dispatch string", _wrapper("${{ inputs.pr || 1 }}"), _called("number"), True),
    ("format() yields a string", _wrapper("${{ format('{0}', inputs.pr) }}"), _called("number"), True),
    ("index form inputs['pr']", _wrapper("${{ inputs['pr'] }}"), _called("number"), True),
    ("another letter case inputs.PR", _wrapper("${{ inputs.PR }}"), _called("number"), True),
    ("healthy: inputs keeps a boolean dispatch input a boolean",
     _wrapper("${{ inputs.pr }}", "boolean"), _called("boolean"), False),
    ("healthy: fromJSON over a fallback", _wrapper("${{ fromJSON(inputs.pr || '1') }}"), _called("number"), False),
    ("also triggered by workflow_call: the dispatch path still breaks",
     _wrapper("${{ inputs.pr }}", extra_on="  workflow_call: {}\n"), _called("number"), True),
    ("healthy: fromJSON(inputs.pr) to a number input", _wrapper("${{ fromJSON(inputs.pr) }}"), _called("number"), False),
    ("healthy: bare inputs.pr to a string input", _wrapper("${{ inputs.pr }}"), _called("string"), False),
    ("healthy: a comparison is already typed", _wrapper("${{ inputs.pr == 'true' }}", "string"), _called("boolean"), False),
    ("a comparison guard still returns the string operand",
     _wrapper("${{ inputs.pr != '' && inputs.pr || 1 }}"), _called("number"), True),
    ("a negation guard still returns the string operand",
     _wrapper("${{ !inputs.pr && 0 || inputs.pr }}"), _called("number"), True),
    ("a '<' inside a quoted fallback is not a comparison",
     _wrapper("${{ inputs.pr || '<none>' }}"), _called("number"), True),
    ("a '!' inside a format() literal is not a negation",
     _wrapper("${{ format('{0}!', inputs.pr) }}"), _called("number"), True),
    ("healthy: comparisons joined by || are a boolean",
     _wrapper("${{ (inputs.pr == 'a') || (inputs.pr == 'b') }}", "string"), _called("boolean"), False),
]


def self_test():
    failures = []
    for name, wrapper, called, expect_fail in CASES:
        tmp = tempfile.mkdtemp(prefix="gate174-")
        try:
            d = os.path.join(tmp, ".github", "workflows")
            os.makedirs(d)
            with open(os.path.join(d, "wrapper.yml"), "w", encoding="utf-8") as fh:
                fh.write(wrapper)
            with open(os.path.join(d, "called.yml"), "w", encoding="utf-8") as fh:
                fh.write(called)
            got = problems(tmp)
        finally:
            shutil.rmtree(tmp)
        if bool(got) != expect_fail:
            failures.append("{0}: expected {1}, got {2}".format(name, "a failure" if expect_fail else "a pass", got or "a pass"))
        elif expect_fail and "fromJSON(inputs.pr)" not in got[0]:
            failures.append("{0}: the message does not name the fix: {1}".format(name, got[0]))
    # An optional dispatch input with no default: fromJSON('') fails too, so the
    # message names a fallback instead of the bare fromJSON().
    tmp = tempfile.mkdtemp(prefix="gate174-")
    try:
        d = os.path.join(tmp, ".github", "workflows")
        os.makedirs(d)
        with open(os.path.join(d, "wrapper.yml"), "w", encoding="utf-8") as fh:
            fh.write(_wrapper("${{ inputs.pr }}", required="false"))
        with open(os.path.join(d, "called.yml"), "w", encoding="utf-8") as fh:
            fh.write(_called("number"))
        got = problems(tmp)
    finally:
        shutil.rmtree(tmp)
    if len(got) != 1 or "fromJSON(inputs.pr || '<default>')" not in got[0]:
        failures.append("an optional input with no default: the message does not name a fallback: {0}".format(got))
    # A boolean dispatch input read through `inputs` is fine for a boolean
    # callee input, so the message names the string input beside it, not it.
    tmp = tempfile.mkdtemp(prefix="gate174-")
    try:
        d = os.path.join(tmp, ".github", "workflows")
        os.makedirs(d)
        with open(os.path.join(d, "wrapper.yml"), "w", encoding="utf-8") as fh:
            fh.write(_wrapper("${{ inputs.flag && inputs.pr || false }}").replace(
                "    inputs:\n", "    inputs:\n      flag:\n        type: boolean\n", 1))
        with open(os.path.join(d, "called.yml"), "w", encoding="utf-8") as fh:
            fh.write(_called("boolean"))
        got = problems(tmp)
    finally:
        shutil.rmtree(tmp)
    if len(got) != 1 or "dispatch input `pr`" not in got[0]:
        failures.append("a boolean flag beside a string input: the message names the wrong input: {0}".format(got))
    for f in failures:
        print("SELF-TEST FAIL: " + f)
    if failures:
        return 1
    print("Gate 174 self-test: {0} case(s) behave as stated.".format(len(CASES)))
    return 0


def main():
    if "--self-test" in sys.argv[1:]:
        return self_test()
    found = problems(ROOT)
    for p in found:
        print("::error::" + p)
    if found:
        return 1
    print("Gate 174: every dispatch input passed to a typed reusable-workflow input goes through fromJSON.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
