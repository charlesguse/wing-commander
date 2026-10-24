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
- `WING_COMMANDER_LIFECYCLE_REVIEW_GATE_PAUSED` is repository-wide and stops only the lifecycle review gate's own folds.
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
- Q: How does a drop record its dismissal? → A: **Derived from the fold task's removal from tasks.md on the lifecycle branch** (option A). No new state and no new writer; the plan must define a reliable link from a removed fold task back to its finding fingerprints.
- Q: Is a non-comment answer path needed for drop and amend? → A: **No** (option A). The maintainer-feedback comment (drop) and the amendment PR (amend) are sufficient; the request rules out new commands, markers and labels, so there is one label.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A maintainer holds a lifecycle and implement stops building until they release it (Priority: P1)

A maintainer sees a lifecycle going the wrong way — a fold they disagree with, a task they want to discuss — and wants implement to stop building without closing the issue and stopping every other stage. They put the lifecycle on hold by adding the hold label to the lifecycle issue, or by posting a strict `stop` or `/stop` on the lifecycle issue or its PR. From then on no implement cycle does any work for that lifecycle and no fold dispatches implement. When they are ready they remove the label and the lifecycle carries on from where it was.

**Why this priority**: Every other story depends on a hold that is actually respected. Without it, fold-time analyze has nothing to set and the release paths have nothing to release. It is also valuable alone: today a maintainer has no stop short of parking.

**Independent Test**: On a lifecycle in `stage:implement`, add the hold label and trigger an implement cycle and a fold dispatch; confirm neither builds anything and both say why on the lifecycle issue. Remove the label and trigger again; confirm implement runs.

**Acceptance Scenarios**:

1. **Given** a lifecycle in `stage:implement` with no hold, **When** a maintainer adds the hold label to its issue and an implement cycle then starts, **Then** that cycle makes no commit, opens no PR, invokes no agent, and posts one status line on the lifecycle issue naming the hold as the reason.
2. **Given** a held lifecycle, **When** a fold commit lands and the fold-dispatch composite runs, **Then** it does not dispatch implement and records that the dispatch was withheld because of the hold.
3. **Given** a lifecycle with no hold, **When** a maintainer posts a comment whose body is exactly `stop` or `/stop` (the strict form `board_stop_check.py` already accepts) on the lifecycle issue or on the lifecycle's PR, **Then** the hold label is added to the lifecycle issue and an acknowledgement naming the release path is posted there.
4. **Given** a lifecycle with no hold, **When** a non-maintainer or a bot posts `stop`, or a maintainer posts a comment that merely contains the word "stop" in other text, **Then** no hold is set.
5. **Given** a lifecycle with no hold, **When** a maintainer posts free text on the lifecycle's PR that pr-conversation classifies as `stop` but that is not the strict form, **Then** no hold is set, in-flight runs are cancelled as today, and the reply tells the maintainer how to set the hold.
6. **Given** a held lifecycle, **When** a maintainer removes the hold label, **Then** the next implement cycle or fold dispatch proceeds as if the hold had never been set, and the release is noted on the lifecycle issue.
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
6. **Given** a fold on a lifecycle that is already held, **When** the fold commits, **Then** analyze may run and post its verdict, but dispatch is withheld by the existing hold regardless of the verdict.

---

### User Story 3 - The owner answers a hold through paths that already exist (Priority: P2)

The owner reads the held question and chooses one of four answers, each through a path the pipeline already has, with no new command, stage or release workflow:

- **Proceed** — build the task as written: remove the hold label.
- **Drop the task** — post a maintainer-feedback comment on the lifecycle PR asking for the task to be removed (pr-conversation already edits tasks.md), then remove the label.
- **Amend** — change the spec or the constitution through an amendment PR; once it is merged, remove the label.
- **Retry the check** — re-run the analyze workflow, for example after an amendment, which releases the hold itself if no conflict remains.

