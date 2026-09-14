#!/usr/bin/env bash
# Deterministic fixture check for watchdog.yml's "Collect: final PR claims"
# step (id: collect-final-pr-claims) — specs/046-watchdog-supervision-
# collectors, contracts/gate-coverage-046.md's
# verify-final-pr-claims-collector.sh row.
#
# Two copies exercised together: extract_claim() (the best-effort
# natural-language number extractor) and NARRATIVE_DRIFT_FILTER (the
# claimed-vs-actual comparison). No live gh api/compare call is needed:
# ground-truth values are fixture inputs standing in for what the
# surrounding bash would have already derived from the compare API and
# tasks.md.
#
# Usage: .github/scripts/verify-final-pr-claims-collector.sh
# Exit code: 0 = all assertions passed; 1 = an assertion failed.

set -uo pipefail

fail_reasons=()
note() { echo "::notice::verify-final-pr-claims-collector: $1"; }
reason() { fail_reasons+=("$1"); echo "::error::verify-final-pr-claims-collector: $1"; }

if ! command -v jq >/dev/null 2>&1; then
  echo "::error::verify-final-pr-claims-collector: jq is not on PATH."
  exit 1
fi

extract_claim() {
  local text="$1" word="$2" m
  m="$(printf '%s' "$text" | grep -oiE "[0-9]+ ?(${word})" | head -1 | grep -oE '[0-9]+' | head -1)"
  if [ -z "$m" ]; then
    m="$(printf '%s' "$text" | grep -oiE "(${word})[^0-9]{0,20}[0-9]+" | head -1 | grep -oE '[0-9]+' | tail -1)"
  fi
  printf '%s' "$m"
}

