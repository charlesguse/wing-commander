# Quickstart: Validating Name-Free Stage Identity

This feature only runs inside GitHub Actions (watchdog inspections of
other runs), so it cannot be exercised end-to-end from a local shell the
way a library change could. Validation is fixture-driven locally, plus
one real re-drive after merge (CLAUDE.md's rule for Actions-only
behavior).

## Prerequisites

- A checkout of this repository with the feature's changes applied.
- `python3`, `jq`, `bash` (the gate suite's own requirements).

## 1. Run the full local gate suite

```
python .github/scripts/run-local-gates.py
```

This runs every gate `lint-workflows.yml` invokes, including:

- `verify-metrics-record-schema.py` — proves the new
  `spec.identity_is_own` field is additive-valid against every fixture
  (`contracts/spec-identity-declaration.md` Rule 1/2).
- `verify-metrics-summary-record-emission.py` — proves every call site of
  `wing-commander-metrics-summary` passes `spec-identity-is-own` and that
  the record it renders carries the value verbatim.
- The new FR-012 gate (`verify-no-reference-name-stage-match.py`,
  `contracts/stage-identity-name-gate.md`) — proves no FR-002 site other
  than `id: name-fallback` gates on a reference display name, and every
  metrics-summary call site declares its spec identity.
- `verify-watchdog-*` collector self-tests — extended per US1's
  acceptance scenarios to prove each collector's three-state behavior
  (`data-model.md`'s Resolved stage identity table).

Expected: all gates green. A red gate for the new script before its
sites are updated is expected mid-implementation (research.md R2 notes
the gate ships red-then-green with the sites it checks, in the same PR).

## 2. Exercise the composite's resolution logic against fixtures

Each acceptance scenario in spec.md's User Story 1 corresponds to a
fixture pair (renamed wrapper vs. reference-named wrapper) asserting
**identical** `resolved-stage`/`resolved-stage-source` output and
identical downstream collector outcomes. Drive
`wing-commander-inspected-run-identity`'s `run:` blocks directly (the
existing test harness this repository's `.github/scripts/fixtures/`
convention uses for composite-internal logic) with:

- A synthetic metrics record naming `stage: implement`, `run-name` set to
  an arbitrary string → expect `resolved-stage=implement`,
  `resolved-stage-source=record`.
- No record, `run-name` set to `Wing Commander · 5 implement` → expect
  `resolved-stage=implement`, `resolved-stage-source=name`.
- No record, `run-name` set to an unrecognised string → expect both
  outputs empty.
- A record with `stage_available: false`, `run-name` recognised → expect
  the name to win (`resolved-stage-source=name`), proving FR-009's "no
  record, or `stage_available: false`" fallback condition.

## 3. Validate the three-state consumers

For each FR-002 site (branch-drift, spec-meta, final-pr-claims,
spec-collision, the implement-only baseline arms, the stage label, the
self-inspection guard), confirm via the corresponding
`verify-watchdog-*` self-test:

- Identified + in scope → runs, same as today.
- Identified + out of scope → silent skip, same as today.
- Not identified → skip AND a `{"collector": ..., "outcome":
  "unresolved"}` entry lands in `collector-outcomes.json`, feeding the
  `aggregate` step's new `stage-unresolved-collectors` output.

## 4. Validate the FR-014 warning

Confirm via `verify-watchdog-*` (collect-execution-output's extended
self-test) that the warning fires exactly on: stage unresolved AND
`claude-execution-output*` found. Confirm it does NOT fire when: stage
resolved (regardless of name), or no `claude-execution-output*` artifact
was found (regardless of name) — matching spec.md's US2 acceptance
scenarios 2–5.

## 5. Read `docs/adoption.md`'s new section cold

Per US3's own independent test: read only the new subsection (R8) and
confirm it answers "may I rename my wrappers, and what do I lose?"
without needing to open `watchdog.yml`.

## 6. Post-merge proof (Actions-only behavior)

Per CLAUDE.md and spec.md's Assumptions, after the implementation PR
merges:

1. Re-drive one watchdog inspection (`gh workflow run` on
   `wing-commander-8-watchdog.yml`, or wait for the next natural
   `workflow_run` trigger) against a run of a renamed wrapper — e.g. a
   temporary duplicate of an existing wrapper with a different `name:`.
2. Confirm the inspection's findings match an inspection of the
   reference-named wrapper for the same underlying run (SC-001).
3. Record the run URL and outcome as evidence on the PR or the lifecycle
   issue, per CLAUDE.md's rule for behavior that only runs in Actions.
