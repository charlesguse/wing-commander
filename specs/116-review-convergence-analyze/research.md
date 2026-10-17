# Research: 116 Review Convergence and Fold-Time Analyze

No `[NEEDS CLARIFICATION]` markers remain in spec.md (the three clarify answers are recorded there). The decisions below fill planning-level gaps; those made without an owner answer are marked **(plan decision)**.

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

## D8 — Analyze step design **(plan decision)**
**Decision**: New composite `wing-commander-fold-analyze`, run after `fold-commit`, before `fold-dispatch`. Steps: (1) skip when fold section has no tasks; (2) run `anthropics/claude-code-action` with model `claude-sonnet-5-5`, `--max-turns` bounded (initial value 12, tunable constant), tools restricted to Read/Grep/Glob (no Bash, Edit, Write, web), prompt invoking `/speckit-analyze` with arguments scoping to the new fold section, spec content framed as data; (3) agent returns JSON per a schema (severity, category in {constitution-conflict, inconsistency, duplication, other}, fold task id, conflicting location, principle name when constitution); (4) a deterministic script validates the JSON and decides `hold` iff any finding has category `constitution-conflict`, or the step failed/mismatched schema; (5) outputs `decision`, `report-markdown`, `held-question`.
**Rationale**: FR-011..017, IX. Read-only tools satisfy FR-017 structurally. The vendored skill is used unmodified; its report is requested as the structured JSON through the arguments/output schema. If the vendored skill's own output cannot be forced to the schema, the agent is asked to restate its findings in the schema, and anything unparseable is treated as a step failure (FR-013).
**Alternatives**: running analyze after dispatch (rejected: builds one side first); a second wrapper per caller (rejected: duplicate).

## D9 — Hold protocol and release **(plan decision)**
**Decision**: On hold, the caller posts the owner question (marker `<!-- wing-commander-fold-hold: fold=<id> -->`) with three options (amend spec / drop task / proceed anyway; analyze-failure variant: proceed anyway / retry the check) and does not call `fold-dispatch`. The owner answers by comment; a maintainer-verified comment handler (reusing pr-conversation's existing authorization) resolves: *proceed* → dispatch; *drop* → a deterministic commit removes the fold section's task then dispatch; *amend* → wait for the spec PR amendment, then dispatch on the next lifecycle trigger; *retry* → rerun the check. Dispatch uses `fold-dispatch` unchanged except for an additive `skip-reason` pass-through is NOT needed — the caller simply withholds the call.
**Rationale**: FR-013/014, Constitution III/IV. Lowest new surface.
**Open implementation risk**: the exact comment-handler job placement is settled in tasks; if reusing `pr-conversation.yml` proves heavy, a small dedicated wrapper job is acceptable.

## D10 — Skill edit under `.claude/`
**Decision**: The `review-until-clean` edits (SKILL.md, `thrash_signals.py`) are in scope as repository changes made by the implement stage's normal PR flow; if the stage agent is denied writes under `.claude/` (Constitution V), the task is flagged for a human maintainer rather than worked around.
**Rationale**: Constitution V denies agent `Edit`/`Write` under `.claude/`.

## D11 — Gates
**Decision**: `verify-convergence-single-home.py` (flags re-implemented blame/churn/diff-size arithmetic or threshold literals outside the module; fixture per failure branch) and `verify-fold-analyze-wiring.py` (composite ordering in both callers, declared model, `--max-turns`, read-only tool list, `shell: bash` where in a container). Both registered in the gate registry and in `lint-workflows.yml` so `run-local-gates.py` runs them.
**Rationale**: Constitution VIII, FR-019, SC-007.
