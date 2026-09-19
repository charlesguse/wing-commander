#!/usr/bin/env bash
# Pure decision function for the clarification gate specs/055-unattended-
# e2e-gates drives inside auto-release.yml's `poll` step. Takes
# already-fetched comment JSON and decides whether a clarification question
# is open, already answered this round, or the round bound is exhausted --
# never calls `gh` or the network itself (Constitution VIII, research.md
# D5/D6/D7/D8). See
# specs/055-unattended-e2e-gates/contracts/gate-decision-scripts.md.
#
# Invoke with `bash .github/actions/_shared/auto-release-e2e-clarify-
# decision.sh "$COMMENTS_JSON" "$HARNESS_LOGIN" "$ROUNDS_ANSWERED"`.
#
# COMMENTS_JSON is the `.comments` array from `gh issue view <n> --json
# comments` -- entries of {id, author:{login}, body, createdAt}.
#
# Prints one of `none` / `wait` / `exhausted` / `reply` on stdout; `reply`
# is followed on the next line by the fixed prepared-answer body (research.md
# D8) -- the caller posts that comment and increments ROUNDS_ANSWERED only
# after seeing this decision. Never sourced, matching
# auto-release-verdict.sh's invocation idiom.
set -uo pipefail

comments_json="${1:?comments JSON required}"
harness_login="${2:?harness login required}"
rounds_answered="${3:?rounds answered required}"

MAX_CLARIFICATION_ROUNDS=3

# The latest comment matching the marker two stage workflows post
# (intake.yml and clarify.yml's own "Answer the open/remaining
# clarification questions" callouts) -- a [!IMPORTANT] callout naming one
# of the two literal phrases.
marker_created_at="$(printf '%s' "$comments_json" | jq -r --arg open "Answer the open clarification questions" --arg remaining "Answer the remaining clarification questions" '
  [ .[] | select((.body // "") | contains("[!IMPORTANT]"))
        | select((((.body // "") | contains($open))) or (((.body // "") | contains($remaining)))) ]
  | if length == 0 then "" else (last.createdAt // "") end
')"

if [ -z "$marker_created_at" ]; then
  echo "none"
  exit 0
fi

harness_reply_exists="$(printf '%s' "$comments_json" | jq -r --arg login "$harness_login" --arg after "$marker_created_at" '
  any(.[]; (.author.login // "") == $login and (.createdAt // "") > $after)
')"

if [ "$harness_reply_exists" = "true" ]; then
  echo "wait"
  exit 0
fi

if [ "$rounds_answered" -lt "$MAX_CLARIFICATION_ROUNDS" ]; then
  echo "reply"
  printf '%s\n' 'Use the moment this workflow run started as "the timestamp." On a repeat run, overwrite the existing file rather than adding a new one. For anything else this question doesn'"'"'t cover, use your own best judgement and proceed.'
else
  echo "exhausted"
fi
