#!/usr/bin/env python3
"""Gate 128 -- an honoured stop records its stop point, and the kill switch
keeps writing nothing (specs/097-recorded-stop-point, FR-019,
specs/097-recorded-stop-point/contracts/gate-128-stop-point-recording.md).

WHAT IT CHECKS
--------------
1. Structural: `.github/actions/wing-commander-board-stop-check/action.yml`
   has a step, gated on `stop-cause == 'stop-request'`, that invokes
   `board_item_marker.py --step stalled ... --add-label "board:stalled"`.
2. Provenance: that step's invocation, and the composite's own
   `board_stop_check.py` invocation, run from `$RUNNER_TEMP/wc-pristine/
   scripts/...`, never a bare `.github/scripts/...` path (spec 095
   FR-011/FR-012, research.md D8).
3. Cause-aware messaging: none of `.github/workflows/board-loop.yml`'s six
   stand-down messages hardcodes "kill switch" prose unconditionally --
   each reads `stop-cause` to pick its wording (FR-014).
4. Decision-function agreement: `find_stop_command_comment()`'s "did a
   comment win" answer agrees with `find_stop_request()`'s `stand_down` on
   every fixture under `.github/scripts/tests/board-stop-check/` (Gate 87's
   own corpus, reused, plus this feature's FR-016/FR-009 fixtures).
5. Selection exclusion: a fixture issue carrying a `stalled` marker plus
   `board:stalled` is excluded by `is_excluded()` and never returned by
   `in_flight_candidate()`/`select()`, across ten simulated passes (SC-001).
6. No write on kill-switch-only/closed-issue: the record-write step's own
   `if:` is exactly `stop-cause == 'stop-request'` -- never a condition
   that would also admit `"kill-switch"`/`"closed-issue"` (FR-011/FR-013).

Each check's own mutation is applied under --self-test and must be caught
(Principle VIII, SC-009) -- see contracts/gate-128-stop-point-recording.md.
"""
import glob
import json
import os
import re
import sys

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import board_eligibility  # noqa: E402
import board_stop_check  # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
COMPOSITE = os.path.join(
    REPO_ROOT, ".github", "actions", "wing-commander-board-stop-check", "action.yml")
BOARD_LOOP = os.path.join(REPO_ROOT, ".github", "workflows", "board-loop.yml")
FIXTURES_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "tests", "board-stop-check")
BOT_LOGIN = "wing-commander-bot[bot]"

RECORD_WRITE_IF_RE = re.compile(r"stop-cause\s*==\s*'stop-request'")
RECORD_WRITE_INVOCATION_RE = re.compile(
    r"board_item_marker\.py[\s\S]*?--step\s+stalled[\s\S]*?--add-label\s+\"board:stalled\"")
BARE_SCRIPT_PATH_RE = re.compile(
    r"(?<!wc-pristine/scripts/)\.github/scripts/(board_stop_check|board_item_marker)\.py")
PRISTINE_BOARD_STOP_CHECK_RE = re.compile(
    r"wc-pristine/scripts/board_stop_check\.py")


def _load_composite_steps(text=None):
    with open(COMPOSITE, encoding="utf-8") as fh:
        doc = yaml.safe_load(text if text is not None else fh.read())
    return doc["runs"]["steps"]


def _composite_text():
    with open(COMPOSITE, encoding="utf-8") as fh:
        return fh.read()


def _find_step(steps, step_id):
    for step in steps:
        if (step or {}).get("id") == step_id:
            return step
    return None


def _record_write_step(steps):
    """The step this feature adds: gated on stop-cause == 'stop-request',
    invoking board_item_marker.py --step stalled ... --add-label
    "board:stalled". Found by shape, not by a hardcoded id, so a rename
    does not itself break this gate."""
    for step in steps:
        step = step or {}
        if_text = str(step.get("if") or "")
        run_text = str(step.get("run") or "")
        if RECORD_WRITE_IF_RE.search(if_text) and RECORD_WRITE_INVOCATION_RE.search(run_text):
            return step
    return None


