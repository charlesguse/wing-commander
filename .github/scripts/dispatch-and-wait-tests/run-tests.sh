#!/usr/bin/env bash
# Gate -- wing-commander-dispatch-and-wait/action.yml's own "Dispatch and
# correlate" shell EXTRACTED and run against a stub `gh` on PATH
# (specs/057-autonomous-board-loop T055), matching this repository's Gate
# 4 discipline: the harness executes the shipped shell itself.
#
# Covers successful correlation, ambiguous/absent correlation (empty
# run-url), poll-budget exhaustion (conclusion: timeout), a rejected
# dispatch call (dispatch-rejected=true, correlation search skipped), and
# the uncorrelated-wait-seconds input's bounded wait being honored.
#
# Lives under .github/scripts/, not beside the composite -- see
# verify-actions-no-gate-scripts.py.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ACTION_YML="$HERE/../../actions/wing-commander-dispatch-and-wait/action.yml"
FAILURES=0

extract_shell() {
  python3 - "$ACTION_YML" <<'PYEOF'
import sys
import yaml

with open(sys.argv[1], encoding="utf-8") as fh:
    doc = yaml.safe_load(fh)

for step in doc["runs"]["steps"]:
    if step.get("id") == "watch":
        sys.stdout.write(step["run"])
        break
else:
    sys.exit("no step with id: watch found in " + sys.argv[1])
PYEOF
}

SCRIPT="$(mktemp)"
STUBDIR="$(mktemp -d)"
trap 'rm -f "$SCRIPT"; rm -rf "$STUBDIR"' EXIT
extract_shell > "$SCRIPT"

# GH_STUB_MODE selects the fake `gh`'s behavior for this invocation:
#   found     -- one matching run, completes with conclusion=success
#   ambiguous -- two matching runs
#   absent    -- no matching runs, ever (exhausts POLL_ATTEMPTS)
#   timeout   -- one matching run, never reaches status=completed
#   rejected  -- `gh workflow run` itself fails; correlation search never runs
cat > "$STUBDIR/gh" <<'GHSTUB'
#!/usr/bin/env bash
set -uo pipefail
if [ "$1" = "workflow" ] && [ "$2" = "run" ]; then
  if [ "$GH_STUB_MODE" = "rejected" ]; then
    exit 1
  fi
  exit 0
fi
if [ "$1" = "run" ] && [ "$2" = "list" ]; then
  case "$GH_STUB_MODE" in
    found|timeout)
      echo '[{"databaseId": 42, "displayTitle": "release 1.2.3 [attempt:tok-1]", "createdAt": "2999-01-01T00:00:00Z", "url": "https://example/runs/42"}]'
      ;;
    ambiguous)
      echo '[{"databaseId": 42, "displayTitle": "release 1.2.3 [attempt:tok-1]", "createdAt": "2999-01-01T00:00:00Z", "url": "https://example/runs/42"},{"databaseId": 43, "displayTitle": "release 1.2.4 [attempt:tok-1]", "createdAt": "2999-01-01T00:00:01Z", "url": "https://example/runs/43"}]'
      ;;
    absent)
      echo '[]'
      ;;
  esac
  exit 0
fi
if [ "$1" = "run" ] && [ "$2" = "view" ]; then
  if [[ "$*" == *"--json status"* ]]; then
    if [ "$GH_STUB_MODE" = "timeout" ]; then
      echo "in_progress"
    else
      echo "completed"
    fi
    exit 0
  fi
  if [[ "$*" == *"--json conclusion"* ]]; then
    echo "success"
    exit 0
  fi
fi
exit 1
GHSTUB
chmod +x "$STUBDIR/gh"

