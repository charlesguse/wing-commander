#!/usr/bin/env python3
"""Gate 120 -- the dedup key's rule stays doc-and-code synchronized, and
spec 076's key composition stays deliberately split from spec 057's
(specs/076-stable-finding-dedup-key, FR-012/FR-015, contracts/gates.md).

WHY THIS EXISTS
---------------
specs/056-stage-found-defect-filing's data-model.md states the dedup-key
formula in a fenced block as the rule's ONE canonical home (FR-012); the
shipped code that actually computes the key lives in a different file
entirely (wing-commander-stage-findings/action.yml's "Extract, validate,
cap, and prepare findings" step). Nothing keeps the two in lockstep --
an edit to either side with no matching edit to the other would silently
drift, and the next agent to read the doc would be reading a rule the
code no longer implements. `verify-single-home-idioms.py`'s whole shape
(and `verify-metrics-summary-record-emission.py`'s) is "the declared home
has no second copy"; this is the same idea turned around: the DECLARED
copy (the doc's fenced block) must stay byte-consistent with the SHIPPED
copy (the action's code), not merely exist once each.

Separately, FR-015 asks for the opposite polarity: spec 057's own
fingerprint (keyed by issue number -- computed by `board-loop.yml`'s
"Prepare out-of-scope findings for filing" step, whose formula's single
home is `.github/scripts/wc_review_finding_fingerprint.py` since
specs/062-lifecycle-review-gate T028/T029) and this feature's two shapes must
NOT converge on one formula, and each must keep its own distinguishing
ingredient (this feature's `anchor|`/`fallback|` tag; spec 057's
issue-number segment). Bundled into this one script rather than a fifth
gate file, per CLAUDE.md's "extend the nearest existing gate" line --
both checks share the same extraction technique and both hold a
key-composition question in place, just in opposite directions.

NOTE ON GATE NUMBERING: shipped as Gate 120. It was written as Gate 99,
but main's Gates 99/100/116 and the numbers allocated to other in-flight
specs (101-119) were taken first; #660 tracks the allocation problem.

WHAT IT CHECKS
--------------
check_canonical_rule_sync (FR-012): every literal ingredient the doc's
fenced formula names -- the `norm()` regex `[\\W_]+`, the `anchor|` and
`fallback|` shape tags, and each shape's pipe-delimited segment count --
appears verbatim in the shipped step. Fails loudly, naming which literal
is missing and from which side, on any divergence; fails loudly (never
"0 checked, pass") if either source file is missing or the fenced block
cannot be found.

check_composition_split (FR-015): extracts this feature's own two shipped
format-string literals from the action step, and spec 057's shipped
format-string literal from wc_review_finding_fingerprint.py -- and fails
if board-loop.yml's step no longer calls that module's fingerprint(), so
the check still reaches the formula board-loop really runs rather than an
orphaned file. Fails if either extraction
cannot find its own distinguishing ingredient (this feature's `anchor|`/
`fallback|` tag; spec 057's `issue_number` as the first `.format()`
argument) or if spec 057's literal template is textually identical to
either of this feature's two.

Extraction uses `find_step`, the same helper
`.github/scripts/stage-findings-tests/run_fixtures.py` already uses to
pull a shipped `run:` block out of a workflow or composite action by step
name -- no second, drifting YAML parse of the same files (CLAUDE.md
"Shared logic has exactly one home").

USAGE
-----
    python3 .github/scripts/verify-dedup-key-canonical-rule.py
    python3 .github/scripts/verify-dedup-key-canonical-rule.py --self-test
"""
import argparse
import os
import re
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_shell_harness import find_step, use_utf8_stdout  # noqa: E402

ACTION_FILE = os.path.join(
    ".github", "actions", "wing-commander-stage-findings", "action.yml")
ACTION_STEP_NAME = "Extract, validate, cap, and prepare findings"
DATA_MODEL_FILE = os.path.join(
    "specs", "056-stage-found-defect-filing", "data-model.md")
BOARD_LOOP_FILE = os.path.join(".github", "workflows", "board-loop.yml")
BOARD_LOOP_STEP_NAME = "Prepare out-of-scope findings for filing"
# specs/062-lifecycle-review-gate T028: the single home of spec 057's
# formula; board-loop.yml's step imports fingerprint() from it.
SPEC057_HOME_FILE = os.path.join(".github", "scripts", "wc_review_finding_fingerprint.py")
BOARD_LOOP_CALL_RE = re.compile(
    r'from\s+wc_review_finding_fingerprint\s+import\s+fingerprint\b')

