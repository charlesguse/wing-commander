# Contract: `wing-commander-agent-verdict` gains `rate-limited`; `wing-commander-metrics-summary` gains the allow-list value

`data-model.md`'s "Verdict" and "Rate-limit event"/"Terminal result
record" entities define the field shapes referenced below;
`research.md` R1/R2/R3 explain the reasoning.

## `wing-commander-agent-verdict` (EXTENDED)

`.github/actions/wing-commander-agent-verdict/action.yml`

**Inputs**: unchanged (`transcript-path`, `intended-turns`, `run-label`).

**Outputs**:

| Name | Change |
|---|---|
| `verdict` | Description string gains the fifth value: `"healthy \| exhausted \| rate-limited \| failed \| unclassifiable"`. |
| `reason` | Unchanged shape; new prose for the rate-limited case. |
| `rate-limit-reset` | NEW. `resetsAt` verbatim when present and non-empty, else `"unknown"`. Empty string for every other verdict. |
| `counted-turns` / `reported-turns` / `over-budget` / `subagent-turns` | Unchanged. |

**Behavioral contract**:

- Still never fails its own step (`exit 0` unconditionally) — the new
  branch is additive inside the same `run:` block, no new exit path.
- Classification order, inside the existing `if [ -z "$result_json" ]
  ... else ...` branch, after `subtype` and `is_error` are read:

  ```
  if subtype == "error_max_turns":       verdict = exhausted        # unchanged, checked first
  elif (is_error == "true" OR subtype != "success") AND rate_limit_evidence_present:
                                          verdict = rate-limited     # NEW, checked second
  elif is_error == "true":               verdict = failed           # unchanged
  elif subtype != "success":             verdict = failed           # unchanged
  else:                                   verdict = healthy          # unchanged
  ```

  `rate_limit_evidence_present` = `(result_json.terminal_reason ==
  "api_error" AND result_json.api_error_status == 429)` OR (transcript
  contains a `.type=="rate_limit_event"` record whose status is
  `"rejected"` (case-insensitive) or absent). The status is read from
  `.rate_limit_info.status`, falling back to a top-level `.status`. An
  event whose status is anything else (the runtime's informational
  `"allowed"` / `"allowed_warning"`) is not evidence (#544): counting it
  classified unrelated failures as `rate-limited`. A statusless event
  still counts: every informational event names its status, and a
  genuine refused-run transcript (#231) carries a bare one. Evaluated with `jq`
  against the same transcript file already open for `result_json` — no
  second file read, no network call (FR-002).
- `rate-limit-reset` is computed once, from the *last* qualifying
  (rejected or statusless) `.type=="rate_limit_event"` record's
  `.resetsAt`, or its `.rate_limit_info.resetsAt`. When no event
  qualifies (a terminal api_error 429 whose only events are
  informational), it falls back to the last event of any status (FR-003:
  expose the reset whenever the transcript carries one). That fallback
  feeds only the reset time and window, never classification. A numeric
  (epoch-seconds) `resetsAt` is converted to ISO-8601, and CR/LF in the
  reset time or window become spaces, so neither can inject a
  `$GITHUB_OUTPUT` line (mirrors the
  "last record is authoritative" rule the classifier already applies to
  `result` records) — `"unknown"` when no such record exists, is empty,
  or is unparseable as non-empty text. Never epoch-zero, never a
  fabricated timestamp (spec.md edge case).
- Turn counting (`_shared/count-turns.sh`) and `over-budget` are
  unaffected — independent of the verdict branch, as today.
- Every existing verdict's classification is byte-for-byte unchanged for
  every transcript shape that does not meet the new condition (FR-005).

## `wing-commander-metrics-summary` (EXTENDED, additive-only)

`.github/actions/wing-commander-metrics-summary/action.yml`

**Inputs**: unchanged (`verdict`, `verdict-reason` already accept
arbitrary strings, passed through display-only).

**Behavioral contract change**:

- The outcome-resolution `case "$VERDICT" in healthy|exhausted|failed|unclassifiable) ...` allow-list gains `rate-limited` as a fifth accepted literal, mapped straight through (`outcome_val="$VERDICT"`).
- The action's own standalone fallback classifier (used only when no
  `verdict` input is supplied at all) is **not** extended — research.md
  R3. A caller that never wires `wing-commander-agent-verdict` and
  relies on the fallback keeps seeing `failed` for a rate-limited
  transcript, the same pre-existing gap it has for every other
  fallback-only site today; no in-scope call site depends on this path
  (every site was already wired to pass `verdict` by spec 037).
- The rendered `**Verdict**: %s — %s` line is unchanged mechanically; it
  now simply renders `rate-limited — usage window (...) exhausted,
  resets at ...` when that's what it's handed, with no new decision
  logic in this action.
- Never-fail contract unchanged.

## Docs (FR-017)

`docs/architecture.md`'s existing paragraph (currently: "a
`wing-commander-agent-verdict` step classifies each run
(healthy/exhausted/failed/unclassifiable) from the transcript alone")
gains the fifth value in the same enumeration, plus one sentence naming
Gate 22's three new cases and the new FR-015b gate (contracts/exemption-gate.md), immediately after the existing Gate 22/23 sentence.
