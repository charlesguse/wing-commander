#!/usr/bin/env python3
"""Self-test for lint-workflows.yml's Gate 12.

Gate 12 asserts that every `gh`/API call a workflow makes runs under a token
whose permissions actually cover what it touches — the class of defect
behind spec 005's `gh workflow run` 403 and
specs/033-pr-conversation-commands T062/T063 (a `gh run cancel`/`gh run
list` pair that inherited the App token, which per docs/setup.md has no
Actions permission, and 403'd; T062's variant went further and reported that
403 to a maintainer as an "already completed" outcome). All three were found
by accident — a maintainer noticing a stall, not a check — and T062/T063
survived five pipeline cycles, a full quickstart desk-check, and three
rounds of executing the shipped shell against synthetic inputs first.

Also covers multi-permission verbs: `gh pr create` needs contents:read on
top of pull-requests:write (it resolves repository.defaultBranchRef over
GraphQL even with an explicit --base), and `gh pr ready` needs
contents:WRITE — the markPullRequestReadyForReview mutation is gated like
a merge (cli/cli discussion #6924).

A gate that never fires is indistinguishable from one whose detection logic
is broken (gate 5 exists because that already happened once — a verifier sat
green for weeks checking a filter that did not ship). So this script feeds
Gate 12 synthetic workflow trees that each carry one known-bad call (or one
known-fine one) and asserts the verdict, including what the error text
names.

Drift-proofing: the gate's source is EXTRACTED from lint-workflows.yml at
run time rather than copied here, the same way verify-gate-6.py and
verify-gate-7.py do it. There is no second copy to fall out of sync — if the
shipped gate changes, this runs the changed gate.

Usage: python3 .github/scripts/verify-gate-12.py
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_lint_gate_source import LINT_WORKFLOW, extract_gate_step  # noqa: E402

_N = chr(10)

STEP_PREFIX = "Gate 12"


# ---------------------------------------------------------------- fixtures
#
# Kept deliberately tiny and self-contained rather than mutating the real
# fleet: the real files change for unrelated reasons, and a self-test that
# breaks on every unrelated edit gets deleted rather than fixed.

DOCS_OK = """\
## 1. Create the wing-commander-bot GitHub App

1. GitHub -> Settings

2. **Repository permissions**:
   - Contents: **Read and write**
   - Issues: **Read and write**
   - Pull requests: **Read and write**
   - Everything else: No access
