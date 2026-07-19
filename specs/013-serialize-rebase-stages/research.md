# Phase 0 Research: Serialize Rebase and Stages Per Specification

`spec.md` carries no `[NEEDS CLARIFICATION]` markers — Question 1 (scope of
the mutual exclusion) was answered on lifecycle issue #53 (Option B, full
per-specification serialization) before this planning session began, and is
already encoded in FR-001/FR-008 and `checklists/requirements.md`'s Notes.
This document resolves the remaining *technical* unknowns needed to turn the
spec into a plan: how the existing five stage workflows, each declaring its
own disjoint per-spec `concurrency:` group, are brought under one shared
ordering per specification without over-serializing or losing the
branch-currency guarantee.

## D1 — The root cause, precisely

**Decision**: Confirmed by reading every published stage's job-level
`concurrency:` block as it stands on `main` today:

| Workflow | Job | Current group |
|---|---|---|
| `rebase.yml` | `rebase` (matrix) | `wing-commander-rebase-${{ matrix.slug }}` |
| `plan.yml` | `plan` | `wing-commander-plan-${{ inputs.slug \|\| inputs.head-ref }}` |
| `tasks.yml` | `tasks` | `wing-commander-tasks-${{ inputs.slug \|\| inputs.head-ref }}` |
| `tasks.yml` | `tasks-approved` | `wing-commander-tasks-${{ inputs.slug \|\| inputs.head-ref }}` |
| `implement.yml` | `implement`, dispatch-next job | `wing-commander-${{ inputs.spec-dir }}` |
| `finalize.yml` | `finalize` | `wing-commander-${{ inputs.spec-dir }}` |

Five distinct group *prefixes* (`rebase-`, `plan-`, `tasks-`, and the
unprefixed pair already shared by implement/finalize) mean GitHub Actions
treats a rebase and a plan/tasks run for the same spec as entirely unrelated
job queues — nothing stops them running at the same instant. This is the gap
FR-001/FR-003/FR-008 close: not a locking bug, a *naming* one. Notably,
`specs/010-reusable-pipeline/contracts/stage-interfaces.md` already asserts
"Per-spec serialization (`concurrency: speckit-<slug>`) is declared at job
level... and therefore applies in the consuming repository" as if one shared
convention already existed — it doesn't, in practice, across stage
*families*, only within a single stage's own re-dispatch chain
(implement→implement, implement→finalize). Bringing the code in line with
that already-documented intent is this feature's job; the contract text
itself gets a follow-up correction once the group string is finalized below
(tracked as a task, not a planning-time edit, since this plan may only touch
`specs/013-serialize-rebase-stages/`).

**Rationale**: Establishes that the fix is confined to six `concurrency:`
blocks across five files — no new locking primitive, workflow, or state file
is needed. Matches the spec's Assumptions ("this change... only orders
existing operations so they do not collide on the same branch").

**Alternatives considered**: A new dedicated "spec lock" reusable workflow
job that every stage calls before doing real work — rejected as unnecessary
machinery; GitHub Actions' own concurrency-group primitive already gives
mutual exclusion, FIFO-ish queuing, and cross-workflow scope for free once
the group *string* matches, which is exactly the mechanism every existing
stage already uses for its own internal serialization.

## D2 — The canonical group key

**Decision**: Adopt `wing-commander-${{ <spec-dir> }}` (where `<spec-dir>`
is `specs/NNN-slug`, e.g. `wing-commander-specs/013-serialize-rebase-stages`)
as the one concurrency group every slug-bearing operation for a
specification shares. This is **not a new format** — it is `implement.yml`
and `finalize.yml`'s existing group, verbatim, unchanged. Every other stage
converges onto it:

- `rebase.yml`: the `rebase` matrix job already carries `matrix.spec_dir`
  (`discover` already emits `{slug, spec_dir, issue}` triples — `spec_dir`
  is unused today except for the branch-identity check). Change the group
  from `wing-commander-rebase-${{ matrix.slug }}` to
  `wing-commander-${{ matrix.spec_dir }}`. One-line change, no new job.
- `plan.yml` / `tasks.yml`: these jobs only receive `head-ref` (prefixed —
  `spec-draft/NNN-slug`, `plan/NNN-slug`, or `tasks/NNN-slug` depending on
  trigger) or a bare `slug`, and today derive the canonical slug in a
  same-job step (`Resolve spec identity`) that runs *after* the job's
  `concurrency:` block has already been evaluated — GitHub Actions computes
  a job's `concurrency.group` expression before any step of that job runs,
  from `inputs`/`needs`/`vars`/`github` context only, so a same-job step
  output can never feed it. See D3.

