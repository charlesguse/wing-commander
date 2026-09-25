#!/usr/bin/env python3
"""Gate 93 — board-loop.yml's agent steps read the issue only through
wing-commander-issue-context, and nothing re-implements its trust filter.

WHY THIS EXISTS
----------------
#499 code review, round 3 (B1, blocking): board-loop.yml's route stage
was granted `Bash(gh issue view:*)` and told to run
`gh issue view N --comments` directly, reading every comment on a public
issue unfiltered, then flowing pr-title/pr-body into
`gh issue create --label spec-request` -- a public commenter could reach
write-capable intake through a bot-authored issue body, bypassing
intake.yml's own comment-trust-gate (specs/029-intake-issue-comments) and,
in spirit, FR-056 (specs/057-autonomous-board-loop: comment selection MUST
be decided in code by author association, never by asking the agent to
ignore the rest). The fix (this same PR) moved that filter into
`wing-commander-issue-context` (`.github/actions/`), the single home both
intake.yml and board-loop.yml now consume, and removed every
`Bash(gh issue view:*)`/`Bash(gh api...)` grant board-loop.yml's agent
steps had. This gate is what keeps both true after the next edit.

WHAT IT CHECKS
--------------
1. tool-grant: every `Bash(...)` grant reachable by a board-loop.yml agent
   step -- from a `wing-commander-tool-args` call site's
   `default-allowed-tools`/`extra-allowed-tools`/`allowed-tools-override`
   inputs, AND from each `claude-code-action` step's own `claude_args`
   text (a literal grant can be appended there directly, e.g.
   `--allowedTools "${{ steps.tool-args-x.outputs.allowed-tools
   }},Bash(gh issue view:*)"`, bypassing the composite entirely -- #499
   round 4 review) -- is parsed into its `gh` command tokens and checked
   against a forbidden-prefix list, not a substring: `gh` bare (any of
   Claude Code's equivalent open-wildcard spellings -- `gh:*`, `gh*`,
   `gh *` -- authorizes every gh subcommand; #499 round 5 review: the
   round-4 fix only stripped a trailing `:*`, so `gh*`/`gh *` still slipped
   through), `gh issue *`, `gh api*`, `gh search issues*`, and `gh pr *`.
   A bare `Bash` (no argument at all) or `Bash(*)` grant is ALSO forbidden
   here, for the same reason -- it authorizes every gh subcommand too,
   among everything else. Prefix matching on whitespace-split tokens closes the
   substring check's own holes (`Bash(gh issue:*)`, `Bash(gh:*)` both
   slipped through the old `"gh issue view" in value` test).
   `gh pr *` joined the list with #503: `gh pr view N --comments` returns
   every PR comment unfiltered (FR-056), and the reviewer that held
   `Bash(gh pr view:*)` feeds review-fixup, which commits. The reviewer
   now reads files its job's gather step stages (check 5). Scoped to
   board-loop.yml only: intake.yml legitimately grants its own agent
   `Bash(gh issue view:*)` for title/body (it never grants comment access
   that way -- comments are staged, code-filtered, by the same composite),
   and this gate is not the place to relitigate that design.
2. single-home: no file other than
   `.github/actions/wing-commander-issue-context/action.yml` may contain
   all three fragments unique to its trust-filter idiom together --
   `select(.user.type != "Bot")`, a paginated fetch of an issue's
   `/comments` endpoint, and the `"## Comment by @` staging template.
   Individually each fragment is generic (`--paginate` and
   `author_association` checks exist all over this repository for
   unrelated purposes -- comment-reply triggers, PR review gating,
   auto-release's own actor check); this gate matches only their
   co-occurrence in one file, the same "literal fragments unique to the
   idiom, checked together" methodology Gate 60
   (verify-single-home-idioms.py) uses for its own idioms.

3. spec-request-body (board-loop run 36044831201: route-propose returned
   `category=spec` with no `pr-body`, and spec-request #509's whole body
   was "No drafted body." and a link). Every step in board-loop.yml whose
   `run:` files a spec-request (`gh issue create ... spec-request`) must:
   - pass `--body-file "$F"` and never `--body`/`-b`, so the body cannot
     be an inline string that skips the builder;
   - write `$F` with `.github/scripts/board_spec_request_body.py
     ... --out "$F"` (the single home for the body and its fallback);
   - give that builder `--context-file "$V"`, where the step's `env:`
     maps `V` to exactly `${{ steps.ID.outputs.context-file }}` and `ID`
     is an EARLIER step in the SAME job whose `uses:` is
     wing-commander-issue-context -- so the fallback reads the
     composite's trust-filtered file and nothing else (not its
     `comments-file`, not a path of the step's own making);
   - never reassign that variable in its `run:` before the builder call
     (`V=...`, `read V`, `printf -v V`, `export`/`declare`/`unset V`,
     `for V in`);
   - gate that fetch step so it runs whenever the site does: no `if:`
     at all, or exactly the site's own `if:` (`if: false`, or any
     narrower condition, fails);
   - feed `--drafted-body-file`, if passed, a literal path written only
     by one `jq ... .proposal["pr-body"] ... > PATH` line;
   - make no issue read of its own: no `gh api` of any kind (REST or
     graphql), and no `gh issue view` other than
     `$(gh issue view N -R REPO --json title --jq .title)` (FR-056 --
     the spec-request body feeds intake);
   - capture the new issue's URL (`V="$(gh issue create ...)"`) and guard
     it with `[[ "$V" =~ RE ]] || { echo "::error::..."; exit N; }` (or
     `[ -n "$V" ]`), N >= 1, RE anchored `^` and ending
     `/issues/[0-9]+$` (so `.*` cannot pass an empty URL), before
     anything else touches `$V` or the
     issue: no `gh issue comment/edit/close/reopen`, `gh pr comment/
     edit`, `gh label` or `$GITHUB_OUTPUT` write may come first, and the
     guard's own failure branch may do none of them (#514: these steps
     run without `-e`, so a failed create still posted the re-route
     comment, added board:stalled and cross-linked an empty URL);
   - not be `continue-on-error`, and no later step in the job that reads
     the site's outputs may be gated `always()`/`!cancelled()`/
     `failure()` -- a failed create fails the job and leaves the issue
     without board:stalled, so a later run retries it.
   `gh issue edit --add-label spec-request` is also flagged: relabelling
   an existing issue would file a spec-request whose body never went
   through the builder. So is any `gh issue create` in board-loop.yml
   whose `--label` comes through a variable: the check cannot tell
   whether that files a spec-request, so it fails closed. The check fails
   on zero sites too, so a rename of the label or the command cannot turn
   it vacuous. The builder's own behaviour (fallback order, the "No
   drafted body." line, a fence no content can close around both the
   drafted body and the context, so @mentions, #N references, links,
   images and HTML stay inert (#548), truncation under 65536 characters
   with a visible note) is exercised by `--self-test`, and each
   BUILDER_MUTATIONS rewrite of the builder (the draft unfenced, the
   fence no longer sized from the content, long backtick runs no longer
   split so the fence passes cmark-gfm's 255 cap) must be caught.

4. read-only-git (#513). triage-propose, route-propose and the reviewer
   are read-only, but were granted `Bash(git log:*)`/`Bash(git diff:*)`/
   `Bash(git show:*)`, and all three subcommands take `--output=<path>`:
   `git log -1 --format=format:X --output=/any/path` writes a file, and
   Claude Code's prefix allow rule permits it (checked with 2.1.282 in
   `-p` mode). A deny rule for `--output` would have to list every form
   the option can take, so it is not used. Instead, each read-only
   tool-args site (the three labels in READ_ONLY_STEP_LABELS, plus any
   site whose allowed list has neither Write nor Edit) must:
   - grant no Bash command other than READ_ONLY_BASH_GRANTS. Raw git in
     any spelling (`git log:*`, `git *`, `/usr/bin/git show:*`) is named
     as such; the git grant is `Bash(python3 .github/scripts/
     git_read.py:*)`, a wrapper that runs only log/diff/show and
     refuses `--output` and every prefix of it, and `-o`;
   - grant that wrapper, and name it in the prompt of the agent step it
     feeds by exactly the granted path (every `...git_read.py` token in
     the prompt must be that path), and not tell the agent to run raw
     `git log`/`git diff`/`git show`;
   - allow no Write/Edit/MultiEdit/NotebookEdit;
   - deny `Bash(git:*)` (so plain git, which Claude Code otherwise runs
     as a built-in read-only command, is not a second path), plus Write
     and Edit (Claude Code refuses a `>`/`>>` redirect because Edit is
     denied).
   The agent step fed by such a site may not append a Bash grant to its
   own `--allowedTools` outside that list, and must pass the site's
   disallowed-tools output. It also may not switch the checks off or
   work around the lists: no `--dangerously-skip-permissions`, no
   `--permission-mode` other than `default`, no `--settings` flag at all
   (its value can be a file this gate cannot read), and no `settings:`
   input on the action step that carries `permissions` or is not inline
   JSON. The check fails if a label is missing, so a
   rename cannot make it pass without checking anything. Since #503 the
   list holds only the wrapper and `cat`: a read-only agent gets no `gh`
   command at all.

   4b. read-only-git across the fleet (#518). The same hole was open in
   implement.yml's progress composer, watchdog.yml's diagnose and
   pr-conversation.yml's classify. Every other workflow is now checked
   with the git half of check 4: each read-only tool-args site (the
   labels in FLEET_READ_ONLY_STEP_LABELS, plus any site whose shipped
   allowed list has neither Write nor Edit) must grant no raw
   `Bash(git ...)` (nor bare `Bash`/`Bash(*)`), allow no write tool,
   deny `Bash(git:*)`, Write and Edit, and its agent step must pass the
   deny list, keep permission checks on, and name the wrapper in its
   prompt by the granted path. A listed site must grant the wrapper.
   Other Bash grants (`gh ...`) are not this check's business outside
   board-loop.yml. The wrapper is the one file .github/scripts/
   git_read.py; a published stage (workflow_call) reaches it through
   its pipeline checkout, so its grant is `Bash(python3
   .wing-commander-pipeline/.github/scripts/git_read.py:*)`, and a
   grant of the repo-local path there (a file a consumer's tree does not
   have) fails. `${{ inputs.* }}` values (a consumer's own
   extra/override lists) are ignored; the shipped defaults are checked.

5. reviewer-staged-inputs (#503). The reviewer prompt named
   `${{ github.workspace }}/../board-review-diff.txt` while its gather
   step wrote `$RUNNER_TEMP/board-review-diff.txt` (runner.temp is
   /home/runner/work/_temp, not the workspace's parent), so the reviewer
   was pointed at a missing file and fell back to `gh pr view`. In the
   job whose agent step is fed by the `board-loop.reviewer` tool-args
   site, the step with id `gather` must start `set -euo pipefail`, fail
   (`if [ ! -s PATH ]; then ... exit 1`) on an empty diff -- an empty
   diff makes the reviewer find nothing and readiness run on an
   unreviewed PR -- and write each file it stages exactly once, to a
   literal path under /tmp/wing-commander/. Every prompt token ending in
   one of those files' basenames must be that exact path, so a prompt
   naming `${{ runner.temp }}/board-review-pr.md` fails as the workspace-
   parent diff path did. Every /tmp/wing-commander/ path the prompt names
   must be one the gather step writes, and the prompt must not tell the
   agent to run `gh`.

`--self-test`: synthetic tempdir fixtures prove each check can fail (a
board-loop tool-args grant carrying `gh issue view`, a second file
re-implementing all three trust-filter fragments, and spec-request
creation steps that bypass the builder, feed it the wrong file, or read
the issue unfiltered, and read-only agents granted raw git or missing a
deny), unit-test board_spec_request_body.py and git_read.py, run
mutation checks (each mutation of the real board-loop.yml's spec-request
sites and read-only tool grants, and of the other workflows' read-only
git grants and prompts, must be caught), and confirm the real
fleet passes.
"""
import glob
import os
import re
import sys
import tempfile

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_shell_harness import use_utf8_stdout  # noqa: E402
from wc_published_stages import published_stages  # noqa: E402

BOARD_LOOP = ".github/workflows/board-loop.yml"
ISSUE_CONTEXT_ACTION = ".github/actions/wing-commander-issue-context/action.yml"
TOOL_ARGS_USES = "wing-commander-tool-args"
AGENT_ACTION_PREFIX = "anthropics/claude-code-action@"

# Each entry is the whitespace-split token prefix a `Bash(gh ...)` grant's
# command must NOT start with (checked against multi-token commands only
# -- a bare `gh:*` grant, with no subcommand argument at all, is checked
# separately below since it is not a "prefix" of anything, it authorizes
# every gh subcommand outright, including these four). `gh pr` is here
# because `gh pr view N --comments` reads PR comments unfiltered (#503).
FORBIDDEN_GH_PREFIXES = (
    ("gh", "issue"),
    ("gh", "api"),
    ("gh", "search", "issues"),
    ("gh", "pr"),
)

BASH_GRANT_RE = re.compile(r"Bash\(([^)]*)\)")
# A bare `Bash` grant, no argument and no parens at all -- authorizes
# every shell command, including any gh subcommand. Matched only where a
# comma or the string boundary follows, so it never matches the "Bash" in
# "Bash(...)" (the parenthesized form is handled by BASH_GRANT_RE above).
BARE_BASH_RE = re.compile(r"(?<![\w-])Bash(?!\()(?![\w-])")

TRUST_FILTER_FRAGMENTS = (
    re.compile(r'select\(\s*\.user\.type\s*!=\s*"Bot"\s*\)'),
    re.compile(r"--paginate[^\n]{0,200}/comments|/comments[^\n]{0,200}--paginate"),
    re.compile(r'"## Comment by @'),
)


def _find_steps_by_uses(doc, needle):
    """Yield every step dict in a parsed workflow whose `uses:` contains
    `needle`, under any checkout path or job nesting."""
    steps = []

    def walk(node):
        if isinstance(node, dict):
            uses = node.get("uses")
            if isinstance(uses, str) and needle in uses:
                steps.append(node)
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(doc)
    return steps


def find_tool_args_steps(doc):
    return _find_steps_by_uses(doc, TOOL_ARGS_USES)


def find_agent_steps(doc):
    """Every step whose `uses:` pins claude-code-action, at any ref."""
    steps = []
    for step in _find_steps_by_uses(doc, "anthropics/claude-code-action@"):
        uses = str(step.get("uses") or "").strip()
        if uses.startswith(AGENT_ACTION_PREFIX):
            steps.append(step)
    return steps


def find_forbidden_gh_grants(text):
    """Every forbidden grant in `text`: a `Bash(...)` grant whose gh
    command matches one of FORBIDDEN_GH_PREFIXES, by whitespace-split
    token prefix -- not by substring, which a `Bash(gh issue:*)` or bare
    `Bash(gh:*)` grant (#499 round 4 review) slips past -- plus a bare
    `Bash`/`Bash(*)` grant (unrestricted, authorizes every gh subcommand
    among everything else; #499 round 5 review). Returns a list of
    ready-to-print descriptions, one per match -- the caller does not
    reconstruct or re-wrap them."""
    hits = []
    for m in BASH_GRANT_RE.finditer(text or ""):
        inner = m.group(1).strip()
        # Strip a trailing ":*" wildcard suffix (the ":" separates the
        # command from its argument wildcard, e.g. "gh issue view:*"),
        # THEN strip any trailing bare "*" too, repeatedly -- Claude Code
        # accepts "gh:*", "gh*" and "gh *" as equivalent open-wildcard
        # spellings (#499 round 5 review: the round-4 fix only handled the
        # first), and all three must collapse to the same "gh" this
        # function already treats as fully open below.
        command = inner.split(":", 1)[0].strip()
        while command.endswith("*"):
            command = command[:-1].rstrip()
        tokens = tuple(command.split())
        if not tokens:
            # The wildcard was the entire grant -- Bash(*).
            hits.append(f"Bash({inner}) (unrestricted -- authorizes every "
                       f"shell command, including any gh subcommand)")
            continue
        if tokens[0] != "gh":
            continue
        if len(tokens) == 1:
            # A bare "gh" command (Bash(gh:*)/Bash(gh*)/Bash(gh *))
            # authorizes every gh subcommand outright, including the
            # three forbidden ones.
            hits.append(f"Bash({inner})")
            continue
        for prefix in FORBIDDEN_GH_PREFIXES:
            if tokens[:len(prefix)] == prefix:
                hits.append(f"Bash({inner})")
                break

    for _m in BARE_BASH_RE.finditer(text or ""):
        hits.append("a bare Bash grant (unrestricted, no argument at all "
                    "-- authorizes every shell command, including any gh "
                    "subcommand)")
    return hits


