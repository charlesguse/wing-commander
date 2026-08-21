# Feature Specification: A Transient API Blip No Longer Kills Six Stages at Entry, and the Gate Says What Actually Happened

**Feature Branch**: `039-lifecycle-gate-retry`

**Created**: 2026-08-21

**Status**: Draft

**Input**: User description: "Lifecycle gate: a transient GraphQL 502 kills six stages at entry, reported as a missing issue or missing token scope. The lifecycle gate is the first billable step of six stages. It makes exactly one GitHub API call, and a transient failure of that call kills the stage at entry with an error message that names two causes, neither of which need be true. Found while restarting #184: run 31597186484 died at `Check lifecycle issue state` with `HTTP 502: 502 Bad Gateway (https://api.github.com/graphql)` followed by `##[error]wing-commander-lifecycle-gate: could not determine state of issue #184 — it may not exist, or the token lacks issues: read.` The issue existed and the token was fine. GitHub's GraphQL endpoint had a blip. Two defects on one line in `.github/actions/wing-commander-lifecycle-gate/action.yml`: (1) **No retry.** One attempt. A 502/503/504, a timeout, or a dropped connection is fatal. There is no retry logic anywhere else in the shared composites either — the only loop in the repo (`pr-conversation.yml:1629`) polls for a run URL and is not transient-error handling. (2) **No error classification.** Every non-zero exit produces the same sentence, and that sentence asserts a nonexistent issue or a missing `issues: read` scope. A maintainer reading it goes hunting for a permissions problem that isn't there. Worse, the command substitution captures **stdout only**, so the actual `HTTP 502` on stderr never reaches the error text — it survives only in the raw job log, above the misleading line. Blast radius: the gate is called as the first step of `clarify`, `finalize`, `implement`, `intake`, `pr-conversation`, and `tasks` — before preflight, before checkout, before any agent step (by design, per specs/022 FR-001). For `implement` the consequence is worse than one lost run. The job dies before the `stalled` job's dependencies resolve, so `stalled` is **skipped**: `spec-meta.json` is never marked, and nothing is posted to the lifecycle issue. The chain simply stops. The watchdog's `workflow_run` trigger does catch the red run, so a human hears about it eventually, but nothing restarts and the issue itself says nothing. How often: exactly one occurrence across the last 100 failed runs in this repository. This is rare, and the fix should be sized accordingly — a bounded retry on transient classes, not a general resilience framework. Suggested fix: (1) **Retry only what is retryable.** Capture stderr, and retry on 5xx / timeout / connection-reset with a small bounded backoff (3 attempts is plenty for a blip of this kind). Fail fast on 404, 401 and 403 — retrying a genuinely missing issue or a bad token just delays a correct failure by the length of the backoff. (2) **Say what actually happened.** Quote the captured stderr in the `::error::` line. Keep the 'may not exist / lacks issues: read' wording for the case it describes — a 404 — rather than applying it to everything. (3) Consider whether the same treatment belongs on other single-shot API reads that gate a whole stage; this issue is scoped to the lifecycle gate, which is the one with six callers and no fallback. Testing: `wc_shell_harness.py` already supports running a shipped composite's `run:` block against a stubbed `gh` on PATH — that is how Gate 14 (`verify-stall-restart-runbook.py`, PR #186) drives the stall/guard round trip. A stub that returns `HTTP 502` on the first N invocations and then succeeds would cover the retry path, and one that returns a 404 would prove the fast-fail path is not swallowed by the retry loop. Both are cheap and belong in the same gate. Per #169's lesson, the harness must actually exercise the failure branch — a stub that can only succeed would leave the retry shipped unexecuted, which is exactly the class of gap that issue tracks. Prior art: #186 (the PR from the same incident), #169 (test harnesses modelling dependencies that cannot fail), specs/022-gate-closed-lifecycle (the spec that introduced this gate)."

## Clarifications

### Session 2026-08-21

