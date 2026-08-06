# Contract: Deployment Environment Binding

Governs every one of Wing Commander's ten published `workflow_call`-only
stage workflows (FR-001 through FR-013). Companion to
`specs/010-reusable-pipeline/contracts/stage-interfaces.md`'s "Common
inputs" table, which implementation amends with the two rows below (that
edit is scoped to the implementation stage, not this plan's own artifacts —
see `plan.md` Project Structure).

## New stage inputs (all ten published stages: intake, clarify, plan, tasks,
implement, finalize, cleanup, rebase, watchdog, auto-update-spec-kit —
research D1)

| Input | Type | Default | Required |
|---|---|---|---|
| `environment` | string | `""` | never (optional, off by default — FR-001) |
| `environment-deployment` | boolean | `true` | never (optional; meaningful only when `environment` is non-empty — FR-002) |

No `secrets:` additions. No changes to any existing input, secret, or output
of any stage — this is a strictly additive interface change.

## Binding mechanism (research D2)

Every job in every one of the ten stage files gains:

```yaml
jobs:
  <job-id>:
    # ...
    environment:
      name: ${{ inputs.environment }}
      deployment: ${{ inputs.environment-deployment }}
```

added unconditionally — no `if:`, no per-job selection, no distinction
between agent-running and agent-free jobs within a stage file (FR-004, User
Story 4 acceptance scenario 2: "which jobs bind is not a hidden internal
rule"). This is the *entire* implementation surface for the binding itself;
no composite action, step, or `permissions:` block is added anywhere
(research D6).

**Empirical basis** (probed 2026-08-05 against GitHub-hosted runners, public
repo [charlesguse/wc-env-probe](https://github.com/charlesguse/wc-env-probe);
FR-013 requires every place this contract or its implementation relies on
these to carry a comment pointing back here):

1. An empty `name` is a true no-op — no environment applied, no gate, no
   deployment record, no phantom environment created — for both the string
   and mapping forms. This is what lets the block above be emitted
   unconditionally rather than gated behind an `if: inputs.environment != ''`.
2. The mapping form accepts an expression in `name`, binding identically to
   the string form.
3. `deployment: false` is a real, GitHub-recognized key (confirmed against a
   strict-parser control: an actually-unknown key under `environment:`
   produces a hard `422`) that preserves the environment binding and its
   protection rules while suppressing the deployment record.
4. A name that doesn't exist yet is silently auto-created on reference, with
   no protection rules — not rejected, not validated.

## Timing invariant (FR-005)

`environment:` is a job-level attribute, evaluated by GitHub before any step
in that job runs. This structurally guarantees the binding takes effect
before the job's existing preflight step and before any agent step — no
reordering of steps, no new pre-agent check, and nothing for a shared
composite (`wing-commander-preflight` or otherwise) to enforce (research D4).
A protection rule that pauses the run (required reviewer, wait timer) does
so before the job's first step executes at all, so no agent cost is ever
incurred while pending (SC-002).

## Pass-through, no validation (FR-007)

The pipeline performs no existence check, allowlist, or format validation on
`environment`'s value, and requires no new GitHub App permission to support
one. A name that doesn't exist is created on reference by GitHub itself
(empirical basis item 4) — the adopter-facing consequence (a typo silently
produces a new, unprotected environment) is a documentation obligation
(FR-012), not a code behavior this contract adds.

## Deployment-record suppression (FR-008, User Story 3)

`environment-deployment: false` keeps the environment's protection rules in
force while suppressing the deployment record GitHub would otherwise create
— entirely via GitHub's own `deployment` mapping key (empirical basis item
3), not pipeline logic. The documented trade-off (custom App-based
protection rules require the deployment object to function, so they stop
working when suppressed) belongs to the implementation-stage documentation
update (FR-012), not to this contract's binding mechanism, which is
unaffected either way.

## Per-job, per-stage-call granularity (FR-004, User Story 4)

Binding applies uniformly to every job in a stage file — there is no
per-job internal selector. Adopters who want to gate only some invocations
of a multi-call stage (the motivating case: `tasks.yml`, called once with
`mode: generate` — runs an agent — and once with `mode: approved` —
agent-free) achieve that by setting `environment` on only the call(s) they
want gated; this requires no change to the stage's own logic (research D7).

## Lifecycle reporting (FR-009)

No change to any lifecycle-issue reporting path. A job pending environment
approval has not reached GitHub's `completed` state, so
`workflow_run: [completed]`-triggered reporting (this repo's own watchdog
wrapper, and any adopter-built equivalent) structurally cannot see, and
therefore cannot misreport, a pending gate as a stage failure (research D5).

## Ambient-state prohibition (FR-011, constitution VII)

`environment` and `environment-deployment` are the sole source of the
binding. No stage supplies a default environment name, looks one up from a
repository variable (`vars.*`), or otherwise derives it from ambient
repository state — both values arrive exclusively as `workflow_call` inputs,
set only by the calling wrapper's own `with:` block, exactly like every
other trusted configuration input this pipeline already exposes (`model`,
`max-turns`, `pipeline-repo`).

## Traceability (FR-013)

Every occurrence of the `environment:` block added to a stage workflow file
carries a comment pointing back to
[charlesguse/wc-env-probe](https://github.com/charlesguse/wc-env-probe)
(verified 2026-08-05), so a silent upstream change to any of the four
empirical behaviors above is detectable rather than discovered as an
unexplained regression.

## Non-goals (unchanged from the spec's Out of Scope section, restated for
this contract's boundary)

- **Environment secrets.** The stage's secret contract is kebab-case
  (`anthropic-api-key`, `speckit-app-private-key`); GitHub environment-secret
  names cannot contain hyphens, so the stage's declared secrets can never
  *be* environment secrets. An adopter's wrapper resolves `secrets.*` in the
  calling job, which has no environment, so an environment-scoped credential
  resolves empty and preflight fails with an unrelated-looking "no
  credential" error. This is a documented adopter-facing caveat (FR-012), not
  a code behavior this contract, or any future one, can fix.
- **Validating that the named environment exists, or preventing
  create-on-reference.** Pass-through matches Actions' behavior everywhere
  else; the consequence is documented, not coded around.
- **Reporting "waiting for approval" to the lifecycle issue thread.**
- **Setting `environment.url`.**
- **Any pipeline-side dedup, memory, or short-circuiting of approvals across
  `implement` iterations.** A required reviewer on `implement` prompts once
  per iteration by design (spec edge case); adopters wanting a single
  approval per feature bind a once-per-feature stage (`plan`, or the
  tasks-generate call) instead.
- **Private-repository plan-tier behavior.** Deployment environments in
  private repositories require GitHub Team or Pro; this is a documented
  prerequisite (FR-012), not a code behavior — the probe repo above is
  public, and private-plan behavior is confirmed separately per the spec's
  Assumptions.
