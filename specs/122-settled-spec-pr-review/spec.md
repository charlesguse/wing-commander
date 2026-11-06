# Feature Specification: Review a Spec PR Automatically Once Clarification Has Settled It

**Feature Branch**: `122-settled-spec-pr-review`

**Created**: 2026-11-03

**Status**: Draft

**Lifecycle issue**: #1094

**Input**: User description: "Review a spec PR automatically once clarification has settled it. A spec PR gets an independent review today only when a local session runs one by hand. Spec 062 (#476) gave final PRs an automated review gate, but its FR-002 leaves spec and plan PRs out on purpose: they have no implement stage behind them, so a not-clean round has nothing to fold into. The manual reviews have been worth running (#1086 / spec 120: FR-002 needed an Actions: write permission the App doesn't hold; #1078 / spec 119: FR-022 added a ninth merge condition conflicting with constitution X's eight gates). None of those reviews left a record on GitHub. When a spec PR has settled, an independent review runs on its own and posts its result on the PR, before the owner reads it: settled = intake or clarify announced the PR ready, no NEEDS CLARIFICATION markers, issue at stage:spec, head unchanged since; one review per head; checks buildability against current main's permissions/secrets/variables, conflicts with the constitution and live contracts of merged specs, contradictory/untestable/undecided requirements; reports a verdict and structured findings on the PR, owner-only decisions as questions with options, a recommendation and any precedent cited; bounded by a round budget and the spec 116 convergence check; a WING_COMMANDER_*_PAUSED kill switch. Spec PR merge stays human; the review never approves, requests changes, or merges. Out of scope: final PRs; any change to who merges a spec or plan PR."

## Overview

Spec 062's lifecycle review gate reviews the **final** implementation pull
request of a lifecycle. Its FR-002 deliberately excludes the spec pull
request (`spec-draft/…` → `main`) and the plan pull request, because a
not-clean round on them has no implement stage to fold findings into.

That exclusion left a gap the owner has been filling by hand. On the last two
specs a local session reviewed the spec PR before merge and each time found a
defect that would otherwise have surfaced only in implement:

- **#1086 (spec 120)** — FR-002 required the App to hold `Actions: write`,
  which it does not. The owner chose a different remedy before merge.
- **#1078 (spec 119)** — FR-022 added a ninth merge condition, conflicting
  with constitution X's eight gates. The owner decided to file a constitution
  amendment alongside the feature.

#1078 took three such reviews and #1086 took two. None left a record on
GitHub: both PRs merged with no review and no comment, and the findings exist
only in session transcripts.

This feature makes that review automatic, gives it a durable record on the
spec PR, and keeps it strictly advisory. It **prepares** the owner's review;
it never replaces it. The spec PR merge stays human (constitution V).

## Clarifications

### Session 2026-11-03 (answers on #1094)

- Q: Are plan PRs in scope when `WING_COMMANDER_PLAN_REVIEW` is `pr`, or is
  this feature spec-PR-only? → A: **C — spec PRs only.** Reviewing plan PRs
  is a named follow-up, recorded in Out of Scope (FR-001).
- Q: Which reviewer model and effort? → A: **A — Opus (`claude-opus-5-5`)
  with the full `code-review` recipe at `high` effort.** Constitution II
  assigns Opus to specification work because the spec is the foundation every
  later stage consumes; the manual reviews that caught the spec 119 and 120
  defects ran this way. The final-PR gate's Sonnet default is for
  implementation review, a different tier (FR-008).
- Q: What happens to findings beyond the report? → A: **B and C together.**
  Every finding is reported on the spec PR. Unambiguous errors are fixed by
  the reviewer pushing to the `spec-draft/` branch; anything needing an owner
  trade-off goes back to clarify as new questions on the lifecycle issue,
  each with a recommendation, and is answered there. The spec defines the
  "unambiguous" boundary, and a pushed head must settle again before another
  round (FR-015, FR-015a–FR-015d). This is how the manual reviews of #1078 and
  #1086 worked, except that their decisions went to the owner in chat rather
  than on the issue.

### Session 2026-11-06 (owner, after the spec PR review)

- Q: What deterministic check backs the reviewer's "unambiguous" call before
  it pushes a fix? → A: **(b) Path bound, size cap, and a cited
  precedent.** The fix diff may touch only the spec's own files (FR-015b),
  stays under a size cap, and each fix cites a location on main that
  deterministic code confirms exists. Over any bound, the finding is reported
  but not pushed. This mirrors constitution X's size-and-path backstop
  (FR-026).
