# Feature Specification: A Bounded Read for the Marker Dedup Lookup

**Feature Branch**: `spec-draft/115-bounded-marker-dedup-lookup`

**Created**: 2026-09-30

**Status**: Draft

**Input**: Lifecycle issue #837 — "fix(durable-failure-issue): pass
--limit to the marker dedup lookup so matches past issue 30 aren't
dropped" (routed from board-loop.yml, originating issue #705; the finding
itself came from the code review of #693)

## Overview

`wing-commander-durable-failure-issue` is the one home for the durable
failure issue idiom: look up an issue by label, comment on it if it is
already there, create it if it is not. Since spec 056 it also accepts an
opt-in `marker` — a fingerprint string a candidate issue's body must
contain — so that a stage's finding appends to the issue that already
carries the same fingerprint instead of filing a second one. Every filer
of a machine-authored finding in this repository reaches GitHub through
that path: `wing-commander-stage-findings` (three survivor slots),
`board-loop.yml`'s out-of-scope review findings (three slots), and
`lifecycle-review-gate.yml`'s out-of-scope findings (three slots), all
under a `found-by:*` label and all with `state-scope: all`.

That lookup asks `gh issue list` for the label's issues and then filters
the returned set locally for the marker. It passes no `--limit`, and
`gh issue list` defaults to a single 30-issue page. So the lookup does not
search the label — it searches the label's newest 30 issues. While a
`found-by:*` label held fewer than 30 issues (open plus closed, because
`--state all`) that distinction was invisible. Past 30, the oldest
fingerprints fall off the end of the page the lookup never asked to be
widened, the marker does not match, and a finding that should have
appended to an existing issue files a duplicate instead. The dedup key
itself is sound (spec 076 settled its composition); what fails is the
window the key is looked for in.

