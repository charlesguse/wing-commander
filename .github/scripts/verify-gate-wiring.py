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
            from the local sweep. The same holds for any script, not only a
            gate: every script a PR-time step names (through an
            interpreter, by direct exec, across a continuation) is one the
            local runner runs too (#825).
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
import argparse
import ast
import glob
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_gate_registry import (  # noqa: E402
    LOOSE_PY_HEREDOC_RE, SCRIPTS_DIR, _self_check, gate_label, invocations,
    pr_time_gates, pr_time_inline_steps, pr_time_invocations, pr_time_script_calls,
    referenced_actions_script_paths, referenced_script_paths, shared_modules,
    workflow_files)


LINT_WORKFLOW = os.path.join(".github", "workflows", "lint-workflows.yml")

# Composite actions can host a heredoc gate exactly as a workflow can, so
# they are scanned alongside the workflows the registry already enumerates.
COMPOSITE_ACTIONS_GLOB = os.path.join(".github", "actions", "*", "action.yml")

# A published document a gate reads as its subject. Three shapes ship
# today: specs/<feature>/contracts/<file>; a document under docs/ - Gate 12
# treats docs/setup.md as the single source of truth for what the App may
# do and sys.exits if its permissions list moves; and the constitution
# under .specify/memory/, which Gate 113 reads to decide whether the
# document names every class of merge the pipeline can perform. Anchored
# and whitespace-free so a docstring that merely mentions a spec directory
# across a line wrap cannot masquerade as one.
SUBJECT_PATH_RE = re.compile(
    r"^(?:specs/[^\s*?\[\]]+/contracts/[^\s*?\[\]]+"
    r"|docs/[^\s*?\[\]]+\.md"
    r"|\.specify/memory/[^\s*?\[\]]+\.md)$")

# Two more shapes a gate reads as its subject, which _folded_join first
# made visible (code reviews of #940): a feature's own top-level document
# (verify-maintainer-credential-canonical-statement.py compares
# specs/055-*/research.md and spec.md with docs/setup.md;
# verify-dedup-key-canonical-rule.py reads specs/056-*/data-model.md) and
# a skill (verify-skill-board-loop-concurrency-claim.py checks
# spec-cross-reference/SKILL.md's example). Subjects only when the file
# exists: self-tests name made-up ones as fixture keys
# (specs/999-example-feature/spec.md, .claude/skills/foo/SKILL.md), which
# no PR can edit into breaking a gate.
ON_DISK_SUBJECT_PATH_RE = re.compile(
    r"^(?:specs/[^\s*?\[\]/]+/[^\s*?\[\]/]+\.md"
    r"|\.claude/skills/[^\s*?\[\]/]+/SKILL\.md)$")

# `python3 - <<'PYEOF' ... PYEOF` inside a run: block, which is how the
# larger gates in lint-workflows.yml are written. The opener may carry
# script arguments before the delimiter (watchdog.yml's signal-id stamp
# passes `"$f"`) and a redirect after it (Gate 23's does), and the
# terminator is matched at any indentation so the YAML block's own nesting
# is irrelevant. Interpreter flags before the `-` are read too: board-
# loop.yml's post-agent heredocs run `python3 -I -` (#583).
PY_HEREDOC_RE = re.compile(
    r"^[ \t]*python3?(?: +-[A-Za-z]+)* +- +[^\n<]*<<'(\w+)'[^\n]*\n(.*?)^[ \t]*\1[ \t]*$",
    re.S | re.M)

# The dumber reader of the same thing, and the one that decides whether a
# heredoc was MISSED: "a line invoking python that opens a heredoc". It
# knows nothing about how the opener is spelled, so any spelling
# PY_HEREDOC_RE cannot read (an unquoted delimiter, say) shows up here
# and nowhere else, which is exactly the disagreement _check_heredoc_reader
# reports. Same one-precise-one-loose technique as LOOSE_PATH_RE. The
# pattern itself lives in wc_gate_registry (LOOSE_PY_HEREDOC_RE, imported
# above): pr_time_inline_steps decides local-suite membership with the
# same grammar, and one home means the two readers cannot drift apart.

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
# Measured against the tree: this finds every subject document and nothing
# else. Restricting it to .md is what keeps it quiet -- gates name many other
# existing files (workflows, composites, required-tools.txt), all of them
# code, and all already covered by the tree-wide paths: entries. No literal
# count here on purpose: the set grows with each gate that takes a document
# as its subject, and a number nothing maintains is a stale number waiting
# to happen.
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
    out = [node.value.strip() for node in ast.walk(tree)
           if isinstance(node, ast.Constant) and isinstance(node.value, str)]
    return out + [path for node in ast.walk(tree)
                  if (path := _folded_join(node)) is not None]


def _folded_join(node):
    """The repo-relative path an `os.path.join(...)` call spells, or None.

    A path split across join arguments
    (`os.path.join(REPO_ROOT, "specs", "060-...", "contracts", "x.md")`,
    Gate 101's) has no single string constant holding it, so neither
    reader saw it and the document's own edits never had to trigger its
    gate (code reviews of #940). Folded when every argument after a
    leading root -- any non-constant first arguments, such as `REPO_ROOT`
    or a fixture's temp dir -- is a string constant; a `"."` component is
    dropped. A call with a non-constant argument further in is not a
    constant path and is left alone."""
    if not (isinstance(node, ast.Call) and not node.keywords
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "join"
            and ast.unparse(node.func.value) in ("os.path", "posixpath",
                                                 "path")):
        return None
    args = list(node.args)
    while args and not (isinstance(args[0], ast.Constant)
                        and isinstance(args[0].value, str)):
        args.pop(0)
    if not args or not all(isinstance(a, ast.Constant)
                           and isinstance(a.value, str) for a in args):
        return None
    parts = [p for a in args for p in a.value.strip().split("/")
             if p not in ("", ".")]
    return "/".join(parts) if len(parts) > 1 else None


def _subject_paths_in_source(source):
    """Every subject-document path appearing as a string constant."""
    return [value for value in _string_constants(source)
            if SUBJECT_PATH_RE.match(value)
            or (ON_DISK_SUBJECT_PATH_RE.match(value)
                and os.path.isfile(value))]


def _check_heredoc_reader(scanned):
    """Fail loudly, PER HEREDOC, when discovery cannot read one of them.

    docs/setup.md happens to be discoverable from .github/scripts too -- as
    a FIXTURE KEY in verify-gate-12.py, not as the path the gate opens -- so
    if this reader silently stopped matching, every subject document would
    still be found and this check would still print 0 failures. That is the
    same "green while proving nothing" shape the whole file exists to stop.
    A style change to the heredocs (a different delimiter, an unquoted
    one) must therefore be a loud failure here, not a quiet loss of
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


def check_local_runner_parity(root="."):
    """-> list of failure strings.

    `pr_time_gates` finds a gate by substring; `pr_time_invocations`
    tokenizes the same text to recover its argv, and run-local-gates.py
    runs only what the second returns. A gate the tokenizer cannot parse
    therefore vanishes from the local suite while still running in CI, and
    the sweep keeps reporting the smaller number as if it were the whole
    thing. Neither reader can notice that alone; comparing them can.
    """
    failures = []
    invoked = {script for script, _ in pr_time_invocations(root)}
    for script in pr_time_gates(root):
        if script not in invoked:
            failures.append(
                f"{script} runs in the PR-time lint suite, but the local "
                f"runner recovers no argv for it, so `run-local-gates.py` "
                f"skips it entirely. Its call site is written in a form the "
                f"registry's tokenizer cannot read - the local sweep is "
                f"quietly rehearsing less than CI runs.")
    if not failures:
        print(f"ok    all {len(pr_time_gates(root))} PR-time gate(s) are "
              f"reproducible locally ({len(pr_time_invocations(root))} invocation(s))")

    # The same promise for the heredoc gates (Gate 12's live scan among
    # them). pr_time_inline_steps and LOOSE_PY_HEREDOC_RE share one grammar
    # for "this step opens a python heredoc"; a PR-time step it cannot run
    # verbatim is reported here rather than dropped, and a lint-workflows.yml
    # with no runnable heredoc gate at all means the reader broke, not that
    # the gates went away.
    runnable, unrunnable = pr_time_inline_steps(root)
    for name, reason in unrunnable:
        failures.append(
            f"lint-workflows.yml step {name!r} runs a python heredoc in the "
            f"PR-time suite, but run-local-gates.py cannot execute it "
            f"verbatim ({reason}), so the local sweep is quietly rehearsing "
            f"less than CI runs. Give it a script the registry can invoke, "
            f"or keep the step self-contained.")
    if not runnable:
        failures.append(
            "pr_time_inline_steps found no runnable python-heredoc step in "
            "lint-workflows.yml's PR-time jobs - Gates 2/3/6/12/15/16/22/23 "
            "are written that way, so the reader has stopped seeing them.")
    elif not unrunnable:
        print(f"ok    all {len(runnable)} PR-time heredoc gate(s) run "
              f"verbatim in run-local-gates.py")
    return failures


def check_local_runner_script_coverage(root="."):
    """-> list of failure strings. Every script a PR-time lint step runs is
    one run-local-gates.py runs too (#825): a gate script it recovers argv
    for, or a script path handed to such a gate as an argument. A step that
    runs anything else (a composite's fixture suite, a harness not named
    run-tests.sh) runs in CI only, and the local sweep stays green while
    CI is red. A python-heredoc step is not read here: the runner runs a
    runnable one verbatim, and check_local_runner_parity already fails an
    unrunnable one."""
    failures = []
    invocations = pr_time_invocations(root)
    covered = {script for script, _ in invocations}
    covered |= {re.sub(r"^(?:--?[\w-]+=)?(?:\./)*", "", arg)
                for _, args in invocations for arg in args}
    steps = pr_time_script_calls(root)
    total = 0
    for name, scripts, unresolved in steps:
        for path in unresolved:
            failures.append(
                f"lint-workflows.yml step {name!r} runs {path!r} in the PR-time "
                f"suite, a script path this check cannot resolve to one "
                f"repository file (a variable, an expression, a glob, a "
                f"checkout prefix, or a working-directory: that is not "
                f"literal), so it cannot tell whether "
                f"run-local-gates.py runs it (#825). Name each script by its "
                f"literal repo-relative path.")
        for script in scripts:
            total += 1
            if script in covered:
                continue
            failures.append(
                f"lint-workflows.yml step {name!r} runs {script} in the PR-time "
                f"suite, but run-local-gates.py does not run it, so the local "
                f"sweep can be green while CI is red (#825). Move it to "
                f"{SCRIPTS_DIR}/ as a verify-* gate or a <name>-tests/run-tests.sh "
                f"harness, which the runner derives on its own.")
    if not failures:
        print(f"ok    all {total} script call(s) in the PR-time suite run "
              f"in run-local-gates.py too")
    return failures


def check_forward_wiring(root="."):
    """-> (wiring dict, failures). Every check is invoked by some workflow.

    Split out of `main` (T004) so `--self-test` can exercise this direction
    alone, against a fixture tree, without also requiring the rest of the
    tree the other checks need (a subject document, a real lint-workflows.yml).
    """
    wiring = invocations(root)
    failures = []
    for script, workflows in wiring.items():
        if not workflows:
            failures.append(
                f"{script} is not invoked by any workflow. A verifier nothing "
                f"runs is not a verifier: it will drift out of sync with the "
                f"code it checks and keep reporting success (this is exactly "
                f"what happened to verify-denied-tool-collector.sh). Wire it "
                f"into a gate, or delete it.")
    return wiring, failures


def check_reverse_wiring(root="."):
    """-> list of failure strings. Every invoked path -- .github/scripts/...
    and .github/actions/... alike -- exists on disk."""
    failures = []
    for path, workflows in referenced_script_paths(root).items():
        if not os.path.exists(os.path.join(root, path)):
            failures.append(
                f"{path} is run by {', '.join(workflows)} but does not exist. "
                f"That step will fail the moment it is reached, and until "
                f"then its name in the job list implies a check that is not "
                f"happening.")
    for path, workflows in referenced_actions_script_paths(root).items():
        if not os.path.exists(os.path.join(root, path)):
            failures.append(
                f"{path} is run by {', '.join(workflows)} but does not exist. "
                f"That step will fail the moment it is reached, and until "
                f"then its name in the job list implies a check that is not "
                f"happening.")
    return failures


def check_shared_wiring(root="."):
    """-> ({module: [importer, ...]}, failures). Every wc_*.py shared
    module is imported by something -- an empty importer list is the
    failure."""
    scripts_dir = os.path.join(root, SCRIPTS_DIR)
    sources = {}
    for name in os.listdir(scripts_dir):
        if name.endswith(".py"):
            sources[name] = open(os.path.join(scripts_dir, name),
                                 encoding="utf-8").read()
    importers_by_module = {}
    failures = []
    for module in shared_modules(root):
        stem = module[:-3]
        importers = sorted(
            n for n, src in sources.items()
            if n != module
            and re.search(rf"^\s*(from {stem} import|import {stem})\b",
                          src, re.M))
        importers_by_module[module] = importers
        if not importers:
            failures.append(
                f"{SCRIPTS_DIR}/{module} is a shared module that nothing "
                f"imports. It is exempt from the invocation rule because "
                f"nothing runs it directly, which makes an unused one "
                f"invisible. Use it or delete it.")
    return importers_by_module, failures


def main():
    failures = []
    _self_check()

    # --- forward: every check is invoked -----------------------------------
    wiring, forward_failures = check_forward_wiring()
    if not wiring:
        print("::error::found no verify-* scripts at all. Either they moved "
              "or this gate's discovery has broken; either way it is about "
              "to check nothing.")
        return 1
    for script, workflows in wiring.items():
        if workflows:
            print(f"ok    {script} <- {', '.join(workflows)}")
    failures.extend(forward_failures)

    # --- reverse: every invoked path exists --------------------------------
    failures.extend(check_reverse_wiring())

    # --- modules: every shared module has an importer ----------------------
    importers_by_module, module_failures = check_shared_wiring()
    for module, importers in importers_by_module.items():
        if importers:
            print(f"ok    {module} <- imported by {', '.join(importers)}")
    failures.extend(module_failures)

    # --- argv: CI's gate set and the local runner's agree -----------------
    failures.extend(check_local_runner_parity())
    failures.extend(check_local_runner_script_coverage())

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


# ----------------------------------------------------------------------------
# Self-test
# ----------------------------------------------------------------------------
# Gate 10 ran live-only against the real tree from the day it shipped (#158)
# until this feature (research.md D6) -- every check above predates fixture
# coverage. Rather than backfilling every existing branch at once, each
# fixture below is appended by the task that introduces or extends the
# failure branch it proves, in the same in-tempdir _write shape
# verify-actions-layer-invariants.py already uses. `FIXTURES` starts empty:
# this scaffold alone must run and exit 0 with zero fixtures asserted
# (checkpoint after this task), and the live (no-flag) run above is
# unchanged by anything in this section.
def _write(root, relpath, content):
    full = os.path.join(root, *relpath.split("/"))
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(content)


def _fixture_uncovered_script_call():
    """#825: a PR-time step running a script the local runner does not
    derive (a fixture suite named run.sh) is reported; a run-tests.sh
    harness beside it is not."""
    root = tempfile.mkdtemp(prefix="wc-gate-wiring-")
    try:
        _write(root, ".github/scripts/widget-tests/run-tests.sh", "echo hi\n")
        _write(root, ".github/scripts/gadget-tests/run.sh", "echo hi\n")
        _write(root, ".github/workflows/lint-workflows.yml",
               "on: pull_request\njobs:\n  lint:\n    runs-on: ubuntu-latest\n"
               "    steps:\n"
               "      - name: covered\n"
               "        run: bash .github/scripts/widget-tests/run-tests.sh\n"
               "      - name: uncovered\n"
               "        run: bash .github/scripts/gadget-tests/run.sh\n")
        failures = check_local_runner_script_coverage(root)
        ok = (len(failures) == 1 and ".github/scripts/gadget-tests/run.sh" in failures[0]
              and "'uncovered'" in failures[0])
        return ok, f"got {failures!r}"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _fixture_uncovered_script_shapes():
    """Code review of #939: a script is seen through an interpreter, by
    direct exec, across a `\\` continuation, behind an interpreter flag
    that takes a value, or in a `NAME=` assignment; a path no reader can
    resolve (a variable, an expression, a glob) fails rather than being
    skipped; a script handed to a gate as a `--flag=` argument is the
    gate's input, not a second call. A step named like a runnable heredoc
    step, and an unnamed one, are read all the same."""
    root = tempfile.mkdtemp(prefix="wc-gate-wiring-")
    expr = "$" + "{{ github.workspace }}"
    try:
        _write(root, ".github/scripts/widget-tests/run-tests.sh", "echo hi\n")
        _write(root, ".github/workflows/lint-workflows.yml",
               "on: pull_request\njobs:\n  lint:\n    runs-on: ubuntu-latest\n"
               "    steps:\n"
               "      - name: heredoc\n"
               "        run: |\n"
               "          python3 - <<'PYEOF'\n"
               "          print('hi')\n"
               "          PYEOF\n"
               "      - name: heredoc\n"
               "        run: ./.github/scripts/a-tests/run.sh\n"
               "      - run: |\n"
               "          bash \\\n"
               "            tools/b.sh\n"
               "      - name: flagged\n"
               "        run: bash -o pipefail .github/scripts/c-tests/run.bash\n"
               "      - name: unresolved\n"
               "        run: |\n"
               "          for t in .github/actions/*/tests/run.sh; do bash \"$t\"; done\n"
               "          bash \"$GITHUB_WORKSPACE/.github/scripts/d.sh\"\n"
               f"          python3 {expr}/.github/scripts/e.py\n"
               "      - name: assigned\n"
               "        run: S=.github/scripts/g-tests/run.sh; bash \"$S\"\n"
               "      - name: covered\n"
               "        run: bash .github/scripts/widget-tests/run-tests.sh "
               "--case=.github/scripts/fixtures/case.sh\n")
        failures = check_local_runner_script_coverage(root)
        joined = "\n".join(failures)
        want = [".github/scripts/a-tests/run.sh", "runs tools/b.sh ",
                ".github/scripts/c-tests/run.bash", "'.github/actions/*/tests/run.sh'",
                "'$GITHUB_WORKSPACE/.github/scripts/d.sh'", "}}/.github/scripts/e.py'",
                "runs .github/scripts/g-tests/run.sh ", "'heredoc'", "'(unnamed step)'"]
        ok = (len(failures) == 7 and all(w in joined for w in want)
              and "widget-tests" not in joined and "case.sh" not in joined)
        return ok, f"got {failures!r}"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _fixture_script_call_tokens():
    """Code review of #939: a script path an `echo`/`printf` prints, a
    `test -f`/`[ -x ]` probes, a trailing comment or a heredoc body
    mentions, or a URL carries is not a call; a script reached through a
    literal `working-directory:`, a directory variable the step assigns or
    a literal `env:` sets, or a `$( )` with quotes of its own, is; and a
    `working-directory:` holding an expression leaves the path
    unresolved."""
    root = tempfile.mkdtemp(prefix="wc-gate-wiring-")
    expr = "$" + "{{ inputs.dir }}"
    try:
        _write(root, ".github/workflows/lint-workflows.yml",
               "on: pull_request\njobs:\n  lint:\n    runs-on: ubuntu-latest\n"
               "    steps:\n"
               "      - name: mentions\n"
               "        run: |\n"
               "          echo \"run .github/scripts/m-tests/run.sh\"\n"
               "          printf '%s\\n' .github/scripts/m-tests/run.sh\n"
               "          test -f .github/scripts/m-tests/run.sh && "
               "[ -x .github/scripts/m-tests/run.sh ]\n"
               "          curl -o /dev/null https://example.com/.github/scripts/m.sh\n"
               "          true # bash .github/scripts/m-tests/run.sh\n"
               "          cat <<'EOF'\n"
               "          it's bash .github/scripts/m-tests/run.sh\n"
               "          EOF\n"
               "      - name: workdir\n"
               "        working-directory: .github/actions/w\n"
               "        run: bash tests/run.sh\n"
               "      - name: dirvar\n"
               "        env:\n          E: .github/actions/u/tests\n"
               "        run: |\n"
               "          D=.github/actions/v/tests\n"
               "          bash \"$D/run.sh\" && bash \"${E}/run.sh\"\n"
               "      - name: cmdsub\n"
               "        run: |\n"
               "          out=\"$(bash .github/scripts/y-tests/run.sh \"$a\")\" # it's\n"
               "      - name: exprdir\n"
               f"        working-directory: {expr}\n"
               "        run: bash run.sh\n"
               # Code review of #954: a here-string or an arithmetic shift
               # opens no heredoc, and a wrapper command hides no
               # interpreter.
               "      - name: herestring\n"
               "        run: |\n"
               "          read a <<< \"hello\"\n"
               "          n=$(( 1 << k )); (( n <<= k ))\n"
               "          bash .github/scripts/h-tests/run.sh\n"
               "      - name: wrapped\n"
               "        working-directory: .github/actions/t\n"
               "        run: |\n"
               "          timeout 300 bash tests/run.sh\n"
               "          env A=1 nice -n 5 bash tests/more.sh\n"
               "          sudo -u runner python3 tests/x.py\n"
               # Code review of #954, round 2: a `$( )` body runs where it
               # stands, with the variables set by then, and a `-c`
               # string is code (its `cd` included), never a path.
               "      - name: order\n"
               "        run: |\n"
               "          out=\"$(bash \"$O/run.sh\")\"; O=.github/actions/o\n"
               "          D=.github/actions/p; out=\"$(bash \"$D/run.sh\")\"\n"
               "          D=.github/actions/q\n"
               "      - name: dashc\n"
               "        working-directory: .github/actions/c\n"
               "        run: |\n"
               "          bash -c \"cd tests && ./run.sh\"\n"
               "          sh -c 'bash more/run.sh'\n")
        failures = check_local_runner_script_coverage(root)
        joined = "\n".join(failures)
        want = ["runs .github/actions/w/tests/run.sh ",
                "runs .github/actions/v/tests/run.sh ",
                "runs .github/actions/u/tests/run.sh ",
                "runs .github/scripts/y-tests/run.sh ",
                "'exprdir' runs '" + expr + "/run.sh'",
                "runs .github/scripts/h-tests/run.sh ",
                "runs .github/actions/t/tests/run.sh ",
                "runs .github/actions/t/tests/more.sh ",
                "runs .github/actions/t/tests/x.py ",
                "runs .github/actions/p/run.sh ",
                "runs .github/actions/c/tests/run.sh ",
                "runs .github/actions/c/more/run.sh "]
        ok = (len(failures) == 12 and all(w in joined for w in want)
              and "m-tests" not in joined and "m.sh" not in joined
              and "actions/o/" not in joined and "actions/q/" not in joined
              and "cd tests" not in joined)
        return ok, f"got {failures!r}"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _fixture_script_call_scoping():
    """Code review of #954, round 3: a backtick substitution runs its
    script; `-c` (alone or in a cluster like `-ec`) is code only ahead of
    the script, so `bash x.sh -c foo` still runs x.sh; a `cd` inside a
    `( )` group ends at its `)`; and a variable reassigned from something
    no reader can pin down (`$OTHER`, a `$( )`) no longer carries its
    earlier literal value, nor a `$( )` placeholder, into a path."""
    root = tempfile.mkdtemp(prefix="wc-gate-wiring-")
    try:
        _write(root, ".github/workflows/lint-workflows.yml",
               "on: pull_request\njobs:\n  lint:\n    runs-on: ubuntu-latest\n"
               "    steps:\n"
               "      - name: scoped\n"
               "        working-directory: .github/actions/s\n"
               "        env:\n          E: tests/stale-env.sh\n"
               "        run: |\n"
               "          x=`bash tests/tick.sh`\n"
               "          bash tests/trail.sh -c foo\n"
               "          python3 tests/trail.py -c cfg\n"
               "          bash -ec 'bash tests/inner.sh'\n"
               "          (cd sub && bash a.sh)\n"
               "          bash b.sh\n"
               "          S=tests/stale.sh; S=$OTHER; bash \"$S\"\n"
               "          E=$(pick); bash \"$E\"\n"
               "          D=$(dirname x); bash \"$D/tests/run.sh\"\n")
        failures = check_local_runner_script_coverage(root)
        joined = "\n".join(failures)
        want = ["runs .github/actions/s/tests/tick.sh ",
                "runs .github/actions/s/tests/trail.sh ",
                "runs .github/actions/s/tests/trail.py ",
                "runs .github/actions/s/tests/inner.sh ",
                "runs .github/actions/s/sub/a.sh ",
                "runs .github/actions/s/b.sh "]
        ok = (len(failures) == 6 and all(w in joined for w in want)
              and "stale" not in joined and "WC_CMDSUB" not in joined
              and "bash tests" not in joined)
        return ok, f"got {failures!r}"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _fixture_script_call_stdin():
    """Code review of #954, round 4: a heredoc a shell runs (`bash
    <<'EOF'`, `cat <<EOF | bash`) is code, its scripts read, while one
    handed to a script stays data; `bash < x.sh` runs x.sh; nothing after
    `python3 -m MOD` is a script; a python `-Wonce` hides no `-c`; `bash
    -s arg` runs its stdin (round 5); an interpreter behind an unknown
    wrapper (`retry 3`, `xvfb-run -a`) runs its script; a shell behind
    a known wrapper (`timeout 300 bash <<EOF`) runs its heredoc (round 8);
    `-eo pipefail` takes `pipefail` as the option's value, and a shell
    after `if` runs its heredoc (round 10); and a
    step `env:` expression overrides a job's literal value, so the job's
    file is not reported as the script the step runs."""
    root = tempfile.mkdtemp(prefix="wc-gate-wiring-")
    expr = "$" + "{{ inputs.s }}"
    try:
        _write(root, ".github/workflows/lint-workflows.yml",
               "on: pull_request\njobs:\n  lint:\n    runs-on: ubuntu-latest\n"
               "    env:\n      S: .github/scripts/job-env.sh\n"
               "    steps:\n"
               "      - name: stdin\n"
               "        working-directory: .github/actions/i\n"
               "        run: |\n"
               "          bash <<'EOF'\n"
               "          bash tests/heredoc.sh\n"
               "          EOF\n"
               "          cat <<EOF | sh -e\n"
               "          bash tests/piped.sh\n"
               "          EOF\n"
               "          bash tests/real.sh <<EOF\n"
               "          bash tests/data.sh\n"
               "          EOF\n"
               "          bash < tests/redirected.sh\n"
               "          python3 -m pytest tests/test_mod.py\n"
               "          python3 -Wonce tests/warned.py\n"
               # Round 5: `bash -s arg` still runs its stdin, and an
               # interpreter behind a wrapper this reader does not know
               # still runs its script (origin/main's regex saw it).
               "          bash -s arg <<EOF\n"
               "          bash tests/sfed.sh\n"
               "          EOF\n"
               "          retry 3 bash tests/retried.sh\n"
               "          xvfb-run -a bash tests/xvfb.sh\n"
               "          xargs -a list bash tests/xargs.sh\n"
               # Round 8: a shell behind a wrapper still runs its heredoc.
               "          timeout 300 bash <<EOF\n"
               "          bash tests/wrapped.sh\n"
               "          EOF\n"
               # Round 10: an option cluster's `o` takes `pipefail` as
               # its value, and a shell after `if`/`while` runs its
               # heredoc.
               "          bash -eo pipefail -c \"bash tests/clustered.sh\"\n"
               "          bash -eo pipefail <<EOF\n"
               "          bash tests/clustered-hd.sh\n"
               "          EOF\n"
               "          if bash -s <<EOF; then\n"
               "          bash tests/if-hd.sh\n"
               "          EOF\n"
               "            :\n"
               "          fi\n"
               "      - name: override\n"
               f"        env:\n          S: {expr}\n"
               "        run: bash \"$S\"\n")
        failures = check_local_runner_script_coverage(root)
        joined = "\n".join(failures)
        want = ["runs .github/actions/i/tests/heredoc.sh ",
                "runs .github/actions/i/tests/piped.sh ",
                "runs .github/actions/i/tests/real.sh ",
                "runs .github/actions/i/tests/redirected.sh ",
                "runs .github/actions/i/tests/warned.py ",
                "runs .github/actions/i/tests/sfed.sh ",
                "runs .github/actions/i/tests/retried.sh ",
                "runs .github/actions/i/tests/xvfb.sh ",
                "runs .github/actions/i/tests/xargs.sh ",
                "runs .github/actions/i/tests/wrapped.sh ",
                "runs .github/actions/i/tests/clustered.sh ",
                "runs .github/actions/i/tests/clustered-hd.sh ",
                "runs .github/actions/i/tests/if-hd.sh "]
        ok = (len(failures) == 13 and all(w in joined for w in want)
              and "data.sh" not in joined and "test_mod" not in joined
              and "job-env" not in joined)
        return ok, f"got {failures!r}"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _fixture_script_call_scope_reset():
    """Code review of #954, round 6: `cd "$GITHUB_WORKSPACE"` returns to
    the checkout root, where repo paths still resolve; `D=x cmd` sets D
    for that command only, so a later `$D` keeps the job's literal value;
    and a heredoc delimiter bash accepts with a `-` in it (`<<'PY-EOF'`)
    still hides its body, an apostrophe there blanking nothing after.
    Round 7: so does a backslash-quoted one (`<<\\EOF`)."""
    root = tempfile.mkdtemp(prefix="wc-gate-wiring-")
    try:
        _write(root, ".github/workflows/lint-workflows.yml",
               "on: pull_request\njobs:\n  lint:\n    runs-on: ubuntu-latest\n"
               "    env:\n      D: .github/actions/j\n"
               "    steps:\n"
               "      - name: reset\n"
               "        working-directory: .github/actions/i\n"
               "        run: |\n"
               "          cd \"$GITHUB_WORKSPACE\"\n"
               "          bash .github/scripts/rooted.sh\n"
               "          D=.github/actions/k bash .github/scripts/prefixed.sh\n"
               "          bash \"$D/scoped.sh\"\n"
               "          cat <<'PY-EOF'\n"
               "          it's data\n"
               "          PY-EOF\n"
               "          cat <<\\EOF\n"
               "          it's data: bash .github/scripts/inbody.sh\n"
               "          EOF\n"
               "          bash .github/scripts/after.sh\n")
        failures = check_local_runner_script_coverage(root)
        joined = "\n".join(failures)
        want = ["runs .github/scripts/rooted.sh ",
                "runs .github/scripts/prefixed.sh ",
                "runs .github/actions/j/scoped.sh ",
                "runs .github/scripts/after.sh "]
        ok = (len(failures) == 4 and all(w in joined for w in want)
              and "actions/k" not in joined and "$PWD" not in joined
              and "inbody.sh" not in joined)
        return ok, f"got {failures!r}"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _fixture_folded_join_subjects():
    """Code reviews of #940: a subject path split across os.path.join
    arguments after a root is read as the path it spells, a `"."`
    component dropped; a join with a non-constant argument further in is
    not a constant path. A feature's own document or a skill is a subject
    only when it exists on disk."""
    source = (
        "import os\n"
        "A = os.path.join(REPO_ROOT, 'specs', '060-x', 'contracts', 'c.md')\n"
        "B = os.path.join('.', 'docs', 'adoption.md')\n"
        "C = os.path.join(root, 'specs', slug, 'contracts', 'c.md')\n"
        "D = os.path.join('specs', '999-made-up', 'spec.md')\n"
        "E = os.path.join('.claude', 'skills', 'spec-cross-reference', 'SKILL.md')\n")
    got = sorted(_subject_paths_in_source(source))
    # Spelled in pieces: a literal here would itself read as a subject.
    skill = "/".join((".claude", "skills", "spec-cross-reference", "SKILL.md"))
    want = sorted(["/".join(("specs", "060-x", "contracts", "c.md")),
                   "/".join(("docs", "adoption.md"))]
                  + ([skill] if os.path.isfile(skill) else []))
    return got == want and len(want) == 3, f"got {got!r}, want {want!r}"


def _fixture_inline_steps_match_ci():
    """Code review of #939: run-local-gates.py writes two heredoc steps
    whose names share a slug to two files, not one, and runs each under
    CI's `bash -e {0}`, so a failing command before the last fails it.
    A heredoc step under any shell: (step, job default or workflow
    default) is unrunnable verbatim, since that changes CI's flags, and
    so is one under a working-directory:, since the runner runs it from
    the repository root (code review of #942)."""
    import importlib.util
    from wc_shell_harness import resolve_bash
    root = tempfile.mkdtemp(prefix="wc-gate-wiring-")
    try:
        spec = importlib.util.spec_from_file_location(
            "wc_run_local_gates",
            os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "run-local-gates.py"))
        runner = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(runner)
        paths = runner._write_inline_gates(
            [("Lint: shared slug", "false\ntrue\n"),
             ("Lint, shared slug", "true\n"),
             ("Gate 9", "true\n"), ("Gate 9 again", "true\n")], root)
        bash = resolve_bash()
        rcs = [subprocess.run(runner.command_for(p, bash),
                              capture_output=True).returncode for p in paths]
        _write(root, ".github/workflows/lint-workflows.yml",
               "on: pull_request\njobs:\n"
               "  a:\n    runs-on: ubuntu-latest\n    steps:\n"
               "      - name: plain\n        run: |\n"
               "          python3 - <<'PYEOF'\n          PYEOF\n"
               "      - name: step-shell\n        shell: bash\n        run: |\n"
               "          python3 - <<'PYEOF'\n          PYEOF\n"
               "  b:\n    runs-on: ubuntu-latest\n"
               "    defaults:\n      run:\n        shell: bash\n    steps:\n"
               "      - name: job-shell\n        run: |\n"
               "          python3 - <<'PYEOF'\n          PYEOF\n"
               "  c:\n    runs-on: ubuntu-latest\n    steps:\n"
               "      - name: step-wd\n        working-directory: sub\n"
               "        run: |\n"
               "          python3 - <<'PYEOF'\n          PYEOF\n"
               "  d:\n    runs-on: ubuntu-latest\n"
               "    defaults:\n      run:\n        working-directory: sub\n"
               "    steps:\n"
               "      - name: job-wd\n        run: |\n"
               "          python3 - <<'PYEOF'\n          PYEOF\n")
        runnable, unrunnable = pr_time_inline_steps(root)
        ok = (len(set(paths)) == 4 and rcs[0] != 0 and rcs[1:] == [0, 0, 0]
              and [n for n, _ in runnable] == ["plain"]
              and sorted(n for n, _ in unrunnable)
              == ["job-shell", "job-wd", "step-shell", "step-wd"])
        return ok, (f"got paths={paths!r} rcs={rcs!r} runnable={runnable!r} "
                    f"unrunnable={unrunnable!r}")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _fixture_orphaned_composite_harness():
    """A composite harness with no invoking workflow reports as orphaned
    (FR-003 -- already-true behaviour; this fixture proves it, research.md
    D6 first bullet)."""
    root = tempfile.mkdtemp(prefix="wc-gate-wiring-")
    try:
        _write(root, ".github/scripts/widget-tests/run-tests.sh", "echo hi\n")
        _, failures = check_forward_wiring(root)
        found = any(".github/scripts/widget-tests/run-tests.sh" in f
                   for f in failures)
        return found, f"got {failures!r}"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _fixture_distinct_gate_labels():
    """Two run-tests.sh harnesses sharing a basename under different
    .github/scripts/<name>-tests/ directories get distinct gate_label()
    identities (FR-007, research.md D6 fifth bullet)."""
    a = gate_label(".github/scripts/foo-tests/run-tests.sh", [])
    b = gate_label(".github/scripts/bar-tests/run-tests.sh", [])
    return a != b, f"got {a!r} == {b!r}"


def _fixture_actions_harness_not_gate10_subject():
    """A run-tests.sh under .github/actions/ (outside _shared/), invoked by
    some workflow but not lint-workflows.yml, never enters gate_scripts()'s
    .github/scripts/-only notion of "a gate" (D2) -- Gate 10's forward check
    has nothing to say about it either way, so it cannot double-report or
    contradict the placement gate's (verify-actions-no-gate-scripts.py) own
    failure for the same file (research.md D6, fourth bullet; spec.md Edge
    Case; quickstart.md §4)."""
    root = tempfile.mkdtemp(prefix="wc-gate-wiring-")
    try:
        path = ".github/actions/widget/run-tests.sh"
        _write(root, path, "echo hi\n")
        _write(root, ".github/workflows/other.yml",
               "on: push\njobs:\n  a:\n    steps:\n"
               f"      - run: {path}\n")
        wiring, failures = check_forward_wiring(root)
        ok = path not in wiring and not any(path in f for f in failures)
        return ok, f"got wiring keys={list(wiring)!r} failures={failures!r}"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _fixture_missing_actions_path():
    """A run: block naming a .github/actions/ script path with no file on
    disk is reported as missing, the same way a missing .github/scripts/
    path already is (FR-004, research.md D6 second bullet)."""
    root = tempfile.mkdtemp(prefix="wc-gate-wiring-")
    try:
        path = ".github/actions/widget/missing.sh"
        _write(root, ".github/workflows/fake.yml",
               "on: push\njobs:\n  a:\n    steps:\n"
               f"      - run: ./{path}\n")
        failures = check_reverse_wiring(root)
        ok = any(path in f and "does not exist" in f for f in failures)
        return ok, f"got {failures!r}"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _fixture_actions_self_checkout_dedup():
    """A pair of run: blocks -- one ./.github/actions/_shared/x.sh, one
    ./.wing-commander-pipeline/.github/actions/_shared/x.sh -- with the same
    file existing once on disk report as ONE path, not a spurious second
    entry (FR-013, research.md D6 third bullet)."""
    root = tempfile.mkdtemp(prefix="wc-gate-wiring-")
    try:
        _write(root, ".github/actions/_shared/x.sh", "echo hi\n")
        _write(root, ".github/workflows/fake.yml",
               "on: push\njobs:\n  a:\n    steps:\n"
               "      - run: |\n"
               "          ./.github/actions/_shared/x.sh\n"
               "          ./.wing-commander-pipeline/.github/actions/_shared/x.sh\n")
        refs = referenced_actions_script_paths(root)
        ok = list(refs.keys()) == [".github/actions/_shared/x.sh"]
        return ok, f"got {refs!r}"
    finally:
        shutil.rmtree(root, ignore_errors=True)


# Each entry: (name, fixture_fn), fixture_fn() -> (ok: bool, detail: str).
# A fixture builds and tears down its own tempdir, so a FAILing fixture never
# leaves scratch state for the next one to trip over.
FIXTURES = [
    ("a PR-time step running a script the local runner does not derive is "
     "reported (#825)", _fixture_uncovered_script_call),
    ("a script is seen however a step runs it, and an unresolvable script "
     "path fails (code review of #939)", _fixture_uncovered_script_shapes),
    ("a script path a step only mentions is not a call, and one reached "
     "through working-directory:, a variable or $( ) is (code review of "
     "#939)", _fixture_script_call_tokens),
    ("a backtick runs its script, `-c` is code only ahead of the script, "
     "a `( )` group's cd ends at its `)`, and a non-literal reassignment "
     "drops the earlier value (code review of #954)",
     _fixture_script_call_scoping),
    ("a heredoc or `<` a shell runs is code, `python3 -m` takes no "
     "script, `-Wonce` hides no -c, and a step env: expression overrides "
     "a job literal (code review of #954)", _fixture_script_call_stdin),
    ("cd \"$GITHUB_WORKSPACE\" returns to the root, a prefix assignment "
     "ends with its command, and a `-` heredoc delimiter hides its body "
     "(code review of #954, round 6)", _fixture_script_call_scope_reset),
    ("a subject path split across os.path.join arguments is read whole "
     "(code reviews of #940)", _fixture_folded_join_subjects),
    ("inline heredoc steps get distinct files, run under CI's bash -e, and "
     "a shell: or working-directory: step is unrunnable verbatim (code "
     "reviews of #939 and #942)",
     _fixture_inline_steps_match_ci),
    ("an unwired composite harness reports as orphaned",
     _fixture_orphaned_composite_harness),
    ("two run-tests.sh harnesses under different directories get distinct "
     "gate_label identities", _fixture_distinct_gate_labels),
    ("a run-tests.sh under .github/actions/ is never Gate 10's forward-check "
     "subject", _fixture_actions_harness_not_gate10_subject),
    ("a missing .github/actions/ path named by a run: block is reported",
     _fixture_missing_actions_path),
    ("the self-checkout .github/actions/ prefix dedups to one path",
     _fixture_actions_self_checkout_dedup),
]


def self_test():
    bad = 0
    for name, fixture_fn in FIXTURES:
        ok, detail = fixture_fn()
        if ok:
            print(f"[ok] {name}")
        else:
            bad += 1
            print(f"[FAIL] {name}: {detail}")
    print(f"verify-gate-wiring self-test: {len(FIXTURES) - bad}/{len(FIXTURES)} "
          f"fixtures behaved as specified.")
    return 1 if bad else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Assert every check in .github/scripts is wired to a "
                    "workflow, and every wire lands.")
    parser.add_argument("--self-test", action="store_true")
    cli_args = parser.parse_args()
    sys.exit(self_test() if cli_args.self_test else main())
