import glob, os, re, sys, yaml

# subcommand (verb1, verb2) -> frozenset of (permission-category, level)
# pairs it needs. Extended only with evidence (research.md R6 / Gate 6's
# SUPPORTED_EVENTS rule): every entry is a real invocation this
# repository's own workflows make. An empty frozenset means no repository
# permission is needed at all (repo metadata is always readable,
# regardless of token).
# `ctx` is the shared wing-commander-context composite's token: the
# App installation token for the repository the stage runs in,
# minted inside the composite, so the workflow only ever sees the
# composite's output and nothing structural in the workflow file
# says it is an App token. It and APP_TOKEN_ENV_EXPR below (the same
# token, exported to $GITHUB_ENV) are the App-token expressions
# that have to be named here.
#
# Every OTHER App token this repository mints is a workflow step
# that `uses: actions/create-github-app-token` directly (e2e-stage's
# `scratch-token` for the pre-created scratch repository) or through
# the `_shared/scoped-app-token` composite, which wraps that action
# and re-exports its token (auto-release.yml's `token` for the
# pre-onboarded end-to-end test repository, auto-update-spec-kit's
# scratch-repository mints). Each is a scope the context token
# cannot cover, since one installation token cannot span two
# owners. Those are recognised STRUCTURALLY, per job, by
# app_token_exprs_for() below:
# a step id is only an App token in the job that mints it, so a
# generic id like `token` in some other job never inherits the
# classification by name. Same App, same grant, so the same
# docs/setup.md check applies. Should this repository ever mint a
# token for a second App, that App needs its own documented grant
# and its own classification — do not fold it into this one.
APP_TOKEN_EXPRS = {"steps.ctx.outputs.token"}
APP_TOKEN_MINTER = "actions/create-github-app-token"
# A step using this composite (by any COMPOSITE_USES_RE path) mints
# through APP_TOKEN_MINTER and outputs that token as `token`.
APP_TOKEN_MINTER_COMPOSITE = "_shared/scoped-app-token"
DEFAULT_TOKEN_EXPRS = {"github.token", "secrets.GITHUB_TOKEN"}


# wing-commander-context also exports its App token to $GITHUB_ENV
# as WC_BOT_TOKEN, so in a job that runs it `env.WC_BOT_TOKEN` is
# the same App token. Left as "other", every call made under it
# went unchecked: board-loop triage's run-evidence fetch called
# the Actions API with it, which 403s under the documented grant.
APP_TOKEN_ENV_EXPR = "env.WC_BOT_TOKEN"
APP_TOKEN_ENV_EXPORTER = "/actions/wing-commander-context"


def app_token_exprs_for(job):
    """APP_TOKEN_EXPRS plus `steps.<id>.outputs.token` for every step
    in THIS job that mints an installation token with
    actions/create-github-app-token, directly or through the
    scoped-app-token composite, plus APP_TOKEN_ENV_EXPR when
    THIS job runs wing-commander-context."""
    out = set(APP_TOKEN_EXPRS)
    for st in job.get("steps") or []:
        st = st or {}
        sid = st.get("id")
        uses = str(st.get("uses") or "")
        cm = COMPOSITE_USES_RE.match(uses.replace("\\", "/"))
        if sid and (uses.split("@")[0] == APP_TOKEN_MINTER
                    or (cm and cm.group(1) == APP_TOKEN_MINTER_COMPOSITE)):
            out.add(f"steps.{sid}.outputs.token")
        if uses.split("@")[0].endswith(APP_TOKEN_ENV_EXPORTER):
            out.add(APP_TOKEN_ENV_EXPR)
    return out

SUBCOMMAND_PERMS = {
    ("run", "cancel"):     frozenset({("actions", "write")}),
    ("run", "download"):   frozenset({("actions", "read")}),
    ("run", "list"):       frozenset({("actions", "read")}),
    ("run", "view"):       frozenset({("actions", "read")}),
    # auto-release.yml polls the release.yml run it dispatched.
    # `gh run watch` is `gh run view` in a loop: GET
    # /repos/{o}/{r}/actions/runs/{id} plus its jobs until the run
    # completes - reads only, so the same actions:read as view.
    ("run", "watch"):      frozenset({("actions", "read")}),
    ("workflow", "run"):   frozenset({("actions", "write")}),
    ("workflow", "view"):  frozenset({("actions", "read")}),
    ("workflow", "list"):  frozenset({("actions", "read")}),
    ("issue", "view"):     frozenset({("issues", "read")}),
    ("issue", "comment"):  frozenset({("issues", "write")}),
    ("issue", "create"):   frozenset({("issues", "write")}),
    ("issue", "edit"):     frozenset({("issues", "write")}),
    ("issue", "close"):    frozenset({("issues", "write")}),
    ("issue", "reopen"):   frozenset({("issues", "write")}),
    ("issue", "list"):     frozenset({("issues", "read")}),
    ("label", "create"):   frozenset({("issues", "write")}),
    ("label", "list"):     frozenset({("issues", "read")}),
    ("pr", "view"):        frozenset({("pull-requests", "read")}),
    ("pr", "comment"):     frozenset({("pull-requests", "write")}),
    ("pr", "create"):      frozenset({("pull-requests", "write"),
                                       ("contents", "read")}),
    ("pr", "edit"):        frozenset({("pull-requests", "write")}),
    # auto-release.yml closes the previous attempt's leftover PRs in
    # the end-to-end test repository. Closing is the closePullRequest
    # GraphQL mutation (with --comment, an addComment first): a
    # pull-request write, the same level as `gh issue close` above.
    ("pr", "close"):       frozenset({("pull-requests", "write")}),
    ("pr", "list"):        frozenset({("pull-requests", "read")}),
    # board-loop.yml's reviewer step reads the PR's own diff --
    # GET /repos/{o}/{r}/pulls/{n} with the diff media type, a
    # pull-requests read like `pr view`.
    ("pr", "diff"):        frozenset({("pull-requests", "read")}),
    ("pr", "ready"):       frozenset({("pull-requests", "write"),
                                       ("contents", "write")}),
    # lifecycle-review-gate.yml's `merge` job squash-merges a
    # lifecycle PR once every merge precondition holds
    # (specs/062-lifecycle-review-gate, US4 — off unless
    # WING_COMMANDER_LIFECYCLE_AUTO_MERGE is set). PUT
    # /repos/{o}/{r}/pulls/{n}/merge: the REST reference for
    # "Merge a pull request" lists Pull requests (write) as the
    # fine-grained requirement, and the squash commit it writes
    # onto the base branch is a Contents write — the same pairing
    # `gh pr ready` above already carries, and both are granted in
    # docs/setup.md.
    ("pr", "merge"):       frozenset({("pull-requests", "write"),
                                       ("contents", "write")}),
    ("search", "issues"):  frozenset({("issues", "read")}),
    ("search", "prs"):     frozenset({("pull-requests", "read")}),
    ("release", "create"): frozenset({("contents", "write")}),
    ("repo", "view"):      frozenset(),
    # auto-release-switch.yml sets, deletes and reads back
    # WING_COMMANDER_AUTO_RELEASE_PAUSED. The REST reference for
    # Actions variables lists the "Variables" repository permission
    # (read for get, write for set/delete) as the fine-grained
    # requirement. A `permissions:` block cannot grant it to
    # GITHUB_TOKEN and docs/setup.md does not grant it to the App,
    # so only a dedicated token can satisfy these.
    ("variable", "get"):    frozenset({("variables", "read")}),
    ("variable", "set"):    frozenset({("variables", "write")}),
    ("variable", "delete"): frozenset({("variables", "write")}),
}

