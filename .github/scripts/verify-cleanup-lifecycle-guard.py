#!/usr/bin/env python3
"""cleanup's lifecycle guard says which thing went wrong, and recovers the one
lifecycle issue it is allowed to recover.

WHY THIS EXISTS
---------------
Every cleanup arm opens with the same step — "Verify spec artifacts and resolve
lifecycle issue" — which reads `issue` and `spec_dir` out of the spec branch's
spec-meta.json before anything is written. It used to test both in one
condition and report both with one message:

    spec-meta.json (issue='', spec_dir='specs/990-scratch-a') does not match
    the expected specs/990-scratch-a — refusing.

Two separate faults, one sentence, and the sentence is false for the common
one: spec_dir DID match; only `issue` was empty. Worse, that refusal made an
outcome unreachable rather than merely mis-labelled. A hand-submitted spec
carries `"issue": null` on spec/<slug> until its plan PR merges — plan.yml
creates the lifecycle issue and has the agent write the number into
spec-meta.json, but that edit lands on plan/<slug>. `mark-stalled` fires
exactly when a stage PR is closed UNMERGED, i.e. exactly inside that window,
so for every hand-submitted spec whose plan PR was rejected the spec was never
marked stalled and its (existing) lifecycle issue never flipped to
stage:stalled. Issue #73, gap 1; runs 29668954733 and 29669149568.

WHAT THIS CHECKS
----------------
The SHIPPED step, executed (gate 5 exists because a copy sat green for weeks
while checking a filter that did not ship), across every state spec-meta.json
and the label lookup can be in when cleanup reaches them — and, for each
failing one, that the message names the fault it actually hit and not another
one. Plus:

  * the fallback resolves the issue number from the `spec:<slug>` label and
    publishes it as the step's `issue` output, which is what every later step
    in the job reads;
  * the healthy path does NOT reach for the label at all (a fallback that runs
    always would silently paper over a spec-meta.json that had gone wrong);
  * EXACTLY ONE labelled issue is accepted. Two is a refusal naming both
    numbers, not a pick: the next thing this step's job does is relabel or
    close that issue, the label lookup is the only evidence there is, and so
    a wrong pick has nothing downstream that could catch it;
  * a FAILED lookup is its own outcome, never "no issue carries the label".
    #188 is the standing proof that collapsing a dead read into an empty
    result produces a confident, wrong diagnosis;
  * all three copies of the guard are byte-identical, so a fix applied to one
    arm cannot leave the other two on the old shape. Which arm reached the
    guard says nothing about the branch it is reading.

Mutations at the end reintroduce the shipped defect and four plausible drifts
and assert the suite fails on each.

Usage: python3 .github/scripts/verify-cleanup-lifecycle-guard.py
Requires: bash, jq (both present on ubuntu-latest runners).

On Windows, invoke with `python` — `python3` on PATH is usually the Microsoft
Store stub, which exits 49 without running anything. See wc_shell_harness for
why `bash` on PATH is also probed rather than trusted.
"""
import copy
import json
import os
import shutil
import sys
import tempfile

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_shell_harness import (ensure_jq, resolve_bash, run_step,
                              use_utf8_stdout)

STAGE = ".github/workflows/cleanup.yml"
STEP_NAME = "Verify spec artifacts and resolve lifecycle issue"
# The arm #73 was reported against. The other two carry the same step and are
# asserted identical to it below.
JOB = "mark-stalled"

SLUG = "990-scratch-a"
SPEC_DIR = f"specs/{SLUG}"
LABELLED_ISSUE = "68"
PR_NUMBER = "70"
REPO = "charlesguse/wing-commander"

BASH = None

