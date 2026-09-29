#!/usr/bin/env bash
# Fixtures for wing-commander-fold-queue-admit/action.yml's own "Enqueue
# (or resolve existing token) and await this run's turn" step, extracted
# and run against a throwaway LOCAL bare git repository (LEDGER_REMOTE_URL
# override -- no live network, matching this repository's existing
# dispatch-and-wait-tests/run-tests.sh discipline of executing the shipped
# shell itself rather than a restatement of it).
#
# Covers quickstart.md Drill 2's three scenarios (a clean immediate grant,
# a queued-then-granted sequence, and one stale-ticket reclaim) plus two
# covering the implement-kind stale-reclaim fix (research.md D6): an
# implement-kind head ticket's own run_id is the DISPATCHING run that
# enqueued it, not the real implement.yml run holding the ticket, so
# staleness must be checked against the round's correlated
# implement_run_id -- not reclaimed while that real run is still
# in_progress, reclaimed once it has completed.
#
# Invoked directly by a `run:` step in lint-workflows.yml (Gate 126
# fixtures), so CI runs this suite on every PR. run-local-gates.py mirrors
# CI by deriving its gate list from wc_gate_registry.gate_scripts(), which
# only recognizes .github/scripts/verify-*.{py,sh} and
# .github/scripts/*/run-tests.sh; a path under .github/actions/**/tests/
# does not match that convention, so this suite runs in CI but is not yet
# reproduced by the local sweep -- size-path-backstop-tests is in fact a
# poor precedent for that gap, since .github/scripts/size-path-backstop-tests/run-tests.sh
# matches the convention and IS a registered gate. Invoke directly for a
# quick local check: bash .github/actions/wing-commander-fold-queue-admit/tests/run.sh
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

# --- Scenarios 4/5 setup: an implement-kind head ticket whose own run_id
# is the DISPATCHING run (claim-dispatch stamps it that way), never the
# actual implement.yml run holding the ticket. Build a realistic round so
# record-implement-run has something to correlate.
enqueue_out="$(LEDGER_REMOTE_URL="$REMOTE" GH_TOKEN=x GITHUB_REPOSITORY=x/x SPEC_DIR="$SPEC_DIR" \
  KIND=act RUN_ID=900 bash "$LEDGER_SH" enqueue)"
round="$(printf '%s\n' "$enqueue_out" | grep '^round=' | cut -d= -f2-)"

LEDGER_REMOTE_URL="$REMOTE" GH_TOKEN=x GITHUB_REPOSITORY=x/x SPEC_DIR="$SPEC_DIR" \
  TOKEN="run-900-act" RUN_ID=900 OUTCOME=folded COMMIT_SHA=def456 LEG_ID=leg-1 SUMMARY=s \
  bash "$LEDGER_SH" release >/dev/null

LEDGER_REMOTE_URL="$REMOTE" GH_TOKEN=x GITHUB_REPOSITORY=x/x SPEC_DIR="$SPEC_DIR" \
  KIND=dispatch RUN_ID=900 bash "$LEDGER_SH" enqueue >/dev/null

LEDGER_REMOTE_URL="$REMOTE" GH_TOKEN=x GITHUB_REPOSITORY=x/x SPEC_DIR="$SPEC_DIR" \
  ROUND="$round" DISPATCH_TOKEN="run-900-dispatch" ITERATION=5 \
  bash "$LEDGER_SH" claim-dispatch >/dev/null

LEDGER_REMOTE_URL="$REMOTE" GH_TOKEN=x GITHUB_REPOSITORY=x/x SPEC_DIR="$SPEC_DIR" \
  TOKEN="run-900-dispatch" RUN_ID=900 OUTCOME=folded \
  bash "$LEDGER_SH" release >/dev/null

# claim-dispatch enqueued "run-900-implement" (run_id=900, the DISPATCHING
# run) behind the dispatch ticket; releasing the dispatch ticket makes it
# head. Correlate it to the REAL implement.yml run (901) the way
# dispatch-once does once it observes the dispatched run.
LEDGER_REMOTE_URL="$REMOTE" GH_TOKEN=x GITHUB_REPOSITORY=x/x SPEC_DIR="$SPEC_DIR" \
  ROUND="$round" IMPLEMENT_RUN_ID=901 bash "$LEDGER_SH" record-implement-run >/dev/null

