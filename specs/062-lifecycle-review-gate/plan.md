# Implementation Plan: The Review That Clears the Check — An Automated Code Review Gates the Lifecycle's Merge-Worthy PRs

**Branch**: `spec/062-lifecycle-review-gate` | **Date**: 2026-09-26 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/062-lifecycle-review-gate/spec.md`

## Summary

One new, repository-only workflow, `lifecycle-review-gate.yml` (no
`workflow_call` trigger, scheduled + `workflow_dispatch`, the
`board-loop.yml`/`auto-release.yml` shape per research.md D1), reviews the
final implementation pull request of a feature lifecycle once every
condition the pipeline already uses to call it ready is re-derived green
on its exact head SHA. The reviewer step invokes Claude Code's packaged
`code-review` capability through the Skill tool rather than a bespoke
prompt (FR-007, research.md D3), posts a `COMMENT`-only review (the same
constraint and mechanism `board-loop.yml`'s reviewer already uses), and
restates its findings in the pipeline's existing structured-finding shape
(`.github/schemas/board-review-finding.schema.json`, reused unmodified —
FR-010). A clean round reports a passing status on the head SHA (FR-013);
a not-clean round folds its in-scope findings into the *existing* fold
mechanism spec 042 owns and files its out-of-scope findings through the
existing durable-failure-issue path (FR-016/FR-019).

Because no composite action owns spec 042's fold logic today — it is
split across `pr-conversation.yml`'s agent-driven `act` job and its
deterministic `dispatch-once` job — reaching that path directly (FR-017)
requires extracting two shared homes this feature's own call site and
`pr-conversation.yml`'s existing call site both consume (research.md
D8–D10): `wing-commander-fold-commit` (append a tasks.md section, flip
`spec-meta.json.stage` back to `implement`, record `pending_re_review_from`,
commit as `fold(<id>): <summary>`) and `wing-commander-fold-dispatch`
(bump `spec-meta.json.iteration`, dispatch `implement.yml` once, record
fold evidence — today's `dispatch-once` job body). `pr-conversation.yml`'s
`act` job still drafts a tasks.md section with an agent, because
interpreting a human's free-text review remains a judgment call; this
gate's own findings are already structured, so its own step renders the
section deterministically and both paths hand the result to the same two
composites. Round state (round number, reviewed head SHA, outcome, open
finding count, folded/filed fingerprints) lives in a new `review_gate`
object on `spec-meta.json`, the same durable-state home `iteration`
already occupies (data-model.md §1).

Auto-merge (User Story 4) is new code with no executable prior art: the
board loop's own merge invariant check
(`verify-board-readiness.py::check_no_merge_invariant`) proves the
repository has never called `gh pr merge` from pipeline code before. It
ships behind two independent, off-by-default gates — a kill switch
(`WING_COMMANDER_LIFECYCLE_REVIEW_GATE_PAUSED`, stopping review and merge
alike, FR-034) and a separate enable switch
(`WING_COMMANDER_LIFECYCLE_AUTO_MERGE`, FR-024) — and a merge is attempted
only after a dedicated precondition script re-derives every FR-026
condition, including two the board loop's readiness function has no
analogue for today (`mergeable`, and "no unresolved human
changes-requested review"). A deterministic gate (`verify-constitution-
merge-class-parity.py`, FR-038) fails if this capability's code exists in
the tree while `.specify/memory/constitution.md` does not name the third
merge class; the amendment itself (FR-031–FR-033) is a separate,
human-merged PR against `main`, outside this spec branch's own file scope.

See [research.md](./research.md) (D1–D16), [data-model.md](./data-model.md),
and [contracts/](./contracts/) for the full design.

## Technical Context

**Language/Version**: YAML (the new workflow and composite actions), Bash
(`run:` steps, the existing convention), Python 3 (new `verify-*.py` gates
and the two new decision scripts, matching every existing
`.github/scripts/` script), JSON Schema (draft 2020-12 — reused, not
added: `board-review-finding.schema.json`).

**Primary Dependencies**: `anthropics/claude-code-action@v1` (existing, no
new secret or credential class — FR-007's Claude Code `code-review`
capability is reached by granting the `Skill` tool in the same action's
existing `claude_args`/tool-allowlist surface, research.md D3), `gh` CLI
under the existing wing-commander-bot GitHub App token
(`wing-commander-context`), `git`, `jq`. No new third-party package.

**Storage**: `spec-meta.json` on each spec's persistent branch gains one
new object, `review_gate` (data-model.md §1) — the same durable-state home
`iteration` and `pending_re_review_from` already occupy. No new file, no
database; a review round's own transcript/metrics artifact follows the
existing `claude-execution-output.json` convention every agent step
already produces.

**Testing**: Every new decision script (`lifecycle_readiness.py`,
`lifecycle_merge_preconditions.py`) carries an embedded self-test mode
against checked-in fixtures, mirroring `board_readiness.py` /
`verify-board-readiness.py`'s six-case shape (contracts/gates.md); each
new composite (`wing-commander-fold-commit`, `wing-commander-fold-dispatch`)
gets a `tests/run-tests.sh` harness matching
`wing-commander-stage-findings/tests/`; every new gate registers in
`lint-workflows.yml` so `run-local-gates.py` (constitution VIII, FR-037)
picks it up automatically; `quickstart.md` carries the manual drills that
need a real dispatched run (a clean round, a findings round that folds and
re-reviews, a merge with the setting on and off).

**Target Platform**: GitHub Actions (`ubuntu`-class runners), this
repository's own self-checkout composite-action model. The new workflow is
repository-only (no `workflow_call`), the same layer `board-loop.yml` and
`auto-release.yml` already occupy (research.md D1).

**Project Type**: Reusable GitHub Actions pipeline (single project; no
frontend/backend split; "source" is workflows, composite actions, and gate
scripts).

**Performance Goals**: Zero review invocations attributable to an
implement ⟲ converge cycle or the boundary between cycles (SC-002); at
most one review round per distinct reviewed head SHA (SC-009, FR-004/005)
— the selection step's cheapest read (`spec-meta.json.review_gate.head_sha`
vs. the PR's current `headRefOid`) MUST short-circuit before any billable
agent invocation, the same discipline `board_eligibility.py` already
proves for the board loop's own "no eligible issue" case.

**Constraints**: The gate MUST NOT attach to the spec or plan pull request
(FR-002) — enforced by requiring `spec-meta.json.stage == "review"`, a
value only `finalize.yml` ever sets, rather than a branch-name heuristic.
No web tool on any invocation this feature adds (matching FR-057 of spec
057, carried forward by convention). The gate MUST NOT widen the
pull-request-conversation wrapper's bot-author exclusion or add it a
`workflow_dispatch` entry point (FR-018) — this feature makes zero edits
to `wing-commander-9-pr-conversation.yml`. Auto-merge MUST NOT run before
the constitution names the class (FR-031, enforced structurally by
FR-038's gate). Every new agent invocation declares an explicit model and
a bounded turn budget (constitution II, FR-009).

**Scale/Scope**: One new repository-only workflow
(`lifecycle-review-gate.yml`); two new composite actions extracted from
`pr-conversation.yml` (`wing-commander-fold-commit`,
`wing-commander-fold-dispatch`) that `pr-conversation.yml` is edited to
consume instead of its current inline job bodies; one new composite
promoted from `board-loop.yml`'s existing COMMENT-review idiom
(`wing-commander-post-review-comment`) that `board-loop.yml` is edited to
consume; two new decision scripts (`lifecycle_readiness.py`,
`lifecycle_merge_preconditions.py`) each with a paired gate; one new gate
checking constitution/capability parity
(`verify-constitution-merge-class-parity.py`); one new gate checking the
fold-dispatch wiring travels with the findings-drafting step
(`verify-lifecycle-review-gate-fold-wiring.py`, mirroring Gate 72's
shape); one `spec-meta.schema.json` field addition (`review_gate`); two
new repository variables (`WING_COMMANDER_LIFECYCLE_REVIEW_GATE_PAUSED`,
`WING_COMMANDER_LIFECYCLE_AUTO_MERGE`) plus a model-tier variable
(`WING_COMMANDER_LIFECYCLE_REVIEW_GATE_MODEL`, default `claude-sonnet-5`);
a separate, human-merged constitution-amendment PR outside this spec
branch's file scope (FR-033). No change to any of the eight published
lifecycle stages' `workflow_call` interfaces.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Result |
|---|---|---|
| I. Guide — repo is its own first example | Built through the pipeline itself (issue #476 → this spec → this plan → tasks → implement); the worked example spec.md's Overview names (issue #473 / PR #475's hand-run review-fold-merge loop) is the acceptance shape quickstart.md's drills re-run. | ✅ Pass |
| II. Cost-Conscious Model Tiering | The reviewer declares an explicit model (`WING_COMMANDER_LIFECYCLE_REVIEW_GATE_MODEL`, default `claude-sonnet-5` — implementation-weight, matching the board loop's own reviewer tier) and a bounded `--max-turns` via `wing-commander-turn-ceiling` (FR-009). No new premium-tier default. | ✅ Pass |
| III. Simple, GitHub-Native Interaction | Every round's outcome is a PR review comment plus a lifecycle-issue comment naming round, head SHA, finding count and result (FR-015); every merge is announced the same way (FR-029); a maintainer stops the whole feature with one repository variable (FR-034), no dashboard. | ✅ Pass |
| IV. Automation-First | A ready lifecycle PR is reviewed, folded, re-reviewed and (opt-in) merged without a human between rounds (US1–US2); every manual handover this feature cannot close — budget exhaustion, a credential-scope refusal — is reported explicitly to the lifecycle issue, never silently assumed (FR-022, FR-030). | ✅ Pass |
| V. Security — Untrusted Content Is Never Instructions (NON-NEGOTIABLE) | PR titles/bodies/diffs/comments are framed to the reviewing agent as data, never instructions (FR-011). The bot-author exclusion in `wing-commander-9-pr-conversation.yml` is left untouched and gains no dispatch entry point (FR-018) — this feature reaches the fold path by calling its logic directly (FR-017), never by posting a review the wrapper would have to trust. Auto-merge is the third bot-mergeable class Principle V's own sentence must name before it may run at all (FR-031, FR-038 gates this structurally). | ✅ Pass |
| VI. Portability | Every new artifact lives under this repository's own `.github/{workflows,actions,scripts}`, resolved the same self-checkout way every existing composite is. | ✅ Pass |
| VII. Two Interfaces | `lifecycle-review-gate.yml` carries no `workflow_call` trigger (research.md D1) — not part of the published surface, the same choice spec 057 made for `board-loop.yml`. The two composites extracted from `pr-conversation.yml` and the one promoted from `board-loop.yml` are new internal composites with no adopter-pinned interface prior to this feature. No published stage's `workflow_call` input/output/secret is removed or renamed. | ✅ Pass |
| VIII. A Green Check Means What It Says | Every new script is reachable through the gate registry, runs the same subject with the same arguments locally and in CI (`run-local-gates.py`), fails loudly rather than passing vacuously when its subject is unreachable, and ships a checked-in fixture per failure branch (FR-037, contracts/gates.md). | ✅ Pass |
| IX. Judgment That Gates a Durable Action Belongs in Deterministic Code | Whether a round is clean, whether to fold or file a finding, whether a finding is a duplicate across rounds (FR-021), whether every merge precondition holds (FR-026) — each is deterministic code re-deriving its own answer from a fresh GitHub read or from `spec-meta.json`, never the reviewing agent's own judgment on its findings' disposition. | ✅ Pass |
| X. Bounded Autonomy — The Pipeline Works Its Own Board | This feature is deliberately outside X's own board loop — it operates the feature lifecycle's final PR, not an open issue — and copies X's fix-PR-merge *shape* (checks green on exact head SHA, independent review with zero open findings, kill switch, squash commit one human action reverts) for its own third class rather than reusing X's board-loop code, because X's own merge implementation does not exist yet either (research.md D13). | ✅ Pass |

No violations. **Complexity Tracking is intentionally near-empty**: the
two extractions from `pr-conversation.yml` and the one from
`board-loop.yml` are CLAUDE.md's "single home" rule applied at the exact
point FR-017/FR-035 require it, not complexity invented for this feature.

**Post-Phase-1 re-check**: Unchanged. Phase 1 design confirms every new
piece of state lives in `spec-meta.json` (already this stage's own
lifecycle state) or in a job/step output (ephemeral); the one new
untrusted-input surface (the PR diff/title/body handed to the reviewer)
is the same surface `board-loop.yml`'s reviewer already reads under the
same "framed as data" discipline (FR-011); no principle re-opened by the
concrete shapes Phase 1 chose.

## Project Structure

### Documentation (this feature)

```text
specs/062-lifecycle-review-gate/
├── plan.md                                  # This file
├── research.md                              # Phase 0 output — D1-D16
├── data-model.md                            # Phase 1 output
├── contracts/                               # Phase 1 output
│   ├── lifecycle-review-gate-workflow.md
│   ├── review-and-findings.md
│   ├── readiness-and-merge.md
│   ├── fold-integration.md
│   ├── constitution-amendment.md
│   └── gates.md
├── quickstart.md                            # Phase 1 output
├── checklists/requirements.md               # from intake, unchanged
└── spec-meta.json
```

### Source code (repository root)

This repository is a GitHub Actions pipeline; "source" is workflows,
composite actions, and gate scripts — there is no `src`/`tests` split.

```text
.github/
├── workflows/
│   ├── lifecycle-review-gate.yml         # NEW — repository-only, scheduled
│   │                                      #   + workflow_dispatch (no
│   │                                      #   workflow_call, research D1)
│   ├── pr-conversation.yml               # EDITED: act's per-leg
│   │                                      #   commit/flip and
│   │                                      #   dispatch-once's bump/dispatch
│   │                                      #   now call the two new
│   │                                      #   composites instead of their
│   │                                      #   own inline bodies (FR-017)
│   ├── board-loop.yml                    # EDITED: reviewer's COMMENT-post
│   │                                      #   step calls the new
│   │                                      #   wing-commander-post-review-
│   │                                      #   comment composite instead of
│   │                                      #   its own inline gh api call
│   └── lint-workflows.yml                # + 4 new gates (readiness,
│                                          #   merge preconditions,
│                                          #   constitution parity,
│                                          #   fold-wiring)
├── actions/
│   ├── wing-commander-fold-commit/       # NEW — extracted from
│   │                                      #   pr-conversation.yml's act job
│   │   └── tests/
│   ├── wing-commander-fold-dispatch/     # NEW — extracted from
│   │                                      #   pr-conversation.yml's
│   │                                      #   dispatch-once job
│   │   └── tests/
│   └── wing-commander-post-review-comment/  # NEW — promoted from
│                                          #   board-loop.yml's reviewer
│       └── tests/
└── scripts/
    ├── lifecycle_readiness.py            # NEW — FR-001/004/005/006
    ├── verify-lifecycle-readiness.py     # NEW gate
    ├── lifecycle_merge_preconditions.py  # NEW — FR-026/027/030
    ├── verify-lifecycle-merge-preconditions.py  # NEW gate
    ├── verify-constitution-merge-class-parity.py  # NEW gate — FR-038
    ├── verify-lifecycle-review-gate-fold-wiring.py  # NEW gate
    └── verify-single-home-idioms.py      # EXTENDED — 3 new DECLARED_HOMES

specs/002-plan-stage/contracts/
└── spec-meta.schema.json                 # EDITED: + review_gate property

.specify/memory/
└── constitution.md                       # Amendment PR, separate from
                                            #   this spec branch (FR-033) —
                                            #   named here for completeness
                                            #   only; not edited by this
                                            #   plan or its branch
```

**Structure Decision**: No new top-level directory. The gate is a single
repository-only workflow file, matching `board-loop.yml`'s own shape,
because it is not part of the published stage contract (VII) — the
auto-merge setting it carries is a per-adopter-repository choice, and this
repository's own constitution is what must authorize the repository's own
bot to exercise it (VI), not something the published surface needs to
expose as a stage. The three extractions are each a second call site
appearing for logic that already had exactly one, per CLAUDE.md's rule;
none is a pre-emptive abstraction.

## Complexity Tracking

*No violations to justify — table intentionally omitted.*
