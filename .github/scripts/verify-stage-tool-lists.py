#!/usr/bin/env python3
"""Gate 27 - the per-stage default tool-list table matches the call sites.

WHY THIS EXISTS
---------------
specs/026-configurable-tool-lists (#144) shipped `wing-commander-tool-args`
and, with it, a promise: FR-013 / SC-006, "a consumer can determine, from
documentation alone, what each stage's default tool lists are". The document
that keeps that promise is the table in

    specs/010-reusable-pipeline/contracts/stage-interfaces.md

and it is hand-maintained. The contract says so in as many words - "a future
change that edits a stage's default list must update this table" - and then
nothing enforced it. The 16 `default-allowed-tools:`/`default-disallowed-
tools:` literals at the composite's call sites are the only source of truth,
so a one-line edit to any of them silently falsified the documentation a
consumer is told to rely on when writing an `allowed-tools-override`.

This is the same failure mode as the drifted-and-orphaned
verify-denied-tool-collector.sh (#139 -> PR #158): a document that reads as
evidence while proving nothing. It had already happened here. When this gate
was written, the table's older sibling - the 026 draft the 010 copy was
carried from - was missing both `pr-conversation.*` rows entirely, while its
own prose referred to "`pr-conversation.act` below". Two copies, one stale,
neither checked (#147).

The draft is now a pointer at the live table rather than a second copy, so
this gate has exactly one document to hold to exactly one set of literals.

WHAT IT CHECKS
--------------
  1. Every `wing-commander-tool-args` call site has a row, keyed by
     `step-label`, and every row has a call site. A row for a step that no
     longer exists is as misleading as a missing one.

  2. For each label, the documented allowed and disallowed lists hold the
     same tools as the literals - and, where the table wrote an order down,
     in that order. See the note on the two cell forms below for why order
     is asserted on some rows and not others.

Cells come in two forms, both used by the live table:

    `A,B,C`                                    - a literal list
    same as `other-label` plus `D,E`           - relative to another row

The relative form is resolved against the row it names, which is why the
gate reads the table as a whole before comparing anything. A trailing
parenthetical - "(deliberately read-only)" - is prose and ignored; only
backticked spans are read as tool names.

The relative form APPENDS, while the shipped literals interleave:
`plan.pr` carries Bash(git checkout:*) beside Bash(git commit:*), not at
the end. So the notation cannot express the shipped order, and rows using
it are compared as sets. Literal cells - where an order was actually
written down - are still compared in order. Widening every row to a set
comparison would have been the easy fix and would have thrown away a real
assertion on the thirteen rows that can hold it.

WHAT IT DOES NOT CHECK
----------------------
Whether a default list is the RIGHT list. Gate 12 answers that for `gh`
tools (does the step's token carry the permission the grant implies); this
gate only answers whether the documentation says what the workflows do.

SELF-TEST
---------
`--self-test` mutates the real inputs in memory - dropping a row, adding a
row for no call site, reordering one list, editing a single tool, and
breaking a `same as` reference - and asserts each is caught, and caught for
the right reason. A gate that cannot fail its own subject is worthless; this
repository has three recorded instances of shipping one (#169).
"""
import argparse
import glob
import io
import os
import re
import shutil
import sys
import tempfile

import yaml

_NL = chr(10)

TABLE_DOC = "specs/010-reusable-pipeline/contracts/stage-interfaces.md"
# Both extensions: GitHub accepts either, and every other gate in this
# repository globs both. Globbing only *.yml would make a .yaml stage
# invisible to Gate 27 - an undocumented tool grant passing the check
# whose whole job is to catch it.
WORKFLOW_DIR = ".github/workflows"
WORKFLOW_GLOBS = ("*.yml", "*.yaml")
COMPOSITE = "wing-commander-tool-args"
BACKTICKED = re.compile(r"`([^`]*)`")
SAME_AS = re.compile(r"^\s*same as\b", re.IGNORECASE)


def split_tools(text):
    """A comma-separated tool list -> ordered list, blanks dropped."""
    return [t.strip() for t in text.split(",") if t.strip()]