run_case() {
  local name="$1" mode="$2" expect_url_present="$3" expect_conclusion="$4" \
        expect_dispatch_rejected="$5" expect_correlation="$6" expect_run_id_present="$7" \
        uncorrelated_wait="${8:-0}"

  OUT_FILE="$(mktemp)"
  if ! PATH="$STUBDIR:$PATH" GH_STUB_MODE="$mode" GH_TOKEN=x \
      WORKFLOW_FILE=release.yml WORKFLOW_INPUTS='{}' ATTEMPT_TOKEN=tok-1 \
      POLL_ATTEMPTS=2 POLL_INTERVAL_SECONDS=0 WAIT_ATTEMPTS=2 \
      UNCORRELATED_WAIT_SECONDS="$uncorrelated_wait" \
      GITHUB_OUTPUT="$OUT_FILE" bash "$SCRIPT"; then
    echo "::error::[$name] the extracted shell exited non-zero"
    FAILURES=$((FAILURES + 1))
    rm -f "$OUT_FILE"
    return
  fi

  got_url="$(grep '^run-url=' "$OUT_FILE" | cut -d= -f2-)"
  got_conclusion="$(grep '^conclusion=' "$OUT_FILE" | cut -d= -f2-)"
  got_dispatch_rejected="$(grep '^dispatch-rejected=' "$OUT_FILE" | cut -d= -f2-)"
  got_correlation="$(grep '^correlation=' "$OUT_FILE" | cut -d= -f2-)"
  got_run_id="$(grep '^correlated-run-id=' "$OUT_FILE" | cut -d= -f2-)"
  got_request_time="$(grep '^request-time=' "$OUT_FILE" | cut -d= -f2-)"
  rm -f "$OUT_FILE"

  url_ok="false"
  if [ "$expect_url_present" = "true" ] && [ -n "$got_url" ]; then url_ok="true"; fi
  if [ "$expect_url_present" = "false" ] && [ -z "$got_url" ]; then url_ok="true"; fi

  run_id_ok="false"
  if [ "$expect_run_id_present" = "true" ] && [ -n "$got_run_id" ]; then run_id_ok="true"; fi
  if [ "$expect_run_id_present" = "false" ] && [ -z "$got_run_id" ]; then run_id_ok="true"; fi

  if [ "$url_ok" = "true" ] && [ "$got_conclusion" = "$expect_conclusion" ] \
      && [ "$got_dispatch_rejected" = "$expect_dispatch_rejected" ] \
      && [ "$got_correlation" = "$expect_correlation" ] \
      && [ "$run_id_ok" = "true" ] && [ -n "$got_request_time" ]; then
    echo "[ok] $name: run-url=${got_url:-<empty>} conclusion=${got_conclusion:-<empty>} dispatch-rejected=$got_dispatch_rejected correlation=$got_correlation correlated-run-id=${got_run_id:-<empty>} request-time=$got_request_time"
  else
    echo "::error::[$name] expected url-present=$expect_url_present conclusion=$expect_conclusion dispatch-rejected=$expect_dispatch_rejected correlation=$expect_correlation run-id-present=$expect_run_id_present request-time=<non-empty>, got url=${got_url:-<empty>} conclusion=${got_conclusion:-<empty>} dispatch-rejected=${got_dispatch_rejected:-<empty>} correlation=${got_correlation:-<empty>} run-id=${got_run_id:-<empty>} request-time=${got_request_time:-<empty>}"
    FAILURES=$((FAILURES + 1))
  fi
}

run_wait_honored_case() {
  local name="waits configured uncorrelated-wait-seconds" wait_seconds=2

  OUT_FILE="$(mktemp)"
  start_epoch="$(date -u +%s)"
  if ! PATH="$STUBDIR:$PATH" GH_STUB_MODE=absent GH_TOKEN=x \
      WORKFLOW_FILE=release.yml WORKFLOW_INPUTS='{}' ATTEMPT_TOKEN=tok-1 \
      POLL_ATTEMPTS=2 POLL_INTERVAL_SECONDS=0 WAIT_ATTEMPTS=2 \
      UNCORRELATED_WAIT_SECONDS="$wait_seconds" \
      GITHUB_OUTPUT="$OUT_FILE" bash "$SCRIPT"; then
    echo "::error::[$name] the extracted shell exited non-zero"
    FAILURES=$((FAILURES + 1))
    rm -f "$OUT_FILE"
    return
  fi
  end_epoch="$(date -u +%s)"
  rm -f "$OUT_FILE"

  elapsed=$((end_epoch - start_epoch))
  if [ "$elapsed" -ge "$wait_seconds" ]; then
    echo "[ok] $name: elapsed=${elapsed}s >= ${wait_seconds}s"
  else
    echo "::error::[$name] expected at least ${wait_seconds}s elapsed, got ${elapsed}s"
    FAILURES=$((FAILURES + 1))
  fi
}

run_case "successful correlation" found true success false found true
run_case "ambiguous correlation" ambiguous false "" false ambiguous false
run_case "absent correlation" absent false "" false not-observed false
run_case "poll-budget exhaustion" timeout true timeout false found true
run_case "dispatch-rejected" rejected false "" true not-observed false
run_wait_honored_case

echo "wing-commander-dispatch-and-wait tests: $FAILURES failure(s)."
[ "$FAILURES" -eq 0 ]
