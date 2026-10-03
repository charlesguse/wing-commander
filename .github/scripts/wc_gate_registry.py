#!/usr/bin/env python3
"""Which scripts in .github/scripts are gates, and which workflows run them.

WHY THIS EXISTS
---------------
A verifier nothing runs is not a verifier. This repository learned that the
expensive way: verify-denied-tool-collector.sh sat in the tree unreferenced
by any workflow AND silently drifted out of sync with the filter it claimed
to check, so it read as evidence while proving nothing. PR #158 wired that
one script up. Nothing stopped the next one from landing the same way.

This module is the shared definition of the wiring, used by two consumers so
they cannot disagree about what a gate is:

  verify-gate-wiring.py   asserts, in CI, that the wiring is complete in both
                          directions.
  run-local-gates.py      runs the PR-time gates on a maintainer's machine.

THE CONVENTION (mechanical, not a manifest)
-------------------------------------------
  .github/scripts/verify-*.py|.sh    a check. MUST be invoked by a workflow.
  .github/scripts/*/run-tests.sh     a multi-file harness's entrypoint. Same.
  .github/scripts/wc_*.py            shared module. Exempt from the wiring
                                     rule; must be imported by something.
  anything else under a subdirectory  a helper of that subdirectory's
                                     entrypoint. Not independently wired.

Deliberately a convention rather than a list of gate names. A list is what
issue #149 was: forgetting to add a file to it is invisible, and a new gate
is born exempt. A naming rule cannot be forgotten silently, because the gate
that enforces it reads the same directory the author just added a file to.
"""
import glob
import os
import posixpath
import re
import shlex

import yaml

SCRIPTS_DIR = ".github/scripts"
WORKFLOWS_DIR = ".github/workflows"
ACTIONS_DIR = ".github/actions"
ACTIONS_SHARED_DIR = ACTIONS_DIR + "/_shared"
SUBDIR_ENTRYPOINT = "run-tests.sh"
SHARED_PREFIX = "wc_"
STANDALONE_VERIFY_RE = re.compile(r"verify-.*\.(?:py|sh)$")
# #877: a harness under .github/actions/ is not always called run-tests.sh
# (spec 074's fold-queue fixtures were `tests/run.sh`). Every file inside
# a `tests`/`test`/`spec`/`__tests__` directory of a composite belongs to
# a harness -- its scripts, `.bats` files and fixture data alike -- and a
# `run.sh` or extensionless `run` there is its entrypoint. Neither is
# outside such a directory: `${{ github.action_path }}/run.sh` is how a
# composite runs its own body, so it is matched by directory, never by
# name alone. Outside one, a test-named file (`test_*.py`, `*_test.sh`,
# `*.bats`) is a test too (code review of #939).
HARNESS_ENTRYPOINT_NAMES = (SUBDIR_ENTRYPOINT, "run.sh", "run")
HARNESS_DIR_NAMES = ("tests", "test", "spec", "__tests__")
TEST_FILE_RE = re.compile(
    r"(?:test_.+\.(?:py|sh|bash)|.+_test\.(?:py|sh|bash)|.+\.bats)$")


def _rel(path):
    """Repo-relative, forward slashes, no "./" prefix.

    The prefix matters: these paths are compared as substrings against the
    text of `run:` blocks, which spell them ".github/scripts/x" — so a
    "./.github/scripts/x" from glob() matches nothing and every check reads
    as orphaned. Normalising in one place is the only way this stays true for
    every caller.
    """
    out = path.replace(os.sep, "/")
    while out.startswith("./"):
        out = out[2:]
    return out


def gate_scripts(root="."):
    """Every script the wiring rule applies to, repo-relative."""
    base = os.path.join(root, SCRIPTS_DIR)
    found = set()
    for pattern in ("verify-*.py", "verify-*.sh"):
        found.update(glob.glob(os.path.join(base, pattern)))
    found.update(glob.glob(os.path.join(base, "*", SUBDIR_ENTRYPOINT)))
    prefix = _rel(os.path.join(root, "")) if root != "." else ""
    out = []
    for p in sorted(found):
        r = _rel(p)
        out.append(r[len(prefix):] if prefix and r.startswith(prefix) else r)
    return sorted(out)