def check_tool_grants(path):
    """Gate 93 check 1: no board-loop.yml agent step may be granted
    `gh`/`gh issue`/`gh api`/`gh search issues`/`gh pr`, whether through a
    wing-commander-tool-args call site's inputs or appended literally
    inside an agent step's own claude_args text."""
    problems = []
    try:
        with open(path, encoding="utf-8") as fh:
            doc = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        return [f"{path}: could not parse as YAML ({exc})"]
    if not isinstance(doc, (dict, list)):
        return problems

    for step in find_tool_args_steps(doc):
        name = step.get("name") or step.get("id") or "(unnamed step)"
        with_block = step.get("with") or {}
        if not isinstance(with_block, dict):
            continue
        for key in ("default-allowed-tools", "extra-allowed-tools",
                    "allowed-tools-override"):
            value = str(with_block.get(key) or "")
            for description in find_forbidden_gh_grants(value):
                problems.append(
                    f"{path}: step {name!r}'s {key} grants "
                    f"{description} to a board-loop agent -- read the "
                    f"issue through wing-commander-issue-context instead "
                    f"(single home for the trust filter; #499), and a PR "
                    f"through files the job stages (#503).")

    for step in find_agent_steps(doc):
        name = step.get("name") or step.get("id") or "(unnamed step)"
        with_block = step.get("with") or {}
        if not isinstance(with_block, dict):
            continue
        claude_args = str(with_block.get("claude_args") or "")
        for description in find_forbidden_gh_grants(claude_args):
            problems.append(
                f"{path}: agent step {name!r}'s claude_args grants "
                f"{description} directly -- read the issue through "
                f"wing-commander-issue-context instead (single home for "
                f"the trust filter; #499), and a PR through files the "
                f"job stages (#503).")
    return problems


# The one copy of the wrapper (#518 moved it from board_git_read.py).
# board-loop.yml runs in this repository's own checkout and reaches it at
# GIT_READ_WRAPPER; a published stage (workflow_call) runs in the
# consumer's tree with the pipeline checked out at PIPELINE_CHECKOUT, so
# its agents reach the same file at PUBLISHED_GIT_READ_WRAPPER.
GIT_READ_WRAPPER = ".github/scripts/git_read.py"
GIT_READ_GRANT = f"Bash(python3 {GIT_READ_WRAPPER}:*)"
PIPELINE_CHECKOUT = ".wing-commander-pipeline"
PUBLISHED_GIT_READ_WRAPPER = f"{PIPELINE_CHECKOUT}/{GIT_READ_WRAPPER}"
PUBLISHED_GIT_READ_GRANT = f"Bash(python3 {PUBLISHED_GIT_READ_WRAPPER}:*)"
RAW_GIT_DENY = "Bash(git:*)"
# Any token naming the wrapper, by whatever path. Each one in a read-only
# agent's prompt must be exactly the path its grant names.
WRAPPER_TOKEN_RE = re.compile(r"[^\s`'\"(]*" + re.escape(
    os.path.basename(GIT_READ_WRAPPER)))
# A prompt telling the agent to run raw git log/diff/show: at the start of
# a line or right after an opening backtick.
PROMPT_RAW_GIT_RE = re.compile(r"(?:^[ \t]*|`)git\s+(?:log|diff|show)\b",
                               re.MULTILINE)
# A consumer's own extra/override tool lists: not shipped, not checked.
CONSUMER_INPUT_RE = re.compile(r"\$\{\{\s*inputs\.[A-Za-z0-9_-]+\s*\}\}")
# The only Bash grants a read-only board-loop agent may hold. Each one was
# checked to write nothing: the wrapper refuses git's --output (#513);
# `cat` has no write option, and Claude Code denies a `>`/`>>` redirect
# when Edit is denied (checked with 2.1.282). A new grant goes here only
# after the same check. No `gh` command belongs here: `gh pr view N
# --comments` returns every PR comment unfiltered (FR-056), so a read-only
# agent reads the PR from files its job stages instead (#503).
READ_ONLY_BASH_GRANTS = (GIT_READ_GRANT, "Bash(cat:*)")
# The agent steps that must stay read-only. Any other tool-args site whose
# allowed list has neither Write nor Edit is held to the same rules.
READ_ONLY_STEP_LABELS = ("board-loop.triage-propose",
                         "board-loop.route-propose", "board-loop.reviewer")
# Check 4b (#518): the read-only agent steps outside board-loop.yml that
# read git, by workflow. Each must grant the wrapper. Any other site
# whose shipped allowed list has neither Write nor Edit is checked too.
FLEET_READ_ONLY_STEP_LABELS = {
    ".github/workflows/implement.yml": ("implement.post-progress-comment",),
    ".github/workflows/pr-conversation.yml": ("pr-conversation.classify",),
    ".github/workflows/watchdog.yml": ("watchdog.diagnose",),
}
WRITE_TOOLS = ("Write", "Edit", "MultiEdit", "NotebookEdit")
TOOL_ARGS_OUTPUT_RE = re.compile(
    r"steps\.([A-Za-z0-9_-]+)\.outputs\.(allowed|disallowed)-tools")
# The value of a claude_args `--allowedTools`/`--allowed-tools` flag, quoted
# or not (unquoted: the rest of the line, so `${{ ... }},Bash(x)` is seen
# whole). Only allow flags are scanned: a literal deny is not a grant.
ALLOWED_TOOLS_ARG_RE = re.compile(
    r"--allowed(?:Tools|-tools)(?:=|[ \t]+)(\"[^\"]*\"|'[^']*'|[^\n]*)")


def _tool_names(value):
    """The comma-separated entries of a tool list, with each `Bash(...)`
    grant kept whole even if it holds a comma."""
    text = str(value or "")
    names = [m.group(0) for m in BASH_GRANT_RE.finditer(text)]
    rest = BASH_GRANT_RE.sub("", text)
    names.extend(p.strip() for p in rest.split(",") if p.strip())
    return names


def _bash_grant_problems(text, where, git_grant=GIT_READ_GRANT, strict=True):
    """Problems with the Bash grants in `text` for a read-only agent whose
    git grant is `git_grant`. `strict` (board-loop.yml, check 4) allows
    only that grant and `cat`; otherwise (check 4b) only git is checked:
    no raw git in any spelling, no unrestricted Bash, and the wrapper by
    no other path."""
    problems = []
    allowed = (git_grant, "Bash(cat:*)") if strict else (git_grant,)
    for m in BASH_GRANT_RE.finditer(text or ""):
        grant = m.group(0)
        if grant in allowed:
            continue
        command = m.group(1).split(":", 1)[0].strip().rstrip("* ")
        tokens = command.split()
        if tokens and os.path.basename(tokens[0]) == "git":
            problems.append(
                f"{where} grants raw {grant} to a read-only agent. git "
                f"log/diff/show take --output=<path>, which writes a file, "
                f"and an allow rule does not stop it (#513). Grant "
                f"{git_grant} instead.")
        elif not tokens:
            problems.append(
                f"{where} grants unrestricted {grant} to a read-only agent, "
                f"which includes raw git (#513).")
        elif WRAPPER_TOKEN_RE.search(command):
            problems.append(
                f"{where} grants {grant}, which is not this workflow's git "
                f"wrapper grant {git_grant}: the agent would be pointed at "
                f"a path its job does not run the wrapper from (#518).")
        elif not strict:
            continue
        elif tokens and os.path.basename(tokens[0]) == "gh":
            problems.append(
                f"{where} grants {grant} to a read-only agent. `gh pr view "
                f"--comments` and its kin return comments from anyone, "
                f"unfiltered (FR-056); stage what the agent needs as a "
                f"file in a deterministic step instead (#503).")
        else:
            problems.append(
                f"{where} grants {grant} to a read-only agent, which is "
                f"not in this gate's READ_ONLY_BASH_GRANTS. Check that it "
                f"cannot write a file, then add it there (#513).")
    if BARE_BASH_RE.search(text or ""):
        problems.append(f"{where} grants bare Bash to a read-only agent "
                        f"(#513).")
    return problems


SKIP_PERMISSIONS_RE = re.compile(r"--(?:allow-)?dangerously-skip-permissions")
PERMISSION_MODE_RE = re.compile(
    r"--permission-mode(?:=|[ \t]+)(\"[^\"]*\"|'[^']*'|\S+)")
SETTINGS_FLAG_RE = re.compile(r"--settings(?![\w-])")


def _permission_bypass_problems(claude_args, settings_input, where):
    """A read-only agent step must not turn permission checks off or add
    rules around the composite's lists: no --dangerously-skip-permissions,
    no --permission-mode other than `default`, no --settings flag (its
    value can be a file this gate cannot read, so any use is refused), and
    no `settings:` input that carries `permissions` or is not inline JSON
    (a path cannot be read here either)."""
    problems = []
    if SKIP_PERMISSIONS_RE.search(claude_args):
        problems.append(f"{where} passes --dangerously-skip-permissions to a "
                        f"read-only agent, which turns every tool check off "
                        f"(#513).")
    for m in PERMISSION_MODE_RE.finditer(claude_args):
        mode = m.group(1).strip("\"'")
        if mode != "default":
            problems.append(f"{where} sets --permission-mode {mode} on a "
                            f"read-only agent; only `default` keeps the "
                            f"allow/deny lists in force (#513).")
    if SETTINGS_FLAG_RE.search(claude_args):
        problems.append(f"{where} passes --settings to a read-only agent. "
                        f"Settings can carry a permissions allow list that "
                        f"this gate cannot see (#513).")
    if settings_input is not None:
        text = str(settings_input).strip()
        if "permissions" in text or not text.startswith("{"):
            problems.append(
                f"{where}: the step's `settings:` input carries "
                f"permissions, or is not inline JSON this gate can read "
                f"(#513).")
    return problems


def _shipped(value):
    """A tool-list input as shipped: a consumer's own `${{ inputs.* }}`
    list is theirs to set, not this gate's to check."""
    return CONSUMER_INPUT_RE.sub("", str(value or ""))


def check_read_only_git(path, labels=READ_ONLY_STEP_LABELS,
                        git_grant=GIT_READ_GRANT, strict=True):
    """Gate 93 check 4 (#513) and, with strict=False, check 4b (#518): a
    read-only agent gets no raw `Bash(git ...)` grant (strict: and no Bash
    grant but the wrapper and `cat`), has `Bash(git:*)`, Write and Edit
    denied, and no write tool allowed, through the tool-args composite or
    its own claude_args. A site in `labels` must grant `git_grant`, and
    the prompt of an agent step fed a wrapper grant must name the wrapper
    by the granted path and never tell the agent to run raw git."""
    problems = []
    check = "check 4" if strict else "check 4b"
    wrapper_path = BASH_GRANT_RE.match(git_grant).group(1).split(":", 1)[0]
    wrapper_path = wrapper_path.split(None, 1)[1].strip()
    try:
        with open(path, encoding="utf-8") as fh:
            doc = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        return [f"{path}: could not parse as YAML ({exc})"]
    except OSError as exc:
        return [f"{path}: could not read ({exc}) -- {check} found nothing "
                f"to check."]
    if not isinstance(doc, (dict, list)):
        return [f"{path}: not a workflow -- {check} found nothing to check."]

    read_only_ids = set()
    wrapper_ids = set()
    labels_seen = set()
    for step in find_tool_args_steps(doc):
        with_block = step.get("with") or {}
        if not isinstance(with_block, dict):
            continue
        label = str(with_block.get("step-label") or "")
        override = _shipped(with_block.get("allowed-tools-override"))
        allowed_values = ([override] if override and override.strip() else
                          [_shipped(with_block.get("default-allowed-tools")),
                           _shipped(with_block.get("extra-allowed-tools"))])
        allowed = [n for v in allowed_values for n in _tool_names(v)]
        if (label not in labels
                and any(t in allowed for t in ("Write", "Edit"))):
            continue
        labels_seen.add(label)
        if step.get("id"):
            read_only_ids.add(str(step["id"]))
            if git_grant in allowed:
                wrapper_ids.add(str(step["id"]))
        where = f"{path}: step {step.get('name') or label!r}"
        for value in allowed_values:
            problems.extend(_bash_grant_problems(value, where, git_grant,
                                                 strict))
        if label in labels and git_grant not in allowed:
            problems.append(
                f"{where} does not grant {git_grant}; this read-only agent "
                f"reads git history only through that wrapper (#518).")
        for tool in WRITE_TOOLS:
            if tool in allowed:
                problems.append(f"{where} allows {tool} to a read-only "
                                f"agent (#513).")
        d_override = _shipped(with_block.get("disallowed-tools-override"))
        disallowed = _tool_names(
            d_override if d_override and d_override.strip() else
            f"{_shipped(with_block.get('default-disallowed-tools'))},"
            f"{_shipped(with_block.get('extra-disallowed-tools'))}")
        for needed in (RAW_GIT_DENY, "Write", "Edit"):
            if needed not in disallowed:
                problems.append(
                    f"{where} does not deny {needed} to a read-only agent. "
                    f"{RAW_GIT_DENY} keeps plain git from being a second "
                    f"way around {wrapper_path}; Write and Edit being "
                    f"denied is what makes Claude Code refuse a `>` "
                    f"redirect (#513).")

    for label in labels:
        if label not in labels_seen:
            problems.append(
                f"{path}: no tool-args step labelled {label!r} -- {check} "
                f"would pass without checking it. If it was renamed, "
                f"update READ_ONLY_STEP_LABELS/FLEET_READ_ONLY_STEP_LABELS.")

    for step in find_agent_steps(doc):
        with_block = step.get("with") or {}
        if not isinstance(with_block, dict):
            continue
        claude_args = str(with_block.get("claude_args") or "")
        refs = {m.group(1) for m in TOOL_ARGS_OUTPUT_RE.finditer(claude_args)}
        ids = refs & read_only_ids
        if not ids:
            continue
        name = step.get('name') or step.get('id')
        where = f"{path}: agent step {name!r}'s claude_args"
        for m in ALLOWED_TOOLS_ARG_RE.finditer(claude_args):
            problems.extend(_bash_grant_problems(m.group(1), where,
                                                 git_grant, strict))
        problems.extend(_permission_bypass_problems(
            claude_args, with_block.get("settings"), where))
        for tool_id in sorted(ids):
            if f"steps.{tool_id}.outputs.disallowed-tools" not in claude_args:
                problems.append(
                    f"{where} does not pass steps.{tool_id}.outputs."
                    f"disallowed-tools, so {RAW_GIT_DENY}/Write/Edit are not "
                    f"denied (#513).")
        prompt = str(with_block.get("prompt") or "")
        where = f"{path}: agent step {name!r}'s prompt"
        for m in PROMPT_RAW_GIT_RE.finditer(prompt):
            problems.append(
                f"{where} tells a read-only agent to run raw "
                f"{m.group(0).strip(' `')!r}, which its tools deny; name "
                f"`python3 {wrapper_path}` instead (#518).")
        if ids & wrapper_ids:
            tokens = WRAPPER_TOKEN_RE.findall(prompt)
            if f"python3 {wrapper_path}" not in prompt:
                problems.append(
                    f"{where} never tells the agent to run "
                    f"`python3 {wrapper_path}`, the git wrapper it is "
                    f"granted (#518).")
            for token in sorted(set(tokens) - {wrapper_path}):
                problems.append(
                    f"{where} names the git wrapper as {token!r}, but the "
                    f"agent is granted it only as {wrapper_path} (#518).")

    if not os.path.isfile(GIT_READ_WRAPPER):
        problems.append(f"{GIT_READ_WRAPPER} is missing, but read-only "
                        f"agents are granted it.")
    return problems


