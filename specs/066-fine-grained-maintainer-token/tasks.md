---

description: "Task list for feature 066: Fine-grained maintainer token for the auto-release end-to-end harness"
---

# Tasks: Fine-grained maintainer token for the auto-release end-to-end harness

**Input**: Design documents from `/specs/066-fine-grained-maintainer-token/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md (all present)

**Tests**: Not explicitly requested as TDD, but FR-015 and Constitution VIII make fixture-plus-mutation coverage mandatory for every new precheck branch and for the new canonical-statement gate — those tasks are folded into Foundational and the user-story phases below as the feature's own acceptance mechanism, not a separate opt-in pass.

**Organization**: Tasks are grouped by user story (spec.md priorities P1/P1/P2/P2). Shape detection (D1) and the malformed-shape branch, and the `gh api` exit-status fix that both shapes' containment check now needs (D4), are pulled into Foundational because every later story's own scenarios call through them. The rest of the fine-grained-branch implementation (D2/D5/D6 probes) sits in User Story 1, whose happy path is the first thing that needs it to exist; User Story 2 then adds the failure-side fixture/mutation coverage for those same branches. See Dependencies & Execution Order below.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1-US4)
- Line numbers cited below are today's (`ce9f3a9`) positions in `.github/workflows/auto-release.yml` and `.github/workflows/lint-workflows.yml`, taken from a direct read of those files during task generation; locate sites by the step/gate name in quotes once a prior task in the same phase has landed, since each edit shifts later line numbers in the same file.

## Path Conventions

CI/CD pipeline infrastructure repository — no `src`/`tests` split. Paths below are repository-root-relative (`.github/`, `docs/`, `specs/`), per plan.md's Project Structure. No published stage workflow (`.github/workflows/{intake,clarify,plan,tasks,implement,converge,finalize,cleanup,watchdog}.yml`) is touched by any task below (FR-021).

---

## Phase 1: Setup

**Purpose**: Confirm the baseline this feature edits against, before any file changes.

- [X] T001 Confirm today's line anchors for the sites this feature touches: the "Confirm the fixture maintainer identity's credential" step's comment block and body in `.github/workflows/auto-release.yml` (comment ~lines 287-299, step body ~lines 300-413, containment read at ~line 388, containment failure verdict at ~line 402); Gate 67's registration in `.github/workflows/lint-workflows.yml` (~lines 3658-3669); the next free gate number (Gate 98 is the highest registered as of this commit, so the new canonical-statement gate below is Gate 99 unless another feature lands first — recheck before registering); `docs/setup.md` §2's `WING_COMMANDER_AUTO_RELEASE_E2E_MAINTAINER_TOKEN` row (~line 59) and §3 (~line 89); and `specs/055-unattended-e2e-gates/research.md`'s D1 (~line 13) and D2 (~line 62) headings and `spec.md`'s Clarifications session (~line 539). Record any drift from these citations in the PR description rather than in a spec file. No file changes.

**Checkpoint**: Baseline confirmed; Foundational work can begin.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The shape-detection branch every later check depends on, and the one correctness fix (D4) that applies to both shapes' containment check regardless of which user story exercises it.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T002 In `.github/workflows/auto-release.yml`'s "Confirm the fixture maintainer identity's credential" step, after the existing `MAINTAINER_TOKEN`/`MAINTAINER_USERNAME` unset checks (~lines 319-338) and before the existing `viewerPermission` check (~line 339), add shape classification per research.md D1: match `MAINTAINER_TOKEN` against the literal prefixes `ghp_` (classic) and `github_pat_` (fine-grained) using a plain shell case/pattern match — no network call. A value matching neither prefix must call `bash .github/actions/_shared/auto-release-verdict.sh "fail-infra" "$HEAD_SHA" "fixture maintainer identity credential" "a value matching the classic (ghp_) or fine-grained (github_pat_) token prefix" "matches neither accepted shape" "WING_COMMANDER_AUTO_RELEASE_E2E_MAINTAINER_TOKEN" "$MODE"` (data-model.md table row #0) and `exit 0`. This is a new branch, never a collapse into any of FR-008's other five (now six) named failures.
- [X] T003 Restructure the remainder of the same step into two mutually exclusive branches keyed on T002's `shape` value, per contracts/credential-precheck.md's decision-order table (step 5 = classic, step 6 = fine-grained): move the existing `viewerPermission`, `gh api user` login, and case-insensitive comparison checks (~lines 339-377) unmodified under `if [ "$shape" = "classic" ]`, so the classic path stays byte-identical to today's behavior (contracts/credential-precheck.md: "every following check is BYTE-IDENTICAL to specs/055 D2/today's step"). Leave the containment read (~line 388) and its failure verdict (~line 402) shared by both branches, per T004 below — do not duplicate it into each branch.
- [X] T004 Fix the containment check's `gh api` exit-status swallow (research.md D4): capture the exit status of `gh api "user/repos?affiliation=owner,collaborator,organization_member" --paginate --jq '.full_name'` (~line 388) separately from its output, instead of the current `2>/dev/null` swallow into `sort -u`. A non-zero exit from that call must produce its own `fail-infra` verdict via `auto-release-verdict.sh` with `expected` "the credential's reachable-repository set can be observed" and `observed` naming that the call itself failed (data-model.md table row #6) — distinguishable from the existing "reached 0 repositories" text (table row #7), which remains reserved for a call that succeeds and returns an empty set. This fix applies to both shapes, since both branches reach this same containment read.
- [X] T005 Update the comment block above the step (`.github/workflows/auto-release.yml` ~lines 287-299) to describe the shape-detection branch this phase adds (both accepted shapes, dual acceptance during the transition per FR-003) without restating the credential's own scope/permissions/expiry in prose — that restatement is Phase 5's job (FR-017). Point the comment at `docs/setup.md` (`-- see docs/setup.md`) for the canonical statement instead.

**Checkpoint**: shape detection and the shared containment fix are in place; the classic path is provably unchanged; user story work can begin.

---

## Phase 3: User Story 1 - The harness authenticates with a repository-scoped credential (Priority: P1) 🎯 MVP

**Goal**: A fine-grained credential scoped to the test repository alone, with only the harness's permissions, authenticates the fixture maintainer identity and drives all four gates unchanged.

**Independent Test**: Transfer the fixture to the machine account, issue the credential, set the secret and the test-repository variable and the App installation that follow the move, dispatch one auto-release verification attempt, and observe the credential precheck passing and all four gates driven to a terminal verdict.

### Implementation for User Story 1

- [X] T006 [US1] In the fine-grained branch (`if [ "$shape" = "fine-grained" ]`, contracts/credential-precheck.md step 6a-b) of the same step, call `GH_TOKEN="$MAINTAINER_TOKEN" gh api user --jq .login`; a transport failure on this or any probe call below produces the same "rejected/expired credential" `fail-infra` verdict as the classic branch's `viewerPermission` failure (data-model.md table row #2). Compare the resolved login against `MAINTAINER_USERNAME` case-insensitively, whitespace-stripped, exactly as the classic branch does (table row #3) — this is a reachability/authentication check only for this shape, per research.md D6: never treat `viewerPermission` as a permission proof here, since ownership makes the account (not the token) report ADMIN by construction.
- [X] T007 [US1] Add the D6 write-permission probes to the fine-grained branch (contracts/credential-precheck.md step 6c): `POST /repos/{owner}/{repo}/issues/999999999/comments` for Issues:write, and one Pull-requests:write-gated call against the same certainly-nonexistent id (a merge attempt, review-request, or label edit against issue/PR `999999999` — any one satisfying contracts/credential-precheck.md's "read-side-effect-free, 403-before-404" requirement) for Pull-requests:write. A `403` on either means the permission is absent and must fail with `expected` "Issues and Pull-requests write, per research.md D6" (data-model.md table row #4); a `404` means the permission is present and the resource lookup failed as expected, i.e. this probe passed.
- [X] T008 [US1] Add the D5 Administration-absence probe to the fine-grained branch (contracts/credential-precheck.md step 6d): `GET /repos/{owner}/{repo}/collaborators`. A `200` response means the token grants Administration and must fail with `expected` "no Administration permission on the test repository" (data-model.md table row #5, FR-016) — distinguishable from every other branch, and never produced for the classic shape (FR-003's stated asymmetry). A `403` naming the missing permission means this probe passed.
- [X] T009 [US1] Add the D2 expiry read to the fine-grained branch (contracts/credential-precheck.md step 6f): read the `github-authentication-token-expiration` response header from the `gh api user` call in T006 (reuse that call's response; do not add a second one). Add a new repository variable `WING_COMMANDER_AUTO_RELEASE_E2E_MAINTAINER_TOKEN_EXPIRY_WARNING_DAYS`, read into the step's `env` block, defaulting to `14` when unset (research.md D2). If the header is present and its timestamp is already past "now", fail with the same "rejected/expired credential" verdict as table row #2. If present and within `now + <warning days>`, proceed to `ok=true` and additionally emit a step output (e.g. `expiry-warning=<date>`) that the `report` job can surface in its summary — a report-only note, not a new verdict field (data-model.md, "Approaching expiry ... is not a failure branch"). Absent header (classic shape, or a fine-grained token GitHub did not attach the header to) proceeds exactly as today — not an error.
- [X] T010 [US1] Route the fine-grained branch's containment check through the same shared read T004 fixed (contracts/credential-precheck.md step 6e) — do not add a second containment implementation; confirm by inspection that both branches call the identical shell block.
- [X] T011 [US1] Update `docs/setup.md` §2's `WING_COMMANDER_AUTO_RELEASE_E2E_MAINTAINER_TOKEN` row (~line 59) to become the canonical statement of content (FR-002, FR-006, FR-020; the *pointer mechanism* enforcing this as the single home is Phase 5's job, not this task): state dual acceptance during the transition (classic and fine-grained, FR-003); for the fine-grained shape, the required scope (the test repository alone), permissions (Contents read; Issues read/write; Pull requests read/write; explicitly no Administration), mandatory expiry, and the rotation procedure (replace the secret; no workflow change, SC-003); the Administration bound on the *credential* versus the *account's* ownership-conferred Admin (FR-016); and the two ownership options not taken (leave the fixture where it is; move it under an organization) with the one-sentence reason for each (FR-020, research.md Clarifications Q1). Add a `docs/setup.md` §3 row (~line 89) for `WING_COMMANDER_AUTO_RELEASE_E2E_MAINTAINER_TOKEN_EXPIRY_WARNING_DAYS` (T009), stating its default of 14 days.
- [ ] T012 [US1] Run quickstart.md's Prerequisites and Scenario 1: complete the one-time repository transfer and its fallout (variable, App reinstall, Claude secret, container-image variable, `spec-request` label — research.md D8), issue the fine-grained token per T011's documented shape, dispatch `auto-release.yml`, and confirm the credential step reports `ok=true` with no verdict output and the run proceeds through all four gates exactly as specs/055's own Scenario 1 describes (User Story 1's Independent Test; SC-001, SC-006). Record the run's evidence (URL and head SHA) on the PR or on issue #506 (FR-022).

**Checkpoint**: a correctly scoped fine-grained credential passes the precheck and drives a live attempt to a terminal verdict; User Story 1 is independently functional and testable.

---

## Phase 4: User Story 2 - A wrong or expired credential is named before any spend (Priority: P1)

**Goal**: Every way the new credential shape can be misconfigured is detected before the attempt starts a lifecycle it cannot finish, and reported as a named, distinguishable infrastructure outcome.

**Independent Test**: Run the credential precheck against each misconfiguration in turn (no network needed) and assert every one ends the attempt with an infrastructure verdict that names what to fix and never quotes the credential.

### Implementation for User Story 2

- [X] T013 [US2] Extend `.github/scripts/verify-auto-release-credential-step.py` (Gate 67)'s `SCENARIOS` with fine-grained-shape cases for every row of data-model.md's Credential precheck outcome table not already covered by the existing classic-shape scenarios: row #0 (malformed prefix, T002), row #2 fine-grained variants (a probe call transport-failing outright, and an already-expired token per T009's header), row #4 fine-grained variant (T007's D6 probe rejected for Issues and/or Pull-requests write), and row #5 (T008's D5 probe accepted — grants Administration). Each scenario stubs `gh`/`gh api` to return the fixed response codes contracts/credential-precheck.md's probe table specifies (200/403 for D5, 404/403 for D6), matching Gate 67's existing "no network call, ever" property.
- [X] T014 [US2] Add a scenario asserting the approaching-expiry note (T009) is present on a `pass` outcome when the stubbed `github-authentication-token-expiration` header falls within the warning window, and absent when it is well outside it or missing (classic shape) — this is report-only text, not a verdict field, per data-model.md.
- [X] T015 [US2] Add a scenario asserting FR-009: for every new fail-infra branch added in this feature (T002, T006-T009), no verdict, step output, or log line contains the raw `MAINTAINER_TOKEN` value or the unredacted `MAINTAINER_USERNAME`/resolved login — extend Gate 67's existing masked-login assertion (the one its own docstring already describes for the containment branch) to cover the new branches too.
- [X] T016 [US2] Add mutations to Gate 67 for each new scenario in T013-T015, following the existing `mut_raw_repository_names`/`mut_no_username_guard` pattern (~lines 191-205): one mutation per new failure branch that would make it silently pass (e.g. accepting a malformed prefix, treating a D5 200 as a pass, treating a D6 403 as a pass, dropping the expiry check), each proven to break at least one scenario's assertion (FR-015, Constitution VIII).
- [X] T017 [US2] Run `.github/scripts/verify-auto-release-credential-step.py` (Gate 67) locally and confirm it exercises, and separately distinguishes, every row of the outcome table and every mutation added above (quickstart.md Scenario 2; SC-002 — zero of these reach a live dispatch).

**Checkpoint**: every misconfiguration of the fine-grained shape is caught before any gate-driving spend, with a distinguishable verdict and no credential or login leakage; User Stories 1 and 2 both hold.

---

## Phase 5: User Story 3 - The containment guarantee is still proved, not assumed (Priority: P2)

**Goal**: The runtime containment check keeps discriminating "reaches exactly the test repository" from "reaches more" from "could not determine what it reaches" under the new credential shape.

**Independent Test**: Exercise the containment check under the new credential shape with a correctly scoped credential, an over-scoped one, and one that cannot enumerate repositories at all, and assert the three outcomes differ.

### Implementation for User Story 3

- [X] T018 [US3] Add Gate 67 scenarios (data-model.md table rows #6/#7) specifically for containment under the fine-grained shape: a correctly scoped token whose stubbed `user/repos` response is exactly `{E2E_REPO}` passes; a token whose stubbed response includes one extra repository fails, naming it with the account's own login replaced by the `<maintainer account>` placeholder (FR-014, reusing the existing redaction logic Gate 67 already asserts for the classic shape); a stubbed `gh api user/repos` call that itself exits non-zero (T004's fix) is reported as "containment could not be established," never as "reached 0 repositories."
- [X] T019 [US3] Add a mutation reverting T004's exit-status fix (folding the `gh api` failure back into the empty-output case) and confirm it breaks the "could not be established" scenario's assertion from T018 — proving the containment check can fail in the specific way FR-013/FR-015 requires, not just that it happens to pass today.
- [X] T020 [US3] Run quickstart.md Scenario 3: confirm Gate 67's three containment outcomes (pass / over-scoped / unobservable) never collapse into two (SC-005). The scenario's optional live-side step (a token scoped to "all repositories" for an account that also owns something else) is left to the maintainer's discretion per quickstart.md — no code change is needed for it, per research.md D3's claim that the existing invariant already catches it.

**Checkpoint**: containment is demonstrably able to fail in three distinguishable ways under the new shape; User Story 3 holds alongside 1 and 2.

---

## Phase 6: User Story 4 - One statement of the accepted credential shape (Priority: P2)

**Goal**: Exactly one place states the accepted credential shape, its scope, permissions, lifetime, and containment mechanism; every other site points at it; a gate fails if a contradicting statement reappears.

**Independent Test**: After the change, sweep the repository for statements about the credential's shape and assert every one either is the canonical statement or points at it; assert the sweep fails when a contradicting statement is reintroduced.

### Implementation for User Story 4

- [X] T021 [US4] Confirm `docs/setup.md` §2's row (T011) is the sole canonical statement and carries no unpointed restatement elsewhere in that file.
- [X] T022 [US4] Add a pointer to `docs/setup.md` (`-- see docs/setup.md` or `(see docs/setup.md)`) in Gate 67's own docstring/header comment in `.github/scripts/verify-auto-release-credential-step.py`, and reword any scenario description there that currently asserts an absolute shape claim (e.g. anything implying "classic only") to a qualified statement consistent with dual acceptance (contracts/canonical-statement-gate.md, site 3).
- [X] T023 [US4] Confirm the comment block T005 wrote above the credential step in `.github/workflows/auto-release.yml` carries the same pointer form (site 2) and no unqualified "not fine-grained"/"never fine-grained" phrase.
- [X] T024 [US4] Annotate `specs/055-unattended-e2e-gates/research.md`'s D1 (~line 13) and D2 (~line 62) headings, and `specs/055-unattended-e2e-gates/spec.md`'s Clarifications session (~line 539), with a sentence stating the classic-only decision was superseded by specs/066 and pointing at it (FR-019) — preserved as history, never rewritten to read as though the fine-grained shape had always been chosen.
- [X] T025 [US4] Create `.github/scripts/verify-maintainer-credential-canonical-statement.py` (Gate 99, per T001's baseline — recheck the next free number before registering) per contracts/canonical-statement-gate.md: scan the four named sites for the fixed contradicting-phrase list (an unqualified "not fine-grained"/"never fine-grained" claim; "classic PAT... the only accepted shape" or equivalent absolute language; "Write — never Admin" stated as the credential's own bound) outside `docs/setup.md`'s canonical row; require sites 2 and 3 to carry a pointer to site 1; require site 4 to carry the FR-019 annotation from T024. Emit `::error::` lines naming the file, the offending phrase or missing pointer, and which rule fired, per this suite's existing convention — never a bare "gate failed."
- [X] T026 [US4] Add the gate's self-test (Constitution VIII, contracts/canonical-statement-gate.md's Self-test obligation): a clean fixture (current-state text at all four sites) that passes; a mutation reintroducing each fixed contradicting phrase at each pointer site without a pointer, each failing; a mutation removing the pointer from site 2 or site 3 while leaving a qualified restatement in place, failing; a mutation removing the FR-019 annotation from specs/055's research.md, failing; a mutation pointing site 2 or site 3 at a nonexistent target, failing.
- [X] T027 [US4] Register the new gate in `.github/workflows/lint-workflows.yml`, following the Gate 97/98 pattern (~line 4118): a `- name: Gate 99 — one canonical statement of the accepted maintainer-credential shape, every other site a pointer` step running `python3 .github/scripts/verify-maintainer-credential-canonical-statement.py`, and a `- name: Gate 99 self-test — ...` step running its self-test mode.
- [X] T028 [US4] Run quickstart.md Scenario 4: run `python .github/scripts/run-local-gates.py`, confirm the new gate passes against the post-migration text at all four sites, then temporarily reintroduce an unqualified "not fine-grained" sentence at one pointer site, confirm the gate fails naming that site, and revert (SC-004).

**Checkpoint**: exactly one canonical statement exists; every other site points at it; the gate demonstrably catches drift.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Repository-wide checks this feature's diff must pass before it can be reviewed and merged.

- [X] T029 [P] Run `python .github/scripts/run-local-gates.py` (CLAUDE.md's PR-time gate suite) and fix anything Gate 67, Gate 99, or any pre-existing gate newly flags as a result of this feature's changes.
- [X] T030 [P] Run the `review-step-gating` skill against this feature's diff, since it adds new fail-infra exit branches inside the "Confirm the fixture maintainer identity's credential" step and downstream steps still gate on `steps.maintainer-credential.outputs.ok == 'true'` (CLAUDE.md's rule for any change touching a failing step).
- [X] T031 Confirm no published stage workflow, the verdict schema, or any adopter-facing default changed (FR-021, SC-007): diff `.github/workflows/{intake,clarify,plan,tasks,implement,converge,finalize,cleanup,watchdog}.yml` and `docs/adoption.md` against the previous release tag and confirm this feature's commits touch none of them.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately.
- **Foundational (Phase 2)**: Depends on Setup completion — BLOCKS all user stories.
- **User Story 1 (Phase 3)**: Depends on Foundational (T002's shape classification and T004's containment fix).
- **User Story 2 (Phase 4)**: Depends on User Story 1 — its fixtures exercise the fine-grained branches T006-T009 implement.
- **User Story 3 (Phase 5)**: Depends on Foundational (T004) and User Story 1 (T010's shared containment wiring), but not on User Story 2's credential-validity fixtures — could run in parallel with Phase 4 by a second contributor.
- **User Story 4 (Phase 6)**: Depends on User Story 1 (T011's canonical-statement content must exist before Phase 6 can point at it) but not on User Story 2/3's fixture work — could start as soon as T011 lands.
- **Polish (Phase 7)**: Depends on all preceding phases being complete.

### Within Each User Story

- User Story 1: T006 before T007/T008 (both probes reuse T006's resolved login/transport-failure handling); T009 (expiry) is independent of T007/T008 but shares the step's env block, so sequence to avoid merge conflicts within the same file; T010 depends on T004 (Foundational) and confirms no duplicate logic; T011 (docs) can proceed in parallel with T006-T010; T012 (live validation) depends on all of T002-T011.
- User Story 2: T013-T015 (new scenarios) before T016 (mutations, which target those scenarios' assertions); T017 (validation) depends on T013-T016.
- User Story 3: T018 before T019 (the mutation targets T018's new scenario); T020 depends on T018-T019.
- User Story 4: T021-T024 (the four sites) can proceed in any order once T011 exists; T025 (the gate) depends on T021-T024 being in their final form, since the gate's fixed-phrase/pointer check reads them; T026 (self-test) and T027 (registration) depend on T025; T028 (validation) depends on T025-T027.

### Parallel Opportunities

- T007 and T008 (the D6 and D5 probes) touch different `if` arms of the same shell block but assert independent permissions — implement sequentially within the same file, but their test coverage (part of T013) can be written in parallel.
- Phase 5 (User Story 3) and Phase 4 (User Story 2) both extend Gate 67 but cover disjoint outcome-table rows (credential validity vs. containment) — a second contributor could pick up Phase 5 as soon as Phase 3 completes, in parallel with Phase 4.
- Phase 6 (User Story 4) is documentation- and gate-only, independent of Phase 4/5's Gate 67 fixture work once T011 (docs content) exists — a second contributor could pick it up in parallel with Phase 4/5.
- T029 and T030 (Polish) are independent checks over the finished diff — parallelizable.

---

## Parallel Example: User Stories 2 and 3 (after User Story 1 completes)

```bash
# Contributor A extends Gate 67 for credential-validity branches:
Task: "Extend verify-auto-release-credential-step.py with fine-grained validity/permission/Administration scenarios (T013-T017)"

