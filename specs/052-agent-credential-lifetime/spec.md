# Feature Specification: Bot Credential Lifetime Across Long Agent Cycles

**Feature Branch**: `052-agent-credential-lifetime`

**Created**: 2026-09-15

**Status**: Draft

**Input**: User description (lifecycle issue #345): "Every agent stage mints its bot credential once, in the `Wing Commander context` step, before the agent step. That credential lives for one hour. An implement cycle is allowed to run longer than that (the turn ceiling, not the clock, is the only hard stop), and when it does, every credential-bearing step after the agent fails with `HTTP 401: Bad credentials`. Seen on spec 049's first implement cycle, run 34804973881, lifecycle issue #326: context minted at 04:09:21, the cycle ran 04:09:24 → 05:13:17 (64 minutes, 274 of 180 intended turns, verdict healthy), and `Report over-budget agent run (cycle)` failed at 05:13:20 with a 401. Three consequences, each its own defect: (1) the callout is documented in place as 'observability, not failure (FR-017)' but carries no `continue-on-error: true`, so its failure failed the job and stranded `Read back cycle outcome` and everything below it — retry, consolidate, progress comment, stall diagnostics; (2) with no `outcome` output, the stalled job's 'Determine which dependency did not start' step fell through to 'the implement stage failed before it could run its own steps' and marked spec-meta.json stalled, although the agent had run for an hour and pushed seven implement commits (Phases 1–7) — a maintainer reading #326 would conclude nothing ran; (3) every later credential-bearing step has the same exposure: the retry arm (another agent hour under the same credential), `Report exhausted cycle classification`, the progress-comment poster, and `wing-commander-chain-stop-notice`, and the spec-branch checkout authenticates as the bot too, so an agent push after minute 60 is at risk. Any cycle whose ceiling can exceed roughly 55 minutes of wall clock reproduces this. Proposed change (design trade-off; spec-request shape): the owner has to choose where the credential lifetime is re-established, and the answer spans every agent stage (intake, clarify, plan, tasks, implement, finalize, pr-conversation, auto-update's e2e arm) — re-mint after the agent step, mint lazily inside the composites, or bound the agent step by wall clock below the credential lifetime. Independent of that choice, two deterministic fixes belong in the same change: the observability callouts between an agent step and its read-back get `continue-on-error: true`, and the stalled job's 'did not start' diagnosis must read a job output set immediately after the agent step. Found by re-driving spec 049 after its stall."

## Clarifications

### Session 2026-09-15

- Q: Which remedy re-establishes credential validity for the steps after an agent step? → A: Re-establish the bot credential once immediately after each agent step, with every post-agent step reading the refreshed value. Smallest change, no widening of any published composite's declared input surface, and the turn ceiling stays the agent step's only hard bound. This declines both the per-call mint inside each bot-acting composite and the wall-clock ceiling on the agent step. The care points the remedy carries — a value captured from the superseded credential into a file, an environment, or an authenticated remote, and a second agent step in the same job — are what the durability check must pin, so that check ships with the sweep. (FR-001, FR-002, FR-003, FR-020, FR-025)
- Q: How far does the sweep reach in this feature — all agent stages, or only the stage where the defect was observed? → A: All eight agent stages in one sweep (intake, clarify, plan, tasks, implement, finalize, pr-conversation, and the auto-update stage's end-to-end arm). One arrangement applied once and gated once matches the repository's single-home rule, and a durability check that holds on only some stages is not a check. (FR-007, FR-019, SC-005)
- Q: Is the agent's own push credential in scope for this feature? → A: No — out of scope, recorded as a residual risk in place (the implement stage's read-back comment and the architecture documentation), with a follow-up issue filed when this feature's pull request opens. The observed credential errors were all in the steps around the agent; the push case needs an agent still pushing after minute sixty, and fixing it means refreshing an authenticated remote underneath a running agent, which is a different mechanism. Agent guidance to push early and often is a mitigation for that follow-up, not a fix belonging here. (FR-008, Edge Cases, Out of Scope)

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A cycle that outruns the credential still completes its own bookkeeping (Priority: P1)

An implement cycle runs for sixty-four minutes because its turn ceiling, not the clock, is what bounds it. It finishes healthy and pushes its work. Every step after the agent that speaks to the forge as the bot — the over-budget callout, the retry arm's own agent, the exhausted-cycle classification, the progress comment, the stage-label flip, the chain-stop notice — is holding a credential that was minted before the agent started and has since expired. Today all of them fail with a credentials error. What the maintainer needs is for a cycle's length to have no bearing on whether the cycle's reporting, retry, and hand-off work.

**Why this priority**: This is the defect's root. Every other consequence in this feature is downstream of one expired credential, and the exposure grows with the very thing the pipeline is designed to allow — a long, productive agent cycle. It has already cost one spec a full cycle of work, and the two fixes below only limit the blast radius; they do not stop it recurring.

**Independent Test**: Drive an agent stage whose agent step runs past the credential lifetime, and confirm every credential-bearing step after the agent completes normally — no credentials error anywhere in the job, and no step skipped as a consequence of one.

**Acceptance Scenarios**:

1. **Given** an agent stage whose agent step runs longer than the bot credential's lifetime, **When** the steps after the agent act as the bot, **Then** each succeeds, and the job's outcome is what the agent's own result and the deterministic read-back say it is.
2. **Given** the same stage, **When** the agent step finishes well inside the credential lifetime, **Then** behaviour is unchanged from today — same steps, same outcomes, same reported result.
3. **Given** a stage with a retry arm that runs a second agent after the first, **When** the two agents together exceed the credential lifetime, **Then** the steps after the second agent are equally unaffected — the remedy holds for every agent step in the job, not only the first.
4. **Given** an agent stage whose credential cannot be re-established at all (the forge refuses the mint), **When** the steps after the agent run, **Then** the failure is reported as a credential failure naming the step that could not act, never as a silent skip or as an agent-side failure.

---

### User Story 2 - A stall notice never claims a stage that ran did not start (Priority: P1)

The implement job fails somewhere after the agent step. The stalled job takes over, and because the implement job's outputs carry nothing about whether the agent ran, it reports "the implement stage failed before it could run its own steps" and marks the lifecycle record stalled. In fact the agent had run for an hour and pushed seven commits of real work. The maintainer reading the lifecycle issue is told the opposite of what happened, and the natural next action — re-dispatch from scratch — discards or duplicates an hour of completed work.

**Why this priority**: A notice that misreports is worse than no notice: it converts a recoverable partial failure into a maintainer decision made on false evidence. This story is independently valuable — it makes every post-agent failure legible, including failures that have nothing to do with credentials — and it is the only part of this feature a maintainer sees directly.

**Independent Test**: Force a failure in a step after the agent has run to completion, and confirm the stall notice states that the agent ran and names the step that failed afterwards, rather than reporting that the stage never started.

**Acceptance Scenarios**:

1. **Given** an agent stage whose agent step ran to completion and whose job then failed in a later step, **When** the stall notice is composed, **Then** it states that the agent ran and identifies the post-agent step that failed, and does not use the "never started" wording.
2. **Given** an agent stage whose job failed before the agent step was reached, **When** the stall notice is composed, **Then** it reports today's "did not start" diagnosis unchanged, distinguishing a failed prerequisite job from a skipped one exactly as it does now.
3. **Given** an agent stage whose agent step ran and whose job then failed, **When** the lifecycle record is updated, **Then** the record reflects that the cycle produced work, so the restart guidance the notice offers resumes rather than restarts from zero.
4. **Given** a job that was cancelled after the agent ran, **When** the stall path evaluates it, **Then** it is reported as cancelled rather than as either "never started" or a completed cycle.

---

### User Story 3 - An observability callout can never strand the pipeline below it (Priority: P2)

A callout that exists purely to inform — "this cycle used its full intended turn budget" — sits between the agent step and the deterministic read-back that decides what happens next. It is documented in place as observability rather than failure, but nothing enforces that: when it fails for any reason, the job flips to failure and every unguarded step below it is skipped, including the read-back the whole cycle depends on, the retry arm, the consolidation, the progress comment, and the stall diagnostics upload.

**Why this priority**: This is the amplifier — the difference between "one comment did not get posted" and "an hour of agent work was reported as a stall". It is a small, deterministic change with a large reduction in blast radius, and it holds for any future cause of a callout failure, not just an expired credential. It ranks below the two P1 stories because it mitigates rather than removes the fault.

**Independent Test**: Make an observability callout between an agent step and its read-back fail, and confirm the read-back and every step below it still run and the job's reported outcome is decided by the read-back.

**Acceptance Scenarios**:

1. **Given** a step whose in-place documentation declares it observability rather than failure, **When** it fails, **Then** the job continues and every step below it that would have run had the callout succeeded still runs.
2. **Given** the same failed callout, **When** the job's outcome is decided, **Then** the failure is still visible to a reader of the run — tolerated is not hidden.
3. **Given** a step between an agent and its read-back whose failure genuinely should stop the job, **When** it fails, **Then** it still stops the job — the tolerance is granted per declared-observability step, never to the whole region.

---

### User Story 4 - A newly added post-agent step cannot silently reintroduce the exposure (Priority: P2)

Six months from now someone adds a seventh credential-bearing step after an agent step in one of the agent stages, or adds an agent step to a stage that did not have one. Nothing in the repository tells them the credential they are reaching for may have expired, and nothing fails if they get it wrong; the defect returns and is found the next time a cycle runs long.

**Why this priority**: This repository's stated rule is that a consolidation without a gate behind it lasts until the next session, and this exact exposure class already shipped across eight stages unnoticed. A check is what makes the remedy durable rather than a one-time sweep. It is P2 because the pipeline is correct without it — just not durably so.

**Independent Test**: Add, in a fixture, a credential-bearing step after an agent step that does not follow the shipped remedy, and confirm the check fails and names the step; revert it and confirm the check passes.

**Acceptance Scenarios**:

1. **Given** a stage where a credential-bearing step after an agent step does not follow the shipped remedy, **When** the check runs, **Then** it fails and names the workflow, the job, and the step.
2. **Given** every stage as shipped by this feature, **When** the check runs, **Then** it passes.
3. **Given** the check itself, **When** it is run against a tree where it cannot locate the stages it is meant to inspect, **Then** it fails loudly rather than reporting a pass over nothing.
4. **Given** each failure branch the check ships, **When** the gate suite runs, **Then** a checked-in fixture exercises that branch, so no branch is proven only by a live run.

---

### Edge Cases

- **The agent step itself pushes after the credential expires.** The spec-branch checkout authenticates as the bot, so the credential the agent pushes with is the same one that expires at minute sixty. The remedy applies to the steps *after* the agent and leaves the agent's own push exposed; per FR-008 this is a knowingly accepted residual risk, documented in place and carried to a follow-up issue rather than fixed here, because refreshing an authenticated remote underneath a running agent is a different mechanism from the one this feature ships.
- **The re-established credential is not identical to the first.** Anything captured from the original credential — an authenticated remote already configured in the checkout, a value written to a file or an environment for a later step — continues to reference the expired one unless it is refreshed too. FR-001 requires the refresh and FR-020's check pins it.
- **Two agent steps in one job.** Several stages run an agent, read back, and then run a second agent (a retry, an escalation, a progress summariser). A credential re-established once, immediately after the first agent, is stale again after the second.
- **The credential mint fails or is rate-limited.** Re-establishing a credential is a call to the forge and can fail. Whatever the remedy, its own failure must be attributable and must not be mistaken for an agent failure or a stall.
- **A cycle finishes just under the boundary.** A credential minted at minute zero and used at minute fifty-nine works; the same cycle a minute slower does not. The remedy must not have a boundary of its own where a step is issued a credential that expires before it is used.
- **Post-job teardown.** The run's own token revocation reported "Token expired, skipping token revocation". Whatever is minted must still be accounted for at teardown rather than leaking additional live credentials.
- **A stage with no agent step.** Stages that never run an agent cannot exceed the lifetime and must not pay a cost — no extra mints, no extra steps.
- **An adopting repository pinned to an older release.** Adopters pin the published stages by tag; whatever changes must not require an adopter to change anything they have configured in order to keep working.

## Requirements *(mandatory)*

### Functional Requirements

#### The credential outlives the agent

- **FR-001**: Every step in an agent stage that acts as the bot after an agent step MUST use a credential that is valid at the moment that step runs, regardless of how long the agent step ran. This includes steps that act through something derived from the credential — an authenticated remote already configured in the checkout, or a credential value written to a file or an environment for a later step — which MUST be refreshed along with the credential itself rather than continuing to reference the superseded one.
- **FR-002**: The mechanism that establishes credential validity for post-agent steps MUST be a re-establishment of the bot credential immediately after each agent step, with every post-agent step reading the refreshed value rather than the one established before the agent ran. The bot-acting composites MUST NOT be changed to mint their own credential per call, so no composite's declared input surface widens; and the agent step MUST NOT be bounded by wall clock, so the turn ceiling remains its only hard bound.
- **FR-003**: The remedy MUST hold for every agent step in a job, not only the first — a job that runs an agent, then a second agent, then reports, MUST have a valid credential for the steps after each of them.
- **FR-004**: When the credential cannot be established or re-established, the step that needed it MUST fail with a message naming the credential as the cause and the step as the site, and MUST NOT be reported as an agent failure or as a stage that never started.
- **FR-005**: The remedy MUST NOT change behaviour for a job whose agent step finishes well inside the credential lifetime: the same steps run, in the same order, with the same outcomes.
- **FR-006**: The remedy MUST cost no additional agent turns and no additional agent invocations.
- **FR-007**: The remedy MUST apply to every stage that runs an agent step followed by a bot-acting step, and all eight such stages MUST be changed in this one feature as a single sweep: intake, clarify, plan, tasks, implement, finalize, pr-conversation, and the auto-update stage's end-to-end arm. No stage may be deferred to a follow-up, so the durability check of FR-020 ships turned on in the same change.
- **FR-008**: The credential an agent step itself pushes with is OUT OF SCOPE for this feature. The spec-branch checkout authenticates as the bot, so a push made by an agent that is still running after the credential's lifetime remains exposed; that residual risk MUST be recorded in place — at the implement stage's read-back and in the architecture documentation — and a follow-up issue MUST be filed when this feature's pull request opens. The remedy of FR-002 therefore covers the steps around an agent step and not the running agent's own remote.
- **FR-009**: Any credential this feature establishes MUST be accounted for when the job ends, so the change does not leave live credentials behind that the previous single-mint arrangement revoked.

#### A post-agent failure is reported as what it is

- **FR-010**: Each agent stage's job MUST publish, immediately after each agent step, a durable signal recording that the agent step ran and how it concluded, set in a way that survives a later failure in the same job.
- **FR-011**: The stall path MUST read that signal, and when it says the agent ran, MUST report that the agent ran and name the post-agent step that failed — never the "the stage failed before it could run its own steps" wording.
- **FR-012**: When the signal says the agent did not run, the stall path MUST report today's diagnosis unchanged, still distinguishing a failed prerequisite job from a skipped one.
- **FR-013**: When the job was cancelled after the agent ran, the stall path MUST report cancellation rather than either "never started" or a completed cycle.
- **FR-014**: The signal MUST carry no model-authored prose, in keeping with the existing rule that job outputs never carry text a model wrote; prose belongs in the diagnostics the stall path already downloads.
- **FR-015**: When an agent stage's cycle ran and pushed work but the job later failed, the lifecycle record and the restart guidance the stall notice offers MUST reflect that work exists, so the maintainer's next action resumes rather than restarts from zero.

#### The tolerance that limits the blast radius

- **FR-016**: Every step between an agent step and the deterministic read-back that decides the job's outcome whose in-place documentation declares it observability rather than failure MUST be tolerated, so its failure cannot skip the read-back or anything below it.
- **FR-017**: A tolerated failure MUST remain visible to a reader of the run — tolerating a step is not hiding it.
- **FR-018**: Tolerance MUST be granted per declared-observability step and MUST NOT be applied to steps in that region whose failure genuinely should stop the job.
- **FR-019**: The audit that produced the tolerated set MUST be applied to every agent stage, not only the stage where the defect was observed, and MUST be recorded so a reviewer can see which steps were examined and why each was or was not tolerated.

#### Keeping it fixed

- **FR-020**: A deterministic check MUST fail when a bot-acting step after an agent step does not follow the shipped remedy, naming the workflow, the job, and the step. The check MUST pin the two care points the chosen remedy carries: a post-agent step that reads a credential value captured before the agent step, and a second or later agent step in the same job that is not followed by its own re-establishment.
- **FR-021**: The same check MUST fail when a step between an agent and its read-back is declared observability in place but is not tolerated.
- **FR-022**: The check MUST be reachable through the existing gate registry, MUST run the same subject with the same arguments locally as in CI, MUST be triggered by changes to the workflows it inspects, and MUST fail loudly rather than pass when it cannot reach its subject.
- **FR-023**: Every failure branch the check ships MUST be exercised by a checked-in fixture.
- **FR-024**: The in-place comments that document the credential arrangement and the observability callouts MUST be corrected to describe the mechanism that actually ships, with one canonical statement and pointers from the other sites, following this repository's single-home rule.

#### Compatibility

- **FR-025**: An adopting repository MUST require no configuration change to keep working: no new required input, no new required secret, and no change to any existing input, secret, or output name. The remedy of FR-002 leaves every published composite's declared surface as it is, so this requirement is unconditional for this feature rather than contingent on the remedy.
- **FR-026**: Stages that run no agent step MUST be unaffected — no additional credential mints and no additional steps.

### Key Entities

- **Bot credential**: the short-lived installation credential every agent stage acts under. Has a fixed lifetime measured from when it is established, which is shorter than a long agent cycle. The subject of this feature.
- **Agent step**: the step in a stage that invokes the model. Bounded by a turn ceiling rather than a clock, so its duration is unbounded in wall-clock terms.
- **Post-agent bot-acting step**: any step after an agent step that speaks to the forge as the bot — callouts, comment posters, label flips, checkouts, chain-stop notices, dispatches. The population this feature must make safe.
- **Agent-ran signal**: the durable, prose-free record that an agent step ran and how it concluded, published by the job and consumed by the stall path. Distinguishes "the stage never started" from "the stage ran and something after it failed".
- **Declared-observability step**: a step whose in-place documentation states it informs rather than gates. FR-016 makes that declaration enforced rather than aspirational.
- **Stall notice**: the lifecycle-issue message a maintainer reads when a stage does not complete. Its accuracy is the user-visible outcome of this feature.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An agent stage whose agent step runs past the credential lifetime completes every post-agent step successfully in 100% of seeded cases, with zero credential errors in the run log.
- **SC-002**: Across agent stage runs whose agent finishes inside the credential lifetime, the change produces zero behavioural differences — same steps run, same outcomes reported.
- **SC-003**: For every seeded post-agent failure where the agent ran to completion, the message a maintainer reads names the step that failed and states that the agent ran; the "never started" wording appears in zero of those cases.
- **SC-004**: A seeded failure of any declared-observability step between an agent and its read-back leaves 100% of the steps below it running, and the job's reported outcome is the one the read-back computed.
- **SC-005**: All eight agent stages are covered by the shipped remedy in this feature, with zero stages deferred to a follow-up and zero stages neither covered nor recorded with a reason.
- **SC-006**: Introducing a non-conforming post-agent bot-acting step into a fixture fails the gate suite in 100% of attempts, and the current tree passes.
- **SC-007**: The number of agent invocations and agent turns per stage run is unchanged by this feature.
- **SC-008**: An adopting repository upgrading across this change needs zero configuration edits, and zero published input, secret, or output names change.
- **SC-009**: No live credential outlives the job that established it.

## Assumptions

- The bot credential's one-hour lifetime is a property of the forge and cannot be extended; the remedy works within it rather than negotiating it away.
- Agent cycles exceeding the credential lifetime are expected and permitted, not a malfunction to be prevented — the turn ceiling is the intended bound. The remedy chosen in FR-002 preserves this: no wall-clock ceiling is introduced, so "exhausted" continues to mean the turn budget ran out.
- The observed failure mode is the credential expiring, not any per-call rate limiting; a rate-limited call presents differently and is already handled elsewhere in the pipeline.
- The stall path already downloads a diagnostics artifact from the failed job, so a prose-free signal plus the existing artifact is enough to compose an accurate notice without adding a new transport.
- The steps this feature must make safe are enumerable by inspecting the stage workflows, so the durability check of FR-020 can be deterministic and needs no agent judgment.
- Establishing a credential is cheap and fast relative to an agent cycle, so the cost of doing it once more per agent step is not a reason to avoid the chosen remedy.
- Recovery for the spec that surfaced this (049) was already performed by re-dispatch on 2026-09-15; this feature is about preventing recurrence, not about that spec's state.
- The three consequences in the source issue are independent: the tolerance fix and the accurate-stall-notice fix are worth shipping on their own merits and remain correct alongside the re-establishment remedy of FR-002.

## Out of Scope

- Changing the turn ceiling, the iteration cap, or any budget the implement loop already enforces; no wall-clock bound is placed on an agent step.
- The credential a running agent step pushes with (FR-008): documented in place as a residual risk and carried to a follow-up issue filed when this feature's pull request opens. Agent guidance about pushing early and often is a mitigation for that risk and belongs to that follow-up, not here.
- Retrying or resuming an agent cycle that failed for reasons unrelated to credentials.
- Any change to how findings, comments, or notices are worded beyond the accuracy requirements in FR-011 through FR-013.
- Changing the authentication mechanism itself — the pipeline continues to authenticate as a dedicated application, never a personal token.
- Backfilling or re-reporting lifecycle issues whose stall notices were already posted under the incorrect diagnosis.
- Any new agent-facing surface, prompt, or judgment step; every part of this feature is deterministic.