# Permissions no `permissions:` block can grant GITHUB_TOKEN (the
# variables entries above, and the Secrets and Administration
# surfaces API_CATEGORY_PERM maps actions/ sub-paths to): a call
# needing one 403s under github.token in every job, so check_call
# fails it even where the job declares no permissions: block to
# compare against.
DEFAULT_TOKEN_NEVER_GRANTED = frozenset({"variables", "secrets", "administration"})

# `gh api PATH` — PATH's first segment under repos/{owner}/{repo}/ decides
# the permission, the same way SUBCOMMAND_PERMS does for named subcommands.
# "branches": cleanup.yml's branch probe (#282) — GET
# /repos/{owner}/{repo}/branches/{branch}; the REST reference for "Get a
# branch" lists "Contents" repository permissions (read) as the
# fine-grained token requirement, and docs/setup.md grants the App
# Contents: Read and write.
API_CATEGORY_PERM = {
    "actions": "actions", "check-runs": "checks", "check-suites": "checks",
    "issues": "issues", "pulls": "pull-requests", "contents": "contents",
    "releases": "contents", "labels": "issues", "milestones": "issues",
    "branches": "contents",
    # auto-release.yml resolves main's tip (GET .../commits/main)
    # before dispatching release.yml. The commits endpoints are the
    # "Contents" permission's surface in GitHub's fine-grained
    # permission reference, same as .../contents/... itself.
    "commits": "contents",
    # specs/046-watchdog-supervision-collectors' collect-final-pr-claims
    # reads GET .../compare/{basehead} for ground-truth commit/file
    # counts — the REST reference lists this under the same
    # "Contents" repository permission as .../commits/... and
    # .../contents/... above.
    "compare": "contents",
    # auto-release.yml's e2e-pin creates, reads back and deletes a
    # run-scoped annotated tag (POST .../git/tags, .../git/refs,
    # GET .../git/ref/tags/..., DELETE .../git/refs/tags/...): the
    # Git database endpoints are under "Contents" in the
    # fine-grained permission reference.
    "git": "contents",
    # .../actions/<sub>/... sub-paths that path_category splits out
    # of "actions" (ACTIONS_SUBPATHS below) because GitHub's
    # fine-grained permission reference files them under their own
    # repository permission, not "Actions":
    # - variables, organization-variables: "Variables", as the
    #   `gh variable` entries in SUBCOMMAND_PERMS say;
    # - secrets, organization-secrets: "Secrets";
    # - permissions, runners: "Administration" (auto-release.yml's
    #   maintainer-token probe reads .../actions/permissions).
    "actions/variables": "variables",
    "actions/organization-variables": "variables",
    "actions/secrets": "secrets",
    "actions/organization-secrets": "secrets",
    "actions/permissions": "administration",
    "actions/runners": "administration",
    # specs/062-lifecycle-review-gate T024: POST .../statuses/{sha}
    # (Create a commit status) -- the REST reference lists
    # "Commit statuses" as its own fine-grained repository
    # permission, distinct from "Checks" (which covers
    # check-runs/check-suites above).
    "statuses": "statuses",
}

# The sub-paths path_category splits out of "actions", read from the
# table itself so a new sub-path entry needs no second edit.
ACTIONS_SUBPATHS = frozenset(k.split("/", 1)[1] for k in API_CATEGORY_PERM
                             if k.startswith("actions/"))

# `gh api`'s own flags may precede the path in any order (`gh api -i
# -X POST PATH`); the parser before the code review of #939 allowed
# only -X/--method there and read `-i` as the PATH, hiding six
# auto-release.yml calls. A flag gh documents as taking a value
# consumes the next word, and so does a cluster of gh's one
# boolean short flag ending in one (`-iX POST`, as in `curl -iX
# POST`); any other word starting `-` (`-i`, `--method=POST`,
# `-H'Accept: x'`, `--`) is a switch. A valued flag
# standing alone is never a switch: the regex would otherwise
# backtrack it into one and take its value (`-X POST`'s `POST`) as
# the PATH, a non-repos/ path skipped as out of scope where a call
# with no PATH must fail loudly as unrecognised. A word is read the
# way the shell splits it, so a partly quoted value (`-f body="a
# b"`) is one word, not `body="a` plus a PATH `b"`, and so is a value
# holding a command substitution or an Actions expression with
# blanks in it (`-f sha=$(git rev-parse HEAD)`), which would
# otherwise free `rev-parse` as the PATH, including a substitution
# inside double quotes whose own quoted words hold blanks (`-f
# body="$(printf "%s %s" "$A" "$B")"`), and a value with a
# backslash-escaped quote (`-f body='it'\''s'`); an unclosed one is no
# word at all, so backtracking never splits it either. A backslash
# outside quotes is read only as an escape, never as a plain
# character too: a word with both readings has 2^n splittings, so a
# call with no PATH and a few dozen escapes (`--jq .a\.b\.c...`)
# would hang the gate instead of failing it. Words are
# separated the way the shell separates them on one command: blanks
# or a `\`-newline continuation, never a bare newline -- a call
# whose PATH sits on its continuation line is still resolved (not
# read as a PATH `\` and skipped as out of scope), and a call with
# no PATH never takes the next command's first word as one.
#
# A command substitution nests up to SUB_DEPTH parenthesis levels
# (`$(a "$(b "$(c)")")`, a subshell or `$((...))` counting as one),
# and a quoted `)` inside one (`$(printf ')')`, `$(echo ")")`) does
# not close it; one nested deeper is no word, so its call fails
# loudly as having no PATH (code review of #944). An unquoted
# parameter expansion (`${X:-a b}`, one inner `{...}` level) and a
# backtick substitution (`` `git rev-parse HEAD` ``) are one word
# part each, not split at their blanks. Every alternative inside a
# word, and inside each of these parts, starts on a character no
# other alternative there can start on, so a word has exactly one
# parse and a failed match backs out in linear time: this parser
# once hung the gate on catastrophic backtracking, and the
# self-test times adversarial inputs to keep it from doing so
# again.
GH_API_SEP = r'(?:[ \t]|\\\n)+'
SUB_DEPTH = 3


def _sub_body(depth):
    """The inside of a `(...)` nesting at most `depth` levels."""
    inner = _sub_body(depth - 1) if depth > 1 else None
    dq = (r'"(?:[^"\\$]|\\.|\$(?!\()'
          + (r'|\$\(' + inner + r'\)' if inner else '') + r')*"')
    return (r"(?:[^()'" + '"' + r"\\]|\\.|'[^']*'|" + dq
            + (r'|\(' + inner + r'\)' if inner else '') + r')*')


