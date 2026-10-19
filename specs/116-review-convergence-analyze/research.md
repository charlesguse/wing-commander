# Research: 116 Review Convergence and Fold-Time Analyze

No `[NEEDS CLARIFICATION]` markers remain in spec.md (the three clarify answers are recorded there). The decisions below fill planning-level gaps; those made without an owner answer are marked **(plan decision)**. D8 and D9 (the fold-time analyze check and its holds) moved to #1066 with Story 3 (owner decision 2026-10-19).

## D1 — One module for the arithmetic
**Decision**: `.github/scripts/wc_convergence.py` holds attribution, churn, growth, recurrence, the thresholds table and `decide()`. `thrash_signals.py` keeps its CLI and `--self-test` but delegates to it.
**Rationale**: FR-018/FR-010; the existing script is already correct and tested; moving rather than rewriting keeps SC-003 trivially true.
**Alternatives**: keep two copies with a parity test (rejected: drift is invisible until it diverges); put the module in the skill dir (rejected: workflows should not import from `.claude/`, and agents may not write there).

## D2 — Attribution by blame at the reviewed head, merges excluded
**Decision**: Reuse `Origins`/`blame_commits`: a line is loop-written when its blame commit is not an ancestor of the base, nor of round 1's head, and is a fold/implement/fixup commit after it. Commits reachable only through a merge from the base branch are classified `main`, using `git merge-base --is-ancestor` against the freshly fetched base each round (not a base pinned at round 1).
**Rationale**: Spec assumption + edge case "main merged between rounds"; the existing stale-base warning becomes a correction rather than a warning for the automated loops.
**Alternatives**: per-file attribution (rejected by #998).

## D3 — Round history storage **(plan decision)**
**Decision**: Persist each round's record (head SHA, finding fingerprint/file/line/attributable, in-scope count) in the same place the lifecycle gate already persists `folded_fingerprints`/`filed_fingerprints` (the round marker/report), extended additively; the board loop keeps its equivalent in its PR round marker. `decide()` is a pure function of that history plus git.
**Rationale**: No new datastore (Constitution III); stateless runs can rebuild history from markers.
**Alternatives**: a state branch/artifact (rejected: more moving parts, more permissions).

## D4 — Recurrence semantics
**Decision**: Ledger = fingerprints of findings a round folded (lifecycle) or fixed (board). Partition classifies a match as `recurrence`: it stays open, round is not `clean`, status is not `success`, and it is named. Dismissed-list matches are not recurrences. Fingerprint formula is unchanged (`wc_review_finding_fingerprint`).
**Rationale**: FR-001..003, edge case on dismissals.

## D5 — Line field and validation
**Decision**: Add optional `line` (integer ≥ 1) beside `file_path` in `fingerprint_basis`-adjacent finding evidence in both reviewers' output schemas. Deterministic code checks `1 ≤ line ≤ lines(file@head)`; otherwise unattributable and recorded. `line` is NOT part of the fingerprint (it would change dedup keys).
**Rationale**: FR-005; optional keeps the published schema backward-compatible.

## D6 — Thresholds home
**Decision**: A `THRESHOLDS` dict in `wc_convergence.py` (`min_round=3`, `self_inflicted_share=0.5`, `consecutive_churn_rounds=2`, `growth_ratio=0.5`); the 5-round budgets remain the workflow `env` values. Gate verifies the literal numbers appear nowhere else in workflows/skill prose scripts.
**Rationale**: FR-010.

## D7 — Stop behaviour
**Decision**: On `not-converging` at round ≥3, the loop takes the existing budget-exhaustion hand-off path, with stall reason text `not-converging` and the signal table. If budget exhausts the same round, the stop reason is the budget and tripped signals are still listed (spec edge case). Round 2: record only.
**Rationale**: FR-006..009; reuses the existing labelling and re-eligibility rule.

## D8 — Analyze step design
Moved to #1066 (Story 3).

## D9 — Hold protocol and release
Moved to #1066 (Story 3).

## D10 — Skill edit under `.claude/`
**Decision**: The `review-until-clean` edits (SKILL.md, `thrash_signals.py`) are in scope as repository changes made by the implement stage's normal PR flow; if the stage agent is denied writes under `.claude/` (Constitution V), the task is flagged for a human maintainer rather than worked around.
**Rationale**: Constitution V denies agent `Edit`/`Write` under `.claude/`.

## D11 — Gates
**Decision**: `verify-convergence-single-home.py` (flags re-implemented blame/churn/diff-size arithmetic or threshold literals outside the module; fixture per failure branch), registered in `lint-workflows.yml` so `run-local-gates.py` runs it. The analyze-wiring gate moved to #1066 with Story 3.
**Rationale**: Constitution VIII, FR-019, SC-007.
