#!/usr/bin/env python3
"""Gate -- two tiers, both job-scoped, never file-wide "created somewhere":

  1. Every literal `board:*` label applied (via `gh issue edit --add-label`,
     `gh issue create`/`gh pr create --label`/`-l`, or a REST
     `-f "labels[]=..."` call) in ANY workflow or composite action is
     created by that SAME job's own `gh label create ... --force` call, or
     a local composite action (`uses: ./...`) whose OWN steps actually
     create it, at an EARLIER step than the first apply. This is main's
     original #488 scope, unchanged.
  2. board-loop.yml additionally gets checked for EVERY literal label it
     applies, not just `board:*` -- #493's own spec-request bug was a
     board-loop.yml-only label outside tier 1's board:*-only reach.

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
the actual failure mode: a workflow's own jobs run as separate runners that
can each be entered directly (board-loop.yml's resume path re-enters at
fix, review or readiness without triage/route ever running in that job
graph), so a create in one job's steps says nothing about whether the JOB
that applies the label ran its own create first. A first version of this
gate checked file-wide co-occurrence and stayed green with the
label-creating step deleted from a single job -- code review of #488
caught it. This version walks each job's (or composite action's) own step
list in order and requires the create -- inline, or via a local composite
action whose own steps create it -- to appear in an earlier step of THAT
SAME job than the first apply. There is no cross-job or cross-file
fallback: a composite creating a label counts only for the job that
actually `uses:` it, never for a sibling job or a different file that
never calls that composite.

A composite's own creates are DERIVED, never assumed: this gate walks a
`uses: ./...` step's target action.yml through the exact same
`_extract_creates` used for an inline `run:` block, so deleting a create
from wing-commander-board-labels/action.yml (or any local composite) shows
up here as a real finding instead of silently trusting a hardcoded belief
about what that composite does (code review of #493's first version caught
a hardcoded `BOARD_LABELS_COMPOSITE_CREATES` tuple doing exactly that --
`gh label create` lines could be deleted from the composite with this gate
still reporting 0 failures).

#493 widened tier 2 (board-loop.yml only) from just `board:*` to every
literal label it applies -- the original `board:*`-only scope let
`gh issue create ... --label spec-request` at three of board-loop.yml's own
call sites (route, fix, readiness) go unnoticed even though nothing
created spec-request either (#493's own report). Tier 1 (every workflow
and composite action, `board:*` only) stays exactly as narrow as main's
original scope: a dry run that widened the LABEL TOKEN everywhere, not
just in board-loop.yml, turned up matches elsewhere that are not the
#488/#493 shape -- `auto-update-spec-kit.yml`'s and `watchdog.yml`'s
`gh issue list --label ...` / `gh search ... --label ...` calls are reads,
not applies, and `cleanup.yml`'s `stage:done` "hit" is inside an `echo`
building a comment body for a human to read, not a `gh` invocation this
gate should ever execute. Widening the label token everywhere (rather than
the file this gate additionally scans in full) would have made this gate
red on code that was never the #488/#493 shape; keeping tier 1 to
`board:*` while adding tier 2 for board-loop.yml's own wider set is what
avoids that without dropping main's original repo-wide `board:*` coverage.
(One further-file finding from that dry run was real but out of scope for
a board-loop-only fix: `auto-release.yml`'s `verify-e2e` job applies
`spec-request` to its E2E target repo by design, relying on that repo
having been provisioned ahead of time by
`provision-e2e-target.sh:act_spec_request_label` -- a maintainer-run
script this gate does not, and should not, reach into.)

`--label`/`-l` detection is per-command, not line-wide: a line can hold
more than one shell command (`n=$(gh search issues x); gh issue create
--label newlbl`), a real command can carry a trailing shell comment
(`gh issue create --label newlbl # vs gh pr list`), and a multi-line
command's own `--label` can land on a continuation line several lines
below the command name (board-loop.yml's own fix/readiness spec-request
sites: `gh issue create ... \` / `  --label spec-request)"`). Line-wide
matching either missed a real apply hiding after a read command's own
`--label`, or (worse) mistook a `--label` continuation of a `gh issue
list`/`gh search` as an apply. Each physical line is split on `;`, `&&`,
`||`, `|`, and `$(` into command segments after stripping a trailing shell
comment; each segment is classified as a read command (`gh issue list`,
`gh pr list`, `gh search`) or not on its own; a segment continuing the
previous physical line (trailing unescaped `\`) inherits that command's
classification instead of reclassifying itself.

A file this gate needs to read that fails to parse as YAML is a hard
failure (a finding), never a silent 0 -- the same reasoning `evaluate()`
already applies to board-loop.yml going missing entirely.

`--self-test`: see `run_selftest()` for the full list; it proves the
per-job ordering, that a composite's creates are derived from its own
`run:` blocks (not hardcoded) including a composite missing a label,
cross-file/cross-job non-coverage in both directions (an inline create and
a composite's own create), each extended apply form (`--add-label=`, a
comma-separated list, `-l`/`--label=` on `gh issue create`/`gh pr
create`/`gh issue edit`, and a REST `-f "labels[]=..."` call), the
command-substitution trailing-punctuation fix, the per-command read/apply
split (mid-line command switch, trailing comment, multi-line continuation
inheriting its command's classification), a `gh label create` that
appears only in a comment line not counting, a label named only through a
shell variable staying out of scope, tier 1's repo-wide `board:*` coverage
(and that a non-board literal label elsewhere is correctly tier-1-exempt),
the exact reported line number even when steps share an identical first
line, and a file that fails to parse producing a hard failure.
"""
import argparse
import glob
import os
import re
import shutil
import sys
import tempfile
from collections import namedtuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_shell_harness import use_utf8_stdout  # noqa: E402