# `gh` is called twice by this step and the two calls must be told apart:
# `gh pr comment` is the refusal channel (its output is never read), while
# `gh issue list --label spec:<slug>` is the fallback lookup whose STDOUT is
# the recovered issue number(s), one per line — what `--jq '.[].number'`
# emits. GH_ISSUE_LIST holds what that lookup finds (empty stands for "no
# issue carries the label"); GH_ISSUE_LIST_RC makes the lookup FAIL instead,
# which is a different thing entirely and must not be read as "found none".
GH_STUB = """#!/bin/sh
echo "gh $*" >> "$GH_CALLS"
case "$1 $2" in
  "issue list")
    if [ "${GH_ISSUE_LIST_RC:-0}" != 0 ]; then
      echo "gh: Could not resolve to a Repository with the name 'o/r'. (HTTP 502)" >&2
      exit "$GH_ISSUE_LIST_RC"
    fi
    if [ -n "$GH_ISSUE_LIST" ]; then printf '%s\\n' "$GH_ISSUE_LIST"; fi
    ;;
esac
exit 0
"""


def load_guards():
    """The guard's `run:` text per job, so the three copies can be compared."""
    with open(STAGE, encoding="utf-8") as fh:
        wf = yaml.safe_load(fh) or {}
    found = {}
    for job_name, job in (wf.get("jobs") or {}).items():
        for step in (job or {}).get("steps") or []:
            if (step or {}).get("name") == STEP_NAME:
                found[job_name] = step["run"]
    if JOB not in found:
        sys.exit(f"::error file={STAGE}::no step named {STEP_NAME!r} in job "
                 f"{JOB!r}. If it was renamed, update the workflow and this "
                 f"gate together — do not drop the check.")
    return found


RESOLVE_ANCHOR = "issue=$(jq -r '.issue // empty'"


def _resolve_half(guard):
    """The arm-independent tail of the guard, comments stripped.

    Everything from the spec-meta read onward acts on the spec branch alone,
    so the three arms must agree on it exactly; what precedes it is each arm's
    own "cannot match this …" wording.
    """
    if RESOLVE_ANCHOR not in guard:
        sys.exit(f"::error file={STAGE}::the guard no longer reads `issue` via "
                 f"{RESOLVE_ANCHOR!r}. This gate compares the three arms from "
                 f"that line onward — update the anchor rather than letting "
                 f"the comparison silently pass on nothing.")
    tail = guard[guard.index(RESOLVE_ANCHOR):]
    return "\n".join(l for l in tail.splitlines()
                     if not l.lstrip().startswith("#"))


def make_workspace(root, meta):
    """A checkout of the spec branch as the guard finds it.

    `meta` is None for "spec-meta.json was never written", otherwise the
    object to write. spec.md always exists: the first branch of the guard
    (neither file present) is covered by the `spec.md` scenario below, and
    conflating the two would let a fix to one hide a break in the other.
    """
    work = tempfile.mkdtemp(dir=root)
    os.makedirs(os.path.join(work, SPEC_DIR), exist_ok=True)
    with open(os.path.join(work, SPEC_DIR, "spec.md"), "w",
              encoding="utf-8", newline="\n") as fh:
        fh.write("# Feature Specification: scratch\n")
    if meta is not None:
        with open(os.path.join(work, SPEC_DIR, "spec-meta.json"), "w",
                  encoding="utf-8", newline="\n") as fh:
            json.dump(meta, fh)
    return work


