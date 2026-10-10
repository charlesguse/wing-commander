#!/usr/bin/env python3
"""Gate 12 -- every `gh`/API call runs under a token whose permissions
actually cover what it touches.

The gate's rationale and rules are the comment above its step in
.github/workflows/lint-workflows.yml; this script is that step's body, moved
out of the workflow (specs/113-gh-callsite-locator FR-007). Finding the `gh`
calls in a `run:` block is wc_gh_callsites.locate()'s job alone: a call in a
form it cannot prove fails here with the authoring rule's heading, rather
than being guessed at (CONTRIBUTING.md, "Authoring rule for `gh` call
sites").

Usage: python3 .github/scripts/verify-gate-12-token-permissions.py
"""
import glob, os, re, sys, yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_gh_callsites import Dynamic, api_parts, locate  # noqa: E402

AUTHORING_RULE = "Authoring rule for `gh` call sites"
AUTHORING_RULE_DOC = "CONTRIBUTING.md"

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
# implicit POST never reaches this table. The spellings gh accepts
# (`-X POST`, `-XPOST`, `-iX POST`, `--method POST`, `--method=POST`)
# are read by wc_gh_callsites.api_parts() from the located call's own
# words, so a `-X GET` inside another flag's value is never this
# call's method. When the call names its method more than once, gh
# (pflag) keeps the LAST value, so `-X POST ... -X GET` is a read and
# `-X GET ... -X POST` a write. A method that is not a literal word
# is a disallowed form (wc_gh_callsites), never read as a read.
API_WRITE_METHOD_RE = re.compile(r'(?:POST|PATCH|PUT|DELETE)\b')


def norm_expr(raw):
    s = raw.strip()
    m = re.fullmatch(r"\$\{\{\s*(.*?)\s*\}\}", s)
    if m:
        return m.group(1).strip()
    if s.startswith('"') and s.endswith('"') and len(s) >= 2:
        s = s[1:-1]
    return s


def collect_assignments(text):
    out = {}
    text = "\n".join(l for l in text.splitlines() if not l.strip().startswith("#"))
    for m in ASSIGN_RE.finditer(text):
        out.setdefault(m.group(1), []).append(m.group(2))
    return out


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


def api_level(args):
    """-> (level, why): "write" when the LAST method flag names a write,
    "read" when it names none or there is no method flag; level None, with
    `why`, when the method is not a literal word (the locator already
    rejects such a call, so this is the belt to its braces)."""
    methods = api_parts(args)[1]
    if not methods:
        return "read", None
    last = methods[-1]
    if isinstance(last, Dynamic):
        return None, (
            f"`gh api ... {last}` - Gate 12 cannot resolve this call's method "
            f"to a literal value, so it cannot tell a read from a write.")
    return ("write" if API_WRITE_METHOD_RE.match(last) else "read"), None


def check_gh_invocation(where, tok, assigns, tok_kind, tok_detail,
                        job_perms, app_perms, failures, notes):
    """One located `gh` call -> the permission it needs -> check_call.
    Shared by the workflow scan (category A) and the composite walk
    (category D) so the two can never disagree about what a call needs."""
    argv = tok.argv
    api_path = api_parts(argv[1:])[0] if argv and argv[0] == "api" else None
    if api_path is not None:
        apipath = str(api_path)
        resolved = resolve_paths(apipath, assigns)
        if any(p is None for p in resolved):
            failures.append(
                f"{where}: `gh api {apipath}` - Gate "
                f"12 cannot resolve this path to a literal "
                f"value (it traces to a `$(...)` computed "
                f"value or an unset variable), so it cannot "
                f"verify which permission this call needs. "
                f"Either make the path traceable or add it as "
                f"a reviewed exception.")
            return
        if any(p.startswith("-") for p in resolved):
            failures.append(
                f"{where}: `gh api {apipath}` - the path resolves to a word "
                f"starting with `-`, which gh reads as a flag (a method could "
                f"hide there), so Gate 12 cannot tell what this call does.")
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
                level, why = api_level(argv[1:])
                if level is None:
                    failures.append(f"{where}: {why}")
                    return
            check_call(where, f"gh api (.../{cat}/...)",
                       frozenset({(perm_cat, level)}),
                       tok_kind, tok_detail, app_perms, job_perms,
                       failures, notes)
        return
    verb1 = str(argv[0]) if argv else ""
    verb2 = (str(argv[1]) if len(argv) > 1
             and re.fullmatch(r"[a-zA-Z][\w-]*", str(argv[1])) else None)
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


