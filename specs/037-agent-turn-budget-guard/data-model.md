# Phase 1 Data Model: Agent Turn Budget Guard

This feature has no application database — every "entity" below is
either a computed shape passed between GitHub Actions steps as
inputs/outputs, or a piece of already-existing transcript data being
read a specific, now-shared way. This is `spec.md`'s Key Entities section
made concrete against the actual composite/gate contracts research.md
designs.

## Agent run verdict

Computed once per agent step by `wing-commander-agent-verdict`
(contracts/agent-verdict-composite.md), consumed by every downstream
step at that call site.

| Field | Type | Values / Shape | Notes |
|---|---|---|---|
| `verdict` | enum (action output, string) | `healthy` \| `exhausted` \| `failed` \| `unclassifiable` | See research.md R3 for the full transcript-state → verdict mapping. Only `healthy` means "continue as success." |
| `reason` | string (action output) | Free text, e.g. `"terminal result subtype=success, is_error=false"`, `"transcript missing or unparseable"`, `"is_error=true"`, `"no terminal result record"`, `"runtime cut off at the N-turn ceiling"` | Rendered in the step summary (via metrics-summary's new passthrough, R6) and in the "Fail loud" step's `::error::` message. |
| `counted-turns` | integer or empty string (action output) | Distinct main-loop assistant `.message.id` count, subagent excluded — identical rule to `wing-commander-metrics-summary`'s existing `main_turns` | Empty when turn counting itself fails (unreadable transcript shape) — never a fabricated zero. |
| `reported-turns` | integer or empty string (action output) | The transcript's own `.num_turns` | Display/diagnosis only — never used for any `if:` condition anywhere (FR-006, "Reported turns" Key Entity). |
| `over-budget` | boolean-as-string (action output) | `"true"` \| `"false"` | `true` only when `verdict == 'healthy' && counted-turns >= intended-turns`. Always `"false"` when counting failed or the verdict isn't healthy — over-budget is a fact *about* a healthy run, not a second failure signal (spec.md edge case: "the verdict must not collapse them into one"). |
| `subagent-turns` | integer or empty string (action output) | Passthrough of the same subagent count `wing-commander-metrics-summary` already reports | Carried through so the verdict composite alone is sufficient evidence for FR-012 even at the 5 sites gaining metrics-summary for the first time. |

State transitions: none — the verdict is computed fresh from one
transcript file per invocation and never mutated or persisted. Edge
case "a job runs more than one agent step and they share a transcript
path" (spec.md) is handled the same way `wing-commander-metrics-summary`
already handles it: each verdict step runs immediately after its own
agent step, before any later agent step in the same job overwrites the
shared transcript path (R7 step 3's ordering requirement).

## Counted turns / Reported turns

Not separate entities from the verdict's own fields above — restated
here because spec.md's Key Entities lists them independently. Both are
produced by the shared `.github/actions/_shared/count-turns.sh` script
(research.md R5), called identically by `wing-commander-agent-verdict`
and `wing-commander-metrics-summary`. Counting rule (unchanged from the
action that already implements it correctly):

```
main_turns  = count(distinct .message.id where .type=="assistant" and (.parent_tool_use_id // null) == null)
sub_turns   = count(distinct .message.id where .type=="assistant" and (.parent_tool_use_id // null) != null)
reported    = (last .type=="result" record).num_turns
```

## Intended turn budget / Runaway ceiling

| Field | Type | Where declared | Notes |
|---|---|---|---|
| `intended-turns` | integer, required | Each call site's existing `--max-turns` source — a `workflow_call` input (8 sites: `clarify`, `cleanup`, `finalize`, `implement` cycle/retry, `intake`, `plan`, `rebase`, `tasks`) or a literal (`implement` progress-comment: 15; `watchdog` diagnose/propose-fix: 30/30; `auto-update-spec-kit`'s 3 sites: 30/20/8) | Unchanged meaning and unchanged source — this feature does not rename or move where a site's intended budget comes from, only what happens to it next (research.md, Technical Context "Constraints"). |
| `multiplier` | float, optional (default `2.5`) | `wing-commander-turn-ceiling`'s own input default | Single source of truth for the whole fleet (research.md R1); overridable per site only if a specific site's own future evidence justifies a different margin — no site overrides it at this feature's landing. |
| `ceiling` | integer (action output) | `wing-commander-turn-ceiling`'s only output | `ceil(intended-turns * multiplier)`. The literal value that reaches `claude_args`' `--max-turns` flag at every site. |

`wing-commander-turn-ceiling` is the one composite in this feature that
**fails its own step** (`exit 1`) when `intended-turns` is absent,
non-numeric, or `<= 0` — every other piece of this feature follows the
never-fail-the-step convention, but constitution II's "no stage may run
without a bounded turn budget" makes an unbounded ceiling a
configuration error worth stopping the job over, before any cost is
spent on the agent step it gates (mirrors `wing-commander-preflight`'s
existing fail-fast posture, cited in `026-configurable-tool-lists/plan.md`).

## Agent call site

The unit Gate 23 (contracts/coverage-gate.md) enumerates and asserts
coverage over — not a maintained list anywhere in the repository
(research.md R8/R9: derived dynamically, matching this codebase's
existing "derive, don't hardcode" convention for Gates 6/7/12).
Re-enumerated during this plan (research.md R8); the 19 sites as of this
plan's writing:

| Workflow | Step id | Schema declared? | Posts to a lifecycle-style issue? | Intended turns |
|---|---|---|---|---|
| `clarify.yml` | `agent` | Yes | Yes | 40 |
| `cleanup.yml` | `summarize` | No | Yes | 20 |
| `finalize.yml` | `summarize` | No | Yes | 20 |
| `implement.yml` | `cycle` | No | Yes | 180 |
| `implement.yml` | `retry` | No | Yes | 180 |
| `implement.yml` | `progress` | No | Yes | 15 |
| `intake.yml` | `agent` | Yes | Yes | 50 |
| `plan.yml` | `agent-auto` | No | Yes | 110 |
| `plan.yml` | `agent-pr` | No | Yes | 110 |
| `pr-conversation.yml` | `agent` (classify) | Yes | Yes | 40 |
| `pr-conversation.yml` | `agent` (act) | Yes | Yes | 40 |
| `rebase.yml` | `agent` | No | Yes (escalation path) | 50 |
| `tasks.yml` | `agent-auto` | No | Yes | 60 |
| `tasks.yml` | `agent-pr` | No | Yes | 60 |
| `watchdog.yml` | `diagnose` | Yes (dynamic) | No (posts to a findings issue, not a spec lifecycle issue) | 30 |
| `watchdog.yml` | `propose-fix` | No | No | 30 |
| `auto-update-spec-kit.yml` | `decide` (upgrade path) | Yes | No (posts to the upgrade-tracking issue) | 30 |
| `auto-update-spec-kit.yml` | `decide` (e2e stage) | No | No | 20 |
| `auto-update-spec-kit.yml` | `interpret` | Yes | No (posts to the upgrade-tracking issue) | 8 |

"Posts to a lifecycle-style issue" governs whether R7 step 6 (the
over-budget callout) applies at that site — all 19 sites still get the
verdict/ceiling/fail-loud wiring (R7 steps 1-5) regardless, since FR-017
requires the over-budget report "in the run's own summary" universally
and "additionally on the lifecycle issue... for stages that post there."

Explicitly **not** call sites for this feature (research.md R8):
`claude.yml:37`, `claude-code-review.yml:37` — no `--max-turns` declared
today, structurally different (interactive GitHub-App triggers, not
pipeline stages), out of scope with a documented follow-up
recommendation rather than silent inclusion or silent exclusion.

## Upstream report

A single Markdown document, `specs/037-agent-turn-budget-guard/upstream-report.md`
(research.md R11) — not runtime state, listed here because FR-018/SC-010
treat it as a deliverable artifact with required content:

| Section | Content |
|---|---|
| Addressed to | `anthropics/claude-code-action`, referencing the shipped behavior added in `anthropics/claude-code-action#1607` |
| Evidence | Both observed occurrences (`auto-update-spec-kit.yml`'s absorbed site, and `clarify.yml` run 31918153816 / issue #204) with their exact numbers |
| Divergence sample | The 1.0x-2.3x range this repository's own history shows, with the specific worked example (198 reported vs. 87 counted, 2026-08-06 implement cycle) |
| Proposed fix(es) | The counter mismatch itself (compare `.num_turns` against a documented, counted equivalent, or expose the counted total directly) — described as a report of a bug, not a pull request against that repository |
| Filing status | Explicitly states filing is optional, at the maintainers' discretion (FR-018) — this document's existence, not its filing, is what completes the requirement |
