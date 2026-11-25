#!/usr/bin/env python3
"""Gate 174: a dispatch input reaches a typed reusable-workflow input through fromJSON.

WHY THIS EXISTS
---------------
A `workflow_dispatch` input arrives at the reusable-workflow call as a
string, whatever `type:` the dispatch declares (one exception: the `inputs`
context keeps a `type: boolean` input a boolean). When the called workflow
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
a local reusable workflow (`uses: ./.github/workflows/X.yml`) may pass a
value that reads a dispatch input (`inputs.NAME`, `inputs['NAME']`, the
`github.event.inputs.` forms, any letter case, anywhere in any `${{ }}` of
the value) to a `number` or `boolean` input of X only in one of these
forms, the whole value and nothing else:

  ${{ fromJSON(inputs.NAME) }}               NAME required, has a default,
                                             or is a boolean dispatch input
  ${{ fromJSON(inputs.NAME || '<json>') }}   '<json>' parses as the callee's
                                             type (fromJSON('') fails too)
  ${{ inputs.NAME }}                         only a boolean dispatch input
                                             into a boolean callee input: the
                                             `inputs` context keeps it a
                                             boolean

The value is matched as YAML hands it over: a `>` or `|` block scalar keeps
a trailing newline, and text or whitespace around the `${{ }}` makes the
value a string (wc_gha_expr.evaluate_value). When the workflow has any
trigger besides workflow_dispatch and workflow_call (schedule, workflow_run,
pull_request, ...), the `inputs` context is empty on those runs, so every
dispatch input may be empty there and only the JSON-fallback form is
accepted.

A boolean dispatch input never fills a number input. Anything else fails
with a message naming the form to use. The rule is an allowlist on purpose:
two review passes of an expression matcher (fallbacks, guards, format(),
literals, comparisons) each found new shapes it misread, and every typed
call in the fleet already uses the first form.

Usage: python3 .github/scripts/verify-dispatch-input-types.py [--self-test]
"""
import glob
import json
import os
import re
import shutil
import sys
import tempfile

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wc_gha_expr  # noqa: E402  -- `${{ }}` splitting has one home

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
TYPED = ("number", "boolean")
REF = re.compile(
    r"(?<![A-Za-z0-9_.-])(?:github\.event\.)?inputs(?:\.([A-Za-z0-9_-]+)|\[\s*'([^']*)'\s*\])", re.I)
LITERAL = re.compile(r"'(?:[^']|'')*'")
NAME = r"inputs\.([A-Za-z0-9_-]+)"
FROMJSON_BARE = re.compile(r"\$\{\{\s*fromjson\(\s*" + NAME + r"\s*\)\s*\}\}", re.I)
FROMJSON_FALLBACK = re.compile(
    r"\$\{\{\s*fromjson\(\s*" + NAME + r"\s*\|\|\s*('(?:[^']|'')*')\s*\)\s*\}\}", re.I)
BARE = re.compile(r"\$\{\{\s*" + NAME + r"\s*\}\}", re.I)


def _dispatch_refs(value, dispatch):
    """The dispatch inputs any expression in `value` reads, quoted literals ignored."""
    names = []
    for kind, body in wc_gha_expr.segments(value):
        if kind != "expr":
            continue
        quoted = [m.span() for m in LITERAL.finditer(body)]
        for ref in REF.finditer(body):
            if any(start <= ref.start() < end for start, end in quoted):
                continue
            name = (ref.group(1) or ref.group(2)).lower()
            if name in dispatch and name not in names:
                names.append(name)
    return names


def _is_boolean(spec):
    return str(spec.get("type")) == "boolean"


def _may_be_empty(spec, other):
    """True when inputs.NAME can be '': an optional non-boolean input with no
    default, or any input of a workflow with another trigger (`other`), whose
    runs leave the `inputs` context empty."""
    if other:
        return True
    return not _is_boolean(spec) and not spec.get("required") and spec.get("default") in (None, "")


def _forms(name, kind, spec, other=None):
    if _may_be_empty(spec, other):
        forms = ["${{{{ fromJSON(inputs.{0} || '<{1}>') }}}}".format(name, kind)]
    else:
        forms = ["${{{{ fromJSON(inputs.{0}) }}}}".format(name)]
    if kind == "boolean" and _is_boolean(spec) and not other:
        forms.append("${{{{ inputs.{0} }}}}".format(name))
    return " or ".join("`{0}`".format(f) for f in forms)


def _of_kind(literal, kind):
    try:
        parsed = json.loads(literal[1:-1].replace("''", "'"))
    except ValueError:
        return False
    if kind == "boolean":
        return isinstance(parsed, bool)
    return isinstance(parsed, (int, float)) and not isinstance(parsed, bool)


