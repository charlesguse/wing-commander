# Phase 0 Research: Unattended Passage of the Pipeline's Human Gates in End-to-End Release Verification

Input: `spec.md`, already fully clarified (Session 2026-09-19 resolved all
three open questions on lifecycle issue #386; no `[NEEDS CLARIFICATION]`
markers remain). This phase resolves *technical* unknowns — how the four
gates get driven inside the existing `verify-e2e` job — not what to decide,
which the spec's Clarifications session already settled.

Each entry is a Decision / Rationale / Alternatives triad, per the plan
template's format. File:line citations are against `auto-release.yml` and
related files as of `53e203b` (the branch head this plan starts from).

## D1. Identity and credential shape (FR-003, FR-003a, FR-011)

**Decision**: a dedicated GitHub user account (never a bot identity),
invited as a collaborator with **Write** access to the test repository
only, authenticating via a fine-grained personal access token scoped to
that single repository with Contents (write), Issues (write), and Pull
requests (write) permissions. The token is stored as a new repository
secret, `WING_COMMANDER_AUTO_RELEASE_E2E_MAINTAINER_TOKEN`, read only by
`verify-e2e`.

**Rationale**: the clarify entry point's actor gate
(`wing-commander-2-clarify.yml:22-27`) rejects `github.event.comment.user.type
== 'Bot'` outright regardless of association, then requires
`author_association` in `OWNER|MEMBER|COLLABORATOR` or that the commenter
is the issue's own author. A collaborator-with-write real user account
satisfies this gate exactly as a maintainer would, with no widening of the
gate itself (FR-012). Write access (not Admin) is sufficient to comment,
open no PRs of its own, and merge PRs: `specs/053-e2e-scratch-provisioning`
records that the disposable test repository carries no branch protection
by adoption default, so merging never needs an admin bypass. Granting
Admin would be an avoidable containment risk this feature does not need to
take (FR-011).

**Alternatives considered**: reusing the existing `wing-commander[bot]` App
identity — rejected outright, it *is* the bot type the actor gate excludes
by design, and widening that gate to accept bots would be exactly the kind
of gate-weakening FR-012 forbids. A second GitHub App installed as a
"maintainer" App — rejected: Apps are always `type: Bot` on the comment
payload; there is no App configuration that presents as a `User`. A
classic (non-fine-grained) PAT — rejected: classic PATs cannot be scoped to
a single repository, so they cannot satisfy FR-011's "no other repository"
requirement by construction; only a fine-grained PAT can.

## D2. Runtime containment check for the new credential (FR-014)

**Decision**: a new step immediately after the existing `token`/`reachable`
steps (`auto-release.yml:181-224`) checks the new secret is non-empty and
that `GH_TOKEN=<secret> gh repo view <e2e-repo> --json viewerPermission`
succeeds and reports `WRITE` or higher. Any failure — secret unset, `gh`
rejects the token, or `viewerPermission` below `WRITE` — produces a
`fail-infra` verdict via `auto-release-verdict.sh`, naming
`WING_COMMANDER_AUTO_RELEASE_E2E_MAINTAINER_TOKEN` as the thing to set, the
same wording shape the existing App-token `reachable` step already uses at
`auto-release.yml:206-219`.

**Rationale**: FR-014 requires the same treatment this job already gives an
unset `WING_COMMANDER_AUTO_RELEASE_E2E_REPO` (`docs/setup.md:126`) — a
named, actionable `fail-infra` outcome, never a crash, and no lifecycle
started that can't be carried to a verdict. Checking `viewerPermission`
rather than merely "the token authenticates" catches the case where the
account exists and the token is valid but was never actually invited as a
collaborator to the test repository — a misconfiguration this job should
name rather than discover as a mysterious merge failure two hours later.

**Alternatives considered**: skip the up-front check and let the first
gate-driving attempt fail naturally — rejected, because that would surface
as a late `fail-gate-stall` after intake has already spent real money
(the two prior failing attempts each did real agent work before stalling),
where an up-front check costs nothing and fails before any spend.

