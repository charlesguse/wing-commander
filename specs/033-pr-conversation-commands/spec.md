# Feature Specification: Maintainer Commands and Spec Kit Routing Through PR Conversation

**Feature Branch**: `033-pr-conversation-commands`

**Created**: 2026-08-09

**Status**: Draft

**Input**: User description: "Wing Commander should respond to comments and reviews on implementation PRs. A maintainer's review or change request should be taken, run through converge, and start an implement/converge loop again; or ask for more information; or push back on why something doesn't fit (a constitution violation). If a request doesn't fit the PR's work but still makes sense, either fold it into the currently-implementing spec (via Spec Kit), or — if it should be its own spec — create an issue for it; or, if it's a very small unrelated code/document change, create a separate PR pointed at main and call it out in both the current PR and the current issue. If a maintainer asks for a manual step, either do it or explain why not — e.g. a needed permission becomes a one-off PR requesting it, unless there has already been a conversation on why that permission is withheld, in which case link that conversation. Implementation-detail conversation stays in the PR; anything larger than the PR is referenced in both the PR and its tied lifecycle issue. Anything done outside the PR (a new spec issue, an unrelated tiny PR) is recorded on the issue as an outstanding task item so it can't be ignored."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - In-scope review feedback re-drives the implement/converge loop (Priority: P1)

A maintainer is reviewing an implementation PR produced by the pipeline. They leave a review (or a comment) asking for a change that belongs to the work the PR is already doing — a bug in the new code, a missing test, a naming tweak from code review. Instead of a human maintainer having to translate that feedback into pipeline action, Wing Commander reads the review, folds it into the convergence step for that spec, and restarts the implement ⟲ converge loop. When the loop settles, the updated result is pushed to the same PR and the outcome is reported on the PR thread.

**Why this priority**: This is the headline value and the most common case. The maintainer's own words state the goal: "take the review results, put them through converge and start an implement/converge loop again," so that the least possible burden falls on human maintainers. A single change-request that automatically re-drives the existing loop delivers a working, demonstrable slice on its own, so it is P1.

**Independent Test**: Open an implementation PR for a spec, leave a review requesting an in-scope change (e.g. "this function is missing a null check"), and confirm the pipeline folds the request into converge, runs another implement/converge iteration, updates the same PR, and posts a status reply on the PR — with no manual maintainer step in between.

**Acceptance Scenarios**:

1. **Given** an open implementation PR for an in-flight spec, **When** a maintainer requests an in-scope change via a review or comment, **Then** the request is folded into that spec's converge input and a new implement/converge iteration runs against the PR's branch.
2. **Given** a re-triggered implement/converge loop that settles, **When** the loop completes, **Then** the updated code is pushed to the existing PR and a status reply is posted on the PR thread.
3. **Given** an in-scope change request, **When** it is processed, **Then** the conversation and its resolution stay on the PR and are not duplicated onto the lifecycle issue.

---

### User Story 2 - Out-of-scope-but-valid requests are routed and never lost (Priority: P1)

While reviewing an implementation PR, a maintainer raises something that does not belong to the PR's current work but is still worth doing. The stage classifies it and routes it to the right home rather than silently dropping it or forcing it awkwardly into the current change:

- **New functionality**: the stage uses Spec Kit to judge whether the request extends the spec currently being implemented — in which case it is folded into that spec — or is large/distinct enough to warrant its own spec, in which case a new lifecycle issue is created for it.
- **Small, unrelated code or documentation change**: the stage opens a separate PR targeting `main`, independent of the current work, and calls it out in both the current PR and the current lifecycle issue. A separate PR is considered only for a very small code or document change.

Anything created outside the current PR is recorded on the lifecycle issue as an outstanding task item so it cannot be ignored.

**Why this priority**: This is the second core behavior in the request and the one that prevents good ideas from being lost or from derailing the current PR. The worked example in the issue — reviewing PR Y and noticing an unrelated docs change, versus asking for new functionality — is exactly this routing. It is independently demonstrable and central to the feature, so it is P1.

**Independent Test**: On an implementation PR, (a) leave a comment describing a completely unrelated one-line docs fix and confirm a separate PR to `main` is opened and referenced from both the PR and the issue; and (b) leave a comment requesting new functionality and confirm the stage decides between folding it into the current spec and creating a new spec issue, with the outcome recorded on the lifecycle issue.

