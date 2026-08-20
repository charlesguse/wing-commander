# Quickstart: Validating Runner and Container Passthrough

Per the spec's own Independent Test vehicles, most scenarios below require a
scratch adopter repository — a self-hosted runner, a real container pull,
and real registry credentials are all live, cross-system interactions this
repository's own CI cannot exercise. This quickstart covers what **is**
validated in this repository (correct plumbing, cross-file consistency) and
what requires a scratch repository. See
`contracts/runner-container-passthrough.md` for the full interface and
`data-model.md` for field-level notes.

## Prerequisites

- A checkout of this repository on the feature branch with the
  implementation applied (new `runner`/`container-image` inputs, the two
  registry-credential secrets, the `runs-on:`/`container:` block on every
  job of all eleven published stages, and the `verify-image-prerequisites`
  job per stage — see `contracts/runner-container-passthrough.md`).
- For the manual scenarios: a scratch GitHub repository that can call this
  pipeline's stages by `uses:`, with a registered self-hosted runner (for
  Scenarios 3–4) and access to a private container registry (for Scenarios
  6–8).

## Scenario 1 — Default path is unchanged (Story 2, SC-002)

1. Invoke any stage (e.g. `plan.yml`) as today, with `runner` and
   `container-image` left unset.
2. **Expected**: identical behavior to before this feature — the job runs on
   `ubuntu-latest`, `verify-image-prerequisites` is skipped (not run, not
   failed), no container step appears in the job log, and every subsequent
   step runs exactly as it does today.

## Scenario 2 — Cross-stage consistency (mechanically verifiable in this repo)

1. Grep all eleven stage workflow files (`intake`, `clarify`, `plan`,
   `tasks`, `implement`, `finalize`, `cleanup`, `watchdog`,
   `pr-conversation`, `rebase`, `auto-update-spec-kit`) for `runner:`,
   `container-image:`, `inputs.runner`, `inputs.container-image`, and
   `verify-image-prerequisites`.
2. **Expected**: every file declares both `workflow_call` inputs and both
   secrets with the documented names/types/defaults; every job with no local
   `uses:` carries the identical `runs-on:`/`container:` block; every file
   declares `verify-image-prerequisites`; every entry job depends on it with
   a skip-tolerant `if:` (FR-007, FR-014).
3. Run Gate 22 and Gate 23 (`lint-workflows.yml`) over the changed files —
   must pass, and their self-tests
   (`.github/scripts/verify-gate-22.py`/`verify-gate-23.py`) must
   demonstrate the gates actually fail against a synthetic defect.
4. Run the pinned `actionlint` (1.7.7, matching `release.yml` Gate 1a) over
   all eleven files. **Expected**: no new diagnostics — unlike specs/031's
   `environment.deployment` key, `container:`/`image:`/`credentials:` are
   standard, long-published Actions workflow-syntax keys (research
   Testing note); any diagnostic here is a real finding, not an accepted
   schema gap.
5. Run `.github/workflows/lint-workflows.yml`'s YAML-parse + `bash -n` check
   over the changed files and the new `verify-image-prerequisites` steps —
   must pass.

## Scenario 3 — Single-label runner selection (Story 1, SC-001; manual, scratch repo)

1. In the scratch repository, register a runner (or use a larger
   GitHub-hosted runner label).
2. Call a stage (e.g. `plan.yml`) with `with: runner: <that label>`.
3. **Expected**: the job is scheduled on that runner and the stage completes
   exactly as it would on the default runner.

## Scenario 4 — Multi-label conjunction (Story 1 acceptance scenario 2; manual, scratch repo)

1. Register a self-hosted runner carrying labels `self-hosted`, `linux`,
   `x64` (or a subset you control).
2. Call a stage with `with: runner: '["self-hosted","linux","x64"]'`.
3. **Expected**: the job is scheduled only on a runner carrying every named
   label — not one carrying only the first. This is also the scenario that
   closes research D2's open verification gap: confirm the
   `startsWith(...) && fromJSON(...) || ...` expression evaluates the
   JSON-array form correctly before relying on it elsewhere.

## Scenario 5 — Unregistered label is passed through (Story 1 acceptance scenario 3; manual, scratch repo)

1. Call a stage with `with: runner: no-runner-carries-this-label`.
2. **Expected**: GitHub queues the job per its own behavior (it will sit
   queued/never pick up) — no pipeline-side validation, allowlist, or
   pre-existence check runs or fails first (FR-008).

