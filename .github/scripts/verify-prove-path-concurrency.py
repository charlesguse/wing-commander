#!/usr/bin/env python3
"""Gate 137 -- FR-018, specs/096-durable-prove-entry contracts/
prove-path-concurrency.md: `prove-gate`/`prove`'s own `pull_request`-branch
concurrency group is keyed by the merged PR's own number, distinct per
merge and distinct from both the ordinary and directed-proof groups, and
the two jobs never desync.

Asserts, against the real `board-loop.yml`, via
`board_prove.read_job_concurrency_group()`/`render_pull_request_group()`
(research.md D8, maintainer review): the raw group text's own
`pull_request`-branch `format(...)` arm renders two distinct PR numbers to
two distinct group names, neither of which collides with the shared
ordinary (`wing-commander-board-loop`) or directed-proof
(`wing-commander-board-loop-directed-proof`) literal -- never a substring
check alone, which a collapsed group key or a wrong-event-name regression
could still pass -- and `prove-gate`/`prove` resolve to identical raw
group text.

    python3 .github/scripts/verify-prove-path-concurrency.py
    python3 .github/scripts/verify-prove-path-concurrency.py --self-test
"""
import argparse
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from board_prove import (  # noqa: E402
    DIRECTED_GROUP, ORDINARY_GROUP, read_job_concurrency_group,
    render_pull_request_group)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REPO_BOARD_LOOP = os.path.join(REPO_ROOT, ".github", "workflows", "board-loop.yml")

PR_NUMBER_A = 111
PR_NUMBER_B = 222


def check(workflow_path, label, failures):
    """The FR-018 properties against `workflow_path`, appending to
    `failures` and returning it -- shared between the real-tree check in
    run() and every fixture mutation in self_test()."""
    groups = {job: read_job_concurrency_group(workflow_path, job) for job in ("prove-gate", "prove")}
    for job, group in groups.items():
        render_a = render_pull_request_group(group, PR_NUMBER_A)
        render_b = render_pull_request_group(group, PR_NUMBER_B)
        if render_a is None or render_b is None:
            failures.append(
                "{0}: {1}'s own pull_request-branch group text has no "
                "format('<prefix>{{0}}', github.event.pull_request.number) arm gated on "
                "github.event_name == 'pull_request' -- the group key is not per-merge "
                "(FR-004).".format(label, job))
            continue
        if render_a == render_b:
            failures.append(
                "{0}: {1}'s own pull_request-branch group renders the same for PR #{2} "
                "and PR #{3} ({4!r}) -- two merges proven together would collide "
                "(FR-004).".format(label, job, PR_NUMBER_A, PR_NUMBER_B, render_a))
        if render_a in (ORDINARY_GROUP, DIRECTED_GROUP):
            failures.append(
                "{0}: {1}'s own pull_request-branch group renders to {2!r} for PR #{3} "
                "-- indistinguishable from the shared ordinary or directed-proof group "
                "(FR-004).".format(label, job, render_a, PR_NUMBER_A))
    if groups["prove-gate"] != groups["prove"]:
        failures.append(
            "{0}: prove-gate and prove resolve to different raw group text -- they can "
            "desync even though prove needs: prove-gate.\n"
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
        "      group: \"{0}\"\n"
        "    steps: []\n"
        "  prove:\n"
        "    needs: prove-gate\n"
        "    runs-on: ubuntu-latest\n"
        "    concurrency:\n"
        "      group: \"{1}\"\n"
        "    steps: []\n"
    ).format(prove_gate_group, prove_group)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False, encoding="utf-8") as fh:
        fh.write(text)
        return fh.name


def _directed_expr(middle_arm):
    return (
        "${{ (github.event_name == 'workflow_dispatch' && inputs.directed-stage != '') && "
        "'" + DIRECTED_GROUP + "' || " + middle_arm + " || '" + ORDINARY_GROUP + "' }}")


# The real board-loop.yml shape (board-loop.yml ~:4481-4487/4665-4671).
PASS_GROUP = _directed_expr(
    "(github.event_name == 'pull_request' && format('wing-commander-board-loop-prove-"
    "{0}', github.event.pull_request.number))")

# Regression: the pull_request branch collapses back to the shared literal.
SHARED_LITERAL_GROUP = ORDINARY_GROUP

# Regression: the per-merge key is templated with a fixed string, dropping
# .number entirely -- every merge would collide on the same group.
FIXED_STRING_GROUP = _directed_expr(
    "(github.event_name == 'pull_request' && 'wing-commander-board-loop-prove')")

# Regression: the middle arm's own event-name check is swapped away from
# 'pull_request' -- the format() call still looks right, so a substring
# check alone would still pass this.
EVENT_SWAPPED_GROUP = _directed_expr(
    "(github.event_name == 'schedule' && format('wing-commander-board-loop-prove-{0}', "
    "github.event.pull_request.number))")

FIXTURE_CASES = [
    ("pass: per-merge key on both jobs", PASS_GROUP, PASS_GROUP, False),
    ("fail: pull_request branch reverted to the shared literal",
     SHARED_LITERAL_GROUP, SHARED_LITERAL_GROUP, True),
    ("fail: per-merge key templated with a fixed string, no .number",
     FIXED_STRING_GROUP, FIXED_STRING_GROUP, True),
    ("fail: the middle arm's own event-name check is swapped away from 'pull_request'",
     EVENT_SWAPPED_GROUP, EVENT_SWAPPED_GROUP, True),
    ("fail: prove-gate and prove diverge", PASS_GROUP, SHARED_LITERAL_GROUP, True),
]


def run():
    """The real tree only -- regression coverage for every structural
    mutation lives in self_test() instead (mirrors this repo's other
    fixture-driven gates, e.g. verify-gh-error-stub-conformance.py)."""
    failures = check(REPO_BOARD_LOOP, "real tree", [])
    for finding in failures:
        print("::error::verify-prove-path-concurrency: {0}".format(finding))
    if not failures:
        print("[ok] real tree: prove-gate/prove's own pull_request-branch group is "
              "per-merge and never desyncs")
    print("verify-prove-path-concurrency: {0} failure(s).".format(len(failures)))
    return 1 if failures else 0


def self_test():
    failures = []
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

    print("verify-prove-path-concurrency --self-test: {0} failure(s).".format(len(failures)))
    return 1 if failures else 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    sys.exit(self_test() if args.self_test else run())


if __name__ == "__main__":
    main()