import yaml  # noqa: E402

# Tier 2's own subject file (verify-board-readiness.py already names this
# same path BOARD_LOOP_FILE).
BOARD_LOOP_FILE = ".github/workflows/board-loop.yml"

WORKFLOWS_DIR = ".github/workflows"
ACTIONS_DIR = ".github/actions"

# Tier 1: board:* only, matching main's original (#488) scope.
BOARD_LABEL_TOKEN_RE = re.compile(r'^board:[A-Za-z0-9_-]+$')
# Tier 2 (board-loop.yml only): any literal label token (#493).
ANY_LABEL_TOKEN_RE = re.compile(r'^[A-Za-z0-9_:-]+$')

# --add-label / --label, space or "=" form, quoted or bare value. The bare
# (unquoted) branch is a label-token charset, not `\S+` -- #493's own
# spec-request apply sites are each the last flag inside a `$(gh issue
# create ... --label spec-request)"` command substitution, so a greedy
# `\S+` swallowed the closing `)"` into the "label" and the token regex
# above (rightly) rejected it, silently dropping the apply from scope
# instead of flagging it.
_VALUE = r'("[^"\n]*"|\'[^\'\n]*\'|[A-Za-z0-9_.,:=-]+)'
ADD_LABEL_VALUE_RE = re.compile(r'--add-label(?:=|\s+)' + _VALUE)
LABEL_FLAG_VALUE_RE = re.compile(r'--label(?:=|\s+)' + _VALUE)
# `-l` short form: only recognized on a `gh pr create`/`gh issue create`/
# `gh issue edit` command, so an unrelated `-l` flag elsewhere (ls -l,
# wc -l, ...) is never mistaken for it.
SHORT_LABEL_VALUE_RE = re.compile(r'-l(?:=|\s+)' + _VALUE)
_LABEL_SHORT_FLAG_COMMANDS = ("gh pr create", "gh issue create", "gh issue edit")
# wc-gh-method-exempt: documentation, not an invocation -- REST array form
# (-f "labels[]=board:x") on a gh api call this gate's own apply-detection
# matches; it does not call gh api itself.
REST_LABEL_VALUE_RE = re.compile(
    r'-f\s+("labels\[\]=[^"\n]*"|\'labels\[\]=[^\'\n]*\'|labels\[\]=[A-Za-z0-9_.,:=-]+)')

# `gh label create <token> ... --force` on one line (every real call site in
# this repo is single-line; see the fleet-wide grep in #488's own review).
CREATE_LABEL_RE = re.compile(r'gh label create\s+' + _VALUE)

# A command that filters BY a label rather than applying one -- the same
# `--label` flag spelling as a real apply. Checked per command SEGMENT
# (see `_line_segments`), never per line.
_LABEL_READ_COMMAND_RE = re.compile(r'gh\s+(issue|pr)\s+list\b|gh\s+search\b')

# Shell command-boundary operators a `--label`/`-l` for one command must
# never be attributed across: `;`, `&&`, `||`, `|`, and `$(` (a command
# substitution starts a nested command, even though its own `)` does not
# reappear as a boundary token here -- the trailing `)"` a substitution
# leaves behind is handled by _VALUE's charset above, not by resplitting).
_CMD_SPLIT_RE = re.compile(r'&&|\|\||[;|]|\$\(')

