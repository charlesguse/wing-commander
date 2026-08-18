# Contract: Turn-Ceiling and Agent-Verdict Composites, and the Metrics-Summary Extension

Three pieces, wired together at every one of the 19 call sites in the
same order. This document specifies each piece's interface and the
shared per-site wiring pattern (research.md R7); `data-model.md` defines
the field shapes referenced below.

## `wing-commander-turn-ceiling` (NEW)

`.github/actions/wing-commander-turn-ceiling/action.yml`

**Purpose**: Turn a site's intended turn budget into the literal
runaway-ceiling value handed to `claude-code-action`'s `--max-turns`
flag. The only composite this feature adds that fails its own step.

**Inputs**:

| Name | Required | Default | Notes |
|---|---|---|---|
| `intended-turns` | yes | — | Must resolve to a positive integer. |
| `multiplier` | no | `2.5` | research.md R1. |

**Outputs**:

| Name | Type | Notes |
|---|---|---|
| `ceiling` | integer (string) | `ceil(intended-turns * multiplier)`. |

**Behavioral contract**:
- Exits non-zero with an `::error::` line naming the offending value
  when `intended-turns` is empty, non-numeric, or `<= 0` — this is
  deliberate: constitution II requires every stage to run under a
  bounded budget, and a call site that can't produce a valid intended
  budget must not silently proceed to an agent step with no real cap.
- Pure arithmetic (`awk`), no network, no repository read beyond its own
  inputs.
- Never rounds down — `ceil`, not truncation, so a small intended
  budget (e.g. 8) never produces a ceiling smaller than
  `intended * multiplier` would suggest (8 * 2.5 = 20 exactly; a
  non-exact product like 15 * 2.5 = 37.5 must ceiling to 38, not 37).

## `wing-commander-agent-verdict` (NEW)

`.github/actions/wing-commander-agent-verdict/action.yml`

**Purpose**: Read one already-produced execution transcript and answer,
deterministically and without a network call or a second agent
invocation, "was this agent run healthy" — replacing the ~8 hand-copied
`is_error`/`subtype` checks this issue's evidence found duplicated
across the fleet (research.md R3/R4).

**Inputs**:

| Name | Required | Default | Notes |
|---|---|---|---|
| `transcript-path` | no | `${{ runner.temp }}/claude-execution-output.json` | Same default as `wing-commander-metrics-summary`, so most call sites need not repeat it. |
| `intended-turns` | yes | — | Same value passed to `wing-commander-turn-ceiling` at this site — used only for the `over-budget` comparison, never to gate the verdict itself. |
| `run-label` | no | `""` | Passed straight through into `reason` text when non-empty, for jobs with more than one agent step sharing a transcript path convention. |

**Outputs**: see `data-model.md`'s "Agent run verdict" table
(`verdict`, `reason`, `counted-turns`, `reported-turns`, `over-budget`,
`subagent-turns`).

**Behavioral contract**:
- Never fails its own step (always `exit 0`) — mirrors
  `wing-commander-metrics-summary`'s existing never-fail contract
  (research.md R4). Callers that need the job to fail on a bad verdict
  add their own step (see "Per-site wiring pattern" below); this
  action's job is to answer the question, never to enforce anything
  from inside itself.
- Verdict classification is exactly the table in research.md R3 — no
  additional heuristics, no reading of any field beyond the last
  `.type=="result"` record's `subtype`/`is_error` and the shared
  turn-count script's output.
