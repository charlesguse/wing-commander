# Contract: Model Override Points

This is the configuration-surface contract for spec 017. It has two layers,
mirroring the existing `WING_COMMANDER_IMPLEMENT_MODEL` precedent
(`docs/setup.md` §3, `wing-commander-5-implement.yml`):

1. **Reusable-workflow contract** — the `workflow_call` inputs every
   reusable stage workflow exposes (what an adopter pinning
   `owner/repo/.github/workflows/<stage>.yml@ref` directly can already set
   via `with:`, with no repository variable involved at all).
2. **Repository-variable contract** — the `vars.*` names this repository's
   own thin wrapper workflows read to populate layer 1, for adopters who
   prefer setting a variable once over editing `with:` blocks per stage
   (FR-003).

Both layers MUST reproduce today's model selections when nothing is
configured (FR-002, FR-005). This file is the acceptance contract Phase 2
(tasks.md) and implementation are checked against — not new design.

## Layer 1 — Reusable-workflow `workflow_call` inputs

| Workflow file | Input name | Type | Required | Default | Status after this feature |
|---|---|---|---|---|---|
| `intake.yml` | `model` | string | false | `claude-opus-4-8` | Unchanged (already existed) |
| `clarify.yml` | `model` | string | false | `claude-opus-4-8` | Unchanged (already existed) |
| `plan.yml` | `model` | string | false | `claude-sonnet-5` | Unchanged (already existed) |
| `tasks.yml` | `model` | string | false | `claude-sonnet-5` | Unchanged (already existed) |
| `rebase.yml` | `model` | string | false | `claude-sonnet-5` | Unchanged (already existed) |
| `finalize.yml` | `summary-model` | string | false | `claude-haiku-4-5` | Unchanged (already existed) |
| `cleanup.yml` | `summary-model` | string | false | `claude-haiku-4-5` | Unchanged (already existed) |
| `watchdog.yml` | `diagnose-model` | string | false | `claude-haiku-4-5` | Unchanged (already existed) |
| `watchdog.yml` | `propose-fix-model` | string | false | `claude-sonnet-5` | Unchanged (already existed) |
| `implement.yml` | `model` | string | false | `claude-sonnet-5` | Unchanged (already existed) |
| `implement.yml` | `escalation-model` | string | false | `claude-opus-4-8` | **New** — replaces 5 literals (data-model.md `implement/escalation`) |
| `implement.yml` | `summary-model` | string | false | `claude-haiku-4-5` | **New** — replaces 2 literals (progress-comment step) |

**Contract clauses**:

- Every input's `default:` MUST exactly equal the literal value it replaces
  or already represented (verified by `quickstart.md` scenario 1).
- No reusable stage workflow (`intake`, `clarify`, `plan`, `tasks`,
  `implement`, `finalize`, `cleanup`, `rebase`) may read `vars.*` directly —
  `release.yml` Gate 1b enforces this by grep; `watchdog.yml` is the sole
  documented exception (D4 in research.md), pre-existing and unchanged in
  scope by this feature.
- Every agent step consuming one of these inputs MUST also declare
  `--max-turns` explicitly (constitution II; unaffected by this feature —
  already true for all 12 rows above).

## Layer 2 — Repository variables (this repo's own wrapper wiring)

| Variable | Default (when unset or blank) | Wrapper file(s) | Resolution |
|---|---|---|---|
| `WING_COMMANDER_SPEC_MODEL` | `claude-opus-4-8` | `wing-commander-1-intake.yml`, `wing-commander-2-clarify.yml` | `model: ${{ vars.WING_COMMANDER_SPEC_MODEL \|\| 'claude-opus-4-8' }}` |
| `WING_COMMANDER_PLAN_MODEL` | `claude-sonnet-5` | `wing-commander-3-plan.yml`, `wing-commander-4-tasks.yml`, `wing-commander-rebase.yml` | `model: ${{ vars.WING_COMMANDER_PLAN_MODEL \|\| 'claude-sonnet-5' }}` |
| `WING_COMMANDER_SUMMARY_MODEL` | `claude-haiku-4-5` | `wing-commander-6-finalize.yml`, `wing-commander-7-cleanup.yml`, `wing-commander-5-implement.yml` (new `summary-model` output), `watchdog.yml` (direct read, `diagnose-model`) | `summary-model` / `model`: `${{ vars.WING_COMMANDER_SUMMARY_MODEL \|\| 'claude-haiku-4-5' }}` |
| `WING_COMMANDER_IMPLEMENT_MODEL` *(existing)* | `claude-sonnet-5` (`model:opus` label → `claude-opus-4-8`) | `wing-commander-5-implement.yml` (existing `resolve-model` job), `watchdog.yml` (direct read, `propose-fix-model`, no label logic) | Existing job logic for implement; `propose-fix-model: ${{ vars.WING_COMMANDER_IMPLEMENT_MODEL \|\| 'claude-sonnet-5' }}` for watchdog |
| `WING_COMMANDER_IMPLEMENT_ESCALATION_MODEL` | `claude-opus-4-8` | `wing-commander-5-implement.yml` (new output on the existing `resolve-model` job) | `escalation-model: ${{ vars.WING_COMMANDER_IMPLEMENT_ESCALATION_MODEL \|\| 'claude-opus-4-8' }}` |

**Contract clauses**:

- Each variable is independently optional (FR-006) — setting any subset
  leaves the rest at their documented default; no variable's resolution
  reads another variable (except the pre-existing, unchanged `model:opus`
  label layered on `WING_COMMANDER_IMPLEMENT_MODEL`).
- An empty-string value for any variable MUST resolve identically to that
  variable being unset (FR-009) — the `vars.X || 'default'` expression form
  (and `watchdog.yml`'s equivalent bash `${VAR:-default}` for its two direct
  reads) satisfies this for every row.
- `docs/setup.md` §3 ("Repository variables") MUST list every row in this
  table with its variable name and default — this is the enumeration surface
  SC-005 measures ("a reviewer can enumerate every model a run may select by
  reading configuration alone... without inspecting pipeline logic").
- Adding a repository variable never requires editing any file under
  `.github/workflows/{intake,clarify,plan,tasks,implement,finalize,cleanup,rebase}.yml`
  in the consuming repository — only the thin wrapper (or, for `watchdog.yml`,
  the reusable workflow itself, per its documented exception) — consistent
  with constitution VI (the consuming repository owns its configuration).

## Non-goals (explicitly out of contract)

- Validating that an operator-supplied model identifier is a real
  Anthropic/Bedrock model — out of scope per spec.md Assumptions; invalid
  values surface as ordinary run failures.
- Translating Anthropic model IDs to Bedrock model/inference-profile IDs —
  spec 016's concern, unchanged by this feature.
- Any new variable beyond the five in Layer 2 — the tier list is fixed at
  four illustrative tiers plus the pre-existing `implement` tier's
  escalation sibling (research.md D3); no per-location variables.
