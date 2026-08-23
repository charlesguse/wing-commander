#!/usr/bin/env python3
"""Assert every check in .github/scripts is actually run, and vice versa.

WHY THIS EXISTS
---------------
verify-denied-tool-collector.sh was orphaned for weeks: no workflow invoked
it, and while nothing was running it, it drifted out of sync with the filter
it claimed to verify. It still printed "all assertions passed" whenever
someone ran it by hand, so it read as evidence while proving nothing about
the code that shipped. PR #158 wired that script up. It did nothing to stop
the next one from landing the same way, and by then this repository had four
verifiers and was adding more.

This closes it generally, in both directions:

  forward   every .github/scripts/verify-*.{py,sh} and every subdirectory
            harness entrypoint is invoked by at least one workflow. A check
            nobody runs is dead weight that looks like coverage.
  reverse   every .github/scripts/... path a workflow tries to run exists on
            disk. A gate step pointing at a moved or renamed file fails at
            the worst possible moment, and until it does, the gate's name in
            the job list implies a check that is not happening.
  modules   every wc_*.py shared module is imported by something. These are
            exempt from the wiring rule (nothing invokes them directly), so
            without this they are the one place an orphan could still hide.
  argv      every gate the PR-time suite runs is one the local runner can
            reproduce. The two answers come from different readers - one
            substring-matches the workflow text, one tokenizes it - and a
            gate only the first can see runs in CI and is silently absent
            from the local sweep.
  triggers  every published document a gate treats as its subject is named
            by lint-workflows.yml's pull_request paths: filter. A gate that
            is wired but never TRIGGERED by an edit to the one file it
            reads is wired in name only - the edit ships, the gate sits
            out the PR, and the desync waits for the nightly schedule.
            "Subject" is deliberately wider than specs/*/contracts/*: Gate
            12's is docs/setup.md, and scoping this rule to the contracts
            tree let the one document most likely to invalidate its gate go
            untriggered while this check reported no failures. Discovery
            reads workflow-embedded heredoc gates too, for the same reason
            #213 had to - a gate that lives in a run: block is invisible to
            anything that only walks .github/scripts.

The rule is a naming convention read off the directory, not a list of gate
names — see wc_gate_registry.py for why a list would recreate issue #149.

Usage: python3 .github/scripts/verify-gate-wiring.py
"""
import ast
import glob
import os
import re
import sys
import textwrap

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_gate_registry import (  # noqa: E402
    SCRIPTS_DIR, _self_check, invocations, pr_time_gates,
    pr_time_invocations, referenced_script_paths, shared_modules,
    workflow_files)


LINT_WORKFLOW = os.path.join(".github", "workflows", "lint-workflows.yml")

# Composite actions can host a heredoc gate exactly as a workflow can, so
# they are scanned alongside the workflows the registry already enumerates.
COMPOSITE_ACTIONS_GLOB = os.path.join(".github", "actions", "*", "action.yml")

# A published document a gate reads as its subject. Two shapes ship today:
# specs/<feature>/contracts/<file>, and a document under docs/ - Gate 12
# treats docs/setup.md as the single source of truth for what the App may
# do and sys.exits if its permissions list moves. Anchored and
# whitespace-free so a docstring that merely mentions a spec directory
# across a line wrap cannot masquerade as one.
SUBJECT_PATH_RE = re.compile(
    r"^(?:specs/[^\s*?\[\]]+/contracts/[^\s*?\[\]]+"
    r"|docs/[^\s*?\[\]]+\.md)$")

# `python3 - <<'PYEOF' ... PYEOF` inside a run: block, which is how the
# larger gates in lint-workflows.yml are written. The opener may carry a
# redirect after the delimiter (Gate 23's does), and the terminator is
# matched at any indentation so the YAML block's own nesting is irrelevant.
PY_HEREDOC_RE = re.compile(
    r"^[ \t]*python3? +- +<<'(\w+)'[^\n]*\n(.*?)^[ \t]*\1[ \t]*$",
    re.S | re.M)


