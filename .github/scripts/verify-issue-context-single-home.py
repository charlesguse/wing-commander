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
   - make no unfiltered issue read of its own: no `gh api` on an issue,
     no `gh issue view` with `--comments` or a `--json` field list naming
     `body` or `comments` (FR-056 -- the spec-request body feeds intake).
   `gh issue edit --add-label spec-request` is also flagged: relabelling
   an existing issue would file a spec-request whose body never went
   through the builder. The check fails on zero sites too, so a rename of
   the label or the command cannot turn it vacuous. The builder's own
   behaviour (fallback order, the "No drafted body." line, truncation
   under 65536 characters with a visible note) is exercised by
   `--self-test`.

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
UNFILTERED_READ_RES = (
    (re.compile(r"gh\s+api\b[^\n]*issues"), "a `gh api` issue read"),
    (re.compile(r"gh\s+issue\s+view\b[^\n]*--comments"),
     "`gh issue view --comments`"),
    (re.compile(r"gh\s+issue\s+view\b[^\n]*--json[= ]\s*[\"']?[\w,]*"
                r"\b(?:body|comments)\b"),
     "a `gh issue view --json` read of body/comments"),
)


def _logical_lines(run_text):
    """Shell logical lines: backslash-newline continuations joined."""
    return re.sub(r"\\\n\s*", " ", run_text or "").split("\n")


def _is_spec_request_create(line):
    return bool(re.search(r"\bgh\s+issue\s+create\b", line)
                and "spec-request" in line)


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
        context_step_ids = set()
        for step in steps:
            if not isinstance(step, dict):
                continue
            if ISSUE_CONTEXT_USES in str(step.get("uses") or ""):
                if step.get("id"):
                    context_step_ids.add(str(step["id"]))
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

            creates = [line for line in lines if _is_spec_request_create(line)]
            if not creates:
                continue
            sites += len(creates)

            builder_lines = [line for line in lines
                             if "board_spec_request_body.py" in line]
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

            for line in builder_lines:
                ctx_vars = [m.group(1)
                            for m in BUILDER_CONTEXT_RE.finditer(line)]
                if len(ctx_vars) != 1:
                    problems.append(
                        f"{where}: {SPEC_REQUEST_BUILDER} must get exactly "
                        f"one --context-file \"$VAR\" (found "
                        f"{len(ctx_vars)}) -- without it an empty drafted "
                        f"body has no trust-filtered fallback.")
                    continue
                var = ctx_vars[0]
                expr = str(env.get(var) or "").strip()
                match = CONTEXT_FILE_EXPR_RE.match(expr)
                if not match:
                    problems.append(
                        f"{where}: {SPEC_REQUEST_BUILDER}'s --context-file "
                        f"\"${var}\" is {expr or '(not set in env:)'!r}, "
                        f"not a wing-commander-issue-context step's "
                        f"context-file output -- the fallback must read "
                        f"the composite's trust-filtered file and nothing "
                        f"else (FR-056).")
                elif match.group(1) not in context_step_ids:
                    problems.append(
                        f"{where}: --context-file comes from step "
                        f"{match.group(1)!r}, which is not an earlier "
                        f"wing-commander-issue-context step in job "
                        f"{job_id!r}.")

            for line in lines:
                for pattern, label in UNFILTERED_READ_RES:
                    if pattern.search(line):
                        problems.append(
                            f"{where} makes {label} -- unfiltered issue "
                            f"content must never reach a spec-request "
                            f"body (FR-056); read the composite's "
                            f"context-file through {SPEC_REQUEST_BUILDER}.")

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
    '          spec_body_file="$RUNNER_TEMP/body.md"\n'
    '          python3 .github/scripts/board_spec_request_body.py '
    '--context-file "$ISSUE_CONTEXT_FILE" \\\n'
    '            --footer "f" --out "$spec_body_file" \\\n'
    '            || printf \'No drafted body.\\n\' > "$spec_body_file"\n'
    '          gh issue create -R "$GITHUB_REPOSITORY" --title "t" \\\n'
    '            --body-file "$spec_body_file" \\\n'
    '            --label spec-request\n'
)


def _site_fixture(run=_GOOD_SITE_RUN,
                  context_env="${{ steps.ctx.outputs.context-file }}",
                  context_step_first=True):
    fetch = (
        "      - name: Fetch issue context\n"
        "        id: ctx\n"
        "        uses: ./.github/actions/wing-commander-issue-context\n"
        "        with:\n"
        "          token: t\n"
        "          issue-number: 1\n"
    )
    site = (
        "      - name: File the spec-request\n"
        "        env:\n"
        f"          ISSUE_CONTEXT_FILE: {context_env}\n"
        "        run: |\n" + run
    )
    body = fetch + site if context_step_first else site + fetch
    return ("name: gate-93-fixture-spec-request\n"
            "jobs:\n"
            "  route:\n"
            "    steps:\n" + body)


def _self_test_spec_request_sites(tmpdir):
    """Check 3 fixtures: a well-formed site passes; each way of filing a
    spec-request whose body can skip the trust-filtered fallback, or whose
    fallback reads something other than the composite's context-file,
    fails and names why."""
    failures = []
    good = _GOOD_SITE_RUN
    cases = [
        ("good site", _site_fixture(), None),
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
        ("unfiltered gh issue view --json body,comments read",
         _site_fixture(run=good.replace(
             '          spec_body_file=',
             '          gh issue view 1 --json body,comments > "$RUNNER_TEMP/raw.json"\n'
             '          spec_body_file=')),
         "read of body/comments"),
        ("unfiltered gh issue view --comments read",
         _site_fixture(run=good.replace(
             '          spec_body_file=',
             '          gh issue view 1 --comments > "$RUNNER_TEMP/raw.md"\n'
             '          spec_body_file=')),
         "gh issue view --comments"),
        ("unfiltered gh api issue read",
         _site_fixture(run=good.replace(
             '          spec_body_file=',
             '          gh api "repos/x/y/issues/1/comments" > raw.json\n'
             '          spec_body_file=')),
         "a `gh api` issue read"),
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


def _self_test_builder():
    """board_spec_request_body.py: fallback order, the one-line fallback,
    and truncation under GitHub's body limit with a visible note."""
    failures = []
    try:
        b = _load_builder()
    except (OSError, ImportError, SyntaxError) as exc:
        return [f"could not load {SPEC_REQUEST_BUILDER}: {exc}"]

    ctx = "## Issue\n\nTitle\n\nThe issue body."
    body = b.build_body(drafted="", context=ctx, footer="Routed from x")
    if not body.startswith(b.CONTEXT_HEADING + "\n\n" + ctx):
        failures.append(f"builder: an empty drafted body did not fall back "
                        f"to the labelled context: {body[:200]!r}")
    if not body.endswith("\n\n---\nRouted from x"):
        failures.append(f"builder: footer missing or misplaced: {body!r}")

    body = b.build_body(drafted="Drafted.", context=ctx)
    if body != "Drafted." or ctx in body:
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

    huge = "## Issue\n\n" + ("x" * 50000) + ("\U0001F600" * 20000)
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
    if not failures:
        print("note: builder unit tests passed (fallback order, one-line "
              "fallback, truncation under the limit with a note).")
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