## D3. FR-013's self-repository refusal already covers every new act

**Decision**: no new code. The existing `config` step's self-repository
check (`auto-release.yml:151-168`) already runs before the `token` step,
before D2's new check, and before every downstream act. If the configured
test repository resolves to this repository, the job stops at that check
today, and continues to stop there — nothing this feature adds runs
earlier.

**Rationale**: FR-013 asks only that this refusal be extended to "every
act this feature adds," and the job's own sequencing already achieves
that: D2's credential check and the gate-driving logic (D5 onward) are
strictly downstream of `config`. Adding a second, redundant self-repository
check would duplicate a comparison that can only ever produce the same
answer, which is exactly the kind of pasted-copy CLAUDE.md's "shared logic
has exactly one home" section warns against — here the "one home" is
simply the existing gate, unmodified.

**Alternatives considered**: a second explicit check at the point the
credential is first used — rejected as redundant per the above; considered
briefly because FR-013's wording ("extending the refusal... to every act
this feature adds") could be misread as requiring a new call site, but the
refusal is a job-level precondition, not a per-act guard, and job-level
sequencing already satisfies it.

## D4. Gate-driving integration point: extend the existing poll loop

**Decision**: gate-driving logic runs inside the existing `poll` step's
`while` loop (`auto-release.yml:509-580`), not as new jobs or new steps.
Each iteration, in addition to the existing `gh issue view` terminal-state
check, the loop now also: (a) checks for an open clarification question
and answers it if one is found and the round bound isn't exhausted (D7),
and (b) checks for a mergeable pull request matching the current attempt's
slug at each of the three PR-gated prefixes and merges it if found (D9).

**Rationale**: the poll loop already runs every 30 seconds for up to
`POLL_BUDGET_SECONDS`, already holds the attempt's issue number and repo
context, and is already the single place `auto-release.yml` watches this
attempt's state. Driving gates from a second, independent step would
require re-deriving all of that context and would double the number of
places that read the attempt's live state — a second pasted copy of
context CLAUDE.md's shared-logic section also warns against, just within
one workflow rather than across workflows. Extending the one loop keeps
one home for "what does this attempt's state look like right now."

**Alternatives considered**: separate GitHub Actions jobs per gate,
triggered by watching the test repository's own events — rejected: this
job is schedule/dispatch-only and self-contained by design (no webhook
listener into the test repository), and adding one would mean this feature
touches trigger plumbing FR-004 says must not require published-stage
changes and should not need wrapper-workflow proliferation either.

## D5. Fetch/decide split for gate-driving logic (Constitution VIII)

**Decision**: each gate-driving decision is implemented as a small,
pure script under `.github/actions/_shared/` that takes already-fetched
JSON (via argument or stdin) and returns a decision — never a script that
calls `gh` or the network itself. The `poll` step's shell does the
fetching (as it already does for `gh issue view`) and passes the result to
the decision script, mirroring exactly how `auto-release-verdict.sh`
already separates "build the verdict shape" (pure, in `_shared/`) from
"decide what verdict to build" (the workflow step, which does the `gh`
calls).

**Rationale**: Constitution Principle VIII requires every gate to "run the
same subject with the same arguments locally as it does in CI." A script
that shells out to `gh` against a live test repository cannot be run
locally without that repository existing and being in the right state; a
pure function of already-fetched JSON can be unit-tested with a checked-in
fixture, the same pattern `verify-auto-release-report.py` already uses for
the existing verdict-classification logic. This also keeps `auto-release
-verdict.sh`'s own precedent intact — `contracts/verdict-helper.md`
(spec 049) already established "single-workflow shared logic lives in
`_shared/` as a plain script, not a composite" for exactly this job; this
feature's new scripts follow the identical idiom rather than introducing a
second convention.

**Alternatives considered**: a single new composite action
(`.github/actions/e2e-gate-harness/`) wrapping all gate logic behind one
`uses:` call — rejected: this job is the only caller, so a composite adds
an action-input/output boundary with nothing on the other side to justify
it, and it would sit awkwardly against Principle VII's split (composites
under `.github/actions/**` resolved by *published* stages are compatibility
surface; this logic belongs to the consuming instrument only, exactly
where `auto-release-verdict.sh` already lives).

