#!/usr/bin/env python3
"""Gate — board_prove.py's actions_only() resolves every documented branch
correctly (specs/057-autonomous-board-loop, contracts/prove-step.md,
research.md D15), and specs/060-self-redrive-concurrency's directed-proof-run
mechanism (directed_stage(), joins_directed_group(),
directed_proof_group_busy(), scan_job_uses_graph()) resolves every
documented branch correctly too (FR-020/FR-021).
"""
import json
import os
import sys
import tempfile

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from board_prove import (  # noqa: E402
    actions_only, aimable_jobs, directed_proof_group_busy, directed_stage,
    is_safe_redrive_target, joins_directed_group, redrive_target,
    scan_dispatchable_and_uses_graph, scan_job_uses_graph,
)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REPO_WORKFLOWS_DIR = os.path.join(REPO_ROOT, ".github", "workflows")
REPO_BOARD_LOOP = os.path.join(REPO_WORKFLOWS_DIR, "board-loop.yml")

CASES = [
    (["docs/setup.md", "specs/999-example-feature/spec.md"], False),
    ([".github/scripts/verify-board-triage.py"], False),
    ([".github/workflows/board-loop.yml"], True),
    ([".github/scripts/board_triage.py"], True),
    (["docs/setup.md", ".github/workflows/board-loop.yml"], True),
]

# is_safe_redrive_target(): a candidate missing attempt-token correlation
# support, or carrying another required input the composite has no way to
# supply, must never be offered to redrive_target() -- the composite could
# dispatch it but never observe the result, or gh would reject the
# dispatch outright.
SAFE_TARGET_CASES = [
    ("run-name: 'release ${{ inputs.attempt-token }}'\non:\n  workflow_dispatch:\n"
     "    inputs:\n      attempt-token:\n        required: true\n",
     {"attempt-token": {"required": True}}, True),
    ("name: plan\non:\n  workflow_dispatch: {}\n", {}, False),
    ("run-name: 'release ${{ inputs.attempt-token }}'\non:\n  workflow_dispatch:\n"
     "    inputs:\n      attempt-token:\n        required: true\n"
     "      version:\n        required: true\n",
     {"attempt-token": {"required": True}, "version": {"required": True}}, False),
    ("run-name: 'release ${{ inputs.attempt-token }}'\non:\n  workflow_dispatch:\n"
     "    inputs:\n      attempt-token:\n        required: true\n"
     "      breaking:\n        required: false\n",
     {"attempt-token": {"required": True}, "breaking": {"required": False}}, True),
]

# contracts/prove-step.md "Re-drive": which workflow proves the change.
# The wrapper/stage split is this repository's own shape -- a published
# stage carries workflow_call only, so only its wrapper can be dispatched.
DISPATCHABLE = [
    ".github/workflows/board-loop.yml",
    ".github/workflows/wing-commander-watchdog-test.yml",
]
USES_GRAPH = {
    ".github/workflows/board-loop.yml": [
        ".github/actions/wing-commander-dispatch-and-wait/action.yml",
    ],
    ".github/workflows/wing-commander-watchdog-test.yml": [
        ".github/workflows/watchdog.yml",
    ],
}

REDRIVE_CASES = [
    # 1. a changed workflow that dispatches itself is its own wrapper
    ([".github/workflows/board-loop.yml"], "board-loop.yml"),
    # 2. a workflow_call-only stage is reached through its wrapper
    ([".github/workflows/watchdog.yml"], "wing-commander-watchdog-test.yml"),
    # 2. a composite is reached through the workflow that uses it
    ([".github/actions/wing-commander-dispatch-and-wait/action.yml"],
     "board-loop.yml"),
    # 3. nothing dispatchable reaches it -- say so, never dispatch a
    #    workflow that would prove something else
    ([".github/actions/wing-commander-unreferenced/action.yml"], None),
]

# specs/060-self-redrive-concurrency research.md D1/D2: directed_stage()'s
# own job-uses-graph -- one aimable job per changed helper, plus a tied
# helper (board_item_marker.py) both review and readiness reference.
JOB_USES_GRAPH = {
    "triage": ["board_triage.py"],
    "review": ["board_reviewer.py", "board_item_marker.py"],
    "readiness": ["board_readiness.py", "board_item_marker.py"],
    "prove": ["board_prove.py"],
}

