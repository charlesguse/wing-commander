---

description: "Task list template for feature implementation"
---

# Tasks: Private-Image Credentials That Reach Every Stage Job

**Input**: Design documents from `/specs/044-private-registry-credentials/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/private-registry-credentials.md, quickstart.md — all read in full before this file was written.

**Tests**: Not requested. This repository has no application test suite for its stage files; verification is PR-time lint gates (Gate 22 and friends) plus the scratch-adopter-repository scenarios in `quickstart.md`, per the plan's own Testing section.

**Organization**: Tasks are grouped by user story per spec.md's priorities (P1: US1/US2/US3, P2: US4/US5, P3: US6/US7). User Story 5 (the mechanism is proven before it is built) is delivered by Phase 2 (Foundational) rather than its own late phase, because FR-016 makes it a hard blocking prerequisite for every other story, not an independent increment that could ship after them.

## Contingency guide — read this before executing any task below

Per FR-026, research D3, and this plan's own repeated emphasis, **which of three outcomes ships is not known yet** — it depends on Phase 2's live-runner probes (P1/P2), which this tasks-generation pass cannot itself run (no `.github/workflows` write access, no dispatch/PR authority under this stage's own tool allowlist — the identical gap specs/038's plan stage hit and recorded honestly, per `specs/038-runner-container-passthrough/research.md`'s "T001 outcome... still not verified" precedent). Do not fabricate a probe result to unblock later tasks. The tasks below are written so that whichever real outcome Phase 2 records, there is a concrete next task:

- **Outcome 1** (preferred — `credentials: {}` suppresses the login attempt; no new stage input): execute Phase 3 tasks **T007–T019** as written, skip T020, skip T021.
- **Outcome 2** (one opt-in input required): execute **T020** instead of T007–T018's literal expression (same files, different expression — see T020's text), still execute T019, skip T021, and additionally execute **T041**.
- **Outcome 3** (measured-and-not-possible): skip T007–T020 entirely (no stage file is edited), execute **T021** only, skip Phase 5 (US3) entirely, and use the Outcome-3 framing in Phase 8's documentation tasks instead of the Outcome-1/2 framing.
- **If Phase 2's probes cannot be run at all** under this pipeline's own implement-stage tool allowlist (the same gap this planning pass hit): do not guess. Record that fact in `research.md` exactly the way `specs/038-runner-container-passthrough/research.md` recorded T001's non-execution, leave Phases 3, 5, 7 (the stage-file, ECR-component, and Gate 22 edits) undone, and stop after Phase 2 — this is a valid, honest terminal state for one pipeline pass, not a failure to hide.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1–US7)
- Every task names an exact file path (or, where a job list can't be fully enumerated from prior research, the exact `grep` to run to enumerate it)

---

## Phase 1: Setup

**Purpose**: Confirm the baseline this feature amends matches what research.md already measured, before touching anything.

- [X] T001 Run `python3 -c "import sys; sys.path.insert(0,'.github/scripts'); from wc_published_stages import published_stages; print(published_stages())"` (or the equivalent already used by `verify-gate-22.py`'s `check_derivations_agree`) plus `grep -rn 'image:[[:space:]]*\${{[[:space:]]*inputs\.container-image' .github/workflows/*.yml | wc -l` from the repo root. Confirm: 12 files reported as published stages (intake, clarify, plan, tasks, implement, finalize, cleanup, watchdog, pr-conversation, rebase, auto-update-spec-kit, metrics-persist) and 42 total job-level `container.image` matches, matching research.md D1's verified baseline. If either number has drifted since 2026-09-07, record the drift in `research.md` D1 before proceeding — the per-file task list below (T007–T018) assumes this baseline. **Done (implementation, 2026-09-07)**: re-verified via Grep — 12 files declare `workflow_call:` (same 12 named above) and 42 total `image: ${{ inputs.container-image }}` job matches, split identically to research.md D1's baseline (intake 2, clarify 2, plan 2, tasks 5, implement 2, finalize 2, cleanup 4, watchdog 5, pr-conversation 5, rebase 2, auto-update-spec-kit 10, metrics-persist 1). No drift.

---

## Phase 2: Foundational (Blocking Prerequisites — delivers User Story 5)

**Purpose**: FR-016/User Story 5 forbid touching any stage file, `lint-workflows.yml`, or shipping `wing-commander-ecr-credentials` before two live-runner probes are run on real GitHub-hosted runners and their evidence is recorded. This phase **is** User Story 5's independent test, executed as a prerequisite rather than a late-priority increment, because every other phase's design is contingent on its outcome.

**⚠️ CRITICAL**: No task in Phase 3, 5, or 7 may be executed until T002–T006 are complete and their outcome is recorded.

- [X] T002 Dispatch the P1 probe (research D3): in a throwaway `workflow_dispatch` workflow (never merged as a permanent file — delete it when done, mirroring PR #226's own discipline and `specs/038-runner-container-passthrough/tasks.md` T001's stated method), create one job per row of research D3's probe table:
  - P1.1: no image, no secrets, `credentials: ${{ fromJSON('{}') }}`
  - P1.2: public image (e.g. `node:20`), no secrets, same `credentials:` expression — **this is the decisive row**
  - P1.3: public image, only one secret set (the other empty string)
  - P1.4: private test image, both secrets set to real, correct credentials
  - P1.5: private test image, both secrets set to real but incorrect credentials

  Dispatch it on real GitHub-hosted runners. Record the run URL. **Done (implementation, 2026-09-07)**: could not be dispatched — this run's fixed tool allowlist has no `gh workflow run`/`gh run view`/`gh api`. Recorded as a "P1 outcome" paragraph in research.md D3, mirroring specs/038's T001 precedent.
- [X] T003 Dispatch the P2 probe (research D4), in the same or a second throwaway `workflow_dispatch` workflow: job A mints a known dummy token, masks it with `::add-mask::`, sets it as a step output; job B (`needs: A`) echoes `needs.A.outputs.token` in a step of its own (P2.1); a third job forwards the same masked value as a `secrets:` value into a `uses:` call to a minimal test reusable workflow and that workflow's own job echoes it too (P2.2). Dispatch it. Download the **raw** job logs via the run's API/artifact (not just the rendered UI) and search for the literal dummy token value in every job's log. Record the run URL and the search result. **Done (implementation, 2026-09-07)**: same tooling gap as T002 — could not be dispatched. Recorded as a "P2 outcome" paragraph in research.md D4.
- [X] T004 Replace research.md's "Blocking prerequisite for `tasks.md`" section (currently the last section of the file) with the real P1 evidence: for each of P1.1–P1.5, the observed behavior (clean run / template error / attempted-and-failed login) and the run URL from T002. Update the "one open question this contract rests on" table in `contracts/private-registry-credentials.md` (the row currently marked "Open — this contract's own P1.2, research D3") with the measured result. **Done (implementation, 2026-09-07)**: no real evidence exists (T002 blocked). Recorded that fact instead, in both research.md (P1 outcome paragraph) and the contract's P1.2 row.
- [X] T005 Record the real P2 evidence from T003 into research.md D4 (replacing its "unverified, blocking" framing) and into `contracts/private-registry-credentials.md`'s "cross-job masked hand-off" section (currently "FR-012's masking guarantee for this exact shape is open"). If the value leaked anywhere, record exactly which job/log and do not mark FR-012 satisfied. **Done (implementation, 2026-09-07)**: no real evidence exists (T003 blocked). Recorded that fact instead, in both research.md (P2 outcome paragraph) and the contract's masked-hand-off section. FR-012 not marked satisfied.
- [X] T006 Using T004's recorded result, determine which of FR-026's three outcomes applies per research D3's decision tree, and write that determination as a new dated paragraph at the top of research.md's D3 section (e.g. "**Outcome determined 2026-MM-DD**: Outcome 1/2/3, because..."). This paragraph is what every task from Phase 3 onward is conditional on — do not proceed past this task without it existing. If T002/T003 could not be dispatched at all under this pipeline's own tool allowlist, write that fact instead (mirroring `specs/038-runner-container-passthrough/research.md`'s "T001 outcome... still not verified" paragraph, dated), and stop — do not execute Phase 3, 5, or 7's file edits this pass. **Done (implementation, 2026-09-07)**: T002/T003 could not be dispatched at all, so per this task's own fallback, that fact is recorded as a dated "T006 determination" paragraph in research.md's "Blocking prerequisite for `tasks.md`" section. Phases 3, 5, 7 (and everything depending on them: 4, 6, 8, 9) are not executed this pass.

**Checkpoint**: Foundational phase complete only once T006's determination paragraph exists in research.md. The rest of this document assumes Outcome 1 as the primary path (T007–T019), with T020/T021 as the explicit Outcome-2/Outcome-3 substitutes.

---

## Phase 3: User Story 1 - Pull a private image from every job, on hosted runners (Priority: P1) 🎯 MVP

**Goal**: Every job of every published stage that already carries `container.image` gains a `credentials:` sibling that is present-but-inert when the adopter supplies no (or one) credential, and real when both are supplied — so a private image is pullable by every job, not just `verify-image-prerequisites`.

**Independent Test**: In a scratch adopter repository on GitHub-hosted runners, name a private image, supply both secrets, run a stage, and observe every job start inside the image and the stage complete.

**Depends on**: Phase 2 (T006) recording Outcome 1 (T007–T019 below) — if Outcome 2, substitute T020 for T007–T018's expression; if Outcome 3, execute only T021 and skip the rest of this phase.

### Per-file credential binding (Outcome 1 — the preferred path)

Each task below amends every job in the named file that already carries `container: { image: ${{ inputs.container-image }} }` **except** `verify-image-prerequisites` (which is exempt from `container:` entirely, per Gate 22's existing carve-out — it invokes Docker directly on the runner). Add the exact expression from `contracts/private-registry-credentials.md`'s "Binding mechanism" section as the `credentials:` sibling of `image:` in each such job's `container:` block, byte-for-byte identical across every job and every file (Gate 22, amended in T032, will check this):

```yaml
credentials: >-
  ${{
    (secrets.container-registry-username != '' && secrets.container-registry-password != '')
      && fromJSON(format('{{"username":{0},"password":{1}}}', toJSON(secrets.container-registry-username), toJSON(secrets.container-registry-password)))
      || fromJSON('{}')
  }}
```

Where the exact job list wasn't fully enumerated by prior research, run `grep -n -B8 'image:[[:space:]]*\${{[[:space:]]*inputs\.container-image' <file>` first to find every job id, then edit each one.

- [ ] T007 [P] [US1] Amend `.github/workflows/intake.yml` — jobs `intake` and its second container-bearing job (verify via the grep above; expected count 2, excluding `verify-image-prerequisites`).
- [ ] T008 [P] [US1] Amend `.github/workflows/clarify.yml` — 2 jobs (verify via grep).
- [ ] T009 [P] [US1] Amend `.github/workflows/plan.yml` — jobs `resolve-spec` and `plan`.
- [ ] T010 [P] [US1] Amend `.github/workflows/tasks.yml` — 5 jobs including `resolve-spec`, `tasks`, `tasks-approved` (verify the remaining 2 via grep).
- [ ] T011 [P] [US1] Amend `.github/workflows/implement.yml` — 2 jobs (verify via grep).
- [ ] T012 [P] [US1] Amend `.github/workflows/finalize.yml` — 2 jobs (verify via grep).
- [ ] T013 [P] [US1] Amend `.github/workflows/cleanup.yml` — jobs `select`, `teardown-done`, `teardown-rejected`, `mark-stalled`.
- [ ] T014 [P] [US1] Amend `.github/workflows/watchdog.yml` — jobs `collect`, `diagnose`, `triage` (matrix), `act` (matrix), `report-unhandled-failure`.
- [ ] T015 [P] [US1] Amend `.github/workflows/pr-conversation.yml` — 5 jobs including `classify-and-announce`, `act` (matrix) (verify the remaining 3 via grep).
- [ ] T016 [P] [US1] Amend `.github/workflows/rebase.yml` — jobs `discover`, `rebase` (matrix).
- [ ] T017 [P] [US1] Amend `.github/workflows/auto-update-spec-kit.yml` — jobs `health-check`, `detect`, `settle`, `evaluate-path`, `prepare`, `e2e-stage`, `verify`, `act`, `pr-merged`, `comment-reply` (10 jobs).
- [ ] T018 [P] [US1] Amend `.github/workflows/metrics-persist.yml` — job `persist`.

### verify-image-prerequisites messaging (all 12 files, all outcomes 1/2)

- [ ] T019 [US1] Across all 12 stage files (intake, clarify, plan, tasks, implement, finalize, cleanup, watchdog, pr-conversation, rebase, auto-update-spec-kit, metrics-persist), in the `verify-image-prerequisites` job: (a) remove the `::warning::wing-commander verify-image-prerequisites: registry credentials were supplied. They authenticate this check only...` line (FR-015) — note `metrics-persist.yml`'s copy is missing the `(#227)` citation the other 11 carry; removing it entirely makes that drift moot, no separate fix needed; (b) sharpen the "exactly one credential supplied" branch of the `docker pull` failure handler (currently folded into the generic pull-failure `if/elif` chain, e.g. `intake.yml:271-282`) so its existing per-case messages ("container-registry-username was not supplied...", "...password was not supplied...") remain — these already name the missing secret correctly per FR-007; confirm no file's chain regressed to a generic message during (a)'s edit.

### Outcome-2 substitute (only if T006 recorded Outcome 2)

- [ ] T020 [US1] Instead of T007–T018's literal expression: add one new `workflow_call` input, `container-registry-authenticated` (`type: string`, `default: "false"`), to all 12 stage files' `on.workflow_call.inputs` blocks. On every job identified in T007–T018, replace the whole `container:` value with an expression selecting between today's bare form (`container: ${{ inputs.container-image }}`-shaped, no `credentials` key) when the input is `"false"`, and an object-literal form carrying the `credentials:` expression above when it is `"true"` — finalize the exact expression using whichever whole-value-context answer T004/T006 recorded for research D3's "Decision tree" item 2, since research.md explicitly declined to pre-finalize it before that answer exists. Apply T019 as written regardless.

### Outcome-3 substitute (only if T006 recorded Outcome 3)

- [ ] T021 [US1] Do not edit any stage file's `container:` block. Instead, in all 12 files' `verify-image-prerequisites` job, update (not remove) the `::warning::` line to cite this feature's own recorded probe evidence (T004) instead of `#227`, stating that per-job credential reach was measured and found not possible for the reason T004 recorded. Skip T007–T020 and Phase 5 (US3) entirely; proceed to Phase 8 using the Outcome-3 framing.

**Checkpoint**: Every job of every published stage now carries the uniform binding (or, under Outcome 3, an updated but unchanged-shape warning) — User Story 1 is independently testable in a scratch adopter repository.

---

## Phase 4: User Story 2 - All three shapes keep working from one set of stage files (Priority: P1)

**Goal**: Confirm the same edits from Phase 3 leave the no-image and public-image defaults behaviorally identical to the previous release — this story adds no new code, only validation, because FR-005/FR-006 are satisfied by the same `{}`-resolving expression Phase 3 already ships.

**Independent Test**: Run a stage three times from the same stage files — no image; a public image with no credentials; a private image with credentials — and confirm each behaves per its contract.

**Depends on**: Phase 3 complete (or, under Outcome 3, skipped with T021's fallback applied — in that case this phase's tests still apply, since the no-image/public-image contract is unchanged either way).

- [ ] T022 [US2] Validate quickstart.md Scenario 1 (default path, no image, no secrets) in a scratch adopter repository: confirm no container, no login attempt, no new failure/warning/artifact versus the pre-044 release.
- [ ] T023 [US2] Validate quickstart.md Scenario 2 (public image, no credentials): confirm every job runs inside the image with no authentication attempted.
- [ ] T024 [US2] Validate quickstart.md Scenario 3 (credentials supplied, no image named): confirm total inertness — no login, no warning, no behavior change.
- [ ] T025 [US2] Confirm exactly one set of published stage files exists post-edit (no per-shape variant, no duplicated stage, no fork) — `git diff --stat` against the pre-Phase-3 tree should show only the 12 existing files (plus, under Outcome 2, no new files — only new input lines) modified, never a new `*-private.yml` or similar sibling.

**Checkpoint**: User Stories 1 and 2 both independently verified.

---

## Phase 5: User Story 3 - Hand in a credential my registry mints at run time (Priority: P1)

**Goal**: Ship the optional, edge-located `wing-commander-ecr-credentials` composite action and its worked example, so an adopter whose registry issues short-lived tokens (AWS ECR) can mint one in their own wrapper and hand it to a stage.

**Independent Test**: In a scratch adopter repository, mint a token via a cloud role, pass it into the stage call, and confirm the stage pulls the private image with the token masked throughout.

**Depends on**: Phase 2's T005 confirming the masked cross-job hand-off is safe (P2). **Do not execute this phase if T005 recorded a leak, or if T006 recorded Outcome 3** — use T029 instead.

- [ ] T026 [US3] Create `.github/actions/wing-commander-ecr-credentials/action.yml` exactly per research D8's specification: `inputs` (`aws-role-arn` required, `aws-region` required, `registry` optional default `""`), `outputs` (`username` fixed `"AWS"`, `password` masked), `runs: using: composite` with one `aws-actions/configure-aws-credentials@v4` step followed by an `id: mint` shell step that runs `aws ecr get-login-password`, applies `::add-mask::` to the password **before** writing it to `$GITHUB_OUTPUT`, then writes both outputs. Follow `.github/actions/wing-commander-bedrock-credentials/action.yml`'s header-comment and self-checkout conventions.
- [ ] T027 [US3] Confirm the new composite action satisfies this repository's existing composite-action description gate (the one FR-022 references as covering "the composite-action description rules") — locate it in `lint-workflows.yml` (search for the gate checking `.github/actions/**/action.yml` `description:` fields) and run it locally against the new file; no code change expected if T026's description matches the required shape, verification only.
- [ ] T028 [US3] Author the full copy-pasteable ECR wrapper worked example (two jobs: `mint-ecr-credentials` with `permissions: id-token: write, contents: read`, using `wing-commander-ecr-credentials`; a sibling job `needs: mint-ecr-credentials` calling a stage with `secrets: container-registry-username/password: ${{ needs.mint-ecr-credentials.outputs.* }}`) exactly as shown in `contracts/private-registry-credentials.md`'s "cross-job masked hand-off" section — this becomes the content T038 places into `docs/adoption.md`.
- [ ] T029 [US3] [Conditional] If T005 (P2) recorded a masking leak, or T006 recorded Outcome 3: do not execute T026–T028. Instead record in research.md D4 that `wing-commander-ecr-credentials` does not ship this pass, name the measured leak location, and note that FR-013 remains open pending a different hand-off shape and a re-probe.

**Checkpoint**: The ECR component and its worked example exist (or are explicitly deferred with a recorded reason) — User Story 3 is independently testable.

---

## Phase 6: User Story 4 - Registry-agnostic core, provider help at the edge (Priority: P2)

**Goal**: Confirm no provider name, region, role, or registry-specific input leaked into any published stage file, and that a no-adapter registry (static pair or repository-scoped token) needs zero extra components.

**Independent Test**: Read the published stage files and confirm no provider-specific string appears in any of them; complete a private-image run against a registry needing no adapter.

**Depends on**: Phase 3 (or its Outcome-3 fallback) complete.

- [ ] T030 [US4] Grep all 12 published stage files plus the amended `lint-workflows.yml` Gate 22 section for any provider-specific string (`ecr`, `aws`, `gcr`, `acr`, `dkr.ecr`, case-insensitive) outside of comments citing this feature's own issue/PR numbers; confirm zero matches inside actual job/expression bodies (FR-009). Record the grep command and its empty result.
- [ ] T031 [US4] Validate quickstart.md Scenario 7 (repository-scoped-token worked example, once T039 documents it): confirm a reader following the documentation alone reaches a working private-image run using only the two existing secrets, no adapter, no extra wrapper job.

**Checkpoint**: Registry-agnostic constraint verified as still holding after Phase 3's edits.

---

## Phase 7: User Story 6 - The uniformity checks are amended, not bypassed (Priority: P3)

**Goal**: Gate 22 stops forbidding `credentials:` outright and instead requires it match the exact new expression, with its self-test extended to cover every new failure branch and a registered exception for `verify-image-prerequisites`.

**Independent Test**: Introduce a stage job that omits the credential binding and confirm the pipeline's own PR checks fail naming the stage file and job; restore it and confirm they pass.

**Depends on**: Phase 3 (or T021's Outcome-3 fallback) complete, since Gate 22 must check whatever shape actually shipped.

- [ ] T032 [US6] Amend Gate 22's step in `.github/workflows/lint-workflows.yml` (currently hard-failing at the `if "credentials" in container:` check, ~lines 1961–1973, citing #227): replace the hard failure with a check that every job's `container.credentials` value matches, byte-for-byte, the exact expression from T007–T018 (or T020's Outcome-2 shape, whichever shipped) — mirroring how the existing `image:` check already does an exact match. Under Outcome 3 (T021), leave Gate 22 unchanged (it still correctly forbids `credentials:`, since none was added).
- [ ] T033 [US6] Add a registered exception-table entry (FR-021) to Gate 22's exception data for `verify-image-prerequisites`, naming the reason: it must invoke Docker directly on the runner and is therefore exempt from the `container:` binding entirely — mirroring Gate 7's existing `pr-conversation.act` exception pattern.
- [ ] T034 [US6] Extend `.github/scripts/verify-gate-22.py`'s `CASES` list with one new fixture per new failure branch T032 introduces (FR-020): (a) the pre-044 bare `image:`-only shape must now fail (previously the required/healthy shape); (b) the pre-#227 raw-secrets shape (`credentials: { username: secrets.x, password: secrets.y }` unconditional) must still fail; (c) a `credentials:` value present but not byte-identical to the required expression (drift) must fail; (d) **only if Outcome 2 shipped**, a job whose `container-registry-authenticated`-gated expression is mismatched must fail.
- [ ] T035 [US6] Run `verify-gate-22.py`'s `check_derivations_agree` and `check_real_fleet` checks against the real, now-amended repository to confirm Gate 22 passes on all 12 real stage files (13, once T044 ships) with no fixture regressions.
- [ ] T036 [US6] Manually execute Story 6's acceptance scenario 1 against a scratch copy: introduce a job that carries `container.image` but omits (or mismatches) `credentials:`; confirm Gate 22 fails naming that exact stage file and job id; restore it and confirm Gate 22 passes again.

**Checkpoint**: Gate 22 protects the new shape the same way it protected the old one — User Story 6 independently verified.

---

## Phase 8: User Story 7 - Documentation says what is now possible (Priority: P3)

**Goal**: Adoption/setup documentation states the new reach, presents the pre-authenticated-runner path as a fallback (not the only option), and carries both required worked examples; the stage-interfaces contract gains the credential-secret rows it never had.

**Independent Test**: A reader following the adoption documentation alone reaches a working private-image run for both worked examples, and finds no surviving claim that credentials reach only the prerequisite check.

**Depends on**: T006's outcome determination (framing differs under Outcome 3), T028 (ECR example content, if Phase 5 ran).

- [ ] T037 [US7] Rewrite `docs/adoption.md` lines ~876–889 (currently "**These credentials reach the prerequisite check and nothing else, today.**" through "...A public (or otherwise unauthenticated) image needs nothing."): under Outcome 1/2, state credentials now reach every job of the stage, and present the pre-authenticated-runner guidance as the documented fallback specifically for registries that cannot present a username/password pair (FR-023) — not as the only option. Under Outcome 3 (T021 applied), instead state the limitation was measured and found to still hold, citing this feature's own recorded evidence (T004) rather than #227's.
- [ ] T038 [US7] Add T028's ECR worked example verbatim to `docs/adoption.md`, in the same section as T037's rewrite, as a complete copy-pasteable block (skip this task entirely if Phase 5 was skipped per T029).
- [ ] T039 [US7] Add the repository-scoped-token worked example to `docs/adoption.md` (research D9 shape: `container-image: ghcr.io/${{ github.repository_owner }}/<private-package>:latest`, `container-registry-username: ${{ github.actor }}`, `container-registry-password: ${{ secrets.GITHUB_TOKEN }}`), with an explicit note that the calling wrapper job needs `packages: read` in its own `permissions:` block.
- [ ] T040 [US7] Add the credential-lifetime statement (FR-024) to `docs/adoption.md` (near the rewritten section from T037): each stage call carries the credential it was given, the pipeline never refreshes or renews one, and a credential that expires before a queued job starts surfaces as a plain pull failure.
- [ ] T041 [US7] [Conditional: Outcome 2 only] Document the new `container-registry-authenticated` opt-in input in `docs/setup.md`, alongside this repository's other opt-in-input documentation (e.g. `use-bedrock`'s existing entry, for a consistent format).
- [ ] T042 [US7] Add new rows to `specs/010-reusable-pipeline/contracts/stage-interfaces.md`'s secrets/common-inputs tables for `container-registry-username` and `container-registry-password` — these rows do not exist there today (confirmed absent from both the "Secrets" table at lines 9–16 and the "Common inputs" table at lines 20–37), despite `contracts/private-registry-credentials.md` describing itself as amending them. Use description text consistent with T037's rewrite (reach: every job, not only the prerequisite check, under Outcome 1/2; or the Outcome-3 framing otherwise) and the existing `container-image` row's style (line 33) as a template.
- [ ] T043 [US7] Grep `docs/`, `.github/`, and all workflow file comments for any remaining phrase claiming credentials "reach...nothing else" or "authenticate this check only"; confirm zero survive outside of historical citations to `#227`/PR #226 kept for context (SC-009). This includes double-checking `metrics-persist.yml`'s slightly-different (uncredited) copy of the warning was fully removed by T019, not merely edited.

