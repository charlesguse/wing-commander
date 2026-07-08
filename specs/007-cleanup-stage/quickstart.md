# Quickstart: Validating the Cleanup Stage

Prerequisites: a repo checkout with `gh` authenticated as a maintainer,
and one or more scratch specifications at various pipeline stages (a
draft-only spec, a spec with an open plan or tasks PR, and a spec whose
final PR is open) so each scenario below has a real pull request to
close.

## Scenario 1 — Common case: final PR merges (US1, SC-001, SC-002)

1. Merge a scratch specification's final pull request
   (`spec/NNN-slug → main`).
2. Expected, with zero manual steps:
   - `spec-draft/NNN-slug`, `spec/NNN-slug`, `plan/NNN-slug`,
     `tasks/NNN-slug` (if it existed), and any `impl/NNN-slug-iter*`
     branches are all gone (`git ls-remote --heads origin` shows none).
   - The lifecycle issue (`gh issue view <N>`) is **closed**, carrying a
     completion-summary comment describing what the merged feature
     delivered — readable without opening the merged PR or inspecting
     the branch list (SC-002).
   - The issue's label reads `stage:done` (no prior `stage:*` label
     remains).

## Scenario 2 — Draft rejection (US2, SC-003)

1. Close a scratch specification's draft pull request
   (`spec-draft/NNN-slug → main`) **without** merging it.
2. Expected:
   - `spec-draft/NNN-slug` is deleted.
   - The lifecycle issue has neither a `stage:*` label nor a
     `spec:NNN-slug` label anymore.
   - The issue carries a comment stating the specification was rejected.
   - The issue is still **open** (`gh issue view <N> --json state`) —
     FR-014, so the requester can revise and re-enter the pipeline.

## Scenario 3 — Built specification's final PR is rejected (US4, SC-007)

1. Close a scratch specification's final pull request
   (`spec/NNN-slug → main`) **without** merging it.
2. Expected:
   - `spec/NNN-slug`, `plan/NNN-slug`, `tasks/NNN-slug`, and any
     `impl/*` branches are all still present — nothing is deleted.
   - The issue's label reads `stage:stalled` (prior stage label removed).
   - The issue carries a comment stating the final pull request was
     rejected, including a link and manual commands for optionally
     tearing the specification down completely (FR-015).
   - `specs/NNN-slug/spec-meta.json` on `spec/NNN-slug` now reads
     `"stage": "stalled"`.

## Scenario 4 — Non-final (plan/tasks) PR is rejected (US4, FR-013)

1. Close a scratch specification's open plan PR (or tasks PR, in
   `SPECKIT_TASKS_REVIEW=pr` mode) **without** merging it.
2. Expected: identical shape to Scenario 3 — `stage:stalled`, branches
   intact, a stalled comment with the teardown runbook — but this time
   produced by `speckit-7-cleanup.yml` itself, not by a `stalled` job
   inside `speckit-3-plan.yml`/`speckit-4-tasks.yml` (those jobs are
   retired by this feature; confirm only one stalled comment appears).

## Scenario 5 — Non-final PR merges normally: no action (FR-013 acceptance #4)

1. Merge a scratch specification's plan PR (`plan/NNN-slug → spec/NNN-slug`)
   the ordinary way.
2. Expected: `speckit-7-cleanup.yml` takes no action at all (no run, or a
   run whose jobs all evaluate `if:` false) — the tasks stage's own
   `pull_request: closed` trigger is what reacts to this merge, unchanged.

## Scenario 6 — Unowned pull requests: no action (User Story 3, FR-010)

1. Open and close an ordinary pull request unrelated to the pipeline
   (e.g. a docs fix branch merged into `main`).
2. Open a pull request from a branch literally named `plan/foo` but
   targeting `main` instead of a `spec/*` branch, and close it unmerged.
3. Expected in both cases: no branch deletion, no label change, no issue
   comment. For case 2, confirm the run either doesn't start or its
   refusal step reports (via `gh pr comment`) that the merge target
   doesn't match this specification's expected base, per the
   base-ref-mismatch edge case.

## Scenario 7 — Idempotency: re-delivered / partially-applied events (User Story 3, FR-011)

1. Immediately after Scenario 1 completes, re-run
   `speckit-7-cleanup.yml`'s `teardown-done` job for the same PR (e.g.
   via `gh workflow run` replay, or by re-triggering the event if the
   platform allows).
2. Expected: the job finds the issue already closed and skips the
   summary/close/label steps, but still (harmlessly) re-attempts branch
   deletion, finding every branch already absent and treating that as
   success. No duplicate comment appears on the issue
   (`gh issue view <N> --json comments` — same count as after Scenario 1).
3. Repeat the same check for Scenario 2 (identity label already absent)
   and Scenario 3/4 (label already `stage:stalled`) — each must produce
   no duplicate comment.

## Scenario 8 — Identity cannot be resolved (Edge Case, FR-009)

1. Manually push a branch named `spec/999-does-not-exist` with no
   corresponding `specs/999-does-not-exist/` directory, open a PR to
   `main`, and close it (merged or not).
2. Expected: the refusal step fails loudly (`::error::`, step summary)
   and comments on the *pull request itself* (not any lifecycle issue,
   since none can be resolved) explaining that identity resolution
   failed. No branch is deleted, no label changes anywhere.

See `contracts/cleanup-workflow.md` for the exact trigger/job-gate/
refusal/outcome contracts and `data-model.md` for the full outcome
table and the `spec-meta.json` state transition each scenario above
exercises.
