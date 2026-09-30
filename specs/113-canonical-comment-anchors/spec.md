# Feature Specification: Named Anchors for Canonical Comment Pointers

**Feature Branch**: `spec-draft/113-canonical-comment-anchors`

**Created**: 2026-09-30

**Status**: Draft

**Input**: Lifecycle issue #747 — "Gate 47 misses a deleted canonical
comment when its topic words appear elsewhere in the file" (found by the
code review of #745), plus the routing comment on that issue that measured
the gap and chose `spec-request` over a local fix.

## Overview

CLAUDE.md's "Shared logic has exactly one home" section says repeated
comment prose gets ONE canonical comment and every other site points at it
(`-- see clarify.yml`). Gate 47
(`.github/scripts/verify-comment-canonical-pointers.py`) is the gate behind
that sentence. It asks three questions of every `#` comment in
`.github/workflows/*.yml`: does the pointer's named file exist, does the
pointer's topic prose share vocabulary with that file's own text, and does
every `(canonical copy; do not condense)` marker have at least one such
pointer aimed at it from another file.

All three questions are answered at **file** granularity. A pointer names a
file, never a block; the topic-overlap test is run against the union of
every comment in the target file. So a pointer proves only that *somewhere*
in the target there is a comment about roughly the same subject. When the
canonical block a pointer was written for is deleted, and some other comment
in the same file happens to share one 4+-letter topic word with it — which,
in a file like `clarify.yml` whose comments all describe one stage's agent
step, is the normal case rather than the unlucky one — the pointer keeps
passing. The marker check stops applying at the same moment, because there
is no longer a marker to justify. The gate goes quiet precisely when the
thing it exists to protect has been destroyed.

That is not a hypothetical. On the head of #745, deleting the whole
inspection-guidance block from `clarify.yml` left the gate reporting 10
markers and 0 violations, while the four pointers written for that block
went on resolving against unrelated `clarify.yml` comments. A pointer can
outlive its canonical comment, silently — which is exactly the drift the
single-home rule exists to prevent, and exactly the shape Principle VIII
names a liability: a check that reads as evidence while proving nothing.

The routing comment on #747 measured the two obvious repairs to the
vocabulary test and found neither works. Letting a pointer match *any*
canonical block in the target still misses the deletion of 8 of the 13
canonical blocks on `main`. Tightening to "a word unique to one block"
still misses 7 of those 8 and wrongly fails 14 pointers that are correct
today. Topic-word similarity cannot distinguish a block from its
neighbours, because neighbours in this repository legitimately describe the
same subject in the same words.

The fix that does work is identity instead of similarity: each canonical
block carries a **name**, each pointer states the name it depends on, and
the gate matches the two exactly. A deleted block takes its name with it,
and every pointer that named it fails on the next run.

The cost is that this is a repository-wide rename, not a one-file gate
patch. That is why #747 is spec-shaped rather than fix-shaped: the spec has
to decide how far the anchor requirement reaches and whether the tree
converts in one step or in phases. Those two decisions are the open
questions below.

### Observed facts (verified against `main` at 9d19228)

- Gate 47 ships as `.github/scripts/verify-comment-canonical-pointers.py`
  and is registered at `.github/workflows/lint-workflows.yml:3418` with its
  self-test at `:3421`.
- The pointer form is `-- see <FILE>` (case-insensitive), matched by
  `POINTER_MARK`; the target is the first `*.yml` / `*.yaml` / `*.md` /
  `*.py` name after it. A pointer naming nothing is treated as a same-file
  pointer and exempted from both the existence and overlap tests.
- The canonical-block form is a comment line containing both
  `(canonical copy` and `do not condense`. There are **13** such markers on
  `main`: `clarify.yml:308, 438, 599, 615, 625, 634, 641, 785, 1174, 1192,
  1378`; `finalize.yml:439`; `intake.yml:978`.
