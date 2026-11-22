# Feature Specification: The Merge Evidence Audit — One Watching Verdict for Every Pull Request Into Main, and a Daily List of What Reached It

**Feature Branch**: `125-merge-evidence-audit`

**Created**: 2026-11-21

**Status**: Draft

**Input**: User description: "One merge-evidence workflow for every pull request into main: it records and audits, and never merges or blocks" (lifecycle issue #1143)

**Layer**: consuming instrument (Principle VII). The feature is one repository-only workflow of this repository, the verdict records it keeps and the audit it reports; it adds nothing to the published contract of `workflow_call` stage workflows.

## Background

Five kinds of pull request reach `main` today, and each is decided and evidenced differently:

| Pull request | Who presses merge | What decides | Where the evidence is recorded |
|---|---|---|---|
| Board loop fix PR | the board loop's `merge` job while its switch is on, otherwise a human | the board loop's merge conditions (eight) | the App's review verdict, and a merge outcome marker on the PR |
| Spec Kit bump PR | the same job | the bump's merge conditions (seven) | the App's verification record, confirmed against the Actions run it names |
| Final PR of a lifecycle | the lifecycle review gate's `merge` job while its switch is on (off here), otherwise a human | the lifecycle merge preconditions (eight in code, nine in Principle X) | a `lifecycle-review-gate` commit status, and a marker on the lifecycle issue |
| A session's own fix PR | the session, on the owner's standing instruction of 2026-11-13 | a rule in CLAUDE.md, and no code | the separate session's report, a comment on the PR |
| Spec PR, constitution amendment, any other PR | a human | nothing in code | none required |

Nothing can answer "what was the evidence when this commit reached `main`?" for every merge. A merge by a human records nothing; a session's merge of its own fix PR is checked by nothing outside the session (`docs/reference.md`, "Known limits"); `main` has no ruleset and no branch protection; and because sessions merge under the owner's account, the merging account cannot tell a session's merge from the owner's.

A lookup of the 48 pull requests merged into `main` from 2026-10-15 to 2026-11-16 (lookups only, nothing posted) found: 9 spec PRs, 9 final PRs, 21 session or owner PRs, 6 Spec Kit bumps and 3 board loop fix PRs; 44 merged under the owner's account and 4 by the App. CI checks were green on all 39 that had any; the 9 spec PRs had none at merge time. A clean, pipeline-written record naming exactly the merged commit existed for 6 (four bump verifications, two board loop review verdicts); a session-written clean record for 14 more; for 3, the clean pass itself pushed the merged commit afterwards; 25 had neither, including all spec and final PRs. #1140 merged after three passes, none clean, by the owner's recorded choice.

The owner's direction (2026-11-16): keep the existing merge jobs, and add a workflow that watches merges into `main` and only records what it finds. This feature is that workflow. It changes no existing merge decision, and nothing waits on its verdict.

## Clarifications

### Session 2026-11-22

- Q: For a pull request with no checks at all (every spec PR today), is the verdict "unmet: no checks", or are missing checks reported separately as not applicable? → A: Unmet. "No checks on the head" is the first unmet condition for any kind; spec PRs show as unmet until #1141 moves them off `main` or a check is added (FR-006).
- Q: What starts a verdict run? → A: A schedule over every open pull request into `main`, hourly rather than every 30 minutes (each job costs at least one Actions minute), plus manual dispatch; a pull request merged between two runs gets only a reconstructed verdict (FR-016).
- Q: How long does the watching period run, and what ends it? → A: A fixed 30 days; when it ends the owner reviews the audit and decides the next step, including whether the merge jobs read the verdict (FR-024).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - See, for an open pull request into main, whether its merge evidence is there on the exact head (Priority: P1)

The owner, or a session about to merge, looks up the verdict for a pull request into `main` and sees, for its current head commit: the kind the audit assigned it, every condition that kind needs with its result, and the first one unmet. The verdict was computed by deterministic code from a complete snapshot fetched fresh for that head, so it can be trusted to describe that commit and no earlier one.

**Why this priority**: This is the one question the feature exists to answer. The daily audit (Story 2) reads these verdicts; without them it has nothing to list.

**Independent Test**: With an open board loop fix PR whose head has green checks, a gate-suite run, and an App-posted clean review verdict naming that head, run the workflow and confirm a verdict record exists for that head naming kind "board loop fix PR", every condition met, and no first-unmet condition. Push a new commit and confirm the next verdict is recorded against the new head and does not count the earlier review verdict.

**Acceptance Scenarios**:

1. **Given** an open pull request into `main` whose head has green checks, the gate suite among them, and the evidence its kind needs (FR-007), **When** the verdict is computed, **Then** a verdict record is written for that head naming the commit, the kind, each condition as met, and no first-unmet condition.
2. **Given** a board loop fix PR whose App-posted review verdict names an earlier commit, **When** the verdict is computed for the current head, **Then** the review-evidence condition is unmet and is reported as naming a different commit.
3. **Given** a Spec Kit bump PR whose verification record names an Actions run that the Actions API does not confirm (wrong workflow, wrong head, not successful, or not found), **When** the verdict is computed, **Then** the verification condition is unmet and the reason is named.
4. **Given** a final PR whose most recent lifecycle review gate round was recorded at the current head and came back clean with zero open in-scope findings, **When** the verdict is computed, **Then** the review-evidence condition is met.
5. **Given** a pull request whose only review evidence is a comment posted under a maintainer's account (a session's pass report, a decision record), **When** the verdict is computed, **Then** that comment is listed in the verdict as reported and the review-evidence condition is not counted as met by it (FR-009).
6. **Given** a snapshot that could not be fetched completely (a page missing, a call refused), **When** the verdict is computed, **Then** the verdict says it is incomplete and names what could not be read, and no condition is reported as met on data that was not read (FR-005).
7. **Given** a pull request of any kind, a spec PR among them, with no checks on its head, **When** the verdict is computed, **Then** the checks condition is unmet and "no checks on the head" is reported as the first unmet condition (FR-006).