def run_guard(guard, root, meta, labelled, lookup_rc="0"):
    """Execute the guard once. Returns (rc, output, outputs, summary, calls)."""
    work = make_workspace(root, meta)
    runner_temp = os.path.join(work, "runner_temp")
    bindir = os.path.join(work, "bin")
    calls = os.path.join(work, "gh_calls")
    os.makedirs(runner_temp, exist_ok=True)
    os.makedirs(bindir, exist_ok=True)
    open(calls, "w").close()
    stub = os.path.join(bindir, "gh")
    with open(stub, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(GH_STUB)
    os.chmod(stub, 0o755)

    rc, out, outputs, summary = run_step(
        BASH, guard, work,
        {"GH_TOKEN": "x", "SPEC_DIR": SPEC_DIR, "SLUG": SLUG,
         "PR_NUMBER": PR_NUMBER, "GITHUB_REPOSITORY": REPO,
         "GH_CALLS": calls, "GH_ISSUE_LIST": labelled,
         "GH_ISSUE_LIST_RC": lookup_rc,
         "PATH": bindir + os.pathsep + os.environ["PATH"]},
        runner_temp)
    with open(calls, encoding="utf-8") as fh:
        made = fh.read()
    return rc, out, outputs, summary, made


# The two faults the old single message conflated. Each scenario states which
# words the refusal MUST carry and which it must NOT — a message that names
# both is the defect, not a thorough message.
HEALTHY = {"issue": 68, "spec_dir": SPEC_DIR, "stage": "plan"}
NULL_ISSUE = {"issue": None, "spec_dir": SPEC_DIR, "stage": "plan"}
WRONG_DIR = {"issue": 68, "spec_dir": "specs/991-somewhere-else",
             "stage": "plan"}


def scenarios(guard, root):
    failures = []

    def note(msg):
        failures.append(msg)

    # 1. The ordinary case: spec-meta.json knows its own issue.
    rc, out, outputs, _, calls = run_guard(guard, root, HEALTHY, "")
    if rc != 0:
        note(f"healthy spec-meta.json: guard exited {rc}: {out.strip()}")
    elif outputs.get("issue") != "68":
        note(f"healthy spec-meta.json: guard published issue="
             f"{outputs.get('issue')!r}, expected '68' — every later step in "
             f"the job reads that output.")
    if "issue list" in calls:
        note("healthy spec-meta.json: the guard consulted the spec: label "
             "anyway. The fallback must fire only when `issue` is empty, or a "
             "spec-meta.json that has gone wrong is silently papered over.")

    # 2. #73 gap 1: the window a hand-submitted spec is guaranteed to be in.
    rc, out, outputs, summary, calls = run_guard(
        guard, root, NULL_ISSUE, LABELLED_ISSUE)
    if rc != 0:
        note(f'"issue": null with a spec:{SLUG} label present: guard exited '
             f"{rc} instead of recovering the issue — mark-stalled is "
             f"unreachable for every hand-submitted spec whose plan PR is "
             f"rejected (#73). Guard said: {out.strip()}")
    elif outputs.get("issue") != LABELLED_ISSUE:
        note(f'"issue": null: guard published issue={outputs.get("issue")!r}, '
             f"expected {LABELLED_ISSUE!r} recovered from the spec:{SLUG} "
             f"label.")
    if f"--label spec:{SLUG}" not in calls:
        note(f'"issue": null: the guard never asked for issues labelled '
             f"spec:{SLUG}. gh calls were: {calls.strip() or '(none)'}")
    if rc == 0 and "issue" not in summary.lower():
        note('"issue": null: the guard recovered the number but said nothing '
             "in the step summary — a silent fallback is how the next drift "
             "goes unnoticed.")

    # 3. Same window, but nothing carries the label: refuse, and say so in
    #    terms of the issue, never of spec_dir.
    rc, out, _, _, _ = run_guard(guard, root, NULL_ISSUE, "")
    if rc == 0:
        note('"issue": null with no labelled issue: guard exited 0. There is '
             "no lifecycle issue to resolve to — it must refuse, not guess.")
    if '"issue": null' not in out:
        note('"issue": null with no labelled issue: the refusal does not name '
             f'`"issue": null` as the cause. Guard said: {out.strip()}')
    if f"spec:{SLUG}" not in out:
        note('"issue": null with no labelled issue: the refusal does not name '
             f"the spec:{SLUG} label it looked for, so a maintainer cannot "
             f"see what would fix it. Guard said: {out.strip()}")
    if "spec-meta.json is missing or invalid" in out:
        note('"issue": null: the refusal reports the spec-meta.json fault '
             "instead. This is the misattribution #73 names — spec_dir "
             "matched perfectly.")

    # 3b. Two issues carry the label. This step's next act is to relabel or
    #     close a lifecycle issue, so picking the newest of several would let
    #     a stale or hand-applied label decide which issue gets closed — and
    #     the lookup is the only evidence there is, so nothing downstream
    #     could catch the wrong choice.
    rc, out, outputs, _, _ = run_guard(
        guard, root, NULL_ISSUE, f"{LABELLED_ISSUE}\n99")
    if rc == 0:
        note(f'"issue": null with TWO issues labelled spec:{SLUG}: guard '
             f"exited 0 and resolved issue={outputs.get('issue')!r}. It must "
             f"refuse rather than pick one — the label is the only evidence "
             f"there is, so a wrong pick is silent.")
    for number in (LABELLED_ISSUE, "99"):
        if f"#{number}" not in out:
            note(f'"issue": null with two labelled issues: the refusal does '
                 f"not name #{number}, so the maintainer cannot see which "
                 f"issues to disambiguate. Guard said: {out.strip()}")
    if outputs.get("issue"):
        note(f'"issue": null with two labelled issues: the guard still '
             f"published issue={outputs.get('issue')!r}. A refusing step must "
             f"publish nothing for the rest of the job to act on.")

    # 3c. The lookup FAILS. "the API did not answer" and "nothing carries the
    #     label" are different facts and only one of them is a refusal on the
    #     merits — #188 is the standing proof that collapsing them produces a
    #     confident, wrong diagnosis.
    rc, out, outputs, _, _ = run_guard(
        guard, root, NULL_ISSUE, "", lookup_rc="1")
    if rc == 0:
        note('"issue": null with a FAILING lookup: guard exited 0. Whether a '
             "lifecycle issue exists is unknown; it must refuse.")
    if "no issue carries the" in out:
        note('"issue": null with a FAILING lookup: the refusal reports it as '
             '"no issue carries the label". A failed read is not an absent '
             f"issue (#188). Guard said: {out.strip()}")
    if "HTTP 502" not in out:
        note('"issue": null with a FAILING lookup: the refusal does not carry '
             f"gh's own diagnostic, so the transient cause is invisible in the "
             f"job log. Guard said: {out.strip()}")

    # 4. The genuine spec-meta fault, which must NOT be reported as a null
    #    issue now that the two are separate.
    rc, out, _, _, calls = run_guard(guard, root, WRONG_DIR, LABELLED_ISSUE)
    if rc == 0:
        note("spec_dir pointing elsewhere: guard exited 0 — it would act on a "
             "specification this pull request does not identify.")
    if "spec-meta.json is missing or invalid" not in out:
        note(f"spec_dir pointing elsewhere: the refusal does not identify the "
             f"spec-meta.json as the fault. Guard said: {out.strip()}")
    if "issue list" in calls:
        note("spec_dir pointing elsewhere: the guard reached for the spec: "
             "label. An invalid spec-meta.json must stop the step, not be "
             "worked around.")

    # 5. No spec-meta.json at all — the pre-existing first branch, kept under
    #    test so splitting the second one cannot quietly swallow it.
    rc, out, _, _, _ = run_guard(guard, root, None, LABELLED_ISSUE)
    if rc == 0:
        note("no spec-meta.json: guard exited 0.")
    if "spec-meta.json" not in out:
        note(f"no spec-meta.json: the refusal does not name the missing file. "
             f"Guard said: {out.strip()}")

    # Every refusal reaches a human on the closed PR, which is the only
    # channel this step has.
    for label, meta, labelled in (("null issue, nothing labelled",
                                   NULL_ISSUE, ""),
                                  ("spec_dir elsewhere", WRONG_DIR,
                                   LABELLED_ISSUE)):
        _, _, _, _, calls = run_guard(guard, root, meta, labelled)
        if f"pr comment {PR_NUMBER}" not in calls:
            note(f"{label}: the refusal never commented on PR #{PR_NUMBER}. "
                 f"gh calls were: {calls.strip() or '(none)'}")
    return failures


def _mut_recombine_the_two_tests(guard):
    """The shipped defect: one condition, one message for both faults."""
    return guard.replace(
        'if [ -z "$meta_dir" ] || [ "$meta_dir" != "$SPEC_DIR" ]; then',
        'if [ -z "$issue" ] || [ -z "$meta_dir" ] || [ "$meta_dir" != "$SPEC_DIR" ]; then')


def _mut_drop_the_fallback(guard):
    """The guard splits its messages but still cannot reach the issue.

    `:` swallows the whole invocation and succeeds, so the lookup neither
    fails nor finds anything — which is what "there is no fallback" looks
    like from the rest of the block.
    """
    return guard.replace('if ! labelled=$(gh issue list',
                         'if ! labelled=$(: gh issue list')


def _mut_fallback_runs_always(guard):
    """The label becomes the source of truth even when spec-meta.json is fine.

    Passes every failure scenario and quietly stops spec-meta.json from being
    authoritative, which is why the healthy path asserts on the gh calls too.
    """
    return guard.replace(
        'if [ -z "$issue" ]; then\n  # A failed read is not an absent issue',
        'if true; then\n  # A failed read is not an absent issue')


def _mut_accept_any_number_of_labelled_issues(guard):
    """The ≠1 check goes, and the loop's LAST match wins silently."""
    return guard.replace('if [ "$count" -ne 1 ]; then', 'if false; then')


def _mut_lookup_failure_reads_as_empty(guard):
    """`|| true` inside the substitution: a dead API becomes "found none".

    The shape the first version of this fallback shipped, and the shape #188
    fixed in the lifecycle gate.
    """
    return guard.replace("""--jq '.[].number' 2>"$lookup_err"); then""",
                         """--jq '.[].number' 2>"$lookup_err" || true); then""")


MUTATIONS = [
    ("both faults share one condition and one message",
     _mut_recombine_the_two_tests),
    ("the spec: label fallback is removed", _mut_drop_the_fallback),
    ("the fallback runs even when spec-meta.json names its issue",
     _mut_fallback_runs_always),
    ("any number of labelled issues is accepted, newest wins",
     _mut_accept_any_number_of_labelled_issues),
    ("a failed lookup is read as 'no issue carries the label'",
     _mut_lookup_failure_reads_as_empty),
]


def main():
    global BASH
    use_utf8_stdout()
    ensure_jq()
    BASH = resolve_bash()

    guards = load_guards()
    guard = guards[JOB]
    failures = []

    # A fix applied to one arm and not the others is the drift this repository
    # keeps rediscovering; compare rather than trust. Only the lifecycle-issue
    # half is compared: each arm legitimately words its own "cannot match this
    # <merge|draft rejection|closed pull request>" line, and comments differ.
    # Everything from the spec-meta read onward is arm-independent, because it
    # reads the spec branch, which does not know which arm reached it.
    for job_name, other in sorted(guards.items()):
        if job_name != JOB and _resolve_half(other) != _resolve_half(guard):
            failures.append(
                f"job {job_name!r}'s lifecycle-issue resolution has drifted "
                f"from job {JOB!r}'s copy of {STEP_NAME!r} — either keep the "
                f"three identical or give this gate a scenario for the "
                f"difference. Only the arm-specific 'cannot match this …' "
                f"wording is allowed to differ.")
    print(f"cleanup lifecycle guard: {len(guards)} copies of the step, "
          f"{'identical' if not failures else 'DRIFTED'}.")

    root = tempfile.mkdtemp()
    try:
        failures += scenarios(guard, root)
        for f in failures:
            print(f"::error::{f}")

        for label, apply_mutation in MUTATIONS:
            mutated = apply_mutation(copy.copy(guard))
            if mutated == guard:
                print(f"::error::mutation {label!r} changed nothing — the "
                      f"code it edits was rewritten. Update the mutation so "
                      f"this gate keeps proving it can fail.")
                failures.append(f"mutation inapplicable: {label}")
                continue
            if scenarios(mutated, root):
                print(f"Mutation OK — {label}: caught.")
            else:
                print(f"::error::MUTATION SURVIVED — reintroducing {label} "
                      f"broke nothing in this suite, so the suite is not "
                      f"testing that defect. Fix the scenarios, not the "
                      f"mutation.")
                failures.append(f"mutation survived: {label}")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    print(f"cleanup lifecycle guard: 7 lookup/spec-meta state(s), "
          f"{len(MUTATIONS)} mutation(s); {len(failures)} failure(s).")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
