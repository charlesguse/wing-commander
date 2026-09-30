# Research: The Prove Entry Survives a Displaced Queue Slot

Every line number below is re-verified against `main` at `cead742`
(2026-09-30), per spec.md's own "Status update 2026-09-30" note. Each
decision is a plan-time engineering judgment, not a spec clarification —
spec.md's Q1/Q2/Q3 answers and FR-001 through FR-022 are fixed inputs;
this document is how to build the mechanism those answers require.

## D1: The ordinary prove path's group is keyed by the merged PR's number, preserving the directed branch verbatim

**Decision**: `prove-gate` (`board-loop.yml:3986-3993`) and `prove`
(`:4166-4173`) both carry the same three-branch `group:` expression today
they carry two of:

```yaml
group: >-
  ${{ (github.event_name == 'workflow_dispatch' && inputs.directed-stage != '') &&
  'wing-commander-board-loop-directed-proof' ||
  (github.event_name == 'pull_request' && format('wing-commander-board-loop-prove-{0}', github.event.pull_request.number)) ||
  'wing-commander-board-loop' }}
```

The directed branch (first `&&`/`||` pair) is untouched byte-for-byte
(FR-004's "existing directed branch... MUST be preserved"). The new middle
branch fires only on the `pull_request` event these two jobs' own `if:`
already restricts them to alongside the directed case
(`prove-gate`'s `if:`, `:3976-3979`), so the trailing
`'wing-commander-board-loop'` fallback is unreachable in practice — kept
only because the existing expression already carries the same
belt-and-suspenders fallback for its own unreachable case, and removing it
would be an unrelated stylistic change this feature has no FR asking for.

**Rationale**: `github.event.pull_request.number` is available directly in
a job-level `concurrency.group:` expression on a `pull_request` event
without any prior step (FR-004's own text names this value). It is
one-to-one with the merged PR, and — per spec.md's Assumptions — one-to-one
with the item's issue, because a loop fix PR cites exactly one issue and an
issue has at most one merged loop fix PR in flight. Keying by PR number
(not issue number, which would need the PR body parsed first — work no
`concurrency:` expression can do) satisfies FR-004's "no two distinct
merged items share one group" without adding a job or a pre-step.

**Alternatives considered**: Keying by `github.event.pull_request.head.sha`
was rejected — a PR's head SHA changes if it were re-pushed before close
(not possible post-merge, but the expression would be reasoning about a
fact that stops being useful the moment the PR fires this event) and adds
nothing PR number doesn't already give one-to-one. A single new shared
group for every ordinary prove run (`wing-commander-board-loop-prove`, no
per-PR key) was rejected outright — it is exactly the "group key shared by
all merges would move the displacement rather than remove it" edge case
spec.md itself names.

## D2: The guarantee sentence gains a second permitted-overlap clause; Gate 101 needs no code change

**Decision**: The FR-016 canonical sentence in
`specs/060-self-redrive-concurrency/contracts/concurrency-groups.md` ("##
The guarantee") changes from:

> One board item is in flight repository-wide. A directed proof run, which
> selects no board item and opens no fix PR, is the only run permitted to
> overlap an ordinary board-loop run. Every other pair of `board-loop.yml`
> runs queues rather than races or cancels.

to:

> One board item is in flight repository-wide. A directed proof run and a
> merged item's own prove run — neither of which selects a board item or
> opens a fix PR — are the only runs permitted to overlap an ordinary
> board-loop run, or each other when they prove distinct merged items.
> Every other pair of `board-loop.yml` runs queues rather than races or
> cancels.

This is a content edit to three sites (FR-005): the canonical blockquote
above, `board-loop-workflow.md`'s "Concurrency" section, and all eight
per-job `concurrency:` comments in `board-loop.yml`. Gate 101
(`verify-concurrency-guarantee-statement.py`) reads its canonical text from
`concurrency-groups.md` at run time and diffs the other nine sites against
it (normalized) — it needs no code change for a sentence-content edit, only
for a change to the *count* of comment blocks (still 8: D1 doesn't add or
remove a job) or the *file* it reads canonical from (unchanged). This
directly satisfies FR-019: "MUST NOT add a second gate that compares the
same prose."

**Rationale**: The old sentence is false the moment D1 ships — a
`pull_request: closed` prove run for merge A can now start while a
`pull_request: closed` prove run for merge B (or a directed proof run) is
in flight, none of which is "an ordinary board-loop run" in the old
sentence's sense. FR-005 requires this be fixed by editing the canonical
sentence, never by a second, drifting comment.

**Alternatives considered**: Leaving the sentence broader ("any run that
selects no board item and opens no fix PR may overlap") was rejected as
imprecise — it would also license two directed proof runs of *different*
issues to appear to overlap in the sentence's own text when the directed
group is in fact shared (not per-item) and DOES serialize them, per
`concurrency-groups.md`'s existing "shared across every directed dispatch"
paragraph. The revised sentence's "or each other when they prove distinct
merged items" clause is scoped to the ordinary prove path specifically,
where D1's per-PR key is what makes the overlap real.

## D3: Recovery is a new step in `select`, reusing the displacement step's own already-fetched data

**Decision**: A new step, "Recover a stranded prove (FR-011)", is added to
the `select` job immediately after "Detect a merge whose proof run never
started (FR-010b)" (`board-loop.yml:216-301`), gated by the same `if:`
condition that step already carries
(`steps.killswitch.outputs.status != 'paused' && steps.stand-down.outputs.status != 'in-flight'`
— this is FR-012's re-check, identical to the existing pattern, not a new
one).

It reads the same two artifacts the displacement step already wrote to
`$RUNNER_TEMP` in this same run —
`board-recent-merges-by-issue.json` (issue → most-recently-merged
`board:owned` PR) and `board-displacement-comments-by-issue.json` (each of
those issues' own comments) — rather than re-querying GitHub a second time.
For each issue in that set (all of them already `board:owned`-scoped by
the displacement step's own `gh pr list --label board:owned` query,
satisfying FR-013 by construction rather than a second ownership check):

1. Skip if the issue is not in the run's own open-issues list (the "closed
   by a human" edge case: not recovered, not an error).
2. Read the newest marker (`board_item_marker.read_marker`). Skip unless
   `marker["step"] == "prove"`.
3. Skip unless `marker.get("outcome_reason")` is exactly
   `board_prove_displacement.RECORDED_REASON` ("prove run displaced") or
   the literal string `"uncorrelated"` (Q3/FR-011's two shapes). A marker
   with no `outcome_reason` key at all — every marker written before this
   feature ships, and every `failure`/`unfinished` marker, which never
   carries value `"uncorrelated"` — does not match either literal, so it
   reads as "not recoverable" without a special case (FR-011c).
4. Skip if `marker.get("recovery_attempted")` is truthy (FR-011a).

This yields the recoverable set; **at most one** is chosen (FR-011b),
oldest-marker-timestamp-first — the same "oldest first" fairness rule
`board_eligibility.select()`'s own fallback scan already uses, so a
recoverable item does not starve behind a repeatedly-re-displaced one.

For the chosen item, the step re-derives the merged PR's own
board-loop-managed-ness the same way `prove-gate`'s existing "Resolve the
originating issue"/ownership steps already do (nothing new: the recovered
dispatch below re-enters that same code), calls
`board_prove.directed_proof_group_busy()` against a fresh
`gh run list --workflow=board-loop.yml --json databaseId,displayTitle,status -L 20`,
and:

- if busy → records nothing durable, leaves the item recoverable (FR-011a:
  "not made because busy MUST NOT count"), and lets a later run retry.
- if not busy → dispatches with `gh workflow run board-loop.yml -f
  directed-stage=prove -f directed-issue=<N> -f directed-pr=<PR> -f
  directed-recovery=true` (D6). **The instant this call returns success**,
  it writes the marker with `--step prove --outcome-reason
  <unchanged-reason> --recovery-attempted` (durably spending the one
  attempt per FR-011a, regardless of what the dispatched run itself later
  does) and posts a comment naming the recovery dispatch. It does **not**
  wait for the dispatched run's conclusion — the dispatched run's own
  `prove-gate`/`prove` jobs perform the actions-only decision, the redrive,
  the wait, and the close-on-success exactly as they do for any other
  directed or ordinary entry (FR-002: no second implementation of any of
  those decisions).

**Rationale**: `select` is, again, the one job structurally guaranteed to
run on every non-`pull_request`, non-directed trigger — the same
reasoning spec 060's own displacement step (D8 in its research.md) already
established, extended here to acting rather than only recording. Reusing
the displacement step's own fetched JSON avoids a second `gh pr
list`/`gh api` round trip for data this run already has. Not waiting for
the dispatched run keeps `select`'s own job bounded and avoids
reimplementing `wing-commander-dispatch-and-wait`'s correlation for an
outcome the dispatched run's own `prove` job already needs to determine
for itself.

**Alternatives considered**: A dedicated new scheduled workflow for
recovery was rejected for the same reason spec 060's D8 rejected one for
detection — a new concurrency group, a new kill-switch check, and a new
gate-registry entry, to run a check `select` can absorb as two more steps.
Waiting synchronously via `wing-commander-dispatch-and-wait` was
considered and rejected: it would make `select`'s own run time depend on
an unrelated merge's full actions-only redrive-and-wait budget, and FR-002
already forbids reimplementing that wait outside the one place it lives.

## D4: The board-item marker gains two additive fields: `outcome_reason` and `recovery_attempted`

**Decision**: `board_item_marker.write_marker()` gains two keyword
parameters with backward-compatible defaults:

```python
def write_marker(step, round, pr, branch, base_sha,
                  outcome_reason=None, recovery_attempted=False):
```

included in the JSON payload unconditionally
(`sort_keys=True` unchanged). Every existing call site (triage, route,
fix, review, readiness writes) is unaffected — positional calls keep
working, and their markers simply carry `"outcome_reason": null,
"recovery_attempted": false` alongside the five existing keys. The CLI
(`board_item_marker.py`'s `main()`) gains `--outcome-reason` (string,
default `None`) and `--recovery-attempted` (`store_true`).

Two existing write sites start passing the new flag:

- The displacement step (`:298`) passes
  `--outcome-reason "prove run displaced"` — the same
  `board_prove_displacement.RECORDED_REASON` literal the Python function
  already returns per row, now actually read by the bash loop
  (`jq -r '.recorded_reason'`) instead of discarded, so the constant stays
  the one source of that string (FR-014).
- The `prove` job's "Record the proof outcome" step (`:4455-4506`) passes
  `--outcome-reason "$OUTCOME_REASON"` on every non-`success` arm, where
  `$OUTCOME_REASON` is the same value `board_prove.outcome_reason()`
  already computed for that run (previously used only to pick the shell
  `case` arm and the metrics label, never persisted). It also passes
  `--recovery-attempted` whenever `inputs.directed-recovery == 'true'`
  (D6) — propagating the spent flag through this run's own overwrite of
  the marker so a later re-displacement of *this* run does not look like a
  fresh, unspent one.

**Rationale**: Spec.md's FR-011c cites spec 093's "not-ready record" as
the machine-readable idiom to reuse. As of this tree, spec 093
(`specs/093-not-ready-board-release/spec.md`) is Draft with no `plan.md`,
`data-model.md`, or `contracts/` — its own Assumptions section explicitly
defers "whether that means a new marker field, a new step name, or both"
to *a* plan stage, and does not commit to a concrete shape. There is
nothing shipped to reuse. Rather than block this feature on an unplanned
dependency, or invent an unrelated second mechanism, this plan extends the
existing marker mechanism spec 093 itself points at
(`board_item_marker.py`'s JSON payload) with the minimal fields FR-011c
needs; if spec 093 is planned after this feature ships, it inherits this
precedent as the shape to extend rather than a second one to reconcile
with. This ordering fact — spec 093 not being "already defined" as spec
096's own text assumes — is flagged separately as a finding for the
intake/clarify stages, not resolved here as a spec correction.

**Alternatives considered**: A separate, second marker comment (a new
HTML-comment name via `marker_regexes()`, as `wc_lifecycle_review_marker.py`
does for spec 062's own state) was rejected — the recovery/outcome state is
per-issue, single-valued, and already co-located with the `step` it
qualifies; a second comment would need its own "newest wins" resolution
this feature has no other reason to build. Deriving `outcome_reason` from
comment prose (regex over the human sentence) was rejected outright —
FR-011c and Principle IX both forbid deciding a durable action from prose.

## D5: A new sibling module, `board_prove_recovery.py`

**Decision**: A new module, matching the one-`board_*.py`-module-per-concern
convention (`board_eligibility.py`, `board_stand_down.py`,
`board_item_marker.py`, `board_prove_displacement.py`, `board_prove.py`),
holds:

- `is_recoverable(marker)` — the pure predicate for D3 steps 2-4 above
  (`step == "prove"` and `outcome_reason` in the two recoverable literals
  and not `recovery_attempted`), taking `board_prove_displacement.RECORDED_REASON`
  as an import rather than a re-typed literal (single home, FR-014).
- `find_recoverable_items(merged_prs_by_issue, comments_by_issue,
  open_issue_numbers, bot_login)` — filters `merged_prs_by_issue`'s issues
  (the displacement step's own `board-recent-merges-by-issue.json` shape)
  to the open ones, reads each one's marker via
  `board_item_marker.read_marker_with_timestamp`, and returns
  `is_recoverable` matches sorted oldest-marker-first.
- `RECOVERY_DIRECTED_INPUT = "directed-recovery"` — the literal
  `workflow_dispatch` input name (D6), defined once so the dispatch-side
  step and the outcome-recording step never spell it independently.

**Rationale**: Keeps the judgment (which item, if any, is recoverable)
pure Python, unit-testable the same way `board_prove_displacement.py`'s
`find_undetected_merges()` already is (Principle IX), rather than a shell
`jq`/`if` chain reasoning about JSON marker fields inline in
`board-loop.yml`.

**Alternatives considered**: Folding these functions into
`board_prove_displacement.py` itself was considered — rejected because
that module's own docstring and existing tests are scoped to *detecting*
an undetected merge, not to *deciding whether to act* on one already
detected and recorded; keeping them separate keeps each module's one job
legible and each one's fixture set focused (FR-020).

## D6: A new `directed-recovery` `workflow_dispatch` input distinguishes a recovery dispatch from every other directed-stage=prove dispatch

**Decision**: `board-loop.yml` gains one more `workflow_dispatch` input,
alongside `directed-stage`/`directed-issue`/`directed-pr`:

```yaml
directed-recovery:
  description: "Directed proof run: this dispatch is recovering a previously displaced or uncorrelated proof (internal use, leave blank otherwise)"
  required: false
  default: ""
  type: string
```

Read only by the `prove` job's existing "Record the proof outcome" step
(adds one sentence to each non-`success` comment arm and one to `success`:
"the proof was displaced and has now been recovered" / "...uncorrelated,
and has now been recovered", per FR-014) and its "Determine this run's
outcome for the metrics record" step (labels the run
`"proof (recovered): <outcome_reason>"` instead of `"proof:
<outcome_reason>"` when set — FR-015's "run label that names the recovery
and is distinct from every label spec 060's taxonomy already maps", no new
`outcome_reason` enum value). It is **not** read by `prove-gate`'s
eligibility `if:`, which stays exactly as it resolves an ordinary directed
`prove` dispatch today — a recovery dispatch is, structurally, an ordinary
directed `prove` dispatch, and FR-002 forbids giving it a second decision
path.

**Rationale**: `prove-gate`/`prove`'s directed branch already re-derives
every fact it needs from `directed-issue`/`directed-pr` via live `gh`
calls rather than `github.event.pull_request` (confirmed at
`board-loop.yml:4036`, `:4209`, `:4305`, `:4426`: `PR_NUMBER: ${{
github.event.pull_request.number || inputs.directed-pr }}`) — this is the
existing self-redrive mechanism (FR-042/FR-043, spec 057/060), built
before this feature and exercised today for a different case (a merge
touching the prove step's own code). FR-010's "every fact... MUST be
re-derived from live GitHub state" is therefore already satisfied by code
that predates this feature; `directed-recovery` adds nothing to that
re-derivation, only to the label/comment text a maintainer reads
afterward.

**Alternatives considered**: Inferring "this is a recovery" from the
target issue's own marker (already carrying `outcome_reason` in one of the
two recoverable shapes) at the time `prove` writes its outcome, instead of
a dedicated input, was rejected — by the time `prove`'s outcome step runs,
the marker may already have been overwritten (e.g., a mid-flight write by
a concurrent step), and re-reading it to decide "was this a recovery"
reintroduces exactly the prose/state-inference Principle IX warns against;
an explicit input carried through the one dispatch that started this run
is a fact about *how this run started*, not a fact re-derived from mutable
state.

## D7: The resume step's stale-marker clause splits on `pr_state`, not on `marker_step`

**Decision**: `board-loop.yml`'s resume step
(`:572-871`) has one `elif` clause (today at `:792-810`) that sends *every*
`FIX_OR_LATER_STEPS` marker whose PR resolved by number but is not `OPEN`
to `triage`, clearing `pr`/`branch`/`round`/`base_sha`. This clause splits
into two:

```python
elif pr_from_marker and marker_step in FIX_OR_LATER_STEPS and pr_state == "MERGED":
    step = "prove"
    reason = "merged fix -- awaiting proof"
    pr_number = ""
    pr_state = ""
    branch = ""
    round_ = "0"
    base_sha = ""
elif pr_from_marker and marker_step in FIX_OR_LATER_STEPS:
    step = "triage"
    reason = "stale marker -- recorded pr {0} is {1}, not open".format(pr_number, pr_state)
    pr_number = ""
    pr_state = ""
    branch = ""
    round_ = "0"
    base_sha = ""
```

The second clause is exactly today's code, now reached only when
`pr_state == "CLOSED"` (unmerged) — FR-008's "falls to a fresh triage,
unchanged". The first clause is new: `step = "prove"` mirrors the exact
value `board_prove_displacement`'s own marker write already uses for this
situation, and clearing every other field satisfies FR-007's "no branch,
round or base SHA from the merged attempt leaks into whatever step it is
resolved to" the same way the existing clause already clears them for its
own case.

**Rationale**: FR-007 requires this whether or not the displacement step
has already run this tick (it may not have — the merge may be too recent
for the `-L 20` window, or this is the very run in which the merge closes
and `select`'s own displacement step and the resume step are evaluating
different data as of different moments). Since `select`'s displacement
step already runs earlier in the same job and, when it does catch a merge,
writes a `prove` marker that this same resume evaluation would then read
via clause 1 of the existing chain (`marker_step == "prove" and not
marker_pr_field` → `step = "prove"`) — this new clause is a second,
narrower path to the identical outcome for the specific window the
displacement step cannot yet have covered. It introduces no new step name
(`"prove"` is already in `FIX_OR_LATER_STEPS`, satisfying FR-009's "one
list").

**Alternatives considered**: Relying solely on the displacement step
having already written the marker (removing this clause entirely) was
rejected — spec.md's own Acceptance Scenario 1 ("whether or not spec 060's
displacement step has yet written its `prove` marker") requires the resume
step hold this invariant on its own, not merely as a consequence of timing
that happens to work out in the common case.

## D8: FR-018's gate reuses a small extraction from `joins_directed_group()`, not a re-implementation

**Decision**: `board_prove.py`'s `joins_directed_group()`
(`:383-406`) inlines its "read a workflow's own `concurrency.group` text
off the tree" step. This plan extracts that into a standalone function:

```python
def read_job_concurrency_group(workflow_path, job_name):
    """Reads jobs[job_name].concurrency.group's raw (unevaluated) text
    from workflow_path, off the checked-out tree. Returns "" if the job
    or its concurrency block is absent."""
    with open(workflow_path, encoding="utf-8") as fh:
        doc = yaml.safe_load(fh.read()) or {}
    job = (doc.get("jobs") or {}).get(job_name) or {}
    return (job.get("concurrency") or {}).get("group") or ""
```

`joins_directed_group()`'s own workflow-level read (used only for a
future *external* dispatchable target, per its docstring) is unchanged —
it reads a *workflow*-level `concurrency:` block, a different shape than a
*job*-level one, and D8's new function is additive, not a replacement.

A new gate, `verify-prove-path-concurrency.py` (next free gate number in
`lint-workflows.yml` at this tree's HEAD is 118; confirmed again at
implementation time, since numbering is assigned by wiring order, not
reserved in advance), calls `read_job_concurrency_group("board-loop.yml
path", "prove-gate")` (and `"prove"`) and asserts, against the real tree
(FR-018, precedent `verify-spec-branch-push-concurrency.py`):

1. the raw group text is not the literal `wing-commander-board-loop` (the
   ordinary group — catches an edit collapsing the split back, spec.md's
   own "A rule with no gate behind it" scenario);
2. the raw text contains both a `pull_request` discriminator and the
   literal `github.event.pull_request.number` substring — the structural
   proxy for "the key distinguishes two merged items," parsed as text
   (Gate 101's own precedent for reading YAML-embedded GitHub Actions
   expressions as text rather than evaluating them), not by constructing
   two synthetic events and diffing evaluated strings, which GitHub
   Actions expressions offer no local evaluator for;
3. `prove-gate` and `prove` resolve to the *same* raw text (so a future
   edit cannot desync the pair, which `needs: prove-gate` requires stay in
   the same group to mean anything).

Fixtures (FR-020): a passing copy of `board-loop.yml`'s two relevant job
blocks; a failing copy with the ordinary branch reverted to the shared
literal; a failing copy with the per-PR key replaced by a fixed string
literal (no `.number`); a failing copy where `prove-gate` and `prove`
diverge.

**Rationale**: FR-018 explicitly asks that "where
`board_prove.joins_directed_group()` already parses a job's group
expression, that reader MUST be reused rather than re-implemented" — the
extraction keeps a single home for "read a job's own group text off the
tree" while giving the new gate (which needs a *job*-level read
`joins_directed_group()`'s self-target shortcut never performs today) the
same primitive rather than a second YAML-parsing routine.

**Alternatives considered**: Asserting the *evaluated* group name for a
synthetic `pull_request` payload (e.g., feeding a fake `github` context
through `actionlint` or a local expression evaluator) was rejected as
disproportionate — no such evaluator exists in this repository's tooling
today, and the string-structural check (2 above) is exactly what
`verify-spec-branch-push-concurrency.py` already does for its own group
literals (`PER_SPEC_GROUP_RE`), so this is the established idiom, not a
new one.

## D9: `specs/057-.../contracts/` and `specs/060-.../contracts/` are edited during implementation, not by this plan

Per CLAUDE.md's rule that a merged spec's `spec.md`/`plan.md`/`research.md`/
`tasks.md` are historical records while its `contracts/` stay live, and per
this plan's own constraint (edit files only inside
`specs/096-durable-prove-entry`), the concrete edits D1/D2/D6/D7 describe
for `specs/057-autonomous-board-loop/contracts/prove-step.md` and
`contracts/board-item-marker.md`, and
`specs/060-self-redrive-concurrency/contracts/concurrency-groups.md`,
`directed-proof-run.md`, and `proof-outcome-taxonomy.md`, are `tasks.md`
work items during implementation (FR-021), not artifacts this plan stage
produces. This plan's own `contracts/` (below) states the target text for
each so implementation has no ambiguity about what to fold in — mirroring
`specs/060-self-redrive-concurrency/research.md`'s own D9.
