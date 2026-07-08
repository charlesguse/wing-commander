# Phase 0 Research: Cleanup Stage — Lifecycle Teardown on Final Merge or Draft Rejection

`spec.md`'s own checklist (`checklists/requirements.md`) confirms no
`[NEEDS CLARIFICATION]` markers remain — all three clarifications raised
against #28 were already answered before this plan ran (FR-012's stalled
vs. deleted choice, FR-013's ownership consolidation, FR-014's
issue-stays-open choice). What follows are the implementation-level
decisions `spec.md` and `docs/architecture.md`'s Stage 6 sketch
deliberately leave open, plus two findings this plan's own reading of the
current codebase surfaced that the spec text doesn't (and shouldn't) spell
out at the specification level.

## Finding: FR-013 requires retiring the `stalled` jobs already living in the plan and tasks stages

**Finding**: `speckit-3-plan.yml` has a `stalled` job that reacts to
`pull_request: closed` with `merged == false` and `head.ref` starting
`plan/` — it marks `spec-meta.json` stage `stalled` and comments a
restart runbook on the lifecycle issue. `speckit-4-tasks.yml` has the
identical shape for `tasks/*`. FR-013 says the cleanup stage "owns this
stalled-teardown behavior for these pull requests rather than leaving it
to the plan, tasks, and implementation stages." If both the old job and
this new stage's `mark-stalled` job are left listening on the same close
event, a single closed `plan/NNN-slug` PR fires **two** independent
"stalled" comments with slightly different wording, and two independent
(harmlessly idempotent, but redundant) `spec-meta.json` writes.

**Decision**: Retiring the two existing `stalled` jobs is in scope for
this feature's implementation, alongside the new `speckit-7-cleanup.yml`
jobs. There is no third job to retire for `impl/*` — see the next
finding.

**Rationale**: FR-013's wording is a direct instruction, not a
side-effect to infer; "rather than leaving it to the plan, tasks, and
implementation stages" only makes sense as "move it out of them."
Leaving both in place would violate FR-011's idempotency spirit (not the
literal per-workflow guarantee, but the user-facing "one clear stalled
record" outcome SC-007 promises) the moment both fire on the same event.

**Alternatives considered**: Leaving the old jobs in place and making the
new stage's `mark-stalled` job detect "was this already stalled by the
owning stage's own job" and no-op — rejected: it doesn't remove the
duplicate-comment risk (the old job's comment lands first, unconditionally,
before the new job could ever check anything), and it keeps two sources
of truth for the same behavior, exactly what FR-013 is written to prevent.

## Finding: FR-013's `impl/*` arm is presently unreachable — the implemented Stage 4 never opens an implementation PR

**Finding**: `docs/architecture.md`'s Stage 4 design and the constitution's
branch-convention list both name `impl/<NNN-slug>-iterN` as a pipeline
branch, and the cleanup stub's head-ref guard already includes an `impl/`
prefix. But the actual implementation
(`specs/005-implement-converge/`, `speckit-5-implement.yml`) commits
directly to `spec/NNN-slug` — no `impl/*` branch or pull request is ever
created. `spec.md`'s FR-002 ("implementation branches") and FR-013
("an implementation-stage pull request") describe a shape the system
does not currently produce.

**Decision**: Implement the `impl/*` handling anyway — matching head-ref
prefix, branch deletion attempt, stalled-comment eligibility — exactly as
specified, but treat it as defensive/inert code, not a path this stage's
`quickstart.md` can exercise against a real run today. If Stage 4 later
grows an `impl/*` PR (a documented but unbuilt possibility), this stage
already handles it with no further change.

**Rationale**: `spec.md` is written against the pipeline's documented
branch conventions, not against Stage 4's specific implementation choice;
narrowing this stage's scope to match today's implementation accident
would silently drop coverage the moment Stage 4 changes. The cost of
keeping the `impl/*` arm is zero — it's the same generic prefix-match
code path as `plan/*`/`tasks/*`, just never exercised in practice today.

**Alternatives considered**: Dropping `impl/*` handling entirely as
dead code — rejected as it would need re-adding (and re-verifying) the
moment Stage 4's design changes, for a saving of a few lines of generic,
already-shared logic.

## Decision: Outcome is disambiguated from the event payload alone, never by a follow-up `gh` query

**Decision**: Three independently-gated jobs, each computing its own
narrow `if:` from `github.event.pull_request.{head.ref, base.ref, merged}`:

