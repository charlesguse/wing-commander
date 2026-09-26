#!/usr/bin/env bash
# Pure decision half of the container-mode evidence checks
# (specs/067-e2e-container-image-evidence, contracts/
# container-evidence-decision-script.md): the workflow step performs the
# `gh` reads and captures their raw results; this script maps those
# captured results to the {failing_check, expected, observed} triple that
# feeds auto-release-verdict.sh, with no `gh` call and no network access of
# its own -- callable directly by the new gate's fixtures (SC-006).
#
# Also holds classify_read_status() (research.md D6/T004's shared
# classification, exact string test also written once here), sourced by
# both new evidence steps in auto-release.yml (the container-evidence-
# config step and the poll step's execution-evidence check) so the
# exit-status/stderr -> read_status mapping exists in exactly one place
# (CLAUDE.md "Shared logic has exactly one home") -- reusing the same
# rate-limit-text-grep idiom this workflow's own write_repeated_failure_verdict
# helper already applies. plan.md's Structure Decision reserves exactly one
# new `.github/actions/_shared/` file for this feature, so the classifier
# lives here rather than in a second new file.
#
# Usage as a decision (never sourced for this half):
#   bash .github/actions/_shared/auto-release-container-evidence-decision.sh \
#     <config|execution> <ok|unreadable|rate-limited> "$EXPECTED" "$OBSERVED"
# prints three lines: failing_check=..., expected=..., observed=... .
#
# Usage as a classifier (sourced):
#   source .github/actions/_shared/auto-release-container-evidence-decision.sh
#   read_status="$(classify_read_status "$rc" "$errtext")"
set -uo pipefail

# classify_read_status EXIT_STATUS ERR_TEXT -> prints ok|unreadable|rate-limited
classify_read_status() {
  local rc="$1" errtext="$2"
  if [ "$rc" -eq 0 ]; then
    printf 'ok\n'
  elif printf '%s' "$errtext" | grep -qi 'rate limit'; then
    printf 'rate-limited\n'
  else
    printf 'unreadable\n'
  fi
}

# The decision CLI below only runs when this file is EXECUTED (bash
# .../auto-release-container-evidence-decision.sh ...), not when it is
# sourced purely to pick up classify_read_status above.
if [ "${BASH_SOURCE[0]}" = "${0}" ]; then
  check="${1:?auto-release-container-evidence-decision.sh: missing check (config|execution)}"
  read_status="${2:?auto-release-container-evidence-decision.sh: missing read_status (ok|unreadable|rate-limited)}"
  expected="${3:-}"
  observed="${4:-}"

  failing_check=""
  case "$read_status" in
    unreadable)
      failing_check="container-mode evidence unreadable"
      ;;
    rate-limited)
      failing_check="container-mode evidence rate-limited"
      ;;
    ok)
      case "$check" in
        config)
          if [ -z "$observed" ]; then
            failing_check="container image not configured on the test repository"
          elif [ "$observed" != "$expected" ]; then
            failing_check="container image configured but does not match this repository's pin"
          fi
          ;;
        execution)
          if [ -n "$observed" ]; then
            failing_check="container image configured but stage jobs did not execute inside a container"
          fi
          ;;
        *)
          echo "auto-release-container-evidence-decision.sh: unknown check '$check' (want config|execution)" >&2
          exit 1
          ;;
      esac
      ;;
    *)
      echo "auto-release-container-evidence-decision.sh: unknown read_status '$read_status' (want ok|unreadable|rate-limited)" >&2
      exit 1
      ;;
  esac

  printf 'failing_check=%s\n' "$failing_check"
  printf 'expected=%s\n' "$expected"
  printf 'observed=%s\n' "$observed"
fi
