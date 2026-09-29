#!/usr/bin/env python3
"""Gate 114 -- exactly one canonical statement of the accepted maintainer
credential shape; every other site points at it (FR-017/FR-018,
specs/066-fine-grained-maintainer-token).

specs/066-fine-grained-maintainer-token's User Story 4 motivation: "a
classic PAT, not fine-grained" was asserted in at least four places
(`docs/setup.md` section 2, `auto-release.yml`'s credential-step comment,
this gate's own docstring/scenario text, and specs/055-unattended-e2e-gates'
research.md D1/D2 and Clarifications session) before this feature flipped
the shape in three of them. A change that corrects the claim in three
places and leaves the fourth is exactly the drift CLAUDE.md's "shared logic
has exactly one home" rule exists to prevent -- here the drifted copy would
be a security claim.

This is a NEW, topic-specific gate rather than an extension of Gate 47
(`verify-comment-canonical-pointers.py`), whose declared scope is `#`
comments in `.github/workflows/*.yml` only -- it never scans `docs/*.md` or
`specs/*/research.md` as a pointer source (research.md D7 of this feature).

WHAT IT CHECKS
--------------
Four sites (contracts/canonical-statement-gate.md):

  1. Canonical: docs/setup.md's WING_COMMANDER_AUTO_RELEASE_E2E_MAINTAINER_TOKEN
     row. Exempt from the phrase check below -- it is where a qualified
     statement of the shape is expected to live.
  2. Pointer: auto-release.yml's comment block above the "Confirm the
     fixture maintainer identity's credential" step.
  3. Pointer: the precheck's own expectation text -- the step's own `run:`
     body (the `expected` arguments passed to auto-release-verdict.sh) plus
     this gate script's own docstring/scenario text.
  4. Pointer, historical: specs/055-unattended-e2e-gates/research.md's D1
     and D2 sections, and its spec.md Clarifications session.

Sites 2 and 3 MUST carry a pointer to site 1 (`-- see docs/setup.md` or
`(see docs/setup.md)`, the two forms Gate 47 already recognizes), and MUST
NOT contain an unqualified instance of the fixed contradicting-phrase list
below. Site 4 MUST instead carry the FR-019 annotation (a sentence naming
specs/066-fine-grained-maintainer-token and stating the decision was
superseded) near each of its three locations, preserving the old text as
history rather than restating it as still current.

This is a fixed phrase list, not a generic overlap heuristic (research.md
D7) -- the gate exists to catch a specific, previously-drifted claim, not
to police prose generally.

USAGE
-----
    python3 .github/scripts/verify-maintainer-credential-canonical-statement.py
    python3 .github/scripts/verify-maintainer-credential-canonical-statement.py --self-test
"""
import importlib.util
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_shell_harness import find_step  # noqa: E402

_HERE = os.path.dirname(os.path.abspath(__file__))


