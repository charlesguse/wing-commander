# Implementation Plan: One Fold Queue Per PR — Concurrent Stage-9 Runs Stop Cancelling Each Other's Legs and Cycles

**Branch**: `spec/074-serialized-fold-dispatch` | **Date**: 2026-09-26 | **Spec**: [specs/074-serialized-fold-dispatch/spec.md](./spec.md)

**Input**: Feature specification from `specs/074-serialized-fold-dispatch/spec.md`

## Summary

`pr-conversation.yml`'s fold legs (`act`), its single dispatcher
(`dispatch-once`), and `implement.yml`'s `implement`/`stalled` jobs all
share one GitHub Actions concurrency group per spec (`wing-commander-<spec-dir>`).
That primitive holds at most one *running* and one *pending* job; a second
stage-9 run's leg queuing behind a first run's pending leg evicts it rather
than queuing behind it, silently dropping fold-route items and, when the
evicted entrant is a dispatched `implement` run, killing an implement cycle
with no job left alive to report it (PR #414, 2026-09-20).

This plan replaces GitHub's single-pending-slot admission for
*cross-stage-9-run* ordering with a small deterministic ticket ledger — a
per-spec ordered queue recorded as JSON on a dedicated internal git ref,
written and read through the same fetch/commit/push-with-retry idiom
`wing-commander-metrics-persist` already uses for N-way concurrent writers
with no concurrency group at all. Every participant (`act`'s whole fold
phase, `dispatch-once`, `implement`) enqueues a ticket for itself in a new,
non-scarce prerequisite job before it is allowed to even attempt entry into
the existing `wing-commander-<spec-dir>` GitHub concurrency group, which is
otherwise **left unchanged** — it keeps serializing the fold/dispatch/
implement phases against `plan`/`tasks`/`finalize`/`rebase` exactly as
today. Because the ticket ledger admits exactly one ticket-holder at a time
regardless of which run it belongs to, at most one job ever attempts to
become the group's pending entrant at once, so GitHub's eviction rule is
never exercised by two stage-9-family jobs again. The same ledger absorbs
the "exactly one dispatch per overlapping set" requirement (FR-009) as an
atomic claim, and each ticket's own release step records its leg's outcome
and commit SHA directly, replacing the git-log base..tip range scan that
today misattributes a concurrent run's fold commits (FR-006/FR-011). A
new, deliberately agent-free reactor workflow — reusing the `workflow_run:
completed` wiring `watchdog.yml` already has on `implement.yml` — detects
a run cancelled while never having started, distinguishes a concurrency
replacement from an unexplained/manual cancel by deterministic correlation
with another run's state, posts the lifecycle-issue notice, and re-dispatches
at most once (User Story 3, FR-012–FR-016a).

## Technical Context

**Language/Version**: Bash (workflow/composite steps, matching every other
job this plan touches), Python 3 (the new gate script, matching
`.github/scripts/`'s existing convention and reusing its shared
`wc_gha_expr.py`/`wc_shell_harness.py` modules), YAML (workflows/composite
actions).

**Primary Dependencies**: `gh` CLI (ledger reads via `git`, run/job
inspection via `gh api`), no new third-party package. Reuses three existing
idioms rather than inventing new ones: `wing-commander-metrics-persist`'s
fetch/commit/push retry-on-rejection loop (the ledger's write path),
`wing-commander-dispatch-and-wait`'s dispatch-then-correlate-by-token
pattern (the lost-cycle re-dispatch), and `wing-commander-board-stop-check`'s
`gh api repos/.../actions/runs/<id>` run-state read (the never-started /
replaced-vs-manual determination).

**Storage**: One new dedicated internal git ref/branch,
`wing-commander-fold-queue` (research.md D2), holding a single JSON
document keyed by `spec-dir` — no database, no new artifact type beyond
what `git`/`gh` already give every other stage.

**Testing**: Composite-level bash fixtures under each new composite's own
`tests/` directory (matching `wing-commander-stage-findings`'s precedent —
an injectable `git`/`gh` shim, no live network), plus a new gate,
provisionally Gate 99 (`verify-fold-queue-admission.py`, the next
unclaimed gate number as of this plan; the tasks stage fixes the final
number against `lint-workflows.yml` at merge time), built on Gate 70's
load-the-real-expression-and-mutate recipe (research.md D8), plus the
quickstart's post-merge live two-run drill (FR-023/SC-008).

**Target Platform**: GitHub Actions (this repository's existing
self-checkout composite-action model; no new runner class or container).

**Project Type**: Reusable GitHub Actions pipeline (single project; no
frontend/backend split).

**Performance Goals**: Negligible added latency on the uncontended path
(SC-006) — one ledger read plus, at most, one CAS write per participant
when nothing else is queued; no polling loop is entered when a ticket is
already at the head.

**Constraints**: No two jobs that mutate one spec's branch may ever run
concurrently (FR-003, unchanged invariant); the admission mechanism MUST
NOT deadlock even when a ticket holder's job never released its ticket
(FR-018); the published `workflow_call` contracts of `pr-conversation.yml`
and `implement.yml` MUST NOT lose or rename anything, and the one new input
this plan adds (`implement.yml`'s `fold-queue-token`) MUST be optional with
a default that preserves today's behavior when absent (FR-019); every
judgment that gates a durable action (a ticket admission, a stale-ticket
reclaim, a replaced-vs-manual determination, the at-most-once re-dispatch
bound) MUST be deterministic code, never an agent's inference (Principle
IX, FR-015).

**Scale/Scope**: Two existing workflows edited (`pr-conversation.yml`,
`implement.yml`); one new shared shell library
(`.github/actions/_shared/fold-queue-ledger.sh`); three new published
composite actions (`wing-commander-fold-queue-admit`,
`wing-commander-fold-queue-release`, `wing-commander-fold-queue-claim-dispatch`);
one new published stage workflow plus wrapper for the lost-cycle observer
(`fold-cycle-guard.yml`); one new gate script; zero new adopter-facing
required inputs.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

- **I. Guide**: Built as an ordinary spec/plan/tasks/implement/finalize
  cycle through this repository's own pipeline. PASS.
- **II. Cost-Conscious Model Tiering**: No new agent invocation anywhere in
  this design — the ticket ledger, the claim, the reclaim, and the
  lost-cycle observer are all deterministic script code; the one existing
  agent step inside `act` (the fold itself) is unchanged in model tier and
  turn budget. PASS.
- **III. Simple, GitHub-Native Interaction**: The lifecycle issue gains
  exactly the notices FR-012/FR-016 require and loses nothing; a
  maintainer still needs only the issue and the PR to answer SC-005's
  question. PASS.
- **IV. Automation-First**: Ticket admission, reclaim, dispatch claiming,
  and lost-cycle re-dispatch are all automatic; the one deliberately
  manual residue (a second re-dispatch after FR-016a's bound) is reported
  explicitly rather than silently dropped. PASS.
- **V. Security**: No new surface reads issue/comment bodies as
  instructions; the new observer workflow reads only run/job state via
  `gh api` and posts a templated, code-composed notice — no agent, so no
  untrusted-content framing question arises for it. Ledger writes carry no
  secrets. PASS.
- **VI. Portability**: The new ref lives in the consuming repository's own
  git history via the same self-hosted-checkout composite-action model
  every other published composite already uses; nothing is bundled with
  or resolved from Wing Commander itself. PASS.
- **VII. Two Interfaces**: One new optional `workflow_call` input on
  `implement.yml` (`fold-queue-token`, default `''`, preserving today's
  behavior when empty) and three new published composites plus one new
  published stage widen the contract deliberately, not accidentally — a
  MINOR release change, tracked in contracts/workflow-changes.md. No
  existing input, secret, or output is removed or renamed. PASS.
- **VIII. A Green Check Means What It Says**: Gate 99 is reachable through
  the existing registry derivation (`run-local-gates.py` from
  `lint-workflows.yml`, research.md finding #6), is triggered by the
  existing `.github/workflows/**`/`.github/actions/**`/`.github/scripts/**`
  path globs (no new `paths:` entry needed), evaluates the real shipped
  `concurrency:`/`if:` expressions rather than a restatement of them, and
  ships one mutation per named defect so it fails on the pre-fix shape
  (FR-021/FR-022). PASS.
- **IX. Judgment That Gates a Durable Action Belongs in Deterministic
  Code**: This is this feature's organizing constraint, exactly as it was
  spec 056's for a different mechanism — ticket admission order, stale-lease
  reclaim, the dispatch claim, the replaced-vs-manual determination, and the
  re-dispatch-at-most-once bound are all computed by code that reads `gh
  api`/ledger state, never inferred by a model. PASS.
- **X. Bounded Autonomy**: Not exercised — this feature dispatches no
  autonomous merge and changes nothing X governs. N/A.

No violations. **Complexity Tracking is intentionally empty**: the new
ledger, three composites, and observer stage are the direct consequence of
FR-017a's explicit rejection of a single per-PR whole-run group (the one
structurally simpler option GitHub's own primitive would otherwise offer),
not incidental complexity — research.md D1 records the alternatives this
rejects and why each still reproduces the eviction it exists to remove.

## Project Structure

### Documentation (this feature)

```text
specs/074-serialized-fold-dispatch/
├── plan.md                          # This file
├── research.md                      # Phase 0 output — 9 recorded decisions
├── data-model.md                    # Phase 1 output — ledger, ticket, round, notice entities
├── contracts/                       # Phase 1 output
│   ├── fold-queue-ledger-schema.md
│   ├── wing-commander-fold-queue-admit.md
│   ├── wing-commander-fold-queue-release.md
│   ├── wing-commander-fold-queue-claim-dispatch.md
│   ├── fold-cycle-guard.md
│   ├── workflow-changes.md
│   └── gates.md
├── quickstart.md                    # Phase 1 output — validation drills
├── checklists/requirements.md       # from intake, unchanged by this stage
└── spec-meta.json
```

### Source Code (repository root)

This is a GitHub Actions pipeline repository, not an application;
"source" is workflows, composite actions, and gate scripts. No
frontend/backend split applies.

```text
.github/
├── actions/
│   ├── _shared/
│   │   └── fold-queue-ledger.sh              # NEW: CAS read/enqueue/release/claim primitives (single home, FR-020)
│   ├── wing-commander-fold-queue-admit/       # NEW: enqueue-and-await-turn composite
│   │   └── tests/
│   ├── wing-commander-fold-queue-release/     # NEW: release-and-record-outcome composite
│   │   └── tests/
│   └── wing-commander-fold-queue-claim-dispatch/  # NEW: round-emptiness check + atomic dispatch claim
│       └── tests/
├── workflows/
│   ├── pr-conversation.yml         # EDITED: +fold-turn-act/fold-turn-dispatch prerequisite jobs,
│   │                               #   act/dispatch-once unchanged concurrency block + needs:,
│   │                               #   report-fold-outcomes/dispatch-once read ledger records
│   │                               #   instead of the base..tip git-log range
│   ├── implement.yml               # EDITED: +fold-queue-token input (optional, default ''),
│   │                               #   +fold-turn-implement prerequisite job, implement/stalled
│   │                               #   unchanged concurrency block + needs:
│   ├── fold-cycle-guard.yml        # NEW: workflow_call stage, no agent step — the lost-cycle observer
│   ├── wing-commander-9b-fold-cycle-guard.yml  # NEW: workflow_run wrapper, mirrors watchdog's wiring
│   └── lint-workflows.yml          # EDITED: register Gate 99
└── scripts/
    └── verify-fold-queue-admission.py         # NEW: Gate 99

docs/
└── architecture.md                # EDITED if the concurrency-group description needs the new admission layer noted
```

**Structure Decision**: This feature touches no application source tree —
every artifact is a workflow, a composite action, a shared shell library,
or a gate script, following the repository's existing
`.github/{workflows,actions,scripts}` layout exactly. The one new
top-level addition is the `wing-commander-fold-queue` git ref itself,
which is infrastructure data (like the existing metrics ledger branch),
not a tree directory.

## Complexity Tracking

*No violations to justify — table intentionally empty (see Constitution Check).*
