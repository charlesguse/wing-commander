#!/usr/bin/env python3
"""Gate 90 — the FR-016 guarantee sentence (SC-006) is identical everywhere
it is stated (specs/060-self-redrive-concurrency
contracts/concurrency-groups.md "The guarantee").

WHY THIS EXISTS
---------------
The sentence describing this repository's one-board-item-in-flight
guarantee is stated in three places: board-loop.yml's own per-job
concurrency: comments, specs/057-autonomous-board-loop/contracts/
board-loop-workflow.md's "Concurrency" section, and
specs/060-self-redrive-concurrency/contracts/concurrency-groups.md itself
(the canonical source). A paraphrase drifting in any one of them is a
silent contract violation nothing else in the gate suite would catch --
CLAUDE.md's "repeated comment prose gets ONE canonical comment" applies
here in spirit (the sentence has one canonical SOURCE), but the sentence
itself is deliberately restated verbatim at each site rather than pointed
at, because a YAML comment cannot "-- see" a markdown file's prose the way
Gate 47 expects. This gate is the check that restatement did not drift.
"""
import os
import re
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONCURRENCY_GROUPS_MD = os.path.join(
    REPO_ROOT, "specs", "060-self-redrive-concurrency", "contracts", "concurrency-groups.md")
BOARD_LOOP_WORKFLOW_MD = os.path.join(
    REPO_ROOT, "specs", "057-autonomous-board-loop", "contracts", "board-loop-workflow.md")
BOARD_LOOP_YML = os.path.join(REPO_ROOT, ".github", "workflows", "board-loop.yml")

# board-loop.yml's per-job concurrency: blocks (select/triage/route/fix/
# review/readiness/prove-gate/prove) -- every one of them must carry this
# comment (T009).
EXPECTED_YAML_BLOCK_COUNT = 8


def _normalize(text):
    """Backticks are markdown-only (a YAML comment cannot carry them
    meaningfully); whitespace collapses so a different line-wrap reads as
    identical prose."""
    text = text.replace("`", "")
    return re.sub(r"\s+", " ", text).strip()


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def extract_blockquote_after_heading(text, heading):
    """The first '> '-prefixed paragraph appearing after `heading` in a
    markdown file's TEXT. Returns None if the heading or a following
    blockquote cannot be found."""
    idx = text.find(heading)
    if idx == -1:
        return None
    rest = text[idx:].splitlines()
    lines = []
    in_quote = False
    for line in rest:
        if line.startswith(">"):
            in_quote = True
            lines.append(line[1:].strip())
        elif in_quote:
            break
    if not lines:
        return None
    return _normalize(" ".join(lines))


def extract_yaml_guarantee_comments(text):
    """Every comment block immediately preceding a `concurrency:` key,
    at any indentation -- one per job's own per-job concurrency: block."""
    blocks = []
    buffer = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            buffer.append(stripped[1:].strip())
        elif re.match(r"^\s*concurrency:\s*$", line):
            if buffer:
                blocks.append(_normalize(" ".join(buffer)))
            buffer = []
        else:
            buffer = []
    return blocks


def run():
    failures = 0

    canonical_text = _read(CONCURRENCY_GROUPS_MD)
    canonical = extract_blockquote_after_heading(canonical_text, "## The guarantee")
    if canonical is None:
        print("::error::verify-concurrency-guarantee-statement: could not find "
              "'## The guarantee' blockquote in {0}.".format(CONCURRENCY_GROUPS_MD))
        return 1
    print("[ok] canonical sentence read from concurrency-groups.md")

    workflow_text = _read(BOARD_LOOP_WORKFLOW_MD)
    workflow_sentence = extract_blockquote_after_heading(workflow_text, "## Concurrency")
    if workflow_sentence is None:
        failures += 1
        print("::error::verify-concurrency-guarantee-statement: could not find "
              "a blockquote under '## Concurrency' in {0}.".format(BOARD_LOOP_WORKFLOW_MD))
    elif workflow_sentence != canonical:
        failures += 1
        print("::error::verify-concurrency-guarantee-statement: {0}'s own "
              "'## Concurrency' blockquote drifted from concurrency-groups.md's "
              "canonical sentence.\n  canonical: {1!r}\n  found:     {2!r}".format(
                  BOARD_LOOP_WORKFLOW_MD, canonical, workflow_sentence))
    else:
        print("[ok] board-loop-workflow.md's 'Concurrency' section matches the canonical sentence")

    yaml_text = _read(BOARD_LOOP_YML)
    yaml_blocks = extract_yaml_guarantee_comments(yaml_text)
    if len(yaml_blocks) != EXPECTED_YAML_BLOCK_COUNT:
        failures += 1
        print("::error::verify-concurrency-guarantee-statement: expected "
              "{0} per-job concurrency: comment block(s) in board-loop.yml, "
              "found {1}.".format(EXPECTED_YAML_BLOCK_COUNT, len(yaml_blocks)))
    for i, block in enumerate(yaml_blocks):
        if block != canonical:
            failures += 1
            print("::error::verify-concurrency-guarantee-statement: "
                  "board-loop.yml's concurrency: comment block #{0} drifted "
                  "from concurrency-groups.md's canonical sentence.\n"
                  "  canonical: {1!r}\n  found:     {2!r}".format(i, canonical, block))
    if yaml_blocks and all(b == canonical for b in yaml_blocks):
        print("[ok] all {0} of board-loop.yml's own concurrency: comment "
              "blocks match the canonical sentence".format(len(yaml_blocks)))

    print("verify-concurrency-guarantee-statement: {0} failure(s).".format(failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(run())