def collect_sites(root="."):
    """-> ({step-label: (allowed, disallowed)}, [error, ...]).

    `step-label` is the join key between a call site and its documented row,
    so it has to be unique for the comparison to mean anything. A second
    site reusing a label used to overwrite the first silently: the gate
    would then compare the survivor against the row and report a clean
    match, while the shadowed site's grants were never checked against
    anything. A collision is therefore a failure, not a last-write-wins.
    """
    sites = {}
    origins = {}
    errors = []
    paths = []
    for pat in WORKFLOW_GLOBS:
        paths.extend(glob.glob(
            os.path.join(root, WORKFLOW_DIR, pat).replace(os.sep, "/")))
    for path in sorted(set(paths)):
        with io.open(path, encoding="utf-8") as fh:
            doc = yaml.safe_load(fh) or {}
        rel = path.replace(os.sep, "/")
        for job in (doc.get("jobs") or {}).values():
            for step in (job or {}).get("steps") or []:
                if COMPOSITE not in str((step or {}).get("uses", "")):
                    continue
                with_ = step.get("with") or {}
                label = with_.get("step-label")
                if not label:
                    continue
                entry = (
                    split_tools(str(with_.get("default-allowed-tools", ""))),
                    split_tools(str(with_.get("default-disallowed-tools", ""))),
                )
                if label in sites:
                    errors.append(
                        "step-label {0!r} is used by more than one `{1}` call "
                        "site ({2} and {3}). Labels are the join key to {4}, "
                        "so a duplicate leaves one site compared against "
                        "nothing.".format(
                            label, COMPOSITE, origins[label], rel, TABLE_DOC))
                    continue
                origins[label] = rel
                sites[label] = entry
    return sites, errors


def call_sites(root="."):
    """The sites alone, for callers that only need the mapping."""
    return collect_sites(root)[0]


def parse_table(text):
    """-> ({label: (allowed, disallowed)}, [error, ...]).

    Unresolvable `same as` references are reported rather than skipped: a
    reference to a row that does not exist would otherwise silently produce
    an empty list, which compares unequal for a reason nobody can read.
    """
    raw = {}
    order = []
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 4:
            continue
        spans = BACKTICKED.findall(cells[1])
        if len(spans) != 1:
            continue                      # header row, separator, or prose
        label = spans[0]
        if label == "step-label":
            continue                      # the header's own backticked word
        raw[label] = (cells[2], cells[3])
        order.append(label)

    errors = []
    resolved = {}

    def resolve(label, cell, seen):
        spans = BACKTICKED.findall(cell)
        if not SAME_AS.match(cell):
            if not spans:
                errors.append(
                    "row {0!r}: cell has no backticked tool list: {1!r}".format(
                        label, cell[:80]))
                return []
            return split_tools(spans[0])
        if not spans:
            errors.append(
                "row {0!r}: `same as` cell names no row: {1!r}".format(
                    label, cell[:80]))
            return []
        base_label = spans[0]
        if base_label in seen:
            errors.append(
                "row {0!r}: `same as` reference cycles through {1!r}".format(
                    label, base_label))
            return []
        if base_label not in raw:
            errors.append(
                "row {0!r}: `same as {1}` names a row that does not exist in "
                "the table".format(label, base_label))
            return []
        which = 0 if cell is raw[label][0] else 1
        base = resolve(base_label, raw[base_label][which], seen | {label})
        extra = []
        for span in spans[1:]:
            extra.extend(split_tools(span))
        return base + extra

    relative = set()
    for label in order:
        allowed_cell, disallowed_cell = raw[label]
        for idx, cell in ((0, allowed_cell), (1, disallowed_cell)):
            if SAME_AS.match(cell):
                relative.add((label, idx))
        resolved[label] = (resolve(label, allowed_cell, {label}),
                           resolve(label, disallowed_cell, {label}))
    return resolved, errors, relative


