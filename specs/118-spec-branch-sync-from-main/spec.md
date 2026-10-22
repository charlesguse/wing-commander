# Feature Specification: Keep Spec Branches Current by Merging Main (sync-from-main)

**Feature Branch**: `spec-draft/118-spec-branch-sync-from-main`

**Created**: 2026-10-21

**Status**: Draft

**Input**: User description: "Keep spec branches current by merging main into them (sync-from-main), selectable instead of rebase" (issue #1074). On every push to `main`, the rebase stage rebases each in-flight `spec/*` branch onto it and force-pushes with lease, so every branch commit gets a new SHA and the old SHAs leave the remote. Anything derived from a branch's history then breaks: spec 116's convergence signals that need earlier round heads (self-inflicted share, churn) read n/a after the first rebase; finalize's fold range starts at a pre-rebase SHA and cannot be resolved, so the fold log stops growing (#1068, #918); and SHAs recorded on PRs and issues (review ledgers, fold logs, "started from" heads) stop resolving. Proposal: add a second way to keep spec branches current that merges `main` into the branch and never rewrites its history, selected by a repository switch, with rebase remaining the default. Its name must read as syncing, not as a feature merge. Conflicts follow the same model as rebase (agent resolution, deterministic scope verification before publish, escalation on the lifecycle issue). Out of scope: changing how final PRs merge into `main`.

## Clarifications

### Session 2026-10-21

- Q: Can a repository switch sync methods while lifecycles are in flight, and how are in-flight branches treated? → A: The switch is read at run time like the other `WING_COMMANDER_*` switches; every in-flight branch uses the new method from the next push to `main` (FR-012).
- Q: Should merge sync rely on, enforce, or ignore final PRs being squash-merged? → A: Documented assumption only; merge sync adds no coupling to the final-merge method. If squash-merging stops, sync commits reaching `main` are part of that separate decision (FR-013).
- Q: Should the rebase path keep and grow its history workarounds, or report n/a? → A: Keep the existing workaround (#1062's stored per-round diff size), add no new ones, and report the other history-derived signals as n/a with a reason saying rebase rewrites history and merge sync avoids it. Precedent: spec 116 F2 owner decision (#890 "Owner decisions") (FR-014).

### Session 2026-10-22

- Q: Under merge sync, what label does an escalated (unresolvable) branch carry? → A: Keep `rebase:blocked` for both methods. Discovery already reads it, it involves no contract change, and it does not read as "merge". The escalation text itself names the merge remedy (FR-008). The owner chose this on 2026-10-22, from the spec PR review.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A spec branch stays current without losing its history (Priority: P1)

A maintainer of a repository where `main` moves several times a day turns on the merge-based sync. From then on, each sync run (the stage's existing triggers: a push to `main`, nightly, or a manual dispatch) brings every in-flight spec integration branch up to date by adding a sync commit on top of the branch; every commit the branch already had keeps its SHA and stays reachable on the remote.

**Why this priority**: This is the whole point of the feature. Every downstream benefit (convergence signals, fold ranges, recorded SHAs) follows from history never being rewritten.

**Independent Test**: With the switch set to merge, record a spec branch's head SHA, push an unrelated commit to `main`, let the sync run, and confirm the recorded SHA is still an ancestor of the new branch head and the new head contains the `main` commit.

**Acceptance Scenarios**:

1. **Given** the switch is set to merge and a spec branch is behind `main` with no conflicting changes, **When** `main` receives a push, **Then** the branch gains exactly one new sync commit whose parents are the previous branch head and the current `main` head, and the branch is published without a force-push.
2. **Given** the switch is set to merge and a spec branch already contains the current `main` head, **When** the sync runs, **Then** the branch is left unchanged and no commit is created.
3. **Given** the switch is set to merge, **When** the sync publishes a branch, **Then** every SHA that was on the branch before the sync is still reachable from the new head.

---

### User Story 2 - The repository chooses its sync method with one switch (Priority: P1)

An adopter who prefers linear spec branches does nothing and keeps today's rebase behaviour. An adopter who needs stable history sets one repository-level switch to select the merge-based sync. The wrapper reads the switch and hands the choice to the stage as a declared input.

**Why this priority**: Adopters already depend on rebase; the new mode must be opt-in and must not change behaviour for anyone who does not ask for it.

**Independent Test**: Run the sync with the switch unset, set to `rebase`, and set to `merge`, and confirm the first two rebase and the third merges; set it to an unrecognised value and confirm the run fails loudly naming the bad value.

**Acceptance Scenarios**:

1. **Given** the switch is unset, **When** `main` receives a push, **Then** spec branches are rebased exactly as today.
2. **Given** the switch is set to `merge`, **When** `main` receives a push, **Then** spec branches are synced by merging and none is force-pushed.
3. **Given** the switch holds a value other than `rebase` or `merge`, **When** the sync runs, **Then** it fails before touching any branch and names the invalid value and the accepted values.
4. **Given** lifecycles are in flight and the switch is changed from `rebase` to `merge` (or back), **When** the next sync run starts, **Then** every in-flight spec branch is synced with the new method, regardless of the method in force when its lifecycle started.

---

### User Story 3 - Conflicts are resolved, verified and escalated the same way as today (Priority: P2)

When merging `main` into a spec branch conflicts, an agent resolves the conflict, deterministic code verifies the resolution stayed inside the conflicting paths before anything is published, and a branch that cannot be resolved is escalated on its lifecycle issue — the same model the rebase path uses.

**Why this priority**: Without a conflict path the merge mode only works for trivially clean branches; reusing the rebase model keeps the safety guarantees maintainers already trust.

**Independent Test**: Create a spec branch and a `main` commit that edit the same lines, run the sync in merge mode, and confirm (a) a resolvable conflict yields a published sync commit whose changes outside the conflicting paths match a clean merge, and (b) a resolution that touches a path outside the conflict set is refused and escalated.

**Acceptance Scenarios**:

1. **Given** a conflicting merge, **When** the agent resolves it within the conflicting paths, **Then** the scope check passes and the sync commit is published.
2. **Given** a conflicting merge, **When** the agent's resolution modifies a path outside the conflict set, or leaves conflict markers, **Then** nothing is published and the lifecycle issue receives an escalation naming the branch and the reason.
3. **Given** a conflicting merge the agent cannot resolve within its turn budget, **When** the run ends, **Then** the branch is left at its previous head and the lifecycle issue receives an escalation.

---

### User Story 4 - History-derived signals keep working under merge sync (Priority: P2)

Under merge sync, the review-convergence signals that need earlier round heads (self-inflicted share, churn, growth), finalize's fold range and fold log, and SHAs recorded on PRs and issues keep resolving for the whole lifecycle.

**Why this priority**: This is the payoff the issue names, but it depends on Stories 1–3 and needs no new mechanism of its own beyond not breaking those consumers.

**Independent Test**: Drive a lifecycle through two review rounds with at least one `main` push between them in merge mode, and confirm the convergence report computes share and churn (not n/a) and finalize's fold range resolves.

**Acceptance Scenarios**:

1. **Given** merge sync and a `main` push between two review rounds, **When** the convergence report is computed, **Then** self-inflicted share and churn are reported with values rather than n/a.
2. **Given** merge sync, **When** finalize computes its fold range from a SHA recorded earlier in the lifecycle, **Then** the range resolves and the fold log grows.
3. **Given** merge sync, **When** history-derived consumers compute a diff for the branch's own work, **Then** changes brought in by sync commits from `main` are not attributed to the lifecycle.

---

### Edge Cases

- A branch that already contains the current `main` head: no sync commit is created. A branch that does not contain it gets a sync commit even when the merged tree equals the branch's tree (e.g. `main` gained a cherry-pick of branch work), so the branch's merge-base with `main` advances and the next sync does not retry the same merge.
- `main` moves again while a sync is in progress: the branch's remote head did not change, so the publish succeeds with the branch synced to the earlier `main` head; the next sync run brings it current.
- The remote branch head changed between checkout and publish (another stage pushed): the publish is rejected rather than overwriting, and is retried on the next sync run.
- A branch that tracks the pipeline's own checkout directory, or a lifecycle in a project subfolder (spec 114): the same refusals and project-folder scoping that apply to rebase apply to merge sync.
- The switch is changed while lifecycles are in flight: every in-flight branch uses the new method from the next sync run (FR-012). Switching back to `rebase` linearizes a branch's sync commits; a branch whose sync commits carry conflict resolutions may re-conflict and be escalated through the existing rebase path rather than published (FR-012).
- A branch with an open final PR (the PR's head is the spec branch): a sync commit moves the PR head, exactly as a rebase does today, so the lifecycle review gate's head-bound review round applies unchanged.
- A stalled, closed-lifecycle or already-escalated branch: excluded by the same discovery rules as rebase (FR-009).
- Stage work branches (`plan/`, `tasks/`, `impl/`) whose PRs target the spec branch: they are not synced; under merge sync their base keeps its history, so their PRs keep a stable merge-base.
- A repository that stops squash-merging final PRs while merge sync is on: nothing refuses or warns; sync commits may then reach `main`, which is part of that separate decision (FR-013).
- Under rebase, a convergence report after a rebase: share and churn read n/a with the reason "rebase rewrites history; merge sync avoids it", while #1062's stored per-round diff size keeps working (FR-014).
- A conflict resolution that is textually clean but leaves a file outside the conflict set different from a clean merge: refused by the scope check.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The pipeline MUST offer a merge-based method for keeping in-flight spec integration branches current with `main` that adds a sync commit and never rewrites or removes commits already on the branch.
- **FR-002**: The merge-based method MUST publish without force-pushing; a publish whose remote head no longer matches the head the sync started from MUST be rejected rather than overwrite it.
- **FR-003**: The merge-based method MUST NOT create a commit when the branch already contains the current `main` head, and MUST create one whenever it does not, even if the merged tree equals the branch's tree.
- **FR-004**: The repository MUST select the method with a single repository-level switch whose accepted values are `rebase` and `merge`; unset MUST mean `rebase`, preserving today's behaviour for every adopter who does not opt in.
- **FR-005**: An unrecognised switch value MUST fail the run before any branch is touched, naming the invalid value and the accepted values.
- **FR-006**: The switch MUST be read by the wrapper and passed to the stage as a declared, typed input; the stage MUST NOT read repository variables directly (constitution VII). Any new input is an additive widening of the published contract with a default that preserves current behaviour.
- **FR-007**: The merge-based method, its job and its check MUST be named so they read as syncing a spec branch with `main` (default: "sync-from-main"; check/job title "Sync spec branch with main"), never as merging a feature. Under the `rebase` method every existing name stays as it is today (SC-004).
- **FR-008**: Conflicts under merge sync MUST follow the rebase model: an agent resolves the conflict under an explicit model and bounded turn budget (constitution II); deterministic code verifies before publish that the resolution changed only conflicting paths (narrowed to the lifecycle's project folder) and left no conflict markers; an unresolvable or out-of-scope result is abandoned and escalated on the lifecycle issue under the same `rebase:blocked` label rebase uses, and the escalation's remedy text describes bringing `main` into the branch by merge, not rebasing it.
- **FR-009**: Merge sync MUST apply the same pre-sync refusals and scoping as rebase: the same in-flight branch discovery and exclusions (merged PR, stalled lifecycle, closed lifecycle with no open PR, unchanged since its last escalation), refusing a branch that tracks the pipeline's own checkout directory, resolving spec names, and honouring project-subfolder lifecycles (spec 114).
- **FR-010**: Merge sync MUST emit the same run reporting as rebase — execution log and metrics record artifacts, cost line, over-budget report, and agent-verdict handling — so watchdog and metrics consumers see no gap when a repository switches.
- **FR-011**: History-derived consumers (review-convergence signals, finalize's fold range and fold log, recorded "started from" heads) MUST resolve their recorded SHAs under merge sync, and any diff they compute of the lifecycle's own work MUST exclude changes that arrived through sync commits from `main`; lines a sync commit's conflict resolution changed relative to `main` count as the lifecycle's own work.
- **FR-012**: The switch MUST be read at run time on every sync, like the other `WING_COMMANDER_*` switches; when it changes while lifecycles are in flight, the pipeline MUST apply the new method to every in-flight spec branch from the next sync run (the stage's existing triggers: a non-bot push to `main`, the nightly schedule, or a manual dispatch). Lifecycles are not pinned to the method they started under, and the switch is not refused while lifecycles are open. A branch that was previously rebased is merge-synced from its current head onward; a branch that already carries sync commits is handed to the unchanged rebase path once the switch returns to `rebase`, which linearizes it; where a sync commit carried a conflict resolution, the rebase may re-conflict and fail its scope check, and the branch is then escalated rather than published. This is an accepted limit: per FR-014 the rebase path gains no merge-aware handling.
- **FR-013**: Merge sync MUST treat squash-merging of final PRs as a documented assumption only: it MUST NOT check, enforce or depend on how final PRs reach `main` (neither merge sync nor finalize refuses to run based on the merge method). If a repository stops squash-merging, sync commits reaching `main` are a consequence of that separate decision, not something this feature prevents.
- **FR-014**: Under the rebase method, the pipeline MUST keep the existing workaround (#1062's stored per-round diff size) and MUST NOT add new rebase-path workarounds; every other history-derived signal that cannot survive a rebase (e.g. self-inflicted share, churn) MUST be reported as n/a with an explicit reason stating that rebase rewrites history and that merge sync avoids it.
- **FR-015**: The documentation for adopters MUST describe both methods, the switch, its default, and the trade-off (linear branches vs. stable history), stating which layer (published contract vs. consuming instrument) each part describes.
- **FR-016**: Every new deterministic check this feature adds (switch validation, no-force publish, scope verification for merge conflicts) MUST live in deterministic code that the stage step calls, with every failure branch exercised by a checked-in fixture run through the gate registry (constitution VIII); a gate that only inspects workflow text does not satisfy this.

### Key Entities

- **Sync method switch**: A repository-level setting with values `rebase` (default) or `merge`, read by the wrapper and passed to the stage.
- **Sync commit**: The merge commit merge sync adds to a spec branch; first parent is the previous branch head, second parent is the `main` head it synced to. It carries no lifecycle work of its own other than conflict resolutions.
- **Spec integration branch**: The long-lived `spec/[<P>/]<NNN-slug>` branch kept current with `main`.
- **Recorded head**: A SHA the pipeline stores on a PR, issue or spec artifact (review round heads, fold-range starts, "started from" heads) and later resolves.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Under merge sync, 100% of spec-integration-branch SHAs recorded during a lifecycle remain resolvable on the remote until the lifecycle's cleanup, across any number of pushes to `main`.
- **SC-002**: Under merge sync, zero force-pushes are made to spec integration branches by the sync stage.
- **SC-003**: Under merge sync, a lifecycle never rebased after its first recorded round head, with at least one `main` push between review rounds reports self-inflicted share and churn with values (not n/a) in 100% of convergence reports.
- **SC-004**: Repositories that leave the switch unset see no change in branch history, check names, or reporting compared with today.
- **SC-005**: Every conflicting merge sync ends in exactly one of: a published, scope-verified sync commit, or an escalation on the lifecycle issue — never a silently stale or partially published branch.
- **SC-006**: Under merge sync, finalize's fold log grows on every fold for a lifecycle that saw `main` pushes and was never rebased after its fold-range start was recorded, eliminating the stall class reported in #918 and #1068.

## Assumptions

- The name defaults to "sync-from-main" (check/job title "Sync spec branch with main") from the issue's candidates; the plan may refine the wording but not toward "merge".
- The switch's repository variable defaults to the name suggested in the issue, `WING_COMMANDER_SPEC_BRANCH_SYNC`, following the existing `WING_COMMANDER_*` convention.
- Final PRs continue to be squash-merged: constitution X requires it of the bot's lifecycle auto-merge, and a maintainer merging by hand (auto-merge off, the default) is assumed to squash as well; changing that is out of scope, and merge sync relies on it as a documented assumption only (FR-013).
- The triggers are unchanged: the same runs that drive rebase today (a non-bot push to `main`, the nightly schedule, a manual dispatch) drive merge sync.
- Stage work branches (`plan/`, `tasks/`, `impl/`) are not in scope; only spec integration branches are synced.
- The conflict-resolution agent, its model tier and turn ceiling, and the escalation format are reused from the rebase path rather than redesigned.
- #1062's stored per-round diff size remains in place under rebase (FR-014).