# shellcheck disable=SC2016 # this is a jq program — its $vars must NOT be
# shell-expanded.
FILTER='
  . as $in
  | if ($in.stage_is_finalize // false) != true then []
    else
      ( if ($in.tasks_claim != null) and ($in.tasks_claim != $in.tasks_actual)
        then [{source:"final-pr-claims","class-hint":"narrative-drift",facts:{pr:$in.pr,"claim-type":"tasks","claimed-value":$in.tasks_claim,"actual-value":$in.tasks_actual,"actual-source":"tasks.md checked-box count on the PR head ref"}}]
        else [] end )
      + ( if ($in.commits_claim != null) and ($in.commits_claim != $in.commits_actual)
          then [{source:"final-pr-claims","class-hint":"narrative-drift",facts:{pr:$in.pr,"claim-type":"commits","claimed-value":$in.commits_claim,"actual-value":$in.commits_actual,"actual-source":"git rev-list --count <base>..<head>"}}]
          else [] end )
      + ( if ($in.tests_claim != null) and ($in.tests_claim != $in.tests_actual)
          then [{source:"final-pr-claims","class-hint":"narrative-drift",facts:{pr:$in.pr,"claim-type":"tests","claimed-value":$in.tests_claim,"actual-value":$in.tests_actual,"actual-source":"fixture files added under */fixtures/* between base and head"}}]
          else [] end )
    end
'

build_input() {
  jq -n --arg pr "$1" --argjson stage_is_finalize "$2" \
    --argjson tasks_claim "${3:-null}" --argjson tasks_actual "$4" \
    --argjson commits_claim "${5:-null}" --argjson commits_actual "$6" \
    --argjson tests_claim "${7:-null}" --argjson tests_actual "$8" \
    '{pr:($pr|tonumber), stage_is_finalize:$stage_is_finalize, tasks_claim:$tasks_claim, tasks_actual:$tasks_actual, commits_claim:$commits_claim, commits_actual:$commits_actual, tests_claim:$tests_claim, tests_actual:$tests_actual}'
}

# ── extract_claim(): number-before-word and word-before-number orderings.
m="$(extract_claim "This PR completes 42 tasks across three phases." 'tasks?')"
if [ "$m" = "42" ]; then note "extract_claim found 42 tasks (number-before-word)"; else reason "extract_claim expected 42 for 'completes 42 tasks', got '$m'"; fi

m="$(extract_claim "Tasks completed: 41" 'tasks?')"
if [ "$m" = "41" ]; then note "extract_claim found 41 tasks (word-before-number)"; else reason "extract_claim expected 41 for 'Tasks completed: 41', got '$m'"; fi

# ── extract_claim(): unparseable claim shape → empty (FR-023 — no signal,
#    never an error).
m="$(extract_claim "A great deal of work went into the tasks for this spec." 'tasks?')"
if [ -n "$m" ]; then
  reason "extract_claim expected no match for prose with no isolable number, got '$m'"
else
  note "extract_claim correctly found no number in unparseable prose"
fi

# ── Positive: task-count mismatch.
out="$(jq -c "$FILTER" <<<"$(build_input 301 true 42 41 10 10 0 0)")"
note "task mismatch fixture output: $out"
if [ "$(jq '[.[] | select(.facts."claim-type"=="tasks")] | length' <<<"$out")" != "1" ]; then
  reason "a task-count mismatch (claimed 42, actual 41) must produce exactly one narrative-drift signal with claim-type tasks, got $out"
else
  note "task-count mismatch correctly produced one narrative-drift signal"
fi

# ── Positive: commit-count mismatch.
out="$(jq -c "$FILTER" <<<"$(build_input 301 true null 0 10 12 null 0)")"
note "commit mismatch fixture output: $out"
if [ "$(jq '[.[] | select(.facts."claim-type"=="commits")] | length' <<<"$out")" != "1" ]; then
  reason "a commit-count mismatch (claimed 10, actual 12) must produce exactly one narrative-drift signal with claim-type commits, got $out"
else
  note "commit-count mismatch correctly produced one narrative-drift signal"
fi

# ── Positive: test-count (fixture-file-count) mismatch.
out="$(jq -c "$FILTER" <<<"$(build_input 301 true null 0 null 0 5 3)")"
note "test mismatch fixture output: $out"
if [ "$(jq '[.[] | select(.facts."claim-type"=="tests")] | length' <<<"$out")" != "1" ]; then
  reason "a test-count mismatch (claimed 5, actual 3 fixture files) must produce exactly one narrative-drift signal with claim-type tests, got $out"
else
  note "test-count mismatch correctly produced one narrative-drift signal"
fi

# ── Negative: unparseable claim shape (null claim) → no signal for that
#    claim type.
out="$(jq -c "$FILTER" <<<"$(build_input 301 true null 41 null 10 null 0)")"
if [ "$out" != "[]" ]; then
  reason "an unparseable (null) claim for every claim type must produce no signal, got $out"
else
  note "unparseable claims correctly produced no signal"
fi

# ── Negative: all three claims matching ground truth → no signal.
out="$(jq -c "$FILTER" <<<"$(build_input 301 true 41 41 10 10 3 3)")"
if [ "$out" != "[]" ]; then
  reason "all three claims matching ground truth must produce no signal, got $out"
else
  note "matching claims correctly produced no signal"
fi

# ── Negative: non-finalize run → no signal regardless of mismatches
#    (scope guard).
out="$(jq -c "$FILTER" <<<"$(build_input 301 false 42 41 10 10 0 0)")"
if [ "$out" != "[]" ]; then
  reason "a non-finalize run must produce no signal even with mismatches present, got $out"
else
  note "non-finalize scope guard correctly produced no signal"
fi

if [ "${#fail_reasons[@]}" -eq 0 ]; then
  echo "✅ verify-final-pr-claims-collector: all assertions passed."
  exit 0
fi

echo "❌ verify-final-pr-claims-collector: ${#fail_reasons[@]} assertion(s) failed:"
for r in "${fail_reasons[@]}"; do echo "- $r"; done
exit 1