Finding = namedtuple("Finding", ["path", "job", "label", "line"])


class GateParseError(Exception):
    """A subject file could not be parsed as YAML. Raised, never
    swallowed into a silent 0 findings -- a file this gate cannot read is
    a hard failure, not a clean bill of health."""


# --------------------------------------------------------------------------
# Discovery
# --------------------------------------------------------------------------
def workflow_files(root="."):
    base = os.path.join(root, WORKFLOWS_DIR)
    return sorted(_relativize(root, glob.glob(os.path.join(base, "*.yml"))
                               + glob.glob(os.path.join(base, "*.yaml"))))


def action_files(root="."):
    """Every action.yml/action.yaml under .github/actions/**."""
    base = os.path.join(root, ACTIONS_DIR)
    found = []
    for dirpath, _dirs, names in os.walk(base):
        for name in names:
            if name in ("action.yml", "action.yaml"):
                found.append(os.path.join(dirpath, name))
    return sorted(_relativize(root, found))


def _relativize(root, paths):
    """Repo-relative, forward slashes, no leading "./" -- glob.glob(os.path
    .join(root, ...)) with root="." returns "./.github/workflows/x.yml"
    unchanged (it is already relative), so a bare `os.path.isabs` check
    misses it and BOARD_LOOP_FILE's own no-"./" spelling never matches it
    for the tier-1/tier-2 dedup in evaluate() -- board-loop.yml would get
    scanned twice, once under each spelling."""
    out = []
    for p in paths:
        if os.path.isabs(p):
            p = os.path.relpath(p, root).replace(os.sep, "/")
        else:
            p = p.replace(os.sep, "/")
        while p.startswith("./"):
            p = p[2:]
        out.append(p)
    return out


def all_subject_files(root="."):
    return sorted(workflow_files(root) + action_files(root))


def _read(root, path):
    with open(os.path.join(root, path), encoding="utf-8") as fh:
        return fh.read()


def _load_yaml(root, path):
    """None if the file does not exist (a `uses: ./...` composite that
    simply isn't there); raises GateParseError if it exists but is not
    valid YAML -- callers must let that propagate to a hard failure, never
    catch-and-continue-as-if-clean."""
    try:
        text = _read(root, path)
    except OSError:
        return None
    try:
        return yaml.safe_load(text) or {}
    except yaml.YAMLError as e:
        raise GateParseError(f"{path}: could not be parsed as YAML ({e})") from e


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
# Per-line / per-command extraction
# --------------------------------------------------------------------------
def _is_comment_line(line):
    return line.strip().startswith("#")


def _strip_trailing_comment(line):
    """A ` # ...` shell comment trailing real command text -- quote-aware,
    so a `#` inside a quoted string is never mistaken for one."""
    in_dq = in_sq = False
    for i, ch in enumerate(line):
        if ch == '"' and not in_sq:
            in_dq = not in_dq
        elif ch == "'" and not in_dq:
            in_sq = not in_sq
        elif ch == '#' and not in_dq and not in_sq:
            if i == 0 or line[i - 1].isspace():
                return line[:i]
    return line


def _is_line_continuation(stripped):
    """True if `stripped` ends in an unescaped trailing `\\` (an odd run
    of trailing backslashes -- an even run is escaped-literal-backslash
    pairs, never a continuation)."""
    if not stripped.endswith("\\"):
        return False
    count = 0
    i = len(stripped) - 1
    while i >= 0 and stripped[i] == "\\":
        count += 1
        i -= 1
    return count % 2 == 1


def _line_segments(line):
    """Split one physical line into command segments on `;`, `&&`, `||`,
    `|`, and `$(` -- the shell operators that start a new command within
    the same line."""
    segments = []
    last = 0
    for m in _CMD_SPLIT_RE.finditer(line):
        segments.append(line[last:m.start()])
        last = m.end()
    segments.append(line[last:])
    return segments


def _unquote(raw):
    raw = raw.strip()
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'":
        raw = raw[1:-1]
    return raw


def _labels_in_value(raw, token_re):
    """A flag's value may be a single label or a comma-separated list
    (`--add-label "spec-request,board:x"`) -- a matching literal label
    token in any position is in scope."""
    raw = _unquote(raw)
    labels = []
    for token in raw.split(","):
        token = _unquote(token.strip())
        if token_re.match(token):
            labels.append(token)
    return labels