def _brace_body(depth):
    """The inside of a `{...}` nesting at most `depth` levels."""
    inner = _brace_body(depth - 1) if depth > 1 else None
    return (r'(?:[^{}]' + (r'|\{' + inner + r'\}' if inner else '')
            + r')*')


_CMD_SUB = r'\$\(' + _sub_body(SUB_DEPTH) + r'\)'
# A process substitution (`-F body=@<(jq -n ...)`) is one word part
# like `$(...)`: read as plain characters, it split at its blanks
# and a `--method GET` inside it read as the call's last method
# (code review of #944).
_PROC_SUB = r'[<>]\(' + _sub_body(SUB_DEPTH) + r'\)'
# A `${...}` value nests SUB_DEPTH levels of braces too
# (`${A:-${B:-${C}}}`): capped at two, the third level's `-X GET`
# started a word of its own after the PATH and read as the call's
# last method (code review of #944).
_PARAM_EXP = r'\$\{(?!\{)' + _brace_body(SUB_DEPTH) + r'\}'
_BACKTICK = r'`(?:[^`\\]|\\.)*`'
_EXPR = r'\$\{\{(?:[^}]|\}(?!\}))*\}\}'


def _dq_brace_body(depth):
    """The inside of a `${...}` within double quotes, nesting at
    most `depth` levels of braces. A quoted string inside it
    (`"${X:-"a b"}"`) is part of the expansion, as bash reads it:
    closing the outer quote at its first inner `"` left the text
    between the inner quotes unquoted, so `"${X:-" -X GET "}"`
    read as two words and its `-X GET` as the call's last method
    (code review of #944)."""
    inner = _dq_brace_body(depth - 1) if depth > 1 else None
    return (r'(?:[^{}"\\]|\\.|"(?:[^"\\]|\\.)*"'
            + (r'|\{' + inner + r'\}' if inner else '') + r')*')


_DQ_PARAM = r'\$\{(?!\{)' + _dq_brace_body(SUB_DEPTH) + r'\}'
SHELL_WORD = (r'(?:"(?:[^"\\$]|\\.|' + _CMD_SUB + r'|' + _EXPR
              + r'|' + _DQ_PARAM + r'|\$(?![({]))*"|\'[^\']*\''
              r'|' + _CMD_SUB + r'|' + _PROC_SUB + r'|' + _EXPR
              + r'|' + _PARAM_EXP + r'|' + _BACKTICK +
              r'|\\.|(?!\$\(|\$\{|[<>]\()[^\s"\'\\`])+')
GH_API_VALUE_FLAGS = ("-X", "--method", "-H", "--header", "-f", "--raw-field",
                      "-F", "--field", "-q", "--jq", "-t", "--template",
                      "-p", "--preview", "--hostname", "--input", "--cache")
_GH_API_VALUE_FLAG = ("(?:" + "|".join(re.escape(f) for f in GH_API_VALUE_FLAGS)
                      + r"|-i+[XHfFqtp])")
GH_API_FLAGS = (
    r'(?:' + _GH_API_VALUE_FLAG + GH_API_SEP + SHELL_WORD + GH_API_SEP +
    r'|(?!' + _GH_API_VALUE_FLAG + r'(?:\s|\\\n|$))-' + SHELL_WORD + GH_API_SEP + r')*')

GH_INVOKE_RE = re.compile(
    r'(?:GH_TOKEN=(?P<tokexpr>"(?:[^"\\]|\\.)*"|\$\{\{[^}]*\}\}|\$\w+)\s+)?'
    r'\bgh\s+(?:'
    r'api' + GH_API_SEP + GH_API_FLAGS + r'(?P<apipath>"(?:[^"\\]|\\.)*"|(?!\\\n)[^\s-]\S*)'
    r'|(?P<verb1>[a-zA-Z][\w-]*)(?:\s+(?P<verb2>[a-zA-Z][\w-]*))?'
    r')'
)
ASSIGN_RE = re.compile(r'(?<![\w$])(\w+)=("(?:[^"\\]|\\.)*"|\$\([^)]*\)|\S+)')
TOOL_GH_RE = re.compile(r'Bash\(gh\s+([a-zA-Z][\w-]*)(?:\s+([a-zA-Z][\w-]*))?')
# A workflow step calling one of this repository's own composites,
# by any path a caller resolves them at: `./.github/actions/X` (a
# workflow running in this repository's own checkout),
# `./.wing-commander-pipeline/.github/actions/X` (a published
# stage, through its self-checkout), or
# `./.wc-pristine-repo/.github/actions/X` (board-loop.yml's own
# trusted-copy checkout -- see that file's header;
# specs/086-trusted-composite-resolution). Group 1 is X, the
# directory under .github/actions/ — `_shared/name` for a nested
# one.
COMPOSITE_USES_RE = re.compile(
    r'^\./(?:\.wing-commander-pipeline/|\.wc-pristine-repo/)?\.github/actions/([^@\s]+?)/?(?:@\S+)?$')
# `gh api` level: an explicit -X or --method decides (POST/PATCH/PUT/
# DELETE write, anything else reads). Gate 28 separately requires
# every `gh api` call that passes a field to name its method, so an
# implicit POST never reaches this table. Both spellings, because
# wing-commander-metrics-persist writes `--method PATCH` — which the
# -X-only parser before #339 read as a PATH named `--method` and
# dropped as out of scope. Every spelling gh accepts: `-X POST`,
# `-XPOST`, `-iX POST`, `--method POST`, `--method=POST`, quoted or not -- the
# flag parser above skips the attached forms as switches, so a
# space-only match here would read those writes as reads. The flag
# is found on the blanked call line (so one inside another flag's
# quoted value is not this call's), its method word on the raw one
# (blanking would erase a quoted `'POST'`) -- see api_level().
# When the call names its method more than once, gh (pflag) keeps
# the LAST value, so `-X POST ... -X GET` is a read and `-X GET
# ... -X POST` a write. A method held in a variable (`-X
# "$METHOD"`) is resolved through the step's assignments the way
# a PATH is; one that resolves to no literal (a `$(...)`, an
# Actions expression, an unassigned variable) fails the gate
# rather than being read as a read, by the same rule as an
# unresolvable PATH (code review of #944). Only a flag starting
# one of the call's own words counts: a `-X GET` inside another
# flag's `$(...)`, backtick or `${...}` value (all executable, so
# not blanked) belongs to that value, and reading it as the last
# method would turn a `-X POST` call whose `-f` value runs a
# nested `-X GET` command into a read.
API_METHOD_FLAG_RE = re.compile(r'(?:^|\s)(?P<flag>-i*X|--method(?![\w-]))')
SHELL_WORD_RE = re.compile(SHELL_WORD)
API_WRITE_METHOD_RE = re.compile(r'(?:POST|PATCH|PUT|DELETE)\b')


