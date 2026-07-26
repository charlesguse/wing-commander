# Quickstart: Validating Composite-Action Lint Coverage

Prerequisites: ability to open a pull request against this repository (or a
fork), and read access to its checks tab. No special setup beyond a normal
checkout — this repo dogfoods itself (constitution I) and has no separate
unit-test harness for workflow YAML (see plan.md's Technical Context).

## Scenario 1 — A broken composite-action script fails the guard (US1; FR-001, FR-004, FR-005)

1. On a throwaway branch, introduce a deliberate shell syntax error into one
   of the `run:` blocks under any file in `.github/actions/**` (for example,
   an unmatched quote in `wing-commander-preflight/action.yml`'s "Preflight
   (credentials, spec-kit, prerequisites)" step) — do **not** do this against
   `main`.
2. Open a pull request from that branch.
3. Confirm `lint · workflows` triggers and the `lint` job fails with an
   `::error` annotation naming the action file and the specific step.
4. Revert the deliberate breakage; confirm the same PR's `lint` job now
   passes.

**Expected**: SC-001, SC-002 hold — the composite action's scripts are
covered by the syntax check, and a syntax error there fails the pull
request.

## Scenario 2 — Expression interpolation does not cause a false failure (US1 Acceptance Scenario 3; FR-004)

1. On a throwaway branch, add (or confirm an existing) composite-action step
   whose `run:` block references an action input via `${{ inputs.some-input }}`
   in a way that would not be valid bash if left un-neutralized (e.g. used
   directly in a position bash would otherwise choke on).
2. Open a pull request from that branch.
3. Confirm the `lint` job passes that step — the same `${{ ... }} → EXPR`
   neutralization already applied to workflow scripts applies here too.

**Expected**: SC-001 holds without a false positive; User Story 1
Acceptance Scenario 3 is satisfied.

## Scenario 3 — Composite-action-only change still triggers the guard (US2; FR-002)

1. On a throwaway branch, edit only a file under `.github/actions/**` (for
   example, a comment-only or description-only change in any `action.yml`)
   — touch no file under `.github/workflows/**`.
2. Open a pull request from that branch.
3. Confirm `lint · workflows` runs at all (previously it would not have
   triggered for a change scoped this way) and the `lint` job evaluates the
   changed file.

**Expected**: SC-003 holds.

## Scenario 4 — Malformed composite action file fails with parity to a malformed workflow (Edge Cases; FR-009)

1. On a throwaway branch, break the YAML structure of an `action.yml` file
   (e.g. an unclosed mapping) so `yaml.safe_load` raises.
2. Open a pull request from that branch.
3. Confirm the `lint` job fails with a `::error file=...::YAML parse
   failure: ...` annotation, in the same form the existing check already
   uses for a malformed workflow file.

**Expected**: The guard fails on the parse failure itself rather than
silently skipping the file, matching the spec's Edge Cases entry for this
case.

## Scenario 5 — No regression in existing workflow-script coverage (FR-007)

1. On a throwaway branch, introduce a deliberate shell syntax error into a
   `.github/workflows/*.yml` file's `run:` block (the same kind of change
   the guard already caught before this feature).
2. Open a pull request from that branch.
3. Confirm the `lint` job still fails on it, with the same annotation shape
   as before this feature's change.
4. Revert; confirm a pull request that changes both a workflow file and a
   composite action file (both syntactically valid) triggers the guard once
   and passes, evaluating both (User Story 2 Acceptance Scenario 2).

**Expected**: SC-004 holds — zero regression in previously-covered
reusable-workflow scripts.

## Scenario 6 — Actions with no embedded scripts pass cleanly (Edge Cases)

1. Confirm (by inspection, no PR needed unless one is already open for
   another scenario) that an action definition using `runs.using: node20` or
   `runs.using: docker` — if any exist or are added later — contributes no
   failures, since it has no `runs.steps` to walk.

**Expected**: Matches the spec's Edge Cases entry — no scripts to check, no
failure.

## Scenario 7 — Documentation states the syntax-only limitation (US3; FR-006)

1. Read `.github/workflows/lint-workflows.yml`'s header comment.
2. Confirm it explicitly states the check is a syntax check only and does
   not verify runtime `errexit` behavior of composite `shell: bash` steps.

**Expected**: SC-005 holds, verifiable by inspection.
