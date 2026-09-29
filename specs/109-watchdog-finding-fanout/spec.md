# Feature Specification: Watchdog Dedup That Survives Partial Signal Overlap and Class Fan-Out

**Feature Branch**: `spec-draft/109-watchdog-finding-fanout`

**Created**: 2026-09-29

**Status**: Draft

**Input**: Lifecycle issue #792 — "watchdog: one underlying failure fans
out into several issues — findings split by class, and the fingerprint
hashes the exact cited-signal set"

## Overview

The watchdog's dedup identity is `sha256(class | sorted(cited signal
ids))`, and the lookup that consumes it matches that hash **exactly**,
inside the finding's **own class label**. Both halves of that sentence are
a filter that one underlying failure can slip past, and the tracker shows
it slipping past both.

**Partial overlap never matches.** Signal ids are deliberately stable
across runs — they are hashed from a per-source projection that keeps only
the facts identifying the problem and drops the ones describing this
occurrence of it. So the *same* signal recurs run after run with the *same*
id. But the agent that writes a finding chooses **which** ids to cite, and
that choice varies with what else the run happened to contain. A finding
citing `{A,B}` and a later one citing `{A,C,D}` hash differently, so the
second files a fresh issue while the first sits open describing the same
defect. Three open `gate-suite-failure` issues (#729, #732, #765) all cite
signal `1bcf7944887991cd` and none of them deduplicated onto the others.

**Class is half the key, and the agent picks the class.** Findings are
diagnosed per run as an array; each one carries its own class, each class
has its own label, and the dedup lookup is scoped by that label. So a
single red gate suite described six ways becomes six issues. Run
36484099706 filed #708, #709, #710, #711, #712 and #713 in the same
minute. The answer to this half (see Clarifications) is not to group the
six — it is that a converging implement cycle's red gate suite is not a
defect the watchdog should have filed on at all.

The repository already knows this shape of bug. The signal-id stamper
carries a comment written for exactly one instance of it — the
`turn-budget` and `turn-budget-trend` collectors were given one shared
`kind` precisely so that "a Finding may cite this signal alone, the trend
signal alone, or both … all three citation subsets must collapse to one
basis — otherwise the fingerprint, and therefore FR-012s one accumulating
finding, would depend on which subset diagnose happened to cite this run."
That fix made two *sources* collapse to one id. It did nothing about two
findings citing two different *subsets* of the ids, which is the general
case the comment describes and this feature has to answer.

What is **not** in scope is the tool-denial separation. `tool-denial`
signal ids are keyed per `{stage, tool}` on purpose (#266), so each
stage's denials accumulate on their own issue and a reopen means a
regression in that stage. #761, #764 and #780 are three different
stage/tool pairs and are three correct issues, not a fan-out. Any rule
this feature adopts has to leave them alone.

This is a design question, not a plumbing fix: it changes the "one
accumulating finding per fingerprint" contract (FR-012–FR-016 of spec 015,
as amended by spec 024) and it can only be made safe by choosing what
counts as "the same underlying failure" — a choice with a false-merge cost
on one side and a fan-out cost on the other. That is why it is specced
rather than patched.

### Observed facts (verified against main at 73be417; re-check cited line numbers at plan time)

- `.github/workflows/watchdog.yml:3142-3170` ("Compute fingerprint")
  intersects the finding's cited `signalId`s with the ids `collect`
  actually emitted, sorts and comma-joins the survivors, and hashes
  `"<class>|signals:<joined>"`. The joined set is the whole basis; there is
  no per-id projection of it.
- `.github/workflows/watchdog.yml:3175-3225` ("Dedup search") lists issues
  filtered by `--label "pipeline-defect" --label "🐕 · <class>"`,
  `--state all --limit 200`, then selects locally for bodies containing
  `fingerprint=<the exact hash>`. Two consequences follow directly: a
  candidate outside the finding's own class label is never fetched, and a
  candidate whose body carries a *different* hash is never matched even
  when it cites the same signals.
- `.github/workflows/watchdog.yml:3216-3221`: more than one exact match is
  not a merge and not a pick — it is `outcome=data-integrity`, reported and
  left for a human, with no write. Whatever overlap rule ships has to say
  what the *overlapping* analogue of that case is.
- `.github/workflows/watchdog.yml:3619-3635`: the filed body carries
  exactly one machine-readable marker,
  `<!-- wing-commander-watchdog: fingerprint=<hash> -->`, plus a
  human-readable `_Fingerprint facts:_` line. The cited signal ids appear
  only inside that opaque hash — nothing in the body lets a later run ask
  "does this issue already cite `1bcf7944887991cd`?"
- `.github/workflows/watchdog.yml:3652-3660`: a recurrence is recorded as a
  comment listing the new occurrence's evidence. The comment is not read
  back by any later lookup, so evidence that accumulates there does not
  widen what the issue can match.
- `.github/workflows/watchdog.yml:1898-1960` ("Stamp signal ids") projects
  each signal to `{kind, ident}` before hashing, dropping occurrence-only
  facts. This is why ids recur across runs at all, and why "cites the same
  id" is a meaningful statement about two different runs.
- `.github/workflows/watchdog.yml:1949-1958` is the `turn-budget` /
  `turn-budget-trend` shared-`kind` comment quoted above — the
  already-shipped, already-reasoned precedent that a fingerprint must not
  depend on which citation subset the agent chose.
- `.github/workflows/watchdog.yml:2274-2311`: the class vocabulary is the
  `🐕 · ` label set compiled into the structured-output enum, plus a
  `__new__` escape hatch a deterministic step resolves. The agent selects
  from that enum per finding; nothing constrains two findings of one run to
  agree, and nothing relates one class to another.
- `.github/workflows/watchdog.yml:3595-3601`: the "Ensure pipeline-defect
  issue" step already refuses to act on `data-integrity` and `unknown`.
  Any new "cannot decide" outcome has an existing shape to follow.
- `specs/015-pipeline-watchdog/spec.md:145-149,173`: FR-012 (check open and
  closed), FR-013 (comment, never duplicate), FR-014 (reopen closed),
  FR-015 (create only when the lookup completed and matched nothing),
  FR-028 (`unknown` is not `none`). FR-016 requires a fingerprint that is
  deterministic and stable "such that the same defect recurring across many
  runs maps to one issue … while genuinely distinct defects map to distinct
  fingerprints." The current implementation satisfies determinism and fails
  the mapping clause whenever the citation subset moves.
- Constitution Principle IX names "resolving a dedup outcome" as judgment
  that belongs in deterministic code, and Principle VIII requires every
  failure branch a gate ships to be exercised by a checked-in fixture.
- `.github/actions/wing-commander-durable-failure-issue/action.yml:164` is
  a *different* dedup lookup with no `--limit` (so `gh`'s default of 30).
  That is issue #705 and is out of scope here; it is named only so the two
  are not confused.

## Clarifications

### Session 2026-09-29 — answered on lifecycle issue #792 by @charlesguse

All three open questions are resolved. The answers are folded into the
requirements, scenarios and success criteria below.

- **Q1 — which dedup mechanism (FR-001)?** Overlap matching **within a
  class**: an *open* issue of the same class citing any signal id in common
  is a match. Cross-class grouping is **not** adopted. The class fan-out of
  User Story 2 is answered instead by a filing condition: the watchdog does
  not file for a red gate suite belonging to an implement cycle that feeds a
  further cycle — that red suite is the converge loop working as designed.
  It files only when (i) the stage stalled on the red suite, or (ii)
  finalize was reached with the suite still red. That condition alone
  accounts for #708–#713.
- **Q2 — multi-match resolution (FR-007)?** Comment on the
  **lowest-numbered open match**, and name the other matching issues by
  number in that comment so a maintainer can merge them by hand. Multi-match
  is **not** `data-integrity`, and the watchdog closes nothing — spec 024's
  FR-014 remediation surface is unchanged.
- **Q3 — retroactive consolidation (FR-023)?** Go-forward only. The owner
  triages #708–#713, #729, #732 and #765 by hand against their specs'
  current state; this feature files no follow-up issue for them.

Two readings the answer pins rather than states outright, recorded here so
the plan stage does not re-open them:

- **"Gate-suite finding" is not one class.** #708–#713 carry six different
  classes, and the answer states the filing condition alone would have
  suppressed all six. So the condition is scoped by *evidence* — a finding
  whose cited signals come from the inspected run's gate suite failure —
  not by the `gate-suite-failure` class label alone (FR-009).
- **Overlap matching is scoped to open issues.** The answer says "open
  issue" in both Q1 and Q2. Partial overlap therefore does not reopen a
  closed issue; the existing exact-fingerprint match continues to reopen one
  (FR-006).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - One recurring failure accumulates on one issue even when the citation set moves (Priority: P1)

A maintainer opening the `pipeline-defect` label wants each open issue to
be one problem. Today they find #729, #732 and #765 — three issues, three
runs, one signal in common, filed because the agent cited that signal
alongside a different supporting cast each time. Triaging them costs three
reads to reach one conclusion, and closing two of them as duplicates by
hand is work the dedup step exists to prevent.

**Why this priority**: This is the half of the issue with live evidence on
the board right now, it is the half that keeps producing new duplicates on
every run, and it is the half that directly contradicts the mapping clause
of the governing fingerprint requirement. It stands alone: fixing only this
and leaving class fan-out untouched still collapses three issues into one.

**Independent Test**: Replay the three runs behind #729, #732 and #765 in
order against a clean tracker. The first files one issue; the second and
third comment on it. No second issue is created.

**Acceptance Scenarios**:

1. **Given** an open `pipeline-defect` issue whose accumulated occurrences
   cite `{A,B}`, **When** a later run produces a finding of the same class
   citing `{A,C,D}`, **Then** the new occurrence is attached to that issue
   and no second issue is created.
2. **Given** that same issue, **When** a later run produces a finding of
   the same class citing `{E,F}` — no id in common — **Then** a new issue
   **is** created, because nothing links the two.
3. **Given** an issue that has accumulated occurrences citing `{A,B}` and
   later `{A,C,D}`, **When** a third run cites `{D}` alone, **Then** it
   matches, because the ids the issue carries are the union of everything
   recorded on it, not only the first occurrence's set.
4. **Given** a finding that matches an issue on a strict subset of its
   cited ids, **When** the occurrence is recorded, **Then** a maintainer
   reading the issue can see which ids caused the match and which ids are
   new, without opening the run.
5. **Given** the dedup lookup errors, **When** the finding is triaged,
   **Then** the outcome is `unknown` and nothing is filed — unchanged by
   this feature (FR-028 of spec 015).

---

### User Story 2 - A converging implement cycle's red gate suite never reaches the board (Priority: P1)

A maintainer watching a red gate suite wants the board to say nothing at
all while the implement stage is still converging on it. Today run
36484099706 handed them six issues filed in the same minute —
single-home-violation, container-shell-unpinned,
canonical-pointer-misresolved, harness-step-name-drift,
gate-self-test-failure, shellcheck-coverage-gap — six descriptions of one
red run that the *next* implement cycle was already going to fix. Each of
the six then needs its own triage, its own close, and its own board-loop
cycle.

**Why this priority**: It is the larger multiplier of the two (six issues
from one run versus three from three runs) and it consumes the autonomous
loop's own capacity, which is bounded by a shared usage window. It ranks
level with User Story 1 rather than above it because it has no live
recurrence pressure — the six issues are already filed.

**Independent Test**: Replay run 36484099706's finding set against a clean
tracker, with that run's implement cycle recorded as feeding a further
cycle. No `pipeline-defect` issue is created for its gate-suite findings;
each is reported to the lifecycle issue under a named write-suppression
outcome.

**Acceptance Scenarios**:

1. **Given** an implement cycle whose red gate suite feeds a further cycle,
   **When** its gate-suite findings are triaged, **Then** no
   `pipeline-defect` issue is filed for any of them, whatever classes the
   diagnose agent assigned them.
2. **Given** that same suppression, **When** a maintainer reads the
   lifecycle issue, **Then** every suppressed finding is named there with
   the reason, so the suppression is visible rather than silent.
3. **Given** an implement stage that **stalled** on a red gate suite,
   **When** its gate-suite findings are triaged, **Then** they are filed as
   normal — the suppression covers only a cycle that is still converging.
4. **Given** finalize reached with the gate suite still red, **When** its
   gate-suite findings are triaged, **Then** they are filed as normal.
5. **Given** a run whose findings include both gate-suite findings from a
   converging cycle and findings citing evidence from elsewhere, **When**
   the run is triaged, **Then** only the gate-suite findings are suppressed
   and the others are triaged unchanged.

---

### User Story 3 - Deliberate separations survive the change (Priority: P1)

A maintainer relies on `tool-denial` issues being per `{stage, tool}`: a
reopen on one of them means *that stage* regressed. A dedup rule that
merges on any shared evidence, applied carelessly, could chain those three
correct issues (#761, #764, #780) into one and destroy the attribution
#266 was filed to create.

**Why this priority**: It is a correctness bound on Stories 1 and 2 rather
than a feature of its own, and a regression here is silent — the merged
issue looks tidier than the three it replaced. It must be specified and
fixture-checked before either story ships, not after.

**Independent Test**: Replay the three runs behind #761, #764 and #780. All
three issues are filed, separately, exactly as today.

**Acceptance Scenarios**:

1. **Given** findings from three different `{stage, tool}` denial pairs,
   **When** each is triaged, **Then** three separate issues exist, as they
   do today.
2. **Given** an open issue citing `{A,B}` and another citing `{B,C}` in the
   same class, **When** a finding citing `{A,C}` arrives, **Then** exactly
   one of them — the lowest-numbered — receives the occurrence, its comment
   names the other by number, and neither issue is closed or merged: a
   chain of pairwise-overlapping issues never collapses on its own.
3. **Given** the `narrative-drift` class, which is issue-exempt by design,
   **When** it is triaged, **Then** it still files nothing and still
   reports to the lifecycle issue — unchanged.
4. **Given** a class vocabulary that has just self-healed through
   `__new__`, **When** a finding of the freshly registered class is
   triaged, **Then** matching behaves exactly as for a pre-existing class.

---

### User Story 4 - The self-test proves it, and a mutation breaks it (Priority: P2)

The next contributor to touch the fingerprint needs a fixture that fails
when they get it wrong. Nothing in the watchdog's current self-test drives
two runs with overlapping-but-unequal citation sets, which is why this
defect reached the board by a maintainer noticing three open issues rather
than by a check.

**Why this priority**: Without it the fix is a claim. Principle VIII is
explicit that a manual demonstration during development is evidence for
that reviewer, not coverage for the next one. It sits at P2 only because it
has to follow the rule it tests.

**Independent Test**: Revert the matching rule to exact-set equality and
run the PR-time gate suite. It fails, and names the overlap fixture.

**Acceptance Scenarios**:

1. **Given** a checked-in fixture where two runs cite overlapping but
   unequal signal sets, **When** the self-test runs, **Then** it asserts
   exactly one issue is filed and one comment is added.
2. **Given** a checked-in fixture where a converging implement cycle's red
   gate suite yields findings of several classes, **When** the self-test
   runs, **Then** it asserts no issue is filed and every finding is
   reported; and a companion fixture for the stalled / finalize-red arm
   asserts that those findings **are** filed.
3. **Given** a checked-in fixture for the deliberate `{stage, tool}`
   separation, **When** the self-test runs, **Then** it asserts three
   distinct issues.
4. **Given** the matching rule mutated back to exact-set equality,
   **When** the suite runs, **Then** it fails — the fixture can fail its
   own subject.
5. **Given** the fixtures, **When** they run locally through
   `run-local-gates.py`, **Then** they run the same subject with the same
   arguments as in CI.

---

### User Story 5 - The governing requirement says what the code does (Priority: P3)

A reviewer citing FR-012–FR-016 needs those requirements to describe the
shipped rule. Today FR-016's "the same defect recurring across many runs
maps to one issue" reads as satisfied while the implementation it governs
demonstrably fails it, and FR-013's "MUST NOT open a duplicate" is written
against a notion of "matches" that this feature redefines.

**Why this priority**: No run behaves differently because of it, but a
requirement that overstates its implementation is the thing that let this
gap sit unnoticed through spec 024's own retrospective on the same
fingerprint.

**Independent Test**: Read FR-012–FR-016 with no other context and predict
what happens when a finding cites a superset of an open issue's ids. The
prediction matches the shipped behaviour.

**Acceptance Scenarios**:

1. **Given** the amended requirements, **When** a reviewer reads the
   matching rule, **Then** it states what counts as a match for unequal
   citation sets and what happens when several candidates match.
2. **Given** the amended requirements, **When** a reviewer reads them
   alongside #266's per-`{stage, tool}` separation, **Then** the separation
   is recorded as deliberate rather than as an exception to be tidied away.

---

### Edge Cases

- **Chained overlap.** Issue X carries `{A,B}`, issue Y carries `{B,C}`,
  and a new finding cites `{A,C}`. Two open issues overlap it, by different
  ids. Under FR-007 the lowest-numbered of them takes the occurrence and
  its comment names the other; neither is closed, so the merge stays a
  maintainer's decision. This is deliberately *not* routed to
  `data-integrity` — under an overlap rule multi-match is routine, and
  suppressing every routine case would keep real findings off the board.
- **Transitive growth.** Each accepted occurrence widens the set an issue
  can match on, so a long-lived issue drifts toward matching everything. The
  rule needs a bound (FR-008) or an issue eventually swallows the board.
- **Closed-issue overlap.** A finding partially overlaps a *closed* issue.
  Reopening on a partial match is a stronger action than commenting on an
  open one, so FR-006 does not reopen on it: overlap matching considers
  open issues only, and a closed issue still reopens on the exact-match
  path it does today.
- **Cross-class overlap where the classes are genuinely different
  problems.** Two collectors can legitimately emit one shared signal (a
  single annotation) for two unrelated defects. This is why matching stays
  inside the class label and cross-class grouping was rejected: grouping on
  that shared id would merge two real problems into one issue and lose one
  of them.
- **The converging-cycle state cannot be determined.** The collector cannot
  tell whether the implement cycle that produced a red gate suite feeds a
  further cycle, stalled, or reached finalize. The suppression in FR-009
  must not be applied on a guess; the finding is triaged as normal, so an
  undeterminable state errs toward filing rather than toward silence.
- **Issues filed before this change.** Their bodies carry only the opaque
  `fingerprint=` marker and no readable signal ids, so a partial-overlap
  lookup cannot see into them. They stay matchable through the existing
  exact-fingerprint path, and their bodies are never edited to add ids
  (FR-015); overlap matching reaches only issues filed after this change.
- **The lookup's bound.** The candidate set is `--limit 200` within one
  class label. Overlap matching stays inside that filter, so the fetch does
  not widen — but it now has to *read* each candidate's recorded ids rather
  than grep for one hash, and a truncated candidate list must behave as
  `unknown`, never as "nothing matched" (FR-016).
- **A finding citing exactly one id that is also the only id of an
  unrelated open issue.** Overlap and equality coincide; behaviour must be
  identical to today.
- **`data-integrity` and `unknown` today.** Neither writes. Any new
  *undecidable* outcome must join them rather than invent a further
  write-suppression shape. The FR-009 suppression is a different animal —
  it is a decided "this is not a defect", not a failure to decide — so it
  is named distinctly in the report and must not be read back as
  `data-integrity` (FR-011, FR-019).

## Requirements *(mandatory)*

### Functional Requirements

#### Matching findings whose citation sets differ

- **FR-001**: The watchdog MUST attach a new occurrence to an existing
  `pipeline-defect` issue when the finding and that issue describe the same
  underlying failure, where "the same underlying failure" is determined by
  the collector signal ids they have in common rather than by equality of
  the cited set. The adopted mechanism is **overlap matching within a
  class**: an *open* `pipeline-defect` issue carrying the finding's class
  label and citing **any** signal id the finding cites is a match. Equality
  of the cited sets MUST NOT be required. Matching MUST NOT cross the class
  label.
- **FR-002**: The identity an issue is matched on MUST be derived from
  deterministic collector output and MUST NOT depend on any text the
  diagnose agent authored, on the order of the cited ids, or on which
  subset of a run's ids that agent chose to cite (Constitution Principle
  IX; FR-006/FR-007 of spec 024).
- **FR-003**: An issue MUST carry, in a form a later run can read back
  without inspecting the original run, the full set of collector signal ids
  its accumulated occurrences have cited — not only those of the first
  occurrence. The ids are recorded at filing and in recurrence comments;
  the watchdog MUST NOT edit an issue body.
- **FR-004**: A finding that matches nothing MUST still file a new issue.
  The change MUST NOT convert "no match" into a suppression, and — apart
  from the single stated filing condition of FR-009 — MUST NOT reduce the
  set of real failures that reach the board.
- **FR-005**: A dedup lookup that could not complete MUST continue to
  produce `unknown`, MUST suppress the write, and MUST NOT share a code
  path with "matched nothing" (FR-028 of spec 015, unchanged).
- **FR-006**: Overlap matching applies to **open** issues only. A partial
  overlap against a **closed** issue MUST NOT reopen it; a closed issue
  MUST continue to reopen on the exact-identity match it does today
  (FR-014 of spec 015, unchanged). A finding whose only overlap is with a
  closed issue files a new issue.
- **FR-007**: When more than one open issue matches the finding, the
  watchdog MUST attach the occurrence to the **lowest-numbered** open match
  and MUST NOT write to any other issue for that finding. The occurrence
  record MUST name the other matching issues by number so a maintainer can
  merge them by hand. Multi-match MUST NOT produce `data-integrity`, and
  the watchdog MUST NOT close, merge or relabel any of the matches — spec
  024's FR-014 remediation surface is unchanged.
- **FR-008**: The accumulation in FR-003 MUST be bounded so that an issue's
  matchable identity cannot grow without limit across occurrences, and the
  bound MUST be stated in the shipped code where a reader of the matching
  step will find it. The plan fixes the number.

#### Gate-suite findings from a converging implement cycle

- **FR-009**: The watchdog MUST NOT file a `pipeline-defect` issue for a
  gate-suite finding — a finding whose cited signals come from the
  inspected run's gate suite failure, whatever class the diagnose agent
  assigned it — when that red suite belongs to an implement cycle that
  feeds a further cycle. It MUST file such a finding only when (i) the
  stage stalled on the red suite, or (ii) finalize was reached with the
  suite still red. A converging cycle's red suite is the converge loop
  working as designed, not a pipeline defect.
- **FR-010**: The FR-009 condition MUST be decided from deterministic
  collector output about the cycle's own state, and MUST NOT depend on the
  diagnose agent's class assignment or prose (Constitution Principle IX).
  When that state cannot be determined, the finding MUST be triaged as
  normal — the suppression MUST NOT be applied on a guess. The source is
  the inspected implement run's own recorded cycle outcome (whether it
  dispatched a further cycle, stalled, or handed off to finalize — the
  `converged`, `handoff` and `reason` facts implement.yml's cycle-outcome
  step already emits), together with the spec-meta stage and `stalled`
  label the watchdog already reads.
- **FR-011**: A finding suppressed under FR-009 MUST still be reported to
  the lifecycle issue, named, with the reason for the suppression, so the
  outcome is visible rather than silent. It MUST carry its own named
  outcome and MUST NOT be reported as `data-integrity` or `unknown`, which
  mean the watchdog could not decide.
- **FR-012**: The FR-009 suppression MUST be scoped to gate-suite findings.
  Findings of the same run citing evidence from elsewhere MUST be triaged
  unchanged, and no cross-class grouping of findings is adopted: two
  findings of different classes MUST continue to reach separate issues.

#### Separations that must survive

- **FR-013**: The per-`{stage, tool}` separation of `tool-denial` signal
  ids (#266) MUST be preserved: denials from different stages, or different
  tools within a stage, MUST continue to accumulate on separate issues, and
  a reopen MUST continue to mean a regression in that specific stage.
- **FR-014**: The `narrative-drift` issue-exempt path MUST be unchanged —
  it reports to the lifecycle issue and files nothing.
- **FR-015**: `pipeline-defect` issues filed before this change MUST remain
  matchable through the existing exact-fingerprint path. Overlap matching
  applies to issues carrying the new readable id record. No existing issue
  body is edited.
- **FR-016**: If the candidate set the lookup fetches is truncated, or the
  matching rule requires candidates the lookup did not fetch, the outcome
  MUST be `unknown` (write suppressed, reported) and MUST NOT be "matched
  nothing".

#### Legibility of the decision

- **FR-017**: A maintainer reading a filed issue or its recurrence comment
  MUST be able to determine which signal ids caused the match and which ids
  the new occurrence added, without opening the inspected run.
- **FR-018**: The lifecycle-issue report every finding produces MUST
  continue to name the action taken and MUST distinguish a partial-overlap
  attachment from an exact recurrence, and a multi-match attachment from a
  single-match one, so the report does not claim a stronger identity than
  the rule established.
- **FR-019**: Every new *undecidable* outcome MUST reuse the existing
  write-suppression shape (`data-integrity` / `unknown`: report, do not
  write) rather than introduce a further variant. The FR-009 suppression is
  a decided outcome, not an undecidable one, and is the single new
  non-writing outcome this feature adds.

#### Coverage

- **FR-020**: The watchdog self-test MUST carry a checked-in fixture in
  which two runs cite overlapping but unequal signal sets, asserting that
  exactly one issue is filed and the second occurrence is recorded on it.
- **FR-021**: The self-test MUST carry checked-in fixtures for both arms of
  the FR-009 condition — a converging implement cycle's red gate suite,
  asserting nothing is filed and every finding is reported; and a stalled
  or finalize-red suite, asserting the findings **are** filed — and for the
  preserved `{stage, tool}` separation (three denial pairs, three issues).
  It MUST also carry a fixture for the FR-007 multi-match case, asserting
  one write, to the lowest-numbered open match, naming the others.
- **FR-022**: Each fixture MUST be accompanied by a mutation that reverts
  the behaviour it covers and MUST be shown to fail under that mutation, so
  the fixture can fail its own subject (Constitution Principle VIII). The
  fixtures MUST run through the PR-time gate suite and MUST run the same
  subject with the same arguments locally as in CI.

#### Governing documents

- **FR-023**: The dedup requirements of spec 015 (FR-012–FR-016) as amended
  by spec 024 MUST be updated to state the matching rule this feature
  adopts, including what counts as a match for unequal citation sets, the
  open-issue scoping of overlap, the lowest-numbered multi-match
  resolution, and the FR-009 filing condition, so a reviewer citing them is
  citing the shipped behaviour.
- **FR-024**: The per-`{stage, tool}` denial separation MUST be recorded in
  the amended requirements as a deliberate design choice with its
  originating issue (#266), not as an inconsistency.
- **FR-025**: This feature changes go-forward behaviour only. It MUST NOT
  close, relabel or consolidate the already-open duplicates it was filed
  over — #729/#732/#765 and #708–#713 — which the owner triages by hand,
  and it MUST NOT file a follow-up issue for them.

### Key Entities

- **Signal**: One deterministic observation a collector made about the
  inspected run, carrying a source, a fact bag, and a content-derived id.
- **Signal id**: The hash of a signal's `{kind, ident}` projection. Stable
  across runs by construction; the only agent-independent evidence handle
  the system has.
- **Finding**: One problem the diagnose agent reports for a run, carrying a
  class from the label-backed vocabulary, a description, and a list of
  cited signal ids. One run yields an array of these.
- **Finding class**: A value from the `🐕 · ` label vocabulary (plus the
  `__new__` escape hatch). It is half the dedup key and the dedup lookup's
  own filter, and stays so — overlap matching never crosses it.
- **Gate-suite finding**: A finding whose cited signals come from the
  inspected run's gate suite failure. Not a single class: run 36484099706
  produced six of them under six different class labels.
- **Converging implement cycle**: An implement cycle whose red gate suite
  feeds a further cycle. Its red suite is the converge loop working, and is
  the subject of the FR-009 filing condition.
- **Dedup identity**: Whatever a `pipeline-defect` issue is matched on.
  Today a single opaque hash in the issue body; this feature replaces or
  supplements it with something that can express partial overlap.
- **Dedup outcome**: One of match-open, match-closed, none, data-integrity,
  unknown, plus the FR-009 suppression this feature adds. Selects the single
  remediation action the watchdog takes.
- **Occurrence**: One recording of a finding against an issue — the filing
  itself, or a recurrence comment. Occurrences are what accumulate the ids
  in FR-003.
- **pipeline-defect issue**: The durable artifact. One per underlying
  failure is the contract this feature exists to restore.

## Success Criteria *(mandatory)*

- **SC-001**: Replaying, in order, the three runs behind #729, #732 and
  #765 against a clean tracker produces exactly one `pipeline-defect`
  issue and two recurrence records on it.
- **SC-002**: Replaying run 36484099706's finding set against a clean
  tracker, with its implement cycle recorded as feeding a further cycle,
  produces zero `pipeline-defect` issues and six lifecycle-issue reports
  naming the suppression. Replaying the same finding set with the cycle
  recorded as stalled, or as finalize-reached-still-red, files them.
- **SC-003**: Replaying the three runs behind #761, #764 and #780 produces
  three separate issues, one per `{stage, tool}` pair — unchanged from
  today.
- **SC-004**: Across any 20 consecutive watchdog runs after this ships, no
  two *open* `pipeline-defect` issues **of the same class** cite a common
  signal id, except where a stated deliberate separation (FR-013) accounts
  for it. Issues of different classes may share an id by design — matching
  never crosses the class label.
- **SC-005**: Reverting the matching rule to exact-set equality makes the
  PR-time gate suite fail and names the overlap fixture; likewise reverting
  the FR-009 filing condition names the converging-cycle fixture, and
  likewise for the `{stage, tool}` separation fixture.
- **SC-006**: A maintainer can determine, from a filed issue and its
  comments alone, which signal ids it covers and which occurrence
  contributed each — in 100% of issues filed after this ships.
- **SC-007**: No finding that would have been filed under the current rule
  is silently dropped: for every replayed scenario, each input finding is
  either filed, attached to an issue, or reported under a named
  write-suppression outcome — including every finding suppressed under
  FR-009, which is named in the lifecycle-issue report with its reason.
- **SC-008**: Reading the amended FR-012–FR-016 alone, a reviewer correctly
  predicts the outcome for a finding citing a superset, a subset, a
  disjoint set, and a chained-overlap set.

## Assumptions

- Collector signal ids are stable across runs for the same underlying
  problem. This is the premise the whole feature rests on; it is supported
  by the per-source projection in "Stamp signal ids" and by the observed
  recurrence of `1bcf7944887991cd` across three separate runs.
- The diagnose agent's choice of class and of citation subset will remain
  variable. The fix belongs in the deterministic matching code, not in a
  stronger prompt instruction (Principle IX).
- The `🐕 · ` label vocabulary stays the class registry, and `__new__` stays
  the escape hatch; this feature does not re-open how classes are named.
- The watchdog stays a pure reporter — it files, comments on, and reopens
  issues, and nothing else (FR-014 of spec 024). The adopted answers add no
  remediation path: multi-match links the other issues for a human rather
  than closing them.
- The inspected run carries enough deterministic evidence to tell a
  converging implement cycle from a stalled one and from a finalize reached
  with the suite still red. FR-010 is written so that the feature stays
  correct if it does not — the suppression is simply not applied.
- The three duplicate-set examples in the issue (`gate-suite-failure`
  #729/#732/#765, the six-class run 36484099706, and the three correct
  `tool-denial` issues) are the working corpus. They are treated as the
  acceptance corpus, not as an exhaustive one.
- Issue #705 (a separate dedup lookup with no explicit limit, in
  `wing-commander-durable-failure-issue`) and #748/#749 (evidence gate /
  fingerprint projection comments) are related but separate; this feature
  does not carry them.
- Once an underlying failure's issue exists, adding an occurrence to it is
  strictly preferable to filing a second issue — the cost of a slightly
  over-broad issue is lower than the cost of a fan-out, up to the
  false-merge boundary FR-001's class scoping and FR-013 draw.

## Dependencies

- `specs/015-pipeline-watchdog/spec.md` (FR-012–FR-016, FR-028) and
  `specs/024-*/spec.md` (FR-006, FR-007, FR-018–FR-020) are the governing
  requirements this feature amends; both are live contracts a reviewer
  cites.
- `.github/workflows/watchdog.yml`'s `collect` → `diagnose` → `triage` →
  `act` chain, and the triage-decision artifact handoff between `triage`
  and `act`.
- The watchdog self-test surface: `wing-commander-8b-watchdog-self.yml`,
  `wing-commander-watchdog-test.yml`, and the existing
  `verify-act-dedup-guard.py` / `verify-watchdog-*` harnesses, which are
  the nearest existing homes for the new fixtures (CLAUDE.md: extend the
  nearest existing gate).
- Constitution Principles VIII (a green check means what it says) and IX
  (deterministic judgment gates durable actions).

## Out of Scope

- Issue #705 — the unbounded candidate list in a different dedup lookup.
- Issues #748/#749 — evidence-gate and fingerprint-projection comments.
- Changing the finding-class vocabulary, the `__new__` resolution path, or
  the diagnose agent's prompt.
- Adding any remediation action beyond file / comment / reopen.
- Cross-class grouping of findings, and any rule that matches across the
  `🐕 · ` class label — considered and rejected in favour of the FR-009
  filing condition (see Clarifications).
- Closing, relabelling or consolidating any existing `pipeline-defect`
  issue, including the duplicates this feature was filed over
  (FR-025) — the owner triages those by hand.
