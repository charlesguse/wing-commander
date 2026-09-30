# Feature Specification: The Evidence Gate's Comment Names Its Real Counterpart

**Feature Branch**: `120-evidence-gate-comment`

**Created**: 2026-09-30

**Status**: Draft

**Input**: User description: "fix(watchdog): correct evidence-gate comment about the per-class key list — the comment above the evidence-validity gate's per-class required-key list claims it is 'the same per-class required-key list the fingerprint step below projects to' and that the two are 'kept in agreement deliberately'. That has been false since spec 024: `Compute fingerprint` only hashes the finding's class plus its cited signal ids, and the actual per-class projection lives in `Stamp signal ids` in the `collect` job. Several classes disagree with that projection — e.g. `turn-budget-trend` requires `stage/expected/actual` here but `Stamp signal ids` projects it to `stage/band`. Reword the comment to name `Stamp signal ids` as the projection's actual home and clarify that this list only checks that a Finding is grounded in its class's facts, not that it agrees with the fingerprint's projection. No behaviour change."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A maintainer reading the gate is told the truth about it (Priority: P1)

A maintainer opens the watchdog's evidence-validity gate to answer a
question about why a finding was suppressed, or to change the key list for
one class. The comment directly above the list tells them the list mirrors
what the fingerprint step below projects to, and that the two are kept in
agreement on purpose. Acting on that, the maintainer either believes a
change here must be mirrored below (it must not — there is nothing below to
mirror), or believes the two lists already agree and reasons about
fingerprint stability from the wrong list.

After this feature, the comment states what the list actually does — check
that a Finding of this class is grounded in the facts that class is
expected to carry — and names the step that really does project per-class
identity, so a maintainer arriving at either site is pointed at the other
for the right reason.

**Why this priority**: This is the reported defect, and the comment is the
only documentation at the point of use. A load-bearing comment that
misdirects is worse than no comment: it survives review because it reads as
settled prior reasoning.

**Independent Test**: Read the comment against the two steps it describes.
It passes if every claim it makes about the fingerprint step and about the
identity projection is true of the current file, and if a reader following
it lands on the step that actually performs a per-class projection.

**Acceptance Scenarios**:

1. **Given** the corrected comment, **When** a maintainer reads it and then
   reads the fingerprint step below, **Then** nothing the comment claims
   about that step is contradicted by it — in particular the comment does
   not claim the fingerprint step projects per class or carries a key list.
2. **Given** the corrected comment, **When** a maintainer looks for where
   per-class identity projection actually happens, **Then** the comment
   names that step, and that step exists in the file under that name.
3. **Given** the corrected comment, **When** a maintainer compares the
   gate's key list for a class against that step's projection for the
   corresponding signal kind and finds them different, **Then** the comment
   has already told them the two are allowed to differ and why, so the
   difference is not read as a bug.

---

### User Story 2 - The gate keeps behaving exactly as it did (Priority: P1)

The watchdog files, suppresses and dedups findings on a schedule. A comment
correction must not move any of those outcomes.

**Why this priority**: Equal in priority to Story 1 because it bounds it.
The repository's fingerprints are durable state — a changed fingerprint
splits a finding's accumulated issue — so a documentation fix that quietly
changed the key list, the suppression reason strings, or the fingerprint
basis would be a far larger change than the one requested.

**Independent Test**: Compare the gate's executable content before and
after. It passes if the class-to-key-list mapping, the suppression
conditions, the emitted reason text and every step output are unchanged.

**Acceptance Scenarios**:

1. **Given** the corrected file, **When** the evidence-validity gate runs on
   a Finding that was suppressed before the change, **Then** it is still
   suppressed, for the same recorded reason.
2. **Given** the corrected file, **When** a Finding that passed the gate
   before the change reaches the fingerprint step, **Then** it produces the
   same fingerprint it produced before.

---

### User Story 3 - The correction does not drift back (Priority: P2)

The claim being corrected was true when it was written and was falsified by
a later change to a different step. Nothing failed when that happened; the
comment simply went stale and stayed stale across every subsequent review of
the file.

**Why this priority**: Lower than P1 because the immediate misdirection is
gone once Story 1 lands, and because the repository's convention that a rule
without a gate behind it does not survive is a convention about durability,
not about correctness today.

**Independent Test**: Introduce, in a checked-in fixture, a copy of the
comment that reasserts the stale claim, and confirm the repository's gate
suite reports it.

**Acceptance Scenarios**:

1. **Given** the check this feature adds (see Q1), **When** a future change
   makes the comment claim again that the fingerprint step carries or
   projects to a per-class key list, **Then** the gate suite fails and names
   the comment.
2. **Given** that check, **When** the comment is correct, **Then** the gate
   suite passes and the check reports what it examined rather than passing
   silently on an unreachable subject.

---

### Edge Cases

- The comment is rewritten while the step it points at is renamed in the
  same change: the pointer must name a step that exists, so the check
  backing it must resolve the named step in the file rather than matching
  the name as free text.
- A future change legitimately reintroduces a per-class projection into the
  fingerprint step: the correction must not be written so that restoring
  that relationship is impossible to describe — it records what is true
  today, with the reason, not a prohibition.
- The gate's key list and the identity projection are keyed on different
  things (a Finding's class versus a signal's kind), so for some classes
  there is no corresponding projection entry at all. The comment must not
  imply a one-to-one correspondence that does not exist.
