#!/usr/bin/env python3
"""Board loop stand-down check (specs/057-autonomous-board-loop, research.md
D16, FR-049): "an implement cycle is in flight" is read directly from
Actions' own run state, never inferred from usage metrics or elapsed time.

Runtime shape: `gh run list --workflow=implement.yml --status=in_progress
--json databaseId` -- a non-empty result means the board loop MUST stand
down (entry gate 2, contracts/board-loop-workflow.md) before selecting or
acting on anything.
"""
import json
import subprocess
import sys


def implement_cycle_in_flight(run_list_json):
    """True when `run_list_json` (the raw stdout of `gh run list
    --workflow=implement.yml --status=in_progress --json databaseId`) names
    at least one in-progress run."""
    try:
        runs = json.loads(run_list_json)
    except (TypeError, ValueError):
        return False
    return isinstance(runs, list) and len(runs) > 0


def check():
    """Runtime entry point: shells out to `gh run list` and returns
    implement_cycle_in_flight() over its output."""
    proc = subprocess.run(
        ["gh", "run", "list", "--workflow=implement.yml",
         "--status=in_progress", "--json", "databaseId"],
        capture_output=True, text=True, check=True)
    return implement_cycle_in_flight(proc.stdout)


def main():
    in_flight = check()
    print("in-flight" if in_flight else "clear")
    return 0


if __name__ == "__main__":
    sys.exit(main())
