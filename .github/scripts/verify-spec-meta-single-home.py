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
    origin ref's spec-meta.json (the idiom) — spelled with the literal file
    name in the path, or through a variable the same file assigns from a
    string naming spec-meta.json — outside the shared script and the one
    recorded exception below;
  * the shared script no longer contains that read (the gate would then be
    protecting nothing - update both together);
  * wing-commander-spec-meta or wing-commander-inspected-run-identity stops
    calling the shared script.

The one recorded exception (EXCEPTIONS, counted exactly): rebase.yml's
branch-selection loop reads every spec branch's spec-meta.json in one shell
loop. A published stage may not source _shared/ (spec 049 FR-022) and a
composite step cannot run per loop iteration, so that copy stays where it
is, with its own identity check, and this gate pins its count: a second
copy there fails, and so does the exception going stale.

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
# A `git show` of a branch's spec-meta.json: `origin/<branch>:<path>` or
# `refs/remotes/origin/...`, with or without quoting. The path is the idiom
# when it names spec-meta.json literally, or through a variable the same
# file assigns from a string that names it (rebase.yml's `$meta_path`).
SHOW_ORIGIN_RE = re.compile(r'git show\s+"?(?:refs/remotes/)?origin/[^\s"]*:([^\s"]*)')
META_VAR_ASSIGN_RE = re.compile(r'\b(\w+)=["\']?[^\n"\']*spec-meta\.json')
PATH_VAR_RE = re.compile(r'\$\{?(\w+)\}?')
# path -> (exact count, reason). Counted, never open-ended.
EXCEPTIONS = {
    ".github/workflows/rebase.yml": (
        1, "the branch-selection loop reads every spec branch in one shell loop; a "
           "published stage may not source _shared/ (spec 049 FR-022) and a composite "
           "cannot run per iteration"),
}


def idiom_lines(text):
    """-> [(line number, line)] of every `git show` of an origin ref's
    spec-meta.json in `text`, literal or variable-carried."""
    meta_vars = set(META_VAR_ASSIGN_RE.findall(text))
    out = []
    for n, line in enumerate(text.splitlines(), 1):
        if line.strip().startswith("#"):
            continue
        for m in SHOW_ORIGIN_RE.finditer(line):
            path = m.group(1)
            if "spec-meta.json" in path or any(v in meta_vars for v in PATH_VAR_RE.findall(path)):
                out.append((n, line))
                break
    return out


def contains_idiom(text):
    return bool(idiom_lines(text))


def _read(path):
    with io.open(path, encoding="utf-8") as fh:
        return fh.read()


def scan(root="."):
    failures = []
    shared = os.path.join(root, SHARED)
    if not os.path.isfile(shared):
        failures.append(f"{SHARED} is missing - it is the one home of the spec-meta read.")
    elif not contains_idiom(_read(shared)):
        failures.append(f"{SHARED} no longer contains the `git show` of a branch's "
                        f"spec-meta.json this gate protects; if the read moved, move "
                        f"this gate's SHARED with it.")

    files = (glob.glob(os.path.join(root, ".github/workflows/*.yml"))
             + glob.glob(os.path.join(root, ".github/workflows/*.yaml"))
             + glob.glob(os.path.join(root, ".github/actions/**/action.yml"), recursive=True)
             + glob.glob(os.path.join(root, ".github/actions/**/action.yaml"), recursive=True)
             + glob.glob(os.path.join(root, ".github/actions/_shared/*.sh")))
    seen_exceptions = set()
    for f in sorted(files):
        rel = os.path.relpath(f, root).replace("\\", "/")
        if rel == SHARED:
            continue
        hits = idiom_lines(_read(f))
        if rel in EXCEPTIONS:
            seen_exceptions.add(rel)
            want, reason = EXCEPTIONS[rel]
            if len(hits) != want:
                failures.append(
                    f"{rel}: {len(hits)} `git show` read(s) of a spec branch's "
                    f"spec-meta.json, but the recorded exception allows exactly {want} "
                    f"({reason}). A new copy belongs in {SHARED}; a removed one means "
                    f"the exception is stale - update EXCEPTIONS with the change. Lines: "
                    + ", ".join(str(n) for n, _ in hits))
            continue
        for n, line in hits:
            failures.append(
                f"{rel}:{n}: reads a spec branch's spec-meta.json with its own "
                f"`git show` - the one home is {SHARED} (source it from a composite) "
                f"or the wing-commander-spec-meta composite (from a workflow): "
                f"{line.strip()}")
    for rel in EXCEPTIONS:
        if rel not in seen_exceptions and os.path.isdir(os.path.join(root, ".github/workflows")):
            failures.append(f"{rel} is recorded as an exception but was not scanned - remove "
                            f"the entry if the file is gone.")

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

        # (b2) the idiom pasted with the file name carried by a variable
        carried = os.path.join(root, "carried")
        _copy_tree(carried)
        target = os.path.join(carried, ".github/workflows/tasks.yml")
        with io.open(target, "a", encoding="utf-8") as fh:
            fh.write('\n      - name: Fixture step\n'
                     '        run: |\n'
                     '          mp="$SPEC_DIR/spec-meta.json"\n'
                     '          stage=$(git show "refs/remotes/origin/${SPEC_PREFIX}$SLUG:$mp" | jq -r .stage)\n')
        got = scan(carried)
        if not any("workflows/tasks.yml" in g and "git show" in g for g in got):
            problems.append(f"a variable-carried `git show` of spec-meta.json in tasks.yml "
                            f"was NOT detected; got: {got}")

        # (b3) a second copy inside the counted exception
        second = os.path.join(root, "second")
        _copy_tree(second)
        target = os.path.join(second, ".github/workflows/rebase.yml")
        with io.open(target, "a", encoding="utf-8") as fh:
            fh.write('\n      - name: Fixture step\n'
                     '        run: |\n'
                     '          stage=$(git show "origin/$SPEC_PREFIX$SLUG:$SPEC_DIR/spec-meta.json" | jq -r .stage)\n')
        got = scan(second)
        if not any("rebase.yml" in g and "exactly 1" in g for g in got):
            problems.append(f"a second copy inside the counted exception (rebase.yml) was "
                            f"NOT detected; got: {got}")

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
    print("Gate 61 self-test: clean tree passes; a pasted copy (literal or "
          "variable-carried), a second copy inside the counted exception, and a "
          "dropped call each fail.")
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
