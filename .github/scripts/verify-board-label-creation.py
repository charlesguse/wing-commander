#!/usr/bin/env python3
"""Gate -- every literal label board-loop.yml applies (via `gh issue edit
--add-label`, `gh issue create`/`gh pr create --label`/`-l`, or a REST
`-f "labels[]=..."` call) is created by that SAME job's own
`gh label create ... --force` call, or a `wing-commander-board-labels`
composite call, at an EARLIER step than the first apply -- never merely
"created somewhere in the repository."

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

#493 widened the labels this gate looks at from just `board:*` to every
literal label board-loop.yml applies -- the original `board:*`-only scope
let `gh issue create ... --label spec-request` at three of board-loop.yml's
own call sites (route, fix, readiness) go unnoticed even though nothing
created spec-request either (#493's own report). The subject file stays
pinned to board-loop.yml alone (BOARD_LOOP_FILE), not every workflow: a
dry run against the whole fleet during #493 turned up two apply-shaped
matches elsewhere that are not the #488 bug --
`auto-update-spec-kit.yml`'s and `watchdog.yml`'s `gh issue list --label`
/ `gh search prs --label` calls are reads, not applies, that this gate's
own `--label` detection cannot yet tell apart from a real
`gh issue create --label`/`gh pr create --label` (LABEL_FLAG_VALUE_RE has
no subcommand check), and `cleanup.yml`'s `stage:done` "hit" is inside an
`echo` building a comment body for a human to read, not a `gh` invocation
this gate should ever execute. Widening the subject scope before either of
those is fixed would make this gate red on code that was never the #488
shape. (One further-file finding was real but out of scope for a
board-loop-only fix: `auto-release.yml`'s `verify-e2e` job applies
`spec-request` to its E2E target repo by design, relying on that repo
having been provisioned ahead of time by
`provision-e2e-target.sh:act_spec_request_label` -- a maintainer-run
script this gate does not, and should not, reach into.)

`--self-test`: a synthetic tempdir tree proves the per-job ordering (same
job passes, a different job in the same or another file does not cover
it, the composite call counts as creating all of its labels, a job
missing the step fails while a sibling job with it passes), each of the
extended apply forms is detected (`--add-label=`, a comma-separated label
list, `-l`/`--label=` on `gh issue create`/`gh pr create`, and a REST
`-f "labels[]=..."` call), a `gh label create` that appears only in a
comment line does not count, and a label named only through a shell
variable stays out of scope. Every fixture writes its subject workflow at
BOARD_LOOP_FILE's own path, since that is now the only file this gate
scans.
"""
import argparse
import os
import re
import shutil
import sys
import tempfile
from collections import namedtuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_shell_harness import use_utf8_stdout  # noqa: E402

import yaml  # noqa: E402

# #493: scoped to board-loop.yml alone, not every workflow -- see the
# WHY THIS EXISTS note above for the false-hit and out-of-scope-real-hit
# findings a file-wide dry run turned up. Same path verify-board-readiness.py
# already names as BOARD_LOOP_FILE.
BOARD_LOOP_FILE = ".github/workflows/board-loop.yml"

# The one composite this gate knows creates board:stalled, board:owned, and
# spec-request (wing-commander-board-labels/action.yml). A step that
# `uses:` it counts, for every later step in the same job, as having
# created all three labels -- never for an earlier step, and never for a
# different job.
BOARD_LABELS_COMPOSITE_USES = "./.github/actions/wing-commander-board-labels"
BOARD_LABELS_COMPOSITE_CREATES = ("board:stalled", "board:owned", "spec-request")

# #493: any literal label token, not just `board:*` -- board-loop.yml's own
# apply sites now include the plain `spec-request` label too.
LABEL_TOKEN_RE = re.compile(r'^[A-Za-z0-9_:-]+$')

# --add-label / --label, space or "=" form, quoted or bare value. The bare
# (unquoted) branch is a label-token charset, not `\S+` -- #493's own
# spec-request apply sites are each the last flag inside a `$(gh issue
# create ... --label spec-request)"` command substitution, so a greedy
# `\S+` swallowed the closing `)"` into the "label" and the tightened
# LABEL_TOKEN_RE below (rightly) rejected it, silently dropping the apply
# from scope instead of flagging it.
_VALUE = r'("[^"\n]*"|\'[^\'\n]*\'|[A-Za-z0-9_.,:=-]+)'
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
    r'-f\s+("labels\[\]=[^"\n]*"|\'labels\[\]=[^\'\n]*\'|labels\[\]=[A-Za-z0-9_.,:=-]+)')

