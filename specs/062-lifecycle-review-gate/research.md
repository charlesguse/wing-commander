# Phase 0 Research: The Lifecycle Review Gate

No `[NEEDS CLARIFICATION]` marker remains in `spec.md` — the three the
intake checklist recorded (FR-002, FR-017, FR-024) were resolved by the
owner's reply on issue #476 before this plan started. The decisions below
are this plan's own technical-design resolutions: things the spec
deliberately leaves to planning (which workflow shape, which script owns
which condition, which existing idiom becomes a shared home) rather than
unresolved requirements.

## D1 — The gate is a repository-only workflow, not a published stage

**Decision**: `lifecycle-review-gate.yml` carries no `workflow_call`
trigger. It is scheduled (`schedule:`) plus `workflow_dispatch`, the same
shape `board-loop.yml` and `auto-release.yml` already occupy, and is a
single file that is both trigger-owner and stage-logic (Constitution
VII's stage/wrapper split binds the *published* surface only; a
repository-only workflow is exempt the same way `board-loop.yml` already
is).

**Rationale**: Two of the conditions this gate re-derives — "every other
required check green" and "the branch is mergeable" — can become true at
any time after `finalize.yml` last ran, from events this repository does
not own (a slow third-party check, a human resolving a merge conflict).
Nothing in the existing lifecycle re-polls a PR for that; the only
existing precedent for "keep checking a condition that becomes true
asynchronously" is `board-loop.yml`'s own scheduled loop. A dispatch-chain
design (`finalize.yml` dispatches the gate once, the gate dispatches
itself again on fold-convergence) would miss the case where checks finish
green *after* the triggering event, which is exactly the case FR-001
extends readiness to ("re-derived against the pull request's exact head
SHA," not against a snapshot taken at dispatch time).

**Alternatives considered**: A published `workflow_call` stage dispatched
by `finalize.yml` and by `pr-conversation.yml`'s fold-convergence path —
rejected for the reason above (misses asynchronously-resolved checks)
and because publishing a stage is a wider commitment (Constitution VII:
"widening the surface is a deliberate act") than this feature's own scope
asks for; nothing in spec.md's Out of Scope or Assumptions sections asks
for adopter-facing publication, and the auto-merge setting it carries is
explicitly a single per-repository switch (FR-024), which a
repository-only workflow satisfies without inventing a `workflow_call`
input an adopter would need to wire through their own wrapper. A
`pull_request`/`check_suite` event trigger alone — rejected for the same
async-resolution gap, and because GitHub does not deliver `check_suite`
events for checks a third-party CI provider posts through the Checks API
in every configuration.

## D2 — Selection: which PR is "the lifecycle pull request" in scope

**Decision**: The gate's selection step lists open PRs, keeps only those
whose lifecycle issue's `spec-meta.json` (read via
`wing-commander-spec-meta`, following the existing `read-spec-meta.sh`
convention) has `stage == "review"`, and picks the oldest whose
`review_gate.head_sha` (if any) does not equal the PR's current
`headRefOid`.

**Rationale**: `stage: review` is set by exactly one stage
(`finalize.yml`, on opening or refreshing the final PR — research
confirmed no other stage ever writes it) and never by the spec or plan
PR's own stages. This satisfies FR-002 precisely — spec and plan PRs are
excluded because their spec-meta.json is never in `stage: review` — using
a signal that already exists rather than inventing a branch-name
heuristic (`spec-draft/` vs `spec/`) that would need to independently
track finalize's own state machine and could drift from it.

**Alternatives considered**: Matching on branch prefix
(`spec/<NNN>` → `main`) — rejected: the spec PR's branch is
`spec-draft/<NNN>` → `main` too, so a prefix check alone cannot
distinguish "has an implement stage behind it" (the actual FR-002
boundary) without also re-deriving stage, at which point the branch check
adds nothing `spec-meta.json.stage` doesn't already say more directly.