- Q: How should the gate treat a failure it cannot positively classify — including a read that exits successfully but yields an empty state, and a rate-limit rejection? → A: Retry it. Only a failure positively identified as permanent (issue not found, credential absent/invalid/insufficient) fails immediately; everything else is retried. A classifier that retries only the failure shapes already seen would kill a stage at entry the next time a transient fault is worded differently — which is exactly the incident that produced this issue. The cost of the default is a few seconds of backoff on an unrecognisable permanent failure: a slower correct failure, not a wrong one. The diagnostic blurring this creates is addressed in the failure message, not the policy — an exhausted-retry error states what the attempts actually returned, so "recognised as transient" and "could not classify" are distinguishable in the log even though both took the same path.
- Q: When the gate ultimately fails, must the entering stage still record its outcome and post a notice to the lifecycle issue — so an exhausted retry does not stop the chain silently? → A: Out of scope. This feature changes the gate composite only and does not reach into any calling stage's job graph. The silent chain-stop is real and worth fixing, but rewiring job conditions inside a feature whose subject is a retry loop is the step-gating class that has already taken this pipeline down; it gets its own spec, its own gate, and its own attention. It is filed as a separate issue and linked from #188.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A momentary API blip costs a retry, not a run (Priority: P1)

A maintainer triggers a stage — comments a command, applies a label, merges a PR. At the instant the stage asks the API whether the lifecycle issue is still open, the API returns a server-side error. The stage pauses briefly, asks again, gets its answer, and proceeds exactly as though nothing had happened.

**Why this priority**: This is the defect. The gate is the first billable step of six stages and has no fallback: when its single call fails, the whole stage dies at entry, before preflight, before checkout, before any work. Nothing about that failure was a decision — the question it asks has one true answer, and the answer was momentarily unavailable. Every other story here improves how a failure reads; this one stops the failure.

**Independent Test**: Drive the shipped gate against a stubbed API that fails with a transient server error on its first call and succeeds afterwards, and confirm the gate reports the correct issue state and succeeds — and that a stage entering through it proceeds normally.

**Acceptance Scenarios**:

1. **Given** an open lifecycle issue and an API whose first read fails with a server-side error, **When** the gate runs, **Then** it reports the issue as open, succeeds, and the stage proceeds.
2. **Given** the same conditions but a closed lifecycle issue, **When** the gate runs, **Then** it reports the issue as closed and succeeds — the retry decides nothing about the answer, only about whether an answer was obtained.
3. **Given** an API whose reads fail transiently more times than the retry budget allows, **When** the gate runs, **Then** it fails, and the failure names the transient condition and the number of attempts made.
4. **Given** an API that answers on the first read, **When** the gate runs, **Then** the outcome, the outputs, and the elapsed time are indistinguishable from today's.
5. **Given** an API whose first read times out or drops the connection without returning a status, **When** the gate runs, **Then** that failure is treated as transient and retried.
6. **Given** a first read that fails in a way the gate cannot classify — an unfamiliar fault, a rate-limit rejection, or a call that exits successfully but yields no state — and a second that answers, **When** the gate runs, **Then** the first failure is retried rather than fatal, and the gate reports the correct issue state and succeeds.

---

### User Story 2 - The error says what actually happened (Priority: P1)

A stage fails at the gate. The maintainer who opens the run reads one line that tells them what the API actually said. They know immediately whether to re-run, to check the issue number, or to check the token — instead of being pointed at a permissions problem that may not exist.

**Why this priority**: The misdirection is as costly as the failure. Today every non-zero exit produces the same sentence, that sentence asserts two specific causes, and the real cause — which the API did report — is discarded because only the command's normal output is captured. The maintainer in the source incident went looking for a token scope problem that was not there. A wrong diagnosis printed with confidence is worse than no diagnosis.

**Independent Test**: Drive the shipped gate against stubbed failures of each class in turn and confirm each failure line quotes what the API reported and describes the class that actually occurred.

**Acceptance Scenarios**:

