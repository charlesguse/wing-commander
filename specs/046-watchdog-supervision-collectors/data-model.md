# Phase 1 Data Model: Deterministic Watchdog Collectors for the Supervision Gap

No application database. Every entity below is either the shape of a JSON
document already flowing through `watchdog.yml`'s existing pipeline (a
signal, a collector outcome, a Finding's `normalizedFacts`), or a
read-only view over data another feature already persists (spec 043's
metrics record). This is spec.md's Key Entities section made concrete
against research.md's decisions.

## Turn-budget observation (per-run signal)

Emitted by `collect-turn-budget`, one per inspected run whose stage
declares a turn budget and whose turn values are available (FR-008,
FR-014).

```json
{
  "source": "turn-budget",
  "class-hint": null,
  "facts": {
    "stage": "implement",
    "run": "<workflow_run_id>",
    "counted-turns": 226,
    "intended-budget": 180,
    "enforced-ceiling": 450,
    "consumed-ceiling-fraction": 0.502,
    "band": "critical"
  }
}
```

- Emitted only when `counted-turns >= intended-budget` (FR-010's own
  gating condition) — a run comfortably under budget produces no signal
  at all (Acceptance Scenario 6).
- `class-hint: null` (research.md R5) — this signal alone never files; it
  exists only as evidence a cross-run Finding may cite.
- `band` is the same severity band the collector computes for the
  cross-run signal below from this same window, stamped onto the per-run
  signal too (`null` when neither trigger is met this window).
- Signal-id identity (research.md R11, corrected by T041 and T042):
  `kind: "turn-budget-trend"` (the SAME kind string as the cross-run
  signal below, not its own `"turn-budget-observation"` kind — T042),
  `ident: {stage, band}` — **not** `{stage, run}`. This signal is always
  cited alongside the trend signal in one Finding (its only job, per R5),
  so its id must not just be stable run-to-run (T041) but IDENTICAL to
  the trend signal's own id for the same `{stage, band}` (T042): a
  Finding may cite the trend signal alone, this signal alone (when the
  latest run in the window is itself under budget, so no per-run signal
  exists to cite), or both, and `Compute fingerprint`'s `unique` over
  cited ids only collapses those three citation subsets to one basis
  when the two signals' ids are literally equal — sharing `{stage, band}`
  but differing kind strings still hashes to two different ids and
  reopens FR-012's "one accumulating finding" depending on which subset
  diagnose happened to cite that run. See `contracts/turn-budget-trend.md`'s
  "Why band, not magnitude, is the identity" section for the base
  reasoning, and T042 in tasks.md for the citation-subset failure this
  shared-kind fix closes.

## Budget trend (cross-run signal)

Emitted by `collect-turn-budget`, at most one per inspected run, only
when the stage's recent history (the most recent
`WING_COMMANDER_TURN_BUDGET_HISTORY_WINDOW` records for that stage,
oldest-to-newest) satisfies at least one of the two configured triggers
(FR-011), and only when research.md R4's closed-fingerprint pre-check
finds no existing closed match for the resulting band.

```json
{
  "source": "turn-budget-trend",
  "class-hint": "turn-budget-trend",
  "facts": {
    "stage": "implement",
    "band": "critical",
    "window-size": 10,
    "consecutive-at-or-over-budget": 3,
    "max-consumed-ceiling-fraction": 0.62,
    "headroom-remaining-fraction": 0.38,
    "history": [
      {"run": "<id-1>", "counted-turns": 160, "intended-budget": 180},
      {"run": "<id-2>", "counted-turns": 197, "intended-budget": 180},
      {"run": "<id-3>", "counted-turns": 226, "intended-budget": 180}
    ]
  }
}
```

- **Severity band** (research.md R4), a three-value ordinal computed
  fresh every run from the current window, never carried forward from a
  prior run's classification:

  | Band | Condition |
  |---|---|
  | `watch` | `consecutive-at-or-over-budget >= CONSECUTIVE_TRIGGER`, climb-fraction condition not met |
  | `elevated` | `max-consumed-ceiling-fraction >= CLIMB_FRACTION`, consecutive condition not met |
  | `critical` | both conditions met in the same window |

  A window meeting neither condition emits no cross-run signal at all.

- Signal-id identity (research.md R11): `kind: "turn-budget-trend"`,
  `ident: {stage, band}` — **not** the run id, **not** the specific turn
  counts. This is the field that makes every run extending the same
  trend at the same band hash to the same signal id, and therefore the
  same fingerprint, and is the entire mechanism behind FR-012's "one
  accumulating finding" and FR-015's "closure is acceptance" — see
  `contracts/turn-budget-trend.md` for the full state walkthrough.
- `headroom-remaining-fraction` (FR-013: "the remaining headroom" as a
  monitored, reported quantity) is `1 - max-consumed-ceiling-fraction`,
  computed once here rather than left for a reader to derive.
