#!/usr/bin/env python3
"""The gate-suite sites spec 095 contains, in one place.

Read by verify-gate-suite-credential-free.py (FR-001/FR-005/FR-006) and
verify-snapshot-integrity-statement.py (FR-007/FR-008), so the list of
sites, and the one site deferred, cannot drift between the two gates.

SITES maps each verdict site (contracts/gate-verdict.schema.json) to the
workflow, the credential-free job that runs the suite there, and the job
that reads its verdict. EXEMPT_GATE_SUITE_SITES lists a step that still
runs the suite inside a credential-bearing job, with the issue that
records the deferral (Gate 124 holds the citation open).
"""
import re
from collections import namedtuple

Site = namedtuple("Site", "workflow gate_job reader")

SITES = {
    "board-fix": Site("board-loop.yml", "gate-suite-fix", "fix"),
    "board-review-fixup": Site("board-loop.yml", "gate-suite-review-fixup",
                               "review-fixup-publish"),
    "implement-cycle": Site("implement.yml", "gate-suite-implement-cycle", "implement"),
}

# Every job in these workflows runs an agent and later acts with the App
# token, or feeds one that does (FR-005).
COVERED_WORKFLOWS = ("board-loop.yml", "implement.yml", "pr-conversation.yml")

CONTAINED_COMPOSITE = "wing-commander-contained-gate-suite"
SUITE_CALL = "run-local-gates.py"

Exemption = namedtuple("Exemption", "reason issue permanent permanent_reason decided_by",
                       defaults=(False, None, ()))

# (workflow, job, step id) -> Exemption.
EXEMPT_GATE_SUITE_SITES = {
    ("implement.yml", "implement", "gate-suite-retry"): Exemption(
        reason=(
            "implement's retry-leg suite runs after the cycle agent, inside the "
            "job that holds the App token; containing it means splitting the "
            "retry chain into a job of its own (spec 095 research R6, tasks.md "
            "T015), deferred together with agent-invoked gates"),
        issue=(737,),
    ),
}


# A shell line that invokes the suite (not one that merely names it in prose
# or a quoted prompt): the interpreter starts the command.
SUITE_INVOCATION_RE = re.compile(
    r"^\s*(?:if\s+!?\s*|\(\s*|timeout\s+\S+\s+|exec\s+|cd\s+\S+\s*&&\s*)*"
    r"(?:\S*/)?python3?(?:\.\d+)?\s+(?:-\S+\s+)*\S*run-local-gates\.py\b", re.MULTILINE)
COMMENT_LINE_RE = re.compile(r"^[ \t]*#[^\n]*$", re.MULTILINE)


def suite_steps(job):
    """(step id or name, how) for every step of a parsed job that runs the
    gate suite: through the contained composite, or a run: line that
    invokes run-local-gates.py (whole-line comments skipped)."""
    found = []
    for step in (job or {}).get("steps") or []:
        if not isinstance(step, dict):
            continue
        key = step.get("id") or step.get("name") or "?"
        if CONTAINED_COMPOSITE in str(step.get("uses", "")):
            found.append((key, "uses " + CONTAINED_COMPOSITE))
        run = COMMENT_LINE_RE.sub("", str(step.get("run", "")))
        if SUITE_INVOCATION_RE.search(run):
            found.append((key, "runs " + SUITE_CALL))
    return found
