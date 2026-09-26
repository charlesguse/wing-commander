# Data Model: Gate 59 resolves the dispatch idiom wherever it lives

This feature has no runtime data store. "Entities" here are the gate's
resolution model, the widened composite contract, the job's own outputs,
and the two records this feature retires or amends — the shapes a later
tasks/implement stage builds against. Names match spec.md's Key
Entities section; sources are the concrete files/lines gathered in
research.md and the plan-stage exploration.

## Release-dispatch regression gate

`.github/scripts/verify-correlated-release-dispatch.py` (Gate 59, unchanged number)

| Field | Type | Notes |
|---|---|---|
| subject | `release.yml`, `auto-release.yml`, plus whichever local composite `auto-release.yml`'s `dispatch-release` job's `uses:` steps resolve to | widened from exactly-two-files (today) per FR-001 |
| checks 1–2 | unchanged | `release.yml` only, FR-009 |
| check 3 (correlation) | resolves through D1's spliced corpus | fails naming only the recency-based-selection clause |
| check 4 (tag-state) | job-only corpus, never composite (FR-027) | fails naming only the tag-state clause; also fails if only found inside a composite |
| check 5 (wait-before-tag-read) | resolves through D1's spliced corpus | fails naming only the mid-flight-read clause |
| attribution | per-check, printed on pass | job path or resolved composite path (FR-005) |
| unresolvable-reference handling | hard fail, 3 sub-cases | D3: missing file, resolved-but-construct-absent, two-levels-deep |
| self-test fixtures | in-memory, `resolve=` injection point | D5's 10-case matrix; no real files touched |
| failure clause isolation | unchanged from today | SC-003: each fixture's failure names exactly one clause |

## Dispatch-and-wait composite (widened contract)

`.github/actions/wing-commander-dispatch-and-wait/action.yml`

| Field | Type | Notes |
|---|---|---|
| `token` (input) | secret string | unchanged |
| `workflow-file` (input) | string | unchanged |
| `workflow-inputs` (input) | JSON object string | unchanged |
| `attempt-token` (input) | string | unchanged |
| `poll-attempts` (input) | int-as-string, default `12` | unchanged |
| `poll-interval-seconds` (input) | int-as-string, default `10` | unchanged |
| `wait-attempts` (input) | int-as-string, default `60` | unchanged |
| `uncorrelated-wait-seconds` (input) | int-as-string, default `0` | **new** — D6, FR-014; `board-loop.yml`'s prove job keeps today's no-wait behavior by omitting it |
| `run-url` (output) | string, may be empty | unchanged name/meaning (FR-013) |
| `conclusion` (output) | string, `timeout`, or empty | unchanged name/meaning (FR-013) |
| `dispatch-rejected` (output) | `"true"`/`"false"` | **new** — D6, FR-011 |
| `correlation` (output) | `found` \| `ambiguous` \| `not-observed` | **new** — D6, FR-011, FR-012 |
| `correlated-run-id` (output) | string, may be empty | **new** — D6, FR-011, FR-026 |
| `request-time` (output) | ISO-8601 string | **new** — D6, FR-011 |
| deferred-hook note | header-comment paragraph | **new** — D7, FR-028: a generic post-wait verification hook is deliberately out of scope |

**Call sites**: `board-loop.yml`'s prove job (existing, unaffected —
reads only `run-url`/`conclusion`, keeps working per SC-009);
`auto-release.yml`'s `dispatch-release` job (new call site, User Story
3, D9).

**Behavioral harness**: `.github/scripts/dispatch-and-wait-tests/run-tests.sh`
(Gate 88, unchanged number) — widened with cases for
`dispatch-rejected: true` (dispatch itself fails, no correlation search
run), `correlation: ambiguous` and `correlation: not-observed` asserted
as their own field (not inferred from empty `run-url`), `correlated-run-id`
asserted alongside `run-url`, `request-time` asserted present in every
case including `not-observed`, and `uncorrelated-wait-seconds` asserted
to actually delay when set and to default to no wait when omitted.

## `dispatch-release` job (post-repoint shape, User Story 3)

`.github/workflows/auto-release.yml`

| Field | Type | Notes |
|---|---|---|
| step 1: "Dispatch and correlate release.yml" | `uses:` step calling the composite | mints `token`, passes `uncorrelated-wait-seconds: "90"` (D9) |
| step 2: "Decide release outcome from tag state" | `run:` step | reads step 1's five new/kept outputs as passthrough only; independently fetches the tag and compares to `VERIFIED_HEAD` (FR-019, FR-027) — this is Gate 59 check 4's corpus and D8's new harness's subject |
| job `outputs.correlation` | passthrough of step 1's `correlation` | unchanged name (FR-018) |
| job `outputs.correlated-run-id` | passthrough of step 1's `correlated-run-id` | unchanged name |
| job `outputs.correlated-run-url` | passthrough of step 1's `run-url` | **name kept**, composite's own output renamed only at this passthrough boundary |
| job `outputs.tag-matches` | step 2's own decision | unchanged name/meaning |
| job `outputs.request-time` | passthrough of step 1's `request-time` | unchanged name |
| job `outputs.dispatch-rejected` | passthrough of step 1's `dispatch-rejected` | unchanged name |

**Fallback**: none needed — this is not an optional composite call; a
step 1 that fails to run (job-level failure) leaves the job's outputs
unset, which `report`'s existing `always()` + result-checking logic
(`auto-release.yml:1872-1879`, `file_job_failure`) already handles today
for the same reason a hand-rolled step could fail.

## New runtime harness for the tag-state invariant

`.github/scripts/verify-auto-release-tag-state-runtime.py` (Gate 99 as
of this plan — re-check for a collision before claiming it)

| Field | Type | Notes |
|---|---|---|
| subject | `dispatch-release`'s step 2 ("Decide release outcome from tag state") | extracted via `find_step`, matching Gate 67's own shape |
| execution | `run_step` with a stubbed `git` on `PATH` | asserts `tag-matches` flips correctly for tag-present-at-head / tag-present-elsewhere / tag-absent |
| runtime proof supplied | check 4 (tag-state) of FR-025's three | the other two (correlation, wait-before-tag-read) are supplied by Gate 88 (existing, widened per User Story 2) |
| lands with | User Story 3 | needs the post-repoint two-step job shape (D9) to isolate its subject |

## Records retired or amended (not new entities, existing artifacts)

| Record | Current state | Corrected state |
|---|---|---|
| `.github/scripts/single-home-waivers.json` | `dispatch-and-wait` / `auto-release.yml` entry, issue #408, "Remove this waiver when T054 lands" | entry deleted; Gate 60's existing `check_dispatch_and_wait` then fails if the inline copy ever returns (FR-020, FR-021) |
| `specs/057-autonomous-board-loop/tasks.md` T054 | `[ ] ... **BLOCKED (2026-09-22, cycle 2)**` | `[X]`, one-line pointer to this feature |
| `specs/057-autonomous-board-loop/tasks.md` T056 | `[ ] ... **PARTIALLY DONE, BLOCKED on T054**` | `[X]`, one-line pointer to this feature |
| `specs/048-correlated-release-dispatch/contracts/regression-gate.md` | "five checks" table frames checks 3/5 as pure `auto-release.yml` text checks; states the gate "does not re-implement or simulate" (Non-goals) | gains a note that checks 3/5 resolve through a called composite (pointing at `contracts/resolving-gate.md`), and that runtime proof for all three invariants now exists (pointing at Gate 88 and Gate 99) |
