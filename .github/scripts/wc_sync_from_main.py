#!/usr/bin/env python3
"""Deterministic helper for rebase.yml's `merge` sync method (spec 118).

The single home of merge-sync decisions: method validation, the
already-current test, the conflict-resolution scope check and the one
allowed publish refspec. rebase.yml calls it; nothing else carries a copy
(verify-sync-from-main.py enforces the single home). Contract:
specs/118-spec-branch-sync-from-main/contracts/sync-method-input.md.

Subcommands:
  validate-method <value>   prints rebase|merge; exit 1 on anything else
  decide --main <sha>       prints current|merge
  verify-scope ...          exit 0 pass; exit 1 with each reason on stderr
  publish-refspec <branch>  prints HEAD:refs/heads/<branch>; exit 1 on a
                            forced or malformed branch value
  push-race                 reads a refused push's stderr on stdin; exit 0
                            when it is the branch race (git's client-side
                            "[rejected]"), 1 for any other refusal
"""
import argparse
import re
import subprocess
import sys

# A bare `=======` is a valid Markdown setext underline, so only the opening
# and closing markers count.
MARKER = re.compile(r"^(<<<<<<<|>>>>>>>)( |$)", re.M)


def git(*args, check=True):
    # errors="replace": a conflicted file can be binary or not UTF-8, and the
    # marker scan must read it rather than crash on the decode.
    return subprocess.run(["git", "-c", "core.quotepath=off", *args],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", check=check)


def validate_method(value):
    if value in ("", "rebase"):
        print("rebase")
        return 0
    if value == "merge":
        print("merge")
        return 0
    print("::error::wing-commander rebase: sync-method '{0}' is not valid; "
          "accepted values are 'rebase' and 'merge'".format(value))
    return 1


def publish_refspec(branch):
    # One argv word cannot become an option or a forced update unless it
    # starts with '+' or '-'; a '--force' later in a slug is just a name.
    if not branch or branch.startswith("+") or branch.startswith("-") or any(c.isspace() for c in branch):
        print("::error::wing-commander rebase: refusing a forced or malformed "
              "publish target '{0}'".format(branch), file=sys.stderr)
        return 1
    print("HEAD:refs/heads/{0}".format(branch))
    return 0


# A plain push the server refuses as a non-fast-forward is git's client-side
# "! [rejected]" line: the branch moved since checkout. "[remote rejected]"
# is the server refusing (branch protection, a hook, a missing permission)
# and is never the race.
RACE = re.compile(r"^ ?! \[rejected\] ", re.M)


def push_race(stderr_text):
    return 0 if RACE.search(stderr_text) else 1


def decide(main):
    ok = git("merge-base", "--is-ancestor", main, "HEAD", check=False).returncode == 0
    print("current" if ok else "merge")
    return 0


def in_project(path, project):
    return not project or path == project or path.startswith(project.rstrip("/") + "/")


def conflicted_paths(before, main):
    """The paths a merge of `main` into `before` conflicts on, from git alone:
    the deterministic bound on what a resolution may change, whatever the
    agent-writable manifest file says. None when git cannot say."""
    r = git("merge-tree", "--write-tree", "--name-only", "--no-messages", main, before, check=False)
    if r.returncode not in (0, 1):
        return None
    return {ln for ln in r.stdout.splitlines()[1:] if ln}


def verify_scope(before, main, conflicted_tree, manifest, project, verdict):
    reasons = []
    if verdict != "healthy":
        reasons.append("agent verdict is '{0}', not healthy".format(verdict))
    parents = git("rev-list", "--parents", "-n", "1", "HEAD", check=False).stdout.split()[1:]
    if parents != [before, main]:
        reasons.append("HEAD parents {0} are not [pre-merge tip, default-branch tip] {1}".format(
            parents, [before, main]))
    try:
        with open(manifest, encoding="utf-8") as fh:
            listed = {ln.rstrip("\n") for ln in fh if ln.strip()}
    except OSError:
        listed = set()
    conflicts = conflicted_paths(before, main)
    if conflicts is None:
        reasons.append("could not list the conflicting paths of {0} and {1}".format(before, main))
        conflicts = set()
    allowed = {p for p in listed if in_project(p, project) and p in conflicts}
    diff = git("diff", "--name-only", conflicted_tree, "HEAD^{tree}", check=False)
    if diff.returncode != 0:
        reasons.append("conflicted tree '{0}' is not a readable tree".format(conflicted_tree))
    changed = [p for p in diff.stdout.splitlines() if p]
    for p in changed:
        if p not in allowed:
            reasons.append("path outside the conflict manifest differs from a clean merge: " + p)
    for p in sorted(allowed):
        blob = git("show", "HEAD:" + p, check=False)
        if blob.returncode == 0 and MARKER.search(blob.stdout):
            reasons.append("conflict marker still present in " + p)
    for r in reasons:
        print(r, file=sys.stderr)
    return 1 if reasons else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("validate-method").add_argument("value", nargs="?", default="")
    sub.add_parser("decide").add_argument("--main", required=True)
    p = sub.add_parser("verify-scope")
    for name in ("before", "main", "conflicted-tree", "manifest", "verdict"):
        p.add_argument("--" + name, required=True)
    p.add_argument("--project", default="")
    sub.add_parser("publish-refspec").add_argument("branch")
    sub.add_parser("push-race")
    a = ap.parse_args(argv)
    if a.cmd == "push-race":
        return push_race(sys.stdin.read())
    if a.cmd == "validate-method":
        return validate_method(a.value)
    if a.cmd == "decide":
        return decide(a.main)
    if a.cmd == "publish-refspec":
        return publish_refspec(a.branch)
    return verify_scope(a.before, a.main, a.conflicted_tree, a.manifest, a.project, a.verdict)


if __name__ == "__main__":
    sys.exit(main())
