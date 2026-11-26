#!/usr/bin/env python3
"""Gate: runs the shared reviewer's fixtures (specs/127-shared-pr-reviewer).

Runs every test_*.py under .github/scripts/tests/ that tests wc_shared_review
or shared_review_compare: record build/parse, verdict order, the blocking
rule, finding identity and transitions, run confirmation, guard and budget
(SC-002, SC-004..SC-007). Exit 1 on any failure.
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TESTS = os.path.join(HERE, "tests")


def main():
    sys.path.insert(0, HERE)
    suite = unittest.TestSuite()
    suite.addTests(unittest.defaultTestLoader.discover(TESTS, pattern="test_*shared_review*.py"))
    if suite.countTestCases() == 0:
        print("::error::verify-shared-review-fixtures: no fixtures found under .github/scripts/tests")
        return 1
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
