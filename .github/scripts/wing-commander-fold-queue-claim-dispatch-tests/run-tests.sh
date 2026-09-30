#!/usr/bin/env bash
# Fixtures for wing-commander-fold-queue-claim-dispatch/action.yml's own
# "Attempt the round's dispatch claim" step, extracted and run against a
# throwaway LOCAL bare git repository (LEDGER_REMOTE_URL override -- no
# live network), matching this directory's sibling fixture suites.
#
# Covers quickstart.md Drill 2 plus the maintainer's 2026-09-29
# reconciliation with spec 075 (spec.md Clarifications): a run with no
# folds of its own declines unconditionally; a run with folds of its own
# that finds another act-kind ticket still queued requeues and re-awaits
# internally rather than stepping aside, then wins once that ticket
# clears; a run with folds of its own wins immediately against an already-
# empty, unclaimed round; a run with folds of its own still declines when
# another run already won the round.
#
# T052 (maintainer review of #821, #719/#825): moved here (and renamed
# run.sh -> run-tests.sh) from
# .github/actions/wing-commander-fold-queue-claim-dispatch/tests/run.sh, a
# location Gate 119 (verify-actions-no-gate-scripts.py) forbids -- see
# wing-commander-fold-queue-admit-tests/run-tests.sh's header for why.
# Registered in lint-workflows.yml (Gate 128 fixtures), so both CI and
# `python .github/scripts/run-local-gates.py` now run it. Invoke directly
# for a quick local check:
# bash .github/scripts/wing-commander-fold-queue-claim-dispatch-tests/run-tests.sh
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSITE_DIR="$HERE/../../actions/wing-commander-fold-queue-claim-dispatch"
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
    if step.get("id") == "claim":
        sys.stdout.write(step["run"])
        break
else:
    sys.exit("no step with id: claim found in " + sys.argv[1])
PYEOF
}

SCRIPT="$(mktemp)"
extract_step > "$SCRIPT"

WORK="$(mktemp -d)"
REMOTE="$WORK/fold-queue-remote.git"
git init --quiet --bare "$REMOTE"

trap 'rm -f "$SCRIPT"; rm -rf "$WORK"' EXIT

SPEC_DIR_FIXTURE="specs/074-serialized-fold-dispatch"
mkdir -p "$WORK/$SPEC_DIR_FIXTURE"
echo '{"iteration": 2}' > "$WORK/$SPEC_DIR_FIXTURE/spec-meta.json"

run_claim() {
  local token="$1" round="$2" own_folds="$3" max_wait="${4:-30}" poll="${5:-10}" stale_after="${6:-10}"
  local out_file summary_file
  out_file="$(mktemp)"
  summary_file="$(mktemp)"
  (
    cd "$WORK" || exit 1
    GITHUB_ACTION_PATH="$COMPOSITE_DIR" \
      GH_TOKEN=x GITHUB_REPOSITORY=x/x \
      LEDGER_REMOTE_URL="$REMOTE" \
      SPEC_DIR="$SPEC_DIR_FIXTURE" ROUND="$round" DISPATCH_TOKEN="$token" OWN_FOLDS="$own_folds" \
      MAX_WAIT_MINUTES="$max_wait" POLL_INTERVAL_SECONDS="$poll" STALE_AFTER_MINUTES="$stale_after" \
      GITHUB_OUTPUT="$out_file" GITHUB_STEP_SUMMARY="$summary_file" \
      bash "$SCRIPT"
  )
  local rc=$?
  echo "$out_file"
  return $rc
}

# --- Scenario 1: declined -- no folds of its own, even against an empty,
# unclaimed round (spec 075 FR-014, reconciled 2026-09-29) ------------------
LEDGER_REMOTE_URL="$REMOTE" GH_TOKEN=x GITHUB_REPOSITORY=x/x SPEC_DIR="$SPEC_DIR_FIXTURE" \
  KIND=act RUN_ID=200 bash "$LEDGER_SH" enqueue >/dev/null
LEDGER_REMOTE_URL="$REMOTE" GH_TOKEN=x GITHUB_REPOSITORY=x/x SPEC_DIR="$SPEC_DIR_FIXTURE" \
  TOKEN="run-200-act" RUN_ID=200 OUTCOME="not-folded" LEG_ID="leg-1" \
  bash "$LEDGER_SH" release >/dev/null
LEDGER_REMOTE_URL="$REMOTE" GH_TOKEN=x GITHUB_REPOSITORY=x/x SPEC_DIR="$SPEC_DIR_FIXTURE" \
  KIND=dispatch RUN_ID=200 bash "$LEDGER_SH" enqueue >/dev/null

out_file="$(run_claim "run-200-dispatch" 1 0)"
should_dispatch="$(grep '^should-dispatch=' "$out_file" | cut -d= -f2-)"
outcome="$(grep '^outcome=' "$out_file" | cut -d= -f2-)"
if [ "$should_dispatch" = "false" ] && [ "$outcome" = "declined" ]; then
  echo "[ok] declined (no own folds): should-dispatch=false outcome=$outcome"