def fleet_git_grant(path, published):
    """The wrapper grant a workflow's read-only agents must hold: through
    the pipeline checkout for a published stage, repo-local otherwise."""
    return PUBLISHED_GIT_READ_GRANT if path in published else GIT_READ_GRANT


def check_fleet_read_only_git(root="."):
    """Gate 93 check 4b (#518): check 4's git rules for every workflow
    other than board-loop.yml (which check 4 holds to the strict list)."""
    problems = []
    published = set(published_stages(root))
    base = os.path.join(root, ".github", "workflows")
    paths = sorted(glob.glob(os.path.join(base, "*.yml"))
                   + glob.glob(os.path.join(base, "*.yaml")))
    rel_paths = []
    for full in paths:
        rel = os.path.relpath(full, root).replace(os.sep, "/")
        rel_paths.append(rel)
        if rel == BOARD_LOOP:
            continue
        problems.extend(check_read_only_git(
            full, labels=FLEET_READ_ONLY_STEP_LABELS.get(rel, ()),
            git_grant=fleet_git_grant(rel, published), strict=False))
    for rel in FLEET_READ_ONLY_STEP_LABELS:
        if rel not in rel_paths:
            problems.append(f"{rel} is missing, but FLEET_READ_ONLY_STEP_"
                            f"LABELS names read-only agents in it -- check "
                            f"4b would pass without checking them.")
    return problems


REVIEWER_LABEL = "board-loop.reviewer"
REVIEW_GATHER_ID = "gather"
REVIEW_DIFF_BASENAME = "board-review-diff.txt"
STAGING_DIR = "/tmp/wing-commander/"
# A redirect target in the gather step's `run:` -- `> path`, `>> path`,
# quoted or not.
REDIRECT_TARGET_RE = re.compile(r">>?\s*(\"[^\"]+\"|'[^']+'|[^\s;|&]+)")
STAGED_PATH_RE = re.compile(r"/tmp/wing-commander/[\w./-]*[\w-]")
PROMPT_DIFF_PATH_RE = re.compile(
    r"[^\s`'\"(]*" + re.escape(REVIEW_DIFF_BASENAME))
PROMPT_GH_RE = re.compile(r"(?<![\w-])gh\s+(?:pr|issue|api|search)\b")


def check_reviewer_staged_inputs(path):
    """Gate 93 check 5 (#503): the job's gather step runs under
    `set -euo pipefail`, fails on an empty diff, and writes each staged
    file exactly once to a literal /tmp/wing-commander path; every prompt
    token ending in one of those files' basenames is that exact path;
    every staged path the prompt names is written there; and the prompt
    never tells the agent to run gh."""
    try:
        with open(path, encoding="utf-8") as fh:
            doc = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        return [f"{path}: could not parse as YAML ({exc})"]
    jobs = doc.get("jobs") if isinstance(doc, dict) else None
    if not isinstance(jobs, dict):
        return [f"{path}: no jobs -- check 5 found nothing to check."]

    found = []
    for job_name, job in jobs.items():
        steps = job.get("steps") if isinstance(job, dict) else None
        if not isinstance(steps, list):
            continue
        tool_ids = set()
        for step in steps:
            if not isinstance(step, dict):
                continue
            with_block = step.get("with") or {}
            if (TOOL_ARGS_USES in str(step.get("uses") or "")
                    and isinstance(with_block, dict)
                    and with_block.get("step-label") == REVIEWER_LABEL
                    and step.get("id")):
                tool_ids.add(str(step["id"]))
        for step in steps:
            if not isinstance(step, dict):
                continue
            if not str(step.get("uses") or "").startswith(AGENT_ACTION_PREFIX):
                continue
            with_block = step.get("with") or {}
            if not isinstance(with_block, dict):
                continue
            refs = {m.group(1) for m in TOOL_ARGS_OUTPUT_RE.finditer(
                str(with_block.get("claude_args") or ""))}
            if refs & tool_ids:
                found.append((job_name, steps, step, with_block))

    if len(found) != 1:
        return [f"{path}: expected exactly one agent step fed by the "
                f"{REVIEWER_LABEL!r} tool-args site, found {len(found)} -- "
                f"check 5 would pass without checking it."]
    job_name, steps, agent, with_block = found[0]
    where = f"{path}: job {job_name!r}"
    problems = []

    gather = [s for s in steps if isinstance(s, dict)
              and s.get("id") == REVIEW_GATHER_ID]
    if len(gather) != 1:
        return [f"{where} has {len(gather)} steps with id "
                f"{REVIEW_GATHER_ID!r}, want 1 -- the reviewer's staged "
                f"inputs have no single writer."]
    if steps.index(gather[0]) > steps.index(agent):
        problems.append(f"{where}: the {REVIEW_GATHER_ID!r} step runs after "
                        f"the reviewer, so nothing is staged when it reads.")
    run = str(gather[0].get("run") or "")
    first = next((ln.strip() for ln in run.splitlines() if ln.strip()), "")
    if first != "set -euo pipefail":
        problems.append(
            f"{where}: the {REVIEW_GATHER_ID!r} step's run: starts with "
            f"{first!r}, not `set -euo pipefail` -- a failed write would "
            f"leave the reviewer an empty or missing file and the step "
            f"green (#503 review).")
    written = [m.group(1).strip("\"'") for m in REDIRECT_TARGET_RE.finditer(run)]
    by_base = {}
    for w in written:
        by_base.setdefault(os.path.basename(w), []).append(w)
    if REVIEW_DIFF_BASENAME not in by_base:
        problems.append(f"{where}: the {REVIEW_GATHER_ID!r} step never "
                        f"writes {REVIEW_DIFF_BASENAME}.")
    for base, paths in sorted(by_base.items()):
        if len(paths) != 1:
            problems.append(f"{where}: the {REVIEW_GATHER_ID!r} step writes "
                            f"{base} {len(paths)} times ({paths!r}), want "
                            f"exactly once.")
        for w in paths:
            if not w.startswith(STAGING_DIR) or "$" in w:
                problems.append(
                    f"{where}: the {REVIEW_GATHER_ID!r} step writes {base} "
                    f"to {w!r}, not a literal path under {STAGING_DIR} "
                    f"(where wing-commander-issue-context stages, and the "
                    f"agent's Read reaches; #503).")

    diff_paths = by_base.get(REVIEW_DIFF_BASENAME, [])
    if len(diff_paths) == 1:
        guard = re.compile(
            r"if \[ ! -s \"?" + re.escape(diff_paths[0]) + r"\"? \]; then\n"
            r"(?:(?![ \t]*fi\b)[^\n]*\n){0,3}?[ \t]*exit [1-9]")
        if not guard.search(run):
            problems.append(
                f"{where}: the {REVIEW_GATHER_ID!r} step does not fail on an "
                f"empty {diff_paths[0]} (`if [ ! -s PATH ]; then ... exit "
                f"1`). An empty diff makes the reviewer find nothing and "
                f"readiness run on an unreviewed PR (#503 review).")

    prompt = str(with_block.get("prompt") or "")
    if not PROMPT_DIFF_PATH_RE.search(prompt):
        problems.append(f"{where}: the reviewer prompt does not name "
                        f"{REVIEW_DIFF_BASENAME} at all.")
    for base, paths in sorted(by_base.items()):
        token_re = re.compile(r"[^\s`'\"(]*" + re.escape(base))
        for n in token_re.findall(prompt):
            if len(paths) == 1 and n != paths[0]:
                problems.append(
                    f"{where}: the reviewer prompt names {base} at {n!r}, "
                    f"but the {REVIEW_GATHER_ID!r} step writes {paths[0]!r} "
                    f"-- the reviewer would read a missing file (#503).")
    for n in sorted(set(STAGED_PATH_RE.findall(prompt))):
        if n not in written:
            problems.append(
                f"{where}: the reviewer prompt names {n!r}, which the "
                f"{REVIEW_GATHER_ID!r} step does not write (#503).")
    for m in PROMPT_GH_RE.finditer(prompt):
        problems.append(
            f"{where}: the reviewer prompt tells the agent to run "
            f"{m.group(0)!r}, but it has no gh grant; stage what it needs "
            f"in the {REVIEW_GATHER_ID!r} step instead (#503).")
    return problems


def gather_scannable_files():
    files = []
    for pattern in (".github/workflows/*.yml", ".github/workflows/*.yaml"):
        files.extend(glob.glob(pattern))
    for pattern in (".github/actions/**/action.yml",
                     ".github/actions/**/action.yaml"):
        files.extend(glob.glob(pattern, recursive=True))
    return sorted(set(files))


def check_single_home(path, exempt):
    """Gate 93 check 2: no file other than `exempt` may carry all three
    trust-filter fragments together."""
    if os.path.normpath(path) == os.path.normpath(exempt):
        return []
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except (OSError, UnicodeDecodeError) as exc:
        return [f"{path}: could not read ({exc})"]
    if all(pattern.search(text) for pattern in TRUST_FILTER_FRAGMENTS):
        return [
            f"{path}: carries all three fragments unique to "
            f"wing-commander-issue-context's own trust filter (a non-bot "
            f"check, a paginated /comments fetch, and its '## Comment by "
            f"@' staging template) -- this is a second, drifting copy. "
            f"Consume the composite instead of re-implementing it (#499)."
        ]
    return []


SPEC_REQUEST_BUILDER = ".github/scripts/board_spec_request_body.py"
ISSUE_CONTEXT_USES = "wing-commander-issue-context"
CONTEXT_FILE_EXPR_RE = re.compile(
    r"^\$\{\{\s*steps\.([A-Za-z0-9_-]+)\.outputs\.context-file\s*\}\}$")
# `"$X"`, `"${X}"`, `$X` or `${X}` -- a bare shell variable, nothing else.
SHELL_VAR = r'"?\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?"?'
BODY_FILE_RE = re.compile(r"--body-file[= ]\s*" + SHELL_VAR + r"(?=\s|$)")
BUILDER_OUT_RE = re.compile(r"--out[= ]\s*" + SHELL_VAR + r"(?=\s|$)")
BUILDER_CONTEXT_RE = re.compile(
    r"--context-file[= ]\s*" + SHELL_VAR + r"(?=\s|$)")
INLINE_BODY_RE = re.compile(r"(?<![\w-])(?:--body(?![\w-])|-b(?![\w-]))")
GH_ISSUE_CREATE_RE = re.compile(r"\bgh\s+issue\s+create\b")
LABEL_ARG_RE = re.compile(
    r"(?<![\w-])(?:--label|-l)(?:=|\s+)(\"[^\"]*\"|'[^']*'|\S+)")
GH_ISSUE_VIEW_RE = re.compile(r"\bgh\s+issue\s+view\b")
# The ONE `gh issue view` form a spec-request site may use: the new
# issue's title, captured by `$(...)` with nothing piped or redirected.
_VAR_ARG = r'"?\$\{?[A-Za-z_][A-Za-z0-9_]*\}?"?'
ALLOWED_ISSUE_VIEW_RE = re.compile(
    r"gh\s+issue\s+view\s+" + _VAR_ARG + r"(?:\s+-R\s+" + _VAR_ARG + r")?"
    r"\s+--json[= ]title\s+--jq[= ]\.title\)")
GH_API_RE = re.compile(r"\bgh\s+api\b")
DRAFTED_ARG_RE = re.compile(
    r"--drafted-body-file(?:=|\s+)(\"[^\"]*\"|'[^']*'|\S+)")
BARE_VAR_TOKEN_RE = re.compile(r'^"?\$\{?[A-Za-z_][A-Za-z0-9_]*\}?"?$')


def _drafted_writer_re(token):
    """The only line allowed to write the --drafted-body-file: route's
    `jq ... .proposal["pr-body"] ... > FILE` (a single `>`, no pipe)."""
    return re.compile(r'^\s*jq\s[^|;&>]*\.proposal\["pr-body"\][^|;&>]*>\s*'
                      + re.escape(token) + r"\s*$")


def _reassignment_res(var):
    v = re.escape(var)
    return (
        re.compile(r"(?<![\w$\{])" + v + r"\+?="),
        re.compile(r"\b(?:read|mapfile|readarray)\b[^\n]*(?<![\w$\{])" + v
                   + r"\b"),
        re.compile(r"\bprintf\s+-v\s*" + v + r"\b"),
        re.compile(r"\b(?:unset|export|declare|local|readonly|typeset)\b"
                   r"[^\n]*(?<![\w$\{])" + v + r"\b"),
        re.compile(r"\bfor\s+" + v + r"\s+in\b"),
    )


def _normalize_if(value):
    """An `if:` as comparable text: `${{ }}` and whitespace stripped.
    None for a missing or null `if:` (the step always runs)."""
    if value is None:
        return None
    text = str(value).strip()
    m = re.match(r"^\$\{\{(.*)\}\}$", text, re.DOTALL)
    if m:
        text = m.group(1)
    return " ".join(text.split())


def _logical_lines(run_text):
    """Shell logical lines: backslash-newline continuations joined."""
    return re.sub(r"\\\n\s*", " ", run_text or "").split("\n")


def _is_spec_request_create(line):
    return bool(GH_ISSUE_CREATE_RE.search(line) and "spec-request" in line)


# Check 3's create guard (#514). A site's `run:` has no `-e`, so a failed
# `gh issue create` would otherwise flow straight into the re-route
# comment, board:stalled and the outstanding-task item.
CREATE_CAPTURE_RE = re.compile(
    r'^\s*([A-Za-z_][A-Za-z0-9_]*)="?\$\(\s*gh\s+issue\s+create\b')
# Acting on the issue or publishing the URL: none may precede the guard.
ACT_BEFORE_GUARD_RE = re.compile(
    r"\bgh\s+(?:issue\s+(?:comment|edit|close|reopen)|pr\s+(?:comment|edit)"
    r"|label)\b|GITHUB_OUTPUT")
# Step conditions that would still run a later step after the site failed.
RUNS_AFTER_FAILURE_RE = re.compile(r"\b(?:always|cancelled|failure)\(\)")


def _url_guard_re(var):
    """One logical line that tests the captured URL and, when it fails,
    reports `::error::` and exits non-zero from the step's own shell:
    `[ -n "$V" ] || { ...; exit N; }` or `[[ "$V" =~ RE ]] || { ... }`
    (N >= 1, as the brace group's last command; a `( ... )` subshell
    would exit only itself). RE must be anchored `^...` and end in
    `/issues/[0-9]+$` -- a vacuous `.*` matches the empty string a
    failed create leaves behind."""
    v = r'"\$\{?' + re.escape(var) + r'\}?"'
    test = (r"(?:\[\[?\s+-n\s+" + v + r"\s+\]\]?"
            r"|\[\[\s+" + v + r"\s+=~\s+\^\S*/issues/\[0-9\]\+\$\s+\]\])")
    return re.compile(r"^\s*" + test + r"\s*\|\|\s*\{\s+echo\s.*::error::.*"
                      r";\s*exit\s+[1-9][0-9]*\s*;\s*\}\s*$")


