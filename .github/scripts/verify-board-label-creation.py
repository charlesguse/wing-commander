#!/usr/bin/env python3
"""Gate -- every literal board:* label a job applies (via `gh issue edit
--add-label`, `gh pr create --label`/`-l`, or a REST `-f "labels[]=..."`
call) is created by that SAME job's own `gh label create ... --force` call,
or a `wing-commander-board-labels` composite call, at an EARLIER step than
the first apply -- never merely "created somewhere in the repository."

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

A file-wide "does a create exist ANYWHERE in the repo" check does not catch
the actual failure mode: board-loop.yml's own jobs run as separate runners
that can each be entered directly (the resume path re-enters at fix,
review or readiness without triage/route ever running in that job graph),
so a create in one job's steps says nothing about whether the JOB that
applies the label ran its own create first. A first version of this gate
checked file-wide co-occurrence and stayed green with the label-creating
step deleted from a single job -- code review of #488 caught it. This
version walks each job's (or composite action's) own step list in order
and requires the create -- inline, or via the wing-commander-board-labels
composite -- to appear in an earlier step of THAT SAME job than the first
apply. There is no cross-job or cross-file fallback: nothing in this repo
today needs one, and adding one back would reopen exactly the gap review
found.

`--self-test`: a synthetic tempdir tree proves the per-job ordering (same
job passes, a different job in the same or another file does not cover
it, the composite call counts as creating both labels, a job missing the
step fails while a sibling job with it passes), each of the extended apply
forms is detected (`--add-label=`, a comma-separated label list, `-l`/
`--label=` on `gh pr create`, and a REST `-f "labels[]=..."` call), a
`gh label create` that appears only in a comment line does not count, and
a label named only through a shell variable stays out of scope.
"""
import argparse
import os
import re
import shutil
import sys
import tempfile
from collections import namedtuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_gate_registry import workflow_files  # noqa: E402
from wc_shell_harness import use_utf8_stdout  # noqa: E402

import yaml  # noqa: E402

ACTIONS_DIR = ".github/actions"

# The one composite this gate knows creates both board:stalled and
# board:owned (wing-commander-board-labels/action.yml). A step that `uses:`
# it counts, for every later step in the same job, as having created both
# labels -- never for an earlier step, and never for a different job.
BOARD_LABELS_COMPOSITE_USES = "./.github/actions/wing-commander-board-labels"
BOARD_LABELS_COMPOSITE_CREATES = ("board:stalled", "board:owned")

BOARD_LABEL_TOKEN_RE = re.compile(r'^board:[A-Za-z0-9_-]+$')

# --add-label / --label, space or "=" form, quoted or bare value.
_VALUE = r'("[^"\n]*"|\'[^\'\n]*\'|\S+)'
ADD_LABEL_VALUE_RE = re.compile(r'--add-label(?:=|\s+)' + _VALUE)
LABEL_FLAG_VALUE_RE = re.compile(r'--label(?:=|\s+)' + _VALUE)
# `-l` short form: only recognized on a `gh pr create` line, so an
# unrelated `-l` flag elsewhere (ls -l, wc -l, ...) is never mistaken for
# it.
SHORT_LABEL_VALUE_RE = re.compile(r'-l(?:=|\s+)' + _VALUE)
# wc-gh-method-exempt: documentation, not an invocation -- REST array form
# (-f "labels[]=board:x") on a gh api call this gate's own apply-detection
# matches; it does not call gh api itself.
REST_LABEL_VALUE_RE = re.compile(
    r'-f\s+("labels\[\]=[^"\n]*"|\'labels\[\]=[^\'\n]*\'|labels\[\]=\S+)')

# `gh label create <token> ... --force` on one line (every real call site in
# this repo is single-line; see the fleet-wide grep in #488's own review).
CREATE_LABEL_RE = re.compile(r'gh label create\s+' + _VALUE)

Finding = namedtuple("Finding", ["path", "job", "label", "line"])


# --------------------------------------------------------------------------
# Discovery
# --------------------------------------------------------------------------
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


def _load_yaml(root, path):
    try:
        return yaml.safe_load(_read(root, path)) or {}
    except (yaml.YAMLError, OSError):
        return None


def line_of(text, offset):
    return text.count("\n", 0, offset) + 1


def _step_lists(doc):
    """Every (job_id_or_'runs', [steps]) in a workflow or composite action
    doc -- same shape Gate 60's own token-mint check uses."""
    if not isinstance(doc, dict):
        return []
    out = []
    for job_id, job in (doc.get("jobs") or {}).items():
        out.append((job_id, (job or {}).get("steps") or []))
    runs = doc.get("runs") or {}
    if runs.get("steps"):
        out.append(("runs", runs["steps"]))
    return out