def unsupported_actions_scripts(root="."):
    """Every path under .github/actions/ that a test harness or standalone
    gate script must not occupy -- see verify-actions-no-gate-scripts.py,
    the gate this feeds.

    Walks exactly `<root>/.github/actions`, never a broader sweep from
    `<root>`, so a sibling checkout directory elsewhere in the tree is
    unreachable by construction. At each directory: a `run-tests.sh`
    entrypoint is always flagged; otherwise a standalone
    `verify-*.py`/`verify-*.sh`, a test-named file (TEST_FILE_RE), and
    every file inside a composite's harness directory (HARNESS_DIR_NAMES;
    its `run.sh` and fixture data included), are flagged (#877) -- a
    file that shares its directory with a `run-tests.sh` is a helper of
    that harness, not a second violation.
    A composite's runtime scripts outside such a directory, a top-level
    `run.sh` among them, are not harnesses and are never flagged.
    `.github/actions/_shared/` is pruned from the walk entirely -- the
    carve-out is structural, not a name checked per file.
    """
    base = os.path.join(root, *ACTIONS_DIR.split("/"))
    if not os.path.isdir(base):
        return []
    prefix = _rel(os.path.join(root, "")) if root != "." else ""
    out = []
    for dirpath, dirnames, filenames in os.walk(base):
        rel_dir = _rel(dirpath)
        rel_dir = rel_dir[len(prefix):] if prefix and rel_dir.startswith(prefix) else rel_dir
        if rel_dir == ACTIONS_SHARED_DIR or rel_dir.startswith(ACTIONS_SHARED_DIR + "/"):
            dirnames[:] = []
            continue
        in_tests_dir = any(part in HARNESS_DIR_NAMES
                           for part in rel_dir.split("/")[3:])
        if SUBDIR_ENTRYPOINT in filenames:
            matches = [SUBDIR_ENTRYPOINT]
        else:
            matches = sorted(
                n for n in filenames
                if in_tests_dir or STANDALONE_VERIFY_RE.match(n)
                or TEST_FILE_RE.match(n))
        for name in matches:
            r = _rel(os.path.join(dirpath, name))
            out.append(r[len(prefix):] if prefix and r.startswith(prefix) else r)
    return sorted(out)


def referenced_actions_script_paths(root="."):
    """Every .github/actions/... path any run: block names, -> workflows.

    The reverse-direction sibling of `referenced_script_paths`, scoped to
    `.github/actions/` instead of `.github/scripts/`. Matches on the
    substring starting at `.github/actions/` regardless of what precedes it
    in the source line, so a self-checkout prefix
    (`./.wing-commander-pipeline/.github/actions/x.sh`) and the direct form
    (`./.github/actions/x.sh`) both key to the identical string.
    """
    pattern = re.compile(r"\.github/actions/[A-Za-z0-9_./-]+")
    result = {}
    for wf in workflow_files(root):
        for match in pattern.findall(_run_text(wf)):
            result.setdefault(match.rstrip("."), set()).add(wf)
    return {k: sorted(v) for k, v in sorted(result.items())}


def gate_label(script, args, root="."):
    """The display/cache/filter identity of one (script, args) gate call.

    `script`'s path relative to `.github/scripts/` -- never
    `os.path.basename`, which collapses every `.github/scripts/*/
    run-tests.sh` harness to the identical string `run-tests.sh`. For a
    script directly under `.github/scripts/` with no subdirectory, the
    relative form and the basename coincide, so this is a drop-in
    replacement for the old `label_of` on every gate that was never
    colliding, not only the ones that were. Two distinct files cannot
    share a repo-relative path, so this is unique across the whole gate
    population by construction -- no uniqueness check is needed at call
    sites.
    """
    prefix = SCRIPTS_DIR + "/"
    relative = script[len(prefix):] if script.startswith(prefix) else script
    return (relative + " " + " ".join(args)).strip()


def _self_check():
    """A path that keeps its "./" makes every check look orphaned.

    Cheap enough to run on import of the CLI paths, and it turns the most
    likely way this module breaks into an immediate, specific error rather
    than eight identical "not invoked by any workflow" reports.
    """
    bad = [p for p in gate_scripts() if p.startswith("./") or "\\" in p]
    if bad:
        raise AssertionError(
            f"wc_gate_registry produced non-normalised paths {bad!r}; they "
            f"will not match the text of any run: block and every check will "
            f"read as orphaned.")


def shared_modules(root="."):
    """The wc_*.py support modules, which are exempt from the wiring rule."""
    base = os.path.join(root, SCRIPTS_DIR)
    return sorted(_rel(p).split("/")[-1]
                  for p in glob.glob(os.path.join(base, SHARED_PREFIX + "*.py")))


def workflow_files(root="."):
    base = os.path.join(root, WORKFLOWS_DIR)
    return sorted(_rel(p) for p in
                  glob.glob(os.path.join(base, "*.yml"))
                  + glob.glob(os.path.join(base, "*.yaml")))


def _run_text(path):
    """Every `run:` block in a workflow, with shell comment lines removed.

    Comments are stripped so that MENTIONING a script in a comment does not
    count as running it — that is precisely how an orphan would hide from
    this check, and an orphan that looks wired is worse than an obvious one.
    """
    try:
        wf = yaml.safe_load(open(path, encoding="utf-8")) or {}
    except yaml.YAMLError:
        return ""          # the YAML guard rail reports this, with a better message
    chunks = []
    for job in (wf.get("jobs") or {}).values():
        for step in (job or {}).get("steps") or []:
            run = (step or {}).get("run")
            if run:
                chunks.append("\n".join(
                    l for l in str(run).splitlines()
                    if not l.lstrip().startswith("#")))
    return "\n".join(chunks)


def invocations(root="."):
    """script path -> sorted list of workflows whose run: blocks name it."""
    runs = {wf: _run_text(wf) for wf in workflow_files(root)}
    result = {}
    for script in gate_scripts(root):
        result[script] = sorted(wf for wf, text in runs.items()
                                if script in text)
    return result


