#!/usr/bin/env bash
# Deterministic verification that a completed watchdog (stage 8) run actually
# did its job. No LLM involved — every check reads the Actions API or a run
# artifact.
#
# Why this exists: a watchdog run can be GREEN and still have failed. The
# agent steps inside watchdog.yml run with continue-on-error: true, so a
# crashed diagnose agent never turns its job red (observed: run 30136381350,
# agent died with "non-human actor" in 5s, run stayed green), and the jobs
# API reports the step's POST-continue-on-error conclusion (success), so the
# crash is invisible in job/step conclusions of the agent step itself. What
# IS visible is the workflow's own conditional reporting steps — they encode
# the true outcome:
#   - diagnose step 'Report "diagnose failed" to lifecycle issue' runs (not
#     skipped) exactly when the agent crashed;
#   - report-unhandled-failure's conditional steps run exactly when its
#     "Determine failed jobs" gate found an internal failure;
#   - collect's 'Report "could not inspect"...' runs exactly when evidence
#     gathering failed.
# This script turns those into hard pass/fail, plus a runtime-anomaly band
# derived from the run's own workflow history.
#
# Usage (env vars):
#   RUN_ID        (required) the watchdog run to verify
#   GH_TOKEN      (required) token with actions:read (+ issues:write if
#                 CREATE_ISSUE=true)
#   REPO          (required) owner/name
#   CREATE_ISSUE  "true" to file/append a pipeline-defect issue on failure
#                 (default "false" — report-only, for tests)
#   GITHUB_STEP_SUMMARY  honored when set
#
# Exit code: 0 = verified healthy; 1 = verification FAILED (caller's job
# turns red); 2 = script could not verify (API errors) — also red, because
# "could not verify" must never read as "verified".

set -uo pipefail

fail_reasons=()
note() { echo "::notice::verify-watchdog: $1"; }
reason() { fail_reasons+=("$1"); echo "::error::verify-watchdog: $1"; }

api() { gh api "repos/$REPO/$1"; }

run_json="$(api "actions/runs/$RUN_ID")" || { echo "::error::cannot fetch run $RUN_ID"; exit 2; }
conclusion="$(jq -r '.conclusion' <<<"$run_json")"
workflow_id="$(jq -r '.workflow_id' <<<"$run_json")"
started="$(jq -r '.run_started_at' <<<"$run_json")"
updated="$(jq -r '.updated_at' <<<"$run_json")"
run_url="$(jq -r '.html_url' <<<"$run_json")"
duration=$(( $(date -d "$updated" +%s) - $(date -d "$started" +%s) ))
note "run $RUN_ID conclusion=$conclusion duration=${duration}s"

# ── Check 1: honest conclusion ──────────────────────────────────────────────
if [ "$conclusion" != "success" ]; then
  reason "run conclusion is '$conclusion', not success"
fi

# startup_failure (and any zero-job run) is its own shape: GitHub registers
# the run with no jobs, no logs (/logs 404s), no artifacts — none of the
# evidence the checks below read will ever exist, so verdict now.
if [ "$conclusion" = "startup_failure" ] || \
   [ "$(api "actions/runs/$RUN_ID/jobs?per_page=1" | jq -r '.total_count')" = "0" ]; then
  reason "run never started (startup_failure / zero jobs) — GitHub could not even begin it; no job-level evidence exists"
fi
# (The step/artifact checks below no-op harmlessly on a zero-job run; the
# two reasons above already fail it.)

# ── Check 2: runtime anomaly vs. this workflow's own successful history ────
# Median of the last 20 successful runs (excluding this one). Bounds are
# deliberately loose — this gates issue creation, and a run with real
# Findings legitimately takes several times a quiet run (triage/act
# matrices do real work) — but they still catch the two observed shapes:
# an instant death (agent crashed in seconds) and a multi-minute stall
# (diagnose hung 44 minutes; watchdog.yml previously had no timeouts).
hist="$(api "actions/workflows/$workflow_id/runs?status=success&per_page=21" \
  | jq -r --arg id "$RUN_ID" \
      '.workflow_runs[] | select((.id|tostring) != $id)
       | ((.updated_at | fromdateiso8601) - (.run_started_at | fromdateiso8601))' \
  | head -20)" || hist=""
count="$(wc -l <<<"$hist" | tr -d ' ')"
if [ -n "$hist" ] && [ "$count" -ge 3 ]; then
  median="$(sort -n <<<"$hist" | awk -v n="$count" 'NR == int((n+1)/2)')"
  # Clamps per the 2026-07-24 run audit: floor 40s sits 37% under the
  # slowest-to-die observed crash shapes' healthy floor (64s min genuine
  # success) while staying above collect-crash (27-33s) and instant-death
  # territory; ceiling 900s is ~7x the worst healthy findings-bearing run
  # (128s) yet catches the observed 2689s hang three times over.
  floor=$(( median * 2 / 5 )); [ "$floor" -lt 40 ] && floor=40
  ceiling=$(( median * 6 )); [ "$ceiling" -lt 900 ] && ceiling=900
  note "duration band from $count runs: median=${median}s floor=${floor}s ceiling=${ceiling}s"
  if [ "$duration" -lt "$floor" ]; then
    reason "run finished in ${duration}s — under the ${floor}s floor (median ${median}s); too fast to have done real work"
  elif [ "$duration" -gt "$ceiling" ]; then
    reason "run took ${duration}s — over the ${ceiling}s ceiling (median ${median}s); something stalled"
  fi