def _create_guard_problems(where, step, steps, job_id, lines, create_idx):
    """Check 3 (#514): each spec-request create captures its URL, and a
    guard on that URL exits non-zero before the step comments, labels or
    publishes anything; the site is not continue-on-error, and no later
    step reading its outputs is gated to run after it failed."""
    problems = []
    for index in create_idx:
        m = CREATE_CAPTURE_RE.match(lines[index])
        if not m:
            problems.append(
                f"{where} files a spec-request without capturing its URL "
                f"(`VAR=\"$(gh issue create ...)\"`) -- nothing can check "
                f"that the create succeeded (#514).")
            continue
        var = m.group(1)
        guard = _url_guard_re(var)
        var_ref = re.compile(r"\$\{?" + re.escape(var) + r"\b")
        for later in lines[index + 1:]:
            if guard.search(later):
                if ACT_BEFORE_GUARD_RE.search(later):
                    problems.append(
                        f"{where}: the guard on ${var} itself comments, "
                        f"labels or publishes on a failed create "
                        f"({later.strip()[:80]!r}) -- it may only report "
                        f"`::error::` and exit (#514).")
                break
            if ACT_BEFORE_GUARD_RE.search(later) or var_ref.search(later):
                problems.append(
                    f"{where} acts on the spec-request before checking "
                    f"${var} ({later.strip()[:80]!r}) -- on a failed "
                    f"create that posts the re-route comment, adds "
                    f"board:stalled or publishes an empty URL with no "
                    f"spec-request filed (#514). Guard ${var} right "
                    f"after the create.")
                break
        else:
            problems.append(
                f"{where} never checks ${var} after `gh issue create "
                f"... spec-request` -- add `[[ \"${var}\" =~ ... ]] || "
                f"{{ echo \"::error::...\"; exit 1; }}` right after it "
                f"(#514).")
    coe = step.get("continue-on-error")
    if coe is not None and coe is not False and str(coe).strip() != "false":
        problems.append(
            f"{where} is continue-on-error ({coe!r}) -- a failed "
            f"spec-request create must fail the job, so the issue is "
            f"retried rather than reported as done (#514).")
    step_id = step.get("id")
    if step_id:
        ref = re.compile(r"\bsteps\." + re.escape(str(step_id))
                         + r"\.outputs\.")
        seen = False
        for other in steps:
            if other is step:
                seen = True
                continue
            if not seen or not isinstance(other, dict):
                continue
            if not ref.search(yaml.safe_dump(other)):
                continue
            cond = str(other.get("if") or "")
            if RUNS_AFTER_FAILURE_RE.search(cond):
                name = other.get("name") or other.get("id") or "(unnamed)"
                problems.append(
                    f"{where}: later step {name!r} in job {job_id!r} reads "
                    f"its outputs under `if: {cond}`, which runs after the "
                    f"site failed its create guard -- gate it on "
                    f"success() (#514).")
    return problems


def check_spec_request_bodies(path):
    """Gate 93 check 3: every spec-request board-loop.yml files gets its
    body from board_spec_request_body.py, fed the issue-context
    composite's context-file and nothing else."""
    problems = []
    try:
        with open(path, encoding="utf-8") as fh:
            doc = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        return [f"{path}: could not parse as YAML ({exc})"]
    jobs = doc.get("jobs") if isinstance(doc, dict) else None
    if not isinstance(jobs, dict):
        return [f"{path}: no jobs: mapping -- check 3 found nothing to "
                f"check."]

    sites = 0
    for job_id, job in jobs.items():
        steps = job.get("steps") if isinstance(job, dict) else None
        if not isinstance(steps, list):
            continue
        # Only steps ABOVE the current one count: a context file fetched
        # after the spec-request is filed cannot have fed its body.
        context_steps = {}
        for step in steps:
            if not isinstance(step, dict):
                continue
            if ISSUE_CONTEXT_USES in str(step.get("uses") or ""):
                if step.get("id"):
                    context_steps[str(step["id"])] = step
                continue
            name = step.get("name") or step.get("id") or "(unnamed step)"
            where = f"{path}: job {job_id!r} step {name!r}"
            lines = _logical_lines(str(step.get("run") or ""))

            for line in lines:
                if (re.search(r"\bgh\s+issue\s+edit\b", line)
                        and re.search(r"--add-label[= ]\s*[\"']?spec-request",
                                      line)):
                    problems.append(
                        f"{where} relabels an issue as spec-request -- its "
                        f"body never went through {SPEC_REQUEST_BUILDER}. "
                        f"File a new spec-request through the builder "
                        f"instead.")
                # Fail closed: a label passed through a variable could be
                # spec-request, and the site checks below would never see
                # it.
                if GH_ISSUE_CREATE_RE.search(line):
                    for m in LABEL_ARG_RE.finditer(line):
                        if "$" in m.group(1) or "`" in m.group(1):
                            problems.append(
                                f"{where} passes `gh issue create` a label "
                                f"through a variable ({m.group(1)}) -- this "
                                f"gate cannot tell whether it files a "
                                f"spec-request. Pass labels literally.")

            create_idx = [i for i, line in enumerate(lines)
                          if _is_spec_request_create(line)]
            creates = [lines[i] for i in create_idx]
            if not creates:
                continue
            sites += len(creates)
            problems.extend(_create_guard_problems(
                where, step, steps, job_id, lines, create_idx))

            builder_idx = [i for i, line in enumerate(lines)
                           if "board_spec_request_body.py" in line]
            builder_lines = [lines[i] for i in builder_idx]
            builder_outs = {m.group(1) for line in builder_lines
                            for m in BUILDER_OUT_RE.finditer(line)}
            env = step.get("env")
            if not isinstance(env, dict):
                env = {}

            for line in creates:
                if INLINE_BODY_RE.search(line):
                    problems.append(
                        f"{where} files a spec-request with an inline "
                        f"--body/-b -- the body must come from "
                        f"{SPEC_REQUEST_BUILDER} via --body-file, so an "
                        f"empty drafted body falls back to the "
                        f"trust-filtered issue context.")
                body_files = [m.group(1) for m in BODY_FILE_RE.finditer(line)]
                if not body_files:
                    problems.append(
                        f"{where} files a spec-request without "
                        f"--body-file \"$VAR\" -- the body must be the "
                        f"file {SPEC_REQUEST_BUILDER} wrote.")
                for var in body_files:
                    if var not in builder_outs:
                        problems.append(
                            f"{where} files a spec-request with --body-file "
                            f"\"${var}\", which no {SPEC_REQUEST_BUILDER} "
                            f"call in this step writes (--out \"${var}\").")

            for index in builder_idx:
                line = lines[index]
                ctx_vars = [m.group(1)
                            for m in BUILDER_CONTEXT_RE.finditer(line)]
                if len(ctx_vars) != 1:
                    problems.append(
                        f"{where}: {SPEC_REQUEST_BUILDER} must get exactly "
                        f"one --context-file \"$VAR\" (found "
                        f"{len(ctx_vars)}) -- without it an empty drafted "
                        f"body has no trust-filtered fallback.")
                else:
                    var = ctx_vars[0]
                    expr = str(env.get(var) or "").strip()
                    match = CONTEXT_FILE_EXPR_RE.match(expr)
                    if not match:
                        problems.append(
                            f"{where}: {SPEC_REQUEST_BUILDER}'s "
                            f"--context-file \"${var}\" is "
                            f"{expr or '(not set in env:)'!r}, not a "
                            f"wing-commander-issue-context step's "
                            f"context-file output -- the fallback must "
                            f"read the composite's trust-filtered file "
                            f"and nothing else (FR-056).")
                    elif match.group(1) not in context_steps:
                        problems.append(
                            f"{where}: --context-file comes from step "
                            f"{match.group(1)!r}, which is not an earlier "
                            f"wing-commander-issue-context step in job "
                            f"{job_id!r}.")
                    else:
                        # The fetch must run whenever this site does:
                        # no `if:` at all, or the site's own `if:`.
                        fetch = context_steps[match.group(1)]
                        fetch_if = (_normalize_if(fetch.get("if"))
                                    if "if" in fetch else None)
                        site_if = _normalize_if(step.get("if"))
                        if fetch_if is not None and fetch_if != site_if:
                            problems.append(
                                f"{where}: its context fetch "
                                f"{match.group(1)!r} is gated "
                                f"`if: {fetch_if}`, which the site's own "
                                f"`if: {site_if}` does not imply -- the "
                                f"fetch must have no `if:` or the site's "
                                f"exact `if:`, or the fallback can "
                                f"silently never have its file.")
                    for earlier in lines[:index]:
                        for pattern in _reassignment_res(var):
                            if pattern.search(earlier):
                                problems.append(
                                    f"{where} reassigns ${var} before "
                                    f"{SPEC_REQUEST_BUILDER} reads it "
                                    f"({earlier.strip()[:80]!r}) -- the "
                                    f"context file must be the "
                                    f"composite's output as given in env:.")
                                break

                for m in DRAFTED_ARG_RE.finditer(line):
                    token = m.group(1)
                    if BARE_VAR_TOKEN_RE.match(token):
                        problems.append(
                            f"{where}: --drafted-body-file {token} is a "
                            f"bare variable -- pass the literal path "
                            f"route's pr-body jq writes, so this gate can "
                            f"check what feeds it.")
                        continue
                    writer = _drafted_writer_re(token)
                    writers = 0
                    for other_index, other in enumerate(lines):
                        if other_index in builder_idx or token not in other:
                            continue
                        if writer.search(other):
                            writers += 1
                        else:
                            problems.append(
                                f"{where}: --drafted-body-file {token} is "
                                f"touched by {other.strip()[:80]!r} -- it "
                                f"may be written only by `jq ... "
                                f".proposal[\"pr-body\"] ... > {token}`.")
                    if writers != 1:
                        problems.append(
                            f"{where}: --drafted-body-file {token} has "
                            f"{writers} `jq ... .proposal[\"pr-body\"] "
                            f"... > FILE` writer(s); it needs exactly one.")

            for line in lines:
                if GH_API_RE.search(line):
                    problems.append(
                        f"{where} calls `gh api` (REST or graphql) -- a "
                        f"spec-request site must not read the issue "
                        f"itself; unfiltered content must never reach "
                        f"its body (FR-056).")
                for m in GH_ISSUE_VIEW_RE.finditer(line):
                    if not ALLOWED_ISSUE_VIEW_RE.match(line[m.start():]):
                        problems.append(
                            f"{where} runs `gh issue view` other than "
                            f"`$(gh issue view N -R REPO --json title --jq "
                            f".title)` ({line.strip()[:80]!r}) -- the "
                            f"issue's body and comments reach a "
                            f"spec-request only through "
                            f"{SPEC_REQUEST_BUILDER}'s context file "
                            f"(FR-056).")

    if sites == 0:
        problems.append(
            f"{path}: found no `gh issue create ... spec-request` step -- "
            f"check 3 would pass vacuously. If the label or command "
            f"changed, update this gate with it.")
    return problems


def check_repo():
    problems = []
    problems.extend(check_tool_grants(BOARD_LOOP))
    problems.extend(check_spec_request_bodies(BOARD_LOOP))
    problems.extend(check_read_only_git(BOARD_LOOP))
    problems.extend(check_fleet_read_only_git())
    problems.extend(check_reviewer_staged_inputs(BOARD_LOOP))
    for path in gather_scannable_files():
        problems.extend(check_single_home(path, ISSUE_CONTEXT_ACTION))
    return problems


_URL_GUARD = (
    '          [[ "$spec_url" =~ ^https?://[^[:space:]]+/issues/[0-9]+$ ]] '
    '|| { echo "::error::no spec-request URL (got \'$spec_url\')"; exit 1; }\n')
_GOOD_SITE_RUN = (
    '          set -uo pipefail\n'
    '          jq -r \'.proposal["pr-body"] // empty\' "$RUNNER_TEMP/d.json" > "$RUNNER_TEMP/drafted.md"\n'
    '          issue_title="$(gh issue view "$ISSUE_NUMBER" -R "$GITHUB_REPOSITORY" --json title --jq .title)"\n'
    '          spec_body_file="$RUNNER_TEMP/body.md"\n'
    '          python3 .github/scripts/board_spec_request_body.py '
    '--context-file "$ISSUE_CONTEXT_FILE" \\\n'
    '            --drafted-body-file "$RUNNER_TEMP/drafted.md" \\\n'
    '            --footer "f" --out "$spec_body_file" \\\n'
    '            || printf \'No drafted body.\\n\' > "$spec_body_file"\n'
    '          spec_url="$(gh issue create -R "$GITHUB_REPOSITORY" --title "$issue_title" \\\n'
    '            --body-file "$spec_body_file" \\\n'
    '            --label spec-request)"\n'
    + _URL_GUARD +
    '          echo "spec-url=$spec_url" >> "$GITHUB_OUTPUT"\n'
    '          gh issue comment 1 --body "re-routed"\n'
    '          gh issue edit 1 --add-label "board:stalled"\n'
)
_BEFORE_BUILDER = '          spec_body_file='


def _site_fixture(run=_GOOD_SITE_RUN,
                  context_env="${{ steps.ctx.outputs.context-file }}",
                  context_step_first=True, fetch_if=None,
                  site_if="steps.x.outputs.y != 'true'",
                  site_coe=None, after=""):
    fetch = (
        "      - name: Fetch issue context\n"
        "        id: ctx\n"
        + (f"        if: {fetch_if}\n" if fetch_if is not None else "")
        + "        uses: ./.github/actions/wing-commander-issue-context\n"
        "        with:\n"
        "          token: t\n"
        "          issue-number: 1\n"
    )
    site = (
        "      - name: File the spec-request\n"
        "        id: site\n"
        + (f"        if: {site_if}\n" if site_if is not None else "")
        + (f"        continue-on-error: {site_coe}\n"
           if site_coe is not None else "")
        + "        env:\n"
        f"          ISSUE_CONTEXT_FILE: {context_env}\n"
        "        run: |\n" + run
    )
    body = (fetch + site if context_step_first else site + fetch) + after
    return ("name: gate-93-fixture-spec-request\n"
            "jobs:\n"
            "  route:\n"
            "    steps:\n" + body)


def _insert_before_builder(line):
    return _GOOD_SITE_RUN.replace(_BEFORE_BUILDER,
                                  "          " + line + "\n" + _BEFORE_BUILDER)


def _cross_link_step(cond):
    return ("      - name: Cross-link the spec-request\n"
            f"        if: {cond}\n"
            "        uses: ./.github/actions/wing-commander-outstanding-task-item\n"
            "        with:\n"
            "          artifact-url: ${{ steps.site.outputs.spec-url }}\n")