1. **Given** a read that fails with a server-side error, **When** the gate reports the failure, **Then** the reported error contains the diagnostic text the API produced.
2. **Given** a read that fails because the issue does not exist or is not visible, **When** the gate reports the failure, **Then** the failure describes that condition — and this is the only condition for which the "may not exist, or the token lacks read access" wording appears.
3. **Given** a read that fails because the token is missing, invalid, or lacks access, **When** the gate reports the failure, **Then** the failure names the credential as the cause and does not suggest the issue is missing.
4. **Given** a read that fails and is then retried, **When** the gate ultimately fails, **Then** the reported error identifies the last failure observed and states how many attempts were made.
5. **Given** any gate failure, **When** the maintainer reads only the reported error line, **Then** the diagnostic text the API produced is present in that line rather than only elsewhere in the raw log.
6. **Given** reads that fail in a way the gate cannot classify and exhaust the retry budget, **When** the gate reports the failure, **Then** the failure says the attempts could not be classified — not that they were a known transient fault — and quotes what they returned.

---

### User Story 3 - A real failure still fails immediately (Priority: P2)

Someone triggers a stage against an issue number that does not exist, or with a credential that cannot read it. The gate fails at once, with the correct explanation, without spending the retry budget first.

**Why this priority**: Retrying is not free — it costs wall-clock on the first billable step of six stages, and a retry loop that swallows a permanent failure turns a clear, fast error into a slow one. It also destroys the diagnostic value of story 2 by making every failure look like it might have been transient. This is below the two P1 stories only because nothing is currently broken here: today's behaviour already fails fast, and this story is about not regressing it.

**Independent Test**: Drive the shipped gate against a stubbed API that always reports the issue as missing, and confirm exactly one read is attempted; repeat for a credential failure. A test that cannot tell one attempt from several does not satisfy this story.

**Acceptance Scenarios**:

1. **Given** a read that fails because the issue is not found, **When** the gate runs, **Then** exactly one read is attempted and the gate fails immediately.
2. **Given** a read that fails because the credential is rejected, **When** the gate runs, **Then** exactly one read is attempted and the gate fails immediately.
3. **Given** a first read that fails transiently and a second that reports the issue as missing, **When** the gate runs, **Then** it stops at the second read and reports the missing issue, not the transient error.
4. **Given** a successful read that returns a non-empty state value the gate does not recognise, **When** the gate runs, **Then** it fails loudly without retrying — an unrecognised answer is an answer, not an absence of one.
5. **Given** a read that fails for a reason the gate cannot positively identify as permanent, **When** the gate runs, **Then** it is retried rather than failed at once — only the not-found and credential-rejected conditions of scenarios 1 and 2 bypass the budget.

---

### User Story 4 - The retry is proven to run, not merely shipped (Priority: P2)

Both the retry path and the fast-fail path are exercised by executable coverage before merge. Removing the retry, or widening it to swallow permanent failures, fails a check.