def norm_expr(raw):
    s = raw.strip()
    m = re.fullmatch(r"\$\{\{\s*(.*?)\s*\}\}", s)
    if m:
        return m.group(1).strip()
    if s.startswith('"') and s.endswith('"') and len(s) >= 2:
        s = s[1:-1]
    return s


def strip_heredocs(text):
    """Heredoc bodies are data for another interpreter (python, jq), never
    bash commands — a `gh ...` mentioned inside one (an error message a gate
    prints, e.g.) never actually runs. Strip them before scanning.
    A `<<WORD` the shell never executes is not an opener: auto-release's
    `echo 'verdict<<AUTO_RELEASE_VERDICT_EOF'` writes a $GITHUB_OUTPUT
    delimiter, and reading it as a heredoc hid the rest of that step,
    six maintainer-token `gh api` calls among it (code review of #939).
    An opener need not end its line: `cat <<EOF | jq ...` and
    `python3 - <<'PY' > out` open one too, and the rest of that line
    is still shell. Several openers on one line take their bodies in
    order, one after another, as bash does. A `<<` inside `$((...))`
    is a shift and a `<<<` a here-string, neither an opener; an
    unquoted delimiter must start like a name (`x << 2` is no
    opener) and is its whole word: `<<EOF-1`'s delimiter is
    `EOF-1`, as bash reads it -- cut at `EOF`, the body would hide
    the rest of the step, and read as no opener, the body's text
    would be scanned as shell (code review of #944). A quoted
    delimiter is everything between its quotes (`<<'END-X'`)."""
    out = []
    lines = text.splitlines()
    heredoc_re = re.compile(
        r"(?<!<)<<(?!<)-?[ \t]*(?:'([^'\n]+)'|" + '"' + r'([^"\n]+)' + '"'
        + r"|\\?([A-Za-z_][^\s;|&<>()'" + '"' + r"`\\]*)(?=[\s;|&<>()]|$))")
    i = 0
    while i < len(lines):
        line = lines[i]
        delims = []
        found = list(heredoc_re.finditer(line))
        if found:
            base = len("\n".join(out)) + (1 if out else 0)
            flags = executable_flags("\n".join(out + [line]))
            for m in found:
                if not flags[base + m.start()]:
                    continue
                if re.search(r"\(\((?:(?!\)\)).)*$", line[:m.start()]):
                    continue
                delims.append(m.group(1) or m.group(2) or m.group(3))
        out.append(line)
        i += 1
        for delim in delims:
            while i < len(lines) and lines[i].strip() != delim:
                i += 1
            if i < len(lines):
                out.append(lines[i])
                i += 1
    return "\n".join(out)


def strip_comments(text):
    return "\n".join(l for l in text.splitlines() if not l.strip().startswith("#"))


def executable_flags(text):
    """True per character where shell would actually EXECUTE what it finds,
    as opposed to inside a single-quoted or (non-substitution) double-quoted
    literal — e.g. the "gh workflow run ..." inside an `echo "...gh..."`
    human-facing message never runs. `$( ... )` command substitutions stay
    executable even nested inside double quotes, because bash really does
    run them there."""
    n = len(text)
    flags = [True] * n
    stack = []
    i = 0
    while i < n:
        c = text[i]
        top = stack[-1] if stack else None
        cur_exec = top not in ("sq", "dq")
        flags[i] = cur_exec
        if c == "\\" and top != "sq" and i + 1 < n:
            flags[i + 1] = cur_exec
            i += 2
            continue
        if top == "sq":
            if c == "'":
                stack.pop()
            i += 1
            continue
        # T068: a `#` starting a word outside quotes opens a shell
        # comment running to end of line. strip_comments() only drops
        # WHOLE-line comments, so a TRAILING one reached this scanner
        # intact and its apostrophe (`target=1  # stage 8's resolve
        # job must fail`) pushed a bogus frame that hid every call
        # after it — that is what kept wing-commander-watchdog-test's
        # real `gh workflow run` invisible to Gate 12.
        if c == "#" and top != "dq" and (i == 0 or text[i - 1] in " \t\n"):
            j = text.find("\n", i)
            j = n if j < 0 else j
            for k in range(i, j):
                flags[k] = False
            i = j
            continue
        # T068: an apostrophe inside a DOUBLE-quoted string is a
        # literal, not a quote opener ("this project's constitution").
        # Pushing an `sq` frame for it made everything after it in the
        # step read as non-executable, silently hiding 10 real `gh`
        # calls repo-wide from this gate — including this feature's
        # own `gh pr comment` and rebase.yml's `gh label create`. `'`
        # still opens a frame inside `$( ... )`, where the shell
        # really does honour it.
        if c == "'" and top != "dq":
            stack.append("sq"); i += 1; continue
        if c == '"':
            stack.pop() if top == "dq" else stack.append("dq")
            i += 1; continue
        if c == "$" and i + 1 < n and text[i + 1] == "(":
            stack.append("sub"); i += 2; continue
        # A `(` or `)` inside a `${...}` pattern
        # (`"$(echo ${subject##*(#})"`) is a literal character,
        # not a level: pushed as one, the substitution's own `)`
        # closed it instead, the closing `"` opened a new
        # double-quoted frame, and every call after it in the
        # step read as quoted text (code review of f703d73).
        if top in ("sub", "brace") and c == "$" and i + 1 < n and text[i + 1] == "{":
            stack.append("brace"); i += 2; continue
        if top == "brace":
            if c == "{":
                stack.append("brace")
            elif c == "}":
                stack.pop()
            i += 1
            continue
        # A bare `(` inside a substitution (`$((p+1))`'s second
        # one, a `$( (a) )` subshell) opens a level its own `)`
        # closes; unpaired, the first `)` closed the substitution
        # and the last one read as quoted text, so cmdline_of's
        # depth count never got back to 0 and the call ran on
        # through the next command's flags (code review of #944).
        if top == "sub" and c == "(":
            stack.append("sub"); i += 1; continue
        if top == "sub" and c == ")":
            stack.pop(); i += 1; continue
        i += 1
    return flags


def collect_assignments(text):
    out = {}
    for m in ASSIGN_RE.finditer(text):
        out.setdefault(m.group(1), []).append(m.group(2))
    return out


# NEVER write the literal two-brace expression opener in this (or any)
# run: block, even inside a quoted Python string in a heredoc.
# GitHub's own workflow parser scans run: text for expressions before
# anything executes, and an opener with no closer fails the WHOLE file
# with "The expression is not closed" — the file then does not
# register, its checks silently never appear on the PR, and only Gate
# 1 (which reads the default branch, post-merge) would notice. Build
# the sequence by concatenation instead.
EXPR_OPEN = "${" + "{"

def resolve_paths(path, assigns, depth=0):
    path = norm_expr(path)
    if depth > 5 or path.startswith(EXPR_OPEN):
        return [path]
    if path.startswith("$("):
        return [None]
    if path.startswith("$"):
        varname = path[1:].strip("{}")
        if varname in assigns:
            out = []
            for v in assigns[varname]:
                out.extend(resolve_paths(v, assigns, depth + 1))
            return out
        return [None]
    return [path]


