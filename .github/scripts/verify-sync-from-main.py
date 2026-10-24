#!/usr/bin/env python3
"""The `merge` sync method's deterministic helper behaves on real git history.

WHY THIS EXISTS
---------------
rebase.yml's `sync-method: merge` arm (spec 118) brings the default branch
into a spec branch by a sync commit, never a rewrite. Every decision in it
lives in wc_sync_from_main.py, so this gate builds real local git fixtures
(a bare origin plus a clone per case) and runs the helper and the plain git
commands the workflow runs against them: method validation, the
already-current test, the clean and same-tree merges, the publish push (plain
fast-forward; rejected when the remote head moved), and every verify-scope
failure branch. Each MUTATION disables one verify-scope guard in the helper
source and asserts the suite then fails (FR-016). It also pins the wrapper
wiring: the stage reads no `vars.*`; the wrapper feeds the switch.

Usage: python3 .github/scripts/verify-sync-from-main.py
Requires: git.
"""
import os
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wc_sync_from_main  # noqa: E402

HELPER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wc_sync_from_main.py")
STAGE = ".github/workflows/rebase.yml"
WRAPPER = ".github/workflows/wing-commander-rebase.yml"
SWITCH = "sync-method: ${{ vars.WING_COMMANDER_SPEC_BRANCH_SYNC || 'rebase' }}"

results = []


def check(name, ok, detail="", quiet=False):
    results.append((name, ok, detail))
    if quiet:
        return
    if ok:
        print("[ok] {0}".format(name))
    else:
        print("::error::verify-sync-from-main: {0} -- {1}".format(name, detail))


def sh(cwd, *args, check_rc=True):
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t", GIT_EDITOR="true")
    r = subprocess.run(args, cwd=cwd, capture_output=True, text=True, env=env)
    if check_rc and r.returncode != 0:
        raise RuntimeError("{0}: {1}".format(" ".join(args), r.stderr))
    return r


def write(path, text):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def helper(src, cwd, *args):
    return subprocess.run([sys.executable, src, *args], cwd=cwd, capture_output=True, text=True)


def make_repo(tmp):
    """origin (bare) + a clone on spec/x with main one commit ahead of the fork."""
    origin = os.path.join(tmp, "origin.git")
    work = os.path.join(tmp, "work")
    sh(tmp, "git", "init", "-q", "--bare", "-b", "main", origin)
    sh(tmp, "git", "clone", "-q", origin, work)
    sh(work, "git", "checkout", "-q", "-b", "main")
    write(os.path.join(work, "a.txt"), "one\ntwo\nthree\n")
    write(os.path.join(work, "b.txt"), "b\n")
    sh(work, "git", "add", "."), sh(work, "git", "commit", "-q", "-m", "base")
    sh(work, "git", "push", "-q", "origin", "main")
    sh(work, "git", "checkout", "-q", "-b", "spec/x")
    write(os.path.join(work, "own.txt"), "branch work\n")
    sh(work, "git", "add", "."), sh(work, "git", "commit", "-q", "-m", "branch work")
    sh(work, "git", "push", "-q", "origin", "spec/x")
    return origin, work


def advance_main(work, fname, text, msg="main moves"):
    sh(work, "git", "checkout", "-q", "main")
    write(os.path.join(work, fname), text)
    sh(work, "git", "add", "."), sh(work, "git", "commit", "-q", "-m", msg)
    sh(work, "git", "push", "-q", "origin", "main")
    sh(work, "git", "checkout", "-q", "spec/x")
    sh(work, "git", "fetch", "-q", "--no-tags", "origin", "main:refs/remotes/origin/main")
    return sh(work, "git", "rev-parse", "origin/main").stdout.strip()


def head(work, ref="HEAD"):
    return sh(work, "git", "rev-parse", ref).stdout.strip()


def sync_commit(work):
    sh(work, "git", "merge", "--no-ff", "--no-commit", "origin/main", check_rc=False)
    sh(work, "git", "commit", "-q", "--allow-empty", "-m", "sync: merge main into spec/x")