**Acceptance Scenarios**:

1. **Given** a review comment describing new functionality, **When** the stage evaluates it with Spec Kit, **Then** it either folds the request into the currently-implementing spec or creates a new lifecycle issue for a separate spec, and records which it chose.
2. **Given** a review comment describing a very small unrelated code or documentation change, **When** the stage acts, **Then** it opens a separate PR targeting `main` and links that PR from both the current PR and the current lifecycle issue.
3. **Given** any artifact created outside the current PR (a new spec issue or a spin-off PR), **When** it is created, **Then** it appears on the lifecycle issue as an outstanding task item.
4. **Given** an unrelated change that is not "very small," **When** the stage evaluates it, **Then** it does NOT open a separate PR and instead routes it to a spec/issue.

---

### User Story 3 - The stage asks for more information or pushes back when a request doesn't fit (Priority: P2)

Not every request can or should be acted on. When a maintainer's comment is ambiguous, the stage asks for the missing information rather than guessing. When a request conflicts with the project's constitution or otherwise does not belong in the PR, the stage pushes back with a clear explanation of why, rather than complying. Implementation-detail discussion stays on the PR thread.

**Why this priority**: This is what keeps the automation trustworthy — it prevents the stage from acting on a misread request or from quietly violating a governing principle. It is essential but secondary to actually routing valid work (US1, US2), so it is P2.

**Independent Test**: Leave a comment that would require a constitution violation (e.g. asking the bot to merge its own PR to `main`) and confirm the stage declines with a reasoned explanation; separately, leave an ambiguous request and confirm the stage asks a clarifying question instead of acting.

**Acceptance Scenarios**:

1. **Given** a request that would violate a constitution principle, **When** the stage evaluates it, **Then** it declines and replies on the PR explaining which principle it conflicts with.
2. **Given** an ambiguous or underspecified request, **When** the stage cannot determine a safe action, **Then** it asks a clarifying question on the PR rather than guessing.
3. **Given** a comment that is ordinary implementation-detail discussion (not an actionable command), **When** the stage evaluates it, **Then** the discussion remains on the PR and no cross-referencing to the issue occurs.

---

### User Story 4 - Manual steps and permission requests are handled or explained (Priority: P2)

A maintainer asks the stage to perform a manual step that remains outstanding on the work — running a command, making a tweak, completing a hand-off. The stage either performs it or explains why it cannot. A recurring special case is a missing capability: when the stage needs a permission it does not have, it opens a one-off PR requesting that permission — unless there has already been a recorded conversation explaining why that permission is deliberately withheld, in which case the stage links that conversation instead of re-requesting it.

**Why this priority**: This addresses the maintainer's goal of putting "as minimal on the human maintainers as possible" for the residual manual steps. It is valuable but narrower than the review-loop and routing behaviors, and depends on the same conversation surface, so it is P2.

**Independent Test**: Ask the stage to perform a manual step it can do and confirm it does it and reports back; ask it to do something requiring a permission it lacks and confirm it opens a one-off permission-request PR — then repeat when a prior "we don't grant this" conversation exists and confirm it links that conversation instead.

**Acceptance Scenarios**:

1. **Given** a maintainer request for a manual step the stage is able to perform, **When** it processes the request, **Then** it performs the step and reports the outcome on the PR.
2. **Given** a manual step the stage cannot perform, **When** it processes the request, **Then** it explains on the PR why it cannot rather than failing silently.
3. **Given** a request that requires a permission the stage lacks and no prior discussion of that permission exists, **When** it processes the request, **Then** it opens a one-off PR requesting the needed permission.
4. **Given** a request for a permission that has already been discussed and deliberately withheld, **When** the stage processes it, **Then** it links the prior conversation instead of opening another permission-request PR.

---

### User Story 5 - Intent is announced before anything changes, and a run can be stopped (Priority: P2)

The stage acts on its own by default, so a maintainer must be able to see what it is about to do and to stop it while it is still working. Before mutating anything, the stage posts the classification it assigned, the action it is about to take, and a link to the run. If the maintainer decides the stage read the request wrong, they can cancel the run directly or simply reply asking it to stop, and the stage abandons the remaining work. If the work already finished before the stop landed, the stage says what it already did so the maintainer can undo it.

