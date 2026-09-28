# Feature Specification: The Worked Example Outlives Its Code — Keeping spec-cross-reference's Structural Claim True

**Feature Branch**: `spec-draft/089-skill-example-drift`

**Created**: 2026-09-28

**Status**: Draft

**Input**: Lifecycle issue [#658](https://github.com/charlesguse/wing-commander/issues/658) — "spec-cross-reference skill still describes the board loop's replaced workflow-level concurrency block" (routed from the board loop, originating issue #486, found by the implement stage of spec 060)

## Overview

The `spec-cross-reference` skill exists to stop a review from rating a
finding by code shape alone. It teaches two failure directions with two
worked examples. The **Over-rated** one is the load-bearing half: a
hypothesized race (two board-loop cycles landing two PRs for the same
issue) looks plausible in isolation, and the skill shows how a structural
guarantee in the spec — FR-048's concurrency group — refutes it
(`.claude/skills/spec-cross-reference/SKILL.md:23-28`):

> FR-048's own concurrency group (`group: wing-commander-board-loop`, one
> item in flight repository-wide, applied to every trigger in the file)
> rules the race out structurally.

That sentence is a quote of another file's content. The skill does not own
`.github/workflows/board-loop.yml`, and nothing in the repository fails
when the two disagree.

## What the originating report got wrong, and what it got right

The report claims spec 060's per-job concurrency split "replaced" the
workflow-level block, and that `board-loop.yml` "now carries eight per-job
`concurrency:` blocks". **That is false against current `main`.**
`.github/workflows/board-loop.yml:40-46` still carries exactly one
workflow-level block:

```
concurrency:
  # One board item in flight repository-wide (FR-048): a second scheduled
  # or dispatched run queues behind an in-flight one rather than racing or
  # cancelling it. Never loosen this without re-establishing that guarantee
  # some other way.
  group: wing-commander-board-loop
  cancel-in-progress: false
```

`specs/060-self-redrive-concurrency/spec-meta.json` records
`"stage": "spec"` — spec 060 has not reached implement, let alone merged.
Editing the skill today to describe per-job groups would *introduce* the
defect the report describes rather than remove it.

