# Contract: Fold Integration (FR-016, FR-017, FR-035)

This is the delta this feature makes to `pr-conversation.yml`, and the
two new composites both it and this gate consume — the single home
FR-017/FR-035 require.

## `wing-commander-fold-commit` (NEW)

See data-model.md §6 for the input/output table. Behavior: read
`tasks.md`, append `section-file`'s content (a well-formed Markdown
section — the caller's responsibility, not this composite's, to have
drafted correctly), read `spec-meta.json`, set `stage: "implement"`,
union `actor-login` into `pending_re_review_from`, write both files,
commit as `fold(<fold-id>): <fold-summary>`, push. If `section-file` is
empty (a leg or a review round that produced nothing to fold), the
composite writes nothing and outputs `folded: false` — this is the
existing "not folded" case `report-fold-outcomes` already has to
distinguish from a genuine fold, now produced by one function instead of
by whatever each caller's own agent happened to do.

**Callers**:
- `pr-conversation.yml`'s `act` job, one leg at a time (matrix,
  `max-parallel: 1`, unchanged). The agent step's job narrows: draft the
  section to a file, do not commit it — its tool grant loses
  `Bash(git commit:*)`/`Bash(git push:*)` (it never needed `git push`
  read/write beyond this, per the existing prompt's own instruction not
  to dispatch), and a new deterministic step after it calls this
  composite with the drafted file.
- This gate's `disposition` job (contracts/lifecycle-review-gate-
  workflow.md job 5), once per round, with `fold-id:
  review-gate-round-<N>`.

## `wing-commander-fold-dispatch` (NEW)

See data-model.md §7. Behavior: re-read the branch tip; if it moved past
`base-sha`, read `spec-meta.json.iteration`, dispatch `implement.yml`
with `iteration = iteration + 1`, record the fold evidence
`report-fold-outcomes` already scrapes via `git log --grep '^fold('`.

**Callers**:
- `pr-conversation.yml`'s `dispatch-once` job (`needs: [verify-image-
  prerequisites, classify-and-announce, act]`, `if: always()`) — becomes
  a thin wrapper: capture `base-sha` before the matrix (unchanged), call
  this composite after it (replacing today's inline body).
- This gate's `disposition` job, after `wing-commander-fold-commit`
  reports `folded: true`, with `base-sha` = the tip captured before this
  round's fold step ran.

## What does *not* change

- `pr-conversation.yml`'s `classify-and-announce` job (unchanged — still
  the only job that classifies a human's review into legs).
- `pr-conversation.yml`'s `report-fold-outcomes` job (unchanged — its
  cross-reference of job `conclusion`s against `fold(<id>):` git history
  works identically regardless of which code produced the commit).
- `wing-commander-9-pr-conversation.yml`'s trigger and bot-author
  exclusion (FR-018, research.md D7) — zero edits.
- `finalize.yml`'s re-review-request step, which reads
  `pending_re_review_from` — unaffected, since `wing-commander-fold-
  commit` writes that field the same way `act`'s agent used to.

## Regression coverage this delta must not weaken

- Spec 042's Gate 34 (`verify-fold-dispatch-once.py`) and Gate 35
  (`verify-finalize-refresh.py`) continue to exercise the real shipped
  `run:` text of `pr-conversation.yml`/`finalize.yml` — their fixtures
  are re-run against the extracted composites' call sites, not against a
  second copy of the logic, so a regression in the extraction fails the
  same gates that already prove the behavior these composites now
  implement.
- `verify-stage-tool-lists.py` (Gate 27) is updated for `act`'s narrowed
  tool grant (losing `Bash(git commit:*)`/`Bash(git push:*)`) the same
  way spec 042 itself updated it when `implement.yml` gained
  `Bash(git rm:*)` — a call-site/contract match, not a new check.
