# Feature Specification: Stage-Found Defect Filing Through a Deterministic Filing Step

**Feature Branch**: `056-stage-found-defect-filing`

**Created**: 2026-09-20

**Status**: Draft

**Input**: Lifecycle issue [#412](https://github.com/charlesguse/wing-commander/issues/412) — "stages: file the bugs they meet during their own work through a deterministic filing step (the board loop's feed)"

## Context

Every agent stage meets defects that are not its own work. An implement
cycle notices a gate that cannot fail its subject. A plan run reads a
contract that contradicts the workflow it describes. A clarify run spots a
stale count in prose. Today that knowledge dies with the run: each stage's
prompt tells the agent to stay in scope, no stage has a route for filing
what it saw, and `implement.yml` has no `gh issue create` path at all.

The pipeline does file issues — but every existing route is a route for
that feature's own failure, never for "I saw something wrong on the way":

- the watchdog's `pipeline-defect`,
- stage 10's `spec-request` and `permission-request` spin-offs,
- auto-update's `auto-update:*`,
- auto-release's `auto-release:failed`.

So the owner files these by hand from local sessions — #397, #402, #410 and
#411 are all that shape — and the board loop (#408) has nothing to pick up
unless a person types. This feature gives the stages a mouth and the board
loop a feed.

The shape is fixed by Constitution Principle IX: **the agent proposes, code
files.** The agent describes what it saw; deterministic code decides whether
that description is well-formed enough, novel enough, and safe enough to
become an issue. The agent never runs `gh issue create`. This is the same
discipline as the watchdog's `__new__` finding-class escape hatch, where the
model proposes a name and a deterministic step resolves and registers it.

This is also observability, not function. A stage exists to specify, plan,
implement, or finalize; filing a passing observation is a side effect that
must never cost the stage its outcome.

No constitution dependency. Filing is something the pipeline already does
under labels it owns, so this feature can proceed before #409 (which would
name this as the board loop's feed under a new Principle X) merges. #408 is
the consumer.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A defect a stage met on the way reaches the board (Priority: P1)

An agent stage is doing its own work and notices something broken that is
not its task — a gate that cannot fail, a contract that contradicts the
workflow, a count that has gone stale. It writes a short structured
description of what it saw and carries on with its own task. It does not
fix it. It does not file it. By the time the run ends, an issue exists on
the board carrying the description, the evidence, and a line saying which
stage of which spec found it and in which run.

**Why this priority**: This is the feature. Every other story is a
constraint on it or a report about it. The observation is free — the stage
already read the code — and today 100% of it is discarded at the end of the
run.

**Independent Test**: Drive one stage run against a tree carrying a
deliberately planted defect outside that stage's task, and confirm an issue
exists afterwards carrying the description, the evidence paths, the run
URL, and the stage-and-spec attribution line — with the stage's own output
unchanged from a run without the planted defect.

**Acceptance Scenarios**:

1. **Given** a stage run whose agent described one well-formed finding,
   **When** the run completes, **Then** exactly one issue exists carrying
   that finding, labelled as found by that stage, with a body naming the
   stage, the spec, and the run.
2. **Given** a stage run whose agent described no finding, **When** the run
   completes, **Then** no issue is filed, nothing is reported as an error,
   and the run's outcome is identical to today's.
3. **Given** a stage run that filed a finding, **When** the stage's own
   declared outputs and artifacts are compared against an equivalent run
   without the finding, **Then** they are unchanged — the finding did not
   widen, narrow, or redirect the stage's own work.
4. **Given** a filed finding, **When** a maintainer opens it, **Then** it
   names what is wrong and points at file paths and the run, without the
   maintainer having to open the run transcript to understand the claim.

---

### User Story 2 - Code decides what gets filed, never the agent (Priority: P1)

The agent's description is a proposal. A deterministic step reads it,
validates it against a checked-in schema, computes a fingerprint from
deterministic fields, checks that fingerprint against what is already open,
and only then files. A malformed proposal is dropped with a log line saying
why. A proposal that matches something already open is appended to that
issue rather than opening a twin. A run that proposes more findings than
the cap allows does not flood the board.

**Why this priority**: Constitution Principle IX exists because a prompt
instruction is a request the model can silently fail to follow — it
produces no error, no test failure, and no signal that the gate was ever
skipped. A filed issue is a durable action, and the judgment that gates it
("is this well-formed?", "is this new?") has to be code a reviewer can
re-run. Without this story the feature is a licence for a chatty run to
write to the board.

**Independent Test**: Feed the filing step a fixture set — a well-formed
finding, a malformed one, one that duplicates an open issue, and more
findings than the cap — and confirm exactly the expected filings, the
expected appends, and the expected drops, each with its log line, without
any agent running.

**Acceptance Scenarios**:

1. **Given** a proposed finding missing a required field or otherwise
   failing the schema, **When** the filing step runs, **Then** nothing is
   filed for it and the run records a log line naming the finding and why
   it was dropped.
2. **Given** a proposed finding whose fingerprint matches an issue already
   open under the pipeline's finding label, **When** the filing step runs,
   **Then** the existing issue receives a reference to this run and no
   second issue is created.
3. **Given** a run proposing more findings than the cap, **When** the
   filing step runs, **Then** no more than the cap are filed, the excess is
   dropped deterministically rather than by the agent's own choice, and the
   drop is recorded.
4. **Given** the fingerprint of any finding, **When** it is recomputed from
   the same inputs, **Then** it is identical — it is derived from
   deterministic fields (such as stage, file path, and gate or artifact
   name), never from the model's prose.
5. **Given** any stage in this feature's scope, **When** its tool grants are
   inspected, **Then** no grant to create an issue was added for this
   feature: the agent cannot file even if it tries.

---

### User Story 3 - The lifecycle issue shows what the run spun off (Priority: P2)

A maintainer reading the lifecycle issue alone can see that a run filed
something. Each filing adds one unchecked outstanding-task line to the
lifecycle issue, pointing at the new issue — the same mechanism stage 10
already uses when it spins work out of a PR conversation.

**Why this priority**: Constitution Principle III requires the lifecycle of
a spec to be legible from its original issue alone. A run that quietly
opened an issue somewhere else breaks that: the maintainer learns about it
from the board, not from the thread they are already reading. It is P2
rather than P1 because the filing itself is useful before the cross-link
exists — but only barely, and only for one release.

**Independent Test**: Drive one stage run that files a finding, then read
only the lifecycle issue and confirm it names what was spun off and links
it, without opening the run or the board.

**Acceptance Scenarios**:

1. **Given** a run that filed one finding, **When** the lifecycle issue is
   read, **Then** it carries exactly one new unchecked outstanding-task line
   linking that issue.
2. **Given** a run whose finding was deduped into an existing issue rather
   than filed fresh, **When** the lifecycle issue is read, **Then** it still
   records that the run observed and routed the finding, and where it went.
3. **Given** a run that filed nothing, **When** the lifecycle issue is read,
   **Then** no outstanding-task line is added and nothing about the run's
   existing reporting changes.
4. **Given** a run with no lifecycle issue to post to, **When** it files a
   finding, **Then** the filing still happens and the absence of a
   cross-link is recorded rather than treated as a failure.

---

### User Story 4 - Filing never costs the stage its outcome (Priority: P1)

The filing step is observability. It runs after the stage's deterministic
read-back of what the agent produced, it is allowed to fail, and its
failure changes nothing about the stage's verdict, outputs, or the
lifecycle's progress. A GitHub API refusal, a rate limit, or a bug in the
filing step itself degrades to "no issue filed, loudly" — never to a red
stage.

**Why this priority**: This ships inseparably with US1: the moment a stage
can file, it can also fail to file. A feature whose purpose is to capture
passing observations must not become a new way for a specification run to
die. It is also the shape the `review-step-gating` skill checks for.

**Independent Test**: Force the filing step to fail (deny its API call) on
an otherwise healthy stage run and confirm the stage's outcome, declared
outputs, and lifecycle transition are identical to a run where filing
succeeded — and that the failure is visible in the run's own summary.

**Acceptance Scenarios**:

1. **Given** a filing step that fails for any reason, **When** the stage
   finishes, **Then** the stage's outcome and declared outputs are what they
   would have been had the step not run at all.
2. **Given** a filing step that fails, **When** the run is inspected,
   **Then** the failure is visible in the run's own summary and in the log,
   with the unfiled finding's description preserved there so it is not
   silently lost.
3. **Given** a stage run in which the agent step itself failed or was
   exhausted, **When** the filing step is reached, **Then** it does not
   convert that run into a filing, and the stage's existing failure
   reporting is unchanged.
4. **Given** a cancelled run, **When** the job completes, **Then** the
   filing step does not file — cancellation is not an occasion to write to
   the board.
5. **Given** the filing step's position in the job, **When** the job is
   read, **Then** it sits after the stage's deterministic read-back, so no
   read-back the stage depends on is stranded behind it.

---

### User Story 5 - A finding is data, and stays data (Priority: P1)

A finding may quote an issue body, a comment, or a file the agent read —
all untrusted content. It is filed as quoted data, framed as such. Anything
that later reads a filed finding — the board loop above all — reads it as
data too, never as instructions.

**Why this priority**: Constitution Principle V is non-negotiable, and this
feature opens a new path from untrusted input to a durable artifact that
another agent will read. Without this story, an issue body containing
instruction-shaped text could be laundered through a finding into the board
loop's input, where it arrives wearing the pipeline's own label.

**Independent Test**: Plant instruction-shaped text in the content a stage
reads, drive a run that files a finding quoting it, and confirm the filed
body frames the quote as data — then confirm the consuming loop's own
framing treats a body carrying the pipeline's finding label as untrusted.

**Acceptance Scenarios**:

1. **Given** a finding that quotes untrusted content, **When** it is filed,
   **Then** the quoted material is presented as data in the issue body and
   is distinguishable from the pipeline's own text.
2. **Given** a filed finding, **When** any downstream agent reads it,
   **Then** that agent's framing treats the body as untrusted user data.
3. **Given** the credentials the filing step uses, **When** they are
   inspected, **Then** they are the pipeline's existing identity and no
   stage's write surface widened beyond what filing an issue requires.

---

### Edge Cases

- **The overwhelmingly common case — no findings at all**: the step is a
  no-op. It emits nothing that reads as a problem, and adds no measurable
  time to the run.
- **A malformed or partially-formed finding**: dropped whole, never filed
  with the missing parts guessed or defaulted. The drop is logged with the
  reason.
- **The agent emits the findings channel but nothing parseable at all**
  (truncated output, wrong shape): treated as zero findings plus one log
  line, not as a stage failure.
- **More findings than the cap**: the excess is dropped by the code's own
  deterministic ordering, not by asking the agent to choose which matter.
- **A fingerprint matching an issue that is already closed**: the defect
  recurred. A new issue is filed and linked to the closed one rather than
  reopening a settled thread.
- **Two different stages meet the same defect**: the stage is part of the
  fingerprint basis, so each files its own issue. They are cross-referenced
  rather than merged; a maintainer closes one.
- **The same stage meets the same defect on a later iteration of the same
  spec**: the fingerprint matches the open issue, so the run is appended to
  it — the watchdog's discipline.
- **The finding is actually inside the stage's own task**: code cannot tell
  a scope boundary from prose. The filing happens; triage catches it.
- **The agent proposes a finding and then fixes it anyway**: the prompt
  forbids it, and nothing in code can prevent it. The stage's existing diff
  review is what catches it; this feature adds no new protection there.
- **A run with no lifecycle issue** (a stage driven outside a spec
  lifecycle): the filing happens, the cross-link does not, and the absence
  is recorded.
- **The label the filing needs does not exist yet**: creating it is part of
  the filing step's own deterministic work, not a prerequisite a maintainer
  must remember.
- **The API refuses the filing** (rate limit, permission, outage): no issue,
  a loud log line carrying the finding's text, and an unchanged stage
  outcome.
- **A stage whose enable input is off** (the five discovery stages, by
  default): the mechanism is present but inert. Nothing is filed, the
  agent's proposals survive only in the execution-output artifact, and the
  run reports no problem — being switched off is not a failure.
- **An adopter does not want the pipeline opening issues in their
  repository**: the behaviour is controlled by the stage's declared input
  surface, which their wrapper sets — per stage, so an adopter can leave
  implement filing and silence the rest, or the reverse.

## Requirements *(mandatory)*

### Scope

- **FR-001**: All seven agent stages — intake, clarify, plan, tasks,
  implement, converge, finalize — are in scope, and each MUST receive the
  complete mechanism (proposal channel, validation, dedup, filing,
  cross-link) in this feature. No stage may carry a partial mechanism.
  Which stages actually file is a matter of configuration, not of scope:
  the enable input of FR-029 MUST default to on for implement and finalize
  — the two that read the most code — and to off for the other five, so
  that turning a discovery stage on later is a wrapper change rather than
  a second move of the published surface.
- **FR-001a**: Because activation is configuration, the published surface
  MUST move exactly once for this feature: every in-scope stage declares the
  same filing inputs in the same release, whether or not its default is on.
- **FR-002**: The watchdog's `pipeline-defect` route, stage 10's
  `spec-request` and `permission-request` spin-offs, auto-update's and
  auto-release's failure filings MUST be unchanged. This feature adds a
  route for "a defect I met during my own work", alongside those routes for
  "this feature's own failure".

### The agent proposes

- **FR-003**: Each in-scope stage's prompt MUST gain one paragraph
  instructing the agent that, on meeting a defect outside its own task, it
  describes the defect in that stage's findings channel — in the shape
  FR-006 gives that stage — and carries on: it does not fix the defect, and
  it does not file it.
- **FR-004**: No in-scope stage MAY gain the ability to create a GitHub
  issue for this feature. The agent's proposal is the only thing it
  produces; the filing is entirely deterministic code (Constitution
  Principle IX).
- **FR-005**: A finding MUST NOT change the stage's own behaviour: the
  stage's declared outputs, its artifacts, its lifecycle transition, and the
  scope of the work it performs are all unaffected by whether it proposed a
  finding.
- **FR-006**: The findings channel is the agent's final message, in one of
  two shapes decided by what that stage's final message already is:
  - a stage whose final message is free-form prose MUST carry findings in a
    fenced block in that message — the channel every stage already captures
    in its execution-output artifact (#312), and the only one the read-only
    stages under spec 051's inspection policy can produce with no write
    tool;
  - a stage whose terminal result is already a schema-validated structured
    object MUST carry findings as a `findings` array inside that result,
    because a fenced block cannot be added to such a message without
    breaking the schema that validates it.
  A `findings/*.json` file is NOT the channel: only the write-capable stages
  could produce one, which would exclude the read-only stages FR-001 puts in
  scope. Each stage has exactly one authoritative channel — the structured
  result where the stage has one, the fenced block otherwise — and the
  filing step MUST read that one.
- **FR-007**: The channel MUST NOT disturb any stage's existing structured
  result or the validation that stage already performs on it. The `findings`
  array MUST be an addition to each such schema that leaves the existing
  required fields and their validation unchanged, and MUST be optional: a
  result that omits it, or carries it empty, means no findings and MUST
  still validate. A stage whose terminal result is schema-validated MUST NOT
  be asked to emit a fenced block as well.

### Code files

- **FR-008**: A checked-in schema MUST define a well-formed finding. Its
  required content is: a title; a statement of what is wrong; evidence
  consisting of file paths plus the run URL; and the deterministic fields
  that form the fingerprint basis.
- **FR-009**: A post-agent step MUST read the findings channel, validate
  each finding against that schema, and drop any finding that fails
  validation — whole, never partially filed and never with missing fields
  defaulted — recording one log line naming the finding and the reason.
- **FR-010**: The fingerprint MUST be computed from deterministic fields
  only — such as the stage, the file path, and the gate or artifact name —
  and MUST NOT be derived from the model's prose. Spec 024's lesson: a
  prompt-authored fingerprint basis drifts.
- **FR-011**: Before filing, the step MUST check the fingerprint against
  issues already open under the pipeline's finding label. On a match it MUST
  append a reference to the current run to the existing issue rather than
  opening a twin — the watchdog's discipline.
- **FR-012**: A fingerprint matching only a closed issue MUST result in a
  new issue that links the closed one, rather than reopening it.
- **FR-013**: Findings filed per run MUST be capped by code. Proposals
  beyond the cap MUST be dropped by the step's own deterministic ordering,
  never by asking the agent which of its findings matter most, and the drop
  MUST be recorded.
- **FR-014**: Each filed issue MUST carry a pipeline-owned label identifying
  the stage that found it (`found-by:<stage>`), and the step MUST ensure
  that label exists rather than failing because a maintainer never created
  it.
- **FR-015**: Each filed issue's body MUST carry the attribution line
  `Found by the <stage> stage of spec NNN, run <url>` together with the
  finding's evidence, so a maintainer can act on it without opening the run.
- **FR-016**: The find-or-create-under-a-dedup-label idiom MUST have exactly
  one home in the repository. The existing internal
  `durable-failure-issue` composite is that idiom, and reaching it from a
  published stage crosses the boundary Constitution Principle VII draws
  around underscore-prefixed directories. The resolution is promotion: the
  existing internal composite MUST be promoted to the published surface,
  and auto-release and auto-update MUST be repointed at the promoted path
  in the same change, leaving no consumer on the internal path and no
  second copy of the idiom anywhere. Its interface is already a general
  find-or-create-under-a-dedup-label filer, so the promotion MUST NOT
  reshape that interface for this feature's sake; any behaviour filing
  needs and the composite lacks is an addition that the existing consumers
  can ignore.

### Legibility

- **FR-017**: Each filing MUST add one unchecked outstanding-task line to
  the lifecycle issue, linking the filed issue, using the mechanism stage 10
  already uses for its spin-offs (Constitution Principle III).
- **FR-018**: A finding routed to an already-open issue by FR-011 MUST still
  be recorded on the lifecycle issue, naming where it went.
- **FR-019**: When a run has no lifecycle issue to post to, the filing MUST
  still occur and the absent cross-link MUST be recorded rather than
  reported as a failure.
- **FR-020**: The run's own summary MUST state how many findings were
  proposed, filed, appended to an existing issue, and dropped — and for
  dropped findings, why.
- **FR-021**: A run that filed anything MUST say so where a maintainer
  scanning run outcomes will see it, so filing activity is legible without
  opening the board.

### Never in the way

- **FR-022**: The filing step MUST be observability: it MUST run with
  `continue-on-error` semantics, and its failure MUST NOT fail the stage,
  change the stage's declared outputs, or alter the lifecycle transition.
- **FR-023**: The filing step MUST be placed after the stage's deterministic
  read-back of what the agent produced, so nothing the stage depends on sits
  behind it.
- **FR-024**: The step's gating MUST distinguish "the job was cancelled"
  from "something above me failed": a cancelled run MUST NOT file, while a
  run whose agent step failed or exhausted its budget MUST NOT be converted
  into a filing either, and neither case may strand or alter the stage's
  existing failure reporting.
- **FR-025**: A filing that could not be performed MUST leave the finding's
  text visible in the run's log and summary, so an observation is never lost
  silently.

### Untrusted content

- **FR-026**: A finding that quotes content the agent read MUST be filed
  with that quoted material presented as data and distinguishable from the
  pipeline's own text.
- **FR-027**: Any consumer of a `found-by:*` issue — the board loop (#408)
  above all — MUST frame the body as untrusted user data, never as
  instructions.
- **FR-028**: Filing MUST use the pipeline's existing identity. No stage's
  write surface may widen beyond what creating and commenting on an issue in
  the consuming repository requires.

### Published surface and coverage

- **FR-029**: The published stages' `workflow_call` input surface MUST widen
  by exactly the knobs filing needs — at minimum the finding label prefix,
  the per-run cap, and whether filing is enabled — each a declared, typed
  input passed by the wrapper, never ambient repository state. The enable
  input MUST default per FR-001 (on for implement and finalize, off for the
  other five), so an adopter changes a stage's filing behaviour by setting
  an input rather than by waiting for another release. This widening, and
  the composite promotion FR-016 requires, are a MINOR change at the next
  release (Constitution Principle VII).
- **FR-030**: Every failure branch the filing step ships MUST be exercised
  by a checked-in fixture: a malformed proposal, a dedup hit against an open
  issue, a match against a closed issue, a cap overflow, an API failure, and
  the no-findings case (Constitution Principle VIII). Both channel shapes of
  FR-006 — the fenced block and the structured result's `findings` array —
  MUST be covered, including a structured result that omits the array.
- **FR-031**: A gate MUST fail CI when an in-scope stage carries the
  findings paragraph in its prompt without the filing step in its job, or
  the filing step without the paragraph — the rule's single home, added to
  the nearest existing gate rather than left as prose. Because FR-001 puts
  all seven stages in scope regardless of their enable default, the gate
  MUST check every one of them, not only the stages whose default is on.
- **FR-032**: A gate MUST fail CI if a second copy of the FR-016 filing
  idiom appears, the way the metrics cost-line formatter is already
  protected, and likewise if any caller still reaches the composite at its
  retired internal path after the promotion.
- **FR-033**: Documentation for adopters MUST state that an in-scope stage
  may open issues in their repository, under which label, which stages file
  by default and which do not, and which input turns filing on or off for a
  given stage.

### Key Entities

- **Stage finding**: one defect an agent met outside its own task, described
  by the agent as a proposal. Carries a title, what is wrong, evidence (file
  paths and the run URL) and the deterministic fields that form its
  fingerprint basis. A proposal, never an issue.
- **Findings channel**: the one place a given stage's agent writes its
  proposals so the deterministic step can read them — a fenced block in a
  free-form final message, or the `findings` array of a schema-validated
  terminal result, per FR-006. Never a file.
- **Finding schema**: the checked-in definition of a well-formed finding.
  The sole authority on whether a proposal is filed; not the agent's
  judgment.
- **Fingerprint**: the dedup key, derived from deterministic fields (stage,
  file path, gate or artifact name) and never from the model's prose. Stable
  across runs, so the same defect met twice is recognised.
- **Finding label**: the pipeline-owned `found-by:<stage>` label, both the
  marker of provenance and the search scope the dedup check reads.
- **Filed finding issue**: the durable artifact — description, evidence, and
  the `Found by the <stage> stage of spec NNN, run <url>` line. Read by the
  board loop as data.
- **Filing step**: the post-agent, post-read-back, failure-tolerant
  deterministic step that validates, fingerprints, dedups, files, labels and
  cross-links. The only thing in this feature that writes.
- **Outstanding task item**: the unchecked line the filing step adds to the
  lifecycle issue, stage 10's existing mechanism, making the spin-off
  legible from the thread the maintainer is already reading.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The number of well-formed defects an in-scope stage described
  that are lost at the end of the run is zero — down from all of them today.
- **SC-002**: The number of issues created by an agent's own tool call under
  this feature is zero; 100% of filings are performed by deterministic code.
- **SC-003**: The number of malformed findings filed as issues is zero, and
  every dropped finding has a log line naming the reason.
- **SC-004**: The number of twin issues opened for a fingerprint that
  already has an open issue is zero.
- **SC-005**: The number of findings filed by any single run never exceeds
  the configured cap.
- **SC-006**: The number of stage runs whose outcome, declared outputs, or
  lifecycle transition changed because filing succeeded, failed, or was
  skipped is zero.
- **SC-007**: The number of filings that reach the board without a matching
  outstanding-task line on an available lifecycle issue is zero.
- **SC-008**: A maintainer reading only the lifecycle issue can name what
  the run spun off, and open it, in under one minute and without opening the
  run.
- **SC-009**: The number of failure branches the filing step ships without a
  checked-in fixture is zero.
- **SC-010**: After this ships, the board loop's input is non-empty without
  anyone typing: at least one `found-by:*` issue arrives from a pipeline run
  rather than from a local session.
- **SC-011**: The number of downstream consumers that treat a `found-by:*`
  body as instructions rather than as data is zero.
- **SC-012**: The number of copies of the filing idiom in the repository is
  exactly one, enforced by a gate rather than by review attention.
- **SC-013**: The added wall-clock cost of the filing step on a run that
  proposes nothing is negligible against the stage's own agent step, and a
  run that proposes nothing produces no new output a maintainer must read.

## Assumptions

- The per-run cap defaults to **three** findings, the number the lifecycle
  issue proposes. It is a declared input, so the value is a reviewed change
  and an adopter may lower it.
- Filing ships to all seven stages but is **enabled by default only for
  implement and finalize**, with the wrapper able to turn any stage on or
  off (FR-001, FR-029). The label is pipeline-owned and the cap is small,
  so the default behaviour is a bounded, clearly-attributed handful of
  issues from the two stages that read the most code rather than a surprise
  from all seven at once; an adopter who wants the discovery stages filing
  too sets the input. FR-033 makes both the default and the switch
  discoverable before adoption rather than after.
- Putting every stage behind one input rather than shipping a subset now and
  the rest later moves the published surface once. The consequence accepted
  here is that five stages ship code that is off by default: FR-030's
  fixtures and FR-031's gate therefore cover all seven, so a stage that has
  never filed in anger is still exercised.
- The dedup scope is open issues carrying the pipeline's finding label in
  the consuming repository. This feature introduces no cross-repository
  search.
- The stage is part of the fingerprint basis, as the lifecycle issue
  proposes. Two stages meeting the same defect therefore file two issues
  that cross-reference rather than merge; a maintainer closes one. Removing
  the stage from the basis would collapse those but would also make the
  `found-by:<stage>` provenance ambiguous, so the stage stays in.
- Filing uses the pipeline's existing GitHub App identity — the one the
  stages already use to comment on lifecycle issues. No new credential, no
  new secret, and no PAT (Constitution Principle V).
- `specs/010-reusable-pipeline`'s stage interfaces and the existing
  wrapper-owns-the-knobs division are unchanged: the new inputs are declared
  on the stage and supplied by the wrapper.
- The agent's execution output is already captured as an artifact (#312), so
  under either shape of the FR-006 channel the proposal is durably recorded
  even when filing fails.
- Each stage's terminal result shape is known and stable, so which of the
  two FR-006 shapes applies to a stage is a fact about that stage rather
  than a runtime choice: the filing step does not have to sniff both.
- #408 (the board loop) is the consumer and is not a dependency: findings
  accumulate usefully on the board whether or not a loop is reading them.
  #409 (Principle X) is likewise not a dependency — the pipeline already
  files issues under labels it owns, so the rule this feature needs is
  already in force.
- A finding that turns out to be inside the finding stage's own scope, or
  that turns out not to be a defect at all, is a triage cost a maintainer
  pays when closing it. This feature does not attempt to have code judge
  scope from prose.
- `specs/033-pr-conversation-commands`' outstanding-task-item mechanism is
  reused as-is for FR-017 rather than reimplemented.
- The `durable-failure-issue` composite's promotion (FR-016) is a move, not
  a rewrite: its interface is already a general
  find-or-create-under-a-dedup-label filer, so auto-release's and
  auto-update's behaviour after being repointed is expected to be identical
  to before. Their existing coverage is what demonstrates that.
- The `review-step-gating` skill's shape governs FR-022 through FR-024, and
  the change will be run past it, per this repository's working rules.
