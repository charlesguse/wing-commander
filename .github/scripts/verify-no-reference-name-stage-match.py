#!/usr/bin/env python3
"""Gate 138 — no FR-002 site gates on a reference display name
(specs/099-name-free-stage-identity T032, contracts/stage-identity-name-
gate.md).

WHY THIS EXISTS
---------------
T024-T030 converted every FR-002 collector/guard in watchdog.yml, and T023
converted the slug-fallback allowlist in wing-commander-inspected-run-
identity/action.yml, away from matching the inspected run's display name.
The one permitted exception is the `id: name-fallback` step inside that
same composite (R2) — the FR-009 fallback itself. Nothing stops a future
edit from reintroducing a `case "$RUN_NAME" in "Wing Commander · ...")`
arm elsewhere in either file, which would silently regress an adopter's
renamed wrapper back to losing watchdog coverage (spec.md's motivating
defect). This gate scans for exactly that regression.

It additionally enforces SC-008: every `wing-commander-metrics-summary`
call site across every workflow must carry a literal `spec-identity-is-
own:` key in its `with:` block (contracts/spec-identity-declaration.md
Rule 2) — kept behind this same gate rather than opening a second one for
a closely related property (research.md R3).

WHAT COUNTS AS A VIOLATION
---------------------------
Only a reference display-name literal used inside a shell conditional
that gates behavior: a `case "$VAR" in ... "LITERAL") ...` arm, or an
`if [ "$VAR" = "LITERAL" ]`/`!=` test. A bare mention in a comment, a
log/summary string, or documentation text is not a violation — nor is a
literal handed to a CLI flag (e.g. `gh run list --workflow 'NAME'`, which
queries this PIPELINE's own fixed workflow identity, never an adopter's
wrapper name).

FAILURE MODE
------------
Fails loudly — never silently reporting zero violations for the wrong
reason (constitution VIII) — if either target file cannot be read, or if
the permitted `id: name-fallback` step cannot be located at all (a sign
the exception site itself was renamed or removed without updating this
gate).

Usage: python3 .github/scripts/verify-no-reference-name-stage-match.py [--self-test]
"""
import os
import re
import sys

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_gate_registry import workflow_files  # noqa: E402

WATCHDOG = ".github/workflows/watchdog.yml"
COMPOSITE = ".github/actions/wing-commander-inspected-run-identity/action.yml"
NAME_FALLBACK_STEP_NAME = (
    "Resolve inspected run's stage from its display name, when the "
    "record left it unresolved")
NAME_FALLBACK_STEP_ID = "name-fallback"
METRICS_SUMMARY_MARKER = "wing-commander-metrics-summary"
SPEC_IDENTITY_KEY = "spec-identity-is-own"

# data-model.md's "Name-derived stage map" (nine entries) plus the tenth
# literal the self-inspection guard used to compare against (deliberately
# absent from the map itself, but still a reference name this gate must
# catch if it ever reappears in a gating conditional).
REFERENCE_NAMES = [
    "Wing Commander · 1 intake",
    "Wing Commander · 2 clarify",
    "Wing Commander · 3 plan",
    "Wing Commander · 4 tasks",
    "Wing Commander · 5 implement",
    "Wing Commander · 6 finalize",
    "Wing Commander · 7 cleanup",
    "Wing Commander · 9 pr conversation",
    "Wing Commander · rebase",
    "Wing Commander · 8 watchdog",
]

# A reference name as a `case` arm label: "NAME") or "NAME"|  (alternation).
CASE_ARM_RE = {
    name: re.compile(r'"' + re.escape(name) + r'"\s*[)|]') for name in REFERENCE_NAMES
}
# A reference name as the right-hand side of a bash string-equality test:
# [ "$VAR" = "NAME" ] / != "NAME" / [[ ... ]] alike.
IF_TEST_RE = {
    name: re.compile(r'[=!]=\s*"' + re.escape(name) + r'"') for name in REFERENCE_NAMES
}


def _find_name_fallback_line_range(text):
    """(start, end) 1-indexed inclusive line range of the permitted
    exception step's body in the composite's raw text, by locating its
    `id: name-fallback` line and the next step/EOF after it. Returns None
    if the step cannot be located at all (the gate's own fail-loudly
    requirement)."""
    lines = text.splitlines()
    id_line = None
    for i, line in enumerate(lines):
        if re.match(r"\s*id:\s*" + re.escape(NAME_FALLBACK_STEP_ID) + r"\s*$", line):
            id_line = i
            break
    if id_line is None:
        return None
    # The step itself starts at the preceding `- name:` line.
    start = id_line
    for i in range(id_line, -1, -1):
        if re.match(r"\s*-\s*name:", lines[i]):
            start = i
            break
    step_indent = len(re.match(r"\s*", lines[start]).group(0))
    end = len(lines) - 1
    for i in range(start + 1, len(lines)):
        m = re.match(r"(\s*)-\s*name:", lines[i])
        if m and len(m.group(1)) <= step_indent:
            end = i - 1
            break
    return (start + 1, end + 1)  # 1-indexed


