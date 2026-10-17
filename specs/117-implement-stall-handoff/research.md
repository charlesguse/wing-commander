# Research: Implement Stall Hand-off and Honest Remaining-Work Reporting

No `[NEEDS CLARIFICATION]` markers remain in spec.md. The decisions below
resolve the points spec.md deliberately left to planning (marker literal,
blocker field, standing-instruction rule, where the logic lives).

## D1. Maintainer marker literal

- **Decision**: the literal token `[maintainer]`, placed after the task ID
  and before any story tag: `- [ ] T004 [maintainer] Dispatch ...`.
- **Rationale**: lower-case, bracketed, cannot collide with the checkbox
  `- [ ]`/`- [x]` pattern (the checkbox is always the first bracket pair),
  and greppable. Detection is a fixed-string match of ` [maintainer] `
  within the first 40 characters after the checkbox, so prose that mentions
  the word is not a marker.
- **Alternatives**: `**MAINTAINER**` (bold collides with Markdown prose);
  `[M]` (collides with the legacy `M001` catch-all ids); a separate
  "Maintainer" phase heading only (position-based, not per-line, so finalize
  could not classify a line deterministically).

## D2. Single home: extend `count-tasks-checkboxes.sh`

- **Decision**: classification (maintainer / standing / implementation)
  lives in `.github/actions/_shared/count-tasks-checkboxes.sh`, the existing
  one home of the tasks.md read (CLAUDE.md "Shared logic has exactly one
  home"). The script gains outputs `impl-checked-count`,
  `impl-unchecked-count`, `impl-unchecked-items`, `maintainer-items`,
  `standing-count`. Existing `checked-count`/`unchecked-count`/
  `unchecked-items` keep their meaning (all lines) so no published output
  is removed. The `wing-commander-tasks-checkbox-count` composite surfaces
  the new outputs (additive widening of the published composite surface,
  Principle VII; noted in the PR and at the release).
- **Rationale**: implement's two read-back arms and finalize all already
  read tasks.md through this script; a second classifier would be a pasted
  copy.
- **Alternatives**: a separate classifier script (two parsers of the same
  file drift); classifying in finalize's agent prompt (violates IX / FR-007).

## D3. Standing-instruction rule

- **Decision**: a checkbox line is a standing instruction when, after
  stripping the checkbox and an optional `T###`/`M###` id, it matches one
  entry of a closed pattern table in the script: starts with
  `Complete every remaining`, `Keep the gates green`, `Run the (full )?gate
  suite` with no deliverable noun after it (no `and fix`/file path/backtick
  path), or `After each cycle`. Table entries are anonymous, case-insensitive
  and each backed by a fixture line. Lines in no table entry are
  implementation.
- **Rationale**: FR-004 asks for a deterministic rule; a closed table is
  reviewable and errs toward counting as implementation (the safe, louder
  direction, per the spec's edge cases).
- **Alternatives**: any task without a file path is standing (too broad:
  would hide real unfinished work); agent judgment (IX).

## D4. Blocker field

- **Decision**: the implement agent may write one JSON file,
  `implement-blocker.json`, to the runner temp directory (never the repo,
  matching `finalize-remaining.md`). Shape: `{"task": "T0NN", "kind":
  "<missing-tool|missing-permission|contradictory-spec|external-dependency>",
  "detail": "<=300 chars, single line"}`. A new shared script
  `_shared/validate-implement-blocker.sh` validates it: file parses as a
  JSON object with exactly those keys; `kind` in the closed list; `detail`
  non-empty, single line, <=300 chars; and `task` names an *unchecked
  implementation* task id present in tasks.md at the pushed tip. Any failure
  means "no blocker" and the script prints the reason for the step summary.
- **Rationale**: FR-005 requires a shape-validated, agent-supplied field;
  cross-checking `task` against tasks.md gives deterministic code something
  it can re-derive, so a made-up blocker cannot stop the loop.
- **Alternatives**: a commit trailer (survives in git but is parsed from
  free text); a tasks.md annotation (agent edits the file the progress test
  reads, muddying FR-010a).

## D5. Stop-rule decision as a pure function

- **Decision**: the hand-off decision moves out of the two inline read-back
  blocks (primary cycle and retry arm, `implement.yml` ~1837 and ~2719) into
  one script `_shared/decide-implement-outcome.sh` taking
  `ok, truncated, impl_checked_base, impl_checked_tip, impl_unchecked_tip,
  converge_sha, iteration, max_iterations, blocker_valid` and printing
  `converged`, `progressed`, `handoff`, `stall-reason`. Both arms call it.
  `handoff=true` only if healthy, not converged, not progressed, no
  converge commit, and (`blocker_valid` or `iteration >= max_iterations`).
- **Rationale**: the two arms currently duplicate the rule; a fixture-driven
  pure function is what FR-012 and Principle VIII need.
- **Alternatives**: leave inline and patch both (the pasted-copy shape).

## D6. Stall comment

- **Decision**: the existing hand-off/exhausted reporting step on the
  lifecycle issue gains a stall paragraph (outstanding implementation count
  from `impl-unchecked-count`, reason from `stall-reason`) whenever the
  outcome ends with `impl-unchecked-count > 0`, at handoff or at the cap.
  Text built in the shared decide script's output, not in each workflow.

## D7. Finalize split

- **Decision**: finalize writes `finalize-remaining.md` deterministically
  from `maintainer-items` and `impl-unchecked-items` via a small shared
  renderer `_shared/render-remaining-work.sh` (two headed lists, a stall
  statement when the implementation list is non-empty, empty file when both
  are empty). The summarising agent keeps change summary and how-to-see-it
  only; its "write the remaining manual work" instruction is removed. The
  announce step uses a summary keyed to the case ("Maintainer steps" vs
  "Stalled with implementation outstanding"), and the PR body heading
  changes from "Remaining manual work" accordingly. The out-of-boundary
  result keeps its separate report (FR-009).

## D8. Tasks stage

- **Decision**: add a closed list of maintainer action kinds and the
  marker/placement/no-standing-instruction rules to the tasks stage prompt
  and to the project's tasks template guidance in the tasks workflow; a
  gate checks the prompt text lists the marker literal and every kind (the
  agent's compliance is covered by the downstream deterministic handling,
  not trusted). Maintainer tasks go in a final "Maintainer follow-up" phase.

## D9. Re-entry

- **Decision**: in `implement.yml`'s idempotency-guard step, when the
  recorded stage is `review` and the dispatch is manual, post a lifecycle
  comment (why nothing ran; comment on the implementation PR to re-enter)
  via the existing comment composite, in addition to the current skip. For
  maintainer-comment re-entry, the Maintainer Feedback cycle's start comment
  includes `max-iterations - iteration` cycles remaining, computed from
  spec-meta. No cap reset: unchanged code path.
- **Rationale**: FR-010/FR-011 are reporting-only; behaviour stays.
- **Note**: any new input on the published `implement.yml` is declared and
  additive (Principle VII); `is-manual-dispatch` is the likely one and will
  be named in tasks.

## D10. Gates and docs

- One new gate `verify-implement-stall-handoff.py` registered in the gate
  registry and `lint-workflows.yml`, running fixtures under
  `.github/scripts/fixtures/117-implement-stall-handoff/` through the three
  shared scripts (every failure branch: malformed JSON, bad kind, over-long
  detail, task not unchecked, task checked, zero-progress no blocker, cap,
  standing line forms, unsplit marker line, legacy untagged file). It also
  asserts both implement arms and finalize call the shared scripts and no
  copy of the rule reappears inline. Live docs (the implement-loop and
  finalize docs under `docs/`) are updated; spec 059 is not edited.
