#!/usr/bin/env python3
"""Gate 129 -- spec-cross-reference's Over-rated example still describes
board-loop.yml's actual concurrency shape (specs/089-skill-example-drift).

WHY THIS EXISTS
---------------
.claude/skills/spec-cross-reference/SKILL.md's Over-rated example refutes a
hypothesized board-loop race by quoting a structural guarantee about
board-loop.yml's concurrency configuration: the job range that joins
`wing-commander-board-loop`, and the directed-proof group that is the only
run allowed to overlap them. That quote is a claim about a file the skill
does not own -- nothing failed when spec 060 changed the workflow-level
block into per-job groups (#490) until this gate existed (issue #658). This
script is the mechanical owner FR-002 requires for that one quote: it
extracts the claim from SKILL.md, the authoritative per-job classification
from specs/060-self-redrive-concurrency/contracts/concurrency-groups.md,
and the real per-job concurrency: blocks from board-loop.yml itself, then
fails loudly on any divergence, per
specs/089-skill-example-drift/contracts/skill-drift-gate.md.
"""
import argparse
import collections
import json
import os
import re
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SKILL_MD = os.path.join(REPO_ROOT, ".claude", "skills", "spec-cross-reference", "SKILL.md")
CONCURRENCY_GROUPS_MD = os.path.join(
    REPO_ROOT, "specs", "060-self-redrive-concurrency", "contracts", "concurrency-groups.md")
BOARD_LOOP_YML = os.path.join(REPO_ROOT, ".github", "workflows", "board-loop.yml")
DRIFT_WAIVERS_PATH = os.path.join(
    REPO_ROOT, ".github", "scripts", "skill-example-drift-waivers.json")

# The Over-rated example's anchor phrase (spec-cross-reference/SKILL.md).
ANCHOR = "**Over-rated.**"

SkillClaim = collections.namedtuple(
    "SkillClaim",
    ["job_range_start", "job_range_end", "ordinary_group", "directed_group",
     "queues_not_cancels", "location"])

JobClassification = collections.namedtuple(
    "JobClassification",
    ["job", "can_select_or_open_fix_pr", "expected_group_ordinary",
     "expected_group_directed", "expected_cancel_in_progress"])

WorkflowConcurrencyFact = collections.namedtuple(
    "WorkflowConcurrencyFact",
    ["job", "group_literal", "group_expression", "cancel_in_progress", "line"])

DriftFinding = collections.namedtuple(
    "DriftFinding",
    ["property", "job", "skill_location", "workflow_location", "expected", "actual"])

WaiverEntry = collections.namedtuple(
    "WaiverEntry", ["index", "property", "job", "issue", "permanent", "reason"])

# The conditional group shape prove-gate/prove use (research.md D5): resolves
# to the directed-proof group when a directed dispatch names a stage, the
# ordinary group otherwise. Matched structurally, not evaluated generically.
DIRECTED_EXPR_RE = re.compile(
    r"directed-stage\s*!=\s*''\s*\)\s*&&\s*'([\w.-]+)'\s*\|\|\s*'([\w.-]+)'")

# Item 4 (contracts/skill-example-claim.md "Verification"): a queuing/
# cancellation word in the same paragraph as the group tokens.
QUEUE_WORD_RE = re.compile(r"queue|cancel", re.IGNORECASE)

# Item 5: the literal script path, required within two paragraphs of the
# anchor (contracts/skill-example-claim.md "Verification").
SCRIPT_PATH_TOKEN = ".github/scripts/verify-skill-board-loop-concurrency-claim.py"


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _collapse_ws(text):
    return re.sub(r"\s+", " ", text).strip()


def extract_skill_claim(text, path):
    """-> (SkillClaim, None) or (None, DriftFinding) -- a missing anchor or
    any missing token is a loud subject-missing finding, never a raise
    (research.md D3, contracts/skill-example-claim.md "Verification")."""
    idx = text.find(ANCHOR)
    if idx == -1:
        return None, DriftFinding(
            property="subject-missing", job=None,
            skill_location=(path, None), workflow_location=(path, None),
            expected="an Over-rated example paragraph ({0!r}) naming the job "
                     "range and both concurrency groups".format(ANCHOR),
            actual="no {0!r} anchor found in {1}".format(
                ANCHOR, os.path.relpath(path, REPO_ROOT)))

    line_no = text.count("\n", 0, idx) + 1
    end = text.find("\n\n", idx)
    paragraph = text[idx:end if end != -1 else len(text)]
    collapsed = _collapse_ws(paragraph)

    # Item 5's window: the anchor paragraph plus the one after it (contracts/
    # skill-example-claim.md "Verification" -- "within two paragraphs").
    if end != -1:
        second_end = text.find("\n\n", end + 2)
        two_paragraph_window = text[idx:second_end if second_end != -1 else len(text)]
    else:
        two_paragraph_window = paragraph

    range_match = re.search(r"`([\w.-]+)`\s+through\s+`([\w.-]+)`", collapsed)
    ordinary_match = re.search(r"joins\s+`([\w.-]+)`", collapsed)
    directed_match = re.search(r"directed proof run in\s+`([\w.-]+)`", collapsed)
    has_queue_word = QUEUE_WORD_RE.search(collapsed) is not None
    has_script_pointer = SCRIPT_PATH_TOKEN in two_paragraph_window

    missing = []
    if not range_match:
        missing.append("a job-range phrase shaped '`X` through `Y`'")
    if not ordinary_match:
        missing.append("an ordinary group token shaped 'joins `GROUP`'")
    if not directed_match:
        missing.append("a directed group token shaped 'directed proof run in `GROUP`'")
    if not has_queue_word:
        missing.append("a queuing/cancellation word ('queue' or 'cancel') in the "
                        "Over-rated paragraph")
    if not has_script_pointer:
        missing.append("the literal script path '{0}' within two paragraphs of "
                        "the anchor".format(SCRIPT_PATH_TOKEN))
    if missing:
        rel_path = os.path.relpath(path, REPO_ROOT)
        return None, DriftFinding(
            property="subject-missing", job=None,
            skill_location=(path, line_no), workflow_location=(path, line_no),
            expected="the Over-rated paragraph starting at {0}:{1} to carry {2}".format(
                rel_path, line_no, "; ".join(missing)),
            actual="a paragraph without it")

    return SkillClaim(
        job_range_start=range_match.group(1),
        job_range_end=range_match.group(2),
        ordinary_group=ordinary_match.group(1),
        directed_group=directed_match.group(1),
        queues_not_cancels=has_queue_word,
        location=(path, line_no),
    ), None


