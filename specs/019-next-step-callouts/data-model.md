# Phase 1 Data Model: Clear Next-Step Callouts

This feature has no runtime data store; its "entities" (per `spec.md`'s Key
Entities section) are realized as the inputs/output shape of the new
`wing-commander-callout` composite action and the call sites that invoke it.
This document specifies their fields, relationships, and validation rules.

## Entity: Action-required callout

A message posted to the lifecycle issue signalling the pipeline is waiting
on a human (spec.md Key Entities). Realized as one invocation of
`wing-commander-callout` with `kind: action`.

| Field | Description | Required |
|---|---|---|
| `issue-number` | The lifecycle issue to comment on | yes |
| `summary` | One-sentence, plain statement of the required action (FR-001) | yes |
| `body` / `body-file` | Additional markdown detail (e.g. clarification questions, a task list, a stall runbook) | no |
| `pr-url` | Direct link to the related pull request (FR-002) | no — omitted only when no PR exists (FR-008, Edge Case "no PR exists") |
| `pr-label` | Short human label for the PR (e.g. "the implementation PR", "the spec PR") shown next to the link | no, defaults to "the pull request" when `pr-url` is set |
| `timing` | When the action should be performed (e.g. "after this PR merges") — FR-007 | no — omitted when the action is immediate |

**Rendering contract** (`contracts/callout-format.md` is the normative
source): wrapped in a GitHub `[!IMPORTANT]` alert block; `summary` is bolded
as the first line; `pr-url`/`pr-label` render as a `**PR:**` line when
present; `timing` renders as a `**When:**` line when present.

**Validation rules**:
- `summary` MUST be non-empty (FR-001 — "plainly states what the person
  needs to do").
- When the human-action moment has an associated open PR, `pr-url` MUST be
  set (FR-002, FR-003) — enforced by the calling workflow's deterministic
  step, not by the composite action itself (the action cannot know whether
  a PR *should* exist for a given call site).
- `timing` is free text, not a structured date/schedule (spec.md's Key
  Entities describes it as e.g. "after merge" — no scheduling system is
  introduced, matching the Assumptions section's "no new machine-readable
  protocol").

## Entity: Informational status message

A message that shares progress/context and explicitly does not require
action (spec.md Key Entities). Two forms exist after this feature:

1. **Migrated informational sites** (only `finalize.yml`'s "no manual work
   remains" case, per `research.md`'s call-site mapping) — realized as
   `wing-commander-callout` with `kind: info`: posts `body`/`summary`
   verbatim, no alert wrapper.
2. **All other existing informational comments** (stage-started, converged,
   plan/tasks-stage summaries, watchdog findings, etc.) — unchanged,
   continue to post directly via `gh issue comment` exactly as today. They
   are already compliant with FR-005 (none of them claim to require action)
   and are out of this feature's scope (research.md).

| Field | Description | Required |
|---|---|---|
| `issue-number` | The lifecycle issue to comment on | yes |
| `summary` / `body` | The informational content | yes |

**Validation rules**: MUST NOT be wrapped in a `[!IMPORTANT]` alert block
and MUST NOT contain the fixed `"Action needed:"` phrase the action-required
template reserves (FR-005) — enforced by construction: only
`wing-commander-callout`'s `kind: action` path ever emits either.

## Entity: Review gate

A point in the lifecycle where an open PR awaits human review (spec.md Key
Entities) — currently exactly two: the spec-phase PR (intake/clarify) and
the implementation/finalize-phase PR (finalize). Not a new stored entity;
realized as the `pr-url`/`pr-label` fields of an Action-required callout at
the two specific call sites in `contracts/callout-points.md` rows 1, 4, 5.

| Field | Description |
|---|---|
| `phase` | `spec` or `implementation` |
| `pr-label` | `"the spec PR"` / `"the implementation PR"` — the two labels rows 1/4 and row 5 use, so both gates read as the "same recognizable format" (Acceptance Scenario 2) |
| `posting stage(s)` | `intake.yml` (opened) and `clarify.yml` (re-announced after clarification answers, if the PR wasn't already announced) for `spec`; `finalize.yml` for `implementation` |

**Relationships**: A Review gate produces exactly one Action-required
callout at the moment its PR opens (FR-003, SC-001 — "exactly one clearly-
marked action-required callout announcing that gate"). If a spec cycles
through `clarify.yml` more than once, only the state transition from
"questions open" to "no questions remain" produces the spec-PR-ready
callout — repeated identical states do not re-post it (Edge Case "repeated
or retried stages": FR-012's append-only, most-recent-wins model still
applies if a later stage genuinely reruns the gate, e.g. a new PR opened
after a rejected draft).

## Entity: Remaining manual task

A unit of residual work surfaced to the lifecycle issue as a human to-do
with associated timing (spec.md Key Entities). Realized as the `body` of the
`finalize.yml` remaining-manual-work Action-required callout (contract row
6) — the existing `finalize-remaining.md` temp file, unchanged in how the
agent populates it, now posted through `wing-commander-callout` with
`timing: "after this PR merges"` fixed for this call site (finalize's
remaining work is by definition post-merge follow-up, since it's reported
inside the pull-request-review action itself).

| Field | Description |
|---|---|
| `items` | One line per unchecked/human-only `tasks.md` item, exactly as `finalize.yml`'s existing agent step already extracts | 
| `timing` | Fixed: `"after this PR merges"` for the finalize call site |

**Validation rules**:
- When `finalize-remaining.md` is non-empty, the callout MUST be `kind:
  action` (FR-006 — framed as human to-dos, distinguished from completed
  pipeline work) with `timing` set (FR-007).
- When empty, the callout MUST be `kind: info` (FR-009 — "No manual work
  remains" is not an action).

## State / lifecycle

None of these entities have persisted state — each is a point-in-time
rendering decision made fresh by the deterministic step immediately
preceding a `wing-commander-callout` invocation, using signals already
computed by that workflow run (whether `spec.md` still has
`[NEEDS CLARIFICATION]` markers, whether `finalize-remaining.md` is
non-empty, whether `gh pr create`/`gh pr list` found a PR). No new field is
added to `spec-meta.json`; the append-only ordering FR-012 requires is
simply "post a new comment," which GitHub's issue timeline already
guarantees is ordered — no sequence number or dedup marker is introduced
beyond the ones (`rebase.yml`'s existing marker) that already exist for an
unrelated purpose (research.md).
