#!/usr/bin/env python3
"""Gate 31 - published stages read no ambient repository state.

WHY THIS EXISTS
---------------
Constitution VII: a `workflow_call`-only stage workflow is the PUBLISHED
CONTRACT. It owns no trigger and reads no ambient state - not
`github.event.*`, not `vars.*`, and never `secrets: inherit`. Every event
fact and every knob arrives as a declared, typed input. A stage that must
deviate carries a REGISTERED, MACHINE-CHECKED exception - never an
undeclared one, and never a code comment alone.

`release.yml`'s Gate 1b has enforced two thirds of that since spec 010, and
it did so badly in two ways that this gate exists to fix (#149):

  TIMING. `release.yml` is `workflow_dispatch`-only, so the invariants were
  checked when a human cut a release and never on the pull request that
  introduced the violation.

  COVERAGE - the load-bearing half. Gate 1b greps a hardcoded brace
  expansion of eight file names. There are eleven `workflow_call`-only
  stages. `watchdog.yml` was in neither that list nor `actionlint`'s, so the
  largest stage in the fleet was the one file no linter examined, and its
  `vars.*` reads grew 2 -> 9 -> 15 across FOUR tagged releases while Gate 1b
  passed on every one of them. The gate did not miss a window between
  checks; it ran, and was structurally incapable of seeing the file. A
  PR-time gate carrying the same hardcoded list would have passed all four
  times too.

The control group in the same measurement is what makes the rule credible
rather than aspirational: at `v2.2.0` every stage Gate 1b DID cover read
`vars.*` zero times. Stages do not naturally accumulate ambient reads - they
stay at zero precisely where something checks.

So the stage list is DERIVED, twice (see `stage_workflows`), and the one
standing deviation is a waiver in a checked-in file rather than a name
missing from a brace expansion. `watchdog.yml`'s exception used to be
expressed by NOT APPEARING in that expansion, and its own comment called
itself "release.yml Gate 1b's documented vars.*-read exception" while
`release.yml` never mentioned the watchdog - the two halves of that claim
never met.

WHAT IT CHECKS
--------------
For every workflow whose `on:` declares `workflow_call` AND NOTHING ELSE:

  1. no `github.event...` read
  2. no `vars.<NAME>` read
  3. no `secrets: inherit`

Reads are counted only in EXPRESSION context - inside `${{ ... }}`, or in
the value of an `if:` key, which GitHub evaluates as an expression with or
without the braces. Prose is not a read: `watchdog.yml` has two comments
saying it never reads `github.event.*`, and `auto-update-spec-kit.yml`'s
`trigger` input describes itself as resolved "from github.event_name" by the
wrapper. A grep counts all three as violations; none of them is one.
Comments are blanked before the scan for the same reason, offsets preserved
so line numbers stay true.

WAIVERS (.github/scripts/stage-invariant-waivers.json)
------------------------------------------------------
Each waiver names the file, the exact pattern, why, and the tracking issue,
and declares HOW MANY findings it covers. It is stale-checked in both
directions, on the model of Gate 26's grandfathered tag:

  - a pattern matching nothing fails the gate. An exception nobody can
    inspect suppresses the next violation that reuses its shape.
  - a count that no longer matches fails the gate. This is what makes GROWTH
    red: the watchdog's fifteen reads are waived, a sixteenth is not, and
    the four-release drift #149 measured would have failed on the release
    that took it from 2 to 9.
  - a waiver naming a file that is not a discovered stage fails the gate.

A waiver cannot outlive its reason, and it cannot quietly widen.

SELF-TEST
---------
`--self-test` builds throwaway repository roots on disk - real workflow
files, a real waiver file - and runs the real `evaluate()` over them, so
discovery, comment stripping, expression detection and waiver loading are
all exercised rather than stubbed. A fixture that fails for the WRONG reason
is itself a failure (#169): every red fixture asserts the substring naming
its specific defect.
"""
import argparse
import json
import os
import re
import shutil
import sys
import tempfile

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_published_stages import published_stages  # noqa: E402

WORKFLOWS_DIR = ".github/workflows"
WAIVERS_PATH = ".github/scripts/stage-invariant-waivers.json"

