#!/usr/bin/env bash
# Entry point for the auto-update-spec-kit behavioral tests.
#
#   run-tests.sh              # every suite
#   run-tests.sh t2_settle    # one suite (name with or without extension)
#
# Exits non-zero if any assertion in any suite fails. See README.md.
set -uo pipefail

SP="$(cd "$(dirname "$0")" && pwd)"
cd "$SP"

WC_TEST_WORK="$(mktemp -d)"
export WC_TEST_WORK
trap 'rm -rf "$WC_TEST_WORK"' EXIT

SUITES=(t1_detect.sh t2_settle.sh t3_healthcheck.sh t4_verify.sh t5_act.sh t6_reply.sh t7_gating.py t8_scaffold.sh t9_prepare.sh t10_notes.sh)
if [ "$#" -gt 0 ]; then
  want="${1%.sh}"; want="${want%.py}"
  SUITES=()
  for f in t*.sh t*.py; do
    [ "${f%.sh}" = "$want" ] || [ "${f%.py}" = "$want" ] && SUITES+=("$f")
  done
  if [ "${#SUITES[@]}" -eq 0 ]; then
    echo "no suite named '$1'" >&2; exit 2
  fi
fi

# Same validating probe lib.sh uses — `command -v python3` succeeds on Windows
# even when it is the Microsoft Store stub that fails on every invocation.
PY=""
for c in "${WC_PYTHON:-}" python3 python py; do
  [ -n "$c" ] || continue
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys' >/dev/null 2>&1; then
    PY="$(command -v "$c")"; break
  fi
done
if [ -z "$PY" ]; then
  echo "auto-update-spec-kit-tests: no working python3/python on PATH." >&2; exit 2
fi
export WC_PYTHON="$PY"
TOTAL_P=0; TOTAL_F=0; BROKEN=()

for suite in "${SUITES[@]}"; do
  echo
  echo "############################## $suite ##############################"
  if [ "${suite##*.}" = "py" ]; then
    output="$("$PY" "$SP/$suite" 2>&1)"; rc=$?
  else
    output="$(bash "$SP/$suite" 2>&1)"; rc=$?
  fi
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
echo "auto-update-spec-kit tests — passed: $TOTAL_P   failed: $TOTAL_F"
if [ "${#BROKEN[@]}" -gt 0 ]; then
  printf 'broken suite: %s\n' "${BROKEN[@]}"
fi
if [ -n "${GITHUB_STEP_SUMMARY:-}" ] && [ -w "${GITHUB_STEP_SUMMARY:-/dev/null}" ]; then
  {
    echo "### auto-update-spec-kit behavioral tests"
    echo ""
    echo "- passed: **$TOTAL_P**"
    echo "- failed: **$TOTAL_F**"
  } >> "$GITHUB_STEP_SUMMARY"
fi
if [ "$TOTAL_F" -gt 0 ] || [ "${#BROKEN[@]}" -gt 0 ]; then
  echo "::error::auto-update-spec-kit behavioral tests failed ($TOTAL_F assertion failure(s), ${#BROKEN[@]} broken suite(s))"
  exit 1
fi
exit 0
