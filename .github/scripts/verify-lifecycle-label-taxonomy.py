#!/usr/bin/env python3
"""Gate 105 -- every documented `stage:*` label either has a real writer or a
registered, reasoned exemption (FR-001/FR-007, specs/063-stage-clarify-label).

WHY THIS EXISTS
---------------
`docs/setup.md` documented `stage:clarify` ("Spec has open clarification
questions") for as long as this repository has had a clarify stage, but no
workflow ever applied or removed it -- a maintainer filtering issues by
`stage:clarify` found nothing, forever. Nothing caught this: it is not a
YAML error, not a broken `if:`, not a failed shell command. The label table
was simply describing a pipeline that did not exist. specs/063 traced it by
hand; this gate exists so the next documented-but-unwritten label fails a
pull request instead of waiting for another by-hand trace.

WHAT IT CHECKS
--------------
1. The DOCUMENTED set: every backtick-quoted `` `stage:[a-z-]+` `` token
   found anywhere in `docs/setup.md`, read fresh on every run -- never a
   hardcoded list (FR-007).
2. The APPLIED set: every literal `stage:[a-z-]+` token passed as an
   argument to an ADD-shaped call -- `gh issue edit --add-label`, `gh issue
   create --label`/`-l`, or a REST `-f "labels[]=..."` call -- across every
   `.github/workflows/*.yml` and every local `.github/actions/**/
   action.yml`, scanning both a step's `run:` shell text and, for an agent
   step, its `with.prompt` text (e.g. intake.yml's `stage:spec` add lives
   inside the Claude Code action's prompt, not a `run:` step -- maintainer
   feedback on PR #651). A bare `--remove-label` call does NOT put a label
   in this set on its own: removing a label is not evidence that anything
   ever adds it (Phase 7 convergence fix -- `plan.yml`'s pre-existing,
   unrelated best-effort `--remove-label "stage:clarify"` lines otherwise
   satisfied this gate for a label nothing ever added). This REIMPLEMENTS
   (never imports) Gate 90's (`verify-board-label-creation.py`)
   segmentation rules -- comment stripping, `;`/`&&`/`||`/`|`/`$(`
   splitting, backslash-continuation joining, quote handling, and the
   read/apply distinction that excludes a `--label`/`-l` argument to `gh
   issue list`/`gh pr list`/`gh search` -- because Gate 105 asks a strictly
   weaker question than Gate 90 does (does a writer exist ANYWHERE, never
   "does this job's own `gh label create` precede its own apply"), so
   importing Gate 90's job-ordering machinery would buy nothing.
3. The EXEMPTION REGISTRY: `.github/scripts/lifecycle-label-taxonomy-
   waivers.json`, parsed the same way Gate 31
   (`verify-stage-invariants.py`) parses `stage-invariant-waivers.json`:
   a missing file means zero waivers; a malformed file or an entry missing
   a required field is a hard failure naming the malformed entry, never a
   silent skip.

VERDICT
-------
PASS   every documented label is in the applied set, or covered by a
       shape-valid, non-stale waiver.
FAIL   a documented label is in neither the applied set nor the waiver
       registry -- named directly.
FAIL   a documented label is in the applied set AND ALSO has a waiver --
       stale by construction, nothing left to exempt.
FAIL   a waiver's `pattern` names a label `docs/setup.md` no longer
       documents, or whose `count` no longer matches the live count of
       documented mentions -- stale, either direction.
FAIL   the registry file is malformed, or an entry is missing a required
       field -- names the malformed entry.

Usage:
    python3 .github/scripts/verify-lifecycle-label-taxonomy.py
    python3 .github/scripts/verify-lifecycle-label-taxonomy.py --self-test

NOTE: the applied set counts only ADD-shaped sites (`--add-label`, `gh
issue create --label`/`-l`, a REST `-f "labels[]=..."` call). A bare
`--remove-label` site never satisfies "has a writer" on its own -- fixed
in this feature's Phase 7 convergence pass after `plan.yml`'s pre-existing
best-effort `--remove-label "stage:clarify"` lines were found to satisfy
the gate for a label nothing ever added.
"""
import glob
import json
import os
import re
import sys
import tempfile

import yaml

DOC_PATH = "docs/setup.md"
WORKFLOWS_DIR = ".github/workflows"
ACTIONS_DIR = ".github/actions"
WAIVERS_PATH = ".github/scripts/lifecycle-label-taxonomy-waivers.json"

