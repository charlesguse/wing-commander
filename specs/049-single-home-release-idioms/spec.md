# Feature Specification: Single home for the auto-release / auto-update shared idioms

**Feature Branch**: `049-single-home-release-idioms`

**Created**: 2026-09-14

**Status**: Draft

**Input**: User description (GitHub issue #326): "auto-release.yml duplicates auto-update-spec-kit.yml's token-mint, orphan-reset, and failure-issue idioms, and its docs claims drift from the diff"

## Overview

Spec 045's `auto-release.yml` was written by reading `auto-update-spec-kit.yml`
and re-typing three of its hardest-won shell idioms in place. Its own comment
admits it — "same technique as auto-update-spec-kit.yml". CLAUDE.md's "Shared
logic has exactly one home" section exists precisely to stop this, and the
reason it gives is the one that applies here: a pasted copy is invisible until
the first divergent fix.

The three idioms are not boilerplate. Each is a paragraph of shell that encodes
a lesson learned from a specific production failure:

- **The scoped App token mint plus reachability check.** The shared context
  token is scoped to the current repository only, so a second, explicitly
  scoped token is minted for the other repository, allowed to fail
  (`continue-on-error`), and then re-checked by hand so the maintainer gets
  "install the App on that repository" instead of the token action's bare
  "Not Found". `auto-update-spec-kit.yml` learned that on run 31679204393.
- **The orphan-branch force-reset of another repository's default branch.**
  Detach, delete the local branch, `checkout --orphan`, drop the index, delete
  every non-`.git` entry, force-push over a tokenised URL that is immediately
  rewritten out of `.git/config`. Every clause is load-bearing: the detach
  exists because run 31905247552 failed with "a branch named ... already
  exists" the first run after the scaffold first succeeded; the empty-tree
  reset exists so a previous cycle's leftovers cannot satisfy the next cycle's
  assertions; the tokenised URL exists because this is a different repository
  from the one `actions/checkout` credentialed.
- **The durable failure issue keyed on a label.** Create the label idempotently
  (`--force`), look for an open issue carrying it, comment on that issue if one
  exists and create it otherwise, and close it when the condition clears. This
  is what keeps a recurring infrastructure failure to one board item instead of
  one per run.

A divergent fix to any of these has to land twice today, and nothing fails when
only one copy moves.

Inside `auto-release.yml` there is a second, narrower instance of the same
shape: the fail-infra verdict is assembled by hand eleven times from the same
field set (`outcome`, `verified_head`, `failing_check`, `expected`, `observed`,
`evidence_url`) wrapped in the same heredoc. The `poll` step already factored
this into `write_verdict`/`emit_verdict`; the other nine sites did not follow,
so a change to the verdict's shape is an eleven-site edit.

Alongside the duplication, the same PR left two records claiming things that
are not true of the tree: `docs/architecture.md` has no section for
`auto-release.yml` even though every other free-standing pipeline workflow has
one, and `specs/045-auto-release-verified-head/tasks.md` marks T023 ("register
`auto-release.yml` as `shell_exempt` in release.yml's Gate 1a") done when
neither `release.yml` nor `verify-stage-shell-lint.py` was touched. The
registration is not needed — `auto-release.yml` is not a published stage, so
Gate 48 excludes it — so the record should say that rather than claim a change
that does not exist. The finalize narrative repeats the claim and additionally
states "all gate suite checks passing" when CI had failed Gate 12 and then
Gate 15.

This feature gives each idiom exactly one home, puts a gate behind the rule so
the next paste fails CI rather than passing review, and corrects the two
records so they describe the tree that shipped.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A fix to a shared idiom lands once (Priority: P1)

A maintainer discovers that the scoped-token reachability check gives the wrong
remediation when the App is installed but lacks Contents write. They open the
one file that owns that check, fix the message, and both `auto-release.yml` and
`auto-update-spec-kit.yml` pick it up. They do not have to know that a second
copy exists, and they cannot forget it.

**Why this priority**: This is the cost the issue exists to remove. Every other
story either protects this one or cleans up after it. Delivered alone, it takes
the three idioms from two divergent-able copies each to one.

**Independent Test**: Change one observable detail in each shared home — an
error message, a branch-naming rule, a label colour — and confirm that both
workflows' behaviour changes with a single edit and that no second copy of the
changed text remains anywhere under `.github/workflows/`.

**Acceptance Scenarios**:

1. **Given** the scoped-token mint and reachability check now live in one
   shared home, **When** a maintainer edits its "install the App on that
   repository" remediation text, **Then** both `auto-release.yml` and
   `auto-update-spec-kit.yml` emit the edited text, and the old text appears
   nowhere in the repository.
2. **Given** the orphan-branch force-reset now lives in one shared home,
   **When** a maintainer adds a clause to it, **Then** both workflows' reset
   behaviour changes and neither workflow contains its own `checkout --orphan`
   sequence.
3. **Given** the durable failure issue now lives in one shared home, **When**
   a failure fires in either workflow and an open issue already carries the
   configured label, **Then** the failure is added as a comment on that issue
   rather than opening a second one, using the same dedup rule in both
   workflows.
4. **Given** either workflow's call site, **When** the shared home is
   unreachable or never ran, **Then** the call site retains at most a one-line
   fallback, as CLAUDE.md requires, not a re-implementation.

---

### User Story 2 - The next paste fails CI instead of review (Priority: P2)

A future contributor needs a scratch repository in a third workflow and copies
the token-mint block out of one of the two workflows that now consume the
shared home. The gate suite fails on their PR and names the shared home they
should have called, before a reviewer has to notice.

**Why this priority**: CLAUDE.md is explicit that a rule with no gate behind it
lasts until the next session, and this issue is itself the proof — the "shared
logic has exactly one home" rule was written down and then broken by the very
next free-standing workflow. Without this story, story 1's consolidation has a
shelf life.

**Independent Test**: Add a fixture workflow that re-pastes each of the three
idioms, run the gate suite locally, and confirm it fails and names the shared
home; remove the fixture and confirm the suite passes.

**Acceptance Scenarios**:

1. **Given** the gate suite passes on the consolidated tree, **When** a copy of
   any of the three idioms is reintroduced anywhere under `.github/workflows/`
   or `.github/actions/` — including in a workflow that is neither of the two
   known consumers — **Then** the gate suite fails and its message names both
   the offending site and the shared home to call instead.
2. **Given** the gate ships a failure branch, **When** the gate suite runs,
   **Then** that branch is exercised by a checked-in fixture rather than by a
   manual demonstration (constitution VIII).
3. **Given** the gate, **When** it is run from the repository root locally and
   in CI, **Then** it checks the same subject with the same arguments and is
   reachable through the gate registry.
4. **Given** the gate cannot reach its subject — no workflows found, an
   unresolvable shared home — **Then** it fails loudly rather than reporting a
   pass it did not earn.
5. **Given** a third site that genuinely cannot call a shared definition,
   **When** its reason is recorded as a waiver in the gate's waiver file,
   **Then** the gate passes for that site; **When** the same reason is written
   only as a code comment, **Then** the gate still fails.
6. **Given** a `workflow_call` stage workflow or a published composite action,
   **When** it resolves an underscore-prefixed internal helper, **Then** the
   gate fails, so an internal definition cannot enter the adopter-pinned
   surface without a deliberate promotion.

---

### User Story 3 - The fail-infra verdict has one shape (Priority: P3)

A maintainer adds a field to the fail-infra verdict, or fixes how one of its
fields is escaped. They change the one helper that builds the verdict and every
site in `auto-release.yml` that emits one is correct.

**Why this priority**: The blast radius is one workflow rather than two, and
the `poll` step already demonstrates the factored form, so this is finishing a
refactor that was started rather than starting one. Real, but strictly less
costly than the cross-workflow copies.

**Independent Test**: Add a field to the verdict in the single helper and
confirm every emitting site in `auto-release.yml` carries it, with no
hand-built `jq -n` verdict construction left in the workflow.

**Acceptance Scenarios**:

1. **Given** the verdict helper, **When** the verdict's field set changes,
   **Then** exactly one file changes and all eleven former construction sites
   emit the new shape.
2. **Given** `auto-release.yml` after consolidation, **When** the workflow is
   scanned for verdict construction, **Then** no site assembles the verdict's
   fields by hand.
3. **Given** a verdict emitted through the helper, **When** it is read back by
   whatever consumes it today, **Then** the value is byte-identical to what the
   hand-built site produced for the same inputs.

---

### User Story 4 - The records describe the tree that shipped (Priority: P4)

A maintainer reading `docs/architecture.md` to understand the pipeline finds
`auto-release.yml` described in the same place and shape as every other
free-standing workflow. A maintainer auditing spec 045 finds T023 saying what
actually happened, and a finalize narrative that does not claim a green gate
suite that was not green.

**Why this priority**: Documentation drift costs a reader's time rather than a
maintainer's fix, and it costs it later. It is the smallest item here, but it
is the one an adopter hits first.

**Independent Test**: Read `docs/architecture.md` end to end and confirm every
free-standing pipeline workflow has a section before "Reusability"; read
specs/045's T023 and finalize narrative and confirm each claim is checkable
against the merged tree.

**Acceptance Scenarios**:

1. **Given** `docs/architecture.md`, **When** a reader looks for
   `auto-release.yml`, **Then** they find a section for it positioned with the
   other free-standing workflow sections and following their established shape.
2. **Given** specs/045's tasks.md, **When** a reader reads T023, **Then** it
   records that the Gate 1a `shell_exempt` registration is not required
   (`auto-release.yml` is not a published stage, so Gate 48 excludes it),
   rather than claiming a change that is not in the diff.
3. **Given** specs/045's finalize narrative, **When** a reader reads its
   gate-suite claim, **Then** it reflects the actual CI outcome, including the
   Gate 12 and Gate 15 failures, rather than "all gate suite checks passing".

---

### Edge Cases

- **The subject arrived on `main` while this spec was being drafted.** #317
  merged on 2026-09-14, so `auto-release.yml`, spec 045's `tasks.md`, and the
  finalize narrative are all on `main` now, with the duplicated copies present
  there today. This feature is a follow-up against `main`, not a change folded
  into #317; work branched before that merge must rebase onto it before any
  requirement naming `auto-release.yml` can be checked. See FR-021.
- **An internal helper is one promotion away from being a published
  contract.** The three shared definitions live outside the adopter-pinned
  surface, so nothing stops a future `workflow_call` stage or a published
  composite from resolving one and silently making it pinnable. That has to
  fail a check rather than rely on a reviewer noticing. See FR-022 and FR-025.
- **A genuinely new third use of an idiom.** The structural scan sends it to
  the shared definition; where a call site truly cannot use it, the escape is a
  registered waiver in the gate's own waiver file naming the reason — never a
  code comment, and never silence. See FR-023 and FR-026.
- **`auto-update-spec-kit.yml`'s copies are the proven ones.** They have run in
  production; `auto-release.yml`'s have not. Consolidation must not silently
  regress the proven behaviour to match the newer copy where the two differ —
  every divergence between the pair has to be resolved deliberately and
  recorded, not averaged.
- **The two workflows do not want identical behaviour everywhere.** The failure
  issue differs in label, title, and body per call site; the token mint differs
  in which repository it targets; the orphan reset differs in branch name. The
  shared home has to be parameterised for exactly these, and no more.
- **A future workflow legitimately needs one of these idioms.** The gate must
  send it to the shared home, not block the need.
- **The shared home never ran.** Its consumers must degrade the way CLAUDE.md
  prescribes — a one-line fallback at the call site — rather than each
  re-implementing the idiom as a backstop.
- **A verdict field is empty or contains characters that need escaping.** The
  single helper must handle it the way all eleven hand-built sites collectively
  did, and the acceptance test is byte-identity for the same inputs.
- **Spec 045 is closed.** Correcting its `tasks.md` and finalize narrative edits
  the record of a completed feature. The correction states what is true now; it
  does not rewrite history to pretend the claim was never made.

## Requirements *(mandatory)*

### Functional Requirements

**Consolidation**

- **FR-001**: The scoped App token mint for a maintainer-onboarded repository,
  together with its reachability check and actionable remediation message, MUST
  have exactly one definition in the repository.
- **FR-002**: The orphan-branch force-reset of another repository's default
  branch — detach, delete, orphan checkout, index drop, working-tree clear,
  force-push over a tokenised URL that is not left in `.git/config` — MUST have
  exactly one definition in the repository.
- **FR-003**: The durable failure issue keyed on a label — idempotent label
  creation, open-issue lookup by that label, comment-if-exists-else-create, and
  close-on-success — MUST have exactly one definition in the repository.
- **FR-004**: Both `auto-release.yml` and `auto-update-spec-kit.yml` MUST
  consume each shared definition at every site where they use that idiom today
  (three sites in `auto-release.yml`; the scratch-token/resolve pair, the
  scaffold reset, and the four `auto-update:failed` sites in
  `auto-update-spec-kit.yml`).
- **FR-005**: Each shared definition MUST be parameterised for exactly the
  differences its call sites actually have (target repository, branch name,
  label, issue title, issue body, remediation wording) and MUST NOT require a
  caller to pass a parameter no call site varies.
- **FR-006**: Each call site MUST retain at most a one-line fallback for the
  case where the shared definition never ran, and MUST NOT retain a second
  implementation of the idiom as a backstop.
- **FR-007**: Where `auto-release.yml`'s copy and `auto-update-spec-kit.yml`'s
  copy of an idiom differ today, the shared definition MUST adopt a resolution
  chosen deliberately and recorded in the change, and MUST NOT regress the
  behaviour that has run in production.
- **FR-008**: `auto-release.yml`'s fail-infra verdict MUST be constructed
  through a single helper covering all eleven current construction sites,
  including the two the `poll` step already factored.
- **FR-009**: A verdict emitted through the helper MUST be byte-identical to
  what the corresponding hand-built site produced for the same inputs.

**Enforcement**

- **FR-010**: The gate suite MUST fail when any of the three idioms, or the
  fail-infra verdict construction, reappears as a second copy anywhere under
  `.github/workflows/` or `.github/actions/`, whether or not the copying site
  is one of the two known consumers.
- **FR-011**: That gate's failure message MUST name both the offending site and
  the shared definition the author should call instead.
- **FR-012**: The gate MUST be registered in the gate registry and MUST run the
  same subject with the same arguments through `run-local-gates.py` as it does
  in CI (constitution VIII).
- **FR-013**: The gate MUST be triggered by changes to the workflows, shared
  definitions, and waiver file it checks.
- **FR-014**: The gate MUST fail loudly — never report a pass — when it cannot
  reach its subject (no workflows discovered, shared definition missing,
  invoked outside the repository root).
- **FR-015**: Every failure branch the gate ships MUST be exercised by a
  checked-in fixture, not by a manual demonstration.
- **FR-016**: The gate MUST NOT be suppressible by the failure of an unrelated
  gate that shares its job.

**Records**

- **FR-017**: `docs/architecture.md` MUST contain a section for
  `auto-release.yml`, positioned with the other free-standing pipeline workflow
  sections and before "Reusability", following the shape those sections
  establish.
- **FR-018**: `specs/045-auto-release-verified-head/tasks.md` T023 MUST record
  that the Gate 1a `shell_exempt` registration is not required — because
  `auto-release.yml` is not a published stage and Gate 48 therefore excludes it
  — instead of claiming a change absent from the diff.
- **FR-019**: Spec 045's finalize narrative MUST NOT claim a gate-suite outcome
  that CI did not produce, and MUST reflect the Gate 12 and Gate 15 failures
  that occurred.
- **FR-020**: No requirement in this feature may be satisfied by naming a
  private downstream consumer; all shared definitions and their documentation
  stay generic to any adopting repository.

**Sequencing, placement, and surface**

- **FR-021**: This feature MUST land as a follow-up PR against `main`, after
  #317 (merged 2026-09-14), and MUST NOT be folded into #317. Every
  requirement naming `auto-release.yml`, spec 045's `tasks.md`, or spec 045's
  finalize narrative is satisfiable against `main` as it stands, and the record
  corrections of FR-018 and FR-019 land in this feature's own PR.
- **FR-022**: The three shared definitions MUST be composite actions placed in
  an underscore-prefixed internal location under `.github/actions/` — the
  `_shared/` convention, extended from scripts to composite shape — and MUST
  NOT join the adopter-pinned published surface. Composite shape is required
  rather than plain scripts because at least the token mint wraps a `uses:`
  step, which a script cannot express.
- **FR-023**: The single-home gate MUST be a structural scan that fails on a
  re-paste of any of the three idioms, or of the fail-infra verdict
  construction, anywhere under `.github/workflows/` or `.github/actions/` —
  not merely an assertion that the two known consumers call the shared
  definitions, which could not have failed for the case that produced this
  issue.
- **FR-024**: Constitution VII MUST be amended in this feature to state that
  underscore-prefixed directories under `.github/actions/` are internal to this
  repository and are not part of the published, adopter-pinned surface. The
  amendment is a clarification bump carrying the repository's usual Sync Impact
  Report, so the carve-out is a stated rule rather than a remembered one, and
  promoting an internal helper to the published surface later is a deliberate
  minor release rather than a rename.
- **FR-025**: The gate MUST fail when a `workflow_call` stage workflow or a
  published composite action resolves an internal, underscore-prefixed helper,
  so an internal definition cannot become part of the pinned surface by
  accident.
- **FR-026**: A genuinely new third use that cannot call a shared definition
  MUST be expressible as a waiver in a registered waiver file that the gate
  reads, with each waiver naming its reason; the gate MUST NOT honour a waiver
  expressed as a code comment or any other form it does not read.

### Key Entities

- **Shared definition**: the single home for one idiom. Has a name, a
  parameter set covering exactly the variation its call sites need, and one or
  more observable outputs its callers consume.
- **Call site**: a place in a workflow that consumes a shared definition, plus
  at most a one-line fallback for the case where it never ran.
- **Fail-infra verdict**: the record `auto-release.yml` emits when its
  verification cannot be completed, carrying `outcome`, `verified_head`,
  `failing_check`, `expected`, `observed`, and `evidence_url`.
- **Durable failure issue**: at most one open issue per configured label,
  reused by comment while the failure persists and closed when it clears.
- **Single-home gate**: the deterministic check that no second copy of a
  consolidated idiom exists and that no published surface resolves an internal
  helper, with its registry entry and its failure fixtures.
- **Waiver**: a registered entry in the gate's waiver file exempting one named
  site from the single-home rule and stating the reason. Read by the gate, so
  an unlisted exception cannot pass.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Each of the three cross-workflow idioms has exactly one
  definition, down from two, and a change to any one of them requires editing
  exactly one file to take effect in both workflows.
- **SC-002**: The fail-infra verdict is constructed in exactly one place, down
  from eleven, and adding a field to it changes exactly one file.
- **SC-003**: Reintroducing a copy of any consolidated idiom anywhere under
  `.github/workflows/` or `.github/actions/` — including at a site that is
  neither known consumer — causes the local gate suite and CI to fail, with the
  message naming the shared definition to call instead; this is demonstrated by
  a checked-in fixture rather than a manual run.
- **SC-004**: `run-local-gates.py` passes on the consolidated tree, and every
  gate it runs is reachable from the gate registry.
- **SC-005**: Both workflows behave the same before and after consolidation for
  every path that has run in production, with any deliberate divergence
  recorded in the change.
- **SC-006**: Every free-standing pipeline workflow, `auto-release.yml`
  included, has a section in `docs/architecture.md` before "Reusability".
- **SC-007**: Every completion claim in spec 045's tasks.md and finalize
  narrative is checkable against the merged tree, with zero claims of changes
  that are not in the diff and zero claims of a CI outcome that did not occur.
- **SC-008**: The adopter-pinned surface is unchanged by this feature: the set
  of published composite actions an adopter can pin is the same before and
  after, the three shared definitions sit outside it, and a stage or published
  composite that resolves one fails the gate.
- **SC-009**: Every exception to the single-home rule is discoverable in one
  place — the gate's waiver file — with a reason attached, and no exception is
  carried by a code comment.

## Dependencies

- **Cleared**: #317 merged on 2026-09-14, putting `auto-release.yml`, spec
  045's `tasks.md`, and the finalize narrative on `main`. FR-001 through FR-009
  and FR-017 through FR-019 are satisfiable against `main` today; this feature
  is a follow-up PR, not a change folded into #317 (FR-021). Work branched
  before that merge rebases onto it first.
- Constitution VII is amended by this feature (FR-024), so the change carries a
  Sync Impact Report in `.specify/memory/constitution.md`.
- `auto-update-spec-kit.yml`'s copies of all three idioms are the production-proven
  ones and are the reference behaviour for FR-007.
- The existing gate registry, `run-local-gates.py`, and `lint-workflows.yml`
  are the integration points for FR-010 through FR-016.
- Gate 47 (`verify-comment-canonical-pointers.py`) is the existing gate behind
  CLAUDE.md's "Shared logic has exactly one home" section and is the nearest
  prior art for the new check; `verify-metrics-summary-record-emission.py` is
  the prior art for a gate that fails when a consolidated formatter reappears
  in a workflow.

## Assumptions

- The durable-failure-issue definition covers close-on-success as well as
  create-or-comment, since both workflows need both halves and splitting them
  would leave half the idiom duplicated.
- The three shared definitions are separate from one another; a caller that
  needs only the token mint is not forced to adopt the reset or the failure
  issue.
- Consolidation is behaviour-preserving by default. This feature is not a
  licence to improve either idiom; improvements found along the way become
  their own issues rather than widening this change.
- The verdict helper stays internal to `auto-release.yml`'s needs. No other
  workflow emits this verdict today, so it is not generalised speculatively.
- The Constitution VII amendment (FR-024) is a clarification of the existing
  two-interface split rather than a new principle: it names where the boundary
  already sits for underscore-prefixed directories, so it is a clarification
  bump and does not retire or redefine any other principle.
- No adopter pins an underscore-prefixed path under `.github/actions/` today,
  so declaring that namespace internal removes nothing from the published
  surface.
- The `auto-update-spec-kit.yml` sites that already reuse
  `wing-commander-callout` for the failure comment keep doing so; FR-003 covers
  the label/lookup/create/close machinery, not the comment rendering.
- The architecture.md section for `auto-release.yml` matches the depth of the
  Auto-Update Spec Kit and private-image-dogfood sections rather than the depth
  of the published-stage sections.
- FR-017 is a one-off correction: the issue asks for the missing section, not
  for a gate asserting that every free-standing workflow has one. Gating the
  documentation-drift class is a separate, larger change and is out of scope
  here.
- Correcting spec 045's records is a forward correction. It does not touch the
  merged commit history of #317.
- This repository is public, so no shared definition, comment, or document
  added here names a private downstream consumer.
