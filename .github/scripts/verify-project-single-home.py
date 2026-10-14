#!/usr/bin/env python3
"""Gate: project-aware files hold no root-only path pattern (spec 114 FR-020).

A file converted for subfolder projects must reach the spec directory, the
Spec Kit state and the skills through the shared project logic
(`_shared/project-name.sh`, the `wing-commander-project` composite), never by
rebuilding a root-only path or splitting a name by hand. Five patterns count:

  root-spec-dir        a spec directory built as `specs/<any variable>`
  root-specify         a bare `.specify/` path (no project prefix before it)
  root-specs-scan      a `ls`/`find` over a bare `specs/`
  root-skill-path      a bare `.claude/skills/speckit-*` path
  inline-project-split a project or NNN-slug cut out of a slug, spec dir or
                       branch with `%/*`, `##*/`, `%specs/*` or `%%/specs/*`

A Windows separator reads as `/`.

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
    # Any variable or expression right after a bare `specs/` -- `$feature`,
    # `${name}`, `${{ inputs.x }}` -- not only one named like a slug.
    "root-spec-dir": re.compile(r"""(?:^|[\s"'(=])specs/\$(?:\{\{\s*|\{)?[A-Za-z_]"""),
    "root-specify": re.compile(r"""(?:^|[\s"'(=])\.specify/"""),
    "root-specs-scan": re.compile(r"\b(?:ls|find)\s+(?:-\w+\s+)*specs/"),
    "root-skill-path": re.compile(r"""(?:^|[\s"'(=])\.claude/skills/speckit-"""),
    # A lifecycle name split by hand (T066/MF-21): the project or the bare
    # NNN-slug cut out of a slug, spec dir or branch with `%/*`, `##*/`,
    # `%specs/*` or `%%/specs/*` instead of read by the parser.
    "inline-project-split": re.compile(
        r"\$\{\w*(?:slug|SLUG|spec_dir|SPEC_DIR|record_dir|branch|BRANCH)\w*(?:%/\*|##\*/|%specs/\*|%%/specs/\*)\}"),
}

# file -> {pattern: hits allowed}. A hit is a documented root branch.
ALLOWED = {
    # spec-dir-rel is project-relative by definition.
    ".github/actions/wing-commander-project/action.yml": {"root-spec-dir": 1},
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

# inline-project-split hits that cannot reach the parser: each sits in a job
# that runs before any pipeline checkout exists (a one-step pre-job whose
# outputs name the next job's concurrency group), or in the credential-free
# gate-suite job, where wing-commander-project's token-bearing callout may
# not run. Each validates the name's shape first, and the job that acts on
# the value re-reads it through wing-commander-project, which refuses any
# name the inline split would read differently.
INLINE_SPLIT_ALLOWED = {
    ".github/workflows/plan.yml": 2,              # resolve-spec
    ".github/workflows/tasks.yml": 6,             # resolve-spec x3
    ".github/workflows/cleanup.yml": 1,           # select
    ".github/workflows/pr-conversation.yml": 2,   # resolve-identity
    ".github/workflows/rebase.yml": 2,            # discover's per-branch loop
    ".github/workflows/implement.yml": 1,         # gate-suite-implement-cycle
}
for _rel, _n in INLINE_SPLIT_ALLOWED.items():
    ALLOWED.setdefault(_rel, {})["inline-project-split"] = _n


def scan(text):
    """{pattern: count} over non-comment lines of `text`."""
    counts = {name: 0 for name in PATTERNS}
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            continue
        # A Windows separator (`specs\$slug`, `.specify\`) is the same path.
        line = line.replace("\\\\", "/").replace("\\", "/")
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
            # reject-<pattern>[--<variant>].txt
            name = fname[len("reject-"):].rsplit(".", 1)[0].split("--", 1)[0]
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
