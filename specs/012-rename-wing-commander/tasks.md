---

description: "Task list for renaming this product to Wing Commander"
---

# Tasks: Rename to Wing Commander

**Input**: Design documents from `/specs/012-rename-wing-commander/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/rename-migration.md, quickstart.md (all present)

**Tests**: Not requested. This is a text/filename rename with no application logic; verification is the `grep`/`actionlint`/dry-run procedure in `quickstart.md`, captured below as Polish-phase tasks.

**Organization**: Tasks are grouped by user story (spec.md: US1 = product displays as "Wing Commander", US2 = no broken references, US3 = attribution preserved).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: US1 / US2 / US3 per spec.md
- File paths are exact and relative to the repository root

## ⚠️ Findings that refine the plan — read before implementing

Cataloging every current file against `data-model.md` surfaced three things
the plan/research did not fully capture. Tasks below implement the
*corrected* behavior; flag these to the plan/spec owner if a different call
is wanted:

1. **`docs/adoption.md`'s and `docs/architecture.md`'s `@v1` copy-paste
   `uses:` examples must NOT get the bare (no-`reusable-`) filename.**
   `git tag -l` confirms `v1`/`v1.0.0` already exist and are immutable — the
   actual `v1` tag's tree still contains `reusable-<stage>.yml`, not
   `<stage>.yml`. Renaming the filename in a `@v1`-pinned example would
   document a 404 for every new adopter. Per `research.md`'s own redirect
   rationale, only the **owner/repo** (`charlesguse/speckit-action` →
   `charlesguse/wing-commander`) is safe to update in these specific frozen
   examples — GitHub's rename redirect makes both spellings resolve
   identically today. The filename, the `speckit-app-id`/
   `speckit-app-private-key` `secrets:` keys (the reusable workflow's actual
   declared `v1` interface), and the `SPECKIT_APP_ID`-style secret-name hints
   inside those specific code blocks stay byte-identical. Everything *outside*
   those frozen code blocks in the same files (titles, prose, the
   *current-state* naming-convention explanations, the `name:` display field
   inside the example — which is the adopter's own free choice, not part of
   the `v1` interface) renames normally.
2. **Two files outside `data-model.md`'s inventory contain the phrase
   `"speckit pipeline"` as self-description**: `.github/workflows/claude.yml`
   and `.github/workflows/claude-code-review.yml` (a `# Disabling for now
   while working on speckit pipeline` comment in each). `quickstart.md`'s own
   validation grep (`speckit pipeline`) would catch these and fail the "zero
   hits" check if left alone, so they're added as a small task (T010).
3. **The wrapper workflows' Actions-UI display names**
   (`name: "speckit · 1 intake"` etc., one per wrapper file) and the matching
   mentions in `docs/setup.md`'s smoke-test step ("Watch Actions →
   *speckit · 1 intake*") are human-facing product-name text not enumerated
   in `data-model.md`'s tables. Included in the relevant wrapper-file and
   `docs/setup.md` tasks below.

## Phase 1: Setup

- [X] T001 Reconfirm the rename inventory against the live tree before editing: re-run the `data-model.md`/`research.md` catalog sweep with `grep -rniE 'speckit|reusable-' --include='*.md' --include='*.yml' .` (excluding `specs/001-011-*`, `specs/012-rename-wing-commander/`, `.speckit-pipeline/`, `.claude-pr/`, `.claude/skills/speckit-*/`, `.specify/`) and diff the file list against the "Files touched" list in this document's task set below (T005–T027). No file changes in this task — it's a scope check that must turn up no new files before Phase 2 starts.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Rename every file/directory whose *path* changes, so every later task edits files at their final locations. All later phases depend on this phase.

- [X] T002 [P] `git mv` the 8 reusable stage workflow files, dropping the `reusable-` prefix (FR-009a; `data-model.md` "Reusable stage filenames" table): `.github/workflows/reusable-intake.yml` → `.github/workflows/intake.yml`; `reusable-clarify.yml` → `clarify.yml`; `reusable-plan.yml` → `plan.yml`; `reusable-tasks.yml` → `tasks.yml`; `reusable-implement.yml` → `implement.yml`; `reusable-finalize.yml` → `finalize.yml`; `reusable-cleanup.yml` → `cleanup.yml`; `reusable-rebase.yml` → `rebase.yml` (all in `.github/workflows/`)
- [X] T003 [P] `git mv` the 8 wrapper workflow files, `speckit-` → `wing-commander-` prefix (`data-model.md` "Wrapper stage filenames" table): `.github/workflows/speckit-1-intake.yml` → `wing-commander-1-intake.yml`; `speckit-2-clarify.yml` → `wing-commander-2-clarify.yml`; `speckit-3-plan.yml` → `wing-commander-3-plan.yml`; `speckit-4-tasks.yml` → `wing-commander-4-tasks.yml`; `speckit-5-implement.yml` → `wing-commander-5-implement.yml`; `speckit-6-finalize.yml` → `wing-commander-6-finalize.yml`; `speckit-7-cleanup.yml` → `wing-commander-7-cleanup.yml`; `speckit-rebase.yml` → `wing-commander-rebase.yml` (all in `.github/workflows/`)
- [X] T004 [P] `git mv` the 3 action directories, `speckit-` → `wing-commander-` prefix (`data-model.md` "Action directories" table): `.github/actions/speckit-context/` → `.github/actions/wing-commander-context/`; `.github/actions/speckit-preflight/` → `.github/actions/wing-commander-preflight/`; `.github/actions/speckit-metrics-summary/` → `.github/actions/wing-commander-metrics-summary/`

**Checkpoint**: `git status` shows 19 renames, no content changes yet. The pipeline is transiently broken (dangling `uses:`/`path:` references) until Phase 4 lands — expected, since this phase is a blocking prerequisite, not a shippable increment on its own.

---

## Phase 3: User Story 1 - Product presents itself as "Wing Commander" (Priority: P1) 🎯 MVP

**Goal**: Every human-facing surface (README, docs, constitution, PR/status text) names the product "Wing Commander," with Spec Kit attribution intact.

**Independent Test**: Read `README.md` and `docs/*.md` top to bottom; confirm "Wing Commander" is the only name presented as the product's own identity, and that "Spec Kit"/"spec-kit" mentions remain but read as attribution, not branding.

### Implementation for User Story 1

- [X] T005 [US1] `README.md` — display text only: title `# speckit-action` (line 1) → `# Wing Commander`; "speckit-action ships pipeline mechanics; it never ships or reads project content of its own" (line 73) → "Wing Commander ships..."; the `speckit-bot` GitHub App mention in Quickstart step 1 (line 54) → `wing-commander-bot`. Leave `SPECKIT_APP_ID`/`SPECKIT_APP_PRIVATE_KEY` (line 56) untouched — those are the *current* live secret names, not renamed until the v2 cut (see T034). Leave every `/speckit-specify`, `/speckit-plan`, `/speckit-tasks`, `/speckit-implement`, `/speckit-converge`, `/speckit-constitution` vendored-skill mention and every "spec-kit"/"GitHub spec-kit" attribution sentence (lines 6, 63, 71–72, 79–81) untouched.
- [X] T006 [P] [US1] `.specify/memory/constitution.md` — title `# Speckit GitHub Action Constitution` → `# Wing Commander Constitution`; Principle VI prose "...never bundled with or resolved from speckit-action..." → "...never bundled with or resolved from Wing Commander...". Leave the "spec-kit skills (`.claude/skills/speckit-*`)" and "Spec-kit is pinned (currently v0.12.4)" attribution mentions untouched.
- [X] T007 [P] [US1] `docs/adoption.md` — display text only: title `# Adopting the speckit pipeline` (line 1) → `# Adopting the Wing Commander pipeline`; the `speckit-bot` GitHub App cross-reference (line 31, link text and anchor target prose, not the anchor slug itself which T026 handles in `setup.md`) → `wing-commander-bot`. Leave every "spec-kit"/"Your own spec-kit artifacts" attribution sentence (lines 21–23, 71, 559, 561, 583, 614) untouched.
- [X] T008 [P] [US1] `docs/setup.md` — display text only: intro prose "the speckit pipeline" (line 3) and "never from speckit-action" (line 8) → "the Wing Commander pipeline" / "never from Wing Commander"; section heading `## 1. Create the speckit-bot GitHub App` (line 10) → `## 1. Create the wing-commander-bot GitHub App`; the literal suggested App name `` `speckit-bot` `` (line 20) → `` `wing-commander-bot` ``. Leave `.claude/skills/speckit-*` (line 6) and "spec-kit v0.12.4" (line 113) attribution untouched, and leave `SPECKIT_APP_ID`/`SPECKIT_APP_PRIVATE_KEY`/`SPECKIT_TASKS_REVIEW`/`SPECKIT_IMPLEMENT_MODEL`/`SPECKIT_MAX_ITERATIONS` (lines 41–42, 60–62) untouched per T034.
- [X] T009 [P] [US1] `docs/architecture.md` — display text only: "No stage resolves any project artifact from speckit-action itself" (line 294) → "...from Wing Commander itself"; section header `### Identity & chaining: the speckit-bot App` (line 72) → `### Identity & chaining: the wing-commander-bot App`. Leave "spec-kit moves fast" (Known risks table) attribution untouched.
- [X] T010 [P] [US1] `.github/workflows/claude.yml` and `.github/workflows/claude-code-review.yml` — the disabled-job comment `# Disabling for now while working on speckit pipeline. Might not be needed.` (one occurrence in each file) → `# Disabling for now while working on Wing Commander pipeline. Might not be needed.` (gap found versus `data-model.md`; required for `quickstart.md` step 1's grep to return zero hits)

**Checkpoint**: User Story 1 independently testable — README/docs/constitution name the product "Wing Commander" with Spec Kit attribution intact. (Internal filenames still say `speckit-*`/`reusable-*` in places until Phase 4 — that's User Story 2's job, tracked separately since it has its own independent test.)

---

## Phase 4: User Story 2 - No broken references after the rename (Priority: P1)

**Goal**: Every internal identifier — filenames, `uses:`/`path:` cross-references, concurrency groups, the OIDC audience, the rebase marker comment, step/workflow display names — resolves correctly after the Phase 2 renames, and the pipeline runs end-to-end.

**Independent Test**: `actionlint` passes, every `uses:`/`path:` reference resolves (`quickstart.md` step 2), and a dry-run on a sample issue completes every stage with no failure caused by a mismatched name (`quickstart.md` step 4).

### Implementation for User Story 2 — renamed reusable stage files (Phase 2/T002)

For each file below, update in place: the concurrency `group:` prefix `speckit-` → `wing-commander-`; the OIDC `audience=speckit-pipeline-ref` → `audience=wing-commander-pipeline-ref`; the self-checkout `path: .speckit-pipeline` → `path: .wing-commander-pipeline` and every `uses: ./.speckit-pipeline/.github/actions/speckit-*` → `uses: ./.wing-commander-pipeline/.github/actions/wing-commander-*`; the `Speckit context` step name → `Wing Commander context`; every `Checkout ... as speckit-bot` / `Re-checkout ... as speckit-bot` step name → `... as wing-commander-bot`; the `default: charlesguse/speckit-action` `pipeline-repo` input default → `default: charlesguse/wing-commander` (safe today — GitHub's repo-rename redirect resolves both; `research.md`); and any self-referential `(reusable-<stage>.yml)` mention in an error string → the bare `(<stage>.yml)` name plus its own `speckit <stage> stage:` log prefix → `wing-commander <stage> stage:`.

- [X] T011 [P] [US2] `.github/workflows/intake.yml`
- [X] T012 [P] [US2] `.github/workflows/clarify.yml`
- [X] T013 [P] [US2] `.github/workflows/plan.yml` — also its self-referential error string `speckit plan stage: ... produced by the intake stage (reusable-intake.yml)` → `wing-commander plan stage: ... (intake.yml)`
- [X] T014 [P] [US2] `.github/workflows/tasks.yml` — also its self-referential error string `speckit tasks stage: ... produced by the plan stage (reusable-plan.yml)` → `wing-commander tasks stage: ... (plan.yml)`
- [X] T015 [P] [US2] `.github/workflows/implement.yml` — also its self-referential error string `speckit implement stage: ... tasks.md is produced by the tasks stage (reusable-tasks.yml)` → `wing-commander implement stage: ... (tasks.yml)`; also the internal heredoc EOF markers `SPECKIT_REMAINING_EOF` / `SPECKIT_AGENT_MSG_EOF` → `WING_COMMANDER_REMAINING_EOF` / `WING_COMMANDER_AGENT_MSG_EOF` (both the opening `<<MARKER` and the closing line, same file, so writer/reader stay matched)
- [X] T016 [P] [US2] `.github/workflows/finalize.yml` — also its self-referential error string `speckit finalize stage: ... produced by the intake/plan/tasks stages` → `wing-commander finalize stage: ...`; also the internal heredoc EOF marker `SPECKIT_FILES_EOF` → `WING_COMMANDER_FILES_EOF` (opening and closing, same file)
- [X] T017 [P] [US2] `.github/workflows/cleanup.yml`
- [X] T018 [P] [US2] `.github/workflows/rebase.yml` — also the rebase-escalation marker comment `<!-- speckit-rebase: blocked branch-sha=... -->` → `<!-- wing-commander-rebase: blocked branch-sha=... -->` in both the writer (the line that emits the marker) and the reader (the `--jq` search pattern), same file

### Implementation for User Story 2 — renamed wrapper files (Phase 2/T003)

- [X] T019 [US2] All 8 files in `.github/workflows/wing-commander-*.yml` (`wing-commander-1-intake.yml` through `wing-commander-7-cleanup.yml` and `wing-commander-rebase.yml`): update each `uses: ./.github/workflows/reusable-<stage>.yml` line to `uses: ./.github/workflows/<stage>.yml` (matching T002's renames); update each file's header comment mentioning `reusable-<stage>.yml` by name (e.g. `wing-commander-4-tasks.yml`'s `# reusable-tasks.yml with mode: generate`) to the bare name; update each `name: "speckit · N <stage>"` workflow display field to `name: "Wing Commander · N <stage>"` (finding #3 above)

### Implementation for User Story 2 — renamed action directories (Phase 2/T004)

- [X] T020 [US2] `.github/actions/wing-commander-context/action.yml` — `name: speckit-context` → `name: wing-commander-context`; `description:` "Shared context for speckit pipeline stages: mints the speckit-bot GitHub App..." → "...Wing Commander pipeline stages: mints the wing-commander-bot..."; input/output descriptions "GitHub App ID of the speckit bot"/"Installation token for the speckit bot App" → "wing-commander bot"; step name `Mint speckit-bot App token` → `Mint wing-commander-bot App token`; header-comment snippet (lines 9–20) showing `path: .speckit-pipeline` / `uses: ./.speckit-pipeline/.github/actions/speckit-context` / "speckit-metrics-summary reads only runner.temp" → updated to `.wing-commander-pipeline` / `wing-commander-context` / `wing-commander-metrics-summary`. Leave `secrets.SPECKIT_APP_ID`/`secrets.SPECKIT_APP_PRIVATE_KEY` mentioned in the `app-id`/`private-key` input descriptions untouched (current live secret names; see T034)
- [X] T021 [US2] `.github/actions/wing-commander-preflight/action.yml` — rename this action's *own* identity only: `name: speckit-preflight` → `name: wing-commander-preflight`; log strings `speckit preflight: $1` / `❌ **speckit preflight failed**` / `✅ speckit preflight passed` / `::warning::speckit preflight: ...` → `wing-commander preflight` equivalents; header-comment cross-reference to `.github/actions/speckit-context/action.yml` → `wing-commander-context/action.yml`; the `(reusable-plan.yml)`/`(reusable-intake.yml)` mentions in `require-files` doc-comment and the `spec-meta.json` error message → `(plan.yml)`/`(intake.yml)`. **Do NOT rename** (Spec Kit dependency attribution, not this product's identifier): the `require-speckit` input name, the `REQUIRE_SPECKIT` env var, `SPECKIT_SUPPORTED_VERSION`, the `.speckit_version` JSON field read from the vendored `.specify/init-options.json`, or any "spec-kit"/"specify init"/"`.claude/skills/speckit-*`"/"`/speckit-constitution`" prose mention
- [X] T022 [P] [US2] `.github/actions/wing-commander-metrics-summary/action.yml` — `name: speckit-metrics-summary` → `name: wing-commander-metrics-summary` (only occurrence in this file)

### Implementation for User Story 2 — `release.yml`

- [X] T023 [US2] `.github/workflows/release.yml` — concurrency `group: speckit-release` → `group: wing-commander-release`; the actionlint glob and all four grep/for-loop globs currently `.github/workflows/reusable-*.yml` (lines ~62, 76, 81, 88, 104) → the explicit brace list `.github/workflows/{intake,clarify,plan,tasks,implement,finalize,cleanup,rebase}.yml` (a bare `*.yml` glob would now also match the wrapper files and `release.yml` itself, which these gates must not lint/grep as "published stages"); the stray-check pattern (line ~95) `grep -n 'charlesguse/speckit-action' ... | grep -v 'default: charlesguse/speckit-action'` → both occurrences updated to `charlesguse/wing-commander`; the top-of-file comment "actionlint over all reusable-*.yml" → the new glob description; the two `git tag` annotation messages (lines ~172, 174) `"speckit-action $TAG"` / `"speckit-action $MAJOR (currently $TAG)"` → `"wing-commander $TAG"` / `"wing-commander $MAJOR (currently $TAG)"`

### Implementation for User Story 2 — cross-referencing docs (current-state descriptions, distinct from the frozen `@v1` examples flagged above)

- [X] T024 [US2] `README.md` — internal identifiers only (depends on T005 having landed on this file first, to avoid overlapping edits): the "Status" section prose (lines 36–39) explaining the naming convention → rewrite to describe the new bare `<stage>.yml` / `wing-commander-N-<stage>.yml` convention (no more "reusable-" prefix); the stage table (lines 43–50), both columns, for all 8 rows → new bare reusable filenames and new wrapper filenames; "the published `reusable-*.yml` stages" (line 82) → new convention wording; "this repository's own `speckit-*.yml` workflows" (line 89) → `wing-commander-*.yml`; the Repository map code block (lines 122–128): `.github/workflows/reusable-*.yml` → describe the new bare-name convention, `.github/workflows/speckit-*.yml` → `.github/workflows/wing-commander-*.yml`, `.github/actions/speckit-context/` / `speckit-preflight/` / `speckit-metrics-summary/` → `wing-commander-` equivalents. Leave `.claude/skills/speckit-*/` (line 128) untouched (vendored, exempt).
- [X] T025 [US2] `docs/adoption.md` — internal identifiers only (depends on T007 landing first): "its `speckit-*.yml` workflows" (line 15) → `wing-commander-*.yml`; `.claude/skills/speckit-*` (line 26, exempt, leave); `charlesguse/speckit-action` accessibility mention (line 41) → `charlesguse/wing-commander`; each `### N. speckit-N-stage.yml` section subheading (e.g. line 121 `### 1. speckit-1-intake.yml`) → `### 1. wing-commander-1-intake.yml`, matching T003's renames; label prefix mention "`speckit-<slug>`-shaped" (line 573) → `wing-commander-<slug>`-shaped (matches the concurrency-group rename, T011–T018). **In the ~10 frozen `@v1` copy-paste code blocks** (the `name:`, `on:`, `uses:`, `secrets:` snippets under each numbered section, and the two "Private pipeline repository" snippets near lines 600/642): change **only** the owner/repo in each `uses: charlesguse/speckit-action/.github/workflows/reusable-<stage>.yml@v1` line to `charlesguse/wing-commander` — the filename stays `reusable-<stage>.yml` (see the flagged finding above) — and update the `name: "speckit · N <stage>"` display field to `name: "Wing Commander · N <stage>"` (the adopter's own free-form label, not part of the frozen interface). Leave the `secrets: speckit-app-id: / speckit-app-private-key:` keys, the `${{ secrets.SPECKIT_APP_ID }}` / `${{ secrets.SPECKIT_APP_PRIVATE_KEY }}` / `${{ vars.SPECKIT_TASKS_REVIEW }}` / `${{ vars.SPECKIT_IMPLEMENT_MODEL }}` / `${{ vars.SPECKIT_MAX_ITERATIONS }}` value expressions, and `next-workflow: speckit-5-implement.yml` / `self-workflow: speckit-5-implement.yml` dispatch-target values in those same code blocks completely untouched — they are the actual `v1` interface. Then append a new "Migrating to `@v2`" section (or extend the existing version-pinning section) containing the full migration table from `contracts/rename-migration.md` (new `uses:` paths, the five `SPECKIT_*` → `WING_COMMANDER_*` secret/variable renames) per `quickstart.md` step 6 — this table documents the *future* v2 interface and does not change today's `v1` behavior.
- [X] T026 [US2] `docs/setup.md` — internal identifiers only (depends on T008 landing first): `charlesguse/speckit-action` in the `PIPELINE_REPO_TOKEN` row (line 43) → `charlesguse/wing-commander` (safe — names the repo generally, not tied to a specific tag's filename); the smoke-test mentions "Watch Actions → *speckit · 1 intake*" (line 101) and "*speckit · 2 clarify*" (line 106) → `*Wing Commander · 1 intake*` / `*Wing Commander · 2 clarify*`, matching T019's workflow `name:` rename.
- [X] T027 [US2] `docs/architecture.md` — internal identifiers only (depends on T009 landing first): per-stage section headers (lines 134, 161, 186, 220, 231, 263) e.g. `## Stage 2 — Plan (reusable-plan.yml, wrapper speckit-3-plan.yml)` → `## Stage 2 — Plan (plan.yml, wrapper wing-commander-3-plan.yml)`; "Published stages & thin wrappers" intro (lines 5, 30, 32) describing `reusable-<stage>.yml`/`reusable-*.yml` as the current convention → bare-name convention; "Reusability" section (lines 285–313): line 294 handled in T009; line 301 "Stage bodies live in `reusable-<stage>.yml`..." → "Stage bodies live in `<stage>.yml`..."; line 308 "the `speckit-context`, `speckit-preflight`, and `speckit-metrics-summary` composites" → `wing-commander-context`/`wing-commander-preflight`/`wing-commander-metrics-summary`. **In the single frozen `@v1` example** (line 305, `uses: charlesguse/speckit-action/.github/workflows/reusable-plan.yml@v1`): change only the owner/repo to `charlesguse/wing-commander`, keep `reusable-plan.yml` (same frozen-interface reasoning as T025). Leave "spec-kit moves fast" (Known risks table) attribution untouched.

**Checkpoint**: User Stories 1 AND 2 both work — `actionlint` passes, every cross-reference resolves, and a pipeline dry-run completes with the new names end-to-end.

---

## Phase 5: User Story 3 - Attribution to Spec Kit remains accurate (Priority: P2)

**Goal**: Confirm the rename did not touch legitimate Spec Kit/Claude Code attribution.

**Independent Test**: `docs/adoption.md`/`docs/setup.md`/`README.md`/constitution still explain Wing Commander is built on Spec Kit and Claude Code, framed as dependencies, not as the product's own brand.

- [X] T028 [US3] After T005–T027 land, run `grep -n 'spec-kit\|Spec Kit\|Claude Code' README.md docs/adoption.md docs/setup.md .specify/memory/constitution.md` (per `quickstart.md` step 5) and diff the output against `data-model.md`'s "Attribution reference" entity list; confirm every listed sentence is byte-identical to before the rename (no file changes expected from this task — it's a verification gate; if any attribution sentence was accidentally altered, that's a defect to fix by reverting the offending line in the relevant Phase 3/4 task's file, not a new task)