What the report gets right is the exposure underneath it. Spec 060's entire
deadlock analysis rests on that block being workflow-level ("`board-loop.yml`'s
concurrency block is **workflow-level**, so it applies uniformly across every
trigger of that one file"), and its whole purpose is to change how the
re-drive path interacts with it. The skill's example is therefore one merge
away from being wrong, in a file that is currently scheduled to change, with
no mechanism that will say so.

## Why a stale example here is worse than an ordinary stale comment

The skill's job is to *downgrade* findings. Its Over-rated example is a
template for saying "this race cannot happen." When the quoted guarantee no
longer holds, a reviewer following the template refutes a **real** race by
citing a rule the workflow does not have — and says so in the report with
the confidence of a named requirement behind it. The failure is silent, it
points the wrong way, and it lands on exactly the concurrency-shaped
findings a per-job split would make newly possible.

The skill already anticipates this class of error for *specs* — Procedure
step 2 tells a reviewer that "a spec bullet asserting a guarantee ... is a
claim about the code, not proof of it" and to read the actual file before
letting it downgrade a finding. It does not apply that instruction to its
own worked example, which is the one structural claim a reader is least
likely to re-check.

Issue #658 is itself the second failure direction of the same gap: an agent
read the skill, could not tell from it whether the quoted claim was current
or historical, and filed a defect asserting a workflow shape that does not
exist. A claim that cannot be dated cannot be triaged.

## Scope

In scope: the durability of the single structural claim the
`spec-cross-reference` skill makes about a file it does not own — the
Over-rated example's assertion about `board-loop.yml`'s concurrency
configuration — and a blocking gate that owns it.

Out of scope: changing `board-loop.yml`'s concurrency configuration, and
deciding spec 060's design. This feature must follow the workflow, never
anticipate it. Also out of scope: generalizing the rule to every skill
document. The two other review skills, `review-step-gating` and
`container-shell-safety`, name workflow files only as example command
arguments, never as load-bearing assertions about their content, so there
is nothing for a registry to hold; building one, or recording an intent to
cover examples that do not exist, would add weight nothing acts on.

## Clarifications

### Session 2026-09-28

- Q: Which remedy shape — remove the file-specific detail so there is
  nothing to drift, keep the concrete quote and gate it against the
  workflow, or restate the example as dated history plus a reader
  instruction? → A: Keep the concrete quote and add a gate. CLAUDE.md says
  a rule with no gate behind it lasts until the next session, and the
  constitution treats a check that cannot fail as a liability; the
  reader-instruction option leaves the claim unenforced, and dropping the
  detail throws away the concreteness FR-005 exists to protect. The
  accepted cost is a gate that has to read two files' shapes rather than
  compare two strings. (FR-002, FR-005, FR-012)
- Q: Should a drift failure block the PR that changes `board-loop.yml`, or
  be advisory so a concurrency change is never held up by a doc edit? → A:
  Blocking, with a waiver file on the existing `*-waivers.json` precedent
  (single-home, stage-invariant, spec-branch-push). A PR that outdates the
  example — spec 060's, for instance — lands with a waiver entry while a
  human session updates the skill, because the implement stage agent cannot
  write under `.claude/` (#489, #675). The accepted cost is a second
  tracked file whose entries must themselves be stale-checked so a waiver
  cannot become a permanent exemption. (FR-010, FR-013, FR-014, SC-001,
  SC-007)
- Q: Does the rule bind this one `board-loop.yml` claim, or every
  structural quote in every skill document? → A: The one example that
  exists today. No registry, and no recorded intent to cover future
  examples — recording intent that nothing acts on only adds weight to the
  system. A second quoted example gets the gate extended when it appears.
  The accepted cost is that a future skill author quoting a workflow fact
  is not obliged by anything to register it. (FR-011)

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The reviewer refutes a race with a rule that still exists (Priority: P1)

A code review surfaces a concurrency-shaped finding against the board loop.
The reviewer invokes `spec-cross-reference`, reaches the Over-rated
example, and decides whether the loop's concurrency guarantee rules the
finding out. The verdict they reach matches what `board-loop.yml` says on
the branch under review — whether that is one workflow-level group, several
per-job groups, or none.

**Why this priority**: This is the skill's whole purpose. A wrong refusal
here is a real defect shipped with a citation attached, which is harder to
undo than an unrated finding.

**Independent Test**: Take the skill as written, a finding that depends on
the loop's concurrency, and two variants of `board-loop.yml` — the current
workflow-level block and a per-job split. Following the skill produces the
correct verdict in both cases without the reviewer needing prior knowledge
of which variant is checked out.

**Acceptance Scenarios**:

1. **Given** `board-loop.yml` as it stands on `main` (one workflow-level
   group, `cancel-in-progress: false`), **When** a reviewer follows the
   Over-rated example against a two-cycles-race finding, **Then** the
   finding is refuted and the report quotes a guarantee that is present in
   the file.
2. **Given** a branch where the workflow-level block has been replaced by
   per-job groups, **When** the same reviewer follows the same example,
   **Then** they do not refute the finding on the strength of a
   repository-wide group, and the skill itself is what tells them the
   example's premise no longer holds.
3. **Given** a finding about some other subject entirely, **When** the
   reviewer reads the Over-rated example, **Then** they still take away the
   transferable lesson (a structural guarantee can refute a plausible race)
   without having to trust the specific concurrency detail.

---

### User Story 2 - Changing the workflow surfaces the doc it invalidates (Priority: P2)

A maintainer (or the implement stage of spec 060) changes
`board-loop.yml`'s concurrency configuration. Before that change can merge,
the repository tells them the skill's quoted claim no longer matches, and
names both lines.

**Why this priority**: This is what converts the rule into something that
survives the next session. Per CLAUDE.md, a rule with no gate behind it
lasts until the next session — and the change that will break this one is
already specified.

**Independent Test**: Mutate `board-loop.yml`'s concurrency block in a
working tree, run the repository's local gate suite, and observe a failure
that names the skill line and the workflow line that disagree.

**Acceptance Scenarios**:

1. **Given** a branch that replaces the workflow-level concurrency block
   with per-job groups and leaves the skill untouched, **When** the PR-time
   gate suite runs, **Then** it fails with a message naming both the skill
   location and the workflow location.
2. **Given** the same branch with the skill updated to match, **When** the
   suite runs, **Then** it passes.
3. **Given** a branch that touches neither file, **When** the suite runs,
   **Then** the check adds no failure and no manual step.
4. **Given** a branch that changes the concurrency block and cannot touch
   `.claude/` (an implement-stage PR), **When** it records a waiver entry
   naming the reason and the tracking issue, **Then** the suite passes and
   the branch merges with the divergence in the open rather than hidden.
5. **Given** that waiver still recorded after a later session brings the
   skill back into agreement, **When** the suite runs, **Then** it fails on
   the stale waiver, so the exemption cannot outlive the update it was
   waiting on.

---

### User Story 3 - A triager can date the claim (Priority: P3)

Someone meets a report like #658 — "the skill describes a configuration the
workflow no longer has". They determine in one command whether the skill is
stale or the reporter misread the tree, and close or fix accordingly.

**Why this priority**: The originating issue cost a triage, a route, and an
intake run to establish a fact that should have been one command. It will
recur every time spec 060 is discussed.

**Independent Test**: Given only the skill and the repository, produce a
yes/no answer to "is this claim currently true?" without reading spec 060
or the issue history.

**Acceptance Scenarios**:

1. **Given** the skill as shipped, **When** a triager asks whether its
   concurrency claim matches the tree, **Then** the skill itself points at
   the check or the file that answers it, and the answer needs no
   familiarity with spec 060.
2. **Given** a report asserting the skill is stale, **When** the claim is
   in fact current, **Then** the triager can quote the mechanical evidence
   that refutes the report, in the form this repository's triage rule
   already expects.

---

### Edge Cases

- **`board-loop.yml` is renamed or split.** The quoted subject disappears
  entirely rather than changing shape. The check must fail loudly (subject
  missing) rather than silently passing on a file it can no longer find.
- **The block moves to per-job groups with several different group names**
  (spec 060's likely shape). No single "repository-wide" group exists to
  quote; the skill's claim is not merely outdated but no longer
  expressible in its current form.
- **FR-048 itself is reworded or renumbered in spec 057.** The skill quotes
  a requirement identifier as well as a workflow fact; both can drift, and
  the spec text is the one the skill treats as authoritative.
- **The nested `.wing-commander-pipeline/` checkout carries its own copy of
  the skill.** It is an untracked, gitignored checkout, already excluded
  from this repository's sweeps; the check must not treat it as a subject
  or as a second home to keep in sync.
- **A PR changes the skill's wording but not its meaning** (reflow,
  typo fix). The check must not fail on formatting alone, or it becomes
  the kind of gate people route around.
- **The concurrency block keeps its group name but flips
  `cancel-in-progress` to `true`.** The group still exists, so a name-only
  comparison passes, yet "queues rather than cancelling" — the property the
  refutation actually leans on — is gone.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The `spec-cross-reference` skill MUST NOT leave a reader
  believing a concurrency guarantee holds in `board-loop.yml` unless that
  belief is true of the file on the branch being reviewed.

- **FR-002**: Every structural claim the skill makes about a file it does
  not own MUST have a mechanical owner — something in the PR-time gate
  suite that fails when the claim and the quoted file diverge — rather than
  depending on a future reader noticing. The remedy is a **gate over the
  concrete quote**: the Over-rated example keeps its specific claim about
  `board-loop.yml`, and a check compares that claim against the workflow.
  De-concretizing the example, or relying on an instruction to the reader
  alone, is not sufficient — a rule with no gate behind it lasts until the
  next session, and a check that cannot fail is a liability.

- **FR-003**: The skill MUST apply to its own worked example the same force
  its Procedure step 2 already applies to claims a *spec* makes — a reader
  arriving at the Over-rated example MUST be told to confirm the guarantee
  against the live file before letting it downgrade a finding.

- **FR-004**: The change MUST follow the code, not anticipate it. While
  `main` carries the single workflow-level block at
  `.github/workflows/board-loop.yml:40-46`, the skill MUST NOT be edited to
  describe per-job concurrency groups, and MUST NOT be written as though
  spec 060 had landed.

- **FR-005**: The skill MUST remain a concrete, checkable illustration — a
  named requirement plus the specific structural guarantee that refuted a
  specific finding — and MUST NOT be reduced to a generic statement that
  structural guarantees can refute findings. The teaching value is the
  concreteness.

- **FR-006**: Any check introduced MUST name, in its failure message, both
  the skill location and the workflow location that disagree, so the fixer
  does not have to rediscover the pairing.

- **FR-007**: Any check introduced MUST be able to fail on its subject: a
  deliberate mutation of either the skill's claim or the workflow's
  concurrency configuration MUST produce a failure, demonstrated the way
  this repository's existing self-testing gates demonstrate it.

- **FR-008**: The skill MUST make the currency of its structural claim
  legible to a reader who has no history with spec 060 — a triager meeting
  a "this is stale" report MUST be able to settle it from the skill and the
  tree alone.

- **FR-009**: The check MUST NOT fire on wording changes that leave the
  claim's meaning intact, and MUST NOT treat the untracked
  `.wing-commander-pipeline/` copy of the skill as a subject.

- **FR-010**: The enforcement MUST be registered with the repository's
  existing PR-time gate suite so it runs from
  `python .github/scripts/run-local-gates.py` and in CI by the same
  derivation, with no separate invocation to remember. A drift failure is
  **blocking**: the PR that changes `board-loop.yml` does not merge while
  the skill still describes the previous shape. It is not advisory.

- **FR-011**: The rule binds **only this one claim** — the
  `spec-cross-reference` Over-rated example's assertion about
  `board-loop.yml`'s concurrency configuration. The feature MUST NOT build
  a registry covering every structural quote in `.claude/skills/**`, and
  MUST NOT record an intent to cover future examples that nothing acts on.
  If a second load-bearing structural quote appears in a skill document
  later, the gate is extended then.

- **FR-012**: The comparison MUST cover the properties the refutation
  actually leans on, not merely the group's name: that the concurrency
  block is workflow-level (so it applies to every trigger in the file),
  that its group is repository-wide, and that a second run queues rather
  than cancelling (`cancel-in-progress: false`). A change that keeps the
  group name while dropping any of these MUST fail the check.

- **FR-013**: A PR that outdates the example MUST be able to land behind a
  recorded waiver rather than being stuck, because the implement stage
  agent cannot write under `.claude/` (issues #489, #675) and so cannot fix
  the skill in the same PR. The waiver MUST follow this repository's
  existing `*-waivers.json` precedent
  (`single-home-waivers.json`, `stage-invariant-waivers.json`,
  `spec-branch-push-waivers.json`): one tracked file, each entry carrying a
  reason and a tracking issue, in the open rather than as a name missing
  from a list.

- **FR-014**: Waiver entries MUST be stale-checked in both directions, the
  way the existing waiver files are: an entry whose subject no longer
  diverges MUST fail the gate, so a waiver cannot outlive the update it was
  waiting on. Waiving MUST therefore be a temporary state that a later
  human session closes out, never a permanent exemption.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A change to `board-loop.yml`'s concurrency configuration
  cannot reach `main` with the skill silently still describing the previous
  shape — the divergence is surfaced by the gate suite before merge, in
  100% of cases, rather than by a reader. The only path past it is a
  recorded waiver entry naming a tracking issue, which the gate itself
  removes the cover for once the skill is updated.

- **SC-002**: A reviewer invoking the skill against a concurrency-shaped
  finding reaches the verdict that matches the branch under review, with
  zero steps that require remembering the workflow's prior shape.

- **SC-003**: Every structural claim remaining in the skill is either
  confirmable against the tracked tree in a single command, or explicitly
  marked as historical — no claim in the skill is both current-sounding and
  unverifiable.

- **SC-004**: A triager can settle a "the skill is stale" report in one
  command, with no reading of spec 060, the issue history, or the board
  loop's commit log.

- **SC-005**: The full local gate suite passes on the change, and a
  deliberately mutated copy of either subject file fails it — both
  demonstrated, not asserted.

- **SC-006**: No copy of the skill's structural claim exists in more than
  one tracked location; the claim has exactly one home, consistent with the
  repository's single-home rule.

- **SC-007**: A PR that changes `board-loop.yml`'s concurrency block can
  still merge without a `.claude/` edit by recording one waiver entry, and
  that same entry fails the gate once the skill is brought back into
  agreement — both demonstrated, so the waiver is provably temporary.

## Assumptions

- The workflow-level concurrency block at
  `.github/workflows/board-loop.yml:40-46` is the state of `main` as of
  2026-09-28, and spec 060 (`stage: spec`, unmerged) is the change expected
  to alter it. This spec does not depend on spec 060 landing, and does not
  block on it.
- FR-048 of spec 057 ("The loop MUST run under a global concurrency group:
  one item in flight repository-wide, with a second run queuing rather than
  cancelling or racing") is the requirement the skill's example cites, and
  it remains the governing requirement unless spec 060 supersedes it.
- `review-step-gating` and `container-shell-safety` reference workflow files
  only as example command arguments and carry no load-bearing assertion
  about another file's content, so they need no remediation today, and
  FR-011 leaves them unbound going forward. The gate covers the one claim
  that exists; a second one gets the gate extended when it appears.
- The remedy is a documentation-and-gate change; no workflow behaviour, no
  agent prompt, and no pipeline stage contract changes as part of it.
- The originating report's factual claim about eight per-job blocks is a
  misreading, not evidence of an unmerged change having landed; the record
  of that belongs on issue #658, not in the skill.
