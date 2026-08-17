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
# non-zero) regardless of input — callers `eval` its output, which is safe
# because these three values are always empty or a bare non-negative integer.
set -uo pipefail

TRANSCRIPT="${1:-}"

main_turns=""
sub_turns=""
reported=""

if [ -n "$TRANSCRIPT" ] && [ -f "$TRANSCRIPT" ] && [ -s "$TRANSCRIPT" ]; then
  if jq -e . "$TRANSCRIPT" >/dev/null 2>&1; then
    # Distinct .message.id, because one response streams as several assistant
    # records (a text chunk, then a tool_use chunk) that share an id —
    # counting records inflates the total ~1.6x.
    #
    # parent_tool_use_id == null, because subagent (Task tool) responses are
    # inlined into the same transcript and do NOT count against the parent's
    # budget.
    main_turns="$(jq -r 'if type=="array" then . else [.] end
      | map(select(.type=="assistant"
                   and (.parent_tool_use_id // null) == null)
            | .message.id // empty)
      | unique | length' "$TRANSCRIPT" 2>/dev/null || true)"
    sub_turns="$(jq -r 'if type=="array" then . else [.] end
      | map(select(.type=="assistant"
                   and (.parent_tool_use_id // null) != null)
            | .message.id // empty)
      | unique | length' "$TRANSCRIPT" 2>/dev/null || true)"
    reported="$(jq -r 'if type=="array" then . else [.] end
      | map(select(.type=="result")) | last | .num_turns // empty' "$TRANSCRIPT" 2>/dev/null || true)"
  fi
fi

printf 'main_turns=%s\n' "$main_turns"
printf 'sub_turns=%s\n' "$sub_turns"
printf 'reported=%s\n' "$reported"