def _labels_applied_in_segment(seg_text, is_read, token_re):
    """Every literal label one command SEGMENT applies, across every
    supported flag form. `is_read` (this segment's own command
    classification -- see `_iter_applies`) suppresses `--label`/`--label=`
    only: `gh issue list --label ...` / `gh pr list --label ...` /
    `gh search ... --label ...` read labels rather than applying one, but
    `--add-label` and the REST array form have no read-command spelling in
    this repo, so they are never suppressed."""
    labels = []
    for m in ADD_LABEL_VALUE_RE.finditer(seg_text):
        labels.extend(_labels_in_value(m.group(1), token_re))
    if not is_read:
        for m in LABEL_FLAG_VALUE_RE.finditer(seg_text):
            labels.extend(_labels_in_value(m.group(1), token_re))
    if any(cmd in seg_text for cmd in _LABEL_SHORT_FLAG_COMMANDS):
        for m in SHORT_LABEL_VALUE_RE.finditer(seg_text):
            labels.extend(_labels_in_value(m.group(1), token_re))
    for m in REST_LABEL_VALUE_RE.finditer(seg_text):
        raw = _unquote(m.group(1))
        if raw.startswith("labels[]="):
            labels.extend(_labels_in_value(raw[len("labels[]="):], token_re))
    return labels


def _iter_applies(run_lines, token_re):
    """Yields (line_idx, label) for every literal label APPLIED across a
    step's run block, honoring per-command read/apply classification (see
    the module docstring's "per-command, not line-wide" note). `line_idx`
    is 0-based within `run_lines`."""
    carry_open = False
    carry_is_read = False
    for idx, raw_line in enumerate(run_lines):
        if _is_comment_line(raw_line):
            carry_open = False
            carry_is_read = False
            continue
        line = _strip_trailing_comment(raw_line)
        stripped = line.rstrip()
        continues = _is_line_continuation(stripped)
        body = stripped[:-1] if continues else stripped
        segments = _line_segments(body)
        is_continuation_line = carry_open
        last_is_read = carry_is_read
        for i, seg_text in enumerate(segments):
            if i == 0 and is_continuation_line:
                is_read = carry_is_read
            else:
                is_read = bool(_LABEL_READ_COMMAND_RE.search(seg_text))
            for label in _labels_applied_in_segment(seg_text, is_read, token_re):
                yield idx, label
            last_is_read = is_read
        carry_open = continues
        carry_is_read = last_is_read


def _extract_creates(line):
    """Every literal label this line creates with `--force`. Skips comment
    lines entirely -- a `# gh label create "board:stalled" --force` left as
    documentation must never satisfy this gate. Always uses the widest
    token pattern: what a create makes available is never itself
    tier-restricted, only which applies this gate checks against it is."""
    if _is_comment_line(line):
        return []
    if "--force" not in line:
        return []
    labels = []
    for m in CREATE_LABEL_RE.finditer(line):
        labels.extend(_labels_in_value(m.group(1), ANY_LABEL_TOKEN_RE))
    return labels


# --------------------------------------------------------------------------
# Composite actions: creates are DERIVED, never a hardcoded belief
# --------------------------------------------------------------------------
def _composite_creates(root, uses_path):
    """Every literal label a local composite action (`uses: ./...`)
    actually creates, derived by walking ITS OWN `runs.steps` through the
    same `_extract_creates` a workflow job's inline `run:` blocks use --
    never a hardcoded belief about what a named composite does. Raises
    GateParseError if the composite's action.yml exists but fails to
    parse; returns an empty set if the composite simply is not there."""
    rel = uses_path
    while rel.startswith("./"):
        rel = rel[2:]
    for name in ("action.yml", "action.yaml"):
        candidate = f"{rel}/{name}"
        if os.path.isfile(os.path.join(root, candidate)):
            doc = _load_yaml(root, candidate)
            if not isinstance(doc, dict):
                return set()
            creates = set()
            for _job, steps in _step_lists(doc):
                for step in steps:
                    step = step or {}
                    run = str(step.get("run") or "")
                    for line in run.split("\n"):
                        creates.update(_extract_creates(line))
            return creates
    return set()


