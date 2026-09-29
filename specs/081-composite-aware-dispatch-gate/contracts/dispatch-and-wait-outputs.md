# Contract: the widened dispatch-and-wait outcome contract (FR-011–FR-016, FR-026, FR-028)

Status: normative for this feature's implementation. Narrows
`wing-commander-dispatch-and-wait/action.yml`'s own header/description
for the specifics below; that file's header comment is the canonical
copy once this feature lands (this document does not restate it a
second time — CLAUDE.md's "single home" rule for prose).

## Published surface (Constitution VII)

`.github/actions/wing-commander-dispatch-and-wait/` is not
underscore-prefixed — it is part of the published, adopter-pinned
surface. Every input/output named below is a compatibility surface the
moment it ships; FR-016 records this widening as the deliberate act
Constitution VII requires, not a convenience.

## Inputs

| Input | Required | Default | This feature |
|---|---|---|---|
| `token` | yes | — | Unchanged. |
| `workflow-file` | yes | — | Unchanged. |
| `workflow-inputs` | no | `"{}"` | Unchanged. |
| `attempt-token` | yes | — | Unchanged. |
| `poll-attempts` | no | `"12"` | Unchanged. |
| `poll-interval-seconds` | no | `"10"` | Unchanged. |
| `wait-attempts` | no | `"60"` | Unchanged. |
| `uncorrelated-wait-seconds` | no | `"0"` | **New.** A bounded wait applied only when `correlation` never reaches `found` (dispatch rejected, or the poll budget exhausted with zero or multiple matches). Default `0` means "no wait", preserving `board-loop.yml`'s prove job exactly. `auto-release.yml`'s call site passes `"90"`, matching today's fixed uncorrelated-path wait. |

## What the composite promises

1. **Every existing output keeps its name and meaning** (FR-013). A
   caller reading only `run-url`/`conclusion` today needs no edit
   (SC-009).

2. **The dispatch call's own rejection is a discrete, reportable fact**
   (FR-011). `dispatch-rejected` is `"true"` iff `gh workflow run` itself
   returned non-zero; in that case the correlation search never runs
   (User Story 2 scenario 4), and `correlation` reports `not-observed`.

3. **Correlation is a three-way fact, never collapsed** (FR-011, FR-012).
   `correlation` is exactly one of `found`, `ambiguous`, `not-observed`.
   It is never derived by a caller from whether `run-url` is empty —
   `run-url` stays empty for both `ambiguous` and `not-observed` today
   (unchanged, FR-013), and `correlation` is what tells them apart. The
   composite never resolves ambiguity by picking the most recent match.

4. **The correlated run's identity is its own fact** (FR-011, FR-026).
   `correlated-run-id` carries the id half of what `run-url` already
   carries as a caller-parseable id (not just a URL a caller would have
   to parse) — empty whenever `correlation` is not `found`.

5. **The request time is always reported** (FR-011). `request-time`
   (ISO-8601) is set before the dispatch call and reported regardless of
   `dispatch-rejected` or `correlation`'s outcome — including
   `not-observed` (User Story 2 scenario 3).

6. **The uncorrelated-path wait is caller-settable, not fixed** (FR-014).
   When `correlation` is `ambiguous` or `not-observed`, the composite
   waits `uncorrelated-wait-seconds` (default `0`) before returning —
   giving a caller that reads state the dispatched run was expected to
   change a way to avoid reading it mid-flight, without forcing every
   caller to pay a wait it doesn't need.

7. **Every fact is its own named output** (FR-026). No caller is ever
   required to parse a structured (JSON, delimited) value out of one
   output to read a single fact — this rules out collapsing the widened
   facts into `conclusion` or a new combined output.

8. **A generic post-wait verification hook is out of scope, on record**
   (FR-028). The composite does not gain a release-specific "expected
   ref" input or a generic "verify state X now shows Y" step in this
   feature — `auto-release.yml`'s own tag-state check (contract:
   `resolving-gate.md`, D9's step 2) stays outside the composite by
   FR-027. This is recorded in the composite's own header so a future
   second caller needing the same shape reaches for that deferred
   decision rather than pasting a second verification copy.

## Behavioral harness (FR-015)

`.github/scripts/dispatch-and-wait-tests/run-tests.sh` (Gate 88) executes
the composite's own shipped shell (unchanged extraction method:
`extract_shell` reads the `watch` step's `run:` text out of `action.yml`)
against a stubbed `gh`, widened with the following stubbed scenarios,
each asserting every declared output for that case:

| Scenario | `dispatch-rejected` | `correlation` | `correlated-run-id` | `run-url` | `request-time` | `conclusion` |
|---|---|---|---|---|---|---|
| found | `false` | `found` | set | set | set | `success` (as today) |
| ambiguous | `false` | `ambiguous` | empty | empty | set | empty |
| absent (not-observed) | `false` | `not-observed` | empty | empty | set | empty |
| timeout (found, wait exhausted) | `false` | `found` | set | set | set | `timeout` (as today) |
| dispatch-rejected (**new**) | `true` | `not-observed` | empty | empty | set | empty |
| uncorrelated-wait honored (**new**) | `false` | `not-observed` | empty | empty | set | empty — asserts the stub observes the configured wait elapsed before the composite returns |

## Non-goals

This composite does not gain a way to verify state a caller expects the
dispatched run to have changed (FR-028) and does not gain any
release-specific input (FR-027) — both stay `auto-release.yml`'s own
concern, per `resolving-gate.md`.
