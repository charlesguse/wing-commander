# Quickstart: Validating the Auto-Rebase Stage

Prerequisites: a repo checkout with `gh` authenticated as a maintainer,
and one or more scratch specifications with a `spec/NNN-slug` working
branch already created (i.e. past the plan stage) so each scenario below
has a real branch to rebase. Some scenarios need a commit on `main` that
conflicts with a scratch branch's own changes — pick a file the scratch
branch touches and edit the same lines on `main`.

## Scenario 1 — Common case: clean rebase behind main (US1, SC-001, SC-002)

1. Advance `main` with a commit that doesn't conflict with a scratch
   spec's `spec/NNN-slug` branch.
2. Trigger the stage (push to `main`, or `gh workflow run
   speckit-rebase.yml`).
3. Expected, with zero manual steps:
   - `spec/NNN-slug`'s tip is a rebase of its prior work onto the new
     `main` tip (`git merge-base --is-ancestor origin/main
     origin/spec/NNN-slug` succeeds; the branch's own commits still
     appear in `git log`, just replayed).
   - No comment appears on the lifecycle issue, no label changes
     (contracts/rebase-workflow.md step 4).

## Scenario 2 — Already current: no-op (US1 Acceptance Scenario 3)

1. Immediately re-run the stage against the same branch from Scenario 1
   with no further `main` advance.
