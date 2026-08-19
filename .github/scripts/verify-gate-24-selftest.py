#!/usr/bin/env python3
"""Self-test for lint-workflows.yml's Gate 24 (verify-gate-24.py).

Gate 24 runs against a fleet that is compliant the moment it lands and
should stay that way forever — so, exactly as with Gates 6/7/12/23, a green
Gate 24 says nothing about whether its detection works. Worse here than
elsewhere: this gate is deliberately narrow (three clauses, each excluding a
whole family of legitimate hard exits), so the likely way it breaks is not
"crashes" but "quietly stops matching anything". This feeds the SHIPPED
script synthetic workflows — the five-defect shape, and one fixture per
clause that must NOT fire — and asserts both directions.

Usage: python3 .github/scripts/verify-gate-24-selftest.py
"""
import os
import shutil
import subprocess
import sys
import tempfile

GATE_SCRIPT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "verify-gate-24.py"))

# The shape of all five PR #221 defects, reduced: a tolerated agent step, a
# verdict derived from it, a fail-loud guard that hard-exits on that verdict,
# and below it the fallback the tolerance existed for.
DEFECT = """\
name: stage
on:
  workflow_call:
jobs:
  run:
    runs-on: ubuntu-latest
    steps:
      - id: agent
        continue-on-error: true
        uses: anthropics/claude-code-action@v1
      - id: agent-verdict
        if: always() && steps.agent.outcome != 'skipped'
        uses: ./.github/actions/wing-commander-agent-verdict
      - name: Fail loud on non-healthy agent verdict
        if: always() && steps.agent.outcome != 'skipped' && steps.agent-verdict.outputs.verdict != 'healthy'
        run: |
          echo "::error::agent step rejected"
          exit 1
      - name: Resolve completion summary (with fallback)
        id: summary
        run: |
          if [ "${{ steps.agent-verdict.outputs.verdict }}" != "healthy" ]; then
            echo "automated summary unavailable" > summary.md
          fi
      - name: Delete pipeline branches
        run: git push origin --delete spec/x
"""


def replace_once(text, old, new):
    assert old in text, f"fixture setup error: {old!r} not found"
    return text.replace(old, new, 1)


GUARD_IF = ("        if: always() && steps.agent.outcome != 'skipped' && "
            "steps.agent-verdict.outputs.verdict != 'healthy'\n")

# Fix 1 — the one applied at all five real sites.
FIXED_WITH_CONTINUE_ON_ERROR = replace_once(
    DEFECT, GUARD_IF, GUARD_IF + "        continue-on-error: true\n")

# Fix 3 — the degradation path survives the red step on its own.
FIXED_WITH_NOT_CANCELLED = replace_once(
    DEFECT,
    "      - name: Resolve completion summary (with fallback)\n"
    "        id: summary\n",
    "      - name: Resolve completion summary (with fallback)\n"
    "        id: summary\n        if: '!cancelled()'\n")

# Fix 2 — nothing left below the guard to strand.
FIXED_BY_DEFERRING_THE_GUARD = """\
name: stage
on:
  workflow_call:
jobs:
  run:
    runs-on: ubuntu-latest
    steps:
      - id: agent
        continue-on-error: true
        uses: anthropics/claude-code-action@v1
      - id: agent-verdict
        if: always() && steps.agent.outcome != 'skipped'
        uses: ./.github/actions/wing-commander-agent-verdict
      - name: Resolve completion summary (with fallback)
        id: summary
        run: |
          if [ "${{ steps.agent-verdict.outputs.verdict }}" != "healthy" ]; then
            echo "automated summary unavailable" > summary.md
          fi
      - name: Fail loud on non-healthy agent verdict
        if: always() && steps.agent.outcome != 'skipped' && steps.agent-verdict.outputs.verdict != 'healthy'
        run: |
          echo "::error::agent step rejected"
          exit 1
"""

# Clause (b): `Fail on agent API error` fires on the tolerated signal's
# SUCCESS, for an independent reason. Stranding what is below it is the
# point of the step, not a defect. This is the real shape in clarify.yml and
# pr-conversation.yml, and the fixture that would go red first if clause (b)
# were dropped.
FIRES_ON_HEALTHY_NOT_ON_FAILURE = replace_once(
    DEFECT,
    "      - name: Fail loud on non-healthy agent verdict\n" + GUARD_IF,
    "      - name: Fail on agent API error\n"
    "        if: steps.agent-verdict.outputs.verdict == 'healthy'\n")

# Clause (b): a bare skip guard is not a failure test. Gate 23 REQUIRES
# `steps.<agent>.outcome != 'skipped'` on every fail-loud step, so reading it
# as "fires on a tolerated failure" would arm this gate at all 19 sites.
ONLY_A_SKIP_GUARD = replace_once(
    DEFECT, GUARD_IF,
    "        if: always() && steps.agent.outcome != 'skipped'\n")

# Clause (c): the stranded step reads nothing the guard fired on. A failed
# agent SHOULD stop the label flip — tasks.yml's real shape.
STRANDS_ONLY_UNRELATED_WORK = replace_once(
    DEFECT,
    "      - name: Resolve completion summary (with fallback)\n"
    "        id: summary\n"
    "        run: |\n"
    "          if [ \"${{ steps.agent-verdict.outputs.verdict }}\" != "
    "\"healthy\" ]; then\n"
    "            echo \"automated summary unavailable\" > summary.md\n"
    "          fi\n",
    "      - name: Flip stage label\n"
    "        run: gh issue edit 1 --add-label stage:review\n")

