#!/usr/bin/env python3
"""The Board status issue's body, rendered now instead of at 07:17 UTC.

board-status.yml rewrites the "Board status" issue once a day, so by the
evening it can be most of a day old. This prints the same report from a
fresh snapshot, through wc_board_status.py's own snapshot() and render() --
the one home of what the report reads and says -- without publishing
anything. The switches come from the repository variables board-status.yml
passes in its env, read through wc_board_status.switches_from(), so a new
switch added there reaches this report too.

Needs gh authenticated with read access to the repository and its
variables. It exits non-zero rather than render a guess when it can't list
them: the switches decide which bucket an item lands in. The repository
comes from --repo, GITHUB_REPOSITORY or the origin remote, never from
`gh repo view`, whose GraphQL call Claude Code sessions refuse.

  board_now.py [--repo OWNER/NAME]
"""
import argparse
import json
import os
import re
import subprocess
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                         "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, ".github", "scripts"))

import wc_board_status  # noqa: E402


def gh(*args):
    return subprocess.run(["gh"] + list(args), capture_output=True, text=True)


def switches_for(repo):
    out = gh("variable", "list", "-R", repo, "--json", "name,value")
    if out.returncode != 0:
        sys.exit("board_now: can't read the repository variables, so the switches "
                 "are unknown: {0}".format(out.stderr.strip()))
    values = {v["name"]: v.get("value", "") for v in json.loads(out.stdout or "[]")}
    return wc_board_status.switches_from(lambda env: values.get("WING_COMMANDER_" + env, ""))


def repo_from_origin():
    out = subprocess.run(["git", "-C", REPO_ROOT, "remote", "get-url", "origin"],
                         capture_output=True, text=True)
    match = re.search(r"([^/:]+/[^/:]+?)(?:\.git)?/?$", out.stdout.strip())
    return match.group(1) if out.returncode == 0 and match else None


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--repo")
    args = parser.parse_args()
    repo = args.repo or os.environ.get("GITHUB_REPOSITORY") or repo_from_origin()
    if not repo:
        sys.exit("board_now: can't tell the repository from the origin remote; pass --repo")
    sys.stdout.write(wc_board_status.render(wc_board_status.snapshot(repo, switches_for(repo))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
