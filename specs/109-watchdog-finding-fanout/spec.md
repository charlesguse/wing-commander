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
minute.

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

### Observed facts (verified against main at 73be417)

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

Three questions are open. Intake did not resolve them; they are posted to
lifecycle issue #792 for the owner, and each is carried as a
`[NEEDS CLARIFICATION]` marker at the requirement it blocks (FR-001,
FR-007, FR-023). Everything else in this spec is written so that it holds
under any of the offered answers.

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

### User Story 2 - One failing run does not become one issue per class (Priority: P1)

A maintainer watching a red gate suite wants the board to say "the gate
suite failed on run 36484099706", not to hand them six issues filed in the
same minute — single-home-violation, container-shell-unpinned,
canonical-pointer-misresolved, harness-step-name-drift,
gate-self-test-failure, shellcheck-coverage-gap — that are six
descriptions of one red run. Each of the six then needs its own triage, its
own close, and its own board-loop cycle.

**Why this priority**: It is the larger multiplier of the two (six issues
from one run versus three from three runs) and it consumes the autonomous
loop's own capacity, which is bounded by a shared usage window. It ranks
level with User Story 1 rather than above it because it has no live
recurrence pressure — the six issues are already filed — and because any
grouping rule has a higher false-merge risk than a same-class overlap rule.

**Independent Test**: Replay run 36484099706's finding set against a clean
tracker and count the issues created. The count is lower than six, and
every issue created covers a set of cited signal ids disjoint from every
other issue created by the same replay.

**Acceptance Scenarios**:

1. **Given** one inspected run whose findings of several classes cite
   overlapping signal ids, **When** the run is triaged, **Then** those
   findings do not each produce a separate `pipeline-defect` issue.
2. **Given** an issue that covers findings of more than one class, **When**
   a maintainer reads it, **Then** it names every class it covers and
   carries the class label for each, so the `🐕 · ` label set remains a
   complete index of what is open.
3. **Given** one inspected run whose findings describe two genuinely
   unrelated problems with no shared signal id, **When** the run is
   triaged, **Then** two issues result — grouping never merges findings
   that share no evidence.
4. **Given** a grouped issue that is open, **When** a later run reproduces
   only one of the classes it covers, **Then** that occurrence is attached
   to the existing issue rather than filed as new.

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
2. **Given** a finding citing `{A,B}` on one issue and a finding citing
   `{B,C}` on another, **When** a third finding citing `{C,D}` arrives,
   **Then** the rule's behaviour for chained overlap is defined and
   bounded, and does not silently collapse a chain of pairwise-overlapping
   findings into one issue covering unrelated defects.
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
2. **Given** a checked-in fixture where one run yields findings of several
   classes over overlapping signals, **When** the self-test runs, **Then**
   it asserts the grouping outcome chosen under FR-001.
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
  ids. This is the overlapping analogue of today's `data-integrity`
  outcome and is the subject of FR-007.
- **Transitive growth.** Each accepted occurrence widens the set an issue
  can match on, so a long-lived issue drifts toward matching everything. The
  rule needs a bound (FR-008) or an issue eventually swallows the board.
- **Closed-issue overlap.** A finding partially overlaps a *closed* issue.
  Reopening on a partial match is a stronger action than commenting on an
  open one — FR-006 must say whether partial overlap reopens.
- **Cross-class overlap where the classes are genuinely different
  problems.** Two collectors can legitimately emit one shared signal (a
  single annotation) for two unrelated defects. Grouping on that shared id
  merges two real problems into one issue and loses one of them.
- **A grouped issue whose classes diverge over time.** The run that filed it
  covered classes P and Q; later runs only ever reproduce P. The issue's
  class labels then overstate what is live.
- **Issues filed before this change.** Their bodies carry only the opaque
  `fingerprint=` marker and no readable signal ids, so a partial-overlap
  lookup cannot see into them. They must not be orphaned into a permanent
  second population that new findings can never match (FR-015).
