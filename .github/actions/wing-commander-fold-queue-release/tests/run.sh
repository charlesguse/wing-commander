#!/usr/bin/env bash
# Fixtures for wing-commander-fold-queue-release/action.yml's own "Release
# ticket and record outcome" step, extracted and run against a throwaway
# LOCAL bare git repository (LEDGER_REMOTE_URL override -- no live
# network), matching wing-commander-fold-queue-admit/tests/run.sh's shape.
#
# Covers quickstart.md Drill 2: a normal release-with-outcome and an
# idempotent double-release.
#
# Not discovered by run-local-gates.py -- invoke directly:
# bash .github/actions/wing-commander-fold-queue-release/tests/run.sh
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSITE_DIR="$HERE/.."
ACTION_YML="$COMPOSITE_DIR/action.yml"
LEDGER_SH="$HERE/../../_shared/fold-queue-ledger.sh"
FAILURES=0

extract_step() {
  python3 - "$ACTION_YML" <<'PYEOF'
import sys
import yaml

with open(sys.argv[1], encoding="utf-8") as fh:
    doc = yaml.safe_load(fh)

steps = doc["runs"]["steps"]
sys.stdout.write(steps[0]["run"])
PYEOF
}

SCRIPT="$(mktemp)"
extract_step > "$SCRIPT"

WORK="$(mktemp -d)"
REMOTE="$WORK/fold-queue-remote.git"
git init --quiet --bare "$REMOTE"

trap 'rm -f "$SCRIPT"; rm -rf "$WORK"' EXIT

SPEC_DIR="specs/074-serialized-fold-dispatch"

run_release() {
  local token="$1" round="$2" leg_id="$3" outcome="$4" commit_sha="$5" run_id="${6:-200}"
  local summary_file
  summary_file="$(mktemp)"
  GITHUB_ACTION_PATH="$COMPOSITE_DIR" \
    GH_TOKEN=x GITHUB_REPOSITORY=x/x \
    LEDGER_REMOTE_URL="$REMOTE" \
    SPEC_DIR="$SPEC_DIR" TOKEN="$token" ROUND="$round" RUN_ID="$run_id" LEG_ID="$leg_id" \
    OUTCOME="$outcome" COMMIT_SHA="$commit_sha" SUMMARY="s" \
    GITHUB_STEP_SUMMARY="$summary_file" \
    bash "$SCRIPT"
}

# --- Scenario 1: normal release-with-outcome --------------------------------
LEDGER_REMOTE_URL="$REMOTE" GH_TOKEN=x GITHUB_REPOSITORY=x/x SPEC_DIR="$SPEC_DIR" \
  KIND=act RUN_ID=200 bash "$LEDGER_SH" enqueue >/dev/null

if run_release "run-200-act" 1 "leg-1" "folded" "deadbeef"; then
  peek_out="$(LEDGER_REMOTE_URL="$REMOTE" GH_TOKEN=x GITHUB_REPOSITORY=x/x SPEC_DIR="$SPEC_DIR" PEEK_TOKEN="run-200-act" bash "$LEDGER_SH" peek)"
  position="$(printf '%s\n' "$peek_out" | grep '^position=' | cut -d= -f2-)"
  if [ "$position" = "-1" ]; then
    echo "[ok] normal release-with-outcome: token removed from queue"
  else
    echo "::error::[normal release-with-outcome] token still in queue at position $position"
    FAILURES=$((FAILURES + 1))
  fi
else
  echo "::error::[normal release-with-outcome] release step exited non-zero"
  FAILURES=$((FAILURES + 1))
fi

# --- Scenario 2: idempotent double-release ----------------------------------
if run_release "run-200-act" 1 "leg-1" "folded" "deadbeef"; then
  echo "[ok] idempotent double-release: second release of an absent token is a no-op"
else
  echo "::error::[idempotent double-release] second release exited non-zero"
  FAILURES=$((FAILURES + 1))
fi

# --- Scenario 3: a second leg of the SAME run's matrix, sharing the SAME
# (already-dequeued) ticket, still gets its own completion recorded -----
if run_release "run-200-act" 1 "leg-2" "not-folded" ""; then
  echo "[ok] second leg of the same run still records its own completion after the shared ticket was already dequeued"
else
  echo "::error::[second leg, same shared ticket] release exited non-zero"
  FAILURES=$((FAILURES + 1))
fi

echo "wing-commander-fold-queue-release tests: $FAILURES failure(s)."
[ "$FAILURES" -eq 0 ]