def _subject_paths_in_source(source):
    """Every subject-document path appearing as a string constant.

    Read out of the SOURCE with ast, not by grepping, for two reasons: a
    path assembled by implicit string concatenation across a line wrap (as
    verify-clarification-gating.py's SCHEMA_CONTRACT is) reaches us joined
    rather than as its first fragment, and comments -- which mention spec
    directories constantly in this repository -- are not in the tree at all.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []             # not this gate's job; the script's own run fails
    return [node.value.strip() for node in ast.walk(tree)
            if isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and SUBJECT_PATH_RE.match(node.value.strip())]


def _check_heredoc_reader(scanned):
    """Fail loudly if the heredoc half of discovery stopped reading anything.

    docs/setup.md happens to be discoverable from .github/scripts too -- as
    a FIXTURE KEY in verify-gate-12.py, not as the path the gate opens -- so
    if this reader silently stopped matching, every subject document would
    still be found and this check would still print 0 failures. That is the
    same "green while proving nothing" shape the whole file exists to stop.
    A style change to the heredocs (a different delimiter, `python -c`)
    must therefore be a loud failure here, not a quiet loss of coverage.
    """
    if any(parsed for _, _, parsed in scanned):
        return []

    missed = [(path, source) for path, source, _ in scanned
              if re.search(r"\bpython3? +- +<<", source)]
    if missed:
        path, source = missed[0]
        opener = re.search(r"<<[^\n]*", source)
        return [f"{path} contains a python heredoc that PY_HEREDOC_RE did "
                f"not extract and parse, so no gate written as a run: block "
                f"is being read for the documents it opens, and a subject "
                f"document only such a gate names would go untriggered with "
                f"nothing reported. Update the pattern to match how the "
                f"heredocs are now written "
                f"({opener.group(0).strip() if opener else 'unknown opener'})."]

    return ["found no python heredoc in any workflow or composite action. "
            "Either they were all extracted into .github/scripts -- in "
            "which case delete this reader -- or its pattern has broken "
            "and heredoc gates are no longer being read at all."]


def subject_paths_read_by_gates(scanned=None):
    """-> {path: [reader, ...]} for every subject document a gate opens.

    Readers are the gate scripts under .github/scripts AND the python
    heredocs embedded in workflow and composite run: blocks, reported as
    `<file>:<line>`. Skipping the second is how this check could have
    reported "0 failure(s)" over an untriggered docs/setup.md: Gate 12's
    live scan is a heredoc, and the only file-based trace of its subject is
    a fixture key in its self-test -- discovery by accident.

    `scanned`, when given a list, collects (path, source, parsed) per
    workflow so _check_heredoc_reader can tell "no heredocs here" from
    "heredocs this pattern can no longer read".
    """
    found = {}
    for path in sorted(glob.glob(os.path.join(SCRIPTS_DIR, "*.py"))):
        source = open(path, encoding="utf-8").read()
        for value in _subject_paths_in_source(source):
            found.setdefault(value, []).append(os.path.basename(path))

    for path in workflow_files() + sorted(glob.glob(COMPOSITE_ACTIONS_GLOB)):
        source = open(path, encoding="utf-8").read()
        parsed = 0
        for match in PY_HEREDOC_RE.finditer(source):
            # The body is indented by its YAML block; dedent before parsing
            # or every heredoc is an IndentationError and vanishes silently.
            body = textwrap.dedent(match.group(2))
            try:
                ast.parse(body)
            except SyntaxError:
                continue      # a shell heredoc, or one the bash gate reports
            parsed += 1
            line = source[:match.start()].count("\n") + 1
            where = f"{os.path.basename(path)}:{line}"
            for value in _subject_paths_in_source(body):
                found.setdefault(value, []).append(where)
        if scanned is not None:
            scanned.append((path, source, parsed))

    return {k: sorted(set(v)) for k, v in found.items()}


def _pattern_matches(pattern, path):
    """GitHub path-filter glob semantics, narrowed to what we emit.

    `**` crosses directory separators, a single `*` does not, and everything
    else is literal. Written out rather than handed to fnmatch, whose `*`
    happily matches `/` and would call `specs/*/contracts/x.md` a match for
    a path three directories deep.
    """
    out, i = [], 0
    while i < len(pattern):
        if pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.fullmatch("".join(out), path) is not None


def pull_request_paths(workflow=LINT_WORKFLOW):
    """The pull_request paths: filter, or None if there is no filter."""
    doc = yaml.safe_load(open(workflow, encoding="utf-8")) or {}
    on = doc.get(True, doc.get("on"))
    if not isinstance(on, dict):
        return None
    pr = on.get("pull_request")
    if not isinstance(pr, dict):
        return None
    paths = pr.get("paths")
    return list(paths) if isinstance(paths, list) else None


def check_subject_triggers():
    """-> list of failure strings."""
    scanned = []
    reading = subject_paths_read_by_gates(scanned)
    failures = _check_heredoc_reader(scanned)
    if not reading:
        return failures + [
            "found no gate that reads a published subject document. "
            "Either they moved or this check's discovery has broken; "
            "either way it is about to verify nothing."]

    patterns = pull_request_paths()
    if patterns is None:
        # No filter at all means every PR runs the suite -- over-triggering,
        # never under-triggering. Nothing to enforce, and saying so beats a
        # confusing pass.
        print("ok    lint-workflows.yml has no pull_request paths: filter; "
              "every subject document triggers it by default")
        return failures

    for path, readers in sorted(reading.items()):
        if any(_pattern_matches(pattern, path) for pattern in patterns):
            print(f"ok    {path} triggers lint-workflows.yml "
                  f"<- read by {', '.join(readers)}")
        else:
            failures.append(
                f"{path} is read by {', '.join(readers)}, but no pattern in "
                f"lint-workflows.yml's pull_request paths: filter matches it. "
                f"A PR that edits only that document -- the change most likely "
                f"to break that gate -- will not run the gate, and the desync "
                f"waits for the nightly schedule. Add the path to the filter.")
    return failures


def check_local_runner_parity():
    """-> list of failure strings.

    `pr_time_gates` finds a gate by substring; `pr_time_invocations`
    tokenizes the same text to recover its argv, and run-local-gates.py
    runs only what the second returns. A gate the tokenizer cannot parse
    therefore vanishes from the local suite while still running in CI, and
    the sweep keeps reporting the smaller number as if it were the whole
    thing. Neither reader can notice that alone; comparing them can.
    """
    failures = []
    invoked = {script for script, _ in pr_time_invocations()}
    for script in pr_time_gates():
        if script not in invoked:
            failures.append(
                f"{script} runs in the PR-time lint suite, but the local "
                f"runner recovers no argv for it, so `run-local-gates.py` "
                f"skips it entirely. Its call site is written in a form the "
                f"registry's tokenizer cannot read - the local sweep is "
                f"quietly rehearsing less than CI runs.")
    if not failures:
        print(f"ok    all {len(pr_time_gates())} PR-time gate(s) are "
              f"reproducible locally ({len(pr_time_invocations())} invocation(s))")
    return failures


def main():
    failures = []
    _self_check()

    # --- forward: every check is invoked -----------------------------------
    wiring = invocations()
    if not wiring:
        print("::error::found no verify-* scripts at all. Either they moved "
              "or this gate's discovery has broken; either way it is about "
              "to check nothing.")
        return 1
    for script, workflows in wiring.items():
        if workflows:
            print(f"ok    {script} <- {', '.join(workflows)}")
        else:
            failures.append(
                f"{script} is not invoked by any workflow. A verifier nothing "
                f"runs is not a verifier: it will drift out of sync with the "
                f"code it checks and keep reporting success (this is exactly "
                f"what happened to verify-denied-tool-collector.sh). Wire it "
                f"into a gate, or delete it.")

    # --- reverse: every invoked path exists --------------------------------
    for path, workflows in referenced_script_paths().items():
        if not os.path.exists(path):
            failures.append(
                f"{path} is run by {', '.join(workflows)} but does not exist. "
                f"That step will fail the moment it is reached, and until "
                f"then its name in the job list implies a check that is not "
                f"happening.")

    # --- modules: every shared module has an importer ----------------------
    sources = {}
    for name in os.listdir(SCRIPTS_DIR):
        if name.endswith(".py"):
            sources[name] = open(os.path.join(SCRIPTS_DIR, name),
                                 encoding="utf-8").read()
    for module in shared_modules():
        stem = module[:-3]
        importers = sorted(
            n for n, src in sources.items()
            if n != module
            and re.search(rf"^\s*(from {stem} import|import {stem})\b",
                          src, re.M))
        if importers:
            print(f"ok    {module} <- imported by {', '.join(importers)}")
        else:
            failures.append(
                f"{SCRIPTS_DIR}/{module} is a shared module that nothing "
                f"imports. It is exempt from the invocation rule because "
                f"nothing runs it directly, which makes an unused one "
                f"invisible. Use it or delete it.")

    # --- argv: CI's gate set and the local runner's agree -----------------
    failures.extend(check_local_runner_parity())

    # --- triggers: every subject document a gate reads fires the suite ----
    failures.extend(check_subject_triggers())

    print()
    for f in failures:
        print(f"::error::{f}")
    # ASCII only in this line: it also runs on a maintainer's Windows shell,
    # where a cp1252 stdout cannot encode a dash and the gate would die in
    # the print instead of reporting its verdict.
    print(f"Gate wiring: {len(wiring)} check(s), "
          f"{len(shared_modules())} shared module(s), "
          f"{len(subject_paths_read_by_gates())} subject document(s); "
          f"{len(failures)} failure(s).")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