# Clause (c): mutually exclusive with the guard — on the run that fires it,
# this step was never going to execute anyway.
STRANDED_STEP_IS_MOOT = replace_once(
    DEFECT,
    "      - name: Resolve completion summary (with fallback)\n"
    "        id: summary\n",
    "      - name: Report over-budget agent run\n"
    "        id: summary\n"
    "        if: steps.agent-verdict.outputs.verdict == 'healthy'\n")

# The shape three of the five defects actually had: the degradation path
# reaches the verdict through `env:`, and carries no `if:` at all. A checker
# that only parsed conditions would miss it.
READS_THE_SIGNAL_ONLY_THROUGH_ENV = replace_once(
    DEFECT,
    "      - name: Resolve completion summary (with fallback)\n"
    "        id: summary\n"
    "        run: |\n"
    "          if [ \"${{ steps.agent-verdict.outputs.verdict }}\" != "
    "\"healthy\" ]; then\n"
    "            echo \"automated summary unavailable\" > summary.md\n"
    "          fi\n",
    "      - name: Read back decision\n"
    "        id: readback\n"
    "        env:\n"
    "          DECIDE_OUTCOME: ${{ steps.agent-verdict.outputs.verdict }}\n"
    "        run: |\n"
    "          if [ \"$DECIDE_OUTCOME\" != \"healthy\" ]; then\n"
    "            echo 'outcome=needs-migration' >> \"$GITHUB_OUTPUT\"\n"
    "          fi\n")

# Nothing was declared survivable, so no guard here can revoke a tolerance.
# An ordinary setup step that exits 1 strands everything below it, correctly.
NO_TOLERANCE_DECLARED = replace_once(
    DEFECT, "        continue-on-error: true\n", "")

UNPARSEABLE_ALONGSIDE_A_GOOD_SITE = {
    "stage.yml": FIXED_WITH_CONTINUE_ON_ERROR,
    "broken.yml": "name: broken\njobs:\n   - [unclosed\n  bad: : :\n",
}

CASES = [
    ("the five-defect shape fails, naming the guard and the degradation "
     "path it strands",
     DEFECT, True,
     ("Fail loud on non-healthy agent verdict",
      "Resolve completion summary (with fallback)",
      "steps.agent-verdict")),
    ("the same shape with the degradation path reached only through env: "
     "still fails — three of the five real defects looked like this",
     READS_THE_SIGNAL_ONLY_THROUGH_ENV, True, ("Read back decision",)),
    ("fix 1 (continue-on-error: true on the guard) passes",
     FIXED_WITH_CONTINUE_ON_ERROR, False, ()),
    ("fix 2 (defer the guard to the end of the job) passes",
     FIXED_BY_DEFERRING_THE_GUARD, False, ()),
    ("fix 3 (!cancelled() on the degradation path) passes",
     FIXED_WITH_NOT_CANCELLED, False, ()),
    ("clause (b): a guard firing on verdict == 'healthy' passes — it fires "
     "on the signal's success, for an independent reason",
     FIRES_ON_HEALTHY_NOT_ON_FAILURE, False, ()),
    ("clause (b): a bare outcome != 'skipped' skip guard does not arm the "
     "gate — Gate 23 requires that guard at all 19 sites",
     ONLY_A_SKIP_GUARD, False, ()),
    ("clause (c): stranding work that does not read the signal passes — a "
     "failed agent should stop the label flip",
     STRANDS_ONLY_UNRELATED_WORK, False, ()),
    ("clause (c): a stranded step gated on the guard's condition NOT "
     "holding passes — it was never going to run on that path",
     STRANDED_STEP_IS_MOOT, False, ()),
    ("a job that declared no tolerance passes — an ordinary step exiting 1 "
     "strands everything below it, correctly",
     NO_TOLERANCE_DECLARED, False, ()),
    ("a workflow that does not parse as YAML fails the gate rather than "
     "dropping out of coverage",
     UNPARSEABLE_ALONGSIDE_A_GOOD_SITE, True,
     ("could not parse", "silently dropping")),
]


def run_case(workflow_text, expect_fail, must_mention):
    root = tempfile.mkdtemp(prefix="verify_gate24_case_")
    try:
        wf_dir = os.path.join(root, ".github", "workflows")
        os.makedirs(wf_dir)
        files = (workflow_text if isinstance(workflow_text, dict)
                 else {"stage.yml": workflow_text})
        for filename, text in files.items():
            with open(os.path.join(wf_dir, filename), "w",
                      encoding="utf-8") as handle:
                handle.write(text)
        proc = subprocess.run([sys.executable, GATE_SCRIPT], cwd=root,
                              capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
        out = (proc.stdout or "") + (proc.stderr or "")
        fired = proc.returncode != 0
        problems = []
        if fired != expect_fail:
            problems.append(f"expected the gate to "
                            f"{'FAIL' if expect_fail else 'PASS'}, it "
                            f"{'FAILED' if fired else 'PASSED'}")
        for token in must_mention:
            if token not in out:
                problems.append(f"error text never mentions {token!r}")
        return problems, out
    finally:
        shutil.rmtree(root, ignore_errors=True)


def main():
    if not os.path.isfile(GATE_SCRIPT):
        sys.exit(f"::error::{GATE_SCRIPT} not found — run this from the "
                 f"repository root.")

    failed = 0
    for name, workflow_text, expect_fail, must_mention in CASES:
        problems, out = run_case(workflow_text, expect_fail, must_mention)
        if problems:
            failed += 1
            print(f"FAIL  {name}")
            for problem in problems:
                print(f"        - {problem}")
            for line in (out or "").strip().splitlines():
                print(f"        | {line}")
        else:
            print(f"ok    {name}")

    print(f"\nGate 24 self-test: {len(CASES)} check(s), {failed} failure(s).")
    if failed:
        print("::error::Gate 24's detector does not behave as documented — "
              "a green Gate 24 cannot be read as evidence until this passes.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