# Contributor B extends Gate 67 for containment branches, in parallel:
Task: "Extend verify-auto-release-credential-step.py with fine-grained containment scenarios (T018-T020)"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup.
2. Complete Phase 2: Foundational (CRITICAL — blocks every user story).
3. Complete Phase 3: User Story 1.
4. **STOP and VALIDATE**: run quickstart.md Scenario 1 end to end (T012). This alone proves SC-001/SC-006 and is the feature's whole point — a correctly scoped fine-grained credential drives a live attempt to a terminal verdict.

### Incremental Delivery

1. Setup + Foundational → shape detection exists, the classic path is unchanged, containment's exit-status bug is fixed for both shapes.
2. Add User Story 1 → a fine-grained credential authenticates and drives a live attempt (MVP!).
3. Add User Story 2 → every credential misconfiguration is caught before any spend.
4. Add User Story 3 → containment is demonstrably able to fail in three distinguishable ways.
5. Add User Story 4 → one canonical statement exists, everywhere else points at it, and a gate catches drift.

### Notes

- [P] tasks touch different files, or independent scenarios within a shared fixture file, with no dependency between them.
- [Story] labels map each task to spec.md's user stories for traceability.
- No published stage workflow or `docs/adoption.md`-documented wrapper changes at any step (FR-021) — every edit lands in `auto-release.yml` (this repository's own wrapper), `verify-auto-release-credential-step.py`'s fixtures, a new gate script, `lint-workflows.yml`'s gate registry, `docs/setup.md`, and specs/055's history annotation.
- Every new precheck decision is a fixed string/status-code comparison in shell (Constitution IX) — no task above asks an agent to judge whether a credential passes.
