# Quickstart: Validating the Plan Stage

This is a manual validation guide, run against a real (or scratch) instance
of this repository — matching the project's dogfooding-over-unit-tests
approach (see `plan.md` Technical Context → Testing). It exercises the three
user stories from `spec.md`.

## Prerequisites

- `speckit-3-plan.yml` is present on `main` (this feature's deliverable).
- `SPECKIT_APP_ID` / `SPECKIT_APP_PRIVATE_KEY` secrets are configured (the
  `speckit-bot` GitHub App), and `CLAUDE_CODE_OAUTH_TOKEN` is configured.
- `gh` CLI authenticated against the target repository.

## Scenario 1 — Accepted spec becomes a plan PR (User Story 1, P1)

1. Run stage 1 (intake) to completion for a throwaway feature, or manually
   create `specs/999-quickstart-check/{spec.md,spec-meta.json}` on a
   `spec-draft/999-quickstart-check` branch and open a PR to `main`.
2. Merge that PR.
3. **Expect**, within a few minutes:
   - Branch `spec/999-quickstart-check` exists:
     `gh api repos/:owner/:repo/branches/spec/999-quickstart-check`.
   - Branch `plan/999-quickstart-check` exists and a PR is open:
     `gh pr list --head plan/999-quickstart-check --json number,baseRefName`
     — `baseRefName` must be `spec/999-quickstart-check`, not `main`.
   - `specs/999-quickstart-check/spec-meta.json` on `spec/999-quickstart-check`
     has `"stage": "plan"` and a non-null `spec_branch`.
   - `plan.md`, `research.md`, `data-model.md`, `contracts/`, `quickstart.md`
     exist in the plan PR's diff.

## Scenario 2 — Lifecycle issue stays current (User Story 2, P2)

Using the same run as Scenario 1:

1. `gh issue view <issue-number> --json labels,comments`.
2. **Expect**: labels include `stage:plan` (and no `stage:spec`); the most
   recent comment summarizes the plan and links the PR from Scenario 1.

## Scenario 3 — Hand-submitted spec gets a lifecycle issue (User Story 3, P3)

1. Create `specs/998-handwritten/{spec.md,spec-meta.json}` directly with
   `spec-meta.json`'s `"issue": null`, on a branch
   `spec-draft/998-handwritten`, and open + merge a PR to `main` without
   ever creating a GitHub issue for it first.
2. **Expect**:
   - A new issue exists, titled `Lifecycle: <feature name from spec.md>`.
   - It carries labels `spec:998-handwritten` and `stage:plan`.
   - `specs/998-handwritten/spec-meta.json` on `spec/998-handwritten` now has
     a non-null `issue` matching that new issue's number.

## Edge case checks

- **Duplicate merge notification**: re-dispatch
  `gh workflow run speckit-3-plan.yml -f slug=999-quickstart-check` after
  Scenario 1 completes. **Expect**: the run completes without creating a
  second `plan/999-quickstart-check` branch or a second open PR (verify with
  `gh pr list --head plan/999-quickstart-check --state all`).
- **Ambiguous / missing spec**: merge a PR touching `specs/**` whose head
  branch does not start with `spec-draft/`, or whose `spec.md`/
  `spec-meta.json` are missing on `main`. **Expect**: the job fails with an
  `::error::` annotation and no branch/PR is created.
- **Plan PR closed unmerged**: open the plan PR from Scenario 1 (on a fresh
  throwaway spec) and close it without merging. **Expect**: within the same
  workflow run's `stalled` job, `spec-meta.json`'s `stage` becomes
  `"stalled"`, the issue label flips to `stage:stalled`, and a comment
  explains the manual restart (delete `plan/NNN-slug`, re-dispatch with
  `slug=NNN-slug`).