## D3 — Reviewer engine: Claude Code's packaged `code-review` capability, not a bespoke prompt

**Decision**: The reviewer step grants the `Skill` tool (alongside
`Read`, `Grep`, `Glob`, and the same read-only `git_read.py` Bash idiom
`board-loop.yml`'s reviewer already uses) and instructs the agent to
invoke the `code-review` skill against the PR's diff at an explicit
effort level, rather than writing out review instructions inline the way
`board-loop.yml`'s own reviewer prompt does. The skill's own recipe ends
by reporting findings through the `ReportFindings` tool; a closing
instruction in this gate's own prompt asks the agent to restate that same
finding set as the fenced `wing-commander-review-findings` block
`board-review-finding.schema.json` already validates, so the reviewer
engine changes (FR-007) without the finding *shape* changing (FR-010).

**Rationale**: FR-007 is explicit that the request is to reuse Claude
Code's own reviewer "rather than a bespoke, gate-specific prompt, so that
improvements to the reviewer are inherited rather than reimplemented."
`board-loop.yml`'s reviewer — this repository's only existing review
agent — is exactly that bespoke pattern (a hand-written correctness-review
prompt fed to `claude-code-action@v1`), which is why it is precedent for
the surrounding *plumbing* (independence, tool-args, turn ceiling, posting
a `COMMENT` review) but the thing FR-007 says not to repeat for the
review logic itself. No other call site in this repository invokes a
packaged review capability; this is new integration work, not an
extraction.

**Alternatives considered**: Copy `board-loop.yml`'s prompt verbatim —
rejected, it is precisely the "bespoke, gate-specific prompt" FR-007
names. Have the skill's own `ReportFindings` output stand as the gate's
finding record directly, dropping the fenced-block restatement — rejected
because `ReportFindings`'s schema (file/summary/failure_scenario/category/
verdict) is not the schema FR-010 requires reuse of, and capturing a tool
call's structured arguments from a `claude-code-action` transcript has no
existing extraction path in this repository, while parsing a fenced
Markdown block from the final message is the exact mechanism every other
structured-finding call site already uses.

## D4 — Round state lives in `spec-meta.json`, not a new file or label

**Decision**: `spec-meta.json` gains one new object, `review_gate: {round,
head_sha, outcome, findings_open, folded_fingerprints, filed_fingerprints,
updated_at}` (data-model.md §1), written only by this feature's own
workflow and read by its selection step, its readiness script, and its
merge-precondition script.

**Rationale**: `spec-meta.json` is already "the machine-readable source of
truth for a spec's lifecycle state" (constitution, Operational
Constraints) and already carries the one directly analogous counter,
`iteration`. Board-loop's own round budget lives in an issue-comment
marker instead — but the board loop tracks plain GitHub issues with no
`spec-meta.json` behind them at all; a lifecycle PR always has one
(spec.md Assumptions), so following the board loop's marker idiom here
would be reaching past a home that already exists for the same purpose.

**Alternatives considered**: An issue-comment marker like the board
loop's — rejected for the reason above. A PR label (`review-round:N`) —
rejected: labels are a coarse, single-value signal already fully spent by
`stage:review`/`stage:*`, and would need a second read path (`gh pr view
--json labels`) alongside `spec-meta.json` for no reduction in complexity.

## D5 — Readiness re-derivation: a new script modeled on `board_readiness.py`, not a shared one

**Decision**: `.github/scripts/lifecycle_readiness.py` re-derives, from a
fresh `gh pr view --json headRefOid,statusCheckRollup,mergeable,
mergeStateStatus`: checks green on the current head, the gate-suite
entry within that same rollup, the kill switch clear, and — new,
data `board_readiness.py` has no analogue for — `mergeable` (a head with
`mergeable: UNKNOWN` or `CONFLICTING` is not ready) and "not already
reviewed at this head SHA" (`review_gate.head_sha != headRefOid`).

