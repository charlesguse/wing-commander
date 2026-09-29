#!/usr/bin/env bash
# .github/actions/_shared/fold-queue-await.sh
#
# Single home for "poll the fold-queue ledger until a given token is
# granted, reclaiming a stale head ticket along the way" -- the wait
# primitive both `wing-commander-fold-queue-admit` (its own first grant)
# and `wing-commander-fold-queue-claim-dispatch` (research.md D4/D9's
# 2026-09-29 reconciliation with spec 075: a dispatch ticket requeued
# behind an outstanding `act` ticket awaits its own token being regranted
# through this exact code path, never a restated copy -- CLAUDE.md's
# "Shared logic has exactly one home") need identically. Extracted from
# wing-commander-fold-queue-admit/action.yml's own step so both composites
# call it rather than diverging copies drifting apart on the next fix (the
# way research.md D6's implement-kind liveness fix would otherwise have
# needed to land twice).
#
# Invoke with `bash "$GITHUB_ACTION_PATH/../_shared/fold-queue-await.sh"`
# (never sourced -- matching this directory's existing convention).
#
# Gate 12 (lint-workflows.yml) hard-fails any `.github/actions/_shared/*.sh`
# that makes a `gh` call of its own -- a shared script is sourced from
# whatever composite step happens to invoke it, carrying THAT step's own
# GH_TOKEN, which Gate 12 cannot attribute to a specific, checkable call
# site. So the one `gh api` call the staleness check needs is NOT inlined
# here: the caller must define and `export -f` a `wc_fold_queue_run_status`
# shell function (one argument, a run id; prints the run's `status` field,
# or nothing on any failure) BEFORE invoking this script, so the literal
# `gh api` text lives in the composite's own step where Gate 12 can check
# its token -- both `wing-commander-fold-queue-admit` and
# `wing-commander-fold-queue-claim-dispatch` define the identical four-line
# function ahead of their own call into this script.
#
# Required env: SPEC_DIR, TOKEN, GH_TOKEN, GITHUB_REPOSITORY (unless
# LEDGER_REMOTE_URL overrides them for fixture use, matching
# fold-queue-ledger.sh's own override).
# Optional env: MAX_WAIT_MINUTES (default 30), POLL_INTERVAL_SECONDS
# (default 10), STALE_AFTER_MINUTES (default 10, must be smaller than
# MAX_WAIT_MINUTES).
#
# On success, prints `round=<n>` and `granted=true` (the caller decides
# which of its own outputs, if any, to publish these under) and exits 0.
# On timeout, prints an `::error::` line and exits 1 -- a hard stop, never
# a silent pass-through, matching wing-commander-fold-queue-admit's own
# failure contract.
set -uo pipefail

: "${SPEC_DIR:?fold-queue-await.sh: SPEC_DIR is required}"
: "${TOKEN:?fold-queue-await.sh: TOKEN is required}"

if ! declare -F wc_fold_queue_run_status >/dev/null; then
  echo "::error::fold-queue-await.sh: caller must define and 'export -f wc_fold_queue_run_status' before invoking this script (see header comment) -- Gate 12 forbids a gh call inside a _shared/ script, so the actual gh api call must live in the composite's own step." >&2
  exit 1
fi

MAX_WAIT_MINUTES="${MAX_WAIT_MINUTES:-30}"
POLL_INTERVAL_SECONDS="${POLL_INTERVAL_SECONDS:-10}"
STALE_AFTER_MINUTES="${STALE_AFTER_MINUTES:-10}"

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LEDGER="$HERE/fold-queue-ledger.sh"

start_ts=$(date +%s)
deadline=$(( start_ts + MAX_WAIT_MINUTES * 60 ))

while :; do
  peek_out="$(SPEC_DIR="$SPEC_DIR" PEEK_TOKEN="$TOKEN" bash "$LEDGER" peek)"
  position="$(printf '%s\n' "$peek_out" | grep '^position=' | cut -d= -f2-)"
  round="$(printf '%s\n' "$peek_out" | grep '^round=' | cut -d= -f2-)"
  granted="$(printf '%s\n' "$peek_out" | grep '^granted=' | cut -d= -f2-)"
  head_token="$(printf '%s\n' "$peek_out" | grep '^head-token=' | cut -d= -f2-)"
  head_run_id="$(printf '%s\n' "$peek_out" | grep '^head-run-id=' | cut -d= -f2-)"
  head_kind="$(printf '%s\n' "$peek_out" | grep '^head-kind=' | cut -d= -f2-)"
  head_granted_at="$(printf '%s\n' "$peek_out" | grep '^head-granted-at=' | cut -d= -f2-)"

  if [ "$position" = "0" ] && [ "$granted" = "true" ]; then
    echo "round=$round"
    echo "granted=true"
    exit 0
  fi

  now_ts=$(date +%s)
  if [ "$now_ts" -ge "$deadline" ]; then
    # Callers capture this script's stdout via command substitution (both
    # wing-commander-fold-queue-admit's own wait and
    # wing-commander-fold-queue-claim-dispatch's requeue-reawait loop), so
    # the failure line goes to stderr -- stdout on a successful exit is
    # exactly the two `key=value` lines above, nothing else.
    echo "::error::fold-queue-await.sh: timed out after ${MAX_WAIT_MINUTES}m waiting for ticket $TOKEN (spec-dir=$SPEC_DIR) to be granted -- current head is $head_token (run $head_run_id)." >&2
    exit 1
  fi

  # research.md D6 (extended by specs/074-serialized-fold-dispatch T039): a
  # waiter that has watched the SAME head ticket sit granted for longer
  # than stale-after-minutes independently confirms (via the caller's
  # exported wc_fold_queue_run_status -- see this file's header) that its
  # owning run is no longer active, then reclaims it. An implement-kind
  # head ticket's own run_id is the DISPATCHING run that enqueued it, not
  # the real implement.yml run holding the ticket, so staleness for that
  # kind is checked against the round's correlated implement-run-id
  # instead, skipping reclaim entirely until that correlation exists.
  if [ -n "$head_token" ] && [ "$head_token" != "$TOKEN" ] && [ -n "$head_granted_at" ]; then
    head_granted_epoch=$(date -u -d "$head_granted_at" +%s 2>/dev/null || echo 0)
    if [ "$head_granted_epoch" -gt 0 ]; then
      age_minutes=$(( (now_ts - head_granted_epoch) / 60 ))
      if [ "$age_minutes" -ge "$STALE_AFTER_MINUTES" ]; then
        liveness_run_id="$head_run_id"
        skip_reclaim="false"
        if [ "$head_kind" = "implement" ]; then
          round_out="$(SPEC_DIR="$SPEC_DIR" ROUND="$round" bash "$LEDGER" peek-round)"
          liveness_run_id="$(printf '%s\n' "$round_out" | grep '^implement-run-id=' | cut -d= -f2-)"
          if [ -z "$liveness_run_id" ]; then
            skip_reclaim="true"
          fi
        fi
        if [ "$skip_reclaim" != "true" ]; then
          head_status="$(wc_fold_queue_run_status "$liveness_run_id")"
          if [ -z "$head_status" ] || [ "$head_status" = "completed" ]; then
            SPEC_DIR="$SPEC_DIR" STALE_TOKEN="$head_token" bash "$LEDGER" reclaim-stale >/dev/null || true
          fi
        fi
      fi
    fi
  fi

  sleep "$POLL_INTERVAL_SECONDS"
done
