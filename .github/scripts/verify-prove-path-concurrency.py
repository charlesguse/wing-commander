#!/usr/bin/env python3
"""Gate 137 -- FR-018, specs/096-durable-prove-entry contracts/
prove-path-concurrency.md: `prove-gate`/`prove`'s own `pull_request`-branch
concurrency group is keyed by the merged PR's own number, distinct per
merge and distinct from both the ordinary and directed-proof groups, and
the two jobs never desync.

Asserts, against the real `board-loop.yml`, via
`board_prove.read_job_concurrency_group()` (research.md D8, maintainer
review): the WHOLE group expression, evaluated the way GitHub resolves it
(wc_gha_expr.interpolate) for a `pull_request` event, renders two distinct
PR numbers to two distinct group names, neither of which collides with the
shared ordinary (`wing-commander-board-loop`) or directed-proof
(`wing-commander-board-loop-directed-proof`) literal; a scheduled run and
an ordinary dispatch resolve to the ordinary group and a directed dispatch
to the directed-proof group (specs/060-self-redrive-concurrency/contracts/
concurrency-groups.md's "Groups, per job" table, the canonical one); and
`prove-gate`/`prove` resolve to identical raw group text.

Evaluated, never pattern-matched: a regex for the `format(...)` arm (this
gate's first form) still passed when that arm was present but could never
win -- shadowed by an earlier `||` literal, or `&&`-ed with a false
clause -- because the arm's text survives either regression (code review
of #893).

    python3 .github/scripts/verify-prove-path-concurrency.py
    python3 .github/scripts/verify-prove-path-concurrency.py --self-test
"""
import argparse
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from board_prove import (  # noqa: E402
    DIRECTED_GROUP, ORDINARY_GROUP, read_job_concurrency_group)
from wc_gha_expr import FUNCS, interpolate, tokenize  # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REPO_BOARD_LOOP = os.path.join(REPO_ROOT, ".github", "workflows", "board-loop.yml")

PR_NUMBER_A = 111
PR_NUMBER_B = 222


def render_group(group_text, event_name, pr_number=None, directed_stage=""):
    """The group name GitHub resolves `group_text` to for one run: the
    whole expression evaluated, not one arm of it. `inputs` is empty on a
    non-dispatch event, so `inputs.directed-stage` is null there."""
    ctx = {
        "github.event_name": event_name,
        "github.event.pull_request.number": pr_number,
        "inputs.directed-stage": directed_stage if event_name == "workflow_dispatch" else None,
    }
    # A context name this table does not model would evaluate as null and
    # could quietly steer the result, so it is an error, not a guess.
    for expr in re.findall(r"\$\{\{(.*?)\}\}", group_text, re.S):
        tokens = tokenize(expr)
        for i, (kind, val) in enumerate(tokens):
            is_call = i + 1 < len(tokens) and tokens[i + 1] == ("op", "(")
            if (kind == "name" and not is_call and val not in ("true", "false", "null")
                    and val not in ctx):
                raise ValueError("unmodelled context name {0!r}".format(val))
            if kind == "name" and is_call and val.lower() not in FUNCS:
                raise ValueError("unmodelled function {0!r}".format(val))
    return interpolate(group_text, ctx)


# (event_name, directed-stage, the group the contract's table requires).
NON_PULL_REQUEST_RUNS = (
    ("schedule", "", ORDINARY_GROUP),
    ("workflow_dispatch", "", ORDINARY_GROUP),
    ("workflow_dispatch", "prove", DIRECTED_GROUP),
)


