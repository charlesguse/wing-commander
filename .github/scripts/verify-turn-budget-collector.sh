#!/usr/bin/env bash
# Deterministic fixture check for watchdog.yml's "Collect: turn budget" step
# (id: collect-turn-budget) — specs/046-watchdog-supervision-collectors,
# contracts/gate-coverage-046.md's verify-turn-budget-collector.sh row.
#
# FILTER below is a copy of watchdog.yml's TURN_BUDGET_FILTER — the
# self-contained function of (this run's own metrics record, the stage's
# recent history, the two thresholds) the live collect-turn-budget step
# evaluates. No live watchdog run or gh/git call is needed: this feeds
# fixture inputs directly and asserts the per-run signal and severity band
# the collector would compute (SC-002).
#
# Usage: .github/scripts/verify-turn-budget-collector.sh
# Exit code: 0 = all assertions passed; 1 = an assertion failed.

set -uo pipefail

fail_reasons=()
note() { echo "::notice::verify-turn-budget-collector: $1"; }
reason() { fail_reasons+=("$1"); echo "::error::verify-turn-budget-collector: $1"; }

if ! command -v jq >/dev/null 2>&1; then
  echo "::error::verify-turn-budget-collector: jq is not on PATH."
  exit 1
fi

# shellcheck disable=SC2016 # this is a jq program — its $vars must NOT be
# shell-expanded.
FILTER='
  . as $in
  | ($in.own // {}) as $own
  | (($own.available // false) == true) as $own_available
  | (if $own_available and $own.counted != null and $own.intended != null and ($own.counted >= $own.intended)
     then {
       source:"turn-budget","class-hint":null,
       facts:{
         stage:$in.stage, run:$in.run,
         "counted-turns":$own.counted, "intended-budget":$own.intended,
         "enforced-ceiling":$own.ceiling,
         "consumed-ceiling-fraction": (if ($own.ceiling // 0) > 0 then (($own.counted / $own.ceiling * 1000 | round) / 1000) else 0 end)
       }
     }
     else null end) as $per_run
  | ($in.history // []) as $hist0
  | (if $own_available and $own.counted != null then
       (if ($hist0|length) > 0 and ($hist0[-1].run == $in.run) then $hist0
        else $hist0 + [{run:$in.run, counted:$own.counted, intended:$own.intended, ceiling:$own.ceiling}] end)
     else $hist0 end) as $hist1
  | ($in.history_window // 10) as $n
  | ($hist1[-$n:]) as $window
  | ([$window[] | (.counted != null and .intended != null and .counted >= .intended)] | reverse
      | reduce .[] as $b ({n:0,stop:false}; if .stop then . elif $b then {n:(.n+1),stop:false} else {n:.n,stop:true} end) | .n
    ) as $consecutive
  | ([$window[] | select((.ceiling // 0) > 0) | (.counted / .ceiling)] | if length>0 then max else 0 end) as $max_frac_raw
  | (($max_frac_raw*1000|round)/1000) as $max_frac
  | ((((1-$max_frac)*1000)|round)/1000) as $headroom
  | ($consecutive >= ($in.consecutive_trigger // 3)) as $meets_consecutive
  | ($max_frac >= ($in.climb_fraction // 0.6)) as $meets_climb
  | (if $meets_consecutive and $meets_climb then "critical"
     elif $meets_consecutive then "watch"
     elif $meets_climb then "elevated"
     else null end) as $band
  | (if $per_run == null then null else ($per_run + {facts: ($per_run.facts + {band: $band})}) end) as $per_run
  | {
      "per-run": $per_run,
      "trend": (if $band == null then null else {
         stage: $in.stage, band: $band, "window-size": ($window|length),
         "consecutive-at-or-over-budget": $consecutive,
         "max-consumed-ceiling-fraction": $max_frac,
         "headroom-remaining-fraction": $headroom,
         history: [$window[] | {run: .run, "counted-turns": .counted, "intended-budget": .intended}]
      } end)
    }
'

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

run_filter() {
  jq -c "$FILTER" <<<"$1"
}

# ── Fixture 1 (positive, critical): three consecutive at-or-over-budget
#    runs (185, 300, 400 against budget 180) whose max consumed-ceiling-
#    fraction (400/450 = 0.889) also crosses the 0.6 climb trigger — both
#    conditions met in the same window (research.md R4's three-value
#    ladder).
critical_in='{"stage":"implement","run":"r3","own":{"available":true,"counted":400,"intended":180,"ceiling":450},"history":[{"run":"r1","counted":185,"intended":180,"ceiling":450},{"run":"r2","counted":300,"intended":180,"ceiling":450}],"history_window":10,"consecutive_trigger":3,"climb_fraction":0.6}'
out="$(run_filter "$critical_in")"
note "critical fixture output: $out"
band="$(jq -r '.trend.band // "null"' <<<"$out")"
if [ "$band" != "critical" ]; then
  reason "climbing history (185,300,400 vs budget 180, ceiling 450) expected band 'critical', got '$band'"
else
  note "climbing history correctly produced band 'critical'"
fi
per_run_frac="$(jq -r '."per-run".facts."consumed-ceiling-fraction"' <<<"$out")"
if [ "$per_run_frac" != "0.889" ]; then
  reason "per-run consumed-ceiling-fraction expected 0.889 for 400/450, got '$per_run_frac'"
fi
# T041: the per-run signal's own facts.band must match this window's band —
# it is what Stamp signal ids now keys the per-run signal's identity on
# ({stage, band}, not {stage, run}), so the two signals a Finding cites
# together must agree on the same value.
per_run_band="$(jq -r '."per-run".facts.band // "null"' <<<"$out")"
if [ "$per_run_band" != "critical" ]; then
  reason "per-run signal's facts.band expected 'critical' to match the trend band, got '$per_run_band'"
else
  note "per-run signal's facts.band correctly matches the trend band 'critical'"
fi

# ── Fixture 2 (positive, watch): three consecutive at-or-over-budget runs
#    but a high ceiling keeps the consumed fraction low — consecutive
#    trigger alone met.
watch_in='{"stage":"implement","run":"r3","own":{"available":true,"counted":200,"intended":180,"ceiling":2000},"history":[{"run":"r1","counted":185,"intended":180,"ceiling":2000},{"run":"r2","counted":190,"intended":180,"ceiling":2000}],"history_window":10,"consecutive_trigger":3,"climb_fraction":0.6}'
out="$(run_filter "$watch_in")"
note "watch fixture output: $out"
band="$(jq -r '.trend.band // "null"' <<<"$out")"
if [ "$band" != "watch" ]; then
  reason "three consecutive at-or-over-budget runs under a high ceiling expected band 'watch', got '$band'"
else
  note "consecutive-only history correctly produced band 'watch'"
fi
per_run_band="$(jq -r '."per-run".facts.band // "null"' <<<"$out")"
if [ "$per_run_band" != "watch" ]; then
  reason "per-run signal's facts.band expected 'watch' to match the trend band, got '$per_run_band'"
else
  note "per-run signal's facts.band correctly matches the trend band 'watch'"
fi

# ── Fixture 3 (positive, elevated): the climb-fraction trigger alone met
#    (one run at 280/300 = 0.933), but the trailing (most recent) run is
#    under budget, so the consecutive count is 0.
elevated_in='{"stage":"implement","run":"r3","own":{"available":true,"counted":90,"intended":180,"ceiling":300},"history":[{"run":"r1","counted":100,"intended":180,"ceiling":300},{"run":"r2","counted":280,"intended":180,"ceiling":300}],"history_window":10,"consecutive_trigger":3,"climb_fraction":0.6}'
out="$(run_filter "$elevated_in")"
note "elevated fixture output: $out"
band="$(jq -r '.trend.band // "null"' <<<"$out")"
if [ "$band" != "elevated" ]; then
  reason "a lone high-fraction run (280/300) with no trailing consecutive run expected band 'elevated', got '$band'"
else
  note "climb-only history correctly produced band 'elevated'"
fi
per_run="$(jq -c '."per-run"' <<<"$out")"
if [ "$per_run" != "null" ]; then
  reason "own run 90/180 is under budget and must not emit a per-run signal, got $per_run"
else
  note "under-budget own run correctly emitted no per-run signal"
fi

# ── Fixture 4 (negative, under both thresholds): comfortably under budget
#    the whole window — no cross-run signal at all (Acceptance Scenario 6).
none_in='{"stage":"implement","run":"r3","own":{"available":true,"counted":120,"intended":180,"ceiling":500},"history":[{"run":"r1","counted":100,"intended":180,"ceiling":500},{"run":"r2","counted":110,"intended":180,"ceiling":500}],"history_window":10,"consecutive_trigger":3,"climb_fraction":0.6}'
out="$(run_filter "$none_in")"
note "under-threshold fixture output: $out"
trend="$(jq -c '.trend' <<<"$out")"
if [ "$trend" != "null" ]; then
  reason "a window comfortably under both thresholds must emit no cross-run signal, got $trend"
else
  note "under-threshold history correctly emitted no cross-run signal"
fi
per_run="$(jq -c '."per-run"' <<<"$out")"
if [ "$per_run" != "null" ]; then
  reason "own run 120/180 is under budget and must not emit a per-run signal, got $per_run"
else
  note "under-budget own run correctly emitted no per-run signal"
fi

# ── Fixture 5 (negative, turns.available: false): no per-run signal, and
#    the collector still reports outcome "ok" (Acceptance Scenario 7) — the
#    outcome itself is a bash-level concern outside this filter, so this
#    assertion covers the filter's own half of that contract: available:
#    false must never synthesize a per-run signal from stale counted/intended
#    values.
unavailable_in='{"stage":"implement","run":"r3","own":{"available":false,"counted":226,"intended":180,"ceiling":450},"history":[],"history_window":10,"consecutive_trigger":3,"climb_fraction":0.6}'
out="$(run_filter "$unavailable_in")"
note "turns.available:false fixture output: $out"
per_run="$(jq -c '."per-run"' <<<"$out")"
if [ "$per_run" != "null" ]; then
  reason "turns.available: false must produce no per-run signal even when counted >= intended, got $per_run"
else
  note "turns.available: false correctly produced no per-run signal"
fi

# ── Note on the skipped/cancelled fixture (attribution invariant, FR-004):
#    that guard is a bash-level `case "$RUN_CONCLUSION" in skipped|cancelled)`
#    exit-0 before this filter is ever invoked (mirrors every other
#    collector's attribution guard in watchdog.yml) — there is no filter
#    input to construct for it, so it is verified by inspecting the shipped
#    step directly rather than by feeding this filter a fixture that could
#    never reach it in production.
if [ -f ".github/workflows/watchdog.yml" ]; then
  if grep -A3 'id: collect-turn-budget' .github/workflows/watchdog.yml | grep -q 'continue-on-error: true'; then
    note "collect-turn-budget step present with continue-on-error: true"
  fi
  if grep -A40 'id: collect-turn-budget' .github/workflows/watchdog.yml | grep -q 'skipped|cancelled'; then
    note "collect-turn-budget carries the skipped|cancelled attribution guard"
  else
    reason "collect-turn-budget no longer carries a skipped|cancelled attribution guard (FR-004)"
  fi
else
  reason "cannot find .github/workflows/watchdog.yml to verify the attribution guard — run this from the repository root"
fi

if [ "${#fail_reasons[@]}" -eq 0 ]; then
  echo "✅ verify-turn-budget-collector: all assertions passed."
  exit 0
fi

echo "❌ verify-turn-budget-collector: ${#fail_reasons[@]} assertion(s) failed:"
for r in "${fail_reasons[@]}"; do echo "- $r"; done
exit 1