STAGE_TOKEN_RE = re.compile(r'^stage:[a-z-]+$')
DOC_MENTION_RE = re.compile(r'`(stage:[a-z-]+)`')

REQUIRED_WAIVER_FIELDS = ("file", "check", "pattern", "count", "issue", "reason")
WAIVER_CHECK_NAME = "stage-label-writer"

# --------------------------------------------------------------------------
# Documented set (docs/setup.md)
# --------------------------------------------------------------------------
def documented_labels(root="."):
    """-> {label: mention_count}. Read fresh on every run -- never a
    hardcoded list (FR-007). Every backtick-quoted `stage:[a-z-]+` token
    anywhere in the file counts, table row or prose, deduplicated only for
    membership -- the raw count is what a waiver's `count` field is
    stale-checked against."""
    path = os.path.join(root, *DOC_PATH.split("/"))
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    counts = {}
    for m in DOC_MENTION_RE.finditer(text):
        counts[m.group(1)] = counts.get(m.group(1), 0) + 1
    return counts


# --------------------------------------------------------------------------
# Applied set -- Gate 90's segmentation rules, reimplemented (not imported)
# --------------------------------------------------------------------------
_VALUE = r'("[^"\n]*"|\'[^\'\n]*\'|[A-Za-z0-9_.,:=-]+)'
ADD_LABEL_VALUE_RE = re.compile(r'--add-label(?:=|\s+)' + _VALUE)
# `--remove-label` is intentionally NOT matched here -- a remove-only site
# is not a writer (Phase 7 convergence fix; see module docstring).
LABEL_FLAG_VALUE_RE = re.compile(r'--label(?:=|\s+)' + _VALUE)
SHORT_LABEL_VALUE_RE = re.compile(r'-l(?:=|\s+)' + _VALUE)
_LABEL_SHORT_FLAG_COMMANDS = ("gh pr create", "gh issue create", "gh issue edit")
REST_LABEL_VALUE_RE = re.compile(
    r'-f\s+("labels\[\]=[^"\n]*"|\'labels\[\]=[^\'\n]*\'|labels\[\]=[A-Za-z0-9_.,:=-]+)')

# A command that filters BY a label rather than applying one -- same
# `--label` spelling as a real apply. Checked per command segment, never
# per line (Gate 90's own reasoning: a line can hold more than one shell
# command, and a real apply can trail a read command's own `--label`).
_LABEL_READ_COMMAND_RE = re.compile(r'gh\s+(issue|pr)\s+list\b|gh\s+search\b')

_CMD_SPLIT_RE = re.compile(r'&&|\|\||[;|]|\$\(')


def _is_comment_line(line):
    return line.strip().startswith("#")


def _strip_trailing_comment(line):
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
    if not stripped.endswith("\\"):
        return False
    count = 0
    i = len(stripped) - 1
    while i >= 0 and stripped[i] == "\\":
        count += 1
        i -= 1
    return count % 2 == 1


def _line_segments(line):
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


def _labels_in_value(raw):
    """A flag's value may be a single label or a comma-separated list."""
    raw = _unquote(raw)
    labels = []
    for token in raw.split(","):
        token = _unquote(token.strip())
        if STAGE_TOKEN_RE.match(token):
            labels.append(token)
    return labels


def _labels_applied_in_segment(seg_text, is_read):
    """Every literal `stage:*` label one command SEGMENT ADDS -- never a
    bare `--remove-label` site (Phase 7 convergence fix). `--add-label`
    has no read-command spelling in this repository, so it is never
    suppressed by `is_read`; only the bare `--label` flag (shared with
    `gh issue list`/`gh search`) is."""
    labels = []
    for m in ADD_LABEL_VALUE_RE.finditer(seg_text):
        labels.extend(_labels_in_value(m.group(1)))
    if not is_read:
        for m in LABEL_FLAG_VALUE_RE.finditer(seg_text):
            labels.extend(_labels_in_value(m.group(1)))
    if any(cmd in seg_text for cmd in _LABEL_SHORT_FLAG_COMMANDS):
        for m in SHORT_LABEL_VALUE_RE.finditer(seg_text):
            labels.extend(_labels_in_value(m.group(1)))
    for m in REST_LABEL_VALUE_RE.finditer(seg_text):
        raw = _unquote(m.group(1))
        if raw.startswith("labels[]="):
            labels.extend(_labels_in_value(raw[len("labels[]="):]))
    return labels