The remedy is not a new design. `watchdog.yml`'s own fingerprint dedup
makes exactly this call, and it already carries an explicit bound with a
comment explaining why a bounded direct read was chosen over
`gh search issues`: GitHub's search index is eventually consistent, and a
prior use of the search index there produced a structurally identical miss
(#167/#168). This feature applies that settled convention to the one call
site that missed it, records the reason at that site, and puts a
checked-in fixture behind it so the bound cannot silently disappear again.

### Observed facts (verified against main at a90c011)

- `.github/actions/wing-commander-durable-failure-issue/action.yml:164`
  — the marker path's lookup:
  `gh issue list --repo "$GITHUB_REPOSITORY" --label "$LABEL" --state "$scope" --json number,state,body`,
  piped into `jq '[.[] | select(.body … contains($marker))] | first // empty'`.
  No `--limit`. The `jq` filter runs over whatever page `gh` returned, so
  the marker can only ever match inside the default 30.
- `.github/workflows/watchdog.yml:3196` — the same shape with the bound
  present: `… --state all --limit 200 --json number,state,body`, above it
  a comment calling it "a bounded, strongly-consistent direct read scoped
  to the finding's own class label — not an eventually-consistent search
  index", and naming #167/#168 as the prior art. The convention is
  therefore already decided in this repository; only its application here
  is missing.
- Callers that pass `marker` with `state-scope: all`, i.e. every caller
  exposed to this:
  `.github/actions/wing-commander-stage-findings/action.yml:407,519,619`;
  `.github/workflows/board-loop.yml:3153,3179,3205`;
  `.github/workflows/lifecycle-review-gate.yml:1270,1287,1304`. All nine
  file under a `found-by:*`-shaped label, and a label scoped to `all`
  accumulates closed issues as fast as it accumulates open ones — the
  30-issue ceiling is reached by ordinary success, not by a backlog.
- `.github/actions/wing-commander-durable-failure-issue/action.yml:179` —
  the no-marker path's lookup (`--state open --json number --jq '.[0].number // empty'`),
  also without `--limit`. It reads only the first element of a
  newest-first list, so the default page still yields the same answer a
  wider page would.
- `.github/scripts/stage-findings-tests/run_fixtures.py:52` extracts this
  composite's real `Look up, then report or close` step and drives it
  against a stubbed `gh` (`STUB_GH_TEMPLATE`, line 587), so the shipped
  lookup — not a copy of it — is already under fixture coverage. The stub
  prints its whole `list_json` on any `issue list` call and ignores
  `--limit` entirely; the existing fixtures assert outcomes, and one
  (`case_existing_no_marker_caller_is_byte_identical`, line 737) asserts
  on the invocation itself.
- `specs/049-single-home-release-idioms/contracts/durable-failure-issue.md`
  quotes the no-marker lookup line verbatim as the composite's contract; a
  shipped comment in `auto-update-spec-kit.yml:2771-2774` points readers at
  that file. The marker path postdates it and is not described there.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A repeat finding appends past the thirtieth issue (Priority: P1)

A stage meets the same defect it has met before. Its fingerprint is
already recorded on an issue under its `found-by:*` label, but that label
has since accumulated more than thirty issues (open and closed together)
and the matching one is no longer among the newest thirty. The maintainer
opening the board sees one issue for that defect with a new comment on it,
not a second issue saying the same thing.

**Why this priority**: This is the defect. Without it the pipeline's dedup
silently degrades with age — precisely when the board is busiest and a
duplicate costs the most attention — and every downstream count (open
findings, triage queue) inflates.

**Independent Test**: Drive the shipped lookup step against a stubbed
`gh` that behaves the way `gh` does — honouring the requested page size —
with thirty-one issues under the label and the fingerprint match as the
oldest. The step must resolve that issue and comment on it, and must not
create anything.

**Acceptance Scenarios**:

1. **Given** a label holding 31 issues where only the oldest carries the
   finding's marker, **When** the lookup runs, **Then** the outcome is
   "commented" on that issue's number and no issue is created.
2. **Given** the same 31-issue label and a marker no issue carries,
   **When** the lookup runs, **Then** the outcome is "created" — a widened
   page must not manufacture a match.
3. **Given** a label holding fewer issues than the bound, **When** the
   lookup runs, **Then** every outcome is exactly what it is today.

### User Story 2 - The bound cannot silently disappear again (Priority: P1)

A future edit to the composite drops or narrows the bound. The local gate
suite fails, naming the lookup, before the change can reach `main`.

**Why this priority**: Equal to P1 above under Principle VIII: the fix is
one flag, and a one-flag fix with nothing checking it is one careless
reformat away from regressing. The fixture is the deliverable, not a
garnish on it.

**Independent Test**: Remove the bound from the composite and run the
fixture harness; it must fail. Restore it; it must pass. A fixture that
passes in both states is not coverage.

**Acceptance Scenarios**:

1. **Given** the shipped lookup with its bound, **When** the fixture
   harness runs, **Then** it passes.
2. **Given** the bound removed from the shipped lookup, **When** the
   fixture harness runs, **Then** it fails and names the unbounded
   `gh issue list` call.
3. **Given** a bound present but at or below `gh`'s default page size,
   **When** the fixture harness runs, **Then** it fails — the assertion is
   about the window actually being wider, not about the flag being typed.

### User Story 3 - The reason is readable at the call site (Priority: P2)

An agent or maintainer reading the composite sees why the bound is there
and why a direct read rather than the search index, without having to
find `watchdog.yml` first.

**Why this priority**: Comments here are load-bearing, and the repository
has already paid once (#167/#168) for a lookup whose rationale lived
somewhere else. One canonical statement with a pointer at it satisfies
both this and the repository's no-second-copy rule for prose.

**Independent Test**: Read the composite's lookup step; the bound's reason
is stated there in one line, pointing at the canonical explanation rather
than restating it.

**Acceptance Scenarios**:

1. **Given** the shipped composite, **When** a reader reaches the marker
   lookup, **Then** a comment states the bound's purpose and points at the
   one canonical explanation of the bounded-direct-read choice.
2. **Given** that comment, **When** the comment-pointer gate runs,
   **Then** it passes — the rationale is not duplicated prose.

### Edge Cases

- The label holds exactly `gh`'s default page size, or exactly the bound:
  the boundary itself must resolve a match, not sit one off.
- The label's population exceeds the bound. The same failure this feature
  fixes returns, just further out; FR-005 decides whether that case is
  detected or merely deferred.
- The lookup call fails outright. Unchanged: `gh`'s failure is already
  tolerated into an empty match by `2>/dev/null || true`, and the report
  path's own degraded-outcome handling (`fail-on-api-error`) is what
  reports it. This feature must not widen or narrow that behaviour.
- A candidate issue with a null body is already skipped by the local
  filter; a wider page brings in more of them and must not change that.
- Two issues under the label carry the same marker (a duplicate that was
  filed before this fix): the lookup takes the first match in the page.
  With a wider page, "first" now means a different, older issue than it
  did. The appended comment must still land on exactly one issue, and the
  choice must be deterministic for a given page.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The marker-scoped dedup lookup in
  `wing-commander-durable-failure-issue` MUST request an explicitly
  bounded page whose size exceeds `gh issue list`'s default page size, so
  that a fingerprint recorded on an issue older than the newest thirty is
  still found.
- **FR-002**: The bound MUST be the same value `watchdog.yml`'s
  fingerprint dedup already ships (`--limit 200`), adopted as the
  repository's settled convention for a fingerprint-scoped direct read
  rather than re-argued here.
- **FR-003**: The bound MUST be visible at the call site as a literal on
  the shipped invocation — not supplied by a caller input, an environment
  variable, or a default computed elsewhere — so that reading the step
  tells a reader the window it reads.
- **FR-004**: A one-line comment at the lookup MUST state why the bound
  exists and MUST point at the canonical explanation of the
  bounded-direct-read choice (`watchdog.yml`'s dedup-search comment)
  rather than restating its reasoning, per this repository's one-canonical-
  comment rule.
- **FR-005**: When the label's issue population exceeds the bound, the
  composite MUST [NEEDS CLARIFICATION: behaviour when the bounded page is
  full — silently accept the same truncation risk further out, emit a
  warning annotation naming the label, or treat a full page as an
  indeterminate lookup and refuse to file (suppressing a possible
  duplicate at the cost of possibly dropping a genuinely new finding)?]
- **FR-006**: The no-marker (label-only) lookup MUST
  [NEEDS CLARIFICATION: also carry the same explicit bound, for uniformity
  and against a future edit that starts reading more than `.[0]` — which
  also requires updating the verbatim snippet in
  `specs/049-single-home-release-idioms/contracts/durable-failure-issue.md`
  in the same change — or stay byte-identical, on the ground that reading
  only the newest element of a newest-first list is already correct at any
  page size?]
- **FR-007**: A checked-in fixture in
  `.github/scripts/stage-findings-tests/run_fixtures.py` MUST drive the
  shipped lookup step against a label scan of thirty-one issues whose sole
  marker match is the oldest entry, and MUST assert the lookup resolves
  that issue and creates nothing.
- **FR-008**: The `gh` stub that fixture uses MUST honour the requested
  page size the way `gh` does — returning at most the requested number of
  newest-first entries, and at most the default page size when no bound is
  requested — so the fixture fails against an unbounded lookup. A stub
  that returns every issue regardless of the request cannot fail its
  subject and does not satisfy this requirement.
- **FR-009**: The fixture MUST additionally assert that the shipped
  invocation carries an explicit page bound greater than `gh`'s default
  page size, so a bound that is present but too small fails as loudly as
  an absent one.
- **FR-010**: Every existing fixture over this composite MUST continue to
  pass unchanged in intent, including the one asserting a no-marker
  caller's invocation is byte-identical; if FR-006 resolves to bounding
  that path too, that fixture's assertion MUST be updated to the new
  byte-exact expectation rather than loosened.
- **FR-011**: Dedup semantics other than the page width MUST NOT change:
  an OPEN match still yields `commented` on that issue, a closed match
  still yields `created-linked-closed` with the closed issue named, no
  match still yields `created`, and the lookup's tolerance of a failed
  `gh` call is untouched.
- **FR-012**: The repository's gate coverage for this convention MUST be
  [NEEDS CLARIFICATION: the fixture alone (the originating issue's ask), or
  additionally a gate that fails any `gh issue list` under
  `.github/workflows/` or `.github/actions/` that filters the returned
  bodies locally while requesting no explicit bound — which would catch the
  next such call site instead of only this one, at the cost of a new gate
  registration and its own fixtures?]
- **FR-013**: Whatever coverage FR-012 resolves to MUST be reachable from
  both `run-local-gates.py` and the CI lint suite with the same subject and
  the same arguments, and MUST be wired into the gate registry the same way
  the harness it extends already is.

### Key Entities

- **Marker**: the literal fingerprint string a candidate issue's body must
  contain for the lookup to call it the same finding. Composed elsewhere
  (spec 076); unchanged here.
- **Label scan**: the set of issues `gh issue list` returns for a label at
  a requested state scope and page size. This feature changes only its
  width.
- **Dedup outcome**: `commented` / `created` / `created-linked-closed`
  plus the resolved issue number, as read by every caller. Unchanged in
  shape.

## Success Criteria *(mandatory)*

- **SC-001**: A finding whose prior issue is the thirty-first-oldest under
  its label appends to that issue instead of filing a second one,
  demonstrated by a checked-in fixture that runs in under the harness's
  existing time budget and needs no network.
- **SC-002**: Removing the bound from the shipped lookup makes the fixture
  harness fail; restoring it makes it pass. Demonstrated by running the
  harness in both states before merge.
- **SC-003**: Lowering the bound to `gh`'s default page size also makes
  the harness fail, so the assertion measures the window and not the
  presence of a flag.
- **SC-004**: All nine marker-passing call sites keep their current
  outcomes on label populations below the default page size — no existing
  fixture changes its expected outcome except as FR-010 allows.
- **SC-005**: The full local gate suite (`run-local-gates.py`) passes on
  the change, including the comment-pointer and single-home gates.
- **SC-006**: A reader of the composite can state, from the step alone,
  how wide the lookup reads and why, without opening another file for the
  reason's existence (only for its full argument).

## Assumptions

- `gh issue list` returns a label's issues newest-first and truncates to
  the requested page size; this is the behaviour the fixture's stub must
  model and the behaviour the observed defect depends on.
- Existing duplicate issues already filed under a `found-by:*` label by
  this defect are historical records. Reconciling or closing them is a
  maintainer's judgement, not part of this change, and no migration of
  already-recorded markers is in scope (matching spec 076's own choice).
- The bounded direct read stays a direct read: `gh search issues` remains
  rejected for this lookup for the reason `watchdog.yml` already records,
  and this feature does not revisit that choice.
- No adopter pins a behaviour that depends on the lookup's page width; the
  composite's declared inputs and outputs are unchanged, so the published
  contract (Principle VII) is not widened by this change.
- The `found-by:*` labels are per-finder, not per-finding, so their
  populations grow monotonically with pipeline activity — which is why the
  ceiling is reached by ordinary operation and why FR-005's question is
  about "when", not "if".

## Dependencies

- `.github/actions/wing-commander-durable-failure-issue/action.yml` — the
  subject; the `Look up, then report or close` step.
- `.github/workflows/watchdog.yml` — the `Dedup search` step, the
  canonical statement of the bounded-direct-read choice FR-004 points at
  (read only; unchanged).
- `.github/scripts/stage-findings-tests/run_fixtures.py` and its
  `run-tests.sh` wrapper — where FR-007 to FR-010 land, including the
  `gh` stub FR-008 makes faithful.
- `.github/actions/wing-commander-stage-findings/action.yml`,
  `.github/workflows/board-loop.yml`,
  `.github/workflows/lifecycle-review-gate.yml` — the nine marker-passing
  call sites whose behaviour FR-011 protects (read for their contract;
  unchanged).
- `specs/049-single-home-release-idioms/contracts/durable-failure-issue.md`
  — the live contract quoting the no-marker lookup verbatim; in scope only
  if FR-006 resolves to bounding that path.
- `.github/workflows/lint-workflows.yml` and
  `.github/scripts/run-local-gates.py` — where FR-013 wires whatever
  coverage FR-012 resolves to.

## Out of Scope

- Changing how a fingerprint or marker is composed, normalized, or
  recorded (spec 076's key rule and its gate stay as they are).
- Reconciling duplicate issues this defect already filed, or backfilling
  markers onto them.
- Replacing the direct read with a search-index query, or introducing
  pagination that walks every page of a label.
- Changing `fail-on-api-error`, the degraded-report outcomes, or the
  label-description truncation this composite performs.
- Any change to `watchdog.yml`'s own dedup search, which already carries
  the bound.
- Auditing every `gh` list call in the repository for an explicit bound;
  FR-012 decides only whether a gate covers the body-filtering shape, and
  a general audit is a separate issue if the answer is no.
