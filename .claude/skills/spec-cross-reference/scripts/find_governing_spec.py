#!/usr/bin/env python3
"""Find which specs/NNN-*/ directory governs a set of changed files, and
list its FR-*/SC-* requirements, so a code review can cross-reference
findings against them (CLAUDE.md, "Working the issue board").

Usage:
    git diff --name-only main...HEAD | python3 find_governing_spec.py
    python3 find_governing_spec.py path/one path/two
"""
import glob
import io
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")


def changed_paths_from_args_or_stdin():
    if len(sys.argv) > 1:
        return [p.strip() for p in sys.argv[1:] if p.strip()]
    return [line.strip() for line in sys.stdin if line.strip()]


def governing_specs(changed_paths):
    """Ranks each specs/NNN-*/ directory by how many changed paths its own
    tasks.md/plan.md/contracts/*.md reference literally, highest first."""
    hits = {}
    for spec_doc in sorted(glob.glob("specs/*/tasks.md") + glob.glob("specs/*/plan.md")
                            + glob.glob("specs/*/contracts/*.md")):
        spec_dir = spec_doc.replace("\\", "/").split("/")[1]
        with open(spec_doc, encoding="utf-8") as fh:
            text = fh.read()
        for path in changed_paths:
            if path and path in text:
                hits.setdefault(spec_dir, set()).add(path)
    return sorted(hits.items(), key=lambda kv: -len(kv[1]))


def list_requirements(spec_dir):
    """Every FR-NNN/SC-NNN bullet's own first line, from that spec's spec.md."""
    path = "specs/{0}/spec.md".format(spec_dir)
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    return re.findall(r"^- \*\*(?:FR|SC)-\d+\*\*.*$", text, re.MULTILINE)


def main():
    changed_paths = changed_paths_from_args_or_stdin()
    if not changed_paths:
        print("no changed paths given", file=sys.stderr)
        sys.exit(1)

    ranked = governing_specs(changed_paths)
    if not ranked:
        print("no specs/*/ directory references any changed path -- "
              "this looks like a spec-less change; nothing to cross-reference.")
        return

    top_dir, matched = ranked[0]
    print("governing spec: specs/{0}/spec.md ({1} of {2} changed paths matched)".format(
        top_dir, len(matched), len(changed_paths)))
    # A path name shared with an unrelated spec's own worked examples is
    # noise; only a close second (same order of magnitude as the winner)
    # is worth a maintainer's attention as a second candidate.
    close_seconds = [d for d, m in ranked[1:] if len(m) >= max(2, len(matched) // 2)]
    if close_seconds:
        print("also a close match: {0}".format(
            ", ".join("specs/{0}".format(d) for d in close_seconds)))
    print()
    print("its FR-*/SC-* requirements:")
    for line in list_requirements(top_dir):
        print(" ", line.strip())


if __name__ == "__main__":
    main()
