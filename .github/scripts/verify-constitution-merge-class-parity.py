#!/usr/bin/env python3
"""Gate — the constitution names every class of merge the pipeline can
actually perform (specs/062-lifecycle-review-gate FR-038,
contracts/constitution-amendment.md).

WHY THIS EXISTS
---------------
Principle V says "the only merges the bot may perform are the two classes
Principle X defines", and Principle X names them: the bounded fix-PR merge
and the verified dependency-bump merge. This feature adds a THIRD — the
lifecycle pull request merge, behind `WING_COMMANDER_LIFECYCLE_AUTO_MERGE`.
Code that merges a class the constitution does not name is a violation of
V, not an extension of X, and the document says so in those words.

The direction of this check matters. It is **presence-implies-documented**,
never absence-implies-forbidden — the exact inverse of
verify-board-readiness.py's `check_no_merge_invariant`, which scans
board-loop.yml for merge calls that must not exist. Here the merge call is
allowed to exist; what is not allowed is for it to exist while Principles V
and X still describe a two-class world. So: no merge capability in
lifecycle-review-gate.yml → this gate passes vacuously, and a constitution
that already names the class with no code present also passes (the
amendment may land first).

Only Principles V and X's own text counts. The Sync Impact Report comments
stacked at the top of the file are amendment *history* (CLAUDE.md keeps
them deliberately); a past report's prose must never be what satisfies a
present-tense claim about what the principles say.

    python3 .github/scripts/verify-constitution-merge-class-parity.py
    python3 .github/scripts/verify-constitution-merge-class-parity.py --self-test
"""
import os
import re
import sys

WORKFLOW = ".github/workflows/lifecycle-review-gate.yml"
CONSTITUTION = ".specify/memory/constitution.md"

AUTO_MERGE_VAR = "WING_COMMANDER_LIFECYCLE_AUTO_MERGE"
KILL_SWITCH_VAR = "WING_COMMANDER_LIFECYCLE_REVIEW_GATE_PAUSED"

# The merge capability's own code: a `gh pr merge` call in a workflow that
# also gates on the auto-merge variable. Both halves are required — a
# workflow naming the variable without ever merging (this gate's own
# self-test fixtures, or a future read-only reporter) is not a capability.
GH_PR_MERGE_RE = re.compile(r"\bgh\s+pr\s+merge\b")

# The two headings whose text this gate reads (### V. ... / ### X. ...),
# each running to the next `### ` or `## ` heading.
PRINCIPLE_HEADING_RE = re.compile(
    r"^###\s+(?P<numeral>[IVX]+)\.\s", re.MULTILINE)

# The amendment's own three-class language (contracts/constitution-
# amendment.md "Required edits" 1 and 3).
THREE_CLASS_RE = re.compile(r"\bthree\s+(?:merge\s+)?classes\b", re.I)
# ...naming which third class it is, not merely that there are three.
LIFECYCLE_CLASS_RE = re.compile(
    r"\blifecycle\s+(?:pull[- ]request|PR)\s+merge\b", re.I)


def merge_capability_present(workflow_text):
    """True when the workflow carries the merge capability's own code: a
    `gh pr merge` call AND the auto-merge variable that gates it."""
    return bool(GH_PR_MERGE_RE.search(workflow_text)
                and AUTO_MERGE_VAR in workflow_text)


def principle_text(constitution_text, numerals):
    """The body of each named principle, concatenated. Everything above the
    first `### <numeral>. ` heading — the stacked Sync Impact Report
    comments included — is excluded by construction."""
    matches = list(PRINCIPLE_HEADING_RE.finditer(constitution_text))
    chunks = []
    for i, match in enumerate(matches):
        if match.group("numeral") not in numerals:
            continue
        end = (matches[i + 1].start() if i + 1 < len(matches)
               else len(constitution_text))
        chunks.append(constitution_text[match.start():end])
    return "\n".join(chunks)


def missing_documentation(constitution_text):
    """The list of things Principles V and X must say once the capability
    exists, and do not. Empty means the constitution is in parity."""
    text = principle_text(constitution_text, {"V", "X"})
    missing = []
    if not THREE_CLASS_RE.search(text):
        missing.append("Principles V/X still describe two merge classes -- "
                       "no 'three classes' language")
    if not LIFECYCLE_CLASS_RE.search(text):
        missing.append("Principles V/X never name the third class (the "
                       "lifecycle pull request merge)")
    if AUTO_MERGE_VAR not in text:
        missing.append("Principles V/X never name {0} -- the setting the "
                       "third class is bounded by".format(AUTO_MERGE_VAR))
    if KILL_SWITCH_VAR not in text:
        missing.append("Principles V/X never name {0} -- the kill switch "
                       "that stops the third class".format(KILL_SWITCH_VAR))
    return missing