else
  note "fewer than 3 prior successful runs; skipping the duration band"
fi

# ── Checks 3-6: step-level truth in the conditional reporting steps ─────────
jobs_json="$(api "actions/runs/$RUN_ID/jobs?per_page=100")" || { echo "::error::cannot fetch jobs"; exit 2; }

# step <job-name-suffix> <step-name> -> conclusion (empty if job/step absent).
# Job display names carry the reusable-workflow prefix ("watchdog / diagnose");
# match on suffix so this works for stage 8, 8b, and direct calls alike.
step() {
  jq -r --arg j "$1" --arg s "$2" \
    '[.jobs[] | select(.name == $j or (.name | endswith("/ " + $j)))
      | .steps[] | select(.name == $s) | .conclusion] | first // empty' <<<"$jobs_json"
}

# Any job red at all (belt-and-braces; conclusion above should already say).
failed_jobs="$(jq -r '[.jobs[] | select(.conclusion != null and .conclusion != "success" and .conclusion != "skipped") | .name] | join(", ")' <<<"$jobs_json")"
[ -n "$failed_jobs" ] && reason "failed jobs: $failed_jobs"

# Diagnose-job duration ceiling — much tighter than the run-level band,
# because this job's cost is bounded by --max-turns, not by finding count
# (healthy max observed 74s). This is the check that would have flagged the
# 44-minute hang at the 5-minute mark.
d_secs="$(jq -r '[.jobs[] | select(.name == "diagnose" or (.name | endswith("/ diagnose")))
  | select(.started_at != null and .completed_at != null)
  | ((.completed_at | fromdateiso8601) - (.started_at | fromdateiso8601))] | first // empty' <<<"$jobs_json")"
if [ -n "$d_secs" ] && [ "$d_secs" -gt 300 ]; then
  reason "the diagnose job ran ${d_secs}s (normal is under 75s; hard ceiling 300s) — the agent stalled"
fi

# 3 + 4 only apply when the diagnose job actually ran (it is skipped when
# collect could not gather evidence — check 5 owns that case).
diagnose_conclusion="$(jq -r '[.jobs[] | select(.name == "diagnose" or (.name | endswith("/ diagnose"))) | .conclusion] | first // empty' <<<"$jobs_json")"
if [ -n "$diagnose_conclusion" ] && [ "$diagnose_conclusion" != "skipped" ]; then
  # 3. The diagnose agent crashed (continue-on-error hid it from the job).
  c="$(step diagnose 'Report "diagnose failed" to lifecycle issue')"
  if [ -n "$c" ] && [ "$c" != "skipped" ]; then
    reason "the diagnose agent FAILED (its 'diagnose failed' reporter ran, conclusion=$c) — the inspected run was never actually inspected"
  fi
  # 4. The read-back that parses the agent's structured output must have run.
  c="$(step diagnose 'Read back diagnose outcome')"
  if [ "$c" != "success" ]; then
    reason "diagnose read-back step conclusion is '${c:-absent}' — the agent's output was never validated"
  fi
fi

# 5. Evidence collection degraded to "could not inspect".
c="$(step collect 'Report "could not inspect" to lifecycle issue')"
if [ -n "$c" ] && [ "$c" != "skipped" ]; then
  reason "collect could not gather evidence (its 'could not inspect' reporter ran)"
fi

# 6. The internal safety net fired: something inside this green run failed.
for s in 'Report unhandled job failure' 'Report unhandled job failure to run summary'; do
  c="$(step report-unhandled-failure "$s")"
  if [ -n "$c" ] && [ "$c" != "skipped" ]; then
    reason "the unhandled-failure safety net fired ('$s' ran) — an internal job/step failed inside this run"
  fi
done
c="$(step report-unhandled-failure 'Determine failed jobs')"
if [ -n "$c" ] && [ "$c" != "success" ]; then
  reason "the safety net's own gate did not run cleanly (conclusion=$c) — failures could pass unreported"
fi

