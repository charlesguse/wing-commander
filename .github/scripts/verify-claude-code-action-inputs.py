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
intake.yml's `Create spec from issue` step, intake.yml:622), so
board-loop.yml was the one outlier, and
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
and every step whose `uses:` pins `anthropics/claude-code-action@` — any
ref, not only a bare `v1` major tag: a code review of the first version of
this gate showed a step pinned `anthropics/claude-code-action@v1.2.0` (an
otherwise-identical, otherwise-bad step) passing green, because the
comparison was `== "anthropics/claude-code-action@v1"` exactly. Matched the
same way Gate 23 (verify-gate-23.py) matches this action, by prefix rather
than by exact ref, so a minor/patch pin or a commit-SHA pin is covered too
(workflow `jobs.*.steps` or composite-action `runs.steps` — the walk is
structural, not job/step-name specific, so it also catches a
`claude-code-action` step added inside a composite action) — has its
`with:` keys checked against ACCEPTED_INPUTS below. Any key not in that set
fails, naming the file, the step, and the offending key(s). Finding zero
such steps repo-wide is ALSO a failure (Gate 5's precedent: a verifier that
never fires is indistinguishable from one whose detection is broken) —
there are 20+ known call sites as of this writing, so zero means the
detector itself regressed, not that the fleet went quiet.

ACCEPTED_INPUTS is hardcoded from the action's own refusal, not
re-derived at gate time (a network call here would make this gate flaky
and would not exercise a fixed contract): the exact `##[warning]Unexpected
input(s) ..., valid inputs are [...]` line `claude-code-action@v1` printed
for board-loop.yml's triage-propose step in run 36027401298 (job
107727724501), https://github.com/charlesguse/wing-commander/actions/runs/36027401298/job/107727724501
-- the same run and warning text #499 cites. This is v1's own accepted-input
list; a step pinned to a later v1.x might accept more inputs than this, but
never fewer, so hardcoding v1's list is conservative (a false failure on a
genuinely-new input is possible and should be treated as this list needing
an update, not as the gate being wrong) rather than silently permissive.