def _create_guard_cases(good):
    """Check 3 fixtures for the create guard (#514): a spec-request site
    whose failed `gh issue create` could still comment, label, publish
    its URL, or leave the job green."""
    uncaptured = good.replace('spec_url="$(gh issue create',
                              'gh issue create').replace(
        '--label spec-request)"', '--label spec-request')
    unguarded = good.replace(_URL_GUARD, "")
    comment = '          gh issue comment 1 --body "re-routed"\n'
    edit = '          gh issue edit 1 --add-label "board:stalled"\n'
    output = '          echo "spec-url=$spec_url" >> "$GITHUB_OUTPUT"\n'

    def guard_with(tail):
        return good.replace(
            _URL_GUARD,
            '          [[ "$spec_url" =~ ^https?://[^[:space:]]+/issues/'
            '[0-9]+$ ]] || ' + tail + '\n')

    return [
        ("good site ([ -n ] guard)",
         _site_fixture(run=good.replace(
             _URL_GUARD,
             '          [ -n "$spec_url" ] || { echo "::error::no URL"; '
             'exit 1; }\n')),
         None),
        ("good site (cross-link gated on the site's output only)",
         _site_fixture(after=_cross_link_step(
             "steps.site.outputs.spec-url != ''")),
         None),
        ("create URL not captured",
         _site_fixture(run=uncaptured), "without capturing its URL"),
        ("no guard, output written next (the #514 shape)",
         _site_fixture(run=unguarded), "acts on the spec-request before"),
        ("no guard and nothing after the create",
         _site_fixture(run=unguarded.replace(output, "").replace(
             comment, "").replace(edit, "")),
         "never checks $spec_url"),
        ("guard after the re-route comment",
         _site_fixture(run=unguarded.replace(output, "").replace(
             edit, edit + _URL_GUARD + output)),
         "acts on the spec-request before"),
        ("board:stalled added before the guard",
         _site_fixture(run=unguarded.replace(output, "").replace(
             comment, "").replace(edit, edit + _URL_GUARD + output
                                  + comment)),
         "acts on the spec-request before"),
        ("guard with no exit",
         _site_fixture(run=guard_with('echo "::error::no URL"')),
         "acts on the spec-request before"),
        ("guard exits 0",
         _site_fixture(run=guard_with('{ echo "::error::no URL"; exit 0; }')),
         "acts on the spec-request before"),
        ("guard exits only a subshell",
         _site_fixture(run=guard_with('( echo "::error::no URL"; exit 1 )')),
         "acts on the spec-request before"),
        ("guard regex vacuous (.* matches an empty URL)",
         _site_fixture(run=good.replace(
             "^https?://[^[:space:]]+/issues/[0-9]+$", ".*")),
         "acts on the spec-request before"),
        ("guard regex unanchored",
         _site_fixture(run=good.replace(
             "^https?://[^[:space:]]+/issues/[0-9]+$", "/issues/")),
         "acts on the spec-request before"),
        ("guard with no ::error::",
         _site_fixture(run=guard_with('{ echo "no URL"; exit 1; }')),
         "acts on the spec-request before"),
        ("guard on a different variable",
         _site_fixture(run=good.replace(
             _URL_GUARD, _URL_GUARD.replace("$spec_url", "$other_url"))),
         "acts on the spec-request before"),
        ("guard's failure branch comments on the issue",
         _site_fixture(run=guard_with(
             '{ echo "::error::no URL"; gh issue comment 1 --body x; '
             'exit 1; }')),
         "the guard on $spec_url itself"),
        ("site is continue-on-error",
         _site_fixture(site_coe="true"), "is continue-on-error"),
        ("cross-link gated always()",
         _site_fixture(after=_cross_link_step(
             "always() && steps.site.outputs.spec-url != ''")),
         "runs after the site failed its create guard"),
        ("cross-link gated !cancelled()",
         _site_fixture(after=_cross_link_step(
             "\"!cancelled() && steps.site.outputs.spec-url != ''\"")),
         "runs after the site failed its create guard"),
    ]


def _self_test_spec_request_sites(tmpdir):
    """Check 3 fixtures: well-formed sites pass; each way of filing a
    spec-request whose body can skip the trust-filtered fallback, or whose
    fallback reads something other than the composite's context-file,
    fails and names why."""
    failures = []
    good = _GOOD_SITE_RUN
    site_if = "steps.x.outputs.y != 'true'"
    cases = [
        ("good site (fetch has no if:)", _site_fixture(), None),
        ("good site (fetch if: identical to the site's)",
         _site_fixture(fetch_if="${{ " + site_if + " }}"), None),
        ("inline --body (the #509 shape)",
         _site_fixture(run=good.replace(
             '--body-file "$spec_body_file"',
             '--body "${pr_body:-No drafted body.}"')),
         "inline --body"),
        ("--body-file not written by the builder",
         _site_fixture(run=good.replace(
             '--body-file "$spec_body_file"', '--body-file "$other_file"')),
         "which no .github/scripts/board_spec_request_body.py call"),
        ("no builder call at all",
         _site_fixture(run=good.replace(
             "python3 .github/scripts/board_spec_request_body.py",
             "python3 .github/scripts/some_other.py")),
         "which no .github/scripts/board_spec_request_body.py call"),
        ("builder without --context-file",
         _site_fixture(run=good.replace(
             '--context-file "$ISSUE_CONTEXT_FILE" ', '')),
         "exactly one --context-file"),
        ("context from the composite's comments-file",
         _site_fixture(
             context_env="${{ steps.ctx.outputs.comments-file }}"),
         "not a wing-commander-issue-context step's context-file"),
        ("context from a self-made path",
         _site_fixture(context_env="/tmp/wing-commander/context.md"),
         "not a wing-commander-issue-context step's context-file"),
        ("context from a step that is not the composite",
         _site_fixture(
             context_env="${{ steps.other.outputs.context-file }}"),
         "not an earlier wing-commander-issue-context step"),
        ("context fetched only after the site",
         _site_fixture(context_step_first=False),
         "not an earlier wing-commander-issue-context step"),
        ("context fetch gated if: false",
         _site_fixture(fetch_if="false"),
         "which the site's own"),
        ("context fetch gated narrower than the site",
         _site_fixture(fetch_if=site_if + " && steps.z.outputs.w == 'true'"),
         "which the site's own"),
        ("context env var reassigned before the builder",
         _site_fixture(run=_insert_before_builder(
             'ISSUE_CONTEXT_FILE="$RUNNER_TEMP/raw.md"')),
         "reassigns $ISSUE_CONTEXT_FILE"),
        ("context env var overwritten by read",
         _site_fixture(run=_insert_before_builder(
             'read -r ISSUE_CONTEXT_FILE < "$RUNNER_TEMP/path.txt"')),
         "reassigns $ISSUE_CONTEXT_FILE"),
        ("unfiltered gh issue view --json body,comments read",
         _site_fixture(run=_insert_before_builder(
             'gh issue view 1 --json body,comments > "$RUNNER_TEMP/raw.json"')),
         "runs `gh issue view` other than"),
        ("unfiltered gh issue view --comments read",
         _site_fixture(run=_insert_before_builder(
             'gh issue view 1 --comments > "$RUNNER_TEMP/raw.md"')),
         "runs `gh issue view` other than"),
        ("bare gh issue view redirected to a file",
         _site_fixture(run=_insert_before_builder(
             'gh issue view "$ISSUE_NUMBER" > "$RUNNER_TEMP/raw.md"')),
         "runs `gh issue view` other than"),
        ("gh issue view --json title piped onward",
         _site_fixture(run=_insert_before_builder(
             'gh issue view "$ISSUE_NUMBER" --json title --jq .title > t.txt')),
         "runs `gh issue view` other than"),
        ("unfiltered gh api issue read",
         _site_fixture(run=_insert_before_builder(
             'gh api "repos/x/y/issues/1/comments" > raw.json')),
         "calls `gh api`"),
        ("gh api graphql read",
         _site_fixture(run=_insert_before_builder(
             # wc-gh-method-exempt: fixture text Gate 93 must flag, never executed
             "gh api graphql -f query='{repository(owner:\"x\",name:\"y\"){issue(number:1){body}}}' > raw.json")),
         "calls `gh api`"),
        ("--drafted-body-file written by something else",
         _site_fixture(run=_insert_before_builder(
             'cat "$ISSUE_CONTEXT_RAW" > "$RUNNER_TEMP/drafted.md"')),
         "is touched by"),
        ("--drafted-body-file with no pr-body writer",
         _site_fixture(run=good.replace(
             '.proposal["pr-body"]', '.proposal["pr-title"]')),
         "is touched by"),
        ("--drafted-body-file appended to",
         _site_fixture(run=_insert_before_builder(
             'jq -r \'.proposal["pr-body"]\' x.json >> "$RUNNER_TEMP/drafted.md"')),
         "is touched by"),
        ("--drafted-body-file as a bare variable",
         _site_fixture(run=good.replace(
             '--drafted-body-file "$RUNNER_TEMP/drafted.md"',
             '--drafted-body-file "$drafted"')),
         "is a bare variable"),
        ("label passed through a variable",
         _site_fixture(run=good + (
             '          lbl=spec-request\n'
             '          gh issue create -R "$GITHUB_REPOSITORY" --title t '
             '--body x --label "$lbl"\n')),
         "a label through a variable"),
        ("relabel an existing issue as spec-request",
         _site_fixture(run=good + (
             '          gh issue edit 1 --add-label spec-request\n')),
         "relabels an issue as spec-request"),
        ("no spec-request site at all (vacuous)",
         _site_fixture(run=good.replace("spec-request", "board:stalled")),
         "would pass vacuously"),
    ]
    cases.extend(_create_guard_cases(good))
    for index, (label, text, expect) in enumerate(cases):
        path = os.path.join(tmpdir, f"gate-93-fixture-spec-{index}.yml")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        problems = check_spec_request_bodies(path)
        if expect is None:
            if problems:
                failures.append(f"check 3 fixture {label!r} should pass but "
                                f"was flagged: {problems!r}")
            continue
        if not problems:
            failures.append(f"check 3 fixture {label!r} was not caught")
        elif expect not in " ".join(problems):
            failures.append(f"check 3 fixture {label!r} was caught without "
                            f"naming {expect!r}: {problems!r}")
        else:
            print(f"note: check 3 fixture {label!r} caught.")
    return failures


def _load_builder(path=SPEC_REQUEST_BUILDER):
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "board_spec_request_body", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fenced_inner(b, body, heading=None):
    """(fence, inner text) of the one fenced block under `heading` (the
    context heading by default) in `body`, or (None, None) when the block
    is not well formed: an opening fence line right after the heading and
    the SAME fence alone on a later line, with no line in between that
    could close it (a backtick run at least as long, alone on its line
    after up to three spaces)."""
    lines = body.split("\n")
    try:
        start = lines.index(heading or b.CONTEXT_HEADING) + 2
    except ValueError:
        return None, None
    fence = lines[start] if start < len(lines) else ""
    if not re.fullmatch(r"`{3,}", fence):
        return None, None
    # cmark-gfm reads a fence of more than 255 backticks as 255 (#548
    # review), so a line of 255 or more closes any longer fence.
    effective = min(len(fence), CMARK_MAX_FENCE)
    for end in range(start + 1, len(lines)):
        m = re.fullmatch(r" {0,3}(`{3,})\s*", lines[end])
        if m and len(m.group(1)) >= effective:
            if lines[end] != fence:
                return None, None  # closed early by the content
            return fence, "\n".join(lines[start + 1:end])
    return None, None


# #548: route-propose's pr-body is model output derived from issue
# content. Every live-markdown shape it could carry must stay inside the
# fence: an @mention (a ping), #N (a backlink), a link, an image, HTML,
# and backtick runs -- one alone on its own line, the shape that closes
# a too-short fence.
DRAFTED_HOSTILE = (
    "## Proposal\n\ncc @someone, see #12 and org/repo#3.\n"
    "[x](http://example.com/x) ![i](http://example.com/i.png)\n"
    "<img src=\"http://example.com/p.png\"> <details><summary>s</summary>"
    "</details>\n```\n@escaped #1\n```\n``````\n@escaped #2\n"
    "   `````\nend")
# What must never appear outside the fence of a drafted body.
LIVE_MARKDOWN_RE = re.compile(r"@\w|#\d|\]\(|!\[|<[A-Za-z/!]")
# cmark-gfm's cap on fence length (#548 review): a longer fence is read as
# this long, so a lone line of this many backticks inside would close it.
CMARK_MAX_FENCE = 255
# A lone 300-backtick line, then live markdown: with an unbounded fence
# (301) cmark reads the fence as 255 and this line closes it.
LONG_RUN_HOSTILE = ("`" * 300 + "\n@x #12 ![i](http://e/i.png) <b>h</b>")


def _drafted_fence_problems(b):
    """Problems with how builder module `b` places a hostile drafted body
    (DRAFTED_HOSTILE): it must sit whole under DRAFTED_HEADING inside a
    fence longer than its longest backtick run, with nothing live outside
    that fence, and the context must not also be rendered. Also run
    against a mutated builder, which it must flag."""
    problems = []
    heading = getattr(b, "DRAFTED_HEADING", None)
    if not heading:
        return ["builder: no DRAFTED_HEADING for the drafted body"]
    notice, footer = "Notice.", "Routed from x"
    body = b.build_body(drafted=DRAFTED_HOSTILE, context="## Issue\n\nT",
                        notice=notice, footer=footer)
    fence, inner = _fenced_inner(b, body, heading)
    if inner != DRAFTED_HOSTILE:
        problems.append(f"builder: the drafted body is not whole inside "
                        f"its own fence under {heading!r}: {body!r}")
    else:
        longest = max(len(r) for r in re.findall(r"`+", DRAFTED_HOSTILE))
        if len(fence) <= longest:
            problems.append(f"builder: drafted fence {fence!r} is not "
                            f"longer than the draft's longest backtick "
                            f"run ({longest})")
        outside = body.replace(inner, "", 1)
        live = LIVE_MARKDOWN_RE.findall(outside)
        if live:
            problems.append(f"builder: live markdown {live!r} sits outside "
                            f"the drafted fence: {outside!r}")
    if not (body.startswith(notice + "\n\n" + heading)
            and body.endswith("\n\n---\n" + footer)):
        problems.append(f"builder: drafted layout is not notice, heading, "
                        f"fence, footer: {body!r}")
    if b.CONTEXT_HEADING in body:
        problems.append("builder: a drafted body should win over the "
                        "context, not sit beside it")
    problems.extend(_long_run_problems(b))
    return problems


def _long_run_problems(b):
    """A lone line of 300 backticks followed by live markdown, in both the
    drafted and the context path: one fence of at most CMARK_MAX_FENCE
    holds all of it (U+200B splits aside), nothing is live outside it,
    and the footer sits after the closing fence."""
    problems = []
    footer = "Routed from x"
    for label, heading, kwargs in (
            ("drafted", getattr(b, "DRAFTED_HEADING", None),
             {"drafted": LONG_RUN_HOSTILE}),
            ("context", b.CONTEXT_HEADING,
             {"context": "## Issue\n\n" + LONG_RUN_HOSTILE})):
        text = next(iter(kwargs.values()))
        body = b.build_body(footer=footer, **kwargs)
        fence, inner = _fenced_inner(b, body, heading)
        if inner is None or inner.replace("\u200b", "") != text:
            problems.append(f"builder: a {label} body with a lone 300-"
                            f"backtick line escaped (or mangled) its fence: "
                            f"{body[-400:]!r}")
            continue
        if len(fence) > CMARK_MAX_FENCE:
            problems.append(f"builder: {label} fence is {len(fence)} "
                            f"backticks, over cmark-gfm's cap of "
                            f"{CMARK_MAX_FENCE}")
        outside = body.replace(inner, "", 1)
        live = LIVE_MARKDOWN_RE.findall(outside)
        if live:
            problems.append(f"builder: live markdown {live!r} sits outside "
                            f"the {label} fence")
        close = body.index("\n" + fence + "\n", body.index(inner))
        if body.rfind(footer) < close or not body.endswith(
                "\n\n---\n" + footer):
            problems.append(f"builder: the footer is not after the {label} "
                            f"fence's closing line")
    return problems


