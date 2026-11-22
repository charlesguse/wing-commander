# Feature Specification: One Reviewer for Every Kind of Pull Request

**Feature Branch**: `127-shared-pr-reviewer`

**Created**: 2026-11-22

**Status**: Draft

**Input**: User description: "One reviewer workflow for every kind of pull request: it reviews and records, and never fixes" (issue #1142), with issue #1110 ("Lifecycle review gate converges: findings keep their identity when reworded, refutations are recorded, unfinished PRs aren't reviewed") folded in by owner decision of 2026-11-22.

## Context

Owner direction (2026-11-15): keep the existing review workflows and add one new workflow that covers reviewing as a whole. Owner decision (2026-11-22): fold #1110 into this feature; #1110 is closed as folded.

Today four reviewers exist, each built for one kind of pull request: the spec PR review (paused since it shipped), the lifecycle review gate (final PRs; five stopped `not-converging` as counted on 2026-11-10), the board loop's review job (its fix PRs), and the session review procedure (`review-until-clean`, a hand-driven loop of fresh sessions). Each Actions reviewer is one agent making one unchecked pass. Since spec 116 the three Actions reviewers share a hidden round record (round, commit, finding count, fingerprints), but it carries no verdict and no run id, and each reviewer reports its verdict its own way, so nothing can answer "was this commit reviewed, by what, with what verdict" in one form for every kind of pull request. A session's fix PR has no Actions reviewer at all.

From #1110, two of its three parts belong to this feature's memory: a finding's identity must survive rewording (on #1087 five defects each came back under new titles in later rounds; on #1102 the gate's 29 findings were 19 distinct defects, three of them raised in all three rounds under different titles), and a dismissal must be recorded so the next round cannot raise it again without showing it was wrong. #1110's third part (no review of an unfinished PR) is already on `main`.

Two read-only trials on 2026-11-15 (a finding agent and a checking agent each) showed the shape can say something the gate did not (#1102: "the feature is mostly not built") and can agree with a thorough hand review (#1139). They did not show that a review ends, that it finds a real defect in a fix PR, that the checking step ever overturns anything, or that an Actions job behaves as the session's agents did. That is why the first use is report-only.

**Layer**: This specification describes a new reviewer for this repository (the consuming instrument), built as a callable workflow plus a thin wrapper so that later publication is a decision, not a rewrite. It does not add to or change the published contract in this feature.

## Scope

In scope: the shared reviewer (callable workflow and thin wrapper), its round record and memory, its run confirmation, and **one line added to CLAUDE.md's fix-PR section**:

> A session dispatches the shared reviewer on each of its fix PRs, on the head its hand review covers, during report-only use.

That line changes the rules agents run under, so it is approved with this spec; it is written by the implement stage, not in the spec PR (FR-004). Out of scope: any change to the existing reviewers (FR-005) and any round for a pull request that is not a fix PR (FR-001). *(Spec review round 1, owner decision 2026-11-22.)*

## Clarifications

### Session 2026-11-22

Owner's choices, made in chat on 2026-11-22 and posted on #1142; no precedent settled any of them.

- Q: What starts the reviewer on a session's fix PR? → A: (a) The session dispatches it explicitly, on the same head its hand review covers. A forgotten dispatch leaves a gap in the comparison; that is accepted, and automatic starts are a later decision (FR-004).
- Q: May the checking job run code? → A: (b) Only the change's own named check and the gate suite, in an isolated job with no write credential; no other code. Isolation and credential stripping must be proven in this feature (FR-012, SC-008).
- Q: How is a new finding matched to an earlier one? → A: (a) plus a location-overlap flag. Identity carries over only when the finding job cites an earlier id that deterministic code verifies exists; deterministic code also flags "possible repeat of <id>" on location overlap but never merges identities on location alone; the flag is in the record and given to the next round (FR-016).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Review a session's fix PR, report-only (Priority: P1)

A session opens a fix PR for a defect recorded before the change (an issue, a Maintenance backlog line, or a failing run). The shared reviewer is started for that pull request. It first asks about the purpose: is the problem real, does the change fix it, and does the change carry a check that fails without the fix? Then it asks whether the change breaks anything, each claim with a concrete failing case. A second, separate checking job tests every answer and candidate finding against the code; only what it upholds counts. The reviewer posts one round record on the pull request and nothing else. The hand review the `review-until-clean` skill already requires proceeds unchanged beside it, and the reviewer's verdict authorizes nothing.

**Why this priority**: It is the whole first use the owner's direction asks for, and the only way to compare the shared reviewer with the hand review on real pull requests before anything depends on it.

**Independent Test**: Start the reviewer on a session fix PR whose originating issue is known; confirm one round record appears on the PR naming the reviewed commit, the verdict, the round number, each finding with its status, the reviewer's own commit and the writing run, and that no push, label, merge, approval or fix was made by it.

**Acceptance Scenarios**:

1. **Given** a session fix PR that cites its originating issue, **When** the reviewer is started for it from the default branch, **Then** the finding job is given the originating issue's text as the statement of purpose, and the PR description only as the author's claim to be checked.
2. **Given** a fix PR that fixes a real problem and carries a check that fails without the fix, and no other defect, **When** a round runs, **Then** the record's verdict is clean, with the three purpose answers recorded as upheld.
3. **Given** a fix PR whose added check would pass without the fix, **When** a round runs, **Then** the record carries an upheld finding saying so, and the verdict is not clean.
4. **Given** the finding job proposes a breakage claim with no concrete failing case, or one the checking job cannot reproduce from the code, **When** the checking job evaluates it, **Then** it is recorded as dismissed, with its reason, and does not affect the verdict. *(Spec review round 1, owner decision 2026-11-22.)*
5. **Given** any round on any pull request, **When** it finishes, **Then** the pull request's branch, labels, merge state, review approval state and linked issue are unchanged by the reviewer, apart from the one posted record.

---

### User Story 2 - A later round remembers earlier rounds (Priority: P1)

When the same pull request is reviewed again (after a fix, or a re-dispatch), the new round is given every earlier finding on that pull request with its identity and status, open or dismissed, and each dismissal's reason. A finding that repeats an earlier one and cites its id, however it is reworded or re-anchored, keeps the earlier finding's identity rather than being counted as new. An uncited finding whose location overlaps an earlier one is flagged as a possible repeat but keeps its own identity. A dismissed finding is reopened only when the round shows why the dismissal was wrong, and the checking job upholds that showing.

**Why this priority**: This is the part of #1110 the owner folded in. Without it, rounds do not converge: reworded repeats count as new findings and refuted findings come back.

**Independent Test**: Run round 1 on a pull request and dismiss one finding with a reason; run round 2 with the finding job prompted (or seeded) to raise the same defect under a different title and file, citing the earlier id; confirm round 2's record shows the earlier finding's identity with its dismissed status and no new finding for it. Seed a second repeat that overlaps the earlier finding's location without citing it; confirm it gets a new identity carrying a "possible repeat of <id>" flag.

**Acceptance Scenarios**:

1. **Given** round N recorded a finding F as open, **When** round N+1 raises the same defect under a different title and cites F's id, **Then** round N+1's record lists it under F's identity, not under a new one.
2. **Given** F was dismissed with a reason, **When** round N+1 re-raises it citing F's id without showing the dismissal was wrong, **Then** F stays dismissed and does not count toward the verdict.
3. **Given** F was dismissed, **When** round N+1 shows (and the checking job upholds) that the dismissal was wrong, **Then** F is recorded reopened under its original identity, with the reason.
4. **Given** round N+1 raises a defect that cites no earlier id, **When** it is upheld, **Then** it gets a new identity.
5. **Given** a round record exists on the pull request that was not written by a confirmed run of this reviewer, **When** a later round assembles the earlier findings, **Then** that record is ignored.
6. **Given** round N+1 raises an uncited finding whose file and line range overlap an earlier finding F's, **When** the record is written, **Then** the new finding has its own new identity and carries a "possible repeat of F" flag, F's identity and status are unchanged, and the flag is given to the next round.
7. **Given** round N+1 cites an id that no earlier confirmed finding on the pull request has, **When** identities are assigned, **Then** the citation is ignored and the finding gets a new identity.
8. **Given** an open finding F, **When** anyone, the requester included, posts a comment on the pull request shaped like a dismissal of F and a later round assembles the earlier findings, **Then** the open set is unchanged: F is still open and is re-checked in that round (FR-010, FR-018). *(Spec review round 2, owner decision 2026-11-22.)*

---

### User Story 3 - One readable record per round, counted only when confirmed (Priority: P2)

Any later consumer (a session, a future proposal that moves an existing reviewer onto this one, or the owner) can read, for a given commit, whether it was reviewed by this reviewer, in which round, with what verdict and which findings, in one form for every kind of pull request. A record counts only when the Actions run it names is read back and confirmed as this reviewer's own run, from the default branch, for the commit the record names, in the same way `verification_run_confirms` in `board_merge.py` confirms a Spec Kit bump's verification record.

**Why this priority**: The single record is what makes the later moves (each existing reviewer onto this one) a replacement of one job rather than a rewrite of every consumer, but nothing consumes it to authorize anything in this feature.

**Independent Test**: Post a well-formed record by hand naming a run that is not this reviewer's run (or is from a non-default branch, or for another commit); confirm the reader reports it as unconfirmed and counts it for nothing, while a genuine record is reported confirmed.

**Acceptance Scenarios**:

1. **Given** a record naming a run of this reviewer's workflow, on the default branch, that reviewed the commit the record names and finished, **When** it is read back, **Then** it is confirmed.
2. **Given** a record naming a run of another workflow, a run on another branch, a run for another commit, a run that cannot be fetched, or no run, **When** it is read back, **Then** it is unconfirmed and counts for nothing.
3. **Given** several confirmed records on one pull request, **When** they are read, **Then** the latest round for a given commit is identifiable without parsing prose.
4. **Given** a final PR with lifecycle review gate rounds, and a shared-reviewer round record on it carrying the shared reviewer's reviewer field, **When** the lifecycle review gate reads its convergence history (`read_round_records`), **Then** the shared-reviewer record is not counted and the gate's convergence count is the same as without it. *(Spec review round 1, owner decision 2026-11-22.)*
5. **Given** a dispatch naming a pull request that is not a fix PR (a spec, plan or final PR), **When** the run starts, **Then** it refuses before any agent runs, writes no round record, and says in the run's summary that only the fix round is defined in this feature (FR-001). *(Spec review round 1, owner decision 2026-11-22.)*

---

### User Story 4 - The reviewer cannot be brought by the pull request it reviews (Priority: P2)

The reviewer runs only from the default branch. A dispatch that targets any other ref is refused before any agent runs, and the refusal is visible. The pull request's own files never supply the reviewer's prompts, tool lists or record format.

**Why this priority**: A dispatch can target any branch; without this, a pull request could ship a reviewer that approves itself, and every record would mean nothing.

**Independent Test**: Dispatch the reviewer on a non-default ref; confirm it ends without an agent run, without a record, and with a stated refusal.

**Acceptance Scenarios**:

1. **Given** a dispatch on a non-default ref, **When** the run starts, **Then** it refuses before any agent step and writes no record.
2. **Given** a pull request that modifies the reviewer's own workflow, prompts or scripts, **When** it is reviewed, **Then** the round uses the default branch's copies, not the pull request's.
3. **Given** a pull request whose named check or gate-suite code tries to read a model credential or App token, or to overwrite the checking job's results, **When** that code runs in the code-run job (FR-012), **Then** no secret is reachable to it, and the checking job's recorded results change only through the exit codes and output staged to it as data. *(Spec review round 1, owner decision 2026-11-22.)*

---

### User Story 5 - A bounded, legible stop (Priority: P3)

Re-dispatching the reviewer on one pull request cannot run without limit. When the per-pull-request round budget is spent, the reviewer writes a final hand-off record instead of a round, saying the budget is spent, what is still open (the open set after the last confirmed round, as that round's record lists it), and that the pull request is left to whatever asked for the review.

**Why this priority**: Each round is two agent runs in a usage window shared with the pipeline and the owner's sessions.

**Independent Test**: Dispatch rounds on one pull request until the budget is spent; confirm the next dispatch runs no agent and writes the hand-off record.

**Acceptance Scenarios**:

1. **Given** a pull request whose confirmed rounds equal the budget, **When** the reviewer is started for it again, **Then** no agent runs and a hand-off record lists the open findings, as FR-015 defines them and the last confirmed round record lists them (FR-019), and carries no verdict (FR-025). *(Spec review round 1, owner decision 2026-11-22.)* *(Spec review round 2, owner decision 2026-11-22.)*

---

### Edge Cases

- **No pre-existing statement of purpose**: the fix PR cites no issue, backlog line or run. The round runs the breakage questions only, records the purpose answers as "no source of purpose", and the verdict is `undetermined` unless a blocking finding makes it `findings` (FR-014). *(Spec review round 1, owner decision 2026-11-22.)*
- **Purpose source is a failing run**: the run's step results and error messages are staged for the finding job, since the diff alone does not show what failed.
- **The cited purpose source changed after the pull request opened** (edited issue, edited backlog line): the reviewer uses the text as it stood when the pull request was opened where that is recoverable, and says in the record which version it used.
- **A new commit is pushed while a round runs**: the record names the commit actually reviewed; it never claims the new head.
- **The checking job fails, times out or returns malformed output**: the round's verdict is "incomplete", no finding counts as upheld, and the record says why. An incomplete round still uses one unit of the budget.
- **The finding job returns nothing**: the checking job still evaluates the three purpose answers; an empty finding list is not by itself a clean verdict.
- **Rate limit or usage-window exhaustion mid-round**: same as a failed checking job; incomplete, stated.
- **The change's named check or the gate suite exits non-zero**: that exit code is a staged result for the checking job, never a job failure; a check that fails on purpose on the unfixed tree (FR-008(c)) is the expected answer, not a reason for `incomplete` (FR-012, FR-014). *(Spec review round 2, owner decision 2026-11-22.)*
- **Code-run results are missing**: when the code-run job could not stage its results at all (for example a timeout, a runner error, or output that cannot be staged), each purpose answer that depends on them is not determinable, and the verdict follows FR-014's order: `findings` when a blocking finding gives it, else `incomplete`. When only some results are missing, the answers that depend on them are not determinable and `undetermined` applies unless a blocking finding gives `findings`. *(Spec review round 2, owner decision 2026-11-22.)*
- **Pull request code hangs or crashes the code-run job**: this cannot turn a `findings` round into `incomplete`; a blocking finding still yields `findings` (FR-014). *(Spec review round 2, owner decision 2026-11-22.)*
- **Pull request closed or merged before the round posts**: the record is still posted (it is evidence for the report-only comparison), marked with the state the pull request was in.
- **Two dispatches for the same pull request at once**: they serialize per pull request; the second sees the first's record as an earlier round.
- **The reviewer is refused or stopped** (non-default ref, a pull request that is not a fix PR, or the kill switch): no agent runs, no round record is written, and the refusal or stop is stated in the run's summary only; `refused` is never a round verdict (FR-014, FR-022, FR-026). *(Spec review round 1, owner decision 2026-11-22.)*
- **A forged record or dismissal in a human or bot comment**: unconfirmed, ignored for memory and for counting, whoever posted it (Story 3). A dismissal counts only when a confirmed run's record carries it (FR-018); a dismissal-shaped comment from anyone, the requester included, is ignored. *(Spec review round 2, owner decision 2026-11-22.)*
- **A finding cites only a merged spec's spec.md, plan.md, tasks.md or research.md**: it is not a defect under this repository's rules, and is recorded as dismissed with that reason; contracts under `specs/*/contracts/` remain reviewable like code.

## Requirements *(mandatory)*

### Functional Requirements

**Scope and invocation**

- **FR-001**: The repository MUST gain one new reviewer, given a pull request number. Its request and record formats MUST accept and record every kind of pull request (session fix PR, board loop fix PR, spec PR, plan PR, final PR). In this feature only the fix round is defined: a request for any other kind MUST be refused visibly, before any agent runs and with no round record (FR-022). Each later proposal defines its own kind's purpose questions. In this feature the reviewer is put to use only on session fix PRs. *(Spec review round 1, owner decision 2026-11-22.)*
- **FR-002**: The reviewer MUST be built as a callable workflow with a thin wrapper that owns its trigger(s) and repository-specific inputs, so publishing it later changes no behaviour. It is not added to the published contract in this feature.
- **FR-003**: The reviewer MUST be startable by a manual dispatch naming a pull request number, and by another workflow calling it with one.
- **FR-004**: On a session's fix PR, the reviewer MUST be started by the session dispatching it explicitly, on the same head commit its hand review covers, so the FR-029 comparison gets exact same-commit pairs at the least spend. It MUST NOT start automatically on pull requests a session opens. A forgotten dispatch leaves that pull request out of the comparison; this gap is accepted, and moving to automatic starts is left to a later decision. The duty lives in one line this feature adds to CLAUDE.md's fix-PR section (see Scope): "A session dispatches the shared reviewer on each of its fix PRs, on the head its hand review covers, during report-only use." That line changes the rules agents run under and is approved with this spec; the implement stage writes it. *(Spec review round 1, owner decision 2026-11-22.)*
- **FR-005**: The existing review workflows (spec PR review, lifecycle review gate, board loop review job) and the `review-until-clean` procedure MUST be unchanged by this feature. Moving each onto the shared reviewer is a later proposal each.

**Purpose first**

- **FR-006**: Each round MUST be given a statement of what the change is for from a source that predates the change: for a fix, the originating issue, the Maintenance backlog line, or the failing run. The pull request's description MUST be presented as the author's claim, to be checked, never as the statement of purpose.
- **FR-007**: When the purpose source is a failing run, the round MUST be given that run's step results and error messages, not only the diff, commits and pull request text.
- **FR-008**: For a fix, each round MUST answer, in this order: (a) is the problem real, (b) does the change fix it, (c) does the change carry a check that fails without the fix, answered from the code-run job's staged results, where the check's non-zero exit without the fix is a result and never a job failure (FR-012); and then (d) does the change break anything. Every breakage claim MUST carry a concrete failing case (inputs or state, and the wrong result). *(Spec review round 2, owner decision 2026-11-22.)*
- **FR-009**: The equivalent purpose question for a feature (which requirements the change does not meet) is reserved for the later proposal for final PRs; this feature MUST leave the record format able to carry it without a format change.

**Two jobs per round**

- **FR-010**: A round MUST consist of two separate agent jobs (plus FR-012's code-run job, which runs no agent): a finding job that produces the purpose answers and candidate findings, and a checking job that shares no conversational context with it and evaluates each answer, each candidate and every finding open at the start of the round (FR-015) against the code and against the pull request's earlier confirmed rounds. For each finding open at the start of the round, the checking job MUST either confirm it still upheld or mark it resolved; output that leaves one unevaluated is malformed (FR-014's `incomplete`). When that re-check depends on code-run results that are missing (FR-012), the checking job MUST instead record the finding as "not re-checked: code-run results missing"; the finding keeps its status and stays open, and that output is not malformed. *(Spec review round 1, owner decision 2026-11-22.)* *(Spec review round 2, owner decision 2026-11-22.)* *(Spec review round 3, owner decision 2026-11-22.)*
- **FR-011**: Only answers and findings the checking job upholds MUST count toward the verdict. Each candidate the checking job does not uphold MUST still be recorded, as dismissed, with its reason (FR-015). *(Spec review round 1, owner decision 2026-11-22.)*
- **FR-012**: A round MAY run exactly two kinds of the pull request's code: the change's own named check (the check FR-008(c) asks about) and the repository's gate suite. It MUST run no other code. That code MUST run in its own code-run job, separate from both agent jobs, that holds no secret of any kind: no model credential and no App token. The code-run job's exit codes and output MUST be staged to the checking job as data, and nothing else the code-run job writes may reach the checking job or its recorded results. The named check's and the gate suite's exit codes, zero or not, are staged results, never a job failure. A code-run outcome makes the round `incomplete` only when the code-run job could not stage its results at all (for example a timeout, a runner error, or output that cannot be staged), and then only under FR-014's order. The isolation and the absence of every secret MUST be proven as part of this feature (SC-008). *(Spec review round 1, owner decision 2026-11-22.)* *(Spec review round 2, owner decision 2026-11-22.)*
- **FR-013**: Whether an upheld finding is blocking MUST be decided by deterministic rules applied to fields the checking job reports, not by the agent's own label. A finding is blocking when it is upheld, it is in the pull request's scope, and its failing case is reachable in this repository's configuration as checked; otherwise it is recorded as non-blocking with the rule that made it so.
- **FR-014**: A round record's verdict MUST be one of a fixed set, taken in this order: `incomplete` (an agent job failed or its output could not be read); else `findings` (at least one blocking finding in the open set after the round, or a purpose answer upheld negatively); else `incomplete` (the code-run job could not stage its results at all, FR-012); else `undetermined` (a purpose answer is not determinable, or there is no source of purpose); else `clean` (all purpose answers upheld positively and no blocking finding in the open set after the round). The verdict MUST be computed by deterministic code from the checked results, over the open set after the round (FR-015), not over this round's candidates only: a finding upheld in an earlier round and still open counts as much as a new one. The named check's and the gate suite's exit codes are staged results, never a job failure (FR-012). When code-run results are missing, each purpose answer that depends on them is not determinable, so pull request code that hangs or crashes the code-run job never turns a `findings` round into `incomplete`. `refused` (the run was not permitted, FR-001, FR-022) and the kill-switch stop (FR-026) are recorded in the run's summary only, never in a round record; the hand-off record (FR-025) carries no verdict. *(Spec review round 1, owner decision 2026-11-22.)* *(Spec review round 2, owner decision 2026-11-22.)*

**Memory (folded from #1110)**

- **FR-015**: Each round MUST be given every finding from the pull request's earlier confirmed round records (which carry every dismissal that counts, FR-018), with its identity, its status and, for a dismissal or reopening, its reason. A finding's status is one of `upheld`, `dismissed`, `reopened` or `resolved`, and changes only as this table allows:

  | Actor | Sets | From | When |
  |---|---|---|---|
  | Finding job | nothing | — | It proposes candidates and may cite an earlier id (FR-016); it sets no status. |
  | Checking job | `upheld` | new candidate | It upholds the candidate. |
  | Checking job | `dismissed`, with reason | new candidate | It does not uphold the candidate (FR-011). |
  | Checking job | `reopened`, with reason | `dismissed` or `resolved` | It upholds a cited repeat's showing that the dismissal was wrong (FR-017), or that a resolved defect is back. |
  | Checking job | unchanged (`upheld` or `reopened`) | `upheld` or `reopened` | It re-checks a finding open at the start of the round (FR-010) and its failing case still reproduces. |
  | Checking job | `resolved` | `upheld` or `reopened` | It re-checks a finding open at the start of the round (FR-010) and its failing case no longer reproduces. |
  | Checking job | unchanged (`upheld` or `reopened`), recorded as "not re-checked: code-run results missing" | `upheld` or `reopened` | Its re-check of a finding open at the start of the round (FR-010) depends on code-run results that are missing. The finding stays open; a finding is never marked `resolved` without the evidence its re-check needs. *(Spec review round 3, owner decision 2026-11-22.)* |
  | Requester, through a confirmed run | `dismissed`, with reason | `upheld` or `reopened` | It passes the dismissal as an input to the next dispatch, and that run writes it into its own round record (FR-018); it counts only once that record is confirmed (FR-021). |

  Any other change, and a cited repeat that shows nothing new, leaves the status as it was. A finding is **resolved** only by the checking job's row above; not being raised again does not resolve it. A finding is **open** when its latest status, taken from the confirmed round records in round order, is `upheld` or `reopened`; a requester dismissal is ordered by the round of the run that carries it, and applies from the start of that round. Deterministic code MUST compute the open set this way, for the next round's memory, for each round's verdict (FR-014) and record (FR-019), and for the hand-off record (FR-025). *(Spec review round 1, owner decision 2026-11-22.)* *(Spec review round 2, owner decision 2026-11-22.)*
- **FR-016**: A finding that repeats an earlier one MUST keep the earlier finding's identity even when its title, wording or anchor differs. A finding keeps an earlier finding's identity only when the finding job cites that earlier id and deterministic code verifies that the cited id exists among the pull request's earlier confirmed findings; a citation of an id that does not exist is ignored and the finding gets a new identity. In addition, deterministic code MUST record a "possible repeat of <id>" flag on a new finding whenever its file and line range overlap an earlier finding's; the flag is visible in the record and given to the next round, but identities MUST NEVER be merged on location alone. The identity written into the record MUST be assigned by deterministic code. (Rationale: an uncited repeat shows as a visible overcount, which is preferred to the risk of merging a new real defect into a dismissed finding, which would hide it under FR-017.)
- **FR-017**: A dismissed finding MUST NOT count toward the verdict, and MUST be reopened only when the round shows why the dismissal was wrong and the checking job upholds that showing. The reopening MUST keep the original identity and record the reason.
- **FR-018**: A dismissal MUST be recordable by the checking job (a candidate it does not uphold is dismissed with its reason) and by whatever asked for the review, under FR-015's table. A requester dismissal counts only when a confirmed run carries it: it is passed as an input to the next dispatch (FR-003), written into that run's round record, and counts only once that record is confirmed (FR-021); round order alone orders it. A dismissal-shaped comment on the pull request, from anyone, the requester included, MUST be ignored. This feature MUST NOT require any existing reviewer to write dismissals. *(Spec review round 1, owner decision 2026-11-22.)* *(Spec review round 2, owner decision 2026-11-22.)*

**The record**

- **FR-019**: Each round MUST write exactly one record on the pull request, containing: the commit reviewed, the verdict, the round number, the full open set after the round (FR-015) and every other finding the round evaluated or dismissed, each with its identity and status, any requester dismissal the run carries (FR-018), the purpose answers, the reviewer's own commit (the default-branch commit the reviewer ran from), and the id of the Actions run that wrote it. *(Spec review round 2, owner decision 2026-11-22.)*
- **FR-020**: The record MUST be machine-readable in one form for every kind of pull request, so "was this commit reviewed, by this reviewer, with what verdict" is answerable without parsing prose. The record SHOULD extend, not fork, the round record the existing Actions reviewers share (spec 116). The record MUST carry a reviewer field naming this reviewer, and existing readers of spec 116's round record (`read_round_records` in `wc_convergence.py`, including the lifecycle review gate's convergence history) MUST never count a shared-reviewer record in this feature. FR-005 still holds: those readers' behaviour on their own records is unchanged. *(Spec review round 1, owner decision 2026-11-22.)*
- **FR-021**: A record MUST count only after its named run is read back and confirmed as a run of this reviewer's workflow, on the default branch, for the commit the record names, in the manner of `verification_run_confirms` in `board_merge.py`. An unconfirmed record MUST count for nothing, for memory (FR-015) and for any reader.

**Trust and limits**

- **FR-022**: The reviewer MUST refuse, before any agent runs, a run that is not on the default branch, and MUST write no round record for it; the refusal MUST be visible in the run's summary, and `refused` is never written into a round record (FR-014). *(Spec review round 1, owner decision 2026-11-22.)*
- **FR-023**: The reviewer MUST only report. It MUST NOT push, fix, merge, approve, request changes in a way that blocks a merge, label, close or retitle anything. What happens to its findings stays with whatever asked for the review.
- **FR-024**: Each agent job MUST declare an explicit model and a bounded turn budget, per the constitution's Principle II. The models default to `claude-sonnet-5-5` for both jobs and are overridable by repository variable. No effort level is set: neither job passes an effort override unless a repository variable sets one. *(Spec review round 1, owner decision 2026-11-22.)*
- **FR-025**: Rounds on one pull request MUST be bounded by a per-pull-request budget, defaulting to 5 confirmed rounds; when it is spent, a further start MUST run no agent and write a hand-off record listing the open findings (FR-015) (Story 5). The hand-off record carries no verdict. *(Spec review round 1, owner decision 2026-11-22.)*
- **FR-026**: Rounds on one pull request MUST serialize, and the reviewer MUST carry a repository-level kill switch in the `WING_COMMANDER_*_PAUSED` family that stops it before any agent runs. A kill-switch stop writes no round record and no verdict; it is stated in the run's summary only (FR-014). *(Spec review round 1, owner decision 2026-11-22.)*
- **FR-027**: Issue, pull request and comment text, and the code-run job's staged output, given to either agent job MUST be framed as untrusted data, and neither agent job may have web tools or any write credential. The code-run job holds no secret of any kind (FR-012). *(Spec review round 1, owner decision 2026-11-22.)*

**Report-only period**

- **FR-028**: During this feature, the reviewer's verdict MUST authorize nothing: no merge rule, gate or skill reads it as a condition. The hand review `review-until-clean` requires is unchanged, and does not count this reviewer as the "separate session" CLAUDE.md's fix-PR merge rule names.
- **FR-029**: For each session fix PR that gets both a shared-reviewer round and a hand review, it MUST be possible to compare the two on the same commit: the shared reviewer's record and the hand review's report are both findable from the pull request.

### Key Entities

- **Review request**: a pull request number, the kind of pull request, the purpose source (issue, backlog line or run), who asked for the review, and any requester dismissals it passes (FR-018).
- **Round**: one finding job, one checking job and, when the change's check or the gate suite is run, one code-run job (FR-012), against one commit of one pull request; has a number within that pull request.
- **Code-run results**: the exit codes and output of the code-run job, staged to the checking job as data (FR-012).
- **Candidate finding**: what the finding job proposes: a claim, an anchor, a failing case and, when it repeats one, the earlier identity it cites.
- **Checked finding**: a candidate after the checking job: a status from FR-015's table, with a reason, a blocking/non-blocking result from the deterministic rule, a stable identity and, when its location overlaps an earlier finding's without citing it, a "possible repeat of <id>" flag.
- **Purpose answers**: the three fix questions (problem real, change fixes it, check fails without the fix), each upheld positively, negatively or not determinable; a not-determinable answer, or no source of purpose, makes the verdict `undetermined` unless a higher verdict applies (FR-014).
- **Round record**: the one machine-readable record a round posts (FR-019), with the run id that makes it confirmable and the reviewer field that keeps spec 116's existing readers from counting it (FR-020).
- **Dismissal**: a finding's `dismissed` status with its reason, set by the checking job, or by the requester as a dispatch input that a confirmed run's round record carries (FR-015, FR-018), carried forward to later rounds. A dismissal-shaped comment is never one.
- **Hand-off record**: what the reviewer posts instead of a round when the budget is spent: the open findings (FR-015), and no verdict.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On at least 5 session fix PRs reviewed during the report-only period, every round posts exactly one confirmed record and makes no other change to the pull request (zero pushes, labels, merges or approvals by the reviewer).
- **SC-002**: A record whose named run is not a default-branch run of this reviewer for the named commit is reported unconfirmed in 100% of checked-in test cases (wrong workflow, wrong branch, wrong commit, missing run, unfetchable run).
- **SC-003**: A dispatch on a non-default ref ends with zero agent runs and zero records in 100% of attempts.
- **SC-004**: In a seeded test where round 2 re-raises a round-1 finding under a different title and anchor and cites its id, the round-2 record carries the round-1 identity and adds no new finding for it; a dismissed finding re-raised with a citation but without a showing stays dismissed; an uncited round-2 finding overlapping a round-1 finding's location gets a new identity with a "possible repeat of <id>" flag and never the round-1 identity; a citation of a non-existent id yields a new identity; and the open set computed from the records follows FR-015's table (an upheld finding not raised again stays open; one the checking job marks resolved does not); a round 2 on a commit that fixes a round-1 upheld finding marks it resolved, and a round 2 where its failing case still reproduces keeps it open and, if it is blocking, makes the round-2 verdict `findings` even when round 2 raises nothing new; and an open blocking finding whose re-check needs code-run results, in a round where pull request code crashes the code-run job, stays open and blocking, and that round's verdict is `findings`. *(Spec review round 1, owner decision 2026-11-22.)* *(Spec review round 2, owner decision 2026-11-22.)* *(Spec review round 3, owner decision 2026-11-22.)*
- **SC-005**: On a fix PR seeded with a known defect (for example, an added check that passes without the fix), the round's verdict is not clean, and the defect is recorded as an upheld finding.
- **SC-006**: In a seeded test, the checking job dismisses at least one candidate (for example, a breakage claim with no reproducible failing case), so a round where the checking job upholds everything is not the only observed outcome. *(Spec review round 1, owner decision 2026-11-22.)*
- **SC-007**: Shared-reviewer and hand-review results can be laid side by side for every session fix PR that got both, without reading run logs.
- **SC-008**: Checked-in evidence shows, in 100% of tested cases, that (a) no secret of any kind (model credential, App token or other) is reachable from the job that runs the pull request's code (an attempt to read one from within it finds nothing); (b) nothing that job writes can change the checking job's recorded results except through the staged exit codes and output (an attempt to overwrite them has no effect); (c) neither agent job holds a write credential (a write attempt from within either fails); and (d) no code of the pull request runs other than the change's own named check and the gate suite (an attempt to run anything else is refused or absent from the allowed tools). *(Spec review round 1, owner decision 2026-11-22.)*

## Assumptions

- The originating issue, backlog line or failing run of a session fix PR is identifiable from the pull request (a cited `#N`, a backlog line reference, or a run URL); when none is, the edge case above applies.
- Sonnet for both agent jobs, no effort override, and a 5-round per-pull-request budget are defaults the owner confirms by approving this spec; each is overridable by a repository variable (FR-024, FR-025). *(Spec review round 1, owner decision 2026-11-22.)*
- "Blocking" follows the deterministic rule in FR-013; on #1102 two of five blocking calls were arguable (a gate not enforcing what its spec says; a failure only in a private repository, not verified). Under FR-013 the latter is non-blocking until its reachability is checked.
- The report-only period ends by a later owner decision, informed by the FR-029 comparison; this feature sets no automatic end.
- The reviewer counts as the fix-PR merge rule's "separate session" only if a later decision says so; this feature does not change that rule (FR-028).
- #1110's convergence goal for the lifecycle review gate is met when the gate moves onto this reviewer in its own later proposal; this feature supplies the memory (identity across rewording, recorded dismissals) that move will use, and does not change the gate.
- Spec 119's maintainer drop action and the lifecycle review gate's `tasks.md` folding are untouched; a later move of the gate onto this reviewer decides how they map onto FR-018 dismissals.
- The round record the three Actions reviewers share today (`round_record_marker`, `read_round_records` in `wc_convergence.py`) and the finding fingerprint (`wc_review_finding_fingerprint.py`) are the starting points the plan stage extends.

## Dependencies

- Spec 116 (shared round record), `board_merge.py`'s `verification_run_confirms` (run confirmation precedent), `wc_gate_verdict.py` (verdict bound to a trusted commit), and the `wing-commander-tool-args` composite (tool lists).
- Issue #1110 (closed as folded into this feature), Maintenance backlog #889 (the line on the fix-PR merge-rule procedure).
