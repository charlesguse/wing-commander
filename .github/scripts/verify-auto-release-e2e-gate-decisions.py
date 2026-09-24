#!/usr/bin/env python3
"""Gate 66: the two e2e gate-decision scripts cover every documented branch.

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

Renamed from "Gate 63" to "Gate 66" in lint-workflows.yml to clear a
numbering collision with two other features landed on the same base (see
that file's own comment) -- this docstring and the self-test banner below
now say 66 to match (maintainer feedback on PR #389: the two had drifted).

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

ISSUE_AUTHOR_ID = "555"


def comment(id_, login, user_id, created_at, body="the answer",
            user_type="User", association="NONE"):
    return {"id": id_, "user": {"login": login, "id": user_id, "type": user_type},
            "author_association": association, "body": body, "created_at": created_at}


def marker(id_, created_at, body=OPEN_MARKER):
    return comment(id_, "wing-commander[bot]", "1", created_at, body=body,
                   user_type="Bot", association="NONE")


def run_script(script_path, args, stdin_json):
    proc = subprocess.run([BASH, script_path, *args], input=stdin_json,
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace")
    return proc.returncode, proc.stdout, proc.stderr


# --------------------------------------------------------------------------
# Clarify-decision scenarios (contracts/gate-decision-scripts.md)
# --------------------------------------------------------------------------
CLARIFY_DECIDE_SCENARIOS = [
    dict(name="no marker comment at all: none",
         comments=[comment("c1", "wing-commander[bot]", "1", "2026-01-01T00:00:00Z",
                            body="hello", user_type="Bot")],
         author_id="999", rounds="0", expect_head="none"),
    dict(name="marker open, round 0: reply with the exact prepared answer",
         comments=[marker("c1", "2026-01-01T00:00:00Z")],
         author_id="999", rounds="0", expect_head="reply",
         expect_body=PREPARED_ANSWER),
    dict(name="marker open (remaining-questions wording), round 2: still replies",
         comments=[marker("c1", "2026-01-01T00:00:00Z", body=REMAINING_MARKER)],
         author_id="999", rounds="2", expect_head="reply",
         expect_body=PREPARED_ANSWER),
    dict(name="marker open, round 3 (bound exhausted): exhausted",
         comments=[marker("c1", "2026-01-01T00:00:00Z")],
         author_id="999", rounds="3", expect_head="exhausted"),
    dict(name="marker open, a qualifying (COLLABORATOR) reply postdates it: wait",
         comments=[marker("c1", "2026-01-01T00:00:00Z"),
                   comment("c2", "a-maintainer", "42", "2026-01-01T00:05:00Z",
                           association="COLLABORATOR")],
         author_id="999", rounds="1", expect_head="wait"),
    dict(name="marker open, the issue's own author (by id, NONE association) replies: wait",
         comments=[marker("c1", "2026-01-01T00:00:00Z"),
                   comment("c2", "the-reporter", ISSUE_AUTHOR_ID, "2026-01-01T00:05:00Z",
                           association="NONE")],
         author_id=ISSUE_AUTHOR_ID, rounds="0", expect_head="wait"),
    dict(name="marker open, a bot comment postdates it: still unanswered (reply) -- "
              "the original deadlock this feature closes",
         comments=[marker("c1", "2026-01-01T00:00:00Z"),
                   comment("c2", "metrics-bot[bot]", "9", "2026-01-01T00:05:00Z",
                           body="rollup", user_type="Bot", association="NONE")],
         author_id="999", rounds="0", expect_head="reply",
         expect_body=PREPARED_ANSWER),
    dict(name="marker open, a non-qualifying human (NONE, not the issue author) postdates it: "
              "still unanswered (reply)",
         comments=[marker("c1", "2026-01-01T00:00:00Z"),
                   comment("c2", "a-random-passerby", "777", "2026-01-01T00:05:00Z",
                           association="NONE")],
         author_id="999", rounds="0", expect_head="reply",
         expect_body=PREPARED_ANSWER),
    dict(name="marker open, a Bot account with a qualifying (COLLABORATOR) association "
              "postdates it: still unanswered (reply) -- the Bot check, not merely "
              "association, is what excludes it",
         comments=[marker("c1", "2026-01-01T00:00:00Z"),
                   comment("c2", "wing-commander[bot]", "1", "2026-01-01T00:05:00Z",
                           user_type="Bot", association="COLLABORATOR")],
         author_id="999", rounds="0", expect_head="reply",
         expect_body=PREPARED_ANSWER),
]

CLARIFY_SATISFIED_SCENARIOS = [
    dict(name="no markers ever: ok (vacuous)",
         comments=[comment("c1", "someone", "2", "2026-01-01T00:00:00Z", body="hi")],
         author_id="999", expect="ok"),
    dict(name="one marker, one qualifying reply after: ok",
         comments=[marker("c1", "2026-01-01T00:00:00Z"),
                   comment("c2", "a-maintainer", "42", "2026-01-01T00:05:00Z",
                           association="MEMBER")],
         author_id="999", expect="ok"),
    dict(name="one marker, only a non-qualifying reply after: unsatisfied",
         comments=[marker("c1", "2026-01-01T00:00:00Z"),
                   comment("c2", "metrics-bot[bot]", "9", "2026-01-01T00:05:00Z",
                           user_type="Bot", association="NONE")],
         author_id="999", expect="unsatisfied"),
    dict(name="two markers, only the first answered: unsatisfied",
         comments=[marker("c1", "2026-01-01T00:00:00Z"),
                   comment("c2", "a-maintainer", "42", "2026-01-01T00:05:00Z",
                           association="OWNER"),
                   marker("c3", "2026-01-01T00:10:00Z", body=REMAINING_MARKER)],
         author_id="999", expect="unsatisfied"),
    dict(name="two markers, both answered: ok",
         comments=[marker("c1", "2026-01-01T00:00:00Z"),
                   comment("c2", "a-maintainer", "42", "2026-01-01T00:05:00Z",
                           association="OWNER"),
                   marker("c3", "2026-01-01T00:10:00Z", body=REMAINING_MARKER),
                   comment("c4", "a-maintainer", "42", "2026-01-01T00:15:00Z",
                           association="OWNER")],
         author_id="999", expect="ok"),
]

CLARIFY_MARKERS_SCENARIOS = [
    dict(name="markers mode returns every marker, oldest first",
         comments=[marker("c2", "2026-01-01T00:10:00Z", body=REMAINING_MARKER),
                   marker("c1", "2026-01-01T00:00:00Z"),
                   comment("c3", "someone", "2", "2026-01-01T00:05:00Z", body="not a marker")],
         expect_ids=["c1", "c2"]),
]


def run_clarify_suite(script_path):
    failures = []
    for sc in CLARIFY_DECIDE_SCENARIOS:
        tag = f"[clarify decide: {sc['name']}]"
        comments_json = json.dumps(sc["comments"])
        rc, out, err = run_script(script_path, ["decide", sc["author_id"], sc["rounds"]], comments_json)
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
    for sc in CLARIFY_SATISFIED_SCENARIOS:
        tag = f"[clarify satisfied: {sc['name']}]"
        comments_json = json.dumps(sc["comments"])
        rc, out, err = run_script(script_path, ["satisfied", sc["author_id"]], comments_json)
        if rc != 0:
            failures.append(f"{tag} script exited {rc}: {out}{err}")
            continue
        got = out.strip()
        if got != sc["expect"]:
            failures.append(f"{tag} expected {sc['expect']!r}, got {got!r}")
    for sc in CLARIFY_MARKERS_SCENARIOS:
        tag = f"[clarify markers: {sc['name']}]"
        comments_json = json.dumps(sc["comments"])
        rc, out, err = run_script(script_path, ["markers"], comments_json)
        if rc != 0:
            failures.append(f"{tag} script exited {rc}: {out}{err}")
            continue
        try:
            got_ids = [c["id"] for c in json.loads(out)]
        except (json.JSONDecodeError, TypeError, KeyError) as exc:
            failures.append(f"{tag} could not parse output as a JSON array of comments: {exc} (full: {out!r})")
            continue
        if got_ids != sc["expect_ids"]:
            failures.append(f"{tag} expected ids {sc['expect_ids']!r}, got {got_ids!r}")
    return failures


# --------------------------------------------------------------------------
# Merge-decision scenarios (contracts/gate-decision-scripts.md)
# --------------------------------------------------------------------------
DEFAULT_BASE = "main"


def pr(number, head_ref, base_ref=DEFAULT_BASE, mergeable="MERGEABLE",
       merge_state="CLEAN", is_draft=False, state="OPEN", status_checks=None):
    return {"number": number, "headRefName": head_ref, "baseRefName": base_ref,
            "mergeable": mergeable, "mergeStateStatus": merge_state,
            "isDraft": is_draft, "state": state,
            "statusCheckRollup": status_checks if status_checks is not None else []}


COMPLETED_CHECK = {"status": "COMPLETED", "conclusion": "FAILURE"}
PENDING_CHECK = {"status": "IN_PROGRESS", "conclusion": None}
# Legacy commit StatusContext shape -- no `status`/`conclusion` at all, only
# `state` (SUCCESS/PENDING/ERROR/FAILURE). A required check backed by the
# Status API (not a Check Run) reports this shape in statusCheckRollup.
STATUS_CONTEXT_SUCCESS = {"state": "SUCCESS"}
STATUS_CONTEXT_PENDING = {"state": "PENDING"}
# EXPECTED: the state a required legacy check reports before any status has
# been posted for the commit at all -- still pending, not yet resolved.
STATUS_CONTEXT_EXPECTED = {"state": "EXPECTED"}

MERGE_SCENARIOS = [
    dict(name="empty array: none", prs=[], prefix="spec-draft/", slug="055-foo",
         expected_base=DEFAULT_BASE, expect_head="none"),
    dict(name="mismatched headRefName: wrong-attempt",
         prs=[pr(1, "spec-draft/054-bar")],
         prefix="spec-draft/", slug="055-foo", expected_base=DEFAULT_BASE,
         expect_head="wrong-attempt"),
    dict(name="right head, mismatched baseRefName: wrong-base",
         prs=[pr(1, "spec-draft/055-foo", base_ref="some-other-branch")],
         prefix="spec-draft/", slug="055-foo", expected_base=DEFAULT_BASE,
         expect_head="wrong-base"),
    dict(name="draft PR: wait",
         prs=[pr(1, "spec-draft/055-foo", is_draft=True)],
         prefix="spec-draft/", slug="055-foo", expected_base=DEFAULT_BASE,
         expect_head="wait"),
    dict(name="mergeStateStatus UNKNOWN: wait",
         prs=[pr(1, "plan/055-foo", base_ref="spec/055-foo", merge_state="UNKNOWN")],
         prefix="plan/", slug="055-foo", expected_base="spec/055-foo",
         expect_head="wait"),
    dict(name="mergeStateStatus BEHIND: wait",
         prs=[pr(1, "plan/055-foo", base_ref="spec/055-foo", merge_state="BEHIND")],
         prefix="plan/", slug="055-foo", expected_base="spec/055-foo",
         expect_head="wait"),
    dict(name="mergeable CONFLICTING: conflicting",
         prs=[pr(1, "spec/055-foo", mergeable="CONFLICTING")],
         prefix="spec/", slug="055-foo", expected_base=DEFAULT_BASE,
         expect_head="conflicting"),
    dict(name="mergeStateStatus BLOCKED, no pending check: blocked",
         prs=[pr(1, "spec/055-foo", merge_state="BLOCKED",
                 status_checks=[COMPLETED_CHECK])],
         prefix="spec/", slug="055-foo", expected_base=DEFAULT_BASE,
         expect_head="blocked"),
    dict(name="mergeStateStatus BLOCKED, a check still running: wait, not blocked",
         prs=[pr(1, "spec/055-foo", merge_state="BLOCKED",
                 status_checks=[COMPLETED_CHECK, PENDING_CHECK])],
         prefix="spec/", slug="055-foo", expected_base=DEFAULT_BASE,
         expect_head="wait"),
    dict(name="mergeStateStatus BLOCKED, no check has registered yet (freshly opened PR): wait, not blocked",
         prs=[pr(1, "spec/055-foo", merge_state="BLOCKED", status_checks=[])],
         prefix="spec/", slug="055-foo", expected_base=DEFAULT_BASE,
         expect_head="wait"),
    dict(name="mergeStateStatus BLOCKED, a legacy StatusContext (state, no status/conclusion) still pending: wait",
         prs=[pr(1, "spec/055-foo", merge_state="BLOCKED",
                 status_checks=[STATUS_CONTEXT_PENDING])],
         prefix="spec/", slug="055-foo", expected_base=DEFAULT_BASE,
         expect_head="wait"),
    dict(name="mergeStateStatus BLOCKED, a legacy StatusContext (state, no status/conclusion) resolved: blocked",
         prs=[pr(1, "spec/055-foo", merge_state="BLOCKED",
                 status_checks=[STATUS_CONTEXT_SUCCESS])],
         prefix="spec/", slug="055-foo", expected_base=DEFAULT_BASE,
         expect_head="blocked"),
    dict(name="mergeStateStatus BLOCKED, a legacy StatusContext in EXPECTED "
              "(no status has posted yet): wait, not blocked",
         prs=[pr(1, "spec/055-foo", merge_state="BLOCKED",
                 status_checks=[STATUS_CONTEXT_EXPECTED])],
         prefix="spec/", slug="055-foo", expected_base=DEFAULT_BASE,
         expect_head="wait"),
    dict(name="clean and mergeable: merge <number>",
         prs=[pr(42, "spec-draft/055-foo")], prefix="spec-draft/", slug="055-foo",
         expected_base=DEFAULT_BASE, expect_head="merge", expect_number="42"),
]


def run_merge_suite(script_path):
    failures = []
    for sc in MERGE_SCENARIOS:
        tag = f"[merge: {sc['name']}]"
        prs_json = json.dumps(sc["prs"])
        rc, out, err = run_script(script_path, [sc["prefix"], sc["slug"], sc["expected_base"]], prs_json)
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
    ("wait collapsed into reply (a qualifying reply already posted is ignored)",
     'if [ "$reply_exists" = "true" ]; then\n      echo "wait"\n      exit 0\n    fi',
     'if false; then\n      echo "wait"\n      exit 0\n    fi'),
    ("the Bot filter is dropped from qualification (a bot comment would then count as a reply)",
     '((.user.type // "") != "Bot")',
     'true'),
]

MERGE_MUTATIONS = [
    ("wrong-attempt collapsed into merge (leftover PR from a previous attempt acted on)",
     'if [ "$head_ref" != "$expected_head" ]; then',
     'if false; then'),
    ("wrong-base collapsed into merge (a retargeted PR would be merged)",
     'if [ "$base_ref" != "$expected_base" ]; then',
     'if false; then'),
    ("conflicting collapsed into merge",
     'if [ "$mergeable" = "CONFLICTING" ]; then',
     'if false; then'),
    ("a pending required check reads as blocked instead of wait",
     'if [ "$still_pending" = "true" ]; then',
     'if false; then'),
    ("an empty statusCheckRollup (no check registered yet on a freshly "
     "opened PR) reads as blocked instead of wait",
     'if ($rollup | length) == 0 then true',
     'if ($rollup | length) == 0 then false'),
    ("a legacy StatusContext rollup entry (state, no status/conclusion) is "
     "read with the CheckRun-shaped predicate and always reads as pending, "
     "hanging forever",
     'if has("state") then (.state == "PENDING" or .state == "EXPECTED")',
     'if false then (.state == "PENDING" or .state == "EXPECTED")'),
    ("a legacy StatusContext in EXPECTED (no status posted yet) reads as "
     "resolved instead of still pending",
     '.state == "PENDING" or .state == "EXPECTED"',
     '.state == "PENDING"'),
    ("draft collapsed into merge",
     'if [ "$is_draft" = "true" ]; then',
     'if false; then'),
]


def run_mutation(script_path, run_suite, label, old, new, failures):
    mutated_text = mutate(script_path, old, new, label)
    # Keyed on this process's own pid, not a fixed name -- two --self-test
    # invocations running in parallel (observed once on Windows) otherwise
    # race on the same file, and the loser's os.remove in the other's
    # `finally` raises FileNotFoundError (maintainer feedback on PR #389,
    # second review, Verify item: a race, not a logic defect).
    tmp_path = f"{script_path}.{os.getpid()}.mutated.tmp"
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
    """Gate 66 self-test: each documented branch fails its own mutation."""
    failures = []
    for label, old, new in CLARIFY_MUTATIONS:
        run_mutation(CLARIFY_SCRIPT, run_clarify_suite, label, old, new, failures)
    for label, old, new in MERGE_MUTATIONS:
        run_mutation(MERGE_SCRIPT, run_merge_suite, label, old, new, failures)

    total = len(CLARIFY_MUTATIONS) + len(MERGE_MUTATIONS)
    print(f"Gate 66 self-test: {total} mutation(s); {len(failures)} failure(s).")
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

    total = (len(CLARIFY_DECIDE_SCENARIOS) + len(CLARIFY_SATISFIED_SCENARIOS)
             + len(CLARIFY_MARKERS_SCENARIOS) + len(MERGE_SCENARIOS))
    print(f"auto-release e2e gate decisions: "
          f"{total} scenario(s); "
          f"{len(failures)} failure(s).")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
