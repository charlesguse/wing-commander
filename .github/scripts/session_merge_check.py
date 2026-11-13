#!/usr/bin/env python3
"""May one of the owner's sessions merge this fix PR without asking?

    python3 .github/scripts/session_merge_check.py <PR number>

    exit 0  the checks on the exact head are green and the PR touches
            nothing reserved for the owner
    exit 1  reserved for the owner, or not ready: ask before merging
    exit 2  could not determine: treat it as reserved

CLAUDE.md ("Deciding without the owner") lets a session merge its own fix
PR on evidence. This script is the one home of two parts of that evidence:
whether the checks are green, and whether the PR touches something that is
the owner's to merge.

WHY THIS IS CODE
----------------
The reserved list was first written as prose. Three independent reviews
each found it incomplete, every time for code that decides a merge or a
review: the modules a merge script imports, the verdict actions, a prompt
edited inside a workflow. A list a session reads can be misread or left
half-checked with no error. This one is computed from the pull request's
own diff, and every rule below has a fixture in
verify-session-merge-check.py.

It fails closed. A file it cannot read, a patch GitHub left out, or a rule
it cannot evaluate ends in exit 2, never in exit 0.

WHAT IT DOES NOT CHECK
----------------------
- Whether an edit loosens what a gate fails on. Only a reviewer can say.
- Who reviewed the PR and what they found. CLAUDE.md states that condition.
The report names both every time, so a reader does not take silence for a
pass.
"""
import fnmatch
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

# --------------------------------------------------------------------------
# The reserved list. Each entry: (rule id, what the owner reads in a report).
# --------------------------------------------------------------------------
RULES = {
    "author": "not opened by the owner's account, or opened from a fork",
    "branch": "a lifecycle or pipeline pull request, or one not based on the default branch",
    "rules": "the rules agents run under (CLAUDE.md, .claude/, .specify/memory/, a waiver register)",
    "self": "this check, its gate or its fixtures",
    "decider": "what decides a merge, a review or a fix's shape, or a module one of those imports",
    "merge-job": "a job that merges, or the board loop's review or route job",
    "prompt": "an agent's prompt",
    "tools": "an agent's tool list",
    "permissions": "a permissions block",
    "credential": "a credential or a token mint",
    "kill-switch": "a kill-switch check",
    "contract": "the published workflow_call or action contract",
    "gate-removed": "a gate or one of its fixtures deleted or renamed",
    "gate-step": "a gate's step taken out of the suite, or made conditional",
}

LIFECYCLE_PREFIXES = ("spec/", "spec-draft/", "plan/", "tasks/", "impl/")

RULE_PATHS = ("CLAUDE.md", ".claude/*", ".specify/memory/*", "*-waivers.json")
SELF_PATHS = (
    ".github/scripts/session_merge_check.py",
    ".github/scripts/verify-session-merge-check.py",
)
# The scripts that decide. Whatever they import is reserved with them: see
# import_closure().
DECIDER_SCRIPTS = (
    "board_merge.py", "board_readiness.py", "board_route_backstop.py",
    "lifecycle_merge_preconditions.py", "wc_convergence.py", "spec_pr_review.py",
)
DECIDER_PATHS = (
    ".github/scripts/spec_pr_review*.py",
    ".github/workflows/spec-pr-review.yml",
    ".github/workflows/lifecycle-review-gate.yml",
    ".github/actions/wing-commander-size-path-backstop/*",
    ".github/actions/wing-commander-agent-verdict/*",
    ".github/actions/wing-commander-gate-verdict/*",
    ".github/actions/wing-commander-tool-args/*",
)
BOARD_LOOP = ".github/workflows/board-loop.yml"
BOARD_LOOP_JOBS = re.compile(r"(^|-)(review|route|merge)(-|$)")
MERGE_JOB = re.compile(r"merge")
LINT = ".github/workflows/lint-workflows.yml"

