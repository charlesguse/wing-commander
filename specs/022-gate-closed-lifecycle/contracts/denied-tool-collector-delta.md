# Contract Delta: Denied-Tool Collector (`watchdog.yml`, `collect` job)

This is a delta against `specs/015-pipeline-watchdog/contracts/
watchdog-workflow.md` and `specs/015-pipeline-watchdog/data-model.md`,
which remain the full contract for the watchdog's detection/triage/act
pipeline. Only the denied-tool collector's counting and labeling logic
changes; its `class-hint`, the fact that it is a `collect`-job
`continue-on-error: true` step, and its consumers (`diagnose`'s prompt,
`triage`, `act`) are unchanged.

## Current behavior (step "Collect: execution-output artifacts",
`watchdog.yml:314-357`, id `collect-execution-output`)

```jq
( [ .[] | select(.type=="assistant") | (.message.content // [])[]? | select(.type=="tool_use") | {(.id): .name} ] | add // {} ) as $toolmap
| [ to_entries[] as $e
    | $e.value as $ev
    | select($ev.type=="user")
    | ($ev.message.content // [])[]?
    | select(.type=="tool_result" and (.is_error==true))
    | { turn: $e.key, tool: ($toolmap[.tool_use_id] // "unknown") }
  ]
| group_by(.tool)
| map(select(length > 1))
| map({source:"execution-output", "class-hint":"denied-tool", facts:{tool: .[0].tool, denials: length, turns: [.[].turn]}})
```

Defects (research.md R4):

1. `to_entries[] | .key` is the zero-based index into the raw, interleaved
   SDK message array (`claude-execution-output.json`) — **not** a
   conversation turn. A single turn commonly spans several array entries,
   so these indexes can (and did, in issues #105/#106) exceed the run's own
   `num_turns`. Reported under the field name `turns`.
2. `map(select(length > 1))` silently drops every tool whose denial-shaped
   `tool_result` entries number exactly one, and reports `denials: length`
   for the survivors — a count of "how many entries survived the group
   filter," not the number of denial events that actually occurred.

## Corrected behavior

```jq
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
```

Deltas from current behavior:

- `turn` → `record-index` (FR-010): same array-position value, honest
  name. Never compared against, or presented alongside, `num_turns` as if
  it were a turn count.
- `map(select(length > 1))` removed: every tool with at least one
  denial-shaped entry is reported, and `denials` (still `length` of the
  post-`group_by` array) now equals the true number of denial-shaped
  `tool_result` entries observed for that tool — no silent drop, no
  count disconnected from occurrences (FR-008).
- `source` literal changed to make the fallback explicit inline in the
  finding itself, not only in prose (FR-009's "make clear that a fallback
  count is not authoritative" — belt-and-suspenders with the `diagnose`
  prompt change below).

## Preferring a terminal-result-record count when present (FR-009, forward-compatible)

Research.md R4 confirms the terminal result record carries no
`permission_denials`-shaped field in the Claude Code SDK version this
pipeline currently uses — so this branch has no live case to exercise
today. The collector step is nonetheless written to prefer it if present,
so no further collector change is needed if a future SDK version adds one:

```jq
if (.[] | select(.type=="result") | has("permission_denials"))
then # source the count and per-denial identifiers from the result record's own field — authoritative, no fallback labeling
else # the log-scan above, explicitly labeled non-authoritative
end
```

**Non-goal**: deriving genuine turn numbers from the transcript (e.g. by
correlating array entries back to `num_turns` boundaries) is explicitly not
required (FR-010) — the minimal, accurate-naming fix is the chosen and
maintainer-confirmed approach (checklists/requirements.md Decision A).

## Downstream: `diagnose` prompt guard (`watchdog.yml:990` area)

The existing instruction to keep `normalizedFacts` free of "volatile
fields like run IDs, timestamps, or turn numbers" already exists but does
not prevent the agent from quoting the collector's own (previously
mislabeled) `turns` field into a Finding's human-readable `description`
prose — which is how the reported "3 denials across turns 28, 116, 118"
description was produced. Renaming the field to `record-index` removes the
misleading label at its source; no prompt change is strictly required, but
the prompt's evidence-citation instruction is confirmed to still read
naturally against the renamed field (it already says "quote or cite the
specific evidence," which `record-index: [28, 116, 118]` satisfies without
implying those are turns).

## Fixture verification (Testing, plan.md)

A small deterministic check, following the existing pattern of
`.github/scripts/verify-watchdog-run.sh` (plain bash/jq assertions, no
test framework): feed the corrected `jq` filter a synthetic
`claude-execution-output.json`-shaped array with a known number of
denial-shaped `tool_result` entries (including at least one tool with
exactly one denial, to prove the size-1 drop is gone) and a known
`num_turns` on its `result` record, and assert:

1. `facts.denials` equals the true injected count (no drop, no
   inflation) — SC-005.
2. No `record-index` value is presented as, or mistaken for, a turn number
   exceeding the injected `num_turns` — SC-006.
3. A fixture with no `result`-type record at all still produces output
   (the fallback path, not a crash) — spec.md's "Collector with no
   terminal result record" edge case.
