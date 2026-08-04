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
  export TRACKING_LABEL="auto-update:tracking" MIGRATION_SCAN_LIMIT="${WC_SCAN_LIMIT:-200}"
  run_step 'auto-update-spec-kit__settle__*state-machine*.sh' >"$WORK/settle.log" 2>&1
  S_SETTLED="$(out settled)"; S_ISSUE="$(out issue-number)"; S_SUMMARY="$(summary)"
  S_LOG="$(cat "$WORK/settle.log")"
}

# Re-run settle against the SAME $GH_STATE (that is the point — it models the
# next day's cron seeing yesterday's issue), but with the per-step files the
# runner would freshly provide: a stale $GITHUB_OUTPUT would let an old
# `settled=` line be read back, and a stale $GH_CALLS would double-count.
rerun_settle() { # rerun_settle <latest> <release-type> <stabilization-checks>
  : > "$GITHUB_OUTPUT"; : > "$GITHUB_STEP_SUMMARY"; : > "$GH_CALLS"
  run_settle "$@"
}

labels_of() { "$PY" -c "import json,sys;print(','.join(json.load(open(sys.argv[1]))['issues'][sys.argv[2]]['labels']))" "$GH_STATE" "$1"; }

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
# Counts BODY rewrites specifically. `gh issue edit --add-label` is also an
# `issue edit`, and the tracking-label self-heal legitimately makes one; what
# FR-015 forbids is rewriting the marker out from under a pending decision.
check "S12 issue body untouched" "$(grep -c 'issue edit.*--body' "$GH_CALLS")" "0"
check_contains "S12 summary" "$S_SUMMARY" "awaiting a maintainer decision"

echo "--- Scenario 12b: newer candidate while awaiting a decision -> notes it, still holds ---"
seed "$(mk_issue 42 0.15.1 1 ' awaiting-decision=true')"
run_settle "0.16.0" "minor" "1"
check "S12b still not settled" "$S_SETTLED" "false"
check_contains "S12b comment explains the hold" "$(comments 42)" "still awaiting a maintainer decision"
check "S12b marker not rewritten" "$(grep -c 'issue edit.*--body' "$GH_CALLS")" "0"

echo "--- Scenario 13: the #167 regression — a BROKEN lookup must never open an issue ---"
# 2026-08-03: the lookup returned empty because it failed, not because the
# repo was empty, and the empty-means-none branch opened #167 on top of #162.
# The invariant is: an unusable lookup produces NO writes at all.
seed "$(mk_issue 162 0.15.1 1 '')"
# Set/unset explicitly: `VAR=x some_function` leaks VAR into the rest of the
# shell in bash, which would silently break every scenario after this one.
export GH_STUB_FAIL="issue list"
run_settle "0.15.1" "minor" "1"
unset GH_STUB_FAIL
check "S13 still exactly one issue (no duplicate filed)" "$(issue_count)" "1"
check "S13 no gh issue create call" "$(grep -c 'issue create' "$GH_CALLS")" "0"
check "S13 no writes of any kind" "$(grep -cE 'issue (edit|comment|create)' "$GH_CALLS")" "0"
check "S13 not settled" "$S_SETTLED" "false"
check "S13 hands no issue number forward" "$S_ISSUE" ""
check_contains "S13 failure is annotated, not swallowed" "$S_LOG" "::warning::"
check_contains "S13 warning says the state is UNKNOWN" "$S_LOG" "UNKNOWN"
check_contains "S13 summary records the skipped cycle" "$S_SUMMARY" "lookup failed"

echo "--- Scenario 13b: only the migration scan breaks -> still no duplicate ---"
seed "$(mk_issue 162 0.15.1 1 '')"
export GH_STUB_FAIL="issue list 200"
run_settle "0.15.1" "minor" "1"
unset GH_STUB_FAIL
check "S13b no duplicate" "$(issue_count)" "1"
check "S13b not settled" "$S_SETTLED" "false"
check_contains "S13b annotated" "$S_LOG" "::warning::"

echo "--- Scenario 13d: tier-1 label lookup alone breaks -> degrades, but LOUDLY ---"
# The migration scan is a superset of the label lookup, so a broken tier 1 is
# survivable — which is exactly why it must still be annotated. Silent
# degradation means every run quietly does the wide scan and nobody knows the
# cheap path is dead. (Mutation-checked: restoring `2>/dev/null || echo '[]'`
# on the label lookup is invisible to every other assertion in this file.)
seed "$(mk_issue 162 0.15.1 1 '')"
export GH_STUB_FAIL="issue list --label"
run_settle "0.15.1" "minor" "1"
unset GH_STUB_FAIL
check "S13d degrades to the scan and still settles" "$S_SETTLED" "true"
check "S13d found the right issue" "$S_ISSUE" "162"
check "S13d no duplicate" "$(issue_count)" "1"
check_contains "S13d the dead cheap path is annotated" "$S_LOG" "could not list issues labelled"