# `gh label create <token> ... --force` on one line (every real call site in
# this repo is single-line; see the fleet-wide grep in #488's own review).
CREATE_LABEL_RE = re.compile(r'gh label create\s+' + _VALUE)

Finding = namedtuple("Finding", ["path", "job", "label", "line"])


# --------------------------------------------------------------------------
# Discovery
# --------------------------------------------------------------------------
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


def _labels_in_value(raw):
    """A flag's value may be a single label or a comma-separated list
    (`--add-label "spec-request,board:x"`) -- any literal label token in
    any position is in scope."""
    raw = _unquote(raw)
    labels = []
    for token in raw.split(","):
        token = _unquote(token.strip())
        if LABEL_TOKEN_RE.match(token):
            labels.append(token)
    return labels


# Read commands that take the same `--label` flag spelling as a real apply
# but only filter by it -- `gh issue list --label ...`, `gh pr list --label
# ...`, `gh search ... --label ...`. A multi-line `gh issue create`/
# `gh pr create` can carry its `--label` on a continuation line, well after
# the line naming the subcommand (board-loop.yml's own fix/readiness spec-
# request sites, #493), so this gate cannot require the create/pr-create
# subcommand on the SAME line the way it does for the `-l` short form
# below; it instead blocklists the read shapes it actually knows about.
_LABEL_READ_COMMAND_RE = re.compile(r'gh\s+(issue|pr)\s+list\b|gh\s+search\b')


def _extract_applies(line):
    """Every literal label this line applies, across every supported flag
    form. Skips comment lines entirely."""
    if _is_comment_line(line):
        return []
    labels = []
    for m in ADD_LABEL_VALUE_RE.finditer(line):
        labels.extend(_labels_in_value(m.group(1)))
    if not _LABEL_READ_COMMAND_RE.search(line):
        for m in LABEL_FLAG_VALUE_RE.finditer(line):
            labels.extend(_labels_in_value(m.group(1)))
    if "gh pr create" in line:
        for m in SHORT_LABEL_VALUE_RE.finditer(line):
            labels.extend(_labels_in_value(m.group(1)))
    for m in REST_LABEL_VALUE_RE.finditer(line):
        raw = _unquote(m.group(1))
        if raw.startswith("labels[]="):
            labels.extend(_labels_in_value(raw[len("labels[]="):]))
    return labels


def _extract_creates(line):
    """Every literal label this line creates with `--force`. Skips comment
    lines entirely -- a `# gh label create "board:stalled" --force` left as
    documentation must never satisfy this gate."""
    if _is_comment_line(line):
        return []
    if "--force" not in line:
        return []
    labels = []
    for m in CREATE_LABEL_RE.finditer(line):
        labels.extend(_labels_in_value(m.group(1)))
    return labels


# --------------------------------------------------------------------------
# The per-job scan
# --------------------------------------------------------------------------
def check_job_scope(root="."):
    findings = []
    path = BOARD_LOOP_FILE
    doc = _load_yaml(root, path)
    if doc is None:
        return findings
    text = _read(root, path)
    # A cursor that only ever advances forward through the file. Several
    # steps in board-loop.yml share an identical first line (most begin
    # `set -uo pipefail`), so a plain `text.find(lines[0])` always resolves
    # to the FIRST such line in the whole file -- every finding reported
    # "near line 110" regardless of which step it was actually in (#493).
    # Searching from a cursor that only moves forward, and updating it past
    # each match found, makes each successive occurrence of shared text
    # resolve to its own, later position instead.
    cursor = 0
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
            run_lines = run.split("\n")
            first_line = run.splitlines()[0] if run.splitlines() else ""
            offset = text.find(first_line, cursor) if first_line else -1
            if offset == -1:
                # Fallback: text.find from the start, so a step this
                # cursor-based search cannot place still gets SOME line
                # number rather than none.
                offset = text.find(first_line) if first_line else 0
                offset = max(offset, 0)
            else:
                cursor = offset + len(first_line)
            base_line = line_of(text, offset)
            for idx, line in enumerate(run_lines):
                for label in _extract_creates(line):
                    created.add(label)
                for label in _extract_applies(line):
                    if label not in created:
                        findings.append(Finding(
                            path, job, label, base_line + idx))
    return findings