- Q: How does a spec PR head that a human pushed (no fresh readiness
  announcement) become reviewable? → A: **(b) A maintainer's manual dispatch
  for that one pull request counts as the settling act.** It still checks that
  the PR is open and carries no open clarification marker. It skips the
  announcement and unchanged-head conditions, because a maintainer dispatch is
  authorization under constitution V (FR-027).
- Q: Do failed rounds (rate limit, timeout, malformed output) count against
  the round budget? → A: **(b) A separate cap per head on failed attempts
  (2), then a hand-off to the owner.** Transient failures don't use up review
  rounds, and retries stay bounded, unlike parked #869 (FR-028).

### Session 2026-11-06 (owner, after spec review 2)

- Q: How do the review's owner-decision questions reach clarify, which reads
  only open clarification markers in spec.md? → A: **A. Write markers too.**
  In the same path-bounded push, the round writes each question into spec.md
  as a colon-form clarification marker and also posts it on the issue, as
  intake does. The marker check in FR-002(b) then blocks a re-review until
  clarify folds the answers. No published stage changes. Marker lines are
  not fixes and are exempt from FR-026's citation check (FR-015c, FR-026).
- Q: Where may a fix's cited precedent live? → A: **A. Where it actually
  is.** A line on the default branch for the constitution, merged specs and
  workflow facts; a line in the spec's own files on the reviewed head for its
  recorded answers; an issue comment in this repository, confirmed through
  the API, for recorded owner decisions (FR-026).
- Q: Does a maintainer's dispatch still require `stage:spec`? → A: **Yes**,
  answered from the spec itself: FR-027 lists only the announcement and
  unchanged-head conditions as skipped, so the stage check stands. The
  maintainer clears `stage:clarify`, or lets clarify finish, before
  dispatching (FR-027).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A settled spec PR is reviewed and the result is on the PR (Priority: P1)

The owner opens a spec PR that intake (or the last clarify round) has
announced ready. A review comment is already there: a verdict ("ready for the
owner" or "not ready"), the findings behind it, and — for anything only the
owner can decide — a question with options and a recommendation.

**Why this priority**: This is the whole value: the defects the manual
reviews caught are caught without a local session, and the result is on
GitHub rather than in a transcript.

**Independent Test**: Take a spec PR whose lifecycle issue is at
`stage:spec`, with no `NEEDS CLARIFICATION` markers and a ready
announcement newer than its head commit. Run the review once. A single
review result appears on the PR naming the reviewed head SHA, a
verdict, and zero or more structured findings.

**Acceptance Scenarios**:

1. **Given** a settled spec PR whose spec requires a permission the pipeline's
   credential does not hold, **When** the review runs, **Then** the result
   carries verdict "not ready" and a finding naming the requirement and the
   missing permission.
2. **Given** a settled spec PR whose requirement contradicts a constitution
   principle, **When** the review runs, **Then** a finding names the
   requirement and the principle it conflicts with.
3. **Given** a settled spec PR with no defects the review can find, **When**
   the review runs, **Then** the result carries verdict "ready for the owner"
   and states that no findings were raised.
4. **Given** any completed review, **Then** the pull request has no approval,
   no changes-requested review, and has not been merged by the pipeline.

---

### User Story 2 - Unsettled PRs are never reviewed (Priority: P1)

While a clarify round is in progress, or while an owner's answer is still
being written into the spec, nothing reviews the PR. A review of a moving
target would be noise the owner has to read and discard.

**Why this priority**: Reviewing an unsettled spec wastes budget and posts
findings that the next clarify commit invalidates; it would erode trust in
the result.

**Independent Test**: For each unsettled condition below, run the selection
once and confirm the PR is skipped with the reason recorded in the run log.

**Acceptance Scenarios**:

1. **Given** a spec PR whose lifecycle issue carries `stage:clarify`, **When**
   the selection runs, **Then** the PR is not reviewed.
2. **Given** a spec PR whose spec.md still contains a
   `NEEDS CLARIFICATION` marker, **When** the selection runs, **Then** the
   PR is not reviewed.
3. **Given** a spec PR whose head commit is newer than the most recent ready
   announcement, **When** the selection runs, **Then** the PR is not reviewed.
4. **Given** a spec PR with no ready announcement at all, **When** the
   selection runs, **Then** the PR is not reviewed.

---

### User Story 3 - One review per head, re-eligible on a new head (Priority: P1)

A head that has been reviewed is not reviewed again. When the owner's answer
lands as a new commit and the PR settles again, the new head is reviewed.

**Why this priority**: Without it the review either repeats itself every
cycle (cost, noise) or never sees the owner's resolution.

**Independent Test**: Review a settled head; run the selection again on the
same head and confirm it is skipped as already reviewed. Push a new commit,
let it settle (new ready announcement), and confirm it is selected.

**Acceptance Scenarios**:

1. **Given** a head SHA already carrying a review result, **When** the
   selection runs, **Then** that head is not reviewed again.
2. **Given** a previously reviewed PR that received a new commit and a new
   ready announcement, **When** the selection runs, **Then** the new head is
   reviewed and the result names the new SHA.

---

### User Story 4 - Decisions come back as questions, with precedent cited (Priority: P2)

Where a finding needs a choice only the owner can make, the review phrases it
as a question with options and a recommendation, posted on the lifecycle
issue for the clarify stage to take. Where an existing precedent already
settles it, the finding is an unambiguous error: the review pushes the fix to
the `spec-draft/` branch and cites the precedent, in the same manner as the
`answer-from-precedent` skill.

**Why this priority**: The manual reviews' most valuable outputs were
decisions (spec 120's Q1 B, spec 119's constitution amendment). Phrasing them
ready-to-answer saves the owner a round-trip.

**Independent Test**: Seed a spec with a requirement whose remedy the
constitution or a merged spec already decides, and one whose remedy needs an
owner trade-off. Confirm the first finding cites the precedent and the second
carries options and a recommendation.

**Acceptance Scenarios**:

1. **Given** a finding a precedent settles, **Then** the finding cites the
   precedent's location (constitution principle, spec and FR, or recorded
   owner decision).
