# Feature Specification: Keep Spec Branches Current by Merging Main (sync-from-main)

**Feature Branch**: `spec-draft/118-spec-branch-sync-from-main`

**Created**: 2026-10-21

**Status**: Draft

**Input**: User description: "Keep spec branches current by merging main into them (sync-from-main), selectable instead of rebase" (issue #1074). On every push to `main`, the rebase stage rebases each in-flight `spec/*` branch onto it and force-pushes with lease, so every branch commit gets a new SHA and the old SHAs leave the remote. Anything derived from a branch's history then breaks: spec 116's convergence signals that need earlier round heads (self-inflicted share, churn) read n/a after the first rebase; finalize's fold range starts at a pre-rebase SHA and cannot be resolved, so the fold log stops growing (#1068, #918); and SHAs recorded on PRs and issues (review ledgers, fold logs, "started from" heads) stop resolving. Proposal: add a second way to keep spec branches current that merges `main` into the branch and never rewrites its history, selected by a repository switch, with rebase remaining the default. Its name must read as syncing, not as a feature merge. Conflicts follow the same model as rebase (agent resolution, deterministic scope verification before publish, escalation on the lifecycle issue). Out of scope: changing how final PRs merge into `main`.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A spec branch stays current without losing its history (Priority: P1)

A maintainer of a repository where `main` moves several times a day turns on the merge-based sync. From then on, each push to `main` brings every in-flight spec integration branch up to date by adding a sync commit on top of the branch; every commit the branch already had keeps its SHA and stays reachable on the remote.

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

- A branch whose work has already landed on `main` (sync would produce no change): no empty sync commit is created.
- `main` moves again while a sync is in progress: the publish refuses to overwrite a remote head it did not start from (no force), and the next push to `main` brings the branch current.
- The remote branch head changed between checkout and publish (another stage pushed): the publish is rejected rather than overwriting, and is retried on the next trigger.
- A branch that tracks the pipeline's own checkout directory, or a lifecycle in a project subfolder (spec 114): the same refusals and project-folder scoping that apply to rebase apply to merge sync.
- The switch is changed while lifecycles are in flight: behaviour governed by FR-012.
- A repository that stops squash-merging final PRs while merge sync is on: behaviour governed by FR-013.
- A conflict resolution that is textually clean but leaves a file outside the conflict set different from a clean merge: refused by the scope check.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The pipeline MUST offer a merge-based method for keeping in-flight spec integration branches current with `main` that adds a sync commit and never rewrites or removes commits already on the branch.
- **FR-002**: The merge-based method MUST publish without force-pushing; a publish whose remote head no longer matches the head the sync started from MUST be rejected rather than overwrite it.
- **FR-003**: The merge-based method MUST NOT create a commit when the branch already contains the current `main` head or when the merge would change nothing.
- **FR-004**: The repository MUST select the method with a single repository-level switch whose accepted values are `rebase` and `merge`; unset MUST mean `rebase`, preserving today's behaviour for every adopter who does not opt in.
- **FR-005**: An unrecognised switch value MUST fail the run before any branch is touched, naming the invalid value and the accepted values.
- **FR-006**: The switch MUST be read by the wrapper and passed to the stage as a declared, typed input; the stage MUST NOT read repository variables directly (constitution VII). Any new input is an additive widening of the published contract with a default that preserves current behaviour.
- **FR-007**: The merge-based method, its job and its check MUST be named so they read as syncing a spec branch with `main` (default: "sync-from-main"; check/job title "Sync spec branch with main"), never as merging a feature.
- **FR-008**: Conflicts under merge sync MUST follow the rebase model: an agent resolves the conflict under an explicit model and bounded turn budget (constitution II); deterministic code verifies before publish that the resolution changed only conflicting paths (narrowed to the lifecycle's project folder) and left no conflict markers; an unresolvable or out-of-scope result is abandoned and escalated on the lifecycle issue.
- **FR-009**: Merge sync MUST apply the same pre-sync refusals and scoping as rebase: refusing a branch that tracks the pipeline's own checkout directory, resolving spec names, and honouring project-subfolder lifecycles (spec 114).
- **FR-010**: Merge sync MUST emit the same run reporting as rebase — execution log and metrics record artifacts, cost line, over-budget report, and agent-verdict handling — so watchdog and metrics consumers see no gap when a repository switches.
- **FR-011**: History-derived consumers (review-convergence signals, finalize's fold range and fold log, recorded "started from" heads) MUST resolve their recorded SHAs under merge sync, and any diff they compute of the lifecycle's own work MUST exclude changes that arrived through sync commits from `main`.
- **FR-012**: When the switch changes while lifecycles are in flight, the pipeline MUST [NEEDS CLARIFICATION: Can a repository switch methods while lifecycles are in flight, and if so how are branches already rebased (or already carrying sync commits) treated — apply the new method to every in-flight branch on the next push, pin each lifecycle to the method it started under, or refuse the switch while any lifecycle is open?]
- **FR-013**: The relationship between merge sync and how final PRs reach `main` MUST be [NEEDS CLARIFICATION: Final PRs are squash-merged today so sync commits never reach `main`. Should merge sync rely on that as a documented assumption only, should it be enforced (e.g. merge sync refuses to run, or finalize refuses to merge, unless the final PR will be squash-merged), or is it acceptable for sync commits to land on `main` if squash-merging stops?]
- **FR-014**: Under the rebase method, the history-derived signals that cannot survive a rebase MUST be handled as follows: [NEEDS CLARIFICATION: Should the rebase path keep its own workarounds (such as #1062's stored per-round diff size) and gain more where possible, or should it stop carrying workarounds and report those signals as n/a with an explicit "rebase rewrites history; use merge sync" reason?]
- **FR-015**: The documentation for adopters MUST describe both methods, the switch, its default, and the trade-off (linear branches vs. stable history), stating which layer (published contract vs. consuming instrument) each part describes.
- **FR-016**: Every new deterministic check this feature adds (switch validation, no-force publish, scope verification for merge conflicts) MUST be reachable through the gate registry with checked-in fixtures for each failure branch (constitution VIII).

### Key Entities

- **Sync method switch**: A repository-level setting with values `rebase` (default) or `merge`, read by the wrapper and passed to the stage.
- **Sync commit**: The merge commit merge sync adds to a spec branch; first parent is the previous branch head, second parent is the `main` head it synced to. It carries no lifecycle work of its own other than conflict resolutions.
- **Spec integration branch**: The long-lived `spec/[<P>/]<NNN-slug>` branch kept current with `main`.
- **Recorded head**: A SHA the pipeline stores on a PR, issue or spec artifact (review round heads, fold-range starts, "started from" heads) and later resolves.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Under merge sync, 100% of SHAs recorded during a lifecycle remain resolvable on the remote until the lifecycle's cleanup, across any number of pushes to `main`.
- **SC-002**: Under merge sync, zero force-pushes are made to spec integration branches by the sync stage.
- **SC-003**: Under merge sync, a lifecycle with at least one `main` push between review rounds reports self-inflicted share and churn with values (not n/a) in 100% of convergence reports.
- **SC-004**: Repositories that leave the switch unset see no change in branch history, check names, or reporting compared with today.
- **SC-005**: Every conflicting merge sync ends in exactly one of: a published, scope-verified sync commit, or an escalation on the lifecycle issue — never a silently stale or partially published branch.
- **SC-006**: Under merge sync, finalize's fold log grows on every fold for a lifecycle that saw `main` pushes, eliminating the stall class reported in #918 and #1068.

## Assumptions

- The name defaults to "sync-from-main" (check/job title "Sync spec branch with main") from the issue's candidates; the plan may refine the wording but not toward "merge".
- The switch's repository variable defaults to the name suggested in the issue, `WING_COMMANDER_SPEC_BRANCH_SYNC`, following the existing `WING_COMMANDER_*` convention.
- Final PRs continue to be squash-merged (constitution X); changing that is out of scope (see FR-013 for how merge sync treats the assumption).
- The trigger is unchanged: the same push to `main` that drives rebase today drives merge sync.
- Stage work branches (`plan/`, `tasks/`, `impl/`) are not in scope; only spec integration branches are synced.
- The conflict-resolution agent, its model tier and turn ceiling, and the escalation format are reused from the rebase path rather than redesigned.
- #1062's stored per-round diff size remains in place until FR-014 is settled.
