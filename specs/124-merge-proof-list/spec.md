# Feature Specification: The Proof List — Every Merge Into Main, the Runs That Could Show It Working, and What Is on Record

**Feature Branch**: `124-merge-proof-list`

**Created**: 2026-11-19

**Status**: Draft

**Input**: User description: "List, for every merge into main, the runs that could prove it and what is on record: start no run and give no verdict" (lifecycle issue #1144)

**Layer**: consuming instrument (Principle VII). The feature is one repository-only scheduled workflow of this repository and the report it keeps; it adds nothing to the published contract of `workflow_call` stage workflows.

## Background

The constitution (Principle X) and CLAUDE.md say a fix to behaviour that only runs in Actions is proven after merge by re-driving one run, with the evidence recorded on the PR or the issue. Four things prove a merged change today — the board loop's `prove` job, the `prove-after-merge` hand procedure, the scheduled runs, and a feature's `[maintainer]` post-merge tasks — and nothing lists the merges. No place says, for each merge, whether it needed a run, which runs could show it working, or whether anyone wrote a proof down. A proof that was never written looks the same as a change that needed none.

A lookup of the 48 pull requests merged into `main` between 2026-10-15 and 2026-11-16 (lookups only, classified by hand) found: 11 needed no run; 6 needed one by the rule but were reached by no workflow (prose only); of the 31 reached by a workflow, 10 had a hand-written proof naming a run, and 21 had nothing a reader could count as one. The board loop's `prove` job recorded no outcome on any of its own merged fix PRs. The lookup also showed why a list must give no verdict: 3 of the 10 proofs name a run that failed for another cause, one proof is a skipped job, a passing run can miss the change, and several proofs are partial by their own account.

Since #1146 sessions write proofs in a fixed form; the proofs the lookup read were free prose.

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

Answered on #1144 from the owner's answer (chosen in chat on 2026-11-19) to the question raised in round 2 of the spec PR's review (#1148).

- Q: Does a notice the pipeline posts through `github-actions[bot]`, rather than the App, count as a record? → A: It falls under the same rule as the App. Every bot account the pipeline posts as — the pipeline's App and `github-actions[bot]` — counts only when its comment carries the board item marker at step `proven`. This covers the watchdog's lost-findings notice and pr-conversation's similar notice; comments by people and sessions are unchanged (FR-007, FR-009).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - See which entries have a run that could show them working and nothing on record (Priority: P1)

The owner, or a session working the board, opens the proof list's daily report and sees every recent entry (a commit that reached `main`, FR-001) that a run could show working and for which nothing is written down: either a workflow reaches the change and no run of one has finished since the merge, or runs have finished and no comment names one. For each such entry they see the reaching workflows and, for each, how many runs have finished since, by event and conclusion, with the earliest and latest of them, so they can write a proof from a run that already happened instead of dispatching a new one.

**Why this priority**: This is the gap the lookup exposed — 21 of 31 reachable merges had nothing on record, and 4 Spec Kit bumps were promised a proof that never came, though a passing nightly run on a commit containing each existed. Listing them is the whole value of the feature.

**Independent Test**: With a window containing an entry whose changed path a workflow reaches, a later finished run of that workflow on a commit containing the merge, and no comment naming that run, run the workflow and confirm the report lists the entry in state 5 with that workflow, that run counted under its event and conclusion, and that run as both the earliest and the latest.

**Acceptance Scenarios**:

1. **Given** an entry that changed a workflow-reached path and a run of that workflow that finished afterwards on a commit containing the merge, **When** there is no record comment (Key Entities) for it, **Then** the report lists the entry in state 5 ("runs have finished since, and no comment names one"), with, for each reaching workflow, the count of its finished runs by event and conclusion and its earliest and latest run.
2. **Given** an entry that changed a workflow-reached path and no run of any reaching workflow that has finished since on a commit containing it, **When** the list is built, **Then** the report lists the entry in state 4 ("a workflow reaches it, and no run of one has finished since").
3. **Given** an entry whose PR carries a record comment (Key Entities; FR-007, FR-009), **When** the list is built, **Then** the entry is in state 2 and is not in the report's states-4-and-5 section, whatever the conclusion of the run it names.
4. **Given** an entry that changed a lifecycle stage workflow, or a wrapper file the nightly end-to-end run copies, **When** the list is built, **Then** the nightly end-to-end run is among its reaching workflows (FR-005).
5. **Given** a state-5 entry reached by a workflow that has finished hundreds of runs since the merge, **When** the report is built, **Then** that workflow appears once with its counts by event and conclusion and its earliest and latest run, the whole report fits in one issue body, and no entry is dropped; or, when the full detail cannot fit, it is shortened as FR-020 says and no entry is dropped (FR-020).
6. **Given** a commit in state 4 or 5 that reached `main` in the day just before the window starts, **When** the list is built, **Then** it is no longer an entry of the list and is counted in the report's aged-out count; nothing else removes an entry from the states-4-and-5 section except moving to another state (FR-012).
7. **Given** a state-5 entry whose PR or board-item issue carries a comment, posted after the merge and naming a qualifying run, that is one of these — a comment by the pipeline's App with no board item marker, a comment by `github-actions[bot]` with no board item marker, or a comment by anyone under the board item marker at step `prove` — **When** the list is built, **Then** the entry stays in state 5 (FR-007).
8. **Given** two entries in the window with different pull requests that name the same issue, and a comment on that issue that names a qualifying run and only the first entry's pull request, **When** the list is built, **Then** the comment counts for the first entry and not for the second (FR-006).

---

### User Story 2 - Every entry is in exactly one state, decided by code (Priority: P1)

A reader of the list can trust that each entry in the window appears once, in exactly one of five states, and that the same inputs always produce the same state. The states, first that fits:

1. it needs no run;
2. a comment names a run (as defined in FR-006);
3. no workflow reaches the change;
4. a workflow reaches it, and no run of one has finished since;
5. runs have finished since, and no comment names one.

**Why this priority**: The report in Story 1 is only as good as the classification under it. An entry that falls through the states, or lands in two, is the same invisible gap the feature exists to close (Principle IX: the judgment is code, not a prompt).

**Independent Test**: Feed the classifier a fixed set of entries built to land in each of the five states, plus entries built to satisfy two states at once, and confirm each lands in the first state that fits and only there.

**Acceptance Scenarios**:

1. **Given** an entry whose changed paths are all under `docs/` or `specs/`, or are all gate scripts (`.github/scripts/verify-*.py`), **When** it is classified, **Then** it is in state 1, by the same rule the board loop's `prove` job applies today, and no reach scan, run read or comment read decides otherwise. By that rule an entry whose changed paths mix the two kinds is not in state 1, and an entry with no changed paths is.
2. **Given** an entry that changed only prose outside those paths (for example the constitution, CLAUDE.md or the README) that no workflow reaches, **When** it is classified, **Then** it is in state 3.
3. **Given** an entry that both has a comment naming a qualifying run and is reached by no workflow, **When** it is classified, **Then** it is in state 2 (the first that fits).
4. **Given** the same entries, runs and comments, **When** the list is built twice, **Then** both builds put every entry in the same state.
5. **Given** a scheduled or dispatched build, **When** it sets its window, **Then** the window is the 30 days before the build's own time and nothing the report is given can change it; only a test may supply another window, as SC-001 does (FR-011).

---

### User Story 3 - The list reads each entry's own tree (Priority: P2)

When an entry added, renamed or removed a workflow, the list decides which workflows reach the change from the tree as it stood at that merge, not from `main` as it stands today, so a workflow the merge added is counted and one it removed is not credited after the fact.

**Why this priority**: The hand lookup read today's `main` for every merge and so missed paths renamed or removed since; the board loop's `prove` job already reads the merge's own tree. Without this, older entries in the window are classified against the wrong graph.

**Independent Test**: Classify an entry that added a workflow which reaches a path the same entry changed, and confirm that workflow is listed as reaching it; classify an entry whose reaching workflow was deleted by a later commit, and confirm it is still listed as reached.

**Acceptance Scenarios**:

1. **Given** an entry that added a workflow file and changed a path that workflow reaches, **When** the entry is classified, **Then** that workflow is among those reaching the change.
2. **Given** an entry reached by a workflow that a later commit on `main` deleted, **When** the entry is classified, **Then** the deleted workflow is still listed as reaching it.

---

### User Story 4 - It is safe to leave running (Priority: P2)

The owner can leave the proof list running daily without it costing usage window, starting runs, or producing anything but the content of its report section. It never comments on, labels or closes a pull request or an issue, never edits `tasks.md`, never dispatches a workflow, uses no agent, runs only from the default branch, and stops when its kill switch is set.

**Why this priority**: The lookup that motivated this feature was read-only for the same reasons: a comment on a lifecycle issue in `stage:spec`/`stage:clarify`, a final PR or the Spec Kit tracking issue starts a pipeline run, a dispatched run costs Actions minutes, and pipeline agents and local sessions share one usage window.

**Independent Test**: Run the workflow over a window that includes a final PR and a Spec Kit bump; confirm afterwards that it posted no comment, applied no label, closed nothing, dispatched no workflow, invoked no agent, and that its only output was the content of its report section. Dispatch it on a non-default branch and confirm it refuses before reading anything.

**Acceptance Scenarios**:

1. **Given** a dispatch that targets a branch other than the default branch, **When** the workflow starts, **Then** it refuses and publishes no list.
2. **Given** the kill switch is set, **When** the schedule or a dispatch fires, **Then** the workflow stands down and publishes no list.
3. **Given** a normal run, **When** it completes, **Then** its only output is the content of its report section, and it made no other durable write.
4. **Given** a build that completes, **When** a session reads the open "Board status" issue with `gh`, **Then** the proof list is a collapsed section there that shows when it was built (FR-021).
5. **Given** the latest build of the list failed or was paused, or none has run, **When** a reader opens the "Board status" issue, **Then** the section says so and gives the date of the last good build, or says there has never been one; no older list is shown without that notice (FR-021).

---

### Edge Cases

- **A comment names the run that posted it.** The board loop's "proof run never started" notice names the run that posted it (on #1047, for #1051). That notice carries the board item marker, so it is set apart and does not put an entry in state 2 (FR-007).
- **An App notice with no board item marker names a run.** The watchdog's `[Inspected run](<run URL>)` notices name a run but are not proofs; they never count (FR-007).
- **A `github-actions[bot]` notice names a run.** The watchdog's lost-findings notice and pr-conversation's similar notice are posted through `github-actions[bot]`, not the App. They fall under the same bot-account rule and never count unless they carry the board item marker at step `proven` (FR-007).
- **One issue is named by several pull requests.** A tracking, backlog or lifecycle issue that the pull requests of several entries in the window close, name as their board item or belong to collects comments for all of them; the Maintenance backlog issue, which every backlog-line fix PR names as its board item, is one. A comment there counts for an entry only when it also names that entry's pull request (FR-006).
- **A comment names a run that failed, or a skipped job.** It still puts the entry in state 2; the list gives no verdict and does not read a run's conclusion as one (FR-010).
- **A comment names a run that started before the merge, or on a commit that does not contain the merge.** It does not count.
- **A comment is posted before the merge.** It does not count.
- **More runs than one query returns.** The Actions API returns at most 1,000 runs per query and `board-loop.yml` runs hourly; the read of runs is bounded by date so the window is read completely, and a read that cannot be completed fails loudly rather than reporting a partial list as whole (FR-013).
- **The checkout lacks history.** "A commit that contains the merge" needs the history of `main`; a checkout whose own history of `main` is incomplete fails loudly (FR-013). A run whose commit cannot be resolved while that history is complete (for example a pull-request run on a branch deleted since), or a run a comment names that is not a run of this repository, is not a failed read: it does not qualify, and it is set apart and counted (FR-013).
- **An entry reached only through the nightly end-to-end run's copied wrappers.** The scan links the nightly run to two of its copied wrappers only because the workflow happens to name them; FR-005 makes the rest explicit.
- **An entry no run can show working, or the owner decides needs no proof** (for example #1082). It stays in state 4 or 5 until it leaves the window; see FR-012.
- **A pull request that names no issue.** Only the PR's own comments (and, for a final PR, its lifecycle issue's) are read; nothing fails. An issue the pull request closes or names that was closed before the merge is still read (FR-006).
- **An entry with no pull request** (a direct push to `main`). It is an entry of its own, classified by the same rule; it has no PR comments to read.

## Requirements *(mandatory)*

### Functional Requirements

#### The list

- **FR-001**: The system MUST keep one list of the entries within the window (FR-011). An entry is a commit on `main`'s first-parent line, with its pull request when it has one; a direct push is an entry of its own. An entry's merge time is when it reached `main`, and "the merge" in this spec is that event.
- **FR-002**: For each entry, the system MUST record whether the change needs a run, by the rule the board loop's `prove` job already applies (`board_prove.actions_only()`), reused from its one home and not copied.
- **FR-003**: For each entry that needs a run, the system MUST record which workflows reach a changed path, by the reach scan the `prove-after-merge` hand procedure already uses (following reusable workflows transitively and counting a literal mention of a changed path). That scan MUST have exactly one home that both the hand procedure and this workflow consume; neither keeps a copy. The list MUST report reach per workflow, not per job.
- **FR-004**: The reach scan MUST read the tree as it stood at that entry's merge (Story 3), so a workflow the merge added is counted and one removed later is still credited.
- **FR-005**: The nightly end-to-end run MUST count as reaching the lifecycle stage workflows whose copies its wrappers run, so an entry that changed a stage workflow is listed with the nightly run among its reaching workflows. It also counts as reaching each wrapper file it copies, and whatever those stage workflows reach.
- **FR-006**: For each entry that needs a run, whether or not a workflow reaches it, the system MUST record the comments, posted after the merge, that name an Actions run started after the merge on a commit containing it, each with the account that posted it. For each such entry a workflow reaches, it MUST also record the runs of the reaching workflows that have finished since the merge on a commit that contains it, each with its workflow, event and conclusion. Comments MUST be read on the pull request, on each issue the pull request closes or names as its board item (since #1147 a board-loop fix PR closes no issue and names its item instead: the item's own issue, or for a backlog-line fix the Maintenance backlog issue), and, for a final PR, on its lifecycle issue. An issue is *shared* when more than one pull request among the entries in the window names it in any of those three ways; a comment on a shared issue MUST count toward an entry only when it also names that entry's pull request. (Clarified.)
- **FR-007**: A comment carrying the board item marker MUST count toward FR-006 only when its marker is step `proven`. A comment under the marker at step `prove` (a failed re-drive, a run never started, or any other outcome reason) MUST NOT count, so the loop's own "proof run never started" notice is set apart. A comment posted by any bot account the pipeline posts as — the pipeline's App or `github-actions[bot]` — MUST count only when it carries the board item marker at step `proven`; a comment from either with no board item marker (for example the watchdog's `[Inspected run](<run URL>)` notices, the watchdog's lost-findings notice, or pr-conversation's similar notice) MUST NOT count. Comments posted by people and sessions are not subject to this paragraph's bot-account rule. (Clarified: only step `proven` counts; unmarked comments from the App or `github-actions[bot]` never count.)

#### The states

- **FR-008**: The system MUST place every entry in exactly one of the five states of Story 2, the first that fits, deterministically from the inputs of FR-002 through FR-007.
- **FR-009**: A comment that names a qualifying run, and meets FR-006's shared-issue condition and FR-007's marker and bot-account conditions, MUST count as a record whatever else it says, by whatever person or session posted it; the list records the account and does not judge the comment.

#### What it never does

- **FR-010**: The system MUST give no verdict: it never says a change is proven or not proven, and never reads a run's conclusion as one.
- **FR-011**: The window MUST be the 30 days before the list is built: an entry is in it when its merge time falls within those 30 days. A test may supply the window; the report never does.
- **FR-012**: An entry MUST leave the states-4-and-5 section of the report only by moving to another state or by ageing out of the window, and the report MUST say how many aged out. The aged-out count is worked out from the build's own inputs and time, never from an earlier report: the commits that are in state 4 or 5 and reached `main` in the day just before the window starts. Those commits are classified for this count only, by the rules for an entry as if the window began one day earlier, and are not entries of the list. An entry no run can show working (as on #1082), or one the owner decides needs no proof, has no other way out; the system offers no way to mark it. (Clarified.)
- **FR-013**: A read the system cannot complete — runs past the API's per-query cap, a checkout whose own history of `main` is incomplete, an unreadable comment thread, an unresolvable tree — MUST fail the run loudly and MUST NOT publish a list that silently omits what it could not read (Principle VIII). These are not failed reads: a run whose commit cannot be resolved while `main`'s history is complete, and a run a comment names that is not a run of this repository, do not qualify, and each is set apart and counted. The runs of a reaching workflow that a later commit deleted are read like any other workflow's; a read of them that cannot be completed is a failed read.
- **FR-014**: The system MUST start no run: it dispatches no workflow and re-runs nothing.
- **FR-015**: The proof list's only output MUST be the content of its report section; it makes no other durable write. It never comments on, labels, closes or edits a pull request or an issue, and never edits `tasks.md`.
- **FR-016**: The system MUST use no agent; every step is deterministic code (Principle IX), and it adds nothing to the shared usage window.

#### Running

- **FR-017**: The system MUST run daily on a schedule and on manual dispatch, and MUST refuse any run whose ref is not the default branch before it reads anything, publishing no list.
- **FR-018**: The system MUST carry a kill switch in the `WING_COMMANDER_*_PAUSED` family that stands it down with no list published. Creating the repository variable is the owner's.
- **FR-019**: The system MUST be repository-only: one wrapper of this repository, not a `workflow_call` stage of the published contract.
- **FR-020**: The report MUST list every entry in states 4 and 5 with its reaching workflows. For a state-5 entry it gives, for each reaching workflow, the count of its finished runs by event and conclusion and its earliest and latest run (FR-006 still records every finished run for the classifier). The report MUST give the count of entries in each of the five states for the window, the aged-out count (FR-012) and the count of runs set apart (FR-013). It MUST fit in one issue body and MUST NOT drop an entry to do so. When the full detail does not fit, the report shortens detail before it drops any entry, down to each entry with only the names of its reaching workflows, and says it was shortened. If even that does not fit, the build fails and FR-021's notice applies.
- **FR-021**: The report MUST be readable by a session through `gh` (a run's step summary alone is not, because `gh` cannot read it). It MUST be published as a collapsed section of the open `disposition:tracking` issue titled "Board status", written by that issue's one writer (`wc_board_status.py publish`), since that issue is rewritten whole daily and a second writer would be overwritten; the proof list supplies the section's content and never writes the issue itself. (Clarified.) The section MUST show when its list was built. When the latest build of the list did not complete (it failed or was paused) or none has run, the section MUST say so and give the date of the last good build (or that there has never been one); no rewrite of the issue shows an older list without that notice. A run refused under FR-017 is not a build and changes nothing the section shows.
- **FR-022**: `docs/reference.md` MUST list the new loop with its schedule, window, kill switch and report location; its "Known limits" section and its description of the board loop's prove step are checked against what the list shows and corrected where they disagree.

### Key Entities

- **Entry**: one commit on `main`'s first-parent line that reached `main` in the window (FR-001) — its SHA, merge time, pull request (if any), the issues that pull request closes or names as its board item, its lifecycle issue (if it is a final PR), its changed paths, and its state.
- **Reaching workflow**: a workflow that, in the entry's own tree, reaches one of its changed paths by the shared scan, or by FR-005.
- **Finished run**: a run of a reaching workflow that finished after the merge on a commit containing it — workflow, run id, event, conclusion, head SHA, start time.
- **Record comment**: a comment posted after the merge, on a place FR-006 names, that names a run started after the merge on a commit containing it (and, on a shared issue, that entry's pull request), and that FR-007 does not set apart — where it was posted, the run it names, the account that posted it, and its board item marker if any.
- **State**: one of the five states of Story 2.
- **Report**: the published view: when it was built, the states-4-and-5 listing, the per-state counts, the aged-out count and the count of runs set apart (FR-020, FR-021).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Given a checked-in record of the pull requests, runs and comments the lookup read, and the 2026-10-15 to 2026-11-16 window supplied for the test only (FR-011), with the loop's own "proof run never started" notice set apart, the list puts all 10 hand-written proofs in state 2 and lists in states 4 and 5 exactly the 21 merges the lookup found nothing for (the 14 with nothing found, the 4 Spec Kit bumps, #1051, #1081 and #1082). The only differences allowed, in either half, are those on a checked-in list of expected differences, each with its reason (the entry's own tree, FR-005, FR-006's shared-issue condition, or a run set apart under FR-013). Any other difference fails.
- **SC-002**: 100% of entries in the window appear in the list exactly once, in exactly one state.
- **SC-003**: Two builds over the same inputs produce the same state for every entry.
- **SC-004**: Across every run, the workflow posts zero comments, applies zero labels, closes zero issues or PRs, dispatches zero workflows and invokes zero agents.
- **SC-005**: A session can read the latest report with `gh` in one command, without opening a run's logs.
- **SC-006**: The need-a-run rule and the reach scan each exist in exactly one place in the repository, and a gate fails if a copy of either reappears (CLAUDE.md "Shared logic has exactly one home").
- **SC-007**: A dispatch from a non-default branch, a set kill switch, and an incomplete read each end the run with no list published (after a set kill switch or an incomplete read the section shows FR-021's notice; a refused dispatch leaves the section unchanged); each has a checked-in fixture.

## Assumptions

- **What counts as a record** is the rule the lookup tested — a comment posted after the merge that names an Actions run started after the merge on a commit containing it — with one added condition the owner chose: on an issue more than one merge in the window names, the comment must also name that merge's pull request (FR-006). It cannot tell a proof from a note, and since the list only lists, that is accepted (filing session's proposed answer, confirmed by the owner; the shared-issue condition added by the owner on 2026-11-19).
- **Window**: 30 days, the span the lookup read (confirmed by the owner).
- **Granularity**: runs are listed by workflow, not by job, because the per-job scan (`scan_job_uses_graph()`) covers one workflow file today (confirmed by the owner).
- **The nightly end-to-end run counts** as reaching the lifecycle stages from the wrappers that run copies (confirmed by the owner; FR-005).
- **Name**: "the proof list", since "prove" names the board loop's step and the hand procedure and "ledger" the review loop's notes and the fold queue (confirmed by the owner).
- How a change is proven does not change: the `prove` job, the `prove-after-merge` procedure and the scheduled runs stay as they are. The `prove` job's stand-down on issue-born fix PRs was fixed by #1147 before this spec; merges after it are where the list can first show whether the job recorded a proof.
- If #1143 (a daily audit of merges) is also built, the two should share one reading of what reached `main` and one report; neither depends on the other.
- The reach scan's known misreads stay as they are apart from FR-005: it over-reads a workflow that only names another workflow's file, and that is accepted for a list that gives no verdict.

### Out of scope (each the owner's call)

- Any verdict on a proof, and anything a verdict would need a pull request to say before it merges (#1142 proposes the reviewer a verdict would lean on).
- Reading the fixed session proof form to tell its outcomes apart. Such a record counts only by the existing rule: it names a qualifying run.
- Starting a run when none is due.
- What follows a failed or missing proof.
- A per-feature "did its job" signal (#1137).
