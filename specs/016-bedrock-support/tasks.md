---

description: "Task list for AWS Bedrock Support for Consuming Repositories"
---

# Tasks: AWS Bedrock Support for Consuming Repositories

**Input**: Design documents from `/specs/016-bedrock-support/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/bedrock-provider.md, quickstart.md

**Tests**: Not requested — no automated test suite exists for any pipeline stage in this repository (plan.md's Testing section: `lint-workflows.yml`'s YAML-parse + `bash -n` static check is the only automated CI check). Validation is manual/scripted, via `quickstart.md`'s six scenarios, folded into each phase's checkpoint and the Polish phase below. A live Bedrock round-trip is explicitly out of scope for this repository (spec Assumption).

**Organization**: This feature is a uniform, mechanical change repeated across nine existing stage workflow files (`intake`, `clarify`, `plan`, `tasks`, `implement`, `finalize`, `cleanup`, `rebase`, `watchdog`) plus one extended and one new shared composite. User Story 1's independent test only requires *one* stage to demonstrate the mechanism end-to-end; User Story 3 is what extends the identical surface to the remaining eight stages and documents it — this split gives a real, mergeable MVP checkpoint (per spec.md's own priority ordering) instead of one all-nine-stages-or-nothing task. `intake.yml` is the representative stage for User Story 1: single job, single `anthropics/claude-code-action` call site, already carries every input pattern this feature reuses.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- Setup, Foundational, and Polish tasks carry no story label

## Path Conventions

Single-project CI/CD feature (GitHub Actions reusable workflows + composite actions), no `src/`/`tests/` split (plan.md's Structure Decision). All file paths below are repo-root-relative.

---

## Phase 1: Setup

**Purpose**: Resolve the one open verification item research.md flags before any wiring begins.

- [X] T001 Confirm the exact upstream contract this feature relies on (research.md D1, made "without clarification" during planning since that environment had no outbound web access): verify the pinned `anthropics/claude-code-action@v1` exposes a boolean `use_bedrock` `with:` input and expects AWS credentials/region via the ambient job environment (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`, `AWS_REGION`) rather than its own AWS-credential inputs — check the action's `action.yml`/README at the pinned tag (e.g. via `gh api repos/anthropics/claude-code-action/contents/action.yml?ref=v1` or a scratch checkout). Record the confirmed input name and env-var contract (or any discrepancy) in this task's commit message — every task below that adds `use_bedrock: ${{ inputs.use-bedrock }}` depends on this being correct.

