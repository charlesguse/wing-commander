#!/usr/bin/env python3
"""Gate 98 -- board-loop's fix, review and readiness jobs run helpers from
a pristine snapshot, never from the working tree (#583).

WHY THIS EXISTS
---------------
The fixer and review-fixup agents hold Write/Edit on the checkout, and the
review and readiness jobs check out a branch those agents wrote. Steps
after that import .github/scripts helpers and then comment, push and label
with the App token. Importing them from the working tree runs code an
agent could have changed. Each of the three jobs therefore takes a copy of
.github/scripts and .github/schemas from $GITHUB_SHA (the commit whose
board-loop.yml is running) right after checkout, before any agent step,
into $RUNNER_TEMP/wc-pristine, and makes it read-only. Every later step
imports from that copy.

WHAT IT CHECKS
--------------
In each of fix, review and readiness:
  1. exactly one "Snapshot helper scripts" step, directly after the job's
     actions/checkout step, before any agent step and before any other
     step that references the snapshot;
  2. the three snapshot steps' run: blocks are identical;
  3. an allowlist over every other run: block. Each python call is
     `python3 -I -`, `python3 -I -c`, or `python3 -I` on a script under
     "$RUNNER_TEMP/wc-pristine/scripts/"; the one exception is the
     gate-suite steps' `python3 .github/scripts/run-local-gates.py` (the
     gate suite checks the agent's change, so it runs the agent's tree by
     design). The interpreter must be spelled exactly `python3`: a path
     to it (/usr/bin/python3, venv/bin/python3), a versioned name
     (python3.12) or plain `python` is refused, so every spelling reaches
     the same argument check (#593). -I keeps the working directory off
     sys.path, so a json.py the agent writes cannot shadow the stdlib. The
     only sys.path change allowed is inserting the snapshot's scripts
     directory; a block that imports a board_*, wc_* or verify module must
     make that insert; a spec_from_file_location path must be under the
     snapshot; and PYTHONPATH, runpy, __import__,
     importlib.import_module, exec, eval and compile (with or without a
     space before the parenthesis), the site module (import site,
     site.addsitedir),
     sys.executable (a child interpreter started without -I) and os.chdir
     are refused. The working tree's .github/scripts must not be named at
     all. The interpreter and refused-pattern checks skip whole-line `#`
     comments (shell, or Python after indentation): a comment never runs,
     and prose such as "the python heredoc below" would otherwise trip them.
Then it runs the real snapshot step in a scratch git repository whose
working tree differs from the commit: the copy must hold the commit's
content, not the working tree's, and must be read-only.

--self-test applies one mutation per rule and asserts each is caught.

Usage: python3 .github/scripts/verify-board-loop-helper-provenance.py [--self-test]
Requires: bash, git, tar.
"""
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_shell_harness import resolve_bash, run_step, use_utf8_stdout  # noqa: E402

import yaml  # noqa: E402

WORKFLOW = os.path.join(".github", "workflows", "board-loop.yml")
JOBS = ("fix", "review", "readiness")
SNAPSHOT_NAME = "Snapshot helper scripts (before any agent runs)"
AGENT_USES = "anthropics/claude-code-action@"
GATE_SUITE_IDS = ("gate-suite", "gate-suite-review-fixup")
GATE_SUITE_CALL = "python3 .github/scripts/run-local-gates.py"
PRISTINE = "wc-pristine"
WORKTREE_SCRIPTS_RE = re.compile(
    r"\.github/scripts|\.github['\"]\s*,\s*['\"]scripts")
# Every spelling of a python interpreter: an optional path before it
# (/usr/bin/, venv/bin/, $HOME/bin/), then python, python3 or python3.N.
# Only a bare `python3` is allowed (see WHAT IT CHECKS, 3); matching the
# other spellings is what lets the gate refuse them (#593).
PYTHON_CALL_RE = re.compile(
    r"(?<![\w.-])(?P<prefix>[^\s\"'`()=;|&<>]*/)?"
    r"(?P<name>python(?:3(?:\.\d+)?)?)(?![\w./-])(?P<args>[^\n]*)")
ALLOWED_PYTHON_NAME = "python3"
ALLOWED_PYTHON_ARGS_RE = re.compile(
    r" -I (?:- |- *$|-c |\"\$RUNNER_TEMP/wc-pristine/scripts/[A-Za-z0-9_-]+\.py\")")
