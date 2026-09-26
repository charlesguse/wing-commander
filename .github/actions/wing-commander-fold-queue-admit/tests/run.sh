#!/usr/bin/env bash
# Fixtures for wing-commander-fold-queue-admit/action.yml's own "Enqueue
# (or resolve existing token) and await this run's turn" step, extracted
# and run against a throwaway LOCAL bare git repository (LEDGER_REMOTE_URL
# override -- no live network, matching this repository's existing
# dispatch-and-wait-tests/run-tests.sh discipline of executing the shipped
# shell itself rather than a restatement of it).
#
# Covers quickstart.md Drill 2's three scenarios: a clean immediate grant,
# a queued-then-granted sequence, and one stale-ticket reclaim.
#
# Not discovered by run-local-gates.py (.github/actions/**/tests/ is
# outside its scan, per this repository's existing size-path-backstop-tests
# precedent) -- invoke directly: bash .github/actions/wing-commander-fold-queue-admit/tests/run.sh
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

for step in doc["runs"]["steps"]:
    if step.get("id") == "admit":
        sys.stdout.write(step["run"])
        break
else:
    sys.exit("no step with id: admit found in " + sys.argv[1])
PYEOF
}

SCRIPT="$(mktemp)"
extract_step > "$SCRIPT"

WORK="$(mktemp -d)"
REMOTE="$WORK/fold-queue-remote.git"
STUBDIR="$WORK/stub"
mkdir -p "$STUBDIR"
git init --quiet --bare "$REMOTE"

trap 'rm -f "$SCRIPT"; rm -rf "$WORK"' EXIT

# GH_STUB_STATUS selects the fake `gh api .../runs/<id>`'s reported status
# for the reclaim-stale path's independent liveness check.
cat > "$STUBDIR/gh" <<'GHSTUB'
#!/usr/bin/env bash
set -uo pipefail
if [ "$1" = "api" ]; then
  echo "${GH_STUB_STATUS:-completed}"
  exit 0
fi
exit 1
GHSTUB
chmod +x "$STUBDIR/gh"

SPEC_DIR="specs/074-serialized-fold-dispatch"

run_admit() {
  local run_id="$1" kind="$2" existing_token="$3" max_wait="$4" poll="$5" stale_after="$6"
  local out_file summary_file
  out_file="$(mktemp)"
  summary_file="$(mktemp)"
  PATH="$STUBDIR:$PATH" \
    GITHUB_ACTION_PATH="$COMPOSITE_DIR" \
    GH_TOKEN=x GITHUB_REPOSITORY=x/x \
    LEDGER_REMOTE_URL="$REMOTE" \
    SPEC_DIR="$SPEC_DIR" KIND="$kind" RUN_ID="$run_id" EXISTING_TOKEN="$existing_token" \
    MAX_WAIT_MINUTES="$max_wait" POLL_INTERVAL_SECONDS="$poll" STALE_AFTER_MINUTES="$stale_after" \
    GITHUB_OUTPUT="$out_file" GITHUB_STEP_SUMMARY="$summary_file" \
    bash "$SCRIPT"
  local rc=$?
  echo "$out_file"
  return $rc
}

# --- Scenario 1: clean immediate grant (empty ledger) ----------------------
out_file="$(run_admit 100 act "" 1 1 1)"
rc=$?
token="$(grep '^token=' "$out_file" | cut -d= -f2-)"
granted="$(grep '^granted=' "$out_file" | cut -d= -f2-)"
if [ "$rc" -eq 0 ] && [ "$token" = "run-100-act" ] && [ "$granted" = "true" ]; then
  echo "[ok] clean immediate grant: token=$token granted=$granted"
else
  echo "::error::[clean immediate grant] rc=$rc token=${token:-<empty>} granted=${granted:-<empty>}"
  FAILURES=$((FAILURES + 1))
fi
rm -f "$out_file"

# --- Scenario 2: queued-then-granted ----------------------------------------
LEDGER_REMOTE_URL="$REMOTE" GH_TOKEN=x GITHUB_REPOSITORY=x/x SPEC_DIR="$SPEC_DIR" \
  KIND=act RUN_ID=101 bash "$LEDGER_SH" enqueue >/dev/null

(
  sleep 2
  LEDGER_REMOTE_URL="$REMOTE" GH_TOKEN=x GITHUB_REPOSITORY=x/x SPEC_DIR="$SPEC_DIR" \
    TOKEN="run-101-act" OUTCOME="folded" COMMIT_SHA="abc123" LEG_ID="leg-1" SUMMARY="s" \
    bash "$LEDGER_SH" release >/dev/null
) &
releaser_pid=$!

out_file="$(run_admit 102 act "" 1 1 1)"
rc=$?
wait "$releaser_pid"
token="$(grep '^token=' "$out_file" | cut -d= -f2-)"
granted="$(grep '^granted=' "$out_file" | cut -d= -f2-)"
if [ "$rc" -eq 0 ] && [ "$token" = "run-102-act" ] && [ "$granted" = "true" ]; then
  echo "[ok] queued-then-granted: token=$token granted=$granted"
else
  echo "::error::[queued-then-granted] rc=$rc token=${token:-<empty>} granted=${granted:-<empty>}"
  FAILURES=$((FAILURES + 1))
fi
rm -f "$out_file"

# --- Scenario 3: stale-ticket reclaim ---------------------------------------
LEDGER_REMOTE_URL="$REMOTE" GH_TOKEN=x GITHUB_REPOSITORY=x/x SPEC_DIR="$SPEC_DIR" \
  KIND=act RUN_ID=103 bash "$LEDGER_SH" enqueue >/dev/null

out_file="$(GH_STUB_STATUS=completed run_admit 104 act "" 1 1 0)"
rc=$?
token="$(grep '^token=' "$out_file" | cut -d= -f2-)"
granted="$(grep '^granted=' "$out_file" | cut -d= -f2-)"
if [ "$rc" -eq 0 ] && [ "$token" = "run-104-act" ] && [ "$granted" = "true" ]; then
  echo "[ok] stale-ticket reclaim: token=$token granted=$granted"
else
  echo "::error::[stale-ticket reclaim] rc=$rc token=${token:-<empty>} granted=${granted:-<empty>}"
  FAILURES=$((FAILURES + 1))
fi
rm -f "$out_file"

echo "wing-commander-fold-queue-admit tests: $FAILURES failure(s)."
[ "$FAILURES" -eq 0 ]
