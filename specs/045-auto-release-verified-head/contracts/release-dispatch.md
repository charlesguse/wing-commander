# Contract: reusing `release.yml`, and reporting its outcome

Status: normative for this feature's implementation. Cross-references
`research.md` (D12, D13) and `data-model.md` ("Version decision",
"Release dispatch", "Failure report").

## `release.yml` is consumed exactly as it exists today — no new input,
no new trigger

`release.yml` keeps its current, unmodified `workflow_dispatch` interface
(FR-021 — the manual path gains no gate, input, or precondition from this
feature):

| Input | Type | This feature's value |
|---|---|---|
| `version` | string, required | computed next version (data-model.md "Version decision"), e.g. `v1.4.0` |
| `breaking` | boolean, default `false` | always `false` (FR-018) |
| `breaking-notes` | string, default `""` | always `""` |

This feature adds no `workflow_call` trigger to `release.yml`, no new
input, and no bypass of its Gate 1a/1b lint gates, tag-creation logic, or
release-notes generation (FR-020). It is invoked the only way its current
trigger allows: `gh workflow run release.yml -f version=<v> -f
breaking=false -f breaking-notes=`, run with `GH_TOKEN: ${{ github.token
}}` from a job declaring `permissions: { actions: write }` — the
established, incident-documented idiom for cross-workflow dispatch in
this repository (research.md D12).

## Confirming the dispatch actually succeeded

`gh workflow run`'s success only means the dispatch was accepted, not that
`release.yml` itself passed its own gates. This feature polls the
dispatched run to a conclusion (`gh run list --workflow=release.yml -b
main --json databaseId,status,conclusion -L 1`, then `gh run watch
<id>` or an equivalent poll) before recording an outcome:

| `release.yml` run conclusion | This feature's `release-outcome` |
|---|---|
| `success` | `released` |
| anything else (`failure`, `cancelled`, `timed_out`) | `failed` — reported as a **release failure**, distinct from a verification failure, and never recorded as a successful auto-release (FR-029) |

## Version computation (data-model.md "Version decision")

1. `bump`: `minor` if `release:minor` appears on any pull request merged
   in `git log <latest-tag>..<verified-head> --merges`; otherwise `patch`
   (research.md D5). Never `major` — there is no code path by which this
   feature can request one (FR-018, FR-019).
2. `next_version`: `latest-tag` incremented by `bump` on the minor or
   patch component only.
3. Collision check: `git rev-parse -q --verify refs/tags/<next_version>`.
   A hit means `next_version` is already an immutable published tag — no
   dispatch happens; this is reported as a distinct outcome (FR-024) from
   both a verification failure and a release failure, since neither the
   end-to-end run nor `release.yml` did anything wrong.

## Reporting (data-model.md "Failure report")

`auto-release.yml`'s `report` job (see `auto-release-workflow.md`) is the
only place this feature writes anything maintainer-facing:

- **Every** attempt: one `$GITHUB_STEP_SUMMARY` line stating its outcome
  — `released <version>`, `no new work since <tag>`, `verification failed:
  <failing_check>`, `release dispatch failed`, `version collision:
  <version> already tagged`, or (implicitly, via the job simply not
  running) `paused` (FR-030).
- **Any `fail-*` verdict, a version collision, or a `release-outcome:
  failed`**: file-or-update the durable `auto-release:failed` issue on
  this repository (research.md D13) — dedup by that label, one issue
  updated across consecutive failures for the same unreleased head
  (FR-028), body naming the verified head, the failing check, and
  expected-vs-observed (FR-026), classified as infrastructure
  (`fail-infra`) or pipeline defect (every other outcome).
- **`release-outcome: released`**: close any open `auto-release:failed`
  issue with a comment naming the version that shipped.

This is a deliberately different mechanism from `wing-commander-callout`
(research.md D13) — there is no spec lifecycle issue for an auto-release
attempt to post to.
