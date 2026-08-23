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
import re
import shlex

import yaml

SCRIPTS_DIR = ".github/scripts"
WORKFLOWS_DIR = ".github/workflows"
SUBDIR_ENTRYPOINT = "run-tests.sh"
SHARED_PREFIX = "wc_"


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