**Checkpoint**: All three user stories independently verified.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Repository-wide validation per `quickstart.md`, plus the one non-file-edit action this feature depends on but cannot itself perform.

- [X] T029 [P] Run `quickstart.md` step 1's grep sweep repo-wide (`grep -rniE 'speckit-action|speckit pipeline|speckit github action' --include='*.md' --include='*.yml' .`, excluding `specs/001-011-*` and `specs/012-rename-wing-commander/`) — expect zero output after T005–T027
- [X] T030 [P] Run `quickstart.md` step 2's dangling-reference checks: confirm all 8 bare stage files exist, every `wing-commander-*.yml` wrapper's `uses:` target exists, and every `.wing-commander-pipeline/.github/actions/wing-commander-*` reference resolves to an existing directory
- [X] T031 Run `quickstart.md` step 3 (`actionlint` over `.github/workflows/*.yml`) — expect no errors
- [ ] T032 Run `quickstart.md` step 4: open a throwaway issue, apply the pipeline's entry label, and confirm intake → clarify → plan → tasks → implement → finalize → cleanup all trigger using the renamed files and post "Wing Commander"-branded status comments, with zero failures from a mismatched reference (SC-003)
- [X] T033 Confirm `docs/adoption.md`'s new migration section (added in T025) matches `contracts/rename-migration.md`'s table exactly (`quickstart.md` step 6)
- [ ] T034 **Manual/out-of-band, not a file edit**: before this feature's `v2` release is ever cut (not part of this feature's merge), create the repository secrets/variables `WING_COMMANDER_APP_ID`, `WING_COMMANDER_APP_PRIVATE_KEY`, `WING_COMMANDER_TASKS_REVIEW`, `WING_COMMANDER_IMPLEMENT_MODEL`, `WING_COMMANDER_MAX_ITERATIONS` in this repository's own GitHub Settings (copied from the current `SPECKIT_*` values) and only then update this repo's own `wing-commander-*.yml` wrappers' `secrets:`/`vars:` value expressions to read the new names — doing this before the release is cut would break this repo's own live dogfooded pipeline (FR-006), and doing it without first creating the new secrets breaks it immediately. Flagged here per FR-007/FR-010/SC-003 so it isn't lost; not assigned a code task because it is a GitHub Settings action, not a file change, and belongs to the future release-cut decision, not this rename's implementation.

