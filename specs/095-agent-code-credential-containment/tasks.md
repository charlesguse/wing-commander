# Tasks: Agent-Authored Code Never Runs Beside the Loop's Write Token

**Input**: Design documents from `specs/095-agent-code-credential-containment/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/ (`gate-verdict.schema.json`, `workspace-bundle.md`, `new-gates.md`), quickstart.md

**Tests**: The spec requires a checked-in fixture per gate failure branch (FR-020) and a `--self-test` per gate. Those are written as part of each gate task, not as separate TDD tasks.

**Organization**: Grouped by user story. US1 is the MVP. Before pushing, run `python .github/scripts/run-local-gates.py`. Any change to an `if:`/`continue-on-error:` also gets the `review-step-gating` skill; any `run:` step in a `container:` job gets `container-shell-safety`. Workflow comments are load-bearing: re-run the suite after comment edits.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: US1 (gate suite credential-free, P1), US2 (snapshot/env integrity, P2), US3 (composite `run:` provenance, P3), US4 (hooks/config/`.git` deny, P4)

## Phase 1: Setup

**Purpose**: Locate current call sites; line numbers in the spec have drifted (research R4/R7).

- [x] T001 Re-read current `main` shapes and record the exact step names/line anchors for the four gate-suite sites (`board-loop.yml` fixer and review-fixup steps, `implement.yml` cycle and retry steps) and the push sites (`board-loop.yml` x2, `implement.yml` x1) as a short note at the top of `specs/095-agent-code-credential-containment/quickstart.md`
- [x] T002 [P] Read `.github/scripts/verify-board-loop-helper-provenance.py` (Gate 98), `verify-board-loop-composite-provenance.py` (Gate 104), `verify-implement-gate-suite-preflight.py`, `verify-stage-tool-lists.py`, and the spec-090 write-boundary definition, and list in `specs/095-agent-code-credential-containment/quickstart.md` what each asserts about the current in-job gate step (hot spot in plan.md)
- [x] T003 [P] Check `.github/scripts/wc_gate_registry.py` and `lint-workflows.yml` to document how a new `verify-*.py` gate is registered with path triggers (FR-019/FR-021) in `specs/095-agent-code-credential-containment/quickstart.md`

---

## Phase 2: Foundational (blocking)

**Purpose**: Shared single-home pieces that every story consumes. No workflow is wired yet.

**⚠️ CRITICAL**: No user story work begins until this phase is complete.

- [x] T004 Implement `.github/scripts/wc_gate_verdict.py` (single home): a writer that emits a verdict per `contracts/gate-verdict.schema.json` and a fail-closed reader that validates schema, `head_sha` == expected, `trusted_sha` == `github.sha`, `outcome` in {`pass`,`fail`}; any absence/unreadable/unknown key/mismatch yields `outcome=fail` with `reason` and `first-failure`; write outputs via `wc_step_output.py`; include `--self-test`
- [x] T005 [P] Add fixtures under `.github/scripts/fixtures/095-gate-verdict/` for every reader branch: artifact missing, unparsable, unknown key, `outcome` not pass/fail, `head_sha` mismatch, `trusted_sha` mismatch, valid pass, valid fail
- [x] T006 Create `.github/scripts/verify-gate-verdict-fail-closed.py` (FR-002/FR-003/FR-004) driving T005 fixtures through `wc_gate_verdict.py`, also failing a publisher `if:` that treats a skipped/cancelled gate job as green; fixtures for that branch in `.github/scripts/fixtures/095-gate-verdict/`; include `--self-test`; register in `.github/workflows/lint-workflows.yml` with path triggers
- [x] T007 [P] Create composite `.github/actions/wing-commander-contained-gate-suite/action.yml` (steps shared by every gate-suite job): verify bundle (`git bundle verify`), check out `head_sha` from `contracts/workspace-bundle.md` layout, run `python3 .github/scripts/run-local-gates.py` guarded on the script existing (Principle VI), write the verdict via `wc_gate_verdict.py`, upload `wc-gate-verdict-<site>`; missing/unverifiable/oversized bundle writes `outcome=fail`, never skips; every `run:` sets `shell: bash`
- [x] T008 [P] Create composite `.github/actions/wing-commander-gate-bundle/action.yml` that builds `bundle.git` (`<base-sha>..HEAD`) and `meta.json` (`base_sha`, `head_sha`, `site`) and uploads `wc-gate-bundle-<site>`; optional inputs with defaults only (Principle VII)
- [x] T009 [P] Create composite `.github/actions/wing-commander-hardened-push/action.yml` with script in `.github/actions/_shared/` implementing the single hardened-push idiom: inputs `branch`, `token`, `expected-head-sha`; refuses to push if `HEAD` != expected; `core.hooksPath=/dev/null` via `GIT_CONFIG_COUNT`/`KEY_n`/`VALUE_n`, empty pristine `GIT_CONFIG_GLOBAL`, `GIT_CONFIG_NOSYSTEM=1`, explicit URL from `github.server_url` + `$GITHUB_REPOSITORY` (research R7)
- [x] T010 Create `.github/scripts/verify-hardened-push.py` (FR-015–FR-017, FR-022) with fixtures in `.github/scripts/fixtures/095-hardened-push/`: raw `git push origin` at a covered site; idiom pasted instead of using the composite; planted `pre-push` hook ran (real local git run against a temp bare remote); planted `url.<base>.insteadOf` redirected the push. If the env override does not neutralise `insteadOf`, implement the R7 fallback (push from a fresh `git init` shim repo) in T009 and re-run; include `--self-test`; register in `lint-workflows.yml`

**Checkpoint**: Verdict module, composites and the hardened-push gate exist and pass locally; nothing is wired into a workflow.

---

## Phase 3: User Story 1 - Gate suite cannot reach the loop's credentials (P1) 🎯 MVP

**Goal**: Every FR-005 gate-suite call site runs in a `permissions: contents: read` job with no App token; the verdict returns as a head-SHA-bound artifact read fail-closed.

**Independent Test**: A fixture gate that dumps its environment finds no write credential; green pushes, red stalls with a fenced first failure, and an absent verdict is red (spec US1 scenarios 1-4).

- [ ] T011 [US1] In `.github/workflows/board-loop.yml` `fix` job: remove the in-job `Run local gate suite (fixer)` step, add the `wing-commander-gate-bundle` upload after the agent phase, add a `gate-suite-fix` job (`permissions: contents: read`, no `create-github-app-token`, no `wing-commander-context`, `persist-credentials: false`, uses `wing-commander-contained-gate-suite` from the trusted checkout), and make the publish steps read the verdict via `wc_gate_verdict.py` (absent/cancelled = fail via `if: !cancelled()`), preserving push-on-green and fenced `board:stalled` on red (FR-002/FR-003). Split the job at the push boundary as needed so the credential-bearing publish job downloads bundle and verdict
- [ ] T012 [US1] Apply the same bundle → `gate-suite-review-fixup` job → verdict-gated publish change to the review-fixup gate step in `.github/workflows/board-loop.yml`, reusing the composites from T007/T008 (no pasted `run:` copies)
- [ ] T013 [US1] Amend Gate 98 (`.github/scripts/verify-board-loop-helper-provenance.py`) and Gate 104 (`.github/scripts/verify-board-loop-composite-provenance.py`) in the same commit as T011/T012 so the `run-local-gates.py` carve-out moves with the step and the new jobs' composites are covered; update their fixtures
- [ ] T014 [US1] In `.github/workflows/implement.yml`: add a pre-agent `gate-suite-implement-cycle` job (credential-free) on the spec-branch head whose verdict feeds the agent's prompt, and make the implement job's agent step wait on it (`needs:`) and read the verdict through `wc_gate_verdict.py`; `continue-on-error` semantics preserved (verdict is prompt input, not a push decision); apply `review-step-gating`
- [ ] T015 [US1] Decide the implement **retry** site after reading the job graph (research R6): either bundle the cycle output and add a downstream credential-free job, or defer and record the deferral in `specs/095-agent-code-credential-containment/quickstart.md` for the #737 comment; record the decision
- [ ] T016 [US1] Update `.github/scripts/verify-implement-gate-suite-preflight.py` and its fixtures in the same commit as T014 so they assert the new job shape
- [ ] T017 [US1] Create `.github/scripts/verify-gate-suite-credential-free.py` (FR-001/FR-004/FR-005/FR-006) with fixtures in `.github/scripts/fixtures/095-gate-suite/`: job with App-token step; `permissions` above read; gate step still in the credential-bearing job at any FR-005 site; undeterminable job graph (fails loud); `--self-test`; register in `lint-workflows.yml` with triggers on the three workflows and the composites
- [ ] T018 [US1] Add a fixture env-dumping gate and a `board:stalled`/green walkthrough to `specs/095-agent-code-credential-containment/quickstart.md` so SC-001/SC-005 are reproducible

**Checkpoint**: US1 independently testable; MVP complete.

---

## Phase 4: User Story 2 - Snapshot and environment stay trusted after agent code runs (P2)

**Goal**: The snapshot/trusted-copy guarantee is stated precisely, and no agent-code step remains in a job that later pushes.

**Independent Test**: A fixture gate that `chmod u+w`s the snapshot and appends to `$GITHUB_ENV`/`$GITHUB_PATH` affects no durable-action step, because it ran in another job.

- [ ] T019 [US2] Rewrite the snapshot-documenting comment in `.github/workflows/board-loop.yml` (FR-009/FR-010) stating exactly which steps the guarantee covers, that it rests on agent-code execution having moved to a separate job, and the runner assumption (fresh VM per job; self-hosted must be ephemeral); add the one-line pointer form at other sites per CLAUDE.md "canonical comment" rule and check Gate 47
- [ ] T020 [P] [US2] Add the matching comment at the implement gate-suite job in `.github/workflows/implement.yml` as a pointer to the canonical comment in `board-loop.yml`
- [ ] T021 [US2] Create `.github/scripts/verify-snapshot-integrity-statement.py` (FR-007–FR-010) with fixtures in `.github/scripts/fixtures/095-snapshot-statement/`: comment missing covered-steps text; missing runner-assumption text; agent-code step remains in a job that later pushes; `--self-test`; register in `lint-workflows.yml`

**Checkpoint**: US1 and US2 both hold.

---

## Phase 5: User Story 3 - Composite `run:` bodies import from the trusted copy (P3)

**Goal**: A gate sees inside composites reachable from covered jobs so a workspace-relative call cannot reappear. No behavioural change to `wing-commander-board-stop-check` (already closed, research R1).

**Independent Test**: The gate fails on a composite calling `python3 .github/scripts/x.py` and passes on `$GITHUB_ACTION_PATH`-relative or snapshot paths.

- [x] T022 [US3] Create `.github/scripts/verify-composite-run-provenance.py` (FR-011/FR-013/FR-014): resolve the composites reachable (`uses: ./...`, transitively) from the board-loop `fix`/`review`/`readiness` jobs and the lifecycle stages, scan their `run:` bodies for workspace-relative script paths; fail loud when the reachable set cannot be determined; `--self-test`
- [x] T023 [US3] Add fixtures in `.github/scripts/fixtures/095-composite-run/`: composite `run:` with workspace-relative script (fail), undeterminable composite set (fail loud), composite moved out of view (fail), snapshot/`$GITHUB_ACTION_PATH` form (pass); confirm the real `wing-commander-board-stop-check` passes
- [x] T024 [US3] Register the gate in `.github/workflows/lint-workflows.yml` with path triggers on `.github/actions/**`, the workflows, and the script; confirm the new contained-gate-suite composite is exempt only by design (it runs the suite on purpose) and record why in the gate

**Checkpoint**: US3 independently testable.

---

## Phase 6: User Story 4 - Planted hook or config cannot steer the push (P4)

**Goal**: Agents cannot write `.git/**`, and every push site uses the hardened composite.

**Independent Test**: A planted `pre-push` hook and `insteadOf` have no effect on a push through the composite; the gate fails when `.git/**` is missing at a covered label.

- [ ] T025 [US4] Replace the push step in `.github/workflows/board-loop.yml` `fix` (publish) with `wing-commander-hardened-push` (one-line fallback only, no pasted idiom)
- [ ] T026 [US4] Replace the review-fixup push step in `.github/workflows/board-loop.yml` with `wing-commander-hardened-push`
- [ ] T027 [US4] Replace the push step in `.github/workflows/implement.yml` with `wing-commander-hardened-push`; where the agent's own `Bash(git push:*)` step env is workflow-controlled, set the same hardening env, and record in the #737 comment that agent-composed pushes are deferred (research R6)
- [ ] T028 [P] [US4] In `.github/workflows/pr-conversation.yml` add the `.git/**` deny to `pr-conversation.act` and harden its push env as far as the workflow controls it; no gate-suite job here (FR-001/FR-006 not applicable)
- [ ] T029 [US4] Add `Edit(.git/**)` and `Write(.git/**)` to the single stage write-boundary definition from spec 090 for implement (an entry, not a second literal list) and to the `default-disallowed-tools` of the fixer and review-fixup in `.github/workflows/board-loop.yml`; update documented lists checked by `.github/scripts/verify-stage-tool-lists.py` and its fixtures
- [ ] T030 [US4] Create `.github/scripts/verify-agent-git-deny.py` (FR-018 first half) with fixtures in `.github/scripts/fixtures/095-agent-git-deny/`: `.git/**` missing at a covered label (fixer, review-fixup, implement, pr-conversation.act); second literal list instead of the spec-090 set; `--self-test`; register in `lint-workflows.yml`
- [ ] T031 [US4] Extend `verify-hardened-push.py` fixtures (from T010) to cover each real push site now converted (T025–T028) so the "raw push at a covered site" branch is exercised against the live workflows

**Checkpoint**: All four paths closed or recorded as deferred.

---

## Phase 7: Polish & Proof

- [ ] T032 Run the read-access audit (research R8): run the suite with write credentials unset and `GH_TOKEN` read-only, list any gate needing a write credential or more than `contents: read`, and fix any found before shipping; record the result in `specs/095-agent-code-credential-containment/quickstart.md`
- [ ] T033 [P] Confirm `.github/scripts/wc_gate_registry.py`/`run-local-gates.py` pick up every new gate with the same arguments locally and in CI (FR-019); run `python .github/scripts/run-local-gates.py` and fix all failures
- [ ] T034 [P] Run the `review-step-gating` skill over every new `if:`/`continue-on-error:` and `container-shell-safety` over any `run:` in a container job; fix findings in the same PR
- [ ] T035 Verify no downstream/private consumer names appear in any added file (public repo) and that the new composites add only optional inputs (Principle VII)
- [ ] T036 Post-merge proof (FR-024/SC-008): re-drive one board-loop run (`gh workflow run` on the dispatching wrapper) through fix → green suite → pushed branch → PR, and one implement stage run; record evidence on the PR or #737; list deferrals (agent-invoked gates, agent-composed pushes, implement retry if deferred) on #737

---

## Dependencies & Execution Order

- Phase 1 → Phase 2 (blocks all stories) → US1 (MVP) → US2 → US3 → US4 → Polish.
- US2's gate (T021) needs US1's job shape (T011–T014). US4 push replacements (T025–T027) edit the same workflow files as US1, so sequence them after T011–T014 to avoid conflicts. US3 (T022–T024) is independent of US1/US2 once Phase 2 is done and can run in parallel with them.
- T013 and T016 must land in the same commit as the workflow change they track (plan.md hot spot).
- T010 may require changing T009 (R7 fallback).

## Parallel Opportunities

- Phase 1: T002, T003.
- Phase 2: T005 with T004; T007, T008, T009 together.
- Across stories: US3 (T022–T024) in parallel with US1/US2; T028 in parallel with T025–T027.
- Polish: T033, T034.

## Implementation Strategy

- **MVP**: Phases 1–3 (US1): foundation plus the credential-free gate job at the board-loop and implement-cycle sites. This alone closes paths 1 and 2 in practice (token, snapshot rewrite, `$GITHUB_ENV`/`$GITHUB_PATH`).
- **Incremental**: US2 (statement and gate), US3 (provenance gate), US4 (deny and hardened push), then Polish and post-merge proof.
- Not in scope: agent-invoked gates and agent-composed pushes (deferred per research R6 and spec 111); anything in the already-closed list (FR-023).

## Review Gate Round 1 Findings

- [x] Review finding: Gate suite passes when head lacks run-local-gates.py

  The existence check for run-local-gates.py runs against the hostile head checkout, so an agent commit that deletes it yields outcome=pass and the publisher pushes ungated code.

  - .github/actions/_shared/contained-gate-suite.sh

  Detail: line ~88; check against trusted checkout or base_sha

- [x] Review finding: Verdict writer runs from workspace replaced by hostile head

  wc_gate_verdict.py is resolved under the workspace, which `git checkout --detach head_sha` has already overwritten with the agent's copy, so a modified writer can emit any verdict.

  - .github/actions/_shared/contained-gate-suite.sh

  Detail: line ~49; copy trusted scripts out before the checkout

- [x] Review finding: Bundle fetch may lack base_sha prerequisite

  A thin bundle needs base_sha in the trusted checkout. At the implement-cycle site the spec-branch head is not an ancestor of github.sha, and at the board-loop sites main may have advanced, so the fetch fails and valid work is rejected.

  - .github/actions/_shared/contained-gate-suite.sh

  Detail: line ~82; meta.json base_sha is never used by the consumer

- [x] Review finding: Empty bundle aborts producer when no new commits

  `git bundle create base..HEAD HEAD` refuses to create an empty bundle when HEAD equals base_sha. set -e then aborts before upload and the failure reason is lost.

  - .github/actions/_shared/build-gate-bundle.sh

  Detail: line ~18

- [x] Review finding: bundle-artifact default hard-coded to board-fix

  The default is wc-gate-bundle-board-fix instead of being derived from `site`, so a caller that omits bundle-artifact downloads the wrong bundle or none.

  - .github/actions/wing-commander-contained-gate-suite/action.yml

  Detail: line ~180

- [x] Review finding: Publisher-if gate rule is easy to evade

  EXPLICIT_RE matches any outcome/result == pass|success anywhere in the expression, and only single-line `if:` values are checked. Expressions that still treat a skipped gate as green can pass the gate.

  - .github/scripts/verify-gate-verdict-fail-closed.py

  Detail: line ~452

- [x] Review finding: Raw-push detection too narrow and self-disabling

  RAW_PUSH_RE only matches `git push` at the start of a line, so `if ! git push` is missed. Any mention of the composite skips the check for the whole file. COVERED_WORKFLOWS is empty, so the static check currently checks nothing. Comments that mention core.hooksPath are also flagged.

  - .github/scripts/verify-hardened-push.py

  Detail: line ~597

- [x] Review finding: first_failure starting with '-' breaks argparse

  A first_failure value beginning with '-' is parsed as an option, so the writer exits 2 and no verdict file is written. The grep also matches benign lines such as '0 failures'.

  - .github/actions/_shared/contained-gate-suite.sh

  Detail: line ~100; use --first-failure="$4"

- [x] Review finding: read_verdict does not catch RecursionError/MemoryError

  A deeply nested hostile JSON verdict crashes the reader with a traceback, contradicting the documented exits-0 contract. The site check is also skipped when --site is omitted.

  - .github/scripts/wc_gate_verdict.py

  Detail: line ~825

- [x] Review finding: Push token embedded in remote URL

  On a failed push, git may echo the x-access-token URL to the job log. Passing the token via an extraheader or credential helper would avoid it.

  - .github/actions/_shared/hardened-push.sh

  Detail: line ~138
