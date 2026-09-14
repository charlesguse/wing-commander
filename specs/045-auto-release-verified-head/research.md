# Phase 0 Research: Auto-Release After Merged Features Pass a Scheduled End-to-End Verification

Input: `spec.md` (already clarified — three clarification sessions resolved
FR-008/FR-008a lifecycle coverage, FR-002 cadence shape, FR-017/17a/17b
patch-vs-minor). No `[NEEDS CLARIFICATION]` markers remain in the spec, so
this phase resolves *technical* unknowns — how to build what the spec
already decided, not what to decide. Each entry below is a Decision /
Rationale / Alternatives triad, per the plan template's format. Prior-art
citations refer to files read directly during research; none of this is
guessed.

## D1. Workflow shape: one self-contained file, not a stage+wrapper pair

**Decision**: `.github/workflows/auto-release.yml` is a single file that
owns its own triggers (`schedule` + `workflow_dispatch`) directly. It does
**not** declare `on: workflow_call`, so it is not picked up by
`wc_published_stages.py`/Gate 1a's published-stage closure check, and it is
not split into a `wing-commander-auto-release.yml` wrapper.

**Rationale**: The stage+wrapper split (Constitution VII) exists so that
*adopters* can pin the reusable logic (`uses: owner/repo/…@ref`) while a
repository-specific wrapper translates ambient `github.event.*` facts
(issue number, comment author, PR head ref) into typed inputs the stage
itself is forbidden to read. Auto-release has neither of those properties:
it is not something an adopter repository would ever consume (it releases
*this* repository, not theirs), and its two triggers — `schedule` and
`workflow_dispatch` — carry no ambient event payload that needs
extraction; `workflow_dispatch`'s inputs are already declared, typed, and
optional (FR-005 just needs the trigger to exist, not a payload). This is
exactly `release.yml`'s own shape: a single `workflow_dispatch`-only file
with no wrapper, no `workflow_call`, gating its own job with `permissions:`
and `if:` inline. Auto-release extends that same shape with a `schedule`
trigger.

**Alternatives considered**: Mirroring `auto-update-spec-kit.yml`'s
stage+wrapper split was rejected — that split earns its keep there because
the stage has *four* real triggers (`schedule`, `workflow_dispatch`,
`pull_request: closed`, `issue_comment: created`), three of which need
real event-field extraction into a `trigger` enum input. Copying the split
here would add a wrapper file whose only job is `if: vars.…PAUSED != 'true'`
around a single `uses:` line — machinery with no ambient state to
translate.

## D2. Kill switch

**Decision**: repository variable `WING_COMMANDER_AUTO_RELEASE_PAUSED`,
checked as a job-level `if: vars.WING_COMMANDER_AUTO_RELEASE_PAUSED !=
'true'` on every job in `auto-release.yml` (not a stage-side write-suppress
step).

**Rationale**: `watchdog.yml` carries a **deprecated** stage-side
`write-suppression` shim precisely because a stage-side-only pause still
runs and bills for `collect`/`diagnose`/`triage` before suppressing
writes; the current, correct pattern lives job-level in the wrapper
(`wing-commander-8-watchdog.yml:60,93`, `wing-commander-8b-watchdog-self.yml:49`)
and in `wing-commander-auto-update-spec-kit.yml:26`. Because auto-release
has no wrapper (D1), the job-level gate lives directly in
`auto-release.yml` itself — the same file that owns the trigger, which is
what the watchdog precedent is actually optimizing for (stop the job from
starting, not just from writing). This satisfies FR-006/SC-009 (paused ⇒
zero jobs, zero agent invocations, zero writes, zero billing) without
reintroducing the shape the watchdog's own history flags as wrong.

**Alternatives considered**: A stage-side check after detection — rejected
per the watchdog's own documented lesson above.

## D3. Cadence

**Decision**: a fixed daily cron, `"9 9 * * *"`, declared directly in
`auto-release.yml`'s `on.schedule`.

