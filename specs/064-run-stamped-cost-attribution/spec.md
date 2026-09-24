# Feature Specification: The Cost Line Names Its Own Run — Run-Stamped Cost Attribution

**Feature Branch**: `spec-draft/064-run-stamped-cost-attribution`

**Created**: 2026-09-24

**Status**: Draft

**Input**: Lifecycle issue #491 — "watchdog: cost-line attribution cannot
tell two runs overlapping on one lifecycle issue apart" (routed from the
board loop; originating issue #380, found by the code review of #378)

## Overview

Every cost-bearing pipeline stage posts a per-run cost line on its lifecycle
issue (`**Cost**: $0.42 · 37 turns · claude-opus-5`). The watchdog's
cost-report collector reads those comments back to answer one question: *did
this run post its cost line, and is the amount well-formed?* A run that owes
a cost line and never posted one is reported as `cost-line-missing`.

The collector cannot actually tell whose comment it is reading. It decides
"this run's own comments" from two weak signals:

- **author login** — the pipeline's own identities (the App as
  `<slug>[bot]`, plus `github-actions[bot]`), and
- **time window** — comments created between the inspected run's
  `createdAt` and its `updatedAt`.

Neither signal distinguishes two pipeline runs from each other. When two
runs overlap on one lifecycle issue, each falls inside the other's window,
so the cost line one of them posted is read as belonging to both. The run
that posted nothing is credited with its neighbour's line and its genuine
`cost-line-missing` is masked. The watchdog's own source comment already
admits this:

> Known limit: two runs overlapping on one issue can each be credited with
> the other's line; nothing in a comment names the run that posted it.
> — `.github/workflows/watchdog.yml`, `COST_ATTRIBUTION_FILTER`

### Observed failure

Runs #369 and #370 were clarify runs started **8 seconds apart** on
lifecycle issue #362. Both windows contained both comments. One run's cost
line satisfied the collector for both, and the other run's missing cost line
was never reported.

This is a *supervision* defect, not a cost defect: the watchdog is the thing
that is supposed to notice when a stage stops reporting what it spent, and a
masked `cost-line-missing` is exactly the signal it exists to raise. Overlap
is not exotic — the board loop, a re-driven proof run, and a human replying
on an issue that a stage is already working all produce it.

### The fix in one sentence

Make each cost-bearing comment say which run posted it, at the single place
the cost line is formatted, and have the collector believe that statement in
preference to the time window — keeping the window as the fallback for
comments posted before the stamp existed.

## Clarifications

Two questions remain open. They are recorded as `[NEEDS CLARIFICATION]`
markers against the requirements they govern (FR-002, FR-008) and are posted
to lifecycle issue #491 for the owner to answer.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A run that posted no cost line is reported, even with a neighbour on the same issue (Priority: P1)

Two pipeline runs work the same lifecycle issue at overlapping times. One
posts its cost line; the other does not. The watchdog inspects each of them
and reports `cost-line-missing` for exactly the one that owes a line and did
not post it — never for the one that did, and never for neither.

**Why this priority**: This is the reported defect. Until it is fixed, the
watchdog's cost supervision is silently unreliable on any issue with
concurrent activity, and the failure is invisible: a masked signal looks
exactly like a healthy run.

**Independent Test**: Replay the #369/#370 shape — two cost-bearing runs on
one lifecycle issue whose windows overlap, one of which posted a cost line —
and confirm each run's collection produces the correct verdict for that run
alone.

**Acceptance Scenarios**:

1. **Given** two cost-bearing runs whose windows overlap on one lifecycle
   issue, and only run A posted a cost line, **When** the watchdog inspects
   run A, **Then** no `cost-line-missing` signal is emitted.
2. **Given** the same state, **When** the watchdog inspects run B, **Then**
   `cost-line-missing` is emitted naming run B.
3. **Given** the same state but with run A's cost line malformed, **When**
   the watchdog inspects run B, **Then** run B's verdict is unaffected by
   run A's malformed line — no `cost-line-malformed` is charged to run B.
4. **Given** two runs on one issue that *each* posted a correct cost line,
   **When** the watchdog inspects either, **Then** neither produces a
   signal, and each reads its own line rather than the other's amount.
5. **Given** a run whose cost line is the only pipeline comment in its
   window, **When** the watchdog inspects it, **Then** the verdict is
   unchanged from today's behaviour.

