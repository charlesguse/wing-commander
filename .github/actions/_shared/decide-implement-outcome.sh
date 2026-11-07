#!/usr/bin/env bash
# .github/actions/_shared/decide-implement-outcome.sh
#
# The one home of the implement loop's stop rule (specs/117 research D5/D6).
# Spec 059's rule ended the loop on a single healthy cycle that checked
# nothing new and landed no converge commit, which stranded #737 and #1022
# with work an ordinary next cycle could have done. The loop now hands off
# only when continuing cannot help: a validated agent blocker, or the
# iteration cap.
#
# Invoke with
#   bash "$GITHUB_ACTION_PATH/../_shared/decide-implement-outcome.sh"
# with the cycle's facts in the environment (counts are IMPLEMENTATION tasks
# only, as count-tasks-checkboxes.sh classifies them):
#   OK TRUNCATED IMPL_CHECKED_BASE IMPL_CHECKED_TIP IMPL_UNCHECKED_TIP
#   CONVERGE_SHA ITERATION MAX_ITERATIONS BLOCKER_VALID BLOCKER_TEXT
#   IMPL_UNCHECKED_IDS_BASE IMPL_IDS_TIP CARRIED_DROPPED_IDS (space-separated
#   task ids) WRITE_BOUNDARY_ALL_OOB (the write-boundary classifier's
#   all-unchecked-out-of-boundary, already in both read-back arms' env)
# specs/123 adds BUILDABLE_CHECKED_BASE BUILDABLE_CHECKED_TIP
# BUILDABLE_UNCHECKED_TIP (the buildable view): progress uses the buildable
# checked delta, and a cap or blocker hands off only while buildable work
# (plus dropped ids) remains. Unset, they fall back to the IMPL_* values.
# Task identity (owner decisions A and C on #992, option (a)): an id that was
# unchecked implementation work at base, or that an earlier cycle dropped
# (CARRIED_DROPPED_IDS, spec-meta.json's dropped_task_ids at the cycle base),
# but is not implementation at the tip (retagged [maintainer], reworded as a
# standing instruction, or deleted) still counts as outstanding. The caller
# persists dropped-ids as the next cycle's carried set, so an id leaves it
# only by showing up as implementation work again (or a maintainer removing
# it from dropped_task_ids), and a tasks.md edit cannot reach converged in
# the cycle that made it or any later one. Lines without an id cannot be
# tracked; ids converge adds are unaffected.
# Prints single-line `key=value` lines shaped as $GITHUB_OUTPUT entries:
#   converged=  progressed=  handoff=  stall-reason=  stall-comment=
#   dropped-ids=  (the ids above, space-separated)
# For a cycle that is not healthy, or was truncated, the stop rule does not
# apply: converged is false for a truncated cycle and empty for an unhealthy
# one, progressed is empty, handoff is false.
set -uo pipefail

ok="${OK:-false}"
truncated="${TRUNCATED:-false}"
base="${IMPL_CHECKED_BASE:-0}"
tip="${IMPL_CHECKED_TIP:-0}"
unchecked="${IMPL_UNCHECKED_TIP:-1}"
converge_sha="${CONVERGE_SHA:-}"
iteration="${ITERATION:-0}"
max="${MAX_ITERATIONS:-0}"
blocker_valid="${BLOCKER_VALID:-false}"
blocker_text="${BLOCKER_TEXT:-}"
all_oob="${WRITE_BOUNDARY_ALL_OOB:-false}"

# A non-numeric count would make `[ -gt ]` error to stderr and take the false
# branch with exit 0, silently disabling the cap hand-off. Normalise to base-10
# integers; an unusable unchecked count stays "unknown work remains" (1), the
# safe side for the convergence test.
num() { case "$1" in ''|*[!0-9]*) printf '%s' "$2" ;; *) printf '%d' "$((10#$1))" ;; esac; }
base="$(num "$base" 0)"
tip="$(num "$tip" 0)"
unchecked="$(num "$unchecked" 1)"

dropped=""
dropped_count=0
for id in ${IMPL_UNCHECKED_IDS_BASE:-} ${CARRIED_DROPPED_IDS:-}; do
  case " ${IMPL_IDS_TIP:-} " in *" $id "*) continue ;; esac
  case " $dropped " in *" $id "*) continue ;; esac
  dropped="${dropped:+$dropped }$id"
  dropped_count=$((dropped_count + 1))
