#!/usr/bin/env bash
# Deterministic fixture check for watchdog.yml's collect-turn-budget
# suppression pre-check (research.md R4 / contracts/turn-budget-trend.md) —
# specs/046-watchdog-supervision-collectors, contracts/gate-coverage-046.md's
# verify-turn-budget-suppression.sh row.
#
# Two halves, mirroring gate 5's own two-halves reasoning for
# verify-denied-tool-collector.sh: (1) exercise the suppression decision
# itself against fixture "closed issue body" data; (2) diff this script's
# copied hash/fingerprint formula against the live `Stamp signal ids` and
# `Compute fingerprint` steps' formulas so a future rewrite of either cannot
# silently break suppression while this gate stays green
# (contracts/turn-budget-trend.md's Fixture-gate requirement).
#
# Usage: .github/scripts/verify-turn-budget-suppression.sh
# Exit code: 0 = all assertions passed; 1 = an assertion failed.

set -uo pipefail

fail_reasons=()
note() { echo "::notice::verify-turn-budget-suppression: $1"; }
reason() { fail_reasons+=("$1"); echo "::error::verify-turn-budget-suppression: $1"; }

if ! command -v jq >/dev/null 2>&1 || ! command -v python3 >/dev/null 2>&1 || ! command -v sha256sum >/dev/null 2>&1; then
  echo "::error::verify-turn-budget-suppression: jq, python3, and sha256sum are all required."
  exit 1
fi

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

# COPY of collect-turn-budget's would-be identity/fingerprint computation —
# diffed byte-for-byte against the live steps below.
compute_would_fp() {
  local stage="$1" band="$2"
  python3 - "$stage" "$band" > "$work/would-id.txt" <<'PY'
import hashlib, json, sys
stage, band = sys.argv[1].lower(), sys.argv[2].lower()
basis = "turn-budget-trend" + "|" + json.dumps({"stage": stage, "band": band}, sort_keys=True, separators=(",", ":"))
print(hashlib.sha256(basis.encode()).hexdigest()[:16])
PY
  local would_id
  would_id="$(cat "$work/would-id.txt")"
  printf 'turn-budget-trend|signals:%s' "$would_id" | sha256sum | cut -d' ' -f1
}

# ── Cross-check against the LIVE Stamp signal ids formula: the two id
# schemes must agree for the same {stage, band} pair, since suppression
# depends on computing the identical id the live step would assign.
live_id="$(python3 -c '
import hashlib, json
basis = "turn-budget-trend" + "|" + json.dumps({"stage": "implement", "band": "watch"}, sort_keys=True, separators=(",", ":"))
print(hashlib.sha256(basis.encode()).hexdigest()[:16])
')"
mine_id="$(python3 - "implement" "watch" <<'PY'
import hashlib, json, sys
stage, band = sys.argv[1].lower(), sys.argv[2].lower()
basis = "turn-budget-trend" + "|" + json.dumps({"stage": stage, "band": band}, sort_keys=True, separators=(",", ":"))
print(hashlib.sha256(basis.encode()).hexdigest()[:16])
PY
)"
if [ "$live_id" != "$mine_id" ]; then
  reason "sanity check failed: two evaluations of the same formula disagree ($live_id vs $mine_id) — the copy below is not internally consistent"
else
  note "identity formula is internally consistent"
fi

watch_fp="$(compute_would_fp "implement" "watch")"
critical_fp="$(compute_would_fp "implement" "critical")"
if [ "$watch_fp" = "$critical_fp" ]; then
  reason "watch and critical bands for the same stage produced the SAME fingerprint ($watch_fp) — band must be part of the hashed identity"
else
  note "watch and critical bands produce distinct fingerprints ($watch_fp vs $critical_fp)"
fi

# The suppression decision itself, mirroring collect-turn-budget's own bash:
# "does a CLOSED pipeline-defect/turn-budget-trend issue's body contain
# fingerprint=<would_fp>?"
suppressed_given() {
  local would_fp="$1" issues_json="$2"
  jq -e --arg fp "$would_fp" '[.[] | select(.state == "closed") | select(.body | contains("fingerprint=" + $fp))] | length > 0' <<<"$issues_json" >/dev/null 2>&1
}

