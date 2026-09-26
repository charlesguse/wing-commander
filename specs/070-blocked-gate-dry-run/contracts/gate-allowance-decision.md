# Contract: FR-001-FR-006, FR-009 — the amended merge-decision script and the new gate-allowance-decision script

research.md D1/D2/D3 explain why the empty-rollup-blocked condition gets a
new decision-script token instead of a re-derived check in the `poll` step,
and why the elapsed-time judgment is a second pure script rather than inline
bash. This document is the authoritative contract for this feature's two
script changes; it sits beside, and does not replace,
`specs/055-unattended-e2e-gates/contracts/gate-decision-scripts.md`, which
still governs every other branch of `auto-release-e2e-merge-decision.sh`
and all of `auto-release-e2e-clarify-decision.sh`.

## `.github/actions/_shared/auto-release-e2e-merge-decision.sh` (AMENDED)

**Invocation**: unchanged —
`bash .github/actions/_shared/auto-release-e2e-merge-decision.sh
"$HEAD_REF_PREFIX" "$SLUG" "$EXPECTED_BASE" <<<"$PR_LIST_JSON"`

**Decision logic**: unchanged except step 6:

1. Empty array: print `none`. *(unchanged)*
2. `headRefName` mismatch: print `wrong-attempt`. *(unchanged)*
3. `baseRefName` mismatch: print `wrong-base`. *(unchanged)*
4. `isDraft` true: print `wait`. *(unchanged)*
5. `mergeable == "CONFLICTING"`: print `conflicting`. *(unchanged)*
6. `mergeStateStatus == "BLOCKED"`: inspect `statusCheckRollup` exactly as
   today (empty array, or every entry not yet `COMPLETED`/`COMPLETED` with
   no `conclusion`, or a legacy StatusContext entry in `PENDING`/`EXPECTED`
   → "nothing resolved"; anything else → "durably blocked"). **CHANGED**:
   if nothing is resolved, print `blocked-pending` (was `wait`). If durably
   blocked, print `blocked` unchanged.
7. `mergeStateStatus` is `UNKNOWN` or `BEHIND`: print `wait`. *(unchanged)*
8. Otherwise: print `merge` followed by the PR `number`. *(unchanged)*

**Output**: one of `none` / `wrong-attempt` / `wrong-base` / `wait` /
`conflicting` / `blocked` / **`blocked-pending` (NEW)** / `merge\n<number>`
on stdout. `conflicting`, `blocked`, `wrong-attempt`, and `wrong-base` remain
immediate `fail-gate-stall` triggers with no waiting allowance, exactly as
spec 055 specifies — this feature adds no waiting allowance to any of those.
`blocked-pending` is the only token this feature routes through the new
allowance-decision script below rather than deciding immediately; it is
never itself a terminal decision.

## `.github/actions/_shared/auto-release-e2e-gate-allowance-decision.sh` (NEW)

**Invocation**:
```
bash .github/actions/_shared/auto-release-e2e-gate-allowance-decision.sh \
  "$MERGE_DECISION" "$BLOCKED_SINCE" "$NOW" "$ALLOWANCE_SECONDS"
```

Pure function, no `gh` calls, no file reads beyond its own arguments —
mirrors the merge-decision script's "never calls `gh` or the network
itself" contract (Constitution VIII, research.md D2).

- `MERGE_DECISION`: the exact token the merge-decision script printed this
  iteration for this gate (its first line, if `merge`) — one of `none` /
  `wrong-attempt` / `wrong-base` / `wait` / `conflicting` / `blocked` /
  `blocked-pending` / `merge`.
- `BLOCKED_SINCE`: this gate's `gate_blocked_since[$prefix]` value carried
  from the previous iteration — an integer `$SECONDS` value, or the empty
  string if this gate has not been continuously observed `blocked-pending`
  since its last reset.