NORM_REGEX_LITERAL = r"[\W_]+"
ANCHOR_TAG = "anchor|"
FALLBACK_TAG = "fallback|"

WITH_ANCHOR_FORMULA_RE = re.compile(
    r'with-anchor key\s*=\s*sha256\("([^"]*)"\)')
FALLBACK_FORMULA_RE = re.compile(
    r'fallback key\s*=\s*sha256\("([^"]*)"\)')

ANCHOR_LITERAL_RE = re.compile(r'"(anchor\|[^"]*)"')
FALLBACK_LITERAL_RE = re.compile(r'"(fallback\|[^"]*)"')
SPEC057_LITERAL_RE = re.compile(
    r'hashlib\.sha256\("([^"]*)"\.format\(\s*issue_number\b')

failures = []


def fail(msg):
    failures.append(msg)
    print(f"::error::verify-dedup-key-canonical-rule: {msg}")


def note(msg):
    print(f"note: {msg}")


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _fenced_fingerprint_block(root):
    """The fenced block immediately under data-model.md's '## Fingerprint'
    heading -- T006's canonical home for the doc-side formula. Returns
    None (never raises) if the file, the heading, or the fence is
    missing, so callers can fail loudly through their own fail()."""
    path = os.path.join(root, DATA_MODEL_FILE)
    if not os.path.isfile(path):
        return None, path
    text = _read(path)
    m = re.search(r"## Fingerprint\b.*?```\n(.*?)```", text, re.S)
    return (m.group(1) if m else None), path


def _action_step_text(root):
    path = os.path.join(root, ACTION_FILE)
    if not os.path.isfile(path):
        return None, path
    return find_step(path, ACTION_STEP_NAME)["run"], path


def _board_loop_step_text(root):
    path = os.path.join(root, BOARD_LOOP_FILE)
    if not os.path.isfile(path):
        return None, path
    return find_step(path, BOARD_LOOP_STEP_NAME)["run"], path


def check_canonical_rule_sync(root="."):
    """FR-012: the doc's fenced formula and the shipped code stay in sync."""
    found = []

    def local_fail(msg):
        found.append(msg)
        fail(msg)

    doc_block, doc_path = _fenced_fingerprint_block(root)
    if doc_block is None:
        local_fail(f"could not find data-model.md's '## Fingerprint' fenced "
                   f"formula block at {doc_path} -- cannot check doc/code "
                   f"sync at all (FR-012).")
        return found

    code_text, code_path = _action_step_text(root)
    if code_text is None:
        local_fail(f"could not find {ACTION_FILE} to check against the "
                   f"data-model.md formula (FR-012).")
        return found

    if NORM_REGEX_LITERAL not in doc_block:
        local_fail(f"data-model.md's Fingerprint block no longer states the "
                   f"norm() regex {NORM_REGEX_LITERAL!r} -- the doc side of "
                   f"FR-012's sync has drifted.")
    if NORM_REGEX_LITERAL not in code_text:
        local_fail(f"{ACTION_FILE}'s {ACTION_STEP_NAME!r} step no longer "
                   f"uses the norm() regex {NORM_REGEX_LITERAL!r} that "
                   f"data-model.md's Fingerprint block states -- the code "
                   f"side of FR-012's sync has drifted.")

    for tag, label in ((ANCHOR_TAG, "anchor|"), (FALLBACK_TAG, "fallback|")):
        in_doc = tag in doc_block
        in_code = tag in code_text
        if not in_doc:
            local_fail(f"data-model.md's Fingerprint block no longer states "
                       f"the {label!r} shape tag (FR-012).")
        if not in_code:
            local_fail(f"{ACTION_FILE}'s {ACTION_STEP_NAME!r} step no "
                       f"longer carries the {label!r} shape tag that "
                       f"data-model.md's Fingerprint block states "
                       f"(FR-012).")

    doc_anchor_m = WITH_ANCHOR_FORMULA_RE.search(doc_block)
    doc_fallback_m = FALLBACK_FORMULA_RE.search(doc_block)
    code_anchor_m = ANCHOR_LITERAL_RE.search(code_text)
    code_fallback_m = FALLBACK_LITERAL_RE.search(code_text)

    # One home: the step computes the fingerprint in exactly one place
    # (finding_fingerprint()), which both the filing slots and the
    # lifecycle checklist items call. A second copy of either format
    # literal is a pasted computation that can drift from the first.
    for label, regex in (("anchor|", ANCHOR_LITERAL_RE), ("fallback|", FALLBACK_LITERAL_RE)):
        count = len(regex.findall(code_text))
        if count > 1:
            local_fail(f"{ACTION_FILE}'s {ACTION_STEP_NAME!r} step carries {count} "
                       f"{label!r}-tagged format literals; the fingerprint has one "
                       f"home, finding_fingerprint() -- call it instead of pasting "
                       f"the computation.")

    if doc_anchor_m and code_anchor_m:
        doc_pipes = doc_anchor_m.group(1).count("|")
        code_pipes = code_anchor_m.group(1).count("|")
        if doc_pipes != code_pipes:
            local_fail(
                f"the with-anchor formula's pipe-delimited segment count "
                f"differs between data-model.md ({doc_pipes} pipes: "
                f"{doc_anchor_m.group(1)!r}) and {ACTION_FILE} ({code_pipes} "
                f"pipes: {code_anchor_m.group(1)!r}) (FR-012).")
    elif doc_anchor_m and not code_anchor_m:
        local_fail(f"{ACTION_FILE} carries no {ANCHOR_TAG!r}-tagged format "
                   f"literal to compare against data-model.md's with-anchor "
                   f"formula (FR-012).")

    if doc_fallback_m and code_fallback_m:
        doc_pipes = doc_fallback_m.group(1).count("|")
        code_pipes = code_fallback_m.group(1).count("|")
        if doc_pipes != code_pipes:
            local_fail(
                f"the fallback formula's pipe-delimited segment count "
                f"differs between data-model.md ({doc_pipes} pipes: "
                f"{doc_fallback_m.group(1)!r}) and {ACTION_FILE} "
                f"({code_pipes} pipes: {code_fallback_m.group(1)!r}) "
                f"(FR-012).")
    elif doc_fallback_m and not code_fallback_m:
        local_fail(f"{ACTION_FILE} carries no {FALLBACK_TAG!r}-tagged "
                   f"format literal to compare against data-model.md's "
                   f"fallback formula (FR-012).")

    if not found:
        note("check_canonical_rule_sync: data-model.md's Fingerprint "
             "formula and the shipped step agree.")
    return found


