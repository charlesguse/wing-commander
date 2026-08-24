# Feature Specification: The Post-Review Fold Loop — Fold Every Leg Once, Come Back for Re-Review, and Be Able to Delete a File

**Feature Branch**: `042-post-review-fold-loop`

**Created**: 2026-08-24

**Status**: Draft

**Input**: User description: "Three defects, one loop: what happens after a maintainer reviews a pipeline PR. Today the fold loop can drop review feedback (#246), never re-presents the folded result for re-review (#247), and the implement runs it dispatches cannot delete a file (#242). Each was filed separately; they should ship as one spec because they are one user journey — 'maintainer requests changes → pipeline folds, implements, and comes back for re-review' — and every fix touches the same two workflows (pr-conversation.yml, finalize.yml) plus implement's allowlist. **The journey today, measured on PR #240 (2026-08-24, runs 32680244191 / 32680906254 / 32687741454)**: (1) A single request-changes review with 3 in-scope items + 1 question + 1 note was classified into 5 act legs. (2) Every act leg joins concurrency group `wing-commander-<spec-dir>` (cancel-in-progress: false) — the same group implement uses. Leg 1 folded and dispatched implement iteration 2; leg 3 sat pending behind that run, then folded and dispatched iteration 3; leg 4 and iteration 3 met in the group and both were cancelled inside one second. Leg 4 died with zero steps run: its review item was never folded — an 'announcement' comment with no outcome is all that remains (#246). Recovery was manual (hand-fold 0269027 + manual dispatch). (3) When the folded work converged, finalize ran — and skipped everything: the existing-PR guard (finalize.yml:507-510) makes finalize one-shot, so the PR body still describes the pre-fold branch, spec-meta stays `stage: implement`, the `stage:review` flip and re-review request never happen (#247). The maintainer is never told the fold is ready. (4) Any folded change that requires deleting a file cannot complete: implement's allowlist has no `git rm`/`rm`, so such specs end in 'manual work' comments (#242) — twice observed. **What the spec should cover**: Fold-then-dispatch-once (#246) — the act pass folds ALL legs of one review before any implement dispatch (either a single act job over the classified set, or serialized legs with dispatch deferred to the last) and act legs must not contend with the implement run they themselves dispatch; an act leg that is cancelled before folding must fail loudly on the PR thread, not vanish behind its own announcement. Re-entrant finalize (#247) — a finalize run that finds an existing final PR refreshes it (body regenerated from the folded branch, spec-meta committed to `review`, `stage:review` label restored, re-review requested from the maintainer(s) whose review triggered the fold) instead of skipping; the one-shot guard's original purpose (no duplicate PRs) is preserved by updating, not by doing nothing. Deletion capability (#242) — implement's allowed tools gain `git rm` (and the minimal equivalent for non-tracked files), with the same guardrails as other write verbs — scoped to the spec branch checkout, gated by the existing constraints block. Acceptance should include a re-run of the #240 shape: one review, ≥3 in-scope items, one implement dispatch total, zero cancelled legs, finalize refreshing the PR and asking for re-review, and a folded task that deletes a file completing without 'manual work'. **Non-goals**: Reworking classification categories or the question/no-action legs (they behaved correctly on #240); the stop procedure (T030-T032) — untouched. Closes #246, #247, #242 when implemented."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Every item in one review is folded, exactly once, before any implementation starts (Priority: P1)

A maintainer leaves a single review on a pipeline PR carrying several requested changes. The pipeline acknowledges the review, folds **every** in-scope item into the specification's task list, and only then starts one implementation cycle. No item is silently dropped, no implementation cycle is started that will immediately be cancelled, and the maintainer can see, from the PR thread alone, that each item they raised was accounted for.

**Why this priority**: This is the defect with the worst outcome — a review item can vanish. On PR #240 leg 4 was cancelled with zero steps run, so its item was never folded and the only trace was an announcement comment promising work that never happened. A maintainer reading that thread has every reason to believe their feedback was taken. Silent loss of human review feedback is the most expensive failure this pipeline can have, because the pipeline's whole contract with a maintainer is that reviewing is how you steer it. Everything else here is about the loop being slow, wasteful, or incomplete; this one is about it being untrustworthy.

**Independent Test**: Drive one review carrying at least three in-scope change requests plus a question and a note, and confirm that all three in-scope items appear in the task list, that exactly one implementation cycle is dispatched for that review, that no leg or cycle belonging to that review is cancelled, and that the question and note legs behave exactly as they do today.

