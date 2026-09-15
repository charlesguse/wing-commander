# Contract: the deterministic regression gate (FR-018, SC-005)

Status: normative for this feature's implementation. Cross-references
research.md D7 for the full rationale and `release-handover-contract.md`
for the behavior being protected.

## Subject

`.github/scripts/verify-correlated-release-dispatch.py` — a new gate,
following the established shape of Gate 50
(`verify-release-contract.py`) and Gate 51
(`verify-rate-limited-exemption.py`): textual, line-based, with its own
`--self-test` exercising every failure branch against an in-memory
fixture rather than the real files, and a plain invocation that checks
the real repository. Registered as a PR-time step in
`lint-workflows.yml` (next available gate number at implementation
time — 52 as of this plan; re-check for a collision with any
concurrently-landing spec before claiming it) immediately followed by
its own `--self-test` invocation, matching every existing gate's
two-step pattern. `run-local-gates.py` needs no separate registration —
it derives its list from `lint-workflows.yml`.

Unlike Gate 50/31, this gate's subject is **not** the derived
published-stage set (`wc_published_stages()`) — `release.yml` and
`auto-release.yml` carry no `workflow_call` trigger, so they are outside
that set by construction (research.md D6). This gate names exactly
those two files directly.

## The five checks

Each check corresponds to one clause of FR-018 and must fail on the one
mutation that reintroduces the regression it names, per Constitution
VIII:

| # | Checks that... | Fails when... | FR-018 clause |
|---|---|---|---|
| 1 | `release.yml` declares a `run-name:` referencing both `inputs.version` and `inputs.attempt-token` | the `run-name:` key is removed, or is rewritten to omit the token | "drops the attempt token from the release run's title" |
| 2 | `release.yml` contains a live tip comparison (`git ls-remote origin "refs/heads/${DEFAULT_BRANCH}"`, resolved from `github.event.repository.default_branch`, or equivalent) whose line number is *after* the "Create tags" step's own marker line | the comparison is removed, or is moved before that marker (i.e., turned into a request/checkout-time check instead of a tag-time one) | "removes the tag-time tip refusal" |
| 3 | `auto-release.yml`'s correlation logic references a created-at/time field in the same step that matches on the attempt token | the step is rewritten to select on token alone, or on recency alone (e.g., back to `-L 1`/`.[0]` with no token filter) | "reintroduces recency-based selection" |
| 4 | `auto-release.yml`'s outcome computation reads a `refs/tags/` comparison (`git rev-parse` against a tag ref) to decide `released` | the outcome is instead read from a run's `conclusion`/`status` field | "lets a release be reported from a run conclusion instead of the tag state" |
| 5 | `auto-release.yml` waits for the correlated run's own `status` (a `gh run view ... --json status` poll, never `.conclusion`) to reach a terminal state before the tag fetch that decides `released` | the tag fetch is moved ahead of, or the wait removed from before, that status poll | "reads tag state immediately after correlation, which can observe a correlated run still mid-flight and file a false dispatch-failed report" (added this cycle, T025) |

## Self-test fixture shape

Following Gate 50's pattern exactly: an in-memory "clean" pair of file
contents exercising every checked-for form (a `run-name:` with the
token, a correctly-ordered `ls-remote` check, a correlation step
matching on both token and `createdAt`, a status-poll wait before the
tag fetch, a `released` decision reading a tag comparison), asserted to
pass with zero findings; then one mutated copy per check above, each
asserted to fail with a message naming only that check's own FR-018
clause (not the other four) and the offending line, matching Gate 50's
`check(...)`/`fixture(...)` helper shape so a future reviewer already
familiar with Gate 50 can read this gate's self-test without learning a
new pattern.

## Non-goals

This gate does not re-implement or simulate the correlation algorithm
or the tag-time check — it is a static, textual check that the
*mechanisms* are present and correctly ordered, the same level Gate 50
already operates at for its own three checks. Runtime correctness (does
the poll loop actually find the right run) is validated by the
quickstart scenarios in `quickstart.md`, not by this gate.
