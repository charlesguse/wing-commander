# Phase 0 Research: Clarify's Turn Budget Reflects the Work Clarify Actually Does

Every item below either resolves a mechanism question the spec leaves to
this plan (the arithmetic FR-001 asks for, but does not spell out to the
turn) or confirms an existing mechanism needs no change. No
`[NEEDS CLARIFICATION]` marker remains in spec.md — three clarifications
were already folded in during the clarify session (2026-09-25) — but one
genuine design decision (R1, the actual re-based number) was left to plan,
since "derived from the recorded run history" is a directive, not a
formula. R1 is called out below and in the completion comment as a
decision made without a fourth clarification round.

## R1: What is the re-based declared budget, and what is its reasoning?

**Decision**: Re-base clarify's `max-turns` default from `40` to `65`.
Accepted range: 39-61 counted turns (the three recorded runs). Resulting
ceiling (FR-003): `ceil(65 * 2.5) = 163` (up from `100`).

**Rationale**: The floor is fixed by Acceptance Scenario 1 (User Story
1) and SC-002: a run at the heaviest recorded consumption (61) must not
be reported over budget, and `over_intended` at the metrics-summary layer
fires on `counted >= budget` (`.github/actions/wing-commander-metrics-summary/action.yml`
lines 613-625) — so the new budget must be strictly greater than 61,
i.e. >= 62. A bare `62` would be reverse-engineered from the alert
threshold rather than the workload: only three of the trend window's ten
slots are populated so far, and the next healthy run landing at 62-64
turns — well within the variance the existing three-run spread already
shows (39, 45, 61) — would immediately regenerate the same
"true-but-repeated" alert this feature exists to retire (spec.md's Why
Priority for User Story 1). `65` is the smallest multiple of 5 clearing
that floor, giving ~6% margin over the observed maximum without inflating
the ceiling into the "formality" the Edge Cases section warns against: a
budget of `100` (2.5x the current one) would carry a ceiling of `250`,
more than 4x the heaviest observed run, for evidence that only supports
roughly a 1.6x move.

