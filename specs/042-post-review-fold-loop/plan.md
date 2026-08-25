# Implementation Plan: The Post-Review Fold Loop — Fold Every Leg Once, Come Back for Re-Review, and Be Able to Delete a File

**Branch**: `042-post-review-fold-loop` | **Date**: 2026-08-25 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/042-post-review-fold-loop/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

Three defects, one loop, fixed as three narrow diffs against the two
workflows and the tool grant the measured PR #240 run exercised.

**Fold-then-dispatch-once** (research.md D1–D6): `pr-conversation.yml`'s
`act` matrix job (max-parallel: 1) keeps folding each classified item
exactly as it does today, but its per-leg dispatch step is removed. A new
job, `dispatch-once` (`needs: [classify-and-announce, act]`,
`if: always()`), reads the branch tip once the whole matrix has finished
and issues at most one `gh workflow run` for the entire review — so
"fold all, dispatch once" falls out of the matrix's own existing
serialization rather than a new coordination mechanism. `act`'s
concurrency group is left unchanged (`wing-commander-${SPEC_DIR}`, the
same group `implement.yml` uses) because that membership is what already
makes a review wait behind an in-flight implementation cycle (FR-004a);
`dispatch-once` joins the same group but, because it depends on `act`,
never overlaps with `act`'s own hold on it — which is what removes the
contention that cancelled leg 4 and iteration 3 together on #240, without
touching the wait FR-004a still needs. A second new job,
`report-fold-outcomes` (also `needs: [classify-and-announce, act]`,
`if: always()`), cross-references the run's own GitHub-set job
`conclusion`s against git-history fold evidence — two signals neither of
which a cancelled leg has to have published itself (FR-006a) — to post one
PR-thread comment naming any item that died without folding, distinguishing
"not folded" from "partly folded," and posting nothing when every leg
folded cleanly.

**Re-entrant finalize** (research.md D7–D10): `finalize.yml`'s existing-PR
guard changes from a boolean `skip` to a four-valued `pr-state`
(`none`/`open`/`merged`/`closed`). The steps that already do everything
FR-008 requires on the *create* path — body assembly, label flip, the
`stage: review` metadata commit, the lifecycle-issue announcement — are
regated to also run for `open`, refreshing instead of creating; `merged`
and `closed` route to a new, distinct report step and change nothing
(FR-009/FR-009a). The PR body gains a delimited machine-owned region (the
same HTML-comment idiom `auto-update-spec-kit.yml` and `rebase.yml`
already use elsewhere in this pipeline): a state block regenerated on
every refresh, and an append-only fold log, one entry per fold, keyed for
idempotency by the branch tip SHA it describes. Re-review is requested
from a login `pr-conversation.yml`'s new `dispatch-once` job records into
a new `spec-meta.json` field (`pending_re_review_from`) at fold time — the
most precise available source, since a PR's live review state can be
dismissed or superseded before finalize runs — falling back to the PR's
own review records when that field is absent.

**Deletion capability** (research.md D11–D12): `Bash(git rm:*)` is added
to both of `implement.yml`'s tool-grant literals (`implement.cycle`,
line 725; `implement.retry`, line 1086) and to the two matching rows of
the published contract (`specs/010-reusable-pipeline/contracts/stage-interfaces.md`,
248–294). Convergence needs no separate edit — it already shares whichever
of those two grants is active, since it runs as step 3 of the same agent
prompt in both call sites — so FR-012's "must not diverge" holds by
construction. `git rm`'s own semantics are the untracked-file boundary
FR-011a requires; no new guardrail code is added, matching every other
write verb this stage already grants bare. The existing Gate 27
(`verify-stage-tool-lists.py`) already fails a call-site/contract mismatch
and needs no change.

