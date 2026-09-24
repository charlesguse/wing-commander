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
   against a forbidden-prefix list, not a substring: `gh` bare (a `gh:*`
   grant authorizes every gh subcommand), `gh issue *`, `gh api*`, and
   `gh search issues*`. Prefix matching on whitespace-split tokens closes
   the substring check's own holes (`Bash(gh issue:*)`,
   `Bash(gh:*)` both slipped through the old `"gh issue view" in value`
   test). `Bash(gh pr view:*)` is deliberately NOT forbidden here -- the
   reviewer legitimately keeps it for now (a separate issue tracks
   removing it); this gate only closes the issue-read hole #499 exists
   for. Scoped to board-loop.yml only: intake.yml legitimately grants its
   own agent `Bash(gh issue view:*)` for title/body (it never grants
   comment access that way -- comments are staged, code-filtered, by the
   same composite), and this gate is not the place to relitigate that
   design.
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

`--self-test`: synthetic tempdir fixtures prove each check can fail (a
board-loop tool-args grant carrying `gh issue view`, and a second file
re-implementing all three trust-filter fragments), and that the real
fleet passes both.
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
    """Every `Bash(...)` grant in `text` whose gh command matches one of
    FORBIDDEN_GH_PREFIXES, by whitespace-split token prefix -- not by
    substring, which a `Bash(gh issue:*)` or bare `Bash(gh:*)` grant (#499
    round 4 review) slips past. Returns the list of raw fragment strings
    that matched."""
    hits = []
    for m in BASH_GRANT_RE.finditer(text or ""):
        inner = m.group(1).strip()
        # Strip a trailing ":*" / "*" wildcard suffix (the ":" separates
        # the command from its argument wildcard, e.g. "gh issue view:*";
        # a bare "gh:*" has no command before the colon at all beyond
        # "gh" itself).
        command = inner.split(":", 1)[0].strip()
        tokens = tuple(command.split())
        if not tokens or tokens[0] != "gh":
            continue
        if len(tokens) == 1:
            # A bare "gh" command (a `Bash(gh:*)` grant) authorizes every
            # gh subcommand outright, including the three forbidden ones.
            hits.append(inner)
            continue
        for prefix in FORBIDDEN_GH_PREFIXES:
            if tokens[:len(prefix)] == prefix:
                hits.append(inner)
                break
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
            for fragment in find_forbidden_gh_grants(value):
                problems.append(
                    f"{path}: step {name!r}'s {key} grants "
                    f"Bash({fragment}) to a board-loop agent -- read the "
                    f"issue through wing-commander-issue-context instead "
                    f"(single home for the trust filter; #499).")

    for step in find_agent_steps(doc):
        name = step.get("name") or step.get("id") or "(unnamed step)"
        with_block = step.get("with") or {}
        if not isinstance(with_block, dict):
            continue
        claude_args = str(with_block.get("claude_args") or "")
        for fragment in find_forbidden_gh_grants(claude_args):
            problems.append(
                f"{path}: agent step {name!r}'s claude_args grants "
                f"Bash({fragment}) directly -- read the issue through "
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


def check_repo():
    problems = []
    problems.extend(check_tool_grants(BOARD_LOOP))
    for path in gather_scannable_files():
        problems.extend(check_single_home(path, ISSUE_CONTEXT_ACTION))
    return problems


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

        # Fixture 1b (#499 round 4): the exact bypasses the review found --
        # a bare subcommand grant (Bash(gh issue:*)), a fully-open grant
        # (Bash(gh:*)), and a literal grant appended directly inside an
        # agent step's own claude_args --allowedTools text rather than
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
                "          extra-allowed-tools: \"Bash(gh:*)\"\n"
                "          step-label: \"board-loop.route-propose\"\n"
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
        expect_all = ("gh issue:*", "gh:*", "gh issue view:*")
        missing = [e for e in expect_all if e not in joined_bypass]
        if missing:
            failures.append(
                f"fixture 1b did not catch all three bypasses -- missing "
                f"{missing!r}: {bypass_problems!r}")
        if "gh pr view" in joined_bypass:
            failures.append(
                f"fixture 1b's legitimate Bash(gh pr view:*) grant "
                f"(reviewer's, carved out by #499 round 4) was wrongly "
                f"flagged: {bypass_problems!r}")
        if not missing and "gh pr view" not in joined_bypass:
            print(f"note: fixture 1b (bare/open/claude_args-appended "
                  f"bypasses) caught, gh pr view left alone: "
                  f"{bypass_problems}")

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
          "api, and wing-commander-issue-context's trust filter has "
          "exactly one home.")

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
          "re-implementation) was caught, the legitimate gh pr view "
          "grant and the exempt file were both left alone, and the real "
          "fleet passes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
