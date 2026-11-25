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
a dispatch input to a `number` or `boolean` input of X as a bare reference
(`${{ inputs.NAME }}` or `${{ github.event.inputs.NAME }}`). Wrap it in
fromJSON(). Any other expression (a comparison, a fromJSON of a var) is
left alone: it is either already typed or not a dispatch input.

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
BARE = re.compile(r"^\$\{\{\s*(?:github\.event\.)?inputs\.([A-Za-z0-9_-]+)\s*\}\}$")


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
        dispatch_inputs = set(((on.get("workflow_dispatch") or {}).get("inputs") or {}).keys())
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
                m = BARE.match(str(value).strip())
                if m and m.group(1) in dispatch_inputs:
                    found.append(
                        "{0}: job {1} passes dispatch input `{2}` to {3}'s {4} input `{5}` as `{6}`; "
                        "a dispatch input arrives as a string and the run fails at startup -- "
                        "pass ${{{{ fromJSON(inputs.{2}) }}}}".format(
                            rel, job_name, m.group(1), os.path.basename(uses), kind, key, str(value).strip()))
    return found


# ------------------------------------------------------------------ self-test

def _wrapper(value, dispatch_type="number", extra_on=""):
    return ("name: w\non:\n{extra}  workflow_dispatch:\n    inputs:\n      pr:\n"
            "        required: true\n        type: {t}\npermissions: {{}}\njobs:\n  call:\n"
            "    uses: ./.github/workflows/called.yml\n    with:\n      pr: {v}\n"
            ).format(extra=extra_on, t=dispatch_type, v=value)


def _called(kind):
    return ("name: c\non:\n  workflow_call:\n    inputs:\n      pr:\n        type: {0}\n"
            "        required: true\njobs:\n  j:\n    runs-on: ubuntu-latest\n"
            "    steps:\n      - run: echo hi\n").format(kind)


CASES = [
    # name, wrapper, called, expect_fail
    ("the 1c94bbb shape: bare inputs.pr to a number input", _wrapper("${{ inputs.pr }}"), _called("number"), True),
    ("bare github.event.inputs.pr to a number input", _wrapper("${{ github.event.inputs.pr }}"), _called("number"), True),
    ("bare inputs.pr to a boolean input", _wrapper("${{inputs.pr}}", "boolean"), _called("boolean"), True),
    ("also triggered by workflow_call: the dispatch path still breaks",
     _wrapper("${{ inputs.pr }}", extra_on="  workflow_call: {}\n"), _called("number"), True),
    ("healthy: fromJSON(inputs.pr) to a number input", _wrapper("${{ fromJSON(inputs.pr) }}"), _called("number"), False),
    ("healthy: bare inputs.pr to a string input", _wrapper("${{ inputs.pr }}"), _called("string"), False),
    ("healthy: a comparison is already typed", _wrapper("${{ inputs.pr == 'true' }}", "string"), _called("boolean"), False),
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