ALLOWED_SYS_PATH = (
    "sys.path.insert(0, os.path.join(os.environ['RUNNER_TEMP'], 'wc-pristine', 'scripts'))",
    'sys.path.insert(0, os.path.join(os.environ["RUNNER_TEMP"], "wc-pristine", "scripts"))',
)
# A whole-line comment in shell or Python: `#` after optional indentation.
# A trailing comment after code is left in place, so no code is hidden.
COMMENT_LINE_RE = re.compile(r"^[ \t]*#[^\n]*$", re.MULTILINE)
HELPER_IMPORT_RE = re.compile(r"\b(?:from|import)\s+(?:board_|wc_|verify)\w*")
FORBIDDEN = ("PYTHONPATH", "runpy", "__import__", "import_module", "os.chdir")
# (pattern, what the problem names) -- spellings a plain substring misses.
FORBIDDEN_RES = (
    (re.compile(r"\bexec\s*\("), "exec("),
    (re.compile(r"\beval\s*\("), "eval("),
    (re.compile(r"\bcompile\s*\("), "compile("),
    (re.compile(r"\baddsitedir\b"), "site.addsitedir"),
    (re.compile(r"\bsite[ \t]*\.[ \t]*[A-Za-z_]"), "the site module"),
    (re.compile(r"\b(?:import|from)[ \t]+(?:[\w.]+[ \t]*(?:as[ \t]+\w+[ \t]*)?,[ \t]*)*site\b"),
     "the site module"),
    (re.compile(r"\bsys[ \t]*\.[ \t]*executable\b"), "sys.executable"),
)


def run_problems(run, is_gate_suite):
    """Allowlist problems for one run: block (see WHAT IT CHECKS, 3)."""
    problems = []
    scan = run.replace(GATE_SUITE_CALL, "") if is_gate_suite else run
    code = COMMENT_LINE_RE.sub("", scan)
    for m in PYTHON_CALL_RE.finditer(code):
        if (m.group("prefix") is not None or m.group("name") != ALLOWED_PYTHON_NAME
                or code[m.start() - 1:m.start()] == "/"):
            problems.append("python interpreter not spelled `python3` (no path, no "
                            "version): {0!r}".format(m.group(0)[:80]))
        elif not ALLOWED_PYTHON_ARGS_RE.match(m.group("args")):
            problems.append("python call not in the allowlist (python3 -I -/-c, or "
                            "python3 -I on a snapshot script): {0!r}".format(m.group(0)[:80]))
    rest = scan
    for allowed in ALLOWED_SYS_PATH:
        rest = rest.replace(allowed, "")
    if "sys.path" in rest:
        problems.append("changes sys.path other than inserting the snapshot's scripts directory")
    if HELPER_IMPORT_RE.search(scan) and not any(a in scan for a in ALLOWED_SYS_PATH):
        problems.append("imports a repository helper without inserting the snapshot's "
                        "scripts directory")
    for m in re.finditer(r"spec_from_file_location\(", scan):
        head = scan[m.end():m.end() + 300]
        head = head[:head.find('.py"') + 4] if '.py"' in head else head
        if '"wc-pristine"' not in head and "'wc-pristine'" not in head:
            problems.append("spec_from_file_location loads a file outside the snapshot")
    for token in FORBIDDEN:
        if token in scan:
            problems.append("uses {0}".format(token))
    for pattern, what in FORBIDDEN_RES:
        if pattern.search(code):
            problems.append("uses {0}".format(what))
    if WORKTREE_SCRIPTS_RE.search(scan):
        problems.append("names the working tree's .github/scripts")
    return problems


