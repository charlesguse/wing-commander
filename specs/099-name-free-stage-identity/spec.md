# Feature Specification: Name-Free Stage Identity for Watchdog Collectors

**Feature Branch**: `099-name-free-stage-identity`

**Created**: 2026-09-29

**Status**: Draft

**Input**: Lifecycle issue #750 — "watchdog collectors silently skip adopters whose wrapper names differ from the reference names"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - An adopter with their own wrapper names gets the same watchdog coverage (Priority: P1)

An adopter installs the pipeline and names their wrapper workflows to fit
their own repository's conventions — `ai-spec-intake`, `Feature Pipeline:
Implement`, anything at all. The watchdog inspects their runs and produces
exactly the same findings it would produce for a repository that copied the
reference wrapper names verbatim: stage/spec-meta mismatches are detected,
lost progress on a plan/tasks/implement run is detected, finalize PR claims
and intake spec-number collisions are checked, and a dispatched run's spec
slug still resolves.

**Why this priority**: This is the defect. Today every one of those
collectors takes its "not my stage — skipping" branch for a renamed wrapper
and the watchdog reports "run passed inspection. No problems detected." A
green check that cannot fail its subject is precisely what constitution
VIII forbids, and hardcoded reference names in a published stage are
precisely what constitution VI forbids.

**Independent Test**: Drive one watchdog inspection against a run of a
wrapper whose display name shares no substring with the reference names,
where the underlying spec is in a state the spec-meta collector must flag.
The finding is filed. Repeat with the reference-named wrapper: the same
finding, same facts.

**Acceptance Scenarios**:

1. **Given** an inspected run from a wrapper named `Feature Pipeline:
   Implement` that calls the implement stage, and a spec whose recorded
   stage is earlier than `implement`, **When** the watchdog inspects that
   run, **Then** the spec-meta collector emits the stage-mismatch signal it
   would have emitted for a run named `Wing Commander · 5 implement`.
2. **Given** an inspected run from a renamed plan wrapper that pushed no
   commits to its spec branch and whose record carries branch-advance
   evidence, **When** the watchdog inspects it, **Then** branch-drift
   measures the spec branch and reports lost progress rather than skipping
   as "not a push-expected stage".
3. **Given** a dispatched run from a renamed tasks wrapper whose head is the
   default branch, **When** the inspected-run-identity composite resolves
   the spec slug, **Then** the metrics-record fallback runs and the slug
   resolves, so collectors and the diagnose verdict file against the spec's
   lifecycle issue instead of the bare run URL.
4. **Given** an inspected run from a renamed finalize wrapper whose final PR
   body overstates its task count, **When** the watchdog inspects it,
   **Then** final-pr-claims runs and the narrative-drift signal is emitted.
5. **Given** an inspected run from a renamed intake wrapper that created a
   spec number already claimed, **When** the watchdog inspects it, **Then**
   spec-collision runs and the collision signal is emitted.

---

### User Story 2 - A maintainer can tell when stage identity was not resolved (Priority: P2)

When neither the inspected run's own evidence nor its display name yields a
stage, the watchdog says so — in the step summary and in whatever the
maintainer reads about that inspection — rather than emitting a silent
"skipping" line inside a collector nobody reads and a top-level "passed
inspection" verdict.

**Why this priority**: Without this, the fix is only as good as the new
identity source: the moment a run's record is missing or expired the
adopter is back in today's silent-skip world with no way to know. The P1
story delivers coverage; this story delivers the ability to trust it.
Constitution VIII: a collector that cannot reach its subject must say so
rather than report a pass it did not earn.

**Independent Test**: Inspect a run that emitted no metrics record and
carries an unrecognised display name. The inspection's own report names the
collectors that could not run, and the top-level verdict is not an
unqualified clean bill of health.

**Acceptance Scenarios**:

1. **Given** an inspected run with no resolvable stage identity from any
   source, **When** the watchdog finishes, **Then** its report distinguishes
   "inspected, no problems" from "some evidence classes were not examined
   because the stage could not be identified".
2. **Given** an inspected run whose display name is unrecognised but whose
   record names its stage, **When** the watchdog finishes, **Then** no
   warning about the name is required for the inspection to be complete —
   the stage was identified.

---

### User Story 3 - The adoption docs state exactly what still depends on a name (Priority: P3)

`docs/adoption.md` states, in one place, whether wrapper display names are
free-form and which pipeline behaviours (if any) still read them, so an
adopter choosing a name knows what they are choosing.

**Why this priority**: Documentation cannot substitute for the fix, but a
reader who has to infer a naming requirement from eight `case "$RUN_NAME"`
branches in a published stage is the reason this issue exists. Today the
reference names appear in the example wrappers with no statement either way.

**Independent Test**: Read `docs/adoption.md` alone and answer "may I rename
my wrappers, and what do I lose?" without opening `watchdog.yml`.

**Acceptance Scenarios**:

1. **Given** the shipped `docs/adoption.md`, **When** an adopter reads the
   wrapper section, **Then** it states whether the reference display names
   are required and lists any behaviour that still keys on them.

---

### Edge Cases

- **The record is gone.** Artifact retention expired, the artifact was
  never uploaded, or the download failed. The run's stage is then knowable
  only from its name — which is exactly the case the reference-name match
  handles today. Whether this falls back to the name is Q1.
- **The run emitted no record at all.** A run that was skipped, cancelled,
  or failed before its metrics step never wrote one. Most collectors
  already exit early on `skipped`/`cancelled`, but a run that *failed* mid-
  stage is still inspected and is exactly the kind the watchdog exists for.
- **The record exists but carries no stage.** `stage_available: false` is a
  shape the metrics-summary composite explicitly supports. It must be
  treated as "no stage from this source", never as the empty-string stage.
- **The run is not a pipeline stage at all.** An adopter's unrelated
  workflow, or the pipeline's own cleanup, rebase, or pr-conversation runs.
  These have no single spec and no expected stage transition; the correct
  outcome is still "skip, on purpose". Whether an unrecognised name is
  worth a warning here — where most unrecognised names will legitimately
  land — is Q3.
- **The record's stage and the name disagree.** A wrapper named
  `Wing Commander · 3 plan` that actually calls the tasks stage, or a single
  wrapper file that calls two stages. Which one wins follows from Q1.
- **Several records, one run.** An implement run writes a cycle record and
  a progress record; a rebase run writes one per matrix slug. Each names the
  same stage, so first-record-wins is safe for the stage field even where it
  is unsafe for the spec field.
- **Self-inspection.** The watchdog's own record carries `stage: watchdog`
  *and* borrows the spec of the run it inspected. The stage field is
  therefore trustworthy for self-inspection even though the spec field is
  not — which is the observation the allowlist question (Q2) turns on.
- **A record borrowed from another run.** The existing allowlist exists to
  stop the watchdog's, rebase's, and cleanup's records from tying those runs
  to an arbitrary spec. Any change here must not reopen that.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The pipeline MUST resolve the inspected run's stage identity
  from evidence that does not depend on the run's workflow display name,
  for every stage that emits a metrics record.
- **FR-002**: Every site that today identifies the inspected stage by
  matching a reference display name MUST consume the resolved stage
  identity instead of matching a name. The known sites are: the
  inspected-run-identity composite's metrics-record slug-fallback allowlist;
  the branch-drift collector's push-expected-stage gate, its implement-only
  since-created baseline arms, and its stage label for the summary line; the
  spec-meta collector's expected-stage map; the final-pr-claims finalize
  scope guard; the spec-collision intake scope guard; and the watchdog's own
  self-inspection cascade guard.
- **FR-003**: The resolved stage identity MUST be derived once per
  inspection and shared by every consumer, rather than each collector
  deriving its own. (CLAUDE.md, "shared logic has exactly one home".)
- **FR-004**: Resolving the stage identity MUST NOT add a metrics-record
  download beyond the one the inspection already performs — the collectors
  that need the record today already share a single downloaded copy.
- **FR-005**: Every consumer MUST distinguish three states: stage
  identified and in scope, stage identified and out of scope (skip on
  purpose), and stage not identified. The third MUST NOT be reported as the
  second.
- **FR-006**: A stage identity that cannot be resolved MUST be surfaced in
  the inspection's report as an evidence class that was not examined, so
  the inspection is not reported as an unqualified clean pass.
  [NEEDS CLARIFICATION: Q3 — see below; whether an unrecognised display
  name additionally warrants a warning, and on which runs, is unresolved.]
- **FR-007**: The mapping from a resolved stage to its expected `spec-meta`
  lifecycle stage (intake→spec, plan→plan, tasks→tasks,
  implement→implement, finalize→review) MUST keep exactly one home, as the
  display-name map does today.
- **FR-008**: The set of stages whose every run advances exactly one spec —
  and whose record spec identity is therefore the run's own — MUST remain
  enforced, so a watchdog, rebase, or cleanup run is still never tied to a
  borrowed spec. [NEEDS CLARIFICATION: Q2 — see below; whether that set is
  re-expressed as an allowlist of resolved stage values, replaced by a
  property the record itself carries, or dropped in favour of a different
  guard is unresolved.]
- **FR-009**: The precedence between the name-free stage identity and the
  display name MUST be fixed and documented in one place. [NEEDS
  CLARIFICATION: Q1 — see below.]
- **FR-010**: The published stage workflows MUST NOT require an adopter's
  wrapper to carry any particular display name in order to receive the
  collector coverage FR-002 lists.
- **FR-011**: `docs/adoption.md` MUST state whether the reference wrapper
  display names are required, and MUST list any pipeline behaviour that
  still reads them.
- **FR-012**: A checked-in gate MUST fail if a reference display name
  reappears as a stage-identification condition at any of the FR-002 sites,
  so the consolidation survives the next edit. (CLAUDE.md: "a rule with no
  gate behind it lasts until the next session.")
- **FR-013**: Each failure and fallback branch this feature introduces MUST
  be exercised by a checked-in fixture — a record with no stage, a missing
  record, an unrecognised name, and a disagreement between the two sources.
  (Constitution VIII.)

### Key Entities

- **Inspected-run stage identity**: which pipeline stage the run under
  inspection executed, expressed as a stage value (`intake`, `clarify`,
  `plan`, `tasks`, `implement`, `finalize`, `cleanup`, `rebase`,
  `pr-conversation`, `watchdog`, `board-loop`) or "unknown". One value per
  inspection, plus the source it came from.
- **Metrics record stage field**: the `stage` / `stage_available` pair each
  stage's metrics record already carries. The literal is set inside the
  published stage workflow, not by the wrapper, so it is adopter-
  independent by construction.
- **Wrapper display name**: adopter-owned, free-form, currently load-
  bearing. After this feature its load-bearing role is whatever Q1 and Q3
  decide.
- **Single-spec stage set**: the stages whose every run advances exactly one
  spec. Today an allowlist of six display names; after this feature,
  whatever Q2 decides.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For the same underlying run, an inspection of a wrapper with
  an arbitrary display name and an inspection of a wrapper with the
  reference display name produce identical collector outcomes and identical
  findings — zero differences across all FR-002 sites.
- **SC-002**: Zero of the FR-002 sites decide stage scope by comparing
  against a reference display name, as measured by the FR-012 gate.
- **SC-003**: Zero inspections report an unqualified "passed inspection" for
  a run whose stage could not be identified.
- **SC-004**: The number of metrics-record downloads per inspection is
  unchanged from today.
- **SC-005**: An adopter can answer "may I rename my wrappers, and what do
  I lose?" from `docs/adoption.md` alone, with no reference to the stage
  workflow sources.
- **SC-006**: Every fallback and failure branch introduced has at least one
  checked-in fixture; zero branches are covered only by a manual
  demonstration.

## Open Questions

### Q1 — Precedence between the record's stage and the display name

**Context**: FR-009. The issue asks: "record stage first, then name?"

| Option | Answer | Implications |
|--------|--------|--------------|
| A | Record stage first; display name only when the record yields none | Adopter-neutral in the common case, and keeps today's behaviour intact for runs with no record (cancelled, failed-early, expired artifacts). Cost: two code paths forever, and the reference names stay in the source, so the FR-012 gate must permit them as a fallback while forbidding them as the primary. |
| B | Record stage only; no name fallback at all | One path, one source of truth, and the reference names leave the published stage entirely. Cost: a run whose record is missing or expired loses coverage it has today even in this repository — a regression for failed-early runs, which are the watchdog's core subject. |
| C | Display name first; record stage only when the name is unrecognised | Byte-identical behaviour for this repository, so the risk of regressing the worked example is lowest. Cost: the adopter-facing defect is fixed only for renamed wrappers whose runs left a record, and the reference names remain the primary contract in all but name. |

### Q2 — What the single-spec allowlist becomes

**Context**: FR-008, and the composite's `record_fallback` allowlist. The
allowlist exists so a watchdog, rebase, or cleanup run — whose record names
a spec it did not advance — is never tied to that spec.

| Option | Answer | Implications |
|--------|--------|--------------|
| A | Re-express the same six-member set as resolved stage values | Smallest change; the guard's meaning is unchanged and becomes adopter-independent. Cost: circular for the slug fallback specifically — the stage now comes from the same record whose spec field the allowlist is deciding whether to trust. Needs the plan to confirm that is sound (it is, if the stage field is trustworthy even in a borrowed record, which self-inspection suggests). |
| B | Have the record itself declare whether its spec identity is the run's own, and drop the name/stage allowlist | Puts the knowledge where it is known — in the stage that writes the record — and no central list can drift out of date as stages are added. Cost: widens the record's shape and touches every stage that emits one; a record written before the field existed must be handled. |
| C | Keep the allowlist keyed on display names, treating it as out of scope | Minimal blast radius. Cost: leaves the slug-resolution half of the reported defect unfixed, so a renamed dispatched wrapper still files findings against a bare run URL instead of its lifecycle issue. |

### Q3 — Whether an unrecognised display name is warned about

**Context**: FR-006. Most unrecognised names will legitimately belong to
runs that are not pipeline stages at all — an adopter's own workflows, plus
cleanup, rebase and pr-conversation.

| Option | Answer | Implications |
|--------|--------|--------------|
| A | Warn only when no stage could be resolved from any source, and only on a run that otherwise looks like a pipeline stage | Signal where it matters, silence where "unrecognised" is the normal answer. Cost: "otherwise looks like a pipeline stage" is a judgment that must be reduced to a deterministic condition (constitution IX). |
| B | Warn whenever the display name is unrecognised, regardless of whether a stage was resolved | Loudest, and an adopter learns immediately. Cost: fires on every non-stage run the watchdog inspects, which in this repository is routine — recurring noise that trains maintainers to ignore it, and under Q1-A it fires even when identity succeeded. |
| C | Never warn about the name; report only the unresolved-identity state (FR-005/FR-006) | No new noise, and the name stops being something the pipeline has an opinion about. Cost: an adopter who renamed a wrapper *and* whose runs leave no record sees only a generic "evidence class not examined" line, with no hint that the name is the reason. |

## Assumptions

- The metrics record's `stage` literal is set inside each published stage
  workflow rather than passed by the wrapper, so it is already adopter-
  independent and needs no new adopter action. Verified against the stage
  workflows, not assumed from the issue.
- #744's `record-stage` output is the intended carrier and has not yet
  merged. This spec is written against the shape the issue describes and
  does not depend on #744's internals; if #744 lands first, this feature
  consumes its output, and if it does not, this feature establishes the
  output itself.
- Reference display names remain in the example wrappers in
  `docs/adoption.md` — this feature stops them from being *required*, it
  does not rename anything.
- Scope is the watchdog's identification of the *inspected* stage. Two
  related name dependencies are deliberately out of scope and are recorded
  here so the plan does not have to rediscover them: the watchdog's
  discovery of its own prior runs by workflow name (`gh run list
  --workflow`), which is a run-discovery concern rather than an
  inspected-stage concern, and any adopter-facing trigger configuration,
  which is wrapper-owned per constitution VII.
- Behaviour for this repository's own reference-named wrappers must not
  change; every option above is evaluated against that.
- Because this behaviour only runs in Actions, it is proven after merge by
  re-driving one watchdog run and recording the evidence, per CLAUDE.md.
