#!/usr/bin/env bash
# Fixture harness for wing-commander-stage-findings (FR-030). The actual
# cases live in run_fixtures.py, which drives the shipped `run:` blocks via
# wc_shell_harness the same way Gate 11/the metrics-summary gate already
# do (research.md D14) -- this wrapper exists only so the harness has the
# run-tests.sh entry point every other composite/workflow test suite in
# this repository is invoked by.
set -euo pipefail
exec python3 "$(dirname "${BASH_SOURCE[0]}")/run_fixtures.py"