**Acceptance Scenarios**:

1. **Given** a single review classified into three in-scope change items, **When** the pipeline acts on it, **Then** all three items are folded into the task list before any implementation cycle is dispatched.
2. **Given** the same review, **When** the pipeline finishes acting on it, **Then** exactly one implementation cycle has been dispatched for that review, and it starts with all three fold-ins already present.
3. **Given** the same review, **When** the run completes, **Then** no leg of that review and no implementation cycle it dispatched was cancelled by contention with another part of the same review.
4. **Given** a review that also contains a question and a no-action note, **When** the pipeline acts on it, **Then** those legs behave exactly as they do today and neither delays nor triggers an implementation dispatch of its own.
5. **Given** a review where one in-scope item is held waiting on a human confirmation, **When** the other items are ready, **Then** those items are still folded, and the single dispatch happens after the held item resolves rather than before it.
6. **Given** a review whose items are all questions or notes, **When** the pipeline finishes acting on it, **Then** no implementation cycle is dispatched at all.
7. **Given** a review that arrives while an implementation cycle for the same specification is already running, **When** the pipeline acts on it, **Then** the running cycle is allowed to finish undisturbed, the fold happens after it, and the single dispatch follows the fold.

---

### User Story 2 - A leg that dies says so on the PR thread (Priority: P1)

A maintainer whose review item cannot be folded — the run was cancelled, the branch moved, the fold failed — reads that fact on the PR thread. The announcement that promised the work is followed by an outcome that contradicts it, naming the item and what a human should do. The maintainer never has to reconcile a promise with a silence.

**Why this priority**: The announcement-before-work design is deliberate and good — it tells the maintainer their review was seen before any slow work begins. But an announcement with no possible outcome is worse than no announcement, because it converts an observable failure into an invisible one. On #240 the recovery was a hand-fold and a manual dispatch by someone who happened to notice; nothing in the pipeline would have raised it. Equal priority to story 1 because story 1 reduces how often a leg dies, and cannot make it impossible.

**Independent Test**: Cause a leg to terminate without folding — by cancellation and by an outright fold failure — and confirm that in each case a comment appears on the PR thread naming the unfolded item, and that the run's status reflects the failure.

**Acceptance Scenarios**:

1. **Given** a leg that is cancelled before it folds its item, **When** the run ends, **Then** a comment on the PR thread names the item that was not folded and states that it requires attention.
2. **Given** a leg that fails while folding, **When** the run ends, **Then** the same kind of comment appears, and it distinguishes "not folded" from "partly folded".
3. **Given** a leg that was announced and then never ran at all, **When** the run ends, **Then** the outcome comment still appears — it does not depend on any value the dead leg would have produced.
4. **Given** any unfolded item, **When** the outcome is reported, **Then** the report is not suppressed by the failure or cancellation of the step ahead of it, or of the leg itself.
5. **Given** a run where every announced leg folded successfully, **When** the run ends, **Then** no failure comment is posted — this reporting is silent on the healthy path.
6. **Given** a review where some legs folded and one did not, **When** the run ends, **Then** the maintainer can tell from the thread which items landed and which did not.

---

### User Story 3 - The folded PR comes back and asks to be looked at again (Priority: P1)

A maintainer requested changes on a final PR. Some time later, the same PR's description reflects the folded work, the specification's lifecycle record says it is back in review, the review label is back on the lifecycle issue, and the maintainer has been asked for a re-review. They are told, on the lifecycle issue, that the feedback they gave has been acted on and the PR is ready again.

**Why this priority**: Without this, the loop has no closing move. On PR #235 the second finalize did nothing at all: the record still said implementation, the PR body described a pre-fold branch, and the last thing the lifecycle issue said was "cycle 2 completed". A maintainer who requests changes and hears nothing back has to poll. Worse, a specification whose record permanently reads `implement` is one every downstream consumer — the restart guard, the watchdog, the cleanup stage — reads wrongly. Equal priority to stories 1 and 2 because folding feedback nobody is told about is only marginally better than dropping it.

**Independent Test**: Run a specification through review → fold → implement → converge → finalize a second time, and confirm the PR body reflects the folded branch, the lifecycle record reads review, the review label is present, a re-review is requested from the reviewer whose review triggered the fold, and a comment on the lifecycle issue says so.

**Acceptance Scenarios**:

1. **Given** a specification whose final PR is open and whose folded work has converged, **When** finalize runs again, **Then** the PR description is refreshed to describe the current state of the branch.
2. **Given** the same run, **When** it completes, **Then** the specification's lifecycle record is committed with the review stage recorded, not left at implementation.
3. **Given** the same run, **When** it completes, **Then** the review label is present on the lifecycle issue and any implementation-stage label is gone.
4. **Given** the same run, **When** it completes, **Then** a re-review is requested from the reviewer or reviewers whose review triggered the fold, and a comment on the lifecycle issue says the feedback was acted on and names the review it answers.
5. **Given** a specification whose final PR was already merged, **When** finalize runs again, **Then** nothing is refreshed, no metadata is committed, no re-review is requested, and the run says why.
6. **Given** a specification with no final PR yet, **When** finalize runs, **Then** it opens exactly one PR, as it does today.
7. **Given** two finalize runs for the same specification in quick succession, **When** both complete, **Then** there is still exactly one final PR and the requester sees at most one re-review request per fold.
8. **Given** a refresh run, **When** it completes, **Then** it has not opened a second PR, reopened a closed one, approved anything, or merged anything.
9. **Given** a PR body carrying human prose outside the machine-owned delimiters and a human edit inside them, **When** the refresh runs, **Then** the prose outside is preserved, the state block inside is regenerated from the branch, and an entry for this fold is appended to the fold log without rewriting earlier entries.

---

### User Story 4 - A folded change that deletes a file completes (Priority: P2)

A maintainer's review asks for something to be removed — a retired script, a superseded spec directory, a dead gate's helper. The implementation cycle removes it and the cycle completes. The requester is not handed a "remaining manual work" note asking them to run the removal by hand.

**Why this priority**: This one is a hard stop rather than a silent loss: the pipeline reports honestly that it could not finish, so nothing is lost and nobody is misled. But it has been observed twice, and it makes every removal-shaped feature un-automatable — which the constitution's automation-first principle treats as a defect, and which leaves exactly the orphaned-artifact shape another gate exists to fail. Below the P1 stories because the failure is loud and the workaround is a human running one command.

**Independent Test**: Fold a task that requires deleting a tracked file, run the implementation cycle, and confirm the file is gone from the branch and the cycle reports no remaining manual work for that task.

**Acceptance Scenarios**:

1. **Given** a task that requires deleting a tracked file, **When** the implementation cycle runs, **Then** the file is removed on the specification branch and the cycle does not report the deletion as remaining manual work.
2. **Given** the same capability, **When** a retry or a convergence pass runs, **Then** it has the same removal capability the cycle has — the three do not diverge.
3. **Given** a removal, **When** it happens, **Then** it is confined to the specification branch checkout under the same guardrails as every other write the stage performs.
4. **Given** the published tool contract, **When** it is inspected after this change, **Then** the widened capability is recorded there, and a mismatch between the contract and the actual call sites fails a check.
5. **Given** an adopting repository, **When** it takes this change, **Then** it receives the capability without editing a wrapper workflow, and its existing per-repository tool grants keep working.
6. **Given** a task that requires removing a file that is not tracked, **When** the implementation cycle runs, **Then** it reports the removal as remaining manual work rather than performing it, and the stage's capabilities are unchanged for that case.

---

### User Story 5 - The failure branches are exercised, not merely written (Priority: P2)

Before this ships, checks drive each of the three defect shapes and assert the new behaviour. Regressing any of them — a per-leg dispatch returning, a finalize refresh becoming a skip again, the removal capability disappearing from the contract or the call sites — fails a check.

**Why this priority**: Every path this feature adds runs only after something has already gone a particular way: a review with several items, a second finalize, a task that deletes. That is precisely the class of behaviour that rots unobserved, and the repository has the standing rule that every shipped failure branch is covered by a checked-in fixture rather than a manual demonstration during development. Below the P1 stories because it protects the fix rather than being the fix.

**Independent Test**: Run the checks against a tree with each defect reintroduced in turn and confirm each one goes red; run them against the fixed tree and confirm they pass.

**Acceptance Scenarios**:

1. **Given** a fixture with three in-scope legs, **When** the checks run, **Then** they assert exactly one implementation dispatch.
2. **Given** a fixture with an existing open final PR, **When** the checks run, **Then** they assert the metadata commit, the label restore, and the re-review request occur.
3. **Given** a fixture with an already-merged final PR, **When** the checks run, **Then** they assert none of those occur.
4. **Given** a fixture with a leg that terminates before folding, **When** the checks run, **Then** they assert the PR-thread failure comment is produced.
5. **Given** the removal capability removed from either the contract or a call site, **When** the checks run, **Then** a check fails.
6. **Given** the new coverage disabled, removed, or made unreachable, **When** the checks run, **Then** a check fails — it is wired into the same registry that proves every other gate is run.

---

### Edge Cases

- **A leg is cancelled by contention with a run this same review dispatched.** This is the observed defect. The act pass must not compete for the same serialization slot as the implementation it starts; a review must not be able to cancel its own work.
- **A second review arrives while the first is still folding.** The two reviews are separate units of work. No item from either review may be dropped, and a maintainer must not receive an announcement whose outcome never appears. The second review's act pass waits, as it does for any cycle already in flight, and folds once the first review's work has settled.
- **An implementation cycle for the same specification is already running when a review arrives.** Folding into the task list under a running cycle is the shape that produced the original contention. The act pass waits for the running cycle to finish, then folds every leg and dispatches once — the running cycle is never discarded, and it is never handed a task list mid-write. The maintainer waits the length of the cycle already in flight before their review takes effect.
- **One leg of a review is held waiting on a human confirmation while the others are ready.** The ready items still fold — a held leg must not block the others, as it does not today — but the single dispatch waits for the held leg to resolve so the cycle sees the whole review.
- **A held leg is never confirmed.** The dispatch cannot wait forever. The pipeline reports on the PR thread that the review was folded except for the held item, and dispatches what it has.
- **A review with zero in-scope items.** Nothing is folded and nothing is dispatched, and the announcement's outcome says so rather than leaving a promise open.
- **Finalize runs a second time and nothing has changed since the first.** The refresh is idempotent: the body is rewritten to the same content, the record is committed only if it differs, and at most one re-review request exists per fold.
- **The existing final PR is closed but not merged.** A human closed it deliberately. Refreshing it would resurrect work someone stopped; the run reports what it found and changes nothing.
- **The existing final PR is merged.** The specification is done. The refresh path must not run, must not commit a record change, and must not ask anyone for a re-review.
- **The reviewer whose review triggered the fold cannot be asked for a re-review** — they are the PR author, they have left the repository, or the request is rejected. The refresh still completes and still reports on the lifecycle issue; the re-review request is best-effort and its failure is stated, not swallowed.
- **The record cannot be committed during a refresh** because the specification branch moved underneath the run. The refresh still reports on the lifecycle issue and says the record could not be updated.
- **The removal capability is asked to remove something outside the specification's checkout.** It is scoped the same way every other write verb of that stage is scoped; a removal outside that scope is not available to the stage.
- **A task asks to remove a file that is not tracked.** The stage gains no capability for this case. It reports the removal as remaining manual work, as it does today — a loud stop rather than a widened tool surface, until a real task shows the need.
- **A removal that would empty the specification branch's diff against the default branch.** The existing empty-diff anomaly handling is unchanged; a specification that deletes everything is still an anomaly.
- **The stop procedure runs while a fold is in flight.** Out of scope for this feature and unchanged by it; the fold's serialization must not alter how a stop request is handled.

## Requirements *(mandatory)*

### Functional Requirements

#### Folding a review exactly once

- **FR-001**: All in-scope items classified from a single review that are not abandoned under FR-005a MUST be folded into the specification's task list before any implementation cycle is dispatched for that review.
- **FR-002**: A single review MUST result in at most one implementation dispatch, regardless of how many in-scope items it was classified into. A review with no in-scope items MUST result in none.
- **FR-003**: The dispatched implementation cycle MUST begin with every folded item from that review already present.
- **FR-004**: The act pass MUST NOT contend for the same serialization slot as the implementation cycle it dispatches. No part of a review's own processing may cancel, or be cancelled by, work that same review started.
- **FR-004a**: When a review arrives while an implementation cycle for the same specification is already in flight, the act pass MUST wait for that cycle to finish before folding, then fold every in-scope item of that review and dispatch a single implementation cycle. In-flight implementation work MUST NOT be discarded to make room for a fold, and no implementation cycle may be started against a task list that a fold is still writing.
- **FR-004b**: While an act pass is waiting under FR-004a, the announcement's obligation still stands: the wait MUST NOT be mistaken for a terminated leg, and if the wait itself ends without folding, FR-006 applies.
- **FR-005**: An item that is held awaiting human confirmation MUST NOT block the folding of the other items of the same review, and MUST NOT produce a dispatch of its own.
- **FR-005a**: A held leg's wait MUST be bounded. When the bound expires without confirmation, the pipeline MUST report on the PR thread that the review was folded except for the held item, naming it, and dispatch what it has; the abandoned item then falls under FR-006 as an unfolded item needing attention — it is never dropped silently.
- **FR-006**: Every announced leg MUST produce an observable outcome on the PR thread. A leg that terminates without folding its item — cancelled, failed, or never started — MUST result in a comment naming the unfolded item and stating that it needs attention, and MUST NOT be reported as success.
- **FR-006a**: The outcome report of FR-006 MUST NOT depend on any value the terminated leg failed to publish, and MUST NOT be suppressed by the failure or cancellation of a step ahead of it, or of the leg itself.
- **FR-007**: Classification categories, the question and no-action legs, and the announce-before-work ordering MUST be unchanged by this feature.