2. **Given** a finding requiring an owner trade-off, **Then** it is phrased
   as a question with at least two options and one recommendation, posted on
   the lifecycle issue and written into spec.md as a clarification marker
   (FR-015c), and the issue moves from `stage:spec` to `stage:clarify`.
3. **Given** a finding that is an unambiguous error (FR-015a), **Then** the
   fix is pushed to the `spec-draft/` branch, the result comment lists the
   fixing commit SHA, and the pushed head is not reviewed until it settles
   again (FR-015d).
4. **Given** a finding where more than one correction is reasonable,
   **Then** no fix is pushed for it and it is raised as a question.

---

### User Story 5 - The loop is bounded and can be stopped (Priority: P2)

A spec that keeps drawing findings round after round stops being reviewed and
is handed to the owner with the reason. A maintainer can pause the whole
feature with one repository variable.

**Why this priority**: Constitution II and X require bounded autonomy; spec
116 established that a review loop must notice when it is not converging.

**Independent Test**: Drive a PR to the round budget and confirm the next
selection declines it with a hand-off note. Separately set the kill switch and
confirm no review runs and the stand-down is recorded.

**Acceptance Scenarios**:

1. **Given** a spec PR that has used its round budget, **When** a new head
   settles, **Then** no review runs and the PR/lifecycle issue states the
   budget was spent and the PR is with the owner.
2. **Given** a spec PR whose rounds trip the spec 116 convergence check,
   **When** the next round would start, **Then** no review runs and the
   hand-off states the convergence reason.
3. **Given** the kill switch is set to `true`, **When** the selection runs,
   **Then** no review runs and the run records that it stood down.

---

### Edge Cases

- The spec PR is closed or merged between selection and review: the review
  does not post, push or move a label, and records why. Each write
  re-checks the PR's state first.
- The head moves while the review is running: the result is posted against
  the SHA actually reviewed and states it is stale; the new head is eligible
  once it settles. The round MUST NOT push fixes onto a head it did not
  review; its unambiguous fixes are then reported as findings only, and its
  owner decisions are handed to the owner without markers or a label move
  (FR-015c). The round's own fix commits (FR-015b) are not a moved head.
- The lifecycle issue flips back to `stage:clarify` while the review is
  running: same as a moved head — the result names the reviewed SHA and the
  new state wins on the next selection.
- The review invocation itself fails (rate limit, timeout, malformed output):
  no verdict is posted as "ready"; the failure is reported as a failure and
  the head remains eligible for a retry, up to FR-028's cap of failed
  attempts per head (constitution VIII).