**Why this priority**: Without a documented answer path the hold from Story 2 is a dead end; but every path is reuse, so the work is mostly wiring and wording.

**Independent Test**: For each of the four answers, start from a held lifecycle created by Story 2 and confirm that taking only the listed action leaves the lifecycle unheld and implement building the expected task list.

**Acceptance Scenarios**:

1. **Given** a hold set by fold-time analyze, **When** the hold question is posted, **Then** it names all four answers and the exact action for each, worded so it is usable in an adopting repository (no reference to this repository's own wrappers or labels other than the hold label itself).
2. **Given** a held lifecycle, **When** the owner drops the task via a maintainer-feedback comment and then removes the label, **Then** the next implement cycle does not build the dropped task, and the findings that produced the dropped task are recorded as **dismissed** so the review gate does not re-raise them as recurrences.
3. **Given** a held lifecycle, **When** the analyze workflow is re-run and decide finds no constitution conflict among the same fold's tasks, **Then** the hold label is removed by that run and dispatch proceeds.
4. **Given** a hold set by a maintainer's `stop` or by hand (not by analyze), **When** analyze is re-run and finds no conflict, **Then** the hold is **not** removed: analyze releases only holds it set.
5. **Given** an adopting repository that does not use this repository's wrappers, **When** a lifecycle there is held, **Then** a maintainer can release it by removing the label alone.

---

### Edge Cases

- **Label added twice / by two sources**: setting a hold on an already-held lifecycle is idempotent; the second source's reason is posted but no second label or state is created.
- **Hold set mid-cycle**: implement checks at the start of each cycle only; a cycle already past that check finishes (User Story 1, scenario 7). A hold never cancels a running cycle; a maintainer who wants that uses pr-conversation's existing `stop` on the PR as well.
- **Hold vs. `stage:stalled`**: the two labels are independent. A stalled lifecycle may also be held; removing one never removes the other.
- **Hold vs. `parked`**: closing a held lifecycle as parked leaves the label in place; reopening it keeps it held until the label is removed.
- **Label removed by a non-maintainer**: GitHub permits only users with triage access or above to change labels, so this is a maintainer action by construction; the release note on the lifecycle issue names who removed it.
- **Fold covering several commits**: analyze sees the union of the tasks.md additions in that fold's commits only (#994 C6).
- **Two folds in quick succession**: implement runs one cycle per spec at a time, and the hold is checked where the work is consumed, so a fold that dispatches after another fold's hold was set is withheld without a lock.
- **Drop comment that does not remove the task**: if the label is removed but the task is still present in tasks.md, implement builds it; nothing records it as dismissed (only a drop that actually removed the task counts).
- **Strict stop on a PR that belongs to no lifecycle**: no hold is set; existing pr-conversation and board-loop behaviour is unchanged.
- **Kill switch**: `WING_COMMANDER_LIFECYCLE_REVIEW_GATE_PAUSED` continues to stop the gate's folds; it neither sets nor clears the hold.

## Requirements *(mandatory)*

### Functional Requirements

**The hold (Story 1)**

- **FR-001**: The pipeline MUST define exactly one lifecycle hold label (default name `lifecycle:held`), distinct from `stage:stalled` and `parked`, whose presence on a lifecycle issue means "build nothing for this lifecycle until a maintainer releases it".
- **FR-002**: The implement stage MUST read the hold label from a freshly fetched view of the lifecycle issue at the start of every cycle, before invoking any agent or writing anything, and while it is set MUST end the cycle without commits, pushes, PRs or agent invocations, posting one status line on the lifecycle issue that names the hold.
- **FR-003**: The fold-dispatch composite MUST read the hold label before dispatching implement and MUST withhold the dispatch while it is set, recording the withheld dispatch on the lifecycle issue.
- **FR-004**: The hold check MUST be deterministic code (constitution IX), MUST fail closed when the lifecycle issue's labels cannot be read (treat as held and say why), and MUST receive the lifecycle issue number as a declared input in any published stage or composite (constitution VII).
- **FR-005**: A maintainer's comment on a lifecycle issue or on a lifecycle's PR that passes the strict stop parser already used by `board_stop_check.py` (exact `stop` or `/stop`, maintainer author, not a bot) MUST set the hold label on the lifecycle issue and post an acknowledgement naming how to release it. Only this strict form sets the hold (constitution IX: a classifier's judgement never gates a durable action). When pr-conversation's LLM-classified `stop` category fires on a lifecycle PR for a comment that is not the strict form, it MUST NOT set the hold; its reply cancels in-flight runs as today and tells the maintainer how to set the hold (post exactly `stop` or `/stop`, or add the hold label).
- **FR-006**: Setting the hold MUST be idempotent: a second source adds no second label and creates no additional state, but its reason is posted.
- **FR-007**: Removing the hold label MUST be a sufficient release on its own in any repository, with no command, marker, wrapper or release workflow required; the release MUST be noted on the lifecycle issue by the next run that observes it.

**Fold-time analyze (Story 2)**

- **FR-008**: After a lifecycle review gate fold commits and before it dispatches implement, a fold-time analyze job MUST run when that fold's own commits change tasks.md, and MUST NOT run when they do not.
- **FR-009**: The analyze agent's input MUST be limited to the tasks added by that fold's own commits (the fold's tasks.md diff, not earlier folds and not the whole file), spec.md, and the constitution.
- **FR-010**: The analyze agent MUST run in its own job with read-only repository contents and no write-capable credential, with an explicit `claude-sonnet-5-5` model and a bounded turn budget (constitution II), and MUST produce output against a declared schema naming, per objected task, the task, whether it is a constitution conflict, the principle cited, and its reasoning.
- **FR-011**: A deterministic decide step, not the agent, MUST determine whether to hold. It MUST hold only when a well-formed verdict names a constitution conflict, the cited principle exists in the constitution the agent read, and the cited task is one the fold added.
- **FR-012**: When decide holds, it MUST add the hold label (its only hold action), withhold dispatch, and post on the lifecycle issue the task, the principle, the agent's reasoning, and the four release paths of FR-015. Objections that do not meet FR-011 MUST be posted for the record and MUST NOT block dispatch.
- **FR-013**: When the analyze agent fails, times out, or returns output that does not match its schema, decide MUST report the failure on the lifecycle issue and MUST NOT treat it as "no conflict" silently. Default behaviour: dispatch proceeds and the failure is reported, since analyze guards a failure mode that has not been observed and a failing check must not stall every fold; this is recorded as an assumption below.
- **FR-014**: Every failure branch the decide step ships (hold, record-only objection, malformed verdict, unknown principle, task not in the fold, agent failure, no tasks.md diff) MUST be exercised by a checked-in fixture (constitution VIII).

**Release paths (Story 3)**

- **FR-015**: The hold question MUST name four answers, each through an existing path: **proceed** (remove the label), **drop** (maintainer-feedback comment on the lifecycle PR to remove the task, then remove the label), **amend** (amendment PR, then remove the label), **retry** (re-run the analyze workflow). It MUST be worded so it applies in an adopting repository.
- **FR-016**: Re-running fold-time analyze on the same fold MUST remove the hold label if decide no longer finds a conflict, but only when the current hold was set by analyze; a hold set by `stop` or by hand MUST NOT be released by analyze.
- **FR-017**: The findings that produced a dropped task MUST reach the convergence signals of spec 116 as **dismissed** fingerprints, so a later review round's matching finding is not counted as a recurrence. The dismissal MUST be derived deterministically from the fold task's removal from tasks.md on the lifecycle branch: no new stored state and no new writer (neither pr-conversation nor a maintainer action records it). Each folded task MUST therefore carry a reliable link back to the finding fingerprints that produced it, so a removed fold task resolves to its fingerprints; the plan defines that link.
- **FR-018**: No new command (no `/fold-hold`), published stage workflow, release wrapper, hold-state or resolved marker, additional label, open-holds read, or per-lifecycle fold-queue lock MAY be introduced for holds, and no answer path beyond those of FR-015 (no review-comment or label-based drop); the maintainer-feedback comment (drop) and the amendment PR (amend) are the only non-label answer paths. No state beyond the label itself is introduced; the dismissal of FR-017 is derived from tasks.md, not stored.

**Shared logic and gates**

- **FR-019**: The hold check MUST have one home (a composite or shared script) consumed by implement and fold-dispatch, and a gate MUST fail when either consumer stops calling it or when a second copy of the check appears in a workflow (CLAUDE.md "Shared logic has exactly one home").
- **FR-020**: The strict stop parsing MUST reuse `board_stop_check.py`'s parser rather than a copy.

### Key Entities

- **Lifecycle hold**: the presence of the hold label on a lifecycle issue. Attributes: who or what set it (analyze, strict stop, by hand), when, and the posted reason. It is the only hold state; there is at most one per lifecycle.
- **Fold-time analyze verdict**: the agent's structured output for one fold — per objected task: task id/text, constitution-conflict flag, cited principle, reasoning. Consumed only by the deterministic decide step.
- **Dismissed fingerprint**: a finding fingerprint whose fold task the owner dropped, derived from that task's removal from tasks.md on the lifecycle branch via the task's link to its fingerprints (not stored separately); read by spec 116's convergence signals so it never matches as a recurrence.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In 100% of implement cycles and fold dispatches started while a lifecycle carries the hold label, nothing is built or dispatched for that lifecycle, demonstrated by fixtures and by one re-driven run after merge.
- **SC-002**: A maintainer can hold a lifecycle in one action (one comment or one label) and release it in one action (removing the label), in this repository and in an adopting repository.
- **SC-003**: A folded task that contradicts a constitution principle in a fixture is held before implement is dispatched in 100% of fixture runs; an ordinary folded task is never held.
- **SC-004**: The feature adds no new published stage workflow, no new slash command, and no hold-state marker; the published contract grows by at most the inputs needed to pass the lifecycle issue number and hold label name.
- **SC-005**: After a task is dropped, the review gate's next round reports zero recurrences for the findings behind that task.
- **SC-006**: Every failure branch of the hold check and the decide step is covered by a checked-in fixture that fails when the branch is removed.

## Assumptions

- The default label name is `lifecycle:held`; the name is consumer-configurable in the same way other pipeline labels are, and the owner may rename it at clarify.
- Fold-time analyze failing (FR-013) reports and lets dispatch proceed rather than holding; spec 116 recorded the guarded failure as unobserved, and holding every fold on a flaky check would block more work than it protects.
- implement already runs one cycle per spec at a time (per-spec concurrency group), so a start-of-cycle check closes the dispatch race without a lock (#1066).
- Only maintainers can add or remove labels on GitHub, so label changes need no further authorization check.
- Spec 116's convergence stories (#1062, after the split) land first and provide the dismissed-fingerprint set this feature feeds (data-model: "Dismissed fingerprints are kept in a separate set and never match recurrence"); this feature contributes to that set by derivation from tasks.md (FR-017), not by writing new state.
- The board loop's eligibility exclusions are unchanged: a lifecycle still never enters the board loop; this feature only reuses the strict stop parser.
- pr-conversation's existing `stop` behaviour on PRs (cancel in-flight runs) is unchanged by this feature, except that on a lifecycle PR its reply to a classified (non-strict) `stop` also tells the maintainer how to set the hold (FR-005).

## Out of Scope

- Holding a lifecycle in stages other than implement and fold-dispatch (intake, clarify, plan, tasks, finalize continue to run; parking remains the total stop).
- Cancelling an implement run already in progress when a hold is set.
- The shared reviewer-judgement procedure (spec 116 Story 5).
- Any change to `stage:stalled` semantics or to the board loop's `board:stalled`.