def check(workflow_path, label, failures):
    """The FR-018 properties against `workflow_path`, appending to
    `failures` and returning it -- shared between the real-tree check in
    run() and every fixture mutation in self_test()."""
    groups = {job: read_job_concurrency_group(workflow_path, job) for job in ("prove-gate", "prove")}
    for job, group in groups.items():
        try:
            render_a = render_group(group, "pull_request", PR_NUMBER_A)
            render_b = render_group(group, "pull_request", PR_NUMBER_B)
            others = [(event, stage, want, render_group(group, event, None, stage))
                      for event, stage, want in NON_PULL_REQUEST_RUNS]
        except Exception as exc:  # noqa: BLE001 -- any evaluation failure is the finding
            failures.append(
                "{0}: {1}'s concurrency group cannot be evaluated ({2}) -- this gate "
                "cannot tell what group a run joins.".format(label, job, exc))
            continue
        for event, stage, want, got in others:
            if got != want:
                failures.append(
                    "{0}: {1}'s group resolves to {2!r} for a {3} run{4}, not {5!r} "
                    "(specs/060-self-redrive-concurrency/contracts/concurrency-groups.md's "
                    "\"Groups, per job\" table).".format(
                        label, job, got, event,
                        " with directed-stage {0!r}".format(stage) if stage else "", want))
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

# Regression: the per-merge arm is intact but sits after the ordinary
# literal, so `||` never reaches it -- the arm's own text is unchanged, so
# extracting the arm (this gate's first form) passed this.
SHADOWED_ARM_GROUP = (
    "${{ (github.event_name == 'workflow_dispatch' && inputs.directed-stage != '') && "
    "'" + DIRECTED_GROUP + "' || '" + ORDINARY_GROUP + "' || "
    "(github.event_name == 'pull_request' && format('wing-commander-board-loop-prove-"
    "{0}', github.event.pull_request.number)) }}")

# Regression: the per-merge arm is `&&`-ed with a clause that is never
# true on a pull_request run, so it always falls through to the ordinary
# literal -- the arm's own text is again unchanged.
DEAD_ARM_GROUP = _directed_expr(
    "(github.event_name == 'pull_request' && format('wing-commander-board-loop-prove-"
    "{0}', github.event.pull_request.number) && github.event_name == 'schedule')")

# Regression: the directed-proof arm's own guard is dropped, so a scheduled
# run joins the directed-proof group.
UNGUARDED_DIRECTED_GROUP = (
    "${{ (github.event_name == 'pull_request' && format('wing-commander-board-loop-prove-"
    "{0}', github.event.pull_request.number)) || '" + DIRECTED_GROUP + "' }}")

# Regression: a clause reads a context name this gate does not model, so
# its value here (null) need not be what GitHub resolves -- refused rather
# than evaluated on a guess.
UNMODELLED_NAME_GROUP = _directed_expr(
    "((github.event_name == 'pull_request' || github.event.action == 'closed') && "
    "format('wing-commander-board-loop-prove-{0}', github.event.pull_request.number))")

FIXTURE_CASES = [
    ("pass: per-merge key on both jobs", PASS_GROUP, PASS_GROUP, False),
    ("fail: pull_request branch reverted to the shared literal",
     SHARED_LITERAL_GROUP, SHARED_LITERAL_GROUP, True),
    ("fail: per-merge key templated with a fixed string, no .number",
     FIXED_STRING_GROUP, FIXED_STRING_GROUP, True),
    ("fail: the middle arm's own event-name check is swapped away from 'pull_request'",
     EVENT_SWAPPED_GROUP, EVENT_SWAPPED_GROUP, True),
    ("fail: the per-merge arm is shadowed by an earlier ordinary literal",
     SHADOWED_ARM_GROUP, SHADOWED_ARM_GROUP, True),
    ("fail: the per-merge arm is and-ed with a clause that is never true",
     DEAD_ARM_GROUP, DEAD_ARM_GROUP, True),
    ("fail: a scheduled run joins the directed-proof group",
     UNGUARDED_DIRECTED_GROUP, UNGUARDED_DIRECTED_GROUP, True),
    ("fail: a clause reads a context name the gate does not model",
     UNMODELLED_NAME_GROUP, UNMODELLED_NAME_GROUP, True),
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

    for finding in failures:
        print("::error::verify-prove-path-concurrency --self-test: {0}".format(finding))
    print("verify-prove-path-concurrency --self-test: {0} failure(s).".format(len(failures)))
    return 1 if failures else 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    sys.exit(self_test() if args.self_test else run())


if __name__ == "__main__":
    main()
