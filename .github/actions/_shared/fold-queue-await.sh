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
# MAX_WAIT_MINUTES), UNCORRELATED_IMPLEMENT_GRACE_MINUTES (default 5, T046 --
# how much longer than STALE_AFTER_MINUTES an implement-kind head ticket
# still uncorrelated (no rounds[round].implement_run_id recorded yet) is
# given before it is reclaimed outright).
#
# On success, prints `round=<n>` and `granted=true` (the caller decides
# which of its own outputs, if any, to publish these under) and exits 0.
# On timeout, prints an `::error::` line and exits 1 -- a hard stop, never
# a silent pass-through, matching wing-commander-fold-queue-admit's own
# failure contract. specs/074-serialized-fold-dispatch T049: waiting behind
# a CORRELATED, confirmed-alive implement-kind OR act-kind head ticket
# extends this deadline instead of failing at it -- a real implement cycle
# routinely runs well past MAX_WAIT_MINUTES's default (recent runs: 16-125
# minutes), and an act-kind leg can be held just as long awaiting
# environment approval (confirm-timeout-minutes defaults to 1440 = 24h);
# a review posted during either window must still be folded, not dropped
# with a hard failure just because the run it is queued behind is
# legitimately still working. T060 (maintainer review of #821, B8): "alive"
# means any status but "completed" (not an allowlist of "in_progress"/
# "queued" alone), so a run paused on "waiting" (environment approval) or a
# redispatched run (T055) reporting any other non-terminal status also
# extends, not just hard-fails.
set -uo pipefail

: "${SPEC_DIR:?fold-queue-await.sh: SPEC_DIR is required}"
: "${TOKEN:?fold-queue-await.sh: TOKEN is required}"

# T068 (maintainer review of #821, B9): TOKEN is always this waiter's own
# ticket, shaped "run-<RUN_ID>-<kind>" (fold-queue-ledger.sh's enqueue/
# claim-dispatch/claim-redispatch). Parsed once so the loop below can tell
# "the head ticket is some OTHER ticket this same run still owns" (e.g. run
# A's own act-kind ticket, orphaned because its release step never ran)
# from "the head ticket belongs to a genuinely different, still-live run" --
# the former can never be confirmed alive by asking A's own run status,
# since A is this very waiter and is of course still in_progress.
# Not for an implement ticket: its "run-<id>" names the DISPATCHING run, not
# this waiter (implement run Y waits on run-X-implement), so treating X's
# other tickets as this waiter's own orphans would reclaim a live run's
# ticket without a liveness check (review of #821, round 4). MY_RUN_ID stays
# empty there and the own-orphan check below never fires.
MY_RUN_ID=""
case "$TOKEN" in
  *-implement) ;;
  *)
    MY_RUN_ID="${TOKEN%-*}"
    MY_RUN_ID="${MY_RUN_ID#run-}"
    ;;
esac

if ! declare -F wc_fold_queue_run_status >/dev/null; then
  echo "::error::fold-queue-await.sh: caller must define and 'export -f wc_fold_queue_run_status' before invoking this script (see header comment) -- Gate 12 forbids a gh call inside a _shared/ script, so the actual gh api call must live in the composite's own step." >&2
  exit 1
fi

