# Phase 0 Research: Lint Composite Action Scripts

`spec.md` carries no `[NEEDS CLARIFICATION]` markers — the requirements
(FR-001 through FR-009) and Assumptions section are already fully resolved.
Phase 0 research below is about the *technical* design decisions planning
still had to make to turn those requirements into a concrete change to
`.github/workflows/lint-workflows.yml`. None of these were escalated as
clarification questions; each is recorded here as a decision made during
planning, per this pipeline's standing instruction to proceed rather than
block when a spec is otherwise complete.

## R1 — Where the new discovery/check logic lives

**Decision**: Extend the existing "Parse YAML and bash -n every run block"
step's inline Python script in place — add a second glob
(`.github/actions/**/action.yml` and `.github/actions/**/action.yaml`,
recursive) alongside the existing `.github/workflows/*.yml` glob, and for
each discovered composite action walk `(doc.get("runs") or {}).get("steps")
or []` the same way the existing code walks
`job.get("steps") or []` for every job. Both sources funnel into the same
`failures` counter, the same expression-neutralization regex
(`re.sub(r"\$\{\{[^}]*\}\}", "EXPR", run)`), and the same `bash -n` subprocess
call, so a composite-action script is checked with byte-for-byte the same
logic a workflow-job script already gets (FR-004).

**Rationale**: FR-003 requires collecting scripts from both the
composite-action step layout and the reusable-workflow job layout, and FR-004
requires identical neutralization/syntax-check treatment across both. Doing
this inside the single existing step (rather than adding a parallel step or
job) is the only way to guarantee that identity by construction — one code
path, one annotation format, one failure counter — instead of maintaining two
copies that could drift.

**Alternatives considered**:
- *New sibling step or job dedicated to composite actions*: rejected. It
  would duplicate the neutralization regex and `bash -n` invocation, creating
  exactly the drift risk FR-004 exists to prevent, and would double the
  annotation/failure-reporting surface for no benefit — the spec does not ask
  for the two sources to be distinguished in reporting, only that both are
  covered and neither regresses (FR-007).
- *A separate script/tool invoked by the step*: rejected as unnecessary
  indirection for a ~15-line addition to an already-inline heredoc; every
  other gate in this file follows the same inline-heredoc convention.

## R2 — Composite action discovery pattern (FR-008)

**Decision**: Use `glob.glob(".github/actions/**/action.yml", recursive=True)`
and the same for `action.yaml`, matching at any depth. This mirrors the
existing workflow glob's use of the standard-library `glob` module and
requires no new dependency.

**Rationale**: FR-008 explicitly requires recursive discovery at any nesting
depth and both extensions, "so that no composite action can slip past
discovery regardless of nesting depth or file-name extension." All six
composite actions in this repository today sit at `.github/actions/<name>/action.yml`
(a single level of nesting, all `.yml`), but the requirement is written
depth- and extension-agnostic, and `glob.glob(..., recursive=True)` costs
nothing extra to get right up front.

**Alternatives considered**: `os.walk` with manual filename matching —
rejected as more code for the same result; `glob`'s `**` recursive form is
already the pattern this file's own conventions favor (simplicity, stdlib
only).

## R3 — Parse-failure handling parity (FR-009)

**Decision**: A composite action file that raises on `yaml.safe_load` is
reported with `::error file={f}::YAML parse failure: {e}`, incrementing the
same `failures` counter — identical in shape to the existing workflow
parse-failure branch, just applied to the `.github/actions/**` glob's files
too. No separate skip/continue path is introduced for unparseable composite
actions.

**Rationale**: FR-009 requires parity with how reusable-workflow parse
failures are reported, and explicitly forbids silently skipping the file or
limiting the check to whatever scripts happen to be extractable. Reusing the
exact same `try`/`except`-around-`yaml.safe_load` shape already in the file
is the direct way to guarantee that parity rather than approximate it.

