# Phase 1 Data Model: An Honest Read-Failure Policy for board-stop-check's Closed Check

This feature has no database or application data model. Its "entities" are
values computed by deterministic shell and YAML expressions inside a
GitHub Actions composite action, and comment-text facts scanned by a gate
script — the workflow-native equivalent of a data model for this project
type (a CI/CD pipeline). This document names each one, its shape, where
it is computed, and the rules that relate them.

## Entities

### Lifecycle-issue state read (`state`, `is-open`) — pre-existing, unchanged

- **Shape**: `state` is `OPEN`/`CLOSED` (or the step fails); `is-open` is
  `"true"`/`"false"`.
- **Computed by**: `wing-commander-lifecycle-gate`'s `check` step
  (unchanged by this feature — FR-006 forbids touching it).
- **Read by**: `wing-commander-board-stop-check`'s `closed-check` step,
  only when `inputs.check-issue-closed == 'true'` (today: `prove` only).

### Read-failure policy (fail-loud) — the subject of FR-002

- **Shape**: not a runtime value — a structural property of the
  `closed-check` step: absence of `continue-on-error: true`.
- **Before this feature**: `continue-on-error: true` present; a total read
  failure left `closed-check.outputs.is-open` empty and the step marked
  `outcome: failure` / `conclusion: success` (tolerated), so the composite
  and the calling job continued.
- **After this feature**: no `continue-on-error`; a total read failure
  marks `closed-check.outcome: failure` / `conclusion: failure`, which
  fails the calling `uses: ./.github/actions/wing-commander-board-stop-check`
  step and therefore the `prove` job (FR-002).

### Kill-switch/stop-request check (`check` step, reordered) — FR-003's subject

- **Shape**: step id `check`; outputs `paused` (`"true"`/`"false"`).
- **Computed by**: `INITIAL_PAUSED` (the caller's resolved
  `vars.WING_COMMANDER_BOARD_LOOP_PAUSED` comparison) OR'd with
  `find_stop_request()`'s result (a maintainer stop comment, via
  `board_stop_check.py`), plus the `gh run cancel` side effect on a
  genuinely different, still-running earlier run (unchanged logic; see
  `action.yml`'s existing extensive inline comments on the cancel guard,
  untouched by this feature).
- **Ordering rule (new)**: runs *first* in the composite's step sequence,
  unconditionally (no `if:` gating on `closed-check`), and no longer reads
  any `steps.closed-check.*` value (D1). This is what makes FR-003 hold:
  the kill-switch re-check and the cancel side effect happen regardless of
  whether `closed-check` later fails.

### Composite-level paused signal (`outputs.paused`) — FR-002/FR-003's join point

- **Shape**: `"true"`/`"false"` (unchanged published shape, Constitution
  VII).
- **Computed by**: the composite's own `outputs:` mapping, as an OR of two
  independent facts (D2):
  `steps.check.outputs.paused == 'true'` OR (`inputs.check-issue-closed ==
  'true'` AND `steps.closed-check.outputs.is-open == 'false'`).
- **Relates to**: for the six callers that never pass
  `check-issue-closed: "true"`, the second clause is always false by
  construction, so `paused` is exactly `steps.check.outputs.paused` — byte-
  identical behavior to today. For `prove`, `paused` is `true` whenever
  either the kill-switch/stop-request check fires OR the issue read
  succeeded and reports CLOSED. It is **not** `true` merely because the
  read failed — a failed read fails the *job*, via `closed-check`'s own
  unguarded exit, rather than resolving `paused` either way (this is the
  FR-002/FR-003 distinction: "stops the job" is not the same signal as
  "paused").

### Read-failure visibility (`closed-check-note` step, new) — FR-004's subject

- **Shape**: one `::error::` line, no output.
- **Computed by**: a new composite step, `if: steps.closed-check.outcome ==
  'failure'`, naming the issue number (from `inputs.issue-number`) and the
  fail-loud consequence.