#### Presenting the folded result for re-review

- **FR-008**: When a finalize run finds an existing **open** final pull request for the specification, it MUST refresh that pull request rather than skip: the description MUST describe the current state of the specification branch, the lifecycle record MUST be committed with the review stage recorded, the review stage label MUST be present on the lifecycle issue with any implementation-stage label removed, and a re-review MUST be requested from the reviewer or reviewers whose review triggered the fold. That identity MUST be read from the pull request's own review records or the specification's lifecycle record — never from ambient event state.
- **FR-008a**: The refreshed description MUST contain a machine-owned region, delimited so that a human and the pipeline can both tell where it begins and ends. That region holds two parts: a state block describing the branch's current state, which MUST be regenerated (overwritten) on every refresh, and an append-only fold log beneath it, to which a short entry recording what each fold changed MUST be appended — one entry per fold, not one per finalize run. A refresh MUST NOT rewrite or drop existing fold-log entries.
- **FR-008b**: Prose outside the machine-owned delimiters MUST be preserved across refreshes. Content inside them is machine-owned: a human edit made inside the delimiters MUST NOT survive the next refresh (the state block is regenerated; the fold log is restored to its recorded entries), and the delimiters MUST make that ownership evident to a reader.
- **FR-009**: A finalize run that finds an existing final pull request that is **merged** MUST NOT refresh it, MUST NOT commit a record change, MUST NOT alter labels, and MUST NOT request a re-review. It MUST report what it found.
- **FR-009a**: A finalize run that finds an existing final pull request that is **closed but not merged** MUST likewise change nothing and report what it found; a deliberately closed pull request is not reopened or refreshed by this feature.
- **FR-010**: The guard's original purpose MUST be preserved: no finalize run may open a second final pull request for a specification that already has one, on any path this feature adds.
- **FR-010a**: The refresh MUST be idempotent. Repeated finalize runs with no intervening change MUST leave the pull request, the record, and the labels in the same state, and MUST NOT accumulate duplicate re-review requests or duplicate lifecycle-issue comments for the same fold.
- **FR-010b**: A re-review request that cannot be fulfilled MUST NOT fail the refresh. The remaining effects MUST still occur and the failure MUST be stated rather than swallowed.
- **FR-010c**: After a refresh, the lifecycle record MUST NOT read as though implementation were still in progress.
- **FR-010d**: The lifecycle issue MUST carry a comment stating that the review feedback was acted on and that the pull request is ready to be looked at again, naming the review it answers.
- **FR-010e**: The refresh path MUST NOT approve or merge anything.

#### Removing files

- **FR-011**: The implementation cycle MUST be able to remove a tracked file from the specification branch and have the cycle complete, without reporting the removal as remaining manual work.
- **FR-011a**: The removal capability MUST cover tracked files only, and MUST leave the removal staged the same way the stage's existing write capabilities leave their changes staged. A task that requires removing a file that is not tracked MUST be reported as remaining manual work, exactly as it is today; no capability that can remove arbitrary untracked content from the checkout is added by this feature. That capability is deferred until a real task demonstrates the need.
- **FR-012**: The removal capability MUST be available to the implementation cycle, its retry, and the convergence pass alike; these MUST NOT diverge in what they can remove.
- **FR-013**: The removal MUST be confined to the specification branch checkout and governed by the same constraints as the stage's existing write capabilities. No new constraint may be weakened to accommodate it.
- **FR-014**: The widening of the stage's capabilities MUST be recorded in the published contract, and a divergence between that record and the actual call sites MUST fail a check.
- **FR-015**: Adopting repositories MUST receive this capability without editing a wrapper workflow, and any existing per-repository grant of the same capability MUST continue to work.

