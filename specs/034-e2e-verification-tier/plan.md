# Implementation Plan: End-to-End Verification Tier That Actually Verifies the Candidate

**Branch**: `spec/034-e2e-verification-tier` | **Date**: 2026-08-12 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/034-e2e-verification-tier/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

Replace `auto-update-spec-kit.yml`'s `verify` job "End-to-end verification
(minor/major only)" step (currently lines 1294-1325: copy the candidate's
`spec-template.md` into the scratch feature dir, check it's non-empty, and
silently substitute a locally-generated one-liner when the template is
missing) with a tier whose verdict actually depends on the candidate's own
behaviour, per this feature's own spec. Concretely:

1. **Per-script assertions** (FR-001/002/003): reuse the lightweight tier's
   already-created scratch feature (`create-new-feature.sh` + `spec.md`) and
   add the on-disk non-empty check lightweight never made, then chain
   `setup-plan.sh --json` and `setup-tasks.sh --json` — the two `.specify/`
   scripts the pipeline's own plan/tasks stages depend on and that no check
   anywhere exercises today — against the same isolated worktree, asserting
   each script's documented JSON fields and the on-disk artifact (`plan.md`)
   it produces. `common.sh` is exercised transitively by every one of these
   four scripts, and `check-prerequisites.sh --paths-only` is unchanged from
   the lightweight tier. This closes FR-002's "every Spec Kit script the
   pipeline depends on" without inventing new dependencies to check.
2. **No fallback** (FR-004): delete the tier's own `else` branch that
   fabricates a substitute spec. Because `create-new-feature.sh` and
   `setup-plan.sh` already degrade to an empty file (`touch`) when the
   candidate's own template is missing — never a non-empty substitute — the
   new non-empty on-disk assertions above are sufficient to fail the tier
   the moment a candidate ships without one; no separate pre-flight template
   probe is needed.