**Why this priority**: This defect class is defined by rarity — one occurrence in a hundred failed runs. Code that runs that rarely is code nobody notices is broken, and a retry that has silently stopped retrying looks exactly like a retry that never had to. The repository has already recorded this lesson (#169: harnesses that model dependencies which cannot fail), and it already has the machinery — the shell harness that runs a shipped composite's step against a stubbed command on PATH, and a registry that proves each gate is actually run. This is below the P1 stories because it protects the fix rather than being the fix.

**Independent Test**: Revert the retry and confirm a check fails; separately, make every failure class retryable and confirm a check fails; separately, make an unclassifiable failure fatal instead of retried and confirm a check fails; then confirm all three checks pass on the delivered feature.

**Acceptance Scenarios**:

1. **Given** a stub that fails transiently on its first calls and then succeeds, **When** the coverage runs, **Then** it asserts the gate succeeded with the correct state and that more than one read was attempted.
2. **Given** a stub that always reports the issue as missing, **When** the coverage runs, **Then** it asserts the gate failed after exactly one read.
3. **Given** the retry removed from the shipped gate, **When** the checks run, **Then** a check fails.
4. **Given** the classification removed so that permanent failures are retried, **When** the checks run, **Then** a check fails.
5. **Given** the new coverage disabled, removed, or made unreachable, **When** the repository's checks run, **Then** a check fails — the coverage is wired into the same registry that proves every other gate is run.
6. **Given** the retry narrowed to a list of known failure shapes, so that an unfamiliar or unclassifiable failure is fatal at entry, **When** the checks run, **Then** a check fails — the default that keeps an unseen fault survivable is itself covered.

---

### Edge Cases

- **Every attempt fails transiently.** The gate fails after its bounded budget, naming the transient class, the last observed failure, and the number of attempts. It does not retry indefinitely, and it does not fall through to a guessed state.
- **The failure class changes between attempts** — a transient error followed by a missing issue, or vice versa. Each attempt is classified on its own; the first permanent classification stops the loop and is what gets reported.
- **The read succeeds but returns nothing** (a zero-exit call that produces an empty state). Today this is folded into the same failure as a non-zero exit. It is retried: an absent answer is not positively identified as permanent, so it takes the recoverable path under FR-009.
- **The API rejects the read for rate-limiting reasons** rather than a server fault. Retried like anything else not positively identified as permanent (FR-009). A short bounded backoff may not outlast the limit, in which case the gate fails within its budget and reports what the attempts actually returned, so the rate limit is legible in the failure line.
- **A failure the gate has never seen before** — a transient fault worded differently, a new server-side status, a connection dropped in an unfamiliar shape. Retried, by default. This is the case that produced the source incident, and FR-009 puts it in the recoverable bucket rather than the fatal one.
- **A successful read returns a state value the gate does not recognise.** Unchanged from today: fail loudly, refuse to guess, and do not retry — the retry exists for an absent answer, not an unexpected one. An empty state is the absent case, not this one.
- **The diagnostic text is very long, multi-line, or contains characters that would break the reported error line.** The failure must still be readable as one reported error, so the quoted text is bounded and rendered safely rather than emitted raw.
- **The diagnostic text could contain credential material.** Nothing the gate reports may expose the token it was given.
- **The lifecycle issue is legitimately closed.** Unaffected: a closed issue is a successful read with a "closed" answer, and the calling stage's decline path runs as it does today.
- **The stage that entered through the gate is `implement`.** When the gate fails outright, the run stops before the chain's bookkeeping resolves, so nothing is recorded and nothing is posted to the lifecycle issue. The retry makes this rarer but cannot make it impossible, and this feature does not change it — the silent stop is out of scope and tracked separately (FR-016).
- **Worst-case added latency on the first billable step of six stages.** The budget must be small enough that an exhausted retry is a rounding error against a stage's runtime, not a visible stall.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The lifecycle gate MUST retry its state read when the read fails for a transient reason — a server-side fault, a timeout, or a dropped or reset connection — rather than failing the stage on a single unsuccessful attempt. That list is illustrative, not exhaustive: FR-009 makes retry the treatment for every failure except the permanent conditions of FR-002.
- **FR-002**: The gate MUST NOT retry a failure that identifies a permanent condition — the issue not existing or not being visible, or the credential being absent, invalid, or lacking the access it needs — and MUST fail on the first attempt that reports one.
- **FR-003**: The number of attempts MUST be bounded and small, and the delay between attempts MUST be bounded, such that a fully exhausted retry adds no more than fifteen seconds to the stage's entry.
- **FR-004**: The gate MUST capture the diagnostic output the failed read produces — including output the read sends to its error channel, which today is discarded — and MUST include it in the failure it reports.
- **FR-005**: The failure the gate reports MUST describe the condition that actually occurred. The wording asserting that the issue may not exist or that the credential lacks read access MUST appear only when the read reported that condition.
- **FR-006**: When the retry budget is exhausted, the reported failure MUST state that the read was retried, how many attempts were made, and what the last attempt reported. Because retry is the default for everything not positively identified as permanent (FR-009), the reported failure MUST also make plain whether the retried attempts were recognised as a transient class or merely could not be classified — the distinction the policy no longer draws MUST remain visible in the log.
- **FR-007**: A read that succeeds on a later attempt MUST produce exactly the result a first-attempt success produces — the same state and open/closed outputs, and a successful step. Earlier transient failures MUST be visible in the log as retried attempts, and MUST NOT be reported as an error or annotate the run as failed.
- **FR-008**: The gate's behaviour when the read succeeds with a state value MUST be unchanged, including its refusal to guess on a value it does not recognise; an unrecognised value MUST NOT be retried. This applies to a read that returns a value the gate cannot interpret, which is an answer; a read that returns no state at all is not an answer and is retried under FR-009.
- **FR-009**: Every failure the gate can observe MUST fall into exactly one of the two treatments — retried or failed immediately — with no third, undefined path. Immediate failure MUST be reserved for a failure positively identified as permanent under FR-002; every other unsuccessful read MUST be retried. This retry-by-default explicitly covers failures the read does not classify for itself, rate-limit rejections, and a read that exits successfully but yields an empty state. The default MUST be stated in the gate itself, so a failure class the gate has never seen lands in the recoverable treatment rather than killing the stage at entry.
- **FR-010**: The gate MUST publish its result exactly once regardless of how many attempts were made; a retried read MUST NOT leave duplicate, partial, or conflicting results behind.
- **FR-011**: Executable coverage MUST drive the shipped gate's own step against a stubbed API that fails transiently on its first calls and then succeeds, and MUST assert both that the gate succeeded with the correct state and that more than one read was attempted. The coverage MUST include at least one failure that matches no recognised class, so the retry-by-default of FR-009 is executed rather than only stated.
- **FR-012**: Executable coverage MUST drive the shipped gate's own step against a stubbed API reporting a permanent failure, and MUST assert that exactly one read was attempted — coverage that cannot distinguish one attempt from several does not satisfy this requirement.
- **FR-013**: Reverting the retry, widening it so that permanent failures are retried, or narrowing it so that a failure the gate cannot classify fails immediately, MUST each fail a check. Coverage that can only exercise the success path does not satisfy this requirement.
- **FR-014**: The new coverage MUST be wired into the repository's existing gate registry, so that coverage which stops being run is itself a failure.
- **FR-015**: The gate's declared inputs, outputs, and required access MUST NOT change. No caller may need editing, and no adopter-visible behaviour may change other than a stage surviving a transient failure and the improved failure text.
- **FR-016**: This feature MUST confine itself to the gate composite and MUST NOT alter any calling stage's job graph or job conditions. When the gate ultimately fails, each entering stage behaves exactly as it does today — including `implement`, where the run stops before the chain's bookkeeping resolves, so nothing is recorded and nothing is posted to the lifecycle issue. That silent chain-stop is a real defect, is tracked as its own request, and MUST NOT be addressed here.
- **FR-017**: Nothing the gate reports — including captured diagnostic text — may expose the credential it was given.
- **FR-018**: The reported failure MUST remain a single readable error even when the captured diagnostic text is long, multi-line, or contains characters that would otherwise break it.

### Key Entities

- **Lifecycle gate**: the first billable step of the `clarify`, `finalize`, `implement`, `intake`, `pr-conversation`, and `tasks` stages. It answers one question — is this lifecycle issue currently open? — from a live read, and it has no fallback and no cached alternative.
- **State read**: the single request the gate makes. Its possible outcomes are a recognised answer, an unrecognised answer, a transient failure, and a permanent failure.
- **Failure classification**: the decision, made per attempt, of whether an unsuccessful read is worth asking again. It recognises the two permanent conditions and treats everything else as worth another ask, so the immediate-failure treatment is the narrow case and retry is the default. It is also what makes the reported error specific.
- **Retry budget**: the bounded number of attempts and the bounded delay between them. It is deliberately small — the defect it addresses occurred once in a hundred failed runs.
- **Diagnostic output**: what the failed read reported about itself, including the error channel the gate discards today. It is the evidence that makes a failure diagnosable.
- **Shell harness coverage**: executable coverage that runs a shipped composite's step against a stubbed command supplied on the path, and can make that stub fail on demand. It exists in the repository today and is what proves the retry and fast-fail paths actually run.

## Out of Scope

- **A general resilience framework.** The defect occurred once in the last hundred failed runs. The fix is a small bounded retry on classified transient failures for one composite, not retry infrastructure for the pipeline.
- **Extending retry or classification to other API reads.** The source request explicitly scopes this to the lifecycle gate — the read with six callers and no fallback. Whether other single-shot reads that gate a stage deserve the same treatment is a question this feature raises and does not answer; it belongs in its own request.
- **Changing what the gate decides.** The gate still answers only "is this lifecycle issue open?", still performs no write, and still leaves the decline note on a closed lifecycle to the calling stage.
- **Changing which stages call the gate, or where in a stage it sits.** It remains the first step, before preflight and before any checkout.
- **Automatically restarting a stage that failed at the gate.** Making the failure rarer and legible is this feature's job; resuming from it is not.
- **The silent chain-stop when `implement` dies at the gate.** A stage that cannot enter never resolves the dependencies its bookkeeping job waits on, so `spec-meta.json` goes unmarked and the lifecycle issue hears nothing. Fixing it means changing job conditions in a calling stage — the step-gating class that has already broken this pipeline — and that does not belong inside a feature whose subject is a retry loop. It is filed as its own request and linked from #188.
- **Any change to the watchdog**, which already notices the red run through its own trigger.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A stage entry whose state read fails transiently once, then succeeds, completes the gate and proceeds — where today it fails outright. Recovery is total for any transient failure run shorter than the retry budget.
- **SC-002**: A permanent failure — missing issue, or rejected credential — still fails on the first attempt, adding zero delay compared with today.
- **SC-003**: Every gate failure message contains what the read actually reported; the number of failures reported with a cause that was not observed drops to zero from today's every failure.
- **SC-004**: In the worst case, where every attempt fails transiently, the gate adds no more than fifteen seconds before failing.
- **SC-005**: A run whose first read succeeds — the overwhelmingly common case — behaves identically before and after this feature, with no measurable added time and no change to any output.
- **SC-006**: Reverting the retry fails a check; widening the retry to cover permanent failures fails a check; narrowing it so an unclassifiable failure is fatal fails a check; removing or disabling the new coverage fails a check.
- **SC-007**: A maintainer given only the gate's reported failure line can tell a transient fault, a missing issue, and a credential problem apart without opening the raw log.
- **SC-008**: The change reaches all six stages that call the gate without editing any of them, and without altering the gate's declared inputs, outputs, or required access.
- **SC-009**: A transient failure the gate has never seen before — one whose wording matches no known class — survives to a retry rather than killing the stage at entry, so the count of fatal-at-entry failure classes falls to exactly two: the issue not found and the credential rejected.

## Assumptions

- The read's failures are distinguishable in practice: the underlying API reports server faults, missing resources, and credential problems in text the gate can tell apart, as the source incident's `HTTP 502` line demonstrates. Recognition is only relied on for the two permanent conditions, however; everything else is retried by default under FR-009, so an unfamiliar wording costs a bounded backoff rather than a dead stage.
- Retry-by-default is worth its cost. On a permanent failure the gate cannot recognise, it buys a slower correct failure — bounded by FR-003 — rather than a wrong one, and the two permanent conditions that actually occur in practice still fail fast and specifically. The alternative, retrying only failure shapes already observed, would reproduce the source incident the next time a transient fault is worded differently.
- Three attempts with a short, bounded delay is the right size. The source request states this explicitly and the observed frequency — one occurrence in a hundred failed runs — supports it. The attempt count and delay are fixed constants rather than new inputs, because exposing them would widen the published contract of a composite whose whole virtue is being small.
- A retried read is safe to repeat: it is a read, has no side effect, and asking twice cannot change the answer or leave anything behind.
- The repository's existing shell harness can run this composite's step against a stubbed command that fails on demand, without being restructured — the same mechanism already drives another shipped composite's failure paths.
- The repository's gate registry is the right home for the new coverage; it already proves that each gate is actually run, and this feature joins that arrangement rather than establishing a new one.
- The run environment masks the credential in log output, but the gate must not rely on that alone when it chooses what to quote (FR-017).
- The retry runs where the gate runs — inside its own step, before preflight and before checkout — so it may not depend on anything the stage sets up later.
- Fixing this needs no additional access: the same read is made, only repeated and reported better.
