# Feature Specification: Gate 59 resolves the dispatch idiom wherever it lives

**Feature Branch**: `081-composite-aware-dispatch-gate`

**Created**: 2026-09-25

**Status**: Draft

**Input**: User description: "Gate 59 pins spec 048's dispatch idiom to auto-release.yml's own text, blocking any extraction. `verify-correlated-release-dispatch.py` checks 3, 4 and 5 assert the correlation search, tag-state outcome and wait-for-status appear in auto-release.yml's raw YAML, so moving that shell into any shared composite fails the gate by construction. Being line-based rather than an execution harness, it also cannot prove an extraction behaviour-preserving. This is what blocks tasks.md T054. Found by the implement stage of spec 057."

## Context

Two rules of this repository are, today, in direct contradiction for one
piece of shell.

**Shared logic has exactly one home.** The dispatch-then-correlate-by-attempt-token-then-wait-to-terminal
idiom now exists twice: inline in `auto-release.yml`'s `dispatch-release`
job, and in the `wing-commander-dispatch-and-wait` composite that
`board-loop.yml`'s prove job reaches it through. Spec 057's T054 exists
to collapse that to one home.

**A green check means what it says (Constitution VIII).** Gate 59
(`verify-correlated-release-dispatch.py`) protects spec 048's
correlated-and-atomic release-dispatch invariants: correlate on evidence
rather than recency, decide `released` from tag state rather than a run
conclusion, and wait for the correlated run's own status before reading
tag state. It protects them by asserting that specific text appears in
`auto-release.yml`'s own raw YAML.

The consequence is that the gate, as written, treats "the invariant is
satisfied by a composite this job calls" as identical to "the invariant
was deleted." T054 is therefore blocked, a `single-home-waivers.json`
entry keeps Gate 60 green in the meantime, and a second copy of the
idiom keeps drifting. This feature removes the contradiction: the
invariants become the thing being checked, and where the shell happens
to live becomes an implementation detail the gate follows rather than
dictates.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The gate follows the idiom into a composite (Priority: P1)

A maintainer moves the correlation search, the wait-for-status, or the
tag-state comparison out of `auto-release.yml` and into a composite
action that the `dispatch-release` job calls. Gate 59 resolves that call
and checks the invariants where the shell actually is, so a pure
relocation passes and a deletion or weakening still fails — from either
location.

**Why this priority**: This is the blocking defect. Nothing else in this
feature can land while a relocation is indistinguishable from a
deletion. It is also independently valuable: with only this story
shipped, the gate has stopped being a pin on one file's text and the
waiver above it has a path to removal, even if no shell has moved yet.

**Independent Test**: Run the gate against the tree unchanged (passes),
against a fixture where the checked shell has been relocated into a
composite the job calls (passes), and against fixtures where each
invariant is weakened in whichever location it now occupies (fails,
naming only its own clause).

**Acceptance Scenarios**:

1. **Given** the dispatch shell sits inline in `auto-release.yml` exactly as it does today, **When** the gate runs, **Then** it passes and reports which location each invariant was satisfied in.
2. **Given** the dispatch shell has been relocated verbatim into a composite the `dispatch-release` job calls, **When** the gate runs, **Then** it passes.
3. **Given** the relocated shell has had its attempt-token match removed, leaving only a time-bound comparison, **When** the gate runs, **Then** it fails naming the recency-based-selection clause (FR-001–FR-003 of spec 048) and no other clause.
4. **Given** the relocated shell decides `released` from a run's conclusion rather than a `refs/tags/` comparison, **When** the gate runs, **Then** it fails naming the tag-state clause and no other clause.
5. **Given** the relocated shell reads tag state with no prior wait on the correlated run's status, **When** the gate runs, **Then** it fails naming the mid-flight-read clause and no other clause.
6. **Given** the `dispatch-release` job names a composite that does not exist, or whose expected shell cannot be located within it, **When** the gate runs, **Then** it fails loudly as an unresolvable reference rather than reporting a pass it did not earn (Constitution VIII).

---

### User Story 2 - The shared composite carries the full dispatch outcome (Priority: P2)

The `report` job of `auto-release.yml` distinguishes six facts about a
dispatch attempt: whether the dispatch call itself was rejected, whether
correlation found exactly one run / more than one / none, that run's id
and URL, the request time it searched from, and whether the expected tag
landed on the verified head. The shared composite today reports two
(`run-url`, `conclusion`). Its contract widens to carry every fact a
caller needs to reproduce today's maintainer-facing reporting, so
adopting it costs a caller no diagnostic detail.