TOOLS_LINE = re.compile(r"allowed[-_]?tools|allowedTools|disallowedTools", re.I)
TOOLS_KEYS = ("allowed-tools", "disallowed-tools", "extra-allowed-tools", "extra-disallowed-tools",
              "allowed-tools-override", "disallowed-tools-override", "claude_args")
PERMISSION_LINE = re.compile(
    r"^\s*(actions|attestations|checks|contents|deployments|discussions|id-token|issues|"
    r"packages|pages|pull-requests|security-events|statuses):\s*(read|write|none)\b")
CREDENTIAL_LINE = re.compile(
    r"create-github-app-token|\bapp-id\b|private-key|secrets\.|\.outputs\.token\b|"
    r"OAUTH_TOKEN|API_KEY", re.I)
KILL_SWITCH_LINE = re.compile(r"_PAUSED\b")
# A waiver can be a table in a gate (EXEMPT_JOBS = {...}) or a marker
# comment beside the call it excuses (# wc-pagination-exempt: reason).
EXEMPT_TABLE = re.compile(r"^([A-Za-z_]*EXEMPT[A-Za-z_]*)\s*(?::[^=]*)?=\s*(.*)$")
EXEMPT_MARKER = re.compile(r"wc-[a-z-]+-exempt:")
STANDARD_GATE_IF = re.compile(r"""^\s*if:\s*(["']?)(\$\{\{\s*)?!cancelled\(\)(\s*\}\})?\1\s*$""")


def _match_any(path, patterns):
    return any(fnmatch.fnmatch(path, p) for p in patterns)


def is_workflow_yaml(path):
    return path.startswith(".github/workflows/") and path.endswith((".yml", ".yaml"))


def is_action_yaml(path):
    return path.startswith(".github/actions/") and os.path.basename(path) in ("action.yml", "action.yaml")


def is_script(path):
    """A Python or shell file under .github/, where a waiver table or an
    exemption marker can live."""
    return path.startswith(".github/") and path.endswith((".py", ".sh"))


def needs_text(path):
    return is_workflow_yaml(path) or is_action_yaml(path) or is_script(path)


# --------------------------------------------------------------------------
# Reading a patch and a YAML file's blocks, without a YAML parser
# --------------------------------------------------------------------------
HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def changed_lines(patch):
    """(added, removed): lists of (line number, text). `added` numbers are in
    the head file, `removed` numbers in the base file. None when the patch
    is missing or unreadable, so the caller fails closed."""
    if patch is None:
        return None
    added, removed = [], []
    old_no = new_no = None
    for line in patch.split("\n"):
        m = HUNK.match(line)
        if m:
            old_no, new_no = int(m.group(1)), int(m.group(3))
            continue
        if old_no is None:
            if line.strip():
                return None  # text before the first hunk header: not a patch we understand
            continue
        if line.startswith("+"):
            added.append((new_no, line[1:]))
            new_no += 1
        elif line.startswith("-"):
            removed.append((old_no, line[1:]))
            old_no += 1
        elif line.startswith("\\"):
            continue  # "\ No newline at end of file"
        else:
            old_no += 1
            new_no += 1
    return added, removed


def _indent(line):
    return len(line) - len(line.lstrip(" "))


def key_blocks(text, keys):
    """[(first line, last line, key)], 1-based and inclusive, for every
    `key:` line (or `- key:` list item) and the more-indented lines under it."""
    lines = text.split("\n")
    out = []
    pattern = re.compile(r"^(\s*)(- )?(%s):" % "|".join(re.escape(k) for k in keys))
    for i, line in enumerate(lines):
        m = pattern.match(line)
        if not m:
            continue
        depth = len(m.group(1)) + (2 if m.group(2) else 0)
        j = i + 1
        while j < len(lines) and (not lines[j].strip() or _indent(lines[j]) > depth):
            j += 1
        while j - 1 > i and not lines[j - 1].strip():
            j -= 1  # trailing blank lines belong to nobody
        out.append((i + 1, j, m.group(3)))
    return out


