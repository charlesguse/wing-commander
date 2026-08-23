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
            anything that only walks .github/scripts. Both the pattern and
            the heredoc reader are themselves read by a second, dumber
            reader, because a discovery rule cannot fail on a subject it
            has been told not to look at.

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
# larger gates in lint-workflows.yml are written. The opener may carry
# script arguments before the delimiter (watchdog.yml's signal-id stamp
# passes `"$f"`) and a redirect after it (Gate 23's does), and the
# terminator is matched at any indentation so the YAML block's own nesting
# is irrelevant.
PY_HEREDOC_RE = re.compile(
    r"^[ \t]*python3? +- +[^\n<]*<<'(\w+)'[^\n]*\n(.*?)^[ \t]*\1[ \t]*$",
    re.S | re.M)

# The dumber reader of the same thing, and the one that decides whether a
# heredoc was MISSED: "a line invoking python that opens a heredoc". It
# knows nothing about how the opener is spelled, so any spelling
# PY_HEREDOC_RE cannot read (an interpreter flag before the `-`, an
# unquoted delimiter, `python -` instead of `python3 -`) shows up here and
# nowhere else, which is exactly the disagreement _check_heredoc_reader
# reports. Same one-precise-one-loose technique as LOOSE_PATH_RE.
LOOSE_PY_HEREDOC_RE = re.compile(r"^[ \t]*python3? +[^\n]*<<", re.M)

# The SECOND, deliberately dumber reader of the same sources. SUBJECT_PATH_RE
# defines the set the triggers rule is enforced over, and a check cannot fail
# on a subject it has been told not to look at: narrow that pattern and
# discovery quietly returns fewer documents, every one of them passes, and the
# gate prints a smaller number as though it were the whole story. Nothing
# inside the rule can notice, because the mutation attacks its eyesight rather
# than the property it enforces.
#
# So this asks a coarser question with no knowledge of the shapes above -- "is
# this an .md file on disk that a gate names?" -- and the two answers are
# compared. Same technique as _check_heredoc_reader and check_local_runner_parity:
# one precise reader, one loose one, and disagreement is the failure.
#
# Measured against the tree: this finds exactly the four subject documents and
# nothing else. Restricting it to .md is what keeps it quiet -- gates name
# fourteen other existing files (workflows, composites, required-tools.txt),
# all of them code, and all already covered by the tree-wide paths: entries.
LOOSE_PATH_RE = re.compile(r"^[A-Za-z0-9_.\-]+(?:/[A-Za-z0-9_.\-]+)+\.md$")

# Markdown a gate names WITHOUT it being that gate's subject -- a fixture it
# writes, say. Empty, and the emptiness is the point: unlike a manifest OF
# subjects (#149's objection, and rightly), this list fails CLOSED. Forget to
# add a genuine subject to a subject-manifest and the gate silently passes;
# forget to add a non-subject here and the gate fails loudly and tells you.
# An entry needs a comment saying why the document is not a subject.
NOT_SUBJECT_DOCUMENTS = frozenset()


