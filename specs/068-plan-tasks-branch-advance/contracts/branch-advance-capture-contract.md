# Contract: `wing-commander-branch-advance` (new composite action)

`.github/actions/wing-commander-branch-advance/action.yml` — the single
home (FR-011) for the "after"/"commits" half of the branch-advance
capture, consumed by `implement.yml` (refactored from its existing
inline step) and the two new call sites this feature adds to `plan.yml`
and `tasks.yml`. Not part of the `workflow_call` published surface
(constitution VII) — an internal implementation detail resolved through
each stage workflow's own self-checkout, the same status
`wing-commander-metrics-summary` already has.

## Inputs

| Name | Required | Description |
|---|---|---|
| `branch` | yes | The branch to measure. Passed straight through to the caller's own record-emission call afterward — this composite does not interpret it beyond using it as a `git fetch`/`rev-parse` target. |
| `before-sha` | no (default `''`) | The caller's already-resolved "before" point. |
| `before-sha-available` | no (default `'false'`) | `'true'` when the caller successfully resolved `before-sha`. |

## Outputs

| Name | Description |
|---|---|
| `after-sha` | `branch`'s tip as observed by this composite, after a fresh fetch. Empty if the fetch or rev-parse failed. |
| `after-sha-available` | `'true'` unless the fetch/rev-parse failed. |
| `commits` | `git rev-list --count "<before-sha>..<after-sha>"`, computed only when both SHAs are available. Empty otherwise. |
| `commits-available` | `'true'` unless either SHA is unavailable or the range failed to resolve for a reason other than "0 commits." |

## Behavior

1. `git fetch origin "+refs/heads/$BRANCH:refs/remotes/origin/$BRANCH"`.
   A failure here (network flake, or the branch genuinely does not exist
   yet — e.g. a `pr`-mode run whose agent step never created its review
   branch) is caught, not fatal to the composite or its caller.
2. On fetch success: `git rev-parse refs/remotes/origin/$BRANCH` for
   `after-sha`. Empty/failed rev-parse degrades `after-sha-available` to
   `'false'`.
3. When both `before-sha-available` and `after-sha-available` are
   `'true'`: `git rev-list --count "$BEFORE_SHA..$AFTER_SHA"` for
   `commits`. Any other combination leaves `commits`/`commits-available`
   at their empty/`'false'` defaults.
4. The composite never fails its own step (best-effort throughout,
   matching FR-008) — every failure degrades an output rather than
   erroring, and the calling step still wraps it in `continue-on-error:
   true` as belt-and-braces, matching implement's existing convention
   for this same logic today.

## Non-goals

- Does not compute or validate `before-sha` — that is each caller's own
  concern (research.md R1/R2), since implement, plan, and tasks each
  resolve it from a different existing or new source.
- Does not call `wing-commander-metrics-summary` or write any record —
  callers do that themselves immediately afterward, exactly as
  `implement.yml`'s existing two-step (capture, then emit) sequence
  already does.
- Does not know or care about review mode, stage identity, or branch
  naming convention — `branch` arrives fully resolved.

## Single-home enforcement (FR-012)

Gate 60 (`verify-single-home-idioms.py`) gains a `branch-advance-
capture` check keyed on the co-occurrence of the refspec-form `git
fetch origin "+refs/heads/$` fragment and the `..`-range `git rev-list
--count "$` fragment, declared home
`.github/actions/wing-commander-branch-advance/action.yml`
(research.md R10, contracts/gate-coverage-068.md).