## D6. Two new decision scripts

**Decision**: two new files under `.github/actions/_shared/`:

- `auto-release-e2e-clarify-decision.sh` — given the fetched issue-comment
  list (JSON: `[{id, createdAt, author, body}]`), the harness's own
  identity login, and a round counter, decides whether an unanswered
  clarification question is currently open (marker: a comment whose body
  contains `[!IMPORTANT]` and either `Answer the open clarification
  questions` or `Answer the remaining clarification questions` — the two
  literal strings `intake.yml:1094-1102` and `clarify.yml:874-882` already
  post) that postdates the harness's most recent reply, and if so, whether
  the round bound (D8) still permits a reply. Prints one of `reply`,
  `wait` (question open, already answered this round, waiting for the
  stage to consume it or ask again), `none` (no question open), or
  `exhausted` (bound exceeded) plus the fixed reply body (D8) when the
  decision is `reply`.
- `auto-release-e2e-merge-decision.sh` — given one `gh pr list --json
  number,headRefName,mergeable,mergeStateStatus,isDraft` entry (or empty),
  the expected head-ref prefix, and the attempt's slug, decides `merge`,
  `wait` (found, not draft, but checks still pending —
  `mergeStateStatus: UNKNOWN` or `BEHIND`), `none` (no matching open PR
  yet), or a specific stall reason: `conflicting` (`mergeable: CONFLICTING`),
  `blocked` (`mergeStateStatus: BLOCKED`, a required check failing), or
  `wrong-attempt` (a PR exists at that prefix but its branch name doesn't
  carry this attempt's slug — the leftover-PR edge case, FR-009).

**Rationale**: these are the two shapes of judgment FR-005 requires be
deterministic rather than an agent's call, and Constitution IX names this
exact pattern — "judgment that gates a durable action belongs in
deterministic code." Splitting clarify-decision from merge-decision (two
scripts, not one dispatch script) matches D5's principle at finer grain:
the two decisions consume unrelated fetched shapes (comments vs. PR
metadata) and have unrelated failure vocabularies, so a shared script
would need to branch internally on which vocabulary applies — worse than
two scripts with one job each.

**Alternatives considered**: one combined `auto-release-e2e-gate.sh
<clarify|merge> ...` dispatcher — rejected as an unnecessary indirection
for two scripts that share no logic; folding both into a modified
`auto-release-verdict.sh` — rejected, that script's contract (spec 049) is
specifically "build the verdict JSON shape," and these two scripts decide
something upstream of any verdict.

## D7. Clarification round bound (FR-006)

**Decision**: `MAX_CLARIFICATION_ROUNDS=3`, a literal in the `poll` step's
env, next to the existing `POLL_BUDGET_SECONDS`.

**Rationale**: both prior failing attempts at `1880c9e` independently
produced exactly two questions ("what moment 'the timestamp' refers to,"
and "whether a repeat run adds a file or overwrites one"). Three rounds
gives one full spare round beyond the observed two-question case before
declaring a stall, without turning a genuine stuck loop (Edge Cases: "the
answer itself provokes a follow-up question") into an open-ended wait —
exactly the FR-006 trade-off. Like `POLL_BUDGET_SECONDS`, this is a value
"changed by a reviewed pull request, not a settings-side knob" (spec
Assumptions), so it is a literal, not a repository variable.

**Alternatives considered**: bound = 2 (exactly the observed count) —
rejected as brittle against the Edge Case's explicit warning that "nothing
guarantees the third [round] does" ask the same two questions; bound = 5
or unbounded-with-timeout — rejected, a stall that only surfaces at full
`POLL_BUDGET_SECONDS` is precisely the `fail-timeout`/gate-stall conflation
User Story 3 exists to eliminate.

## D8. Prepared answer content (FR-005, FR-007)

**Decision**: one fixed markdown reply, stored as a literal in
`auto-release-e2e-clarify-decision.sh`'s output (not fetched, not
templated per-run):