def _string_constants(source):
    """Every string constant in a python source, stripped.

    Read out of the SOURCE with ast, not by grepping, for two reasons: a
    path assembled by implicit string concatenation across a line wrap (as
    verify-clarification-gating.py's SCHEMA_CONTRACT is) reaches us joined
    rather than as its first fragment, and comments -- which mention spec
    directories constantly in this repository -- are not in the tree at all.

    Both readers share this, so the only thing that can differ between them
    is the pattern each applies -- which is the whole point of having two.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []             # not this gate's job; the script's own run fails
    return [node.value.strip() for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)]


def _subject_paths_in_source(source):
    """Every subject-document path appearing as a string constant."""
    return [value for value in _string_constants(source)
            if SUBJECT_PATH_RE.match(value)]


def _check_heredoc_reader(scanned):
    """Fail loudly, PER HEREDOC, when discovery cannot read one of them.

    docs/setup.md happens to be discoverable from .github/scripts too -- as
    a FIXTURE KEY in verify-gate-12.py, not as the path the gate opens -- so
    if this reader silently stopped matching, every subject document would
    still be found and this check would still print 0 failures. That is the
    same "green while proving nothing" shape the whole file exists to stop.
    A style change to the heredocs (an interpreter flag, a different
    delimiter) must therefore be a loud failure here, not a quiet loss of
    coverage.

    Per heredoc, and not "did ANY of them parse", because the repository has
    a dozen of them and the whole-tree question is satisfied by any one:
    respell Gate 12's opener alone and eleven others still parse, so the
    guard returned [] and docs/setup.md quietly went back to being
    attributed to verify-gate-12.py's fixture key -- discovery by accident,
    the exact thing this reader exists to make impossible. Each opener the
    loose pattern sees and the precise one did not is named on its own line,
    with the opener quoted, so the fix is mechanical.
    """
    failures = []
    parsed_total = 0
    for path, source, matches in scanned:
        parsed_total += sum(1 for _, _, ok in matches if ok)
        for m in LOOSE_PY_HEREDOC_RE.finditer(source):
            at = m.start()
            enclosing = next(((s, e, ok) for s, e, ok in matches
                              if s <= at < e), None)
            if enclosing is not None and (enclosing[0] != at or enclosing[2]):
                # Either an opener-shaped line sitting INSIDE a heredoc body
                # that was read whole (data for another interpreter, not a
                # gate), or this very heredoc, read and parsed fine.
                continue
            eol = source.find("\n", at)
            opener = (source[at:] if eol < 0 else source[at:eol]).strip()
            failures.append(
                f"{path}:{source[:at].count(chr(10)) + 1} opens a python "
                f"heredoc that PY_HEREDOC_RE did not extract and parse, so "
                f"that gate is not being read for the documents it opens, "
                f"and a subject document only it names would go untriggered "
                f"with nothing reported. Other heredocs parsing is not a "
                f"defence: they are different gates reading different "
                f"documents. Update the pattern to match how this one is "
                f"now written ({opener}).")

    if failures:
        return failures

    if parsed_total == 0:
        return ["found no python heredoc in any workflow or composite action. "
                "Either they were all extracted into .github/scripts -- in "
                "which case delete this reader -- or its pattern has broken "
                "and heredoc gates are no longer being read at all."]
    return []


def gate_sources(scanned=None):
    """-> [(where, python source), ...] for everything that acts as a gate.

    The gate scripts under .github/scripts AND the python heredocs embedded
    in workflow and composite run: blocks, the latter as `<file>:<line>`.
    Skipping the second is how this check could have reported "0 failure(s)"
    over an untriggered docs/setup.md: Gate 12's live scan is a heredoc, and
    the only file-based trace of its subject is a fixture key in its
    self-test -- discovery by accident.

    Both readers below run over THIS list rather than gathering their own,
    so a disagreement between them can only mean the patterns disagree --
    never that one of them was looking at a different set of files.

    `scanned`, when given a list, collects (path, source, matches) per
    workflow, where `matches` is one (start, end, parsed_ok) per heredoc
    PY_HEREDOC_RE recognised. _check_heredoc_reader needs the SPANS, not a
    count: it has to tell a heredoc this pattern could not read from an
    opener-shaped line sitting inside one it read whole.
    """
    sources = []
    for path in sorted(glob.glob(os.path.join(SCRIPTS_DIR, "*.py"))):
        sources.append((os.path.basename(path),
                        open(path, encoding="utf-8").read()))

    for path in workflow_files() + sorted(glob.glob(COMPOSITE_ACTIONS_GLOB)):
        source = open(path, encoding="utf-8").read()
        matches = []
        for match in PY_HEREDOC_RE.finditer(source):
            # The body is indented by its YAML block; dedent before parsing
            # or every heredoc is an IndentationError and vanishes silently.
            body = textwrap.dedent(match.group(2))
            try:
                ast.parse(body)
            except SyntaxError:
                # Recognised but unreadable. Recorded as a match so the
                # reader check reports it by name rather than skipping it:
                # the opener says `python`, so a body that is not python is
                # a defect somewhere, not something to pass over quietly.
                matches.append((match.start(), match.end(), False))
                continue
            matches.append((match.start(), match.end(), True))
            line = source[:match.start()].count("\n") + 1
            sources.append((f"{os.path.basename(path)}:{line}", body))
        if scanned is not None:
            scanned.append((path, source, matches))

    return sources


def subject_paths_read_by_gates(scanned=None, sources=None):
    """-> {path: [reader, ...]} for every subject document a gate opens."""
    if sources is None:
        sources = gate_sources(scanned)
    found = {}
    for where, source in sources:
        for value in _subject_paths_in_source(source):
            found.setdefault(value, []).append(where)
    return {k: sorted(set(v)) for k, v in found.items()}


def _check_pattern_reader(sources, precise):
    """-> list of failure strings. The loose reader's dissent.

    See LOOSE_PATH_RE. Anything the dumb reader can see and the precise one
    cannot is either a subject SUBJECT_PATH_RE has been narrowed past, or a
    document that genuinely is not a subject and belongs in
    NOT_SUBJECT_DOCUMENTS with a reason.
    """
    failures = []
    loose = {}
    for where, source in sources:
        for value in _string_constants(source):
            if (LOOSE_PATH_RE.match(value)
                    and value not in NOT_SUBJECT_DOCUMENTS
                    and os.path.isfile(value)):
                loose.setdefault(value, []).append(where)

    # Who watches this reader. Blunting LOOSE_PATH_RE would silently restore
    # the blind spot it exists to cover, and nothing above would notice --
    # the dissent it never files reads exactly like agreement. The regress
    # stops here, on a tautology: a pattern claiming to match every .md path
    # must match the .md subjects the precise reader just found. It cannot
    # go quiet without contradicting its own description.
    should_be_loose = {p for p in precise
                       if p.endswith(".md") and os.path.isfile(p)
                       and p not in NOT_SUBJECT_DOCUMENTS}
    if should_be_loose - set(loose):
        missing = ", ".join(sorted(should_be_loose - set(loose)))
        failures.append(
            f"LOOSE_PATH_RE does not match {missing}, which the precise "
            f"reader found and which exist(s) on disk as markdown. The "
            f"second reader can no longer dissent, so narrowing "
            f"SUBJECT_PATH_RE would go unreported again. Restore the loose "
            f"pattern to match any .md path.")

    for path in sorted(set(loose) - set(precise)):
        failures.append(
            f"{path} is a document on disk named by "
            f"{', '.join(sorted(set(loose[path])))}, but SUBJECT_PATH_RE does "
            f"not classify it as a subject document, so the triggers rule "
            f"below never checks whether editing it runs its gate. Either "
            f"widen that pattern (and add the path to lint-workflows.yml's "
            f"paths: filter), or add it to NOT_SUBJECT_DOCUMENTS with a "
            f"comment saying why it is not a subject.")
    return failures


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
    sources = gate_sources(scanned)
    reading = subject_paths_read_by_gates(sources=sources)
    failures = _check_heredoc_reader(scanned)
    failures += _check_pattern_reader(sources, reading)
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
