# Quickstart: Validating the Auto-Update PR Guard

The fast, safe path is the executable harness
(`.github/scripts/auto-update-spec-kit-tests/run-tests.sh`) —
every scenario below has a corresponding assertion added there (FR-016,
contracts/auto-update-pr-guard.md's "Test-harness contract"), and it
runs against `gh_stub.py`/a scratch git repo, never against this
repository's real issues or PRs. The manual variants are for a
maintainer who wants to see the real GitHub UI behaviour once, against a
disposable fork or careful scratch labels — never against this
repository's real pinned version — mirroring
`specs/027-auto-update-spec-kit/quickstart.md`'s own caveat.

```sh
bash .github/scripts/auto-update-spec-kit-tests/run-tests.sh t7_gating
bash .github/scripts/auto-update-spec-kit-tests/run-tests.sh t5_act
bash .github/scripts/auto-update-spec-kit-tests/run-tests.sh   # full suite, also gated by lint-workflows.yml
```

## Scenario 1 — Settled candidate, matching open PR: guard fires (US1)

1. Stage an open PR whose body carries
   `<!-- wing-commander-auto-update-spec-kit: version-bump -->` and whose
   head branch is `auto-update-spec-kit/v$CANDIDATE` for the
   candidate `settle` has just settled on the tracking issue.
2. Dispatch the stage.
3. Expected: `evaluate-path`'s "Decide upgrade path" (the first
   Claude-billed step) never runs; `prepare`, `e2e-stage`, `verify`,
   `act` all report `skipped`; the run concludes green; the step summary
   and the tracking issue both name the candidate and the PR number
   (US1 Acceptance #1-#3, SC-001, SC-003).

## Scenario 2 — No matching open PR: proceeds exactly as today (US1 Acceptance #4)

1. No open PR carries the version-bump marker.
2. Dispatch the stage with a settled candidate.
3. Expected: `notes`/`decide`/`prepare`/`verify`/`act` all run exactly
   as `specs/027-auto-update-spec-kit/quickstart.md`'s existing
   scenarios describe — this feature changes nothing on this path.

## Scenario 3 — Maintainer reads the run without opening the Actions tab (US2)

1. After Scenario 1, read only the tracking issue (not the workflow run
   log).
2. Expected: the candidate version, the blocking PR number/link, and a
   plain statement that the run declined to act because that PR is
   awaiting review are all present, satisfying US2's "is this thing
   still working?" test (SC-003).

## Scenario 4 — Consecutive guarded runs: one narration, refreshed liveness marker (US2 Acceptance #4-#5, SC-007)

1. Dispatch the stage three times in a row against the same open PR
   (simulating three scheduled days).
2. Expected: exactly one narration comment exists on the tracking issue
   for that PR across all three runs; the issue body's `guard-checked`
   sub-field is a different (later) value after each run.

## Scenario 5 — A newer candidate settles behind an older open PR: queued, not blocked (FR-011)

1. An open version-bump PR proposes v0.16.4. Upstream releases v0.16.5,
   which `settle` observes and settles independently.
2. Dispatch the stage.
3. Expected: the guard still declines (at most one proposal in flight),
   but the narration on both the step summary and the tracking issue
   states v0.16.5 is queued behind PR #N (which proposes v0.16.4) —
   distinguishable from Scenario 1's "already proposes this candidate"
   wording (FR-003). The PR itself is never closed, retitled, or edited.

## Scenario 6 — The open-PR lookup itself fails: decline, not a red run (FR-010, Edge Cases)

1. Simulate a `gh pr list` failure (the harness's `GH_STUB_FAIL`
   mechanism; in the real world, a GitHub API outage or rate limit).
2. Dispatch the stage.
3. Expected: the run declines this cycle (same shape as Scenario 1's
   skip, different reason text: "the open-PR lookup failed"), concludes
   green, and does **not** proceed into the billed steps on the
   strength of an empty/absent result it cannot distinguish from "no
   matches."

## Scenario 7 — Resumed maintainer decision hits the identical guard (US3, Edge Cases)

1. `evaluate-path` previously posted an `ambiguous-options` question;
   while it awaits a reply, someone else opens a matching version-bump
   PR by hand (or a prior resolved run's PR is still open).
2. A maintainer replies, triggering `comment-reply` → resumed entry into
   `evaluate-path`.
3. Expected: the guard fires on this entry point exactly as it does on
   the fresh-settle entry point — the resumed path does not bypass it.

## Scenario 8 — PR merges: next run resumes with nothing to propose (US3 Acceptance #1)

1. Merge the open version-bump PR from Scenario 1.
2. Dispatch the stage again.
3. Expected: the pin now matches, `settle` finds no newer candidate
   eligible, no billed stage runs — the guard is not even reached, and
   no state needed clearing beforehand (FR-009).

## Scenario 9 — PR closes unmerged, branch deleted: full chain resumes (US3 Acceptance #2)

1. Close the PR from Scenario 1 without merging, and delete its branch.
2. Dispatch the stage again.
3. Expected: the guard finds no open PR and does not fire; the run
   proceeds through the full chain (`notes` through `act`) exactly as
   Scenario 2.

## Scenario 10 — PR closes unmerged, branch left behind: `act` declines loudly (US4, FR-015)

1. Close the PR from Scenario 1 without merging, but leave its branch
   (`auto-update-spec-kit/v$CANDIDATE`) on the remote.
2. Dispatch the stage again.
3. Expected: `evaluate-path`'s guard does not fire (no open PR); the
   chain runs through `verify`; `act`'s "Open version-bump PR" step
   declines — no push, no `gh pr create` — and its message names the
   branch and states the remedy (delete the branch, re-dispatch),
   distinct from a raw non-fast-forward push rejection. The job
   concludes as a success.

## Scenario 11 — `act` meets a pre-existing open PR directly (US4 Acceptance #2, defensive case)

1. Contrive a state where `verify` passes for a candidate whose branch
   already has an open PR (this should already be impossible in
   practice, since `evaluate-path`'s guard would have caught it — this
   scenario exercises `act`'s own check as a defense-in-depth backstop,
   not a reachable production path).
2. Expected: `act`'s check names the PR specifically (not just the
   branch), and still declines rather than double-opening or
   overwriting.

## Scenario 12 — Harness catches a weakened guard (US5, FR-016, SC-005)

1. Comment out (or otherwise disable) the guard step's `skip` output, or
   remove the `&& steps.guard.outputs.skip != 'true'` clause from
   `notes`/`decide`.
2. Run `t7_gating.py`.
3. Expected: at least one assertion fails, per SC-005 — the guard's
   presence is enforced by the harness, not only by documentation.
