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
# in_progress, reclaimed once it has completed. Scenarios 6/7 (T060,
# maintainer review of #821, B8) cover fold-queue-await.sh's separate
# admission-DEADLINE extension (not the stale-reclaim check above): it
# extends for an implement-kind head reporting "waiting" (not just
# "in_progress"/"queued"), and now also for a long-held ACT-kind head
# (a leg bound by confirm-timeout-minutes, not an implement cycle's
# runtime) -- previously the extension applied only to head-kind
# "implement" and only two literal statuses. Scenarios 8/9 cover the
# SEPARATE, pre-existing (T046) uncorrelated-implement-head uncorrelated-
# grace-period reclaim, which had no fixture of its own before T060.
#
# T052 (maintainer review of #821, #719/#825): this suite used to live at
# .github/actions/wing-commander-fold-queue-admit/tests/run.sh, a location
# Gate 119 (verify-actions-no-gate-scripts.py) forbids for exactly this
# reason -- wc_gate_registry.gate_scripts() only discovers
# .github/scripts/verify-*.{py,sh} and .github/scripts/*/run-tests.sh, so a
# harness under .github/actions/**/ is invisible to
# `python .github/scripts/run-local-gates.py`, the suite CLAUDE.md's
# "Before pushing" section tells every contributor to trust. Moved here
# (and renamed run.sh -> run-tests.sh, the exact entrypoint name the
# registry globs for) so both the local sweep and CI run it -- registered
# in lint-workflows.yml (Gate 128 fixtures) exactly as
# size-path-backstop-tests/run-tests.sh already is, no longer a "poor
# precedent" as this file once said. Invoke directly for a quick local
# check: bash .github/scripts/wing-commander-fold-queue-admit-tests/run-tests.sh
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSITE_DIR="$HERE/../../actions/wing-commander-fold-queue-admit"
ACTION_YML="$COMPOSITE_DIR/action.yml"
LEDGER_SH="$HERE/../../actions/_shared/fold-queue-ledger.sh"
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

# This scenario only exercises the grant path, but the ticket it was
# granted is real and stays queued (head, forever) until released -- every
# later scenario shares this same spec-dir/remote, so leaving it held would
# wedge every subsequent admit behind it.
LEDGER_REMOTE_URL="$REMOTE" GH_TOKEN=x GITHUB_REPOSITORY=x/x SPEC_DIR="$SPEC_DIR" \
  TOKEN="run-100-act" RUN_ID=100 OUTCOME="not-folded" LEG_ID="leg-1" \
  bash "$LEDGER_SH" release >/dev/null

# --- Scenario 2: queued-then-granted ----------------------------------------
LEDGER_REMOTE_URL="$REMOTE" GH_TOKEN=x GITHUB_REPOSITORY=x/x SPEC_DIR="$SPEC_DIR" \
  KIND=act RUN_ID=101 bash "$LEDGER_SH" enqueue >/dev/null