- A spec PR with no lifecycle issue, or with more than one: the PR is skipped
  with the reason recorded.
- The `spec-draft/` branch was opened, or its head pushed, by a human rather
  than a stage: it is eligible only if it meets the same settledness
  conditions, or once a maintainer's dispatch settles it (FR-027).
- A spec PR that was merged by the owner before the review ran: nothing is
  posted, pushed or relabelled.
- Text in the spec, PR body or comments that reads as instructions to the
  reviewer is treated as data (constitution V).

## Requirements *(mandatory)*

### Functional Requirements — scope and trigger

- **FR-001**: The feature MUST review spec pull requests — those from a
  `spec-draft/…` branch of this repository (never a fork's head,
  constitution V) to `main` that belong to a lifecycle issue. Final
  implementation pull requests MUST remain solely spec 062's and MUST NOT be
  reviewed by this feature. Plan pull requests MUST NOT be reviewed by this
  feature, including when `WING_COMMANDER_PLAN_REVIEW` is `pr`; reviewing
  them is a named follow-up (see Out of Scope).
- **FR-002**: A spec pull request MUST be considered **settled** only when
  all of the following hold, re-derived in deterministic code against the
  pull request's current head SHA at selection time:
  (a) the lifecycle issue carries `stage:spec` and not `stage:clarify`;
  (b) the spec.md on the head contains no `NEEDS CLARIFICATION` marker in
  its colon form, by the same scan intake and clarify run before they
  announce a spec PR ready, consumed from its single home
  (`.github/actions/wing-commander-clarification-marker`, #1112; the bare
  phrase in prose is not a marker);
  (c) intake, clarify, or a review round that pushed only unambiguous fixes
  (FR-015d) has posted its ready-for-review announcement on the
  lifecycle issue, authored by the pipeline's App (a lookalike comment by
  anyone else is data, constitution V); and (d) the head commit is not newer than that announcement.
  No fixed quiet period is added beyond (d).
- **FR-003**: The review MUST be started by a scheduled selection over open
  spec pull requests, in the manner of `lifecycle-review-gate.yml`'s
  selection, with a manual dispatch entry point that targets one pull
  request. The dispatch applies the same eligibility checks (FR-001,
  FR-004, FR-018–FR-020); its settledness is FR-027's, not FR-002's.
- **FR-004**: The feature MUST record the head SHA a completed round
  reviewed and MUST NOT review a head SHA a completed round already covered
  (as spec 062 FR-004). A new head becomes eligible once it is settled.
- **FR-005**: A failed review round (no valid result produced) MUST NOT mark
  the head as reviewed.

### Functional Requirements — the review itself

- **FR-006**: The review MUST be independent of the stage agents that wrote
  the spec — a separate invocation sharing no context with intake or clarify.
- **FR-007**: The review MUST check, at minimum:
  (a) whether each requirement can be built on current `main` with the
  permissions, secrets and repository variables the pipeline actually has,
  read from their documented and referenced surface on `main` (the App
  permissions `docs/setup.md` lists, which Gate 12 enforces, and the
  `secrets.*` and `vars.*` the workflows reference): neither the App token
  nor the workflow's own token can list the repository's secrets or
  variables;
  (b) conflicts with the constitution and with the live contracts of merged
  specs (`specs/*/contracts/`) and the behaviour on `main`;
  (c) requirements that contradict each other, cannot be tested, or leave a
  decision unstated.
- **FR-008**: The review invocation MUST declare an explicit model, effort
  and bounded turn budget (constitution II). The default model MUST be
  `claude-opus-5-5`, running the full `code-review` recipe at `high` effort —
  the specification-work tier constitution II assigns, and the configuration
  the manual spec reviews ran with. Spec 062's Sonnet default is for
  implementation review and MUST NOT be inherited. The model and effort MUST
  be overridable by a repository variable without editing a workflow.
- **FR-009**: Spec contents, pull request titles, bodies, diffs and comments
  MUST be framed to the reviewing agent as untrusted data, never
  instructions (constitution V).
