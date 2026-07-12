# Quickstart: Validating the Reusable Pipeline Extraction

Runnable scenarios proving the feature end-to-end. Interface details live in
[contracts/stage-interfaces.md](contracts/stage-interfaces.md); credential
rules in [contracts/credentials.md](contracts/credentials.md); tag rules in
[contracts/versioning.md](contracts/versioning.md).

## Prerequisites (all scenarios)

- A test repository (fresh, or a scratch repo you can reset) on github.com.
- `specify init` run in the test repository (spec-kit v0.12.4, `--integration
  claude --script sh`), plus a constitution via `/speckit-constitution`.
- A dedicated GitHub App installed on the test repository (per docs/setup.md),
  with `speckit-app-id` / `speckit-app-private-key` secrets set.
- A Claude credential: `claude-code-oauth-token` (subscription) — the OAuth-only
  configuration is the verified path (spec clarification).

## Scenario 1 — Full adoption in a fresh repository (US1, SC-001)

1. Start a timer. Follow only `docs/adoption.md` from its first line.
2. Copy the minimal full-pipeline wrapper set from the doc into
   `.github/workflows/` of the test repo, pinned `@v1` (or `@main` pre-release).
3. Create labels and secrets exactly as the doc says.
4. Open an issue describing a small feature; apply the approval label.

**Expected**: a spec PR appears, built from the *test repo's own* templates and
constitution; issue is labeled `spec:NNN-slug` + `stage:spec`; nothing in the
PR originates from the publishing repository (acceptance 1.1); elapsed time
under 60 minutes (SC-001).

## Scenario 2 — Single-stage adoption with a custom trigger (US2, SC-002)

1. In the test repo, delete all wrappers except one that calls
   `reusable-plan.yml`, and retrigger it with a custom event of your choice
   (e.g., `workflow_dispatch` with a `slug` input) — no other stage, label, or
   lifecycle convention present.
2. Place a hand-written `specs/NNN-slug/spec.md` + `spec-meta.json` on the
   default branch; dispatch the wrapper.

**Expected**: plan PR opens targeting `spec/NNN-slug`; no failure caused by any
missing sibling stage or label (acceptance 2.1, 2.3). Repeat spirit-check for
each stage per its contract preconditions (SC-002 claims 100% of stages).

## Scenario 3 — Credential preflight (US4, SC-005, FR-004)

1. In the test repo, remove **both** Claude credential secrets from the wrapper
   wiring; trigger any agent stage.

**Expected**: run fails in the preflight step, before any agent step, naming
`claude-code-oauth-token` and `anthropic-api-key` (acceptance 4.3). The run's
metrics summary shows zero agent cost.

2. Restore only the OAuth token; retrigger. **Expected**: stage completes
   (acceptance 4.1). *(API-key-only runtime verification is deferred to adopter
   feedback per spec clarification; verify by review that both action inputs
   are wired and preflight accepts API-key-only.)*

## Scenario 4 — Missing prerequisites fail with guidance (FR-009)

1. In a repo **without** `specify init` output, wire one wrapper and trigger it.
   **Expected**: deterministic failure naming the missing `.specify/` /
   skills and pointing to the prerequisite step — not a mid-run agent error.
2. Dispatch the tasks stage for a slug whose `spec-meta.json.stage` is not
   `plan`. **Expected**: refusal naming the plan stage as the missing
   predecessor (edge case 4).

## Scenario 5 — Publisher dogfooding & zero duplication (US3, SC-003, SC-004)

1. Inspect this repository:
   `grep -L "workflow_call" .github/workflows/speckit-*.yml` — every
   `speckit-*` wrapper must contain a `uses: ./.github/workflows/reusable-*.yml`
   job and **no stage logic** (agent prompts, branch surgery, meta writes).
2. Run one full lifecycle here (open issue → label → merge through).
   **Expected**: every stage job executes inside a `reusable-*` called workflow
   (visible in the run's job names as `wrapper / stage`), i.e., the same
   interface adopters call (acceptance 3.1).
3. Make a trivial stage-logic edit; confirm it lands in exactly one file
   (`reusable-*.yml` or a composite), and reaches the test repo by moving its
   pin only (acceptance 3.2, SC-004).

## Scenario 6 — Version pinning and floating tag (FR-008)

1. Pin the test repo's wrappers to exact tag `vX.Y.Z`; publish a new
   non-breaking release. **Expected**: test repo behavior unchanged until the
   pin is edited (edge case 2).
2. Switch the test repo to `@v1`; publish another non-breaking release.
   **Expected**: next run picks up the fix with zero changes in the test repo
   (acceptance 1.2).
3. Inspect the release notes. **Expected**: an explicit Breaking-changes
   section exists (even if "none").
