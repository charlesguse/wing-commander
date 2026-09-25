# Data Model: The Board Loop

This feature persists nothing in a new storage layer (research.md D21):
every entity below is read back from GitHub Issues/PRs, a run's own
transcript, or a checked-in constant. This document gives each of the
spec's Key Entities a concrete field-level shape.

## Board Item

The unit of work one run selects and acts on.

| Field | Type | Source | Notes |
|---|---|---|---|
| `issue_number` | int | selection (FR-009) | the originating issue |
| `eligibility_basis` | enum: `maintainer-authored` \| `maintainer-labeled` \| `pipeline-labeled` | `board_eligibility.py` (FR-006/FR-008) | never present for an ineligible issue — selection never reaches one |
| `cited_run` | run URL \| null | issue title/body and trust-filtered comments (wing-commander-issue-context's context-file, #505), read by triage | null for a maintainer-filed issue with no cited run (edge case, spec.md) |
| `step` | enum: `triage` \| `route` \| `fix` \| `review` \| `readiness` \| `awaiting-merge` \| `prove` \| `stalled` \| `closed` | Board Item Marker (contracts/board-item-marker.md) + live GitHub state | the resume point |
| `round` | int, ≥0 | Board Item Marker | fix→review round count, bounded by D18's constant |
| `branch` | string \| null | live `git` state | `fix/<issue_number>-<slug>`, set once cut (FR-023) |
| `pr_number` | int \| null | live GitHub state | set once the fix PR opens (FR-026) |
| `base_sha` | string \| null | fix step's own fetch (D7) | the `origin/main` SHA the branch was cut from |

## Triage Verdict

| Field | Type | Notes |
|---|---|---|
| `outcome` | enum: `closed` \| `handover` \| `proceed` | `closed` only on one of the two grounds below |
| `ground` | enum: `rate_limit` \| `action_bump` \| `already_fixed_proposal` \| `evidence_unavailable` \| null | `already_fixed_proposal` MUST NOT co-occur with `outcome: closed` (FR-012) |
| `evidence` | object | shape depends on `ground` — see below |
| `agent_proposal` | string \| null | recorded verbatim when it disagrees with the gated verdict (edge case: "agent proposes then refuses") |

`evidence` by ground:
- `rate_limit`: `{run_url, rate_limit_event: true, api_error_status: "429", num_turns: 1, cost_usd: 0}` — the exact fields `wing-commander-agent-verdict` already emits.
- `action_bump`: `{workflow_file, action_ref, run_pin, main_pin}` — both pins named, per FR-020's "measured value" discipline generalized to triage.
- `already_fixed_proposal` (hand-over, never a close ground): `{proposed_commit_sha, agent_reasoning}` — recorded on the issue, `board:stalled` applied (FR-012).
- `evidence_unavailable`: `{reason: "expired" | "missing" | "api_error"}` (FR-014).

## Route Decision

| Field | Type | Notes |
|---|---|---|
| `agent_proposal` | enum: `fix` \| `spec` | never widens the backstop's verdict (FR-017) |
| `backstop_verdict` | enum: `fix` \| `spec` | code's own verdict |
| `reason` | enum: `under_threshold` \| `over_threshold` \| `contract_widening` \| `post_push_final_diff_breach` | names the threshold and measured value when re-routing (FR-020) |
| `measured` | object | `{files, lines}` from `wing-commander-size-path-backstop`, plus `contract_touched_paths: []` when `reason == contract_widening` |

## Review Finding

Validated against `.github/schemas/board-review-finding.schema.json`
(contracts/review-and-findings.md). Distinct from spec 056's
`stage-finding.schema.json` (research.md D11) by the addition of
`in_scope`.

| Field | Type | Required | Notes |
|---|---|---|---|
| `title` | string | yes | one line |
| `what` | string | yes | one line, no line breaks |
| `evidence` | object `{file_paths: [string], detail?: string}` | yes | `detail` optional |
| `in_scope` | boolean | yes | drives FR-031 (fixed on the same PR) vs. FR-032 (filed as a new issue) |
| `fingerprint_basis` | object `{file_path, gate_or_artifact}` | yes | same shape/`norm` rule as spec 056's D6 |

## Readiness Decision

| Field | Type | Notes |
|---|---|---|
| `head_sha` | string | the exact SHA every condition below is evaluated against (FR-036) |
| `checks_green` | bool | from a fresh `statusCheckRollup` fetch at this `head_sha`; an empty rollup is `false` (FR-037) |
| `gate_suite_green` | bool | read from the `lint-workflows` check within the same fresh rollup (research.md D13) |
| `open_findings` | int | count of review findings with `in_scope: true` not yet fixed, from the FR-033 structure |
| `backstop_holds` | bool | `wing-commander-size-path-backstop` re-applied to the final diff (FR-018) |
| `ready` | bool | true only when all four above hold and the kill switch is clear |
| `unmet_reason` | string \| null | named per FR-067 when `ready: false` |

## Proof Record

| Field | Type | Notes |
|---|---|---|
| `actions_only` | bool | research.md D15's path-based rule |
| `run_url` | string \| null | set only when a re-drive was dispatched |
| `outcome` | enum: `success` \| `failure` \| `not_dispatched` \| `not_required` | `not_required` when `actions_only: false` |
| `reason` | string | names why no re-drive was needed, or the failing run's terminal conclusion |

## Board Item Marker

The resumable-state artifact (research.md D21). An HTML comment embedded
in the loop's own latest status comment on the issue:

```html
<!-- wing-commander-board-item: {"step":"review","round":2,"pr":123,"branch":"fix/408-board-loop","base_sha":"abc1234"} -->
```

Read by the next run as a fast path only; every run additionally
re-derives `branch`/`pr_number`/PR `state` from live GitHub queries before
taking any durable action, so a missing or stale marker degrades to
"re-derive from GitHub" rather than to undefined behavior or a second
branch/PR (FR-054). See contracts/board-item-marker.md for the exact
read/write contract.

## Configuration Constants (checked in, PR-reviewed — not repository variables)

| Name | Value | Rationale |
|---|---|---|
| Round budget | 5 | research.md D18, the implement⟲converge precedent |
| Board size-and-path backstop | its own `max-files`/`max-lines`, distinct from pr-conversation's 3/40 | research.md D5, spec Assumptions |
| Findings cap per PR review round | unbounded per round (FR-030's bound is on *rounds*, not findings-per-round) | the round budget is the loop's stopping condition, not a per-round cap |

## Repository Variables (kill switch and tier, not checked-in constants)

| Name | Purpose |
|---|---|
| `WING_COMMANDER_BOARD_LOOP_PAUSED` | kill switch (FR-002/FR-051, research.md D2) |
| `WING_COMMANDER_BOARD_LOOP_MODEL` | default model tier, `model:opus` label escalates (research.md D18) |

## New Label

| Label | Applied by | Meaning | Cleared by |
|---|---|---|---|
| `board:stalled` | the loop, on round-budget exhaustion (FR-030), a post-push backstop breach (FR-021), or an already-fixed hand-over (FR-012) | excludes the issue from selection (FR-010) | a human removing the label |
