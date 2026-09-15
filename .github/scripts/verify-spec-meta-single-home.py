#!/usr/bin/env python3
"""Gate 61 - a spec branch's spec-meta.json is read in exactly one place.

The read "fetch the spec branch, `git show` its spec-meta.json, pull fields
out with jq" was pasted into implement.yml (both read-back steps), plan.yml,
tasks.yml and wing-commander-inspected-run-identity, and only the last copy
checked that the file identifies the directory it was read from (#340). The
one home is now `.github/actions/_shared/read-spec-meta.sh`; composites
source it, stage workflows reach it through the wing-commander-spec-meta
composite. This gate fails when:

  * any workflow or composite under .github/ carries its own `git show` of an
    origin ref's spec-meta.json (the idiom), outside the shared script;
  * the shared script no longer contains that read (the gate would then be
    protecting nothing - update both together);
  * wing-commander-spec-meta or wing-commander-inspected-run-identity stops
    calling the shared script.

Not the idiom, deliberately: rebase.yml's read of spec-meta.json at a BEFORE
sha (a historical revision, not a branch tip) and the `gh api .../contents/`
reads in tasks.yml / pr-conversation.yml (an API read with no checkout).

Self-test (--self-test): copies the real tree, then (a) passes it clean, (b)
pastes the idiom into a workflow and expects the failure to name that line,
(c) removes the composite's call to the script and expects a failure -
constitution VIII: a gate that cannot fail proves nothing.

Usage: python3 .github/scripts/verify-spec-meta-single-home.py [--self-test]
"""
import glob
import io
import os
import re
import shutil
import sys
import tempfile

SHARED = ".github/actions/_shared/read-spec-meta.sh"
CALL = "_shared/read-spec-meta.sh"
CONSUMERS = (
    ".github/actions/wing-commander-spec-meta/action.yml",
    ".github/actions/wing-commander-inspected-run-identity/action.yml",
)
# A `git show` of a branch's spec-meta.json: `origin/<branch>:<dir>/spec-meta.json`
# or `refs/remotes/origin/...`, with or without quoting.
IDIOM_RE = re.compile(r'git show\s+"?(?:refs/remotes/)?origin/[^\s"]*spec-meta\.json')


def _read(path):
    with io.open(path, encoding="utf-8") as fh:
        return fh.read()


def scan(root="."):
    failures = []
    shared = os.path.join(root, SHARED)
    if not os.path.isfile(shared):
        failures.append(f"{SHARED} is missing - it is the one home of the spec-meta read.")
    elif not IDIOM_RE.search(_read(shared)):
        failures.append(f"{SHARED} no longer contains the `git show` of a branch's "
                        f"spec-meta.json this gate protects; if the read moved, move "
                        f"this gate's SHARED with it.")

    files = (glob.glob(os.path.join(root, ".github/workflows/*.yml"))
             + glob.glob(os.path.join(root, ".github/workflows/*.yaml"))
             + glob.glob(os.path.join(root, ".github/actions/**/action.yml"), recursive=True)
             + glob.glob(os.path.join(root, ".github/actions/**/action.yaml"), recursive=True)
             + glob.glob(os.path.join(root, ".github/actions/_shared/*.sh")))
    for f in sorted(files):
        rel = os.path.relpath(f, root).replace("\\", "/")
        if rel == SHARED:
            continue
        for n, line in enumerate(_read(f).splitlines(), 1):
            if line.strip().startswith("#"):
                continue
            if IDIOM_RE.search(line):
                failures.append(
                    f"{rel}:{n}: reads a spec branch's spec-meta.json with its own "
                    f"`git show` - the one home is {SHARED} (source it from a composite) "
                    f"or the wing-commander-spec-meta composite (from a workflow): "
                    f"{line.strip()}")

    for consumer in CONSUMERS:
        p = os.path.join(root, consumer)
        if not os.path.isfile(p):
            failures.append(f"{consumer} is missing.")
        elif CALL not in _read(p):
            failures.append(f"{consumer} does not call {CALL} - it must read spec-meta.json "
                            f"through the shared script, not its own copy.")
    return failures


def _copy_tree(dst):
    for rel in (".github/workflows", ".github/actions"):
        shutil.copytree(rel, os.path.join(dst, rel))


def self_test():
    problems = []
    root = tempfile.mkdtemp(prefix="verify_spec_meta_home_")
    try:
        # (a) the real tree, clean
        clean = os.path.join(root, "clean")
        _copy_tree(clean)
        got = scan(clean)
        if got:
            problems.append("clean copy of the real tree FAILED: " + "; ".join(got))

        # (b) the idiom pasted back into a workflow
        pasted = os.path.join(root, "pasted")
        _copy_tree(pasted)
        target = os.path.join(pasted, ".github/workflows/plan.yml")
        with io.open(target, "a", encoding="utf-8") as fh:
            fh.write('\n# pasted-copy fixture\n'
                     '      - name: Fixture step\n'
                     '        run: |\n'
                     '          stage=$(git show "origin/$SPEC_PREFIX$SLUG:$SPEC_DIR/spec-meta.json" | jq -r .stage)\n')
        got = scan(pasted)
        if not any("workflows/plan.yml" in g and "git show" in g for g in got):
            problems.append(f"a pasted `git show` of spec-meta.json in plan.yml was NOT "
                            f"detected; got: {got}")

        # (c) the composite stops calling the shared script
        dropped = os.path.join(root, "dropped")
        _copy_tree(dropped)
        comp = os.path.join(dropped, CONSUMERS[0])
        text = _read(comp).replace(CALL, "_shared/some-other-script.sh")
        with io.open(comp, "w", encoding="utf-8") as fh:
            fh.write(text)
        got = scan(dropped)
        if not any(CONSUMERS[0] in g and "does not call" in g for g in got):
            problems.append(f"the composite dropping its call to {CALL} was NOT "
                            f"detected; got: {got}")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    for p in problems:
        print(f"::error::Gate 61 self-test: {p}")
    if problems:
        return 1
    print("Gate 61 self-test: clean tree passes; a pasted copy and a dropped "
          "call each fail.")
    return 0


def main(argv):
    if "--self-test" in argv:
        return self_test()
    failures = scan(".")
    for f in failures:
        print(f"::error::Gate 61: {f}")
    print(f"Gate 61: a spec branch's spec-meta.json is read in one place "
          f"({SHARED}); {len(failures)} failure(s).")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