else
  echo "::error::[declined, no own folds] expected should-dispatch=false outcome=declined, got should-dispatch=${should_dispatch:-<empty>} outcome=${outcome:-<empty>}"
  FAILURES=$((FAILURES + 1))
fi
LEDGER_REMOTE_URL="$REMOTE" GH_TOKEN=x GITHUB_REPOSITORY=x/x SPEC_DIR="$SPEC_DIR_FIXTURE" \
  TOKEN="run-200-dispatch" RUN_ID=200 OUTCOME="not-folded" \
  bash "$LEDGER_SH" release >/dev/null
rm -f "$out_file"

# --- Scenario 2: requeued then won -- own folds exist, but another run's
# act-kind ticket is still outstanding when this run first attempts the
# claim; the ticket requeues and re-awaits internally, then wins once that
# act ticket releases -- with the round's folded-items naming BOTH runs. ---
enqueue_out_301="$(LEDGER_REMOTE_URL="$REMOTE" GH_TOKEN=x GITHUB_REPOSITORY=x/x SPEC_DIR="$SPEC_DIR_FIXTURE" \
  KIND=act RUN_ID=301 bash "$LEDGER_SH" enqueue)"
round2="$(printf '%s\n' "$enqueue_out_301" | grep '^round=' | cut -d= -f2-)"
LEDGER_REMOTE_URL="$REMOTE" GH_TOKEN=x GITHUB_REPOSITORY=x/x SPEC_DIR="$SPEC_DIR_FIXTURE" \
  TOKEN="run-301-act" RUN_ID=301 OUTCOME="folded" COMMIT_SHA="feed" LEG_ID="leg-1" SUMMARY="s" \
  bash "$LEDGER_SH" release >/dev/null
LEDGER_REMOTE_URL="$REMOTE" GH_TOKEN=x GITHUB_REPOSITORY=x/x SPEC_DIR="$SPEC_DIR_FIXTURE" \
  KIND=dispatch RUN_ID=301 bash "$LEDGER_SH" enqueue >/dev/null
LEDGER_REMOTE_URL="$REMOTE" GH_TOKEN=x GITHUB_REPOSITORY=x/x SPEC_DIR="$SPEC_DIR_FIXTURE" \
  KIND=act RUN_ID=302 bash "$LEDGER_SH" enqueue >/dev/null

(
  sleep 2
  LEDGER_REMOTE_URL="$REMOTE" GH_TOKEN=x GITHUB_REPOSITORY=x/x SPEC_DIR="$SPEC_DIR_FIXTURE" \
    TOKEN="run-302-act" RUN_ID=302 OUTCOME="folded" COMMIT_SHA="cafe" LEG_ID="leg-1" SUMMARY="s" \
    bash "$LEDGER_SH" release >/dev/null
) &
releaser_pid=$!

out_file="$(run_claim "run-301-dispatch" "$round2" 1 1 1 1)"
rc=$?
wait "$releaser_pid"
should_dispatch="$(grep '^should-dispatch=' "$out_file" | cut -d= -f2-)"
outcome="$(grep '^outcome=' "$out_file" | cut -d= -f2-)"
folded_items="$(grep '^folded-items=' "$out_file" | cut -d= -f2-)"
run_ids_in_folded="$(printf '%s' "$folded_items" | jq -r '[.[].run_id] | sort | join(",")' 2>/dev/null || echo "<parse-error>")"
if [ "$rc" -eq 0 ] && [ "$should_dispatch" = "true" ] && [ "$outcome" = "won" ] && [ "$run_ids_in_folded" = "301,302" ]; then
  echo "[ok] requeued then won: should-dispatch=true outcome=$outcome folded-items run_ids=$run_ids_in_folded"
else
  echo "::error::[requeued then won] rc=$rc should-dispatch=${should_dispatch:-<empty>} outcome=${outcome:-<empty>} folded-items run_ids=${run_ids_in_folded:-<empty>} (raw: ${folded_items:-<empty>})"
  FAILURES=$((FAILURES + 1))
fi
rm -f "$out_file"

# Drain the queue fully (release both the winning dispatch ticket and the
# implement ticket it enqueued) so scenario 3's act ticket opens a FRESH
# round rather than joining round2 (already claimed).
LEDGER_REMOTE_URL="$REMOTE" GH_TOKEN=x GITHUB_REPOSITORY=x/x SPEC_DIR="$SPEC_DIR_FIXTURE" \
  TOKEN="run-301-dispatch" RUN_ID=301 OUTCOME="folded" \
  bash "$LEDGER_SH" release >/dev/null
