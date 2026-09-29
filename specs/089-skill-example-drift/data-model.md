# Data Model: The Worked Example Outlives Its Code

This feature has no runtime data store (research.md's Storage: N/A). The
"entities" below are the shapes Gate 125
(`.github/scripts/verify-skill-board-loop-concurrency-claim.py`) reads,
derives, and compares — each one a structure the gate's own code holds in
memory for one run, not a persisted record (except `WaiverEntry`, which
lives in tracked JSON).

## SkillClaim

Extracted from `spec-cross-reference/SKILL.md`'s Over-rated example
paragraph (research.md D3).

| Field | Type | Source |
|---|---|---|
| `job_range_start` | str | first backtick-quoted job name in the "X through Y" phrase (expected: `select`) |
| `job_range_end` | str | second backtick-quoted job name in the same phrase (expected: `readiness`) |
| `ordinary_group` | str | the backtick-quoted group name the claim says select-through-readiness jobs join (expected: `wing-commander-board-loop`) |
| `directed_group` | str | the backtick-quoted group name the claim says the directed proof run joins (expected: `wing-commander-board-loop-directed-proof`) |
| `queues_not_cancels` | bool | whether the paragraph asserts the queuing/`cancel-in-progress` property (research.md D6 — present only after the implement-stage wording addition) |
| `location` | (path, line-range) | for FR-006's failure message |

Missing any field (the anchor paragraph itself not found, or a field's
token absent) is itself a divergence: "subject missing," per the spec's own
edge case for a renamed/removed quote, and per FR-007's demonstrated
failing direction — reported the same way a structural mismatch is, not
silently skipped.

## JobClassification

Read from `specs/060-self-redrive-concurrency/contracts/concurrency-groups.md`'s
"Groups, per job" table (research.md D4) — the authoritative list Gate 125
does not re-derive by guesswork.

| Field | Type | Meaning |
|---|---|---|
| `job` | str | job id as it appears in `board-loop.yml` (`select`, `triage`, `route`, `fix`, `review`, `readiness`, `prove-gate`, `prove`, plus any job the table does not mention, e.g. `resolve-model`) |
| `can_select_or_open_fix_pr` | bool | true for the six unconditional jobs and (conditionally) `prove-gate`/`prove`'s ordinary-trigger path; false for every unlisted job |
| `expected_group_ordinary` | str | group the table's "Group (ordinary trigger)" column names |
| `expected_group_directed` | str \| null | group the table's "Group (`directed-stage != ''`)" column names, or null where the table says "n/a" |
| `expected_cancel_in_progress` | bool | always `false` per the table's third column |

## WorkflowConcurrencyFact

Parsed from `board-loop.yml` itself (research.md D5) — the real
`concurrency:` block for each job, not its preceding comment (Gate 101
already owns the comment-text check).

| Field | Type | Meaning |
|---|---|---|
| `job` | str | job id, from the job's own top-level key |
| `group_literal` | str \| null | the literal `group:` value when it is a plain string |
| `group_expression` | str \| null | the raw `${{ ... }}` expression when the value is conditional (only `prove-gate`/`prove` today) |
| `cancel_in_progress` | bool \| null | the literal `cancel-in-progress:` value; null if the job has no `concurrency:` block at all |

## DriftFinding

One per property Gate 125 checks; the unit both the failure message (FR-006)
and the waiver stale-check (D7) key on.

| Field | Type | Meaning |
|---|---|---|
| `property` | str | a fixed vocabulary token: `job-missing-from-group`, `cancel-in-progress-mismatch`, `unexpected-job-in-group`, `job-range-mismatch`, `directed-group-mismatch`, `subject-missing` |
| `job` | str \| null | the job the finding concerns, when applicable |
| `skill_location` | (path, line) | where the skill's claim was read from (or would have been) |
| `workflow_location` | (path, line) | where `board-loop.yml`'s conflicting fact was read from (or would have been) |
| `expected` | str | what the skill's claim (or the classification table, for `unexpected-job-in-group`) requires |
| `actual` | str | what `board-loop.yml` actually has |

A run with zero `DriftFinding`s (after waivers are applied, D7) passes.

## WaiverEntry

Persisted in `.github/scripts/skill-example-drift-waivers.json`, shaped
like every sibling `*-waivers.json` register (Gate 124's generic schema)
plus one field specific to this gate's own stale-check (D7):

| Field | Type | Meaning |
|---|---|---|
| `file` | str | always `.github/workflows/board-loop.yml` today (the one drift subject) |
| `check` | str | always `skill-board-loop-concurrency-claim` (this gate's own identifier, for consistency with sibling registers that name a `check` per entry) |
| `property` | str | one of `DriftFinding.property`'s vocabulary tokens — the specific divergence this entry waives |
| `job` | str \| null | the job the waived divergence concerns, mirroring `DriftFinding.job` |
| `issue` | str \| null | `"#N"` tracking the pending skill update, or `null` with `permanent: true` (Gate 124's XOR rule — FR-013 expects `tracked`, not `permanent`, to be the normal case here, since the whole point is "a human session updates the skill") |
| `permanent` | bool \| absent | per Gate 124's schema |
| `permanent_reason` | str \| absent | per Gate 124's schema, required when `permanent` |
| `decided_by` | str \| list[str] \| absent | optional provenance, per Gate 124's schema |
| `reason` | str | free-text explanation, as every sibling register carries |

`{property, job}` together are the stale-check key (D7): Gate 125 fails if
that pair is not currently present in the run's own computed
`DriftFinding` set, and fails (blocking, unwaived) if a `DriftFinding` with
that pair exists and no entry covers it.

## Relationships

```text
concurrency-groups.md ──(canonical per-job classification)──> JobClassification
                                                                     │
SKILL.md (Over-rated example) ──(extraction, D3)──> SkillClaim       │ compared against
                                                          │           │
board-loop.yml ──(structural parse, D5)──> WorkflowConcurrencyFact ──┘
                                                          │
                                     (SkillClaim, JobClassification,
                                      WorkflowConcurrencyFact) ──> [DriftFinding]
                                                          │
                              skill-example-drift-waivers.json ──> filters/validates [DriftFinding]
                                                          │
                                                     pass | fail (FR-006 message)
```