def _self_test_builder():
    """board_spec_request_body.py: fallback order, the one-line fallback,
    fencing that keeps @mentions/#refs inert and cannot be broken out of,
    and truncation under GitHub's body limit with a visible note."""
    failures = []
    try:
        b = _load_builder()
    except (OSError, ImportError, SyntaxError) as exc:
        return [f"could not load {SPEC_REQUEST_BUILDER}: {exc}"]

    ctx = ("## Issue\n\nTitle\n\nThe issue body, see #12 and @someone.\n\n"
           "## Comment by @owner (2026-01-01)\n\ncc @team, fixes org/repo#3")
    body = b.build_body(drafted="", context=ctx, footer="Routed from x")
    fence, inner = _fenced_inner(b, body)
    if inner != ctx:
        failures.append(f"builder: an empty drafted body did not fall back "
                        f"to the labelled, fenced context: {body[:300]!r}")
    outside = body.replace(inner or "", "") if inner else body
    if re.search(r"[@#]\w", outside):
        failures.append(f"builder: an @mention or #reference sits outside "
                        f"the fence, where GitHub would expand it: "
                        f"{outside!r}")
    if not body.endswith("\n\n---\nRouted from x"):
        failures.append(f"builder: footer missing or misplaced: {body!r}")

    # Content carrying ``` or longer backtick runs, including one alone on
    # its own line (the shape that closes a too-short fence), must stay
    # inside the fence.
    for tricky in ("```\n@escaped #1\n```",
                   "```````\n@escaped #1",
                   "   ````\n@escaped",
                   "inline `code` and ``two`` and\n```python\nx\n```"):
        tctx = "## Issue\n\nT\n\n" + tricky
        body = b.build_body(context=tctx)
        fence, inner = _fenced_inner(b, body)
        if inner != tctx:
            failures.append(f"builder: context containing {tricky!r} broke "
                            f"out of (or mangled) its fence: {body!r}")
        elif len(fence) <= max(len(r) for r in re.findall(r"`+", tctx)):
            failures.append(f"builder: fence {fence!r} is not longer than "
                            f"the longest backtick run in {tricky!r}")

    failures.extend(_drafted_fence_problems(b))

    # #580 review: GitHub ends a line at a lone CR as well as at LF, so
    # fenced_section() normalises every CR to LF before fencing.
    cr_text = "a\r\nb\r```\r@x #12\rc"
    cr_body = b.fenced_section("H:", cr_text, 1000)
    fence, inner = _fenced_inner(b, cr_body, "H:")
    if "\r" in cr_body or inner != "a\nb\n```\n@x #12\nc":
        failures.append(f"builder: fenced_section() left a CR in (or "
                        f"mangled) {cr_text!r}: {cr_body!r}")

    body = b.build_body(drafted="  \n", context="", notice="N", footer="F")
    if body != "N\n\nNo drafted body.\n\n---\nF":
        failures.append(f"builder: missing context did not produce the "
                        f"one-line fallback: {body!r}")

    with tempfile.TemporaryDirectory() as tmpdir:
        missing = os.path.join(tmpdir, "nope.md")
        if b.read_text(missing) != "" or b.read_text("") != "":
            failures.append("builder: a missing/empty context path did not "
                            "read as empty")
        out = os.path.join(tmpdir, "out.md")
        b.main(["--context-file", missing, "--out", out])
        with open(out, encoding="utf-8") as fh:
            if fh.read().strip() != b.NO_BODY_FALLBACK:
                failures.append("builder CLI: a missing context file did "
                                "not produce the one-line fallback")

    huge = ("## Issue\n\n" + ("x" * 50000) + "\n" + ("`" * 9) + "\n"
            + ("\U0001F600" * 20000))
    notice = "n" * 300
    footer = "f" * 300
    for label, kwargs in (("context", {"context": huge}),
                          ("drafted", {"drafted": huge})):
        body = b.build_body(notice=notice, footer=footer, **kwargs)
        units = b.utf16_len(body)
        if units >= b.GITHUB_BODY_LIMIT or units > b.MAX_BODY_UNITS:
            failures.append(f"builder: an oversized {label} produced "
                            f"{units} UTF-16 units, over the limit")
        if "_[Truncated:" not in body:
            failures.append(f"builder: an oversized {label} was cut "
                            f"without a visible truncation note")
        if not (body.startswith(notice) and body.endswith(footer)):
            failures.append(f"builder: truncating an oversized {label} "
                            f"lost the notice or footer")
        heading = (b.CONTEXT_HEADING if label == "context"
                   else getattr(b, "DRAFTED_HEADING", None))
        fence, inner = _fenced_inner(b, body, heading)
        if inner is None or not huge.startswith(inner):
            failures.append(f"builder: truncating an oversized {label} "
                            f"left the fence unclosed or broken")
        elif body.index("_[Truncated:") < body.rindex(fence):
            failures.append(f"builder: the truncation note for an oversized "
                            f"{label} landed inside the fence, where it "
                            f"would not render")
    # U+200B splits add units: a body that is nothing but backticks must
    # still come in under the cap.
    for label in ("context", "drafted"):
        body = b.build_body(footer="f" * 300, **{label: "`" * 70000})
        units = b.utf16_len(body)
        if units > b.MAX_BODY_UNITS:
            failures.append(f"builder: a {label} of 70000 backticks "
                            f"produced {units} UTF-16 units, over "
                            f"{b.MAX_BODY_UNITS}")
    if not failures:
        print("note: builder unit tests passed (fallback order, one-line "
              "fallback, inert @/#/links/images/HTML inside an unbreakable "
              "fence for both the draft and the context, truncation under "
              "the limit with a note).")
    return failures


# Each mutation rewrites the REAL builder in memory the way a later edit
# could reopen #548; _drafted_fence_problems() must flag every one.
BUILDER_MUTATIONS = (
    ("drafted body unfenced again",
     "        proper = fenced_section(DRAFTED_HEADING, drafted, budget)\n",
     "        kept, note = truncate(drafted, budget)\n"
     "        proper = kept + note\n"),
    ("fence no longer sized from the content",
     '    return "`" * max(3, longest + 1)\n',
     '    return "```"\n'),
    ("long backtick runs no longer split (fence over cmark's 255 cap)",
     "    text = split_long_backtick_runs(text)\n",
     ""),
)


def _mutation_check_builder():
    failures = []
    try:
        with open(SPEC_REQUEST_BUILDER, encoding="utf-8") as fh:
            original = fh.read()
    except OSError as exc:
        return [f"mutation check: could not read {SPEC_REQUEST_BUILDER}: "
                f"{exc}"]
    with tempfile.TemporaryDirectory() as tmpdir:
        for label, old, new in BUILDER_MUTATIONS:
            if old not in original:
                failures.append(
                    f"mutation {label!r} no longer applies ({old!r} not in "
                    f"{SPEC_REQUEST_BUILDER}) -- update BUILDER_MUTATIONS "
                    f"so this gate stays proven.")
                continue
            path = os.path.join(tmpdir, "board_spec_request_body_mutated.py")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(original.replace(old, new, 1))
            if not _drafted_fence_problems(_load_builder(path)):
                failures.append(f"mutation {label!r} was NOT caught")
            else:
                print(f"note: mutation caught ({label}).")
    return failures


# Each mutation rewrites the REAL board-loop.yml in memory the way a later
# edit could reopen #509's gap; check 3 must catch every one.
SPEC_REQUEST_MUTATIONS = (
    ("route site's body inlined again",
     '--body-file "$spec_body_file" --label spec-request',
     '--body "${pr_body:-No drafted body.}" --label spec-request'),
    ("fallback fed the comments-file",
     "ISSUE_CONTEXT_FILE: ${{ steps.issue-context-route.outputs.context-file }}",
     "ISSUE_CONTEXT_FILE: ${{ steps.issue-context-route.outputs.comments-file }}"),
    ("fallback fed an unfiltered issue read",
     "ISSUE_CONTEXT_FILE: ${{ steps.issue-context-breach.outputs.context-file }}",
     "ISSUE_CONTEXT_FILE: /tmp/raw.md"),
    ("builder dropped from the readiness site",
     '--context-file "$ISSUE_CONTEXT_FILE" \\\n'
     '                --notice',
     '--notice'),
    ("breach context fetch disabled",
     "        id: issue-context-breach\n"
     "        if: steps.push-pr.outputs.pr-url != '' && "
     "steps.final-diff-backstop.outputs.breach == 'true'\n",
     "        id: issue-context-breach\n"
     "        if: false\n"),
    ("route title read widened to the body",
     'issue_title="$(gh issue view "$ISSUE_NUMBER" -R "$GITHUB_REPOSITORY" '
     '--json title --jq .title)"\n\n          spec_title=',
     'issue_title="$(gh issue view "$ISSUE_NUMBER" -R "$GITHUB_REPOSITORY" '
     '--json title,body --jq .title)"\n\n          spec_title='),
    # #514: the create guard at each site.
    ("route create guard reduced to an echo",
     '[[ "$spec_url" =~ ^https?://[^[:space:]]+/issues/[0-9]+$ ]] || '
     '{ echo "::error::board-loop route (spec verdict)',
     'echo "::error::board-loop route (spec verdict)'),
    ("fix create guard regex made vacuous",
     '[[ "$spec_url" =~ ^https?://[^[:space:]]+/issues/[0-9]+$ ]] || '
     '{ echo "::error::board-loop fix (post-push breach)',
     '[[ "$spec_url" =~ .* ]] || '
     '{ echo "::error::board-loop fix (post-push breach)'),
    ("route create URL no longer captured",
     'spec_url="$(gh issue create -R "$GITHUB_REPOSITORY" --title "$spec_title"',
     'gh issue create -R "$GITHUB_REPOSITORY" --title "$spec_title"'),
    ("fix create guard exits 0",
     'retries it."; exit 1; }\n'
     '          echo "spec-url=$spec_url" >> "$GITHUB_OUTPUT"\n'
     '          echo "measured=$measured"',
     'retries it."; exit 0; }\n'
     '          echo "spec-url=$spec_url" >> "$GITHUB_OUTPUT"\n'
     '          echo "measured=$measured"'),
    ("fix breach site made continue-on-error",
     "        id: post-push-breach\n",
     "        id: post-push-breach\n        continue-on-error: true\n"),
    ("readiness spec-url output written before the guard",
     '            [[ "$spec_url" =~',
     '            echo "spec-url=$spec_url" >> "$GITHUB_OUTPUT"\n'
     '            [[ "$spec_url" =~'),
    ("readiness re-route comment posted before the guard",
     '            [[ "$spec_url" =~',
     '            gh issue comment "$ISSUE_NUMBER" -R "$GITHUB_REPOSITORY" '
     '--body "re-routed"\n'
     '            [[ "$spec_url" =~'),
    ("route cross-link gated always()",
     "        if: steps.spec_request.outputs.spec-url != ''",
     "        if: always() && steps.spec_request.outputs.spec-url != ''"),
    ("readiness cross-link gated !cancelled()",
     "        if: steps.report-unmet.outputs.spec-url != ''",
     "        if: \"!cancelled() && steps.report-unmet.outputs.spec-url != ''\""),
)


def _mutation_check_spec_request_sites():
    failures = []
    try:
        with open(BOARD_LOOP, encoding="utf-8") as fh:
            original = fh.read()
    except OSError as exc:
        return [f"mutation check: could not read {BOARD_LOOP}: {exc}"]
    with tempfile.TemporaryDirectory() as tmpdir:
        for label, old, new in SPEC_REQUEST_MUTATIONS:
            if old not in original:
                failures.append(
                    f"mutation {label!r} no longer applies ({old!r} not in "
                    f"{BOARD_LOOP}) -- update SPEC_REQUEST_MUTATIONS so "
                    f"this gate stays proven.")
                continue
            path = os.path.join(tmpdir, "board-loop-mutated.yml")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(original.replace(old, new, 1))
            if not check_spec_request_bodies(path):
                failures.append(f"mutation {label!r} was NOT caught")
            else:
                print(f"note: mutation caught ({label}).")
    return failures


_RO_ALLOWED = f"Read,Grep,Glob,{GIT_READ_GRANT},Bash(cat:*)"
_RO_DENIED = "WebSearch,WebFetch,Write,Edit,Bash(git:*),Bash(git push:*)"


def _read_only_fixture(allowed=_RO_ALLOWED, denied=_RO_DENIED,
                       claude_allowed='"${{ steps.ta.outputs.allowed-tools }}"',
                       claude_denied='"${{ steps.ta.outputs.disallowed-tools }}"',
                       extra_step="", claude_extra="", with_extra="",
                       prompt=f"run python3 {GIT_READ_WRAPPER} log -1"):
    """A workflow with the three read-only tool-args sites; the route one
    (id `ta`) takes the given lists and feeds an agent step."""
    def site(label, step_id, allow, deny):
        return ("      - name: Compose tool args (" + label + ")\n"
                f"        id: {step_id}\n"
                "        uses: ./.github/actions/wing-commander-tool-args\n"
                "        with:\n"
                f"          default-allowed-tools: \"{allow}\"\n"
                f"          default-disallowed-tools: \"{deny}\"\n"
                f"          step-label: \"{label}\"\n")
    return ("name: gate-93-fixture-read-only-git\n"
            "jobs:\n"
            "  demo:\n"
            "    steps:\n"
            + site("board-loop.triage-propose", "tt", _RO_ALLOWED, _RO_DENIED)
            + site("board-loop.route-propose", "ta", allowed, denied)
            + site("board-loop.reviewer", "tr", _RO_ALLOWED, _RO_DENIED)
            + site("board-loop.fixer", "tf",
                   "Read,Write,Edit,Bash(git log:*),Bash(git commit:*)",
                   "WebFetch")
            + "      - name: Route-propose\n"
            "        uses: anthropics/claude-code-action@v1\n"
            "        with:\n"
            f"          prompt: \"{prompt}\"\n"
            + with_extra
            + "          claude_args: |\n"
            f"            --allowedTools {claude_allowed}\n"
            f"            --disallowedTools {claude_denied}\n"
            + (f"            {claude_extra}\n" if claude_extra else "")
            + extra_step)


_FLEET_ALLOWED = f"Read,Grep,Bash(gh run view:*),{PUBLISHED_GIT_READ_GRANT}"
_FLEET_DENIED = "WebFetch,Write,Edit,Bash(git:*)"


def _fleet_fixture(allowed=_FLEET_ALLOWED, denied=_FLEET_DENIED,
                   prompt=f"run python3 {PUBLISHED_GIT_READ_WRAPPER} log -1",
                   with_extra="", extra_site=""):
    """A published-stage-shaped workflow for check 4b: one labelled
    read-only site (`stage.ro`, id `ro`) feeding an agent step."""
    return ("name: gate-93-fixture-fleet\n"
            "jobs:\n"
            "  demo:\n"
            "    steps:\n"
            "      - name: Compose tool args (stage.ro)\n"
            "        id: ro\n"
            "        uses: ./.wing-commander-pipeline/.github/actions/wing-commander-tool-args\n"
            "        with:\n"
            f"          default-allowed-tools: \"{allowed}\"\n"
            f"          default-disallowed-tools: \"{denied}\"\n"
            + with_extra +
            "          step-label: \"stage.ro\"\n"
            + extra_site +
            "      - name: Agent\n"
            "        uses: anthropics/claude-code-action@v1\n"
            "        with:\n"
            f"          prompt: \"{prompt}\"\n"
            "          claude_args: |\n"
            "            --allowedTools \"${{ steps.ro.outputs.allowed-tools }}\"\n"
            "            --disallowedTools \"${{ steps.ro.outputs.disallowed-tools }}\"\n")