def evaluate(root="."):
    """Returns (findings, hard_failures)."""
    if not os.path.isfile(os.path.join(root, BOARD_LOOP_FILE)):
        return [], [f"{BOARD_LOOP_FILE} not found -- this gate is about to "
                     "check nothing."]
    return check_job_scope(root), []


def report(findings, hard_failures):
    for msg in hard_failures:
        print(f"::error::verify-board-label-creation: {msg}")
    for f in findings:
        print(f"::error::verify-board-label-creation: {f.path}:{f.line}: job "
              f"{f.job!r} applies {f.label!r} with no `gh label create "
              f"{f.label!r} ... --force` (inline, or via the "
              f"wing-commander-board-labels composite) at an earlier step "
              f"of the SAME job -- the apply may fail there if the label "
              f"does not already exist on the target repo (#488, #493).")


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
        _write(tmp, BOARD_LOOP_FILE,
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
        _write(tmp, BOARD_LOOP_FILE,
               "on: push\njobs:\n  x:\n    runs-on: ubuntu-latest\n    steps:\n"
               "      - shell: bash\n        run: |\n"
               "          gh issue edit \"$N\" -R \"$GITHUB_REPOSITORY\" "
               "--add-label \"board:stalled\"\n")
        findings, hard = evaluate(tmp)
        _assert_finding_for(case, findings, hard, "board:stalled", job="x")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def selftest_spec_request_missing_create_fails():
    case = "an applied spec-request label with no create anywhere fails (the #493 shape)"
    tmp = tempfile.mkdtemp(prefix="wc-board-label-")
    try:
        _write(tmp, BOARD_LOOP_FILE,
               "on: push\njobs:\n  route:\n    runs-on: ubuntu-latest\n    steps:\n"
               "      - shell: bash\n        run: |\n"
               "          gh issue create -R \"$GITHUB_REPOSITORY\" --title t "
               "--label spec-request\n")
        findings, hard = evaluate(tmp)
        _assert_finding_for(case, findings, hard, "spec-request", job="route")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def selftest_composite_call_covers_later_applies():
    case = "a wing-commander-board-labels composite step covers later applies in the same job, including spec-request"
    tmp = tempfile.mkdtemp(prefix="wc-board-label-")
    try:
        _write(tmp, BOARD_LOOP_FILE,
               "on: push\njobs:\n  x:\n    runs-on: ubuntu-latest\n    steps:\n"
               "      - uses: ./.github/actions/wing-commander-board-labels\n"
               "        with:\n          token: ${{ env.WC_BOT_TOKEN }}\n"
               "      - shell: bash\n        run: |\n"
               "          gh issue edit \"$N\" --add-label \"board:stalled\"\n"
               "          gh pr create --title t --label board:owned\n"
               "          gh issue create --title t --label spec-request\n")
        findings, hard = evaluate(tmp)
        _assert_clean(case, findings, hard)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def selftest_composite_call_after_apply_does_not_cover_it():
    case = "a composite step AFTER the apply does not retroactively cover it"
    tmp = tempfile.mkdtemp(prefix="wc-board-label-")
    try:
        _write(tmp, BOARD_LOOP_FILE,
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
    case = "a create in a different job does not cover an apply"
    tmp = tempfile.mkdtemp(prefix="wc-board-label-")
    try:
        _write(tmp, BOARD_LOOP_FILE,
               "on: push\n"
               "jobs:\n"
               "  other:\n"
               "    runs-on: ubuntu-latest\n"
               "    steps:\n"
               "      - shell: bash\n        run: |\n"
               "          gh label create \"board:stalled\" --color B60205 "
               "--force\n"
               "  x:\n"
               "    runs-on: ubuntu-latest\n"
               "    steps:\n"
               "      - shell: bash\n        run: |\n"
               "          gh issue edit \"$N\" --add-label \"board:stalled\"\n")
        findings, hard = evaluate(tmp)
        _assert_finding_for(case, findings, hard, "board:stalled", job="x")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def selftest_other_file_is_out_of_scope():
    case = "a create OR an apply in a file other than board-loop.yml is out of scope entirely"
    tmp = tempfile.mkdtemp(prefix="wc-board-label-")
    try:
        # The exact shape a file-wide (rather than board-loop-scoped) check
        # would have flagged: an unrelated workflow applying a label with
        # no create of its own. #493 scoped this gate to board-loop.yml
        # alone (see the module docstring) precisely so this stays quiet.
        # board-loop.yml itself is present but has nothing to say about it.
        _write(tmp, BOARD_LOOP_FILE,
               "on: push\njobs:\n  y:\n    runs-on: ubuntu-latest\n    steps:\n"
               "      - shell: bash\n        run: |\n          echo noop\n")
        _write(tmp, ".github/workflows/some-other-workflow.yml",
               "on: push\njobs:\n  x:\n    runs-on: ubuntu-latest\n    steps:\n"
               "      - shell: bash\n        run: |\n"
               "          gh issue edit \"$N\" --add-label \"board:stalled\"\n")
        findings, hard = evaluate(tmp)
        if hard:
            fail(f"[{case}] unexpected hard failure(s): {hard}")
            return
        if findings:
            fail(f"[{case}] unexpected finding(s) from a non-board-loop file: {findings}")
        else:
            note(f"[{case}] passed")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def selftest_one_job_missing_the_step_fails_its_sibling_passes():
    case = "one job lacking the step fails while a sibling job with it passes"
    tmp = tempfile.mkdtemp(prefix="wc-board-label-")
    try:
        _write(tmp, BOARD_LOOP_FILE,
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
        _write(tmp, BOARD_LOOP_FILE,
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
        _write(tmp, BOARD_LOOP_FILE,
               "on: push\njobs:\n  x:\n    runs-on: ubuntu-latest\n    steps:\n"
               "      - shell: bash\n        run: |\n"
               "          # gh label create \"board:stalled\" --force\n"
               "          gh issue edit \"$N\" --add-label \"board:stalled\"\n")
        findings, hard = evaluate(tmp)
        _assert_finding_for(case, findings, hard, "board:stalled", job="x")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def selftest_command_substitution_trailing_punctuation_still_matches():
    case = ("a --label value at the end of a $(...) command substitution "
            "is not swallowed with its closing )\" (#493's own spec-request "
            "shape at route/fix/readiness)")
    tmp = tempfile.mkdtemp(prefix="wc-board-label-")
    try:
        _write(tmp, BOARD_LOOP_FILE,
               "on: push\njobs:\n  route:\n    runs-on: ubuntu-latest\n    steps:\n"
               "      - shell: bash\n        run: |\n"
               "          spec_url=\"$(gh issue create -R \"$R\" --title t "
               "--body b --label spec-request)\"\n")
        findings, hard = evaluate(tmp)
        _assert_finding_for(case, findings, hard, "spec-request", job="route")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def selftest_read_only_label_flag_is_not_an_apply():
    case = "a --label flag on gh issue list / gh pr list / gh search (a read) is never mistaken for an apply"
    tmp = tempfile.mkdtemp(prefix="wc-board-label-")
    try:
        _write(tmp, BOARD_LOOP_FILE,
               "on: push\njobs:\n  x:\n    runs-on: ubuntu-latest\n    steps:\n"
               "      - shell: bash\n        run: |\n"
               "          gh issue list -R \"$R\" --label \"spec-request\" "
               "--state open\n"
               "          gh pr list -R \"$R\" --label board:owned "
               "--state open\n"
               "          gh search prs --repo \"$R\" --label board:owned "
               "--state all\n")
        findings, hard = evaluate(tmp)
        _assert_clean(case, findings, hard)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def selftest_multiline_apply_label_on_a_continuation_line_still_detected():
    case = ("a --label flag on a continuation line, several lines below the "
            "gh issue create/gh pr create it belongs to, is still detected "
            "(board-loop.yml's own fix/readiness spec-request sites split "
            "the command across lines with trailing `\\`)")
    tmp = tempfile.mkdtemp(prefix="wc-board-label-")
    try:
        _write(tmp, BOARD_LOOP_FILE,
               "on: push\njobs:\n  fix:\n    runs-on: ubuntu-latest\n    steps:\n"
               "      - shell: bash\n        run: |\n"
               "          spec_url=\"$(gh issue create -R \"$R\" \\\n"
               "            --title t \\\n"
               "            --body b \\\n"
               "            --label spec-request)\"\n")
        findings, hard = evaluate(tmp)
        _assert_finding_for(case, findings, hard, "spec-request", job="fix")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def selftest_finding_line_number_is_exact_with_shared_first_lines():
    case = "the reported line number is the apply's own line, even when steps share an identical first line (the #493 'near line 110' bug)"
    tmp = tempfile.mkdtemp(prefix="wc-board-label-")
    try:
        content = (
            "on: push\njobs:\n  x:\n    runs-on: ubuntu-latest\n    steps:\n"
            "      - shell: bash\n        run: |\n"
            "          set -uo pipefail\n"
            "          echo unrelated\n"
            "      - shell: bash\n        run: |\n"
            "          set -uo pipefail\n"
            "          echo also unrelated\n"
            "      - shell: bash\n        run: |\n"
            "          set -uo pipefail\n"
            "          gh issue edit \"$N\" --add-label \"board:stalled\"\n"
        )
        _write(tmp, BOARD_LOOP_FILE, content)
        expected_line = content.splitlines().index(
            "          gh issue edit \"$N\" --add-label \"board:stalled\"") + 1
        findings, hard = evaluate(tmp)
        if hard:
            fail(f"[{case}] unexpected hard failure(s): {hard}")
            return
        hits = [f for f in findings if f.label == "board:stalled"]
        if not hits:
            fail(f"[{case}] expected a finding, got none: {findings}")
        elif hits[0].line != expected_line:
            fail(f"[{case}] expected line {expected_line}, got {hits[0].line} "
                 f"(the shared 'set -uo pipefail' first line at line 8 is the "
                 f"#493 bug's own wrong answer)")
        else:
            note(f"[{case}] passed (line {hits[0].line})")
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
    ("--label form on gh issue create (#493's own spec-request shape)",
     "          gh issue create -R \"$R\" --title t --label spec-request\n"),
    ("REST -f labels[]= form",
     # wc-gh-method-exempt: fixture text for this gate's own self-test, not a real gh api invocation
     "          gh api \"repos/$R/issues/$N/labels\" -f \"labels[]=board:stalled\"\n"),
]


def selftest_extended_apply_forms_detected():
    for name, run_line in _APPLY_FORM_FIXTURES:
        case = f"extended apply form is detected: {name}"
        tmp = tempfile.mkdtemp(prefix="wc-board-label-")
        try:
            _write(tmp, BOARD_LOOP_FILE,
                   "on: push\njobs:\n  x:\n    runs-on: ubuntu-latest\n    steps:\n"
                   "      - shell: bash\n        run: |\n" + run_line)
            findings, hard = evaluate(tmp)
            if hard:
                fail(f"[{case}] unexpected hard failure(s): {hard}")
                continue
            if not findings:
                fail(f"[{case}] expected a finding, got: {findings}")
            else:
                note(f"[{case}] passed ({[f.label for f in findings]})")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


def selftest_extended_apply_forms_pass_with_matching_create():
    for name, run_line in _APPLY_FORM_FIXTURES:
        case = f"extended apply form passes once created: {name}"
        tmp = tempfile.mkdtemp(prefix="wc-board-label-")
        try:
            _write(tmp, BOARD_LOOP_FILE,
                   "on: push\njobs:\n  x:\n    runs-on: ubuntu-latest\n    steps:\n"
                   "      - shell: bash\n        run: |\n"
                   "          gh label create \"board:stalled\" --color B60205 "
                   "--force\n"
                   "          gh label create \"board:owned\" --color 0E8A16 "
                   "--force\n"
                   "          gh label create \"spec-request\" --color 0E8A16 "
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
    selftest_spec_request_missing_create_fails()
    selftest_composite_call_covers_later_applies()
    selftest_composite_call_after_apply_does_not_cover_it()
    selftest_cross_job_create_does_not_cover_apply()
    selftest_other_file_is_out_of_scope()
    selftest_one_job_missing_the_step_fails_its_sibling_passes()
    selftest_variable_label_is_ignored()
    selftest_comment_only_create_does_not_count()
    selftest_command_substitution_trailing_punctuation_still_matches()
    selftest_multiline_apply_label_on_a_continuation_line_still_detected()
    selftest_read_only_label_flag_is_not_an_apply()
    selftest_finding_line_number_is_exact_with_shared_first_lines()
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
