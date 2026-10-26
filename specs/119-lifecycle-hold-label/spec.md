# Feature Specification: Hold a Lifecycle With One Label, and Check Folded Tasks Before Implement Builds Them

**Feature Branch**: `119-lifecycle-hold-label`

**Created**: 2026-10-22

**Status**: Draft

**Lifecycle issue**: #1066 (split out of spec 116, lifecycle #994, PR #1062, at the owner's direction on 2026-10-19; replaces spec 116's Story 3 and its FR-011 to FR-017)

**Input**: User description: "Hold a lifecycle with one label; check folded tasks before implement builds them (split from spec 116). On #1062, spec 116's Story 3 grew into a hold-and-release protocol of its own (a `/fold-hold proceed|drop|amend|retry` command, a published `fold-hold.yml` release stage and wrapper, hold-state and resolved markers, an open-holds read, a per-lifecycle fold-queue lock, release cancel and explain jobs, drop and dismiss accounting); review passes 6–10 found most of their defects there. Today no lifecycle-level stop exists apart from closing the issue; `stage:stalled` is only a signal; `WING_COMMANDER_LIFECYCLE_REVIEW_GATE_PAUSED` stops only the gate's own folds; `wing-commander-fold-dispatch` checks nothing about the lifecycle's state; `/stop` does nothing on a lifecycle issue. Proposed shape: (1) one lifecycle hold label, distinct from `stage:stalled`, checked by implement at the start of every cycle and by `wing-commander-fold-dispatch`; (2) set by fold-time analyze on a constitution conflict, by a maintainer's strict `stop`/`/stop` on the lifecycle issue or its PR, or by hand; (3) released only by paths that already exist — remove the label (proceed), a maintainer-feedback comment then remove (drop), an amendment PR (amend), re-run analyze (retry); (4) fold-time analyze kept from #1062 as a read-only Sonnet job between fold commit and dispatch with deterministic decide, whose only hold action is adding the label. Lessons: a hold must be releasable in an adopter's repo; one label per lifecycle means any open hold blocks all fold dispatches; a dropped task's findings must reach convergence as dismissed; a fold covers only its own commits' tasks.md diff; the analyze agent runs in its own `contents: read` job. Depends on spec 116's convergence stories for the dismissed-fingerprint ledger."

## Context

A lifecycle today has exactly one stop that every stage respects: closing its issue with the `parked` label. That stop is total — it ends every stage, not just implement — and it is meant for lifecycles waiting on the owner for a long time, not for a pause of hours.

Everything short of that is either a signal or a narrower switch:

- `stage:stalled` records that implement failed; no workflow reads it before implement runs again.
- `WING_COMMANDER_LIFECYCLE_REVIEW_GATE_PAUSED` is repository-wide and pauses only the lifecycle review gate (its reviews, folds and auto-merge); it does nothing to implement, to pr-conversation's folds, or to any other stage.
- The fold-dispatch composite (`wing-commander-fold-dispatch`) dispatches implement after a fold commit without asking anything about the lifecycle's state.
- `stop` on a PR (pr-conversation, spec 033) cancels in-flight runs and records nothing, so the next trigger starts work again. The board loop's strict `stop`/`/stop` (specs 057, 097) records `board:stalled`, but board eligibility excludes every issue carrying `stage:*`, `spec:*`, `spec-request` or `spec-proposal`, so it never applies to a lifecycle.

Spec 116 set out to check a review task folded into tasks.md against the spec and the constitution before implement builds it, and to hold the lifecycle for the owner when the check objects. Its hold-and-release protocol grew into a subsystem of its own and drew most of #1062's review defects. This feature keeps the check and replaces the protocol with one label: a lifecycle hold that every consumer of a lifecycle's work reads, that any of three sources may set, and that is released only through paths the pipeline already has.

## Clarifications