def _is_comment_or_display_text(line):
    """True when `line`'s content is a `#` comment, a `name:`/description
    field, or a log/summary echo — contexts the contract excludes."""
    stripped = line.strip()
    if stripped.startswith("#"):
        return True
    if re.match(r"-?\s*name:\s*", stripped) or stripped.startswith("description:"):
        return True
    if "GITHUB_STEP_SUMMARY" in line or re.match(r'\s*echo\b', stripped):
        return True
    return False


def scan_reference_name_matches(path, text, exclude_range=None):
    """Violations: (path, line_no, name, line_text) for every reference
    name used inside a gating conditional, outside `exclude_range`
    (1-indexed, inclusive)."""
    violations = []
    for i, line in enumerate(text.splitlines(), start=1):
        if exclude_range and exclude_range[0] <= i <= exclude_range[1]:
            continue
        if _is_comment_or_display_text(line):
            continue
        for name in REFERENCE_NAMES:
            if CASE_ARM_RE[name].search(line) or IF_TEST_RE[name].search(line):
                violations.append((path, i, name, line.strip()))
    return violations


def _iter_steps(doc):
    if not isinstance(doc, dict):
        return
    for job in (doc.get("jobs") or {}).values():
        for step in ((job or {}).get("steps") or []):
            if isinstance(step, dict):
                yield step
    runs = doc.get("runs")
    if isinstance(runs, dict):
        for step in (runs.get("steps") or []):
            if isinstance(step, dict):
                yield step


def scan_metrics_summary_call_sites(sources):
    """{path: text} -> violations: (path, step-name) for every
    wing-commander-metrics-summary call site whose `with:` block has no
    literal `spec-identity-is-own:` key (SC-008)."""
    violations = []
    for path, text in sorted(sources.items()):
        try:
            doc = yaml.safe_load(text) or {}
        except yaml.YAMLError as exc:
            sys.exit(f"::error file={path}::verify-no-reference-name-stage-match: "
                     f"could not parse as YAML ({exc}) — cannot confirm its "
                     f"metrics-summary call sites declare spec-identity-is-own.")
        for step in _iter_steps(doc):
            uses = str(step.get("uses") or "")
            if METRICS_SUMMARY_MARKER not in uses:
                continue
            with_block = step.get("with") or {}
            if SPEC_IDENTITY_KEY not in with_block:
                violations.append((path, step.get("name") or "<unnamed step>"))
    return violations


def run_check(watchdog_text, composite_text, metrics_sources):
    """Returns (violations, errors). `errors` are fail-loud conditions
    (missing name-fallback step); `violations` are ordinary findings."""
    exclude_range = _find_name_fallback_line_range(composite_text)
    if exclude_range is None:
        return [], [
            f"could not locate the permitted `id: {NAME_FALLBACK_STEP_ID}` "
            f"step in the composite — it may have been renamed or removed "
            f"without updating this gate (constitution VIII: a gate that "
            f"cannot reach its subject MUST fail loudly)."]

    violations = []
    violations += scan_reference_name_matches(WATCHDOG, watchdog_text)
    violations += scan_reference_name_matches(COMPOSITE, composite_text, exclude_range)

    name_violations = [
        f"{p}:{ln}: reference display name {n!r} used inside a gating "
        f"conditional outside the permitted name-fallback step — {t!r}"
        for p, ln, n, t in violations]

    call_site_violations = scan_metrics_summary_call_sites(metrics_sources)
    name_violations += [
        f"{p}: step {name!r} calls wing-commander-metrics-summary with no "
        f"literal spec-identity-is-own: key (SC-008)"
        for p, name in call_site_violations]
    return name_violations, []


def main():
    self_test = "--self-test" in sys.argv[1:]
    if self_test:
        return self_test_main()

    if not os.path.isfile(WATCHDOG):
        sys.exit(f"::error file={WATCHDOG}::verify-no-reference-name-stage-match: "
                 f"cannot read {WATCHDOG}.")
    if not os.path.isfile(COMPOSITE):
        sys.exit(f"::error file={COMPOSITE}::verify-no-reference-name-stage-match: "
                 f"cannot read {COMPOSITE}.")
    watchdog_text = open(WATCHDOG, encoding="utf-8").read()
    composite_text = open(COMPOSITE, encoding="utf-8").read()
    metrics_sources = {p: open(p, encoding="utf-8").read() for p in workflow_files()}

    violations, errors = run_check(watchdog_text, composite_text, metrics_sources)
    for e in errors:
        print(f"::error::verify-no-reference-name-stage-match: {e}")
    for v in violations:
        print(f"::error::verify-no-reference-name-stage-match: {v}")
    if errors or violations:
        print(f"{len(errors)} error(s), {len(violations)} violation(s).")
        return 1
    print(f"Gate 138: {len(metrics_sources)} workflow file(s) scanned for "
          f"spec-identity-is-own; 0 reference-name-conditional violations, "
          f"0 missing-declaration violations.")
    return 0


