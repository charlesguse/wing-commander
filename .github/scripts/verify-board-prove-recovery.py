#!/usr/bin/env python3
"""Gate 136 — board_prove_recovery.is_recoverable()/find_recoverable_items()
resolve FR-011/FR-011a/FR-011b/FR-011c correctly (specs/096-durable-prove-
entry research.md D5), and board_item_marker.write_marker()/main() carry
the two fields this feature adds (research.md D4) round-trip, including a
pre-feature marker (five keys only) reading back
`outcome_reason=None, recovery_attempted=False` rather than raising.
"""
import json
import os
import shutil
import sys
import tempfile

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from board_item_marker import write_marker, read_marker_with_timestamp  # noqa: E402
from board_prove_displacement import RECORDED_REASON  # noqa: E402
from board_prove_recovery import (  # noqa: E402
    RECOVERY_DIRECTED_INPUT, is_recoverable, find_recoverable_items,
)
from wc_shell_harness import (  # noqa: E402
    ensure_jq, find_step, resolve_bash, run_step, use_utf8_stdout)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REPO_BOARD_LOOP = os.path.join(REPO_ROOT, ".github", "workflows", "board-loop.yml")

BOT_LOGIN = "wing-commander-bot[bot]"
BOT_USER = {"login": BOT_LOGIN, "type": "Bot"}

BASH = None
REPO = "acme/widgets"

GATE_STEP_NAME = "Resolve the originating issue and decide whether prove is entered"


def _board_pr_owned_jq():
    """board-loop.yml's own top-level env: BOARD_PR_OWNED_JQ -- not part of
    the step's `run:` text find_step() returns, so the harness supplies it
    the way a real run's env: merging would. Read from its one home, never
    re-typed here: a copy would keep this fixture green on a program the
    workflow no longer runs (code review of #893)."""
    with open(REPO_BOARD_LOOP, encoding="utf-8") as fh:
        prog = (yaml.safe_load(fh) or {}).get("env", {}).get("BOARD_PR_OWNED_JQ")
    if not prog:
        sys.exit("::error file={0}::verify-board-prove-recovery: board-loop.yml's "
                 "top-level env: has no BOARD_PR_OWNED_JQ for the prove-gate step "
                 "to read.".format(REPO_BOARD_LOOP))
    return prog


BOARD_PR_OWNED_JQ = _board_pr_owned_jq()

GH_API_STUB = r"""#!/bin/sh
case " $* " in
  *" api "*"/pulls/"*)
    cat "$GH_PR_JSON"
    exit 0
    ;;
  *" api "*"/comments"*)
    cat "$GH_COMMENTS_JSONL"
    exit 0
    ;;
esac
exit 0
"""

def marker_dict(step="prove", outcome_reason=None, recovery_attempted=False):
    return {"step": step, "round": 0, "pr": None, "branch": None, "base_sha": None,
            "outcome_reason": outcome_reason, "recovery_attempted": recovery_attempted}


IS_RECOVERABLE_CASES = [
    ("no outcome_reason key (pre-feature marker)",
     {"step": "prove", "round": 0, "pr": None, "branch": None, "base_sha": None},
     False),
    ("outcome_reason group-busy", marker_dict(outcome_reason="group-busy"), False),
    ("outcome_reason not-started", marker_dict(outcome_reason="not-started"), False),
    ("outcome_reason unfinished", marker_dict(outcome_reason="unfinished"), False),
    ("outcome_reason displaced", marker_dict(outcome_reason="displaced"), False),
    ("outcome_reason no-target", marker_dict(outcome_reason="no-target"), False),
    ("outcome_reason nothing-reaches", marker_dict(outcome_reason="nothing-reaches"), False),
    ("outcome_reason failure", marker_dict(outcome_reason="failure"), False),
    ("outcome_reason RECORDED_REASON", marker_dict(outcome_reason=RECORDED_REASON), True),
    ("outcome_reason uncorrelated", marker_dict(outcome_reason="uncorrelated"), True),
    ("RECORDED_REASON but recovery_attempted",
     marker_dict(outcome_reason=RECORDED_REASON, recovery_attempted=True), False),
    ("uncorrelated but recovery_attempted",
     marker_dict(outcome_reason="uncorrelated", recovery_attempted=True), False),
    ("step not prove", marker_dict(step="proven", outcome_reason=RECORDED_REASON), False),
]


