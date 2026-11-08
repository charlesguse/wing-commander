#!/usr/bin/env bash
# .github/actions/_shared/migrate-stranded-review-lifecycles.sh
#
# specs/123-implement-task-completion FR-018: the one home of the decision
# whether a lifecycle stranded at stage `review` is handed off. Pure: no gh
# or git calls (Gate 12 keeps those in the calling workflow's own steps).
#
# Invoke with `bash` (never the file itself):
#   decide <issue-state> <spec-meta-stage> <handoff-marker-present> <buildable-unchecked-count>
# prints `decision=migrate` or `decision=skip reason=<why>`. The buildable
# count comes from count-tasks-checkboxes.sh -- the one classification home;
# this script never counts tasks itself.
set -uo pipefail

decide() {
  local state="${1:-}" stage="${2:-}" marker="${3:-}" count="${4:-}"
  if [ "$state" != "open" ]; then echo "decision=skip reason=issue-not-open"; return 0; fi
  # The marker comment is the last write of a hand-off, so it alone proves
  # the hand-off finished. A stalled lifecycle without it is a partial run:
  # only the comment is missing.
  if [ "$marker" = "true" ]; then echo "decision=skip reason=already-migrated"; return 0; fi
  if [ "$stage" = "stalled" ]; then echo "decision=comment-only"; return 0; fi
  if [ "$stage" != "review" ]; then echo "decision=skip reason=not-at-review"; return 0; fi
  case "$count" in ''|*[!0-9]*) echo "decision=skip reason=count-unreadable"; return 0 ;; esac
  if [ "$count" -le 0 ]; then echo "decision=skip reason=no-buildable-left"; return 0; fi
  echo "decision=migrate"
}

case "${1:-}" in
  decide) shift; decide "$@" ;;
  *) echo "usage: $0 decide <issue-state> <stage> <marker> <count>" >&2; exit 2 ;;
esac