LEDGER_REMOTE_URL="$REMOTE" GH_TOKEN=x GITHUB_REPOSITORY=x/x SPEC_DIR="$SPEC_DIR_FIXTURE" \
  TOKEN="run-301-implement" RUN_ID=301 OUTCOME="folded" \
  bash "$LEDGER_SH" release >/dev/null

# --- Scenario 3: won immediately -- own folds exist and the round is
# already empty and unclaimed. -----------------------------------------
LEDGER_REMOTE_URL="$REMOTE" GH_TOKEN=x GITHUB_REPOSITORY=x/x SPEC_DIR="$SPEC_DIR_FIXTURE" \
  KIND=act RUN_ID=400 bash "$LEDGER_SH" enqueue >/dev/null
LEDGER_REMOTE_URL="$REMOTE" GH_TOKEN=x GITHUB_REPOSITORY=x/x SPEC_DIR="$SPEC_DIR_FIXTURE" \
  TOKEN="run-400-act" RUN_ID=400 OUTCOME="folded" COMMIT_SHA="baad" LEG_ID="leg-1" SUMMARY="s" \
  bash "$LEDGER_SH" release >/dev/null
LEDGER_REMOTE_URL="$REMOTE" GH_TOKEN=x GITHUB_REPOSITORY=x/x SPEC_DIR="$SPEC_DIR_FIXTURE" \
  KIND=dispatch RUN_ID=400 bash "$LEDGER_SH" enqueue >/dev/null

round_of_400="$(LEDGER_REMOTE_URL="$REMOTE" GH_TOKEN=x GITHUB_REPOSITORY=x/x SPEC_DIR="$SPEC_DIR_FIXTURE" PEEK_TOKEN="run-400-dispatch" bash "$LEDGER_SH" peek | grep '^round=' | cut -d= -f2-)"

out_file="$(run_claim "run-400-dispatch" "$round_of_400" 1)"
should_dispatch="$(grep '^should-dispatch=' "$out_file" | cut -d= -f2-)"
outcome="$(grep '^outcome=' "$out_file" | cut -d= -f2-)"
implement_token="$(grep '^implement-token=' "$out_file" | cut -d= -f2-)"
iteration="$(grep '^iteration=' "$out_file" | cut -d= -f2-)"
if [ "$should_dispatch" = "true" ] && [ "$outcome" = "won" ] && [ "$implement_token" = "run-400-implement" ] && [ "$iteration" = "3" ]; then
  echo "[ok] won immediately: should-dispatch=true outcome=$outcome implement-token=$implement_token iteration=$iteration"
else
  echo "::error::[won immediately] should-dispatch=${should_dispatch:-<empty>} outcome=${outcome:-<empty>} implement-token=${implement_token:-<empty>} iteration=${iteration:-<empty>}"
  FAILURES=$((FAILURES + 1))
fi
rm -f "$out_file"

# --- Scenario 4: declined -- own folds exist, but another run already won
# this exact round. Dequeue run-400's dispatch and implement tickets (LEG_ID
# empty on both, so neither files a completion record) so a second
# dispatch-kind ticket for the SAME round can reach the queue head and
# actually attempt (rather than error on) the claim. ------------------------
LEDGER_REMOTE_URL="$REMOTE" GH_TOKEN=x GITHUB_REPOSITORY=x/x SPEC_DIR="$SPEC_DIR_FIXTURE" \
  TOKEN="run-400-dispatch" RUN_ID=400 OUTCOME="folded" \
  bash "$LEDGER_SH" release >/dev/null
LEDGER_REMOTE_URL="$REMOTE" GH_TOKEN=x GITHUB_REPOSITORY=x/x SPEC_DIR="$SPEC_DIR_FIXTURE" \
  KIND=dispatch RUN_ID=401 bash "$LEDGER_SH" enqueue >/dev/null
LEDGER_REMOTE_URL="$REMOTE" GH_TOKEN=x GITHUB_REPOSITORY=x/x SPEC_DIR="$SPEC_DIR_FIXTURE" \
  TOKEN="run-400-implement" RUN_ID=400 OUTCOME="folded" \
  bash "$LEDGER_SH" release >/dev/null

out_file="$(run_claim "run-401-dispatch" "$round_of_400" 1)"
should_dispatch="$(grep '^should-dispatch=' "$out_file" | cut -d= -f2-)"
outcome="$(grep '^outcome=' "$out_file" | cut -d= -f2-)"
if [ "$should_dispatch" = "false" ] && [ "$outcome" = "declined" ]; then
  echo "[ok] declined (round already claimed): should-dispatch=false outcome=$outcome"
else
  echo "::error::[declined, already claimed] expected should-dispatch=false outcome=declined, got should-dispatch=${should_dispatch:-<empty>} outcome=${outcome:-<empty>}"
  FAILURES=$((FAILURES + 1))
fi
rm -f "$out_file"

echo "wing-commander-fold-queue-claim-dispatch tests: $FAILURES failure(s)."
[ "$FAILURES" -eq 0 ]
