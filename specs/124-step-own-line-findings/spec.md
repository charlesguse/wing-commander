# Feature Specification: A Gate 60 Finding Names Its Own Step's Line

**Feature Branch**: `124-step-own-line-findings`

**Created**: 2026-09-30

**Status**: Draft

**Input**: User description: "fix(gate-60): report the violating step's own line for marker-write/pr-branch findings — `check_marker_write` and `check_pr_branch` located a finding with `text.find(run.splitlines()[0])`, which returns the first textual occurrence of the run's first line anywhere in the file, not the occurrence belonging to the violating step. A step whose `run:` opens with a line common to several steps (e.g. `set -uo pipefail`) landed on an earlier, unrelated step's line instead (board-loop.yml:298 reported at :176 on PR #683). Fix: parse the workflow with a line-tracking YAML loader, stashing the source line as an attribute rather than a dict key so it can never collide with real step content or show up in `.items()`, and report the step's own mapping line directly instead of re-finding text. Add two self-tests that reproduce the exact failure shape (a decoy step sharing the real step's first `run:` line) and assert the reported line equals the real step's, not the decoy's."

## Overview

Gate 60 (`verify-single-home-idioms.py`) reports each finding as
`<path>:<line>: <check> (<evidence>) -- see <declared home>`. For its
per-step checks the `<line>` is not derived from the step at all: it is
the result of searching the whole file for the first textual occurrence of
the step's first `run:` line. Because most `run:` blocks in this fleet open
with the same boilerplate (`set -uo pipefail`, `set -euo pipefail`), that
search lands on whichever step happens to come first in the file.

The reported location is therefore wrong whenever it matters most — on a
large workflow with many steps, which is exactly where a maintainer needs
the pointer. PR #683 showed the failure in the real tree: the violating
step sat at `board-loop.yml:298` and the gate named `:176`, an unrelated
step whose `run:` opens with the same line. A maintainer following that
pointer reads a step that does not contain the idiom, concludes the gate
is confused, and either waives a real violation or spends a session
locating it by hand.

This is the third independent appearance of the same defect class in this
repository's gates. `verify-board-label-creation.py` hit it as #493 and
worked around it with a forward-only cursor; `verify-gate-24.py` avoided
it by parsing with a line-recording YAML loader that injects a `__line__`
key into every mapping. Gate 60 has neither, in any of its per-step
checks.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The pointer in a Gate 60 failure leads to the violating step (Priority: P1)

