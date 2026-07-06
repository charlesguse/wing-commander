# Contract: `speckit-3-plan.yml` triggers

## `pull_request` (closed)

Fires the `plan` job when **all** of the following hold (FR-001):

- `github.event.pull_request.merged == true`
- `github.event.pull_request.base.ref == 'main'`
- `github.event.pull_request.head.ref` starts with `spec-draft/`

Fires the `stalled` job when **all** of the following hold (FR-012):

- `github.event.pull_request.merged == false`
- `github.event.pull_request.head.ref` starts with `plan/`

Any other `pull_request: closed` event touching `specs/**` (e.g. an
unrelated docs PR, or this very plan PR closing) matches neither condition
and no job runs.

## `workflow_dispatch`

Manual (re)start of planning for one specification — used to retry after a
`stalled` outcome, or to plan a hand-submitted spec that never went through
stage 1.

| Input | Required | Type | Description |
|---|---|---|---|
| `slug` | yes | string | `NNN-slug` identifying `specs/NNN-slug/`. Must match `^[0-9]{3}-[a-z0-9][a-z0-9-]*$` or the run fails immediately (FR-010). |

**Precondition for a successful manual restart**: `plan/NNN-slug` must not
exist (delete it first) — otherwise the run treats it as a duplicate
planning attempt and no-ops (FR-009).

## Outputs (observable side effects, not literal `outputs:`)

On success:
- `spec/NNN-slug` exists (created if absent).
- `plan/NNN-slug` exists, containing the plan artifacts and updated
  `spec-meta.json`.
- An open PR: head `plan/NNN-slug`, base `spec/NNN-slug`.
- The lifecycle issue has label `stage:plan` and a new comment linking the
  plan PR.

On the spec/lifecycle-issue mismatch case (FR-010):
- The run fails (`::error::`) before creating any branch or PR.
- If a PR number is available, a comment is left on it explaining planning
  did not start.

On a stalled plan PR (FR-012):
- `spec-meta.json`'s `stage` becomes `"stalled"`, committed to
  `spec/NNN-slug`.
- The lifecycle issue gets label `stage:stalled` (replacing `stage:plan`) and
  a comment explaining the manual restart procedure.
