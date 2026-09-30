#!/usr/bin/env bash
# Fixtures for fold-queue-ledger.sh's claim-redispatch transform, exercised
# directly the same way
# wing-commander-fold-queue-claim-dispatch-tests/run-tests.sh exercises
# claim-dispatch: against a throwaway LOCAL bare git repository
# (LEDGER_REMOTE_URL override -- no live network).
#
# Covers the T038 fix (specs/074-serialized-fold-dispatch): a winning
# redispatch claim must enqueue a fresh implement-kind ticket and return
# its token in the SAME atomic write as the redispatch_count CAS, not just
# flip the counter -- otherwise the recovered cycle re-enters
# implement.yml's concurrency group unticketed, exposed to the very
# eviction FR-016 exists to recover from. Also covers the bounded case
# (redispatch_count already 1) and same-run_id idempotency.
#
# T052 (maintainer review of #821, #719/#825): moved here (and renamed
# run.sh -> run-tests.sh) from
# .github/actions/wing-commander-fold-queue-ledger/tests/run.sh, a location
# Gate 119 (verify-actions-no-gate-scripts.py) forbids -- see
# wing-commander-fold-queue-admit-tests/run-tests.sh's header for why.
# Registered in lint-workflows.yml (Gate 128 fixtures), so both CI and
# `python .github/scripts/run-local-gates.py` now run it. Invoke directly
# for a quick local check:
# bash .github/scripts/wing-commander-fold-queue-ledger-tests/run-tests.sh
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LEDGER_SH="$HERE/../../actions/_shared/fold-queue-ledger.sh"
FAILURES=0

WORK="$(mktemp -d)"
REMOTE="$WORK/fold-queue-remote.git"
git init --quiet --bare "$REMOTE"
trap 'rm -rf "$WORK"' EXIT

SPEC_DIR_FIXTURE="specs/999-fixture"

claim_redispatch() {
  local round="$1" run_id="$2"
  LEDGER_REMOTE_URL="$REMOTE" GH_TOKEN=x GITHUB_REPOSITORY=x/x \
    SPEC_DIR="$SPEC_DIR_FIXTURE" ROUND="$round" RUN_ID="$run_id" \
    bash "$LEDGER_SH" claim-redispatch
}

# Open round 1 with a fresh redispatch_count=0 record (an act-kind ticket
# landing in an empty queue opens the round -- the same setup the
# claim-dispatch fixtures use), then empty the queue again so the winning
# claim below lands alone at index 0.
LEDGER_REMOTE_URL="$REMOTE" GH_TOKEN=x GITHUB_REPOSITORY=x/x SPEC_DIR="$SPEC_DIR_FIXTURE" \
  KIND=act RUN_ID=700 bash "$LEDGER_SH" enqueue >/dev/null
LEDGER_REMOTE_URL="$REMOTE" GH_TOKEN=x GITHUB_REPOSITORY=x/x SPEC_DIR="$SPEC_DIR_FIXTURE" \
  TOKEN="run-700-act" RUN_ID=700 OUTCOME="folded" COMMIT_SHA="cafe" LEG_ID="leg-1" SUMMARY="s" \
  bash "$LEDGER_SH" release >/dev/null

# --- Scenario 1: winning claim enqueues the ticket atomically --------------
out="$(claim_redispatch 1 900)"
should_redispatch="$(printf '%s\n' "$out" | grep '^should-redispatch=' | cut -d= -f2-)"
implement_token="$(printf '%s\n' "$out" | grep '^implement-token=' | cut -d= -f2-)"
if [ "$should_redispatch" = "true" ] && [ "$implement_token" = "run-900-implement" ]; then
  echo "[ok] winning claim: should-redispatch=true implement-token=$implement_token"
else
  echo "::error::[winning claim] should-redispatch=${should_redispatch:-<empty>} implement-token=${implement_token:-<empty>}"
  FAILURES=$((FAILURES + 1))
fi

peek_out="$(LEDGER_REMOTE_URL="$REMOTE" GH_TOKEN=x GITHUB_REPOSITORY=x/x SPEC_DIR="$SPEC_DIR_FIXTURE" \
  PEEK_TOKEN="run-900-implement" bash "$LEDGER_SH" peek)"
granted="$(printf '%s\n' "$peek_out" | grep '^granted=' | cut -d= -f2-)"
if [ "$granted" = "true" ]; then
  echo "[ok] enqueued ticket: run-900-implement landed alone at queue head and was granted"
else
  echo "::error::[enqueued ticket] expected run-900-implement granted=true, got: $peek_out"
  FAILURES=$((FAILURES + 1))
fi

# --- Scenario 2: idempotent retry with the SAME run_id ----------------------
out2="$(claim_redispatch 1 900)"
should_redispatch2="$(printf '%s\n' "$out2" | grep '^should-redispatch=' | cut -d= -f2-)"
implement_token2="$(printf '%s\n' "$out2" | grep '^implement-token=' | cut -d= -f2-)"
if [ "$should_redispatch2" = "true" ] && [ "$implement_token2" = "run-900-implement" ]; then
  echo "[ok] idempotent retry: same run_id resolves the same implement-token again"
else
  echo "::error::[idempotent retry] should-redispatch=${should_redispatch2:-<empty>} implement-token=${implement_token2:-<empty>}"
  FAILURES=$((FAILURES + 1))
fi

# --- Scenario 3: bound already spent -- a DIFFERENT run_id must lose -------
out3="$(claim_redispatch 1 901)"
should_redispatch3="$(printf '%s\n' "$out3" | grep '^should-redispatch=' | cut -d= -f2-)"
if [ "$should_redispatch3" = "false" ]; then
  echo "[ok] bound already spent: a second, different run_id resolves should-redispatch=false"
else
  echo "::error::[bound already spent] expected should-redispatch=false for a fresh run_id once redispatch_count=1, got ${should_redispatch3:-<empty>}"
  FAILURES=$((FAILURES + 1))
fi

echo "wing-commander-fold-queue-ledger tests: $FAILURES failure(s)."
[ "$FAILURES" -eq 0 ]
