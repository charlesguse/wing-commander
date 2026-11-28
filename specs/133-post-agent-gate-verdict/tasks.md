# Tasks: Post-agent full-suite verdict for implement cycles

**Input**: Design documents from `/specs/133-post-agent-gate-verdict/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/post-agent-verdict.md, quickstart.md

**Tests**: Gate scripts with `--self-test` are the repository's tests; each gate task below includes its self-test cases. Run `python .github/scripts/run-local-gates.py` (named gates while iterating) per CLAUDE.md "Before pushing". Workflow comments are load-bearing: treat comment edits as code edits.

## Format: `[ID] [P?] [Story] Description`

## Phase 1: Setup

- [X] T001 Read `.github/workflows/implement.yml`, the `gate-suite-implement-cycle` job, and the composites `wing-commander-contained-gate-suite` and `wing-commander-gate-verdict` under `.github/actions/`; record in `specs/133-post-agent-gate-verdict/research.md` only any divergence from the plan found (no edit if none)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Register the new verdict site and extract shared prepare logic, so both the cycle-start and post jobs use one home.

- [X] T002 [P] Add `implement-post` to `SITES` in `.github/scripts/wc_gate_verdict.py` and its entry in `.github/scripts/wc_gate_suite_sites.py`; extend their self-tests; verdict artifact name `wc-gate-verdict-implement-post` with fields `site`, `outcome`, `head_sha`, `trusted_sha`, `first_failure` per data-model.md `Post-agent verdict`
- [X] T003 Create composite `.github/actions/wing-commander-gate-suite-prepare/action.yml` holding the branch-resolve + preflight shell currently inlined in `gate-suite-implement-cycle` (outputs `script-exists`, `ready`, `missing`); move the logic, do not copy it (CLAUDE.md "single home")
- [X] T004 Switch `gate-suite-implement-cycle` in `.github/workflows/implement.yml` to call the new prepare composite, behaviour unchanged (FR-011); update `.github/actions/wing-commander-contained-gate-suite/action.yml` and `.github/actions/wing-commander-gate-verdict/action.yml` site-list docs and add the optional exact-head input (default = today's behaviour)
- [X] T005 Update the existing gates that pin the cycle-start job's inline preflight (single-home and preflight gates under `.github/scripts/verify-*.py`) so they accept the composite and fail on a reappearing inline copy

**Checkpoint**: cycle-start behaviour unchanged, gates green.

---

## Phase 3: User Story 1 - Converging cycle judged by the full suite (Priority: P1) 🎯 MVP

**Goal**: A converging cycle converges only on a pass bound to the pushed head; stall hand-offs get an informational verdict.

**Independent Test**: Per spec US1 and quickstart.md: all-tasks-checked branch with one failing gate → not converged, implement re-dispatched; passing → converged, finalize dispatched.

- [X] T006 [US1] In `.github/workflows/implement.yml` `implement` job: rename the tasks-only `converged` reading to output `tasks-converged`; publish outputs `handoff`, `routed`, `truncated`, `head-sha` (exact head the final attempt pushed, whichever leg) and the other values `implement-dispatch` needs (contracts/post-agent-verdict.md "Jobs")
- [X] T007 [US1] Add job `gate-suite-implement-post` to `.github/workflows/implement.yml` exactly per contracts/post-agent-verdict.md: `needs: [implement]`, the `if:` on `tasks-converged`/`handoff`, `permissions: contents: read`, no App token, same runner/container as `gate-suite-implement-cycle`, `timeout-minutes: 30`, `suite-timeout-minutes: "25"` (FR-007), verdict site `implement-post`, uses the prepare composite (T003) and contained-gate-suite composite, outputs `script-exists`, `ready`, `missing`
- [X] T008 [US1] Add job `implement-dispatch` to `.github/workflows/implement.yml`: `needs: [implement, gate-suite-implement-post]`, `if: !cancelled() && needs.implement.result == 'success'`, holds the App token, reads the verdict with `wing-commander-gate-verdict` (`site: implement-post`, `expected-head-sha` = `head-sha`, `gate-job-result`), computes final `converged` by the decision table in data-model.md `Cycle decision` (fail closed on absent/unbound/red/cancelled; missing prerequisite names `missing`; no suite → tasks alone), and moves the existing "Dispatch next step" logic here so it exists exactly once; cap-reached path keeps finalize with `converged=false` (FR-005)
- [X] T009 [US1] Point the `workflow_call` output `converged` and the metrics record's convergence field at `jobs.implement-dispatch.outputs.converged` in `.github/workflows/implement.yml` (FR-006); other outputs keep their names
- [X] T010 [US1] Stall hand-off (`handoff=true`, blocker and cap alike): in `implement-dispatch`, wait for the post job at most the suite budget, post one lifecycle-issue comment starting `<!-- wing-commander:post-agent-verdict -->` with outcome, head and fenced first failure (or "no verdict produced: <reason>") per data-model.md `Stall hand-off verdict`, then dispatch finalize unchanged; the outcome never blocks the hand-off (FR-014)
- [X] T011 [P] [US1] In `.github/workflows/finalize.yml` read the newest `<!-- wing-commander:post-agent-verdict -->` comment on the lifecycle issue and render it (or the "none produced" report) in the final PR body as untrusted fenced text; do not change finalize's `workflow_dispatch` inputs (FR-014, SC-007)
- [ ] T012 [P] [US1] Extend `.github/scripts/verify-gate-suite-credential-free.py` (with self-test cases): `gate-suite-implement-post` holds `contents: read` only and no App-token step; `implement-dispatch` is its registered reader; no `run-local-gates.py` invocation in `implement-dispatch`
- [ ] T013 [P] [US1] Create `.github/scripts/verify-implement-post-verdict.py` with `--self-test`: asserts the dispatch step exists exactly once in `implement.yml` inside `implement-dispatch`, the post job's `if:` and budget-below-timeout (FR-007), `converged` output sourced from `implement-dispatch`, and finalize's dispatch signature unchanged; register it with whatever lists `run-local-gates.py` and `lint-workflows.yml` use
- [ ] T014 [US1] Run the `review-step-gating` skill over the new `if:`/`needs` chain in `.github/workflows/implement.yml` and the `container-shell-safety` skill over the new container job; fix findings; run `python .github/scripts/run-local-gates.py`

**Checkpoint**: US1 deliverable; converging cycles are judged post-agent.

---

## Phase 4: User Story 2 - Agent runs only gates its change touches (Priority: P2)

**Goal**: Agent guidance directs targeted by-name gate runs and states the verdict comes after.

**Independent Test**: Read the implement prompt and CLAUDE.md "Before pushing"; neither asks for a full-suite run.

- [ ] T015 [US2] Change the implement prompt text in `.github/workflows/implement.yml`: run only gates for changed files by name with `run-local-gates.py`'s existing name filter, full suite runs after the agent to decide convergence; keep the cycle-start result hand-over and the no-suite wording (FR-008, FR-009; no changed-file selector)
- [ ] T016 [P] [US2] Update CLAUDE.md "Before pushing" (the part addressing the implement stage agent) to the same wording; owner approves with the final PR
- [ ] T017 [US2] Extend the gate that pins prompt/guidance text (nearest existing `verify-*.py` covering implement prompt wording) so the two texts cannot contradict, with self-test cases

---

## Phase 5: User Story 3 - Owner can see why a cycle did not converge (Priority: P3)

**Goal**: Non-convergence reason names the post-agent full suite and quotes the first failing gate.

**Independent Test**: In the red case, step summary and lifecycle comment name "post-agent full suite" with the fenced first failing gate.

- [X] T018 [US3] In `implement-dispatch` of `.github/workflows/implement.yml` render the non-convergence reason (step summary and lifecycle comment) as "post-agent full suite" plus the first failing gate in a fence, distinct from the unchecked-tasks reason, via the existing untrusted-text rendering helper (FR-010)
- [ ] T019 [US3] Add self-test cases to `.github/scripts/verify-implement-post-verdict.py` asserting the reason strings are distinct and the first failure is fenced

---

## Phase 6: Polish & Cross-Cutting

- [X] T020 [P] Update `docs/reference.md`: post-agent gate job, its 25-minute budget inside the 30-minute timeout, and its effect on convergence and stall hand-off (FR-012)
- [ ] T021 Run `python .github/scripts/run-local-gates.py` and fix any red gate; walk through `specs/133-post-agent-gate-verdict/quickstart.md` statically against the final workflow

---

## Phase 7: Maintainer follow-up

- [ ] T022 [maintainer] After merge, re-drive one implement run (`gh workflow run` on the wrapper) with all tasks checked and confirm the post-agent job ran, the verdict bound to the head, and the dispatch read it (`prove-after-merge` skill); record evidence on the PR or #1180

---

## Dependencies & Execution Order

- Phase 1 → Phase 2 (T002 ∥ T003; T004 after T003; T005 after T004) → Phase 3.
- US1: T006 → T007 → T008 → T009 → T010; T011, T012, T013 parallel once T008/T010 shape is fixed; T014 last.
- US2 (T015–T017) and US3 (T018–T019) depend on T008 (same workflow file, so do not edit in parallel with US1 tasks); US3 after US1.
- Polish after all stories; T022 after merge.

## Parallel Examples

- Foundational: T002 alongside T003.
- After T010: T011, T012, T013 (different files).
- T016 alongside T015's review; T020 alongside T021 prep.

## Implementation Strategy

MVP is Phase 1–3 (US1): the post-agent verdict deciding convergence and the stall hand-off report. Then US2 (guidance), US3 (reason rendering), polish, and the maintainer proof. Standing guidance: keep gates green and run the gate suite before pushing; these are not tasks.