# --- Check 1: the record-write step exists -----------------------------
def check_record_write_present(steps=None, verbose=True):
    steps = steps if steps is not None else _load_composite_steps()
    step = _record_write_step(steps)
    if step is None:
        if verbose:
            print("::error::verify-stop-point-recording: no step in {0} is gated on "
                  "stop-cause == 'stop-request' and invokes board_item_marker.py "
                  "--step stalled ... --add-label \"board:stalled\" (check 1)."
                  .format(COMPOSITE))
        return 1
    if verbose:
        print("[ok] check 1: the record-write step is present")
    return 0


# --- Check 2: provenance -------------------------------------------------
def check_provenance(steps=None, verbose=True):
    steps = steps if steps is not None else _load_composite_steps()
    check_step = _find_step(steps, "check")
    record_step = _record_write_step(steps)
    combined = str((check_step or {}).get("run") or "") + "\n" + str((record_step or {}).get("run") or "")
    failures = 0
    bare = BARE_SCRIPT_PATH_RE.search(combined)
    if bare:
        failures += 1
        if verbose:
            print("::error::verify-stop-point-recording: {0!r} references a bare "
                  ".github/scripts/ path instead of $RUNNER_TEMP/wc-pristine/scripts/ "
                  "(check 2).".format(bare.group(0)))
    if not PRISTINE_BOARD_STOP_CHECK_RE.search(str((check_step or {}).get("run") or "")):
        failures += 1
        if verbose:
            print("::error::verify-stop-point-recording: the `check` step does not "
                  "invoke board_stop_check.py from $RUNNER_TEMP/wc-pristine/scripts/ "
                  "(check 2).")
    if not failures and verbose:
        print("[ok] check 2: both invocations run from the pristine snapshot")
    return failures


# --- Check 3: cause-aware messaging -------------------------------------
KILL_SWITCH_TEXT_RE = re.compile(r"kill switch", re.IGNORECASE)
STOP_CAUSE_REF_RE = re.compile(r"stop-cause|STOP_CAUSE", re.IGNORECASE)


def _board_loop_jobs(doc):
    return (doc.get("jobs") or {}).items()


def check_cause_aware_messaging(board_loop_doc=None, verbose=True):
    if board_loop_doc is None:
        with open(BOARD_LOOP, encoding="utf-8") as fh:
            board_loop_doc = yaml.safe_load(fh)
    failures = 0
    for job_id, job in _board_loop_jobs(board_loop_doc):
        steps = (job or {}).get("steps") or []
        if not any((s or {}).get("id") == "killswitch-recheck" for s in steps):
            continue
        for step in steps:
            run_text = str((step or {}).get("run") or "")
            if not run_text:
                continue
            if KILL_SWITCH_TEXT_RE.search(run_text) and not STOP_CAUSE_REF_RE.search(run_text):
                failures += 1
                if verbose:
                    print("::error::verify-stop-point-recording: job {0!r} step {1!r} "
                          "hardcodes \"kill switch\" prose with no stop-cause reference "
                          "(check 3).".format(job_id, (step or {}).get("name")))
    if not failures and verbose:
        print("[ok] check 3: every stand-down message reads stop-cause")
    return failures


# --- Check 4: decision-function agreement -------------------------------
def _fixture_files():
    return sorted(
        p for p in glob.glob(os.path.join(FIXTURES_DIR, "*.json"))
        if os.path.basename(p) != "stop-command-cases.json")


def check_decision_function_agreement(verbose=True):
    failures = 0
    files = _fixture_files()
    if not files:
        print("::error::verify-stop-point-recording: no fixtures found under {0} "
              "(check 4).".format(FIXTURES_DIR))
        return 1
    for path in files:
        with open(path, encoding="utf-8") as fh:
            spec = json.load(fh)
        comments = spec["comments"]
        bot_login = spec["bot_login"]
        current_run_id = spec.get("current_run_id", "999")
        stand_down = board_stop_check.find_stop_request(comments, current_run_id, bot_login).stand_down
        comment_won = board_stop_check.find_stop_command_comment(comments, bot_login) is not None
        if stand_down != comment_won:
            failures += 1
            if verbose:
                print("::error::verify-stop-point-recording: {0}: find_stop_request()."
                      "stand_down={1!r} but find_stop_command_comment() is not None "
                      "= {2!r} (check 4).".format(os.path.basename(path), stand_down, comment_won))
        elif verbose:
            print("[ok] check 4: {0}: both functions agree (stand_down={1!r})".format(
                os.path.basename(path), stand_down))
    return failures


