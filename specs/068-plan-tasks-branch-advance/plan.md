# Implementation Plan: The Plan and Tasks Stages Record Their Own Branch Advance

**Branch**: `068-plan-tasks-branch-advance` | **Date**: 2026-09-26 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/068-plan-tasks-branch-advance/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

`specs/050-branch-drift-sha-baseline` shipped the exact-SHA branch-advance
mechanism for `implement` only, and deliberately shaped the
`branch_advance` record group to be stage-neutral so `plan`/`tasks`
could populate the same fields later "with no contract change" (FR-020
of that spec). This feature is that follow-up (issue #511). Today the
gap is total: `watchdog.yml`'s `collect-branch-drift` step names
`plan`/`tasks`/`implement` as the three push-expected stages but only
implement's dispatched runs ever reach the exact-SHA lookup — a plan or
tasks run's head branch is never the branch it pushes to, so both fall
into the step's existing "the head branch owes no commits — skipping"
arm unconditionally, and neither stage's own workflow captures the
before/after pair at all.

This plan closes the gap with the smallest diff that satisfies FR-011's
"exactly one home" rule: the "after"/"commits" git plumbing
`implement.yml` already has inline is extracted into a new composite,
`wing-commander-branch-advance` (research.md R1), consumed by
`implement.yml` (refactored, values unchanged) and by one new call site
each in `plan.yml` and `tasks.yml`. Plan/tasks gain a small new "before"
capture — a `git rev-parse HEAD` immediately after the existing spec-
branch checkout, which is provably the right value for both review modes
and both the branch-exists and branch-is-created-by-this-run cases with
no special-casing (research.md R2/R4). The composite's outputs feed a
second, transcript-less `wing-commander-metrics-summary` call in each
file, mirroring the pattern implement's own fourth call site already
established.

`watchdog.yml`'s collector widens its existing metrics-record download
and `branch_advance.available` scan to run for all three push-expected
stages (today gated to implement only), always naming the branch from
the record itself — never guessed from a prefix, which would be wrong
for a `pr`-mode plan/tasks run advancing its own review branch
(research.md R5; FR-004). A plan/tasks run with no usable evidence keeps
exactly today's outcome — no signal, no fallback measurement — since
the since-created fallback's baseline branch is only correct in `auto`
mode and guessing it in `pr` mode risks a false detection (research.md
R5; FR-016/FR-017/FR-018). Two stale comments describing the total skip
as permanent are replaced (FR-023; research.md R7).

Every gate this feature touches is an extension of an already-wired
gate — Gate 39 (schema fixtures, no code change needed since the group
is already stage-neutral), Gate 43 (the real composite proven for both
new call sites plus a regression proof that implement's own refactor
changed nothing), Gate 53 (new plan/tasks cases on both the exact-sha
and no-evidence arms), and Gate 60 (a new single-home check for the
extracted composite, per CLAUDE.md's "add the check to the nearest
existing gate"). No new gate script, no new `lint-workflows.yml` wiring
(FR-022 satisfied by construction). No agent invocation is added or
changed anywhere (FR-007; SC-007).

See [research.md](./research.md) for the full decision record (R1–R12),
[data-model.md](./data-model.md) for the concrete shapes, and
[contracts/](./contracts/) for the four delta/coverage documents this
plan produces.

## Technical Context

**Language/Version**: Bash (the new/refactored `run:`/`uses:` steps in
`plan.yml`, `tasks.yml`, `implement.yml`, and the rewritten portion of
`watchdog.yml`'s `collect-branch-drift`), YAML (the new composite
action, its two new call sites), Python 3 (the four extended gate
scripts) — no new language introduced; every touched file already uses
one of these three.

**Primary Dependencies**: `jq`, `git`, `gh` (already the sole
dependencies of every file this feature touches). `wc_gate_registry.py`,
`wc_shell_harness.py` (existing, reused unmodified by Gate 53's
extension). Gate 60's own `DECLARED_HOMES`/waiver/self-test machinery
(existing, reused unmodified except for the one new entry).

**Storage**: The agent run metrics record (schema version 1, additive
only) gains two new populators of an already-existing group; no shape
change. Persisted form is unchanged: one more populated `branch_advance`
group inside a JSONL line on the `metrics` branch, for one new record
per plan run and one new record per tasks run this feature adds — same
`metrics-record-<label>` artifact-naming convention already in use
(e.g. `metrics-record-branch-advance`).

**Testing**: Extended `.github/scripts/verify-metrics-record-schema.py`
(Gate 39, three new fixtures, no code change),
`.github/scripts/verify-metrics-summary-record-emission.py` (Gate 43,
extended), `.github/scripts/verify-branch-drift-sha-baseline.py`
(Gate 53, extended), `.github/scripts/verify-single-home-idioms.py`
(Gate 60, one new check). All run locally via
`python .github/scripts/run-local-gates.py`, identically to CI
(constitution VIII).

**Target Platform**: GitHub Actions `workflow_call` stages,
`ubuntu-latest` runner — `plan.yml`'s and `tasks.yml`'s agent-bearing
jobs (dispatched by `wing-commander-3-plan.yml`/
`wing-commander-4-tasks.yml`), `implement.yml`'s `cycle` job (refactor
only, unchanged behavior), and `watchdog.yml`'s `collect` job, exactly
as today.

**Project Type**: Single project — a GitHub Actions reusable-workflow
pipeline component; no application `src`/`tests` split applies.

**Performance Goals**: No added latency on the common path beyond one
new deterministic step (`git rev-parse HEAD`, negligible) before each
agent step in `plan.yml`/`tasks.yml`, and one new composite invocation
(a `git fetch` + `rev-parse` + `rev-list --count`, all against a
checkout already present) after each. No new agent turn, no new retry
loop, no new network round-trip on the watchdog side beyond the
artifact download the collector already performs for implement.

**Constraints**:
- Additive-only within schema version 1 (FR-009): the `branch_advance`
  group's shape is unchanged; only its set of populators grows and its
  "before" field's stated meaning widens (FR-005), a widening every
  already-persisted value already satisfies.
- Zero new agent turns anywhere (FR-007); every new decision point — the
  mode-to-branch mapping, the composite's fetch/rev-list, the
  collector's widened lookup and its per-stage fallback choice — is
  deterministic code.
- The capture has exactly one home (FR-011), enforced structurally by
  Gate 60 (FR-012) rather than by convention alone.
- The collector's per-stage fallback asymmetry (implement keeps
  since-created; plan/tasks get none) must not regress implement's own
  behavior for a record that predates this feature (FR-017/FR-018).