def run_is_recoverable():
    failures = 0
    for name, marker, expected in IS_RECOVERABLE_CASES:
        got = is_recoverable(marker)
        if got != expected:
            failures += 1
            print("::error::verify-board-prove-recovery: is_recoverable {0}: "
                  "expected {1!r}, got {2!r}.".format(name, expected, got))
        else:
            print("[ok] is_recoverable {0} == {1!r}".format(name, got))
    return failures


def comment(created_at, outcome_reason=None, recovery_attempted=False, step="prove"):
    return {"created_at": created_at,
            "body": "Not proven -- " + write_marker(
                step, 0, None, None, None,
                outcome_reason=outcome_reason, recovery_attempted=recovery_attempted),
            "user": BOT_USER}


def run_find_recoverable_items():
    failures = 0

    merged_prs_by_issue = [
        {"issue": 10, "pr": 110, "merged_at": "2026-01-01T00:00:00Z"},
        {"issue": 11, "pr": 111, "merged_at": "2026-01-02T00:00:00Z"},
        {"issue": 12, "pr": 112, "merged_at": "2026-01-03T00:00:00Z"},
    ]
    comments_by_issue = {
        "10": [comment("2026-01-01T01:00:00Z", outcome_reason=RECORDED_REASON)],
        "11": [comment("2026-01-01T00:30:00Z", outcome_reason="uncorrelated")],
        "12": [comment("2026-01-03T01:00:00Z", outcome_reason=RECORDED_REASON)],
    }
    open_issue_numbers = {10, 11}  # issue 12 is excluded (not open)

    expected = [
        {"issue": 11, "merged_pr": 111, "marker_created_at": "2026-01-01T00:30:00Z",
         "outcome_reason": "uncorrelated"},
        {"issue": 10, "merged_pr": 110, "marker_created_at": "2026-01-01T01:00:00Z",
         "outcome_reason": RECORDED_REASON},
    ]
    got = find_recoverable_items(merged_prs_by_issue, comments_by_issue, open_issue_numbers, BOT_LOGIN)
    if got != expected:
        failures += 1
        print("::error::verify-board-prove-recovery: find_recoverable_items two candidates: "
              "expected {0!r}, got {1!r}.".format(expected, got))
    else:
        print("[ok] find_recoverable_items two candidates, oldest-first, excludes closed issue")

    # Issue 11 is recoverable but absent from open_issue_numbers here --
    # excluded even though its own marker would otherwise qualify.
    expected_excluding_11 = [
        {"issue": 10, "merged_pr": 110, "marker_created_at": "2026-01-01T01:00:00Z",
         "outcome_reason": RECORDED_REASON},
    ]
    got = find_recoverable_items(merged_prs_by_issue, comments_by_issue, {10}, BOT_LOGIN)
    if got != expected_excluding_11:
        failures += 1
        print("::error::verify-board-prove-recovery: find_recoverable_items issue-not-open: "
              "expected {0!r}, got {1!r}.".format(expected_excluding_11, got))
    else:
        print("[ok] find_recoverable_items excludes a candidate absent from open_issue_numbers")

    # spec 097 FR-008: an honoured stop labels the issue board:stalled; it is
    # never a recovery candidate while held, and is again once released.
    got = find_recoverable_items(merged_prs_by_issue, comments_by_issue, open_issue_numbers, BOT_LOGIN,
                                 stalled_issue_numbers={11})
    if got != expected_excluding_11:
        failures += 1
        print("::error::verify-board-prove-recovery: find_recoverable_items board:stalled: "
              "expected {0!r}, got {1!r}.".format(expected_excluding_11, got))
    else:
        print("[ok] find_recoverable_items excludes a board:stalled issue")

    return failures