- Turn counting calls `.github/actions/_shared/count-turns.sh` via
  `"$GITHUB_ACTION_PATH/../_shared/count-turns.sh"` — never reimplements
  the counting `jq` inline (research.md R5). When that script cannot
  produce a countable total (an unexpected transcript shape),
  `counted-turns`/`reported-turns` are empty and `over-budget` is
  `"false"`, but `verdict` is computed independently from the result
  record and is unaffected — a turn-counting failure never demotes a
  genuinely healthy result to a lesser verdict (spec.md edge case:
  "budget comparison must be suppressed rather than computed from the
  wrong counter").
- Does **not** validate any call site's declared JSON Schema
  (research.md R2) — that remains each site's own existing shape-check
  step, now gated on this action's `verdict` output.

## `wing-commander-metrics-summary` (EXTENDED, additive-only)

`.github/actions/wing-commander-metrics-summary/action.yml`

**New inputs** (both optional, default `""`, backward compatible):

| Name | Notes |
|---|---|
| `verdict` | Pass `${{ steps.<verdict-id>.outputs.verdict }}`. |
| `verdict-reason` | Pass `${{ steps.<verdict-id>.outputs.reason }}`. |

**Behavioral contract change**: when both are non-empty, the rendered
block gains one additional line beneath the existing table, stating the
verdict and reason (FR-012). When either is empty (any caller not yet
updated), rendering is byte-for-byte identical to today — no new
decision logic, no new failure mode, no change to the existing
never-fail contract. Internally, this action's own turn-counting block
is replaced by a call to the same shared `_shared/count-turns.sh` script
`wing-commander-agent-verdict` uses (research.md R5) — a refactor of
*where* the counting logic lives, not a behavior change; Gate 11 is
updated to test the shared script directly and must continue to pass
unchanged against every existing case (`streamed chunks count once`,
`subagent turns excluded`, `exhaustion is called out`, `warning
boundary`, `no budget no ratio`, `uncountable transcript`, `never
fails`).

## Per-site wiring pattern

Applied identically at all 19 call sites (research.md R7); shown here
against a representative site (`clarify.yml`'s `agent` step) — every
other site follows the same shape with its own step names/ids
substituted:

```yaml
- id: agent-ceiling
  uses: ./.wing-commander-pipeline/.github/actions/wing-commander-turn-ceiling
  with:
    intended-turns: ${{ inputs.max-turns }}

- id: agent
  continue-on-error: true
  uses: anthropics/claude-code-action@v1
  with:
    claude_args: |
      ...
      --max-turns ${{ steps.agent-ceiling.outputs.ceiling }}
      ...

- id: agent-verdict
  if: always() && steps.agent.outcome != 'skipped'
  uses: ./.wing-commander-pipeline/.github/actions/wing-commander-agent-verdict
  with:
    intended-turns: ${{ inputs.max-turns }}

# existing shape-check / "Fail on agent API error" / "Verify..." step(s):
# `if:` rewritten from `steps.agent.outcome == 'success'` to
# `steps.agent-verdict.outputs.verdict == 'healthy'`; body unchanged.

- name: Fail loud on non-healthy agent verdict
  if: always() && steps.agent.outcome != 'skipped' && steps.agent-verdict.outputs.verdict != 'healthy'
  env:
    VERDICT: ${{ steps.agent-verdict.outputs.verdict }}
    REASON: ${{ steps.agent-verdict.outputs.reason }}
  run: |
    echo "::error::agent step rejected — verdict=$VERDICT: $REASON"
    exit 1

# existing wing-commander-metrics-summary invocation (added where absent):
# gains `verdict: ${{ steps.agent-verdict.outputs.verdict }}` and
# `verdict-reason: ${{ steps.agent-verdict.outputs.reason }}`.

- name: Report over-budget agent run   # only at sites that already post to a lifecycle issue
  if: steps.agent-verdict.outputs.verdict == 'healthy' && steps.agent-verdict.outputs.over-budget == 'true'
  uses: ./.wing-commander-pipeline/.github/actions/wing-commander-callout
  with:
    kind: info
    summary: "This step used its full intended turn budget."
    body: >-
      Counted ${{ steps.agent-verdict.outputs.counted-turns }} of an
      intended ${{ inputs.max-turns }} turns. The run continued and
      finished successfully — the runaway ceiling
      (${{ steps.agent-ceiling.outputs.ceiling }}) is the only hard
      stop; this is an observability note, not a failure.
```

**The skip guard on both new steps is `steps.<agent>.outcome !=
'skipped'` and nothing else.** Do not restate the agent step's own `if:`
conditions there — a copy drifts the moment either side gains a
condition, and when it does, an ordinary skip (the agent step correctly
declining to run) produces `verdict: unclassifiable`, which the fail-loud
step reads as a defect and fails an otherwise-green job over. Two sites
shipped with exactly that drift and had to be corrected: `finalize.yml`
(verdict gated on `is-open`, agent step also required
`steps.diff.outputs.skip != 'true'`, so every idempotent no-diff re-run
went red) and `auto-update-spec-kit.yml` (verdict gated on `resumed`,
agent step also required `steps.guard.outputs.skip != 'true'`, so every
deduped run went red). The agent step's `outcome` already reflects every
guard on that step, so it cannot drift by construction (PR #221 review).

Validated per user story and edge case in `../quickstart.md`.