def _labels_applied_in_run(run_text):
    """Every literal `stage:*` label a step's `run:` block ADDS anywhere
    in it -- no job-ordering or same-job requirement (Gate 105's non-goal:
    a strictly weaker property than Gate 90's)."""
    found = set()
    carry_open = False
    carry_is_read = False
    for raw_line in run_text.split("\n"):
        if _is_comment_line(raw_line):
            carry_open = False
            carry_is_read = False
            continue
        line = _strip_trailing_comment(raw_line)
        stripped = line.rstrip()
        continues = _is_line_continuation(stripped)
        body = stripped[:-1] if continues else stripped
        segments = _line_segments(body)
        last_is_read = carry_is_read
        for i, seg_text in enumerate(segments):
            if i == 0 and carry_open:
                is_read = carry_is_read
            else:
                is_read = bool(_LABEL_READ_COMMAND_RE.search(seg_text))
            found.update(_labels_applied_in_segment(seg_text, is_read))
            last_is_read = is_read
        carry_open = continues
        carry_is_read = last_is_read
    return found


def _step_lists(doc):
    """Every [steps] list in a workflow (each job) or a composite action
    (`runs.steps`)."""
    if not isinstance(doc, dict):
        return []
    out = []
    for job in (doc.get("jobs") or {}).values():
        out.append((job or {}).get("steps") or [])
    runs = doc.get("runs") or {}
    if runs.get("steps"):
        out.append(runs["steps"])
    return out


def _subject_files(root="."):
    workflows = sorted(glob.glob(os.path.join(root, WORKFLOWS_DIR, "*.yml"))
                        + glob.glob(os.path.join(root, WORKFLOWS_DIR, "*.yaml")))
    actions = []
    base = os.path.join(root, ACTIONS_DIR)
    for dirpath, _dirs, names in os.walk(base):
        for name in names:
            if name in ("action.yml", "action.yaml"):
                actions.append(os.path.join(dirpath, name))
    return sorted(workflows) + sorted(actions)


class GateParseError(Exception):
    """A subject file could not be parsed as YAML -- a hard failure, never
    a silent 0 (the same reasoning every other verify-*.py gate applies)."""


def applied_labels(root="."):
    """-> set of every literal `stage:*` label ADDED anywhere across every
    workflow and local composite action -- a bare `--remove-label` site
    does not count (Phase 7 convergence fix). Scans both a step's `run:`
    shell text and, for an agent step, its `with.prompt` text (e.g.
    intake.yml's `gh issue edit --add-label "spec:<NNN-slug>,stage:spec"`
    instruction, which lives inside the Claude Code action's prompt, not a
    `run:` step) -- reusing the same segmentation and comma-list parsing
    for both (maintainer feedback on PR #651)."""
    found = set()
    for path in _subject_files(root):
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        try:
            doc = yaml.safe_load(text) or {}
        except yaml.YAMLError as exc:
            raise GateParseError(f"{path}: could not be parsed as YAML ({exc})") from exc
        for steps in _step_lists(doc):
            for step in steps:
                run = str((step or {}).get("run") or "")
                if run:
                    found.update(_labels_applied_in_run(run))
                prompt = str(((step or {}).get("with") or {}).get("prompt") or "")
                if prompt:
                    found.update(_labels_applied_in_run(prompt))
    return found