- **FR-010**: The review MUST NOT approve the pull request, request changes,
  merge it, or alter its labels' merge-relevant state. Pushing unambiguous
  fixes to the `spec-draft/` branch (FR-015b), pushing FR-015c's
  clarification marker lines to that branch, and moving the lifecycle issue
  back to `stage:clarify` (FR-015c) are the only writes it makes beyond its
  comments, reviews and commit status. Merge of a spec pull request stays
  human (constitution V). Nothing it posts may start pr-conversation or
  clarify; both already ignore bot actors (constitution V,
  `wing-commander-2-clarify.yml` and `wing-commander-9-pr-conversation.yml`).

### Functional Requirements — the result

- **FR-011**: Each completed round MUST post one result on the spec pull
  request, as a pull request review with the `COMMENT` event, naming the
  round number, the reviewed head SHA, a verdict of exactly "ready for the
  owner" or "not ready", and the findings, with spec 116's round record
  appended last (spec 116 `contracts/convergence-signals.md`, "Round
  records": only the App's own reviews are read back).
- **FR-012**: Findings MUST be emitted as structured records in the shape the
  pipeline's existing review findings use (title, what, evidence with file
  paths and optional quoted lines, fingerprint basis), so rendering and
  deduplication are reused, not re-derived.
- **FR-013**: The verdict MUST be computed in deterministic code from the
  structured findings (any finding on the reviewed head ⇒ "not ready",
  including one the round fixed on the branch; the pushed head gets its own
  verdict in the next round, FR-015d), not taken from the reviewing agent's
  prose (constitution IX).
- **FR-014**: A finding that requires a decision only the owner can make
  MUST be phrased as a question with at least two options and a
  recommendation. A finding a precedent already settles MUST cite that
  precedent (constitution principle, merged spec FR, or recorded owner
  decision), as the `answer-from-precedent` skill does.
- **FR-015**: Every finding MUST be reported in the round's result comment
  (FR-011). Beyond the report, each finding MUST be classified as either an
  **unambiguous error** (FR-015a), which the round fixes on the branch
  (FR-015b) unless FR-026's checks block the fix, in which case it is
  reported only and left to the owner, or an **owner decision**, which
  re-enters clarify (FR-015c).
- **FR-015a**: A finding is an unambiguous error only when exactly one
  correction is consistent with what is already decided, and that correction
  introduces no new behaviour, scope or trade-off. "Already decided" means
  the spec's own recorded clarification answers, the constitution, a merged
  spec's FR or live contract, a recorded owner decision, or a fact on current
  `main` (a file, step, job, label, variable or permission as it actually
  exists). Examples: a requirement contradicting the spec's own recorded
  answer; a wrong file, step or workflow name; a requirement that cannot be
  built with the App's actual permissions where a precedent already decides
  the remedy. A finding with more than one reasonable correction, or whose
  correction a reviewer would have to choose, is an owner decision. When in
  doubt, the finding MUST be treated as an owner decision.
- **FR-015b**: For unambiguous errors, the round MUST push the corrections
  as commits to the spec pull request's `spec-draft/` branch, and the result
  comment MUST list each such finding with the commit SHA that fixed it and
  the precedent or fact it relied on. The push MUST NOT touch files outside
  the lifecycle's spec directory (`[<P>/]specs/NNN-*/`, constitution
  Operational Constraints), and deterministic code MUST check that path
  bound on the round's diff before anything is pushed (constitution IX).
