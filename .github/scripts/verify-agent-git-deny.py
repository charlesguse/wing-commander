#!/usr/bin/env python3
"""Gate 154 -- every agent spec 095 covers is denied `.git/**` (FR-018,
first mitigation).

WHY THIS EXISTS
---------------
The fixer, review-fixup, pr-conversation's act agents and the implement
agent hold Write/Edit over the checkout. Without a `.git/**` deny, any of
them can plant a hook (`.git/hooks/pre-push`) or a config value
(`core.hooksPath`, `url.<base>.insteadOf`) that a later git call in the
same job -- one holding the App token -- runs or obeys. The harness
enforces disallowed tools, so the deny is a real boundary (spec 095 Q3).
The hardened push (Gate 150) is the second mitigation, for plants that
arrive another way.

WHAT IT CHECKS
--------------
  1. Each wing-commander-tool-args call whose step-label is in
     DENY_LABELS (board-loop, which takes no adopter override) carries
     `Edit(.git/**)` and `Write(.git/**)` in its default-disallowed-tools,
     and each in BOUNDARY_LABELS (pr-conversation, a published stage) passes
     `.git/` in no-write-paths, which tool-args applies after any override.
  2. implement.yml carries the deny as an ENTRY of spec 090's one
     write-boundary definition, never as a second literal list: the
     `no-write-paths` input's default lists `.git/`; every
     wing-commander-tool-args call labelled in IMPLEMENT_LABELS passes
     `no-write-paths: ${{ inputs.no-write-paths }}`; and none of
     implement.yml's tool-args calls spells `.git/**` in its own
     default-disallowed-tools.
  3. This repository's own implement wrapper, whose fallback replaces that
     default when the repository variable is unset, keeps `.git/` in it.

--self-test runs the fixtures under fixtures/095-agent-git-deny/ and
mutations of the shipped workflows, and asserts each is caught.

NOTE ON GATE NUMBERING: this gate was first registered as Gate 146. It is
numbered 154, not 146: 141-146 were taken by spec 110's PR #982 and 147-148
by spec 112's PR #1003, which claimed them first among the open
lifecycle branches.

Usage: python3 .github/scripts/verify-agent-git-deny.py [--self-test]
"""
import os
import re
import sys

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
WORKFLOWS = os.path.join(ROOT, ".github", "workflows")
FIXTURES = os.path.join(HERE, "fixtures", "095-agent-git-deny")
TOOL_ARGS = "wing-commander-tool-args"
DENIES = ("Edit(.git/**)", "Write(.git/**)")
# board-loop is not a published stage: its tool-args calls take no adopter
# override, so the deny can sit in the defaults.
DENY_LABELS = {
    "board-loop.yml": ("board-loop.fixer", "board-loop.review-fixup"),
}
# pr-conversation is published: an adopter's disallowed-tools-override
# replaces the defaults wholesale, and an extra-allowed-tools entry is
# subtracted from them, so its deny goes through no-write-paths, which
# tool-args appends after both (code review of #990).
BOUNDARY_LABELS = {
    "pr-conversation.yml": ("pr-conversation.act", "pr-conversation.act.fold"),
}
IMPLEMENT = "implement.yml"
IMPLEMENT_LABELS = ("implement.cycle", "implement.retry")
WRAPPER = "wing-commander-5-implement.yml"
PASSTHROUGH = "${{ inputs.no-write-paths }}"
GIT_ENTRY = ".git/"


def tool_args_steps(doc):
    """(job, step) for every wing-commander-tool-args call in a document."""
    for job_id, job in ((doc or {}).get("jobs") or {}).items():
        for step in (job or {}).get("steps") or []:
            if isinstance(step, dict) and TOOL_ARGS in str(step.get("uses", "")):
                yield job_id, step


def _entries(csv):
    return [e.strip() for e in str(csv or "").split(",") if e.strip()]