# ---------------------------------------------------------------------------
# --self-test: contract Fixtures 1-5.
# ---------------------------------------------------------------------------
MINIMAL_CLEAN_COMPOSITE = """\
runs:
  using: composite
  steps:
    - name: Resolve inspected run's stage
      id: stage
      shell: bash
      run: |
        echo "record-stage=" >> "$GITHUB_OUTPUT"
    - name: Resolve inspected run's stage from its display name, when the record left it unresolved
      id: name-fallback
      shell: bash
      run: |
        case "$RUN_NAME" in
          "Wing Commander · 1 intake") name_stage="intake" ;;
          "Wing Commander · 5 implement") name_stage="implement" ;;
        esac
        echo "resolved-stage=$name_stage" >> "$GITHUB_OUTPUT"
"""

MINIMAL_CLEAN_WATCHDOG = """\
name: Wing Commander · 8 watchdog
on: workflow_call
jobs:
  collect:
    runs-on: ubuntu-latest
    steps:
      - name: "Collect: branch drift"
        id: collect-branch-drift
        shell: bash
        run: |
          case "$RESOLVED_STAGE" in
            plan|tasks|implement) ;;
            *) exit 0 ;;
          esac
      - name: Agent run metrics summary
        uses: ./.wing-commander-pipeline/.github/actions/wing-commander-metrics-summary
        with:
          stage: watchdog
          spec-identity-is-own: 'false'
"""


def self_test_main():
    bad = 0

    # Fixture 1 — a clean pass.
    v, e = run_check(MINIMAL_CLEAN_WATCHDOG, MINIMAL_CLEAN_COMPOSITE,
                      {"watchdog.yml": MINIMAL_CLEAN_WATCHDOG})
    if v or e:
        bad += 1
        print(f"[FAIL] fixture 1 (clean pass): expected no findings, got {v + e}")
    else:
        print("[ok] fixture 1: clean pass produces no findings")

    # Fixture 2 — a reference name reintroduced as a case condition outside
    # name-fallback.
    regressed_watchdog = MINIMAL_CLEAN_WATCHDOG.replace(
        'case "$RESOLVED_STAGE" in\n            plan|tasks|implement) ;;',
        'case "$RUN_NAME" in\n            "Wing Commander · 5 implement") ;;')
    if regressed_watchdog == MINIMAL_CLEAN_WATCHDOG:
        bad += 1
        print("[FAIL] fixture 2 setup: the regression replacement did not apply")
    else:
        v, e = run_check(regressed_watchdog, MINIMAL_CLEAN_COMPOSITE,
                          {"watchdog.yml": regressed_watchdog})
        if not v or e:
            bad += 1
            print(f"[FAIL] fixture 2 (reintroduced match): expected a violation, "
                  f"got violations={v} errors={e}")
        else:
            print(f"[ok] fixture 2: reintroduced reference-name case arm caught: {v}")

    # Fixture 3 — a reference name inside name-fallback itself: passes.
    v, e = run_check(MINIMAL_CLEAN_WATCHDOG, MINIMAL_CLEAN_COMPOSITE,
                      {"watchdog.yml": MINIMAL_CLEAN_WATCHDOG})
    if v or e:
        bad += 1
        print(f"[FAIL] fixture 3 (inside name-fallback): expected no findings "
              f"(the permitted site), got {v + e}")
    else:
        print("[ok] fixture 3: matches inside name-fallback are permitted")

    # Fixture 4 — a metrics-summary call site missing spec-identity-is-own:.
    missing_key_watchdog = MINIMAL_CLEAN_WATCHDOG.replace(
        "          spec-identity-is-own: 'false'\n", "")
    if missing_key_watchdog == MINIMAL_CLEAN_WATCHDOG:
        bad += 1
        print("[FAIL] fixture 4 setup: the key-removal replacement did not apply")
    else:
        v, e = run_check(MINIMAL_CLEAN_WATCHDOG, MINIMAL_CLEAN_COMPOSITE,
                          {"watchdog.yml": missing_key_watchdog})
        if not v or e:
            bad += 1
            print(f"[FAIL] fixture 4 (missing spec-identity-is-own): expected a "
                  f"violation, got violations={v} errors={e}")
        else:
            print(f"[ok] fixture 4: missing spec-identity-is-own: caught: {v}")

    # Fixture 5 — the name-fallback step renamed/removed: the gate errors.
    removed_step_composite = MINIMAL_CLEAN_COMPOSITE.replace("id: name-fallback\n", "id: renamed-step\n")
    if removed_step_composite == MINIMAL_CLEAN_COMPOSITE:
        bad += 1
        print("[FAIL] fixture 5 setup: the id rename did not apply")
    else:
        v, e = run_check(MINIMAL_CLEAN_WATCHDOG, removed_step_composite,
                          {"watchdog.yml": MINIMAL_CLEAN_WATCHDOG})
        if not e:
            bad += 1
            print(f"[FAIL] fixture 5 (name-fallback step removed): expected this "
                  f"gate to error rather than silently report zero violations, "
                  f"got violations={v} errors={e}")
        else:
            print(f"[ok] fixture 5: a removed/renamed name-fallback step errors: {e}")

    print(f"Gate 138 self-test: {'FAILED' if bad else 'all 5 fixtures behaved as specified'}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