**Rationale**: FR-002 is already resolved by the spec's own clarification
session — fixed interval in the workflow file, no repository-variable
knob, matching `wing-commander-rebase.yml` (`17 4 * * *`),
`wing-commander-7-cleanup.yml` (`53 6 * * *`),
`wing-commander-auto-update-spec-kit.yml` (`13 7 * * *`),
`wing-commander-private-image-dogfood.yml` (`37 8 * * *`), and
`lint-workflows.yml` (`43 5 * * *`). `9 9 * * *` continues that de-facto
"spread scheduled ticks across the early morning UTC hours" convention
without colliding with an existing minute/hour pair; the exact value is a
one-line, PR-reviewed knob per FR-002, not load-bearing design.

**Alternatives considered**: none — the spec's own clarification already
closed the "repository variable vs. fixed interval" question.

## D4. Detecting unreleased work costs nothing extra

**Decision**: "is there new work" and "has this head already been
auto-released" are answered by the *same* single check: does `git tag
--points-at HEAD` (restricted to `vX.Y.Z` exact tags, excluding the
floating `vX` major tags) return anything. If yes, either the tag predates
HEAD (nothing new) or HEAD already carries the most recent release's tag
— both are no-ops. Latest release tag is resolved as the highest `vX.Y.Z`
by semver ordering among exact tags (never the floating major).

**Rationale**: This is a Constitution IX read: no extra state (a "have we
already released this head" ledger) is needed, because a passing
auto-release attempt's own side effect — the tag it caused `release.yml`
to create — *is* the record. FR-022 ("one head yields at most one
automatic release") and FR-003/FR-004 (no-op paths) fall out of one
`git`/`gh` read rather than two independently-maintained checks that could
drift. This is also why the edge case "main advances while the end-to-end
run is in flight" (spec Edge Cases) is safe without extra locking beyond
D9's concurrency group: if main moved during a run, dispatch happens for
the head that was actually verified (captured once, at detection time,
into a job output), and the *next* tick's detection re-reads main's
current tip independently.

**Alternatives considered**: a dedicated "last verified head" file/variable
— rejected as exactly the kind of extra state Constitution IX and the
spec's own FR-002 rationale (state the no-op path must read correctly, for
a knob that moves rarely) warn against; the tag itself is already that
record and cannot drift from what `release.yml` actually did.

## D5. Patch-vs-minor signal collection

**Decision**: enumerate merge commits between the latest release tag and
the verified head (`git log <tag>..<head> --merges --format=%H`), extract
each merged PR number from its merge/squash commit message (GitHub's
`Merge pull request #NNN` or `(#NNN)` squash suffix — both forms already
appear in this repository's own history), then `gh pr view NNN --json
labels` for each and look for a fixed label name, **`release:minor`**. Any
one occurrence anywhere in the range ⇒ `minor`; none ⇒ `patch` (FR-017,
FR-017a, FR-017b).

**Rationale**: matches the spec's own resolved clarification exactly
("any single minor signal in the range wins... a missing label degrades
to a patch"). A **label**, not a PR body/title heuristic, is the
authoritative signal — consistent with this repository's existing use of
labels as trusted, maintainer-applied signals (`spec-request`,
`model:opus`, `stage:*`) rather than free-text content, which also keeps
Principle V's "untrusted content is never instructions" intact: the
version decision never parses PR prose.

**Alternatives considered**: reading PR titles/bodies for a keyword —
rejected, since PR bodies are user-authored content and Principle V holds
that untrusted content must never gate a decision; a label requires a
maintainer's deliberate act, same as `model:opus`.

## D6. The end-to-end test repository's "per-run branch" is its default branch

**Decision**: the end-to-end test repository's **default branch** is the
"per-run branch" FR-010 describes. Each attempt force-resets it (orphan
commit, same technique as D7) rather than resetting some other,
non-default branch.

**Rationale**: this is the one place spec 034's scratch-repository
prior art does not transfer unchanged, and it matters enough to write
down. `auto-update-spec-kit.yml`'s scratch tier never relies on the
scratch repository's *own* GitHub Actions firing — its `e2e-stage` job
drives one Claude Code turn directly against a local clone inside the
*wing-commander* job, so which branch it resets is irrelevant to whether
Actions triggers fire there. Spec 045 is different in kind: FR-008
requires driving the test repository's own **installed, adopter-shaped
wrapper workflows** through real `issues: {types: [labeled]}` and
`pull_request: {types: [closed]}` triggers (the same triggers
`docs/adoption.md`'s minimal wrapper set declares) — and GitHub Actions
only evaluates workflow files for non-ref-scoped events like `issues` and
`schedule` from the **default branch** of the repository the event fires
in, regardless of what other branches exist. Scaffolding onto a
non-default branch would produce a repository whose installed wrapper
workflows never trigger, silently. The end-to-end test repository is
therefore a single-branch repository by construction: its one branch is
simultaneously "the default branch" and "the per-run branch," reset clean
before each attempt.

One consequence flows from this and is folded into the reset step's own
contract (`contracts/e2e-repository-wiring.md`): any issue or PR a
previous attempt left open must be closed as part of the reset, not just
have its branch's tree replaced — an orphan-reset default branch leaves a
stale open PR from a previous run pointing at history that no longer
exists, which is exactly the "previous run's leftovers" FR-010 exists to
neutralize.

**Alternatives considered**: resetting a non-default branch and pointing
the scaffolded wrapper workflows' `push`/`pull_request` triggers at it —
rejected, because `issues: {types: [labeled]}` (what actually starts
`intake.yml`, per `docs/adoption.md`) is not ref-scoped at all and would
still resolve from the default branch regardless; there is no branch
parameter for that trigger to redirect.

## D7. Reset mechanics and scaffold contents

**Decision**: reuse the exact orphan-branch force-reset git sequence
`auto-update-spec-kit.yml`'s `e2e-stage` job already uses (detach, delete
local branch, `checkout --orphan`, remove tracked files, recreate), applied
to the test repository's default branch (D6) instead of a side branch.
Onto the freshly emptied branch, push:

1. `specify init` output pinned at the same `SPECKIT_SUPPORTED_VERSION`
   this repository itself pins (`.github/actions/wing-commander-preflight/action.yml`).
2. The minimal full-pipeline wrapper set exactly as `docs/adoption.md`
   documents it (`wing-commander-1-intake.yml` through
   `wing-commander-7-cleanup.yml`, plus `wing-commander-rebase.yml`), each
   `uses:` line rewritten from `@v2` to `@<verified-head-sha>` — the exact
   commit this attempt is verifying, not a tag (unreleased work has no tag
   yet by definition).
3. One commit, `chore: scaffold end-to-end verification fixture at
   <short-sha>`.
4. `git push --force` over a tokenized URL from a second, narrowly-scoped
   App installation token (D11) — never `gh repo clone`/`gh auth
   setup-git`, matching `auto-update-spec-kit.yml`'s own reasoning for
   avoiding a broader credential helper than the operation needs.

**Rationale**: this is the same "adopter-shaped repository" the spec's own
Input text names, built from the one checked-in example of that shape
this repository has (`docs/adoption.md`'s wrapper snippets), pointed at
the unreleased commit rather than a released tag so the run actually
verifies the head in question (SC-003) rather than whatever the test
repository last happened to pin.

**Alternatives considered**: pinning at `@main` — rejected, because `main`
moves; a maintainer reading the test repository afterward (Assumptions:
"survives every outcome so a maintainer can inspect it") needs the pin to
name the exact commit this attempt verified, and the spec's own edge case
("main advances while the end-to-end run is in flight... a tag must never
land on a commit no end-to-end run ever saw") requires that precision.

## D8. Starting the lifecycle: create, then label, never both at once

**Decision**: `gh issue create --repo <e2e-repo> --title … --body …`
first, with **no** `--label` flag, then a separate `gh issue edit <n>
--add-label spec-request` (or equivalent `gh api …/labels` call) as its
own step.

**Rationale**: GitHub's Actions trigger for `issues: {types: [labeled]}`
fires on a genuine label-add event. Creating an issue with labels attached
in the same API call is reported as an `opened` event, not a `labeled`
one — a wrapper gated on `if: github.event.label.name == 'spec-request'`
(the exact gate `docs/adoption.md`'s wrapper #1 and this repository's own
`wing-commander-1-intake.yml` use) would never fire if the label arrived
bundled with creation. Splitting creation and labeling into two calls is
the only way to produce a real `labeled` event.

**Alternatives considered**: none — this is a hard GitHub Actions
constraint, not a preference.

## D9. Trivial feature fixture (FR-008a)

**Decision**: the issue body driving the end-to-end run describes one
small, fixed, deterministic change (e.g., "add a single new markdown file
under `docs/` stating the verified commit and timestamp") — small and
unambiguous enough that `implement` finishes and `converge` sees
`tasks.md` unchanged after exactly one iteration.

**Rationale**: directly implements the spec's own FR-008a and its
Assumptions ("a fixture sized for one-iteration convergence, not a
realistic feature"). The exact fixture text is an implementation/tasks-
stage detail, not a plan-level design decision, but its *shape*
(single-file, mechanically verifiable, no ambiguity an agent could
interpret two ways) is fixed here so the tasks stage doesn't have to
re-derive the constraint from FR-008a and FR-012 ("did not complete" vs.
"completed and produced the wrong output" both need an output whose
correctness is checkable without judgment).

**Alternatives considered**: reusing spec 034's e2e-stage's single-turn
fixture — rejected, because that fixture only exercises `/speckit-specify`
once and produces no `plan.md`/`tasks.md`/implementation PR; FR-008 needs
a fixture that survives all seven remaining stages after intake.

## D10. Verdict computation is a poll over the issue's own state and labels, plus artifact presence — never agent narration

**Decision**: after kickoff (D8), poll (bounded by the job's own
`timeout-minutes`) `gh issue view <n> --repo <e2e-repo> --json
state,labels` on an interval. Classify:

- `state: OPEN` and the label set has not yet reached `stage:done` /
  `stage:stalled` when the timeout elapses → **did-not-complete** (FR-012).
- `state: CLOSED` with label `stage:done` → provisional pass; then assert
  each documented per-stage artifact actually exists (`spec.md`,
  `plan.md`, `tasks.md` present via `gh api
  repos/<e2e-repo>/contents/specs/<slug>/...` against the merged
  implementation PR's head, and the timeline
  (`gh api repos/<e2e-repo>/issues/<n>/timeline`) shows every
  `stage:{spec,clarify,plan,tasks,implement,review,done}` label having
  been applied at some point, not just the final one) → pass only if every
  assertion holds, otherwise **completed-wrong-output** (FR-012) naming
  which asserted output was missing.
- `state: OPEN` with label `stage:stalled`, or `CLOSED` without
  `stage:done` (the `teardown-rejected` path) → **did-not-complete**.

**Rationale**: this is the direct implementation of Constitution IX and
FR-015 for this feature — release-cutting is a durable action, so what
gates it must be a concrete, machine-readable read, not "the agent said it
finished." `cleanup.yml`'s own terminal signals (issue closed +
`stage:done`, vs. left open + `stage:stalled`, vs. closed unmerged with
neither) are already exactly that: deterministic, GitHub-native state a
poller with `issues: read` on the test repository can read without
touching that repository's Actions logs at all. Checking the timeline for
every intermediate `stage:*` label, not just the terminal one, is what
makes SC-015 ("the number of exercised stages whose documented output went
unasserted is zero") true rather than assumed — a run that skipped straight
from `stage:spec` to `stage:done` through some pipeline defect must not
read as a pass just because the terminal label matches.

**Alternatives considered**: trusting the terminal label alone — rejected
by SC-015's explicit "every exercised stage's output asserted," which a
terminal-label-only check cannot distinguish from a skipped stage.
Watching the test repository's own Actions run logs — rejected as heavier
(needs `actions: read` on a repository this pipeline holds no
administrative right over, and turns a state read into a log-parsing
exercise, reintroducing the "trust narration" problem one layer down).

## D11. Credentials on the test repository

**Decision**: the test repository is onboarded once, by a maintainer,
exactly as `docs/setup.md`/`docs/adoption.md` describe for any adopter
repository — its own `wing-commander-bot` App installation, its own
Claude credential secret, its own `spec-request` label. The `auto-release`
job in *this* repository never supplies Claude credentials to it and never
runs a stage against it directly; it only pushes the scaffold (D7) and
polls (D10). For those two operations it mints a **second**, narrowly
scoped App installation token via `actions/create-github-app-token@v3`
with `owner`/`repositories` set to exactly the test repository —
identical to `auto-update-spec-kit.yml`'s `scratch-token` step — because
the job's own primary token (minted by `wing-commander-context`) is scoped
to the current repository only and 404s against any other, as that prior
run already demonstrated live.

**Rationale**: this keeps the test repository a real, independently
functioning adopter installation (so what gets verified is genuinely "the
published stages as an adopter would run them," per the spec's Input
text), and keeps this repository's own credentials scoped to exactly the
two operations it performs there (push + issue read/write) — no
`actions: read` or content-write beyond the scaffold commit, satisfying
SC-010's "zero repository-administration permissions."

**Alternatives considered**: threading this repository's own Claude
credential through to drive the test repository's stages directly (e.g.
via `workflow_call`) — rejected: `docs/adoption.md`'s stages are
`workflow_call`-invoked by *that* repository's own wrappers, and a
cross-repository `workflow_call` from this repository's job into the test
repository's wrapper is not how the published contract works (a wrapper
`uses:`-calls the stage, not the reverse); the only cross-repository
mechanism this repository has for kicking off *another* repository's
installed automation is the event it's already wired to react to
(`issues: labeled`), which is what D8 uses.

## D12. Dispatching `release.yml`

**Decision**: `gh workflow run release.yml -f version=<computed> -f
breaking=false -f breaking-notes=` run with `GH_TOKEN: ${{ github.token }}`
(the default `GITHUB_TOKEN`, not the wing-commander App token), inside a
job that declares `permissions: { actions: write, contents: read }`. After
dispatch, poll `gh run list --workflow=release.yml -b main --json
databaseId,status,conclusion -L 1` (or `gh run watch`) for that run's
conclusion before reporting a version as released.

**Rationale**: `release.yml` is `workflow_dispatch`-only — it has no
`workflow_call` trigger, so it cannot be `uses:`-invoked as a reusable
workflow; `gh workflow run` is the only mechanism, and it is this
repository's own established idiom for cross-workflow dispatch
(`implement.yml`'s "Dispatch next step" step, `tasks.yml`, `plan.yml`,
`pr-conversation.yml`, `wing-commander-rebase.yml`,
`wing-commander-watchdog-test.yml` all use exactly this shape). The
`github.token`-not-App-token choice is likewise not a new decision but a
documented, incident-backed constraint already recorded in
`implement.yml`'s own comment ("the wing-commander-bot App token has no
actions permission") and in Gate 12's own docstring, which names a real
403 (issue/spec 005) caused by using the wrong token for exactly this
call. Polling the dispatched run's own conclusion, rather than treating
`gh workflow run`'s zero exit status as success, is what makes FR-029
possible: `gh workflow run` only confirms the dispatch was *accepted*, not
that `release.yml`'s own Gate 1a/1b or tag-creation step later succeeded.

**Alternatives considered**: none for the dispatch mechanism —
`workflow_call` reuse is unavailable given `release.yml`'s trigger, and
`gh workflow run` with `github.token` is the only idiom this repository
uses anywhere for this exact cross-workflow shape, with a specific
documented incident against the alternative (App token).

## D13. Failure reporting is a durable, deduplicated issue on this repository — not the `wing-commander-callout` composite

**Decision**: on any failure outcome, search this repository's own open
issues for the fixed label `auto-release:failed`
(`gh issue list --repo charlesguse/wing-commander --label
auto-release:failed --state open`). If one exists, update it with a new
comment carrying the current attempt's head/check/expected/observed; if
none exists, file a new one with that label. Every attempt (pass, no-op,
fail, or paused-via-skip) also writes a `$GITHUB_STEP_SUMMARY` stating its
outcome in one line (FR-030).

**Rationale**: `wing-commander-callout` is scoped to *an existing spec's
lifecycle issue* (its own header: "the single enforcement point for the
action-required/informational convention" tied to a spec's issue) — there
is no such issue here, since an auto-release attempt is not a spec.
`auto-update-spec-kit.yml`'s own failure path already solves exactly this
shape of problem (a scheduled, non-spec-driven job that must file *one*
durable, deduplicated issue rather than one per tick): its dedup-by-label
`gh issue list --label auto-update:failed --state open` check before
opening a new issue is the direct precedent FR-028
("consecutive failures... update one durable report") asks for, reused
here with a new, feature-specific label
(`auto-release:failed`) rather than overloading the auto-updater's own.

**Alternatives considered**: reusing `wing-commander-callout` against a
synthetic or pinned "auto-release" tracking issue — rejected as an
unnecessary new persistent object (a pinned issue nothing else in the
repository's lifecycle model expects) when the auto-updater's own
dedup-by-label pattern already does the job with one fewer moving part.

## D14. Concurrency: at most one attempt in flight

**Decision**: `concurrency: { group: wing-commander-auto-release,
cancel-in-progress: false }` at the workflow level in `auto-release.yml`.

**Rationale**: matches `release.yml`'s own top-level concurrency group
(`wing-commander-release`, `cancel-in-progress: false`) — a second
scheduled tick or manual dispatch that fires while one is already running
queues rather than racing it or cancelling it mid-verification (FR-023).
Combined with D4 (no-op re-detection costs nothing), a queued run that
starts after a prior one already released the head it would have targeted
simply finds nothing new and no-ops — no separate "already attempted this
head" bookkeeping needed.

**Alternatives considered**: `cancel-in-progress: true` — rejected,
because cancelling a live end-to-end verification mid-run to start a
redundant one wastes the exact expensive resource (a real multi-stage
agent-driven run) the no-op path exists to conserve, and produces an
ambiguous "did this head get verified or not" state, exactly what FR-016
requires stay clean.

## D15. Gate-suite touch points flagged for the tasks stage (not resolved here)

Recorded so the tasks stage doesn't have to re-derive them from a cold
read of the gate suite:

- `auto-release.yml` will contain non-trivial dynamic shell (git tag
  parsing, the reset sequence, the polling loop) of the same shape
  `watchdog.yml`, `auto-update-spec-kit.yml`, and `pr-conversation.yml`
  already carry — the tasks stage should decide, and record a reason
  either way, whether it joins `shell_exempt` (`lint-workflows.yml`'s
  Gate 1a pass-2 array) alongside those three, or `shell_linted` with any
  needed cleanup. Because `auto-release.yml` declares no `workflow_call`,
  Gate 1a's closure check (every workflow declaring `workflow_call` must
  be in one of the two arrays) does not *force* this choice the way it
  would for a published stage — but the file still runs under Gate 1a
  pass-1 (`verify-actionlint.py` over every workflow) regardless, and a
  deliberate `shell_exempt`/`shell_linted` choice is still worth recording
  once the exact shell is written, per Constitution VIII's "every gate
  must be reachable... and every failure branch exercised by a fixture."
- Any change to `auto-release.yml`'s `if:`/`continue-on-error:` steps
  needs a pass from the `review-step-gating` skill (CLAUDE.md), given the
  number of gated steps this design implies (pause check, no-op early
  exit, infra-unreachable early exit, timeout branch, dispatch-failure
  branch).
- `run-local-gates.py` should keep working unchanged unless a new
  `.github/scripts/verify-*.py` gate is introduced; this plan does not
  require a new gate script — the deterministic checks described in D10
  live inline in the workflow, the same way `auto-update-spec-kit.yml`'s
  own readback checks do, not as a separate `.github/scripts/verify-*.py`
  file, since nothing here is asserting a property of the *workflow files
  themselves* (which is what the `verify-*.py` gate family checks) as
  opposed to a property of a live run.
