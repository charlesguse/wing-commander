# Feature Specification: Auto-Update Declines to Re-Propose a Candidate Whose PR Is Already Open

**Feature Branch**: `035-auto-update-pr-guard`

**Created**: 2026-08-16

**Status**: Draft

**Input**: User description: "auto-update-spec-kit re-proposes a candidate whose PR is already open, burning two Claude stages a day and failing act. Nothing in `auto-update-spec-kit.yml` asks 'have I already done this?'. While a version-bump PR sits unmerged, every scheduled run repeats the entire adoption pipeline — including two Claude-billed stages — and then fails at `act`, because the branch it wants to push already exists. This is live as of PR #203 (v0.16.4). The pin on `main` only moves when the PR merges, so until then `detect` keeps finding the same candidate eligible, and `settle` has no latch — once the candidate has been observed enough times it reports `settled=true` on every subsequent run. So the run proceeds through `evaluate-path` (one `claude-sonnet-5` judgment call), `prepare`, `e2e-stage` (a full agent-driven run against the scratch repository), and `verify` — all of which succeed and all of which are thrown away. `act`'s branch name is a pure function of the candidate version (`auto-update-spec-kit/v$CANDIDATE`), and `prepare` rebuilds the commit fresh from the default branch each run, so the new commit is a sibling of the one already on the remote branch, never a descendant. That push is rejected non-fast-forward, and `set -euo pipefail` ends the step there. A forced push alone would not fix this: the very next command is a plain `gh pr create` with no existing-PR handling, which exits non-zero with 'a pull request for branch … already exists'. Forcing the push moves the failure one command later, and costs the guarantee that the pipeline never overwrites a branch someone is reviewing. Cost per day, per open version-bump PR: one `evaluate-path` Claude call, one `e2e-stage` agent run, a scratch-repository force-push, and a red run in the Actions tab that means nothing is wrong. Proposed fix: guard on an already-open PR before `evaluate-path`, since that is the first billed step — look for an open PR carrying `<!-- wing-commander-auto-update-spec-kit: version-bump -->` whose title/branch names the current candidate; if one exists, no-op: record it on the tracking issue and in the step summary ('v0.16.4 already has an open PR #203 awaiting review'), and skip the rest of the chain. `pr-merged` already fires when such a PR closes, so the next run resumes naturally with no state to clear. Same shape as `implement`'s iteration idempotency guard. On force-pushing, if it is wanted as well: there is a coherent combined policy — guard when a PR is open, force when one is not. A branch only survives without an open PR if a previous run failed or the PR was closed — in both cases nothing is under review, so forcing is safe by construction, and it removes the manual 'delete the branch before re-dispatching' step that closing #201 required. The guard is the part that saves the quota; forcing is only a convenience on top of it. Alternatives considered: unique branch per run (append run id) — fixes the collision, but opens a duplicate PR every morning and does nothing about the wasted stages; force-push and update the existing PR in place — keeps the PR current, but still pays for a full pipeline run daily to do it. Test coverage: `t9_prepare.sh` (added in #202) covers `prepare`'s commit; `t5_act.sh` covers `act`'s push and PR creation against the `gh` stub. Neither has a scenario where the target branch or PR already exists — the guard should land with one on each side, plus the `t7_gating.py` routing assertion for the new skip. Repro: leave PR #203 open, dispatch the workflow, every job succeeds through `verify`, and `act`'s 'Open version-bump PR' step fails at the push."

## Clarifications

### Session 2026-08-16

- Q: Does this feature ship the open-PR guard alone, or the guard plus the combined "force-push when no PR is open" policy? → A: Guard now; force-push filed as a follow-up issue against this spec. Ships the quota fix with the narrowest review surface and lets the overwrite-policy change be judged on its own once the guard is proven in production.
- Q: How often should a guarded (skipped) run record itself on the tracking issue? → A: Refresh the issue body every run with a last-checked marker, and comment once when the skip first starts — one-time human-readable narration plus per-run liveness evidence.
- Q: What should happen when an open version-bump PR proposes a candidate *other than* the one that has just settled? → A: Skip as well — at most one version-bump proposal in flight at a time — and note on the tracking issue that a newer candidate is queued behind the open PR.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A settled candidate that already has an open PR costs nothing (Priority: P1)