**Why this priority**: Acting immediately is what keeps maintainer burden low, but only an announced, interruptible action is safe to run unattended — the announcement is what makes the default autonomy acceptable. It guards every other story's actions rather than producing routing behavior of its own, so it is P2.

**Independent Test**: Leave a comment that the stage will classify as an out-of-PR spin-off, confirm an intent announcement (classification, planned action, run link) appears on the PR before any artifact exists, then reply asking it to stop and confirm no artifact is created and the stop is acknowledged.

**Acceptance Scenarios**:

1. **Given** an actionable request, **When** the stage decides on an action, **Then** it announces the classification, the intended action, and a link to the run on the PR before performing any mutating step.
2. **Given** an announced action that has not completed, **When** an authorized maintainer replies asking the stage to stop (or cancels the run), **Then** the remaining work is abandoned and no further artifacts are created.
3. **Given** an announced action that has already completed, **When** a stop request arrives afterwards, **Then** the stage reports what was already done rather than claiming it stopped in time.
4. **Given** a repository that has configured propose-and-confirm for out-of-PR artifacts, **When** the stage classifies a request as a spin-off, **Then** it posts the proposal and waits for maintainer confirmation before creating anything, while in-PR actions still run immediately.

---

### User Story 6 - Questions about the code or the state of the work get answered (Priority: P3)

A maintainer reviewing the PR asks a question rather than requesting a change — how a piece of the new code behaves, why an approach was taken, or where the spec's work currently stands. The stage answers on the PR thread and changes nothing: no code push, no new issue, no spin-off PR.

**Why this priority**: Answering questions makes the PR conversation a usable working surface instead of a command-only channel, but no work is blocked without it and it creates no artifacts, so it is the lowest priority.

**Independent Test**: Ask a question about the new code or the state of the spec on an implementation PR and confirm the stage replies with an answer while the branch, the lifecycle issue, and the repository are left untouched.

**Acceptance Scenarios**:

1. **Given** a comment that asks a question about the code, the PR, or the state of the work, **When** the stage evaluates it, **Then** it replies with an answer on the PR and takes no mutating action.
2. **Given** a comment that mixes a question with an actionable change request, **When** the stage evaluates it, **Then** it answers the question and routes the request by its own classification.
3. **Given** a question the stage cannot answer confidently, **When** it replies, **Then** it says so rather than guessing.

---

### User Story 7 - Everything larger than the PR is traceable from the lifecycle issue (Priority: P3)

The lifecycle issue remains the single legible record of a spec's life. Any outcome of a PR conversation that is bigger than the PR itself — a new spec issue, a spin-off PR, a withheld-permission decision — is referenced from both the PR and its tied lifecycle issue and recorded on the issue as an outstanding task item, so nothing spun off during review can be forgotten. Purely PR-scoped discussion is not copied to the issue.

**Why this priority**: This is the traceability guarantee that ties the other stories together. It hardens the feature against lost work but does not itself produce new routing behavior, so it is the lowest priority of the set.

**Independent Test**: Drive US2 and US4 outcomes, then inspect the lifecycle issue and confirm each out-of-PR artifact appears as an outstanding task item cross-linked to the PR, while an in-scope US1 conversation leaves no trace on the issue.

**Acceptance Scenarios**:

1. **Given** any artifact created outside the PR during a conversation, **When** it is created, **Then** it is referenced from both the PR and the lifecycle issue.
2. **Given** an out-of-PR artifact, **When** it is recorded on the issue, **Then** it appears as an outstanding task item rather than a passing mention.
3. **Given** a PR-only implementation-detail exchange, **When** it resolves, **Then** the lifecycle issue is not updated with it.

---

### Edge Cases

