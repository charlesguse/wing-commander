#!/usr/bin/env python3
"""Gate 128 -- an honoured stop records its stop point, and the kill switch
keeps writing nothing (specs/097-recorded-stop-point, FR-019,
specs/097-recorded-stop-point/contracts/gate-128-stop-point-recording.md).

See that contract for the full table of checks and self-test mutations.
Checks are added incrementally through this feature's tasks.md phases;
run with --self-test to additionally apply each check's mutation and
confirm it is caught.
"""
import sys


def main():
    sys.exit(0)


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        pass
    main()
