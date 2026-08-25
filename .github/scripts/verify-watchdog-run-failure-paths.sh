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
  failed_scenarios="$(grep -oE "\[FAIL\] $tag s[0-9]" "$work/$tag.log" | grep -oE 's[0-9]$' | sort -u | tr '\n' ' ')"
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

echo "Gate 36: 6 scenario(s) x 3 runs + 2 mutation(s); $bad failure(s)."
exit $([ "$bad" -eq 0 ] && echo 0 || echo 1)