| Job | `head.ref` | `base.ref` | `merged` |
|---|---|---|---|
| `teardown-done` | starts `spec/` | `main` | `true` |
| `teardown-rejected` | starts `spec-draft/` | `main` | `false` |
| `mark-stalled` | starts `spec/` **or** `plan/` **or** `tasks/` **or** `impl/` | `main` (for `spec/`) or not `main` (for the other three — see below) | `false` |

A closed `spec-draft/*` PR that **merged** matches none of these three —
that event is the plan stage's own trigger (`speckit-3-plan.yml`), and
this stage correctly no-ops on it (User Story 3 Scenario 1). A closed
`plan/*`/`tasks/*`/`impl/*` PR that **merged** also matches none of these
three — that's the owning stage's own trigger reacting to its normal
advance (FR-013 acceptance scenario 4), and this stage again no-ops.

**Rationale**: FR-009 requires identifying the specification "from the
pull request itself rather than guessing," and the payload already
carries every fact needed (head, base, merged) with no extra API call —
computing the same three-way split from a `gh pr view` after the fact
would be strictly more expensive for no additional certainty, since the
event payload's `merged`/`base.ref` fields are exactly what GitHub itself
used to decide the event fired in the first place.

**Alternatives considered**: One job with an internal branch on outcome
(mirroring how `speckit-6-finalize.yml` is a single job) — rejected:
unlike finalize (one `workflow_dispatch` shape, several possible
early-exits), this stage has three *fundamentally different* GitHub-write
sequences (delete-and-close vs. delete-and-comment vs.
preserve-and-relabel) reacting to genuinely different event shapes; three
small, independently-readable jobs (each mirroring the existing
plan/tasks stages' own two-job "main path / stalled path" split) is more
consistent with this repo's established pattern than one job with three
internal exit branches.

## Decision: The `mark-stalled` job's base-ref check for non-final PRs is "not `main`," not "equals `spec/<slug>`"

**Decision**: For the `plan/`/`tasks/`/`impl/` arm of `mark-stalled`, the
job-level `if:` only checks `base.ref != 'main'` (cheap, coarse); the
first deterministic step inside the job then derives the expected base
(`spec/<slug>`, where `<slug>` comes from stripping the head prefix) and
**verifies** `github.event.pull_request.base.ref` equals it exactly,
declining (FR-009/FR-010) if it doesn't.

**Rationale**: GitHub Actions `if:` expressions can't cheaply compute
"strip this prefix and compare" against another dynamic field, so the
coarse job-level gate (existence of a recognized prefix + not targeting
`main`) is the practical boundary of what conditions can express, and
the precise check belongs in a step that has `slug` computed — identical
in shape to how `speckit-6-finalize.yml`'s "Resolve and validate spec
identity" step does its own regex refusal after a coarser job-level gate.
A `plan/007-x` PR opened against `main` directly (not `spec/007-x`) is
exactly the "head branch matches a pipeline naming convention but the PR
is not actually an owned pipeline PR" edge case `spec.md` calls out —
caught by this base check before any write happens, and reported the same
way finalize's refusal step reports a bad hand-off: a PR comment (always
resolvable, since the PR number is always known) plus `::error::` and a
step-summary line.

**Alternatives considered**: Trusting the job-level `if:` alone (any
`plan/*` PR closed unmerged, regardless of base) — rejected: it would
treat an accidental `plan/foo → main` PR (e.g. a stray branch coincidentally
prefixed `plan/`) as an owned pipeline PR, exactly the failure mode
FR-010's edge case exists to prevent.

## Decision: Identity resolution checks out whichever branch the event guarantees still exists

**Decision**: For `teardown-done` and `mark-stalled`'s `spec/*` arm,
check out `spec/NNN-slug` (the PR's own head — guaranteed to still exist
at the moment the job runs, since deletion, if any, is this job's own
later step). For `teardown-rejected`, check out `spec-draft/NNN-slug`
(same reasoning). For `mark-stalled`'s non-final arm, check out
`spec/NNN-slug` (the PR's **base** — the branch the plan/tasks/impl work
was targeting, which is what still carries the authoritative
`spec-meta.json` to both validate against and, per the storage decision
above, write `stage: "stalled"` onto).

**Rationale**: Every other stage's refusal check reads `spec-meta.json`
off whichever ref is authoritative for that stage's moment in the
pipeline (e.g. finalize reads it off `spec/NNN-slug`, plan reads it off
`main` before the persistent branch exists yet); this stage's version of
that same pattern is "read it off whichever ref this specific outcome's
event guarantees is still present," which is never `main` (main only has
`spec-meta.json` as of the *last* stage's commit, one stage behind
whichever branch is closing right now, except for the `teardown-done`
case where main *does* just get it via the merge — but the branch is
simpler and identical content immediately post-merge, so there's no
reason to special-case it).

