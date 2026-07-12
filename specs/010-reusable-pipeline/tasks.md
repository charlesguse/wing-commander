# Tasks: Reusable Pipeline Extraction

**Input**: Design documents from `/specs/010-reusable-pipeline/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/ (stage-interfaces.md, credentials.md, versioning.md), quickstart.md

**Tests**: Not requested in the spec — no automated test tasks. Validation is `actionlint` (CI) plus the quickstart.md scenarios; scenarios needing an external test repository or a human timer are marked **MANUAL** and must be reported to the lifecycle issue (constitution IV), not silently skipped.

**Organization**: Tasks are grouped by user story. Story order follows spec priorities: US1 (P1) → US2 (P2) → US4 (P2) → US3 (P3). US3 (dogfooding) intentionally comes after US2/US4 because rewriting this repo's wrappers requires the published stages to be event-agnostic and credential-complete first.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3, US4)

## Path Conventions

All paths are repository-root-relative. This feature touches only `.github/workflows/`, `.github/actions/`, `docs/`, and `README.md` — there is no `src/` (GitHub Actions YAML project, see plan.md Technical Context).

---

## Phase 1: Setup

**Purpose**: Make CI able to validate everything the later phases produce.

- [X] T001 Confirm `.github/workflows/lint-workflows.yml` lints the whole `.github/workflows/*.yml` glob (it must cover the upcoming `reusable-*.yml` and `release.yml`); extend its paths/glob if it is workflow-name-scoped.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared pieces every extracted stage consumes. No stage extraction can merge before these exist.

**⚠️ CRITICAL**: T002 and T003 block all user-story phases.

- [X] T002 Create `.github/actions/speckit-preflight/action.yml` composite per contracts/credentials.md and research.md D7: inputs `oauth-token`, `api-key` (values, so the composite can test emptiness), `require-speckit` (bool), `require-files` (newline list of consumer-checkout paths), `require-meta-stage` (optional expected `spec-meta.json` stage + `spec-dir`); fails with the contract's exact-secret-names message when both credentials are empty, and with a missing-prerequisite message naming the providing step (`specify init`, predecessor stage) for file/stage checks; when `.specify/init-options.json` is present, warn (never fail) on a spec-kit version mismatch against the pipeline's supported version — a `SPECKIT_SUPPORTED_VERSION` constant declared at the top of this composite's `action.yml`, updated whenever the constitution's spec-kit pin changes. Pure shell — no agent, no network.
- [X] T003 [P] Audit `.github/actions/speckit-context/action.yml` and `.github/actions/speckit-metrics-summary/action.yml` for workspace-relative assumptions that break when the action is resolved from a `.speckit-pipeline/` subdirectory checkout (research.md D3 pattern); fix any (e.g., paths relative to `github.action_path` vs. workspace). Record the verified self-checkout snippet as a comment header in `.github/actions/speckit-context/action.yml`.

**Checkpoint**: Preflight composite exists; shared composites proven relocatable.

---

## Phase 3: User Story 1 — Adopt the pipeline without copying it (Priority: P1) 🎯 MVP

**Goal**: Every stage published as an independently referenceable `workflow_call` workflow, versioned by release, adoptable from the docs alone.

**Independent Test**: quickstart.md Scenario 1 — fresh repo + published docs only → spec PR from that repo's own templates in under 60 minutes; Scenario 6 — pinned adopters unaffected until pin moves.

### Implementation for User Story 1

- [X] T004 [US1] Extract `.github/workflows/reusable-intake.yml` from `speckit-1-intake.yml` per contracts/stage-interfaces.md: `on: workflow_call` only; inputs `issue-number`, `model` (default `claude-opus-4-8`), `max-turns` (default 50), `pipeline-repo`; secrets `claude-code-oauth-token`, `anthropic-api-key`, `speckit-app-id`, `speckit-app-private-key`; job sequence = consumer checkout → pipeline self-checkout at `github.job_workflow_sha` (research.md D3) → speckit-preflight → speckit-context → default-branch resolution (`default-branch` input or `gh repo view --json defaultBranchRef` — no literal `main` anywhere) → feature-number allocation → agent step (both credential inputs passed) → PR labeling → execution-log upload → metrics summary; outputs `spec-dir`, `feature-num`. **This task sets the skeleton every other extraction copies — its structure is the pattern.**
- [X] T005 [P] [US1] Extract `.github/workflows/reusable-clarify.yml` from `speckit-2-clarify.yml` per contracts/stage-interfaces.md (inputs `issue-number`, `comment-id`, `model` default `claude-opus-4-8`, `max-turns`), following the T004 skeleton.
- [X] T006 [P] [US1] Extract `.github/workflows/reusable-plan.yml` from `speckit-3-plan.yml` per contracts/stage-interfaces.md: inputs `head-ref` or `slug` (one required), `merged`, `model` default `claude-sonnet-5`, `max-turns`; slug derivation + duplicate-plan guard + hand-submitted-spec issue creation stay inside the stage; outputs `spec-branch`, `spec-dir`.
- [X] T007 [P] [US1] Extract `.github/workflows/reusable-tasks.yml` from `speckit-4-tasks.yml` per contracts/stage-interfaces.md: inputs `mode` (`generate`|`approved`, default `generate`), `head-ref`/`slug`, `tasks-review` (default `auto`), `model` default `claude-sonnet-5`, `max-turns` default 60, `next-workflow` (default `""` = no dispatch). `mode: approved` is the agent-free entry point for a merged tasks PR (validates slug, dispatches `next-workflow`) — the `pull_request: closed` trigger for it stays wrapper-side, since a `workflow_call` workflow has no triggers of its own.
- [X] T008 [P] [US1] Extract `.github/workflows/reusable-implement.yml` from `speckit-5-implement.yml` per contracts/stage-interfaces.md: inputs `spec-dir`, `issue-number`, `iteration`, `model` default `claude-sonnet-5`, `max-iterations` (default 5), `self-workflow` (default `""`), `next-workflow` (default `""`); iteration-cap check, converge commit-range walk, tier-up retry, and stall marking stay internal; empty chaining inputs ⇒ post converge report to issue and stop; output `converged`.
- [X] T009 [P] [US1] Extract `.github/workflows/reusable-finalize.yml` from `speckit-6-finalize.yml` per contracts/stage-interfaces.md (inputs `spec-dir`, `issue-number`, `converged`, `summary-model` default `claude-haiku-4-5`; output `pr-number`).
- [X] T010 [P] [US1] Extract `.github/workflows/reusable-cleanup.yml` from `speckit-7-cleanup.yml` per contracts/stage-interfaces.md: inputs are raw PR facts (`head-ref`, `base-ref`, `merged`); the three-way outcome self-selection and identity-refusal steps stay internal; output `outcome`.
- [X] T011 [P] [US1] Extract `.github/workflows/reusable-rebase.yml` from `speckit-rebase.yml` per contracts/stage-interfaces.md (inputs `model` default `claude-sonnet-5`, `max-turns`; discover→matrix fan-out, lease push, escalate-once marker all internal).
- [X] T012 [US1] Create `.github/workflows/release.yml` per contracts/versioning.md: `workflow_dispatch` (`version`, `breaking`); actionlint gate over `reusable-*.yml`; create annotated `vX.Y.Z` tag; create-or-advance the floating major tag for the release's **own** major (force-move for non-breaking, create for the first release of a new major — a breaking release must start a new major and never touches the previous major's floating tag); create GitHub Release whose notes always contain a Breaking-changes section.
- [X] T013 [US1] Write `docs/adoption.md` (research.md D8): prerequisites (own `specify init` + constitution, credentials from the adopter's plan, GitHub App one-time setup referencing docs/setup.md, and that the pipeline repository is accessible to the adopting repository — reusable workflows and the self-checkout both require it), the minimal full-pipeline wrapper set as copy-paste YAML pinned `@v1` (wrappers show the security gates — constitution V obligation — and the dispatch-target wrappers declare the chaining payload inputs verbatim per contracts/stage-interfaces.md), version pinning guidance (exact vs. floating tag), and the credential rules per contracts/credentials.md. Adopter-facing docs use the stage name `rebase` (the spec's "auto-rebase") consistently, noting its triggers are automatic.
- [X] T014 [P] [US1] Update `README.md`: "Using this on your own project" step 2 becomes the thin-wrapper reference (link docs/adoption.md); roadmap milestone 4 marked done; repository map gains `reusable-*.yml` / `docs/adoption.md`.
- [X] T015 [US1] **MANUAL** Run quickstart.md Scenario 1 in a fresh test repository (timed, docs-only adoption at `@main` pre-release); report elapsed time and outcome on the lifecycle issue (SC-001, acceptance 1.1).

**Checkpoint**: All 8 stages referenceable from another repository; adoption documented end-to-end. MVP delivered.

---

## Phase 4: User Story 2 — Pick only the methods you want (Priority: P2)

**Goal**: Any subset of stages works with adopter-chosen triggers, gates, and labels; no stage requires the full lifecycle.

**Independent Test**: quickstart.md Scenario 2 — exactly one stage adopted with a custom trigger completes with no sibling stage, label, or convention present.

### Implementation for User Story 2

- [X] T016 [US2] Audit every `.github/workflows/reusable-*.yml` for: `github.event.*` and `vars.*` references (research.md D2/D5 — must be zero; event facts and configuration arrive only via declared inputs); literal `main` branch references (must use the `default-branch` input/derivation — spec edge case 3); hardcoded publisher owner/repo strings outside the `pipeline-repo` input default (FR-005); and every agent step having a bounded `--max-turns` sourced from a defaulted or required input (constitution II). Fix any stragglers; add grep one-liners for these invariants to the release.yml lint gate.
- [X] T017 [US2] Verify and, where missing, implement the standalone paths in `.github/workflows/reusable-tasks.yml` and `.github/workflows/reusable-implement.yml`: with `next-workflow`/`self-workflow` empty, the stage completes its own work, posts its report, and stops cleanly — no failed dispatch step, no required label (FR-002, acceptance 2.1).
- [X] T018 [P] [US2] Add the per-stage reference to `docs/adoption.md`: one section per stage with inputs/secrets/outputs/preconditions/side-effects tables derived from contracts/stage-interfaces.md, each with a minimal single-stage wrapper example using a custom trigger (acceptance 2.2, 2.3, FR-010).
- [X] T019 [US2] **MANUAL** Run quickstart.md Scenario 2 (single-stage adoption, custom `workflow_dispatch` trigger, no sibling conventions) and Scenario 4 (missing spec-kit / missing predecessor refusals) in the test repository; report outcomes on the lifecycle issue (SC-002, FR-009).

**Checkpoint**: Single-stage adoption proven; stage reference published.

---

## Phase 5: User Story 4 — Bring your own Claude subscription, either credential type (Priority: P2)

**Goal**: OAuth token and API key both first-class; deterministic fail-fast when neither is configured; documented API-key-wins precedence.

**Independent Test**: quickstart.md Scenario 3 — preflight failure names both secrets before any agent work; OAuth-only run completes; API-key wiring confirmed by review (per spec clarification).

### Implementation for User Story 4

- [X] T020 [US4] Verify dual-credential wiring across all eight `.github/workflows/reusable-*.yml`: both secrets declared optional, both passed to every `anthropics/claude-code-action` step (`claude_code_oauth_token` + `anthropic_api_key`), speckit-preflight invoked with both values before the first agent step in every stage (contracts/credentials.md; FR-003, FR-004). Fix gaps; this is the code-review verification the spec's clarification designates for the API-key path.
- [X] T021 [P] [US4] Credential documentation: `docs/adoption.md` credentials section states where each credential comes from (`claude setup-token` vs. Claude Console), the API-key-wins precedence with a link to Claude Code's authentication-precedence doc, and the exact preflight error text; update `docs/setup.md` secrets table so `ANTHROPIC_API_KEY` is a first-class alternative (no more "swap the input name in the workflows") (FR-010, acceptance 4.4).
- [X] T022 [US4] **MANUAL** Run quickstart.md Scenario 3 in the test repository: neither credential ⇒ preflight failure naming both secret names with zero agent cost; OAuth-only ⇒ stage completes. Report on the lifecycle issue (SC-005, acceptance 4.1, 4.3).

**Checkpoint**: Credential contract enforced and documented; SC-005/SC-006 posture satisfied.

---

## Phase 6: User Story 3 — The publisher dogfoods the published pipeline (Priority: P3)

**Goal**: This repository's workflows become thin wrappers calling the published stages by local path; stage logic exists in exactly one place.

**Independent Test**: quickstart.md Scenario 5 — no stage logic in any `speckit-*` wrapper; a full lifecycle run executes every stage inside a `reusable-*` called workflow.

**Depends on**: Phases 3–5 (stages must be extracted, event-agnostic, credential-complete before wrappers can call them).

### Implementation for User Story 3

- [X] T023 [US3] Rewrite `.github/workflows/speckit-1-intake.yml` as a thin wrapper: keep `on: issues: [labeled]`, the `spec-request` gate, permissions, and intake concurrency group; job body becomes `uses: ./.github/workflows/reusable-intake.yml` with `issue-number: ${{ github.event.issue.number }}` and this repo's secrets. **This task sets the wrapper pattern the rest copy.**
- [X] T024 [P] [US3] Rewrite `.github/workflows/speckit-2-clarify.yml` as a thin wrapper (keep comment-trigger + commenter-authorization gates; pass `issue-number`, `comment-id`).
- [X] T025 [P] [US3] Rewrite `.github/workflows/speckit-3-plan.yml` as a thin wrapper (keep `pull_request: closed` + `workflow_dispatch` triggers and head-prefix guard `if:`; pass `head-ref`/`slug`, `merged`).
- [X] T026 [P] [US3] Rewrite `.github/workflows/speckit-4-tasks.yml` as a thin wrapper with both triggers: plan-PR-merged calls the stage with `mode: generate`; tasks-PR-merged (`pull_request: closed`, base `spec/**`, head `tasks/*`, merged) calls it with `mode: approved`. Pass `tasks-review: ${{ vars.SPECKIT_TASKS_REVIEW }}`, `next-workflow: speckit-5-implement.yml`.
- [X] T027 [P] [US3] Rewrite `.github/workflows/speckit-5-implement.yml` as a thin wrapper (keep `workflow_dispatch` inputs; wire `model` from `vars.SPECKIT_IMPLEMENT_MODEL` / `model:opus` label lookup — the label read is lifecycle convention and stays wrapper-side per research.md D5; `max-iterations: ${{ vars.SPECKIT_MAX_ITERATIONS }}`, `self-workflow: speckit-5-implement.yml`, `next-workflow: speckit-6-finalize.yml`).
- [X] T028 [P] [US3] Rewrite `.github/workflows/speckit-6-finalize.yml` as a thin wrapper (keep `workflow_dispatch`; pass `spec-dir`, `issue-number`, `converged`).
- [X] T029 [P] [US3] Rewrite `.github/workflows/speckit-7-cleanup.yml` as a thin wrapper (keep repo-wide `pull_request: closed` trigger; pass raw `head-ref`, `base-ref`, `merged` — outcome selection now lives in the reusable stage).
- [X] T030 [P] [US3] Rewrite `.github/workflows/speckit-rebase.yml` as a thin wrapper (keep `push`-to-main + schedule triggers and bot-actor skip).
- [X] T031 [US3] Update `docs/architecture.md`: rewrite the "Reusability roadmap" section as current-state (published stages, wrapper pattern, self-checkout mechanism, release contract); adjust the Foundations section so stage descriptions point at `reusable-*.yml`.
- [X] T032 [US3] **MANUAL** Run one full lifecycle in this repository (issue → label → merges through cleanup) and confirm every stage job executed inside a `reusable-*` called workflow; report on the lifecycle issue (acceptance 3.1, SC-003).

**Checkpoint**: Publisher and adopters consume the identical `workflow_call` interface.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [X] T033 Duplication audit (SC-003): verify every `speckit-*.yml` wrapper contains no agent prompt, branch surgery, or spec-meta write (e.g., `grep -l "claude-code-action" .github/workflows/speckit-*.yml` must return nothing); delete any dead logic left behind by the rewrites.
- [X] T034 [P] Cross-check `docs/adoption.md`, `docs/setup.md`, `README.md`, and `docs/architecture.md` tell one consistent story (same secret names, same version-pinning advice, same stage names as contracts/stage-interfaces.md — a single naming convention: `rebase`, not "auto-rebase"). Also fix plan.md Scale/Scope composite-action count ("2–3" → 3), and verify every `reusable-*.yml` declares the contract's common inputs (`default-branch`, `pipeline-repo`) even where a task's inline enumeration (T004) omitted them.
- [X] T035 **MANUAL** Run quickstart.md Scenario 6 (pin an exact tag → publish non-breaking release → pinned repo unchanged; switch to `@v1` → fix arrives automatically; release notes carry Breaking-changes section), then publish `v1.0.0` via `release.yml` once Scenarios 1–5 have passed. Report on the lifecycle issue (FR-008, acceptance 1.2).

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: none.
- **Foundational (Phase 2)**: after Setup. T002/T003 block all extractions.
- **US1 (Phase 3)**: after Foundational. T004 (skeleton) blocks T005–T011; T012–T014 after the stages they document exist in draft; T015 last.
- **US2 (Phase 4)** and **US4 (Phase 5)**: after Phase 3's extraction tasks (they audit/extend the `reusable-*.yml` files) — the two phases are mutually independent and can run in parallel.
- **US3 (Phase 6)**: after Phases 3–5 (wrappers call the finished stage interfaces). T023 (wrapper pattern) blocks T024–T030.
- **Polish (Phase 7)**: after all story phases; T035 is the final gate before `v1.0.0`.

### User Story Dependencies

- **US1 (P1)**: independent — the MVP.
- **US2 (P2)**: layers on US1's files; independently testable via Scenario 2.
- **US4 (P2)**: layers on US1's files; independent of US2; testable via Scenario 3.
- **US3 (P3)**: requires US1 (spec-stated dependency); benefits from US2/US4 being done first.

### Parallel Opportunities

- T002 ∥ T003 (different action directories).
- T005–T011: seven stage extractions in parallel once T004 lands (seven different files).
- T014 ∥ T013 finish; T018 ∥ T016/T017; T021 ∥ T020.
- Phases 4 and 5 in parallel (different concerns, mostly different files — coordinate on `docs/adoption.md` sections).
- T024–T030: seven wrapper rewrites in parallel once T023 lands.

## Parallel Example: User Story 1

```bash
# After T004 establishes the skeleton, launch the remaining extractions together:
Task: "Extract reusable-clarify.yml from speckit-2-clarify.yml"    # T005
Task: "Extract reusable-plan.yml from speckit-3-plan.yml"          # T006
Task: "Extract reusable-tasks.yml from speckit-4-tasks.yml"        # T007
Task: "Extract reusable-implement.yml from speckit-5-implement.yml" # T008
Task: "Extract reusable-finalize.yml from speckit-6-finalize.yml"  # T009
Task: "Extract reusable-cleanup.yml from speckit-7-cleanup.yml"    # T010
Task: "Extract reusable-rebase.yml from speckit-rebase.yml"        # T011
```

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Phase 1 + Phase 2 (T001–T003).
2. Phase 3: extract all eight stages, release workflow, adoption doc (T004–T014).
3. **STOP and VALIDATE**: Scenario 1 in a test repo at `@main` (T015).
4. US1 alone already lets an adopter run the full pipeline by reference.

### Incremental Delivery

1. US1 → external adoption works (MVP).
2. US2 → partial adoption + per-stage reference.
3. US4 → credential contract enforced and documented.
4. US3 → this repo switches to its own published stages; logic exists once.
5. Polish → consistency audits, Scenario 6, tag `v1.0.0`.

### Notes

- MANUAL tasks (T015, T019, T022, T032, T035) need an external test repository and/or human timing; per constitution IV each must be reported to the lifecycle issue when the automated portion of its phase completes.
- Every extraction task must preserve constitution II (explicit `--model` + `--max-turns` from inputs) and V (prompt framing, least-privilege `--allowedTools`, no web tools) exactly as in the source workflow — extraction moves logic, it does not relax it.
- Commit after each task or logical group; wrappers and their reusable stage must land in the same PR only for US3 tasks (this repo must never be broken mid-transition).