"""

# Same doc, but the App holds Issues at Read-only — the T073 case: category
# membership alone would let an App-token `gh issue create` pass here.
DOCS_ISSUES_READONLY = DOCS_OK.replace("Issues: **Read and write**",
                                       "Issues: **Read-only**")

# Same doc, but Pull requests at Read-only - the `gh pr close` mirror of T073.
DOCS_PRS_READONLY = DOCS_OK.replace("Pull requests: **Read and write**",
                                    "Pull requests: **Read-only**")

APP_ENV = 'GH_TOKEN: ${{ steps.ctx.outputs.token }}'
DEFAULT_ENV = 'GH_TOKEN: ${{ github.token }}'


def wf(run_body, job_perms="", job_env="", name="w"):
    perms = f"    permissions:\n{job_perms}" if job_perms else ""
    env = f"    env:\n{job_env}" if job_env else ""
    return (f"name: {name}\n"
            f"on:\n  workflow_dispatch: {{}}\n"
            f"jobs:\n  work:\n    runs-on: ubuntu-latest\n{perms}{env}"
            f"    steps:\n      - name: step\n        env:\n"
            f"{run_body}\n")


def step(env_lines, run_lines):
    env = "".join(f"          {l}\n" for l in env_lines)
    run = "        run: |\n" + "".join(f"          {l}\n" for l in run_lines)
    return env + run


ACTIONS_WRITE = "      actions: write\n"
ACTIONS_READ = "      actions: read\n"
ISSUES_WRITE = "      issues: write\n"
CONTENTS_READ = "      contents: read\n"


def minted_wf(minter_uses, run_lines, step_id="e2e-token"):
    """A job whose first step mints a token (or pretends to) under `step_id`
    and whose second step runs `gh` under `steps.<step_id>.outputs.token`.
    Gate 12 recognises the output as the App token only when the minting
    step really `uses: actions/create-github-app-token` - structurally, per
    job - so the same generic step id under any other action stays an
    unrecognised token, not a silently-inherited App classification."""
    run = "".join(f"          {l}\n" for l in run_lines)
    return ("name: minted\n"
            "on:\n  workflow_dispatch: {}\n"
            "jobs:\n  work:\n    runs-on: ubuntu-latest\n"
            "    steps:\n"
            f"      - name: mint\n        id: {step_id}\n"
            f"        uses: {minter_uses}\n"
            "      - name: call\n        env:\n"
            f"          GH_TOKEN: ${{{{ steps.{step_id}.outputs.token }}}}\n"
            "        run: |\n" + run)


def mkcase_minted(minter_uses, run_lines, docs=DOCS_OK, step_id="e2e-token"):
    return {".github/workflows/w.yml": minted_wf(minter_uses, run_lines, step_id),
            "docs/setup.md": docs}


def mkcase(job_perms, job_env, env_lines, run_lines, docs=DOCS_OK):
    return {
        ".github/workflows/w.yml": wf(step(env_lines, run_lines),
                                      job_perms=job_perms, job_env=job_env),
        "docs/setup.md": docs,
    }


# --- category C fixtures (#215) -------------------------------------------
# Category C reads tools passed at a REUSABLE-WORKFLOW call site, where they
# arrive at the called stage as an unexpanded `inputs.extra-allowed-tools`
# that category B cannot see through. This repository has exactly one such
# call site with a literal list, and its grants are `Bash(python3 ...)` /
# `Bash(bash ...)`, which TOOL_GH_RE matches nothing in - so `cs_grants` is
# empty and neither the cross-check nor its "found no agent step" failure
# branch runs against the real tree. The branch WAS proven by hand when it
# landed (a temporary `Bash(gh run list:*)` grant, since reverted); these
# fixtures are that experiment made permanent, because a proof that is not
# checked in is not coverage.

def caller_wf(grant, called="./.github/workflows/stage.yml",
              key="extra-allowed-tools"):
    return ("name: caller" + _N +
            "on:" + _N + "  workflow_dispatch: {}" + _N +
            "jobs:" + _N + "  call:" + _N +
            "    uses: " + called + _N +
            "    with:" + _N +
            "      " + key + ': "' + grant + '"' + _N)


def stage_wf(agent_env=APP_ENV, with_agent=True):
    head = ("name: stage" + _N +
            "on:" + _N + "  workflow_call: {}" + _N +
            "jobs:" + _N + "  work:" + _N +
            "    runs-on: ubuntu-latest" + _N +
            "    steps:" + _N)
    if not with_agent:
        return head + "      - name: not an agent" + _N + "        run: echo hi" + _N
    return head + ("      - name: agent" + _N +
                   "        uses: anthropics/claude-code-action@v1" + _N +
                   "        env:" + _N +
                   "          " + agent_env + _N)


# A stage with TWO agent steps that do NOT agree about a grant: one runs
# under github.token in a job granting `actions: read` (which covers
# `gh run list`), the other under the App token (which docs/setup.md gives
# no Actions permission at all). A stage-level `extra-allowed-tools` input
# reaches both, so the grant is only safe if it is safe for the least
# privileged one — the whole reason the cross-check loops over EVERY agent
# context rather than the first.
#
# Every other category C fixture builds a stage with exactly one agent
# step, which made that loop untestable: `for ... in ctxs` and
# `for ... in ctxs[:1]` are indistinguishable on a one-element list, so a
# mutation narrowing it to the first agent step left the self-test green.
# Both orderings ship, because truncating from either end must fail.
def stage_wf_split_agents(approve_first=True):
    approving = ("  permissive:" + _N +
                 "    runs-on: ubuntu-latest" + _N +
                 "    permissions:" + _N +
                 "      actions: read" + _N +
                 "    steps:" + _N +
                 "      - name: agent on github.token" + _N +
                 "        uses: anthropics/claude-code-action@v1" + _N +
                 "        env:" + _N +
                 "          " + DEFAULT_ENV + _N)
    rejecting = ("  restricted:" + _N +
                 "    runs-on: ubuntu-latest" + _N +
                 "    steps:" + _N +
                 "      - name: agent on the App token" + _N +
                 "        uses: anthropics/claude-code-action@v1" + _N +
                 "        env:" + _N +
                 "          " + APP_ENV + _N)
    order = (approving, rejecting) if approve_first else (rejecting, approving)
    return ("name: stage" + _N +
            "on:" + _N + "  workflow_call: {}" + _N +
            "jobs:" + _N + "".join(order))


def mkcase_c(grant, with_agent=True, called="./.github/workflows/stage.yml"):
    files = {
        ".github/workflows/caller.yml": caller_wf(grant, called=called),
        ".github/workflows/stage.yml": stage_wf(with_agent=with_agent),
        "docs/setup.md": DOCS_OK,
    }
    return files


# --- category D fixtures (#339) -------------------------------------------
# Category D walks composite actions under .github/actions/**, resolving each
# composite's `inputs.*` token through what the workflow call site passes in
# `with:` (or the input's declared default) and checking the call in THAT
# caller's job. The fixtures build one tiny composite, `wing-commander-probe`,
# and vary the call site around it.

ISSUES_READ = "      issues: read\n"
APP_TOKEN_WITH = 'token: ${{ steps.ctx.outputs.token }}'
DEFAULT_TOKEN_WITH = 'token: ${{ github.token }}'
PROBE_USES = "./.github/actions/wing-commander-probe"
PIPELINE_USES = "./.wing-commander-pipeline/.github/actions/wing-commander-probe"


def composite_action(run_lines, env_lines=(), inputs=("token",),
                     token_default=None, mint_step_id=None,
                     token_env="${{ inputs.token }}"):
    """A composite with one bash step, `Render`, whose env carries
    GH_TOKEN: `token_env` (inputs.token by default) plus `env_lines`,
    running `run_lines`. Every name in `inputs` is declared optional;
    `token` gets `token_default` when one is given. `mint_step_id` adds a
    preceding actions/create-github-app-token step under that id — the
    composite's OWN App mint, in its own step-id namespace."""
    out = "name: probe" + _N + "description: fixture" + _N + "inputs:" + _N
    for name in inputs:
        out += "  " + name + ":" + _N + "    description: t" + _N + "    required: false" + _N
        if name == "token" and token_default is not None:
            out += "    default: " + token_default + _N
    out += "runs:" + _N + "  using: composite" + _N + "  steps:" + _N
    if mint_step_id:
        out += ("    - name: mint" + _N + "      id: " + mint_step_id + _N +
                "      uses: actions/create-github-app-token@v3" + _N)
    out += ("    - name: Render" + _N + "      shell: bash" + _N +
            "      env:" + _N +
            "        GH_TOKEN: " + token_env + _N)
    for l in env_lines:
        out += "        " + l + _N
    out += "      run: |" + _N
    for l in run_lines:
        out += "        " + l + _N
    return out


