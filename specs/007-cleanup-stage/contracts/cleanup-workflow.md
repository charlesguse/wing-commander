# Contract: `speckit-7-cleanup.yml`

This project has no library/API surface; its "interfaces" are the GitHub
Actions trigger contract and the deterministic checks/writes that must
run in order. This document is the contract the implementation (tasks
phase, next stage) must satisfy. It also contracts the two changes this
feature makes to `speckit-3-plan.yml` and `speckit-4-tasks.yml`
(research.md's consolidation finding).

## Trigger contract

```yaml
on:
  pull_request:
    types: [closed]
```

Repo-wide, no path filter — self-selecting via the job-level `if:`
guards below, per FR-010 and User Story 3. This extends the stub's
existing head-ref guard to recognize `tasks/*` (currently missing —
the stub only lists `spec/`, `spec-draft/`, `plan/`, `impl/`).

## Job gates (coarse — job-level `if:`, cheap, payload-only)

```
teardown-done:
  github.event.pull_request.merged == true &&
  github.event.pull_request.base.ref == 'main' &&
  startsWith(github.event.pull_request.head.ref, 'spec/')

teardown-rejected:
  github.event.pull_request.merged == false &&
  github.event.pull_request.base.ref == 'main' &&
  startsWith(github.event.pull_request.head.ref, 'spec-draft/')

mark-stalled:
  github.event.pull_request.merged == false &&
  (
    (github.event.pull_request.base.ref == 'main' &&
     startsWith(github.event.pull_request.head.ref, 'spec/'))
    ||
    (github.event.pull_request.base.ref != 'main' &&
     (startsWith(github.event.pull_request.head.ref, 'plan/') ||
      startsWith(github.event.pull_request.head.ref, 'tasks/') ||
      startsWith(github.event.pull_request.head.ref, 'impl/')))
  )
```

Every other combination (an ordinary PR; a `spec-draft/*` PR that merged;
a `plan/`/`tasks/`/`impl/*` PR that merged; a `plan/`/`tasks/`/`impl/*` PR
whose base is `main` instead of a spec branch) matches none of the three
jobs — no job runs, no action taken (FR-010, data-model.md's outcome
table).

## Refusal contract (FR-009, all three jobs)

The first step inside every job, after checkout + `speckit-context`:

1. Derive `slug` by stripping the matched head prefix
   (`spec-draft/`, `spec/`, `plan/`, `tasks/`, or `impl/` — for `impl/`,
   also strip a trailing `-iterN` suffix) and validate it against
   `^[0-9]{3}-[a-z0-9][a-z0-9-]*$`.
2. For the `mark-stalled` job's non-final arm: verify
   `github.event.pull_request.base.ref == "spec/$slug"` exactly
   (research.md — the coarse job gate only checked "not main").
3. Check out the branch data-model.md's identity-resolution table names
   for this outcome (`spec/$slug` for `teardown-done` and
   `mark-stalled`'s final arm; `spec-draft/$slug` for
   `teardown-rejected`; `spec/$slug` — the PR's base — for
   `mark-stalled`'s non-final arm) and verify `specs/$slug/spec.md` and
   `specs/$slug/spec-meta.json` both exist, and that
   `spec-meta.json`'s own `issue`/`spec_dir` fields are non-empty and
   `spec_dir` matches `specs/$slug`.

Any failure: `::error::`, a `$GITHUB_STEP_SUMMARY` line, and
`gh pr comment $PR_NUMBER --body "⚠️ ..."` (never a lifecycle-issue
comment — research.md). No branch deletion, no label change, no issue
write happens after a refusal.

## `teardown-done` contract (FR-002–FR-005)

Runs only once the refusal contract passes:

1. **Idempotency check**: `gh issue view $issue --json state --jq .state`.
   If already `CLOSED`, skip steps 2–4 below (branch deletion, step 5,
   still runs).
2. **Completion summary** (the one agent step, `claude-haiku-4-5`,
   `--allowedTools "Read,Glob,Grep,Bash(git log:*),Bash(git diff:*),Bash(git show:*),Write"`,
   `--disallowedTools "WebSearch,WebFetch"`, no `git commit`/`git
   push`/`gh` access): diffs
   `${merge_commit_sha}^1..${merge_commit_sha}` on a checkout of `main`,
   writes a narrative to a temp file. On outright failure (action fails,
   or the file is missing/empty afterward): fall back to a generic
   "Specification merged (automated summary unavailable)." sentence
   rather than blocking issue closure — a summary-generation failure must
   not prevent SC-001's teardown from completing.
3. `gh issue close $issue --comment "$(cat <summary temp file>)"` —
   atomic close-with-comment, avoiding a separate close call that could
   race a duplicate comment on retry.
4. `gh label create "stage:done" --force`; `gh issue edit $issue
   --add-label "stage:done"`; remove whichever `stage:*` label is
   currently present (read via `gh issue view --json labels`, strip
   `stage:done` itself from the candidates, remove the rest).
5. **Branch deletion** (independent of steps 1–4, always attempted):
   `spec-draft/$slug`, `spec/$slug`, `plan/$slug`, `tasks/$slug`, and any
   `impl/$slug-iter*` (glob via `git ls-remote --heads origin
   "impl/$slug-iter*"`). Each deletion tolerates "ref not found" as
   success (FR-011).

## `teardown-rejected` contract (FR-006–FR-008, FR-014)

Runs only once the refusal contract passes:

1. **Idempotency check**: is the `spec:$slug` label still present on the
   issue (`gh issue view --json labels`)? If already absent, skip steps
   2–3 below (branch deletion, step 4, still runs).
2. `gh issue comment $issue --body "..."` — states the specification was
   rejected; issue is **not** closed (FR-014).
3. `gh issue edit $issue --remove-label "spec:$slug"`; remove whichever
   `stage:*` label is currently present.
4. **Branch deletion**: `spec-draft/$slug` only (the only branch that
   exists at the draft stage). Tolerates "ref not found" as success.

## `mark-stalled` contract (FR-012, FR-013, FR-015)

Runs only once the refusal contract passes, for either the final-PR arm
or the non-final-PR arm:

1. **Idempotency check**: does the issue's current stage label already
   read `stage:stalled`? If so, skip steps 2–4 below.
2. Commit `specs/$slug/spec-meta.json` (`stage: "stalled"`) directly onto
   `spec/$slug` and push (`git diff --cached --quiet` guard before
   committing, matching the retired jobs' own guard — a no-op commit must
   not fail the job).
3. `gh label create "stage:stalled" --force`; `gh issue edit $issue
   --add-label "stage:stalled"`; remove whichever prior `stage:*` label
   was present (never removes `spec:$slug`).
4. `gh issue comment $issue --body "..."` — states which pull request
   (final, or plan/tasks/impl) was closed unmerged, that the
   specification is now stalled with its branches intact, and includes
   the full-teardown runbook: a link to the closed PR and to
   `docs/architecture.md`'s Stage 6 section, plus literal
   `git push origin --delete <branch>` / `gh label`/`gh issue edit`
   commands scoped to this specification's own remaining branches
   (research.md's runbook decision).
5. **No branch deletion on this path** — FR-012/FR-013 explicitly
   preserve every branch.

## Consolidation contract (FR-013 — changes outside `speckit-7-cleanup.yml`)

`speckit-3-plan.yml`'s `stalled` job (reacting to `plan/*` closed
unmerged) and `speckit-4-tasks.yml`'s `stalled` job (reacting to
`tasks/*` closed unmerged) are removed in the same change that lands this
feature. Their behavior is fully replaced by this workflow's
`mark-stalled` job's non-final arm — leaving both in place would fire two
independent "stalled" comments on the same closed PR (research.md).
Nothing in `speckit-5-implement.yml` needs retiring — it has no
`pull_request`-triggered stalled job (its own stalled path reacts to its
own dispatch failing, not to a PR closing).

## Non-goals (explicitly out of contract, per spec.md Assumptions)

- Judging whether a merge or close "should" have happened — this stage
  reacts to whatever a human already did.
- Any automated "force full teardown" dispatch mode for a stalled
  specification — the stalled comment's runbook is manual, per
  research.md.
- Re-litigating the finalize stage's own PR-body content or the
  implement/converge stage's iteration logic — both are unchanged and
  out of scope.
