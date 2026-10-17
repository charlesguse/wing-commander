#!/usr/bin/env python3
"""Gate — the board loop's self-merge decision and its `merge` job stay inside
the bounds Principle X authorizes (specs/115-board-loop-self-merge,
contracts/board-merge.md, FR-015).

WHY THIS EXISTS
---------------
board_merge.py decides whether a PR may be squash-merged without the owner.
Every merge-blocking condition and every refusal branch must have a checked-in
fixture that proves it blocks (or classifies), so a condition dropped from the
evaluator cannot look identical to a working one. The workflow half is
structural: the `merge` job may call `gh pr merge` only pinned to the head SHA
it evaluated, never with `--admin`, `--auto`, an approval, or a second merge
method, only behind both switches, and without dispatching proof runs itself.

Fixtures live in .github/scripts/fixtures/board-merge/, named
`<class>-<condition>[-variant].json` (a case where that condition is the
first unmet one), `<class>-pass[-variant].json` (every condition holds) and
`refusal-<class>.json` (gh stderr plus the expected refusal class).

    python3 .github/scripts/verify-board-merge.py
"""
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import board_merge  # noqa: E402
from board_readiness import CONDITIONS as READINESS_CONDITIONS  # noqa: E402

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
FIXTURES_DIR = os.path.join(SCRIPTS_DIR, "fixtures", "board-merge")
BOARD_LOOP = ".github/workflows/board-loop.yml"
AUTO_UPDATE = ".github/workflows/auto-update-spec-kit.yml"
WORKFLOWS_DIR = ".github/workflows"

failures = 0


def fail(message):
    global failures
    failures += 1
    print("::error::verify-board-merge: {0}".format(message))


def ok(message):
    print("[ok] {0}".format(message))


def _load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def check_decision_fixtures():
    for klass, names in (("fix", board_merge.CONDITIONS_FIX), ("bump", board_merge.CONDITIONS_BUMP)):
        passes = sorted(glob.glob(os.path.join(FIXTURES_DIR, "{0}-pass*.json".format(klass))))
        if not passes:
            fail("no all-pass fixture for class {0}".format(klass))
        cases = [(path, None) for path in passes]
        for name in names:
            found = sorted(glob.glob(os.path.join(FIXTURES_DIR, "{0}-{1}*.json".format(klass, name))))
            if not found:
                fail("condition {0} of class {1} has no fixture".format(name, klass))
            cases += [(path, name) for path in found]
        for path, blocked_by in cases:
            spec = _load(path)
            got = board_merge.decide(spec["inputs"])
            want = spec["expect"]
            label = os.path.basename(path)
            if (got["may_merge"] != want["may_merge"] or got["unmet_reason"] != want["unmet_reason"]
                    or got["unmet_reason"] != blocked_by):
                fail("{0}: expected {1!r} (named by its file), got may_merge={2} unmet_reason={3!r}".format(
                    label, want, got["may_merge"], got["unmet_reason"]))
            elif list(got["conditions"]) != list(names):
                fail("{0}: decision lists conditions {1}, expected {2}".format(
                    label, list(got["conditions"]), list(names)))
            else:
                ok("{0}: may_merge={1} unmet_reason={2!r}".format(label, got["may_merge"], got["unmet_reason"]))


def check_refusal_fixtures():
    for name in board_merge.REFUSAL_CLASSES:
        path = os.path.join(FIXTURES_DIR, "refusal-{0}.json".format(name))
        if not os.path.isfile(path):
            fail("refusal class {0} has no fixture".format(name))
            continue
        spec = _load(path)
        got = board_merge.classify_refusal(spec["stderr"])
        if got != name or spec["expect_class"] != name:
            fail("refusal-{0}.json classified as {1!r}".format(name, got))
        else:
            ok("refusal-{0}.json classifies as {0}".format(name))


def job_block(lines, job):
    """The lines of top-level job `job` (two-space indent) up to the next job."""
    start = None
    for i, line in enumerate(lines):
        if line == "  {0}:".format(job):
            start = i
        elif start is not None and re.fullmatch(r"  [A-Za-z0-9_-]+:", line):
            return lines[start:i]
    return lines[start:] if start is not None else None


def _run_blocks_text(lines):
    return "\n".join(line for line in lines if not line.lstrip().startswith("#"))