---

### User Story 2 - Read a daily audit of everything that reached main (Priority: P1)

Once a day the owner reads one list: each pull request merged into `main` since the last audit, with the verdict at the merged commit as of the moment it merged, the account that merged it, and any commit that reached `main` without a pull request.

**Why this priority**: The owner's direction is to watch merges into `main`. The audit is the watching; it is what turns a gap such as "25 of 48 merges had no record" from a one-off lookup into a standing view.

**Independent Test**: In a window containing one merged pull request with a recorded verdict at its merged commit, one merged pull request whose merged commit has no recorded verdict, and one direct push to `main`, run the audit and confirm all three appear: the first with its recorded verdict, the second with a verdict reconstructed from records dated no later than the merge, and the third in the "without a pull request" list.

**Acceptance Scenarios**:

1. **Given** a pull request merged since the last audit, **When** the audit runs, **Then** it lists the pull request, its kind, the merged commit, the verdict at that commit as of the merge, the first unmet condition if any, and the account that merged it.
2. **Given** a pull request merged at a commit for which no verdict was recorded before the merge, **When** the audit runs, **Then** it computes the verdict for that commit from checks, statuses and records dated no later than the merge, and marks the entry as reconstructed.
3. **Given** a merged commit whose checks gained new runs after the merge (stages started by the merge), **When** the audit runs, **Then** those later runs are left out of the verdict as of the merge (FR-012).
4. **Given** a commit on `main` that no merged pull request produced, **When** the audit runs, **Then** it is listed under "reached main without a pull request" with its author and committer.
5. **Given** a merge whose pull request carries a session decision record (a comment starting `**Session decision (`) choosing to merge without the evidence, as on #1140, **When** the audit runs, **Then** the entry shows its unmet condition and links that decision record, reported and not counted (FR-015).
6. **Given** an audit that did not run for several days, **When** it next runs, **Then** it covers every merge since the last audit that did run, not only the last day.

---

### User Story 3 - Trust that the watcher can never block, merge, or be steered by the pull request it watches (Priority: P2)

The owner and every merge path keep working exactly as today. The workflow never merges, approves, labels, pushes or blocks, never puts its verdict among a head commit's checks or statuses, runs only from the default branch, uses no agent, and stops when its kill switch is set.

