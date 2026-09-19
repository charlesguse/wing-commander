#!/usr/bin/env bash
# Pure decision function for the three PR-merge gates specs/055-unattended-
# e2e-gates drives inside auto-release.yml's `poll` step. Takes an
# already-fetched `gh pr list` result and decides whether to merge, wait,
# or treat the gate as stalled -- never calls `gh` or the network itself
# (Constitution VIII, research.md D5/D6/D9). See
# specs/055-unattended-e2e-gates/contracts/gate-decision-scripts.md.
#
# Invoke with `bash .github/actions/_shared/auto-release-e2e-merge-
# decision.sh "$HEAD_REF_PREFIX" "$SLUG" "$EXPECTED_BASE" <<<"$PR_LIST_JSON"`.
#
# PR_LIST_JSON arrives on stdin (maintainer feedback: a long-running
# issue's comment history hit Linux's 128 KB per-argument limit on the
# sibling clarify-decision script; both decision scripts now take their
# JSON the same way for one calling convention). It is the array from
# `gh pr list --head <prefix><slug> --json
# number,headRefName,baseRefName,mergeable,mergeStateStatus,isDraft,state,statusCheckRollup`
# -- normally 0 or 1 entries, since the caller already filters --head to
# the exact expected branch name.
#
# EXPECTED_BASE is the base branch this gate's PR is required to target
# (research.md D9): the default branch for the spec-draft and finalize
# gates, `spec/<slug>` for the plan gate. A PR at the right head but the
# wrong base is a `wrong-base` gate stall (maintainer feedback) -- never
# merged, since a retargeted PR could otherwise land unreviewed content.
#
# Prints one of `none` / `wrong-attempt` / `wrong-base` / `wait` /
# `conflicting` / `blocked` / `merge` on stdout; `merge` is followed on
# the next line by the PR number. `conflicting`, `blocked`,
# `wrong-attempt`, and `wrong-base` are each a distinct fail-gate-stall
# reason (FR-023) -- the caller never retries after receiving one of
# them. Never sourced, matching auto-release-verdict.sh's invocation
# idiom.
set -uo pipefail

head_ref_prefix="${1:?head ref prefix required}"
slug="${2:?slug required}"
expected_base="${3:?expected base branch required}"

pr_list_json="$(cat)"

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

base_ref="$(printf '%s' "$entry" | jq -r '.baseRefName // ""')"
if [ "$base_ref" != "$expected_base" ]; then
  echo "wrong-base"
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
  # BLOCKED also reports while a required check is still running, not
  # only once one has definitively failed (maintainer feedback: confirm a
  # pending-checks PR is never declared a gate stall). A rollup entry
  # still PENDING/QUEUED/IN_PROGRESS -- or COMPLETED with no conclusion
  # yet recorded -- means the wait, not the block, is what's actually
  # happening; only a rollup with nothing left pending is a genuine stall.
  still_pending="$(printf '%s' "$entry" | jq -r '
    [ (.statusCheckRollup // [])[]
      | select((.status // "") != "COMPLETED" or ((.conclusion // "") == "")) ]
    | length > 0
  ')"
  if [ "$still_pending" = "true" ]; then
    echo "wait"
    exit 0
  fi
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