def compare(sites, table, relative=frozenset()):
    """-> list of failure strings.

    `relative` holds (label, idx) pairs whose documented cell uses the
    `same as <row> plus <tools>` notation. Those are compared as SETS,
    not sequences: the notation appends, while the shipped literals
    interleave - `plan.pr` carries Bash(git checkout:*) next to
    Bash(git commit:*), not at the end - so the notation cannot express
    the shipped order and an order assertion against it would fail
    forever on three rows that are entirely correct. Literal cells,
    where the author did write an order, are still held to it.
    """
    failures = []

    for label in sorted(set(sites) - set(table)):
        failures.append(
            "step-label {0!r} composes tool args in a workflow but has no row "
            "in {1}. A consumer cannot determine its defaults from "
            "documentation, which is what FR-013/SC-006 promise.".format(
                label, TABLE_DOC))

    for label in sorted(set(table) - set(sites)):
        failures.append(
            "{0} documents step-label {1!r}, but no `{2}` call site uses that "
            "label. The row describes a step that does not exist.".format(
                TABLE_DOC, label, COMPOSITE))

    for label in sorted(set(sites) & set(table)):
        for idx, which in ((0, "allowed"), (1, "disallowed")):
            shipped, documented = sites[label][idx], table[label][idx]
            if shipped == documented:
                continue
            if (label, idx) in relative and sorted(shipped) == sorted(documented):
                continue
            missing = [t for t in shipped if t not in documented]
            extra = [t for t in documented if t not in shipped]
            if missing or extra:
                detail = []
                if missing:
                    detail.append("shipped but undocumented: " +
                                  ", ".join(missing))
                if extra:
                    detail.append("documented but not shipped: " +
                                  ", ".join(extra))
                failures.append(
                    "{0} default-{1}-tools disagrees with {2}. {3}.".format(
                        label, which, TABLE_DOC, "; ".join(detail)))
            else:
                failures.append(
                    "{0} default-{1}-tools has the same tools as {2} but in a "
                    "different ORDER. SC-005 promises a byte-for-byte "
                    "identical composed list, so the order is part of the "
                    "contract. shipped: {3}".format(
                        label, which, TABLE_DOC, ",".join(shipped)))
    return failures


def run(root="."):
    with io.open(os.path.join(root, TABLE_DOC), encoding="utf-8") as fh:
        table, errors, relative = parse_table(fh.read())
    sites, site_errors = collect_sites(root)
    return site_errors + errors + compare(sites, table, relative)


# --------------------------------------------------------------------------
# Self-test
# --------------------------------------------------------------------------
def _mutations(sites, table):
    """-> [(name, mutated_sites, mutated_table, expected substring), ...]"""
    label = "intake"
    other = "finalize"
    out = []

    t = dict(table)
    del t[label]
    out.append(("a call site with no row", dict(sites), t,
                "composes tool args in a workflow but has no row"))

    t = dict(table)
    t["ghost.step"] = (["Read"], ["Write"])
    out.append(("a row with no call site", dict(sites), t,
                "no `wing-commander-tool-args` call site uses that label"))

    t = dict(table)
    allowed, disallowed = t[label]
    t[label] = (list(reversed(allowed)), disallowed)
    # deliberately a LITERAL cell (`intake`), so this mutation proves the
    # order assertion is still live for rows that can express order.
    out.append(("a reordered literal list", dict(sites), t,
                "in a different ORDER"))

    t = dict(table)
    allowed, disallowed = t[other]
    t[other] = (allowed[:-1], disallowed)
    out.append(("a tool shipped but dropped from the table", dict(sites), t,
                "shipped but undocumented: " + table[other][0][-1]))

    t = dict(table)
    allowed, disallowed = t[other]
    t[other] = (allowed + ["Bash(rm -rf:*)"], disallowed)
    out.append(("a tool documented that is not shipped", dict(sites), t,
                "documented but not shipped: Bash(rm -rf:*)"))

    return out


BROKEN_REF_TABLE = """
| Stage | Internal step (`step-label`) | Default allowed | Default disallowed |
|---|---|---|---|
| a | `a.one` | `Read,Write` | `WebFetch` |
| a | `a.two` | same as `a.nonexistent` plus `Glob` | `WebFetch` |
"""


_FIXTURE_STEP = """      - uses: ./.github/actions/{composite}
        with:
          step-label: "{label}"
          default-allowed-tools: "Read,Glob"
          default-disallowed-tools: "WebFetch"
"""


