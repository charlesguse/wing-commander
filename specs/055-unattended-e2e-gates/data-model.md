# Data Model: Unattended Passage of the Pipeline's Human Gates in End-to-End Release Verification

Like spec 045's own data model, this feature has no application database —
every entity below is state read from or written to the test repository
(issues, comments, PRs) or carried between steps of the `verify-e2e` job as
job/step outputs. This document gives each entity from the spec's Key
Entities section a concrete shape, and extends spec 045's verdict shape
(`specs/045-auto-release-verified-head/data-model.md`) rather than
replacing it — every field spec 045 already defined keeps its meaning.

## Fixture maintainer identity

| Field | Source | Notes |
|---|---|---|
| `login` | the dedicated GitHub user account's username | Provisioned by a maintainer outside the pipeline (FR-003a); not read by any workflow, only implied by the token below authenticating as it. |
| `token` | repository secret `WING_COMMANDER_AUTO_RELEASE_E2E_MAINTAINER_TOKEN` | Fine-grained PAT, scoped to the test repository alone, Contents/Issues/Pull requests write (research.md D1). Read only by `verify-e2e`. |
| `viewer_permission` | `gh repo view <e2e-repo> --json viewerPermission` using `token` | Checked once at job start (research.md D2); must be `WRITE` or higher or the attempt ends `fail-infra`. |

## Prepared answer

| Field | Value |
|---|---|
| `body` | The fixed markdown literal in research.md D8 — answers "what moment does 'the timestamp' refer to" and "does a repeat run add a file or overwrite one," delegates anything else to the stage's judgment. |
| `posted_by` | Fixture maintainer identity, never the App/bot identity. |
| `round` | 1-indexed count of how many times this exact body has been posted on the current attempt's issue; bounded by `MAX_CLARIFICATION_ROUNDS = 3` (research.md D7). |

## Lifecycle gate (one row per gate, per attempt)

| Gate | Opens when | Harness act | Driven-evidence | Stall classification |
|---|---|---|---|---|
| Clarification | A comment matching the `[!IMPORTANT]` / "Answer the open/remaining clarification questions" marker (research.md D6) appears on the kickoff issue | Post the Prepared answer, once per round | A harness-authored reply comment exists after each such question, before `stage:done` | Round bound exhausted with a question still open |
| Spec-draft PR merge | An open, non-draft PR with head `spec-draft/<slug>` exists | `gh pr merge <n> --merge` once `mergeable`/`mergeStateStatus` allow it | `gh pr list --state merged --head spec-draft/<slug>` returns the PR, with `mergedAt` set | `conflicting`, `blocked`, or `wrong-attempt` (research.md D9/D6) |
| Plan PR merge | An open, non-draft PR with head `plan/<slug>` exists | Same as above | Same as above, prefix `plan/<slug>` | Same as above |
| Finalize PR merge | An open, non-draft PR with head `spec/<slug>` (base = default branch) exists | Same as above | Same as above, prefix `spec/<slug>`; also transitively proven by `stage:done` + `specs/<slug>/{spec,plan,tasks}.md` present (spec 045's existing pass-path checks) | Same as above |

A gate that never opens (no clarification question ever asked) is not a
stall — FR-008 requires the attempt proceed, and this table's Clarification
row above is asserted N/A rather than failing when no marker comment ever
appears.

## Gate evidence (carried in the `report` job's summary, not in the verdict JSON)

| Field | Source |
|---|---|
| `clarification_rounds_answered` | Count of Prepared-answer replies the harness posted this attempt (0 if the gate never opened). |
| `clarification_comment_ids` | The question comment id(s) and the harness's reply comment id(s), when the gate opened. |
| `spec_draft_pr` / `plan_pr` / `finalize_pr` | `{number, merged_at}` for each, gathered per research.md D12, or `null` if a `fail-*` outcome ended the attempt before that gate. |

This is presentation-layer evidence for FR-017/FR-019's legibility
requirement; it does not change `auto-release-verdict.sh`'s six-field JSON
shape (research.md D11/D12 — no schema migration).

## End-to-end verdict (extends spec 045's shape — same six fields, one new `outcome` value)

```jsonc
{
  "outcome": "pass" | "fail-infra" | "fail-timeout" | "fail-incomplete"
           | "fail-wrong-output" | "fail-gate-stall",
  "verified_head": "<head_sha>",
  "failing_check": "<string, e.g. 'clarification' | 'spec-draft PR merge' | null on pass>",
  "expected": "<string, null on pass>",
  "observed": "<string, null on pass>",
  "evidence_url": "<link to the test repository's lifecycle issue>"
}
```

- Every value spec 045 already defined (`pass`, `fail-infra`,
  `fail-timeout`, `fail-incomplete`, `fail-wrong-output`) is unchanged in
  meaning and unchanged at every existing call site.
- `fail-gate-stall` (new): the harness attempted to drive a gate and either
  exhausted its bound (clarification) or the PR it needed to merge reported
  a `conflicting`, `blocked`, or `wrong-attempt` decision (research.md D9,
  D6). `failing_check` names the gate (one of the four names in the
  Lifecycle gate table above); `expected` states what the harness was
  attempting; `observed` states the specific reason. This outcome is
  produced from *inside* the poll loop, as soon as the stall is detected —
  it does not wait for `POLL_BUDGET_SECONDS` to expire (research.md D9),
  which is what makes it distinguishable from `fail-timeout` per SC-010.
- `pass` additionally requires the new clarification-gate assertion
  (research.md D12) alongside every assertion spec 045 already requires.

## Failure report classification (extends spec 045's two-way split to three)

| `outcome` | Classification shown in the durable `auto-release:failed` issue |
|---|---|
| `fail-infra` | "infrastructure" (unchanged) |
| `fail-gate-stall` | "gate stall" (new) |
| every other `fail-*` | "pipeline defect" (unchanged) |

Reuses the existing durable one-report-per-head issue (spec 045's Failure
report entity, `_shared/durable-failure-issue`) — no second reporting
channel (FR-024). The body-building logic gains one new branch for
`fail-gate-stall` that states, per FR-022: which gate, what the pipeline
was waiting for (`expected`), what the harness attempted, and what was
observed instead (`observed`).

## Kill switch (unchanged shape, new resume condition recorded in prose)

Repository variable `WING_COMMANDER_AUTO_RELEASE_PAUSED`, unchanged
mechanically from spec 045 (`"true"` ⇒ every job in `auto-release.yml`
skips via job-level `if:`). This feature adds no new code path for
clearing it — research.md D14 records that as a follow-up, evidence-
carrying PR a maintainer authors once the first unattended run reaches
`stage:done`, per FR-028.