Settled by the request (from #994's clarify and owner decisions, carried in by #1066):

- Fold-time analyze holds a lifecycle only on a **constitution conflict** in a newly folded task; any other objection is reported and dispatch proceeds (spec 116 FR-012, clarify on #994).
- The analyze agent runs on **Sonnet** (spec 116 FR-016, moved here; #1066 "a read-only Sonnet job").
- **Any open hold blocks all fold dispatches** for that lifecycle (owner decision 9 on #994). With one label per lifecycle this needs no separate mechanism.
- The analyze agent runs in its **own job with read-only repository contents** (owner decision 15 on #994).
- A fold's check covers **only its own commits' tasks.md diff** (#994 C6).

### Session 2026-10-24 (answers on #1066)

- Q: Should pr-conversation's LLM-classified `stop` on a lifecycle PR also set the hold, or only the strict exact-match form? → A: **Strict exact-match only** (option C). The hold is set only by the exact `stop` / `/stop` form `board_stop_check.py` accepts. When pr-conversation classifies a free-text stop on a lifecycle PR, its reply cancels in-flight runs as it does today and tells the maintainer how to set the hold.
- Q: How does a drop record its dismissal? → A: **Derived from the fold task's removal from tasks.md on the lifecycle branch** (option A). No new state and no new writer of dismissal records; the plan must define a reliable link from a removed fold task back to its finding fingerprints. (The later session's answer B adds pr-conversation's deterministic drop action as the one writer of the tasks.md removal itself; it still records no dismissal state.)
- Q: Is a non-comment answer path needed for drop and amend? → A: **No** (option A). The maintainer-feedback comment (drop) and the amendment PR (amend) are sufficient; the request rules out new commands, markers and labels, so there is one label.

### Session 2026-10-24 (owner, after the spec PR review)

- Q: Removing the label triggers nothing (implement runs only when dispatched); how does a release restart work? → A: **The implement wrapper gains an `issues: unlabeled` trigger filtered to the hold label** (option a). It re-dispatches implement for that lifecycle, so release stays one action. This trigger is allowed under FR-018: it is a trigger on the existing wrapper, not a release stage or release workflow. Adopters update their wrapper to get it (FR-007).
- Q: pr-conversation's feedback path only appends and its agent may not edit tasks.md; who removes a dropped task? → A: **pr-conversation gets a deterministic drop action** (option a): a maintainer's explicit drop names the fold task ids (fold tasks carry no id today; FR-023 names them by the gate's fold title line), and a deterministic step (not the agent) removes exactly those tasks from tasks.md in its own commit. This is the one writer this feature adds; it edits tasks.md and stores nothing else. It runs on a held lifecycle (the hold withholds implement, not the removal).
- Q: No workflow reads a strict `stop` on the lifecycle issue; how is it read? → A: **A deterministic job in the existing pr-conversation wrapper handles issue comments on lifecycle issues** (option a).
- Q: Analyze-retry auto-release needs to know who set the hold, which FR-018 bans recording; what does retry do? → A: **Retry only posts a fresh verdict and never removes the label** (option a); a maintainer releases. The retry reads the constitution from the default branch and spec.md/tasks.md from the lifecycle branch at re-run time.
- Q: Should a hold block the lifecycle review gate's auto-merge? → A: **Yes** (option a): no hold label is one more merge precondition.

### Session 2026-10-26 (owner, after the second spec PR review)

- Q: FR-022 makes "no hold label" a ninth lifecycle-merge condition, but constitution X names "all eight of its gates"; how is that reconciled? → A: **A constitution X amendment PR is filed alongside this feature** (option a), so the count stays exact. The amendment stays human-merged (constitution V); it lands before the final PR that ships FR-022 is merged.
- Q: Keep the default that a strict stop on an issue in `stage:spec`/`stage:clarify` sets the hold and clarify ignores that comment? → A: **Keep it** (FR-024).
- Q: Should held lifecycles appear on the daily Board status report? → A: **Yes, later**: a Maintenance backlog (#889) line after this feature, not part of it (Out of Scope).
- Q: Should `@someone stop` (the shared parser drops a leading handle) set a hold? → A: **Keep the shared parser as it is** (FR-020); a wrong hold costs one label removal (Assumptions).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A maintainer holds a lifecycle and implement stops building until they release it (Priority: P1)

A maintainer sees a lifecycle going the wrong way — a fold they disagree with, a task they want to discuss — and wants implement to stop building without closing the issue and stopping every other stage. They put the lifecycle on hold by adding the hold label to the lifecycle issue, or by posting a strict `stop` or `/stop` on the lifecycle issue or its PR. From then on no implement cycle does any work for that lifecycle and no fold dispatches implement. When they are ready they remove the label and the lifecycle carries on from where it was.

**Why this priority**: Every other story depends on a hold that is actually respected. Without it, fold-time analyze has nothing to set and the release paths have nothing to release. It is also valuable alone: today a maintainer has no stop short of parking.

**Independent Test**: On a lifecycle in `stage:implement`, add the hold label and trigger an implement cycle and a fold dispatch; confirm neither builds anything and both say why on the lifecycle issue. Remove the label and trigger again; confirm implement runs.

**Acceptance Scenarios**:

1. **Given** a lifecycle in `stage:implement` with no hold, **When** a maintainer adds the hold label to its issue and an implement cycle then starts, **Then** that cycle makes no commit, opens no PR, invokes no agent, and posts one status line on the lifecycle issue naming the hold as the reason.
2. **Given** a held lifecycle, **When** a fold commit lands and the fold-dispatch composite runs, **Then** it does not dispatch implement and records that the dispatch was withheld because of the hold.
3. **Given** a lifecycle with no hold, **When** a maintainer posts a comment that `board_stop_check.is_stop_command` accepts (its first-line command form: `stop` or `/stop`, optionally with a reason such as `stop: wrong file`; never prose) on the lifecycle issue or on the lifecycle's PR, **Then** the hold label is added to the lifecycle issue and an acknowledgement naming the release path is posted there.
4. **Given** a lifecycle with no hold, **When** a non-maintainer or a bot posts `stop`, or a maintainer posts a comment that merely contains the word "stop" in other text, **Then** no hold is set.
5. **Given** a lifecycle with no hold, **When** a maintainer posts free text on the lifecycle's PR that pr-conversation classifies as `stop` but that is not the strict form, **Then** no hold is set, in-flight runs are cancelled as today, and the reply tells the maintainer how to set the hold.
6. **Given** a held lifecycle whose implement is due (FR-007: in `stage:implement`, held at a review-gate fold under `stage:review`, or held before its first cycle), **When** a maintainer removes the hold label, **Then** the label-removed trigger dispatches the next implement cycle (FR-007) with no further action, that cycle and any later fold dispatch proceed as if the hold had never been set, and the release is noted on the lifecycle issue.
7. **Given** a held lifecycle whose implement run was already past its start check when the hold was set, **When** that run finishes, **Then** its work stands, and the next cycle observes the hold.

---

### User Story 2 - A folded task that conflicts with the constitution is held for the owner before implement builds it (Priority: P2)

When the lifecycle review gate folds review findings into tasks.md as new tasks, a read-only check compares just those newly folded tasks against the spec and the constitution. If deterministic code decides a folded task conflicts with the constitution, the lifecycle is held with the same label as Story 1, and the question — which task, which principle, the check's reasoning, and the four release paths — is posted on the lifecycle issue. Any other objection is posted for the record and the fold dispatches as usual.

**Why this priority**: This is the failure spec 116 set out to prevent, but spec 116 itself records it as "reasoning about the mechanism, not an observed failure". It depends on Story 1's hold and adds a model invocation per fold.

**Independent Test**: Fold a task that plainly contradicts a NON-NEGOTIABLE principle (for example, one that has the bot merge a spec PR); confirm the lifecycle is held, the question is posted, and implement is not dispatched. Fold an ordinary task; confirm dispatch proceeds and no hold is set.

**Acceptance Scenarios**:

1. **Given** a fold commit whose tasks.md diff adds tasks, **When** fold-time analyze runs, **Then** it reads only the tasks added by that fold's own commits (not earlier folds' tasks, not the whole tasks.md) together with spec.md and the constitution, and produces a structured verdict per task.
2. **Given** a verdict that names a constitution conflict for a folded task, **When** the deterministic decide step evaluates it, **Then** the hold label is added, the question is posted on the lifecycle issue, and implement is not dispatched for that fold.
3. **Given** a verdict that objects to a task without naming a constitution conflict, or names a principle that does not exist, or cites a task the fold did not add, **When** decide evaluates it, **Then** no hold is set, the objection (if well-formed) is posted for the record, and dispatch proceeds.
4. **Given** the analyze agent fails, times out, or returns output that does not match its schema, **When** decide runs, **Then** no hold is set, dispatch proceeds (FR-013), and the failure is reported on the lifecycle issue; it never silently reads as "no conflict".
5. **Given** a fold with no tasks.md diff, **When** the fold runs, **Then** analyze is not invoked and dispatch proceeds.
6. **Given** a fold on a lifecycle that is already held, **When** the fold commits, **Then** analyze runs (FR-008) and posts its verdict, but dispatch is withheld by the existing hold regardless of the verdict.

---

### User Story 3 - The owner answers a hold through paths that already exist (Priority: P2)

The owner reads the held question and chooses one of four answers, each through a path the pipeline already has, with no new command, stage or release workflow:

- **Proceed** — build the task as written: remove the hold label.
- **Drop the task** — post a maintainer-feedback comment on the lifecycle PR that names the fold task(s) to drop; pr-conversation's deterministic drop action removes exactly those tasks from tasks.md (FR-023). Then remove the label.
- **Amend** — change the spec or the constitution through an amendment PR; once it is merged, remove the label.
- **Retry the check** — re-run the fold-time analyze job of the fold's lifecycle review gate run (GitHub's re-run of that job), for example after an amendment, to get a fresh verdict posted; if it finds no conflict, remove the label. A retry never removes the label itself.

**Why this priority**: Without a documented answer path the hold from Story 2 is a dead end; but every path is reuse, so the work is mostly wiring and wording.

**Independent Test**: For each of the four answers, start from a held lifecycle created by Story 2 and confirm that taking only the listed actions leaves the lifecycle unheld and implement building the expected task list.

**Acceptance Scenarios**:

1. **Given** a hold set by fold-time analyze, **When** the hold question is posted, **Then** it names all four answers and the exact action for each, worded so it is usable in an adopting repository (no reference to this repository's own wrappers or labels other than the hold label itself).
2. **Given** a held lifecycle, **When** the owner drops the task via a maintainer-feedback comment and then removes the label, **Then** the next implement cycle does not build the dropped task, and the findings that produced the dropped task count as **dismissed** (derived from the removal, FR-017; nothing is recorded) so the review gate does not re-raise them as recurrences.
3. **Given** a held lifecycle, **When** the fold's analyze job is re-run, **Then** it reads the constitution from the default branch and spec.md and tasks.md from the lifecycle branch as they are at re-run time, posts a fresh verdict on the lifecycle issue, and does **not** remove the hold label, whatever the verdict and whoever set the hold.
4. **Given** a held lifecycle, **When** a maintainer posts a drop naming an unchecked fold task the fold added, **Then** that task is removed from tasks.md by the deterministic drop action in its own commit even though the lifecycle is held, and implement is not dispatched until the label is removed.
5. **Given** an adopting repository whose implement wrapper carries the label-removed trigger (FR-007), **When** a lifecycle there is held, **Then** a maintainer can release it by removing the label alone; in one whose wrapper predates the trigger, removing the label and then dispatching implement by hand releases it.

---

### Edge Cases

- **Label added twice / by two sources**: setting a hold on an already-held lifecycle is idempotent; the second source's reason is posted but no second label or state is created.
- **Hold set mid-cycle**: implement checks at the start of each cycle only; a cycle already past that check finishes (User Story 1, scenario 7). A hold never cancels a running cycle; a maintainer who wants that uses pr-conversation's existing `stop` on the lifecycle's PR as well, or, before finalize has opened that PR, cancels the run in Actions.
- **Hold vs. `stage:stalled`**: the two labels are independent. A stalled lifecycle may also be held; removing one never removes the other.
- **Hold vs. `parked`**: closing a held lifecycle as parked leaves the label in place; reopening it keeps it held until the label is removed.
- **Label removed by a non-maintainer**: GitHub permits only users with triage access or above to change labels, and this feature treats any of them as a maintainer for releasing a hold (Assumptions); the release note on the lifecycle issue names who removed it.
- **Fold covering several commits**: analyze sees the union of the tasks.md additions in that fold's commits only (#994 C6).
- **Two folds in quick succession**: implement runs one cycle per spec at a time, and the hold is checked where the work is consumed, so a fold that dispatches after another fold's hold was set is withheld without a lock.
- **Drop comment that does not remove the task**: a drop that names no fold task, or names a task that is not an unchecked fold task still present in tasks.md (a checked-off fold task is already built), removes nothing and says so in its reply; if the label is then removed, implement builds the task and nothing records it as dismissed (only a removal made by the drop action counts).
- **Strict stop on a PR or issue that belongs to no lifecycle**: no hold is set; existing pr-conversation and board-loop behaviour is unchanged, and the issue-comment job of FR-005 does nothing on an issue that is not a lifecycle issue or for a bot's comment.
- **Strict stop on a lifecycle issue in spec or clarify**: the hold is set there as in any stage, and clarify does not treat the stop comment as an answer to its questions or start a run for it (FR-024; the hold matters from implement on; see "Hold set before implement").
- **Label removed while no implement is due**: the label-removed trigger dispatches implement only when implement is due (FR-007); on a lifecycle still in spec, clarify, plan or tasks with no merged tasks.md, a parked or closed one, a `stage:stalled` one (stall recovery is unchanged), or one with no spec branch it does nothing but note the release. The trigger ignores removal of any other label and removal on an issue that is not a lifecycle issue. A second dispatch while a cycle runs queues and no-ops on implement's idempotency guard.
- **Held at merge time**: a lifecycle PR whose round came back clean is not auto-merged while the hold label is on its lifecycle issue, or while the labels cannot be read (FR-022); the gate's readiness report says the hold is why.
- **Kill switch**: `WING_COMMANDER_LIFECYCLE_REVIEW_GATE_PAUSED` continues to pause the whole lifecycle review gate, so while it is set no gate fold and no fold-time analyze runs (a retry included); it neither sets nor clears the hold.
- **Hold set before implement**: a lifecycle held during spec, clarify, plan or tasks runs those stages as usual (Out of Scope); implement's first cycle observes the hold at its start check.
- **Implement dispatched by another path**: implement's own next-iteration dispatch, fold-cycle-guard's re-dispatch and a manual dispatch do not pass through the fold-dispatch composite; implement's start check (FR-002) is what holds them.
- **Held cycle vs. stall and loss detection**: a cycle that ends at the hold check pushes no commits by design. It is not a failure: implement does not apply `stage:stalled` for it, and the watchdog does not read it as lost progress, a stall or a pipeline defect (FR-021).
- **Fold-queue ticket on a withheld dispatch**: a fold dispatch withheld by the hold, or an implement cycle that ends at the hold check, still releases any fold-queue ticket (spec 074) it carried, so later folds for the spec are not left waiting on a ticket no run will release (FR-003).
- **Fold task changed rather than dropped**: a fold task that implement checks off, that a maintainer rewords, or that leaves tasks.md through a rebase's conflict resolution or any path other than the drop, is not a dismissal; when the derivation cannot attribute a removal to a drop, it is not a dismissal (FR-017). A drop commit the rebase stage replays onto the default branch is still a drop. A finding with several unchecked fold tasks is dismissed only when all of them were dropped; an earlier fold task already checked off (the case behind every `Recurring review finding:` task) does not block the dismissal.
- **Retry after the re-run window, or after release**: GitHub re-runs a job only for a limited time; after that, retry is unavailable and the other three answers stand. A retry re-run after the maintainer released may set the hold again if it still finds a conflict (FR-016); it never removes it.
- **Same-titled fold tasks**: two findings with the same title in different files fold as two tasks with the same title line; a drop that removes only one of them dismisses neither fingerprint (FR-017).
- **Drop comment also read as feedback**: the comment the drop action handles is not also classified and folded by pr-conversation's agent as maintainer feedback (FR-023), so a drop never comes back as a new task.
- **Hold label on lifecycle PRs**: intake, plan, tasks and finalize copy the lifecycle issue's labels onto the PRs they open; they MUST NOT copy the hold label (FR-001), so a PR never shows a hold its issue does not carry, and removing a label from a PR releases nothing.
- **Label removals that are not a release**: the `issues: unlabeled` trigger starts an implement-wrapper run for every label removal on any issue, which skips at once; a caller that looks up the implement run it just dispatched MUST filter to `workflow_dispatch` runs, so such a run is never mistaken for it (FR-007).
- **Stop author who cannot release**: the parser's association check accepts `COLLABORATOR`, which includes read-only collaborators, so such a collaborator can set a hold they cannot remove; the acknowledgement names that a maintainer with triage access releases it.

## Requirements *(mandatory)*

### Functional Requirements

**The hold (Story 1)**

- **FR-001**: The pipeline MUST define exactly one lifecycle hold label (default name `lifecycle:held`), distinct from `stage:stalled` and `parked`, whose presence on a lifecycle issue means "build nothing for this lifecycle until a maintainer releases it". The hold lives on the lifecycle issue only: the steps that copy the issue's labels onto the PRs the stages open MUST skip it.
- **FR-002**: The implement stage MUST read the hold label from a freshly fetched view of the lifecycle issue at the start of every cycle, before invoking any agent or writing anything, and while it is set MUST end the cycle without commits, pushes, PRs, agent invocations or dispatches (no next iteration and no finalize), posting one status line on the lifecycle issue that names the hold.
- **FR-003**: The fold-dispatch composite MUST read the hold label before dispatching implement and MUST withhold the dispatch while it is set, reporting it as an output whose caller records the withheld dispatch on the lifecycle issue (the composite holds no issue-write credential). A withheld dispatch, and an implement cycle that ends at the hold check, MUST release any fold-queue ticket (spec 074) it carried.
- **FR-004**: The hold check MUST be deterministic code (constitution IX), MUST fail closed when the lifecycle issue's labels cannot be read (treat as held, and say that the labels could not be read, distinct from a hold, so a maintainer does not look for a label to remove, naming how to resume: dispatching implement by hand once the labels can be read, since no label removal will restart it and the withheld run's fold-queue ticket was released (FR-003), so re-running that run is not a resume), and MUST receive the lifecycle issue number as a declared input in any published stage or composite (constitution VII).
- **FR-005**: A maintainer's comment on a lifecycle issue or on a lifecycle's PR (its implementation PR from the spec branch to the default branch, the only PR pr-conversation acts on, which exists once finalize opens it; the issue path read by a deterministic job in the existing pr-conversation wrapper, on issue comments to lifecycle issues, ignoring non-lifecycle issues; no agent) that passes the strict stop parser already used by `board_stop_check.py` (`is_stop_command`'s first-line command form, whose accepted and rejected forms its module docstring lists, from an author with the `OWNER`, `MEMBER` or `COLLABORATOR` association that parser's callers check) and is not from a bot (checked by the caller; the parser does not check it) MUST set the hold label on the lifecycle issue and post an acknowledgement naming how to release it. Only this strict form sets the hold (constitution IX: a classifier's judgement never gates a durable action). When pr-conversation's LLM-classified `stop` category fires on a lifecycle PR for a comment that is not the strict form, it MUST NOT set the hold; its reply cancels in-flight runs as today and tells the maintainer how to set the hold (post exactly `stop` or `/stop`, or add the hold label).
- **FR-006**: Setting the hold MUST be idempotent: a second source adds no second label and creates no additional state, but its reason is posted.
- **FR-007**: Removing the hold label MUST be a sufficient release on its own, with no command, marker or release workflow required. The implement wrapper (consuming instrument, constitution VII) MUST carry an `issues: unlabeled` trigger, filtered to the hold label, that dispatches the next implement cycle for that lifecycle when implement is due — the lifecycle is open, not parked and not `stage:stalled`, and it has a spec branch whose `spec-meta.json` records stage `tasks` (held before its first cycle) or `implement` (mid-loop, or after a review-gate fold, whose fold commit sets it back to `implement` while the issue may still carry `stage:review`); the issue's stage label does not decide it, so a lifecycle at spec-meta stage `review` with no withheld fold is not due — with the chaining inputs (spec directory, issue, and the iteration implement's idempotency guard expects next from the recorded spec-meta state) derived from the lifecycle rather than from the event, which carries none, so the release needs no second action. Callers that look up the implement run they dispatched MUST filter to `workflow_dispatch` runs, since the trigger adds a run for every label removal. An adopter whose wrapper predates this trigger releases by removing the label and then dispatching implement by hand; the adoption docs MUST say to add the trigger. The release MUST be noted on the lifecycle issue.

**Fold-time analyze (Story 2)**

- **FR-008**: After a lifecycle review gate fold commits and before it dispatches implement, a fold-time analyze job MUST run when that fold's own commits change tasks.md, and MUST NOT run when they do not.
- **FR-009**: The analyze agent's input MUST be limited to the tasks added by that fold's own commits (the fold's tasks.md diff, not earlier folds and not the whole file), spec.md, and the constitution.
- **FR-010**: The analyze agent MUST run in its own job with read-only repository contents and no write-capable credential, with an explicit `claude-sonnet-5-5` model and a bounded turn budget (constitution II), and MUST produce output against a declared schema naming, per objected task, the task, whether it is a constitution conflict, the principle cited, and its reasoning.
- **FR-011**: A deterministic decide step, not the agent, MUST determine whether to hold. It MUST hold only when a well-formed verdict names a constitution conflict, the cited principle exists in the constitution the agent read, and the cited task is one the fold added.
- **FR-012**: When decide holds, it MUST add the hold label (its only hold action), withhold dispatch, and post on the lifecycle issue the task, the principle, the agent's reasoning, and the four release paths of FR-015. Objections that do not meet FR-011 MUST be posted for the record and MUST NOT block dispatch.
- **FR-013**: When the analyze agent fails, times out, or returns output that does not match its schema, decide MUST report the failure on the lifecycle issue and MUST NOT treat it as "no conflict" silently. Default behaviour: dispatch proceeds and the failure is reported, since analyze guards a failure mode that has not been observed and a failing check must not stall every fold; this is recorded as an assumption below.
- **FR-014**: Every failure branch the decide step ships (hold, record-only objection, malformed verdict, unknown principle, task not in the fold, agent failure, no tasks.md diff) MUST be exercised by a checked-in fixture (constitution VIII).

**Release paths (Story 3)**

- **FR-015**: The hold question MUST name four answers, each through an existing path: **proceed** (remove the label), **drop** (maintainer-feedback comment on the lifecycle PR to remove the task, then remove the label), **amend** (amendment PR, then remove the label), **retry** (re-run the fold-time analyze job of that fold's lifecycle review gate run for a fresh verdict, then remove the label if no conflict remains). It MUST be worded so it applies in an adopting repository.
- **FR-016**: Re-running fold-time analyze on the same fold MUST post a fresh verdict on the lifecycle issue and MUST NOT remove the hold label, whatever the verdict and whoever set the hold; only a maintainer releases. The re-run MUST read the constitution from the default branch and spec.md and tasks.md from the lifecycle branch at re-run time (so it sees a merged amendment), and its task set is the fold's own additions still present in tasks.md. Jobs that re-run with it in a later attempt of the run may set the hold again on a conflict, never remove it, and MUST NOT dispatch implement, post a second review or round record, or attempt the merge: a retry's only effects are the verdict and, on a conflict, the label.
- **FR-017**: The findings that produced a dropped task MUST reach the convergence signals of spec 116 as **dismissed** fingerprints, so a later review round's matching finding is not counted as a recurrence. The dismissal MUST be derived deterministically from the fold task's removal from tasks.md on the lifecycle branch: no new stored state, and nothing records the dismissal itself (the drop action of FR-023 removes the task; the dismissal is read from that removal). Each folded task MUST therefore carry a reliable link back to the finding fingerprints that produced it, so a removed fold task resolves to its fingerprints; the plan defines that link, building on the gate's existing fold record (its marker's `folded_fingerprints` and the tasks.md title match its disposition step already uses) rather than a second mapping. Only a removal made by the drop action's own commit (FR-023) counts, and the derivation MUST tell that commit apart by something an agent-authored commit cannot reproduce, not by its message alone (constitution IX), and that attribution MUST survive the rebase stage replaying the drop commit onto the default branch; the plan fixes how. A task checked off, reworded, or removed by a rebase's conflict resolution, by implement, or by any other commit is not a dismissal; a fingerprint with several unchecked fold tasks is dismissed only when all of them were dropped, and a fold task already checked off (so a `Recurring review finding:` task's earlier fold) does not block it; and when a removed task's title matches more than one folded fingerprint, a fingerprint is dismissed only when every unchecked fold task carrying its title was dropped. A dismissed fingerprint raised again is not a recurrence, and the gate MUST also neither fold it again nor count it as an open in-scope finding of the round, so a drop is not undone by the next round. The derived set is what the lifecycle gate passes as `evaluate`'s `dismissed` list, and this feature updates spec 116's `contracts/convergence-signals.md`, which today says no loop feeds that list.
- **FR-018**: No new command (no `/fold-hold`), published stage workflow, release wrapper, hold-state or resolved marker, additional label, open-holds read, or per-lifecycle fold-queue lock MAY be introduced for holds, and no answer path beyond those of FR-015 (no review-comment or label-based drop); the maintainer-feedback comment (drop) and the amendment PR (amend) are the only non-label answer paths. No state beyond the label itself is introduced; the dismissal of FR-017 is derived from tasks.md, not stored. Allowed, by owner decision (2026-10-24): the `issues: unlabeled` trigger on the existing implement wrapper (FR-007), the issue-comment job in the existing pr-conversation wrapper (FR-005), and the deterministic drop action (FR-023), the one new writer.

**Shared logic and gates**

- **FR-019**: The hold check MUST have one home (a composite or shared script) consumed by implement and fold-dispatch, and setting the hold (FR-006's idempotent add and posted reason) MUST have one home consumed by its three setters (the issue-comment job, pr-conversation's strict-stop path and analyze's decide step); a gate MUST fail when a consumer stops calling either or when a second copy of either appears in a workflow (CLAUDE.md "Shared logic has exactly one home").
- **FR-020**: The strict stop parsing MUST reuse `board_stop_check.py`'s parser rather than a copy.
- **FR-021**: An implement cycle that ends at the hold check (FR-002), including a fail-closed read (FR-004), MUST end in an outcome that implement's stall handling and the watchdog read as held, not as a failure, a stall or lost progress: it MUST NOT apply `stage:stalled` and MUST NOT lead the watchdog to file or report a defect. A fixture MUST show a held cycle's run is not classified as lost progress.
- **FR-022**: The lifecycle review gate's merge preconditions MUST include "the lifecycle issue does not carry the hold label", read from a freshly fetched view at merge time and failing closed when the labels cannot be read, and the readiness report MUST name the hold as the unmet condition. This feature updates spec 062's `contracts/readiness-and-merge.md`, which today defines `may_merge` as the conjunction of eight conditions, and a constitution X amendment (human-merged, constitution V) changes "all eight of its gates" to name the hold condition; that amendment MUST be merged before the final PR that ships this requirement.
- **FR-023**: pr-conversation MUST implement the drop as a deterministic step, not an agent action: from a maintainer's feedback comment on the lifecycle PR it reads the fold tasks the comment names (fold tasks carry no task id today, only the `Review finding:` / `Recurring review finding:` title line the gate writes; the plan fixes the accepted form, parsed deterministically, without adding a task id or marker), removes exactly those tasks from tasks.md when each is an unchecked fold task still present, and commits the removal alone in its own commit that identifies it as a drop, through the fold-queue ticket and push path pr-conversation's feedback folds already use (spec 074), so it is serialized with folds and the implement cycles they dispatch without a new lock. A comment the drop action handles MUST NOT also be classified and folded by pr-conversation's agent as maintainer feedback. It MUST run while the lifecycle is held, MUST NOT dispatch implement on a held lifecycle (FR-003), MUST reply naming what it removed and what it refused, and MUST be the only removal FR-017 counts. Each branch (removed, unknown task, not a fold task, already checked off, already absent, non-maintainer) MUST have a checked-in fixture.

- **FR-024**: clarify MUST NOT treat a comment that sets the hold under FR-005 as an answer to its questions, and MUST NOT start a run for it, on a lifecycle issue in `stage:spec` or `stage:clarify`.

### Key Entities

- **Lifecycle hold**: the presence of the hold label on a lifecycle issue. Attributes: when it was set and the posted reason (analyze, strict stop or by hand); who set it is not recorded as state, since nothing releases by provenance (FR-016). It is the only hold state; there is at most one per lifecycle.
- **Fold-time analyze verdict**: the agent's structured output for one fold — per objected task: task id/text, constitution-conflict flag, cited principle, reasoning. Consumed only by the deterministic decide step.
- **Dismissed fingerprint**: a finding fingerprint whose fold task the owner dropped, derived from that task's removal from tasks.md on the lifecycle branch via the task's link to its fingerprints (not stored separately); read by spec 116's convergence signals so it never matches as a recurrence.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In 100% of implement cycles and fold dispatches started while a lifecycle carries the hold label, nothing is built or dispatched for that lifecycle, demonstrated by fixtures and by one re-driven run after merge.
- **SC-002**: A maintainer can hold a lifecycle in one action (one comment or one label) and release it in one action (removing the label), in this repository and in an adopting repository whose implement wrapper carries FR-007's trigger.
- **SC-003**: A folded task that contradicts a constitution principle in a fixture is held before implement is dispatched in 100% of fixture runs; an ordinary folded task is never held.
- **SC-004**: The feature adds no new published stage workflow, no new slash command, and no hold-state marker; the published contract grows by at most the inputs needed to pass the lifecycle issue number and hold label name and the fold-dispatch composite's withheld output (FR-003), plus the shared homes of FR-019; the consuming instrument adds the implement wrapper's label-removed trigger and the pr-conversation wrapper's lifecycle-issue comment job (and clarify's skip of a hold-setting comment, FR-024).
- **SC-005**: After a drop that FR-017 counts as a dismissal, the review gate's next round reports zero recurrences for the findings behind that task and folds none of them again.
- **SC-006**: Every failure branch of the hold check and the decide step is covered by a checked-in fixture that fails when the branch is removed.

## Assumptions

- The default label name is `lifecycle:held`; the name is consumer-configurable in the same way other pipeline labels are, and the owner may rename it at clarify.
- Fold-time analyze failing (FR-013) reports and lets dispatch proceed rather than holding; spec 116 recorded the guarded failure as unobserved, and holding every fold on a flaky check would block more work than it protects.
- implement already runs one cycle per spec at a time (per-spec concurrency group), so a start-of-cycle check closes the dispatch race without a lock (#1066).
- Only users with triage access or above can add or remove labels on GitHub; the feature treats them all as maintainers for releasing a hold, so label changes need no further authorization check.
- Spec 116's convergence stories are on main (#1062). `wc_convergence.py`'s `evaluate` already takes a `dismissed` list and subtracts it from recurrences and counts, but no loop passes one today (spec 116 `contracts/convergence-signals.md`); this feature supplies that list by derivation from tasks.md (FR-017), not by writing new state.
- The board loop's eligibility exclusions are unchanged: a lifecycle still never enters the board loop; this feature only reuses the strict stop parser.
- The strict stop parser is reused unchanged (FR-020), including its documented acceptance of a first line that starts with an @handle (`@alice stop`): such a comment from a maintainer sets a hold, and releasing a hold set that way costs one label removal (owner decision 2026-10-26).
- pr-conversation's existing `stop` behaviour on PRs (cancel in-flight runs) is unchanged by this feature, except that on a lifecycle PR its reply to a classified (non-strict) `stop` also tells the maintainer how to set the hold (FR-005).

## Out of Scope

- Holding a lifecycle in stages other than implement, fold-dispatch and the review gate's auto-merge (intake, clarify, plan, tasks and finalize continue to run; parking remains the total stop).
- Cancelling an implement run already in progress when a hold is set.
- The shared reviewer-judgement procedure (spec 116 Story 5).
- Any change to `stage:stalled` semantics or to the board loop's `board:stalled`.
- Listing held lifecycles on `board-status.yml`'s daily Board status report (wanted later; tracked on the Maintenance backlog, #889).
