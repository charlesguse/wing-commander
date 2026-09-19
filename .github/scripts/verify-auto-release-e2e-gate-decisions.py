#!/usr/bin/env python3
"""Gate 63: the two e2e gate-decision scripts cover every documented branch.

specs/055-unattended-e2e-gates/contracts/gate-decision-scripts.md is the
contract for two pure scripts auto-release.yml's `poll` step calls to
decide the clarification and PR-merge gates
(.github/actions/_shared/auto-release-e2e-clarify-decision.sh and
.github/actions/_shared/auto-release-e2e-merge-decision.sh). Both are pure
functions of already-fetched JSON (Constitution VIII, research.md D5/D6) --
no `gh` call, no network -- so this harness EXECUTES the shipped scripts
directly against fixture JSON, rather than a copy of their logic.

Follows verify-auto-release-report.py's checked-in-fixture-plus-mutation-
check style: every documented branch is a scenario, then MUTATION checks
put each defect back and assert the suite then fails. A test that cannot
fail is not a test.

Usage: python3 .github/scripts/verify-auto-release-e2e-gate-decisions.py
Requires: bash, jq. See wc_shell_harness.py for running this on Windows.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_shell_harness import ensure_jq, resolve_bash, use_utf8_stdout  # noqa: E402

import subprocess  # noqa: E402

CLARIFY_SCRIPT = os.path.join(".github", "actions", "_shared",
                               "auto-release-e2e-clarify-decision.sh")
MERGE_SCRIPT = os.path.join(".github", "actions", "_shared",
                             "auto-release-e2e-merge-decision.sh")

BASH = None

PREPARED_ANSWER = (
    'Use the moment this workflow run started as "the timestamp." On a '
    "repeat run, overwrite the existing file rather than adding a new "
    "one. For anything else this question doesn't cover, use your own "
    "best judgement and proceed."
)

OPEN_MARKER = ("[!IMPORTANT]\nAnswer the open clarification questions in "
               "the comment below.")
REMAINING_MARKER = ("[!IMPORTANT]\nAnswer the remaining clarification "
                     "questions in the comment below.")


def comment(id_, login, body, created_at):
    return {"id": id_, "author": {"login": login}, "body": body,
            "createdAt": created_at}


def run_script(script_path, args):
    proc = subprocess.run([BASH, script_path, *args], capture_output=True,
                          text=True, encoding="utf-8", errors="replace")
    return proc.returncode, proc.stdout, proc.stderr


# --------------------------------------------------------------------------
# Clarify-decision scenarios (contracts/gate-decision-scripts.md)
# --------------------------------------------------------------------------
CLARIFY_SCENARIOS = [
    dict(name="no marker comment at all: none",
         comments=[comment("c1", "wing-commander[bot]", "hello", "2026-01-01T00:00:00Z")],
         login="harness-user", rounds="0", expect_head="none"),
    dict(name="marker open, round 0: reply with the exact prepared answer",
         comments=[comment("c1", "wing-commander[bot]", OPEN_MARKER, "2026-01-01T00:00:00Z")],
         login="harness-user", rounds="0", expect_head="reply",
         expect_body=PREPARED_ANSWER),
    dict(name="marker open (remaining-questions wording), round 2: still replies",
         comments=[comment("c1", "wing-commander[bot]", REMAINING_MARKER, "2026-01-01T00:00:00Z")],
         login="harness-user", rounds="2", expect_head="reply",
         expect_body=PREPARED_ANSWER),
    dict(name="marker open, round 3 (bound exhausted): exhausted",
         comments=[comment("c1", "wing-commander[bot]", OPEN_MARKER, "2026-01-01T00:00:00Z")],
         login="harness-user", rounds="3", expect_head="exhausted"),
    dict(name="marker open, a harness reply already postdates it: wait",
         comments=[comment("c1", "wing-commander[bot]", OPEN_MARKER, "2026-01-01T00:00:00Z"),
                   comment("c2", "harness-user", "the answer", "2026-01-01T00:05:00Z")],
         login="harness-user", rounds="1", expect_head="wait"),
]


def run_clarify_suite(script_path):
    failures = []
    for sc in CLARIFY_SCENARIOS:
        tag = f"[clarify: {sc['name']}]"
        comments_json = json.dumps(sc["comments"])
        rc, out, err = run_script(script_path, [comments_json, sc["login"], sc["rounds"]])
        if rc != 0:
            failures.append(f"{tag} script exited {rc}: {out}{err}")
            continue
        lines = out.splitlines()
        head = lines[0] if lines else ""
        if head != sc["expect_head"]:
            failures.append(f"{tag} expected head {sc['expect_head']!r}, got {head!r} (full: {out!r})")
            continue
        if "expect_body" in sc:
            body = "\n".join(lines[1:])
            if body != sc["expect_body"]:
                failures.append(f"{tag} reply body mismatch:\n  want: {sc['expect_body']!r}\n  got:  {body!r}")
    return failures


# --------------------------------------------------------------------------
# Merge-decision scenarios (contracts/gate-decision-scripts.md)
# --------------------------------------------------------------------------
def pr(number, head_ref, mergeable="MERGEABLE", merge_state="CLEAN", is_draft=False, state="OPEN"):
    return {"number": number, "headRefName": head_ref, "mergeable": mergeable,
            "mergeStateStatus": merge_state, "isDraft": is_draft, "state": state}


MERGE_SCENARIOS = [
    dict(name="empty array: none", prs=[], prefix="spec-draft/", slug="055-foo",
         expect_head="none"),
    dict(name="mismatched headRefName: wrong-attempt", prs=[pr(1, "spec-draft/054-bar")],
         prefix="spec-draft/", slug="055-foo", expect_head="wrong-attempt"),
    dict(name="draft PR: wait", prs=[pr(1, "spec-draft/055-foo", is_draft=True)],
         prefix="spec-draft/", slug="055-foo", expect_head="wait"),
    dict(name="mergeStateStatus UNKNOWN: wait",
         prs=[pr(1, "plan/055-foo", merge_state="UNKNOWN")],
         prefix="plan/", slug="055-foo", expect_head="wait"),
    dict(name="mergeStateStatus BEHIND: wait",
         prs=[pr(1, "plan/055-foo", merge_state="BEHIND")],
         prefix="plan/", slug="055-foo", expect_head="wait"),
    dict(name="mergeable CONFLICTING: conflicting",
         prs=[pr(1, "spec/055-foo", mergeable="CONFLICTING")],
         prefix="spec/", slug="055-foo", expect_head="conflicting"),
    dict(name="mergeStateStatus BLOCKED: blocked",
         prs=[pr(1, "spec/055-foo", merge_state="BLOCKED")],
         prefix="spec/", slug="055-foo", expect_head="blocked"),
    dict(name="clean and mergeable: merge <number>",
         prs=[pr(42, "spec-draft/055-foo")], prefix="spec-draft/", slug="055-foo",
         expect_head="merge", expect_number="42"),
]


def run_merge_suite(script_path):
    failures = []
    for sc in MERGE_SCENARIOS:
        tag = f"[merge: {sc['name']}]"
        prs_json = json.dumps(sc["prs"])
        rc, out, err = run_script(script_path, [prs_json, sc["prefix"], sc["slug"]])
        if rc != 0:
            failures.append(f"{tag} script exited {rc}: {out}{err}")
            continue
        lines = out.splitlines()
        head = lines[0] if lines else ""
        if head != sc["expect_head"]:
            failures.append(f"{tag} expected head {sc['expect_head']!r}, got {head!r} (full: {out!r})")
            continue
        if "expect_number" in sc:
            number = lines[1] if len(lines) > 1 else ""
            if number != sc["expect_number"]:
                failures.append(f"{tag} expected PR number {sc['expect_number']!r}, got {number!r}")
    return failures


def run_all(clarify_path, merge_path):
    return run_clarify_suite(clarify_path) + run_merge_suite(merge_path)


# --------------------------------------------------------------------------
# Mutations: each puts one documented-branch defect back into a scratch
# copy of the script, then asserts the suite fails against that copy.
# --------------------------------------------------------------------------
def mutate(src_path, old, new, label):
    text = open(src_path, encoding="utf-8").read()
    if text.count(old) != 1:
        sys.exit(f"::error::verify-auto-release-e2e-gate-decisions: expected exactly "
                 f"one occurrence of {old!r} in {src_path} to mutate for {label!r}, "
                 f"found {text.count(old)} -- the script text may have changed shape; "
                 f"update this harness alongside it.")
    return text.replace(old, new, 1)


CLARIFY_MUTATIONS = [
    ("exhausted collapsed into reply (round bound ignored)",
     'if [ "$rounds_answered" -lt "$MAX_CLARIFICATION_ROUNDS" ]; then',
     'if true; then'),
    ("wait collapsed into reply (a harness reply already posted is ignored)",
     'if [ "$harness_reply_exists" = "true" ]; then\n  echo "wait"\n  exit 0\nfi',
     'if false; then\n  echo "wait"\n  exit 0\nfi'),
]

MERGE_MUTATIONS = [
    ("wrong-attempt collapsed into merge (leftover PR from a previous attempt acted on)",
     'if [ "$head_ref" != "$expected_head" ]; then',
     'if false; then'),
    ("conflicting collapsed into merge",
     'if [ "$mergeable" = "CONFLICTING" ]; then',
     'if false; then'),
    ("blocked collapsed into merge",
     'if [ "$merge_state" = "BLOCKED" ]; then',
     'if false; then'),
    ("draft collapsed into merge",
     'if [ "$is_draft" = "true" ]; then',
     'if false; then'),
]


def run_mutation(script_path, run_suite, label, old, new, failures):
    mutated_text = mutate(script_path, old, new, label)
    tmp_path = script_path + ".mutated.tmp"
    with open(tmp_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(mutated_text)
    try:
        broke = run_suite(tmp_path)
    finally:
        os.remove(tmp_path)
    if broke:
        print(f"Mutation OK - {label}: {len(broke)} assertion(s) fail.")
    else:
        print(f"::error::MUTATION SURVIVED - reintroducing {label!r} broke nothing "
              f"in this suite, so the suite is not testing that defect.")
        failures.append(f"mutation survived: {label}")


def self_test():
    """Gate 63 self-test: each documented branch fails its own mutation."""
    failures = []
    for label, old, new in CLARIFY_MUTATIONS:
        run_mutation(CLARIFY_SCRIPT, run_clarify_suite, label, old, new, failures)
    for label, old, new in MERGE_MUTATIONS:
        run_mutation(MERGE_SCRIPT, run_merge_suite, label, old, new, failures)

    total = len(CLARIFY_MUTATIONS) + len(MERGE_MUTATIONS)
    print(f"Gate 63 self-test: {total} mutation(s); {len(failures)} failure(s).")
    return 1 if failures else 0


def main(argv):
    global BASH
    use_utf8_stdout()
    ensure_jq()
    BASH = resolve_bash()

    if not os.path.isfile(CLARIFY_SCRIPT) or not os.path.isfile(MERGE_SCRIPT):
        sys.exit(f"::error::run this from the repository root; {CLARIFY_SCRIPT} or "
                 f"{MERGE_SCRIPT} not found.")

    if "--self-test" in argv:
        return self_test()

    failures = run_all(CLARIFY_SCRIPT, MERGE_SCRIPT)
    for f in failures:
        print(f"::error::{f}")

    print(f"auto-release e2e gate decisions: "
          f"{len(CLARIFY_SCENARIOS) + len(MERGE_SCENARIOS)} scenario(s); "
          f"{len(failures)} failure(s).")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