- **FR-015c**: For owner decisions, the round MUST post them on the
  lifecycle issue as new clarification questions — each with at least two
  options and a recommendation (FR-014) — and move the lifecycle issue from
  `stage:spec` back to `stage:clarify`, so the answers are taken and folded
  into the spec by the clarify stage, not in chat. In the same path-bounded
  push (FR-015b), the round MUST also write each question into the spec's
  spec.md as a colon-form clarification marker, so clarify, which works from
  open markers, can fold the answers, and FR-002(b)'s marker scan blocks a
  re-review until it has (owner decision 2026-11-06, after spec review 2).
  The issue moves to `stage:clarify` only once the marker lines are on the
  branch: when they cannot be pushed (the head moved, FR-026's path or size
  check blocks them, or the push is refused), the round MUST NOT move the
  label, and states the questions on the lifecycle issue as a hand-off to
  the owner (FR-017) and in the result comment, as FR-015 does for a blocked
  fix. Clarify can fold only questions that exist as markers, and it still
  runs on a reply while the issue is at `stage:spec`
  (`wing-commander-2-clarify.yml`), where it finds no open marker and asks
  for a clearer answer (`clarify.yml`'s prompt, step 2). So the hand-off MUST
  say that a reply on the issue will not be folded, and that the owner
  answers by editing the spec on the branch, which is then settled by a
  maintainer's dispatch (FR-027) or a later stage's announcement (FR-015d).
- **FR-015d**: A head the round itself pushed MUST settle again under
  FR-002 before another round reviews it. When the round raised owner
  decisions, clarify's ready announcement after folding in the answers
  settles it. When the round raised only unambiguous errors and pushed a
  fix for every one of them (none blocked by FR-026), the round MUST
  post a ready announcement naming the pushed head after its push, which
  makes that head eligible at the next selection. Otherwise (a fix blocked
  by FR-026, or decisions handed to the owner without markers) the round
  posts no announcement, and the head settles only by a later stage's
  announcement or a maintainer's dispatch (FR-027). Either way the following
  review is a new round that counts against the round budget (FR-018) and
  the convergence check (FR-019).
- **FR-016**: Each round MUST post a commit status on the reviewed head
  under a context distinct from spec 062's, with the workflow's own token
  and a job-level `statuses: write` permission as spec 062's gate does (the
  App holds no Commit statuses permission, `docs/setup.md`), reporting
  success for "ready for
  the owner", failure for "not ready", budget exhausted, convergence stop,
  or review failure, so the result is visible in the PR's checks. This
  feature MUST NOT make that status a required check.
- **FR-017**: The round's outcome MUST also be stated in one line on the
  lifecycle issue (constitution III).

### Functional Requirements — bounds and controls

- **FR-018**: Rounds per spec pull request MUST be bounded by a round budget.
  On exhaustion, no further round runs; the pull request and lifecycle issue
  state that the budget was spent and the pull request is with the owner.
- **FR-019**: Before each round after the first, the feature MUST apply the
  spec 116 convergence check to the PR's prior rounds and, if it trips, stop
  and hand the PR to the owner with the convergence reason stated. The
  convergence arithmetic MUST be reused from its existing single home, not
  re-implemented. Re-eligibility after a convergence stop follows spec 116
  FR-008: a later head re-arms the review only when the PR's diff against
  `main` differs from the stopped round's.
- **FR-020**: The feature MUST carry a repository-level kill switch named in
  the `WING_COMMANDER_*_PAUSED` family (e.g.
  `WING_COMMANDER_SPEC_REVIEW_PAUSED`), settable without editing a workflow;
  when set, no round runs and the stand-down is recorded in the run.
- **FR-021**: Any review step that cannot reach its subject (pull request
  unreadable, spec missing, review output malformed) MUST report failure and
  MUST NOT report "ready for the owner" (constitution VIII).

### Functional Requirements — placement and plumbing

- **FR-022**: The feature MUST live in this repository's consuming
  instrument, as spec 062's gate and the board loop do, and MUST NOT add a
  stage to the published contract (constitution VII).
- **FR-023**: Logic this feature shares with spec 062's gate — selection,
  head-SHA bookkeeping, findings rendering, the cost line, the convergence
  check — MUST be consumed from its existing single home, never pasted.
- **FR-024**: The per-round cost MUST be reported through the existing
  cost-line single home.
- **FR-025**: Every deterministic decision the feature makes (settledness,
  including a dispatch's (FR-027), eligibility, verdict, budget,
  convergence stop, the fix checks (FR-026), whether the label moves to
  `stage:clarify` (FR-015c) and whether a post-push ready announcement is
  posted (FR-015d), the failed-attempt cap (FR-028)) MUST be exercised by a
  checked-in fixture reachable through the gate registry and run identically
  locally and in CI (constitution VIII).

- **FR-026**: Before the reviewer's fix commits are pushed (FR-015a,
  FR-015b), deterministic code MUST check that the fix diff touches only the
  spec's own files, stays within a fixed size cap, and that each fix cites a
  precedent that exists where it lives: a file:line on the default branch for
  the constitution, a merged spec or a workflow fact; a file:line in the
  spec's own files on the reviewed head for its recorded answers; or an issue
  comment in this repository, confirmed through the API, for a recorded owner
  decision. FR-015c's clarification marker lines are not fixes and are exempt
  from the citation check, but not from the path and size checks. A fix that fails any check
  MUST be reported as a finding and not pushed (constitution IX; X's
  size-and-path backstop is the precedent).