def run_marker_round_trip():
    failures = 0

    cases = [
        ("no outcome_reason/recovery_attempted (defaults)", {}, None, False),
        ("outcome_reason set, recovery_attempted false",
         {"outcome_reason": RECORDED_REASON}, RECORDED_REASON, False),
        ("outcome_reason set, recovery_attempted true",
         {"outcome_reason": "uncorrelated", "recovery_attempted": True}, "uncorrelated", True),
    ]
    for name, kwargs, expected_reason, expected_attempted in cases:
        rendered = write_marker("prove", 0, None, None, None, **kwargs)
        comment_body = "Not proven -- " + rendered
        pair = read_marker_with_timestamp(
            [{"created_at": "2026-01-01T00:00:00Z", "body": comment_body, "user": BOT_USER}],
            BOT_LOGIN)
        if pair is None:
            failures += 1
            print("::error::verify-board-prove-recovery: marker round-trip {0}: "
                  "no marker read back.".format(name))
            continue
        _created_at, marker = pair
        if marker.get("outcome_reason") != expected_reason or marker.get("recovery_attempted") != expected_attempted:
            failures += 1
            print("::error::verify-board-prove-recovery: marker round-trip {0}: "
                  "expected (outcome_reason={1!r}, recovery_attempted={2!r}), "
                  "got (outcome_reason={3!r}, recovery_attempted={4!r}).".format(
                      name, expected_reason, expected_attempted,
                      marker.get("outcome_reason"), marker.get("recovery_attempted")))
        else:
            print("[ok] marker round-trip {0}".format(name))

    # A marker written before this feature (five keys only) reads back with
    # the two new fields defaulted, rather than raising.
    pre_feature_payload = json.dumps(
        {"step": "prove", "round": 0, "pr": None, "branch": None, "base_sha": None},
        sort_keys=True)
    pre_feature_marker = "<!-- wing-commander-board-item: {0} -->".format(pre_feature_payload)
    pair = read_marker_with_timestamp(
        [{"created_at": "2026-01-01T00:00:00Z",
          "body": "Not proven -- " + pre_feature_marker, "user": BOT_USER}],
        BOT_LOGIN)
    if pair is None:
        failures += 1
        print("::error::verify-board-prove-recovery: pre-feature marker (five keys): not read back at all.")
    else:
        _created_at, marker = pair
        if marker.get("outcome_reason") is not None or marker.get("recovery_attempted"):
            failures += 1
            print("::error::verify-board-prove-recovery: pre-feature marker (five keys): "
                  "expected outcome_reason=None, recovery_attempted=False, got {0!r}.".format(marker))
        else:
            print("[ok] pre-feature marker (five keys) reads outcome_reason=None, recovery_attempted=False")

    return failures


def run_directed_recovery_input_spelling():
    """research.md D5/D6: board-loop.yml cannot import
    RECOVERY_DIRECTED_INPUT (a workflow_dispatch input name is YAML schema,
    resolved before any step runs) -- so this checks the same literal
    appears, verbatim, at the three sites that would otherwise silently
    drift from it: the input's own declaration, the recovery step's
    dispatch flag, and at least one `inputs.<name>` read."""
    failures = 0
    with open(REPO_BOARD_LOOP, encoding="utf-8") as fh:
        text = fh.read()

    declaration = "      {0}:".format(RECOVERY_DIRECTED_INPUT)
    if declaration not in text:
        failures += 1
        print("::error::verify-board-prove-recovery: board-loop.yml declares no "
              "`{0}` workflow_dispatch input (expected {1!r}).".format(
                  RECOVERY_DIRECTED_INPUT, declaration))
    else:
        print("[ok] board-loop.yml declares the `{0}` workflow_dispatch input".format(
            RECOVERY_DIRECTED_INPUT))

    dispatch_flag = "-f {0}=true".format(RECOVERY_DIRECTED_INPUT)
    if dispatch_flag not in text:
        failures += 1
        print("::error::verify-board-prove-recovery: board-loop.yml's recovery dispatch "
              "never sets `{0}` (expected {1!r}).".format(RECOVERY_DIRECTED_INPUT, dispatch_flag))
    else:
        print("[ok] board-loop.yml's recovery dispatch sets `{0}`".format(RECOVERY_DIRECTED_INPUT))

    read_expr = "inputs.{0}".format(RECOVERY_DIRECTED_INPUT)
    if text.count(read_expr) < 2:
        failures += 1
        print("::error::verify-board-prove-recovery: board-loop.yml reads `{0}` fewer than "
              "twice (expected the recovery notice and the metrics-label branch both to "
              "read it).".format(read_expr))
    else:
        print("[ok] board-loop.yml reads `{0}` at least twice".format(read_expr))

    return failures


DISPLACEMENT_STEP_NAME = "- name: Detect a merge whose proof run never started (FR-010b)"