def scan_run(run, path, first_line, failures):
    """The `gh` calls of one run: block that this gate can check. A call in
    a form the locator cannot prove is a failure of its own, named by file
    and line, and is not checked further (FR-005)."""
    out = []
    for tok in locate(run):
        if tok.kind != "call":
            continue
        if tok.position == "disallowed":
            failures.append(
                f"{path}:{first_line + tok.line - 1}: gh call in a form Gate 12 "
                f"cannot verify ({tok.reason}) — rewrite it to the allowed form; "
                f"see {AUTHORING_RULE}.")
        else:
            out.append(tok)
    return out


def _map_get(node, key):
    if isinstance(node, yaml.MappingNode):
        for k, v in node.value:
            if getattr(k, "value", None) == key:
                return v
    return None


def run_lines(path, in_jobs):
    """{(job name or None, step index): 1-based line where that step's
    run: text starts}, from the YAML node marks (safe_load drops them)."""
    out = {}
    try:
        with open(path, encoding="utf-8") as fh:
            root = yaml.compose(fh)
    except Exception:
        return out
    if in_jobs:
        jobs = _map_get(root, "jobs")
        groups = [(k.value, _map_get(v, "steps")) for k, v in jobs.value
                  ] if isinstance(jobs, yaml.MappingNode) else []
    else:
        groups = [(None, _map_get(_map_get(root, "runs"), "steps"))]
    for jname, steps in groups:
        if not isinstance(steps, yaml.SequenceNode):
            continue
        for idx, st in enumerate(steps.value):
            run = _map_get(st, "run")
            if isinstance(run, yaml.ScalarNode):
                out[(jname, idx)] = run.start_mark.line + 1 + (run.style in ("|", ">"))
    return out


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
# Every disallowed-form failure points at the authoring rule's heading, so
# the heading has to be there to point at.
try:
    with open(AUTHORING_RULE_DOC, encoding="utf-8") as fh:
        rule_documented = f"### {AUTHORING_RULE}" in fh.read()
except OSError:
    rule_documented = False
if not rule_documented:
    failures.append(
        f"{AUTHORING_RULE_DOC}: no `### {AUTHORING_RULE}` section, which every "
        f"gh call-site failure from this gate tells the author to read.")
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
    wf_run_lines = run_lines(f, True)

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

        for sidx, step in enumerate(job.get("steps") or []):
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
                assigns = collect_assignments(run)
                for tok in scan_run(run, f, wf_run_lines.get((jname, sidx), 1),
                                    failures):
                    where = f"{f} :: {jname} / {sname}"
                    tok_kind, tok_detail = resolve_token(
                        tok.prefix_token, step_env, job_env, job_app_exprs)
                    check_gh_invocation(where, tok, assigns, tok_kind,
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
    comp_calls = []   # (step name, step env, located call, assigns)
    comp_run_lines = run_lines(af, False)
    for sidx, st in enumerate(comp_steps):
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
        assigns = collect_assignments(run)
        for tok in scan_run(run, afp, comp_run_lines.get((None, sidx), 1), failures):
            comp_calls.append((st_name, st.get("env") or {}, tok, assigns))
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
        for st_name, st_env, tok, assigns in comp_calls:
            where = f"{afp} :: {st_name} <- {cf} :: {cj} / {cs_name}"
            tok_kind, tok_detail = resolve_composite_token(
                tok.prefix_token, st_env, cjob_env, decl_inputs, cs_with,
                cjob_app, comp_app_exprs)
            check_gh_invocation(where, tok, assigns, tok_kind, tok_detail,
                                cjob_perms, app_perms, failures, notes)

for sh in sorted(glob.glob(".github/actions/_shared/*.sh")):
    shp = sh.replace("\\", "/")
    calls = [t for t in locate(open(sh, encoding="utf-8").read()) if t.kind == "call"]
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