def referenced_script_paths(root="."):
    """Every .github/scripts/... path any run: block names, -> workflows."""
    pattern = re.compile(r"\.github/scripts/[A-Za-z0-9_./-]+")
    result = {}
    for wf in workflow_files(root):
        for match in pattern.findall(_run_text(wf)):
            result.setdefault(match.rstrip("."), set()).add(wf)
    return {k: sorted(v) for k, v in sorted(result.items())}


def pr_time_gates(root=".", workflow=".github/workflows/lint-workflows.yml"):
    """The gates a given workflow runs — by default, the PR-time lint suite.

    Derived rather than listed, so a gate added to lint-workflows.yml is
    picked up by the local runner without anyone remembering to register it
    in a second place.
    """
    return [s for s, wfs in invocations(root).items() if workflow in wfs]


# Shell tokens that end a simple command. Argument capture stops at these so
# a redirect or a pipe is never mistaken for a flag to the gate.
_CMD_TERMINATORS = {"|", "||", "&&", ";", ">", ">>", "2>", "&"}


def _job_runs_on_pull_request(job):
    """Whether a job's `if:` lets it run for a pull_request event.

    Deliberately narrow: absent `if` means it runs, an `if` naming
    pull_request positively means it runs, and only an explicit
    `!= 'pull_request'` excludes it. Guessing at arbitrary expressions would
    be worse than useless here — a job wrongly excluded is a gate that
    silently stops running locally, which is the failure this module exists
    to prevent.
    """
    cond = str((job or {}).get("if") or "").strip()
    if not cond:
        return True
    if re.search(r"github\.event_name\s*!=\s*'pull_request'", cond):
        return False
    return True


def _invocations_in_run(text, script):
    """Every argv the `run:` text uses to invoke `script`, args only.

    Returns a list of argument lists — one per call site — so a gate CI
    invokes twice with different flags is reproduced twice locally rather
    than collapsed into whichever call the reader happened to find first.
    That promise used to hold only ACROSS lines: the token scan stopped at
    the first match on each line, so `x.py --self-test && x.py --other`
    yielded `--self-test` alone and the local suite quietly ran a different
    check than CI — the exact defect this function exists to close, one
    line-break away from being reintroduced. Today's two double-invoked
    gates sit on separate lines, which is luck, not design.

    Only the literal path is matched. Resolving a non-identical form
    (`"$SCRIPTS/verify-x.py"`) by basename was attempted here and was dead
    code — an `endswith` test followed immediately by an equality test that
    could never let it through. It stays out deliberately rather than being
    revived: two gate scripts sharing a basename would then cross-attribute
    silently, and the tree already has a nested entrypoint
    (auto-update-spec-kit-tests/run-tests.sh) that a future
    .github/scripts/run-tests.sh would collide with. A gate invoked through
    a form this does not resolve is not lost quietly either — `invocations`
    matches on the same literal, so it reports as orphaned and fails
    verify-gate-wiring.py loudly.
    """
    found = []
    for line in text.splitlines():
        if script not in line:
            continue
        try:
            tokens = shlex.split(line, comments=True)
        except ValueError:
            continue          # unbalanced quotes: a partial line, not a call
        for i, tok in enumerate(tokens):
            if tok != script:
                continue
            args = []
            for nxt in tokens[i + 1:]:
                if nxt in _CMD_TERMINATORS:
                    break
                args.append(nxt)
            found.append(args)
    return found


def pr_time_invocations(root=".",
                        workflow=".github/workflows/lint-workflows.yml"):
    """(script, args) for every gate call in a workflow's PR-time jobs.

    `pr_time_gates` answers "which gates run"; this answers "run how", and
    the difference is not cosmetic. Every gate here was previously invoked
    locally with NO arguments, which silently changed what some of them
    checked: `verify-versioning-refs.py` takes `--self-test` at PR time but
    defaults to `--remote origin`, so the local sweep reached across the
    network and failed offline on a check the PR never runs. A local suite
    that runs a different check than CI is not a rehearsal of CI.
    """
    path = os.path.join(root, workflow) if root != "." else workflow
    try:
        wf = yaml.safe_load(open(path, encoding="utf-8")) or {}
    except (yaml.YAMLError, OSError):
        return []
    scripts = set(gate_scripts(root))
    out = []
    seen = set()
    for job in (wf.get("jobs") or {}).values():
        if not _job_runs_on_pull_request(job):
            continue
        for step in (job or {}).get("steps") or []:
            run = (step or {}).get("run")
            if not run:
                continue
            text = "\n".join(l for l in str(run).splitlines()
                              if not l.lstrip().startswith("#"))
            for script in sorted(scripts):
                for args in _invocations_in_run(text, script):
                    key = (script, tuple(args))
                    if key not in seen:
                        seen.add(key)
                        out.append((script, args))
    return out


# The larger PR-time gates are not scripts at all: they are `python3 -
# <<'PYEOF'` heredocs inlined in lint-workflows.yml (Gates 2, 3, 5, 6, 7,
# 12, 15, 16, 22, 23 and the bash -n pass). `pr_time_invocations` cannot see them,
# so until #282's fix the local sweep ran only their synthetic self-tests
# (verify-gate-N.py) and never the shipped check over the real fleet:
# PR #301 passed 61/61 locally and failed Gate 12 in CI on a table entry
# the self-test's fixtures never exercise. The loose grammar below is the
# ONE home of "a line invoking python that opens a heredoc":
# verify-gate-wiring.py imports it to decide whether a heredoc was MISSED,
# so the two readers cannot disagree on membership.
LOOSE_PY_HEREDOC_RE = re.compile(r"^[ \t]*python3? +[^\n]*<<", re.M)