def _self_test_read_only_git(tmpdir):
    """Check 4 fixtures: the well-formed shape passes (and the fixer's raw
    git grants are left alone); each way of handing a read-only agent a
    write path through git, or of dropping the denies, fails."""
    failures = []
    cases = [
        ("well-formed read-only sites", _read_only_fixture(), None),
        ("raw Bash(git log:*) grant (the #513 shape)",
         _read_only_fixture(allowed=_RO_ALLOWED + ",Bash(git log:*)"),
         "grants raw Bash(git log:*)"),
        ("raw Bash(git diff *) grant",
         _read_only_fixture(allowed=_RO_ALLOWED + ",Bash(git diff *)"),
         "grants raw Bash(git diff *)"),
        ("raw Bash(git:*) grant",
         _read_only_fixture(allowed=_RO_ALLOWED + ",Bash(git:*)"),
         "grants raw Bash(git:*)"),
        ("git by absolute path",
         _read_only_fixture(allowed=_RO_ALLOWED + ",Bash(/usr/bin/git show:*)"),
         "grants raw Bash(/usr/bin/git show:*)"),
        ("Bash(gh pr view:*) grant (the #503 shape)",
         _read_only_fixture(allowed=_RO_ALLOWED + ",Bash(gh pr view:*)"),
         "grants Bash(gh pr view:*) to a read-only agent. `gh pr view"),
        ("gh appended in claude_args",
         _read_only_fixture(claude_allowed=(
             '"${{ steps.ta.outputs.allowed-tools }},Bash(gh pr diff:*)"')),
         "claude_args grants Bash(gh pr diff:*) to a read-only agent"),
        ("an unlisted Bash grant that can write",
         _read_only_fixture(allowed=_RO_ALLOWED + ",Bash(python3:*)"),
         "not in this gate's READ_ONLY_BASH_GRANTS"),
        ("wrapper granted under a different spelling",
         _read_only_fixture(allowed=_RO_ALLOWED.replace(
             GIT_READ_GRANT, "Bash(python3 .github/scripts/board_git_read.py*)")),
         "is not this workflow's git wrapper grant"),
        ("wrapper granted by the published-stage path in board-loop",
         _read_only_fixture(allowed=_RO_ALLOWED.replace(
             GIT_READ_GRANT, PUBLISHED_GIT_READ_GRANT)),
         "is not this workflow's git wrapper grant"),
        ("route no longer grants the wrapper",
         _read_only_fixture(allowed=_RO_ALLOWED.replace(
             "," + GIT_READ_GRANT, "")),
         f"does not grant {GIT_READ_GRANT}"),
        ("prompt never names the wrapper",
         _read_only_fixture(prompt="read the history"),
         f"never tells the agent to run `python3 {GIT_READ_WRAPPER}`"),
        ("prompt names the wrapper by another path",
         _read_only_fixture(prompt=(
             f"run python3 {GIT_READ_WRAPPER} log, or python3 "
             f"{PUBLISHED_GIT_READ_WRAPPER} show")),
         f"names the git wrapper as '{PUBLISHED_GIT_READ_WRAPPER}'"),
        ("prompt tells the agent to run raw git",
         _read_only_fixture(prompt=(
             f"run python3 {GIT_READ_WRAPPER} log, or `git show HEAD`")),
         "tells a read-only agent to run raw 'git show'"),
        ("bare Bash grant",
         _read_only_fixture(allowed=_RO_ALLOWED + ",Bash"),
         "grants bare Bash"),
        ("Write allowed",
         _read_only_fixture(allowed=_RO_ALLOWED + ",Write"),
         "allows Write"),
        ("Bash(git:*) not denied",
         _read_only_fixture(denied=_RO_DENIED.replace(",Bash(git:*)", "")),
         "does not deny Bash(git:*)"),
        ("Edit not denied",
         _read_only_fixture(denied=_RO_DENIED.replace(",Edit", "")),
         "does not deny Edit"),
        ("raw git appended in claude_args",
         _read_only_fixture(claude_allowed=(
             '"${{ steps.ta.outputs.allowed-tools }},Bash(git show:*)"')),
         "claude_args grants raw Bash(git show:*)"),
        ("raw git appended unquoted in claude_args",
         _read_only_fixture(claude_allowed=(
             "${{ steps.ta.outputs.allowed-tools }},Bash(git log:*)")),
         "claude_args grants raw Bash(git log:*)"),
        ("claude_args drops the composite's deny list",
         _read_only_fixture(claude_denied='"WebFetch"'),
         "does not pass steps.ta.outputs.disallowed-tools"),
        ("--permission-mode default is left alone",
         _read_only_fixture(claude_extra="--permission-mode default"), None),
        ("inline settings: without permissions is left alone",
         _read_only_fixture(
             with_extra="          settings: '{\"model\": \"x\"}'\n"), None),
        ("--permission-mode acceptEdits",
         _read_only_fixture(claude_extra="--permission-mode acceptEdits"),
         "sets --permission-mode acceptEdits"),
        ("--permission-mode=bypassPermissions",
         _read_only_fixture(
             claude_extra="--permission-mode=bypassPermissions"),
         "sets --permission-mode bypassPermissions"),
        ("--dangerously-skip-permissions",
         _read_only_fixture(claude_extra="--dangerously-skip-permissions"),
         "passes --dangerously-skip-permissions"),
        ("--settings with a permissions allow list",
         _read_only_fixture(claude_extra=(
             "--settings '{\"permissions\": {\"allow\": [\"Bash(git:*)\"]}}'")),
         "passes --settings"),
        ("--settings pointing at a file",
         _read_only_fixture(claude_extra="--settings /tmp/s.json"),
         "passes --settings"),
        ("settings: input with a permissions allow list",
         _read_only_fixture(with_extra=(
             "          settings: '{\"permissions\": {\"allow\": [\"Write\"]}}'\n")),
         "`settings:` input carries permissions"),
        ("settings: input pointing at a file",
         _read_only_fixture(with_extra="          settings: .claude/s.json\n"),
         "`settings:` input carries permissions"),
        ("a read-only site renamed away (vacuous)",
         _read_only_fixture().replace("board-loop.reviewer", "board-loop.rv"),
         "no tool-args step labelled 'board-loop.reviewer'"),
    ]
    fleet = {"labels": ("stage.ro",), "git_grant": PUBLISHED_GIT_READ_GRANT,
             "strict": False}
    cases = [c + ({},) for c in cases] + [
        ("4b: well-formed published read-only site (gh left alone)",
         _fleet_fixture(), None, fleet),
        ("4b: consumer override inputs are not the shipped list",
         _fleet_fixture(with_extra=(
             "          allowed-tools-override: ${{ inputs.allowed-tools-override }}\n"
             "          disallowed-tools-override: ${{ inputs.disallowed-tools-override }}\n")),
         None, fleet),
        ("4b: raw Bash(git log:*) (the #518 shape)",
         _fleet_fixture(allowed=_FLEET_ALLOWED + ",Bash(git log:*)"),
         "grants raw Bash(git log:*)", fleet),
        ("4b: unrestricted Bash(*)",
         _fleet_fixture(allowed=_FLEET_ALLOWED + ",Bash(*)"),
         "grants unrestricted Bash(*)", fleet),
        ("4b: repo-local wrapper path in a published stage",
         _fleet_fixture(allowed=_FLEET_ALLOWED.replace(
             PUBLISHED_GIT_READ_GRANT, GIT_READ_GRANT)),
         "is not this workflow's git wrapper grant", fleet),
        ("4b: Bash(git:*) not denied",
         _fleet_fixture(denied=_FLEET_DENIED.replace(",Bash(git:*)", "")),
         "does not deny Bash(git:*)", fleet),
        ("4b: prompt names the repo-local wrapper path",
         _fleet_fixture(prompt=f"run python3 {GIT_READ_WRAPPER} log"),
         f"names the git wrapper as '{GIT_READ_WRAPPER}'", fleet),
        ("4b: an unlisted site with no Write/Edit holds raw git",
         _fleet_fixture(extra_site=(
             "      - name: Compose tool args (stage.summary)\n"
             "        id: ts\n"
             "        uses: ./.wing-commander-pipeline/.github/actions/wing-commander-tool-args\n"
             "        with:\n"
             "          default-allowed-tools: \"Read,Bash(git show:*)\"\n"
             "          default-disallowed-tools: \"WebFetch\"\n"
             "          step-label: \"stage.summary\"\n")),
         "grants raw Bash(git show:*)", fleet),
    ]
    for index, (label, text, expect, kwargs) in enumerate(cases):
        path = os.path.join(tmpdir, f"gate-93-fixture-git-{index}.yml")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        problems = check_read_only_git(path, **kwargs)
        if expect is None:
            if problems:
                failures.append(f"check 4 fixture {label!r} should pass but "
                                f"was flagged: {problems!r}")
            continue
        if not problems:
            failures.append(f"check 4 fixture {label!r} was not caught")
        elif expect not in " ".join(problems):
            failures.append(f"check 4 fixture {label!r} was caught without "
                            f"naming {expect!r}: {problems!r}")
        else:
            print(f"note: check 4 fixture {label!r} caught.")
    return failures


def _self_test_git_read_wrapper():
    """git_read.py: log/diff/show with ordinary arguments pass; every
    spelling of --output, -o, and every other subcommand are refused, and
    a refused call runs nothing."""
    import importlib.util
    import subprocess
    failures = []
    try:
        spec = importlib.util.spec_from_file_location("git_read",
                                                      GIT_READ_WRAPPER)
        w = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(w)
    except (OSError, ImportError, SyntaxError) as exc:
        return [f"could not load {GIT_READ_WRAPPER}: {exc}"]

    allowed = (
        ["log", "-1", "--oneline"],
        ["log", "--format=%H %s", "origin/main..HEAD"],
        ["log", "--oneline", "--", ".github/workflows/board-loop.yml"],
        ["diff", "origin/main..HEAD"],
        ["diff", "--stat", "--name-only", "HEAD~1", "HEAD"],
        ["diff", "-O", "orderfile", "HEAD"],
        ["show", "HEAD"],
        ["show", "-s", "--format=%B", "HEAD"],
        ["show", "HEAD:README.md"],
        ["log", "--no-merges", "-S", "output", "--oneline"],
        # Short clusters git accepts today, including values holding 'o'.
        ["log", "-p", "-1"],
        ["diff", "-U3", "HEAD"],
        ["diff", "-M", "-C", "-B", "HEAD"],
        ["diff", "-M50%", "-l1000", "HEAD"],
        ["log", "-Sfoo", "--oneline"],
        ["log", "-Gfoo.*bar", "-p"],
        ["log", "-pSfoo"],
        ["log", "-L1,5:foo.py"],
        ["diff", "-Oorderfile", "HEAD"],
        ["diff", "-Ifoo", "HEAD"],
        ["diff", "-Xfiles,cumulative", "--dirstat", "HEAD"],
        ["log", "-n10", "-3"],
        ["diff", "-pRw", "HEAD"],
    )
    for argv in allowed:
        reason = w.refusal(argv)
        if reason is not None:
            failures.append(f"wrapper refused read-only {argv!r}: {reason}")

    refused = (
        [],
        ["log", "--output=/tmp/x"],
        ["log", "--output", "/tmp/x"],
        ["diff", "--output=/tmp/x"],
        ["show", "HEAD", "--output=/tmp/x"],
        ["log", "--outp=/tmp/x"],
        ["log", "--outpu=/tmp/x"],
        ["log", "--out=/tmp/x"],
        ["log", "--o=/tmp/x"],
        ["diff", "--outp", "/tmp/x"],
        ["show", "--output-indicator-new=+"],
        ["log", "-o", "/tmp/x"],
        ["log", "-o/tmp/x"],
        ["log", "-po", "/tmp/x"],
        ["diff", "-pRo/tmp/x"],
        ["show", "-poS", "x"],
        ["log", "--", "--output=/tmp/x"],
        ["push"],
        ["commit", "-m", "x"],
        ["format-patch", "-1"],
        ["-c", "core.pager=sh", "log"],
        ["-C", "/tmp", "log"],
        ["--git-dir=/tmp", "log"],
        ["LOG"],
        ["log;", "rm"],
    )
    for argv in refused:
        if w.refusal(argv) is None:
            failures.append(f"wrapper did not refuse {argv!r}")

    # A refused call must exit 2 and run nothing -- check it end to end.
    with tempfile.TemporaryDirectory() as tmpdir:
        target = os.path.join(tmpdir, "written.txt")
        result = subprocess.run(
            [sys.executable, GIT_READ_WRAPPER, "log", "-1",
             "--format=format:X", f"--output={target}"],
            capture_output=True, text=True)
        if result.returncode != 2 or os.path.exists(target):
            failures.append(f"wrapper --output call exited "
                            f"{result.returncode} (want 2) or wrote "
                            f"{target}: {result.stderr!r}")
    if not failures:
        print(f"note: {GIT_READ_WRAPPER} unit tests passed ({len(allowed)} "
              f"read-only calls allowed, {len(refused)} write/other "
              f"calls refused, a refused call writes nothing).")
    return failures


# Each mutation rewrites the REAL board-loop.yml in memory the way a later
# edit could reopen #513; check 4 must catch every one.
READ_ONLY_GIT_MUTATIONS = (
    ("route regains Bash(git log:*)",
     f'"Read,Grep,Glob,{GIT_READ_GRANT},Bash(cat:*)"\n'
     '          default-disallowed-tools: "WebSearch,WebFetch,Write,Edit,'
     'Bash(git:*),Bash(git push:*),Bash(git commit:*)"\n'
     '          step-label: "board-loop.route-propose"',
     '"Read,Grep,Glob,Bash(git log:*),Bash(cat:*)"\n'
     '          default-disallowed-tools: "WebSearch,WebFetch,Write,Edit,'
     'Bash(git:*),Bash(git push:*),Bash(git commit:*)"\n'
     '          step-label: "board-loop.route-propose"'),
    ("triage regains Bash(git show:*)",
     f'"Read,Grep,Glob,{GIT_READ_GRANT},Bash(cat:*)"\n'
     '          default-disallowed-tools: "WebSearch,WebFetch,Write,Edit,'
     'Bash(git:*),Bash(git push:*),Bash(gh issue close:*)',
     f'"Read,Grep,Glob,{GIT_READ_GRANT},Bash(cat:*),Bash(git show:*)"\n'
     '          default-disallowed-tools: "WebSearch,WebFetch,Write,Edit,'
     'Bash(git:*),Bash(git push:*),Bash(gh issue close:*)'),
    ("reviewer stops denying Bash(git:*)",
     '"WebSearch,WebFetch,Write,Edit,Bash(git:*),Bash(git push:*),'
     'Bash(git commit:*)"\n'
     '          step-label: "board-loop.reviewer"',
     '"WebSearch,WebFetch,Write,Edit,Bash(git push:*),'
     'Bash(git commit:*)"\n'
     '          step-label: "board-loop.reviewer"'),
    ("reviewer regains Bash(gh pr view:*) (#503)",
     f'"Read,Grep,Glob,{GIT_READ_GRANT},Bash(cat:*)"\n'
     '          default-disallowed-tools: "WebSearch,WebFetch,Write,Edit,'
     'Bash(git:*),Bash(git push:*),Bash(git commit:*)"\n'
     '          step-label: "board-loop.reviewer"',
     f'"Read,Grep,Glob,{GIT_READ_GRANT},Bash(cat:*),Bash(gh pr view:*)"\n'
     '          default-disallowed-tools: "WebSearch,WebFetch,Write,Edit,'
     'Bash(git:*),Bash(git push:*),Bash(git commit:*)"\n'
     '          step-label: "board-loop.reviewer"'),
    ("route agent's claude_args appends raw git",
     '--allowedTools "${{ steps.tool-args-route.outputs.allowed-tools }}"',
     '--allowedTools "${{ steps.tool-args-route.outputs.allowed-tools }},'
     'Bash(git diff:*)"'),
    ("reviewer's claude_args turns on acceptEdits",
     '--allowedTools "${{ steps.tool-args-review.outputs.allowed-tools }}"',
     '--allowedTools "${{ steps.tool-args-review.outputs.allowed-tools }}"\n'
     '            --permission-mode acceptEdits'),
)


def _mutation_check_read_only_git():
    failures = []
    try:
        with open(BOARD_LOOP, encoding="utf-8") as fh:
            original = fh.read()
    except OSError as exc:
        return [f"mutation check: could not read {BOARD_LOOP}: {exc}"]
    with tempfile.TemporaryDirectory() as tmpdir:
        for label, old, new in READ_ONLY_GIT_MUTATIONS:
            if original.count(old) != 1:
                failures.append(
                    f"mutation {label!r} no longer applies ({old!r} is not "
                    f"in {BOARD_LOOP} exactly once) -- update "
                    f"READ_ONLY_GIT_MUTATIONS so this gate stays proven.")
                continue
            path = os.path.join(tmpdir, "board-loop-mutated.yml")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(original.replace(old, new, 1))
            if not check_read_only_git(path):
                failures.append(f"mutation {label!r} was NOT caught")
            else:
                print(f"note: mutation caught ({label}).")
    return failures


