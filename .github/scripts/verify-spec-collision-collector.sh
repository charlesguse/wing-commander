#!/usr/bin/env bash
# Deterministic fixture check for watchdog.yml's "Collect: spec collision"
# step (id: collect-spec-collision) — specs/046-watchdog-supervision-
# collectors, contracts/gate-coverage-046.md's
# verify-spec-collision-collector.sh row.
#
# FILTER below is EXTRACTED from watchdog.yml's live SPEC_COLLISION_FILTER
# at run time (wc_shell_harness.extract_quoted_var), not a hand-typed copy —
# mutation testing found a hand copy here stayed green through a shipped
# collision-threshold break (constitution VIII). No live gh pr list call is
# needed: this feeds the exact claimant-enumeration fixture inputs the
# surrounding bash would have already derived from `gh pr list` and the
# checked-out `specs/` directory listing.
#
# Usage: .github/scripts/verify-spec-collision-collector.sh
# Exit code: 0 = all assertions passed; 1 = an assertion failed.

set -uo pipefail

fail_reasons=()
note() { echo "::notice::verify-spec-collision-collector: $1"; }
reason() { fail_reasons+=("$1"); echo "::error::verify-spec-collision-collector: $1"; }

if ! command -v jq >/dev/null 2>&1 || ! command -v python3 >/dev/null 2>&1; then
  echo "::error::verify-spec-collision-collector: jq and python3 are both required."
  exit 1
fi

FILTER="$(python3 - <<'PY'
import sys
sys.path.insert(0, ".github/scripts")
from wc_shell_harness import extract_quoted_var
print(extract_quoted_var(".github/workflows/watchdog.yml", "SPEC_COLLISION_FILTER"))
PY
)"

run_filter() { jq -c "$FILTER" <<<"$1"; }

# ── Positive: two open PRs sharing the same numeric prefix (046).
out="$(run_filter '{"own_number":"046","pr_claimants":[{"pr":301,"branch":"spec-draft/046-watchdog-supervision-collectors","number":"046"},{"pr":305,"branch":"spec-draft/046-a-different-feature","number":"046"}],"dir_claimants":[]}')"
note "two-open-PR fixture output: $out"
if [ "$(jq '.[0].facts.claimants | length' <<<"$out" 2>/dev/null || echo 0)" != "2" ]; then
  reason "two open PRs sharing number 046 must produce a collision naming both, got $out"
else
  note "two open PRs sharing a number correctly produced a collision naming both"
fi

# ── Positive: one open PR matching an existing specs/ directory on main.
out="$(run_filter '{"own_number":"046","pr_claimants":[{"pr":301,"branch":"spec-draft/046-watchdog-supervision-collectors","number":"046"}],"dir_claimants":[{"dir":"specs/046-old-landed-spec","number":"046"}]}')"
note "PR-vs-directory fixture output: $out"
kinds="$(jq -c '[.[0].facts.claimants[].kind] | sort' <<<"$out" 2>/dev/null || echo '[]')"
if [ "$kinds" != '["main-directory","open-pr"]' ]; then
  reason "an open PR matching an existing specs/ directory must produce a collision naming both an open-pr and a main-directory claimant, got $out"
else
  note "PR-vs-main-directory correctly produced a collision naming both claimant kinds"
fi

# ── Negative: every open PR has a distinct number → no signal.
out="$(run_filter '{"own_number":"046","pr_claimants":[{"pr":301,"branch":"spec-draft/046-watchdog-supervision-collectors","number":"046"},{"pr":312,"branch":"spec-draft/047-unrelated","number":"047"}],"dir_claimants":[]}')"
if [ "$out" != "[]" ]; then
  reason "every open PR carrying a distinct number must produce no signal, got $out"
else
  note "all-distinct numbers correctly produced no signal"
fi

# ── Negative: a PR observed twice (the same run re-inspected) must not
#    self-collide (FR-028) — jq's `unique` on the projected {kind,pr,branch}
#    object collapses an exact duplicate to one claimant.
out="$(run_filter '{"own_number":"046","pr_claimants":[{"pr":301,"branch":"spec-draft/046-watchdog-supervision-collectors","number":"046"},{"pr":301,"branch":"spec-draft/046-watchdog-supervision-collectors","number":"046"}],"dir_claimants":[]}')"
if [ "$out" != "[]" ]; then
  reason "the same PR observed twice must not self-collide, got $out"
else
  note "the same PR observed twice correctly did not self-collide"
fi

# ── Note on the non-intake-run fixture (scope guard): that guard is a
#    bash-level `if [ "$RUN_NAME" != "Wing Commander · 1 intake" ]` exit-0
#    before this filter is ever invoked — verified by inspecting the
#    shipped step directly, the same way verify-turn-budget-collector.sh
#    verifies its own attribution guard.
WATCHDOG_YML=".github/workflows/watchdog.yml"
if [ -f "$WATCHDOG_YML" ]; then
  if grep -A25 'id: collect-spec-collision' "$WATCHDOG_YML" | grep -q "Wing Commander · 1 intake"; then
    note "collect-spec-collision carries the intake-only scope guard"
  else
    reason "collect-spec-collision no longer scopes itself to intake-completion runs"
  fi
else
  reason "cannot find $WATCHDOG_YML to verify the scope guard — run this from the repository root"
fi

if [ "${#fail_reasons[@]}" -eq 0 ]; then
  echo "✅ verify-spec-collision-collector: all assertions passed."
  exit 0
fi

echo "❌ verify-spec-collision-collector: ${#fail_reasons[@]} assertion(s) failed:"
for r in "${fail_reasons[@]}"; do echo "- $r"; done
exit 1
