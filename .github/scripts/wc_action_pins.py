#!/usr/bin/env python3
"""Bump SHA-pinned third-party actions to their newest release, with the
runtime-register rows each bump needs (specs/132 FR-009b, FR-017a).

WHY THIS EXISTS
---------------
Actions outside the trusted-publisher set (its one home is the
`unpinned-uses` policy in .github/zizmor.yml) are pinned to a full commit
SHA with a `# vX.Y.Z` comment naming the release. A SHA never moves, so
without automation those pins only age. Dependabot (.github/dependabot.yml,
owner decision on #890 for FR-009b) opens the bump pull requests, rewriting
each SHA and its version comment together; a human merges them (no bot
merge class). Dependabot cannot write Gate 170's registers, so the human
runs `--write` on the bump branch before merging (FR-017a).

Gate 170 (verify-action-runtime-pins.py) keys its register on the full
`uses:` string, so a bump that rewrites only the workflow line fails it.
`sync_rows` (`--write`) repairs the registers after such a bump. `apply`
(`--bump --write`) does the bump itself and rewrites three things together:
  * every `uses: <action>@<old-sha> # <old-tag>` line, SHA and comment;
  * .github/scripts/action-runtime-pins.json: the new ref's row (the
    runtime read from the action's own action.yml at the new SHA) replaces
    the old one;
  * .github/scripts/action-runtime-waivers.json: a waiver for the old ref
    moves to the new ref while the new runtime is still deprecated, and is
    dropped once it is not (Gate 170 fails a stale waiver).

Only lines already in the SHA-plus-comment form are touched, so trusted
publishers on tags are never rewritten and this module needs no copy of
the trusted-publisher list (FR-009a).

Usage:
    # On a Dependabot bump PR: add the new refs' rows, drop the old ones.
    python3 .github/scripts/wc_action_pins.py --write
    # By hand: report, or apply, a bump of every SHA pin to its newest release.
    python3 .github/scripts/wc_action_pins.py --bump [--write] [--summary FILE]
Imported by verify-action-runtime-pins.py, whose --self-test runs
`self_test_cases` (the SC-010 bump fixture).
"""
import argparse
import glob
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

PINS_PATH = ".github/scripts/action-runtime-pins.json"
WAIVERS_PATH = ".github/scripts/action-runtime-waivers.json"
DEPRECATED = ("node12", "node16", "node20")
PIN_RE = re.compile(
    r"^(?P<lead>[ \t]*(?:-[ \t]+)?uses:[ \t]*)"
    r"(?P<action>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_./-]+)?)"
    r"@(?P<sha>[0-9a-f]{40})[ \t]+#[ \t]*(?P<tag>v?[0-9]+(?:\.[0-9]+)*)[ \t]*$",
    re.M)
RELEASE_TAG_RE = re.compile(r"^v?([0-9]+)\.([0-9]+)\.([0-9]+)$")


def _here():
    return os.path.dirname(os.path.abspath(__file__))


def _files(root):
    return sorted(
        glob.glob(os.path.join(root, ".github", "workflows", "*.yml"))
        + glob.glob(os.path.join(root, ".github", "workflows", "*.yaml"))
        + glob.glob(os.path.join(root, ".github", "actions", "**", "action.yml"),
                    recursive=True)
        + glob.glob(os.path.join(root, ".github", "actions", "**", "action.yaml"),
                    recursive=True))


def _read(path):
    with io.open(path, encoding="utf-8") as fh:
        return fh.read()


def _write(path, text):
    with io.open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def find_pins(root="."):
    """-> {(action, sha, tag): [repo-relative file, ...]}."""
    out = {}
    for path in _files(root):
        rel = os.path.relpath(path, root).replace(os.sep, "/")
        for m in PIN_RE.finditer(_read(path)):
            key = (m.group("action"), m.group("sha"), m.group("tag"))
            out.setdefault(key, []).append(rel)
    return out


def _version(tag):
    m = RELEASE_TAG_RE.match(tag)
    return tuple(int(x) for x in m.groups()) if m else None