**Rationale**: FR-001 requires re-deriving "the conditions it already uses
to call a pull request ready," and `board_readiness.py::evaluate_from_
snapshot` is that exact shape for a PR — but it was written for the board
loop's own fix-PR class, which never checks `mergeable` because it never
merges (research confirmed `board_readiness.py` has no `mergeable` field
at all). Making `board_readiness.py` itself grow a lifecycle-PR-only
condition would mean one script serving two unrelated subjects (an
arbitrary board-fix PR vs. a specific final-implementation PR) with
diverging condition sets — a worse single-home violation than two small,
clearly-scoped scripts sharing nothing but the pattern.

**Alternatives considered**: Add `mergeable` and the head-SHA-not-yet-
reviewed check as optional parameters to `board_readiness.py` — rejected:
the board loop's own invariant gate
(`check_no_merge_invariant`) exists specifically because that script must
never grow anything merge-adjacent; adding a `mergeable` check to it
would raise exactly the question that gate exists to catch, whether or
not the board loop's own call site uses the new parameter.

## D6 — Auto-merge preconditions: a second new script, not folded into readiness

**Decision**: `.github/scripts/lifecycle_merge_preconditions.py` takes a
head SHA and calls `lifecycle_readiness.py`'s evaluation for the
checks/gate-suite/mergeable/kill-switch conditions, then adds: the current
round's outcome is `clean` at this exact head SHA, zero open in-scope
findings, and no open `CHANGES_REQUESTED` review from a human (any
`reviews[].author` whose `authorAssociation` is not this App's own bot
identity). It returns the first failing condition's name, never a
boolean alone (FR-027).

**Rationale**: FR-026 lists six conditions, three of which
(checks/gate-suite/mergeable/kill-switch — four, precisely) are also
FR-001's readiness conditions; the other two (review clean, no unresolved
human changes-requested review) exist only for the merge decision and
have no reason to gate a plain review round. Keeping them a separate
script keeps `lifecycle_readiness.py` answerable to "should a review run
at all" and `lifecycle_merge_preconditions.py` answerable to "should a
merge happen," each independently fixturable (contracts/gates.md).

**Alternatives considered**: One script answering both questions with a
mode flag — rejected: it would need two different definitions of "clean"
in the same function (a round that hasn't run yet vs. a round that must
have already run clean), which is exactly the kind of two-shapes-one-
function ambiguity Principle IX's discipline exists to keep out of a
single deterministic answer.

## D7 — The bot-author exclusion and its wrapper are untouched

**Decision**: Zero edits to `wing-commander-9-pr-conversation.yml` or
`pr-conversation.yml`'s trigger surface. The gate never posts a review
and waits for the review event to carry it forward; it calls
`wing-commander-fold-commit`/`wing-commander-fold-dispatch` directly
(D8–D10) from its own job.

**Rationale**: FR-018 forbids exactly the alternative of widening
`review.user.type != 'Bot'` or adding a dispatch entry point to that
wrapper — both would let *any* bot-authored review drive the fold loop, a
strictly larger trust surface than this feature needs. Calling the shared
fold logic directly needs no change to who the review-event path trusts.

**Alternatives considered**: none seriously — this is FR-018 restated as
a design constraint, not a choice among options.

## D8 — `wing-commander-fold-commit`: the append/flip/commit primitive, extracted

**Decision**: A new composite action takes `spec-dir`, a pre-drafted
tasks.md section (as file content), a fold id, a fold summary, and an
actor login; it appends the section to `tasks.md`, sets
`spec-meta.json.stage` to `implement`, unions the actor into
`pending_re_review_from`, and commits both files as
`fold(<id>): <summary>`, pushing to the spec branch.
`pr-conversation.yml`'s `act` job is edited so its agent step drafts the
section to a file instead of running `git add`/`git commit`/`git push`
itself, and a new deterministic step after it calls this composite; this
gate's own findings-drafting step (deterministic, D11) calls the same
composite.

**Rationale**: FR-017/FR-035 require the fold logic to "live in a single
shared home... that both the existing review-event path and this gate
call, so the two paths cannot drift apart" — and research confirmed no
such home exists today; the mechanics are inline in an agent's own tool
calls. The *drafting* judgment genuinely differs between the two paths (a
human's free-text review needs interpretation; this gate's findings are
already structured), but the *commit shape* — append, flip, record
reviewer, commit message prefix — is identical, and is the actual thing
FR-021's "not folded twice" and finalize's re-review-request path both
depend on staying byte-identical between the two callers.

**Alternatives considered**: Leave `pr-conversation.yml`'s `act` job
exactly as it is and have this gate duplicate its commit shape inline —
rejected outright by FR-017's own text. Extract only a shell *script*
(not a composite) that the agent's own Bash tool call invokes mid-turn —
rejected: an agent-invoked script is still judgment-gated by whether the
agent chooses to call it correctly every time (constitution IX); a
deterministic step after the agent's turn ends is the same discipline
`dispatch-once` already established for the sibling half of this same
job (a deterministic step run once the agent's own work is done, not
trusted to the agent itself).

## D9 — `wing-commander-fold-dispatch`: the bump/dispatch primitive, extracted

**Decision**: A new composite action takes `spec-dir`, `issue`, and the
pre-fold branch tip SHA; it re-reads the current tip, compares, and — if
it moved — reads `spec-meta.json.iteration`, dispatches `implement.yml`
with `iteration = iteration + 1`, and records the fold evidence used for
`report-fold-outcomes`. `pr-conversation.yml`'s `dispatch-once` job
becomes a thin caller of this composite; this gate's own post-fold step
calls it after `wing-commander-fold-commit` has pushed its own commit.

**Rationale**: This is already deterministic code today
(`dispatch-once`), so extracting it is a pure move, not new logic — the
"fold all, dispatch once" property FR-017/FR-035 need to hold for a second
caller falls out of reusing the exact function that already holds it for
the first.

**Alternatives considered**: Have this gate call `gh workflow run` on
`implement.yml` directly, bypassing `dispatch-once`'s tip-comparison —
rejected: it would reintroduce exactly the double-dispatch risk spec 042
fixed (a leg that folds nothing still triggering a wasted cycle), for a
caller that has no reason to be exempt from the same guard.

## D10 — `wing-commander-post-review-comment`: promoted on its second call site

**Decision**: The `gh api .../pulls/<n>/reviews -f event=COMMENT`
call — today inline in `board-loop.yml`'s reviewer step — becomes a small
composite action (`token`, `pr-number`, `body-file`) that both
`board-loop.yml` and this gate's reviewer-posting step call.

**Rationale**: CLAUDE.md: "Before pasting a `run:` block... into a second
workflow, move it instead." This gate needs the exact same mechanism for
the exact same reason board-loop.yml's header comment already states —
GitHub rejects `APPROVE`/`REQUEST_CHANGES` from the PR's own author
identity, and both PRs are authored by the same App identity — so this is
precisely a second call site of one existing idiom, not a new one.

**Alternatives considered**: Leave `board-loop.yml`'s inline call alone
and paste a second copy for this gate — rejected by the CLAUDE.md rule
quoted above; this is the "before pasting... move it instead" case
verbatim.

## D11 — This gate's own findings are folded/filed deterministically, not by the reviewing agent

**Decision**: A deterministic step (not an agent) reads the fenced
`wing-commander-review-findings` block the reviewer produced (D3),
partitions it into in-scope (fold) and out-of-scope (file) using the
existing `in_scope` field, computes each finding's fingerprint the same
way `wing-commander-durable-failure-issue` already does (spec 076's
verbatim-anchor scheme), checks each fingerprint against
`review_gate.folded_fingerprints`/`filed_fingerprints` before acting
(FR-021), renders the in-scope survivors into one tasks.md section with a
fixed template (title/what/evidence per finding), and calls
`wing-commander-fold-commit` (D8) with that section; out-of-scope
survivors are filed through `wing-commander-durable-failure-issue`
unmodified, body-prefixed `Found by the code review of #<N>.` (FR-019),
identical to `board-loop.yml`'s own existing out-of-scope filing call.

