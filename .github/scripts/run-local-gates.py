#!/usr/bin/env python3
"""Run the PR-time gate suite locally. One command, no arguments needed.

    python .github/scripts/run-local-gates.py
    python .github/scripts/run-local-gates.py sentinel gate-7   # filter
    python .github/scripts/run-local-gates.py --jobs 1          # serial
    python .github/scripts/run-local-gates.py --changed         # what a change reaches
    python .github/scripts/run-local-gates.py --changed HEAD~3  # ... since HEAD~3

WHY THIS EXISTS
---------------
The checks in this directory are the repository's real safety net, and until
now the only way to run them was to read lint-workflows.yml, copy each `run:`
line out by hand, and discover one at a time that `python3` on Windows is the
Microsoft Store stub and `bash` is the WSL launcher. A gate suite that is
awkward to run before pushing gets run after pushing, which is how a verifier
ends up merged in a state where it cannot fail.

It is also the single command for spec artifacts to point at. A quickstart
that enumerates script paths goes stale the first time one is renamed; this
one does not, because the gate list is DERIVED from what lint-workflows.yml
actually invokes (wc_gate_registry.pr_time_invocations). Adding a gate to CI
adds it here, with nobody remembering to.

Arguments are derived too, and that part is load-bearing rather than tidy.
This runner used to invoke every gate bare, which for most of them merely
selected a default mode - but for `verify-versioning-refs.py` it changed the
SUBJECT. CI runs that one `--self-test`; bare, it defaults to
`--remote origin` and reaches across the network, so a maintainer running
the sweep offline or in a restricted sandbox got a confident FAIL on a check
the pull request never performs. A local suite that runs a different check
than CI is not a rehearsal of CI, and the discrepancy hides well because
both ends look green on a good day. A gate CI invokes twice with different
flags now runs twice here too.

INLINE GATES
------------
The larger gates are not scripts: Gates 2, 3, 5, 6, 7, 12, 15, 16, 22, 23
and the bash -n pass are `python3 - <<'PYEOF'` heredocs inlined in
lint-workflows.yml, and until #282's fix this runner could not see them.
It ran their self-tests (verify-gate-N.py, synthetic fixtures) and never
the shipped check over the real fleet, so PR #301 passed 61/61 locally
and then failed Gate 12 in CI on a table entry no fixture exercises. Each
such step's whole `run:` block now runs here VERBATIM under the resolved
bash -e, as CI's default `bash -e {0}` runs it
(wc_gate_registry.pr_time_inline_steps), labelled `inline-gate-N.sh`
(a repeated slug gets a `-2` suffix, so no step overwrites another), with `python3` on PATH shimmed to THIS interpreter -
bare `python3` on Windows is the Microsoft Store stub, the same trap
command_for avoids for the scripts. A heredoc step that cannot be run
verbatim (an env: block, a shell:, a working-directory:, a `${{ }}`
expression) is not silently dropped: verify-gate-wiring.py fails on it.

CHANGED-FILE SELECTION (--changed [BASE])
-----------------------------------------
`--changed` runs only the gates whose inputs differ from BASE (#1180), and
prints the changed files, then each gate it picked with the file and the
rule that picked it. BASE is any commit git resolves; without one it is
`git merge-base HEAD origin/main`. "Differ" is the working tree against
BASE: commits, staged and unstaged edits, deletions (both names of a
rename), and untracked files git does not ignore. `--changed=BASE` is the
unambiguous spelling; after a bare `--changed`, the next token is BASE only
when git resolves it to a commit, and is a filter otherwise. Filters still
narrow the picked set, and `--jobs` applies as usual.

What a gate reads is derived from its text, as the gate list is, never
listed. A gate's own files are its script, or a `<dir>/run-tests.sh`
harness's whole directory. Its references are read from those files and,
transitively, from code under .github/scripts/ and .github/actions/ that
they pull in (a file named by path, a file name only one file carries, a
composite's action.yml). Python is read off its syntax tree, so a path
in a docstring or a comment, or a sys.path entry, is not a read; a module
it imports counts only as far as it is used: the top-level statements,
the defs and constants the importer names, and what those use in turn.
Other files are read as text with their `#` comment lines dropped. A
reference is a string literal holding a path, an os.path.join/Path chain
of literals, or a shell word with a `/`; a variable or pattern component
(`$ROOT`, `{n}`, `*.yml`) stands for anything below what comes before it,
so `glob(os.path.join(ROOT, ".github", "workflows", "*.yml"))` reads every
workflow. A module-level name bound to the file's own directory
(`HERE = os.path.dirname(os.path.abspath(__file__))`) stands for that
directory, `..` included, so `glob(os.path.join(HERE, "**", "*.py"))`
reads everything beside the script. A changed file picks a gate when it is one of the gate's own or
pulled-in files, lies under or starts with one of its references, or has
a file name the gate's code names. A gate that lists every tracked file
(`git ls-files` with flags only), walks a root, or globs from `**` is
picked by any change.

It fails closed: a changed file no gate's inputs cover runs every gate,
and so does a change to SUITE_INPUTS -- this runner, the registry and the
helpers it loads gates through, and lint-workflows.yml, which the gate
list and the inline gates come from. No change runs no gate, and says so.
What it can miss is a read that no text shows (a path assembled from data
another file holds, or a reference only a sys.path entry carries), which
is why the full suite still runs before a push lands.
verify-run-local-gates-changed.py (Gate 176) drives each rule end to end.

WHAT IT DOES NOT RUN
--------------------
Checks wired to other workflows — verify-watchdog-run.sh belongs to the
watchdog self-test and needs a live run id and a token, so it is not
something a local sweep can honestly report on. verify-gate-wiring.py knows
about those; this runner only claims to cover the PR-time suite.

PARALLELISM (--jobs)
---------------------
Serial, the suite measured 1599s: one ~300s harness (run-tests.sh) and a
handful of 40-120s verify-*.py self-tests dominate, while most gates finish
in under 5s. Every gate here is already a subprocess.run of a SEPARATE
process, so a thread pool submitting those calls parallelises real wall
time with no GIL concern — the Python interpreter running this file is
never doing the CPU-bound work, it is just waiting on children.

Threads are safe to interleave here because a targeted audit (2026-08,
alongside this flag's introduction) found nothing that shares mutable state
across gates:

  * Every gate that needs a scratch directory gets it from
    `tempfile.mkdtemp()`/`mktemp -d`, which mints a fresh random-suffixed
    path per call — two gates, or two invocations of the SAME gate (a
    script CI invokes twice with different flags, see above), never
    collide on a fixed name the way a hard-coded `RUNNER_TEMP/foo` would.
  * `ensure_jq()` (wc_shell_harness.py) does not download anything — it
    only probes PATH and a fixed list of known local install directories
    and, at most, prepends one of them to THIS process's PATH. It runs
    once, before any gate is dispatched, so there is no concurrent-write
    window at all.
  * No gate mutates this repository's working tree. Every gate that runs
    `git init`/`add`/`commit`/`push` does so inside a throwaway repo it
    just created under its own temp dir (verify-stall-restart-runbook.py,
    the auto-update-spec-kit-tests harness, etc.) — the real checkout is
    read from, at most (e.g. `cp "$REPO"/.specify ...`), never written to.
  * Neither this runner nor any gate calls `os.chdir`. Gates that `cd`
    do so inside a bash subprocess of their own, which cannot change this
    process's (or a sibling thread's) working directory.

`--jobs 1` does not go through the pool at all — it keeps running the
original sequential loop verbatim, so its output and behavior stay
byte-for-byte what this script always produced. `--jobs N>1` prints one
PASS/FAIL line per gate as it COMPLETES (not in the list order above,
since faster gates finish out of order), with that gate's full output
inlined immediately below a FAIL. The final table and totals line are
still printed for both modes, so a parallel run and a serial run report
the same pass/fail facts even though the second column of a live run is
compressed to wall-clock time rather than the historical CI-style body.

SCHEDULING (the timing cache)
------------------------------
Submission order matters for a bounded pool: the registry orders gates
however wc_gate_registry happened to walk lint-workflows.yml, which is not
correlated with cost. Left as-is, the three ~300s gates can land late in
that order, so they start only after several worker-seconds have already
gone by and the run's tail becomes one worker grinding alone through a
gate that could have started at t=0 — the classic bin-packing mistake of
scheduling the heaviest items last.

The fix is a self-maintaining timing cache rather than a hard-coded list
of "the slow gates": a literal list is exactly the anti-pattern this
repository keeps re-discovering the expensive way (see the module-level
WHY THIS EXISTS above, and wc_gate_registry's own docstring on why gate
membership is a mechanical convention rather than a manifest) — it would
drift the moment a gate's cost changed materially, and nothing would ever
notice, because a stale schedule still finishes correctly, just slower.
A cache keyed by the same label this script already prints requires no
maintenance: every run records what it measured, so the schedule tracks
reality automatically.

  * Storage: `<tempdir>/wing-commander-gate-timings.json`, one JSON object
    of `{label: seconds}`. Machine-local scratch on purpose — it is a
    performance hint, not a fact about the repository, and committing it
    would make every maintainer's local hardware speed part of the diff.
    Written atomically (temp file in the same directory + os.replace) so
    a run killed mid-write cannot leave the next run reading a torn file,
    and merged with whatever was already there so a filtered run (three
    gates) does not evict the timings of the other fifty-four.
  * Loading is wrapped in a bare try/except returning {}: missing (first
    run ever), corrupt (killed mid-write on some OTHER machine sharing
    the temp dir, hand-edited, OS-cleaned mid-run), or simply absent for
    a label that never ran locally before are all the same case from the
    scheduler's point of view — proceed with no hint rather than fail the
    whole suite over a cache that only ever exists to make things faster.
  * Sort key: known durations descending, UNKNOWN LABELS FIRST (treated
    as heaviest). This is the safe default in both directions: a gate
    that turns out to be cheap merely starts a little early and finishes
    fast, costing nothing; a gate that turns out to be the next 300s
    outlier is never starved to the end of the queue by having no data
    yet. It also means a bare `--jobs N` with no cache present degrades
    to exactly today's registry-order behavior (every label ties at
    "unknown," so the stable sort leaves the original order untouched),
    and the very next run — cache now populated — self-heals into
    longest-first without anyone invoking a separate warm-up step.
  * `--jobs 1` records timings too (folded into the same cache the
    parallel path reads), so alternating between `--jobs 1` for a
    one-off debug run and the parallel default does not leave the cache
    stale — but it does not print anything about doing so, because its
    whole contract above is byte-identical output to the pre-cache
    script.
"""
import ast
import concurrent.futures
import json
import os
import posixpath
import re
import subprocess
import sys
import tempfile
import time
import warnings

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_gate_registry import (gate_label, pr_time_inline_steps,  # noqa: E402
                              pr_time_invocations)