# --------------------------------------------------------------------------
# Exemption registry
# --------------------------------------------------------------------------
def load_waivers(root="."):
    """-> (waivers, failures). A missing file means zero waivers -- the
    state this feature ships in. Unreadable or malformed is reported, not
    silenced (mirrors Gate 31's `load_waivers`)."""
    path = os.path.join(root, *WAIVERS_PATH.split("/"))
    if not os.path.isfile(path):
        return [], []
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (ValueError, OSError) as exc:
        return [], [f"{WAIVERS_PATH} could not be read ({exc}). A waiver file "
                    f"that does not parse would otherwise silently waive "
                    f"nothing while looking like a register."]
    waivers = data.get("waivers") if isinstance(data, dict) else data
    if not isinstance(waivers, list):
        return [], [f'{WAIVERS_PATH} must contain a "waivers" list.']
    failures = []
    shape_valid = []
    for index, waiver in enumerate(waivers):
        where = f"{WAIVERS_PATH} entry {index}"
        if not isinstance(waiver, dict):
            failures.append(f"{where} is not an object.")
            continue
        missing = [f for f in REQUIRED_WAIVER_FIELDS if not waiver.get(f)]
        if missing:
            failures.append(
                f"{where} ({waiver.get('pattern', '?')}) is missing "
                f"{', '.join(missing)}. Every waiver names the file, the "
                f"check, the exact label pattern, the documented-mention "
                f"count it covers, the tracking issue and the reason -- an "
                f"exception nobody can inspect is indistinguishable from a "
                f"bug someone silenced.")
            continue
        if waiver["check"] != WAIVER_CHECK_NAME:
            failures.append(
                f"{where} waives check {waiver['check']!r}, which is not "
                f"{WAIVER_CHECK_NAME!r} -- the only check this gate grants "
                f"exemptions for.")
            continue
        if not STAGE_TOKEN_RE.match(str(waiver["pattern"])):
            failures.append(
                f"{where} pattern {waiver['pattern']!r} is not a "
                f"`stage:<name>` label.")
            continue
        if not isinstance(waiver["count"], int):
            failures.append(f"{where} count must be an integer, got "
                            f"{waiver['count']!r}.")
            continue
        shape_valid.append(waiver)
    return shape_valid, failures


def evaluate(root="."):
    """-> list of failure strings."""
    failures = []
    documented = documented_labels(root)
    try:
        applied = applied_labels(root)
    except GateParseError as exc:
        return [str(exc)]

    waivers, waiver_failures = load_waivers(root)
    failures.extend(waiver_failures)

    waived_by_label = {}
    for waiver in waivers:
        label = waiver["pattern"]
        where = f"{WAIVERS_PATH} waiver for {label}"
        if label in applied:
            failures.append(
                f"{where} exempts a label that IS in the applied set -- "
                f"stale by construction, nothing left to exempt. Remove "
                f"the waiver (tracking issue {waiver['issue']}).")
            continue
        if label not in documented:
            failures.append(
                f"{where} names a label {DOC_PATH} no longer documents. "
                f"Stale in the direction of a removed mention -- remove "
                f"the waiver (tracking issue {waiver['issue']}).")
            continue
        live_count = documented[label]
        if live_count != waiver["count"]:
            failures.append(
                f"{where} declares {waiver['count']} documented mention(s), "
                f"but {DOC_PATH} currently has {live_count}. Stale either "
                f"direction -- update the count deliberately or remove the "
                f"waiver (tracking issue {waiver['issue']}).")
            continue
        waived_by_label[label] = waiver

    for label in sorted(documented):
        if label in applied or label in waived_by_label:
            continue
        failures.append(
            f"{label} is documented in {DOC_PATH} but no workflow or local "
            f"composite action ever adds it anywhere (FR-001) -- and no "
            f"waiver in {WAIVERS_PATH} exempts it. A bare `--remove-label` "
            f"site does not count as a writer. Wire up a writer, drop it "
            f"from {DOC_PATH}, or add a waiver naming why it is documented "
            f"on purpose with no writer.")

    return failures


def main():
    failures = evaluate()
    for f in failures:
        print(f"::error::Gate 105: {f}")
    print(f"Gate 105: lifecycle label taxonomy check; {len(failures)} failure(s).")
    return 1 if failures else 0


# --------------------------------------------------------------------------
# Self-test -- the seven required fixtures (contracts/lifecycle-label-
# taxonomy-gate.md), each a synthetic root under tempfile.mkdtemp()
# --------------------------------------------------------------------------
def _write(root, relpath, content):
    path = os.path.join(root, *relpath.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)


def _fresh_root():
    root = tempfile.mkdtemp(prefix="verify_gate105_")
    os.makedirs(os.path.join(root, WORKFLOWS_DIR), exist_ok=True)
    os.makedirs(os.path.join(root, ACTIONS_DIR), exist_ok=True)
    os.makedirs(os.path.join(root, os.path.dirname(WAIVERS_PATH)), exist_ok=True)
    return root


DOC_NO_WRITER = """\
# Setup

| Label | Purpose |
|---|---|
| `stage:clarify` | Spec has open clarification questions |
"""