**Rationale**: Reusing implement/finalize's existing string is the smallest
possible change (two of five files need none at all) and is already proven
in production to work as a GitHub Actions concurrency group value (the
literal `/` in `specs/NNN-slug` is not a restricted character). Every job
that shares this string — regardless of which of the five workflow files
declares it — is scoped to the same repository-wide concurrency domain,
which is documented GitHub Actions behavior: concurrency groups are not
workflow-scoped, only string-scoped.

**Alternatives considered**: Inventing a fresh, shorter group name
(`wing-commander-spec-<slug>`) for all five — rejected, it would still
require touching implement.yml and finalize.yml (currently correct) purely
for cosmetic consistency, expanding the diff for no behavioral gain.

## D3 — Resolving a canonical slug before job start (plan.yml, tasks.yml)

**Decision**: Add one small preliminary job to `plan.yml` (`resolve-spec`)
and one to `tasks.yml` (`resolve-spec`, shared by both `tasks` and
`tasks-approved` since only one of the two ever runs per call, gated on the
same `inputs.mode` the two downstream jobs already gate on). Each:

- Takes the same inputs the downstream job already uses (`inputs.slug`,
  `inputs.head-ref`, and — for `tasks.yml` — `inputs.mode` to pick which
  prefix (`plan/` vs `tasks/`) to strip).
- Runs the *exact* validation/derivation logic that already exists today as
  the `Resolve spec identity` step inside `plan`/`tasks`/`tasks-approved`
  (strip the known prefix, validate `^[0-9]{3}-[a-z0-9][a-z0-9-]*$`, fail
  loudly with `::error::` on anything else) — moved, not duplicated: the
  downstream job's own `Resolve spec identity` step is deleted and replaced
  with a reference to `needs.resolve-spec.outputs.spec-dir` /
  `needs.resolve-spec.outputs.slug`.
- Declares `permissions: {}` and no checkout — it is pure string handling
  over `inputs`, so it needs no repository access at all (least-privilege,
  constitution V).
- Exposes `slug` and `spec-dir` as job outputs.

The downstream job (`plan`, `tasks`, `tasks-approved`) adds
`needs: resolve-spec` and its `concurrency.group` becomes
`wing-commander-${{ needs.resolve-spec.outputs.spec-dir }}`.

**Rationale**: A job's `concurrency:` block is evaluated at job-start, before
its own steps run, so the only way to key it off a value that must be
*derived* from a raw trigger payload (a prefixed `head-ref`) is to derive
that value in a job this one `needs:`. This is not a novel shape for this
codebase: `wing-commander-5-implement.yml` already has exactly this
pattern (`resolve-model`, a tiny prerequisite job feeding
`needs.resolve-model.outputs.model` into the dispatch), just one layer up
(wrapper, not reusable workflow). Moving (not copying) the existing
derivation step also deletes duplicate slug-validation logic from the
downstream job — a small simplification alongside the fix, not scope creep,
since the downstream job needs the same value the new job just computed and
has no reason to recompute it.

**Alternatives considered**: Keeping slug derivation inside the downstream
job and accepting a *coarser* concurrency group for `plan`/`tasks` (e.g.
literal `inputs.head-ref`, prefix and all) — rejected: it cannot converge
with `rebase`/`implement`/`finalize`'s group for the same spec (FR-008
requires the *same* spec to land on one shared ordering regardless of which
operation it is), and it doesn't even self-consistently group two different
triggers of the *same* stage for the same spec (`slug=013-foo` vs
`head-ref=spec-draft/013-foo` already produce two different group strings
today, a latent bug this design also happens to close). Re-deriving the
slug twice (once in a resolve job for grouping, once again unchanged in the
downstream job for real use) — rejected as needless duplication once the
value already exists as a job output.

## D4 — Cross-stage queuing satisfies FR-004 (currency) without new plumbing