---

### User Story 2 - Every cost-bearing comment names its run, from one place (Priority: P1)

Every comment the pipeline posts carrying a cost line carries a
machine-readable statement of which run posted it. That statement is added
where the cost line is formatted — the one home the formatter already has —
so no stage workflow has to remember to add it and no two stages can drift.

**Why this priority**: The attribution rule in User Story 1 cannot exist
without the stamp, and a stamp added per call site is the pasted-copy shape
this repository's single-home rule exists to prevent — there are nine stage
workflows posting this line.

**Independent Test**: Render the cost line for a known run and confirm the
stamp names that run; then confirm that a workflow posting a cost line
without going through the formatter fails a gate.

**Acceptance Scenarios**:

1. **Given** a cost-bearing agent step, **When** its stage posts any comment
   carrying the cost line, **Then** that comment carries a stamp naming the
   run that posted it.
2. **Given** a stage whose metrics were unavailable and which posts the
   degraded one-line fallback, **When** it posts that comment, **Then** the
   comment still carries the stamp — a run that reports "metrics
   unavailable" is still a run whose comment must be attributable.
3. **Given** a reader looking at the lifecycle issue in GitHub's web UI,
   **When** the comment renders, **Then** the stamp is not visible — it
   changes no human-readable text of any existing comment.
4. **Given** a change that adds a second formatter for the cost line in a
   workflow, **When** the PR-time gate suite runs, **Then** a gate fails, as
   it does today.

---

### User Story 3 - The attribution rule has a gate that can fail it (Priority: P2)

The overlapping-runs case is a checked-in scenario of the gates that already
exercise the cost-report collector, so the next change to attribution fails
a gate rather than masking a supervision signal for weeks.

**Why this priority**: This defect was found by a code review, not by a
gate — the existing cost-report scenarios all use a single run on a single
issue, so every one of them passes with the broken rule and with the fixed
one alike. Constitution VIII: a green check means what it says.

**Independent Test**: Run the PR-time gate suite against a collector with
the stamp preference removed, and confirm a gate fails.

**Acceptance Scenarios**:

1. **Given** the overlapping-runs fixtures, **When** the PR-time gate suite
   runs, **Then** the collector's verdict is asserted for each run of the
   overlapping pair independently.
2. **Given** a change that makes the collector ignore the stamp and use the
   time window alone, **When** the gate suite runs, **Then** a gate fails.
3. **Given** a change that makes the collector accept a stamp naming a
   different run, **When** the gate suite runs, **Then** a gate fails.

---

### Edge Cases

- **No comment in the window carries a stamp** (every comment predates the
  stamp). The window heuristic decides, exactly as it does today — the
  pre-stamp behaviour is preserved, including its known limit.
- **A comment carries a stamp naming a different run.** It is not this run's
  comment, whatever the window says.
- **A comment carries a malformed or unparsable stamp.** It degrades to "no
  stamp" — the collector never raises and never guesses a run id.
- **A non-pipeline account posts a comment containing a stamp** naming the
  inspected run. The stamp is only believed on comments the pipeline's own
  identities authored; the existing author filter is not weakened by the
  stamp, it is narrowed by it.
- **One run posts several cost-bearing comments** (a stage that announces a
  questionnaire and then a PR link). All carry the same run's stamp; the
  collector's existing "first cost line wins, ordered by creation time" rule
  is unchanged.
- **The run posted a stamped comment that carries no cost line at all.** The
  run is known to have commented, so the verdict is `cost-line-missing` with
  "a comment of its own was found" — the distinction the collector already
  draws, now drawn correctly.
