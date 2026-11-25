# Feature Specification: Gate the skill scripts' self-tests and cross-tree imports

**Feature Branch**: `131-skill-script-gate`

**Created**: 2026-11-25

**Status**: Draft

**Input**: User description: "No gate runs the `.claude/skills/*/scripts` self-tests (`thrash_signals.py --self-test`) or checks their imports from `.github/scripts` (`board_prove.scan_dispatchable_and_uses_graph`, `board_route_backstop.diff_name_list`, `wc_board_status.snapshot`/`render`/`switches_from`), and lint-workflows' `pull_request: paths:` doesn't include `.claude/skills/`, so a rename there breaks the skills with every gate green (found by the code review of #998). PR #1205 grew past the board's size-and-path backstop by readiness time (files=2, lines=123); the branch/PR are left open, unmerged, under a notice. This spec request covers finishing the work at the size a human plan should decide." (lifecycle issue #1206, Maintenance backlog #889 line `bl-ddabf5f6`)

## Context

The owner's sessions run helper scripts that ship with the repository's
skills (`.claude/skills/<skill>/scripts/*.py`). Several of them import
functions from the shared `.github/scripts/` tree, either by name or by
importing the module and using its names as attributes:

| Skill script | Names it reaches in `.github/scripts/` |
|---|---|
| `review-until-clean/scripts/thrash_signals.py` | `wc_convergence` as `wc`, used as `wc.measure`, `wc.decide`, `wc.decide_history`, `wc.render_handoff` (and has its own `--self-test`) |
| `prove-after-merge/scripts/redrive_candidates.py` | `board_prove` names, `board_route_backstop.diff_name_list` |
| `whats-on-me/scripts/board_now.py` | `wc_board_status`, used as `wc_board_status.snapshot`, `.render`, `.switches_from` |
| `container-shell-safety/scripts/unpinned-container-steps.py` | `wc_gate_registry.workflow_files`, `wc_shell_pin` names |

These scripts run only when a session invokes the skill. A rename in
`.github/scripts/` therefore merges with every gate
green, and the first sign of breakage is an owner's session failing mid-task.

State on main at intake (2026-11-25), so the plan does not redo it:

- lint-workflows' `pull_request: paths:` already lists
  `.claude/skills/*/scripts/**`, so a PR touching a skill script does trigger
  the gate suite. A PR that touches only `.github/scripts/**` also triggers
  it. The trigger half of the original defect is closed.
- Some imports are partly covered by existing gates that serve other
  purposes (`verify-board-prove.py` names `redrive_candidates.py` as a reach
  consumer; `verify-board-status.py` exercises one `board_now` path;
  `verify-convergence-single-home.py` scans skill scripts for copied
  arithmetic). None of them runs `thrash_signals.py --self-test`, and none
  checks that every skill script's cross-tree imports resolve.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A rename that breaks a skill script fails the PR (Priority: P1)

A maintainer (or a stage agent) renames or removes a function in
`.github/scripts/` that a skill script imports. The PR's gate suite fails,
naming the skill script and the missing name, before the change can merge.

**Why this priority**: This is the defect itself: today the break is
invisible until an owner's session hits it.

**Independent Test**: On a scratch copy, rename one imported function (for
example `diff_name_list`) and run the gate suite; the new check fails and
names `redrive_candidates.py` and `diff_name_list`. Revert; it passes.

**Acceptance Scenarios**:

1. **Given** main with all skill scripts' imports resolving, **When** the
   check runs, **Then** it passes.
2. **Given** a change that removes or renames a name a skill script imports
   from `.github/scripts/`, **When** the check runs, **Then** it fails and
   names the skill script, the module and the missing name.
3. **Given** a change that removes a whole module a skill script imports,
   **When** the check runs, **Then** it fails the same way.
4. **Given** a skill script that imports a whole module (for example
   `import wc_convergence as wc`) and calls `wc.decide`, **When** a change
   renames `decide` in that module, **Then** the check fails and names the
   skill script, the module and `decide`.

---

### User Story 2 - A skill script's own self-test runs on every PR (Priority: P2)

`thrash_signals.py --self-test` (and any other skill script that offers a
self-test) runs in the PR gate suite, so a change to the convergence
arithmetic it wraps, or to the script itself, cannot merge with the
self-test failing.

**Why this priority**: The self-test exists but nothing runs it; it guards
the review-until-clean loop's thrash decision.

**Independent Test**: Break the self-test's expected value on a scratch
copy and run the gate suite; it fails. Restore; it passes.

**Acceptance Scenarios**:

1. **Given** a skill script that declares a self-test, **When** the gate
   suite runs, **Then** that self-test runs and its failure fails the suite.
2. **Given** a new skill script that declares a self-test, **When** it is
   added, **Then** the gate runs it with no workflow edit and no entry in a
   hand-kept list, so it is never silently skipped.

---

### User Story 3 - The check cannot go blind (Priority: P3)

The new gate proves it can fail its subject: it carries a self-test (or
mutation fixtures) showing that a removed name, a removed module and a
failing skill self-test each make it fail, and that it discovers skill
scripts rather than relying on a hand-kept list that can drift.

**Why this priority**: The repository's rule is that a gate must be able to
fail; a list of three scripts goes stale the day a fourth appears.

**Independent Test**: Run the gate's own self-test; each mutation fails it.

**Acceptance Scenarios**:

1. **Given** the gate's self-test, **When** it runs, **Then** each seeded
   defect (missing name, missing module, failing skill self-test) is caught.
2. **Given** a new skill script importing from `.github/scripts/`, **When**
   the gate runs, **Then** that script's imports are checked with no edit to
   the gate.

### Edge Cases

- A skill script that imports a module with side effects at import time
  (network, `gh` calls): the check must resolve names without running the
  skill's command-line behaviour or reaching the network.
- A skill script that imports nothing from `.github/scripts/`
  (`stranded-steps.py`, `find_governing_spec.py`): checked trivially, not an
  error.
- Third-party imports (`yaml`) missing in the gate's environment are a
  different failure and must not be reported as a renamed repository name.
- A self-test that needs `git` or a scratch repository (thrash_signals does)
  must run in the CI job's environment.
- Skill scripts under `ideas/<project>/.claude/skills/` (per-project
  copies), if any exist, are out of scope unless the plan finds them in use.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The PR-time gate suite MUST fail when any skill script under
  `.claude/skills/*/scripts/` reaches a module or name in `.github/scripts/`
  that does not exist on the PR's head. This covers every name the script
  reaches, whether imported directly (`from module import name`) or used as
  an attribute of an imported module (`import module as m` … `m.name`).
- **FR-002**: The failure message MUST name the skill script, the module
  and the missing name, for both kinds of use in FR-001.
- **FR-003**: The set of skill scripts checked MUST be discovered from the
  tree, not from a hand-kept list.
- **FR-004**: A skill script offers a self-test when it accepts a
  `--self-test` command-line flag. Every such script MUST have that
  self-test run by the PR-time gate suite, found from the tree (FR-003),
  and a failing self-test MUST fail the suite. The skill self-tests MUST run
  as part of the gate set `run-local-gates.py` derives, not only in CI.
  A skill self-test MUST run offline; one that needs the network or the
  GitHub API fails the gate as a defect in that skill's self-test.
- **FR-005**: The check MUST NOT execute a skill script's normal command
  path or reach the network or GitHub API.
- **FR-006**: The new gate MUST carry a self-test that demonstrates it fails
  on a removed name, a removed module and a failing skill self-test.
- **FR-007**: The gate MUST be picked up by the derived gate list, so that
  `python .github/scripts/run-local-gates.py` runs it, with no hand
  registration. `docs/reference.md` is edited only if one of the
  categories its "Keeping this current" section lists changes.
- **FR-008**: lint-workflows' `pull_request: paths:` MUST continue to
  include `.claude/skills/*/scripts/**` (already true on main), and that
  MUST remain enforced by exactly one gate:
  `verify-convergence-single-home.py`, which already fails when the entry
  stops covering the skill scripts. This feature adds no second copy.
- **FR-009**: The open PR #1205 MUST be closed with a pointer to this
  lifecycle, whether or not its content is reused in this feature's
  implementation, and Maintenance backlog line `bl-ddabf5f6` is closed
  when this feature merges.
- **FR-010**: The plan sets how the work is split into PRs; this spec sets
  no size bound.
- **FR-011**: The new gate step(s) and the self-test of the new gate MUST
  follow whatever PR-time layout from spec 129 (`129-parallel-pr-lint`) is
  on main when this is implemented, sharded or not: each sits in exactly
  one unit, runs regardless of an unrelated step's failure, has a step name
  unique across PR-time steps, and is picked up by the derived gate list
  with no extra edit.

### Key Entities

- **Skill script**: a Python file under `.claude/skills/<skill>/scripts/`
  that a session runs while following a skill.
- **Cross-tree import**: a module or name a skill script reaches in
  `.github/scripts/`, imported directly or used as an attribute of an
  imported module.
- **Skill self-test**: the `--self-test` mode of a skill script, which
  checks its own behaviour and exits non-zero on failure.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Renaming any one of the cross-tree names listed in the
  Context table makes the PR gate suite fail; 100% of them are caught.
- **SC-002**: `thrash_signals.py --self-test` runs on every PR that
  triggers the gate suite, and breaking it turns the suite red.
- **SC-003**: Adding a new skill script that imports from `.github/scripts/`
  requires zero edits to the gate for its imports to be checked.
- **SC-004**: The new gate steps, skill self-tests included, take no more
  than one minute of their own run time in CI.
- **SC-005**: On merge, no open PR or backlog line still tracks this defect.

## Assumptions

- The trigger-path half of the original backlog line is already fixed on
  main (`.claude/skills/*/scripts/**` is in lint-workflows' paths); this
  feature keeps it fixed rather than re-adding it.
- Checking imports statically (or by importing with side effects stubbed)
  is acceptable; which one is a plan decision.
- One new gate script is the expected shape; extending an existing gate
  (e.g. folding into `verify-convergence-single-home.py`) is acceptable if
  the plan prefers it, provided the "single home" rule in CLAUDE.md holds.
- The CI job that runs the gate suite already has Python, PyYAML and git.
