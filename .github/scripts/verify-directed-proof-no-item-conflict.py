#!/usr/bin/env python3
"""Gate 101 — a directed proof run never conflicts with the board item it is
proving (FR-017, specs/060-self-redrive-concurrency research.md D7).

WHY THIS EXISTS
---------------
research.md D2 excludes `select`/`route`/`fix` from `aimable_jobs` by
construction so a directed proof run can never select a board item or open
a fix PR (FR-002). D7's own point is that this must be CHECKED, not merely
argued in prose: a future edit widening `aimable_jobs` to include one of
those three would silently reintroduce exactly the race FR-017 forbids
("the issue being proven is still open... while its proof run is in
flight"), and nothing else in the gate suite reads that constant at all.

This gate has two parts:

1. A structural assertion reading `aimable_jobs` directly from
   `board_prove.py` (never re-derived) and failing if it contains any of
   `select`/`route`/`fix`.
2. A pointer to the `directed-proof-in-flight` fixture under
   `.github/scripts/tests/board-eligibility/in-flight/`, which
   `verify-board-eligibility.py` already exercises (Gate 101 itself does
   not re-run it -- doing so would be a second, redundant assertion of the
   same fixture rather than a second home for it, CLAUDE.md's single-home
   rule) -- proving `select()` never returns an issue whose only open
   marker names `step: prove`, the specific case FR-017 names.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from board_prove import aimable_jobs  # noqa: E402

FORBIDDEN_JOBS = frozenset({"select", "route", "fix"})

FIXTURES_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "tests", "board-eligibility",
    "in-flight", "directed-proof-in-flight")


def run():
    failures = 0

    conflict = aimable_jobs & FORBIDDEN_JOBS
    if conflict:
        failures += 1
        print("::error::verify-directed-proof-no-item-conflict: "
              "board_prove.aimable_jobs contains {0} -- FR-002 forbids a "
              "directed proof run from selecting a board item or opening a "
              "fix PR, and one of these jobs does exactly that. This "
              "widens the aimable-stage set past what D2/FR-017 permit."
              .format(sorted(conflict)))
    else:
        print("[ok] board_prove.aimable_jobs ({0}) contains none of "
              "select/route/fix".format(sorted(aimable_jobs)))

    if not os.path.isdir(FIXTURES_DIR):
        failures += 1
        print("::error::verify-directed-proof-no-item-conflict: {0} does "
              "not exist -- FR-017's own regression fixture (verified by "
              "verify-board-eligibility.py) is missing.".format(FIXTURES_DIR))
    else:
        print("[ok] {0} exists -- see verify-board-eligibility.py for "
              "select()/in_flight_candidate() assertions against it "
              "(single home, CLAUDE.md)".format(FIXTURES_DIR))

    print("verify-directed-proof-no-item-conflict: {0} failure(s).".format(failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(run())
