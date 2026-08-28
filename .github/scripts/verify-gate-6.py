#!/usr/bin/env python3
"""Self-test for lint-workflows.yml's Gate 6.

Gate 6 passing against a healthy workflow fleet proves nothing: a gate that
never fires is indistinguishable from one whose detection logic is broken.
That is not hypothetical here — gate 5 exists because a verifier sat green
for weeks while checking a code path that did not ship.

So this script feeds Gate 6 synthetic workflow trees that each contain one
known defect (or one known NON-defect) and asserts the verdict, including
which file and event the error names.

Drift-proofing: the gate's source is EXTRACTED from lint-workflows.yml at
run time rather than copied here. There is no second copy to fall out of
sync — if the shipped gate changes, this runs the changed gate.

Usage: python3 .github/scripts/verify-gate-6.py
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_lint_gate_source import extract_gate_step  # noqa: E402

LINT_WORKFLOW = ".github/workflows/lint-workflows.yml"
STEP_PREFIX = "Gate 6"


def extract_gate(path=LINT_WORKFLOW):
    """Return Gate 6's python source, read out of the shipped workflow."""
    return extract_gate_step(path, STEP_PREFIX, "verify-gate-6")


# ---------------------------------------------------------------- fixtures
#
# Kept deliberately tiny and self-contained rather than mutating the real
# fleet: the real files change for unrelated reasons, and a self-test that
# breaks on every unrelated edit gets deleted rather than fixed.

AGENT_STAGE = """\
name: agent stage
on:
  workflow_call: {}
jobs:
  work:
    runs-on: ubuntu-latest
    steps:
      - uses: anthropics/claude-code-action@v1
"""

PLAIN_STAGE = """\
name: plain stage
on:
  workflow_call: {}
jobs:
  work:
    runs-on: ubuntu-latest
    steps:
      - run: echo no agent here
"""

MIDDLE = """\
name: middle
on:
  workflow_call: {}
jobs:
  inner:
    uses: ./.github/workflows/stage.yml
"""


def wrapper(on_block, if_line="", uses="./.github/workflows/stage.yml"):
    cond = f"    if: {if_line}\n" if if_line else ""
    return f"name: wrapper\non:\n{on_block}jobs:\n  call:\n{cond}    uses: {uses}\n"


PUSH_ON = "  push:\n    branches: [main]\n"
PUSH_DISPATCH_ON = "  push:\n    branches: [main]\n  workflow_dispatch: {}\n"
GOOD_IF = "${{ github.event_name == 'schedule' || github.event_name == 'workflow_dispatch' }}"

CASES = [
    # name, files, expect_fail, must_mention
    ("healthy: dispatch-only wrapper onto an agent stage",
     {"wrapper.yml": wrapper("  workflow_dispatch: {}\n"), "stage.yml": AGENT_STAGE},
     False, ()),

    ("the 028 defect: push reaches an agent stage with no event guard",
     {"wrapper.yml": wrapper(PUSH_ON), "stage.yml": AGENT_STAGE},
     True, ("wrapper.yml", "'call'", "push")),

    ("the 028 fix: push declared but the job admits only supported events",
     {"wrapper.yml": wrapper(PUSH_DISPATCH_ON, GOOD_IF), "stage.yml": AGENT_STAGE},
     False, ()),

    ("forward-looking: an unsupported event that is not push",
     {"wrapper.yml": wrapper("  create: {}\n"), "stage.yml": AGENT_STAGE},
     True, ("wrapper.yml", "create")),

    ("no false positive: push onto a stage with no agent step",
     {"wrapper.yml": wrapper(PUSH_ON), "stage.yml": PLAIN_STAGE},
     False, ()),

    ("exclusion form: `!= 'push'` keeps push out",
     {"wrapper.yml": wrapper(PUSH_DISPATCH_ON, "${{ github.event_name != 'push' }}"),
      "stage.yml": AGENT_STAGE},
     False, ()),

    ("conservative: an if: with no event_name clause does not excuse push",
     {"wrapper.yml": wrapper(PUSH_ON, "${{ vars.PAUSED != 'true' }}"),
      "stage.yml": AGENT_STAGE},
     True, ("wrapper.yml", "push")),

    ("nesting: the agent is one `uses:` hop deeper",
     {"wrapper.yml": wrapper(PUSH_ON, uses="./.github/workflows/middle.yml"),
      "middle.yml": MIDDLE, "stage.yml": AGENT_STAGE},
     True, ("wrapper.yml", "push")),

    ("nesting, no defect: workflow_call is not itself an unsupported event",
     {"wrapper.yml": wrapper("  workflow_dispatch: {}\n",
                             uses="./.github/workflows/middle.yml"),
      "middle.yml": MIDDLE, "stage.yml": AGENT_STAGE},
     False, ()),

    ("a `.yaml` stage is resolved, not silently skipped",
     {"wrapper.yml": wrapper(PUSH_ON, uses="./.github/workflows/stage.yaml"),
      "stage.yaml": AGENT_STAGE},
     True, ("wrapper.yml", "push")),

    ("an unresolvable local callee is reported, not silently skipped",
     {"wrapper.yml": wrapper(PUSH_ON, uses="./.github/workflows/typo.yml"),
      "stage.yml": AGENT_STAGE},
     True, ("does not exist",)),
]


def main():
    if not os.path.isfile(LINT_WORKFLOW):
        sys.exit(f"::error::run this from the repository root; {LINT_WORKFLOW} not found.")

    gate_src = extract_gate()
    root = tempfile.mkdtemp(prefix="verify_gate6_")
    gate_path = os.path.join(root, "gate6.py")
    io.open(gate_path, "w", encoding="utf-8").write(gate_src)

    failures = []
    try:
        for name, files, expect_fail, must_mention in CASES:
            case_dir = tempfile.mkdtemp(prefix="case_", dir=root)
            wf_dir = os.path.join(case_dir, ".github", "workflows")
            os.makedirs(wf_dir)
            for fname, body in files.items():
                io.open(os.path.join(wf_dir, fname), "w", encoding="utf-8").write(body)

            proc = subprocess.run([sys.executable, gate_path], cwd=case_dir,
                                  capture_output=True, text=True,
                                  encoding="utf-8", errors="replace")
            out = (proc.stdout or "") + (proc.stderr or "")
            fired = proc.returncode != 0

            problems = []
            if fired != expect_fail:
                problems.append(
                    f"expected the gate to {'FAIL' if expect_fail else 'PASS'}, "
                    f"it {'FAILED' if fired else 'PASSED'}")
            for token in must_mention:
                if token not in out:
                    problems.append(f"error text never mentions {token!r}")

            if problems:
                failures.append((name, problems, out.strip()))
                print(f"FAIL  {name}")
                for p in problems:
                    print(f"        - {p}")
                for line in out.strip().splitlines():
                    print(f"        | {line}")
            else:
                print(f"ok    {name}")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    print()
    if failures:
        print(f"::error file={LINT_WORKFLOW}::Gate 6 self-test: "
              f"{len(failures)} of {len(CASES)} scenarios behaved wrongly. Gate 6's "
              f"detection logic does not do what its name claims, so a green Gate 6 "
              f"on the real fleet means nothing.")
        return 1
    print(f"Gate 6 self-test: all {len(CASES)} scenarios behaved as expected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