def deny_problems(doc, name, labels):
    problems = []
    seen = set()
    for _job, step in tool_args_steps(doc):
        with_ = step.get("with") or {}
        label = str(with_.get("step-label", ""))
        if label not in labels:
            continue
        seen.add(label)
        have = _entries(with_.get("default-disallowed-tools"))
        for deny in DENIES:
            if deny not in have:
                problems.append("{0}: {1} does not deny {2} in default-disallowed-tools -- the "
                                "agent could plant a git hook or config (FR-018)".format(
                                    name, label, deny))
    for label in labels:
        if label not in seen:
            problems.append("{0}: no {1} call labelled {2!r} -- the covered agent moved out of "
                            "view".format(name, TOOL_ARGS, label))
    return problems


def boundary_problems(doc, name, labels):
    problems = []
    seen = set()
    for _job, step in tool_args_steps(doc):
        with_ = step.get("with") or {}
        label = str(with_.get("step-label", ""))
        if label not in labels:
            continue
        seen.add(label)
        entries = [e if e.endswith("/") else e + "/" for e in _entries(with_.get("no-write-paths"))]
        if GIT_ENTRY not in entries:
            problems.append("{0}: {1} does not carry {2} in no-write-paths -- an adopter's "
                            "disallowed-tools-override or extra-allowed-tools could reopen "
                            ".git/** (FR-018)".format(name, label, GIT_ENTRY))
    for label in labels:
        if label not in seen:
            problems.append("{0}: no {1} call labelled {2!r} -- the covered agent moved out of "
                            "view".format(name, TOOL_ARGS, label))
    return problems


def implement_problems(doc, name=IMPLEMENT):
    problems = []
    inputs = (((doc or {}).get("on") or (doc or {}).get(True) or {}).get("workflow_call")
              or {}).get("inputs") or {}
    default = (inputs.get("no-write-paths") or {}).get("default")
    if default is None:
        problems.append("{0}: no no-write-paths input default -- spec 090's one "
                        "write-boundary definition is gone".format(name))
    elif GIT_ENTRY not in [e if e.endswith("/") else e + "/" for e in _entries(default)]:
        problems.append("{0}: the no-write-paths default {1!r} has no {2} entry (FR-018)".format(
            name, default, GIT_ENTRY))
    seen = set()
    for _job, step in tool_args_steps(doc):
        with_ = step.get("with") or {}
        label = str(with_.get("step-label", ""))
        if any(".git/" in e for e in _entries(with_.get("default-disallowed-tools"))):
            problems.append("{0}: {1} spells a .git/ deny in its own default-disallowed-tools "
                            "-- a second literal list instead of an entry in no-write-paths "
                            "(spec 090 FR-003)".format(name, label))
        if label in IMPLEMENT_LABELS:
            seen.add(label)
            if str(with_.get("no-write-paths", "")).replace(" ", "") != PASSTHROUGH.replace(" ", ""):
                problems.append("{0}: {1} does not pass {2} to {3} -- its agent is not held to "
                                "the write boundary".format(name, label, PASSTHROUGH, TOOL_ARGS))
    for label in IMPLEMENT_LABELS:
        if label not in seen:
            problems.append("{0}: no {1} call labelled {2!r}".format(name, TOOL_ARGS, label))
    return problems


WRAPPER_FALLBACK_RE = re.compile(r"no-write-paths:\s*\$\{\{[^}]*\|\|\s*'([^']*)'\s*\}\}")


def wrapper_problems(text, name=WRAPPER):
    m = WRAPPER_FALLBACK_RE.search(text)
    if not m:
        return ["{0}: no `no-write-paths: ${{{{ vars... || '<fallback>' }}}}` line".format(name)]
    if GIT_ENTRY not in [e if e.endswith("/") else e + "/" for e in _entries(m.group(1))]:
        return ["{0}: the no-write-paths fallback {1!r} drops {2} (FR-018)".format(
            name, m.group(1), GIT_ENTRY)]
    return []


def _read(name, directory=WORKFLOWS):
    with open(os.path.join(directory, name), encoding="utf-8") as fh:
        return fh.read()