# --------------------------------------------------------------------------
# The invariants
# --------------------------------------------------------------------------
# id -> (regex over expression context, human sentence for the report)
EXPRESSION_INVARIANTS = {
    "github.event": (
        re.compile(r"github\.event[A-Za-z0-9_.]*"),
        "reads github.event - event facts reach a stage only as declared "
        "workflow_call inputs, extracted by the wrapper that owns the "
        "trigger (constitution VII, research.md D2)",
    ),
    "vars": (
        re.compile(r"\bvars\.[A-Za-z_][A-Za-z0-9_]*"),
        "reads vars.* - configuration reaches a stage only as declared "
        "workflow_call inputs, so an adopter can see every knob in the "
        "stage's own interface (constitution VII, research.md D5)",
    ),
}

# Not an expression: a `secrets: inherit` binding is YAML, and it hands the
# called workflow every secret the caller holds rather than the ones its
# interface declares.
SECRETS_INHERIT_RE = re.compile(r"^[ \t]*secrets:[ \t]*inherit[ \t]*$", re.M)
SECRETS_INHERIT_MESSAGE = (
    "uses `secrets: inherit` - a stage never receives a secret beyond those "
    "its own workflow_call interface declares (constitution VII)"
)

EXPR_RE = re.compile(r"\$\{\{.*?\}\}", re.S)
# `if:` is evaluated as an expression with or without ${{ }}, so
# `if: vars.X == 'true'` is a vars read that a braces-only scan would miss.
IF_RE = re.compile(r"^[ \t]*(?:-[ \t]+)?if:[ \t]*", re.M)


class Finding(object):
    """One ambient read, at a file and line, with the text that matched."""

    def __init__(self, path, line, check, text):
        self.path = path
        self.line = line
        self.check = check
        self.text = text

    def __repr__(self):                                  # pragma: no cover
        return "<Finding {0}:{1} {2} {3!r}>".format(
            self.path, self.line, self.check, self.text)


# --------------------------------------------------------------------------
# Reading a workflow file
# --------------------------------------------------------------------------
def strip_comments(text):
    """Blank out comment text, preserving every offset and line break.

    Both YAML and the shell inside a `run:` block start a comment at a `#`
    that begins a line or follows whitespace, and neither does inside a
    quoted string. Quote state is tracked per line and reset at each newline,
    which is what YAML block scalars and shell lines both want.

    Blanked rather than removed so `text[:offset].count("\\n")` still names
    the right line - a report that points at the wrong line is a report a
    maintainer stops trusting.
    """
    out = []
    for line in text.split("\n"):
        in_single = in_double = False
        cut = None
        i = 0
        while i < len(line):
            char = line[i]
            if in_single:
                if char == "'":
                    in_single = False
            elif in_double:
                if char == "\\":
                    i += 1
                elif char == '"':
                    in_double = False
            elif char == "'":
                in_single = True
            elif char == '"':
                in_double = True
            elif char == "#" and (i == 0 or line[i - 1] in " \t"):
                cut = i
                break
            i += 1
        out.append(line if cut is None else line[:cut] + " " * (len(line) - cut))
    return "\n".join(out)


def expression_spans(text):
    """(start, end) of every region GitHub evaluates as an expression."""
    spans = [(m.start(), m.end()) for m in EXPR_RE.finditer(text)]
    for match in IF_RE.finditer(text):
        eol = text.find("\n", match.end())
        spans.append((match.end(), len(text) if eol < 0 else eol))
    return spans


def scan_text(path, text):
    """-> [Finding] for one workflow's source."""
    code = strip_comments(text)
    spans = expression_spans(code)
    findings = []
    for check, (pattern, _) in sorted(EXPRESSION_INVARIANTS.items()):
        for match in pattern.finditer(code):
            if not any(start <= match.start() < end for start, end in spans):
                continue
            findings.append(Finding(path,
                                    code[:match.start()].count("\n") + 1,
                                    check, match.group(0)))
    for match in SECRETS_INHERIT_RE.finditer(code):
        findings.append(Finding(path,
                                code[:match.start()].count("\n") + 1,
                                "secrets-inherit", match.group(0).strip()))
    return sorted(findings, key=lambda f: (f.line, f.check, f.text))


# --------------------------------------------------------------------------
# Discovery
# --------------------------------------------------------------------------
def workflow_paths(root="."):
    base = os.path.join(root, *WORKFLOWS_DIR.split("/"))
    if not os.path.isdir(base):
        return []
    out = []
    for name in sorted(os.listdir(base)):
        if name.endswith(".yml") or name.endswith(".yaml"):
            out.append(os.path.join(base, name))
    return out