2. Expected: the branch's tip SHA is unchanged (`git rev-parse` before
   and after match) — no push happens at all, not even a same-content
   force-push (data-model.md's `before == after` outcome row).

## Scenario 3 — Conflicting rebase, AI resolves it (US2, SC-002)

1. Advance `main` with a commit that edits the same lines a scratch
   spec's `spec/NNN-slug` branch already changed, in a way a competent
   editor could reconcile (e.g. both add an adjacent bullet to the same
   list).
2. Trigger the stage.
3. Expected:
   - The branch is rebased and force-pushed onto the new `main` — its
     tip now sits on top of the latest `main` (same ancestry check as
     Scenario 1).
   - `git diff` between the resolved commit and its pre-rebase original,
     restricted to files outside the ones that actually conflicted, is
     empty — no unrelated edits (FR-005, contracts/rebase-workflow.md
     step 6's scope check).
   - No lifecycle-issue comment (only the abandon path comments).

## Scenario 4 — Conflicting rebase, unresolvable (US3, SC-003)

1. Advance `main` with a commit that conflicts with a scratch branch in
   a way that's genuinely ambiguous or contradictory (e.g. `main` deletes
   a section the branch is actively editing).
2. Trigger the stage.
3. Expected:
   - `spec/NNN-slug`'s tip SHA is **byte-for-byte identical** to before
     the run (`git rev-parse` unchanged) — no half-rebased state, no
     force-push of any kind (FR-007).
   - The lifecycle issue carries a new comment asking a human to rebase
     by hand, and now has label `rebase:blocked`.
   - The comment's body contains the `speckit-rebase: blocked` HTML
     marker with the branch's (unchanged) tip SHA and the current `main`
     SHA (research.md D6) — inspect via `gh issue view <N> --json
     comments`.

## Scenario 5 — Repeated stall against an unchanged pair: dedup (FR-012)

1. Immediately after Scenario 4, trigger the stage again with no further
   change to either `main` or the blocked branch (e.g. the nightly
   schedule firing twice in a row).
2. Expected: the branch is excluded from `discover`'s matrix entirely —
   no agent run, no new comment (`gh issue view <N> --json comments` —
   same count as after Scenario 4).

## Scenario 6 — Stall clears once something changes (FR-012 "until it changes")

1. After Scenario 4/5, either (a) manually rebase the branch by hand and
   force-push it, or (b) advance `main` again with a new, unrelated
   commit.
2. Trigger the stage.
3. Expected: the branch is attempted again (not skipped) — for case (a),
   it's likely already-current and Scenario 2's no-op applies (or,
   because `rebase:blocked` is now stale relative to reality, still gets
   attempted and probably succeeds cleanly, clearing the label); for case
   (b), a fresh rebase attempt runs against the new `main` tip. Confirm
   `rebase:blocked` is removed from the issue once an attempt succeeds.

## Scenario 7 — Concurrent update during the run: silent skip (FR-011)

1. Start a rebase run for a scratch branch (e.g. via `main` advancing),
   and — while it's still in flight — push a legitimate, unrelated commit
   directly to that same `spec/NNN-slug` branch (simulating an in-flight
   pipeline stage, e.g. a tasks-stage auto-commit landing mid-run).
2. Expected: the stage's `--force-with-lease` push is rejected; the
   branch retains the concurrently-pushed commit untouched (`git log`
   shows it); no lifecycle-issue comment appears (FR-011 explicitly
   forbids one); the next run (or the nightly schedule) picks the branch
   up again and rebases cleanly against the now-current state.

## Scenario 8 — Stalled specification is excluded (spec.md edge case, FR-002)

1. Take a scratch specification whose `spec/NNN-slug` branch still exists
   but whose `spec-meta.json` (on that branch) reads `"stage":
   "stalled"` (e.g. produced by `speckit-7-cleanup.yml`'s `mark-stalled`
   job).
2. Advance `main` with a commit that would conflict with that branch.
3. Trigger the stage.
4. Expected: the branch never appears in the `rebase` job's matrix at
   all (check the workflow run's job list) — not rebased, not
   escalated, not commented on.

## Scenario 9 — No in-flight branches: quiet success (US4 Acceptance Scenario 4)

1. In a repo/checkout state with zero `spec/*` branches present (or all
   excluded per Scenarios 5/8), trigger the stage.
2. Expected: the workflow run succeeds, `discover` reports an empty
   branch list, and the `rebase` job shows zero matrix entries — no
   error, no comment anywhere.

## Scenario 10 — Loop protection: the pipeline's own push doesn't re-trigger (US4, FR-009)

1. Let Scenario 1 or 3 complete (a force-push to `spec/NNN-slug` made
   through the App-token identity) — this doesn't push to `main`, so
   verify instead by simulating: push to `main` using the same App-token
   identity used by `speckit-context` (or inspect a real automation push
   to `main`, e.g. a merge performed by the bot, if one exists in the
   repo's history).
2. Expected: `discover`'s job-level `if: !endsWith(github.actor,
   '[bot]')` evaluates false — the run either doesn't start `discover` or
   it's visibly skipped in the Actions UI.

## Scenario 11 — Nightly schedule runs independent of push activity (US4 Acceptance Scenario 3, SC-005)

1. With no `main` push having occurred recently, manually fire the
   workflow the same way the `schedule` trigger would (`gh workflow run
   speckit-rebase.yml` or wait for `17 4 * * *` UTC).
2. Expected: the stage still runs and brings any in-flight branches that
   are behind `main` current, identical in effect to a push-triggered run
   (Scenario 1).

## Scenario 12 — Several in-flight branches, one escalates: isolation (US4, FR-010)

1. Set up at least two scratch specifications' `spec/NNN-slug` branches:
   one that will rebase cleanly, one that will hit an unresolvable
   conflict (Scenario 4's setup) against the same `main` advance.
2. Trigger the stage once.
3. Expected: the clean branch is rebased and pushed exactly as Scenario 1
   (check its job in the matrix run independently), and the conflicting
   branch is abandoned/escalated exactly as Scenario 4 — inspect both
   matrix job runs under the same workflow run and confirm neither's
   outcome depended on the other's (the escalating job's failure doesn't
   mark the whole workflow run in a way that hid or skipped the clean
   job).

## Scenario 13 — Lifecycle issue cannot be identified (spec.md edge case, FR-013)

1. Manually push a branch `spec/999-scratch-no-issue` whose
   `specs/999-scratch-no-issue/spec-meta.json` has `.issue` set to a
   nonexistent/invalid value (or `.spec_dir` deliberately mismatched),
   and give it a conflicting change against `main` so it would otherwise
   hit the abandon path.
2. Trigger the stage.
3. Expected: the branch is excluded at `discover` time (matches Scenario
   8's shape) with a `::warning::`/step-summary line explaining why
   (identity/self-consistency failure) — no comment is attempted on any
   issue, and the branch is left untouched.

See `contracts/rebase-workflow.md` for the exact trigger/job/step
contract each scenario above exercises, and `data-model.md` for the full
outcome table and escalation-marker format.
