# Feature Specification: Rename to Wing Commander

**Feature Branch**: `012-rename-wing-commander`

**Created**: 2026-07-15

**Status**: Draft

**Input**: User description: "Please rename the app. While this uses speckit, I don't want to tie the name so closely to it as I am in no way associated with the creators of Speckit."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Product presents itself as "Wing Commander" (Priority: P1)

Anyone who encounters the project — a first-time reader of the repository landing
page, a maintainer reading documentation, or a person watching the pipeline run on
their issue — should see it named and described as "Wing Commander," not as a
"speckit" product. The project may still accurately state that it is *built on* the
third-party Spec Kit tool, but its own identity is Wing Commander.

**Why this priority**: This is the entire request. The owner does not want the
product's name to imply an association with the creators of Spec Kit. Every other
story is a supporting slice of this one outcome.

**Independent Test**: Read the primary README and the pipeline's user-facing status
comments/PR titles; confirm the product is named "Wing Commander" and that no text
presents "speckit" as the product's own name (references to Spec Kit as an
underlying dependency are acceptable and clearly framed as attribution).

**Acceptance Scenarios**:

1. **Given** a new visitor opens the repository README, **When** they read the
   title and opening description, **Then** the product is identified as "Wing
   Commander" and any mention of Spec Kit is framed as an underlying tool, not as
   the product's name.
2. **Given** the pipeline runs on a lifecycle issue, **When** it posts status
   comments and opens pull requests, **Then** the human-facing text refers to the
   product as "Wing Commander."
3. **Given** a reader browses the documentation, **When** they look for the product
   name, **Then** it is consistently "Wing Commander" with no leftover branding that
   names the product "speckit-action" / "speckit pipeline."

---

### User Story 2 - No broken references after the rename (Priority: P1)

After the rename, the pipeline must still function end-to-end and downstream
consumers that depend on the project must not silently break. Whatever is renamed
must be renamed consistently everywhere it is referenced, and anything that would
break an external consumer must either be preserved or its removal called out
explicitly.

**Why this priority**: A rename that leaves dangling references — a workflow that
calls a renamed file, a label that no longer matches, a consumer pinned to an old
action path — turns a cosmetic change into an outage. Correctness is as critical as
the rename itself.

**Independent Test**: Run (or dry-run) the full pipeline on a sample issue after the
rename and confirm every stage triggers, references resolve, and no step fails due
to a name that was changed in one place but not another.

**Acceptance Scenarios**:

1. **Given** the rename is applied, **When** the pipeline executes each stage, **Then**
   every internal reference to a renamed file, label, action, or identifier resolves
   successfully.
2. **Given** an external repository consumes this project (e.g., pins a reusable
   workflow or a published action), **When** the rename changes a name that consumer
   depends on, **Then** the change is either backward-compatible or the breaking
   change is explicitly documented for consumers.
3. **Given** the rename is complete, **When** the repository is searched for the old
   product branding used as the product's own name, **Then** no unintended
   occurrences remain (excluding deliberate attribution to the Spec Kit dependency).

---

### User Story 3 - Attribution to Spec Kit remains accurate (Priority: P2)

The project genuinely runs on Spec Kit, and the owner explicitly acknowledges this
("while this uses speckit"). The rename must not delete or obscure honest
attribution to the underlying tool; it must only stop presenting "speckit" as the
product's own name.

**Why this priority**: Honesty about dependencies is valuable and the owner is not
asking to hide the relationship — only to avoid implying an association with Spec
Kit's creators. This guards against over-correcting the rename into erasing
legitimate, accurate references.

**Independent Test**: Confirm the documentation still explains that Wing Commander is
built on Spec Kit and Claude Code, framed as tools it uses rather than as its brand.

**Acceptance Scenarios**:

1. **Given** the rename is applied, **When** a reader looks for what powers the
   project, **Then** Spec Kit is still credited as an underlying tool.
2. **Given** attribution text mentions Spec Kit, **When** it is read, **Then** it does
   not imply the product is made by, endorsed by, or affiliated with Spec Kit's
   creators.

---

### Edge Cases

- What happens to identifiers whose names mirror the underlying Spec Kit tool's own
  command names (e.g., the vendored `/speckit-*` skill commands that ARE Spec Kit's
  interface)? These may need to stay for the engine to work even though they contain
  the old branding. [NEEDS CLARIFICATION: see Question 3 — do engine-mirroring
  identifiers get renamed, or are they kept because they belong to the dependency?]
