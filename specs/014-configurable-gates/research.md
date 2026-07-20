# Phase 0 Research: Configurable Human Review Gates

`spec.md`'s checklist confirms no `[NEEDS CLARIFICATION]` markers remain (both
prior markers were resolved on issue #74 before this plan ran). The decisions
below are implementation-level choices the spec deliberately left open (it
says "configurable" and "trusted maintainer configuration" without naming a
mechanism) that this plan must pin down before tasks can be generated.

## Decision: Mechanism — reuse the tasks-stage's declared-input pattern

**Decision**: Gate 3 (plan review) becomes configurable the same way the
tasks step already is: a new `plan-review` input (`pr` \| `auto`, default
`pr`) on the reusable `plan.yml` workflow, set from a new repository variable
`WING_COMMANDER_PLAN_REVIEW` by the wrapper (`wing-commander-3-plan.yml`) —
exactly parallel to `tasks.yml`'s `tasks-review` input and
`vars.WING_COMMANDER_TASKS_REVIEW`.

**Rationale**: This precedent already exists in the codebase (`tasks.yml`
lines documented in `docs/architecture.md` §Stage 3) and already satisfies
FR-001 (per-gate on/off), FR-010 (trusted maintainer configuration — a repo
variable, not issue/comment content), and FR-012 (repository-wide, no
per-spec override — a `vars.*` value is inherently repository-scoped). No new
configuration surface needs inventing.

**Alternatives considered**: A single JSON/YAML file (e.g.
`.specify/gates.json`) committed to the repo and read by every stage —
rejected: it duplicates a mechanism (repo variables) that is already
trusted, already discoverable via the GitHub UI (Settings → Variables), and
already used for exactly this purpose one stage over. Introducing a second
configuration surface for the same kind of decision would violate the
"three similar lines is better than a premature abstraction" instinct in
reverse — it would *add* an abstraction where a direct repeat of the existing
pattern is simpler and more consistent.

## Decision: Default value is `pr`, not `auto` — intentionally asymmetric with tasks-review

**Decision**: `plan-review` defaults to `pr` (Gate 3 enabled — today's
behavior). This differs from `tasks-review`'s existing default of `auto`.

**Rationale**: FR-004 requires every gate to default to enabled, and the
spec's Assumptions state "Default configuration reproduces current behavior:
all gates enabled." Gate 3 is enabled (a human merges the plan PR) in
today's shipped behavior, so its configurable default must be `pr`. The
tasks step's existing `auto` default predates this feature (introduced by
`003-tasks-stage`) and is explicitly carved out by FR-011's phrasing as "the
already-automatic tasks step" — this feature does not touch that default,
only confirms it remains untouched and independent (FR-003).

**Alternatives considered**: Defaulting the new `plan-review` variable to
`auto` for symmetry with `tasks-review` — rejected outright; it would silently
weaken review for every repository that adopts this feature version without
opting in, violating FR-004 and User Story 3 directly.

## Decision: Invalid-configuration handling deliberately does NOT copy tasks.yml's silent fallback

**Decision**: A new "Resolve review mode" step in `plan.yml` evaluates
`inputs.plan-review` as a three-way case:
- unset/empty → `pr` (silent — this is the documented default, not an error)
- `pr` or `auto` → respected as-is
- any other non-empty value → falls back to `pr` **and** surfaces the
  problem: an `::warning::` workflow annotation, a `$GITHUB_STEP_SUMMARY`
  line, and a note appended to the "planning started" lifecycle-issue
  comment, so a maintainer who only watches the issue (Principle III) still
  learns about it.

**Rationale**: FR-008 requires that invalid/unrecognized configuration "MUST
NOT weaken a gate" and that "the problem MUST be surfaced rather than
silently applied." `tasks.yml`'s existing `tasks-review` resolution step
treats *any* non-`pr` value as `auto` with no distinction between "unset" and
"typo'd" — that is out of scope to change here (FR-011 scopes this feature to
Gate 3; the tasks step's existing behavior is not part of this feature's
acceptance criteria), but the new Gate 3 resolution step must not repeat that
gap, since this feature's own FR-008 explicitly demands surfacing.