- Suppression (research.md R4, step 3): before emitting,
  `collect-turn-budget` computes the fingerprint this signal *would*
  produce (`sha256("turn-budget-trend|signals:" + this-signal's-id)`,
  identical formula to the live `Compute fingerprint` step — gate-diffed
  against it, `contracts/gate-coverage-046.md`) and checks
  `gh issue list --label pipeline-defect --label "🐕 · turn-budget-trend"
  --state closed --json body` for a body containing that fingerprint. A
  match suppresses this signal for this run entirely (collector outcome
  is still `ok` — a suppressed signal is not a collector failure).

## Cost-line claim

Emitted by `collect-cost-report`, at most one signal per condition per
inspected cost-bearing stage run (FR-016, FR-017).

```json
{"source": "cost-report", "class-hint": "cost-line-missing",
 "facts": {"stage": "plan", "run": "<workflow_run_id>",
           "cost-available": true, "lifecycle-comment-found": false}}
```

```json
{"source": "cost-report", "class-hint": "cost-line-malformed",
 "facts": {"stage": "implement", "run": "<workflow_run_id>",
           "observed-text": "Cost: $COST_LINE · 40 turns",
           "expected-pattern": "currency amount, 2dp if >= $1 else 4dp (research.md R8)"}}
```

- `cost-line-missing`: metrics record says `cost_available: true` for
  this run, but no lifecycle-issue comment attributable to this run
  carries a parseable cost figure (spec.md edge case: a stage that posted
  no comment at all for the run is a missing cost line whenever the
  metrics record marks cost available).
- `cost-line-malformed`: a cost figure is present but its dollar-amount
  substring fails the magnitude-appropriate regex from research.md R8.
  `observed-text` carries the exact string found (FR-018).
- No signal when `cost_available: false` (not cost-bearing, or genuinely
  unavailable), the stage is not cost-bearing at all, or a well-formed
  figure is present regardless of amount (FR-019).
- Signal-id identity: `kind: "cost-line-claim"`,
  `ident: {run, stage, claim-type}` (`claim-type` ∈ `missing`\|`malformed`)
  — distinct per run, since a recurring formatting defect across many
  runs of the same stage is still a distinct instance each time (unlike
  the turn-budget trend, there is no "same trend, don't reopen" behavior
  specified for this class — FR-032 leaves dedup's existing per-instance
  behavior as the correct one here).

## Narrative claim

Emitted by `collect-final-pr-claims`, at most one signal per mismatched
claim shape, only on finalize-stage runs (FR-008, FR-021–FR-024).

```json
{"source": "final-pr-claims", "class-hint": "narrative-drift",
 "facts": {"pr": 301, "claim-type": "tasks",
           "claimed-value": 42, "actual-value": 41,
           "actual-source": "tasks.md checked-box count on the PR head ref"}}
```

