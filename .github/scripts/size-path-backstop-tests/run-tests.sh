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
# The formula's one home is .github/scripts/size-path-measure.sh (#734/
# #850); the composite runs it from $GITHUB_ACTION_PATH, set here to the
# composite's own directory as the runner sets it. The second half runs
# pr-conversation.yml's "Compute confirmation requirements" step, the
# script's other caller, against a fixture of classified legs: it must
# re-route exactly the over-threshold small-unrelated-change legs, quote
# the measured counts, and leave every other leg as classified.
#
# Lives under .github/scripts/, not beside the composite -- see
# verify-actions-no-gate-scripts.py.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ACTION_DIR="$HERE/../../actions/wing-commander-size-path-backstop"
ACTION_YML="$ACTION_DIR/action.yml"
PR_CONVERSATION_YML="$HERE/../../workflows/pr-conversation.yml"
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

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
# Every temp path from here on, ours or a step's, lands in the trapped
# directory -- see run-local-gates.py's TEMP FILES.
export TMPDIR="$WORK/wc-tmp"; mkdir -p "$TMPDIR"
SCRIPT="$(mktemp)"
extract_shell > "$SCRIPT"

run_case() {
  local name="$1" file_changes="$2" max_files="$3" max_lines="$4" \
        expect_over="$5" expect_files="$6" expect_lines="$7"

  OUT_FILE="$(mktemp)"
  if ! FILE_CHANGES="$file_changes" MAX_FILES="$max_files" MAX_LINES="$max_lines" \
      GITHUB_ACTION_PATH="$ACTION_DIR" GITHUB_OUTPUT="$OUT_FILE" bash "$SCRIPT"; then
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

# --- pr-conversation.yml's per-leg backstop (#734/#850) -----------------
CONFIRM_SCRIPT="$(mktemp)"
python3 - "$PR_CONVERSATION_YML" > "$CONFIRM_SCRIPT" <<'PYEOF'
import sys
import yaml

with open(sys.argv[1], encoding="utf-8") as fh:
    doc = yaml.safe_load(fh)

for step in doc["jobs"]["classify-and-announce"]["steps"]:
    if step.get("id") == "confirm":
        sys.stdout.write(step["run"])
        break
else:
    sys.exit("no step with id: confirm in classify-and-announce of " + sys.argv[1])
PYEOF

# The step runs from the workspace, where the pipeline checkout sits at
# .wing-commander-pipeline; this repository is that checkout here.
ln -s "$(cd "$HERE/../../.." && pwd)" "$WORK/.wing-commander-pipeline"
mkdir -p "$WORK/tmp"
python3 - "$WORK/tmp/classifications-raw.json" "$ONE_FILE_SMALL_DIFF" "$FOUR_FILES" "$BIG_DIFF_ONE_FILE" <<'PYEOF'
import json
import sys

out, small, four, big = sys.argv[1:]
legs = [
    {"category": "small-unrelated-change", "summary": "tiny",
     "planned-action": "open a small PR",
     "drafted-content": {"pr-title": "Tiny", "pr-body": "b",
                         "file-changes": json.loads(small)}},
    {"category": "in-scope-change", "summary": "fold me",
     "planned-action": "fold into tasks.md"},
    {"category": "small-unrelated-change", "summary": "four files",
     "planned-action": "open a small PR",
     "drafted-content": {"pr-title": "Four", "pr-body": "",
                         "file-changes": json.loads(four)}},
    {"category": "small-unrelated-change", "summary": "fifty lines",
     "planned-action": "open a small PR",
     "drafted-content": {"pr-title": "", "pr-body": "body",
                         "file-changes": json.loads(big)}},
    {"category": "small-unrelated-change", "summary": "no drafted content",
     "planned-action": "open a small PR"},
]
with open(out, "w", encoding="utf-8") as fh:
    json.dump(legs, fh)
PYEOF

CONFIRM_OUT="$WORK/out"
: > "$CONFIRM_OUT"
if ! (cd "$WORK" && RUNNER_TEMP="$WORK/tmp" GITHUB_OUTPUT="$CONFIRM_OUT" \
      CONFIRM_CATEGORIES="" CONFIRM_ENVIRONMENT="" PR_NUMBER=1 SPEC_DIR=specs/001-x \
      GH_TOKEN=unused bash "$CONFIRM_SCRIPT"); then
  echo "::error::[pr-conversation confirm step] the extracted shell exited non-zero"
  FAILURES=$((FAILURES + 1))
else
  if python3 - "$WORK/tmp/classifications.json" <<'PYEOF'
import json
import sys

legs = {leg["id"]: leg for leg in json.load(open(sys.argv[1], encoding="utf-8"))}
problems = []

def expect(cond, what):
    if not cond:
        problems.append(what)

expect(legs["leg-0"]["category"] == "small-unrelated-change",
       "leg-0 (1 file, 2 lines) must stay small-unrelated-change")
expect(legs["leg-0"]["drafted-content"]["pr-title"] == "Tiny",
       "leg-0's drafted content must be untouched")
expect(legs["leg-1"]["category"] == "in-scope-change",
       "leg-1 (in-scope-change) must be untouched")
for leg_id, files, lines, title in (("leg-2", 4, 4, "Four"),
                                    ("leg-3", 1, 50, "fifty lines")):
    leg = legs[leg_id]
    expect(leg["category"] == "new-functionality"
           and leg.get("fold-target") == "new-spec",
           f"{leg_id} is over threshold and must re-route to new-functionality/new-spec")
    body = leg.get("drafted-content", {}).get("issue-body", "")
    expect(f"touched {files} file(s)" in body and f"{lines} changed line(s)" in body,
           f"{leg_id}'s issue body must quote {files} file(s) and {lines} line(s), got {body!r}")
    expect(leg.get("drafted-content", {}).get("issue-title") == title,
           f"{leg_id}'s issue title must be {title!r}")
expect(legs["leg-4"]["category"] == "small-unrelated-change",
       "leg-4 (no drafted content: 0 files, 0 lines) must stay small-unrelated-change")
for p in problems:
    print("::error::[pr-conversation confirm step] " + p)
sys.exit(1 if problems else 0)
PYEOF
  then
    echo "[ok] pr-conversation confirm step re-routes exactly the over-threshold small-unrelated-change legs"
  else
    FAILURES=$((FAILURES + 1))
  fi
fi

echo "wing-commander-size-path-backstop tests: $FAILURES failure(s)."
[ "$FAILURES" -eq 0 ]
