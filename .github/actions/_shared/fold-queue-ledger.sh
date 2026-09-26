#!/usr/bin/env bash
# .github/actions/_shared/fold-queue-ledger.sh
#
# Single home for FR-020's canonical statement of why the fold/dispatch/
# implement jobs in pr-conversation.yml and implement.yml are gated the way
# they are (specs/074-serialized-fold-dispatch, research.md D1/D9). Every
# other call site that used to carry its own copy of this rationale now
# points here instead -- see fold-queue-ledger.sh.
#
# GitHub evaluates a job's `concurrency:` block before any of its steps
# run, so no step-level logic inside `act` or `dispatch-once` can prevent
# that job from becoming a second contender for the `wing-commander-<spec-dir>`
# group's single pending slot -- the eviction decision (PR #414) is made
# before the job has executed anything. The only lever available is
# gating whether a job is scheduled at all, via `needs:`. This ledger is
# that lever: `fold-turn-act`, `fold-turn-dispatch`, and
# `fold-turn-implement` each enqueue one ticket for their whole run in this
# ledger and block (via `wing-commander-fold-queue-admit`) until that
# ticket is granted, BEFORE the downstream job (`act` / `dispatch-once` /
# `implement`, whose own `concurrency:` block is otherwise unchanged) is
# even allowed to start. Because the ledger grants at most one ticket at a
# time per spec-dir -- regardless of which run or kind (act/dispatch/
# implement) holds it -- at most one job across every in-flight stage-9
# run is ever attempting to enter the GitHub concurrency group, so its
# one-pending-slot eviction rule is never exercised by two stage-9-family
# jobs again.
#
# Contract: specs/074-serialized-fold-dispatch/contracts/fold-queue-ledger-schema.md
# Shape:    specs/074-serialized-fold-dispatch/data-model.md
#
# Invoke with `bash "$GITHUB_ACTION_PATH/../_shared/fold-queue-ledger.sh" <transform>`
# rather than executing it directly or sourcing it -- matching this
# directory's existing convention (see count-turns.sh) since a plain git
# checkout does not reliably preserve the executable bit.
#
# Storage: branch `wing-commander-fold-queue` (created via the orphan-
# branch idiom on first write), one file `fold-queue.json` at the branch
# root, keyed by spec-dir. Every write is a CAS transaction: clone the
# branch fresh into an isolated temp directory (never the caller's own
# working tree, which may have other checkouts active), parse the current
# JSON (or start from {"specs": {}} if the branch or key is absent), apply
# exactly one named transform, commit, and push. On a push rejection
# (almost always non-fast-forward from a concurrent writer), the local
# clone is discarded and the whole clone-transform-push cycle is retried
# from a fresh fetch -- capped at 8 attempts with the identical
# 1s/2s/3s/4s/5s/5s/5s backoff wing-commander-metrics-persist already uses
# (.github/actions/wing-commander-metrics-persist/action.yml). Exhausting
# the retry budget is a hard `::error::` failure, never a silent no-op.
#
# Transforms (first positional argument):
#   enqueue        -- SPEC_DIR, KIND, RUN_ID
#                     Appends a ticket unless one with the same token
#                     already exists (idempotent re-enqueue). Increments
#                     the spec's round and opens a fresh round record only
#                     when the queue was empty immediately before this
#                     append. When the new ticket lands at queue index 0
#                     (an uncontended enqueue), it is granted immediately
#                     in the same write.
#   release        -- SPEC_DIR, TOKEN, RUN_ID, OUTCOME, COMMIT_SHA
#                      (optional), LEG_ID (optional), SUMMARY (optional)
#                     Removes TOKEN from the queue head and, when LEG_ID is
#                     non-empty, files a completion record under the
#                     current round (idempotent per run_id+leg_id, so a
#                     retried call never double-files). A run's whole act
#                     matrix shares ONE ticket (research.md D1), so this is
#                     called once per LEG job instance while the ticket
#                     itself is only actually dequeued on the first such
#                     call -- every later call for the same (now-absent)
#                     token still records its own leg's completion; a call
#                     with an empty LEG_ID (the dispatch/implement case,
#                     which has no per-leg completion to record) is a pure
#                     dequeue. A TOKEN present but not at the queue head is
#                     a caller error. When a new ticket becomes head as a
#                     result, it is granted in the same write.
#   claim-dispatch -- SPEC_DIR, ROUND, DISPATCH_TOKEN, ITERATION
#                     Valid only when DISPATCH_TOKEN is at the queue head.
#                     Succeeds (should-dispatch=true) only when no other
#                     `act`-kind ticket remains anywhere in the queue and
#                     this round has not already been claimed; in the same
#                     write, records dispatch_claimed_by/iteration and
#                     enqueues an `implement`-kind ticket immediately
#                     behind the calling dispatch ticket, so it becomes the
#                     new head the instant the dispatch ticket releases
#                     (research.md D5 -- no caller-visible gap for a later
#                     round's ticket to queue ahead of it).
#   reclaim-stale  -- SPEC_DIR, STALE_TOKEN
#                     Removes STALE_TOKEN from the queue head with no
#                     completion record (its outcome is unknown by
#                     construction). Valid only when STALE_TOKEN is at the
#                     queue head -- the caller (wing-commander-fold-queue-admit)
#                     is responsible for having already confirmed, via
#                     `gh api`, that STALE_TOKEN's owning run is no longer
#                     active and that its `granted_at` predates the
#                     caller-supplied staleness bound (research.md D6);
#                     this transform only performs the removal.
#
# Every transform is idempotent under retry: a retried write observes its
# own prior effect on the freshly re-fetched tip and returns the same
# result the first attempt would have, rather than double-applying.
#
# A fifth mode, `peek` -- SPEC_DIR, PEEK_TOKEN -- is not one of the four
# named transforms above and never writes: it is the read contract's poll
# (contracts/fold-queue-ledger-schema.md's "Read contract"), a plain fetch
# plus a lookup of one token's queue position/grant state, used by
# wing-commander-fold-queue-admit's wait loop. Each call re-clones the
# branch fresh -- callers MUST NOT cache a read across poll iterations.
#
# A sixth mode, `peek-round` -- SPEC_DIR, ROUND -- is the same kind of
# read-only lookup, returning a round's folded_items/not_folded_items as
# compact JSON. Used by report-fold-outcomes (research.md D3) to read THIS
# run's own completion records instead of the base..tip git-log range scan
# that could misattribute a concurrent run's fold commits.
#
# Output: one `key=value` line per result field on stdout (never
# $GITHUB_OUTPUT directly -- the calling composite step decides which
# fields it needs and how to publish them, since the three composites
# built on this script each expose a different output surface).
set -uo pipefail

