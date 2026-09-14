# Feature Specification: Correlated, atomic release dispatch

**Feature Branch**: `048-correlated-release-dispatch`

**Created**: 2026-09-14

**Status**: Draft

**Input**: User description (GitHub issue #324): "auto-release: the dispatched release.yml run is found by \"newest run\" with no correlation, and the stale-head check is not atomic with the dispatch"

## Overview

The automatic release path (spec 045, `auto-release.yml`) detects unreleased
work on the default branch, verifies it end-to-end, computes the next
non-breaking version, and asks the existing release automation
(`release.yml`) to cut it. Two seams in the handover between the two
workflows are currently held together by assumption rather than by evidence.

**The run it watches may not be the run it caused.** After asking for the
release, `auto-release.yml` finds "its" run by listing the most recent
`release.yml` run on the default branch and watching whatever comes back.
Nothing ties that run to the request: the release workflow's run title does
not carry the version, and the inputs a dispatch carried are not readable
from the runs listing. A maintainer's own manual release dispatch in the
same minute — a deliberate breaking release, for instance — is
indistinguishable from the automatic one. The consequence is a report that
can be wrong in either direction: the automatic path can announce
"released vX.Y.Z" and close its standing failure issue on the strength of
somebody else's run, or it can file a release failure for a run that was
never its attempt. The two workflows hold separate single-in-flight guards,
so neither one's serialisation covers the other.

**The head it verified may not be the head that gets tagged.** The guard
that refuses to release a head the default branch has moved past reads the
branch tip, compares it, and only then makes the request — two separate
reads with a window between them. The release automation checks out the
branch fresh at the moment the request is accepted, so a merge that lands in
that window is tagged without any end-to-end verification ever having seen
it. That is precisely the outcome FR-016 of spec 045 exists to prevent, and
today it is prevented only by the window being short.

Both seams are fixed by making the handover carry evidence: the request says
which head it means and which attempt it is, and the release automation
answers on that basis instead of the automatic path inferring an answer from
recency. Because that changes the release automation's own contract — shared
by the maintainer's manual path — the shape of the evidence was the owner's
decision, which is why this arrived as a spec request rather than a local
fix. That decision is recorded in Clarifications below and carried through
the requirements: the release automation gains a run title carrying the
version and an optional attempt token, and an optional commit input it
refuses to tag past; the tag that results is what proves the release
happened.

## Clarifications

### Session 2026-09-14

- Q: Which form of correlating evidence ties the dispatched release run to the attempt that asked for it? → A: Both a title and a time bound. The release automation gains a run title carrying the version and an optional attempt-identifying token supplied as an input; the automatic path selects the run whose title carries its own token *and* whose start time is after its own request. The title establishes identity; the time bound closes the case where an earlier attempt requested the same version and left an identically-titled run behind. A manual dispatch leaves the token blank, so its run title can never match. (FR-002, FR-003, FR-016)
- Q: What counts as authoritative proof that this attempt's release happened? → A: The tag state — the exact version tag exists and points at the verified commit. The correlated run is used for log links and diagnostics only. The tag is the durable artifact and is immune to correlation lag, and because the release automation refuses to tag any commit but the verified one, a tag in that position is the outcome this attempt asked for. The standing failure issue closes on that fact rather than on a run listing. (FR-005, FR-007, FR-008)
- Q: How is the "verified head == tagged commit" guarantee enforced? → A: The release automation accepts an optional commit input, checks that commit out, and refuses to tag unless that commit is still the default branch's tip at the moment the tag would be created; the automatic path passes its verified head. Evaluating at tag time rather than at request time keeps a dispatch that sat queued covered. A manual dispatch leaves the input blank and tags the tip exactly as it does today. This declines assert-only and after-the-fact detection, both of which leave a wrong tag publishable. (FR-010, FR-011, FR-014, FR-015)

## User Scenarios & Testing *(mandatory)*

### User Story 1 - An automatic release never reports on a run it did not cause (Priority: P1)

A maintainer dispatches a deliberate breaking release by hand at the same
moment the scheduled automatic check reaches its dispatch step. Today, the
automatic path watches the maintainer's run and reports its outcome as its
own. After this feature, the automatic path identifies its own run by the
attempt token its request put in the run's title; if it cannot, it says so,
and what it reports as released rests on the tag it asked for rather than on
whatever run happens to be newest.

**Why this priority**: This is the failure that corrupts the record. A wrong
"released vX.Y.Z" closes the standing failure issue and tells the maintainer
a version was published that was not; a wrong release failure sends them to
read someone else's logs. Every other story here protects a tag; this one
protects the maintainer's ability to trust the report at all.

**Independent Test**: Start a manual release dispatch and an automatic
attempt so that both have a run in flight, and confirm the automatic run's
report names only its own run, and that a run it did not cause is never
adopted as its own under any outcome.

**Acceptance Scenarios**:

1. **Given** an automatic attempt has requested a release, **When** another
   release run exists that the attempt did not cause (started before it,
   concurrently with it, or by a different requester), **Then** the attempt
   does not watch that run, does not report its conclusion, and does not
   close or file anything on the strength of it.
2. **Given** an automatic attempt whose own release run is found and the
   exact version tag exists on the verified commit, **When** the report is
   written, **Then** it records the release and links the run that the
   attempt itself caused — never another run's.
3. **Given** an automatic attempt whose own release run cannot be identified
   within the waiting period, **When** the report is written, **Then** it
   states that the attempt's own run was not observed and links no run; it
   reports a release only if the exact version tag exists on the verified
   commit, and otherwise reports no release and does not close the standing
   failure issue.
4. **Given** two automatic attempts on different days that requested the same
   version (the first having failed before any tag was created), **When** the
   second attempt looks for its run, **Then** it never adopts the first
   attempt's run.

---

### User Story 2 - A tag only ever lands on a verified head (Priority: P1)

A pull request merges in the seconds between the automatic path confirming
the branch tip and the release automation checking the branch out. Today the
newly merged commit is tagged, having never been verified end to end. After
this feature, either the verified commit is the one tagged, or no tag is
created and the attempt reports why.

**Why this priority**: This is the guarantee the whole automatic path exists
to make — the reason it verifies before releasing. A tag on an unverified
commit is published, immutable, and consumed by anyone pinning the floating
major tag. It shares P1 with Story 1 because the two defects are independent:
fixing correlation does not narrow this window, and fixing this window does
not stop a foreign run being adopted.

**Independent Test**: Request a release naming a commit that is no longer the
branch tip and confirm no tag and no release are created, and that the
refusal is reported with both the commit named and the tip observed.

**Acceptance Scenarios**:

1. **Given** a release request that names the verified commit, **When** the
   branch tip still equals that commit at the moment the tag would be
   created, **Then** the release is built from that commit and the tag is
   created on it.
2. **Given** a release request that names the verified commit, **When** the
   branch has advanced past it by the time the tag would be created,
   **Then** no tag is created, no release is published, and the refusal names
   both the requested commit and the tip observed — including when the
   advance happened while the request sat queued behind another release run.
3. **Given** an automatic attempt whose release request was refused for that
   reason, **When** its report is written, **Then** it is reported as the
   expected "the branch moved on" outcome rather than as a broken pipeline,
   and the next scheduled check verifies the new head from scratch.
4. **Given** a release that is created, **When** a maintainer asks which
   commit was verified for it, **Then** the tagged commit and the verified
   commit are the same commit, and that is a property the release automation
   enforced rather than a window that happened to stay closed.

---

### User Story 3 - The maintainer's manual release path keeps working unchanged (Priority: P2)

A maintainer cuts a breaking release by hand, as they do today: open the
release workflow, type the version, tick breaking, write the migration notes,
run it. Nothing new is required of them.

**Why this priority**: Spec 045's FR-021 already promises this, and this
feature is the first change to touch the release automation's inputs since.
It is P2 rather than P1 because it is a constraint on how P1 and Story 2 are
delivered rather than a capability of its own — but a delivery that
tightened the manual path would be a regression the maintainer feels every
release.

**Independent Test**: Dispatch the release workflow by hand supplying only
the inputs required today, and confirm it behaves exactly as it does today.

**Acceptance Scenarios**:

1. **Given** the release workflow's manual dispatch form, **When** a
   maintainer fills in only the inputs that are required today, **Then** the
   release proceeds exactly as it does today.
2. **Given** a manual dispatch that names no particular commit, **When** the
   release runs, **Then** it tags the branch tip as it does today, with no
   new refusal.
3. **Given** a manual dispatch, **When** an automatic attempt is looking for
   its own run, **Then** the manual run is never mistaken for it, regardless
   of timing or of which version each one names.

---

### Edge Cases

- **A run that matches on every visible attribute but is not ours.** Two
  attempts can legitimately request the same version — a first attempt that
  failed before creating a tag, and a later retry. Identity must not rest on
  the version alone; the earlier attempt's run carries the same version in
  its title, so the attempt token and the time bound together are what keep a
  stale run from being adopted.
- **The requested run never appears.** A dispatch can be accepted and the run
  still not be listable within the waiting period (queueing, API lag). The
  attempt must report "not observed" honestly about the run: with no tag on
  the verified commit it must neither claim a release nor assert that the
  release failed.
- **The release actually happened but was never correlated.** The dispatch
  succeeded, the tag was created, and the attempt still could not identify
  its run. Because the tag state is the proof (FR-007) and the release
  automation refuses to tag anything but the verified commit (FR-010), the
  attempt reports the release and notes that its run could not be linked.
  Either way the next scheduled check must reach a correct conclusion (it
  sees the new tag, finds no unreleased work, and stays quiet) rather than
  attempting a duplicate release.
- **The dispatch is rejected outright.** Unchanged from today: no run, no
  release, reported as a release failure with no run link.
- **The release run is cancelled** (by a maintainer, or by a concurrency
  guard). A cancelled run is not a successful release and must not be
  reported as one.
- **The named commit is not on the default branch at all** — it was
  force-pushed away, or belongs to another branch. The release automation
  must refuse rather than tag it.
- **The named commit is an ancestor of the tip.** This is the ordinary
  "branch moved on" case and must be refused, not tagged; releasing an
  older commit would move the floating major tag backwards.
- **Concurrency guards interact.** The two workflows serialise
  independently, so a request can sit queued behind another release run for
  longer than the window the branch stays still. The refusal in Story 2 must
  be evaluated at tag time, not at request time, or the queue reintroduces
  the gap.
- **A maintainer's manual run and an automatic run request the same version.**
  Exact release tags are immutable, so whichever runs second refuses on the
  existing tag-collision check. Each must report its own outcome, and the
  automatic attempt must not read the other's refusal as its own. If the
  manual run won the race and tagged the verified commit, the tag state the
  automatic attempt asked for holds and it reports the release; if the manual
  run tagged a different commit under that version, the tag state does not
  hold and the attempt must not report a release.

## Requirements *(mandatory)*

### Functional Requirements

**Correlating the dispatched run**

- **FR-001**: The automatic release path MUST identify the release run it
  caused by evidence tying that run to its own request, and MUST NOT identify
  it by recency, by being the only recent run, or by any other inference from
  ordering alone.
- **FR-002**: The correlating evidence MUST be carried through the release
  request itself, so that a run started by anyone else — a maintainer's
  manual dispatch in particular — cannot satisfy it. The release automation
  MUST title its run with the version it was asked for and with an
  attempt-identifying token taken from an optional request input, and the
  automatic path MUST select its run on that token. A request that supplies
  no token MUST produce a run whose title cannot match any attempt.
- **FR-002a**: The attempt token MUST be unique to a single attempt, so that
  no two attempts — including two attempts requesting the same version — can
  ever produce the same title.
- **FR-003**: Correlation MUST be bounded in time as well as in identity: a
  run that started before the current request was made MUST never be adopted,
  even if every other attribute, the token included, matches.
- **FR-004**: When more than one run satisfies the correlating evidence, the
  attempt MUST treat the outcome as ambiguous rather than picking one.
- **FR-005**: When no run satisfies the correlating evidence within the
  waiting period, the attempt MUST report that its own run was not observed
  and MUST link no run. Whether a release is reported and whether the
  standing failure issue is closed is decided by FR-007 and not by the
  correlation, so an unobserved run with no tag on the verified commit MUST
  NOT be reported as a release and MUST NOT close that issue.
- **FR-006**: An ambiguous or unobserved correlation MUST be a distinct
  reported outcome, distinguishable by a maintainer from "the release ran and
  failed" and from "the request was rejected", and its report MUST name the
  version requested and the time of the request.
- **FR-007**: The report MUST record a release as having happened on the tag
  state alone: the exact version tag exists and points at the commit the
  end-to-end verification passed for. The correlated run MUST be used only
  for log links and diagnostics and MUST NOT itself be the proof that the
  release happened. Closing the standing failure issue MUST rest on that same
  tag state.
- **FR-007a**: The tag check of FR-007 MUST compare the tag against the
  commit this attempt verified, not against the branch tip at report time, so
  that a branch which advanced after a correct release still reports a
  release.
- **FR-008**: A release run that was cancelled — by a maintainer or by a
  concurrency guard — MUST NOT by itself be reported as a successful release;
  where the tag state of FR-007 does not hold, the outcome MUST be reported
  as a cancelled or failed release rather than as a release.

**Making the verified head and the tagged commit the same commit**

- **FR-009**: A release cut by the automatic path MUST land on the exact
  commit that the end-to-end verification passed for. It MUST NOT be possible
  for the default branch to advance between the automatic path's check and
  the creation of the tag in a way that results in a different commit being
  tagged.
- **FR-010**: The guarantee in FR-009 MUST be enforced by the release
  automation at the moment it creates the tag, not by the automatic path
  narrowing the window before the request. The release automation MUST accept
  an optional commit on the request; when one is supplied it MUST build the
  release from that exact commit, and it MUST refuse to create the tag unless
  that commit is still the default branch's tip at the moment the tag would
  be created.
- **FR-010a**: The comparison in FR-010 MUST be made at tag time against the
  branch tip as it is then, not against anything read when the request was
  accepted or when the checkout was made, so that a request which sat queued
  behind another release run is covered.
- **FR-011**: When the enforcement in FR-010 refuses, no exact version tag
  MUST be created, no floating major tag MUST be created or moved, and no
  release MUST be published.
- **FR-012**: A refusal under FR-010 MUST state both the commit the request
  named and the branch tip observed at tag time, clearly enough for a
  maintainer to conclude "the branch moved on" without opening run logs.
- **FR-013**: The automatic path MUST report a refusal under FR-010 as the
  expected "the branch advanced" outcome — the same class as its existing
  stale-head skip — and MUST NOT file it as a release failure or a pipeline
  defect.
- **FR-014**: A commit that is not the default branch's current tip at tag
  time MUST be refused whether it is an ancestor of the tip, has been removed
  from the branch's history, or was never on the branch.

**Preserving the manual path**

- **FR-015**: The manual release dispatch MUST keep working with exactly the
  inputs it requires today. Both inputs this feature adds — the attempt token
  of FR-002 and the commit of FR-010 — MUST be optional, and omitting them
  MUST produce today's behaviour unchanged: the branch tip is checked out and
  tagged, with no tip comparison and no new refusal.
- **FR-016**: A manual release dispatch MUST NOT be capable of satisfying the
  automatic path's correlating evidence, regardless of the version it names
  or when it is started. A dispatch carrying no attempt token MUST produce a
  run title that no attempt's correlation can match.
- **FR-017**: This feature MUST NOT add any new gate, precondition, or
  required input to the human release path, consistent with FR-021 of spec
  045.

**Keeping the guarantees from rotting**

- **FR-018**: Both guarantees MUST be covered by deterministic checks that
  run before a release, so that a future edit which reintroduces
  recency-based selection, drops the attempt token from the release run's
  title, removes the tag-time tip refusal, or lets a release be reported from
  a run conclusion instead of the tag state fails rather than merges quietly.
- **FR-019**: The contract between the two workflows — what the request
  carries, what the release automation promises about the commit it tags, and
  what the automatic path is permitted to report as a release — MUST be
  written down in one place, with each workflow pointing at it rather than
  restating it.
- **FR-020**: Nothing in this feature may weaken the existing checks the
  release automation performs today: the lint gates, the tag-collision
  refusal, the breaking-release rules, and the always-present breaking-changes
  section of the release notes all continue to apply unchanged.

### Key Entities

- **Release request**: The act of asking the release automation to cut a
  version. Today it carries the version and the breaking flags. This feature
  makes it carry two further optional values: the attempt token of FR-002,
  which says which attempt is asking, and the commit of FR-010, which says
  which head it means. A manual dispatch supplies neither.
- **Verified head**: The exact commit that the end-to-end verification
  passed for. Already produced today; this feature makes it travel with the
  request instead of being compared against and then discarded.
- **Correlated run**: The release run that a given automatic attempt caused,
  established by its attempt token and the time bound rather than by recency.
  Distinct from "the newest release run", which is what the attempt reads
  today. It supplies the report's log link and its diagnosis of a failure; it
  is not what proves a release happened.
- **Tag state**: Whether the exact version tag exists and points at the
  verified commit. This is the authority for "was this attempt's release
  cut", per FR-007, and the fact the standing failure issue closes on.
- **Release outcome**: The single value the automatic attempt's report reads
  to decide what to say. Today it spans released, failed, stale-head, and
  tip-unresolved; this feature adds the ambiguous/unobserved correlation
  outcome of FR-005 and FR-006, and settles "released" on the tag state
  rather than on a run's conclusion.
- **Standing failure issue**: The one durable report consecutive failures
  fold into, and which a successful release closes. Closing it on a foreign
  run is the concrete harm FR-007 prevents by resting that closure on the tag
  state.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In a run where a manual release dispatch and an automatic
  attempt are in flight together, the automatic attempt's report references
  only the run it caused — zero reports attributing a foreign run, under any
  ordering of the two dispatches.
- **SC-002**: 100% of tags created by the automatic path point at a commit
  that a passing end-to-end verification named, with no dependence on how
  long the attempt's steps took or on how busy the default branch was.
- **SC-003**: A maintainer can dispatch a release by hand supplying the same
  inputs as today, with no additional required field and no new way for that
  dispatch to be refused.
- **SC-004**: Every outcome the automatic attempt can reach — released,
  release failed, request rejected, run not observed, correlation ambiguous,
  branch advanced — is distinguishable from the others by reading the report
  alone, in under a minute, without opening run logs.
- **SC-005**: A change that reverts either guarantee — selecting the release
  run by recency again, dropping the attempt token from the run title,
  dropping the tag-time commit refusal, or reporting a release from a run
  conclusion instead of the tag state — is caught by a deterministic check
  before it can merge.
- **SC-006**: No existing release behaviour regresses: the full local gate
  suite passes, and a release cut after this change performs the same lint
  gates, tag-collision refusal, floating-tag handling, and release-notes
  structure as before.

## Assumptions

- The automatic release path as merged for spec 045 is the baseline. This
  feature changes how it identifies the run it caused and how it guarantees
  the tagged commit, and changes nothing else about detection, end-to-end
  verification, version computation, collision handling, pausing, or the
  shape of the standing failure issue.
- The release automation remains the only thing that creates tags and
  publishes releases. This feature supplies it more evidence; it never
  duplicates or bypasses it (spec 045 FR-020).
- Breaking releases stay a human act. Nothing here gives the automatic path a
  route to a major bump or to declaring a release breaking.
- Immutability of published tags is unchanged: a wrongly-tagged commit cannot
  be un-tagged, which is why FR-009 is framed as prevention and why FR-010
  refuses at tag time rather than detecting a mismatch after the fact.
- The two workflows keep their separate single-in-flight guards unless the
  owner's answers require otherwise; correlation is specified to hold even if
  they were merged into one, so serialisation is not load-bearing for
  correctness here.
- A maintainer's manual dispatch is the realistic competing run. Other
  sources of a release run (a re-run of a previous release run, for example)
  are treated the same way: not ours unless the evidence says so.
- The waiting period for the correlated run to appear is a tuning knob, not a
  correctness property; FR-005 defines the behaviour when it elapses, and the
  current value is assumed adequate until evidence says otherwise. Resting
  the released/not-released decision on the tag state (FR-007) is what keeps
  it from becoming a correctness property.
- Reporting remains report-only (spec 045 FR-027). Nothing in this feature
  takes corrective action on the repository — it does not retry a release,
  delete a tag, or cancel a competing run.
- This repository is public and both workflows are read by adopters as
  examples; the contract document of FR-019 is written on that assumption.
