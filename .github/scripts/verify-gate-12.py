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

A gate that never fires is indistinguishable from one whose detection logic
is broken (gate 5 exists because that already happened once — a verifier sat
green for weeks checking a filter that did not ship). So this script runs
the SHIPPED gate, verify-gate-12-token-permissions.py, and the shared
locator it reads `run:` blocks with, wc_gh_callsites.py (specs/113-gh-
callsite-locator), five ways:

  1. fixtures: synthetic workflow trees that each carry one known-bad call
     (or one known-fine one) and an assertion on the verdict, including
     what the error text names (FIXTURES);
  2. the locator on its own, snippet by snippet, including the mention/call
     boundary of each clause of the authoring rule (LOCATOR_CASES);
  3. the acceptance corpus: the 183 scenarios of the closed PR #969
     (gate-12-corpus.json). Each one #969 expected to fail still fails; the
     only verdict that may change is pass -> disallowed, and only where the
     scenario says `changed_from_969` (FR-014);
  4. a seeded differential against real bash: generated scripts run under a
     stub `gh` that records its argv, and every invocation bash actually ran
     must be one the locator found or rejected as disallowed (FR-015, SC-001);
  5. a mutation: a locator that calls a real call a mention must turn the
     corpus red (FR-016).

Usage: python3 .github/scripts/verify-gate-12.py
"""
import concurrent.futures
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "gate-12-fuzz"))
import wc_gh_callsites as loc  # noqa: E402
import wc_shell_harness as harness  # noqa: E402

GATE = os.path.join(HERE, "verify-gate-12-token-permissions.py")
LOCATOR = os.path.join(HERE, "wc_gh_callsites.py")
CORPUS = os.path.join(HERE, "gate-12-corpus.json")
FUZZ_DIR = os.path.join(HERE, "gate-12-fuzz")

_N = chr(10)

# One scenario runs in well under a second; a gate still running after this
# long is not terminating in time, which on the real fleet is a CI job that
# hangs until its timeout instead of failing.
CASE_TIMEOUT_S = 30
# The differential's fixed seed range and size: bounded CI time (FR-015).
FUZZ_SEED, FUZZ_COUNT = 969, 400
# Scenarios the mutation check replays; enough that one real call among them
# is certain to be among the ones the mutated locator hides.
MUTATION_SAMPLE = 12

AUTHORING_RULE = "Authoring rule for `gh` call sites"

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

APP_ENV = 'GH_TOKEN: ${{ steps.ctx.outputs.token }}'
DEFAULT_ENV = 'GH_TOKEN: ${{ github.token }}'

ACTIONS_WRITE = "      actions: write\n"
ISSUES_READ = "      issues: read\n"


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


def mkcase(job_perms, job_env, env_lines, run_lines, docs=DOCS_OK):
    return {
        ".github/workflows/w.yml": wf(step(env_lines, run_lines),
                                      job_perms=job_perms, job_env=job_env),
        "docs/setup.md": docs,
    }


# With one env line and no job permissions, `wf` puts the step's first run
# line on line 12 of w.yml; a failure must name exactly that line (FR-005).
FIRST_RUN_LINE = 12
DISALLOWED = "gh call in a form Gate 12 cannot verify"
UNUSED_COMPOSITE = {
    ".github/actions/wing-commander-probe/action.yml":
        "name: probe" + _N + "description: fixture" + _N + "runs:" + _N +
        "  using: composite" + _N + "  steps:" + _N + "    - name: Render" + _N +
        "      shell: bash" + _N + "      run: |" + _N +
        "        gh issue view 5" + _N,
    "docs/setup.md": DOCS_OK,
}
BIG_HEREDOC = ["cat <<'EOF'"] + ["a b c"] * 60000 + ["EOF", "gh issue view 5"]

# name, files, expect_fail, must_mention
FIXTURES = [
    # --- US1: allowed forms are checked ---------------------------------
    ("a statement-level call is checked: App-token `gh run cancel` fails, "
     "naming file and line",
     mkcase("", "", [APP_ENV], ['gh run cancel "$RUN_ID"']),
     True, ("run cancel", "App token", f".github/workflows/w.yml :: work / step")),

    ("a GH_TOKEN= prefix wins over the step's token",
     mkcase(ACTIONS_WRITE, "", [APP_ENV, "DISPATCH: ${{ github.token }}"],
            ['GH_TOKEN="$DISPATCH" gh run cancel "$RUN_ID"']),
     False, ()),

    ("a call as the first command of a one-level $( ) is checked",
     mkcase("", "", [APP_ENV], ['r="$(gh run list -R "$REPO")"']),
     True, ("run list", "App token")),

    # --- US1: unprovable forms fail closed, naming file:line and the rule --
    ("backticks: a call inside them fails closed",
     mkcase("", "", [APP_ENV], ["x=`gh issue view 5`"]),
     True, (DISALLOWED, "(backtick)", AUTHORING_RULE,
            f".github/workflows/w.yml:{FIRST_RUN_LINE}:")),

    ("a nested $( $( ) ) fails closed",
     mkcase("", "", [APP_ENV], ['x="$(echo "$(gh issue view 5)")"']),
     True, (DISALLOWED, "(nested-substitution)", AUTHORING_RULE)),

    ("a $( ) whose gh is not its first command fails closed",
     mkcase("", "", [APP_ENV], ['x="$(cd /tmp && gh issue view 5)"']),
     True, (DISALLOWED, "(substitution-not-first)")),

    ("a variable subcommand fails closed",
     mkcase("", "", [APP_ENV], ['gh "$VERB" list']),
     True, (DISALLOWED, "(variable-subcommand)")),

    ("a variable second subcommand word fails closed",
     mkcase("", "", [APP_ENV], ['gh issue "$ACTION" 5']),
     True, (DISALLOWED, "(variable-subcommand)")),

    ("a variable `gh api` method fails closed",
     mkcase("", "", [APP_ENV], ['gh api -X "$M" "repos/$REPO/issues/1"']),
     True, (DISALLOWED, "(variable-method)")),

    ("a wrapper before gh fails closed",
     mkcase("", "", [APP_ENV], ["env FOO=1 gh issue view 5"]),
     True, (DISALLOWED, "(unquoted-wrapper)")),

    ("a gh inside an unquoted heredoc body fails closed",
     mkcase("", "", [APP_ENV], ["cat <<EOF", "gh issue view 5", "EOF"]),
     True, (DISALLOWED, "(unquoted-heredoc)")),

    ("an ANSI-C quoted gh fails closed",
     mkcase("", "", [APP_ENV], ["echo $'gh issue view 5'"]),
     True, (DISALLOWED, "(ansi-c)")),

    ("a case arm inside $( ) fails closed",
     mkcase("", "", [APP_ENV],
            ['x="$(case "$a" in b) gh issue view 5;; esac)"']),
     True, (DISALLOWED, "(case-arm)")),

    ("a double-quoted string holding $( ) and the word gh fails closed",
     mkcase("", "", [APP_ENV], ['echo "gh totallynew thing $(date)"']),
     True, (DISALLOWED, "(quoted-substitution)")),

    ("a gh in ${...} fails closed",
     mkcase("", "", [APP_ENV], ['x="${Y:-$(gh issue view 5)}"']),
     True, (DISALLOWED, "(param-expansion)")),

    ("an unterminated quote hides nothing: the rest fails closed",
     mkcase("", "", [APP_ENV], ["echo 'oops", "gh issue view 5"]),
     True, (DISALLOWED, "(unterminated-quote)")),

    # --- US1: provable mentions pass (even of calls the gate would reject) --
    ("a quoted mention of an unrecognised subcommand is not a call",
     mkcase("", "", [APP_ENV], ['echo "run gh totallynew thing first"']),
     False, ()),

    ("a single-quoted mention is not a call",
     mkcase("", "", [APP_ENV], ["echo 'gh totallynew thing'"]),
     False, ()),

    ("a comment mention is not a call, trailing or whole-line",
     mkcase("", "", [APP_ENV],
            ["# gh totallynew thing", "true # gh totallynew thing"]),
     False, ()),

    ("a quoted-delimiter heredoc body mention is not a call",
     mkcase("", "", [APP_ENV],
            ["cat <<'EOF'", "gh totallynew thing", "EOF"]),
     False, ()),

    ("words that merely contain gh are not calls: ghost, gh-pages, .github",
     mkcase("", "", [APP_ENV],
            ["git push origin gh-pages", "ghost run", "ls .github/gh"]),
     False, ()),

    ("an Actions expression is opaque text, not shell",
     mkcase("", "", [APP_ENV],
            ['echo "${{ github.event.name }} gh totallynew"']),
     False, ()),

    ("a line continuation joins the call's words: `gh \\\\\\n run cancel`",
     mkcase("", "", [APP_ENV], ["gh \\", "  run cancel 5"]),
     True, ("run cancel", "App token")),

    ("a large quoted heredoc is skipped in linear time and the gh after it "
     "is still checked",
     mkcase("", "", [APP_ENV], BIG_HEREDOC),
     False, ()),

    # --- US1: every other failure branch -----------------------------------
    ("an unresolvable token fails",
     mkcase("", "", [APP_ENV], ['GH_TOKEN="$UNSET" gh issue view 5']),
     True, ("could not resolve",)),

    ("an unknown subcommand fails",
     mkcase("", "", [APP_ENV], ["gh totallynew thing"]),
     True, ("totallynew", "SUBCOMMAND_PERMS")),

    ("an unknown `gh api` path category fails",
     mkcase("", "", [APP_ENV], ['gh api "repos/$REPO/zzzunknown/1"']),
     True, ("zzzunknown", "API_CATEGORY_PERM")),

    ("a composite that calls gh but is used by no workflow fails",
     UNUSED_COMPOSITE, True, ("no workflow under",)),

    ("the authoring-rule section the failures point at must exist",
     {**mkcase("", "", [APP_ENV], ['gh issue view 5']),
      "CONTRIBUTING.md": "# Contributing\n"},
     True, (f"no `### {AUTHORING_RULE}` section",)),

    # --- the #889 gaps, each by name ---------------------------------------
    ("gap: glued method flags `-XPOST` are a write",
     mkcase(ISSUES_READ, "", [DEFAULT_ENV],
            ['gh api -XPOST "repos/$REPO/issues/1/comments" -f body=x']),
     True, ("issues", "write")),

    ("gap: `--method=POST` is a write",
     mkcase(ISSUES_READ, "", [DEFAULT_ENV],
            ['gh api --method=POST "repos/$REPO/issues/1/comments" -f body=x']),
     True, ("issues", "write")),

    ("gap: an unquoted Actions expression in a `gh api` value is not one "
     "word, so it fails closed instead of hiding a method",
     mkcase(ISSUES_READ, "", [DEFAULT_ENV],
            ['gh api -X POST "repos/${GITHUB_REPOSITORY}/issues/1/comments" '
             '-f body=${{ inputs.a || inputs.b }}']),
     True, (DISALLOWED, "(dynamic-flag)")),

    ("gap: ... while the same expression quoted is one word and the write "
     "is checked",
     mkcase(ISSUES_READ, "", [DEFAULT_ENV],
            ['gh api -X POST "repos/${GITHUB_REPOSITORY}/issues/1/comments" '
             '-f body="${{ inputs.a || inputs.b }}"']),
     True, ("issues", "write")),

    ("gap: separators in escaped backticks end nothing of the call",
     mkcase(ISSUES_READ, "", [DEFAULT_ENV],
            ['x=`gh api "repos/$REPO/issues/1/comments" -f body=\\`a;b\\` -X POST`']),
     True, (DISALLOWED, "(backtick)")),
]

# ----------------------------------------------------------- locator cases
#
# script, then the (kind, detail) pairs locate() must return in order, where
# detail is the position of an allowed call, `disallowed:<reason>` of a
# rejected one, or the mention clause.

C_ST, C_SUB = ("call", "statement"), ("call", "subst_first")


def dis(reason):
    return ("call", "disallowed:" + reason)


def men(clause):
    return ("mention", clause)


LOCATOR_CASES = [
    ("statement", "gh issue view 5", [C_ST]),
    ("after a separator", "true; gh a b && gh c d | gh e f", [C_ST] * 3),
    ("after then/do/!", "if ! gh a b; then gh c d; fi", [C_ST] * 2),
    ("first command of a substitution", 'x="$(gh issue view 5)"', [C_SUB]),
    ("first of a pipeline in a substitution", "x=$(gh api x | jq .)", [C_SUB]),
    ("process substitution", "mapfile -t a < <(gh issue list)", [C_SUB]),
    ("GH_TOKEN prefix", 'GH_TOKEN="$T" gh run list', [C_ST]),
    ("timeout prefix", 'x="$(timeout "$T" gh issue view 5)"', [C_SUB]),
    ("other assignment prefix", "GH_REPO=x gh issue view 5",
     [dis("unsupported-prefix")]),
    ("backticks", "x=`gh issue view 5`", [dis("backtick")]),
    ("double-quoted backticks", 'x="`gh issue view 5`"', [dis("backtick")]),
    ("nested substitution", 'x="$(echo "$(gh issue view 5)")"',
     [dis("nested-substitution")]),
    ("not first in substitution", "x=$(cd d && gh issue view 5)",
     [dis("substitution-not-first")]),
    ("variable subcommand", 'gh "$V" list', [dis("variable-subcommand")]),
    ("variable verb two", 'gh issue "$A"', [dis("variable-subcommand")]),
    ("variable api method", 'gh api -X "$M" x', [dis("variable-method")]),
    ("glued api method is literal", "gh api -XPOST x", [C_ST]),
    ("wrapper", "env gh issue view 5", [dis("unquoted-wrapper")]),
    ("command -v is not a wrapper call", "command -v gh", []),
    ("which / echo are not calls", "which gh; echo gh", []),
    ("single-quoted mention", "echo 'gh issue view'", [men("quoted")]),
    ("double-quoted mention", 'echo "gh issue view"', [men("quoted")]),
    ("quote with $( ) is not a mention", 'echo "gh $(date)"',
     [dis("quoted-substitution")]),
    ("quote with backtick is not a mention", 'echo "gh `date`"',
     [dis("quoted-substitution")]),
    ("quote with ${} only is a mention", 'echo "gh ${X}"', [men("quoted")]),
    ("comment", "# gh issue view", [men("comment")]),
    ("trailing comment", "true # gh issue view", [men("comment")]),
    ("# inside a word is no comment", "echo a#gh", []),
    ("quoted heredoc", "cat <<'EOF'\ngh x\nEOF", [men("quoted-heredoc")]),
    ("double-quoted delimiter", 'cat <<"EOF"\ngh x\nEOF', [men("quoted-heredoc")]),
    ("backslash delimiter", "cat <<\\EOF\ngh x\nEOF", [men("quoted-heredoc")]),
    ("unquoted heredoc", "cat <<EOF\ngh x\nEOF", [dis("unquoted-heredoc")]),
    ("tab-stripped heredoc", "cat <<-'EOF'\n\tgh x\n\tEOF\ngh a b",
     [men("quoted-heredoc"), C_ST]),
    ("heredoc then call", "cat <<'EOF' | jq .\ngh x\nEOF\ngh a b",
     [men("quoted-heredoc"), C_ST]),
    ("two heredocs on a line", "cat <<'A' <<'B'\ngh 1\nA\ngh 2\nB\ngh a b",
     [men("quoted-heredoc"), men("quoted-heredoc"), C_ST]),
    ("heredoc inside a substitution", 'x="$(cat <<\'E\'\ngh x\nE\n)"\ngh a b',
     [men("quoted-heredoc"), C_ST]),
    ("unterminated heredoc", "cat <<'EOF'\ngh x", [dis("unterminated-heredoc")]),
    ("here-string", 'cat <<< "gh x"', [men("quoted")]),
    ("shift is no heredoc", "echo $(( 1 << 2 )) && gh a b", [C_ST]),
    ("arithmetic command shift", "(( A = 1 << 2 )); gh a b", [C_ST]),
    ("ANSI-C", "echo $'gh x'", [dis("ansi-c")]),
    ("case arm in substitution", 'x="$(case $a in b) gh x y;; esac)"',
     [dis("case-arm")]),
    ("case arm at top level", "case $a in b) gh x y;; esac", [C_ST]),
    ("param expansion", 'x="${Y:-$(gh a b)}"', [dis("param-expansion")]),
    ("unterminated quote", "echo 'gh x", [dis("unterminated-quote")]),
    ("unterminated substitution", "x=$(gh a b",
     [dis("unterminated-substitution")]),
    ("ghost and gh-pages", "ghost run; git push origin gh-pages", []),
    ("quoted gh-pages", 'echo "gh-pages .github/gh"', []),
    ("Actions expression text", "echo ${{ x == '`' }} && gh a b", [C_ST]),
    ("Actions expression with }} string", "echo ${{ contains(x, '}}') }} gh a b",
     []),
    ("line continuation", "gh issue \\\n  comment 5", [C_ST]),
    ("redirect target is no command", "echo x >gh", []),
    ("unclosed Actions openers are linear", "echo \"" + "`${{" * 20000 + "\"", None),
    ("a large heredoc is linear", "cat <<'EOF'\n" + "a b c\n" * 200000 + "EOF\ngh a b",
     [C_ST]),
]


def fmt(tok):
    if tok.kind == "mention":
        return ("mention", tok.mention_clause)
    if tok.position == "disallowed":
        return ("call", "disallowed:" + tok.reason)
    return ("call", tok.position)


def run_locator_cases():
    bad = []
    for name, script, expected in LOCATOR_CASES:
        t0 = time.time()
        got = [fmt(t) for t in loc.locate(script)]
        took = time.time() - t0
        if took > 5:
            bad.append((name, [f"took {took:.1f}s: not linear"]))
        elif expected is not None and got != expected:
            bad.append((name, [f"expected {expected}", f"got      {got}"]))
    toks = loc.locate('GH_TOKEN="$T" timeout 30 gh api -iX POST "repos/$R/issues" '
                      '-f a="$b" --jq .x')
    argv = toks[0].argv if toks else []
    if not (toks and toks[0].prefix_token == '"$T"' and toks[0].timeout
            and [str(w) for w in argv[:3]] == ["api", "-iX", "POST"]
            and [type(w) for w in argv[3:]] == [loc.Dynamic, str, loc.Dynamic, str, str]
            and argv[4] == "-f"):
        bad.append(("token fields", [f"got {toks}"]))
    for args, want in (
            (["-XPOST", "p"], ("p", ["POST"])),
            (["-X", "PATCH", "p"], ("p", ["PATCH"])),
            (["-iX", "PUT", "p"], ("p", ["PUT"])),
            (["--method", "DELETE", "p"], ("p", ["DELETE"])),
            (["--method=POST", "p"], ("p", ["POST"])),
            (["p", "-X", "POST", "-X", "GET"], ("p", ["POST", "GET"])),
            (["-H", "Accept: x", "-i", "p"], ("p", [])),
            (["-f", "a=-X POST", "p"], ("p", [])),
            (["--", "-p"], ("-p", [])),
            ([], (None, []))):
        path, methods = loc.api_parts(args)
        if (None if path is None else str(path), [str(m) for m in methods]) != want:
            bad.append((f"api_parts {args}", [f"got {(path, methods)}, want {want}"]))
    return bad


# -------------------------------------------------------------- gate runner

def write_tree(case_dir, files):
    # The gate checks that the heading its failures point at exists.
    files = {"CONTRIBUTING.md": f"### {AUTHORING_RULE}\n", **files}
    for relpath, body in files.items():
        body = re.sub(r"@@REPEAT:(.*?):(\d+)@@",
                      lambda m: m.group(1) * int(m.group(2)), body)
        full = os.path.join(case_dir, *relpath.split("/"))
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as fh:
            fh.write(body)


def run_gate(gate, files, root):
    """-> (fired, output, timed_out) for the gate run over a synthetic tree."""
    case_dir = tempfile.mkdtemp(prefix="case_", dir=root)
    write_tree(case_dir, files)
    try:
        proc = subprocess.run([sys.executable, gate], cwd=case_dir,
                              capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=CASE_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return False, "", True
    return proc.returncode != 0, (proc.stdout or "") + (proc.stderr or ""), False


def judge(name, fired, out, timed_out, expect_fail, must_mention, changed=False):
    """-> problems for one scenario's verdict."""
    if timed_out:
        return [f"the gate did not finish within {CASE_TIMEOUT_S}s"]
    problems = []
    if changed and not expect_fail and fired and DISALLOWED in out:
        return problems              # the one change FR-014 allows
    if fired != expect_fail:
        problems.append(f"expected the gate to {'FAIL' if expect_fail else 'PASS'}, "
                        f"it {'FAILED' if fired else 'PASSED'}")
    for token in must_mention:
        if token not in out:
            problems.append(f"error text never mentions {token!r}")
    return problems


