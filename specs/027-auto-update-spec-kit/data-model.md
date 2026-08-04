# Phase 1 Data Model: Auto-Update Spec Kit

This feature has no application database — it reads GitHub Releases,
GitHub Actions run/event data, and repository files, and writes GitHub
issues/comments/labels/PRs plus (via its own generated PRs, never
directly) `.specify/init-options.json` and
`wing-commander-preflight`'s `SPECKIT_SUPPORTED_VERSION` constant. The
"entities" below are `spec.md`'s Key Entities section, expressed as their
concrete on-disk/on-GitHub representation, plus the supporting shapes
research.md introduces.

## Pinned Spec Kit version (`.specify/init-options.json`, existing file)

| Field | Type | Notes |
|---|---|---|
| `speckit_version` | string (semver, no `v` prefix) | The value this feature reads every run and proposes to change. Currently `"0.12.4"`. |

Companion value, same file conceptually but a different location: `.github/actions/wing-commander-preflight/action.yml`'s
`SPECKIT_SUPPORTED_VERSION` constant — every version-bump/revert PR this
feature opens updates **both** in the same commit, or `preflight` starts
warning on every subsequent stage run. This feature never writes either
value directly; only a merged PR changes them.

## Upstream release (`gh api repos/github/spec-kit/releases`, external, not persisted)

| Field | Source | Used for |
|---|---|---|
| `tag_name` / semver | GitHub Releases API | Compared against the pinned version to determine eligibility and `release_type` |
| `prerelease` | GitHub Releases API | `true` → excluded from eligibility entirely (spec Assumptions: pre-releases out of scope) |
| `body` (release notes) | GitHub Releases API | Fed to `evaluate-path` as untrusted data; also the "sources" cited back on the lifecycle issue (FR-013) |
| `html_url` | GitHub Releases API | Cited verbatim wherever this release is referenced on the issue, so a human can open it directly |

`release_type` (`patch` \| `minor` \| `major`) is computed
deterministically from the semver delta between the currently pinned
version and `latest_upstream` (research.md) — never model-assigned.

## Settle-tracking marker (embedded in the lifecycle issue body, not a separate file)

```
<!-- wing-commander-auto-update-spec-kit: candidate=X.Y.Z observed=N -->
```

| Field | Meaning |
|---|---|
| `candidate` | The upstream version currently being watched/prepared |
| `observed` | Count of consecutive daily checks that found this exact `candidate` as `latest_upstream` |

