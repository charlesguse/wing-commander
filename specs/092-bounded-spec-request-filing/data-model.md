# Data Model: Bounded, Idempotent spec-request Filing

This feature adds no new persistent store: everything below is either a
new field on the existing board item marker (spec 057) or a value computed
fresh, per run, from live GitHub state. Per Constitution IX, every
decision below is deterministic code, never an agent's judgment.

## Board Item Marker (extended)

Owning module: `.github/scripts/board_item_marker.py` (spec 057,
`specs/057-autonomous-board-loop/contracts/board-item-marker.md` — that
contract is a live, gate-read artifact per CLAUDE.md and needs its payload
shape updated in the same PR that changes `write_marker()`; out of scope
for this plan stage, which may only touch `specs/092-*`).

| Field | Type | Added by | Meaning |
|---|---|---|---|
| `step` | string | spec 057 | unchanged |
| `round` | int | spec 057 | unchanged — review round budget, never touched by this feature (Out of Scope) |
| `pr` | int or null | spec 057 | unchanged |
| `branch` | string or null | spec 057 | unchanged |
| `base_sha` | string or null | spec 057 | unchanged |
| `spec_request_attempts` | int, default 0 | **this feature** | consecutive failed spec-request filing attempts for this originating issue, since the last successful filing or re-admission |

`spec_request_attempts` is:

- **Read** by `select`/`resume` (board-loop.yml's `resume` step) exactly
  as `round` is read today, and republished as
  `needs.select.outputs.spec-request-attempts` for route/fix/readiness to
  consume (research.md D4).
- **Never reset** by resume's "stale marker" branches (the ones that zero
  `round`/`base_sha`/`branch` when a fix attempt's branch/PR cannot be
  re-derived live, FR-022) — it tracks a budget orthogonal to any fix
  attempt (research.md D4).
- **Incremented by 1** by whichever of the three filing sites just failed
  to file (a failed lookup *or* a failed create both count as one failed
  attempt — spec.md's Edge Cases: "A failed check counts as a failed
  attempt against the bound").
- **Cleared to 0** on a successful filing, whether a fresh create or a
  reuse (research.md D5).
- Left at its capped value on a give-up stall (FR-012's comment states it);
  effectively reset only when a maintainer removes `board:stalled` and the
  item is re-triaged (FR-014) — see "Give-up stall" below.

## Filing attempt (spec.md Key Entity)

Not a persisted record — a decision made once per run, per site, from:

```
inputs:  issue_number, bot_login, existing_attempts (from the marker),
         budget (env.BOARD_LOOP_SPEC_REQUEST_ATTEMPT_BUDGET)
outputs: outcome in {"reused", "filed", "failed-below-cap", "gave-up"}
```

State transition, computed by `board_spec_request_filing.py` (research.md
D1, D6) plus the site's own `gh issue create`:

```
lookup(issue_number, bot_login)
  -> lookup failed?            => treat as a failed attempt (below)
  -> existing_url found?       => outcome = "reused"; spec_request_attempts := 0
  -> no existing_url           => attempt a create

create(...)
  -> succeeded (URL shape ok)? => outcome = "filed"; spec_request_attempts := 0
  -> failed                    => attempts := existing_attempts + 1
                                   attempts < budget?
                                     => outcome = "failed-below-cap"
                                        (marker-only comment persists
                                        `attempts`; step exits 1)
                                     => outcome = "gave-up"
                                        (board:stalled, give-up comment,
                                        stalled marker; step exits 0)
```

## Attempt budget (spec.md Key Entity)

A single configured constant, `env.BOARD_LOOP_SPEC_REQUEST_ATTEMPT_BUDGET`
in `.github/workflows/board-loop.yml`'s top-level `env:` block, value `3`
(research.md D4). Not per-site, not shared with `BOARD_LOOP_ROUND_BUDGET`.
Read by all three filing sites and by Gate 93's new check (research.md D8).

## Prior-filing record (spec.md Key Entity)

Not a new artifact — the existence check's *evidence*: an issue in the
repository such that:

- `user.type == "Bot"` and `user.login` is the loop's own App identity
  (`steps.ctx.outputs.bot-slug + "[bot]"`, the same identity
  `is_loop_marker_author()` already checks), and
- its body contains the line `Originating issue: <server>/<repo>/issues/N`
  verbatim (whitespace/CR-normalized, matching the existing `#530` jq
  predicate's `rtrimstr("\r")` handling), and
- its `created_at` is at or after the originating issue's `since` bound
  (research.md D3: the last `reopened` event's timestamp, or the issue's
  own `created_at` if never reopened).

State (open/closed) is never part of the predicate (FR-003) — the oldest
match by `created_at` among however many satisfy it is reused (FR-004);
no other prior spec-request is touched.

## Give-up stall (spec.md Key Entity)

A terminal marker state, reached only via the "gave-up" transition above:

- `board:stalled` label present (via `add_stalled_label()`, unchanged).
- Marker `step` = `"stalled"`.
- `spec_request_attempts` left at its capped value (`budget`) in the
  marker — read-only evidence of how it ended, not consulted again until
  re-admission.
- A comment stating: no `spec-request` was filed, the last observed
  failure (the `gh issue create` error / URL-shape check's own message),
  the number of attempts spent, and that removing `board:stalled`
  re-admits the item (FR-012).

**Re-admission** (FR-014): identical to every other stall's re-eligibility
condition — a maintainer removes `board:stalled`. `board_eligibility.
is_excluded()` (line 141) no longer excludes the issue; the next run's
`resume` finds no branch/PR, resolves `step = "triage"`, and — because
route's spec verdict path re-reads `needs.select.outputs.spec-request-
attempts` fresh from whatever the marker's last write recorded — a fresh
routing decision starts the budget over only if the give-up marker's
`spec_request_attempts` is treated as stale the same way `round`/`branch`
are for an abandoned fix attempt. To keep this consistent with D4's "never
implicitly reset" rule, re-admission's fresh start is made explicit: the
give-up comment's own marker write is the **last** write to
`spec_request_attempts` before re-admission, and it is defined to carry
value `0`, not `budget` — the give-up state is recorded as "capped and
stalled" in the comment's prose (human-readable, for FR-012/SC-004), while
the marker field itself already reads "fresh" for whichever run picks the
item up after re-admission. This avoids adding a second, re-admission-
specific reset rule to `resume`'s step-resolution logic, keeping FR-018's
single-implementation rule intact.
