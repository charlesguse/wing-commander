# Feature Specification: The Agent's Own Push Credential Outlives Its Cycle

**Feature Branch**: `071-agent-push-credential`

**Created**: 2026-09-25

**Status**: Draft

**Input**: User description (lifecycle issue #545, routed from the board loop; originating issue #402): "An agent stage's own `git push` credential expires one hour after the job starts, so an agent that is still working after minute 60 keeps committing locally and can no longer publish any of it. Spec 052 (#345) fixed the steps *around* the agent step and left this one out of scope on purpose (FR-008); its requirement was that the residual risk be recorded and a follow-up filed when its pull request opens. Evidence — spec 052's own first implement cycle, run 35450562414 (2026-09-19): the job started 15:02 UTC with a token minted about 15:02:45 and expiring about 16:02:45; the agent pushed twelve commits in the first 57 minutes, the last at 15:59:04; nothing was pushed for the next 51 minutes while the job kept running (cycle agent, then retry agent, both ending 'out of turn budget') until the stall marker at 16:50:24; the stall notice said the branch 'never advanced' because the closing metadata commit was one of the pushes that could not happen. The retry arm makes it structural: a job that runs the cycle agent and then the retry agent puts the retry entirely past the token's lifetime whenever the cycle takes more than about an hour. First live occurrence after spec 052 — run 35486482556 (2026-09-20), implement cycle 1 of spec 056: 12 pushes succeeded to 04:23:13; at 04:36 a commit's push failed with `remote: Invalid username or token. Password authentication is not supported for Git operations. fatal: Authentication failed`; the agent kept working, committing five more times and retrying the push ten more times, every one with the same error, the last three labelled 'Final push attempt', 'One more push retry', 'Final push attempt before wrapping up'; the cycle ended over budget (446 of 180 intended turns) with six commits unpushed, which spec 052's post-agent refresh then recovered at 04:55. Nothing was lost that time, but the agent spent a measurable share of its turns retrying a push that could not succeed and had no way to tell an expired credential from a transient failure; a cycle that hits the runaway ceiling while pushes fail, or whose agent step is killed or cancelled, would not reach the recovery step. Options, a design choice rather than a deterministic fix: refresh the remote under the agent with a credential helper that mints on demand; bound the agent step by wall clock below the token lifetime (for example 50 minutes) and let the implement/converge loop's next cycle continue with a fresh token (declined for the credential problem in spec 052's clarifications); have the agent push early and often (mitigation only — the evidence shows it already does); split the retry into its own job so it starts with a fresh token; or tell the agent, in the prompt or a tool-result hint, that an `Authentication failed` on push after roughly an hour is the credential lifetime and it should stop retrying and finish."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - An agent still working after the credential lifetime can still publish its work (Priority: P1)

An implement cycle is bounded by a turn ceiling, not a clock, and a productive cycle routinely runs longer than an hour. The credential the agent's own `git push` authenticates with was established when the job started and expires at minute sixty. From that moment the agent keeps doing real work — editing files, running the gate suite, committing — and every commit it makes stays on the runner. What the maintainer needs is for the length of a cycle to have no bearing on whether the cycle's commits reach the spec branch.

**Why this priority**: This is the defect. It is the one part of an agent stage that spec 052 knowingly left exposed, and the exposure grows with exactly the thing the pipeline is designed to permit — a long, productive cycle. It has already produced one stall notice that reported the opposite of what happened (run 35450562414) and one cycle that ended with six commits stranded (run 35486482556).

**Independent Test**: Drive an agent stage whose agent step is still pushing after the credential lifetime has elapsed, and confirm every push the agent makes succeeds and the spec branch carries every commit the agent created, with no authentication failure in the agent's transcript.

**Acceptance Scenarios**:

1. **Given** an agent step that is still running and committing after the bot credential established at job start has expired, **When** the agent pushes, **Then** the push succeeds and the commit is visible on the spec branch.
2. **Given** the same stage, **When** the agent step finishes well inside the credential lifetime, **Then** behaviour is unchanged from today — the same pushes, the same commits, the same reported outcome, and no additional agent turns consumed.
3. **Given** a job that runs a second agent step after the first (the implement stage's retry and progress arms), **When** the second agent pushes at a point past the credential lifetime measured from job start, **Then** its pushes succeed on the same terms as the first agent's.
4. **Given** an agent step whose closing lifecycle-record commit is made after the credential lifetime, **When** the job's deterministic read-back runs, **Then** it observes the advanced record, and the stall path does not report that the branch never advanced.

---

### User Story 2 - An agent never burns its budget on a push that cannot succeed (Priority: P1)

An agent's push fails with `Authentication failed`. The agent cannot tell that from a transient network failure or a race with a concurrent push, so it does the sensible thing and retries — in the observed run, ten more times across sixteen minutes, interleaved with more commits, ending with three attempts it itself labelled final. Those turns came out of the same budget the actual work draws on, in a cycle that then reported over budget at 446 of 180 intended turns.

**Why this priority**: This is the cost that is being paid on every long cycle right now, and it is paid even in the runs where nothing is ultimately lost. It is independently valuable: whatever mechanism User Story 1 ships, an agent that meets an unrecoverable push failure should stop spending turns on it and spend them finishing instead. It also bounds the damage in the case User Story 1's mechanism cannot cover (a mint that fails outright).

**Independent Test**: Seed an agent step whose push fails with the credential-expiry signature, and confirm the agent stops retrying the push within a small, stated number of attempts and proceeds to finish its work, rather than continuing to retry until its budget is spent.

**Acceptance Scenarios**:

1. **Given** an agent whose `git push` fails with an authentication failure that the pipeline can attribute to credential expiry, **When** the agent decides what to do next, **Then** it stops retrying that push after a stated small bound and continues to finish and record its work locally.
2. **Given** an agent whose `git push` fails for a reason that is not credential expiry (a rejected non-fast-forward, a transient network error), **When** the agent decides what to do next, **Then** today's retry behaviour is unchanged — the guidance narrows only the unrecoverable case.
3. **Given** a cycle that stopped retrying under this guidance, **When** the maintainer reads the run, **Then** the reason the agent stopped is attributable to the credential rather than presented as the agent giving up on the task.
4. **Given** an agent that never meets a push failure, **When** the cycle completes, **Then** it consumes no additional turns and no additional invocations because of this feature.

---

### User Story 3 - A second agent in the same job does not start already expired (Priority: P2)

The implement stage runs a cycle agent, then — when the cycle is classified as needing it — a retry agent, then a progress agent, all in one job under one credential minted at job start. Whenever the cycle alone takes about an hour, the retry agent begins its work with a credential that is already dead, so *none* of the retry's pushes can succeed. This is not a tail risk that grows with duration; it is certain for that shape of job.

**Why this priority**: It converts the probabilistic exposure of User Story 1 into a deterministic one for the arm whose whole purpose is to rescue a cycle that went badly. It is P2 because User Story 1's remedy, if it covers every agent step, subsumes it — but the retry arm is the case that must be demonstrated, not assumed.

**Independent Test**: Drive an implement job whose cycle agent runs past the credential lifetime and whose retry agent then runs, and confirm the retry agent's pushes succeed.

**Acceptance Scenarios**:

1. **Given** an implement job whose cycle agent has already exhausted the credential lifetime, **When** the retry agent runs and pushes, **Then** its pushes succeed.
2. **Given** the same job, **When** the progress agent runs after the retry agent, **Then** its bot-acting work succeeds on the same terms.
3. **Given** a job where the cycle agent finishes quickly and no retry runs, **When** the job completes, **Then** no additional credential work is performed on its account.

---

### User Story 4 - Work the agent could not publish is never silently lost (Priority: P2)

Spec 052's post-agent refresh already rescues commits an agent could not push, and did so in run 35486482556 — six stranded commits reached the spec branch at 04:55. But that rescue only runs if the job gets that far. A cycle whose agent step is killed, cancelled, or stopped at a runaway ceiling while pushes are failing ends with commits on a runner that is about to be destroyed, and nothing tells the maintainer that happened.

**Why this priority**: It is the backstop behind User Story 1, and it is the difference between "an hour of work was delayed" and "an hour of work is gone with no record". It ranks P2 because the primary remedy should make it rare; it is not P3 because the failure it catches is unrecoverable.

**Independent Test**: Seed an agent step that ends with unpushed commits on the runner, and confirm that either the commits reach the branch or a record naming the unpublished work is posted where the maintainer will read it — never a silent completion.

**Acceptance Scenarios**:

1. **Given** an agent step that ended with commits the agent could not push, **When** the job continues, **Then** those commits reach the spec branch before the job ends.
2. **Given** an agent step that ended with unpushed commits and a job that cannot publish them, **When** the job ends, **Then** the lifecycle record or the run's own summary states that commits were created and not published, and names how many.
3. **Given** an agent step that pushed everything it committed, **When** the job ends, **Then** nothing additional is reported — the record appears only when there is something to report.

---

### User Story 5 - A newly added agent step cannot silently reintroduce the exposure (Priority: P3)

Six months from now someone adds an agent step to a stage, or adds a stage that runs one. Nothing in the repository tells them the credential the agent pushes with has a lifetime shorter than the step's possible duration, and nothing fails if they get it wrong. The defect returns and is found the next time a cycle runs long — which is how this one was found twice.

**Why this priority**: This repository's own rule is that a rule with no gate behind it lasts until the next session, and spec 052's sweep shipped exactly this class of check for the post-agent steps. It is P3 because the pipeline is correct without it — just not durably so.

**Independent Test**: Introduce, in a fixture, an agent step that does not follow the shipped remedy, and confirm the check fails and names the workflow, the job, and the step; revert it and confirm the check passes.

**Acceptance Scenarios**:

1. **Given** a fixture stage whose agent step does not follow the shipped remedy, **When** the check runs, **Then** it fails and names the workflow, the job, and the step.
2. **Given** every stage as shipped by this feature, **When** the check runs, **Then** it passes.
3. **Given** a tree where the check cannot locate the stages it inspects, **When** it runs, **Then** it fails loudly rather than reporting a pass over nothing.
4. **Given** each failure branch the check ships, **When** the gate suite runs, **Then** a checked-in fixture exercises that branch.

---

### Edge Cases

- **The agent step is killed or cancelled past the credential lifetime.** The post-agent recovery that rescued run 35486482556 is itself gated on the agent step having run to a conclusion. A step killed by a runner timeout or a run-level cancellation skips it, and every unpushed commit dies with the runner.
- **The runaway ceiling is reached while pushes are failing.** The cycle is cut off at its turn ceiling with commits unpublished; whether the recovery path still runs decides whether the work survives.
- **Establishing a credential under a running agent fails or is rate-limited.** Any mechanism that mints on demand multiplies mints by the number of pushes a cycle makes — the observed cycles pushed twelve to eighteen times each. A refused or throttled mint must be attributable, must not be reported as an agent failure, and must not leave the agent retrying blindly.
- **A push fails for a reason other than the credential.** A non-fast-forward rejection, a protected-branch refusal, or a transient network error must keep today's behaviour; narrowing the agent's retries must key on the expiry signature, not on every push failure.
- **A push issued just before the boundary.** A credential valid at the moment the push starts can expire during a large push. The remedy must not simply move the cliff a few seconds later.
- **A wall-clock bound in a stage with no loop to resume it.** The implement and converge loops re-dispatch, so a bounded cycle continues with a fresh credential. Intake, clarify, plan, tasks, finalize and pr-conversation have no such loop — a wall-clock bound there cuts the stage off with no continuation, which is a different outcome from the one it produces in implement.
- **A wall-clock bound changes what "exhausted" means.** Today a verdict of `exhausted` means the turn budget ran out, and the read-back, the retry gate, the truncated classification and the metrics all read it that way. A step that ends on a clock is a third outcome those consumers do not currently have a name for.
- **The end-to-end arm pushes to a scratch repository.** That stage's agent authenticates against a different repository under a separately minted credential, so a remedy expressed only in terms of the pipeline repository's own remote does not reach it.
- **A stage whose agent never pushes.** Stages that only read and comment cannot strand work and must pay no additional cost — no extra mints, no extra steps, no extra prompt text competing for the agent's attention.
- **An adopting repository pinned to an older release.** Adopters pin the published stages by tag; whatever ships must not require them to change an input, a secret, or a repository setting in order to keep working.
- **Credentials outliving the job.** Every credential this feature establishes must still be accounted for at teardown; the observed run already reported "Token expired, skipping token revocation" once.

## Requirements *(mandatory)*

### Functional Requirements

#### The agent's pushes succeed for as long as the agent runs

- **FR-001**: A `git push` made by a running agent step MUST succeed regardless of how long that agent step has been running, for every agent step in scope under FR-007.
- **FR-002**: The mechanism that achieves FR-001 is [NEEDS CLARIFICATION: which remedy does the owner choose? (a) a credential the agent's remote resolves freshly at push time, so every push carries a valid credential and the agent needs no change; (b) a wall-clock bound on the agent step below the credential lifetime, with the loop's next cycle continuing under a fresh credential; (c) a hybrid — a fresh-at-push-time credential for the loop-bearing stages plus a bound only where a bound is safe; the issue also lists splitting the retry arm into its own job, which fixes User Story 3 alone]. Whichever is chosen, the mechanism MUST be named once in this repository and referenced from every call site, per the single-home rule.
- **FR-003**: The remedy MUST hold for every agent step in a job, not only the first: a job that runs a cycle agent, then a retry agent, then a progress agent MUST give each of them pushes that succeed.
- **FR-004**: The remedy MUST NOT change behaviour for an agent step that finishes well inside the credential lifetime — the same pushes, the same commits, the same steps, the same reported outcome.
- **FR-005**: The remedy MUST cost no additional agent turns and no additional agent invocations.
- **FR-006**: When the remedy's own credential work fails — a mint refused, throttled, or otherwise unavailable — the failure MUST be attributable to the credential and to the site that needed it, and MUST NOT be reported as an agent failure or as a stage that never started.
- **FR-007**: The remedy MUST apply to [NEEDS CLARIFICATION: which agent steps are in scope? (a) only the implement stage's cycle and retry agents — the only steps observed to exceed the lifetime; (b) every agent step in the eight stages spec 052 swept (intake, clarify, plan, tasks, implement, finalize, pr-conversation, and the auto-update stage's end-to-end arm), matching that feature's single-sweep precedent; (c) every agent step whose duration is not already bounded below the credential lifetime, which is the rule spec 052 used to exclude the 10-minute-bounded steps]. Any agent step excluded MUST be recorded with the reason for its exclusion.
- **FR-008**: The end-to-end arm's agent, which pushes to a provisioned scratch repository under its own credential, MUST be covered on the same terms as the pipeline repository's own remote if it is in scope under FR-007, or recorded as excluded with a reason if it is not.
- **FR-009**: Any credential the remedy establishes MUST be accounted for when the job ends, leaving no live credential behind that the previous single-mint arrangement would have revoked.

#### The agent stops retrying a push that cannot succeed

- **FR-010**: The pipeline MUST give a running agent a way to recognise that a push failure is caused by credential expiry rather than by a transient or recoverable condition.
- **FR-011**: On recognising that condition, the agent MUST stop retrying the push after a stated small bound and continue to finish and commit its work locally, rather than spending further turns on attempts that cannot succeed.
- **FR-012**: A push failure that is NOT credential expiry MUST leave today's behaviour unchanged; the narrowed retry applies only to the recognised unrecoverable condition.
- **FR-013**: When an agent stops retrying under FR-011, the reason MUST be visible to a maintainer reading the run and attributed to the credential, not presented as the agent abandoning its task.
- **FR-014**: FR-010 through FR-013 MUST hold even if the FR-002 remedy makes the condition rare, because the remedy's own credential work can fail (FR-006).

#### Nothing the agent committed is lost without a record

- **FR-015**: When an agent step ends with commits it could not push, those commits MUST reach the spec branch before the job ends, on every path the job can take after the agent step — including an agent step that failed, was cut off at its runaway ceiling, or was killed by a step timeout.
- **FR-016**: When a job ends with commits the agent created and no path published them, the run MUST record that unpublished work existed and how many commits it was, in a place the maintainer reads — never a silent completion.
- **FR-017**: The record of FR-016 MUST appear only when there is unpublished work; a cycle that published everything MUST produce no additional output.
- **FR-018**: When the closing lifecycle-record commit is among the commits that could not be pushed at the time the agent made it, the job's deterministic read-back MUST observe the advanced record once FR-015's publication has happened, so the stall path does not report that the branch never advanced.
- **FR-019**: Whether FR-015's guarantee must also hold for a run cancelled at the run level is [NEEDS CLARIFICATION: (a) yes — the publication path runs on cancellation too, accepting that it performs a network mint and a push inside the cancellation window, which spec 052 deliberately declined for its own post-agent refresh; (b) no — a cancelled run is the maintainer's own stop and may end with unpublished commits, provided FR-016's record is still emitted where it can be; (c) no, and the exclusion is recorded in place with spec 052's reasoning cited].

#### Keeping it fixed

- **FR-020**: A deterministic check MUST fail when an agent step in scope does not follow the shipped remedy, naming the workflow, the job, and the step.
- **FR-021**: The check MUST be reachable through the existing gate registry, MUST run the same subject with the same arguments locally as in CI, MUST be triggered by changes to the workflows it inspects, and MUST fail loudly rather than pass when it cannot reach its subject.
- **FR-022**: Every failure branch the check ships MUST be exercised by a checked-in fixture, so no branch is proven only by a live run.
- **FR-023**: The in-place documentation that currently records this exposure as an accepted residual risk — the implement stage's read-back comment and the architecture document's identity section, both of which point at issue #402 — MUST be replaced by a description of the mechanism that actually ships, with one canonical statement and pointers from the other sites.

#### Compatibility and cost

- **FR-024**: An adopting repository MUST require no configuration change to keep working: no new required input, no new required secret, and no change to any existing input, secret, or output name.
- **FR-025**: Stages whose agent steps never push MUST be unaffected — no additional credential work, no additional steps, and no additional prompt text.
- **FR-026**: If the chosen remedy introduces a new way for an agent step to end (for example a clock-based stop), every consumer of the agent step's outcome — the deterministic read-back, the retry gate, the truncated classification, the metrics record, and the stall path — MUST be given an unambiguous name for it, distinct from today's `exhausted` (turn budget ran out) and from a failure.

### Key Entities

- **Agent push credential**: the credential a running agent step's `git push` authenticates with. Established once at job start, valid for one hour, and fixed for the life of the job today. The subject of this feature.
- **Agent step**: the step that invokes the model. Bounded by a turn ceiling rather than a clock, so its wall-clock duration is unbounded — which is what lets it outlive the credential.
- **Stranded commit**: a commit an agent created on the runner that no push has published. Recoverable only while the job still runs.
- **Post-agent recovery**: the step spec 052 ships that re-establishes the credential after an agent step and thereby publishes stranded commits. Today's only backstop, and gated on the agent step having concluded.
- **Expiry signature**: the specific push failure an expired credential produces (`Invalid username or token` / `Authentication failed`), as distinct from every other push failure. What FR-010 must let the agent recognise.
- **Loop-bearing stage**: a stage whose next cycle is re-dispatched automatically (implement, converge). The only stages where a wall-clock bound has a continuation rather than a hard stop.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In seeded runs where an agent step is still pushing after the credential lifetime, 100% of the agent's pushes succeed and zero authentication failures appear in the agent's transcript.
- **SC-002**: Across agent steps that finish inside the credential lifetime, the change produces zero behavioural differences — the same steps run, the same commits land, the same outcome is reported.
- **SC-003**: The number of agent invocations and agent turns for a run that meets no push failure is unchanged by this feature.
- **SC-004**: In a seeded run where a push fails with the expiry signature, the agent makes no more than the stated bound of retry attempts, against the ten further attempts observed in run 35486482556.
- **SC-005**: For every seeded job that ends after an agent step created commits, the spec branch carries 100% of those commits, or the run carries a record naming the unpublished count; the count of silent losses is zero.
- **SC-006**: Across seeded implement jobs whose cycle agent exceeds the credential lifetime and whose retry agent then runs, 100% of the retry agent's pushes succeed.
- **SC-007**: Every agent step in the repository is either covered by the shipped remedy or recorded with a reason for its exclusion; the count of agent steps that are neither is zero.
- **SC-008**: Introducing a non-conforming agent step into a fixture fails the gate suite in 100% of attempts, and the current tree passes.
- **SC-009**: An adopting repository upgrading across this change needs zero configuration edits, and zero published input, secret, or output names change.
- **SC-010**: No live credential outlives the job that established it.

## Assumptions

- The credential's one-hour lifetime is a property of the forge and cannot be extended; the remedy works within it rather than negotiating it away.
- Agent cycles that exceed the credential lifetime are expected and permitted, not a malfunction to be prevented. Two of the three cited runs exceeded it while doing useful work.
- Pushing early and often is already what the agents do — the evidence shows a commit every three to nine minutes — so it is a mitigation already in force and not a remedy on its own. This feature does not rely on additional agent guidance about push cadence.
- Spec 052's post-agent recovery stays in place and keeps working; this feature strengthens the paths it does not cover rather than replacing it.
- The expiry signature is distinguishable from other push failures by its message, as observed verbatim in run 35486482556, so a deterministic rule can recognise it without agent judgment.
- The agent steps in scope are enumerable by inspecting the stage workflows, so the durability check of FR-020 can be deterministic.
- Establishing a credential is cheap relative to an agent cycle, but a remedy that mints per push multiplies mints by the cycle's push count (twelve to eighteen in the observed runs); that volume is assumed acceptable unless the chosen remedy's evaluation finds otherwise.
- This feature does not change the turn ceiling, the intended turn budget, or the iteration cap. If FR-002 resolves to a wall-clock bound, that bound is a new, separate limit, not a redefinition of the existing budgets.
- The two cited runs (35450562414 and 35486482556) are past incidents whose specs have already been recovered; this feature is about preventing recurrence, not about their state.

## Out of Scope

- The steps *around* an agent step, which spec 052 already covers. This feature is the complement of that one: the running agent's own remote, not the post-agent bookkeeping.
- Changing the turn ceiling, the intended turn budget, or the iteration cap that the implement and converge loops already enforce.
- Changing the authentication mechanism itself — the pipeline continues to authenticate as a dedicated application, never a personal token.
- Retrying or resuming an agent cycle that failed for reasons unrelated to credentials.
- Backfilling or re-reporting lifecycle issues whose stall notices were already posted under a "branch never advanced" diagnosis caused by this defect.
- Rewriting the wording of findings, comments, or notices beyond the accuracy requirements in FR-013, FR-016 and FR-018.
- Any new agent-judgment step. FR-010 through FR-013 give the agent a deterministic fact to act on; nothing in this feature asks a model to decide whether a credential expired.