def suite(src, quiet=False):
    """Run every case against helper source `src`; return the failure names."""
    start = len(results)
    q = quiet

    for val, want_rc, want_out in (("", 0, "rebase"), ("rebase", 0, "rebase"), ("merge", 0, "merge"),
                                   ("bogus", 1, None), ("Merge", 1, None)):
        r = helper(src, ".", "validate-method", val)
        ok = r.returncode == want_rc and (want_out is None or r.stdout.strip() == want_out)
        if want_rc:
            ok = ok and ("sync-method '{0}' is not valid; accepted values are 'rebase' and 'merge'".format(val) in r.stdout)
        check("validate-method {0!r}".format(val), ok, r.stdout + r.stderr, q)
    for br, rc in (("spec/x", 0), ("+spec/x", 1), ("--force-with-lease", 1)):
        r = helper(src, ".", "publish-refspec", "--", br)
        ok = r.returncode == rc and (rc == 1 or r.stdout.strip() == "HEAD:refs/heads/spec/x")
        check("publish-refspec {0!r}".format(br), ok, r.stdout + r.stderr, q)

    with tempfile.TemporaryDirectory() as tmp:
        # decide: current, behind, same-tree.
        _, work = make_repo(tmp)
        main_sha = head(work, "origin/main")
        sh(work, "git", "merge", "-q", "--no-edit", "origin/main", check_rc=False)
        r = helper(src, work, "decide", "--main", main_sha)
        check("decide: branch already contains main -> current", r.stdout.strip() == "current", r.stdout + r.stderr, q)
        # main moves again after the sync: the branch is behind once more.
        newer = advance_main(work, "m2.txt", "later\n", "main moves again")
        r = helper(src, work, "decide", "--main", newer)
        check("decide: main moved again after a sync -> merge", r.stdout.strip() == "merge", r.stdout + r.stderr, q)

    with tempfile.TemporaryDirectory() as tmp:
        origin, work = make_repo(tmp)
        old = head(work)
        main_sha = advance_main(work, "m.txt", "from main\n")
        r = helper(src, work, "decide", "--main", main_sha)
        check("decide: behind main -> merge", r.stdout.strip() == "merge", r.stdout + r.stderr, q)
        sync_commit(work)
        parents = sh(work, "git", "rev-list", "--parents", "-n", "1", "HEAD").stdout.split()[1:]
        check("clean merge: parents are [old tip, main tip]", parents == [old, main_sha], str(parents), q)
        check("clean merge: old head is an ancestor and main is contained",
              sh(work, "git", "merge-base", "--is-ancestor", old, "HEAD", check_rc=False).returncode == 0
              and sh(work, "git", "merge-base", "--is-ancestor", main_sha, "HEAD", check_rc=False).returncode == 0, "", q)
        ref = helper(src, work, "publish-refspec", "spec/x").stdout.strip()
        r = sh(work, "git", "push", "origin", ref, check_rc=False)
        check("publish: plain push is a fast-forward", r.returncode == 0, r.stderr, q)
        check("publish: remote tip is the sync commit", head(origin, "refs/heads/spec/x") == head(work), "", q)

    with tempfile.TemporaryDirectory() as tmp:
        # same-tree: main gained a cherry-pick of branch work.
        _, work = make_repo(tmp)
        old = head(work)
        sh(work, "git", "checkout", "-q", "main")
        write(os.path.join(work, "own.txt"), "branch work\n")
        sh(work, "git", "add", "."), sh(work, "git", "commit", "-q", "-m", "same change on main")
        sh(work, "git", "push", "-q", "origin", "main")
        sh(work, "git", "checkout", "-q", "spec/x")
        sh(work, "git", "fetch", "-q", "--no-tags", "origin", "main:refs/remotes/origin/main")
        main_sha = head(work, "origin/main")
        r = helper(src, work, "decide", "--main", main_sha)
        check("decide: same-tree main -> merge", r.stdout.strip() == "merge", r.stdout + r.stderr, q)
        sync_commit(work)
        parents = sh(work, "git", "rev-list", "--parents", "-n", "1", "HEAD").stdout.split()[1:]
        check("same-tree merge still creates the sync commit", parents == [old, main_sha], str(parents), q)

    with tempfile.TemporaryDirectory() as tmp:
        # remote head moved after checkout: plain push rejected, remote untouched.
        origin, work = make_repo(tmp)
        advance_main(work, "m.txt", "from main\n")
        sync_commit(work)
        other = os.path.join(tmp, "other")
        sh(tmp, "git", "clone", "-q", "-b", "spec/x", origin, other)
        write(os.path.join(other, "late.txt"), "late\n")
        sh(other, "git", "add", "."), sh(other, "git", "commit", "-q", "-m", "late")
        sh(other, "git", "push", "-q", "origin", "spec/x")
        moved = head(origin, "refs/heads/spec/x")
        r = sh(work, "git", "push", "origin", "HEAD:refs/heads/spec/x", check_rc=False)
        check("publish: rejected when the remote head moved, branch untouched",
              r.returncode != 0 and head(origin, "refs/heads/spec/x") == moved, r.stderr, q)

    # verify-scope: a conflicting edit of a.txt on both sides, plus a bystander.
    def conflict_case(tmp):
        _, work = make_repo(tmp)
        write(os.path.join(work, "a.txt"), "one\nBRANCH\nthree\n")
        sh(work, "git", "add", "."), sh(work, "git", "commit", "-q", "-m", "branch edits a")
        before = head(work)
        main_sha = advance_main(work, "a.txt", "one\nMAIN\nthree\n")
        tree = sh(work, "git", "merge-tree", "--write-tree", "--no-messages", main_sha, "HEAD", check_rc=False).stdout.split()[0]
        sh(work, "git", "merge", "--no-ff", "--no-commit", main_sha, check_rc=False)
        manifest = os.path.join(tmp, "manifest.txt")
        write(manifest, "a.txt\n")
        return work, before, main_sha, tree, manifest

    def verify(work, before, main_sha, tree, manifest, verdict="healthy", project=""):
        return helper(src, work, "verify-scope", "--before", before, "--main", main_sha,
                      "--conflicted-tree", tree, "--manifest", manifest, "--project", project,
                      "--verdict", verdict)

    def resolve(work, extra=None, a="one\nBOTH\nthree\n"):
        write(os.path.join(work, "a.txt"), a)
        for name, text in (extra or {}).items():
            write(os.path.join(work, name), text)
        sh(work, "git", "add", "."), sh(work, "git", "commit", "-q", "-m", "sync: merge main into spec/x")

    with tempfile.TemporaryDirectory() as tmp:
        w, b, m, t, mf = conflict_case(tmp)
        resolve(w)
        r = verify(w, b, m, t, mf)
        check("verify-scope: in-scope resolution passes", r.returncode == 0, r.stderr, q)
    with tempfile.TemporaryDirectory() as tmp:
        w, b, m, t, mf = conflict_case(tmp)
        resolve(w, {"b.txt": "tampered\n"})
        r = verify(w, b, m, t, mf)
        check("verify-scope: path outside the manifest fails",
              r.returncode == 1 and "b.txt" in r.stderr, r.stderr, q)
    with tempfile.TemporaryDirectory() as tmp:
        w, b, m, t, mf = conflict_case(tmp)
        resolve(w, a="one\n<<<<<<< HEAD\nBOTH\n=======\nx\n>>>>>>> main\nthree\n")
        r = verify(w, b, m, t, mf)
        check("verify-scope: leftover marker fails",
              r.returncode == 1 and "marker" in r.stderr, r.stderr, q)
    with tempfile.TemporaryDirectory() as tmp:
        w, b, m, t, mf = conflict_case(tmp)
        resolve(w)
        write(os.path.join(w, "extra.txt"), "x\n")
        sh(w, "git", "add", "."), sh(w, "git", "commit", "-q", "-m", "extra commit")
        r = verify(w, b, m, t, mf)
        check("verify-scope: extra commit (wrong parents) fails",
              r.returncode == 1 and "parents" in r.stderr, r.stderr, q)
    with tempfile.TemporaryDirectory() as tmp:
        w, b, m, t, mf = conflict_case(tmp)
        resolve(w)
        r = verify(w, b, m, t, mf, verdict="exhausted")
        check("verify-scope: unhealthy verdict fails",
              r.returncode == 1 and "verdict" in r.stderr, r.stderr, q)
    with tempfile.TemporaryDirectory() as tmp:
        w, b, m, t, mf = conflict_case(tmp)
        resolve(w)
        r = verify(w, b, m, t, mf, project="proj")
        check("verify-scope: manifest entries outside the project are not admitted",
              r.returncode == 1 and "a.txt" in r.stderr, r.stderr, q)
    with tempfile.TemporaryDirectory() as tmp:
        w, b, m, t, mf = conflict_case(tmp)
        resolve(w, a="Title\n=======\nthree\n")
        r = verify(w, b, m, t, mf)
        check("verify-scope: a bare ======= line (setext underline) passes",
              r.returncode == 0, r.stderr, q)
    with tempfile.TemporaryDirectory() as tmp:
        w, b, m, t, mf = conflict_case(tmp)
        resolve(w)
        r = verify(w, b, m, "", mf)
        check("verify-scope: an empty conflicted tree fails with a reason, no traceback",
              r.returncode == 1 and "conflicted tree" in r.stderr and "Traceback" not in r.stderr,
              r.stderr, q)
    with tempfile.TemporaryDirectory() as tmp:
        w, b, m, t, mf = conflict_case(tmp)
        resolve(w)
        r = verify(w, b, m, "0" * 40, mf)
        check("verify-scope: a bad tree OID fails with a reason, no traceback",
              r.returncode == 1 and "Traceback" not in r.stderr, r.stderr, q)
    failed = [n for n, ok, _ in results[start:] if not ok]
    if quiet:
        del results[start:]
    return failed