> Use the moment this workflow run started as "the timestamp." On a
> repeat run, overwrite the existing file rather than adding a new one.
> For anything else this question doesn't cover, use your own best
> judgement and proceed.

**Rationale**: this is Option A from the spec's own Clarifications
session, Question 3 — answers the two known questions and delegates
anything else to the stage's judgment, posted once per round up to the
D7 bound. It is deterministic and pre-authored per FR-005, and posting the
literal string "this workflow run started" (rather than a computed
timestamp value) keeps the answer itself a fixed literal — no run-specific
interpolation for the clarify stage to parse two ways.

**Alternatives considered**: interpolating the actual kickoff timestamp
into the reply — rejected, it adds a moving part to a string that gates a
durable action (Constitution IX) for no benefit, since the clarify stage
only needs to know *which* timestamp is meant, not its numeric value.

## D9. PR-merge gate mechanics (FR-002, FR-009, FR-010, FR-023)

**Decision**: for each of the three PR gates — `spec-draft/<slug>` (base
`main`/default branch), `plan/<slug>` (base `spec/<slug>`), and
`spec/<slug>` (the finalize PR, base the default branch) — each poll
iteration runs `gh pr list --head <prefix><slug> --json
number,headRefName,mergeable,mergeStateStatus,isDraft,state`, feeds the
result to D6's merge-decision script, and on a `merge` decision runs `gh
pr merge <number> --merge` (a merge commit, matching the plain "click
merge" a human performs per `docs/setup.md:192`'s smoke test — no
`--squash`, no `--admin`, no `--delete-branch`; branch deletion stays
`cleanup.yml`'s job, unchanged). A `wait` decision does nothing this
iteration (checks still settling). A `conflicting`, `blocked`, or
`wrong-attempt` decision is an immediate `fail-gate-stall` (D11) — the
attempt does not wait out the remaining poll budget once a merge attempt
has concretely failed, per FR-023's requirement to distinguish the reason
rather than let it read as a generic timeout.

**Rationale**: `WING_COMMANDER_PLAN_REVIEW`'s default (`pr`,
`plan.yml:46,584-600`) and `WING_COMMANDER_TASKS_REVIEW`'s default (`auto`,
`docs/setup.md:95`) already match exactly the four gates spec 055 lists —
zero fixture reconfiguration needed for gate shape. No branch protection
exists on the disposable test repository by adoption default
(`specs/053-e2e-scratch-provisioning/spec.md:363-366`), so a plain `gh pr
merge` needs no admin bypass and no approving review; `conflicting` and
`blocked` are therefore expected to be rare in practice but are still
classified explicitly because FR-023 requires the report to say which one
occurred if it ever does.

**Alternatives considered**: retrying a `conflicting`/`blocked` PR for the
remainder of the poll budget on the theory it might resolve itself —
rejected: a conflicting merge or a permanently failing required check on a
disposable, single-writer test repository cannot self-resolve without a
new commit nobody is going to push, so waiting out the budget only delays
the same `fail-gate-stall` verdict while spending more of the run's cost.

## D10. Leftover-attempt guard (FR-009)

**Decision**: `<slug>` in D9's `gh pr list --head` filter is the exact
slug intake derives from this attempt's kickoff issue title (already
computed and available to the `poll` step as the branch-name component the
spec-draft/plan/finalize PRs are required to carry), not merely the
prefix. A PR at the right prefix but the wrong slug is `wrong-attempt`
(D6), never merged.

**Rationale**: the existing `cleanup` step (`auto-release.yml:234-253`)
already closes every open issue and PR in the test repository before each
attempt's reset, so an exact-slug match is defense in depth rather than
the primary guard — but FR-009 asks that the harness "never act on a
leftover from a previous attempt," and matching by prefix alone would
still be technically capable of merging a same-prefix PR from a
same-second race (Edge Cases: "two attempts overlap" is already excluded
by FR-023 elsewhere, but a slug check costs nothing and removes the
possibility entirely rather than relying solely on the serialization
guarantee holding).

**Alternatives considered**: trust the pre-attempt cleanup alone and match
by prefix only — rejected as a single point of failure for a requirement
FR-009 states as a MUST; matching by exact branch name is nearly free once
the slug is already known to the step.

## D11. New outcome class: `fail-gate-stall`, and three-way failure
classification (FR-018, FR-021–FR-024, SC-010, User Story 3 Acceptance
Scenario 4)

**Decision**: `auto-release-verdict.sh`'s schema is unchanged — no new
field. A new `outcome` value, `fail-gate-stall`, is added, populated the
same way every existing `fail-*` site already is:  `failing_check` names
the gate (`"clarification"`, `"spec-draft PR merge"`, `"plan PR merge"`, or
`"finalize PR merge"`), `expected` states what the harness attempted or was
waiting for, `observed` states the specific reason (`"still open after 3
rounds"`, `"PR #N: CONFLICTING"`, `"PR #N: required check blocked"`, `"PR
#N belongs to a previous attempt"`). The `report` job's classification
step (`auto-release.yml:1013-1014`, today a binary `fail-infra` →
"infrastructure" else "pipeline defect") becomes a three-way switch:
`fail-infra` → "infrastructure", `fail-gate-stall` → "gate stall", every
other `fail-*` → "pipeline defect", unchanged from today for those.

