#!/usr/bin/env bash
# .github/actions/_shared/migrate-stranded-review-lifecycles.sh
#
# specs/123-implement-task-completion FR-018: a lifecycle stranded at stage
# `review` with buildable tasks still unchecked is handed off once
# (stage `stalled`, label `stage:stalled`, one comment).
#
# Invoke with `bash` (never the file itself):
#   decide <issue-state> <spec-meta-stage> <handoff-marker-present> <buildable-unchecked-count>
#       prints `decision=migrate` or `decision=skip reason=<why>`; pure, no I/O.
#       The buildable count comes from count-tasks-checkboxes.sh -- the one
#       classification home; this script never counts tasks itself.
#   apply <repo> <issue> <branch> <spec-dir> [dry-run]
#       reads tasks.md and spec-meta.json at origin/<branch>, decides, and
#       (unless dry-run) commits `stage: stalled`, labels and comments.
set -uo pipefail

MARKER='<!-- wing-commander-migrate-stranded-review -->'

decide() {
  local state="${1:-}" stage="${2:-}" marker="${3:-}" count="${4:-}"
  if [ "$state" != "open" ]; then echo "decision=skip reason=issue-not-open"; return 0; fi
  if [ "$stage" = "stalled" ] || [ "$marker" = "true" ]; then echo "decision=skip reason=already-migrated"; return 0; fi
  if [ "$stage" != "review" ]; then echo "decision=skip reason=not-at-review"; return 0; fi
  case "$count" in ''|*[!0-9]*) echo "decision=skip reason=count-unreadable"; return 0 ;; esac
  if [ "$count" -le 0 ]; then echo "decision=skip reason=no-buildable-left"; return 0; fi
  echo "decision=migrate"
}

apply() {
  local repo="$1" issue="$2" branch="$3" dir="$4" dry="${5:-}"
  local here
  here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  git fetch origin "$branch" || { echo "::error::cannot fetch $branch" >&2; return 1; }
  local out count stage state marker
  out="$(bash "$here/count-tasks-checkboxes.sh" "origin/$branch" "$dir/tasks.md")" || return 1
  count="$(printf '%s\n' "$out" | sed -n 's/^buildable-unchecked-count=//p')"
  stage="$(git show "origin/$branch:$dir/spec-meta.json" | jq -r '.stage // ""')" || return 1
  state="$(gh issue view "$issue" --repo "$repo" --json state --jq '.state | ascii_downcase')" || return 1
  marker=false
  if gh issue view "$issue" --repo "$repo" --json comments --jq '.comments[].body' | grep -qF "$MARKER"; then marker=true; fi
  local verdict
  verdict="$(decide "$state" "$stage" "$marker" "$count")"
  echo "#$issue: $verdict"
  [ "$verdict" = "decision=migrate" ] || return 0
  if [ "$dry" = "dry-run" ]; then echo "#$issue: dry-run, no changes"; return 0; fi
  local items
  items="$(printf '%s\n' "$out" | sed -n '/^buildable-unchecked-items<</,/^EOF/p' | sed '1d;$d')"
  git checkout -B "$branch" "origin/$branch" || return 1
  jq '.stage = "stalled"' "$dir/spec-meta.json" > "$dir/spec-meta.json.tmp" && mv "$dir/spec-meta.json.tmp" "$dir/spec-meta.json"
  git add "$dir/spec-meta.json"
  git commit -m "implement: hand off stranded review lifecycle (stage stalled)" || return 1
  git push origin "$branch" || return 1
  gh issue edit "$issue" --repo "$repo" --add-label "stage:stalled" --remove-label "stage:review" || true
  gh issue comment "$issue" --repo "$repo" --body "$MARKER
wing-commander: this lifecycle reached review with $count buildable task(s) unchecked, so it is handed off. Remaining buildable tasks:

$items

Resume with an implement dispatch (spec_dir=$dir, issue=$issue, iteration=recorded+1)."
}

case "${1:-}" in
  decide) shift; decide "$@" ;;
  apply) shift; apply "$@" ;;
  *) echo "usage: $0 decide|apply ..." >&2; exit 2 ;;
esac
