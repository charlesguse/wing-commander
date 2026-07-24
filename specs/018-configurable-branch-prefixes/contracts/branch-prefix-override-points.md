# Contract: Branch Prefix Override Points

This is the configuration-surface contract for spec 018. It has two layers,
mirroring the precedent `specs/017-parameterize-hardcoded-models/contracts/model-override-points.md`
and `specs/014-configurable-gates` already established:

1. **Reusable-workflow contract** — the `workflow_call` inputs every
   reusable stage workflow exposes (what an adopter pinning
   `owner/repo/.github/workflows/<stage>.yml@ref` directly can already set
   via `with:`, with no repository variable involved at all).
2. **Repository-variable contract** — the `vars.*` names this repository's
   own thin wrapper workflows (and `watchdog.yml`, directly) read to populate
   layer 1, for adopters who prefer setting a variable once (FR-006).

Both layers MUST reproduce today's branch names when nothing is configured
(FR-002, FR-005). This file is the acceptance contract Phase 2 (`tasks.md`)
and implementation are checked against — not new design.

## Layer 1 — Reusable-workflow `workflow_call` inputs

| Workflow file | Input name | Default | Role | Status after this feature |
|---|---|---|---|---|
| `intake.yml` | `spec-draft-prefix` | `spec-draft/` | CREATE | **New** — replaces literal in agent-prompt + `git ls-remote` numbering scan |
| `intake.yml` | `spec-prefix`, `plan-prefix`, `tasks-prefix`, `impl-prefix` | `spec/`, `plan/`, `tasks/`, `impl/` | validation-only (research.md D3) | **New** — forwarded to `wing-commander-preflight`'s collision check, not used for any git operation |
| `clarify.yml` | `spec-draft-prefix` | `spec-draft/` | LOCATE (checkout ref) | **New** — replaces literal `ref: spec-draft/...` |
| `plan.yml` | `spec-draft-prefix` | `spec-draft/` | LOCATE (slug derivation from `HEAD_REF`, trigger guard already lives in the wrapper) | **New** — replaces `${HEAD_REF#spec-draft/}` |
| `plan.yml` | `spec-prefix` | `spec/` | CREATE | **New** — replaces literal in branch push, `spec_branch` field, PR head |
| `plan.yml` | `plan-prefix` | `plan/` | CREATE | **New** — replaces literal `git checkout -b plan/...`, duplicate-guard `ls-remote`, `gh pr list --head` |
| `plan.yml` | `tasks-prefix`, `impl-prefix` | `tasks/`, `impl/` | validation-only | **New** — forwarded to `wing-commander-preflight`'s collision check only |
| `tasks.yml` | `spec-prefix` | `spec/` | LOCATE | **New** — replaces literal `origin/spec/$SLUG` references |
| `tasks.yml` | `plan-prefix` | `plan/` | LOCATE (slug derivation when triggered from a merged plan PR) | **New** — replaces `${HEAD_REF#plan/}` |
| `tasks.yml` | `tasks-prefix` | `tasks/` | CREATE + LOCATE | **New** — replaces literal `git checkout -b tasks/...`, `ls-remote`, `gh pr list --head`, `${HEAD_REF#tasks/}` |
| `tasks.yml` | `spec-draft-prefix`, `impl-prefix` | `spec-draft/`, `impl/` | validation-only | **New** — forwarded to `wing-commander-preflight`'s collision check only |
| `implement.yml` | `spec-prefix` | `spec/` | LOCATE | **New** — replaces literal `origin/spec/$SLUG` references |
| `finalize.yml` | `spec-prefix` | `spec/` | LOCATE (`gh pr list --head`, `gh pr create --head`) | **New** — replaces literal `spec/$SLUG` |
| `rebase.yml` | `spec-prefix` | `spec/` | LOCATE (`git ls-remote --heads origin 'spec/*'` discovery) | **New** — replaces literal glob |
| `cleanup.yml` | `spec-draft-prefix`, `spec-prefix`, `plan-prefix`, `tasks-prefix`, `impl-prefix` | all five defaults | LOCATE + DELETE (PR-outcome `case`, branch deletion, slug recovery) | **New** — replaces five literal prefixes across the outcome classifier and teardown steps |
| `watchdog.yml` | *(none — direct `vars.*` read, existing exception)* | all five defaults | LOCATE (slug-recovery `case` on `HEAD_BRANCH`) | **New** direct reads, mirroring its existing `WING_COMMANDER_IMPLEMENT_MODEL` exception |

**Contract clauses**:

- Every input's `default:` MUST exactly equal the literal value it replaces
  (verified by `quickstart.md` scenario 1).
- No reusable stage workflow (`intake`, `clarify`, `plan`, `tasks`,
  `implement`, `finalize`, `cleanup`, `rebase`) may read `vars.*` directly —
  `release.yml` Gate 1b enforces this by grep (unchanged by this feature);
  `watchdog.yml` is the sole documented exception, pre-existing and unchanged
  in scope by this feature.
- The three CREATE-capable stages (`intake.yml`, `plan.yml`, `tasks.yml`)
  MUST forward all five resolved prefixes — including the ones they perform
  no git operation with — into `wing-commander-preflight`'s new
  `branch-prefixes` input, and MUST fail before their branch-creation step
  if that check fails (FR-010; research.md D4).
