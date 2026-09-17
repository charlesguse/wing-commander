# Implementation Plan: On-demand E2E scratch repository provisioning

**Branch**: `053-e2e-scratch-provisioning` | **Date**: 2026-09-17 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/053-e2e-scratch-provisioning/spec.md`

## Summary

Both `auto-release.yml`'s `verify-e2e` job and `auto-update-spec-kit.yml`'s
`e2e-stage` need a second GitHub repository that only a human can create
today, because no App installation token in this repository is allowed to
create or delete a repository (`docs/setup.md`, Constitution VI/VII). This
feature adds one local, maintainer-run entry point —
`.github/scripts/provision-e2e-target.sh` — that performs every onboarding
element of either target profile it can perform under the maintainer's own
`repo`-scoped `gh` authentication (repository creation, Claude credential
secret, `spec-request` label, wrapper workflow set, pinned container image
variable), verifies every element deterministically, and reports the App
installation as the one remaining manual step for as long as it is absent.
The same deterministic element-checking code is shared with a generalized,
workflow-dispatchable readiness check (extending
`auto-update-spec-kit-scratch-preflight.yml` in place to cover both profiles)
so a maintainer or agent can ask "is this target ready?" for zero Claude
quota and about one runner-minute, exactly like the existing single-element
preflight does today. Neither `auto-release.yml`'s nor `e2e-stage`'s own
per-run reset/scaffold behaviour changes, and no App installation token
gains any new permission.

## Technical Context

**Language/Version**: Bash (POSIX-oriented, `bash` 5.x as already assumed by
every live-`gh`-calling script in `.github/scripts/`, e.g.
`verify-watchdog-run.sh`) for the entry point and the shared onboarding
library; Python 3 for the new static "single home" gate, matching the
existing `verify-*.py` / bash split documented in research.md.

**Primary Dependencies**: GitHub CLI (`gh`, already the repository's sole
convention for live GitHub API access — no PyGithub, no raw REST), `jq` for
JSON report construction, `actions/create-github-app-token@v3` (already
vendored, used by the generalized readiness-check workflow to mint the
read-only check's App token exactly as `auto-update-spec-kit-scratch-preflight.yml`
does today).

**Storage**: N/A. Provisioning holds no state of its own; every fact it
needs to converge on ("is this already done?") is read back from the target
repository itself (its variables, secrets index, labels, workflow files,
description).

**Testing**: A new `.github/scripts/e2e-provisioning-tests/` bash harness
following the existing `auto-update-spec-kit-tests/` convention (`gh_stub.py`
to stub `gh` calls, `tN_*.sh` per scenario, a `run-tests.sh` entry point) —
covering re-run idempotency (FR-005), self-target refusal (FR-007), the
not-ready/named-remaining-action path (FR-006), and the "no `repo create` /
`repo delete` call from the App-token-scoped surface" assertion this
repository already makes for the scratch profile in `t4_verify.sh`, extended
to the new script's own App-token-scoped half (the readiness-check workflow).
The new Python gate gets a `--self-test` fixture per Constitution VIII.

**Target Platform**: a maintainer's or agent session's local POSIX shell
(macOS/Linux) with an authenticated `gh` for the provisioning entry point
(FR-014); GitHub Actions `ubuntu-latest` for the generalized read-only
readiness-check workflow.

**Project Type**: Tooling addition inside this repository's own "consuming
instrument" layer (Constitution VII) — `.github/scripts/` and one
`wing-commander-*.yml`-style wrapper workflow. No published `<stage>.yml`
contract is touched, widened, or versioned by this feature.

**Performance Goals**: SC-006 — a readiness check costs zero Claude quota
and ≤1 runner-minute, matching the cost of today's single-element preflight.

**Constraints**: SC-001 — one provisioning invocation, the one declared
manual App-install step, and one re-invocation complete in under 15 minutes
wall-clock. FR-003/FR-009 — no App installation token gains a new
permission; no credential value is ever written to a log, summary, commit,
issue comment, or PR body.

**Scale/Scope**: two target profiles (`auto-release`, `spec-kit-scratch`),
at most six onboarding elements total, one maintainer-operated tool — no
concurrency or multi-tenant concerns.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Guide**: This feature is itself dogfooded through the pipeline (issue
  #362, spec 053, this plan). Once implemented, provisioning a fresh
  `auto-release` target *is* the worked example `docs/adoption.md` and
  `docs/setup.md` already promise. Pass.
- **II. Cost-Conscious Model Tiering**: N/A to the delivered artifacts — the
  provisioning script and readiness-check workflow invoke no Claude step of
  their own (FR-013's "unattended" and User Story 2's "zero Claude quota"
  are the point). The spec/plan/tasks stages that produced this feature
  already ran under their own tiering. Pass (N/A).
- **III. Simple, GitHub-Native Interaction**: N/A — this feature is
  maintainer/agent-operated infrastructure tooling, not a pipeline-facing
  interaction surface a requester uses; it has no issue/comment lifecycle of
  its own. Pass (N/A), noted rather than silently skipped per the
  principle's own spirit.
- **IV. Automation-First**: The one manual step that survives (App
  installation) is reported explicitly by the readiness report on every
  invocation for as long as it is absent (FR-006, FR-015) — never silently
  assumed. Pass.
- **V. Security**: No issue/comment content is parsed by this feature, so
  the untrusted-content rule does not apply directly; its credential
  handling extends the same least-privilege posture — FR-003 forbids
  widening any App installation token, FR-009 forbids ever emitting a
  credential value, and the privileged half runs under a human's own
  authentication that this repository never stores (FR-014). Pass.
- **VI. Portability**: The new script and workflow are this repository's
  own tooling for maintaining its own E2E infrastructure, not part of what
  an adopting repository's `specify init` pulls in — they belong beside
  `run-local-gates.py`, not beside the published stages. Pass.
- **VII. Two Interfaces**: The generalized readiness-check workflow is a
  `wing-commander-*.yml`-style wrapper (consuming instrument, free to
  change) — not a `workflow_call`-only published stage — because it is
  specific to this repository's own E2E targets, not a capability offered to
  adopters. No `<stage>.yml` input, secret, or output changes. Pass.
- **VIII. A Green Check Means What It Says**: The new single-home gate
  (SC-007) must be gate-registry-reachable, self-testable, and triggered by
  changes to the files it scans, following `verify-spec-meta-single-home.py`
  exactly. Recorded as a Phase 1 design obligation, not yet built. Pass
  (planned).
- **IX. Judgment That Gates a Durable Action Belongs in Deterministic Code**:
  This is the feature's central design constraint (FR-008) — the readiness
  verdict is computed once, in a shared onboarding-element library, and both
  the local provisioning entry point and the CI readiness-check workflow
  call the same functions rather than each re-deriving the answer. Pass.

No violations requiring justification. Complexity Tracking is not used.

## Project Structure

### Documentation (this feature)

```text
specs/053-e2e-scratch-provisioning/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   ├── cli.md
│   ├── readiness-report.schema.json
│   └── readiness-workflow.md
└── tasks.md             # Phase 2 output (/speckit-tasks — not created here)
```

### Source Code (repository root)

```text
.github/scripts/
├── e2e-provisioning/
│   ├── profiles.sh            # FR-010: the two TargetProfile definitions
│   │                          # (auto-release, spec-kit-scratch) as data,
│   │                          # not two copies of the checking code
│   └── checks.sh              # FR-008: one deterministic check function per
│                               # OnboardingElement, sourced by both the
│                               # local entry point and the CI workflow below
├── provision-e2e-target.sh    # FR-001/FR-014: the single documented,
│                               # maintainer-run entry point; performs the
│                               # privileged half locally, then sources
│                               # e2e-provisioning/checks.sh for the report
├── verify-e2e-provisioning-single-home.py   # SC-007 gate (Constitution VIII)
└── e2e-provisioning-tests/    # bash test harness, gh_stub.py convention,
                                # mirrors auto-update-spec-kit-tests/

.github/workflows/
└── auto-update-spec-kit-scratch-preflight.yml
    # generalized in place (User Story 2): gains a `profile` input
    # (default preserves today's single-scratch-repo behaviour), sources
    # .github/scripts/e2e-provisioning/checks.sh instead of re-deriving the
    # split/mint/reachability logic inline — see research.md for why this is
    # extended rather than replaced by a second dispatcher

docs/
├── setup.md      # FR-012: the two pre-created-repository rows point at
│                  # provision-e2e-target.sh instead of "create one by hand"
└── adoption.md   # FR-012: onboarding walkthrough gains a pointer to the
                   # same entry point for the auto-release profile
```

**Structure Decision**: Single-project tooling addition, entirely inside
this repository's existing `.github/scripts/` (Bash entry point + shared
library + Python gate + bash test harness) and `.github/workflows/`
(one generalized wrapper-style workflow) layout — no new top-level
directory, no new language, no new runtime dependency beyond what
`.github/scripts/` and `.github/workflows/` already use throughout this
repository.

## Complexity Tracking

*No Constitution Check violations. Table intentionally empty.*
