#!/usr/bin/env python3
"""Gate 104 -- every uses: ./.github/actions/ reference in board-loop.yml
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
      `.wc-pristine-repo`;
  (f) every job that carries the trusted-copy checkout also carries a
      canonical `Write-protect board-loop's own trusted copy (composites)`
      step, after the checkout and before every dependent reference in
      that job -- #640 maintainer review: the fixer and review-fixup
      agents hold unrestricted Write/Edit on the workspace and could
      otherwise rewrite the sidecar before it is executed with
      `secrets.WING_COMMANDER_APP_PRIVATE_KEY`.

A job with no composite reference at all (today: only `resolve-model`)
trivially satisfies (a)-(d) and (f); rule (e) is a file-level fact
independent of any one job.

Rule (g) carries the same uses:-block concern to every OTHER workflow in
.github/workflows/, since a relative `uses: ./.github/actions/<name>`
resolves from the workspace root in any file, not only this one:
  (g1) a workflow that runs in a consumer's workspace -- it declares a
       `pipeline-repo` workflow_call input -- holds no raw reference at
       all: its root is the consumer's repository (and, after a leg's
       checkout, a PR or item branch), so its composites come from the
       pipeline copy at `./.wing-commander-pipeline/`;
  (g2) in any other workflow, no raw reference follows, in the same job,
       a checkout into the workspace root of anything but the run's own
       commit (no `repository:`, and no `ref:` or one of TRUSTED_ROOT_REFS).
pr-conversation.yml's act job once posted its outstanding task item
through a raw reference after checking the PR's branch out at the root,
with the bot token -- the shape both halves of (g) reject.

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
WRITE_PROTECT_NAME = "Write-protect board-loop's own trusted copy (composites)"
RAW_PREFIX = "./.github/actions/"
SIDECAR_PREFIX = "./.wc-pristine-repo/.github/actions/"
AGENT_USES = "anthropics/claude-code-action@"
CONTEXT_ACTION = "wing-commander-context"
SIDECAR_PATH = ".wc-pristine-repo"
EXPECTED_REF = "${{ github.sha }}"
RAW_LINE_RE = re.compile(r"uses:\s*" + re.escape(RAW_PREFIX))
WORKFLOWS_DIR = os.path.join(".github", "workflows")
CONSUMER_INPUT = "pipeline-repo"
# Refs a workspace-root checkout may name and still hold the run's own,
# trusted commit (rule (g2)); no `ref:` at all means the same.
TRUSTED_ROOT_REFS = (
    "${{ github.sha }}",
    "${{ github.event.repository.default_branch }}",
)
TRUSTED_ROOT_REPOS = (None, "${{ github.repository }}")


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


def _write_protect_indices(steps):
    return [i for i, s in enumerate(steps) if (s or {}).get("name") == WRITE_PROTECT_NAME]


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
    write_protects = _write_protect_indices(steps)
    if not write_protects:
        problems.append(
            "{0}: has a trusted-copy checkout but no {1!r} step -- rule (f)".format(
                job_id, WRITE_PROTECT_NAME))
    else:
        if len(write_protects) > 1:
            problems.append("{0}: more than one {1!r} step -- rule (f)".format(
                job_id, WRITE_PROTECT_NAME))
        write_protect = write_protects[0]
        if write_protect < checkout:
            problems.append(
                "{0}: the write-protect step (step {1}) is before the trusted-copy "
                "checkout (step {2}) -- rule (f)".format(job_id, write_protect, checkout))
        for d in dependents:
            if write_protect > d:
                problems.append(
                    "{0}: the write-protect step (step {1}) is not before step {2} "
                    "({3!r}) -- rule (f)".format(
                        job_id, write_protect, d, (steps[d] or {}).get("name", d)))
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


# --- rule (g): every other workflow -----------------------------------------

def _triggers(doc):
    on = doc.get("on", doc.get(True))
    return on if isinstance(on, dict) else {}


def _runs_in_consumer_workspace(doc):
    call = _triggers(doc).get("workflow_call")
    return isinstance(call, dict) and CONSUMER_INPUT in ((call.get("inputs") or {}))


def _is_raw(step):
    return str((step or {}).get("uses", "")).strip().startswith(RAW_PREFIX)


def _untrusted_root_checkout(step):
    """The checkout's description when it writes something other than the
    run's own commit into the workspace root; None otherwise."""
    step = step or {}
    if not str(step.get("uses", "")).startswith("actions/checkout@"):
        return None
    w = step.get("with") or {}
    path = str(w.get("path") or "").strip()
    if path not in ("", ".", "./"):
        return None
    ref, repo = w.get("ref"), w.get("repository")
    if repo in TRUSTED_ROOT_REPOS and (ref is None or ref in TRUSTED_ROOT_REFS):
        return None
    return "{0!r} (repository={1!r}, ref={2!r})".format(step.get("name"), repo, ref)


