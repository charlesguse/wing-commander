#!/usr/bin/env bash
# .github/actions/_shared/fetch-job-logs.sh
#
# The one place that fetches an inspected run's job list and job logs
# (specs/101-read-only-gh-grants/contracts/diagnose-staged-logs.md). The
# watchdog's `collect-step-summary` collector (which scans the logs for
# sentinels) and the diagnose job's `Stage failed-job logs` step (which hands
# the failed jobs' logs to a read-only agent as files) both call it, so a
# second copy of this fetch never has to be kept in step with the first
# (CLAUDE.md "Shared logic has exactly one home").
#
# Invoke with
#   GH_TOKEN=<github.token> RUN_ID=<run id> bash fetch-job-logs.sh <out-dir>
# -- `bash file`, never the file itself, so its executable bit is never
# load-bearing. GITHUB_REPOSITORY is the runner's own variable. The token must
# carry actions: read, which the App token does not have (docs/setup.md).
#
# Writes into <out-dir>:
#   jobs.json        every job of the run, as one JSON array ([] when the
#                    listing failed)
#   <job_id>.log     the raw log of one job, written ONLY when the read
#                    succeeded and returned a non-empty body. An error message
#                    or an empty body is never written as log content, so a
#                    log file that exists is always real evidence.
#   reason.txt       only when the outcome is `failed`: `jobs-list` or
#                    `log-read`
# Jobs concluded `skipped` or `cancelled` are not fetched: they owe no log
# (spec 024 FR-004/FR-005).
#
# The final stdout line is `ok` or `failed`. This script returns 0 always;
# failure travels in that line so a caller keeps its own errexit semantics.
# Exactly one bounded retry (after `sleep 10`) is spent per invocation, not per
# job: logs for a just-completed job can lag the jobs API by a few seconds, but
# a systematic failure (a token without actions: read 403s every job) must not
# burn N x 10s.
set -uo pipefail

OUT_DIR="${1:-}"
if [ -z "$OUT_DIR" ]; then
  echo "fetch-job-logs.sh: usage: fetch-job-logs.sh <out-dir>" >&2
  echo "failed"
  exit 0
fi
mkdir -p "$OUT_DIR"
rm -f "$OUT_DIR/reason.txt"

failed=0
# Captured via a direct pipeline with `|| rc=` (never a bare $(...), whose own
# PIPESTATUS would only report jq's exit code) so a failed listing is told
# apart from a legitimately empty one.
jobs_rc=0
gh api "repos/$GITHUB_REPOSITORY/actions/runs/${RUN_ID:-}/jobs" --paginate --jq '.jobs[]' 2>/dev/null | jq -s '.' > "$OUT_DIR/jobs.json" || jobs_rc="${PIPESTATUS[0]}"
[ -s "$OUT_DIR/jobs.json" ] || printf '[]' > "$OUT_DIR/jobs.json"
if [ "$jobs_rc" != "0" ]; then
  printf 'jobs-list' > "$OUT_DIR/reason.txt"
  echo "failed"
  exit 0
fi

retried=0
fetch_one() {
  local id="$1" rc=0
  gh api "repos/$GITHUB_REPOSITORY/actions/jobs/$id/logs" > "$OUT_DIR/$id.log" 2>/dev/null || rc=$?
  if [ "$rc" != "0" ] && [ "$retried" = "0" ]; then
    retried=1
    sleep 10
    rc=0
    gh api "repos/$GITHUB_REPOSITORY/actions/jobs/$id/logs" > "$OUT_DIR/$id.log" 2>/dev/null || rc=$?
  fi
  if [ "$rc" != "0" ] || [ ! -s "$OUT_DIR/$id.log" ]; then
    rm -f "$OUT_DIR/$id.log"
    return 1
  fi
  return 0
}

for job_id in $(jq -r '.[]?.id // empty' "$OUT_DIR/jobs.json"); do
  conclusion="$(jq -r --arg id "$job_id" '.[] | select((.id|tostring) == $id) | .conclusion // "in_progress"' "$OUT_DIR/jobs.json")"
  case "$conclusion" in
    skipped|cancelled) continue ;;
  esac
  fetch_one "$job_id" || failed=1
done

if [ "$failed" != "0" ]; then
  printf 'log-read' > "$OUT_DIR/reason.txt"
  echo "failed"
else
  echo "ok"
fi
exit 0