# --------------------------------------------------------------------------
# Per-line extraction
# --------------------------------------------------------------------------
def _is_comment_line(line):
    return line.strip().startswith("#")


def _unquote(raw):
    raw = raw.strip()
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'":
        raw = raw[1:-1]
    return raw


def _board_labels_in_value(raw):
    """A flag's value may be a single label or a comma-separated list
    (`--add-label "spec-request,board:x"`) -- a board:* label in any
    position is in scope."""
    raw = _unquote(raw)
    labels = []
    for token in raw.split(","):
        token = _unquote(token.strip())
        if BOARD_LABEL_TOKEN_RE.match(token):
            labels.append(token)
    return labels


def _extract_applies(line):
    """Every literal board:* label this line applies, across every
    supported flag form. Skips comment lines entirely."""
    if _is_comment_line(line):
        return []
    labels = []
    for m in ADD_LABEL_VALUE_RE.finditer(line):
        labels.extend(_board_labels_in_value(m.group(1)))
    for m in LABEL_FLAG_VALUE_RE.finditer(line):
        labels.extend(_board_labels_in_value(m.group(1)))
    if "gh pr create" in line:
        for m in SHORT_LABEL_VALUE_RE.finditer(line):
            labels.extend(_board_labels_in_value(m.group(1)))
    for m in REST_LABEL_VALUE_RE.finditer(line):
        raw = _unquote(m.group(1))
        if raw.startswith("labels[]="):
            labels.extend(_board_labels_in_value(raw[len("labels[]="):]))
    return labels


def _extract_creates(line):
    """Every literal board:* label this line creates with `--force`. Skips
    comment lines entirely -- a `# gh label create "board:stalled" --force`
    left as documentation must never satisfy this gate."""
    if _is_comment_line(line):
        return []
    if "--force" not in line:
        return []
    labels = []
    for m in CREATE_LABEL_RE.finditer(line):
        labels.extend(_board_labels_in_value(m.group(1)))
    return labels


# --------------------------------------------------------------------------
# The per-job scan
# --------------------------------------------------------------------------
def _step_first_line(text, run):
    lines = run.splitlines()
    if not lines:
        return 0
    return text.find(lines[0])


def check_job_scope(root="."):
    findings = []
    for path in all_subject_files(root):
        doc = _load_yaml(root, path)
        if doc is None:
            continue
        text = _read(root, path)
        for job, steps in _step_lists(doc):
            created = set()
            for step in steps:
                step = step or {}
                uses = str(step.get("uses") or "").strip()
                if uses == BOARD_LABELS_COMPOSITE_USES:
                    created.update(BOARD_LABELS_COMPOSITE_CREATES)
                    continue
                run = str(step.get("run") or "")
                if not run:
                    continue
                for line in run.split("\n"):
                    for label in _extract_creates(line):
                        created.add(label)
                    for label in _extract_applies(line):
                        if label not in created:
                            offset = _step_first_line(text, run)
                            findings.append(Finding(
                                path, job, label, line_of(text, max(offset, 0))))
    return findings


def evaluate(root="."):
    """Returns (findings, hard_failures)."""
    subjects = workflow_files(root)
    if not subjects:
        return [], ["no .github/workflows/*.yml files discovered -- this "
                     "gate is about to check nothing."]
    return check_job_scope(root), []


def report(findings, hard_failures):
    for msg in hard_failures:
        print(f"::error::verify-board-label-creation: {msg}")
    for f in findings:
        print(f"::error::verify-board-label-creation: {f.path}: job {f.job!r} "
              f"applies {f.label!r} (near line {f.line}) with no `gh label "
              f"create {f.label!r} ... --force` (inline, or via the "
              f"wing-commander-board-labels composite) at an earlier step "
              f"of the SAME job -- the apply may fail there if the label "
              f"does not already exist on the target repo (#488).")


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


def _assert_clean(case, findings, hard):
    if hard:
        fail(f"[{case}] unexpected hard failure(s): {hard}")
        return False
    if findings:
        fail(f"[{case}] unexpected finding(s): {findings}")
        return False
    note(f"[{case}] passed")
    return True


def _assert_finding_for(case, findings, hard, label, job=None):
    if hard:
        fail(f"[{case}] unexpected hard failure(s): {hard}")
        return
    hits = [f for f in findings if f.label == label and (job is None or f.job == job)]
    if not hits:
        fail(f"[{case}] expected a finding for {label!r}"
             f"{'' if job is None else f' in job {job!r}'}, got: {findings}")
    else:
        note(f"[{case}] passed ({hits[0].path}: job {hits[0].job!r}, line {hits[0].line})")


