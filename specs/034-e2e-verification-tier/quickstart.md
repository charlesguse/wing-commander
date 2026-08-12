# Quickstart: Validating the End-to-End Verification Tier

Prerequisites: same as `specs/027-auto-update-spec-kit/quickstart.md` (a repo
checkout with `gh` authenticated as a maintainer, a willingness to stage
disposable issues/PRs/repositories against a scratch environment — never
against this repository's real pinned version without immediately cleaning
up). Additionally: the scheduled job's token needs repository create/delete
rights for Scenarios 4-7 below (spec.md Assumptions) — those scenarios can
alternatively be exercised entirely through the executable harness
(`.github/scripts/auto-update-spec-kit-tests/`, extended by this feature),
which is the primary, repeatable validation path per FR-015/FR-020 and does
not need real `gh repo create`/`delete` rights at all.

Run the harness with:

```sh
bash .github/scripts/auto-update-spec-kit-tests/run-tests.sh t4_verify
bash .github/scripts/auto-update-spec-kit-tests/run-tests.sh          # everything
```

## Scenario 1 — Healthy candidate: every check passes, tier reports pass (US1 Acceptance #1, SC-002, SC-009)

1. Harness: `t4_verify.sh`'s per-script block runs the extracted
   `spec.md`-non-empty, `setup-plan.sh`, and `setup-tasks.sh` assertion
   steps against a real fixture worktree seeded from this repository's own
   `.specify/templates/`, then feeds an `agent_out()`-built
   `claude-execution-output.json` representing a completed e2e-stage that
   produced a `spec.md`.
2. Expected: each extracted step reports `passed=true`; `combine` reports
   `tier=lightweight+end-to-end`, `passed=true`.
3. Live equivalent: dispatch the stage against an unmodified upstream
   candidate that is a minor/major jump from the pinned version. Expected:
   the version-bump PR opens (unchanged from specs/027 Scenario 5) — but its
   evidence is now the candidate's own four scripts plus a completed
   `e2e-stage` run, confirmed via the job summary or the PR body's
   "Verified: lightweight+end-to-end checks passed" line, not the old
   copy-and-check-non-empty step.

## Scenario 2 — Missing expected artifact fails, no fallback content, single outcome (US2, FR-004, SC-002)

1. Harness: seed the fixture worktree's `.specify/templates/` **without**
   `plan-template.md`, run `setup-plan.sh --json` for real against it, then
   run the extracted "assert `IMPL_PLAN` non-empty" check against the
   resulting `plan.md`.