**Alternatives considered**: Always reading off `main` — rejected for the
draft-rejection and stalled paths, where `main` has never seen this
specification's in-flight artifacts at all (draft) or is a stage behind
(stalled plan/tasks work) — `main` simply doesn't have the file to read
yet in those cases.

## Decision: The refusal/identity check reports failures the same way `speckit-3-plan.yml`'s `stalled` job does — a PR comment, not an issue comment

**Decision**: When identity/artifact validation fails (missing
`spec.md`/`spec-meta.json`, slug regex mismatch, base-ref mismatch,
`spec-meta.json`'s own `issue`/`spec_dir` disagreeing with what the
branch name implies), the job reports via `::error::`, a
`$GITHUB_STEP_SUMMARY` line, and `gh pr comment $PR_NUMBER` — never a
lifecycle-issue comment (FR-009: the whole point of this check is that
the issue can't yet be trusted to be the right one, or at all).

**Rationale**: The pull request number is always known directly from the
event payload regardless of how identity resolution fails, making it the
one reliably-addressable surface to report to; this exactly mirrors
`speckit-3-plan.yml`'s "Verify spec artifacts and resolve lifecycle
issue" step's existing precedent (`gh pr comment "$PR_NUMBER" --body
"⚠️ $msg ..."`), so this stage introduces no new refusal-reporting shape.

**Alternatives considered**: Reporting only via `::error::`/step summary
(no PR comment) — rejected as strictly less discoverable to the human who
just closed the PR, for no simplification benefit; the existing precedent
already establishes the PR-comment fallback as this repo's answer to "we
can't trust the issue yet."

## Decision: Idempotency signal is "does the target state already hold," per outcome, not a durable marker

**Decision**: No new "already processed this event" marker is introduced.
Each outcome's own target state doubles as its idempotency check,
evaluated right before that outcome's writes:

- `teardown-done`: if the lifecycle issue is already `state: CLOSED`,
  skip the summary generation, the close-with-comment, and the label
  flip entirely (branch deletion still runs — deleting an
  already-deleted branch is itself a no-op, see below — since a prior
  run could plausibly have closed the issue but died before finishing
  branch cleanup).
- `teardown-rejected`: if the `spec:NNN-slug` identity label is already
  absent from the issue, skip the label removals and the rejection
  comment (branch deletion still attempted, same reasoning).
- `mark-stalled`: if the issue's current stage label already reads
  `stage:stalled`, skip the label flip and the stalled comment (the
  `spec-meta.json` write is naturally idempotent — writing
  `stage: "stalled"` again when it already reads that is a no-op commit,
  guarded the same way `speckit-3-plan.yml`'s existing `stalled` job
  already guards it: `git diff --cached --quiet` before committing).
- **Every** branch deletion (`git push origin --delete <branch>`, or the
  equivalent `gh api` call) treats a "not found"/422-class failure as
  success, never as an error — this is the one idempotency rule shared
  by all three outcomes (FR-011's "branch already absent" edge case).

**Rationale**: A durable "already ran" marker would be a second source of
truth that could itself desync from the real GitHub state (the exact
failure mode `speckit-6-finalize.yml`'s research.md rejected a
`spec-meta.json`-keyed guard for, in favor of checking the PR's own
existence). Checking the actual target state directly is simpler, has no
extra storage, and is exactly what FR-011's edge cases describe ("an
issue already closed," "a branch already absent") — these are phrased as
states to detect, not events to deduplicate.

**Alternatives considered**: A sentinel issue comment (e.g. "cleanup
already ran") checked via `gh issue view --json comments` before acting —
rejected as an extra API call and an extra thing that could itself be
duplicated by a race, for no benefit over checking the actual label/state
this stage is trying to reach.

## Decision: Completion summary reuses the merge commit, not a live checkout of the (about to be deleted) spec branch

**Decision**: The one agent step (merged path only) derives its
`git log`/`git diff` range from `github.event.pull_request.merge_commit_sha`
against its first parent (`git diff ${sha}^1..${sha}` on a checkout of
`main`, which already contains that commit) — not from a checkout of
`spec/NNN-slug` itself.

**Rationale**: Ordering branch deletion relative to summary generation
would otherwise matter (deleting `spec/NNN-slug` before the agent reads it
would break the summary step); reading the merge commit off `main`
instead makes the two independent — branch deletion and summary
generation can happen in either order, or even fail/retry independently,
without one blocking the other. `main` is guaranteed to have the merge
commit the instant the trigger fires (that's what "merged" means).

**Alternatives considered**: Checking out `spec/NNN-slug` and diffing
against `main`'s pre-merge tip (`git diff main...HEAD` from before the
merge) — rejected: requires computing "main before this merge," an extra
git step, for output identical to just diffing the merge commit's own two
parents on the ref that's already checked out.

## Decision: `spec-meta.json` is never written on `main`; the file's last pre-merge content is the permanent historical record

**Decision**: The `teardown-done` and `teardown-rejected` paths make no
commit to `main` (or anywhere) to update `stage` to `"done"` or otherwise
annotate the now-deleted branch's last metadata state.

**Rationale**: No stage in this pipeline commits directly to `main` — every
prior stage pushes to its own branch and a human merges it; introducing a
direct-to-`main` commit here (the one thing left standing after every
branch is gone) would be a first, and would need its own PR-and-merge
cycle to stay consistent with constitution V ("humans merge every PR into
main"), which is exactly the overhead this terminal stage should not add
for a durable record the issue and the merged PR already carry (SC-002 —
a maintainer already gets the full completion story from the issue alone,
without needing `spec-meta.json` to say so too).

**Alternatives considered**: Opening one more tiny PR (`stage: "done"` on
`main`) purely to keep `spec-meta.json` current — rejected as
disproportionate process (a full PR-and-merge cycle) for a field nothing
downstream ever reads again once a specification is torn down.

## Decision: The stalled comment's "optional full teardown" instructions are a manual runbook, not a new automated dispatch mode

**Decision**: FR-015's "link and instructions" are a literal git/`gh`
command runbook in the comment body (delete the specification's remaining
branches, remove its `spec:*`/`stage:*` labels) — the same shape
`speckit-3-plan.yml`'s existing stalled comment already uses for its own
restart runbook — rather than a new `workflow_dispatch` "force teardown"
input on `speckit-7-cleanup.yml`.

**Rationale**: `spec.md` requires that a human *can* trigger full
teardown, not that this stage must provide one more automated trigger to
do it — a copy-pasteable command block is sufficient, matches an existing
in-repo precedent exactly, and avoids adding a second, differently-shaped
"teardown" code path (dispatch-triggered) alongside the event-triggered
one this feature already implements, for the same eventual effect a human
running four `git push --delete`/`gh label` commands already achieves
today for every already-implemented stalled path.

**Alternatives considered**: A `workflow_dispatch` input (`spec_dir`,
`mode: teardown`) that re-runs this stage's own `teardown-done`-style
branch deletion (but not the issue-close) on demand — a reasonable future
enhancement, rejected here as unnecessary process for what FR-015
literally asks for, and deferrable without cost since nothing else in
this design depends on it existing.

## Decision: Branch deletion set includes `tasks/NNN-slug`, though `spec.md`'s Key Entities section does not name it

**Decision**: The `teardown-done` path's branch-deletion list is:
`spec-draft/NNN-slug`, `spec/NNN-slug`, `plan/NNN-slug`, `tasks/NNN-slug`,
and any `impl/NNN-slug-iter*` branches (glob via
`git ls-remote --heads origin "impl/NNN-slug-iter*"`) — five branch
shapes, not the four `spec.md`'s Key Entities section lists ("its draft
branch, its persistent working branch, its plan branch, and its
implementation branches").

**Rationale**: `tasks/NNN-slug` is a real pipeline branch — Stage 3 opens
it whenever `vars.SPECKIT_TASKS_REVIEW=pr` (`docs/architecture.md` §Stage
3, `speckit-4-tasks.yml`) — and `spec.md`'s omission reads as an oversight
carried over from the constitution's own branch-convention list (which
also doesn't name `tasks/<slug>`), not a deliberate exclusion; leaving it
undeleted would contradict SC-004's "the repository retains no pipeline
branches ... for any specification that has been merged" the moment a
specification went through PR-mode task review. This is a decision made
without an explicit clarification request, called out in the plan PR per
the pipeline's own convention for undocumented judgment calls.

**Alternatives considered**: Deleting only the four branches `spec.md`
names verbatim — rejected as it would leave `tasks/NNN-slug` behind for
every specification reviewed in `pr` mode, directly contradicting SC-004.