def selftest_same_job_inline_create_passes():
    case = "an inline create earlier in the same job covers a later apply"
    tmp = tempfile.mkdtemp(prefix="wc-board-label-")
    try:
        _write(tmp, ".github/workflows/labels-ok.yml",
               "on: push\njobs:\n  x:\n    runs-on: ubuntu-latest\n    steps:\n"
               "      - shell: bash\n        run: |\n"
               "          gh label create \"board:stalled\" --color B60205 "
               "--force\n"
               "          gh label create \"board:owned\" --color 0E8A16 "
               "--force\n"
               "      - shell: bash\n        run: |\n"
               "          gh issue edit \"$N\" --add-label \"board:stalled\"\n"
               "          gh pr create --title t --label board:owned\n")
        findings, hard = evaluate(tmp)
        _assert_clean(case, findings, hard)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def selftest_missing_create_fails():
    case = "an applied board:* label with no create anywhere fails (the #488 shape)"
    tmp = tempfile.mkdtemp(prefix="wc-board-label-")
    try:
        _write(tmp, ".github/workflows/labels-missing-create.yml",
               "on: push\njobs:\n  x:\n    runs-on: ubuntu-latest\n    steps:\n"
               "      - shell: bash\n        run: |\n"
               "          gh issue edit \"$N\" -R \"$GITHUB_REPOSITORY\" "
               "--add-label \"board:stalled\"\n")
        findings, hard = evaluate(tmp)
        _assert_finding_for(case, findings, hard, "board:stalled", job="x")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def selftest_composite_call_covers_later_applies():
    case = "a wing-commander-board-labels composite step covers later applies in the same job"
    tmp = tempfile.mkdtemp(prefix="wc-board-label-")
    try:
        _write(tmp, ".github/workflows/labels-composite.yml",
               "on: push\njobs:\n  x:\n    runs-on: ubuntu-latest\n    steps:\n"
               "      - uses: ./.github/actions/wing-commander-board-labels\n"
               "        with:\n          token: ${{ env.WC_BOT_TOKEN }}\n"
               "      - shell: bash\n        run: |\n"
               "          gh issue edit \"$N\" --add-label \"board:stalled\"\n"
               "          gh pr create --title t --label board:owned\n")
        findings, hard = evaluate(tmp)
        _assert_clean(case, findings, hard)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def selftest_composite_call_after_apply_does_not_cover_it():
    case = "a composite step AFTER the apply does not retroactively cover it"
    tmp = tempfile.mkdtemp(prefix="wc-board-label-")
    try:
        _write(tmp, ".github/workflows/labels-composite-late.yml",
               "on: push\njobs:\n  x:\n    runs-on: ubuntu-latest\n    steps:\n"
               "      - shell: bash\n        run: |\n"
               "          gh issue edit \"$N\" --add-label \"board:stalled\"\n"
               "      - uses: ./.github/actions/wing-commander-board-labels\n"
               "        with:\n          token: ${{ env.WC_BOT_TOKEN }}\n")
        findings, hard = evaluate(tmp)
        _assert_finding_for(case, findings, hard, "board:stalled", job="x")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def selftest_cross_job_create_does_not_cover_apply():
    case = "a create in a different job (or a different file) does not cover an apply"
    tmp = tempfile.mkdtemp(prefix="wc-board-label-")
    try:
        # The create lives in its own composite action file, entirely
        # separate from the workflow job that applies the label -- the
        # exact shape a file-wide (rather than job-scoped) check would
        # have missed, and the shape the review of #488 caught.
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
        _assert_finding_for(case, findings, hard, "board:stalled", job="x")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def selftest_one_job_missing_the_step_fails_its_sibling_passes():
    case = "one job lacking the step fails while a sibling job with it passes"
    tmp = tempfile.mkdtemp(prefix="wc-board-label-")
    try:
        _write(tmp, ".github/workflows/labels-two-jobs.yml",
               "on: push\n"
               "jobs:\n"
               "  covered:\n"
               "    runs-on: ubuntu-latest\n"
               "    steps:\n"
               "      - uses: ./.github/actions/wing-commander-board-labels\n"
               "        with:\n          token: ${{ env.WC_BOT_TOKEN }}\n"
               "      - shell: bash\n        run: |\n"
               "          gh issue edit \"$N\" --add-label \"board:stalled\"\n"
               "  uncovered:\n"
               "    runs-on: ubuntu-latest\n"
               "    steps:\n"
               "      - shell: bash\n        run: |\n"
               "          gh issue edit \"$N\" --add-label \"board:stalled\"\n")
        findings, hard = evaluate(tmp)
        if hard:
            fail(f"[{case}] unexpected hard failure(s): {hard}")
            return
        covered_hit = any(f.job == "covered" for f in findings)
        uncovered_hit = any(f.job == "uncovered" and f.label == "board:stalled"
                            for f in findings)
        if covered_hit:
            fail(f"[{case}] the covered job should not have a finding: {findings}")
        elif not uncovered_hit:
            fail(f"[{case}] expected a finding in job 'uncovered', got: {findings}")
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
        _assert_clean(case, findings, hard)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def selftest_comment_only_create_does_not_count():
    case = "a gh label create that appears only in a comment line does not count"
    tmp = tempfile.mkdtemp(prefix="wc-board-label-")
    try:
        _write(tmp, ".github/workflows/labels-commented-create.yml",
               "on: push\njobs:\n  x:\n    runs-on: ubuntu-latest\n    steps:\n"
               "      - shell: bash\n        run: |\n"
               "          # gh label create \"board:stalled\" --force\n"
               "          gh issue edit \"$N\" --add-label \"board:stalled\"\n")
        findings, hard = evaluate(tmp)
        _assert_finding_for(case, findings, hard, "board:stalled", job="x")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# One fixture per extended apply form (NIT 2): each proves the form is
