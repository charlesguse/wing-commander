#!/usr/bin/env python3
"""Gate — board_prove.py's actions_only() resolves every documented branch
correctly (specs/057-autonomous-board-loop, contracts/prove-step.md,
research.md D15).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from board_prove import actions_only, redrive_target  # noqa: E402

CASES = [
    (["docs/setup.md", "specs/999-example-feature/spec.md"], False),
    ([".github/scripts/verify-board-triage.py"], False),
    ([".github/workflows/board-loop.yml"], True),
    ([".github/scripts/board_triage.py"], True),
    (["docs/setup.md", ".github/workflows/board-loop.yml"], True),
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

    print("verify-board-prove: {0} failure(s).".format(failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(run())
