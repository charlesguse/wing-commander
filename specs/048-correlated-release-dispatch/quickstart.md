# Quickstart: validating correlated, atomic release dispatch

These scenarios exercise the two independent guarantees this feature
adds, matching spec.md's Story 1 and Story 2 Independent Tests. Both
require a maintainer able to dispatch workflows on this repository
(`actions: write` is already what `dispatch-release` needs) and are
written to run against a real (or forked/test) copy of this repository
— they are not unit tests, since the subject is cross-workflow
coordination in GitHub's own Actions infrastructure.

## Prerequisites

- `gh` authenticated against the target repository.
- `.github/workflows/release.yml` and `.github/workflows/auto-release.yml`
  carrying this feature's changes (see `release-handover-contract.md`).
- A version that is not already an existing tag (so the scenarios below
  do not collide with real release history) — use a throwaway low patch
  number on a fork, or coordinate with whoever owns tagging on the real
  repository.

## Scenario 1 — an automatic attempt never adopts a foreign run (Story 1)

Proves FR-001–FR-006: correlation is by evidence, not recency.

1. Dispatch a manual release first, so a `release.yml` run already
   exists when the automatic path looks:
   ```
   gh workflow run release.yml -f version=v0.0.1-test1 -f breaking=false -f breaking-notes=
   ```
2. Within the same minute, trigger `auto-release.yml` (or run its
   `dispatch-release` job in isolation against a test fixture that lets
   `decide-version` compute a *different* version, e.g. `v0.0.1-test2`,
   so the two dispatches are clearly distinguishable in the run list):
   ```
   gh workflow run auto-release.yml
   ```
3. **Expected**: `gh run list --workflow=release.yml --json
   displayTitle` shows two runs — `release v0.0.1-test1 [attempt:]` (the
   manual one) and `release v0.0.1-test2 [attempt:<token>]` (the
   automatic one). The automatic attempt's own report (the
   `$GITHUB_STEP_SUMMARY` of its `report` job, or the standing
   `auto-release:failed` issue if it filed one) names and links only the
   `[attempt:<token>]` run — never the manual one — regardless of which
   run happens to finish first.
4. **Also confirm** (Acceptance Scenario 4): re-run step 2 a second time
   requesting the *same* version as a still-open, un-tagged earlier
   attempt (simulate by not letting the first automatic attempt's tag
   land — e.g., dispatch it with a `commit` input that will fail the
   tag-time check). The second attempt's correlation search must not
   adopt the first attempt's run — confirm by checking the second
   attempt's report links a *different* `databaseId` than the first.

## Scenario 2 — a tag only ever lands on the verified head (Story 2)

Proves FR-009–FR-014: the tag-time refusal, evaluated live.

1. Note the current tip of `main`: `git rev-parse origin/main`.
2. Dispatch `release.yml` directly, naming that commit and a throwaway
   version, but with a deliberately-stale `commit` input (any commit
   that is *not* the current tip — the previous commit works):
   ```
   gh workflow run release.yml \
     -f version=v0.0.1-test3 -f breaking=false -f breaking-notes= \
     -f commit=<a commit that is not the current tip> \
     -f attempt-token=quickstart-manual-test
   ```
3. **Expected**: the run fails at the tag-time comparison step (after
   Gate 1a/1b and version validation have already passed), with an
   `::error::` line naming both the commit requested and the tip
   observed. `git tag --list v0.0.1-test3` and `git tag --list v0.0.1`
   (the floating major) both show nothing new — no tag, no release
   published.
4. **Then confirm the positive case**: re-dispatch with `commit` set to
   the actual current tip of `main`:
   ```
   gh workflow run release.yml \
     -f version=v0.0.1-test3 -f breaking=false -f breaking-notes= \
     -f commit=$(git rev-parse origin/main) \
     -f attempt-token=quickstart-manual-test2
   ```
   **Expected**: the release proceeds and `v0.0.1-test3` is tagged
   exactly on that commit — `git rev-parse v0.0.1-test3^{commit}` equals
   the commit supplied.
5. **Also confirm the queueing case** (Edge Cases: "the advance happened
   while the request sat queued"): dispatch two `release.yml` runs back
   to back with the same valid `commit`, so the second sits behind the
   first in the `wing-commander-release` concurrency group; merge a
   trivial commit to `main` while the first run is still executing. The
   second run — which started with a still-valid `commit` — must refuse
   once it reaches the tag-time check, because the live re-read at that
   moment (not at dispatch time) now disagrees.

## Scenario 3 — the manual path is unchanged (Story 3)

1. Dispatch `release.yml` supplying only `version`, `breaking`, and
   `breaking-notes` — the three inputs that existed before this
   feature.
2. **Expected**: identical behavior to before this feature shipped — the
   branch tip is tagged, no new refusal fires, and the run's title is
   `release <version> [attempt:]` (cosmetic only; nothing reads or acts
   on the empty bracket).

## Scenario 4 — the deterministic gate catches a reverted guarantee (FR-018)

```
python3 .github/scripts/verify-correlated-release-dispatch.py --self-test
```

**Expected**: every self-test fixture passes, including the four
mutation fixtures (recency-based selection, dropped token, dropped
tag-time refusal, run-conclusion-based reporting) each failing with a
message naming only its own FR-018 clause. Then:

```
python3 .github/scripts/verify-correlated-release-dispatch.py
```

**Expected**: passes against the real, shipped
`.github/workflows/release.yml` and `.github/workflows/auto-release.yml`.
This is also exercised by `python .github/scripts/run-local-gates.py`,
which derives its gate list from `lint-workflows.yml` and needs no
separate wiring for this new gate.
