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

project-name.sh is the home of the rules and is not scanned. Every other
published stage workflow (on.workflow_call), every composite under
.github/actions/ and every shared script under .github/actions/_shared/ is
scanned (T046); a file absent from ALLOWED may hold no hit at all.
Exit 0 when the gate holds; 1 otherwise.
"""
import glob
import os
import re
import sys

from wc_published_stages import published_stages

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FIXTURES = os.path.join(ROOT, ".github", "scripts", "fixtures", "project-single-home")
HOME = ".github/actions/_shared/project-name.sh"

PATTERNS = {
    "root-spec-dir": re.compile(r"""(?:^|[\s"'(=])specs/\$\{?\{?\s*\w*(?:slug|SLUG)\w*"""),
    "root-specify": re.compile(r"""(?:^|[\s"'(=])\.specify/"""),
    "root-specs-scan": re.compile(r"\b(?:ls|find)\s+(?:-\w+\s+)*specs/"),
    "root-skill-path": re.compile(r"""(?:^|[\s"'(=])\.claude/skills/speckit-"""),
}

# file -> {pattern: hits allowed}. A hit is a documented root branch.
ALLOWED = {
    ".github/actions/_shared/read-spec-meta.sh": {"root-spec-dir": 1},
    # spec-dir-rel is project-relative by definition.
    ".github/actions/wing-commander-project/action.yml": {"root-spec-dir": 1},
    ".github/actions/wing-commander-inspected-run-identity/action.yml": {"root-spec-dir": 1},
    ".github/actions/wing-commander-context/action.yml": {"root-spec-dir": 1},
    # Two input-description lines name the artifacts in prose; the third
    # skill hit is the root branch's `ls -d` (the empty-project case).
    ".github/actions/wing-commander-preflight/action.yml": {
        "root-specify": 2, "root-skill-path": 3},
    # The two `case` arms that match a root `.specify/` script grant to
    # derive its P-prefixed twin (spec 114, FR-006).
    ".github/actions/wing-commander-tool-args/action.yml": {"root-specify": 2},
    # Each agent step's literal default-allowed-tools (Gate 27 reads it as a
    # literal list) grants the root-form `.specify/` scripts; tool-args adds
    # the project's twin, so the literal is the root branch.
    ".github/workflows/implement.yml": {"root-specify": 2},
    ".github/workflows/plan.yml": {"root-specify": 2},
    ".github/workflows/tasks.yml": {"root-specify": 2},
    # The project-guidance prose names "its .specify/" for a routed project.
    ".github/workflows/intake.yml": {"root-specify": 1},
    # rel_dir is the project-relative spec_dir spec-meta.json records.
    ".github/workflows/rebase.yml": {"root-spec-dir": 1},
    # Upgrades the adopter's root Spec Kit install, which is not a lifecycle
    # and has no project; a subfolder project's own upgrade is out of scope.
    ".github/workflows/auto-update-spec-kit.yml": {"root-specify": 12, "root-skill-path": 1},
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


def scope():
    """Repository-relative paths of every file this gate scans."""
    files = {os.path.relpath(p, ROOT) for p in published_stages(ROOT)}
    actions = os.path.join(ROOT, ".github", "actions")
    for pattern in ("*/action.yml", "*/action.yaml", "_shared/*.sh"):
        files |= {os.path.relpath(p, ROOT) for p in glob.glob(os.path.join(actions, pattern))}
    files.discard(HOME)
    return sorted(f.replace(os.sep, "/") for f in files)


def main():
    errors = []
    files = scope()
    for rel in ALLOWED:
        if rel not in files:
            errors.append(f"{rel}: has an allowance but is not in scope (stale entry)")
    for rel in files:
        allowed = ALLOWED.get(rel, {})
        with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
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
    print(f"verify-project-single-home: OK ({len(files)} file(s) in scope, {len(ALLOWED)} with allowances)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