# actually detected, by omitting the create and expecting a finding --
# a form the regexes miss would silently pass instead.
_APPLY_FORM_FIXTURES = [
    ("--add-label= form",
     "          gh issue edit \"$N\" --add-label=board:stalled\n"),
    ("comma-separated label list, board label in a non-first position",
     "          gh issue edit \"$N\" --add-label \"spec-request,board:stalled\"\n"),
    ("gh pr create -l short flag",
     "          gh pr create -R \"$R\" --title t -l board:owned\n"),
    ("--label= form on gh pr create",
     "          gh pr create -R \"$R\" --title t --label=board:owned\n"),
    ("REST -f labels[]= form",
     # wc-gh-method-exempt: fixture text for this gate's own self-test, not a real gh api invocation
     "          gh api \"repos/$R/issues/$N/labels\" -f \"labels[]=board:stalled\"\n"),
]


def selftest_extended_apply_forms_detected():
    for name, run_line in _APPLY_FORM_FIXTURES:
        case = f"extended apply form is detected: {name}"
        tmp = tempfile.mkdtemp(prefix="wc-board-label-")
        try:
            _write(tmp, ".github/workflows/labels-form.yml",
                   "on: push\njobs:\n  x:\n    runs-on: ubuntu-latest\n    steps:\n"
                   "      - shell: bash\n        run: |\n" + run_line)
            findings, hard = evaluate(tmp)
            if hard:
                fail(f"[{case}] unexpected hard failure(s): {hard}")
                continue
            board_findings = [f for f in findings if f.label.startswith("board:")]
            if not board_findings:
                fail(f"[{case}] expected a board:* finding, got: {findings}")
            else:
                note(f"[{case}] passed ({[f.label for f in board_findings]})")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


def selftest_extended_apply_forms_pass_with_matching_create():
    for name, run_line in _APPLY_FORM_FIXTURES:
        case = f"extended apply form passes once created: {name}"
        tmp = tempfile.mkdtemp(prefix="wc-board-label-")
        try:
            _write(tmp, ".github/workflows/labels-form-ok.yml",
                   "on: push\njobs:\n  x:\n    runs-on: ubuntu-latest\n    steps:\n"
                   "      - shell: bash\n        run: |\n"
                   "          gh label create \"board:stalled\" --color B60205 "
                   "--force\n"
                   "          gh label create \"board:owned\" --color 0E8A16 "
                   "--force\n"
                   "      - shell: bash\n        run: |\n" + run_line)
            findings, hard = evaluate(tmp)
            _assert_clean(case, findings, hard)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


def run_selftest():
    use_utf8_stdout()
    selftest_same_job_inline_create_passes()
    selftest_missing_create_fails()
    selftest_composite_call_covers_later_applies()
    selftest_composite_call_after_apply_does_not_cover_it()
    selftest_cross_job_create_does_not_cover_apply()
    selftest_one_job_missing_the_step_fails_its_sibling_passes()
    selftest_variable_label_is_ignored()
    selftest_comment_only_create_does_not_count()
    selftest_extended_apply_forms_detected()
    selftest_extended_apply_forms_pass_with_matching_create()
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
