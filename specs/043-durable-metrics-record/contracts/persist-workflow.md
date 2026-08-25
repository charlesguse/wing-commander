# Contract: Persistence (published mechanism, consumer-chosen destination)

**Layer**: published contract — new `metrics-persist.yml`
(`workflow_call`-only) plus a new composite action,
`wing-commander-metrics-persist`, it calls. The trigger and the
destination live in the consuming instrument
(`wing-commander-metrics-persist.yml`, contracts/wrapper-contract.md
below) — never in this file.

## `metrics-persist.yml` — declared interface

```yaml
on:
  workflow_call:
    inputs:
      run-id:
        type: string
        required: true
      destination-branch:
        type: string
        required: true
      destination-path:
        type: string
        required: true
      pipeline-repo:
        type: string
        required: false
      pipeline-repo-ref:
        type: string
        required: false
    secrets:
      pipeline-repo-token:
        required: false
    outputs:
      persisted-count:
        value: ${{ jobs.persist.outputs.persisted-count }}
      unpersisted-record-keys:
        value: ${{ jobs.persist.outputs.unpersisted-record-keys }}
```

No input has a literal default for `destination-branch` or
`destination-path` (FR-013: the mechanism must not choose, default to,
or infer a destination). `run-id` is the only required fact about the
event that started this — everything else about "which run, which
job" is discovered from `run-id` via the GitHub API, not read from
`github.event.*` (this workflow owns no trigger of its own; it is only
ever `workflow_call`ed by the wrapper, which resolved `run-id` from
either a `workflow_run` event or a `workflow_dispatch` input).

## Behavior

1. **Discover records**: `gh api repos/{owner}/{repo}/actions/runs/{run-id}/jobs`
   for the job list, then `gh api .../artifacts` filtered to names
   matching `metrics-record*`, mirroring `watchdog.yml`'s existing
   cross-run artifact discovery pattern. A run with zero such artifacts
   (no agent steps, or all skipped) produces zero records and no
   failure (FR-021).
2. **Retrieve**: `gh run download {run-id} -p 'metrics-record*' -D <dir>`,
   same tool and auth (`github.token` via `ACTIONS_TOKEN`) `watchdog.yml`
   already uses for cross-run artifact retrieval. An artifact that has
   expired or was never uploaded is reported as **not retrieved** by
   name (FR-022) — never silently skipped, never persisted as a partial
   record indistinguishable from a complete one.
3. **Validate**: each downloaded record is checked against
   contracts/metrics-record-schema.md's shape and its `per_model` sum
   invariant. A record whose `schema_version` this workflow doesn't
   recognize is persisted as-is (retained, not evaluated further,
   FR-025d) — it is a valid record of a version this reader doesn't have
   to understand to store. A record whose *declared* version is 1 but
   fails the schema check is rejected and reported by `record_key`
   (FR-041: well-formedness is decided by deterministic code).
4. **Append with retry**: research.md R6/R7/R8 — fetch the destination
   branch (creating it if absent), compute records not already present
   by `record_key`, append, commit, push; on rejection, retry up to 8
   times with linear backoff; on exhaustion, fail the step and name
   every unwritten `record_key`.
5. **Rollup** (Tier 2's cumulative surface only — the per-run line is
   emitted in-band by the originating stage, contracts/emission-contract.md):
   after a successful append, resolve this run's `spec_dir` (from the
   persisted records themselves — `spec.spec_dir`, when
   `identity_available`), re-read the destination file filtered to that
   `spec_dir`, recompute the cumulative totals, and update the lifecycle
   issue's machine-owned region per data-model.md and
   contracts/rollup-contract.md. A run with no spec identity on any of
   its records (e.g. a non-spec-attached workflow run) skips this step
   entirely — there is no lifecycle issue to update.

## Isolation guarantees (FR-015, FR-019, FR-019a)

- Never checks out, modifies, or pushes to any branch other than
  `destination-branch` (the origin pipeline run's branch is never
  touched).
- Never commits to the repository's default branch.
- Never approves or merges anything.
- Runs only after the origin run has concluded (`workflow_run: types:
  [completed]`, or manual `workflow_dispatch` naming an already-concluded
  `run-id`) — never a step inside the stage job it collects from.
- A failure at any step here (discovery, retrieval, validation, append,
  rollup) fails *this* workflow's own run, visibly, and has no effect on
  the origin pipeline run's status, checks, or comments.

## No agent invocation (FR-040a)

Every step in this workflow and its composite is deterministic
(`gh`, `git`, `jq`, `bash`). No step uses `claude-code-action` or any
other model invocation — verified by gate coverage (research.md R12.1).
