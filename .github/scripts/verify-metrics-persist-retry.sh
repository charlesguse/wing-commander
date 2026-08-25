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

# --- batch-shaped variant of the algorithm ------------------------------
# T062-T064 (tasks.md Phase 9) need scenarios single_attempt/append_with_retry
# cannot express: an EMPTY batch (zero artifacts discovered), and running the
# same non-empty batch twice against an already-persisted key. Both are the
# real "Append records with retry" step's shape (a batch of zero-or-more
# not-yet-present records filtered against the destination, appended in one
# commit) rather than one record at a time, so this adds a batch-based
# sibling alongside the existing single-record functions instead of
# rewriting them and risking the two already-passing scenarios above.
append_batch_with_retry() {
  local work="$1" branch="$2" dest="$3" batch_file="$4" max_attempts="$5"
  local attempt=1
  while [ "$attempt" -le "$max_attempts" ]; do
    git -C "$work" fetch -q origin "+refs/heads/${branch}:refs/remotes/origin/${branch}" 2>/dev/null || true
    git -C "$work" checkout -q -B "$branch" "origin/$branch" 2>/dev/null || true

    local existing_keys="$work/.existing-keys.txt"
    if [ -f "$work/$dest" ]; then
      jq -r '.run.record_key // empty' "$work/$dest" 2>/dev/null > "$existing_keys" || : > "$existing_keys"
    else
      : > "$existing_keys"
    fi

    local to_append="$work/.to-append.jsonl"
    : > "$to_append"
    while IFS= read -r line; do
      [ -n "$line" ] || continue
      local key
      key="$(printf '%s' "$line" | jq -r '.run.record_key // empty')"
      if [ -n "$key" ] && grep -qxF "$key" "$existing_keys" 2>/dev/null; then
        continue
      fi
      printf '%s\n' "$line" >> "$to_append"
    done < "$batch_file"

    if [ ! -s "$to_append" ]; then
      # Nothing new to write — either the batch was empty (zero artifacts
      # discovered, T062) or every key in it is already persisted (repeat
      # persistence, T064). Both are a successful zero-record contribution,
      # not a failure (FR-021/FR-018).
      echo "PERSISTED:0"
      return 0
    fi

    cat "$to_append" >> "$work/$dest"
    git -C "$work" add "$dest"
    local n
    n="$(wc -l < "$to_append" | tr -d ' ')"
    git -C "$work" -c user.name=test -c user.email=test@example.com \
      commit -q -m "metrics: append $n record(s)"

    if git -C "$work" push -q origin "HEAD:refs/heads/$branch" 2>/dev/null; then
      echo "PERSISTED:$n"
      return 0
    fi

    git -C "$work" reset -q --hard HEAD~1
    attempt=$((attempt + 1))
  done
  echo "UNWRITTEN"
  return 1
}