def structural_problems(doc):
    problems = []
    snapshot_runs = {}
    jobs = doc.get("jobs") or {}
    for job_id in JOBS:
        steps = (jobs.get(job_id) or {}).get("steps") or []
        if not steps:
            problems.append("job {0!r} not found or has no steps".format(job_id))
            continue
        checkout = [i for i, s in enumerate(steps)
                    if str((s or {}).get("uses", "")).startswith("actions/checkout@")]
        snaps = [i for i, s in enumerate(steps) if (s or {}).get("name") == SNAPSHOT_NAME]
        if len(checkout) != 1:
            problems.append("{0}: expected one actions/checkout step, found {1}".format(
                job_id, len(checkout)))
            continue
        if len(snaps) != 1:
            problems.append("{0}: expected one {1!r} step, found {2}".format(
                job_id, SNAPSHOT_NAME, len(snaps)))
            continue
        snap = snaps[0]
        if snap != checkout[0] + 1:
            problems.append("{0}: the snapshot step is not directly after checkout".format(job_id))
        snapshot_runs[job_id] = str(steps[snap].get("run", ""))
        for i, step in enumerate(steps):
            step = step or {}
            label = "{0}: step {1!r}".format(job_id, step.get("name", i))
            if AGENT_USES in str(step.get("uses", "")) and i < snap:
                problems.append("{0} runs an agent before the snapshot".format(label))
            if i == snap or "run" not in step:
                continue
            run = str(step["run"])
            if PRISTINE in run and i < snap:
                problems.append("{0} reads the snapshot before it is taken".format(label))
            for p in run_problems(run, step.get("id") in GATE_SUITE_IDS):
                problems.append("{0}: {1}".format(label, p))
    if len(set(snapshot_runs.values())) > 1:
        problems.append("the snapshot steps' run: blocks differ between {0}".format(
            ", ".join(sorted(snapshot_runs))))
    return problems, snapshot_runs


def _git(cwd, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                    "-c", "commit.gpgsign=false"] + list(args),
                   cwd=cwd, check=True, capture_output=True)


def behaviour_problems(bash, snapshot_run, tmproot):
    """Runs the snapshot step in a scratch repository whose working tree
    has been edited after the commit."""
    repo = tempfile.mkdtemp(dir=tmproot)
    runner_temp = tempfile.mkdtemp(dir=tmproot)
    for sub in ("scripts", "schemas"):
        os.makedirs(os.path.join(repo, ".github", sub))
    with open(os.path.join(repo, ".github", "scripts", "helper.py"), "w") as fh:
        fh.write("PRISTINE = True\n")
    with open(os.path.join(repo, ".github", "schemas", "s.json"), "w") as fh:
        fh.write("{}\n")
    _git(repo, "init", "-q")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "c")
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, check=True,
                         capture_output=True, text=True).stdout.strip()
    # The agent's edit: the working tree no longer matches the commit.
    with open(os.path.join(repo, ".github", "scripts", "helper.py"), "w") as fh:
        fh.write("PRISTINE = False\n")
    with open(os.path.join(repo, ".github", "scripts", "planted.py"), "w") as fh:
        fh.write("PLANTED = True\n")
    problems = []
    try:
        rc, out, _o, _s = run_step(bash, snapshot_run, repo, {"GITHUB_SHA": sha}, runner_temp)
        if rc != 0:
            return ["the snapshot step exited {0}: {1}".format(rc, out.strip()[-400:])]
        base = os.path.join(runner_temp, PRISTINE)
        helper = os.path.join(base, "scripts", "helper.py")
        if not os.path.isfile(helper):
            return ["the snapshot has no scripts/helper.py"]
        if open(helper).read() != "PRISTINE = True\n":
            problems.append("the snapshot holds the working tree's edited helper, not the commit's")
        if os.path.exists(os.path.join(base, "scripts", "planted.py")):
            problems.append("the snapshot holds a file only the working tree has")
        if not os.path.isfile(os.path.join(base, "schemas", "s.json")):
            problems.append("the snapshot has no schemas/ beside scripts/")
        if os.stat(helper).st_mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH):
            problems.append("the snapshot is writable")
    finally:
        for root, dirs, files in os.walk(runner_temp):
            for name in dirs + files:
                try:
                    os.chmod(os.path.join(root, name), 0o755)
                except OSError:
                    pass
    return problems


def check(doc, bash, tmproot):
    problems, runs = structural_problems(doc)
    if runs:
        problems += behaviour_problems(bash, next(iter(runs.values())), tmproot)
    return problems


# --- self-test mutations: each must be caught ------------------------------

ONE_LINER = "sys.path.insert(0, os.path.join(os.environ['RUNNER_TEMP'], 'wc-pristine', 'scripts'))"
HEREDOC = 'sys.path.insert(0, os.path.join(os.environ["RUNNER_TEMP"], "wc-pristine", "scripts"))'
SPEC_CALL = 'python3 -I "$RUNNER_TEMP/wc-pristine/scripts/board_spec_request_body.py"'


def _replace_once(text, old, new):
    if old not in text:
        sys.exit("::error::Gate 98 self-test: {0!r} not found in {1}; update the "
                 "self-test alongside the workflow.".format(old[:60], WORKFLOW))
    return text.replace(old, new, 1)


