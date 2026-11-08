#!/usr/bin/env bash
# .github/actions/_shared/stalled-handoff.sh
#
# The ONE home of the FR-015/FR-015a stalled hand-off (specs/123-implement-
# task-completion): buildable tasks remain, so nothing is dispatched and the
# lifecycle waits at stage:stalled for an implement dispatch at the recorded
# iteration + 1. Reached through the wing-commander-stalled-handoff
# composite by finalize's refusal step and implement's skip branch.
#
# Order: spec-meta stage -> stalled (commit and push), then the label, then
# ONE comment carrying an idempotency marker. Each write must succeed before
# the next; a failure exits non-zero before the label and comment.
#
# Env: GH_TOKEN, ISSUE, SPEC_DIR, SLUG, BOT_SLUG, BODY_FILE (the comment
# prose, without marker or resume line), MARKER_KIND (marker name),
# COMMIT_REASON (short text for the commit subject).
set -uo pipefail

meta="$SPEC_DIR/spec-meta.json"
next_iter="$(( $(jq -r '.iteration // 0' "$meta") + 1 ))"
marker="<!-- wing-commander-${MARKER_KIND} iteration=${next_iter} -->"

if [ "$(jq -r '.stage // ""' "$meta")" != "stalled" ]; then
  jq '.stage = "stalled"' "$meta" > "${RUNNER_TEMP:-/tmp}/stalled-meta.json" || exit 1
  mv "${RUNNER_TEMP:-/tmp}/stalled-meta.json" "$meta" || exit 1
  git add "$meta" || exit 1
  git config user.name  "${BOT_SLUG}[bot]"
  git config user.email "${BOT_SLUG}[bot]@users.noreply.github.com"
  git commit -m "${COMMIT_STAGE:-implement}: $SLUG -> stalled (#$ISSUE, $COMMIT_REASON)" || exit 1
  git push || exit 1
fi

gh label create "stage:stalled" --color B60205 --description "Lifecycle waiting for an implement dispatch" --force || true
gh issue edit "$ISSUE" --add-label "stage:stalled" --remove-label "stage:review" 2>/dev/null \
  || gh issue edit "$ISSUE" --add-label "stage:stalled" || exit 1

if gh issue view "$ISSUE" --repo "$GITHUB_REPOSITORY" --json comments --jq '.comments[].body' | grep -qF "$marker"; then
  echo "stalled hand-off comment for iteration $next_iter already posted" >> "${GITHUB_STEP_SUMMARY:-/dev/null}"
  exit 0
fi
body="$marker"$'\n'"$(cat "$BODY_FILE")"$'\n\n'"Resume with an implement dispatch (spec_dir=$SPEC_DIR, issue=$ISSUE, iteration=$next_iter)."
gh issue comment "$ISSUE" --repo "$GITHUB_REPOSITORY" --body "$body"