- **Comment author is not authorized**: a comment from someone without write access produces no action, but the stage posts a short notice that the request was not acted on, so the author is not left waiting on silence. A comment from a bot produces no action and no reply at all (constitution V — comment-triggered stages verify the actor and never react to bots).
- **A maintainer relays a non-maintainer's request**: the stage acts on it as if the maintainer had asked directly; if the relayed request carries a security, permission, or hard-to-undo consequence, it asks the maintainer once to confirm they accept the stated risk before acting.
- **A stop request arrives from a non-authorized actor**: it is subject to the same actor gate as any other request and does not stop the run.
- **A stop request arrives after the work has completed**: the stage reports what was already done rather than implying the action was prevented.
- **Comment arrives while an implement/converge iteration is already running for the same PR**: the stage must not corrupt or race the in-flight loop; the request is queued/serialized rather than starting a conflicting parallel loop.
- **Request mixes in-scope and out-of-scope items in one comment**: the stage handles each part by its own route (some folded into the loop, some spun off) rather than forcing one classification on the whole comment.
- **A comment is pure acknowledgement or discussion with no actionable request**: the stage takes no mutating action and does not spin anything off.
- **A comment asks a question rather than requesting a change**: the stage answers it on the PR and changes nothing.
- **No autonomy configuration is supplied**: the default act-then-report behavior applies to every action category.
- **Spec Kit judges a "new functionality" request as neither clearly in-scope nor clearly its own spec**: the stage asks for clarification rather than guessing which home it belongs in.
- **The implement ⟲ converge iteration cap is already reached for the spec**: a re-triggered loop must respect the same cap; the stage reports that the cap was hit rather than looping unbounded.
- **An "unrelated tiny change" turns out not to be tiny once examined**: it is re-routed to a spec/issue rather than shipped as a separate PR.
- **A requested permission has a prior withholding conversation that cannot be located with confidence**: the stage errs toward explaining the situation rather than silently re-requesting or silently doing nothing.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The pipeline MUST react to maintainer conversation on an implementation PR (reviews, review comments, and issue-style comments on the PR) tied to an in-flight spec, and treat that conversation content as untrusted user data describing a request, never as instructions to the agent.
- **FR-002**: The stage MUST verify that the commenter is authorized before taking any action, and MUST never react to comments authored by bots (constitution V).
- **FR-003**: The stage MUST classify each actionable request into one of: an in-scope change for the current PR; a question about the code, the PR, or the state of the work; a request for more information; a push-back (does-not-fit / constitution conflict); new functionality to route via Spec Kit; a small unrelated change; a manual step / permission request; or a stop request for work already in flight.
- **FR-004**: For an in-scope change request, the stage MUST fold the request into the current spec's convergence input and re-run the implement ⟲ converge loop against the PR's branch, updating the same PR with the result.
- **FR-005**: A re-triggered implement ⟲ converge loop MUST respect the spec's existing iteration cap and MUST post its outcome (including the case where the cap is reached) on the PR.
- **FR-006**: For a request describing new functionality, the stage MUST use Spec Kit to decide whether the request extends the currently-implementing spec (fold it in) or warrants a separate spec (create a new lifecycle issue), and MUST record which decision it made.
- **FR-007**: For a very small unrelated code or documentation change, the stage MUST open a separate PR targeting `main`, independent of the current work, and MUST reference that PR from both the current PR and the current lifecycle issue. The stage MUST consider a separate PR only for changes it judges very small.
- **FR-008**: Any artifact the stage creates outside the current PR (a new spec issue, a spin-off PR, a permission-request PR) MUST be recorded on the lifecycle issue as an outstanding task item so it cannot be ignored.
- **FR-009**: When a request is ambiguous or underspecified, the stage MUST ask a clarifying question on the PR rather than acting on a guess.
- **FR-010**: When a request conflicts with a constitution principle or otherwise does not belong in the PR, the stage MUST decline and reply on the PR with the reason, and MUST NOT perform the conflicting action (including never merging or approving a PR to `main`).
- **FR-011**: When a maintainer requests a manual step, the stage MUST either perform it and report the outcome, or explain on the PR why it cannot.
- **FR-012**: When acting on a request requires a capability (permission) the stage lacks, the stage MUST open a one-off PR requesting that permission, UNLESS a prior recorded conversation already explains why that permission is withheld, in which case the stage MUST link that conversation instead of opening another request.
- **FR-013**: Implementation-detail discussion MUST remain on the PR thread and MUST NOT be copied to the lifecycle issue; anything larger than the PR MUST be referenced in both the PR and its tied lifecycle issue.
- **FR-014**: The stage MUST post a reply on the PR describing the action it took (or declined to take) for each actionable request, so the maintainer sees a response to their comment.
- **FR-015**: The stage MUST NOT start a conflicting parallel implement/converge loop for a PR that already has an iteration in flight; concurrent requests for the same spec MUST serialize.
- **FR-016**: The stage's model and turn budget MUST be explicitly declared and bounded, consistent with the project's cost-conscious tiering (constitution II), and web tools MUST be disabled for this comment-driven stage (constitution V).
- **FR-017**: A comment that carries no actionable request (pure acknowledgement or discussion) MUST result in no mutating action and no spin-off artifacts.
- **FR-018**: The stage MUST respond only to conversation on **implementation PRs** tied to an in-flight spec, and on such a PR it MUST accept requests from all three GitHub conversation surfaces: issue-style PR comments, formal PR review bodies, and inline review-thread comments. Conversation on spec-draft and plan PRs MUST NOT trigger this stage; that feedback continues to flow through the existing clarify path.
- **FR-019**: The stage MUST act only on requests from an authorized maintainer — an actor with write access to the repository (OWNER, MEMBER, or COLLABORATOR association) — and MUST never act on a comment authored by a bot. A non-maintainer, including the original requester of the lifecycle issue, cannot command the stage directly.
- **FR-020**: The stage's autonomy MUST be configurable. The default MUST be act-then-report: having announced its intent (FR-023), the stage executes the routing action and posts what it did. The configuration MUST allow a consuming repository to require propose-and-confirm for individual action categories — for example confirming before creating out-of-PR artifacts (new spec issues, spin-off PRs, permission-request PRs) while still acting immediately on in-PR actions — or for every category. When no autonomy configuration is supplied, the default applies. Autonomy configuration MUST come from trusted pipeline configuration and MUST NOT be settable from PR conversation content, though a maintainer may still ask the stage to confirm before acting on one specific request.
- **FR-021**: When an actionable request comes from an actor the stage is not authorized to obey, the stage MUST post a brief notice on the PR that the request was not acted on and who can authorize it, rather than ignoring it silently. Comments authored by bots MUST be ignored with no reply at all.
- **FR-022**: An authorized maintainer MUST be able to relay a non-maintainer's request (for example, "they aren't a maintainer, but please do what they asked"); the stage MUST then treat that request as if the maintainer had made it themselves. When a relayed request carries risk — a security, permission, or otherwise hard-to-undo consequence — the stage MUST state the risk and ask the relaying maintainer once more to confirm they accept it, and MUST NOT act until that confirmation arrives.
- **FR-023**: Before performing any mutating action, the stage MUST announce its intent on the PR — the classification it assigned, the action it is about to take, and a link to the run — so a maintainer can cancel the run or object before the action completes.
- **FR-024**: The stage MUST honor a stop request from an authorized maintainer: a follow-up comment asking it to stop, or cancellation of the announced run, MUST abandon the remaining work for that request rather than completing it. When the work has already completed by the time the stop request is seen, the stage MUST report what was already done so the maintainer can undo it.
- **FR-025**: The stage MUST recognize a comment that asks a question about the code, the PR, or the state of the work rather than requesting a change, and MUST answer it on the PR thread without making any code change or spin-off artifact. A comment that mixes a question with an actionable request MUST have each part handled by its own route (FR-003).