def _rel(root, path):
    """Repo-relative, forward slashes - the form a waiver names."""
    rel = os.path.relpath(path, root).replace(os.sep, "/")
    return rel[2:] if rel.startswith("./") else rel


def trigger_names(workflow):
    """Every trigger a parsed workflow declares, in any of the four forms.

    PyYAML resolves the bare key `on` to the boolean True (YAML 1.1); a
    quoted "on" stays a string. The value may then be a mapping
    (`on:\\n  workflow_call:`), a sequence (`on: [workflow_call]`) or a bare
    scalar (`on: workflow_call`). Losing any one of those forms would drop
    stages out of the scan silently, which is why `evaluate` fails loudly on
    a workflow this returns nothing for.
    """
    on = workflow.get(True, workflow.get("on"))
    if isinstance(on, dict):
        return [str(k) for k in on]
    if isinstance(on, list):
        return [str(k) for k in on]
    if isinstance(on, str):
        return [on]
    return []


def load_workflows(root="."):
    """-> [(relpath, source, parsed_or_None)] for every workflow file."""
    loaded = []
    for path in workflow_paths(root):
        with open(path, encoding="utf-8") as handle:
            source = handle.read()
        try:
            parsed = yaml.safe_load(source) or {}
        except yaml.YAMLError:
            parsed = None    # the YAML guard rail reports this, better
        loaded.append((_rel(root, path), source, parsed))
    return loaded


def stage_workflows(loaded):
    """Relative paths of every workflow whose only trigger is workflow_call."""
    return sorted(path for path, _, parsed in loaded
                  if parsed is not None
                  and set(trigger_names(parsed)) == {"workflow_call"})


# --------------------------------------------------------------------------
# Waivers
# --------------------------------------------------------------------------
REQUIRED_WAIVER_FIELDS = ("file", "check", "pattern", "count", "reason",
                          "issue")


def load_waivers(root="."):
    """-> (waivers, failures). A missing file means no waivers, not an error.

    Absent is legitimate - it is the state every stage but one is in, and the
    state this repository should end up in when #149's waiver is retired.
    Unreadable or malformed is not: that would silence every waiver check at
    once, so it is reported.
    """
    path = os.path.join(root, *WAIVERS_PATH.split("/"))
    if not os.path.isfile(path):
        return [], []
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (ValueError, OSError) as exc:
        return [], ["{0} could not be read ({1}). A waiver file that does not "
                    "parse would otherwise silently waive nothing while "
                    "looking like a register.".format(WAIVERS_PATH, exc)]
    waivers = data.get("waivers") if isinstance(data, dict) else data
    if not isinstance(waivers, list):
        return [], ["{0} must contain a \"waivers\" list.".format(WAIVERS_PATH)]
    return waivers, []


def check_waiver_shape(waivers):
    """-> list of failure strings for structurally invalid waivers."""
    failures = []
    for index, waiver in enumerate(waivers):
        where = "{0} entry {1}".format(WAIVERS_PATH, index)
        if not isinstance(waiver, dict):
            failures.append("{0} is not an object.".format(where))
            continue
        missing = [f for f in REQUIRED_WAIVER_FIELDS if not waiver.get(f)]
        # count is an int and 0 is falsy, but a waiver covering zero findings
        # is stale by definition, so treating it as missing is right.
        if missing:
            failures.append(
                "{0} ({1}) is missing {2}. Every waiver names the file, the "
                "exact pattern, the reason, the tracking issue and the number "
                "of findings it covers - an exception whose reason nobody "
                "recorded is indistinguishable from a bug someone "
                "silenced.".format(where, waiver.get("file", "?"),
                                   ", ".join(missing)))
            continue
        known = set(EXPRESSION_INVARIANTS) | {"secrets-inherit"}
        if waiver["check"] not in known:
            failures.append(
                "{0} waives check {1!r}, which is not one of {2}. A waiver "
                "for a check that does not exist waives nothing.".format(
                    where, waiver["check"], ", ".join(sorted(known))))
            continue
        try:
            re.compile(waiver["pattern"])
        except re.error as exc:
            failures.append("{0} has an invalid pattern {1!r}: {2}".format(
                where, waiver["pattern"], exc))
        if not isinstance(waiver["count"], int):
            failures.append("{0} count must be an integer, got {1!r}.".format(
                where, waiver["count"]))
    return failures