WORKFLOW_NO_WRITER = """\
name: intake
on:
  workflow_call: {}
jobs:
  intake:
    runs-on: ubuntu-latest
    steps:
      - name: Do something unrelated
        run: |
          echo "no label writes here"
"""

WORKFLOW_WITH_WRITER = """\
name: intake
on:
  workflow_call: {}
jobs:
  intake:
    runs-on: ubuntu-latest
    steps:
      - name: Flip stage label for clarification
        run: |
          gh label create "stage:clarify" --color 1D76DB --force
          gh issue edit "$ISSUE" --add-label "stage:clarify"
"""

DOC_TWO_LABELS = """\
# Setup

| Label | Purpose |
|---|---|
| `stage:clarify` | Spec has open clarification questions |
| `stage:spec` | Spec is being drafted / awaiting review |
"""

WORKFLOW_ONE_WRITER = """\
name: intake
on:
  workflow_call: {}
jobs:
  intake:
    runs-on: ubuntu-latest
    steps:
      - name: Flip stage label
        run: |
          gh issue edit "$ISSUE" --add-label "stage:spec"
"""

WORKFLOW_REMOVE_ONLY = """\
name: plan
on:
  workflow_call: {}
jobs:
  plan:
    runs-on: ubuntu-latest
    steps:
      - name: Best-effort remove, no add anywhere
        run: |
          gh issue edit "$ISSUE" --remove-label "stage:clarify" 2>/dev/null || true
"""

DOC_PROMPT_LABEL = """\
# Setup

| Label | Purpose |
|---|---|
| `stage:spec` | Spec drafted / awaiting review |
"""

WORKFLOW_PROMPT_ONLY_WRITER = """\
name: intake
on:
  workflow_call: {}
jobs:
  intake:
    runs-on: ubuntu-latest
    steps:
      - name: Create spec from issue
        uses: anthropics/claude-code-action@v1
        with:
          prompt: |
            7. Update the lifecycle issue:
               - gh issue edit --add-label "spec:<NNN-slug>,stage:spec"
"""


