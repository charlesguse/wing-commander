# Contract Delta: The Image Check Job Shape (all 13 published stages)

This is a delta against `specs/010-reusable-pipeline/contracts/
stage-interfaces.md`'s "Conventions shared by all stages" section, which
remains the base contract for every other shared convention (the
`container-image`/registry-credential inputs themselves, the read-only
inspection policy, the tool list). Only the clause below changes.

## `verify-image-prerequisites` job — allocation, not existence

**Current contract**: every published stage carries a
`verify-image-prerequisites` job, first in the graph, with no job-level
`if:` — its one step is gated on `inputs.container-image != ''`, so the
job always allocates a runner even when the step it contains does
nothing. Every job that depends on it does so via bare `needs:`
(entry jobs) or, for the small set that already survive a `!cancelled()`
path, via a status-function `if:` that checks
`needs.verify-image-prerequisites.result == 'success'` alongside its
other ancestor checks.

**Amended contract**: the job itself gains
`if: inputs.container-image != ''`. With no image configured, GitHub
reports the job `skipped` and bills no runner for it (FR-001, SC-001).
With an image configured, the job's behavior is unchanged — it still
runs before any dependent job's container is created, and still fails
fast on a bad image or rejected credential (FR-003).

Every job in the same workflow whose `needs:` names
`verify-image-prerequisites` MUST carry an explicit `if:` containing the
literal comparison `needs.verify-image-prerequisites.result !=
'failure'`, combined with `!cancelled()` and, for every other named
dependency, an explicit `needs.<X>.result == 'success'` clause — see
`data-model.md`'s dependent-job condition table for the exact shape per
job type. A job that reaches the check only transitively, through
another job that already carries this condition, is unchanged (research.md
R-A2) — this clause governs direct dependents only.

This clause applies uniformly to all 13 published stages named in
FR-002. A stage-binding tool that iterates the published stage set
uniformly (spec.md's edge case) sees the check present, in the same
position, in every one — only its allocation behavior changed.

## What does not change

- The check's own step body (the `docker login`/`pull`/tool-probe bash)
  — untouched (research.md R-A4).
- The `container-image`/registry-credential input names and defaults.
- The job's `permissions: {}` and `runs-on:` passthrough shape, beyond
  gaining the one new `if:` line (Gate 22, amended to include it in its
  byte-for-byte comparison).
- Any dependent job's `needs:` list itself — only the `if:` gains the
  explicit clause; no dependency edge is added or removed.

## Versioning

Additive from an adopter's perspective: a stage invoked exactly as
today (no `run-name`/`since` changes — those belong to the other two
deltas in this directory) behaves identically when an image is
configured, and now bills one fewer job when it is not. No input,
secret, or output name changes. Per `specs/010-reusable-pipeline/
contracts/versioning.md`, this ships as part of this feature's overall
minor release; no separate per-stage version marker exists for this
repository's published contract (one repository-wide `vX.Y.Z` tag
governs every stage together).
