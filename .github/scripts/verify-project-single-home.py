#!/usr/bin/env python3
"""Gate: project-aware files hold no root-only path pattern (spec 114 FR-020).

A file converted for subfolder projects must reach the spec directory, the
Spec Kit state and the skills through the shared project logic
(`_shared/project-name.sh`, the `wing-commander-project` composite), never by
rebuilding a root-only path. Four patterns count as root-only:

  root-spec-dir   a spec directory built from a slug as `specs/<slug var>`
  root-specify    a bare `.specify/` path (no project prefix before it)
  root-specs-scan a `ls`/`find` over a bare `specs/`
  root-skill-path a bare `.claude/skills/speckit-*` path

Each converted file may keep a fixed number of hits (its documented root
branch: the empty-project case that must stay byte-identical); a hit beyond
that count fails. Reject fixtures under fixtures/project-single-home/ each
carry one pattern and must be caught; accept.txt must stay clean.

project-name.sh is the home of the rules and is not scanned. Scope is listed
in SCOPE below. T046 widens it to every stage workflow and
composite; until then a file not listed is not scanned.
Exit 0 when the gate holds; 1 otherwise.
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FIXTURES = os.path.join(ROOT, ".github", "scripts", "fixtures", "project-single-home")

PATTERNS = {
    "root-spec-dir": re.compile(r"""(?:^|[\s"'(=])specs/\$\{?\{?\s*\w*(?:slug|SLUG)\w*"""),
    "root-specify": re.compile(r"""(?:^|[\s"'(=])\.specify/"""),
    "root-specs-scan": re.compile(r"\b(?:ls|find)\s+(?:-\w+\s+)*specs/"),
    "root-skill-path": re.compile(r"""(?:^|[\s"'(=])\.claude/skills/speckit-"""),
}

# file -> {pattern: hits allowed}. A hit is a documented root branch.
SCOPE = {
    ".github/actions/_shared/read-spec-meta.sh": {"root-spec-dir": 1},
    # spec-dir-rel is project-relative by definition.
    ".github/actions/wing-commander-project/action.yml": {"root-spec-dir": 1},
    ".github/actions/wing-commander-inspected-run-identity/action.yml": {"root-spec-dir": 1},
    ".github/actions/wing-commander-context/action.yml": {"root-spec-dir": 1},
    # Two input-description lines name the artifacts in prose; the third
    # skill hit is the root branch's `ls -d` (the empty-project case).
    ".github/actions/wing-commander-preflight/action.yml": {
        "root-specify": 2, "root-skill-path": 3},
}


def scan(text):
    """{pattern: count} over non-comment lines of `text`."""
    counts = {name: 0 for name in PATTERNS}
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            continue
        for name, rx in PATTERNS.items():
            if rx.search(line):
                counts[name] += 1
    return counts


def main():
    errors = []
    for rel, allowed in SCOPE.items():
        path = os.path.join(ROOT, rel)
        if not os.path.isfile(path):
            errors.append(f"{rel}: in scope but missing")
            continue
        with open(path, encoding="utf-8") as fh:
            counts = scan(fh.read())
        for name, n in counts.items():
            if n > allowed.get(name, 0):
                errors.append(
                    f"{rel}: {n} {name} hit(s), {allowed.get(name, 0)} allowed -- "
                    "route it through _shared/project-name.sh / wing-commander-project")
    caught = set()
    for fname in sorted(os.listdir(FIXTURES)):
        with open(os.path.join(FIXTURES, fname), encoding="utf-8") as fh:
            counts = scan(fh.read())
        hits = {name for name, n in counts.items() if n}
        if fname == "accept.txt":
            if hits:
                errors.append(f"fixture accept.txt wrongly flagged: {sorted(hits)}")
        elif fname.startswith("reject-"):
            name = fname[len("reject-"):].rsplit(".", 1)[0]
            if name not in hits:
                errors.append(f"fixture {fname} was not caught as {name}")
            caught |= hits
    for name in PATTERNS:
        if name not in caught:
            errors.append(f"pattern {name} has no reject fixture that catches it")
    if errors:
        print("verify-project-single-home: FAIL")
        for e in errors:
            print("  " + e)
        return 1
    print(f"verify-project-single-home: OK ({len(SCOPE)} file(s) in scope)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