**Alternatives considered**: Failing the whole workflow run on an invalid
value — rejected; FR-008 asks for a safe fallback (defaults to enabled) plus
visibility, not a hard failure that would block planning entirely over a
typo.

## Decision: Auto-mode execution shape mirrors `tasks.yml`'s `agent-auto` step

**Decision**: When `plan-review` resolves to `auto`, the plan agent runs on
the `spec/NNN-slug` branch directly (no `plan/NNN-slug` work branch), commits
`plan.md`, `research.md`, `data-model.md`, `contracts/`, `quickstart.md`, and
`spec-meta.json` (`stage: "plan"`) straight to `spec/NNN-slug`, and opens no
PR — byte-for-byte the same shape as `tasks.yml`'s existing `agent-auto` step
for the tasks artifact.

**Rationale**: Reuses an already-implemented, already-reviewed pattern
instead of inventing a new one. FR-006 (the gated artifact must still be
produced and persisted) falls out of this for free — the commit lands on the
persistent spec branch exactly as it would land eventually via a merged PR.

**Alternatives considered**: Still creating `plan/NNN-slug` and having the
workflow auto-merge it via the `gh` API — rejected; that requires the bot to
merge a PR, which the constitution forbids (Principle V: "the bot never
approves or merges to `main`" — and by the same spirit, never auto-merges any
pipeline PR). Direct commit avoids a merge entirely.

## Decision: FR-007 (bad artifact must stop, not cascade) — deterministic post-agent verification

**Decision**: After the auto-mode agent step, a deterministic (non-agent)
step fetches `spec/NNN-slug` and verifies `plan.md` exists and is non-empty,
and that `spec-meta.json`'s `stage` field reads `"plan"`, before any dispatch
happens — mirroring `tasks.yml`'s existing "Verify tasks committed (auto)"
step. Any failure emits `::error::` and fails the job; nothing downstream is
dispatched.