from wc_repo_files import git_env, repo_files  # noqa: E402
from wc_shell_harness import (UNSPECIFIED_SHELL_HOSTED, ensure_jq,  # noqa: E402
                              resolve_bash, use_utf8_stdout)


TIMING_CACHE_PATH = os.path.join(tempfile.gettempdir(),
                                 "wing-commander-gate-timings.json")


def _load_timing_cache():
    """{label: last-measured seconds}, or {} on any reason it isn't usable.

    Deliberately a blanket except: every failure mode here (file absent,
    truncated by a killed run, hand-edited, a stale schema from some future
    version of this script) means the same thing to the caller — no hint
    available, fall back to registry order — and none of them should turn
    a scheduling nicety into a suite failure. See the SCHEDULING section of
    this module's docstring for why this lives in the OS temp dir rather
    than the repo.
    """
    try:
        with open(TIMING_CACHE_PATH, encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            return {str(k): float(v) for k, v in data.items()}
    except Exception:
        pass
    return {}


def _save_timing_cache(measured):
    """Merge `measured` ({label: seconds}) into the cache, written atomically.

    Merge, not overwrite: a filtered run (`run-local-gates.py gate-7`) only
    measured one label and must not blank out the other fifty-six the next
    parallel run would otherwise get a scheduling hint for. Atomic via
    temp-file-then-os.replace in the SAME directory (so the replace is a
    same-filesystem rename, not a cross-device copy) — a run killed mid-write
    must never leave a half-written JSON file for the next run to trip over,
    which is exactly the failure `_load_timing_cache` above is written to
    shrug off, but there is no reason to manufacture it when os.replace
    makes the write instantaneous from any reader's point of view.

    Best-effort: an OSError here (read-only temp dir, out of space) must not
    fail the gate suite over a file that only ever exists to make the next
    run schedule slightly better.
    """
    cache = _load_timing_cache()
    cache.update(measured)
    try:
        fd, tmp_path = tempfile.mkstemp(
            dir=os.path.dirname(TIMING_CACHE_PATH),
            prefix=".wing-commander-gate-timings-")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(cache, fh)
            os.replace(tmp_path, TIMING_CACHE_PATH)
        except OSError:
            os.remove(tmp_path)
            raise
    except OSError:
        pass


def command_for(script, bash, args=()):
    """How to invoke one gate, with the arguments CI gives it.

    .py goes to THIS interpreter rather than to `python3`: on Windows the
    latter is usually the Microsoft Store stub, which exits 49 without
    running anything, and the resulting "gate failed" is about PATH rather
    than about the code.
    """
    if script.endswith(".py"):
        return [sys.executable, script] + list(args)
    if script in _INLINE_SCRIPTS:
        # CI runs a step with no shell: as `bash -e {0}` (errexit, no
        # pipefail -- wc_shell_harness.UNSPECIFIED_SHELL_HOSTED is that
        # mapping's one home), so a failing command before the last fails
        # the step there; plain `bash file` would pass it here.
        # pr_time_inline_steps leaves a step that sets any shell:
        # unrunnable, so lint-workflows.yml (no defaults.run.shell, no
        # container) always lands on that default.
        return ([bash if a == "bash" else script if a == "{0}" else a
                 for a in UNSPECIFIED_SHELL_HOSTED] + list(args))
    return [bash, script] + list(args)


# Paths _write_inline_gates wrote, so command_for gives them CI's -e.
_INLINE_SCRIPTS = set()


def _inline_gate_files(bash):
    """Write every runnable inline gate's run: block to a temp .sh and
    return [(path, [])] in the same shape as pr_time_invocations, so the
    rest of this runner treats them as ordinary bash gates. Also puts a
    `python3` shim for this interpreter, and the resolved bash's own
    directory, at the front of PATH for every child - see INLINE GATES in
    the module docstring."""
    runnable, _ = pr_time_inline_steps()
    if not runnable:
        return []
    root = tempfile.mkdtemp(prefix="wc-inline-gates-")
    shim = os.path.join(root, "python3")
    exe = sys.executable.replace("\\", "/")
    with open(shim, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(f'#!/bin/sh\nexec "{exe}" "$@"\n')
    os.chmod(shim, 0o755)
    os.environ["PATH"] = os.pathsep.join(
        [root, os.path.dirname(bash), os.environ.get("PATH", "")])
    # Inline gates open files with the platform default encoding; the
    # workflows they read are UTF-8 (em-dashes in comments), and the
    # Python 3.14 default on Windows is still cp1252.
    os.environ.setdefault("PYTHONUTF8", "1")
    return [(path, []) for path in _write_inline_gates(runnable, root)]


def _write_inline_gates(runnable, root):
    """Write each (step name, run text) to its own `inline-<slug>.sh`
    under `root` and return the paths, in order. Split out of
    _inline_gate_files so verify-gate-wiring.py's self-test can drive it
    without touching this process's PATH."""
    out = []
    seen = set()
    for name, run in runnable:
        head = re.match(r"Gate \d+", name)
        slug = (head.group(0).lower().replace(" ", "-") if head
                else re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40])
        # Two steps sharing a slug would write one file and run it twice,
        # so the second step never ran locally: suffix the later ones.
        base, n = slug, 1
        while slug in seen:
            n += 1
            slug = f"{base}-{n}"
        seen.add(slug)
        path = os.path.join(root, f"inline-{slug}.sh")
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(run if run.endswith("\n") else run + "\n")
        _INLINE_SCRIPTS.add(path)
        out.append(path)
    return out


def _parse_jobs_flag(argv):
    """Pull `--jobs N` / `--jobs=N` out of argv; everything else is a filter.

    Not argparse: this script has never had a flag before, every other
    token is a free-text filter substring (see gate_label matching below),
    and argparse's positional/optional mixing would have to special-case
    that anyway. A tiny hand-rolled scan keeps `--jobs 4 sentinel gate-7`
    and `sentinel --jobs=4 gate-7` both working, which is the level of
    tolerance the existing filter argument already gets.
    """
    jobs = None
    filters = []
    i = 0
    while i < len(argv):
        tok = argv[i]
        if tok == "--jobs":
            if i + 1 >= len(argv):
                sys.exit("--jobs requires a value, e.g. --jobs 4")
            jobs = argv[i + 1]
            i += 2
            continue
        if tok.startswith("--jobs="):
            jobs = tok[len("--jobs="):]
            i += 1
            continue
        filters.append(tok)
        i += 1
    if jobs is None:
        jobs = os.cpu_count() or 4
    else:
        try:
            jobs = int(jobs)
        except ValueError:
            sys.exit(f"--jobs expects an integer, got {jobs!r}")
        if jobs < 1:
            sys.exit("--jobs must be >= 1")
    return jobs, filters


# --- --changed ------------------------------------------------------------
# See CHANGED-FILE SELECTION in the module docstring for the rules; every
# name below is one of them.

# A change to any of these changes WHICH gates exist or HOW they run, so it
# runs the whole suite: this runner, the registry that derives the gate
# list, the harness module it resolves bash and jq through, and the
# workflow the registry reads the gate calls (and the inline gates) from.
SUITE_INPUTS = (
    ".github/scripts/run-local-gates.py",
    ".github/scripts/wc_gate_registry.py",
    ".github/scripts/wc_shell_harness.py",
    ".github/scripts/wc_repo_files.py",
    ".github/workflows/lint-workflows.yml",
)
# A gate whose text carries one of these reads files no path in it names
# (a listing of every tracked file, a recursive walk of a root, a glob
# rooted at `**`), so it is picked by every change.
_READS_ANY = re.compile(
    r"""\bls-files(?:[ \t]+-[\w-]+(?:=\S+)?)*[ \t]*(?:$|[|;&)>`"'])"""
    r"""|\.rglob\(|glob\(\s*["']\*\*"""
    r"""|os\.walk\(\s*(?:ROOT|root|REPO\w*|repo_root|["']\.["'])\s*[,)]""",
    re.M)
_QUOTED = re.compile(r""""([^"\\\n]*)"|'([^'\\\n]*)'""")
# Two or more string literals in a row, separated by `,` (os.path.join
# arguments) or `/` (pathlib): read as one path.
_LITERAL_RUN = re.compile(
    r"""(?:"[^"\\\n]*"|'[^'\\\n]*')"""
    r"""(?:\s*[,/]\s*(?:"[^"\\\n]*"|'[^'\\\n]*'))+""")
_PATH_TOKEN = re.compile(r"[\w.\-/*?{}$%<>\[\]]*/[\w.\-/*?{}$%<>\[\]]*")
_FILE_NAME = re.compile(
    r"[\w.\-]*\w\.(?:py|sh|bash|jq|ya?ml|json|md|txt|toml|bats|cfg|ini)\b")
_IMPORT = re.compile(r"^\s*(?:from|import)\s+(\w+)", re.M)
_ROOT_NAME = re.compile(r"(?:ROOT|root|REPO\w*|repo\w*)$")
_WILD = re.compile(r"[*?{}$%<>\[\]]")
# Files a gate's own text pulls in, read for THEIR references too: code
# under these trees, never a workflow or a document (which name far more
# than the gate that reads them reads).
_FOLLOW_ROOTS = (".github/scripts/", ".github/actions/")
_FOLLOW_EXT = re.compile(r"(?:\.(?:py|sh|bash|jq)|/action\.ya?ml)$")
# A module-level name bound to the file's own directory: what it stands
# for is known, so `glob(os.path.join(HERE, "**", "*.py"))` reads that
# directory rather than nothing.
_HERE_VALUES = frozenset(f"{wrap}(__file__){tail}" for wrap, tail in (
    ("os.path.dirname(os.path.abspath", ")"),
    ("os.path.dirname(os.path.realpath", ")"),
    ("os.path.dirname", ""),
    ("Path", ".resolve().parent"),
    ("Path", ".parent"),
    ("pathlib.Path", ".resolve().parent"),
    ("pathlib.Path", ".parent")))
_LISTS_DIR = ("glob", "iglob", "listdir", "scandir", "walk", "iterdir")


def _path_ref(raw):
    """One reference as a '/'-joined path: leading variable components
    (`$ROOT`, `{root}`, `..`) dropped, then cut at the first component
    that is still a pattern, so `f"{root}/.github/workflows/{n}.yml"`
    and `$REPO/.github/workflows/*.yml` both read `.github/workflows`."""
    parts = [p for p in raw.replace("\\", "/").split("/")
             if p not in ("", ".", "..")]
    while parts and _WILD.search(parts[0]):
        parts.pop(0)
    out = []
    for part in parts:
        if _WILD.search(part):
            break
        out.append(part)
    return "/".join(out)


def _dotted(node):
    """`os.path.join` for the node of that expression, else ''."""
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return ""


def _str_of(node):
    """A string literal or f-string as text (`{}` for each field), else
    None."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(v.value if isinstance(v, ast.Constant) else "{}"
                       for v in node.values)
    return None


def _joined(parts):
    """One path reference from a join's arguments, or ''."""
    if not any(p is not None for p in parts):
        return ""
    comps = "/".join("{}" if p is None else p for p in parts).split("/")
    known = next((i for i, c in enumerate(comps) if _WILD.search(c)),
                 len(comps))
    if known:
        # The known head (a _here_names directory, literals) steps up on
        # `..`: join(HERE, "..", "workflows") is .github/workflows, and
        # join(HERE, "..", "..") is the root, which reads as nothing.
        head = posixpath.normpath("/".join(comps[:known]))
        comps = ([] if head == "." else [head]) + comps[known:]
    return _path_ref("/".join(comps))


class _Part:
    """What one top-level statement of a Python file reads (paths, file
    names, reads-any match) and what it uses (identifiers, `alias.attr`
    pairs, imports as (module, local name, imported name or None))."""

    def __init__(self):
        self.paths, self.names, self.any = set(), set(), None
        self.idents, self.attrs, self.imports = set(), set(), []


def _here_names(tree, rel):
    """{name: rel's directory} for each module-level `NAME = <the file's
    own directory>` (_HERE_VALUES)."""
    out = {}
    for top in tree.body:
        if (isinstance(top, ast.Assign) and len(top.targets) == 1
                and isinstance(top.targets[0], ast.Name)
                and ast.unparse(top.value) in _HERE_VALUES):
            out[top.targets[0].id] = rel.rsplit("/", 1)[0] if "/" in rel else "."
    return out


def _scan_py_node(top, here=None):
    """A _Part for one top-level statement, read off its syntax tree:
    string literals in CODE only (a docstring or other bare string
    statement names paths the script never opens), sys.path entries
    skipped (an import directory is not a read), os.path.join/Path/`/`
    chains joined into one path. `here` is _here_names(): each of those
    names, in a join or a directory listing, stands for its directory."""
    here = here or {}

    def arg(node):
        if isinstance(node, ast.Name) and node.id in here:
            return here[node.id]
        return _str_of(node)

    part = _Part()
    skip, strings = set(), []
    extended = {id(n.left) for n in ast.walk(top)
                if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Add)}
    for node in ast.walk(top):
        if isinstance(node, ast.Expr) and _str_of(node.value) is not None:
            skip.add(id(node.value))
        elif isinstance(node, (ast.List, ast.Tuple)) and id(node) not in extended:
            # `git ls-files` with flags only, nothing appended after it:
            # a listing of every file. A pathspec after it reads those.
            elts = [_str_of(e) for e in node.elts]
            if "ls-files" in elts:
                tail = elts[elts.index("ls-files") + 1:]
                if all(e is not None and e.startswith("-") for e in tail):
                    part.any = part.any or "git ls-files"
        elif isinstance(node, ast.Name):
            part.idents.add(node.id)
        elif isinstance(node, ast.Attribute):
            if isinstance(node.value, ast.Name):
                part.attrs.add((node.value.id, node.attr))
        elif isinstance(node, ast.Import):
            part.imports.extend((a.name.split(".")[0],
                                 (a.asname or a.name).split(".")[0], None)
                                for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            part.imports.extend((node.module.split(".")[0],
                                 a.asname or a.name, a.name)
                                for a in node.names)
        elif isinstance(node, ast.Call):
            name = _dotted(node.func)
            first = node.args[0] if node.args else None
            if name.startswith("sys.path."):
                skip.update(id(n) for a in node.args for n in ast.walk(a))
            elif name in ("os.walk", "walk") and first is not None and (
                    (isinstance(first, ast.Name) and _ROOT_NAME.match(first.id))
                    or _str_of(first) == "."):
                part.any = part.any or f"{name}({ast.unparse(first)})"
            elif name.endswith("rglob"):
                part.any = part.any or f"{name}(...)"
            elif name.endswith("glob") and (_str_of(first) or "").startswith("**"):
                part.any = part.any or f"{name}({_str_of(first)!r})"
            func = node.func
            if (isinstance(func, ast.Attribute)
                    and func.attr in _LISTS_DIR + ("rglob",)
                    and isinstance(func.value, ast.Name)
                    and func.value.id in here):
                part.paths.add(here[func.value.id])  # HERE.glob("*.py")
            elif (name.rsplit(".", 1)[-1] in _LISTS_DIR
                    and isinstance(first, ast.Name) and first.id in here):
                part.paths.add(here[first.id])       # os.listdir(HERE)
            if ((name.endswith(".join") and not isinstance(
                    getattr(node.func, "value", None), ast.Constant))
                    or name in ("Path", "pathlib.Path", "PurePosixPath")):
                ref = _joined([arg(a) for a in node.args]) \
                    if len(node.args) > 1 else ""
                if ref:
                    part.paths.add(ref)
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            chain, cur = [], node
            while isinstance(cur, ast.BinOp) and isinstance(cur.op, ast.Div):
                chain.append(cur.right)
                cur = cur.left
            chain.append(cur)
            ref = _joined([arg(a) for a in reversed(chain)])
            if ref:
                part.paths.add(ref)
    for node in ast.walk(top):
        if id(node) in skip or not isinstance(node, (ast.Constant,
                                                      ast.JoinedStr)):
            continue
        if isinstance(node, ast.JoinedStr):
            skip.update(id(v) for v in node.values)
        value = _str_of(node)
        if value is not None:
            strings.append(value)
            hit = _READS_ANY.search(value) if "ls-files " in value else None
            if hit:
                part.any = part.any or hit.group(0).strip()
    code = "\n".join(strings)
    part.paths.update(r for r in map(_path_ref, _PATH_TOKEN.findall(code)) if r)
    part.names.update(_FILE_NAME.findall(code))
    return part


def _scan_text(text):
    """A _Part for a file read as text (shell, YAML, a Python file that
    does not parse), `#` comment lines dropped."""
    part = _Part()
    text = "\n".join(l for l in text.splitlines()
                     if not l.lstrip().startswith("#"))
    for m in _LITERAL_RUN.finditer(text):
        ref = _path_ref("/".join(a or b for a, b in _QUOTED.findall(m.group(0))))
        if ref:
            part.paths.add(ref)
    part.paths.update(r for r in map(_path_ref, _PATH_TOKEN.findall(text)) if r)
    part.names.update(_FILE_NAME.findall(text))
    part.imports.extend((mod, mod, None) for mod in _IMPORT.findall(text))
    hit = _READS_ANY.search(text)
    part.any = hit.group(0) if hit else None
    return part


def _top_keys(top):
    """The names a top-level statement defines -- a def, a class, or an
    assignment to plain names (`SCRIPTS_DIR = ".github/scripts"`) -- or
    [""] for any other statement, which runs on import."""
    if isinstance(top, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return [top.name]
    targets = (top.targets if isinstance(top, ast.Assign)
               else [top.target] if isinstance(top, ast.AnnAssign) else [])
    names = []
    for t in targets:
        for n in (t.elts if isinstance(t, ast.Tuple) else [t]):
            if not isinstance(n, ast.Name):
                return [""]
            names.append(n.id)
    return names or [""]


def _scan_file_parts(rel, text):
    """{key: _Part}: for Python, one per name a top-level statement
    defines (_top_keys) plus "" for the statements that run on import;
    anything else is one "" part."""
    if rel.endswith(".py"):
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                tree = ast.parse(text)
        except (SyntaxError, ValueError):
            tree = None
        if tree is not None:
            parts = {"": _Part()}
            here = _here_names(tree, rel)
            for top in tree.body:
                got = _scan_py_node(top, here)
                for key in _top_keys(top):
                    if key in parts:
                        base = parts[key]
                        base.paths |= got.paths
                        base.names |= got.names
                        base.any = base.any or got.any
                        base.idents |= got.idents
                        base.attrs |= got.attrs
                        base.imports += got.imports
                    else:
                        parts[key] = got
            return parts
    return {"": _scan_text(text)}


def _refs_for(path):
    """Every reference that covers a changed `path`: each whole component
    (`"workflows"`, from a join on a variable), and each string that
    starts at a component and runs at least into the next one -- so a
    reference may stop part-way through its last component
    (`".github/workflows/wing-commander-" + n`)."""
    parts = path.split("/")
    out = set(parts)
    for i in range(len(parts) - 1):
        tail = "/".join(parts[i:])
        first = len(parts[i]) + 1
        out.update(tail[:j] for j in range(first + 1, len(tail) + 1))
    return out


class GateInputs:
    """What one gate reads, as far as its text (and the code it pulls in)
    says: its own files, the path references, the file names, and whether
    it reads the whole tree."""

    def __init__(self, label):
        self.label = label
        self.own = set()       # files, or directories ending in "/"
        self.paths = set()
        self.names = set()
        self.reads_any = None  # (file, match) when it reads every file
        self.where = {}        # path reference or file name -> file it is in
        self.pulled = set()    # files read for references: imported, run

    def why(self, path, refs=None):
        """The rule that picks this gate for `path`, or None. `refs` is
        _refs_for(path), passed in when the caller asks many gates."""
        for own in sorted(self.own):
            if path == own or (own.endswith("/") and path.startswith(own)):
                return "its own file"
        if path in self.pulled:
            return "its code pulls this file in"
        hits = self.paths & (_refs_for(path) if refs is None else refs)
        if hits:
            ref = max(hits, key=len)
            return f"reads {ref!r} ({self.where.get(ref, '?')})"
        name = path.rsplit("/", 1)[-1]
        if name in self.names:
            return f"names {name!r} ({self.where.get(name, '?')})"
        return None


def gate_inputs(root, gates, texts=None):
    """{label: GateInputs} for every (script, args) in `gates`.

    `texts` maps a label to text standing in for the script's file (the
    inline gates, whose run: block is the text). A gate's own file is its
    script; a `<dir>/run-tests.sh` harness owns its whole directory. Every
    own file is read whole. So is each file under _FOLLOW_ROOTS that a
    read part names by path, or by a file name only one file carries. A
    Python module a read part imports is read only as far as it is used:
    its top-level statements, the defs the importer names
    (`from m import f`, `m.f`), and the defs those use in turn -- most
    gates import wc_shell_harness for resolve_bash, not for the
    workflow sweep beside it.
    """
    texts = texts or {}
    files = repo_files(root)
    by_name = {}
    for f in files:
        by_name.setdefault(f.rsplit("/", 1)[-1], []).append(f)
    cache = {}

    def parts_of(rel):
        if rel not in cache:
            try:
                with open(os.path.join(root, rel), encoding="utf-8",
                          errors="replace") as fh:
                    text = fh.read()
            except OSError:
                text = ""
            cache[rel] = _scan_file_parts(rel, text)
        return cache[rel]

    def followable(f):
        # Never this runner: a gate that loads it does so for one helper,
        # and a change to it runs every gate anyway (SUITE_INPUTS).
        return (f != SUITE_INPUTS[0]
                and f.startswith(_FOLLOW_ROOTS) and _FOLLOW_EXT.search(f)
                and os.path.isfile(os.path.join(root, f)))

    def visit(inputs, src, parts, want, queue):
        """Fold the parts of one file `want` reaches into `inputs`, and
        queue what they pull in as (file, wanted names or None)."""
        keys = set(parts) if want is None else {""} | (want & set(parts))
        todo = list(keys)
        while todo:
            for ident in parts[todo.pop()].idents:
                if ident in parts and ident not in keys:
                    keys.add(ident)
                    todo.append(ident)
        idents, attrs = set(), set()
        for key in keys:
            part = parts[key]
            for ref in (part.paths | part.names) - inputs.paths - inputs.names:
                inputs.where[ref] = src
            inputs.paths |= part.paths
            inputs.names |= part.names
            if part.any and inputs.reads_any is None:
                inputs.reads_any = (src, part.any)
            idents |= part.idents
            attrs |= part.attrs
            for n in part.names:
                if len(by_name.get(n, ())) == 1:
                    queue.append((by_name[n][0], None))
            for ref in part.paths:
                if "/" in ref:
                    queue.extend((f, None) for f in
                                 by_name.get(ref.rsplit("/", 1)[-1], ())
                                 if ("/" + f).endswith("/" + ref))
        for key in keys:
            for mod, local, name in parts[key].imports:
                target = f".github/scripts/{mod}.py"
                if name == "*" or not src.endswith(".py"):
                    queue.append((target, None))
                elif name is not None:
                    if local in idents:
                        queue.append((target, {name}))
                else:
                    used = {a for v, a in attrs if v == local}
                    if used:
                        queue.append((target, used))
                    elif local in idents:
                        queue.append((target, None))

    out = {}
    for script, args in gates:
        label = gate_label(script, args)
        inputs = out.setdefault(label, GateInputs(label))
        queue = []
        if label in texts:
            visit(inputs, "(inline step)", _scan_file_parts("", texts[label]),
                  None, queue)
        elif script.endswith("/run-tests.sh"):
            own_dir = script.rsplit("/", 1)[0] + "/"
            inputs.own.add(own_dir)
            queue.extend((f, None) for f in files if f.startswith(own_dir))
        else:
            inputs.own.add(script)
            queue.append((script, None))
        done = {}
        while queue:
            rel, want = queue.pop()
            if not (rel in inputs.own or any(
                    rel.startswith(o) for o in inputs.own if o.endswith("/"))
                    or followable(rel)):
                continue
            had = done.get(rel, set())
            if had is None or (want is not None and want <= had):
                continue
            done[rel] = None if want is None else had | want
            inputs.pulled.add(rel)
            visit(inputs, rel, parts_of(rel),
                  None if want is None else want | had, queue)
    return out


def select_changed(changed, inputs):
    """-> (labels to run, {label: [reason]}, whole-suite reason or None).

    `changed` is the list of repo-relative paths; `inputs` is
    gate_inputs()'s map, in run order. Fails closed: a SUITE_INPUTS file,
    or a file no gate's own files, references or names cover, returns
    every label with the reason.
    """
    labels = list(inputs)
    if not changed:
        return [], {}, None
    for path in changed:
        if path in SUITE_INPUTS:
            return labels, {}, f"{path} defines the gate suite"
    reasons = {}
    for path in changed:
        covered = False
        refs = _refs_for(path)
        for label in labels:
            why = inputs[label].why(path, refs)
            if why:
                covered = True
                reasons.setdefault(label, []).append(f"{path}: {why}")
        if not covered:
            return labels, {}, (f"{path} is read by no gate this runner "
                                f"can map, so nothing rules a gate out")
    for label in labels:
        if inputs[label].reads_any and label not in reasons:
            src, match = inputs[label].reads_any
            reasons[label] = [f"reads every file ({match!r} in {src})"]
    return [l for l in labels if l in reasons], reasons, None


def _git_out(root, *args):
    proc = subprocess.run(["git", "-C", root, *args], env=git_env(),
                          capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: "
                           f"{(proc.stderr or '').strip() or proc.returncode}")
    return proc.stdout


def default_base(root="."):
    """The merge-base of HEAD with origin/main."""
    return _git_out(root, "merge-base", "HEAD", "origin/main").strip()


def changed_files(root, base):
    """Every path that differs from `base` in the working tree: committed,
    staged or not, deleted (under both names for a rename), and untracked
    files git does not ignore."""
    out = set(_git_out(root, "diff", "--name-only", "--no-renames", "-z",
                       base, "--").split("\0"))
    out |= set(_git_out(root, "ls-files", "--others", "--exclude-standard",
                        "-z").split("\0"))
    return sorted(p for p in out if p)


def _parse_changed_flag(argv, root="."):
    """Pull `--changed`, `--changed=BASE` or `--changed BASE` out of argv.

    -> (base or None when the flag is absent, the rest). A token after a
    bare `--changed` is BASE only when git resolves it to a commit;
    otherwise it stays a filter, so `--changed gate-7` means "changed
    gates matching gate-7" against the default base.
    """
    base = None
    rest = []
    i = 0
    while i < len(argv):
        tok = argv[i]
        if tok == "--changed" or tok.startswith("--changed="):
            base = tok[len("--changed="):] if "=" in tok else ""
            if (not base and i + 1 < len(argv)
                    and not argv[i + 1].startswith("-")):
                probe = subprocess.run(
                    ["git", "-C", root, "rev-parse", "--verify", "--quiet",
                     argv[i + 1] + "^{commit}"],
                    env=git_env(), capture_output=True)
                if probe.returncode == 0:
                    base = argv[i + 1]
                    i += 1
            i += 1
            continue
        rest.append(tok)
        i += 1
    return base, rest


def _apply_changed(base, gates, texts):
    """Narrow `gates` to the ones a change since `base` reaches, printing
    the base, the changed files, and each pick with its reason."""
    try:
        base = base or default_base()
        changed = changed_files(".", base)
    except RuntimeError as exc:
        sys.exit(f"--changed: {exc}. Pass a base commit: --changed BASE")
    print(f"--changed: {len(changed)} file(s) differ from {base}")
    for path in changed:
        print(f"  {path}")
    if not changed:
        print("--changed: no file changed, so no gate runs.")
        return []
    inputs = gate_inputs(".", gates, texts)
    picked, reasons, whole = select_changed(changed, inputs)
    if whole:
        print(f"--changed: running every gate: {whole}.\n")
        return gates
    print(f"--changed: {len(picked)} of {len(inputs)} gate(s) picked:")
    for label in picked:
        print(f"  {label}")
        for why in reasons[label]:
            print(f"      {why}")
    print()
    keep = set(picked)
    return [(sc, ar) for sc, ar in gates if gate_label(sc, ar) in keep]


def _run_one(script, args, bash, label):
    """Invoke one gate and collect its result. Runs on a pool thread.

    Each call is its own OS process (subprocess.run), so nothing here
    touches state another thread's call could also be touching — see the
    PARALLELISM section of this module's docstring for the audit that
    established that.
    """
    start = time.time()
    proc = subprocess.run(command_for(script, bash, args),
                          capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    elapsed = time.time() - start
    out = (proc.stdout or "") + (proc.stderr or "")
    return label, proc.returncode, elapsed, out


def main(argv):
    use_utf8_stdout()
    if not os.path.isdir(".github/workflows"):
        sys.exit("run this from the repository root.")
    ensure_jq()
    bash = resolve_bash()

    all_gates = pr_time_invocations() + _inline_gate_files(bash)

    changed_base, argv = _parse_changed_flag(argv)
    jobs, argv = _parse_jobs_flag(argv)

    gates = all_gates
    if changed_base is not None:
        texts = {}
        for script, args in all_gates:
            if script in _INLINE_SCRIPTS:
                with open(script, encoding="utf-8") as fh:
                    texts[gate_label(script, args)] = fh.read()
        gates = _apply_changed(changed_base, gates, texts)
        if not gates:
            return 0
    if argv:
        gates = [(sc, ar) for sc, ar in gates
                 if any(t in gate_label(sc, ar) or t in sc for t in argv)]
    if not gates and changed_base is not None:
        print(f"--changed: no picked gate matched {argv!r}; nothing to run.")
        return 0
    if not gates:
        sys.exit(f"no gates matched {argv!r}. Available:\n  "
                 + "\n  ".join(gate_label(sc, ar)
                                  for sc, ar in all_gates))

    results = []
    wall_start = time.time()

    if jobs == 1:
        # The original sequential loop, untouched, so `--jobs 1` is not a
        # 1-worker pool that HAPPENS to behave the same — it is the exact
        # code path this script ran before parallelism existed. Anything
        # that ever depended on that (a maintainer's muscle memory, a spec
        # quickstart quoting this output) keeps working unconditionally.
        print(f"Running {len(gates)} gate(s) with {sys.executable}\n"
              f"                and bash {bash}\n")
        for script, args in gates:
            label = gate_label(script, args)
            print(f"--- {label} " + "-" * max(0, 60 - len(label)))
            start = time.time()
            proc = subprocess.run(command_for(script, bash, args),
                                  capture_output=True, text=True,
                                  encoding="utf-8", errors="replace")
            elapsed = time.time() - start
            out = (proc.stdout or "") + (proc.stderr or "")
            # Full output only for failures: a passing sweep should be
            # readable at a glance, and every one of these gates prints its
            # own verdict line, which is the part worth seeing when it
            # passed.
            if proc.returncode == 0:
                tail = [l for l in out.strip().splitlines() if l.strip()][-1:]
                print("\n".join(tail) or "(no output)")
            else:
                print(out.strip() or "(no output)")
            results.append((label, proc.returncode, elapsed))
            print()
    else:
        print(f"Running {len(gates)} gate(s) with {sys.executable}\n"
              f"                and bash {bash}\n"
              f"                across {jobs} worker(s) in parallel — lines "
              f"below print in COMPLETION order.\n")
        # Longest-known-first submission: a bounded pool finishes soonest
        # when the biggest items go in first, so the tail isn't one worker
        # alone on a 300s gate the other N-1 workers could have been
        # helping shorten from the start. `timing_cache.get(label, inf)`
        # makes an unmeasured gate sort as heaviest — see SCHEDULING in
        # this module's docstring for why that default, and why the cache
        # lives outside the repo.
        timing_cache = _load_timing_cache()
        gates = sorted(
            gates,
            key=lambda sa: -timing_cache.get(gate_label(*sa), float("inf")))
        with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as pool:
            futures = [pool.submit(_run_one, script, args, bash,
                                   gate_label(script, args))
                       for script, args in gates]
            for fut in concurrent.futures.as_completed(futures):
                label, rc, elapsed, out = fut.result()
                status = "PASS" if rc == 0 else "FAIL"
                print(f"{status}  {elapsed:6.1f}s  {label}")
                if rc != 0:
                    # Delimited and printed right away rather than held for
                    # the final table: in a live run a maintainer is
                    # watching this stream, and the failure's own output is
                    # the part worth seeing the moment it is known, same as
                    # the serial path already does.
                    print(f"----- {label} output " + "-" * 40)
                    print(out.strip() or "(no output)")
                    print("-" * 70)
                results.append((label, rc, elapsed))

    wall_elapsed = time.time() - wall_start

    # Record what this run measured for next time, regardless of --jobs.
    # This is silent by design (--jobs 1's contract above is byte-identical
    # output to the pre-cache script) and best-effort (see
    # _save_timing_cache) — a maintainer offline or on a read-only temp dir
    # still gets a correct, merely unscheduled, run.
    _save_timing_cache({label: elapsed for label, _, elapsed in results})

    width = max(len(r[0]) for r in results)
    print("=" * (width + 22))
    for label, rc, elapsed in results:
        print(f"{label:<{width}}  {'PASS' if rc == 0 else 'FAIL'}  {elapsed:6.1f}s")
    failed = [r for r in results if r[1] != 0]
    print("=" * (width + 22))
    if jobs == 1:
        print(f"{len(results) - len(failed)}/{len(results)} passed, "
              f"{sum(r[2] for r in results):.1f}s total")
    else:
        # Wall-clock is what a maintainer waiting on this run experiences;
        # the summed per-gate time is also printed since it is what the
        # 1599s serial baseline is comparable to, and the gap between the
        # two numbers is the parallelism's whole point.
        print(f"{len(results) - len(failed)}/{len(results)} passed, "
              f"{wall_elapsed:.1f}s wall-clock total "
              f"({sum(r[2] for r in results):.1f}s summed across gates)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