**Rationale**: Constitution IX and FR-021 require that whether a finding
is well-formed, novel, or safe to act on is decided by deterministic code,
never the reviewing agent's own judgment. Because this gate's findings
already arrive structured (unlike pr-conversation's free-text human
review), no agent interpretation step is needed between "the reviewer
found X" and "X becomes a tasks.md section" — removing an entire class of
drift the human-review fold path cannot avoid (a human's prose has to be
classified by an agent; this gate's own JSON does not).

**Alternatives considered**: Route this gate's findings through the same
agent-drafts-a-section step `pr-conversation.yml`'s `act` job uses —
rejected: it would spend a second agent invocation turning already-
structured data back into prose for another agent to draft from, adding
cost and a second place the same judgment (fold vs. file) could diverge
from the deterministic `in_scope` field the reviewer already computed.

## D12 — Round budget: a workflow-level constant, coupled to the existing `iteration` counter

**Decision**: `lifecycle-review-gate.yml` declares
`LIFECYCLE_REVIEW_ROUND_BUDGET: 5` as a job-level `env:` (a PR-reviewed
constant, not a `vars.` override — matching `board-loop.yml`'s own
`BOARD_LOOP_ROUND_BUDGET`). `review_gate.round` increments once per
completed review round (clean or not); when it would exceed the budget,
the gate stops, states the reason and the open findings on the lifecycle
issue, and does not fold further (US2 scenario 4, FR-022).

**Rationale**: The constitution's own "conservative default (single
digits)" assumption and `implement.yml`'s `max-iterations` default (5)
both land on the same number; `board-loop.yml`'s round budget is the
closer analogue (a fix→review round cap, not an implement-cycle cap) and
uses the same constant shape. `review_gate.round` is deliberately its own
counter, not a read of `spec-meta.json.iteration` — a single fold can
trigger an implement cycle that itself has multiple retries/escalations
before converging, so "review rounds spent" and "implement iterations
spent" count different things and would silently conflate two budgets if
merged into one field.