# Single home (CLAUDE.md "Shared logic has exactly one home"): method
# validation and the conflict-marker scan live only in the helper.
# The marker sign is the helper's own compiled pattern, so a verbatim copy is
# caught and an unrelated marker regex elsewhere does not trip the gate.
COPY_SIGNS = ("accepted values are 'rebase' and 'merge'", wc_sync_from_main.MARKER.pattern)


def copies_of_helper_logic(files):
    """Names of the files in `files` ({path: text}) that carry a sign."""
    return sorted(p for p, text in files.items() if any(s in text for s in COPY_SIGNS))


def single_home_files():
    found = {}
    for base, ext in ((".github/workflows", (".yml", ".yaml")), (".github/actions", (".yml", ".yaml", ".sh")),
                      (".github/scripts", (".py", ".sh"))):
        for dirpath, _dirs, names in os.walk(base):
            for name in names:
                path = os.path.join(dirpath, name).replace(os.sep, "/")
                if name.endswith(ext) and path not in (".github/scripts/wc_sync_from_main.py",
                                                       ".github/scripts/verify-sync-from-main.py"):
                    with open(path, encoding="utf-8", errors="replace") as fh:
                        found[path] = fh.read()
    return found


def main():
    with open(HELPER, encoding="utf-8") as fh:
        source = fh.read()
    if suite(HELPER):
        sys.exit(1)
    copies = copies_of_helper_logic(single_home_files())
    check("method validation and the marker scan have a single home", not copies,
          "copied into: " + ", ".join(copies))
    check("the single-home check sees a pasted copy",
          copies_of_helper_logic({"x.yml": "echo \"accepted values are 'rebase' and 'merge'\""}) == ["x.yml"], "")
    # The importable module and the subprocess entry point are one file.
    check("helper marker pattern matches a conflict line and not prose",
          bool(wc_sync_from_main.MARKER.search("a\n<<<<<<< HEAD\nb"))
          and not wc_sync_from_main.MARKER.search("a ======= b"), "")

    # Wrapper wiring (FR-006, constitution VII).
    with open(STAGE, encoding="utf-8") as fh:
        stage = fh.read()
    with open(WRAPPER, encoding="utf-8") as fh:
        wrapper = fh.read()
    check("stage reads no vars.* for the sync switch", "vars.WING_COMMANDER_SPEC_BRANCH_SYNC" not in stage
          and not re.search(r"\bvars\.", stage), "rebase.yml must take the switch as an input")
    check("wrapper passes the switch with a rebase default", SWITCH in wrapper, "missing: " + SWITCH)
    validate = stage.find("name: Validate the sync method")
    select = stage.find("name: Select in-flight branches")
    check("an invalid sync-method fails discover before branches are selected",
          0 < validate < select and "validate-method" in stage[validate:select], "")

    restore = stage.find("name: Restore the seeded conflict manifest")
    narrow = stage.find("name: Narrow the conflict manifest to the project folder")
    check("the merge arm restores the seeded manifest before narrowing it",
          0 < restore < narrow and "conflict-manifest.seed.txt" in stage[restore:narrow], "")

    mutations = (
        ("verdict guard", 'if verdict != "healthy":', "if False:"),
        ("parents guard", "if parents != [before, main]:", "if False:"),
        ("manifest guard", "if p not in allowed:", "if False:"),
        ("marker guard", "if blob.returncode == 0 and MARKER.search(blob.stdout):", "if False:"),
        ("project narrowing", "allowed = {p for p in listed if in_project(p, project)}", "allowed = set(listed)"),
        ("force refusal", 'branch.startswith("+") or ', ""),
    )
    for name, old, new in mutations:
        if old not in source:
            check("mutation target present: " + name, False, "text not found in the helper")
            continue
        with tempfile.TemporaryDirectory() as tmp:
            mutated = os.path.join(tmp, "wc_sync_from_main.py")
            write(mutated, source.replace(old, new))
            check("mutation caught: " + name, bool(suite(mutated, quiet=True)),
                  "the suite stayed green with this guard disabled")

    failed = [n for n, ok, _ in results if not ok]
    if failed:
        sys.exit("verify-sync-from-main: {0} check(s) failed".format(len(failed)))
    print("verify-sync-from-main: all {0} checks passed".format(len(results)))


if __name__ == "__main__":
    main()