# A script a run: block executes (#825, code review of #939), read off
# shell tokens rather than raw text, so a path an `echo`/`printf` prints, a
# `test -f`/`[ -f ]` probes, a trailing `# comment` mentions or a URL
# carries is not mistaken for a call. Per simple command: an interpreter
# (`bash`/`sh`/`python`/`python3`) runs its first script-named argument,
# and a command word naming a script runs it directly; any other token
# naming a script under .github/ -- a loop over a glob, a `NAME=`
# assignment a later `bash "$NAME"` runs, a `--flag=` value handed to a
# gate -- is read too, so a shape this reader has not met fails loud
# rather than vanishing. `$NAME`/`${NAME}` is resolved from the step's own
# literal assignments and literal `env:` (step, job, workflow), and a
# relative path from a literal `working-directory:` (step, then job and
# workflow `defaults.run`).
#
# REPO_SCRIPT_RE reads one token. Group 1 is whatever it carries before
# `.github/`: empty, `./`, `NAME=` or `--flag=` is a literal repo path;
# anything else (`$VAR/`, an expression, a checkout prefix) is a path no
# reader can resolve.
REPO_SCRIPT_RE = re.compile(
    r"([^\s\"'`;&|()<>]*?)(\.github/[^\s\"'`;&|()<>]*?\.(?:sh|bash|py))(?![\w.-])")
SCRIPT_EXT_RE = re.compile(r"\.(?:sh|bash|py)$")
_INTERPRETERS = {"bash", "sh", "python", "python3"}
# A command whose arguments are data, never a script it runs.
_NON_EXEC_COMMANDS = {"echo", "printf", "test", "[", "[[", ":"}
# Words that open a command without being one.
_COMMAND_PREFIXES = {"if", "then", "else", "elif", "while", "until", "do",
                     "!", "{", "}", "time", "exec", "command", "export",
                     "readonly", "local", "declare"}
# Commands that run their trailing words as a command: their own options
# (`-n 10`, `-u root`, `--signal=KILL`) and leading operands (a timeout's
# duration, env's `NAME=value`) are skipped to reach the interpreter.
_COMMAND_WRAPPERS = {"timeout", "env", "nice", "nohup", "xargs", "sudo",
                     "stdbuf", "ionice", "setsid", "chronic"}
_REDIRECTS = {">", ">>", "<", ">&", "<&", "&>", "<<", "<<<", ">|", "<<-"}
_ASSIGN_RE = re.compile(r"([A-Za-z_]\w*)=(.*)", re.S)
_VAR_RE = re.compile(r"\$(?:\{([A-Za-z_]\w*)\}|([A-Za-z_]\w*))")
_EXPR_RE = re.compile(r"\$\{\{.*?\}\}", re.S)
# A shell in command position on a heredoc's line: `bash <<'EOF'`,
# `cat <<EOF | sh -e`, `timeout 300 bash <<EOF`. Group 1 is the rest of its
# command, which _feeds_shell reads to tell a shell running its stdin from
# one running a script (whose stdin the heredoc merely is). A wrapper's own
# options and operands (`-n 5`, `-u root`, a duration) are skipped as the
# command reader skips them; xargs is left out, since its stdin is
# arguments, not a script. Code review of #954, round 8: without the
# wrapper words a wrapped shell's heredoc read as data and its scripts
# vanished, where origin/main's raw-text regex saw them.
_HEREDOC_WRAPPERS = sorted(_COMMAND_WRAPPERS - {"xargs"})
_SHELL_ON_LINE_RE = re.compile(
    r"(?:^|[;&|(!{]|\b(?:then|do|else|exec|time|command)\b"
    r"|\b(?:" + "|".join(_HEREDOC_WRAPPERS) + r")\b"
    r"(?:[ \t]+(?!(?:bash|sh)(?![\w.-]))[^\s;&|()<>]+)*?)"
    r"[ \t]*(?:[A-Za-z_]\w*=\S*[ \t]+)*(?:bash|sh)(?![\w.-])([^;&|)\n]*)")


def _feeds_shell(line):
    """True when a heredoc opened on `line` is the stdin a shell runs as
    its script: some `bash`/`sh` on it takes only options (no script
    operand, no `-c` string). Code review of #954: such a body is code,
    and dropping it as data silently lost every script it runs."""
    for m in _SHELL_ON_LINE_RE.finditer(line):
        words, k, stdin, dash_s = m.group(1).split(), 0, True, False
        while k < len(words):
            w = words[k]
            if w == "--":
                break
            if w in ("-o", "+o", "-O", "+O") or re.fullmatch(r"\d*[<>]+[-&|]?", w):
                k += 2
                continue
            if re.match(r"\d*[<>]", w) or w.startswith(("+", "--")) or (
                    w.startswith("-") and "c" not in w[1:]):
                dash_s = dash_s or (w.startswith("-") and not w.startswith("--")
                                    and "s" in w[1:])
                k += 1
                continue
            # `-s` reads stdin whatever follows: `bash -s arg` hands `arg`
            # to it as $1. Otherwise a script operand, or a `-c` string.
            stdin = dash_s and not (w.startswith("-") and "c" in w[1:])
            break
        if stdin:
            return True
    return False