- **Relates to**: layered on top of `lifecycle-gate`'s own `::error::`
  (which names *why* the read failed); this step names *what the caller's
  policy did about it* — the piece `lifecycle-gate` cannot state because it
  has no knowledge of its callers' individual tolerance policies (D3).

### Errexit premise (comment-text fact) — FR-007/FR-008's subject

- **Shape**: free text inside a `#`-comment block in a `.github/workflows/
  *.yml` or `.github/actions/**/action.yml` file.
- **Two states**: **false** ("a `shell: bash` step runs without errexit" /
  "`set -uo pipefail` clears `-e`" — the claim FR-007 forbids) and **true**
  (the corrected, negation-shaped statement — "does not clear `-e`",
  "errexit is already active" — D6's polarity distinction).
- **Canonical instance**: the new gate script's module docstring (D4) — the
  one place the full mechanism is stated in prose.
- **Site instances**: five corrected comments (the `board-stop-check`
  rewrite under FR-001, plus `board-loop.yml`, `metrics-persist.yml`,
  `implement.yml`, `lint-workflows.yml` under FR-007), each stating its own
  local consequence and pointing at the canonical instance rather than
  restating the mechanism (FR-008).
- **Validation rule**: FR-009's gate scans both directories (D5), applies
  the phrase-pattern + negation-window + quoted-span rule (D6), and fails
  naming the file and line of any surviving false instance — including a
  newly introduced one (SC-002, SC-003).

### Gate-24 scope boundary (`WORKFLOWS_GLOB` documentation) — FR-012's subject

- **Shape**: a docstring paragraph in `verify-gate-24.py`, not a runtime
  value.
- **States**: what `WORKFLOWS_GLOB` covers (`.github/workflows/*.yml`
  only), what it does not (`.github/actions/**`), and a pointer to the
  filed widening-tracker issue (D8).
- **Relates to**: FR-009's gate (D5) is the worked counterexample this
  paragraph can cite — "unlike this gate, `verify-errexit-claim-comments.py`
  scans both directories, because the mistake it exists to catch shipped in
  an action file."

## Relationships

```
inputs.initial-paused ──┐
find_stop_request() ────┼─▶ check.outputs.paused (unconditional, step 1)
gh run cancel (side effect, unconditional)

inputs.check-issue-closed == 'true' ──▶ closed-check (step 2, fail-loud)
                                          ├─▶ success: outputs.is-open
                                          └─▶ failure: composite step fails
                                                        → prove job fails
                                                        → closed-check-note
                                                          (step 3, visibility)

check.outputs.paused, inputs.check-issue-closed, closed-check.outputs.is-open
                                        ─▶ composite outputs.paused (OR)

prove job: steps.killswitch-recheck.outputs.paused, (implicit success())
                                        ─▶ close-or-redrive steps run/skip
```

```
comment text (5 sites) ──▶ verify-errexit-claim-comments.py (Gate <N>)
                             ├─▶ phrase-pattern match
                             ├─▶ negation-window exclusion
                             └─▶ quoted-span exclusion
                           ─▶ pass / ::error:: file:line

Gate 47 pointer sources (4 of the 5 sites, workflow files only)
                           ─▶ target exists + topic overlap ─▶ pass/fail
```

## State: what does *not* change

- `wing-commander-lifecycle-gate/action.yml` — untouched (FR-006).
- `watchdog.yml`'s `Collect: annotations` step and the diagnose
  classifier — untouched (FR-005 is satisfied by construction, FR-006
  forbids a filtering remedy).
- The composite's published input/output names and shapes
  (`token`, `cancel-token`, `issue-number`, `bot-login`, `initial-paused`,
  `check-issue-closed` → `paused`).
- The six non-`prove` call sites' observable behavior — algebraically
  identical before and after (D2's OR clause is always false for them).
- `action.yml:171`'s `gh run cancel ... failed: $cancel_error`
  interpolation (FR-011, left for spec 087/#621).
- `find_stop_request()`, `is_stop_command()`, the cancel-target workflow-
  path guard, and every other piece of `check`'s existing logic besides
  the `ISSUE_IS_OPEN` removal (D1).
