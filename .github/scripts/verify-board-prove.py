#!/usr/bin/env python3
"""Gate — board_prove.py's actions_only() resolves every documented branch
correctly (specs/057-autonomous-board-loop, contracts/prove-step.md,
research.md D15).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from board_prove import (  # noqa: E402
    actions_only, is_safe_redrive_target, redrive_target,
    scan_dispatchable_and_uses_graph,
)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REPO_WORKFLOWS_DIR = os.path.join(REPO_ROOT, ".github", "workflows")

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

    print("verify-board-prove: {0} failure(s).".format(failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(run())