- **The lookup's bound.** The candidate set is `--limit 200` within one
  class label. A rule that must consider candidates across classes widens
  what has to be fetched, and a truncated candidate list must behave as
  `unknown`, never as "nothing matched" (FR-016).
- **A finding citing exactly one id that is also the only id of an
  unrelated open issue.** Overlap and equality coincide; behaviour must be
  identical to today.
- **`data-integrity` and `unknown` today.** Neither writes. Any new
  undecidable outcome must join them rather than invent a fourth
  write-suppression shape.

## Requirements *(mandatory)*

### Functional Requirements

#### Matching findings whose citation sets differ

- **FR-001**: The watchdog MUST attach a new occurrence to an existing
  `pipeline-defect` issue when the finding and that issue describe the same
  underlying failure, where "the same underlying failure" is determined by
  the collector signal ids they have in common rather than by equality of
  the cited set. [NEEDS CLARIFICATION: which of issue #792's three
  mechanisms is adopted — (a) overlap matching, where an open issue of the
  same class citing any id in common is a match; (b) signal-first dedup,
  where each cited id is recorded as its own marker, ids already carried by
  an open issue are dropped before filing, and a new issue is filed only if
  uncited ids remain; (c) per-run grouping, where all findings from one
  run's failure become a single issue listing the classes — or a
  combination, e.g. (a) within a class plus (c) across classes]
- **FR-002**: The identity an issue is matched on MUST be derived from
  deterministic collector output and MUST NOT depend on any text the
  diagnose agent authored, on the order of the cited ids, or on which
  subset of a run's ids that agent chose to cite (Constitution Principle
  IX; FR-006/FR-007 of spec 024).
- **FR-003**: An issue MUST carry, in a form a later run can read back
  without inspecting the original run, the full set of collector signal ids
  its accumulated occurrences have cited — not only those of the first
  occurrence.
- **FR-004**: A finding that matches nothing MUST still file a new issue.
  The change MUST NOT convert "no match" into a suppression, and MUST NOT
  reduce the set of real failures that reach the board.
- **FR-005**: A dedup lookup that could not complete MUST continue to
  produce `unknown`, MUST suppress the write, and MUST NOT share a code
  path with "matched nothing" (FR-028 of spec 015, unchanged).
- **FR-006**: The rule MUST state whether a partial match against a
  **closed** issue reopens it (FR-014 of spec 015) or files a new issue,
  and MUST apply that choice deterministically.
- **FR-007**: When more than one existing issue matches the finding, the
  watchdog MUST resolve the ambiguity by a stated deterministic rule and
  MUST NOT write to more than one issue for a single finding.
  [NEEDS CLARIFICATION: which resolution — attach to the single
  lowest-numbered open match; attach to the most recently updated open
  match; suppress and report as the existing `data-integrity` outcome does;
  or file a new issue that supersedes and cross-references the matches]
- **FR-008**: The accumulation in FR-003 MUST be bounded so that an issue's
  matchable identity cannot grow without limit across occurrences, and the
  bound MUST be stated in the shipped code where a reader of the matching
  step will find it.

#### Findings split across classes

- **FR-009**: Findings produced by one inspected run MUST NOT each produce
  their own `pipeline-defect` issue solely because the diagnose agent
  assigned them different classes while they cite overlapping evidence.