def _shell_prepass(text, i=0, nested=False, subs=None):
    """-> (text, [inner text, ...], end): `text` as bash reads its words,
    with comments and heredoc bodies dropped and each `$( )` lifted out
    into its own entry of `subs` (nested ones too; pass a list to append
    to it), leaving the placeholder word `__WC_CMDSUB_<index>__`, so the
    reader runs each body at the point bash does (code review of #954).

    Needed because shlex alone cannot read a run: block: its
    `comments=True` starts a comment at ANY `#`, mid-word too (`a#b`, a
    URL fragment), and it has no notion that quotes reset inside `$( )`,
    so `x="$(bash a.sh "$y")"` reads as two strings around a bare word and
    an apostrophe further on unbalances the rest. A heredoc body is data,
    like an `echo`'s arguments."""
    out, pending = [], []
    subs = [] if subs is None else subs
    quote, prev, depth = None, " ", 0
    while i < len(text):
        ch = text[i]
        if quote == "'":
            quote = None if ch == "'" else quote
        elif ch == "\\" and i + 1 < len(text):
            out.append(text[i:i + 2])
            i, prev = i + 2, "x"
            continue
        elif text.startswith("$(", i) and not text.startswith("$((", i):
            index = len(subs)
            subs.append("")
            subs[index], _, i = _shell_prepass(text, i + 2, nested=True,
                                               subs=subs)
            out.append(f"__WC_CMDSUB_{index}__")
            prev = "x"
            continue
        elif ch == "`":
            # The older `cmd` spelling of `$( )`, unescaped one level.
            j = i + 1
            while j < len(text) and text[j] != "`":
                j += 2 if text[j] == "\\" else 1
            index = len(subs)
            subs.append("")
            subs[index], _, _ = _shell_prepass(
                re.sub(r"\\([`$\\])", r"\1", text[i + 1:j]), subs=subs)
            out.append(f"__WC_CMDSUB_{index}__")
            i, prev = j + 1, "x"
            continue
        elif quote == '"':
            quote = None if ch == '"' else quote
        elif ch in "'\"":
            quote = ch
        elif ch == "#" and (prev.isspace() or prev in ";&|()"):
            end = text.find("\n", i)
            i = len(text) if end < 0 else end
            continue
        elif text.startswith("$((", i) or (
                text.startswith("((", i) and (prev.isspace() or prev in ";&|(")):
            # Arithmetic: `<<` inside shifts (`$((1 << n))`), it opens no
            # heredoc, so the expression is copied through to its `))`.
            j, level = i + (3 if ch == "$" else 2), 2
            while j < len(text) and level:
                level += {"(": 1, ")": -1}.get(text[j], 0)
                j += 1
            out.append(text[i:j])
            i, prev = j, "x"
            continue
        elif nested and ch == "(":
            depth += 1
        elif nested and ch == ")":
            if not depth:
                return "".join(out), subs, i + 1
            depth -= 1
        elif text.startswith("<<<", i):
            # A here-string: its word is an argument, not a delimiter.
            out.append("<<<")
            i, prev = i + 3, "x"
            continue
        elif text.startswith("<<", i):
            # A word delimiter, bare, quoted or backslash-quoted (`<<\EOF`).
            m = re.match(r"<<-?[ \t]*\\?(['\"]?)([\w.+@%:,/-]+)\1", text[i:])
            if m:
                out.append(text[i:i + m.end()])
                pending.append(m.group(2))
                i, prev = i + m.end(), "x"
                continue
        elif ch == "\n" and pending:
            so_far = "".join(out)
            shell_stdin = _feeds_shell(so_far[so_far.rfind("\n") + 1:])
            body = []
            for delim in pending:
                while i < len(text):
                    end = text.find("\n", i + 1)
                    end = len(text) if end < 0 else end
                    line, i = text[i + 1:end], end
                    if line.strip() == delim:
                        break
                    body.append(line)
            pending = []
            out.append("\n")
            if shell_stdin:
                # A body a shell runs is read as a run: block of its own,
                # at the point the shell runs it.
                index = len(subs)
                subs.append("")
                subs[index], _, _ = _shell_prepass("\n".join(body),
                                                   subs=subs)
                out.append(f"__WC_CMDSUB_{index}__\n")
            prev = "\n"
            continue
        out.append(ch)
        prev = ch
        i += 1
    return "".join(out), subs, i


