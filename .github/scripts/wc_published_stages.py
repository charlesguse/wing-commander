#!/usr/bin/env python3
"""The set of published stages, derived once.

A "published stage" is any workflow declaring `on.workflow_call` — that is
what makes it callable by an adopter, and therefore what makes it something
this repository must lint, bind and release as part of its public surface.

WHY THIS IS A FILE RATHER THAN A LIST
-------------------------------------
Issue #149: release.yml's actionlint gate carried a hardcoded list of stage
files. watchdog.yml and auto-update-spec-kit.yml were not on it, so they went
unlinted for an entire release while the gate reported success. The failure is
not that someone forgot to edit a list — it is that a list makes forgetting
invisible, and a new stage is born exempt.

lint-workflows.yml gate 7 already derives the set instead, and says so in its
comment. This module exists so the release gate can use the SAME derivation
rather than a second approximation of it. The first attempt at that was a
shell grep for `^  workflow_call:`, which reintroduced the original defect in
a subtler form: it silently misses a stage written in flow style
(`on: {workflow_call: ...}`), with a quoted key, or at a different
indentation, and since such a stage's `deployment:` lines would go uncounted
too, the gate's own diagnostics-vs-bindings balance check would still pass.
A YAML parse cannot be fooled that way.

verify-gate-7.py asserts that this module and gate 7's inline derivation
agree on the real repository, so the two cannot drift apart in silence.

Usage:
  python3 .github/scripts/wc_published_stages.py     # one path per line
  from wc_published_stages import published_stages   # as a list
"""
import glob
import os
import sys

import yaml


def published_stages(root="."):
    """Sorted paths of every workflow declaring on.workflow_call."""
    found = []
    pattern = os.path.join(root, ".github", "workflows")
    for path in sorted(glob.glob(os.path.join(pattern, "*.yml"))
                       + glob.glob(os.path.join(pattern, "*.yaml"))):
        try:
            wf = yaml.safe_load(open(path, encoding="utf-8")) or {}
        except yaml.YAMLError:
            # Not this module's job to report — the YAML/bash guard rail and
            # actionlint both do, with better messages. Skipping keeps a
            # malformed file from taking the whole derivation down.
            continue
        # PyYAML resolves the bare key `on` to the boolean True (YAML 1.1);
        # a quoted "on" stays a string. Accept either — same as gate 7.
        on = wf.get(True, wf.get("on"))
        # Membership, not truthiness: a bare `workflow_call:` parses to None,
        # and a stage with no inputs yet is still a stage. The scalar form
        # (`on: workflow_call`) is equally valid YAML for the same
        # declaration - missing it made this reader disagree with Gate 31's
        # about any stage written that way (#245 blind spot 3).
        if (isinstance(on, dict) and "workflow_call" in on) or \
           (isinstance(on, list) and "workflow_call" in on) or \
           (isinstance(on, str) and on == "workflow_call"):
            # Forward slashes and no "./" prefix: callers compare these paths
            # as strings against hand-written lists (release.yml's shellcheck
            # opt-in), and "./x" != "x" would make every such comparison miss
            # silently.
            rel = path.replace(os.sep, "/")
            found.append(rel[2:] if rel.startswith("./") else rel)
    return found


def main():
    # LF regardless of platform. The caller reads this with bash `mapfile`,
    # which does not strip a trailing CR, so on Windows the default CRLF
    # translation yields paths like "…/rebase.yml\r" that no longer exist.
    # Irrelevant on the runner; the point is that a maintainer verifying this
    # gate locally sees what CI sees rather than a phantom failure.
    try:
        sys.stdout.reconfigure(newline="\n")
    except (AttributeError, ValueError):
        pass
    stages = published_stages()
    if not stages:
        # An empty derivation must never read as "nothing to check" — that is
        # how a gate passes by doing nothing at all (gate 7 carries the same
        # guard for the same reason).
        print("::error::no workflow declares on.workflow_call. Either the "
              "published stages moved or this derivation has broken; either "
              "way the caller is about to check nothing.", file=sys.stderr)
        return 1
    print("\n".join(stages))
    return 0


if __name__ == "__main__":
    sys.exit(main())
