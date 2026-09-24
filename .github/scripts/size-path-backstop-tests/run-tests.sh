#!/usr/bin/env bash
# Gate -- wing-commander-size-path-backstop/action.yml's own "Measure
# file/line counts against the threshold" shell EXTRACTED and run against
# fixtures (specs/057-autonomous-board-loop T022), matching this
# repository's Gate 4 discipline (auto-update-spec-kit-tests): the harness
# executes the shipped shell itself, so it cannot drift from the composite
# the way a hand-copied fixture could.
#
# Covers under/over threshold independently by files and by lines,
# parameterized rather than hardcoding either caller's own numbers
# (research.md D26) -- pr-conversation.yml's 3/40 and board-loop.yml's own,
# larger, board-specific thresholds are both exercised here as plain
# max-files/max-lines arguments, not literals baked into this script.
#
# WHY THIS LIVES UNDER .github/scripts/ AND NOT BESIDE THE COMPOSITE
# ------------------------------------------------------------------
# wc_gate_registry.py discovers gates under .github/scripts/ ONLY
# (SCRIPTS_DIR), so a run-tests.sh under .github/actions/<composite>/tests/
# is invisible to BOTH verify-gate-wiring.py and run-local-gates.py: CI's
# own lint-workflows.yml step still ran it, but `python
# .github/scripts/run-local-gates.py` -- the suite CLAUDE.md's "Before
# pushing" section tells every contributor to trust -- silently did not.
# T062 caught that. wing-commander-stage-findings' own harness already sets
# the precedent this file follows (.github/scripts/stage-findings-tests/).
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ACTION_YML="$HERE/../../actions/wing-commander-size-path-backstop/action.yml"
FAILURES=0

extract_shell() {
  python3 - "$ACTION_YML" <<'PYEOF'
import sys
import yaml

with open(sys.argv[1], encoding="utf-8") as fh:
    doc = yaml.safe_load(fh)

for step in doc["runs"]["steps"]:
    if step.get("id") == "measure":
        sys.stdout.write(step["run"])
        break
else:
    sys.exit("no step with id: measure found in " + sys.argv[1])
PYEOF
}

SCRIPT="$(mktemp)"
trap 'rm -f "$SCRIPT" "$OUT_FILE"' EXIT
extract_shell > "$SCRIPT"

run_case() {
  local name="$1" file_changes="$2" max_files="$3" max_lines="$4" \
        expect_over="$5" expect_files="$6" expect_lines="$7"

  OUT_FILE="$(mktemp)"
  if ! FILE_CHANGES="$file_changes" MAX_FILES="$max_files" MAX_LINES="$max_lines" \
      GITHUB_OUTPUT="$OUT_FILE" bash "$SCRIPT"; then
    echo "::error::[$name] the extracted shell exited non-zero"
    FAILURES=$((FAILURES + 1))
    return
  fi

  got_over="$(grep '^over-threshold=' "$OUT_FILE" | cut -d= -f2)"
  got_files="$(grep '^measured-files=' "$OUT_FILE" | cut -d= -f2)"
  got_lines="$(grep '^measured-lines=' "$OUT_FILE" | cut -d= -f2)"

  ok=true
  [ "$got_over" = "$expect_over" ] || ok=false
  [ "$got_files" = "$expect_files" ] || ok=false
  [ "$got_lines" = "$expect_lines" ] || ok=false

  if [ "$ok" = "true" ]; then
    echo "[ok] $name: over-threshold=$got_over measured-files=$got_files measured-lines=$got_lines"
  else
    echo "::error::[$name] expected over-threshold=$expect_over files=$expect_files lines=$expect_lines, got over-threshold=$got_over files=$got_files lines=$got_lines"
    FAILURES=$((FAILURES + 1))
  fi
}

ONE_FILE_SMALL_DIFF='[{"path": "a.txt", "diff": "--- a/a.txt\n+++ b/a.txt\n@@ -1 +1 @@\n-old\n+new\n"}]'
FOUR_FILES='[{"path":"a.txt","diff":"+x\n"},{"path":"b.txt","diff":"+x\n"},{"path":"c.txt","diff":"+x\n"},{"path":"d.txt","diff":"+x\n"}]'
BIG_DIFF_ONE_FILE="$(python3 -c '
import json
lines = "\n".join("+line{0}".format(i) for i in range(50))
print(json.dumps([{"path": "a.txt", "diff": lines}]))
')"

run_case "under threshold (default 3/40)" "$ONE_FILE_SMALL_DIFF" 3 40 false 1 2
run_case "over threshold by files (default 3/40)" "$FOUR_FILES" 3 40 true 4 4
run_case "over threshold by lines (default 3/40)" "$BIG_DIFF_ONE_FILE" 3 40 true 1 50
run_case "under threshold, board-loop's own larger thresholds" "$FOUR_FILES" 10 100 false 4 4
run_case "over threshold, board-loop's own larger thresholds" "$BIG_DIFF_ONE_FILE" 10 40 true 1 50

echo "wing-commander-size-path-backstop tests: $FAILURES failure(s)."
[ "$FAILURES" -eq 0 ]