def apply_waivers(findings, waivers, stages):
    """-> (unwaived findings, failures). Stale checking lives here.

    A finding is waived by a waiver naming its file and check whose pattern
    matches the exact text that matched - `vars.WING_COMMANDER_SPEC_PREFIX`,
    not the whole line - so a waiver cannot be written broadly enough to
    cover a read it was never meant to.
    """
    failures = []
    waived = set()
    for index, waiver in enumerate(waivers):
        where = "{0} entry {1}".format(WAIVERS_PATH, index)
        if waiver["file"] not in stages:
            failures.append(
                "{0} waives {1}, which is not a workflow_call-only stage in "
                "this checkout. Either the file moved, gained a second "
                "trigger, or was deleted - in every case the waiver now "
                "covers nothing and hides the next stage that takes its "
                "name.".format(where, waiver["file"]))
            continue
        pattern = re.compile(waiver["pattern"])
        matched = [f for f in findings
                   if f.path == waiver["file"]
                   and f.check == waiver["check"]
                   and pattern.search(f.text)]
        if not matched:
            failures.append(
                "{0} waives {1} in {2} with pattern {3!r}, and nothing "
                "matches it any more. The reason ({4}) has been resolved or "
                "the read was respelled; remove the waiver - a standing "
                "exception for a violation nobody can inspect suppresses the "
                "next one that reuses its shape.".format(
                    where, waiver["check"], waiver["file"], waiver["pattern"],
                    waiver["issue"]))
            continue
        if len(matched) != waiver["count"]:
            direction = ("MORE" if len(matched) > waiver["count"] else "FEWER")
            failures.append(
                "{0} declares {1} finding(s) of {2} in {3}, but {4} match - "
                "{5} than the waiver was granted for. {6} Update the count "
                "deliberately, with the reason, or fix the reads: #149 "
                "measured this exact drift growing 2 -> 9 -> 15 across four "
                "releases with nothing red.".format(
                    where, waiver["count"], waiver["check"], waiver["file"],
                    len(matched), direction,
                    "A waived deviation may not grow."
                    if len(matched) > waiver["count"] else
                    "The waiver is now wider than the deviation it covers."))
            continue
        waived.update(id(f) for f in matched)
    return [f for f in findings if id(f) not in waived], failures


# --------------------------------------------------------------------------
# The gate
# --------------------------------------------------------------------------
def evaluate(root="."):
    """-> (failures, stages, findings, waived_count)."""
    failures = []
    loaded = load_workflows(root)

    # The trigger reader must understand how EVERY workflow declares its
    # triggers. If it stops recognising a form, the stages written that way
    # silently leave the scan and the gate prints a smaller number as though
    # it were the whole story - the mutation attacks the gate's eyesight
    # rather than the property it enforces, so nothing inside the rule can
    # notice. Same technique as verify-gate-wiring.py's loose second reader.
    for path, _, parsed in loaded:
        if parsed is None:
            continue
        if not trigger_names(parsed):
            failures.append(
                "{0} declares no trigger this gate can read. Either the file "
                "has no `on:` block, or the reader no longer understands the "
                "form it uses - in which case stages written that way have "
                "silently left the scan.".format(path))

    stages = stage_workflows(loaded)

    # Second reader: the derivation release.yml's Gate 1a already uses. It
    # answers "is this published", this file answers "is workflow_call its
    # ONLY trigger", and every stage must be in both.
    try:
        # published_stages() returns paths joined onto whatever root it was
        # given; normalise to the same repo-relative form used everywhere
        # here, or the two readers "disagree" about every file at once.
        published = {_rel(root, p) for p in published_stages(root)}
    except (OSError, ValueError):                        # pragma: no cover
        published = set(stages)
    for path in sorted(set(stages) - published):
        failures.append(
            "{0} is workflow_call-only here but wc_published_stages.py does "
            "not list it as published. The two readers disagree; reconcile "
            "them rather than trusting either.".format(path))
    for path in sorted(published - set(stages)):
        parsed = next((p for rel, _, p in loaded if rel == path), None)
        names = sorted(trigger_names(parsed or {}))
        if len(names) < 2:
            failures.append(
                "{0} is a published stage that this gate did not classify as "
                "workflow_call-only, and it does not have a second trigger to "
                "explain that. It is being scanned by nothing.".format(path))

    if not stages:
        # Same guard as Gate 7's `stages == 0` and Gate 26's empty listing: a
        # check whose subject vanished reports a success indistinguishable
        # from one that verified something.
        failures.append(
            "no workflow declares workflow_call as its only trigger, so this "
            "gate examined nothing. Either the published stages moved or "
            "discovery has broken; both are conditions to report, not pass.")
        return failures, stages, [], 0

    findings = []
    for path, source, _ in loaded:
        if path in stages:
            findings.extend(scan_text(path, source))

    waivers, waiver_failures = load_waivers(root)
    failures.extend(waiver_failures)
    shape_failures = check_waiver_shape(waivers)
    failures.extend(shape_failures)
    if shape_failures or waiver_failures:
        # A malformed register must not also produce a cascade of "nothing
        # matches" reports about the same entries.
        return failures, stages, findings, 0

    unwaived, stale = apply_waivers(findings, waivers, stages)
    failures.extend(stale)
    for finding in unwaived:
        _, message = (EXPRESSION_INVARIANTS.get(finding.check)
                      or (None, SECRETS_INHERIT_MESSAGE))
        failures.append(
            "{0}:{1}: `{2}` - this published stage {3}. If the deviation is "
            "deliberate, register it in {4} with a reason and a tracking "
            "issue; constitution VII does not accept a code comment.".format(
                finding.path, finding.line, finding.text, message,
                WAIVERS_PATH))
    return failures, stages, findings, len(findings) - len(unwaived)