- Every prefix value used as a `git checkout -b <prefix>$SLUG`,
  `git ls-remote --heads origin '<prefix>*'`, `gh pr list --head "<prefix>$SLUG"`,
  or `${VAR#<prefix>}` operation MUST come from the corresponding input above
  — no literal prefix string may remain in any of the eight reusable stage
  workflows or in `watchdog.yml` after this feature ships (SC-001, User
  Story 3's audit scenario).

## Layer 2 — Repository variables (this repo's own wrapper wiring)

| Variable | Default (when unset or blank) | Wrapper file(s) | Resolution |
|---|---|---|---|
| `WING_COMMANDER_SPEC_DRAFT_PREFIX` | `spec-draft/` | `wing-commander-1-intake.yml`, `wing-commander-2-clarify.yml`, `wing-commander-3-plan.yml`, `wing-commander-4-tasks.yml`, `wing-commander-7-cleanup.yml` | `spec-draft-prefix: ${{ vars.WING_COMMANDER_SPEC_DRAFT_PREFIX \|\| 'spec-draft/' }}` |
| `WING_COMMANDER_SPEC_PREFIX` | `spec/` | `wing-commander-3-plan.yml`, `wing-commander-4-tasks.yml`, `wing-commander-5-implement.yml`, `wing-commander-6-finalize.yml`, `wing-commander-rebase.yml`, `wing-commander-7-cleanup.yml`, `wing-commander-1-intake.yml` (validation-only) | `spec-prefix: ${{ vars.WING_COMMANDER_SPEC_PREFIX \|\| 'spec/' }}` |
| `WING_COMMANDER_PLAN_PREFIX` | `plan/` | `wing-commander-3-plan.yml`, `wing-commander-4-tasks.yml`, `wing-commander-7-cleanup.yml`, `wing-commander-1-intake.yml` (validation-only) | `plan-prefix: ${{ vars.WING_COMMANDER_PLAN_PREFIX \|\| 'plan/' }}` |
| `WING_COMMANDER_TASKS_PREFIX` | `tasks/` | `wing-commander-4-tasks.yml`, `wing-commander-7-cleanup.yml`, `wing-commander-1-intake.yml`, `wing-commander-3-plan.yml` (validation-only) | `tasks-prefix: ${{ vars.WING_COMMANDER_TASKS_PREFIX \|\| 'tasks/' }}` |
| `WING_COMMANDER_IMPL_PREFIX` | `impl/` | `wing-commander-7-cleanup.yml`, `wing-commander-1-intake.yml`, `wing-commander-3-plan.yml`, `wing-commander-4-tasks.yml` (validation-only) | `impl-prefix: ${{ vars.WING_COMMANDER_IMPL_PREFIX \|\| 'impl/' }}` |

All five are also read directly inside `watchdog.yml`:
`SPEC_DRAFT_PREFIX="${{ vars.WING_COMMANDER_SPEC_DRAFT_PREFIX }}"` (bash
`${VAR:-'spec-draft/'}` fallback), and equivalently for the other four.

**Contract clauses**:

- Each variable is independently optional (FR-004) — setting any subset
  leaves the rest at their documented default; no variable's resolution
  reads another variable.
- An empty-string value for any variable MUST resolve identically to that
  variable being unset (spec Edge Case "blank configuration"): the
  `vars.X || 'default'` expression form (and `watchdog.yml`'s bash
  `${VAR:-default}` equivalent) satisfies this for every row.
- A non-blank value that fails `wing-commander-preflight`'s shape/collision
  check (data-model.md, Naming Value validation rules) MUST fail the
  creating stage's run before any branch is created — never silently
  fall back to the default (FR-010).
- `docs/setup.md` §3 ("Repository variables") MUST list every row in this
  table with its variable name and default — the enumeration surface SC-004
  measures.
- Adding or changing a branch-prefix variable never requires editing any
  file under `.github/workflows/{intake,clarify,plan,tasks,implement,finalize,cleanup,rebase}.yml`
  in the consuming repository — only the thin wrapper (or, for
  `watchdog.yml`, the reusable workflow itself, per its documented
  exception) — consistent with constitution VI.

## Layer 3 — Shared validation (`wing-commander-preflight`)

| Input | Type | Required | Default | Purpose |
|---|---|---|---|---|
| `branch-prefixes` | string (newline-separated `type=value`) | false | `""` (no check performed) | The full resolved set of branch-type prefixes for this run, supplied by the three CREATE-capable stages (research.md D3/D4). Validated for non-empty value, legal namespace-prefix shape, and pairwise non-collision before the composite returns success. |

**Contract clauses**:

- Empty/unset `branch-prefixes` performs no check — every other call site
  (`clarify`, `finalize`, `rebase`, `implement`, `cleanup`) that doesn't pass
  it is unaffected, preserving its existing behavior exactly.
- A failure here uses the composite's existing `fail()` helper — identical
  failure shape (`::error::`, `$GITHUB_STEP_SUMMARY`, non-zero exit) to every
  other preflight check, so no new failure-reporting mechanism is introduced.
- This check is purely deterministic bash/regex — no agent turn, no network
  call — consistent with the rest of `wing-commander-preflight` and with
  constitution II (agent cost only where an agent is genuinely needed).

## Non-goals (explicitly out of contract)

- Validating that a configured prefix, once created, is reachable under any
  consumer's branch-protection rules — out of scope; branch protection
  rejecting a push surfaces as an ordinary git/GitHub API failure at push
  time, same as today.
- `watchdog-fix/` (watchdog's autonomous-fix branches) — explicitly excluded
  per research.md's decision on branch-type scope; not part of this
  contract.
- Any naming value other than the five branch-type prefixes (labels, PR
  title formats, the `specs/NNN-slug` directory pattern) — explicitly out of
  scope per FR-009.
- Changing which stage creates which branch type, or introducing new branch
  types (e.g. making `implement.yml` start creating `impl/` branches) — a
  control-flow change, not a naming change (constitution VI; research.md
  "No change to implement.yml's branch behavior").