The self-test writes a fixture workflow file to a temp directory and runs
`check_file()` on it for real, the same function the real fleet is checked
with, rather than re-implementing the check inline — a second copy of the
matching logic could pass its own self-test while the real `check_file()`
had drifted. The fixture carries a step pinned `@v1.2.0` (this review's own
motivating defect: the exact-match bug let it through as "good") with
`model:`/`max_turns:` (this PR's original motivating defect) beside a clean
`@v1` sibling using only `claude_args`, and asserts the bad step is caught
by name, by ref, and by input, while the clean one and the real fleet both
pass.
"""
import glob
import os
import sys
import tempfile

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_shell_harness import use_utf8_stdout  # noqa: E402

# Matched by prefix, not exact ref, the same way Gate 23's
# AGENT_USES_PREFIX does for this same action -- a pin more specific than a
# bare major tag (`@v1.2.0`, or a commit SHA) is still this action.
ACTION_REF_PREFIX = "anthropics/claude-code-action@"

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
    step dict whose `uses:` pins claude-code-action, at any ref (a bare
    major tag, a minor/patch pin, or a commit SHA -- ACTION_REF_PREFIX is
    matched by prefix, not equality, precisely so a pin more specific than
    `@v1` cannot slip past this gate the way `@v1.2.0` did before this
    matched by prefix). Structural, not path-specific, so it also catches
    one nested inside a composite action's `runs.steps` or any future
    job/step shape."""
    steps = []

    def walk(node):
        if isinstance(node, dict):
            uses = node.get("uses")
            if isinstance(uses, str) and uses.strip().startswith(ACTION_REF_PREFIX):
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
        uses = str(step.get("uses") or "").strip()
        with_block = step.get("with") or {}
        if not isinstance(with_block, dict):
            continue
        bad = sorted(k for k in with_block if k not in ACCEPTED_INPUTS)
        if bad:
            problems.append(
                f"{path}: step {name!r} ({uses}) passes claude-code-action "
                f"input(s) it does not accept: {', '.join(bad)}. Move them "
                f"into claude_args (see intake.yml's 'Create spec from "
                f"issue' step, intake.yml:622).")
    return problems


def gather_files():
    files = []
    for pattern in (".github/workflows/*.yml", ".github/workflows/*.yaml"):
        files.extend(glob.glob(pattern))
    for pattern in (".github/actions/**/action.yml",
                     ".github/actions/**/action.yaml"):
        files.extend(glob.glob(pattern, recursive=True))
    return sorted(set(files))


def count_claude_code_action_steps():
    """Total claude-code-action steps found repo-wide -- used to assert the
    detector itself still fires (Gate 5's precedent) independent of whether
    any of them is well-formed."""
    total = 0
    for path in gather_files():
        try:
            with open(path, encoding="utf-8") as fh:
                doc = yaml.safe_load(fh)
        except yaml.YAMLError:
            continue
        if isinstance(doc, (dict, list)):
            total += len(find_claude_code_action_steps(doc))
    return total


def check_repo():
    problems = []
    for path in gather_files():
        problems.extend(check_file(path))
    return problems


FIXTURE_TEXT = """\
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
      - name: Bad step, pinned past the bare major tag
        uses: anthropics/claude-code-action@v1.2.0
        with:
          claude_code_oauth_token: token
          model: claude-sonnet-5
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


def main():
    use_utf8_stdout()
    if not os.path.isdir(".github"):
        sys.exit("::error::run this from the repository root; "
                  ".github not found.")

    total_steps = count_claude_code_action_steps()
    if total_steps == 0:
        print("::error::Gate 92: found zero claude-code-action steps "
              "repo-wide. This repository has 20+ known call sites; zero "
              "means ACTION_REF_PREFIX or the YAML walk regressed, not that "
              "the fleet went quiet.")
        return 1

    real_problems = check_repo()
    for p in real_problems:
        print(f"::error::Gate 92: {p}")
    if real_problems:
        print(f"Gate 92: {len(real_problems)} claude-code-action "
              f"step(s), of {total_steps} checked, pass an input the "
              f"action does not accept.")
        return 1
    print(f"Gate 92: all {total_steps} claude-code-action step(s)' with: "
          f"keys are inputs the action accepts.")

    # --- self-test -----------------------------------------------------
    self_test_failures = []

    with tempfile.TemporaryDirectory() as tmpdir:
        fixture_path = os.path.join(tmpdir, "gate-92-fixture.yml")
        with open(fixture_path, "w", encoding="utf-8") as fh:
            fh.write(FIXTURE_TEXT)
        fixture_problems = check_file(fixture_path)

    joined = " ".join(fixture_problems)
    if "'Bad step'" not in joined:
        self_test_failures.append(
            f"fixture's bad step (model/max_turns/allowed_tools/"
            f"disallowed_tools, pinned @v1) was not caught: "
            f"{fixture_problems!r}")
    if "Bad step, pinned past the bare major tag" not in joined:
        self_test_failures.append(
            f"fixture's @v1.2.0-pinned bad step was not caught -- "
            f"ACTION_REF_PREFIX matching may have regressed to an exact-"
            f"ref comparison: {fixture_problems!r}")
    if "'Good step'" in joined:
        self_test_failures.append(
            f"fixture's good step (claude_args only) was wrongly flagged: "
            f"{fixture_problems!r}")
    if not self_test_failures:
        for expect in ("model", "max_turns", "allowed_tools",
                       "disallowed_tools"):
            if expect not in joined:
                self_test_failures.append(
                    f"fixture's bad step(s) were caught but {expect!r} "
                    f"was not named: {fixture_problems!r}")
    if not self_test_failures:
        print(f"note: fixture bad steps caught: {fixture_problems}")

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

    print("Gate 92 self-test: both bad steps (bare @v1 and @v1.2.0) were "
          "caught by name, the good step (claude_args only) was not "
          "flagged, and the real fleet passes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