### Key Entities *(include if feature involves data)*

- **PR conversation event**: a maintainer review body, inline review-thread comment, or issue-style PR comment on an implementation PR tied to an in-flight spec; the untrusted request content the stage acts on.
- **Request classification**: the category assigned to an actionable request (in-scope change, question, needs-info, push-back, new-functionality, small-unrelated-change, manual-step/permission, stop) that determines its route.
- **Intent announcement**: the reply the stage posts before mutating anything — the classification, the action it is about to take, and a link to the run — which is also what makes the run cancellable.
- **Stop request**: an authorized maintainer's follow-up comment (or run cancellation) asking the stage to abandon an announced action before it completes.
- **Autonomy configuration**: trusted, consumer-supplied configuration selecting act-then-report (the default) or propose-and-confirm per action category; never derived from PR conversation content.
- **Relayed request**: a non-maintainer's request that an authorized maintainer endorses on their behalf, carrying the maintainer's authority — and, when risky, an explicit risk confirmation from that maintainer.
- **Lifecycle issue**: the originating issue for a spec; the single legible record where out-of-PR artifacts are cross-linked as outstanding task items.
- **Current spec**: the spec being implemented by the PR under review, identified from the PR's branch/labels; the target when a request is folded in.
- **Spin-off artifact**: anything created outside the current PR as a result of a conversation — a new spec lifecycle issue, a separate small-change PR to `main`, or a permission-request PR.
- **Outstanding task item**: the record on the lifecycle issue that pins a spin-off artifact so it is not forgotten.
- **Withheld-permission conversation**: a prior recorded discussion explaining why a given permission is not granted to the agent; linked instead of re-requesting.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For in-scope change requests on an implementation PR, a maintainer no longer performs any manual translation step — 100% of such requests re-drive the implement/converge loop and update the same PR without a human intermediary.
- **SC-002**: Every out-of-PR artifact created during a conversation (new spec issue, spin-off PR, permission-request PR) is cross-referenced from both the PR and the lifecycle issue and appears as an outstanding task item — zero spun-off items are left untracked.
- **SC-003**: The stage never performs an action that a constitution principle forbids (e.g. merging/approving to `main`); 100% of such requests are declined with a stated reason.
- **SC-004**: Unrelated changes shipped as a separate PR are limited to very small code/document changes; no large or non-tiny change is shipped as a spin-off PR instead of being routed to a spec/issue.
- **SC-005**: Every actionable maintainer comment receives a reply on the PR stating the action taken or the reason for declining — no actionable comment goes unanswered.
- **SC-006**: No comment from a bot or unauthorized actor triggers a mutating pipeline action — 100% of such triggers are ignored; the only response to a non-bot unauthorized request is a notice that it was not acted on, and a bot comment draws no response at all.
- **SC-007**: The volume of manual maintainer follow-up needed to act on PR review feedback measurably drops relative to today's fully-manual handling (the maintainer's stated goal of minimizing human load).
- **SC-008**: 100% of mutating actions are announced on the PR — with classification, planned action, and run link — before the mutation occurs, so no action is discoverable only after the fact.
- **SC-009**: A stop request from an authorized maintainer prevents the announced action whenever it arrives before the action completes; when it arrives later, the maintainer is told what was already done — no stop request is silently dropped.
- **SC-010**: Questions asked on the PR are answered without any code change, issue, or spin-off PR being produced.

