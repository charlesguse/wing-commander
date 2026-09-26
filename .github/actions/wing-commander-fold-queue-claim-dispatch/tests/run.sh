#!/usr/bin/env bash
# Fixtures for wing-commander-fold-queue-claim-dispatch/action.yml's own
# "Attempt the round's dispatch claim" step, extracted and run against a
# throwaway LOCAL bare git repository (LEDGER_REMOTE_URL override -- no
# live network), matching this directory's sibling fixture suites.
#
# Covers quickstart.md Drill 2: a losing claim (round not empty) and a
# winning claim (round empty, atomic implement-ticket insertion).
#
# Not discovered by run-local-gates.py -- invoke directly:
# bash .github/actions/wing-commander-fold-queue-claim-dispatch/tests/run.sh
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
  local token="$1" round="$2"
  local out_file summary_file
  out_file="$(mktemp)"
  summary_file="$(mktemp)"
  (
    cd "$WORK" || exit 1
    GITHUB_ACTION_PATH="$COMPOSITE_DIR" \
      GH_TOKEN=x GITHUB_REPOSITORY=x/x \
      LEDGER_REMOTE_URL="$REMOTE" \
      SPEC_DIR="$SPEC_DIR_FIXTURE" ROUND="$round" DISPATCH_TOKEN="$token" \
      GITHUB_OUTPUT="$out_file" GITHUB_STEP_SUMMARY="$summary_file" \
      bash "$SCRIPT"
  )
  echo "$out_file"
}

# --- Scenario 1: losing claim (an act ticket still queued) -----------------
# run 300's own act ticket enqueues, folds, and releases (queue empties);
# run 300's dispatch ticket then enqueues into the empty queue -- per
# research.md D4 a non-act ticket reaching an empty queue does NOT bump the
# round, so it stays under round 1 and is granted immediately (alone at
# head). run 301's act ticket then queues behind it, still round 1.
LEDGER_REMOTE_URL="$REMOTE" GH_TOKEN=x GITHUB_REPOSITORY=x/x SPEC_DIR="$SPEC_DIR_FIXTURE" \
  KIND=act RUN_ID=300 bash "$LEDGER_SH" enqueue >/dev/null
LEDGER_REMOTE_URL="$REMOTE" GH_TOKEN=x GITHUB_REPOSITORY=x/x SPEC_DIR="$SPEC_DIR_FIXTURE" \
  TOKEN="run-300-act" OUTCOME="folded" COMMIT_SHA="cafe" LEG_ID="leg-1" SUMMARY="s" \
  bash "$LEDGER_SH" release >/dev/null
LEDGER_REMOTE_URL="$REMOTE" GH_TOKEN=x GITHUB_REPOSITORY=x/x SPEC_DIR="$SPEC_DIR_FIXTURE" \
  KIND=dispatch RUN_ID=300 bash "$LEDGER_SH" enqueue >/dev/null
LEDGER_REMOTE_URL="$REMOTE" GH_TOKEN=x GITHUB_REPOSITORY=x/x SPEC_DIR="$SPEC_DIR_FIXTURE" \
  KIND=act RUN_ID=301 bash "$LEDGER_SH" enqueue >/dev/null

out_file="$(run_claim "run-300-dispatch" 1)"
should_dispatch="$(grep '^should-dispatch=' "$out_file" | cut -d= -f2-)"
if [ "$should_dispatch" = "false" ]; then
  echo "[ok] losing claim: should-dispatch=false while an act ticket remains queued"
else
  echo "::error::[losing claim] expected should-dispatch=false, got ${should_dispatch:-<empty>}"
  FAILURES=$((FAILURES + 1))
fi
rm -f "$out_file"

LEDGER_REMOTE_URL="$REMOTE" GH_TOKEN=x GITHUB_REPOSITORY=x/x SPEC_DIR="$SPEC_DIR_FIXTURE" \
  TOKEN="run-300-dispatch" OUTCOME="not-folded" \
  bash "$LEDGER_SH" release >/dev/null

# --- Scenario 2: winning claim (round empty, atomic implement-ticket) ------
LEDGER_REMOTE_URL="$REMOTE" GH_TOKEN=x GITHUB_REPOSITORY=x/x SPEC_DIR="$SPEC_DIR_FIXTURE" \
  TOKEN="run-301-act" OUTCOME="folded" COMMIT_SHA="feed" LEG_ID="leg-1" SUMMARY="s" \
  bash "$LEDGER_SH" release >/dev/null
LEDGER_REMOTE_URL="$REMOTE" GH_TOKEN=x GITHUB_REPOSITORY=x/x SPEC_DIR="$SPEC_DIR_FIXTURE" \
  KIND=dispatch RUN_ID=301 bash "$LEDGER_SH" enqueue >/dev/null

out_file="$(run_claim "run-301-dispatch" 1)"
should_dispatch="$(grep '^should-dispatch=' "$out_file" | cut -d= -f2-)"
implement_token="$(grep '^implement-token=' "$out_file" | cut -d= -f2-)"
iteration="$(grep '^iteration=' "$out_file" | cut -d= -f2-)"
if [ "$should_dispatch" = "true" ] && [ "$implement_token" = "run-301-implement" ] && [ "$iteration" = "3" ]; then
  echo "[ok] winning claim: should-dispatch=true implement-token=$implement_token iteration=$iteration"
else
  echo "::error::[winning claim] should-dispatch=${should_dispatch:-<empty>} implement-token=${implement_token:-<empty>} iteration=${iteration:-<empty>}"
  FAILURES=$((FAILURES + 1))
fi
rm -f "$out_file"

echo "wing-commander-fold-queue-claim-dispatch tests: $FAILURES failure(s)."
[ "$FAILURES" -eq 0 ]