**Rationale**: Matches the edge case in `spec.md` ("Auto-advanced artifact is
defective") and the general pattern this repo already uses everywhere else:
verification is a cheap deterministic step, not an agent turn, and runs even
when the agent step itself reports success (protects against a partial or
silently-empty write).

**Alternatives considered**: Trusting the agent's own report of success —
rejected; this is exactly the failure mode FR-007 exists to prevent, and the
codebase already treats "verify, then flip the label" as the standard
closing step for every stage (`pr` mode's own "Verify plan PR and flip stage
label" step is the existing example this generalizes from).

## Decision: Dispatching the tasks stage on bypass reuses the `next-workflow` idiom verbatim

**Decision**: `plan.yml` gains a `next-workflow` input (string, default
`""`), following `tasks.yml`'s existing contract exactly. On successful
auto-mode verification, a deterministic step runs
`gh workflow run "$NEXT_WORKFLOW" -f slug="$SLUG"`. The wrapper
(`wing-commander-3-plan.yml`) sets `next-workflow: wing-commander-4-tasks.yml`.
No change is needed to `wing-commander-4-tasks.yml`'s trigger surface: it
already accepts a bare `slug` via `workflow_dispatch` and treats the call as
`restart: true`, which the tasks stage's own idempotency guard already
admits whenever `spec-meta.json.stage == "plan"` — true here — regardless of
the `restart` flag's value (`restart` only additionally admits `"stalled"`;
it never *narrows* the `"plan"` case). So this dispatch lands on an existing,
unmodified acceptance path.

**Rationale**: Consistency with the one precedent this repo already has for
"stage N bypasses its human gate and hands off to stage N+1 directly"
(`tasks.yml`'s own dispatch of `wing-commander-5-implement.yml`). Reusing the
exact same input name and dispatch shape means an adopter who already
understands `tasks-review`/`next-workflow` needs to learn nothing new for
`plan-review`.

**Permissions note**: the `plan` job in `plan.yml` currently declares
`contents: write`, `pull-requests: write`, `issues: write`, `id-token: write`
— no `actions: write`. Dispatching a workflow via `gh workflow run` requires
it. This is a genuine, minimal permissions addition (scoped to workflow
dispatch only, matching what `tasks.yml`'s job already grants itself for the
same reason) — not a violation of least-privilege, since it is the smallest
grant that makes the dispatch possible.

**Alternatives considered**: Having the tasks stage itself poll/watch for a
direct-commit plan (no dispatch, tasks stage triggers on a push to
`spec/**`) — rejected; a push-based trigger on the persistent spec branch
would fire on *every* commit to that branch (including ones tasks.yml itself
makes), creating ambiguity about which push means "plan is ready" that the
explicit dispatch avoids entirely.

## Decision: Lifecycle-issue auditability (FR-005)

**Decision**: The plan agent's own prompt step (already responsible for
posting the plan summary to the issue) is given mode-specific closing
instructions: `pr` mode keeps its existing text (plan PR link, "merging
advances to task generation"); `auto` mode's text instead states that the
plan was committed directly to the spec branch and that the tasks stage was
dispatched automatically because Gate 3 (plan review) is disabled —
mirroring `tasks.yml`'s existing `auto`-mode issue comment ("implementation
is dispatched automatically...").

**Rationale**: Directly satisfies FR-005 and SC-004 (every bypassed-gate
advance is recorded on the lifecycle issue) using the same agent step that
already writes to the issue — no new agent invocation needed.

**Alternatives considered**: A separate deterministic step posting a
"gate bypassed" comment — rejected as redundant; the agent step already
authors the issue comment as part of its normal completion report, so adding
one more sentence of instruction is simpler than a second `gh issue comment`
call.

## Decision: Discoverability (FR-009, SC-003)

**Decision**: Document `WING_COMMANDER_PLAN_REVIEW` in the same three places
`WING_COMMANDER_TASKS_REVIEW` already lives: `docs/setup.md`'s repository
variables table, `docs/adoption.md`'s stage-interfaces reference (the `plan`
section's Inputs row and the wrapper example), and
`specs/010-reusable-pipeline/contracts/stage-interfaces.md`'s
`reusable-plan.yml` row. `docs/architecture.md`'s Stage 2 section is rewritten
to describe both modes, mirroring how its Stage 3 section already describes
`auto`/`pr` for the tasks step.

**Rationale**: Satisfies FR-009/SC-003 ("discoverable... without reading
pipeline source or run logs") via the same channel already relied upon for
the tasks step: the GitHub Settings → Variables page (which lists the
variable and its current value directly) plus the adoption docs (which name
the variable and explain its values). No new discovery UI or command is
built, consistent with Principle III (no external dashboards, no custom
CLIs).

**Alternatives considered**: A `gh` script or Actions job that prints "here
are your current gate settings" — rejected as unnecessary; the repository
variables UI already answers this question directly, and building a second
way to ask it would be a feature the spec never requested.

## Decision: Gates 1, 2, and 4 are explicitly out of scope

**Decision**: No code changes touch `intake.yml` (Gate 1: maintainer-applied
label), the spec-draft→`main` PR flow (Gate 2), or `finalize.yml` (Gate 4:
final PR into `main`). This plan's Project Structure section names exactly
the files this feature touches; anything not listed there is unmodified.

**Rationale**: FR-011 is explicit and the constitution's Principle V marks
"humans merge every PR into `main`" and "pipeline entry requires a
maintainer-applied label" NON-NEGOTIABLE. Making Gates 1, 2, or 4
configurable would require a constitution amendment, which is out of scope
for this feature (spec Edge Cases section).

**Alternatives considered**: None — this is a hard constitutional boundary,
not a design trade-off.

## Decision: Mid-lifecycle configuration changes need no new mechanism (edge case)

**Decision**: No caching or snapshotting of `vars.WING_COMMANDER_PLAN_REVIEW`
is introduced. The wrapper reads the repository variable fresh every time it
runs (GitHub Actions resolves `vars.*` at job evaluation time, per-run), so a
spec already past Gate 3 when the variable changes is unaffected, and the
next spec (or the next run of the same spec, which can only reach Gate 3
once) always observes whatever value is current at that moment.

**Rationale**: This is exactly the behavior the spec's edge case
("Configuration changed mid-lifecycle") asks for, and it falls out of how
GitHub Actions variables already work — no additional state needs to be
introduced or synchronized.

**Alternatives considered**: Snapshotting the gate setting into
`spec-meta.json` at spec-creation time — rejected; the spec explicitly wants
the *currently configured* value read "when the spec reaches a gate," not a
value pinned earlier in the spec's life.
