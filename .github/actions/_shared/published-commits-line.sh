#!/usr/bin/env bash
# .github/actions/_shared/published-commits-line.sh
#
# specs/071-agent-push-credential FR-016/FR-017: the one place that renders
# the "N commit(s) the agent could not push during the run were published
# after it" stall-notice line, read by both wing-commander-chain-stop-notice
# (the "stage did not start"/post-agent-failure stall path) and
# implement.yml's own inline exhausted-retry stall notice (a separate path
# with no shared composite of its own) -- CLAUDE.md's single-home rule: this
# line's wording was pasted into both before this extraction (code review of
# this PR).
#
# Invoke with:
#   eval "$(bash "$GITHUB_ACTION_PATH/../_shared/published-commits-line.sh" \
#     "$COMMITS_PUBLISHED" "$PUSH_OK")"
# from inside a composite (a plain workflow `run:` step resolves the same
# path as .wing-commander-pipeline/.github/actions/_shared/published-commits-
# line.sh, per every other workflow-level reader of a pipeline script).
#
# $1 = commits-published (a bare non-negative integer, or empty/anything
#      non-numeric, which renders no line at all).
# $2 = push-ok ("false" renders a "could not be published either" line
#      instead of "were published"; anything else, including empty for a
#      caller that predates this input, means success).
#
# Prints exactly one line: `published_line=<shell-quoted value>` (empty
# string when there is nothing to say) -- callers eval it directly.
set -uo pipefail

commits="${1:-}"
push_ok="${2:-}"

published_line=""
case "$commits" in
  ''|0) ;;
  *[!0-9]*) ;;
  *)
    if [ "$push_ok" = "false" ]; then
      published_line="$commits commit(s) the agent could not push during the run could not be published either -- the rescue push itself failed."
    else
      published_line="$commits commit(s) the agent could not push during the run were published after it."
    fi
    ;;
esac

printf 'published_line=%q\n' "$published_line"