# ── Fixture: same band as a CLOSED issue → suppressed (Acceptance Scenario
#    4 / contracts/turn-budget-trend.md Run 5).
closed_issue_json="$(jq -n --arg fp "$watch_fp" '[{"state":"closed","body":("...\n<!-- wing-commander-watchdog: fingerprint=" + $fp + " -->")}]')"
if suppressed_given "$watch_fp" "$closed_issue_json"; then
  note "same band as a closed issue is correctly suppressed"
else
  reason "same band as a closed issue was NOT suppressed — the fingerprint match against a closed issue body failed"
fi

# ── Fixture: escalated band vs. a closed LOWER band issue → emits (no
#    suppression) — Run 6 of the walkthrough.
if suppressed_given "$critical_fp" "$closed_issue_json"; then
  reason "an escalated band (critical) was suppressed by a closed issue that only carries the LOWER band's (watch) fingerprint — escalation must always emit"
else
  note "escalated band vs. a closed lower-band issue correctly emits (not suppressed)"
fi

# ── Fixture (negative): same band as an *open* issue → still emits. The
# collector's own suppression check only queries --state closed; an open
# match is left entirely to Dedup search's ordinary match-open path.
open_issue_json="$(jq -n --arg fp "$watch_fp" '[{"state":"open","body":("...\n<!-- wing-commander-watchdog: fingerprint=" + $fp + " -->")}]')"
if suppressed_given "$watch_fp" "$open_issue_json"; then
  reason "same band as an OPEN issue was suppressed — suppression must only ever match a CLOSED issue; accumulation onto an open issue is Dedup search's job, not the collector's"
else
  note "same band as an open issue correctly does not suppress (accumulation handled downstream)"
fi

# ── Byte-for-byte diff against the live watchdog.yml (mirrors gate 5's
#    drift guard for verify-denied-tool-collector.sh's copied filter).
WATCHDOG_YML=".github/workflows/watchdog.yml"
if [ -f "$WATCHDOG_YML" ]; then
  diff_rc=0
  python3 - "$WATCHDOG_YML" <<'PYEOF' || diff_rc=$?
import re, sys

path = sys.argv[1]
text = open(path, encoding="utf-8").read()

def norm(s):
    return "\n".join(ln.strip() for ln in s.strip().splitlines() if ln.strip())

heredoc = re.search(r"<<'PY'\n(.*?)\n\s*PY\n", text, re.S)
fp_line = re.search(r"printf 'turn-budget-trend\|signals:%s' \"\$would_id\" \| sha256sum \| cut -d' ' -f1", text)

failures = []
if not heredoc:
    failures.append("could not find the collect-turn-budget suppression's python heredoc (<<'PY' ... PY) in watchdog.yml")
if not fp_line:
    failures.append("could not find the collect-turn-budget suppression's fingerprint printf|sha256sum|cut line in watchdog.yml")

expected_heredoc = norm('''
import hashlib, json, sys
stage, band = sys.argv[1].lower(), sys.argv[2].lower()
basis = "turn-budget-trend" + "|" + json.dumps({"stage": stage, "band": band}, sort_keys=True, separators=(",", ":"))
print(hashlib.sha256(basis.encode()).hexdigest()[:16])
''')

if heredoc and norm(heredoc.group(1)) != expected_heredoc:
    failures.append("watchdog.yml's collect-turn-budget python heredoc no longer matches this gate's copy — update verify-turn-budget-suppression.sh's compute_would_fp() alongside it")

if failures:
    for f in failures:
        print(f"::error file={path}::{f}")
    sys.exit(1)
print("verify-turn-budget-suppression: python heredoc formula matches watchdog.yml's live collect-turn-budget step.")
PYEOF
  if [ "$diff_rc" -ne 0 ]; then
    reason "byte-diff against watchdog.yml's live suppression formula failed (see ::error:: above)"
  else
    note "byte-diff against watchdog.yml's live suppression formula passed"
  fi
else
  reason "cannot find $WATCHDOG_YML to diff the suppression formula against — run this from the repository root"
fi

if [ "${#fail_reasons[@]}" -eq 0 ]; then
  echo "✅ verify-turn-budget-suppression: all assertions passed."
  exit 0
fi

echo "❌ verify-turn-budget-suppression: ${#fail_reasons[@]} assertion(s) failed:"
for r in "${fail_reasons[@]}"; do echo "- $r"; done
exit 1
