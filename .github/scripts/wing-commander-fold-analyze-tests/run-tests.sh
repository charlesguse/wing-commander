#!/usr/bin/env bash
# Fixtures for wing-commander-fold-analyze's deterministic hold/dispatch
# decision (decide.py) and its stage mode's fold-section scoping
# (specs/116-review-convergence-analyze, contracts/fold-analyze.md, SC-004,
# SC-005). Lives here, not under .github/actions/, because gate discovery
# reads only .github/scripts/ (Gate 119). Registered in lint-workflows.yml,
# so CI and `python .github/scripts/run-local-gates.py` both run it:
#   bash .github/scripts/wing-commander-fold-analyze-tests/run-tests.sh
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 -I "$HERE/test_decide.py"
python3 -I "$HERE/test_fold_hold_release.py"