# The "Groups, per job" table's data rows (contracts/concurrency-groups.md):
# job names in column 1, ordinary/directed group tokens and the
# cancel-in-progress literal in columns 2-4. Read as-is -- never re-derived
# from board-loop.yml's own job names (research.md D4).
TABLE_ROW_RE = re.compile(
    r"^\|(?P<jobs>[^|]+)\|(?P<ordinary>[^|]+)\|(?P<directed>[^|]+)\|(?P<cancel>[^|]+)\|\s*$",
    re.MULTILINE)


def extract_job_classifications(text):
    """-> [JobClassification, ...] from concurrency-groups.md's "Groups, per
    job" table (research.md D4, data-model.md JobClassification)."""
    heading_idx = text.find("## Groups, per job")
    if heading_idx == -1:
        return []
    table_text = text[heading_idx:]

    classifications = []
    for match in TABLE_ROW_RE.finditer(table_text):
        jobs = re.findall(r"`([\w.-]+)`", match.group("jobs"))
        if not jobs:
            continue  # header/separator row
        ordinary_tokens = re.findall(r"`([\w.-]+)`", match.group("ordinary"))
        if not ordinary_tokens:
            continue
        directed_cell = match.group("directed")
        directed_tokens = re.findall(r"`([\w.-]+)`", directed_cell)
        expected_directed = (
            directed_tokens[0] if directed_tokens and "n/a" not in directed_cell.lower()
            else None)
        cancel_tokens = re.findall(r"`(true|false)`", match.group("cancel"))
        expected_cancel = cancel_tokens[0] == "true" if cancel_tokens else False
        for job in jobs:
            classifications.append(JobClassification(
                job=job,
                can_select_or_open_fix_pr=True,
                expected_group_ordinary=ordinary_tokens[0],
                expected_group_directed=expected_directed,
                expected_cancel_in_progress=expected_cancel,
            ))
    return classifications


# Each job's own top-level key under board-loop.yml's `jobs:` map (2-space
# indented). Restricted to text after `jobs:` so `on:`'s own 2-space-indented
# trigger keys (schedule:, workflow_dispatch:, ...) are never mistaken for
# job blocks.
JOB_KEY_RE = re.compile(r"^  ([A-Za-z0-9_-]+):\s*$", re.MULTILINE)
CONCURRENCY_BLOCK_RE = re.compile(
    r"\n {4}concurrency:\n {6}group:(?P<group>.*?)\n {6}cancel-in-progress:\s*(?P<cancel>true|false)",
    re.DOTALL)


def extract_workflow_concurrency_facts(text):
    """-> {job: WorkflowConcurrencyFact} for every job board-loop.yml
    declares (research.md D5, data-model.md WorkflowConcurrencyFact) --
    parsed from each job's own `concurrency:` block, never its preceding
    comment (Gate 101 already owns the comment text)."""
    jobs_idx = text.find("\njobs:\n")
    if jobs_idx == -1:
        return {}
    base_offset = jobs_idx + 1
    jobs_text = text[base_offset:]
    base_line = text.count("\n", 0, base_offset)

    job_starts = [(m.group(1), m.start()) for m in JOB_KEY_RE.finditer(jobs_text)]
    facts = collections.OrderedDict()
    for i, (job, start) in enumerate(job_starts):
        end = job_starts[i + 1][1] if i + 1 < len(job_starts) else len(jobs_text)
        block = jobs_text[start:end]
        line_no = base_line + jobs_text.count("\n", 0, start) + 1

        match = CONCURRENCY_BLOCK_RE.search(block)
        if not match:
            facts[job] = WorkflowConcurrencyFact(
                job=job, group_literal=None, group_expression=None,
                cancel_in_progress=None, line=line_no)
            continue

        concurrency_line = line_no + block.count("\n", 0, match.start())
        raw_group = match.group("group").strip()
        cancel_in_progress = match.group("cancel") == "true"
        if raw_group.startswith(">-") or raw_group.startswith("|"):
            expr = _collapse_ws(raw_group[2:])
            facts[job] = WorkflowConcurrencyFact(
                job=job, group_literal=None, group_expression=expr,
                cancel_in_progress=cancel_in_progress, line=concurrency_line)
        else:
            literal = raw_group.strip("'\"")
            facts[job] = WorkflowConcurrencyFact(
                job=job, group_literal=literal, group_expression=None,
                cancel_in_progress=cancel_in_progress, line=concurrency_line)
    return facts