(
  sleep 2
  LEDGER_REMOTE_URL="$REMOTE" GH_TOKEN=x GITHUB_REPOSITORY=x/x SPEC_DIR="$SPEC_DIR" \
    TOKEN="run-101-act" RUN_ID=101 OUTCOME="folded" COMMIT_SHA="abc123" LEG_ID="leg-1" SUMMARY="s" \
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

# Same as scenario 1 -- release the ticket this scenario was actually
# granted, or scenario 3's stale-reclaim would target it instead of
# run-103-act.
LEDGER_REMOTE_URL="$REMOTE" GH_TOKEN=x GITHUB_REPOSITORY=x/x SPEC_DIR="$SPEC_DIR" \
  TOKEN="run-102-act" RUN_ID=102 OUTCOME="not-folded" LEG_ID="leg-1" \
  bash "$LEDGER_SH" release >/dev/null

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

# Same as scenario 1 -- this ticket was really granted and stays queued
# until released, or every later scenario sharing this spec-dir/remote
# wedges behind it.
LEDGER_REMOTE_URL="$REMOTE" GH_TOKEN=x GITHUB_REPOSITORY=x/x SPEC_DIR="$SPEC_DIR" \
  TOKEN="run-104-act" RUN_ID=104 OUTCOME="not-folded" LEG_ID="leg-1" \
  bash "$LEDGER_SH" release >/dev/null

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
  ROUND="$round" DISPATCH_TOKEN="run-900-dispatch" ITERATION=5 OWN_FOLDS=1 \
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

# Scenario 5 was really granted (run-106-act) and stays queued until
# released, or scenarios 6/7 below would wedge behind it.
LEDGER_REMOTE_URL="$REMOTE" GH_TOKEN=x GITHUB_REPOSITORY=x/x SPEC_DIR="$SPEC_DIR" \
  TOKEN="run-106-act" RUN_ID=106 OUTCOME="not-folded" LEG_ID="leg-1" \
  bash "$LEDGER_SH" release >/dev/null

# --- Scenario 6/7 setup: another realistic round, correlated to a THIRD
# real run (902) -- distinct from 901 (already completed/reclaimed above)
# so this round's own deadline-extension check cannot pass by accident.
enqueue_out2="$(LEDGER_REMOTE_URL="$REMOTE" GH_TOKEN=x GITHUB_REPOSITORY=x/x SPEC_DIR="$SPEC_DIR" \
  KIND=act RUN_ID=910 bash "$LEDGER_SH" enqueue)"
round2="$(printf '%s\n' "$enqueue_out2" | grep '^round=' | cut -d= -f2-)"

LEDGER_REMOTE_URL="$REMOTE" GH_TOKEN=x GITHUB_REPOSITORY=x/x SPEC_DIR="$SPEC_DIR" \
  TOKEN="run-910-act" RUN_ID=910 OUTCOME=folded COMMIT_SHA=ghi789 LEG_ID=leg-1 SUMMARY=s \
  bash "$LEDGER_SH" release >/dev/null

LEDGER_REMOTE_URL="$REMOTE" GH_TOKEN=x GITHUB_REPOSITORY=x/x SPEC_DIR="$SPEC_DIR" \
  KIND=dispatch RUN_ID=910 bash "$LEDGER_SH" enqueue >/dev/null

LEDGER_REMOTE_URL="$REMOTE" GH_TOKEN=x GITHUB_REPOSITORY=x/x SPEC_DIR="$SPEC_DIR" \
  ROUND="$round2" DISPATCH_TOKEN="run-910-dispatch" ITERATION=6 OWN_FOLDS=1 \
  bash "$LEDGER_SH" claim-dispatch >/dev/null

LEDGER_REMOTE_URL="$REMOTE" GH_TOKEN=x GITHUB_REPOSITORY=x/x SPEC_DIR="$SPEC_DIR" \
  TOKEN="run-910-dispatch" RUN_ID=910 OUTCOME=folded \
  bash "$LEDGER_SH" release >/dev/null

LEDGER_REMOTE_URL="$REMOTE" GH_TOKEN=x GITHUB_REPOSITORY=x/x SPEC_DIR="$SPEC_DIR" \
  ROUND="$round2" IMPLEMENT_RUN_ID=902 bash "$LEDGER_SH" record-implement-run >/dev/null

# --- Scenario 6 (T060/B8): the admission DEADLINE (not the stale-reclaim
# check) extends for an implement-kind head whose correlated run (902)
# reports "waiting" (an environment-approval pause), not just
# "in_progress"/"queued" -- MAX_WAIT_MINUTES=0 makes the deadline check
# fire on the very first poll.
out_file6="$(mktemp)"
summary_file6="$(mktemp)"
(
  PATH="$STUBDIR:$PATH" \
    GITHUB_ACTION_PATH="$COMPOSITE_DIR" \
    GH_TOKEN=x GITHUB_REPOSITORY=x/x \
    LEDGER_REMOTE_URL="$REMOTE" \
    SPEC_DIR="$SPEC_DIR" KIND=act RUN_ID=111 EXISTING_TOKEN="" \
    MAX_WAIT_MINUTES=0 POLL_INTERVAL_SECONDS=1 STALE_AFTER_MINUTES=60 \
    GH_STUB_STATUS=waiting \
    GITHUB_OUTPUT="$out_file6" GITHUB_STEP_SUMMARY="$summary_file6" \
    bash "$SCRIPT"
) &
waiter_pid6=$!
sleep 3
if kill -0 "$waiter_pid6" 2>/dev/null; then
  kill "$waiter_pid6" 2>/dev/null
  wait "$waiter_pid6" 2>/dev/null
  echo "[ok] admission deadline extends for an implement-kind head reporting 'waiting', not just in_progress/queued"
else
  echo "::error::[deadline extension, 'waiting' status] waiter exited early (should have extended past MAX_WAIT_MINUTES=0 while the correlated run reports 'waiting')"
  FAILURES=$((FAILURES + 1))
fi
rm -f "$out_file6" "$summary_file6"

# Scenario 6's killed waiter already pushed its own real "run-111-act"
# ticket to the ledger (enqueue commits before the poll loop even starts),
# queued directly behind "run-910-implement" -- release both, in queue
# order, so scenario 7 below starts from an empty queue.
LEDGER_REMOTE_URL="$REMOTE" GH_TOKEN=x GITHUB_REPOSITORY=x/x SPEC_DIR="$SPEC_DIR" \
  TOKEN="run-910-implement" RUN_ID=910 OUTCOME=folded \
  bash "$LEDGER_SH" release >/dev/null
LEDGER_REMOTE_URL="$REMOTE" GH_TOKEN=x GITHUB_REPOSITORY=x/x SPEC_DIR="$SPEC_DIR" \
  TOKEN="run-111-act" RUN_ID=111 OUTCOME="not-folded" LEG_ID="leg-1" \
  bash "$LEDGER_SH" release >/dev/null

# --- Scenario 7 (T060/B8): the admission deadline also extends for a
# long-held ACT-kind head (a leg bound only by confirm-timeout-minutes,
# default 1440 = 24h, not by an implement cycle's runtime) -- previously
# this extension applied only to head-kind "implement".
LEDGER_REMOTE_URL="$REMOTE" GH_TOKEN=x GITHUB_REPOSITORY=x/x SPEC_DIR="$SPEC_DIR" \
  KIND=act RUN_ID=920 bash "$LEDGER_SH" enqueue >/dev/null

out_file7="$(mktemp)"
summary_file7="$(mktemp)"
(
  PATH="$STUBDIR:$PATH" \
    GITHUB_ACTION_PATH="$COMPOSITE_DIR" \
    GH_TOKEN=x GITHUB_REPOSITORY=x/x \
    LEDGER_REMOTE_URL="$REMOTE" \
    SPEC_DIR="$SPEC_DIR" KIND=act RUN_ID=112 EXISTING_TOKEN="" \
    MAX_WAIT_MINUTES=0 POLL_INTERVAL_SECONDS=1 STALE_AFTER_MINUTES=60 \
    GH_STUB_STATUS=in_progress \
    GITHUB_OUTPUT="$out_file7" GITHUB_STEP_SUMMARY="$summary_file7" \
    bash "$SCRIPT"
) &
waiter_pid7=$!
sleep 3
if kill -0 "$waiter_pid7" 2>/dev/null; then
  kill "$waiter_pid7" 2>/dev/null
  wait "$waiter_pid7" 2>/dev/null
  echo "[ok] admission deadline extends for a long-held act-kind head whose own run is still in_progress"
else
  echo "::error::[deadline extension, act-kind] waiter exited early (should have extended past MAX_WAIT_MINUTES=0 behind a confirm-held act-kind head)"
  FAILURES=$((FAILURES + 1))
fi
rm -f "$out_file7" "$summary_file7"

# Same leaked-ticket cleanup as scenario 6's, in queue order: run-920-act
# (head), then scenario 7's own killed waiter's real "run-112-act" ticket.
LEDGER_REMOTE_URL="$REMOTE" GH_TOKEN=x GITHUB_REPOSITORY=x/x SPEC_DIR="$SPEC_DIR" \
  TOKEN="run-920-act" RUN_ID=920 OUTCOME="not-folded" LEG_ID="leg-1" \
  bash "$LEDGER_SH" release >/dev/null
LEDGER_REMOTE_URL="$REMOTE" GH_TOKEN=x GITHUB_REPOSITORY=x/x SPEC_DIR="$SPEC_DIR" \
  TOKEN="run-112-act" RUN_ID=112 OUTCOME="not-folded" LEG_ID="leg-1" \
  bash "$LEDGER_SH" release >/dev/null

# --- Scenario 8/9 setup (T060/B8, "uncorrelated reclaim" fixtures): a
# third round whose implement-kind head ticket NEVER gets
# record-implement-run called -- T046's own backstop for exactly this gap.
enqueue_out4="$(LEDGER_REMOTE_URL="$REMOTE" GH_TOKEN=x GITHUB_REPOSITORY=x/x SPEC_DIR="$SPEC_DIR" \
  KIND=act RUN_ID=930 bash "$LEDGER_SH" enqueue)"
round3="$(printf '%s\n' "$enqueue_out4" | grep '^round=' | cut -d= -f2-)"

LEDGER_REMOTE_URL="$REMOTE" GH_TOKEN=x GITHUB_REPOSITORY=x/x SPEC_DIR="$SPEC_DIR" \
  TOKEN="run-930-act" RUN_ID=930 OUTCOME=folded COMMIT_SHA=jkl012 LEG_ID=leg-1 SUMMARY=s \
  bash "$LEDGER_SH" release >/dev/null

LEDGER_REMOTE_URL="$REMOTE" GH_TOKEN=x GITHUB_REPOSITORY=x/x SPEC_DIR="$SPEC_DIR" \
  KIND=dispatch RUN_ID=930 bash "$LEDGER_SH" enqueue >/dev/null

LEDGER_REMOTE_URL="$REMOTE" GH_TOKEN=x GITHUB_REPOSITORY=x/x SPEC_DIR="$SPEC_DIR" \
  ROUND="$round3" DISPATCH_TOKEN="run-930-dispatch" ITERATION=7 OWN_FOLDS=1 \
  bash "$LEDGER_SH" claim-dispatch >/dev/null

# Releasing the dispatch ticket promotes "run-930-implement" to head,
# granted -- deliberately never correlated via record-implement-run.
LEDGER_REMOTE_URL="$REMOTE" GH_TOKEN=x GITHUB_REPOSITORY=x/x SPEC_DIR="$SPEC_DIR" \
  TOKEN="run-930-dispatch" RUN_ID=930 OUTCOME=folded \
  bash "$LEDGER_SH" release >/dev/null

# --- Scenario 8 (T060/B8): an uncorrelated implement-kind head is NOT
# reclaimed before stale-after-minutes PLUS the uncorrelated grace period
# has elapsed, even though it has no correlated run to check liveness
# against at all.
out_file8="$(mktemp)"
summary_file8="$(mktemp)"
(
  PATH="$STUBDIR:$PATH" \
    GITHUB_ACTION_PATH="$COMPOSITE_DIR" \
    GH_TOKEN=x GITHUB_REPOSITORY=x/x \
    LEDGER_REMOTE_URL="$REMOTE" \
    SPEC_DIR="$SPEC_DIR" KIND=act RUN_ID=113 EXISTING_TOKEN="" \
    MAX_WAIT_MINUTES=5 POLL_INTERVAL_SECONDS=1 STALE_AFTER_MINUTES=0 \
    UNCORRELATED_IMPLEMENT_GRACE_MINUTES=60 \
    GH_STUB_STATUS=completed \
    GITHUB_OUTPUT="$out_file8" GITHUB_STEP_SUMMARY="$summary_file8" \
    bash "$SCRIPT"
) &
waiter_pid8=$!
sleep 3
if kill -0 "$waiter_pid8" 2>/dev/null; then
  kill "$waiter_pid8" 2>/dev/null
  wait "$waiter_pid8" 2>/dev/null
  still_position8="$(LEDGER_REMOTE_URL="$REMOTE" GH_TOKEN=x GITHUB_REPOSITORY=x/x SPEC_DIR="$SPEC_DIR" PEEK_TOKEN="run-930-implement" bash "$LEDGER_SH" peek | grep '^position=' | cut -d= -f2-)"
  if [ "$still_position8" = "0" ]; then
    echo "[ok] uncorrelated implement-kind head NOT reclaimed before stale-after-minutes + the grace period elapses"
  else
    echo "::error::[uncorrelated reclaim, within grace] expected run-930-implement still at head, position=$still_position8"
    FAILURES=$((FAILURES + 1))
  fi
else
  echo "::error::[uncorrelated reclaim, within grace] waiter exited early (should still be blocked within the grace period)"
  FAILURES=$((FAILURES + 1))
fi
rm -f "$out_file8" "$summary_file8"
# NOT released here: "run-113-act" (scenario 8's own killed waiter's real,
# already-enqueued ticket) sits behind "run-930-implement" at position 1,
# not the queue head, so a release call on it would itself error "not at
# queue head". Scenario 9 below reclaims "run-930-implement" (clearing it)
# and then, in the SAME invocation's next poll, reclaims "run-113-act" too
# (GH_STUB_STATUS=completed is blanket for every run id in that call) on
# its way to granting its own ticket -- no separate cleanup step needed.

# --- Scenario 9 (T060/B8): the SAME uncorrelated implement-kind head IS
# reclaimed unconditionally once stale-after-minutes + the grace period
# has elapsed (here, a zero grace period makes it immediate) -- T046's own
# backstop for whatever gap record-implement-run's own callers don't cover.
out_file9="$(mktemp)"
summary_file9="$(mktemp)"
PATH="$STUBDIR:$PATH" \
  GITHUB_ACTION_PATH="$COMPOSITE_DIR" \
  GH_TOKEN=x GITHUB_REPOSITORY=x/x \
  LEDGER_REMOTE_URL="$REMOTE" \
  SPEC_DIR="$SPEC_DIR" KIND=act RUN_ID=114 EXISTING_TOKEN="" \
  MAX_WAIT_MINUTES=5 POLL_INTERVAL_SECONDS=1 STALE_AFTER_MINUTES=0 \
  UNCORRELATED_IMPLEMENT_GRACE_MINUTES=0 \
  GH_STUB_STATUS=completed \
  GITHUB_OUTPUT="$out_file9" GITHUB_STEP_SUMMARY="$summary_file9" \
  bash "$SCRIPT"
rc9=$?
token9="$(grep '^token=' "$out_file9" | cut -d= -f2-)"
granted9="$(grep '^granted=' "$out_file9" | cut -d= -f2-)"
if [ "$rc9" -eq 0 ] && [ "$token9" = "run-114-act" ] && [ "$granted9" = "true" ]; then
  echo "[ok] uncorrelated implement-kind head reclaimed unconditionally once stale-after-minutes + the (zero) grace period elapses"
else
  echo "::error::[uncorrelated reclaim, grace elapsed] rc=$rc9 token=${token9:-<empty>} granted=${granted9:-<empty>}"
  FAILURES=$((FAILURES + 1))
fi
rm -f "$out_file9" "$summary_file9"

echo "wing-commander-fold-queue-admit tests: $FAILURES failure(s)."
[ "$FAILURES" -eq 0 ]