**Alternatives considered**: Derive the round count from `iteration`
directly — rejected for the reason above; a truncated-cycle-carry-forward
iteration (spec 040) that produces no new findings-relevant commit would
otherwise silently consume review-round budget it never spent.

## D13 — Auto-merge has no executable precedent to copy; it is designed from the constitution's prose

**Decision**: The merge step is new code:
`gh pr merge --squash "$PR" --match-head-commit "$SHA"` (GitHub CLI's own
head-match guard as a second, independent safety net beyond
`lifecycle_merge_preconditions.py`'s own re-derivation), run only when
`vars.WING_COMMANDER_LIFECYCLE_AUTO_MERGE == 'true'` and every
precondition (D6) holds.

**Rationale**: Research confirmed exhaustively that no `gh pr merge`,
`--auto`, `event=APPROVE`, or `event=REQUEST_CHANGES` call exists anywhere
in this repository's pipeline code — `board-loop.yml` is mechanically
forbidden from ever adding one
(`verify-board-readiness.py::check_no_merge_invariant`). The constitution's
Principle X paragraph describes the fix-PR-merge class's gates in prose
(checks green on exact head SHA, independent review with zero open
findings, kill switch clear, squash commit) but no code implements that
class either. This feature's own merge step is designed directly from
that prose description — the nearest thing to "prior art" available — not
copied from a working implementation, because none exists yet.

**Alternatives considered**: Defer auto-merge design questions until
Principle X's own fix-PR-merge class ships its first implementation, then
copy it — rejected: nothing on the roadmap commits that class to ship
before this feature, and User Story 4 is this spec's own explicit,
prioritized scope (P2), not contingent on a different feature.

## D14 — Credential-scope refusal: detected by `gh pr merge`'s own failure, not a pre-check

**Decision**: When `gh pr merge` exits non-zero, the step inspects stderr
for GitHub's own "workflow scope" refusal text; on a match, the gate
posts the refusal reason to the lifecycle issue and stops — no retry, no
alternate route to `main` (FR-030). Any other non-zero exit is treated as
a generic merge failure, reported the same way but without the
scope-specific wording.

**Rationale**: FR-030's condition (a token lacking the `workflow` scope
for a workflow-touching PR) is exactly the situation CLAUDE.md's own
"Working the issue board" section names for a *different* merge path
("`gh pr merge` on a PR that touches `.github/workflows/` needs a token
with the `workflow` scope... hand the merge to the maintainer... never
push to main around the refusal") — the same refusal, the same required
response, reached here by the merge attempt's own exit status rather than
a separate scope-introspection call, since GitHub does not expose "would
this token's scope allow this merge" as a query independent of attempting
it.

**Alternatives considered**: Pre-check the token's granted scopes before
attempting the merge — rejected: GitHub Apps do not expose a scope list
comparable to a PAT's; whether a specific merge is refused depends on
whether the PR's diff touches `.github/workflows/`, which the merge
attempt itself already has to determine to succeed or fail, so a separate
check would re-derive the same fact through a less direct path.

## D15 — Kill switch and enable switch are two variables, not one

**Decision**: `WING_COMMANDER_LIFECYCLE_REVIEW_GATE_PAUSED` (FR-034,
checked at job entry and re-checked immediately before every durable
action via the existing `wing-commander-board-stop-check` composite,
reused unmodified) stops review *and* merge. `WING_COMMANDER_LIFECYCLE_
AUTO_MERGE` (FR-024) enables merge alone and defaults off; the review
half of the gate runs and reports regardless of its value (FR-025).

**Rationale**: FR-024 and FR-034 are independent controls answering
different questions ("is auto-merge authorized at all" vs. "is the whole
feature stood down right now") and the spec is explicit that turning
auto-merge off must never disable the review gate itself (FR-025) — one
variable could not represent both a three-state need (off / review-only /
review-and-merge) as cleanly as two booleans, and two booleans matches
the existing `WING_COMMANDER_*_PAUSED` family's own one-variable-per-
concern convention exactly.

**Alternatives considered**: A single three-valued variable
(`off`/`review`/`merge`) — rejected: every existing kill switch in this
repository is a boolean checked with `== 'true'`; a three-valued variable
would need its own parsing/validation this feature would then be the only
consumer of, for no reduction in the number of concepts a maintainer has
to hold (they still have to know both "is it paused" and "is merge
enabled" independently).

## D16 — The constitution amendment is out of this branch's file scope

**Decision**: This plan documents the amendment's required shape
(contracts/constitution-amendment.md) but neither drafts nor commits it.
`verify-constitution-merge-class-parity.py` (FR-038) is added to this
feature's own gate set so that if the merge capability's code lands on
`main` before the amendment does, CI fails and says so; the amendment PR
itself is a separate, human-merged PR against `.specify/memory/
constitution.md` (FR-033).

**Rationale**: This plan's own constraints keep it to
`specs/062-lifecycle-review-gate/`; the constitution amendment's PR is
itself the human-merged artifact FR-033 requires (a bot merging its own
authorization to merge would violate the very principle being amended).
Sequencing the two through a gate rather than through PR ordering alone
means a maintainer merging this feature's implementation PR before the
amendment lands gets a failing, explicit check instead of a silently
inert `WING_COMMANDER_LIFECYCLE_AUTO_MERGE` variable nobody would notice
was unauthorized.

**Alternatives considered**: Ship the amendment PR from inside this
feature's own implement stage — rejected: the implement stage's PR is
itself a bot-authored, (eventually) bot-mergeable artifact under the very
constraint FR-033 states; the amendment has to be a distinct PR a human
merges on its own, not a commit folded into this feature's branch.