def _fixture_workflow(labels):
    head = "name: fixture" + _NL + "on: [push]" + _NL + "jobs:" + _NL
    head += "  j:" + _NL + "    runs-on: ubuntu-latest" + _NL + "    steps:" + _NL
    return head + "".join(
        _FIXTURE_STEP.format(composite=COMPOSITE, label=l) for l in labels)


def _write_fixture(tmp, filename, labels):
    wf_dir = os.path.join(tmp, WORKFLOW_DIR)
    if not os.path.isdir(wf_dir):
        os.makedirs(wf_dir)
    with io.open(os.path.join(wf_dir, filename), "w",
                 encoding="utf-8", newline=_NL) as fh:
        fh.write(_fixture_workflow(labels))


def _collector_fixtures():
    """Drive the two collector branches that the real tree cannot reach.

    Neither is reachable from this repository's own workflows: there is no
    .yaml stage here, and no duplicated step-label - which is exactly why
    both shipped unexercised. A branch a gate cannot reach in production is
    a branch that has to be given a fixture, or it is not covered at all.
    """
    results = []

    tmp = tempfile.mkdtemp()
    try:
        _write_fixture(tmp, "dup.yml", ["stage.agent", "stage.agent"])
        _, errors = collect_sites(tmp)
        hit = any("more than one" in e for e in errors)
        results.append((
            "a duplicated step-label is reported, not silently overwritten",
            hit, errors))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    tmp = tempfile.mkdtemp()
    try:
        _write_fixture(tmp, "stage.yaml", ["yaml.agent"])
        sites, errors = collect_sites(tmp)
        results.append((
            "a call site in a .yaml workflow is discovered",
            "yaml.agent" in sites and not errors, sorted(sites)))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    return results


def self_test(root="."):
    bad = 0
    sites = call_sites(root)
    with io.open(os.path.join(root, TABLE_DOC), encoding="utf-8") as fh:
        table, errors, relative = parse_table(fh.read())

    if errors:
        print("[FAIL] the real table does not parse cleanly: " +
              " | ".join(errors))
        bad += 1
    else:
        print("[ok] the real table parses with no unresolved references")

    baseline = compare(sites, table, relative)
    if baseline:
        print("[FAIL] baseline: the real repository should be clean, got: " +
              " | ".join(baseline))
        bad += 1
    else:
        print("[ok] baseline: {0} call sites match {0} rows".format(
            len(sites)))

    for name, m_sites, m_table, expect in _mutations(sites, table):
        found = compare(m_sites, m_table, relative)
        joined = " | ".join(found)
        if not found:
            bad += 1
            print("[FAIL] mutation {0!r} was NOT caught".format(name))
        elif expect not in joined:
            bad += 1
            print("[FAIL] mutation {0!r} caught for the WRONG reason. "
                  "expected {1!r}, got: {2}".format(name, expect, joined))
        else:
            print("[ok] mutation caught: {0}".format(name))

    for name, ok, detail in _collector_fixtures():
        if ok:
            print("[ok] {0}".format(name))
        else:
            bad += 1
            print("[FAIL] {0}; got: {1}".format(name, detail))

    _, ref_errors, _ = parse_table(BROKEN_REF_TABLE)
    if any("names a row that does not exist" in e for e in ref_errors):
        print("[ok] a dangling `same as` reference is reported, not silently "
              "resolved to an empty list")
    else:
        bad += 1
        print("[FAIL] a dangling `same as` reference was not reported: "
              "{0}".format(ref_errors))

    print("Gate 27 self-test: {0} failure(s).".format(bad))
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser(description="Gate 27 - stage tool lists")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--root", default=".")
    args = ap.parse_args()

    if args.self_test:
        return self_test(args.root)

    failures = run(args.root)
    for failure in failures:
        print("::error::Gate 27: {0}".format(failure))
    print("Gate 27: compared {0} tool-args call site(s) against {1}; {2} "
          "failure(s).".format(len(call_sites(args.root)), TABLE_DOC,
                               len(failures)))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
