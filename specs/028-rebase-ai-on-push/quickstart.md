# Quickstart: Validating Auto-Rebase AI Conflict Resolution on Push

Prerequisites: `gh` authenticated as a maintainer against this repository,
and a scratch specification with a `spec/NNN-slug` working branch already
created (past the plan stage), so there's a real branch to conflict and
rebase — same prerequisite `specs/008-auto-rebase/quickstart.md` uses.
FR-012 requires this feature's core fix (Scenario 1) to be validated
against a genuine induced conflict, not inferred from source — do not skip
it.

## Scenario 1 — Push-triggered conflict reaches and is resolved by the agent (US1, SC-001, SC-002)

1. Advance `main` with a commit that edits the same lines a scratch spec's
   `spec/NNN-slug` branch already changed, in a way a competent editor
   could reconcile (mirrors `specs/008-auto-rebase/quickstart.md` Scenario
   3's setup) — push it directly to `main` so `wing-commander-rebase.yml`'s
   `push` trigger fires.
2. In the Actions run list, confirm two runs appear in sequence: a
   `redispatch`-only run (fast, `push`-triggered, no `rebase.yml` jobs) and
   a second `workflow_dispatch`-triggered run of the same wrapper that
   contains `rebase.yml`'s `discover`/`rebase` jobs.
3. In the second run's `rebase` matrix job, confirm the "Resolve conflicts"
   step (the `claude-code-action` step) actually executes and completes —
   not "Unsupported event type: push," not skipped.
4. Expected, with zero manual steps: `spec/NNN-slug`'s tip is a rebase of
   its prior work onto the new `main` tip, force-pushed by the pipeline;
   `git diff` between the resolved commit and its pre-rebase original,
   restricted to files outside the ones that actually conflicted, is empty
   (the existing scope check, unaffected by this feature); no lifecycle-issue
   comment (only the abandon path comments).

**Expected**: SC-001 and SC-002 hold — this is the feature's core proof:
a real, deliberately induced conflict on the affected push path is resolved
automatically end-to-end.

## Scenario 2 — Same conflict, schedule-triggered: identical outcome (US1 Acceptance Scenario 3, FR-002)

1. Set up an equivalent conflicting scratch branch (or reuse Scenario 1's
   setup pattern against a fresh scratch spec).
2. Trigger the stage via the schedule path instead of push — either wait
   for `17 4 * * *` UTC or manually invoke the wrapper with
   `github.event_name` forced to `schedule` (not available via `gh workflow
   run`, which always produces `workflow_dispatch` — if a live schedule
   firing isn't practical within the validation window, Scenario 3's
   `workflow_dispatch` path is an acceptable equivalence proxy, since both
   are on Gate 6's supported list and the `rebase` job's `if:` treats them
   identically).
3. Expected: identical outcome shape to Scenario 1 — the agent step runs
   and resolves the conflict, with no trigger-dependent difference in
   whether the attempt is made or how it behaves.

**Expected**: FR-002 holds — one resolution path serving both triggers.

## Scenario 3 — Manual `workflow_dispatch` reaches the agent directly (contracts/rebase-wrapper-delta.md)

1. Run `gh workflow run wing-commander-rebase.yml --ref main` directly
   (not via a push).
2. Expected: the `rebase` job's `if:` admits `workflow_dispatch`
   immediately — no `redispatch` job runs (its `if:` requires
   `github.event_name == 'push'`), and the run goes straight to
   `rebase.yml`'s `discover`/`rebase` jobs.

**Expected**: Confirms the `rebase` job's allow-list `if:` (research.md R5)
behaves as documented for a genuinely manual dispatch, not only for a
`redispatch`-originated one.

## Scenario 4 — The safety fallback is unchanged when the AI cannot resolve (US3, SC-003)

1. Advance `main` with a commit that conflicts with a scratch branch in a
   way that's genuinely ambiguous or contradictory (mirrors
   `specs/008-auto-rebase/quickstart.md` Scenario 4), and push it to `main`
   so the `push` → `redispatch` → `workflow_dispatch` path is exercised.
2. Expected, identical to today's pre-fix behavior: `spec/NNN-slug`'s tip
   is byte-for-byte unchanged from before the run (no half-rebased state,
   no force-push of any kind); the lifecycle issue gets a new comment and
   the `rebase:blocked` label, carrying the same
   `<!-- wing-commander-rebase: blocked ... -->` marker format as before.

