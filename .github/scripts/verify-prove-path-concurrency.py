#!/usr/bin/env python3
"""Gate 129 — FR-018, specs/096-durable-prove-entry contracts/
prove-path-concurrency.md: `prove-gate`/`prove`'s own `pull_request`-branch
concurrency group is keyed by the merged PR's own number, not the shared
`wing-commander-board-loop` literal, and the two jobs never desync.

Asserts, against the real `board-loop.yml`, via
`board_prove.read_job_concurrency_group()` (research.md D8):

1. `prove-gate` and `prove`'s raw `pull_request`-branch group text is not
   the literal `wing-commander-board-loop`.
2. That text contains the literal substring
   `github.event.pull_request.number`.
3. `prove-gate` and `prove` resolve to identical raw group text.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from board_prove import read_job_concurrency_group  # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REPO_BOARD_LOOP = os.path.join(REPO_ROOT, ".github", "workflows", "board-loop.yml")

SHARED_GROUP_LITERAL = "wing-commander-board-loop"
PER_MERGE_SUBSTRING = "github.event.pull_request.number"


def check(workflow_path, label, failures):
    """The three FR-018 properties against `workflow_path`, appending to
    `failures` and returning it -- shared between the real-tree check and
    each fixture mutation below."""
    groups = {job: read_job_concurrency_group(workflow_path, job) for job in ("prove-gate", "prove")}
    for job, group in groups.items():
        if group.strip() == SHARED_GROUP_LITERAL:
            failures.append("{0}: {1}'s own pull_request-branch group text is the literal "
                             "'{2}' -- a scheduled tick or another merge's prove run can "
                             "displace this run's queued slot again (FR-004).".format(
                                 label, job, SHARED_GROUP_LITERAL))
        if PER_MERGE_SUBSTRING not in group:
            failures.append("{0}: {1}'s own pull_request-branch group text does not contain "
                             "'{2}' -- the group key is not per-merge (FR-004).".format(
                                 label, job, PER_MERGE_SUBSTRING))
    if groups["prove-gate"] != groups["prove"]:
        failures.append("{0}: prove-gate and prove resolve to different raw group text -- "
                         "they can desync even though prove needs: prove-gate.\n"
                         "  prove-gate: {1!r}\n  prove:      {2!r}".format(
                             label, groups["prove-gate"], groups["prove"]))
    return failures


def write_fixture(prove_gate_group, prove_group):
    text = (
        "on:\n  pull_request:\n    types: [closed]\n"
        "jobs:\n"
        "  prove-gate:\n"
        "    runs-on: ubuntu-latest\n"
        "    concurrency:\n"
        "      group: {0}\n"
        "    steps: []\n"
        "  prove:\n"
        "    needs: prove-gate\n"
        "    runs-on: ubuntu-latest\n"
        "    concurrency:\n"
        "      group: {1}\n"
        "    steps: []\n"
    ).format(prove_gate_group, prove_group)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False, encoding="utf-8") as fh:
        fh.write(text)
        return fh.name


PASS_GROUP = "wing-commander-board-loop-prove-{{ github.event.pull_request.number }}"

FIXTURE_CASES = [
    ("pass: per-merge key on both jobs", PASS_GROUP, PASS_GROUP, False),
    ("fail: pull_request branch reverted to the shared literal",
     SHARED_GROUP_LITERAL, SHARED_GROUP_LITERAL, True),
    ("fail: per-merge key templated with a fixed string, no .number",
     "wing-commander-board-loop-prove", "wing-commander-board-loop-prove", True),
    ("fail: prove-gate and prove diverge", PASS_GROUP, SHARED_GROUP_LITERAL, True),
]


def run():
    failures = []
    check(REPO_BOARD_LOOP, "real tree", failures)
    for finding in failures:
        print("::error::verify-prove-path-concurrency: {0}".format(finding))
    if not failures:
        print("[ok] real tree: prove-gate/prove's own pull_request-branch group is "
              "per-merge and never desyncs")

    for name, prove_gate_group, prove_group, expect_failure in FIXTURE_CASES:
        path = write_fixture(prove_gate_group, prove_group)
        try:
            fixture_failures = check(path, name, [])
        finally:
            os.unlink(path)
        if expect_failure and not fixture_failures:
            failures.append("fixture `{0}`: expected a failure, got none.".format(name))
        elif not expect_failure and fixture_failures:
            failures.append("fixture `{0}`: expected no failure, got {1!r}.".format(
                name, fixture_failures))
        else:
            print("[ok] fixture `{0}` -> {1}".format(
                name, "fails as expected" if expect_failure else "passes as expected"))

    print("verify-prove-path-concurrency: {0} failure(s).".format(len(failures)))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(run())
