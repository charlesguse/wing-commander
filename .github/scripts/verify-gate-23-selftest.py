#!/usr/bin/env python3
"""Self-test for lint-workflows.yml's Gate 23 (verify-gate-23.py).

Gate 23 enumerates a fleet that, once this feature lands, should be
uniformly compliant forever — so like Gate 7's own self-test, a passing Gate
23 run says nothing about whether its detection logic actually works unless
something here proves it can fail. This feeds the shipped
verify-gate-23.py synthetic workflow trees, each carrying one known defect
(or no defect at all), and asserts the verdict and that the failure names the
right site.

Runs the SHIPPED script directly (no extraction needed — unlike Gates 6/7,
Gate 23 already lives as its own standalone .github/scripts file, so this
self-test executes it exactly as lint-workflows.yml does, just with a
different cwd).

Usage: python3 .github/scripts/verify-gate-23-selftest.py
"""
import os
import subprocess
import sys
import tempfile

GATE_SCRIPT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "verify-gate-23.py"))

GOOD_JOB = """\
name: stage
on:
  workflow_call:
jobs:
  run:
    runs-on: ubuntu-latest
    steps:
      - id: agent-ceiling
        uses: ./.wing-commander-pipeline/.github/actions/wing-commander-turn-ceiling
        with:
          intended-turns: 40
      - id: agent
        continue-on-error: true
        uses: anthropics/claude-code-action@v1
        with:
          claude_args: |
            --model claude-sonnet-5
            --max-turns ${{ steps.agent-ceiling.outputs.ceiling }}
      - id: agent-verdict
        if: always() && steps.agent.outcome != 'skipped'
        uses: ./.wing-commander-pipeline/.github/actions/wing-commander-agent-verdict
        with:
          intended-turns: 40
      - name: Fail loud on non-healthy agent verdict
        if: always() && steps.agent.outcome != 'skipped' && steps.agent-verdict.outputs.verdict != 'healthy'
        run: |
          echo "::error::agent step rejected"
          exit 1
"""


def replace_once(text, old, new):
    assert old in text, f"fixture setup error: {old!r} not found"
    return text.replace(old, new, 1)


MISSING_CONTINUE_ON_ERROR = replace_once(
    GOOD_JOB, "        continue-on-error: true\n", "")

LITERAL_MAX_TURNS = replace_once(
    GOOD_JOB, "--max-turns ${{ steps.agent-ceiling.outputs.ceiling }}",
    "--max-turns 100")

RAW_PASSTHROUGH_MAX_TURNS = replace_once(
    GOOD_JOB, "--max-turns ${{ steps.agent-ceiling.outputs.ceiling }}",
    "--max-turns ${{ inputs.max-turns }}")

MISSING_VERDICT_STEP = replace_once(GOOD_JOB, """\
      - id: agent-verdict
        if: always() && steps.agent.outcome != 'skipped'
        uses: ./.wing-commander-pipeline/.github/actions/wing-commander-agent-verdict
        with:
          intended-turns: 40
""", "")

MISSING_FAIL_LOUD = replace_once(GOOD_JOB, """\
      - name: Fail loud on non-healthy agent verdict
        if: always() && steps.agent.outcome != 'skipped' && steps.agent-verdict.outputs.verdict != 'healthy'
        run: |
          echo "::error::agent step rejected"
          exit 1
""", "")

# The pre-PR-#221 shape: `always()` and nothing else. The verdict step runs
# even when the agent step was legitimately skipped, answers
# `unclassifiable`, and the fail-loud arm fails a green job.
VERDICT_UNGUARDED = replace_once(
    GOOD_JOB,
    "      - id: agent-verdict\n"
    "        if: always() && steps.agent.outcome != 'skipped'\n",
    "      - id: agent-verdict\n        if: always()\n")

FAIL_LOUD_UNGUARDED = replace_once(
    GOOD_JOB,
    "        if: always() && steps.agent.outcome != 'skipped' && "
    "steps.agent-verdict.outputs.verdict != 'healthy'\n",
    "        if: always() && steps.agent-verdict.outputs.verdict "
    "!= 'healthy'\n")

# The subtler shape, and the one that actually shipped twice: a hand-copied
# SUBSET of the agent step's conditions instead of its outcome. It looks
# guarded, and it is — against exactly the skips it happens to name.
VERDICT_RESTATES_AGENT_CONDITIONS = replace_once(
    GOOD_JOB,
    "      - id: agent-verdict\n"
    "        if: always() && steps.agent.outcome != 'skipped'\n",
    "      - id: agent-verdict\n"
    "        if: steps.lifecycle-gate.outputs.is-open == 'true' && always()\n")

# Order within the `&&` chain carries no meaning; watchdog.yml writes the
# guard first. This must PASS.
GUARD_BEFORE_ALWAYS = replace_once(
    GOOD_JOB,
    "        if: always() && steps.agent.outcome != 'skipped'\n"
    "        uses: ./.wing-commander-pipeline/.github/actions/wing-commander-agent-verdict\n",
    "        if: steps.agent.outcome != 'skipped' && always()\n"
    "        uses: ./.wing-commander-pipeline/.github/actions/wing-commander-agent-verdict\n")

# multiplier: 1 is a raw inputs.max-turns passthrough wearing the
# composite's clothes — the ceiling equals the intended budget, so the
# agent is cut off at exactly the number this feature exists to stop
# cutting it off at. Only detectable by reading the ceiling step's
# `with:` (T025).
CEILING_WITH = "        with:\n          intended-turns: 40\n"

MULTIPLIER_OF_ONE = replace_once(
    GOOD_JOB, CEILING_WITH, CEILING_WITH + "          multiplier: '1'\n")

