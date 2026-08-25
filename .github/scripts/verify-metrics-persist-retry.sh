#!/usr/bin/env bash
# Gate: the append-with-retry algorithm (research.md R7,
# wing-commander-metrics-persist's "Append records with retry" step)
# survives a concurrent writer and fails loudly — never hangs, never
# succeeds silently — under sustained contention.
#
# This drives a standalone reimplementation of the SAME algorithm shape
# (fetch fresh, append only records not already present, commit, push;
# on rejection reset and retry with a bound) against real local bare git
# repositories, because the production logic lives inline in a composite
# action's `run:` block, not in an importable/callable form. The two are
# expected to agree because both implement research.md R7's one paragraph,
# not because one calls the other (same relationship as
# verify-metrics-schema-version-tolerance.py to T018's jq).
#
# No live subject exists in the repository (a real metrics branch is a
# runtime artifact) — this gate only runs --self-test.
set -uo pipefail

# --- the algorithm under test ------------------------------------------
# One push attempt: fetch, checkout the branch, append the record if its
# key is not already present, commit, push. Resets the local commit on a
# rejected push so the next attempt starts clean. Echoes "pushed",
# "already-present", or "rejected".
single_attempt() {
  local work="$1" branch="$2" dest="$3" record_key="$4" record_line="$5" do_fetch="$6"
  if [ "$do_fetch" = "yes" ]; then
    git -C "$work" fetch -q origin "+refs/heads/${branch}:refs/remotes/origin/${branch}" 2>/dev/null || true
    git -C "$work" checkout -q -B "$branch" "origin/$branch" 2>/dev/null || true
  fi
  if [ -f "$work/$dest" ] && grep -qF "\"$record_key\"" "$work/$dest" 2>/dev/null; then
    echo "already-present"
    return 0
  fi
  printf '%s\n' "$record_line" >> "$work/$dest"
  git -C "$work" add "$dest"
  git -C "$work" -c user.name=test -c user.email=test@example.com commit -q -m "metrics: append $record_key"
  if git -C "$work" push -q origin "HEAD:refs/heads/$branch" 2>/dev/null; then
    echo "pushed"
    return 0
  fi
  git -C "$work" reset -q --hard HEAD~1
  echo "rejected"
  return 1
}

# The bounded retry loop (research.md R7: up to N attempts, fetch fresh
# every time). Prints "UNWRITTEN:<record_key>" and returns 1 on exhaustion.
append_with_retry() {
  local work="$1" branch="$2" dest="$3" record_key="$4" record_line="$5" max_attempts="$6"
  local attempt=1 result
  while [ "$attempt" -le "$max_attempts" ]; do
    result="$(single_attempt "$work" "$branch" "$dest" "$record_key" "$record_line" yes)"
    if [ "$result" != "rejected" ]; then
      return 0
    fi
    attempt=$((attempt + 1))
  done
  echo "UNWRITTEN:$record_key"
  return 1
}

# --- fixture plumbing ----------------------------------------------------
new_bare_repo() {
  local dir; dir="$(mktemp -d)"
  git init -q --bare "$dir" >/dev/null
  echo "$dir"
}

new_clone() {
  local origin="$1" dir; dir="$(mktemp -d)"
  git clone -q "$origin" "$dir" >/dev/null 2>&1
  echo "$dir"
}

seed_branch() {
  # Creates the destination branch's first commit directly (R8's job, not
  # this gate's subject) so both writers race over an APPEND, matching
  # steady-state contention rather than the one-time branch-creation race.
  local origin="$1" branch="$2" dest="$3" work
  work="$(mktemp -d)"
  git clone -q "$origin" "$work" >/dev/null 2>&1
  git -C "$work" checkout -q --orphan "$branch"
  : > "$work/$dest"
  git -C "$work" add "$dest"
  git -C "$work" -c user.name=test -c user.email=test@example.com \
    commit -q -m "metrics: initialize $dest"
  git -C "$work" push -q origin "HEAD:refs/heads/$branch" >/dev/null 2>&1
  rm -rf "$work"
}

FAIL=0
CHECKS=0

check() {
  local desc="$1" ok="$2"
  CHECKS=$((CHECKS + 1))
  if [ "$ok" = "true" ]; then
    echo "[ok] $desc"
  else
    FAIL=$((FAIL + 1))
    echo "[FAIL] $desc"
  fi
}

