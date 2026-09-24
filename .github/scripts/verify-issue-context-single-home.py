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
   through), `gh issue *`, `gh api*`, and `gh search issues*`. A bare
   `Bash` (no argument at all) or `Bash(*)` grant is ALSO forbidden here,
   for the same reason -- it authorizes every gh subcommand too, among
   everything else. Prefix matching on whitespace-split tokens closes the
   substring check's own holes (`Bash(gh issue:*)`, `Bash(gh:*)` both
   slipped through the old `"gh issue view" in value` test).
   `Bash(gh pr view:*)` is deliberately NOT forbidden here -- the reviewer
   legitimately keeps it for now (a separate issue tracks removing it);
   this gate only closes the issue-read hole #499 exists for. Scoped to
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
     the spec-request body feeds intake).
   `gh issue edit --add-label spec-request` is also flagged: relabelling
   an existing issue would file a spec-request whose body never went
   through the builder. So is any `gh issue create` in board-loop.yml
   whose `--label` comes through a variable: the check cannot tell
   whether that files a spec-request, so it fails closed. The check fails
   on zero sites too, so a rename of the label or the command cannot turn
   it vacuous. The builder's own behaviour (fallback order, the "No
   drafted body." line, a fence no content can close so @mentions and #N
   references stay inert, truncation under 65536 characters with a
   visible note) is exercised by `--self-test`.

`--self-test`: synthetic tempdir fixtures prove each check can fail (a
board-loop tool-args grant carrying `gh issue view`, a second file
re-implementing all three trust-filter fragments, and spec-request
creation steps that bypass the builder, feed it the wrong file, or read
the issue unfiltered), unit-test board_spec_request_body.py, run a
mutation check (each mutation of the real board-loop.yml's spec-request
sites must be caught), and confirm the real fleet passes.
"""
import glob
import os
import re
import sys
import tempfile

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_shell_harness import use_utf8_stdout  # noqa: E402

BOARD_LOOP = ".github/workflows/board-loop.yml"
ISSUE_CONTEXT_ACTION = ".github/actions/wing-commander-issue-context/action.yml"
TOOL_ARGS_USES = "wing-commander-tool-args"
AGENT_ACTION_PREFIX = "anthropics/claude-code-action@"

# Each entry is the whitespace-split token prefix a `Bash(gh ...)` grant's
# command must NOT start with (checked against multi-token commands only
# -- a bare `gh:*` grant, with no subcommand argument at all, is checked
# separately below since it is not a "prefix" of anything, it authorizes
# every gh subcommand outright, including these three).
FORBIDDEN_GH_PREFIXES = (
    ("gh", "issue"),
    ("gh", "api"),
    ("gh", "search", "issues"),
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
    `gh`/`gh issue`/`gh api`/`gh search issues`, whether through a
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
                    f"(single home for the trust filter; #499).")

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
                f"the trust filter; #499).")
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

            creates = [line for line in lines if _is_spec_request_create(line)]
            if not creates:
                continue
            sites += len(creates)

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
    for path in gather_scannable_files():
        problems.extend(check_single_home(path, ISSUE_CONTEXT_ACTION))
    return problems


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
    '          gh issue create -R "$GITHUB_REPOSITORY" --title "$issue_title" \\\n'
    '            --body-file "$spec_body_file" \\\n'
    '            --label spec-request\n'
)
_BEFORE_BUILDER = '          spec_body_file='


def _site_fixture(run=_GOOD_SITE_RUN,
                  context_env="${{ steps.ctx.outputs.context-file }}",
                  context_step_first=True, fetch_if=None,
                  site_if="steps.x.outputs.y != 'true'"):
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
        + (f"        if: {site_if}\n" if site_if is not None else "")
        + "        env:\n"
        f"          ISSUE_CONTEXT_FILE: {context_env}\n"
        "        run: |\n" + run
    )
    body = fetch + site if context_step_first else site + fetch
    return ("name: gate-93-fixture-spec-request\n"
            "jobs:\n"
            "  route:\n"
            "    steps:\n" + body)


def _insert_before_builder(line):
    return _GOOD_SITE_RUN.replace(_BEFORE_BUILDER,
                                  "          " + line + "\n" + _BEFORE_BUILDER)


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


def _load_builder():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "board_spec_request_body", SPEC_REQUEST_BUILDER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fenced_inner(b, body):
    """(fence, inner text) of the one fenced context block in `body`, or
    (None, None) when the block is not well formed: an opening fence line
    right after the heading and the SAME fence alone on a later line, with
    no line in between that could close it (a backtick run at least as
    long, alone on its line after up to three spaces)."""
    lines = body.split("\n")
    try:
        start = lines.index(b.CONTEXT_HEADING) + 2
    except ValueError:
        return None, None
    fence = lines[start] if start < len(lines) else ""
    if not re.fullmatch(r"`{3,}", fence):
        return None, None
    for end in range(start + 1, len(lines)):
        m = re.fullmatch(r" {0,3}(`{3,})\s*", lines[end])
        if m and len(m.group(1)) >= len(fence):
            if lines[end] != fence:
                return None, None  # closed early by the content
            return fence, "\n".join(lines[start + 1:end])
    return None, None


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

    body = b.build_body(drafted="Drafted.", context=ctx)
    if body != "Drafted." or "Title" in body:
        failures.append(f"builder: a drafted body should win over the "
                        f"context: {body!r}")

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
        if label == "context":
            fence, inner = _fenced_inner(b, body)
            if inner is None or not huge.startswith(inner):
                failures.append("builder: truncating an oversized context "
                                "left the fence unclosed or broken")
            elif body.index("_[Truncated:") < body.rindex(fence):
                failures.append("builder: the truncation note landed inside "
                                "the fence, where it would not render")
    if not failures:
        print("note: builder unit tests passed (fallback order, one-line "
              "fallback, inert @/# inside an unbreakable fence, truncation "
              "under the limit with a note).")
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
     '              --notice',
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
        # through the tool-args composite at all. Each must be caught,
        # and the legitimate Bash(gh pr view:*) grant alongside them must
        # NOT be (reviewer keeps it; #499 round 4 explicitly carves it
        # out, a separate issue tracks removing it).
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
                      "bare Bash grant (unrestricted, no argument at all",
                      "Bash(*) (unrestricted")
        missing = [e for e in expect_all if e not in joined_bypass]
        if missing:
            failures.append(
                f"fixture 1b did not catch all bypasses -- missing "
                f"{missing!r}: {bypass_problems!r}")
        if "gh pr view" in joined_bypass:
            failures.append(
                f"fixture 1b's legitimate Bash(gh pr view:*) grant "
                f"(reviewer's, carved out by #499 round 4) was wrongly "
                f"flagged: {bypass_problems!r}")
        if not missing and "gh pr view" not in joined_bypass:
            print(f"note: fixture 1b (bare/open-in-every-spelling/bare-"
                  f"Bash/claude_args-appended bypasses) caught, gh pr "
                  f"view left alone: {bypass_problems}")

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
    failures.extend(_self_test_builder())
    failures.extend(_mutation_check_spec_request_sites())

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
          "api, wing-commander-issue-context's trust filter has exactly "
          "one home, and every spec-request board-loop.yml files takes "
          "its body from board_spec_request_body.py with the "
          "composite's context-file as its fallback.")

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
          "trust-filtered fallback, and every mutation of the real "
          "sites) was caught, the legitimate gh pr view grant, the "
          "exempt file and the well-formed site were left alone, the "
          "spec-request body builder passed its unit tests, and the "
          "real fleet passes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