DIRECTED_STAGE_CASES = [
    (["board_triage.py"], "triage"),
    (["board_reviewer.py"], "review"),
    (["board_readiness.py"], "readiness"),
    (["board_prove.py"], "prove"),
    ([".github/scripts/board_unrelated_helper.py"], None),
    # tie-break: board_item_marker.py is referenced by both review and
    # readiness -- pipeline order, latest-stage-wins, so readiness wins.
    (["board_item_marker.py"], "readiness"),
]

# research.md D4/FR-001: self-target (board-loop.yml, an aimable job) is
# true by construction; an external target's own concurrency: group is read
# off the tree and compared against both wing-commander-board-loop* groups.
JOINS_DIRECTED_GROUP_CASES = [
    (REPO_BOARD_LOOP, "prove", True),
    (REPO_BOARD_LOOP, "readiness", True),
]

DIRECTED_PROOF_GROUP_BUSY_CASES = [
    ("[]", False),
    (json.dumps([{"databaseId": 1, "displayTitle": "board-loop [directed:prove]", "status": "in_progress"}]), True),
    (json.dumps([{"databaseId": 1, "displayTitle": "board-loop [directed:prove]", "status": "completed"}]), False),
    (json.dumps([{"databaseId": 1, "displayTitle": "board-loop", "status": "in_progress"}]), False),
]