# Mirrors the composite's "Create destination branch (first write, R8)"
# step: only runs when the branch does not already exist, orphan-commits the
# first batch, and pushes it (T063).
first_write_if_missing() {
  local origin="$1" branch="$2" dest="$3" batch_file="$4"
  if git ls-remote --exit-code "$origin" "refs/heads/$branch" >/dev/null 2>&1; then
    echo "already-exists"
    return 0
  fi
  local work
  work="$(mktemp -d)"
  git clone -q "$origin" "$work" >/dev/null 2>&1
  git -C "$work" checkout -q --orphan "$branch"
  git -C "$work" rm -rf . >/dev/null 2>&1 || true
  cp "$batch_file" "$work/$dest"
  git -C "$work" add "$dest"
  git -C "$work" -c user.name=test -c user.email=test@example.com \
    commit -q -m "metrics: initialize $dest" --allow-empty
  git -C "$work" push -q origin "HEAD:refs/heads/$branch"
  rm -rf "$work"
  echo "created"
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

test_zero_artifact_discovery_is_zero_failure() {
  # T062: discovery finding zero metrics-record* artifacts must still exit
  # successfully, appending nothing — not merely assumed from FR-021's prose.
  local origin branch=metrics dest=records.jsonl
  origin="$(new_bare_repo)"
  seed_branch "$origin" "$branch" "$dest"

  local work; work="$(new_clone "$origin")"
  git -C "$work" checkout -q "$branch"
  local empty_batch; empty_batch="$(mktemp)"
  : > "$empty_batch"

  local output status
  output="$(append_batch_with_retry "$work" "$branch" "$dest" "$empty_batch" 8)"
  status=$?
  check "a zero-artifact run reports zero persisted" \
    "$([ "$status" -eq 0 ] && [ "$output" = "PERSISTED:0" ] && echo true || echo false)"

  local final; final="$(new_clone "$origin")"
  git -C "$final" checkout -q "$branch"
  check "the destination file is unchanged after a zero-artifact run" \
    "$([ ! -s "$final/$dest" ] && echo true || echo false)"

  rm -rf "$origin" "$work" "$final" "$empty_batch"
}

test_first_write_creates_missing_destination_branch() {
  # T063: starting from a destination branch that does not exist yet, the
  # first append creates it (research.md R8's orphan-commit shape).
  local origin branch=metrics dest=records.jsonl
  origin="$(new_bare_repo)"   # deliberately NOT seeded — no branch exists

  check "the destination branch does not exist before the first write" \
    "$(git ls-remote --exit-code "$origin" "refs/heads/$branch" >/dev/null 2>&1 && echo false || echo true)"

  local batch; batch="$(mktemp)"
  printf '%s\n' '{"run":{"record_key":"run-first:cycle:0"},"cost_usd":5}' > "$batch"

  local result; result="$(first_write_if_missing "$origin" "$branch" "$dest" "$batch")"
  check "the first write reports it created the destination branch" \
    "$([ "$result" = "created" ] && echo true || echo false)"
  check "the destination branch now exists on the remote" \
    "$(git ls-remote --exit-code "$origin" "refs/heads/$branch" >/dev/null 2>&1 && echo true || echo false)"

  local final; final="$(new_clone "$origin")"
  git -C "$final" checkout -q "$branch"
  check "the first record is present in the newly created destination" \
    "$([ -f "$final/$dest" ] && grep -q "run-first:cycle:0" "$final/$dest" && echo true || echo false)"

  rm -rf "$origin" "$final" "$batch"
}

test_idempotent_repeat_persistence_is_byte_for_byte_unchanged() {
  # T064: appending the same already-persisted record_key a second time must
  # leave the destination store byte-for-byte unchanged, not merely "a fresh
  # key round-trips once" (FR-018/SC-005).
  local origin branch=metrics dest=records.jsonl
  origin="$(new_bare_repo)"
  seed_branch "$origin" "$branch" "$dest"

  local batch; batch="$(mktemp)"
  printf '%s\n' '{"run":{"record_key":"run-idem:cycle:0"},"cost_usd":7}' > "$batch"

  local work1; work1="$(new_clone "$origin")"
  git -C "$work1" checkout -q "$branch"
  append_batch_with_retry "$work1" "$branch" "$dest" "$batch" 8 >/dev/null

  local before; before="$(new_clone "$origin")"
  git -C "$before" checkout -q "$branch"
  local before_hash; before_hash="$(sha1sum "$before/$dest" 2>/dev/null | awk '{print $1}')"

  local work2; work2="$(new_clone "$origin")"
  git -C "$work2" checkout -q "$branch"
  local output2 status2
  output2="$(append_batch_with_retry "$work2" "$branch" "$dest" "$batch" 8)"
  status2=$?

  local final; final="$(new_clone "$origin")"
  git -C "$final" checkout -q "$branch"
  local after_hash; after_hash="$(sha1sum "$final/$dest" 2>/dev/null | awk '{print $1}')"

  check "repeat persistence of an already-present record reports zero newly persisted" \
    "$([ "$status2" -eq 0 ] && [ "$output2" = "PERSISTED:0" ] && echo true || echo false)"
  check "the destination store is byte-for-byte unchanged after the repeat run" \
    "$([ -n "$before_hash" ] && [ "$before_hash" = "$after_hash" ] && echo true || echo false)"

  rm -rf "$origin" "$batch" "$work1" "$before" "$work2" "$final"
}

self_test() {
  test_concurrent_writers_both_survive
  test_sustained_contention_fails_loudly_naming_the_key
  test_zero_artifact_discovery_is_zero_failure
  test_first_write_creates_missing_destination_branch
  test_idempotent_repeat_persistence_is_byte_for_byte_unchanged
  echo "verify-metrics-persist-retry self-test: $((CHECKS - FAIL))/$CHECKS checks behaved as specified."
  [ "$FAIL" -eq 0 ]
}

if [ "${1:-}" = "--self-test" ]; then
  self_test
  exit $?
fi

echo "verify-metrics-persist-retry: no live subject in the repository (the metrics branch is a runtime artifact) — run with --self-test."
exit 1
