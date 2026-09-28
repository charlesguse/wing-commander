# Contract: The Cost-Report Collector's Attribution Rule

The algorithm `collect-cost-report` (`.github/workflows/watchdog.yml`)
runs to decide which lifecycle-issue comments are the inspected run's own,
after this feature. Extends spec 046's `cost-report` collector; does not
replace its signal classes, its fingerprint identity, or its dedup
behavior (Out of Scope).

## Inputs

- `ISSUE`: the lifecycle issue number (unchanged).
- `BOT_SLUG`: resolves the pipeline's own App login (unchanged).
- `CREATED_AT` / `UPDATED_AT`: the inspected run's own window bounds —
  **now optional**; empty when `gh run view` could not resolve them
  (research.md R5).
- `RUN_ID`: the inspected run's own `github.run_id`-equivalent — always
  known (this is the run the watchdog was invoked to inspect).
- `ATTEMPT`: the inspected run's own attempt number, from `run-meta`'s
  widened `gh run view --json ...,attempt` call — **may be unresolvable**
  (research.md R6); empty when so.
- `comments`: every comment on `ISSUE`, each `{body, createdAt, userLogin}`.

## Gating: `comments_checked`

`comments_checked` is `true` iff `ISSUE` and `BOT_SLUG` both resolve.
`CREATED_AT`/`UPDATED_AT` no longer gate this boolean — an unresolved
window narrows what the `unstamped` set can contribute (below), it does
not block the check outright (FR-009, research.md R5). When
`comments_checked` is `false`, the collector reports nothing for this run
— unchanged from today.

## The three-way partition

1. **`authored`** — comments whose `userLogin` is `${BOT_SLUG}[bot]` or
   `github-actions[bot]` (unchanged, FR-007).
2. Each comment in `authored` is parsed for a stamp
   (`run-stamp.md`'s regex). A non-match — no marker, or a marker that
   doesn't complete the four-field pattern — yields `stamp: null`
   (research.md R7; never an error, never a partial guess).
3. **`stamped_own`**: `stamp != null` and the stamp's run-identity portion
   (`run_id:attempt`) equals `RUN_ID:ATTEMPT` — **except** when `ATTEMPT`
   is itself unresolvable, in which case a same-`RUN_ID` stamp is *not*
   trusted into this set (research.md R6) even though the run id alone
   matches.
4. **`stamped_foreign`**: `stamp != null` and the run-identity portion
   does **not** equal `RUN_ID:ATTEMPT` (or, when `ATTEMPT` is
   unresolvable, does not equal `RUN_ID` alone) — excluded from `own`
   unconditionally, regardless of `CREATED_AT`/`UPDATED_AT` (FR-006).
5. **`unstamped`**: `stamp == null`, **or** `stamp != null` with a
   matching `RUN_ID` but `ATTEMPT` unresolvable (research.md R6's
   demotion) — eligible for `own` only if `createdAt` falls within
   `[CREATED_AT, UPDATED_AT]`, treating either bound as open when empty
   (FR-008, unchanged from today's window semantics).
6. **`own`** = `stamped_own ∪ (unstamped ∩ window)`.

Membership in `stamped_own` is never bounded by the window — a stamped
comment posted after `UPDATED_AT` is still this run's own (spec.md edge
case).

## Deciding the verdict

Unchanged from today, applied to `own` instead of the old window-only
set: sort `own` by `createdAt`, take the first comment carrying a parsed
`**Cost**: ...` figure. `comment_found` is `(own | length) > 0`.
`cost_token` extraction and the currency-shape validity regex are
unchanged (spec 046).

- `own` non-empty, no parseable cost token → `cost-line-missing`
  (FR-011 unchanged: only for `cost_available: true` runs).
- A cost token present but malformed → `cost-line-malformed`.
- A well-formed token, any magnitude → no signal (FR-019, unchanged).

## `attribution`

Every emitted `cost-line-missing`/`cost-line-malformed` signal gains one
fact: `attribution: "stamp"` if the verdict rests on `stamped_own`
membership (including "no `stamped_own` comment existed" driving a
`cost-line-missing`), `"window"` if it rests on the `unstamped ∩ window`
fallback (FR-010). This is a fact on the *existing* signal kind
(`cost-line-claim`, unchanged identity) — see `data-model.md`.

## Coverage this contract drives (FR-012)

Every branch named above needs at least one fixture in `verify-gate-19.py`'s
`COST_SCENARIOS` and/or `verify-cost-report-collector.sh`'s program-level
fixtures — the full list is `data-model.md`'s "Gate fixtures" table. Three
mutation checks specifically target this contract's own decision points,
not the collector's pre-existing behavior: removing the stamp preference
entirely, inverting it to prefer `stamped_foreign`, and dropping the
attempt number from the matched run-identity portion. Each MUST make the
gate suite fail (SC-005) — these three mutations are the concrete proof
that the overlapping-run scenarios this feature adds actually exercise
the fix, not just pass around it the way every pre-existing single-run
scenario already did before this feature (spec.md's own motivation for
User Story 3).
