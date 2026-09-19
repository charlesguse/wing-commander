#!/usr/bin/env bash
# Pure decision function for the clarification gate specs/055-unattended-
# e2e-gates drives inside auto-release.yml's `poll` step. Takes
# already-fetched REST-shape issue-comments JSON and decides whether a
# clarification question is open, already answered this round, or the
# round bound is exhausted -- never calls `gh` or the network itself
# (Constitution VIII, research.md D5/D6/D7/D8). See
# specs/055-unattended-e2e-gates/contracts/gate-decision-scripts.md.
#
# Usage:
#   bash auto-release-e2e-clarify-decision.sh decide "$ISSUE_AUTHOR_ID" "$ROUNDS_ANSWERED" <<<"$COMMENTS_JSON"
#   bash auto-release-e2e-clarify-decision.sh satisfied "$ISSUE_AUTHOR_ID" <<<"$COMMENTS_JSON"
#   bash auto-release-e2e-clarify-decision.sh markers <<<"$COMMENTS_JSON"
#
# COMMENTS_JSON arrives on stdin, not argv -- a long-running issue's full
# comment history can exceed Linux's 128 KB per-argument limit (maintainer
# feedback on PR #389). It is the array `gh api
# repos/<owner>/<repo>/issues/<n>/comments --paginate` returns (REST
# shape): entries of {id, user:{login,id,type}, author_association, body,
# created_at}. This is the same shape intake.yml's own comment-trust-gate
# (intake.yml:524) reads, on purpose -- see "qualifies" below.
#
# ISSUE_AUTHOR_ID is the issue author's numeric user id (`.user.id` from
# `gh api repos/<owner>/<repo>/issues/<n>`).
#
# `markers` is the single home for the "[!IMPORTANT] + one of the two
# clarification-callout phrases" predicate (maintainer feedback: this used
# to be pasted a second time inline in auto-release.yml). It prints the
# JSON array of matching comments, oldest first. Both `decide` and
# `satisfied` call it internally; auto-release.yml's pass-path assertion
# calls it directly instead of re-deriving the predicate.
#
# `decide` prints one of `none` / `wait` / `exhausted` / `reply` on
# stdout; `reply` is followed on the next line by the fixed prepared-
# answer body (research.md D8) -- the caller posts that comment and
# increments ROUNDS_ANSWERED only after seeing this decision. A reply
# "counts" as answering the round only when it QUALIFIES (see below) --
# a comment from a bot account, or from a human with no standing to answer
# clarification questions, is not treated as a reply (maintainer feedback:
# this used to be "any later comment", which let an unrelated bot comment
# -- a metrics rollup, a watchdog notice -- deadlock the gate in
# fail-timeout).
#
# `satisfied` prints `ok` if every marker comment in the issue's full
# history already has a qualifying reply after it, else `unsatisfied` --
# used by auto-release.yml's pass-path assertion (FR-016/FR-018), which
# must accept a human's answer, not only the harness's own (FR-010; the
# "a human answers first" Edge Case).
#
# A comment QUALIFIES as an answer exactly when it would pass intake.yml's
# own comment-trust-gate (intake.yml:524): not a Bot account, and either
# an OWNER/MEMBER/COLLABORATOR association or the issue's own author.
# MAX_CLARIFICATION_ROUNDS, if set in the environment (auto-release.yml's
# `poll` step env), overrides the default of 3 -- this is the one place
# that number is read, so the workflow's own `MAX_CLARIFICATION_ROUNDS`
# env var is no longer dead (maintainer feedback).
set -uo pipefail

MAX_CLARIFICATION_ROUNDS="${MAX_CLARIFICATION_ROUNDS:-3}"

mode="${1:?mode required: decide | satisfied | markers}"
shift

comments_json="$(cat)"

markers_json() {
  printf '%s' "$comments_json" | jq -c --arg open "Answer the open clarification questions" --arg remaining "Answer the remaining clarification questions" '
    [ .[] | select((.body // "") | contains("[!IMPORTANT]"))
          | select((((.body // "") | contains($open))) or (((.body // "") | contains($remaining)))) ]
    | sort_by(.created_at)
  '
}

qualifying_reply_after() {
  # $1: the ISO timestamp a qualifying reply must postdate.
  local after="$1" author_id="$2"
  printf '%s' "$comments_json" | jq -r --arg after "$after" --arg author_id "$author_id" '
    any(.[]; (.created_at // "") > $after
      and ((.user.type // "") != "Bot")
      and ( ((.author_association // "") == "OWNER")
            or ((.author_association // "") == "MEMBER")
            or ((.author_association // "") == "COLLABORATOR")
            or (((.user.id // -1) | tostring) == $author_id) ))
  '
}

case "$mode" in
  markers)
    markers_json
    ;;
  decide)
    author_id="${1:?issue author id required}"
    rounds_answered="${2:?rounds answered required}"
    marker_created_at="$(markers_json | jq -r 'if length == 0 then "" else (last.created_at // "") end')"
    if [ -z "$marker_created_at" ]; then
      echo "none"
      exit 0
    fi
    reply_exists="$(qualifying_reply_after "$marker_created_at" "$author_id")"
    if [ "$reply_exists" = "true" ]; then
      echo "wait"
      exit 0
    fi
    if [ "$rounds_answered" -lt "$MAX_CLARIFICATION_ROUNDS" ]; then
      echo "reply"
      printf '%s\n' 'Use the moment this workflow run started as "the timestamp." On a repeat run, overwrite the existing file rather than adding a new one. For anything else this question doesn'"'"'t cover, use your own best judgement and proceed.'
    else
      echo "exhausted"
    fi
    ;;
  satisfied)
    author_id="${1:?issue author id required}"
    markers="$(markers_json)"
    result="ok"
    while IFS= read -r marker_created_at; do
      [ -n "$marker_created_at" ] || continue
      if [ "$(qualifying_reply_after "$marker_created_at" "$author_id")" != "true" ]; then
        result="unsatisfied"
        break
      fi
    done < <(printf '%s' "$markers" | jq -r '.[].created_at')
    echo "$result"
    ;;
  *)
    echo "::error::auto-release-e2e-clarify-decision.sh: unknown mode '$mode'" >&2
    exit 1
    ;;
esac