#### Not regressing

- **FR-016**: The declared inputs, outputs, and secrets of every affected stage MUST NOT be removed or renamed; any addition MUST be optional, with a default that preserves current behaviour. No adopter may need to edit a wrapper workflow to receive any part of this feature.
- **FR-017**: Every path that is quiet today MUST remain quiet. A healthy review whose legs all fold, a first finalize, and an implementation cycle that removes nothing MUST each behave exactly as they do now.
- **FR-018**: Executable coverage MUST exercise each of the following against checked-in fixtures: a review with at least three in-scope legs producing exactly one dispatch; a review arriving while an implementation cycle is in flight producing no fold and no dispatch until that cycle has finished; a leg that terminates before folding producing the PR-thread failure comment; a finalize run against an existing open pull request producing the record commit, the label restore, the re-review request, and a body whose machine-owned region is regenerated while prose outside it survives; a finalize run against a merged pull request producing none of those; a finalize run against a pull request closed without merging producing FR-009a's distinct outcome; a re-review request that cannot be fulfilled producing FR-010b's recorded fallback; a repeat refresh with no intervening fold changing nothing, per FR-010a; and an implementation cycle that removes a tracked file completing.
- **FR-019**: Reintroducing any of the three defects MUST fail a check: a per-leg dispatch, a finalize refresh that reverts to skipping on an open pull request, or the removal capability disappearing from either the contract or a call site.
- **FR-020**: The new coverage MUST be wired into the repository's existing gate registry, so coverage that stops being run is itself a failure.
- **FR-021**: The conditions this feature introduces or changes MUST satisfy the repository's existing job-suppression gate. If that gate's rules must change to admit them, the change MUST NOT reduce the set of shapes it detects.

### Key Entities

- **Review**: one maintainer's submitted review on a pipeline pull request, carrying one or more items. It is the unit that determines how many implementation cycles are dispatched — one at most — even though it is processed as several classified items.
- **Act leg**: the processing of one classified item from a review. Today each leg both folds its item and dispatches implementation; the dispatch belongs to the review, not to the leg.
- **Fold**: the act of writing a review item into the specification's task list and returning the lifecycle record to the implementation stage, so the next cycle picks the item up.
- **Announcement**: the comment posted before a leg's work begins, telling the maintainer their item was seen. It creates an obligation that an outcome must eventually discharge.
- **Final pull request**: the pull request finalize opens from the specification branch to the default branch. It is the artifact a maintainer reviews, and after this feature it is a long-lived artifact refreshed across loops rather than a one-shot output.
- **Refresh**: the finalize path that updates an existing open final pull request and re-presents it — as distinct from the create path that opens one and from the skip path that leaves a merged or closed one alone.
- **Lifecycle record**: the per-specification machine-readable source of truth for the stage a specification is at. A record left at the implementation stage after a fold has completed is read wrongly by every downstream consumer.
- **Removal capability**: the stage capability that lets an implementation cycle delete a *tracked* file it was asked to delete, leaving the deletion staged like every other write the stage makes. Its absence is why removal-shaped work always leaks to a human. Untracked content stays outside it.
- **Machine-owned region**: the delimited part of a final pull request's description that the pipeline writes and rewrites — a regenerated account of the branch's current state plus an appended per-fold entry. Everything outside the delimiters belongs to whoever wrote it.

## Out of Scope