- The two stale watchdog comments naming the skip as permanent must be
  replaced, not merely supplemented (FR-023) — CLAUDE.md's load-bearing-
  comments rule applies.

**Scale/Scope**: One new composite action
(`.github/actions/wing-commander-branch-advance/action.yml`); one
workflow's existing step refactored to consume it
(`.github/workflows/implement.yml`, values unchanged); two workflows
each gain one new pre-agent step and one new post-agent call site
(`.github/workflows/plan.yml`, `.github/workflows/tasks.yml`); one
workflow's one collector step is widened
(`.github/workflows/watchdog.yml`, `collect-branch-drift`); one
published contract document gains a further amendment
(`specs/043-durable-metrics-record/contracts/metrics-record-schema.md`,
per this feature's `metrics-record-schema-delta.md`); four existing
gate scripts gain fixtures/assertions, zero new gate scripts, zero new
`lint-workflows.yml` steps. No edits to any wrapper workflow, to
`wing-commander-inspected-run-identity` (its slug resolution already
covers plan/tasks), or to any composite action other than the one new
one and the four extended gate scripts.

### Project Structure

#### Documentation (this feature)

```text
specs/068-plan-tasks-branch-advance/
├── plan.md                                   # This file (/speckit-plan command output)
├── research.md                               # Phase 0 output (/speckit-plan command)
├── data-model.md                             # Phase 1 output (/speckit-plan command)
├── quickstart.md                             # Phase 1 output (/speckit-plan command)
├── contracts/                                # Phase 1 output (/speckit-plan command)
│   ├── metrics-record-schema-delta.md        # delta against specs/043's contract (as amended by specs/050)
│   ├── branch-advance-capture-contract.md    # the new wing-commander-branch-advance composite's own contract
│   ├── branch-drift-collector-delta.md       # delta against specs/050's own collector delta
│   └── gate-coverage-068.md                  # Gate 39/43/53/60 extensions
├── checklists/
│   └── requirements.md                       # already present (intake stage output)
├── spec-meta.json
└── tasks.md                                  # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

#### Source code (repository root)

This repository is a GitHub Actions pipeline, not a conventional
library/service — there is no `src`/`tests` split. The real layout this
feature touches:

```text
.github/
├── actions/
│   └── wing-commander-branch-advance/        # NEW composite — inputs
│       └── action.yml                        #   branch/before-sha/
│                                              #   before-sha-available;
│                                              #   outputs after-sha/
│                                              #   after-sha-available/
│                                              #   commits/commits-
│                                              #   available. Extracted
│                                              #   from implement.yml's
│                                              #   existing inline bash
│                                              #   (R1) — byte-identical
│                                              #   git plumbing.
├── workflows/
│   ├── implement.yml                         # "Record branch advance
│   │                                          #   (cycle)" REFACTORED to
│   │                                          #   call the new composite
│   │                                          #   instead of inline bash;
│   │                                          #   before-sha source
│   │                                          #   (steps.base.outputs
│   │                                          #   .base-sha) and every
│   │                                          #   recorded value UNCHANGED
│   │                                          #   (FR-011).
│   ├── plan.yml                               # NEW step "Record branch
│   │                                          #   tip before agent"
│   │                                          #   (~after line 673, before
│   │                                          #   either agent step —
│   │                                          #   R2). NEW step "Record
│   │                                          #   branch advance (after
│   │                                          #   agent)" (~after line
│   │                                          #   1043, before "Compute
│   │                                          #   agent run verdict" —
│   │                                          #   R3), calling the new
│   │                                          #   composite then a
│   │                                          #   transcript-less
│   │                                          #   wing-commander-metrics-
│   │                                          #   summary call. NEW
│   │                                          #   "Upload metrics record
│   │                                          #   (branch advance)" step.
│   ├── tasks.yml                              # Same two new steps as
│   │                                          #   plan.yml, in the
│   │                                          #   `tasks` job's `generate`
│   │                                          #   mode path only — the
│   │                                          #   `tasks-approved` job
│   │                                          #   runs no agent step and
│   │                                          #   pushes nothing, so it is
│   │                                          #   out of scope (research
│   │                                          #   finding, confirmed
│   │                                          #   against the shipped
│   │                                          #   job).
│   ├── watchdog.yml                           # collect-branch-drift:
│   │                                          #   the metrics-record
│   │                                          #   download + branch_
│   │                                          #   advance scan (currently
│   │                                          #   implement-only) widened
│   │                                          #   to plan/tasks/implement
│   │                                          #   alike (R5); measure_
│   │                                          #   branch always read from
│   │                                          #   the record's own
│   │                                          #   branch_advance.branch;
│   │                                          #   since-created fallback
│   │                                          #   stays implement-only.
│   │                                          #   Two stale comments
│   │                                          #   replaced (FR-023, R7).
│   └── lint-workflows.yml                     # No new step — Gate 39/
│                                              #   43/53/60's existing
│                                              #   invocations are reused.
└── scripts/
    ├── verify-metrics-record-schema.py         # NO code change; +3
    │                                            #   fixtures (R8)
    ├── fixtures/metrics-record-schema/          # +3 fixture files
    ├── verify-metrics-summary-record-emission.py # +assertions: refactor
    │                                            #   regression proof,
    │                                            #   plan/tasks new call
    │                                            #   sites (Gate 43)
    ├── verify-branch-drift-sha-baseline.py      # +4 scenario functions:
    │                                            #   plan/tasks exact-sha
    │                                            #   hit, plan/tasks
    │                                            #   no-evidence-no-
    │                                            #   fallback (R9)
    └── verify-single-home-idioms.py             # +1 DECLARED_HOMES
                                                   #   entry, +1 check
                                                   #   function
                                                   #   (branch-advance-
                                                   #   capture), +self-
                                                   #   test cases (R10)

specs/043-durable-metrics-record/contracts/
└── metrics-record-schema.md          # further amended per this
                                       #   feature's metrics-record-
                                       #   schema-delta.md (FR-010)
```

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Result |
|---|---|---|
| I. Guide — repo is its own first example | Built through the pipeline itself (issue #511 → this spec → this plan → tasks → implement), closing the exact gap specs/050's own FR-020 named and required to be filed. | ✅ Pass |
| II. Cost-Conscious Model Tiering | This plan runs at `claude-sonnet-5` (planning-weight default). The feature adds no new agent invocation anywhere and changes no existing one's model tier — every new/refactored step is deterministic bash/YAML/Python. | ✅ Pass |
| III. Simple, GitHub-Native Interaction | No new interaction surface. The watchdog's emitted finding still lands wherever findings land today (unchanged, Out of Scope); the step summary — already a GitHub-native surface — states which basis (measured vs. no-evidence) a plan/tasks run used (FR-016). | ✅ Pass |
| IV. Automation-First | Closes a detection gap fully automatically for two more stages — no new manual step, no new confirmation. | ✅ Pass |
| V. Security — untrusted content is never instructions | No new trust boundary: every new input into the new composite and the two new call sites is a literal or a `git`-computed value the stage's own deterministic steps already produce, never issue/comment/PR body text. The watchdog's widened lookup reuses the same artifact-download pattern already in place for implement — no new fork-PR checkout, no new secret, no new web tool. | ✅ Pass |
| VI. Portability — consuming repo owns its artifacts | Unaffected — every edited/added file already lives under `.github/**`, resolved from the pipeline repository's own checkout; no hardcoded repository name, no new resolution mechanism. | ✅ Pass |
| VII. Two Interfaces — published contract vs. consuming instrument | `wing-commander-branch-advance`, like `wing-commander-metrics-summary` before it, is an internal implementation detail three published stage workflows resolve through self-checkout — not itself a `workflow_call` input/output of any of them, so its addition is not a compatibility-surface change. The record shape itself (`contracts/metrics-record-schema.md`) IS a published surface and gains only a further, purely additive/widening amendment (rule 1; FR-005/FR-009). No stage gains a new ambient-state read (`github.event.*`/`vars.*`). No deviation to register. | ✅ Pass |
| VIII. A Green Check Means What It Says | Every gate this feature touches already runs the real shipped subject (the real composite for Gate 43, the real collector step text for Gate 53, a file-system-wide scan for Gate 60) — extended, not duplicated. Gate 60 gains a fixture-backed negative case (a synthetic third paste) proving it can actually fail on the defect it exists to catch, matching the principle's own "every failure branch... exercised by a checked-in fixture" requirement. | ✅ Pass |
| IX. Judgment That Gates a Durable Action Belongs in Deterministic Code | The lost-progress verdict remains a two-string equality check in deterministic bash for all three stages now, not just implement. The one new decision this feature adds — "does this run's stage get a since-created fallback" — is a static `case`/`if` on `RUN_NAME`, not a judgment call. No model is consulted anywhere in the new or widened path. | ✅ Pass |
| X. Bounded Autonomy — The Pipeline Works Its Own Board | Not directly implicated — this feature is a fix-shaped follow-up to an already-accepted spec's own named gap, filed and routed through the ordinary feature lifecycle (plan/tasks/implement), not the board loop. | ✅ Pass |

**Post-Phase-1 re-check**: Unchanged. Phase 1 design (data-model.md,
contracts/, quickstart.md) confirms every new value lives in a step
output (ephemeral, run-scoped), the metrics record (an already-published,
additively-versioned contract surface), or an artifact already
downloaded for an existing purpose — no new untrusted-input path, no new
stage-side ambient-state read, and no principle re-opened by the
concrete shapes chosen in Phase 1.

## Complexity Tracking

*No Constitution Check violations — table intentionally empty.*

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| — | — | — |
