#!/usr/bin/env bash
# Deterministic fixture check for watchdog.yml's "Collect: execution-output
# artifacts" step (id: collect-execution-output) — specs/022-gate-closed-
# lifecycle, contracts/denied-tool-collector-delta.md. No live watchdog run
# is needed: this feeds the exact jq filter that step runs a synthetic
# claude-execution-output.json-shaped array with a known denial count and
# asserts the collector counts and labels it correctly (SC-005, SC-006).
#
# FILTER below is a copy of watchdog.yml's collect-execution-output filter.
# It used to be kept in sync by a comment saying it must be — that failed:
# PR #137 rewrote the collector and left this copy behind, still carrying
# the exact {tool: .tool, denials: .count} bug #137 existed to fix, and
# nothing noticed because nothing ran this script either. Both holes are
# now closed mechanically: lint-workflows.yml gate 4 runs this file on
# every PR AND extracts watchdog.yml's filter to diff against this copy
# (whitespace-normalized — jq does not care about indentation, and forcing
# cosmetic sync across a YAML block scalar would just get worked around).
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
      | { tool: (.tool_name // .tool // "unknown"),
          cmd: ((.tool_input.command // .tool_input.file_path // "") | tostring | .[0:120]) }
    ]
    | group_by(.tool)
    | map({source:"result-record", "class-hint":"denied-tool",
           facts:{ tool: .[0].tool,
                   denials: length,
                   "denied-commands": ([ .[].cmd | select(. != "") ] | unique | .[0:5]) }})
  else
    ( [ .[] | select(.type=="assistant") | (.message.content // [])[]? | select(.type=="tool_use") | {(.id): .name} ] | add // {} ) as $toolmap
    | [ to_entries[] as $e
        | $e.value as $ev
        | select($ev.type=="user")
        | ($ev.message.content // [])[]?
        | select(.type=="tool_result" and (.is_error==true))
        | select(
            ( .content
              | if type=="string" then .
                elif type=="array" then (map(.text? // "") | join(" "))
                else tostring end
            )
            | test("require(s)? approval|has been denied|was blocked|Claude Code may only|Contains simple_expansion"; "i")
          )
        | { "record-index": $e.key, tool: ($toolmap[.tool_use_id] // "unknown") }
      ]
    | group_by(.tool)
    | map({source:"execution-output (log-scan fallback — not authoritative)", "class-hint":"denied-tool", facts:{tool: .[0].tool, denials: length, "record-index": [.[]."record-index"]}})
  end
'

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

# ── Fixture 1 (fallback path): a result record is present but carries no
#    permission_denials, so the log scan runs. Injected denials: Bash x1
#    (the singleton the pre-022 filter silently dropped), WebFetch x2.
#    Total = 3. A fourth is_error result — an ordinary actionlint exit 1 —
#    carries no denial text and MUST NOT be counted: before #137 the
#    fallback equated is_error with denied and inflated 8 real denials into
#    20 on a live artifact. num_turns is deliberately far below the highest
#    record-index this fixture produces (SC-006: record-index is a raw array
#    position, never validated against or capped by num_turns).
cat > "$work/fixture-fallback.json" <<'JSON'
[
  {"type":"assistant","message":{"content":[{"type":"tool_use","id":"t1","name":"Bash"}]}},
  {"type":"user","message":{"content":[{"type":"tool_result","tool_use_id":"t1","is_error":true,"content":"Bash command requires approval"}]}},
  {"type":"assistant","message":{"content":[{"type":"tool_use","id":"t2","name":"WebFetch"}]}},
  {"type":"user","message":{"content":[{"type":"tool_result","tool_use_id":"t2","is_error":true,"content":[{"type":"text","text":"This tool has been denied by the permission system"}]}]}},
  {"type":"assistant","message":{"content":[{"type":"tool_use","id":"t3","name":"WebFetch"}]}},
  {"type":"user","message":{"content":[{"type":"tool_result","tool_use_id":"t3","is_error":true,"content":"Output redirection was blocked"}]}},
  {"type":"assistant","message":{"content":[{"type":"tool_use","id":"t4","name":"Bash"}]}},
  {"type":"user","message":{"content":[{"type":"tool_result","tool_use_id":"t4","is_error":true,"content":"actionlint: 3 problem(s) found; exit status 1"}]}},
  {"type":"result","num_turns":2,"is_error":false,"result":"done"}
]
JSON
injected_denials=3
num_turns=2

out1="$(jq -c "$FILTER" "$work/fixture-fallback.json")"
note "fixture 1 (fallback) output: $out1"

total_denials="$(jq '[.[].facts.denials] | add // 0' <<<"$out1")"
if [ "$total_denials" != "$injected_denials" ]; then
  reason "fallback: facts.denials summed to $total_denials, expected exactly the injected count $injected_denials (no drop, no inflation — SC-005). A count of 4 means the non-denial actionlint failure was counted as a denial."
else
  note "fallback: facts.denials summed to the injected count ($injected_denials) — no drop, no inflation"
fi

single_tool_denials="$(jq '[.[] | select(.facts.tool=="Bash")][0].facts.denials // empty' <<<"$out1")"
if [ "$single_tool_denials" != "1" ]; then
  reason "fallback: the singleton-tool (Bash, exactly one denial plus one ordinary error) reported '$single_tool_denials', expected 1 — either the size-1 drop is back, or the ordinary error was miscounted as a denial"
else
  note "fallback: the singleton-tool denial (Bash) was reported once, and its ordinary error was not counted"
fi

if jq -e '.[0] | has("facts") and (.facts | has("turn"))' <<<"$out1" >/dev/null 2>&1; then
  reason "fallback: output still carries a 'turn' field — it must be renamed to 'record-index' (FR-010)"
else
  note "fallback: no 'turn' field present — only 'record-index'"
fi

max_record_index="$(jq '[.[].facts."record-index"[]] | max' <<<"$out1")"
if [ "$max_record_index" -le "$num_turns" ]; then
  reason "fixture 1 is not exercising the decoupling this check exists for — max record-index ($max_record_index) should exceed num_turns ($num_turns); fix the fixture"
else
  note "fallback: max record-index ($max_record_index) exceeds num_turns ($num_turns) and is still reported as record-index, not mistaken for a turn count (SC-006)"
fi

# ── Fixture 2: no result-type record at all (spec.md's "Collector with no
#    terminal result record" edge case) — the fallback path must still
#    produce output for a genuine denial, not crash and not fabricate a
#    count out of nothing.
cat > "$work/fixture-no-result.json" <<'JSON'
[
  {"type":"assistant","message":{"content":[{"type":"tool_use","id":"t1","name":"Edit"}]}},
  {"type":"user","message":{"content":[{"type":"tool_result","tool_use_id":"t1","is_error":true,"content":"Edit was blocked by the permission system"}]}}
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

# ── Fixture 3 (authoritative path): a result record carrying the SDK's real
#    permission_denials shape. Each element is ONE denial —
#    {tool_name, tool_use_id, tool_input:{command, description}} — with no
#    .tool and no .count. Reading those two absent fields is what made every
#    denied-tool finding ever filed carry {tool: null, denials: null} until
#    #137. The null assertions below are the regression guard for that.
cat > "$work/fixture-result-record.json" <<'JSON'
[
  {"type":"result","num_turns":9,"is_error":false,"permission_denials":[
    {"tool_name":"Bash","tool_use_id":"a1","tool_input":{"command":"git -C /tmp log --oneline","description":"log"}},
    {"tool_name":"Bash","tool_use_id":"a2","tool_input":{"command":"echo hi"}},
    {"tool_name":"Bash","tool_use_id":"a3","tool_input":{"command":"echo hi"}},
    {"tool_name":"WebSearch","tool_use_id":"a4","tool_input":{"query":"anything"}}
  ]}
]
JSON

out3="$(jq -c "$FILTER" "$work/fixture-result-record.json")"
note "fixture 3 (authoritative) output: $out3"

if jq -e '[.[] | select((.facts.tool == null) or (.facts.denials == null))] | length > 0' <<<"$out3" >/dev/null 2>&1; then
  reason "authoritative: a signal carries a null tool or null denials — the collector is reading fields the SDK does not emit (.tool/.count instead of .tool_name, the #137 bug)"
else
  note "authoritative: every signal carries a non-null tool and denials"
fi

auth_total="$(jq '[.[].facts.denials] | add // 0' <<<"$out3")"
if [ "$auth_total" != "4" ]; then
  reason "authoritative: facts.denials summed to $auth_total, expected 4 (one per permission_denials element, not one per group)"
else
  note "authoritative: facts.denials summed to 4 — one per denial element"
fi

bash_cmds="$(jq -c '[.[] | select(.facts.tool=="Bash")][0].facts."denied-commands" // empty' <<<"$out3")"
if [ "$bash_cmds" != '["echo hi","git -C /tmp log --oneline"]' ]; then
  reason "authoritative: Bash denied-commands was $bash_cmds, expected the two distinct commands de-duplicated and sorted"
else
  note "authoritative: denied-commands carries the distinct denied commands, so a Finding can name what was refused"
fi

websearch_cmds="$(jq -c '[.[] | select(.facts.tool=="WebSearch")][0].facts."denied-commands" // empty' <<<"$out3")"
if [ "$websearch_cmds" != '[]' ]; then
  reason "authoritative: a tool whose input has neither command nor file_path should yield an empty denied-commands, got $websearch_cmds"
else
  note "authoritative: a tool with no command/file_path input yields an empty denied-commands rather than a null or a stray string"
fi

# ── Fixture 4: the same run described BOTH ways — a result record with
#    permission_denials, and the matching tool_use/tool_result pairs the log
#    scan reads. The two paths must agree on the per-tool counts. This is
#    the check that was done by hand against three live artifacts during
#    #137 (2/2, 16/16, 8/8, where the pre-#137 fallback gave 3, 18 and 20);
#    keeping it here means neither path can drift alone.
cat > "$work/fixture-both.json" <<'JSON'
[
  {"type":"assistant","message":{"content":[{"type":"tool_use","id":"u1","name":"Bash"}]}},
  {"type":"user","message":{"content":[{"type":"tool_result","tool_use_id":"u1","is_error":true,"content":"Claude Code may only run allowlisted commands"}]}},
  {"type":"assistant","message":{"content":[{"type":"tool_use","id":"u2","name":"Bash"}]}},
  {"type":"user","message":{"content":[{"type":"tool_result","tool_use_id":"u2","is_error":true,"content":"This command requires approval"}]}},
  {"type":"assistant","message":{"content":[{"type":"tool_use","id":"u3","name":"Grep"}]}},
  {"type":"user","message":{"content":[{"type":"tool_result","tool_use_id":"u3","is_error":true,"content":"has been denied"}]}},
  {"type":"assistant","message":{"content":[{"type":"tool_use","id":"u4","name":"Bash"}]}},
  {"type":"user","message":{"content":[{"type":"tool_result","tool_use_id":"u4","is_error":true,"content":"yamllint exited 1"}]}},
  {"type":"result","num_turns":4,"is_error":false,"permission_denials":[
    {"tool_name":"Bash","tool_use_id":"u1","tool_input":{"command":"for f in *; do echo $f; done"}},
    {"tool_name":"Bash","tool_use_id":"u2","tool_input":{"command":"git show HEAD:a.yml > b.yml"}},
    {"tool_name":"Grep","tool_use_id":"u3","tool_input":{"pattern":"x"}}
  ]}
]
JSON

auth_counts="$(jq -cS '[.[] | {tool: .facts.tool, denials: .facts.denials}] | sort_by(.tool)' \
  <<<"$(jq -c "$FILTER" "$work/fixture-both.json")")"
fallback_counts="$(jq -cS '[.[] | {tool: .facts.tool, denials: .facts.denials}] | sort_by(.tool)' \
  <<<"$(jq 'map(del(.permission_denials))' "$work/fixture-both.json" | jq -c "$FILTER")")"

if [ "$auth_counts" != "$fallback_counts" ]; then
  reason "the two paths disagree on the same run: authoritative $auth_counts vs fallback $fallback_counts. The fallback is the only evidence available when the SDK record is missing, so a drift here means denial counts silently depend on which path ran."
else
  note "both paths agree on the same run ($auth_counts) — the fallback independently reproduces the SDK's own denial list"
fi

if [ "$auth_counts" != '[{"denials":2,"tool":"Bash"},{"denials":1,"tool":"Grep"}]' ]; then
  reason "fixture 4 is not exercising what it claims — expected Bash 2 / Grep 1 with the ordinary yamllint failure excluded, got $auth_counts"
else
  note "fixture 4: Bash 2 / Grep 1, with the ordinary yamllint failure excluded from both paths"
fi

if [ "${#fail_reasons[@]}" -eq 0 ]; then
  echo "✅ verify-denied-tool-collector: all assertions passed."
  exit 0
fi

echo "❌ verify-denied-tool-collector: ${#fail_reasons[@]} assertion(s) failed:"
for r in "${fail_reasons[@]}"; do echo "- $r"; done
exit 1
