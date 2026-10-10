#!/usr/bin/env python3
"""The Board status issue's body, rendered now instead of at 07:17 UTC.

board-status.yml rewrites the "Board status" issue once a day, so by the
evening it can be most of a day old. This prints the same report from a
fresh snapshot, through wc_board_status.py's own snapshot() and render() --
the one home of what the report reads and says -- without publishing
anything. The switches come from the repository variables board-status.yml
passes in its env; the variable-to-switch names below mirror
wc_board_status.main()'s, which is where a new switch is added first.

Needs gh authenticated with read access to the repository and its
variables (a variable it can't read renders as unset).

  board_now.py [--repo OWNER/NAME]
"""
import argparse
import json
import os
import subprocess
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                         "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, ".github", "scripts"))

import wc_board_status  # noqa: E402

SWITCH_VARIABLES = {
    "auto_release_paused": "WING_COMMANDER_AUTO_RELEASE_PAUSED",
    "board_loop_paused": "WING_COMMANDER_BOARD_LOOP_PAUSED",
    "lifecycle_auto_merge": "WING_COMMANDER_LIFECYCLE_AUTO_MERGE",
    "review_gate_paused": "WING_COMMANDER_LIFECYCLE_REVIEW_GATE_PAUSED",
    "tasks_review": "WING_COMMANDER_TASKS_REVIEW",
}


def gh(*args):
    return subprocess.run(["gh"] + list(args), capture_output=True, text=True)


def switches_for(repo):
    out = gh("variable", "list", "-R", repo, "--json", "name,value")
    values = {}
    if out.returncode == 0 and out.stdout.strip():
        values = {v["name"]: v.get("value", "") for v in json.loads(out.stdout)}
    else:
        sys.stderr.write("board_now: couldn't read repository variables; switches render as unset\n")
    switches = {key: values.get(name, "") for key, name in SWITCH_VARIABLES.items()}
    switches["tasks_review"] = switches["tasks_review"].strip().lower()
    return switches


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--repo")
    args = parser.parse_args()
    repo = args.repo
    if not repo:
        out = gh("repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner")
        if out.returncode != 0:
            sys.exit("board_now: gh can't see the repository: {0}".format(out.stderr.strip()))
        repo = out.stdout.strip()
    sys.stdout.write(wc_board_status.render(wc_board_status.snapshot(repo, switches_for(repo))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
