#!/usr/bin/env python3
"""Gate -- every literal board:* label board-loop.yml (or any other
workflow/composite) applies via `gh issue edit --add-label`, `gh pr create
--label`, or a bare `--label` flag is created somewhere under
.github/workflows/ or .github/actions/ by a `gh label create ... --force`
call naming that same literal label, so applying it can never fail for want
of the label existing on a repo that has not created it by hand (#488).

WHY THIS EXISTS
---------------
board-loop.yml applied `--add-label "board:stalled"` at six call sites with
nothing in the workflow ever running `gh label create "board:stalled"`. On
a repo that starts without that label (every adopter, and this repository
before someone created it by hand), every one of those calls failed. The
label never landed on the issue, board_eligibility.py's STALLED_LABEL check
kept finding the issue still eligible, and route re-opened a duplicate
spec-request on every scheduled run -- a silent, repeating side effect with
no failed gate anywhere to catch it (#488's own report).

This gate is the structural scan that catches a THIRD label shipped the
same way: literal, applied, never created. It is deliberately mechanical --
a scan of literal `board:*` strings that appear after `--add-label`,
`--label`, or `gh label create`, not a fixture of board_eligibility.py's own
logic (verify-board-eligibility.py already owns that). A label named only
through a shell variable (`--add-label "$LABEL"`) is invisible to a literal
scan by construction; that is a gap this gate accepts the same way Gate 60's
per-step scope accepts a narrower net for a lower false-positive rate, and
the case this gate exists for -- a hand-typed `--add-label "board:whatever"`
with no matching create anywhere -- is exactly the literal shape it catches.

`--self-test`: a synthetic tempdir tree proves the check passes when every
applied label has a matching create, fails when a create is missing (the
#488 shape), and ignores a label applied only through a variable.
"""
import argparse
import os
import re
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_gate_registry import workflow_files  # noqa: E402
from wc_shell_harness import use_utf8_stdout  # noqa: E402

ACTIONS_DIR = ".github/actions"

# A literal board:<slug> label following --add-label, --label, or a
# `gh label create`. Deliberately anchored to the `board:` prefix -- other
# label families (stage:*, spec:*, ...) each already have their own create
# call sites and are out of scope for this gate.
LABEL_TOKEN = r'"?(board:[A-Za-z0-9_-]+)"?'
ADD_LABEL_RE = re.compile(r'--add-label\s+' + LABEL_TOKEN)
LABEL_FLAG_RE = re.compile(r'--label\s+' + LABEL_TOKEN)
CREATE_LABEL_RE = re.compile(r'gh label create\s+' + LABEL_TOKEN + r'[^\n]*--force')


def action_files(root="."):
    """Every action.yml/action.yaml under .github/actions/**."""
    base = os.path.join(root, ACTIONS_DIR)
    found = []
    for dirpath, _dirs, names in os.walk(base):
        for name in names:
            if name in ("action.yml", "action.yaml"):
                path = os.path.join(dirpath, name)
                rel = os.path.relpath(path, root).replace(os.sep, "/")
                found.append(rel)
    return sorted(found)


def _relativize(root, paths):
    out = []
    for p in paths:
        if os.path.isabs(p):
            p = os.path.relpath(p, root).replace(os.sep, "/")
        out.append(p)
    return out


def all_subject_files(root="."):
    return sorted(_relativize(root, workflow_files(root)) + action_files(root))


def _read(root, path):
    with open(os.path.join(root, path), encoding="utf-8") as fh:
        return fh.read()


def line_of(text, offset):
    return text.count("\n", 0, offset) + 1


def _applied_labels(root):
    """{label: [(path, line), ...]} for every literal board:* label applied
    via --add-label or --label anywhere under workflows/actions."""
    applied = {}
    for path in all_subject_files(root):
        text = _read(root, path)
        for regex in (ADD_LABEL_RE, LABEL_FLAG_RE):
            for m in regex.finditer(text):
                label = m.group(1)
                applied.setdefault(label, []).append((path, line_of(text, m.start())))
    return applied


def _created_labels(root):
    """{label} for every literal board:* label a `gh label create ...
    --force` call names anywhere under workflows/actions."""
    created = set()
    for path in all_subject_files(root):
        text = _read(root, path)
        for m in CREATE_LABEL_RE.finditer(text):
            created.add(m.group(1))
    return created


def evaluate(root="."):
    """Returns (findings, hard_failures). findings is a list of
    (label, [(path, line), ...]) for every applied board:* label with no
    matching create."""
    subjects = workflow_files(root)
    if not subjects:
        return [], ["no .github/workflows/*.yml files discovered -- this "
                     "gate is about to check nothing."]

    applied = _applied_labels(root)
    created = _created_labels(root)

    findings = []
    for label, sites in sorted(applied.items()):
        if label not in created:
            findings.append((label, sites))
    return findings, []