def run_scenarios(gate, scenarios, root):
    """scenarios: (name, files, expect_fail, must_mention, changed) tuples
    -> [(name, problems, output)] for those behaving wrongly."""
    def one(sc):
        name, files, expect_fail, must, changed = sc
        fired, out, timed = run_gate(gate, files, root)
        return name, judge(name, fired, out, timed, expect_fail, must, changed), out

    workers = min(8, os.cpu_count() or 2)
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        return [r for r in pool.map(one, scenarios) if r[1]]


def load_corpus():
    with open(CORPUS, encoding="utf-8") as fh:
        data = json.load(fh)
    scenarios, errors = [], []
    for c in data:
        expect_fail = c["expect"] == "fail"
        changed = bool(c.get("changed_from_969"))
        if changed and expect_fail:
            errors.append(f"{c['id']}: changed_from_969 on a scenario that "
                          f"expects a failure (only pass -> disallowed may change)")
        scenarios.append((f"{c['id']} {c['name']}", c["files"], expect_fail,
                          tuple(c.get("must_mention") or ()), changed))
    return scenarios, errors


def report(title, results, limit=12):
    for name, problems, out in results[:limit]:
        print(f"FAIL  {title}: {name[:150]}")
        for p in problems:
            print(f"        - {p[:300]}")
        for line in (out or "").strip().splitlines()[:3]:
            print(f"        | {line[:300]}")
    if len(results) > limit:
        print(f"FAIL  {title}: ... and {len(results) - limit} more")
    return len(results)


