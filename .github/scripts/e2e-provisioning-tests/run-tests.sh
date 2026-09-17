#!/usr/bin/env bash
# Entry point for the e2e-provisioning behavioral tests.
#
#   run-tests.sh                 # every suite
#   run-tests.sh t2_idempotent   # one suite (name with or without extension)
#
# Exits non-zero if any assertion in any suite fails. Adapted from
# .github/scripts/auto-update-spec-kit-tests/run-tests.sh.
set -uo pipefail

SP="$(cd "$(dirname "$0")" && pwd)"
cd "$SP"

WC_TEST_WORK="$(mktemp -d)"
export WC_TEST_WORK
trap 'rm -rf "$WC_TEST_WORK"' EXIT

SUITES=(t1_new_target.sh t2_idempotent.sh t3_converge_after_install.sh t4_refuse_self.sh t5_refuse_foreign.sh t6_no_delete.sh t7_readiness_workflow.sh)
if [ "$#" -gt 0 ]; then
  want="${1%.sh}"
  SUITES=()
  for f in t*.sh; do
    [ "${f%.sh}" = "$want" ] && SUITES+=("$f")
  done
  if [ "${#SUITES[@]}" -eq 0 ]; then
    echo "no suite named '$1'" >&2; exit 2
  fi
fi

PY=""
for c in "${WC_PYTHON:-}" python3 python py; do
  [ -n "$c" ] || continue
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys' >/dev/null 2>&1; then
    PY="$(command -v "$c")"; break
  fi
done
if [ -z "$PY" ]; then
  echo "e2e-provisioning-tests: no working python3/python on PATH." >&2; exit 2
fi
export WC_PYTHON="$PY"
TOTAL_P=0; TOTAL_F=0; BROKEN=()

for suite in "${SUITES[@]}"; do
  echo
  echo "############################## $suite ##############################"
  output="$(bash "$SP/$suite" 2>&1)"; rc=$?
  printf '%s\n' "$output"
  line="$(printf '%s' "$output" | grep -E '^passed: ' | tail -1)"
  if [ -z "$line" ]; then
    echo "!! $suite produced no result line (exit $rc) — treating as broken"
    BROKEN+=("$suite"); continue
  fi
  p="$(printf '%s' "$line" | sed -E 's/passed: ([0-9]+).*/\1/')"
  f="$(printf '%s' "$line" | sed -E 's/.*failed: ([0-9]+)/\1/')"
  TOTAL_P=$((TOTAL_P + p)); TOTAL_F=$((TOTAL_F + f))
done

echo
echo "======================================================================"
echo "e2e-provisioning tests — passed: $TOTAL_P   failed: $TOTAL_F"
if [ "${#BROKEN[@]}" -gt 0 ]; then
  printf 'broken suite: %s\n' "${BROKEN[@]}"
fi
if [ -n "${GITHUB_STEP_SUMMARY:-}" ] && [ -w "${GITHUB_STEP_SUMMARY:-/dev/null}" ]; then
  {
    echo "### e2e-provisioning behavioral tests"
    echo ""
    echo "- passed: **$TOTAL_P**"
    echo "- failed: **$TOTAL_F**"
  } >> "$GITHUB_STEP_SUMMARY"
fi
if [ "$TOTAL_F" -gt 0 ] || [ "${#BROKEN[@]}" -gt 0 ]; then
  echo "::error::e2e-provisioning behavioral tests failed ($TOTAL_F assertion failure(s), ${#BROKEN[@]} broken suite(s))"
  exit 1
fi
exit 0