- **Classification categories and the question / no-action legs.** They behaved correctly on the measured run and are not touched.
- **The stop procedure.** Untouched by this feature; the serialization changes must not alter how a stop request is handled.
- **Automatically merging or approving the refreshed pull request.** A human merges every pull request into the default branch, and this feature only re-presents one for a human to look at.
- **Reopening a closed final pull request, or opening a replacement for one.** A deliberately closed pull request stays closed.
- **Changing how many implementation cycles a specification may run in total,** or the convergence cap. This feature changes how many cycles one review starts, not how many a specification may have.
- **Reworking the per-specification serialization scheme in general.** Only the specific contention between a review's own act pass and the implementation it dispatches is in scope.
- **A general removal capability for other stages.** Only the implementation cycle, its retry, and the convergence pass gain it.
- **Removing files that are not tracked.** Deferred until a task demonstrates the need; until then such removals stay a reported hard stop rather than a widening of the published tool surface.
- **Preserving human edits made inside the machine-owned region of a pull request body.** That region belongs to the pipeline and is overwritten on every refresh; human prose belongs outside the delimiters.
- **The watchdog.** It observes runs through its own channel and is unchanged.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A review carrying three or more in-scope items produces exactly one implementation dispatch — down from one per item — and zero cancelled legs, measured on a re-run of the observed shape.
- **SC-002**: The number of review items that are announced but never folded, and never reported as unfolded, falls to zero.
- **SC-003**: Every announced leg has an observable outcome on the pull request thread, on both the healthy and the failed path.
- **SC-004**: After a fold has converged, the specification's lifecycle record reads the review stage rather than the implementation stage, in 100% of runs — up from none today.
- **SC-005**: After a fold has converged, the final pull request's description describes the folded branch, and the maintainer whose review triggered the fold has been asked for a re-review and has been told so on the lifecycle issue.
- **SC-006**: A maintainer who requests changes learns that their feedback has been acted on without polling — the notification arrives on the lifecycle issue and as a re-review request.
- **SC-007**: A merged or deliberately closed final pull request receives no refresh, no record commit, no label change, and no re-review request.
- **SC-008**: Exactly one final pull request exists per specification after any number of finalize runs, and repeated finalize runs with no intervening change produce no duplicate comments or duplicate re-review requests.
- **SC-009**: A task that removes a file completes within the implementation cycle, with zero "remaining manual work" reports attributable to the missing removal capability — down from two observed occurrences.
- **SC-010**: Reintroducing a per-leg dispatch, a skip-on-open-pull-request finalize, or the missing removal capability each fails a check; disabling the new coverage fails a check.
- **SC-011**: The change reaches adopters without any wrapper edit, and every affected stage's declared inputs, outputs, and secrets are unchanged.
- **SC-012**: No path that is quiet today becomes noisy: a healthy review, a first finalize, and a cycle that removes nothing are unchanged in what reaches the pull request thread and the lifecycle issue.
- **SC-013**: Zero implementation cycles are discarded because a review arrived while they were running, and every dispatched cycle starts against a task list that no fold is still writing.

## Assumptions

- The three defects are one feature because they are one journey and they share their touch points. Shipping them separately would mean three passes over the same two workflows and three chances to leave the loop half-closed — the loop is only observable end to end when all three are present.
- The announce-before-work ordering is correct and stays. The fix is that an announcement acquires a guaranteed outcome, not that announcements become conditional on the work succeeding.
- Whether the act pass becomes a single unit over the classified set or stays as serialized legs with the dispatch deferred to the end is a design decision, not a specification one. Either satisfies FR-001 through FR-004; the specification requires the outcome, not the shape.
- A held-for-confirmation leg resolving is a bounded wait in practice. If it is not, the pipeline reports and dispatches what it has rather than holding the whole review indefinitely.
- Waiting for an in-flight implementation cycle costs a maintainer minutes at this repository's cycle lengths, and that latency is worth paying: no agent work is thrown away, and a cycle always runs against a task list it saw whole. Superseding a running cycle would buy the latency back by discarding work already done.
- A re-reviewing maintainer reads two things about a refreshed pull request: what is on the branch now, and what changed in the round they asked for. The machine-owned region carries both, which is why neither full regeneration nor pure appending alone is enough.
- The reviewer to ask for a re-review is the one whose review triggered the fold. If several reviewers requested changes and their items were folded together, all of them are asked.
- The existing empty-diff anomaly handling, the duplicate-dispatch guard, and the closed-lifecycle guard are all correct and are reused as they are; this feature adds paths through finalize rather than reworking its entry conditions.
- The existing one-shot guard reads the pull request's state today only to decide "exists or not". Distinguishing open from merged from closed is new information the refresh needs, and is available from the same place.
- The removal capability is a deliberate widening of the published stage contract rather than something an adopter should have to grant per repository. A stage that cannot complete this repository's own removal-shaped specifications is under-provisioned by default.
- Coverage for these behaviours can be driven against checked-in fixtures rather than live runs, the same way the repository's existing checks reason about workflow conditions and drive shipped logic against modelled inputs.
- The measured run on PR #240 is representative of the shape this feature must handle, and re-running that shape is a fair acceptance test.
