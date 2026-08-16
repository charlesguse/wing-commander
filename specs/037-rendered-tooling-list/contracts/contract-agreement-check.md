# Contract: The Output-Declaration Agreement Check (implementer-facing)

**Feature**: 037-rendered-tooling-list

Draft contract for a new gate script,
`.github/scripts/verify-tool-args-contract.py`, registered in
`.github/workflows/lint-workflows.yml` as a new numbered gate (research.md
D9; placeholder number — confirm the next free one against
`lint-workflows.yml` at implementation time). Satisfies FR-011, FR-012, and
User Story 3 (an adopter can see every output the composite emits; an
undeclared or removed output fails a check that names it).

This is a **repository-development-time** check — it runs in CI against
this repository's own files, not against a pipeline run's runtime output.
It is unrelated in scope to `contracts/tooling-statement-render.md`'s
render-correctness guarantees, which are exercised by a separate script
(`verify-tooling-statement.py`) — this check only holds *declared* and
*emitted* output names in agreement; it says nothing about whether a
declared output's value is correct.

## What it checks

Three sets of output names, all derived from files already in the
repository — no new manifest is introduced:

1. **`action.yml`-declared**: the keys of
   `.github/actions/wing-commander-tool-args/action.yml`'s top-level
   `outputs:` mapping.
2. **Emitted**: every `<name>` in an
   `echo "<name>=<value>" >> "$GITHUB_OUTPUT"` line (or equivalent
   heredoc/printf form already in use) inside that action's shipped
   `Compose tool args` step's `run:` block — parsed from the same extracted
   script text `verify-tooling-statement.py` already pulls out (research.md
   D8/D9 share the extraction helper to avoid two independently-drifting
   YAML parsers).
3. **`tool-composition-action.md`-documented**: the first-column entries of
   the Markdown table under `## Outputs` in
   `specs/026-configurable-tool-lists/contracts/tool-composition-action.md`.

## Pass condition

All three sets are identical. Concretely, the check fails, naming the
specific output and which set(s) it is missing from, when:

- An output is emitted but not in set 1 (`action.yml` under-declares what it
  actually produces).
- An output is emitted but not in set 3 (the published contract omits a
  real output — this is spec 037's own motivating defect, reproduced as a
  regression test against a scratch fixture in the self-test below).
- An output is in set 1 or set 3 but never emitted (a declared-but-dead
  output — FR-012's other direction).
- Set 1 and set 3 disagree with each other even where both agree with set 2
  (keeps the machine-checked action-level contract and the human-read
  Markdown contract from silently diverging from each other, not just from
  reality).

## Failure reporting

Matches the existing gate convention (`::error::` + a
`GITHUB_STEP_SUMMARY` line naming the script and the specific discrepancy,
non-zero exit) — the same shape `wing-commander-tool-args` itself already
uses for its own `fail()` helper, and the same shape every other
`verify-*.py` gate in this repository uses.

## Self-test (FR-015, User Story 4 Acceptance 4)

The script's own test phase runs the check twice more against scratch
fixtures, asserting each one fails for the expected reason:

1. A copy of `action.yml` with a fourth entry added to `outputs:` (declared)
   but no matching `echo ... >> "$GITHUB_OUTPUT"` line added to the `run:`
   block (not emitted) — asserts the check reports "declared but not
   emitted" for that name.
2. A copy of `action.yml` with the `shell-commands` entry deleted from
   `outputs:` while the `run:` block still emits it — asserts the check
   reports "emitted but not declared" for `shell-commands`. This
   reproduces, as a fixture, exactly the defect this spec exists to close
   permanently.

The suite passes only when both fixture runs fail and the real,
unmodified files pass — matching Gate 11/Gate 12's established
"demonstrates it failing on a known-bad input" pattern.

## Registration

A `- name: Gate <N> — every output the tool-args composite emits is
declared, and every declared output is emitted` step in
`.github/workflows/lint-workflows.yml`, `run: python3
.github/scripts/verify-tool-args-contract.py`. Auto-detected by
`.github/scripts/wc_gate_registry.py`/`verify-gate-wiring.py`'s existing
`verify-*.py`-in-a-`run:`-block scan — no separate registry edit (research.md
current-state findings).

## Non-goals

- Does not validate output *values* — see
  `contracts/tooling-statement-render.md` and `verify-tooling-statement.py`
  for the render-correctness guarantees.
- Does not extend to any other composite action's outputs. Scoped to
  `wing-commander-tool-args` because that is the composite this spec's
  defect was found in; a future spec may generalize the pattern if another
  composite's outputs drift the same way (no such drift is known today).