**Why this priority**: A watcher that can change what it watches is no longer only watching. Every existing "checks green" read counts what is on the commit: a failing verdict there would stop the board loop's merges and fail a session's own check; a passing one would make a commit with no other checks look green (Principle VIII).

**Independent Test**: Run the workflow over a pull request that fails every condition and confirm no check run, commit status, label, review, merge or push appeared anywhere; dispatch it on a non-default branch and confirm it refuses before reading anything; set its kill switch and confirm it exits without writing.

**Acceptance Scenarios**:

1. **Given** any pull request, verdict met or unmet, **When** the workflow runs, **Then** the head commit's set of check runs and commit statuses is unchanged, and the pull request's labels, reviews and merge state are unchanged.
2. **Given** a dispatch on a ref other than the default branch, **When** the workflow starts, **Then** it refuses and writes nothing.
3. **Given** the workflow's kill switch is set, **When** the workflow starts, **Then** it exits without computing or writing anything and says why in its run log.
4. **Given** the board loop's merge job or the lifecycle review gate's merge job deciding a merge, **When** it decides, **Then** it reads none of this feature's records.

---

### Edge Cases

- **A rebase or force-push replaces the head**: the verdict for the new head is computed afresh; records naming a replaced commit never count for the new one. The earlier verdict record stays, naming its own commit.
- **Records under the wrong author**: a record that looks like the App's but was posted by another account, or a bump verification naming a run that does not exist, counts as not met with the reason named.
- **Two "checks green" rules**: the board loop's rule counts every status on the commit; the lifecycle rule leaves the gate's own status out. Each kind is judged by the rule its own merge path uses today (FR-008), and the verdict says which rule it applied, so a final PR's failed `lifecycle-review-gate` status does not by itself make it "not green" here.
- **A merged pull request whose merged commit differs from its last head** (squash merge): the verdict is as of the pull request's last head before merge, and the squash commit on `main` is linked to it; the squash commit is not listed as "without a pull request".
- **A pull request merged into a branch other than `main`**: not watched (Assumptions).
- **A pull request opened from a fork**: watched read-only like any other; the workflow never checks out its head.
- **A merged pull request closed and reopened, or merged twice by revert-and-reapply**: each merge is its own audit entry.
- **Where the verdict is written**: never on a lifecycle issue in `stage:spec` or `stage:clarify`, on a final PR, or on the Spec Kit tracking issue, because a comment there starts a pipeline run (FR-018).
- **The 9th lifecycle condition (spec 119's hold label)**: checked by this verdict for final PRs even though the merge job does not yet check it at merge time; the verdict reports it as its own condition.

## Requirements *(mandatory)*

### Functional Requirements

**Scope and kinds**

- **FR-001**: The workflow MUST compute a verdict for every open pull request whose base is `main`, for its current head commit, at the times FR-016 names.
- **FR-002**: The workflow MUST assign each pull request exactly one kind from facts deterministic code reads, never from an agent: *Spec Kit bump PR* and *board loop fix PR* by the same authorship and branch-shape facts the board loop's merge code uses today; *final PR* by the finalize stage's head-branch convention (`spec/[<P>/]<NNN-slug>`); *spec PR* by the intake stage's head-branch convention (`spec-draft/[<P>/]<NNN-slug>`); every other pull request as *maintainer PR*. The verdict MUST state the facts that decided the kind.
- **FR-003**: The workflow MUST NOT try to tell an owner's pull request from a session's by account; both are *maintainer PR*. A session's fix PR is a maintainer PR whose evidence is read as FR-007 says.

**Snapshot**

- **FR-004**: Each verdict MUST be computed from a complete snapshot of the pull request and its head commit fetched fresh in that run — checks, statuses, reviews, comments, labels and the records FR-007 names — the way the board loop's merge decision already fetches one.
- **FR-005**: When any part of the snapshot cannot be read completely, the verdict MUST be marked incomplete, MUST name what was not read, and MUST NOT report as met any condition that depended on it.

**Conditions**

- **FR-006**: For every kind, the verdict MUST include the condition "checks green on the head commit, with the gate suite among them". A head with no checks is not green (Principle VIII): for a pull request of any kind with no checks on its head, this condition is unmet and "no checks on the head" is its first unmet condition. No kind is exempt; spec PRs, which have no checks today, therefore show as unmet until #1141 moves them off `main` or a check is added (clarified 2026-11-22, #1143).
- **FR-007**: The verdict MUST then include the kind's own evidence condition:
  - *Spec Kit bump PR*: its verification record, counted only when the Actions run it names is confirmed by the Actions API as the expected workflow, on that head, successful — as the bump's merge conditions confirm it today.
  - *Board loop fix PR*: the board loop's own review verdict for that head commit, posted by the pipeline's App, with zero open findings.
  - *Final PR*: the lifecycle review gate's round recorded at that head, clean, with zero open in-scope findings; plus no unresolved human changes-requested review and no hold label on the lifecycle issue (Principle X's nine conditions, reported as separate conditions).
  - *Maintainer PR* and *spec PR*: the reviewer's round record proposed by #1142, counted only when the Actions run that wrote it is confirmed by the Actions API. Until #1142 exists, this condition is unmet for every such pull request, and any session pass report on it is listed as reported, not counted.
