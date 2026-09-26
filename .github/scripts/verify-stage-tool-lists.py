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

  3. Every `Bash(<path>)` grant - at a `wing-commander-tool-args` composite
     call site's `default-allowed-tools`, a reusable-workflow caller's
     `extra-allowed-tools`/`allowed-tools-override`, or a bare
     `claude-code-action` step's `claude_args --allowedTools` string - names
     a script that exists, once any interpreter prefix (bare, `bash `, `sh `,
     `./`, `python `/`python3 `, with an optional flag) is stripped and the
     remaining token is a path (a leading `./` or a contained `/`) rather
     than a bare command (`jq`, `git status`). A path absent from the
     checkout by design (a run-time-provisioned directory) is recorded, with
     its exact text and a reason, in `script-grant-waivers.json` - an entry
     whose path *does* resolve is itself a failure, so the record cannot
     outlive its reason. Spec Kit stopped shipping `update-agent-context.sh`
     and both plan sites kept granting it, with the prompt still describing
     the step it ran (#426); the same failure mode is now caught regardless
     of which of the three surfaces carries the stale grant or which
     directory the script lives in.

WHAT IT DOES NOT CHECK
----------------------
Whether a default list is the RIGHT list. Gate 12 answers that for `gh`
tools (does the step's token carry the permission the grant implies); this
gate mostly only answers whether the documentation says what the workflows
do. Check 3 is the one exception: it reads the granted script path against
the working tree, not the table, so it can fail even when documentation and
call sites already agree with each other (#426). Check 3 resolves every
granted path at the three surfaces named above; a `Bash(<path>)` grant
written anywhere else under `.github/workflows/` is a fourth surface the
check does not yet cover, and adding it is a new finding, not a gap this
check silently absorbs (specs/082).

SELF-TEST
---------
`--self-test` mutates the real inputs in memory - dropping a row, adding a
row for no call site, reordering one list, editing a single tool,
breaking a `same as` reference, and granting a script that does not exist -
and asserts each is caught, and caught for the right reason. A gate that
cannot fail its own subject is worthless; this repository has three
recorded instances of shipping one (#169). ...and granting a script at a
reusable-workflow-caller or bare-`claude_args` surface that does not exist,
plus a waiver entry that has gone stale (specs/082).
"""
import argparse
import glob
import io
import json
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

# The read-only inspection policy (stage-interfaces.md, spec 051): every
# read-capable stage's default allowed list carries this set.
INSPECTION_SET = {
    "Bash(grep:*)", "Bash(head:*)", "Bash(tail:*)", "Bash(sort:*)",
    "Bash(uniq:*)", "Bash(wc:*)", "Bash(cut:*)",
}

READ_CAPABLE_LABELS = {
    "intake", "clarify",
    "plan.direct-commit", "plan.pr",
    "tasks.direct-commit", "tasks.pr",
    "implement.cycle", "implement.retry",
}

# A grant of any script, at any of the three surfaces this gate checks: an
# optional interpreter prefix (`bash`, `sh`, `python`, `python3`, with zero or
# more `-flag` tokens) followed by the granted token, so a re-spelled grant
# cannot walk around the check. The captured token is then classified by
# `_classify_grant_token` as a path or a bare command.
GRANT_TOKEN = re.compile(
    r"^Bash\((?:(?:bash|sh|python|python3)(?:\s+-\S+)*\s+)?"
    r"([^\s:)]+)[^)]*\)$")

WAIVER_FILE = ".github/scripts/script-grant-waivers.json"


def _classify_grant_token(token):
    """-> repository-relative path, or None if `token` is a bare command.

    A leading `./` or any `/` makes it a path (FR-003); a bare command
    (`jq`, `git`, `yamllint`) has neither and returns None.
    """
    if token.startswith("./"):
        return token[2:]
    if "/" in token:
        return token
    return None


def _grant_path(tool):
    """-> repository-relative path for `tool` (a `Bash(...)` string), or
    None if it names no path (bare command) or is unresolvable (FR-008:
    contains an unexpanded `${{ ... }}` expression, checked on the RAW
    string before token extraction, since an expression may itself embed
    whitespace GRANT_TOKEN would otherwise mis-split on).
    """
    if "${{" in tool:
        return None
    m = GRANT_TOKEN.match(tool)
    if not m:
        return None
    return _classify_grant_token(m.group(1))

# What repository guidance (CLAUDE.md's "Before pushing" section) mandates a
# stage run - hand-maintained alongside CLAUDE.md edits, same as TABLE_DOC/
# COMPOSITE above (research.md D7: this judgment belongs in reviewable code,
# not a prose-parser).
MANDATED_COMMANDS = {
    "Bash(python .github/scripts/run-local-gates.py:*)": {
        "implement.cycle", "implement.retry",
    },
}


def split_tools(text):
    """A comma-separated tool list -> ordered list, blanks dropped."""
    return [t.strip() for t in text.split(",") if t.strip()]


def _load_workflows(root="."):
    """-> ({path: parsed_doc}, [error, ...]).

    Every collector reads from this map instead of re-globbing and
    re-parsing .github/workflows/*.yml|*.yaml itself.
    """
    docs = {}
    errors = []
    paths = []
    for pat in WORKFLOW_GLOBS:
        paths.extend(glob.glob(
            os.path.join(root, WORKFLOW_DIR, pat).replace(os.sep, "/")))
    for path in sorted(set(paths)):
        rel = path.replace(os.sep, "/")
        try:
            with io.open(path, encoding="utf-8") as fh:
                docs[rel] = yaml.safe_load(fh) or {}
        except yaml.YAMLError as exc:
            errors.append(
                "{0} could not be parsed as YAML and was skipped: {1}".format(
                    rel, exc))
    return docs, errors


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
    docs, errors = _load_workflows(root)
    for rel, doc in docs.items():
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
    errors = []
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
        # The mirror image of collect_sites' duplicate guard, on the other
        # half of the same join key. A plain assignment here was
        # last-write-wins: two rows for one step-label left the FIRST row
        # compared against nothing while the gate reported a clean match -
        # the identical silent-overwrite defect the call-site side was
        # deliberately hardened against, and no less silent for being on
        # the documentation side of the join.
        if label in raw:
            errors.append(
                "step-label {0!r} has more than one row in {1}. Labels are "
                "the join key to the `{2}` call sites, so a duplicate leaves "
                "one row compared against nothing.".format(
                    label, TABLE_DOC, COMPOSITE))
            continue
        raw[label] = (cells[2], cells[3])
        order.append(label)

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


def check_inspection_set(table):
    """-> list of failure strings.

    Every read-capable stage's default allowed list carries the seven-
    primitive inspection set (stage-interfaces.md's "Read-only inspection
    policy" section). A `READ_CAPABLE_LABELS` entry absent from `table` is
    not a failure here - the `compare()` call already reports a missing row
    as its own failure, so this only evaluates labels already confirmed to
    exist.
    """
    failures = []
    for label in sorted(READ_CAPABLE_LABELS & set(table)):
        missing = INSPECTION_SET - set(table[label][0])
        if missing:
            failures.append(
                "{0!r}'s default allowed list omits {1} from the read-only "
                "inspection set ({2}'s policy section) and records no "
                "exception.".format(
                    label,
                    ", ".join("`{0}`".format(m) for m in sorted(missing)),
                    TABLE_DOC))
    return failures


def check_mandated_commands(table):
    """-> list of failure strings.

    FR-010's reconciliation made mechanical: a command repository guidance
    mandates for a stage must appear in that stage's documented default
    allowed list.
    """
    failures = []
    for command, required_labels in MANDATED_COMMANDS.items():
        for label in sorted(required_labels & set(table)):
            if command not in table[label][0]:
                failures.append(
                    "{0!r} is told by CLAUDE.md/its own prompt to run "
                    "{1!r} but its default allowed list does not permit it "
                    "(FR-010).".format(label, command))
    return failures


def _script_exists(root, rel):
    """Case-sensitive `os.path.isfile`, keyed off the directory listing.

    `os.path.isfile` is case-insensitive on Windows and macOS, but Actions
    runs this gate on Ubuntu. A case-mangled grant (`Setup-Plan.sh` for the
    shipped `setup-plan.sh`) would pass `run-local-gates.py` on this
    repository's own Windows worktrees and then fail only in CI - the exact
    local-pass/CI-fail divergence this gate exists to prevent (#436 review
    round 2).
    """
    path = os.path.join(root, rel)
    if not os.path.isfile(path):
        return False
    directory, filename = os.path.split(path)
    try:
        return filename in os.listdir(directory or ".")
    except OSError:
        return False


def collect_reusable_workflow_grants(docs):
    """-> [(site_label, [tool, ...]), ...] for jobs calling a local
    reusable workflow (`uses: ./.github/workflows/...`), reading
    `with.extra-allowed-tools` / `with.allowed-tools-override`.
    """
    sites = []
    for rel, doc in docs.items():
        for job_name, job in (doc.get("jobs") or {}).items():
            uses = str((job or {}).get("uses", ""))
            if not uses.startswith("./.github/workflows/"):
                continue
            with_ = (job or {}).get("with") or {}
            for key in ("extra-allowed-tools", "allowed-tools-override"):
                val = with_.get(key)
                if val is None:
                    continue
                label = "{0}:{1} ({2})".format(rel, job_name, key)
                sites.append((label, split_tools(str(val))))
    return sites


_ALLOWED_TOOLS_RE = (
    re.compile(r'--allowedTools\s+"([^"]*)"'),
    re.compile(r"--allowedTools\s+'([^']*)'"),
)


def _extract_allowed_tools(claude_args):
    for pattern in _ALLOWED_TOOLS_RE:
        m = pattern.search(claude_args)
        if m:
            return m.group(1)
    return None


def collect_claude_args_grants(docs):
    """-> [(site_label, [tool, ...]), ...] for claude-code-action steps
    whose `with.claude_args` carries a bare `--allowedTools "..."` string.
    """
    sites = []
    for rel, doc in docs.items():
        for job_name, job in (doc.get("jobs") or {}).items():
            for idx, step in enumerate((job or {}).get("steps") or []):
                if "claude-code-action" not in str((step or {}).get("uses", "")):
                    continue
                claude_args = (step.get("with") or {}).get("claude_args")
                if not claude_args:
                    continue
                allowed = _extract_allowed_tools(str(claude_args))
                if allowed is None:
                    continue
                step_name = step.get("name") or step.get("id") or \
                    "step[{0}]".format(idx)
                label = "{0}:{1}:{2!r}".format(rel, job_name, step_name)
                sites.append((label, split_tools(allowed)))
    return sites


def load_waivers(root="."):
    """-> ({path: entry}, [error, ...])."""
    path = os.path.join(root, WAIVER_FILE)
    with io.open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    return {w["path"]: w for w in data.get("waivers", [])}, []


def check_grant_existence(all_sites, waivers, root="."):
    """-> list of failure strings.

    `all_sites` is the concatenation of collect_sites()'s (label, allowed)
    pairs (allowed half only) with collect_reusable_workflow_grants() and
    collect_claude_args_grants()'s output - every surface, uniformly. Read
    off the CALL SITES, not the table: the table is held to the sites by
    `compare()`, and the grant that reaches the agent is the site's literal
    (#426). `exists` memoizes per call: the same script is granted at up to
    a dozen call sites (`check-prerequisites.sh` alone, across both
    spellings, at six labels), and the directory listing behind
    `_script_exists` isn't free to repeat (#436 review round 2).
    """
    failures = []
    exists = {}
    for label, tools in all_sites:
        for tool in tools:
            rel = _grant_path(tool)
            if rel is None:
                continue
            if rel in waivers:
                continue
            if rel not in exists:
                exists[rel] = _script_exists(root, rel)
            if not exists[rel]:
                failures.append(
                    "{0!r} grants {1!r}, but {2} does not exist in this "
                    "repository and carries no waiver in {3} - a stale "
                    "entry in a load-bearing list; drop the grant and any "
                    "prompt text that describes the step it ran, or add a "
                    "waiver entry if the path is absent by design.".format(
                        label, tool, rel, WAIVER_FILE))
    for rel, entry in waivers.items():
        if _script_exists(root, rel):
            failures.append(
                "{0} waives {1!r} (#{2}) as absent by design, but it now "
                "exists in the working tree - the waiver has gone stale; "
                "drop the entry.".format(
                    WAIVER_FILE, rel, entry.get("issue", "?")))
    return failures


def run(root="."):
    docs, load_errors = _load_workflows(root)
    with io.open(os.path.join(root, TABLE_DOC), encoding="utf-8") as fh:
        table, errors, relative = parse_table(fh.read())
    sites, site_errors = collect_sites(root)
    all_grant_sites = (
        [(label, allowed) for label, (allowed, _disallowed) in sites.items()]
        + collect_reusable_workflow_grants(docs)
        + collect_claude_args_grants(docs))
    waivers, waiver_errors = load_waivers(root)
    return (load_errors + site_errors + errors + waiver_errors +
            compare(sites, table, relative) +
            check_inspection_set(table) + check_mandated_commands(table) +
            check_grant_existence(all_grant_sites, waivers, root))


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

# Unreachable from the shipped table (which has no duplicate row), which is
# precisely why the hole it covers survived: a branch production cannot
# reach is a branch that gets a fixture or no coverage at all.
DUPLICATE_ROW_TABLE = """
| Stage | Internal step (`step-label`) | Default allowed | Default disallowed |
|---|---|---|---|
| a | `a.one` | `Read,Write` | `WebFetch` |
| a | `a.one` | `Read,Glob` | `WebFetch` |
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


_REUSABLE_FIXTURE = """name: fixture
on: [push]
jobs:
  j:
    uses: ./.github/workflows/x.yml
    with:
      extra-allowed-tools: "Bash(.github/scripts/zzz-does-not-exist.py:*)"
"""

_CLAUDE_ARGS_FIXTURE = """name: fixture
on: [push]
jobs:
  j:
    runs-on: ubuntu-latest
    steps:
      - name: "Run agent"
        uses: anthropics/claude-code-action@v1
        with:
          claude_args: --allowedTools "Bash(.github/scripts/zzz-does-not-exist.py:*)"
"""


def _write_text_fixture(tmp, filename, text):
    wf_dir = os.path.join(tmp, WORKFLOW_DIR)
    if not os.path.isdir(wf_dir):
        os.makedirs(wf_dir)
    with io.open(os.path.join(wf_dir, filename), "w",
                 encoding="utf-8", newline=_NL) as fh:
        fh.write(text)


def _collector_fixtures():
    """Drive the collector branches that the real tree cannot reach.

    None is reachable from this repository's own workflows: there is no
    .yaml stage here, no duplicated step-label, no reusable-workflow-caller
    grant for a missing script, and no `claude_args` grant for a missing
    script either - which is exactly why all four shipped unexercised. A
    branch a gate cannot reach in production is a branch that has to be
    given a fixture, or it is not covered at all.
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

    tmp = tempfile.mkdtemp()
    try:
        _write_text_fixture(tmp, "reusable.yml", _REUSABLE_FIXTURE)
        docs, _ = _load_workflows(tmp)
        reusable_sites = collect_reusable_workflow_grants(docs)
        found = check_grant_existence(reusable_sites, {}, tmp)
        results.append((
            "a reusable-workflow caller's extra-allowed-tools grant for a "
            "missing script is caught, naming the workflow file and job",
            len(found) == 1 and "reusable.yml:j (extra-allowed-tools)"
            in found[0],
            found))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    tmp = tempfile.mkdtemp()
    try:
        _write_text_fixture(tmp, "claude-args.yml", _CLAUDE_ARGS_FIXTURE)
        docs, _ = _load_workflows(tmp)
        claude_sites = collect_claude_args_grants(docs)
        found = check_grant_existence(claude_sites, {}, tmp)
        results.append((
            "a bare claude_args --allowedTools grant for a missing script "
            "is caught, naming the workflow file, job, and step",
            len(found) == 1 and "claude-args.yml:j:" in found[0]
            and "Run agent" in found[0],
            found))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    return results


def self_test(root="."):
    bad = 0
    sites = call_sites(root)
    docs, _doc_errors = _load_workflows(root)
    waivers, _waiver_errors = load_waivers(root)
    with io.open(os.path.join(root, TABLE_DOC), encoding="utf-8") as fh:
        table, errors, relative = parse_table(fh.read())

    if errors:
        print("[FAIL] the real table does not parse cleanly: " +
              " | ".join(errors))
        bad += 1
    else:
        print("[ok] the real table parses with no unresolved references")

    # _grant_path's classifier, exercised directly and independent of any
    # collector or surface (research.md D9 mutations 4/5).
    bare = _grant_path("Bash(jq:*)")
    if bare is None:
        print("[ok] _grant_path classifies a bare-command grant "
              "(Bash(jq:*)) as no path")
    else:
        bad += 1
        print("[FAIL] _grant_path should classify a bare-command grant as "
              "no path, got: {0!r}".format(bare))

    expr_grant = "Bash(python3 -I ${{ runner.temp }}/x.py:*)"
    expr = _grant_path(expr_grant)
    if expr is None:
        print("[ok] _grant_path classifies an expression-valued grant as "
              "unresolvable, even though it contains a `/`")
    else:
        bad += 1
        print("[FAIL] _grant_path should classify an expression-valued "
              "grant ({0!r}) as unresolvable, got: {1!r}".format(
                  expr_grant, expr))

    baseline = compare(sites, table, relative)
    if baseline:
        print("[FAIL] baseline: the real repository should be clean, got: " +
              " | ".join(baseline))
        bad += 1
    else:
        print("[ok] baseline: {0} call sites match {0} rows".format(
            len(sites)))

    baseline_inspection = check_inspection_set(table)
    if baseline_inspection:
        print("[FAIL] baseline: the real table should carry the full "
              "inspection set on every read-capable row, got: " +
              " | ".join(baseline_inspection))
        bad += 1
    else:
        print("[ok] baseline: every read-capable row carries the "
              "inspection set")

    baseline_mandated = check_mandated_commands(table)
    if baseline_mandated:
        print("[FAIL] baseline: the real table should already permit every "
              "mandated command, got: " + " | ".join(baseline_mandated))
        bad += 1
    else:
        print("[ok] baseline: every mandated command is permitted where "
              "required")

    # T019 / SC-003: the widened check, run against every real grant across
    # all three surfaces and the real waiver map, mechanically proving
    # research.md D0's "13 grant occurrences, 2 waiver entries, repository
    # green" claim rather than only asserting it in prose.
    all_sites = (
        [(label, allowed) for label, (allowed, _disallowed) in sites.items()]
        + collect_reusable_workflow_grants(docs)
        + collect_claude_args_grants(docs))
    baseline_scripts = check_grant_existence(all_sites, waivers, root)
    if baseline_scripts:
        print("[FAIL] baseline: every granted script across all three "
              "surfaces should exist or carry a waiver in {0}, got: {1}"
              .format(WAIVER_FILE, " | ".join(baseline_scripts)))
        bad += 1
    else:
        print("[ok] baseline: every granted script across all three "
              "surfaces ({0} grant site(s), {1} waiver entrie(s)) exists "
              "or carries a waiver".format(len(all_sites), len(waivers)))

    # These mutations run against the REAL sites/waivers/root, so their
    # assertions look only at the NEW failures a mutation adds on top of
    # `baseline_scripts` above - never at the raw count - since a stray
    # untracked directory already present in the working tree (this
    # repository's own `.wing-commander-pipeline/` pipeline-checkout
    # convention, when this self-test runs from inside a pipeline stage's
    # own job rather than a clean `actions/checkout@v5`) can itself already
    # be contributing a pre-existing failure baseline_scripts already
    # reported once, on its own, above.
    def new_failures(found):
        return [f for f in found if f not in baseline_scripts]

    # The shipped defect (#426), replayed: both spellings of a grant for a
    # script Spec Kit no longer ships, on the site that carried them.
    ghost = ".specify/scripts/bash/update-agent-context.sh"
    m_sites = dict(sites)
    allowed, disallowed = m_sites["plan.direct-commit"]
    m_sites["plan.direct-commit"] = (
        allowed + ["Bash({0}:*)".format(ghost), "Bash(bash {0}:*)".format(ghost)],
        disallowed)
    m_all_sites = [(label, a) for label, (a, _d) in m_sites.items()]
    found = new_failures(check_grant_existence(m_all_sites, waivers, root))
    if len(found) == 2 and all(ghost in f and "plan.direct-commit" in f
                               for f in found):
        print("[ok] mutation caught: a grant for a .specify script that does "
              "not exist, in both spellings")
    else:
        bad += 1
        print("[FAIL] a grant for a nonexistent .specify script was not caught "
              "in both spellings (expected 2 failures naming it): {0}".format(found))

    # The other two spellings GRANT_TOKEN accepts (`sh `-prefixed and a
    # `./`-prefixed path), plus a grant carrying a trailing argument before
    # the wildcard - none of which the #426 replay above exercises. A
    # synthetic name, not a real script that merely happens to be absent
    # today, so this can never start passing for the wrong reason if a
    # future Spec Kit release ships a same-named file (#436 review round 2).
    ghost2 = ".specify/scripts/bash/zzz-does-not-exist.sh"
    for spelling, grant in (
        ("sh-prefixed", "Bash(sh {0}:*)".format(ghost2)),
        ("./-prefixed", "Bash(./{0}:*)".format(ghost2)),
        ("carrying a trailing argument", "Bash({0} --json:*)".format(ghost2)),
    ):
        m_sites = dict(sites)
        allowed, disallowed = m_sites["plan.direct-commit"]
        m_sites["plan.direct-commit"] = (allowed + [grant], disallowed)
        m_all_sites = [(label, a) for label, (a, _d) in m_sites.items()]
        found = new_failures(check_grant_existence(m_all_sites, waivers, root))
        if len(found) == 1 and ghost2 in found[0]:
            print("[ok] mutation caught: a {0} grant for a .specify script "
                  "that does not exist".format(spelling))
        else:
            bad += 1
            print("[FAIL] a {0} grant for a nonexistent .specify script was "
                  "not caught (expected 1 failure naming it): {1}".format(
                      spelling, found))

    # research.md D9 mutation 1 / T012: a composite-site grant for a script
    # OUTSIDE .specify/scripts/bash/ that does not exist - proving the
    # widened check is not still secretly scoped to one directory.
    ghost3 = ".github/scripts/zzz-does-not-exist.py"
    m_sites = dict(sites)
    allowed, disallowed = m_sites["plan.direct-commit"]
    m_sites["plan.direct-commit"] = (
        allowed + ["Bash({0}:*)".format(ghost3)], disallowed)
    m_all_sites = [(label, a) for label, (a, _d) in m_sites.items()]
    found = new_failures(check_grant_existence(m_all_sites, waivers, root))
    if len(found) == 1 and ghost3 in found[0] and \
            "plan.direct-commit" in found[0]:
        print("[ok] mutation caught: a grant for a nonexistent script "
              "outside .specify/scripts/bash/")
    else:
        bad += 1
        print("[FAIL] a grant for a nonexistent script outside "
              ".specify/scripts/bash/ was not caught (expected 1 failure "
              "naming the site and path): {0}".format(found))

    # A grant whose case doesn't match the file on disk must fail here the
    # same way it fails on Actions' case-sensitive runners, even though
    # this self-test itself may be running on a case-insensitive filesystem.
    tmp = tempfile.mkdtemp()
    try:
        script_dir = os.path.join(tmp, ".specify", "scripts", "bash")
        os.makedirs(script_dir)
        with io.open(os.path.join(script_dir, "setup-plan.sh"), "w",
                     encoding="utf-8") as fh:
            fh.write("#!/bin/sh\n")
        mismatched = [("plan.direct-commit",
                       ["Bash(.specify/scripts/bash/Setup-Plan.sh:*)"])]
        found = check_grant_existence(mismatched, {}, tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if len(found) == 1 and "Setup-Plan.sh" in found[0]:
        print("[ok] mutation caught: a case-mismatched grant, even on a "
              "case-insensitive filesystem")
    else:
        bad += 1
        print("[FAIL] a case-mismatched grant was not caught - this check "
              "would pass locally on Windows/macOS and fail only in CI: "
              "{0}".format(found))

    # A grant for a script that DOES exist is not a failure: the check
    # reads the working tree, not a list of names. `real` can legitimately
    # be empty (e.g. if a future change moves every `.specify` script grant
    # off plan.direct-commit) - that is not itself a defect, so it must not
    # be reported as one; `baseline_scripts` above already covers every
    # real grant across every site.
    real = [t for t in sites["plan.direct-commit"][0]
            if _grant_path(t) is not None]
    found = new_failures(
        check_grant_existence([("plan.direct-commit", real)], waivers, root))
    if not found:
        print("[ok] the {0} shipped script grant(s) on plan.direct-commit "
              "pass".format(len(real)))
    else:
        bad += 1
        print("[FAIL] the shipped script grants should pass, got: {0} for "
              "{1}".format(found, real))

    # research.md D9 mutation 6 / T018 / FR-007: a waiver entry whose path
    # DOES resolve is itself a failure - proven against a synthetic fixture
    # tree, never against either of the two real waiver entries (neither is
    # expected to ever resolve, per waiver-schema.md's Verification note).
    tmp = tempfile.mkdtemp()
    try:
        stale_path = "stale-waived-script.sh"
        with io.open(os.path.join(tmp, stale_path), "w",
                     encoding="utf-8") as fh:
            fh.write("#!/bin/sh\n")
        stale_waivers = {stale_path: {"path": stale_path, "issue": "#000",
                                       "reason": "test fixture"}}
        found = check_grant_existence([], stale_waivers, tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if len(found) == 1 and WAIVER_FILE in found[0] and \
            stale_path in found[0] and "#000" in found[0]:
        print("[ok] mutation caught: a waiver entry whose path now exists "
              "in the working tree is reported as stale")
    else:
        bad += 1
        print("[FAIL] a stale waiver entry (path now exists) was not caught "
              "(expected 1 failure naming {0}, the path, and the issue): "
              "{1}".format(WAIVER_FILE, found))

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

    t = dict(table)
    allowed, disallowed = t["plan.direct-commit"]
    t["plan.direct-commit"] = (
        [tool for tool in allowed if tool != "Bash(cut:*)"], disallowed)
    found = " | ".join(check_inspection_set(t))
    if "omits `Bash(cut:*)`" in found:
        print("[ok] mutation caught: plan.direct-commit loses "
              "Bash(cut:*) from the inspection set")
    else:
        bad += 1
        print("[FAIL] mutation 'plan.direct-commit loses Bash(cut:*)' was "
              "NOT caught for the right reason: {0}".format(found))

    t = dict(table)
    allowed, disallowed = t["finalize"]
    t["finalize"] = ([], disallowed)
    found = check_inspection_set(t)
    if found:
        bad += 1
        print("[FAIL] a non-read-capable row (finalize) missing the whole "
              "inspection set should not fail Check A, got: {0}".format(
                  found))
    else:
        print("[ok] a non-read-capable row missing the whole inspection "
              "set raises no Check A failure")

    t = dict(table)
    allowed, disallowed = t["implement.cycle"]
    gate_suite = "Bash(python .github/scripts/run-local-gates.py:*)"
    t["implement.cycle"] = (
        [tool for tool in allowed if tool != gate_suite], disallowed)
    found = " | ".join(check_mandated_commands(t))
    if "is told by CLAUDE.md" in found and \
            "does not permit it" in found:
        print("[ok] mutation caught: implement.cycle loses the mandated "
              "gate-suite command")
    else:
        bad += 1
        print("[FAIL] mutation 'implement.cycle loses the gate-suite "
              "command' was NOT caught for the right reason: {0}".format(
                  found))

    for name, ok, detail in _collector_fixtures():
        if ok:
            print("[ok] {0}".format(name))
        else:
            bad += 1
            print("[FAIL] {0}; got: {1}".format(name, detail))

    dup_table, dup_errors, _ = parse_table(DUPLICATE_ROW_TABLE)
    if any("more than one row" in e for e in dup_errors):
        print("[ok] a duplicated table row is reported, not silently "
              "overwritten")
    else:
        bad += 1
        print("[FAIL] a duplicated table row was not reported: {0} "
              "(parsed: {1})".format(dup_errors, sorted(dup_table)))

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
