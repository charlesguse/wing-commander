#!/usr/bin/env python3
"""Gate — the FR-003 findings paragraph and the filing step travel together.

WHY THIS EXISTS
---------------
specs/056-stage-found-defect-filing wires two independent things into each
of the six published stage workflows: the FR-003 paragraph telling the
agent how to propose a finding, and the `wing-commander-stage-findings`
step that turns a proposal into a filed issue. Nothing else keeps them in
lockstep — an edit that drops one while leaving the other (a prompt
rewrite that trims the paragraph, or a workflow refactor that drops the
step) would silently degrade the mechanism: the agent proposing findings
into a void nothing reads, or the composite running with nothing ever
proposing anything. FR-031 requires both catchable at PR time, on all six
stages regardless of that stage's own `findings-filing-enabled` default
(FR-001a) — the mechanism's *presence* is not conditional on the default.

WHAT IT CHECKS
--------------
For each of the six stage workflows named below: the workflow file exists
and parses; the FR-003 paragraph's stable substring ("do not attempt to
file it yourself") appears somewhere in the file; the
`wing-commander-stage-findings` composite is `uses:`'d by some step in the
file. Exactly one of the two present without the other fails loudly,
naming the stage and which side is missing. A workflow that cannot be
found or parsed also fails loudly (Principle VIII: "loud rather than
vacuous").

The paragraph check is a stable-substring scan across the whole file
rather than a per-step "prompt-composition" parse: `stage-wiring.md`
already documents that plan.yml/tasks.yml/implement.yml each carry the
paragraph in TWO agent steps (auto/pr, or cycle/retry), and intake.yml/
clarify.yml/finalize.yml carry it in one — a per-step requirement would
need six different step-count expectations to stay correct, where the
substring's mere presence in the file already proves the paragraph reached
at least one agent prompt (and stage-wiring.md's own contract is what
governs how many).
"""
import argparse
import os
import shutil
import sys
import tempfile

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_shell_harness import use_utf8_stdout  # noqa: E402

STAGE_WORKFLOWS = (
    ".github/workflows/intake.yml",
    ".github/workflows/clarify.yml",
    ".github/workflows/plan.yml",
    ".github/workflows/tasks.yml",
    ".github/workflows/implement.yml",
    ".github/workflows/finalize.yml",
)

PARAGRAPH_SUBSTRING = "do not attempt to file it yourself"
FILING_STEP_NEEDLE = "wing-commander-stage-findings"

failures = []


def fail(msg):
    failures.append(msg)
    print(f"::error::verify-stage-findings-wiring: {msg}")


def note(msg):
    print(f"note: {msg}")


def _step_lists(doc):
    if not isinstance(doc, dict):
        return []
    out = []
    for job_id, job in (doc.get("jobs") or {}).items():
        out.append((job_id, (job or {}).get("steps") or []))
    return out


def has_filing_step(doc):
    for _job_id, steps in _step_lists(doc):
        for step in steps:
            uses = str((step or {}).get("uses") or "")
            if FILING_STEP_NEEDLE in uses:
                return True
    return False


def check_stage(root, path):
    full = os.path.join(root, *path.split("/"))
    if not os.path.isfile(full):
        fail(f"{path} does not exist — cannot check its findings wiring at all.")
        return
    with open(full, encoding="utf-8") as fh:
        text = fh.read()
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        fail(f"{path} could not be parsed as YAML ({exc}) — cannot check its "
            f"findings wiring.")
        return

    has_paragraph = PARAGRAPH_SUBSTRING in text
    has_step = has_filing_step(doc)

    if has_paragraph and not has_step:
        fail(f"{path} carries the FR-003 findings paragraph in an agent "
            f"prompt, but no step in this workflow calls "
            f"wing-commander-stage-findings — a proposal with nothing to "
            f"read it.")
    elif has_step and not has_paragraph:
        fail(f"{path} calls wing-commander-stage-findings, but no agent "
            f"prompt in this workflow carries the FR-003 findings paragraph "
            f"(the stable substring {PARAGRAPH_SUBSTRING!r}) — a filing step "
            f"with nothing to propose to it.")
    elif has_paragraph and has_step:
        note(f"{path}: paragraph and filing step both present.")
    else:
        fail(f"{path} carries neither the FR-003 findings paragraph nor a "
            f"wing-commander-stage-findings step.")