def run():
    failures = 0
    for changed_paths, expected in CASES:
        got, reason = actions_only(changed_paths)
        if got != expected:
            failures += 1
            print("::error::verify-board-prove: {0}: expected actions_only={1}, "
                  "got {2} ({3}).".format(changed_paths, expected, got, reason))
        else:
            print("[ok] {0}: actions_only={1} ({2})".format(changed_paths, got, reason))

    for changed_paths, expected in REDRIVE_CASES:
        got, reason = redrive_target(changed_paths, DISPATCHABLE, USES_GRAPH)
        if got != expected:
            failures += 1
            print("::error::verify-board-prove: {0}: expected redrive target "
                  "{1}, got {2} ({3}).".format(changed_paths, expected, got, reason))
        else:
            print("[ok] {0}: redrive={1} ({2})".format(changed_paths, got, reason))

    for workflow_text, inputs, expected in SAFE_TARGET_CASES:
        got = is_safe_redrive_target(workflow_text, inputs)
        if got != expected:
            failures += 1
            print("::error::verify-board-prove: is_safe_redrive_target({0!r}, {1!r}): "
                  "expected {2}, got {3}.".format(workflow_text, inputs, expected, got))
        else:
            print("[ok] is_safe_redrive_target(...): {0}".format(got))

    for changed_paths, expected in DIRECTED_STAGE_CASES:
        got = directed_stage(changed_paths, JOB_USES_GRAPH, aimable_jobs)
        if got != expected:
            failures += 1
            print("::error::verify-board-prove: directed_stage({0}): expected "
                  "{1}, got {2}.".format(changed_paths, expected, got))
        else:
            print("[ok] directed_stage({0}) = {1}".format(changed_paths, got))

    for target_workflow, target_job, expected in JOINS_DIRECTED_GROUP_CASES:
        got = joins_directed_group(target_workflow, target_job, aimable_jobs)
        if got != expected:
            failures += 1
            print("::error::verify-board-prove: joins_directed_group({0}, {1}): "
                  "expected {2}, got {3}.".format(target_workflow, target_job, expected, got))
        else:
            print("[ok] joins_directed_group({0}, {1}) = {2}".format(target_workflow, target_job, got))

    # External-target cases (FR-004/FR-001): a workflow sharing this
    # repository's own board-loop group must read as joining it (False);
    # one with a genuinely distinct group must read as not joining (True).
    # release.yml is a real, checked-in workflow with its own distinct
    # group (wing-commander-release) -- an integration case, not only a
    # synthetic fixture, same discipline as the real-tree check below.
    release_yml = os.path.join(REPO_WORKFLOWS_DIR, "release.yml")
    got = joins_directed_group(release_yml, "release", aimable_jobs)
    if got is not True:
        failures += 1
        print("::error::verify-board-prove: joins_directed_group(release.yml, ...): "
              "expected True (distinct group), got {0}.".format(got))
    else:
        print("[ok] joins_directed_group(release.yml, ...) = True (distinct group)")

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False, encoding="utf-8") as fh:
        fh.write("on: workflow_dispatch\nconcurrency:\n  group: wing-commander-board-loop\n"
                  "jobs:\n  x:\n    runs-on: ubuntu-latest\n    steps: []\n")
        shared_group_path = fh.name
    try:
        got = joins_directed_group(shared_group_path, "x", aimable_jobs)
        if got is not False:
            failures += 1
            print("::error::verify-board-prove: joins_directed_group(shared group fixture): "
                  "expected False, got {0}.".format(got))
        else:
            print("[ok] joins_directed_group(shared group fixture) = False")
    finally:
        os.unlink(shared_group_path)

    for run_list_json, expected in DIRECTED_PROOF_GROUP_BUSY_CASES:
        got = directed_proof_group_busy(run_list_json)
        if got != expected:
            failures += 1
            print("::error::verify-board-prove: directed_proof_group_busy({0}): "
                  "expected {1}, got {2}.".format(run_list_json, expected, got))
        else:
            print("[ok] directed_proof_group_busy({0}) = {1}".format(run_list_json, got))

    # Integration check, not just fixtures: the synthetic DISPATCHABLE/
    # SAFE_TARGET_CASES above can all pass while scan_dispatchable_and_uses_graph()
    # filters every REAL workflow in this repository out to an empty set
    # (this is exactly how the redrive mechanism went dead for every
    # workflow, including board-loop.yml itself, without failing CI --
    # board-loop.yml lacked the run-name/attempt-token wiring
    # is_safe_redrive_target() requires). board-loop.yml is its own
    # documented redrive target (REDRIVE_CASES case 1 above); assert it
    # actually is one on the checked-out tree, not only in a fixture.
    real_dispatchable, _real_uses_graph = scan_dispatchable_and_uses_graph(REPO_WORKFLOWS_DIR)
    real_dispatchable_basenames = {p.rsplit("/", 1)[-1] for p in real_dispatchable}
    if "board-loop.yml" not in real_dispatchable_basenames:
        failures += 1
        print("::error::verify-board-prove: board-loop.yml is not in the real "
              "repository's dispatchable set ({0}) -- the redrive/prove "
              "mechanism cannot re-drive itself, and a merge that changes only "
              "board-loop.yml's own logic can never be proven.".format(sorted(real_dispatchable_basenames)))
    else:
        print("[ok] board-loop.yml is a real, safe redrive target on the checked-out tree")

    # research.md D4: "a future edit narrowing or removing the split fails
    # loudly rather than silently reintroducing the deadlock" -- read the
    # real, checked-out board-loop.yml's own per-job concurrency.group:
    # expressions and assert the directed pair's literally differs from
    # every ordinary job's.
    with open(REPO_BOARD_LOOP, encoding="utf-8") as fh:
        real_board_loop = yaml.safe_load(fh.read())
    real_jobs = real_board_loop.get("jobs") or {}
    directed_groups = {
        job: (real_jobs.get(job) or {}).get("concurrency", {}).get("group")
        for job in ("prove-gate", "prove")
    }
    ordinary_groups = {
        job: (real_jobs.get(job) or {}).get("concurrency", {}).get("group")
        for job in ("select", "triage", "route", "fix", "review", "readiness")
    }
    for job, group in directed_groups.items():
        if not group:
            failures += 1
            print("::error::verify-board-prove: {0}'s own concurrency.group: "
                  "is missing on the checked-out tree.".format(job))
            continue
        clashes = [oj for oj, og in ordinary_groups.items() if og == group]
        if clashes:
            failures += 1
            print("::error::verify-board-prove: {0}'s own concurrency.group: "
                  "expression is byte-identical to {1}'s -- the directed/"
                  "ordinary split (research.md D3) has been narrowed or "
                  "removed.".format(job, clashes))
        else:
            print("[ok] {0}'s own concurrency.group: expression differs from "
                  "every ordinary job's on the checked-out tree".format(job))

    print("verify-board-prove: {0} failure(s).".format(failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(run())
