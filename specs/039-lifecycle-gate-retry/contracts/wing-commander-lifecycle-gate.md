# Contract Delta: `wing-commander-lifecycle-gate` (existing composite, `Check lifecycle issue state` step rewritten)

The composite was introduced by `specs/022-gate-closed-lifecycle/contracts/
wing-commander-lifecycle-gate.md`. This document records what this feature
changes and, explicitly, what it does not. Everything not listed under
"Changes" is unchanged from the specs/022 contract, still in force.

## Inputs — UNCHANGED

| Input | Required | Description |
|---|---|---|
| `issue-number` | yes | The lifecycle issue to check |
| `token` | yes | A token with at least `issues: read` |

No new input. Attempt count, per-attempt timeout, and inter-attempt delay
are internal constants, not inputs (FR-015, spec Assumptions).

## Outputs — UNCHANGED

| Output | Values | Meaning |
|---|---|---|
| `state` | `OPEN` \| `CLOSED` | Set exactly once, on the first successful read, whichever attempt that is (FR-007, FR-010) |
| `is-open` | `"true"` \| `"false"` | Unchanged derivation |

## Behavior — CHANGED

The single step `Check lifecycle issue state` now attempts its `gh issue
view "$ISSUE_NUMBER" --json state --jq .state` read up to 3 times
(data-model.md Retry budget) instead of once:

1. Each attempt runs the read wrapped in `timeout 4`, with stderr captured
   to a per-attempt temp file (research.md D3) instead of discarded.
2. On success (non-empty `state`), the loop stops immediately — a
   later-attempt success is indistinguishable in output from a
   first-attempt success (FR-007, SC-005).
3. On failure, the captured diagnostic is classified (data-model.md
   Failure classification):
   - **Not found** or **credential rejected** → the step fails immediately
     with `::error::`, quoting the sanitised diagnostic (research.md D4)
     and naming the specific condition (FR-002, FR-005). No further
     attempt is made (US3, FR-012).
   - Anything else → logged with `::warning::` (not `::error::` — FR-007)
     and, if attempts remain, retried after a 1-second delay.
4. If the budget is exhausted with no success, the step fails with a
   single `::error::` stating: the read was retried, how many attempts
   were made, whether the retried failures were a recognised transient
   class or unclassified, and the last attempt's sanitised diagnostic
   (FR-006).
5. Steps 3–4 of the specs/022 contract (the unrecognised-non-empty-state
   fail-loud path, and "no default on an ambiguous value") are **unchanged
   and unaffected** — they run once, after the retry loop has already
   produced a non-empty `state`, exactly as before this feature. This path
   is never retried (FR-008): a successful read with an unrecognised value
   is an answer, not an absence of one.

## Non-goals — UNCHANGED, plus one addition

All four non-goals from the specs/022 contract still hold. This feature
adds:

- Does not expose attempt count, timeout, or delay as configurable inputs
  (spec Assumptions — keeping the composite's published surface small).
- Does not change what the calling job does when the gate ultimately fails
  — the `implement` stage's silent chain-stop on gate failure is unchanged
  and out of scope (FR-016, tracked as #231).
- Does not retry, or change the behavior of, the unrecognised-state
  fail-loud path (FR-008).

## Permissions — UNCHANGED

Still requires only `issues: read` to check state. No new permission scope.

## Caller contract — UNCHANGED

The YAML snippet in the specs/022 contract (`Check lifecycle issue state`
step invocation, `Note closed lifecycle and stop` follow-up) is unchanged
byte-for-byte from a caller's perspective — same `with:` block, same
`steps.lifecycle-gate.outputs.*` reads. None of the six calling workflows
(`clarify.yml`, `finalize.yml`, `implement.yml`, `intake.yml`,
`pr-conversation.yml`, `tasks.yml`) needs any edit (FR-015, SC-008).