2. Expected: `setup-plan.sh` exits `0` (its own silent-empty fallback, not
   a crash) but writes a zero-byte `plan.md`; the non-empty assertion
   reports `passed=false`, naming `plan.md` in `failure-detail` — **no**
   locally-manufactured substitute is ever written by the tier itself
   (confirm no `else`/`printf placeholder` branch exists anywhere in the
   extracted step's source).
3. Repeat with `spec-template.md` missing instead (same shape, via
   `create-new-feature.sh`'s own identical fallback).
4. Confirm via `t7_gating.py` (or direct inspection of `act`'s `if:`
   conditions) that this failure reaches the exact same single branch as
   every other deeper-tier failure — no distinct label, no second comment
   kind, no routing branch (FR-005/FR-006).

## Scenario 3 — Wrong-shape or non-zero-exit script result fails (US1 Acceptance #2/#3, SC-008)

1. Harness: inject a mutant — rename a documented JSON field
   `setup-tasks.sh` emits (e.g. `TASKS_TEMPLATE` → `TASKS_TMPL`), or make
   `setup-plan.sh` exit non-zero (`GH_STUB_FAIL`-style injection, or a
   direct fixture edit) — and re-run the extracted assertion step.
2. Expected: `passed=false`, `failure-detail` states what shape/exit was
   expected and what was observed (FR-003). Repeat once per script in scope
   (`create-new-feature.sh`, `check-prerequisites.sh`, `setup-plan.sh`,
   `setup-tasks.sh`) — SC-008 requires a defect in *any one*, in isolation,
   to fail the tier; the harness's mutation-table convention (README.md)
   should record each as caught, per the existing precedent for the
   `FEATURE_DIR` double-prefix and `--paths-only` mutants.

## Scenario 4 — AI-driven stage does not complete: verification failure, distinguished from a candidate defect (US1 Acceptance #6, FR-021)

1. Harness: `agent_out()` a `claude-execution-output.json` with
   `is_error=true` (or omit the file entirely, simulating a timeout), run
   the extracted "Read back stage result" step.
2. Expected: `passed=false`; `failure-detail` states explicitly that the
   stage *did not complete* — distinct wording from Scenario 5's "completed
   but wrong shape" — so a maintainer reading only the issue can tell an
   infrastructure problem from a broken candidate (FR-021, SC-004).
3. Confirm the combined verdict still reports the single `auto-update:failed`
   outcome (FR-018: the stage gates adoption, it is never reported without
   effect).

## Scenario 5 — AI-driven stage completes but produces no/wrong-shaped output (US1 Acceptance #6, FR-018)

1. Harness: `agent_out()` a successful result whose working-tree fixture
   has no `specs/*/spec.md` (or an empty one).
2. Expected: `passed=false`; `failure-detail` states the expected output
   (a non-empty `specs/*/spec.md`) versus what was observed (none).

## Scenario 6 — Missing-artifact narration carries the FR-008 hint; other failures don't (US3, FR-008/FR-009)

1. Harness: drive `combine` (or the full `t4_verify.sh` chain) once with a
   missing-template failure (Scenario 2's shape) and once with a
   non-zero-exit or e2e-stage-incomplete failure (Scenarios 3/4).
2. Expected: only the missing-artifact case's `failure-detail` contains the
   sentence naming a possible legitimate reorganization and pointing at
   specs/027 FR-018 (`check_contains`); the other cases' `failure-detail`
   does not (`check_not_contains`) — confirm via the harness the label
   applied, the adoption decision, and the run's flow are otherwise
   identical (FR-009's "narration content only").
3. Confirm every tier=lightweight+end-to-end run's narration — pass or
   fail — names the scratch repository and states it is deleted on issue
   close (SC-012), via a `check_contains` on the composed detail/summary
   text, not just the failure path.

## Scenario 7 — Scratch repository: retained while open, deleted on close (US3 Acceptance #5/#6, FR-019/022/023, SC-011)

1. Harness (`gh_stub.py`'s new `repo create`/`repo delete`/`repo list`
   handling): drive the extracted scratch-repo-create step for a lifecycle
   issue number, confirm `gh repo view` then reports it present; re-run the
   create step (simulating a re-dispatch) and confirm no duplicate is
   recorded (idempotency).
2. Drive the `issue-closed` trigger's deletion branch against that same
   issue number; confirm the stub's state marks the repo deleted, and that
   re-running the deletion branch against an already-deleted (or
   never-created) repo does not error (idempotent).
3. Drive the scheduled backstop sweep against a stub state containing one
   repo whose issue is `OPEN`, one whose issue is `CLOSED`, and one whose
   issue number no longer exists at all; confirm only the latter two are
   deleted.
4. Live equivalent (optional, needs real repo create/delete rights):
   observe a full minor/major cycle create `wing-commander-e2e-<issue>`,
   confirm it's reachable from the lifecycle issue's own comments
   (SC-012), close the issue, confirm the repository is gone.

## Scenario 8 — Lightweight-only tier is unaffected (Edge Case: patch-type jump)

1. Reach the settled state for a patch-type jump (same shape as specs/027
   Scenario 7's patch half).
2. Expected: `e2e-stage` never runs (`if:
   needs.prepare.outputs.release-type != 'patch'` short-circuits), no
   scratch repository is ever created for this cycle, `tier=lightweight`,
   unchanged from specs/027.

## Scenario 9 — Every deeper-tier failure reason matches the tier's actual behaviour (FR-016, SC-007)

1. Compare `specs/027-auto-update-spec-kit/quickstart.md` Scenario 7's
   narrative (implementation-phase edit, not this plan's own artifact)
   against the tier's actual checks after implementation.
2. Expected: the narrative states the tier exercises every dependent
   Spec Kit script plus one real AI-driven stage against a scratch
   repository, single failure path, no fallback — matching this feature's
   spec.md and this quickstart's scenarios above, not the old "throwaway
   spec-kit-driven stage generated and discarded" description that never
   matched the implementation.

See `contracts/e2e-verification-tier.md` for the exact job/step contracts
and `data-model.md` for the extended Verification result, AI-driven stage
run, scratch repository, and failure narration shapes each scenario above
exercises. `specs/027-auto-update-spec-kit/quickstart.md` Scenarios 1-6,
8-15 are unaffected by this feature and are not repeated here.