def self_test():
    failed = []

    def check(label, build, expect_fail, name_fragment=None):
        root = _fresh_root()
        try:
            build(root)
            fs = evaluate(root)
        finally:
            import shutil
            shutil.rmtree(root, ignore_errors=True)
        fired = len(fs) > 0
        if fired != expect_fail:
            failed.append(f"{label}: expected the gate to "
                          f"{'FAIL' if expect_fail else 'PASS'}, it "
                          f"{'FAILED' if fired else 'PASSED'} ({fs!r})")
            return
        if expect_fail and name_fragment:
            if not any(name_fragment in f for f in fs):
                failed.append(f"{label}: failed, but not naming "
                              f"{name_fragment!r} ({fs!r})")
                return
        print(f"ok    {label}")

    # 1. The regression this feature fixes: documented, zero writers, zero
    #    waiver -- FR-008's permanently pinned demonstration.
    def build_1(root):
        _write(root, DOC_PATH, DOC_NO_WRITER)
        _write(root, f"{WORKFLOWS_DIR}/intake.yml", WORKFLOW_NO_WRITER)

    check("(1) documented label with no writer and no waiver fails, naming it",
          build_1, expect_fail=True, name_fragment="stage:clarify")

    # 2. A documented label with a valid, exact waiver -- PASS.
    def build_2(root):
        _write(root, DOC_PATH, DOC_NO_WRITER)
        _write(root, f"{WORKFLOWS_DIR}/intake.yml", WORKFLOW_NO_WRITER)
        _write(root, WAIVERS_PATH, json.dumps({"waivers": [{
            "file": "docs/setup.md", "check": "stage-label-writer",
            "pattern": "stage:clarify", "count": 1, "issue": 999,
            "reason": "synthetic fixture: exercised on purpose, no real writer",
        }]}))

    check("(2) a valid, exact waiver passes", build_2, expect_fail=False)

    # 3. A stale waiver whose labeled deviation now has a writer -- FAIL.
    def build_3(root):
        _write(root, DOC_PATH, DOC_NO_WRITER)
        _write(root, f"{WORKFLOWS_DIR}/intake.yml", WORKFLOW_WITH_WRITER)
        _write(root, WAIVERS_PATH, json.dumps({"waivers": [{
            "file": "docs/setup.md", "check": "stage-label-writer",
            "pattern": "stage:clarify", "count": 1, "issue": 999,
            "reason": "now stale: a writer was added after this waiver",
        }]}))

    check("(3) a waiver for a label that now has a writer fails (stale)",
          build_3, expect_fail=True, name_fragment="applied set")

    # 4. A waiver whose count no longer matches -- FAIL.
    def build_4(root):
        _write(root, DOC_PATH, DOC_NO_WRITER)
        _write(root, f"{WORKFLOWS_DIR}/intake.yml", WORKFLOW_NO_WRITER)
        _write(root, WAIVERS_PATH, json.dumps({"waivers": [{
            "file": "docs/setup.md", "check": "stage-label-writer",
            "pattern": "stage:clarify", "count": 5, "issue": 999,
            "reason": "count deliberately wrong for this fixture",
        }]}))

    check("(4) a waiver whose count no longer matches fails (stale)",
          build_4, expect_fail=True, name_fragment="documented mention")

    # 5. A new documented label with no writer -- FAIL, naming the new label.
    def build_5(root):
        _write(root, DOC_PATH, DOC_TWO_LABELS)
        _write(root, f"{WORKFLOWS_DIR}/intake.yml", WORKFLOW_ONE_WRITER)

    check("(5) a new documented label with no writer fails, naming it",
          build_5, expect_fail=True, name_fragment="stage:clarify")

    # 6. A workflow change that deletes the only apply site for a
    #    documented label, leaving the OTHER documented label's writer
    #    intact -- FAIL, naming only the one whose site was deleted.
    def build_6(root):
        _write(root, DOC_PATH, DOC_TWO_LABELS)
        _write(root, f"{WORKFLOWS_DIR}/intake.yml", WORKFLOW_WITH_WRITER)

    check("(6) deleting the only apply site for a documented label fails, naming it",
          build_6, expect_fail=True, name_fragment="stage:spec")

    # 7. A malformed waivers file (missing required field) -- FAIL, names
    #    the malformed entry, distinct from cases 1/5.
    def build_7(root):
        _write(root, DOC_PATH, DOC_NO_WRITER)
        _write(root, f"{WORKFLOWS_DIR}/intake.yml", WORKFLOW_NO_WRITER)
        _write(root, WAIVERS_PATH, json.dumps({"waivers": [{
            "file": "docs/setup.md", "check": "stage-label-writer",
            "pattern": "stage:clarify", "count": 1,
            # "issue" and "reason" deliberately omitted.
        }]}))

    check("(7) a malformed waivers file fails, naming the malformed entry",
          build_7, expect_fail=True, name_fragment="entry 0")

    # 8. A remove-only site with no add anywhere -- FAIL, naming it. The
    #    Phase 7 convergence fixture: `plan.yml`'s pre-existing best-effort
    #    `--remove-label "stage:clarify"` lines must not, on their own,
    #    read as a writer.
    def build_8(root):
        _write(root, DOC_PATH, DOC_NO_WRITER)
        _write(root, f"{WORKFLOWS_DIR}/intake.yml", WORKFLOW_REMOVE_ONLY)

    check("(8) a remove-only site with no add anywhere still fails, naming it",
          build_8, expect_fail=True, name_fragment="stage:clarify")

    # 9. A `with.prompt`-only writer (no `run:` shell site at all) counts
    #    as a writer -- PASS. Maintainer feedback on PR #651: intake.yml's
    #    real `stage:spec` add lives inside the Claude Code action's
    #    prompt text, not a `run:` step, and was invisible to the scanner
    #    before this fixture's corresponding fix.
    def build_9(root):
        _write(root, DOC_PATH, DOC_PROMPT_LABEL)
        _write(root, f"{WORKFLOWS_DIR}/intake.yml", WORKFLOW_PROMPT_ONLY_WRITER)

    check("(9) a with.prompt-only writer counts as a writer",
          build_9, expect_fail=False)

    if failed:
        print(f"::error::Gate 105 self-test: {len(failed)} check(s) behaved "
              f"wrongly: {'; '.join(failed)}. Gate 105's detection logic does "
              f"not do what its name claims, so a green Gate 105 on the real "
              f"fleet means nothing.")
        return 1
    print("Gate 105 self-test: all 9 checks behaved as expected.")
    return 0


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(self_test())
    sys.exit(main())
