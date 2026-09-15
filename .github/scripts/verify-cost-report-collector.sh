#!/usr/bin/env bash
# Deterministic fixture check for watchdog.yml's "Collect: cost report" step
# (id: collect-cost-report) — specs/046-watchdog-supervision-collectors,
# contracts/gate-coverage-046.md's verify-cost-report-collector.sh row.
#
# FILTER below is EXTRACTED from watchdog.yml's live COST_REPORT_FILTER at
# run time (wc_shell_harness.extract_quoted_var), not a hand-typed copy —
# mutation testing found a hand copy here stayed green through a shipped
# cost-validity break (constitution VIII). No live watchdog run, gh api
# call, or lifecycle-issue comment listing is needed: this feeds the exact
# missing/malformed decision fixture inputs describing what the surrounding
# bash would have already resolved (cost_available, whether an attributable
# comment was found, and any extracted cost token).
#
# Usage: .github/scripts/verify-cost-report-collector.sh
# Exit code: 0 = all assertions passed; 1 = an assertion failed.

set -uo pipefail

fail_reasons=()
note() { echo "::notice::verify-cost-report-collector: $1"; }
reason() { fail_reasons+=("$1"); echo "::error::verify-cost-report-collector: $1"; }

if ! command -v jq >/dev/null 2>&1 || ! command -v python3 >/dev/null 2>&1; then
  echo "::error::verify-cost-report-collector: jq and python3 are both required."
  exit 1
fi

FILTER="$(python3 - <<'PY'
import sys
sys.path.insert(0, ".github/scripts")
from wc_shell_harness import extract_quoted_var
print(extract_quoted_var(".github/workflows/watchdog.yml", "COST_REPORT_FILTER"))
PY
)"

run_filter() { jq -c "$FILTER" <<<"$1"; }

# ── Positive: cost_available true, no attributable comment at all.
out="$(run_filter '{"stage":"plan","run":"r1","cost_available":true,"comment_found":false,"cost_token":null,"observed_text":null}')"
note "no-comment fixture output: $out"
if [ "$(jq -r '.[0]."class-hint" // "none"' <<<"$out")" != "cost-line-missing" ]; then
  reason "cost_available:true with no attributable comment expected 'cost-line-missing', got $out"
else
  note "no attributable comment correctly produced cost-line-missing"
fi
if [ "$(jq -r '.[0].facts."lifecycle-comment-found"' <<<"$out")" != "false" ]; then
  reason "cost-line-missing with no comment at all must set lifecycle-comment-found:false"
fi

# ── Positive: the literal #272 $COST_LINE leak, comment found but the
#    figure is not currency-shaped at all.
# shellcheck disable=SC2016 # single-quoted JSON literal, not a shell expansion
out="$(run_filter '{"stage":"implement","run":"r2","cost_available":true,"comment_found":true,"cost_token":"$COST_LINE","observed_text":"Cost: $COST_LINE · 40 turns"}')"
note "COST_LINE leak fixture output: $out"
if [ "$(jq -r '.[0]."class-hint" // "none"' <<<"$out")" != "cost-line-malformed" ]; then
  reason "a literal \$COST_LINE leak expected 'cost-line-malformed', got $out"
else
  note "the \$COST_LINE leak correctly produced cost-line-malformed"
fi
observed="$(jq -r '.[0].facts."observed-text"' <<<"$out")"
# shellcheck disable=SC2016 # literal comparison text, not a shell expansion
if [ "$observed" != 'Cost: $COST_LINE · 40 turns' ]; then
  reason "cost-line-malformed must carry the exact observed text (FR-018), got $observed"
fi

# ── Negative: cost_available false → no signal regardless of comment state.
out="$(run_filter '{"stage":"plan","run":"r3","cost_available":false,"comment_found":false,"cost_token":null,"observed_text":null}')"
if [ "$out" != "[]" ]; then
  reason "cost_available:false must never produce a signal, got $out"
else
  note "cost_available:false correctly produced no signal"
fi

# ── Negative: well-formed >= \$1 figure (2dp) → no signal.
# shellcheck disable=SC2016 # single-quoted JSON literal, not a shell expansion
out="$(run_filter '{"stage":"implement","run":"r4","cost_available":true,"comment_found":true,"cost_token":"$1.42","observed_text":"Cost: $1.42 · 38/60 turns"}')"
if [ "$out" != "[]" ]; then
  reason "a well-formed >=\$1 figure (\$1.42, 2dp) must produce no signal, got $out"
else
  note "well-formed >=\$1 figure correctly produced no signal"
fi

# ── Negative: well-formed sub-\$1 figure (4dp, research.md R8's
#    magnitude-aware pattern) → no signal. This is the case most likely to
#    regress under a single-precision rewrite: a naive ^\$[0-9]+\.[0-9]{2}\$
#    pattern would falsely flag this as malformed.
# shellcheck disable=SC2016 # single-quoted JSON literal, not a shell expansion
out="$(run_filter '{"stage":"implement","run":"r5","cost_available":true,"comment_found":true,"cost_token":"$0.0042","observed_text":"Cost: $0.0042 · 3/10 turns"}')"
if [ "$out" != "[]" ]; then
  reason "a well-formed sub-\$1 figure (\$0.0042, 4dp) must produce no signal under the magnitude-aware pattern, got $out"
else
  note "well-formed sub-\$1 figure (4dp) correctly produced no signal"
fi

# ── Negative (boundary): exactly \$1.00 — the magnitude crossover
#    research.md R8 names between the 2dp (>= \$1) and 4dp (< \$1) patterns.
#    The 2dp pattern's leading digit class is [1-9], which \$1.00 satisfies
#    exactly at the boundary, so this must still validate rather than fall
#    through to "malformed" the way a naive off-by-one on the crossover would.
# shellcheck disable=SC2016 # single-quoted JSON literal, not a shell expansion
out="$(run_filter '{"stage":"implement","run":"r6","cost_available":true,"comment_found":true,"cost_token":"$1.00","observed_text":"Cost: $1.00 · 12/60 turns"}')"
if [ "$out" != "[]" ]; then
  reason "the exact \$1.00 magnitude-crossover figure (2dp) must produce no signal, got $out"
else
  note "the exact \$1.00 magnitude crossover correctly produced no signal"
fi

if [ "${#fail_reasons[@]}" -eq 0 ]; then
  echo "✅ verify-cost-report-collector: all assertions passed."
  exit 0
fi

echo "❌ verify-cost-report-collector: ${#fail_reasons[@]} assertion(s) failed:"
for r in "${fail_reasons[@]}"; do echo "- $r"; done
exit 1