- What happens to a downstream repository that has pinned a reusable workflow or
  action by its current path/name when that name changes? (Covered by User Story 2 —
  breaking changes must be preserved or documented.)
- How is the in-repo transitional copy at `.speckit-pipeline/` treated? (See
  Assumptions — it is out of scope as untracked scaffolding.)
- What happens if the rename is only partially applied (some surfaces renamed,
  others not)? The result must be all-or-nothing per surface to avoid mixed
  branding.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The product's user-facing name MUST be "Wing Commander" across all
  human-readable surfaces (repository README, documentation, and pipeline-generated
  comments, pull request titles, and status messages).
- **FR-002**: No human-facing surface MUST present "speckit"/"speckit-action"/
  "speckit pipeline" as the product's own name; such branding MUST be replaced with
  "Wing Commander."
- **FR-003**: References to the third-party Spec Kit tool as an underlying dependency
  MUST be preserved and framed as attribution (what the product is built on), not as
  the product's identity.
- **FR-004**: Attribution to Spec Kit MUST NOT imply affiliation with, endorsement
  by, or association with the creators of Spec Kit.
- **FR-005**: The rename MUST be applied consistently: every reference to a name that
  is changed MUST be updated everywhere that name is used, leaving no dangling or
  mismatched references.
- **FR-006**: The pipeline MUST continue to function end-to-end after the rename,
  with all stages triggering and all internal references resolving.
- **FR-007**: Where the rename changes a name that an external consumer depends on,
  the change MUST either remain backward-compatible or be explicitly documented as a
  breaking change with migration guidance.
- **FR-008**: The scope of the rename (which surfaces are affected) MUST be clearly
  bounded so that "renamed" versus "intentionally unchanged" is unambiguous.
- **FR-009**: System MUST rename technical/internal identifiers (reusable and wrapper
  workflow filenames, the `spec-request` and other pipeline labels, action
  directories, and internal command/skill prefixes) [NEEDS CLARIFICATION: see
  Question 1 — is the rename limited to human-facing branding, or does it also cover
  breaking internal/downstream-facing identifiers?].
- **FR-010**: System MUST rename the outward-facing distribution identity (the GitHub
  repository name and the published/pinned action reference) [NEEDS CLARIFICATION:
  see Question 2 — are the repository name and published action reference in scope,
  or handled outside this feature?].

### Key Entities *(include if data involved)*

- **Product name**: The human-facing identity of the project — target value "Wing
  Commander." Appears in titles, docs, and generated messages.
- **Internal identifier**: A machine-referenced name — workflow filenames, label
  strings, action directory names, command/skill prefixes — that other parts of the
  system or downstream consumers resolve by exact value.
- **Attribution reference**: A mention of the underlying Spec Kit (or Claude Code)
  tooling, framed as a dependency the product uses.
- **Downstream consumer**: An external repository that pins or calls this project's
  reusable workflows or published action by name.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of human-facing surfaces that name the product refer to it as
  "Wing Commander"; zero present "speckit" as the product's own name.
- **SC-002**: A reader can determine the product's name in under 10 seconds from the
  repository landing page, and it is unambiguously "Wing Commander."
- **SC-003**: After the rename, the full pipeline completes a run on a sample issue
  with zero failures caused by mismatched or dangling renamed references.
- **SC-004**: Every name changed by the rename has zero unintended remaining
  occurrences of its old value (verified by search), excluding deliberate Spec Kit
  attribution.
- **SC-005**: Any name change that affects external consumers is either
  backward-compatible or accompanied by documented migration guidance — zero
  undocumented breaking changes.

## Assumptions

- The new product name is exactly "Wing Commander" (display form), with a
  lower-case, hyphenated slug form of `wing-commander` used wherever a
  slug/identifier is needed. The repository directory is already `wing-commander`,
  which is treated as confirmation of the intended slug.
- The intent is to remove "speckit" as the *product's own name*, not to remove
  honest attribution to the Spec Kit tool the product is built on.
- Claude Code attribution (the other tool the product uses) is unaffected by this
  rename and stays as-is.
- The untracked in-repo copy at `.speckit-pipeline/` is transitional scaffolding and
  is out of scope for this rename.
- The names of vendored Spec Kit skill/command interfaces are the property of the
  Spec Kit dependency; whether they are renamed is governed by Question 3 rather than
  assumed.
- No functional behavior of the pipeline changes as a result of this feature — it is
  a naming/branding change only.
