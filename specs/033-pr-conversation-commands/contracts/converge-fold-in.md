# Contract: Folding an In-Scope Change Into Converge Input (FR-004/FR-005)

Implements research.md D5. **Touches no file outside this feature's own
new stage** — `implement.yml` and `.claude/skills/speckit-converge/SKILL.md`
are unmodified.

## Precondition

`RequestClassification.category == "in-scope-change"`, running inside
`pr-conversation.act`, already checked out on `spec/<slug>` (the same
branch the PR under discussion is the head of — data-model.md
`PullRequestIdentity`), inside the `wing-commander-<spec-dir>` concurrency
group (research.md D6).

## Steps (deterministic except step 2)

1. **Read current state**: `stage=$(jq -r .stage spec-meta.json)`,
   `recorded=$(jq -r .iteration spec-meta.json)`.
2. **Draft the feedback section** (agent step, using
   `RequestClassification.drafted-content.tasks-md-section` from the
   classify step — already produced read-only; this step performs the
   actual file write, staying inside `pr-conversation.act`'s allowed
   tools): append to `<spec-dir>/tasks.md`:

   ```markdown
   ## Maintainer Feedback (PR #<pr-number>, comment <comment-id>)

   <traceable task items derived from the untrusted request text,
   in the same checkbox-list shape /speckit-tasks already produces>
   ```

   Append-only — never edits or reorders existing sections, mirroring
   `/speckit-converge`'s own "APPEND-ONLY, NEVER REWRITE" operating
   constraint for `tasks.md`, even though this step is not `/speckit-converge`
   itself.
3. **Commit the section on its own**: `git commit -m "pr-feedback: fold PR #<pr-number> comment <comment-id> into tasks.md"`.
   The `pr-feedback:` prefix is deliberately distinct from `implement.yml`'s
   `converge:` prefix (research.md D5) so the two commit-scan signals never
   collide.
4. **Advance `spec-meta.json.stage` back to `"implement"`** (iteration left
   at `recorded` — the next `implement.yml` cycle sets it, per that
   stage's own existing "Update spec-meta.json" instruction), committed in
   the same push as step 3 (one commit, `spec-meta.json` + `tasks.md`
   together) so the branch is never observed in an inconsistent
   intermediate state.
5. **Push to `spec/<slug>`.**
6. **Dispatch** `gh workflow run <implement-workflow> -f spec_dir=<spec-dir> -f issue=<issue-number> -f iteration=<recorded+1>` —
   the exact, already-published `workflow_dispatch` signature
   (`specs/010-reusable-pipeline/contracts/stage-interfaces.md`'s "Chaining
   payload contract" table, unchanged by this feature). `<implement-workflow>`
   is the stage's declared `implement-workflow` input, **never** a literal
   filename: a wrapper filename is consuming-repository convention, not
   published contract (constitution VI/VII), exactly as `implement.yml`'s
   `self-workflow`/`next-workflow` and `plan.yml`'s `next-workflow` already
   treat it. Empty (the default) = **standalone mode**: steps 1-5 still
   happen — the fold-in is committed and pushed — and step 7's reply says
   plainly that no implement workflow is configured and gives the manual
   `spec_dir`/`issue`/`iteration` payload. A missing dispatch must never
   fail the step: under `set -euo pipefail` that would abort *after* the
   fold-in push and *before* the reply, leaving the maintainer's change
   folded in with nothing run and nothing said (T078, FR-014/SC-005).
7. **Reply on the PR** confirming the fold-in and dispatch (FR-014), with
   a link to the dispatched run once `gh run list --workflow
   <implement-workflow> --created ">=<step-start-timestamp>" --limit 1`
   resolves it (best-effort — a short, bounded poll, not the long-running
   pattern research.md D10 explicitly rejects elsewhere; if resolution
   times out, the reply still confirms the dispatch and points at the
   workflow's Actions tab rather than a specific run).

## Idempotency guard interaction (why step 4 is required)

`implement.yml`'s own idempotency guard only proceeds when
`stage=="implement" && iteration==recorded+1` (or the `stalled` variant).
After `finalize.yml` has run, `stage` reads `"review"` — without step 4,
the dispatch in step 6 would be silently accepted by `gh workflow run` but
then no-op inside `implement.yml` itself (its guard step sets
`skip=true` and stops before any agent step), which would look like
nothing happened with no error surfaced. Step 4 is what makes step 6's
dispatch actually run a cycle.

## Cap interaction (FR-005)

No new cap logic is introduced. `implement.yml`'s existing
`max-iterations` resolution and "cap reached" branch (`implement.yml`'s
own `Resolve iteration cap` / `Dispatch next step` steps) apply unchanged
to the re-dispatched iteration `recorded+1` — if that number already
exceeds the cap, `implement.yml` itself posts the existing "Iteration cap
reached" callout to the lifecycle issue and still dispatches
`next-workflow` (finalize). `pr-conversation.act`'s own step 7 reply
additionally notes on the **PR** (which `implement.yml` does not do today)
that the cap may be hit, satisfying FR-005's "MUST post its outcome...on
the PR" without `pr-conversation.act` needing to know the cap's numeric
value itself — it only needs to know it dispatched, and `implement.yml`'s
existing progress-comment step (posted to the issue) remains the
authoritative outcome report either way.

## Convergence signal (unchanged)

`implement.yml`'s existing deterministic convergence check — scanning
`git log` for a `converge:`-prefixed commit touching `tasks.md` in the new
cycle's own commit range — is unaffected by this feature's
`pr-feedback:`-prefixed commit, which lands in a *prior* range (before the
re-dispatched cycle's own `BASE_SHA`), not inside it.