def check(workflow_text, constitution_text):
    """Returns a list of failure strings (empty == pass). Presence-implies-
    documented: with no capability in the workflow, nothing is required."""
    if not merge_capability_present(workflow_text):
        return []
    return missing_documentation(constitution_text)


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def run():
    for path in (WORKFLOW, CONSTITUTION):
        if not os.path.isfile(path):
            print("::error::verify-constitution-merge-class-parity: {0} "
                  "does not exist; this gate cannot check what it claims "
                  "to.".format(path))
            return 1

    workflow_text = _read(WORKFLOW)
    constitution_text = _read(CONSTITUTION)

    if not merge_capability_present(workflow_text):
        print("[ok] {0} carries no auto-merge capability; the constitution "
              "is not required to name a third merge class.".format(WORKFLOW))
        print("verify-constitution-merge-class-parity: 0 failure(s).")
        return 0

    failures = check(workflow_text, constitution_text)
    if not failures:
        print("[ok] {0} carries the auto-merge capability and {1}'s "
              "Principles V/X name the third merge class.".format(
                  WORKFLOW, CONSTITUTION))
        print("verify-constitution-merge-class-parity: 0 failure(s).")
        return 0

    print("::error::verify-constitution-merge-class-parity: {0} carries the "
          "auto-merge capability ({1}-gated `gh pr merge`) while {2} does "
          "not name it as a class of merge the bot may perform. The "
          "capability may ship inert, but {1} can never be set to true "
          "until the amendment lands (FR-033: a separate, human-merged PR "
          "against main -- never part of this feature's own branch)."
          .format(WORKFLOW, AUTO_MERGE_VAR, CONSTITUTION))
    for failure in failures:
        print("::error::  - {0}".format(failure))
    print("verify-constitution-merge-class-parity: {0} failure(s).".format(
        len(failures)))
    return 1


# T056: inline synthetic fixtures, not checked-in files
# (contracts/gates.md "Fixture placement", matching
# check_no_merge_invariant's own self-test shape).
_MERGE_CODE = """
  merge:
    if: vars.WING_COMMANDER_LIFECYCLE_AUTO_MERGE == 'true'
    steps:
      - run: gh pr merge --squash "$PR_NUMBER" --match-head-commit "$SHA"
"""
_NO_MERGE_CODE = """
  report:
    steps:
      - run: gh issue comment "$ISSUE" --body "$body"
"""
_TWO_CLASS_CONSTITUTION = """
Sync Impact Report: this amendment names three classes and
WING_COMMANDER_LIFECYCLE_AUTO_MERGE and
WING_COMMANDER_LIFECYCLE_REVIEW_GATE_PAUSED and the lifecycle pull request
merge -- history, above the principles, which must not satisfy this gate.

# Wing Commander Constitution

## Core Principles

### V. Security — Untrusted Content Is Never Instructions (NON-NEGOTIABLE)

The only merges the bot may perform are the two classes Principle X
defines.

### X. Bounded Autonomy — The Pipeline Works Its Own Board

A fix PR MUST NOT be merged unless the checks are green. The second and
only other class the bot may merge is a dependency-bump PR.
"""
_THREE_CLASS_CONSTITUTION = """
# Wing Commander Constitution

## Core Principles

### V. Security — Untrusted Content Is Never Instructions (NON-NEGOTIABLE)

The only merges the bot may perform are the three classes Principle X
defines.

### X. Bounded Autonomy — The Pipeline Works Its Own Board

The third class is the lifecycle pull request merge, behind
WING_COMMANDER_LIFECYCLE_AUTO_MERGE and stopped by
WING_COMMANDER_LIFECYCLE_REVIEW_GATE_PAUSED.
"""


def self_test():
    failures = 0

    def expect(name, workflow_text, constitution_text, should_fail):
        nonlocal failures
        got = check(workflow_text, constitution_text)
        if bool(got) == should_fail:
            print("PASS {0}".format(name))
        else:
            failures += 1
            print("FAIL {0} expected {1}, got {2!r}".format(
                name, "failure" if should_fail else "pass", got))

    expect("merge-code-present-constitution-silent",
           _MERGE_CODE, _TWO_CLASS_CONSTITUTION, True)
    expect("constitution-names-class-no-merge-code",
           _NO_MERGE_CODE, _THREE_CLASS_CONSTITUTION, False)
    expect("neither-present", _NO_MERGE_CODE, _TWO_CLASS_CONSTITUTION, False)
    expect("both-present", _MERGE_CODE, _THREE_CLASS_CONSTITUTION, False)

    # The Sync Impact Report's own prose sits above the first principle
    # heading and must never satisfy the check -- the two-class fixture's
    # report mentions every phrase this gate looks for.
    body = principle_text(_TWO_CLASS_CONSTITUTION, {"V", "X"})
    if "Sync Impact Report" not in body:
        print("PASS sync-impact-report-excluded")
    else:
        failures += 1
        print("FAIL sync-impact-report-excluded: the report's prose leaked "
              "into the principle text this gate reads")

    # A workflow that names the variable but never merges is not a
    # capability (constitution VIII: a gate must be able to distinguish).
    got = check("if: vars.WING_COMMANDER_LIFECYCLE_AUTO_MERGE == 'true'\n",
                _TWO_CLASS_CONSTITUTION)
    if not got:
        print("PASS variable-without-merge-call-is-not-a-capability")
    else:
        failures += 1
        print("FAIL variable-without-merge-call-is-not-a-capability: "
              "{0!r}".format(got))

    # ...and a `gh pr merge` with no auto-merge gate is some other
    # workflow's merge, not this class.
    got = check('- run: gh pr merge --squash "$PR"\n',
                _TWO_CLASS_CONSTITUTION)
    if not got:
        print("PASS ungated-merge-call-is-not-this-class")
    else:
        failures += 1
        print("FAIL ungated-merge-call-is-not-this-class: {0!r}".format(got))

    print("{0} failure(s).".format(failures))
    return 1 if failures else 0


def main(argv):
    if argv == ["--self-test"]:
        return self_test()
    if argv:
        sys.exit("unknown arguments {0!r}; takes --self-test or nothing.".format(argv))
    return run()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
