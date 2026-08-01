#!/usr/bin/env bash
# Scenarios 2, 3, 4, 11 (+ the awaiting-decision hold from 12): settle's
# state machine, executed for real against the gh stub.
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

seed() { # seed <json-for-issues>
  new_step_env
  printf '%s' "$1" > "$GH_STATE"
}

run_settle() { # run_settle <latest> <release-type> <stabilization-checks>
  GHA_SUBST=()
  export GH_TOKEN=stub LATEST="$1" RELEASE_TYPE="$2" STABILIZATION_CHECKS="$3"
  export LATEST_URL="https://github.com/github/spec-kit/releases/tag/v$1"
  run_step 'auto-update-spec-kit__settle__*state-machine*.sh' >/dev/null 2>&1
  S_SETTLED="$(out settled)"; S_ISSUE="$(out issue-number)"; S_SUMMARY="$(summary)"
}

issue_body()  { "$PY" -c "import json,sys;print(json.load(open(sys.argv[1]))['issues'][sys.argv[2]]['body'])" "$GH_STATE" "$1"; }
issue_count() { "$PY" -c "import json,sys;print(len(json.load(open(sys.argv[1]))['issues']))" "$GH_STATE"; }
comments()    { "$PY" -c "import json,sys;print('\n'.join(c['body'] for c in json.load(open(sys.argv[1]))['issues'][sys.argv[2]].get('comments',[])))" "$GH_STATE" "$1"; }

MARKER='<!-- wing-commander-auto-update-spec-kit: candidate=%s observed=%s%s -->'
mk_issue() { # mk_issue <num> <candidate> <observed> <extra-marker> <state>
  printf '{"issues":{"%s":{"number":%s,"state":"%s","title":"Auto-update Spec Kit","body":"Spec Kit v%s detected upstream.\\n\\n%s","labels":[],"comments":[]}},"next_issue":300}' \
    "$1" "$1" "${5:-open}" "$2" "$(printf "$MARKER" "$2" "$3" "$4")"
}

echo "--- Scenario 2: first detection -> opens a watching issue, observed=1, no PR ---"
seed '{"issues":{},"next_issue":42}'
run_settle "0.15.1" "minor" "1"
check "S2 settled (does NOT adopt same day)" "$S_SETTLED" "false"
check "S2 one issue now exists" "$(issue_count)" "1"
B="$(issue_body 42)"
check_contains "S2 marker candidate" "$B" "candidate=0.15.1"
check_contains "S2 marker observed=1" "$B" "observed=1"
check_contains "S2 says waiting to settle" "$B" "aiting for the patch stream to settle"
check_contains "S2 records release URL" "$B" "releases/tag/v0.15.1"
check_contains "S2 summary" "$S_SUMMARY" "opened #42 watching v0.15.1"

echo "--- Scenario 3: second unchanged check reaches threshold -> proceeds ---"
seed "$(mk_issue 42 0.15.1 1 '')"
run_settle "0.15.1" "minor" "1"
check "S3 settled=true at observed(1) >= threshold(1)" "$S_SETTLED" "true"
check "S3 hands the issue number forward" "$S_ISSUE" "42"
check_contains "S3 summary names evaluate-path" "$S_SUMMARY" "proceeding to evaluate-path"

echo "--- Scenario 3b: threshold=3, observed=1 -> increments, does not proceed ---"
seed "$(mk_issue 42 0.15.1 1 '')"
run_settle "0.15.1" "minor" "3"
check "S3b not settled yet" "$S_SETTLED" "false"
check_contains "S3b marker incremented to observed=2" "$(issue_body 42)" "observed=2"
check_contains "S3b summary shows progress" "$S_SUMMARY" "(2/3)"

echo "--- Scenario 3c: threshold=3, observed=3 -> settles ---"
seed "$(mk_issue 42 0.15.1 3 '')"
run_settle "0.15.1" "minor" "3"
check "S3c settled" "$S_SETTLED" "true"

echo "--- Scenario 4: superseded candidate resets the settle counter ---"
seed "$(mk_issue 42 0.15.0 2 '')"
run_settle "0.15.1" "patch" "3"
check "S4 not settled (no adoption this cycle)" "$S_SETTLED" "false"
B="$(issue_body 42)"
check_contains "S4 marker now tracks the new candidate" "$B" "candidate=0.15.1"
check_contains "S4 observed reset to 1" "$B" "observed=1"
check_not_contains "S4 old candidate gone from marker" "$B" "candidate=0.15.0"
check_contains "S4 supersession explained in a comment" "$(comments 42)" "superseded the previously-watched v0.15.0"
check_contains "S4 summary" "$S_SUMMARY" "settle count reset to 1"

echo "--- Scenario 11: duplicate-attempt guard -> reuses, never creates a second issue ---"
seed "$(mk_issue 42 0.15.1 1 '')"
run_settle "0.15.1" "minor" "5"
check "S11 still exactly one issue" "$(issue_count)" "1"
check "S11 no gh issue create call" "$(grep -c 'issue create' "$GH_CALLS")" "0"

echo "--- Scenario 11b: closed prior issue does not block a new cycle ---"
seed "$(mk_issue 42 0.14.0 1 '' closed)"
run_settle "0.15.1" "minor" "1"
check "S11b opens a fresh issue (closed one ignored)" "$(issue_count)" "2"
check "S11b not settled on first sighting" "$S_SETTLED" "false"

echo "--- Scenario 11c: >1 open marked issue -> data-integrity hold, no writes ---"
seed '{"issues":{
 "42":{"number":42,"state":"open","body":"x <!-- wing-commander-auto-update-spec-kit: candidate=0.15.1 observed=1 -->","labels":[],"comments":[]},
 "43":{"number":43,"state":"open","body":"y <!-- wing-commander-auto-update-spec-kit: candidate=0.15.1 observed=1 -->","labels":[],"comments":[]}},"next_issue":300}'
run_settle "0.15.1" "minor" "1"
check "S11c not settled" "$S_SETTLED" "false"
check "S11c no new issue" "$(issue_count)" "2"
check "S11c no edit/comment writes" "$(grep -cE 'issue (edit|comment|create)' "$GH_CALLS")" "0"
check_contains "S11c left for a human" "$S_SUMMARY" "data-integrity condition"

echo "--- Scenario 12 hold: awaiting-decision=true issue is left untouched ---"
seed "$(mk_issue 42 0.15.1 1 ' awaiting-decision=true')"
run_settle "0.15.1" "minor" "1"
check "S12 not settled while a question is open" "$S_SETTLED" "false"
check "S12 issue body untouched" "$(grep -c 'issue edit' "$GH_CALLS")" "0"
check_contains "S12 summary" "$S_SUMMARY" "awaiting a maintainer decision"

echo "--- Scenario 12b: newer candidate while awaiting a decision -> notes it, still holds ---"
seed "$(mk_issue 42 0.15.1 1 ' awaiting-decision=true')"
run_settle "0.16.0" "minor" "1"
check "S12b still not settled" "$S_SETTLED" "false"
check_contains "S12b comment explains the hold" "$(comments 42)" "still awaiting a maintainer decision"
check "S12b marker not rewritten" "$(grep -c 'issue edit' "$GH_CALLS")" "0"

report "T2 settle"
