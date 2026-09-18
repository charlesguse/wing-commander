#!/usr/bin/env bash
# The auto-release fail-infra verdict has exactly one shape, built here.
# Every verdict-construction site in auto-release.yml calls this script
# rather than hand-building the {outcome, verified_head, failing_check,
# expected, observed, evidence_url} JSON object inline -- see
# specs/049-single-home-release-idioms/contracts/verdict-helper.md and
# research.md D3. Extracted verbatim from the `poll` step's own
# write_verdict jq program (today's auto-release.yml:492-498).
#
# Invoke with `bash .github/actions/_shared/auto-release-verdict.sh
# "$OUTCOME" "$HEAD_SHA" "$FAILING_CHECK" "$EXPECTED" "$OBSERVED"
# "$EVIDENCE_URL"` -- never sourced, matching the `_shared/count-turns.sh`
# invocation idiom. auto-release.yml runs from a plain repository checkout
# with no GITHUB_ACTION_PATH of its own (that variable only exists inside
# a running action), so callers resolve this path as a plain repo-relative
# one, not through $GITHUB_ACTION_PATH.
set -uo pipefail

outcome="${1:-}"
head="${2:-}"
failing_check="${3:-}"
expected="${4:-}"
observed="${5:-}"
evidence_url="${6:-}"

jq -n --arg outcome "$outcome" --arg head "$head" --arg failing_check "$failing_check" \
      --arg expected "$expected" --arg observed "$observed" --arg url "$evidence_url" \
  '{outcome:$outcome, verified_head:$head,
    failing_check: (if $failing_check == "" then null else $failing_check end),
    expected: (if $expected == "" then null else $expected end),
    observed: (if $observed == "" then null else $observed end),
    evidence_url:$url}'
