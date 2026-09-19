# Implementation Plan: Exact-SHA Branch-Drift Baseline for Dispatched Implement Runs

**Branch**: `050-branch-drift-sha-baseline` | **Date**: 2026-09-15 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/050-branch-drift-sha-baseline/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

The implement stage's `cycle` job already computes both halves of the
evidence the watchdog needs — `steps.base.outputs.base-sha` (the spec
branch's tip at cycle start, captured today for an unrelated purpose)
and, after every push a cycle can make (the agent's own, a retry's, and
the deterministic "Record truncated-cycle count" bookkeeping push), the
branch's actual final tip — but no existing step sits after *all* of
those pushes while also being able to emit a metrics record: the three
`wing-commander-metrics-summary` call sites (`cycle`/`retry`/`progress
comment`, step-indexes 0/1/2) are each pinned, by the shared-transcript-
overwrite constraint that already governs them, to run immediately after
their own agent step and strictly before the next one — which places all
three before the bookkeeping push (research.md R2).

This plan adds one new, transcript-less, fourth invocation of the same
composite — "Record branch advance (cycle)", step-index `3` — placed
after "Record truncated-cycle count" and before "Flip stage label". It
passes new, additive, optional composite inputs (`branch`, `before-sha`,
`after-sha`, `commits`, each paired with its own `*-available` input)
that the three existing call sites never pass, so they are unaffected
byte-for-byte. The composite gains one new nested `branch_advance` group
in the record shape — `available`, `branch`, `before_sha`,
`before_available`, `after_sha`, `after_available`, `commits`,
`commits_available` — populated only by the new fourth call site,
`false`/`null` everywhere else (research.md R3, R6; data-model.md).

The watchdog's `collect-branch-drift` step, for the dispatched-implement
arm only, downloads the inspected run's `metrics-record*` artifact (the
same download `wing-commander-inspected-run-identity`'s existing
`record_fallback` already performs) and looks for the record whose
`branch_advance.available` is `true`. When found, the verdict is a pure
string comparison of `before_sha`/`after_sha` — no `git rev-list`, no
window, no re-derivation from the branch's state at inspection time,
which is what closes both the rebase-force-push and the second-run-
masking miss cases by construction (research.md R7; SC-001, SC-003).
When absent (an older record, an expired artifact, a push that never
reached the recording point), the collector falls back to exactly
today's `--since=<createdAt>` mechanism, and the step summary states
which baseline was used (FR-013, FR-018). The two comment blocks
documenting the two miss cases as permanent are replaced with comments
describing the mechanism that now closes them (FR-015; research.md R8).

