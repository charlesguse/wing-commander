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
#   IMPL_UNCHECKED_IDS_BASE IMPL_IDS_TIP (space-separated task ids)
# Task identity (owner decision on #992, option (a)): an id that was
# unchecked implementation work at base but is not implementation at the tip
# (retagged [maintainer], reworded as a standing instruction, or deleted)
# still counts as outstanding, so editing tasks.md cannot reach converged.
# Lines without an id cannot be tracked; ids converge adds are unaffected.
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
for id in ${IMPL_UNCHECKED_IDS_BASE:-}; do
  case " ${IMPL_IDS_TIP:-} " in *" $id "*) continue ;; esac
  case " $dropped " in *" $id "*) continue ;; esac
  dropped="${dropped:+$dropped }$id"
  dropped_count=$((dropped_count + 1))
done
unchecked=$((unchecked + dropped_count))
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
  if [ "$tip" -gt "$base" ]; then progressed=true; else progressed=false; fi
  if [ "$unchecked" -eq 0 ]; then
    converged=true
  else
    converged=false
    if [ "$progressed" = "true" ] || [ -n "$converge_sha" ]; then
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
  dropped_note=" ($dropped_count of them reclassified or removed from tasks.md during the cycle: ${dropped// /, })"
fi

# FR-006: a stop with implementation outstanding is always reported, whether
# it came from a hand-off or from the loop running out of iterations.
if [ "$ok" = "true" ] && [ "$converged" != "true" ] && [ "$unchecked" -gt 0 ]; then
  if [ "$handoff" = "true" ]; then
    stall_comment="Implement stopped with $unchecked implementation task(s) still unchecked$dropped_note: $stall_reason."
  elif [ "$max" -gt 0 ] && [ "$iteration" -ge "$max" ]; then
    stall_reason="the iteration cap ($max) was reached"
    if [ "$blocker_valid" = "true" ]; then
      stall_reason="$stall_reason; the agent also reported a blocker: $blocker_text"
    fi
    stall_comment="Implement stopped with $unchecked implementation task(s) still unchecked$dropped_note: $stall_reason."
  fi
fi

printf 'converged=%s\n' "$converged"
printf 'progressed=%s\n' "$progressed"
printf 'handoff=%s\n' "$handoff"
printf 'stall-reason=%s\n' "$stall_reason"
printf 'stall-comment=%s\n' "$stall_comment"
printf 'dropped-ids=%s\n' "$dropped"