def path_category(path_text):
    """-> ('SELF'|'CROSS', category) for a repos/OWNER/REPO/... path, or
    ('OTHER', None) for anything else (org/user endpoints, GraphQL, etc.).
    A query string is not a path segment: `actions/variables?per_page=30`
    is the Variables surface all the same. Only a `?` outside `${...}`
    starts one; `${GITHUB_REPOSITORY:?}` is a parameter expansion."""
    path_text = re.split(r"\?(?![^{}]*\})", path_text, maxsplit=1)[0]
    segs = [s for s in path_text.strip("/").split("/") if s]
    if not segs or segs[0] != "repos":
        return "OTHER", None
    rest = segs[1:]
    if not rest:
        return "OTHER", None
    if rest[0].startswith("$"):
        rest = rest[1:]           # one token already carries owner/repo
        scope = "SELF"
    elif rest[:2] == ["{owner}", "{repo}"]:
        rest = rest[2:]           # gh fills these from the current repository
        scope = "SELF"
    else:
        rest = rest[2:] if len(rest) >= 2 else []
        scope = "CROSS"           # a literal, different owner/repo pair
    if rest[:1] == ["actions"] and len(rest) >= 2 and rest[1] in ACTIONS_SUBPATHS:
        # Under actions/ by path, but another permission's surface,
        # not "Actions" (fine-grained reference; code reviews of
        # #924 and #939) -- the same split SUBCOMMAND_PERMS makes
        # for `gh variable`.
        return scope, f"actions/{rest[1]}"
    return (scope, rest[0]) if rest else (scope, None)


def classify_token_expr(expr, app_exprs):
    """-> (kind, detail) for a normalised token expression."""
    if expr in app_exprs:
        return "app", expr
    if expr in DEFAULT_TOKEN_EXPRS:
        return "default", expr
    return "other", expr


def resolve_token(tokexpr, step_env, job_env, app_exprs, classify=None):
    """-> (kind, detail). kind in app/default/other/unresolved.
    The one lookup chain for both scans: a per-command `GH_TOKEN="$X"`
    prefix names an env var resolved through step_env then job_env;
    otherwise the step's GH_TOKEN, then the job's. `classify` maps the
    expression found to (kind, detail); the default recognises the
    caller job's App exprs and github.token, and the composite walk
    passes one that first binds `inputs.*` through the call site."""
    if classify is None:
        def classify(expr, origin):
            return classify_token_expr(expr, app_exprs)

    # `origin` names the env the expression was read from ("step" or
    # "job"), or "literal" for an expression written into the
    # command itself: the composite walk classifies a job-env value
    # in the CALLER's step-id namespace and a step-env value in the
    # composite's own.
    envs = (("step", step_env), ("job", job_env))
    if tokexpr is not None:
        val = norm_expr(tokexpr)
        if val.startswith("$") and not val.startswith(EXPR_OPEN):
            varname = val[1:].strip("{}")
            for origin, env in envs:
                if varname in env:
                    kind, detail = classify(norm_expr(str(env[varname])), origin)
                    return kind, (varname if kind in ("app", "default") else detail)
            return "unresolved", varname
        return classify(val, "literal")

    for origin, env in envs:
        if "GH_TOKEN" in env:
            kind, detail = classify(norm_expr(str(env["GH_TOKEN"])), origin)
            return kind, (None if kind in ("app", "default") else detail)
    return "unresolved", None


def effective_job_permissions(wf, job):
    p = job.get("permissions")
    if p is None:
        p = wf.get("permissions")
    return p if isinstance(p, dict) else None


# T073: must honour the required LEVEL, exactly as its `default`
# sibling below does. Checking mere category membership let an
# App-token `gh issue create` pass against a Read-only `issues`
# grant and 403 at runtime — the very class of defect this gate
# exists to catch.
def permission_satisfied(level, granted):
    if granted is None:
        return False
    if level == "write":
        return granted == "write"
    return granted in ("read", "write")


def missing_perms(required, granted):
    return [(cat, level) for cat, level in sorted(required)
            if not permission_satisfied(level, granted.get(cat))]


def parse_app_permissions(path="docs/setup.md"):
    text = open(path, encoding="utf-8").read()
    m = re.search(r"\*\*Repository permissions\*\*:\n((?:\s*-\s*.+\n)+)", text)
    if not m:
        sys.exit(f"::error file={path}::Gate 12 could not find the "
                  f"'Repository permissions' bullet list this gate treats as "
                  f"the single source of truth for what the wing-commander-bot "
                  f"App may do. If it moved or was reworded, update this gate "
                  f"and the doc together.")
    perms = {}
    for line in m.group(1).splitlines():
        lm = re.match(r"\s*-\s*([A-Za-z ]+):\s*\*\*(.+?)\*\*", line)
        if not lm:
            continue
        name, level = lm.group(1).strip(), lm.group(2).strip().lower()
        if name.lower() == "everything else":
            continue
        key = name.lower().replace(" ", "-")
        if "write" in level:
            perms[key] = "write"
        elif "read" in level:
            perms[key] = "read"
    return perms


def check_call(where, label, required, tok_kind, tok_detail,
               app_perms, job_perms, failures, notes):
    if tok_kind == "app":
        missing = missing_perms(required, app_perms)
        if missing:
            failures.append(
                f"{where}: {label} runs under the App token, which needs "
                f"{missing} but docs/setup.md only grants it "
                f"{ {cat: app_perms.get(cat) or 'nothing' for cat, _ in missing} } "
                f"(full grant: {sorted(app_perms.items())}). "
                f"This 403s at runtime.")
        return
    if tok_kind == "default":
        if not required:
            return
        never = sorted({cat for cat, _ in required} & DEFAULT_TOKEN_NEVER_GRANTED)
        if never:
            failures.append(
                f"{where}: {label} runs under github.token, which needs "
                f"{sorted(required)}, but GitHub never grants github.token "
                f"{never}: no permissions: block can add it. This 403s at "
                f"runtime; run the call under a dedicated token that holds it.")
            return
        if job_perms is None:
            notes.append(f"{where}: {label} runs under github.token needing "
                         f"{sorted(required)}; this job declares no "
                         f"permissions: block (inherits the repo default), "
                         f"which Gate 12 cannot resolve - unverified.")
            return
        missing = missing_perms(required, job_perms)
        if missing:
            failures.append(
                f"{where}: {label} runs under github.token, which needs "
                f"{missing} but the job's effective permissions "
                f"are {job_perms}. This 403s at runtime.")
        return
    if tok_kind == "unresolved":
        failures.append(
            f"{where}: {label} - Gate 12 could not resolve which token this "
            f"call runs under ({tok_detail!r}), so it cannot verify the call "
            f"is safe.")
        return
    notes.append(f"{where}: {label} runs under an unrecognised token "
                 f"expression ({tok_detail!r}) - not the App token or "
                 f"github.token, so Gate 12 cannot check it against either "
                 f"permission model. Unverified.")