Gate 39 (`verify-metrics-record-schema.py`) gains the `branch_advance`
group in its required-field maps and the contract's `## Shape` block,
plus seven new fixtures (FR-008). Gate 43
(`verify-metrics-summary-record-emission.py`) gains an assertion that the
real, shipped fourth call site produces a conforming, non-colliding
record. Gate 41 (`verify-metrics-persist-retry.py`) gains one fixture
proving append/dedup/retry is unaffected by the new fields (FR-009). A
new gate (provisionally Gate 53 — the next unused slot at plan time;
confirmed at implementation time per this repository's own convention)
exercises the real, shipped `collect-branch-drift` step text against
synthetic before/after and since-created fixtures, covering both arms
and the already-handled/stalled coexistence path (FR-014; research.md
R9). No agent invocation is added or changed anywhere in this feature
(FR-016; SC-006).

See [research.md](./research.md) for the full decision record (R1–R11),
[data-model.md](./data-model.md) for the concrete shapes, and
[contracts/](./contracts/) for the three delta/coverage documents this
plan produces.

## Technical Context

**Language/Version**: Bash (the `run:` steps added to `implement.yml`
and rewritten in `watchdog.yml`'s `collect-branch-drift` step), YAML
(the new composite inputs/outputs in `wing-commander-metrics-summary`,
the one new call site in `implement.yml`), Python 3 (the extended
`verify-metrics-record-schema.py`/`verify-metrics-summary-record-
emission.py`/`verify-metrics-persist-retry.py` gates and the one new
gate script) — no new language introduced; every file this feature
touches already uses one of these three.

**Primary Dependencies**: `jq`, `git`, `gh` (already the sole
dependencies of every step this feature touches or adds — no new tool
introduced). `wc_gate_registry.py` (existing, reused unmodified — picks
up the new gate by filename convention once it has exactly one `run:`
invocation in `lint-workflows.yml`). `wc_shell_harness.py`-style fixture
harnesses (existing convention, e.g. `verify-fold-dispatch-once.py`,
`verify-finalize-refresh.py`) for the one new gate, since it must
exercise real shipped bash against a real local git repository (the
`collect-branch-drift` step does real `git fetch`/`rev-parse`/
`rev-list` against the fixture remote, matching the discipline
`verify-metrics-persist-retry.py` already applies to persistence).

**Storage**: The agent run metrics record (schema version 1, additive
change only) gains one new nested group, `branch_advance`
(data-model.md). Persisted form is unchanged: one more populated group
inside the same JSONL line on the `metrics` branch, for the one new
record per implement cycle this feature adds. No new file, branch, or
artifact name pattern — the fourth record reuses the existing
`metrics-record-<label>` artifact-naming convention
(`metrics-record-branch-advance`).

**Testing**: Extended `.github/scripts/verify-metrics-record-schema.py`
(Gate 39, new fixtures under `.github/scripts/fixtures/metrics-record-
schema/`), extended `.github/scripts/verify-metrics-summary-record-
emission.py` (Gate 43), extended `.github/scripts/verify-metrics-
persist-retry.py` (Gate 41), one new gate script exercising
`collect-branch-drift`'s shipped text (provisionally Gate 53). All run
locally via `python .github/scripts/run-local-gates.py`, identically to
CI (constitution VIII).

**Target Platform**: GitHub Actions `workflow_call` stages,
`ubuntu-latest` runner — `implement.yml`'s `cycle` job (dispatched by
`wing-commander-5-implement.yml`) and `watchdog.yml`'s `collect` job
(dispatched by `wing-commander-8-watchdog.yml`), exactly as today.

**Project Type**: Single project — a GitHub Actions reusable-workflow
pipeline component; no application `src`/`tests` split applies.

**Performance Goals**: No added latency on the common path beyond one
new deterministic step per implement cycle (a `git fetch` + `rev-parse`
+ `rev-list --count`, all against a ref already fetched earlier in the
same job) and, on the watchdog side, one artifact download for a
dispatched-implement run that the collector doesn't already perform
today — bounded, no retry loop, no new agent turn (SC-006).

**Constraints**:
- Additive-only within schema version 1 (FR-006): no existing record
  field removed, renamed, retyped, or given a new meaning; the three
  existing `wing-commander-metrics-summary` call sites in `implement.yml`
  require zero changes.
- Zero new agent turns anywhere in this feature (FR-016); every new
  decision point — the fourth call site's inputs, the collector's
  SHA-equality verdict, the fallback selection — is deterministic code.
- The new fields are stage-neutral in name and semantics (FR-020): the
  `branch_advance` group is not named or shaped around "implement"
  specifically, so `plan`/`tasks` can populate it later without a
  contract change; only `implement.yml` populates it in this feature.
- Gate 39's `check_fields_match_contract` cross-check (Gate 19's own
  literal-path convention) means the contract's `## Shape` JSON block and
  `verify-metrics-record-schema.py`'s `REQUIRED_*` maps must change in
  the same PR, in lockstep, or Gate 39 fails by construction.