MULTIPLIER_EXPRESSION_IS_NOT_STATICALLY_KNOWABLE = replace_once(
    GOOD_JOB, CEILING_WITH,
    CEILING_WITH + "          multiplier: ${{ inputs.ceiling-multiplier }}\n")

UNPARSEABLE_ALONGSIDE_A_GOOD_SITE = {
    "stage.yml": GOOD_JOB,
    "broken.yml": "name: broken\njobs:\n   - [unclosed\n  bad: : :\n",
}

NO_SITES_AT_ALL = """\
name: not a stage
on:
  pull_request: {}
jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - run: echo nothing to see here
"""

CASES = [
    ("healthy: a known-good site passes",
     GOOD_JOB, False, ()),
    ("missing continue-on-error fails, named",
     MISSING_CONTINUE_ON_ERROR, True, ("agent", "continue-on-error")),
    ("--max-turns a literal instead of the ceiling step's output fails, "
     "named (US3 Acceptance Scenario 3)",
     LITERAL_MAX_TURNS, True, ("agent", "does not resolve")),
    ("--max-turns a raw inputs.max-turns passthrough fails, named",
     RAW_PASSTHROUGH_MAX_TURNS, True, ("agent", "does not resolve")),
    ("missing verdict step fails, named",
     MISSING_VERDICT_STEP, True, ("agent", "no wing-commander-agent-verdict")),
    ("missing fail-loud arm fails, named",
     MISSING_FAIL_LOUD, True, ("agent", "no fail-loud step")),
    ("verdict step gated on a bare always(), with no skip guard, fails",
     VERDICT_UNGUARDED, True, ("agent", "not skip-guarded")),
    ("fail-loud step with no skip guard fails",
     FAIL_LOUD_UNGUARDED, True, ("agent", "not skip-guarded")),
    ("verdict step restating a subset of the agent step's own conditions "
     "instead of its outcome fails (PR #221's two shipped drifts)",
     VERDICT_RESTATES_AGENT_CONDITIONS, True,
     ("agent", "not skip-guarded", "steps.lifecycle-gate")),
    ("the skip guard written before always() still passes — order in the "
     "&& chain is not meaning",
     GUARD_BEFORE_ALWAYS, False, ()),
    ("a ceiling step declaring multiplier: 1 fails — the ceiling would "
     "equal the intended budget (T025)",
     MULTIPLIER_OF_ONE, True, ("agent", "multiplier: 1")),
    ("a multiplier given as an expression passes — not statically knowable "
     "here, and the action validates it at runtime",
     MULTIPLIER_EXPRESSION_IS_NOT_STATICALLY_KNOWABLE, False, ()),
    ("a workflow that does not parse as YAML fails the gate rather than "
     "dropping out of coverage — checked alongside a compliant workflow so "
     "the zero-in-scope-sites guard cannot be what fails the run",
     UNPARSEABLE_ALONGSIDE_A_GOOD_SITE, True,
     ("could not parse", "silently dropping")),
]


def run_case(name, workflow_text, expect_fail, must_mention):
    root = tempfile.mkdtemp(prefix="verify_gate23_case_")
    try:
        wf_dir = os.path.join(root, ".github", "workflows")
        os.makedirs(wf_dir)
        files = (workflow_text if isinstance(workflow_text, dict)
                 else {"stage.yml": workflow_text})
        for filename, text in files.items():
            with open(os.path.join(wf_dir, filename), "w",
                      encoding="utf-8") as f:
                f.write(text)
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
        import shutil
        shutil.rmtree(root, ignore_errors=True)


def run_no_sites_case():
    root = tempfile.mkdtemp(prefix="verify_gate23_case_")
    try:
        wf_dir = os.path.join(root, ".github", "workflows")
        os.makedirs(wf_dir)
        with open(os.path.join(wf_dir, "lint.yml"), "w", encoding="utf-8") as f:
            f.write(NO_SITES_AT_ALL)
        proc = subprocess.run([sys.executable, GATE_SCRIPT], cwd=root,
                              capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
        out = (proc.stdout or "") + (proc.stderr or "")
        problems = []
        if proc.returncode == 0:
            problems.append("expected the gate to FAIL (zero in-scope "
                            "sites found is a hard stop), it PASSED")
        if "zero in-scope" not in out:
            problems.append("error text never mentions the zero-sites guard")
        return problems, out
    finally:
        import shutil
        shutil.rmtree(root, ignore_errors=True)


def main():
    if not os.path.isfile(GATE_SCRIPT):
        sys.exit(f"::error::{GATE_SCRIPT} not found — run this from the "
                 f"repository root.")

    failures = []

    def record(name, problems, out):
        failures.append((name, problems, out))
        print(f"FAIL  {name}")
        for problem in problems:
            print(f"        - {problem}")
        for line in (out or "").strip().splitlines():
            print(f"        | {line}")

    for name, workflow_text, expect_fail, must_mention in CASES:
        problems, out = run_case(name, workflow_text, expect_fail, must_mention)
        if problems:
            record(name, problems, out)
        else:
            print(f"ok    {name}")

    problems, out = run_no_sites_case()
    name = "a fleet with zero in-scope sites is a hard stop, not a clean pass"
    if problems:
        record(name, problems, out)
    else:
        print(f"ok    {name}")

    total = len(CASES) + 1
    print()
    if failures:
        print(f"::error::Gate 23 self-test: {len(failures)} of {total} "
             f"check(s) behaved wrongly ({', '.join(n for n, _, _ in failures)}). "
             f"Gate 23's detection logic does not do what its name claims, "
             f"so a green Gate 23 on the real fleet means nothing.")
        return 1
    print(f"Gate 23 self-test: all {total} checks behaved as expected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