def _shell_commands(text):
    """Yield (tokens, ok) per logical line of a prepassed run: block: its
    shlex tokens with `;`, `&&`, `|`, `(` and their kin as their own
    tokens, or (raw line, False) for a line no amount of joining balances.
    A line whose quote opens on it and closes on a later one is joined to
    them, as bash reads it."""
    lines = text.replace("\\\n", " ").split("\n")
    i = 0
    while i < len(lines):
        buf, j = lines[i], i
        while True:
            lexer = shlex.shlex(buf, posix=True, punctuation_chars=True)
            lexer.whitespace_split = True
            lexer.commenters = ""
            try:
                yield list(lexer), True
                break
            except ValueError:
                if j + 1 >= len(lines):
                    yield buf, False
                    break
                j += 1
                buf += "\n" + lines[j]
        i = j + 1


def _split_simple_commands(tokens):
    """[[token, ...] | "(" | ")", ...]: one list per simple command, split
    on the control operators shlex hands back as all-punctuation tokens,
    with each `(`/`)` they carry kept as a marker so a reader can scope a
    subshell group's `cd` and assignments to it."""
    out, cur = [], []
    for tok in tokens:
        if tok and all(c in ";&|()" for c in tok):
            if cur:
                out.append(cur)
            cur = []
            out.extend(c for c in tok if c in "()")
        else:
            cur.append(tok)
    if cur:
        out.append(cur)
    return out


def _literal_env(*blocks):
    """NAME -> value for every env: entry with no `${{ }}` expression."""
    env = {}
    for block in blocks:
        for k, v in (block or {}).items() if isinstance(block, dict) else ():
            if v is not None and "${{" not in str(v):
                env[str(k)] = str(v)
            else:
                # An expression overrides the outer block's literal value
                # at runtime, so the name is no longer known.
                env.pop(str(k), None)
    return env


def _expand(token, env):
    """`token` with every `$NAME`/`${NAME}` that `env` knows replaced."""
    return _VAR_RE.sub(
        lambda m: env.get(m.group(1) or m.group(2), m.group(0)), token)


_CMDSUB_RE = re.compile(r"__WC_CMDSUB_(\d+)__")
# Interpreter options that take the next word as their value.
_VALUE_OPTIONS = {"-o", "+o", "-O", "+O", "--rcfile", "--init-file",
                  "-W", "-X", "--check-hash-based-pycs"}


def _code_string_index(interpreter, args):
    """The index in `args` of a `-c` code string, or None: only the
    options ahead of the first operand are the interpreter's, and `c` may
    sit in a cluster (`-ec`, `-xc`). `python -m MOD` returns len(args):
    what follows is the module's arguments, never a script operand. A
    python `-W`/`-X` carries its value attached (`-Wonce`), not a `c`."""
    k = 0
    while k < len(args) and args[k][:1] in ("-", "+") \
            and args[k] not in ("-", "--"):
        opt = args[k]
        if opt in _VALUE_OPTIONS:
            k += 2
            continue
        if interpreter.startswith("python"):
            if opt == "-m":
                return len(args)
            if opt[:2] in ("-W", "-X"):
                k += 1
                continue
        if not opt.startswith("--") and "c" in opt[1:]:
            return k + 1
        k += 1
    return None


