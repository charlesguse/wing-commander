#!/usr/bin/env python3
"""Gate -- every uses: ./.github/actions/ reference AND every bare
.github/scripts import in lifecycle-review-gate.yml resolves from a
trusted copy, never the reviewed pull request's own checkout
(specs/062-lifecycle-review-gate T073, maintainer review 5355876805 F1).

WHY THIS EXISTS
---------------
"review" and "disposition" both check out the lifecycle PR's own branch
as their workspace root -- untrusted code. Before T073, every composite
those jobs called (starting with wing-commander-context, which mints the
App's private key) resolved `uses: ./.github/actions/<name>` from that
same untrusted workspace, and disposition's own `sys.path.insert(0,
".github/scripts")` imported the branch's own copy of
wc_review_finding_fingerprint.py and wc_lifecycle_review_marker.py. A
branch under review must never supply the code that reviews or merges
it (constitution IX/X). T073 gives both jobs a second, trusted checkout
at `github.sha` (board-loop.yml's own ".wc-pristine-repo" idiom,
byte-for-byte -- see verify-board-loop-composite-provenance.py, Gate 104)
and repoints every composite and script reference at it.

"select"/"readiness"/"report"/"merge" never check out the PR's own
branch at all (their only checkout, if any, has no `ref:` override, so it
resolves `github.sha` -- always trusted); they keep bare
`./.github/actions/...` and `.github/scripts/...` references, which this
gate's rule (g) below does not flag, matching Gate 104's own "a job with
no composite reference at all trivially satisfies (a)-(d)" precedent
applied to this file's own job shape rather than inherited as a per-job
allowlist.

WHAT IT CHECKS
--------------
(a)-(f): identical to Gate 104's own rules, applied to
lifecycle-review-gate.yml's own trusted-copy step names -- see that
gate's docstring for the full statement of each. No per-job allowlist:
every job in the file is scanned the same way.

(g) NEW relative to Gate 104: in a job that carries the trusted-copy
    checkout (i.e. a job this gate's own rule (b)-(f) already covers),
    no `run:` block may reference a bare `.github/scripts/` or
    `.github/actions/` path -- every reference must be prefixed
    `.wc-pristine-repo/` (the composite-and-script trusted copy) or name
    `wc-pristine/scripts` under `$RUNNER_TEMP`/`${{ runner.temp }}` (the
    older, still-valid helper-script-only snapshot T016 established for
    `review`, which pre-dates and coexists with (a)-(f)'s composite-only
    copy).

Usage: python3 .github/scripts/verify-lifecycle-review-gate-composite-provenance.py [--self-test]
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_shell_harness import use_utf8_stdout  # noqa: E402

import yaml  # noqa: E402

WORKFLOW = os.path.join(".github", "workflows", "lifecycle-review-gate.yml")
GITIGNORE = ".gitignore"
CHECKOUT_NAME = "Checkout this job's own trusted copy (composites)"
WRITE_PROTECT_NAME = "Write-protect this job's own trusted copy (composites)"
RAW_ACTIONS_PREFIX = "./.github/actions/"
SIDECAR_ACTIONS_PREFIX = "./.wc-pristine-repo/.github/actions/"
AGENT_USES = "anthropics/claude-code-action@"
CONTEXT_ACTION = "wing-commander-context"
SIDECAR_PATH = ".wc-pristine-repo"
EXPECTED_REF = "${{ github.sha }}"
RAW_LINE_RE = re.compile(r"uses:\s*" + re.escape(RAW_ACTIONS_PREFIX))

# Rule (g): a bare .github/scripts or .github/actions reference in a run:
# block -- not prefixed .wc-pristine-repo/, and not the runner.temp
# wc-pristine snapshot's own scripts/ path.
BARE_SCRIPT_RE = re.compile(r"(?<![\w./-])\.github/(scripts|actions)\b")
TRUSTED_SCRIPT_MARKERS = (".wc-pristine-repo/.github/", "wc-pristine/scripts",
                          "wc-pristine\", \"scripts\"", 'wc-pristine", "scripts"')


def rule_a_problems(text):
    problems = []
    for lineno, line in enumerate(text.splitlines(), 1):
        if RAW_LINE_RE.search(line):
            problems.append("line {0}: raw workspace reference {1!r} -- rule (a)".format(
                lineno, line.strip()))
    return problems


def _dependent_indices(steps):
    idx = []
    for i, step in enumerate(steps):
        uses = str((step or {}).get("uses", ""))
        if not uses:
            continue
        if uses.startswith(SIDECAR_ACTIONS_PREFIX) or CONTEXT_ACTION in uses or AGENT_USES in uses:
            idx.append(i)
    return idx


def _checkout_indices(steps):
    return [i for i, s in enumerate(steps)
            if (s or {}).get("name") == CHECKOUT_NAME
            and str((s or {}).get("uses", "")).startswith("actions/checkout@")]


def _write_protect_indices(steps):
    return [i for i, s in enumerate(steps) if (s or {}).get("name") == WRITE_PROTECT_NAME]


def _run_text_problems(job_id, steps):
    """Rule (g): every run: block in this job, scanned for a bare
    .github/scripts or .github/actions reference. Skips comment-only lines
    (a `#`-prefixed line references a path only in prose) and `git archive
    --format=tar "$GITHUB_SHA" .github/scripts ...`-shaped lines: `git
    archive` reads pathspecs from the OBJECT STORE at the given SHA, never
    the working tree, so a bare pathspec there is not a workspace-relative
    read regardless of what branch happens to be checked out ("Snapshot
    helper scripts", T016 -- pre-dates and coexists with (a)-(f)'s
    composite-only copy, matching this gate's own docstring)."""
    problems = []
    for i, step in enumerate(steps):
        run = (step or {}).get("run")
        if not run:
            continue
        for lineno, line in enumerate(str(run).splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if "git archive" in line and "$GITHUB_SHA" in line:
                continue
            for match in BARE_SCRIPT_RE.finditer(line):
                start = match.start()
                prefix = line[max(0, start - 40):start]
                if any(marker in prefix for marker in TRUSTED_SCRIPT_MARKERS):
                    continue
                problems.append(
                    "{0}: step {1} ({2!r}) run: block line {3}: bare {4!r} reference "
                    "-- rule (g)".format(job_id, i, (step or {}).get("name", i), lineno,
                                        line.strip()))
    return problems


def job_problems(job_id, job):
    problems = []
    steps = (job or {}).get("steps") or []
    dependents = _dependent_indices(steps)
    checkouts = _checkout_indices(steps)
    if not dependents and not checkouts:
        return problems
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
    problems += _run_text_problems(job_id, steps)
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
    sys.exit("::error::lifecycle-review-gate composite provenance self-test: no "
             "{0!r} step found; update the self-test alongside the "
             "workflow.".format(CHECKOUT_NAME))


def _first_sidecar_ref(steps):
    for i, s in enumerate(steps):
        if str((s or {}).get("uses", "")).startswith(SIDECAR_ACTIONS_PREFIX):
            return i
    sys.exit("::error::lifecycle-review-gate composite provenance self-test: no "
             "sidecar-relative reference found; update the self-test alongside "
             "the workflow.")


def mut_raw_uses_reintroduced(doc):
    steps = _job_steps(doc, "review")
    step = next(s for s in steps
                if str((s or {}).get("uses", "")).startswith(SIDECAR_ACTIONS_PREFIX + CONTEXT_ACTION))
    step["uses"] = RAW_ACTIONS_PREFIX + CONTEXT_ACTION
    return doc


def mut_raw_uses_in_disposition(doc):
    """Proves rule (a) admits no per-job carve-out (Gate 104's own D7
    mutation 7 precedent) -- a raw reference reintroduced in `disposition`
    rather than `review`."""
    steps = _job_steps(doc, "disposition")
    step = next(s for s in steps
                if str((s or {}).get("uses", "")).startswith(SIDECAR_ACTIONS_PREFIX + CONTEXT_ACTION))
    step["uses"] = RAW_ACTIONS_PREFIX + CONTEXT_ACTION
    return doc


def mut_checkout_moved_after(doc):
    steps = _job_steps(doc, "review")
    checkout = steps.pop(_checkout_index(steps))
    dep = _first_sidecar_ref(steps)
    steps.insert(dep + 1, checkout)
    return doc


def mut_checkout_dropped(doc):
    steps = _job_steps(doc, "disposition")
    del steps[_checkout_index(steps)]
    return doc


def mut_ref_changed(doc):
    steps = _job_steps(doc, "review")
    steps[_checkout_index(steps)]["with"]["ref"] = "main"
    return doc


def mut_continue_on_error(doc):
    steps = _job_steps(doc, "review")
    steps[_checkout_index(steps)]["continue-on-error"] = True
    return doc


def mut_write_protect_dropped(doc):
    steps = _job_steps(doc, "disposition")
    idx = next(i for i, s in enumerate(steps) if (s or {}).get("name") == WRITE_PROTECT_NAME)
    del steps[idx]
    return doc


def mut_gitignore_removed(text):
    return "".join(line for line in text.splitlines(keepends=True)
                   if SIDECAR_PATH not in line)


def mut_bare_script_import(doc):
    """Rule (g): disposition's "Partition..." step reverts to importing
    from its own (untrusted) checkout instead of the trusted copy."""
    steps = _job_steps(doc, "disposition")
    step = next(s for s in steps if (s or {}).get("name") ==
               "Partition, dedup, and render this round's findings")
    step["run"] = str(step["run"]).replace(
        'sys.path.insert(0, ".wc-pristine-repo/.github/scripts")',
        'sys.path.insert(0, ".github/scripts")')
    return doc


MUTATIONS = [
    ("a raw uses: ./.github/actions/ reappears in review (already sidecar-relative)",
     "doc", mut_raw_uses_reintroduced, "rule (a)"),
    ("the trusted-copy checkout is moved after a composite reference in review",
     "doc", mut_checkout_moved_after, "rule (b)"),
    ("the trusted-copy checkout is dropped from disposition, orphaning its references",
     "doc", mut_checkout_dropped, "rule (b)"),
    ("the trusted-copy checkout's ref: becomes a literal branch in review",
     "doc", mut_ref_changed, "rule (c)"),
    ("continue-on-error: true is added to the trusted-copy checkout in review",
     "doc", mut_continue_on_error, "rule (d)"),
    ("the .gitignore entry for .wc-pristine-repo is removed",
     "gitignore", mut_gitignore_removed, "rule (e)"),
    ("a raw uses: ./.github/actions/ reappears in disposition, proving rule (a) "
     "admits no per-job carve-out",
     "doc", mut_raw_uses_in_disposition, "rule (a)"),
    ("the write-protect step is dropped from disposition, leaving the sidecar writable",
     "doc", mut_write_protect_dropped, "rule (f)"),
    ("disposition's partition step imports wc_review_finding_fingerprint from "
     "its own (untrusted) checkout instead of the trusted copy",
     "doc", mut_bare_script_import, "rule (g)"),
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
        print("::error file={0}::lifecycle-review-gate composite provenance: {1}".format(
            WORKFLOW, f))
    if failures:
        return 1
    if self_test:
        print("lifecycle-review-gate composite provenance self-test: {0} mutation(s), "
              "each caught and attributed to its own rule.".format(len(MUTATIONS)))
    else:
        print("lifecycle-review-gate composite provenance: every uses: "
              "./.github/actions/ reference and every .github/scripts import in "
              "lifecycle-review-gate.yml resolves from a trusted copy, never the "
              "reviewed pull request's own checkout.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