- **The run's window or the App login is unresolvable.** Today the collector
  reports nothing either way (#376). With a stamp the run's own comments are
  identifiable without the window, so this degradation narrows — see FR-009.
- **A run was re-run** (a second attempt of the same workflow run). See
  FR-002's open question.
- **A run posts its cost line after its recorded `updatedAt`.** Possible
  when the last comment lands as the run finalises; a stamped comment is
  attributed on its stamp regardless of the window.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Every comment the pipeline posts on a lifecycle issue that
  carries a per-run cost line MUST carry a machine-readable stamp naming the
  run that posted it. This includes the degraded "metrics unavailable"
  fallback a stage posts when the metrics summary never ran.

- **FR-002**: The stamp MUST identify the posting run unambiguously among
  the runs that can post on the same lifecycle issue.
  [NEEDS CLARIFICATION: must the stamp distinguish re-run attempts of the
  same workflow run (run id + attempt), or is the run id alone sufficient?
  A re-run reuses its run id, and both attempts post their own cost line on
  the same issue, so run-id-only attribution reproduces the reported defect
  for that pair.]

- **FR-003**: The stamp MUST be applied at the single place the cost line is
  formatted, so that every consumer of that line inherits it. No stage
  workflow may add, re-add, or reformat the stamp itself; a second formatter
  MUST fail the existing single-home gate the cost-line formatter is already
  covered by.

- **FR-004**: The stamp MUST NOT change any human-visible text of the
  comments it is added to — it is metadata for the collector, not content
  for the requester, and several of these comments are byte-compared by
  existing gates.

- **FR-005**: The cost-report collector MUST attribute a comment to the
  inspected run on the strength of its stamp, in preference to the time
  window, whenever a stamp is present and the comment was authored by one of
  the pipeline's own identities.

- **FR-006**: The collector MUST NOT treat a comment carrying a stamp that
  names a run other than the inspected one as the inspected run's own
  comment, regardless of whether it falls inside the inspected run's time
  window. This is the single change that closes the reported defect.

- **FR-007**: The collector MUST continue to require that a comment was
  authored by one of the pipeline's own identities before believing its
  stamp. A stamp appearing in a comment posted by any other account MUST be
  ignored — the stamp is content in a comment body, and comment bodies are
  untrusted content (Constitution V).

- **FR-008**: The collector MUST retain the existing author-plus-window
  heuristic as a fallback for comments carrying no stamp, so comments posted
  before this feature shipped keep their current attribution.
  [NEEDS CLARIFICATION: when the inspected run's window contains stamped
  comments but none of them is the inspected run's, may an *unstamped*
  comment in that window still be attributed to the inspected run
  (conservative: no false positives, but a pre-stamp comment from an
  overlapping run can still be misattributed), or do stamps decide alone
  once any stamp is present in the window (strict: catches every overlap,
  but can report a false `cost-line-missing` against a mixed-era issue)?]

- **FR-009**: Where a stamped comment identifies the inspected run's own
  comments, the collector MUST NOT abandon the check merely because the
  run's time window is unresolvable. It MUST still decline to report
  anything when it has neither a usable stamp match nor a usable window —
  "not checked" is never "checked and absent" (#376), and that guarantee is
  not weakened by this feature.

- **FR-010**: Each emitted cost-report signal MUST record how the comment
  was attributed — by stamp or by the window fallback — so a maintainer
  reading a `cost-line-missing` issue can tell a stamp-backed finding from a
  heuristic one.

- **FR-011**: The collector's read outcome semantics MUST be unchanged: a
  failed comment read still marks the collector untrusted for the run rather
  than reporting an absent cost line, and a run that owes no cost line
  (skipped, cancelled, no metrics record, or `cost_available` false) still
  produces no signal.

- **FR-012**: The overlapping-runs case MUST be a checked-in scenario of the
  gates that already cover the cost-report collector, asserting the verdict
  for **each** run of an overlapping pair independently, and covering at
  minimum: overlapping pair where only one posted a line; overlapping pair
  where both posted; a foreign-stamped comment inside the window; an
  unstamped comment inside the window (pre-stamp behaviour); a malformed
  stamp; and a stamp in a comment by a non-pipeline author. The gates MUST
  fail when the stamp preference is removed or inverted (mutation check),
  since today's single-run scenarios pass with the defect present.

- **FR-013**: The stamp's shape MUST be documented once, at the place it is
  written, with every reader pointing at that description rather than
  restating it.

### Key Entities

- **Cost line**: the preformatted per-run line
  `**Cost**: <cost> · <turns> · <model>`, each part degrading to
  "... unavailable" independently. It has exactly one formatter today, and
  every stage appends that formatter's output verbatim with a one-line
  fallback for the case where the formatter never ran.
- **Run stamp**: the new machine-readable, human-invisible statement of
  which run posted a cost-bearing comment. Analogous to the existing rollup
  marker the metrics-persist step writes onto its own comment.
- **Inspected run**: the run the watchdog is currently supervising, and the
  subject every cost-report signal is charged to.
- **Cost-report signal**: `cost-line-missing` or `cost-line-malformed`,
  carrying the stage and run it is charged to, whether a comment of the
  run's own was found, and (new, FR-010) how that comment was attributed.
- **Attribution window**: the inspected run's `createdAt`..`updatedAt`
  bounds, which today are the only thing separating one run's comments from
  another's and after this feature are the fallback.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For two cost-bearing runs overlapping on one lifecycle issue
  where exactly one posted a cost line, the watchdog reports
  `cost-line-missing` for exactly one run — the one that posted nothing —
  100% of the time, demonstrated by fixture.
- **SC-002**: Replaying the #369/#370 conditions (two clarify runs started
  8 seconds apart on issue #362) produces the correct verdict for each run
  independently.
- **SC-003**: Zero cost-bearing comments posted by the pipeline after this
  feature ships lack a run stamp, measured across one full lifecycle
  (intake → finalize) of a real feature.
- **SC-004**: Zero human-visible changes to the text of existing comments —
  the existing byte-comparing gates over those comments pass unchanged.
- **SC-005**: Every attribution branch named in FR-012 is covered by a
  checked-in fixture, and deliberately removing or inverting the stamp
  preference fails the PR-time gate suite.
- **SC-006**: No new false `cost-line-missing` issue is filed in the first
  30 days after the change — the #376 regression (eight false issues) is not
  repeated in the opposite direction.
- **SC-007**: A maintainer reading any cost-report finding can tell from the
  finding alone whether it was attributed by stamp or by window.

## Assumptions

- The per-run cost line already has exactly one formatter, and every stage
  consumes that formatter's output rather than building the line itself.
  This feature relies on that being true and does not re-establish it; the
  gate that enforces it is in place today.
- The run identity the stamp carries is already known at the point the cost
  line is formatted — the metrics record the formatter reads is keyed by
  run id. No new lookup, token, or network call is needed to write a stamp.
- An HTML-comment-style marker is invisible in every surface these comments
  render in (issue comments, PR comments, step summaries), so applying the
  stamp at the formatter rather than at each posting site does not create
  visible noise anywhere the line already goes.
- The watchdog inspects completed runs, so a run's cost-bearing comments
  exist by the time the collector reads them; a comment landing fractionally
  after the recorded `updatedAt` is the reason FR-006 does not re-apply the
  window to stamped comments.
- The existing author-login filter (the App as `<slug>[bot]` and
  `github-actions[bot]`) is correct as written and is reused unchanged; the
  stamp narrows that set, it does not replace it.
- Comments posted before this feature ships are never re-stamped. They keep
  the window heuristic and its known limit, which is acceptable because the
  masked signal they can produce is the status quo, not a regression.
- The cost-report collector is the only consumer of the attribution window;
  no other watchdog collector reads lifecycle-issue comments, so this change
  does not perturb them.
- "Cost-bearing" continues to mean what the collector already means by it: a
  run with a metrics record whose `cost_available` is true, and whose
  conclusion is neither skipped nor cancelled.

## Dependencies

- The per-run cost-line formatter and its single-home gate — the place the
  stamp is written (FR-003).
- The watchdog's cost-report collector, its two decision programs, and the
  run metadata (`createdAt`, `updatedAt`, lifecycle issue, App login) it
  already resolves.
- The gates that cover the cost-report collector today: the one that
  executes the whole collector step against synthetic comment listings, and
  the one that pins the collector's decision programs against fixtures.
  FR-012's scenarios extend these rather than adding a third harness.
- Spec `046-watchdog-supervision-collectors`, which defines the cost-report
  collector, its signal classes, and its gate coverage. This feature is a
  correction inside that feature's boundary.
- The rollup marker written by the metrics-persist step, as the precedent
  for an invisible, machine-readable marker on a pipeline-authored comment.

## Out of Scope

- Changing what the cost line says, how the cost is computed or rounded, or
  how turns are counted.
- Changing the cost-report signal classes, their fingerprints, their dedup
  identity, or how the watchdog diagnoses and files them.
- Stamping comments that carry no cost line (stage announcements, callouts,
  questionnaires without a cost line) — the attribution question this
  feature answers is only asked about cost-bearing comments.
- Back-filling stamps onto comments posted before this change.
- Extending the stamp to any other watchdog collector, or using it as an
  eligibility, routing, or dedup input.
- Preventing two pipeline runs from overlapping on one lifecycle issue. The
  overlap is legitimate; only the attribution is wrong.