def _script_calls_in_run(run, env, workdir):
    """(scripts, unresolved) for one run: block -- see REPO_SCRIPT_RE.

    Commands are read in the order bash runs them: a `$( )` body before
    the command that holds it, with a copy of the variables in effect
    there (a subshell's assignments do not leak out); a `bash -c`/`sh -c`
    string as a run: block of its own, never as a script path; and a
    literal `cd` moves the directory later relative paths resolve from
    (code review of #954)."""
    scripts, unresolved = set(), set()
    # `${{ x }}` holds spaces; collapse it to one token-safe word so it
    # reaches the classifier whole, as a path no reader can resolve.
    text = _EXPR_RE.sub(lambda m: re.sub(r"\s+", "", m.group(0)), run)
    subs = []

    def literal_dir(wd):
        return wd is None or not re.search(r"[$*?{}\[]", wd)

    def relative(path, wd):
        path = re.sub(r"^(?:\./)+", "", path)
        if wd is None or path.startswith("/"):
            return path
        return posixpath.normpath(posixpath.join(wd, path))

    def interpreted(path, wd):
        # An interpreter's argument, or a command word: a `$` left after
        # expansion is a generated script (a runner temp file) unless it
        # names .github/, which REPO_SCRIPT_RE then reports.
        if "$" in path or "__WC_CMDSUB_" in path or path.startswith("/") \
                or "://" in path:
            return
        if not literal_dir(wd):
            unresolved.add(f"{wd}/{path}")
        elif re.search(r"[*?{}\[]", path):
            unresolved.add(relative(path, wd))
        else:
            scripts.add(relative(path, wd))

    def repo_token(token, wd):
        if "://" in token:
            return
        for m in REPO_SCRIPT_RE.finditer(token):
            prefix, script = m.group(1), m.group(2)
            literal = re.fullmatch(
                r"(?:--?[\w-]+=|[A-Za-z_]\w*=)?(?:\./)*", prefix)
            if literal and not re.search(r"[$*?{}\[]", script):
                if not literal_dir(wd):
                    unresolved.add(f"{wd}/{script}")
                else:
                    scripts.add(relative(script, wd))
            else:
                unresolved.add(prefix + script)

    def run_subs(token, env, wd):
        for m in _CMDSUB_RE.finditer(token):
            read(subs[int(m.group(1))], dict(env), wd)

    def read(prepassed, env, wd):
        """Read one prepassed block in the order bash runs it."""
        groups = []
        for tokens, ok in _shell_commands(prepassed):
            if not ok:
                # An unbalanced quote to the end of the block: no command
                # can be read off it, so every script it names is
                # unresolved.
                run_subs(tokens, env, wd)
                for m in REPO_SCRIPT_RE.finditer(tokens):
                    unresolved.add(m.group(1) + m.group(2))
                continue
            for cmd in _split_simple_commands(tokens):
                if cmd == "(":
                    # A `( )` group is a subshell: its `cd` and its
                    # assignments end at its `)`.
                    groups.append((wd, dict(env)))
                    continue
                if cmd == ")":
                    if groups:  # else a `case` pattern's `)`
                        wd, saved = groups.pop()
                        env.clear()
                        env.update(saved)
                    continue
                words = []
                skip_next = None
                stdin = None
                for tok in cmd:
                    run_subs(tok, env, wd)
                    if skip_next:
                        if skip_next in ("<", "0<"):
                            stdin = _expand(tok, env)
                        skip_next = None
                        continue
                    if tok in _REDIRECTS or re.fullmatch(r"\d*[<>]+&?", tok):
                        skip_next = tok
                        continue
                    words.append(_expand(tok, env))
                i = 0
                assigned = {}
                declared = False
                while i < len(words) and (words[i] in _COMMAND_PREFIXES
                                          or _ASSIGN_RE.fullmatch(words[i])):
                    m = _ASSIGN_RE.fullmatch(words[i])
                    if m and ("$" in m.group(2)
                              or "__WC_CMDSUB_" in m.group(2)):
                        # A value no reader can pin down replaces the
                        # earlier literal one too.
                        assigned[m.group(1)] = None
                    elif m:
                        assigned[m.group(1)] = m.group(2)
                    elif words[i] in ("export", "readonly", "local",
                                      "declare"):
                        declared = True
                    i += 1
                if declared or i >= len(words):
                    # `D=x` alone, or `export D=x`: the shell keeps it.
                    # `D=x cmd` sets D for cmd only (code review of #954,
                    # round 6).
                    for name, value in assigned.items():
                        if value is None:
                            env.pop(name, None)
                        else:
                            env[name] = value
                while i < len(words) and words[i] in _COMMAND_WRAPPERS:
                    i += 1
                    while i < len(words) and (
                            words[i].startswith("-") or _ASSIGN_RE.fullmatch(words[i])
                            or re.fullmatch(r"[\d.]+[smhd]?", words[i])
                            or (i and re.fullmatch(r"-[nuIgpLPs]|--user|--adjustment",
                                                   words[i - 1]))):
                        i += 1
                if i < len(words) and words[i] in _NON_EXEC_COMMANDS:
                    continue
                if i < len(words) and words[i] not in _INTERPRETERS \
                        and words[i] != "cd" \
                        and not SCRIPT_EXT_RE.search(words[i]):
                    # A wrapper this reader does not know (`xvfb-run -a`,
                    # `retry 3`, `env -C DIR`): an interpreter further on
                    # still runs its script, as origin/main's regex read
                    # it (code review of #954, round 5).
                    i = next((k for k in range(i + 1, len(words))
                              if words[k] in _INTERPRETERS), i)
                if i < len(words) and words[i] == "cd":
                    target = words[i + 1] if i + 1 < len(words) else "~"
                    if re.fullmatch(r"(?:\$\{?GITHUB_WORKSPACE\}?|\$\{\{\s*"
                                    r"github\.workspace\s*\}\})/*", target):
                        # The checkout root, where origin/main's regex
                        # read every repo path from (code review of #954,
                        # round 6).
                        wd = None
                    elif target.startswith(("/", "~", "-")) or "$" in target \
                            or "__WC_CMDSUB_" in target:
                        # A directory no reader can pin down.
                        wd = "$PWD"
                    elif literal_dir(wd):
                        wd = relative(target, wd)
                    continue
                inline = None
                if i < len(words) and words[i] in _INTERPRETERS:
                    args = words[i + 1:]
                    k = _code_string_index(words[i], args)
                    if k is not None:
                        # `-c STRING` (or `-ec`): the string is code, not a
                        # path; a shell's is read as a run: block of its
                        # own. Only the options ahead of the script count:
                        # `bash x.sh -c foo` hands `-c` to x.sh.
                        if words[i] in ("bash", "sh") and k < len(args):
                            inline = k
                    else:
                        arg = next((w for w in args if SCRIPT_EXT_RE.search(w)),
                                   None)
                        if arg is None and stdin is not None \
                                and SCRIPT_EXT_RE.search(stdin):
                            # `bash < x.sh`: the redirect is the script.
                            arg = stdin
                            repo_token(stdin, wd)
                        if arg is not None and ".github/" not in arg:
                            interpreted(arg, wd)
                    if inline is not None:
                        inner, _, _ = _shell_prepass(args[inline], subs=subs)
                        read(inner, dict(env), wd)
                        inline += i + 1
                elif i < len(words) and SCRIPT_EXT_RE.search(words[i]) \
                        and ".github/" not in words[i]:
                    interpreted(words[i], wd)
                for k, word in enumerate(words):
                    if k != inline:
                        repo_token(word, wd)

    outer, _, _ = _shell_prepass(text, subs=subs)
    read(outer, dict(env), workdir)
    return scripts, unresolved