def check_composition_split(root="."):
    """FR-015: this feature's key composition and spec 057's must keep
    differing, each for its own reason."""
    found = []

    def local_fail(msg):
        found.append(msg)
        fail(msg)

    code_text, code_path = _action_step_text(root)
    if code_text is None:
        local_fail(f"could not find {ACTION_FILE} to extract this "
                   f"feature's own formula from (FR-015).")
        return found

    board_text, board_path = _board_loop_step_text(root)
    if board_text is None:
        local_fail(f"could not find {BOARD_LOOP_FILE}'s "
                   f"{BOARD_LOOP_STEP_NAME!r} step, which computes spec "
                   f"057's own fingerprint (FR-015).")
        return found
    if not BOARD_LOOP_CALL_RE.search(board_text):
        local_fail(f"{BOARD_LOOP_FILE}'s {BOARD_LOOP_STEP_NAME!r} step no "
                   f"longer imports fingerprint() from "
                   f"{SPEC057_HOME_FILE} -- spec 057's formula has left its "
                   f"single home, so checking that file would no longer "
                   f"check what board-loop runs (FR-015).")
        return found
    home_path = os.path.join(root, SPEC057_HOME_FILE)
    if not os.path.isfile(home_path):
        local_fail(f"could not find {SPEC057_HOME_FILE} to extract spec "
                   f"057's own formula from (FR-015).")
        return found
    home_text = _read(home_path)

    anchor_m = ANCHOR_LITERAL_RE.search(code_text)
    fallback_m = FALLBACK_LITERAL_RE.search(code_text)
    if not anchor_m and not fallback_m:
        local_fail(f"{ACTION_FILE} carries neither an {ANCHOR_TAG!r}- nor "
                   f"a {FALLBACK_TAG!r}-tagged format literal -- this "
                   f"feature's own distinguishing ingredient is missing, "
                   f"so FR-015's split cannot be checked (#569).")
        return found

    spec057_m = SPEC057_LITERAL_RE.search(home_text)
    if not spec057_m:
        local_fail(
            f"{SPEC057_HOME_FILE} no longer "
            f"formats its fingerprint with `issue_number` as the first "
            f".format() argument -- spec 057's own distinguishing "
            f"ingredient (the issue-number segment) is missing, so FR-015 "
            f"requires this feature's and spec 057's formulas to keep "
            f"differing, and that can no longer be checked (#569).")
        return found

    spec057_literal = spec057_m.group(1)
    this_feature_literals = [m.group(1) for m in (anchor_m, fallback_m) if m]
    collided = [lit for lit in this_feature_literals if lit == spec057_literal]
    if collided:
        local_fail(
            f"FR-015 requires this feature's key composition and spec "
            f"057's to keep differing, but {SPEC057_HOME_FILE}'s formula "
            f"{spec057_literal!r} is textually identical to this "
            f"feature's own {collided[0]!r} in {ACTION_FILE} -- the two "
            f"have silently converged.")

    if not found:
        note("check_composition_split: this feature's key composition and "
             "spec 057's own formula still keep their own, deliberately "
             "differing ingredients (FR-015).")
    return found


