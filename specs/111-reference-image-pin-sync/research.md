# Research: Reference-Image Pin Sync

The spec has no `[NEEDS CLARIFICATION]` markers; the owner decisions are
recorded in its Clarifications. The decisions below close the remaining
design choices.

## D1. Waiting for the start-up check verdict

- **Decision**: `startup-check` keeps dispatching the dogfood wrapper, then
  finds the run it started and waits for its conclusion (`gh run list
  --workflow ... --json databaseId,createdAt,headSha` filtered to runs
  created after the dispatch, then `gh run watch --exit-status`). It exposes
  `passed=true|false` as a job output. `sync-pins` needs it and writes only
  on `passed=true`.
- **Rationale**: today it is fire-and-forget, so the build cannot know the
  verdict (FR-001 needs it). The dispatch carries the digest, so a run is
  matched by its `container-image` input via the run's display title/inputs
  where available, else by creation time after the dispatch.
- **Alternatives**: `workflow_call` of the check (rejected in the existing
  workflow: the agent action does not support the `push` event, Gate 6); a
  separate `workflow_run` trigger (loses the digest handoff and the
  race ordering in D4).

## D2. Prerequisite check gate

- **Decision**: The prerequisite check is the dogfood wrapper's
  `verify-image-prerequisites` job, which the same dispatched run already
  executes alongside the start-up check. The sync requires the whole
  dispatched run to conclude `success`, covering both checks with one verdict.
  If spec 112's check is absent on the ref, the dispatch run would not
  contain it; the script's workflow-wiring gate fails the PR rather than
  letting a pin be written unchecked (spec Assumptions).
- **Alternatives**: re-running Gate 62 in the sync job (it checks the
  Dockerfile text, not the published image); a second dispatch (double cost).

## D3. Credential and containment

- **Decision**: New secret `WING_COMMANDER_REFERENCE_IMAGE_SYNC_TOKEN`, a
  fine-grained token with Variables (write) on exactly this repository and the
  test repository. Containment: `gh api installation/repositories` does not
  apply to a PAT, so use the same observation auto-release uses —
  `user/repos?affiliation=owner,collaborator,organization_member --paginate
  --jq '.[].full_name'` — and require the sorted set to equal the sync set
  (this repository plus `WING_COMMANDER_AUTO_RELEASE_E2E_REPO`,
  case-insensitive). Under-permission surfaces when the write itself is
  refused; the script probes each repository with a variable read
  (`gh api repos/<r>/actions/variables/WING_COMMANDER_CONTAINER_IMAGE`) first
  and writes nothing unless both probes and the reach check pass (FR-005).
- **Rationale**: same technique as the reviewed 066/auto-release check, with
  a no-write-first ordering so a partial credential never half-writes.
- **Alternatives**: GitHub App token (more setup, owner chose option B);
  `GITHUB_TOKEN` (cannot write variables, cannot reach the other repository).
- **Residual risk**: a fine-grained token's variable read permission is not
  proof of write; a refused write is therefore still a handled failure (D6).

## D4. Concurrent builds (FR-010)

- **Decision**: a workflow-level `concurrency` group on the `sync-pins` job
  (`group: reference-image-pin-sync`, `cancel-in-progress: false`), plus an
  ordering guard in the script: before writing it compares `github.run_number`
  recorded in a hidden marker held in the job summary is not available across
  runs, so instead it reads the most recent *successful* run of this workflow
  (`gh run list --workflow --status success`) and refuses to write when a
  run with a higher `run_number` has already completed its sync, reporting
  "skipped: superseded by run N".
- **Rationale**: GitHub concurrency keeps one running and one pending and
  drops older pending runs, which already favours the newest; the guard covers
  an older run that finishes its check after a newer one wrote.
- **Alternatives**: store the winning run number in a third variable (breaks
  FR-003, which allows one variable only).

## D5. Idempotence and no-op (FR-006)

- **Decision**: read each repository's current value
  (`gh variable get`); equal to `<image>@<digest>` → "already current", no
  write. Digest must match `^sha256:[0-9a-f]{64}$` and the image name must
  equal `E2E_IMAGE`, else the run is a sync failure with nothing written.

## D6. Failure surfacing (FR-007)

- **Decision**: the script writes an outcome JSON (per repository: status,
  held, expected, reason) and exits non-zero if any repository failed. A
  following step, `if: failure()`-guarded on the sync step only, builds the
  issue body from that JSON and calls `wing-commander-durable-failure-issue`
  with label `reference-image-sync:failed` and `issues: write`, using the
  repository `GITHUB_TOKEN`. A final step re-fails the job. On a later fully
  successful sync the same composite closes the issue (`operation: close`),
  matching auto-release.
- **Alternatives**: a per-fingerprint marker like the watchdog (one label is
  enough: only one failure class exists).

## D7. Test repository unset

- **Decision**: with `WING_COMMANDER_AUTO_RELEASE_E2E_REPO` empty the sync set
  is this repository alone; the table reports "skipped: no test repository
  configured"; the run does not fail. Containment then requires reach of this
  repository only.

## D8. Gate and docs

- **Decision**: `verify-reference-image-pin-sync.py` (a) runs the script
  against a stubbed `gh` for: all-current, both written, over-reach,
  under-permission, one write refused, malformed digest, E2E repo unset,
  superseded; (b) asserts the workflow wires `needs`, the `passed` condition,
  the concurrency group, and that no other workflow or run-block holds a copy
  of the write call (single home). `docs/setup.md` and the workflow header
  drop the manual-copy instruction (FR-011).
