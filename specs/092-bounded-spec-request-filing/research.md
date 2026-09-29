# Research: Bounded, Idempotent spec-request Filing

Phase 0 output. Each decision resolves either an explicit spec.md unknown
or a design question spec.md leaves to the plan (its clarifications answer
*what* to build; these decisions answer *how*, against the code as it
exists on `main` today). Decisions marked **(unclarified)** are judgment
calls made per this run's DEVIATIONS instruction and are restated in the
"Decisions made without clarification" section of the lifecycle issue
comment.

## Current-state baseline (read directly from `.github/workflows/board-loop.yml` and `.github/scripts/` on `main`)

- Three filing sites exist: route's spec verdict (`spec_request` step,
  board-loop.yml:1815-1911), the fix job's post-push breach
  (`post-push-breach` step, :2425-2469), and readiness's backstop breach,
  which itself has two entries inside `Report the unmet condition (not
  ready)` (:3862-3917): an *ordinary* entry (`BREACH_RETRY` false) with
  **no existence check today**, and a `step=breach` retry entry
  (`BREACH_RETRY` true) that reuses `breach-retry-lookup`'s output
  (:3831-3860) — the #530 lookup FR-018 asks to generalize.
- The #514 create guard (`[[ "$spec_url" =~ ^https?://.../issues/[0-9]+$ ]]
  || { ...; exit 1; }`) is inline shell repeated at all three sites, never
  a composite. Gate 93 check 3 (`verify-issue-context-single-home.py`,
  `check_spec_request_bodies()`, line 1120) already enforces its shape and
  ordering, and that a spec-request's body always comes from
  `board_spec_request_body.py` fed the issue-context composite's
  `context-file` output.
- The #530 lookup (board-loop.yml:3839-3860) is inline shell + a jq filter
  held in the env var `BREACH_SPEC_REQUEST_JQ`, not a script or composite.
  It matches on bot authorship (`user.type=="Bot" && user.login==$bot`),
  the exact `Originating issue: …/issues/N` line, **and** a `/pull/N` or
  `PR #N` reference in the body, scoped `since` the PR's `createdAt`,
  oldest match wins.
- The `Originating issue: …/issues/N` footer line is built by a
  `printf` at each of the three call sites (and again, identically, at the
  lookup site) — not emitted by `board_spec_request_body.py` itself, which
  only accepts `--footer TEXT` as an opaque string. FR-002 calls this the
  "canonical originating-issue reference line the spec-request body
  builder already emits", which is true of the *text shape*, not of a
  single code location that emits it.
- The board item marker (`board_item_marker.py`) is an HTML comment
  `<!-- wing-commander-board-item: {"step","round","pr","branch",
  "base_sha"} -->` appended to a `**Run:** <url>` line inside a bot-authored
  issue comment; `write_marker()` (line 139) takes those five fields
  positionally, `main()` (228) exposes them as CLI flags. `select`/`resume`
  (board-loop.yml:589-871) parses the newest such marker and republishes
  each field as a job output (`needs.select.outputs.round`, `.pr`, etc.) so
  every downstream job reads it without re-parsing comments.
