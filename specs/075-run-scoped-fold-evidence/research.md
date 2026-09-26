# Phase 0 Research: Run-Scoped Fold Evidence

Every decision below stays inside spec 042's boundary (`dispatch-once`,
`report-fold-outcomes`, `act`, `classify-and-announce` in
`pr-conversation.yml`) and changes only what counts as fold evidence — the
job graph, concurrency groups, categories, and outcome vocabulary from
specs/033/042 are untouched (Out of Scope).

## D1 — How a fold commit becomes attributable to its producing run

**Decision**: A deterministic step in the `act` job, run once per leg
immediately after "Checkout working tree for this leg" (`pr-conversation.yml`
~1911) and before "Act on this classification" (~1959), configures a local
git hook on that checkout: `git config core.hooksPath <path>` pointing at a
`prepare-commit-msg` hook (written inline by this same step, not fetched
from anywhere) that appends one trailer line,
`Wing-Commander-Run-Id: ${{ github.run_id }}`, to any commit message made in
that working tree. The agent's own prompt and allowed-tools list are
unchanged — it still runs `git commit -m "fold(${{ matrix.id }}): ..."` and
`git push` exactly as it does today (~2009–2013); the trailer is appended by
the hook, not by an instruction the agent must remember to follow.

**Rationale**: FR-004 requires the attribution signal to be "readable by...
a deterministic step," not "an instruction an agent is asked to follow when
it writes its commit" — Constitution IX names this exact class of defect
(judgment gating a durable record must live in code, never a prompt). A git
hook is deterministic code that fires on every local commit in that
checkout regardless of what the agent's own reasoning does that turn, and it
requires no change to the fold commit's user-visible subject line (`fold(id):
summary`), which two other things already depend on: Gate 34's structural
assertion that the agent prompt contains the literal substring
`fold(${{ matrix.id }})`, and the human-readable fold-log entries a
maintainer reads on the PR.

**Alternatives considered**:
- *Ask the agent to add the trailer itself* (e.g., extend the prompt to say
  "include a `Wing-Commander-Run-Id:` trailer"). Rejected outright by
  FR-004/Constitution IX — this is exactly the "instruction an agent is
  asked to follow" the requirement forbids, and an adversarial PR comment
  (Constitution V: untrusted content is never instructions) could plausibly
  talk the agent out of adding it with no error surfaced.
- *Amend the commit after the agent pushes, in a second deterministic step*
  (`git commit --amend --trailer ... && git push`). Rejected: this is a
  second push in the same window the agent already pushed into, racing
  against `git push`'s own fast-forward requirement if the leg's own agent
  step or a concurrent leg (same run, `max-parallel: 1`, so not concurrent
  within a run, but a *sibling run* per FR-006 could push in the interim)
  moved the branch tip first — the amend-and-repush would need its own
  fetch/rebase/retry loop for a problem the hook avoids by construction
  (the hook runs inside the same `git commit` invocation, before any push).
- *A PR-comment or artifact carrying run attribution instead of the commit
  itself* (the spec's own Assumptions section allows this: "an artifact is
  a legitimate mechanism if the plan prefers it"). Rejected: FR-005
  requires the signal to be readable "without depending on any leg's own
  steps having completed" — a cancelled leg (the exact case the report
  exists for, FR-005/FR-006a of spec 042) never reaches a later step that
  could publish an artifact, but it may already have pushed a fold commit
  before being cancelled (Edge Cases: "a leg folds more than one commit").
  The commit itself is the only artifact guaranteed to exist whenever fold
  evidence exists at all.

## D2 — Where the run-scoped read lives (single home, FR-009)

**Decision**: A new composite action, `.github/actions/wing-commander-fold-evidence`,
resolved via the same self-checkout pattern `dispatch-once` and
`report-fold-outcomes` already use for the pipeline's own repo content
(`pr-conversation.yml` 2644–2647, 2816–2819 — a second checkout of this
repository at `steps.pipeline-ref.outputs.ref`, alongside the spec-branch
checkout at 2676–2680/2863–2867 that holds the git history to read).
Inputs: `working-directory` (the spec-branch checkout path), `base-sha`,
`tip-sha`, `run-id` (defaults to `github.run_id`). Output: `folded-json`, a
JSON array of `{id, summary}` for every commit in `base-sha..tip-sha` whose
subject matches `^fold(<id>): <summary>$` **and** whose full message body
contains the trailer line `Wing-Commander-Run-Id: <run-id>` exactly — read
with `git log <range> --grep '^fold(' --format='%H'`, then `git show -s
--format=%B <sha>` per candidate to check subject and trailer together
(`git log --grep` alone cannot express "subject matches X and a later line
matches Y" in one pass, since its pattern is matched against the whole
message buffer without the multi-line anchoring a subject-then-trailer
check needs). Both `dispatch-once` and `report-fold-outcomes` call this
composite once each, with the same shape of inputs they already assemble
today, and consume `folded-json` with `jq` for their own purposes (D3–D5).

**Rationale**: FR-009 requires "exactly one home shared by every reader of
fold evidence in this stage" — today's defect is two independent copies of
`git log --grep '^fold(...)'  "$BASE_SHA..$TIP_SHA"` (2707 and 2924), and
CLAUDE.md's own worked example for this rule is this exact class of bug
("the per-run cost line was once pasted into 12 run-blocks... a rounding
fix would have had to land 12 times"). A composite action — not a bare
script checked into `.github/scripts/` and invoked by relative path — is
required here because `dispatch-once` and `report-fold-outcomes` have
already repurposed `GITHUB_WORKSPACE` for the spec-branch checkout by the
time the fold-evidence read happens; a script living in this repository is
only reachable through the same self-checkout composites already use
(`wing-commander-inspected-run-identity`'s header names this precisely:
"resolved from the pipeline repository's own checkout at
`github.job_workflow_sha`").

**Alternatives considered**:
- *A shared script under `.github/scripts/`, invoked by a relative path
  from a `run:` block.* Rejected for the reason above — no `run:` step in
  either job has this repository's own tree at a resolvable relative path;
  only the composite-action self-checkout mechanism does.
- *Inline the shared logic as a third job whose outputs both jobs consume*
  (a `read-fold-evidence` job between `act` and the two existing jobs).
  Rejected: `dispatch-once` and `report-fold-outcomes` each read their own,
  independently-fetched tip SHA today (data-model.md's D3/D6 from spec 042
  deliberately did not share a single post-fold tip between them), and a
  shared job would need to either reintroduce that coupling or take two
  tip inputs and run twice anyway — no simpler than a composite action, and
  a new job carries `needs:`/`if: always()` wiring Gate 15 would have to
  re-verify, where a composite action call is a plain step inside each
  job's existing `if: always()` scope.

## D3 — The dispatch decision reads this run's own evidence (FR-014)

**Decision**: `dispatch-once`'s dispatch condition changes from "branch tip
moved" (`steps.tip.outputs.sha != needs.classify-and-announce.outputs.base-sha`,
research.md D3 of spec 042) to "this run's own `folded-json` is non-empty."
The fold list in the PR comment (2707–2709 today) is built directly from
`folded-json`'s entries, not from a fresh unscoped grep.

**Rationale**: FR-014 states this exactly — "A run with no fold evidence of
its own MUST dispatch no implement cycle, even when the branch tip moved
during its window." In the ordinary single-run case this changes nothing
observable: if this run is the only one in flight, every branch movement in
its window is its own fold, so "tip moved" and "own evidence non-empty" agree
(FR-012's single-run-unchanged bar). The two conditions diverge only in the
cases FR-014/FR-015 exist for: a sibling run's commit, or an unrelated push
(rebase, a human) landing in this run's window.

**Alternatives considered**:
- *Keep the tip-moved condition and additionally suppress the fold-list
  text for items not attributable to this run.* Rejected: this still
  dispatches an implement cycle off someone else's commit (or an unrelated
  push), which is exactly the "incidental re-dispatch" FR-014 says is
  "removed deliberately."

## D4 — The declined-dispatch notice (FR-015)

**Decision**: When the branch tip moved (`!= base-sha`) but `folded-json`
is empty, `dispatch-once` posts one PR comment: this run folded nothing of
its own and therefore dispatched no implement cycle. When the tip did not
move at all, nothing is posted — identical to today's silent no-op path
(FR-012's baseline; this is the "every other classification was a reply,
question, or note" case spec 042 already handles silently).

**Rationale**: FR-015 requires a maintainer to "tell from the PR alone that
the missing cycle was this run's decision and not a lost dispatch." The two
branch-tip states (moved vs. not) combined with the one new evidence state
(own folded-json empty) give exactly three outcomes: dispatch (moved, own
evidence present — today's path, unchanged), silence (not moved — today's
path, unchanged), and the one new outcome, the declined-dispatch notice
(moved, own evidence empty). This notice is distinct wording from the
existing `report-fold-outcomes` warning (FR-015's own text: "distinct from
the concurrency-cancellation notice of #415 option 4").

## D5 — `report-fold-outcomes`'s per-leg check narrows to this run (FR-001–FR-003)

**Decision**: The `folded` boolean at 2923–2926 today
(`git log --grep "^fold($id):" ... | grep -q .`) becomes a membership test
against this job's own `folded-json` call (D2): `folded=true` iff `id`
appears in `folded-json`. The surrounding outcome derivation — `success` +
`folded` → healthy/silent; `folded` + not `success` → "partly folded";
not `folded` → "not folded" (2928–2935) — is unchanged, preserving FR-002's
independence-of-both-halves rule and FR-003's existing vocabulary exactly.

**Rationale**: FR-001 forbids crediting a leg with "a commit made by a
different stage-9 run, under any leg id"; narrowing the evidence source to
`folded-json` (already scoped to this run by D2) satisfies FR-001 with no
change to the decision table itself, which is exactly what FR-003 asks for
("this feature changes what counts as evidence, not the vocabulary").

## D6 — Cross-run and unattributed commits require no special-case code (FR-006, FR-007, FR-013)

**Decision**: No branch, flag, or migration check distinguishes "a sibling
run's commit" from "a pre-migration commit with no trailer at all" — both
simply fail D2's membership test (no `Wing-Commander-Run-Id: <this run's
id>` trailer present) and are absent from `folded-json`. Both FR-006
(tolerate the overlap) and FR-007 (no id-matching fallback when attribution
is absent) and FR-013 (pre-migration commits become invisible, not
reinterpreted) fall out of the same one rule: presence in `folded-json`
requires this run's own trailer, full stop.

**Rationale**: A run started under a checkout of this workflow (old or new)
runs consistently under that one version for its whole lifetime — GitHub
Actions resolves a reusable workflow's content once, at trigger time, for
the entire run (Constitution VII's "Two Interfaces" self-checkout model);
no run executes a mix of pre- and post-migration code. A run in flight
during rollout is therefore either entirely pre-migration (old jobs, old
unscoped grep, behaves exactly as it does today — not this feature's
concern) or entirely post-migration (new jobs, D2's composite, reads its
own commits' trailers correctly). FR-013's "MUST NOT retroactively
reinterpret" and "MUST NOT... report a false 'folded cleanly'" both hold
without extra code: an old commit's absence of a trailer is not evidence of
anything, and the conservative direction (Assumptions: "reporting... as not
folded when it really did fold is... the conservative [error]") is where
that absence lands.

**Alternatives considered**:
- *A cutover date or commit-SHA boundary before which unattributed commits
  are still trusted.* Rejected: adds a second code path only pre-migration
  runs would ever hit, and (per the rationale above) no live run actually
  straddles the boundary — the special case has no live audience.

## D7 — Gate 34 is extended, not duplicated into a new gate (FR-009, FR-010, FR-011)

**Decision**: `.github/scripts/verify-fold-dispatch-once.py` (Gate 34, the
existing single home for `dispatch-once`/`report-fold-outcomes` behavioral
coverage per spec 042's own contract) gains: (a) a second run identity
constant alongside the harness's existing `make_repo()` fixture builder —
`RUN_ID_UNDER_TEST` and `RUN_ID_SIBLING` — and a `stamp_run_id` parameter to
its fold-commit helper so a fixture can produce commits carrying either
identity or no trailer at all; (b) one new scenario per FR-010's six
enumerated cases (own-success-plus-sibling-same-id → silent; own-cancelled-
no-commit-plus-sibling-same-id → "not folded"; own-success-no-commit →
"partly folded"; no-trailer-at-all commit → not this run's; own-folds-
nothing-while-sibling-folds → no dispatch plus FR-015's notice;
single-run baseline unchanged); (c) since D2 moves the shared read into a
composite action, `wc_shell_harness.py`'s extraction step for these two
jobs gains a second load — the composite's own `runs.steps` `run:` text
(`.github/actions/wing-commander-fold-evidence/action.yml`) — stitched in
wherever the workflow step's `uses:` line names it, alongside the jobs'
existing extracted `run:` text, so the harness continues to test the
exact shipped bash on both sides of the call; (d) a fifth mutation:
replace the composite-action call with the pre-fix inline
`git log --grep '^fold(' "$BASE_SHA..$TIP_SHA"` (no run-id filtering) and
assert the new two-run scenario then misreports a sibling's commit as this
run's own (FR-011).

**Rationale**: The spec's own Dependencies section calls for the fixtures
to live in "Gate 34 ... and its shell harness: the existing home for the
fixtures FR-010 requires, extended rather than duplicated" — a second gate
number would itself violate FR-009's single-home rule one layer up (two
gates checking the same fold-evidence rule). No new `Gate N —` heading is
added to `lint-workflows.yml`; the existing Gate 34 step's wiring (already
asserted by Gate 10) is unchanged.