def check(texts):
    """`texts`: {workflow name: text} for every workflow this gate reads."""
    problems = []
    for name, labels in DENY_LABELS.items():
        problems += deny_problems(yaml.safe_load(texts[name]), name, labels)
    for name, labels in BOUNDARY_LABELS.items():
        problems += boundary_problems(yaml.safe_load(texts[name]), name, labels)
    problems += implement_problems(yaml.safe_load(texts[IMPLEMENT]))
    problems += wrapper_problems(texts[WRAPPER])
    return problems


def _shipped():
    return {n: _read(n) for n in list(DENY_LABELS) + list(BOUNDARY_LABELS) + [IMPLEMENT, WRAPPER]}


def run():
    problems = check(_shipped())
    for p in problems:
        print("::error::Gate 154: " + p)
    if problems:
        return 1
    print("Gate 154: every covered agent is denied .git/** -- implement through its "
          "no-write-paths boundary, the others in their disallowed tools.")
    return 0


def self_test():
    failures = []
    cases = (
        ("good-deny.yml", "deny", None),
        ("good-boundary.yml", "boundary", None),
        ("missing-deny.yml", "deny", "does not deny Write(.git/**)"),
        ("second-literal-list.yml", "boundary", "a second literal list"),
        ("boundary-without-git.yml", "boundary", "has no .git/ entry"),
        ("published-with-boundary.yml", "published", None),
        ("published-without-boundary.yml", "published", "does not carry .git/"),
    )
    for name, kind, expect in cases:
        doc = yaml.safe_load(_read(name, FIXTURES))
        if kind == "deny":
            got = deny_problems(doc, name, ("fixture.fixer",))
        elif kind == "published":
            got = boundary_problems(doc, name, ("fixture.act",))
        else:
            got = implement_problems(doc, name)
        if expect is None and got:
            failures.append("fixture {0} should pass: {1}".format(name, got))
        elif expect is not None and not any(expect in p for p in got):
            failures.append("fixture {0} not caught for {1!r}: {2}".format(name, expect, got))
        else:
            print("note: fixture {0}: {1}".format(name, got[0] if got else "passes"))
    shipped = _shipped()
    base = check(shipped)
    if base:
        failures += ["the shipped workflows already fail: " + p for p in base]

    def mutated(name, old, new):
        texts = dict(shipped)
        if old not in texts[name]:
            sys.exit("::error::Gate 154 self-test: {0!r} not in {1}".format(old, name))
        texts[name] = texts[name].replace(old, new, 1)
        return texts

    mutations = (
        ("the fixer loses its Write(.git/**) deny",
         mutated("board-loop.yml", ',Edit(.git/**),Write(.git/**)"', ',Edit(.git/**)"'),
         "does not deny Write(.git/**)"),
        ("pr-conversation.act loses its boundary entry",
         mutated("pr-conversation.yml", '          no-write-paths: ".git/"\n', ""),
         "pr-conversation.act does not carry .git/"),
        ("implement's boundary default drops .git/",
         mutated(IMPLEMENT, 'default: ".claude/,.git/"', 'default: ".claude/"'),
         "has no .git/ entry"),
        ("implement.cycle spells its own .git deny",
         mutated(IMPLEMENT, 'default-disallowed-tools: "WebSearch,WebFetch,ScheduleWakeup,'
                 'Monitor,SendMessage"', 'default-disallowed-tools: "WebSearch,WebFetch,'
                 'ScheduleWakeup,Monitor,SendMessage,Edit(.git/**)"'),
         "a second literal list"),
        ("the wrapper fallback drops .git/",
         mutated(WRAPPER, "|| '.claude/,.git/' }}", "|| '.claude/' }}"), "drops .git/"),
    )
    for label, texts, expect in mutations:
        got = check(texts)
        if any(expect in p for p in got):
            print("note: mutation caught ({0})".format(label))
        else:
            failures.append("mutation {0!r} not caught for {1!r}: {2}".format(label, expect, got))
    for f in failures:
        print("::error::Gate 154 self-test: " + f)
    if failures:
        return 1
    print("Gate 154 self-test: {0} fixture(s) and {1} mutation(s), each caught.".format(
        len(cases), len(mutations)))
    return 0


if __name__ == "__main__":
    sys.exit(self_test() if "--self-test" in sys.argv[1:] else run())