def job_blocks(text):
    """[(first line, last line, job id)] for each job under a top-level `jobs:`."""
    lines = text.split("\n")
    out, in_jobs, current = [], False, None
    for i, line in enumerate(lines):
        if re.match(r"^jobs:\s*(#.*)?$", line):
            in_jobs = True
            continue
        if in_jobs and line and not line.startswith((" ", "#")):
            in_jobs = False  # the next top-level key ends the jobs map
        m = re.match(r"^  ([A-Za-z0-9_-]+):\s*(#.*)?$", line) if in_jobs else None
        if m:
            if current:
                out.append((current[0], i, current[1]))
            current = (i + 1, m.group(1))
        elif not in_jobs and current:
            out.append((current[0], i, current[1]))
            current = None
    if current:
        out.append((current[0], len(lines), current[1]))
    return out


def exempt_blocks(text):
    """[(first line, last line, table name)] for each module-level table
    whose name contains EXEMPT. A table that opens a bracket runs to the
    first later line that starts with the closing bracket."""
    lines = text.split("\n")
    out = []
    for i, line in enumerate(lines):
        m = EXEMPT_TABLE.match(line)
        if not m:
            continue
        rest = m.group(2)
        opens = sum(rest.count(c) for c in "{[(")
        closes = sum(rest.count(c) for c in "}])")
        j = i
        if opens > closes:
            j = i + 1
            while j < len(lines) and not lines[j].startswith(("}", "]", ")")):
                j += 1
            j = min(j, len(lines) - 1)
        out.append((i + 1, j + 1, m.group(1)))
    return out


def _in_blocks(line_no, blocks):
    return [b for b in blocks if b[0] <= line_no <= b[1]]


# --------------------------------------------------------------------------
# Which scripts the deciders import
# --------------------------------------------------------------------------
IMPORT = re.compile(r"^\s*(?:from\s+([A-Za-z_][A-Za-z0-9_]*)\s+import|import\s+([A-Za-z_][A-Za-z0-9_]*))", re.M)


def import_closure(read_script, roots=DECIDER_SCRIPTS):
    """The decider scripts and every sibling module they import, directly or
    not. `read_script(name)` returns a script's text, or None when no such
    file sits beside the deciders."""
    seen, todo = set(), list(roots)
    while todo:
        name = todo.pop()
        if name in seen:
            continue
        text = read_script(name)
        if text is None:
            continue
        seen.add(name)
        for a, b in IMPORT.findall(text):
            todo.append((a or b) + ".py")
    return seen


def _read_sibling(name):
    path = os.path.join(HERE, name)
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return fh.read()


# --------------------------------------------------------------------------
# The classification
# --------------------------------------------------------------------------
def classify_pr(pr):
    """Reserved hits that come from the pull request itself, not its files."""
    hits = []
    if pr.get("is_cross_repository") or not pr.get("author") or pr.get("author") != pr.get("repo_owner"):
        hits.append(("author", "", "author %r, repository owner %r" % (pr.get("author"), pr.get("repo_owner"))))
    head = pr.get("head_ref") or ""
    if head.startswith(LIFECYCLE_PREFIXES):
        hits.append(("branch", "", "head branch %r is a lifecycle branch" % head))
    if not pr.get("base_ref") or pr.get("base_ref") != pr.get("default_branch"):
        hits.append(("branch", "", "base %r is not the default branch %r" % (pr.get("base_ref"), pr.get("default_branch"))))
    return hits