def composite_caller_job(jname, with_lines, uses_path=PROBE_USES, job_perms=""):
    perms = ("    permissions:" + _N + job_perms) if job_perms else ""
    out = ("  " + jname + ":" + _N + "    runs-on: ubuntu-latest" + _N + perms +
           "    steps:" + _N +
           "      - name: Probe" + _N +
           "        uses: " + uses_path + _N)
    if with_lines:
        out += "        with:" + _N
        for l in with_lines:
            out += "          " + l + _N
    return out


def composite_caller_wf(with_lines, uses_path=PROBE_USES, job_perms=""):
    return ("name: w" + _N + "on:" + _N + "  workflow_dispatch: {}" + _N +
            "jobs:" + _N +
            composite_caller_job("work", with_lines, uses_path, job_perms))


def mkcase_d(with_lines, run_lines, env_lines=(), inputs=("token",),
             token_default=None, job_perms="", uses_path=PROBE_USES):
    return {
        ".github/actions/wing-commander-probe/action.yml":
            composite_action(run_lines, env_lines, inputs, token_default),
        ".github/workflows/w.yml":
            composite_caller_wf(with_lines, uses_path, job_perms),
        "docs/setup.md": DOCS_OK,
    }


CASES = [
    # name, files, expect_fail, must_mention

    ("healthy: App-token issue comment (App has Issues)",
     mkcase("", "", [APP_ENV], ['gh issue comment "$N" --body hi']),
     False, ()),

    ("the T062/T063 defect: App-token `gh run cancel` (App has no Actions)",
     mkcase("", "", [APP_ENV], ['gh run cancel "$RUN_ID" -R "$REPO"']),
     True, ("run cancel", "App token", "actions")),

    ("the T062/T063 fix: per-command prefix routes to github.token, which "
     "the job grants actions:write",
     mkcase(ACTIONS_WRITE, "", [APP_ENV, "DISPATCH_TOKEN: ${{ github.token }}"],
            ['GH_TOKEN="$DISPATCH_TOKEN" gh run cancel "$RUN_ID" -R "$REPO"']),
     False, ()),

    ("github.token call with no permissions: block anywhere to resolve "
     "(inherits the repo default) is reported as unverified, not silently "
     "passed and not failed on a guess - same rule Gate 3 already uses",
     mkcase("", "", [DEFAULT_ENV], ['gh run list -R "$REPO"']),
     False, ("cannot resolve",)),

    ("github.token call with only read granted cannot satisfy a write call",
     mkcase(ACTIONS_READ, "", [DEFAULT_ENV], ['gh run cancel "$RUN_ID" -R "$REPO"']),
     True, ("run cancel", "actions")),

    ("github.token call with read granted satisfies a read call",
     mkcase(ACTIONS_READ, "", [DEFAULT_ENV], ['gh run list -R "$REPO"']),
     False, ()),

    ("gh api under the App token needing Actions (the watchdog collector class)",
     mkcase("", "", [APP_ENV],
            ['jobs="$(gh api "repos/$REPO/actions/runs/$RUN_ID/jobs")"']),
     True, ("actions", "App token")),

    ("gh api under the App token for a permission it DOES have (Issues)",
     mkcase("", "", [APP_ENV],
            ['gh api -X PATCH "repos/$REPO/issues/comments/$ID" -f body=hi']),
     False, ()),

    ("gh api under the App token reading a branch (cleanup.yml's #282 probe: "
     "branches/ is Contents, which the App holds)",
     mkcase("", "", [APP_ENV],
            ['gh api -X GET "repos/$REPO/branches/$BRANCH" --jq .name']),
     False, ()),

    ("cross-repository gh api call is out of scope (different owner/repo)",
     mkcase("", "", [DEFAULT_ENV],
            ['releases="$(gh api repos/github/spec-kit/releases)"']),
     False, ()),

    ("unrecognised subcommand fails loudly rather than passing silently",
     mkcase("", "", [APP_ENV], ['gh totallynew thing "$X"']),
     True, ("totallynew", "SUBCOMMAND_PERMS")),

    # --- auto-release.yml's call sites (#319) ---------------------------
    ("gh run watch is a read: github.token with actions:write (the "
     "dispatching job's grant) satisfies it",
     mkcase(ACTIONS_WRITE, "", [DEFAULT_ENV],
            ['gh run watch "$run_id" --exit-status >/dev/null 2>&1']),
     False, ()),

    ("gh run watch under the App token fails: the App has no Actions grant",
     mkcase("", "", [APP_ENV], ['gh run watch "$run_id" --exit-status']),
     True, ("run watch", "App token", "actions")),

    ("gh api .../commits/... is a Contents read: github.token with "
     "contents:read satisfies it",
     mkcase(CONTENTS_READ, "", [DEFAULT_ENV],
            ['tip="$(gh api "repos/${GITHUB_REPOSITORY}/commits/main" --jq .sha)"']),
     False, ()),

    ("gh api .../commits/... under github.token with only actions:read "
     "fails, naming contents",
     mkcase(ACTIONS_READ, "", [DEFAULT_ENV],
            ['tip="$(gh api "repos/${GITHUB_REPOSITORY}/commits/main" --jq .sha)"']),
     True, ("commits", "contents")),

    ("gh pr close under the App token passes against the documented "
     "Pull requests: Read and write grant",
     mkcase("", "", [APP_ENV],
            ['gh pr close "$n" --repo "$E2E_REPO" --comment "leftover"']),
     False, ()),

    ("gh pr close under the App token fails when Pull requests is "
     "Read-only (the T073 level check, on the new entry)",
     mkcase("", "", [APP_ENV],
            ['gh pr close "$n" --repo "$E2E_REPO" --comment "leftover"'],
            docs=DOCS_PRS_READONLY),
     True, ("pr close", "App token", "pull-requests")),

    # --- structural App-token recognition (#319) -------------------------
    ("a token minted by actions/create-github-app-token in the same job IS "
     "the App token: its gh issue create passes against the documented grant",
     mkcase_minted("actions/create-github-app-token@v3",
                   ['gh issue create --repo "$E2E_REPO" --title t --body b']),
     False, ()),

    ("... and is held to that grant: gh issue create fails when the doc "
     "says Issues is Read-only",
     mkcase_minted("actions/create-github-app-token@v3",
                   ['gh issue create --repo "$E2E_REPO" --title t --body b'],
                   docs=DOCS_ISSUES_READONLY),
     True, ("issue create", "App token", "issues")),

    ("... and the recognition follows the minting step, not the id: the "
     "generic id `token` under some other action is an unrecognised token "
     "(reported unverified, neither passed as the App nor failed)",
     mkcase_minted("some-org/mint-a-different-token@v1",
                   ['gh issue create --repo "$OTHER" --title t --body b'],
                   step_id="token"),
     False, ("unrecognised token", "Unverified")),

    ("... and a job cannot borrow another job's minted token by name: the "
     "same expression in a job with no minting step is unrecognised",
     {".github/workflows/w.yml":
          minted_wf("actions/create-github-app-token@v3",
                    ['gh issue view "$N"']).replace(
              "      - name: mint\n        id: e2e-token\n"
              "        uses: actions/create-github-app-token@v3\n", ""),
      "docs/setup.md": DOCS_OK},
     False, ("unrecognised token", "Unverified")),

    ("an unresolvable gh api path (traced to a $(...) computed value) fails "
     "loudly rather than being silently skipped",
     mkcase("", "", [APP_ENV], ['gh api -X PATCH "$(compute_path)" -f body=hi']),
     True, ("cannot resolve",)),

    ("no false positive: a gh mention inside an echo string never runs",
     mkcase("", "", [APP_ENV],
            ['echo "   gh run cancel $RUN_ID -R $REPO"']),
     False, ()),

    ("no false positive: a gh mention inside a `#` comment never runs",
     mkcase("", "", [APP_ENV],
            ['# gh run cancel is mentioned here for humans only',
             'gh issue view "$N"']),
     False, ()),

    ("no false positive: a gh mention inside a heredoc body (data for "
     "another interpreter) never runs",
     mkcase("", "", [APP_ENV],
            ["python3 - <<'PYEOF'",
             'print("gh run cancel $RUN_ID")',
             "PYEOF"]),
     False, ()),

    ("agent tool grant: Bash(gh run view:*) handed to an agent step whose "
     "token is the App token 403s exactly like a deterministic call would",
     {".github/workflows/w.yml": (
         "name: w\non:\n  workflow_dispatch: {}\njobs:\n  work:\n"
         "    runs-on: ubuntu-latest\n    steps:\n"
         "      - name: Compose tool args\n"
         "        uses: ./.github/actions/wing-commander-tool-args\n"
         "        with:\n"
         '          default-allowed-tools: "Read,Bash(gh run view:*)"\n'
         "      - name: Agent step\n"
         "        uses: anthropics/claude-code-action@v1\n"
         "        env:\n"
         f"          {APP_ENV}\n"),
      "docs/setup.md": DOCS_OK},
     True, ("agent tool grant", "run view", "App token")),

    ("agent tool grant under github.token with the matching job permission "
     "is fine",
     {".github/workflows/w.yml": (
         "name: w\non:\n  workflow_dispatch: {}\njobs:\n  work:\n"
         "    runs-on: ubuntu-latest\n    permissions:\n      actions: read\n"
         "    steps:\n"
         "      - name: Compose tool args\n"
         "        uses: ./.github/actions/wing-commander-tool-args\n"
         "        with:\n"
         '          default-allowed-tools: "Read,Bash(gh run view:*)"\n'
         "      - name: Agent step\n"
         "        uses: anthropics/claude-code-action@v1\n"
         "        env:\n"
         f"          {DEFAULT_ENV}\n"),
      "docs/setup.md": DOCS_OK},
     False, ()),

    # T068 regression guards. The shipped `executable_flags` decides which
    # text really runs; when it wrongly concludes "not executable" the gate
    # skips the call entirely and reports success — a false PASS, the one
    # failure mode a linter must never have. Both shapes below hid real
    # calls in this repository (rebase.yml's `gh label create`, masked by
    # "Once you've rebased"; wing-commander-watchdog-test's `gh workflow
    # run`, masked by "# ... stage 8's resolve job must fail"), so each is
    # pinned with a KNOWN-BAD call after the apostrophe: if the scanner
    # regresses, the call goes invisible and the case stops failing.
    ("T068: an apostrophe inside a DOUBLE-quoted string is a literal, not a "
     "quote opener - a wrongly-permissioned call after it must still be seen",
     mkcase("", "", [APP_ENV],
            # Exactly ONE apostrophe on purpose: a second one would close the
            # bogus frame the bug opens and the fixture would pass even
            # against the broken scanner, proving nothing (this fixture was
            # written with two first, and the mutation test caught it).
            ['echo "Once you\'ve rebased the branch, CI retries automatically"',
             'gh run cancel "$RUN_ID" -R "$REPO"']),
     True, ("run cancel", "App token", "actions")),

    ("T068: an apostrophe inside a TRAILING `#` comment does not open a "
     "quote - a wrongly-permissioned call after it must still be seen",
     mkcase("", "", [APP_ENV],
            ["target=1   # no run 1 exists; stage 8's resolve job must fail",
             'gh run cancel "$target" -R "$REPO"']),
     True, ("run cancel", "App token", "actions")),

    # T073: the App branch must honour the required LEVEL, not just the
    # category. With membership-only checking this case passed while 403ing
    # at runtime - exactly the class T064 built this gate to catch.
    ("T073: an App-token write call against a Read-only App grant fails, "
     "rather than passing on mere category membership",
     mkcase("", "", [APP_ENV], ['gh issue create --title t --body b'],
            docs=DOCS_ISSUES_READONLY),
     True, ("issue create", "App token", "issues")),

    ("T073: an App-token read call against that same Read-only grant is fine",
     mkcase("", "", [APP_ENV], ['gh issue view "$N"'],
            docs=DOCS_ISSUES_READONLY),
     False, ()),

    ("under-permissioned `gh pr create` under github.token with only "
     "pull-requests:write (missing contents:read) fails",
     mkcase("      pull-requests: write\n", "", [DEFAULT_ENV],
            ['gh pr create --repo "$REPO" --base main --head "$HEAD" '
             '--draft --title t --body b']),
     True, ("pr create", "contents")),

    ("the fix: `gh pr create` with both pull-requests:write "
     "and contents:read passes",
     mkcase("      pull-requests: write\n      contents: read\n", "", [DEFAULT_ENV],
            ['gh pr create --repo "$REPO" --base main --head "$HEAD" '
             '--draft --title t --body b']),
     False, ()),

    ("under-permissioned `gh pr ready` under github.token with contents:read "
     "(needs contents:WRITE) fails",
     mkcase("      pull-requests: write\n      contents: read\n", "", [DEFAULT_ENV],
            ['gh pr ready "$N" --repo "$REPO"']),
     True, ("pr ready", "contents")),

    ("the fix: `gh pr ready` with contents:write passes",
     mkcase("      pull-requests: write\n      contents: write\n", "", [DEFAULT_ENV],
            ['gh pr ready "$N" --repo "$REPO"']),
     False, ()),

    # --- category C (#215) ------------------------------------------------
    ("category C: a call site granting `gh run list` to a stage whose agent "
     "runs on the App token fails - the App has no Actions permission",
     mkcase_c("Bash(gh run list:*)"),
     True, ("run list", "App token", "actions")),

    ("category C: the second call-site key, allowed-tools-override, is read "
     "too - not just extra-allowed-tools",
     {".github/workflows/caller.yml":
         caller_wf("Bash(gh run list:*)", key="allowed-tools-override"),
      ".github/workflows/stage.yml": stage_wf(),
      "docs/setup.md": DOCS_OK},
     True, ("run list", "App token", "actions")),

    ("category C: a grant the App token does cover passes",
     mkcase_c("Bash(gh issue comment:*)"),
     False, ()),

    ("category C: a call site granting tools to a stage with no agent step "
     "fails rather than passing quietly",
     mkcase_c("Bash(gh run list:*)", with_agent=False),
     True, ("no agent step",)),

    ("category C: a call site naming a workflow that does not exist fails",
     mkcase_c("Bash(gh run list:*)",
              called="./.github/workflows/gone.yml"),
     True, ("no agent step",)),

    ("category C: a grant the stage's FIRST agent step can satisfy is still "
     "rejected for a later one that cannot - the input reaches both",
     {".github/workflows/caller.yml": caller_wf("Bash(gh run list:*)"),
      ".github/workflows/stage.yml": stage_wf_split_agents(approve_first=True),
      "docs/setup.md": DOCS_OK},
     True, ("restricted / agent on the App token", "run list", "App token",
            "actions")),

    ("category C: and the same the other way round - the offending agent "
     "step being the FIRST one must not be the only case that fails",
     {".github/workflows/caller.yml": caller_wf("Bash(gh run list:*)"),
      ".github/workflows/stage.yml": stage_wf_split_agents(approve_first=False),
      "docs/setup.md": DOCS_OK},
     True, ("restricted / agent on the App token", "run list", "App token",
            "actions")),

    # --- category D: composite actions (#339) -----------------------------
    ("category D: the #337 shape - a composite's `gh run view` under an "
     "`inputs.token` the caller binds to the App token fails, naming both the "
     "composite and the call site",
     mkcase_d([APP_TOKEN_WITH], ['gh run view "$RUN_ID" --json headBranch']),
     True, ("wing-commander-probe", "Render", "w.yml :: work / Probe",
            "run view", "App token", "actions")),

    ("category D: the same composite bound to github.token in a job granting "
     "actions:read passes",
     mkcase_d([DEFAULT_TOKEN_WITH], ['gh run view "$RUN_ID" --json headBranch'],
              job_perms=ACTIONS_READ),
     False, ()),

    ("category D: the same call site through the published-stage path "
     "(./.wing-commander-pipeline/.github/actions/...) resolves to the same "
     "composite",
     mkcase_d([APP_TOKEN_WITH], ['gh run view "$RUN_ID" --json headBranch'],
              uses_path=PIPELINE_USES),
     True, ("wing-commander-probe", "run view", "App token", "actions")),

    ("category D: the inspected-run-identity split - a per-command "
     'GH_TOKEN="$ACTIONS_TOKEN" prefix bound to github.token (actions:read) '
     "for the Actions read, the step's App token for the issue read - passes",
     mkcase_d([APP_TOKEN_WITH, 'actions-token: ${{ github.token }}'],
              ['GH_TOKEN="$ACTIONS_TOKEN" gh run download "$RUN_ID" -p rec',
               'gh issue view "$N" --json labels'],
              env_lines=['ACTIONS_TOKEN: ${{ inputs.actions-token }}'],
              inputs=("token", "actions-token"), job_perms=ACTIONS_READ),
     False, ()),

    ("category D: ... and the split is what saves it: the same two reads with "
     "the prefix dropped fail on the Actions read only",
     mkcase_d([APP_TOKEN_WITH, 'actions-token: ${{ github.token }}'],
              ['gh run download "$RUN_ID" -p rec',
               'gh issue view "$N" --json labels'],
              env_lines=['ACTIONS_TOKEN: ${{ inputs.actions-token }}'],
              inputs=("token", "actions-token"), job_perms=ACTIONS_READ),
     True, ("run download", "App token", "actions")),

    ("category D: a token input the caller never passes and that has no "
     "default is unresolved - the call would run under an empty token",
     mkcase_d([], ['gh issue view "$N"']),
     True, ("could not resolve", "not passed at this call site")),

    ("category D: a token input the caller never passes falls back to its "
     "declared default (the metrics-persist shape: github.token, checked "
     "against the caller's job permissions)",
     mkcase_d([], ['gh run download "$RUN_ID" -p rec'],
              token_default="${{ github.token }}", job_perms=ACTIONS_READ),
     False, ()),

    ("category D: ... and that default is held to the caller's grant - the "
     "same composite in a job without actions:read fails",
     mkcase_d([], ['gh run download "$RUN_ID" -p rec'],
              token_default="${{ github.token }}", job_perms=ISSUES_WRITE),
     True, ("run download", "actions")),

    ("category D: a composite is checked once per call site - fine under the "
     "App token in one job, a failure under an under-granted github.token in "
     "another, and the failure names the second job",
     {".github/actions/wing-commander-probe/action.yml":
          composite_action(['gh issue comment "$N" --body hi']),
      ".github/workflows/w.yml":
          composite_caller_wf([APP_TOKEN_WITH])
          + composite_caller_job("second", [DEFAULT_TOKEN_WITH],
                                 job_perms="      issues: read\n"),
      "docs/setup.md": DOCS_OK},
     True, ("w.yml :: second / Probe", "issue comment", "issues")),

    ("category D: a composite that calls gh but no workflow uses fails "
     "loudly - no call site, no token to check",
     {".github/actions/wing-commander-orphan/action.yml":
          composite_action(['gh issue view "$N"']),
      ".github/workflows/w.yml": wf(step([APP_ENV], ['gh issue view "$N"'])),
      "docs/setup.md": DOCS_OK},
     True, ("wing-commander-orphan", "no workflow")),

    ("category D: a composite that makes no gh call needs no call site",
     {".github/actions/wing-commander-quiet/action.yml":
          composite_action(['echo "nothing to see"']),
      ".github/workflows/w.yml": wf(step([APP_ENV], ['gh issue view "$N"'])),
      "docs/setup.md": DOCS_OK},
     False, ()),

    ("category D: a gh call inside a _shared script fails - shared scripts "
     "run under whatever the sourcing composite exported",
     {".github/actions/_shared/helper.sh":
          '#!/usr/bin/env bash\ngh issue view "$N"\n',
      ".github/workflows/w.yml": wf(step([APP_ENV], ['gh issue view "$N"'])),
      "docs/setup.md": DOCS_OK},
     True, ("_shared/helper.sh", "shared script")),

    # --- gh api level: --method (#339) --------------------------------------
    # The composite walk brought metrics-persist's `gh api --method PATCH`
    # into scope, which the -X-only parser read as a PATH named `--method`
    # and silently dropped as out of scope. (An implicit POST — a body field
    # with no method — is Gate 28's subject, so there is no fixture for it
    # here: Gate 28 scans this file too and would reject the fixture text.)
    ("gh api --method PATCH is a write: under github.token with only "
     "issues:read it fails, naming issues",
     mkcase(ISSUES_READ, "", [DEFAULT_ENV],
            ['gh api --method PATCH "repos/$REPO/issues/comments/$ID" -F body=@f']),
     True, ("issues", "write")),

    ("gh api -X GET with a body field (a query parameter) stays a read",
     mkcase(CONTENTS_READ, "", [DEFAULT_ENV],
            ['gh api -X GET "repos/$REPO/contents/$P" -f ref="$BRANCH" --jq .content']),
     False, ()),

    ("the --method GET / --paginate combination stays a read and its path "
     "is still parsed (not mistaken for `--method`)",
     mkcase(ACTIONS_READ, "", [DEFAULT_ENV],
            ['gh api --method GET "repos/$REPO/actions/runs/$RUN_ID/jobs" --paginate']),  # wc-pagination-exempt: Gate 12 self-test fixture text (this repo's own no-filter shape, deliberately unfiltered to test Gate 12's own --method parsing), not a real invocation
     False, ()),

    ("... and under the App token that same --method GET Actions read fails, "
     "proving the path was seen",
     mkcase("", "", [APP_ENV],
            ['gh api --method GET "repos/$REPO/actions/runs/$RUN_ID/jobs" --paginate']),  # wc-pagination-exempt: Gate 12 self-test fixture text, not a real invocation
     True, ("actions", "App token")),

    # The method is read from THIS call's own executable arguments only
    # (review of #348): a `--method POST` in a trailing comment, inside a
    # quoted value, or in the next command on the same line is not this
    # call's method. Each of these is a read under a read-only grant and
    # must pass.
    ("gh api level: a `--method POST` in a trailing comment does not make "
     "the read a write",
     mkcase(ISSUES_READ, "", [DEFAULT_ENV],
            ['gh api "repos/$REPO/issues/$N" --jq .id   # writes use --method POST']),
     False, ()),

    ("gh api level: a `--method POST` inside a quoted argument does not make "
     "the read a write",
     mkcase(ISSUES_READ, "", [DEFAULT_ENV],
            ['gh api "repos/$REPO/issues/$N" --jq \'"--method POST"\'']),
     False, ()),

    ("gh api level: a `--method POST` in the NEXT command on the line does "
     "not make the read a write",
     mkcase(ISSUES_READ, "", [DEFAULT_ENV],
            ['gh api "repos/$REPO/issues/$N" --jq .id && echo "--method POST"']),
     False, ()),

    ("gh api level: ... while a write chained after the read is still "
     "checked as a write in its own right",
     mkcase(ISSUES_READ, "", [DEFAULT_ENV],
            ['gh api "repos/$REPO/issues/$N" --jq .id && gh api --method POST '
             '"repos/$REPO/issues" --input body.json']),
     True, ("issues", "write")),

    # Step-id namespaces (review of #348): `steps.<id>.outputs.token` names a
    # different step on the caller's side and on the composite's side. A
    # composite's own App mint must never vouch for a caller's unrelated
    # token that happens to share the id, and vice versa.
    ("category D: the composite mints its own App token under id `setup`; "
     "the caller passes ITS `steps.setup.outputs.token` from a non-App "
     "action - unverified, never classified App by the shared id",
     {".github/actions/wing-commander-probe/action.yml":
          composite_action(['gh issue comment "$N" --body hi'], mint_step_id="setup"),
      ".github/workflows/w.yml": (
          "name: w" + _N + "on:" + _N + "  workflow_dispatch: {}" + _N +
          "jobs:" + _N + "  work:" + _N + "    runs-on: ubuntu-latest" + _N +
          "    permissions:" + _N + "      issues: read" + _N +
          "    steps:" + _N +
          "      - name: not a mint" + _N + "        id: setup" + _N +
          "        uses: some-org/mint-a-different-token@v1" + _N +
          "      - name: Probe" + _N +
          "        uses: ./.github/actions/wing-commander-probe" + _N +
          "        with:" + _N +
          "          token: ${{ steps.setup.outputs.token }}" + _N),
      "docs/setup.md": DOCS_OK},
     False, ("unrecognised token", "Unverified")),

    ("category D: a composite's own App mint IS the App token for the "
     "composite's own env - held to the documented grant",
     {".github/actions/wing-commander-probe/action.yml":
          composite_action(['gh issue create --title t --body b'],
                           mint_step_id="mint",
                           token_env="${{ steps.mint.outputs.token }}"),
      ".github/workflows/w.yml": composite_caller_wf([]),
      "docs/setup.md": DOCS_ISSUES_READONLY},
     True, ("issue create", "App token", "issues")),

    ("category D: a token the CALLER mints in its own job and passes in is "
     "the App token on the caller's side - held to the documented grant",
     {".github/actions/wing-commander-probe/action.yml":
          composite_action(['gh issue create --title t --body b']),
      ".github/workflows/w.yml": (
          "name: w" + _N + "on:" + _N + "  workflow_dispatch: {}" + _N +
          "jobs:" + _N + "  work:" + _N + "    runs-on: ubuntu-latest" + _N +
          "    steps:" + _N +
          "      - name: mint" + _N + "        id: ctx2" + _N +
          "        uses: actions/create-github-app-token@v3" + _N +
          "      - name: Probe" + _N +
          "        uses: ./.github/actions/wing-commander-probe" + _N +
          "        with:" + _N +
          "          token: ${{ steps.ctx2.outputs.token }}" + _N),
      "docs/setup.md": DOCS_ISSUES_READONLY},
     True, ("issue create", "App token", "issues")),

    ("category D: ... and the caller's job env is the caller's namespace "
     "too - a composite step with no env of its own falls back to the "
     "caller job's GH_TOKEN, an App token minted in that job",
     {".github/actions/wing-commander-probe/action.yml":
          composite_action(['gh issue create --title t --body b']).replace(
              "      env:" + _N + "        GH_TOKEN: ${{ inputs.token }}" + _N, ""),
      ".github/workflows/w.yml": (
          "name: w" + _N + "on:" + _N + "  workflow_dispatch: {}" + _N +
          "jobs:" + _N + "  work:" + _N + "    runs-on: ubuntu-latest" + _N +
          "    env:" + _N + "      GH_TOKEN: ${{ steps.ctx2.outputs.token }}" + _N +
          "    steps:" + _N +
          "      - name: mint" + _N + "        id: ctx2" + _N +
          "        uses: actions/create-github-app-token@v3" + _N +
          "      - name: Probe" + _N +
          "        uses: ./.github/actions/wing-commander-probe" + _N),
      "docs/setup.md": DOCS_ISSUES_READONLY},
     True, ("issue create", "App token", "issues")),
]


def main():
    if not os.path.isfile(LINT_WORKFLOW):
        sys.exit(f"::error::run this from the repository root; {LINT_WORKFLOW} not found.")

    gate_src = extract_gate_step(STEP_PREFIX)
    root = tempfile.mkdtemp(prefix="verify_gate12_")
    gate_path = os.path.join(root, "gate12.py")
    io.open(gate_path, "w", encoding="utf-8").write(gate_src)

    failures = []
    try:
        for name, files, expect_fail, must_mention in CASES:
            case_dir = tempfile.mkdtemp(prefix="case_", dir=root)
            for relpath, body in files.items():
                full = os.path.join(case_dir, *relpath.split("/"))
                os.makedirs(os.path.dirname(full), exist_ok=True)
                io.open(full, "w", encoding="utf-8").write(body)

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
        print(f"::error file={LINT_WORKFLOW}::Gate 12 self-test: "
              f"{len(failures)} of {len(CASES)} scenarios behaved wrongly. Gate "
              f"12's detection logic does not do what its name claims, so a "
              f"green Gate 12 on the real fleet means nothing.")
        return 1
    print(f"Gate 12 self-test: all {len(CASES)} scenarios behaved as expected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
