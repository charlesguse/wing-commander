# Phase 0 Research: Auto-Rebase

`spec.md` carries no `[NEEDS CLARIFICATION]` markers — the three that
existed pre-planning were resolved from lifecycle issue #33's answers and
are recorded in `checklists/requirements.md`'s Notes (FR-002, FR-011,
FR-012). This document resolves the remaining *technical* unknowns needed
to turn the spec into a plan, each as Decision / Rationale / Alternatives.
`docs/architecture.md`'s "Auto-rebase (`speckit-rebase.yml`, stub)"
section already sketches the shape this research confirms and sharpens.

## D1 — Discovering the in-flight branch set (FR-002)

**Decision**: Enumerate remote branches matching `spec/*` via
`git ls-remote --heads origin 'spec/*'` from a single bootstrap checkout
(no per-branch checkout needed for discovery). For each, read
`specs/<slug>/spec-meta.json` **from that branch's own tip** —
`git show spec/<slug>:specs/<slug>/spec-meta.json` — never from `main`.
Include the branch only if: the file parses as JSON, `.spec_dir` equals
`specs/<slug>` (self-identity check, same idiom as
`speckit-7-cleanup.yml`'s "Verify spec artifacts" steps), and `.stage` is
not `"stalled"`.

**Rationale**: `main`'s copy of `specs/NNN-slug/spec-meta.json` is only as
fresh as the last merge that touched that path (intake's spec PR, or a
final merge) — it does **not** track the plan/tasks/implement stages'
commits, which land on `spec/NNN-slug` itself and never touch `main`
until final merge. Reading `main` would misclassify a spec that has since
been marked `stalled` (or has advanced past `spec`) as still eligible.
The branch tip is the only place the current `stage` value lives while a
spec is mid-pipeline. Scoping to `spec/*` (not `spec-draft/*`) matches
`docs/architecture.md`'s existing stub ("for each open `spec/**` branch")
and spec.md's Assumptions ("persistent working branch" = the long-lived
per-spec integration branch `spec/NNN-slug`, not the short-lived draft PR
head) — `spec-draft/*` branches are out of this stage's scope.
`stage == "done"` branches are excluded implicitly: `speckit-7-cleanup.yml`
deletes `spec/NNN-slug` in the same job that flips the issue to `done`, so
a `spec/*` branch simply won't exist anymore by the time this stage looks
for it, absent a narrow race with cleanup's own run (harmless — the next
run's `ls-remote` no longer lists it).

**Alternatives considered**: Reading `specs/*/spec-meta.json` off `main`
directly (cheaper — one checkout, no per-branch `git show`) — rejected as
stale per above. Checking out every `spec/*` branch in full to read the
file — correct but far more expensive than `git show`, with no benefit
over the ref-scoped read.

## D2 — Per-branch isolation (FR-010)

**Decision**: Two jobs. `discover` (single run) computes and outputs a
JSON array of `{slug, spec_dir, issue}` for the branches D1 selects,
already filtered by D6's dedup check. `rebase` is a
`strategy: {matrix: {include: fromJson(needs.discover.outputs.branches)}, fail-fast: false}`
job, one instance per branch, each with its own
`concurrency: speckit-rebase-<slug>` group (the same per-spec
concurrency idiom every other stage uses).

**Rationale**: GitHub Actions' own matrix semantics give per-branch
failure isolation for free — one matrix entry failing, timing out, or
being cancelled has no effect on sibling entries when `fail-fast: false`
— which is exactly FR-010's requirement, without hand-rolling a
continue-on-error loop over branches in a single job. An empty
`branches` array simply runs zero matrix jobs; the workflow still
succeeds, satisfying "MUST complete without error when there are no
in-flight working branches."

**Alternatives considered**: A single job looping over branches with
`continue-on-error` per iteration inside one `run:` step — rejected: a
mid-loop `git` or `gh` failure is harder to contain than an OS process
boundary, and it loses the individually-inspectable job run per branch
that the matrix approach gives for free (useful when debugging a stuck
rebase).

## D3 — Clean-rebase publish, and how it also satisfies FR-011