# --- Check 5: selection exclusion ---------------------------------------
STALLED_ISSUE = {
    "number": 402, "author": {"login": "someone"}, "authorAssociation": "NONE",
    "labels": [{"name": "board:stalled"}], "state": "OPEN",
    "createdAt": "2026-01-01T00:00:00Z",
}
STALLED_MARKER_BODY = (
    "**Run:** https://github.com/example/example/actions/runs/1\n\n"
    "<!-- wing-commander-board-item: "
    "{\"step\": \"stalled\", \"round\": 0, \"pr\": null, \"branch\": null, \"base_sha\": null} -->")


def _stalled_fixture():
    open_issues = [STALLED_ISSUE]
    comments_by_issue = {402: [{
        "created_at": "2026-01-02T00:00:00Z", "body": STALLED_MARKER_BODY,
        "user": {"login": BOT_LOGIN, "type": "Bot"},
    }]}
    pr_state_by_number = {}
    labeled_events_by_issue = {402: []}
    return open_issues, comments_by_issue, pr_state_by_number, labeled_events_by_issue


def check_selection_exclusion(verbose=True):
    open_issues, comments_by_issue, pr_state_by_number, labeled_events_by_issue = _stalled_fixture()
    failures = 0
    excluded, reason = board_eligibility.is_excluded(STALLED_ISSUE)
    if not (excluded and reason == "board:stalled"):
        failures += 1
        if verbose:
            print("::error::verify-stop-point-recording: is_excluded() did not exclude "
                  "the stalled fixture (got {0!r}) (check 5).".format((excluded, reason)))
    for _ in range(10):
        candidate, _multiple = board_eligibility.in_flight_candidate(
            open_issues, comments_by_issue, pr_state_by_number, BOT_LOGIN)
        if candidate is not None:
            failures += 1
            if verbose:
                print("::error::verify-stop-point-recording: in_flight_candidate() "
                      "returned the stalled issue (check 5).")
            break
    for _ in range(10):
        selected = board_eligibility.select(
            open_issues, labeled_events_by_issue, comments_by_issue, pr_state_by_number, BOT_LOGIN)
        if selected is not None:
            failures += 1
            if verbose:
                print("::error::verify-stop-point-recording: select() returned the "
                      "stalled issue (check 5).")
            break
    if not failures and verbose:
        print("[ok] check 5: the stalled fixture is excluded across ten simulated passes")
    return failures


# --- Check 6: no write on kill-switch-only/closed-issue -----------------
def check_no_write_on_stand_down(steps=None, verbose=True):
    steps = steps if steps is not None else _load_composite_steps()
    step = _record_write_step(steps)
    if step is None:
        if verbose:
            print("::error::verify-stop-point-recording: no record-write step found "
                  "(check 6).")
        return 1
    if_text = str(step.get("if") or "")
    if not re.fullmatch(r"\s*steps\.check\.outputs\.stop-cause\s*==\s*'stop-request'\s*", if_text):
        print("::error::verify-stop-point-recording: the record-write step's `if:` "
              "is {0!r} -- it must be exactly `steps.check.outputs.stop-cause == "
              "'stop-request'`, never a broader condition that would also admit "
              "\"kill-switch\"/\"closed-issue\" (check 6).".format(if_text))
        return 1
    if verbose:
        print("[ok] check 6: the record-write step's `if:` admits only stop-request")
    return 0


CHECKS = (
    ("check 1", check_record_write_present),
    ("check 2", check_provenance),
    ("check 3", check_cause_aware_messaging),
    ("check 4", check_decision_function_agreement),
    ("check 5", check_selection_exclusion),
    ("check 6", check_no_write_on_stand_down),
)


def run(verbose=True):
    failures = 0
    for _name, fn in CHECKS:
        failures += fn(verbose=verbose)
    return failures


# --- Self-test -----------------------------------------------------------
def _mutate_composite_text(pattern, replacement, count=1):
    text = _composite_text()
    mutated, n = re.subn(pattern, replacement, text, count=count)
    if n != count:
        raise AssertionError("mutation pattern {0!r} matched {1} time(s), expected {2}"
                              .format(pattern, n, count))
    return yaml.safe_load(mutated)["runs"]["steps"]