**Coverage** (research.md D13, contracts/gate-coverage-042.md): two new
gates, numbered from the next unused slot in `lint-workflows.yml` (33 is
the highest in use at plan time; confirm the actual number at
implementation time). Gate 34 exercises `dispatch-once` and
`report-fold-outcomes` via `wc_shell_harness.py` against synthetic
job-conclusion and git-history fixtures. Gate 35 exercises `finalize.yml`'s
refresh path via a real local git repository with a bare remote, following
`verify-stall-restart-runbook.py`'s (Gate 14) shape — needed because the
idempotent fold-log append and the preserve/regenerate body split have
real commit/push and real body-read/write side effects a transcript-only
harness cannot honestly prove. Both wire in through `wc_gate_registry.py`'s
existing filename convention; neither requires a change to Gate 15
(job-suppression) since every new job-level `if:` uses `always()`, which
Gate 15 already recognizes, and `finalize.yml`'s new conditions are
step-level, outside Gate 15's job-`needs:` graph walk entirely.

See [research.md](./research.md) for the full decision record (D1–D13),
[data-model.md](./data-model.md) for the concrete shapes, and
[contracts/](./contracts/) for the four delta contracts this plan produces.

## Technical Context

**Language/Version**: Bash (the `run:` steps rewritten/added in
`pr-conversation.yml` and `finalize.yml`), YAML (the two `workflow_call`
input/tool-grant literal edits in `pr-conversation.yml`/`implement.yml`),
Python 3 (the two new `verify-*.py` gates, matching every existing
`verify-*.py` gate script's shape) — no new language introduced.

**Primary Dependencies**: `jq`, `git`, `gh` (already the sole dependencies
of every step this feature touches or adds), `wc_shell_harness.py`
(existing, reused unmodified — its `find_job`/`find_step`/`run_step`/
`parse_github_output` API already covers what both new gates need),
`wc_gate_registry.py` (existing, reused unmodified — picks up both new
gates by filename convention).

**Storage**: `spec-meta.json` on each spec's persistent branch gains one
new field, `pending_re_review_from` (data-model.md §5). The final pull
request's own description gains a delimited machine-owned region
(data-model.md §6) — the PR body itself is the storage for the fold log,
not a new file. No other persisted state; every other new value (job/step
outputs) lives only for the duration of the run that computes it.

**Testing**: Two new gates, `.github/scripts/verify-fold-dispatch-once.py`
(Gate 34) and `.github/scripts/verify-finalize-refresh.py` (Gate 35),
wired into `.github/workflows/lint-workflows.yml`, executing the real
shipped `run:` step text of both affected workflows against synthetic
fixtures (contracts/gate-coverage-042.md). The existing Gate 27
(`verify-stage-tool-lists.py`) and Gate 10 (wiring completeness) require
no changes but must stay green against the two-call-site tool-grant edit.

**Target Platform**: GitHub Actions `workflow_call` stages, `ubuntu-latest`
runner, dispatched by `wing-commander-9-pr-conversation.yml` and
`wing-commander-6-finalize.yml` exactly as today.

**Project Type**: Single project — a GitHub Actions reusable-workflow
pipeline component; no application `src`/`tests` split applies.

**Performance Goals**: No added latency on a review whose legs all fold
cleanly and dispatch once, beyond the two new jobs' own runtime (a
`git ls-remote`/branch-tip comparison for `dispatch-once`; a paginated
`gh api .../jobs` call plus a bounded `git log --grep` for
`report-fold-outcomes`) — both run once per review, not once per leg,
which is strictly less GitHub API and git traffic than today's per-leg
dispatch. A refresh finalize run costs one additional `gh pr view --json
body,reviews` read and one `gh pr edit`/`gh pr edit --add-reviewer` pair
beyond today's now-reused create-path steps; a first (create-path)
finalize run is unchanged.

**Constraints**:
- `pr-conversation.yml`'s, `finalize.yml`'s, and `implement.yml`'s declared
  `workflow_call` inputs/outputs/secrets are not removed or renamed
  (FR-016); the one addition (`pr-conversation.yml`'s
  `confirm-timeout-minutes`) is optional with a default that preserves
  current behavior's practical bound (GitHub's own 360-minute job default
  today has no application-level bound at all; 1440 minutes is a new,
  explicit, adopter-configurable one — data-model.md §9).
