# Phase 0 Research: End-to-End Verification Tier That Actually Verifies

> **Amended after PR #187's CI run — scratch-repository provisioning was removed.**
> Everywhere below that describes this feature *creating* or *deleting* a
> scratch repository (`gh repo create`/`delete`/`list`, the per-run
> `wing-commander-e2e-<issue>` repository, the `issues: {types: [closed]}`
> trigger, the `issue-closed` job, and the `reap-scratch-repos` sweep) is
> **superseded**. A GitHub App installation token cannot create a repository
> on a user account, and the `Administration: write` needed to delete one is
> installation-wide — the same token could delete this repository from any
> agent step. The shipped design uses **one pre-created scratch repository**
> (`WING_COMMANDER_AUTO_UPDATE_SPEC_KIT_E2E_SCRATCH_REPO`) with a per-run
> branch `auto-update-spec-kit/e2e-<issue>` force-reset before every scaffold.
> See spec.md's Assumptions, `contracts/e2e-verification-tier.md`'s
> "Scratch-repository lifecycle" section, and tasks.md Phase 9. Everything
> else in this document still holds.

`spec.md` carries no `[NEEDS CLARIFICATION]` markers — every drafting
ambiguity (the carried-over #157 open question, the two Q1/Q2 drafting
clarifications, and the AI-driven-stage location follow-up) was already
answered in the issue conversation before this spec was accepted
(`checklists/requirements.md`'s Notes section). What follows are the
implementation-shape decisions this plan makes to turn the spec's functional
requirements into something `tasks.md` can build against. Decisions not
dictated by the spec text are marked "(made without clarification)" and are
repeated in the transmittal comment on issue #184, per this pipeline's own
convention (precedent: `specs/027-auto-update-spec-kit/research.md`,
`specs/015-pipeline-watchdog/research.md`).

## Decision: the per-script chain reuses the lightweight tier's own scratch feature, in the same worktree

**Decision**: The end-to-end tier's script coverage does not create a second
scratch feature or a second worktree. It runs, in order, inside the
*same* isolated worktree and the *same* `$FEATURE_DIR` the lightweight
tier's `create-new-feature.sh` + `check-prerequisites.sh --paths-only` steps
already produced:

1. Assert `$FEATURE_DIR/spec.md` exists and is non-empty (new — lightweight
   only checks `create-new-feature.sh`'s JSON fields `BRANCH_NAME`/
   `SPEC_FILE`, never the file's actual content).
2. `SPECIFY_FEATURE_DIRECTORY="$FEATURE_DIR" bash .specify/scripts/bash/setup-plan.sh --json`
   — assert `FEATURE_SPEC`/`IMPL_PLAN`/`SPECS_DIR`/`BRANCH` are all present
   and non-empty, and that `$FEATURE_DIR/plan.md` (the `IMPL_PLAN` path) is
   non-empty on disk.
3. `SPECIFY_FEATURE_DIRECTORY="$FEATURE_DIR" bash .specify/scripts/bash/setup-tasks.sh --json`
   — assert `FEATURE_DIR`/`AVAILABLE_DOCS`/`TASKS_TEMPLATE` are present (an
   empty `AVAILABLE_DOCS` array is valid — this scratch feature never gains
   `research.md`/`data-model.md`/`quickstart.md`/`contracts/`; the field
   merely needs to *exist* in the documented shape) and `TASKS_TEMPLATE`
   resolves to a real, non-empty file path.

`SPECIFY_FEATURE_DIRECTORY` is the exact environment variable this
repository's own `plan.yml`/`tasks.yml` stages already set before invoking
these same two scripts (see e.g. this very plan run's own `plan.yml:539`) —
reusing it here means the deeper tier calls these scripts the *same way*
the pipeline's real stages do, not a bespoke invocation this plan would need
to separately justify.

**Rationale**: FR-002 requires covering "every Spec Kit script the pipeline
depends on," which — per the exploration behind this plan — is exactly four
CLI scripts (`create-new-feature.sh`, `check-prerequisites.sh`,
`setup-plan.sh`, `setup-tasks.sh`; `common.sh` is a library, exercised
transitively by all four, not a fifth entry point). Two are already
exercised by the lightweight tier; this feature's job is to add the other
two and to close the one gap in the two that already run (spec.md's content
was never actually checked). A second scratch feature/worktree would
duplicate `create-new-feature.sh`'s own work for no additional coverage —
`setup-plan.sh`/`setup-tasks.sh` need an *existing* feature directory to
operate on, which the lightweight tier's run already produced in the same
job.

**Alternatives considered**: A dedicated second worktree per script —
rejected: pure duplication, no isolation benefit (nothing here is
destructive to the worktree), and it would need to re-run
`create-new-feature.sh` and `check-prerequisites.sh` a second time just to
reach the same starting state. Running `setup-tasks.sh` without first
guaranteeing `plan.md` exists — rejected: `setup-tasks.sh` hard-errors
("Run /speckit-plan first") if `plan.md` is absent, by design (it has no
silent fallback of its own, unlike the other three scripts) — running it
out of order would make the deeper tier fail on an ordering bug indistinguishable
from a real candidate defect.

## Decision: FR-004's "no fallback" is satisfied by non-empty checks alone — no separate template pre-flight

**Decision**: The tier does **not** independently probe
`$WORKTREE/.specify/templates/{spec,plan,tasks}-template.md` for existence
before running the scripts that consume them. It relies entirely on the
non-empty on-disk assertions in the decision above (`spec.md`, `plan.md`)
plus `setup-tasks.sh`'s own hard failure when `tasks-template.md` cannot be
resolved (no `--paths-only`-style skip for that one — it already errors
loudly, per the script excerpt below).

**Why this is sufficient, not a gap**: `create-new-feature.sh` and
`setup-plan.sh` (upstream Spec Kit's own scripts, not this tier's code) both
degrade to `touch $TARGET` — a zero-byte file — when their own template
resolution fails; neither ever writes a non-empty substitute. `touch`'s
output is indistinguishable from "the script crashed before writing
anything" for the purposes of a non-empty check, which is exactly the
signal FR-004 needs: an absent expected artifact still results in the tier
failing, with no locally-manufactured content ever treated as a pass.
`setup-tasks.sh` has no equivalent silent path at all — it exits non-zero
directly, which the tier's existing "script exited non-zero" handling
(identical shape to the lightweight tier's own checks) already fails on.

**Rationale**: This is strictly less code than a separate pre-flight probe
would be, and pre-checking a file the *candidate's own script* is about to
check anyway would duplicate logic that upstream already implements
correctly (its failure mode was never "silently pass," only "silently
degrade to empty" — the bug FR-004 targets was entirely in this tier's own
`else` branch, at auto-update-spec-kit.yml lines 1311-1315, fabricating a
*non-empty* substitute that made the non-empty check meaningless. Removing
that branch, without adding anything else, is what actually fixes FR-004).

**Alternatives considered**: An explicit `[ -f "$template" ] || fail` probe
for each of the three templates before invoking the corresponding script —
rejected as redundant given the above, and because it would need its own
justification for *which* templates count as "expected" beyond what the
scripts themselves already require, reopening exactly the scope question
FR-002's own text already resolved ("coverage is defined by what the
pipeline consumes").

## Decision: the AI-driven stage is a new `e2e-stage` job, self-contained, not a call into `intake.yml`

**Decision**: FR-017/018's "real AI-driven pipeline stage... e.g. a
specify run" is implemented as a new job (`e2e-stage`) inside
`auto-update-spec-kit.yml` — a bespoke `claude-code-action@v1` step plus a
deterministic read-back step, following the exact shape `evaluate-path`'s
`decide` / `decide-outcome` step pair already establishes in this same
file — rather than a `uses:` call into the published `intake.yml` stage.

**Rationale**: `intake.yml` is hardwired to `$GITHUB_REPOSITORY` (its
checkout, its `gh api repos/${GITHUB_REPOSITORY}/issues/...` calls) and
carries lifecycle-issue machinery (labels, `spec-meta.json`, draft-PR
review) this feature has no use for and does not want to invoke against a
scratch repository — doing so would mean either teaching `intake.yml` to be
repository-parametric (a published-contract change with adopter-facing
consequences, per constitution VII, for a need only this one internal
feature has) or accepting a pile of no-op side effects. A small, disposable,
inline step matches this same workflow file's own established precedent
(the end-to-end tier itself, and the lightweight tier before it, are both
inline rather than factored into a composite) and constitution VII's
guidance that a stage-specific deviation belongs with the thing that needs
it, not bolted onto a published contract.

**Shape** (exact flags deferred to `tasks.md`, per specs/027/research.md's
own "Open items intentionally deferred beyond this plan" precedent):

1. A step creates (or reuses, idempotently) the scratch repository (see
   next decision) and clones it locally.
2. A step runs the same `uvx --from git+https://github.com/github/spec-kit.git@v${CANDIDATE} specify init . --ai claude --script sh --ai-skills --here --force`
   command `prepare` already runs (research.md's own flagged assumption,
   unchanged), this time inside the scratch repository's clone, then commits
   and pushes that scaffold — so the scratch repository reflects "candidate
   scaffolded and ready" even if the next step never completes, satisfying
   FR-022's "a maintainer... can inspect it" regardless of outcome.
3. `claude-code-action@v1`, `continue-on-error: true`, a bounded
   `timeout-minutes`, `--model` from a new `e2e-stage-model` input
   (default `claude-sonnet-5`, see the model-tiering decision below),
   `--max-turns` from a new `e2e-stage-max-turns` input (default `20`,
   flagged as an estimate needing maintainer confirmation before the first
   real minor/major run, matching how `prepare`'s own `specify init`
   command is already flagged), least-privilege `--allowedTools` scoped to
   the candidate's own `.specify/scripts/bash/create-new-feature.sh` plus
   `Write`/`Edit` inside the scratch clone, `--disallowedTools` including
   `WebSearch`/`WebFetch`/`Bash(git push:*)` (the workflow's own deterministic
   step does any pushing, never the agent). Prompt: a fixed, hardcoded
   throwaway feature description (never issue/comment text — there is no
   untrusted input to this step at all, unlike `evaluate-path`), instructing
   the agent to produce one feature spec via the candidate's own
   `/speckit-specify`-equivalent flow.
4. A deterministic "Read back stage result" step — never trusts the agent's
   own narration, exactly like `evaluate-path`'s `decide-outcome`: checks the
   local clone's working tree for a non-empty `specs/*/spec.md` the agent's
   tool calls should have produced. `steps.<agent-step>.outcome != 'success'`
   (timeout, error, unavailable credentials) or no matching file → `passed=false`
   with a `failure-detail` that explicitly states the stage did not complete,
   distinct wording from a candidate-artifact failure (FR-021).
5. Best-effort: if step 4 passed, push the produced `spec.md` to the scratch
   repository too, so a maintainer inspecting it later sees the actual
   output, not just the scaffold. This push is not gating — a push failure
   here does not flip `passed`, since the gating assertion already happened
   against the local working tree.

## Decision (made without clarification): the e2e-stage model tier is `claude-sonnet-5`, not `claude-opus-5`

**Decision**: `e2e-stage-model` defaults to `claude-sonnet-5`, matching
`evaluate-path`'s existing tier, with a dedicated overridable repo variable
(`WING_COMMANDER_AUTO_UPDATE_SPEC_KIT_E2E_STAGE_MODEL`).

**Rationale**: Constitution II assigns `claude-opus-5` to "specification and
clarification" because "the spec is the foundation every later stage
consumes, so a fully fleshed-out spec is worth the premium" — that argument
is about a *real* feature spec a human and every downstream pipeline stage
will actually read. This step's output is a throwaway artifact inside a
disposable scratch repository, read by nothing downstream and asserted only
for existence/shape (FR-018's gate is "did it complete and produce the
documented shape," not "is it good"). That is closer in weight to
`evaluate-path`'s own judgment step (which this repository already tiers at
sonnet) than to a foundational spec. spec.md's own Assumptions already
frame this as an accepted, bounded, infrequent cost ("one AI-driven stage
per minor/major candidate"), which argues for the cheaper tier that still
clears the bar rather than the more expensive one by default.

**Alternatives considered**: `claude-opus-5`, on the literal grounds that
this step *is* mechanically "specification" work per constitution II's
category list — rejected as the more expensive default given the output is
never consumed; the repo variable exists specifically so a maintainer who
disagrees can raise the tier without a code change, and this decision is
flagged on the transmittal issue comment for that reason.

## Decision: the scratch repository's name is deterministic — `wing-commander-e2e-<issue-number>`

**Decision**: The scratch repository is named
`wing-commander-e2e-<lifecycle-issue-number>` under
`github.repository_owner` (the consuming repository's own account/org — VI:
Portability). The create step is idempotent: `gh repo view` first; create
only if absent. No separate name-to-issue mapping is stored anywhere — the
name *is* the mapping (research.md's recurring "state that already exists
beats a new ledger" pattern, same reasoning specs/027/research.md already
used for settle-tracking and the rollback-target lookup).

**Rationale**: A deterministic name directly satisfies FR-022 ("the
lifecycle issue MUST name the run's scratch repository") without needing to
persist anything — the issue number the workflow already has in hand at
every point `e2e-stage` runs is the entire input. Idempotent create means a
re-dispatched run for the same still-open lifecycle issue (e.g. a maintainer
manually re-triggers `workflow_dispatch` after transient infra failure)
reuses the same scratch repository rather than accumulating duplicates,
which also means "retained while the issue is open" (FR-019) requires no
extra bookkeeping — it's just "don't delete on any path except issue-close."

**Alternatives considered**: A random/timestamped suffix
(`wing-commander-e2e-<issue>-<run-id>`) — rejected: `Date.now()`/random
values aren't needed for uniqueness here (at most one open auto-update
lifecycle issue exists at a time, per specs/027 FR-015, so the issue number
alone is already unique), and a fixed name is strictly easier for FR-022's
"names it... so a maintainer... can inspect it" and for the reaper's
prefix-based sweep (next decision) to reason about.

## Decision: scratch-repo deletion is both event-driven and a scheduled backstop sweep

**Decision**: Two independent deletion paths, both idempotent
(`gh repo delete ... --yes`, ignoring "not found"):

1. **Event-driven**: `wing-commander-auto-update-spec-kit.yml` gains
   `issues: {types: [closed]}`, resolved to `trigger: issue-closed` +
   `issue-number` (reusing the existing typed-input pattern). A new branch in
   `auto-update-spec-kit.yml` deletes `wing-commander-e2e-<issue-number>` if
   it exists, guarded by the same self-recognition discipline every other
   trigger already uses (only acts when the closed issue actually carries
   this feature's settle-tracking marker, from specs/027's data-model.md —
   never assumes every closed issue in the repository is one of this
   feature's own).
2. **Scheduled backstop**: a step added to the existing daily
   `scheduled`/`dispatch` entry point (before or alongside `health-check`)
   lists repositories matching the `wing-commander-e2e-*` prefix under
   `github.repository_owner`, extracts the issue number from each name, and
   deletes any whose corresponding issue is closed or no longer exists.

**Rationale**: Spec edge cases explicitly require both: "Run dies after
creating the scratch repository: the repository is still reaped no later
than the closure of the lifecycle issue" (only true if *something* notices
after the fact — the event trigger alone only fires for issues that are
*later* closed through the normal flow; a run that died before ever
creating an issue, or whose issue-closed webhook is missed, needs the sweep)
and "a scratch repository whose lifecycle issue is already closed or
missing is deleted rather than left orphaned" (directly the sweep's job).
GitHub Actions gives no delivery guarantee strong enough to make the
event-driven path alone sufficient (this is stated directly in the spec's
edge cases and was flagged as a known gap by the exploration behind this
plan — no existing `issues: closed` trigger exists anywhere in this
repository to lean on, so both paths are new).

**Alternatives considered**: Scheduled sweep only, no event trigger —
rejected: FR-022/SC-012 want a maintainer to be able to close the issue and
know deletion is imminent, not "sometime within the next day"; a purely
polling design would satisfy the letter of FR-023 but not the spirit of "the
maintainer knows what happens when they close it." Event trigger only, no
sweep — rejected: does not cover the two edge cases quoted above.

## Decision: narration composition — per-check reason, plus the FR-008 hint only for missing-artifact failures

**Decision**: The `combine` step's `failure-detail` output changes from "the
lightweight reason, or a single hardcoded end-to-end reason" to "the reason
of whichever check actually failed" across a strictly larger set of checks
(spec.md/plan.md non-empty, `setup-plan.sh`/`setup-tasks.sh` shape,
e2e-stage completion/shape) — each check's own `run:` step already produces
a `detail` string in the same style the lightweight tier's checks do today,
so no new narration mechanism is introduced, only more checks feeding the
same `AUTOUPDATE_EOF`-delimited multiline output the `act` job already
posts via `wing-commander-callout` unchanged. When (and only when) the
failing check is a missing-expected-artifact case (a template-driven
non-empty check), the detail string additionally appends the FR-008
sentence naming the possible legitimate-reorganization reading and pointing
at specs/027 FR-018. Every other failure reason (non-zero exit, wrong JSON
shape, e2e-stage-incomplete) omits that sentence — FR-009's "narration
content only, does not change flow" is satisfied by construction, since
every failure reason still flows through the exact same single `combine` →
`act`'s existing failure branch, unchanged.

**Rationale**: FR-007/FR-008/FR-009 are entirely about narration *content*,
not a new code path — the `act` job's existing `if:` conditions and its
single "Comment verification failure on the issue" step (unchanged from
specs/027, still gated on `needs.verify.outputs.passed != 'true'`) already
satisfy "exactly one outcome" (FR-005/FR-006); this feature only needs the
string that step posts to carry more information, which is a pure content
change inside the `combine` step that already assembles it.

## Decision: model tiering (full table)

| Step | Model | Constitution II category |
|---|---|---|
| Lightweight tier, per-script assertion chain, scratch-repo create/delete/sweep, `combine` | none (deterministic bash/`gh`/`jq`) | n/a |
| `evaluate-path` (unchanged from specs/027) | `claude-sonnet-5` | implementation-weight judgment |
| Comment-reply interpretation (unchanged from specs/027) | `claude-haiku-4-5` | triage/classification |
| `e2e-stage` decide/read-back (new) | `claude-sonnet-5` | disposable smoke-test generation — see decision above, not the foundational-spec premium tier |

Every agent step declares `--model` and `--max-turns`, per constitution II's
blanket rule. `WING_COMMANDER_AUTO_UPDATE_SPEC_KIT_E2E_STAGE_MODEL` follows
the existing `vars.WING_COMMANDER_*_MODEL || 'claude-...'` fallback idiom.

## Decision: test-harness extensions

**Decision**: No new suite file for the per-script chain or narration
changes — they extend `t4_verify.sh` directly (it already owns Scenarios
5/6/7, which this feature deepens rather than replaces). The e2e-stage
read-back step is also asserted from `t4_verify.sh`, reusing `t6_reply.sh`'s
`agent_out()` helper to build a `claude-execution-output.json` fixture in
the shape `claude-code-action` emits, exactly as `t6_reply.sh` already does
for `evaluate-path`'s own read-back step — no new fixture-building code.
`gh_stub.py` gains three new subcommand handlers:

- `gh repo create OWNER/NAME [--private] [--clone ...] [...]`: records the
  repo in state (`{"repos": {"NAME": {"owner":..,"deleted":false}}}`),
  idempotent (a second create for an already-present, non-deleted name is a
  no-op success, matching real `gh`'s own behavior for `--clone` against an
  existing repo being an error in reality — but the workflow's own
  `gh repo view` idempotency check, mirrored in the stub, means the harness
  never needs to model that error path).
- `gh repo delete OWNER/NAME --yes`: marks `deleted: true` (or removes the
  entry) rather than erroring on an already-absent name, so the
  retain-while-open/delete-on-close scenarios can assert idempotency
  directly.
- `gh repo list OWNER --json name`: returns names of all non-deleted repos
  under `owner`, filterable by the harness fixture the same way
  `releases_file` already seeds `gh api repos/github/spec-kit/releases`.

`t7_gating.py` gains the `issue-closed` trigger's job-routing (reading the
new `if:` conditions verbatim, per its existing no-retyping convention) and
`e2e-stage`'s own `if:`/gating condition in the combined verdict.
`README.md`'s scenario table gains a `t4_verify.sh` row addendum (per-script
chain, e2e-stage read-back, scratch-repo retain/delete) and its mutation
table gains rows for: the `else` fallback reintroduced, a per-script
assertion silently skipped, and the e2e-stage result reported but
non-gating.

**Rationale**: Directly satisfies FR-015/FR-020 — every new pass/fail path
gets a deterministic, repeatable assertion, and the scratch-repo lifecycle
is asserted against the controlled stub, never a real `gh repo
create`/`delete` call (FR-020's explicit requirement). Reusing
`t6_reply.sh`'s existing fixture-building convention rather than inventing a
second one keeps the harness's shape consistent with itself.

## Open items intentionally deferred beyond this plan

- The exact `--allowedTools`/`--disallowedTools` list for `e2e-stage` and
  the exact throwaway feature description text are `tasks.md`-level detail;
  this plan fixes the shape (bounded, read-back-verified, no untrusted
  input) and leaves the literal strings to task breakdown.
- The exact `gh repo create` flags (visibility, whether to seed with
  `--add-readme` so `specify init --here` has a default branch to operate
  against, or an empty repo plus an explicit first commit) are left to task
  breakdown; both are equivalent for this feature's purposes as long as the
  first commit inside the scratch repository is the candidate's own
  regenerated `.specify/` scaffold.
- `e2e-stage-max-turns`'s default of `20` is an estimate, flagged for
  maintainer confirmation before the first real minor/major run reaches
  this tier, matching how `prepare`'s own `specify init` command shape is
  already flagged in specs/027/research.md.
