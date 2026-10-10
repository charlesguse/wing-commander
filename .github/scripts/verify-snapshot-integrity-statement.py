#!/usr/bin/env python3
"""Gate 145 -- the snapshot's guarantee is stated exactly, and still true
(spec 095 FR-007..FR-010).

WHY THIS EXISTS
---------------
`$RUNNER_TEMP/wc-pristine` and `.wc-pristine-repo` are `chmod -R a-w`. That
reads as "unalterable by the agent", and it is not: the runner user can
chmod them back, and code it runs can append to $GITHUB_ENV/$GITHUB_PATH
for every later step. Spec 095 makes the guarantee hold another way -- no
step of a job that holds the App token executes agent-authored code; the
gate suite runs in a separate credential-free job -- and FR-009/FR-010
require the comment that documents the snapshot to say exactly that,
including what it assumes about the runner. This gate holds both the
statement and the fact it states.

WHAT IT CHECKS
--------------
In board-loop.yml:
  1. the comment directly above fix-agent's "Snapshot helper scripts"
     step (the canonical statement) says which steps the guarantee covers,
     that it rests on agent code running in a separate credential-free job
     sharing no $GITHUB_ENV or $GITHUB_PATH, and the runner assumption
     (a fresh virtual machine per job; a self-hosted runner must be
     ephemeral) -- REQUIRED_PHRASES, compared with whitespace collapsed;
  2. every other job's snapshot step points at that statement.
In implement.yml, the credential-free gate-suite job's comment points at
board-loop.yml for the runner assumption (T020).
In board-loop.yml and implement.yml, no job that pushes (a `git push` run:
line, or the hardened-push, publish-stranded-commits or fold-commit
composite) also runs the gate suite (wc_gate_suite_sites.suite_steps),
except a step EXEMPT_GATE_SUITE_SITES records.

--self-test runs the fixtures under fixtures/095-snapshot-statement/ (one
per failure branch, plus a passing one) and mutations of the shipped
workflows, and asserts each is caught for its own reason.

Usage: python3 .github/scripts/verify-snapshot-integrity-statement.py [--self-test]
"""
import os
import re
import sys

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from wc_gate_suite_sites import EXEMPT_GATE_SUITE_SITES, SITES, suite_steps  # noqa: E402

ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
WORKFLOWS = os.path.join(ROOT, ".github", "workflows")
FIXTURES = os.path.join(HERE, "fixtures", "095-snapshot-statement")
BOARD_LOOP = "board-loop.yml"
IMPLEMENT = "implement.yml"
CANONICAL_JOB = "fix-agent"
SNAPSHOT_STEP = "Snapshot helper scripts (before any agent runs)"
POINTER = "see the fix-agent job's \"Snapshot helper scripts\" step"
IMPLEMENT_POINTER = "-- see board-loop.yml"

# (what the statement must say, phrase) -- FR-009 then FR-010.
REQUIRED_PHRASES = (
    ("covered-steps", "it covers every step of this job after this one"),
    ("rests-on", "runs in a separate credential-free job"),
    ("rests-on", "shares no filesystem, $GITHUB_ENV or $GITHUB_PATH with this one"),
    ("not-read-only", "Read-only (chmod -R a-w) is not what makes it hold"),
    ("runner-assumption", "every job gets a fresh virtual machine"),
    ("runner-assumption", "on a self-hosted runner this protection holds only if the "
                          "runner is ephemeral"),
)
PUSH_USES = ("wing-commander-hardened-push", "wing-commander-publish-stranded-commits",
             "wing-commander-fold-commit")
RAW_PUSH_RE = re.compile(r"^[^#\n]*\bgit\s+(?:-\S+\s+)*push\b", re.MULTILINE)


def _norm(text):
    return re.sub(r"\s+", " ", text).strip()


def job_spans(text):
    """{job id: (first line index, end line index)} for top-level jobs."""
    lines = text.splitlines()
    starts = []
    in_jobs = False
    for i, line in enumerate(lines):
        if line.startswith("jobs:"):
            in_jobs = True
            continue
        if in_jobs:
            m = re.match(r"^  ([A-Za-z0-9_-]+):\s*$", line)
            if m:
                starts.append((m.group(1), i))
            elif line and not line.startswith(" ") and not line.startswith("#"):
                in_jobs = False
    spans = {}
    for n, (job, start) in enumerate(starts):
        end = starts[n + 1][1] if n + 1 < len(starts) else len(lines)
        spans[job] = (start, end)
    return spans


def comment_above(lines, idx):
    """The contiguous `#` comment lines directly above line `idx`."""
    out = []
    i = idx - 1
    while i >= 0 and lines[i].lstrip().startswith("#"):
        out.insert(0, lines[i].lstrip()[1:].strip())
        i -= 1
    return " ".join(out)


def snapshot_comments(text):
    """{job id: (comment directly above that job's snapshot step, every
    comment line in the job up to that step)}."""
    lines = text.splitlines()
    found = {}
    for job, (start, end) in job_spans(text).items():
        for i in range(start, end):
            if lines[i].strip() == "- name: " + SNAPSHOT_STEP:
                before = " ".join(l.lstrip()[1:].strip() for l in lines[start:i]
                                  if l.lstrip().startswith("#"))
                found[job] = (comment_above(lines, i), before)
    return found


