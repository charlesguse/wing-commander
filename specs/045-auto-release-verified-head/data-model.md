# Data Model: Auto-Release After Merged Features Pass a Scheduled End-to-End Verification

This feature has no application database — every "entity" below is a
piece of state read from or written to git, GitHub issues/labels/tags, or
a single job's own outputs within one workflow run. This document gives
each entity from the spec's Key Entities section a concrete shape so the
tasks stage can implement it without re-deriving the representation.

## Unreleased head

| Field | Source | Notes |
|---|---|---|
| `head_sha` | `git rev-parse HEAD` at the start of the `detect` job | Captured once per attempt; later jobs must reuse this value (a job output) rather than re-resolving `HEAD`, so a mid-run advance of `main` (spec Edge Cases) cannot cause the release to land on a commit this attempt never verified (FR-016). |
| `has_new_work` | boolean | `true` iff `head_sha` is not exactly the commit the latest release tag (below) points at. |

## Latest release tag

| Field | Source | Notes |
|---|---|---|
| `tag` | highest `vX.Y.Z` exact tag by semver order, excluding floating `vX` major tags | `git tag --list 'v[0-9]*.[0-9]*.[0-9]*'` filtered to the strict `vX.Y.Z` shape, then sorted. |
| `tag_sha` | `git rev-parse "$tag"^{commit}` | The commit the tag's annotated object points at, not the tag object's own SHA. |
| `exists` | boolean | `false` when no such tag exists at all (FR-004: no baseline, report and stop). |

## End-to-end test repository

| Field | Source | Notes |
|---|---|---|
| `full_name` | repository variable `WING_COMMANDER_AUTO_RELEASE_E2E_REPO` | `OWNER/NAME` shape, same convention as `WING_COMMANDER_AUTO_UPDATE_SPEC_KIT_E2E_SCRATCH_REPO`. Unset ⇒ infra-failure outcome (FR-011), never a crash. |
| `default_branch` | `gh repo view <full_name> --json defaultBranchRef` | This is also "the per-run branch" — see research.md D6. Reachability of this call is itself the "configured but unreachable" check (FR-011). |
| `scoped_token` | minted per attempt via `actions/create-github-app-token@v3` with `owner`/`repositories` narrowed to `full_name` | Never the job's primary `wing-commander-context` token (research.md D11). Scope: Contents read/write, Issues read/write. No Administration grant. |

## End-to-end verdict

The single concrete, machine-readable value Constitution IX and FR-015
require the release decision to read — never an agent's narration.

```jsonc
{
  "outcome": "pass" | "fail-infra" | "fail-timeout" | "fail-incomplete" | "fail-wrong-output",
  "verified_head": "<head_sha>",
  "failing_check": "<string, e.g. 'stage:plan label never applied' | 'e2e-repo unreachable' | null on pass>",
  "expected": "<string, null on pass>",
  "observed": "<string, null on pass>",
  "evidence_url": "<link to the test repository's lifecycle issue, or the unreachable repo's expected variable name>"
}
```

- `pass` requires every check in research.md D10 to hold: issue `state:
  CLOSED`, label `stage:done` present, and every intermediate
  `stage:{spec,clarify,plan,tasks,implement,review}` label found in the
  issue's timeline, plus `spec.md`/`plan.md`/`tasks.md` present in the
  merged implementation PR's tree.
- `fail-infra`: `WING_COMMANDER_AUTO_RELEASE_E2E_REPO` unset, or `gh repo
  view`/token-mint against it fails (FR-011). `failing_check` names the
  variable to set or the installation to add, per FR-011's own wording.
- `fail-timeout`: the poll (research.md D10) never reached a terminal
  state within the job's `timeout-minutes` (FR-012, "did not complete").
- `fail-incomplete`: the issue reached a terminal-but-not-done state
  (`stage:stalled`, or closed unmerged) before timeout.
- `fail-wrong-output`: terminal state was `stage:done` but an asserted
  artifact or intermediate label was missing (FR-012, "completed and
  produced the wrong output").

This object is a job output (`needs.verify-e2e.outputs.verdict`, JSON-
encoded), never persisted to this repository's `specs/` tree, a pushed
branch, or a PR (FR-013).

## Minor opt-in label

A fixed string, `release:minor`, applied by a maintainer to a pull request
against this repository's own `main`. Not a repository variable — a label
name, chosen the same way `spec-request` and `model:opus` are: a literal
in the workflow (research.md D5), not a configurable knob (spec declines
extra configuration surface per its own Assumptions).

## Version decision

| Field | Source |
|---|---|
| `bump` | `"minor"` if `release:minor` appears on any merged PR in `git log <tag>..<head_sha> --merges`, else `"patch"` (research.md D5). |
| `next_version` | `tag` (latest release tag) incremented by `bump`, never touching the major component. |
| `collision` | `true` if `next_version` already exists as a tag (FR-024) — computed by the same `git rev-parse -q --verify refs/tags/<next_version>` check `release.yml`'s own "Validate version and plan tags" step already performs; a collision here is reported and no dispatch happens, rather than relying on `release.yml` to reject it after the fact. |

## Release dispatch

The exact `workflow_dispatch` inputs `release.yml` already declares
(`specs/010-reusable-pipeline/contracts/versioning.md` + `release.yml`
itself) — this feature supplies values, adds no new input:

| Input | Value supplied |
|---|---|
| `version` | `next_version` (e.g. `v1.4.0`, `release.yml` itself strips a leading `v` if present) |
| `breaking` | `false`, always (FR-018) |
| `breaking-notes` | `""`, always |

## Failure report

One durable GitHub issue in this repository, labeled `auto-release:failed`,
deduplicated by that label (research.md D13):

- Title: `Auto-release verification failed at <short-sha>`
- Body (rebuilt on every update to the same issue, not appended-to,
  since only the latest attempt's detail is actionable): verified head,
  failing check, expected vs. observed, and an explicit "infrastructure"
  vs. "pipeline defect" classification (`fail-infra` → infrastructure;
  every other `fail-*` outcome → pipeline defect), matching FR-026/SC-007's
  "under 2 minutes, without opening logs" bar.
- Comment appended per recurrence, so a maintainer can see the failure
  history for one unreleased head without the issue count growing
  (FR-028).
- On the next attempt's `pass` outcome, the open `auto-release:failed`
  issue (if any) is closed with a comment naming the version that shipped
  — closes the loop without leaving a stale open issue after the problem
  resolves itself.

## Kill switch

Repository variable `WING_COMMANDER_AUTO_RELEASE_PAUSED`. `"true"` ⇒ every
job in `auto-release.yml` is skipped via job-level `if:` (research.md D2).
No other state.