def cmdline_of(text, flags, m):
    """This invocation's own arguments: from the match to the end of
    its logical line (following `\\` continuations) or the next
    command separator (`;`, `&&`, `||`, `|`) at this call's own
    nesting level, with every non-executable character blanked — so
    a `--method POST` inside a quoted value, in a trailing comment,
    or in the NEXT command on the same line never reads as this
    call's method. A separator inside one of the call's own `$(...)`
    or backtick values does not end it, a newline there included
    (a multi-line `-f body="$(` ... `)"`), and a `)` closing a
    substitution the call itself sits in does: cut inside the
    value, the call's words would end in an unclosed `$(`, and a
    `-X GET | ...` in it would read as the call's last method
    (code review of 4b06261). -> (blanked, raw): the same span
    unblanked, character-aligned with it, for reading a quoted flag
    value."""
    out, raw = [], []
    i, n = m.start(), len(text)
    depth, in_bt = 0, False
    # Open `${...}` braces, innermost last, each with the paren
    # depth it opened at: a `(` or `)` directly inside one
    # (`${subject##*(#}`) is a pattern character, not a level.
    # Counted as one, the `(` never closed, and the call ran past
    # its own newline through the next command's `-X GET`
    # (code review of f703d73).
    braces = []
    # A call inside a backtick substitution ends at the backtick
    # closing it, as one inside `$(...)` ends at its `)`; read as
    # opening a nested value, it would carry the call on through
    # the next command's flags. Counted on the call's own line.
    outer_bt = sum(1 for j in range(text.rfind("\n", 0, m.start()) + 1,
                                    m.start())
                   if flags[j] and text[j] == "`"
                   and not (j > 0 and text[j - 1] == "\\")) % 2 == 1
    while i < n:
        c = text[i]
        if flags[i] and c == "\\" and i + 1 < n and text[i + 1] == "\n":
            out.append(" "); raw.append(" "); i += 2; continue
        if flags[i] and c == "\\" and i + 1 < n:
            out.append(c + (text[i + 1] if flags[i + 1] else " "))
            raw.append(c + text[i + 1])
            i += 2
            continue
        if flags[i] and c == "`":
            if outer_bt:
                break
            in_bt = not in_bt
        elif (flags[i] and c == "$" and i + 1 < n
                and text[i + 1] in "{("):
            if text[i + 1] == "{":
                braces.append(depth)
            else:
                depth += 1
            out.append(c + text[i + 1]); raw.append(c + text[i + 1])
            i += 2
            continue
        elif flags[i] and braces and braces[-1] == depth and c in "{}()":
            if c == "{":
                braces.append(depth)
            elif c == "}":
                braces.pop()
        elif flags[i] and c == "(":
            depth += 1
        elif flags[i] and c == ")":
            depth -= 1
            if depth < 0:
                break
        nested = depth > 0 or in_bt
        if flags[i] and c == "\n" and not nested:
            break
        if flags[i] and c in ";|" and not nested:
            break
        if (flags[i] and c == "&" and not nested
                and not (i > 0 and text[i - 1] == ">")):
            break
        out.append(c if flags[i] else " ")
        raw.append(c)
        i += 1
    return "".join(out), "".join(raw)


def resolve_methods(word, assigns, depth=0):
    """A method flag's word -> the literal methods it can hold, or
    None when any of them is not a literal. Walks the assignments
    itself rather than through resolve_paths(), whose norm_expr()
    strips an Actions expression assigned unquoted and unspaced
    (`METHOD=` then the expression) down to its bare text,
    `inputs.m` -- a literal no write method matches, so a method
    the caller supplies read as a read (code review of #944)."""
    word = re.sub(r'["\']', "", word)
    if (depth > 5 or EXPR_OPEN in word or "`" in word
            or "$(" in word):
        return None
    if "$" not in word:
        return [word]
    vm = re.fullmatch(r'\$(?:(\w+)|\{(\w+)\})', word)
    varname = vm and (vm.group(1) or vm.group(2))
    if not varname or varname not in assigns:
        return None
    out = []
    for v in assigns[varname]:
        sub = resolve_methods(v, assigns, depth + 1)
        if sub is None:
            return None
        out.extend(sub)
    return out


def api_level(cmdline, assigns):
    """-> (level, why): "write" when the LAST method flag can name
    a write, "read" when it names none or there is no method flag;
    level None, with `why` naming the word, when Gate 12 cannot
    read the call's method.

    Every word of the call must parse as one whole SHELL_WORD.
    One that does not -- a value nesting deeper than SUB_DEPTH, an
    opener it never closes -- fails the call closed, as an
    unresolvable method does in resolve_methods(): split at its
    blanks instead, a `-X GET` inside it started a word of its own
    and read as the call's last method, so every new depth limit
    was one more level for a write to hide behind (code review of
    #944). With no fallback split, the depth limits are safe by
    construction. A word starting where nothing executes is the
    call's trailing comment, and ends the walk."""
    blanked, raw = cmdline
    starts = set()
    i, n = 0, len(raw)
    while i < n:
        if raw[i].isspace():
            i += 1
            continue
        if blanked[i] == " ":
            break
        starts.add(i)
        wm = SHELL_WORD_RE.match(raw, i)
        if not wm or (wm.end() < n and not raw[wm.end()].isspace()):
            return None, (
                f"`gh api ... {raw[i:i + 40]}` - Gate 12 cannot read "
                f"this call's method: this word does not parse as "
                f"one shell word. It nests deeper than {SUB_DEPTH} "
                f"levels of " + "`$(...)` or `${...}`, or opens a "
                "quote, substitution or expression the call's line "
                "ends inside (an unquoted `||` or `&&` ends it), and "
                "split at its blanks, a method flag inside it would "
                "read as the call's own. Move the value into a "
                "variable assigned before the call.")
        i = wm.end()
    word = None
    for fm in API_METHOD_FLAG_RE.finditer(blanked):
        if fm.start("flag") not in starts:
            continue
        wm = re.match(r'(?:=|\s*)(' + SHELL_WORD + ')', raw[fm.end():])
        if wm:
            word = wm.group(1)
    if word is None:
        return "read", None
    methods = resolve_methods(word, assigns)
    if methods is None:
        return None, (
            f"`gh api ... {word}` - Gate 12 cannot resolve this "
            f"call's method to a literal value (it traces to a "
            f"`$(...)` computed value, an Actions expression or an "
            f"unset variable), so it cannot tell a read from a "
            f"write. Assign the method a literal in this step.")
    return ("write" if any(API_WRITE_METHOD_RE.match(x) for x in methods)
            else "read"), None