The scheduled auto-update runs while a version-bump PR for the current candidate is sitting open and unreviewed. Before any Claude-billed work begins, the run asks whether it has already proposed this candidate. It finds the open PR, does nothing further, and ends successfully. No judgment call is made, no scratch-repository stage is driven, no branch is pushed, and the pinned version is untouched.

**Why this priority**: This is the entire cost of the defect. Every day a version-bump PR waits for review, the project pays for one `claude-sonnet-5` judgment call and one agent-driven end-to-end stage whose results are thrown away, and the run ends red for a reason that is not a problem. The guard placed before the first billed step eliminates the whole bill on its own, without any other part of this feature landing.

**Independent Test**: With an open version-bump PR carrying this feature's marker for the settled candidate, trigger the workflow and confirm that the billed judgment and end-to-end stages never start, that no branch is pushed to the consumer repository, and that the run concludes successfully.

**Acceptance Scenarios**:

1. **Given** a candidate that has settled and an open pull request this feature opened proposing that same candidate, **When** the scheduled run reaches the point where it would begin its judgment step, **Then** it stops there — the judgment step, the preparation step, the end-to-end stage, the verification step, and the PR-opening step all do not run.
2. **Given** the same situation, **When** the run finishes, **Then** it is reported as a success, not a failure.
3. **Given** the same situation, **When** the run finishes, **Then** the pinned Spec Kit version, the existing PR, its branch, and the tracking issue's settle state are all exactly as they were before the run.
4. **Given** no open version-bump pull request from this feature at all, **When** the run reaches the same point, **Then** it proceeds through the full adoption chain exactly as it does today.

---

### User Story 2 - A maintainer can tell at a glance why nothing happened (Priority: P1)

A maintainer looks at the Actions tab, or at the tracking issue, after a guarded run. The run tells them plainly that the candidate already has an open PR awaiting review, naming the version and the pull request, so that "the pipeline did nothing today" reads as a deliberate decision rather than as a stall or a silent failure.

**Why this priority**: A no-op that is indistinguishable from a broken schedule is barely better than the red run it replaced. The project's operating principle is that the lifecycle of any automated decision is legible from the issue alone. This is separately testable from US1 and delivers the "is this thing still working?" answer that makes the guard trustworthy.

**Independent Test**: Trigger a guarded run and confirm that, reading only the run's step summary — and separately, reading only the tracking issue — a maintainer can state which candidate version was skipped, which pull request it is waiting on, and that the skip was intentional.

**Acceptance Scenarios**:

1. **Given** a guarded run, **When** the step summary is read, **Then** it names the candidate version and the pull request number, and states that the run declined to act because that PR is awaiting review.
2. **Given** a guarded run, **When** the tracking issue is read, **Then** it records the same fact, with a link to the open pull request.
3. **Given** a maintainer with no access to the run logs, **When** they read only the tracking issue, **Then** they can tell whether the pipeline is waiting on them or on itself.
4. **Given** consecutive guarded runs for the same candidate and the same pull request, **When** the tracking issue is read after several days, **Then** exactly one narration entry exists for that skip — written when the skip first started — and the issue body carries a last-checked marker refreshed by the most recent run, so nothing accumulates per run but today's run is still visible (per FR-007).
5. **Given** a guarded run whose last-checked marker is days old, **When** a maintainer reads the tracking issue, **Then** they can tell the schedule has stopped firing without opening the Actions tab.

---

### User Story 3 - Work resumes on its own once the PR is resolved (Priority: P2)

The maintainer merges (or closes) the open version-bump PR. On its next scheduled run, the pipeline resumes normal behaviour with no state to clear: if the PR merged, the pin has moved and there is nothing to propose; if it was closed unmerged, the candidate is still eligible and the pipeline proceeds through the full chain again — with the pre-existing caveat that a branch left behind by the closed PR still has to be deleted before that chain can complete (scenario 4).

**Why this priority**: A guard that requires a human to clear a latch afterwards trades one manual step for another. This must hold for the guard to be a net improvement, but it is only observable after US1 exists, so it is P2.

**Independent Test**: With a guarded run recorded, resolve the PR (once by merging, once by closing unmerged) and confirm the next run behaves correctly in each case without any human touching state.

**Acceptance Scenarios**:

1. **Given** the open version-bump PR is merged, **When** the next scheduled run happens, **Then** the pinned version now matches upstream, no candidate is eligible, and no billed stage runs.
2. **Given** the open version-bump PR is closed without merging *and its branch deleted*, **When** the next scheduled run happens, **Then** the candidate is still eligible and the run proceeds through the full adoption chain.
3. **Given** either resolution, **When** the next run happens, **Then** no state clearing, latch reset, label removal, or issue edit was required beforehand — the guard reads the pull request's own open/closed state and nothing else.
4. **Given** the PR is closed without merging and its branch is left behind, **When** the next scheduled run happens, **Then** the run proceeds through the chain and the PR-opening step declines with the FR-015 message naming that branch. This residual manual step is the one the deferred force-push follow-up would remove (see Out of Scope).

---

### User Story 4 - A leftover branch fails loudly and legibly, not cryptically (Priority: P3)

A branch from a previous run survives with no open pull request behind it — because the run failed after pushing, or because the PR was closed. The pipeline still refuses to overwrite it: the PR-opening step stops, but it stops with a message naming the branch that blocked it and telling the maintainer to delete that branch before re-dispatching, instead of surfacing a raw non-fast-forward push rejection.

**Why this priority**: The guard is the fix; this is the diagnosis quality of the failure that remains once the guard has removed the daily cost. Overwriting a leftover branch — the "force when no PR is open" convenience the source issue floated — is **out of scope for this feature** (see Out of Scope) and is filed as a follow-up so that the change to what the pipeline may overwrite is reviewed on its own once the guard is proven in production.

**Independent Test**: Leave a branch named for the candidate on the consumer repository with no open PR pointing at it, run the chain through to the PR-opening step, and confirm it fails with a message that names the branch and the remedy. Separately confirm that a branch *with* an open PR is never reached by this path, because US1's guard stopped the run long before.

**Acceptance Scenarios**:

1. **Given** a branch for the candidate exists on the consumer repository and no open pull request from this feature references it, **When** the run reaches the PR-opening step, **Then** the step declines to write and reports which branch blocked it and that a maintainer must delete that branch before re-dispatching. The branch's contents are not overwritten.
2. **Given** an open pull request from this feature exists for the candidate, **When** the run happens, **Then** the branch behind it is never rewritten, because the run stopped at the guard.
3. **Given** the PR-opening step encounters a state it will not overwrite, **When** it stops, **Then** the message states which branch or pull request blocked it and what a maintainer should do, rather than surfacing only a raw push rejection.

---

### User Story 5 - The guard is asserted by the executable harness (Priority: P3)

The workflow's executable scenario harness gains coverage for the states nobody had scripted: a target branch that already exists, a pull request that already exists, and the routing decision that skips the billed stages. A future edit that removes or weakens the guard fails a check instead of surviving until the next unreviewed PR.

**Why this priority**: The defect exists because the "already done this" state was never a scenario. Coverage is what stops it recurring, but it delivers nothing on its own if US1 has not landed, so it is P3.

**Independent Test**: Run the workflow's scenario harness and confirm it exercises, and can fail on, each of: the guard skipping the chain when a matching PR is open, the chain proceeding when none is open, the PR-opening step meeting a pre-existing branch, and the PR-opening step meeting a pre-existing pull request.

**Acceptance Scenarios**:

1. **Given** the scenario harness, **When** it runs against the guarded workflow, **Then** it asserts both the skip and the proceed routing decisions.
2. **Given** the scenario harness, **When** it runs, **Then** it covers the PR-opening step against a pre-existing branch and against a pre-existing pull request.
3. **Given** a change that removes the guard, **When** the harness runs, **Then** at least one check fails.

---

### Edge Cases