def classify_file(f, deciders):
    """(hits, unknowns) for one changed file. `f` has path, status,
    previous_path, patch, base_text and head_text (None where absent)."""
    path = f["path"]
    status = f.get("status") or "modified"
    names = [path] + ([f["previous_path"]] if f.get("previous_path") else [])
    hits, unknowns = [], []

    def hit(rule, detail):
        hits.append((rule, path, detail))

    for name in names:
        base = os.path.basename(name)
        if _match_any(name, RULE_PATHS):
            hit("rules", name)
        if name in SELF_PATHS:
            hit("self", name)
        if _match_any(name, DECIDER_PATHS) or (
                name.startswith(".github/scripts/") and name.count("/") == 2 and base in deciders):
            hit("decider", name)
        gate_file = name.startswith(".github/scripts/") and base.startswith("verify-")
        fixture = (name.startswith((".github/scripts/", ".github/actions/"))
                   and re.search(r"(^|/)[A-Za-z0-9_-]*(fixtures|tests)/", name))
        if status in ("removed", "renamed") and (gate_file or fixture):
            hit("gate-removed", "%s (%s)" % (name, status))

    script = is_script(path)
    if not (is_workflow_yaml(path) or is_action_yaml(path) or script):
        return hits, unknowns

    lines = changed_lines(f.get("patch"))
    if lines is None:
        if status == "renamed":
            return hits, unknowns  # a pure rename changes no line
        unknowns.append("%s: GitHub returned no patch, so its lines cannot be read" % path)
        return hits, unknowns
    added, removed = lines

    sides = []
    if added:
        if f.get("head_text") is None:
            unknowns.append("%s: the head version could not be read" % path)
        else:
            sides.append((added, f["head_text"]))
    if removed:
        if f.get("base_text") is None:
            unknowns.append("%s: the base version could not be read" % path)
        else:
            sides.append((removed, f["base_text"]))

    for _no, line in added:
        if EXEMPT_MARKER.search(line):
            hit("rules", "an exemption marker: %s" % line.strip()[:70])

    if script:
        for changed, text in sides:
            tables = exempt_blocks(text)
            for no, line in changed:
                for _a, _b, table in _in_blocks(no, tables):
                    hit("rules", "the waiver table %s, line %d" % (table, no))
        return hits, unknowns

    for changed, text in sides:
        prompt_blocks = key_blocks(text, ("prompt",))
        tool_blocks = key_blocks(text, TOOLS_KEYS)
        permission_blocks = key_blocks(text, ("permissions",))
        jobs = job_blocks(text) if is_workflow_yaml(path) else []
        contract_blocks = []
        if is_workflow_yaml(path):
            contract_blocks = key_blocks(text, ("workflow_call",))
        elif "/_" not in path:  # underscore-prefixed action directories are internal
            contract_blocks = [b for b in key_blocks(text, ("inputs", "outputs"))
                               if _indent(text.split("\n")[b[0] - 1]) == 0]
        for no, line in changed:
            if not line.strip():
                continue
            # Inside a prompt or a tool list a `#` line is content. Anywhere
            # else it is a YAML or shell comment, which runs nothing.
            if _in_blocks(no, prompt_blocks):
                hit("prompt", "line %d" % no)
            if _in_blocks(no, tool_blocks):
                hit("tools", "line %d: %s" % (no, line.strip()[:70]))
            if line.lstrip().startswith("#"):
                continue
            if TOOLS_LINE.search(line):
                hit("tools", "line %d: %s" % (no, line.strip()[:70]))
            if _in_blocks(no, permission_blocks) or PERMISSION_LINE.match(line):
                hit("permissions", "line %d: %s" % (no, line.strip()[:70]))
            if CREDENTIAL_LINE.search(line):
                hit("credential", "line %d: %s" % (no, line.strip()[:70]))
            if KILL_SWITCH_LINE.search(line):
                hit("kill-switch", "line %d: %s" % (no, line.strip()[:70]))
            if _in_blocks(no, contract_blocks):
                hit("contract", "line %d: %s" % (no, line.strip()[:70]))
            for _a, _b, job in _in_blocks(no, jobs):
                if MERGE_JOB.search(job) or (path == BOARD_LOOP and BOARD_LOOP_JOBS.search(job)):
                    hit("merge-job", "job %s, line %d" % (job, no))

    if path == LINT:
        for no, line in removed:
            if line.lstrip().startswith("#"):
                continue  # a comment names a gate without being its step
            if re.match(r"^\s*(- name:|run:)", line) or "verify-" in line:
                hit("gate-step", "removed line %d: %s" % (no, line.strip()[:70]))
        for no, line in added:
            if re.match(r"^\s*continue-on-error:", line):
                hit("gate-step", "added line %d: %s" % (no, line.strip()[:70]))
            elif re.match(r"^\s*if:", line) and not STANDARD_GATE_IF.match(line):
                hit("gate-step", "added line %d: %s" % (no, line.strip()[:70]))
    return hits, unknowns