**Why this priority**: The gate fix (P1) unblocks relocation; this story
is what makes relocation into *this particular* composite possible
without silently coarsening the release report a maintainer reads. It is
independently testable and independently valuable — the widened outputs
are usable by `board-loop.yml`'s prove job the day they land, before any
repoint happens.

**Independent Test**: Drive the composite's shell through its existing
behavioural harness with a stubbed GitHub CLI across the found /
ambiguous / not-observed / dispatch-rejected / wait-exhausted cases, and
assert each declared output for each case.

**Acceptance Scenarios**:

1. **Given** a dispatch whose run is uniquely correlated and completes, **When** the composite finishes, **Then** it reports the correlation outcome as found, the run's id and URL, the request time it searched from, that the dispatch was not rejected, and the run's terminal conclusion.
2. **Given** two runs match the attempt token, **When** the composite finishes, **Then** it reports the correlation outcome as ambiguous and empties the run id, URL and conclusion rather than picking the newest match.
3. **Given** no run matches within the correlation budget, **When** the composite finishes, **Then** it reports the correlation outcome as not-observed and still reports the request time it searched from.
4. **Given** the dispatch call itself is rejected, **When** the composite finishes, **Then** it reports the dispatch as rejected, the correlation outcome as not-observed, and performs no correlation search.
5. **Given** the correlated run has not reached a terminal status within the wait budget, **When** the composite finishes, **Then** it reports the wait as exhausted rather than reporting an absent or successful conclusion.
6. **Given** an existing caller that reads only the two outputs the composite reports today, **When** the widened composite ships, **Then** that caller's behaviour is unchanged (the existing outputs keep their names and meanings).

---

### User Story 3 - auto-release.yml reaches the idiom through its one home (Priority: P3)

`auto-release.yml`'s `dispatch-release` job is repointed at the shared
composite. Its `report` job produces byte-identical maintainer-facing
output for every dispatch outcome it distinguishes today. The
`dispatch-and-wait` waiver in `single-home-waivers.json` is removed, and
Gate 60's withheld half — failing while `auto-release.yml`'s call site
still resolves the old inline path — is switched on, so the second copy
cannot come back.

**Why this priority**: This is the payoff, but it depends on both stories
above and is the only part that changes production release behaviour, so
it lands last and behind the behavioural evidence the first two stories
produce.

**Independent Test**: Run the composite's behavioural harness and the
release-dispatch gate against the repointed tree, confirm the waiver is
gone and Gate 60 is green, and confirm Gate 60 fails on a fixture where
the inline copy is restored.

**Acceptance Scenarios**:

1. **Given** the repointed `dispatch-release` job, **When** a release is dispatched and uniquely correlated and the tag lands on the verified head, **Then** the `report` job's summary text is identical to what the inline implementation produced for that outcome.
2. **Given** the repointed job and an ambiguous, not-observed, or rejected dispatch, **When** the `report` job runs, **Then** its correlation note names the same outcome, the same version, and the same request time the inline implementation would have.
3. **Given** the repointed job and a correlated run that fails while the expected tag nonetheless lands on the verified head, **When** the `report` job runs, **Then** it reports a release — the verdict is still tag state, never the run's conclusion (spec 048 FR-007/FR-007a).
4. **Given** the repoint has landed, **When** the single-home gate runs, **Then** no `dispatch-and-wait` waiver remains and the gate is green.
5. **Given** a change that pastes the correlate-and-poll shell back into any workflow, **When** the single-home gate runs, **Then** it fails.

---

### Edge Cases

- The `dispatch-release` job calls a composite that in turn calls another composite: how deep does the gate follow? (See Assumptions — one level, failing loudly beyond it, rather than silently stopping.)
- The composite that satisfies an invariant is also called by an unrelated workflow: the gate must not conclude from that second call site that `auto-release.yml`'s own invariant is satisfied.
- A composite reference that resolves but whose shell no longer contains the searched-for construct: distinguishable from "the composite is missing", and both fail.
- A dispatch is rejected outright: the correlation search never runs, so no correlation-based invariant can be satisfied at runtime — the gate checks the shipped shell, not a particular run, and must not be confused by the rejected path's early exit.
- Today's uncorrelated path waits a fixed bounded interval before reading tag state; the shared composite does not wait at all on that path. A repoint that drops the wait would reintroduce exactly the mid-flight tag read spec 048's check 5 exists to prevent.
- Both `auto-release.yml` and the composite are edited in the same pull request: the gate must be triggered by a change to either file, not only by a change to the workflow.
- The gate's own self-test must exercise every failure branch in both the inline-satisfied and composite-satisfied forms, or half the shipped branches are uncovered (Constitution VIII).

## Requirements *(mandatory)*

### Functional Requirements