# --------------------------------------------------------------------------
# Self-test
# --------------------------------------------------------------------------
CLEAN = """\
name: clean stage
on:
  workflow_call:
    inputs:
      issue-number:
        type: number
        required: true
jobs:
  go:
    runs-on: ubuntu-latest
    steps:
      # the wrapper reads github.event.issue.number and passes it in;
      # this stage never reads github.event.* or vars.* itself.
      - run: echo "${{ inputs.issue-number }}"
"""

EVENT_READ = """\
name: event reader
on:
  workflow_call:
jobs:
  go:
    runs-on: ubuntu-latest
    steps:
      - run: echo "${{ github.event.issue.number }}"
"""

VARS_READ = """\
name: vars reader
on:
  workflow_call:
jobs:
  go:
    runs-on: ubuntu-latest
    steps:
      - run: echo "$MODEL"
        env:
          MODEL: ${{ vars.WING_COMMANDER_SPEC_MODEL }}
"""

TWO_VARS_READS = """\
name: vars reader
on:
  workflow_call:
jobs:
  go:
    runs-on: ubuntu-latest
    steps:
      - run: echo "$MODEL"
        env:
          MODEL: ${{ vars.WING_COMMANDER_SPEC_MODEL }}
          OTHER: ${{ vars.WING_COMMANDER_PLAN_MODEL }}
"""

BARE_IF_VARS_READ = """\
name: bare if
on:
  workflow_call:
jobs:
  go:
    if: vars.WING_COMMANDER_PAUSED != 'true'
    runs-on: ubuntu-latest
    steps:
      - run: echo hi
"""

SECRETS_INHERIT = """\
name: inheritor
on:
  workflow_call:
jobs:
  go:
    uses: ./.github/workflows/clean.yml
    secrets: inherit
"""

WRAPPER = """\
name: wrapper
on:
  issue_comment:
    types: [created]
jobs:
  go:
    if: vars.WING_COMMANDER_PAUSED != 'true'
    runs-on: ubuntu-latest
    steps:
      - run: echo "${{ github.event.comment.id }}"
"""

MULTI_TRIGGER = """\
name: callable but also scheduled
on:
  workflow_call:
  schedule:
    - cron: "13 7 * * *"
jobs:
  go:
    runs-on: ubuntu-latest
    steps:
      - run: echo "${{ vars.SOMETHING }}"
"""

QUOTED_ON = """\
name: quoted on key
"on":
  workflow_call:
jobs:
  go:
    runs-on: ubuntu-latest
    steps:
      - run: echo "${{ vars.QUOTED_FORM }}"
"""

LIST_ON = """\
name: sequence on value
on: [workflow_call]
jobs:
  go:
    runs-on: ubuntu-latest
    steps:
      - run: echo "${{ vars.LIST_FORM }}"
"""

SCALAR_ON = """\
name: scalar on value
on: workflow_call
jobs:
  go:
    runs-on: ubuntu-latest
    steps:
      - run: echo "${{ vars.SCALAR_FORM }}"
"""

