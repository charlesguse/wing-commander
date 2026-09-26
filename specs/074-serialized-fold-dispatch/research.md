# Phase 0 Research: One Fold Queue Per PR

All line numbers below are against `main` at `91e23d4` (this branch's
starting point). Every decision resolves a design question spec.md leaves
to planning (its own Clarifications already settled the three scope-level
questions cited inline below); none of these reopen those.

## D1 — Admission mechanism: a per-run ticket ledger gating entry to the existing GitHub concurrency group, not a replacement for it

**Decision**: Keep every existing job-level `concurrency: group:
wing-commander-<spec-dir>` block exactly as it is today on `act`,
`dispatch-once`, `implement`, and `implement`'s `stalled`. In front of
each, add a new prerequisite job — `fold-turn-act`, `fold-turn-dispatch`,
`fold-turn-implement` — that carries **no** concurrency group of its own,
enqueues one ticket for its whole run (not one per leg — see below), and
polls a shared per-spec ledger until that ticket is at the head of the
queue. The downstream job (`act`/`dispatch-once`/`implement`) gains
`needs: fold-turn-*` and only attempts to enter the GitHub concurrency
group once its ticket has already been granted.

**Rationale**: GitHub evaluates a job's `concurrency:` block before any of
its steps run, so no step-level logic inside `act` or `dispatch-once`
itself can prevent that job from becoming a second contender for the
group's one pending slot — the eviction decision is made before the job
has executed anything. The only lever available is gating *whether a job
is scheduled at all* via `needs:`, which GitHub evaluates first. Because
the ledger only ever grants one ticket at a time system-wide for a given
`spec-dir`, at most one job across every in-flight stage-9 run (plus at
most one already-running holder) is ever attempting to enter the GitHub
group — so its one-pending-slot rule is never exercised by two stage-9-
family jobs at once, and today's plan/tasks/finalize/rebase exclusivity
(spec 013's contract) is untouched because those jobs' own concurrency
blocks are unmodified.

**Ticket granularity is per run, not per leg.** GitHub Actions resolves a
matrix job's `needs:` on a *matrix* job at the level of the whole job —
every instance of the needed matrix must complete before *any* instance of
the dependent matrix starts. A per-leg ticket scheme (a `fold-turn`
matrix mirroring `act`'s `matrix.id` legs, with `act` matrix-`needs:`-ing
it) would require every leg of a run to be granted its ticket — meaning
each leg would have to reach the head of the *global* per-spec queue —
before the *first* leg of that run could even begin folding, and since a
ticket is only released once its `act` leg actually runs, no later ticket
in the same run could ever be granted while earlier ones wait on a job
that cannot start until they are: an unconditional deadlock. Granting one
ticket per *run* instead (covering the whole `max-parallel: 1` matrix,
which already fully serializes legs within one run per spec.md's own
Assumptions) sidesteps this entirely: `act` (matrix) can safely `need:` a
single non-matrix `fold-turn-act` instance, because a matrix job depending
on a single-instance job is ordinary, well-supported GitHub Actions
behavior.

**Alternatives considered**:
- *Serialize whole stage-9 runs in one per-PR group.* Explicitly rejected
  by the spec itself (FR-017a) — that group has the identical
  one-pending-slot limitation, so a third review would evict the pending
  second run in a new place, and it would also delay `classify-and-announce`'s
  prompt acknowledgment (FR-017), which must not wait on another run's
  folds.
- *GitHub Environments as a manual-approval-shaped queue.* Environments
  serialize deployments to a named environment one at a time, but expose
  only a single current-deployment/waiting-reviewer state, not an ordered
  N-deep queue, and are a heavyweight, UI-visible primitive for what
  should be invisible machine bookkeeping. Rejected.
- *A GitHub Issue comment or label as a mutex.* Would need polling via
  issue reads/writes, adds comment noise to the lifecycle issue (which
  Constitution III reserves for lifecycle notices, not internal
  bookkeeping), and has no atomic compare-and-swap primitive of its own —
  the underlying git-ref CAS this plan already needs would have to exist
  anyway. Rejected as strictly worse than writing directly to a ref.

## D2 — Ledger persistence: a dedicated internal git ref, not the spec branch, not the metrics ledger

**Decision**: A new branch, `wing-commander-fold-queue`, holds one JSON
document (data-model.md) keyed by `spec-dir`. Composites read/write it
using the identical fetch-current-tip → rebuild → commit → push,
reset-and-retry-on-rejection loop `wing-commander-metrics-persist` already
uses (`.github/actions/wing-commander-metrics-persist/action.yml:373-509`),
parameterized by a `jq` transform per operation (enqueue / release /
claim) instead of a plain append.

**Rationale**: This repository already has exactly one accepted pattern
for arbitrarily-many concurrent writers serializing themselves without a
GitHub concurrency group — optimistic retry against a git ref no scarce
primitive protects. Reusing it here means the *ledger's own* writes can
never suffer the eviction bug this feature exists to fix (a write is a
step inside an already-running job, not a second job contending for a
pending slot). A dedicated branch, rather than reusing the metrics
ledger, keeps a orthogonal-purpose, high-churn, frequently-read-then-
mutated document out of an append-only historical record with different
retention expectations; keeping it off the spec branch itself avoids
polluting the branch's real history with queue churn unrelated to the
spec's content, matching why the metrics ledger isn't the spec branch
either.

**Alternative considered**: a `.wing-commander/fold-queue.json` file
committed to the spec branch. Rejected — every enqueue/release/claim
would be a spec-branch commit indistinguishable in `git log` from a real
`fold(<id>):` commit, complicating exactly the attribution problem this
feature also has to fix (D3), and would need its own cleanup step wherever
`cleanup.yml` already prunes spec-branch history.

## D3 — Attribution: per-ticket completion records replace the base..tip git-log range scan

**Decision**: `act`'s per-run fold phase records, at release time (via
`wing-commander-fold-queue-release`), a completion entry under the
current round (data-model.md: `{leg_id, outcome, commit_sha}`) for every
leg it ran. `report-fold-outcomes` and `dispatch-once` stop reading
`git log --grep '^fold(' BASE_SHA..TIP_SHA` (today at
`pr-conversation.yml:2892-2926` and `:2707-2709`) and instead read this
run's own entries out of the ledger's round record.

