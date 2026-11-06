# Research: Implement Finishes Its Tasks

No `[NEEDS CLARIFICATION]` markers remain in spec.md; all clarifications are recorded there. The decisions below resolve plan-level choices.

## D1 — Where classification lives
- **Decision**: Extend `count-tasks-checkboxes.sh` (spec 117's one home). Line classes, first match wins: standing → folded review finding → maintainer (tag) → deterministic-unbuildable → buildable. New outputs: `buildable-checked-count`, `buildable-unchecked-count`, `buildable-unchecked-ids`, `buildable-unchecked-items`, `fold-unchecked-count`, `fold-unchecked-items`; maintainer items now include deterministic-unbuildable lines.
- **Rationale**: FR-017 demands no second counter; finalize, the review gate and implement then read the same composite output (FR-010 "same classification").
- **Alternatives**: a separate classifier script per consumer (rejected: drift); making existing `impl-*` outputs change meaning (adopted for `impl-*` as the buildable view *plus* folds, see D2, to keep existing callers working).

## D2 — Fold lines and convergence
- **Decision**: Folds are recognised by the exact line shapes `- [ ] Review finding: ` and `- [ ] Recurring review finding: ` (after any id/tag run). `impl-*` counts keep meaning "everything implement must tick" (buildable + folds) so convergence is unchanged (FR-009); new `buildable-*` counts exclude folds and drive the cap, the progress count and FR-010.
- **Rationale**: Smallest change to `decide-implement-outcome.sh`: convergence keeps `impl-unchecked`; the cap hand-off and progress use `buildable-*`. Cap with only folds unchecked is not a hand-off (spec edge case).
- **Alternatives**: redefine `impl-*` to exclude folds (rejected: would converge with folds open, violating FR-009).

## D3 — Deterministic unbuildable classes (FR-004/005)
- **Decision**: Write-boundary class: call `classify-out-of-boundary-tasks.sh` (no second pattern list). Post-merge proof and drill classes: a small anchored pattern list inside `count-tasks-checkboxes.sh` (e.g. leading verb "re-drive", "prove after merge", "post-merge", "drill") applied to the text after the tag run; ambiguity falls to buildable (FR-007). Gate-suite class: only when the cycle's gate-suite readiness input says not ready (FR-008); default is buildable.
- **Rationale**: Patterns are narrow and anchored so a false positive is rare; false negatives only cost a cycle, as today.
- **Alternatives**: agent-only tagging (rejected, constitution IX); broad keyword matching (rejected: ambiguity must count as buildable).

## D4 — Readiness input for the gate-suite class
- **Decision**: The script takes an optional env `GATE_SUITE_READY` (default `true`). implement.yml passes the cycle-start gate-suite job's result. Base and tip are classified with the same value so counts are comparable.
- **Rationale**: Follows the pipeline's own per-cycle determination (FR-008); #1077 made the suite run on main, so the default path rarely triggers.

## D5 — Cap and blocker hand-off (FR-015/015a)
- **Decision**: In `decide-implement-outcome.sh`, `handoff=true` for the cap or a validated blocker only when `buildable-unchecked > 0` (plus dropped ids). If only folds and/or maintainer-only lines remain at the cap, the outcome is "continue to finalize" (converged for FR-014 when nothing but maintainer-only is left). The existing `stage:stalled` path is reused; implement's resumed-cycle step removes `stage:stalled` (extend "Flip stage label (first cycle)" to every cycle). The cap does not reset; the guard stays recorded+1.
- **Rationale**: Reuses spec 117/059 machinery; `lifecycle:held` swap deferred until #1102 merges (noted in tasks).

## D6 — Finalize and review-gate wait (FR-010)
- **Decision**: finalize.yml's existing tip checkbox-count step gains a refusal step before PR creation when `buildable-unchecked-count > 0`, posting the remaining list and failing closed with no PR. lifecycle-review-gate.yml's select step reads the same composite at the PR head and skips with a logged reason.
- **Rationale**: Both already read the tip tasks.md; the composite is the shared view.

## D7 — Prompt change and cycle outcome (FR-001–003)
- **Decision**: Edit the implement prompt (two copies in implement.yml, lines ~1359 and ~2375: dedupe into one shared prompt fragment if a composite already holds prompt text; otherwise edit both and extend the existing byte-compare gate) to state that a phase checkpoint is not a stopping point while push-per-phase stays. Cycle outcome line (ticked, remaining, turns used) is computed by `wing-commander-implement-outcome` from base/tip counts and the run's execution record, appended to the lifecycle issue comment and metrics record.
- **Alternatives**: editing the vendored implement skill (rejected: vendored, `.claude/` is agent-denied and gets overwritten by spec-kit updates).

## D8 — One-time migration (FR-018)
- **Decision**: `migrate-stranded-review-lifecycles.sh` plus a manual `workflow_dispatch` job (maintainer-run after merge). It lists open lifecycle issues at spec-meta stage `review`, computes `buildable-unchecked` at each spec branch tip, and for qualifying ones commits `stage: stalled` (iteration preserved) via the hardened push path, adds `stage:stalled`, and comments once. Idempotency marker: the stage already `stalled` plus an existing hand-off comment marker.
- **Rationale**: Dispatch-driven keeps it provable (`prove-after-merge`) and avoids hidden side effects at merge.

## D9 — Decisions made without clarification
None required; spec has no open markers.