Re-verifying against the watchdog's own band arithmetic
(`watchdog.yml`'s `TURN_BUDGET_FILTER`, `.github/scripts/verify-turn-budget-collector.sh`):
`max-consumed-ceiling-fraction` over the cited window becomes
`61 / 163 = 0.374`, under the `WING_COMMANDER_TURN_BUDGET_CLIMB_FRACTION`
threshold of `0.6` (docs/setup.md) with room to spare — not a value that
just clears the line. `consecutive-at-or-over-budget` is `0` under the new
budget too (39, 45, 61 are all < 65), so neither trigger fires: SC-001
holds.

**Alternatives considered**:
- `62` (bare minimum to clear both checks) — rejected: zero margin,
  reverse-engineered from the alert rather than the workload (see above).
- `61` (the exact observed max) — rejected outright: `counted >= budget`
  means the run that produced the evidence would itself be flagged over
  budget, directly violating Acceptance Scenario 1.
- `100` or another 2x-and-up jump — rejected: oversizes the ceiling
  relative to the observed range (Edge Cases: "the ceiling stops being a
  meaningful stop and becomes a formality").
- Re-basing to the window's median (~45) rather than its max — rejected;
  the Edge Cases section names this trade-off explicitly and resolves it
  against the alert-suppression side: re-basing to the median "makes the
  alert fire every time the exception recurs," and 61 is this window's
  *only* evidence of the heavy case, not a contaminated outlier (the
  Assumptions section already treats the counted-turns measurements as
  accurate).

## R2: Where does the single declared-budget value live, and does changing it disagree with anything else?

**Decision**: The sole edit is `clarify.yml`'s `workflow_call.inputs.max-turns.default`
(currently `40`, `.github/workflows/clarify.yml` line ~29). No other file
declares a competing default: the consuming wrapper
(`wing-commander-2-clarify.yml`) does not override `max-turns`, so it
inherits the stage's own default (grepped; zero matches for
`max-turns`/`max_turns` in that wrapper). This is exactly FR-008's "single
setting that already declares clarify's turn budget" and FR-012's
"one value per stage per run": `wing-commander-turn-ceiling` (ceiling),
`wing-commander-metrics-summary` (reported metrics, over-budget flag,
80%-warning) and `wing-commander-agent-verdict` (over-budget verdict used
for the lifecycle-issue callout) all read the same `inputs.max-turns`
value clarify.yml passes them (`clarify.yml` lines 561, 676, 718, 746) —
already one value, already in lockstep. Nothing here needs new plumbing;
raising the default is sufficient.

**Alternatives considered**: A new repository variable
(`WING_COMMANDER_CLARIFY_MAX_TURNS` or similar) — rejected per Q2 (session
2026-09-25) and FR-008/SC-004: a new variable is a new published input
under constitution VII, which this feature is explicitly scoped to avoid.

## R3: Does raising the ceiling from 100 to 163 touch any other guard or gate?

**Decision**: No. The invalid-budget guard (empty/zero/negative/non-numeric
→ loud failure) lives entirely inside `wing-commander-turn-ceiling`'s
`Compute runaway ceiling` step (`.github/actions/wing-commander-turn-ceiling/action.yml`
lines 51-65) and is a function of whatever `intended-turns` value it
receives — it is exercised identically whether that value is `40` or
`65`, and this feature does not touch the action. FR-011/FR-004 hold
unchanged; Gate 22 (`verify-agent-verdict.py`) and Gate 23
(`verify-gate-23.py`) already prove every call site (clarify's included)
carries the ceiling/verdict/fail-loud wiring, and neither gate's fixtures
encode clarify's specific budget number, so raising it needs no fixture
change there.

**Alternatives considered**: none — this is a confirmation, not a choice.

## R4: What written procedure does FR-013/FR-014 require, and where does it live?

**Decision**: One new subsection in `docs/architecture.md`, immediately
following the existing "What a 'turn' is here" / ceiling explanation
(after the Gate 22/51 paragraph, docs/architecture.md lines ~244-294 —
the only place in the repository that already explains the
budget/ceiling/verdict mechanism end-to-end). The subsection states, in
order: (a) the evidence to read — a `turn-budget-trend` signal's
`facts.history` (the window's `{run, counted-turns, intended-budget}`
triples the collector already emits, `specs/046-watchdog-supervision-collectors/data-model.md`);
(b) the arithmetic — new budget = the smallest multiple of 5 strictly
greater than the window's maximum counted-turns, stated beside the
accepted range (min-max of the window) it was derived to cover; (c) the
cost consequence to check — the resulting ceiling,
`ceil(new_budget * 2.5)`, computed and stated in the same change, never
left implicit; (d) when to accept the trend instead: the window's
maximum is a single diagnosed-contaminated run (turns inflated by a cause
unrelated to real work, e.g. spec 037's denied-tool-call inflation) or the
band is `critical` with a rising `consecutive-at-or-over-budget` count
that a bigger budget would only relabel rather than explain — both cases
close the `pipeline-defect` as accepted rather than move the number,
matching the suppression mechanism spec 046 already ships (a closed
finding's fingerprint suppresses its band, `contracts/turn-budget-trend.md`).
The subsection's own worked example is this feature's clarify numbers
(39/45/61 -> 65, ceiling 163) — applying the stated arithmetic to the
cited history reproduces them, satisfying FR-014 by construction rather
than by a separate demonstration harness.

**Alternatives considered**: A new standalone runbook file (e.g.
`docs/turn-budget-trend.md`) — rejected; the repository has no
runbook-style doc directory today (only `adoption.md`, `architecture.md`,
`setup.md`, `agent-friendly-workflows.md`), and the mechanism this
procedure walks through is already explained in one place in
`architecture.md`, so a second document would either duplicate that
explanation or force a reader to jump between two files for one
procedure (CLAUDE.md: "shared logic/prose has exactly one home").

## R5: What is the one rule this feature adds, and what gate enforces it (FR-018)?

**Decision**: The rule FR-017 states directly — "documentation that
states a stage's declared budget... MUST agree with what the stage does"
— is the rule with no existing gate behind it (docs/adoption.md's
per-stage `max-turns` default has drifted from a workflow's real default
before with nothing catching it, structurally the same class of gap Gate
26's Sync Impact Report and CLAUDE.md's cost-line example both name). New
gate: `verify-stage-turn-budget-docs.py`, modeled on the existing
docs-vs-source consistency gates (`verify-versioning-refs.py`'s
WHY/WHAT-IT-CHECKS/WHAT-IT-DOES-NOT-CHECK/`--self-test` shape). For every
published stage workflow under `.github/workflows/` that declares a
`workflow_call.inputs.max-turns.default`, it parses that literal and the
corresponding `### <stage>` section's `Inputs` table cell in
`docs/adoption.md` (the ``max-turns` (number, `NNN`)`` fragment already
present for all nine stages that carry one — intake (50), clarify (40),
plan (110), tasks (60), implement (180), finalize (20), cleanup (20),
rebase (50), pr-conversation (40); see data-model.md for the full table)
and fails loudly, naming the stage and both values, on any mismatch. This
is deterministic (constitution IX): no model judges whether a doc and a
default agree.

**Alternatives considered**: Enforcing the same rule inside
`wc_published_stages.py`'s existing generic stage-discovery helper —
rejected; that module (confirmed via grep) enumerates stage files
structurally and is consumed by several unrelated gates (7, 22, 23,
stage-invariants, single-home-idioms), and this feature's rule is a
narrower docs-vs-one-input-default check that does not belong in a
shared discovery helper several other gates depend on for unrelated
purposes.

## R6: Does anything besides docs/adoption.md's clarify row need updating (FR-017's "no stale number left behind")?

**Decision**: No other file states clarify's specific budget number.
Grepped `docs/`, `README.md`, and `.github/scripts/` for a
clarify-attributed `40`: the only hit is `docs/adoption.md` line 1161
(the `Inputs` row). `docs/architecture.md` line 240 mentions "specify /
clarify" but only for model tier, not turn count. No gate fixture
hardcodes clarify's specific default (`verify-agent-verdict.py`'s `40`
references are generic verdict fixtures, not clarify-specific).
`wc_published_stages.py` discovers stage files structurally and does not
enumerate per-stage input defaults.

**Alternatives considered**: none — this is a confirmation search, not a
choice.