- `NOW`: the loop's current `$SECONDS`.
- `ALLOWANCE_SECONDS`: the configured allowance — `1200` (20 minutes,
  FR-004) via the new `GATE_BLOCKED_ALLOWANCE_SECONDS` env constant in
  production; a fixture may pass any integer, including small values, since
  this script performs no real waiting.

**Decision logic**:
1. If `MERGE_DECISION` is not `blocked-pending`: print `clear` (FR-005 —
   the gate has left the blocked-with-unresolved-checks state, or never
   entered it this iteration; the caller resets its timer).
2. Else if `BLOCKED_SINCE` is empty: print `start` (first continuous
   `blocked-pending` observation; the caller records `NOW` as the new
   `blocked_since`).
3. Else if `NOW - BLOCKED_SINCE >= ALLOWANCE_SECONDS`: print `stall`
   (FR-003/FR-004 — the allowance is exhausted; the caller writes the
   `fail-gate-stall` verdict and exits).
4. Else: print `wait` (still within the allowance; the caller keeps
   polling, `blocked_since` unchanged).

**Output**: one of `clear` / `start` / `wait` / `stall` on stdout. Never
calls `gh pr merge` or writes a verdict itself — exactly like the merge-
decision script, all durable action stays in the `poll` step's own bash,
which is the only place `write_verdict`/`emit_verdict` are defined.

## Call site (`auto-release.yml`'s `poll` step, inside the existing
per-gate `for prefix in ...` loop, immediately after a successful merge-
decision call)

Extends the existing `case "$merge_head" in ... esac` dispatch
(`auto-release.yml:998-1029`) with one more arm:

```
blocked-pending)
  allowance_decision="$(bash .github/actions/_shared/auto-release-e2e-gate-allowance-decision.sh \
    "$merge_head" "${gate_blocked_since[$prefix]}" "$SECONDS" "$GATE_BLOCKED_ALLOWANCE_SECONDS")"
  case "$allowance_decision" in
    start) gate_blocked_since[$prefix]="$SECONDS" ;;
    stall)
      write_verdict "fail-gate-stall" "${gate_name[$prefix]}" "gh pr merge succeeds" \
        "PR #${pr_number}: required checks never reported a result"
      emit_verdict
      exit 0
      ;;
    # wait: nothing to do, blocked_since unchanged.
  esac
  ;;
```

Every other arm of the existing `case` (`merge`, `conflicting`, `blocked`,
`wrong-attempt`, `wrong-base`) additionally clears
`gate_blocked_since[$prefix]=""` (or calls the allowance script with that
`merge_head` and applies its `clear` answer — either is equivalent, since
every one of those tokens is not `blocked-pending` and the allowance script
always answers `clear` for them; the tasks stage picks one form). The `wait`
arm (currently absent — `wait` falls through the `case` doing nothing) gains
the same clearing behavior, since a plain `wait` (draft, UNKNOWN, BEHIND)
must also reset a gate's timer per FR-005.

## Gate coverage

Both scripts ship with checked-in fixtures exercising every branch listed
above (Constitution VIII), extending the existing homes rather than adding
a new gate (research.md D5):

- `.github/scripts/verify-auto-release-e2e-gate-decisions.py` (Gate 66):
  `MERGE_SCENARIOS`' three existing "BLOCKED, still pending" entries move
  their `expect_head` from `wait` to `blocked-pending`; a new
  `ALLOWANCE_SCENARIOS` list + `run_allowance_suite()` exercises `start` /
  `wait` / `stall` / `clear`; matching entries are added to
  `MERGE_MUTATIONS` (for the renamed token) and a new `ALLOWANCE_MUTATIONS`
  list (for each of the four allowance branches).
- `.github/scripts/verify-auto-release-report.py` (Gate 52): one new
  `GATE_STALL_*` fixture using this contract's exact `expected`/`observed`
  strings, proving the rendering and "gate stall" classification path.

No new gate is registered in `lint-workflows.yml` — both gates already run
on changes to the files this feature touches.