- The watchdog's two miss-case comments (`watchdog.yml` ~704–716) must be
  replaced, not merely supplemented (FR-015) — the checked-in explanation
  must match the checked-in behavior (constitution: "a green check means
  what it says," applied here to a comment rather than a gate).

**Scale/Scope**: One composite action gains seven new optional inputs
and one new record-shape group (`.github/actions/wing-commander-
metrics-summary/action.yml`); one workflow gains one new step and one
new upload step in its `cycle` job (`.github/workflows/implement.yml`,
inserted between "Record truncated-cycle count" and "Flip stage label
(first cycle)"; its three existing metrics-summary call sites are
untouched); one workflow's one collector step is rewritten
(`.github/workflows/watchdog.yml`, `collect-branch-drift`, ~lines
628–805); one published contract document gains the new group
(`specs/043-durable-metrics-record/contracts/metrics-record-schema.md`);
three existing gate scripts gain fixtures/assertions and one new gate
script is added, wired into one new step in `.github/workflows/lint-
workflows.yml`. Zero edits to any wrapper workflow, to
`wing-commander-inspected-run-identity`'s own logic (its output is
reused, not changed), or to any other composite action.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Result |
|---|---|---|
| I. Guide — repo is its own first example | Built through the pipeline itself (issue #331 → this spec → this plan → tasks → implement), closing a gap the repository found on its own runs (34709026525) and documented as permanent in #327/#322. | ✅ Pass |
| II. Cost-Conscious Model Tiering | This plan runs at `claude-sonnet-5` (planning-weight default, per the constitution's tiering). The feature adds no new agent invocation anywhere and changes no existing one's model tier — the fourth metrics-summary call site is transcript-less, deterministic bash; the watchdog's new fallback selection is a string comparison, not a judgment call. | ✅ Pass |
| III. Simple, GitHub-Native Interaction | No new interaction surface. The watchdog's emitted finding still lands wherever findings land today (unchanged, Out of Scope); the step summary — a GitHub-native surface a maintainer already reads — states which baseline was used (FR-013). | ✅ Pass |
| IV. Automation-First | Closes a detection gap fully automatically — no new manual step, no new confirmation. The one path this feature explicitly cannot yet close (plan/tasks populating the same fields, FR-020) is reported, not silently assumed: it becomes a filed follow-up issue rather than a TODO comment (research.md R10). | ✅ Pass |
| V. Security — untrusted content is never instructions | No new trust boundary: every new input into the fourth metrics-summary call site is a literal or a `git`/`gh`-computed value this stage's own deterministic steps already produce, never issue/comment/PR body text. The watchdog's artifact download is the same download `wing-commander-inspected-run-identity` already performs today for the same class of run — no new fork-PR checkout, no new secret, no new web tool. | ✅ Pass |
| VI. Portability — consuming repo owns its artifacts | Unaffected — every edited file already lives under `.github/**`, resolved from the pipeline repository's own checkout; no new resolution mechanism, no hardcoded repository name. | ✅ Pass |
| VII. Two Interfaces — published contract vs. consuming instrument | `wing-commander-metrics-summary` is a composite the published stage contract (`stage-interfaces.md`) does not itself enumerate as a top-level input/output of `implement.yml`'s `workflow_call` interface — it is an internal implementation detail `implement.yml` resolves through self-checkout, so its new inputs are not a `workflow_call` compatibility-surface change. The record shape itself (`contracts/metrics-record-schema.md`) IS a published contract surface (specs/043's own framing) and gains a purely additive group, matching that contract's own compatibility rule 1. No stage gains a new ambient-state read (`github.event.*`/`vars.*`); the collector's new artifact download reuses an existing, already-registered pattern. No deviation to register. | ✅ Pass |
| VIII. A Green Check Means What It Says | Gate 39 is extended (not duplicated) with the new group in the same cross-checked contract/code pair it already enforces. Gate 43 is extended to prove the real fourth call site — not a hypothetical one — actually emits a conforming record. A new gate is added specifically because the collector's rewritten SHA-comparison/fallback logic is genuinely new shipped behavior no existing gate exercises (research confirmed no gate today drives `collect-branch-drift`'s own text); it runs the real step text against real local git-repo fixtures, matching `verify-metrics-persist-retry.py`'s and `verify-finalize-refresh.py`'s established discipline, with a fixture for every failure/fallback branch (FR-008, FR-018; contracts/gate-coverage-050.md). | ✅ Pass |
| IX. Judgment That Gates a Durable Action Belongs in Deterministic Code | The lost-progress verdict is, and remains, a two-string equality check in deterministic bash — this feature does not add or remove any judgment, it replaces one deterministic computation (a timestamp-windowed `git rev-list --count`) with a more precise one (a SHA comparison against the stage's own recorded evidence) and keeps the existing already-handled/stalled short-circuit exactly where it is today (FR-014). No model is consulted anywhere in the new path. | ✅ Pass |

**Post-Phase-1 re-check**: Unchanged. Phase 1 design (data-model.md,
contracts/, quickstart.md) confirms every new value lives in a step
output (ephemeral, run-scoped), the metrics record (an already-published,
additively-versioned contract surface), or an artifact already downloaded
for an existing purpose — no new untrusted-input path, no new stage-side
ambient-state read, and no principle re-opened by the concrete shapes
chosen in Phase 1.

## Project Structure

### Documentation (this feature)

```text
specs/050-branch-drift-sha-baseline/
├── plan.md                                   # This file (/speckit-plan command output)
├── research.md                               # Phase 0 output (/speckit-plan command)
├── data-model.md                             # Phase 1 output (/speckit-plan command)
├── quickstart.md                             # Phase 1 output (/speckit-plan command)
├── contracts/                                # Phase 1 output (/speckit-plan command)
│   ├── metrics-record-schema-delta.md        # delta against specs/043's published record contract
│   ├── branch-drift-collector-delta.md       # delta against watchdog.yml's collect-branch-drift step
│   └── gate-coverage-050.md                  # Gate 39/41/43 extensions + new Gate 53 contract
├── checklists/
│   └── requirements.md                       # already present (intake stage output)
├── spec-meta.json
└── tasks.md                                  # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source code (repository root)

This repository is a GitHub Actions pipeline, not a conventional
library/service — there is no `src`/`tests` split. The real layout this
feature touches:

```text
.github/
├── actions/
│   └── wing-commander-metrics-summary/
│       └── action.yml                 # + 7 new optional inputs (branch,
│                                       #   before-sha, before-sha-available,
│                                       #   after-sha, after-sha-available,
│                                       #   commits, commits-available);
│                                       #   emit_record() gains the
│                                       #   branch_advance group, defaulting
│                                       #   to available:false when the new
│                                       #   inputs are absent (R3).
├── workflows/
│   ├── implement.yml                  # NEW step "Record branch advance
│   │                                   #   (cycle)" (step-index '3'),
│   │                                   #   between "Record truncated-cycle
│   │                                   #   count" (~1900-1958) and "Flip
│   │                                   #   stage label (first cycle)"
│   │                                   #   (~1962) — computes branch/
│   │                                   #   before/after/commits and calls
│   │                                   #   wing-commander-metrics-summary
│   │                                   #   with an intentionally-absent
│   │                                   #   transcript path (R2, R4). NEW
│   │                                   #   step "Upload metrics record
│   │                                   #   (branch advance)" immediately
│   │                                   #   after, mirroring the existing
│   │                                   #   three upload steps. The three
│   │                                   #   existing metrics-summary call
│   │                                   #   sites (894, 1330, 1835) and
│   │                                   #   "Record base SHA" (647, reused
│   │                                   #   as the "before" value)
│   │                                   #   UNCHANGED.
│   ├── watchdog.yml                   # collect-branch-drift (~628-805)
│   │                                   #   rewritten: the two miss-case
│   │                                   #   comments (~704-716) replaced
│   │                                   #   (FR-015); dispatched-implement
│   │                                   #   arm downloads metrics-record*
│   │                                   #   and, when branch_advance is
│   │                                   #   available, compares before/
│   │                                   #   after directly (R7); falls back
│   │                                   #   to today's --since mechanism
│   │                                   #   otherwise, naming the fallback
│   │                                   #   in the step summary (FR-013,
│   │                                   #   FR-018). Signal emission
│   │                                   #   (~791-805) gains the recorded
│   │                                   #   commit count (FR-019);
│   │                                   #   already-handled/stalled
│   │                                   #   short-circuit UNCHANGED
│   │                                   #   (FR-014).
│   └── lint-workflows.yml             # Gate 39, 41, 43 extended in place.
│                                       #   + Gate 53 (provisional number)
│                                       #   — "the branch-drift collector
│                                       #   compares the implement run's
│                                       #   own recorded SHAs, not a
│                                       #   commits-since-run-created
│                                       #   window".
└── scripts/
    ├── verify-metrics-record-schema.py         # + branch_advance to
    │                                            #   REQUIRED_* maps; +7
    │                                            #   fixtures (FR-008)
    ├── fixtures/metrics-record-schema/          # + fixture files (FR-008)
    ├── verify-metrics-summary-record-emission.py # + assertion for the
    │                                            #   4th call site (Gate 43)
    ├── verify-metrics-persist-retry.py          # + 1 fixture proving
    │                                            #   append/dedup/retry
    │                                            #   unaffected (FR-009)
    ├── verify-branch-drift-sha-baseline.py      # NEW — Gate 53's script
    └── wc_gate_registry.py                      # UNCHANGED — picks up
                                                   #   the new gate by
                                                   #   filename convention

specs/043-durable-metrics-record/contracts/
└── metrics-record-schema.md          # + branch_advance group in the
                                       #   `## Shape` and degraded-record
                                       #   examples, per contracts/
                                       #   metrics-record-schema-delta.md
                                       #   (FR-007)
```

## Complexity Tracking

*No Constitution Check violations — table intentionally empty.*

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| — | — | — |
