#!/usr/bin/env bash
# Unit and replay tests for wc_convergence.py, the one home of the review
# loops' convergence arithmetic (specs/116-review-convergence-analyze,
# FR-004..FR-010, SC-001..SC-003): each FR-006 rule, the round-2
# record-only and round-5 budget cases, unattributable and invalid lines,
# main-merge exclusion, the round records the loops persist on the PR, and
# the parity of the review-until-clean skill's thrash_signals.py with the
# module's own CLI. Registered in lint-workflows.yml (Gate 165 fixtures), so
# CI and `python .github/scripts/run-local-gates.py` both run it:
#   bash .github/scripts/wc_convergence_tests/run-tests.sh
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 -I -m unittest discover -s "$HERE" -p 'test_*.py'