---

## Dependencies & Execution Order

- **Setup (T001)**: no dependencies
- **Foundational (T002–T004)**: depends on T001; all three renames are independent of each other ([P]); BLOCKS every task below (all reference the new paths)
- **User Story 1 (T005–T010)**: depends on Foundational; all six files/pairs are independent of each other and of User Story 2 ([P] except T005, which is not marked [P] only because it's the sole task touching `README.md` in this phase)
- **User Story 2 (T011–T027)**:
  - T011–T018 (reusable stage files): depend on T002; independent of each other ([P])
  - T019 (wrapper files): depends on T003
  - T020–T022 (action files): depend on T004; independent of each other ([P])
  - T023 (release.yml): depends on T002 (references the renamed stage files)
  - T024: depends on T005 (same file, US1 must land first)
  - T025: depends on T003, T007 (same file)
  - T026: depends on T008 (same file)
  - T027: depends on T009 (same file)
- **User Story 3 (T028)**: depends on all of Phase 3 and Phase 4 completing (it verifies their combined output)
- **Polish (T029–T034)**: depend on all of Phases 3–5

### User Story Dependencies

- **User Story 1 (P1)**: independent of User Story 2 at the file-edit level (different lines in shared files, sequenced only to avoid literal merge conflicts) — can be demoed alone (README/docs read "Wing Commander") even before US2 lands, though the pipeline would still be transiently broken until US2 also lands, since both are P1 and ship together.
- **User Story 2 (P1)**: depends on Foundational; independently verifiable via `actionlint` + dry-run without needing US1's prose changes.
- **User Story 3 (P2)**: purely a verification pass over the combined output of US1 + US2; no independent implementation work.

### Parallel Example: User Story 1

```bash
# After Foundational (T002-T004) completes, launch these together:
Task: "constitution.md title + Principle VI prose"          # T006
Task: "docs/adoption.md title + speckit-bot cross-reference" # T007
Task: "docs/setup.md intro prose + App name"                 # T008
Task: "docs/architecture.md product-name prose + header"     # T009
Task: "claude.yml / claude-code-review.yml comment fix"       # T010
```

### Parallel Example: User Story 2 (reusable stage files)

```bash
Task: "intake.yml internal identifiers"     # T011
Task: "clarify.yml internal identifiers"    # T012
Task: "plan.yml internal identifiers"       # T013
Task: "tasks.yml internal identifiers"      # T014
Task: "implement.yml internal identifiers"  # T015
Task: "finalize.yml internal identifiers"   # T016
Task: "cleanup.yml internal identifiers"    # T017
Task: "rebase.yml internal identifiers"     # T018
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1 (Setup) and Phase 2 (Foundational — the renames everything else needs)
2. Complete Phase 3 (User Story 1)
3. **STOP and VALIDATE**: read `README.md`/`docs/*.md` — the product presents as "Wing Commander"
4. Note: the pipeline is still transiently broken at this checkpoint (US2 not done) — this MVP slice is a documentation/demo checkpoint, not a mergeable state on its own; both P1 stories ship together in practice

### Incremental Delivery

1. Setup + Foundational → file layout ready
2. User Story 1 → demo-able product identity
3. User Story 2 → pipeline functions end-to-end under the new names (now mergeable)
4. User Story 3 → attribution verified unchanged
5. Polish → full `quickstart.md` sign-off, plus the flagged manual secret-rotation prerequisite for the eventual `v2` cut

## Notes

- [P] tasks touch different files with no ordering requirement between them
- Several User Story 2 tasks are explicitly sequenced *after* their User Story 1 counterpart on the same file (T024 after T005, T025 after T007, T026 after T008, T027 after T009) to avoid two tasks editing the same file's overlapping regions out of order — not because the stories are dependent on each other's outcome
- The breaking-change secret/variable rename (`SPECKIT_*` → `WING_COMMANDER_*`) and the manual GitHub Settings step it requires (T034) are intentionally excluded from this feature's mergeable scope, per `contracts/rename-migration.md` and the versioning contract in `specs/010-reusable-pipeline/contracts/versioning.md` — only the documentation of that future migration (T025's new section) ships now
- Commit after each task or logical group; verify `git status` shows only the intended file at each step given several tasks touch large multi-concern files

---

## Phase 7: Convergence

Assessment after implement iteration 1: Phase 3 (US1 human-facing display
text — T001, T005–T010) is complete and committed. All remaining work is
still unbuilt because it is gated on the physical file/directory renames in
Phase 2, which the implement stage could not perform (see T035).

- [X] T035 **CRITICAL — blocker.** The renames in T002–T004 (and therefore every
  rename-dependent task below) could not be executed by the implement stage:
  its Claude `--allowedTools` (in `.github/workflows/reusable-implement.yml`,
  now the running stage) grant `Bash(git status|add|commit|push|pull|fetch|reset|log|diff|show:*)`
  but **not** `Bash(git mv:*)` or `Bash(git rm:*)`, and the sandbox blocks the
  shell `mv`/`rm` builtins, so no file can be moved or deleted — only created or
  overwritten (Write/Edit). Resolve by EITHER (a) a maintainer adding
  `Bash(git mv:*)` and `Bash(git rm:*)` to the implement-stage allowlist — a
  GitHub Actions permission change deliberately left out of this feature's task
  scope — OR (b) a maintainer performing the 19 renames (T002–T004) manually.
  Until one of these lands, T036–T044 cannot complete. (source: FR-009a, plan Phase 2; gap: contradicts/blocked)
- [X] T036 Complete **T002** — `git mv` the 8 `.github/workflows/reusable-<stage>.yml` files to bare `<stage>.yml` (per FR-009a; gap: missing). Blocked by T035.
- [X] T037 Complete **T003** — `git mv` the 8 `.github/workflows/speckit-N-<stage>.yml` wrappers to `wing-commander-N-<stage>.yml` (data-model wrapper filenames; gap: missing). Blocked by T035.
- [X] T038 Complete **T004** — `git mv` the 3 `.github/actions/speckit-*` directories to `wing-commander-*` (data-model action directories; gap: missing). Blocked by T035.
- [X] T039 Complete **T011–T018** — update internal identifiers in the renamed reusable stage files: concurrency `group:` prefix, OIDC `audience=…-pipeline-ref`, `path: .wing-commander-pipeline` + `uses: ./.wing-commander-pipeline/.github/actions/wing-commander-*`, step names, `pipeline-repo` default `charlesguse/wing-commander`, self-referential error strings, `plan.yml`/`tasks.yml`/`implement.yml`/`finalize.yml` heredoc EOF markers, and `rebase.yml`'s escalation marker comment (per US2; gap: missing). Blocked by T036.
- [X] T040 Complete **T019** — in the 8 renamed `wing-commander-*.yml` wrappers, update each `uses: ./.github/workflows/<stage>.yml` target, the `reusable-<stage>.yml` header-comment mentions, and the `name: "Wing Commander · N <stage>"` display field (per US2; gap: missing). Blocked by T037.
- [X] T041 Complete **T020–T022** — update the 3 renamed `action.yml` files' `name:`, descriptions, step names, header-comment snippets, and self-referential `(reusable-*.yml)` mentions to the `wing-commander-*` / bare-name forms, leaving the `SPECKIT_*` secret names and Spec Kit dependency identifiers untouched (per US2; gap: missing). Blocked by T038.
- [X] T042 Complete **T023** — `.github/workflows/release.yml`: concurrency `group: wing-commander-release`; replace the `reusable-*.yml` actionlint/grep globs with the explicit `{intake,clarify,plan,tasks,implement,finalize,cleanup,rebase}.yml` brace list; update both `charlesguse/speckit-action` stray-check patterns; the top-of-file comment; and the two `git tag` annotation messages to `wing-commander …` (per US2; gap: missing). Blocked by T036.
- [X] T043 Complete **T024–T027** — docs current-state cross-references: README stage table/status/repo-map; `docs/adoption.md` `wing-commander-*.yml` refs, section subheadings, `@v1` example owner/repo (filename stays `reusable-*.yml`), and the new `@v2` migration section from `contracts/rename-migration.md`; `docs/setup.md` `PIPELINE_REPO_TOKEN` repo + smoke-test display names; `docs/architecture.md` per-stage headers, composite names, and `@v1` example owner/repo (per US1/US2; gap: partial). Blocked by T036–T038.
- [ ] T044 Complete **T028–T033** — run the verification gates once the renames land: attribution diff (T028), zero-hits grep sweep (T029), dangling-reference checks (T030), `actionlint` (T031), pipeline dry-run (T032), migration-table match (T033) (per SC-002, SC-003; gap: missing). Blocked by T036–T043.