**Checkpoint**: Documentation matches the shipped mechanism exactly — User Story 7 independently verified.

---

## Phase 9: This repository's own dogfood check (FR-027, SC-010)

**Purpose**: Cross-cutting, not owned by a single user story — demonstrates the shipped mechanism on this repository's own infrastructure, on a recurring schedule, using no cloud account or cloud-registry identity, following the `auto-update-spec-kit.yml` stage-plus-wrapper precedent. Skip this phase entirely under Outcome 3 (there is nothing to dogfood).

- [ ] T044 Create a new `workflow_call`-only stage file, `.github/workflows/private-image-dogfood.yml`, with one job that carries `container: { image: ${{ inputs.container-image }}, credentials: <the same expression from T007–T018> }` and a trivial verification step (e.g. `cat /etc/os-release` or similar, just enough to prove the container actually started). This file will be swept into Gate 6/7/22's structurally-derived published-stage set automatically — that is intended, not a bug, since FR-027 requires the dogfood check use "the same stage-file shape adopters use."
- [ ] T045 Create the wrapper `.github/workflows/wing-commander-private-image-dogfood.yml`, mirroring `wing-commander-auto-update-spec-kit.yml`'s `on: schedule: / workflow_dispatch: {}` trigger block, calling `private-image-dogfood.yml` with `container-image: ghcr.io/${{ github.repository_owner }}/wing-commander-dogfood:latest`, `secrets: container-registry-username: ${{ github.actor }}, container-registry-password: ${{ secrets.GITHUB_TOKEN }}`, and `permissions: packages: read` on the calling job.
- [ ] T046 Add a step (in the same wrapper, gated to run before the pull, or in a small one-time setup job) that builds a minimal single-file image and pushes it to `ghcr.io/<owner>/wing-commander-dogfood` using `secrets.GITHUB_TOKEN` with `packages: write`. **Explicitly set the package's visibility to private** (via `gh api`/package settings) and verify it — this repository is public, and a package pushed without an explicit private setting can default to public, which would silently defeat the entire point of the dogfood check (it must exercise real private-registry authentication).
- [ ] T047 Run the full local gate suite (`python .github/scripts/run-local-gates.py`) after T044–T046 land, to confirm the new stage/wrapper pair is automatically covered by Gate 6/7/22 with no manual registration, and that Gate 22's uniform-binding check passes on it exactly as it does on the other 12 stages.
- [ ] T048 Trigger `wing-commander-private-image-dogfood.yml` on demand (`workflow_dispatch`) once; confirm the run pulls the private package successfully and the job completes (quickstart.md Scenario 9). Confirm the `on.schedule` block is present and correctly formed (a first real scheduled run cannot be observed same-day, so this step only verifies configuration, not a historical scheduled execution).