- Sibling comments elsewhere in the same file that describe the fingerprint
  basis were checked and are accurate; the correction is confined to the one
  stale site (see Assumptions).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The comment above the evidence-validity gate's per-class
  required-key list MUST NOT claim that the fingerprint step carries,
  projects to, or is kept in agreement with a per-class key list.
- **FR-002**: The comment MUST state what the key list actually enforces:
  that a Finding of a given class is grounded in the facts that class is
  expected to carry.
- **FR-003**: The comment MUST name the step where per-class identity
  projection actually happens (`Stamp signal ids`, in the collect job), so a
  reader can reach it from here.
- **FR-004**: The comment MUST state that the gate's key list and that
  step's projection answer different questions and are therefore permitted
  to differ, rather than leaving a difference to read as a defect.
- **FR-005**: The class-to-key-list mapping itself MUST be unchanged by this
  feature — same classes, same keys, same order-independent contents.
- **FR-006**: The gate's suppression conditions, its emitted reason strings,
  and its step outputs MUST be unchanged by this feature.
- **FR-007**: The fingerprint a given Finding produces MUST be unchanged by
  this feature, so no existing accumulating finding is split onto a new
  issue.
- **FR-008**: The correction MUST be confined to the single stale comment
  site; other comments in the same file that describe the fingerprint basis
  are out of scope unless they are found to assert the same falsified claim.
- **FR-009**: The repository's full gate suite MUST pass on the change,
  including the gates that byte-compare or mutate workflow comments.
- **FR-010**: [NEEDS CLARIFICATION: Q1 — does this feature also add a
  deterministic check that fails if the comment reasserts the falsified
  claim, or does it stop at the correction? See Clarifications.]
- **FR-011**: [NEEDS CLARIFICATION: Q2 — is the divergence between the
  gate's per-class key list and the collector-side projection recorded as a
  separate board item for review, or accepted as correct-by-design and
  closed out by this comment alone? See Clarifications.]

### Key Entities

- **Evidence-validity gate**: the step that decides whether a Finding is
  grounded enough to file — it requires at least one resolvable cited signal
  id, and, per class, a fixed list of non-empty normalized facts.
- **Per-class required-key list**: the class-to-keys mapping inside that
  gate. Keyed by the Finding's *class*, read against the Finding's
  *normalized facts*.
- **Identity projection**: the source-kind-to-identifying-facts mapping in
  `Stamp signal ids`. Keyed by a *signal's* source/kind, read against the
  *collector's* facts, and hashed into the signal id.
- **Fingerprint basis**: since spec 024, the Finding's class plus the sorted,
  deduplicated ids of the signals it cites — no per-class key projection of
  its own.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Every factual claim the corrected comment makes about another
  step in the file is verifiable against that step as it exists on main —
  zero claims that the file contradicts.
- **SC-002**: A maintainer who reads only the corrected comment can name the
  step that performs per-class identity projection, on the first read,
  without searching the file.
- **SC-003**: Zero executable lines of the evidence-validity gate change:
  the diff for this feature touches comment lines only (plus whatever check
  Q1 resolves to).
- **SC-004**: For a fixed set of recorded example Findings, the suppression
  decision, the suppression reason and the fingerprint are identical before
  and after the change — zero differences.
- **SC-005**: The repository's full gate suite passes on the change.
- **SC-006**: If Q1 resolves to adding a check, a fixture that reasserts the
  falsified claim fails that check — demonstrating the check can fail its
  own subject rather than reporting an unearned pass.

## Clarifications

### Open questions for this session

- **Q1 — Does a gate back the corrected comment?** The repository's
  convention is that a rule with no gate behind it lasts until the next
  session, and this comment is the worked example: it was true when written
  and was falsified silently by a change elsewhere. A check that fails when
  the comment reasserts the falsified claim would have caught that. Against
  it: the check's subject is prose, so it can only match on phrasing, and a
  brittle phrase-match is its own maintenance burden.
- **Q2 — Is the underlying divergence a separate item?** The gate requires
  `stage`/`expected`/`actual` for `turn-budget-trend`, while the collector
  for that signal emits `stage`, `band`, window size and history — no
  `expected` or `actual`. The two lists read different objects (the agent's
  normalized facts versus the collector's facts), so the divergence is not
  automatically wrong, but whether the required keys for that class are the
  right ones is a behaviour question this comment correction deliberately
  does not answer.

## Assumptions

- The corrected comment is the only site asserting the falsified claim. The
  two other comments in the same file that describe the fingerprint basis
  were read and are accurate as written, so they are left alone.
- "No behaviour change" is the binding constraint: where a wording choice
  and a behaviour change both satisfy a requirement, the wording choice is
  taken and the behaviour question is deferred to Q2.
- The gate's key list being keyed on the Finding's class, while the identity
  projection is keyed on a signal's source/kind, is intentional and stays
  that way — the two are not converging as part of this feature.
- Workflow comments in this repository are load-bearing (gates byte-compare
  and mutate them), so this change is treated as a code change and re-runs
  the full gate suite rather than being waved through as documentation.
- Spec 024 is the change that falsified the claim; it is cited as the reason
  the comment went stale, not reopened or amended by this feature.
