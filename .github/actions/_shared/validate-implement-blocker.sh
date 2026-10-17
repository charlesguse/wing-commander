#!/usr/bin/env bash
# .github/actions/_shared/validate-implement-blocker.sh
#
# Validates the blocker record an implement agent may write when it must stop
# with implementation tasks unchecked (specs/117 research D4). The record is
# untrusted agent output (Principle V): this script is the only thing that
# decides whether it counts, so the hand-off decision stays deterministic
# (Principle IX).
#
# Invoke with
#   bash "$GITHUB_ACTION_PATH/../_shared/validate-implement-blocker.sh" \
#     <blocker-json-path> <tasks-ref> <tasks-path>
#
# Prints `key=value` lines shaped as $GITHUB_OUTPUT entries:
#   blocker-valid=true|false
#   blocker-text=<kind: detail (task)>     (empty when invalid)
#   blocker-invalid-reason=<text>          (empty when valid)
# A missing or malformed blocker is an expected input, so the script exits 0
# for it. It exits non-zero only when tasks.md cannot be read at the ref
# (count-tasks-checkboxes.sh's own fail-loud rule).
#
# The blocker must be exactly {"task","kind","detail"}: `task` an unchecked
# IMPLEMENTATION task id at the pushed tip (a checked, absent, standing or
# [maintainer] task is not a blocker on implementation), `kind` one of a
# closed list, `detail` 1-300 characters on a single line.
set -uo pipefail

BLOCKER="${1:-}"
REF="${2:-}"
TASKS_PATH="${3:-}"

if [ -z "$BLOCKER" ] || [ -z "$REF" ] || [ -z "$TASKS_PATH" ]; then
  echo "validate-implement-blocker.sh: usage: validate-implement-blocker.sh <blocker-json-path> <tasks-ref> <tasks-path>" >&2
  exit 1
fi

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Read tasks.md first so an unreadable one fails loudly even when no blocker
# was written.
counts="$(bash "$here/count-tasks-checkboxes.sh" "$REF" "$TASKS_PATH")"
rc=$?
if [ "$rc" -ne 0 ]; then
  exit "$rc"
fi

invalid() {
  printf 'blocker-valid=false\nblocker-text=\nblocker-invalid-reason=%s\n' "$1"
  exit 0
}

[ -f "$BLOCKER" ] || invalid "no blocker file"
jq -e . "$BLOCKER" >/dev/null 2>&1 || invalid "not valid JSON"
[ "$(jq -r 'type' "$BLOCKER")" = "object" ] || invalid "not a JSON object"
[ "$(jq -c 'keys' "$BLOCKER")" = '["detail","kind","task"]' ] || invalid "keys are not exactly task, kind, detail"
[ "$(jq -r '[.task, .kind, .detail] | map(type) | unique | join(",")' "$BLOCKER")" = "string" ] || invalid "task, kind and detail must all be strings"

task="$(jq -r '.task' "$BLOCKER")"
kind="$(jq -r '.kind' "$BLOCKER")"
detail="$(jq -r '.detail' "$BLOCKER")"

case "$kind" in
  missing-tool|missing-permission|contradictory-spec|external-dependency) ;;
  *) invalid "kind is not one of missing-tool, missing-permission, contradictory-spec, external-dependency" ;;
esac

[ "${#detail}" -ge 1 ] || invalid "detail is empty"
[ "${#detail}" -le 300 ] || invalid "detail is longer than 300 characters"
case "$detail" in
  *$'\n'*|*$'\r'*) invalid "detail is not a single line" ;;
esac

[[ "$task" =~ ^T[0-9]+$ ]] || invalid "task is not a task id (T followed by digits)"

impl_items="$(printf '%s\n' "$counts" | awk '
  /^impl-unchecked-items<<WING_COMMANDER_IMPL_ITEMS_EOF$/ { on = 1; next }
  /^WING_COMMANDER_IMPL_ITEMS_EOF$/ { on = 0 }
  on { print }
')"
found=false
while IFS= read -r line; do
  if [[ "$line" =~ ^[[:space:]]*-\ \[\ \][[:space:]]+${task}([[:space:]]|$) ]]; then
    found=true
    break
  fi
done <<<"$impl_items"
[ "$found" = "true" ] || invalid "task $task is not an unchecked implementation task at the pushed tip"

printf 'blocker-valid=true\nblocker-text=%s: %s (%s)\nblocker-invalid-reason=\n' "$kind" "$detail" "$task"