echo "--- Scenario 13c: recovery — the very next run with a working lookup proceeds ---"
seed "$(mk_issue 162 0.15.1 1 '')"
export GH_STUB_FAIL="issue list"
run_settle "0.15.1" "minor" "1"
unset GH_STUB_FAIL
rerun_settle "0.15.1" "minor" "1"
check "S13c settles on the pre-existing issue" "$S_SETTLED" "true"
check "S13c on the ORIGINAL issue, not a new one" "$S_ISSUE" "162"
check "S13c still exactly one issue" "$(issue_count)" "1"

echo "--- Scenario 14: adoption — an unlabelled tracking issue is found and stamped ---"
seed "$(mk_issue 162 0.15.1 1 '')"
run_settle "0.15.1" "minor" "3"
check "S14 adopted the existing issue" "$(issue_count)" "1"
check_contains "S14 issue now carries the tracking label" "$(labels_of 162)" "auto-update:tracking"
check_contains "S14 adoption is stated in the summary" "$S_SUMMARY" "adopted pre-existing tracking issue #162"
check_contains "S14 state still advanced" "$(issue_body 162)" "observed=2"

echo "--- Scenario 14b: once labelled, the lookup is a single direct read ---"
rerun_settle "0.15.1" "minor" "3"
check "S14b one issue list call, not two (no migration scan)" "$(grep -c 'issue list' "$GH_CALLS")" "1"
check_contains "S14b no second adoption" "$S_SUMMARY" "observed again"
check_not_contains "S14b does not re-adopt" "$S_SUMMARY" "adopted pre-existing"

echo "--- Scenario 15: a newly opened tracking issue is labelled at birth ---"
seed '{"issues":{},"next_issue":42}'
run_settle "0.15.1" "minor" "1"
check_contains "S15 created issue carries the tracking label" "$(labels_of 42)" "auto-update:tracking"
check "S15 label was created first (--force, idempotent)" "$(grep -c 'label create auto-update:tracking' "$GH_CALLS")" "1"

echo "--- Scenario 15b: #162 + #167 as they actually stand -> data-integrity hold ---"
seed '{"issues":{
 "162":{"number":162,"state":"open","body":"x <!-- wing-commander-auto-update-spec-kit: candidate=0.15.1 observed=1 -->","labels":[],"comments":[]},
 "167":{"number":167,"state":"open","body":"y <!-- wing-commander-auto-update-spec-kit: candidate=0.15.1 observed=1 -->","labels":[],"comments":[]}},"next_issue":300}'
run_settle "0.15.1" "minor" "1"
check "S15b not settled" "$S_SETTLED" "false"
check "S15b no third issue" "$(issue_count)" "2"
check "S15b no writes" "$(grep -cE 'issue (edit|comment|create)' "$GH_CALLS")" "0"
check_contains "S15b names #162" "$S_SUMMARY" "162"
check_contains "S15b names #167" "$S_SUMMARY" "167"
check_contains "S15b tells the human what to do" "$S_SUMMARY" "Close all but one"

echo "--- Scenario 16: the migration scan window is real, and truncation is announced ---"
# The scan reads newest-first, so an old unlabelled tracking issue can fall
# outside the window on a busy repo. That is a WARN-and-proceed, not a block:
# blocking would wedge first-sighting forever on any repo with more open
# issues than the window. The one thing it must never be is silent.
# WC_SCAN_LIMIT shrinks the window instead of seeding 200 fixtures.
seed '{"issues":{
 "162":{"number":162,"state":"open","body":"old tracker <!-- wing-commander-auto-update-spec-kit: candidate=0.15.1 observed=1 -->","labels":[],"comments":[]},
 "900":{"number":900,"state":"open","body":"unrelated newer issue","labels":[],"comments":[]}},"next_issue":901}'
export WC_SCAN_LIMIT=1
run_settle "0.15.1" "minor" "1"
unset WC_SCAN_LIMIT
check_contains "S16 truncation is announced" "$S_LOG" "migration scan hit its 1-issue window"
check_contains "S16 warning, not a silent miss" "$S_LOG" "::warning::"
check "S16 the window was actually honoured (marker issue not seen)" "$(issue_count)" "3"

echo "--- Scenario 16b: same fixture, adequate window -> finds it, no duplicate ---"
seed '{"issues":{
 "162":{"number":162,"state":"open","body":"old tracker <!-- wing-commander-auto-update-spec-kit: candidate=0.15.1 observed=1 -->","labels":[],"comments":[]},
 "900":{"number":900,"state":"open","body":"unrelated newer issue","labels":[],"comments":[]}},"next_issue":901}'
run_settle "0.15.1" "minor" "1"
check "S16b no duplicate" "$(issue_count)" "2"
check "S16b settled on the old tracker" "$S_ISSUE" "162"
check_not_contains "S16b no truncation warning" "$S_LOG" "window"

report "T2 settle"