def check_gh_invocation(where, m, cmdline, assigns, tok_kind, tok_detail,
                        job_perms, app_perms, failures, notes):
    """One executable `gh` match -> the permission it needs -> check_call.
    Shared by the workflow scan (category A) and the composite walk
    (category D) so the two can never disagree about what a call needs."""
    if m.group("apipath"):
        resolved = resolve_paths(m.group("apipath"), assigns)
        if any(p is None for p in resolved):
            failures.append(
                f"{where}: `gh api {m.group('apipath')}` - Gate "
                f"12 cannot resolve this path to a literal "
                f"value (it traces to a `$(...)` computed "
                f"value or an unset variable), so it cannot "
                f"verify which permission this call needs. "
                f"Either make the path traceable or add it as "
                f"a reviewed exception.")
            return
        cats = {path_category(p) for p in resolved}
        level = None
        for scope, cat in cats:
            if scope != "SELF" or cat is None:
                continue  # cross-repo / non-repos path: a different repo's permission model, out of scope
            perm_cat = API_CATEGORY_PERM.get(cat)
            if perm_cat is None:
                failures.append(
                    f"{where}: `gh api ...{cat}/...` - Gate "
                    f"12's API_CATEGORY_PERM table has no "
                    f"entry for {cat!r}. Add one (with "
                    f"evidence of what permission it needs) "
                    f"rather than let an unrecognised call "
                    f"pass unchecked.")
                continue
            if level is None:
                level, why = api_level(cmdline, assigns)
                if level is None:
                    failures.append(f"{where}: {why}")
                    return
            check_call(where, f"gh api (.../{cat}/...)",
                       frozenset({(perm_cat, level)}),
                       tok_kind, tok_detail, app_perms, job_perms,
                       failures, notes)
        return
    verb1, verb2 = m.group("verb1"), m.group("verb2")
    key = (verb1, verb2)
    if key not in SUBCOMMAND_PERMS:
        failures.append(
            f"{where}: `gh {verb1}"
            f"{(' ' + verb2) if verb2 else ''}` is not in "
            f"Gate 12's SUBCOMMAND_PERMS table. An "
            f"unrecognised subcommand must fail this gate, "
            f"not pass it silently - add an entry (with "
            f"evidence of the permission it needs) if this "
            f"is legitimate.")
        return
    check_call(where, f"gh {verb1} {verb2 or ''}".strip(),
               SUBCOMMAND_PERMS[key], tok_kind, tok_detail,
               app_perms, job_perms, failures, notes)


def executable_gh_calls(run):
    """[(match, cmdline, assigns)] for every `gh` invocation in a run:
    block that the shell would actually execute."""
    text = strip_comments(strip_heredocs(run))
    flags = executable_flags(text)
    assigns = collect_assignments(text)
    return [(m, cmdline_of(text, flags, m), assigns)
            for m in GH_INVOKE_RE.finditer(text) if flags[m.start()]]


def bind_input_expr(expr, decl_inputs, cs_with):
    """`inputs.<name>` inside a composite -> the expression the caller
    passed for it in `with:`, else the input's declared default.
    -> (expr, bound, from_caller); bound=False means neither exists,
    so the call would run under an empty token; from_caller=True
    means the expression is the caller's and lives in the caller
    job's step-id namespace."""
    im = re.fullmatch(r"inputs\.([\w-]+)", expr)
    if not im:
        return expr, True, False
    name = im.group(1)
    if name in cs_with and cs_with[name] not in (None, ""):
        return norm_expr(str(cs_with[name])), True, True
    default = (decl_inputs.get(name) or {}).get("default")
    if default not in (None, ""):
        return norm_expr(str(default)), True, False
    return expr, False, False


def resolve_composite_token(tokexpr, step_env, caller_job_env, decl_inputs,
                            cs_with, caller_app_exprs, comp_app_exprs):
    """resolve_token() for a step INSIDE a composite: the same lookup
    chain over the composite step's env then the CALLER's job env (a
    composite's steps run inside the calling job and see its env),
    with each expression bound through the call site's `with:` (or
    the input's default) before it is classified. `steps.<id>` means
    different things on the two sides: an expression the caller
    passed (or the caller's own job env) is read against the CALLER
    job's minted tokens, one written inside the composite against the
    composite's own — a step id that happens to exist on both sides
    must never let one side's App token vouch for the other's."""
    def classify(expr, origin):
        expr, bound, from_caller = bind_input_expr(expr, decl_inputs, cs_with)
        if not bound:
            return "unresolved", f"{expr}: not passed at this call site and no default"
        caller_side = from_caller or origin == "job"
        return classify_token_expr(expr, caller_app_exprs if caller_side
                                   else comp_app_exprs)

    return resolve_token(tokexpr, step_env, caller_job_env, caller_app_exprs,
                         classify)


app_perms = parse_app_permissions()
failures = []
notes = []
# #215: category C's two halves, filled during the pass below and
# cross-checked after it, because a call site in one file names an
# agent step in another and the files are visited in glob order.
agent_contexts = {}   # workflow path -> [(job, step, tok_kind, tok_detail, perms)]
callsite_grants = []  # (caller, caller-job, called-workflow, [(v1, v2, input)])
# #339: category D's call sites, filled during the pass below and
# walked after it — composite dir under .github/actions/ ->
# [(caller, job, step, with, job env, job perms, job App exprs)].
composite_callsites = {}

for f in sorted(glob.glob(".github/workflows/*.yml") + glob.glob(".github/workflows/*.yaml")):
    try:
        wf = yaml.safe_load(open(f, encoding="utf-8")) or {}
    except Exception as e:
        failures.append(f"{f}: YAML parse failure: {e}")
        continue

    for jname, job in (wf.get("jobs") or {}).items():
        job = job or {}
        job_env = job.get("env") or {}
        job_perms = effective_job_permissions(wf, job)
        job_app_exprs = app_token_exprs_for(job)
        pending_tools = []  # (verb1, verb2, source-step-name)

        # --- category C: tools granted where a stage is CALLED -----
        # A job with `uses:` has no steps, so the loop below never
        # sees it. The tools it passes reach the called stage's agent
        # steps all the same, arriving at the tool-args composite as
        # an unexpanded `inputs.extra-allowed-tools` expression - a
        # literal that category B
        # cannot read anything out of (#215).
        job_uses = str(job.get("uses") or "")
        if job_uses.startswith("./.github/workflows/"):
            called = job_uses.split("@")[0][2:]
            cs_with = job.get("with") or {}
            cs_grants = []
            for key in ("extra-allowed-tools", "allowed-tools-override"):
                val = cs_with.get(key)
                # EXPR_OPEN, not the literal: GitHub's parser scans
                # run: text for expressions and rejects the WHOLE file
                # on one, while yaml.safe_load and bash -n both pass it.
                if not isinstance(val, str) or EXPR_OPEN in val:
                    continue
                for gm in TOOL_GH_RE.finditer(val):
                    cs_grants.append((gm.group(1), gm.group(2), key))
            if cs_grants:
                callsite_grants.append((f, jname, called, cs_grants))

        for step in job.get("steps") or []:
            step = step or {}
            sname = step.get("name") or step.get("id") or "<unnamed step>"
            step_env = step.get("env") or {}
            uses = step.get("uses", "")
            cm = COMPOSITE_USES_RE.match(str(uses).replace("\\", "/"))
            if cm:
                composite_callsites.setdefault(cm.group(1), []).append(
                    (f, jname, sname, step.get("with") or {}, job_env,
                     job_perms, job_app_exprs))

            # --- category A: literal invocations in run: blocks -----------
            run = step.get("run")
            if run:
                for m, cmdline, _assigns in executable_gh_calls(run):
                    where = f"{f} :: {jname} / {sname}"
                    tok_kind, tok_detail = resolve_token(
                        m.group("tokexpr"), step_env, job_env, job_app_exprs)
                    check_gh_invocation(where, m, cmdline, _assigns, tok_kind,
                                        tok_detail, job_perms, app_perms,
                                        failures, notes)

            # --- category B: Bash(gh ...) grants to an agent step ----------
            if "wing-commander-tool-args" in uses:
                with_ = step.get("with") or {}
                for key in ("default-allowed-tools", "extra-allowed-tools",
                            "allowed-tools-override"):
                    val = with_.get(key)
                    if isinstance(val, str):
                        for gm in TOOL_GH_RE.finditer(val):
                            pending_tools.append((gm.group(1), gm.group(2), sname))

            if uses.startswith("anthropics/claude-code-action"):
                tok_kind, tok_detail = resolve_token(None, step_env, job_env,
                                                     job_app_exprs)
                # #215: the same context category C needs, recorded here
                # rather than re-derived, so the two checks can never
                # disagree about which token a step runs under.
                # glob() yields OS separators; a `uses:` path is always
                # posix. Keying on the raw value matched on Linux and
                # never on Windows, where the cross-check then reported
                # "no agent step found" for a stage that has several.
                agent_contexts.setdefault(
                    f.replace("\\", "/"), []).append(
                    (jname, sname, tok_kind, tok_detail, job_perms))
                where = f"{f} :: {jname} / {sname} (agent tool grant)"
                for verb1, verb2, source in pending_tools:
                    key = (verb1, verb2)
                    if key not in SUBCOMMAND_PERMS:
                        continue   # not a subcommand this table tracks (e.g. bare `gh api`) — not this gate's job to police free-form agent calls
                    check_call(f"{where} [granted by {source!r}]",
                               f"Bash(gh {verb1} {verb2 or ''})".strip(),
                               SUBCOMMAND_PERMS[key], tok_kind, tok_detail,
                               app_perms, job_perms, failures, notes)
                pending_tools = []

