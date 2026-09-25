#!/usr/bin/env bash
# .github/actions/_shared/count-turns.sh
#
# The one place that counts the turns --max-turns actually enforces,
# extracted out of wing-commander-metrics-summary so wing-commander-agent-verdict
# can read the exact same rule instead of carrying a second, driftable copy
# (research.md R5 in specs/037-agent-turn-budget-guard/). Callers resolve this
# path as "$GITHUB_ACTION_PATH/../_shared/count-turns.sh", which sits beside
# every composite inside the same .wing-commander-pipeline/ self-checkout
# every stage already performs.
#
# Invoke with `bash "$GITHUB_ACTION_PATH/../_shared/count-turns.sh" "$TRANSCRIPT"`
# rather than executing it directly — that way the file's executable bit,
# which a plain git checkout does not reliably preserve, is never load-bearing.
#
# Takes the transcript path as $1. Prints three `key=value` lines on stdout:
#   main_turns=<N or empty>   distinct main-loop assistant .message.id count
#   sub_turns=<N or empty>    distinct subagent (Task-tool) .message.id count
#   reported=<N or empty>     the last .type=="result" record's .num_turns
# Every value is empty (never a fabricated zero) when the transcript is
# missing, empty, or not readable as JSON. This script never fails (no exit
# non-zero) regardless of input.
#
# Every value it prints is empty or a bare non-negative integer, and that is
# enforced here rather than assumed (#572): the two counts are jq `length`s,
# and `reported` -- the transcript's own .num_turns, which the agent runtime
# writes and nothing here controls -- is printed only when it is an integer
# >= 0. Callers still filter the output to `name=<digits>` lines before their
# `eval`, as defence in depth.
#
# Accepted shapes: one JSON array, one object, NDJSON, or several
# concatenated documents. All normalise to one flat array (`jq -s` collects
# the documents; a document that is itself an array is spliced in), the same
# rule wing-commander-agent-verdict applies to its own reads. Fed per
# document, NDJSON made each count print one line per document, and the
# callers' `eval` ran a bare "0" as a command (exit 127). Non-object elements
# (a bare number, string, `null` or `false`) are then dropped with `objects`
# before any `.type` read: `.type` on a number is a jq error that would empty
# every count.
set -uo pipefail

TRANSCRIPT="${1:-}"

main_turns=""
sub_turns=""
reported=""
records=""

if [ -n "$TRANSCRIPT" ] && [ -f "$TRANSCRIPT" ] && [ -s "$TRANSCRIPT" ]; then
  # One read of the file. A parse failure leaves $records empty, and every
  # value with it. (No `jq -e .` check: -e takes its status from the LAST
  # document only, so NDJSON ending in `null` or `false` read as unparseable.)
  records="$(jq -cs 'map(if type=="array" then .[] else . end)
    | map(objects)' "$TRANSCRIPT" 2>/dev/null)" || records=""
  if [ -n "$records" ]; then
    # Distinct .message.id, because one response streams as several assistant
    # records (a text chunk, then a tool_use chunk) that share an id —
    # counting records inflates the total ~1.6x.
    #
    # parent_tool_use_id == null, because subagent (Task tool) responses are
    # inlined into the same transcript and do NOT count against the parent's
    # budget.
    main_turns="$(printf '%s' "$records" | jq -r '
      map(select(.type=="assistant"
                 and (.parent_tool_use_id // null) == null)
          | .message.id // empty)
      | unique | length' 2>/dev/null || true)"
    sub_turns="$(printf '%s' "$records" | jq -r '
      map(select(.type=="assistant"
                 and (.parent_tool_use_id // null) != null)
          | .message.id // empty)
      | unique | length' 2>/dev/null || true)"
    # Integer >= 0 only; anything else (a string, a float, a negative, an
    # object) prints empty. The digits test also rejects a huge integer jq
    # would print in exponent form.
    reported="$(printf '%s' "$records" | jq -r '
      map(select(.type=="result")) | last | .num_turns // empty
      | select(type=="number" and . >= 0 and . == floor)
      | tostring | select(test("^[0-9]+$"))' 2>/dev/null || true)"
  fi
fi

printf 'main_turns=%s\n' "$main_turns"
printf 'sub_turns=%s\n' "$sub_turns"
printf 'reported=%s\n' "$reported"