- `claim-type` ∈ `tasks` \| `commits` \| `tests`.
- `actual-source` is a free-text citation of where the ground truth came
  from (FR-022's "the source the actual value was derived from") —
  `"tasks.md checked-box count..."`, `"git rev-list --count <base>..<head>"`,
  or `"fixture files added under */fixtures/* between base and head"`
  (research.md R7).
- A claim shape the regex parser cannot match produces no signal at all
  (FR-023) — this is a parser miss, not a `facts.actual-value: null`
  signal; nothing is emitted for it.
- A claim that matches ground truth produces no signal (FR-024).
- Signal-id identity: `kind: "narrative-claim"`, `ident: {pr, claim-type}`
  — stable across re-inspections of the same PR revision so a
  re-triggered watchdog run reports "recurrence," not "new," via the
  ordinary dedup path, while a later PR revision with a *different*
  mismatch on the same claim type still gets a `facts.claimed-value`
  change reflected in the (unconstrained) signal facts, even though the
  fingerprint identity itself does not change until the class or cited
  signal id changes.
- **Issue-filing**: `narrative-drift` is the one class routed by
  research.md R9's new `Determine issue-filing eligibility` step to skip
  `Ensure pipeline-defect issue` entirely — it still fingerprints and
  dedup-searches (so the lifecycle report correctly says "new" vs.
  "recurrence"), it just never creates or reopens a tracked issue
  (FR-025), and is excluded from SC-007's precision window by
  construction (no issue is ever filed for it to be measured against).

## Spec-number claim

Emitted by `collect-spec-collision`, at most one signal per contested
number, only on intake-completion runs whose own allocated number is one
of the colliding claimants (FR-004's attribution invariant: the inspected
run must own the artifact the signal describes — here, the number it
itself just allocated).

```json
{"source": "spec-collision", "class-hint": "spec-number-collision",
 "facts": {"number": "046",
           "claimants": [
             {"kind": "open-pr", "pr": 301, "branch": "spec-draft/046-watchdog-supervision-collectors"},
             {"kind": "open-pr", "pr": 305, "branch": "spec-draft/046-a-different-feature"}
           ]}}
```

- Two claimant `kind`s: `"open-pr"` (an open spec-draft/spec PR whose
  branch name's numeric prefix matches) and `"main-directory"` (a
  `specs/NNN-*` directory already on the default branch).
- A PR never collides with itself (FR-028) — claimants are deduplicated
  by PR number/directory path before the two-or-more check.
- No signal when every open spec PR carries a distinct number and none
  collides with an existing `specs/` directory (FR-028).
- Signal-id identity: `kind: "spec-number-claim"`,
  `ident: {number, sorted-claimants}` — the same two claimants observed
  again on a later run hash to the same id, so FR-029's "accumulates
  evidence rather than a second finding" falls out of the existing,
  unmodified fingerprint/dedup mechanism (the same free mechanism R4
  relies on for the turn-budget trend, applied here without needing R4's
  extra suppression step — a collision has no "acceptance by closure"
  requirement in spec.md, so the ordinary `match-closed` → reopen
  behavior is the *correct*, wanted behavior for this class: an
  unresolved number collision reopening after a maintainer closed it
  prematurely is exactly what should happen).

## Collector outcomes

Each of the four new collectors follows the existing
`collector-outcomes.json` shape exactly:
`{"collector": "collect-turn-budget", "outcome": "ok"}` /
`{"outcome": "failed"}`. `"failed"` is reserved for a genuine read failure
(the metrics-branch fetch errors, the `gh pr list`/`gh issue list` calls
error) — never for "the source produced nothing for this run" (FR-007),
which is `"ok"` with zero signals emitted.

| Collector | `"ok"` with zero signals | `"failed"` |
|---|---|---|
| `collect-turn-budget` | Under budget; no history; no trigger met; suppressed match | Metrics-branch `git show` errors when the branch exists; per-run artifact read errors |
| `collect-cost-report` | Not cost-bearing; well-formed line present | Lifecycle-issue comment listing (`gh api .../comments`) fails |
| `collect-final-pr-claims` | Not a finalize run; no parseable claims; all claims match | PR-body fetch, `tasks.md` read, or commit-range read fails |
| `collect-spec-collision` | Not an intake run; no collision involving this run's own number | `gh pr list` or the `specs/` directory listing fails |

## `normalizedFacts` mapping table (research.md R10)

Restated here as the data contract the evidence-validity gate's per-class
required-key table (a new row per class, additive) checks against:

| Class | Required `normalizedFacts` keys |
|---|---|
| `turn-budget-trend` | `stage`, `expected`, `actual` |
| `cost-line-missing` | `stage`, `expected`, `actual` |
| `cost-line-malformed` | `stage`, `expected`, `actual` |
| `narrative-drift` | `stage`, `expected`, `actual` |
| `spec-number-collision` | `spec`, `expected`, `actual` |

## Gate fixtures (checked-in test data, SC-002)

Every failure branch each new collector or routing step ships needs at
least one fixture, following the existing convention (short-string
fixtures inline in a bash gate's own source for a copied-jq-filter check,
mirroring `verify-denied-tool-collector.sh`; a `fixtures/` directory for
JSON-shaped test data, mirroring spec 043's `fixtures/metrics-record-schema/`):

| Fixture | Used by |
|---|---|
| A stage history climbing 160/180 → 197/180 → 226/180 against ceiling 450 | `verify-turn-budget-collector.sh` — positive: `critical` band |
| A stage history with 3 consecutive at-or-over-budget runs but low ceiling-fraction | positive: `watch` band |
| A stage history under both thresholds | negative: no cross-run signal |
| A run whose metrics record marks `turns.available: false` | negative: no per-run signal, collector outcome `ok` |
| A `pipeline-defect` issue closed with the `watch`-band fingerprint already in its body, plus a new run still in `watch` | `verify-turn-budget-suppression.sh` — suppression fires |
| The same closed `watch`-band issue, plus a new run now computing `critical` | escalation fires (no suppression) |
| A run whose metrics record says `cost_available: true` with no attributable lifecycle comment | `verify-cost-report-collector.sh` — `cost-line-missing` |
| A lifecycle comment with `"Cost: $COST_LINE · ..."` (the literal #272 leak shape) | `cost-line-malformed` |
| A lifecycle comment with a well-formed `$0.0042` (sub-$1, 4dp) | negative — must NOT fire under research.md R8's magnitude-aware pattern |
| A final PR body claiming a task count off by one from `tasks.md`'s checked-box count | `verify-final-pr-claims-collector.sh` — `narrative-drift` (tasks) |
| A final PR body claiming a commit count that disagrees with `git rev-list --count` | `narrative-drift` (commits) |
| A final PR body claiming a test count that disagrees with new fixture-file count | `narrative-drift` (tests) |
| A final PR body whose claim text does not match any recognized shape | negative — no signal (FR-023) |
| A narrative-drift Finding reaching `triage` | `verify-narrative-drift-routing.sh` — `issueless: true`, `Ensure pipeline-defect issue` skipped, lifecycle report still posts |
| Two open spec PRs with the same numeric branch prefix | `verify-spec-collision-collector.sh` — collision (`open-pr` × `open-pr`) |
| One open spec PR whose number matches an existing `specs/` directory on main | collision (`open-pr` × `main-directory`) |
| Every open spec PR with a distinct number | negative — no signal |
| A run whose conclusion is `skipped`/`cancelled` | negative, all four collectors — attribution invariant (FR-004) |