- **The open-PR lookup itself fails** (API error, rate limit): whether a PR exists is then *unknown*. Proceeding on "unknown" is the expensive, failing branch, so the run does nothing this cycle and says so — the same "don't know means don't act" discipline the settle step already applies to its tracking-issue lookup.
- **More than one open pull request from this feature proposes the same candidate**: a data-integrity condition. The guard still declines to act and names every matching PR rather than silently choosing one.
- **An open version-bump PR proposes an *older* candidate than the one that has now settled** (upstream released again while the first PR waited): the run still declines to act — at most one version-bump proposal is in flight at a time — and the tracking issue says that the newer candidate is queued behind the open PR, so the wait reads as a queue rather than a stall. See FR-011.
- **A revert pull request from this feature is open**: reverts carry a different marker and a different meaning; an open revert is not evidence that this candidate has already been proposed.
- **The open PR is a draft**: still open, still awaiting a human, so it still guards.
- **The open PR's branch was deleted while the PR stayed open**: the PR is the thing under review, so the guard holds on the PR alone.
- **The maintainer-decision resume path** (a maintainer answering an ambiguous-options question re-enters the chain at the same billed step): the identical collision awaits it, so the guard covers this entry point too and reports back on the issue rather than silently swallowing a deliberate human action.
- **The candidate settled but no PR was ever opened because a prior run failed mid-chain**: no open PR, so the run proceeds — this is exactly the retry the schedule exists to provide. If that prior run failed *after* pushing its branch, the retry still stops at the PR-opening step with FR-015's message; unblocking it is a branch deletion, and removing even that step is the deferred follow-up (Out of Scope).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Before any Claude-billed step of the auto-update chain begins, the run MUST determine whether this feature already has an open version-bump pull request, and which candidate version that pull request proposes.
- **FR-002**: The check MUST recognise such a pull request by this feature's own version-bump marker in the PR body, never by title or branch name alone — the same self-recognition discipline the merge-handling path already applies, so a PR this feature did not open can never be mistaken for one it did.
- **FR-003**: The check MUST associate a matching open pull request with the specific candidate version it proposes, so that the run can distinguish "the candidate that just settled is already proposed" from "a *different* candidate is proposed and this one is queued behind it". Both outcomes decline to act (FR-011), but they MUST be narrated as the distinct situations they are.
- **FR-004**: When such an open pull request exists — whether it proposes the settled candidate or an earlier one — the run MUST skip the judgment, preparation, end-to-end, verification, and PR-opening steps entirely.
- **FR-005**: A run that skips for this reason MUST conclude as a success.
- **FR-006**: A skipped run MUST record, in the run's own summary, the candidate version, the identity of the open pull request, and that the skip was a deliberate decision to wait for review.
- **FR-007**: A skipped run MUST record the same fact on the tracking issue, with a link to the open pull request, on the following cadence: a narration entry is written **once**, the first time a given pull request is observed as the reason to skip; and the tracking issue's body carries a **last-checked marker that every guarded run refreshes**, naming the candidate, the pull request, and when the guard last confirmed it. No guarded run may add a second narration entry for a pull request already narrated, however long it stays open.
- **FR-008**: A skipped run MUST NOT change the pinned Spec Kit version, the existing pull request or its branch, the tracking issue's settle counter, or any label that gates the chain.
- **FR-009**: When the open pull request is subsequently merged or closed, the next scheduled run MUST resume correct behaviour with no manual state clearing — no latch to reset, no label to remove, no issue edit. The guard MUST hold no state of its own beyond what it reads from the pull request. (A branch left behind by a PR closed unmerged still has to be deleted before the chain can complete, per FR-015 and Out of Scope; that is a pre-existing behaviour this feature does not change.)
- **FR-010**: If the open-pull-request check cannot complete, the run MUST NOT proceed into the billed steps; it MUST decline to act for that cycle and say so visibly, so that a broken lookup degrades into a cheap no-op rather than into a daily bill.
- **FR-011**: When an open version-bump pull request from this feature exists for a candidate *other than* the one that has just settled, the run MUST skip as well: at most one version-bump proposal is in flight at a time. It MUST record on the tracking issue and in the run summary that the newer candidate is queued behind the open pull request, naming both versions and that pull request, so that the wait is legible as a queue rather than a stall. The run MUST NOT close, retitle, or otherwise modify the superseded pull request.
- **FR-012**: The guard MUST apply to every entry point into the billed chain, including a resumed maintainer decision, and MUST report the skip back to the maintainer on that path rather than ending silently.
- **FR-013**: The guard MUST distinguish this feature's version-bump pull requests from its revert pull requests; an open revert MUST NOT be treated as evidence that the candidate has already been proposed.
- **FR-014**: When more than one open pull request from this feature matches the candidate, the run MUST decline to act and MUST name every match, rather than choosing one.
- **FR-015**: The PR-opening step MUST NOT overwrite a pre-existing branch or pull request. When it declines to write, its message MUST name the blocking branch or pull request and state the remedy a maintainer should apply, rather than surfacing only a transport-level rejection.
- **FR-016**: The repository's executable scenario harness for this workflow MUST cover: the skip routing decision, the proceed routing decision, the PR-opening step against a pre-existing target branch, and the PR-opening step against a pre-existing pull request. The latter two MUST assert the declines-with-an-actionable-message behaviour of FR-015. Each MUST be able to fail.
- **FR-017**: The pipeline MUST NOT resolve the collision by proposing the same candidate on a per-run branch, which would open a duplicate pull request on every scheduled run.
- **FR-018**: This feature MUST NOT introduce any force-push or other overwrite of an existing branch on the consumer repository (see Out of Scope).

