#!/usr/bin/env python3
"""Gate 100 - a published stage's declared max-turns default agrees with the
docs/adoption.md row that describes it (FR-017/FR-018, issue #587).

WHY THIS EXISTS
---------------
specs/079-clarify-turn-budget re-based clarify.yml's `max-turns` default from
`40` to `65` and moved docs/adoption.md's `### clarify` Inputs row to match in
the same change. Nothing before this gate would have caught it if only one of
those two had moved: docs/adoption.md's per-stage `max-turns` default is
prose a human types, not a value derived from the workflow file, so a future
PR that re-bases a stage's budget and forgets the docs row (or edits the docs
row without touching the workflow) passes every existing gate. That is the
same class of gap CLAUDE.md's own cost-line example and Gate 26's Sync Impact
Report both name: a fact stated in two places drifts the moment one of them
is edited and nothing reads both.

WHAT IT CHECKS
--------------
For every `*.yml` file directly under the workflows directory that declares
`on.workflow_call.inputs.max-turns.default`, this gate parses that literal
and the matching `docs/adoption.md` `### <stage>` section's Inputs row
`` `max-turns` (number, `NNN`) `` cell, then fails - naming the stage and both
values - on any disagreement. Zero such workflow files discovered is a
failure, not a vacuous pass (constitution VIII): a working directory typo or
every stage's turn-budget input vanishing would otherwise look identical to a
clean run. A stage whose docs section has no `max-turns` cell at all while
its workflow declares one fails naming the stage, rather than being silently
skipped, since a missing cell is the same drift this gate exists to catch,
just with nothing on one side to disagree with yet.

WHAT IT DOES NOT CHECK
-----------------------
Whether the declared number itself is the RIGHT number for that stage's
workload - that is a judgement call recorded in a spec's research.md
(R1, for clarify's 65), not something this gate can derive. It also does not
touch the runaway-ceiling multiplier, the watchdog's band arithmetic, or any
other input this stage declares; it looks at exactly one cell per stage.

SELF-TEST
---------
`--self-test` runs the check against five checked-in fixture pairs under
fixtures/stage-turn-budget-docs/ (contracts/gate-coverage-079.md): all nine
stages agreeing, a workflow-side drift, a docs-side drift, a docs section
missing its cell entirely, and an empty scratch directory with no stage files
at all. A fixture that fails for the WRONG reason is itself a failure - each
assertion matches the substring naming the specific defect.
"""
import argparse
import glob
import os
import re
import sys

import yaml

FIXTURES_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "fixtures", "stage-turn-budget-docs")

DOCS_ROW_RE = re.compile(r"`max-turns`\s*\(number,\s*`(-?\d+)`\)")
STAGE_SECTION_RE = re.compile(r"^###\s+(\S+)\s*$")


def workflow_max_turns_default(path):
    """-> the int default, or None if this file declares no
    on.workflow_call.inputs.max-turns.default."""
    try:
        with open(path, encoding="utf-8") as f:
            doc = yaml.safe_load(f)
    except (yaml.YAMLError, OSError):
        return None
    if not isinstance(doc, dict):
        return None
    # PyYAML resolves the bare key `on` to the boolean True (YAML 1.1); a
    # quoted "on" stays a string. Accept either, same as wc_published_stages.
    on = doc.get(True, doc.get("on"))
    if not isinstance(on, dict):
        return None
    workflow_call = on.get("workflow_call")
    if not isinstance(workflow_call, dict):
        return None
    inputs = workflow_call.get("inputs")
    if not isinstance(inputs, dict):
        return None
    max_turns = inputs.get("max-turns")
    if not isinstance(max_turns, dict) or "default" not in max_turns:
        return None
    return max_turns["default"]


def docs_sections(text):
    """-> {stage: section_text}, split on '### <stage>' headings."""
    sections = {}
    current, buf = None, []
    for line in text.splitlines():
        m = STAGE_SECTION_RE.match(line)
        if m:
            if current is not None:
                sections[current] = "\n".join(buf)
            current, buf = m.group(1), []
        elif current is not None:
            buf.append(line)
    if current is not None:
        sections[current] = "\n".join(buf)
    return sections