- **FR-008**: The workflow MUST reuse the condition code that already exists — the board loop's merge conditions, its snapshot completeness check and its run-confirmation check, and the lifecycle merge preconditions — by calling it, and MUST NOT copy it. Where the two existing "checks green" rules differ, each kind MUST be judged by the rule its own merge path uses, and the verdict MUST name the rule applied. A gate MUST fail if a copy of either rule's logic appears in this feature's code (CLAUDE.md, "Shared logic has exactly one home").
- **FR-009**: A record MUST count only when code can confirm where it came from: posted by the pipeline's App, or written by an Actions run the Actions API confirms. A record posted under a maintainer's account — a pass report, a decision record, a free-prose verdict — MUST be listed in the verdict as reported and MUST NOT make any condition met.
- **FR-010**: A record naming a commit other than the head MUST NOT count for the head.

**Verdict record**

- **FR-011**: The workflow MUST write one verdict record per head commit per pull request: the pull request, the head commit, the kind and the facts that decided it, each condition and its result with a one-line reason when unmet, the first condition unmet, whether the snapshot was complete, and the time it was computed. A later run for the same head MUST replace that head's record, not add a second.

**Daily audit**

- **FR-012**: Once a day the workflow MUST list each pull request merged into `main` since the last completed audit: the pull request, its kind, the merged commit and its last head, the verdict at that head as of the merge time, the first unmet condition, and the account that merged it. "As of the merge" means checks, statuses and records dated no later than the merge; anything dated after it is left out.
- **FR-013**: When no verdict was recorded for a merged pull request's last head before it merged, the audit MUST reconstruct the verdict as FR-012 says and mark the entry as reconstructed.
- **FR-014**: The audit MUST list every commit that reached `main` since the last completed audit without being the merge or squash commit of a merged pull request, with its author and committer.
- **FR-015**: When a merged pull request carries a session decision record (a comment starting `**Session decision (`), the audit entry MUST link it, as reported and not counted; the entry's verdict is unchanged by it.
- **FR-016**: The workflow MUST compute verdicts for every open pull request into `main` on an hourly schedule and on manual dispatch; it MUST NOT be chained to the CI workflow finishing. A pull request merged between two runs gets only a reconstructed verdict in the audit (FR-013). Hourly, not every 30 minutes, because every job counts as at least one Actions minute and a 30-minute schedule would use about 1,440 minutes a month (clarified 2026-11-22, #1143). The workflow MUST run the daily audit on a daily schedule and on manual dispatch.

**Only watching**

- **FR-017**: The workflow MUST NOT merge, approve, request changes, label, push, comment on a commit, create or update a check run or commit status, or edit any pull request. Its verdict MUST NOT appear among any commit's checks or statuses.
- **FR-018**: The verdict records and the audit MUST be written to a single place that starts no pipeline run: a collapsed section of the "Board status" issue, written by that issue's one writer (`board-status.yml`), as the proof list of spec 124 already reports there. Nothing is written to a lifecycle issue, a final PR or the Spec Kit tracking issue.
- **FR-019**: No existing merge job or merge rule MUST read this feature's records; the two merge jobs keep their own decisions.
- **FR-020**: Every step MUST be deterministic code; the workflow MUST invoke no agent.
- **FR-021**: The workflow MUST refuse to run, before reading anything, when its ref is not the default branch.
- **FR-022**: The workflow MUST carry a repository-level kill switch in the `WING_COMMANDER_*_PAUSED` family; while it is set, the workflow writes nothing.
- **FR-023**: The workflow MUST run in this repository only, like the board loop and the review gates, and MUST NOT add to the published contract.

**Watching period**

- **FR-024**: The watching period MUST be a fixed 30 days from the day the feature ships. When it ends, the owner reviews the audit and decides the next step, including whether the merge jobs read the verdict (clarified 2026-11-22, #1143).

**Documentation**

- **FR-025**: `docs/reference.md` MUST describe the workflow, its kill switch and its schedule, and its "Merge classes" and "Known limits" sections MUST be updated to say what the audit now records and what it still does not.

### Key Entities

- **Pull request kind**: one of *Spec Kit bump PR*, *board loop fix PR*, *final PR*, *spec PR*, *maintainer PR*, with the facts that decided it.
- **Condition**: a named check of the snapshot with a result (met, unmet, not read) and a one-line reason when not met.
- **Verdict record**: one per pull request head commit; the kind, every condition, the first unmet, snapshot completeness, computed-at time.
- **Counted record**: evidence whose origin code can confirm — posted by the App, or written by an Actions run the Actions API confirms.
- **Reported record**: evidence under a maintainer's account, listed for the reader and never counted.
- **Audit entry**: one per merge into `main` since the last audit — the pull request, merged commit, last head, verdict as of the merge (recorded or reconstructed), first unmet condition, merging account, and any linked session decision record.
- **Unpaired commit**: a commit that reached `main` without a merged pull request.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For every pull request merged into `main` after the feature ships, the audit has an entry within one day of the merge: 100% of merges, none missing.
- **SC-002**: Every commit that reaches `main` without a pull request appears in the audit within one day.
- **SC-003**: Replayed over the 48 merges of 2026-10-15 to 2026-11-16, the audit's verdicts agree with the lookup's hand count: complete for the 6 with a pipeline-written record at the merged commit, and incomplete for the rest with the right first unmet condition — the 14 session-written clean records listed as reported, not counted.
- **SC-004**: Across the watching period, no check run, commit status, label, review, merge or push is ever attributable to the workflow — zero.
- **SC-005**: Across the watching period, no merge by the board loop or the lifecycle review gate is delayed or changed by the workflow — zero.
- **SC-006**: The workflow adds zero agent turns to the shared usage window.
- **SC-007**: A reader can answer "what was the evidence when this commit reached `main`?" for any merge since the feature shipped from the audit alone, in under a minute.

## Assumptions

- **Only `main`**: merges into a feature's own branch are not watched in this feature; #1141 would move spec PR approval there, and watching that is a follow-up.
- **Kinds by existing facts**: a board loop fix PR and a bump are identified exactly as the board loop's merge code identifies them today; the owner's and a session's pull requests are one kind, because GitHub records the same account for both.
- **Session pass reports before #1142**: shown as reported, never counted (FR-009). The verdict is therefore unmet for every maintainer PR until #1142's round record exists; that is the expected reading during watching, not a defect.
- **Where it reports**: the Board status issue's collapsed section, as #1144 / spec 124 chose for its own report (FR-018). The run summary is not used, because `gh` cannot read it.
- **Audit window**: "since the last completed audit", with the first audit covering the 30 days before it ran.
- **Name**: "the merge evidence audit" — "gate" already names the `verify-*` checks, the gate suite and the lifecycle review gate.
- **Out of scope, each the owner's call later**: the merge jobs and the session fix-PR rule reading this verdict in place of their own conditions; requiring the verdict before any merge.
- **Trigger limits accepted as given** (GitHub docs read 2026-11-16): an event caused by the Actions token starts no workflow run, dispatches excepted; `check_run` and `check_suite` do not fire for suites GitHub Actions created; `workflow_run` runs the default branch's workflow file and chains at most three levels.
