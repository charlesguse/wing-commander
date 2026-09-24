#!/usr/bin/env python3
"""Gate 92 — every `anthropics/claude-code-action@v1` step's `with:` keys are
inputs that version actually accepts.

WHY THIS EXISTS
----------------
#499: board-loop.yml's five agent steps (triage-propose, route-propose,
fixer, reviewer, review-fixup) passed `model:`, `max_turns:`,
`allowed_tools:` and `disallowed_tools:` directly as `with:` inputs to
`anthropics/claude-code-action@v1`. v1 silently ignores unknown inputs — it
only logs a `##[warning]`, never fails the step — so the resolved model
tier, the turn ceiling, and the tool allowlist were never applied. Every
other stage workflow already threads these through `claude_args` (see
intake.yml's `Intake` step), so board-loop.yml was the one outlier, and
nothing caught it: the workflow, and every gate that ran against it,
stayed green while the actual behaviour silently drifted from what the
`with:` block appeared to configure. Visibly, board-loop's route stage sent
every issue to `spec` for weeks — a fenced proposal block from the
mis-tooled agent (12 permission denials in 21 turns) was never parsed
because the allowlist that should have granted it read access was
silently discarded, and the same board-route-proposal.json's own default
(`{"category": "spec", ...}`) took over. See #499 for the full account.

This gate is the general form of that PR's fix: any `claude-code-action@v1`
step anywhere in `.github/workflows` or `.github/actions`, now or later,
that passes an input the action does not accept fails loudly at PR time
instead of degrading a stage's behaviour with only a log line as evidence.

WHAT IT CHECKS
--------------
Every YAML file under `.github/workflows/` and `.github/actions/` is parsed,
and every step whose `uses:` pins `anthropics/claude-code-action@v1`
(workflow `jobs.*.steps` or composite-action `runs.steps` — the walk is
structural, not job/step-name specific, so it also catches a
`claude-code-action` step added inside a composite action) has its `with:`
keys checked against ACCEPTED_INPUTS below. Any key not in that set fails,
naming the file, the step, and the offending key(s).

ACCEPTED_INPUTS is hardcoded from the action's own refusal, not
re-derived at gate time (a network call here would make this gate flaky
and would not exercise a fixed contract): the exact `##[warning]Unexpected
input(s) ..., valid inputs are [...]` line `claude-code-action@v1` printed
for board-loop.yml's triage-propose step in run 36027401298 (job
107727724501), https://github.com/charlesguse/wing-commander/actions/runs/36027401298/job/107727724501
-- the same run and warning text #499 cites.

The self-test builds a fixture workflow tree in memory with one
`claude-code-action@v1` step carrying `model:`/`max_turns:` (this PR's own
motivating defect, reproduced) beside a clean sibling step, and asserts the
bad step is caught by name while the clean one and the real fleet both
pass.
"""
import glob
import os
import sys

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_shell_harness import use_utf8_stdout  # noqa: E402

ACTION_REF = "anthropics/claude-code-action@v1"

# Verbatim from claude-code-action@v1's own refusal, board-loop.yml
# triage-propose step, run 36027401298 / job 107727724501:
#   ##[warning]Unexpected input(s) 'model', 'max_turns', 'allowed_tools',
#   'disallowed_tools', valid inputs are [...]
# https://github.com/charlesguse/wing-commander/actions/runs/36027401298/job/107727724501
ACCEPTED_INPUTS = {
    "trigger_phrase", "assignee_trigger", "label_trigger", "base_branch",
    "branch_prefix", "branch_name_template", "allowed_bots",
    "allowed_non_write_users", "include_comments_by_actor",
    "exclude_comments_by_actor", "prompt", "settings", "anthropic_api_key",
    "claude_code_oauth_token", "anthropic_federation_rule_id",
    "anthropic_organization_id", "anthropic_service_account_id",
    "anthropic_workspace_id", "anthropic_oidc_audience", "github_token",
    "use_bedrock", "use_vertex", "use_foundry", "claude_args",
    "additional_permissions", "use_sticky_comment",
    "classify_inline_comments", "use_commit_signing", "ssh_signing_key",
    "bot_id", "bot_name", "track_progress", "include_fix_links",
    "path_to_claude_code_executable", "path_to_bun_executable",
    "display_report", "show_full_output", "plugins", "plugin_marketplaces",
}


