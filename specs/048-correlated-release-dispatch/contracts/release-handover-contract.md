# Contract: the handover between `auto-release.yml` and `release.yml`

Status: normative for this feature's implementation. This is the FR-019
"one place" document — both workflows' code comments point here for the
specifics below rather than restating them. It narrows
specs/045-auto-release-verified-head's `release-dispatch.md` and
`auto-release-workflow.md` for the parts this feature changes; those
documents remain the reference for what this feature leaves untouched
(the end-to-end verification job, version computation, the failure
report's dedup mechanism).

## `release.yml`'s `workflow_dispatch` interface

| Input | Type | Required | Default | This feature |
|---|---|---|---|---|
| `version` | string | yes | — | Unchanged. |
| `breaking` | boolean | no | `false` | Unchanged. |
| `breaking-notes` | string | no | `""` | Unchanged. |
| `attempt-token` | string | no | `""` | **New.** An automatic dispatch supplies `${{ github.run_id }}-${{ github.run_attempt }}` of the dispatching run. A manual dispatch leaves it blank. |
| `commit` | string | no | `""` | **New.** An automatic dispatch supplies the exact commit its end-to-end verification passed for. A manual dispatch leaves it blank and the release tags the branch tip, exactly as today. |

Both new inputs are optional and both default to producing today's
exact behavior when omitted (FR-015, FR-017) — see "Preserving the
manual path" below.

## What `release.yml` promises

1. **Title carries the version and the token** (FR-002). The workflow
   declares a top-level `run-name:` computed from `inputs.version` and
   `inputs.attempt-token`, wrapping the token in a `[attempt:...]`
   delimiter so a caller can match on the exact bracketed substring
   without a numeric-prefix collision. `attempt-token` left blank
   produces a title no real attempt's token can ever match (FR-016).

2. **The tagged commit is the requested commit, checked at the last
   possible moment** (FR-009–FR-011, FR-014). When `commit` is
   non-empty:
   - The workflow checks out `commit` (not the branch tip) and builds
     the release from it.
   - Immediately before creating any tag, the workflow re-reads
     `refs/heads/${{ github.event.repository.default_branch }}` live from
     `origin` and refuses — creating no
     exact tag, no floating major tag, and publishing no release — unless
     that live read still equals `commit` exactly. This is evaluated at
     tag time, not at the moment the request was accepted or the
     checkout was made (FR-010a), so a request that sat queued behind
     another `release.yml` run under the shared `wing-commander-release`
     concurrency group is still covered.
   - The refusal fires identically whether `commit` is an ancestor of
     the tip, was removed from the branch's history, or was never on
     the branch at all (FR-014) — it is a single equality check, not an
     ancestry walk.
   - The refusal is loud (`::error::` + non-zero exit) and states both
     the commit requested and the tip observed (FR-012) — this is for
     the benefit of a maintainer reading `release.yml`'s own run
     directly; `auto-release.yml` does **not** rely on this run's
     conclusion to classify the outcome (see "What `auto-release.yml`
     promises" below).
   - `commit` left empty skips this check entirely and tags the branch
     tip, exactly as today (FR-015).

3. **Nothing existing is weakened** (FR-020): the lint gates (Gate 1a/
   1b), the tag-collision refusal, the breaking-release rules, and the
   always-present breaking-changes section of the release notes are
   unchanged and still run, in the same order, before any new check
   this feature adds.

## What `auto-release.yml` promises

1. **It identifies its own run by evidence, never by recency**
   (FR-001). `dispatch-release` mints the token in "Request" fields
   above, records `request_time` immediately before dispatching, and
   afterward searches `gh run list --workflow=release.yml
   --json databaseId,displayTitle,createdAt,url` for a row whose
   `displayTitle` contains the exact `[attempt:<token>]` substring and
   whose `createdAt` is strictly after `request_time`. Zero, one, or
   more than one match are three distinct outcomes (`not-observed`,
   `found`, `ambiguous` — FR-004, FR-005), never collapsed by picking
   "the newest" among them.

2. **A release is reported on tag state alone** (FR-007, FR-007a).
   After the correlation search concludes (regardless of its outcome),
   the workflow waits for that outcome's own run to reach a terminal
   state before ever reading tag state: when `correlation` is `found`,
   it polls `gh run view <correlated-run-id> --json status --jq
   .status` (never `.conclusion`, which plays no part in the verdict)
   until that run's `status` is `completed`, bounded at 60 attempts 10
   seconds apart; when no single run was found to wait on, it waits a
   fixed 90 seconds instead. This closes a timing race a correlated run
   can still be mid-flight (checkout, lint, tag creation) the instant
   the correlation search concludes, and reading tag state immediately
   would file a false "release dispatch failed" report moments before
   the release actually lands. Only after that wait does the workflow
   independently fetch `refs/tags/<next_version>` and compare the commit
   it points at to the verified head *this attempt* requested — never
   against the branch tip at report time. That comparison, and only that
   comparison, decides whether the outcome is `released`. The correlated
   run (if any) supplies only the report's log link and, when the
   outcome is not `released`, diagnostic detail — it is never itself the
   proof a release happened (Edge Case: "the release actually happened
   but was never correlated" still reports `released`).

3. **A refusal at the branch-moved-on case is reported as expected, not
   as a failure** (FR-013). When the tag comparison in (2) is false, the
   workflow performs one more independent read — the current tip of
   the repository's default branch, resolved live via `gh repo view`
   (falling back to `main` only if that read fails; `report` runs off a
   `schedule` trigger with no `repository` event payload to read the
   default branch from directly) — and reports `branch-advanced` (not filed against
   the standing failure issue) when that tip no longer equals the
   verified head, or `release-failed` (filed) when it still does. This
   reclassification needs no signal out of `release.yml`'s own run
   beyond what git itself already records.

4. **The standing failure issue closes on tag state, not on a run's
   conclusion** (FR-007). `released` closes any open `auto-release:failed`
   issue; `branch-advanced` neither files nor closes anything;
   `release-failed` and `version-collision` file or update it, same as
   specs/045.

## Preserving the manual path (FR-015–FR-017, SC-003)

A maintainer dispatching `release.yml` by hand through the Actions UI or
`gh workflow run release.yml -f version=... -f breaking=...` supplies
only the three inputs that exist today. `attempt-token` and `commit`
default to `""`, which means:

- The run title still carries the version (now inside an empty
  `[attempt:]` bracket, cosmetic only).
- The checkout still resolves to the branch tip, exactly as today.
- The tag-time tip comparison step does not run at all (its own `if:`
  is `inputs.commit != ''`) — no new refusal, no new required field, no
  behavior change (Story 3's three acceptance scenarios).
- `auto-release.yml`'s correlation search can never match this run: its
  title contains `[attempt:]` with nothing between the colon and the
  bracket, which no real (non-empty) token can equal (FR-016).

## Cross-reference

- Attempt-token generation and the exact-substring matching rule:
  research.md D1–D3.
- The tag-time refusal mechanism and why the default branch is resolved
  dynamically rather than a literal `main`: research.md D4, D6.
- Why `released` is computed from tag state instead of run conclusion,
  including the cancelled-run case (FR-008): research.md D5.
- The deterministic regression gate enforcing all of the above:
  research.md D7, `regression-gate.md` in this directory.