### Key Entities

- **Candidate version**: the upstream Spec Kit version currently under consideration; already settled and eligible before the guard is consulted.
- **Version-bump pull request**: a pull request this feature opened proposing a specific candidate, identified by its embedded version-bump marker, and carrying the candidate version it proposes. Its open/closed state is the sole latch this feature reads.
- **Tracking issue**: the single open issue that holds the settle state and the human-readable narration of every decision this feature makes.
- **Version-bump branch**: the branch a proposal is pushed to, named deterministically from the candidate version, so two runs for the same candidate target the same branch.

## Out of Scope

- **Force-pushing the version-bump branch when no pull request is open.** The source issue's combined "guard when a PR is open, force when one is not" policy is deliberately deferred: this feature ships the guard, which is the part that saves the quota, and the overwrite-policy change is filed as a **follow-up issue against this spec** so it can be judged on its own once the guard is proven in production. Until then, a leftover branch remains a hard stop that a maintainer clears by deleting the branch (FR-015, FR-018, US4).
- **Any change to what the pipeline is permitted to overwrite on the consumer repository.** The guarantee that it never rewrites an existing branch is unchanged by this feature.
- **Closing, retitling, or otherwise editing a superseded version-bump pull request** when a newer candidate settles. The pipeline queues behind it (FR-011) and leaves the human's review surface alone.
- **Any new state store, label, or event subscription.** The pull request's own open/closed state is the only latch.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: While a version-bump pull request for the current candidate stays open, scheduled runs consume zero Claude-billed stages for that candidate — down from two per run, every day the PR waits.
- **SC-002**: Over any window in which a version-bump pull request is open and no other defect is present, the number of failed scheduled auto-update runs is zero.
- **SC-003**: A maintainer reading only the run summary can state, in under one minute, which candidate was skipped and which pull request the pipeline is waiting on.
- **SC-004**: Resuming after the open pull request is merged requires zero manual steps; resuming after it is closed unmerged requires at most deleting its leftover branch, and nothing else.
- **SC-005**: Removing the guard causes at least one scenario-harness check to fail.
- **SC-006**: No scheduled run overwrites any pre-existing branch on the consumer repository — whether or not a pull request is open against it.
- **SC-007**: However many consecutive days a version-bump pull request stays open, the tracking issue gains exactly one narration entry for that skip, and its last-checked marker names a run from within the last scheduled interval.
- **SC-008**: At no point does more than one version-bump pull request from this feature stand open.

## Assumptions

- The tracking issue and the version-bump pull request already exist as concepts with stable markers; this feature reads them and adds no new state store.
- "Billed" means the steps that invoke a Claude model or drive an agent — the judgment step and the end-to-end stage. The guard is placed before the first of these, so both are avoided; steps earlier than the guard (detection, settle) are cheap and continue to run every day, keeping the settle state current.
- The merge-handling path already fires when a version-bump pull request closes, so no new event subscription is required for resumption.
- The pinned-version check on the default branch remains the underlying eligibility signal; the guard sits alongside it and does not replace it.
- The guard is scoped to this feature's own scheduled adoption chain. Other pipeline stages, and other repositories consuming the published pipeline, are unaffected.
- A maintainer keeping a pull request open indefinitely is a legitimate state, not an error; the pipeline waits rather than escalating. With at most one proposal in flight (FR-011), that also means adoption of newer versions waits on that maintainer — an accepted trade for never having two competing bump PRs open.
- The existing behaviour of never merging or approving its own pull request is unchanged.
- The tracking issue's body is already edited by the settle step each run, so a per-run last-checked marker (FR-007) adds no new class of write.
