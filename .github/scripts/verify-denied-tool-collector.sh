#!/usr/bin/env bash
# Deterministic fixture check for watchdog.yml's "Collect: execution-output
# artifacts" step (id: collect-execution-output) — specs/022-gate-closed-
# lifecycle, contracts/denied-tool-collector-delta.md. No live watchdog run
# is needed: this feeds the exact jq filter that step runs a synthetic
# claude-execution-output.json-shaped array with a known denial count and
# asserts the collector counts and labels it correctly (SC-005, SC-006).
#
# FILTER below MUST be kept byte-for-byte in sync with watchdog.yml's
# collect-execution-output step — this script has no other way to notice
# that step drifting out of sync with what it verifies.
#
# Usage: .github/scripts/verify-denied-tool-collector.sh
# Exit code: 0 = all assertions passed; 1 = an assertion failed.

set -uo pipefail

fail_reasons=()
note() { echo "::notice::verify-denied-tool-collector: $1"; }
reason() { fail_reasons+=("$1"); echo "::error::verify-denied-tool-collector: $1"; }

# shellcheck disable=SC2016 # this is a jq program — its $vars must NOT be
# shell-expanded.
FILTER='
  if ([ .[] | select(.type=="result") | has("permission_denials") ] | any)
  then
    [ .[] | select(.type=="result") | .permission_denials[]?
      | {source:"result-record", "class-hint":"denied-tool", facts:{tool: .tool, denials: .count}}
    ]
  else
    ( [ .[] | select(.type=="assistant") | (.message.content // [])[]? | select(.type=="tool_use") | {(.id): .name} ] | add // {} ) as $toolmap
    | [ to_entries[] as $e
        | $e.value as $ev
        | select($ev.type=="user")
        | ($ev.message.content // [])[]?
        | select(.type=="tool_result" and (.is_error==true))
        | { "record-index": $e.key, tool: ($toolmap[.tool_use_id] // "unknown") }
      ]
    | group_by(.tool)
    | map({source:"execution-output (log-scan fallback — not authoritative)", "class-hint":"denied-tool", facts:{tool: .[0].tool, denials: length, "record-index": [.[]."record-index"]}})
  end
'

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

# ── Fixture 1: a known denial count, including a singleton-tool denial,
#    plus a result record whose num_turns is deliberately far smaller than
#    the highest record-index this fixture produces (SC-006: record-index
#    is a raw array position, never validated against or capped by
#    num_turns — proving the two are decoupled, not just usually equal).
#    Injected denials: Bash x1 (the singleton the old filter silently
#    dropped), WebFetch x2. Total = 3.
cat > "$work/fixture-with-result.json" <<'JSON'
[
  {"type":"assistant","message":{"content":[{"type":"tool_use","id":"t1","name":"Bash"}]}},
  {"type":"user","message":{"content":[{"type":"tool_result","tool_use_id":"t1","is_error":true}]}},
  {"type":"assistant","message":{"content":[{"type":"tool_use","id":"t2","name":"WebFetch"}]}},
  {"type":"user","message":{"content":[{"type":"tool_result","tool_use_id":"t2","is_error":true}]}},
  {"type":"assistant","message":{"content":[{"type":"tool_use","id":"t3","name":"WebFetch"}]}},
  {"type":"user","message":{"content":[{"type":"tool_result","tool_use_id":"t3","is_error":true}]}},
  {"type":"result","num_turns":2,"is_error":false,"result":"done"}
]
JSON
injected_denials=3
num_turns=2

out1="$(jq -c "$FILTER" "$work/fixture-with-result.json")"
note "fixture 1 output: $out1"

total_denials="$(jq '[.[].facts.denials] | add' <<<"$out1")"
if [ "$total_denials" != "$injected_denials" ]; then
  reason "facts.denials summed to $total_denials, expected exactly the injected count $injected_denials (no drop, no inflation — SC-005)"
else
  note "facts.denials summed to the injected count ($injected_denials) — no drop, no inflation"
fi

single_tool_denials="$(jq '[.[] | select(.facts.tool=="Bash")][0].facts.denials // empty' <<<"$out1")"
if [ "$single_tool_denials" != "1" ]; then
  reason "the singleton-tool (Bash, exactly one denial) was dropped or miscounted — got '$single_tool_denials', expected 1 (the size-1 drop this feature removes)"
else
  note "the singleton-tool denial (Bash) was reported, not dropped"
fi

if jq -e '.[0] | has("facts") and (.facts | has("turn"))' <<<"$out1" >/dev/null 2>&1; then
  reason "output still carries a 'turn' field — it must be renamed to 'record-index' (FR-010)"
else
  note "no 'turn' field present — only 'record-index'"
fi

max_record_index="$(jq '[.[].facts."record-index"[]] | max' <<<"$out1")"
if [ "$max_record_index" -le "$num_turns" ]; then
  reason "fixture 1 is not exercising the decoupling this check exists for — max record-index ($max_record_index) should exceed num_turns ($num_turns); fix the fixture"
else
  note "max record-index ($max_record_index) exceeds num_turns ($num_turns) and is still reported as record-index, not mistaken for a turn count (SC-006)"
fi

# ── Fixture 2: no result-type record at all (spec.md's "Collector with no
#    terminal result record" edge case) — the fallback path must still
#    produce output for a genuine denial, not crash and not fabricate a
#    count out of nothing.
cat > "$work/fixture-no-result.json" <<'JSON'
[
  {"type":"assistant","message":{"content":[{"type":"tool_use","id":"t1","name":"Edit"}]}},
  {"type":"user","message":{"content":[{"type":"tool_result","tool_use_id":"t1","is_error":true}]}}
]
JSON

if ! out2="$(jq -c "$FILTER" "$work/fixture-no-result.json" 2>&1)"; then
  reason "the filter crashed on a fixture with no result-type record at all: $out2"
else
  note "fixture 2 output: $out2"
  no_result_denials="$(jq '[.[].facts.denials] | add // 0' <<<"$out2")"
  if [ "$no_result_denials" != "1" ]; then
    reason "with no result-type record, expected the log-scan fallback to still report the one real denial (got denials=$no_result_denials) — fallback must produce output, not crash or fabricate"
  else
    note "with no result-type record, the fallback still reported the one real denial (no crash, no fabrication)"
  fi
fi

if [ "${#fail_reasons[@]}" -eq 0 ]; then
  echo "✅ verify-denied-tool-collector: all assertions passed."
  exit 0
fi

echo "❌ verify-denied-tool-collector: ${#fail_reasons[@]} assertion(s) failed:"
for r in "${fail_reasons[@]}"; do echo "- $r"; done
exit 1