def evaluate(root="."):
    failures.clear()
    found = []
    found += check_canonical_rule_sync(root)
    found += check_composition_split(root)
    return found


# ----------------------------------------------------------------------------
# --self-test
# ----------------------------------------------------------------------------
ACTION_TEMPLATE = """name: wing-commander-stage-findings
runs:
  using: composite
  steps:
    - name: Extract, validate, cap, and prepare findings
      run: |
        # norm() collapses every match of the regex {norm_regex} to one space.
        fp = hashlib.sha256("{anchor_literal}".format(
            STAGE, norm_path, norm_gate
        ).encode("utf-8")).hexdigest()
        fp = hashlib.sha256("{fallback_literal}".format(
            STAGE, norm_path
        ).encode("utf-8")).hexdigest()
"""

DATA_MODEL_TEMPLATE = """# Data Model

## Fingerprint

Some prose.

```
{norm_line}
with-anchor key  = sha256("{anchor_formula}")
fallback key     = sha256("{fallback_formula}")
```

More prose.
"""

BOARD_LOOP_TEMPLATE = """on:
  workflow_call: {{}}
jobs:
  x:
    runs-on: ubuntu-latest
    steps:
      - name: Prepare out-of-scope findings for filing
        run: |
          {import_line}
          fp = fingerprint(issue_number, title, file_path)
"""

GOOD_IMPORT_LINE = "from wc_review_finding_fingerprint import fingerprint"

SPEC057_HOME_TEMPLATE = """import hashlib


def fingerprint(issue_number, title, file_path):
    return hashlib.sha256("{spec057_literal}".format(
        {spec057_format_args}
    ).encode("utf-8")).hexdigest()
"""

GOOD_NORM_LINE = r"norm(s) = lowercase(s); regex [\W_]+ collapses to one space; trimmed"
GOOD_ANCHOR_LITERAL = "anchor|{0}|{1}|{2}"
GOOD_FALLBACK_LITERAL = "fallback|{0}|{1}"
GOOD_ANCHOR_FORMULA = "anchor|<stage>|<norm(fingerprint_basis.file_path)>|<norm(fingerprint_basis.gate_or_artifact)>"
GOOD_FALLBACK_FORMULA = "fallback|<stage>|<norm(fingerprint_basis.file_path)>"
GOOD_SPEC057_LITERAL = "{0}|{1}|{2}"


GOOD_SPEC057_FORMAT_ARGS = 'issue_number, norm(title), norm(file_path)'


def _write_fixture(root, norm_regex=r"[\W_]+", anchor_literal=GOOD_ANCHOR_LITERAL,
                   fallback_literal=GOOD_FALLBACK_LITERAL, norm_line=GOOD_NORM_LINE,
                   anchor_formula=GOOD_ANCHOR_FORMULA, fallback_formula=GOOD_FALLBACK_FORMULA,
                   spec057_literal=GOOD_SPEC057_LITERAL,
                   spec057_format_args=GOOD_SPEC057_FORMAT_ARGS, omit_action=False,
                   omit_data_model=False, omit_board_loop=False,
                   import_line=GOOD_IMPORT_LINE):
    action_dir = os.path.join(root, os.path.dirname(ACTION_FILE))
    os.makedirs(action_dir, exist_ok=True)
    if not omit_action:
        with open(os.path.join(root, ACTION_FILE), "w", encoding="utf-8") as fh:
            fh.write(ACTION_TEMPLATE.format(
                norm_regex=norm_regex, anchor_literal=anchor_literal,
                fallback_literal=fallback_literal))

    dm_dir = os.path.join(root, os.path.dirname(DATA_MODEL_FILE))
    os.makedirs(dm_dir, exist_ok=True)
    if not omit_data_model:
        with open(os.path.join(root, DATA_MODEL_FILE), "w", encoding="utf-8") as fh:
            fh.write(DATA_MODEL_TEMPLATE.format(
                norm_line=norm_line, anchor_formula=anchor_formula,
                fallback_formula=fallback_formula))

    bl_dir = os.path.join(root, os.path.dirname(BOARD_LOOP_FILE))
    os.makedirs(bl_dir, exist_ok=True)
    if not omit_board_loop:
        with open(os.path.join(root, BOARD_LOOP_FILE), "w", encoding="utf-8") as fh:
            fh.write(BOARD_LOOP_TEMPLATE.format(import_line=import_line))
    home_dir = os.path.join(root, os.path.dirname(SPEC057_HOME_FILE))
    os.makedirs(home_dir, exist_ok=True)
    with open(os.path.join(root, SPEC057_HOME_FILE), "w", encoding="utf-8") as fh:
        fh.write(SPEC057_HOME_TEMPLATE.format(
            spec057_literal=spec057_literal,
            spec057_format_args=spec057_format_args))