# --- category D: gh calls inside composite actions (#339) ----------
# A composite's steps run inside the calling job, under whatever
# token the caller handed its inputs, so each composite is checked
# once per call site in that caller's context. `_shared/` scripts
# are sourced by composites, never by workflows: a gh call in one
# has no resolvable token and fails here too.
action_files = sorted(
    glob.glob(".github/actions/**/action.yml", recursive=True)
    + glob.glob(".github/actions/**/action.yaml", recursive=True))
for af in action_files:
    afp = af.replace("\\", "/")
    comp_key = re.sub(r"^\.github/actions/", "", re.sub(r"/action\.ya?ml$", "", afp))
    try:
        act = yaml.safe_load(open(af, encoding="utf-8")) or {}
    except Exception as e:
        failures.append(f"{afp}: YAML parse failure: {e}")
        continue
    runs = act.get("runs") or {}
    if runs.get("using") != "composite":
        continue
    decl_inputs = act.get("inputs") or {}
    comp_steps = [st or {} for st in (runs.get("steps") or [])]
    comp_app_exprs = app_token_exprs_for({"steps": comp_steps})
    comp_calls = []   # (step name, step env, match, cmdline, assigns)
    for st in comp_steps:
        st_name = st.get("name") or st.get("id") or "<unnamed step>"
        st_uses = str(st.get("uses") or "")
        if COMPOSITE_USES_RE.match(st_uses):
            notes.append(f"{afp} :: {st_name} calls another local composite "
                         f"({st_uses}); Gate 12 resolves composite tokens one "
                         f"level deep, so that inner call is checked only "
                         f"through workflow call sites of its own.")
        run = st.get("run")
        if not run:
            continue
        for m, cmdline, assigns in executable_gh_calls(run):
            comp_calls.append((st_name, st.get("env") or {}, m, cmdline, assigns))
    if not comp_calls:
        continue
    sites = composite_callsites.get(comp_key)
    if not sites:
        failures.append(
            f"{afp}: makes {len(comp_calls)} gh call(s) but no workflow under "
            f".github/workflows uses this composite, so Gate 12 has no call "
            f"site to resolve its token from. A composite that calls gh must "
            f"be exercised by at least one workflow here; unresolvable is a "
            f"failure for the same reason an unknown subcommand is.")
        continue
    for cf, cj, cs_name, cs_with, cjob_env, cjob_perms, cjob_app in sites:
        for st_name, st_env, m, cmdline, assigns in comp_calls:
            where = f"{afp} :: {st_name} <- {cf} :: {cj} / {cs_name}"
            tok_kind, tok_detail = resolve_composite_token(
                m.group("tokexpr"), st_env, cjob_env, decl_inputs, cs_with,
                cjob_app, comp_app_exprs)
            check_gh_invocation(where, m, cmdline, assigns, tok_kind, tok_detail,
                                cjob_perms, app_perms, failures, notes)

for sh in sorted(glob.glob(".github/actions/_shared/*.sh")):
    shp = sh.replace("\\", "/")
    calls = executable_gh_calls(open(sh, encoding="utf-8").read())
    if calls:
        failures.append(
            f"{shp}: a _shared script makes {len(calls)} gh call(s). Shared "
            f"scripts are sourced from composites with whatever GH_TOKEN the "
            f"composite step exports, which Gate 12 cannot resolve — move the "
            f"call into the composite's own step.")

# --- category C cross-check (#215) ---------------------------------
# Every tool granted at a call site is checked against EVERY agent
# step in the stage it is passed to: a stage-level input reaches all
# of them, so a grant is only safe if it is safe for the least
# privileged one.
for src_file, src_job, called, cs_grants in callsite_grants:
    ctxs = agent_contexts.get(called)
    if not ctxs:
        failures.append(
            f"{src_file} :: {src_job} grants agent tools to "
            f"{called!r}, but Gate 12 found no agent step there to "
            f"check them against - the workflow may have moved or "
            f"the path may be wrong. Unresolvable is a failure here "
            f"for the same reason an unknown subcommand is.")
        continue
    for verb1, verb2, key in cs_grants:
        ckey = (verb1, verb2)
        if ckey not in SUBCOMMAND_PERMS:
            continue   # same policy as category B: not this gate's job
        for jname, sname, tok_kind, tok_detail, job_perms in ctxs:
            check_call(
                f"{src_file} :: {src_job} -> {called} :: {jname} / "
                f"{sname} (granted at the call site via {key!r})",
                f"Bash(gh {verb1} {verb2 or ''})".strip(),
                SUBCOMMAND_PERMS[ckey], tok_kind, tok_detail,
                app_perms, job_perms, failures, notes)

for n in notes:
    print(f"note: {n}")
for fl in failures:
    print(f"::error::Gate 12: {fl}")
print(f"Gate 12: checked every gh/API call site in {len(action_files)} composite action(s) "
      f"and every workflow for a permissioned token; {len(failures)} failure(s).")
sys.exit(1 if failures else 0)