_PUB_GRANT_LIT = PUBLISHED_GIT_READ_GRANT
# Each mutation rewrites a REAL workflow other than board-loop.yml in
# memory the way a later edit could reopen #518; check 4b must catch
# every one.
FLEET_READ_ONLY_GIT_MUTATIONS = (
    (".github/workflows/implement.yml",
     "progress composer regains raw git log/diff/show (the #518 shape)",
     f'default-allowed-tools: "{_PUB_GRANT_LIT}"',
     'default-allowed-tools: "Bash(git log:*),Bash(git diff:*),'
     'Bash(git show:*)"'),
    (".github/workflows/implement.yml",
     "progress composer's prompt goes back to raw git log",
     f"              python3 {PUBLISHED_GIT_READ_WRAPPER} log --oneline",
     "              git log --oneline"),
    (".github/workflows/implement.yml",
     "progress composer stops denying Bash(git:*)",
     '"WebSearch,WebFetch,ScheduleWakeup,Monitor,SendMessage,Write,Edit,'
     'Bash(git:*)"',
     '"WebSearch,WebFetch,ScheduleWakeup,Monitor,SendMessage,Write,Edit"'),
    (".github/workflows/watchdog.yml",
     "diagnose regains raw Bash(git diff:*) beside the wrapper",
     f"Bash(gh:*),{_PUB_GRANT_LIT}",
     f"Bash(gh:*),Bash(git diff:*),{_PUB_GRANT_LIT}"),
    (".github/workflows/watchdog.yml",
     "diagnose is granted board-loop's repo-local wrapper path",
     f'"Read,Grep,Bash(gh:*),{_PUB_GRANT_LIT}"',
     f'"Read,Grep,Bash(gh:*),{GIT_READ_GRANT}"'),
    (".github/workflows/watchdog.yml",
     "diagnose's claude_args appends raw git",
     '--allowedTools "${{ steps.tool-args-diagnose.outputs.allowed-tools }}"',
     '--allowedTools "${{ steps.tool-args-diagnose.outputs.allowed-tools }},'
     'Bash(git show:*)"'),
    (".github/workflows/pr-conversation.yml",
     "classify stops denying Bash(git:*)",
     '"Write,Edit,WebSearch,WebFetch,Bash(git:*),Bash(git push:*)',
     '"Write,Edit,WebSearch,WebFetch,Bash(git push:*)'),
    (".github/workflows/pr-conversation.yml",
     "classify's prompt names the repo-local wrapper path",
     f"through `python3 {PUBLISHED_GIT_READ_WRAPPER}`",
     f"through `python3 {GIT_READ_WRAPPER}`"),
    (".github/workflows/pr-conversation.yml",
     "classify is allowed Write (its label still holds it read-only)",
     f'default-allowed-tools: "Read,Grep,Glob,{_PUB_GRANT_LIT}',
     f'default-allowed-tools: "Read,Write,Grep,Glob,{_PUB_GRANT_LIT}'),
    (".github/workflows/finalize.yml",
     "finalize drops Write and becomes a read-only agent holding raw git",
     'default-allowed-tools: "Read,Glob,Grep,Bash(git log:*),'
     'Bash(git diff:*),Bash(git show:*),Write"',
     'default-allowed-tools: "Read,Glob,Grep,Bash(git log:*),'
     'Bash(git diff:*),Bash(git show:*)"'),
)


def _mutation_check_fleet_read_only_git():
    failures = []
    published = set(published_stages("."))
    with tempfile.TemporaryDirectory() as tmpdir:
        for workflow, label, old, new in FLEET_READ_ONLY_GIT_MUTATIONS:
            try:
                with open(workflow, encoding="utf-8") as fh:
                    original = fh.read()
            except OSError as exc:
                failures.append(f"mutation {label!r}: could not read "
                                f"{workflow}: {exc}")
                continue
            if original.count(old) != 1:
                failures.append(
                    f"mutation {label!r} no longer applies ({old!r} is not "
                    f"in {workflow} exactly once) -- update "
                    f"FLEET_READ_ONLY_GIT_MUTATIONS so this gate stays "
                    f"proven.")
                continue
            path = os.path.join(tmpdir, os.path.basename(workflow))
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(original.replace(old, new, 1))
            if not check_read_only_git(
                    path, labels=FLEET_READ_ONLY_STEP_LABELS.get(workflow, ()),
                    git_grant=fleet_git_grant(workflow, published),
                    strict=False):
                failures.append(f"mutation {label!r} was NOT caught")
            else:
                print(f"note: mutation caught ({label}).")
    return failures


# Each mutation rewrites the REAL board-loop.yml in memory the way a later
# edit could reopen #503; check 5 must catch every one.
REVIEWER_STAGING_MUTATIONS = (
    ("prompt names the workspace parent again (the #503 shape)",
     "diff is at\n            /tmp/wing-commander/board-review-diff.txt,",
     "diff is at\n            ${{ github.workspace }}/../board-review-diff.txt,"),
    ("gather writes the diff to $RUNNER_TEMP again",
     "> /tmp/wing-commander/board-review-diff.txt; then",
     '> "$RUNNER_TEMP/board-review-diff.txt"; then'),
    ("gather writes the PR title/body somewhere the prompt does not name",
     "> /tmp/wing-commander/board-review-pr.md; then",
     "> /tmp/wing-commander/board-review-pr.txt; then"),
    ("prompt names the PR file under runner.temp",
     "title and body at\n            /tmp/wing-commander/board-review-pr.md,",
     "title and body at\n            ${{ runner.temp }}/board-review-pr.md,"),
    ("gather writes the commit list to $RUNNER_TEMP",
     "> /tmp/wing-commander/board-review-commits.txt;",
     '> "$RUNNER_TEMP/board-review-commits.txt";'),
    ("gather drops -e (the fail-open shape)",
     "          set -euo pipefail\n          if ! git fetch origin main",
     "          set -uo pipefail\n          if ! git fetch origin main"),
    ("gather drops the empty-diff check",
     "          if [ ! -s /tmp/wing-commander/board-review-diff.txt ]; then\n",
     "          if false; then\n"),
    ("empty-diff check no longer exits",
     "is empty -- refusing to review nothing.\"\n            exit 1\n",
     "is empty -- refusing to review nothing.\"\n"),
    ("prompt tells the reviewer to run gh pr view again",
     "no `gh` access.",
     "no `gh` access. Or run `gh pr view --comments`."),
)


def _mutation_check_reviewer_staging():
    failures = []
    try:
        with open(BOARD_LOOP, encoding="utf-8") as fh:
            original = fh.read()
    except OSError as exc:
        return [f"mutation check: could not read {BOARD_LOOP}: {exc}"]
    with tempfile.TemporaryDirectory() as tmpdir:
        for label, old, new in REVIEWER_STAGING_MUTATIONS:
            if original.count(old) != 1:
                failures.append(
                    f"mutation {label!r} no longer applies ({old!r} is not "
                    f"in {BOARD_LOOP} exactly once) -- update "
                    f"REVIEWER_STAGING_MUTATIONS so this gate stays proven.")
                continue
            path = os.path.join(tmpdir, "board-loop-mutated.yml")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(original.replace(old, new, 1))
            if not check_reviewer_staged_inputs(path):
                failures.append(f"mutation {label!r} was NOT caught")
            else:
                print(f"note: mutation caught ({label}).")
    return failures


def run_self_test():
    failures = []

    with tempfile.TemporaryDirectory() as tmpdir:
        # Fixture 1: a board-loop-shaped tool-args call granting gh issue view.
        bad_grant_path = os.path.join(tmpdir, "gate-93-fixture-grant.yml")
        with open(bad_grant_path, "w", encoding="utf-8") as fh:
            fh.write(
                "name: gate-93-fixture\n"
                "jobs:\n"
                "  demo:\n"
                "    steps:\n"
                "      - name: Compose tool args (triage-propose)\n"
                "        uses: ./.github/actions/wing-commander-tool-args\n"
                "        with:\n"
                "          default-allowed-tools: \"Read,Bash(gh issue view:*)\"\n"
                "          default-disallowed-tools: \"WebFetch\"\n"
                "          step-label: \"board-loop.triage-propose\"\n"
            )
        grant_problems = check_tool_grants(bad_grant_path)
        if not grant_problems:
            failures.append(
                "fixture 1 (a tool-args call granting Bash(gh issue "
                "view:*)) was not caught")
        elif "gh issue view" not in " ".join(grant_problems):
            failures.append(
                f"fixture 1 was caught but did not name the offending "
                f"fragment: {grant_problems!r}")
        else:
            print(f"note: fixture 1 (gh issue view grant) caught: {grant_problems}")

        # Fixture 1b (#499 rounds 4-5): the exact bypasses the reviews
        # found -- a bare subcommand grant (Bash(gh issue:*)), a fully-
        # open grant spelled three equivalent ways (Bash(gh:*),
        # Bash(gh*), Bash(gh *)), a bare Bash grant and a Bash(*) grant
        # (both unrestricted -- authorize every gh subcommand among
        # everything else), and a literal grant appended directly inside
        # an agent step's own claude_args --allowedTools text rather than
        # through the tool-args composite at all, and (#503) a
        # Bash(gh pr view:*) grant, which reads PR comments unfiltered.
        # Each must be caught.
        bypass_path = os.path.join(tmpdir, "gate-93-fixture-bypass.yml")
        with open(bypass_path, "w", encoding="utf-8") as fh:
            fh.write(
                "name: gate-93-fixture-bypass\n"
                "jobs:\n"
                "  demo:\n"
                "    steps:\n"
                "      - name: Compose tool args (route-propose)\n"
                "        uses: ./.github/actions/wing-commander-tool-args\n"
                "        with:\n"
                "          default-allowed-tools: \"Read,Bash(gh issue:*)\"\n"
                "          extra-allowed-tools: \"Bash(gh:*),Bash(gh*),Bash(gh *)\"\n"
                "          step-label: \"board-loop.route-propose\"\n"
                "      - name: Compose tool args (fixer)\n"
                "        uses: ./.github/actions/wing-commander-tool-args\n"
                "        with:\n"
                "          default-allowed-tools: \"Bash,Bash(*)\"\n"
                "          step-label: \"board-loop.fixer\"\n"
                "      - name: Route-propose\n"
                "        uses: anthropics/claude-code-action@v1\n"
                "        with:\n"
                "          claude_code_oauth_token: token\n"
                "          prompt: hello\n"
                "          claude_args: |\n"
                "            --allowedTools \"${{ steps.tool-args-route.outputs.allowed-tools }},Bash(gh issue view:*)\"\n"
                "      - name: Reviewer\n"
                "        uses: anthropics/claude-code-action@v1\n"
                "        with:\n"
                "          claude_code_oauth_token: token\n"
                "          prompt: hello\n"
                "          claude_args: |\n"
                "            --allowedTools \"Read,Bash(gh pr view:*)\"\n"
            )
        bypass_problems = check_tool_grants(bypass_path)
        joined_bypass = " ".join(bypass_problems)
        expect_all = ("gh issue:*", "gh:*", "gh*", "gh *", "gh issue view:*",
                      "gh pr view:*",
                      "bare Bash grant (unrestricted, no argument at all",
                      "Bash(*) (unrestricted")
        missing = [e for e in expect_all if e not in joined_bypass]
        if missing:
            failures.append(
                f"fixture 1b did not catch all bypasses -- missing "
                f"{missing!r}: {bypass_problems!r}")
        if not missing:
            print(f"note: fixture 1b (bare/open-in-every-spelling/bare-"
                  f"Bash/claude_args-appended/gh pr view bypasses) "
                  f"caught: {bypass_problems}")

        # Fixture 2: a second file re-implementing all three trust-filter
        # fragments.
        bad_reimpl_path = os.path.join(tmpdir, "gate-93-fixture-reimpl.yml")
        with open(bad_reimpl_path, "w", encoding="utf-8") as fh:
            fh.write(
                'name: gate-93-fixture-reimpl\n'
                'jobs:\n'
                '  demo:\n'
                '    steps:\n'
                '      - run: |\n'
                '          gh api "repos/x/y/issues/1/comments" --paginate --jq \'.[]\' | jq -s \'.\' > raw.json\n'
                '          jq -r \'[.[] | select(.user.type != "Bot")] | .[] | "## Comment by @\\(.user.login)"\' raw.json\n'
            )
        reimpl_problems = check_single_home(bad_reimpl_path, ISSUE_CONTEXT_ACTION)
        if not reimpl_problems:
            failures.append(
                "fixture 2 (a second file re-implementing all three "
                "trust-filter fragments) was not caught")
        else:
            print(f"note: fixture 2 (re-implementation) caught: {reimpl_problems}")

        # The exempt file itself (a copy of the real composite) must never
        # be flagged by check 2, even though it legitimately carries all
        # three fragments.
        if os.path.isfile(ISSUE_CONTEXT_ACTION):
            self_problems = check_single_home(ISSUE_CONTEXT_ACTION, ISSUE_CONTEXT_ACTION)
            if self_problems:
                failures.append(
                    f"the exempt file (wing-commander-issue-context/"
                    f"action.yml) was flagged against itself: "
                    f"{self_problems!r}")

        failures.extend(_self_test_spec_request_sites(tmpdir))
        failures.extend(_self_test_read_only_git(tmpdir))
    failures.extend(_self_test_builder())
    failures.extend(_mutation_check_builder())
    failures.extend(_mutation_check_spec_request_sites())
    failures.extend(_self_test_git_read_wrapper())
    failures.extend(_mutation_check_read_only_git())
    failures.extend(_mutation_check_fleet_read_only_git())
    failures.extend(_mutation_check_reviewer_staging())

    # Re-confirm the real fleet still passes, so a self-test fixture
    # leaking into the real check cannot read as green.
    if check_repo():
        failures.append(
            "the real fleet no longer passes after running the self-test "
            "fixtures -- the fixtures mutated shared state.")

    return failures


def main():
    use_utf8_stdout()
    if not os.path.isdir(".github"):
        sys.exit("::error::run this from the repository root; "
                  ".github not found.")

    self_test = "--self-test" in sys.argv[1:]

    real_problems = check_repo()
    for p in real_problems:
        print(f"::error::Gate 93: {p}")
    if real_problems:
        print(f"Gate 93: {len(real_problems)} problem(s).")
        return 1
    print("Gate 93: board-loop.yml grants no agent step gh issue view/gh "
          "api/gh pr, wing-commander-issue-context's trust filter has exactly "
          "one home, and every spec-request board-loop.yml files takes "
          "its body from board_spec_request_body.py with the "
          "composite's context-file as its fallback. Its read-only agents "
          "get git only through git_read.py, with Bash(git:*), Write "
          "and Edit denied, and so do the read-only agents of every other "
          "workflow (by the pipeline-checkout path in a published stage). "
          "The reviewer prompt names only files its "
          "gather step writes.")

    if not self_test:
        return 0

    self_test_failures = run_self_test()
    if self_test_failures:
        for f in self_test_failures:
            print(f"::error::Gate 93 self-test: {f}")
        print(f"Gate 93 self-test: {len(self_test_failures)} failure(s).")
        return 1

    print("Gate 93 self-test: every fixture (a direct grant, the bare/"
          "open/claude_args-appended bypasses, and the inline "
          "re-implementation, every spec-request site that skips the "
          "trust-filtered fallback, every raw-git or missing-deny grant "
          "to a read-only agent, and every mutation of the real "
          "sites) was caught, git_read.py refused every --output "
          "spelling, the exempt file and the well-formed site were "
          "left alone, every mutation of the reviewer's staged inputs "
          "was caught, the "
          "spec-request body builder passed its unit tests, and the "
          "real fleet passes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