TRANSFORM="${1:-}"

case "$TRANSFORM" in
  enqueue|release|claim-dispatch|reclaim-stale|peek|peek-round) ;;
  *)
    echo "::error::fold-queue-ledger.sh: unknown or missing transform '$TRANSFORM' (expected one of: enqueue, release, claim-dispatch, reclaim-stale, peek, peek-round)"
    exit 1
    ;;
esac

if [ -z "${LEDGER_REMOTE_URL:-}" ]; then
  : "${GH_TOKEN:?fold-queue-ledger.sh: GH_TOKEN is required}"
  : "${GITHUB_REPOSITORY:?fold-queue-ledger.sh: GITHUB_REPOSITORY is required}"
fi
: "${SPEC_DIR:?fold-queue-ledger.sh: SPEC_DIR is required}"

LEDGER_BRANCH="${LEDGER_BRANCH:-wing-commander-fold-queue}"
LEDGER_PATH="${LEDGER_PATH:-fold-queue.json}"

case "$TRANSFORM" in
  peek)
    : "${PEEK_TOKEN:?fold-queue-ledger.sh peek: PEEK_TOKEN is required}"
    ;;
  peek-round)
    : "${ROUND:?fold-queue-ledger.sh peek-round: ROUND is required}"
    ;;
  enqueue)
    : "${KIND:?fold-queue-ledger.sh enqueue: KIND is required}"
    : "${RUN_ID:?fold-queue-ledger.sh enqueue: RUN_ID is required}"
    ;;
  release)
    : "${TOKEN:?fold-queue-ledger.sh release: TOKEN is required}"
    : "${OUTCOME:?fold-queue-ledger.sh release: OUTCOME is required}"
    : "${RUN_ID:?fold-queue-ledger.sh release: RUN_ID is required}"
    COMMIT_SHA="${COMMIT_SHA:-}"
    LEG_ID="${LEG_ID:-}"
    SUMMARY="${SUMMARY:-}"
    ;;
  claim-dispatch)
    : "${ROUND:?fold-queue-ledger.sh claim-dispatch: ROUND is required}"
    : "${DISPATCH_TOKEN:?fold-queue-ledger.sh claim-dispatch: DISPATCH_TOKEN is required}"
    : "${ITERATION:?fold-queue-ledger.sh claim-dispatch: ITERATION is required}"
    ;;
  reclaim-stale)
    : "${STALE_TOKEN:?fold-queue-ledger.sh reclaim-stale: STALE_TOKEN is required}"
    ;;
