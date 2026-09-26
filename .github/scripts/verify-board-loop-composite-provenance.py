#!/usr/bin/env python3
"""Gate 99 -- every uses: ./.github/actions/ reference in board-loop.yml
resolves from the trusted copy, never the workspace (#468/#504/#615).

WHY THIS EXISTS
---------------
Gate 98 closed the run:-block half of board-loop's item-branch exposure --
fix, review and readiness import .github/scripts helpers only from a
pristine $GITHUB_SHA snapshot, never the working tree. It says nothing
about a uses: reference: a relative `uses: ./.github/actions/<name>`
resolves from the workspace regardless of which job it is in, and the
workspace is the item's own branch in fix (resume path onward), review
and readiness. specs/086-trusted-composite-resolution closes this second
half by giving every job in this file a second, trusted checkout --
`actions/checkout@v5` at `github.sha` into the gitignored
`.wc-pristine-repo` -- and rewriting every `uses: ./.github/actions/<name>`
to `uses: ./.wc-pristine-repo/.github/actions/<name>`. See board-loop.yml's
own header for the full trusted-copy statement both gates enforce a piece
of.

WHAT IT CHECKS
--------------
Unconditionally, file-wide, no per-job allowlist (FR-011; Gate 98's own
JOBS = ("fix", "review", "readiness") tuple is exactly the shape this gate
must not inherit -- a per-job list is the same shape as the gap this
feature closes):
  (a) no line anywhere in the file matches the raw, workspace-relative
      form `uses: ./.github/actions/`;
  (b) every job that contains a `uses: ./.wc-pristine-repo/.github/actions/...`
      reference contains the canonical `Checkout board-loop's own trusted
      copy (composites)` step, at a step index lower than every such
      reference, every `wing-commander-context` call, and every
      `anthropics/claude-code-action@` step in that same job;
  (c) that step's `with.ref` is exactly `${{ github.sha }}`;
  (d) that step carries no `continue-on-error: true`, and its own `if:`
      (if it has one at all) is not a condition that could skip it while a
      dependent reference still runs;
  (e) `.gitignore` contains an entry matching the sidecar path,
      `.wc-pristine-repo`.

A job with no composite reference at all (today: only `resolve-model`)
trivially satisfies (a)-(d); rule (e) is a file-level fact independent of
any one job.

Gate 98's own `run:`-block checks (helper-script/schema provenance, the
`python3 -I` allowlist) are untouched and out of this gate's scope; this
gate never inspects a `run:` block, and has no gate-suite exemption to
state (it never runs the item's own tree).

--self-test applies one mutation per rule above, plus a mutation
reintroducing a raw reference in `select` -- a job outside Gate 98's own
JOBS tuple -- proving rule (a) admits no per-job carve-out, and asserts
each is caught and attributable to its own rule, plus a baseline assertion
that the shipped file is clean first.

Usage: python3 .github/scripts/verify-board-loop-composite-provenance.py [--self-test]
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_shell_harness import use_utf8_stdout  # noqa: E402

import yaml  # noqa: E402

WORKFLOW = os.path.join(".github", "workflows", "board-loop.yml")
GITIGNORE = ".gitignore"
CHECKOUT_NAME = "Checkout board-loop's own trusted copy (composites)"
RAW_PREFIX = "./.github/actions/"
SIDECAR_PREFIX = "./.wc-pristine-repo/.github/actions/"
AGENT_USES = "anthropics/claude-code-action@"
CONTEXT_ACTION = "wing-commander-context"
SIDECAR_PATH = ".wc-pristine-repo"
EXPECTED_REF = "${{ github.sha }}"
RAW_LINE_RE = re.compile(r"uses:\s*" + re.escape(RAW_PREFIX))


def rule_a_problems(text):
    """(a) no line anywhere in the file names the raw, workspace-relative
    form -- file-wide, unconditional, no per-job allowlist."""
    problems = []
    for lineno, line in enumerate(text.splitlines(), 1):
        if RAW_LINE_RE.search(line):
            problems.append("line {0}: raw workspace reference {1!r} -- rule (a)".format(
                lineno, line.strip()))
    return problems


def _dependent_indices(steps):
    """Every step index the trusted-copy checkout must precede: every
    sidecar-relative composite reference, every wing-commander-context
    call (whichever form it is spelled in), every claude-code-action step."""
    idx = []
    for i, step in enumerate(steps):
        uses = str((step or {}).get("uses", ""))
        if not uses:
            continue
        if uses.startswith(SIDECAR_PREFIX) or CONTEXT_ACTION in uses or AGENT_USES in uses:
            idx.append(i)
    return idx


def _checkout_indices(steps):
    return [i for i, s in enumerate(steps)
            if (s or {}).get("name") == CHECKOUT_NAME
            and str((s or {}).get("uses", "")).startswith("actions/checkout@")]


def job_problems(job_id, job):
    problems = []
    steps = (job or {}).get("steps") or []
    dependents = _dependent_indices(steps)
    if not dependents:
        return problems
    checkouts = _checkout_indices(steps)
    if not checkouts:
        problems.append("{0}: has a trusted-copy-relative reference but no {1!r} step "
                        "-- rule (b)".format(job_id, CHECKOUT_NAME))
        return problems
    if len(checkouts) > 1:
        problems.append("{0}: more than one {1!r} step -- rule (b)".format(
            job_id, CHECKOUT_NAME))
    checkout = checkouts[0]
    for d in dependents:
        if checkout > d:
            problems.append(
                "{0}: the trusted-copy checkout (step {1}) is not before step {2} "
                "({3!r}) -- rule (b)".format(
                    job_id, checkout, d, (steps[d] or {}).get("name", d)))
    step = steps[checkout] or {}
    ref = ((step.get("with") or {})).get("ref")
    if ref != EXPECTED_REF:
        problems.append("{0}: trusted-copy checkout ref is {1!r}, not {2!r} -- rule (c)".format(
            job_id, ref, EXPECTED_REF))
    if step.get("continue-on-error") is True:
        problems.append(
            "{0}: trusted-copy checkout carries continue-on-error: true -- rule (d)".format(
                job_id))
    step_if = step.get("if")
    job_if = (job or {}).get("if")
    if step_if is not None and step_if != job_if and step_if not in ("!cancelled()", "success()"):
        problems.append(
            "{0}: trusted-copy checkout's if: {1!r} could skip it while a dependent "
            "reference still runs -- rule (d)".format(job_id, step_if))
    return problems


def gitignore_problems(text):
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.rstrip("/") == SIDECAR_PATH:
            return []
    return ["{0!r} has no entry matching {1!r} -- rule (e)".format(GITIGNORE, SIDECAR_PATH)]


def check(text, gitignore_text):
    problems = rule_a_problems(text)
    doc = yaml.safe_load(text)
    for job_id, job in (doc.get("jobs") or {}).items():
        problems += job_problems(job_id, job)
    problems += gitignore_problems(gitignore_text)
    return problems


def check_doc(doc, gitignore_text):
    """Same as check(), but the workflow side has already been mutated as a
    parsed document -- re-dumped once so rule (a)'s textual scan still sees
    it (a plain `uses: <value>` mapping always dumps as one line)."""
    dumped = yaml.dump(doc, default_flow_style=False, sort_keys=False)
    problems = rule_a_problems(dumped)
    for job_id, job in (doc.get("jobs") or {}).items():
        problems += job_problems(job_id, job)
    problems += gitignore_problems(gitignore_text)
    return problems


# --- self-test mutations: each must be caught, attributed to its own rule --

def _job_steps(doc, job_id):
    return doc["jobs"][job_id]["steps"]


def _checkout_index(steps):
    for i, s in enumerate(steps):
        if (s or {}).get("name") == CHECKOUT_NAME:
            return i
    sys.exit("::error::Gate 99 self-test: no {0!r} step found; update the self-test "
             "alongside the workflow.".format(CHECKOUT_NAME))


def _first_sidecar_ref(steps):
    for i, s in enumerate(steps):
        if str((s or {}).get("uses", "")).startswith(SIDECAR_PREFIX):
            return i
    sys.exit("::error::Gate 99 self-test: no sidecar-relative reference found; update "
             "the self-test alongside the workflow.")


def mut_raw_uses_reintroduced(doc):
    """A raw uses: reappears in `fix`, a job already using the sidecar form."""
    steps = _job_steps(doc, "fix")
    step = next(s for s in steps
                if str((s or {}).get("uses", "")).startswith(SIDECAR_PREFIX + CONTEXT_ACTION))
    step["uses"] = RAW_PREFIX + CONTEXT_ACTION
    return doc


def mut_raw_uses_outside_jobs_tuple(doc):
    """The same reintroduction, but in `select` -- not one of Gate 98's own
    JOBS -- proving rule (a) has no per-job carve-out (D7 mutation 7)."""
    steps = _job_steps(doc, "select")
    step = next(s for s in steps
                if str((s or {}).get("uses", "")).startswith(SIDECAR_PREFIX + CONTEXT_ACTION))
    step["uses"] = RAW_PREFIX + CONTEXT_ACTION
    return doc


def mut_checkout_moved_after(doc):
    steps = _job_steps(doc, "review")
    checkout = steps.pop(_checkout_index(steps))
    dep = _first_sidecar_ref(steps)
    steps.insert(dep + 1, checkout)
    return doc


def mut_checkout_dropped(doc):
    steps = _job_steps(doc, "readiness")
    del steps[_checkout_index(steps)]
    return doc


def mut_ref_changed(doc):
    steps = _job_steps(doc, "fix")
    steps[_checkout_index(steps)]["with"]["ref"] = "main"
    return doc


def mut_continue_on_error(doc):
    steps = _job_steps(doc, "fix")
    steps[_checkout_index(steps)]["continue-on-error"] = True
    return doc


def mut_gitignore_removed(text):
    return "".join(line for line in text.splitlines(keepends=True)
                   if SIDECAR_PATH not in line)


# (label, "doc" mutates the parsed workflow / "gitignore" mutates .gitignore
#  text, mutation function, substring the caught problem must contain)
MUTATIONS = [
    ("a raw uses: ./.github/actions/ reappears in fix (already sidecar-relative)",
     "doc", mut_raw_uses_reintroduced, "rule (a)"),
    ("the trusted-copy checkout is moved after a composite reference in review",
     "doc", mut_checkout_moved_after, "rule (b)"),
    ("the trusted-copy checkout is dropped from readiness, orphaning its references",
     "doc", mut_checkout_dropped, "rule (b)"),
    ("the trusted-copy checkout's ref: becomes a literal branch in fix",
     "doc", mut_ref_changed, "rule (c)"),
    ("continue-on-error: true is added to the trusted-copy checkout in fix",
     "doc", mut_continue_on_error, "rule (d)"),
    ("the .gitignore entry for .wc-pristine-repo is removed",
     "gitignore", mut_gitignore_removed, "rule (e)"),
    ("a raw uses: ./.github/actions/ reappears in select -- outside Gate 98's own "
     "JOBS, proving rule (a) admits no per-job carve-out",
     "doc", mut_raw_uses_outside_jobs_tuple, "rule (a)"),
]


def main():
    use_utf8_stdout()
    self_test = "--self-test" in sys.argv[1:]
    if not os.path.isfile(WORKFLOW):
        sys.exit("::error::run this from the repository root; {0} not found.".format(WORKFLOW))
    text = open(WORKFLOW, encoding="utf-8").read()
    gitignore_text = open(GITIGNORE, encoding="utf-8").read() if os.path.isfile(GITIGNORE) else ""
    failures = []
    if self_test:
        base = check(text, gitignore_text)
        if base:
            failures += ["the shipped workflow already fails: {0}".format(p) for p in base]
        for label, kind, mutate, expect in MUTATIONS:
            if kind == "doc":
                doc = mutate(yaml.safe_load(text))
                caught = check_doc(doc, gitignore_text)
            else:
                caught = check(text, mutate(gitignore_text))
            caught = [p for p in caught if expect in p]
            if caught:
                print("note: mutation caught ({0}): {1}".format(label, caught[0]))
            else:
                failures.append("mutation {0!r} was NOT caught by its rule ({1!r})".format(
                    label, expect))
    else:
        failures = check(text, gitignore_text)
    for f in failures:
        print("::error file={0}::Gate 99: {1}".format(WORKFLOW, f))
    if failures:
        return 1
    if self_test:
        print("Gate 99 self-test: {0} mutation(s), each caught and attributed to its own "
              "rule.".format(len(MUTATIONS)))
    else:
        print("Gate 99: every uses: ./.github/actions/ reference in board-loop.yml "
              "resolves from the trusted copy, never the workspace.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