done
unchecked=$((unchecked + dropped_count))
# specs/123: progress and the cap/blocker hand-off key on BUILDABLE tasks (a
# folded review finding or a human-only line must not consume the budget or
# hold a hand-off open). Unset means a caller that predates the buildable
# view: fall back to the implementation counts, the old behaviour.
#
# All-or-nothing: the buildable view is used only when the counter's
# BUILDABLE_UNCHECKED_TIP is present. If it is empty (the counter output was
# lost), base, tip and unchecked ALL come from the implementation counts, so
# progress is never computed across two different bases.
if [ -n "${BUILDABLE_UNCHECKED_TIP:-}" ]; then
  b_base="$(num "${BUILDABLE_CHECKED_BASE:-}" 0)"
  b_tip="$(num "${BUILDABLE_CHECKED_TIP:-}" 0)"
  b_unchecked="$(num "$BUILDABLE_UNCHECKED_TIP" 1)"
  b_unchecked=$((b_unchecked + dropped_count))
else
  b_base="$base"
  b_tip="$tip"
  b_unchecked="$unchecked"
fi
iteration="$(num "$iteration" 0)"
max="$(num "$max" 0)"

converged=""
progressed=""
handoff=false
stall_reason=""
stall_comment=""

if [ "$ok" = "true" ] && [ "$truncated" = "true" ]; then
  converged=false
elif [ "$ok" = "true" ]; then
  if [ "$b_tip" -gt "$b_base" ]; then progressed=true; else progressed=false; fi
  if [ "$unchecked" -eq 0 ]; then
    converged=true
  else
    converged=false
    if [ "$progressed" = "true" ] || [ -n "$converge_sha" ]; then
      :
    elif [ "$b_unchecked" -eq 0 ]; then
      # Only folded review findings remain: nothing buildable is stuck, so
      # neither a blocker nor the cap is a hand-off; finalize proceeds.
      :
    elif [ "$blocker_valid" = "true" ]; then
      handoff=true
      stall_reason="the agent reported a blocker: $blocker_text"
    elif [ "$max" -gt 0 ] && [ "$iteration" -ge "$max" ]; then
      handoff=true
      stall_reason="the iteration cap ($max) was reached"
    fi
  fi
fi

dropped_note=""
if [ -n "$dropped" ]; then
  dropped_note=" ($dropped_count of them reclassified or removed from tasks.md while unfinished: ${dropped// /, }; a maintainer accepts such a change by removing the id from dropped_task_ids in spec-meta.json)"
fi

# FR-006: a stop with implementation outstanding is always reported, whether
# it came from a hand-off, from the loop running out of iterations, or from a
# routed remainder (specs/090: the read-back ends the loop when every
# unchecked line is outside the write boundary and no id was dropped).
if [ "$ok" = "true" ] && [ "$converged" != "true" ] && [ "$unchecked" -gt 0 ]; then
  if [ "$handoff" = "true" ]; then
    stall_comment="Implement stopped with $unchecked implementation task(s) still unchecked$dropped_note: $stall_reason."
  elif [ "$max" -gt 0 ] && [ "$iteration" -ge "$max" ] && [ "$b_unchecked" -gt 0 ]; then
    stall_reason="the iteration cap ($max) was reached"
    if [ "$blocker_valid" = "true" ]; then
      stall_reason="$stall_reason; the agent also reported a blocker: $blocker_text"
    fi
    stall_comment="Implement stopped with $unchecked implementation task(s) still unchecked$dropped_note: $stall_reason."
  elif [ "$truncated" = "false" ] && [ "$all_oob" = "true" ] && [ -z "$dropped" ]; then
    stall_reason="the remaining implementation work is outside the implement stage's write boundary and was routed"
    stall_comment="Implement stopped with $unchecked implementation task(s) still unchecked: $stall_reason."
  fi
fi

# specs/123 FR-003: the one-line cycle outcome. Callers append it to the
# lifecycle comment and the metrics record verbatim (single home). TURNS_USED
# and TURN_BUDGET come from the run's execution record; unknown renders "?".
ticked=$((b_tip > b_base ? b_tip - b_base : 0))
turns_used="${TURNS_USED:-}"; turn_budget="${TURN_BUDGET:-}"
case "$turns_used" in ''|*[!0-9]*) turns_used="?" ;; esac
case "$turn_budget" in ''|*[!0-9]*) turn_budget="?" ;; esac
cycle_outcome="Cycle $iteration: ticked $ticked buildable task(s), $b_unchecked buildable remaining, used $turns_used of $turn_budget turns."

printf 'cycle-outcome=%s\n' "$cycle_outcome"
printf 'converged=%s\n' "$converged"
printf 'progressed=%s\n' "$progressed"
printf 'handoff=%s\n' "$handoff"
printf 'stall-reason=%s\n' "$stall_reason"
printf 'stall-comment=%s\n' "$stall_comment"
printf 'dropped-ids=%s\n' "$dropped"