**Checkpoint**: the exact wiring contract is confirmed — per-stage tasks can proceed without re-deriving it.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Build the two shared pieces every stage's wiring depends on — the new AWS-credentials composite and the extended preflight branch.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T002 Create `.github/actions/wing-commander-bedrock-credentials/action.yml` (research.md D2): header comment following the cross-repo self-checkout convention already documented in `wing-commander-context/action.yml` (this composite is resolved from the pipeline's own checkout at `.wing-commander-pipeline/`, same as every other shared composite). Inputs: `use-bedrock` (boolean-as-string, default `"false"`), `aws-role-arn` (string, default `""`), `aws-region` (string, default `""`). A single step running `aws-actions/configure-aws-credentials`, pinned to a major-version tag consistent with this repo's existing third-party-action pinning convention (`actions/checkout@v4`, `anthropics/claude-code-action@v1` — i.e. `aws-actions/configure-aws-credentials@v4`), gated `if: inputs.use-bedrock == 'true'`, with `role-to-assume: ${{ inputs.aws-role-arn }}` and `aws-region: ${{ inputs.aws-region }}` (OIDC only — no `aws-access-key-id`/secret inputs, per FR-003's no-long-lived-secrets constraint). When `use-bedrock` is `"false"`/unset the step does not run — no-op, no AWS call.
- [X] T003 Extend `.github/actions/wing-commander-preflight/action.yml` (research.md D3, data-model.md's Bedrock Configuration validation rules 1–4): add inputs `use-bedrock` (default `"false"`), `aws-role-arn` (default `""`), `aws-region` (default `""`). In the existing "Preflight (credentials, spec-kit, prerequisites)" step, replace check 1 (the unconditional Anthropic-credential-empty check) with a branch: when `use-bedrock == "true"`, skip the Anthropic-credential check entirely (FR-004) and instead `fail()` naming `aws-role-arn` and/or `aws-region` specifically if either is empty (both named together in one message if both are missing — FR-008; no validity probe against AWS, matching the existing "no probe" posture for Anthropic credentials); when `use-bedrock` is `"false"`/unset, run the existing Anthropic-credential-empty check exactly as today, unchanged (FR-005, SC-002). Update the passing step-summary message to reflect whichever branch ran.

**Checkpoint**: the shared composite and the preflight branch both exist and are independently correct — per-stage wiring (User Stories 1 and 3) can now begin.

---

## Phase 3: User Story 1 - Run the pipeline against AWS Bedrock (Priority: P1) 🎯 MVP

**Goal**: Prove the full mechanism end-to-end on one representative stage — a consumer can enable `use-bedrock`, supply `aws-role-arn`/`aws-region`, and have that stage's agent call carry `use_bedrock` through, with no Anthropic credential required.

**Independent Test**: A consuming repository configures AWS credentials and enables the Bedrock flag when calling `intake.yml`, and the stage's agent step receives `use_bedrock: true` and completes without an Anthropic API key or OAuth token — quickstart.md Scenarios 3 and 6.

### Implementation for User Story 1

- [X] T004 [US1] Wire `.github/workflows/intake.yml` end-to-end: add `use-bedrock` (type `boolean`, default `false`), `aws-role-arn` (type `string`, default `""`), `aws-region` (type `string`, default `""`) to the `workflow_call.inputs` block (alongside the existing `model`/`pipeline-repo`/`default-branch` inputs); pass all three through to the existing "Preflight" step's `with:` block (`./.wing-commander-pipeline/.github/actions/wing-commander-preflight`); add a new "Configure AWS credentials for Bedrock" step immediately after preflight and before the "Wing Commander context" step, invoking `./.wing-commander-pipeline/.github/actions/wing-commander-bedrock-credentials` with the same three inputs; add `use_bedrock: ${{ inputs.use-bedrock }}` to the job's `anthropics/claude-code-action@v1` call's `with:` block, alongside the existing `claude_code_oauth_token`/`anthropic_api_key` wiring (left unconditional and unchanged, per research D4).

**Checkpoint**: User Story 1 is fully functional on `intake.yml` — quickstart.md Scenarios 3 and 6 pass against this one stage, independent of every other phase below.

---

## Phase 4: User Story 2 - Existing (Anthropic) adopters are unaffected (Priority: P2)

**Goal**: Confirm that leaving `use-bedrock` unset changes nothing about today's behavior on the stage wired so far.

**Independent Test**: With `use-bedrock` left at its default (unset) on `intake.yml`, the stage runs exactly as before — quickstart.md Scenario 1.

### Implementation for User Story 2

- [X] T005 [US2] Desk-check `.github/workflows/intake.yml` and `.github/actions/wing-commander-preflight/action.yml` against quickstart.md Scenario 1: with `use-bedrock` unset, confirm (a) no new input is `required: true`, so a caller who sets nothing still validates; (b) the Anthropic-credential-empty check in preflight still fires with the exact same message text as before T003; (c) the `wing-commander-bedrock-credentials` step's `if:` condition never evaluates true, so no AWS/STS call is ever attempted; (d) the `claude-code-action` call's existing `claude_code_oauth_token`/`anthropic_api_key` wiring is byte-for-byte unchanged from before this feature.

**Checkpoint**: User Stories 1 AND 2 both hold on `intake.yml` — quickstart.md Scenarios 1, 3, and 6 pass.

---

## Phase 5: User Story 3 - Consistent, documented enablement across every stage (Priority: P3)

**Goal**: Extend the identical enablement surface built in Phase 3 to the remaining eight agent-running stages, verify consistency across all nine, and document the capability for adopters.

**Independent Test**: Enable Bedrock across the full set of nine stages and confirm each accepts the same configuration surface (quickstart.md Scenario 5); confirm the adoption documentation describes the credentials-plus-flag setup (quickstart.md, SC-005).

### Implementation for User Story 3

- [X] T006 [P] [US3] Wire `.github/workflows/clarify.yml` the same way as T004: add the three `workflow_call` inputs; pass through to the existing preflight step (single job `clarify`); add the `wing-commander-bedrock-credentials` step before the job's one `anthropics/claude-code-action` call site; add `use_bedrock: ${{ inputs.use-bedrock }}` to that call.
- [X] T007 [P] [US3] Wire `.github/workflows/plan.yml`: add the three `workflow_call` inputs; pass through to the existing preflight step in the `plan` job (the separate `resolve-spec` job runs no agent step and needs neither the composite nor preflight changes); add one `wing-commander-bedrock-credentials` step in the `plan` job, before its two `anthropics/claude-code-action` call sites; add `use_bedrock` to both calls.
- [X] T008 [P] [US3] Wire `.github/workflows/tasks.yml`: add the three `workflow_call` inputs at the file level; pass through to the preflight step in the `tasks` job (auto-generate mode) and add one `wing-commander-bedrock-credentials` step there, before its two `anthropics/claude-code-action` call sites, wiring `use_bedrock` on both; the `tasks-approved` job is agent-free (`require-credential: "false"` in its own preflight call) and the `resolve-spec` job runs no agent — neither needs the credentials composite, but `tasks-approved`'s preflight call should still receive the three inputs for consistency (they're no-ops there since `use-bedrock` gates the Anthropic-check branch, not agent presence).
- [X] T009 [P] [US3] Wire `.github/workflows/implement.yml`: add the three `workflow_call` inputs; pass through to the preflight step in the single `implement` job and add one `wing-commander-bedrock-credentials` step there (the job's three `anthropics/claude-code-action` call sites — primary cycle, opus retry, haiku progress-comment — all share this one job, so one composite invocation covers all three per research D2); wire `use_bedrock` on all three calls. The `stalled` job runs no agent and needs no changes.
- [X] T010 [P] [US3] Wire `.github/workflows/finalize.yml` the same way as T004: three `workflow_call` inputs; preflight passthrough and one `wing-commander-bedrock-credentials` step in the single `finalize` job, before its one `anthropics/claude-code-action` call; wire `use_bedrock` on that call.
- [X] T011 [P] [US3] Wire `.github/workflows/cleanup.yml`: add the three `workflow_call` inputs; pass through to the preflight step in the `teardown-done` job (its only job with an agent step) and add one `wing-commander-bedrock-credentials` step there, before its one `anthropics/claude-code-action` call; wire `use_bedrock` on that call. The `select`, `teardown-rejected`, and `mark-stalled` jobs run no agent and need no changes.
- [X] T012 [P] [US3] Wire `.github/workflows/rebase.yml` — note this stage's agent call lives in a *different* job from its preflight check: add the three `workflow_call` inputs at the file level; pass them through to the existing preflight step in the `discover` job (unchanged location — this still fails fast before the matrix fans out); additionally add a new `wing-commander-bedrock-credentials` step inside the matrixed `rebase` job itself, before its one `anthropics/claude-code-action` call — required because `configure-aws-credentials`'s exported env vars are job-scoped and do not carry from `discover` into the separate `rebase` job (research D2's "per-job repetition" note); wire `use_bedrock` on that call.
- [X] T013 [P] [US3] Wire `.github/workflows/watchdog.yml` — this stage has preflight calls in three jobs (`collect`, `diagnose`, `triage`) but agent calls in only two (`diagnose`, `triage`; `collect` and `act` run no agent): add the three `workflow_call` inputs at the file level; pass them through to all three existing preflight calls; add a `wing-commander-bedrock-credentials` step in the `diagnose` job before its `anthropics/claude-code-action` call, and a second one in the `triage` job before its `anthropics/claude-code-action` call (research D2's confirmed example of a multi-job stage needing per-job repetition); wire `use_bedrock` on both calls.
- [ ] T014 [US3] Grep all nine stage workflow files (`intake.yml`, `clarify.yml`, `plan.yml`, `tasks.yml`, `implement.yml`, `finalize.yml`, `cleanup.yml`, `rebase.yml`, `watchdog.yml`) for `use-bedrock`, `aws-role-arn`, `aws-region`, and `use_bedrock` (quickstart.md Scenario 5): confirm every stage's `workflow_call.inputs` declares all three with identical types/defaults, every `anthropics/claude-code-action` call site in every file passes `use_bedrock: ${{ inputs.use-bedrock }}`, and every job containing such a call site also carries a `wing-commander-bedrock-credentials` invocation — no stage or call site missing the surface. Also re-confirm quickstart.md Scenario 1 (User Story 2's default-unchanged behavior) now holds across all nine stages, not just `intake.yml`.
- [ ] T015 [P] [US3] Add a Bedrock subsection to `docs/adoption.md`'s "Credentials" section (after the existing Anthropic credentials table): document the `use-bedrock`/`aws-role-arn`/`aws-region` inputs, that AWS credentials are assumed via OIDC inside each stage job (no long-lived AWS secrets; the caller's job must already grant `id-token: write`, the same permission every stage already requires for its own GitHub-OIDC pipeline-ref resolution — adopting Bedrock adds no new permission grant), the documented precedence rule ("if you set `use-bedrock: true`, Bedrock is used regardless of whether an Anthropic credential is also configured"), and that Bedrock-compatible model identifiers are supplied through the existing per-stage `model` inputs (pure pass-through, no translation).
- [ ] T016 [P] [US3] Add `use-bedrock`/`aws-role-arn`/`aws-region` to `docs/setup.md`'s repository secrets/variables section: since these are per-call `workflow_call` inputs (set in a wrapper's own `with:` block), not repository secrets or variables, add a short cross-reference note pointing to `docs/adoption.md#credentials` for the full Bedrock setup, rather than a secrets/variables table row.
- [ ] T017 [P] [US3] Add a short "Bedrock pass-through" note to `docs/architecture.md`'s "Model tiering (constitution II)" section: `use-bedrock` changes only which backend serves the already-tiered `model` inputs; the consumer supplies Bedrock-compatible identifiers directly through those same inputs (research D5) — no new model-mapping mechanism, no tiering change.
- [ ] T018 [P] [US3] Add a companion note to `specs/010-reusable-pipeline/contracts/credentials.md`'s "Non-goals" section, updating the line "No support here for Bedrock/Vertex/Foundry credentials (out of scope for v1; would be a non-breaking additive input later)" to point at `specs/016-bedrock-support/contracts/bedrock-provider.md` now that the Bedrock branch is implemented (Vertex/Foundry remain out of scope).
- [ ] T019 [US3] Add `use-bedrock`, `aws-role-arn`, and `aws-region` to `specs/010-reusable-pipeline/contracts/stage-interfaces.md`'s "Common inputs" table (alongside `pipeline-repo`/`default-branch`), since these three inputs are uniform across all nine agent-running stages exactly like the existing common-inputs entries — not a per-stage row.