**The gate resolves rather than pins**

- **FR-001**: The release-dispatch regression gate MUST verify spec 048's correlation, tag-state-outcome and wait-before-tag-read invariants against the effective implementation of `auto-release.yml`'s `dispatch-release` job — the job's own steps plus the shell of any composite action those steps call — rather than against `auto-release.yml`'s raw text alone.
- **FR-002**: The gate MUST pass when an invariant is satisfied entirely inside a called composite and no longer appears in `auto-release.yml`'s own text.
- **FR-003**: The gate MUST still fail when an invariant is weakened or removed, regardless of which of those locations the shell occupies, and each failure MUST name only its own clause and the spec 048 requirement it protects.
- **FR-004**: When the gate cannot resolve a referenced composite, or resolves it but cannot locate the shell it is meant to inspect, it MUST fail with a message that says so, naming the unresolvable reference. It MUST NOT treat an unresolvable reference as either a pass or as evidence the invariant was deleted.
- **FR-005**: The gate MUST attribute each satisfied invariant to the location that satisfied it, so a maintainer reading a pass can see whether the guarantee currently lives in the workflow or in a composite.
- **FR-006**: The gate MUST only credit a composite that the `dispatch-release` job itself reaches; a composite satisfying the invariant but called only from elsewhere in the repository MUST NOT count.
- **FR-007**: The gate's self-test MUST exercise every failure branch it ships in both the inline-satisfied and composite-satisfied arrangements, using checked-in fixtures, and MUST fail if any branch is unreachable.
- **FR-008**: The gate MUST be triggered by changes to any file it reads — the workflow and every composite it resolves through — not by changes to the workflow alone.
- **FR-009**: Spec 048's checks 1 and 2, which concern `release.yml` rather than `auto-release.yml`, MUST retain their current behaviour and failure messages unchanged.
- **FR-010**: The gate MUST run identically locally and in CI, with the same subject and arguments, and remain reachable through the gate registry.

**The shared composite's outcome contract**

- **FR-011**: The shared dispatch-and-wait composite MUST report, in addition to what it reports today: whether the dispatch call was rejected; the correlation outcome as one of exactly three states — found, ambiguous, not-observed; the correlated run's identifier; and the request time the correlation search searched forward from.
- **FR-012**: The composite MUST NOT collapse the ambiguous and not-observed states into one another or into a "no run" absence, and MUST NOT resolve ambiguity by selecting the most recent candidate.
- **FR-013**: The composite MUST continue to report its existing outputs under their existing names with their existing meanings, so callers written against today's contract keep working unchanged.
- **FR-014**: The composite MUST offer a caller-settable bounded wait applied when no single run could be correlated, so a caller that reads state which the dispatched run is expected to have changed can avoid reading it while that run may still be in flight. Its default MUST preserve the behaviour of existing callers.
- **FR-015**: The composite's behavioural harness MUST cover every state in FR-011 and FR-014 by executing the composite's own shipped shell against a stubbed command surface, not by re-implementing it.
- **FR-016**: Widening this contract MUST be additive: no existing input or output is removed or renamed, and the widening is recorded as a deliberate act on the published, adopter-pinned surface (Constitution VII).

**Repointing and single-home enforcement**

- **FR-017**: `auto-release.yml`'s `dispatch-release` job MUST reach the dispatch-correlate-wait idiom through the shared composite, with no second copy of that shell remaining in the repository.
- **FR-018**: The repointed job MUST preserve every maintainer-facing outcome the `report` job distinguishes today — released, no release because the branch advanced, dispatch failed, dispatched but no tag landed — and the correlation note appended to each, for every combination of dispatch-rejected, correlation outcome, and tag state.
- **FR-019**: The release verdict MUST remain a fresh, post-dispatch comparison of tag state against the verified head, decided independently of the correlated run's conclusion and of whether correlation succeeded at all.
- **FR-020**: The `dispatch-and-wait` entry in the single-home waiver register MUST be removed once the repoint lands, and the single-home gate MUST then fail if `auto-release.yml`'s call site resolves anything other than the shared composite.
- **FR-021**: The single-home gate MUST fail if the correlate-and-poll shell is pasted into any workflow or any second composite.
- **FR-022**: Because this behaviour only runs in GitHub Actions, the repoint MUST be proven after merge by re-driving one real run and recording the evidence on the pull request or the lifecycle issue.

**Provenance and documentation**

- **FR-023**: Spec 057's T054 and the withheld half of its T056, and spec 048's gate contract, MUST be updated to record that the blocker is resolved and how — no task or contract may keep describing a constraint that no longer holds.
- **FR-024**: The gate MUST document, in its own header, that it resolves through composites and which locations it searches, so the next maintainer to move this shell learns the rule from the gate rather than from a failure.