# --- Scenario 4: implement-kind head ticket NOT reclaimed while its
# correlated real run (901) is still in_progress, even though the ticket's
# own run_id (900, the long-finished dispatching run) would report
# "completed" if the fix wrongly checked that field instead.
out_file4="$(mktemp)"
summary_file4="$(mktemp)"
(
  PATH="$STUBDIR:$PATH" \
    GITHUB_ACTION_PATH="$COMPOSITE_DIR" \
    GH_TOKEN=x GITHUB_REPOSITORY=x/x \
    LEDGER_REMOTE_URL="$REMOTE" \
    SPEC_DIR="$SPEC_DIR" KIND=act RUN_ID=105 EXISTING_TOKEN="" \
    MAX_WAIT_MINUTES=1 POLL_INTERVAL_SECONDS=1 STALE_AFTER_MINUTES=0 \
    GH_STUB_STATUS=in_progress \
    GITHUB_OUTPUT="$out_file4" GITHUB_STEP_SUMMARY="$summary_file4" \
    bash "$SCRIPT"
) &
waiter_pid=$!
sleep 3
if kill -0 "$waiter_pid" 2>/dev/null; then
  kill "$waiter_pid" 2>/dev/null
  wait "$waiter_pid" 2>/dev/null
  still_position="$(LEDGER_REMOTE_URL="$REMOTE" GH_TOKEN=x GITHUB_REPOSITORY=x/x SPEC_DIR="$SPEC_DIR" PEEK_TOKEN="run-900-implement" bash "$LEDGER_SH" peek | grep '^position=' | cut -d= -f2-)"
  if [ "$still_position" = "0" ]; then
    echo "[ok] implement-kind ticket not reclaimed while its correlated run is in_progress"
  else
    echo "::error::[implement liveness] expected run-900-implement still at head, position=$still_position"
    FAILURES=$((FAILURES + 1))
  fi
else
  echo "::error::[implement liveness] waiter exited early (should have blocked behind an in_progress implement run)"
  FAILURES=$((FAILURES + 1))
fi
rm -f "$out_file4" "$summary_file4"

# --- Scenario 5: the same implement-kind head ticket IS reclaimed once its
# correlated real run (901) is completed/absent.
out_file5="$(mktemp)"
summary_file5="$(mktemp)"
PATH="$STUBDIR:$PATH" \
  GITHUB_ACTION_PATH="$COMPOSITE_DIR" \
  GH_TOKEN=x GITHUB_REPOSITORY=x/x \
  LEDGER_REMOTE_URL="$REMOTE" \
  SPEC_DIR="$SPEC_DIR" KIND=act RUN_ID=106 EXISTING_TOKEN="" \
  MAX_WAIT_MINUTES=1 POLL_INTERVAL_SECONDS=1 STALE_AFTER_MINUTES=0 \
  GH_STUB_STATUS=completed \
  GITHUB_OUTPUT="$out_file5" GITHUB_STEP_SUMMARY="$summary_file5" \
  bash "$SCRIPT"
rc=$?
token5="$(grep '^token=' "$out_file5" | cut -d= -f2-)"
granted5="$(grep '^granted=' "$out_file5" | cut -d= -f2-)"
if [ "$rc" -eq 0 ] && [ "$token5" = "run-106-act" ] && [ "$granted5" = "true" ]; then
  echo "[ok] implement-kind ticket reclaimed once its correlated run has completed: token=$token5 granted=$granted5"
else
  echo "::error::[implement liveness reclaim] rc=$rc token=${token5:-<empty>} granted=${granted5:-<empty>}"
  FAILURES=$((FAILURES + 1))
fi
rm -f "$out_file5" "$summary_file5"

echo "wing-commander-fold-queue-admit tests: $FAILURES failure(s)."
[ "$FAILURES" -eq 0 ]