**Expected**: FR-004, FR-005, SC-003 hold — the abandon+escalate path is
now reached *after* a genuine resolution attempt on the push path (rather
than being the only path), and its own behavior is completely unchanged.

## Scenario 5 — Bot-authored push does not redispatch (loop guard, research.md R4)

1. Let Scenario 1 complete (a force-push to `spec/NNN-slug` through the App
   identity) — this doesn't push to `main`, so verify instead by inspecting
   any real automation push to `main` made by the App identity in this
   repository's history, or simulate one.
2. Expected: `redispatch`'s `if: github.event_name == 'push' &&
   !endsWith(github.actor, '[bot]')` evaluates false — no `redispatch` run
   starts (or it's visibly skipped), and consequently no second
   `workflow_dispatch` run is queued from it.

**Expected**: The loop guard's behavior is preserved exactly, just
relocated to the `redispatch` job (data-model.md).

## Scenario 6 — Gate 6 catches the original defect shape (US2, FR-008, FR-011)

1. On a throwaway branch, reintroduce the pre-fix shape: change
   `wing-commander-rebase.yml`'s `rebase` job `if:` back to
   `!endsWith(github.actor, '[bot]')` (no `event_name` clause) while
   `on:` still declares `push`.
2. Open a pull request from that branch.
3. Confirm `lint · workflows` → `lint` job fails with an `::error`
   annotation naming `wing-commander-rebase.yml`, the `rebase` job, and
   `push` as the unsupported reachable event.
4. Revert; confirm the same PR's `lint` job now passes.

**Expected**: SC-004 holds for the exact defect this feature fixes; Gate 6
would have caught it before merge.

## Scenario 7 — Gate 6 is forward-looking, not push-specific (US2 Acceptance Scenario 4, FR-010)

1. On a throwaway branch, add a different, clearly-unsupported event (e.g.
   `create` or `release`) to an agent-bearing wrapper's `on:` block with no
   `if:` restricting it (any wrapper works — e.g. add
   `create: {}` to `wing-commander-1-intake.yml`, which calls
   agent-bearing `intake.yml`).
2. Open a pull request.
3. Confirm the `lint` job fails, naming that wrapper and `create` — not a
   hard-coded check for `push` specifically.
4. Revert; confirm it passes again.

**Expected**: Confirms Gate 6's allowlist design (research.md R6) rather
than a `push`-only denylist.

## Scenario 8 — A wrapper with only supported events passes (US2 Acceptance Scenario 2)

1. Inspect (no PR needed) any of `wing-commander-1-intake.yml` through
   `wing-commander-8-watchdog.yml` and `wing-commander-auto-update-spec-kit.yml`
   in their current, unmodified form.
2. Run Gate 6's check logic (contracts/workflow-lint-gate-6.md) against the
   repository as-is.

**Expected**: Zero failures — every wrapper other than
`wing-commander-rebase.yml`'s pre-fix shape already declares only events on
the supported list (data-model.md Supported-Event Set table), confirming
SC-005 (no other agent-bearing wrapper's behavior or lint status changes).

## Scenario 9 — A wrapper with no agent step is never flagged regardless of events (US2 Acceptance Scenario 3)

1. Inspect `wing-commander-8b-watchdog-self.yml` — it has no
   `uses: ./.github/workflows/*.yml` job at all (it's deterministic,
   research.md/docs/architecture.md), so Gate 6 never evaluates it.
2. (Optional, more direct test) On a throwaway branch, add an unsupported
   event (e.g. `push`) to a wrapper whose resolved stage has **no**
   `claude-code-action` step, if one exists, or construct a minimal
   scratch wrapper/stage pair with no agent step for this test only.
3. Open a pull request.

**Expected**: The `lint` job passes — `is_agent_bearing` gates the entire
check, so a wrapper with no agent-bearing resolved stage is never
evaluated for its event set (spec Acceptance Scenario 3).

See `contracts/rebase-wrapper-delta.md` for the exact wrapper YAML delta
each of Scenarios 1–5 exercises, and `contracts/workflow-lint-gate-6.md`
plus `data-model.md`'s Job Reachable-Event Set section for the exact gate
logic Scenarios 6–9 exercise.