# --------------------------------------------------------------------------
# The per-job scan
# --------------------------------------------------------------------------
def check_job_scope(root, path, token_re):
    """Every finding in `path`, using `token_re` to decide which applied
    labels are in scope (BOARD_LABEL_TOKEN_RE for tier 1, ANY_LABEL_TOKEN_RE
    for board-loop.yml's own tier-2 pass). Raises GateParseError if `path`
    exists but fails to parse."""
    findings = []
    doc = _load_yaml(root, path)
    if doc is None:
        return findings
    text = _read(root, path)
    # A cursor that only ever advances forward through the file. Several
    # steps share an identical first line (most begin `set -uo pipefail`),
    # so a plain `text.find(lines[0])` always resolves to the FIRST such
    # line in the whole file -- every finding reported "near line 110"
    # regardless of which step it was actually in (#493). Searching from a
    # cursor that only moves forward, and updating it past each match
    # found, makes each successive occurrence of shared text resolve to
    # its own, later position instead.
    cursor = 0
    for job, steps in _step_lists(doc):
        created = set()
        for step in steps:
            step = step or {}
            uses = str(step.get("uses") or "").strip()
            if uses.startswith("./"):
                created.update(_composite_creates(root, uses))
                continue
            run = str(step.get("run") or "")
            if not run:
                continue
            run_lines = run.split("\n")
            first_line = run_lines[0] if run_lines else ""
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

            for line in run_lines:
                for label in _extract_creates(line):
                    created.add(label)
            for idx, label in _iter_applies(run_lines, token_re):
                if label not in created:
                    findings.append(Finding(path, job, label, base_line + idx))
    return findings


def evaluate(root="."):
    """Returns (findings, hard_failures)."""
    if not os.path.isfile(os.path.join(root, BOARD_LOOP_FILE)):
        return [], [f"{BOARD_LOOP_FILE} not found -- this gate is about to "
                     "check nothing."]

    findings = []
    hard_failures = []

    # Tier 2: board-loop.yml, every literal label.
    try:
        findings.extend(check_job_scope(root, BOARD_LOOP_FILE, ANY_LABEL_TOKEN_RE))
    except GateParseError as e:
        hard_failures.append(str(e))

    # Tier 1: every workflow and composite action, board:* only. Skips
    # board-loop.yml itself -- tier 2 above already covers it, and
    # ANY_LABEL_TOKEN_RE is a superset of BOARD_LABEL_TOKEN_RE, so a second
    # pass would only ever produce duplicate board:* findings.
    for path in all_subject_files(root):
        if path == BOARD_LOOP_FILE:
            continue
        try:
            findings.extend(check_job_scope(root, path, BOARD_LABEL_TOKEN_RE))
        except GateParseError as e:
            hard_failures.append(str(e))

    return findings, hard_failures


def report(findings, hard_failures):
    for msg in hard_failures:
        print(f"::error::verify-board-label-creation: {msg}")
    for f in findings:
        print(f"::error::verify-board-label-creation: {f.path}:{f.line}: job "
              f"{f.job!r} applies {f.label!r} with no `gh label create "
              f"{f.label!r} ... --force` (inline, or via a local composite "
              f"action whose own steps create it) at an earlier step of the "
              f"SAME job -- the apply may fail there if the label does not "
              f"already exist on the target repo (#488, #493).")


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


def _assert_finding_for(case, findings, hard, label, job=None, path=None):
    if hard:
        fail(f"[{case}] unexpected hard failure(s): {hard}")
        return
    hits = [f for f in findings if f.label == label
            and (job is None or f.job == job)
            and (path is None or f.path == path)]
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


