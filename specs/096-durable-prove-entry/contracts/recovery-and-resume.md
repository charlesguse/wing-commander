# Contract: Recovery of a Stranded Prove, and the Resume Step's Merged-PR Fix

This is this feature's working draft of the changes FR-021 requires
folding into `specs/057-autonomous-board-loop/contracts/prove-step.md` and
`contracts/board-item-marker.md`, and into
`specs/060-self-redrive-concurrency/contracts/directed-proof-run.md` and
`proof-outcome-taxonomy.md`, during implementation (research.md D9) — not a
second canonical source for any of them.

## Recovery entry (FR-001/FR-002/FR-011/FR-011a/FR-011b)

Three new steps in the `select` job (maintainer review, FR-012) run
immediately after the existing "Detect a merge whose proof run never
started (FR-010b)" step, each gated at minimum on the job-level entry gate
(kill switch clear, no implement cycle in flight):

1. "Pick a stranded prove to recover" picks the candidate (below) and
   exposes `issue-number`/`merged-pr`/`outcome-reason` as step outputs,
   empty when there is none.
2. "Re-check kill switch and stop requests before recovering it" calls
   `wing-commander-board-stop-check` scoped to that one issue, only when a
   candidate was found — this is the re-check FR-012 means: it runs as
   close to the dispatch as this job's structure allows, not the job-level
   entry gate alone, which can be minutes stale by the time displacement's
   own `gh` calls and the candidate search above have run.
3. "Dispatch the recovered prove" does the busy-check, marker write and
   dispatch (below), gated on step 2's own `outcome == 'success'` (not
   merely its `paused` output — a failed or skipped recheck must not read
   as "not paused") and `paused != 'true'`.

All three carry `continue-on-error: true`: a lasting failure in any of
them must not fail this job's own success() and stall "Resume" and
everything after it.

**Candidate set**: issues from this run's own
`board-recent-merges-by-issue.json` (the displacement step's fetch, reused
verbatim) that are still open, whose newest board-item marker has
`step == "prove"` and `outcome_reason` equal to
`board_prove_displacement.RECORDED_REASON` or the literal `"uncorrelated"`,
and whose marker does not carry `recovery_attempted: true`
(`board_prove_recovery.find_recoverable_items()`, research.md D3/D5).
Ownership (`board:owned`, head-in-this-repository) is inherited from the
displacement step's own `gh pr list --label board:owned` query — no second
ownership check is added here (FR-013).

