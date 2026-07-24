# Phase 0 Research: Configurable Branch Prefixes & Consumer-Modifiable Naming

`spec.md` has no `[NEEDS CLARIFICATION]` markers. The decisions below are
implementation-level choices the spec deliberately leaves open (FR-001–FR-010
say *what* must be true — overridable, defaulted, single source, fail-closed
on invalid input — without naming a mechanism) that this plan must pin down
before `tasks.md` can be generated. Two decisions (D1, D6) resolve points the
spec's own text leaves ambiguous; both are called out explicitly in the
"Decisions made without clarification" section of the plan-completion issue
comment.

## Decision: Mechanism — reuse the repository-variable + `workflow_call` input pattern from specs 014/017

**Decision**: Branch prefixes become configurable the same way task-tier
models (spec 017) and gate modes (spec 014) already are: new repository
Variables (`vars.WING_COMMANDER_*_PREFIX`), read only by this repo's own thin
wrapper workflows (`wing-commander-N-*.yml`) and wired into new
`workflow_call` inputs on the reusable stage workflows, with `||` fallback to
a literal default that reproduces today's behavior.

**Rationale**: This is the third feature to add a consumer-configurable
value to the pipeline; 014 and 017 already establish and validate the exact
mechanism FR-001/FR-002/FR-004/FR-006 ask for (override without touching
stage internals, documented default, independent per-value fallback, single
discoverable location). Inventing a second mechanism (e.g. a checked-in
`.specify/branch-naming.json`) for the same *class* of decision — a static,
repo-scoped, trusted-maintainer setting — would violate the "don't add an
abstraction where a direct repeat of the existing pattern is simpler"
instinct 014's own research.md already applied to itself. `spec.md`'s
Assumptions section explicitly defers the mechanism choice to planning
("a checked-in configuration file and/or workflow inputs... is an
implementation detail to be settled during planning") — this is D1, the
first of the two decisions made without a clarification round.

**Alternatives considered**: A checked-in JSON/YAML naming-config file
(parallel to `.specify/memory/watchdog-guardrails.json`) — rejected. That
precedent is read-only, per-spec-run-agent-consumed configuration for a
single stage (watchdog rung-1 fixes); branch prefixes are read by up to 9
workflow files across the whole lifecycle and must be visible in the GitHub
Settings UI the same way every other pipeline knob already is, so a second,
differently-shaped configuration surface would fragment discoverability
rather than serve it (FR-006).

## Decision: Five new repository variables, one per branch type

**Decision**: Introduce exactly five new repository variables, each
independently optional:

| Variable | Default |
|---|---|
| `WING_COMMANDER_SPEC_DRAFT_PREFIX` | `spec-draft/` |
| `WING_COMMANDER_SPEC_PREFIX` | `spec/` |
| `WING_COMMANDER_PLAN_PREFIX` | `plan/` |
| `WING_COMMANDER_TASKS_PREFIX` | `tasks/` |
| `WING_COMMANDER_IMPL_PREFIX` | `impl/` |

**Rationale**: These are exactly the five branch-type prefixes named in the
constitution's Operational Constraints, `docs/architecture.md`'s "shared
artifact contract" sentence, and `specs/010-reusable-pipeline/contracts/stage-interfaces.md`'s
Universal Behavior bullet. No sixth pipeline-owned prefix exists in the
codebase (confirmed by a full-repo search of `.github/workflows/*.yml` and
`.github/actions/*/action.yml`).

**`impl/` is included despite no current CREATE site**: `implement.yml`
commits each iteration directly onto `spec/$SLUG` — no workflow currently
executes `git checkout -b impl/...`. However `impl/$SLUG-iterN` remains part
of the documented, LOCATE-side contract: `cleanup.yml`'s teardown-on-merge
job globs and deletes `impl/$SLUG-iter*` branches, its PR-outcome classifier
matches `impl/*`, and `watchdog.yml`'s slug-recovery `case` matches `impl/*`.
Treating it as a sixth, unconfigurable exception would contradict FR-006
("single, discoverable configuration location" for the *complete*
consumer-modifiable naming surface) and would leave a latent branch type
that two stages can already resolve but no consumer can rename. It is
therefore included as a configurable value with no operational CREATE
consumer today — a reserved, forward-compatible prefix.

**`watchdog-fix/$SHORT_FP` (watchdog's own autonomous-fix PRs) is explicitly
excluded**: it is not part of the `spec-draft/spec/plan/tasks/impl` lifecycle
contract named anywhere in the constitution, `docs/architecture.md`, or
`docs/adoption.md` — it is watchdog's own remediation artifact, orthogonal to
the spec lifecycle a requester tracks. `spec.md` does not mention it. This
plan makes the explicit scoping call to exclude it, consistent with FR-009's
own style of naming things left fixed on purpose; a future feature can extend
naming configurability to it if requested. This is D6, the second decision
made without a clarification round, called out in the issue comment.

## Decision: Layer 1 — every reusable stage declares only the prefix inputs its own git operations use; the three CREATE stages additionally receive the full 5-value set for validation

**Decision**: Each reusable stage workflow gains `workflow_call` inputs for
the prefixes it operationally reads or writes (see
`contracts/branch-prefix-override-points.md` for the exact per-stage table).
Additionally, the three stages that execute `git checkout -b`/push a
new pipeline-owned branch — `intake.yml` (`spec-draft/`), `plan.yml`
(`spec/`, `plan/`), `tasks.yml` (`tasks/`) — each declare **all five** prefix
inputs, not just the ones they use operationally, and forward all five into
`wing-commander-preflight` (D4) for cross-type validation before the branch
is created. `cleanup.yml` and `watchdog.yml` already need all five
operationally (full-lifecycle teardown/diagnosis), so no extra inputs are
needed there. `clarify.yml`, `finalize.yml`, `rebase.yml`, and `implement.yml`
each declare only the single prefix input their own LOCATE operation needs
(`spec-draft-prefix` for clarify; `spec-prefix` for finalize, rebase, and
implement).

**Rationale**: FR-010 requires the invalid/colliding-prefix failure to occur
"before creating any branch" — a guarantee that can only be made by the
stage that is about to create one, and only if that stage can see every
sibling prefix a collision could occur against. Giving every stage all five
inputs regardless of use would be simpler code but adds inputs three
locate-only, non-creating stages (`clarify`, `finalize`, `rebase`) would never
read, which is unnecessary surface for an adopter pinning a stage directly
(`stage-interfaces.md`'s own minimality expectation). Restricting the
CREATE stages to their own operational subset would leave FR-010 unverifiable
for prefixes those stages don't otherwise touch (e.g. `intake.yml` colliding
`spec-draft-prefix` against a consumer's `impl-prefix` value would go
undetected until `cleanup.yml` or `watchdog.yml` next ran — after the branch
already exists). Giving the three CREATE stages the full set is the smallest
change that makes FR-010's "before creating any branch" literally true.

**Alternatives considered**: A dedicated `validate-naming` reusable workflow
that every wrapper calls as a job dependency before dispatching its target
stage — rejected as unnecessary indirection; `wing-commander-preflight`
already exists as exactly this kind of shared, pre-agent, deterministic gate,
and extending it (D4) reuses it rather than adding a second one.

## Decision: Layer 2 — repository-variable wrapper wiring mirrors the existing `vars.X || 'default'` idiom

**Decision**: Each `wing-commander-N-*.yml` wrapper computes its stage's
needed prefix inputs with the same expression form already used for models
and gate modes: `spec-draft-prefix: ${{ vars.WING_COMMANDER_SPEC_DRAFT_PREFIX || 'spec-draft/' }}`,
etc. `watchdog.yml` (not one of the 8 published/gated stages — see D4) keeps
its existing documented exception and reads `vars.WING_COMMANDER_*_PREFIX`
directly with bash `${VAR:-default}` fallback, exactly as it already does for
`WING_COMMANDER_IMPLEMENT_MODEL`.

**Rationale**: Identical to 017 Layer 2 — GitHub Actions expressions treat an
empty string as falsy for `||`, so unset and blank both resolve to the
documented default in one mechanism (FR-004, spec Edge Case "malformed
configuration" partially: blank is not malformed, it is "unset").

## Decision: FR-010 validation runs inside `wing-commander-preflight`, fails closed, and diverges deliberately from 014's fail-open gate pattern

**Decision**: `wing-commander-preflight` (`.github/actions/wing-commander-preflight/action.yml`)
gains one new optional input, `branch-prefixes` — a newline-separated
`type=value` list (e.g. `spec-draft=spec-draft/`) — and one new check block
that runs whenever it is non-empty:

1. **Emptiness**: each `value` must be non-empty.
2. **Character/shape validity**: each `value` must end in exactly one `/`
   and the portion before it must match `^[A-Za-z0-9][A-Za-z0-9._-]*$` — a
   conservative subset of valid `git check-ref-format` characters (excludes
   space, `~^:?*[\`, `..`, and leading `-`/`.`), sufficient to guarantee the
   resulting branch name is a legal git ref without reimplementing the full
   git grammar.
3. **Collision**: no two of the (up to five) supplied prefixes may be equal,
   and neither may be a literal string-prefix of the other (e.g. `spec/` and
   `spec/sub/` collide — a `startsWith()` trigger guard or `case spec/*`
   branch meant for one would also match the other).

Any failure calls the composite's existing `fail()` helper — `::error::` +
`$GITHUB_STEP_SUMMARY` + non-zero exit — which already stops the job before
any later step (including branch creation) runs, on **every** call site,
matching FR-010's "before creating any branch" without a new failure
mechanism.

**This fails closed, not open, deliberately unlike 014's `plan-review`
resolution**: 014 chose "invalid value → safe default (`pr`) + a visible
warning" because `pr` is always a safe substitute for any gate mode. No
equivalent safe substitute exists here: falling back to a prefix's *default*
value when the *configured* value collides could itself silently collide
with a *different*, correctly-configured sibling prefix (e.g. a consumer sets
`plan-prefix=spec/`, colliding with the default `spec-prefix=spec/` — falling
`plan-prefix` back to *its own* default `plan/` is fine, but the collision
check exists precisely because letting one bad value slide is a hidden
identity bug the consumer would only discover as a cross-stage handoff
failure, exactly what FR-003/SC-002 exist to prevent). FR-010's own text
("fail the run... clear, actionable error... rather than silently falling
back to the default") is unambiguous on this point, so no clarification was
needed here — this decision directly implements FR-010, not a gap-fill.

**Alternatives considered**: Reimplementing `git check-ref-format --branch`
via a subprocess call — rejected as unnecessary precision for a prefix
(not a full branch name); the conservative regex is simpler, has no
subprocess dependency, and any character it rejects that git would have
accepted is not a meaningful loss (hyphenated/underscored/dotted namespace
prefixes cover every realistic team convention named in spec.md's User Story
1, e.g. `feature/`, `team-abbrev/`).

## Decision: Discoverability — `docs/setup.md` §3 gains five rows; `docs/adoption.md`, `docs/architecture.md`, and `stage-interfaces.md` reword hardcoded-literal sentences into "configurable, default shown"

**Decision**: Document all five variables as new rows in `docs/setup.md`'s
existing "Repository variables" table (FR-007, SC-004) — the same table 014
and 017 each added rows to. Reword:
- `docs/adoption.md`'s "the branch prefixes `spec-draft/`, `spec/`, `plan/`,
  `tasks/`, `impl/`... are the shared artifact contract" sentence and each
  Stage-reference table's `Side effects` cell that names a literal prefix, to
  state the prefix is configurable with the literal shown as its default.
- `docs/architecture.md`'s "Branches" bullet (default-branch derivation
  paragraph) and its cleanup/watchdog sections, same treatment.
- `specs/010-reusable-pipeline/contracts/stage-interfaces.md`'s Universal
  Behavior bullet, which currently states the five prefixes "remain part of
  the shared artifact contract" as an immutable fact — reworded to describe
  them as configurable-with-defaults, and a new row added to its Common
  Inputs table for the prefix inputs newly common across the CREATE-capable
  stages.
- `.specify/memory/constitution.md`'s Operational Constraints line 42, which
  names the four prefixes (missing `tasks/`, a pre-existing drift this plan
  also fixes) as flat fact — reworded to "...the pipeline's default branch
  prefixes... (consumer-configurable via repository variables — see
  docs/setup.md)". This is a wording clarification of an Operational
  Constraint, not a Core Principle change, so it is a PATCH-level amendment
  (Governance section semver rule) with its own Sync Impact Report header,
  matching the style of the existing 1.1.0→1.2.0 report at the top of the
  file.

**Rationale**: Directly satisfies FR-007/SC-004 (every consumer-modifiable
naming value listed with its default in one documentation location) using
the same location and table shape 014/017 already validated, and closes the
contradiction FR-001 would otherwise create against `stage-interfaces.md`'s
current "prefixes are contract, not configurable" wording.

## Decision: No change to `implement.yml`'s branch behavior

**Decision**: `implement.yml` is not modified to start creating `impl/`
branches; it continues to commit each iteration directly to `spec/$SLUG`.
This feature only makes `implement.yml`'s existing `spec-prefix` input (used
to construct `origin/spec/$SLUG` references) consumer-configurable — it does
not change *what* branches implement.yml touches.

**Rationale**: Changing implement.yml's branch topology is a distinct,
unscoped concern (spec.md says nothing about it) — this feature's job is
naming, not control flow (constitution VI: "consumers customize naming but
do not change the pipeline's control flow").

## Decision: Mid-lifecycle prefix changes need no new mechanism (edge case)

**Decision**: No snapshotting of the resolved prefix into `spec-meta.json` is
introduced. Each wrapper reads its repository variables fresh on every run,
exactly as 014 already established for gate modes; a spec with branches
already created under an old prefix keeps working under that prefix (its
branch names don't retroactively change), and any *new* branch the same spec
needs after a prefix change uses the new value — this is exactly the
behavior `spec.md`'s Assumptions section describes ("changing a prefix
affects only branches created after the change... may need to complete under
their original prefix").

**Rationale**: Falls out of how GitHub Actions variables and git branches
already work; no additional state to design or synchronize.