PROSE_ONLY = """\
name: prose only
on:
  workflow_call:
    inputs:
      trigger:
        type: string
        description: "resolved by the wrapper from github.event_name; the
          stage never reads github.event.* or vars.* directly"
jobs:
  go:
    runs-on: ubuntu-latest
    steps:
      # this stage never reads github.event.* and holds no vars.* read.
      # What an adopter writes in their WRAPPER, quoted here as guidance:
      #   MODEL: ${{ vars.WING_COMMANDER_SPEC_MODEL }}
      #   if: vars.WING_COMMANDER_PAUSED != 'true'
      #   secrets: inherit
      - run: |
          # neither does this shell comment: ${{ vars.NOT_A_READ }}
          echo "safe # ${{ inputs.trigger }}"
      - run: echo ok    # trailing: ${{ vars.NOT_A_READ_EITHER }}
"""


def _waiver(file, check, pattern, count):
    """A fixture waiver. `file` is a bare name; waivers name repo paths."""
    return {"file": WORKFLOWS_DIR + "/" + file, "check": check,
            "pattern": pattern, "count": count,
            "reason": "self-test fixture", "issue": "#149"}


FIXTURES = [
    # (name, {filename: source}, waivers or None, expected substring or None)
    ("a clean stage passes",
     {"clean.yml": CLEAN}, None, None),
    ("a github.event read is caught",
     {"clean.yml": CLEAN, "bad.yml": EVENT_READ}, None,
     "bad.yml:8: `github.event.issue.number`"),
    ("a vars.* read is caught",
     {"clean.yml": CLEAN, "bad.yml": VARS_READ}, None,
     "bad.yml:10: `vars.WING_COMMANDER_SPEC_MODEL`"),
    ("a vars.* read in a bare if: is caught",
     {"clean.yml": CLEAN, "bad.yml": BARE_IF_VARS_READ}, None,
     "bad.yml:6: `vars.WING_COMMANDER_PAUSED`"),
    ("secrets: inherit is caught",
     {"clean.yml": CLEAN, "bad.yml": SECRETS_INHERIT}, None,
     "bad.yml:7: `secrets: inherit`"),
    ("a wrapper may read github.event and vars",
     {"clean.yml": CLEAN, "wing-commander-1.yml": WRAPPER}, None, None),
    ("a workflow_call workflow with a second trigger is not a stage",
     {"clean.yml": CLEAN, "both.yml": MULTI_TRIGGER}, None, None),
    # discovery: each `on:` form must reach the scan. Every one of these
    # would pass vacuously if the form stopped being recognised, which is
    # why each fixture's stage carries a violation.
    ("a quoted \"on\" key is still discovered",
     {"clean.yml": CLEAN, "quoted.yml": QUOTED_ON}, None,
     "quoted.yml:8: `vars.QUOTED_FORM`"),
    ("a sequence `on: [workflow_call]` is still discovered",
     {"clean.yml": CLEAN, "seq.yml": LIST_ON}, None,
     "seq.yml:7: `vars.LIST_FORM`"),
    ("a scalar `on: workflow_call` is still discovered",
     {"clean.yml": CLEAN, "scalar.yml": SCALAR_ON}, None,
     "scalar.yml:7: `vars.SCALAR_FORM`"),
    ("comments and descriptions are not reads",
     {"prose.yml": PROSE_ONLY}, None, None),
    # the empty-subject guard
    ("a checkout with no stage at all is a failure, not a clean pass",
     {"wing-commander-1.yml": WRAPPER}, None,
     "gate examined nothing"),
    # the waiver machinery
    ("a matching waiver suppresses the finding",
     {"clean.yml": CLEAN, "bad.yml": VARS_READ},
     [_waiver("bad.yml", "vars", r"^vars\.WING_COMMANDER_[A-Z_]+$", 1)],
     None),
    ("the same read WITHOUT the waiver is caught",
     {"clean.yml": CLEAN, "bad.yml": VARS_READ}, [],
     "bad.yml:10: `vars.WING_COMMANDER_SPEC_MODEL`"),
    ("a waiver matching nothing is reported stale",
     {"clean.yml": CLEAN, "bad.yml": VARS_READ},
     [_waiver("bad.yml", "vars", r"^vars\.LONG_GONE$", 1)],
     "nothing matches it any more"),
    # the count, in both directions. Growth is the failure #149 measured;
    # shrinkage means the waiver is now wider than the deviation and would
    # silently cover the next read that reuses its shape.
    ("a waived deviation that GREW fails",
     {"clean.yml": CLEAN, "bad.yml": TWO_VARS_READS},
     [_waiver("bad.yml", "vars", r"^vars\.WING_COMMANDER_[A-Z_]+$", 1)],
     "2 match - MORE than the waiver was granted for"),
    ("a waiver wider than the deviation it covers fails",
     {"clean.yml": CLEAN, "bad.yml": VARS_READ},
     [_waiver("bad.yml", "vars", r"^vars\.WING_COMMANDER_[A-Z_]+$", 2)],
     "1 match - FEWER than the waiver was granted for"),
    ("a waiver naming a non-stage is reported",
     {"clean.yml": CLEAN, "wing-commander-1.yml": WRAPPER},
     [_waiver("wing-commander-1.yml", "vars", r"^vars\.", 1)],
     "is not a workflow_call-only stage"),
    ("a waiver missing its reason is refused",
     {"clean.yml": CLEAN, "bad.yml": VARS_READ},
     [{"file": WORKFLOWS_DIR + "/bad.yml", "check": "vars",
       "pattern": r"^vars\.", "count": 1, "issue": "#149"}],
     "is missing reason"),
    ("a waiver for an unknown check waives nothing and says so",
     {"clean.yml": CLEAN, "bad.yml": VARS_READ},
     [_waiver("bad.yml", "variables", r"^vars\.", 1)],
     "which is not one of"),
]