def compute_drift_findings(claim, classifications, facts):
    """-> [DriftFinding, ...] (contracts/skill-drift-gate.md "Algorithm"
    steps 4-6)."""
    findings = []
    class_by_job = {c.job: c for c in classifications}
    capable_jobs = set(class_by_job)

    for job, c in class_by_job.items():
        fact = facts.get(job)
        if fact is None:
            findings.append(DriftFinding(
                property="job-missing-from-group", job=job,
                skill_location=claim.location,
                workflow_location=(BOARD_LOOP_YML, None),
                expected="a concurrency: block joining `{0}`".format(c.expected_group_ordinary),
                actual="job '{0}' not found in board-loop.yml".format(job)))
            continue
        if fact.cancel_in_progress is None:
            findings.append(DriftFinding(
                property="job-missing-from-group", job=job,
                skill_location=claim.location,
                workflow_location=(BOARD_LOOP_YML, fact.line),
                expected="a concurrency: block joining `{0}`".format(c.expected_group_ordinary),
                actual="no concurrency: block on job '{0}'".format(job)))
            continue

        if fact.group_expression is not None:
            expr_match = DIRECTED_EXPR_RE.search(fact.group_expression)
            if not expr_match or expr_match.group(1) != c.expected_group_directed \
                    or expr_match.group(2) != c.expected_group_ordinary:
                findings.append(DriftFinding(
                    property="directed-group-mismatch", job=job,
                    skill_location=claim.location,
                    workflow_location=(BOARD_LOOP_YML, fact.line),
                    expected="a conditional expression resolving to `{0}` when directed, "
                             "`{1}` otherwise".format(
                                 c.expected_group_directed, c.expected_group_ordinary),
                    actual=fact.group_expression))
        elif fact.group_literal != c.expected_group_ordinary:
            findings.append(DriftFinding(
                property="job-missing-from-group", job=job,
                skill_location=claim.location,
                workflow_location=(BOARD_LOOP_YML, fact.line),
                expected="group `{0}`".format(c.expected_group_ordinary),
                actual="group `{0}`".format(fact.group_literal)))

        if fact.cancel_in_progress != c.expected_cancel_in_progress:
            findings.append(DriftFinding(
                property="cancel-in-progress-mismatch", job=job,
                skill_location=claim.location,
                workflow_location=(BOARD_LOOP_YML, fact.line),
                expected="cancel-in-progress: {0}".format(
                    str(c.expected_cancel_in_progress).lower()),
                actual="cancel-in-progress: {0}".format(str(fact.cancel_in_progress).lower())))

    for job, fact in facts.items():
        if job in capable_jobs:
            continue
        # Exact-token comparison (PR #813 review, T040): a substring test
        # here would falsely flag a future non-capable job whose group name
        # merely contains the claimed group as a substring, e.g.
        # `wing-commander-board-loop-watchdog`.
        if fact.group_literal is not None and "${{" in fact.group_literal:
            # A one-line `group: ${{ ... }}` is parsed as a literal; read
            # its quoted tokens the same way as a block expression.
            group_tokens = set(re.findall(r"'([\w.-]+)'", fact.group_literal))
        elif fact.group_literal is not None:
            group_tokens = {fact.group_literal}
        elif fact.group_expression is not None:
            group_tokens = set(re.findall(r"'([\w.-]+)'", fact.group_expression))
        else:
            group_tokens = set()
        if claim.ordinary_group in group_tokens or claim.directed_group in group_tokens:
            findings.append(DriftFinding(
                property="unexpected-job-in-group", job=job,
                skill_location=claim.location,
                workflow_location=(BOARD_LOOP_YML, fact.line),
                expected="neither `{0}` nor `{1}`".format(
                    claim.ordinary_group, claim.directed_group),
                actual="group `{0}`".format(
                    fact.group_literal or fact.group_expression or "")))

    # Group-name comparison (PR #813 review, T022): confirms the claim's own
    # ordinary_group/directed_group tokens have not gone stale under a
    # coordinated rename that leaves concurrency-groups.md and board-loop.yml
    # agreeing with each other but not with SKILL.md -- the per-job loop
    # above only ever compares a job's real group against the table's
    # expected name, never either of those against what the skill claims.
    if class_by_job:
        real_ordinary = next(iter(class_by_job.values())).expected_group_ordinary
        if claim.ordinary_group != real_ordinary:
            findings.append(DriftFinding(
                property="ordinary-group-name-mismatch", job=None,
                skill_location=claim.location,
                workflow_location=(CONCURRENCY_GROUPS_MD, None),
                expected="ordinary group `{0}`".format(claim.ordinary_group),
                actual="ordinary group `{0}`".format(real_ordinary)))
        # Sourced only from jobs board-loop.yml itself gives a conditional
        # `group:` expression (prove-gate/prove): other capable rows' own
        # "directed" table cell carries directed-*reachability* footnote
        # tokens (e.g. `triage`/`review`/`readiness`), not the directed
        # group's own name, so using those here would pick the wrong token.
        real_directed = next(
            (class_by_job[job].expected_group_directed
             for job, fact in facts.items()
             if fact.group_expression is not None and job in class_by_job
             and class_by_job[job].expected_group_directed),
            None)
        if real_directed is not None and claim.directed_group != real_directed:
            findings.append(DriftFinding(
                property="directed-group-name-mismatch", job=None,
                skill_location=claim.location,
                workflow_location=(CONCURRENCY_GROUPS_MD, None),
                expected="directed group `{0}`".format(claim.directed_group),
                actual="directed group `{0}`".format(real_directed)))

    # Job-range comparison (step 6): the unconditional (literal-group)
    # capable jobs only -- prove-gate/prove are conditionally split and are
    # covered by the directed-group-mismatch check above instead, per
    # research.md D4's three-way split.
    unconditional_capable_order = [
        job for job in facts
        if job in capable_jobs and facts[job].group_expression is None
    ]
    if unconditional_capable_order:
        actual_first = unconditional_capable_order[0]
        actual_last = unconditional_capable_order[-1]
        if claim.job_range_start != actual_first or claim.job_range_end != actual_last:
            findings.append(DriftFinding(
                property="job-range-mismatch", job=None,
                skill_location=claim.location,
                workflow_location=(BOARD_LOOP_YML, None),
                expected="`{0}` through `{1}`".format(
                    claim.job_range_start, claim.job_range_end),
                actual="`{0}` through `{1}`".format(actual_first, actual_last)))

    return findings