# ── Check 7: the diagnose output itself is real ─────────────────────────────
# Scoped to the OUTPUT ARTIFACT only, never the job log: the prompt is
# echoed verbatim into job logs, so grepping a log for prompt-adjacent text
# false-positives on every run.
tmpdir="$(mktemp -d)"
if gh run download "$RUN_ID" -R "$REPO" -n claude-execution-output-diagnose -D "$tmpdir" 2>/dev/null; then
  out="$tmpdir/claude-execution-output.json"
  if [ -f "$out" ]; then
    # "Found nothing" needs a real, successful terminal result record: an
    # empty log ('[]'), a missing record, is_error=true, or an error
    # subtype (error_max_turns, error_during_execution) all mean the run
    # was never truly inspected — observed live as run 30134852122 posting
    # "passed inspection" over an artifact that was literally '[]'.
    # NB: jq's // treats false like null, so `.is_error // true` would turn
    # a healthy is_error=false into true — compare directly instead.
    if ! jq -e '([.[] | select(.type=="result")] | last) as $r
        | $r != null and $r.is_error == false and $r.subtype == "success"' \
        "$out" >/dev/null 2>&1; then
      reason "diagnose execution log has no successful terminal result record (empty output, is_error, or an error subtype) — the agent never produced a real verdict"
    fi
    # Legacy fabrication tripwire (the old prompt's example locator).
    if grep -aq 'WebFetch denied 4 times across turns 12,15,19,22' "$out"; then
      reason "diagnose output contains the old prompt's example locator — fabricated evidence"
    fi
  fi
elif [ -n "$diagnose_conclusion" ] && [ "$diagnose_conclusion" != "skipped" ]; then
  reason "diagnose ran but left no execution-output artifact — the agent crashed before writing output, or the runner was hard-killed; no forensic record exists"
else
  note "no diagnose execution-output artifact (diagnose never ran)"
fi
rm -rf "$tmpdir"

# ── Check 8: crash signatures in the diagnose job log (backstop) ────────────
# The jobs API cannot see a crash inside a continue-on-error step (it
# reports the post-rescue conclusion), and the read-back logic that encodes
# the truth has regressed before. Grep the raw log for the crash signatures
# observed to date. A 404 means GitHub never persisted the log (seen on
# force-killed jobs) — flagged, never treated as a pass.
diagnose_job_id="$(jq -r '[.jobs[] | select(.name == "diagnose" or (.name | endswith("/ diagnose"))) | .id] | first // empty' <<<"$jobs_json")"
if [ -n "$diagnose_job_id" ] && [ "$diagnose_conclusion" != "skipped" ]; then
  if dlog="$(api "actions/jobs/$diagnose_job_id/logs" 2>/dev/null)"; then
    if printf '%s' "$dlog" | grep -aEq '##\[error\]Action failed with error|SDK execution error|Workflow initiated by non-human actor|json-schema is not valid JSON'; then
      reason "diagnose job log carries an agent crash signature that continue-on-error hid from every API conclusion"
    fi
  else
    note "diagnose job log unavailable (404) — crash-signature check could not run"
  fi
fi

# ── Verdict ─────────────────────────────────────────────────────────────────
summary() { [ -n "${GITHUB_STEP_SUMMARY:-}" ] && echo "$1" >> "$GITHUB_STEP_SUMMARY"; echo "$1"; }

if [ "${#fail_reasons[@]}" -eq 0 ]; then
  summary "✅ **watchdog run [$RUN_ID]($run_url) verified healthy** — conclusion, duration (${duration}s), step-level outcomes, and diagnose output all check out."
  exit 0
fi

summary "❌ **watchdog run [$RUN_ID]($run_url) FAILED deterministic verification** (${#fail_reasons[@]} reason(s)):"
for r in "${fail_reasons[@]}"; do summary "- $r"; done

if [ "${CREATE_ISSUE:-false}" = "true" ]; then
  title="watchdog-verify: stage 8 run failed deterministic verification"
  body="🐕‍🦺 **Watchdog verifier** — run [$RUN_ID]($run_url) failed verification:"$'\n'
  for r in "${fail_reasons[@]}"; do body+="- $r"$'\n'; done
  body+=$'\n'"_Filed automatically by the deterministic stage-8b verifier._"
  # The dedup search's failure is its own outcome, never "no issue exists":
  # reading a failed search as an empty result is exactly what made settle
  # file a duplicate issue every day (#167), and this arm shipped with the
  # same shape (#169). On search failure, skip filing - the verification
  # failure above still turns the caller red, and a skipped filing is
  # recoverable while a duplicate issue is noise someone must triage.
  if existing="$(gh issue list -R "$REPO" --state open --label pipeline-defect \
    --search "\"$title\" in:title" --json number --jq '.[0].number // empty')"; then
    if [ -n "$existing" ]; then
      gh issue comment "$existing" -R "$REPO" --body "$body" \
        && note "appended to existing issue #$existing"
    else
      gh issue create -R "$REPO" --title "$title" --label pipeline-defect --body "$body" \
        && note "created pipeline-defect issue"
    fi
  else
    echo "::error::verify-watchdog: the pipeline-defect issue search FAILED - not filing, to avoid creating a duplicate of an issue the search could not see (#167). The verification failure above still stands."
  fi
fi

exit 1