def run_displacement_writer_passes_outcome_reason():
    """FR-011 case (a), maintainer review: a marker the displacement step
    writes with no `--outcome-reason` can never satisfy
    is_recoverable()'s own `outcome_reason ==
    board_prove_displacement.RECORDED_REASON` check -- the reader accepting
    the field is not enough; the one writer that records a genuine
    displacement must actually pass it, sourced from
    find_undetected_merges()'s own `recorded_reason` field (the one home),
    never a re-typed literal."""
    failures = 0
    with open(REPO_BOARD_LOOP, encoding="utf-8") as fh:
        text = fh.read()

    start = text.find(DISPLACEMENT_STEP_NAME)
    if start == -1:
        failures += 1
        print("::error::verify-board-prove-recovery: board-loop.yml has no {0!r} "
              "step to check.".format(DISPLACEMENT_STEP_NAME))
        return failures
    next_step = text.find("\n      - name:", start + len(DISPLACEMENT_STEP_NAME))
    block = text[start:next_step if next_step != -1 else len(text)]

    if "--step prove" not in block:
        failures += 1
        print("::error::verify-board-prove-recovery: the displacement step no longer "
              "writes a `--step prove` marker at all.")
        return failures

    if "--outcome-reason" not in block:
        failures += 1
        print("::error::verify-board-prove-recovery: the displacement step's own "
              "`board_item_marker.py --step prove` call passes no `--outcome-reason` "
              "-- a marker it writes can never satisfy is_recoverable()'s "
              "RECORDED_REASON check, so FR-011 case (a) is unreachable.")
    elif ".recorded_reason" not in block:
        failures += 1
        print("::error::verify-board-prove-recovery: the displacement step's "
              "`--outcome-reason` does not read `.recorded_reason` off its own row -- "
              "expected find_undetected_merges()'s own field to be the one home, "
              "never a re-typed literal.")
    else:
        print("[ok] the displacement step's own marker write passes "
              "`--outcome-reason`, sourced from find_undetected_merges()'s own "
              "`recorded_reason` field")

    return failures


