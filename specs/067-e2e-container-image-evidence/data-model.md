# Phase 1 Data Model: Container-Mode Evidence in End-to-End Release Verification

This feature extends existing entities (the end-to-end verdict) and
introduces no new persisted storage — every entity below is a shape carried
through step outputs and API responses within a single `auto-release.yml`
run, matching spec.md's Key Entities section.

## Container-Mode Evidence

The two observations that together justify a container-mode `pass`.

| Field | Type | Source | Notes |
|---|---|---|---|
| `configuration.expected_image` | string | This repository's own `WING_COMMANDER_CONTAINER_IMAGE` variable, read via `checks.sh`'s `this_repo_container_image()` (research.md D3) | Read before kickoff |
| `configuration.observed_image` | string \| empty \| unreadable | The test repository's `WING_COMMANDER_CONTAINER_IMAGE` variable, read via `gh variable list --repo "$E2E_REPO"` with the maintainer credential | Absent and empty are both "not configured" (FR-002); distinct from an unreadable read (FR-004) |
| `configuration.observed_at` | timestamp | The `container-evidence-config` step's own execution time | Answers the Edge Case "configuration changes mid-run" — the verdict reports what was observed, and when |
| `execution.run_id` | integer | `needs.detect`/the workflow's own run context passed into the test repository's dispatched run | Identifies which run's job data to read |
| `execution.stage_jobs_containerized` | boolean per stage job, reduced to one boolean | Test repository's Actions Jobs API, `steps[]` presence of `Initialize containers` (research.md D4; unconfirmed pending real-run validation) | Read only after the chain reaches its terminal state, immediately before the `pass` write |
| `execution.observed_at` | timestamp | The `poll` step's own execution time, at its terminal iteration | — |

**Validation rules** (from FR-001/FR-006/FR-007):
- A `pass` MUST NOT be reachable unless both `configuration.observed_image ==
  configuration.expected_image` (non-empty) AND
  `execution.stage_jobs_containerized == true` were both observed.
- `configuration.expected_image` unreadable fails closed (FR-004, FR-007's
  last sentence) — never compared against an empty/absent observed value.
- Absence of either observation (a read that never happened, as opposed to a
  read that returned "unconfigured") MUST NOT be treated as configured
  (FR-001's second sentence).

## End-to-End Verdict (extended)

The existing per-run record; unchanged shape (`specs/054`'s contract, 8
fields via `auto-release-verdict.sh`), with new values in two existing
fields.

| Field | Type | Change in this feature |
|---|---|---|
| `outcome` | enum: `pass`, `fail-infra`, `fail-pipeline`, `fail-gate-stall`, ... | Unchanged set of values. Every new FR-005 failure case uses the existing `fail-infra` value (research.md D5). |
| `verified_head` | string (SHA) | Unchanged. |
| `failing_check` | string | New values added (not a new field): one per FR-005 case (i), (ii), (iv), (v), and the rate-limited variant of (v). Case (iii) keeps its existing value verbatim (FR-005's explicit requirement). |
| `expected` | string | Now carries, for the new cases, either the expected image reference (drift case) or the name of the evidence source that could not be read. |
| `observed` | string | Now carries the empty/absent value, the drifted value, the non-containerized stage job names, or the read failure detail, depending on `failing_check`. |
| `evidence_url` | string | Unchanged in shape; for the new cases, points at the test repository (config case) or the run's Jobs API / Actions UI (execution case), per FR-010. |
| `mode` | enum: `container`, `default-runner` | Unchanged; this feature's checks only ever run when `mode == container` (FR-008). |
| `container_image_configured` | boolean | Unchanged semantics (FR-009): `true` only on FR-005 case (vi); `false` on every other path, including every new case this feature adds. |

## Test Repository Container Image Configuration

The maintainer-set value on the test repository.

| State | Meaning | FR-005 case |
|---|---|---|
| Variable absent | Not configured | (i) |
| Variable present, empty string | Not configured (explicitly, per Edge Cases) | (i) |
| Variable present, non-empty, equals this repository's pin | Configured | proceeds to execution evidence |
| Variable present, non-empty, differs from this repository's pin | Drift | (ii) |
| This repository's own pin unreadable at comparison time | Evidence unreadable (not "empty expectation") | (v) |

Kept in step with this repository's own pin by the existing provisioning
script (`provision-e2e-target.sh`); this feature only reads it, never
writes it (spec Assumptions).

## Evidence Access Grant

The fixture maintainer credential (`specs/055`), unchanged by this feature
except in what it is used to read.

| Field | Value |
|---|---|
| Credential | `WING_COMMANDER_AUTO_RELEASE_E2E_MAINTAINER_TOKEN` (classic PAT) + `WING_COMMANDER_AUTO_RELEASE_E2E_MAINTAINER_USERNAME` |
| Scope | Write collaborator on the test repository only |
| Validity check | Existing `maintainer-credential` step, unchanged (`auto-release.yml` ~lines 300–413) |
| Containment check | Existing: exactly one repository (owner/collaborator/org-member affiliation) matches the test repository, case-insensitively |
| New usage | Two additional read-only calls: `gh variable list` (test repository's container image variable) and `gh api .../actions/runs/{id}/jobs` (test repository's job data for the driven run) |
| Failure mode | Any read failure (unset secret, revoked access, insufficient permission, rate limit, API error) routes to `fail-infra` with a `failing_check` naming the unreadable evidence (FR-004), never a silent pass |