def selftest_composite_creates_are_derived_not_hardcoded():
    case = ("a composite's creates are derived from its own run: blocks -- "
            "deleting a create from the composite file itself surfaces as "
            "a finding, not a silent pass (code review of #493's first "
            "version caught a hardcoded belief that did not do this)")
    tmp = tempfile.mkdtemp(prefix="wc-board-label-")
    try:
        # The composite creates board:stalled but NOT spec-request.
        _write(tmp, ".github/actions/wing-commander-board-labels/action.yml",
               "runs:\n  using: composite\n  steps:\n"
               "    - shell: bash\n      run: |\n"
               "        gh label create \"board:stalled\" --color B60205 "
               "--force\n")
        _write(tmp, BOARD_LOOP_FILE,
               "on: push\njobs:\n  route:\n    runs-on: ubuntu-latest\n    steps:\n"
               "      - uses: ./.github/actions/wing-commander-board-labels\n"
               "        with:\n          token: ${{ env.WC_BOT_TOKEN }}\n"
               "      - shell: bash\n        run: |\n"
               "          gh issue edit \"$N\" --add-label \"board:stalled\"\n"
               "          gh issue create --title t --label spec-request\n")
        findings, hard = evaluate(tmp)
        _assert_finding_for(case, findings, hard, "spec-request", job="route")
        if hard:
            return
        board_hit = any(f.label == "board:stalled" and f.job == "route" for f in findings)
        if board_hit:
            fail(f"[{case}] board:stalled IS created by the composite and "
                 f"should not have a finding: {findings}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def selftest_composite_call_covers_later_applies():
    case = "a composite step covers later applies in the same job, including spec-request"
    tmp = tempfile.mkdtemp(prefix="wc-board-label-")
    try:
        _write(tmp, ".github/actions/wing-commander-board-labels/action.yml",
               "runs:\n  using: composite\n  steps:\n"
               "    - shell: bash\n      run: |\n"
               "        gh label create \"board:stalled\" --color B60205 "
               "--force\n"
               "        gh label create \"board:owned\" --color 0E8A16 "
               "--force\n"
               "        gh label create \"spec-request\" --color 0E8A16 "
               "--force\n")
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
        _write(tmp, ".github/actions/wing-commander-board-labels/action.yml",
               "runs:\n  using: composite\n  steps:\n"
               "    - shell: bash\n      run: |\n"
               "        gh label create \"board:stalled\" --color B60205 "
               "--force\n")
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
    case = "an inline create in a different job does not cover an apply"
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


def selftest_composite_create_in_another_file_does_not_cover_an_apply_that_never_calls_it():
    case = ("a composite that CREATES a label, called from one job, does "
            "not cover an apply of that same label in a DIFFERENT file "
            "that never calls the composite (the right-direction cross-file "
            "case: the create is real and reachable, just not from here)")
    tmp = tempfile.mkdtemp(prefix="wc-board-label-")
    try:
        _write(tmp, ".github/actions/wing-commander-board-labels/action.yml",
               "runs:\n  using: composite\n  steps:\n"
               "    - shell: bash\n      run: |\n"
               "        gh label create \"board:owned\" --color 0E8A16 "
               "--force\n")
        _write(tmp, BOARD_LOOP_FILE,
               "on: push\njobs:\n  covered:\n    runs-on: ubuntu-latest\n"
               "    steps:\n"
               "      - uses: ./.github/actions/wing-commander-board-labels\n"
               "        with:\n          token: ${{ env.WC_BOT_TOKEN }}\n"
               "      - shell: bash\n        run: |\n"
               "          gh pr create --title t --label board:owned\n")
        _write(tmp, ".github/workflows/some-other-workflow.yml",
               "on: push\njobs:\n  x:\n    runs-on: ubuntu-latest\n    steps:\n"
               "      - shell: bash\n        run: |\n"
               "          gh pr create --title t --label board:owned\n")
        findings, hard = evaluate(tmp)
        if hard:
            fail(f"[{case}] unexpected hard failure(s): {hard}")
            return
        covered_hit = any(f.job == "covered" for f in findings)
        other_hit = any(f.path == ".github/workflows/some-other-workflow.yml"
                         and f.job == "x" and f.label == "board:owned"
                         for f in findings)
        if covered_hit:
            fail(f"[{case}] the covered job calls the composite and should "
                 f"not have a finding: {findings}")
        elif not other_hit:
            fail(f"[{case}] expected a finding in the other file's job "
                 f"'x', got: {findings}")
        else:
            note(f"[{case}] passed")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def selftest_tier1_covers_board_star_in_every_workflow():
    case = "tier 1: a board:* label applied in ANY workflow (not just board-loop.yml) with no create fails"
    tmp = tempfile.mkdtemp(prefix="wc-board-label-")
    try:
        _write(tmp, BOARD_LOOP_FILE,
               "on: push\njobs:\n  y:\n    runs-on: ubuntu-latest\n    steps:\n"
               "      - shell: bash\n        run: |\n          echo noop\n")
        _write(tmp, ".github/workflows/some-other-workflow.yml",
               "on: push\njobs:\n  x:\n    runs-on: ubuntu-latest\n    steps:\n"
               "      - shell: bash\n        run: |\n"
               "          gh issue edit \"$N\" --add-label \"board:stalled\"\n")
        findings, hard = evaluate(tmp)
        _assert_finding_for(case, findings, hard, "board:stalled", job="x",
                             path=".github/workflows/some-other-workflow.yml")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def selftest_tier1_covers_board_star_in_composite_actions_too():
    case = "tier 1: a board:* label applied inside a composite action's own run: block, with no create, fails"
    tmp = tempfile.mkdtemp(prefix="wc-board-label-")
    try:
        _write(tmp, BOARD_LOOP_FILE,
               "on: push\njobs:\n  y:\n    runs-on: ubuntu-latest\n    steps:\n"
               "      - shell: bash\n        run: |\n          echo noop\n")
        _write(tmp, ".github/actions/some-other-composite/action.yml",
               "runs:\n  using: composite\n  steps:\n"
               "    - shell: bash\n      run: |\n"
               "        gh issue edit \"$N\" --add-label \"board:owned\"\n")
        findings, hard = evaluate(tmp)
        _assert_finding_for(case, findings, hard, "board:owned", job="runs",
                             path=".github/actions/some-other-composite/action.yml")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def selftest_tier1_ignores_a_non_board_label_elsewhere():
    case = "tier 1 does not check a non-board literal label in a file other than board-loop.yml"
    tmp = tempfile.mkdtemp(prefix="wc-board-label-")
    try:
        _write(tmp, BOARD_LOOP_FILE,
               "on: push\njobs:\n  y:\n    runs-on: ubuntu-latest\n    steps:\n"
               "      - shell: bash\n        run: |\n          echo noop\n")
        _write(tmp, ".github/workflows/some-other-workflow.yml",
               "on: push\njobs:\n  x:\n    runs-on: ubuntu-latest\n    steps:\n"
               "      - shell: bash\n        run: |\n"
               "          gh issue edit \"$N\" --add-label \"spec-request\"\n")
        findings, hard = evaluate(tmp)
        _assert_clean(case, findings, hard)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def selftest_board_loop_is_not_double_scanned_under_two_path_spellings():
    case = ("board-loop.yml is scanned exactly once, not once under "
            "BOARD_LOOP_FILE's own spelling and again via a leading "
            "'./' glob.glob(root='.') can hand back (a real finding "
            "would otherwise be reported twice)")
    tmp = tempfile.mkdtemp(prefix="wc-board-label-")
    try:
        _write(tmp, BOARD_LOOP_FILE,
               "on: push\njobs:\n  x:\n    runs-on: ubuntu-latest\n    steps:\n"
               "      - shell: bash\n        run: |\n"
               "          gh issue edit \"$N\" --add-label \"board:stalled\"\n")
        cwd = os.getcwd()
        try:
            os.chdir(tmp)
            findings, hard = evaluate(".")
        finally:
            os.chdir(cwd)
        if hard:
            fail(f"[{case}] unexpected hard failure(s): {hard}")
            return
        hits = [f for f in findings if f.label == "board:stalled" and f.job == "x"]
        if len(hits) != 1:
            fail(f"[{case}] expected exactly 1 finding, got {len(hits)}: {findings}")
        else:
            note(f"[{case}] passed ({hits[0].path})")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def selftest_one_job_missing_the_step_fails_its_sibling_passes():
    case = "one job lacking the step fails while a sibling job with it passes"
    tmp = tempfile.mkdtemp(prefix="wc-board-label-")
    try:
        _write(tmp, ".github/actions/wing-commander-board-labels/action.yml",
               "runs:\n  using: composite\n  steps:\n"
               "    - shell: bash\n      run: |\n"
               "        gh label create \"board:stalled\" --color B60205 "
               "--force\n")
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


def selftest_multiline_apply_label_on_a_continuation_line_still_detected():
    case = ("a --label flag on a continuation line, several lines below the "
            "gh issue create it belongs to, is still detected (board-loop"
            ".yml's own fix/readiness spec-request sites split the command "
            "across lines with trailing `\\`)")
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


def selftest_mid_line_command_switch_still_detects_the_real_apply():
    case = ("a read command earlier on the SAME line does not hide a real "
            "apply later on that line, split by `;` (`n=$(gh search issues "
            "x); gh issue create --label newlbl`)")
    tmp = tempfile.mkdtemp(prefix="wc-board-label-")
    try:
        _write(tmp, BOARD_LOOP_FILE,
               "on: push\njobs:\n  x:\n    runs-on: ubuntu-latest\n    steps:\n"
               "      - shell: bash\n        run: |\n"
               "          n=$(gh search issues x); gh issue create "
               "--title t --label newlbl\n")
        findings, hard = evaluate(tmp)
        _assert_finding_for(case, findings, hard, "newlbl", job="x")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def selftest_trailing_shell_comment_does_not_hide_a_real_apply():
    case = ("a trailing shell comment does not hide a real apply "
            "(`gh issue create --label newlbl # vs gh pr list`)")
    tmp = tempfile.mkdtemp(prefix="wc-board-label-")
    try:
        _write(tmp, BOARD_LOOP_FILE,
               "on: push\njobs:\n  x:\n    runs-on: ubuntu-latest\n    steps:\n"
               "      - shell: bash\n        run: |\n"
               "          gh issue create --title t --label newlbl "
               "# vs gh pr list\n")
        findings, hard = evaluate(tmp)
        _assert_finding_for(case, findings, hard, "newlbl", job="x")
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


def selftest_unparseable_board_loop_file_is_a_hard_failure():
    case = "board-loop.yml failing to parse as YAML is a hard failure, not a silent 0"
    tmp = tempfile.mkdtemp(prefix="wc-board-label-")
    try:
        _write(tmp, BOARD_LOOP_FILE, "on: push\njobs:\n  x:\n    steps: [\n")
        findings, hard = evaluate(tmp)
        if not hard:
            fail(f"[{case}] expected a hard failure, got: findings={findings} hard={hard}")
        else:
            note(f"[{case}] passed ({hard[0]})")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def selftest_unparseable_other_file_is_a_hard_failure():
    case = "a tier-1 file (not board-loop.yml) failing to parse as YAML is a hard failure, not a silent 0"
    tmp = tempfile.mkdtemp(prefix="wc-board-label-")
    try:
        _write(tmp, BOARD_LOOP_FILE,
               "on: push\njobs:\n  y:\n    runs-on: ubuntu-latest\n    steps:\n"
               "      - shell: bash\n        run: |\n          echo noop\n")
        _write(tmp, ".github/workflows/broken.yml", "on: push\njobs: [\n")
        findings, hard = evaluate(tmp)
        if not hard:
            fail(f"[{case}] expected a hard failure, got: findings={findings} hard={hard}")
        else:
            note(f"[{case}] passed ({hard[0]})")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# One fixture per extended apply form: each proves the form is actually
# detected, by omitting the create and expecting a finding -- a form the
# regexes miss would silently pass instead.
_APPLY_FORM_FIXTURES = [
    ("--add-label= form",
     "          gh issue edit \"$N\" --add-label=board:stalled\n"),
    ("comma-separated label list, board label in a non-first position",
     "          gh issue edit \"$N\" --add-label \"spec-request,board:stalled\"\n"),
    ("gh pr create -l short flag",
     "          gh pr create -R \"$R\" --title t -l board:owned\n"),
    ("gh issue create -l short flag",
     "          gh issue create -R \"$R\" --title t -l new-issue-label\n"),
    ("gh issue edit -l short flag",
     "          gh issue edit \"$N\" -R \"$R\" -l new-edit-label\n"),
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
                   "          gh label create \"new-issue-label\" --force\n"
                   "          gh label create \"new-edit-label\" --force\n"
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
    selftest_composite_creates_are_derived_not_hardcoded()
    selftest_composite_call_covers_later_applies()
    selftest_composite_call_after_apply_does_not_cover_it()
    selftest_cross_job_create_does_not_cover_apply()
    selftest_composite_create_in_another_file_does_not_cover_an_apply_that_never_calls_it()
    selftest_tier1_covers_board_star_in_every_workflow()
    selftest_tier1_covers_board_star_in_composite_actions_too()
    selftest_tier1_ignores_a_non_board_label_elsewhere()
    selftest_board_loop_is_not_double_scanned_under_two_path_spellings()
    selftest_one_job_missing_the_step_fails_its_sibling_passes()
    selftest_variable_label_is_ignored()
    selftest_comment_only_create_does_not_count()
    selftest_command_substitution_trailing_punctuation_still_matches()
    selftest_multiline_apply_label_on_a_continuation_line_still_detected()
    selftest_read_only_label_flag_is_not_an_apply()
    selftest_mid_line_command_switch_still_detects_the_real_apply()
    selftest_trailing_shell_comment_does_not_hide_a_real_apply()
    selftest_finding_line_number_is_exact_with_shared_first_lines()
    selftest_unparseable_board_loop_file_is_a_hard_failure()
    selftest_unparseable_other_file_is_a_hard_failure()
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