## Scenario 6 — Public image, no container step visible when unset elsewhere (Story 3; manual, scratch repo)

1. Call a stage with `with: container-image: <a public image reference,
   e.g. node:20>`.
2. **Expected**: `verify-image-prerequisites` runs, pulls the image, and (if
   it lacks a required tool from the canonical list) fails naming every
   missing tool at once; if it has every tool, every job in the stage
   executes its steps inside that image.
3. This scenario is also the one that closes research D3's open
   verification gap: confirm the *unset* case (a separate run, `container-
   image` left empty) produces genuinely no container — no image pulled,
   no container created, no container-related step in the log — before
   treating User Story 2's zero-change guarantee as proven rather than
   assumed.

## Scenario 7 — Image missing a required tool fails fast, before any agent cost (Story 3 acceptance scenario 2, SC-005; manual, scratch repo)

1. Call a stage with `with: container-image:` set to a minimal image known
   to lack at least one canonical tool (e.g. an image with no `jq`).
2. **Expected**: `verify-image-prerequisites` fails, naming every missing
   tool in one message, before any agent-bearing job's own container is
   created and before any agent cost is incurred.

## Scenario 8 — Private image with static credentials (Story 4, SC-004; manual, scratch repo)

1. Set up a private image in a registry reachable by username/password.
2. Call a stage with `container-image` set to that image and
   `secrets: container-registry-username/password` set to repository
   secrets holding the credential pair.
3. **Expected**: `verify-image-prerequisites` pulls successfully, the real
   containerized job(s) pull and run successfully, and neither credential
   value appears anywhere in the run's logs or job configuration (verify by
   inspecting the raw log text, not just the rendered UI, since GitHub's
   masking is what's being relied on here).

## Scenario 9 — Private image, no credentials supplied (Story 4 acceptance scenario 2, FR-010; manual, scratch repo)

1. Call a stage with `container-image` set to the same private image as
   Scenario 8, but leave both credential secrets unset.
2. **Expected**: `verify-image-prerequisites` fails with a message
   identifying the missing credential as the cause (not only the registry's
   raw "unauthorized" error) — the one thing this design can add beyond
   GitHub's own pull failure (research D4/D5).

## Scenario 10 — Cloud-registry token-based credential (Story 4 acceptance scenario 4, FR-009a; manual, scratch repo)

1. In the scratch repository's own wrapper job (not the stage), mint a
   short-lived registry token (e.g. via an ECR login action) before the
   `uses:` call to the stage.
2. Pass the minted token as `secrets.container-registry-password` (and the
   registry's expected fixed username, if any, as
   `container-registry-username`).
3. **Expected**: the stage pulls successfully with no code change to the
   published stage itself — confirming the same credential mechanism serves
   both static pairs (Scenario 8) and minted tokens with no fork (FR-009a).

## Scenario 11 — Per-stage-call granularity via `tasks.yml`'s two calls (Story 4 analog of specs/031 Story 4; manual or inspection)

1. In a wrapper that calls `tasks.yml` twice (mirroring this repository's
   own `wing-commander-4-tasks.yml`: once with `mode: generate`, once with
   `mode: approved`), set `runner`/`container-image` on only the `generate`
   call.
2. **Expected**: only the `generate` call's job(s) run on the chosen
   runner/image; the `approved` call runs on the default.

## Scenario 12 — This repository's own dogfooded configuration (Story 6; manual or inspection)

1. Set `WING_COMMANDER_RUNNER`/`WING_COMMANDER_CONTAINER_IMAGE` repository
   variables (and the two credential secrets, if needed) in this
   repository's own Settings.
2. Trigger a stage through its `wing-commander-*.yml` wrapper.
3. **Expected**: the stage's jobs run on the configured selection, with no
   workflow file edited. Unset the variables and confirm the run returns to
   `ubuntu-latest`/no container.

## Out of scope for this repository's validation

- Live runner-scheduling and container-pull behavior itself (Scenarios
  3–10) — GitHub's/Docker's own mechanics, validated in the scratch adopter
  repository, not re-derived here.
- Runner groups, non-Linux runners, per-job targeting, and the remaining
  container settings (volumes, ports, env, extra options, service
  containers) — explicit non-goals (contracts/runner-container-passthrough.md).