- **FR-027**: A maintainer's manual dispatch naming one spec pull request
  MUST count as that head's settling act; a dispatch whose triggering actor
  is a bot is not a maintainer's. It still requires the pull request
  to be open on this repository's `spec-draft/` branch, requires that the
  lifecycle issue carries `stage:spec`, and requires that
  FR-002(b)'s colon-form marker scan finds no open clarification marker. It
  skips the readiness-announcement and unchanged-since-announcement
  conditions of FR-002.
- **FR-028**: Failed rounds (FR-005) MUST be counted per head, separately
  from the round budget. After 2 failed attempts on one head, the review
  MUST stop retrying that head and hand off to the owner on the lifecycle
  issue, naming the failure. It resumes only on a new head or a manual
  dispatch.

### Key Entities

- **Spec pull request**: A `spec-draft/…` → `main` pull request linked to a
  lifecycle issue; the subject of the review.
- **Ready announcement**: The intake or clarify stage's posting — or a review
  round's, after pushing only unambiguous fixes (FR-015d) — that the spec PR
  is ready for review; its timestamp anchors settledness.
- **Review round**: One review of one head SHA — round number, SHA, findings,
  verdict, outcome (reviewed / failed / budget-exhausted / convergence-stop /
  stood-down).
- **Finding**: A structured defect record, classified as an unambiguous
  error (fixed on the branch, with the fixing commit SHA) or an owner
  decision (a question with options and a recommendation, re-entering
  clarify); may carry a precedent citation.
- **Round budget**: The maximum number of rounds per spec pull request.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Every spec PR that reaches a settled state receives a review
  result on the PR before the owner merges it, with no local session
  involved — 100% of settled heads over the first five lifecycles after
  release.
- **SC-002**: Zero reviews run on unsettled heads (clarify in progress,
  markers present, head newer than the ready announcement and not settled by
  a maintainer's dispatch, FR-027) across the same period, verified from run
  logs.
- **SC-003**: No head SHA is reviewed more than once by a completed round.
- **SC-004**: Replaying the spec PRs of #1078 and #1086 at the heads the
  manual reviews saw produces a "not ready" verdict with a finding naming
  the same requirement (spec 119 FR-022; spec 120 FR-002).
- **SC-005**: The pipeline never approves, requests changes on, or merges a
  spec PR — zero such events attributable to this feature.
- **SC-006**: Setting the kill switch stops all new rounds from the next
  scheduled selection onward.
- **SC-007**: Every owner decision a round raises is posted on the
  lifecycle issue, not left in chat or only on the PR — zero rounds whose
  decisions are absent from the issue; and every fix a round pushes touches
  only the lifecycle's spec directory.

## Assumptions

- "Settled" means only "head unchanged since the ready announcement" (plus
  stage and marker conditions); no additional fixed quiet period. Clarify
  always posts its announcement after pushing, so a head newer than the
  announcement reliably means a write in progress.
- The trigger is a scheduled selection plus manual dispatch, matching
  `lifecycle-review-gate.yml`. A purely event-driven trigger is not relied on
  because the ready announcement is a bot comment and every comment-driven
  stage ignores bot actors (constitution V), and the App holds no Actions
  permission with which to dispatch a workflow.
- The feature is consuming-instrument only (this repository), like spec
  062's gate and the board loop; adopters are not offered it in this cut.
- A commit status is posted for visibility but not made required; making it
  required is the owner's repository setting, not this feature's.
- The round budget defaults to the value the other review loops use (5),
  as a one-line, PR-reviewed knob.
- Concurrency with the three-lifecycles-in-implement cap is unaffected: spec
  PRs are pre-implement.

## Dependencies

- Spec 062 (lifecycle review gate): selection pattern, head-SHA bookkeeping,
  findings shape, kill-switch family.
- Spec 116 (review convergence): the convergence check and its single home.
- Intake and clarify stages' ready-for-review announcement.
- The `code-review` capability and the `answer-from-precedent` skill's
  precedent-citation conventions.
- The cost-line single home (`wing-commander-metrics-summary`).

## Out of Scope

- Final implementation PRs — spec 062 already reviews them, after implement
  has converged (its FR-003).
- Plan PRs, including when `WING_COMMANDER_PLAN_REVIEW` is `pr` — a named
  follow-up feature, so the intent is kept (clarification Q1).
- Any change to who merges a spec or plan PR.
- Supplying repository-authored additional review context beyond what the
  review already reads (as spec 062 FR-012 defers it).
