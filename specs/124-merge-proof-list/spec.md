# Feature Specification: The Proof List — Every Merge Into Main, the Runs That Could Show It Working, and What Is on Record

**Feature Branch**: `124-merge-proof-list`

**Created**: 2026-11-19

**Status**: Draft

**Input**: User description: "List, for every merge into main, the runs that could prove it and what is on record: start no run and give no verdict" (lifecycle issue #1144)

**Layer**: consuming instrument (Principle VII). The feature is one repository-only scheduled workflow of this repository and the report it keeps; it adds nothing to the published contract of `workflow_call` stage workflows.

## Background

The constitution (Principle X) and CLAUDE.md say a fix to behaviour that only runs in Actions is proven after merge by re-driving one run, with the evidence recorded on the PR or the issue. Four things prove a merged change today — the board loop's `prove` job, the `prove-after-merge` hand procedure, the scheduled runs, and a feature's `[maintainer]` post-merge tasks — and nothing lists the merges. No place says, for each merge, whether it needed a run, which runs could show it working, or whether anyone wrote a proof down. A proof that was never written looks the same as a change that needed none.

A lookup of the 48 pull requests merged into `main` between 2026-10-15 and 2026-11-16 (lookups only, classified by hand) found: 11 needed no run; 6 needed one by the rule but were reached by no workflow (prose only); of the 31 reached by a workflow, 10 had a hand-written proof naming a run, and 21 had nothing a reader could count as one. The board loop's `prove` job recorded no outcome on any of its own merged fix PRs. The lookup also showed why a list must give no verdict: 3 of the 10 proofs name a run that failed for another cause, one proof is a skipped job, a passing run can miss the change, and several proofs are partial by their own account.

This feature makes that lookup a daily, deterministic list. It changes nothing about how a change is proven.

## Clarifications

### Session 2026-11-19

Answered on #1144 from the owner's decision recorded on the Roadmap issue (#890).

- Q: Does a comment by the pipeline's App count, and under which markers? → A: Only a comment under board item marker step `proven` counts; a step `prove` comment (any outcome reason, including "proof run never started") is set apart (FR-007).
- Q: How does a merge leave the report when no run can show it working, or the owner decides it needs no proof? → A: Only by moving to another state or by ageing out of the window, and the report says how many aged out (FR-012).
- Q: Where does the report live? → A: A collapsed section of the "Board status" issue, written by that issue's one writer (FR-021).
- The five answers the filing session proposed in Assumptions (record rule, 30-day window, per-workflow listing, nightly end-to-end reach, the name "the proof list") were confirmed in the same decision.

Answered on #1144 from the owner's answers (chosen in chat on 2026-11-19) to the two questions raised in round 1 of the spec PR's review (#1148).

- Q: Does a comment by the pipeline's App that carries no board item marker count as a record? → A: No. An App comment counts only when it carries the board item marker at step `proven`; unmarked App notices, such as the watchdog's `[Inspected run](<run URL>)` notices, never count. Comments by people and sessions are unchanged (FR-007, FR-009).
- Q: On an issue that more than one merge names, does one qualifying comment count for every merge that names it? → A: No. On an issue that more than one merge in the window names, a comment counts for a merge only when it also names that merge's pull request. This adds a condition to the confirmed record rule (FR-006, FR-009, Assumptions).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - See which merges have a run that could show them working and nothing on record (Priority: P1)

The owner, or a session working the board, opens the proof list's daily report and sees every recent merge into `main` that a run could show working and for which nothing is written down: either a workflow reaches the change and no run of one has finished since the merge, or runs have finished and no comment names one. For each such merge they see the reaching workflows and the finished runs with their event and conclusion, so they can write a proof from a run that already happened instead of dispatching a new one.

**Why this priority**: This is the gap the lookup exposed — 21 of 31 reachable merges had nothing on record, and 4 Spec Kit bumps were promised a proof that never came, though a passing nightly run on a commit containing each existed. Listing them is the whole value of the feature.

**Independent Test**: With a window containing a merge whose changed path a workflow reaches, a later finished run of that workflow on a commit containing the merge, and no comment naming that run, run the workflow and confirm the report lists the merge in state 5 with that run, its event and its conclusion.

**Acceptance Scenarios**:

1. **Given** a merge that changed a workflow-reached path and a run of that workflow that finished afterwards on a commit containing the merge, **When** no comment on the PR, an issue it closes, or (for a final PR) its lifecycle issue names a run started after the merge on a commit containing it, **Then** the report lists the merge in state 5 ("runs have finished since, and no comment names one"), with each such run's workflow, event and conclusion.
2. **Given** a merge that changed a workflow-reached path and no run of any reaching workflow that has finished since on a commit containing it, **When** the list is built, **Then** the report lists the merge in state 4 ("a workflow reaches it, and no run of one has finished since").
3. **Given** a merge whose PR carries a comment, posted after the merge, that names a run started after the merge on a commit containing it, **When** the list is built, **Then** the merge is in state 2 and is not in the report's states-4-and-5 section, whatever that run's conclusion was.

---

### User Story 2 - Every merge is in exactly one state, decided by code (Priority: P1)

A reader of the list can trust that each merge into `main` in the window appears once, in exactly one of five states, and that the same inputs always produce the same state. The states, first that fits:

1. it needs no run;
2. a comment names a run (as defined in FR-006);
3. no workflow reaches the change;
4. a workflow reaches it, and no run of one has finished since;
5. runs have finished since, and no comment names one.

**Why this priority**: The report in Story 1 is only as good as the classification under it. A merge that falls through the states, or lands in two, is the same invisible gap the feature exists to close (Principle IX: the judgment is code, not a prompt).

**Independent Test**: Feed the classifier a fixed set of merges built to land in each of the five states, plus merges built to satisfy two states at once, and confirm each lands in the first state that fits and only there.

**Acceptance Scenarios**:

1. **Given** a merge that changed only `docs/**`, `specs/**` or `verify-*.py` paths, **When** it is classified, **Then** it is in state 1, by the same rule the board loop's `prove` job applies today, and no reach scan, run read or comment read decides otherwise.
2. **Given** a merge that changed only prose outside those paths (for example the constitution, CLAUDE.md or the README) that no workflow reaches, **When** it is classified, **Then** it is in state 3.
3. **Given** a merge that both has a comment naming a qualifying run and is reached by no workflow, **When** it is classified, **Then** it is in state 2 (the first that fits).
4. **Given** the same merges, runs and comments, **When** the list is built twice, **Then** both builds put every merge in the same state.

---

### User Story 3 - The list reads each merge's own tree (Priority: P2)

When a merge added, renamed or removed a workflow, the list decides which workflows reach the change from the tree as it stood at that merge, not from `main` as it stands today, so a workflow the merge added is counted and one it removed is not credited after the fact.

**Why this priority**: The hand lookup read today's `main` for every merge and so missed paths renamed or removed since; the board loop's `prove` job already reads the merge's own tree. Without this, older merges in the window are classified against the wrong graph.

**Independent Test**: Classify a merge that added a workflow which reaches a path the same merge changed, and confirm that workflow is listed as reaching it; classify a merge whose reaching workflow was deleted by a later commit, and confirm it is still listed as reached.

**Acceptance Scenarios**:

1. **Given** a merge that added a workflow file and changed a path that workflow reaches, **When** the merge is classified, **Then** that workflow is among those reaching the change.
2. **Given** a merge reached by a workflow that a later commit on `main` deleted, **When** the merge is classified, **Then** the deleted workflow is still listed as reaching it.

---

### User Story 4 - It is safe to leave running (Priority: P2)

The owner can leave the proof list running daily without it costing usage window, starting runs, or touching anything but its own report. It never comments on, labels or closes a pull request or an issue, never edits `tasks.md`, never dispatches a workflow, uses no agent, runs only from the default branch, and stops when its kill switch is set.

**Why this priority**: The lookup that motivated this feature was read-only for the same reasons: a comment on a lifecycle issue in `stage:spec`/`stage:clarify`, a final PR or the Spec Kit tracking issue starts a pipeline run, a dispatched run costs Actions minutes, and pipeline agents and local sessions share one usage window.

**Independent Test**: Run the workflow over a window that includes a final PR and a Spec Kit bump; confirm afterwards that it posted no comment, applied no label, closed nothing, dispatched no workflow, invoked no agent, and changed only its report. Dispatch it on a non-default branch and confirm it refuses before reading anything.

**Acceptance Scenarios**:

1. **Given** a dispatch that targets a branch other than the default branch, **When** the workflow starts, **Then** it refuses and writes nothing.
2. **Given** the kill switch is set, **When** the schedule or a dispatch fires, **Then** the workflow stands down and writes nothing.
3. **Given** a normal run, **When** it completes, **Then** the only durable write it made is its own report.

---

### Edge Cases

- **A comment names the run that posted it.** The board loop's "proof run never started" notice names the run that posted it (on #1047, for #1051). That notice carries the board item marker, so it is set apart and does not put a merge in state 2 (FR-007).
- **An App notice with no board item marker names a run.** The watchdog's `[Inspected run](<run URL>)` notices name a run but are not proofs; they never count (FR-007).
- **One issue is named by several merges.** A tracking or lifecycle issue that several merges in the window close or belong to collects comments for all of them; a comment there counts for a merge only when it also names that merge's pull request (FR-006).
- **A comment names a run that failed, or a skipped job.** It still puts the merge in state 2; the list gives no verdict and does not read a run's conclusion as one (FR-010).
- **A comment names a run that started before the merge, or on a commit that does not contain the merge.** It does not count.
- **A comment is posted before the merge.** It does not count.
- **More runs than one query returns.** The Actions API returns at most 1,000 runs per query and `board-loop.yml` runs hourly; the read of runs is bounded by date so the window is read completely, and a read that cannot be completed fails loudly rather than reporting a partial list as whole (FR-013).
- **The checkout lacks history.** "A commit that contains the merge" needs the history of `main`; a checkout that cannot answer that fails loudly (FR-013).
- **A merge reached only through the nightly end-to-end run's copied wrappers.** The scan does not connect them today; see FR-005.
- **A merge no run can show working, or the owner decides needs no proof** (for example #1082). It stays in state 4 or 5 until it leaves the window; see FR-012.
- **A pull request that closes no issue, or an issue closed before the merge.** Only the PR's own comments (and, for a final PR, its lifecycle issue's) are read; nothing fails.
- **A merge with no pull request** (a direct push to `main`). It is listed and classified by the same rule; it has no PR comments to read.

## Requirements *(mandatory)*

### Functional Requirements

#### The list

- **FR-001**: The system MUST keep one list of the commits that reached `main` within the window (FR-011), one entry per commit, each with its pull request when it has one.
- **FR-002**: For each entry, the system MUST record whether the change needs a run, by the rule the board loop's `prove` job already applies (`board_prove.actions_only()`), reused from its one home and not copied.
- **FR-003**: For each entry that needs a run, the system MUST record which workflows reach a changed path, by the reach scan the `prove-after-merge` hand procedure already uses (following reusable workflows transitively and counting a literal mention of a changed path). That scan MUST have exactly one home that both the hand procedure and this workflow consume; neither keeps a copy. The list MUST report reach per workflow, not per job.
- **FR-004**: The reach scan MUST read the tree as it stood at that merge (Story 3), so a workflow the merge added is counted and one removed later is still credited.
- **FR-005**: The nightly end-to-end run MUST count as reaching the lifecycle stage workflows whose copies its wrappers run, so a merge to a stage workflow is listed with the nightly run among its reaching workflows.
- **FR-006**: For each entry reached by a workflow, the system MUST record the runs of the reaching workflows that have finished since the merge on a commit that contains it, each with its workflow, event and conclusion; and the comments, posted after the merge, that name an Actions run started after the merge on a commit containing it, each with the account that posted it. Comments MUST be read on the pull request, on each issue the pull request closes, and, for a final PR, on its lifecycle issue. An issue is *shared* when it is named, in one of those two ways, by more than one merge in the window; a comment on a shared issue MUST count toward a merge only when it also names that merge's pull request. (Clarified.)
- **FR-007**: A comment carrying the board item marker MUST count toward FR-006 only when its marker is step `proven`. A comment under the marker at step `prove` (a failed re-drive, a run never started, or any other outcome reason) MUST NOT count, so the loop's own "proof run never started" notice is set apart. A comment posted by the pipeline's App MUST count only when it carries the board item marker at step `proven`; an App comment with no board item marker (for example the watchdog's `[Inspected run](<run URL>)` notices) MUST NOT count. Comments posted by people and sessions are not subject to this paragraph's App rule. (Clarified: only step `proven` counts; unmarked App comments never count.)

#### The states

- **FR-008**: The system MUST place every entry in exactly one of the five states of Story 2, the first that fits, deterministically from the inputs of FR-002 through FR-007.
- **FR-009**: A comment that names a qualifying run, and meets FR-006's shared-issue condition and FR-007's marker and App conditions, MUST count as a record whatever else it says, by whatever person or session posted it; the list records the account and does not judge the comment.

#### What it never does

- **FR-010**: The system MUST give no verdict: it never says a change is proven or not proven, and never reads a run's conclusion as one.
- **FR-011**: The window MUST be the merges into `main` from the last 30 days.
- **FR-012**: A merge MUST leave the states-4-and-5 section of the report only by moving to another state or by ageing out of the window, and the report MUST say how many merges in states 4 and 5 aged out since the previous report. A merge no run can show working (as on #1082), or one the owner decides needs no proof, has no other way out; the system offers no way to mark it. (Clarified.)
- **FR-013**: A read the system cannot complete — runs past the API's per-query cap, a checkout without the history to answer "contains the merge", an unreadable comment thread, an unresolvable tree — MUST fail the run loudly and MUST NOT publish a list that silently omits what it could not read (Principle VIII).
- **FR-014**: The system MUST start no run: it dispatches no workflow and re-runs nothing.
- **FR-015**: The system MUST write only its own report. It never comments on, labels, closes or edits a pull request or an issue, and never edits `tasks.md`.
- **FR-016**: The system MUST use no agent; every step is deterministic code (Principle IX), and it adds nothing to the shared usage window.

#### Running

- **FR-017**: The system MUST run daily on a schedule and on manual dispatch, and MUST refuse any run whose ref is not the default branch before it reads or writes anything.
- **FR-018**: The system MUST carry a kill switch in the `WING_COMMANDER_*_PAUSED` family that stands it down with nothing written. Creating the repository variable is the owner's.
- **FR-019**: The system MUST be repository-only: one wrapper of this repository, not a `workflow_call` stage of the published contract.
- **FR-020**: The report MUST list every merge in states 4 and 5 with its reaching workflows and, for state 5, its finished runs; and MUST give the count of merges in each of the five states for the window.
- **FR-021**: The report MUST be readable by a session through `gh` (a run's step summary alone is not, because `gh` cannot read it). It MUST be published as a collapsed section of the open `disposition:tracking` issue titled "Board status", written by that issue's one writer (`wc_board_status.py publish`), since that issue is rewritten whole daily and a second writer would be overwritten; the proof list supplies the section's content and never writes the issue itself. (Clarified.)
- **FR-022**: `docs/reference.md` MUST list the new loop with its schedule, window, kill switch and report location, and its "Known limits" section and its description of the board loop's prove step ("records the evidence") MUST be corrected to match what the list shows.

### Key Entities

- **Merge entry**: one commit that reached `main` in the window — its SHA, merge time, pull request (if any), the issues that pull request closes, its lifecycle issue (if it is a final PR), its changed paths, and its state.
- **Reaching workflow**: a workflow that, in the merge's own tree, reaches one of its changed paths by the shared scan, or by FR-005.
- **Finished run**: a run of a reaching workflow that finished after the merge on a commit containing it — workflow, run id, event, conclusion, head SHA, start time.
- **Record comment**: a comment posted after the merge, on a place FR-006 names, that names a run started after the merge on a commit containing it (and, on a shared issue, that merge's pull request), and that FR-007 does not set apart — where it was posted, the run it names, the account that posted it, and its board item marker if any.
- **State**: one of the five states of Story 2.
- **Report**: the published view: the states-4-and-5 listing, the per-state counts and the aged-out count.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Over the 2026-10-15 to 2026-11-16 window the lookup read, with the loop's own "proof run never started" notice set apart, the list puts all 10 hand-written proofs in state 2 (less any that FR-006's shared-issue condition sets apart, each explained), and its states-4-and-5 section lists the 21 merges the lookup found nothing for (the 14 with nothing found, the 4 Spec Kit bumps, #1051, #1081 and #1082), less any the merge's own tree or FR-005 now reaches differently, each difference explained.
- **SC-002**: 100% of merges into `main` in the window appear in the list exactly once, in exactly one state.
- **SC-003**: Two builds over the same inputs produce the same state for every merge.
- **SC-004**: Across every run, the workflow posts zero comments, applies zero labels, closes zero issues or PRs, dispatches zero workflows and invokes zero agents.
- **SC-005**: A session can read the latest report with `gh` in one command, without opening a run's logs.
- **SC-006**: The need-a-run rule and the reach scan each exist in exactly one place in the repository, and a gate fails if a copy of either reappears (CLAUDE.md "Shared logic has exactly one home").
- **SC-007**: A dispatch from a non-default branch, a set kill switch, and an incomplete read each end the run with nothing published; each has a checked-in fixture.

## Assumptions

- **What counts as a record** is the rule the lookup tested — a comment posted after the merge that names an Actions run started after the merge on a commit containing it — with one added condition the owner chose: on an issue more than one merge in the window names, the comment must also name that merge's pull request (FR-006). It cannot tell a proof from a note, and since the list only lists, that is accepted (filing session's proposed answer, confirmed by the owner; the shared-issue condition added by the owner on 2026-11-19).
- **Window**: 30 days, the span the lookup read (confirmed by the owner).
- **Granularity**: runs are listed by workflow, not by job, because the per-job scan (`scan_job_uses_graph()`) covers one workflow file today (confirmed by the owner).
- **The nightly end-to-end run counts** as reaching the lifecycle stages from the wrappers that run copies (confirmed by the owner; FR-005).
- **Name**: "the proof list", since "prove" names the board loop's step and the hand procedure and "ledger" the review loop's notes and the fold queue (confirmed by the owner).
- How a change is proven does not change: the `prove` job, the `prove-after-merge` procedure and the scheduled runs stay as they are. Fixing the `prove` job's stand-down (on #889) is separate; this list would show when it is fixed.
- If #1143 (a daily audit of merges) is also built, the two should share one reading of what reached `main` and one report; neither depends on the other.
- The reach scan's known misreads stay as they are apart from FR-005: it over-reads a workflow that only names another workflow's file, and that is accepted for a list that gives no verdict.

### Out of scope (each the owner's call)

- Any verdict on a proof, and anything a verdict would need a pull request to say before it merges (#1142 proposes the reviewer a verdict would lean on).
- A fixed form for a proof record that lets code tell "proven" from "pending" or "no run can show this"; that changes the `prove-after-merge` procedure.
- Starting a run when none is due.
- What follows a failed or missing proof.
- A per-feature "did its job" signal (#1137).
