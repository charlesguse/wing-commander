#!/usr/bin/env python3
"""Gate: the shared reviewer's marker is disjoint from spec 116's
(specs/127-shared-pr-reviewer, FR-020, contracts/round-record.md invariant 1).

wc_convergence.read_round_records() must never see a shared-reviewer record,
with no edit to that reader. So the shared marker's name must differ from
ROUND_MARKER and must not match ROUND_MARKER_RE / ROUND_MARKER_OPEN_RE.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wc_convergence  # noqa: E402
import wc_shared_review  # noqa: E402


def check():
    problems = []
    name = wc_shared_review.MARKER
    sample = "<!-- {0}: {{}} -->".format(name)
    if name == wc_convergence.ROUND_MARKER:
        problems.append("the shared marker name equals wc_convergence.ROUND_MARKER")
    if wc_convergence.ROUND_MARKER_RE.search(sample) or wc_convergence.ROUND_MARKER_OPEN_RE.search(sample):
        problems.append("wc_convergence's marker patterns match a shared-reviewer marker")
    return problems


def main():
    problems = check()
    for p in problems:
        print("::error::verify-shared-review-marker-disjoint: " + p)
    if "--self-test" in sys.argv:
        ok = bool(wc_convergence.ROUND_MARKER_OPEN_RE.search("<!-- wing-commander-convergence-round: {}"))
        if not ok:
            print("::error::self-test: ROUND_MARKER_OPEN_RE no longer matches its own marker")
            return 1
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
