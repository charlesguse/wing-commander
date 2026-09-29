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

SECOND CHECK: A GITHUB TOKEN OR AN OIDC GRANT (#814)
----------------------------------------------------
When a step's `with:` has no `github_token`, claude-code-action@v1 tries to
exchange an OIDC token for its own App token instead. It does this before
Claude starts, so without `id-token: write` the step fails. Every such step
is caught here unless the permissions its job actually runs under (the
job's own `permissions:`, or the workflow-level block when the job declares
none; `write-all` counts) grant `id-token: write`. A step inside a
composite action cannot see its caller's permissions, so it always needs
`github_token`. The failure names the file and the step.
Evidence: lifecycle-review-gate.yml's `Reviewer` step had its
`github_token` removed (T080/F9, #759) in a job with no `id-token: write`.
On its first live run (36640266298, job 109650842162) the action retried
the OIDC fetch three times, stopped with `Could not fetch an OIDC token.
Did you remember to add id-token: write ...`, and never started Claude.
The step's `continue-on-error: true` made it read as success. The round
came back Inconclusive with no transcript. Every gate stayed green.

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


def _grants_id_token_write(permissions):
    """True when a `permissions:` value grants `id-token: write`."""
    if isinstance(permissions, str):
        return permissions.strip() == "write-all"
    if isinstance(permissions, dict):
        return str(permissions.get("id-token") or "").strip() == "write"
    return False


def token_problems(path, doc):
    """#814: every claude-code-action step must either pass `github_token`
    or run in a job whose effective permissions grant `id-token: write` --
    without either, the action's OIDC fallback fails before Claude starts.
    Composite-action steps (and any step not under `jobs.<id>.steps`) have
    no visible job permissions, so they must pass `github_token`."""
    problems = []
    covered = set()
    if isinstance(doc, dict) and isinstance(doc.get("jobs"), dict):
        workflow_perms = doc.get("permissions")
        for job_id, job in doc["jobs"].items():
            if not isinstance(job, dict):
                continue
            perms = job["permissions"] if "permissions" in job else workflow_perms
            oidc_ok = _grants_id_token_write(perms)
            for step in find_claude_code_action_steps(job.get("steps") or []):
                covered.add(id(step))
                with_block = step.get("with") or {}
                if isinstance(with_block, dict) and with_block.get("github_token"):
                    continue
                if oidc_ok:
                    continue
                name = step.get("name") or step.get("id") or "(unnamed step)"
                problems.append(
                    f"{path}: job {job_id!r} step {name!r} passes no "
                    f"github_token and its job does not grant "
                    f"`id-token: write` -- claude-code-action's OIDC "
                    f"fallback will fail before Claude starts (#814, run "
                    f"36640266298). Pass a github_token (a read-only "
                    f"`${{{{ github.token }}}}` is enough for an agent that "
                    f"needs no GitHub access).")
    for step in find_claude_code_action_steps(doc):
        if id(step) in covered:
            continue
        with_block = step.get("with") or {}
        if isinstance(with_block, dict) and with_block.get("github_token"):
            continue
        name = step.get("name") or step.get("id") or "(unnamed step)"
        problems.append(
            f"{path}: step {name!r} passes no github_token and has no job "
            f"permissions this gate can see (composite action) -- "
            f"claude-code-action's OIDC fallback cannot be assumed to work "
            f"(#814). Pass a github_token.")
    return problems


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
    problems.extend(token_problems(path, doc))
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
          github_token: token
          model: claude-sonnet-5
          max_turns: 10
          allowed_tools: Read,Grep
          disallowed_tools: WebFetch
          prompt: hello
      - name: Bad step, pinned past the bare major tag
        uses: anthropics/claude-code-action@v1.2.0
        with:
          claude_code_oauth_token: token
          github_token: token
          model: claude-sonnet-5
          prompt: hello
      - name: Good step
        uses: anthropics/claude-code-action@v1
        with:
          claude_code_oauth_token: token
          github_token: token
          prompt: hello
          claude_args: |
            --model claude-sonnet-5
            --max-turns 10
  f9-shape:
    permissions:
      contents: read
      pull-requests: read
    steps:
      - name: Tokenless reviewer
        uses: anthropics/claude-code-action@v1
        with:
          claude_code_oauth_token: token
          prompt: hello
  oidc-granted:
    permissions:
      contents: read
      id-token: write
    steps:
      - name: Tokenless step with an OIDC grant
        uses: anthropics/claude-code-action@v1
        with:
          claude_code_oauth_token: token
          prompt: hello
"""

# #814: workflow-level permissions -- a job with no permissions block
# inherits the workflow's id-token grant (passes); a job with
# `permissions: {}` overrides it and has none (fails).
FIXTURE_WORKFLOW_PERMS_TEXT = """\
name: gate-92-fixture-workflow-perms
permissions:
  contents: read
  id-token: write
jobs:
  inherits:
    steps:
      - name: Tokenless step inheriting a workflow-level OIDC grant
        uses: anthropics/claude-code-action@v1
        with:
          claude_code_oauth_token: token
          prompt: hello
  overrides:
    permissions: {}
    steps:
      - name: Tokenless step whose job overrides the OIDC grant
        uses: anthropics/claude-code-action@v1
        with:
          claude_code_oauth_token: token
          prompt: hello
"""

# #814: a composite action cannot see its caller's permissions, so a
# tokenless step inside one always fails.
FIXTURE_COMPOSITE_TEXT = """\
name: gate-92-fixture-composite
description: fixture
runs:
  using: composite
  steps:
    - name: Tokenless composite step
      uses: anthropics/claude-code-action@v1
      with:
        claude_code_oauth_token: token
        prompt: hello
"""

TOKEN_JOB_MSG = "passes no github_token and its job does not grant"
TOKEN_COMPOSITE_MSG = "passes no github_token and has no job permissions"


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
        print(f"Gate 92: {len(real_problems)} problem(s) across "
              f"{total_steps} claude-code-action step(s): an input the "
              f"action does not accept, or no github_token and no "
              f"id-token: write grant.")
        return 1
    print(f"Gate 92: all {total_steps} claude-code-action step(s)' with: "
          f"keys are inputs the action accepts, and each passes a "
          f"github_token or runs under id-token: write.")

    # --- self-test -----------------------------------------------------
    self_test_failures = []

    with tempfile.TemporaryDirectory() as tmpdir:
        fixture_path = os.path.join(tmpdir, "gate-92-fixture.yml")
        with open(fixture_path, "w", encoding="utf-8") as fh:
            fh.write(FIXTURE_TEXT)
        fixture_problems = check_file(fixture_path)
        wf_perms_path = os.path.join(tmpdir, "gate-92-fixture-wf-perms.yml")
        with open(wf_perms_path, "w", encoding="utf-8") as fh:
            fh.write(FIXTURE_WORKFLOW_PERMS_TEXT)
        wf_perms_problems = check_file(wf_perms_path)
        composite_path = os.path.join(tmpdir, "action.yml")
        with open(composite_path, "w", encoding="utf-8") as fh:
            fh.write(FIXTURE_COMPOSITE_TEXT)
        composite_problems = check_file(composite_path)

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
    # #814: assert on the exact job/step pairing and the token message,
    # not on a substring every token message shares.
    def token_flagged(problems, job, step, msg=TOKEN_JOB_MSG):
        head = (f"job {job!r} step {step!r} " if job else f"step {step!r} ")
        return any(head + msg in p for p in problems)

    token_expectations = (
        (fixture_problems, "f9-shape", "Tokenless reviewer", TOKEN_JOB_MSG,
         True, "F9-shape step (no github_token, job without id-token: write)"),
        (fixture_problems, "oidc-granted", "Tokenless step with an OIDC grant",
         TOKEN_JOB_MSG, False, "tokenless step in a job granting id-token: write"),
        (wf_perms_problems, "inherits",
         "Tokenless step inheriting a workflow-level OIDC grant", TOKEN_JOB_MSG,
         False, "tokenless step inheriting a workflow-level id-token: write"),
        (wf_perms_problems, "overrides",
         "Tokenless step whose job overrides the OIDC grant", TOKEN_JOB_MSG,
         True, "tokenless step whose `permissions: {}` overrides a "
               "workflow-level id-token: write"),
        (composite_problems, None, "Tokenless composite step",
         TOKEN_COMPOSITE_MSG, True, "tokenless composite-action step"),
    )
    for problems, job, step, msg, expect_flag, what in token_expectations:
        flagged = token_flagged(problems, job, step, msg)
        if expect_flag and not flagged:
            self_test_failures.append(
                f"fixture's {what} was not caught (#814): {problems!r}")
        elif not expect_flag and flagged:
            self_test_failures.append(
                f"fixture's {what} was wrongly flagged (#814): {problems!r}")
    if len(wf_perms_problems) != 1 or len(composite_problems) != 1:
        self_test_failures.append(
            f"#814 fixtures produced unexpected extra problems: "
            f"{wf_perms_problems!r} {composite_problems!r}")
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
          "caught by name; the F9-shape, `permissions: {}`-override and "
          "composite tokenless steps were caught (#814); the good step and "
          "the job- and workflow-level OIDC-granted tokenless steps were "
          "not flagged; and the real fleet passes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
