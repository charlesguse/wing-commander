# Phase 1 Data Model: A Transient API Blip No Longer Kills Six Stages at Entry

This feature introduces no persisted data store. Every shape below exists
only for the duration of one step's execution (the composite's outputs are
the sole exception, unchanged from today and ephemeral to the calling job)
or, for the coverage script, for the duration of one test run. Spec's own
Key Entities section names five of these at the requirements level; this
document gives each a concrete shape.

## State read (existing entity, spec Key Entities — now attempted up to 3 times)

| Field | Source | Notes |
|---|---|---|
| `state` | `gh issue view "$ISSUE_NUMBER" --json state --jq .state`, wrapped in `timeout 4` | Unchanged command. Its possible outcomes, per attempt: a recognised answer (`OPEN`/`CLOSED`), an unrecognised non-empty answer, a permanent failure, or a retryable failure (research.md D2) |
| `exit code` | Shell exit status of the wrapped command | `0` with non-empty `state` is the only success; `124` specifically means the `timeout` expired (research.md D1/D3) — folded into the same non-zero handling as any other failure, no special-cased message |
| `stderr` | Captured to a per-attempt temp file (research.md D3), read once per attempt, file removed immediately after | New — today discarded entirely (spec defect #2) |

## Retry attempt (new, ephemeral, one per loop iteration)

| Field | Type | Meaning |
|---|---|---|
| `attempt number` | integer, 1..3 | Which of the bounded 3 attempts this is (FR-003, research.md D1) |
| `outcome` | `success` \| `permanent-not-found` \| `permanent-credential` \| `transient` \| `unclassified` | The classifier's verdict for this attempt (research.md D2). Only `permanent-*` stops the loop before the budget is exhausted (FR-002); `transient` and `unclassified` are both retried (FR-009) and differ only in what the eventual exhaustion message says (FR-006) |
| `diagnostic` | string, raw (pre-sanitisation) | Captured stderr, or a synthetic string (`"gh exited 0 but returned an empty state"`) when the failure is a zero-exit empty result (research.md D5) |

A `permanent-*` outcome is reported immediately (`::error::`, exit 1) and
the loop never reaches a further attempt (FR-002, US3). A `transient` or
`unclassified` outcome on any attempt before the last is logged with
`::warning::` (never `::error::` — FR-007 forbids annotating the run as
failed for a retried, ultimately-successful read) and the loop continues.
The *last* attempt's `outcome`/`diagnostic`, if still `transient` or
`unclassified`, becomes the exhaustion failure's content (FR-006).

## Failure classification (existing concept, spec Key Entities — now a concrete two-pattern allow-list)

| Class | Pattern (case-insensitive) | Treatment | Reported wording |
|---|---|---|---|
| Not found / not visible | `Could not resolve to an.*[Ii]ssue`, `HTTP 404` | Fail immediately, no retry (FR-002) | "may not exist, or the token lacks issues: read" (today's wording, now scoped to only this class — FR-005) |
| Credential rejected | `HTTP 401`, `Bad credentials`, `Resource not accessible by integration`, scope-shaped wording | Fail immediately, no retry (FR-002) | Names the credential as the cause, does not mention the issue (FR-005) |
| Everything else (transient-recognised or unclassified, including rate-limit 403s and an empty successful read) | No match against either pattern above | Retried up to the budget (FR-009) | Only surfaces in the FR-006 exhaustion message, tagged by whichever sub-class the *last* attempt was |

This is the whole of the classifier: two allow-listed permanent patterns,
retry as the unconditional default otherwise (research.md D2's rationale
for why an allow-list of permanent conditions, not a deny-list of
"transient-looking" ones, is what makes FR-009's "never-seen-before fault"
requirement hold without a third branch).

## Retry budget (existing concept, spec Key Entities — now concrete constants)

| Constant | Value | FR/SC it satisfies |
|---|---|---|
| Max attempts | 3 | Spec Assumptions ("Three attempts... is the right size") |
| Per-attempt timeout | 4 seconds | FR-001 (timeout is a named transient class), FR-003 |
| Inter-attempt delay | 1 second (after attempts 1 and 2 only) | FR-003 |
| Worst-case total added time | 14 seconds (`4+1+4+1+4`) | FR-003, SC-004 (≤15s ceiling) |

Fixed inside the step, not exposed as a composite input (spec Assumptions:
exposing them "would widen the published contract of a composite whose
whole virtue is being small").

## Diagnostic output (existing concept, spec Key Entities — now rendered, not discarded)

| Stage | Transformation | FR |
|---|---|---|
| Raw | Captured stderr, or the synthetic empty-state string | FR-004 |
| Collapsed | `\r`/`\n` replaced with a space, repeated whitespace collapsed | FR-018 |
| Bounded | Capped at 300 characters, `… (truncated)` suffix if longer | FR-018 |
| Escaped | `%` → `%25` (GitHub workflow-command escaping) | FR-018 |
| Never includes | The literal token value — never in scope for anything the step prints (research.md D4) | FR-017 |

The rendered form is what appears in every `::warning::`/`::error::` line
this step emits; the raw form never reaches an annotation directly.

## `wing-commander-lifecycle-gate` composite outputs (existing, UNCHANGED)

| Field | Type | Meaning |
|---|---|---|
| `state` | string (`OPEN`/`CLOSED`) | Set exactly once, only on a successful read (any attempt) — FR-010, FR-015 |
| `is-open` | string (`"true"`/`"false"`) | Unchanged derivation from `state`; the unrecognised-value fail-loud path (FR-008) is untouched by this feature and runs only after a successful read, outside the retry loop |

No new output. A retried read that eventually succeeds produces exactly
the same `state`/`is-open` pair a first-attempt success would (FR-007).

## Gate registry entry (new — Gate 25 in `.github/workflows/lint-workflows.yml`)

| Field | Value |
|---|---|
| Gate number | 25 (next unused; the repository's gate numbering is append-only per feature, not renumbered — research.md D7, confirmed against the file's existing Gate 1–24 sequence) |
| Name | "Gate 25 — the lifecycle gate retries transient failures and fails fast on permanent ones" |
| Script | `.github/scripts/verify-lifecycle-gate-retry.py` |
| Proves | FR-011 (retry-then-succeed), FR-012 (fast-fail, exactly one attempt), FR-013 (four required mutations each independently fail the suite), FR-014 (the gate step's own presence/wiring is itself checked, so its removal is caught) |

## `gh` stub (new, ephemeral, coverage-only — not part of the shipped composite)

| Field | Type | Meaning |
|---|---|---|
| `call count` | integer, persisted in a file under `RUNNER_TEMP` for the duration of one `run_step` invocation | Incremented by the stub script on every invocation; lets a single scenario's stub script vary its exit code/stdout/stderr by "which call is this" (research.md D6) |
| `scenario` | one of: fail-transiently-then-succeed, always-not-found, always-credential-rejected, fail-unrecognised-then-succeed, always-transient (budget exhaustion) | Selects which generated stub script `verify-lifecycle-gate-retry.py` writes to `bindir/gh` for a given test case |

Exists only inside the coverage script's own temp directories, torn down
with the rest of `run_step`'s working directory per test case; never
touches the shipped composite or any real GitHub API.