def _problem(value, kind, dispatch, other=None):
    """(dispatch input, reason) when `value` breaks the rule for a `kind` callee input, else None.

    `other` names a trigger besides workflow_dispatch/workflow_call, if the workflow has one."""
    try:
        names = _dispatch_refs(value, dispatch)
    except ValueError as exc:
        return "?", "{0} -- close the expression".format(exc)
    if not names:
        return None
    m = FROMJSON_BARE.fullmatch(value) or FROMJSON_FALLBACK.fullmatch(value) or BARE.fullmatch(value)
    if m:
        name = m.group(1).lower()
    else:
        # Name the input the author must change, not a boolean one that would be fine on its own.
        name = next((n for n in names if not (kind == "boolean" and _is_boolean(dispatch[n]))), names[0])
    spec = dispatch[name]
    if kind == "number" and _is_boolean(spec):
        return name, ("a boolean dispatch input stays a boolean, and no form turns it into a number "
                      "-- declare `{0}` type: number or string".format(name))
    if m is None and value != value.strip() and (FROMJSON_BARE.fullmatch(value.strip())
                                                 or FROMJSON_FALLBACK.fullmatch(value.strip())
                                                 or BARE.fullmatch(value.strip())):
        return name, ("whitespace around the expression (a `>` or `|` block scalar keeps a trailing newline) "
                      "makes the value a string -- use `>-` or `|-`, or a plain scalar")
    if m is None:
        return name, ("a dispatch input reaches the call as a string, and only these forms are known to yield a "
                      "{0}".format(kind))
    empty_run = ("a {0} run leaves the `inputs` context empty, and inputs.{1} is '' there".format(other, name)
                 if other else None)
    if m.re is BARE:
        if kind == "boolean" and _is_boolean(spec) and not other:
            return None
        return name, empty_run or "a dispatch input reaches the call as a string"
    if m.re is FROMJSON_FALLBACK:
        if _of_kind(m.group(2), kind):
            return None
        return name, "the fallback {0} is not a JSON {1}, so fromJSON fails on it at startup".format(m.group(2), kind)
    if other:
        return name, empty_run + ", so fromJSON('') fails at startup"
    if _may_be_empty(spec, other):
        return name, "inputs.{0} is optional with no default, and fromJSON('') fails at startup".format(name)
    return None


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
        # Runs of any other trigger leave the `inputs` context empty.
        other = next((str(k) for k in on if k not in ("workflow_dispatch", "workflow_call")), None)
        for job_name, job in (wf.get("jobs") or {}).items():
            uses = str((job or {}).get("uses") or "")
            if not uses.startswith("./.github/workflows/"):
                continue
            callee_path = os.path.join(root, uses[2:])
            if not os.path.isfile(callee_path):
                found.append("{0}: job {1} calls {2}, which does not exist".format(rel, job_name, uses))
                continue
            # Input names match in any letter case, like the dispatch side.
            callee_inputs = {str(k).lower(): (v or {}) for k, v in
                             (((_on(_load(callee_path)).get("workflow_call") or {}).get("inputs") or {}).items())}
            for key, value in ((job.get("with") or {}).items()):
                kind = str(((callee_inputs.get(str(key).lower()) or {}).get("type")) or "string")
                if kind not in TYPED:
                    continue
                # Matched unstripped: whitespace around the expression makes a string.
                value = str(value)
                bad = _problem(value, kind, dispatch_inputs, other)
                if bad:
                    name, reason = bad
                    if "--" not in reason and name in dispatch_inputs:
                        reason += " -- pass " + _forms(name, kind, dispatch_inputs[name], other)
                    found.append("{0}: job {1} passes `{2}` to {3}'s {4} input `{5}`, reading dispatch input "
                                 "`{6}`: {7}".format(rel, job_name, value.strip(), os.path.basename(uses), kind, key,
                                                     name, reason))
    return found


# ------------------------------------------------------------------ self-test

def _wrapper(value, dispatch_type="number", extra_on="", required="true"):
    return ("name: w\non:\n{extra}  workflow_dispatch:\n    inputs:\n      pr:\n"
            "        required: {r}\n        type: {t}\npermissions: {{}}\njobs:\n  call:\n"
            "    uses: ./.github/workflows/called.yml\n    with:\n      pr: {v}\n"
            ).format(extra=extra_on, t=dispatch_type, v=value, r=required)