def _load_module(name, filename):
    spec = importlib.util.spec_from_file_location(name, os.path.join(_HERE, filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ccp = _load_module("wc_comment_canonical_pointers", "verify-comment-canonical-pointers.py")

CANONICAL_FILE = os.path.join("docs", "setup.md")
WORKFLOW = os.path.join(".github", "workflows", "auto-release.yml")
STEP_NAME = "Confirm the fixture maintainer identity's credential"
GATE_SCRIPT = os.path.join(".github", "scripts", "verify-auto-release-credential-step.py")
SPEC_RESEARCH = os.path.join("specs", "055-unattended-e2e-gates", "research.md")
SPEC_SPEC = os.path.join("specs", "055-unattended-e2e-gates", "spec.md")

POINTER_MARKERS = ("-- see docs/setup.md", "(see docs/setup.md)")

# The specific, previously-drifted claims this gate exists to catch --
# see the module docstring. Checked case-insensitively as plain substrings,
# deliberately not a generic heuristic (research.md D7).
FIXED_PHRASES = (
    "not fine-grained",
    "never fine-grained",
    "only accepted shape",
    "never admin",
)

FR019_MARKER = "specs/066-fine-grained-maintainer-token"


def step_comment_block(path, step_name):
    """The `#`-comment block immediately above the named step's `- name:`
    line, joined into one string -- reuses Gate 47's own comment-block
    extraction rather than a second, hand-rolled copy."""
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()
    target_idx = None
    for i, line in enumerate(lines):
        if "name:" in line and step_name in line:
            target_idx = i
            break
    if target_idx is None:
        sys.exit(f"::error file={path}::no step named {step_name!r}. If it was "
                 f"renamed, update this gate and the workflow together.")
    for block in ccp.comment_blocks(path):
        if block["lines"][-1][0] == target_idx:
            return ccp._joined(block)
    return ""


def check_pointer_site(text):
    """-> list of violation strings for one non-canonical site's text."""
    violations = []
    low = text.lower()
    has_pointer = any(marker in low for marker in POINTER_MARKERS)
    for phrase in FIXED_PHRASES:
        if phrase in low and not has_pointer:
            violations.append(
                f"contains the fixed contradicting phrase {phrase!r} with no "
                f"pointer to docs/setup.md")
    if not has_pointer:
        violations.append(
            "carries no pointer to docs/setup.md ('-- see docs/setup.md' or "
            "'(see docs/setup.md)')")
    return violations


def section_text(path, heading_prefix):
    """The text from a heading starting with `heading_prefix` up to (not
    including) the next `##` heading, or end of file."""
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.strip().startswith(heading_prefix):
            start = i
            break
    if start is None:
        sys.exit(f"::error file={path}::heading {heading_prefix!r} not found. "
                 f"If it was renamed, update this gate and the spec together.")
    end = len(lines)
    for j in range(start + 1, len(lines)):
        stripped = lines[j].strip()
        if stripped.startswith("## ") and not stripped.startswith(heading_prefix):
            end = j
            break
    return "\n".join(lines[start:end])


def check_historical_site(research_path, spec_path):
    violations = []
    sections = [
        (f"{research_path} D1", section_text(research_path, "## D1.")),
        (f"{research_path} D2", section_text(research_path, "## D2.")),
        (f"{spec_path} Clarifications", section_text(spec_path, "## Clarifications")),
    ]
    for label, text in sections:
        low = text.lower()
        if FR019_MARKER not in low or "supersed" not in low:
            violations.append(
                f"{label}: missing the FR-019 annotation (a sentence naming "
                f"{FR019_MARKER} and stating the decision was superseded)")
    return violations


def run_gate(root="."):
    violations = []

    canonical_path = os.path.join(root, CANONICAL_FILE)
    if not os.path.isfile(canonical_path):
        sys.exit(f"::error file={CANONICAL_FILE}::canonical file not found.")

    workflow_path = os.path.join(root, WORKFLOW)
    comment_text = step_comment_block(workflow_path, STEP_NAME)
    for v in check_pointer_site(comment_text):
        violations.append(f"{WORKFLOW} (credential-step comment): {v}")

    step = find_step(workflow_path, STEP_NAME)
    step_body = str(step.get("run", ""))
    gate_script_path = os.path.join(root, GATE_SCRIPT)
    with open(gate_script_path, encoding="utf-8") as f:
        gate_script_text = f.read()
    site3_text = step_body + "\n" + gate_script_text
    for v in check_pointer_site(site3_text):
        violations.append(f"{GATE_SCRIPT} / {WORKFLOW} expectation text: {v}")

    research_path = os.path.join(root, SPEC_RESEARCH)
    spec_path = os.path.join(root, SPEC_SPEC)
    for v in check_historical_site(research_path, spec_path):
        violations.append(v)

    for v in violations:
        file_part = v.split(":", 1)[0]
        print(f"::error file={file_part}::verify-maintainer-credential-canonical-statement: {v}")

    print(f"verify-maintainer-credential-canonical-statement: {len(violations)} violation(s).")
    return 1 if violations else 0


# ----------------------------------------------------------------------------
# Self-test
# ----------------------------------------------------------------------------
def _write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)


_CLEAN_WORKFLOW = """\
on: push
jobs:
  verify-e2e:
    steps:
      # research.md D1: detects the accepted shape from the token's own
      # prefix -- see docs/setup.md for the canonical statement.
      - name: Confirm the fixture maintainer identity's credential
        run: |
          echo "expected=a value matching the classic or fine-grained prefix"
"""

_CLEAN_GATE_SCRIPT = '''"""Gate 67 -- see docs/setup.md for the canonical statement of the
accepted credential shape(s). Scenario: "an extra repository" fails.
"""
'''

_CLEAN_RESEARCH = """\
# Phase 0 Research

## D1. Identity and credential shape

**Superseded**: superseded by specs/066-fine-grained-maintainer-token,
which accepts a repository-scoped fine-grained credential too -- see
specs/066-fine-grained-maintainer-token/research.md D1.

**Decision**: a classic personal access token.

## D2. Runtime containment check

**Superseded in part**: superseded by specs/066-fine-grained-maintainer-token
-- see specs/066-fine-grained-maintainer-token/research.md D3/D4.

**Decision**: list every repository the token can reach.
"""

_CLEAN_SPEC = """\
# Feature Specification

## Clarifications

**Superseded in part**: Question 1's answer was superseded by
specs/066-fine-grained-maintainer-token -- see
specs/066-fine-grained-maintainer-token/spec.md Clarifications Q1.

### Session 2026-09-19

**Answered**: a classic personal access token.
"""


def _write_clean_fixture(root):
    _write(os.path.join(root, CANONICAL_FILE),
           "| `WING_COMMANDER_AUTO_RELEASE_E2E_MAINTAINER_TOKEN` | ... |\n")
    _write(os.path.join(root, WORKFLOW), _CLEAN_WORKFLOW)
    _write(os.path.join(root, GATE_SCRIPT), _CLEAN_GATE_SCRIPT)
    _write(os.path.join(root, SPEC_RESEARCH), _CLEAN_RESEARCH)
    _write(os.path.join(root, SPEC_SPEC), _CLEAN_SPEC)


def self_test():
    """Synthetic fixtures proving each check catches its defect -- built
    fresh in a tempdir, not checked in: the thing under test is a rule
    about live repository prose, and a committed fixture would need this
    gate's own phrase list applied to it forever."""
    failures = 0

    def check(name, cond, detail=""):
        nonlocal failures
        if cond:
            print(f"PASS {name}")
        else:
            failures += 1
            print(f"FAIL {name} {detail}")

    with tempfile.TemporaryDirectory() as td:
        _write_clean_fixture(td)
        rc = run_gate(td)
        check("clean fixture passes", rc == 0, f"rc={rc}")

        # Defect: an unqualified contradicting phrase at the workflow
        # comment site, with its pointer removed.
        _write(os.path.join(td, WORKFLOW), _CLEAN_WORKFLOW.replace(
            "-- see docs/setup.md for the canonical statement.",
            "-- this credential is not fine-grained."))
        rc = run_gate(td)
        check("unqualified 'not fine-grained' at the workflow comment, no pointer, fails",
              rc != 0, f"rc={rc}")
        _write(os.path.join(td, WORKFLOW), _CLEAN_WORKFLOW)

        # Defect: an unqualified contradicting phrase at the gate script
        # site, with no pointer.
        _write(os.path.join(td, GATE_SCRIPT), _CLEAN_GATE_SCRIPT.replace(
            "-- see docs/setup.md for the canonical statement of the",
            "-- classic PAT, the only accepted shape, for the"))
        rc = run_gate(td)
        check("'only accepted shape' at the gate script, no pointer, fails",
              rc != 0, f"rc={rc}")
        _write(os.path.join(td, GATE_SCRIPT), _CLEAN_GATE_SCRIPT)

        # Defect: the pointer removed from the workflow comment while a
        # qualified restatement (no fixed phrase) remains -- still a second,
        # unlinked copy.
        _write(os.path.join(td, WORKFLOW), _CLEAN_WORKFLOW.replace(
            " -- see docs/setup.md for the canonical statement.", "."))
        rc = run_gate(td)
        check("workflow comment with its pointer removed fails",
              rc != 0, f"rc={rc}")
        _write(os.path.join(td, WORKFLOW), _CLEAN_WORKFLOW)

        # Defect: the pointer aimed at a nonexistent target (not
        # docs/setup.md) is not recognized as a pointer at all.
        _write(os.path.join(td, WORKFLOW), _CLEAN_WORKFLOW.replace(
            "-- see docs/setup.md for the canonical statement.",
            "-- see nonexistent-file.md."))
        rc = run_gate(td)
        check("a pointer aimed elsewhere than docs/setup.md fails",
              rc != 0, f"rc={rc}")
        _write(os.path.join(td, WORKFLOW), _CLEAN_WORKFLOW)

        # Defect: the FR-019 annotation removed from specs/055's research.md.
        _write(os.path.join(td, SPEC_RESEARCH), _CLEAN_RESEARCH.replace(
            "**Superseded**: superseded by specs/066-fine-grained-maintainer-token,\n"
            "which accepts a repository-scoped fine-grained credential too -- see\n"
            "specs/066-fine-grained-maintainer-token/research.md D1.\n\n", ""))
        rc = run_gate(td)
        check("missing FR-019 annotation on specs/055 research.md D1 fails",
              rc != 0, f"rc={rc}")
        _write(os.path.join(td, SPEC_RESEARCH), _CLEAN_RESEARCH)

    print(f"{failures} failure(s).")
    return 1 if failures else 0


def main(argv):
    if argv == ["--self-test"]:
        return self_test()
    if argv:
        sys.exit(f"unknown arguments {argv!r}; takes --self-test or nothing.")
    return run_gate()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
