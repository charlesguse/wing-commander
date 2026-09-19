# Contract: FR-005, FR-006, FR-007, FR-009, FR-010, FR-023 — the two gate-decision scripts

research.md D5/D6 explain why these are plain, pure scripts under
`.github/actions/_shared/`, not composites, and why the fetch (network)
stays in the `poll` step while the decision (judgment) moves into these
scripts, per Constitution IX and Principle VIII's local-testability
requirement.

## `.github/actions/_shared/auto-release-e2e-clarify-decision.sh` (NEW)

**Invocation**: `bash .github/actions/_shared/auto-release-e2e-clarify-decision.sh
"$COMMENTS_JSON" "$HARNESS_LOGIN" "$ROUNDS_ANSWERED"`

- `COMMENTS_JSON`: the output of `gh issue view <n> --json comments`
  (an array of `{author:{login}, body, createdAt}`), fetched by the caller.
- `HARNESS_LOGIN`: the fixture maintainer identity's username.
- `ROUNDS_ANSWERED`: integer, how many times this attempt has already
  posted the Prepared answer.

**Decision logic**:
1. Find the latest comment whose `body` contains `[!IMPORTANT]` and either
   `Answer the open clarification questions` or `Answer the remaining
   clarification questions` (the literal strings `intake.yml:1094-1102`
   and `clarify.yml:874-882` post).
2. If none found: print `none` (no clarification gate is open — FR-008).
3. If found, and no comment from `HARNESS_LOGIN` exists later in the array
   than that question comment: this round is unanswered.
   - If `ROUNDS_ANSWERED < 3` (research.md D7): print `reply` followed by
     the Prepared answer body (research.md D8) on subsequent lines.
   - Else: print `exhausted`.
4. If found, and a comment from `HARNESS_LOGIN` already exists later than
   it: print `wait` (this round is answered; waiting for the stage to
   consume it or ask again).

**Output**: one of `none` / `reply\n<body>` / `wait` / `exhausted` on
stdout. No side effects — the caller posts the comment and increments
`ROUNDS_ANSWERED` only after seeing `reply`.

## `.github/actions/_shared/auto-release-e2e-merge-decision.sh` (NEW)

**Invocation**: `bash .github/actions/_shared/auto-release-e2e-merge-decision.sh
"$PR_LIST_JSON" "$HEAD_REF_PREFIX" "$SLUG"`

- `PR_LIST_JSON`: the output of `gh pr list --head <prefix><slug> --json
  number,headRefName,mergeable,mergeStateStatus,isDraft,state` (an array;
  normally 0 or 1 entries, since the caller already filters `--head` to
  the exact expected branch name).
- `HEAD_REF_PREFIX`: one of `spec-draft/`, `plan/`, `spec/` (the finalize
  gate reuses the `spec/<slug>` integration branch as its PR head).
- `SLUG`: this attempt's feature slug, derived from the kickoff issue
  title (research.md D10).

**Decision logic**:
1. If the array is empty: print `none` (this gate hasn't opened yet).
2. If the single entry's `headRefName` isn't exactly `<prefix><slug>`:
   print `wrong-attempt` (FR-009 — a leftover from a different attempt;
   never acted on).
3. If `isDraft` is true: print `wait` (not ready).
4. If `mergeable == "CONFLICTING"`: print `conflicting`.
5. If `mergeStateStatus == "BLOCKED"`: print `blocked`.
6. If `mergeStateStatus` is `UNKNOWN` or `BEHIND` (GitHub still computing,
   or checks still running): print `wait`.
7. Otherwise (`mergeable == "MERGEABLE"`, `mergeStateStatus` in `CLEAN` /
   `UNSTABLE` / `HAS_HOOKS`): print `merge` followed by the PR `number`.

**Output**: one of `none` / `wrong-attempt` / `wait` / `conflicting` /
`blocked` / `merge\n<number>` on stdout. `conflicting`, `blocked`, and
`wrong-attempt` are each a distinct `fail-gate-stall` reason (FR-023); the
caller never retries after receiving one of them, per research.md D9.

## Call site (one, `auto-release.yml`'s `poll` step)

Both scripts are invoked once per poll iteration (every 30s), once for
the clarification gate and once per not-yet-merged PR gate, from inside
the existing `while [ "$SECONDS" -lt "$POLL_BUDGET_SECONDS" ]` loop
(`auto-release.yml:509`). A gate already evidenced as driven (research.md
D12) is skipped on later iterations rather than re-checked.

## Gate coverage

Both scripts ship with a checked-in fixture test exercising every branch
listed above (Constitution VIII: "every failure branch a gate ships MUST
be exercised by a checked-in fixture") — fixtures live alongside
`.github/scripts/verify-auto-release-report.py`'s existing fixture style,
since that is the gate this feature extends to also assert the new
`fail-gate-stall` outcome and the three-way classification (data-
model.md's Failure report classification table).