3. **One real AI-driven stage** (FR-017/018/019): a new `e2e-stage` job runs
   one throwaway `/speckit-specify`-equivalent turn (`claude-code-action@v1`,
   bounded model/turns, read back deterministically — never trusting agent
   narration, matching `evaluate-path`'s existing convention) against the
   candidate's own regenerated `.specify/` artifacts, inside a **scratch
   GitHub repository** created for the run and named from the lifecycle
   issue (FR-022). Its result gates the combined verdict under the same
   single failure path as every other check (FR-018, FR-021).
4. **Scratch repository lifecycle** (FR-019/022/023): create-if-absent,
   named deterministically from the lifecycle issue number so it never
   accumulates duplicates across a re-dispatched run for the same cycle;
   deleted by a new `issues: {types: [closed]}` trigger on the wrapper, with
   a scheduled sweep as backstop for runs that died mid-flight or whose
   webhook never fired.
5. **Narration** (FR-007/008/009/010): the combine step's failure detail
   already reaches the issue via the existing `wing-commander-callout`
   step (`act` job) unchanged; this feature only changes what produces that
   text — a per-check reason instead of one hardcoded string — and appends
   the FR-008 non-clean-bump hint specifically when the failure reason is a
   missing artifact.
6. **Harness** (FR-015/020): extend `t4_verify.sh` with the new scenarios,
   extend `gh_stub.py` with controlled `repo create`/`repo delete`/`repo
   list` handling (net-new — no existing stub or workflow call touches
   `gh repo create`/`delete` today), and extend `t7_gating.py`'s job-routing
   coverage for the new `issue-closed` trigger value and `e2e-stage` job.
   `specs/027-auto-update-spec-kit/quickstart.md` Scenario 7's narrative
   (FR-016) is corrected during implementation, not by this plan.

No new workflow file, no tenth numbered stage, no new persisted ledger — this
is a modification to the existing `auto-update-spec-kit.yml` +
`wing-commander-auto-update-spec-kit.yml` pair from specs/027, following that
feature's own precedent of duplicating tier logic inline rather than
factoring a new composite action for a two-file-scope change.

## Technical Context

**Language/Version**: Bash (GitHub Actions `run:` steps), YAML (workflow
definitions), `jq` for JSON, Python 3 + PyYAML for the test harness only —
identical toolchain to specs/027 and to every other pipeline stage; no new
language introduced.

**Primary Dependencies**: Everything specs/027 already depends on
(`gh`, `jq`, `git`, `anthropics/claude-code-action@v1`, the pipeline's
`wing-commander-context`/`wing-commander-callout` composites), plus:
`.specify/scripts/bash/setup-plan.sh` and `setup-tasks.sh` (newly invoked
directly from a workflow `run:` step — previously only agent-issued from
inside `plan.yml`/`tasks.yml`), `gh repo create`/`gh repo delete`/`gh repo
list` (newly invoked anywhere in this repository's workflows), and the same
`uvx --from git+https://github.com/github/spec-kit.git@v${CANDIDATE} specify
init` command `prepare` already runs, reused a second time against the
scratch repository's clone. No new external service or vendored copy of
Spec Kit's source.

**Storage**: No new persisted state file. The scratch repository's identity
is derived, not stored — its name is a deterministic function of the
lifecycle issue number (`wing-commander-e2e-<issue-number>`), discoverable
by any job that already has the issue number and re-derivable by the
scheduled reaper via `gh repo list --json name` filtered by prefix, so
"is this scratch repo's issue closed or gone" needs no separate mapping
file (research.md — same "state that already exists beats a new ledger"
reasoning specs/027/research.md already established for settle-tracking and
rollback-target lookup).

**Testing**: `.github/scripts/auto-update-spec-kit-tests/` (specs/027's
harness, from #156) is extended, not replaced: new scenarios in
`t4_verify.sh` for the extracted per-script assertion steps and the
deterministic e2e-stage read-back step (reusing `t6_reply.sh`'s
`agent_out()` fixture-building pattern for the latter, since a
`claude-code-action` step itself cannot run inside the harness — only its
deterministic read-back can, exactly as `evaluate-path`'s own `decide` step
is untested today and only `decide-outcome` is), `gh_stub.py` gains
`repo create`/`repo delete`/`repo list` support (net-new surface, backed by
the same JSON state file, so create/delete/list can be asserted as real
state mutations rather than desk-read), and `t7_gating.py` gains the new
`issue-closed` trigger's job-routing and the `e2e-stage` job's `if:`
condition, read verbatim from the YAML per its existing no-retyping
convention. No new test framework.

**Target Platform**: GitHub Actions (`ubuntu-latest` runners), same trigger
set as specs/027 on the wrapper (`schedule`, `workflow_dispatch`,
`pull_request: {types: [closed]}`, `issue_comment: {types: [created]}`) plus
one new trigger: `issues: {types: [closed]}`, resolved to the same typed
`trigger` input (`trigger: issue-closed`) rather than read as raw event data
inside the reusable stage (constitution VII, matching every existing trigger
reason).

**Project Type**: Single project — CI/CD automation under
`.github/workflows/` and `.github/scripts/`, reusing existing composite
actions and the existing test harness. No frontend/backend split.

**Performance Goals**: Unchanged cadence (daily); the new per-script chain
adds a handful of seconds of bash/script execution per minor/major
candidate (unchanged scope — patch candidates never reach this tier). The
new AI-driven stage adds one bounded agent turn budget and one scratch-repo
create per minor/major candidate — the cost spec.md's Assumptions already
accept ("the scheduled job accepts the model cost and wall-clock cost of one
AI-driven stage per minor/major candidate").

**Constraints**: FR-004's single-failure-path rule (no fallback content, no
second outcome branch); FR-013's containment rule now explicitly spans two
kinds of ephemeral state — the disposable isolated worktree (discarded every
outcome, unchanged from specs/027) and the new scratch repository (retained
while the lifecycle issue is open, deleted on close, FR-019/023) — neither
may leak into this repository's real `specs/` tree, pushed branches, or
opened PRs. The scheduled job needs `gh repo create`/`gh repo delete`
rights it does not have today (spec.md Assumptions flags this as a required,
broader grant). Every new agent step declares `--model` and `--max-turns`
(constitution II).

**Scale/Scope**: Two existing workflow files modified
(`auto-update-spec-kit.yml`: `verify` job's end-to-end step split into a
per-script chain, new `e2e-stage` job, new `combine` inputs, new
`reap-scratch-repos` step/job; `wing-commander-auto-update-spec-kit.yml`:
new `issues: {types: [closed]}` trigger), five test-harness files extended
(`t4_verify.sh`, `gh_stub.py`, `t7_gating.py`, plus `README.md`'s scenario
table and mutation table), and one out-of-tree file corrected during
implementation per FR-016 (`specs/027-auto-update-spec-kit/quickstart.md`
Scenario 7). No new workflow file, no new `.specify/memory/*.json` config.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Guide**: This feature repairs a check this repository depends on for
  its own next real upgrade (0.12.4 → current upstream, a minor jump per
  spec.md's own framing) — it is itself built through the pipeline (issue
  #184 → this spec → this plan → tasks → implementation) and its first real
  effect is dogfooded on this repository's own pinned Spec Kit version, the
  exact worked example constitution I asks for. **Pass.**
- **II. Cost-Conscious Model Tiering**: The existing `evaluate-path` agent
  step's tier is unchanged. The new `e2e-stage` agent step is a disposable,
  bounded, at-most-once-per-minor/major-candidate smoke test whose output is
  never read by a human as a real spec and is asserted only for
  existence/shape — research.md documents (as a decision made without
  clarification) why this plan assigns it `claude-sonnet-5` by default,
  matching `evaluate-path`'s own tier, rather than the `claude-opus-5`
  premium constitution II reserves for the *foundational* spec real users
  consume, plus a maintainer-overridable repo variable
  (`WING_COMMANDER_AUTO_UPDATE_SPEC_KIT_E2E_STAGE_MODEL`) and a declared
  `--max-turns` bound, following the blanket rule exactly. The
  per-script assertion chain and the scratch-repo create/delete/reap steps
  are entirely deterministic bash/`gh`/`jq` — no model runs for them.
  **Pass.**
- **III. Simple, GitHub-Native Interaction**: The lifecycle issue remains
  the single legible record — narration gains per-check specificity and the
  FR-008 hint, and now also names the scratch repository and its deletion
  trigger (FR-022), all as comments on the same issue. No new dashboard, no
  new CLI, no second issue or label taxonomy (FR-006/FR-009 preserved).
  **Pass.**
- **IV. Automation-First**: No new manual step is introduced. Closing the
  lifecycle issue — already the maintainer's own action, not a new one this
  feature invents — now also triggers an automated deletion the maintainer
  is told about in advance (FR-022), rather than requiring a separate manual
  cleanup step. **Pass.**
- **V. Security (NON-NEGOTIABLE)**: The scratch repository is created and
  deleted only by this stage's own bot identity, never by an untrusted
  actor's input — its name is derived from the lifecycle issue *number*
  (a trusted, workflow-computed value), never from issue or comment body
  text. The new `e2e-stage` agent step reads only the candidate's own
  regenerated `.specify/` artifacts and a fixed, hardcoded throwaway feature
  description — never live-fetched or user-supplied content — so there is no
  new untrusted-content-as-instruction surface (unlike `evaluate-path`,
  which already frames release notes as data; this step has no comparable
  external input at all). No web tools. Only the candidate's own checkout
  (already fetched via the disposable bundle, per specs/027) and the newly
  created scratch repository — never a fork PR head — are ever checked out.
  This stage still never merges or approves anything. **Pass.**
- **VI. Portability**: No new consuming-repo-owned config file. The new repo
  variable follows the existing `WING_COMMANDER_<PURPOSE>_<KNOB>` naming
  convention. The scratch repository is created under the *consuming*
  repository's own owner/account (`github.repository_owner`), using the
  same App installation token every other step in this stage already mints
  — nothing hardcodes Wing Commander itself or any other repository name.
  **Pass.**
- **VII. Two Interfaces**: `auto-update-spec-kit.yml` remains
  `workflow_call`-only and still reads no `github.event.*`/`vars.*`
  directly — the new `issues: {types: [closed]}` trigger is resolved by the
  wrapper into the same typed `trigger`/`issue-number` inputs the stage
  already accepts for `comment-reply`, not a new ambient read inside the
  stage. **Pass.**

No violations — Complexity Tracking is not needed.

## Project Structure

### Documentation (this feature)

```text
specs/034-e2e-verification-tier/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
│   └── e2e-verification-tier.md
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
.github/
├── workflows/
│   ├── auto-update-spec-kit.yml               # MODIFIED — verify job: per-script
│   │                                            #   assertion chain replaces the
│   │                                            #   copy-and-check-non-empty step;
│   │                                            #   new e2e-stage job (AI-driven,
│   │                                            #   gates the combined verdict);
│   │                                            #   new scratch-repo create step
│   │                                            #   (verify or a new job) and reap
│   │                                            #   step/job (issue-closed trigger
│   │                                            #   + scheduled backstop sweep)
│   └── wing-commander-auto-update-spec-kit.yml # MODIFIED — adds issues:{types:[closed]}
│                                                #   trigger, resolved to trigger:
│                                                #   issue-closed
│
└── scripts/
    └── auto-update-spec-kit-tests/
        ├── t4_verify.sh   # MODIFIED — new scenarios: per-script pass/fail,
        │                  #   missing-artifact fail, wrong-shape fail,
        │                  #   e2e-stage read-back pass/incomplete, narration hint
        ├── gh_stub.py     # MODIFIED — adds repo create/delete/list handling
        ├── t7_gating.py   # MODIFIED — issue-closed routing, e2e-stage gating
        └── README.md      # MODIFIED — scenario/mutation tables gain new rows

specs/027-auto-update-spec-kit/
└── quickstart.md          # MODIFIED during implementation (FR-016) — Scenario 7's
                            #   narrative corrected to describe the fixed tier;
                            #   out of this plan's own edit scope (constraints:
                            #   this plan only writes inside specs/034-.../)
```

**Structure Decision**: No new workflow file and no new source directory —
this is a targeted modification to the existing `auto-update-spec-kit.yml` +
`wing-commander-auto-update-spec-kit.yml` stage-pair from specs/027 and its
existing test harness from #156, matching the single-project, no
`src/`/`tests/`-split shape every prior pipeline-stage feature in this
repository has used. The primary new artifact is one new job
(`e2e-stage`) plus one new step group in the existing `verify` job, not a
new file.

## Complexity Tracking

> Not applicable — no Constitution Check violations.