def docs_max_turns_default(section_text):
    """-> int, or None if this section's Inputs row has no max-turns cell."""
    m = DOCS_ROW_RE.search(section_text)
    return int(m.group(1)) if m else None


def check(workflows_dir, docs_path):
    """-> list of failure strings. Empty means every subject agrees."""
    failures = []
    workflow_defaults = {}
    for path in sorted(glob.glob(os.path.join(workflows_dir, "*.yml"))):
        stage = os.path.splitext(os.path.basename(path))[0]
        default = workflow_max_turns_default(path)
        if default is not None:
            workflow_defaults[stage] = default

    if not workflow_defaults:
        failures.append(
            "no *.yml file under {0} declares "
            "on.workflow_call.inputs.max-turns.default -- either this is the "
            "wrong working directory or every published stage's turn-budget "
            "input has vanished; either way this gate has no subject, which "
            "is a failure, not a clean pass.".format(workflows_dir))
        return failures

    sections = {}
    if os.path.isfile(docs_path):
        with open(docs_path, encoding="utf-8") as f:
            sections = docs_sections(f.read())

    for stage in sorted(workflow_defaults):
        wf_default = workflow_defaults[stage]
        section = sections.get(stage)
        if section is None:
            failures.append(
                "{0}: workflow declares max-turns default {1}, but {2} has "
                "no '### {0}' section at all.".format(
                    stage, wf_default, docs_path))
            continue
        docs_default = docs_max_turns_default(section)
        if docs_default is None:
            failures.append(
                "{0}: workflow declares max-turns default {1}, but its "
                "docs/adoption.md '### {0}' section's Inputs row has no "
                "`max-turns` (number, `NNN`) cell -- the docs row is "
                "missing, not merely wrong.".format(stage, wf_default))
            continue
        if wf_default != docs_default:
            failures.append(
                "{0}: workflow declares max-turns default {1}, but "
                "docs/adoption.md states {2} -- they must agree.".format(
                    stage, wf_default, docs_default))
    return failures


# ----------------------------------------------------------------------------
# Self-test
# ----------------------------------------------------------------------------
FIXTURES = [
    # (case dir name, expected substring or None for a clean pass)
    ("all-agree", None),
    ("workflow-drifted", "workflow declares max-turns default 70"),
    ("docs-drifted", "docs/adoption.md states 70"),
    ("docs-missing-cell", "docs row is missing, not merely wrong"),
    ("no-subjects", "this gate has no subject"),
]


def self_test():
    bad = 0
    for name, expect in FIXTURES:
        case_dir = os.path.join(FIXTURES_DIR, name)
        workflows_dir = os.path.join(case_dir, "workflows")
        docs_path = os.path.join(case_dir, "adoption.md")
        failures = check(workflows_dir, docs_path)
        joined = " | ".join(failures)
        if expect is None:
            if failures:
                bad += 1
                print("[FAIL] {0}: expected a clean pass, got: {1}".format(
                    name, joined))
            else:
                print("[ok] {0}: clean".format(name))
        elif not failures:
            bad += 1
            print("[FAIL] {0}: expected a failure containing {1!r}, got a "
                  "clean pass".format(name, expect))
        elif expect not in joined:
            bad += 1
            print("[FAIL] {0}: failed for the WRONG reason. expected {1!r}, "
                  "got: {2}".format(name, expect, joined))
        else:
            print("[ok] {0}: caught".format(name))
    print("Gate 100 self-test: {0}/{1} fixtures behaved as specified.".format(
        len(FIXTURES) - bad, len(FIXTURES)))
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser(
        description="Gate 100 - stage turn-budget/docs agreement")
    ap.add_argument("--self-test", action="store_true",
                     help="run the checked-in fixtures instead of the "
                          "working tree")
    args = ap.parse_args()

    if args.self_test:
        return self_test()

    workflows_dir = os.path.join(".", ".github", "workflows")
    docs_path = os.path.join(".", "docs", "adoption.md")
    failures = check(workflows_dir, docs_path)
    for failure in failures:
        print("::error::Gate 100: {0}".format(failure))
    print("Gate 100: checked the published stages' max-turns defaults in "
          "{0} workflow file(s) against docs/adoption.md; {1} failure(s).".format(
              len(glob.glob(os.path.join(workflows_dir, "*.yml"))),
              len(failures)))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