def checks_green(checks):
    """(ok, why). Every check finished as success, skipped or neutral, at
    least one succeeded, and none is pending. No checks is not green."""
    if not checks:
        return False, "the head has no checks"
    pending = [c.get("name") or "?" for c in checks if (c.get("status") or "").upper() != "COMPLETED"]
    if pending:
        return False, "still running: " + ", ".join(sorted(pending))
    bad = [c.get("name") or "?" for c in checks
           if (c.get("conclusion") or "").upper() not in ("SUCCESS", "SKIPPED", "NEUTRAL")]
    if bad:
        return False, "not green: " + ", ".join(sorted(bad))
    if not any((c.get("conclusion") or "").upper() == "SUCCESS" for c in checks):
        return False, "no check succeeded"
    return True, "%d checks, none failing or pending" % len(checks)


def evaluate(pr, files, read_script=_read_sibling):
    """{exit, hits, unknowns, checks, not_ready}. Pure: all GitHub data is
    passed in."""
    deciders = import_closure(read_script)
    unknowns = []
    if not all(read_script(name) is not None for name in DECIDER_SCRIPTS):
        missing = [n for n in DECIDER_SCRIPTS if read_script(n) is None]
        unknowns.append("decider scripts missing beside this check: " + ", ".join(missing))
    hits = classify_pr(pr)
    if not files:
        unknowns.append("the pull request lists no changed files")
    for f in files:
        h, u = classify_file(f, deciders)
        hits += h
        unknowns += u
    ok, why = checks_green(pr.get("checks"))
    not_ready = []
    if (pr.get("state") or "").upper() != "OPEN":
        not_ready.append("the pull request is %s" % (pr.get("state") or "in an unknown state").lower())
    if pr.get("is_draft"):
        not_ready.append("the pull request is a draft")
    if (pr.get("review_decision") or "").upper() == "CHANGES_REQUESTED":
        not_ready.append("a changes-requested review stands")
    if not ok:
        not_ready.append("checks: " + why)
    if unknowns:
        code = 2
    elif hits or not_ready:
        code = 1
    else:
        code = 0
    return {"exit": code, "hits": hits, "unknowns": unknowns, "checks": why, "not_ready": not_ready}


def report(pr, result):
    out = ["Session merge check for #%s at %s" % (pr.get("number"), (pr.get("head_sha") or "?")[:12])]
    out.append("Checks on that head: %s" % result["checks"])
    if result["unknowns"]:
        out.append("COULD NOT DETERMINE (treat as reserved):")
        out += ["  - " + u for u in result["unknowns"]]
    if result["hits"]:
        out.append("RESERVED for the owner:")
        seen = set()
        for rule, path, detail in result["hits"]:
            key = (rule, path)
            if key in seen:
                continue
            seen.add(key)
            out.append("  - %s: %s%s" % (RULES[rule], (path + " " if path else ""), "(%s)" % detail if detail and detail != path else ""))
    if result["not_ready"]:
        out.append("NOT READY:")
        out += ["  - " + n for n in result["not_ready"]]
    if result["exit"] == 0:
        out.append("Not reserved, and the checks are green.")
    out.append("Not checked here: whether an edit loosens what a gate fails on; who reviewed this head and what they found.")
    out.append("Result: exit %d (%s)" % (result["exit"], {0: "may merge on evidence once the review conditions hold",
                                                        1: "ask the owner", 2: "could not determine, so ask the owner"}[result["exit"]]))
    return "\n".join(out)