def _run_gate_step(work, pr_json, comments, event_name="workflow_dispatch",
                   pr_number="777", issue="501"):
    """Executes board-loop.yml's SHIPPED "Resolve the originating issue and
    decide whether prove is entered" step (research.md D3/maintainer review:
    a directed recovery dispatch is, structurally, an ordinary directed
    `prove` dispatch -- this is the one job that decides whether such a
    dispatch ever reaches `prove` at all). Returns (rc, out, outputs)."""
    step = find_step(REPO_BOARD_LOOP, GATE_STEP_NAME)
    # the step's own `sys.path.insert(0, ".github/scripts")` idiom resolves
    # relative to cwd -- a real run's cwd is the checked-out repo root, so
    # the harness copies the real scripts dir into its own workdir instead
    # of a reimplementation (same pattern as verify-board-loop-resume-
    # gating.py's own harness).
    shutil.copytree(os.path.join(REPO_ROOT, ".github", "scripts"),
                    os.path.join(work, ".github", "scripts"),
                    ignore=shutil.ignore_patterns("tests", "fixtures", "__pycache__"))
    bindir = os.path.join(work, "bin")
    os.makedirs(bindir, exist_ok=True)
    with open(os.path.join(bindir, "gh"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(GH_API_STUB)
    os.chmod(os.path.join(bindir, "gh"), 0o755)

    pr_json_path = os.path.join(work, "pr.json")
    with open(pr_json_path, "w", encoding="utf-8") as fh:
        json.dump(pr_json, fh)
    comments_jsonl_path = os.path.join(work, "comments.jsonl")
    with open(comments_jsonl_path, "w", encoding="utf-8") as fh:
        for c in comments:
            fh.write(json.dumps(c) + "\n")

    path = bindir + os.pathsep + os.environ["PATH"]
    runner_temp = os.path.join(work, "runner_temp")
    os.makedirs(runner_temp, exist_ok=True)
    rc, out, outputs, _ = run_step(
        BASH, step["run"], work,
        {"GH_TOKEN": "x", "EVENT_NAME": event_name, "PR_BODY": "",
         "PR_NUMBER": pr_number, "MERGED_EVENT": "", "DIRECTED_ISSUE": issue,
         "BOT_LOGIN": BOT_LOGIN, "GITHUB_REPOSITORY": REPO,
         "BOARD_PR_OWNED_JQ": BOARD_PR_OWNED_JQ,
         "GH_PR_JSON": pr_json_path, "GH_COMMENTS_JSONL": comments_jsonl_path,
         "PATH": path},
        runner_temp)
    return rc, out, outputs


def run_directed_dispatch_reaches_prove_gate():
    """Maintainer review: `gh pr view --json merged` is not a real field,
    and the ownership check read `$GITHUB_EVENT_PATH`'s `.pull_request`,
    null on `workflow_dispatch` -- both stranded every directed/recovery
    prove dispatch in `prove-gate` before this feature's own fix. Drives
    the shipped step end to end on a `workflow_dispatch` input shape (never
    a copy of its logic) and asserts `eligible` actually reaches `true`."""
    failures = 0

    with tempfile.TemporaryDirectory() as work:
        marker_comment = comment("2026-01-01T00:00:00Z", outcome_reason=RECORDED_REASON)
        rc, out, outputs = _run_gate_step(
            work,
            {"merged": True, "labels": [{"name": "board:owned"}],
             "head": {"repo": {"full_name": REPO}}},
            [marker_comment])
        if rc != 0:
            failures += 1
            print("::error::verify-board-prove-recovery: directed dispatch through "
                  "prove-gate exited {0}: {1}".format(rc, out))
        elif outputs.get("eligible") != "true" or outputs.get("issue-number") != "501":
            failures += 1
            print("::error::verify-board-prove-recovery: a directed workflow_dispatch "
                  "for a merged, board:owned PR did not reach eligible=true -- "
                  "outputs={0!r}, output={1}".format(outputs, out))
        else:
            print("[ok] a directed workflow_dispatch reaches prove-gate's own "
                  "eligible=true (gh api .../pulls/<N> + ownership read off the "
                  "fetched file, not $GITHUB_EVENT_PATH)")

    with tempfile.TemporaryDirectory() as work:
        marker_comment = comment("2026-01-01T00:00:00Z", outcome_reason=RECORDED_REASON)
        rc, out, outputs = _run_gate_step(
            work,
            {"merged": True, "labels": [],
             "head": {"repo": {"full_name": "someone-else/fork"}}},
            [marker_comment])
        if rc != 0:
            failures += 1
            print("::error::verify-board-prove-recovery: not-owned directed dispatch "
                  "exited {0}: {1}".format(rc, out))
        elif outputs.get("eligible") != "false":
            failures += 1
            print("::error::verify-board-prove-recovery: a directed workflow_dispatch "
                  "for a PR with no board:owned label and a foreign head.repo should "
                  "read eligible=false -- outputs={0!r}".format(outputs))
        else:
            print("[ok] a directed workflow_dispatch for a not-board:owned PR reads "
                  "eligible=false (ownership re-derived off the fetched file, not "
                  "a null $GITHUB_EVENT_PATH)")

    return failures


def run_board_pr_owned_jq_single_home():
    """BOARD_PR_OWNED_JQ's program text lives once, in board-loop.yml's
    top-level env:, and every reader takes it from there (CLAUDE.md "Shared
    logic has exactly one home"; code review of #940). This fixture used to
    re-type it; this check fails on the next copy anywhere under .github/."""
    failures = 0
    copies = []
    for top in ("workflows", "actions", "scripts"):
        for dirpath, dirnames, filenames in os.walk(os.path.join(REPO_ROOT, ".github", top)):
            dirnames[:] = [d for d in dirnames if d != "__pycache__"]
            for name in filenames:
                path = os.path.join(dirpath, name)
                try:
                    with open(path, encoding="utf-8") as fh:
                        n = fh.read().count(BOARD_PR_OWNED_JQ)
                except (OSError, UnicodeDecodeError):
                    continue
                if n:
                    copies.append((os.path.relpath(path, REPO_ROOT), n))
    if copies != [(os.path.relpath(REPO_BOARD_LOOP, REPO_ROOT), 1)]:
        failures += 1
        print("::error::verify-board-prove-recovery: BOARD_PR_OWNED_JQ's program text "
              "must appear exactly once, in board-loop.yml's top-level env:, found "
              "{0!r} -- read it from there instead of re-typing it.".format(copies))
    else:
        print("[ok] BOARD_PR_OWNED_JQ's program text has one home, board-loop.yml's env:")
    return failures


def run():
    failures = (run_is_recoverable() + run_find_recoverable_items() + run_marker_round_trip()
                + run_directed_recovery_input_spelling()
                + run_displacement_writer_passes_outcome_reason()
                + run_directed_dispatch_reaches_prove_gate()
                + run_board_pr_owned_jq_single_home())
    print("verify-board-prove-recovery: {0} failure(s).".format(failures))
    return 1 if failures else 0


if __name__ == "__main__":
    use_utf8_stdout()
    ensure_jq()
    BASH = resolve_bash()
    sys.exit(run())