A maintainer (or the board loop's review agent) reads a Gate 60 failure in
a CI log or a local gate-suite run, clicks or opens the `path:line` it
names, and lands on the step whose `run:` actually carries the duplicated
idiom — not on an earlier step that merely opens with the same shell
boilerplate.

**Why this priority**: This is the whole value of the finding. A location
that points at innocent code is worse than no location: it actively argues
that the gate is wrong, which is how a real violation gets waived.

**Independent Test**: Take a workflow with two steps whose `run:` blocks
begin with an identical first line, where only the later step carries the
idiom the check scans for. Run the gate. The reported line is the later
step's, not the earlier one's. This is testable on a synthetic fixture
alone, with no other part of the feature built.

**Acceptance Scenarios**:

1. **Given** a subject workflow in which step A (no violation) and step B
   (violation) both open their `run:` with `set -uo pipefail`, and B
   appears after A, **When** the gate runs, **Then** the finding's line
   falls inside step B and does not fall inside step A.
2. **Given** a subject workflow whose single violating step is the only
   step in the file, **When** the gate runs, **Then** the reported line
   still falls inside that step (the fix does not regress the case the old
   logic happened to get right).
3. **Given** a subject workflow carrying two distinct violating steps of
   the same check, **When** the gate runs, **Then** two findings are
   reported at two different lines, each inside its own step.
4. **Given** a violating step reached through a composite action's own
   `runs.steps` list rather than a workflow job's `steps`, **When** the
   gate runs, **Then** the reported line falls inside that step.

---

### User Story 2 - The correct anchoring is proven by a checked-in fixture, not a demonstration (Priority: P1)

The repository carries self-test fixtures that reproduce the exact failure
shape — a decoy step sharing the violating step's first `run:` line — and
assert the reported line is the violating step's. The fixtures fail against
the old anchoring logic and pass against the new one, so a future edit that
reintroduces whole-file text searching is caught by the gate suite rather
than by the next maintainer's confusion.

**Why this priority**: Constitution VIII requires every failure branch a
gate ships to be exercised by a checked-in fixture, and states plainly that
a manual demonstration during development is evidence for that reviewer,
not coverage for the next one. An anchoring fix with no fixture is
indistinguishable from no fix after one refactor. Same priority as P1
because the repository's own rules make the fixture part of the fix, not a
follow-up.

**Independent Test**: Revert only the anchoring logic to whole-file
`text.find` while keeping the new fixtures; the gate's `--self-test` must
report failures naming the wrong line. Restore the logic; `--self-test`
must pass.

**Acceptance Scenarios**:

1. **Given** the gate's `--self-test` mode, **When** it runs against the
   shipped tree, **Then** it includes at least one case per per-step check
   in scope that places a decoy step ahead of the violating step and
   asserts the reported line is the violating step's.
2. **Given** the anchoring logic is reverted to a whole-file first-occurrence
   search, **When** `--self-test` runs, **Then** it exits non-zero and names
   the decoy line it received against the violating line it expected.
3. **Given** `--self-test` runs, **When** a case fails, **Then** the failure
   message states both the expected line and the received line, so the
   diagnosis does not require re-reading the fixture.

---

### User Story 3 - Every per-step check in the gate anchors the same way, from one place (Priority: P2)

The step-to-source-line resolution lives in exactly one place that every
per-step check in the gate consumes, so a per-step check added later
inherits correct anchoring instead of re-pasting the defective idiom from
the check above it.

**Why this priority**: The defective expression is not in two places by
accident — it is in eight, because each new per-step check was written by
copying the previous one. Fixing only the two sites the issue names leaves
six live copies of the defect and leaves the next author copying from a
site that is still wrong. CLAUDE.md's "shared logic has exactly one home"
rule and the gate's own subject matter — single-home idioms — both point the
same way. P2 rather than P1 because the two named checks deliver the
user-visible value on their own.

**Independent Test**: Grep the gate for whole-file first-occurrence line
searching in a per-step context; zero occurrences remain. Add a throwaway
per-step check that consumes the shared resolution and confirm it anchors
correctly without new anchoring code.

**Acceptance Scenarios**:

1. **Given** the shipped gate, **When** its per-step checks are inspected,
   **Then** none of them derives a finding's line by searching the file text
   for the step's first `run:` line.
2. **Given** a new per-step check is added that uses the shared resolution,
   **When** it reports a finding, **Then** the line is the violating step's
   without the new check containing any line-resolution logic of its own.

---

### Edge Cases

- **A subject file that does not parse.** The per-step checks currently skip
  a file whose YAML cannot be loaded. A file that parses under the ordinary
  loader but not under a line-tracking one must not become silently
  unscanned — a finding with a less precise line is still a finding, and a
  gate that quietly stops checking a file reports a pass it did not earn
  (Constitution VIII).
- **A step with no `run:`** (`uses:`-only, or an empty `run:`): no finding,
  as today; the anchoring change must not make such a step reportable.
- **A step whose `run:` is a single line, or a flow-style mapping**
  (`- {run: "...", shell: bash}`): the reported line must still be that
  step's own.
- **A YAML anchor/alias reused as a step** (`- *shared-step`): the alias
  site and the anchor definition site are different lines; the spec must say
  which one a finding names, and the answer must be stable across runs.
- **A `.sh` subject file.** Shell scripts under `.github/actions/**` are
  subjects of this gate but have no YAML steps; the per-step checks must go
  on contributing nothing for them rather than erroring.
- **Two byte-identical violating steps in one file.** Two findings at two
  distinct lines, never one finding or two findings sharing a line.
- **The declared-home file itself**, and files under a declared home's
  directory, stay excluded exactly as today.
- **A waiver that suppresses one of these findings.** Waivers match on
  file, check and evidence text — never on line — so a changed line must not
  invalidate any existing waiver, and the stale-waiver failure must not
  start firing because lines moved.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The gate MUST derive the source line of a per-step finding
  from the position of the violating step itself in the subject file, not
  from a search of the file's text for content the step shares with other
  steps.
- **FR-002**: When two or more steps in one subject file open their `run:`
  block with an identical first line and only one of them carries the idiom
  a per-step check scans for, the finding's reported line MUST fall within
  the carrying step and MUST NOT fall within any other step.
- **FR-003**: The reported line MUST be [NEEDS CLARIFICATION: the step
  mapping's own first line (where the step begins), or the line inside the
  step's `run:` block on which the matched fragment actually appears? The
  originating issue asks for the step's mapping line;
  `verify-board-label-creation.py`, the sibling gate that already fixed this
  defect class as #493, reports the matched fragment's own line. Two gates
  answering this differently is how the next maintainer learns not to trust
  either.]
- **FR-004**: Per-step findings for two distinct violating steps in the same
  subject file MUST carry two distinct lines.
- **FR-005**: The anchoring change MUST NOT change which findings the gate
  reports — the set of (file, check, evidence) triples the gate produces
  against the shipped tree MUST be identical before and after, with only the
  line differing.
- **FR-006**: Any source-line information the gate attaches to a parsed step
  MUST NOT be observable as step content: it MUST NOT appear when a step's
  keys or items are enumerated, and MUST NOT be capable of colliding with a
  key a real workflow could legitimately declare.
- **FR-007**: If line-tracking parsing of a subject file fails where
  ordinary parsing succeeds, the gate MUST still run its per-step checks on
  that file and still report any finding, falling back to a best-effort
  line; it MUST NOT skip the file, and MUST NOT report a location it
  presents as exact.
- **FR-008**: The gate's `--self-test` mode MUST include, for each per-step
  check brought into scope, a fixture in which a decoy step sharing the
  violating step's first `run:` line precedes it, asserting the reported
  line is the violating step's and not the decoy's.
- **FR-009**: Each such self-test case MUST fail if the anchoring is
  reverted to a whole-file first-occurrence search, and its failure message
  MUST name both the expected and the received line.
- **FR-010**: The fix MUST apply to [NEEDS CLARIFICATION: only the two
  checks the issue names (`marker-write`, `pr-branch`), or every per-step
  check in the gate that currently anchors by whole-file text search? Eight
  sites carry the identical defective expression today: `failure-issue`,
  `outstanding-task-item`, `post-review-comment`,
  `review-finding-fingerprint`, `fold-commit`, `fold-dispatch`,
  `marker-write`, `pr-branch`. Fixing two leaves six live copies and leaves
  the next per-step check being copied from a wrong one.]
- **FR-011**: The step-to-line resolution MUST have a single home within the
  scope chosen in FR-010, consumed by every per-step check in that scope;
  no per-step check may carry its own copy.
- **FR-012**: That single home MUST be [NEEDS CLARIFICATION: private to
  Gate 60, or a shared helper that `verify-gate-24.py` (which injects a
  `__line__` key into every mapping — the collision FR-006 forbids) and
  `verify-board-label-creation.py` (which advances a forward-only cursor)
  are also migrated onto? Three gates currently answer "which line is this
  step on?" three different ways; consolidating them is the CLAUDE.md
  single-home rule applied to this gate's own subject matter, but it widens
  the change to two gates this issue did not name and whose own fixtures
  must keep passing.]
- **FR-013**: Existing entries in `single-home-waivers.json` MUST continue
  to suppress exactly what they suppressed before, and the stale-waiver
  check MUST NOT begin failing as a result of changed lines.
- **FR-014**: The gate MUST continue to run the same subject set with the
  same arguments locally (through the gate registry and
  `run-local-gates.py`) as it does in CI.

### Key Entities

- **Finding**: what the gate reports — the subject file path, the check
  name, the evidence text, and the source line. The line is the field this
  feature corrects; the other three are unchanged and are what waivers match
  on.
- **Per-step check**: a Gate 60 check scoped to one step's own `run:` text
  rather than the whole file, because its fragments are individually common
  in this fleet. Only these checks have a step to anchor to.
- **Decoy step**: a fixture step that shares the violating step's first
  `run:` line but carries none of the check's fragments — the shape that
  reproduces the defect.
- **Declared home**: the one file a given idiom is allowed to live in.
  Unchanged by this feature; it is the `-- see <home>` half of the message.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For every per-step check in scope, a maintainer following the
  `path:line` in a Gate 60 failure lands inside the violating step 100% of
  the time, including on the largest subject file in the fleet.
- **SC-002**: The failure shape recorded on PR #683 — a violating step
  reported at an earlier, unrelated step's line — is reproduced by a
  checked-in fixture that fails before the change and passes after it.
- **SC-003**: Zero per-step checks in the gate derive a finding's line from
  a whole-file search for text the step shares with other steps.
- **SC-004**: The set of findings the gate reports against the shipped tree
  is unchanged except for line numbers: same count, same files, same checks,
  same evidence text.
- **SC-005**: The full PR-time gate suite passes locally and in CI, and no
  existing waiver becomes stale.
- **SC-006**: Reverting only the anchoring logic makes `--self-test` fail,
  in every per-step check brought into scope.

## Assumptions

- The issue's diagnosis is taken as correct and was verified against the
  shipped tree: eight per-step call sites compute the line as
  `text.find(run.splitlines()[0])`, and the two the issue names are two of
  them.
- Waivers match findings on file, check and evidence text only, so changing
  reported lines cannot invalidate a waiver. Verified against the shipped
  waiver-matching logic.
- The evidence text and the `-- see <declared home>` half of each message
  stay exactly as they are; this feature changes the location, not the
  wording. Gate 47's byte-comparison of workflow comments is untouched.
- The `__line__`-as-a-dict-key approach used by `verify-gate-24.py` is
  treated as the shape to avoid, per the issue's explicit instruction, not
  as the precedent to copy — a key injected into every mapping is
  observable to any consumer that enumerates a step and is exactly what
  FR-006 forbids.
- This gate's subject files are workflows under `.github/workflows/`,
  `action.yml`/`action.yaml` under `.github/actions/**`, and `.sh` files
  under `.github/actions/**`. Unchanged by this feature.
- Recording the line during parsing costs a negligible amount of time on a
  fleet of this size; no performance requirement is stated.

## Out of Scope

- Gate 60's file-wide checks (`orphan-reset`, `extraheader-refresh`,
  `verdict-shape`, `mode-tag-shape`, `transcript-normalise`,
  `branch-advance-capture`, `board-stop-check`, `promotion`,
  `composite-checkout-order`). They anchor on a regex match position in the
  file text, which is already the position of the thing they matched.
- Which idioms the gate checks, what its declared homes are, and how it
  decides a violation. This feature changes only where a finding says it is.
- Emitting the finding as a GitHub annotation with `file=`/`line=`
  properties so it renders on the diff. Gate 60 prints `::error::` with the
  location inside the message text; making the location clickable in the
  Checks UI is a separate, additive change and is not required for a
  maintainer to act on a correct line.
- Auditing the remaining `verify-*.py` gates for the same defect class,
  beyond whatever FR-012 decides about the two named siblings.