def _build(root, files, waivers):
    workflows = os.path.join(root, ".github", "workflows")
    os.makedirs(workflows)
    for name, source in files.items():
        with open(os.path.join(workflows, name), "w", encoding="utf-8",
                  newline="\n") as handle:
            handle.write(source)
    if waivers is not None:
        scripts = os.path.join(root, ".github", "scripts")
        os.makedirs(scripts)
        with open(os.path.join(scripts, "stage-invariant-waivers.json"), "w",
                  encoding="utf-8", newline="\n") as handle:
            json.dump({"waivers": waivers}, handle, indent=2)


def self_test():
    bad = 0
    for name, files, waivers, expect in FIXTURES:
        root = tempfile.mkdtemp(prefix="wc-stage-invariants-")
        try:
            _build(root, files, waivers)
            failures, _, _, _ = evaluate(root)
        finally:
            shutil.rmtree(root, ignore_errors=True)
        joined = " | ".join(failures)
        if expect is None:
            if failures:
                bad += 1
                print("[FAIL] {0}: expected a clean pass, got: {1}".format(
                    name, joined))
            else:
                print("[ok] {0}: clean".format(name))
        elif not failures:
            bad += 1
            print("[FAIL] {0}: expected a failure containing {1!r}, got a "
                  "clean pass".format(name, expect))
        elif expect not in joined:
            bad += 1
            print("[FAIL] {0}: failed for the WRONG reason. expected {1!r}, "
                  "got: {2}".format(name, expect, joined))
        else:
            print("[ok] {0}: caught".format(name))
    print("Gate 31 self-test: {0}/{1} fixtures behaved as specified.".format(
        len(FIXTURES) - bad, len(FIXTURES)))
    return 1 if bad else 0


def main():
    parser = argparse.ArgumentParser(
        description="Gate 31 - published stages read no ambient state")
    parser.add_argument("--self-test", action="store_true",
                        help="run the fixtures instead of this repository")
    parser.add_argument("--root", default=".",
                        help="repository root to scan (default: .)")
    args = parser.parse_args()

    if args.self_test:
        return self_test()

    if not os.path.isdir(os.path.join(args.root, *WORKFLOWS_DIR.split("/"))):
        # A gate that cannot reach its subject fails loudly (constitution
        # VIII): run from the wrong directory this would otherwise discover
        # zero stages and the empty-subject guard would blame the repository.
        print("::error::Gate 31: {0} does not exist under {1!r}. Run this "
              "from the repository root.".format(WORKFLOWS_DIR, args.root))
        return 1

    failures, stages, findings, waived = evaluate(args.root)
    for failure in failures:
        print("::error::Gate 31: {0}".format(failure))
    print("Gate 31: {0} workflow_call-only stage(s), {1} ambient read(s) "
          "found, {2} waived by {3}; {4} failure(s).".format(
              len(stages), len(findings), waived, WAIVERS_PATH,
              len(failures)))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