**Rationale**: The range scan's premise — that everything between this
run's own pre-fold and post-fold tip belongs to this run — was already
false whenever two runs fold concurrently (spec.md's own Edge Cases
section, and the exact PR #414 mechanism); a concurrent run's `fold(<id>):`
commits land inside that range and get misattributed. A completion record
written by the code that actually performed (or didn't perform) the fold,
keyed by that run's own `run_id`/`leg_id`, has no such ambiguity — it
needs no range at all, only "what did *I* do," which is exactly what
FR-006 requires and what the existing job-name-suffix-matching workaround
in `report-fold-outcomes` (`:2921`, addressing issue #416's bare-vs-prefixed
job name bug) was already trying and failing to approximate from outside
the job.

**Cross-reference**: `specs/075-run-scoped-fold-evidence` (lifecycle issue
#565, routed from board-loop issue #416) is an open, unplanned
spec-request targeting this identical symptom from a narrower angle —
disambiguating `leg-N` ids across runs for the same range-scan approach.
Implementing D3 as designed here resolves the false-attribution defect
completely (FR-006/FR-011) without keeping the range scan at all, which
likely makes 075's narrower fix unnecessary. This plan does not change
075's own spec or routing — that overlap is flagged in this run's
findings for a maintainer to reconcile, per this run's own constraints.

## D4 — One dispatch per round: a round counter plus an atomic claim in the same ledger

**Decision**: The ledger tracks, per spec-dir, a monotonically increasing
`round` id that increments only when the queue transitions from fully
empty back to non-empty (a fresh `act`-kind ticket enqueues after the
previous round's queue emptied out). Every ticket's completion record is
filed under its round. `wing-commander-fold-queue-claim-dispatch` is
called by every run's `dispatch-once` once its own `fold-turn-dispatch`
ticket is granted; it performs one atomic ledger transaction that (a)
checks whether any `act`-kind ticket for this spec-dir is still enqueued
or running for the *current* round, and (b) if none remain and no dispatch
has yet been claimed for this round, marks the round claimed and returns
`should-dispatch: true` with every completion record the round has
accumulated so far (across every run that contributed to it) as
`folded-items`/`not-folded-items`; otherwise it returns
`should-dispatch: false` with no items, and the calling `dispatch-once`
releases its ticket and posts nothing.

**Rationale**: This directly implements the Clarifications session's
settled answer — "exactly one cycle for the whole overlapping set; the
later runs' folds ride along in it and the earlier runs' dispatches yield"
(FR-009) — as a single-winner compare-and-swap rather than a race two
runs could both win. Scoping the claim to a round (not a fixed time
window) is what makes the "arrives after dispatch has fired owns its own
cycle" edge case fall out for free: a run that starts a fresh round after
the prior round's dispatch already claimed gets its own round id and
therefore its own claim.

## D5 — Handing the implement run its ticket, not letting it self-enqueue

**Decision**: The same atomic transaction in D4 that wins the dispatch
claim also enqueues the `implement`-kind ticket for the about-to-be-
dispatched cycle, in the identical CAS write — not as a separate step
`implement.yml` performs after it starts. The resulting token is passed as
a new, optional `workflow_call` input on `implement.yml`,
`fold-queue-token` (default `''`). `implement.yml` gains a
`fold-turn-implement` prerequisite job that, when given a non-empty
token, awaits (never enqueues) that ticket; when the token is empty — a
manual `gh workflow run implement.yml` dispatch, or any caller predating
this feature — it no-ops immediately, preserving today's behavior exactly
(FR-019).

**Rationale**: If `implement.yml` enqueued its own ticket independently
after being dispatched, a brand-new round's `act` ticket could race it for
queue position in the gap between `dispatch-once` firing `gh workflow run`
and the dispatched run reaching its own enqueue step — reproducing a
version of the eviction-adjacent ordering bug one level up (spec.md's own
edge case: "the second run's legs must queue behind [an already-dispatched
cycle]... without the fold loop deadlocking against a long-running
implement job"). Writing the implement ticket in the same transaction that
verifies the round is empty guarantees it is inserted at the head before
any later round's ticket can exist.

## D6 — Deadlock avoidance: a bounded stale-ticket reclaim, never an unbounded wait

**Decision**: Every ticket's grant carries a `granted_at` timestamp. A
waiter that has been polling behind the current head ticket for longer
than `stale-after-minutes` (composite input, sized against
`inputs.confirm-timeout-minutes`-class budgets already in use elsewhere in
`pr-conversation.yml`) queries `gh api repos/.../actions/runs/<run_id>`
for the head ticket's owning run. If that run's own status shows it is no
longer active (completed in any conclusion, having never released its
ticket — only reachable if a non-ticketed entrant collided with a
ticket-holder's GitHub-group slot, or a runner/infra failure orphaned the
ticket), the waiter deterministically removes the stale head ticket from
the ledger (a CAS write, same idiom as every other ledger mutation) and
re-checks its own position. This is the FR-018 guarantee, and it is
expected to be a rare path — D1's design means ordinary ticketed
contention no longer produces an evicted, un-released ticket at all; this
reclaim exists for the residual case a non-ticketed dispatch (see D5's
manual-dispatch carve-out) or an infrastructure failure could still cause.

**Rationale for keeping this deterministic rather than agent-judged**:
Principle IX names exactly this shape of decision — "is a fingerprint /
dedup outcome / write valid" — as one that must never be delegated to a
model's inference. A stale-ticket reclaim gates a durable action (letting
someone else's job proceed) and must be computed the same way every time
from `gh api`'s own run-state fields, not phrased-and-hoped-for by a
prompt.

## D7 — The lost-cycle observer: a new, deliberately agent-free reactor, not a change to `stalled`

**Decision**: `implement.yml`'s `stalled` job's `!cancelled()` gate is
left unchanged — it cannot be made to fire for a job cancelled while
pending, because such a job runs zero steps regardless of any `if:`
rewrite (FR-014's own premise). Instead, a new published stage,
`fold-cycle-guard.yml` (`workflow_call`, no agent step at all), is wired
to the same `workflow_run: types: [completed]` trigger `watchdog.yml`
already has on the `implement` workflow
(`.github/workflows/wing-commander-8-watchdog.yml:58-70`), via its own
thin wrapper (`wing-commander-9b-fold-cycle-guard.yml`, naming pattern
matching the existing `wing-commander-8b-watchdog-self.yml` deterministic-
sibling precedent). On each completed `implement.yml` run, it:

1. Reads the run's own jobs via `gh api
   repos/.../actions/runs/<id>/jobs` (the same call `report-fold-outcomes`
   already makes) and determines "never started": the `implement` job (and
   `stalled`, if present) shows no `started_at`.
2. If conclusion is `cancelled` and the run never started, looks for a
   **positive, deterministic correlation**: another run or job sharing the
   same spec-dir's concurrency group that transitioned to `in_progress` at
   approximately the moment this run was cancelled (`gh api` timestamps,
   same read style as `wing-commander-board-stop-check`'s existing
   `status`-vocabulary handling). Correlation found → "replaced by a
   concurrency group" (FR-012's cause). No correlation found → treated as
   an unexplained pending-cancel and left silent, erring toward FR-013's
   existing default (today, a manual cancel is silent) rather than
   guessing a cause with no positive evidence.
3. On a replacement finding: posts the FR-012 notice (spec, iteration, the
   cancelled run's URL, cause) to the lifecycle issue, reusing
   `wing-commander-chain-stop-notice`'s posting shape; checks the round
   record's `redispatch_count` for this iteration (FR-016/FR-016a's
   at-most-once bound, a deterministic integer check, never inferred); if
   still `0`, re-dispatches via the same dispatch-and-claim path `D4`/`D5`
   describe (a fresh round is not started — the re-dispatch reuses the
   same iteration and increments `redispatch_count` to `1`) and names the
   new run next to the lost-cycle notice; if already `1`, reports the
   second loss and stops, naming a maintainer's re-drive as the remaining
   step (FR-016a).

**Rationale**: `watchdog.yml`'s existing `diagnose` step is explicitly an
LLM-tier judgment call over ambiguous multi-signal evidence (Constitution
II's carve-out for it) — the opposite of what this decision needs, which
is a small, fully deterministic classification with no ambiguity budget.
Keeping it out of `watchdog.yml` entirely (rather than adding it as a new
collector feeding `diagnose`) avoids spending an Opus-tier turn on a
decision code can already make outright, and avoids coupling this
feature's correctness to `watchdog.yml`'s own pause kill switch and
unrelated collector set. The `workflow_run`-on-`implement.yml` wiring is
reused rather than re-invented because it is already the one place in this
repository positioned to observe a cancelled run from outside itself
(FR-014).

## D8 — Gate design: Gate 70's load-the-real-expression-and-mutate recipe, applied to the new admission/claim/observer expressions

**Decision**: The new gate (`verify-fold-queue-admission.py`, this plan's
working name Gate 99) follows `verify-watchdog-self-skip-guard.py`'s shape
exactly: load the real `concurrency:`/`needs:`/`if:` expressions for
`fold-turn-act`, `act`, `fold-turn-dispatch`, `dispatch-once`,
`fold-turn-implement`, `implement`, and `fold-cycle-guard.yml`'s
replaced-vs-manual `if:` guard via `yaml.safe_load` + the shared
`find_job` helper (never a restated copy); evaluate them with the shared
`wc_gha_expr.py` interpreter against constructed two- and three-run
overlap contexts (mirroring Gate 70's cross-product-of-states approach);
and ship one `MUTATIONS` entry per defect this feature fixes — reverting
the admission job's `needs:` (reintroducing bare concurrency-group
contention), reverting the dispatch claim to an unconditional dispatch (no
round-emptiness check), and reverting the observer's correlation check to
"any cancelled+never-started run is reported" (collapsing the
manual/replaced distinction) — each proven to make the gate fail (FR-022).
No new `paths:` entry is needed in `lint-workflows.yml`: its existing
`.github/workflows/**`/`.github/actions/**`/`.github/scripts/**` globs
already cover every file this feature adds or edits (confirmed by reading
`lint-workflows.yml:19-58`).

## D9 — FR-020's single canonical comment

**Decision**: The one canonical statement of "why the fold/dispatch/
implement jobs are gated the way they are" moves to
`.github/actions/_shared/fold-queue-ledger.sh`'s header comment. Every
call site that today carries a pasted explanation
(`pr-conversation.yml`'s `act` at `:1517-1522`, `dispatch-once` at
`:2606-2613`, and `implement.yml`'s `implement` at `:360-362`) is replaced
with a one-line pointer (`-- see fold-queue-ledger.sh`), matching this
repository's existing pointer convention that Gate 47
(`verify-comment-canonical-pointers.py`) already enforces elsewhere.
