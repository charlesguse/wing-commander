# Feature Specification: Lint Composite Action Scripts

**Feature Branch**: `025-lint-composite-actions`

**Created**: 2026-07-26

**Status**: Draft

**Input**: GitHub issue #41 — "lint-workflows doesn't cover composite actions under .github/actions/\*\*"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Composite action scripts are syntax-checked before merge (Priority: P1)

A maintainer opens a pull request that changes the embedded shell script inside a
composite action (for example, one of the action definitions under the repository's
composite-actions directory). Those scripts run in every pipeline job, but today the
pre-merge lint guard only inspects reusable-workflow files, so a broken script in a
composite action reaches the default branch undetected. The maintainer wants the same
guard that protects workflow scripts to also protect composite-action scripts, so a
syntax error is surfaced on the pull request instead of breaking live pipeline runs.

**Why this priority**: This is the entire purpose of the request. Composite-action
scripts execute in every pipeline job, so an undetected syntax error there has the same
(or broader) blast radius as the workflow-script bug the guard was originally built to
catch. Closing the coverage gap delivers the feature's value on its own.

**Independent Test**: Introduce a deliberate shell syntax error into a composite
action's embedded script on a branch, open a pull request, and confirm the lint guard
fails the pull request with an annotation pointing at that action file and step.

**Acceptance Scenarios**:

1. **Given** a composite action whose embedded script contains a shell syntax error,
   **When** the lint guard runs on a pull request, **Then** the guard fails and reports
   an annotation identifying the offending action file and step.
2. **Given** a composite action whose embedded scripts are all syntactically valid,
   **When** the lint guard runs on a pull request, **Then** the guard passes those
   scripts without new failures.
3. **Given** a composite action script that uses expression interpolation (the
   `${{ ... }}` form, including action inputs), **When** the guard checks it, **Then**
   the interpolation is neutralized the same way workflow scripts are before the syntax
   check, so valid interpolation does not cause a false failure.

---

### User Story 2 - Changes limited to composite actions still trigger the guard (Priority: P1)

A maintainer opens a pull request that only edits a composite action definition and
touches no reusable-workflow file. They expect the lint guard to run, because the change
affects scripts that execute in the pipeline. Today the guard's trigger only watches the
workflows directory, so a pull request that changes only a composite action never runs
the guard at all.

**Why this priority**: Coverage of the script contents (Story 1) is worthless if the
guard never fires for the pull requests that change those scripts. The trigger scope and
the check scope must land together for the feature to deliver value.

**Independent Test**: Open a pull request that modifies only a composite action file (no
workflow file changed) and confirm the lint guard is triggered and evaluates that change.

**Acceptance Scenarios**:

1. **Given** a pull request whose only changes are under the composite-actions
   directory, **When** the pull request is opened or updated, **Then** the lint guard is
   triggered.
2. **Given** a pull request that changes both a workflow file and a composite action,
   **When** the pull request is opened, **Then** the guard runs and evaluates both.

---

### User Story 3 - The guard's limits are stated honestly (Priority: P2)

A maintainer reading the lint guard's own documentation needs to understand what the
extended coverage does and does not guarantee, so they do not mistake "the script passed
the guard" for "the script is safe at runtime." In particular, the guard performs a
syntax check only; it cannot catch runtime-semantics failures such as a command that
returns non-zero under the errexit behavior that composite `shell: bash` steps run
under.

**Why this priority**: Prevents a false sense of safety, but the coverage improvement is
valuable even without it. Documentation clarity is secondary to the functional gap
closing.

**Independent Test**: Read the lint guard's documentation and confirm it explicitly
states that the check is syntax-only and does not verify runtime errexit behavior of
composite scripts.

**Acceptance Scenarios**:

1. **Given** the lint guard's documentation, **When** a maintainer reads it, **Then** it
   states that the check is a syntax check only and does not make composite scripts
   errexit-safe.

---

### Edge Cases

- What happens when a composite action file does not parse as structured data? The guard
  fails the lint on the parse failure, matching how workflow-file parse failures are
  reported, rather than silently skipping the file or only checking the scripts it can
  extract.