## Assumptions

- **Comment-driven stage precedent**: this behavior follows the existing comment-triggered stage pattern in the pipeline (e.g. the clarify stage that folds lifecycle-issue replies into a draft spec), including its framing of comment bodies as untrusted user data. Its actor gate is deliberately tighter than the clarify stage's: because these commands mutate code and create artifacts, the original requester does not qualify on their own (FR-019). The trigger/actor gate lives in the thin wrapper workflow, not in the reusable stage (constitution VII).
- **Spec Kit is the routing brain for new functionality**: deciding "fold into current spec" versus "own spec" reuses Spec Kit rather than a bespoke heuristic, consistent with how the pipeline already turns requests into specs.
- **Iteration cap is shared**: a re-triggered implement ⟲ converge loop uses the same capped loop the pipeline already runs; this feature does not introduce a new, separate loop with its own cap.
- **The bot never merges to `main`**: spin-off PRs and permission-request PRs target `main` for a human to review and merge; the agent opens them but never approves or merges them (constitution V).
- **Least-privilege, no web tools**: as a comment-driven stage, it runs with the minimal tool allowlist it needs and with web tools disabled (constitution V), on an explicitly declared, turn-bounded model (constitution II).
- **"Very small" is an agent judgment with a conservative bias**: absent a precise size threshold, the stage treats the separate-PR route as the exception for genuinely tiny, unrelated changes and defaults larger or entangled changes to the spec/issue route.
- **Only trusted refs are checked out**: the stage operates on the pipeline's own branches for the spec under review, never on fork PR heads (constitution V).
- **Write access is the maintainer signal**: "authorized maintainer" is read from the commenter's repository association (OWNER/MEMBER/COLLABORATOR), the same signal existing comment-driven stages already use; this feature does not introduce a separate maintainer roster.
- **Cancellation uses what GitHub already offers**: a maintainer can stop an announced action either by cancelling the workflow run linked in the announcement or by replying with a stop request; this feature does not introduce a bespoke cancellation surface.
- **Autonomy configuration follows existing per-stage configuration**: the act-then-report/propose-and-confirm setting is supplied the way the pipeline's other consumer-tunable stage settings are, and its exact shape is a planning concern; the spec fixes only the default and the requirement that it be overridable per action category.
- **"Risk" in a relayed request is an agent judgment with a conservative bias**: security, permission, and hard-to-undo consequences trigger the extra confirmation round; ordinary in-scope code changes do not.