Discovered via `gh issue list` — see the superseding note in
[research.md](./research.md#decision-superseded-2026-08-03-the-tracking-issue-is-found-by-listing-not-by-searching).
The tracking issue also carries the `auto-update:tracking` label, which is
what makes that lookup a bounded direct read.

~~Discovered via `gh search issues --repo "$GITHUB_REPOSITORY" "\"wing-commander-auto-update-spec-kit:\" in:body"`~~
(superseded — it opened duplicate issues #162/#167.)

At most one open issue may carry this marker at a time (FR-015); more than
one match is a data-integrity condition, reported and left for a human,
never auto-resolved.

## Verification (smoke test) result (ephemeral, produced by `verify`, consumed by `act`)

| Field | Type | Notes |
|---|---|---|
| `tier` | enum: `lightweight` \| `lightweight+end-to-end` | Which checks ran, per `release_type` (FR-004/FR-014) |
| `lightweight.passed` | boolean | `.specify/scripts/bash/check-prerequisites.sh` + `create-new-feature.sh --json` ran in an isolated worktree and produced the expected exit code / JSON shape |
| `end_to_end.passed` | boolean \| null | `null` when not applicable (patch upgrade); for minor/major, whether one throwaway spec-kit-driven stage run succeeded |
| `failure_detail` | string \| null | What specifically failed, in plain language — this is what SC-004 requires the issue to carry so a human never needs run logs |

A candidate (or the currently-pinned health-check target) is "working"
only if every check applicable to its tier passed (FR-004's own
definition).

## Upgrade decision record (`evaluate-path`'s structured output, posted to the issue, not separately persisted)

| Field | Type | Notes |
|---|---|---|
| `outcome` | enum: `clean-bump` \| `needs-migration` \| `ambiguous-options` | Determines the next job (`prepare` vs. route-to-human vs. post-question) |
| `reasoning` | string | Plain-language explanation, always recorded on the issue (FR-013) |
| `sources` | array of {title, url} | Drawn from the fetched release notes' own URLs/`html_url`s — never fabricated, empty array only if genuinely none exist |
| `options` | array of {label, description} \| null | Populated only when `outcome == ambiguous-options` — the choices posted as a question (FR-012) |
| `chosen_option` | string \| null | Filled in by the comment-reply interpretation step once a maintainer answers; `null` until then |

## Auto-update lifecycle issue (GitHub issue, one at a time, repo-scoped — not `spec:<NNN-slug>`-labeled)

| Field | Written by this feature? | Notes |
|---|---|---|
| Body | On create: yes — includes the settle-tracking marker plus the detected version/release type | Marker updated in place as `candidate`/`observed` change (settle-tracking section above); narrative content is appended as comments, not body rewrites, except for the marker itself |
| State (open/closed) | Opened on first detection; closed only via the version-bump PR's `Closes #N` keyword on merge (FR-009) — this feature never calls `gh issue close` directly for the success path | Reopened is not applicable — this feature never reopens an issue itself; a fresh detection cycle after a prior success opens a **new** issue (the closed one is that attempt's permanent record) |
| Labels | `auto-update:failed` (color `E99695`, added on any verification failure or rollback — FR-010) | No label at all while a cycle is in progress or after a clean success — mirrors this repo's existing "flag label only on the failure path" convention (`stage:stalled`, `rebase:blocked`) rather than a busy label taxonomy for the routine path |
| Comments | Every state transition: detected, settling, settled/superseded, decision + reasoning + sources, verification outcome, PR link, final summary (`pr-merged` job) | Uses `wing-commander-callout` for anything human-actionable (`kind: action` for the FR-012 question; `kind: info` for routine narration), matching every other stage's convention |

## Version-bump / revert pull request (GitHub PR, opened by this feature, never merged by it)

| Field | Notes |
|---|---|
| Title | `chore: bump Spec Kit to vX.Y.Z` (success path) or `revert: Spec Kit vX.Y.Z regression — restore vA.B.C` (rollback path) |
| Body | States the verified/failed checks, the decision reasoning + sources (success path), and carries `Closes #<lifecycle-issue-number>` (success path only — the revert path does **not** auto-close anything; it opens/keeps open its own flagged issue instead, since a rollback is itself the failure outcome FR-010 wants visible) |
| Diff | `.specify/init-options.json`'s `speckit_version` + `wing-commander-preflight`'s `SPECKIT_SUPPORTED_VERSION` constant, plus whatever the candidate's own `.specify/` artifact regeneration produces for a clean bump — never a partial migration (FR-018 routes those to a human instead of opening this PR at all) |
| Marker | `<!-- wing-commander-auto-update-spec-kit: version-bump -->` (or `: revert` for the rollback path) in the PR body, so the `pr-merged`-triggered job can recognize its own PRs among all merged PRs without depending on title text matching |

## State transition (the slice of pipeline state this feature reacts to and reports on)

```
(daily schedule / workflow_dispatch)
  └─ health-check on currently-pinned version
       fails ──────────────────────────────▶ open revert PR + flagged issue (FR-006/007/010); stop
       passes ─┐
                ▼
       detect latest eligible upstream release (deterministic)
         not newer than pinned ─────────────▶ no-op, no PR, no issue (SC-007); stop
         newer ─┐
                 ▼
       settle-tracking (singular open issue, marker in body)
         no open issue ─────────────────────▶ create issue, observed=1, "watching"; stop
         open issue, candidate unchanged, observed < threshold ▶ increment observed; stop
         open issue, candidate unchanged, observed >= threshold ▶ settled — continue
         open issue, candidate changed ─────▶ update marker, reset observed=1, comment why; stop
         open issue, awaiting maintainer decision ▶ left untouched (FR-015); stop
                 ▼ (settled)
       evaluate-path (agent, sonnet)
         needs-migration ───────────────────▶ comment routing to human, no diff applied (FR-018); stop
         ambiguous-options ─────────────────▶ post question + reasoning + sources (FR-012); stop —
                                               resumes later via (issue_comment, verified maintainer reply,
                                               haiku interpretation) re-entering at clean-bump below
         clean-bump ─┐
                     ▼
       prepare (apply version-bump diff) → verify (tiered per release_type)
         fails ──────────────────────────────▶ comment failure detail, label auto-update:failed,
                                                 leave pin unchanged, issue stays open (FR-006/010)
         passes ─────────────────────────────▶ open version-bump PR with Closes #N; comment PR link

(pull_request closed, merged == true, this feature's own marker present)
  └─ post rich summary comment (adopted version, what was verified) — issue is already closed via Closes #N
     for the success path; for a revert PR's merge, the flagged issue stays open per its own FR-010 shape
```

This feature never writes `spec-meta.json` (it has no per-spec identity)
and never writes any `.specify/memory/*.json` file (research.md) — its
only repository-content writes are the version-bump/revert PR's own diff
(`.specify/init-options.json`, the preflight constant, and whatever the
candidate's own artifact regeneration touches), always via a PR a human
merges, never a direct commit to `main`.