**Checkpoint**: All three user stories are independently functional — the full quickstart.md scenario set (1–6) passes across all nine stages.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Static validation and end-to-end scenario walkthrough across the whole feature.

- [ ] T020 [P] Validate every workflow file touched by T002–T013 parses as YAML and every embedded `run:` script passes `bash -n`, matching `.github/workflows/lint-workflows.yml`'s own CI checks (plan.md's Testing section) — run locally (e.g. `python -c "import yaml,sys; yaml.safe_load(open(sys.argv[1]))"` per file plus a shell syntax check) or trigger `lint-workflows.yml` itself.
- [ ] T021 Desk-check FR-010 precedence end-to-end (research D4, contracts/bedrock-provider.md's Precedence section): confirm no task above introduced pipeline-side conditional logic that skips passing `claude_code_oauth_token`/`anthropic_api_key` when `use-bedrock` is true — all three values must reach every `claude-code-action` call unconditionally in every one of the nine stages, exactly as the two Anthropic credentials already do today, letting upstream Claude Code's own documented precedence decide.
- [ ] T022 Walk `specs/016-bedrock-support/quickstart.md`'s full scenario set (1–6) end-to-end against the finished workflow files, recording in the PR body which were exercised live (e.g. via a scratch consuming repository with a real AWS OIDC-trusted IAM role) versus desk-checked only — Scenario 4 (both an Anthropic credential and Bedrock configured) is explicitly flagged in research D4 as needing re-verification against the pinned `anthropics/claude-code-action` version, since its full confirmation depends on upstream's documented precedence behavior, not this repository's own logic.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately.
- **Foundational (Phase 2)**: Depends on Phase 1 (T002/T003 both add `with: use_bedrock: ...`-adjacent wiring that assumes T001's confirmed contract) — BLOCKS all user stories.
- **User Story 1 (Phase 3)**: Depends on Foundational (T004 invokes T002's composite and relies on T003's preflight branch). No dependency on other stories.
- **User Story 2 (Phase 4)**: Depends on User Story 1 (T005 desk-checks the exact wiring T004 produced).
- **User Story 3 (Phase 5)**: Depends on Foundational (T006–T013 each invoke T002/T003 the same way T004 did) and, for T014 only, on User Story 1 (T004) having already wired `intake.yml`, since T014's cross-stage grep covers all nine. T015–T019 (docs) depend on T006–T014 being complete (they document the finished, consistent surface).
- **Polish (Phase 6)**: Depends on all prior phases.

### User Story Dependencies

- **User Story 1 (P1)**: Independently implementable and testable after Foundational — the only story with no dependency on another story's tasks.
- **User Story 2 (P2)**: Validates User Story 1's output; independently testable once its own phase completes (quickstart.md Scenario 1 on `intake.yml` alone).
- **User Story 3 (P3)**: Repeats User Story 1's mechanism across the remaining eight stages and documents it; independently testable once its own phase completes (quickstart.md Scenario 5 across all nine stages).

### Within Each Story

- Composite creation (T002) before preflight extension (T003) — order is arbitrary between them (different files), but both must exist before any per-stage wiring task.
- Per-stage wiring (T004, T006–T013) before the cross-stage consistency check (T014).
- Cross-stage consistency (T014) before documentation (T015–T019), so docs describe the actually-finished surface.

### Parallel Opportunities

- T002 and T003 touch different files and can run in parallel.
- T006 through T013 each touch a distinct stage workflow file and can all run in parallel once Foundational (Phase 2) and T004 (US1's `intake.yml` reference wiring) are done.
- T015, T016, T017, T018, and T019 touch five different documentation/contract files and can all run in parallel with each other once T014 confirms the surface is finished.
- T020 (lint validation) is parallel-safe with T021/T022 (desk-check/scenario walkthrough) since it only reads the finished files.

---

## Parallel Example: User Story 3 stage wiring

```bash
# Launch together — eight different workflow files, same mechanical change:
Task: "Wire .github/workflows/clarify.yml with use-bedrock/aws-role-arn/aws-region"
Task: "Wire .github/workflows/plan.yml with use-bedrock/aws-role-arn/aws-region"
Task: "Wire .github/workflows/tasks.yml with use-bedrock/aws-role-arn/aws-region"
Task: "Wire .github/workflows/implement.yml with use-bedrock/aws-role-arn/aws-region"
Task: "Wire .github/workflows/finalize.yml with use-bedrock/aws-role-arn/aws-region"
Task: "Wire .github/workflows/cleanup.yml with use-bedrock/aws-role-arn/aws-region"
Task: "Wire .github/workflows/rebase.yml with use-bedrock/aws-role-arn/aws-region (two jobs)"
Task: "Wire .github/workflows/watchdog.yml with use-bedrock/aws-role-arn/aws-region (two jobs)"
```

## Parallel Example: Polish Documentation

```bash
# Launch together — five different doc/contract files:
Task: "Add a Bedrock subsection to docs/adoption.md's Credentials section"
Task: "Add a cross-reference note to docs/setup.md"
Task: "Add a Bedrock pass-through note to docs/architecture.md's Model tiering section"
Task: "Add a companion note to specs/010-reusable-pipeline/contracts/credentials.md's Non-goals section"
Task: "Add the three common inputs to specs/010-reusable-pipeline/contracts/stage-interfaces.md"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (confirm the upstream contract)
2. Complete Phase 2: Foundational (the new composite + the extended preflight)
3. Complete Phase 3: User Story 1 (`intake.yml` wired end-to-end)
4. **STOP and VALIDATE**: Run quickstart.md Scenarios 1, 3, and 6 against `intake.yml` alone
5. This alone proves the entire mechanism — every remaining task is the same mechanical change repeated across eight more files plus documentation

### Incremental Delivery

1. Setup + Foundational → shared composite and preflight branch ready
2. Add User Story 1 → validate Scenarios 1/3/6 on `intake.yml` → mergeable increment (MVP)
3. Add User Story 2 → validate Scenario 1's no-regression claim explicitly → mergeable increment (confidence before touching eight more files)
4. Add User Story 3 → validate Scenario 5 across all nine stages + documentation → mergeable increment (the full, adoptable capability)
5. Polish → validate the full Scenario 1–6 sweep together, plus static lint and the FR-010 precedence desk-check

### Why User Story 3 is sequenced after, not merged into, User Story 1

Spec.md frames User Story 1's Independent Test around *a* stage ("A consuming repository... enables the Bedrock flag when calling **a stage**"), while User Story 3's own value statement is explicit that "the value of the feature is only realized when the *whole* lifecycle can run on Bedrock." Building the mechanism once (Phase 2 + Phase 3) and then repeating it mechanically across the remaining eight stages (Phase 5) gives an honest MVP checkpoint after Phase 3 — a reviewer can validate the entire approach on one file before signing off on the same pattern being copied eight more times — rather than requiring all nine stages plus documentation to land atomically before anything is reviewable.