def evaluate(root="."):
    failures.clear()
    for path in STAGE_WORKFLOWS:
        check_stage(root, path)
    return list(failures)


# --------------------------------------------------------------------------
# --self-test
# --------------------------------------------------------------------------
def _write(root, rel, content):
    path = os.path.join(root, *rel.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(content)


PARAGRAPH_ONLY = (
    "on:\n  workflow_call: {}\njobs:\n  x:\n    runs-on: ubuntu-latest\n    "
    "steps:\n      - uses: anthropics/claude-code-action@v1\n        with:\n"
    "          prompt: |\n            do not attempt to file it yourself\n")
STEP_ONLY = (
    "on:\n  workflow_call: {}\njobs:\n  x:\n    runs-on: ubuntu-latest\n    "
    "steps:\n      - uses: ./.wing-commander-pipeline/.github/actions/"
    "wing-commander-stage-findings\n")
BOTH = (
    "on:\n  workflow_call: {}\njobs:\n  x:\n    runs-on: ubuntu-latest\n    "
    "steps:\n      - uses: anthropics/claude-code-action@v1\n        with:\n"
    "          prompt: |\n            do not attempt to file it yourself\n"
    "      - uses: ./.wing-commander-pipeline/.github/actions/"
    "wing-commander-stage-findings\n")


def _tmp_with_stages(contents_by_index):
    tmp = tempfile.mkdtemp(prefix="wc-stage-findings-wiring-")
    for i, path in enumerate(STAGE_WORKFLOWS):
        _write(tmp, path, contents_by_index.get(i, BOTH))
    return tmp


def selftest_real_six_pass():
    case = "the real six stage workflows pass post-implementation"
    found = evaluate(".")
    if found:
        fail(f"[{case}] real tree failed: {found}")
    else:
        note(f"[{case}] passed")


def selftest_paragraph_without_step_fails():
    case = "paragraph present, step absent fails, naming the stage"
    tmp = _tmp_with_stages({0: PARAGRAPH_ONLY})
    try:
        found = evaluate(tmp)
        hit = [f for f in found if STAGE_WORKFLOWS[0] in f and "nothing to read it" in f]
        if not hit:
            fail(f"[{case}] expected a finding for {STAGE_WORKFLOWS[0]}, got: {found}")
        else:
            note(f"[{case}] passed")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def selftest_step_without_paragraph_fails():
    case = "step present, paragraph absent fails, naming the stage"
    tmp = _tmp_with_stages({1: STEP_ONLY})
    try:
        found = evaluate(tmp)
        hit = [f for f in found if STAGE_WORKFLOWS[1] in f and "nothing to propose to it" in f]
        if not hit:
            fail(f"[{case}] expected a finding for {STAGE_WORKFLOWS[1]}, got: {found}")
        else:
            note(f"[{case}] passed")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def selftest_missing_workflow_fails_loud():
    case = "a missing named stage workflow fails loudly, not vacuously"
    tmp = tempfile.mkdtemp(prefix="wc-stage-findings-wiring-")
    try:
        for i, path in enumerate(STAGE_WORKFLOWS):
            if i == 2:
                continue
            _write(tmp, path, BOTH)
        found = evaluate(tmp)
        hit = [f for f in found if STAGE_WORKFLOWS[2] in f and "does not exist" in f]
        if not hit:
            fail(f"[{case}] expected a finding for missing {STAGE_WORKFLOWS[2]}, got: {found}")
        else:
            note(f"[{case}] passed")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def selftest_clean_fixture_passes():
    case = "all six carrying both sides passes clean"
    tmp = _tmp_with_stages({})
    try:
        found = evaluate(tmp)
        if found:
            fail(f"[{case}] unexpected finding(s): {found}")
        else:
            note(f"[{case}] passed")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def run_selftest():
    use_utf8_stdout()
    selftest_clean_fixture_passes()
    selftest_paragraph_without_step_fails()
    selftest_step_without_paragraph_fails()
    selftest_missing_workflow_fails_loud()
    selftest_real_six_pass()
    print(f"verify-stage-findings-wiring --self-test: {len(failures)} failure(s).")
    return 1 if failures else 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    use_utf8_stdout()

    if args.self_test:
        sys.exit(run_selftest())

    found = evaluate(".")
    print(f"verify-stage-findings-wiring: {len(found)} failure(s).")
    sys.exit(1 if found else 0)


if __name__ == "__main__":
    main()