def _working_directory(wf, job, step):
    """The step's effective `working-directory:`, or None."""
    for block in (step,
                  ((job or {}).get("defaults") or {}).get("run"),
                  ((wf or {}).get("defaults") or {}).get("run")):
        wd = (block or {}).get("working-directory")
        if wd:
            return str(wd).rstrip("/")
    return None


def pr_time_script_calls(root=".",
                         workflow=".github/workflows/lint-workflows.yml"):
    """[(step name, scripts, unresolved)] for every PR-time step whose run:
    block executes a script (REPO_SCRIPT_RE says how it is read).
    `scripts` are repo-relative paths; `unresolved` are the script tokens
    no reader can pin to one file (a `$` variable the step does not set
    literally, a `${{ }}` expression, a glob, a checkout prefix ahead of
    `.github/`, a `working-directory:` that is not literal).

    pr_time_invocations() sees only the gate scripts gate_scripts() names,
    so a step that runs anything else -- a composite's own fixture suite at
    `.github/actions/<name>/tests/run.sh`, a harness not named
    run-tests.sh -- runs in CI and is invisible to the local sweep, which
    stays green while CI goes red (#825). This is the reader that sees
    every script, for verify-gate-wiring.py to compare against the
    runner's. A python-heredoc step (LOOSE_PY_HEREDOC_RE, the grammar
    pr_time_inline_steps decides membership with) is skipped: the runner
    runs a runnable one verbatim, and an unrunnable one is already a
    verify-gate-wiring.py failure."""
    path = os.path.join(root, workflow) if root != "." else workflow
    try:
        wf = yaml.safe_load(open(path, encoding="utf-8")) or {}
    except (yaml.YAMLError, OSError):
        return []
    out = []
    for job in (wf.get("jobs") or {}).values():
        if not _job_runs_on_pull_request(job):
            continue
        for step in (job or {}).get("steps") or []:
            run = str((step or {}).get("run") or "")
            if not run or LOOSE_PY_HEREDOC_RE.search(run):
                continue
            env = _literal_env(wf.get("env"), (job or {}).get("env"),
                               step.get("env"))
            scripts, unresolved = _script_calls_in_run(
                run, env, _working_directory(wf, job, step))
            if scripts or unresolved:
                name = str(step.get("name") or "(unnamed step)")
                out.append((name, sorted(scripts), sorted(unresolved)))
    return out


def pr_time_inline_steps(root=".",
                         workflow=".github/workflows/lint-workflows.yml"):
    """(runnable, unrunnable) for every PR-time step whose run: block opens
    a python heredoc.

    `runnable` is [(step name, run text)]: steps a local sweep can execute
    VERBATIM - the whole run: block under `bash -e`, exactly as CI does -
    because they carry no `env:`, no `${{ }}` expression the runner would
    have to invent a value for, no `shell:` (step, job or workflow
    default) that would change CI's `bash -e {0}`, and no
    `working-directory:` (the same three places) that would move it off
    the repository root the runner runs it from. `unrunnable` is
    [(step name, reason)] for the rest. Returned rather than dropped so verify-gate-wiring.py can fail on a
    heredoc gate that quietly stopped being rehearsed locally, the same way
    check_local_runner_parity fails on a script gate the tokenizer cannot
    read.
    """
    path = os.path.join(root, workflow) if root != "." else workflow
    try:
        wf = yaml.safe_load(open(path, encoding="utf-8")) or {}
    except (yaml.YAMLError, OSError):
        return [], []
    runnable, unrunnable = [], []
    wf_shell = ((wf.get("defaults") or {}).get("run") or {}).get("shell")
    for job in (wf.get("jobs") or {}).values():
        if not _job_runs_on_pull_request(job):
            continue
        job_shell = (((job or {}).get("defaults") or {}).get("run")
                     or {}).get("shell") or wf_shell
        for step in (job or {}).get("steps") or []:
            run = str((step or {}).get("run") or "")
            if not LOOSE_PY_HEREDOC_RE.search(run):
                continue
            name = str(step.get("name") or "(unnamed step)")
            if step.get("env"):
                unrunnable.append((name, "the step carries an env: block"))
            elif step.get("shell") or job_shell:
                # run-local-gates.py runs every inline step as CI's
                # no-shell default, `bash -e {0}`; any shell: changes the
                # flags (bash's is -eo pipefail), so it is not verbatim.
                unrunnable.append((name, "the step runs under a shell: "
                                         "other than CI's default"))
            elif _working_directory(wf, job, step):
                # run-local-gates.py runs every inline step from the
                # repository root (code review of #942).
                unrunnable.append((name, "the step runs under a "
                                         "working-directory: other than "
                                         "the repository root"))
            elif "${{" in run:
                unrunnable.append((name, "the run: block carries a ${{ }} "
                                         "expression"))
            else:
                runnable.append((name, run))
    return runnable, unrunnable
