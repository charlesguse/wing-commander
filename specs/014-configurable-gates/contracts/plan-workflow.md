# Contract: `plan.yml` (Gate 3 configuration addendum)

This project has no library/API surface; its "interfaces" are the
`workflow_call` input contract, the repository-level configuration variable,
and the workflow it dispatches onward. This document describes only what
changes for Gate 3 — everything not mentioned here (slug resolution,
duplicate-plan-branch guard, hand-submitted-issue creation, `pr`-mode PR
opening) is `plan.yml`'s existing, unmodified contract.

## New `workflow_call` inputs

| Input | Type | Default | Meaning |
|---|---|---|---|
| `plan-review` | string | `pr` | `pr` = Gate 3 enabled (open a plan PR, wait for a human merge — today's behavior). `auto` = Gate 3 disabled (commit the plan directly to `spec/NNN-slug`, dispatch the tasks stage automatically). |
| `next-workflow` | string | `""` | Wrapper filename to dispatch when `plan-review` resolves to `auto` and the plan commit is verified. Empty = the stage completes its own work, reports, and stops (standalone adoption, no sibling stage) — same contract shape as `tasks.yml`'s existing `next-workflow` input. |

## Configuration contract: `vars.WING_COMMANDER_PLAN_REVIEW`

Set by the wrapper (`wing-commander-3-plan.yml`) into the `plan-review`
input. Resolution (inside `plan.yml`, a "Resolve review mode" step):

| Value read from the wrapper | Resolved mode | Surfaced as a problem? |
|---|---|---|
| unset / empty | `pr` | No — this is the documented default (FR-004) |
| `pr` | `pr` | No |
| `auto` | `auto` | No |
| any other non-empty value | `pr` (fails open to the enabled default, never to `auto`) | **Yes** (FR-008) — `::warning::` annotation, `$GITHUB_STEP_SUMMARY` line, and a note appended to the "planning started" lifecycle-issue comment naming the invalid value |

This differs deliberately from `tasks.yml`'s existing `tasks-review`
resolution (which silently treats anything other than `pr` as `auto`, with
no unset/invalid distinction) — `tasks-review`'s behavior is unchanged and
out of scope; only the new `plan-review` resolution carries the surfacing
requirement, per this feature's FR-008.

## Outbound dispatch contract (auto mode only)

On success (plan artifacts verified committed to `spec/NNN-slug`, per the
verification contract below):

```bash
gh workflow run "$NEXT_WORKFLOW" -f slug="$SLUG"
```

This matches `wing-commander-4-tasks.yml`'s existing `workflow_dispatch`
input contract (`slug`, required) verbatim — this feature does not change
that wrapper's trigger surface. The dispatched run's job condition
(`github.event_name == 'workflow_dispatch' || ...`) is satisfied, and its
idempotency guard admits it because `spec-meta.json.stage == "plan"` at
that point (the guard's `restart`-flag branch only ever *widens* admission
to also include `"stalled"`; it never narrows the `"plan"` case).

## Verification contract (auto mode only, FR-007)

Before dispatch, a deterministic step must confirm, on `spec/NNN-slug`:

1. `specs/NNN-slug/plan.md` exists and is non-empty.
2. `specs/NNN-slug/spec-meta.json`'s `stage` field reads exactly `"plan"`.

Either check failing → `::error::`, job fails, **no dispatch occurs** and no
`stage:plan` label flip happens. This mirrors the existing `pr`-mode "Verify
plan PR and flip stage label" step's role: mechanical verification gates the
label flip and (in `auto` mode only) the dispatch.

## Permissions contract addendum

The `plan` job must add `actions: write` to its existing permissions
(`contents: write`, `pull-requests: write`, `issues: write`, `id-token:
write`) to perform the dispatch above. This is required only when a consumer
sets `plan-review: auto` with a non-empty `next-workflow`; the additional
grant is unconditional in the job's `permissions:` block (GitHub Actions
requires permissions to be declared statically) but is a no-op token
capability when unused — matching `tasks.yml`'s existing job, which declares
the same grant for the identical reason.

## Lifecycle record contract (unchanged fields, new path)

Precondition: `stage == "spec"` (unchanged from today). Postcondition on
success, either mode: `stage == "plan"`. No new fields are read or written;
see `data-model.md`.

## Lifecycle issue contract

- **`pr` mode (unchanged)**: "planning started" comment; on completion, plan
  summary, plan PR link, "merging advances to task generation"; label flips
  to `stage:plan`.
- **`auto` mode (new)**: "planning started" comment (unchanged); on
  completion, plan summary plus a statement that the plan was committed
  directly and the tasks stage was dispatched automatically because Gate 3
  (plan review) is disabled; label flips to `stage:plan`.
- **Invalid `plan-review` value (either mode)**: the "planning started"
  comment additionally names the invalid value and states that Gate 3
  defaulted to enabled.

## Non-goals (explicitly out of contract, per spec.md FR-011 and Edge Cases)

- Gates 1 (entry label), 2 (spec PR → `main`), and 4 (final PR → `main`) —
  no code path in this contract makes them configurable, and none of their
  wrapper/workflow files are touched by this feature.
- `WING_COMMANDER_TASKS_REVIEW`'s existing behavior, default, or silent
  invalid-value handling — unchanged, independent (FR-003), not part of this
  contract.
- The internal structure of `plan.md`/`research.md`/etc. — owned by
  `.specify/templates/plan-template.md` and the `/speckit-plan` skill,
  unchanged by this feature.
- A `plan/NNN-slug` "stalled" job — not needed, since `auto` mode never opens
  a PR that could be closed unmerged, and `pr` mode's existing stalled path
  (owned centrally by `cleanup.yml`, matching on `plan/*` head refs closed
  unmerged) is unmodified and unaffected by this feature.