def remote_tags(repo):
    """{tag: commit sha} for owner/repo, the peeled commit of an annotated
    tag preferred. Read with `git ls-remote`, which needs no token."""
    proc = subprocess.run(
        ["git", "ls-remote", "--tags", "https://github.com/{0}".format(repo)],
        capture_output=True, text=True, timeout=120)
    if proc.returncode != 0:
        raise RuntimeError("git ls-remote {0} failed: {1}".format(
            repo, proc.stderr.strip()))
    tags = {}
    for line in proc.stdout.splitlines():
        sha, _, ref = line.partition("\t")
        if not ref.startswith("refs/tags/"):
            continue
        name = ref[len("refs/tags/"):]
        if name.endswith("^{}"):
            tags[name[:-3]] = sha
        else:
            tags.setdefault(name, sha)
    return tags


def newest_release(tags):
    """-> (tag, sha) of the highest vX.Y.Z tag, or None."""
    best = None
    for tag, sha in tags.items():
        v = _version(tag)
        if v is not None and (best is None or v > best[0]):
            best = (v, tag, sha)
    return (best[1], best[2]) if best else None


def _gate170():
    spec = importlib.util.spec_from_file_location(
        "verify_action_runtime_pins",
        os.path.join(_here(), "verify-action-runtime-pins.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def remote_runtime(pin):
    """runs.using at that ref -- Gate 170's own reader, its one home."""
    return _gate170().remote_runtime(pin)


def plan(root=".", tags_of=remote_tags):
    """-> [bump] where bump = dict(action, old_sha, old_tag, new_sha,
    new_tag, files). An action whose newest release is the pinned one, or
    older, is left alone."""
    bumps = []
    for (action, sha, tag), files in sorted(find_pins(root).items()):
        repo = "/".join(action.split("/")[:2])
        newest = newest_release(tags_of(repo))
        if newest is None:
            continue
        new_tag, new_sha = newest
        cur = _version(tag)
        if new_sha == sha or (cur is not None and _version(new_tag) <= cur):
            continue
        bumps.append({"action": action, "old_sha": sha, "old_tag": tag,
                      "new_sha": new_sha, "new_tag": new_tag,
                      "files": sorted(set(files))})
    return bumps


def apply(root, bumps, runtime_of=remote_runtime):
    """Rewrite the pins and both Gate 170 registers. -> [note] lines."""
    notes = []
    pins_path = os.path.join(root, PINS_PATH)
    waivers_path = os.path.join(root, WAIVERS_PATH)
    pins_doc = json.loads(_read(pins_path))
    waivers_doc = json.loads(_read(waivers_path))
    for b in bumps:
        old = "{0}@{1}".format(b["action"], b["old_sha"])
        new = "{0}@{1}".format(b["action"], b["new_sha"])
        line_re = re.compile(
            r"^(?P<lead>[ \t]*(?:-[ \t]+)?uses:[ \t]*)" + re.escape(old)
            + r"[ \t]+#[ \t]*" + re.escape(b["old_tag"]) + r"[ \t]*$", re.M)
        for rel in b["files"]:
            path = os.path.join(root, rel)
            text = _read(path)
            _write(path, line_re.sub(
                lambda m: "{0}{1} # {2}".format(m.group("lead"), new, b["new_tag"]),
                text))
        runtime = runtime_of(new)
        if not runtime:
            raise RuntimeError("could not read runs.using of {0}".format(new))
        pins_doc["pins"].pop(old, None)
        pins_doc["pins"][new] = runtime
        kept = []
        for w in waivers_doc.get("waivers", []):
            if w.get("uses") == old:
                if runtime in DEPRECATED:
                    w["uses"] = new
                    kept.append(w)
                    notes.append("{0} {1} still declares {2}; its waiver "
                                 "moved to the new ref.".format(
                                     b["action"], b["new_tag"], runtime))
                else:
                    notes.append("{0} {1} declares {2}; its deprecated-"
                                 "runtime waiver was dropped.".format(
                                     b["action"], b["new_tag"], runtime))
            else:
                kept.append(w)
        waivers_doc["waivers"] = kept
        if runtime in DEPRECATED and not any(
                w.get("uses") == new for w in kept):
            notes.append("{0} {1} declares {2} with no waiver: Gate 170 "
                         "fails this PR until one is added or the bump is "
                         "dropped.".format(b["action"], b["new_tag"], runtime))
        notes.append("{0}: {1} -> {2} ({3}), runtime {4}.".format(
            b["action"], b["old_tag"], b["new_tag"], b["new_sha"], runtime))
    pins_doc["pins"] = dict(sorted(pins_doc["pins"].items()))
    _write(pins_path, json.dumps(pins_doc, indent=2, ensure_ascii=False) + "\n")
    _write(waivers_path,
           json.dumps(waivers_doc, indent=2, ensure_ascii=False) + "\n")
    return notes


def sync_rows(root, runtime_of=remote_runtime):
    """Bring both Gate 170 registers in line with the pins as they stand --
    the step a Dependabot bump pull request needs, since Dependabot rewrites
    the SHA and its comment but not the registers. A pin in use with no row
    gets one (runs.using read at that ref); a row nothing uses is dropped; a
    waiver for a ref nothing uses moves to the same action's new ref while
    that ref's runtime is still deprecated, and is dropped otherwise.
    -> [note] lines."""
    found, failures = _gate170().discover(root)
    if failures:
        raise RuntimeError("; ".join(failures))
    pins_path = os.path.join(root, PINS_PATH)
    waivers_path = os.path.join(root, WAIVERS_PATH)
    pins_doc = json.loads(_read(pins_path))
    waivers_doc = json.loads(_read(waivers_path))
    rows = pins_doc["pins"]
    notes, added = [], []
    for pin in sorted(found):
        if pin not in rows:
            runtime = runtime_of(pin)
            if not runtime:
                raise RuntimeError("could not read runs.using of {0}".format(pin))
            rows[pin] = runtime
            added.append(pin)
            notes.append("added the row {0}: {1}.".format(pin, runtime))
    for pin in sorted(set(rows) - set(found)):
        del rows[pin]
        notes.append("dropped the row for {0}, which nothing uses.".format(pin))
    kept = []
    for w in waivers_doc.get("waivers", []):
        if w.get("uses") in found:
            kept.append(w)
            continue
        action = str(w.get("uses", "")).split("@", 1)[0]
        successor = [p for p in added if p.split("@", 1)[0] == action
                     and rows[p] in DEPRECATED]
        if len(successor) == 1 and not any(
                k.get("uses") == successor[0] for k in kept):
            notes.append("moved the waiver for {0} to {1}, which still "
                         "declares {2}.".format(w["uses"], successor[0],
                                                rows[successor[0]]))
            w["uses"] = successor[0]
            kept.append(w)
        else:
            notes.append("dropped the waiver for {0}, which nothing uses."
                         .format(w.get("uses")))
    waivers_doc["waivers"] = kept
    pins_doc["pins"] = dict(sorted(rows.items()))
    _write(pins_path, json.dumps(pins_doc, indent=2, ensure_ascii=False) + "\n")
    _write(waivers_path,
           json.dumps(waivers_doc, indent=2, ensure_ascii=False) + "\n")
    return notes


def summary(bumps, notes):
    lines = ["Bumps the SHA-pinned third-party actions to their newest "
             "release (specs/132 FR-009b). Each pin's SHA and `# vX.Y.Z` "
             "comment change together, with the Gate 170 runtime rows the "
             "new refs need.", "",
             "Merge by hand after review: a major-version bump can change an "
             "action's inputs. No automation merges this pull request.", ""]
    for b in bumps:
        lines.append("- `{0}` {1} -> {2} in {3}".format(
            b["action"], b["old_tag"], b["new_tag"], ", ".join(b["files"])))
    if notes:
        lines += ["", "Notes:", ""] + ["- " + n for n in notes]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- self-test

SHA_A = "a" * 40
SHA_B = "b" * 40


def _copy_tree(root):
    d = tempfile.mkdtemp(prefix="wc-action-pins-")
    for sub in (".github/workflows", ".github/actions"):
        src = os.path.join(root, sub)
        if os.path.isdir(src):
            shutil.copytree(src, os.path.join(d, sub))
    os.makedirs(os.path.join(d, ".github", "scripts"))
    for rel in (PINS_PATH, WAIVERS_PATH, ".github/zizmor.yml",
                ".github/scripts/zizmor-pin.txt",
                ".github/scripts/zizmor-findings-waivers.json"):
        if os.path.isfile(os.path.join(root, rel)):
            shutil.copy(os.path.join(root, rel), os.path.join(d, rel))
    return d


def self_test_cases(root="."):
    """-> [(label, ok, detail)]. Hermetic: tags and runtimes are injected,
    never read from the network."""
    gate = _gate170()
    out = []

    def check(label, ok, detail=""):
        out.append((label, bool(ok), detail))

    # SC-010: rewrite one real pin to another SHA and comment, with its
    # register rows, on a copy of the shipped tree; Gate 170 (and Gate 178
    # when the pinned analyser is installed) must still pass.
    pins = find_pins(root)
    if not pins:
        check("the shipped tree has a SHA-pinned action to bump", False,
              "find_pins found none")
        return out
    (action, sha, tag), _ = sorted(pins.items())[0]
    old = "{0}@{1}".format(action, sha)
    gate_runtime = json.loads(_read(os.path.join(root, PINS_PATH)))["pins"].get(old)
    new_tag = "v999.0.0"
    new_sha = SHA_B if sha != SHA_B else SHA_A

    def tags_of(repo):
        return {tag: sha, new_tag: new_sha, "v999.1.0-rc.1": "c" * 40}

    d = _copy_tree(root)
    try:
        bumps = plan(d, tags_of)
        target = [b for b in bumps if b["action"] == action and b["old_sha"] == sha]
        check("plan picks the newest release tag, ignoring a pre-release",
              target and target[0]["new_tag"] == new_tag,
              repr(target))
        bumps = target
        apply(d, bumps, lambda pin: gate_runtime)
        new = "{0}@{1}".format(action, bumps[0]["new_sha"]) if bumps else ""
        _, failures = gate.run(d)
        check("a bump with its register rows passes Gate 170", not failures,
              "; ".join(failures))
        text = "".join(_read(os.path.join(d, f)) for f in bumps[0]["files"]) \
            if bumps else ""
        check("the SHA and the version comment change together",
              "{0} # {1}".format(new, new_tag) in text and old not in text,
              new)
        zz = _zizmor_gate()
        if zz is not None and shutil.which("zizmor"):
            got = [g for g in zz.evaluate(d) if "unpinned-uses" in g
                   or "stale record" in g]
            check("the bumped tree passes Gate 178's pin policy", not got,
                  "; ".join(got))
    finally:
        shutil.rmtree(d, ignore_errors=True)

    # The same rewrite without the register rows fails Gate 170.
    d = _copy_tree(root)
    try:
        bumps = [b for b in plan(d, tags_of)
                 if b["action"] == action and b["old_sha"] == sha]
        for rel in bumps[0]["files"] if bumps else []:
            p = os.path.join(d, rel)
            _write(p, _read(p).replace(old, "{0}@{1}".format(
                action, bumps[0]["new_sha"])))
        _, failures = gate.run(d)
        check("the same rewrite without its rows fails Gate 170",
              any("has no row" in f for f in failures), "; ".join(failures))
    finally:
        shutil.rmtree(d, ignore_errors=True)

    # Waiver handling, and a bump to a deprecated runtime staying caught.
    for label, runtime, want_waiver_kept in (
            ("a waiver moves with a bump whose runtime is still deprecated",
             "node20", True),
            ("a waiver is dropped once the new runtime is not deprecated",
             "node24", False)):
        d = tempfile.mkdtemp(prefix="wc-action-pins-")
        try:
            os.makedirs(os.path.join(d, ".github", "workflows"))
            os.makedirs(os.path.join(d, ".github", "scripts"))
            _write(os.path.join(d, ".github", "workflows", "w.yml"),
                   "on: push\njobs:\n  j:\n    runs-on: ubuntu-latest\n"
                   "    steps:\n      - uses: o/r@{0} # v1.0.0\n".format(SHA_A))
            _write(os.path.join(d, PINS_PATH), json.dumps(
                {"pins": {"o/r@" + SHA_A: "node20"}}))
            _write(os.path.join(d, WAIVERS_PATH), json.dumps({"waivers": [
                {"uses": "o/r@" + SHA_A, "issue": "#889", "reason": "r"}]}))
            bumps = plan(d, lambda repo: {"v1.0.0": SHA_A, "v2.0.0": SHA_B})
            apply(d, bumps, lambda pin: runtime)
            w = json.loads(_read(os.path.join(d, WAIVERS_PATH)))["waivers"]
            _, failures = gate.run(d)
            check(label, ([x["uses"] for x in w] == ["o/r@" + SHA_B])
                  == want_waiver_kept and not failures, "; ".join(failures))
            if runtime == "node20":
                _write(os.path.join(d, WAIVERS_PATH), json.dumps({"waivers": []}))
                _, failures = gate.run(d)
                check("Gate 170 still fails a bump to a deprecated runtime "
                      "with no waiver",
                      any("deprecated runtime" in f for f in failures),
                      "; ".join(failures))
        finally:
            shutil.rmtree(d, ignore_errors=True)

    # A Dependabot-shaped bump (SHA and comment rewritten, registers not):
    # Gate 170 fails it; sync_rows (`--write`) repairs both registers and
    # Gate 170 then passes.
    for label, runtime, want_waivers in (
            ("--write after a Dependabot bump adds the new row, drops the "
             "old one and moves the waiver to a still-deprecated ref",
             "node20", ["o/r@" + SHA_B]),
            ("--write after a Dependabot bump drops the waiver once the new "
             "ref is not deprecated", "node24", [])):
        d = tempfile.mkdtemp(prefix="wc-action-pins-")
        try:
            os.makedirs(os.path.join(d, ".github", "workflows"))
            os.makedirs(os.path.join(d, ".github", "scripts"))
            _write(os.path.join(d, ".github", "workflows", "w.yml"),
                   "on: push\njobs:\n  j:\n    runs-on: ubuntu-latest\n"
                   "    steps:\n      - uses: actions/checkout@v5\n"
                   "      - uses: o/r@{0} # v2.0.0\n".format(SHA_B))
            _write(os.path.join(d, PINS_PATH), json.dumps({"pins": {
                "actions/checkout@v5": "node24", "o/r@" + SHA_A: "node20"}}))
            _write(os.path.join(d, WAIVERS_PATH), json.dumps({"waivers": [
                {"uses": "o/r@" + SHA_A, "issue": "#889", "reason": "r"}]}))
            _, before = gate.run(d)
            asked = []
            sync_rows(d, lambda pin: asked.append(pin) or runtime)
            rows = json.loads(_read(os.path.join(d, PINS_PATH)))["pins"]
            w = [x["uses"] for x in json.loads(
                _read(os.path.join(d, WAIVERS_PATH)))["waivers"]]
            _, after = gate.run(d)
            check(label, any("wc_action_pins.py --write" in f for f in before)
                  and asked == ["o/r@" + SHA_B]
                  and sorted(rows) == ["actions/checkout@v5", "o/r@" + SHA_B]
                  and w == want_waivers and not after,
                  "before {0}; asked {1}; rows {2}; waivers {3}; after {4}"
                  .format(before, asked, rows, w, after))
        finally:
            shutil.rmtree(d, ignore_errors=True)

    # A pin already on its newest release, and a tag-pinned trusted action,
    # are left alone.
    d = tempfile.mkdtemp(prefix="wc-action-pins-")
    try:
        os.makedirs(os.path.join(d, ".github", "workflows"))
        _write(os.path.join(d, ".github", "workflows", "w.yml"),
               "on: push\njobs:\n  j:\n    runs-on: ubuntu-latest\n"
               "    steps:\n      - uses: actions/checkout@v5\n"
               "      - uses: o/r@{0} # v2.0.0\n".format(SHA_B))
        check("an up-to-date pin and a tag pin are left alone",
              plan(d, lambda repo: {"v1.0.0": SHA_A, "v2.0.0": SHA_B}) == [])
    finally:
        shutil.rmtree(d, ignore_errors=True)
    return out


def _zizmor_gate():
    path = os.path.join(_here(), "verify-zizmor.py")
    if not os.path.isfile(path):
        return None
    spec = importlib.util.spec_from_file_location("verify_zizmor", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", default=".")
    ap.add_argument("--write", action="store_true",
                    help="bring the Gate 170 registers in line with the pins "
                         "in place (the step a Dependabot bump PR needs)")
    ap.add_argument("--bump", action="store_true",
                    help="first bump every SHA pin to its newest release "
                         "(with --write, rewrite them; alone, report only)")
    ap.add_argument("--summary", help="write a pull request body here")
    args = ap.parse_args(argv)
    bumps, notes = [], []
    if args.bump:
        bumps = plan(args.root)
        if args.write and bumps:
            notes += apply(args.root, bumps)
        if not bumps:
            print("wc_action_pins: every SHA-pinned action is on its newest "
                  "release.")
    if args.write:
        notes += sync_rows(args.root)
        for n in notes:
            print("wc_action_pins: " + n)
        if not notes:
            print("wc_action_pins: the Gate 170 registers already match the pins.")
    if bumps:
        body = summary(bumps, notes)
        if args.summary:
            _write(args.summary, body)
        print(body)
    elif not args.write and not args.bump:
        ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