- Every path quiet today stays quiet (FR-017): a healthy review whose legs
  all fold, a first finalize, and an implementation cycle that removes
  nothing behave byte-for-byte as they do now.
- No new constraint may be weakened to accommodate the deletion capability
  (FR-013) — `Bash(git rm:*)` is additive to the existing literal lists,
  nothing removed.
- Coverage must independently kill every mutation contracts/gate-coverage-042.md
  lists (FR-019), not merely exercise the happy path.
- The existing one-shot guard's purpose (never a second final PR) is
  preserved on every path this feature adds (FR-010).

**Scale/Scope**: Two workflow files gain new jobs/rewired steps
(`pr-conversation.yml`: `act`'s per-leg dispatch step removed/split, two
new jobs `dispatch-once` and `report-fold-outcomes`, one new
`workflow_call` input; `finalize.yml`: the existing-PR guard's output
widened, six existing steps regated, two steps' bodies extended, one new
report step, one new re-review-request step), one workflow file gains a
two-literal edit (`implement.yml`: `Bash(git rm:*)` at two call sites),
one published contract document gains two matching table-row edits
(`stage-interfaces.md`), two new gate scripts are added
(`.github/scripts/verify-fold-dispatch-once.py`,
`.github/scripts/verify-finalize-refresh.py`), and
`.github/workflows/lint-workflows.yml` gains two new gate steps. Zero
edits to any calling wrapper (`wing-commander-9-pr-conversation.yml`,
`wing-commander-5-implement.yml`, `wing-commander-6-finalize.yml`), to the
`wing-commander-tool-args` composite, or to any other composite action.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Result |
|---|---|---|
| I. Guide — repo is its own first example | Built through the pipeline itself (issue #250 → this spec → this plan → tasks → implement), fixing three defects the repository observed on its own PR #240/#235 runs; quickstart.md Scenario 12 re-runs the measured shape as the final acceptance check, per FR-018/SC-001. | ✅ Pass |
| II. Cost-Conscious Model Tiering | This plan runs at `claude-sonnet-5` (planning-weight default). The feature adds no new agent invocation and changes no existing one's model tier — every new/rewired job or step is deterministic bash/YAML reading already-computed or newly-added upstream values; `implement.yml`'s widened tool grant reaches the *same* agent step at the *same* tier it already runs at. | ✅ Pass |
| III. Simple, GitHub-Native Interaction | No new interaction surface — the PR thread and the lifecycle issue still carry every status this feature reports (FR-006, FR-010d), with a new PR-body region a maintainer reads in place rather than a new dashboard. Re-review is requested through GitHub's own native reviewer-request mechanism (`gh pr edit --add-reviewer`), not a custom notification channel. | ✅ Pass |
| IV. Automation-First | Closes the loop's open ends automatically: a review that folds cleanly now dispatches and reports without a human noticing a gap (US1/US2), a converged fold now re-presents itself for review without a maintainer polling (US3), and a removal-shaped task no longer hands back a "manual work" note (US4). Every remaining manual step this feature cannot close — a re-review request that fails, a record commit that cannot land — is reported explicitly to the lifecycle issue (FR-010b, Edge Cases), never silently assumed. | ✅ Pass |
| V. Security — untrusted content is never instructions | No new trust boundary: `report-fold-outcomes` reads GitHub-platform-set job `conclusion`s and this repository's own git history, never issue/comment/review body text, to decide an outcome (FR-006a). `pending_re_review_from` is populated from `inputs.actor-login`, an input the workflow already receives and already documents as "display only" (i.e. never used to gate a security decision) — recording *identity* for a later notification is not the same class of use as trusting *content* as instructions, and FR-008 explicitly forbids deriving it from ambient event state instead. No new secret, no new web tool, no new fork-PR checkout path. | ✅ Pass |
| VI. Portability — consuming repo owns its artifacts | Unaffected — all three edited files already live under `.github/**`, resolved from the pipeline repository's own checkout; the widened tool grant reaches adopters through the existing `wing-commander-tool-args` composite's resolution path with no new resolution mechanism (FR-015). | ✅ Pass |
| VII. Two Interfaces — published contract vs. consuming instrument | `pr-conversation.yml` gains one new, optional, defaulted `workflow_call` input (`confirm-timeout-minutes`); no input, output, or secret of any of the three affected stages is removed or renamed (FR-016) — every change is either additive to the published contract (the new input; the widened `implement.cycle`/`implement.retry` tool-grant rows, recorded in `stage-interfaces.md` in the same change per that document's own maintenance note) or an internal-behavior change beneath an unchanged contract (`finalize.yml`'s refresh logic; `pr-conversation.yml`'s fold/dispatch split). No stage gains a new ambient-state read (`github.event.*`/`vars.*`/inherited secret) — `pending_re_review_from` is stage-owned state in `spec-meta.json`, the same class of state the stage already reads and writes. No deviation to register. | ✅ Pass |
| VIII. A Green Check Means What It Says | Gate 27 already fails its own subject for a call-site/contract mismatch (FR-014) and needs no new gate to duplicate that fact (research.md D12). Two new gates (34, 35) are added specifically because the genuinely new behavior — fold-then-dispatch-once, leg-death reporting, finalize's refresh path — has no existing coverage to extend; both are wired through the existing registry (Gate 10 asserts this both ways), both execute the real shipped `run:` text rather than a copy (matching `wc_shell_harness.py`'s established discipline), and both carry required mutations proving each failure branch is actually exercised (FR-019, contracts/gate-coverage-042.md). | ✅ Pass |
| IX. Judgment That Gates a Durable Action Belongs in Deterministic Code | Every judgment that gates a durable action this feature adds is deterministic code, not a prompt instruction: whether to dispatch (a branch-tip SHA comparison, D3), whether a leg folded (job `conclusion` plus git-history cross-check, D6), whether to refresh vs. skip a final PR (`pr-state`, a `gh pr list --json state` read, D7), whether a fold-log entry is a duplicate (SHA comparison, D9a), and who to re-request review from (`spec-meta.json`'s own field, D10) are each computed the same way from the same input every time. The one place a model still acts — the fold agent's commit — is unchanged from today's already-deterministic-checked shape (its resulting branch state, not its own narration, is what every new signal reads). | ✅ Pass |

**Post-Phase-1 re-check**: Unchanged. Phase 1 design (data-model.md,
contracts/, quickstart.md) confirms every new field lives either in a
job/step output (ephemeral, run-scoped), in `spec-meta.json` (already the
stage's own lifecycle state, not a new external surface), or in the final
PR's own body (an artifact this stage already owns and writes) — no new
untrusted-input path, no new stage-side ambient-state read, and no
principle re-opened by the concrete shapes chosen in Phase 1.

## Project Structure

### Documentation (this feature)

```text
specs/042-post-review-fold-loop/
├── plan.md                                   # This file (/speckit-plan command output)
├── research.md                               # Phase 0 output (/speckit-plan command)
├── data-model.md                             # Phase 1 output (/speckit-plan command)
├── quickstart.md                             # Phase 1 output (/speckit-plan command)
├── contracts/                                # Phase 1 output (/speckit-plan command)
│   ├── fold-dispatch-once.md                 # pr-conversation.yml behavior-delta contract
│   ├── finalize-refresh.md                   # finalize.yml behavior-delta contract
│   ├── implement-deletion-capability.md      # implement.yml + stage-interfaces.md delta
│   └── gate-coverage-042.md                  # new Gate 34/Gate 35 contract
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
├── workflows/
│   ├── pr-conversation.yml           # classify-and-announce gains a new
│   │                                  #   `base-sha` output (D3). `act`'s
│   │                                  #   per-leg dispatch step is split:
│   │                                  #   the fold half stays (fold commit
│   │                                  #   messages become `fold(<id>): ...`,
│   │                                  #   D6), the dispatch half is
│   │                                  #   removed. Classification gains a
│   │                                  #   stable `id` field (D6). NEW:
│   │                                  #   `dispatch-once` job (D1/D2/D3),
│   │                                  #   `report-fold-outcomes` job
│   │                                  #   (D6). NEW input:
│   │                                  #   `confirm-timeout-minutes`,
│   │                                  #   wired to `act`'s
│   │                                  #   `timeout-minutes:` (D5).
│   │                                  #   `stalled` job UNCHANGED.
│   ├── finalize.yml                  # "Check for an existing final pull
│   │                                  #   request" widened: `skip` → four-
│   │                                  #   valued `pr-state` (D7). "Assemble
│   │                                  #   PR body", "Open the final PR"
│   │                                  #   (renamed "Open or update the
│   │                                  #   final PR"), "Flip stage label",
│   │                                  #   "Commit metadata (stage ->
│   │                                  #   review)", "Announce for review",
│   │                                  #   "Check remaining manual work"
│   │                                  #   regated to also run on `open`
│   │                                  #   (D8). "Assemble PR body" gains
│   │                                  #   the machine-owned-region
│   │                                  #   preserve/regenerate/append logic
│   │                                  #   (D9/D9a). NEW: report step for
│   │                                  #   `merged`/`closed` (FR-009/
│   │                                  #   FR-009a), re-review-request step
│   │                                  #   reading/clearing
│   │                                  #   `pending_re_review_from` (D10).
│   ├── implement.yml                 # "Compose tool args (implement.cycle)"
│   │                                  #   (725) and "Compose tool args
│   │                                  #   (implement.retry)" (1086) each
│   │                                  #   gain `Bash(git rm:*)` (D11). No
│   │                                  #   other line changes.
│   └── lint-workflows.yml            # + Gate 34 — "a review folds every
│                                      #   leg once and dispatches once; a
│                                      #   dead leg says so". + Gate 35 —
│                                      #   "finalize refreshes an open final
│                                      #   PR, and only an open one".
└── scripts/
    ├── wc_shell_harness.py           # UNCHANGED — reused as-is
    ├── wc_gate_registry.py           # UNCHANGED — picks up both new gates
    ├── verify-stall-restart-runbook.py  # prior art for the real-git-repo +
    │                                  #   bare-remote shape (read only)
    ├── verify-stage-tool-lists.py    # UNCHANGED — Gate 27, enforces the
    │                                  #   contract/call-site match FR-014
    │                                  #   requires (D12), no new gate
    │                                  #   needed for this sub-feature
    ├── verify-fold-dispatch-once.py  # NEW — Gate 34's script
    └── verify-finalize-refresh.py    # NEW — Gate 35's script

specs/010-reusable-pipeline/
└── contracts/
    └── stage-interfaces.md           # "Per-stage default tool lists"
                                       #   table (248-294): implement.cycle
                                       #   (274) and implement.retry (275)
                                       #   rows each gain `Bash(git rm:*)`,
                                       #   in the same change as the
                                       #   implement.yml edits (D11).
```

**Structure Decision**: No new top-level directory, no new composite
action, no edit to `wing-commander-9-pr-conversation.yml`,
`wing-commander-5-implement.yml`, `wing-commander-6-finalize.yml`, or any
other calling wrapper, no edit to `wing-commander-tool-args` or any other
composite action. The entire change is: two jobs added and one step split
in `pr-conversation.yml`; one guard output widened, six steps regated, and
three steps added in `finalize.yml`; two literal tool-grant edits in
`implement.yml` mirrored by two table-row edits in a published contract
document; two new gate scripts and two new gate steps in
`lint-workflows.yml` — matching the spec's own framing (three narrow,
independently-scoped fixes sharing two workflows, not a rework of either
workflow's architecture).

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No violations — table intentionally omitted.
