# Data Model: Correlated, atomic release dispatch

Like specs/045, this feature has no application database — every
"entity" below is state read from or written to git refs, a GitHub
Actions run's own fields, or one job's outputs within a run. This
document gives each entity from spec.md's Key Entities section a
concrete shape, extending specs/045's `data-model.md` rather than
restating the parts it leaves unchanged (the end-to-end verdict, the
minor-opt-in label, the version-decision bump rule, and the kill
switch are all untouched by this feature).

## Release request

The `workflow_dispatch` call `auto-release.yml`'s `dispatch-release` job
makes against `release.yml`.

| Field | Source | Notes |
|---|---|---|
| `version` | `decide-version` job's `next-version` output | Unchanged from specs/045. |
| `breaking` | literal `false` | Unchanged from specs/045 (FR-018 of specs/045). |
| `breaking-notes` | literal `""` | Unchanged from specs/045. |
| `attempt-token` | `${{ github.run_id }}-${{ github.run_attempt }}` of the dispatching `auto-release.yml` run | New (FR-002, FR-002a). Captured once at the top of `dispatch-release` and reused for the dispatch call, the correlation search, and the report. Globally unique per GitHub's own `run_id` guarantee — see research.md D1. |
| `commit` | `detect` job's `head-sha` output (the verified head) | New (FR-010). The exact commit the end-to-end verification passed for; never a value re-read at dispatch time. |

A manual dispatch through the Actions UI or `gh workflow run release.yml`
supplies only `version`/`breaking`/`breaking-notes` and leaves
`attempt-token`/`commit` at their `""` defaults (FR-015).

## Verified head

Unchanged in source from specs/045's "Unreleased head" `head_sha` field
— this feature's only change is that the value now *travels with the
request* (as the `commit` request field above) instead of being read
once by `auto-release.yml`, compared, and discarded (spec.md Key
Entities: "Verified head").

## Release run title

The GitHub Actions `run-name` GitHub computes for a `release.yml` run,
readable via `gh run list --json displayTitle` or the Actions UI.

| Case | Title |
|---|---|
| Automatic dispatch | `release v1.4.0 [attempt:18234567-1]` |
| Manual dispatch (no token supplied) | `release v1.4.0 [attempt:]` |

The `[attempt:...]` bracket delimiter is load-bearing (research.md D3):
a candidate title must contain the *exact* substring
`[attempt:<token>]`, closing bracket included, so a token that is a
numeric prefix of another token's title can never match it.

## Correlated run

The `release.yml` run — if any — whose title (above) carries this
attempt's own token and whose `createdAt` is strictly after this
attempt's own `request_time`. Distinct from "the newest release run",
which is what `auto-release.yml` read before this feature.

| Field | Source |
|---|---|
| `databaseId` | `gh run list --workflow=release.yml --json databaseId,displayTitle,createdAt,url` |
| `url` | Same call; used only for the report's log link (never as proof a release happened — see "Release outcome" below). |
| `correlation` | `found` \| `ambiguous` \| `not-observed` — see research.md D3 for the selection algorithm. |

`correlation` is reported (FR-006) but never itself gates whether a
release is recorded — that is "Tag state", below.

## Tag state

Whether the exact version tag exists and points at the verified commit
— the sole authority for "did this attempt's release happen" (FR-007).

| Field | Source | Notes |
|---|---|---|
| `tag_sha` | `git fetch origin refs/tags/<next_version>:refs/tags/<next_version>` then `git rev-parse <next_version>^{commit}` | A fresh, post-dispatch fetch — never a value read before the dispatch. |
| `tag_matches` | `tag_sha == verified_head` | The FR-007 test. Compared against the commit *this attempt* verified (`detect`'s `head-sha`), never against the branch tip at report time (FR-007a) — a branch that advances after a correct release must still report a release. |

## Branch-tip state (report-time)

A second, independent read used only to classify *why* `tag_matches`
was false — it never contributes to a `true` "released" determination.

| Field | Source | Notes |
|---|---|---|
| `current_tip` | `git ls-remote origin refs/heads/main \| cut -f1` | A live read at report time, not the `detect` job's stale `head-sha`. |
| `branch_advanced` | `current_tip != verified_head` | When true and `tag_matches` is false, the outcome is `branch-advanced` (FR-013), not a failure. |

## Release outcome

The single value `auto-release.yml`'s `report` job reads to decide what
to write. Extends specs/045's outcome set (`released`, `failed` /
`release-failed`, `stale-head`, `tip-unresolved`) with the two new
values FR-005/FR-006 require, and redefines how `released` itself is
computed:

| Outcome | Condition | Reported as | Standing failure issue |
|---|---|---|---|
| `released` | `tag_matches == true` (regardless of `correlation`) | "released \<version\> — \[correlated run\](url)" or "released \<version\> — own run not correlated" | Closed, with a comment naming the version (unchanged from specs/045). |
| `branch-advanced` | `tag_matches == false` and `branch_advanced == true` | "no release: the branch advanced past the verified head (\<sha\>) before the tag was created" | Not filed/updated — same class as specs/045's `stale-head`, per FR-013. |
| `release-failed` | `tag_matches == false` and `branch_advanced == false` | "release dispatch failed for \<version\>" | Filed/updated, classified "pipeline defect". |
| `correlation-ambiguous` | `correlation == ambiguous` (reported alongside whichever of the three rows above the tag check produced) | "own run could not be uniquely identified (N candidate runs matched)" appended to whichever outcome above applies | Filed/updated only when the *tag* outcome is `release-failed`; never on its own when `tag_matches == true` (FR-006's "distinct outcome" requirement is about the report's wording, not a fourth tag-check branch — ambiguity is diagnostic context on top of the tag-state verdict, per Key Entity "Correlated run"). |
| `correlation-not-observed` | `correlation == not-observed` | Same layering as `correlation-ambiguous` — appended context, never overriding the tag-state verdict (FR-005: "an unobserved run with no tag on the verified commit MUST NOT be reported as a release and MUST NOT close that issue" — which is already true because `tag_matches` is false in that case; this row exists so the *wording* names the gap honestly rather than reading as a generic release failure). | Same as `release-failed`'s row when `tag_matches` is false; not filed when `tag_matches` is true. |
| `version-collision` | Unchanged from specs/045 (`decide-version`'s `collision` output) | Unchanged. | Unchanged (filed, "version collision"). |

Read top-to-bottom: `tag_matches` decides the primary row
(`released`/`branch-advanced`/`release-failed`); `correlation` is then
folded into that row's report text as diagnostic detail, never as a
competing verdict. This keeps FR-007's "tag state alone" and FR-006's
"distinct reported outcome" both true without a decision matrix that
lets correlation override the tag check.

## Standing failure issue

Unchanged shape from specs/045 (`auto-release:failed` label, dedup by
label, body rebuilt per update, comment appended per recurrence). This
feature changes only *which* outcomes are filed against it (see the
table above) and adds one new field to the body:

- **Correlated run**: the log-link URL when `correlation == found`, or
  the literal string "not correlated (see tag state below)" when
  `ambiguous`/`not-observed` — so a maintainer reading the issue always
  sees explicitly whether the link they are following is this attempt's
  own run.

## Regression gate fixture surface (FR-018)

Not a runtime entity, but the concrete subject `verify-correlated-release-dispatch.py`
(research.md D7) reads:

| Checked file | Checked property |
|---|---|
| `.github/workflows/release.yml` | `run-name:` references `inputs.version` and `inputs.attempt-token` |
| `.github/workflows/release.yml` | a `git ls-remote origin refs/heads/main` comparison appears after the "Create tags" step marker |
| `.github/workflows/auto-release.yml` | the correlation step reads a time field (`createdAt`) alongside the token match |
| `.github/workflows/auto-release.yml` | the outcome computation reads a `refs/tags/` comparison, not a run `conclusion`/`status` field |