- What happens for action definitions that contain no embedded scripts (for example,
  actions built on a container or JavaScript rather than composite steps)? These have no
  scripts to syntax-check and should pass without failure.
- What happens for a composite step whose script is empty or absent? It is skipped, the
  same as a workflow step with no script.
- How does the guard handle composite action files stored at a nesting depth or with a
  file-name form other than the top level? Discovery is recursive at any depth and
  accepts both `action.yml` and `action.yaml`, so these files are still discovered and
  checked (see FR-008).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The pre-merge lint guard MUST syntax-check the embedded shell scripts
  defined in composite action definitions, in addition to the scripts embedded in
  reusable-workflow files.
- **FR-002**: The lint guard MUST be triggered by pull requests that modify composite
  action definitions, not only by pull requests that modify reusable-workflow files.
- **FR-003**: The lint guard MUST collect embedded scripts from the composite-action
  step layout (the action's own list of steps) in addition to the reusable-workflow job
  layout (each job's list of steps).
- **FR-004**: Each embedded script collected from a composite action MUST undergo the
  same expression-interpolation neutralization and syntax check that is applied to
  reusable-workflow scripts, so that behavior is consistent across both sources.
- **FR-005**: When a composite action's embedded script fails the syntax check, the
  guard MUST fail the run and emit an annotation that identifies the offending action
  file and the specific step.
- **FR-006**: The lint guard's own documentation MUST state that the check is a syntax
  check only — it does not verify runtime errexit behavior and therefore cannot catch
  the class of runtime-semantics failures that motivated this coverage extension.
- **FR-007**: The extension MUST NOT reduce or regress existing coverage of
  reusable-workflow scripts; all currently-covered workflow scripts remain covered.
- **FR-008**: The guard's discovery of composite action files MUST match `action.yml`
  and `action.yaml` files recursively at any depth under the composite-actions
  directory, so that no composite action can slip past discovery regardless of nesting
  depth or file-name extension.
- **FR-009**: When a composite action definition cannot be parsed as structured data,
  the guard MUST fail the run and report the parse failure, with parity to how
  reusable-workflow parse failures are reported; it MUST NOT silently skip the file or
  limit itself to the scripts it can extract.

### Key Entities *(include if data involved)*

- **Reusable-workflow file**: An existing pipeline workflow definition; its embedded
  scripts are already covered by the guard.
- **Composite action definition**: An action assembled from a list of steps, some of
  which embed shell scripts; these scripts are the newly-covered surface.
- **Embedded script**: A shell script block inside a step (in either a workflow job or a
  composite action) that the guard neutralizes for interpolation and then syntax-checks.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of the embedded scripts in the repository's composite action
  definitions are covered by the syntax check (up from 0% today).
- **SC-002**: A shell syntax error introduced into any composite action script is caught
  and fails the pull request before it can be merged.
- **SC-003**: A pull request whose only change is to a composite action definition
  triggers the lint guard (previously it did not run at all).
- **SC-004**: No previously-covered reusable-workflow script loses coverage as a result
  of the change (zero regressions in existing coverage).
- **SC-005**: The guard's documentation clearly communicates the syntax-only limitation,
  verifiable by inspection.

## Assumptions

- The runtime-semantics coverage discussed in the issue (exercising composite scripts
  under errexit/pipefail via a fixture harness to catch runtime failures) is explicitly
  out of scope for this feature; it is a separate decision, and this feature only closes
  the static syntax-coverage gap.
- The guard's default-branch registration check (which reads how workflows are
  registered by name) does not apply to composite actions, since composite actions are
  not registered as named workflows; only the syntax-checking coverage and its trigger
  are extended.
- Composite action definitions that embed no shell scripts (for example, container- or
  JavaScript-based actions) legitimately contribute nothing to syntax-check and pass
  without failure.
- Expression interpolation inside composite action scripts uses the same interpolation
  form as workflow scripts and never introduces shell quoting, so the existing
  neutralization approach is sufficient.