- There are roughly **200** `-- see <FILE>` pointers across **19** workflow
  files. `clarify.yml` is the target of the large majority; other targets
  include `implement.yml`, `pr-conversation.yml`, `finalize.yml`,
  `wing-commander-8-watchdog.yml`, three `docs/*.md` files (21 pointers in
  `auto-release.yml` name `docs/setup.md` alone), several
  `specs/*/{research,data-model,plan}.md`, and five `.py` gate/helper
  scripts.
- The topic test (`check_pointers`, part (b)) compares the significant
  words of the sentence before `-- see` against
  `significant_words(file_comment_text(target))` — the **whole** target
  file's comments. Nothing in the pointer identifies a block.
- The marker test (`check_canonical_markers`, part (c)) counts a marker
  justified when *any* pointer from another file resolving to this file
  shares one significant word with the block. Two adjacent blocks with
  overlapping vocabulary are mutually indistinguishable to it.
- The worked example from #747: `clarify.yml:634` is the `#266`
  inspection-guidance block. Its four pointers are `plan.yml:802`,
  `plan.yml:1032`, `tasks.yml:791` and `tasks.yml:1015`, each reading
  `#266: inspect files with the Grep, Glob and Read tools, never shell
  loops or unlisted commands, as the prompt below states -- see
  clarify.yml.` Their topic words include `prompt`, which occurs in many
  other `clarify.yml` comments.
- `implement.yml`, `pr-conversation.yml` and `wing-commander-8-watchdog.yml`
  are cross-file pointer targets today and carry **no** canonical marker at
  all, so naming an anchor in a pointer at them requires adding the marker
  to the target first.
- `board-loop.yml` is pointed at only from composite actions and gate
  scripts (`.github/actions/wing-commander-board-labels/action.yml:8`,
  `.github/scripts/wc_fence_extract.py:46`,
  `.github/scripts/board_route_backstop.py:10`, and others), none of which
  Gate 47 scans.
- `.github/actions/**` carries **27** `-- see` occurrences across 15 files,
  entirely outside Gate 47's declared scope. Gate 114's registration
  comment (`lint-workflows.yml:4632`) records that scope explicitly: "Gate
  47's declared scope is `#` comments in .github/workflows/*.yml only".
- `.github/scripts/**` carries **65** `-- see` occurrences across 31 files.
  About 29 of those are the two pointer gates' own docstrings explaining the
  convention rather than pointers, leaving roughly 36 real ones — also
  unscanned. Three sit in shell test harnesses
  (`size-path-backstop-tests/run-tests.sh:15`,
  `dispatch-and-wait-tests/run-tests.sh:12`,
  `stage-findings-tests/run-tests.sh`) and each names
  `verify-actions-no-gate-scripts.py`. `specs/080-composite-harness-gate-
  discovery` created them (T016-T018) and its quickstart §5 / T019 tell a
  maintainer to confirm them by running Gate 47 — which never reads those
  files, so it can neither confirm nor fail them. FR-016 is the question
  that decides whether they come under the rule; until it does, they are
  pointers no gate checks.
- Gate 47's self-test builds synthetic fixtures in a tempdir and currently
  exercises four defects: a pointer to a nonexistent file, a pointer with
  no topic overlap, an orphan canonical marker, and the aux
  `(see X stage)` justification path. **No mutation deletes a canonical
  block and asserts a failure** — which is why the reported gap shipped
  green.