test_concurrent_writers_both_survive() {
  local origin branch=metrics dest=records.jsonl
  origin="$(new_bare_repo)"
  seed_branch "$origin" "$branch" "$dest"

  local b_work a_work
  b_work="$(new_clone "$origin")"
  git -C "$b_work" checkout -q "$branch"

  # B commits locally first, based on the pre-race state, but does NOT
  # push yet — this is what forces a genuine non-fast-forward rejection
  # below, rather than a race the two writers happen never to hit.
  single_attempt "$b_work" "$branch" "$dest" "run-B:cycle:0" \
    '{"run":{"record_key":"run-B:cycle:0"},"cost_usd":1}' no >/dev/null

  # A starts clean, races ahead, and lands first.
  a_work="$(new_clone "$origin")"
  git -C "$a_work" checkout -q "$branch"
  local a_result
  a_result="$(single_attempt "$a_work" "$branch" "$dest" "run-A:cycle:0" \
    '{"run":{"record_key":"run-A:cycle:0"},"cost_usd":2}' no)"
  check "writer A's clean push succeeds" "$([ "$a_result" = "pushed" ] && echo true || echo false)"

  # B's already-committed push now collides with A's — must be rejected,
  # not silently accepted (which would mean this fixture proves nothing).
  local b_push_result
  if git -C "$b_work" push -q origin "HEAD:refs/heads/$branch" 2>/dev/null; then
    b_push_result="pushed"
  else
    b_push_result="rejected"
    git -C "$b_work" reset -q --hard HEAD~1
  fi
  check "writer B's stale push is genuinely rejected (non-fast-forward)" \
    "$([ "$b_push_result" = "rejected" ] && echo true || echo false)"

  # B's retry loop: fetches A's now-landed commit, sees its own key still
  # absent, appends, and this time succeeds.
  append_with_retry "$b_work" "$branch" "$dest" "run-B:cycle:0" \
    '{"run":{"record_key":"run-B:cycle:0"},"cost_usd":1}' 8 >/dev/null
  local retry_status=$?
  check "writer B's retry after rejection exits successfully" \
    "$([ "$retry_status" -eq 0 ] && echo true || echo false)"

  local final; final="$(new_clone "$origin")"
  git -C "$final" checkout -q "$branch"
  local has_a has_b
  has_a=$(grep -c "run-A:cycle:0" "$final/$dest" || true)
  has_b=$(grep -c "run-B:cycle:0" "$final/$dest" || true)
  check "both writers' records survive in the final store (A)" \
    "$([ "$has_a" = "1" ] && echo true || echo false)"
  check "both writers' records survive in the final store (B)" \
    "$([ "$has_b" = "1" ] && echo true || echo false)"

  rm -rf "$origin" "$a_work" "$b_work" "$final"
}

test_sustained_contention_fails_loudly_naming_the_key() {
  local origin branch=metrics dest=records.jsonl
  origin="$(new_bare_repo)"
  seed_branch "$origin" "$branch" "$dest"

  # A fixture "engineered to reject every attempt" (T053), deterministically:
  # a pre-receive hook on the bare origin that declines every push outright.
  # This is more reliable than racing a background writer against a timing
  # window — it proves the retry loop is bounded and reports exhaustion
  # under the WORST case (100% contention), not just a lucky/unlucky race.
  cat > "$origin/hooks/pre-receive" <<'HOOK'
#!/bin/sh
echo "rejected by fixture: simulating sustained contention" >&2
exit 1
HOOK
  chmod +x "$origin/hooks/pre-receive"

  local victim_work
  victim_work="$(new_clone "$origin")"
  git -C "$victim_work" checkout -q "$branch"

  local start_ts end_ts output status
  start_ts=$(date +%s)
  output="$(append_with_retry "$victim_work" "$branch" "$dest" \
    "run-victim:cycle:0" \
    '{"run":{"record_key":"run-victim:cycle:0"},"cost_usd":3}' 3)"
  status=$?
  end_ts=$(date +%s)

  check "exhausted retry returns a non-zero (failing) status" \
    "$([ "$status" -ne 0 ] && echo true || echo false)"
  check "exhausted retry names the specific unwritten record_key" \
    "$(printf '%s' "$output" | grep -q "UNWRITTEN:run-victim:cycle:0" && echo true || echo false)"
  check "exhausted retry terminates (bounded, not hanging) in under 30s" \
    "$([ "$((end_ts - start_ts))" -lt 30 ] && echo true || echo false)"

  rm -rf "$origin" "$victim_work"
}

self_test() {
  test_concurrent_writers_both_survive
  test_sustained_contention_fails_loudly_naming_the_key
  echo "verify-metrics-persist-retry self-test: $((CHECKS - FAIL))/$CHECKS checks behaved as specified."
  [ "$FAIL" -eq 0 ]
}

if [ "${1:-}" = "--self-test" ]; then
  self_test
  exit $?
fi

echo "verify-metrics-persist-retry: no live subject in the repository (the metrics branch is a runtime artifact) — run with --self-test."
exit 1