def _loc(path_line):
    path, line = path_line
    rel = os.path.relpath(path, REPO_ROOT)
    return "{0}:{1}".format(rel, line) if line else rel


def format_finding(finding):
    """-> the FR-006 failure message shape (contracts/skill-drift-gate.md
    "Failure message shape"): names the property, the job, both locations,
    expected/actual, and the waive-or-fix instruction. The workflow-side
    label is derived from the finding's own workflow_location path (T035)
    -- board-loop.yml for most properties, but concurrency-groups.md for
    the two group-name-mismatch properties, and SKILL.md itself for a
    SKILL.md-internal subject-missing finding -- never a hardcoded literal
    naming the wrong file."""
    job_clause = " for job '{0}'".format(finding.job) if finding.job else ""
    workflow_label = os.path.basename(finding.workflow_location[0])
    return (
        "::error::verify-skill-board-loop-concurrency-claim: {property}{job_clause} "
        "-- SKILL.md ({skill_loc}) claims {expected}; {workflow_label} ({workflow_loc}) "
        "has {actual}. Waive with a skill-example-drift-waivers.json entry "
        "naming property \"{property}\" and job {job_json}, and a tracking issue, "
        "or fix the drift.".format(
            property=finding.property, job_clause=job_clause,
            skill_loc=_loc(finding.skill_location), expected=finding.expected,
            workflow_label=workflow_label,
            workflow_loc=_loc(finding.workflow_location), actual=finding.actual,
            job_json=("\"{0}\"".format(finding.job) if finding.job else "null")))


def evaluate():
    """-> (findings, ok_properties) for the real tree: reads all three
    source files, computes the DriftFinding set (contracts/skill-drift-gate.md
    "Algorithm" steps 1-6). A missing/unreadable source file is itself a loud
    subject-missing finding, never a silent skip."""
    findings = []
    claim = classifications = facts = None

    if not os.path.isfile(SKILL_MD):
        findings.append(DriftFinding(
            property="subject-missing", job=None,
            skill_location=(SKILL_MD, None), workflow_location=(SKILL_MD, None),
            expected="{0} to exist".format(os.path.relpath(SKILL_MD, REPO_ROOT)),
            actual="file not found"))
    else:
        claim, missing = extract_skill_claim(_read(SKILL_MD), SKILL_MD)
        if missing:
            findings.append(missing)

    if not os.path.isfile(CONCURRENCY_GROUPS_MD):
        findings.append(DriftFinding(
            property="subject-missing", job=None,
            skill_location=(SKILL_MD, None), workflow_location=(CONCURRENCY_GROUPS_MD, None),
            expected="{0} to exist".format(os.path.relpath(CONCURRENCY_GROUPS_MD, REPO_ROOT)),
            actual="file not found"))
    else:
        classifications = extract_job_classifications(_read(CONCURRENCY_GROUPS_MD))
        if not classifications:
            findings.append(DriftFinding(
                property="subject-missing", job=None,
                skill_location=(SKILL_MD, None),
                workflow_location=(CONCURRENCY_GROUPS_MD, None),
                expected="a non-empty 'Groups, per job' table",
                actual="no classification rows found"))

    if not os.path.isfile(BOARD_LOOP_YML):
        findings.append(DriftFinding(
            property="subject-missing", job=None,
            skill_location=(SKILL_MD, None), workflow_location=(BOARD_LOOP_YML, None),
            expected="{0} to exist".format(os.path.relpath(BOARD_LOOP_YML, REPO_ROOT)),
            actual="file not found"))
    else:
        facts = extract_workflow_concurrency_facts(_read(BOARD_LOOP_YML))
        if not facts:
            findings.append(DriftFinding(
                property="subject-missing", job=None,
                skill_location=(SKILL_MD, None), workflow_location=(BOARD_LOOP_YML, None),
                expected="a readable jobs: map", actual="no jobs found"))

    ok_properties = []
    all_properties = (
        "job-missing-from-group", "cancel-in-progress-mismatch",
        "unexpected-job-in-group", "job-range-mismatch", "directed-group-mismatch",
        "ordinary-group-name-mismatch", "directed-group-name-mismatch")
    if claim is not None and classifications and facts:
        drift = compute_drift_findings(claim, classifications, facts)
        findings.extend(drift)
        drifted = set(f.property for f in drift)
        ok_properties = [p for p in all_properties if p not in drifted]

    return findings, ok_properties