def statement_problems(text, name=BOARD_LOOP):
    problems = []
    comments = snapshot_comments(text)
    if CANONICAL_JOB not in comments:
        return ["{0}: job {1!r} has no {2!r} step to carry the statement".format(
            name, CANONICAL_JOB, SNAPSHOT_STEP)]
    canonical = _norm(comments[CANONICAL_JOB][0])
    for what, phrase in REQUIRED_PHRASES:
        if _norm(phrase) not in canonical:
            problems.append("{0}: the snapshot comment in {1!r} is missing its {2} text "
                            "({3!r}) -- FR-009/FR-010".format(name, CANONICAL_JOB, what, phrase))
    for job, (_above, before) in sorted(comments.items()):
        if job != CANONICAL_JOB and POINTER not in _norm(before):
            problems.append("{0}: job {1!r}'s snapshot step does not point at the statement "
                            "({2!r})".format(name, job, POINTER))
    return problems


def implement_pointer_problems(text, name=IMPLEMENT):
    lines = text.splitlines()
    gate_job = next((s.gate_job for s in SITES.values() if s.workflow == name), None)
    if gate_job is None:
        return []
    span = job_spans(text).get(gate_job)
    if span is None:
        return ["{0}: no job {1!r}".format(name, gate_job)]
    if IMPLEMENT_POINTER not in _norm(comment_above(lines, span[0])):
        return ["{0}: job {1!r}'s comment does not point at the runner assumption "
                "({2!r}) -- FR-010".format(name, gate_job, IMPLEMENT_POINTER)]
    return []


def pushes(job):
    for step in (job or {}).get("steps") or []:
        if not isinstance(step, dict):
            continue
        if any(u in str(step.get("uses", "")) for u in PUSH_USES):
            return True
        if RAW_PUSH_RE.search(str(step.get("run", ""))):
            return True
    return False


def isolation_problems(doc, name, exempt=EXEMPT_GATE_SUITE_SITES):
    problems = []
    for job_id, job in ((doc or {}).get("jobs") or {}).items():
        steps = [k for k, _how in suite_steps(job) if (name, job_id, k) not in exempt]
        if steps and pushes(job):
            problems.append("{0}: job {1!r} runs the gate suite ({2}) and later pushes -- "
                            "agent-authored code must not run in a job that performs a "
                            "durable action (FR-007/FR-008)".format(name, job_id,
                                                                     ", ".join(steps)))
    return problems


def check(board_text, implement_text, exempt=EXEMPT_GATE_SUITE_SITES):
    problems = statement_problems(board_text) + implement_pointer_problems(implement_text)
    for name, text in ((BOARD_LOOP, board_text), (IMPLEMENT, implement_text)):
        try:
            doc = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            problems.append("{0}: does not parse: {1}".format(name, exc))
            continue
        problems += isolation_problems(doc, name, exempt)
    return problems


def _read(name, directory=WORKFLOWS):
    with open(os.path.join(directory, name), encoding="utf-8") as fh:
        return fh.read()


def run():
    problems = check(_read(BOARD_LOOP), _read(IMPLEMENT))
    for p in problems:
        print("::error::Gate 145: " + p)
    if problems:
        return 1
    print("Gate 145: the snapshot statement names what it covers, what it rests on and "
          "the runner it assumes, and no job that runs the gate suite pushes.")
    return 0


FIXTURE_CASES = (
    ("good.yml", None),
    ("missing-covered-steps.yml", "covered-steps"),
    ("missing-runner-assumption.yml", "runner-assumption"),
    ("agent-code-pushes.yml", "later pushes"),
    ("missing-pointer.yml", "does not point at the statement"),
)


def self_test():
    failures = []
    implement_text = _read(IMPLEMENT)
    for name, expect in FIXTURE_CASES:
        text = _read(name, FIXTURES)
        got = statement_problems(text, name) + isolation_problems(yaml.safe_load(text), name)
        if expect is None and got:
            failures.append("fixture {0} should pass: {1}".format(name, got))
        elif expect is not None and not any(expect in p for p in got):
            failures.append("fixture {0} not caught for {1!r}: {2}".format(name, expect, got))
        else:
            print("note: fixture {0}: {1}".format(name, got[0] if got else "passes"))
    board = _read(BOARD_LOOP)
    shipped = check(board, implement_text)
    if shipped:
        failures += ["the shipped workflows already fail: " + p for p in shipped]

    mutations = (
        ("the self-hosted runner sentence is reworded",
         board.replace("on a self-hosted runner this protection", "on some runner this", 1),
         implement_text, None, "runner-assumption"),
        ("the covered-steps sentence is reworded",
         board.replace("it covers every step of this job after this one",
                       "it covers this job", 1), implement_text, None, "covered-steps"),
        ("review's pointer is dropped",
         board.replace("# to. #583: see the fix-agent job's \"Snapshot helper scripts\" step.",
                       "# to. #583.", 1), implement_text, None, "does not point"),
        ("implement's gate job loses its pointer", board,
         implement_text.replace("separate job, and the runner it assumes -- see board-loop.yml.",
                                "separate job, and the runner it assumes.", 1),
         None, "does not point at the runner assumption"),
        ("the retry site without its exemption", board, implement_text, {}, "later pushes"),
    )
    for label, btext, itext, exempt, expect in mutations:
        got = check(btext, itext, EXEMPT_GATE_SUITE_SITES if exempt is None else exempt)
        if any(expect in p for p in got):
            print("note: mutation caught ({0})".format(label))
        else:
            failures.append("mutation {0!r} not caught for {1!r}: {2}".format(label, expect, got))
    for f in failures:
        print("::error::Gate 145 self-test: " + f)
    if failures:
        return 1
    print("Gate 145 self-test: {0} fixture(s) and {1} mutation(s), each caught for its own "
          "reason.".format(len(FIXTURE_CASES), len(mutations)))
    return 0


if __name__ == "__main__":
    sys.exit(self_test() if "--self-test" in sys.argv[1:] else run())