SCHEDULE = "  schedule:\n    - cron: '0 0 * * *'\n"


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
    ("healthy: fromJSON in another letter case", _wrapper("${{FromJson( INPUTS.PR )}}"), _called("number"), False),
    ("healthy: bare inputs.pr to a string input", _wrapper("${{ inputs.pr }}"), _called("string"), False),
    ("healthy: a value that reads no dispatch input", _wrapper("${{ fromJSON(vars.PR) || 1 }}"), _called("number"), False),
    ("a comparison is not one of the allowed forms", _wrapper("${{ inputs.pr == 'true' }}", "string"), _called("boolean"), True),
    ("a comparison guard still returns the string operand",
     _wrapper("${{ inputs.pr != '' && inputs.pr || 1 }}"), _called("number"), True),
    ("a negation guard still returns the string operand",
     _wrapper("${{ !inputs.pr && 0 || inputs.pr }}"), _called("number"), True),
    ("a '<' inside a quoted fallback is not a comparison",
     _wrapper("${{ inputs.pr || '<none>' }}"), _called("number"), True),
    ("a '!' inside a format() literal is not a negation",
     _wrapper("${{ format('{0}!', inputs.pr) }}"), _called("number"), True),
    ("a comparison among format() arguments does not make it a boolean",
     _wrapper("${{ format('{0}{1}', inputs.pr, inputs.pr == 'y') }}"), _called("number"), True),
    ("a 'fromJSON(' inside a literal does not hide the reference after it",
     _wrapper("${{ format('fromJSON(', inputs.pr) }}"), _called("number"), True),
    ("text outside the expression makes a string", _wrapper("x${{ inputs.pr }}"), _called("number"), True),
    ("a with: key in another letter case still reaches the typed input",
     _wrapper("${{ inputs.pr }}").replace("      pr: $", "      PR: $"), _called("number"), True),
    ("a reference inside a quoted literal is text, not a read",
     _wrapper("${{ fromJSON(vars.PR || 'inputs.pr') }}"), _called("number"), False),
    ("an unterminated expression fails instead of crashing the gate",
     _wrapper("'${{ fromJSON(inputs.pr)'"), _called("number"), True),
    ("a fallback that is not a JSON number", _wrapper("${{ fromJSON(inputs.pr || '<default>') }}"), _called("number"), True),
    ("a scheduled run leaves inputs empty, so fromJSON(inputs.pr) fails there",
     _wrapper("${{ fromJSON(inputs.pr) }}", extra_on=SCHEDULE), _called("number"), True),
    ("a scheduled run leaves a boolean dispatch input empty too",
     _wrapper("${{ inputs.pr }}", "boolean", extra_on=SCHEDULE), _called("boolean"), True),
    ("healthy: a JSON fallback covers the scheduled run",
     _wrapper("${{ fromJSON(inputs.pr || '0') }}", extra_on=SCHEDULE), _called("number"), False),
    ("healthy: workflow_call beside dispatch does not empty the inputs",
     _wrapper("${{ fromJSON(inputs.pr) }}", extra_on="  workflow_call: {}\n"), _called("number"), False),
    ("a `>` block scalar keeps a trailing newline, which makes a string",
     _wrapper(">\n        ${{ fromJSON(inputs.pr) }}"), _called("number"), True),
    ("healthy: a `>-` block scalar over several lines",
     _wrapper(">-\n        ${{\n          fromJSON(inputs.pr)\n        }}"), _called("number"), False),
    ("a guarded fromJSON is not an allowed form",
     _wrapper("${{ inputs.pr && fromJSON(inputs.pr) || 0 }}"), _called("number"), True),
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
        elif expect_fail and "fromJSON(inputs.pr" not in got[0]:
            failures.append("{0}: the message does not name the fix: {1}".format(name, got[0]))
    # Message checks: each names the input to change and the fix that applies to it.
    flag = "    inputs:\n      flag:\n        type: boolean\n"
    message_cases = [
        # An optional dispatch input with no default: fromJSON('') fails too, so
        # the bare fromJSON() fails and the message names a fallback instead.
        ("an optional input with no default, bare", _wrapper("${{ inputs.pr }}", required="false"),
         _called("number"), ["fromJSON(inputs.pr || '<number>')"]),
        ("an optional input with no default, fromJSON", _wrapper("${{ fromJSON(inputs.pr) }}", required="false"),
         _called("number"), ["fromJSON('') fails", "fromJSON(inputs.pr || '<number>')"]),
        # A boolean dispatch input read through `inputs` is fine for a boolean
        # callee input, so the message names the string input beside it.
        ("a boolean flag beside a string input",
         _wrapper("${{ inputs.flag && inputs.pr || false }}").replace("    inputs:\n", flag, 1),
         _called("boolean"), ["dispatch input `pr`", "fromJSON(inputs.pr)"]),
        # fromJSON of a boolean is a boolean, so it is not the fix for a number input.
        ("a boolean dispatch input to a number input", _wrapper("${{ inputs.pr }}", "boolean"),
         _called("number"), ["stays a boolean", "type: number or string"]),
        # Another trigger empties the inputs context, so the message names the trigger and a fallback.
        ("a scheduled run, fromJSON", _wrapper("${{ fromJSON(inputs.pr) }}", extra_on=SCHEDULE),
         _called("number"), ["a schedule run leaves", "fromJSON(inputs.pr || '<number>')"]),
        ("a scheduled run, boolean bare", _wrapper("${{ inputs.pr }}", "boolean", extra_on=SCHEDULE),
         _called("boolean"), ["a schedule run leaves", "fromJSON(inputs.pr || '<boolean>')"]),
        ("a block scalar's trailing newline", _wrapper(">\n        ${{ fromJSON(inputs.pr) }}"),
         _called("number"), ["trailing newline", "`>-`"]),
    ]
    for name, wrapper, called, wanted in message_cases:
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
        if len(got) != 1 or any(w not in got[0] for w in wanted):
            failures.append("{0}: expected one failure naming {1}, got {2}".format(name, wanted, got))
    for f in failures:
        print("SELF-TEST FAIL: " + f)
    if failures:
        return 1
    print("Gate 174 self-test: {0} case(s) and {1} message check(s) behave as stated.".format(
        len(CASES), len(message_cases)))
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