def other_workflow_problems(name, doc):
    """Rule (g) for one workflow other than board-loop.yml."""
    problems = []
    consumer = _runs_in_consumer_workspace(doc)
    for job_id, job in ((doc or {}).get("jobs") or {}).items():
        untrusted = None
        for i, step in enumerate((job or {}).get("steps") or []):
            if _is_raw(step):
                label = (step or {}).get("name", i)
                if consumer:
                    problems.append(
                        "{0}: {1}: step {2} ({3!r}) uses {4!r} in a workflow that runs in "
                        "a consumer's workspace -- resolve it from ./.wing-commander-pipeline/ "
                        "-- rule (g)".format(name, job_id, i, label, step.get("uses")))
                elif untrusted:
                    problems.append(
                        "{0}: {1}: step {2} ({3!r}) uses {4!r} after the workspace-root "
                        "checkout {5}, so it resolves from that checkout -- rule (g)".format(
                            name, job_id, i, label, step.get("uses"), untrusted))
            untrusted = untrusted or _untrusted_root_checkout(step)
    return problems


def load_other_workflows():
    docs = {}
    for fname in sorted(os.listdir(WORKFLOWS_DIR)):
        path = os.path.join(WORKFLOWS_DIR, fname)
        if path == WORKFLOW or not fname.endswith((".yml", ".yaml")):
            continue
        with open(path, encoding="utf-8") as fh:
            docs[path] = yaml.safe_load(fh)
    if not docs:
        sys.exit("::error::Gate 104: no workflow found under {0}; rule (g) would pass "
                 "vacuously.".format(WORKFLOWS_DIR))
    return docs


def check_others(docs):
    problems = []
    for name, doc in docs.items():
        problems += other_workflow_problems(name, doc)
    return problems


# --- self-test mutations: each must be caught, attributed to its own rule --

def _job_steps(doc, job_id):
    return doc["jobs"][job_id]["steps"]


def _checkout_index(steps):
    for i, s in enumerate(steps):
        if (s or {}).get("name") == CHECKOUT_NAME:
            return i
    sys.exit("::error::Gate 104 self-test: no {0!r} step found; update the self-test "
             "alongside the workflow.".format(CHECKOUT_NAME))