**Checkpoint**: This repository dogfoods the exact mechanism it ships to adopters, on a recurring schedule, with no cloud dependency.

---

## Phase 10: Polish & Cross-Cutting Concerns

**Purpose**: Final repository-wide checks that span every phase above.

- [ ] T049 Run `python .github/scripts/run-local-gates.py` (the full PR-time gate suite, per `CLAUDE.md`) and fix any failure before this feature's work is committed on the implementation branch.
- [ ] T050 Since this feature touches many `if:`-shaped conditional expressions (the `credentials:` expression's `&&`/`||` chain) and a gate's own `if:` logic (Gate 22's amendment in T032), run the `review-step-gating` skill over the diff per `CLAUDE.md`'s explicit rule for any change touching a workflow `if:`.
- [ ] T051 Update `contracts/private-registry-credentials.md`'s "provisional pending research D3/D4" framing (its opening paragraph and every section marked "contingent on P1/P2") to state the final, now-recorded outcome, striking the provisional language once T004–T006 have resolved it.
- [ ] T052 Walk spec.md's Success Criteria (SC-001 through SC-010) one by one against the tasks above and confirm each has a corresponding executed task or scenario; for any SC that cannot be satisfied under the outcome T006 recorded (e.g. SC-004/SC-001 under Outcome 3), note explicitly in research.md which SC is unmet and why, rather than leaving it silently unaddressed.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies.
- **Foundational (Phase 2)**: Depends on Setup. **Blocks every other phase** — this is stronger than the template's usual "blocks user stories" because FR-016 makes it a hard, spec-mandated gate, not just a convenience ordering.
- **User Story 1 (Phase 3)**: Depends on Phase 2's T006 outcome determination.
- **User Story 2 (Phase 4)**: Depends on Phase 3 (validates its output; adds no new files).
- **User Story 3 (Phase 5)**: Depends on Phase 2's T005 (P2 masking result) specifically, not just T006 — can in principle proceed even if Phase 3 used the Outcome-2 shape, but not at all under Outcome 3.
- **User Story 4 (Phase 6)**: Depends on Phase 3 (greps its output).
- **User Story 6 (Phase 7)**: Depends on Phase 3 (Gate 22 must check whatever shape shipped).
- **User Story 7 (Phase 8)**: Depends on Phase 3's outcome (framing) and Phase 5's T028 (content, if it ran).
- **Dogfood (Phase 9)**: Depends on Phase 3 shipping Outcome 1 or 2 (there is nothing to dogfood under Outcome 3).
- **Polish (Phase 10)**: Depends on all executed phases above.

### Within Phase 3

T007–T018 are mutually independent (different files) and can run in parallel. T019 touches all 12 files and should run after T007–T018 to avoid merge noise in the same job blocks, though it edits a different job (`verify-image-prerequisites`) so a real conflict is unlikely. T020 and T021 are mutually exclusive substitutes for T007–T019, chosen by T006's recorded outcome, not run alongside them.

### Parallel Opportunities

- All of T007–T018 (12 files, Phase 3) in parallel.
- T022–T025 (Phase 4 validation) in parallel with each other once Phase 3 is complete.
- T030–T031 (Phase 6) in parallel with Phase 7's T032–T036, since they touch disjoint files.
- T037–T042 (Phase 8 documentation) in parallel with each other; T043 (repo-wide grep) last, after the others land.

---

## Parallel Example: Phase 3 per-file credential binding

```bash
# After Phase 2 (T006) records Outcome 1, launch all 12 file edits together:
Task: "Amend .github/workflows/intake.yml per T007"
Task: "Amend .github/workflows/clarify.yml per T008"
Task: "Amend .github/workflows/plan.yml per T009"
Task: "Amend .github/workflows/tasks.yml per T010"
Task: "Amend .github/workflows/implement.yml per T011"
Task: "Amend .github/workflows/finalize.yml per T012"
Task: "Amend .github/workflows/cleanup.yml per T013"
Task: "Amend .github/workflows/watchdog.yml per T014"
Task: "Amend .github/workflows/pr-conversation.yml per T015"
Task: "Amend .github/workflows/rebase.yml per T016"
Task: "Amend .github/workflows/auto-update-spec-kit.yml per T017"
Task: "Amend .github/workflows/metrics-persist.yml per T018"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1 (Setup) and Phase 2 (Foundational — the two blocking probes; this is the step this planning pass could not itself execute).
2. Complete Phase 3 (User Story 1) per whichever outcome T006 recorded.
3. **STOP and VALIDATE**: run Phase 4's scenarios in a scratch adopter repository.
4. This alone (Phases 1–4) is the MVP: private-image reach, with the no-image/public-image defaults proven unchanged.

### Incremental Delivery

1. Phases 1–4 → MVP (private-image reach, all three shapes from one file set).
2. Phase 5 → cloud-registry (ECR) minted-credential support, gated on P2's masking proof.
3. Phase 6 → registry-agnostic-core verification (no new capability, a constraint check).
4. Phase 7 → Gate 22 amendment, so the new shape is protected the same way the old one was.
5. Phase 8 → documentation catches up to what Phases 3–7 shipped.
6. Phase 9 → this repository dogfoods its own capability on a recurring schedule.
7. Phase 10 → final cross-cutting gate run and SC checklist sweep.

### Notes

- Outcome 2 and Outcome 3 are not deferred work — they are the two alternate endings this feature was designed to have from the start (FR-026). Whichever one T006 records, the corresponding substitute tasks (T020/T021, T029, T041) are the complete path to a shippable state; none of them represents an unfinished feature.
- Every per-file task in Phase 3 is a mechanical, byte-for-byte-identical edit (the same expression, added to every qualifying job) — the duplication is required by GitHub's own per-job `container:` schema (there is no composite-action indirection available for a job-level key), not a violation of `CLAUDE.md`'s "shared logic has exactly one home" rule, which governs shared `run:`/jq/shell logic, not required per-job YAML repetition Gate 22 already enforces byte-for-byte.
