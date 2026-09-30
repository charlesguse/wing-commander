# Contract: Gate 129 — `verify-skill-board-loop-concurrency-claim.py`

## Purpose

Fails the PR-time gate suite when
`.claude/skills/spec-cross-reference/SKILL.md`'s Over-rated example's
structural claim about `board-loop.yml`'s concurrency configuration no
longer matches the file, per FR-001/FR-002/FR-012. This is the mechanical
owner FR-002 requires for that one quote — not a registry, per FR-011.

## Inputs

- `.claude/skills/spec-cross-reference/SKILL.md` (the claim, data-model.md
  `SkillClaim`)
- `specs/060-self-redrive-concurrency/contracts/concurrency-groups.md` (the
  per-job classification, data-model.md `JobClassification`)
- `.github/workflows/board-loop.yml` (the actual structure, data-model.md
  `WorkflowConcurrencyFact`)
- `.github/scripts/skill-example-drift-waivers.json` (data-model.md
  `WaiverEntry`)

Any of the first three files being absent or unreadable is itself a
`subject-missing` finding (loud failure), never a skip — the spec's own
"renamed or split" edge case, and Principle VIII's "a gate that cannot
reach its subject MUST fail loudly rather than report a pass it did not
earn."

## Algorithm

1. Extract `SkillClaim` from SKILL.md (contracts/skill-example-claim.md's
   Verification section).
2. Extract `JobClassification` rows from `concurrency-groups.md`'s table.
3. Extract `WorkflowConcurrencyFact` for every job `board-loop.yml`
   declares.
4. For every `JobClassification` row with `can_select_or_open_fix_pr`:
   compare its `WorkflowConcurrencyFact` against
   `expected_group_ordinary`/`expected_group_directed`/
   `expected_cancel_in_progress`. Emit a `DriftFinding` per mismatch
   (`job-missing-from-group`, `cancel-in-progress-mismatch`,
   `directed-group-mismatch`).
5. For every job classified `can_select_or_open_fix_pr: false` (including
   any job the table does not mention at all): confirm its
   `WorkflowConcurrencyFact` does not place it in `SkillClaim.ordinary_group`
   or `SkillClaim.directed_group`. Emit `unexpected-job-in-group` on a hit.
6. Compare `SkillClaim.job_range_start`/`job_range_end` against the actual
   first/last job (in `board-loop.yml`'s job order) carrying
   `can_select_or_open_fix_pr`. Emit `job-range-mismatch` on any difference
   — this is what makes Acceptance Scenario 2 (a selecting job leaving the
   group) surface even if steps 4-5 alone would not name the range itself
   as wrong.
6a. Compare `SkillClaim.ordinary_group`/`directed_group` themselves against
   the group names `concurrency-groups.md`'s table actually assigns capable
   jobs (steps 4-5 only ever compare a job's real group against the table's
   expected name, never either of those against what the skill claims).
   Emit `ordinary-group-name-mismatch`/`directed-group-name-mismatch` on a
   difference — this is what catches a coordinated rename that leaves
   `concurrency-groups.md` and `board-loop.yml` agreeing with each other but
   not with `SKILL.md` (PR #813 review).
7. Load `WaiverEntry` rows. For each `DriftFinding`, if a `WaiverEntry` with
   the same `{property, job}` pair exists, mark it **waived** (still
   printed, not counted as a failure). For each `WaiverEntry` whose
   `{property, job}` pair matches no current `DriftFinding`, emit a
   **stale-waiver failure** (FR-014).
8. Exit non-zero if any un-waived `DriftFinding` or any stale-waiver
   failure exists; exit zero otherwise.

## Failure message shape (FR-006)

Every `DriftFinding` line names both locations and both values:

```
::error::verify-skill-board-loop-concurrency-claim: <property> for job
'<job>' — SKILL.md (.claude/skills/spec-cross-reference/SKILL.md:<line>)
claims <expected>; board-loop.yml (.github/workflows/board-loop.yml:<line>)
has <actual>. Waive with a skill-example-drift-waivers.json entry
{"property": "<property>", "job": "<job>"} naming a tracking issue, or fix
the drift.
```

A stale-waiver failure names the entry's location in the JSON file and
states which property no longer diverges.

## Waiver interaction (FR-013, FR-014, SC-007)

Demonstrated by the self-test (research.md D9, SC-005):

1. Mutate a fixture `board-loop.yml`-shaped fragment so `fix` leaves the
   ordinary group, with an empty waiver set → gate fails, blocking.
2. Add a `WaiverEntry{property: "job-missing-from-group", job: "fix",
   issue: "#1"}` → gate passes, printing "waived: job-missing-from-group
   (fix), see #1."
3. Revert the fixture fragment to match (the divergence closes) while
   leaving the same waiver entry in place → gate fails, naming the entry as
   stale.

## Self-test (FR-007)

`--self-test` runs entirely against synthetic fixtures (research.md D9's
list), never the real `board-loop.yml`/SKILL.md — so CI's self-test step
and the real-tree check step are two independently meaningful gate
invocations, the same split `verify-single-home-idioms.py --self-test` vs.
its bare invocation already uses.

## Wiring (Principle VIII)

Registered in `.github/workflows/lint-workflows.yml`'s existing PR-time
lint job, immediately following Gate 124's block (waiver-citation checks
are a natural neighbor), as two steps:

```yaml
- name: Gate 129 — spec-cross-reference's Over-rated example matches board-loop.yml's actual concurrency shape
  if: "!cancelled()"
  run: python3 .github/scripts/verify-skill-board-loop-concurrency-claim.py
- name: Gate 129 self-test — each structural mismatch fails its own mutation, and a stale waiver fails too
  if: "!cancelled()"
  run: python3 .github/scripts/verify-skill-board-loop-concurrency-claim.py --self-test
```

`wc_gate_registry.py`'s `verify-*.py` convention makes both steps visible
to `run-local-gates.py` and `verify-gate-wiring.py` with no separate
registration (FR-010's "no separate invocation to remember").

## Explicitly out of scope for this gate

- Changing `board-loop.yml`'s concurrency configuration (Scope, spec.md).
- Any claim other than this one Over-rated example (FR-011).
- The `.wing-commander-pipeline/` untracked checkout — Gate 129 reads only
  the repo-root-relative paths listed under Inputs, never a glob that could
  match that directory's own nested copy (the spec's own edge case).
