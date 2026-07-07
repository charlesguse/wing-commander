# Phase 0 Research: Finalize Stage — Final Pull Request & Manual-Task Report

`spec.md`'s own checklist (`checklists/requirements.md`) confirms no
`[NEEDS CLARIFICATION]` markers remain — the one marker this spec started
with (FR-010's not-fully-converged signal) was already resolved on the
lifecycle issue before this plan ran, choosing a plain in-body ⚠️ callout
over any additional GitHub state (draft/label). What follows are the
implementation-level decisions `spec.md` and `docs/architecture.md`'s Stage
5 sketch deliberately leave open that a plan must pin down before tasks can
be generated.

## Decision: The Haiku step only produces content; every GitHub write is a separate deterministic step

**Decision**: The stage's one `claude-code-action` step (`claude-haiku-4-5`)
is read-only: it inspects `git diff`/`git log` between `main` and
`spec/NNN-slug` and reads `tasks.md`, then writes exactly two plain-text
files to known paths under `${{ runner.temp }}` — a change-summary
narrative and the remaining-manual-work list — and does nothing else (no
commits, no `gh pr create`, no `gh issue comment`). Every GitHub write
(`gh pr create`, the metadata commit, `gh issue comment`, the label flip)
is a plain deterministic bash step that runs after it, reading those two
files' contents verbatim.

**Rationale**: `docs/architecture.md`'s Stage 5 design already implies this
split: "1. Haiku step summarizes ... (structured output ...) 2. Plain
`gh pr create` ... 3. Comment the same manual-task list ..." — "Plain" is
explicit for step 2, and step 3's "the same" list is far easier to
guarantee byte-identical (SC-003) if both the PR body and the issue comment
read it from one file than if a single agent turn is trusted to reproduce
the same text twice across two different tool calls. This also matches the
constitution's tiering rationale for Haiku ("triage, classification,
labeling, and summaries" — not GitHub-object authoring) and keeps the one
agent step's `--allowedTools` genuinely minimal: `Read`/`Glob`/`Grep`,
`Bash(git log:*)`/`Bash(git diff:*)`/`Bash(git show:*)`, and `Write`
scoped to the two temp paths — no `git commit`, `git push`, or `gh` tool
access at all, which is a strictly smaller footprint than any other
stage's agent step has needed so far.

**Alternatives considered**: Structured output via a `--json-schema`-style
flag on `claude-code-action` (the literal parenthetical in
`docs/architecture.md`'s sketch) — rejected for this plan: no workflow in
this repo yet exercises such a flag, and introducing an unverified
structured-output mechanism carries more implementation risk than two plain
text files read by `cat`, for the same guarantee. A single agent step doing
the whole job (summarize, `gh pr create`, `gh issue comment`, flip the
label) exactly like the plan/tasks stages' one-shot agent steps — rejected
because, unlike those stages, this one has no natural single-review-branch
target to commit into (the "output" here is two independent GitHub
surfaces that must agree word-for-word), and because it would need
`pull-requests: write`-adjacent tool access on a Haiku-tier step, breaking
the "Haiku only classifies/summarizes" boundary.

## Decision: Idempotency check reuses ANY existing PR from `spec/NNN-slug` to `main`, regardless of state

**Decision**: Before doing anything else that writes to GitHub, check
`gh pr list --head spec/NNN-slug --base main --state all`. If any PR is
returned (open, merged, or closed-unmerged), treat this dispatch as a
duplicate/out-of-order hand-off: log a step-summary note and stop — no new
PR, no metadata commit, no issue comment, no label change (FR-012).

**Rationale**: `spec.md`'s edge case is explicit: "a final pull request that
already exists is reused rather than duplicated" — it does not say "an
*open* pull request"; a specification reaching this stage a second time
(retried/duplicated dispatch) could in principle find its final PR already
merged (a human moved fast) or closed unmerged (rejected). In every one of
those cases opening a second final PR would be wrong: the first one is
already the authoritative review surface (or a human already acted on it),
and duplicating it would confuse the reviewer about which PR is current.
`--state all` is the simplest query that covers every one of those
outcomes with a single `gh` call, mirroring the plan/tasks stages'
existing precedent of checking branch/PR *existence* as the idempotency
signal rather than re-deriving it from `spec-meta.json`'s `stage` field
(which this stage does not otherwise need to read for its guard, unlike the
implement stage's `(stage, iteration)` pair — there is no `iteration`
concept here, and "stage already `review`/`done`" is exactly the state a
reused-PR check already catches without an extra read).

**Alternatives considered**: Keying the guard off `spec-meta.json`'s
`stage` field (skip if already `"review"` or later) — rejected as a weaker
signal than the PR's own existence: a prior run could have failed *after*
opening the PR but *before* committing the metadata update (this stage's
own FR-015 failure path, see below), which would leave `stage` at
`"implement"` while a perfectly good final PR already exists — re-running
in that state must still detect and reuse the existing PR rather than
opening a second one. Checking only `--state open` — rejected per the
Rationale above (merged/closed-unmerged cases would slip through and
trigger a duplicate).

## Decision: The no-diff check runs before the agent step, using an explicit `git fetch origin main`

**Decision**: After the identity/artifact refusal check (below) and the
PR-reuse check, and before the Haiku step ever runs, a deterministic step
does `git fetch origin main` (the spec-branch checkout does not otherwise
have `main`'s history available — `actions/checkout` only fetches the ref
it's given, even with `fetch-depth: 0`) and then checks
`git diff --stat origin/main...HEAD`. If that diff is empty, the stage
reports the anomaly on the lifecycle issue ("the persistent branch carries
no changes against main — nothing to finalize") and stops, never invoking
the agent and never attempting `gh pr create` (FR-013).

**Rationale**: `spec.md`'s edge case is explicit that an empty diff must be
reported "rather than attempting to open an empty pull request" — checking
this deterministically, before spending an agent turn, is strictly cheaper
and avoids a doomed `gh pr create` call (GitHub refuses PRs with no
commits between the two refs) that would otherwise need its own error
handling. `git fetch origin main` is the natural fix for the missing-ref
problem, symmetric with how the implement stage's outcome-detection step
already does `git fetch origin "+refs/heads/spec/$SLUG:..."` to reach a ref
its checkout didn't originally have.

**Alternatives considered**: Letting `gh pr create` fail naturally on an
empty diff and catching that failure — rejected: it conflates "genuinely
nothing to finalize" (an expected, reportable anomaly per FR-013) with
"our own work failed" (FR-015's different, retry-oriented failure
reporting), which would blur two edge cases `spec.md` treats as distinct.

## Decision: The identity/artifact refusal check is the first thing the job does, mirroring every prior stage

**Decision**: Immediately after checkout + `speckit-context`, validate
`spec_dir` against `^specs/[0-9]{3}-[a-z0-9][a-z0-9-]*$`, `issue` against
`^[0-9]+$`, and `converged` against `^(true|false)$`; then, after checking
out `spec/NNN-slug`, verify `spec.md`, `plan.md`, `tasks.md`, and
`spec-meta.json` all exist and that `spec-meta.json`'s own `issue` and
`spec_dir` fields match the dispatch inputs. Any mismatch fails the job
loudly (`::error::`, `$GITHUB_STEP_SUMMARY`) before the PR-reuse check, the
no-diff check, or the agent step ever run (FR-014).

**Rationale**: Identical in shape to the implement stage's "Verify spec
artifacts match the dispatch" step (`specs/005-implement-converge/`) and
the plan stage's "Verify spec artifacts" step — this repo already has an
established refusal contract for "the hand-off doesn't match a valid
specification," and finalize's version of the same problem (FR-014) is not
different enough to invent a new shape for.

**Alternatives considered**: None seriously — every implemented stage uses
this exact pattern; deviating would be the first stage-specific
inconsistency in a chain of four (soon five) identical refusal checks.

## Decision: The metadata commit (`stage: "review"`) lands only after the final PR is verifiably open

**Decision**: `gh pr create`'s own step is `continue-on-error: true`; a
following deterministic step verifies a PR now exists at
`spec/NNN-slug → main` (via `gh pr list`). Only on that verified success
does the stage (a) commit `spec-meta.json` (`"stage": "review"`) directly
onto `spec/NNN-slug` and push, (b) post the remaining-manual-work file's
content to the lifecycle issue, and (c) flip the issue's label to
`stage:review`. If PR creation cannot be verified, none of (a)–(c) happen;
instead the stage posts a failure comment to the lifecycle issue (FR-015)
and the job ends failed, leaving `spec-meta.json` exactly as the implement
stage last left it (`stage: "implement"`) so a later dispatch's PR-reuse
check still finds no PR and correctly retries the whole thing.

**Rationale**: This ordering is what makes the PR-reuse decision above
actually safe to rely on across retries: if the metadata update landed
*before* PR verification and PR creation then failed, `spec-meta.json`
would claim `"review"` with no PR to show for it, and nothing would ever
retry finalization (the durable record would be lying). Verifying first
and writing the record last means the record is only ever advanced once
its precondition is independently confirmed true — the same
verify-then-advance discipline the plan stage's "Verify plan PR and flip
stage label" step already established (label/record changes are the last
thing that happens, gated on a deterministic existence check, never on the
agent step's own exit code alone).

**Alternatives considered**: Advancing `spec-meta.json` inside the same
step that calls `gh pr create` (optimistic, matching the plan stage's
single-agent-step pattern where the agent itself edits `spec-meta.json` as
part of its own commit before opening the PR) — rejected here specifically
because this stage's PR-opening step is deterministic bash, not an agent
commit-and-push; there is no "the agent's own commit already includes the
metadata bump" shortcut available, so an explicit ordered verify-then-write
is both necessary and simple to express as two separate steps.

## Decision: "How to see it" (compare link + changed files) is computed deterministically, not by the agent

**Decision**: A deterministic step (same one that does the no-diff check,
since it already has `origin/main` fetched) computes a GitHub compare link
(`https://github.com/${{ github.repository }}/compare/main...spec/NNN-slug`)
and the changed-file list (`git diff --name-only origin/main...HEAD`,
capped at a readable count with a "+N more" tail for very large diffs) as
step outputs, independent of the Haiku step.

**Rationale**: FR-004 requires "how to see it (a link to the changes and
the key files touched)" — both halves are mechanically derivable from git
and GitHub's own URL scheme with no judgment required, so computing them
deterministically is strictly more reliable than asking an LLM to
transcribe a URL or a file list correctly, and it shrinks the Haiku
step's job to the two things that actually need language understanding: a
narrative summary of *what* changed, and identifying which `tasks.md`
items are inherently human-only (not just still unchecked) — the part
`spec.md`'s Assumptions section reserves genuine judgment for ("this stage
extracts them rather than deciding what is or is not manual" — extraction
of an *existing* human/unchecked signal in the text is exactly a
summarization task, unlike inventing a URL).

**Alternatives considered**: Having the Haiku step compute and report the
compare link and file list itself (as part of its one output) — rejected
as unnecessary risk (transcription errors) for zero benefit, since the
deterministic step already has every fact it needs in its own git checkout.

## Decision: The ⚠️ not-converged banner's task count reads the same remaining-manual-work file, not a separate tally

**Decision**: When `converged=false`, the PR-body-assembly step counts the
non-empty lines in the Haiku step's remaining-manual-work output file and
uses that number in the "⚠️ Not fully converged — N tasks remain" banner
(FR-010), rather than computing N a second way (e.g., grepping `tasks.md`
for unchecked checkboxes independently).

**Rationale**: `spec.md`'s User Story 2 requires the remaining-manual-work
list shown in the PR and on the issue to match exactly (SC-003); if the
banner's count came from a *different* extraction than the list directly
below it in the same PR body, the two could disagree (e.g., a checked-off
item that is still human-only, or a phrasing the checkbox-grep misses) and
a reviewer would trust the wrong number. Deriving N from the same file the
rest of the report already uses is the only way to guarantee the banner
and the list never contradict each other.

**Alternatives considered**: Counting unchecked (`- [ ]`) lines in
`tasks.md` directly via `grep -c` for the banner — rejected because it can
diverge from the Haiku-extracted list (which also includes human-only
items regardless of checkbox state per `spec.md`'s Assumptions), reopening
the exact disagreement risk this decision exists to close off.

## Decision: FR-006's "no manual work remains" fallback is substituted deterministically in both places

**Decision**: If the Haiku step's remaining-manual-work file is empty or
contains only whitespace, the deterministic step that assembles the PR
body substitutes the literal sentence "No manual work remains." for that
section, and the deterministic step that posts the lifecycle-issue comment
substitutes the identical sentence — both checked with the same
"is the file empty" test against the same file.

**Rationale**: FR-006 requires this exact non-omission behavior in *both*
the PR and the issue; performing the same empty-check against the same
file in both consuming steps is the natural extension of the "one file is
the single source of truth" decision above, and needs no agent involvement
(an empty-or-not check is purely mechanical).

**Alternatives considered**: Asking the Haiku step to write the fallback
sentence itself when it finds nothing — rejected as strictly more moving
parts (the model must remember an exact required sentence) for a check
that a one-line `[ -s file ]` test already handles deterministically and
identically everywhere it's needed.