def check_board_loop():
    if not os.path.isfile(BOARD_LOOP):
        fail("{0} does not exist; run from the repository root".format(BOARD_LOOP))
        return
    with open(BOARD_LOOP, encoding="utf-8") as fh:
        text = fh.read()
    lines = text.splitlines()
    merge_job = job_block(lines, "merge")
    if merge_job is None:
        fail("{0} has no `merge` job".format(BOARD_LOOP))
        return
    code = _run_blocks_text(lines)
    merge_code = _run_blocks_text(merge_job)

    for pattern, label in ((r"--admin\b", "--admin"), (r"--auto\b", "--auto"),
                           (r"gh\s+pr\s+review\b[^\n]*--approve", "gh pr review --approve"),
                           (r"event=APPROVE\b", "event=APPROVE")):
        if re.search(pattern, code):
            fail("{0} contains {1}".format(BOARD_LOOP, label))
    merge_calls = re.findall(r"gh\s+pr\s+merge\b[^\n]*(?:\\\n[^\n]*)*", merge_code)
    if not merge_calls:
        fail("the merge job never calls `gh pr merge`")
    for call in merge_calls:
        if "--match-head-commit" not in call:
            fail("a `gh pr merge` call without --match-head-commit: {0}".format(call.splitlines()[0]))
        if "--squash" not in call or re.search(r"--(merge|rebase)\b", call):
            fail("a `gh pr merge` call that is not --squash only: {0}".format(call.splitlines()[0]))
    outside = [line for line in lines if line not in merge_job and re.search(r"gh\s+pr\s+merge\b", line)
               and not line.lstrip().startswith("#")]
    if outside:
        fail("`gh pr merge` outside the merge job: {0}".format(outside[0].strip()))

    condition = " ".join(line.strip() for line in merge_job[1:12])
    if "WING_COMMANDER_BOARD_AUTO_MERGE" not in condition or "WING_COMMANDER_BOARD_LOOP_PAUSED" not in condition:
        fail("the merge job's `if:` must carry both WING_COMMANDER_BOARD_AUTO_MERGE and "
             "WING_COMMANDER_BOARD_LOOP_PAUSED")
    elif not re.search(r"WING_COMMANDER_BOARD_AUTO_MERGE\s*==\s*'true'", condition):
        fail("the merge job runs unless the switch is exactly 'true' -- it must be off by default")
    else:
        ok("merge job: pinned --squash merge, no --admin/--auto/approve, both switches in its `if:`")

    if "Awaiting a human merge" not in text:
        fail("the switch-off readiness text 'Awaiting a human merge' is gone (SC-006)")
    else:
        ok("switch-off readiness text unchanged")

    if re.search(r"gh\s+workflow\s+run\b", merge_code):
        fail("the merge job dispatches a run itself; proof comes only from prove-gate (research D8)")
    else:
        ok("merge job dispatches no run")
    # A merged item reaches prove-gate through the PR's closed event, which
    # only an App-token merge starts (a GITHUB_TOKEN one starts no workflow).
    merge_step = next((block for block in re.split(r"\n      - name: ", "\n".join(merge_job))
                       if "gh pr merge" in block), "")
    if "GH_TOKEN: ${{ env.WC_BOT_TOKEN }}" not in merge_step:
        fail("the merge step must run with the App token (env.WC_BOT_TOKEN) so the closed event "
             "reaches prove-gate")
    prove_gate = job_block(lines, "prove-gate")
    if prove_gate is None or "github.event_name == 'pull_request'" not in "\n".join(prove_gate):
        fail("prove-gate no longer runs on the pull_request closed event a merge produces")
    else:
        ok("merge runs as the App and prove-gate takes its closed event")

    # The decision logic has one home: board_merge.py (CLAUDE.md). `switch_on`
    # and `review_converged` also name payload keys the job passes in.
    names = ((set(board_merge.CONDITIONS_FIX) | set(board_merge.CONDITIONS_BUMP))
             - set(READINESS_CONDITIONS) - {"switch_on", "review_converged"})
    for path in sorted(glob.glob(os.path.join(WORKFLOWS_DIR, "*.yml"))):
        with open(path, encoding="utf-8") as fh:
            body = _run_blocks_text(fh.read().splitlines())
        for name in sorted(names):
            if name in body:
                fail("{0} carries the merge condition name {1}; it lives in board_merge.py only".format(path, name))
        if "not mergeable" in body or "approving review" in body:
            fail("{0} carries a refusal regex; classify_refusal() is its one home".format(path))


def check_auto_update():
    if not os.path.isfile(AUTO_UPDATE):
        fail("{0} does not exist".format(AUTO_UPDATE))
        return
    with open(AUTO_UPDATE, encoding="utf-8") as fh:
        body = _run_blocks_text(fh.read().splitlines())
    if re.search(r"gh\s+pr\s+merge\b", body):
        fail("{0} merges a PR; the stage never merges its own (FR-013)".format(AUTO_UPDATE))
    if "--bump-verification" not in body:
        fail("{0} does not post the wc-bump-verification record (board_item_marker.py "
             "--bump-verification)".format(AUTO_UPDATE))
    if not failures:
        ok("auto-update stage posts the verification record and never merges")


def main():
    if not os.path.isdir(FIXTURES_DIR):
        fail("fixtures directory {0} does not exist".format(FIXTURES_DIR))
    else:
        check_decision_fixtures()
        check_refusal_fixtures()
    check_board_loop()
    check_auto_update()
    print("verify-board-merge: {0} failure(s).".format(failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