# ------------------------------------------------------------ differential

def exec_method(argv):
    """The HTTP method a recorded `gh api` argv names (gh keeps the last)."""
    meth, k = "GET", 1
    # Written out here rather than imported: the oracle must not share the
    # locator's reading of gh's flags.
    valued = {"-H", "--header", "-f", "--raw-field", "-F", "--field", "-q", "--jq",
              "-t", "--template", "-p", "--preview", "--hostname", "--input", "--cache"}
    while k < len(argv):
        a = argv[k]
        if a in ("-X", "--method") or re.fullmatch(r"-i+X", a):
            meth = argv[k + 1] if k + 1 < len(argv) else meth
            k += 2
            continue
        if a in valued or re.fullmatch(r"-i+[HfFqtp]", a):
            k += 2
            continue
        glued = re.fullmatch(r"-i*X(.+)", a)
        if a.startswith("--method="):
            meth = a.split("=", 1)[1]
        elif glued:
            meth = glued.group(1)
        k += 1
    return meth


def accounted(tokens, argv):
    """True when the locator found (or rejected as disallowed) this
    invocation bash actually ran."""
    calls = [t for t in tokens if t.kind == "call"]
    if any(t.position == "disallowed" for t in calls):
        return True
    for t in calls:
        words = [str(w) for w in t.argv]
        if any(isinstance(w, loc.Dynamic) for w in t.argv[:2]):
            return True
        if argv[:1] == ["api"]:
            if words[:1] == ["api"]:
                methods = [str(m) for m in loc.api_parts(t.argv[1:])[1]]
                if (methods[-1] if methods else "GET") == exec_method(argv):
                    return True
        elif words[:2] == argv[:2]:
            return True
    return False


