# Contract: FR-005, FR-006, FR-007, FR-009, FR-010, FR-023 — the two gate-decision scripts

research.md D5/D6 explain why these are plain, pure scripts under
`.github/actions/_shared/`, not composites, and why the fetch (network)
stays in the `poll` step while the decision (judgment) moves into these
scripts, per Constitution IX and Principle VIII's local-testability
requirement.

Revised by the PR #389 maintainer code review: both scripts now take
their JSON on stdin, not argv (a long issue's comment history can exceed
Linux's 128 KB per-argument limit), and the clarify script's "already
answered" check is now actor-gated rather than "any later comment", per
the findings below.

## `.github/actions/_shared/auto-release-e2e-clarify-decision.sh` (NEW)

**Invocation**:
```
bash .github/actions/_shared/auto-release-e2e-clarify-decision.sh decide "$ISSUE_AUTHOR_ID" "$ROUNDS_ANSWERED" <<<"$COMMENTS_JSON"
bash .github/actions/_shared/auto-release-e2e-clarify-decision.sh satisfied "$ISSUE_AUTHOR_ID" <<<"$COMMENTS_JSON"
bash .github/actions/_shared/auto-release-e2e-clarify-decision.sh markers <<<"$COMMENTS_JSON"
```

- `COMMENTS_JSON` (stdin): the array `gh api
  repos/<owner>/<repo>/issues/<n>/comments --paginate` returns (REST
  shape, the same shape intake.yml's own comment-trust-gate reads):
  entries of `{id, user:{login,id,type}, author_association, body,
  created_at}`.
- `ISSUE_AUTHOR_ID`: the issue author's numeric id (`.user.id` from `gh
  api repos/<owner>/<repo>/issues/<n>`).
- `ROUNDS_ANSWERED` (`decide` only): integer, how many times this attempt
  has already posted the Prepared answer.

A comment QUALIFIES as an answer exactly when it would pass intake.yml's
own comment-trust-gate (`intake.yml:524`): `user.type != "Bot"`, and
either `author_association` is `OWNER`/`MEMBER`/`COLLABORATOR` or
`user.id` is the issue author's. A comment that does not qualify — a bot
notice (metrics rollup, watchdog), or a human with no standing to answer
— is never read as a reply. This closes the deadlock the original "any
later comment" rule allowed.

**`markers` decision logic** (the single home for the marker predicate —
auto-release.yml's pass-path assertion calls this instead of re-deriving
it): return the JSON array, oldest first, of every comment whose `body`
contains `[!IMPORTANT]` and either `Answer the open clarification
questions` or `Answer the remaining clarification questions` (the literal
strings `intake.yml:1094-1102` and `clarify.yml:874-882` post).

**`decide` decision logic**:
1. Call `markers`. If empty: print `none` (no clarification gate is open
   — FR-008).
2. Otherwise, take the latest marker. If no qualifying comment postdates
   it: this round is unanswered.
   - If `ROUNDS_ANSWERED < MAX_CLARIFICATION_ROUNDS` (env, default 3,
     research.md D7): print `reply` followed by the Prepared answer body
     (research.md D8) on subsequent lines.
   - Else: print `exhausted`.
3. If a qualifying comment already postdates the latest marker: print
   `wait` (this round is answered — by the harness or by a human, FR-010
   — waiting for the stage to consume it or ask again).

**`decide` output**: one of `none` / `reply\n<body>` / `wait` /
`exhausted` on stdout. No side effects — the caller posts the comment and
increments `ROUNDS_ANSWERED` only after seeing `reply`, and only when the
poster is the harness (a human's own qualifying reply never touches this
counter).

**`satisfied` decision logic**: for every marker `markers` returns, a
qualifying comment must postdate it. Print `ok` if true of all of them
(including the vacuous case of zero markers), else `unsatisfied` — used
by auto-release.yml's pass-path assertion (FR-016/FR-018): reaching
`stage:done` is not on its own evidence the gate was satisfied, and a
human's answer must count, not only the harness's own (FR-010, the "a
human answers first" Edge Case).

## `.github/actions/_shared/auto-release-e2e-merge-decision.sh` (NEW)

**Invocation**: `bash .github/actions/_shared/auto-release-e2e-merge-decision.sh
"$HEAD_REF_PREFIX" "$SLUG" "$EXPECTED_BASE" <<<"$PR_LIST_JSON"`

- `PR_LIST_JSON` (stdin): the output of `gh pr list --head <prefix><slug>
  --json
  number,headRefName,baseRefName,mergeable,mergeStateStatus,isDraft,state,statusCheckRollup`
  (an array; normally 0 or 1 entries, since the caller already filters
  `--head` to the exact expected branch name).
- `HEAD_REF_PREFIX`: one of `spec-draft/`, `plan/`, `spec/` (the finalize
  gate reuses the `spec/<slug>` integration branch as its PR head).
- `SLUG`: this attempt's feature slug, derived from this attempt's own
  kickoff issue (research.md D10 — see the Foundational section below;
  not merely the first open PR at that prefix repository-wide).
- `EXPECTED_BASE`: the base branch this gate's PR is required to target
  (research.md D9): the default branch for the spec-draft and finalize
  gates, `spec/<slug>` for the plan gate.

**Decision logic**:
1. If the array is empty: print `none` (this gate hasn't opened yet).
2. If the single entry's `headRefName` isn't exactly `<prefix><slug>`:
   print `wrong-attempt` (FR-009 — a leftover from a different attempt;
   never acted on).
3. If `baseRefName` isn't exactly `EXPECTED_BASE`: print `wrong-base` (a
   retargeted PR; never merged).
4. If `isDraft` is true: print `wait` (not ready).
5. If `mergeable == "CONFLICTING"`: print `conflicting`.
6. If `mergeStateStatus == "BLOCKED"`: inspect `statusCheckRollup`. If any
   entry there is not yet `COMPLETED`, or is `COMPLETED` with no
   `conclusion` recorded yet, the PR is still waiting on a check, not
   durably blocked: print `wait`. Otherwise print `blocked`.
7. If `mergeStateStatus` is `UNKNOWN` or `BEHIND` (GitHub still computing,
   or checks still running): print `wait`.
8. Otherwise (`mergeable == "MERGEABLE"`, `mergeStateStatus` in `CLEAN` /
   `UNSTABLE` / `HAS_HOOKS`): print `merge` followed by the PR `number`.

**Output**: one of `none` / `wrong-attempt` / `wrong-base` / `wait` /
`conflicting` / `blocked` / `merge\n<number>` on stdout. `conflicting`,
`blocked`, `wrong-attempt`, and `wrong-base` are each a distinct
`fail-gate-stall` reason (FR-023); the caller never retries after
receiving one of them, per research.md D9.

## Foundational: binding `SLUG` to this attempt (FR-009, research.md D10)

`SLUG` is resolved once per attempt, inside the `poll` step, from a PR
whose title ends in the exact literal `(#<ISSUE>)` where `<ISSUE>` is
this attempt's own kickoff issue number — the same `(#<issue-number>)`
suffix `intake.yml`'s own `gh pr create --title` call stamps on the
spec-draft PR. This binds the slug to the attempt that opened it, closing
the gap where the previous, repository-wide "first open spec-draft/* PR"
lookup could never actually observe a `wrong-attempt` decision.

## Call site (one, `auto-release.yml`'s `poll` step)

Both scripts are invoked once per poll iteration (every 30s), once for
the clarification gate and once per not-yet-merged PR gate, from inside
the existing `while [ "$SECONDS" -lt "$POLL_BUDGET_SECONDS" ]` loop. A
gate already evidenced as driven (research.md D12) is skipped on later
iterations rather than re-checked. A read (`gh issue view`/`gh pr list`
fetching the JSON these scripts consume) or a decision-script crash that
fails repeatedly is bounded the same way a failed write already is
(maintainer feedback; see the `poll`-step comment above `MAX_GATE_WRITE_FAILURES`).

## Gate coverage

Both scripts ship with a checked-in fixture test exercising every branch
listed above (Constitution VIII: "every failure branch a gate ships MUST
be exercised by a checked-in fixture") — fixtures live in
`.github/scripts/verify-auto-release-e2e-gate-decisions.py` (Gate 66; the
report-outcome fixtures for the new `fail-gate-stall` outcome and the
three-way classification stay in
`.github/scripts/verify-auto-release-report.py`, Gate 52).
