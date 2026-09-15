# Research: Correlated, atomic release dispatch

This feature has no unresolved `[NEEDS CLARIFICATION]` markers in
`spec.md` — the three open design questions were already settled in the
spec's own Clarifications session (2026-09-14). What remains here is the
mechanical research needed to turn those three answers into concrete
GitHub Actions primitives, plus decisions the spec deliberately left to
the implementation ("the shape of the evidence was the owner's decision"
— but the *plumbing* that carries that shape is not).

## D1: What "an attempt-identifying token" is, concretely

**Decision**: `${{ github.run_id }}-${{ github.run_attempt }}` of the
`auto-release.yml` run that is doing the dispatching, generated once in
`dispatch-release` and reused everywhere that job needs it (the dispatch
call, the correlation search, and the report).

**Rationale**: `github.run_id` is unique across this repository's entire
run history (GitHub's own guarantee — it is the value the Actions UI
permalinks on), so two attempts can never mint the same token by
construction, satisfying FR-002a without a counter, a random-number
generator, or a piece of state that would have to be persisted
somewhere. `github.run_attempt` is included so that a *manual re-run* of
the same `auto-release.yml` run (via the Actions UI's "Re-run failed
jobs") — which reuses `run_id` but increments `run_attempt` — still mints
a distinct token, rather than colliding with the original attempt's
already-dispatched run.

**Alternatives considered**:
- A random UUID (`uuidgen` / `$RANDOM`): rejected — it works, but it is
  one more thing that could (in principle) collide, needs an extra
  step to generate, and buys nothing over a value GitHub already
  guarantees unique for free.
- The version string alone: rejected outright — this is exactly the
  identity spec.md's Edge Cases section names as insufficient (two
  attempts can legitimately request the same version).
- A timestamp: rejected — two attempts started in the same second would
  collide, and clock skew between the runner and GitHub's API makes
  string timestamps an awkward join key next to `run_id`.

## D2: How the token and version reach the release run's *title*

