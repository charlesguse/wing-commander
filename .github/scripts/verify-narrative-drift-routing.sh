#!/usr/bin/env bash
# Deterministic fixture check for watchdog.yml's narrative-drift
# issue-exemption routing (research.md R9) — specs/046-watchdog-
# supervision-collectors, contracts/gate-coverage-046.md's
# verify-narrative-drift-routing.sh row.
#
# Two halves: (1) exercise the `Determine issue-filing eligibility` step's
# decision logic directly against fixture classes; (2) confirm, by reading
# the live watchdog.yml, that `Ensure pipeline-defect issue` actually gates
# on that decision and that `Report finding to lifecycle issue` remains
# unconditional (FR-025 requires the mismatch to still reach the lifecycle
# issue even though no tracked issue is ever filed for it).
#
# Usage: .github/scripts/verify-narrative-drift-routing.sh
# Exit code: 0 = all assertions passed; 1 = an assertion failed.

set -uo pipefail

fail_reasons=()
note() { echo "::notice::verify-narrative-drift-routing: $1"; }
reason() { fail_reasons+=("$1"); echo "::error::verify-narrative-drift-routing: $1"; }

# COPY of the `Determine issue-filing eligibility` step's decision.
eligibility() {
  local finding_class="$1"
  if [ "$finding_class" = "narrative-drift" ]; then
    echo "issueless=true"
  else
    echo "issueless=false"
  fi
}

# ── Positive: a narrative-drift Finding → issueless: true.
out="$(eligibility "narrative-drift")"
if [ "$out" != "issueless=true" ]; then
  reason "class 'narrative-drift' expected issueless=true, got '$out'"
else
  note "narrative-drift correctly sets issueless=true"
fi

# ── Negative: every other class → issueless: false (normal issue-filing
#    path unaffected).
for cls in denied-tool lost-progress stage-mismatch turn-budget-trend cost-line-missing cost-line-malformed spec-number-collision; do
  out="$(eligibility "$cls")"
  if [ "$out" != "issueless=false" ]; then
    reason "class '$cls' expected issueless=false, got '$out'"
  else
    note "class '$cls' correctly sets issueless=false"
  fi
done

# ── Confirm the live wiring: Ensure pipeline-defect issue gates on
#    issueless, Report finding to lifecycle issue remains unconditional.
WATCHDOG_YML=".github/workflows/watchdog.yml"
if [ -f "$WATCHDOG_YML" ]; then
  if grep -A10 'name: Ensure pipeline-defect issue' "$WATCHDOG_YML" | grep -q "steps.decision.outputs.issueless != 'true'"; then
    note "Ensure pipeline-defect issue carries the issueless skip condition"
  else
    reason "Ensure pipeline-defect issue no longer carries steps.decision.outputs.issueless != 'true' — a narrative-drift Finding could file a tracked issue (FR-025 violation)"
  fi

  if grep -A3 'name: Report finding to lifecycle issue' "$WATCHDOG_YML" | grep -q "if: always() && steps.finding.outcome == 'success'"; then
    note "Report finding to lifecycle issue remains unconditional (always(), gated only on the body having loaded)"
  else
    reason "Report finding to lifecycle issue's if: condition changed shape — FR-025 requires it stay unconditional so a narrative-drift Finding still reaches the lifecycle issue"
  fi

  if grep -A40 'name: Report finding to lifecycle issue' "$WATCHDOG_YML" | grep -q 'ISSUELESS'; then
    note "Report finding to lifecycle issue reads ISSUELESS and carries its own issue-exempt wording"
  else
    reason "Report finding to lifecycle issue no longer reads ISSUELESS — the issue-exempt path has no distinct wording from the coexistence-suppressed branch (research.md R9)"
  fi

  if grep -q 'name: Determine issue-filing eligibility' "$WATCHDOG_YML"; then
    note "Determine issue-filing eligibility step is present in triage"
  else
    reason "Determine issue-filing eligibility step is missing from watchdog.yml's triage job"
  fi
else
  reason "cannot find $WATCHDOG_YML to verify the routing wiring — run this from the repository root"
fi

if [ "${#fail_reasons[@]}" -eq 0 ]; then
  echo "✅ verify-narrative-drift-routing: all assertions passed."
  exit 0
fi

echo "❌ verify-narrative-drift-routing: ${#fail_reasons[@]} assertion(s) failed:"
for r in "${fail_reasons[@]}"; do echo "- $r"; done
exit 1
