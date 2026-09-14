# Contract: Turn-budget trend accumulate/escalate state machine

This is the plan's most novel mechanism (research.md R4) and the one
piece other implementers are most likely to get subtly wrong, so it gets
its own contract: a full state walkthrough, stated as a sequence of
concrete runs, cross-checked against every acceptance scenario in
spec.md's User Story 1.

## Actors

- **`collect-turn-budget`** (this feature): computes a severity band per
  run from the stage's recent history, and decides whether to emit the
  `turn-budget-trend` signal for that band.
- **`Stamp signal ids`** (existing, unmodified mechanism; gains one row):
  hashes `{stage, band}` into a signal id.
- **`Compute fingerprint`** (existing, unmodified): hashes
  `class + "|signals:" + sorted-joined-cited-signal-ids`.
- **`Dedup search`** (existing, unmodified): looks up that fingerprint
  among `pipeline-defect` issues labeled `🐕 · turn-budget-trend`.
- **`Ensure pipeline-defect issue`** (existing, unmodified): creates on
  `none`, comments on `match-open`, reopens-and-comments on
  `match-closed`.

Nothing above this list changes. The only new code is
`collect-turn-budget`'s own pre-emptive read, described below.

## Walkthrough

**Run 1** — stage `implement`, history `[160/180]`. Neither trigger met
(1 consecutive run, low ceiling fraction). No cross-run signal. (Matches
Acceptance Scenario 1: the per-run signal alone files nothing.)

**Run 2** — history `[160/180, 197/180]`. Still under both triggers
(2 consecutive, not yet 3). No cross-run signal.

**Run 3** — history `[160/180, 197/180, 226/180]`, ceiling 450, every run
at or over its own budget (per spec.md's own motivating numbers). Three
consecutive at-or-over-budget runs meets `CONSECUTIVE_TRIGGER=3`;
`226/450 = 0.50 < 0.6` does not meet `CLIMB_FRACTION`. Band = `watch`. `collect-turn-budget` computes
the fingerprint `watch` would produce, finds no closed match, emits.
`Stamp signal ids` → id `A = hash("turn-budget-trend"|{stage:implement,
band:watch})`. `Compute fingerprint` → `FP_watch = hash("turn-budget-trend|signals:A")`.
`Dedup search` → `none`. `Ensure pipeline-defect issue` → **creates**
issue #400. (Matches Acceptance Scenario 2.)

**Run 4** — a fourth consecutive at-or-over-budget run, still under the
climb fraction. Band is still `watch` (same conditions, same window
shape — the window is the most recent 10, so it may drop run 1 and gain
run 4, but the *band* computed from the current window is unchanged).
Signal id is again `A` (identity is `{stage, band}`, not the specific
runs in the window). Fingerprint is again `FP_watch`. `Dedup search` →
`match-open` (#400 is still open). `Ensure pipeline-defect issue` →
**comments** on #400 — the new run's evidence accumulates onto the same
issue. (Matches Acceptance Scenario 3.)

**Maintainer closes #400** — accepting the `watch`-band trend as known,
tolerable for now.

**Run 5** — a fifth consecutive at-or-over-budget run, still under the
climb fraction. Band is still `watch`. `collect-turn-budget`'s
suppression pre-check computes `FP_watch` itself and searches
`--state closed` for it — **finds #400**. **Emits no cross-run signal for
this run.** No Finding, no dedup search, no reopen. (Matches Acceptance
Scenario 4: closed stays closed, nothing new opens.)

**Run 6** — the window's max consumed-ceiling-fraction crosses 0.6 for
the first time (e.g. a run at 280/450 turns). Both triggers now met. Band
= `critical` (research.md R4's three-value ladder: `watch` alone doesn't
satisfy this, `elevated` alone doesn't either — `critical` requires
both). `collect-turn-budget`'s suppression pre-check computes
`FP_critical = hash("turn-budget-trend|signals:" + hash("turn-budget-trend"|{stage:implement,band:critical}))`
— a value that has **never been closed** (it has never been filed at
all). No suppression. Emits. `Dedup search` → `none`. `Ensure
pipeline-defect issue` → **creates** a new issue, #412, distinct from
#400. (Matches Acceptance Scenario 5: escalation into a higher band files
exactly one new finding, and #400 is not touched.)

## Why band, not magnitude, is the identity

If `ident` instead embedded the run's own counted-turns value (e.g.
`{stage, band, counted-turns: 226}`), every run in the walkthrough above
would produce a distinct signal id, hence a distinct fingerprint, hence
`Dedup search` would return `none` every single time — every run would
open its own issue, which is exactly the "one finding per run" failure
mode FR-012's Independent Test names and rejects. Band-as-identity is not
an optimization; it is the mechanism.

## Why this needs no change to `Dedup search` or `Ensure pipeline-defect issue`

Both steps' behavior is a pure function of `(dedup_outcome, class)` today,
and no branch in either one needs to know or care that this class exists.
The behavior spec.md requires (closed = accepted, no reopen; escalation =
new finding) is produced entirely upstream of them, by which fingerprint
the collector chose to compute and whether it chose to emit at all. This
is deliberate: FR-032 forbids modifying "the dedup rules," and this
design satisfies FR-015 while being invisible to those rules — from
`Dedup search`'s point of view, run 5 above simply never happened (no
Finding reached it), and run 6 looks exactly like any other class's first
occurrence.

## Fixture-gate requirement (constitution VIII / SC-002)

`verify-turn-budget-suppression.sh` MUST embed a byte-identical copy of
both formulas this collector depends on — `Stamp signal ids`' hash
construction and `Compute fingerprint`'s concatenation — and MUST be
diffed against the live `watchdog.yml` steps the same way gate 5 already
diffs `verify-denied-tool-collector.sh`'s copied jq filter against the
live `collect-execution-output` step. A drift between the collector's
copy and the real formula would silently break suppression (every run
would appear to have a "closed match" for the wrong fingerprint, or none
for the right one) with no test failure to catch it otherwise —
exactly the failure class constitution VIII exists to close.