def mut_one_liner_worktree(text):
    return _replace_once(text, ONE_LINER, "sys.path.insert(0, '.github/scripts')")


def mut_heredoc_worktree(text):
    return _replace_once(text, HEREDOC, 'sys.path.insert(0, ".github/scripts")')


def mut_spec_builder_worktree(text):
    return _replace_once(text, SPEC_CALL, "python3 .github/scripts/board_spec_request_body.py")


def mut_pathlib_worktree(text):
    return _replace_once(text, HEREDOC,
                         'sys.path.insert(0, str(pathlib.Path(".github") / "scripts"))')


def mut_cd_worktree(text):
    return _replace_once(text, SPEC_CALL, "cd .github && python3 -I scripts/board_spec_request_body.py")


def mut_no_isolation(text):
    return _replace_once(text, "python3 -I - <<'PYEOF'", "python3 - <<'PYEOF'")


# #593: interpreter spellings and import routes the first allowlist missed.
# Each is caught by the rule its expected substring names, not by another.
def _heredoc_call(spelling):
    return lambda text: _replace_once(text, "python3 -I - <<'PYEOF'", spelling + " <<'PYEOF'")


def _heredoc_append(code):
    return lambda text: _replace_once(text, HEREDOC, HEREDOC + "; " + code)


mut_absolute_path = _heredoc_call("/usr/bin/python3 -")
mut_absolute_path_isolated = _heredoc_call("/usr/bin/python3 -I -")
mut_env_python = _heredoc_call("/usr/bin/env python3 -")
mut_venv_path = _heredoc_call("venv/bin/python3 -I -")
mut_versioned = _heredoc_call("python3.11 -")
mut_versioned_isolated = _heredoc_call("python3.12 -I -")
mut_bare_python = _heredoc_call("python -I -")
mut_exec_space = _heredoc_append('exec (open("helper.py").read())')
mut_addsitedir = _heredoc_append("import site; site.addsitedir('.')")
mut_from_site = _heredoc_append("from site import addsitedir as a; a('.')")
mut_import_site = _heredoc_append("import os, site")
mut_sys_executable = _heredoc_append(
    "import subprocess; subprocess.run([sys.executable, '-c', 'import helper'])")
mut_eval = _heredoc_append('eval (compile_src)')
mut_compile = _heredoc_append('code = compile(open("helper.py").read(), "h", "exec")')

# Comment prose that tripped the pattern checks before comments were
# skipped. Each must pass as a comment and still be caught as code.
COMMENT_PROSE = (
    "data copied from site config",
    "sys.executable is not used here",
    "the python heredoc below",
    "exec (it) and eval (it) and compile (it) are not used here",
)


def comment_case_failures():
    failures = []
    for prose in COMMENT_PROSE:
        for indent in ("", "          "):
            comment = "echo start\n{0}# {1}\necho done\n".format(indent, prose)
            got = run_problems(comment, False)
            if got:
                failures.append("comment {0!r} (indent {1}) trips the gate: {2}".format(
                    prose, len(indent), got[0]))
        if not run_problems("echo start\n{0}\necho done\n".format(prose), False):
            failures.append("the same text as code is not caught: {0!r}".format(prose))
        else:
            print("note: comment skipped, code caught: {0!r}".format(prose))
    return failures


def _job_steps(doc, job_id):
    return doc["jobs"][job_id]["steps"]


def _snapshot_index(steps):
    return next(i for i, s in enumerate(steps) if (s or {}).get("name") == SNAPSHOT_NAME)


def mut_snapshot_dropped(doc):
    steps = _job_steps(doc, "readiness")
    del steps[_snapshot_index(steps)]
    return doc


def mut_snapshot_after_agent(doc):
    steps = _job_steps(doc, "review")
    snap = steps.pop(_snapshot_index(steps))
    agent = next(i for i, s in enumerate(steps) if AGENT_USES in str((s or {}).get("uses", "")))
    steps.insert(agent + 1, snap)
    return doc


def mut_snapshot_from_worktree(text):
    return re.sub(r"git archive [^\n]*\| tar [^\n]*\n",
                  'cp -R .github/scripts .github/schemas "$dest"/\n', text)


def mut_snapshot_writable(text):
    if 'chmod -R a-w "$dest"' not in text:
        sys.exit("::error::Gate 98 self-test: no chmod in the snapshot step; update the self-test.")
    return text.replace('chmod -R a-w "$dest"', 'true')


