# Feature Specification: Feature Health — Whether Each Loop and Stage Is Running and Doing Its Job

**Feature Branch**: `126-feature-health`

**Created**: 2026-11-22

**Status**: Draft

**Input**: User description: "Feature health: show whether each loop and stage is running and doing its job" (lifecycle issue #1137)

**Layer**: consuming instrument (Principle VII). The feature reads this repository's own run history and board, and reports in this repository's "Board status" issue. It adds nothing to the published contract of `workflow_call` stage workflows.

## Background

`docs/reference.md` lists a discrete set of features: the lifecycle stages, the review loops, the board loop, the watchdog, auto-release, the Spec Kit updater and the housekeeping workflows. Nothing shows, per feature, whether it is still running and still producing what it exists to produce. A feature that has gone quiet, or that keeps failing, stays invisible until someone happens to look. The owner's example: if the Spec Kit updater stopped running regularly, it would be good to know.

A first cut by hand, over 30 days of run history (2026-10-14 to 2026-11-12, read per workflow), already found things a run result alone hides:

- The private-image dogfood had failed every nightly run since 2026-10-12, and nothing surfaced it.
- No board-loop `fix/` pull request had merged since 2026-10-16, across 771 board loop runs, nearly all of which ended green.
- Spec PR review had produced nothing since it shipped on 2026-11-08 because it is paused, yet each hourly run ended green. A paused or idle loop looks healthy, because its runs end green.
- A run can end green while a step inside it fails (watchdog run 43365022888, 2026-11-13); that defect is already a line on the Maintenance backlog (#889).
- Five event-driven wrappers return only their latest 1,000 runs, so run counts over a window could not be given for them.

The daily "Board status" issue, rewritten by `board-status.yml`, is the natural home: it is already where the owner and sessions look first.

## Clarifications

### Session 2026-11-22

- Q: Which output signal counts as "did its job" for each feature? → A: The proposed per-feature signals (option A); features without one are not measured and are judged on runs and cadence only (FR-003, FR-008).
- Q: When is a feature quiet? → A: Each registry entry declares its own quiet threshold; 14 days is the default for an entry that declares none (option C; FR-007).
- Q: Does a failing, quiet or not-running feature only show, or is something filed? → A: Show only in the Board status report and file nothing (option A), following #1143 and #1144 (FR-009, FR-013, User Story 4).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - See at a glance which features have gone quiet or keep failing (Priority: P1)

The owner, or a session working the board, opens the "Board status" issue and sees, for each feature in the feature registry (FR-001), one health state, the date of its last successful run, the date of its last failed run, and the date of the last time it produced its output signal (FR-003). A feature that is *failing*, *quiet*, *not running*, *paused* or *unreadable* is called out so it is noticed without reading every row (FR-009); *not configured* and *idle* are shown in their rows but not called out.

**Why this priority**: This is the whole value of the feature. The dogfood that failed for a month and the board loop that merged nothing for a month were both findable only by someone going to look.

**Independent Test**: With recorded run history in which one feature's recent runs all failed, a second feature's runs all succeeded but its output signal is older than its quiet threshold, and a third feature is healthy, build the report and confirm the first shows *failing*, the second *quiet*, the third *healthy*, and that the first two are called out.

**Acceptance Scenarios**:

1. **Given** a feature whose latest finished, non-skipped, non-cancelled run, and every such run in its failing window (FR-005), concluded in failure, **When** the report is built, **Then** the feature shows *failing* with the dates of its last success and last failure.
2. **Given** a feature whose runs end green but whose output signal has not occurred within its quiet threshold, **When** the report is built, **Then** the feature shows *quiet*, not *healthy*, and gives the date of its last output signal (or says there has never been one in the window read).
3. **Given** a scheduled feature with no run at all within its expected cadence plus its tolerance (FR-006), **When** the report is built, **Then** the feature shows *not running*.
4. **Given** a feature whose kill switch is set, **When** the report is built, **Then** the feature shows *paused* and names the switch, and its green runs are not read as health.
5. **Given** a feature with at least one finished, non-skipped, non-cancelled run in the window, that ran within its cadence, whose latest non-skipped, non-cancelled run succeeded, and whose output signal occurred within its quiet threshold (or which declares none), **When** the report is built, **Then** the feature shows *healthy*. (Spec review round 2 default, owner-approved 2026-11-22.)
6. **Given** a feature with no finished, non-skipped, non-cancelled run in the window, and either no declared output signal or one that occurred within its quiet threshold, **When** the report is built, **Then** the feature shows *idle*, never *healthy*, and is not called out (FR-017). (Spec review round 2 default, owner-approved 2026-11-22.)

---

### User Story 2 - "Did its job" is measured per feature, not by run result (Priority: P1)

Each feature declares the signal that shows it did its job — for example a merged pull request, a filed issue, a published release, or a record written to the metrics branch — and health is judged on that signal as well as on run results, so a loop whose runs end green while it produces nothing is not reported healthy.

**Why this priority**: A run result shows only that something ran. The board loop's month without a merged fix and spec PR review's paused-but-green runs are exactly what run results hide.

**Independent Test**: Give the classifier a feature whose every run succeeded and whose declared signal has never occurred, and confirm it is not *healthy*; give it a feature with no declared signal and confirm the report says so rather than inventing one.

**Acceptance Scenarios**:

1. **Given** the board loop with hundreds of successful runs in the window, and within its quiet threshold no merged board-loop fix pull request and no issue closed on one of triage's code-derived grounds (FR-003), **When** the report is built, **Then** the board loop is *quiet*.
2. **Given** a feature whose registry entry declares no output signal, **When** the report is built, **Then** its row says the signal is not measured and its state is decided from run results and cadence alone.
3. **Given** the same run history, board and switches, **When** the report is built twice, **Then** every feature gets the same state both times.

---

### User Story 3 - A reading that could not be made never looks healthy (Priority: P2)

When the report cannot read what it needs for a feature — the run history is past the per-query cap and could not be bounded by date, an output signal cannot be queried, a kill switch cannot be read — that feature shows *unreadable* with the reason, never *healthy*, and the rest of the report is still published.

**Why this priority**: Principle VIII. A health report that shows green for a feature it could not read is the exact failure it exists to catch.

**Independent Test**: Feed the build a feature whose run read fails, and confirm that feature shows *unreadable* with its reason, every other feature is still classified, and the report says how many features were unreadable.

**Acceptance Scenarios**:

1. **Given** an event-driven feature whose wrapper has more than 1,000 runs, **When** its runs are read, **Then** the read is bounded by date so the window is read completely, or, if it cannot be, the feature is *unreadable*, never classified from a partial read.
2. **Given** one feature's output signal query fails, **When** the report is built, **Then** that feature is *unreadable* unless a stronger state (*paused*, *not configured*, *failing* or *not running*) applies, in which case it keeps that state and the failure is recorded in the row's reason and shown in its call-out when that state is called out (*not configured* is not); the others are classified normally, and the report gives the count of unreadable features.

---

### User Story 4 - A quiet or failing feature is shown, not filed (Priority: P3)

A feature that enters a called-out state (*failing*, *quiet*, *not running*, *paused* or *unreadable*) is only shown in the report's call-outs (FR-009); the system files nothing for it. The owner, or a session reading Board status, decides whether it becomes a Maintenance backlog line.

**Why this priority**: Showing it is the core value; filing it would cost duplicates, noise and backlog lines for things already known.

**Independent Test**: Build the report over history in which one feature is *failing* across several consecutive builds, and confirm the feature is called out each time while no issue, comment or backlog line is created.

**Acceptance Scenarios**:

1. **Given** a feature that has been *failing* for several consecutive builds, **When** each report is built, **Then** the feature is called out in every build and no filing of any kind (issue, comment, Maintenance backlog line) is made.

---

### Edge Cases

- **A paused loop with green runs.** Spec PR review runs hourly and ends green while paused; it shows *paused*, never *healthy* or *quiet* (FR-004).
- **A feature that is event-driven and legitimately idle.** PR conversation or rebase may have nothing to do for days; their cadence is declared as event-driven, so the absence of runs alone does not make them *not running* (FR-006). One with no finished, non-skipped, non-cancelled run in the window shows *idle*, whether or not it declares a signal, unless a declared signal past its threshold makes it *quiet* (FR-017).
- **A feature whose runs succeed while a step inside fails.** The report reads run conclusions; step-level failures inside a green run are out of scope (that defect is tracked on #889). Its output signal still catches a feature that produces nothing.
- **A feature that is skipped by design.** The private-image dogfood is skipped while its image variable is unset; a run whose jobs were all skipped because the feature is not configured shows *not configured*, not *healthy* and not *failing*.
- **A cancelled or skipped run.** Cancelled runs (for example by a concurrency group), and runs skipped for any reason other than the *not configured* rule above (for example a wrapper whose guard skips its job), are neither a success nor a failure for the state; they count only toward "ran within cadence", and they neither break nor extend a run of failures (FR-005). (Spec review round 2 default, owner-approved 2026-11-22.)
- **The report's own feature.** Board status is itself a feature in the registry; its row reflects the previous build, since the current build is the one writing it.
- **A feature added to `docs/reference.md` without a registry entry.** A gate fails (FR-002), so the registry cannot silently fall behind.
- **The lifecycle spans many workflows.** The feature lifecycle is reported as one feature with each stage as its own row and state beneath it, so a failure in one stage (for example implement) is visible in that stage's row; the lifecycle's own state is the worst of its stages' states (FR-018).
- **A feature built from several workflows.** The watchdog (two wrappers), or a feature whose schedule is separate from its events, takes the worst state among its workflows, each classified from its own runs (FR-018).
- **A workflow only other workflows call.** A called-only workflow such as `agent-startup-check` may have no finished run of its own in the window; it shows *idle*, never *healthy* (FR-017), and when a sibling workflow in the same feature has runs it is left out of the feature's state (FR-018).

## Requirements *(mandatory)*

### Functional Requirements

#### The features

- **FR-001**: The system MUST keep one feature registry with exactly one home. Each entry names a feature, the workflow or workflows whose runs belong to it, its cadence (a schedule, or event-driven), its kill switch if it has one, its output signal if one is declared (FR-003), and its quiet threshold (FR-007). The registry MUST cover at least the features of the issue's first cut: the feature lifecycle (with its stages: intake, clarify, plan, tasks, implement, finalize, cleanup), spec PR review, the lifecycle review gate, PR conversation, the board loop, the watchdog, auto-release, the Spec Kit updater, rebase, metrics, board status, the proof list, the private-image dogfood, and the gate suite.
- **FR-002**: A gate MUST fail when a loop or workflow that `docs/reference.md`'s "At a glance", "Housekeeping and observability" or "Schedules" tables list has no registry entry, or a registry entry names a workflow that does not exist, so the registry cannot drift from the reference page.
- **FR-003**: A registry entry MAY declare an output signal: an observable, countable event that shows the feature did its job, with the time it last occurred. The signals MUST be drawn from what the repository already records, such as a merged pull request of a given kind, an issue filed under a given label, an issue closed, a comment posted, a published release, a record on the metrics branch, or a rewrite of a tracking issue. The registry MUST declare these signals (clarified 2026-11-22, Q1 option A):
  - feature lifecycle → a spec PR or a final PR merged;
  - Spec Kit updater → a bump PR merged;
  - auto-release → a release published;
  - watchdog → an issue filed or an inspected-run notice posted;
  - board loop → a board-loop fix PR merged or an issue closed at triage on one of triage's code-derived grounds (`board_triage.py`: a rate-limited run or an upstream action bump); a duplicate close at the route step does not count;
  - metrics → a record appended to the metrics branch;
  - board status → the "Board status" issue rewritten; proof list → its section rewritten;
  - every other feature → no signal declared: not measured, judged on runs and cadence only (FR-008).

#### The states

- **FR-004**: The system MUST place every registry feature in exactly one state, the first that fits, deterministically from its runs, its kill switch, its configuration and its output signal: *unreadable* (FR-010: a failed run, switch, variable or cron read, or a failed signal read when no stronger state below applies); *paused* (its kill switch is set); *not configured* (it is skipped by design because a variable it requires is unset); *failing* (FR-005); *not running* (FR-006); *quiet* (FR-007); *idle* (FR-017); *healthy* (it has at least one finished, non-skipped, non-cancelled run in the window and fits none of the earlier states). (Spec review round 2 default, owner-approved 2026-11-22.) A feature built from several workflows is classified per FR-018.
- **FR-005**: A feature MUST be *failing* when its latest finished, non-skipped, non-cancelled run concluded in failure and so did every finished, non-skipped, non-cancelled run in its failing window: the last 3 such runs, or all of them if it has fewer. A single failed run between successes does not make a feature *failing*; the report still shows the date of its last failure. A run skipped for any reason other than FR-004's *not configured* rule counts like a cancelled one: it counts toward having run within its cadence (FR-006), but it is neither a success nor a failure, so it neither breaks nor extends a run of failures. (Spec review round 2 default, owner-approved 2026-11-22.)
- **FR-006**: A scheduled feature MUST be *not running* when it has no run started within its schedule's interval plus a tolerance of one further interval. An event-driven feature is never *not running* on the absence of runs alone.
- **FR-007**: A feature with a declared output signal MUST be *quiet* when that signal has not occurred within its quiet threshold. Each registry entry declares its own quiet threshold in days; an entry that declares none gets the default of 14 days (clarified 2026-11-22, Q2 option C). The report shows the threshold applied to each feature with a declared signal.
- **FR-008**: The system MUST NOT read a green run as evidence that a feature did its job; only its declared output signal is that evidence. A feature with no declared signal is judged on runs and cadence only, and its row says the signal is not measured.
- **FR-017**: A feature, or under FR-018 a workflow, MUST be *idle* when it has no finished, non-skipped, non-cancelled run in the window and fits none of FR-004's earlier states, whether or not it declares an output signal: there is no run evidence, so it is never *healthy*. A declared signal past its quiet threshold still makes it *quiet*, which comes earlier in FR-004's order. A feature built from several workflows is *idle* only when all of its workflows are (FR-018). *Idle* is not called out (FR-009). (Spec review round 1 default, not an owner decision; see Assumptions. The run requirement regardless of a declared signal, and the several-workflow rule: Spec review round 2 default, owner-approved 2026-11-22.)
- **FR-018**: Each stage of the feature lifecycle MUST get its own row and its own state beneath the lifecycle's row. A feature whose entry names several workflows (the lifecycle's stages, the watchdog's wrappers, a schedule separate from its events) MUST classify each workflow by FR-004 from that workflow's own runs, with the feature's kill switch, configuration and output signal; FR-005 and FR-006 apply to each workflow's own run stream, and runs are never pooled across workflows. The feature's own state is the worst of its workflows' states, worst meaning earliest in FR-004's order. (Spec review round 1 default, not an owner decision; see Assumptions.) A workflow that is *idle* is left out of the worst-of when a sibling workflow in the same feature has a finished, non-skipped, non-cancelled run in the window; it still shows *idle* in its own row where it has one. The feature is *idle* only if all of its workflows are. (Spec review round 2 default, owner-approved 2026-11-22.)

#### Where it shows and what it does

- **FR-009**: The report MUST be published in the open `disposition:tracking` issue titled "Board status", through that issue's one writer, as the proof list's section is (spec 124, FR-021): the health system supplies the content and never writes the issue itself. The report MUST show one row per feature with its state, its last success, its last failure and its last output signal, and MUST call out, above the rows, every feature in *failing*, *quiet*, *not running*, *paused* or *unreadable*; *not configured* and *idle* are not called out. A feature in a called-out state is only shown in the report: the system files nothing — no Maintenance backlog line and no issue (clarified 2026-11-22, Q3 option A, following the precedent of #1143 and #1144, which report their verdict in Board status and file nothing).
- **FR-010**: A read the system cannot complete for a feature — a run listing past the per-query cap that cannot be bounded by date, a kill switch or configuration variable it cannot read, a scheduled workflow whose cron cannot be found — MUST put that feature in *unreadable* with the reason. A failed output-signal query does the same only when no stronger state (*paused*, *not configured*, *failing*, *not running*) applies; otherwise the feature keeps that state and the failure is recorded in the row's reason. The system MUST NOT classify it from a partial read, and MUST NOT stop the other features from being classified (Principle VIII). The report MUST give the count of unreadable features; that header count covers only features whose state is *unreadable*, not features that kept a stronger state with a signal failure in their reason. If the run history of every feature is unreadable, the build fails and the section says so with the date of the last good build.
- **FR-011**: The window of history read MUST be long enough to cover every feature's quiet threshold and failing window, and MUST be read bounded by date so the 1,000-run cap of event-driven wrappers does not truncate it silently.
- **FR-012**: The system MUST use no agent; every step is deterministic code (Principle IX), and it adds nothing to the shared usage window.
- **FR-013**: The system MUST start no run, and MUST make no durable write other than its report content: it never comments on, labels, closes or edits a pull request or an issue.
- **FR-014**: The section MUST show when it was built. When the latest build did not complete or was paused, the section MUST say so and give the date of the last good build; no rewrite of "Board status" shows an older report without that notice.
- **FR-015**: The system MUST stand down with no new report when `WING_COMMANDER_BOARD_STATUS_PAUSED` is set (it lives inside the Board status rewrite); it adds no new kill switch of its own unless the plan needs a separate workflow, in which case it carries one in the `WING_COMMANDER_*_PAUSED` family, and creating that variable is the owner's.
- **FR-016**: `docs/reference.md` MUST describe the feature-health section in its "Housekeeping and observability" entry for board status, and list any new workflow, schedule or kill switch the plan adds.

### Key Entities

- **Feature**: one entry of the registry — name, the workflows whose runs belong to it, cadence, kill switch, required configuration, output signal, quiet threshold, and, for the feature lifecycle, its stages (each with its own row and state, FR-018).
- **Run**: a finished run of a feature's workflow — workflow, run id, event, start time, conclusion. A cancelled or skipped run (other than *not configured*) counts only toward cadence (FR-005).
- **Output signal**: the declared event that shows a feature did its job, and the time it last occurred.
- **Health state**: one of *unreadable*, *paused*, *not configured*, *failing*, *not running*, *quiet*, *idle*, *healthy*. The called-out states are *failing*, *quiet*, *not running*, *paused* and *unreadable*.
- **Report**: the published section — build time, the call-out list, one row per feature (and one per lifecycle stage beneath the lifecycle), and the count of unreadable features.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Given a checked-in record of the run history, board and switches behind the issue's first cut (2026-10-14 to 2026-11-12), the report shows the private-image dogfood as *failing*, spec PR review as *paused*, the board loop as *quiet* (the window has no merged board-loop fix PR after 2026-10-16 and no issue closed on one of triage's code-derived grounds; the route-step duplicate closes of #1096, #1097, #1101, #1106 and #1116 do not count; under the 14-day default, or any declared quiet threshold shorter than 27 days), and the Spec Kit updater, auto-release and the watchdog as *healthy* (the updater's and both watchdog wrappers' runs in the window are successes and skips with no failure, and each one's latest non-skipped, non-cancelled run is a success, so the skips at the window's end do not change the verdict under FR-005).
- **SC-002**: 100% of registry features appear in the report exactly once, in exactly one state.
- **SC-003**: Two builds over the same inputs give every feature the same state.
- **SC-004**: A feature that stops producing its output signal is shown as *quiet* in the first daily report after its quiet threshold passes, without anyone going to look.
- **SC-005**: A session can read the latest health report with `gh` in one command, without opening a run's logs.
- **SC-006**: No feature is ever shown *healthy* on a read that did not complete; each failure branch (unreadable runs, unreadable signal, unreadable switch) has a checked-in fixture.
- **SC-007**: The feature registry exists in exactly one place, and the gate of FR-002 fails on a checked-in fixture where `docs/reference.md` lists a feature the registry lacks.

## Assumptions

- **Home**: the report is a section of the "Board status" issue, rewritten daily by its one writer, following the precedent spec 124 set for the proof list. Whether it is a full table, a call-out line only for features that need attention, or both, is settled here as *both*: the call-outs above, the full table collapsed beneath, since the issue already carries collapsed sections.
- **Failing window**: the last 3 non-skipped, non-cancelled runs all failed; a skipped run (other than *not configured*) counts like a cancelled one (FR-005; spec review round 2 default, owner-approved 2026-11-22). One failure among successes is shown by its date but does not change the state.
- **Not running tolerance**: one extra schedule interval, so a single skipped or delayed scheduled run does not flag a feature.
- **Event-driven features** (PR conversation, rebase on push, cleanup on PR close, the watchdog per stage run, metrics-persist per stage run, the gate suite on pull requests) are judged by their output signal and run results, never by the absence of runs; where they also have a schedule (rebase nightly, cleanup daily, metrics daily sweep, the gate suite daily on `main`), that schedule's cadence applies.
- **No runs is *idle*** (FR-017; spec review round 1 default, not an owner decision; extended by spec review round 2 default, owner-approved 2026-11-22): a feature or workflow with no finished, non-skipped, non-cancelled run in the window shows *idle*, never *healthy*, whether or not it declares a signal, unless a declared signal past its threshold makes it *quiet*. It is not called out. The owner may change this, for example to *unreadable* or to a called-out state.
- **Several workflows, worst state wins** (FR-018; spec review round 1 default, not an owner decision): each lifecycle stage gets its own row and state, and a feature built from several workflows takes the worst of its workflows' states, each classified from its own runs; an *idle* workflow is left out of the worst-of when a sibling has runs, so the feature is *idle* only if all its workflows are (spec review round 2 default, owner-approved 2026-11-22). The owner may change this, for example to pooling runs or to stage rows without a combined state.
- **Run conclusions only**: step-level failures inside a green run are out of scope; that defect is already tracked on #889.
- **Window read**: at least 30 days, the span of the first cut, extended as needed to cover the longest quiet threshold.
- **Nothing changes about the features themselves**: this feature observes; it does not restart, re-run, unpause or fix anything.

### Out of scope

- Fixing any feature the report shows unhealthy (the dogfood's causes are already lines on #889; #1139 fixes the first).
- Detecting a step that failed inside a run that ended green.
- Cost or usage-window accounting per feature (the metrics records already carry it).
- Health of an adopter's wrappers: an adopter that pins the published stages gets none of this.