def load_waiver_entries(path):
    """-> [WaiverEntry, ...] from skill-example-drift-waivers.json
    (data-model.md WaiverEntry). Schema validity (issue XOR permanent) is
    Gate 124's job; this only reads the two fields this gate's own
    stale-check keys on."""
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    entries = []
    for index, w in enumerate(data.get("waivers", [])):
        entries.append(WaiverEntry(
            index=index, property=w.get("property"), job=w.get("job"),
            issue=w.get("issue"), permanent=w.get("permanent"), reason=w.get("reason")))
    return entries


def apply_waivers(findings, waivers):
    """-> (blocking, waived_lines, stale) (contracts/skill-drift-gate.md
    "Algorithm" step 7): a finding matching a waiver's {property, job} is
    waived (still reported, not blocking); a waiver matching no current
    finding is itself a blocking stale-waiver failure (FR-014)."""
    blocking = []
    waived_lines = []
    matched = set()
    for finding in findings:
        match = next(
            (w for w in waivers if w.property == finding.property and w.job == finding.job),
            None)
        if match is None:
            blocking.append(finding)
            continue
        matched.add(match.index)
        label = match.issue if match.issue else "a permanent waiver"
        waived_lines.append("waived: {0} ({1}), see {2}".format(
            finding.property, finding.job, label))
    stale = [w for w in waivers if w.index not in matched]
    return blocking, waived_lines, stale


def format_stale_waiver(waiver):
    return (
        "::error::verify-skill-board-loop-concurrency-claim: stale waiver -- "
        "{0} entry {1} ({2}, job={3}) no longer matches any current divergence; "
        "remove it now that the skill and board-loop.yml agree again.".format(
            os.path.relpath(DRIFT_WAIVERS_PATH, REPO_ROOT), waiver.index,
            waiver.property, waiver.job))


def run():
    findings, ok_properties = evaluate()
    waivers = load_waiver_entries(DRIFT_WAIVERS_PATH)
    blocking, waived_lines, stale = apply_waivers(findings, waivers)

    for prop in ok_properties:
        print("[ok] {0}: board-loop.yml matches the skill's claim".format(prop))
    for finding in blocking:
        print(format_finding(finding))
    for line in waived_lines:
        print(line)
    for waiver in stale:
        print(format_stale_waiver(waiver))

    total = len(blocking) + len(stale)
    print("verify-skill-board-loop-concurrency-claim: {0} failure(s).".format(total))
    return 1 if total else 0