NAME = "not spelled `python3`"
ARGS = "not in the allowlist"

# (label, mutation, True when it edits the parsed document rather than text,
#  a substring the first problem must contain, or None for any problem)
MUTATIONS = [
    ("a post-agent one-liner imports from the working tree", mut_one_liner_worktree, False, None),
    ("a post-agent heredoc imports from the working tree", mut_heredoc_worktree, False, None),
    ("the spec-request builder runs from the working tree", mut_spec_builder_worktree, False, None),
    ("sys.path gets pathlib.Path(\".github\") / \"scripts\"", mut_pathlib_worktree, False, None),
    ("cd .github && python3 -I scripts/board_spec_request_body.py", mut_cd_worktree, False, None),
    ("a heredoc python3 runs without -I (the stdlib can be shadowed)", mut_no_isolation, False, ARGS),
    ("/usr/bin/python3 - (absolute path, no -I)", mut_absolute_path, False, NAME),
    ("/usr/bin/python3 -I - (absolute path)", mut_absolute_path_isolated, False, NAME),
    ("/usr/bin/env python3 - (no -I)", mut_env_python, False, ARGS),
    ("venv/bin/python3 -I - (relative path)", mut_venv_path, False, NAME),
    ("python3.11 - (versioned, no -I)", mut_versioned, False, NAME),
    ("python3.12 -I - (versioned)", mut_versioned_isolated, False, NAME),
    ("python -I - (no 3)", mut_bare_python, False, NAME),
    ("exec (...) with a space", mut_exec_space, False, "uses exec("),
    ("import site; site.addsitedir(...)", mut_addsitedir, False, "site"),
    ("from site import addsitedir", mut_from_site, False, "site"),
    ("import os, site", mut_import_site, False, "uses the site module"),
    ("subprocess.run([sys.executable, ...])", mut_sys_executable, False, "uses sys.executable"),
    ("eval (...)", mut_eval, False, "uses eval("),
    ("compile(...)", mut_compile, False, "uses compile("),
    ("readiness's snapshot step is removed", mut_snapshot_dropped, True, None),
    ("the review job's snapshot is taken after the reviewer agent", mut_snapshot_after_agent, True, None),
    ("the snapshot copies the working tree instead of $GITHUB_SHA", mut_snapshot_from_worktree, False,
     None),
    ("the snapshot is left writable", mut_snapshot_writable, False, None),
]


def main():
    use_utf8_stdout()
    self_test = "--self-test" in sys.argv[1:]
    if not os.path.isfile(WORKFLOW):
        sys.exit("::error::run this from the repository root; {0} not found.".format(WORKFLOW))
    bash = resolve_bash()
    text = open(WORKFLOW, encoding="utf-8").read()
    tmproot = tempfile.mkdtemp()
    failures = []
    try:
        base = check(yaml.safe_load(text), bash, tmproot)
        if self_test:
            if base:
                failures += ["the shipped workflow already fails: {0}".format(p) for p in base]
            failures += comment_case_failures()
            for label, mutate, on_doc, expect in MUTATIONS:
                doc = mutate(yaml.safe_load(text)) if on_doc else yaml.safe_load(mutate(text))
                caught = check(doc, bash, tmproot)
                if expect is not None:
                    caught = [p for p in caught if expect in p]
                if caught:
                    print("note: mutation caught ({0}): {1}".format(label, caught[0]))
                elif expect is not None:
                    failures.append("mutation {0!r} was NOT caught by its rule ({1!r})".format(
                        label, expect))
                else:
                    failures.append("mutation {0!r} was NOT caught".format(label))
        else:
            failures = base
    finally:
        for root, dirs, files in os.walk(tmproot):
            for name in dirs:
                try:
                    os.chmod(os.path.join(root, name), 0o755)
                except OSError:
                    pass
        shutil.rmtree(tmproot, ignore_errors=True)
    for f in failures:
        print("::error file={0}::Gate 98: {1}".format(WORKFLOW, f))
    if failures:
        return 1
    if self_test:
        print("Gate 98 self-test: {0} mutation(s), each caught; {1} comment case(s) "
              "skipped as comments and caught as code.".format(len(MUTATIONS), len(COMMENT_PROSE)))
    else:
        print("Gate 98: fix, review and readiness import helpers only from the "
              "pristine $GITHUB_SHA snapshot, taken before any agent runs.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