def selftest_check1():
    case = "record-write step's if: removed -> check 1 fails"
    mutated_steps = _mutate_composite_text(
        r"(id: record-stop-point\n) {6}if: steps\.check\.outputs\.stop-cause == 'stop-request'\n",
        r"\1", count=1)
    failures = check_record_write_present(steps=mutated_steps, verbose=False)
    if not failures:
        print("::error::verify-stop-point-recording self-test: {0}: NOT caught.".format(case))
        return 1
    print("note: mutation caught ({0}).".format(case))
    return 0


def selftest_check2():
    case = "board_item_marker.py invocation rewritten to a bare .github/scripts/ path -> check 2 fails"
    mutated_steps = _mutate_composite_text(
        r'\$RUNNER_TEMP/wc-pristine/scripts/board_item_marker\.py',
        r'.github/scripts/board_item_marker.py', count=1)
    failures = check_provenance(steps=mutated_steps, verbose=False)
    if not failures:
        print("::error::verify-stop-point-recording self-test: {0}: NOT caught.".format(case))
        return 1
    print("note: mutation caught ({0}).".format(case))
    return 0


def selftest_check3():
    case = "a hardcoded \"kill switch\" stand-down message -> check 3 fails"
    doc = {
        "jobs": {
            "triage": {
                "steps": [
                    {"id": "killswitch-recheck"},
                    {"name": "Act", "run": 'echo "board-loop: kill switch set -- standing down."'},
                ]
            }
        }
    }
    failures = check_cause_aware_messaging(board_loop_doc=doc, verbose=False)
    if not failures:
        print("::error::verify-stop-point-recording self-test: {0}: NOT caught.".format(case))
        return 1
    print("note: mutation caught ({0}).".format(case))
    return 0


def selftest_check4():
    case = "find_stop_command_comment() baseline forced empty -> check 4 fails"
    original = board_stop_check.find_stop_command_comment

    def _no_baseline(comments, bot_login):
        ordered = sorted(comments or [], key=lambda c: c.get("created_at") or "")
        winner = None
        for comment in ordered:
            if (comment.get("author_association") in board_stop_check.MAINTAINER_ASSOCIATIONS
                    and board_stop_check.is_stop_command(comment.get("body"))):
                winner = comment
        return winner

    board_stop_check.find_stop_command_comment = _no_baseline
    try:
        failures = check_decision_function_agreement(verbose=False)
    finally:
        board_stop_check.find_stop_command_comment = original
    if not failures:
        print("::error::verify-stop-point-recording self-test: {0}: NOT caught.".format(case))
        return 1
    print("note: mutation caught ({0}: {1} fixture(s) disagreed).".format(case, failures))
    return 0


def selftest_check5():
    case = "board:stalled label omitted from the fixture -> check 5's exclusion assertion no longer holds"
    unlabeled_issue = dict(STALLED_ISSUE)
    unlabeled_issue["labels"] = []
    excluded, _reason = board_eligibility.is_excluded(unlabeled_issue)
    if excluded:
        print("::error::verify-stop-point-recording self-test: {0}: NOT caught "
              "(still excluded with no label).".format(case))
        return 1
    print("note: mutation caught ({0}).".format(case))
    return 0


def selftest_check6():
    case = "record-write step's if: broadened to stop-cause != '' -> check 6 fails"
    mutated_steps = _mutate_composite_text(
        r"(id: record-stop-point\n {6}if: steps\.check\.outputs\.stop-cause) == 'stop-request'\n",
        r"\1 != ''\n", count=1)
    failures = check_no_write_on_stand_down(steps=mutated_steps, verbose=False)
    if not failures:
        print("::error::verify-stop-point-recording self-test: {0}: NOT caught.".format(case))
        return 1
    print("note: mutation caught ({0}).".format(case))
    return 0


SELFTESTS = (
    selftest_check1, selftest_check2, selftest_check3,
    selftest_check4, selftest_check5, selftest_check6,
)


def self_test():
    failures = 0
    for fn in SELFTESTS:
        failures += fn()
    return failures


def main():
    if "--self-test" in sys.argv:
        failures = self_test()
    else:
        failures = run()
    print("verify-stop-point-recording: {0} failure(s).".format(failures))
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