def run_selftest():
    """Synthetic fixtures only, never the real SKILL.md/board-loop.yml
    (contracts/skill-drift-gate.md "Self-test"): the waiver stale-check in
    both directions (research.md D9's waiver bullet, "Waiver interaction")."""
    failures = []

    def check(label, condition):
        if condition:
            print("[ok] self-test: {0}".format(label))
        else:
            failures.append(label)
            print("::error::verify-skill-board-loop-concurrency-claim --self-test: "
                  "{0} failed.".format(label))

    fixture_finding = DriftFinding(
        property="job-missing-from-group", job="fix",
        skill_location=("fixture-skill.md", 1), workflow_location=("fixture-workflow.yml", 1),
        expected="job 'fix' joins `wing-commander-board-loop`",
        actual="job 'fix' has no concurrency: block")

    # An empty waiver set: the divergence blocks.
    blocking, waived_lines, stale = apply_waivers([fixture_finding], [])
    check("an unwaived divergence blocks",
          blocking == [fixture_finding] and not waived_lines and not stale)

    # A matching waiver: the divergence is waived (still reported), not blocking.
    waiver = WaiverEntry(index=0, property="job-missing-from-group", job="fix",
                          issue="#1", permanent=None, reason="fixture")
    blocking, waived_lines, stale = apply_waivers([fixture_finding], [waiver])
    check("a matching waiver waives the divergence",
          not blocking and waived_lines == ["waived: job-missing-from-group (fix), see #1"]
          and not stale)

    # The fixture reverts to match (divergence closes) with the same waiver
    # entry still present: it is now stale and fails the gate.
    blocking, waived_lines, stale = apply_waivers([], [waiver])
    check("a waiver with no matching divergence is stale",
          not blocking and not waived_lines and stale == [waiver])

    # --- extract_skill_claim: subject-missing in both directions, plus a
    # reflow/typo-only change leaving extraction unaffected (FR-009). This
    # and the two extraction fixtures below exercise the functions the
    # waiver checks above never touch (T021, spec 089 Phase 7). ---
    canonical_claim_text = (
        "intro paragraph.\n\n"
        "- **Over-rated.** A hypothesized race looked plausible in "
        "isolation. Every job that can select an item or open a fix PR "
        "(`select` through `readiness`) joins `ordinary-group`, and the "
        "only run allowed to overlap them is a directed proof run in "
        "`directed-group`, which selects no item and opens no fix PR. A "
        "second run in that group queues rather than racing or "
        "cancelling it.\n\n"
        "Run .github/scripts/verify-skill-board-loop-concurrency-claim.py "
        "to settle currency.\n\n"
        "next paragraph."
    )
    claim, missing = extract_skill_claim(canonical_claim_text, "fixture-skill.md")
    check("a well-formed Over-rated paragraph extracts a SkillClaim",
          missing is None and claim is not None
          and claim.job_range_start == "select" and claim.job_range_end == "readiness"
          and claim.ordinary_group == "ordinary-group"
          and claim.directed_group == "directed-group"
          and claim.queues_not_cancels is True)

    reflowed_claim_text = (
        "intro paragraph.\n\n"
        "- **Over-rated.** A\n  hypothesizd    race looked plausible in "
        "isolation. Every job  that can select an item or\nopen a fix PR "
        "(`select`   through\n`readiness`) joins\n`ordinary-group`, and "
        "the only run allowed to overlap them is a directed  proof run "
        "in `directed-group`,\nwhich selects no item and opens no fix "
        "PR. A second  run in that\ngroup queues rather than racing or "
        "cancelling it.\n\n"
        "Run\n.github/scripts/verify-skill-board-loop-concurrency-claim.py "
        "to  settle currency.\n\n"
        "next paragraph."
    )
    reflowed_claim, reflowed_missing = extract_skill_claim(
        reflowed_claim_text, "fixture-skill.md")
    check("a reflow/typo-only change leaves the extracted claim unaffected",
          reflowed_missing is None and reflowed_claim is not None
          and reflowed_claim[:4] == claim[:4])

    no_claim, no_claim_missing = extract_skill_claim(
        "no over-rated example here at all.", "fixture-skill.md")
    check("a missing Over-rated anchor is a subject-missing finding",
          no_claim is None and no_claim_missing is not None
          and no_claim_missing.property == "subject-missing")

    # A SKILL.md-internal subject-missing finding names the skill file on
    # both sides and never leaks an absolute path (PR #813 review).
    abs_skill = os.path.join(REPO_ROOT, "fixture-skill.md")
    for case, text in (("a missing anchor", "no over-rated example here."),
                       ("a missing token", "- **Over-rated.** nothing else.")):
        _claim, internal_missing = extract_skill_claim(text, abs_skill)
        rendered = format_finding(internal_missing) if internal_missing else ""
        check("the subject-missing message for {0} names the skill file, "
              "not board-loop.yml, with a repo-relative path".format(case),
              "; fixture-skill.md (" in rendered
              and "board-loop.yml (" not in rendered
              and REPO_ROOT not in rendered)

    # --- extract_skill_claim: the two FR-008-driven checks contracts/
    # skill-example-claim.md's "Verification" adds as items 4-5 (T029) -- a
    # queuing/cancellation word in the same paragraph as the group tokens,
    # and the literal script path within two paragraphs of the anchor. Each
    # is required: absent either one, extraction itself fails loudly rather
    # than returning a SkillClaim with a false queues_not_cancels (T030). ---
    missing_queue_text = (
        "intro paragraph.\n\n"
        "- **Over-rated.** Every job that can select an item or open a "
        "fix PR (`select` through `readiness`) joins `ordinary-group`, "
        "and the only run allowed to overlap them is a directed proof "
        "run in `directed-group`, which selects no item and opens no "
        "fix PR.\n\n"
        "Run .github/scripts/verify-skill-board-loop-concurrency-claim.py "
        "to settle currency.\n\n"
        "next paragraph."
    )
    missing_queue_claim, missing_queue_missing = extract_skill_claim(
        missing_queue_text, "fixture-skill.md")
    check("a paragraph missing the queuing/cancellation word is a "
          "subject-missing finding",
          missing_queue_claim is None and missing_queue_missing is not None
          and missing_queue_missing.property == "subject-missing")

    missing_pointer_text = (
        "intro paragraph.\n\n"
        "- **Over-rated.** Every job that can select an item or open a "
        "fix PR (`select` through `readiness`) joins `ordinary-group`, "
        "and the only run allowed to overlap them is a directed proof "
        "run in `directed-group`, which selects no item and opens no "
        "fix PR. A second run in that group queues rather than racing "
        "or cancelling it.\n\n"
        "No script pointer sentence here at all.\n\n"
        "next paragraph."
    )
    missing_pointer_claim, missing_pointer_missing = extract_skill_claim(
        missing_pointer_text, "fixture-skill.md")
    check("a paragraph missing the Gate pointer sentence is a "
          "subject-missing finding",
          missing_pointer_claim is None and missing_pointer_missing is not None
          and missing_pointer_missing.property == "subject-missing")

    # --- extract_job_classifications: a synthetic concurrency-groups.md
    # table extracts the expected per-job rows. ---
    table_fixture = (
        "## Groups, per job\n\n"
        "| Job | Ordinary group | Directed group | cancel-in-progress |\n"
        "|-----|-----------------|-----------------|---------------------|\n"
        "| `select` | `ordinary-group` | n/a | `false` |\n"
        "| `mid` | `ordinary-group` | n/a | `false` |\n"
        "| `readiness` | `ordinary-group` | n/a | `false` |\n"
        "| `prove` | `ordinary-group` | `directed-group` | `false` |\n"
    )
    fixture_classes = {c.job: c for c in extract_job_classifications(table_fixture)}
    check("a synthetic classification table extracts all four job rows",
          set(fixture_classes) == {"select", "mid", "readiness", "prove"})
    check("a table row with a directed group populates expected_group_directed",
          fixture_classes["prove"].expected_group_directed == "directed-group"
          and fixture_classes["select"].expected_group_directed is None)

    # --- extract_workflow_concurrency_facts: a synthetic board-loop.yml
    # extracts each job's own concurrency: block, keyed by job. ---
    workflow_fixture = (
        "name: fixture\n\n"
        "jobs:\n"
        "  select:\n"
        "    runs-on: ubuntu-latest\n"
        "    concurrency:\n"
        "      group: ordinary-group\n"
        "      cancel-in-progress: false\n"
        "    steps: []\n"
        "  prove:\n"
        "    runs-on: ubuntu-latest\n"
        "    concurrency:\n"
        "      group: >-\n"
        "        ${{ (needs.select.outputs.directed-stage != '') && "
        "'directed-group' || 'ordinary-group' }}\n"
        "      cancel-in-progress: false\n"
        "    steps: []\n"
        "  other-job:\n"
        "    runs-on: ubuntu-latest\n"
        "    steps: []\n"
    )
    fixture_facts = extract_workflow_concurrency_facts(workflow_fixture)
    check("a synthetic workflow extracts a literal group for an ordinary job",
          fixture_facts["select"].group_literal == "ordinary-group"
          and fixture_facts["select"].cancel_in_progress is False)
    check("a synthetic workflow extracts a conditional expression for a directed job",
          fixture_facts["prove"].group_expression is not None
          and DIRECTED_EXPR_RE.search(fixture_facts["prove"].group_expression) is not None)
    check("a job with no concurrency: block records cancel_in_progress=None",
          fixture_facts["other-job"].cancel_in_progress is None)

    # --- compute_drift_findings: a baseline where everything matches
    # produces no findings; one targeted mutation per property produces
    # exactly that DriftFinding (contracts/skill-drift-gate.md "Algorithm"
    # steps 4-6). ---
    base_claim = SkillClaim(
        job_range_start="select", job_range_end="readiness",
        ordinary_group="ordinary-group", directed_group="directed-group",
        queues_not_cancels=True, location=("fixture-skill.md", 1))
    base_classifications = [
        JobClassification(job="select", can_select_or_open_fix_pr=True,
                           expected_group_ordinary="ordinary-group",
                           expected_group_directed=None,
                           expected_cancel_in_progress=False),
        JobClassification(job="mid", can_select_or_open_fix_pr=True,
                           expected_group_ordinary="ordinary-group",
                           expected_group_directed=None,
                           expected_cancel_in_progress=False),
        JobClassification(job="readiness", can_select_or_open_fix_pr=True,
                           expected_group_ordinary="ordinary-group",
                           expected_group_directed=None,
                           expected_cancel_in_progress=False),
        JobClassification(job="prove", can_select_or_open_fix_pr=True,
                           expected_group_ordinary="ordinary-group",
                           expected_group_directed="directed-group",
                           expected_cancel_in_progress=False),
    ]

    def make_facts(overrides=None):
        base = collections.OrderedDict([
            ("select", WorkflowConcurrencyFact(
                job="select", group_literal="ordinary-group",
                group_expression=None, cancel_in_progress=False, line=10)),
            ("mid", WorkflowConcurrencyFact(
                job="mid", group_literal="ordinary-group",
                group_expression=None, cancel_in_progress=False, line=11)),
            ("readiness", WorkflowConcurrencyFact(
                job="readiness", group_literal="ordinary-group",
                group_expression=None, cancel_in_progress=False, line=12)),
            ("prove", WorkflowConcurrencyFact(
                job="prove", group_literal=None,
                group_expression=(
                    "(needs.select.outputs.directed-stage != '') && "
                    "'directed-group' || 'ordinary-group'"),
                cancel_in_progress=False, line=13)),
            ("other-job", WorkflowConcurrencyFact(
                job="other-job", group_literal="unrelated-group",
                group_expression=None, cancel_in_progress=False, line=14)),
        ])
        if overrides:
            base.update(overrides)
        return base

    baseline_findings = compute_drift_findings(base_claim, base_classifications, make_facts())
    check("a fully matching tree produces no drift findings", baseline_findings == [])

    missing_facts = make_facts()
    del missing_facts["mid"]
    missing_findings = compute_drift_findings(base_claim, base_classifications, missing_facts)
    check("a job absent from board-loop.yml is job-missing-from-group",
          [f.property for f in missing_findings] == ["job-missing-from-group"]
          and missing_findings[0].job == "mid")

    cancel_findings = compute_drift_findings(
        base_claim, base_classifications,
        make_facts({"mid": make_facts()["mid"]._replace(cancel_in_progress=True)}))
    check("a flipped cancel-in-progress is cancel-in-progress-mismatch",
          [f.property for f in cancel_findings] == ["cancel-in-progress-mismatch"]
          and cancel_findings[0].job == "mid")

    unexpected_findings = compute_drift_findings(
        base_claim, base_classifications,
        make_facts({"other-job": make_facts()["other-job"]._replace(
            group_literal="ordinary-group")}))
    check("a non-capable job placed in the claimed group is unexpected-job-in-group",
          [f.property for f in unexpected_findings] == ["unexpected-job-in-group"]
          and unexpected_findings[0].job == "other-job")

    substring_findings = compute_drift_findings(
        base_claim, base_classifications,
        make_facts({"other-job": make_facts()["other-job"]._replace(
            group_literal="ordinary-group-watchdog")}))
    oneline_expr_findings = compute_drift_findings(
        base_claim, base_classifications,
        make_facts({"other-job": make_facts()["other-job"]._replace(
            group_literal="${{ inputs.x && 'ordinary-group' || 'other' }}")}))
    check("a non-capable job whose one-line group expression names the claimed "
          "group is unexpected-job-in-group",
          [f.property for f in oneline_expr_findings] == ["unexpected-job-in-group"])

    check("a non-capable job's group name merely containing the claimed group "
          "as a substring is not unexpected-job-in-group (T040)",
          substring_findings == [])

    range_findings = compute_drift_findings(
        base_claim._replace(job_range_end="mid"), base_classifications, make_facts())
    check("a claimed range shorter than the actual last capable job is job-range-mismatch",
          [f.property for f in range_findings] == ["job-range-mismatch"])

    directed_findings = compute_drift_findings(
        base_claim, base_classifications,
        make_facts({"prove": make_facts()["prove"]._replace(group_expression=(
            "(needs.select.outputs.directed-stage != '') && "
            "'ordinary-group' || 'directed-group'"))}))
    check("a swapped conditional expression is directed-group-mismatch",
          [f.property for f in directed_findings] == ["directed-group-mismatch"]
          and directed_findings[0].job == "prove")

    # --- group-name comparison (PR #813 review, T022/T024): a coordinated
    # rename of the ordinary or directed group across concurrency-groups.md
    # and board-loop.yml, with SKILL.md's claim left unchanged, is caught as
    # a stale claim rather than passing because the two files still agree
    # with each other. ---
    renamed_ordinary_classifications = [
        c._replace(expected_group_ordinary="renamed-ordinary-group")
        for c in base_classifications
    ]
    renamed_ordinary_facts = make_facts({
        "select": make_facts()["select"]._replace(group_literal="renamed-ordinary-group"),
        "mid": make_facts()["mid"]._replace(group_literal="renamed-ordinary-group"),
        "readiness": make_facts()["readiness"]._replace(group_literal="renamed-ordinary-group"),
        "prove": make_facts()["prove"]._replace(group_expression=(
            "(needs.select.outputs.directed-stage != '') && "
            "'directed-group' || 'renamed-ordinary-group'")),
    })
    renamed_ordinary_findings = compute_drift_findings(
        base_claim, renamed_ordinary_classifications, renamed_ordinary_facts)
    check("a coordinated ordinary-group rename across concurrency-groups.md "
          "and board-loop.yml leaves SKILL.md's stale claim caught as "
          "ordinary-group-name-mismatch",
          [f.property for f in renamed_ordinary_findings] == ["ordinary-group-name-mismatch"])
    # Guarded (T038): an empty list here (e.g. a regression in the check
    # above) must record a failed check, not raise IndexError and abort the
    # self-test before it prints every later check or the summary line.
    renamed_ordinary_message = (
        format_finding(renamed_ordinary_findings[0]) if renamed_ordinary_findings else None)
    check("the rendered ordinary-group-name-mismatch message states SKILL.md's "
          "stale claim as the disagreement, not the reverse (T031)",
          renamed_ordinary_message is not None
          and "claims ordinary group `ordinary-group`" in renamed_ordinary_message
          and "has ordinary group `renamed-ordinary-group`" in renamed_ordinary_message)
    check("the rendered ordinary-group-name-mismatch message names "
          "concurrency-groups.md, not board-loop.yml, as the workflow-side "
          "label (T035)",
          renamed_ordinary_message is not None
          and "concurrency-groups.md (" in renamed_ordinary_message
          and "board-loop.yml (" not in renamed_ordinary_message)

    renamed_directed_classifications = [
        c._replace(expected_group_directed=(
            "renamed-directed-group" if c.expected_group_directed else None))
        for c in base_classifications
    ]
    renamed_directed_facts = make_facts({
        "prove": make_facts()["prove"]._replace(group_expression=(
            "(needs.select.outputs.directed-stage != '') && "
            "'renamed-directed-group' || 'ordinary-group'")),
    })
    renamed_directed_findings = compute_drift_findings(
        base_claim, renamed_directed_classifications, renamed_directed_facts)
    check("a coordinated directed-group rename across concurrency-groups.md "
          "and board-loop.yml leaves SKILL.md's stale claim caught as "
          "directed-group-name-mismatch",
          [f.property for f in renamed_directed_findings] == ["directed-group-name-mismatch"])
    # Guarded (T038): same reasoning as the ordinary-group fixture above.
    renamed_directed_message = (
        format_finding(renamed_directed_findings[0]) if renamed_directed_findings else None)
    check("the rendered directed-group-name-mismatch message states SKILL.md's "
          "stale claim as the disagreement, not the reverse (T031)",
          renamed_directed_message is not None
          and "claims directed group `directed-group`" in renamed_directed_message
          and "has directed group `renamed-directed-group`" in renamed_directed_message)
    check("the rendered directed-group-name-mismatch message names "
          "concurrency-groups.md, not board-loop.yml, as the workflow-side "
          "label (T035)",
          renamed_directed_message is not None
          and "concurrency-groups.md (" in renamed_directed_message
          and "board-loop.yml (" not in renamed_directed_message)

    total = len(failures)
    print("verify-skill-board-loop-concurrency-claim --self-test: {0} failure(s).".format(total))
    return 1 if total else 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    sys.exit(run_selftest() if args.self_test else run())


if __name__ == "__main__":
    main()
