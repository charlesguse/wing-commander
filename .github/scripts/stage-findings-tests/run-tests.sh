#!/usr/bin/env bash
# Fixture harness for wing-commander-stage-findings (FR-030). The actual
# cases live in run_fixtures.py, which drives the shipped `run:` blocks via
# wc_shell_harness the same way Gate 11/the metrics-summary gate already
# do (research.md D14) -- this wrapper exists only so the harness has the
# run-tests.sh entry point every other composite/workflow test suite in
# this repository is invoked by.
#
# Lives under .github/scripts/stage-findings-tests/ (Maintainer review item
# 11), not .github/actions/wing-commander-stage-findings/tests/ where it
# first shipped -- wc_gate_registry.gate_scripts() only discovers
# .github/scripts/*/run-tests.sh, so a harness at the earlier path was
# invisible to run-local-gates.py and CLAUDE.md's "run the suite locally"
# instruction was false for it.
set -euo pipefail
exec python3 "$(dirname "${BASH_SOURCE[0]}")/run_fixtures.py"