# --------------------------------------------------------------------------
# GitHub lookups (the only impure part)
# --------------------------------------------------------------------------
def _gh(args):
    proc = subprocess.run(["gh"] + args, capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError("gh %s failed: %s" % (" ".join(args[:3]), proc.stderr.decode("utf-8", "replace").strip()[:300]))
    return proc.stdout.decode("utf-8", "replace")


def _raw(repo, path, sha):
    try:
        return _gh(["api", "-H", "Accept: application/vnd.github.raw", "repos/%s/contents/%s?ref=%s" % (repo, path, sha)])
    except RuntimeError:
        return None


def gather(number):
    repo_info = json.loads(_gh(["repo", "view", "--json", "nameWithOwner,owner,defaultBranchRef"]))
    repo = repo_info["nameWithOwner"]
    view = json.loads(_gh(["pr", "view", str(number), "--json",
                           "number,author,headRefName,baseRefName,headRefOid,isCrossRepository,isDraft,"
                           "reviewDecision,state,statusCheckRollup"]))
    checks = []
    for c in view.get("statusCheckRollup") or []:
        if c.get("__typename") == "StatusContext":
            state = (c.get("state") or "").upper()
            checks.append({"name": c.get("context"),
                           "status": "COMPLETED" if state not in ("PENDING", "EXPECTED", "") else "PENDING",
                           "conclusion": "SUCCESS" if state == "SUCCESS" else state})
        else:
            checks.append({"name": c.get("name"), "status": c.get("status"), "conclusion": c.get("conclusion")})
    head_sha = view["headRefOid"]
    compare = json.loads(_gh(["api", "repos/%s/compare/%s...%s" % (repo, view["baseRefName"], head_sha),
                              "--jq", "{base: .merge_base_commit.sha}"]))
    base_sha = compare["base"]
    listed = _gh(["api", "--paginate", "repos/%s/pulls/%s/files?per_page=100" % (repo, number), "--jq", ".[]"])
    files = []
    for row in listed.splitlines():
        if not row.strip():
            continue
        item = json.loads(row)
        path = item["filename"]
        f = {"path": path, "status": item.get("status"), "previous_path": item.get("previous_filename"),
             "patch": item.get("patch"), "base_text": None, "head_text": None}
        if needs_text(path):
            if item.get("status") != "removed":
                f["head_text"] = _raw(repo, path, head_sha)
            if item.get("status") != "added":
                f["base_text"] = _raw(repo, item.get("previous_filename") or path, base_sha)
        files.append(f)
    pr = {"number": view["number"], "author": (view.get("author") or {}).get("login"),
          "repo_owner": (repo_info.get("owner") or {}).get("login"),
          "is_cross_repository": view.get("isCrossRepository"), "is_draft": view.get("isDraft"),
          "head_ref": view.get("headRefName"), "base_ref": view.get("baseRefName"),
          "default_branch": (repo_info.get("defaultBranchRef") or {}).get("name"),
          "review_decision": view.get("reviewDecision"), "state": view.get("state"),
          "head_sha": head_sha, "checks": checks}
    return pr, files


def main(argv):
    if len(argv) != 1 or not argv[0].lstrip("#").isdigit():
        print(__doc__.split("\n\n")[1])
        return 2
    try:
        pr, files = gather(int(argv[0].lstrip("#")))
    except (RuntimeError, ValueError, KeyError, OSError) as exc:
        print("Session merge check: could not read the pull request: %s" % exc)
        print("Result: exit 2 (could not determine, so ask the owner)")
        return 2
    result = evaluate(pr, files)
    print(report(pr, result))
    return result["exit"]


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
