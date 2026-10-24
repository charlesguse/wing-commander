#!/usr/bin/env python3
"""Deterministic helper for rebase.yml's `merge` sync method (spec 118).

The single home of merge-sync decisions: method validation, the
already-current test, the conflict-resolution scope check and the one
allowed publish refspec. rebase.yml calls it; nothing else carries a copy
(verify-single-home-idioms.py). Contract:
specs/118-spec-branch-sync-from-main/contracts/sync-method-input.md.

Subcommands:
  validate-method <value>   prints rebase|merge; exit 1 on anything else
  decide --main <sha>       prints current|merge
  verify-scope ...          exit 0 pass; exit 1 with each reason on stderr
  publish-refspec <branch>  prints HEAD:refs/heads/<branch>; exit 1 on a
                            forced or malformed branch value
"""
import argparse
import re
import subprocess
import sys

MARKER = re.compile(r"^(<<<<<<<|=======|>>>>>>>)( |$)", re.M)


def git(*args, check=True):
    return subprocess.run(["git", "-c", "core.quotepath=off", *args],
                          capture_output=True, text=True, check=check)


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
    if branch.startswith("+") or branch.startswith("-") or "--force" in branch or " " in branch or not branch:
        print("::error::wing-commander rebase: refusing a forced or malformed "
              "publish target '{0}'".format(branch), file=sys.stderr)
        return 1
    print("HEAD:refs/heads/{0}".format(branch))
    return 0


def decide(main):
    ok = git("merge-base", "--is-ancestor", main, "HEAD", check=False).returncode == 0
    print("current" if ok else "merge")
    return 0


def in_project(path, project):
    return not project or path == project or path.startswith(project.rstrip("/") + "/")


def verify_scope(before, main, conflicted_tree, manifest, project, verdict):
    reasons = []
    if verdict != "healthy":
        reasons.append("agent verdict is '{0}', not healthy".format(verdict))
    parents = git("rev-list", "--parents", "-n", "1", "HEAD").stdout.split()[1:]
    if parents != [before, main]:
        reasons.append("HEAD parents {0} are not [pre-merge tip, default-branch tip] {1}".format(
            parents, [before, main]))
    try:
        with open(manifest, encoding="utf-8") as fh:
            listed = {ln.rstrip("\n") for ln in fh if ln.strip()}
    except OSError:
        listed = set()
    allowed = {p for p in listed if in_project(p, project)}
    changed = [p for p in git("diff", "--name-only", conflicted_tree, "HEAD^{tree}").stdout.splitlines() if p]
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
    a = ap.parse_args(argv)
    if a.cmd == "validate-method":
        return validate_method(a.value)
    if a.cmd == "decide":
        return decide(a.main)
    if a.cmd == "publish-refspec":
        return publish_refspec(a.branch)
    return verify_scope(a.before, a.main, a.conflicted_tree, a.manifest, a.project, a.verdict)


if __name__ == "__main__":
    sys.exit(main())