def _first_sidecar_ref(steps):
    for i, s in enumerate(steps):
        if str((s or {}).get("uses", "")).startswith(SIDECAR_PREFIX):
            return i
    sys.exit("::error::Gate 104 self-test: no sidecar-relative reference found; update "
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


def mut_write_protect_dropped(doc):
    """#640 maintainer review: the write-protect step is removed from
    `fix`, leaving the sidecar writable for the fixer agent's Write/Edit."""
    steps = _job_steps(doc, "fix")
    idx = next(i for i, s in enumerate(steps) if (s or {}).get("name") == WRITE_PROTECT_NAME)
    del steps[idx]
    return doc


def mut_gate_job_raw_reference(doc):
    """spec 095: the credential-free gate-suite-fix job resolves its
    contained-gate-suite composite from the workspace -- the job that runs
    the fixer's tree would then run a composite the fixer could have
    edited. File-wide rule (a) covers the new jobs with no list to update."""
    steps = _job_steps(doc, "gate-suite-fix")
    step = next(s for s in steps
                if "wing-commander-contained-gate-suite" in str((s or {}).get("uses", "")))
    step["uses"] = RAW_PREFIX + "wing-commander-contained-gate-suite"
    return doc


def mut_gitignore_removed(text):
    return "".join(line for line in text.splitlines(keepends=True)
                   if SIDECAR_PATH not in line)


def _other_step(docs, fname, job_id, pred):
    steps = docs[os.path.join(WORKFLOWS_DIR, fname)]["jobs"][job_id]["steps"]
    for step in steps:
        if pred(step or {}):
            return step
    sys.exit("::error::Gate 104 self-test: the step rule (g)'s mutation needs is gone from "
             "{0} job {1}; update the self-test alongside the workflow.".format(fname, job_id))


def mut_consumer_raw_reference(docs):
    """pr-conversation.yml's act job posts its outstanding task item through
    a raw reference again, after the PR-branch checkout at the root."""
    step = _other_step(docs, "pr-conversation.yml", "act",
                       lambda s: "wing-commander-outstanding-task-item" in str(s.get("uses", "")))
    step["uses"] = RAW_PREFIX + "wing-commander-outstanding-task-item"
    return docs


def mut_untrusted_root_ref(docs):
    """shared-pr-reviewer.yml's find job checks the PR head out at the root
    instead of the default-branch commit its composites come from."""
    step = _other_step(docs, "shared-pr-reviewer.yml", "find",
                       lambda s: str(s.get("uses", "")).startswith("actions/checkout@"))
    step["with"]["ref"] = "${{ needs.prepare.outputs.head-sha }}"
    return docs


def mut_side_checkout_moved_to_root(docs):
    """The watchdog's metrics-branch checkout loses its path:, so the
    trial-bound composite after it resolves from the metrics branch."""
    step = _other_step(docs, "wing-commander-8-watchdog.yml", "trial-bound",
                       lambda s: (s.get("with") or {}).get("path") == ".wing-commander-metrics")
    del step["with"]["path"]
    return docs


# (label, "doc" mutates the parsed workflow / "gitignore" mutates .gitignore
#  text / "others" mutates every other parsed workflow, mutation function,
#  substring the caught problem must contain)
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
    ("the write-protect step is dropped from fix, leaving the sidecar writable",
     "doc", mut_write_protect_dropped, "rule (f)"),
    ("gate-suite-fix resolves the contained gate suite from the workspace (spec 095)",
     "doc", mut_gate_job_raw_reference, "rule (a)"),
    ("pr-conversation.yml's act job resolves the outstanding-task-item composite from "
     "the workspace (the PR branch it checked out at the root)",
     "others", mut_consumer_raw_reference, "rule (g)"),
    ("shared-pr-reviewer.yml's find job checks the PR head out at the root before its "
     "raw composite references",
     "others", mut_untrusted_root_ref, "rule (g)"),
    ("the watchdog's metrics-branch checkout moves to the root before the trial-bound "
     "composite",
     "others", mut_side_checkout_moved_to_root, "rule (g)"),
]


def main():
    use_utf8_stdout()
    self_test = "--self-test" in sys.argv[1:]
    if not os.path.isfile(WORKFLOW):
        sys.exit("::error::run this from the repository root; {0} not found.".format(WORKFLOW))
    text = open(WORKFLOW, encoding="utf-8").read()
    gitignore_text = open(GITIGNORE, encoding="utf-8").read() if os.path.isfile(GITIGNORE) else ""
    failures = []
    others = check_others(load_other_workflows())
    if self_test:
        base = check(text, gitignore_text) + others
        if base:
            failures += ["the shipped workflow already fails: {0}".format(p) for p in base]
        for label, kind, mutate, expect in MUTATIONS:
            if kind == "others":
                caught = check_others(mutate(load_other_workflows()))
            elif kind == "doc":
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
        failures = check(text, gitignore_text) + others
    for f in failures:
        # A rule (g) problem names its own workflow first; annotate that file.
        named = f.split(": ", 1)[0]
        where = named if named.startswith(WORKFLOWS_DIR + os.sep) else WORKFLOW
        print("::error file={0}::Gate 104: {1}".format(where, f))
    if failures:
        return 1
    if self_test:
        print("Gate 104 self-test: {0} mutation(s), each caught and attributed to its own "
              "rule.".format(len(MUTATIONS)))
    else:
        print("Gate 104: every uses: ./.github/actions/ reference in board-loop.yml "
              "resolves from the trusted copy, never the workspace; no other workflow "
              "resolves one from a consumer's or an untrusted root checkout.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
