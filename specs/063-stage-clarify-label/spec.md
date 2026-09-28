# Feature Specification: The Label Table Tells the Truth — `stage:clarify` Is Either Applied or Retired

**Feature Branch**: `spec-draft/063-stage-clarify-label`

**Created**: 2026-09-24

**Status**: Draft

**Input**: Lifecycle issue #483 — "stage:clarify is documented/created as a
lifecycle label but no workflow ever applies it" (routed from `board-loop.yml`,
originating issue #361)

## Overview

`docs/setup.md` presents a lifecycle label taxonomy and instructs every
adopting maintainer to create eight labels by hand, one of which is:

```
gh label create stage:clarify   --color 1D76DB --description "Open clarification questions"
```

with the table row "`stage:clarify` | Spec has open clarification questions"
(`docs/setup.md:146`, `docs/setup.md:175`). `docs/architecture.md:355` and
`docs/architecture.md:375` describe the clarify trigger in terms of it, and
`docs/adoption.md:229` ships the wrapper condition that matches it.

No workflow in this repository ever applies it. Of the eight documented
labels plus the two created on the fly, `stage:clarify` is the only one with
no writer:

| Label | Applied by |
|---|---|
| `stage:spec` | `intake.yml:711` (the intake agent's own `gh issue edit --add-label`) |
| `stage:clarify` | **nothing** |
| `stage:plan` | `plan.yml:1153` (pr mode), `plan.yml:1239` (auto mode) |
| `stage:tasks` | `tasks.yml:1205` |
| `stage:implement` | `implement.yml:2488` |
| `stage:review` | `finalize.yml:1205` |
| `stage:done` | `cleanup.yml:869` |
| `stage:stalled` | `wing-commander-chain-stop-notice/action.yml:146`, `implement.yml:2861`, `cleanup.yml:1563` |

Every reference to `stage:clarify` in shipped code is a *reader* or a
*remover* of a label nothing writes:

- `wing-commander-2-clarify.yml:25` — the clarify wrapper fires on
  `stage:spec` **or** `stage:clarify`. The first disjunct is what actually
  matches; the second has never been reached by a pipeline-driven run.
- `plan.yml:1155` and `plan.yml:1241` — two best-effort
  `--remove-label "stage:clarify" 2>/dev/null || true` cleanup lines that
  have never had anything to remove.
- `clarify.yml:1292` — the stall path passes `stage-label: "stage:clarify"`
  to `wing-commander-chain-stop-notice`, whose `stage-label` input is
  documented as "`stage:<name>` label to remove when the mark succeeds"
  (`specs/041-implement-stall-notice/data-model.md:65`). On a genuine clarify
  stall the composite adds `stage:stalled` and removes a label that was never
  there.
- `auto-release.yml:1143-1147` — the end-to-end run's stage-label timeline
  assertion carries a comment recording exactly this state, because requiring
  the label made a genuine pass impossible:

  ```
  # stage:clarify is never applied as an issue label by any stage
  # workflow (clarify.yml's only reference is stall-notice prose,
  # and wing-commander-chain-stop-notice always adds stage:stalled
  # instead) -- requiring it here made a genuine pass impossible.
  ```

  `specs/055-unattended-e2e-gates/research.md:450-453` records the
  consequence: of the four gates that end-to-end run drives, the
  clarification gate is "the clarification gate, which today has no assertion
  at all".

### Why this reached the spec pipeline rather than a local fix

Nothing is failing today. A clarification-needed issue sits at `stage:spec`
for the whole exchange, which is what the clarify wrapper's first disjunct
already matches, so replies are picked up and the spec advances. The defect
is a promise the documentation makes that the code does not keep — and
closing it has two opposite, defensible shapes:

- **Wire it up**: the pipeline starts applying the label while questions are
  open and clearing it when they are answered. The label table becomes true,
  maintainers can filter "awaiting an answer" apart from "awaiting spec
  review", the two `plan.yml` removal lines and `clarify.yml:1292`'s
  `stage-label` start doing work, and the end-to-end clarification gate
  becomes assertable.
- **Retire it**: the label leaves the documented taxonomy and every shipped
  reference to it goes with it. The taxonomy shrinks to what the pipeline
  actually writes, and one fewer label is asked of every adopter.

Choosing between them was the owner's trade-off, which is why #361 was left
unrouted with "Worth a maintainer call" rather than fixed. **The owner chose
"wire it up"** (see Clarifications): the pipeline applies the label while
questions are open, replacing `stage:spec`, and restores `stage:spec` when
they are answered. The requirements below keep the invariant set, carry
Direction A in force, and retain Direction B's heading only to record that it
was not taken.

## Clarifications

### Session 2026-09-25 — resolved on lifecycle issue #483

All three open questions were answered. No `[NEEDS CLARIFICATION]` markers
remain.

- **FR-002 — the direction**: **(a) wire it up.** The pipeline applies
  `stage:clarify` while clarification questions are open and clears it when
  they are answered, so the lifecycle is readable from the issue itself and
  the end-to-end clarify gate becomes assertable. Direction A (FR-010..FR-015,
  FR-023) is in force; Direction B (FR-016..FR-020) is dropped.
- **FR-012 — flip or coexist**: **flip.** `stage:clarify` *replaces*
  `stage:spec` while questions are open — one current stage label at a time,
  as with every other stage transition.
- **FR-021 — the end-to-end assertion**: **(a) in scope here.** A conditional
  clarification assertion lands in this same change, gated on that run's
  intake having actually posted a questionnaire.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The label table describes the pipeline that ships (Priority: P1)

A maintainer adopting Wing Commander follows `docs/setup.md` § 4 and creates
the labels it lists. Every label they create is one the pipeline will either
write itself or that the documentation explicitly tells them is theirs to
apply by hand. No label in the table is silently inert.

**Why this priority**: This is the defect. A taxonomy that documents a label
no code writes teaches the adopter to trust label state that never changes,
and it is the reason `auto-release.yml` had to weaken its own assertion.

**Independent Test**: Read `docs/setup.md` § 4 against the shipped
workflows: for each documented label, find the workflow or composite action
that applies it, or the sentence in the docs that says a human applies it.
Deliverable is met when the count of labels with neither is zero.

**Acceptance Scenarios**:

1. **Given** the merged change, **When** a maintainer walks every row of
   `docs/setup.md`'s label table and every line of its label-creation
   script, **Then** each row either names a pipeline stage that applies it or
   states that no workflow applies it and who does.
2. **Given** the merged change, **When** a reader greps the shipped
   workflows and composite actions for `stage:clarify`, **Then** every
   surviving reference is consistent with a label the pipeline writes — the
   clarify wrapper's disjunct, `plan.yml`'s two removal lines and
   `clarify.yml:1292`'s `stage-label` all have something real to act on, and
   no reader or remover is left pointing at a label nothing writes.
3. **Given** the pre-change tree, **When** the new taxonomy gate runs,
   **Then** it fails and names `stage:clarify` as documented-but-unapplied.

---

### User Story 2 - A requester's reply still reaches the clarify stage (Priority: P1)

A requester answers the clarification questionnaire on their lifecycle
issue. The clarify stage picks the reply up, folds the answers into the draft
spec, and the lifecycle continues — exactly as it does today, now driven by
an issue carrying `stage:clarify` instead of `stage:spec`.

**Why this priority**: The label change touches the trigger condition of the
one stage that is driven by a human reply. `docs/architecture.md:358-364`
names getting this split wrong as "this pipeline's most repeated bug class",
including a guard that "let intake ask for a reply on an issue whose labels
made 1b's trigger unable to fire". A regression here silently strands every
clarification exchange.

**Independent Test**: Drive one clarification round end to end (the existing
end-to-end run already drives one) and confirm the reply-triggered clarify
run starts and folds.

**Acceptance Scenarios**:

1. **Given** an issue carrying `stage:clarify` alone while questions are
   open, **When** the requester or a maintainer replies, **Then**
   `wing-commander-2-clarify.yml`'s trigger condition evaluates true — via
   its second disjunct, which a pipeline-driven run now reaches for the first
   time — and the clarify stage runs.
2. **Given** a lifecycle issue that was already mid-clarification when the
   change merged (it carries `stage:spec`, or a hand-applied
   `stage:clarify`), **When** the requester replies, **Then** the clarify
   stage still runs, and the issue still flips to `stage:plan` when plan
   runs.
3. **Given** the adopter-facing wrapper snippet in `docs/adoption.md`,
   **When** it is compared against the shipped
   `wing-commander-2-clarify.yml` trigger condition, **Then** the two agree.

---

### User Story 3 - The rule has a home and a gate that can fail it (Priority: P2)

The "every documented lifecycle label has a writer" rule is enforced by a
checked-in gate that runs at pull-request time, derives both sides of the
comparison rather than hardcoding them, and is demonstrated to fail on the
tree that motivated it.

**Why this priority**: CLAUDE.md: "a rule with no gate behind it lasts until
the next session." The divergence this feature fixes survived from the label
table's introduction through at least one full end-to-end run and one
weakened assertion, because nothing compared the two lists.

**Independent Test**: Run the gate on the pre-change tree (expect failure
naming `stage:clarify`) and on the post-change tree (expect pass); add a
label row to the docs with no writer and confirm the gate goes red.

**Acceptance Scenarios**:

1. **Given** a documentation change that adds a new lifecycle label row with
   no workflow applying it, **When** the gate suite runs, **Then** it fails
   and names the new label.
2. **Given** a workflow change that deletes the only `--add-label` for a
   documented label, **When** the gate suite runs, **Then** it fails and
   names that label.
3. **Given** a label that is deliberately maintainer-applied, **When** it is
   recorded in the gate's exemption registry with a reason, **Then** the gate
   passes and the reason is readable next to the label.
4. **Given** the new gate, **When** `verify-gate-wiring.py` (Gate 10) and
   `.github/scripts/run-local-gates.py` run, **Then** the gate is registered
   and invoked by both.

---

### Edge Cases

- **A questionnaire is posted and never answered.** The issue sits at
  `stage:clarify` indefinitely, which must be terminal-safe: the issue must
  still be advanceable by hand, and `plan.yml`'s stage flip must still leave
  exactly one `stage:*` label behind when the spec is eventually merged — its
  two existing `stage:clarify` removal lines now being the ones that clear
  it.
- **A second clarification round.** The clarify stage can itself end in
  `needs-clarification` (`clarify.yml:960`) and post a follow-up
  questionnaire. Applying a label that is already present, or removing one
  that is already absent, must be a no-op rather than a failure.
- **A clarify stall while questions are open.** `clarify.yml:1292` passes
  `stage-label: "stage:clarify"` to the stall notice, which adds
  `stage:stalled` and removes the named label. This input now starts doing
  what it says, and the issue is left carrying `stage:stalled` alone rather
  than `stage:stalled` beside a `stage:clarify` that was never removed.
- **An adopter repository with no label taxonomy at all.** `plan.yml:1151`
  records the rule: create-before-add, because "single-stage adopters have no
  label taxonomy". A new `--add-label` that assumes the label exists fails
  the step on those repositories.
- **An end-to-end run that produces no clarification questions.** A spec
  drafted with zero open questions never enters the clarification state, so
  any assertion that demands the label unconditionally makes a genuine pass
  impossible — the precise regression `auto-release.yml:1143-1147`'s comment
  was written to record. The FR-021 assertion must therefore read that run's
  own clarification-needed signal and assert only when a questionnaire was
  actually posted.
- **A spec PR mirroring issue labels.** `intake.yml:1278` copies the issue's
  labels onto the spec PR (clarify has no such step). A stage flip must
  happen before that mirror, or the PR snapshots the label set the issue just
  left (`plan.yml:1156-1158` states this ordering rule).

## Requirements *(mandatory)*

### Functional Requirements — invariant (hold under every direction)

- **FR-001**: Every label that `docs/setup.md` § 4 instructs a maintainer to
  create MUST, after this change, either be applied by a shipped workflow or
  composite action, or be documented in the same table as applied by a human
  with the reason no workflow writes it. `stage:clarify` MUST satisfy one of
  those two; today it satisfies neither.
- **FR-002**: The direction taken for `stage:clarify` MUST be **(a) wire it
  up** — the pipeline applies the label while clarification questions are open
  and clears it when they are answered — applied consistently to code,
  documentation and gates. Direction A's requirements (FR-010..FR-015, FR-023)
  are in force. The two alternatives considered and rejected were retiring the
  label from the taxonomy (Direction B, FR-016..FR-020) and restating it as a
  maintainer-applied convenience label recorded as an FR-007 exemption;
  neither is implemented.
- **FR-003**: A reply on a lifecycle issue awaiting clarification MUST
  continue to reach the clarify stage. An issue carrying `stage:clarify`
  alone MUST satisfy `wing-commander-2-clarify.yml`'s trigger condition, and
  the adopter-facing copy of that condition in `docs/adoption.md` MUST agree
  with the shipped condition after the change.
- **FR-004**: No lifecycle issue in flight at merge time may be stranded. An
  issue carrying `stage:spec` — or a hand-applied `stage:clarify` — when the
  change lands MUST still trigger clarify on a reply and MUST still flip
  cleanly to `stage:plan`.
- **FR-005**: Every shipped comment whose text asserts the pre-change state
  MUST be corrected in the same change, treated as code per CLAUDE.md's
  load-bearing-comments rule. At minimum this covers
  `auto-release.yml:1143-1147` ("stage:clarify is never applied as an issue
  label by any stage workflow"), which this change makes false, and which
  FR-021 replaces with a conditional assertion.
- **FR-006**: Adopter-facing documentation MUST be consistent with the chosen
  direction at every site that mentions the label:
  `docs/setup.md`'s label table and label-creation script,
  `docs/architecture.md`'s clarify trigger description (two sites), and
  `docs/adoption.md`'s wrapper snippet and intake side-effects row.
- **FR-007**: A checked-in, pull-request-time gate MUST enforce FR-001. It
  MUST derive the documented label list from the adopter documentation and
  the applied label set from the shipped workflows and composite actions —
  neither side hardcoded as a literal list — and MUST fail when a documented
  label has no writer and no registered exemption. Exemptions MUST live in a
  checked-in registry entry carrying a reason, not in a code comment alone.
- **FR-008**: The gate MUST fail when run against the pre-change tree,
  naming `stage:clarify`, and that demonstration MUST be recorded in the
  pull request. A gate that cannot fail its own subject does not satisfy
  FR-007.
- **FR-009**: The gate MUST be wired into `lint-workflows.yml`, discovered by
  `verify-gate-wiring.py` (Gate 10), and invoked by
  `.github/scripts/run-local-gates.py`, so a local pre-push run and CI
  execute the same set.
- **FR-022**: Historical specification documents under `specs/` MUST NOT be
  rewritten to match the new behaviour. They record what was true when they
  were written; only shipped code, adopter documentation, and gates change.

### Functional Requirements — Direction A (apply the label)

In force: FR-002 resolved to (a).

- **FR-010**: Whenever the pipeline posts a clarification questionnaire to a
  lifecycle issue — the intake decision's clarification-needed arm and the
  clarify stage's `needs-clarification` outcome — the issue MUST carry
  `stage:clarify` by the end of that run.
- **FR-011**: Whenever the pipeline announces that the spec PR is ready for
  review — no open questions remain — the issue MUST NOT carry
  `stage:clarify`, and MUST be left carrying `stage:spec` alone, the single
  stage label the taxonomy documents for a spec awaiting review. Clearing the
  label is therefore a flip back, not a bare removal.
- **FR-012**: While questions are open, the issue's stage labels MUST be
  `stage:clarify` alone: applying it MUST remove `stage:spec`, the way every
  other stage transition flips its predecessor (`plan.yml:1153-1155`). At most
  one `stage:*` label is current at any time, so a maintainer reading the
  issue's labels sees "waiting on an answer" and not "awaiting spec review".
- **FR-013**: The label decision MUST be derived from the same single,
  schema-validated signal that decides which callout to post, not from an
  independently recomputed condition, and MUST NOT depend on agent judgment
  — it is a deterministic workflow step. (`docs/architecture.md:365-367`: the
  structural fix for #159.)
- **FR-014**: The label write MUST be create-before-add, so a consuming
  repository that never created the label is not failed by the step
  (`plan.yml:1151-1153`, SC-002 of the plan-stage spec).
- **FR-015**: A failure to write the label MUST NOT suppress the
  clarification questionnaire, discard pushed agent work, or fail a run whose
  spec commits are already on the branch; it MUST be visible in the run's
  step summary rather than silent.
- **FR-023**: In intake, the flip MUST run after the agent's own `stage:spec`
  application (`intake.yml:711`) and before "Label spec PR to match the issue"
  (`intake.yml:1278`), the step that mirrors the issue's labels onto the spec
  PR, so the PR snapshots the stage it belongs to rather than the one the
  issue just left (`plan.yml:1156-1158` states the same ordering rule for the
  plan PR).

### Functional Requirements — Direction B (retire the label) — NOT TAKEN

FR-002 resolved to (a), so Direction B does not apply. FR-016..FR-020 were
the retirement branch — removing the label from `docs/setup.md`'s table and
creation script, deleting `plan.yml`'s two removal lines and emptying
`clarify.yml:1292`'s `stage-label`, conditionally dropping the clarify
wrapper's `stage:clarify` disjunct, telling adopters they may delete the
label, and letting the FR-007 gate keep the string from returning. They are
retired with the branch and carry no planning or implementation work; the
numbers are left unreused so the citations in this document and in issue #483
still resolve.

### Functional Requirements — end-to-end assertion

- **FR-021**: The end-to-end run's clarification gate MUST start asserting the
  label in this same change, closing the gap
  `specs/055-unattended-e2e-gates/research.md:450-453` records ("the
  clarification gate, which today has no assertion at all"). The assertion
  MUST be conditional on that run's intake having actually posted a
  questionnaire, read from the same clarification-needed signal FR-013 names:
  a zero-question spec never enters the state, and an unconditional assertion
  reproduces the impossible-pass bug `auto-release.yml:1143-1147` records. When
  the condition does not hold, the run MUST pass and MUST say in its step
  summary that the assertion was skipped because no questionnaire was posted —
  a silent skip is indistinguishable from the missing assertion this replaces.

### Key Entities

- **Lifecycle stage label** — a single `stage:*` label on a lifecycle issue
  recording which stage the specification is in. Written by exactly one
  stage, removed by its successor; the taxonomy's contract is that at most
  one is current.
- **Documented label taxonomy** — the table and label-creation script in
  `docs/setup.md` § 4, the adopter's instruction sheet. The authoritative
  list of labels an adopter is asked to create.
- **Applied label set** — the labels some shipped workflow or composite
  action writes via `gh issue edit --add-label`. Today a strict subset of the
  documented taxonomy.
- **Clarification-needed signal** — the single derived output of the intake
  and clarify decision steps that says whether open questions remain; the
  only legitimate input to a `stage:clarify` write (FR-013) and to the
  end-to-end assertion's condition (FR-021).
- **Label exemption registry** — the checked-in record of documented labels
  that deliberately have no workflow writer, each with its reason.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The number of labels in the adopter label taxonomy that no
  workflow applies and that carry no recorded exemption goes from 1 to 0, and
  is held at 0 by a gate.
- **SC-002**: The new gate fails on the pre-change tree and passes on the
  post-change tree, demonstrated by recorded output in the pull request, not
  asserted in prose.
- **SC-003**: One full clarification exchange completes after the change — a
  questionnaire posted, a reply, the answers folded, the spec advanced — with
  no manual label intervention.
- **SC-004**: A maintainer looking only at a lifecycle issue's labels can
  correctly answer "is this spec waiting on me for an answer?" — `stage:clarify`
  present means yes, `stage:spec` means the spec is awaiting review instead,
  and the two never appear together.
- **SC-007**: The end-to-end run's clarification gate reports a definite
  outcome — asserted or explicitly skipped for want of a questionnaire — in
  every run, replacing the zero assertions it makes today.
- **SC-005**: No stage label regresses: for the first full pipeline run after
  the change, every documented stage label the run passes through appears in
  the issue's label timeline, and the end-to-end run's stage-label assertion
  passes without being weakened again.
- **SC-006**: Adopter documentation contains zero statements about
  `stage:clarify` that the shipped code does not implement, verified by
  reading every site listed in FR-006.

## Assumptions

- The three questions above were the only decisions this feature needed from
  the owner, and all three are answered (Clarifications). Everything else
  either was invariant across directions or has a precedent in the repository
  that makes it a mechanical choice.
- The FR-007 gate covers the whole documented lifecycle taxonomy, not just
  `stage:clarify`. Every other documented label already has a writer (see the
  Overview table), so a taxonomy-wide check passes today except for the one
  label under specification — the general rule costs nothing more than the
  specific one and is what keeps the next label honest.
- `stage:stalled` and `spec:NNN-slug` are already documented as created on
  the fly by the pipeline (`docs/setup.md:158-160`) and are applied; they are
  not affected.
- The label writes are ordinary best-effort GitHub API calls in the same class
  as the existing stage flips; no new permission or token scope is needed.
- The end-to-end scratch-repository run remains the only mechanism that
  proves clarify-stage behaviour in Actions; this feature adds no new
  end-to-end harness.
- The intake stage applies `stage:spec` from inside the agent's prompt
  (`intake.yml:711`) rather than from a deterministic step. This feature does
  not change that arrangement; FR-013 constrains only the new label decision.

## Dependencies

- `specs/032-structured-clarification-gate/` — owns the single derived
  clarification signal and `verify-clarification-gating.py` (Gate 8), which
  re-executes the intake and clarify decision shell byte-for-byte. Any change
  inside those steps must keep that contract intact.
- `specs/041-implement-stall-notice/` — owns `wing-commander-chain-stop-notice`
  and the `stage-label` input semantics that `clarify.yml:1292` uses.
- `specs/055-unattended-e2e-gates/` — owns the end-to-end run's gate
  assertions and records the missing clarification assertion FR-021 asks
  about.
- `specs/002-plan-stage/` and `specs/014-configurable-gates/` — own
  `plan.yml`'s stage flip, including the two `stage:clarify` removal lines and
  the create-before-add rule.
- `verify-gate-wiring.py` (Gate 10) and `.github/scripts/run-local-gates.py`
  — the registration surfaces the new gate must satisfy.

## Out of Scope

- Retiring `stage:clarify` from the taxonomy, or restating it as a
  maintainer-applied convenience label — the two directions FR-002 rejected.
- The `spec-request`, `model:*`, `disposition:*`, `board:*` and
  `pipeline-defect` labels. Only the lifecycle `stage:*` taxonomy is under
  specification, though the FR-007 gate may cover any documented label whose
  writer is checkable.
- Changing which stage the clarify exchange belongs to, how questions are
  rendered, how many are allowed, or how answers are folded.
- Moving `stage:spec`'s application out of the intake agent's prompt into a
  deterministic step.
- Rewriting merged specification documents under `specs/` that describe the
  pre-change behaviour.
- Any new end-to-end harness, scratch repository, or additional driven gate
  beyond the conditional clarification assertion FR-021 now requires.