def report(findings, hard_failures):
    for msg in hard_failures:
        print(f"::error::verify-board-label-creation: {msg}")
    for label, sites in findings:
        where = "; ".join(f"{path}:{line}" for path, line in sites)
        print(f"::error::verify-board-label-creation: {label!r} is applied "
              f"at {where} but no `gh label create {label!r} ... --force` "
              f"exists anywhere under .github/workflows/ or "
              f".github/actions/ -- the label may not exist on the target "
              f"repo and the apply will fail there (#488).")


# --------------------------------------------------------------------------
# --self-test
# --------------------------------------------------------------------------
def _write(root, rel, content):
    path = os.path.join(root, *rel.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(content)


failures = []


def fail(msg):
    failures.append(msg)
    print(f"::error::{msg}")


def note(msg):
    print(f"note: {msg}")


def selftest_matched_create_passes():
    case = "every applied board:* label has a matching create"
    tmp = tempfile.mkdtemp(prefix="wc-board-label-")
    try:
        _write(tmp, ".github/workflows/labels-ok.yml",
               "on: push\njobs:\n  x:\n    runs-on: ubuntu-latest\n    steps:\n"
               "      - shell: bash\n        run: |\n"
               "          gh label create \"board:stalled\" --color B60205 "
               "--force\n"
               "          gh label create \"board:owned\" --color 0E8A16 "
               "--force\n"
               "          gh issue edit \"$N\" --add-label \"board:stalled\"\n"
               "          gh pr create --title t --label board:owned\n")
        findings, hard = evaluate(tmp)
        if hard:
            fail(f"[{case}] unexpected hard failure(s): {hard}")
        elif findings:
            fail(f"[{case}] unexpected finding(s): {findings}")
        else:
            note(f"[{case}] passed")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def selftest_missing_create_fails():
    case = "an applied board:* label with no create fails (the #488 shape)"
    tmp = tempfile.mkdtemp(prefix="wc-board-label-")
    try:
        _write(tmp, ".github/workflows/labels-missing-create.yml",
               "on: push\njobs:\n  x:\n    runs-on: ubuntu-latest\n    steps:\n"
               "      - shell: bash\n        run: |\n"
               "          gh issue edit \"$N\" -R \"$GITHUB_REPOSITORY\" "
               "--add-label \"board:stalled\"\n")
        findings, hard = evaluate(tmp)
        if hard:
            fail(f"[{case}] unexpected hard failure(s): {hard}")
            return
        hit = [f for f in findings if f[0] == "board:stalled"]
        if not hit:
            fail(f"[{case}] expected a finding for board:stalled, got: {findings}")
        else:
            note(f"[{case}] passed ({hit[0][1]})")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def selftest_create_in_a_different_file_passes():
    case = "a create in one file covers an apply in another"
    tmp = tempfile.mkdtemp(prefix="wc-board-label-")
    try:
        _write(tmp, ".github/actions/wing-commander-board-labels/action.yml",
               "runs:\n  using: composite\n  steps:\n"
               "    - shell: bash\n      run: |\n"
               "        gh label create \"board:stalled\" --color B60205 "
               "--force\n")
        _write(tmp, ".github/workflows/labels-cross-file.yml",
               "on: push\njobs:\n  x:\n    runs-on: ubuntu-latest\n    steps:\n"
               "      - shell: bash\n        run: |\n"
               "          gh issue edit \"$N\" --add-label \"board:stalled\"\n")
        findings, hard = evaluate(tmp)
        if hard:
            fail(f"[{case}] unexpected hard failure(s): {hard}")
        elif findings:
            fail(f"[{case}] unexpected finding(s): {findings}")
        else:
            note(f"[{case}] passed")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def selftest_variable_label_is_ignored():
    case = "a label applied only through a shell variable is out of scope"
    tmp = tempfile.mkdtemp(prefix="wc-board-label-")
    try:
        _write(tmp, ".github/workflows/labels-variable.yml",
               "on: push\njobs:\n  x:\n    runs-on: ubuntu-latest\n    steps:\n"
               "      - shell: bash\n        run: |\n"
               "          gh issue edit \"$N\" --add-label \"$LABEL\"\n")
        findings, hard = evaluate(tmp)
        if hard:
            fail(f"[{case}] unexpected hard failure(s): {hard}")
        elif findings:
            fail(f"[{case}] a variable-named label should not be flagged: {findings}")
        else:
            note(f"[{case}] passed")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def run_selftest():
    use_utf8_stdout()
    selftest_matched_create_passes()
    selftest_missing_create_fails()
    selftest_create_in_a_different_file_passes()
    selftest_variable_label_is_ignored()
    print(f"verify-board-label-creation --self-test: {len(failures)} failure(s).")
    return 1 if failures else 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    use_utf8_stdout()

    if args.self_test:
        sys.exit(run_selftest())

    findings, hard_failures = evaluate(".")
    report(findings, hard_failures)

    total = len(findings) + len(hard_failures)
    print(f"verify-board-label-creation: {total} failure(s).")
    sys.exit(1 if total else 0)


if __name__ == "__main__":
    main()