- The self-pointer half of this area (#704) is out of scope here; it ships
  separately in #829.

## Clarifications

Three decisions are left to the owner rather than guessed, because each one
changes the size and the risk profile of the change. They are marked in the
requirements below and restated here:

1. **Migration shape** — one sweep that converts every pointer, or a phased
   rollout where anchored and unanchored pointers coexist behind a
   shrinking grandfather list. See FR-014.
2. **Target kinds that need anchors** — workflow-to-workflow pointers only,
   or also pointers at `docs/*.md`, `specs/*/*.md` and `.py` scripts, which
   carry no canonical-marker convention today. See FR-015.
3. **Pointer sites that come into scope** — workflow files only, as today,
   or also the 27 pointers in `.github/actions/**` and the pointers in gate
   scripts. See FR-016.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — A deleted canonical block breaks every pointer that depended on it (Priority: P1)

A maintainer condenses a long comment block out of `clarify.yml` during an
unrelated edit. Four pointers in `plan.yml` and `tasks.yml` were written
against that block. The next gate run names all four, by file and line, and
says which anchor no longer exists.

**Why this priority**: This is the defect #747 reports. Without it the
single-home rule has no enforcement at the moment it matters most — the
moment the single home disappears.

**Independent Test**: Delete the `#266` inspection-guidance block from
`clarify.yml`, run the gate, and confirm it exits non-zero naming
`plan.yml` and `tasks.yml`. On `main` today the same mutation exits zero.

**Acceptance Scenarios**:

1. **Given** a canonical block with a name and one or more pointers naming
   it, **When** the block is deleted from the target file, **Then** the gate
   fails and names every pointer that referenced the missing name.
2. **Given** the same deletion, **When** another comment in the target file
   shares topic vocabulary with the deleted block, **Then** the gate still
   fails — vocabulary elsewhere in the file never substitutes for the name.
3. **Given** a canonical block that is moved to a different line in the same
   file with its name intact, **When** the gate runs, **Then** it passes: the
   name is the identity, not the line number.
4. **Given** a canonical block whose name is changed without its pointers
   being updated, **When** the gate runs, **Then** it fails on the stale
   pointers.

---

### User Story 2 — A reader following a pointer lands on the block, not the file (Priority: P1)

An agent or a maintainer reads `tasks.yml`, meets a pointer, and needs the
canonical prose. Today the pointer says "see clarify.yml" — a 1400-line
file with 11 canonical blocks. With a name, the pointer says which of the
11, and the reader finds it with one search.

**Why this priority**: The pointer exists to save a reader from a duplicated
paragraph. A pointer that costs a file-wide scan to follow has already
given back most of what the single-home rule was buying, and every pipeline
stage agent pays that cost on every run.

**Independent Test**: Pick any anchored pointer, take its name, search the
target file for that name, and confirm exactly one block matches.

**Acceptance Scenarios**:

1. **Given** an anchored pointer, **When** a reader searches the target file
   for the anchor name, **Then** exactly one canonical block matches.
2. **Given** two canonical blocks in one file, **When** the gate runs,
   **Then** it fails if they carry the same name — a name that matches two
   blocks identifies neither.
3. **Given** a canonical block, **When** the gate runs, **Then** it fails if
   the block carries no name at all (subject to the migration shape chosen
   in FR-014).

---

### User Story 3 — The gate proves it can fail this defect (Priority: P1)

A future maintainer wants to know the gate still catches a deleted canonical
block. They run the self-test and see a named mutation that deletes one and
asserts the failure.

**Why this priority**: Principle VIII: every failure branch a gate ships
must be exercised by a checked-in fixture, and every instance of a check
that could not fail its subject in this repository was found by accident.
This defect shipped green precisely because no mutation covered it. Adding
the rule without adding the mutation would leave the next regression just as
invisible.

**Independent Test**: Run the gate's `--self-test` and confirm a named
deleted-canonical-block mutation is listed and passing.

**Acceptance Scenarios**:

1. **Given** the gate's self-test, **When** it runs, **Then** it includes a
   mutation that deletes a canonical block from a synthetic target while
   leaving a topic-word-sharing comment behind, and asserts the gate fails.
2. **Given** the gate's self-test, **When** it runs, **Then** it includes a
   mutation that renames a canonical block's anchor without updating its
   pointer, and asserts the gate fails.
3. **Given** the gate's self-test, **When** it runs, **Then** it includes a
   mutation that duplicates an anchor name within one file, and asserts the
   gate fails.
4. **Given** the anchored tree as shipped, **When** the gate runs against
   it, **Then** it reports zero violations — the migration is complete with
   respect to whatever scope FR-015 and FR-016 settle on.

---

### User Story 4 — A new pointer is written correctly the first time (Priority: P2)

A maintainer adding a pointer needs to know the form without reading the
gate's source. CLAUDE.md states the convention, and the gate's failure
message shows the expected shape.

**Why this priority**: The convention is only followed if it is discoverable.
CLAUDE.md currently documents the bare `-- see clarify.yml` form, so a
maintainer following the documentation would write a pointer the new gate
rejects.

**Independent Test**: Read CLAUDE.md's "Shared logic has exactly one home"
section and write a conforming pointer without opening the gate script.

**Acceptance Scenarios**:

1. **Given** CLAUDE.md, **When** a maintainer reads the single-home section,
   **Then** it states the anchored pointer form and the named canonical
   marker form.
2. **Given** a pointer that names a file but no anchor where one is
   required, **When** the gate fails it, **Then** the message states the
   expected form and names at least one valid anchor in that target.
3. **Given** the gate script, **When** a maintainer reads its module
   docstring, **Then** the docstring describes anchor matching rather than
   the retired topic-word rule for anchored pointers.

### Edge Cases

- A canonical block whose pointers all live in files outside the scanned set
  (a composite action, a gate script docstring): the block would read as an
  orphan to a workflow-only scan. FR-016 decides whether those pointer sites
  are read; if they are not, the block needs an explicit, registered
  exemption rather than a silently-passing one.
- A pointer target that carries no canonical marker at all today
  (`implement.yml`, `pr-conversation.yml`, `wing-commander-8-watchdog.yml`):
  requiring an anchor means adding the marker to the target as part of this
  work.
- A pointer at a `.md` document or a `.py` docstring, where the
  `(canonical copy; do not condense)` comment convention does not exist:
  FR-015 decides whether these need an anchor mechanism of their own or stay
  on file-level resolution.
- A same-file pointer (`-- see above in this file.`): names nothing to
  resolve and is exempt today. It stays exempt; #829 handles self-pointers.
- Anchor names that collide across different files (`clarify.yml#retry-bound`
  and `intake.yml#retry-bound`): legal, because a pointer always names the
  file too. Uniqueness is required within a file, not across the repository.
- An anchor name that appears inside ordinary comment prose discussing the
  convention — including this gate's own registration comment in
  `lint-workflows.yml`, which quotes the marker phrasing — must not be
  mistaken for a marker instance. The gate already guards this by requiring
  both marker fragments on one line; the anchored form must keep an
  equivalent guard.
- A line-wrapped pointer whose anchor name is split across two comment
  lines: the gate's existing continuation-joining rules must keep the name
  intact.
- A canonical block that legitimately has exactly one consumer and no
  pointer yet, added in the same PR as its first pointer: ordering within a
  PR must not matter, since the gate sees only the final tree.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Every canonical comment block MUST carry a name that
  identifies it within its file, declared on the marker line itself so the
  name and the marker cannot be separated by an edit to either one.
- **FR-002**: Anchor names MUST be unique within a file. The gate MUST fail
  when one file declares the same name twice, naming both blocks.
- **FR-003**: A pointer at a canonical block MUST state the file and the
  anchor name together, in a single token a reader can copy into a search
  (the `-- see clarify.yml#inspection-guidance` shape the issue proposes).
- **FR-004**: The gate MUST fail an anchored pointer whose named anchor does
  not exist in the resolved target file, and MUST report the pointing file,
  its line, and the missing name.
- **FR-005**: The gate MUST NOT accept topic-word overlap anywhere in the
  target file as a substitute for a present anchor. For anchored pointers,
  anchor identity replaces the part (b) vocabulary test entirely.
- **FR-006**: The gate MUST continue to fail a pointer whose named file does
  not exist (today's part (a)), unchanged.
- **FR-007**: A canonical block MUST be justified by at least one pointer,
  from another file within the scanned set, that names its anchor exactly.
  Vocabulary overlap MUST NOT justify a marker.
- **FR-008**: Same-file pointers that name no target MUST remain exempt from
  anchor resolution.
- **FR-009**: The gate MUST report anchor-related violations as GitHub
  annotations on the offending file and line, in the same form it reports
  today's violations, and MUST exit non-zero when any violation is found.
- **FR-010**: The gate's failure message for an unanchored or misanchored
  pointer MUST state the expected pointer form and name at least one anchor
  that does exist in the resolved target, so a maintainer can fix it without
  reading the gate's source.
- **FR-011**: The gate's self-test MUST include a mutation that deletes a
  canonical block from a synthetic target which retains a topic-word-sharing
  comment, and MUST assert the gate fails on it.
- **FR-012**: The gate's self-test MUST additionally include a mutation that
  renames an anchor without updating its pointer, and one that declares the
  same anchor name twice in one file, each asserting a failure.
- **FR-013**: The gate's module docstring MUST describe the anchor rule as
  shipped, and the registration comment in `lint-workflows.yml` MUST match
  it. CLAUDE.md's "Shared logic has exactly one home" section MUST state the
  anchored pointer form it tells maintainers to write.
- **FR-014**: The tree MUST reach a state where the gate passes with the
  anchor rule active. [NEEDS CLARIFICATION: migrate all ~200 pointers and
  all 13 canonical blocks in one change, or phase the anchor requirement in
  behind an explicit, shrinking grandfather list of still-unanchored
  pointers?]
- **FR-015**: The anchor requirement's reach over target kinds MUST be
  stated and enforced. [NEEDS CLARIFICATION: do pointers at `docs/*.md`,
  `specs/*/*.md` and `.py` scripts — which have no canonical-marker
  convention today, and which account for a large share of pointers
  including 21 at `docs/setup.md` — require anchors too, or do only
  workflow-to-workflow pointers?]
- **FR-016**: The set of files scanned as pointer sources MUST be stated and
  enforced. [NEEDS CLARIFICATION: does this feature bring the 27 `-- see`
  pointers in `.github/actions/**` and the roughly 36 in
  `.github/scripts/**` — including three `run-tests.sh` pointers spec 080
  believes Gate 47 already validates — into scope, or does the gate keep its
  declared `.github/workflows/*.yml`-only scope, leaving canonical blocks
  whose only consumers live there needing a registered exemption?]
- **FR-017**: Whatever scope FR-015 and FR-016 settle on MUST be recorded in
  the gate's docstring as its declared scope, so the next reader learns the
  boundary from the gate rather than from a spec.
- **FR-018**: Any pointer or canonical block the chosen migration shape
  leaves outside the anchor rule MUST be covered by an explicit, enumerated
  registration — never by a rule the gate silently skips. The registration
  MUST be readable as a list a reviewer can shrink.
- **FR-019**: The gate MUST keep reporting its counts (pointers checked,
  canonical markers checked, violations found) so a reviewer can see the
  subject was actually reached rather than inferring a pass from silence.
- **FR-020**: The anchor form MUST be chosen so that the gate's existing
  comment-block joining, which concatenates line-wrapped comment text, does
  not fragment an anchor name.

### Key Entities

- **Canonical block**: a run of `#` comment lines, one of which carries both
  canonical-marker fragments plus, after this feature, the block's anchor
  name. It is the single home for one piece of prose.
- **Anchor name**: a short, stable identifier for a canonical block, unique
  within its file. It is the dedup-style key that makes a pointer verifiable
  by identity rather than by similarity.
- **Anchored pointer**: a comment at a duplicate site naming the target file
  and the anchor name together, standing in for the prose it does not
  repeat.
- **Declared scope**: the enumerated set of pointer-source files and target
  kinds the gate checks, recorded in the gate's own docstring.
- **Grandfather registration**: the enumerated list of pointers or blocks
  still exempt from the anchor rule, if the chosen migration shape needs
  one.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Deleting any canonical block in the anchored scope while
  leaving its pointers in place makes the gate exit non-zero, for **all 13**
  such blocks. The two similarity-based alternatives measured on #747 reach
  5 of 13 ("a pointer may match any canonical block") and 6 of 13 ("a word
  unique to one block", which also wrongly fails 14 correct pointers); the
  rule shipping on `main` detects the `clarify.yml:634` deletion 0 times out
  of 1.
- **SC-002**: The gate exits zero on the tree as shipped, with zero
  violations reported and its pointer and marker counts non-zero.
- **SC-003**: Every pointer inside the anchored scope names an anchor that
  resolves to exactly one block in exactly one file.
- **SC-004**: The gate's self-test covers the deleted-block,
  renamed-anchor and duplicate-name mutations, and fails if any of the three
  is removed from the gate's logic.
- **SC-005**: Following any anchored pointer to its canonical prose takes
  one search of the named file and yields exactly one result, with no
  reading of unrelated comments.
- **SC-006**: A maintainer who writes a new pointer using only CLAUDE.md's
  single-home section produces one the gate accepts.
- **SC-007**: No pointer or canonical block in the repository is outside both
  the anchor rule and the enumerated registration FR-018 requires — the
  boundary is legible from the gate and its registration alone.

## Assumptions

- The anchor convention lives in comment prose, not in a side file. A
  registry mapping names to blocks would be a second home for the same fact
  and would itself drift.
- Anchor names are chosen by the maintainer writing the block; nothing
  derives them mechanically from the prose. Deriving them from content would
  reintroduce the similarity problem this feature exists to remove.
- Anchor uniqueness is required per file, not per repository, because a
  pointer always names the file alongside the name.
- The existing marker phrasing stays recognisable. Whatever anchored form is
  chosen, the gate keeps a guard equivalent to today's "both fragments on
  one line" rule so prose *about* the convention is not counted as a marker.
- The pointer form stays a single-line, copy-pasteable token. The `FILE#name`
  shape the issue proposes satisfies this and is assumed unless the plan
  finds it collides with something.
- This feature changes comments and one gate. It changes no pipeline
  behaviour, so it is provable entirely at PR time by the gate suite — no
  post-merge re-drive of an Actions-only path is needed.
- The `.wing-commander-pipeline/` self-checkout in a working tree is a
  transient copy of this repository and is not a migration target.
- #704's self-pointer work, shipping in #829, may touch the same gate. Which
  of the two lands first is a sequencing question for the plan stage, not a
  design conflict.

## Dependencies

- `.github/scripts/verify-comment-canonical-pointers.py` — the gate whose
  rule changes.
- `.github/workflows/lint-workflows.yml` — Gate 47's registration and
  comment, and the gate-suite entry point CI and
  `.github/scripts/run-local-gates.py` share.
- The 19 workflow files carrying pointers, and the 3 carrying canonical
  markers (`clarify.yml`, `finalize.yml`, `intake.yml`).
- `CLAUDE.md` — the "Shared logic has exactly one home" section that states
  the convention to maintainers.
- Whatever FR-015 and FR-016 admit: `docs/setup.md`, `docs/adoption.md`,
  `docs/architecture.md`, `specs/*/{research,data-model,plan}.md`, the `.py`
  pointer targets, `.github/actions/**`, and `.github/scripts/**` (including
  the three `*-tests/run-tests.sh` harnesses).
- Gate 114 (`verify-maintainer-credential-canonical-statement.py`) — a
  sibling single-statement gate whose registration comment records Gate 47's
  declared scope. If that scope moves, its note must move with it.

## Out of Scope

- Rewriting, shortening or deduplicating the canonical prose itself. This
  feature changes how a pointer identifies a block, not what the block says.
- Detecting duplicated prose that carries no pointer and no marker. Gate 47
  checks that the pointer mechanism is wired to something real; finding
  unmarked copies is `verify-single-home-idioms.py`'s job.
- The self-pointer half of this area (#704), which ships in #829.
- Any change to the three canonical-marker-free pointer targets beyond
  adding the markers and anchors the chosen scope requires.
- Extending the anchor idea to spec artifacts as live documents. Merged
  `specs/NNN-*/` spec, plan, research and tasks files are historical records
  and are not edited to satisfy a new convention; they appear here only as
  pointer *targets*.
