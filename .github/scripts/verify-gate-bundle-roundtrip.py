#!/usr/bin/env python3
"""Gate 147 -- a workspace bundle survives the round trip it exists for
(spec 095, contracts/workspace-bundle.md).

WHY THIS EXISTS
---------------
The agent's commits leave the job that wrote them as a git bundle
(_shared/build-gate-bundle.sh), are gated in a credential-free job
(_shared/contained-gate-suite.sh) and are restored in the job that pushes
them (_shared/restore-gate-bundle.sh). Each script is simple on its own;
what can break is the hand-off between them. The first version fetched the
bundle with a `refs/*` refspec while the bundle's one ref is `HEAD`: the
fetch exited 0, imported nothing, every gate verdict read "head could not be
checked out" and every restore failed -- and every gate stayed green,
because none drove the three scripts end to end (code review of #990).

WHAT IT CHECKS
--------------
Against real local git repositories -- an agent clone that commits past a
base, a trusted clone and a publisher clone that hold only the base:
  1. a head whose suite passes is bundled, gated (verdict pass, bound to the
     head and the trusted SHA) and restored (HEAD is that commit, on the
     named branch);
  2. a head whose suite fails yields verdict fail naming the first FAIL line;
  3. a head that made no commits since the base still round-trips, without
     shipping the whole history;
  4. the restore refuses a head the producer did not report, and a missing
     bundle;
  5. a missing bundle, or a head that deleted run-local-gates.py, is a fail
     verdict, never a pass or a skip.
--self-test reruns the checks with each script's fetch reverted to the
`refs/*` refspec, and with the restore's head check removed, and asserts
each mutation is caught.

Usage: python3 .github/scripts/verify-gate-bundle-roundtrip.py [--self-test]
Requires: bash, git, jq.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SHARED = os.path.join(HERE, "..", "actions", "_shared")
SCRIPTS = ("build-gate-bundle.sh", "contained-gate-suite.sh", "restore-gate-bundle.sh",
           "git-push-hardening.sh")
PASSING_SUITE = "print('PASS  verify-x.py')\n"
FAILING_SUITE = "import sys\nprint('FAIL  verify-x.py (planted)')\nsys.exit(1)\n"
TRUSTED_SHA = "b" * 40


def git(cwd, *args):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                           "-c", "commit.gpgsign=false"] + list(args), cwd=cwd, check=True,
                          capture_output=True, text=True).stdout.strip()


def write(repo, rel, text):
    path = os.path.join(repo, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def sh(shared, script, args, cwd, env_extra=None):
    out = tempfile.mktemp()
    env = dict(os.environ, GITHUB_OUTPUT=out, **(env_extra or {}))
    proc = subprocess.run(["bash", os.path.join(shared, script)] + list(args), cwd=cwd,
                          env=env, capture_output=True, text=True)
    outputs = {}
    if os.path.exists(out):
        for line in open(out, encoding="utf-8").read().splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                outputs[k] = v
    return proc.returncode, proc.stdout + proc.stderr, outputs


def world(tmp, agent_change):
    """origin with a base commit; an agent clone that applies agent_change;
    trusted and publisher clones at the base. Returns paths and SHAs."""
    origin = os.path.join(tmp, "origin")
    os.makedirs(origin)
    git(origin, "init", "-q", "-b", "main")
    write(origin, "HISTORY", "an earlier commit, so the base is not a root\n")
    git(origin, "add", "-A")
    git(origin, "commit", "-q", "-m", "history")
    write(origin, ".github/scripts/run-local-gates.py", PASSING_SUITE)
    write(origin, "README", "base\n")
    git(origin, "add", "-A")
    git(origin, "commit", "-q", "-m", "base")
    base = git(origin, "rev-parse", "HEAD")
    clones = {}
    for name in ("agent", "trusted", "publisher"):
        clones[name] = os.path.join(tmp, name)
        git(tmp, "clone", "-q", origin, clones[name])
    agent_change(clones["agent"])
    head = git(clones["agent"], "rev-parse", "HEAD")
    return clones, base, head


def commit_file(rel, text):
    def change(repo):
        write(repo, rel, text)
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "agent: " + rel)
    return change


def remove_suite(repo):
    git(repo, "rm", "-q", ".github/scripts/run-local-gates.py")
    git(repo, "commit", "-q", "-m", "agent: drop the suite")


def no_change(_repo):
    pass


def round_trip(shared, tmp, change, site="board-fix"):
    """-> (verdict dict or None, build/gate output, clones, base, head, bundle dir)."""
    clones, base, head = world(tmp, change)
    bundle = os.path.join(tmp, "bundle")
    rc, out, outs = sh(shared, "build-gate-bundle.sh", [site, base, bundle], clones["agent"])
    if rc != 0:
        return None, "build exited {0}: {1}".format(rc, out), clones, base, head, bundle
    verdict_path = os.path.join(tmp, "verdict.json")
    rc2, out2, _ = sh(shared, "contained-gate-suite.sh",
                      [site, bundle, TRUSTED_SHA, verdict_path], clones["trusted"])
    verdict = None
    if os.path.exists(verdict_path):
        with open(verdict_path, encoding="utf-8") as fh:
            verdict = json.load(fh)
    return verdict, out + out2, clones, base, head, bundle


def checks(shared):
    failures = []

    def ck(name, cond, detail=""):
        if not cond:
            failures.append("{0} -- {1}".format(name, detail))

    with tempfile.TemporaryDirectory() as tmp:
        v, out, clones, base, head, bundle = round_trip(shared, tmp,
                                                        commit_file("src.txt", "fix\n"))
        ck("a passing head is gated green and bound to it",
           v is not None and v.get("outcome") == "pass" and v.get("head_sha") == head
           and v.get("trusted_sha") == TRUSTED_SHA, "verdict={0}\n{1}".format(v, out[-800:]))
        rc, rout, routs = sh(shared, "restore-gate-bundle.sh", [bundle, head, "fix/7-x"],
                             clones["publisher"])
        ck("the publisher restores exactly that head on the named branch",
           rc == 0 and git(clones["publisher"], "rev-parse", "HEAD") == head
           and git(clones["publisher"], "rev-parse", "--abbrev-ref", "HEAD") == "fix/7-x"
           and routs.get("head-sha") == head, "rc={0}\n{1}".format(rc, rout))
        rc, rout, _ = sh(shared, "restore-gate-bundle.sh", [bundle, base, "fix/7-x"],
                         clones["publisher"])
        other = "c" * 40
        rc2, rout2, _ = sh(shared, "restore-gate-bundle.sh", [bundle, other, "fix/7-x"],
                           clones["publisher"])
        ck("the restore refuses a head the producer did not report",
           rc2 != 0 and "does not hold" in rout2, "rc={0}\n{1}".format(rc2, rout2))
        rc3, rout3, _ = sh(shared, "restore-gate-bundle.sh",
                           [os.path.join(tmp, "nowhere"), head, "b"], clones["publisher"])
        ck("the restore refuses a missing bundle", rc3 != 0, rout3)
        corrupt = os.path.join(tmp, "corrupt")
        os.makedirs(corrupt)
        with open(os.path.join(corrupt, "bundle.git"), "w") as fh:
            fh.write("not a bundle\n")
        rc4, rout4, _ = sh(shared, "restore-gate-bundle.sh", [corrupt, head, "b"],
                           clones["publisher"])
        ck("a bundle that fails verification is refused with an annotation saying the "
           "containment could not be established",
           rc4 != 0 and "::error::" in rout4 and "containment could not be established" in rout4,
           rout4)
        # The verdict writer's copy is write-protected before the head is
        # checked out (static: this harness runs as whatever user CI uses,
        # root included, for whom a mode bit proves nothing).
        text = open(os.path.join(shared, "contained-gate-suite.sh"), encoding="utf-8").read()
        protect = text.find('chmod -R a-w "$trusted_copy"')
        checkout = text.find("git worktree add")
        ck("the verdict writer's copy is write-protected before the head is checked out",
           0 <= protect < checkout, "chmod at {0}, worktree add at {1}".format(protect, checkout))
        verdict_path = os.path.join(tmp, "missing-verdict.json")
        sh(shared, "contained-gate-suite.sh",
           ["board-fix", os.path.join(tmp, "nowhere"), TRUSTED_SHA, verdict_path],
           clones["trusted"])
        mv = json.load(open(verdict_path)) if os.path.exists(verdict_path) else {}
        ck("a missing bundle is a fail verdict, never a skip",
           mv.get("outcome") == "fail" and "missing" in mv.get("first_failure", ""), str(mv))

    with tempfile.TemporaryDirectory() as tmp:
        v, out, *_rest = round_trip(shared, tmp, commit_file(".github/scripts/"
                                                             "run-local-gates.py", FAILING_SUITE))
        ck("a failing head is gated red, naming the first FAIL line",
           v is not None and v.get("outcome") == "fail"
           and v.get("first_failure", "").startswith("FAIL  verify-x.py"),
           "verdict={0}\n{1}".format(v, out[-800:]))

    with tempfile.TemporaryDirectory() as tmp:
        v, out, clones, base, head, bundle = round_trip(shared, tmp, no_change)
        heads = git(clones["agent"], "bundle", "list-heads", os.path.join(bundle, "bundle.git"))
        verify = subprocess.run(["git", "bundle", "verify", os.path.join(bundle, "bundle.git")],
                                cwd=clones["agent"], capture_output=True, text=True)
        ck("a head with no new commits still round-trips",
           v is not None and v.get("outcome") == "pass" and v.get("head_sha") == head == base,
           "verdict={0}\n{1}".format(v, out[-800:]))
        ck("a head with no new commits ships one commit, not the whole history",
           "requires" in (verify.stdout + verify.stderr) and head in heads,
           verify.stdout + verify.stderr)

    with tempfile.TemporaryDirectory() as tmp:
        v, out, *_rest = round_trip(shared, tmp, remove_suite)
        ck("a head that deleted run-local-gates.py is red, never a skip",
           v is not None and v.get("outcome") == "fail"
           and "removed run-local-gates.py" in v.get("first_failure", ""), str(v))
    return failures


def mutated_shared(tmp, edits):
    """A copy of _shared/ (and a .github/scripts beside it, which the gate
    script reads its verdict writer from) with (script, old, new) edits."""
    root = os.path.join(tmp, "m", ".github")
    shared = os.path.join(root, "actions", "_shared")
    os.makedirs(shared)
    os.symlink(os.path.abspath(HERE), os.path.join(root, "scripts"))
    for name in SCRIPTS:
        shutil.copy(os.path.join(SHARED, name), os.path.join(shared, name))
    for name, old, new in edits:
        path = os.path.join(shared, name)
        text = open(path, encoding="utf-8").read()
        if old not in text:
            sys.exit("::error::Gate 147 self-test: {0!r} not in {1}; update the "
                     "mutation with the script.".format(old, name))
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text.replace(old, new))
    return shared


MUTATIONS = (
    ("the gate job fetches the bundle with a refs/* refspec",
     [("contained-gate-suite.sh", '"+HEAD:refs/wc-gate/head"', '"+refs/*:refs/wc-gate/*"')]),
    ("the restore fetches the bundle with a refs/* refspec",
     [("restore-gate-bundle.sh", '"+HEAD:refs/wc-gate/head"', '"+refs/*:refs/wc-gate/*"')]),
    ("the restore stops checking that the bundle holds the reported head",
     [("restore-gate-bundle.sh", 'if ! git cat-file -e "${expected}^{commit}" 2>/dev/null; then',
       "if false; then")]),
    ("the verdict writer's copy is left writable",
     [("contained-gate-suite.sh", 'chmod -R a-w "$trusted_copy"', "true")]),
    ("a bundle that fails verification is refused without saying why",
     [("restore-gate-bundle.sh", " The containment could not be established; nothing is pushed.\"\n  exit 1\nfi\n# The bundle",
       "\"\n  exit 1\nfi\n# The bundle")]),
    ("a head with no new commits ships the whole history",
     [("build-gate-bundle.sh", 'git bundle create --quiet "$out_dir/bundle.git" HEAD~1..HEAD HEAD',
       'git bundle create --quiet "$out_dir/bundle.git" HEAD')]),
)


def main():
    failures = checks(os.path.abspath(SHARED))
    if "--self-test" in sys.argv[1:]:
        if failures:
            failures = ["the shipped scripts already fail: " + f for f in failures]
        for label, edits in MUTATIONS:
            with tempfile.TemporaryDirectory() as tmp:
                caught = checks(mutated_shared(tmp, edits))
            if caught:
                print("note: mutation caught ({0}): {1}".format(label, caught[0][:160]))
            else:
                failures.append("mutation {0!r} was NOT caught".format(label))
    for f in failures:
        print("::error::Gate 147: " + f)
    if failures:
        return 1
    print("Gate 147{0}: a workspace bundle round-trips from the agent's job through the "
          "gate job to the publisher.".format(" self-test" if "--self-test" in sys.argv[1:]
                                              else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
