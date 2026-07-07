# Quickstart: Validating the Finalize Stage

Prerequisites: a repo checkout with `gh` authenticated as a maintainer, and
a scratch specification whose `spec/NNN-slug` branch already carries built
work ahead of `main` (e.g. run the implement/converge stage against a
scratch spec first, or manually commit a small change onto a scratch
`spec/NNN-slug`), with `spec-meta.json` at `stage: "implement"`.

## Scenario 1 — Common case: converged hand-off (US1, SC-001, SC-002, SC-005)

1. Dispatch the stage:
   `gh workflow run speckit-6-finalize.yml -f spec_dir=specs/NNN-slug -f issue=<N> -f converged=true`.
2. Expected, with zero manual steps:
   - A pull request `spec/NNN-slug → main` is opened (check with
     `gh pr list --head spec/NNN-slug --base main`).
   - Its body covers what changed, a compare link and changed-file list,
     the remaining-manual-work list (or "No manual work remains."), and
     `Lifecycle issue: #<N>` — readable without opening the raw diff or
     `tasks.md` (SC-002).
   - No ⚠️ not-fully-converged banner appears.
   - `specs/NNN-slug/spec-meta.json` now reads `"stage": "review"`.
   - The lifecycle issue (`gh issue view <N>`) carries the identical
     remaining-manual-work list as a comment, and its label reads
     `stage:review` (not `stage:implement`).
   - The pipeline has not approved or merged the PR (`gh pr view
     spec/NNN-slug --json reviews,mergedAt` shows no bot review, no merge —
     SC-005).

## Scenario 2 — Not-fully-converged hand-off (US3, SC-006)

1. Use a scratch spec whose `tasks.md` still has unchecked items.
2. Dispatch: `gh workflow run speckit-6-finalize.yml -f spec_dir=specs/NNN-slug -f issue=<N> -f converged=false`.
3. Expected: the same PR as Scenario 1, but its body opens with a
   prominent "⚠️ **Not fully converged — N tasks remain**" note near the
   top, where N matches the remaining-manual-work list's item count shown
   further down the same body — the two never disagree.

## Scenario 3 — Remaining manual work is mirrored exactly (US2, SC-003)

1. After Scenario 1 or 2 completes, diff the PR body's "Remaining manual
   work" section against the lifecycle issue's comment.
2. Expected: byte-identical (aside from surrounding markdown), including
   the "No manual work remains." case if `tasks.md` had nothing left
   unchecked or human-only (FR-006 — the report is stated, not omitted).

## Scenario 4 — Idempotency: duplicate hand-off (Edge Case, FR-012, SC-007)

1. Immediately after Scenario 1 completes, re-dispatch the identical
   command: `gh workflow run speckit-6-finalize.yml -f spec_dir=specs/NNN-slug -f issue=<N> -f converged=true`.
2. Expected: the run finds the existing PR via `gh pr list --head
   spec/NNN-slug --base main --state all`, logs a no-op step-summary note,
   and exits without opening a second PR, without a duplicate lifecycle
   comment, and without touching `spec-meta.json` or labels again. Confirm
   via `gh pr list --head spec/NNN-slug --base main --state all` (still
   exactly one PR) and the issue's comment history (unchanged count).

## Scenario 5 — No changes to finalize (Edge Case, FR-013)

1. Use a scratch spec whose `spec/NNN-slug` is identical to `main` (no
   commits ahead).
2. Dispatch as in Scenario 1.
3. Expected: no PR is opened; the lifecycle issue instead receives a
   comment reporting the anomaly ("nothing to finalize"); `spec-meta.json`
   stays at `stage: "implement"`.

## Scenario 6 — Hand-off cannot be matched to a valid specification (Edge Case, FR-014)

1. Dispatch with a `spec_dir` that doesn't exist, or one missing
   `tasks.md`, or an `issue` that disagrees with `spec-meta.json`'s own
   `issue` field:
   `gh workflow run speckit-6-finalize.yml -f spec_dir=specs/does-not-exist -f issue=<N> -f converged=true`.
2. Expected: the job fails with a clear `::error::` and step-summary
   message before any PR, comment, or metadata write occurs.

## Scenario 7 — The stage's own work fails (Edge Case, FR-015)

1. Force a failure after the refusal/idempotency/no-diff checks pass —
   e.g. temporarily revoke the App token's `pull-requests` scope, or point
   at a spec directory that becomes unreadable mid-run.
2. Dispatch as in Scenario 1.
3. Expected: the failure (summarization step failing to produce both temp
   files, or `gh pr create`/its follow-up verification failing) is reported
   as a comment on the lifecycle issue; `spec-meta.json` stays at
   `stage: "implement"` (not advanced to `"review"`) so a corrected
   re-dispatch is still recognized as "not yet finalized" by Scenario 4's
   idempotency check rather than being skipped as a false duplicate.

See `contracts/finalize-workflow.md` for the exact trigger/refusal/
idempotency/PR/post-PR contract and `data-model.md` for the
`spec-meta.json` state transition and the remaining-manual-work file each
scenario above exercises.