**Selection**: at most one candidate, oldest marker timestamp first
(FR-011b). Every candidate not chosen this run is left exactly as found —
still recoverable, not touched (FR-011b's "must remain recoverable rather
than falling to triage or losing its attempt").

**Pre-dispatch check**: `board_prove.directed_proof_group_busy()` against a
fresh `gh run list`. `True` → stop; nothing durable is written for this
item this run (FR-011a: a dispatch not made for this reason does not spend
the attempt). `False` → proceed.

**Dispatch**: `gh workflow run board-loop.yml -f directed-stage=prove -f
directed-issue=<issue> -f directed-pr=<merged PR> -f
directed-recovery=true`. This is spec 060's existing directed dispatch
mechanism (`contracts/directed-proof-run.md`), not a new entry point or a
copy of it (FR-002) — `prove-gate`'s own directed branch re-derives the
PR's merged state and `board:owned` ownership live, via a fresh `gh api
repos/<owner>/<repo>/pulls/<PR>` fetch keyed off `directed-pr` (never
`github.event.pull_request`, which carries no payload at all on
`workflow_dispatch`); `prove`'s own directed branch separately re-derives
the changed paths the same way `fix`/`readiness` already do (`git diff
--name-only <base> HEAD`), satisfying FR-010 with no new re-derivation
code beyond that one PR fetch (maintainer review: the fetch and the
ownership read off it were both broken before this feature's own fix —
see board-loop.yml's "Resolve the originating issue and decide whether
prove is entered" step).

**Before the dispatch call** (maintainer review, SC-008 "retried at most
once"): write the marker `--step prove --outcome-reason <unchanged>
--recovery-attempted`, and post a comment naming that the
displaced/uncorrelated proof is being recovered. This spends the item's
one recovery attempt regardless of whether the dispatch call that follows
itself succeeds — a dispatch that succeeds but whose comment then fails
would otherwise leave no durable record, and the next tick would see the
same candidate as still-recoverable and dispatch it again (a duplicate,
which SC-008 forbids). The rarer inverse (the comment posts, the dispatch
itself then fails) leaves a stranded item a human must re-drive manually,
never a duplicate — this step still does not wait for anything
(research.md D3), and the comment failing is itself a loud, non-fatal
(`continue-on-error: true`) step failure, not a silent one.

**The dispatched run** (a directed `prove` run carrying
`directed-recovery=true`) performs the *same* actions-only decision,
re-drive, wait, and close-on-success/leave-open-otherwise logic as any
other entry into `prove-gate`/`prove` (FR-002, "decision for decision").
Its own "Record the proof outcome" step additionally:

- states the recovery in its comment (FR-014: "what it adds is the
  statement that the displaced proof was recovered, and the proof outcome,
  each distinct from every reason spec 060's taxonomy enumerates");
- writes `--outcome-reason <this run's own outcome_reason>
  --recovery-attempted` on every marker write (success → `proven`, still
  carrying the flag for legibility; any non-success → `prove`), so a
  second re-displacement of *this* recovery attempt cannot look like a
  fresh, unspent one (closing the loop research.md D6 opens);
- labels the run's metrics record `"proof (recovered): <outcome_reason>"`
  instead of `"proof: <outcome_reason>"` (FR-015) when
  `inputs.directed-recovery == 'true'`.

A `failure` or `unfinished` outcome on the recovery dispatch is not
retried — Q3/FR-011 name only the displacement and `uncorrelated` shapes as
recoverable, and `recovery_attempted` is already `true` once the one
dispatch was made, regardless of its outcome (FR-011a).

## The resume step's merged-PR clause (FR-007/FR-008/FR-009)

`board-loop.yml`'s resume step (`:572-871`) gains one clause, splitting the
existing "resolved by number but not OPEN" clause (today `:792-810`) on
`pr_state`:

- `pr_state == "MERGED"` → **new**: `step = "prove"`, every other field
  (`pr`, `branch`, `round`, `base_sha`) cleared — mirrors the value
  `board_prove_displacement`'s own marker write already uses for this
  situation, and holds whether or not that step has already run this tick
  (FR-007's own "whether or not spec 060's displacement step has yet
  written its `prove` marker").
- `pr_state == "CLOSED"` (unmerged) → unchanged: `step = "triage"`, same
  fields cleared, same reason string (FR-008's "unchanged").

No new step name is introduced (`"prove"` is already a member of
`FIX_OR_LATER_STEPS`); `_awaiting_merge_holds()` and
`in_flight_candidate()`/`select()`'s own exclusion of `step == "prove"` are
unchanged (FR-009's "one list").

## Acceptance mapping

- User Story 1, Acceptance Scenarios 3, 4, 5 — the recovery entry above.
- User Story 2, all Acceptance Scenarios — the resume-step clause above.
- User Story 4, Acceptance Scenarios 1-3 — the comment/label additions and
  the durable `recovery_attempted` flag.
- Edge cases "the merged PR is not the loop's own" (ownership inherited),
  "two merges displaced in the same window" (FR-011b's leave-recoverable
  rule), "the directed-proof group is already busy" (the pre-dispatch
  check), "the issue was closed by a human" (candidate filtering against
  open issues), "the displaced run's own event payload is gone" (D6's
  reuse of the pre-existing re-derivation), "the re-drive target is
  board-loop.yml itself" (unchanged — this feature's dispatch is a
  `stage == "prove"` directed run like any other), "a `prove` marker from a
  failed earlier attempt" (excluded by `is_recoverable()`'s literal
  match), "the kill switch is set" (the shared `if:` gate), "a
  merged-but-unproven item a maintainer stopped" (a `stalled` marker is
  neither recoverable literal, so `is_recoverable()` excludes it
  unchanged) — all satisfied by the mechanism above without a special
  case per edge case.
