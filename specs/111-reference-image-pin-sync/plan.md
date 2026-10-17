# Implementation Plan: Reference-Image Pin Sync on Rebuild

**Branch**: `spec/111-reference-image-pin-sync` | **Date**: 2026-10-11 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/111-reference-image-pin-sync/spec.md`

## Summary

After `wing-commander-e2e-reference-image.yml` builds and publishes a new
digest, and only after both the image prerequisite check and the agent
start-up check (spec 112) have passed on that digest, a new `sync-pins` job
writes `WING_COMMANDER_CONTAINER_IMAGE=<image>@<digest>` to this repository
and to `WING_COMMANDER_AUTO_RELEASE_E2E_REPO`. It uses a dedicated
Variables-write token, checks at run time that the token reaches exactly the
sync set, skips pins already current, serialises concurrent builds, writes a
per-repository outcome table to the job summary, and on any failure fails the
run and files or updates one deduplicated tracked issue. The logic lives in
one shared script; auto-release is untouched.

## Technical Context

**Language/Version**: Bash + jq in GitHub Actions (ubuntu-latest); Python 3 for `verify-*.py` gates

**Primary Dependencies**: `gh` CLI, existing `wing-commander-durable-failure-issue` composite, `wing-commander-private-image-dogfood.yml` start-up check dispatch (spec 112)

**Storage**: Repository Actions variables (`WING_COMMANDER_CONTAINER_IMAGE`); a new secret for the token

**Testing**: A fixture-driven `verify-reference-image-pin-sync.py` gate that runs the script against a stubbed `gh`; run via `python .github/scripts/run-local-gates.py`; post-merge proof by re-driving one build (`prove-after-merge`)

**Target Platform**: GitHub Actions only

**Project Type**: Workflow tooling (wing-commander's own maintenance, not a published stage)

**Performance Goals**: N/A (adds the start-up check's wait time to one job)

**Constraints**: Token never printed; write only the one variable on only the sync set; no adopter-facing surface (FR-012); auto-release unchanged (FR-009)

**Scale/Scope**: Two repositories, one variable, one workflow file plus one script, one gate, doc edits

## Constitution Check

*Pre-design: PASS. Post-design: PASS.*

- I Guide / VII Two Interfaces: the sync is the consuming-instrument category (own maintenance tooling), no `workflow_call`, no adopter surface. PASS.
- III GitHub-native, IV Automation-first: removes a manual step, uses only Actions, variables and issues. PASS.
- V Security: the token is a masked secret used for nothing else; the containment check refuses to write on over-reach; digest and repository names come from step outputs and are validated by regex before use, never interpolated into shell. PASS.
- VIII A green check means what it says: a failed sync fails the run and files an issue; "already current" and "skipped" are reported distinctly. PASS.
- IX Deterministic code gates durable actions: the decision to write is a script with fixture tests, no model judgment. PASS.
- X Bounded autonomy: the write is confined to one variable on two named repositories. PASS.
- Shared logic one home (CLAUDE.md): sync logic in one workflow step; failure filing reuses the existing composite; a gate checks no copy appears elsewhere. PASS.

No violations; Complexity Tracking is empty.

## Project Structure

### Documentation (this feature)

```text
specs/111-reference-image-pin-sync/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── pin-sync-script.md
└── tasks.md             # tasks stage
```

### Source Code (repository root)

```text
.github/
├── workflows/
│   ├── wing-commander-e2e-reference-image.yml   # startup-check waits for verdict; new sync-pins job whose sync step is the single home of the write; header comment
│   └── lint-workflows.yml                       # register the new gate
└── scripts/
    ├── verify-reference-image-pin-sync.py       # fixture gate: script behaviour + workflow wiring + single-home
    └── tests/reference-image-pin-sync/          # stubbed-gh fixtures
docs/setup.md                                    # WING_COMMANDER_CONTAINER_IMAGE row + new secret row
```

**Structure Decision**: One new job in the existing build workflow whose sync
step carries the logic inline, so Gate 12 can resolve each `gh` call's token
(it rejects `gh` calls inside `.github/actions/_shared/` scripts); the
fixture gate runs that block verbatim. No new composite is needed because
there is one call site.

## Complexity Tracking

None.