MAX_WAIT_MINUTES="${MAX_WAIT_MINUTES:-30}"
POLL_INTERVAL_SECONDS="${POLL_INTERVAL_SECONDS:-10}"
STALE_AFTER_MINUTES="${STALE_AFTER_MINUTES:-10}"
UNCORRELATED_IMPLEMENT_GRACE_MINUTES="${UNCORRELATED_IMPLEMENT_GRACE_MINUTES:-5}"

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

  # T068: the head ticket belongs to THIS SAME run (head_run_id == our own
  # run id, parsed from TOKEN above) but isn't the ticket we are ourselves
  # waiting for -- it can only be an earlier ticket of ours that was never
  # released (our run's act-kind leg job crashed or lost its runner before
  # its own always() release step ran). Asking "is head_run_id alive?"
  # always answers yes (we ARE that run, still executing this very poll),
  # so neither the deadline-extension nor the staleness liveness check
  # below may trust that self-answer for this one case.
  own_orphaned_head="false"
  if [ -n "$MY_RUN_ID" ] && [ -n "$head_run_id" ] && [ "$head_run_id" = "$MY_RUN_ID" ] && [ "$head_token" != "$TOKEN" ]; then
    own_orphaned_head="true"
  fi

  if [ "$position" = "0" ] && [ "$granted" = "true" ]; then
    echo "round=$round"
    echo "granted=true"
    exit 0
  fi

  now_ts=$(date +%s)
  if [ "$now_ts" -ge "$deadline" ]; then
    # T049: before failing, check whether the head is a CORRELATED,
    # confirmed-alive ticket -- if so, extend the deadline instead of
    # hard-failing. A normal implement cycle routinely runs well past
    # MAX_WAIT_MINUTES's default (recent runs: 16-125 minutes; 9 of 15
    # exceeded 30), and a review posted during that window must still be
    # folded, not dropped just because the run it is queued behind is
    # legitimately still working.
    #
    # T060 (maintainer review of #821, B8) extends this two ways: (1) ANY
    # non-"completed" status counts as alive, not just "in_progress"/
    # "queued" -- a run paused on an environment protection-rule approval
    # reports "waiting", and a redispatched run (T055) can report any of
    # these at the moment this check runs; the stale-reclaim liveness check
    # just below already treats "not completed" (and not empty) as alive
    # for the identical reason, so this mirrors it instead of a narrower
    # allowlist that silently drifts from it. (2) An `act`-kind head can
    # also be legitimately held for a long time -- a leg awaiting
    # environment approval is bounded by the calling stage's own
    # confirm-timeout-minutes (default 1440 = 24h), not by an implement
    # cycle's runtime -- so it now gets the identical extension, using
    # head-run-id directly: unlike an implement-kind ticket, an act-kind
    # ticket's own run_id IS its real owning run (research.md D6).
    extend="false"
    live_run_id=""
    # T068: never extend for our own orphaned head -- see where
    # own_orphaned_head is computed above. Asking wc_fold_queue_run_status
    # about our own run id always reports "alive" (we are the one asking),
    # which would extend the deadline forever rather than letting the
    # stale-reclaim check below clear the orphan and let us proceed.
    if [ "$own_orphaned_head" != "true" ]; then
      if [ "$head_kind" = "implement" ] && [ -n "$round" ]; then
        round_out="$(SPEC_DIR="$SPEC_DIR" ROUND="$round" bash "$LEDGER" peek-round)"
        live_run_id="$(printf '%s\n' "$round_out" | grep '^implement-run-id=' | cut -d= -f2-)"
      elif [ "$head_kind" = "act" ]; then
        live_run_id="$head_run_id"
      fi
    fi
    if [ -n "$live_run_id" ]; then
      live_status="$(wc_fold_queue_run_status "$live_run_id")"
      if [ -n "$live_status" ] && [ "$live_status" != "completed" ]; then
        extend="true"
      fi
    fi
    if [ "$extend" = "true" ]; then
      deadline=$(( now_ts + MAX_WAIT_MINUTES * 60 ))
    else
      # T064 (maintainer review of #821, B6): our own TOKEN is still sitting
      # in the queue (not yet granted, by construction -- the granted check
      # above already returned) -- best-effort abandon it before giving up,
      # so the next waiter behind it isn't stuck watching a dead ticket
      # crawl its way to the head only to need its own stale-reclaim pass
      # once it gets there. `|| true`: a failed abandon here must not mask
      # the real timeout error below.
      SPEC_DIR="$SPEC_DIR" TOKEN="$TOKEN" bash "$LEDGER" abandon >/dev/null 2>&1 || true

      # Callers capture this script's stdout via command substitution (both
      # wing-commander-fold-queue-admit's own wait and
      # wing-commander-fold-queue-claim-dispatch's requeue-reawait loop), so
      # the failure line goes to stderr -- stdout on a successful exit is
      # exactly the two `key=value` lines above, nothing else.
      echo "::error::fold-queue-await.sh: timed out after ${MAX_WAIT_MINUTES}m waiting for ticket $TOKEN (spec-dir=$SPEC_DIR) to be granted -- current head is $head_token (run $head_run_id). This ticket was abandoned (removed from the queue) so it does not block the next waiter." >&2
      exit 1
    fi
  fi

  # research.md D6 (extended by specs/074-serialized-fold-dispatch T039): a
  # waiter that has watched the SAME head ticket sit granted for longer
  # than stale-after-minutes independently confirms (via the caller's
  # exported wc_fold_queue_run_status -- see this file's header) that its
  # owning run is no longer active, then reclaims it. An implement-kind
  # head ticket's own run_id is the DISPATCHING run that enqueued it, not
  # the real implement.yml run holding the ticket, so staleness for that
  # kind is checked against the round's correlated implement-run-id
  # instead.
  if [ -n "$head_token" ] && [ "$head_token" != "$TOKEN" ] && [ -n "$head_granted_at" ]; then
    head_granted_epoch=$(date -u -d "$head_granted_at" +%s 2>/dev/null) || head_granted_epoch=0
    if [ "$head_granted_epoch" -gt 0 ]; then
      age_minutes=$(( (now_ts - head_granted_epoch) / 60 ))
      if [ "$age_minutes" -ge "$STALE_AFTER_MINUTES" ]; then
        liveness_run_id="$head_run_id"
        skip_reclaim="false"
        reclaim_unconditionally="false"
        if [ "$own_orphaned_head" = "true" ]; then
          # T068: the head is our own run's earlier, un-released ticket --
          # asking wc_fold_queue_run_status about our own run id always
          # reports "alive" (we are the one asking), so that self-check is
          # never trustworthy here. Reclaim once stale, same as the
          # already-uncorrelated-implement-head backstop below.
          reclaim_unconditionally="true"
        elif [ "$head_kind" = "implement" ]; then
          round_out="$(SPEC_DIR="$SPEC_DIR" ROUND="$round" bash "$LEDGER" peek-round)"
          liveness_run_id="$(printf '%s\n' "$round_out" | grep '^implement-run-id=' | cut -d= -f2-)"
          if [ -z "$liveness_run_id" ]; then
            # T046: record-implement-run normally lands within seconds of
            # the ticket's grant (the same job, right after its own gh
            # workflow run call) -- an implement-kind head still
            # uncorrelated after stale-after-minutes PLUS this grace period
            # has no recorded run to check liveness against -- including a
            # live run whose correlation poll missed, which can lose its
            # ticket here (self-correlation is the follow-up)
            # (dispatch-once's own cleanup step should already have
            # released a standalone-mode/failed-dispatch/unfound-run-url
            # ticket before this point -- this is the backstop for
            # whatever gap remains) and is reclaimed unconditionally
            # rather than skipped forever.
            if [ "$age_minutes" -ge $(( STALE_AFTER_MINUTES + UNCORRELATED_IMPLEMENT_GRACE_MINUTES )) ]; then
              reclaim_unconditionally="true"
            else
              skip_reclaim="true"
            fi
          fi
        fi
        if [ "$reclaim_unconditionally" = "true" ]; then
          SPEC_DIR="$SPEC_DIR" STALE_TOKEN="$head_token" bash "$LEDGER" reclaim-stale >/dev/null || true
        elif [ "$skip_reclaim" != "true" ]; then
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