def bash_run(bash, bin_dir, script):
    """-> recorded argv list per gh bash ran, or None when the script is not
    a valid, terminating one."""
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "s.sh")
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(script)
        if subprocess.run([bash, "-n", path], capture_output=True).returncode:
            return None
        log = os.path.join(td, "log")
        open(log, "w").close()
        try:
            subprocess.run([bash, path], cwd=td, stdin=subprocess.DEVNULL,
                           capture_output=True, timeout=3,
                           env={"PATH": bin_dir + os.pathsep + "/usr/bin" + os.pathsep
                                + "/bin", "GHLOG": log})
        except subprocess.TimeoutExpired:
            return None
        with open(log, encoding="utf-8", errors="replace") as fh:
            return harness.gh_argv_calls(fh.read())


def differential():
    """-> (failures, scripts run under bash, invocations bash ran)."""
    import gen
    bash = harness.resolve_bash()
    exprs = gen.EXPRS
    scripts = []
    for seed in range(FUZZ_SEED, FUZZ_SEED + FUZZ_COUNT):
        r = random.Random(seed)
        kind = r.choice(["verb", "api"])
        scripts.append((f"seed {seed} ({kind})", gen.G(r).script(kind)))
    for fname in sorted(os.listdir(FUZZ_DIR)):
        if fname.endswith(".jsonl"):
            with open(os.path.join(FUZZ_DIR, fname), encoding="utf-8") as fh:
                for n, line in enumerate(fh, 1):
                    rec = json.loads(line)
                    scripts.append((f"{fname}:{n} ({rec['kind']})", rec["min"]))
    failures, ran, invoked = [], 0, 0
    with tempfile.TemporaryDirectory() as td:
        bin_dir = harness.gh_argv_recording_stub(td)
        for label, script in scripts:
            under_bash = script
            for e in exprs:
                under_bash = under_bash.replace(e, "EXPRV")
            if "${{" in under_bash:
                continue
            calls = bash_run(bash, bin_dir, under_bash)
            if calls is None:
                continue
            ran += 1
            tokens = loc.locate(script)
            for argv in calls:
                invoked += 1
                if not accounted(tokens, argv):
                    failures.append((label, [
                        f"bash ran `gh {' '.join(argv)[:80]}` but the locator "
                        f"neither found it nor rejected the script",
                        f"script: {script!r}"], ""))
                    break
    return failures, ran, invoked


