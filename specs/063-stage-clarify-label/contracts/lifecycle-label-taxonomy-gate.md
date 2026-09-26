# Contract: Gate 99 — `verify-lifecycle-label-taxonomy.py`

**New gate**, `.github/scripts/verify-lifecycle-label-taxonomy.py`, wired
into `lint-workflows.yml` as **Gate 99** (the next available number —
research.md D7 confirms Gate 98 is the current highest). Discovered
automatically by `verify-gate-wiring.py` (Gate 10) and invoked identically
by `.github/scripts/run-local-gates.py` via `wc_gate_registry.py`'s
filename-glob convention — no manifest entry anywhere needs editing beyond
the one `lint-workflows.yml` step (research.md D8).

## Purpose

Enforce FR-001/FR-007: every `stage:*` label `docs/setup.md` documents
either has a real writer among the shipped workflows and composite actions,
or carries a registered, reasoned exemption. Closes the exact gap this
feature exists to close — `stage:clarify` documented with zero writers and
zero waiver, undetected until this feature's own spec (#483) traced it by
hand.

## Inputs (derived, never hardcoded — FR-007)

1. **Documented label set** — every backtick-quoted `` `stage:[a-z-]+` ``
   token found anywhere in `docs/setup.md` (table rows, the label-creation
   script, and prose such as the "created on the fly" sentence), read fresh
   from the file on every run.
2. **Applied label set** — every literal `stage:[a-z-]+` token passed as an
   argument to `gh issue edit --add-label`/`--remove-label`, `gh issue
   create --label`/`-l`, or a REST `-f "labels[]=..."` call, scanned across
   every `.github/workflows/*.yml` and every `.github/actions/**/
   action.yml` (local composites only — `uses: ./...`, matching this
   repository's self-checkout convention; no external action is scanned).
   A `--label`/`-l` argument to a *read* command (`gh issue list`, `gh
   search`) is excluded — the same read/write distinction Gate 90 already
   established and this gate reimplements locally (research.md D7).
3. **Exemption registry** — `.github/scripts/lifecycle-label-taxonomy-
   waivers.json`, parsed the same way Gate 31 parses `stage-invariant-
   waivers.json`: missing file → zero waivers; malformed JSON or a missing
   required field (`file`, `check`, `pattern`, `count`, `issue`, `reason`)
   → hard failure naming the malformed entry, never a silent skip.

## Verdict

| Case | Result |
|---|---|
| Every documented label is in the applied set | PASS |
| A documented label is in the applied set **and** also has a waiver entry | FAIL — a waiver for a label that has a writer is stale by construction (nothing left to exempt) |
| A documented label is in neither the applied set nor the waiver registry | FAIL, naming the label |
| A documented label has a waiver whose `pattern` does not match it exactly, or whose `count` does not match the live count of documented mentions | FAIL — stale waiver, either direction |
| The registry file exists but is malformed, or an entry is missing a required field | FAIL, naming the malformed entry |

## Required self-test fixtures (`--self-test`, following the `Gate 98
self-test` naming convention already in `lint-workflows.yml`)

1. **The regression this feature fixes**: a synthetic `docs/setup.md`
   documenting `stage:clarify` with no matching apply site anywhere →
   FAILs, names `stage:clarify`. This is FR-008's demonstration, run against
   the *actual* pre-change tree in the implementation PR, and pinned
   permanently here as a fixture so the regression cannot silently return
   (constitution VIII: "every failure branch a gate ships MUST be exercised
   by a checked-in fixture").
2. **A documented label with a valid, exact waiver** → PASSes (Acceptance
   Scenario 3 — the exemption mechanism works even though Direction A ships
   with zero live exemptions in the real registry).
3. **A stale waiver** (its labeled deviation now has a writer) → FAILs.
4. **A waiver whose `count` no longer matches** → FAILs.
5. **A new documented label with no writer, added to a synthetic
   `docs/setup.md`** → FAILs, naming the new label (User Story 3,
   Acceptance Scenario 1 — proves the gate catches the *next* one, not just
   `stage:clarify`).
6. **A workflow change that deletes the only apply site for a documented
   label** → FAILs, naming that label (User Story 3, Acceptance Scenario 2).
7. **A malformed waivers file** (missing required field) → FAILs, names the
   malformed entry, distinct from "documented label with no writer."

## Gate 10 / local-runner parity (FR-009)

- `check_subject_triggers()` (part of Gate 10) requires that any `docs/
  *.md`/`specs/*/contracts/*.md` string constant appearing in a gate's
  source be covered by `lint-workflows.yml`'s `pull_request.paths:` filter.
  `"docs/setup.md"` must appear as an actual Python string literal in
  `verify-lifecycle-label-taxonomy.py` (not only in a comment or an f-string
  interpolation) for this check to see it; the literal path is already
  present in the filter, so no filter edit is needed once the constant is
  written literally.
- `run-local-gates.py` picks the gate up automatically via
  `pr_time_invocations()`'s scan of `lint-workflows.yml`'s `run:` blocks —
  no separate registration.

## Non-goals

- Does not cover `spec-request`, `model:*`, `disposition:*`, or `board:*`
  labels (explicit Out of Scope) — scoped to the `stage:*` lifecycle
  taxonomy only, per the Assumptions section of spec.md.
- Does not check label *color* or *description* text, only existence of a
  writer.
- Does not enforce the create-before-add ordering Gate 90 checks (a
  same-job "create appears before apply" property) — Gate 99 asks only
  "does a writer exist anywhere," a strictly weaker and cheaper property
  sufficient for FR-001/FR-007 (research.md D7).
