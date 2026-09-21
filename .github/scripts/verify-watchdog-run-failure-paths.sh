#!/usr/bin/env bash
# Gate 36 — verify-watchdog-run.sh's failure branches actually execute (#169).
#
# The stage-8b verifier is itself a safety net, and until this harness its
# error-handling branches had never run anywhere: the two `exit 2` fetch
# guards, the startup_failure shape, the history-fetch fallback, and the
# CREATE_ISSUE filing arm — which carried the same read-a-failed-search-as-
# empty defect that made settle file a duplicate issue every day (#167).
# A branch that only runs when a dependency fails needs a fixture that makes
# it fail; this file is that fixture set, following the injectable-failure
# shape of auto-update-spec-kit-tests/gh_stub.py (GH_STUB_FAIL, PR #168).
#
# Mechanics: a `gh` stub on PATH serves canned Actions-API shapes from a
# fixture dir, records every invocation, and fails any call whose argv
# matches a regex in $WD_STUB_FAIL (one per line). Scenarios drive the REAL
# shipped script through healthy and failing dependency states; two
# mutations are then applied to a COPY of the script and the harness
# asserts the covering scenario goes red for the right reason
# (constitution VIII — the assertion is checked, not just the coverage).
#
# Usage: .github/scripts/verify-watchdog-run-failure-paths.sh
# Exit code: 0 = every scenario and mutation behaved; 1 = otherwise.

set -uo pipefail

SCRIPT=".github/scripts/verify-watchdog-run.sh"
bad=0
ok()   { echo "[ok] $1"; }
fail() { bad=$((bad+1)); echo "[FAIL] $1"; }

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

# ── The gh stub ─────────────────────────────────────────────────────────────
mkdir -p "$work/bin"
cat > "$work/bin/gh" <<'STUB'
#!/usr/bin/env bash
# Records argv; fails on $WD_STUB_FAIL regex match; otherwise serves the
# fixture shaped like the real API response for the endpoint asked about.
argv="$*"
printf '%s\n' "$argv" >> "$WD_CALL_LOG"
while IFS= read -r sel; do
  [ -n "$sel" ] || continue
  if grep -Eq "$sel" <<<"$argv"; then
    echo "gh: Not Found (HTTP 404) [injected: $sel]" >&2
    exit 1
  fi
done <<<"${WD_STUB_FAIL:-}"