selftest_failures = []


def selftest_fail(msg):
    selftest_failures.append(msg)
    print(f"::error::verify-dedup-key-canonical-rule: {msg}")


def _run_case(case, build, expect_pass, needle=None):
    tmp = tempfile.mkdtemp(prefix="wc-dedup-key-gate-")
    try:
        build(tmp)
        found = evaluate(tmp)
        if expect_pass:
            if found:
                selftest_fail(f"[{case}] expected a clean pass, got: {found}")
            else:
                note(f"[{case}] passed")
        else:
            hit = [f for f in found if (needle or "") in f] if needle else found
            if not hit:
                selftest_fail(f"[{case}] expected a finding"
                             f"{' naming ' + repr(needle) if needle else ''}, got: {found}")
            else:
                note(f"[{case}] passed")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def selftest_clean_fixture_passes():
    _run_case("a clean fixture (good doc, good code, good board-loop) passes",
             lambda tmp: _write_fixture(tmp), expect_pass=True)


def selftest_shape_tag_changed_fails():
    _run_case("a shape tag changed in the action file fails, naming the tag",
             lambda tmp: _write_fixture(tmp, anchor_literal="anchr|{0}|{1}|{2}"),
             expect_pass=False, needle="'anchor|'")


def selftest_doc_norm_line_altered_fails():
    _run_case("the data-model.md norm() line altered (regex dropped) fails",
             lambda tmp: _write_fixture(tmp, norm_line="norm(s) = lowercase(s), trimmed"),
             expect_pass=False, needle="norm() regex")


def selftest_board_loop_converged_fails():
    _run_case("board-loop's formula edited to match this feature's byte-for-byte fails as converged",
             lambda tmp: _write_fixture(tmp, spec057_literal=GOOD_FALLBACK_LITERAL),
             expect_pass=False, needle="FR-015")


def selftest_board_loop_missing_issue_segment_fails():
    _run_case("board-loop's formula missing the issue-number segment fails as diverged",
             lambda tmp: _write_fixture(
                 tmp, spec057_literal="{0}|{1}",
                 spec057_format_args="norm(title), norm(file_path)"),
             expect_pass=False, needle="issue-number segment")


def selftest_board_loop_stops_calling_home_fails():
    _run_case("board-loop's step no longer importing wc_review_finding_fingerprint fails",
             lambda tmp: _write_fixture(tmp, import_line="import hashlib"),
             expect_pass=False, needle="single home")


def selftest_missing_action_file_fails_loudly():
    _run_case("a missing action.yml fails loudly, not vacuously",
             lambda tmp: _write_fixture(tmp, omit_action=True),
             expect_pass=False, needle=ACTION_FILE)


def selftest_missing_data_model_fails_loudly():
    _run_case("a missing data-model.md fails loudly, not vacuously",
             lambda tmp: _write_fixture(tmp, omit_data_model=True),
             expect_pass=False, needle="Fingerprint")


def selftest_real_files_pass():
    case = "the real, post-implementation files pass"
    found = evaluate(".")
    if found:
        selftest_fail(f"[{case}] real tree failed: {found}")
    else:
        note(f"[{case}] passed")


def run_selftest():
    use_utf8_stdout()
    selftest_clean_fixture_passes()
    selftest_shape_tag_changed_fails()
    selftest_doc_norm_line_altered_fails()
    selftest_board_loop_converged_fails()
    selftest_board_loop_missing_issue_segment_fails()
    selftest_board_loop_stops_calling_home_fails()
    selftest_missing_action_file_fails_loudly()
    selftest_missing_data_model_fails_loudly()
    selftest_real_files_pass()
    print(f"verify-dedup-key-canonical-rule --self-test: "
          f"{len(selftest_failures)} failure(s).")
    return 1 if selftest_failures else 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    use_utf8_stdout()

    if args.self_test:
        sys.exit(run_selftest())

    found = evaluate(".")
    print(f"verify-dedup-key-canonical-rule: {len(found)} failure(s).")
    sys.exit(1 if found else 0)


if __name__ == "__main__":
    main()