- `add_stalled_label()` (board_item_marker.py:170) is the single home for
  "board:stalled before any stalled marker" (#782/#604): every stall site
  in board-loop.yml, including all three spec-request sites, already calls
  `board_item_marker.py --step stalled --issue N --add-label board:stalled`
  through it.
- Gate 93 check 3 also forbids `gh api` or `gh issue view` (beyond one
  literal title-fetch form) inside the same step as `gh issue create
  ... --label spec-request` (`GH_API_RE`/`GH_ISSUE_VIEW_RE`, lines
  1298-1314). This is *why* the #530 lookup is its own preceding step
  (`breach-retry-lookup`) rather than inlined into `report-unmet` —
  the same shape the two new lookup sites (route, fix) and the newly
  bound ordinary readiness entry must follow.
- Precedent for "stall without a red run": review's round-budget
  exhaustion (board-loop.yml:3259-3321) posts a stall comment and
  `board:stalled` on the Nth round and does not fail the step — the
  budget being spent is a clean handoff, not an error. This is the shape
  the give-up stall (User Story 2/3) follows, not the #514 guard's `exit
  1` shape.
- No gate today is named `verify-spec-request-*`; Gate 93 already owns
  "everything about a spec-request creation site" (checks 1-5, one file),
  so a new check inside it is the natural home for FR-019 rather than a
  parallel gate file.
- Spec 108 (routed-original disposition, #791) is merged as a *spec
  document* only; `board_eligibility.py` already carries its
  `DISPOSITION_PREFIX`/`is_excluded()` groundwork, but no
  close-as-duplicate step exists in board-loop.yml yet on `main`. Spec 100
  (#752, readiness re-admission) is likewise unmerged as code.

## Decisions

### D1: One shared existence-check implementation, as a new `board_spec_request_filing.py` script (FR-001–FR-004, FR-007, FR-017, FR-018)

**Decision**: Add `.github/scripts/board_spec_request_filing.py`, joining
`board_item_marker.py`, `board_eligibility.py`, `board_spec_request_body.py`
as the board loop's family of shared, unit-tested modules. It exposes:

- `find_existing(issues_json, bot_login, footer)` — pure function over a
  pre-fetched list of issue dicts (`{html_url, created_at, body, user}`),
  returning the oldest URL whose `user` is the bot and whose `body`
  contains `footer` as a whole line (FR-002, FR-004), or `None`. No PR
  filter (see D2).
- `reopened_since(events_json, created_at)` — the `created_at` of the
  last `event == "reopened"` item in an issue's events, or the issue's own
  `created_at` if it was never reopened (FR-003).
- A `main()` CLI, invoked as its own workflow step (never inside the
  `gh issue create` step, per Gate 93's `GH_API_RE` ban):
  `board_spec_request_filing.py lookup --issue N --bot-login LOGIN`,
  which does the `gh api .../issues/N/events` call, the
  `gh api .../issues?since=...&creator=...` call, and prints
  `existing-spec-url=<url-or-empty>` to `$GITHUB_OUTPUT`, exiting 1 (no
  URL printed) on any `gh`/network failure — mirroring #530's existing
  `exit 1` shape exactly, so FR-007's fail-loud, retry-later behavior is
  unchanged in effect, just relocated.

**Why a script, not a composite action**: every other piece of
board-loop-only logic this specific (pure decision functions plus a thin
CLI over `gh`) already lives as a `.github/scripts/board_*.py` module
consumed by an inline `python3 -I "$RUNNER_TEMP/wc-pristine/scripts/..."`
step, not a `.github/actions/` composite; composites in this repo are
reserved for steps with their own `with:`-typed inputs/outputs consumed by
multiple *workflows* (VII), not for one workflow's internal helpers. Making
this a script keeps FR-018's "exactly one implementation" symmetrical with
how the marker and the body builder are already homed, and keeps it
fixture-testable the same way `verify-board-eligibility.py` tests
`board_eligibility.py` (D6).

**Alternatives considered**: A composite action
(`.github/actions/wing-commander-spec-request-lookup`) was considered and
rejected — it would need `with: token/issue-number/bot-login` inputs and a
`context-file`-style secret-bearing output, adding a "composite provenance"
surface (Gate `verify-board-loop-composite-provenance.py`) for something
strictly internal to this one workflow's three call sites, which VII's own
underscore-prefixed-internal convention is for `.github/actions/_shared/`
helpers shared *between composites*, not workflow-internal Python.

### D2: The generalized match predicate drops the `/pull/N` filter the #530 lookup added (FR-002, FR-004)

**Decision (unclarified)**: `find_existing()` matches on bot authorship
plus the exact footer line only — never a PR reference. FR-002 states the
rule as exactly those two things ("artifacts authored by the loop's own
identity and carrying the canonical originating-issue reference line...
never on title text"); it does not mention a PR. FR-004's "oldest of
several matches wins" only makes sense if the match key is the originating
issue alone, since a PR-scoped key would (by construction) almost never
find more than one match at readiness's own site.

**Why this is safe**: the footer line embeds the issue number itself
(`Originating issue: …/issues/N`), so a match already can only ever belong
to one originating issue; the PR filter in the current #530 lookup was an
extra narrowing specific to disambiguating readiness's own two entries
from each other, not part of the canonical rule FR-002 states. Generalizing
it to all three sites without the PR filter is a **strict widening** of
what counts as "already filed" — never a narrowing — so a real spec-request
for issue N is never missed. It can occasionally reuse a spec-request
across two unrelated breaches of the *same* issue (e.g., a first fix PR
breached, and its abandoned branch's spec-request is later found by a
second, unrelated fix attempt on the same issue) — which is exactly FR-004
and the "prior spec-request was closed"/"two spec-requests already exist"
edge cases' intent: reuse the oldest, never file a second one, and leave
any cleanup to a maintainer.

**Alternatives considered**: Keeping the PR filter for readiness's own two
entries while route/fix run without one was rejected outright by FR-018
("the same MUST hold for the attempt bound" and, by the same clause, for
the existence check) — two predicates is the "second, parallel copy" FR-018
and FR-019 exist to forbid.

### D3: `since` is computed from the *issue's* reopen history, not the PR's creation (FR-003)

**Decision**: `board_spec_request_filing.py lookup` always derives `since`
from the originating issue's own timeline (`reopened_since()`, D1) — never
from `gh pr view --json createdAt` as the current #530 lookup does. This is
the one behavior change FR-003's reopen clause requires: a PR's creation
time has no relationship to when its *issue* was last reopened, and using
it at route's and the fix job's post-push-breach sites (which today have no
PR-time scope at all) would be inventing a second, undocumented rule.

### D4: The attempt count is a new marker field, threaded exactly like `round` (FR-008, FR-009, FR-010, FR-013, FR-014, FR-015)

**Decision**: `board_item_marker.py`'s payload gains a sixth field,
`spec_request_attempts` (int, default 0), written via a new optional
`write_marker(..., spec_request_attempts=0)` parameter and a new
`--spec-request-attempts N` CLI flag. `select`/`resume`
(board-loop.yml:589-871) reads it the same way it already reads `round`
(`marker_json | jq -r '.spec_request_attempts // 0'`) and republishes it as
a new `select` job output, `needs.select.outputs.spec-request-attempts`, so
route/fix/readiness read it without re-parsing comments — the same
plumbing `round` already uses end to end (board-loop.yml:145, 606, 851,
869, 2608).

The new `BOARD_LOOP_*` constant FR-010 asks for is named
`BOARD_LOOP_SPEC_REQUEST_ATTEMPT_BUDGET`, set to `3`, added to the
workflow's top-level `env:` block beside `BOARD_LOOP_ROUND_BUDGET`
(board-loop.yml:89-114).

**Persistence across triage/route cycles (unclarified)**: unlike
`round`/`base_sha`/`branch`, which resume's "stale marker" branches
(board-loop.yml:778-829) reset to `0`/`""` whenever a fix attempt's branch
or PR cannot be re-derived live (FR-022's abandoned-attempt rule),
`spec_request_attempts` is **never** reset by those branches. It tracks a
budget over *filing* attempts for one originating issue, which is orthogonal
to whatever happened to any later fix/PR attempt; clearing it on an
unrelated stale-branch resume would let a chronically-unfileable issue
(missing label, lost permission) escape its cap the moment any fix attempt
also went stale. It is cleared in exactly two places: to `0` on a
successful filing (create or reuse, D5), and implicitly to `0` on
re-admission (FR-014: no `board:stalled` label means resume finds no
`stalled` marker to inherit a count from, so a fresh selection starts from
whatever the marker's last non-stalled write recorded — the give-up
comment's own write, D7, is the last one, and it is the one write allowed
to leave a non-zero count standing on a terminal, stalled item).

### D5: A successful filing — new create *or* reuse — clears the count (FR-015)

**Decision**: "successful filing" in FR-015 includes a reuse (FR-006's
"reused" case), not only a fresh create. Both leave the item in the same
end state FR-005 requires (identical downstream treatment), and the
attempt budget exists to bound *unsuccessful* filings, not to distinguish
how the eventual success was reached.

### D6: The attempt-bound decision logic is one function, reused by all three sites (FR-018)

**Decision**: `board_spec_request_filing.py` also exposes
`record_attempt(attempts_before, budget) -> {"attempts": int, "stall":
bool}` — `attempts_before + 1`, and `stall = attempts >= budget` — called
by each site's own failed-create branch via
`board_spec_request_filing.py record-attempt --attempts N --budget "$BOARD_LOOP_SPEC_REQUEST_ATTEMPT_BUDGET"`,
printing that JSON to stdout for the step's shell to branch on with `jq`.
This is the "single implementation" FR-018 asks for on the bound side,
matching D1's existence-check script.

### D7: Below-cap failure persists the count via a marker-only comment; the give-up stall follows the round-budget shape, not the #514 guard's (FR-011, FR-012, FR-013, FR-020, SC-007)

**Decision (unclarified — the plan's most significant judgment call)**:
FR-009 requires the failed-attempt count to live in the board item marker,
and the marker exists only embedded in an issue comment; there is no
comment-free channel this loop has today. Below the cap, the site therefore
posts one new issue comment carrying **only** the standard `**Run:**
<url>` line and the marker HTML comment — no narrative text, no label
change, no spec-request URL — then still fails the step loudly (`exit 1`,
unchanged). This reads FR-011/FR-020/SC-007's "nothing is commented,
labelled or published" as forbidding a *user-facing account of the
failure* (an explanation, a label, an artifact URL) — which still does not
happen — not as forbidding the same content-free bookkeeping write every
other marker in this file already makes (e.g. the fix job's own
pre-create `step=breach` marker, written before that site's create is even
attempted). The alternative literal reading is irreconcilable with FR-009's
own text ("That state is the board item marker the loop already writes and
reads") and is not resolved by spec.md's clarification log, so it is
recorded here for the maintainer to confirm or override.

At the cap (the Nth failure), the site instead follows review's
round-budget-exhaustion precedent (board-loop.yml:3259-3321): add
`board:stalled` first (via `add_stalled_label()`, unchanged), post the
FR-012 give-up comment (states no spec-request was filed, names the last
failure, states the attempt count, names removing `board:stalled` as the
recovery), write a `stalled`-step marker, and **exit 0** — a bounded
budget being spent is a successful, deliberate handoff, not a run failure,
exactly as the existing round-budget stall already establishes; only a
below-cap failure is a red run (SC-007 says so explicitly for that case
only). This is also what FR-013 needs: `select`/`in_flight_candidate()`
already excludes any `board:stalled` issue (`board_eligibility.is_excluded`,
line 141), so a give-up stall is inert to selection the same way every
other stall is, with no new exclusion rule required.

Gate 93 check 3's create-guard logic (`_create_guard_problems`) is
extended (D8) to recognize this new third shape — failed create, at cap,
publish-then-succeed — as sanctioned, distinct from a failed create that
publishes below the cap (still the #514 defect).

### D8: Gate 93 gets a new check, not a new gate file (FR-019)

**Decision**: Add check 6 to `verify-issue-context-single-home.py`
(alongside checks 1-5), `check_spec_request_filing_bound()`, rather than a
new `verify-spec-request-*.py`. Gate 93 already parses board-loop.yml's
`jobs`/`steps` structure and already owns "every rule about a spec-request
creation site" end to end (check 3); a seventh, freestanding gate file
re-parsing the same YAML to check a directly adjacent rule would itself be
the kind of duplicated logic CLAUDE.md's single-home rule flags. The new
check verifies, for each of the three sites: (a) a `board_spec_request_
filing.py lookup` step immediately precedes the create step, gating the
create on an empty `existing-spec-url`; (b) the create's failure branch
calls `board_spec_request_filing.py record-attempt` (never a hand-rolled
`$((N+1))`); and (c) the workflow's `env:` block defines exactly one
`BOARD_LOOP_SPEC_REQUEST_ATTEMPT_BUDGET`, and every site reads it from
`env.BOARD_LOOP_SPEC_REQUEST_ATTEMPT_BUDGET` rather than a literal `3`.

**Fixtures**: following `verify-board-eligibility.py`'s own pattern
(checked-in JSON fixtures under `.github/scripts/tests/<gate>/<case>/`),
`board_spec_request_filing.py`'s pure functions (`find_existing`,
`reopened_since`, `record_attempt`) get fixture-driven unit tests under
`.github/scripts/tests/board-spec-request-filing/`.

### D9: Title-length truncation lives in `board_spec_request_body.py` (FR-016)

**Decision**: Add `truncate_title(title, limit=256)` to
`board_spec_request_body.py` — already the single home for spec-request
shaping (its own docstring's stated purpose) — and have each of the three
sites pipe its drafted/issue title through it before `--title`. This
removes the over-long-title failure cause at its source rather than only
letting the new bound absorb it, exactly as FR-016 and the Edge Cases
section ask.

### D10: Reuse gets identical downstream treatment by construction, not by a special case (FR-005)

**Decision**: Each site's lookup and create steps both write to the same
step output (e.g. `steps.spec_request.outputs.spec-url`), whichever ran.
Every downstream step in that job (the cross-link, the stalled marker, the
closing comment, and — once spec 108's code lands — its route-time
disposition) already keys off that one output and is otherwise unaware of
whether it came from a lookup or a create. This is why D1/D6 are designed
as steps that populate the *existing* output name rather than a
parallel one: FR-005's "identical treatment" falls out of the existing
wiring with zero site-specific branching, and needs no change if/when spec
108's code merges — the reuse path inherits whatever route's own downstream
steps do for a freshly created one, automatically.

**Spec 108 dependency note**: spec 108's disposition code
(`spec/108-routed-original-disposition`) is not on `main` as of this plan.
This feature does not depend on it merging first or in any particular
order — D10's wiring means "identical treatment" holds against whatever
route's downstream steps do at implementation time, with or without 108's
disposition step present.

## Resolved unknowns (spec.md clarifications, restated for traceability)

- Both bounds ship together (spec.md Q1) — reflected in D1-D10 covering
  both the existence check and the attempt budget.
- N = 3, its own `BOARD_LOOP_SPEC_REQUEST_ATTEMPT_BUDGET` (spec.md Q2) — D4.
- The count lives in the board item marker, its own field (spec.md Q3) —
  D4.