**Decision**: On the matrix runner: checkout `spec/<slug>` with
`fetch-depth: 0` (this also populates the local remote-tracking ref
`refs/remotes/origin/spec/<slug>` — the lease value), `git fetch origin
main:refs/remotes/origin/main` (fetches **only** `main`, never
re-fetches the working branch's own ref), record `before=$(git rev-parse
HEAD)`, run `git rebase origin/main`. On success with `after=$(git
rev-parse HEAD)` unchanged from `before`: no-op, nothing to publish
(Acceptance Scenario 1.3). On success with `after != before`: `git push
--force-with-lease origin HEAD:refs/heads/spec/<slug>`.

**Rationale**: `--force-with-lease` (no explicit expected-SHA argument)
compares the remote's current tip against the local
`refs/remotes/origin/spec/<slug>` ref *as recorded at fetch/checkout
time*. Because the job never re-fetches that specific ref after checkout,
this comparison is exactly "has anyone published to this branch since we
started reading it" — precisely FR-011's concurrent-update guard, for
free, with no custom SHA-tracking needed. If the push is rejected, the
job logs it and exits without commenting (edge case: "skips the branch
silently... relies on the next run"). This is why the workflow must never
run a bare `git fetch origin` (no refspec) between checkout and push —
that would silently refresh the lease and defeat the guard; `git fetch
origin main:refs/remotes/origin/main` is scoped deliberately to avoid it.
Pushing through the App-token identity (`speckit-context`, reused
unchanged from every other stage) is what makes the *next* run's loop
guard (D5) correctly recognize this push as the pipeline's own.

**Alternatives considered**: Plain `git push --force` — rejected, it has
no built-in staleness check and would silently clobber a concurrent
legitimate update, violating FR-011 outright. Manually capturing the
pre-checkout remote SHA and passing it as `--force-with-lease=<ref>:<sha>`
— equivalent in effect to the no-argument form given the fetch discipline
above, but adds a manual capture step for no behavioral gain; rejected
for simplicity.

## D4 — AI-assisted conflict resolution, scoped and verified (FR-005, FR-006)

**Decision**: When `git rebase origin/main` stops on conflicts,
`anthropics/claude-code-action@v1` runs on the same runner, mid-rebase,
`--model claude-sonnet-5` (constitution II's implementation tier — this
is conflict-resolution work over code/prose, not a triage/summary task,
so `claude-haiku-4-5` is too light, and it is not spec-authoring, so
`claude-opus-4-8` is unwarranted; matches `docs/architecture.md`'s stub
verbatim). Tool allowlist: `Read, Edit, Grep, Glob,
Bash(git status:*), Bash(git diff:*), Bash(git add:*),
Bash(git rebase --continue:*), Bash(git rebase --abort:*)` —
no arbitrary `Bash`, no `git commit`/`git push`/`gh` access (deterministic
steps own every publish and every GitHub write, matching every other
stage's shape). Prompt: resolve **only** the conflicts blocking the
in-progress rebase, one stop at a time (`git status` → inspect conflict
markers → edit only the conflicted hunks → `git add` → `git rebase
--continue` → repeat), touching no file that isn't currently
conflict-marked; if truly stuck, `git rebase --abort` rather than leaving
a half-resolved stop.

A deterministic post-step then verifies scope, rather than trusting the
agent's self-report: before the agent starts, record `pre_tip=$(git
rev-parse HEAD)` (the original branch tip) and the ordered list of
commit SHAs `git rev-list --reverse origin/main..HEAD` about to be
replayed. After the agent finishes and the rebase reports complete
(`git status` shows no `rebase-merge`/`rebase-apply` in progress), walk
the same-length, same-order sequence of replayed commits on the new tip
(`git rev-list --reverse origin/main..HEAD`) pairwise against the
original sequence; for each pair, the rebased commit's touched-file set
(`git show --name-only`) must be a subset of (that commit's *original*
touched-file set, from the pre-rebase equivalent) **union** the set of
files that were ever reported conflicted at any stop (accumulated into a
temp file by the agent's own `git status`/`git diff --diff-filter=U`
calls, per the prompt above). Any file appearing that isn't in either set
is an out-of-scope edit — treat identically to "cannot resolve" (D5
abandon path), never publish it.

**Rationale**: Tool allowlisting is the primary, always-on guard (an
agent that can't run arbitrary shell or push can't smuggle unrelated
changes past the runner's own checkout or off the runner at all); the
post-step is a cheap, deterministic second gate specifically for FR-005's
"MUST NOT introduce edits unrelated to resolving the conflicts," matching
this codebase's existing pattern of a narrow, verifiable deterministic
check layered on top of an agent step (e.g. `speckit-7-cleanup.yml`'s
"verify the plan PR exists" idiom applied here to "verify the diff is
scope-limited"). The commit-count/order assumption holds because the
tool allowlist forbids `--skip`, `commit --amend`, and interactive
rebase — the only two ways to legally finish this rebase are "same
commits, same order, `--continue`'d" or "`--abort`."

**Alternatives considered**: Trusting the agent's own "I only changed the
conflicted files" report — rejected, matches this repo's general
practice of never trusting an agent's self-report for a safety property
when a cheap deterministic check exists. Diffing the full rebased branch
against `origin/main` and asserting it doesn't touch files outside the
recorded conflict set — rejected: that diff also includes every file the
spec's *own* commits always changed (its normal diff against main), which
has nothing to do with conflict scope, so it can't distinguish "resolved
a conflict" from "read an unrelated file" the way the per-commit
pairwise-subset check can.

## D5 — Abandonment leaves the branch untouched (FR-007)

**Decision**: Any failure path (rebase itself errors outright, the agent
step errors/times out, the agent self-aborts, or D4's post-step scope
check fails) runs `git rebase --abort` if a rebase is still in progress,
then simply lets the ephemeral runner checkout be discarded — no push is
ever attempted on this path.

**Rationale**: The working branch on GitHub is never modified unless a
`git push` happens; every publish in this design (D3, D6) is a single,
explicit, guarded step. So "leave the branch in its original pre-attempt
state" requires no restore logic at all — it's the natural consequence of
never having written to the remote. `git rebase --abort` only cleans up
the *local* runner-only rebase state so the job can exit cleanly and (on
the escalation path, D6) read `pre_tip`'s `spec-meta.json` for the issue
number without a dangling rebase confusing that read.

**Alternatives considered**: Explicitly re-pushing the pre-rebase SHA "to
be safe" — rejected as both unnecessary (nothing was pushed) and risky
(a needless force-push is itself a window for clobbering a concurrent
legitimate update, the exact thing FR-011 guards against).

## D6 — Escalation and per-stall dedup (FR-008, FR-012, FR-013)

**Decision**: On abandonment, first re-derive the lifecycle issue from
`pre_tip`'s `specs/<slug>/spec-meta.json` (`.issue`, already validated
self-consistent in D1's discovery pass — re-read here since discovery and
this abandonment can be minutes apart on a long AI turn). If it resolves:
comment on that issue asking for human help, and post an HTML-comment
marker in the same comment: `<!-- speckit-rebase: blocked branch-sha=<pre_tip> main-sha=<origin/main tip> -->`.
Add label `rebase:blocked` (created with `gh label create ... --force`,
matching every other stage's label-provisioning idiom). If the issue
cannot be resolved or is inconsistent: skip the comment entirely, log why
via `::warning::` and `$GITHUB_STEP_SUMMARY` (the loudest channel
available — there is no pull request to comment on here, unlike
`speckit-7-cleanup.yml`'s refusal path), and take no further action on
that branch this run (spec.md's edge case: "must record why rather than
acting blindly on an unidentified specification" — read as *don't act on
it at all*, not just "don't escalate").

Dedup (FR-012) is enforced in `discover`, before a branch is even added
to the matrix: if the issue carries label `rebase:blocked`, fetch its
most recent comment matching the marker prefix, parse `branch-sha`/
`main-sha`; if both equal the branch's current tip and `main`'s current
tip, exclude the branch from this run's matrix entirely (no agent turn,
no comment). If either differs (a human pushed a fix to the branch, or
`main` advanced again since the stall), include it — a repeat failure
posts a **new** comment with a refreshed marker (so the timestamp and
SHAs are current) rather than silently reusing the stale one; a success
removes the `rebase:blocked` label (auto-recovery, so the flag doesn't
outlive the problem it names).

**Rationale**: `spec-meta.json` on the working branch is explicitly
off-limits for recording "this rebase is currently blocked" state (D5
promises byte-for-byte preservation), so the marker has to live somewhere
else GitHub-native; the lifecycle issue is the only other per-spec
surface every stage already writes to (constitution III). Embedding the
two SHAs directly in the comment body (rather than, say, a separate
label per SHA, which would churn constantly) keeps the dedup check to one
`gh issue view --json comments,labels` call and needs no new persisted
file. Re-deriving the issue at abandonment time (rather than reusing
whatever `discover` resolved) matters because AI-assisted resolution can
run long; re-reading keeps the reported issue number accurate to the
actual failing attempt.

**Alternatives considered**: Storing the blocked marker in
`spec-meta.json` — rejected outright by D5's untouched-branch guarantee.
A separate sentinel branch or repo variable per spec — rejected as new
infrastructure with no GitHub-native precedent in this pipeline
(constitution III favors comments/labels the maintainer already reads).
Comparing only `main-sha` (not `branch-sha`) for dedup — rejected: it
would miss the "a human manually fixed the branch, main hasn't moved"
recovery case spec.md's edge case explicitly names ("until it changes...
the working branch itself moves").

## D7 — Trigger and loop protection (FR-001, FR-009)

**Decision**: Keep the stub's existing trigger and gate verbatim —
`on: push: branches: [main]` plus `schedule: cron: "17 4 * * *"`, with
`discover` gated `if: ${{ !endsWith(github.actor, '[bot]') }}`.

**Rationale**: On a `push` event, `github.actor` is the pusher; every
pipeline write already lands through the `speckit-bot` App
(`<bot-slug>[bot]`), so this gate is already exactly "ignore main-line
advances that originate from the pipeline's own automation" (FR-009).
On a `schedule` event there is no pusher in the FR-009 sense — the
condition still evaluates (`github.actor` on a scheduled run is not a
`[bot]` actor) and the job runs regardless, which is correct: FR-001
requires the nightly run regardless of who last pushed. No change is
needed from the already-drafted stub.

**Alternatives considered**: Filtering on a specific commit-message
marker instead of actor — rejected, actor-based filtering is the
established idiom (`docs/architecture.md`'s Foundations section) and
needs no new convention.

## D8 — Verification approach

**Decision**: Same as every other stage in this repo — no automated test
suite; `quickstart.md`'s scenarios are run by hand against scratch
specifications and a scratch conflicting commit on `main`, cross-checked
against `docs/architecture.md`'s Auto-rebase section and the constitution.

**Rationale**: Consistent with stages 2–6 (`specs/00{2,3,5,6,7}-*`), all
of which validate CI workflow changes this way; no test framework exists
for GitHub Actions workflow bodies in this repository.