**Decision**: Rely entirely on GitHub Actions' native concurrency-group
semantics — `cancel-in-progress: false` on every group member (already true
of all six blocks in D1's table, unchanged by this feature) — rather than
building any bespoke "deferred rebase" retry mechanism.

**Rationale**: With `cancel-in-progress: false`, a job requesting an
already-held group is queued, not dropped, and runs (from a fresh checkout,
against the then-current branch tip and default-branch tip) once the
holder finishes — this is exactly User Story 1/2's required behavior and
satisfies FR-004 ("brings the branch current... when the branch is freed")
for the common case of one contender queued behind one holder. Spec.md's
own Assumptions explicitly anticipate and accept the residual case: GitHub
Actions keeps only one *pending* run per concurrency group — if a second
and third request for the same group arrive while one is already queued
behind an in-progress holder, only the most recently queued one survives
to run next; earlier queued ones are superseded (not "lost" in a data
sense, since neither one has touched the branch yet — nothing to lose —
but that specific triggering *event* does not get its own run). This is
acceptable because FR-004 requires currency "at the next opportunity — when
the branch is freed, on a subsequent main-line advance, or on the recurring
nightly rebase" (already phrased as a disjunction, not "this exact
trigger"): a superseded rebase request is superseded by a newer one that
rebases onto the same or newer `main`, and if instead a stage request
supersedes a queued rebase, the next main-line push or the nightly
`cron` schedule (`rebase.yml`'s existing trigger, unchanged) queues a fresh
rebase attempt behind whatever is running then. No specification's branch
can go permanently un-rebased by this mechanism — only individual redundant
attempts are coalesced, which is a feature (fewer wasted runs), not a
regression.

**Alternatives considered**: A custom "rebase debt" flag (e.g. a label or a
`spec-meta.json` field marking "a rebase was deferred, retry me") consumed
by the next stage completion — rejected: it duplicates what the nightly
`schedule` trigger and every subsequent `push` to the default branch already
guarantee (another rebase attempt will be discovered and queued), adds a new
persisted-state surface this spec's Assumptions explicitly say is
unnecessary ("no new such concepts"), and — per spec 008's own D6 precedent
— this codebase already prefers relying on the next natural trigger over
inventing retry bookkeeping.

## D5 — Scope boundary: cleanup is not joined to the group

**Decision**: `cleanup.yml` keeps its existing, separate
`wing-commander-cleanup-${{ inputs.head-ref }}` group, unchanged. It is not
added to the unified `wing-commander-${{ spec-dir }}` group this feature
creates.

**Rationale**: FR-008 scopes the unified ordering to "the auto-rebase and
every stage run," and spec.md's Key Entities define "Stage run" by example
as plan/tasks/implement/finalize — cleanup runs strictly *after* finalize's
PR has already merged (spec-meta.json is already at its terminal stage) and
its only interaction with the specification's working branch is deleting it
outright, not mutating and publishing it. The one theoretical race —
`discover` selecting a `spec/NNN-slug` branch a moment before cleanup
deletes it on the very same default-branch push — already exists today,
is unrelated to the force-push-collision this spec fixes (a deleted branch
fails a rebase's checkout/push loudly and harmlessly, it does not silently
force-push over in-flight work), and is explicitly out of this spec's
Assumptions ("this change introduces no new such concepts"). Joining
cleanup to the group would also risk a real regression: cleanup's teardown
path runs on every PR-closed event, including ones for `plan/`, `tasks/`,
and `impl/`-prefixed branches that are *not* `spec/NNN-slug` at all — mixing
those into the same per-spec-branch group would over-serialize unrelated
short-lived branch cleanups against a spec's rebase/stage ordering for no
requirement in scope.

**Alternatives considered**: Extending FR-008's group to cleanup "for
consistency" — rejected as unrequested scope expansion with a plausible new
failure mode (above) and no scenario in spec.md's User Stories or Edge
Cases naming cleanup as a contender.

## D6 — Verification approach

**Decision**: Same as every prior CI-workflow-only stage in this repo (008,
010) — no automated test suite exists for GitHub Actions workflow bodies
here; `quickstart.md`'s scenarios are run by hand against scratch
specifications, deliberately timed so a rebase and a stage collide, and the
resulting run/job list in the Actions UI is inspected for queuing instead of
concurrent execution.

**Rationale**: Consistent with every previous stage; no new verification
infrastructure is introduced by this feature.

**Alternatives considered**: A dedicated harness that fires synthetic
`workflow_dispatch` events at controlled offsets and polls the Actions API
for overlap — rejected as disproportionate machinery for a naming/wiring fix
with only six call sites; manual quickstart validation is what every
concurrency-group change in this repo has used to date (008's `rebase`
matrix concurrency, 010's cross-stage groups).
