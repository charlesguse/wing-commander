# v1.0.0 Release Checklist — remaining steps

Everything left between the current state of `feat/reusable-pipeline` and
publishing `v1.0.0`. Automated work (T001–T014, T016–T018, T020–T021,
T023–T031, T033–T034) is complete and live-tested; what remains is the
**MANUAL** validation from [tasks.md](tasks.md) plus the merge/release
mechanics. Steps are ordered — each unlocks the next.

Already verified on the branch (2026-07-11, in the private test repo
`charlesguse/speckit-pipeline-test` pinned `@feat/reusable-pipeline`):
Scenario 3 part 1 (no credentials → preflight failure naming both secrets,
zero agent cost), Scenario 3 part 2 (OAuth-only → stage completes; the haiku
intake runs produced PRs #2 and #4), Scenario 4 part 1 (no `specify init` →
deterministic refusal), and Scenario 5 step 1 (wrapper grep — no stage logic
in any `speckit-*.yml`). Three live bugs were found and fixed on the branch
(`e632888` pipeline-repo-token, `60a66b6` job_workflow_sha OIDC fallback,
`35c8292` PR #40 metrics port).

## 1. Merge `feat/reusable-pipeline` → `main`

- [x] Open a PR from `feat/reusable-pipeline` to `main` and merge it.
      *(PR #42, merged 2026-07-12. The merge's own push exposed a latent
      spec-008 bug — an empty `matrix.include` fails strategy evaluation, so
      the first push to main with zero `spec/*` branches failed the rebase
      run; fixed by a job-level skip guard, PR #43. Cleanup wrapper no-op'd
      cleanly on the same merge.)*

Nothing below can finish without this: `release.yml` tags from `main`, the
dogfood lifecycle (step 4) runs this repo's wrappers from `main`, and
Scenario 1's `@main` pin must resolve to the extracted workflows.

Notes:
- The branch already contains `main` (PR #40 merged in), so the PR should be
  a clean fast-forward-style merge.
- Merging this PR fires `speckit-7-cleanup.yml` (pull_request: closed) and
  `speckit-rebase.yml` (push to main) — both harmless no-ops for a
  non-lifecycle branch, and a free smoke test of the rewritten wrappers.

## 2. Scenario 1 — timed docs-only adoption (T015)

- [x] In a **fresh** test repo (or `speckit-pipeline-test` reset to empty
      workflows), start a timer and follow `docs/adoption.md` from its first
      line only — no prior knowledge, no shortcuts.
- [x] Pin the wrapper set `@main` (pre-release).
- [x] Open a small feature issue, apply the approval label.
- [x] **Pass**: spec PR built from the test repo's own templates, issue
      labeled `spec:NNN-slug` + `stage:spec`, elapsed < 60 min (SC-001).
- [x] Record elapsed time and outcome on the lifecycle issue.
      *(2026-07-12: reset repo → wrappers `@main` → labels → issue #5 →
      spec PR #6 (`spec-draft/001-add-credits-file`), elapsed **3m58s**
      (05:08:58–05:12:56Z). One documented deviation: `model:
      claude-haiku-4-5` on intake for test-repo cost control. The wrapper
      push also validated the empty-matrix rebase fix cross-repo.)*

Reminder (private-repo prerequisites, already in adoption.md): Actions
access policy is set on speckit-action; the test repo needs
`PIPELINE_REPO_TOKEN` (fine-grained PAT, Contents: read), `SPECKIT_APP_ID`,
`SPECKIT_APP_PRIVATE_KEY`, and one Claude credential — and secrets must be
set **on the calling repo** (workflow_call resolves them there).

## 3. Scenario 2 + Scenario 4 part 2 — single-stage adoption (T019)

- [x] In the test repo, delete all wrappers except one calling
      `reusable-plan.yml` with a custom `workflow_dispatch` trigger (e.g. a
      `slug` input) — no other stage, label, or lifecycle convention present.
- [x] Hand-write `specs/NNN-slug/spec.md` + `spec-meta.json` (stage `spec`)
      on the default branch; dispatch.
- [x] **Pass**: plan PR opens targeting `spec/NNN-slug`; nothing fails due to
      a missing sibling stage or label (SC-002).
- [x] Scenario 4 part 2: dispatch the **tasks** stage for a slug whose
      `spec-meta.json.stage` is not `plan`. **Pass**: refusal naming the plan
      stage as the missing predecessor (edge case 4).
- [x] Spirit-check the remaining stages against their contract preconditions
      (SC-002 claims 100% of stages); report on the lifecycle issue.
      *(2026-07-12: hand-written `specs/002-support-doc` + single
      `plan-only.yml` wrapper, stage-label taxonomy deleted from the repo →
      plan PR #8 into auto-created `spec/002-support-doc`, lifecycle issue
      #7 auto-created, `stage:plan` label created on the fly. Preparation
      found a real SC-002 defect: plan was the only stage adding a stage
      label without the create-before-add guard — fixed in PR #44 before
      the run. 4b: `tasks-only.yml` dispatch for the plan-less slug failed
      deterministically at the verify step, zero agent cost, message naming
      reusable-plan.yml.)*

## 4. Scenario 5 — full dogfood lifecycle (T032)

- [x] After the merge (step 1), run one full lifecycle **in this repo**:
      open issue → approval label → spec → clarify → plan → tasks →
      implement⟲converge → finalize → merge → cleanup.
- [x] **Pass**: every stage job executes inside a `reusable-*` called
      workflow — job names render as `wrapper / stage` (acceptance 3.1,
      SC-003).
- [x] Make one trivial stage-logic edit; confirm it touches exactly one file
      (`reusable-*.yml` or a composite) and reaches the test repo by moving
      its pin only (acceptance 3.2, SC-004).
- [x] Report on the lifecycle issue.
      *(2026-07-12: issue #45 "Add a SECURITY.md" ran intake → plan → tasks
      → implement (converged cycle 1, sonnet) → finalize (PR #50) → merge →
      cleanup teardown-done; issue closed `stage:done`, all branches
      deleted. Two runs surfaced real bugs first: a stale
      CLAUDE_CODE_OAUTH_TOKEN produced a **green** run on a 401 (fixed by
      the intake/clarify agent-error guard, PR #46) and every tasks trigger
      died in `startup_failure` because the tasks-approved wrapper job
      granted less than the called workflow file's union — GitHub validates
      even `if`-skipped jobs (fixed in wrapper + adoption doc, PR #49). One
      operational note: a rebase run raced the tasks agent's push when main
      moved mid-stage (pre-existing spec-008 design gap; re-dispatch
      recovered). Propagation check satisfied by PR #44 (one file,
      reached the test repo by pin alone).)*

A good candidate feature: something tiny and real (the haiku smoke tests
used a THANKS.md file). This run doubles as the first end-to-end exercise of
the ported metrics guards across all eight stages.

## 5. Scenario 6 — tag pinning, then publish v1.0.0 (T035)

Requires steps 1–4 green (release gate per tasks.md).

- [x] Publish a pre-1.0 release via `release.yml` (workflow_dispatch, e.g.
      `v0.9.0`) — this also exercises the actionlint + invariant-grep gate.
- [x] Pin the test repo to the exact tag `v0.9.0`; publish a non-breaking
      `v0.9.1`. **Pass**: test repo behavior unchanged until the pin moves
      (edge case 2).
- [x] Switch the test repo to `@v0`; publish another non-breaking patch.
      **Pass**: next run picks up the fix with zero changes in the test repo
      (acceptance 1.2).
- [x] Inspect release notes. **Pass**: explicit Breaking-changes section
      present even when "none" (FR-008).
- [x] Publish `v1.0.0` via `release.yml`; confirm the floating `v1` tag is
      created and `docs/adoption.md`'s `@v1` pins now resolve.
- [x] Report on the lifecycle issue; mark T015/T019/T022/T032/T035 `[X]` in
      tasks.md.
      *(2026-07-12: first v0.9.0 attempt failed the gate on style/info
      shellcheck findings — gate now blocks warning+ only (PR #51). v0.9.0
      → exact-pin baseline; v0.9.1 (PR #52's one-line discover-log change)
      → pinned run stayed on the old sha, floating `@v0` picked the change
      up with zero repo edits; both releases' notes lead with "Breaking
      changes: None." **v1.0.0 published** (run 29199119335), `v1` floating
      tag created, and the canary repo's full doc wrapper set now runs
      green at `@v1`. T022's OAuth-only leg additionally re-verified by the
      whole dogfood lifecycle running on CLAUDE_CODE_OAUTH_TOKEN alone.)*

## 6. Post-release housekeeping (not release blockers)

- [ ] Tear down the scratch repo `charlesguse/speckit-pipeline-test` (or keep
      it as the standing adoption canary — recommended for Scenario 6 pin
      tests on future releases).
- [ ] Close the spec 010 lifecycle issue via the normal finalize/cleanup path
      (or manually if 010 was implemented outside the pipeline).
- [ ] Decide whether the repo stays private; if it ever goes public, the
      `pipeline-repo-token` secret becomes optional for adopters and
      docs/adoption.md's "Private pipeline repository" section should be
      demoted to a note.
- [ ] Backlog carried over from spec 009/cleanup reviews (pre-existing, not
      010 regressions): cleanup teardown idempotency on already-deleted
      branches; mid-step idempotency markers; stale stall-runbook anchor;
      lint-workflows.yml doesn't lint composite actions.