**Rationale**: reusing the existing six-field shape needs no schema
migration and keeps every existing `fail-*` call site untouched (FR-024:
"existing durable one-report-per-head mechanics rather than... a second
reporting channel"). A third classification bucket is required, not
optional, because User Story 3's Acceptance Scenario 4 explicitly demands
a gate stall and a genuine pipeline defect never collapse into the same
label in either direction — today's binary classification would file every
`fail-gate-stall` under "pipeline defect," which is the exact
misclassification SC-010 forbids in spirit (SC-010 names `fail-timeout`
specifically, but the same reasoning applies to "pipeline defect", the
other generic bucket a gate stall must not collapse into).

**Alternatives considered**: encoding the gate name in the existing
`fail-incomplete` outcome instead of a new outcome value — rejected: `fail
-incomplete` already has a specific meaning (terminal-but-not-done, e.g.
`stage:stalled`) that Edge Cases explicitly keeps distinct from a gate
stall ("the lifecycle reaches `stage:stalled` for a non-gate reason:
reported as a pipeline defect, unchanged by this feature"); overloading it
would blur that existing line rather than draw the new one FR-021 asks
for.

## D12. Evidence assertions for a `pass` verdict (FR-016, FR-017, FR-019, SC-004)

**Decision**: before `write_verdict "pass" "" "" ""` (`auto-release.yml
:581`), the poll step gains one new assertion and one new evidence-
gathering step:

- **New assertion — clarification gate**: if any clarification-question
  comment (D6's marker) ever appeared in the issue's comment history,
  there MUST also be a harness-authored reply comment after it, for every
  such question, before `stage:done`. If a question appeared with no
  reply-after-it, that is `fail-wrong-output` (the lifecycle reached a
  terminal state despite an ostensibly open gate — should not happen if
  D4's loop drove it, but is asserted rather than assumed, per FR-016: "
  reaching the next stage is not on its own evidence that the gate was
  satisfied"). If no question ever appeared, the gate is skipped per
  FR-008 and asserted as N/A, not as a failure.
- **New evidence gathering — the three PR gates**: `gh pr list --state
  merged --head <prefix><slug>` for each of the three prefixes, recording
  each PR's number and `mergedAt` into the verdict's evidence. These gates
  were already *transitively* proven by the existing `stage:plan`/`stage
  :tasks` timeline-label assertions (`auto-release.yml:540-560`) — a
  `plan` stage cannot have run under `WING_COMMANDER_PLAN_REVIEW=pr`
  without its PR having merged first — so no new pass/fail logic is
  needed for them; what's missing today is only the *legible evidence*
  FR-017/FR-019 ask the report to name.

The `pass` verdict's `evidence_url` stays the issue URL (unchanged shape);
the newly gathered PR numbers and the clarification comment IDs are
appended to the `report` job's summary text (FR-019: "the run's own report
MUST name the four gates it drove"), not to `auto-release-verdict.sh`'s
JSON schema, keeping D11's "no schema change" decision consistent across
both the pass and fail paths.

**Rationale**: FR-016 requires each driven gate to be asserted positively;
three of the four already are, transitively, by mechanics spec 045 already
built, so the only new *assertion* this feature needs is the
clarification gate, which today has no assertion at all (`stage:clarify`
is never applied as a label, confirmed at `auto-release.yml:544-548`'s own
comment). The other three gates need new *evidence surfacing* for the
report, not new gating logic — SC-004 counts "gates recorded as satisfied
without evidence," and today's report says nothing about which PRs
existed, even though the pass path already required them to exist and
merge.

**Alternatives considered**: re-deriving all four gates' evidence from
scratch as independent checks, ignoring the transitive proof the existing
label assertions already provide — rejected as duplicating logic
CLAUDE.md's "one home" principle argues against; a genuinely independent
merged-PR check costs one more `gh pr list` call per gate and directly
produces the evidence, which is worth adding for legibility even though it
duplicates a *conclusion* the label check already implies.

## D13. Poll budget and cost, provisional pending first observed run
(FR-026, FR-027)

**Decision**: raise `POLL_BUDGET_SECONDS` from `6900` (115 minutes) to
`9000` (150 minutes, matching the job's existing `timeout-minutes: 150` so
the poll budget is never the binding constraint) as a provisional value for
this feature's first shipped version. State the expected per-attempt cost
as "materially more than the roughly one dollar the intake-only attempts
recorded, on the order of the sum of every stage's own per-invocation
model cost (spec/plan/tasks/implement/finalize), with the exact figure to
be recorded from the first unattended run that reaches a verdict" — this
plan does not fabricate a precise number no run has yet produced.

**Rationale**: the spec's own Assumptions state both figures "were sized
before the run had to wait on any gate" and "are re-derived from an
observed complete unattended run rather than carried forward" — this plan
honors that by not inventing a precise final number, while still shipping
a budget generous enough that a healthy run (all four gates driven
promptly, every stage completing normally) does not exhaust it before the
lifecycle itself finishes. Aligning the poll budget to the job's own
`timeout-minutes` removes one of the two clocks that could independently
time out the same attempt for different reasons.

**Alternatives considered**: leaving `POLL_BUDGET_SECONDS` at `6900` and
raising only `timeout-minutes` — rejected: the two would then disagree
about which fires first, reintroducing exactly the "generic timeout vs.
named gate stall" ambiguity User Story 3 exists to remove, just at the
job-timeout layer instead of the poll layer.

## D14. Resume condition is a follow-up maintainer action, not shipped
code (FR-028, FR-029, User Story 5)

**Decision**: this feature ships the capability (D1–D13) and updates
`docs/setup.md` to state the resume condition in words, but does not
automate flipping `WING_COMMANDER_AUTO_RELEASE_PAUSED`. Clearing the pause
switch and posting the run's evidence to tracker issue #385 happens as a
separate, later pull request, authored once a real unattended run has
actually reached `stage:done` — which cannot happen before this feature
merges and a scheduled or dispatched attempt runs against it.

**Rationale**: FR-028 requires the switch be "cleared in the same change
that records that run's evidence" — i.e., a reviewed PR a human writes
after seeing the evidence exists, not a runtime action the pipeline takes
on itself. Automating the flip would also mean granting the auto-release
job write access to this repository's own variables, a privilege this
feature has no other use for and User Story 4 does not ask it to acquire.

**Alternatives considered**: having the `report` job flip the variable
itself on a `pass` verdict via `gh variable set` — rejected: it would need
a token scoped to write repository variables in *this* repository, which
is a broader grant than anything else this feature requires, for a benefit
(saving one manual PR) the spec doesn't ask for and User Story 5 frames as
acceptable to leave manual ("it costs nothing to leave paused").