**Decision**: `release.yml` gains a top-level `run-name:` key (a first-class
GitHub Actions field, distinct from the job name or any step name — it
is what the Actions UI and `gh run list --json displayTitle` both call
the run's title) computed from two new optional `workflow_dispatch`
inputs:

```yaml
run-name: "release ${{ inputs.version }} [attempt:${{ inputs.attempt-token }}]"

on:
  workflow_dispatch:
    inputs:
      version: { ... }            # unchanged
      breaking: { ... }           # unchanged
      breaking-notes: { ... }     # unchanged
      attempt-token:
        description: "Correlation token for an automatic dispatch (internal use; leave blank for a manual release)"
        required: false
        default: ""
        type: string
      commit:
        description: "Exact commit to release (internal use; leave blank to tag the branch tip, as today)"
        required: false
        default: ""
        type: string
```

A manual dispatch that leaves `attempt-token` at its `""` default
produces the title `release v1.4.0 [attempt:]` — no non-empty token can
ever equal the empty string, so FR-016 ("a dispatch carrying no attempt
token MUST produce a run title that no attempt's correlation can match")
holds by construction, and no separate "is this a manual run" branch is
needed anywhere.

**Rationale**: `run-name:` is GitHub's own mechanism for exactly this —
a computed, per-run display title — and it is readable back through
`gh run list --json displayTitle` with no extra API calls or artifact
plumbing. The `[attempt:...]` bracket wrapping is deliberate (see D3):
it gives the token a closing delimiter so a numeric-prefix collision
(token `18234567-1` cannot match a title carrying `18234567-10`) is
impossible, not just unlikely.

**Alternatives considered**:
- Passing the token through a job *output* instead of the title: rejected
  — job outputs from a `workflow_dispatch` run are not readable by a
  *different* workflow's run without either an artifact (extra steps,
  extra failure modes, retention lag) or the run listing itself, and the
  spec's own clarification names the title specifically ("the release
  automation gains a run title carrying the version").
- Embedding the token as a release-notes / commit-message fragment:
  rejected — that pollutes the user-facing release notes with
  machine plumbing, and is not readable until the run has already
  created the tag, too late to correlate a still-running attempt.

## D3: The selection algorithm (FR-001–FR-006)

**Decision**: `dispatch-release` records `request_time` (an epoch second,
captured with `date -u +%s` immediately before `gh workflow run`) and the
token from D1, then polls (same budget shape as today's existing run-
discovery loop, ~60s of 5s intervals — see D9 on why this number is not
load-bearing) calling:

```
gh run list --workflow=release.yml --json databaseId,displayTitle,createdAt,url -L 20
```

On each poll, filter the returned rows to those whose `displayTitle`
contains the exact substring `[attempt:<token>]` **and** whose
`createdAt` (parsed with `date -u -d "$createdAt" +%s`) is strictly
greater than `request_time`. Three outcomes:

- **Exactly one match** → that run is the correlated run (FR-001,
  FR-002). Its `databaseId`/`url` are kept for the report's log link
  only (Key Entity "Correlated run") — never for the release verdict.
- **Two or more matches** → `correlation: ambiguous` (FR-004). This
  should not happen given D1's uniqueness guarantee, but the spec
  requires it be handled as its own outcome rather than picking one,
  so the code checks for it explicitly rather than assuming the
  token already rules it out.
- **Zero matches when the poll budget elapses** → `correlation:
  not-observed` (FR-005).

Both the token match *and* the time bound are always evaluated, even
though a correctly-unique token (D1) already makes the time bound
logically redundant in the common case. The spec's own clarification
answer treats them as two independent controls ("The title establishes
identity; the time bound closes the case...", FR-002 and FR-003 are
separate requirements) — kept independent here rather than collapsed
into one, so Gate 52 (see D7) can verify both are still present
separately, and a future edit that weakens token generation does not
silently also remove the second control.

**Rationale**: this reuses primitives (`gh run list`, a poll loop) that
are already this workflow's idiom (research.md D12 of specs/045) rather
than introducing a new dependency, and keeps the join entirely textual
and deterministic (Constitution IX) — no step here asks an agent to
decide which run is "ours".

**Alternatives considered**:
- Matching on `event`/`actor` instead of title: rejected — every
  dispatch (manual or automatic) shares the same actor identity (the
  same token mints them, or a maintainer's own identity is
  indistinguishable from another maintainer's), so this carries no
  correlating power. The spec's own Q&A already settled on title +
  time.
- A GraphQL query instead of `gh run list`: rejected — no capability
  `gh run list --json` lacks here, and the REST/GraphQL split is not
  otherwise present in this workflow.

## D4: Enforcing "the verified head is the tagged commit" (FR-009–FR-014)

**Decision**: `release.yml`'s existing `Checkout` step gains
`ref: ${{ inputs.commit || github.event.repository.default_branch }}`
(empty `commit` ⇒ today's implicit default-branch checkout, unchanged
— FR-015). A new step, inserted immediately before "Create tags" (after
Gate 1a/1b and "Validate version and plan tags" have already run, so a
stale-head request still gets full linting first — cheap and harmless
since nothing was written yet), runs only `if: inputs.commit != ''`:

```
current_tip="$(git ls-remote origin "refs/heads/${DEFAULT_BRANCH}" | cut -f1)"
if [ "$current_tip" != "$COMMIT_INPUT" ]; then
  echo "::error::release requested commit ${COMMIT_INPUT}, but refs/heads/${DEFAULT_BRANCH} is now at ${current_tip} -- refusing to tag (the branch moved on)."
  exit 1
fi
```

where `DEFAULT_BRANCH` is `${{ github.event.repository.default_branch }}`
— see D6 on why this reads dynamically rather than the literal `main`
this decision originally proposed.

`git ls-remote` is a live read against `origin` at the moment this step
runs, not a re-use of anything captured at checkout or at request time —
this is what closes the queueing gap (FR-010a): a request that sat
behind another `release.yml` run in the `wing-commander-release`
concurrency group only reaches this step after that run has finished,
and re-reads the tip *then*.

A commit that is an ancestor of the tip, was force-pushed away, or was
never on the default branch at all are all refused by the same single
string comparison (FR-014) — no ancestry walk is needed because the
check is "is it still the exact tip", not "is it still reachable".

**Rationale**: doing the comparison at the last possible moment, against
a live remote read, is the only placement that satisfies FR-010a's
explicit "not against anything read when the request was accepted or
when the checkout was made". This decision originally proposed a literal
`main` here (see D6); the shipped code reads the default branch
dynamically instead — D6 records why.

**Alternatives considered**:
- Comparing against the local checkout's `HEAD` (already fetched at job
  start): rejected — that is exactly the request-time/checkout-time
  window the spec explicitly rejects ("assert-only" per Clarification
  Q3), since the checkout can be minutes stale by the time the tag step
  runs, especially behind a queued concurrency group.
- Re-checking out the repository fresh right before tagging instead of
  a bare `ls-remote`: rejected — needlessly heavier (a full fetch) for a
  question that needs exactly one ref's SHA.

## D5: "Released" is decided from tag state, not run conclusion

**Decision**: after the correlation poll (D3) concludes — whether it
found a run, found none, or found several — `dispatch-release` performs
one more, independent check, regardless of the correlation outcome:

```
git fetch origin "refs/tags/${NEXT_VERSION}:refs/tags/${NEXT_VERSION}" --quiet 2>/dev/null || true
tag_matches=false
if git rev-parse -q --verify "refs/tags/${NEXT_VERSION}^{commit}" >/dev/null; then
  [ "$(git rev-parse "${NEXT_VERSION}^{commit}")" = "$VERIFIED_HEAD" ] && tag_matches=true
fi
```

If `tag_matches` is true, the outcome is **`released`** — full stop,
independent of whether `release.yml`'s own run conclusion was `success`,
independent of whether the correlated run was found at all (Edge Case
"the release actually happened but was never correlated"). If
`tag_matches` is false, a second, independent check classifies *why*:

```
default_branch="$(gh repo view "$GITHUB_REPOSITORY" --json defaultBranchRef --jq '.defaultBranchRef.name // empty' 2>/dev/null || true)"
[ -n "$default_branch" ] || default_branch="main"
current_tip="$(git ls-remote "https://github.com/${GITHUB_REPOSITORY}.git" "refs/heads/${default_branch}" | cut -f1)"
if [ "$current_tip" != "$VERIFIED_HEAD" ]; then
  outcome=branch-advanced   # FR-013: expected, same class as today's stale-head skip
else
  outcome=release-failed    # branch never moved and no tag landed -- a real defect
fi
```

(the `report` job runs off a `schedule` trigger, whose event payload
carries no `repository` key, so `github.event.repository.default_branch`
is not available here the way it is in `release.yml`'s `workflow_dispatch`
job — the live `gh repo view` read, with a `main` fallback if that read
fails, is this job's equivalent; see D6.)

**Rationale**: this is the direct implementation of FR-007 ("the report
MUST record a release as having happened on the tag state alone") and
Constitution IX (the durable, reportable judgment — "did a release
happen" — is a deterministic git comparison, never an inference from a
workflow run's green/red conclusion, an agent's summary, or which run
got correlated). It also means `release.yml`'s own run is free to fail
loudly on a stale-head refusal (`exit 1`, D4) for the benefit of a
maintainer glancing at its own Actions tab, without `auto-release.yml`
having to parse that failure's *reason* out of logs to avoid
misclassifying it (FR-013) — the two workflows need no shared
out-of-band signal beyond the tag and the branch tip, both of which are
plain git state either workflow can read on its own.

**Alternatives considered**:
- Keeping `release-outcome` derived from `gh run watch <id> --exit-status`
  (today's mechanism): rejected — this is precisely the defect FR-007
  exists to close; a cancelled run, a run that failed after tagging (the
  GitHub Release creation step, say), or an ambiguous/not-observed
  correlation would each either wrongly claim or wrongly deny a release
  that the tag state alone answers correctly.
- Having `release.yml` write its refusal reason to a location
  `auto-release.yml` can read (an artifact, a check run, a commit note):
  rejected as unnecessary complexity — the branch-tip re-read in
  `auto-release.yml` reconstructs the same fact release.yml already
  computed, using primitives already present in this job, with no new
  cross-workflow channel to build, secure, or keep in sync.

## D6: Why `main` does not stay a literal here (reversed)

**Original decision (superseded)**: this plan originally proposed
keeping the default branch spelled as the literal `main` in both new
checks (D4's tag-time refusal, D5's branch-advanced classification),
matching the literal already present in `auto-release.yml`'s existing
`dispatch-release` job (`gh api repos/${{ GITHUB_REPOSITORY }}/commits/main`),
on the grounds that neither workflow is a published stage under
Constitution VII (Gate 50's "no literal `main`" rule, scoped to
`wc_published_stages()`, does not reach either file) and that a
`default-branch` input would be unneeded configuration surface.

**Reversal**: the maintainer's code review of PR #342 (T027, folded
into this feature's own shipped code before merge) identified that this
framing missed a real defect: `release.yml`'s own `Checkout` step
already resolves the default branch dynamically via
`github.event.repository.default_branch` (D4) — a literal `main` in the
*refusal* step two steps later would compare the checked-out commit
against the wrong ref on any repository whose default branch is not
literally `main`, refusing (or worse, wrongly permitting) a tag for a
reason that has nothing to do with FR-010a. This is not the
reusable/published-stage concern Gate 50 polices — it is a plain
correctness bug in this repository's own workflows, which the original
"scope creep" framing did not anticipate because it was evaluating the
question as "should we add configuration surface", not "does the
literal already disagree with a value the same job computes two steps
earlier."

**Shipped decision**: `release.yml`'s refusal step (D4) reads
`DEFAULT_BRANCH: ${{ github.event.repository.default_branch }}` — safe
there because this job only runs on `workflow_dispatch`, the same event
its `Checkout` step already relies on for the same value.
`auto-release.yml`'s `report` job (D5) cannot reuse that expression — it
runs off a `schedule` trigger, whose event payload carries no
`repository` key — so its classification step instead reads the default
branch live via `gh repo view "$GITHUB_REPOSITORY" --json
defaultBranchRef --jq '.defaultBranchRef.name // empty'` (the same
pattern the `detect` job already uses for the E2E test repository),
falling back to the literal `main` only if that read itself fails.
`auto-release.yml`'s pre-existing `dispatch-release` short-circuit that
also hardcoded `commits/main` was removed entirely by T013, for the
unrelated reason of being fully superseded by D4/D5's checks — so it
carries no remaining literal to reverse.

**Alternatives considered (at the time of the reversal)**:
- Leaving the literal in place: rejected — it is not hypothetical
  scope creep once a concrete second value (the checkout's own resolved
  ref) exists in the same job to disagree with it.
- Adding a `default-branch` workflow input: rejected — the value is
  already available for free from the triggering event
  (`workflow_dispatch`) or a live API read (`schedule`); a new input
  would just be a third, redundant place this could drift.

## D7: The deterministic regression gate (FR-018, SC-005, Constitution VIII)

**Decision**: a new gate script, `.github/scripts/verify-correlated-release-dispatch.py`,
following the established shape of Gate 50
(`verify-release-contract.py`) and Gate 51
(`verify-rate-limited-exemption.py`): a small, textual, line-based
checker with its own `--self-test` exercising each failure branch
against an in-memory fixture, registered as the next PR-time step in
`lint-workflows.yml` (Gate 52 at plan time — tasks/implement must
re-check for a collision with a concurrently-landing spec before
claiming that number) and therefore auto-included in
`run-local-gates.py` (which derives its list from `lint-workflows.yml`,
not a hand-maintained copy).

It asserts, over `.github/workflows/release.yml` and
`.github/workflows/auto-release.yml` specifically (not the derived
published-stage set — these two are not published stages, see D6):

1. `release.yml` declares a `run-name:` that references both
   `inputs.version` and `inputs.attempt-token` (regexp over the raw YAML
   text, the same "grep, not a YAML-semantic diff" style Gate 50 uses) —
   catches "dropped the attempt token from the release run's title".
2. `release.yml` contains a tag-time tip comparison — a line matching
   `git ls-remote origin "refs/heads/${DEFAULT_BRANCH}"` (the dynamic
   default branch, T027) appearing textually *after*
   the "Create tags" step's own marker in the file — catches "removes
   the tag-time tip refusal" (ordering, not just presence, since a
   comparison placed before checkout would be the request-time check
   the spec rejects).
3. `auto-release.yml`'s correlation step references `createdAt` (or the
   equivalent time-bound field) *and* the attempt-token match in the
   same step — catches "reintroduces recency-based selection" (a
   selection step that reads only `-L 1`/`.[0]` off `gh run list` with
   no token filter is exactly today's pre-feature code, and would fail
   this check).
4. `auto-release.yml`'s report/outcome logic computes `released` from a
   tag comparison (`git rev-parse` / `rev-parse -q --verify` against a
   `refs/tags/` ref) rather than from a run's `conclusion`/`status`
   field — catches "lets a release be reported from a run conclusion
   instead of the tag state".
5. `auto-release.yml` waits for the correlated run's own `status` (a
   `gh run view ... --json status` poll, never `.conclusion`) to reach
   a terminal state before the tag fetch that decides `released` —
   catches "reads tag state immediately after correlation, which can
   observe a correlated run still mid-flight and file a false
   dispatch-failed report" (added for T025).

**Rationale**: Constitution VIII requires every gate be able to fail its
own subject; each of the five checks above is a direct, line-addressable
mutation away from the regression FR-018 names for it, so the script's
`--self-test` can assert each one fails on the one mutation it exists to
catch (exactly Gate 50's self-test shape) and passes on a fixture
carrying every allowed form.

**Alternatives considered**:
- A single broad "grep for the word `recency`" style check: rejected —
  not falsifiable against a real mutation, the shape Constitution VIII's
  prior-art list (#139, #158) already names as a check that reads as
  evidence while proving nothing.
- Folding these checks into Gate 50 (`verify-release-contract.py`):
  rejected — Gate 50's subject is the derived *published-stage* set;
  `release.yml`/`auto-release.yml` are deliberately outside that set
  (D6), so extending Gate 50 to reach them would blur what "published
  stage" means for every other caller of `wc_published_stages()`. A new
  gate with its own explicit two-file subject list keeps Gate 50's
  contract unchanged.

## D8: Where the FR-019 single contract document lives

**Decision**: `specs/048-correlated-release-dispatch/contracts/release-handover-contract.md`
is the one canonical document FR-019 requires. It supersedes the
version-only parts of specs/045's `release-dispatch.md` and
`auto-release-workflow.md` for everything this feature changes (the
title/token contract, the commit input and its refusal, the
tag-state-is-authoritative rule); implementation-stage code comments in
both workflows point at the new document for those specifics, the same
way `release.yml`'s Gate 1b comment already points at
`.github/scripts/verify-release-contract.py`'s own docstring as "the one
place the contract lives" for its three checks. specs/045's documents
are left in place for what they still correctly describe (the
end-to-end verification job, the version-computation rules, the failure
report's dedup-by-label mechanism) — this feature narrows, it does not
replace, that prior contract.

**Rationale**: FR-019 is explicit ("written down in one place, with
each workflow pointing at it rather than restating it") and this
repository already has the working pattern for exactly that (Gate 50's
docstring, `wc_published_stages.py`'s shared derivation) — reuse it
rather than inventing a second convention for "the one place a contract
lives".

## D9: The waiting-period budget is not a correctness property

**Decision**: keep the existing ~60-second budget shape (today's
`attempt -lt 12`/`sleep 5` loop) for the correlation poll, rather than
tuning it as part of this feature.

**Rationale**: the spec's own Assumptions section says this explicitly
— "the current value is assumed adequate until evidence says otherwise
... resting the released/not-released decision on the tag state is what
keeps it from becoming a correctness property" (this is D5's point
restated: even if the poll times out with zero/ambiguous correlation,
D5's tag check still reaches the right `released`/`branch-advanced`/
`release-failed` answer on its own). Changing the number here would be
solving a problem the spec has not identified evidence for.

## D10: Manual path regression surface (FR-015–FR-017, SC-003)

**Decision**: no change beyond D2's two new optional inputs (already
default to `""`) and D4's `ref:` becoming conditional on `inputs.commit`
(empty ⇒ identical behavior to today's unconditional default checkout).
No new required input, no new step runs when both new inputs are left
blank — the tag-time comparison step's own `if: inputs.commit != ''`
is the single gate that keeps a manual dispatch's behavior byte-for-byte
unchanged (Story 3's three acceptance scenarios, FR-017).

**Rationale**: this is the natural consequence of D2 and D4's designs
rather than a separate mechanism — called out here because SC-003 and
FR-017 both treat "did we add a gate to the human path" as its own
measurable outcome, worth a deliberate research decision rather than an
implicit side effect.