# ---------------------------------------------------------------- mutation

def mutation(scenarios, root):
    """A locator that calls a real call a mention must turn the corpus red
    (FR-016). -> (survived: bool, replayed count)."""
    with open(LOCATOR, encoding="utf-8") as fh:
        src = fh.read()
    needle = 'self._note(head.off, "call", reason=reason,'
    if needle not in src:
        return True, 0               # the mutation target moved: fail loudly
    mdir = tempfile.mkdtemp(prefix="mutant_", dir=root)
    shutil.copy(GATE, mdir)
    with open(os.path.join(mdir, "wc_gh_callsites.py"), "w", encoding="utf-8") as fh:
        fh.write(src.replace(needle, 'self._note(head.off, "mention", reason=reason,'))
    sample = [s for s in scenarios if s[2] and s[3]][:MUTATION_SAMPLE]
    red = run_scenarios(os.path.join(mdir, os.path.basename(GATE)), sample, root)
    return not red, len(sample)


def main():
    failed = 0
    root = tempfile.mkdtemp(prefix="verify_gate12_")
    try:
        bad = run_locator_cases()
        failed += report("locator", [(n, p, "") for n, p in bad])
        print(f"locator: {len(LOCATOR_CASES)} snippet(s), "
              f"{len(bad)} behaving wrongly")

        fixtures = [(n, f, e, m, False) for n, f, e, m in FIXTURES]
        res = run_scenarios(GATE, fixtures, root)
        failed += report("fixture", res)
        print(f"fixtures: {len(fixtures)} scenario(s), {len(res)} behaving wrongly")

        corpus, errors = load_corpus()
        for e in errors:
            print(f"FAIL  corpus: {e}")
        failed += len(errors)
        res = run_scenarios(GATE, corpus, root)
        failed += report("corpus", res)
        print(f"corpus: {len(corpus)} scenario(s) from PR #969, "
              f"{len(res)} behaving wrongly")

        diffs, ran, invoked = differential()
        failed += report("differential", diffs)
        print(f"differential: {ran} generated script(s) run under real bash, "
              f"{invoked} gh invocation(s) recorded, {len(diffs)} unaccounted")
        if not invoked:
            print("FAIL  differential: bash ran no gh invocation at all, so the "
                  "oracle checked nothing")
            failed += 1

        survived, n = mutation(corpus, root)
        print(f"mutation: a locator hiding real calls as mentions was "
              f"{'NOT caught' if survived else 'caught'} ({n} scenario(s) replayed)")
        if survived:
            print("FAIL  mutation: the corpus stays green when the locator "
                  "calls a real call a mention, so it cannot fail its subject")
            failed += 1
    finally:
        shutil.rmtree(root, ignore_errors=True)

    print()
    if failed:
        print(f"::error file=.github/workflows/lint-workflows.yml::Gate 12 "
              f"self-test: {failed} check(s) behaved wrongly. Gate 12's detection "
              f"logic does not do what its name claims, so a green Gate 12 on the "
              f"real fleet means nothing.")
        return 1
    print("Gate 12 self-test: every check behaved as expected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
