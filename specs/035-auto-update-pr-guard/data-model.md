# Phase 1 Data Model: Auto-Update Declines to Re-Propose a Candidate Whose PR Is Already Open

This feature has no application database — like `027-auto-update-spec-kit`
before it, it reads GitHub pull requests and the tracking issue's body,
and writes only the tracking issue (a comment and a marker edit) and the
run's own step summary. It introduces **no new file and no new label**.
The "entities" below are `spec.md`'s Key Entities section, expressed as
their concrete on-GitHub representation, plus the marker extension
research.md's decisions introduce.

## Version-bump pull request (existing GitHub PR, read-only to this feature)

| Field | Source | Used for |
|---|---|---|
| `number` | `gh pr list --json number` | Identifies the PR in every narration (FR-006, FR-007) |
| `body` | `gh pr list --json body` | Searched for the literal marker `<!-- wing-commander-auto-update-spec-kit: version-bump -->` (recognition, FR-002) vs. `<!-- wing-commander-auto-update-spec-kit: revert -->` (exclusion, FR-013) |
| `headRefName` | `gh pr list --json headRefName` | Parsed as `auto-update-spec-kit/v$CANDIDATE` to recover the candidate version this PR proposes (FR-003; research.md's "recognition vs. extraction" decision) |
| `state` (implicit: `--state open`) | `gh pr list` filter | Only open PRs are ever matches — a merged or closed PR is invisible to the guard by construction (FR-009: the guard "reads the pull request's own open/closed state and nothing else") |
| `isDraft` | not read | Deliberately not filtered — `--state open` already includes drafts (research.md), so a draft PR guards exactly like any other open one |

This feature never writes to a version-bump PR. It is opened and
titled/bodied exactly as `027-auto-update-spec-kit` already built (`act`'s
"Open version-bump PR" step, unchanged except for the new pre-push guard
below).

## Guard match set (computed each run, never persisted)

The guard's own working state for one run — not a stored entity, but the
shape `tasks.md` will implement as the guard step's output:

| Field | Type | Notes |
|---|---|---|
| `matches` | list of `{number, candidate}` | Every open PR whose body carries the version-bump marker, in the order `gh pr list` returns them |
| `lookup_ok` | boolean | `false` only when the `gh pr list` call itself failed (transport/API error) — distinct from `matches == []`, which means the call succeeded and found nothing (research.md's "don't know means don't act") |

Guard decision, purely a function of `(lookup_ok, matches, settled
candidate)`:

| `lookup_ok` | `len(matches)` | Decision | Narration shape |
|---|---|---|---|
| `false` | — | decline (FR-010) | "the open-PR lookup failed — declining this cycle" |
| `true` | `0` | proceed (US1 Acceptance #4) | none (guard is silent when it does not fire) |
| `true` | `1`, `candidate == settled` | decline (US1) | "v$settled already has an open PR #N awaiting review" |
| `true` | `1`, `candidate != settled` | decline (FR-011) | "v$settled is queued behind PR #N, which proposes v$candidate" |
| `true` | `>1` | decline (FR-014) | "N open PRs (#a, #b, ...) carry the version-bump marker — data-integrity condition, left for a human" |

## Settle-tracking marker (extended, same marker `027`'s `settle` step already owns)

Existing shape (`specs/027-auto-update-spec-kit/data-model.md`, embedded
in the singular tracking issue's body, written/read by `settle` at
auto-update-spec-kit.yml:624-687):

```text
<!-- wing-commander-auto-update-spec-kit: candidate=X.Y.Z observed=N [awaiting-decision=true] -->
```

This feature appends two optional sub-fields, written only by the guard
step, in the same position later sub-fields (`awaiting-decision=true`)
already occupy:

```text
<!-- wing-commander-auto-update-spec-kit: candidate=X.Y.Z observed=N [awaiting-decision=true] [guard-pr=N] [guard-checked=2026-08-16T14:03Z] -->
```

| Sub-field | Written | Cleared | Notes |
|---|---|---|---|
| `guard-pr` | Once, the first guarded run for a given blocking PR number (or when the blocking PR number changes — a new PR superseded the narrated one) | Never explicitly — it is overwritten, not deleted, the next time a *different* PR becomes the blocker; a resolved PR (merged/closed) simply stops being observed, so no run ever needs to erase the field (FR-009: no state to clear) | Dedup key for the one-time narration comment (FR-007) |
| `guard-checked` | Every guarded run, unconditionally | Never — always overwritten | UTC timestamp (`date -u +%Y-%m-%dT%H:%MZ`), the "still alive" signal US2 Acceptance #5 reads |

The `count > 1` (multiple open tracking issues) and `count > 1` (multiple
matching version-bump PRs, this feature's own new case) data-integrity
branches never write to the marker at all — both narrate via a warning
on every run instead of maintaining dedup state, matching `settle`'s
existing precedent (auto-update-spec-kit.yml:641-644).

## Version-bump branch (existing Key Entity, read-only to this feature except in `act`)

| Field | Value | Notes |
|---|---|---|
| Name | `auto-update-spec-kit/v$CANDIDATE` | Deterministic, one branch per candidate (`prepare`, auto-update-spec-kit.yml:1194) — the guard's version-extraction source (research.md) |
| Existence check | `git ls-remote --exit-code origin "refs/heads/$BRANCH"` | New: `act`'s "Open version-bump PR" step reads this before pushing (FR-015) |
| Associated open PR check | `gh pr list --head "$BRANCH" --state open --json number` | New: distinguishes "branch exists, PR still open" (should already have been caught upstream by `evaluate-path`'s guard) from "branch exists, no open PR" (the US4 leftover-branch case) for the FR-015 decline message |

## Candidate version / Tracking issue

Unchanged from `027-auto-update-spec-kit/data-model.md` — this feature
reads both, writes neither directly (FR-008: "MUST NOT change the pinned
Spec Kit version, the existing pull request or its branch, the tracking
issue's settle counter, or any label that gates the chain").