case "$1" in
  api)
    path="$2"
    case "$path" in
      */actions/runs/*/jobs*)   cat "$WD_FIXTURES/jobs.json";;
      */actions/runs/*)         cat "$WD_FIXTURES/run.json";;
      */actions/workflows/*/runs*) cat "$WD_FIXTURES/history.json";;
      */actions/jobs/*/logs)    cat "$WD_FIXTURES/diagnose.log";;
      *) echo "gh-stub: unmodelled api path $path" >&2; exit 1;;
    esac;;
  run)
    # gh run download <id> -R <repo> -n <name> -D <dir>
    dir=""
    name=""
    prev=""
    for a in "$@"; do
      [ "$prev" = "-D" ] && dir="$a"
      [ "$prev" = "-n" ] && name="$a"
      prev="$a"
    done
    if [ "$name" != "claude-execution-output-diagnose" ]; then
      echo "gh-stub: unmodelled artifact name '$name'" >&2
      exit 1
    fi
    if [ -f "$WD_FIXTURES/artifact.json" ] && [ -n "$dir" ]; then
      cp "$WD_FIXTURES/artifact.json" "$dir/claude-execution-output.json"
      exit 0
    fi
    echo "no artifact matches claude-execution-output-diagnose" >&2
    exit 1;;
  issue)
    case "$2" in
      list)    cat "$WD_FIXTURES/issue-search.txt" 2>/dev/null || echo -n "";;
      comment) exit 0;;
      create)  exit 0;;
      *) echo "gh-stub: unmodelled issue subcommand $2" >&2; exit 1;;
    esac;;
  *) echo "gh-stub: unmodelled command $1" >&2; exit 1;;
esac
STUB
chmod +x "$work/bin/gh"

# ── Fixtures: one healthy watchdog run, in the API's real shapes ────────────
mkdir -p "$work/fixtures"
cat > "$work/fixtures/run.json" <<'JSON'
{"id": 9001, "conclusion": "success", "workflow_id": 777,
 "run_started_at": "2026-08-25T01:00:00Z", "updated_at": "2026-08-25T01:02:00Z",
 "html_url": "https://example.invalid/runs/9001"}
JSON
# Steps carry the exact display names the verifier keys on; conclusions are
# the healthy set (reporters skipped, read-back and the safety-net gate
# green). total_count feeds the zero-jobs startup check.
cat > "$work/fixtures/jobs.json" <<'JSON'
{"total_count": 3, "jobs": [
  {"id": 1, "name": "watchdog / collect", "conclusion": "success",
   "started_at": "2026-08-25T01:00:05Z", "completed_at": "2026-08-25T01:00:35Z",
   "steps": [
     {"name": "Report \"could not inspect\" to lifecycle issue", "conclusion": "skipped"}
   ]},
  {"id": 2, "name": "watchdog / diagnose", "conclusion": "success",
   "started_at": "2026-08-25T01:00:40Z", "completed_at": "2026-08-25T01:01:40Z",
   "steps": [
     {"name": "Report \"diagnose failed\" to lifecycle issue", "conclusion": "skipped"},
     {"name": "Read back diagnose outcome", "conclusion": "success"}
   ]},
  {"id": 3, "name": "watchdog / report-unhandled-failure", "conclusion": "success",
   "started_at": "2026-08-25T01:01:45Z", "completed_at": "2026-08-25T01:01:55Z",
   "steps": [
     {"name": "Determine failed jobs", "conclusion": "success"},
     {"name": "Report unhandled job failure", "conclusion": "skipped"},
     {"name": "Report unhandled job failure to run summary", "conclusion": "skipped"}
   ]}
]}
JSON
cat > "$work/fixtures/history.json" <<'JSON'
{"workflow_runs": [
  {"id": 8001, "run_started_at": "2026-08-24T01:00:00Z", "updated_at": "2026-08-24T01:02:00Z"},
  {"id": 8002, "run_started_at": "2026-08-23T01:00:00Z", "updated_at": "2026-08-23T01:02:10Z"},
  {"id": 8003, "run_started_at": "2026-08-22T01:00:00Z", "updated_at": "2026-08-22T01:01:50Z"},
  {"id": 8004, "run_started_at": "2026-08-21T01:00:00Z", "updated_at": "2026-08-21T01:02:05Z"}
]}
JSON
cat > "$work/fixtures/artifact.json" <<'JSON'
[{"type": "result", "num_turns": 7, "is_error": false, "subtype": "success",
  "result": "no findings"}]
JSON
printf 'clean diagnose log with no crash signatures\n' > "$work/fixtures/diagnose.log"
printf '' > "$work/fixtures/issue-search.txt"

# ── Scenario driver ─────────────────────────────────────────────────────────
# run_scenario <script> <stub-fail-regexes> <CREATE_ISSUE> -> populates
# $rc and $out; the per-scenario assertions read both.
run_scenario() {
  local script="$1" stub_fail="$2" create="$3"
  : > "$work/calls.log"
  out="$(PATH="$work/bin:$PATH" \
      WD_FIXTURES="$work/fixtures" WD_CALL_LOG="$work/calls.log" \
      WD_STUB_FAIL="$stub_fail" \
      RUN_ID=9001 REPO=o/r GH_TOKEN=stub CREATE_ISSUE="$create" \
      GITHUB_STEP_SUMMARY="" bash "$script" 2>&1)"
  rc=$?
}

# scenarios <script> <tag> — the harness's whole truth table. `tag` prefixes
# every report line so mutation runs read distinctly.
scenarios() {
  local script="$1" tag="$2"

  # s1: the run fetch itself fails -> exit 2, never "verified".
  run_scenario "$script" '/actions/runs/9001$' false
  if [ "$rc" = "2" ] && grep -q "cannot fetch run" <<<"$out"; then
    ok "$tag s1: run-fetch failure exits 2 (could not verify != verified)"
  else
    fail "$tag s1: expected exit 2 + 'cannot fetch run', got rc=$rc: $(tail -1 <<<"$out")"
  fi

  # s2: the jobs fetch fails -> exit 2.
  run_scenario "$script" 'jobs\?per_page=100' false
  if [ "$rc" = "2" ] && grep -q "cannot fetch jobs" <<<"$out"; then
    ok "$tag s2: jobs-fetch failure exits 2"
  else
    fail "$tag s2: expected exit 2 + 'cannot fetch jobs', got rc=$rc: $(tail -1 <<<"$out")"
  fi

  # s3: healthy run, but the HISTORY fetch fails -> the duration band is
  # skipped (its fallback branch executes) and the verdict is still 0.
  run_scenario "$script" 'workflows/777/runs' false
  if [ "$rc" = "0" ] && grep -q "fewer than 3 prior successful runs" <<<"$out"; then
    ok "$tag s3: healthy run verifies (exit 0) with the history fallback branch executed"
  else
    fail "$tag s3: expected exit 0 + history fallback, got rc=$rc: $(tail -2 <<<"$out")"
  fi

  # s4: startup_failure -> exit 1 with the never-started reason (no job
  # evidence exists; artifact download also fails, exercising its notice arm).
  cp "$work/fixtures/run.json" "$work/run.json.bak"
  cp "$work/fixtures/jobs.json" "$work/jobs.json.bak"
  mv "$work/fixtures/artifact.json" "$work/artifact.json.bak"
  sed -i 's/"success"/"startup_failure"/' "$work/fixtures/run.json"
  printf '{"total_count": 0, "jobs": []}\n' > "$work/fixtures/jobs.json"
  run_scenario "$script" '' false
  if [ "$rc" = "1" ] && grep -q "never started" <<<"$out"; then
    ok "$tag s4: startup_failure is a red verdict, not a pass over missing evidence"
  else
    fail "$tag s4: expected exit 1 + 'never started', got rc=$rc: $(tail -2 <<<"$out")"
  fi
  mv "$work/run.json.bak" "$work/fixtures/run.json"
  mv "$work/jobs.json.bak" "$work/fixtures/jobs.json"
  mv "$work/artifact.json.bak" "$work/fixtures/artifact.json"

  # s5: a failing run wants to file, but the dedup SEARCH fails -> no issue
  # is created (a failed search is not an empty result - the #167 shape).
  sed -i 's/"conclusion": "success"/"conclusion": "failure"/' "$work/fixtures/run.json"
  run_scenario "$script" 'issue list' true
  created="$(grep -c '^issue create' "$work/calls.log" || true)"
  if [ "$rc" = "1" ] && [ "$created" = "0" ] && grep -q "not filing" <<<"$out"; then
    ok "$tag s5: dedup-search failure skips filing instead of creating a duplicate"
  else
    fail "$tag s5: expected exit 1, zero 'issue create' calls and a 'not filing' notice; got rc=$rc create-calls=$created"
  fi

  # s6: same failing run, search WORKS and finds an existing issue -> the
  # comment arm runs and create still does not (proves the stub returns the
  # real shape and the dedup arm consumes it).
  printf '42\n' > "$work/fixtures/issue-search.txt"
  run_scenario "$script" '' true
  commented="$(grep -c '^issue comment 42' "$work/calls.log" || true)"
  created="$(grep -c '^issue create' "$work/calls.log" || true)"
  if [ "$rc" = "1" ] && [ "$commented" = "1" ] && [ "$created" = "0" ]; then
    ok "$tag s6: a found issue gets a comment, not a duplicate"
  else
    fail "$tag s6: expected one 'issue comment 42' and zero creates; got comment=$commented create=$created rc=$rc"
  fi
  printf '' > "$work/fixtures/issue-search.txt"
  sed -i 's/"conclusion": "failure"/"conclusion": "success"/' "$work/fixtures/run.json"

  # ── specs/047-rate-limited-verdict: the verifier's rate-limited suppression ──
  cp "$work/fixtures/run.json" "$work/run.json.bak_rl"
  cp "$work/fixtures/jobs.json" "$work/jobs.json.bak_rl"
  cp "$work/fixtures/artifact.json" "$work/artifact.json.bak_rl"

  # A rate-limited diagnose job: "Report rate-limited..." ran, "Report
  # diagnose failed..." was skipped, a short (under-floor) run duration, and
  # a terminal artifact shaped like the real #300/#278 evidence (429).
  cat > "$work/fixtures/run.json" <<'JSON'
{"id": 9001, "conclusion": "success", "workflow_id": 777,
 "run_started_at": "2026-08-25T01:00:00Z", "updated_at": "2026-08-25T01:00:15Z",
 "html_url": "https://example.invalid/runs/9001"}
JSON
  cat > "$work/fixtures/jobs.json" <<'JSON'
{"total_count": 3, "jobs": [
  {"id": 1, "name": "watchdog / collect", "conclusion": "success",
   "started_at": "2026-08-25T01:00:00Z", "completed_at": "2026-08-25T01:00:05Z",
   "steps": [
     {"name": "Report \"could not inspect\" to lifecycle issue", "conclusion": "skipped"}
   ]},
  {"id": 2, "name": "watchdog / diagnose", "conclusion": "success",
   "started_at": "2026-08-25T01:00:05Z", "completed_at": "2026-08-25T01:00:10Z",
   "steps": [
     {"name": "Report \"rate-limited\" to lifecycle issue", "conclusion": "success"},
     {"name": "Report \"diagnose failed\" to lifecycle issue", "conclusion": "skipped"},
     {"name": "Read back diagnose outcome", "conclusion": "success"}
   ]},
  {"id": 3, "name": "watchdog / report-unhandled-failure", "conclusion": "success",
   "started_at": "2026-08-25T01:00:11Z", "completed_at": "2026-08-25T01:00:14Z",
   "steps": [
     {"name": "Determine failed jobs", "conclusion": "success"},
     {"name": "Report unhandled job failure", "conclusion": "skipped"},
     {"name": "Report unhandled job failure to run summary", "conclusion": "skipped"}
   ]}
]}
JSON
  cat > "$work/fixtures/artifact.json" <<'JSON'
[{"type": "rate_limit_event", "status": "rejected", "resetsAt": "2026-08-25T05:00:00Z"},
 {"type": "result", "num_turns": 0, "is_error": true, "subtype": "success",
  "terminal_reason": "api_error", "api_error_status": 429, "result": ""}]
JSON

  # s7: rate-limited diagnose, nothing else wrong -> exits 0, no pipeline-
  # defect issue created or commented.
  run_scenario "$script" '' true
  created="$(grep -c '^issue create' "$work/calls.log" || true)"
  commented="$(grep -c '^issue comment' "$work/calls.log" || true)"
  if [ "$rc" = "0" ] && [ "$created" = "0" ] && [ "$commented" = "0" ]; then
    ok "$tag s7: rate-limited diagnose alone verifies healthy, no pipeline-defect issue"
  else
    fail "$tag s7: expected exit 0 and zero issue create/comment calls; got rc=$rc create=$created comment=$commented"
  fi

  # s8: rate-limited diagnose AND an unrelated red job (collect) -> exits 1
  # for the unrelated reason alone; the suppressed reasons stay silent.
  sed -i 's/"name": "watchdog \/ collect", "conclusion": "success"/"name": "watchdog \/ collect", "conclusion": "failure"/' "$work/fixtures/jobs.json"
  run_scenario "$script" '' true
  created="$(grep -c '^issue create' "$work/calls.log" || true)"
  if [ "$rc" = "1" ] && [ "$created" = "1" ] \
     && grep -q "failed jobs: watchdog / collect" <<<"$out" \
     && ! grep -q "too fast to have done real work" <<<"$out" \
     && ! grep -q "no successful terminal result record" <<<"$out"; then
    ok "$tag s8: rate-limited diagnose plus an unrelated red job fails, and files, for that reason alone"
  else
    fail "$tag s8: expected exit 1 + one issue-create naming only the unrelated red job, got rc=$rc create=$created: $(tail -5 <<<"$out")"
  fi
  sed -i 's/"name": "watchdog \/ collect", "conclusion": "failure"/"name": "watchdog \/ collect", "conclusion": "success"/' "$work/fixtures/jobs.json"

  # s9: rate-limited diagnose AND a stalled RUN duration (ceiling breach) ->
  # exits 1 for the stall alone -- proves the ceiling arm is genuinely
  # unaffected by the floor-arm suppression.
  cat > "$work/fixtures/run.json" <<'JSON'
{"id": 9001, "conclusion": "success", "workflow_id": 777,
 "run_started_at": "2026-08-25T01:00:00Z", "updated_at": "2026-08-25T02:00:00Z",
 "html_url": "https://example.invalid/runs/9001"}
JSON
  run_scenario "$script" '' false
  if [ "$rc" = "1" ] && grep -qE "over the [0-9]+s ceiling" <<<"$out" \
     && ! grep -q "too fast to have done real work" <<<"$out" \
     && ! grep -q "no successful terminal result record" <<<"$out"; then
    ok "$tag s9: a rate-limited diagnose plus a stalled run fails for the stall alone"
  else
    fail "$tag s9: expected exit 1 naming only the ceiling breach, got rc=$rc: $(tail -5 <<<"$out")"
  fi

  # s10: the "Report rate-limited..." step is absent from the jobs response
  # (a degraded/unreadable evidence read, the same real 429 artifact) ->
  # rate_limited resolves to false and the pre-existing checks (floor,
  # missing successful terminal result) still fire -- fails safe, never a
  # silent pass over a run that really was rejected.
  cp "$work/jobs.json.bak_rl" "$work/fixtures/jobs.json"
  cat > "$work/fixtures/run.json" <<'JSON'
{"id": 9001, "conclusion": "success", "workflow_id": 777,
 "run_started_at": "2026-08-25T01:00:00Z", "updated_at": "2026-08-25T01:00:15Z",
 "html_url": "https://example.invalid/runs/9001"}
JSON
  run_scenario "$script" '' false
  if [ "$rc" = "1" ] && grep -q "too fast to have done real work" <<<"$out" \
     && grep -q "no successful terminal result record" <<<"$out"; then
    ok "$tag s10: the rate-limited report step absent from the jobs response fails safe -- pre-existing checks still fire, never a silent pass"
  else
    fail "$tag s10: expected exit 1 with both pre-existing reasons firing, got rc=$rc: $(tail -5 <<<"$out")"
  fi

  mv "$work/run.json.bak_rl" "$work/fixtures/run.json"
  mv "$work/jobs.json.bak_rl" "$work/fixtures/jobs.json"
  mv "$work/artifact.json.bak_rl" "$work/fixtures/artifact.json"

  # ── MF-01: the floor arm must key off THIS run's own diagnose_conclusion,
  # not just the median, against history that still predates the clean path
  # (fixtures/history.json here is the file-top old-shape set: four ~120s
  # agent-bearing runs, median 120s, floor 48s) -- the exact transition
  # window fold(leg-0) flagged: for the first runs after merge, the "last 20
  # successful runs" history is still all agent-bearing.
  cp "$work/fixtures/run.json" "$work/run.json.bak_mf01"
  cp "$work/fixtures/jobs.json" "$work/jobs.json.bak_mf01"
  cp "$work/fixtures/artifact.json" "$work/artifact.json.bak_mf01"

  # s14: a 33s clean-path run (diagnose skipped, pass posted from collect)
  # against the OLD-shape history (floor=48s from that history alone) must
  # still PASS -- the floor arm does not apply when diagnose didn't run.
  sed -i 's/"updated_at": "2026-08-25T01:02:00Z"/"updated_at": "2026-08-25T01:00:33Z"/' "$work/fixtures/run.json"
  cat > "$work/fixtures/jobs.json" <<'JSON'
{"total_count": 3, "jobs": [
  {"id": 1, "name": "watchdog / collect", "conclusion": "success",
   "started_at": "2026-08-25T01:00:03Z", "completed_at": "2026-08-25T01:00:28Z",
   "steps": [
     {"name": "Report \"could not inspect\" to lifecycle issue", "conclusion": "skipped"},
     {"name": "Report \"passed inspection\" to lifecycle issue (empty signal set, no agent)", "conclusion": "success"}
   ]},
  {"id": 2, "name": "watchdog / diagnose", "conclusion": "skipped",
   "started_at": null, "completed_at": null, "steps": []},
  {"id": 3, "name": "watchdog / report-unhandled-failure", "conclusion": "success",
   "started_at": "2026-08-25T01:00:29Z", "completed_at": "2026-08-25T01:00:33Z",
   "steps": [
     {"name": "Determine failed jobs", "conclusion": "success"},
     {"name": "Report unhandled job failure", "conclusion": "skipped"},
     {"name": "Report unhandled job failure to run summary", "conclusion": "skipped"}
   ]}
]}
JSON
  rm -f "$work/fixtures/artifact.json"
  run_scenario "$script" '' false
  if [ "$rc" = "0" ] && ! grep -q "too fast to have done real work" <<<"$out"; then
    ok "$tag s14: a 33s clean-path run against old-shape (agent-bearing) history still passes -- the floor arm is scoped to diagnose having run"
  else
    fail "$tag s14: expected exit 0 with no floor breach, got rc=$rc: $(tail -5 <<<"$out")"
  fi

  # s15: the SAME 33s duration and the SAME old-shape history, but diagnose
  # actually ran (the base fixture's shape) -- must still FAIL the floor,
  # proving MF-01 scoped the exemption to the clean path and did not just
  # widen the floor for everyone.
  cp "$work/jobs.json.bak_mf01" "$work/fixtures/jobs.json"
  cp "$work/artifact.json.bak_mf01" "$work/fixtures/artifact.json"
  run_scenario "$script" '' false
  if [ "$rc" = "1" ] && grep -q "too fast to have done real work" <<<"$out"; then
    ok "$tag s15: the same 33s duration still fails when diagnose actually ran -- the floor exemption never widened"
  else
    fail "$tag s15: expected exit 1 + 'too fast to have done real work', got rc=$rc: $(tail -5 <<<"$out")"
  fi

  mv "$work/run.json.bak_mf01" "$work/fixtures/run.json"
  rm -f "$work/jobs.json.bak_mf01" "$work/artifact.json.bak_mf01"

  # ── specs/058-per-job-minute-floor: the clean-path healthy shape ──────────
  # An inspection whose aggregate signal set is empty now skips diagnose
  # entirely and posts the pass from collect (FR-011). The whole run is
  # collect plus report-unhandled-failure -- ~33s, which the verifier's old
  # 40s absolute floor would have failed as "too fast to have done real
  # work", and which leaves no execution-output artifact and no metrics
  # record because no agent ran. This is a PASSING shape; s12 and s13 below
  # prove the checks it walks past are still load-bearing.
  cp "$work/fixtures/run.json" "$work/run.json.bak_cp"
  cp "$work/fixtures/jobs.json" "$work/jobs.json.bak_cp"
  cp "$work/fixtures/history.json" "$work/history.json.bak_cp"
  mv "$work/fixtures/artifact.json" "$work/artifact.json.bak_cp"

  cat > "$work/fixtures/run.json" <<'JSON'
{"id": 9001, "conclusion": "success", "workflow_id": 777,
 "run_started_at": "2026-08-25T01:00:00Z", "updated_at": "2026-08-25T01:00:33Z",
 "html_url": "https://example.invalid/runs/9001"}
JSON
  # A history of clean-path runs: the median term lands at 13s, so the
  # ABSOLUTE floor is what these scenarios actually exercise.
  cat > "$work/fixtures/history.json" <<'JSON'
{"workflow_runs": [
  {"id": 8001, "run_started_at": "2026-08-24T01:00:00Z", "updated_at": "2026-08-24T01:00:35Z"},
  {"id": 8002, "run_started_at": "2026-08-23T01:00:00Z", "updated_at": "2026-08-23T01:00:33Z"},
  {"id": 8003, "run_started_at": "2026-08-22T01:00:00Z", "updated_at": "2026-08-22T01:00:36Z"},
  {"id": 8004, "run_started_at": "2026-08-21T01:00:00Z", "updated_at": "2026-08-21T01:00:34Z"}
]}
JSON
  cat > "$work/fixtures/jobs.json" <<'JSON'
{"total_count": 3, "jobs": [
  {"id": 1, "name": "watchdog / collect", "conclusion": "success",
   "started_at": "2026-08-25T01:00:03Z", "completed_at": "2026-08-25T01:00:28Z",
   "steps": [
     {"name": "Report \"could not inspect\" to lifecycle issue", "conclusion": "skipped"},
     {"name": "Report \"passed inspection\" to lifecycle issue (empty signal set, no agent)", "conclusion": "success"}
   ]},
  {"id": 2, "name": "watchdog / diagnose", "conclusion": "skipped",
   "started_at": null, "completed_at": null, "steps": []},
  {"id": 3, "name": "watchdog / report-unhandled-failure", "conclusion": "success",
   "started_at": "2026-08-25T01:00:29Z", "completed_at": "2026-08-25T01:00:33Z",
   "steps": [
     {"name": "Determine failed jobs", "conclusion": "success"},
     {"name": "Report unhandled job failure", "conclusion": "skipped"},
     {"name": "Report unhandled job failure to run summary", "conclusion": "skipped"}
   ]}
]}
JSON

  # s11: the clean path verifies healthy and files nothing -- no agent, no
  # execution-output artifact, no metrics record, 33s end to end.
  run_scenario "$script" '' true
  created="$(grep -c '^issue create' "$work/calls.log" || true)"
  if [ "$rc" = "0" ] && [ "$created" = "0" ] \
     && grep -q "diagnose skipped" <<<"$out" \
     && ! grep -q "too fast to have done real work" <<<"$out"; then
    ok "$tag s11: the clean path (diagnose skipped, pass posted from collect) verifies healthy"
  else
    fail "$tag s11: expected exit 0 with no issue filed, got rc=$rc create=$created: $(tail -5 <<<"$out")"
  fi

  # s12 (revised by MF-01): the same clean shape, but 15s -- under what
  # USED to be the re-scaled absolute floor. MF-01 scopes the floor arm to
  # runs where diagnose actually ran, so a clean-path run this fast now
  # passes too; s14/s15 (below the fixtures reset) are what prove the
  # floor still bites an AGENT-BEARING run this fast, so removing it
  # entirely is still caught.
  sed -i 's/"updated_at": "2026-08-25T01:00:33Z"/"updated_at": "2026-08-25T01:00:15Z"/' "$work/fixtures/run.json"
  run_scenario "$script" '' false
  if [ "$rc" = "0" ] && ! grep -q "too fast to have done real work" <<<"$out"; then
    ok "$tag s12: a 15s clean-path run passes -- MF-01 the floor arm does not apply when diagnose was skipped, at any duration"
  else
    fail "$tag s12: expected exit 0 with no floor breach, got rc=$rc: $(tail -5 <<<"$out")"
  fi
  sed -i 's/"updated_at": "2026-08-25T01:00:15Z"/"updated_at": "2026-08-25T01:00:33Z"/' "$work/fixtures/run.json"

  # s13: diagnose skipped and NEITHER of collect's reporters ran -- the run
  # decided something and recorded nothing. A skipped agent is only healthy
  # when the deterministic pass (or the could-not-inspect degradation) was
  # actually posted.
  sed -i 's/{"name": "Report \\"passed inspection\\" to lifecycle issue (empty signal set, no agent)", "conclusion": "success"}/{"name": "Report \\"passed inspection\\" to lifecycle issue (empty signal set, no agent)", "conclusion": "skipped"}/' "$work/fixtures/jobs.json"
  run_scenario "$script" '' false
  if [ "$rc" = "1" ] && grep -q "neither of collect's reporters ran" <<<"$out"; then
    ok "$tag s13: a silent clean path (agent skipped, nothing posted) fails"
  else
    fail "$tag s13: expected exit 1 + 'neither of collect's reporters ran', got rc=$rc: $(tail -5 <<<"$out")"
  fi

  mv "$work/run.json.bak_cp" "$work/fixtures/run.json"
  mv "$work/jobs.json.bak_cp" "$work/fixtures/jobs.json"
  mv "$work/history.json.bak_cp" "$work/fixtures/history.json"
  mv "$work/artifact.json.bak_cp" "$work/fixtures/artifact.json"
}

# ── The real script must pass every scenario ───────────────────────────────
scenarios "$SCRIPT" "real"

# ── Mutations: each fix must be load-bearing (constitution VIII) ───────────
# run_mutation <mutant-path> <tag> <covering-scenario> <description>
# A kill is strict: the mutant must still be VALID bash (an unparseable
# mutant fails every scenario for reasons that prove nothing - an
# independent review caught exactly that: a half-applied sed produced a
# syntax-error mutant whose crash was scored as a kill), and the covering
# scenario must be the ONLY one that goes red - a broader blast radius
# means the mutation, or the harness, is not testing what it claims.
run_mutation() {
  local mutant="$1" tag="$2" covering="$3" description="$4"
  if cmp -s "$SCRIPT" "$mutant"; then
    fail "$tag did not apply - the guard's shape changed; update this harness"
    return
  fi
  if ! bash -n "$mutant" 2>/dev/null; then
    fail "$tag produced an unparseable mutant - its sed no longer matches the script; update this harness"
    return
  fi
  local before=$bad
  scenarios "$mutant" "$tag" > "$work/$tag.log" 2>&1
  bad=$before
  local failed_scenarios
  failed_scenarios="$(grep -oE "\[FAIL\] $tag s[0-9]+" "$work/$tag.log" | grep -oE 's[0-9]+$' | sort -u | tr '\n' ' ')"
  if [ "$failed_scenarios" = "$covering " ]; then
    ok "$tag: $description - exactly $covering went red"
  else
    fail "$tag: expected exactly $covering to fail, got: '${failed_scenarios:-none}' - $(grep "\[FAIL\]" "$work/$tag.log" | head -2 | tr '\n' ' ')"
  fi
}

mut="$work/mutated.sh"

# m1: the run-fetch guard degrades to a pass -> s1 must catch it.
sed 's/{ echo "::error::cannot fetch run $RUN_ID"; exit 2; }/{ echo "::error::cannot fetch run $RUN_ID"; exit 0; }/' \
  "$SCRIPT" > "$mut"
run_mutation "$mut" "m1" "s1" "degrading the run-fetch guard to exit 0 is caught"

# m2: the search-failure guard reverts to read-failure-as-empty (the #167
# shape) -> s5 must catch the duplicate filing. The brackets in the jq
# fragment are escaped: unescaped, sed reads `[0]` as a bracket expression,
# the second expression never matches, and the mutant is the half-applied
# syntax error the strictness above exists to reject.
sed 's/if existing="$(gh issue list/existing="$(gh issue list/; s/--jq '"'"'.\[0\].number \/\/ empty'"'"')"; then/--jq '"'"'.[0].number \/\/ empty'"'"')" || true; if true; then/' \
  "$SCRIPT" > "$mut"
run_mutation "$mut" "m2" "s5" "reverting the search-failure guard files a duplicate again"

# m3 retired (MF-01): it proved the absolute duration floor's 20s clamp
# still bit a fast CLEAN-PATH run (s12) once the median-scaled term alone
# would have let a 15s run pass. MF-01 scopes the whole floor arm --
# clamp included -- to runs where diagnose actually ran, so a clean-path
# run is no longer subject to it at any duration (s12, revised, now
# asserts exactly that); there is no longer a clean-path scenario for
# this specific mutation to be caught by. No replacement mutation: the
# floor arm itself (not just its clamp) is what m4 immediately below,
# and s14/s15 above, already hold load-bearing for the shapes that still
# apply it.

# m4 (spec 058): the skipped-diagnose branch stops requiring that one of
# collect's reporters actually ran, so a run that skipped the agent and said
# nothing at all reads as healthy. s13 must catch it.
sed 's/reason "diagnose was skipped but neither of collect'"'"'s reporters ran — the run decided something and recorded nothing"/note "diagnose was skipped and neither reporter ran"/' \
  "$SCRIPT" > "$mut"
run_mutation "$mut" "m4" "s13" "a skipped agent that recorded nothing must not read as healthy"

echo "Gate 36: 15 scenario(s) x 5 runs + 3 mutation(s); $bad failure(s)."
exit $([ "$bad" -eq 0 ] && echo 0 || echo 1)