**Open questions carried into planning**

- **FR-025**: The gate MUST establish, beyond the textual invariants above, [NEEDS CLARIFICATION: whether the resolved-through-composite arrangement must additionally be proven by executing the shipped shell — extending the composite's behavioural harness to assert the three spec 048 invariants at runtime — or whether a resolving textual gate plus the existing harness coverage is the intended bound. The originating issue names "cannot prove an extraction behaviour-preserving" as part of the defect.]
- **FR-026**: The widened composite contract MUST take the shape of [NEEDS CLARIFICATION: discrete named outputs, one per fact (matching today's style, growing the adopter-pinned output surface by four), or a single structured outcome output the caller destructures (one new output, but callers must parse it)?]
- **FR-027**: The tag-state verification that decides `released` MUST live [NEEDS CLARIFICATION: in `auto-release.yml`'s own job, as release-specific logic the generic composite has no business knowing about — in which case the gate resolves checks 3 and 5 through the composite but keeps check 4 pinned to the workflow — or inside the composite behind an optional "expected ref" input, so one home covers the whole idiom?]

### Key Entities

- **Release-dispatch regression gate**: The deterministic check protecting spec 048's invariants. Owns the resolution rule, the failure clauses, and its own self-test fixtures.
- **Dispatch-and-wait composite**: The single home for the dispatch-correlate-wait idiom. Owns the outcome contract every caller reads.
- **`dispatch-release` job**: `auto-release.yml`'s call site. Owns the release-specific concerns the generic idiom does not cover — the verified head, the expected version tag.
- **`report` job**: The only maintainer-facing writer for this feature. Consumes the outcome facts and is the reason the contract must widen.
- **Single-home waiver register**: The open record of known, temporary deviations from the one-home rule, stale-checked in both directions. Holds the entry this feature retires.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Relocating any of the three checked invariants out of the workflow and into a composite the job calls produces a passing gate run, where today it produces a failing one — demonstrated by a checked-in fixture, not by a one-time manual run.
- **SC-002**: Every failure branch the gate ships fails on a checked-in fixture in both the inline-satisfied and composite-satisfied arrangements; zero branches are reachable only in one of the two.
- **SC-003**: Each of the three invariant failures names exactly one clause; no fixture produces a failure naming a clause it did not mutate.
- **SC-004**: A composite reference that cannot be resolved produces a failure that names the reference, in 100% of the unresolvable cases the fixtures cover — never a pass.
- **SC-005**: Every dispatch outcome the release report distinguishes today is reproducible from the composite's reported facts alone; a side-by-side comparison of report text for each outcome shows zero differences after the repoint.
- **SC-006**: The repository contains exactly one copy of the dispatch-correlate-wait shell, and the single-home register contains zero `dispatch-and-wait` waivers.
- **SC-007**: The full pull-request gate suite is green on the final head, with no gate skipped, waived, or newly excluded to accommodate this change.
- **SC-008**: One real dispatch run is re-driven after merge and its outcome recorded on the pull request or the lifecycle issue.
- **SC-009**: No existing caller of the composite requires an edit to keep working, and no input or output is removed or renamed.

## Assumptions

- The three invariants at issue are exactly spec 048's checks 3, 4 and 5 (correlation on evidence, tag-state outcome, wait-before-tag-read). Checks 1 and 2 concern `release.yml`, are not implicated by any extraction, and are out of scope beyond leaving them working.
- Composite resolution follows calls made by the `dispatch-release` job one level deep. A composite that itself delegates the checked shell to a further composite is treated as unresolvable and fails loudly (FR-004) rather than being followed indefinitely or silently abandoned; deepening that later is a separate decision.
- The gate remains deterministic code with checked-in fixtures. Nothing in this feature moves a judgment that gates a durable action into a prompt (Constitution IX).
- Today's fixed bounded wait on the uncorrelated path is behaviour worth preserving, not an accident; the composite gains a caller-settable equivalent (FR-014) whose default leaves the existing prove-job caller unchanged.
- The composite lives under the published, adopter-pinned surface, so widening its contract is additive and deliberate (Constitution VII), never a rename.
- The `report` job's summary text is the compatibility surface for FR-018 — maintainers read it, and a spec 048 contract describes it — so "preserved" means the same text for the same outcome, not merely the same outcome classification.
- Spec 057's T054/T056 notes and its waiver entries are the authoritative record of why this is blocked today; updating them is part of the change rather than follow-up bookkeeping.
- No change to spec 048's own requirements is intended. This feature changes how those requirements are verified and where the shell that satisfies them lives — never what they require.
