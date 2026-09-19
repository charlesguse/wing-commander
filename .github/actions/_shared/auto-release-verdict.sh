#!/usr/bin/env bash
# The auto-release fail-infra verdict has exactly one shape, built here.
# Every verdict-construction site in auto-release.yml calls this script
# rather than hand-building the {outcome, verified_head, failing_check,
# expected, observed, evidence_url} JSON object inline -- see
# specs/049-single-home-release-idioms/contracts/verdict-helper.md and
# research.md D3. Extracted verbatim from the `poll` step's own
# write_verdict jq program (today's auto-release.yml:492-498).
#
# specs/054-e2e-container-coverage (MF2) folded the mode/container-image-
# configured tagging in here too, as two additional, optional positional
# arguments -- every call site used to pipe this script's output through a
# second, pasted `jq --arg mode "$MODE" '. + {mode:$mode} + (...)'`, twelve
# times over, which is exactly the copy-instead-of-consolidate shape
# CLAUDE.md's "Shared logic has exactly one home" forbids. Gate 60's
# mode-tag-shape check (verify-single-home-idioms.py) fails if that pasted
# pipe reappears anywhere outside this file.
#
# Invoke with `bash .github/actions/_shared/auto-release-verdict.sh
# "$OUTCOME" "$HEAD_SHA" "$FAILING_CHECK" "$EXPECTED" "$OBSERVED"
# "$EVIDENCE_URL" ["$MODE" ["$CONTAINER_IMAGE_CONFIGURED"]]` -- never
# sourced, matching the `_shared/count-turns.sh` invocation idiom.
# auto-release.yml runs from a plain repository checkout with no
# GITHUB_ACTION_PATH of its own (that variable only exists inside a
# running action), so callers resolve this path as a plain repo-relative
# one, not through $GITHUB_ACTION_PATH.
#
# MODE, when non-empty, is threaded through as the verdict's `mode` field.
# CONTAINER_IMAGE_CONFIGURED is only ever consulted when MODE is
# "container" (data-model.md "Execution mode": the field is present only
# when mode is container); the field then DEFAULTS to false unless the
# caller passes the literal string "true". This default, not a per-call-
# site guess, is what fixes the maintainer-review finding that every
# container-turn verdict used to claim `container_image_configured: true`
# regardless of whether the container path ever actually ran (specs/054
# MF1): almost every verdict-construction site in verify-e2e fires before
# the pipeline could have exercised the image at all (resolving the test
# repository, minting a token, resetting its branch, scaffolding the
# fixture, creating the kickoff issue) or without positive evidence the
# image was ever pulled (a poll that timed out, or one that closed
# incomplete). The one call site that has earned "true" -- the poll step's
# `pass` verdict, reached only once the full scaffolded chain finished --
# passes it explicitly; every other site just threads MODE through and
# gets the honest default. Both arguments default to empty, so a call site
# that never passes them -- and every one of the 15 fixed inputs
# contracts/verdict-helper.md's byte-identity check replays -- gets
# byte-identical output to before this field existed.
set -uo pipefail

outcome="${1:-}"
head="${2:-}"
failing_check="${3:-}"
expected="${4:-}"
observed="${5:-}"
evidence_url="${6:-}"
mode="${7:-}"
container_image_configured="${8:-}"

jq -n --arg outcome "$outcome" --arg head "$head" --arg failing_check "$failing_check" \
      --arg expected "$expected" --arg observed "$observed" --arg url "$evidence_url" \
      --arg mode "$mode" --arg cic "$container_image_configured" \
  '{outcome:$outcome, verified_head:$head,
    failing_check: (if $failing_check == "" then null else $failing_check end),
    expected: (if $expected == "" then null else $expected end),
    observed: (if $observed == "" then null else $observed end),
    evidence_url:$url}
   + (if $mode == "" then {} else {mode:$mode} end)
   + (if $mode == "container"
      then {container_image_configured: ($cic == "true")}
      else {} end)'
