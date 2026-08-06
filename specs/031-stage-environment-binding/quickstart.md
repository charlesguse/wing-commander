# Quickstart: Validating Deployment Environment Binding

Per the spec's own Assumptions, the protection-rule scenarios (required
reviewer, wait timer, branch policy) cannot be exercised in this
repository's CI — GitHub deployment-environment approval is a live,
cross-actor interaction. This quickstart covers what **is** validated in
this repository (correct plumbing of `environment`/`environment-deployment`
and that existing behavior is unchanged) and what requires a scratch adopter
repository, per the spec's stated acceptance vehicle. See
`contracts/environment-binding.md` for the full interface and
`data-model.md` for field-level notes.

## Prerequisites

- A checkout of this repository on the feature branch with the
  implementation applied (new `environment`/`environment-deployment` inputs
  and the `environment:` mapping block on every job of all ten published
  stage workflows — see `contracts/environment-binding.md`).
- For the manual scenarios only: a scratch **public** GitHub repository
  (private repos need GitHub Team/Pro — spec edge case) that can call this
  pipeline's stages by `uses:`, with permission to create deployment
  environments in its own Settings.

## Scenario 1 — Default path is unchanged (Story 2, SC-001)

1. Invoke any stage (e.g. `plan.yml`) as today, with `environment` and
   `environment-deployment` left unset.
2. **Expected**: identical behavior to before this feature — no environment
   applied, no gate, no deployment record, and no environment created
   anywhere in the calling repository's settings. Preflight and every
   subsequent step run exactly as they do today.

## Scenario 2 — Cross-stage consistency (mechanically verifiable in this repo)

1. Grep all ten stage workflow files
   (`intake,clarify,plan,tasks,implement,finalize,cleanup,rebase,watchdog,
   auto-update-spec-kit`) for `environment:`, `inputs.environment`, and
   `inputs.environment-deployment`.
2. **Expected**: every file declares both `workflow_call` inputs with the
   documented names/types/defaults, and every job in every file carries the
   same `environment: {name: ..., deployment: ...}` block — no stage is
   missing the surface, no job within a multi-job stage is skipped (FR-004).
3. Run `.github/workflows/lint-workflows.yml`'s checks (YAML-parse +
   `bash -n`) over the changed files — must pass unchanged.
4. Run the pinned `actionlint` (1.7.7, matching `release.yml` Gate 1a) over
   at least the 8 files that gate already covers — confirms the
   `environment:`/`deployment` mapping parses cleanly (research D8 risk); if
   it does not, resolve per research D8's documented fallback before
   considering the change done.

## Scenario 3 — Required reviewer gates the run before any agent cost (Story 1, SC-002; manual, scratch repo)

1. In the scratch repository, create an environment (e.g.
   `wing-commander-agent`) with a required reviewer.
2. Call a stage (e.g. `plan.yml`) with `with: environment:
   wing-commander-agent`.
3. **Expected**: the job enters a pending-approval state before its
   preflight step and before any agent step runs; no agent cost is incurred
   while pending.
4. Approve as the configured reviewer.
5. **Expected**: the stage continues and completes exactly as it would have
   without the environment.

## Scenario 4 — Wait timer (Story 1 acceptance scenario 3; manual, scratch repo)

1. Configure the same environment with a wait timer instead of (or in
   addition to) a required reviewer.
2. Call a stage with `environment` set to it.
3. **Expected**: the job waits the configured time before starting; no agent
   cost is incurred during the wait.

## Scenario 5 — Deployment branch/tag policy (Story 1 acceptance scenario 4; manual, scratch repo)

1. Configure the environment with a deployment branch/tag policy that
   excludes the ref the stage will run from.
2. Call a stage with `environment` set to it, from a violating ref.
3. **Expected**: GitHub blocks the run per its own policy; the pipeline adds
   no check of its own (nothing to grep for — the absence of pipeline-side
   branch-policy logic is itself the expected state).

## Scenario 6 — Deployment-record suppression (Story 3; manual, scratch repo)

1. Bind a stage to an environment with a protection rule (e.g. required
   reviewer), and additionally pass `with: environment-deployment: false`.
2. **Expected**: the reviewer-approval gate still applies exactly as in
   Scenario 3, but no deployment record appears in the repository's
   Deployments/Environments panel.
3. Repeat with `environment-deployment` left at its default (`true`, or
   simply omitted).
4. **Expected**: a deployment record is created.

## Scenario 7 — Create-on-reference for a name that doesn't exist yet (Story 1 edge case, SC-004; manual, scratch repo)

1. Call a stage with `environment` set to a name that does not yet exist in
   the scratch repository's Settings.
2. **Expected**: the environment is created on reference, with no protection
   rules, and the job runs ungated — no validation error, no failure.

## Scenario 8 — Per-job granularity from the wrapper (Story 4; manual or inspection)

1. In a wrapper that calls `tasks.yml` twice (mirroring this repo's own
   `wing-commander-4-tasks.yml`: once with `mode: generate`, once with
   `mode: approved`), set `environment` on only the `generate` call.
2. **Expected**: only the `generate` call's job binds to the environment;
   the `approved` call runs ungated.

## Scenario 9 — Lifecycle issue stays silent while pending (Story 1, SC-006; manual, scratch repo)

1. During Scenario 3's pending window, watch the lifecycle issue this
   pipeline posts status to.
2. **Expected**: no comment appears reporting the pending state as a failure
   or as "waiting for approval" — the lifecycle issue is silent until the
   gate resolves (research D5; this closes the "decision made without
   clarification" gap noted there with a real observation).

## Out of scope for this repository's validation

- Live protection-rule behavior itself (Scenarios 3–7, 9) — GitHub's own
  feature, validated in the scratch adopter repository per the spec's
  Assumptions, not re-derived here.
- Private-repository plan-tier behavior — confirmed separately per the
  spec's Assumptions; not a blocker for this feature.
