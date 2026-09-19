#!/usr/bin/env bash
# Pure decision function for the three PR-merge gates specs/055-unattended-
# e2e-gates drives inside auto-release.yml's `poll` step. Takes an
# already-fetched `gh pr list` result and decides whether to merge, wait,
# or treat the gate as stalled -- never calls `gh` or the network itself
# (Constitution VIII, research.md D5/D6/D9). See
# specs/055-unattended-e2e-gates/contracts/gate-decision-scripts.md.
#
# Invoke with `bash .github/actions/_shared/auto-release-e2e-merge-
# decision.sh "$PR_LIST_JSON" "$HEAD_REF_PREFIX" "$SLUG"`.
#
# PR_LIST_JSON is the array from `gh pr list --head <prefix><slug> --json
# number,headRefName,mergeable,mergeStateStatus,isDraft,state` -- normally
# 0 or 1 entries, since the caller already filters --head to the exact
# expected branch name.
#
# Prints one of `none` / `wrong-attempt` / `wait` / `conflicting` /
# `blocked` / `merge` on stdout; `merge` is followed on the next line by
# the PR number. `conflicting`, `blocked`, and `wrong-attempt` are each a
# distinct fail-gate-stall reason (FR-023) -- the caller never retries
# after receiving one of them. Never sourced, matching
# auto-release-verdict.sh's invocation idiom.
set -uo pipefail

pr_list_json="${1:?PR list JSON required}"
head_ref_prefix="${2:?head ref prefix required}"
slug="${3:?slug required}"

expected_head="${head_ref_prefix}${slug}"

count="$(printf '%s' "$pr_list_json" | jq 'length')"
if [ "$count" -eq 0 ]; then
  echo "none"
  exit 0
fi

entry="$(printf '%s' "$pr_list_json" | jq -c '.[0]')"
head_ref="$(printf '%s' "$entry" | jq -r '.headRefName // ""')"
if [ "$head_ref" != "$expected_head" ]; then
  echo "wrong-attempt"
  exit 0
fi

is_draft="$(printf '%s' "$entry" | jq -r '.isDraft // false')"
if [ "$is_draft" = "true" ]; then
  echo "wait"
  exit 0
fi

mergeable="$(printf '%s' "$entry" | jq -r '.mergeable // ""')"
if [ "$mergeable" = "CONFLICTING" ]; then
  echo "conflicting"
  exit 0
fi

merge_state="$(printf '%s' "$entry" | jq -r '.mergeStateStatus // ""')"
if [ "$merge_state" = "BLOCKED" ]; then
  echo "blocked"
  exit 0
fi

case "$merge_state" in
  UNKNOWN|BEHIND)
    echo "wait"
    exit 0
    ;;
esac

number="$(printf '%s' "$entry" | jq -r '.number // ""')"
echo "merge"
echo "$number"
