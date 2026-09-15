#!/usr/bin/env bash
# Deterministic fixture check for watchdog.yml's narrative-drift
# issue-exemption routing (research.md R9) — specs/046-watchdog-
# supervision-collectors, contracts/gate-coverage-046.md's
# verify-narrative-drift-routing.sh row.
#
# Two halves: (1) EXECUTE the shipped `Determine issue-filing eligibility`
# step (wc_shell_harness.find_step/run_step) against fixture classes — this
# used to be a hand copy of the step's if/else, which mutation testing found
# stayed green through the shipped "narrative-drift" literal being broken
# (constitution VIII); (2) confirm, by reading the live watchdog.yml, that
# `Ensure pipeline-defect issue` actually gates on that decision and that
# `Report finding to lifecycle issue` remains unconditional (FR-025 requires
# the mismatch to still reach the lifecycle issue even though no tracked
# issue is ever filed for it).
#
# Usage: .github/scripts/verify-narrative-drift-routing.sh
# Exit code: 0 = all assertions passed; 1 = an assertion failed.

set -uo pipefail

fail_reasons=()
note() { echo "::notice::verify-narrative-drift-routing: $1"; }
reason() { fail_reasons+=("$1"); echo "::error::verify-narrative-drift-routing: $1"; }

if ! command -v jq >/dev/null 2>&1 || ! command -v python3 >/dev/null 2>&1; then
  echo "::error::verify-narrative-drift-routing: jq and python3 are both required."
  exit 1
fi

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

python3 - "$work" <<'PY'
import os
import sys

sys.path.insert(0, ".github/scripts")
from wc_shell_harness import find_step, resolve_bash, run_step, use_utf8_stdout  # noqa: E402

use_utf8_stdout()
bash = resolve_bash()
workdir = sys.argv[1]
step = find_step(".github/workflows/watchdog.yml", "Determine issue-filing eligibility")
script = step["run"]
if "${{" in script:
    sys.exit("::error::verify-narrative-drift-routing: 'Determine issue-filing "
              "eligibility' now contains an unresolved ${{ }} expression this "
              "harness does not substitute.")

cases = [("narrative-drift", "true")] + [
    (cls, "false") for cls in
    ("denied-tool", "lost-progress", "stage-mismatch", "turn-budget-trend",
     "cost-line-missing", "cost-line-malformed", "spec-number-collision")
]
failures = []
for cls, expect in cases:
    runner_temp = os.path.join(workdir, "rt-" + cls.replace(" ", "_"))
    os.makedirs(runner_temp, exist_ok=True)
    rc, out, outputs, _ = run_step(bash, script, workdir, {"FINDING_CLASS": cls}, runner_temp)
    got = outputs.get("issueless")
    if rc != 0 or got != expect:
        failures.append(f"class {cls!r} expected issueless={expect!r}, got rc={rc} issueless={got!r}: {out}")
    else:
        print(f"::notice::verify-narrative-drift-routing: class {cls!r} correctly sets issueless={expect!r}")

if failures:
    for f in failures:
        print(f"::error::verify-narrative-drift-routing: {f}")
    sys.exit(1)
print("verify-narrative-drift-routing: shipped 'Determine issue-filing eligibility' step matches for every class.")
PY
py_rc=$?
if [ "$py_rc" -ne 0 ]; then
  reason "the shipped 'Determine issue-filing eligibility' step (executed directly, not a copy) failed one or more class fixtures — see ::error:: above"
fi

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
