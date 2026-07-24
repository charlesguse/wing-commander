# Phase 1 Data Model: Configurable Branch Prefixes

This feature has no runtime data store; its "entities" are configuration
concepts realized as GitHub Actions `workflow_call` inputs, repository
Variables, and one new deterministic validation input on the shared
`wing-commander-preflight` composite. This document specifies their fields,
relationships, and validation rules per `spec.md`'s Key Entities section.

## Entity: Branch Type

A distinct category of branch the pipeline creates or resolves during a
spec's lifecycle (spec.md Key Entities). Corresponds exactly to the five
prefixes identified in `research.md`.

| Field | Description |
|---|---|
| `name` | One of: `spec-draft`, `spec`, `plan`, `tasks`, `impl` |
| `default_prefix` | The literal prefix string used when unconfigured |
| `creating_stage(s)` | The stage(s), if any, that execute `git checkout -b`/push to originate a branch of this type |
| `locating_stage(s)` | The stage(s) that resolve an existing branch of this type by prefix (trigger guards, slug stripping, `gh pr list --head`, deletion globs) |

| Branch type | Default prefix | Creating stage(s) | Locating stage(s) |
|---|---|---|---|
| `spec-draft` | `spec-draft/` | `intake.yml` | `clarify.yml`, `plan.yml`, `cleanup.yml`, `watchdog.yml` |
| `spec` | `spec/` | `plan.yml` | `tasks.yml`, `implement.yml`, `finalize.yml`, `rebase.yml`, `cleanup.yml`, `watchdog.yml` |
| `plan` | `plan/` | `plan.yml` | `tasks.yml`, `cleanup.yml`, `watchdog.yml` |
| `tasks` | `tasks/` | `tasks.yml` | `cleanup.yml`, `watchdog.yml` |
| `impl` | `impl/` | *(none currently — reserved, research.md)* | `cleanup.yml`, `watchdog.yml` |

**Relationships**: A Branch Type has exactly one Naming Value governing its
prefix (1:1). A Branch Type has zero-or-one creating stages and one-to-many
locating stages. A stage may be both a creating and locating stage for
different branch types (e.g. `plan.yml` creates `spec` and `plan` branches
while locating `spec-draft` branches to derive its slug).

**Validation rules**: Every CREATE and LOCATE site enumerated in
`contracts/branch-prefix-override-points.md` MUST resolve its branch type's
prefix from the same Naming Value (FR-003, SC-002) — no site may hardcode a
literal prefix string once this feature ships.

## Entity: Naming Value (branch prefix)

An individual consumer-modifiable string — for this feature, exactly a
branch-type prefix (FR-009) — with a documented default and an optional
override, realized as a repository Variable plus the `workflow_call`
input(s) it feeds.

| Field | Description |
|---|---|
| `variable_name` | The `vars.*` repository-variable name a consumer sets |
| `branch_type` | The Branch Type this value governs (1:1) |
| `default_value` | Value used when the variable is unset or blank |
| `wired_workflow_inputs` | The `workflow_call` input(s) this variable's resolved value is passed into |
| `resolution_mechanism` | How the wrapper (or, for watchdog, the stage itself) computes the effective value |

| `variable_name` | `branch_type` | `default_value` | `wired_workflow_inputs` |
|---|---|---|---|
| `WING_COMMANDER_SPEC_DRAFT_PREFIX` | `spec-draft` | `spec-draft/` | `intake.yml:spec-draft-prefix`, `clarify.yml:spec-draft-prefix`, `plan.yml:spec-draft-prefix`, `cleanup.yml:spec-draft-prefix` |
| `WING_COMMANDER_SPEC_PREFIX` | `spec` | `spec/` | `plan.yml:spec-prefix`, `tasks.yml:spec-prefix`, `implement.yml:spec-prefix`, `finalize.yml:spec-prefix`, `rebase.yml:spec-prefix`, `cleanup.yml:spec-prefix` |
| `WING_COMMANDER_PLAN_PREFIX` | `plan` | `plan/` | `plan.yml:plan-prefix`, `tasks.yml:plan-prefix`, `cleanup.yml:plan-prefix` |
| `WING_COMMANDER_TASKS_PREFIX` | `tasks` | `tasks/` | `tasks.yml:tasks-prefix`, `cleanup.yml:tasks-prefix` |
| `WING_COMMANDER_IMPL_PREFIX` | `impl` | `impl/` | `cleanup.yml:impl-prefix` |

All five are additionally read directly by `watchdog.yml` via
`vars.WING_COMMANDER_*_PREFIX` (its existing documented `vars.*` exception —
research.md D3/D4), with no `workflow_call` input.

**Resolution mechanism**: each wrapper (`wing-commander-N-*.yml`) computes
`${{ vars.WING_COMMANDER_<TYPE>_PREFIX || '<default>/' }}` and passes it into
the corresponding stage input; `watchdog.yml` uses the bash equivalent
`${VAR:-'<default>/'}` directly.

**Validation rules** (from `spec.md` Edge Cases and FR-010, detailed in
`research.md` D4 and `contracts/branch-prefix-override-points.md`):

- **Blank/empty override**: unset or empty-string `vars.<NAME>` resolves to
  `default_value` — same single mechanism as 014/017 (`||` in GitHub Actions
  expressions treats `''` as falsy).
- **Invalid override** (FR-010): a non-blank value that is not a legal
  namespace-prefix shape, OR that collides with another supplied prefix
  (equal, or one is a string-prefix of the other), MUST fail the run via
  `wing-commander-preflight`'s new `branch-prefixes` check *before* the
  creating stage's branch-creation step runs. This is validated by the three
  CREATE-capable stages (`intake.yml`, `plan.yml`, `tasks.yml`), which each
  receive all five prefixes for this purpose (research.md D3).
- **Independence** (FR-004): each Naming Value's resolution is a pure
  function of its own variable — no Naming Value's resolution reads another
  Naming Value's variable.
- **Default reproduction** (FR-002, FR-005): every `default_value` above
  equals the literal string the corresponding CREATE/LOCATE site already
  hardcodes today — this is the acceptance bar for `tasks.md` and
  implementation, not a new value chosen by this plan.
- **Discoverability** (FR-007, SC-004): every row's `variable_name` and
  `default_value` MUST appear in `docs/setup.md`'s repository-variables
  table — the single source a reviewer reads to enumerate every configurable
  prefix without inspecting workflow internals.

## Entity: Naming Configuration

The complete set of five Naming Values, considered together — this is the
"single source" FR-006 requires. It is not a separate file or object; it is
the union of the five repository variables above, always resolved together
(with defaults filling any gaps) at the point each CREATE-capable stage's
`wing-commander-preflight` step runs.

**Validation rules**: The full five-value set MUST pass `wing-commander-preflight`'s
collision check (no two resolved prefixes equal or string-prefixed by each
other) before `intake.yml`, `plan.yml`, or `tasks.yml` creates a branch
(FR-010). A subset of the five may be overridden while the rest use their
defaults (FR-004, SC-005) — the collision check still runs against the full
resolved five-value set (defaults included), since a consumer-configured
value can just as easily collide with an *unconfigured* sibling's default as
with another override.

## State / lifecycle

None of these entities have state transitions — they are static
configuration resolved fresh on every workflow run, at the point each
wrapper evaluates its `with:` block (before any job starts) or, for
`watchdog.yml`, at the point its step reads `vars.*` directly. There is no
caching, snapshotting, or persistence of a resolved prefix beyond the GitHub
Actions run itself (research.md, "Mid-lifecycle prefix changes" decision).
