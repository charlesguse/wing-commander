#!/usr/bin/env bash
# Pure decision function for the waiting allowance the `poll` step applies
# to a merge gate that reads `blocked-pending` (specs/070-blocked-gate-
# dry-run, contracts/gate-allowance-decision.md): a merge state that is
# BLOCKED with no resolved check in its statusCheckRollup, per
# auto-release-e2e-merge-decision.sh step 6. Takes the merge-decision
# token just printed for this gate, this gate's own blocked-since marker,
# the loop's current elapsed time, and the configured allowance, and
# decides whether to start timing, keep waiting, declare the gate
# stalled, or clear the timer -- never calls `gh` or the network itself,
# and reads nothing beyond its own arguments (Constitution VIII,
# research.md D2).
#
# Invoke with `bash .github/actions/_shared/auto-release-e2e-gate-
# allowance-decision.sh "$MERGE_DECISION" "$BLOCKED_SINCE" "$NOW"
# "$ALLOWANCE_SECONDS"`.
#
# MERGE_DECISION is the exact token auto-release-e2e-merge-decision.sh
# printed this iteration for this gate (its first line, if `merge`).
# BLOCKED_SINCE is this gate's `gate_blocked_since[$prefix]` value carried
# from the previous iteration -- an integer `$SECONDS` snapshot, or the
# empty string if this gate has not been continuously observed
# blocked-pending since its last reset. NOW is the loop's current
# `$SECONDS`. ALLOWANCE_SECONDS is the configured allowance in seconds
# (`GATE_BLOCKED_ALLOWANCE_SECONDS`, 1200/20 minutes in production).
#
# Prints one of `clear` / `start` / `wait` / `stall` on stdout:
#   - `clear`: MERGE_DECISION is not blocked-pending -- the gate has left
#     the blocked-with-unresolved-checks state, or never entered it this
#     iteration. The caller resets blocked_since to empty (FR-005).
#   - `start`: MERGE_DECISION is blocked-pending and blocked_since was
#     empty -- the first continuous observation. The caller records
#     blocked_since = NOW.
#   - `wait`: MERGE_DECISION is blocked-pending, blocked_since is set, and
#     elapsed time is under the allowance. The caller keeps polling,
#     blocked_since unchanged.
#   - `stall`: MERGE_DECISION is blocked-pending, blocked_since is set,
#     and elapsed time has reached the allowance. The caller writes the
#     fail-gate-stall verdict and exits.
# Never calls write_verdict/emit_verdict itself -- exactly like the
# merge-decision script, all durable action stays in the `poll` step's
# own bash. Never sourced, matching auto-release-verdict.sh's invocation
# idiom.
set -uo pipefail

merge_decision="${1:?merge decision required}"
blocked_since="${2:-}"
now="${3:?current elapsed seconds required}"
allowance_seconds="${4:?allowance seconds required}"

if [ "$merge_decision" != "blocked-pending" ]; then
  echo "clear"
  exit 0
fi

if [ -z "$blocked_since" ]; then
  echo "start"
  exit 0
fi

if [ $((now - blocked_since)) -ge "$allowance_seconds" ]; then
  echo "stall"
  exit 0
fi

echo "wait"