**Alternatives considered**: A distinct error message/annotation format for
composite-action parse failures (e.g., naming it differently from the
workflow case) — rejected; the spec asks for parity, not a distinguishable
variant, and a maintainer reading either annotation gets the same actionable
information (which file, why it didn't parse).

## R4 — Actions with no composite steps (container/JavaScript actions)

**Decision**: No special-case branch is needed. `(doc.get("runs") or
{}).get("steps") or []` naturally evaluates to an empty list for an action
whose `runs.using` is `node20`/`docker`/etc. (those `runs:` blocks have no
`steps:` key), so the walk contributes zero scripts and zero failures for
such a file without any `using:` check in the code.

**Rationale**: The spec's Edge Cases section states this case explicitly
("actions built on a container or JavaScript... have no scripts to
syntax-check and should pass without failure"). The chosen extraction
expression already produces that outcome as a natural consequence of Python's
falsy-empty-list handling, so adding an explicit `if using != "composite":
continue` guard would be redundant code checking a condition the data
structure already encodes.

**Alternatives considered**: An explicit `runs.get("using") == "composite"`
guard before extracting steps — considered for readability, but rejected as
unnecessary: it adds a branch to test for a case the empty-list fallback
already handles correctly, and every composite action in this repository
already sets `using: composite` explicitly (R2's discovery scope), so the
guard would never actually change behavior, only add a line that needs its
own justification.

## R5 — Trigger path extension (FR-002)

**Decision**: Add `".github/actions/**"` as a second entry in
`on.pull_request.paths`, alongside the existing `".github/workflows/**"`.
The `push`/`schedule`/`workflow_dispatch` triggers (which feed Gate 1, the
`registered` job) are unaffected — Gate 1 is specific to workflow
registration-name resolution and does not apply to composite actions per the
spec's Assumptions, so its trigger scope is deliberately left unchanged.

**Rationale**: FR-002 requires the guard to fire for pull requests that
modify composite action definitions, independent of whether any workflow
file also changed (User Story 2, Acceptance Scenario 1). GitHub Actions
`paths:` filters are inclusive-OR across entries, so adding the second glob
is sufficient and does not narrow the existing trigger for workflow-only
changes (FR-007 — no regression).

**Alternatives considered**: A second `pull_request` trigger block scoped
only to `.github/actions/**` running a composite-actions-only job — rejected;
it would either duplicate the check logic (contradicting R1) or require
cross-job coordination for a single failure/success signal, adding
complexity the simpler shared-`paths:` approach avoids entirely.

## R6 — Documentation of the syntax-only limitation (FR-006)

**Decision**: Extend `lint-workflows.yml`'s existing header comment block
(the one already explaining why gates exist and what each one catches) with
a sentence stating the check is a syntax check only and does not exercise or
guarantee `errexit`/`pipefail` runtime behavior of composite `shell: bash`
steps. This is "the guard's own documentation" User Story 3 refers to — the
file's header comment is the only documentation of the guard's semantics
that exists today (`docs/architecture.md` mentions `lint-workflows.yml` only
in passing, as one of two constraints stage 8's wrappers must hold; it does
not document the guard's own scope or limitations).

**Rationale**: FR-006 requires the statement to exist somewhere a maintainer
reading "the lint guard's own documentation" will find it. The header
comment is already the guard's documentation of record — it explains why
each gate was added and what class of failure it catches/misses (e.g., "Gate
1 is the catch-all backstop for the same class, post-merge"). Adding the
syntax-only caveat there, rather than creating a new documentation file or
section elsewhere, keeps the guard's scope and limitations described in one
place next to the logic they describe.

**Alternatives considered**: Adding a new subsection to `docs/architecture.md`
documenting `lint-workflows.yml` end-to-end — rejected as out of scope; that
file does not currently document any of the three existing gates' semantics
either (only the two constraints they enforce on stage 8's wrappers), so
adding full documentation there would be a scope increase beyond what FR-006
asks for, which is a statement of the syntax-only limitation, not a new
architecture document.
