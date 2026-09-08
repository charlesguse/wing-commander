# Quickstart: Validating Private-Image Credentials Reach Every Stage Job

This feature's validation splits into two kinds of scenario: the two
blocking live-runner probes (FR-016/User Story 5) that must run — and be
recorded in `research.md` — before any stage file is touched, and the
downstream scenarios from the spec's own Independent Test vehicles that
confirm the shipped feature once those probes have picked a mechanism. See
`contracts/private-registry-credentials.md` for the full interface and
`data-model.md` for field-level notes.

## Prerequisites

- A scratch GitHub repository that can dispatch a throwaway
  `workflow_dispatch` workflow on real GitHub-hosted runners (mirrors PR
  #226's method for specs/038's own probe).
- For Scenarios 6–10: that scratch repository able to call this pipeline's
  stages by `uses:`, with access to a private container registry (a
  repository-scoped GHCR package needs no extra setup beyond `packages:
  read`; a cloud registry needs the adopter's own OIDC-trusted role).
- A checkout of this repository on the feature branch with the
  implementation applied (the amended `container.credentials` expression,
  or the FR-026-outcome-2 shape, on every job of all 12 published stages;
  Gate 22 amended; `wing-commander-ecr-credentials`, if P2 passed).

## Probe 1 (P1) — does `container.credentials: {}` suppress the login attempt? (research D3, blocking)

1. In the scratch repository, create a throwaway `workflow_dispatch`
   workflow with one job per row of research D3's probe table (P1.1–P1.5),
   each setting `container.image`/`container.credentials` to the exact
   expression under test.
2. Dispatch it. Record the run URL.
3. **Expected outcomes and what they decide**: see research D3's "Decision
   tree." At minimum, confirm P1.2 (public image, `credentials: {}`) either
   runs clean (FR-026 outcome 1 is viable) or fails (outcome 1 is closed;
   proceed to the outcome-2/outcome-3 branch research D3 describes).
4. Record the run URL and the exact observed behavior for each row in
   `research.md`, replacing the "Blocking prerequisite for tasks.md"
   section. Delete the throwaway workflow — it is never merged as a
   permanent file, mirroring PR #226's own discipline.

## Probe 2 (P2) — does a masked cross-job hand-off stay masked? (research D4, blocking)

1. In the same or a second throwaway `workflow_dispatch` workflow, create
   job A (mints a known dummy token, masks it with `::add-mask::`, sets it
   as a step output) and job B (`needs: A`, consumes
   `needs.A.outputs.token`) per research D4's P2.1/P2.2.
2. Dispatch it. Download the raw job logs via the run's own API/artifact —
   not just the rendered UI — and search for the literal dummy token value
   in both jobs' logs, and (for P2.2) in a minimal test stage's log that
   the token was forwarded into as a `secrets:` value.
3. **Expected**: the literal value appears nowhere. If it does, `wing-
   commander-ecr-credentials` (FR-013) does not ship until a masked-safe
   hand-off shape is found and re-probed.
4. Record the run URL and the search result in `research.md`. Delete the
   throwaway workflow.

## Scenario 1 — Default path is unchanged (Story 2, SC-002)

1. Invoke any stage (e.g. `plan.yml`) as today, with neither credential
   secret set and no image named.
2. **Expected**: identical behavior to before this feature — no container,
   no login attempt, no new failure, warning, or artifact.

## Scenario 2 — Public image, no credentials (Story 2 acceptance scenario 2, FR-005)

1. Call a stage with `container-image` set to a public image and neither
   credential secret set.
2. **Expected**: every job runs inside the image; no login is attempted;
   nothing fails for want of a credential. This is the scenario Probe 1's
   P1.2 exists to de-risk before this is ever run for real.

## Scenario 3 — Credentials supplied, no image named (Edge Case, FR-006)

1. Set both credential secrets on a stage call that names no image.
2. **Expected**: entirely inert — no login attempt, no warning, no behavior
   change of any kind.

## Scenario 4 — Private image with static credentials, every job authenticates (Story 1, SC-001, SC-004)

1. Set up a private image in a registry reachable by username/password (or
   the repository-scoped-token example, research D9).
2. Call a stage with `container-image` set to that image and both
   credential secrets set.
3. **Expected**: every job of the stage — not only
   `verify-image-prerequisites` — pulls and runs inside the image; the
   credential value appears nowhere in logs or job configuration; the stage
   completes with zero pipeline file edits, zero forks, no self-hosted
   runner (SC-001).

## Scenario 5 — Only one credential supplied (Edge Case, FR-007)

1. Call a stage with `container-image` set and only one of the two
   credential secrets set.
2. **Expected**: `verify-image-prerequisites` fails fast, naming which
   secret is missing, before any agent cost — not a per-job registry error
   and not a half-attempted login.

## Scenario 6 — Cloud-registry token-based credential via the ECR adapter (Story 3, SC-004; requires P2 to have passed)

1. In the scratch repository's own wrapper, add a `mint-ecr-credentials` job
   using `wing-commander-ecr-credentials` (contracts document) with a role
   the scratch repository's OIDC identity can assume.
2. Call a stage from a sibling job, forwarding
   `needs.mint-ecr-credentials.outputs.username`/`.password` as the two
   secrets.
3. **Expected**: the stage pulls the private ECR image and completes with
   no long-lived registry secret stored anywhere, and the token value
   appears in no workflow file, log, or job configuration — the real,
   end-to-end version of what Probe 2 already checked in isolation.

## Scenario 7 — Repository-scoped-token worked example (Story 7, research D9)

1. Follow `docs/adoption.md`'s worked example verbatim: `container-image:
   ghcr.io/<owner>/<private-package>`, `container-registry-username:
   secrets.WING_COMMANDER_CONTAINER_REGISTRY_USERNAME`,
   `container-registry-password:
   secrets.WING_COMMANDER_CONTAINER_REGISTRY_PASSWORD` — a personal access
   token with `read:packages` scope, stored as the repository's own
   secrets. `github.actor`/`secrets.GITHUB_TOKEN` does **not** work for this
   shape: the token's scope is fixed by the calling job's permissions, and a
   job whose only step is a reusable-workflow `uses:` call never carries
   that grant into the pull that happens inside the callee's own job
   (research D9/D10).
2. **Expected**: a reader following the documentation alone reaches a
   working private-image run with no adapter and no extra wrapper job
   (SC-008).

## Scenario 8 — Cross-file consistency (mechanically verifiable in this repository)

1. Grep all 12 published stage files for the amended `container.credentials`
   expression (or the FR-026-outcome-2 shape, whichever shipped).
2. **Expected**: every job with no local `uses:` carries the identical
   expression, forwarding both secrets verbatim (FR-008).
3. Run Gate 22 (`lint-workflows.yml`) over the changed files — must pass,
   and its self-test (`verify-gate-22.py`) must demonstrate the gate
   actually fails against each new synthetic defect fixture (FR-020),
   including a fixture that regresses to the pre-044 bare `image:`-only
   shape.
4. Introduce a stage job that carries the container binding but not the
   credential binding, and confirm Gate 22 fails, naming the stage file and
   job (Story 6 acceptance scenario 1). Restore it and confirm the gate
   passes again.

## Scenario 9 — This repository's own dogfood check (Story 7 analog, FR-027, SC-010)

1. Trigger the new dogfood workflow (research D10) on demand.
2. **Expected**: it pulls the private GHCR package scoped to this
   repository, through the same `container.credentials` shape adopters use,
   authenticated with this repository's own workflow token — no cloud
   account or cloud-registry identity involved, and no lifecycle stage
   moved off the no-image default.
3. Confirm it also runs on its schedule (inspect the workflow's `on:`
   block and, once it has run at least once on schedule, `gh run list`
   filtered to it).

## Scenario 10 — Documentation no longer claims the old limitation (Story 7, SC-009)

1. Read `docs/adoption.md`'s image-prerequisites section and every stage's
   `verify-image-prerequisites` job output after this feature ships.
2. **Expected**: no statement remains claiming registry credentials reach
   only the prerequisite check (contingent on P1 confirming FR-026 outcome
   1 or 2 shipped — if outcome 3 was measured instead, the documentation
   states the limitation still holds, now citing this feature's own
   evidence rather than #227's, per research D6).

## Out of scope for this repository's own validation

- The two live-runner probes themselves (P1, P2) require a scratch
  repository — this repository's own CI cannot dispatch and observe them
  from inside a PR check.
- Real cloud-registry pulls (Scenario 6) and real self-hosted-runner
  scenarios — validated in a scratch adopter repository, per the spec's own
  Independent Test vehicles.
- Per-job credential selection, multi-registry pulls, and credential
  lifecycle management — explicit non-goals
  (`contracts/private-registry-credentials.md`).