def find_claude_code_action_steps(doc):
    """Walk a parsed YAML tree (workflow or composite action) and yield every
    step dict whose `uses:` pins ACTION_REF. Structural, not path-specific,
    so it also catches one nested inside a composite action's `runs.steps`
    or any future job/step shape."""
    steps = []

    def walk(node):
        if isinstance(node, dict):
            uses = node.get("uses")
            if isinstance(uses, str) and uses.strip() == ACTION_REF:
                steps.append(node)
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(doc)
    return steps


def check_file(path):
    """Return a list of human-readable problems found in one YAML file."""
    problems = []
    try:
        with open(path, encoding="utf-8") as fh:
            doc = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        return [f"{path}: could not parse as YAML ({exc})"]
    if not isinstance(doc, (dict, list)):
        return problems

    for step in find_claude_code_action_steps(doc):
        name = step.get("name") or step.get("id") or "(unnamed step)"
        with_block = step.get("with") or {}
        if not isinstance(with_block, dict):
            continue
        bad = sorted(k for k in with_block if k not in ACCEPTED_INPUTS)
        if bad:
            problems.append(
                f"{path}: step {name!r} passes claude-code-action@v1 "
                f"input(s) it does not accept: {', '.join(bad)}. Move "
                f"them into claude_args (see intake.yml's Intake step).")
    return problems


def gather_files():
    files = []
    for pattern in (".github/workflows/*.yml", ".github/workflows/*.yaml"):
        files.extend(glob.glob(pattern))
    for pattern in (".github/actions/**/action.yml",
                     ".github/actions/**/action.yaml"):
        files.extend(glob.glob(pattern, recursive=True))
    return sorted(set(files))


def check_repo():
    problems = []
    for path in gather_files():
        problems.extend(check_file(path))
    return problems


def main():
    use_utf8_stdout()
    if not os.path.isdir(".github"):
        sys.exit("::error::run this from the repository root; "
                  ".github not found.")

    real_problems = check_repo()
    for p in real_problems:
        print(f"::error::Gate 92: {p}")
    if real_problems:
        print(f"Gate 92: {len(real_problems)} claude-code-action@v1 "
              f"step(s) pass an input v1 does not accept.")
        return 1
    print("Gate 92: every claude-code-action@v1 step's with: keys are "
          "inputs v1 accepts.")

    # --- self-test -----------------------------------------------------
    self_test_failures = []

    fixture_text = """
name: gate-92-fixture
jobs:
  demo:
    steps:
      - name: Bad step
        uses: anthropics/claude-code-action@v1
        with:
          claude_code_oauth_token: token
          model: claude-sonnet-5
          max_turns: 10
          allowed_tools: Read,Grep
          disallowed_tools: WebFetch
          prompt: hello
      - name: Good step
        uses: anthropics/claude-code-action@v1
        with:
          claude_code_oauth_token: token
          prompt: hello
          claude_args: |
            --model claude-sonnet-5
            --max-turns 10
"""
    fixture_doc = yaml.safe_load(fixture_text)
    fixture_problems = []
    for step in find_claude_code_action_steps(fixture_doc):
        name = step.get("name") or "(unnamed step)"
        with_block = step.get("with") or {}
        bad = sorted(k for k in with_block if k not in ACCEPTED_INPUTS)
        if bad:
            fixture_problems.append(f"fixture: step {name!r}: {bad}")

    joined = " ".join(fixture_problems)
    if "Bad step" not in joined:
        self_test_failures.append(
            f"fixture's bad step (model/max_turns/allowed_tools/"
            f"disallowed_tools) was not caught: {fixture_problems!r}")
    elif "Good step" in joined:
        self_test_failures.append(
            f"fixture's good step (claude_args only) was wrongly flagged: "
            f"{fixture_problems!r}")
    else:
        for expect in ("model", "max_turns", "allowed_tools",
                       "disallowed_tools"):
            if expect not in joined:
                self_test_failures.append(
                    f"fixture's bad step was caught but {expect!r} was "
                    f"not named: {fixture_problems!r}")
        if not self_test_failures:
            print(f"note: fixture bad step caught: {fixture_problems}")

    # Re-confirm the real fleet still passes, so a self-test fixture
    # leaking into the real check cannot read as green.
    if check_repo():
        self_test_failures.append(
            "the real fleet no longer passes after running the self-test "
            "fixture -- the fixture mutated shared state.")

    if self_test_failures:
        for f in self_test_failures:
            print(f"::error::Gate 92 self-test: {f}")
        print(f"Gate 92 self-test: {len(self_test_failures)} failure(s).")
        return 1

    print("Gate 92 self-test: the bad step was caught by name, the good "
          "step (claude_args only) was not flagged, and the real fleet "
          "passes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