esac

workdir="$(mktemp -d "${RUNNER_TEMP:-/tmp}/wc-fold-queue-ledger.XXXXXX")"
trap 'rm -rf "$workdir"' EXIT

# LEDGER_REMOTE_URL overrides both the authenticated and plain remote URL
# with a single local path/URL -- unset in every real call site (the
# composites never set it), it exists so the fixtures under this script's
# own tests/ directory can point the whole clone/commit/push cycle at a
# throwaway local bare repository instead of github.com, with no live
# network involved.
auth_url="${LEDGER_REMOTE_URL:-https://x-access-token:${GH_TOKEN}@github.com/${GITHUB_REPOSITORY}.git}"
plain_url="${LEDGER_REMOTE_URL:-https://github.com/${GITHUB_REPOSITORY}.git}"

if [ "$TRANSFORM" = "peek" ]; then
  clone_dir="$workdir/peek-clone"
  if git ls-remote --exit-code "$auth_url" "refs/heads/$LEDGER_BRANCH" >/dev/null 2>&1; then
    if ! git clone --quiet --depth 1 --branch "$LEDGER_BRANCH" --single-branch "$auth_url" "$clone_dir" 2>"$workdir/peek-clone-err.txt"; then
      cat "$workdir/peek-clone-err.txt" >&2
      echo "::error::fold-queue-ledger.sh peek: failed to read $LEDGER_BRANCH"
      exit 1
    fi
  fi
  ledger_file="$clone_dir/$LEDGER_PATH"
  if [ -f "$ledger_file" ]; then
    current_json="$ledger_file"
  else
    current_json="$workdir/empty-ledger.json"
    echo '{"specs":{}}' > "$current_json"
  fi
  jq -c --arg spec "$SPEC_DIR" --arg token "$PEEK_TOKEN" '
    (.specs[$spec].queue // []) as $q
    | ($q | map(.token) | index($token)) as $idx
    | {
        position: ($idx // -1),
        granted: ((($idx // -1) == 0) and (($q[0].granted_at // null) != null)),
        round: (.specs[$spec].round // 0),
        "head-token": (($q[0].token) // ""),
        "head-run-id": (($q[0].run_id) // ""),
        "head-granted-at": (($q[0].granted_at) // "")
      }
  ' "$current_json" | jq -r 'to_entries[] | "\(.key)=\(.value)"'
  exit 0
fi

if [ "$TRANSFORM" = "peek-round" ]; then
  clone_dir="$workdir/peek-round-clone"
  if git ls-remote --exit-code "$auth_url" "refs/heads/$LEDGER_BRANCH" >/dev/null 2>&1; then
    if ! git clone --quiet --depth 1 --branch "$LEDGER_BRANCH" --single-branch "$auth_url" "$clone_dir" 2>"$workdir/peek-round-clone-err.txt"; then
      cat "$workdir/peek-round-clone-err.txt" >&2
      echo "::error::fold-queue-ledger.sh peek-round: failed to read $LEDGER_BRANCH"
      exit 1
    fi
  fi
  ledger_file="$clone_dir/$LEDGER_PATH"
  if [ -f "$ledger_file" ]; then
    current_json="$ledger_file"
  else
    current_json="$workdir/empty-ledger.json"
    echo '{"specs":{}}' > "$current_json"
  fi
  jq -c --arg spec "$SPEC_DIR" --arg round "$ROUND" '
    {
      "folded-items": (.specs[$spec].rounds[$round].folded_items // [] | tojson),
      "not-folded-items": (.specs[$spec].rounds[$round].not_folded_items // [] | tojson)
    }
  ' "$current_json" | jq -r 'to_entries[] | "\(.key)=\(.value)"'
  exit 0
fi

filter_file="$workdir/transform.jq"

case "$TRANSFORM" in
  enqueue)
    cat > "$filter_file" <<'JQ'
.specs[$spec] //= {"round": 0, "queue": [], "rounds": {}}
| (.specs[$spec].queue | map(.token) | index($token)) as $existing_idx
| if $existing_idx != null then
    {
      changed: false,
      ledger: .,
      result: {
        token: $token,
        round: (.specs[$spec].round | tostring),
        granted: ((($existing_idx == 0) and (.specs[$spec].queue[0].granted_at != null)) | tostring)
      }
    }
  else
    (.specs[$spec].queue | length == 0) as $was_empty
    | (.specs[$spec].queue += [{"token": $token, "kind": $kind, "run_id": $run_id, "enqueued_at": $now, "granted_at": null}])
    # Only an act-kind ticket reaching an empty queue opens a fresh round
    # (research.md D4: "a fresh act-kind ticket enqueues after the
    # previous round's queue emptied out"). A dispatch/implement ticket
    # that happens to reach an empty queue -- its own run's act ticket
    # just released, nothing else queued yet -- stays under the CURRENT
    # round instead: it is reporting on the round its own run's act phase
    # already belonged to, not opening a new one of its own.
    | (if $was_empty and $kind == "act" then
         (.specs[$spec].round + 1) as $newround
         | .specs[$spec].round = $newround
         | .specs[$spec].rounds[($newround | tostring)] = {
             "opened_at": $now,
             "folded_items": [],
             "not_folded_items": [],
             "dispatch_claimed_by": null,
             "iteration": null,
             "implement_run_id": null,
             "redispatch_count": 0
           }
       else
         .
       end)
    # Granting on an uncontended enqueue is independent of the round logic
    # above -- any ticket (any kind) that lands alone at queue index 0 is
    # granted immediately.
    | (if $was_empty then
         .specs[$spec].queue[0].granted_at = $now
       else
         .
       end) as $newdoc
    | {
        changed: true,
        ledger: $newdoc,
        result: {
          token: $token,
          round: ($newdoc.specs[$spec].round | tostring),
          granted: ((($newdoc.specs[$spec].queue[0].token == $token) and ($newdoc.specs[$spec].queue[0].granted_at != null)) | tostring)
        }
      }
  end
JQ
    ;;
  release)
    cat > "$filter_file" <<'JQ'
.specs[$spec] //= {"round": 0, "queue": [], "rounds": {}}
| (.specs[$spec].queue | map(.token) | index($token)) as $idx
| (.specs[$spec].round | tostring) as $round
# A run's whole act matrix shares ONE ticket (research.md D1), so this
# transform is called once per LEG job instance while only the first such
# call still finds the ticket present -- every call must still record its
# own leg's completion, even the calls that find the ticket already
# dequeued by an earlier leg. Recording is itself idempotent per
# (run_id, leg_id), independent of the dequeue below, so a retried release
# of the SAME leg never double-appends.
| (($leg_id != "") and (
     ((.specs[$spec].rounds[$round].folded_items // []) + (.specs[$spec].rounds[$round].not_folded_items // []))
     | map(select(.run_id == $run_id and .leg_id == $leg_id)) | length > 0
   )) as $already_recorded
| (if ($leg_id != "") and ($already_recorded | not) then
     (if $commit_sha != "" then
        .specs[$spec].rounds[$round].folded_items = ((.specs[$spec].rounds[$round].folded_items // []) + [{"run_id": $run_id, "leg_id": $leg_id, "summary": $summary, "commit_sha": $commit_sha}])
      else
        .specs[$spec].rounds[$round].not_folded_items = ((.specs[$spec].rounds[$round].not_folded_items // []) + [{"run_id": $run_id, "leg_id": $leg_id, "outcome": $outcome}])
      end)
   else
     .
   end)
| if $idx == null then
    { changed: (($leg_id != "") and ($already_recorded | not)), ledger: ., result: { released: "false", "already-absent": "true" } }
  elif $idx != 0 then
    { error: ("fold-queue-ledger release: token " + $token + " is present but not at queue head (index " + ($idx | tostring) + ") -- release is only valid for the granted head ticket") }
  else
    .specs[$spec].queue |= .[1:]
    | (if (.specs[$spec].queue | length) > 0 and (.specs[$spec].queue[0].granted_at == null) then
         .specs[$spec].queue[0].granted_at = $now
       else
         .
       end) as $newdoc
    | { changed: true, ledger: $newdoc, result: { released: "true", "already-absent": "false" } }
  end
JQ
    ;;
  claim-dispatch)
    cat > "$filter_file" <<'JQ'
.specs[$spec] //= {"round": 0, "queue": [], "rounds": {}}
| if (.specs[$spec].queue | length) == 0 or (.specs[$spec].queue[0].token != $token) then
    { error: ("fold-queue-ledger claim-dispatch: dispatch token " + $token + " is not at queue head") }
  else
    (.specs[$spec].queue[0].run_id) as $run_id
    | ((.specs[$spec].queue[1:] | map(select(.kind == "act")) | length) == 0) as $round_empty
    | ((.specs[$spec].rounds[$round].dispatch_claimed_by // null) == null) as $unclaimed
    | if ($round_empty and $unclaimed) then
        ("run-" + $run_id + "-implement") as $impl_token
        | .specs[$spec].rounds[$round].dispatch_claimed_by = $run_id
        | .specs[$spec].rounds[$round].iteration = ($iteration | tonumber)
        | .specs[$spec].queue = ([.specs[$spec].queue[0]] + [{"token": $impl_token, "kind": "implement", "run_id": $run_id, "enqueued_at": $now, "granted_at": null}] + .specs[$spec].queue[1:])
        | {
            changed: true,
            ledger: .,
            result: {
              "should-dispatch": "true",
              "implement-token": $impl_token,
              "iteration": ($iteration),
              "folded-items": (.specs[$spec].rounds[$round].folded_items // [] | tojson),
              "not-folded-items": (.specs[$spec].rounds[$round].not_folded_items // [] | tojson)
            }
          }
      else
        { changed: false, ledger: ., result: { "should-dispatch": "false" } }
      end
  end
JQ
    ;;
  reclaim-stale)
    cat > "$filter_file" <<'JQ'
.specs[$spec] //= {"round": 0, "queue": [], "rounds": {}}
| if (.specs[$spec].queue | length) == 0 or (.specs[$spec].queue[0].token != $stale_token) then
    { changed: false, ledger: ., result: { reclaimed: "false" } }
  else
    .specs[$spec].queue = (.specs[$spec].queue[1:])
    | (if (.specs[$spec].queue | length) > 0 and (.specs[$spec].queue[0].granted_at == null) then
         .specs[$spec].queue[0].granted_at = $now
       else
         .
       end) as $newdoc
    | { changed: true, ledger: $newdoc, result: { reclaimed: "true" } }
  end
JQ
    ;;
esac

max_attempts=8
attempt=1
success=false
last_error=""

while [ "$attempt" -le "$max_attempts" ]; do
  clone_dir="$workdir/clone-$attempt"
  rm -rf "$clone_dir"

  if git ls-remote --exit-code "$auth_url" "refs/heads/$LEDGER_BRANCH" >/dev/null 2>&1; then
    if ! git clone --quiet --branch "$LEDGER_BRANCH" --single-branch "$auth_url" "$clone_dir" 2>"$workdir/clone-err.txt"; then
      cat "$workdir/clone-err.txt" >&2
      sleep_for=$(( attempt < 5 ? attempt : 5 ))
      sleep "$sleep_for"
      attempt=$(( attempt + 1 ))
      continue
    fi
  else
    if ! git clone --quiet --no-checkout "$auth_url" "$clone_dir" 2>"$workdir/clone-err.txt"; then
      cat "$workdir/clone-err.txt" >&2
      sleep_for=$(( attempt < 5 ? attempt : 5 ))
      sleep "$sleep_for"
      attempt=$(( attempt + 1 ))
      continue
    fi
    (
      cd "$clone_dir" || exit 1
      git checkout --quiet --orphan "$LEDGER_BRANCH"
      git rm -rq --cached . >/dev/null 2>&1 || true
      find . -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +
    )
  fi

  (
    cd "$clone_dir" || exit 1
    git remote set-url origin "$plain_url"
    git config user.name "github-actions[bot]"
    git config user.email "github-actions[bot]@users.noreply.github.com"
  )

  ledger_file="$clone_dir/$LEDGER_PATH"
  if [ -f "$ledger_file" ]; then
    current_json="$ledger_file"
  else
    current_json="$workdir/empty-ledger.json"
    echo '{"specs":{}}' > "$current_json"
  fi

  now="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  output_file="$workdir/output-$attempt.json"

  case "$TRANSFORM" in
    enqueue)
      jq -c --arg spec "$SPEC_DIR" --arg token "run-${RUN_ID}-${KIND}" --arg kind "$KIND" --arg run_id "$RUN_ID" --arg now "$now" \
        -f "$filter_file" "$current_json" > "$output_file"
      ;;
    release)
      jq -c --arg spec "$SPEC_DIR" --arg token "$TOKEN" --arg run_id "$RUN_ID" --arg outcome "$OUTCOME" --arg commit_sha "$COMMIT_SHA" --arg leg_id "$LEG_ID" --arg summary "$SUMMARY" --arg now "$now" \
        -f "$filter_file" "$current_json" > "$output_file"
      ;;
    claim-dispatch)
      jq -c --arg spec "$SPEC_DIR" --arg token "$DISPATCH_TOKEN" --arg round "$ROUND" --arg iteration "$ITERATION" --arg now "$now" \
        -f "$filter_file" "$current_json" > "$output_file"
      ;;
    reclaim-stale)
      jq -c --arg spec "$SPEC_DIR" --arg stale_token "$STALE_TOKEN" --arg now "$now" \
        -f "$filter_file" "$current_json" > "$output_file"
      ;;
  esac

  if [ "$(jq -r 'has("error")' "$output_file")" = "true" ]; then
    echo "::error::$(jq -r '.error' "$output_file")"
    exit 1
  fi

  changed="$(jq -r '.changed' "$output_file")"

  if [ "$changed" != "true" ]; then
    jq -r '.result | to_entries[] | "\(.key)=\(.value)"' "$output_file"
    success=true
    break
  fi

  jq -c '.ledger' "$output_file" > "$ledger_file"

  (
    cd "$clone_dir" || exit 1
    git add "$LEDGER_PATH"
    git commit --quiet -m "fold-queue: $TRANSFORM ($SPEC_DIR)"
  )

  if git -C "$clone_dir" push --quiet "$auth_url" "HEAD:refs/heads/$LEDGER_BRANCH" 2>"$workdir/push-err.txt"; then
    jq -r '.result | to_entries[] | "\(.key)=\(.value)"' "$output_file"
    success=true
    break
  fi

  last_error="$(cat "$workdir/push-err.txt")"
  sleep_for=$(( attempt < 5 ? attempt : 5 ))
  sleep "$sleep_for"
  attempt=$(( attempt + 1 ))
done

if [ "$success" != "true" ]; then
  echo "::error::fold-queue-ledger.sh: gave up applying '$TRANSFORM' for $SPEC_DIR after $max_attempts attempts. Last push error: $last_error"
  exit 1
fi