- **FR-010**: When one issue covers findings of more than one class, it
  MUST name every class it covers in its body and MUST carry the `🐕 · `
  label for each, so the class-label set remains a complete index of what
  is open (the class label is also the dedup lookup's own filter).
- **FR-011**: Grouping MUST NOT merge findings that share no collector
  signal id.
- **FR-012**: A later run reproducing a subset of a grouped issue's classes
  MUST attach to that issue rather than file a new one.

#### Separations that must survive

- **FR-013**: The per-`{stage, tool}` separation of `tool-denial` signal
  ids (#266) MUST be preserved: denials from different stages, or different
  tools within a stage, MUST continue to accumulate on separate issues, and
  a reopen MUST continue to mean a regression in that specific stage.
- **FR-014**: The `narrative-drift` issue-exempt path MUST be unchanged —
  it reports to the lifecycle issue and files nothing.
- **FR-015**: `pipeline-defect` issues filed before this change MUST remain
  matchable by findings produced after it, or the feature MUST state and
  implement a migration that makes them so. A permanently unmatchable
  legacy population is not an acceptable outcome.
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
  attachment from an exact recurrence, so the report does not claim a
  stronger identity than the rule established.
- **FR-019**: Every new undecidable outcome MUST reuse the existing
  write-suppression shape (`data-integrity` / `unknown`: report, do not
  write) rather than introduce a fourth variant.

#### Coverage

- **FR-020**: The watchdog self-test MUST carry a checked-in fixture in
  which two runs cite overlapping but unequal signal sets, asserting that
  exactly one issue is filed and the second occurrence is recorded on it.
- **FR-021**: The self-test MUST carry checked-in fixtures for the class
  fan-out case (one run, several classes, overlapping signals) and for the
  preserved `{stage, tool}` separation (three denial pairs, three issues).
- **FR-022**: Each fixture MUST be accompanied by a mutation that reverts
  the behaviour it covers and MUST be shown to fail under that mutation, so
  the fixture can fail its own subject (Constitution Principle VIII). The
  fixtures MUST run through the PR-time gate suite and MUST run the same
  subject with the same arguments locally as in CI.

#### Governing documents

- **FR-023**: The dedup requirements of spec 015 (FR-012–FR-016) as amended
  by spec 024 MUST be updated to state the matching rule this feature
  adopts, including what counts as a match for unequal citation sets and
  the multi-match resolution, so a reviewer citing them is citing the
  shipped behaviour. [NEEDS CLARIFICATION: does this feature also
  retroactively consolidate the already-open duplicates it was filed over —
  #729/#732/#765 and #708–#713 — as part of its own work, or does it change
  go-forward behaviour only and leave the existing duplicates to ordinary
  board triage?]
- **FR-024**: The per-`{stage, tool}` denial separation MUST be recorded in
  the amended requirements as a deliberate design choice with its
  originating issue (#266), not as an inconsistency.

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
  `__new__` escape hatch). Today it is half the dedup key and the dedup
  lookup's own filter.
- **Dedup identity**: Whatever a `pipeline-defect` issue is matched on.
  Today a single opaque hash in the issue body; this feature replaces or
  supplements it with something that can express partial overlap.
- **Dedup outcome**: One of match-open, match-closed, none, data-integrity,
  unknown. Selects the single remediation action the watchdog takes.
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
  tracker produces fewer issues than the six it produced, and every issue
  it does produce cites a set of signal ids disjoint from every other issue
  produced by the same replay.
- **SC-003**: Replaying the three runs behind #761, #764 and #780 produces
  three separate issues, one per `{stage, tool}` pair — unchanged from
  today.
- **SC-004**: Across any 20 consecutive watchdog runs after this ships, no
  two *open* `pipeline-defect` issues cite a common signal id, except where
  a stated deliberate separation (FR-013) accounts for it.
- **SC-005**: Reverting the matching rule to exact-set equality makes the
  PR-time gate suite fail and names the overlap fixture; likewise for the
  class fan-out fixture and the `{stage, tool}` separation fixture.
- **SC-006**: A maintainer can determine, from a filed issue and its
  comments alone, which signal ids it covers and which occurrence
  contributed each — in 100% of issues filed after this ships.
- **SC-007**: No finding that would have been filed under the current rule
  is silently dropped: for every replayed scenario, each input finding is
  either filed, attached to an issue, or reported under a named
  write-suppression outcome.
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
  issues, and nothing else (FR-014 of spec 024). No option here adds a
  remediation path.
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
  false-merge boundary FR-011 and FR-013 draw.

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
- Bulk-closing unrelated existing `pipeline-defect` issues that are not the
  duplicates named in FR-023.
